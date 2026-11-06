"""Complete HW command owner functions with private queue/task/completion effects.

Native pthread scheduling covers one selected worker/exit race. No kernel thread,
MMIO, real DMA, SER worker, or caller lifetime graph is executed by this model.
"""
import hashlib
import re
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'basic':BASE+'embedded/hw_ctrl/hw_ctrl_basic.c',
 'header':BASE+'embedded/include/hw_ctrl.h','task_header':BASE+'embedded/include/rtmp_os.h',
 'os_header':BASE+'include/os/rt_linux.h','init':BASE+'embedded/common/rtmp_init_inf.c',
 'cmd':BASE+'embedded/hw_ctrl/hw_ctrl_cmd.c','handler':BASE+'embedded/hw_ctrl/hw_ctrl.c',
 'mcu_header':BASE+'include/mcu/mt_cmd.h','os':BASE+'os/linux/rt_main_dev.c',
 'kernel_task':'trunk/linux-4.4.x/kernel/kthread.c'}
FUNCTION_SOURCES={'HwCtrlGetTemperature': 'handler',
 'HwCtrlDequeueCmd': 'basic',
 'free_hwcmd': 'basic',
 'HwCtrlCmdHandler': 'basic',
 'HwCtrlFlagHandler': 'basic',
 'HwCtrlThread': 'basic',
 'HwCtrlExit': 'basic',
 'HwCtrlEnqueueCmd': 'basic',
 'HwCtrlSetFlag': 'basic'}
BODY_ORDER=('HwCtrlGetTemperature',
 'HwCtrlDequeueCmd',
 'free_hwcmd',
 'HwCtrlCmdHandler',
 'HwCtrlFlagHandler',
 'HwCtrlThread',
 'HwCtrlExit',
 'HwCtrlEnqueueCmd',
 'HwCtrlSetFlag')
SOURCE_ONLY_FUNCTION_SOURCES={'HwCtrlValidCmd':'basic','HwCtrlValidFlag':'basic',
 'rtmp_sys_init':'init','rtmp_sys_task_exit':'init','RTMPDrvClose':'init',
 'RTMP_GET_TEMPERATURE':'cmd','RtmpDmaQuarantined':'os','RtmpDmaQuarantine':'os',
 'RtmpDmaStopping':'os','RtmpDmaResourcesMayRelease':'os'}
CASE_NAMES=('node-oom-sync','node-oom-async','payload-oom-sync','payload-oom-async',
 'response-oom','reject-stopped-sync','reject-stopped-async','normal-sync','normal-async',
 'response-complete','response-timeout-queued','null-input','null-response','async-response',
 'exit-before-start','flag-late-stop','flag-after-stop','active-worker-vs-exit',
 'exit-retirement-failure','repeat-exit','command-stop-before-handler','normal-callback',
 'response-handler-failure','response-no-handler','response-exit-before-start',
 'temperature-too-large','temperature-null','temperature-api-failure',
 'exit-without-threadfn','response-exit-without-threadfn','wsys-timeout-queued','wsys-timeout-running',
 'wsys-delayed-producer-stop','wsys-late-ra-async','wsys-terminal-busy',
 'wsys-terminal-close-idle','wsys-terminal-linkdown-idle','wsys-terminal-peerdown-idle',
 'wsys-terminal-quarantined')
FIELDS=('result','allocs','frees','live','locks','completion_init','completion_close',
 'callbacks','flag_callbacks','wakes','kills','quarantined','caller','early_live','stop_join_seen')
EXPECTED_ROWS={'wsys-delayed-producer-stop':[1,4,4,0,0,2,2,1,0,1,1,0,9,0,1],
 'wsys-late-ra-async':[1,2,2,0,0,0,0,0,0,0,1,0,9,0,1],
 'wsys-terminal-busy':[1,2,2,0,0,1,1,0,0,0,1,0,9,0,1],
 'wsys-terminal-close-idle':[0,2,2,0,0,1,1,1,0,1,1,0,9,0,1],
 'wsys-terminal-linkdown-idle':[0,2,2,0,0,1,1,1,0,1,1,0,9,0,1],
 'wsys-terminal-peerdown-idle':[0,2,2,0,0,1,1,1,0,1,1,0,9,0,1],
 'wsys-terminal-quarantined':[1,2,2,0,0,1,1,0,0,0,1,1,9,0,1],
 'wsys-timeout-queued':[1,2,2,0,0,1,1,0,0,1,1,1,9,2,1],
 'wsys-timeout-running':[1,2,2,0,0,1,1,1,0,1,1,1,9,2,1],
 'node-oom-sync': [3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'node-oom-async': [3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'payload-oom-sync': [3, 1, 1, 0, 0, 1, 1, 0, 0, 0, 1, 0, 9, 0, 1],
 'payload-oom-async': [3, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'response-oom': [3, 2, 2, 0, 0, 1, 1, 0, 0, 0, 1, 0, 9, 0, 1],
 'reject-stopped-sync': [1, 2, 2, 0, 0, 1, 1, 0, 0, 0, 1, 0, 9, 0, 1],
 'reject-stopped-async': [1, 2, 2, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'normal-sync': [0, 2, 2, 0, 0, 1, 1, 1, 0, 1, 1, 0, 9, 0, 1],
 'normal-async': [0, 2, 2, 0, 0, 0, 0, 1, 0, 1, 1, 0, 9, 2, 1],
 'response-complete': [0, 3, 3, 0, 0, 1, 1, 1, 0, 1, 1, 0, 77, 0, 1],
 'response-timeout-queued': [1, 3, 3, 0, 0, 1, 1, 1, 0, 1, 1, 0, 123, 3, 1],
 'null-input': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'null-response': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'async-response': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'exit-before-start': [0, 2, 2, 0, 0, 0, 0, 0, 0, 1, 1, 0, 9, 2, 1],
 'flag-late-stop': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'flag-after-stop': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'active-worker-vs-exit': [0, 4, 4, 0, 0, 0, 0, 1, 0, 2, 1, 0, 9, 0, 1],
 'exit-retirement-failure': [0, 2, 2, 0, 0, 0, 0, 0, 0, 1, 2, 1, 9, 2, 1],
 'repeat-exit': [0, 2, 2, 0, 0, 0, 0, 1, 0, 1, 1, 0, 9, 2, 1],
 'command-stop-before-handler': [1, 2, 2, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'normal-callback': [0, 2, 2, 0, 0, 0, 0, 1, 1, 1, 1, 0, 9, 2, 1],
 'response-handler-failure': [3, 3, 3, 0, 0, 1, 1, 1, 0, 1, 1, 0, 9, 0, 1],
 'response-no-handler': [1, 3, 3, 0, 0, 1, 1, 0, 0, 1, 1, 0, 9, 0, 1],
 'response-exit-before-start': [1, 3, 3, 0, 0, 1, 1, 0, 0, 1, 1, 0, 9, 0, 1],
 'temperature-too-large': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'temperature-null': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'temperature-api-failure': [3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 9, 0, 1],
 'exit-without-threadfn': [0, 2, 2, 0, 0, 0, 0, 0, 0, 1, 1, 0, 9, 2, 1],
 'response-exit-without-threadfn': [1, 3, 3, 0, 0, 1, 1, 0, 0, 1, 1, 0, 9, 0, 1]}
SOURCE_DECLARATIONS={
 r'enum \{\n\tHWCMD_ID_FIRST[\s\S]*?\n\};':'header',
 r'enum \{\n\tHWCMD_TYPE_FIRST[\s\S]*?\n\};':'header',
 r'typedef struct _HwCmdQElmt \{[\s\S]*?\} HwCmdQElmt, \*PHwCmdQElmt;':'header',
 r'typedef struct _HwCmdQ \{[\s\S]*?\} HwCmdQ, \*PHwCmdQ;':'header',
 r'typedef struct _HwFlagCtrl \{[\s\S]*?\} HwFlagCtrl, \*PHwFlagCtrl;':'header',
 r'typedef struct _HW_CTRL_TXD \{[\s\S]*?\} HW_CTRL_TXD;':'header',
 r'typedef struct _HWCTRL_OP \{[\s\S]*?\} HWCTRL_OP;':'header',
 r'typedef struct _HW_CTRL_T \{[\s\S]*?\} HW_CTRL_T;':'header',
 r'typedef enum _RTMP_TASK_STATUS_ \{[\s\S]*?\} RTMP_TASK_STATUS;':'task_header',
 r'^#define RTMP_TASK_CAN_DO_INSERT[^\n]*':'task_header',
 r'^#define HWCTRL_CMD_TIMEOUT[^\n]*':'header',
 r'^INT32 MtCmdGetThermalSensorResult\(struct _RTMP_ADAPTER \*pAd, UINT8 ActionIdx, UINT32 \*SensorResult\);':'mcu_header'}
STATUS_DECLARATIONS={'^#define NDIS_STATUS_SUCCESS\\s+(0x[0-9a-fA-F]+)\\s*$': 0,
 '^#define NDIS_STATUS_FAILURE\\s+(0x[0-9a-fA-F]+)\\s*$': 1,
 '^#define NDIS_STATUS_RESOURCES\\s+(0x[0-9a-fA-F]+)\\s*$': 3}
MODEL_BOUNDARY={'native_pthread_one_selected_worker_exit_race':True,
 'selected_native_delayed_Wsys_producer_vs_terminal_barrier':True,
 'kernel_thread_or_DMA_executed':False,'SER_hooks_are_inert':True,
 'external_raw_adapter_callers_are_not_proven_drained':True,
 'callback_argument_borrowing_not_generalized':True,
 'only_one_serialized_teardown_owner':True,
 'kernel_threadfn_skip_is_source_bound_inert_schedule':True,
 'all_functions_whole_current_bodies':True}
PREFIX=r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#define TRUE 1
#define FALSE 0
#define ERR_RECOVERY
#define SER_TIME_ID_END 8
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_RESOURCES 3
#define MTWF_LOG(...) ((void)0)
#define RTMPMsecsToJiffies(n) (n)
#define fRTMP_ADAPTER_NIC_NOT_EXIST 1
#define fRTMP_ADAPTER_START_UP 2
#define fRTMP_ADAPTER_HALT_IN_PROGRESS 4
#define RTMP_TEST_FLAG(a,f) ((a)->flags&(f))
#define RTMP_SET_FLAG(a,f) ((a)->flags|=(f))
#define RTMP_OS_TASK_LEGALITY(t) ((t)->kthread_task!=NULL)
#define RTMP_OS_TASK_DATA_GET(t) ((t)->priv)
#define READ_ONCE(v) __atomic_load_n(&(v),__ATOMIC_ACQUIRE)
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define NdisZeroMemory(p,n) memset((p),0,(n))
#define os_move_mem(p,s,n) memmove((p),(s),(n))
typedef void VOID;typedef unsigned char UCHAR,*PUCHAR,UINT8;typedef uint32_t UINT32;
typedef unsigned long ULONG;typedef int INT,INT32,NDIS_STATUS,NTSTATUS,BOOLEAN;
typedef struct {int refs;} os_kref;
typedef struct {pthread_mutex_t mutex;int initialized;} NDIS_SPIN_LOCK;
typedef struct {int initialized,done;} RTMP_OS_COMPLETION;
typedef struct {void *kthread_task,*priv;int killed;} RTMP_OS_TASK;
struct _RTMP_ADAPTER;struct WIFI_SYS_CTRL;
typedef NTSTATUS(*HwCmdCb)(struct _RTMP_ADAPTER*,VOID*);
typedef NTSTATUS(*HwCmdHdlr)(struct _RTMP_ADAPTER*,void*);
typedef NTSTATUS(*HwFlagHdlr)(struct _RTMP_ADAPTER*);
SOURCE_DEFINITIONS
typedef struct _RTMP_ADAPTER {HW_CTRL_T HwCtrl;int flags,quarantined,stopping,release_allowed;} RTMP_ADAPTER,*PRTMP_ADAPTER;
static int allocs,frees,live,attempts,fail_at,locks,completion_init,completion_close;
static int callbacks,flag_callbacks,wakes,kills,process_on_wait,kill_fail,early_live,stop_join_seen;
static int thread_created,block_handler,handler_entered,release_handler,exit_join_entered,worker_ready;
static pthread_t worker,producer;
static int delayed_publish,producer_started,start_producer,producer_paused,release_producer;
static pthread_mutex_t schedule_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t schedule_cond=PTHREAD_COND_INITIALIZER;
static int wake_budget,sensor_fail,no_handler,skip_threadfn;
static RTMP_ADAPTER *active;
static void lock_create(NDIS_SPIN_LOCK *p){assert(!p->initialized);assert(!pthread_mutex_init(&p->mutex,NULL));p->initialized=1;__sync_add_and_fetch(&locks,1);}
static void lock_delete(NDIS_SPIN_LOCK *p){assert(p->initialized);assert(!pthread_mutex_destroy(&p->mutex));p->initialized=0;__sync_sub_and_fetch(&locks,1);}
#define NdisAllocateSpinLock(a,p) ((void)(a),lock_create(p))
#define NdisFreeSpinLock(p) lock_delete(p)
static void lock_acquire(NDIS_SPIN_LOCK *p){assert(p->initialized);
 if(delayed_publish&&pthread_equal(pthread_self(),producer)){
  pthread_mutex_lock(&schedule_lock);producer_paused=1;pthread_cond_broadcast(&schedule_cond);
  while(!release_producer){pthread_cond_wait(&schedule_cond,&schedule_lock);}
  pthread_mutex_unlock(&schedule_lock);
 }
 assert(!pthread_mutex_lock(&p->mutex));}
#define NdisAcquireSpinLock(p) lock_acquire(p)
#define NdisReleaseSpinLock(p) do{assert((p)->initialized);assert(!pthread_mutex_unlock(&(p)->mutex));}while(0)
static NDIS_STATUS os_alloc_mem(RTMP_ADAPTER *ad,PUCHAR *out,size_t n){void *allocation=NULL;(void)ad;attempts++;memcpy(out,&allocation,sizeof(allocation));if(attempts==fail_at)return 3;allocation=malloc(n);assert(allocation);memcpy(out,&allocation,sizeof(allocation));allocs++;live++;return 0;}
static void os_free_mem(void *p){assert(p);__sync_add_and_fetch(&frees,1);__sync_sub_and_fetch(&live,1);free(p);}
static void os_kref_init(os_kref *p){assert(!p->refs);p->refs=1;}
static void os_kref_get(os_kref *p){assert(p->refs>0);__sync_add_and_fetch(&p->refs,1);}
static int os_kref_put(os_kref *p,void(*fn)(os_kref*)){assert(p->refs>0);if(!__sync_sub_and_fetch(&p->refs,1)){fn(p);return 1;}return 0;}
static void init_completion(RTMP_OS_COMPLETION *p){assert(!p->initialized);p->initialized=1;completion_init++;}
static void exit_completion(RTMP_OS_COMPLETION *p){assert(p->initialized);p->initialized=0;__sync_add_and_fetch(&completion_close,1);}
#define RTMP_OS_INIT_COMPLETION(p) init_completion(p)
#define RTMP_OS_EXIT_COMPLETION(p) exit_completion(p)
#define RTMP_OS_COMPLETE(p) do{assert((p)->initialized);(p)->done=1;}while(0)
static VOID HwCtrlCmdHandler(RTMP_ADAPTER*);
static VOID HwCtrlExit(RTMP_ADAPTER*);
static NTSTATUS HwCtrlGetTemperature(RTMP_ADAPTER*,HwCmdQElmt*);
INT32 MtCmdGetThermalSensorResult(RTMP_ADAPTER *ad,UINT8 action,UINT32 *value){assert(ad==active&&!action);if(sensor_fail)return 3;*value=77;return 0;}
static INT HwCtrlThread(ULONG);
static int wait_completion(RTMP_OS_COMPLETION *p,UINT32 timeout){assert(timeout&&p->initialized);if(process_on_wait==1)HwCtrlCmdHandler(active);else if(process_on_wait==2)HwCtrlExit(active);else if(process_on_wait==3){pthread_mutex_lock(&schedule_lock);while(!handler_entered)pthread_cond_wait(&schedule_cond,&schedule_lock);pthread_mutex_unlock(&schedule_lock);return 0;}return p->done;}
#define RTMP_OS_WAIT_FOR_COMPLETION_TIMEOUT(p,n) wait_completion((p),(n))
static void RTCMDUp(RTMP_OS_TASK *task){(void)task;pthread_mutex_lock(&schedule_lock);wakes++;wake_budget++;pthread_cond_broadcast(&schedule_cond);pthread_mutex_unlock(&schedule_lock);}
static void RtmpOSTaskCustomize(RTMP_OS_TASK *task){assert(task->priv==active);}
static int RtmpOSTaskWait(RTMP_ADAPTER *ad,RTMP_OS_TASK *task,int *status){if(task->killed)assert(ad->HwCtrl.HwCtrlQ.CmdQState==RTMP_TASK_STAT_STOPED);*status=0;pthread_mutex_lock(&schedule_lock);worker_ready=1;pthread_cond_broadcast(&schedule_cond);while(!wake_budget&&!task->killed)pthread_cond_wait(&schedule_cond,&schedule_lock);if(task->killed){pthread_mutex_unlock(&schedule_lock);return 0;}wake_budget--;pthread_mutex_unlock(&schedule_lock);return 1;}
static int RtmpOSTaskNotifyToExit(RTMP_OS_TASK *task){assert(task->priv==active);return 0;}
static void HwCtrlSerExit(RTMP_ADAPTER *ad){assert(ad==active);}
static INT ser_exit(RTMP_ADAPTER *ad){assert(ad==active);return 0;}
static void RtmpDmaQuarantine(RTMP_ADAPTER *ad){ad->quarantined=1;ad->flags&=~fRTMP_ADAPTER_START_UP;}
static void require_publication_lock(RTMP_ADAPTER *ad){int rc=pthread_mutex_trylock(&ad->HwCtrl.HwCtrlQLock.mutex);if(!rc)pthread_mutex_unlock(&ad->HwCtrl.HwCtrlQLock.mutex);assert(rc==EBUSY);}
static int __attribute__((unused)) RtmpDmaStopping(RTMP_ADAPTER *ad){require_publication_lock(ad);return ad->stopping||ad->quarantined;}
static int __attribute__((unused)) RtmpDmaResourcesMayRelease(RTMP_ADAPTER *ad){require_publication_lock(ad);return ad->release_allowed&&!ad->quarantined;}

static int RtmpOSTaskKill(RTMP_OS_TASK *task){kills++;assert(active->HwCtrl.HwCtrlQ.CmdQState==RTMP_TASK_STAT_STOPED);stop_join_seen=1;if(kill_fail)return 1;
 pthread_mutex_lock(&schedule_lock);task->killed=1;exit_join_entered=1;pthread_cond_broadcast(&schedule_cond);pthread_mutex_unlock(&schedule_lock);
 if(thread_created){assert(!pthread_join(worker,NULL));thread_created=0;}else if(!skip_threadfn) HwCtrlThread((ULONG)task);
 task->kthread_task=NULL;return 0;}
static NTSTATUS command_handler(RTMP_ADAPTER *ad,void *ptr){HwCmdQElmt *cmd=ptr;assert(ad==active);callbacks++;
 if(block_handler){pthread_mutex_lock(&schedule_lock);handler_entered=1;pthread_cond_broadcast(&schedule_cond);while(!release_handler)pthread_cond_wait(&schedule_cond,&schedule_lock);pthread_mutex_unlock(&schedule_lock);}
 if(cmd->RspBufferLen){return HwCtrlGetTemperature(ad,cmd);}
 return 0;}
static HwCmdHdlr HwCtrlValidCmd(HwCmdQElmt *cmd){assert(cmd);return no_handler?NULL:command_handler;}
static NTSTATUS flag_handler(RTMP_ADAPTER *ad){assert(ad==active);flag_callbacks++;return 0;}
static HwFlagHdlr HwCtrlValidFlag(PHwFlagCtrl flag){assert(flag->FlagId);flag->FlagId=0;return flag_handler;}
static NTSTATUS callback(RTMP_ADAPTER *ad,void *arg){assert(ad==active&&arg==(void*)(uintptr_t)11);flag_callbacks++;return 0;}
'''
SUFFIX=r'''
static void *worker_entry(void *p){HwCtrlThread((ULONG)p);return NULL;}
struct producer_job {RTMP_ADAPTER *ad;HW_CTRL_TXD tx;int result;};
static void *producer_entry(void *p){struct producer_job *job=p;pthread_mutex_lock(&schedule_lock);producer_started=1;pthread_cond_broadcast(&schedule_cond);while(!start_producer)pthread_cond_wait(&schedule_cond,&schedule_lock);pthread_mutex_unlock(&schedule_lock);job->result=HwCtrlEnqueueCmd(job->ad,job->tx);return NULL;}

static void *exit_entry(void *p){HwCtrlExit(p);return NULL;}
int main(int argc,char **argv){const char *name;RTMP_ADAPTER ad;HW_CTRL_TXD tx;UINT32 input=12,caller=9;int result=0;HwCmdQElmt direct;pthread_t closer;assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&ad,0,sizeof(ad));memset(&tx,0,sizeof(tx));active=&ad;ad.flags=fRTMP_ADAPTER_START_UP;ad.HwCtrl.HwCtrlQ.CmdQState=RTMP_TASK_STAT_RUNNING;ad.HwCtrl.HwCtrlTask.priv=&ad;ad.HwCtrl.HwCtrlTask.kthread_task=&ad.HwCtrl.HwCtrlTask;lock_create(&ad.HwCtrl.HwCtrlQLock);
 tx.pInformationBuffer=&input;tx.InformationBufferLength=sizeof(input);tx.NeedWait=(strstr(name,"sync")!=NULL&&strstr(name,"async")==NULL)||strstr(name,"response")!=NULL;
 if(strstr(name,"response")){tx.RespBufferLength=sizeof(caller);tx.pRespBuffer=&caller;}
 if(!strncmp(name,"node-oom",8))fail_at=1;
 if(!strncmp(name,"payload-oom",11))fail_at=2;
 if(!strcmp(name,"response-oom"))fail_at=3;
 if(!strcmp(name,"wsys-late-ra-async")||!strncmp(name,"wsys-terminal-",14)){
  tx.CmdType=HWCMD_TYPE_WIFISYS;ad.stopping=1;ad.release_allowed=strstr(name,"-idle")!=NULL;tx.NeedWait=TRUE;process_on_wait=1;
  tx.CmdId=strstr(name,"linkdown")?HWCMD_ID_WIFISYS_LINKDOWN:(strstr(name,"peerdown")?HWCMD_ID_WIFISYS_PEER_LINKDOWN:HWCMD_ID_WIFISYS_CLOSE);
  if(!strcmp(name,"wsys-late-ra-async")){tx.CmdId=HWCMD_ID_WIFISYS_PEER_UPDATE;tx.NeedWait=FALSE;}
  if(!strcmp(name,"wsys-terminal-quarantined"))ad.quarantined=1;
 }

 if(!strncmp(name,"wsys-timeout-",13)){tx.NeedWait=TRUE;tx.CmdType=HWCMD_TYPE_WIFISYS;}
 if(!strncmp(name,"reject-stopped",14)||!strcmp(name,"command-stop-before-handler"))ad.HwCtrl.HwCtrlQ.CmdQState=RTMP_TASK_STAT_STOPED;
 if(!strcmp(name,"null-input"))tx.pInformationBuffer=NULL;
 if(!strcmp(name,"null-response"))tx.pRespBuffer=NULL;
 if(!strcmp(name,"async-response"))tx.NeedWait=FALSE;
 if(!strcmp(name,"normal-sync")||!strcmp(name,"response-complete"))process_on_wait=1;
 if(!strcmp(name,"response-handler-failure"))sensor_fail=1;
 if(!strcmp(name,"response-no-handler"))no_handler=1;
 if(!strcmp(name,"response-handler-failure")||!strcmp(name,"response-no-handler"))process_on_wait=1;
 if(!strcmp(name,"response-exit-before-start")||!strcmp(name,"response-exit-without-threadfn"))process_on_wait=2;
 if(strstr(name,"without-threadfn"))skip_threadfn=1;
 if(!strcmp(name,"normal-callback")){tx.CallbackFun=callback;tx.CallbackArgs=(void*)(uintptr_t)11;}
 if(!strncmp(name,"temperature-",12)){
  memset(&direct,0,sizeof(direct));direct.RspBuffer=&caller;direct.RspBufferLen=sizeof(caller);
  if(!strcmp(name,"temperature-too-large"))direct.RspBufferLen=sizeof(caller)*2;
  if(!strcmp(name,"temperature-null"))direct.RspBuffer=NULL;
  if(!strcmp(name,"temperature-api-failure"))sensor_fail=1;
  result=HwCtrlGetTemperature(&ad,&direct);assert(caller==9);
 }else if(!strcmp(name,"flag-late-stop")||!strcmp(name,"flag-after-stop")){
  ad.HwCtrl.HwCtrlQ.CmdQState=RTMP_TASK_STAT_STOPED;
  if(!strcmp(name,"flag-late-stop"))result=HwCtrlSetFlag(&ad,1);
  else{ad.HwCtrl.HwCtrlFlag.FlagId=1;ad.HwCtrl.HwCtrlFlag.IsFlagSet=1;HwCtrlFlagHandler(&ad);}
 }else if(!strcmp(name,"wsys-delayed-producer-stop")){
  struct producer_job job={&ad,tx,99};job.tx.CmdType=HWCMD_TYPE_WIFISYS;job.tx.CmdId=HWCMD_ID_WIFISYS_OPEN;job.tx.NeedWait=TRUE;delayed_publish=1;
  assert(!pthread_create(&producer,NULL,producer_entry,&job));pthread_mutex_lock(&schedule_lock);while(!producer_started)pthread_cond_wait(&schedule_cond,&schedule_lock);start_producer=1;pthread_cond_broadcast(&schedule_cond);while(!producer_paused)pthread_cond_wait(&schedule_cond,&schedule_lock);pthread_mutex_unlock(&schedule_lock);
  ad.stopping=1;ad.release_allowed=1;tx.CmdType=HWCMD_TYPE_WIFISYS;tx.CmdId=HWCMD_ID_WIFISYS_CLOSE;tx.NeedWait=TRUE;process_on_wait=1;assert(HwCtrlEnqueueCmd(&ad,tx)==0&&callbacks==1);
  pthread_mutex_lock(&schedule_lock);release_producer=1;pthread_cond_broadcast(&schedule_cond);pthread_mutex_unlock(&schedule_lock);assert(!pthread_join(producer,NULL));result=job.result;early_live=live;assert(result==1&&callbacks==1&&!ad.HwCtrl.HwCtrlQ.size&&live==0);
 }else if(!strcmp(name,"wsys-timeout-running")){
  ad.HwCtrl.HwCtrlQ.CmdQState=RTMP_TASK_STAT_INITED;block_handler=1;process_on_wait=3;thread_created=1;assert(!pthread_create(&worker,NULL,worker_entry,&ad.HwCtrl.HwCtrlTask));
  pthread_mutex_lock(&schedule_lock);while(!worker_ready)pthread_cond_wait(&schedule_cond,&schedule_lock);pthread_mutex_unlock(&schedule_lock);
  result=HwCtrlEnqueueCmd(&ad,tx);early_live=live;assert(result==1&&ad.quarantined&&callbacks==1&&live==2);
  pthread_mutex_lock(&schedule_lock);release_handler=1;pthread_cond_broadcast(&schedule_cond);pthread_mutex_unlock(&schedule_lock);
 }else if(!strcmp(name,"active-worker-vs-exit")){
  ad.HwCtrl.HwCtrlQ.CmdQState=RTMP_TASK_STAT_INITED;block_handler=1;thread_created=1;assert(!pthread_create(&worker,NULL,worker_entry,&ad.HwCtrl.HwCtrlTask));
  pthread_mutex_lock(&schedule_lock);while(!worker_ready)pthread_cond_wait(&schedule_cond,&schedule_lock);pthread_mutex_unlock(&schedule_lock);
  assert(HwCtrlEnqueueCmd(&ad,tx)==0);pthread_mutex_lock(&schedule_lock);while(!handler_entered)pthread_cond_wait(&schedule_cond,&schedule_lock);pthread_mutex_unlock(&schedule_lock);
  assert(HwCtrlEnqueueCmd(&ad,tx)==0);assert(!pthread_create(&closer,NULL,exit_entry,&ad));pthread_mutex_lock(&schedule_lock);while(!exit_join_entered&&callbacks==1)pthread_cond_wait(&schedule_cond,&schedule_lock);assert(callbacks==1);release_handler=1;pthread_cond_broadcast(&schedule_cond);pthread_mutex_unlock(&schedule_lock);assert(!pthread_join(closer,NULL));assert(callbacks==1&&locks==0&&live==0);
 }else{
  result=HwCtrlEnqueueCmd(&ad,tx);early_live=live;
  if(!strcmp(name,"response-timeout-queued")){assert(result==1&&caller==9&&ad.HwCtrl.HwCtrlQ.head->RspBuffer!=&caller);caller=123;HwCtrlCmdHandler(&ad);assert(caller==123);}
  else if(!strcmp(name,"exit-before-start")||!strcmp(name,"exit-without-threadfn")){ad.HwCtrl.HwCtrlQ.CmdQState=RTMP_TASK_STAT_INITED;HwCtrlExit(&ad);assert(callbacks==0);}
  else if(!strcmp(name,"exit-retirement-failure")){kill_fail=1;HwCtrlExit(&ad);assert(ad.quarantined&&locks>=1&&live==early_live);kill_fail=0;}
  else if(!strcmp(name,"command-stop-before-handler")){assert(result==1);}
  else if(ad.HwCtrl.HwCtrlQ.size)HwCtrlCmdHandler(&ad);
 }
 if(locks){HwCtrlExit(&ad);if(!strcmp(name,"repeat-exit"))HwCtrlExit(&ad);}
 assert(live==0&&locks==0&&completion_init==completion_close&&!ad.HwCtrl.HwCtrlTask.kthread_task);
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%u,%d,%d]\n",result,allocs,frees,live,locks,completion_init,completion_close,callbacks,flag_callbacks,wakes,kills,ad.quarantined,caller,early_live,stop_join_seen);return 0;}
'''


def function(text,name):
 token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
 masked=re.sub(token,lambda m:' '*len(m.group()),text)
 pattern=r'^(?:static\s+)?(?:inline\s+)?(?:INT|INT32|UINT32|NDIS_STATUS|NTSTATUS|BOOLEAN|VOID|void|HwCmdHdlr|HwFlagHdlr)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
 found=list(re.finditer(pattern,masked,re.M))
 if len(found)!=1:raise ValueError('Missing or ambiguous hwcmd owner function: '+name)
 start=found[0].start();opening=masked.index('{',start);depth=0
 for match in re.finditer(token+r'|[{}]',text[opening:]):
  if match.group()=='{':depth+=1
  elif match.group()=='}':
   depth-=1
   if not depth:return text[start:opening+match.end()]
 raise ValueError('Unterminated hwcmd owner function: '+name)


def source_declarations(texts):
 result={}
 for pattern,value in STATUS_DECLARATIONS.items():
  rows=list(re.finditer(pattern,texts['os_header'],re.M))
  if len(rows)!=1 or int(rows[0].group(1),16)!=value:raise ValueError('Actual hwcmd status differs: '+pattern)
  result[pattern]={'source':'os_header','sha256':hashlib.sha256(rows[0].group().encode()).hexdigest()}
 for pattern,key in SOURCE_DECLARATIONS.items():
  rows=list(re.finditer(pattern,texts[key],re.M))
  if len(rows)!=1:raise ValueError('Actual hwcmd declaration missing: '+pattern)
  result[pattern]={'source':key,'sha256':hashlib.sha256(rows[0].group().encode()).hexdigest()}
 return result


def function_manifest(texts):
 return {n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}


def source_only_function_manifest(texts):
 return {n:hashlib.sha256(function(texts[k],n).encode()).hexdigest()for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}


def generate_source(texts,variant='current'):
 if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current hwcmd owner sources required')
 source_declarations(texts);source_only_function_manifest(texts)
 definitions='\n'.join(re.search(p,texts[k],re.M).group()for p,k in SOURCE_DECLARATIONS.items())
 admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
 return PREFIX.replace('SOURCE_DEFINITIONS',definitions)+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)
