"""Actual extract_test recipe against public vendor data, entirely private."""
from pathlib import Path, PurePosixPath
import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from bounded_log_harness import INADYN_SOURCE_PATHS, patched_inadyn_source

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'trunk/user/inadyn'


class InadynLogPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='k2p-inadyn-patch-')
        self.base=Path(self.temp.name).resolve()
        self.archive=(PACKAGE/'inadyn-2.8.1.tar.xz').read_bytes()
        # This checks the exact public fixture before running the same host tar
        # recipe as production. No archive link/device node is extracted.
        with tarfile.open(fileobj=io.BytesIO(self.archive)) as package:
            for item in package.getmembers():
                name=PurePosixPath(item.name)
                self.assertFalse(name.is_absolute())
                self.assertNotIn('..',name.parts)
                self.assertEqual(name.parts[0],'inadyn-2.8.1')
                self.assertTrue(item.isfile() or item.isdir(),item.name)
        for name in ('Makefile','inadyn-2.8.1.tar.xz','inadyn-2.8.1.patch','inadyn-bounded-log.patch'):
            shutil.copyfile(PACKAGE/name,self.base/name)
        self.log=self.base/'inadyn-2.8.1/src/log.c'
        self.expected=patched_inadyn_source(self.archive,
            (PACKAGE/'inadyn-2.8.1.patch').read_text(),(PACKAGE/'inadyn-bounded-log.patch').read_text())

    def tearDown(self):self.temp.cleanup()

    def extract(self,expected=0):
        process=subprocess.run(['make','--no-print-directory','extract_test'],cwd=self.base,
                               capture_output=True,text=True,timeout=20)
        if expected==0:self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        else:self.assertNotEqual(process.returncode,0,process.stdout+process.stderr)
        return process

    def restore_vendor_logger(self):
        subprocess.run(['patch','-d','inadyn-2.8.1','-p1','-R','--force','--batch','--fuzz=0',
                        '-i','../inadyn-bounded-log.patch'],cwd=self.base,check=True,capture_output=True,text=True)

    def test_fresh_extract_and_repeated_idempotent_recipe(self):
        self.extract();self.assertEqual(self.log.read_text(),self.expected)
        before=self.log.read_bytes();self.extract();self.assertEqual(self.log.read_bytes(),before)

    def test_existing_vendor_tree_gets_the_new_logger(self):
        self.extract();self.restore_vendor_logger()
        self.assertNotIn('padavan_log_vwrite',self.log.read_text())
        self.extract();self.assertEqual(self.log.read_text(),self.expected)

    def test_changed_existing_tree_fails_before_partial_application(self):
        self.extract();self.restore_vendor_logger()
        text=self.log.read_text().replace('static int level   = LOG_NOTICE;','static int level   = LOG_DEBUG;')
        self.log.write_text(text);before=self.log.read_bytes()
        self.extract(expected=1);self.assertEqual(self.log.read_bytes(),before)

    def test_pure_replay_rejects_hunk_drift_and_future_vendor_logger_changes(self):
        vendor=(PACKAGE/'inadyn-2.8.1.patch').read_text()
        patch=(PACKAGE/'inadyn-bounded-log.patch').read_text()
        with self.assertRaises(ValueError):
            patched_inadyn_source(self.archive,vendor,patch.replace('static int level   = LOG_NOTICE;',
                                                                 'static int level   = LOG_DEBUG;'))
        with self.assertRaises(ValueError):
            patched_inadyn_source(self.archive,vendor+'\n+++ b/src/log.c\n',patch)


if __name__=='__main__':unittest.main()
