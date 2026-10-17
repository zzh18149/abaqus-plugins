# -*- coding: utf-8 -*-
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cai_config import api_path, dump, load
from cai_source import validate_source_version


class Python3Compatibility(unittest.TestCase):
    def test_api_paths_preserve_chinese(self):
        value = str(Path.cwd() / '中文 空格' / 'source.odb')
        for candidate in (value, Path(value), os.fsencode(value)):
            self.assertEqual(api_path(candidate), value)
            self.assertIsInstance(api_path(candidate), str)

    def test_config_utf8_round_trip(self):
        cfg = load(overrides={'notes': '中文配置', 'output_dir': str(Path.cwd() / '中文目录')})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '配置.json'
            dump(path, cfg)
            self.assertEqual(load(path), cfg)

    def test_source_release_2024(self):
        for version in ('2024', 'Abaqus/Explicit 2024', '2024.HF2'):
            validate_source_version(version)

    def test_old_or_unknown_source_release_rejected(self):
        for version in ('2022', '2023', '2025', '', '12024'):
            with self.assertRaisesRegex(ValueError, 'complete saved-state files'):
                validate_source_version(version)


if __name__ == '__main__':
    unittest.main()
