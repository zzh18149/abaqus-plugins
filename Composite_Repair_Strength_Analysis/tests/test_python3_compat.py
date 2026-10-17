# -*- coding: utf-8 -*-
"""Python 3 regressions; no CAE GUI/license required.

GUI methods are loaded from their actual AST so their I/O can be exercised
without replacing the native abaqusGui module with a permissive GUI stub.
"""
import ast
import csv
import importlib.util
import json
import locale
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_function(path, name, namespace, class_name=None):
    tree = ast.parse(path.read_bytes(), filename=str(path))
    body = tree.body
    if class_name:
        body = next(node for node in body if isinstance(node, ast.ClassDef)
                    and node.name == class_name).body
    node = next(node for node in body if isinstance(node, ast.FunctionDef)
                and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class Python3Compatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            'result_core_test', ROOT / 'scripts/resultCore.py')
        cls.core = importlib.util.module_from_spec(spec)
        odb_stub = types.ModuleType('odbAccess')
        odb_stub.openOdb = lambda **kwargs: None
        with patch.dict(sys.modules, {'odbAccess': odb_stub}):
            spec.loader.exec_module(cls.core)

    def test_native_paths_are_text(self):
        value = str(ROOT / '中文 空格' / '结果.odb')
        for candidate in (value, Path(value), os.fsencode(value)):
            self.assertEqual(self.core._abaqus_api_path(candidate), value)
            self.assertIsInstance(self.core._abaqus_api_path(candidate), str)

    def test_gui_chinese_text(self):
        ns = {'os': os, 'locale': locale}
        fn = load_function(ROOT / 'testDB.py', 'TEXT', ns)
        for value in ('中文测试', '中文测试'.encode('utf-8')):
            self.assertEqual(fn(value), '中文测试')
            self.assertIsInstance(fn(value), str)

    def test_gui_summary_csv_round_trip(self):
        ns = {'os': os, 'csv': csv, 'locale': locale}
        load_function(ROOT / 'testDB.py', 'TEXT', ns)
        export = load_function(ROOT / 'testDB.py', 'omCmdExportResultSummary',
                               ns, 'TestDB')
        with tempfile.TemporaryDirectory() as folder:
            messages = []
            record = {'JobName': 'case_1', 'ODB': '中文 空格/结果.odb',
                      'ResultJSON': '中文,逗号.json'}
            dialog = types.SimpleNamespace(resultRecords=[record],
                lastResultDirectory=folder,
                form=types.SimpleNamespace(showMessage=messages.append))
            export(dialog, None, None, None)
            path = Path(folder) / 'CompositeRepair_Result_Summary.csv'
            self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
            with path.open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['ODB'], record['ODB'])
            self.assertEqual(rows[0]['ResultJSON'], record['ResultJSON'])
            self.assertIn(str(path), messages[0])

    def test_kernel_scripts_share_namespace_and_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            scripts = Path(folder) / 'scripts'
            scripts.mkdir()
            (scripts / 'one.py').write_text(
                '# coding: utf-8\nanswer = 41\nlabel = "中文"\n', encoding='utf-8')
            (scripts / 'two.py').write_text('answer += 1\n', encoding='utf-8')
            ns = {'os': os, 'modelData': {'pluginDir': folder}}
            run = load_function(ROOT / 'RSGen_Master.py', '_run_script', ns)
            run('one.py')
            run('two.py')
            self.assertEqual(ns['answer'], 42)
            self.assertEqual(ns['label'], '中文')

    def test_all_report_files_with_chinese_paths(self):
        curve = [dict(time=i * .01, displacement=i * .01, force_abs=force,
                      right_node_count=4, equilibrium_ratio=0.,
                      odb='中文/结果.odb', step='Step-1', frame_index=i)
                 for i, force in enumerate([0, 10, 30, 60, 100, 90, 70, 50, 40, 30, 20, 10])]
        combined = dict(curve=curve, energies=[], damage_maximum={},
                        odb_paths=['中文/结果.odb'])
        with tempfile.TemporaryDirectory() as folder:
            base = str(Path(folder) / '中文结果')
            result = self.core.write_report(base, combined,
                dict(plateWidth_mm=10., plateTotalThickness_mm=2., jobName='test'))
            self.assertFalse(result['validStrength'])
            for suffix in ('_ForceDisplacement.csv', '_Energy.csv', '_DamageSummary.csv'):
                with open(base + suffix, encoding='utf-8', newline='') as handle:
                    self.assertTrue(list(csv.reader(handle)))
            self.assertIn('中文/结果.odb', Path(base + '_Result.txt').read_text(encoding='utf-8'))
            with open(base + '_Result.json', encoding='utf-8') as handle:
                self.assertEqual(json.load(handle)['odbFiles'], ['中文/结果.odb'])


if __name__ == '__main__':
    unittest.main()
