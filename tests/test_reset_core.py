"""Sequential pulse accounting; no physical reset or kernel concurrency."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import reset_core_harness as h
ROOT=Path(__file__).resolve().parents[1]
BASE='8371e9d2471d85199c8fefcff5fee43e2494094d'

class ResetCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='reset-core-');cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/p).read_text()for k,p in h.SOURCE_PATHS.items()};cls.code=h.generate_source(cls.texts)
        cls.compilers=[('gcc',shutil.which('gcc-16')or shutil.which('gcc')),('clang',shutil.which('clang'))]
        for name,compiler in cls.compilers:
            if not compiler:raise AssertionError('GNU GCC and Clang required')
            version=subprocess.check_output([compiler,'--version'],text=True,timeout=10)
            if name=='gcc'and('Free Software Foundation'not in version or'clang'in version.lower()):raise AssertionError('True GNU GCC required')
        cls.binaries=cls.compile_code(cls.code,'current')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    @classmethod
    def compile_code(cls,code,label):
        source=cls.directory/(label+'.c');source.write_text(code);binaries=[]
        for name,compiler in cls.compilers:
            binary=cls.directory/(label+'-'+name);flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror']
            if name=='clang':flags+=['-fsanitize=address,undefined']
            run=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            if run.returncode:raise AssertionError(run.stderr)
            binaries.append(binary)
        return binaries
    def rows(self,names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(binary=binary.name,case=name):
                    run=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
                    self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stderr,'')
                    self.assertEqual(json.loads(run.stdout),h.EXPECTED_ROWS[name])
    def test_exclusive_success_failure_and_retry_are_unchanged(self):
        self.rows(('exclusive-success','exclusive-failure','exclusive-retry','exclusive-repeat','exclusive-deasserted'))
    def test_shared_success_is_consumed_and_failed_attempts_remain_retryable(self):
        self.rows(('shared-success','shared-repeat','shared-failure','shared-retry-1','shared-retry-2','shared-consumed','shared-already-consumed'))
    def test_invalid_optional_and_mode_guards_have_no_provider_side_effect(self):
        self.rows(('shared-deasserted','null','error-pointer','missing-reset','shared-missing-reset'))
    def test_whole_body_identity_and_explicit_sequential_boundary(self):
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS));self.assertEqual(len(h.CASE_NAMES),17)
        self.assertEqual(len(h.function_manifest(self.texts)),3);self.assertEqual(h.source_only_manifest(self.texts),{})
        self.assertEqual(self.code.count(h.function(self.texts['core'],'reset_control_reset')),1)
        for key in ('synthetic_reset_control_layout','atomic_shims_are_sequential_not_kernel_scheduling','machine_restart_and_hardware_are_not_executed'):self.assertTrue(h.MODEL_VARIANT[key])
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source({'core':self.texts['core']+'\n'+h.function(self.texts['core'],'reset_control_reset')})
        for binary in self.binaries:
            run=subprocess.run([str(binary),'unknown'],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(run.returncode,0);self.assertEqual(run.stdout,'')
    def reject(self,code,names,label):
        for binary in self.compile_code(code,label):
            for name in names:
                run=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
                self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stderr,'')
                self.assertNotEqual(json.loads(run.stdout),h.EXPECTED_ROWS[name])
    def test_pinned_original_reproduces_duplicate_pulse_and_false_success_after_failure(self):
        old=subprocess.check_output(['git','show',BASE+':'+h.SOURCE_PATHS['core']],cwd=ROOT,text=True,timeout=10)
        self.assertIn('if (rstc->shared && !ret)',old)
        # The historical source predates the shared gate. Reconstruct its
        # complete original function without unused current-only shims.
        prefix=h.PREFIX
        for name in ('atomic_cmpxchg','atomic_xchg'):
            prefix=prefix.replace(h.function(prefix,name),'')
        admission='if ('+' && '.join('strcmp(name,"'+n+'")'for n in h.CASE_NAMES)+') return 2;'
        code=prefix+'\n'+h.function(old,'reset_control_reset')+'\n'+h.SUFFIX.replace('CASE_ADMISSION',admission)
        self.reject(code,('shared-repeat','shared-retry-1'),'original')
    def test_rollback_consumption_and_mode_guard_mutants_are_rejected(self):
        self.assertEqual(self.code.count('if (rstc->shared && ret)'),1)
        self.reject(self.code.replace('if (rstc->shared && ret)','if (0 && rstc->shared && ret)'),('shared-retry-1',),'no-rollback')
        self.reject(self.code.replace('if (rstc->shared && ret)','if (rstc->shared)'),('shared-repeat',),'no-consumption')
        before='if (atomic_inc_return(&rstc->triggered_count) != 1)\n\t\t\treturn reset_control_shared_done(rstc, 0);'
        self.assertEqual(self.code.count(before),1)
        self.reject(self.code.replace(before,'(void)atomic_inc_return(&rstc->triggered_count);'),('shared-repeat',),'no-once-guard')
        before='atomic_read(&rstc->deassert_count) != 0'
        self.assertEqual(self.code.count(before),1)
        self.reject(self.code.replace(before,'atomic_read(&rstc->deassert_count) < 0'),('shared-deasserted',),'no-mode-guard')

if __name__=='__main__':unittest.main()
