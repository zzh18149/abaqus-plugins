#-*- coding: utf-8 -*-
######################
import os
import json

modelData = globals()["modelData"]
jobName = modelData['jobName']
cpus = modelData['numOfCpus']
subroutineFile = modelData['mSubroutineFileKw']
if not subroutineFile or not os.path.isfile(subroutineFile):
    raise ValueError("VUMAT file does not exist: %s" % subroutineFile)

jobDirectory = os.path.join(modelData["pluginDir"], "jobs")
if not os.path.isdir(jobDirectory):
    os.makedirs(jobDirectory)
os.chdir(jobDirectory)

metadata = {
    'schemaVersion': 3,
    'jobName': jobName,
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
    'adhesiveModel': modelData['modify'].get(
        'adhesiveModel', 'cohesive-or-perfect-bond'),
    'patchProtrusion_mm': float(
        modelData['modify'].get('patchProtrusion', 0.0)),
    'loadingDisplacement_mm': float(modelData['disValue']),
    'stepTime_s': float(modelData['stepTime']),
    'targetTimeIncrement_s': float(
        modelData['targetTimeIncrement']),
    'meshLevel': int(modelData['meshLevel']),
    'peakDropRatio': float(modelData['peakDropRatio']),
    'minimumPostPeakFrames': int(
        modelData.get('minimumPostPeakFrames', 5)),
    'autoSolve': False,
}
metadataPath = os.path.join(
    jobDirectory, jobName + '_ModelData.json')
with open(metadataPath, 'w') as metadataFile:
    json.dump(metadata, metadataFile, indent=2, sort_keys=True)

lockFile = os.path.join(jobDirectory, jobName + '.lck')
if os.path.isfile(lockFile):
    raise ValueError(
        "Job '%s' is locked. It may already be running or may have stopped "
        "abnormally. Do not submit the same job twice. Use a new Job name, "
        "or confirm that no solver is running before archiving the .lck file."
        % jobName)

if jobName in mdb.jobs:
    existingStatus = str(mdb.jobs[jobName].status).upper()
    if existingStatus in ('SUBMITTED', 'RUNNING', 'CHECK_RUNNING'):
        raise ValueError(
            "Job '%s' is already %s; duplicate submission was blocked."
            % (jobName, existingStatus))
    del mdb.jobs[jobName]
mdb.Job(name=jobName, model='Model-1', description='', type=ANALYSIS,
    atTime=None, waitMinutes=0, waitHours=0, queue=None, memory=90,
    memoryUnits=PERCENTAGE, explicitPrecision=DOUBLE_PLUS_PACK,
    nodalOutputPrecision=SINGLE, echoPrint=OFF, modelPrint=OFF,
    contactPrint=OFF, historyPrint=OFF, userSubroutine=subroutineFile, scratch='',
    resultsFormat=ODB, parallelizationMethodExplicit=DOMAIN, numDomains=cpus,
    activateLoadBalancing=False,
    multiprocessingMode=DEFAULT, numCpus=cpus)
if modelData.get("writeInputOnly", False):
    mdb.jobs[jobName].writeInput(consistencyChecking=OFF)
else:
    mdb.jobs[jobName].submit(consistencyChecking=OFF)
