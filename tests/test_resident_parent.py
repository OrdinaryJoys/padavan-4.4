"""Actual worker fork/FD/mask contract, all exec/flash/reset effects inert."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import resident_parent_harness as h

ROOT=Path(__file__).resolve().parents[1]


class ResidentParentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-resident-parent-')
        cls.root=Path(cls.temp.name);cls.fixture=cls.root/'fixture'
        cls.texts={k:(ROOT/v).read_text() for k,v in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts,str(cls.fixture),os.geteuid())
        path=cls.root/'parent.c';path.write_text(cls.generated);cls.binary=cls.root/'parent'
        result=subprocess.run(['clang','-std=gnu99','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                               '-fsanitize=address,undefined',str(path),'-o',str(cls.binary)],capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def cases(self,names):
        for name,wanted in h.CASES:
            if name not in names:continue
            with self.subTest(case=name):
                if self.fixture.exists():shutil.rmtree(self.fixture)
                result=subprocess.run([str(self.binary),name],capture_output=True,text=True,timeout=8)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads(result.stdout),wanted)
    def test_fd3_and_high_descriptor_closure_empty_environment_and_signal_mask(self):
        self.cases({'fd3','fd-high'})
    def test_raw_statuses_and_exec_return_cannot_fall_into_parent_code(self):
        self.cases({'child-safe20','unexpected-zero','exec-failure','wait-eintr'})
    def test_spawn_and_mask_failures_keep_explicit_unknown_status(self):
        self.cases({'fork-failure','invalid-lease','parent-mask-failure','parent-restore-failure'})
    def test_every_child_setup_failure_exits_before_exec(self):
        self.cases({n for n,_ in h.CASES}-{ 'fd3','fd-high','child-safe20','unexpected-zero','exec-failure','wait-eintr','fork-failure','invalid-lease','parent-mask-failure','parent-restore-failure'})
    def test_generator_embeds_actual_functions_and_rejects_ambiguous_inputs(self):
        for name in h.FUNCTIONS['rc']:
            self.assertEqual(self.generated.count(h.extract(self.texts['rc'],name)),1)
        for uid in (True,-1,2**32):
            with self.assertRaises(ValueError):h.generate_source(self.texts,str(self.fixture),uid)
        with self.assertRaises(ValueError):h.generate_source({},str(self.fixture))
        with self.assertRaises(ValueError):h.generate_source(self.texts,'relative',0)
