#-*- coding: utf-8 -*-
# Abaqus/CAE GUI registration
from abaqusGui import *
from abaqusConstants import ALL
import os
from testForm import TestForm
 
thisPath = os.path.abspath(__file__)
thisDir = os.path.dirname(thisPath)

toolset = getAFXApp().getAFXMainWindow().getPluginToolset()
toolset.registerGuiMenuButton(
                              buttonText='Composite Repair Strength Analysis V2.2.0',
                              object=TestForm(toolset),
                              messageId=AFXMode.ID_ACTIVATE,
                              icon=None,
                              kernelInitString='import RSGen_Master',
                              applicableModules=ALL,
                              version='2.2.0',
                              author='Composite Repair Team',
                              description='Parametric repair modelling, automatic restart solve and result report',
                              helpUrl='N/A'
                              )
