# -*- coding: utf-8 -*-
"""Abaqus 2024 / Python 3.10 configuration, independent of CAE."""
from __future__ import division
import copy
import json
import locale
import math
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))


def api_path(value):
    return native_text(os.fsdecode(value))


def native_text(value):
    """Prepare Unicode for Windows Abaqus 2024 native string wrappers."""
    value = value.decode('utf-8') if isinstance(value, bytes) else str(value)
    if os.name == 'nt' and not value.isascii():
        # LC_NUMERIC remains unchanged: no decimal separator side effects.
        locale.setlocale(locale.LC_CTYPE, '.UTF8')
    return value


DEFAULTS = {
    'schema_version': 1,
    'source_inp': r'F:\FEM\Impact\temp\35j_test.inp',
    'source_odb': r'F:\FEM\Impact\temp\35j_test.odb',
    'source_instance': 'PLATE-1', 'state_selection': 'auto', 'source_step': 1,
    'source_interval': 5, 'source_time': 0.005,
    'vumat': r'F:\FEM\Impact\HouhashinDel_fixed(1).for',
    'output_dir': '', 'job_name': 'CAI_Repair_01',
    'shape': 'circle', 'sides': 'both', 'analysis_mode': 1,
    'corner_radius': 0.0,
    'bond_void_policy': 'reject',
    'size_x': 40.0, 'size_y': 40.0,
    'center_x': 0.0, 'center_y': 0.0, 'rotation': 0.0,
    'ply_count': 8, 'angles': '45/0/-45/90/90/-45/0/45',
    'ply_thickness': 0.14375, 'mesh_size': 2.0,
    'interply_thickness': 0.00001,
    'adhesive_min_thickness': 0.12,
    'adhesive_E': 2200.0, 'adhesive_G': 815.0,
    'adhesive_tn': 31.9, 'adhesive_ts': 21.2,
    'adhesive_GIc': 0.48, 'adhesive_GIIc': 1.83,
    'adhesive_BK': 1.5, 'adhesive_density': 1.2e-9,
    'material_status': 'literature_reference_not_calibrated',
    'base_material': 'D_ZERO00', 'interply_material': 'D_COHESIVE',
    'load_axis': 0, 'nominal_width': 100.0, 'nominal_thickness': 4.6,
    'end_support_width': 12.5, 'side_support_width': 5.0,
    'relax_time': 0.002, 'compression_time': 0.1,
    'displacement': 2.0, 'cpus': 16,
    'field_intervals': 200, 'history_intervals': 1000,
    'peak_drop': 0.15, 'post_peak_points': 5,
    'ke_ie_limit': 0.05, 'ae_ie_limit': 0.05,
    'force_balance_limit': 0.05,
    'fixture_status': 'D7137_inspired_equivalent_not_certified',
    'notes': 'Flat patch; variable-thickness cohesive film fills residual dent.'
}


def load(path=None, overrides=None):
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, 'rb') as handle:
            data = json.loads(handle.read().decode('utf-8-sig'))
        if data.get('schema_version', 1) != 1:
            raise ValueError('Unsupported configuration schema')
        data.pop('source_equilibrated',None)  # removed in v0.3; accept old JSON files
        unknown = set(data) - set(DEFAULTS)
        if unknown:
            raise ValueError('Unknown settings: ' + ', '.join(sorted(unknown)))
        cfg.update(data)
        if 'state_selection' not in data and any(k in data for k in ('source_step','source_interval','source_time')):
            cfg['state_selection']='manual'
    if overrides:
        overrides=dict(overrides)
        overrides.pop('source_equilibrated',None)
        unknown = set(overrides) - set(DEFAULTS)
        if unknown:
            raise ValueError('Unknown settings: ' + ', '.join(sorted(unknown)))
        cfg.update(overrides)
        if 'state_selection' not in overrides and any(k in overrides for k in ('source_step','source_interval','source_time')):
            cfg['state_selection']='manual'
    if not cfg['output_dir']:
        cfg['output_dir'] = os.path.join(r'F:\FEM\CAI_Runs', cfg['job_name'])
    return validate(cfg)


def angles(value):
    if isinstance(value, (list, tuple)):
        result = [float(x) for x in value]
    else:
        result = [float(x) for x in re.split(r'[/,;\s]+', value.strip()) if x]
    if not result or any(math.isnan(x) or math.isinf(x) for x in result):
        raise ValueError('Ply angles must be finite numbers separated by / or commas')
    return result


def validate(cfg):
    cfg = copy.deepcopy(cfg)
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]{0,59}$', cfg['job_name']):
        raise ValueError('Job name: ASCII letter followed by letters, digits or underscores')
    if cfg['job_name'].upper().startswith('CAIR_IMPACT'):
        raise ValueError('CAIR_IMPACT is reserved for the staged source library')
    for key in ('source_inp', 'source_odb', 'vumat'):
        if not cfg[key]:
            raise ValueError('Missing ' + key)
        cfg[key] = os.path.abspath(cfg[key])
    cfg['output_dir'] = os.path.abspath(cfg['output_dir'])
    if os.path.normcase(os.path.dirname(cfg['source_odb'])) == os.path.normcase(cfg['output_dir']):
        raise ValueError('Use a separate output directory to protect the impact job')
    positive = ('size_x', 'size_y', 'ply_thickness', 'mesh_size',
                'interply_thickness', 'adhesive_min_thickness', 'adhesive_E',
                'adhesive_G', 'adhesive_tn', 'adhesive_ts', 'adhesive_GIc',
                'adhesive_GIIc', 'adhesive_BK', 'adhesive_density',
                'nominal_width', 'nominal_thickness', 'relax_time',
                'compression_time', 'displacement', 'ke_ie_limit',
                'ae_ie_limit', 'force_balance_limit')
    for key in positive:
        value = float(cfg[key])
        if math.isnan(value) or math.isinf(value) or value <= 0:
            raise ValueError(key + ' must be finite and positive')
        cfg[key] = value
    for key in ('center_x', 'center_y', 'rotation', 'source_time',
                'end_support_width', 'side_support_width', 'corner_radius'):
        cfg[key] = float(cfg[key])
        if math.isnan(cfg[key]) or math.isinf(cfg[key]):
            raise ValueError(key + ' must be finite')
    for key in ('source_step', 'source_interval', 'ply_count', 'cpus',
                'field_intervals', 'history_intervals', 'post_peak_points', 'load_axis'):
        v = int(cfg[key])
        if float(cfg[key]) != v or v < (0 if key == 'load_axis' else 1):
            raise ValueError(key + ' must be an integer in its valid range')
        cfg[key] = v
    if cfg['analysis_mode'] not in (0,1):
        raise ValueError('analysis_mode must be 0 (impact CAI) or 1 (repaired CAI)')
    if cfg['corner_radius']<0 or (cfg['analysis_mode']==1 and cfg['shape']=='rectangle' and cfg['corner_radius']>min(cfg['size_x'],cfg['size_y'])/2.):
        raise ValueError('Rectangle corner radius must be between zero and half the shorter side')
    if cfg['load_axis'] not in (0, 1):
        raise ValueError('load_axis must be 0 (X) or 1 (Y)')
    if cfg['state_selection'] not in ('auto','manual'):
        raise ValueError('state_selection must be auto or manual')
    if cfg['shape'] not in ('circle', 'rectangle', 'ellipse'):
        raise ValueError('shape must be circle, rectangle or ellipse')
    if cfg['sides'] not in ('top', 'bottom', 'both', 'none'):
        raise ValueError('sides must be top, bottom, both or none')
    if cfg['bond_void_policy'] not in ('reject','bridge'):
        raise ValueError('bond_void_policy must be reject or bridge')
    if cfg['analysis_mode']==1 and cfg['sides']=='none':
        cfg['analysis_mode']=0  # legacy unpatched configuration
    if cfg['analysis_mode']==1 and len(angles(cfg['angles'])) != cfg['ply_count']:
        raise ValueError('Ply count must equal the number of angles; count is PER SIDE')
    cfg['peak_drop']=float(cfg['peak_drop'])
    if not 0 < cfg['peak_drop'] < 1:
        raise ValueError('peak_drop must be between 0 and 1')
    if cfg['source_time'] < 0 or min(cfg['end_support_width'], cfg['side_support_width']) < 0:
        raise ValueError('Times and support widths cannot be negative')
    if cfg['field_intervals'] < 10 or cfg['history_intervals'] < 20:
        raise ValueError('Too few output intervals')
    return cfg


def dump(path, obj):
    data = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    with open(path, 'wb') as handle:
        handle.write(data.encode('utf-8'))
