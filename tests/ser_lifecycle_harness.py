"""Complete current SER/worker functions with private pthread and inert IO.

One serialized teardown owner may race the SER worker and event producer.
Multiple concurrent teardown owners and hardware DMA quiescence are not modeled.
"""
import hashlib
import re

BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'basic':BASE+'embedded/hw_ctrl/hw_ctrl_basic.c',
 'recovery':BASE+'embedded/hw_ctrl/hw_ctrl.c','command':BASE+'embedded/hw_ctrl/hw_ctrl_cmd.c',
 'os':BASE+'os/linux/rt_linux.c','close':BASE+'embedded/common/rtmp_init_inf.c',
 'header':BASE+'embedded/include/hw_ctrl.h',
 'task_header':BASE+'embedded/include/rtmp_os.h', 'wire_header':BASE+'include/hif/mt_hif_pci.h',
 'flag_header':BASE+'embedded/include/rtmp_def.h', 'os_header':BASE+'include/os/rt_linux.h'}
FUNCTION_SOURCES={'__RtmpOSTaskKill':'os','HwRecoveryFromErrorOwned':'recovery','HwRecoveryFromError':'recovery',
 'ser_ctrl_task':'basic','ser_init':'basic','HwCtrlSerExit':'basic',
 'ser_exit':'basic','RTMP_MAC_RECOVERY':'command'}
BODY_ORDER=('__RtmpOSTaskKill', 'HwRecoveryFromErrorOwned', 'HwRecoveryFromError', 'ser_ctrl_task', 'ser_init', 'HwCtrlSerExit', 'ser_exit', 'RTMP_MAC_RECOVERY')
CASE_NAMES=('hif-failure', 'hif-failure-repeat', 'hif-success', 'recovery-halted', 'recovery-failed-entry', 'producer-running',
 'producer-halted', 'producer-failed', 'producer-stopped', 'stop-normal', 'stop-repeat', 'stop-nonzero-exit',
 'stop-before-owner-release', 'ser-reopen-reset', 'stop-during-recovery', 'ser-stop-failure', 'ser-stop-failure-repeat',
 'ser-idle-failure', 'ser-arm-failure', 'ser-arm-failure-repeat', 'ser-qm-failure', 'ser-tm-failure',
 'recovery-owner-busy', 'recovery-stopping', 'recovery-unpinned')
FIELDS=('result','tm_exits','qm_exits','hif_inits','qm_inits','tm_inits',
 'dma_enables','init_done','queues_retired','recovery_failed','wakeups',
 'joins','task_present','ser_state','lock_live','owner_released','invalid_operations')
EXPECTED_ROWS={'hif-failure': [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0],
 'hif-failure-repeat': [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0],
 'hif-success': [0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'recovery-halted': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'recovery-failed-entry': [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
 'producer-running': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 2, 1, 0, 0],
 'producer-halted': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 1, 0, 0],
 'producer-failed': [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 2, 1, 0, 0],
 'producer-stopped': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 1, 0, 0],
 'stop-normal': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
 'stop-repeat': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
 'stop-nonzero-exit': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
 'stop-before-owner-release': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0],
 'ser-reopen-reset': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0],
 'stop-during-recovery': [0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 1, 0],
 'ser-stop-failure': [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
 'ser-stop-failure-repeat': [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
 'ser-idle-failure': [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
 'ser-arm-failure': [1, 2, 2, 1, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0],
 'ser-arm-failure-repeat': [1, 2, 2, 1, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0],
 'ser-qm-failure': [1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0],
 'ser-tm-failure': [1, 1, 2, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0],
 'recovery-owner-busy': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'recovery-stopping': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'recovery-unpinned': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0]}
PREFIX=r'''
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef void VOID,PKT_TOKEN_CB;typedef int INT,INT32,NDIS_STATUS,NTSTATUS,BOOLEAN;
typedef uint32_t UINT32;typedef unsigned long ULONG;
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_INVALID_DATA 2
#define LINUX
#define RTMP_PCI_SUPPORT
#define KTHREAD_SUPPORT
#define RESOURCE_PRE_ALLOC
#define RTMP_MAC_PCI
#define RTMP_TASK_STAT_UNKNOWN 0
#define RTMP_TASK_STAT_INITED 1
#define RTMP_TASK_STAT_RUNNING 2
#define RTMP_TASK_STAT_STOPED 3
#define fRTMP_ADAPTER_HALT_IN_PROGRESS 1
#define RTMP_TEST_FLAG(p,f) (((p)->flags&(f))!=0)
#define MTWF_LOG(...) ((void)0)
#define os_zero_mem(p,n) memset((p),0,(n))
#define ERROR_DETECT_STOP_PDMA 1
#define ERROR_DETECT_RESET_DONE 2
#define ERROR_DETECT_RECOVERY_DONE 4
#define ERROR_DETECT_N9_NORMAL_STATE 8
#define ERROR_DETECT_MASK 15
#define MCU_INT_PDMA0_STOP_DONE 1
#define MCU_INT_PDMA0_INIT_DONE 2
#define MCU_INT_PDMA0_RECOVERY_DONE 4
#define MT7615
#define IS_MT7615(p) ((void)(p),1)
#define IS_MT7622(p) ((void)(p),0)
#define IS_P18(p) ((void)(p),0)
#define HW_BSSID_0 0
#define MT_WPDMA_MEM_RNG_ERR 0
#define BCN_UPDATE_AP_RENEW 0
#define SER_TIME_ID_T0 0
#define SER_TIME_ID_T1 1
#define SER_TIME_ID_T2 2
#define SER_TIME_ID_T3 3
#define SER_TIME_ID_T4 4
#define SER_TIME_ID_T5 5
#define SER_TIME_ID_T6 6
#define SER_TIME_ID_T7 7
#define SER_TIME_ID_END 8
struct lock {pthread_mutex_t mutex;int live;};
typedef struct OS_TASK {pthread_t thread;pthread_mutex_t mutex;pthread_cond_t cond;
 int killed,event,started;void *kthread_task,*priv;INT (*fn)(ULONG);char taskName[16];} OS_TASK;
typedef OS_TASK RTMP_OS_TASK;
typedef struct HW_CTRL_T {OS_TASK ser_task;struct lock ser_lock;int ser_func_state;
 UINT32 ser_status,ser_times[8];BOOLEAN ser_initialized;} HW_CTRL_T;
typedef struct {pthread_mutex_t dma_lifecycle_lock;} COOKIE,*POS_COOKIE;
typedef struct _RTMP_ADAPTER {void *OS_Cookie;int dma_lifecycle_pinned,dma_stopping;HW_CTRL_T HwCtrl;ERR_RECOVERY_CTRL_T ErrRecoveryCtl;
 int flags;char *net_dev;void *PktTokenCb;int bPCIclkOff;} RTMP_ADAPTER,*PRTMP_ADAPTER;
#define IS_PCI_INF(p) ((void)(p),0)
#define IS_PCIE_INF(p) ((void)(p),1)
#define mutex_trylock(p) (pthread_mutex_trylock(p)==0)
#define mutex_unlock(p) do{assert(!pthread_mutex_unlock(p));}while(0)
static int RtmpDmaStopping(RTMP_ADAPTER *p){return p->dma_stopping||RTMP_TEST_FLAG(p,fRTMP_ADAPTER_HALT_IN_PROGRESS);}
static int tm_exits,qm_exits,hif_inits,qm_inits,tm_inits,dma_enables,init_done,wakeups,joins;
static int hif_status,exit_code,owner_released,invalid;
static int stop_ok=TRUE,arm_ok=TRUE,qm_status,tm_status;
/* Restart reporting/containment recorder; legacy SER rows remain unchanged. */
static int restart_quarantine_reports;
static void RtmpDmaQuarantine(RTMP_ADAPTER *ad){assert(ad);restart_quarantine_reports++;}
static pthread_mutex_t barrier=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t barrier_cond=PTHREAD_COND_INITIALIZER;
static int hold_join,join_entered,allow_join;
static int hold_hif,hif_entered,allow_hif;
static void alloc_lock(struct lock *p){assert(!p->live);assert(!pthread_mutex_init(&p->mutex,NULL));p->live=1;}
static void free_lock(struct lock *p){assert(p->live);assert(!pthread_mutex_destroy(&p->mutex));p->live=0;}
static void lock(struct lock *p){assert(p->live);assert(!pthread_mutex_lock(&p->mutex));}
static void unlock(struct lock *p){assert(!pthread_mutex_unlock(&p->mutex));}
#define NdisAllocateSpinLock(a,p) ((void)(a),alloc_lock(p))
#define NdisFreeSpinLock(p) free_lock(p)
#define NdisAcquireSpinLock(p) lock(p)
#define NdisReleaseSpinLock(p) unlock(p)
#define RTMP_OS_TASK_LEGALITY(p) ((p)->kthread_task!=NULL)
#define RTMP_OS_TASK_DATA_GET(p) ((p)->priv)
#define RTMP_OS_TASK_IS_KILLED(p) ((p)->killed)
#define RTMP_OS_NETDEV_GET_DEVNAME(p) (p)
static int task_init(OS_TASK *t,void *ad){memset(t,0,sizeof(*t));t->priv=ad;
 assert(!pthread_mutex_init(&t->mutex,NULL));assert(!pthread_cond_init(&t->cond,NULL));return NDIS_STATUS_SUCCESS;}
#define RTMP_OS_TASK_INIT(t,n,a) ((void)(n),task_init((t),(a)))
static void *run_task(void *p){OS_TASK *t=p;(void)t->fn((ULONG)t);return NULL;}
static int RtmpOSTaskAttach(OS_TASK *t,INT (*fn)(ULONG),ULONG value){assert(value==(ULONG)t);t->fn=fn;
 t->kthread_task=t;t->started=1;assert(!pthread_create(&t->thread,NULL,run_task,t));return 0;}
static void RtmpOSTaskCustomize(OS_TASK *t){assert(t);}
static int RtmpOSTaskNotifyToExit(OS_TASK *t){assert(t);return 0;}
static int RtmpOSTaskWait(RTMP_ADAPTER *a,OS_TASK *t,int *status){int killed;(void)a;
 assert(!pthread_mutex_lock(&t->mutex));while(!t->event&&!t->killed)assert(!pthread_cond_wait(&t->cond,&t->mutex));
 killed=t->killed;t->event=0;assert(!pthread_mutex_unlock(&t->mutex));*status=killed?-1:0;return !killed;}
static int kthread_stop(void *p){OS_TASK *t=p;joins++;
 assert(!pthread_mutex_lock(&barrier));join_entered=1;assert(!pthread_cond_broadcast(&barrier_cond));
 while(hold_join&&!allow_join) {
  assert(!pthread_cond_wait(&barrier_cond,&barrier));
 }
 assert(!pthread_mutex_unlock(&barrier));
 assert(!pthread_mutex_lock(&t->mutex));t->killed=1;assert(!pthread_cond_broadcast(&t->cond));assert(!pthread_mutex_unlock(&t->mutex));
 assert(!pthread_join(t->thread,NULL));return exit_code;}
struct task_struct;
/* Ref lifetime is tested separately by the complete attach/kill model. */
static void put_task_struct(struct task_struct *p){assert(p);}
static int __RtmpOSTaskKill(OS_TASK *p);
static int RtmpOSTaskKill(OS_TASK *p){return __RtmpOSTaskKill(p);}
static void RTCMDUp(OS_TASK *t){wakeups++;if(t->started){assert(!pthread_mutex_lock(&t->mutex));t->event=1;
 assert(!pthread_cond_broadcast(&t->cond));assert(!pthread_mutex_unlock(&t->mutex));}}
static void tm_exit(RTMP_ADAPTER *a){(void)a;tm_exits++;}
static void qm_exit(RTMP_ADAPTER *a){(void)a;qm_exits++;}
static void RTMPResetTxRxRingMemory(RTMP_ADAPTER *a){(void)a;if(!stop_ok)invalid++;}
static void cut_through_deinit(void *p){(void)p;if(!stop_ok)invalid++;}
static int WfHifInit(RTMP_ADAPTER *a){(void)a;hif_inits++;
 if(hold_hif) {
  assert(!pthread_mutex_lock(&barrier));hif_entered=1;assert(!pthread_cond_broadcast(&barrier_cond));
  while(!allow_hif) {assert(!pthread_cond_wait(&barrier_cond,&barrier));}
  assert(!pthread_mutex_unlock(&barrier));
 }
 return hif_status;}
static int qm_init(RTMP_ADAPTER *a){(void)a;qm_inits++;return qm_status;}
static int tm_init(RTMP_ADAPTER *a){(void)a;tm_inits++;return tm_status;}
static int RT28XXDMAStop(RTMP_ADAPTER *a){(void)a;return stop_ok;}
static int RT28XXDMAEnable(RTMP_ADAPTER *a){(void)a;dma_enables++;return arm_ok;}
#define HIF_IO_WRITE32(a,b,c) ((void)(a),(void)(b),(void)(c))
#define WLAN_HOOK_CALL(a,b,c) ((void)(b),(void)(c))
static void MtAsicGetTsfTimeByDriver(RTMP_ADAPTER *a,UINT32 *h,UINT32 *l,int b){(void)a;(void)b;*h=0;*l=0;}
static int ErrRecoveryCurStat(ERR_RECOVERY_CTRL_T *p){return p->errRecovState;}
static void ErrRecoveryStopPdmaAccessDone(ERR_RECOVERY_CTRL_T *p){p->errRecovState=ERR_RECOV_STOP_IDLE_DONE;}
static void ErrRecoveryStopPdmaAccess(ERR_RECOVERY_CTRL_T *p){p->errRecovState=ERR_RECOV_STOP_PDMA0;}
static void ErrRecoveryReinitPdma(ERR_RECOVERY_CTRL_T *p){p->errRecovState=ERR_RECOV_RESET_PDMA0;}
static void ErrRecoveryWaitN9Normal(ERR_RECOVERY_CTRL_T *p){p->errRecovState=ERR_RECOV_WAIT_N9_NORMAL;}
static void ErrRecoveryDone(ERR_RECOVERY_CTRL_T *p){p->errRecovState=ERR_RECOV_STOP_IDLE;}
static void ErrRecoveryEventReentry(ERR_RECOVERY_CTRL_T *p){p->errRecovState=ERR_RECOV_EVENT_REENTRY;}
static void ErrRecoveryMcuIntEvent(RTMP_ADAPTER *a,int n){(void)a;if(n==MCU_INT_PDMA0_INIT_DONE)init_done++;}
static void RtmpusecDelay(int n){(void)n;}
static void UpdateBeaconHandler(RTMP_ADAPTER *a,void *p,int n){(void)a;(void)p;(void)n;}
static void SerTimeLogDump(RTMP_ADAPTER *a){(void)a;}
static void ErrRecoveryEndDriverRestore(RTMP_ADAPTER *a){(void)a;}
'''
SUFFIX=r'''
static void wait_running(RTMP_ADAPTER *a){int i;struct timespec pause={0,1000000};
 for(i=0;i<2000;i++){int ready;lock(&a->HwCtrl.ser_lock);ready=a->HwCtrl.ser_func_state==RTMP_TASK_STAT_RUNNING;
 unlock(&a->HwCtrl.ser_lock);if(ready)return;nanosleep(&pause,NULL);}abort();}
static void task_destroy(OS_TASK *t){assert(!t->kthread_task);assert(!pthread_cond_destroy(&t->cond));assert(!pthread_mutex_destroy(&t->mutex));}
static void *close_owner(void *p){RTMP_ADAPTER *a=p;a->flags=fRTMP_ADAPTER_HALT_IN_PROGRESS;HwCtrlSerExit(a);assert(!a->HwCtrl.ser_task.kthread_task);
 owner_released=1;return NULL;}
int main(int argc,char **argv){const char *name;RTMP_ADAPTER ad;COOKIE cookie;int result=0,thread_case=0;pthread_t closer;
 assert(argc==2);name=argv[1];CASE_ADMISSION memset(&ad,0,sizeof(ad));memset(&cookie,0,sizeof(cookie));ad.OS_Cookie=&cookie;ad.dma_lifecycle_pinned=1;assert(!pthread_mutex_init(&cookie.dma_lifecycle_lock,NULL));
 alloc_lock(&ad.HwCtrl.ser_lock);
 if(!strncmp(name,"stop-",5)||!strcmp(name,"ser-reopen-reset")) {
  free_lock(&ad.HwCtrl.ser_lock);assert(ser_init(&ad)==NDIS_STATUS_SUCCESS);thread_case=1;wait_running(&ad);
  if(!strcmp(name,"stop-nonzero-exit"))exit_code=-4;
  if(!strcmp(name,"stop-during-recovery")) {
   hold_hif=1;hif_status=1;ad.ErrRecoveryCtl.errRecovState=ERR_RECOV_STOP_PDMA0;
   RTMP_MAC_RECOVERY(&ad,ERROR_DETECT_RESET_DONE);
   assert(!pthread_mutex_lock(&barrier));while(!hif_entered)assert(!pthread_cond_wait(&barrier_cond,&barrier));
   assert(!pthread_mutex_unlock(&barrier));assert(!pthread_create(&closer,NULL,close_owner,&ad));
   assert(!pthread_mutex_lock(&barrier));while(!join_entered)assert(!pthread_cond_wait(&barrier_cond,&barrier));
   assert(!owner_released);allow_hif=1;assert(!pthread_cond_broadcast(&barrier_cond));
   assert(!pthread_mutex_unlock(&barrier));assert(!pthread_join(closer,NULL));
  } else if(!strcmp(name,"stop-before-owner-release")) {
   hold_join=1;assert(!pthread_create(&closer,NULL,close_owner,&ad));
   assert(!pthread_mutex_lock(&barrier));while(!join_entered)assert(!pthread_cond_wait(&barrier_cond,&barrier));
   assert(!owner_released&&ad.HwCtrl.ser_task.kthread_task);allow_join=1;
   assert(!pthread_cond_broadcast(&barrier_cond));assert(!pthread_mutex_unlock(&barrier));assert(!pthread_join(closer,NULL));
  } else HwCtrlSerExit(&ad);
  if(!strcmp(name,"stop-repeat"))HwCtrlSerExit(&ad);
  result=ser_exit(&ad);task_destroy(&ad.HwCtrl.ser_task);
  if(!strcmp(name,"ser-reopen-reset")) {
   ad.ErrRecoveryCtl.recovery_failed=ad.ErrRecoveryCtl.queues_retired=TRUE;
   assert(ser_init(&ad)==NDIS_STATUS_SUCCESS);wait_running(&ad);assert(!ad.ErrRecoveryCtl.recovery_failed&&!ad.ErrRecoveryCtl.queues_retired);
   HwCtrlSerExit(&ad);assert(ser_exit(&ad)==0);task_destroy(&ad.HwCtrl.ser_task);
  }
 } else if(!strncmp(name,"producer-",9)) {
  ad.HwCtrl.ser_func_state=RTMP_TASK_STAT_RUNNING;
  if(!strcmp(name,"producer-halted"))ad.flags=fRTMP_ADAPTER_HALT_IN_PROGRESS;
  if(!strcmp(name,"producer-failed"))ad.ErrRecoveryCtl.recovery_failed=TRUE;
  if(!strcmp(name,"producer-stopped"))ad.HwCtrl.ser_func_state=RTMP_TASK_STAT_STOPED;
  RTMP_MAC_RECOVERY(&ad,ERROR_DETECT_RESET_DONE);
 } else {
  ad.ErrRecoveryCtl.errRecovState=ERR_RECOV_STOP_PDMA0;ad.HwCtrl.ser_status=ERROR_DETECT_RESET_DONE;
  if(!strncmp(name,"hif-failure",11))hif_status=1;
  if(!strcmp(name,"recovery-halted"))ad.flags=fRTMP_ADAPTER_HALT_IN_PROGRESS;
  if(!strcmp(name,"recovery-failed-entry"))ad.ErrRecoveryCtl.recovery_failed=TRUE;
  if(!strncmp(name,"ser-stop-failure",16)||!strcmp(name,"ser-idle-failure"))stop_ok=FALSE;
  if(!strncmp(name,"ser-arm-failure",15))arm_ok=FALSE;
  if(!strcmp(name,"ser-qm-failure"))qm_status=1;
  if(!strcmp(name,"ser-tm-failure"))tm_status=1;
  if(!strcmp(name,"recovery-owner-busy"))assert(!pthread_mutex_lock(&cookie.dma_lifecycle_lock));
  if(!strcmp(name,"recovery-stopping"))ad.dma_stopping=1;
  if(!strcmp(name,"recovery-unpinned"))ad.dma_lifecycle_pinned=0;
  result=HwRecoveryFromError(&ad);
  if(!strcmp(name,"recovery-owner-busy"))assert(!pthread_mutex_unlock(&cookie.dma_lifecycle_lock));
  if(!strcmp(name,"hif-failure-repeat"))result=HwRecoveryFromError(&ad);
  if(strstr(name,"ser-")&&strstr(name,"-repeat"))result=HwRecoveryFromError(&ad);
 }
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",result,tm_exits,qm_exits,
 hif_inits,qm_inits,tm_inits,dma_enables,init_done,ad.ErrRecoveryCtl.queues_retired,ad.ErrRecoveryCtl.recovery_failed,
 wakeups,joins,ad.HwCtrl.ser_task.kthread_task!=NULL,ad.HwCtrl.ser_func_state,ad.HwCtrl.ser_lock.live,owner_released,invalid);
 if(!thread_case) {
  free_lock(&ad.HwCtrl.ser_lock);
 }
 assert(!pthread_mutex_destroy(&cookie.dma_lifecycle_lock));return 0;}
'''


def function(text,name):
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:inline\s+)?(?:VOID|INT|NTSTATUS|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    found=list(re.finditer(pattern,masked,re.M))
    if len(found)!=1:raise ValueError('Missing/ambiguous SER function: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated SER function: '+name)


def declarations(text):
    result=[]
    for name in ('ERR_RECOVERY_STATE','ERR_RECOVERY_CTRL_T'):
        pattern=r'typedef (?:enum|struct) _'+name+r'\s*\{[\s\S]*?\}\s*'+name+r'(?:,\s*\*P_ERR_RECOVERY_STATE)?;'
        found=re.findall(pattern,text)
        if len(found)!=1:raise ValueError('Missing actual SER declaration: '+name)
        result.append(found[0])
    return '\n'.join(result)


def generate_source(texts,variant='current'):
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current SER inputs required')
    names=('ERROR_DETECT_STOP_PDMA_WITH_FW_RELOAD','ERROR_DETECT_STOP_PDMA','ERROR_DETECT_RESET_DONE',
           'ERROR_DETECT_RECOVERY_DONE','ERROR_DETECT_N9_NORMAL_STATE','ERROR_DETECT_LMAC_ERROR',
           'ERROR_DETECT_PSE_ERROR','ERROR_DETECT_PLE_ERROR','ERROR_DETECT_PDMA_ERROR','ERROR_DETECT_PCIE_ERROR',
           'ERROR_DETECT_MASK','MCU_INT_PDMA0_STOP_DONE','MCU_INT_PDMA0_INIT_DONE','MCU_INT_PDMA0_RECOVERY_DONE')
    definitions=['#define BIT(n) (1U<<(n))']
    lines=texts['wire_header'].splitlines(keepends=True)
    for name in names:
        values=[]
        for i,line in enumerate(lines):
            if re.match(r'^#define '+name+r'\b',line):
                block=line
                while block.rstrip().endswith('\\'):
                    i+=1;block+=lines[i]
                values.append(block)
        if not values or len(set(values))!=1:raise ValueError('Actual SER wire macro differs: '+name)
        definitions.append(values[0])
    state=re.findall(r'typedef enum _RTMP_TASK_STATUS_ \{[\s\S]*?\} RTMP_TASK_STATUS;',texts['task_header'])
    halt=re.findall(r'^#define fRTMP_ADAPTER_HALT_IN_PROGRESS\s+0x[0-9a-fA-F]+\s*$',texts['flag_header'],re.M)
    if len(state)!=1 or len(halt)!=1:raise ValueError('Actual task/flag ABI missing')
    definitions+=state+halt
    for name,value in (('SUCCESS',0),('FAILURE',1),('INVALID_DATA',2)):
        found=re.findall(r'^#define NDIS_STATUS_'+name+r'\s+(0x[0-9a-fA-F]+)\s*$',texts['os_header'],re.M)
        if len(found)!=1 or int(found[0],16)!=value:raise ValueError('Actual NDIS status changed: '+name)
    prefix=PREFIX
    for name in (*names,'RTMP_TASK_STAT_UNKNOWN','RTMP_TASK_STAT_INITED','RTMP_TASK_STAT_RUNNING',
                 'RTMP_TASK_STAT_STOPED','fRTMP_ADAPTER_HALT_IN_PROGRESS'):
        prefix=re.sub(r'^#define '+name+r'\b[^\n]*\n','',prefix,flags=re.M)
    prefix=prefix.replace('struct lock {','\n'.join(definitions)+'\n'+declarations(texts['header'])+'\nstruct lock {')
    prefix=prefix.replace('static int __RtmpOSTaskKill(OS_TASK *p);','static inline int __RtmpOSTaskKill(OS_TASK *p);')
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return prefix+'\n'.join(function(texts[key],name)for name,key in FUNCTION_SOURCES.items())+SUFFIX.replace('CASE_ADMISSION',admission)


def function_manifest(texts):
    return {name:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}
            for name,key in FUNCTION_SOURCES.items()}
