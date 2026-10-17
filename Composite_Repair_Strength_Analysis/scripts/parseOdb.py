# -*- coding: utf-8 -*-
"""Generate a direct-end residual-strength report from a selected ODB.

For an ODB belonging to an automatic restart chain, the script detects the
root AutoSolve status file and combines every available segment before writing
the report beside the ODB selected in the GUI.
"""

import json
import os
import sys
from importlib import reload

modelData = globals()['modelData']
scriptsDir = os.path.join(modelData['pluginDir'], 'scripts')
if scriptsDir not in sys.path:
    sys.path.insert(0, scriptsDir)
import resultCore
reload(resultCore)

odbName = modelData.get('mOdbFileKw', '')
if not odbName:
    odbName = os.path.join(
        modelData['pluginDir'], 'jobs', modelData['jobName'] + '.odb')
odbName = os.path.abspath(odbName)
if not os.path.isfile(odbName):
    raise ValueError('ODB file does not exist: %s' % odbName)
if os.path.isfile(os.path.splitext(odbName)[0] + '.lck'):
    raise ValueError(
        'The ODB is still locked by a running analysis. '
        'Wait for completion before generating the report.')

metadata = {
    'jobName': os.path.splitext(os.path.basename(odbName))[0],
    'repairType': int(modelData['modify']['type']),
    'plateWidth_mm': float(modelData['height']),
    'plateTotalThickness_mm': float(modelData['depth']),
}
metadataPath = os.path.splitext(odbName)[0] + '_ModelData.json'
if os.path.isfile(metadataPath):
    with open(metadataPath, 'r') as metadataFile:
        metadata.update(json.load(metadataFile))

odbFiles = [odbName]
rootJobName = metadata.get('rootJobName')
if metadata.get('autoSolve') and rootJobName:
    statusPath = os.path.join(
        os.path.dirname(odbName),
        str(rootJobName) + '_AutoSolve_Status.json')
    if os.path.isfile(statusPath):
        with open(statusPath, 'r') as statusFile:
            status = json.load(statusFile)
        chain = []
        for segment in status.get('segments', []):
            path = os.path.abspath(segment.get('odb', ''))
            if path and os.path.isfile(path):
                chain.append(path)
        if chain:
            odbFiles = chain
            metadata['jobName'] = str(rootJobName)

segments = [resultCore.extract_odb(path) for path in odbFiles]
combined = resultCore.combine_segments(segments)
outputBase = os.path.splitext(odbName)[0]
result = resultCore.write_report(
    outputBase,
    combined,
    metadata,
    float(metadata.get(
        'peakDropRatio', modelData.get('peakDropRatio', 0.15))),
    int(metadata.get(
        'minimumPostPeakFrames',
        modelData.get('minimumPostPeakFrames', 5))))

globals()['lastResult'] = result
