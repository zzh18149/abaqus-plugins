# -*- coding: utf-8 -*-
"""Update the existing model with the latest GUI loading/analysis settings."""

from abaqusConstants import (
    AT_BEGINNING, BELOW_MIN, MODEL, ON, SEMI_AUTOMATIC)

modelData = globals()["modelData"]

if "Model-1" not in mdb.models:
    raise ValueError(
        "Model-1 does not exist. Create/mesh the model before updating "
        "boundary conditions and analysis settings.")

model = mdb.models["Model-1"]

if "Step-1" not in model.steps:
    raise ValueError(
        "Step-1 does not exist. Complete model/mesh creation first.")
if "BC-Right" not in model.boundaryConditions:
    raise ValueError(
        "BC-Right does not exist. Complete model/mesh creation first.")
if "Amp-Loading" not in model.amplitudes:
    raise ValueError(
        "Amp-Loading does not exist. Complete model/mesh creation first.")

stepTime = float(modelData["stepTime"])
targetTimeIncrement = float(modelData["targetTimeIncrement"])
fieldIntervals = max(5, int(modelData.get("fieldIntervals", 150)))
historyIntervals = max(50, int(modelData.get("historyIntervals", 500)))
reducedIntervals = max(5, int(round(fieldIntervals / 3.0)))

if stepTime <= 0.0:
    raise ValueError("Analysis time must be greater than zero.")
if targetTimeIncrement <= 0.0:
    raise ValueError("Target time increment must be greater than zero.")

loadDisplacement = abs(float(modelData["disValue"]))
if int(modelData.get("pressBC", 0)):
    loadDisplacement = -loadDisplacement

model.steps["Step-1"].setValues(
    timePeriod=stepTime,
    massScaling=((
        SEMI_AUTOMATIC, MODEL, AT_BEGINNING, 1.0,
        targetTimeIncrement, BELOW_MIN,
        0, 0, 0.0, 0.0, 0, None),),
    improvedDtMethod=ON)

model.amplitudes["Amp-Loading"].setValues(
    data=((0.0, 0.0), (stepTime, 1.0)))

model.boundaryConditions["BC-Right"].setValuesInStep(
    stepName="Step-1",
    u1=loadDisplacement,
    amplitude="Amp-Loading")

if "F-Output-1" in model.fieldOutputRequests:
    model.fieldOutputRequests["F-Output-1"].setValues(
        numIntervals=fieldIntervals)
if "F-Output-Damage" in model.fieldOutputRequests:
    model.fieldOutputRequests["F-Output-Damage"].setValues(
        numIntervals=reducedIntervals)
if "F-Output-Stress" in model.fieldOutputRequests:
    model.fieldOutputRequests["F-Output-Stress"].setValues(
        numIntervals=reducedIntervals)
if "H-Energy" in model.historyOutputRequests:
    model.historyOutputRequests["H-Energy"].setValues(
        numIntervals=historyIntervals)

print(
    "ANALYSIS_SETTINGS_UPDATED: "
    "U1=%g mm, StepTime=%g s, targetDt=%g s, "
    "fieldIntervals=%d, historyIntervals=%d"
    % (
        loadDisplacement, stepTime, targetTimeIncrement,
        fieldIntervals, historyIntervals))
