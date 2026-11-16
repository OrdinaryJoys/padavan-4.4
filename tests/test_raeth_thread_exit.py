"""Fault models for real RAETH open/close/remove thread timeout handling.

The joined tasks, scheduler, IRQs, DMA and network core are simulated. The
park shim exits only after checking the preserved state; the kernel parks.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import raeth_runtime_harness as runtime
import raeth_remove_harness as remove

ROOT = Path(__file__).resolve().parents[1]

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('ambiguous fixture seam: ' + old[:80])
    return text.replace(old, new, 1)

def make_runtime():
    code=runtime.generate_source({k:(ROOT/v).read_text() for k,v in runtime.SOURCE_PATHS.items()})
    # Exercise the MT7623 creation branch; LRO itself remains an inert seam.
    code=replace_once(code,'#define FE_HW_LRO 0','#define FE_HW_LRO BIT(20)')
    code=replace_once(code,'static int fe_hw_lro_init(struct net_device *d) {(void)d;abort();}','static int fe_hw_lro_init(struct net_device *d) {(void)d;return 0;}')
    old='static int kthread_stop_timeout(void *p, unsigned long timeout, int *out) {(void)p;(void)timeout;*out=0;return 0;}'
    new='static int stop_count, fault_which, fault_open;\nstatic int kthread_stop_timeout(void *p, unsigned long timeout, int *out) { if(!p||timeout!=10UL*HZ) abort(); stop_count++; if(stop_count==fault_which)return -ETIMEDOUT; *out=0;return 0; }'
    code=replace_once(code,old,new)
    old='static void reboot_dma_failure_check(bool sleep) { (void)sleep; abort(); }'
    new='static void reboot_dma_failure_check(bool sleep) { if(!sleep || !(restart_failure_reports&REBOOT_DMA_RAETH) || !adapter.dma_quarantined || !adapter.module_reserved || module_refs!=1 || !adapter.dma_stages || stop_count!=fault_which || (fault_which==1 && !adapter.kreset_task) || (fault_which==2 && (adapter.kreset_task || !adapter.kphy_poll_task))) abort(); _Exit(0); }'
    code=replace_once(code,old,new)
    code=replace_once(code,'if(argc!=2)return 2;const char *name=argv[1];','if(argc!=3)return 2;const char *name=argv[1];fault_which=atoi(argv[2]);fault_open=!strcmp(name,"irq-1");')
    code=replace_once(code,'if(!strcmp(name,"esw-post-eio"))fail_esw_post=-5;', 'if(fault_open){adapter.chip_name=MT7623_FE;adapter.features|=FE_HW_LRO;}\n if(!strcmp(name,"esw-post-eio"))fail_esw_post=-5;')
    code=replace_once(code,'ret=ei_close(&main_dev);', 'adapter.kreset_task=(void *)5;adapter.kphy_poll_task=(void *)6;\n   ret=ei_close(&main_dev);')
    marker='return 0;\n}'
    pos=code.rfind(marker)
    if pos<0:raise ValueError('main return not found')
    return code[:pos]+code[pos:].replace(marker,'return 90;\n}',1)

def make_remove():
    code=remove.generate_source({k:(ROOT/v).read_text() for k,v in remove.SOURCE_PATHS.items()})
    old='static int kthread_stop_timeout(void *t, unsigned long timeout, int *out) { check(t&&timeout==10UL*HZ&&rtnl_depth&&thread_live>0);thread_live--;*out=0;return 0; }'
    new='static int stop_count, fault_which;\nstatic int kthread_stop_timeout(void *t, unsigned long timeout, int *out) { check(t&&timeout==10UL*HZ&&rtnl_depth&&thread_live>0);stop_count++;if(stop_count==fault_which)return -ETIMEDOUT;thread_live--;*out=0;return 0; }'
    code=replace_once(code,old,new)
    old='static void reboot_dma_failure_check(bool sleep) { (void)sleep; abort(); }'
    new='static void reboot_dma_failure_check(bool sleep) { if(!sleep || !(restart_failure_reports&REBOOT_DMA_RAETH) || !priv.dma_quarantined || !priv.module_reserved || module_refs!=1 || !dma_live || !irq_live || unregistered || freed || unmaps || core_releases || !parent.dev.data || !parent.dev.driver || rtnl_depth!=1 || stop_count!=fault_which || (fault_which==1 && !priv.kreset_task) || (fault_which==2 && (priv.kreset_task || !priv.kphy_poll_task))) abort(); _Exit(0); }'
    code=replace_once(code,old,new)
    code=replace_once(code,'if(argc!=2) { return 2; }','if(argc!=3) { return 2; } fault_which=atoi(argv[2]);')
    marker='return 0;\n}'
    pos=code.rfind(marker)
    if pos<0:raise ValueError('main return not found')
    return code[:pos]+code[pos:].replace(marker,'return 90;\n}',1)

def make_runtime_late():
    code=make_runtime()
    code=replace_once(code,'#include <stdio.h>','#include <stdio.h>\n#include <pthread.h>')
    old='static int stop_count, fault_which, fault_open;'
    new="""static pthread_t late_thread;
static pthread_mutex_t late_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t late_cv=PTHREAD_COND_INITIALIZER;
static int late_started,late_release,late_done;
static void *late_worker(void *unused) { (void)unused; if(pthread_mutex_lock(&late_lock))abort();late_started=1;pthread_cond_broadcast(&late_cv);while(!late_release)if(pthread_cond_wait(&late_cv,&late_lock))abort();late_done=1;pthread_cond_broadcast(&late_cv);pthread_mutex_unlock(&late_lock);return NULL; }
static int stop_count, fault_which, fault_open;"""
    code=replace_once(code,old,new)
    code=replace_once(code,'if(stop_count==fault_which)return -ETIMEDOUT;', 'if(stop_count==fault_which){if(pthread_create(&late_thread,NULL,late_worker,NULL))abort();if(pthread_mutex_lock(&late_lock))abort();while(!late_started)if(pthread_cond_wait(&late_cv,&late_lock))abort();pthread_mutex_unlock(&late_lock);return -ETIMEDOUT;}')
    old='abort(); _Exit(0); }'
    new='abort(); if(pthread_mutex_lock(&late_lock))abort();late_release=1;pthread_cond_broadcast(&late_cv);pthread_mutex_unlock(&late_lock);if(pthread_join(late_thread,NULL)||!late_done||!adapter.dma_quarantined||!adapter.dma_stages||module_refs!=1)abort(); _Exit(0); }'
    return replace_once(code,old,new)

class RaethThreadExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('K2P_RAETH_THREAD_TARGET_CC'):
            print('RAETH_THREAD_EXIT_TARGET=mipsel-linux-uclibc;RUNNER=qemu-mipsel',flush=True)

    def test_actual_open_close_remove_timeout_preserves_owners(self):
        target=os.environ.get('K2P_RAETH_THREAD_TARGET_CC')
        compilers=[(shutil.which('gcc-16'),[],[]),(shutil.which('clang'),['-fsanitize=address,undefined','-fno-sanitize-recover=all'],[])]
        if target:
            runner=shutil.which('qemu-mipsel');self.assertTrue(runner);compilers.append((target,['-static'],[runner]))
        with tempfile.TemporaryDirectory(prefix='raeth-thread-exit-') as tmp:
            for label,code,cases in [('runtime',make_runtime(),[('success','1'),('success','2'),('irq-1','1')]),('remove',make_remove(),[('success','1'),('success','2')])]:
                src=Path(tmp)/(label+'.c');src.write_text(code)
                for n,(cc,flags,runner) in enumerate(compilers):
                    self.assertTrue(cc);exe=Path(tmp)/(label+str(n))
                    subprocess.run([cc,'-std=gnu99','-Os','-fno-strict-aliasing','-Wall','-Wextra','-Werror',*flags,str(src),'-o',str(exe)],check=True,timeout=90)
                    if cc==target:
                        d=Path(os.environ['K2P_RAETH_THREAD_TARGET_DIR']);d.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(src,d/('target-raeth-thread-'+label+'.c'));shutil.copyfile(exe,d/('target-raeth-thread-'+label+'.elf'))
                    for case in cases:subprocess.run([*runner,str(exe),*case],check=True,timeout=15,env=dict(os.environ,ASAN_OPTIONS='symbolize=0'))

    def test_late_worker_completion_does_not_release_owners(self):
        code=make_runtime_late();target=os.environ.get('K2P_RAETH_THREAD_TARGET_CC')
        compilers=[(shutil.which('gcc-16'),[],[]),(shutil.which('clang'),['-fsanitize=address,undefined','-fno-sanitize-recover=all'],[])]
        if target:compilers.append((target,['-static'],[shutil.which('qemu-mipsel')]))
        with tempfile.TemporaryDirectory(prefix='raeth-thread-late-') as tmp:
            src=Path(tmp)/'late.c';src.write_text(code)
            for n,(cc,flags,runner) in enumerate(compilers):
                self.assertTrue(cc and all(runner));exe=Path(tmp)/('late'+str(n))
                subprocess.run([cc,'-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror',*flags,str(src),'-o',str(exe)],check=True,timeout=90)
                if cc==target:
                    d=Path(os.environ['K2P_RAETH_THREAD_TARGET_DIR']);shutil.copyfile(src,d/'target-raeth-thread-late.c');shutil.copyfile(exe,d/'target-raeth-thread-late.elf')
                for case in [('success','1'),('irq-1','1')]:subprocess.run([*runner,str(exe),*case],check=True,timeout=15,env=dict(os.environ,ASAN_OPTIONS='symbolize=0'))

    def test_open_failure_errno_survives_successful_thread_join(self):
        code=make_runtime()
        # The extra LRO seam is reached only by this simulated other-chip profile.
        code=replace_once(code,'static void fe_hw_lro_deinit(struct net_device *d) {(void)d;abort();}','static void fe_hw_lro_deinit(struct net_device *d) {(void)d;}')
        with tempfile.TemporaryDirectory(prefix='raeth-open-errno-') as tmp:
            src=Path(tmp)/'test.c';src.write_text(code);exe=Path(tmp)/'test'
            subprocess.run([shutil.which('gcc-16'),'-std=gnu99','-Os',str(src),'-o',str(exe)],check=True,timeout=90)
            result=subprocess.run([str(exe),'irq-1','0'],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,90,result.stderr)
            self.assertEqual(__import__('json').loads(result.stdout)['ret'],-16)

    def test_returning_from_quarantine_is_detected(self):
        for label,code in [('runtime',make_runtime()),('remove',make_remove())]:
            needle='reboot_dma_failure_check(true);'
            self.assertGreater(code.count(needle),0);code=code.replace(needle,'(void)0;')
            with tempfile.TemporaryDirectory(prefix='raeth-thread-return-') as tmp:
                src=Path(tmp)/(label+'.c');src.write_text(code);exe=Path(tmp)/label
                subprocess.run([shutil.which('gcc-16'),'-std=gnu99','-Os',str(src),'-o',str(exe)],check=True,timeout=90)
                result=subprocess.run([str(exe),'success','1'],capture_output=True,timeout=15)
                self.assertNotEqual(result.returncode,0)

    def test_missing_failure_publication_is_rejected(self):
        for label,code in [('runtime',make_runtime()),('remove',make_remove())]:
            needle='reboot_dma_failure_report(REBOOT_DMA_RAETH);'
            # Remove every production failure publication; the shim requires it.
            self.assertGreater(code.count(needle),0);code=code.replace(needle,'(void)0;')
            with tempfile.TemporaryDirectory(prefix='raeth-thread-negative-') as tmp:
                src=Path(tmp)/(label+'.c');src.write_text(code);exe=Path(tmp)/label
                subprocess.run([shutil.which('gcc-16'),'-std=gnu99','-Os',str(src),'-o',str(exe)],check=True,timeout=90)
                result=subprocess.run([str(exe),'success','1'],capture_output=True,timeout=15)
                self.assertNotEqual(result.returncode,0)
if __name__=='__main__':unittest.main()
