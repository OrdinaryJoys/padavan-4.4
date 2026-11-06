"""RAETH proc lifecycle: actual entry bodies, ordinary process and inert proc model."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import raeth_proc_harness as h
ROOT=Path(__file__).resolve().parents[1]

class RaethProcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='raeth-proc-')
        cls.base=Path(cls.temp.name)
        cls.texts={k:(ROOT/p).read_text()for k,p in h.SOURCE_PATHS.items()}
        cls.code=h.generate_source(cls.texts)
        cls.binaries=[]
        for label,compiler in [('clang',shutil.which('clang')),('gcc',shutil.which('gcc-16')or shutil.which('gcc-15')or(shutil.which('gcc')if os.uname().sysname=='Linux'else None))]:
            if not compiler:raise RuntimeError('Clang and GNU GCC required')
            cls.binaries.append(cls.compile(cls.code,label,compiler))
        cls.old=cls.compile(h.generate_source(cls.texts,baseline=True),'old',shutil.which('clang'))
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    @classmethod
    def compile(cls,code,label,compiler):
        src=cls.base/(label+'.c');src.write_text(code);binary=src.with_suffix('')
        argv=[compiler,'-std=gnu89','-O1','-g','-Wall','-Wextra','-Werror']
        if 'clang'in Path(compiler).name:argv+=['-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
        r=subprocess.run([*argv,str(src),'-o',str(binary)],capture_output=True,text=True,timeout=45)
        if r.returncode:raise AssertionError((label,r.stderr))
        return binary
    def row(self,case,binary=None):
        r=subprocess.run([str(binary or self.binaries[0]),case],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,(case,r.stderr));self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)
    def check(self,names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(binary=binary.name,case=name):self.assertEqual(self.row(name,binary),h.EXPECTED_ROWS[name])
    def test_full_minimal_and_rss_profile_all_owned_children_retire(self):
        self.check(('full','minimal','rss'))
    def test_each_optional_child_oom_stays_best_effort_and_complete_cleanup(self):
        self.check([n for n in h.CASE_NAMES if n.startswith('child-oom-')])
    def test_directory_oom_never_publishes_root_children(self):
        self.check(('directory-oom',))
    def test_duplicate_init_rejected_without_replacing_owner_and_retry_works(self):
        self.check(('duplicate-init','retry','profile-change'))
    def test_repeat_exit_and_inert_callback_drain_are_explicit(self):
        self.check(('repeat-exit','active-callbacks'))
        self.assertTrue(h.MODEL_VARIANT['callback_rundown_is_inert'])
    def test_fixed_old_bodies_expose_retained_handlers_double_remove_and_root_creation(self):
        for name,body in h.BASELINE_FUNCTIONS.items():self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),h.BASELINE_SHA256[name])
        old=self.row('full',self.old)
        self.assertGreater(old['live'],0);self.assertGreater(old['stale_handles'],0)
        self.assertEqual(old['duplicate_remove'],1);self.assertEqual(old['subtree_calls'],0)
        old=self.row('directory-oom',self.old)
        self.assertEqual(old['ret'],0);self.assertGreater(old['root_publications'],0)
        self.assertGreater(old['live'],0)
    def reject(self,old,new,case,label):
        self.assertEqual(self.code.count(old),1)
        binary=self.compile(self.code.replace(old,new,1),label,shutil.which('clang'))
        row=self.row(case,binary);self.assertNotEqual(row,h.EXPECTED_ROWS[case])
    def test_missing_directory_failure_check_negative_control(self):
        self.reject('if (!proc_reg_dir)\n\t\treturn -ENOMEM;','/* missing directory guard */','directory-oom','no-dir-guard')
    def test_missing_subtree_remove_negative_control(self):
        self.reject('proc_remove(proc_reg_dir);','(void)proc_reg_dir;','full','no-subtree-remove')
    def test_parent_owner_must_remain_until_subtree_remove(self):
        self.reject('proc_remove(proc_reg_dir);','proc_reg_dir = NULL;\n\tproc_remove(proc_reg_dir);','full','early-parent-clear')
    def test_actual_functions_source_only_rundown_and_macro_inputs_are_bound(self):
        self.assertEqual(len(h.CASE_NAMES),29)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),3)
        self.assertEqual(len(h.source_only_manifest(self.texts)),1)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.code.count(h.function(self.texts[key],name)),1)
        subtree=h.function(self.texts['generic'],'remove_proc_subtree')
        self.assertIn('proc_entry_rundown(de);',subtree)
        self.assertIn('while (1)',subtree)
        self.assertNotIn(subtree,self.code)
        for key in h.SOURCE_PATHS:
            bad=dict(self.texts);del bad[key]
            with self.assertRaises(ValueError):h.generate_source(bad)
        bad=dict(self.texts,reg=self.texts['reg'].replace('"set_lan_ip"','"changed_leaf"'))
        with self.assertRaises(ValueError):h.generate_source(bad)
        bad=dict(self.texts,proc=self.texts['proc']+'\n'+h.function(self.texts['proc'],'debug_proc_exit'))
        with self.assertRaises(ValueError):h.generate_source(bad)

if __name__=='__main__':unittest.main()
