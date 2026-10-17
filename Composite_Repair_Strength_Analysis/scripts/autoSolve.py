# -*- coding: utf-8 -*-
"""One-click staged Explicit solve to a demonstrated residual-strength peak.

The user submits once.  The first analysis uses the displacement already
specified in the plug-in.  If a sustained post-peak force drop is not found,
this script creates Abaqus/Explicit restart models and continues the same
solution state in fixed displacement increments.
"""

from __future__ import print_function

import json
import math
import os
import sys
import traceback
from importlib import reload

from abaqus import mdb
from abaqusConstants import (
    ANALYSIS, AT_BEGINNING, BELOW_MIN, DEFAULT, DOMAIN,
    DOUBLE_PLUS_PACK, MODEL, ODB, OFF, ON, PERCENTAGE, RESTART,
    SEMI_AUTOMATIC, SINGLE, STEP, STEP_END)

modelData = globals()['modelData']
scriptsDir = os.path.join(modelData['pluginDir'], 'scripts')
if scriptsDir not in sys.path:
    sys.path.insert(0, scriptsDir)
import resultCore
reload(resultCore)


def _write_json(path, data):
    with open(path, 'w') as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def _write_status(path, lines):
    with open(path, 'w') as handle:
        handle.write('\n'.join(lines) + '\n')


def _job_status_ok(job):
    return str(job.status).upper() == 'COMPLETED'


def _create_job(name, model_name, job_type, subroutine, cpus):
    if name in mdb.jobs:
        status = str(mdb.jobs[name].status).upper()
        if status in ('SUBMITTED', 'RUNNING', 'CHECK_RUNNING'):
            raise ValueError(
                "Job '%s' is already %s." % (name, status))
        del mdb.jobs[name]
    return mdb.Job(
        name=name,
        model=model_name,
        description='Automatic residual-strength staged solve',
        type=job_type,
        atTime=None,
        waitMinutes=0,
        waitHours=0,
        queue=None,
        memory=90,
        memoryUnits=PERCENTAGE,
        explicitPrecision=DOUBLE_PLUS_PACK,
        nodalOutputPrecision=SINGLE,
        echoPrint=OFF,
        modelPrint=OFF,
        contactPrint=OFF,
        historyPrint=OFF,
        userSubroutine=subroutine,
        scratch='',
        resultsFormat=ODB,
        parallelizationMethodExplicit=DOMAIN,
        numDomains=cpus,
        activateLoadBalancing=False,
        multiprocessingMode=DEFAULT,
        numCpus=cpus)


def _metadata(job_name, cumulative_displacement, segment_index):
    return {
        'schemaVersion': 4,
        'jobName': job_name,
        'rootJobName': modelData['jobName'],
        'autoSolve': True,
        'autoSolveSegmentIndex': int(segment_index),
        'repairType': int(modelData['modify']['type']),
        'plateLength_mm': float(modelData['length']),
        'plateWidth_mm': float(modelData['height']),
        'plateTotalThickness_mm': float(modelData['depth']),
        'baseLayerCount': int(modelData['nlayers']),
        'baseLayerAngles_deg': list(modelData['layers']),
        'damageDiameter_mm': float(modelData['damageDiameter']),
        'repairLayerCount': int(modelData['modify']['n']),
        'repairLayerAngles_deg': list(modelData['modify']['layers']),
        'repairOuterDiameter_mm': float(
            modelData['modify']['outerDiameter']),
        'adhesiveThickness_mm': float(
            modelData['modify']['cohesive']),
        'loadingDisplacement_mm': float(cumulative_displacement),
        'stepTime_s': float(modelData['stepTime']),
        'targetTimeIncrement_s': float(
            modelData['targetTimeIncrement']),
        'meshLevel': int(modelData['meshLevel']),
        'peakDropRatio': float(modelData['peakDropRatio']),
        'minimumPostPeakFrames': int(
            modelData['minimumPostPeakFrames']),
    }


def _submit_and_extract(job, job_directory):
    job.submit(consistencyChecking=OFF)
    job.waitForCompletion()
    if not _job_status_ok(job):
        raise RuntimeError(
            "Job '%s' finished with status %s."
            % (job.name, str(job.status)))
    odb_path = os.path.join(job_directory, job.name + '.odb')
    if not os.path.isfile(odb_path):
        raise RuntimeError('ODB was not created: ' + odb_path)
    return odb_path, resultCore.extract_odb(odb_path)


base_job_name = str(modelData['jobName'])
base_model_name = 'Model-1'
cpus = int(modelData['numOfCpus'])
subroutine_file = os.path.abspath(modelData['mSubroutineFileKw'])
if not os.path.isfile(subroutine_file):
    raise ValueError('VUMAT file does not exist: ' + subroutine_file)
if base_model_name not in mdb.models:
    raise ValueError('Model-1 does not exist. Build the model first.')

job_directory = os.path.join(modelData['pluginDir'], 'jobs')
if not os.path.isdir(job_directory):
    os.makedirs(job_directory)
os.chdir(job_directory)

initial_displacement = abs(float(modelData['disValue']))
segment_displacement = abs(float(modelData['autoIncrementDisplacement']))
maximum_displacement = abs(float(modelData['autoMaximumDisplacement']))
minimum_post_peak_frames = int(modelData['minimumPostPeakFrames'])
drop_ratio = float(modelData['peakDropRatio'])
if segment_displacement <= 0.0:
    raise ValueError('Automatic continuation increment must be positive.')
if maximum_displacement < initial_displacement:
    maximum_displacement = initial_displacement
loading_rate = initial_displacement / float(modelData['stepTime'])
if loading_rate <= 0.0:
    raise ValueError('Loading displacement / step time must be positive.')

status_json = os.path.join(
    job_directory, base_job_name + '_AutoSolve_Status.json')
status_txt = os.path.join(
    job_directory, base_job_name + '_AutoSolve_Status.txt')
report_base = os.path.join(
    job_directory, base_job_name + '_AutoResidualStrength')

state = {
    'rootJobName': base_job_name,
    'status': 'PREPARING',
    'initialDisplacement_mm': initial_displacement,
    'continuationIncrement_mm': segment_displacement,
    'maximumDisplacement_mm': maximum_displacement,
    'requiredDropRatio': drop_ratio,
    'minimumPostPeakFrames': minimum_post_peak_frames,
    'segments': [],
}
_write_json(status_json, state)
_write_status(status_txt, [
    'Composite repair automatic residual-strength solve',
    'Status: PREPARING',
    'Root Job: ' + base_job_name,
])

segment_results = []
job_names = []
odb_paths = []
previous_job_name = None
previous_model_name = base_model_name
previous_step_name = 'Step-1'
cumulative_displacement = initial_displacement
finished_reason = None
curve_evaluation = None

try:
    # Write one restart state at the end of the initial Explicit step.
    initial_model = mdb.models[base_model_name]
    initial_model.steps['Step-1'].Restart(
        numberIntervals=1, overlay=ON, timeMarks=OFF)

    initial_odb = os.path.join(job_directory, base_job_name + '.odb')
    initial_lock = os.path.join(job_directory, base_job_name + '.lck')
    if os.path.isfile(initial_lock):
        raise ValueError(
            "Job '%s' is locked and may already be running." %
            base_job_name)
    if os.path.isfile(initial_odb):
        raise ValueError(
            "ODB '%s' already exists. Use a new Job name to protect the "
            "existing result." % initial_odb)

    state['status'] = 'RUNNING_INITIAL'
    _write_json(status_json, state)
    initial_job = _create_job(
        base_job_name, base_model_name, ANALYSIS,
        subroutine_file, cpus)
    metadata_path = os.path.join(
        job_directory, base_job_name + '_ModelData.json')
    _write_json(metadata_path, _metadata(
        base_job_name, cumulative_displacement, 0))
    odb_path, extracted = _submit_and_extract(
        initial_job, job_directory)
    segment_results.append(extracted)
    job_names.append(base_job_name)
    odb_paths.append(odb_path)
    previous_job_name = base_job_name

    combined = resultCore.combine_segments(segment_results)
    curve_evaluation = resultCore.evaluate_curve(
        combined['curve'], drop_ratio, minimum_post_peak_frames)
    state['segments'].append({
        'index': 0,
        'jobName': base_job_name,
        'odb': odb_path,
        'targetDisplacement_mm': cumulative_displacement,
        'peakForce_N': curve_evaluation['peak_force'],
        'finalForce_N': curve_evaluation['final_force'],
        'postPeakDrop': curve_evaluation['post_peak_drop'],
    })
    _write_json(status_json, state)

    segment_index = 0
    while not curve_evaluation['post_peak_drop']:
        if cumulative_displacement >= maximum_displacement - 1.0e-12:
            finished_reason = 'MAXIMUM_DISPLACEMENT_REACHED'
            break

        segment_index += 1
        next_displacement = min(
            cumulative_displacement + segment_displacement,
            maximum_displacement)
        increment = next_displacement - cumulative_displacement
        segment_time = increment / loading_rate
        next_job_name = '%s_R%02d' % (base_job_name, segment_index)
        next_model_name = 'AutoRestartModel-%02d' % segment_index
        next_step_name = 'Auto-Continue-%02d' % segment_index
        amplitude_name = 'Amp-Auto-%02d' % segment_index

        if next_model_name in mdb.models:
            del mdb.models[next_model_name]
        mdb.Model(next_model_name, mdb.models[previous_model_name])
        restart_model = mdb.models[next_model_name]
        restart_model.setValues(
            restartJob=previous_job_name,
            restartStep=previous_step_name,
            restartIncrement=STEP_END)

        restart_model.ExplicitDynamicsStep(
            name=next_step_name,
            previous=previous_step_name,
            timePeriod=segment_time,
            nlgeom=OFF,
            improvedDtMethod=ON)
        restart_model.steps[next_step_name].setValues(
            massScaling=((
                SEMI_AUTOMATIC, MODEL, AT_BEGINNING, 1.0,
                float(modelData['targetTimeIncrement']), BELOW_MIN,
                0, 0, 0.0, 0.0, 0, None),),
            improvedDtMethod=ON)
        restart_model.steps[next_step_name].Restart(
            numberIntervals=1, overlay=ON, timeMarks=OFF)
        # A displacement BC value in a later step is still the total target
        # displacement.  Start the new amplitude at the previous/next ratio
        # so the prescribed displacement is continuous at the restart point.
        amplitude_start = (
            cumulative_displacement / next_displacement)
        restart_model.SmoothStepAmplitude(
            name=amplitude_name,
            timeSpan=STEP,
            data=((0.0, amplitude_start), (segment_time, 1.0)))
        restart_model.boundaryConditions['BC-Right'].setValuesInStep(
            stepName=next_step_name,
            u1=(-next_displacement if int(modelData['pressBC'])
                else next_displacement),
            amplitude=amplitude_name)

        state['status'] = 'RUNNING_RESTART_%02d' % segment_index
        state['currentTargetDisplacement_mm'] = next_displacement
        _write_json(status_json, state)

        restart_job = _create_job(
            next_job_name, next_model_name, RESTART,
            subroutine_file, cpus)
        _write_json(
            os.path.join(
                job_directory, next_job_name + '_ModelData.json'),
            _metadata(next_job_name, next_displacement, segment_index))
        odb_path, extracted = _submit_and_extract(
            restart_job, job_directory)
        segment_results.append(extracted)
        job_names.append(next_job_name)
        odb_paths.append(odb_path)

        combined = resultCore.combine_segments(segment_results)
        curve_evaluation = resultCore.evaluate_curve(
            combined['curve'], drop_ratio, minimum_post_peak_frames)
        state['segments'].append({
            'index': segment_index,
            'jobName': next_job_name,
            'odb': odb_path,
            'targetDisplacement_mm': next_displacement,
            'peakForce_N': curve_evaluation['peak_force'],
            'finalForce_N': curve_evaluation['final_force'],
            'postPeakDrop': curve_evaluation['post_peak_drop'],
        })
        _write_json(status_json, state)

        cumulative_displacement = next_displacement
        previous_job_name = next_job_name
        previous_model_name = next_model_name
        previous_step_name = next_step_name

    if curve_evaluation['post_peak_drop']:
        finished_reason = 'RESIDUAL_STRENGTH_DEMONSTRATED'

    metadata = _metadata(
        base_job_name, cumulative_displacement, len(segment_results) - 1)
    metadata['jobName'] = base_job_name
    metadata['autoSolveJobNames'] = job_names
    metadata['autoSolveOdbFiles'] = odb_paths
    result = resultCore.write_report(
        report_base,
        resultCore.combine_segments(segment_results),
        metadata,
        drop_ratio,
        minimum_post_peak_frames)

    state['status'] = 'COMPLETED'
    state['finishedReason'] = finished_reason
    state['finalTargetDisplacement_mm'] = cumulative_displacement
    state['reportBase'] = report_base
    state['resultJSON'] = report_base + '_Result.json'
    state['validStrength'] = bool(result.get('validStrength', False))
    state['peakForce_N'] = result.get('peakForce_N')
    state['peakDisplacement_mm'] = result.get('peakDisplacement_mm')
    state['residualStrength_MPa'] = result.get(
        'maximumNominalStress_MPa')
    state['warnings'] = result.get('warnings', [])
    _write_json(status_json, state)

    lines = [
        'Composite repair automatic residual-strength solve',
        'Status: COMPLETED',
        'Finished reason: ' + str(finished_reason),
        'Segments: %d' % len(segment_results),
        'Final target displacement (mm): %.9g' %
        cumulative_displacement,
        'Peak force (N): %.9g' % result['peakForce_N'],
        'Peak displacement (mm): %.9g' %
        result['peakDisplacement_mm'],
        'Residual strength (MPa): %s' %
        ('unavailable' if result['maximumNominalStress_MPa'] is None
         else '%.9g' % result['maximumNominalStress_MPa']),
        'Valid residual strength: %s' % result['validStrength'],
        'Result JSON: ' + report_base + '_Result.json',
        'Force-displacement CSV: ' +
        report_base + '_ForceDisplacement.csv',
        'Energy CSV: ' + report_base + '_Energy.csv',
    ]
    for warning in result.get('warnings', []):
        lines.append('WARNING: ' + warning)
    _write_status(status_txt, lines)
    globals()['lastResult'] = result
    globals()['autoSolveStatus'] = state

except Exception:
    state['status'] = 'FAILED'
    state['error'] = traceback.format_exc()
    _write_json(status_json, state)
    _write_status(status_txt, [
        'Composite repair automatic residual-strength solve',
        'Status: FAILED',
        state['error'],
    ])
    raise
