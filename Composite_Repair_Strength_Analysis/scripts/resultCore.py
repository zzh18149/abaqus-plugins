# -*- coding: ascii -*-
"""Shared ODB extraction and residual-strength evaluation utilities.

Abaqus/CAE 2024 uses Python 3.10; native API paths are Unicode strings.
"""

from __future__ import print_function

import csv
import json
import locale
import math
import os

from odbAccess import openOdb


ENERGY_NAMES = (
    'ALLIE', 'ALLKE', 'ALLSE', 'ALLAE', 'ALLDMD', 'ALLVD',
    'ALLFD', 'ALLPD', 'ALLPW', 'ALLCW', 'ALLMW', 'ALLDC',
    'ALLWK', 'ETOTAL')

DAMAGE_MODES = (
    ('SDV2', 'fiber tension'),
    ('SDV3', 'fiber compression/shear'),
    ('SDV4', 'matrix tension'),
    ('SDV5', 'matrix compression'),
    ('SDV6', 'delamination'))

EPS = 1.0e-20

def _abaqus_api_path(path_value):
    """Return str for the Python 3 odbAccess API, including PathLike input."""
    value = os.fsdecode(path_value)
    if os.name == 'nt' and not value.isascii():
        locale.setlocale(locale.LC_CTYPE, '.UTF8')
    return value



def _repo_name(repo, wanted):
    wanted_upper = str(wanted).upper()
    for name in repo.keys():
        if str(name).upper() == wanted_upper:
            return name
    return None


def _find_instance(assembly, wanted):
    exact = _repo_name(assembly.instances, wanted)
    if exact is not None:
        return assembly.instances[exact]
    wanted_upper = str(wanted).upper()
    for name in assembly.instances.keys():
        if wanted_upper in str(name).upper():
            return assembly.instances[name]
    return None


def _find_node_set(assembly, instance, wanted):
    if instance is not None:
        exact = _repo_name(instance.nodeSets, wanted)
        if exact is not None:
            return instance.nodeSets[exact], (
                'instance:' + instance.name + '/' + str(exact))
    exact = _repo_name(assembly.nodeSets, wanted)
    if exact is not None:
        return assembly.nodeSets[exact], 'assembly:' + str(exact)

    wanted_upper = str(wanted).upper()
    for name in assembly.nodeSets.keys():
        if wanted_upper in str(name).upper():
            return assembly.nodeSets[name], 'assembly:' + str(name)
    if instance is not None:
        for name in instance.nodeSets.keys():
            if wanted_upper in str(name).upper():
                return instance.nodeSets[name], (
                    'instance:' + instance.name + '/' + str(name))
    return None, 'NOT FOUND'


def _field_key(frame, wanted):
    exact = _repo_name(frame.fieldOutputs, wanted)
    if exact is not None:
        return exact
    wanted_upper = str(wanted).upper()
    for name in frame.fieldOutputs.keys():
        name_upper = str(name).upper()
        if name_upper == wanted_upper or name_upper.startswith(
                wanted_upper + ' '):
            return name
    return None


def _component(data, index):
    try:
        return float(data[index])
    except Exception:
        return None


def _scalar(data):
    try:
        return float(data)
    except Exception:
        pass
    try:
        return float(data[0])
    except Exception:
        return None


def _history(region, variable):
    exact = _repo_name(region.historyOutputs, variable)
    if exact is not None:
        return list(region.historyOutputs[exact].data)
    variable_upper = str(variable).upper()
    for name, output in region.historyOutputs.items():
        if str(name).upper().endswith(variable_upper):
            return list(output.data)
    return []


def _find_energy_region(step):
    best = None
    best_score = -1
    for region in step.historyRegions.values():
        available = set([
            str(name).upper() for name in region.historyOutputs.keys()])
        score = sum([1 for name in ENERGY_NAMES if name in available])
        if 'ALLIE' in available and 'ALLKE' in available:
            score += 100
        if score > best_score:
            best = region
            best_score = score
    return best


def _nearest_value(history, target_time):
    if not history:
        return None
    return min(history, key=lambda item: abs(item[0] - target_time))[1]


def _smoothed_curve(curve):
    """Return centered moving-average force without changing coordinates."""
    if len(curve) < 7:
        return list(curve), 1
    window = int(round(0.02 * len(curve)))
    window = max(5, min(21, window))
    if window % 2 == 0:
        window += 1
    half_window = window // 2
    output = []
    for index, row in enumerate(curve):
        first = max(0, index - half_window)
        last = min(len(curve), index + half_window + 1)
        average_force = sum([
            item['force_abs'] for item in curve[first:last]
        ]) / float(last - first)
        new_row = dict(row)
        new_row['force_filtered'] = average_force
        output.append(new_row)
    return output, window


def _linear_slope(points):
    if len(points) < 2:
        return None
    count = float(len(points))
    sum_x = sum([item[0] for item in points])
    sum_y = sum([item[1] for item in points])
    sum_xx = sum([item[0] * item[0] for item in points])
    sum_xy = sum([item[0] * item[1] for item in points])
    denominator = count * sum_xx - sum_x * sum_x
    if abs(denominator) <= EPS:
        return None
    return (count * sum_xy - sum_x * sum_y) / denominator


def extract_odb(odb_path):
    """Extract field-derived force/displacement, energies and damage data."""
    odb_path = os.path.abspath(odb_path)
    odb_api_path = _abaqus_api_path(odb_path)
    odb = openOdb(path=odb_api_path, readOnly=True)
    try:
        if not odb.steps:
            raise ValueError('ODB contains no analysis step: ' + odb_path)

        assembly = odb.rootAssembly
        base_instance = _find_instance(assembly, 'PART-BASE-1')
        if base_instance is None:
            base_instance = _find_instance(assembly, 'PART-BASE')
        right_set, right_scope = _find_node_set(
            assembly, base_instance, 'SET-RIGHT-END')
        left_set, left_scope = _find_node_set(
            assembly, base_instance, 'SET-LEFT-END')
        if right_set is None:
            raise ValueError(
                'Set-Right-End was not found in ODB: ' + odb_path)

        curve = []
        energies = []
        first_damage = None
        damage_maximum = {}
        deleted_status_final = None
        deleted_sdv1_final = None
        last_frame = None
        cumulative_time = 0.0
        step_names = list(odb.steps.keys())

        for step_index, step_name in enumerate(step_names):
            step = odb.steps[step_name]
            step_offset = cumulative_time
            for frame_index, frame in enumerate(step.frames):
                last_frame = frame
                u_key = _field_key(frame, 'U')
                rf_key = _field_key(frame, 'RF')
                if u_key is not None and rf_key is not None:
                    right_u = frame.fieldOutputs[u_key].getSubset(
                        region=right_set).values
                    right_rf = frame.fieldOutputs[rf_key].getSubset(
                        region=right_set).values
                    u_values = []
                    rf_values = []
                    for value in right_u:
                        number = _component(value.data, 0)
                        if number is not None:
                            u_values.append(number)
                    for value in right_rf:
                        number = _component(value.data, 0)
                        if number is not None:
                            rf_values.append(number)
                    if u_values and rf_values:
                        left_sum = None
                        if left_set is not None:
                            left_values = frame.fieldOutputs[rf_key].getSubset(
                                region=left_set).values
                            left_numbers = []
                            for value in left_values:
                                number = _component(value.data, 0)
                                if number is not None:
                                    left_numbers.append(number)
                            if left_numbers:
                                left_sum = sum(left_numbers)
                        right_sum = sum(rf_values)
                        equilibrium = None
                        if left_sum is not None:
                            scale = max(
                                abs(right_sum), abs(left_sum), EPS)
                            equilibrium = abs(
                                right_sum + left_sum) / scale
                        curve.append({
                            'odb': odb_path,
                            'step': step_name,
                            'step_index': step_index,
                            'frame_index': frame_index,
                            'time_local': float(frame.frameValue),
                            'time': step_offset + float(frame.frameValue),
                            'displacement': sum(u_values) /
                            float(len(u_values)),
                            'displacement_min': min(u_values),
                            'displacement_max': max(u_values),
                            'force_signed': right_sum,
                            'force_abs': abs(right_sum),
                            'left_force_signed': left_sum,
                            'equilibrium_ratio': equilibrium,
                            'right_node_count': len(u_values),
                        })

                frame_time = step_offset + float(frame.frameValue)
                for variable, mode in DAMAGE_MODES:
                    key = _field_key(frame, variable)
                    if key is None:
                        continue
                    maximum = 0.0
                    for value in frame.fieldOutputs[key].values:
                        number = _scalar(value.data)
                        if number is not None:
                            maximum = max(maximum, number)
                    damage_maximum[variable] = max(
                        damage_maximum.get(variable, 0.0), maximum)
                    if first_damage is None and maximum >= 1.0:
                        first_damage = {
                            'time_s': frame_time,
                            'criterion': variable,
                            'mode': mode,
                            'value': maximum,
                            'source': 'composite',
                        }

            energy_region = _find_energy_region(step)
            if energy_region is not None:
                histories = {}
                for name in ENERGY_NAMES:
                    histories[name] = _history(energy_region, name)
                base_history = histories.get('ALLIE')
                if not base_history:
                    for name in ENERGY_NAMES:
                        if histories.get(name):
                            base_history = histories[name]
                            break
                if base_history:
                    for local_time, unused in base_history:
                        row = {
                            'odb': odb_path,
                            'step': step_name,
                            'time_local': float(local_time),
                            'time': step_offset + float(local_time),
                        }
                        for name in ENERGY_NAMES:
                            value = _nearest_value(
                                histories.get(name), local_time)
                            row[name] = (
                                None if value is None else float(value))
                        energies.append(row)

            if step.frames:
                cumulative_time += float(step.frames[-1].frameValue)

        if last_frame is not None:
            status_key = _field_key(last_frame, 'STATUS')
            if status_key is not None:
                deleted_status_final = 0
                for value in last_frame.fieldOutputs[status_key].values:
                    number = _scalar(value.data)
                    if number is not None and number < 0.5:
                        deleted_status_final += 1
            sdv1_key = _field_key(last_frame, 'SDV1')
            if sdv1_key is not None:
                deleted_sdv1_final = 0
                for value in last_frame.fieldOutputs[sdv1_key].values:
                    number = _scalar(value.data)
                    if number is not None and number < 0.5:
                        deleted_sdv1_final += 1

        dimensions = None
        if base_instance is not None and len(base_instance.nodes) > 0:
            xs = []
            ys = []
            zs = []
            for node in base_instance.nodes:
                xs.append(float(node.coordinates[0]))
                ys.append(float(node.coordinates[1]))
                zs.append(float(node.coordinates[2]))
            dimensions = {
                'length': max(xs) - min(xs),
                'width': max(ys) - min(ys),
                'thickness': max(zs) - min(zs),
            }

        return {
            'odb_path': odb_path,
            'curve': curve,
            'energies': energies,
            'first_damage': first_damage,
            'damage_maximum': damage_maximum,
            'deleted_status_final': deleted_status_final,
            'deleted_sdv1_final': deleted_sdv1_final,
            'dimensions': dimensions,
            'right_scope': right_scope,
            'left_scope': left_scope,
        }
    finally:
        odb.close()


def combine_segments(segment_results):
    """Combine monotonic restart-segment curves without duplicate starts."""
    combined_curve = []
    combined_energies = []
    first_damage = None
    damage_maximum = {}
    deleted_status = None
    deleted_sdv1 = None
    dimensions = None
    odb_paths = []
    global_time_offset = 0.0

    for segment_index, result in enumerate(segment_results):
        odb_paths.append(result['odb_path'])
        segment_curve = list(result.get('curve', []))
        segment_energies = list(result.get('energies', []))
        segment_global_start = global_time_offset
        local_start = 0.0
        if segment_curve:
            local_start = segment_curve[0]['time']
            previous_displacement = (
                None if not combined_curve else
                combined_curve[-1]['displacement'])
            for row in segment_curve:
                if (previous_displacement is not None and
                        abs(row['displacement'] - previous_displacement)
                        <= 1.0e-10 and row is segment_curve[0]):
                    continue
                new_row = dict(row)
                new_row['segment_index'] = segment_index
                new_row['time'] = (
                    global_time_offset + row['time'] - local_start)
                combined_curve.append(new_row)
            if combined_curve:
                global_time_offset = combined_curve[-1]['time']

        if segment_energies:
            local_energy_start = segment_energies[0]['time']
            energy_offset = (
                0.0 if not combined_energies else
                combined_energies[-1]['time'])
            for row in segment_energies:
                new_row = dict(row)
                new_row['segment_index'] = segment_index
                new_row['time'] = (
                    energy_offset + row['time'] - local_energy_start)
                combined_energies.append(new_row)

        event = result.get('first_damage')
        if event is not None and first_damage is None:
            first_damage = dict(event)
            first_damage['segment_index'] = segment_index
            first_damage['time_s'] = (
                segment_global_start + float(event['time_s']) - local_start)
        for name, value in result.get('damage_maximum', {}).items():
            damage_maximum[name] = max(
                damage_maximum.get(name, 0.0), value)
        deleted_status = result.get('deleted_status_final')
        deleted_sdv1 = result.get('deleted_sdv1_final')
        if dimensions is None:
            dimensions = result.get('dimensions')

    return {
        'odb_paths': odb_paths,
        'curve': combined_curve,
        'energies': combined_energies,
        'first_damage': first_damage,
        'damage_maximum': damage_maximum,
        'deleted_status_final': deleted_status,
        'deleted_sdv1_final': deleted_sdv1,
        'dimensions': dimensions,
    }


def evaluate_curve(curve, drop_ratio=0.15, minimum_post_peak_frames=5):
    if len(curve) < 3:
        raise ValueError('Force-displacement curve contains too few frames')
    filtered, window = _smoothed_curve(curve)
    peak_index = max(
        range(len(filtered)),
        key=lambda index: filtered[index]['force_filtered'])
    peak_row = filtered[peak_index]
    post_rows = filtered[peak_index + 1:]
    minimum_post_peak = (
        min([row['force_filtered'] for row in post_rows])
        if post_rows else filtered[-1]['force_filtered'])
    threshold = peak_row['force_filtered'] * (1.0 - drop_ratio)
    enough_frames = len(post_rows) >= int(minimum_post_peak_frames)
    trailing_rows = (
        post_rows[-int(minimum_post_peak_frames):]
        if enough_frames else [])
    sustained_drop = (
        enough_frames and trailing_rows and
        all([row['force_filtered'] <= threshold for row in trailing_rows]))
    tail_slope = None
    if trailing_rows:
        tail_slope = _linear_slope([
            (abs(row['displacement']), row['force_filtered'])
            for row in trailing_rows])
    negative_tail = tail_slope is not None and tail_slope < 0.0
    # Once the last required frames remain below the drop threshold, the
    # peak is demonstrated even if the damaged structure settles onto a
    # nearly horizontal residual-load plateau.
    post_peak_drop = sustained_drop
    peak_near_end = peak_index >= len(filtered) - max(
        int(minimum_post_peak_frames) + 1,
        int(round(0.10 * len(filtered))))

    return {
        'filtered_curve': filtered,
        'filter_window': window,
        'peak_index': peak_index,
        'peak_force': peak_row['force_filtered'],
        'raw_peak_force': max([row['force_abs'] for row in curve]),
        'peak_displacement': peak_row['displacement'],
        'peak_time': peak_row['time'],
        'final_force': filtered[-1]['force_filtered'],
        'final_displacement': filtered[-1]['displacement'],
        'minimum_post_peak_force': minimum_post_peak,
        'drop_ratio_achieved': (
            0.0 if peak_row['force_filtered'] <= EPS else
            1.0 - minimum_post_peak / peak_row['force_filtered']),
        'required_drop_ratio': drop_ratio,
        'minimum_post_peak_frames': int(minimum_post_peak_frames),
        'enough_post_peak_frames': enough_frames,
        'sustained_drop': sustained_drop,
        'tail_slope_N_per_mm': tail_slope,
        'negative_tail_slope': negative_tail,
        'peak_near_end': peak_near_end,
        'post_peak_drop': post_peak_drop,
    }


def _nearest_energy(energies, target_time, name):
    values = []
    for row in energies:
        value = row.get(name)
        if value is not None:
            values.append((row['time'], value))
    if not values:
        return None
    return min(values, key=lambda item: abs(item[0] - target_time))[1]


def build_result(combined, metadata, drop_ratio=0.15,
                 minimum_post_peak_frames=5):
    curve_eval = evaluate_curve(
        combined['curve'], drop_ratio, minimum_post_peak_frames)
    peak_time = curve_eval['peak_time']
    peak_force = curve_eval['peak_force']
    peak_displacement = curve_eval['peak_displacement']

    width = float(metadata.get('plateWidth_mm', 0.0))
    thickness = float(metadata.get('plateTotalThickness_mm', 0.0))
    if (width <= 0.0 or thickness <= 0.0) and combined.get('dimensions'):
        width = float(combined['dimensions']['width'])
        thickness = float(combined['dimensions']['thickness'])
    area = width * thickness
    nominal_stress = None if area <= EPS else peak_force / area

    energy_at_peak = {}
    for name in ENERGY_NAMES:
        energy_at_peak[name] = _nearest_energy(
            combined['energies'], peak_time, name)
    allie = energy_at_peak.get('ALLIE')
    allke = energy_at_peak.get('ALLKE')
    allae = energy_at_peak.get('ALLAE')
    allvd = energy_at_peak.get('ALLVD')
    allwk = energy_at_peak.get('ALLWK')
    etotal = energy_at_peak.get('ETOTAL')
    ke_ie = None
    ae_ie = None
    vd_ie = None
    if allie is not None and abs(allie) > EPS:
        if allke is not None:
            ke_ie = abs(allke / allie)
        if allae is not None:
            ae_ie = abs(allae / allie)
        if allvd is not None:
            vd_ie = abs(allvd / allie)
    energy_scale = max(
        abs(allwk) if allwk is not None else 0.0,
        abs(allie) if allie is not None else 0.0,
        EPS)
    energy_balance = (
        None if etotal is None else abs(etotal) / energy_scale)

    peak_curve_row = min(
        combined['curve'],
        key=lambda row: abs(row['time'] - peak_time))
    equilibrium = peak_curve_row.get('equilibrium_ratio')

    damage_started = any([
        value > 1.0e-6
        for value in combined.get('damage_maximum', {}).values()])
    quasi_static = ke_ie is not None and ke_ie <= 0.10
    artificial_ok = ae_ie is None or ae_ie <= 0.05
    viscous_ok = vd_ie is None or vd_ie <= 0.05
    energy_ok = energy_balance is not None and energy_balance <= 0.01

    valid_strength = (
        curve_eval['post_peak_drop'] and quasi_static and
        damage_started and artificial_ok and viscous_ok and energy_ok)

    first_damage = combined.get('first_damage')
    if first_damage is not None:
        first_damage = dict(first_damage)
        nearest = min(
            combined['curve'],
            key=lambda row: abs(row['time'] - first_damage['time_s']))
        first_damage['force_N'] = nearest['force_abs']
        first_damage['displacement_mm'] = nearest['displacement']
        first_damage['nominalStress_MPa'] = (
            None if area <= EPS else nearest['force_abs'] / area)

    warnings = []
    if not curve_eval['post_peak_drop']:
        warnings.append(
            'The required sustained %.0f%% post-peak force drop was not '
            'demonstrated.' % (100.0 * drop_ratio))
    if curve_eval['peak_near_end']:
        warnings.append(
            'The force peak is too close to the end of the available curve.')
    if ke_ie is None:
        warnings.append('ALLKE/ALLIE could not be evaluated.')
    elif not quasi_static:
        warnings.append(
            'ALLKE/ALLIE at peak is %.6g, above 0.10.' % ke_ie)
    if not damage_started:
        warnings.append('No composite damage variable was activated.')
    if energy_balance is None:
        warnings.append('ETOTAL energy balance could not be evaluated.')
    elif not energy_ok:
        warnings.append(
            'Energy-balance ratio is %.6g, above 0.01.' % energy_balance)
    if ae_ie is not None and not artificial_ok:
        warnings.append('ALLAE/ALLIE is %.6g, above 0.05.' % ae_ie)
    if vd_ie is not None and not viscous_ok:
        warnings.append('ALLVD/ALLIE is %.6g, above 0.05.' % vd_ie)

    return {
        'schemaVersion': 4,
        'jobName': metadata.get('jobName', 'CompositeRepair'),
        'repairType': metadata.get('repairType'),
        'odbFiles': combined.get('odb_paths', []),
        'plateWidth_mm': width,
        'plateTotalThickness_mm': thickness,
        'grossArea_mm2': area,
        'peakForce_N': peak_force,
        'rawPeakForce_N': curve_eval['raw_peak_force'],
        'peakDisplacement_mm': peak_displacement,
        'peakTime_s': peak_time,
        'minimumPostPeakForce_N': curve_eval['minimum_post_peak_force'],
        'finalForce_N': curve_eval['final_force'],
        'finalDisplacement_mm': curve_eval['final_displacement'],
        'maximumNominalStress_MPa': nominal_stress,
        'forceFilterWindow_points': curve_eval['filter_window'],
        'postPeakDrop': curve_eval['post_peak_drop'],
        'requiredDropRatio': drop_ratio,
        'dropRatioAchieved': curve_eval['drop_ratio_achieved'],
        'minimumPostPeakFrames': minimum_post_peak_frames,
        'tailSlope_N_per_mm': curve_eval['tail_slope_N_per_mm'],
        'peakNearEnd': curve_eval['peak_near_end'],
        'ALLKE_atPeak_Nmm': allke,
        'ALLIE_atPeak_Nmm': allie,
        'ALLKE_ALLIE_atPeak': ke_ie,
        'quasiStatic': quasi_static,
        'ALLAE_ALLIE_atPeak': ae_ie,
        'artificialEnergyAcceptable': artificial_ok,
        'ALLVD_ALLIE_atPeak': vd_ie,
        'viscousEnergyAcceptable': viscous_ok,
        'ETOTAL_atPeak_Nmm': etotal,
        'ALLWK_atPeak_Nmm': allwk,
        'absoluteEnergyBalanceRatio_atPeak': energy_balance,
        'energyBalanced': energy_ok,
        'forceEquilibriumRelativeErrorAtPeak': equilibrium,
        'maximumDamageByVariable': combined.get('damage_maximum', {}),
        'maximumDamageVariable': (
            max(combined.get('damage_maximum', {}).values())
            if combined.get('damage_maximum') else None),
        'firstDamageEvent': first_damage,
        'deletedElementsBySTATUS_final': combined.get(
            'deleted_status_final'),
        'deletedElementsBySDV1_final': combined.get(
            'deleted_sdv1_final'),
        'validStrength': valid_strength,
        'warnings': warnings,
    }, curve_eval


def _open_csv(path):
    return open(path, 'w', encoding='utf-8', newline='')


def write_report(output_base, combined, metadata, drop_ratio=0.15,
                 minimum_post_peak_frames=5):
    """Write JSON, TXT and CSV report files. Return the result dictionary."""
    output_base = os.path.abspath(output_base)
    result, curve_eval = build_result(
        combined, metadata, drop_ratio, minimum_post_peak_frames)

    result_path = output_base + '_Result.json'
    with open(result_path, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, sort_keys=True)

    curve_path = output_base + '_ForceDisplacement.csv'
    handle = _open_csv(curve_path)
    try:
        writer = csv.writer(handle)
        writer.writerow((
            'Time_s', 'Displacement_mm', 'RawReactionForce_N',
            'FilteredReactionForce_N', 'RawNominalStress_MPa',
            'FilteredNominalStress_MPa', 'RightNodeCount',
            'ForceEquilibriumRelativeError', 'ODB', 'Step', 'Frame'))
        area = result['grossArea_mm2']
        for index, row in enumerate(combined['curve']):
            filtered_force = curve_eval['filtered_curve'][index][
                'force_filtered']
            writer.writerow((
                row['time'], row['displacement'], row['force_abs'],
                filtered_force,
                '' if area <= EPS else row['force_abs'] / area,
                '' if area <= EPS else filtered_force / area,
                row['right_node_count'],
                '' if row['equilibrium_ratio'] is None
                else row['equilibrium_ratio'],
                row.get('odb', ''), row.get('step', ''),
                row.get('frame_index', '')))
    finally:
        handle.close()

    energy_path = output_base + '_Energy.csv'
    handle = _open_csv(energy_path)
    try:
        writer = csv.writer(handle)
        writer.writerow(('Time_s',) + ENERGY_NAMES + ('ODB', 'Step'))
        for row in combined['energies']:
            writer.writerow(tuple([row['time']] + [
                '' if row.get(name) is None else row.get(name)
                for name in ENERGY_NAMES] + [
                row.get('odb', ''), row.get('step', '')]))
    finally:
        handle.close()

    damage_path = output_base + '_DamageSummary.csv'
    handle = _open_csv(damage_path)
    try:
        writer = csv.writer(handle)
        writer.writerow(('Variable', 'MaximumValue'))
        for name in sorted(combined.get('damage_maximum', {}).keys()):
            writer.writerow((name, combined['damage_maximum'][name]))
        writer.writerow((
            'DeletedElementsBySTATUS_final',
            combined.get('deleted_status_final')))
        writer.writerow((
            'DeletedElementsBySDV1_final',
            combined.get('deleted_sdv1_final')))
    finally:
        handle.close()

    text_path = output_base + '_Result.txt'
    with open(text_path, 'w', encoding='utf-8') as handle:
        handle.write('Composite repair residual-strength report\n')
        handle.write('=' * 52 + '\n')
        handle.write('Job: %s\n' % result['jobName'])
        handle.write('ODB files: %s\n' % ', '.join(result['odbFiles']))
        handle.write('Peak force: %.9g N\n' % result['peakForce_N'])
        handle.write(
            'Peak displacement: %.9g mm\n' %
            result['peakDisplacement_mm'])
        if result['maximumNominalStress_MPa'] is not None:
            handle.write(
                'Residual strength: %.9g MPa\n' %
                result['maximumNominalStress_MPa'])
        handle.write(
            'Final force: %.9g N\n' % result['finalForce_N'])
        handle.write(
            'Post-peak drop demonstrated: %s\n' %
            result['postPeakDrop'])
        handle.write(
            'Drop ratio achieved: %.6g\n' %
            result['dropRatioAchieved'])
        handle.write(
            'ALLKE/ALLIE at peak: %s\n' %
            ('unavailable' if result['ALLKE_ALLIE_atPeak'] is None
             else '%.6g' % result['ALLKE_ALLIE_atPeak']))
        handle.write(
            'Force equilibrium error at peak: %s\n' %
            ('unavailable' if result[
                'forceEquilibriumRelativeErrorAtPeak'] is None
             else '%.6g' % result[
                 'forceEquilibriumRelativeErrorAtPeak']))
        handle.write(
            'Valid residual strength: %s\n' % result['validStrength'])
        for warning in result['warnings']:
            handle.write('WARNING: %s\n' % warning)

    return result
