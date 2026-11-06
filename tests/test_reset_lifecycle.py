"""Whole reset consumer/devres lifetimes and nonblocking shared progress.

Fixtures model module/OF/devres ownership; they do not execute kernel scheduler,
physical reset, DMA, hot-unbind, or production kernel layouts. Native pthread
checks add real overlap around a sleeping provider with synthetic atomics.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import reset_lifecycle_harness as h

ROOT=Path(__file__).resolve().parents[1]
NATIVE = r'''
#undef main
static pthread_mutex_t gate_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_condition=PTHREAD_COND_INITIALIZER;
static int gate_entered,gate_release,worker_result;
static pthread_t active_thread;
struct task { int op; struct reset_control *control; };
static void provider_gate(int op)
{
 if (!pthread_equal(pthread_self(),active_thread)) return;
 if (pthread_mutex_lock(&gate_mutex)) abort();
 gate_entered=op+1;
 if (pthread_cond_broadcast(&gate_condition)) abort();
 while (!gate_release) if (pthread_cond_wait(&gate_condition,&gate_mutex)) abort();
 if (pthread_mutex_unlock(&gate_mutex)) abort();
}
static void *provider_worker(void *arg)
{
 struct task *work=arg;
 active_thread=pthread_self(); worker_result=invoke(work->op,work->control); return NULL;
}
int main(void)
{
 int op,round,iterations=0;
 for (op=0;op<3;op++) for (round=0;round<64;round++) {
  struct reset_control_ops ops={inert_reset,inert_assert,inert_deassert};
  struct reset_controller_dev dev={0};
  struct reset_control control={0},independent={0};
  struct task task={op,&control}; pthread_t worker; int before,result,i;
  dev.ops=&ops; provider=&dev;
  control.rcdev=&dev; control.id=13; control.shared=true;
  control.deassert_count.value=op==1 ? 1 : 0;
  independent.rcdev=&dev; independent.id=13; independent.shared=false;
  gate_entered=gate_release=worker_result=0; depth=warns=successes=0;
  fail_count=1; reenter=-1; entered=0;
  for (i=0;i<3;i++) calls[i]=0;
  if (pthread_create(&worker,NULL,provider_worker,&task)) return 10;
  if (pthread_mutex_lock(&gate_mutex)) abort();
  while (!gate_entered) if (pthread_cond_wait(&gate_condition,&gate_mutex)) abort();
  if (gate_entered!=op+1) return 11;
  if (pthread_mutex_unlock(&gate_mutex)) abort();
  /* Main must return while the provider thread is still sleeping. The outer
   * subprocess timeout turns a blocking/spinning framework into a failure. */
  if (invoke(op,&control)!=-EAGAIN) return 12;
  if (invoke((op+1)%3,&control)!=-EAGAIN) return 13;
  if (atomic_read(&control.shared_busy)!=1 || calls[op]!=1 || successes) return 14;
  /* An independent exclusive caller must not wait behind the shared provider. */
  if (invoke(op,&independent) || independent.triggered_count.value || independent.deassert_count.value) return 15;
  if (pthread_mutex_lock(&gate_mutex)) abort();
  gate_release=1;
  if (pthread_cond_broadcast(&gate_condition)) abort();
  if (pthread_mutex_unlock(&gate_mutex)) abort();
  if (pthread_join(worker,NULL)) return 16;
  if (worker_result!=-5 || atomic_read(&control.shared_busy)) return 17;
  if (control.triggered_count.value || control.deassert_count.value!=(op==1 ? 1 : 0)) return 18;
  if (invoke(op,&control)) return 19;
  if (calls[op]!=3 || successes!=2 || control.shared_busy.value) return 20;
  before=calls[op]; result=invoke(op,&control);
  if (op==1) { if (result!=-EINVAL || warns!=1 || control.deassert_count.value) return 21; }
  else if (result || (op==0 ? control.triggered_count.value : control.deassert_count.value)!=2) return 22;
  if (calls[op]!=before) return 23;
  iterations++;
 }
 printf("{\"iterations\":%d,\"provider_modes\":3,\"busy_returns_before_release\":true,\"failure_retry\":true,\"independent_progress\":true}\n",iterations);
 return 0;
}
'''

class ResetLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='reset-lifecycle-');cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/p).read_text() for k,p in h.SOURCE_PATHS.items()};cls.code=h.generate_source(cls.texts)
        cls.compilers=[('gcc',shutil.which('gcc-16')or shutil.which('gcc')),('clang',shutil.which('clang'))]
        for name,compiler in cls.compilers:
            if not compiler:raise AssertionError('True GNU GCC and Clang required')
            version=subprocess.check_output([compiler,'--version'],text=True,timeout=10)
            if name=='gcc' and ('Free Software Foundation'not in version or 'clang'in version.lower()):raise AssertionError('True GNU GCC required')
        cls.binaries=cls.compile_code(cls.code,'current')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    @classmethod
    def compile_code(cls,code,label,pthread=False):
        source=cls.directory/(label+'.c');source.write_text(code);binaries=[]
        for name,compiler in cls.compilers:
            binary=cls.directory/(label+'-'+name)
            # Full Linux devres callbacks intentionally retain an unused dev
            # argument. Keep all other extra warnings and sanitizer coverage.
            flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror','-Wno-unused-parameter']
            if name=='clang':flags+=['-fsanitize=address,undefined']
            if pthread:flags+=['-pthread']
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
    def test_whole_shared_operation_failures_modes_reentry_and_overflow(self):
        self.rows(h.CASE_NAMES[:26])
    def test_whole_consumer_optional_devres_module_and_reference_lifetimes(self):
        self.rows(h.CASE_NAMES[26:])
    def test_exact_whole_functions_declaration_and_case_admission(self):
        self.assertEqual(len(h.CASE_NAMES),48);self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),12);self.assertEqual(h.source_only_manifest(self.texts),{})
        self.assertEqual(set(h.declarations_manifest(self.texts)),set(h.SOURCE_DECLARATIONS))
        for name in h.BODY_ORDER:self.assertEqual(self.code.count(h.function(self.texts['core'],name)),1)
        self.assertTrue(h.MODEL_VARIANT['synthetic_kernel_and_OF_layout'])
        self.assertTrue(h.MODEL_VARIANT['atomic_shims_are_sequential_not_kernel_scheduling'])
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source({'core':self.texts['core']+'\n'+h.function(self.texts['core'],'reset_control_put')})
        for binary in self.binaries:
            run=subprocess.run([str(binary),'unknown'],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(run.returncode,0);self.assertEqual(run.stdout,'')
    def reject_rows(self,code,cases,label):
        for binary in self.compile_code(code,label):
            for case in cases:
                run=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10)
                self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stderr,'')
                self.assertNotEqual(json.loads(run.stdout),h.EXPECTED_ROWS[case])
    def reject_crash_or_rows(self,code,cases,label):
        for binary in self.compile_code(code,label):
            for case in cases:
                run=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10)
                if run.returncode:self.assertTrue(run.returncode);continue
                self.assertNotEqual(json.loads(run.stdout),h.EXPECTED_ROWS[case])
    def test_original_optional_release_and_module_pin_failures_are_rejected(self):
        before='if (IS_ERR_OR_NULL(rstc))\n\t\treturn;'
        self.assertEqual(self.code.count(before),1)
        old_put=self.code.replace(before,'if (IS_ERR(rstc))\n\t\treturn;')
        self.reject_crash_or_rows(old_put,('put-optional-null','devres-release-historical-null'),'old-null-put')
        before='if (!IS_ERR_OR_NULL(rstc)) {'
        self.assertEqual(old_put.count(before),1)
        self.reject_crash_or_rows(old_put.replace(before,'if (!IS_ERR(rstc)) {'),('devm-optional-absent',),'old-devm-null-release')
        before='if (!try_module_get(rcdev->owner)) {\n\t\tkfree(rstc);\n\t\treturn ERR_PTR(-ENODEV);\n\t}'
        self.assertEqual(self.code.count(before),1)
        self.reject_crash_or_rows(self.code.replace(before,'(void)try_module_get(rcdev->owner);'),('direct-owner-unloading','devm-owner-unloading'),'old-owner-unloading')
    def test_shared_gate_rollback_and_overflow_mutants_are_rejected(self):
        before='if (rstc->shared && atomic_cmpxchg(&rstc->shared_busy, 0, 1))\n\t\treturn -EAGAIN;'
        self.assertEqual(self.code.count(before),1)
        self.reject_rows(self.code.replace(before,before.replace('return -EAGAIN','return 0')),('reset-reenter','assert-reenter-deassert','deassert-reenter-assert'),'false-success-busy')
        before='if (rstc->shared && ret)\n\t\tatomic_inc(&rstc->deassert_count);'
        self.assertEqual(self.code.count(before),1)
        self.reject_rows(self.code.replace(before,'if (0 && rstc->shared && ret)\n\t\tatomic_inc(&rstc->deassert_count);'),('assert-failure-retry',),'no-assert-rollback')
        before='if (rstc->shared && ret)\n\t\tatomic_dec(&rstc->deassert_count);'
        self.assertEqual(self.code.count(before),1)
        self.reject_rows(self.code.replace(before,'if (0 && rstc->shared && ret)\n\t\tatomic_dec(&rstc->deassert_count);'),('deassert-failure-retry',),'no-deassert-rollback')
        before='if (rstc->refcnt == UINT_MAX)\n\t\t\t\treturn ERR_PTR(-EOVERFLOW);'
        self.assertEqual(self.code.count(before),1)
        self.reject_rows(self.code.replace(before,''),('shared-reference-overflow',),'no-reference-overflow')
        before='if (atomic_read(&rstc->deassert_count) == INT_MAX)\n\t\t\treturn reset_control_shared_done(rstc, -EOVERFLOW);'
        self.assertEqual(self.code.count(before),1)
        # The mutant signed overflow is intentionally rejected by UBSan or rows.
        self.reject_crash_or_rows(self.code.replace(before,''),('deassert-count-overflow',),'no-count-overflow')
    def pthread_source(self,code):
        # pthread headers precede synthetic MIPS errno constants. Native host
        # errors are not model observations and do not overwrite model errno.
        undef='\n'.join('#undef '+name for name in ('EINVAL','EAGAIN','ENOMEM','EBUSY','ENODEV','EOVERFLOW','ENOENT','EILSEQ'))
        return '#include <pthread.h>\n#include <errno.h>\n'+undef+'\n#define NATIVE_PTHREAD_TEST 1\n#define main model_main\n'+code+'\n'+NATIVE
    def test_native_pthread_sleeping_provider_progress_and_failure_retry(self):
        for binary in self.compile_code(self.pthread_source(self.code),'pthread',pthread=True):
            run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stderr,'')
            self.assertEqual(json.loads(run.stdout),dict(iterations=192,provider_modes=3,busy_returns_before_release=True,failure_retry=True,independent_progress=True))
        before='return -EAGAIN;'
        self.assertEqual(self.code.count(before),1)
        for binary in self.compile_code(self.pthread_source(self.code.replace(before,'return 0;')),'pthread-false-success',pthread=True):
            run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
            self.assertNotEqual(run.returncode,0)

if __name__=='__main__':unittest.main()
