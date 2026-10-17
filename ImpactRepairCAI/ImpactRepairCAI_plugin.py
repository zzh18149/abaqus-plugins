# -*- coding: utf-8 -*-
"""Distinct registration/module names allow coexistence with the legacy plugin."""
import os
import sys
from abaqusGui import AFXMode, getAFXApp
from abaqusConstants import ALL
_folder = os.path.dirname(os.path.abspath(__file__))
if _folder not in sys.path:
    sys.path.insert(0, _folder)
from cai_gui import ImpactRepairForm
_toolset = getAFXApp().getAFXMainWindow().getPluginToolset()
_toolset.registerGuiMenuButton(
    buttonText='Impact Repair CAI 2024', object=ImpactRepairForm(_toolset),
    messageId=AFXMode.ID_ACTIVATE, kernelInitString='import sys; sys.path.insert(0, %r); import cai_kernel' % _folder,
    applicableModules=ALL, version='0.4.0', author='Impact Repair CAI',
    description='Impact state import, planar bonded repair and compression after impact',
    helpUrl=os.path.join(_folder, 'README.md'))
