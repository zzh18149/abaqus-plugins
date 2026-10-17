from __future__ import division
import os
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cai_source import ReadOnlyOdbCache, REQUIRED_FILES


class FakeOdb(object):
    version = '2022'
    def __init__(self): self.closed = False
    def close(self): self.closed = True
    @property
    def jobData(self):
        if self.closed: raise RuntimeError('closed native handle')
        return self


class SourceCache(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='cair_cache_test_')
        self.base = os.path.join(self.folder, 'source')
        for ext in REQUIRED_FILES+('.inp', '.sta'):
            with open(self.base+ext, 'wb') as handle: handle.write(b'original')
        self.cfg = {'source_odb': self.base+'.odb', 'source_inp': self.base+'.inp'}
        self.cache = ReadOnlyOdbCache()
        self.calls = []

    def tearDown(self):
        self.cache.close()
        for name in os.listdir(self.folder): os.remove(os.path.join(self.folder, name))
        os.rmdir(self.folder)

    def opener(self, **kwargs):
        self.assertTrue(kwargs['readOnly'])
        self.assertEqual(kwargs['path'], self.cfg['source_odb'])
        odb = FakeOdb()
        self.calls.append(odb)
        return odb

    def change(self, ext):
        with open(self.base+ext, 'ab') as handle: handle.write(b'changed')

    def test_reuse_and_explicit_close(self):
        first = self.cache.acquire(self.cfg, self.opener)
        self.assertIs(first, self.cache.acquire(self.cfg, self.opener))
        self.assertEqual(len(self.calls), 1)
        self.cache.close()
        self.assertTrue(first.closed)
        self.assertIsNot(first, self.cache.acquire(self.cfg, self.opener))

    def test_each_source_file_invalidates(self):
        for ext in REQUIRED_FILES+('.inp', '.sta'):
            first = self.cache.acquire(self.cfg, self.opener)
            self.change(ext)
            self.assertIsNot(first, self.cache.acquire(self.cfg, self.opener))
            self.assertTrue(first.closed)

    def test_externally_closed_handle_reopens(self):
        first = self.cache.acquire(self.cfg, self.opener)
        first.close()
        self.assertIsNot(first, self.cache.acquire(self.cfg, self.opener))

    def test_locked_or_missing_source_releases_handle(self):
        first = self.cache.acquire(self.cfg, self.opener)
        with open(self.base+'.lck', 'w') as handle: handle.write('locked')
        with self.assertRaises(ValueError): self.cache.acquire(self.cfg, self.opener)
        self.assertTrue(first.closed)
        os.remove(self.base+'.lck')
        second = self.cache.acquire(self.cfg, self.opener)
        os.remove(self.base+'.res')
        with self.assertRaises(OSError): self.cache.acquire(self.cfg, self.opener)
        self.assertTrue(second.closed)

    def test_change_during_read_rejected(self):
        first = self.cache.acquire(self.cfg, self.opener)
        self.change('.sta')
        with self.assertRaises(ValueError): self.cache.verify(self.cfg)
        self.assertTrue(first.closed)
        self.assertIsNone(self.cache.odb)

    def test_open_failure_does_not_retain_old_handle(self):
        first = self.cache.acquire(self.cfg, self.opener)
        self.change('.odb')
        def fail(**kwargs): raise RuntimeError('cannot open')
        with self.assertRaises(RuntimeError): self.cache.acquire(self.cfg, fail)
        self.assertTrue(first.closed)
        self.assertIsNone(self.cache.odb)


if __name__ == '__main__': unittest.main()
