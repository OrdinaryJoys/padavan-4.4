"""Current complete task owner functions with inert private reference controls."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import kthread_owner_harness as h

ROOT=Path(__file__).resolve().parents[1]


class KthreadOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-current-task-owner-')
        cls.directory=Path(cls.temp.name);cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts);source=cls.directory/'task.c';source.write_text(cls.generated)
        gnu=shutil.which('gcc-16')
        if gnu is None and Path('/opt/homebrew/bin/gcc-16').is_file():gnu='/opt/homebrew/bin/gcc-16'
        if gnu is None:gnu=shutil.which('gcc')
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation'not in version or 'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for name,compiler in (('clang',shutil.which('clang')),('gcc',gnu)):
            if not compiler:raise AssertionError('Required compiler absent: '+name)
            binary=cls.directory/name;flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror','-Wno-unused-parameter']
            if name=='clang':flags+=['-fsanitize=address,undefined']
            result=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=30)
            if result.returncode:raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def cases(self,names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(compiler=binary.name,case=name):
                    result=subprocess.run([str(binary),name],check=True,capture_output=True,text=True,timeout=5)
                    row=json.loads(result.stdout);self.assertEqual(row,h.EXPECTED_ROWS[name])
                    self.assertTrue(all(type(value)is int for value in row))

    def test_create_failure_and_create_get_publish_wake_reference_order(self):
        self.cases(('create-failure','create-order','kill-no-owner'))

    def test_natural_early_exit_and_nonzero_exit_retain_owner_until_kill(self):
        self.cases(('natural-early-exit','nonzero-exit'))

    def test_repeat_kill_and_existing_task_init_or_attach_preserve_ownership(self):
        self.cases(('repeat-kill','existing-owner'))

    def test_whole_current_functions_and_data_only_model_are_bound(self):
        self.assertEqual(len(h.CASE_NAMES),7)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),3)
        for name in h.BODY_ORDER:self.assertEqual(self.generated.count(h.function(self.texts['os'],name)),1)
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')


if __name__=='__main__':unittest.main()
