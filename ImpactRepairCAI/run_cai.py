# -*- coding: utf-8 -*-
"""abaqus cae noGUI=run_cai.py -- settings.json build|inspect|datacheck|submit|results"""
from __future__ import print_function
import os
import sys

# The Abaqus noGUI script runner does not always supply __file__.
script_path=globals().get('__file__')
if not script_path:
    candidates=[x.split('=',1)[-1] for x in sys.argv if 'run_cai.py' in x]
    script_path=candidates[0] if candidates else os.path.join(os.getcwd(),'run_cai.py')
sys.path.insert(0,os.path.dirname(os.path.abspath(script_path)))
from cai_kernel import execute
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[-2:]
if len(args)!=2:
    raise ValueError('Usage: abaqus cae noGUI=run_cai.py -- settings.json ACTION')
execute(config_path=os.path.abspath(args[0]),action=args[1])
