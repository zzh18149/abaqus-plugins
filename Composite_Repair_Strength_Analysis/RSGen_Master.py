# -*- coding: utf-8 -*-
"""Kernel entry point for the Composite Repair Strength Analysis plug-in.

The plug-in targets Abaqus/CAE 2024 and its embedded Python 3.10.
"""

import json
import os
import re

from abaqus import *
from abaqusConstants import *
from caeModules import *
from driverUtils import executeOnCaeStartup


executeOnCaeStartup()
if 'Viewport: 1' not in session.viewports:
    session.Viewport(name='Viewport: 1')
session.viewports['Viewport: 1'].makeCurrent()
session.viewports['Viewport: 1'].maximize()


def _require_positive(name, value):
    if float(value) <= 0.0:
        raise ValueError('%s must be greater than zero' % name)


def _angles(value, name):
    text = str(value).strip()
    if not text:
        raise ValueError('%s cannot be empty' % name)
    values = [item.strip() for item in text.split('/') if item.strip()]
    try:
        return [float(item) for item in values]
    except Exception:
        raise ValueError('%s must be slash-separated numbers' % name)


def _validate_material(material_data):
    if not isinstance(material_data, dict):
        raise ValueError('Material JSON root must be an object')
    material = material_data.get('material')
    if not isinstance(material, dict):
        raise ValueError('Material JSON must contain a material object')

    for material_name in ('base', 'adhesive'):
        if material_name not in material:
            raise ValueError(
                'Material JSON is missing material/%s' % material_name)

    base = material['base']
    for name in ('density', 'data', 'depvar'):
        if name not in base:
            raise ValueError(
                'Material JSON is missing material/base/%s' % name)
    if len(base['data']) < 37:
        raise ValueError(
            'material/base/data must contain at least 37 VUMAT constants')
    if int(base['depvar']) < 63:
        raise ValueError('material/base/depvar must be at least 63')

    adhesive = material['adhesive']
    for name in ('density', 'elastic', 'qd', 'power', 'de'):
        if name not in adhesive:
            raise ValueError(
                'Material JSON is missing material/adhesive/%s' % name)
    for name in ('elastic', 'qd', 'de'):
        if len(adhesive[name]) != 3:
            raise ValueError(
                'material/adhesive/%s must contain exactly 3 values' % name)


def _derived_repair_angles(
        base_angles, repair_count, text, repair_type):
    """Return repair angles in each repair part's local bottom-to-top order.

    For the double-sided patch, ``repair_count`` is the total number of plies
    on both sides.  AUTO mirrors the surface-adjacent parent plies outward:

    * first half: bottom patch, local bottom surface to bonded top surface;
    * second half: top patch, bonded bottom surface to local top surface.
    """
    value = str(text).strip().upper()
    if value in ('', 'AUTO', 'SAME', '同原板'):
        if int(repair_type) == 0:
            if repair_count % 2 != 0:
                raise ValueError(
                    'Double-sided patch total ply count must be even')
            per_side = repair_count // 2
            if per_side > len(base_angles):
                raise ValueError(
                    'Patch plies per side cannot exceed parent ply count')
            bottom_angles = list(reversed(base_angles[:per_side]))
            top_angles = list(reversed(base_angles[-per_side:]))
            return bottom_angles + top_angles
        return list(base_angles[-repair_count:])
    repair_angles = _angles(text, 'repair layer angles')
    if len(repair_angles) != repair_count:
        raise ValueError(
            'Repair layer count does not match the number of repair angles')
    return repair_angles


def _run_script(filename):
    """Execute a kernel stage in the shared namespace, as before migration."""
    path = os.path.join(modelData['pluginDir'], 'scripts', filename)
    with open(path, 'rb') as source:
        code = compile(source.read(), path, 'exec')
    exec(code, globals())


def _build_model():
    _run_script('buildParametricModel.py')


def _apply_bc():
    _run_script('applyBC.py')


def _submit_job():
    _run_script('submitJob.py')


def _parse_odb():
    _run_script('parseOdb.py')


def _auto_solve():
    _run_script('autoSolve.py')


def submitJob():
    """Backward-compatible helper used by existing automation scripts."""
    return _submit_job()


def parseODB():
    """Backward-compatible helper used by legacy GUI commands."""
    return _parse_odb()


def execute(pluginDir='', cmdType='createModel',
            mLength=150.0, mWidth=50.0, mHeight=2.3,
            mThickness=0.0, mNumLayer=18,
            mLayerAngle='0/90/0/90/0/90/0/90/0/0/90/0/90/0/90/0/90/0',
            mPitDiameter=10.0, mMaterialFileKw='', mOdbFileKw='',
            modifyType=1, tbWidth=29.3, tbHeight=29.3,
            tbLayerNum=14, tbLayerAngle='AUTO', glueThickness=0.15,
            jtNum=6, jtStepWidth=1.6083333333,
            repairOuterDiameter=29.3, xjAngle=10.0,
            lrGap=5.0, tbGap=0.0, disValue=0.5,
            jobName='Job-1', numOfCpus=8, mSubroutineFileKw='',
            stepTime=0.0025, targetTimeIncrement=4.0e-9,
            parseOdbType=1, tableKw=(), matParaDict='{}',
            tbType=0, tbShape=0, pressBC=0, meshLevel=0,
            fieldIntervals=150, historyIntervals=500,
            peakDropRatio=0.15, autoSolve=1,
            autoIncrementDisplacement=0.15,
            autoMaximumDisplacement=1.2,
            minimumPostPeakFrames=5):
    """Create, update, submit or post-process one parametric repair model."""

    base_angles = _angles(mLayerAngle, 'base layer angles')
    base_count = int(mNumLayer)
    repair_count = int(tbLayerNum)
    repair_type = int(modifyType)

    if base_count != len(base_angles):
        raise ValueError(
            'Base layer count does not match the number of layer angles')
    if base_count < 2:
        raise ValueError('Base laminate must contain at least two layers')
    if repair_count < 1:
        raise ValueError('Repair laminate must contain at least one layer')
    patch_count_per_side = None
    if repair_type == 0:
        if repair_count < 2 or repair_count % 2 != 0:
            raise ValueError(
                'Double-sided patch total ply count must be a positive '
                'even number')
        patch_count_per_side = repair_count // 2
        if patch_count_per_side > base_count:
            raise ValueError(
                'Patch plies per side cannot exceed parent ply count')
    if repair_type in (1, 2) and repair_count >= base_count:
        raise ValueError(
            'Staircase/scarf repair must leave at least one original ply')

    for name, value in (
            ('length', mLength), ('width', mWidth),
            ('total laminate thickness', mHeight),
            ('damage diameter', mPitDiameter),
            ('adhesive thickness', glueThickness),
            ('CPU count', numOfCpus), ('step time', stepTime),
            ('target time increment', targetTimeIncrement),
            ('loading displacement', disValue),
            ('automatic continuation increment',
             autoIncrementDisplacement),
            ('automatic maximum displacement',
             autoMaximumDisplacement)):
        _require_positive(name, value)

    if float(mPitDiameter) >= min(float(mLength), float(mWidth)):
        raise ValueError('Damage diameter must be smaller than the plate')
    if int(jtNum) < 1:
        raise ValueError('Staircase level count must be at least one')
    if not 0.0 < float(xjAngle) < 85.0:
        raise ValueError('Scarf angle must be between 0 and 85 degrees')
    if int(meshLevel) not in (0, 1, 2):
        raise ValueError('Mesh level must be 0 (fast), 1 (standard) or 2 (fine)')
    if not 0.0 < float(peakDropRatio) < 1.0:
        raise ValueError('Peak-drop ratio must be between zero and one')
    if int(autoSolve) not in (0, 1):
        raise ValueError('autoSolve must be zero or one')
    if int(minimumPostPeakFrames) < 3:
        raise ValueError(
            'Minimum post-peak frame count must be at least three')
    if (int(autoSolve) and
            float(autoMaximumDisplacement) < abs(float(disValue))):
        raise ValueError(
            'Automatic maximum displacement must not be smaller than the '
            'initial displacement')
    if not re.match(r'^[A-Za-z][A-Za-z0-9_-]*$', str(jobName)):
        raise ValueError(
            'Job name must start with a letter and contain only letters, '
            'digits, underscores or hyphens')

    outer_diameter = float(repairOuterDiameter)
    if repair_type == 0:
        outer_diameter = float(tbWidth)
    if repair_type in (0, 1):
        repair_name = (
            'patch diameter' if repair_type == 0
            else 'staircase outer diameter')
        _require_positive(repair_name, outer_diameter)
        if outer_diameter <= float(mPitDiameter):
            raise ValueError(
                '%s must exceed damage diameter' % repair_name.capitalize())
    if outer_diameter >= min(float(mLength), float(mWidth)):
        raise ValueError('Repair outer diameter must be smaller than the plate')

    material_data = json.loads(matParaDict)
    if cmdType in (
            'createModel', 'createGeometry', 'meshModel',
            'updateModel', 'updateMaterial'):
        _validate_material(material_data)

    repair_angles = _derived_repair_angles(
        base_angles, repair_count, tbLayerAngle, repair_type)
    ply_thickness = float(mHeight) / float(base_count)
    repair_depth = ply_thickness * repair_count
    patch_depth_per_side = None
    patch_bottom_angles = []
    patch_top_angles = []
    if repair_type == 0:
        patch_depth_per_side = (
            ply_thickness * float(patch_count_per_side))
        patch_bottom_angles = list(
            repair_angles[:patch_count_per_side])
        patch_top_angles = list(
            repair_angles[patch_count_per_side:])
    stair_width = None
    if repair_type == 1:
        stair_width = (
            outer_diameter - float(mPitDiameter)) / (2.0 * int(jtNum))

    global modelData
    modelData = {
        'pluginDir': os.path.abspath(pluginDir),
        'jobName': str(jobName),
        'length': float(mLength),
        'height': float(mWidth),
        'depth': float(mHeight),
        'totalDepth': float(mHeight),
        'plyThickness': ply_thickness,
        'nlayers': base_count,
        'layers': base_angles,
        'r': float(mPitDiameter) / 2.0,
        'damageDiameter': float(mPitDiameter),
        'numOfCpus': int(numOfCpus),
        'mSubroutineFileKw': os.path.abspath(mSubroutineFileKw),
        'mOdbFileKw': mOdbFileKw,
        'parseOdbType': int(parseOdbType),
        'disValue': abs(float(disValue)),
        'pressBC': int(pressBC),
        'stepTime': float(stepTime),
        'targetTimeIncrement': float(targetTimeIncrement),
        'gripLength': float(lrGap),
        'meshLevel': int(meshLevel),
        'fieldIntervals': int(fieldIntervals),
        'historyIntervals': int(historyIntervals),
        'peakDropRatio': float(peakDropRatio),
        'autoSolve': int(autoSolve),
        'autoIncrementDisplacement': float(
            autoIncrementDisplacement),
        'autoMaximumDisplacement': float(
            autoMaximumDisplacement),
        'minimumPostPeakFrames': int(minimumPostPeakFrames),
        'buildStage': (
            'geometry' if cmdType == 'createGeometry'
            else 'mesh' if cmdType == 'meshModel'
            else 'full'),
        # No artificial inter-ply adhesive is inserted between laminate
        # plies.  Staircase and double-sided patch modes use
        # modify/cohesive as the finite solid adhesive thickness. Staircase,
        # double-sided patch and true scarf modes all use finite solid adhesive
        # parts with tied interfaces in the current validated baseline.
        'cohesive': 0.0,
        'modify': {
            'type': repair_type,
            'tbType': int(tbType),
            'tbShape': int(tbShape),
            'width': float(tbWidth),
            'height': float(tbHeight),
            'n': repair_count,
            'layers': repair_angles,
            'nPerSide': patch_count_per_side,
            'layersBottom': patch_bottom_angles,
            'layersTop': patch_top_angles,
            'repairDepthPerSide': patch_depth_per_side,
            'patchConfiguration': (
                'double-sided-through-hole'
                if repair_type == 0 else None),
            'cohesive': float(glueThickness),
            'jtNum': int(jtNum),
            'stepWidth': stair_width,
            'outerDiameter': outer_diameter,
            'repairDepth': repair_depth,
            'xjAngle': float(xjAngle),
        },
    }
    modelData.update(material_data)

    if cmdType in ('createModel', 'updateModel', 'updateMaterial'):
        Mdb()
        _build_model()
    elif cmdType == 'createGeometry':
        if repair_type != 2:
            raise ValueError(
                'Separated geometry creation is currently provided for '
                'the true smooth scarf model only')
        Mdb()
        _build_model()
    elif cmdType == 'meshModel':
        if repair_type != 2:
            raise ValueError(
                'Separated meshing is currently provided for the true '
                'smooth scarf model only')
        if 'Model-1' not in mdb.models:
            raise ValueError(
                'Model-1 does not exist. Create the scarf geometry first '
                'in the same Abaqus/CAE session.')
        _build_model()
    elif cmdType in ('updateGeometry', 'updateBC', 'applyBC',
                     'applyBCBtDis'):
        _apply_bc()
    elif cmdType == 'submitJob':
        # Always synchronize current GUI loading/analysis values.
        _apply_bc()
        _submit_job()
    elif cmdType == 'autoSolve':
        # The initial and restart segments must share one definition.
        _apply_bc()
        _auto_solve()
    elif cmdType in ('parseODB', 'postProcess'):
        _parse_odb()
    else:
        raise ValueError('Unknown plug-in command: %s' % cmdType)
    return
