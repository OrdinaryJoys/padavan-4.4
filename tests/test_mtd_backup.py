#!/usr/bin/env python3
"""Actual main/open/metadata/dump; synthetic I/O, ASan/UBSan negative controls."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import mtd_backup_harness as harness

ROOT=Path(__file__).resolve().parents[1]


class MtdBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-mtd-backup-')
        cls.base=Path(cls.temp.name).resolve()
        cls.texts={key:(ROOT/path).read_text() for key,path in harness.SOURCE_PATHS.items()}
        cls.binaries={}
        cls.codes={}
        for kind in ('current','baseline','disabled'):
            code=harness.generate_source(cls.texts,str(cls.base/(kind+'-fixtures')),os.geteuid(),
                                         baseline=kind=='baseline',disabled_oracle=kind=='disabled')
            cls.codes[kind]=code
            path=cls.base/(kind+'.c');path.write_text(code)
            binary=cls.base/kind
            result=subprocess.run([shutil.which('clang') or shutil.which('cc'),'-std=gnu99','-Os',
                                   '-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                                   '-Wno-unused-function','-Wno-sign-compare',
                                   '-fsanitize=address,undefined','-g',str(path),'-o',str(binary)],
                                  capture_output=True,text=True,timeout=30)
            if result.returncode:raise AssertionError(result.stderr)
            cls.binaries[kind]=binary

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def record(self,case,kind='current'):
        result=subprocess.run([str(self.binaries[kind]),case],text=True,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('AddressSanitizer',result.stderr)
        self.assertNotIn('runtime error:',result.stderr)
        return json.loads(result.stdout)

    def test_all_actual_paths_and_bytes(self):
        for case in harness.CASE_NAMES:
            with self.subTest(case=case):self.assertTrue(harness.validate_row(self.record(case)))

    def test_literal_baseline_demonstrates_false_success_rw_open_and_cleanup_faults(self):
        for case in harness.BASELINE_CASES:
            with self.subTest(case=case):
                row=self.record(case,'baseline')
                self.assertTrue(harness.validate_row(row,baseline=True))
                with self.assertRaises(ValueError):harness.validate_row(row)

    def test_oracle_disabled_cannot_pass_as_new_model(self):
        for case in harness.CASE_NAMES:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):harness.validate_row(self.record(case,'disabled'))

    def test_actual_functions_bound_once_and_input_identity_strict(self):
        for item in harness.actual_functions(self.texts).values():
            self.assertEqual(self.codes['current'].count(item['body']),1)
        with self.assertRaises(ValueError):harness.generate_source({**self.texts,'extra':''},'/tmp/a')
        with self.assertRaises(ValueError):harness.generate_source(self.texts,'relative')

    def test_report_contract_rejects_changed_bytes_effects_types_and_missing_fields(self):
        original=self.record('normal')
        for key,value in [('returncode',False),('readonly',0),('nonblock',False),
                          ('output','0123456789ABCDE'),('trace','sync,unlock,erase'),
                          ('reads',True),('flags',True),('bad_offsets',[True])]:
            row=copy.deepcopy(original);row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):harness.validate_row(row)
        row=copy.deepcopy(original);row.pop('writes')
        with self.assertRaises(ValueError):harness.validate_row(row)


if __name__=='__main__':unittest.main()
