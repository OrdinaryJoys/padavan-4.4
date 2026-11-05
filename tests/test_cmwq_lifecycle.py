"""Inert CMWQ owner contracts; no Linux workqueue, DMA or device executes."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import cmwq_lifecycle_harness as h

ROOT=Path(__file__).resolve().parents[1]
FLAGS=['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror',
       '-fno-strict-aliasing','-Wno-unused-parameter','-Wno-unused-variable',
       '-Wno-unused-but-set-variable']


class CmwqLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-cmwq-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts)
        source=cls.directory/'cmwq.c';source.write_text(cls.generated)
        gnu=shutil.which('gcc-16')or shutil.which('gcc')
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation'not in version or 'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for name,compiler,extra in (('clang-asan',shutil.which('clang'),['-fsanitize=address,undefined']),
                                   ('gcc',gnu,[]),('gcc-old-kernel',gnu,['-DLINUX_VERSION_CODE=132644']),
                                   ('gcc-allocator-boundary',gnu,['-DLINUX_VERSION_CODE=132645'])):
            if not compiler:raise AssertionError('Required compiler absent: '+name)
            binary=cls.directory/name
            result=subprocess.run([compiler,*FLAGS,*extra,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            if result.returncode:raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def cases(self,*names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(compiler=binary.name,case=name):
                    result=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    row=json.loads(result.stdout);self.assertEqual(row,h.EXPECTED_ROWS[name])
                    self.assertTrue(all(type(x)is int for x in row))

    def test_null_allocations_never_publish_and_second_stage_unwinds_first(self):
        self.cases('qm-oom','hif-oom','hif-rollback-oom')

    def test_supported_queue_modes_and_rbus_select_initialized_callbacks(self):
        self.cases('normal-fast','normal-fair','normal-generic','normal-generic-fair','rbus-normal')

    def test_duplicate_initialization_preserves_owner_and_work_identity(self):
        self.cases('qm-owner','hif-owner','tm-owner')

    def test_unsupported_mode_and_interface_cannot_publish_uninitialized_work(self):
        self.cases('qm-invalid-mode','hif-invalid-bus')

    def test_scheduling_before_init_and_after_exit_rejects_missing_queues(self):
        self.cases('qm-before-init','hif-before-init','qm-after-exit','hif-after-exit','qm-on-after-exit','hif-on-after-exit')

    def test_all_normal_and_cpu_directed_schedulers_use_live_initialized_work(self):
        self.cases('qm-normal-schedule','qm-on-schedule','hif-normal-schedule','hif-on-schedule')

    def test_terminal_stop_quarantine_and_retired_owner_reject_new_work(self):
        self.cases('pci-stop-schedule','pci-quarantine-schedule','tm-stop-refusal','tm-retired-refusal')

    def test_slow_initialization_is_cancelled_or_rejected_after_terminal_stop(self):
        self.cases('qm-allocate-cancel','hif-allocate-cancel','qm-late-stop','hif-late-stop','rbus-allocate-cancel')

    def test_draining_queue_rejects_reinit_duplicate_exit_and_scheduler_admission(self):
        self.cases('qm-drain-admission','hif-drain-admission')

    def test_partial_retirement_preserves_dependencies_and_retry_does_not_destroy_twice(self):
        self.cases('qm-exit-partial-retry','qm-quiesce-partial-retry','hif-exit-partial-retry','hif-quiesce-partial-retry','rollback-drain-retained')

    def test_successful_quiesce_is_idempotent_and_late_generic_exit_only_clears_ops(self):
        self.cases('quiesce-idempotent')

    def test_draining_workers_cannot_requeue_into_detached_queue(self):
        self.cases('worker-requeue-qm','worker-requeue-hif')

    def test_complete_bodies_declarations_and_case_contract_are_bound(self):
        self.assertNotIn('-Wno-unused-function',FLAGS)
        self.assertEqual(set(FLAGS),{'-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror',
                                   '-fno-strict-aliasing','-Wno-unused-parameter',
                                   '-Wno-unused-variable','-Wno-unused-but-set-variable'})
        self.assertEqual(len(h.CASE_NAMES),42)
        self.assertEqual(len(set(h.CASE_NAMES)),42)
        self.assertEqual(set(h.EXPECTED_ROWS),set(h.CASE_NAMES))
        self.assertEqual(set(h.BODY_ORDER),set(h.FUNCTION_SOURCES))
        self.assertEqual(len(h.FUNCTION_SOURCES),33)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        for name,key in h.SOURCE_ONLY_FUNCTION_SOURCES.items():self.assertTrue(h.function(self.texts[key],name))
        self.assertIn(h.declarations(self.texts),self.generated)
        self.assertEqual(len(h.source_declarations(self.texts)),9)
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')
        source=self.directory/'wrong-case';shutil.copyfile(self.binaries[0],source);source.chmod(0o700)
        self.assertEqual(subprocess.run([str(source),'undefined-case'],capture_output=True,timeout=5).returncode,91)
        # Separate native-only TASKLET scenario; not a CMWQ/MIPS case.
        for compiler,label,flags in ((shutil.which('gcc-16')or shutil.which('gcc'),'gnu',[]),
                                     (shutil.which('clang'),'asan',['-fsanitize=address,undefined'])):
            for omitted in (False,True):
                with self.subTest(tasklet_variant=label,missing_subsys_kill=omitted):
                    source=self.directory/('tasklet-'+label+('-missing'if omitted else '')+'.c')
                    source.write_text(tasklet_variant_source(self.texts,omitted));binary=source.with_suffix('')
                    built=subprocess.run([compiler,*FLAGS,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
                    self.assertEqual((built.returncode,built.stderr),(0,''),built.stderr)
                    run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
                    if omitted:self.assertNotEqual(run.returncode,0)
                    else:
                        self.assertEqual((run.returncode,run.stderr),(0,''),run.stderr)
                        self.assertEqual(json.loads(run.stdout),[7,7,127])


    def test_removed_null_stop_retirement_owner_and_dependency_barriers_are_detected(self):
        mutations=(
          ('tm_wq_qm_init','if (!wq) {','if (FALSE) {','qm-oom'),
          ('tm_wq_publish','!RtmpDmaStopping(pAd)) {','TRUE) {','qm-late-stop'),
          ('tm_wq_destroy','if ((*state != TM_WQ_IDLE && *state != TM_WQ_ACTIVE) ||',
           'if (FALSE && ((*state != TM_WQ_IDLE && *state != TM_WQ_ACTIVE) ||','qm-drain-admission'),
          ('tm_quiesce','if (ret == NDIS_STATUS_SUCCESS)\n\t\tpAd->dma_tasks_retired = TRUE;',
           'if (TRUE)\n\t\tpAd->dma_tasks_retired = TRUE;','qm-quiesce-partial-retry'),
          ('tm_exit','if (ret != NDIS_STATUS_SUCCESS)\n\t\treturn ret;','if (FALSE)\n\t\treturn ret;','qm-exit-partial-retry'),
          ('tm_init','pAd->tm_qm_ops = qm_ops;','(void)qm_ops;','rollback-drain-retained'),
          ('tm_exit','if (status != NDIS_STATUS_SUCCESS)\n\t\t\treturn ret;',
           'if (FALSE)\n\t\t\treturn ret;','hif-exit-partial-retry'),
        )
        for index,(name,before,after,selector)in enumerate(mutations):
            with self.subTest(function=name,case=selector):
                body=h.function(self.texts['tm'],name);self.assertEqual(body.count(before),1)
                changed=body.replace(before,after)
                if name=='tm_wq_destroy':
                    changed=changed.replace('((*state == TM_WQ_IDLE) != (*owner == NULL))) {','((*state == TM_WQ_IDLE) != (*owner == NULL)))) {')
                texts=dict(self.texts);texts['tm']=texts['tm'].replace(body,changed)
                source=self.directory/('removed-'+str(index)+'.c');source.write_text(h.generate_source(texts));binary=source.with_suffix('')
                built=subprocess.run([shutil.which('clang'),*FLAGS,'-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
                self.assertEqual((built.returncode,built.stderr),(0,''),built.stderr)
                rejected=subprocess.run([str(binary),selector],capture_output=True,text=True,timeout=10)
                self.assertNotEqual(rejected.returncode,0)

TASKLET_VARIANT_FUNCTIONS = ('rx_done_tasklet','rx1_done_tasklet',
    'mt_mac_recovery_tasklet','mt_mac_fw_own_tasklet','subsys_int_tasklet',
    'tx_dma_done_tasklet','tr_done_tasklet','tm_tasklet_hif_pci_init','tm_tasklet_hif_pci_exit')


def tasklet_variant_source(texts, omit_subsys_kill=False):
    """Native-only variant, separate from42 CMWQ/MIPS cases.

    Tasklet execution/drain is an inert synchronous seam. Whole source
    callbacks/initializer/destructor do not execute the kernel or prove its
    scheduling ABI or current shipping configuration selection.
    """
    prefix=r"""
#include <assert.h>
#include <stdio.h>
#define VOID void
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define ERR_RECOVERY 1
#define CONFIG_FWOWN_SUPPORT 1
#define MULTI_LAYER_INTERRUPT 1
#define HIF_RX_IDX0 0
#define HIF_RX_IDX1 1
typedef int INT;
struct model_tasklet {void (*function)(unsigned long);unsigned long data;int initialized,scheduled,retired;};
struct os_cookie {struct model_tasklet rx_done_task[2],mac_error_recovey_task,mt_mac_fw_own_task,subsys_int_task,tx_dma_done_task,tr_done_task;};
typedef struct os_cookie *POS_COOKIE;
typedef struct _RTMP_ADAPTER {void *OS_Cookie;int alive,callbacks,seen;} RTMP_ADAPTER,*PRTMP_ADAPTER;
static int initialized,killed;
static void model_init(struct model_tasklet *t,void(*fn)(unsigned long),unsigned long data){
 assert(!t->initialized&&fn);t->function=fn;t->data=data;t->initialized=1;t->scheduled=1;initialized++;}
static void model_kill(struct model_tasklet *t){assert(t->initialized&&!t->retired);
 if(t->scheduled){t->function(t->data);t->scheduled=0;}t->retired=1;killed++;}
#define RTMP_OS_TASKLET_INIT(ad,t,fn,data) model_init((t),(fn),(data))
#define RTMP_OS_TASKLET_KILL(t) model_kill(t)
static void backend(RTMP_ADAPTER *ad,int bit){assert(ad->alive);ad->callbacks++;ad->seen|=bit;}
static void rx_done_func(RTMP_ADAPTER *ad){backend(ad,1);}
static void rx1_done_func(RTMP_ADAPTER *ad){backend(ad,2);}
static void mt_mac_recovery_func(RTMP_ADAPTER *ad){backend(ad,4);}
static void mt_mac_fw_own_func(RTMP_ADAPTER *ad){backend(ad,8);}
static void mt_subsys_int_func(RTMP_ADAPTER *ad){backend(ad,16);}
static void tx_dma_done_func(RTMP_ADAPTER *ad){backend(ad,32);}
static void tr_done_func(RTMP_ADAPTER *ad){backend(ad,64);}
"""
    bodies={name:h.function(texts['tm'],name) for name in TASKLET_VARIANT_FUNCTIONS}
    needle='RTMP_OS_TASKLET_KILL(&obj->subsys_int_task);'
    if bodies['tm_tasklet_hif_pci_exit'].count(needle)!=1:
        raise ValueError('Exactly one subsystem tasklet retirement required')
    if omit_subsys_kill:bodies['tm_tasklet_hif_pci_exit']=bodies['tm_tasklet_hif_pci_exit'].replace(needle,'(void)obj;')
    suffix=r"""
int main(void){struct os_cookie cookie={0};RTMP_ADAPTER ad={.OS_Cookie=&cookie,.alive=1};
 struct model_tasklet *tasks[]={&cookie.rx_done_task[0],&cookie.rx_done_task[1],&cookie.mac_error_recovey_task,
 &cookie.mt_mac_fw_own_task,&cookie.subsys_int_task,&cookie.tx_dma_done_task,&cookie.tr_done_task};
 assert(tm_tasklet_hif_pci_init(&ad)==NDIS_STATUS_SUCCESS&&initialized==7);
 assert(tm_tasklet_hif_pci_exit(&ad)==NDIS_STATUS_SUCCESS);
 assert(killed==initialized&&ad.callbacks==7&&ad.seen==127);
 for(unsigned int i=0;i<sizeof(tasks)/sizeof(tasks[0]);i++)assert(tasks[i]->retired&&!tasks[i]->scheduled);
 ad.alive=0;printf("[%d,%d,%d]\n",initialized,killed,ad.seen);return 0;}
"""
    return prefix+'\n'.join(bodies.values())+suffix


if __name__=='__main__':unittest.main()
