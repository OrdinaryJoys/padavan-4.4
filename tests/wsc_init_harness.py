"""Defensive WSC-enabled variant model; WSC is disabled in current K2P.

Complete worker/control-release functions run over private task/timer recorders.
No kernel task, timer, file or hardware executes. Parent init order is source-only.
"""
import hashlib
import re
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'wsc':BASE+'embedded/common/wsc.c','sys':BASE+'embedded/common/rtmp_init_inf.c',
 'mgmt':BASE+'os/linux/rt_rbus_pci_drv.c','adapter':BASE+'embedded/common/rtmp_init.c',
 'rtmp_header':BASE+'embedded/include/rtmp.h','wsc_header':BASE+'embedded/include/wsc.h',
 'os_header':BASE+'include/os/rt_linux.h'}
FUNCTION_SOURCES={'wsc_release_initialized_timer':'wsc','WscThreadStop':'wsc',
 'WscThreadExit':'wsc','WscThreadInit':'wsc','rtmp_cfg_exit':'sys'}
SOURCE_ONLY_FUNCTION_SOURCES={'rtmp_sys_init':'sys','rtmp_sys_task_exit':'sys',
 'RTMPDrvClose':'sys','RtmpMgmtTaskInit':'mgmt','RtmpMgmtTaskExit':'mgmt',
 'UserCfgInit':'adapter','WscUUIDInit':'wsc'}
BODY_ORDER=('wsc_release_initialized_timer','WscThreadStop','WscThreadExit','WscThreadInit','rtmp_cfg_exit')
SOURCE_DECLARATIONS={}
CASE_NAMES=('wsc-hmac-oom','wsc-element-oom','wsc-task-init-failure','wsc-task-attach-failure',
 'wsc-normal','wsc-repeat-owner','wsc-partial-owner','wsc-natural-exit','wsc-stop-repeat','wsc-reopen',
 'cfg-no-owner','cfg-worker-only','cfg-ap-owned','cfg-apcli-unbuilt','cfg-apcli-owned',
 'cfg-partial-buffers','cfg-invalid-timers','cfg-repeated-exit','cfg-worker-and-controls','cfg-user-exit-order')
FIELDS=('result','preserved','retry_result','final_allocations','final_locks','final_tasks',
 'final_timers','invalid_operations')
EXPECTED_ROWS={
 'wsc-hmac-oom':[3,1,0,0,0,0,0,0],'wsc-element-oom':[3,1,0,0,0,0,0,0],
 'wsc-task-init-failure':[3,1,0,0,0,0,0,0],'wsc-task-attach-failure':[3,1,0,0,0,0,0,0],
 'wsc-normal':[0,1,-1,0,0,0,0,0],'wsc-repeat-owner':[1,1,-1,0,0,0,0,0],
 'wsc-partial-owner':[1,1,-1,0,0,0,0,0],'wsc-natural-exit':[0,1,-1,0,0,0,0,0],
 'wsc-stop-repeat':[0,1,-1,0,0,0,0,0],'wsc-reopen':[0,1,0,0,0,0,0,0],
 'cfg-no-owner':[1,1,-1,0,0,0,0,0],'cfg-worker-only':[1,1,-1,0,0,0,0,0],
 'cfg-ap-owned':[1,1,-1,0,0,0,0,0],'cfg-apcli-unbuilt':[1,1,-1,0,0,0,0,0],
 'cfg-apcli-owned':[1,1,-1,0,0,0,0,0],'cfg-partial-buffers':[1,1,-1,0,0,0,0,0],
 'cfg-invalid-timers':[1,1,-1,0,0,0,0,0],'cfg-repeated-exit':[1,1,-1,0,0,0,0,0],
 'cfg-worker-and-controls':[1,1,-1,0,0,0,0,0],'cfg-user-exit-order':[1,1,-1,0,0,0,0,0]}
PREFIX=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void VOID;typedef int BOOLEAN,INT,NDIS_STATUS;typedef unsigned char UCHAR;
typedef unsigned long ULONG;typedef struct {int Valid;void *timer_lock;} RALINK_TIMER_STRUCT;
typedef struct {int MsgLen;UCHAR Msg[32];} MLME_QUEUE_ELEM;
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_RESOURCES 3
#define TRUE 1
#define FALSE 0
#define WSC_INCLUDED
#define CONFIG_AP_SUPPORT
#define APCLI_SUPPORT
#define WSC_V2_SUPPORT
#define MAX_APCLI_NUM 2
#define OPMODE_AP 1
#define MAX_MBSSID_NUM(p) ((void)(p),2)
typedef struct {void *kthread_task,*priv;} RTMP_OS_TASK;
typedef struct {int WscPeerListInitialized,WscPeerListSemLock,WscPeerList;
 RALINK_TIMER_STRUCT EapolTimer,Wsc2MinsTimer,M2DTimer,WscUpdatePortCfgTimer,WscSetupLockTimer;
 RALINK_TIMER_STRUCT WscPBCTimer,WscScanTimer,WscProfileRetryTimer;
 struct {RALINK_TIMER_STRUCT UPnPMsgTimer;} WscUPnPNodeInfo;
 int WscRxBufLen,WscTxBufLen,WscSetupLockTimerRunning;void *pWscRxBuf,*pWscTxBuf;
 struct {struct {void *pTlvData;} ExtraTlv;} WscV2Info;
} WSC_CTRL,*PWSC_CTRL;
typedef struct {struct {WSC_CTRL WscControl;} wdev;} BSS;
typedef struct _RTMP_ADAPTER {RTMP_OS_TASK wscTask;int WscWorkerInitialized,WscConfigInitialized;
 int WscElmeLock,WriteWscCfgToDatFile,OpMode;UCHAR *pHmacData;MLME_QUEUE_ELEM *pWscElme;
 struct {BSS MBSSID[2],ApCliTab[2];} ApCfg;
} RTMP_ADAPTER;
#define RTMP_OS_TASK_LEGALITY(p) ((p)->kthread_task!=NULL)
#define NdisZeroMemory(p,n) memset((p),0,(n))
static int live,locks,tasks,timers,invalid,attempts,fail_at,init_fail,attach_fail,ready_checks;
static int control_stops,button_stops,user_exits;
static void *objects[64];
static void allocate(UCHAR **out,size_t n){int i;*out=NULL;attempts++;if(attempts==fail_at)return;
 *out=malloc(n);assert(*out);memset(*out,0xa5,n);for(i=0;i<64;i++)if(!objects[i]){objects[i]=*out;live++;return;}abort();}
static void release(void *p){int i;assert(p);assert(tasks==0);for(i=0;i<64;i++)if(objects[i]==p){objects[i]=NULL;live--;free(p);return;}invalid++;abort();}
#define os_alloc_mem(a,p,n) ((void)(a),allocate((p),(n)))
#define os_free_mem(p) release(p)
static void alloc_lock(int *p){assert(!*p);*p=1;locks++;}
static void free_lock(int *p){assert(*p==1);*p=0;locks--;}
#define NdisAllocateSpinLock(a,p) ((void)(a),alloc_lock(p))
#define NdisFreeSpinLock(p) free_lock(p)
static int task_init(RTMP_OS_TASK *p,const char *name,RTMP_ADAPTER *ad){(void)name;assert(!p->kthread_task);p->priv=ad;return init_fail?3:0;}
#define RTMP_OS_TASK_INIT(p,n,a) task_init((p),(n),(a))
static int wsc_write_dat_file_thread(ULONG value){RTMP_OS_TASK *task=(void*)value;RTMP_ADAPTER *ad=task->priv;size_t i;
 assert(ad->WscWorkerInitialized&&ad->WscElmeLock&&ad->pHmacData&&ad->pWscElme);
 assert(ad->WriteWscCfgToDatFile==0xff);for(i=0;i<2048;i++)assert(ad->pHmacData[i]==0);
 for(i=0;i<sizeof(*ad->pWscElme);i++){assert(((UCHAR*)ad->pWscElme)[i]==0);}
 ready_checks++;return 0;}
static int RtmpOSTaskAttach(RTMP_OS_TASK *p,INT(*fn)(ULONG),ULONG n){assert(n==(ULONG)p);if(attach_fail)return 3;
 assert(!p->kthread_task);p->kthread_task=p;tasks++;assert(fn(n)==0);return 0;}
static int RtmpOSTaskKill(RTMP_OS_TASK *p){if(p->kthread_task){p->kthread_task=NULL;tasks--;}return 0;}
static void RTMPReleaseTimer(RALINK_TIMER_STRUCT *p,BOOLEAN *cancelled){assert(!tasks&&p->Valid&&p->timer_lock);p->Valid=0;timers--;*cancelled=1;}
static void WscStop(RTMP_ADAPTER *ad,int apcli,WSC_CTRL *p){(void)apcli;assert(ad->WscConfigInitialized&&p->WscPeerListInitialized&&p->WscPeerListSemLock);control_stops++;}
static void WscClearPeerList(int *list){assert(*list==1);*list=0;}
static void WSC_HDR_BTN_Stop(RTMP_ADAPTER *ad){assert(ad->WscConfigInitialized);button_stops++;}
static void UserCfgExit(RTMP_ADAPTER *ad){assert(!ad->WscConfigInitialized&&!ad->WscWorkerInitialized&&live==0&&locks==0&&tasks==0&&timers==0);user_exits++;}
VOID WscThreadStop(RTMP_ADAPTER *ad);
'''
SUFFIX=r'''
static void timer_init(RALINK_TIMER_STRUCT *p){assert(!p->Valid);p->Valid=1;p->timer_lock=p;timers++;}
static void control_init(RTMP_ADAPTER *ad,WSC_CTRL *p,int apcli,int buffers){
 p->WscPeerListInitialized=1;p->WscPeerList=1;alloc_lock(&p->WscPeerListSemLock);ad->WscConfigInitialized=1;
 timer_init(&p->EapolTimer);timer_init(&p->Wsc2MinsTimer);timer_init(&p->WscUPnPNodeInfo.UPnPMsgTimer);timer_init(&p->M2DTimer);
 if(apcli){timer_init(&p->WscPBCTimer);timer_init(&p->WscScanTimer);timer_init(&p->WscProfileRetryTimer);}
 else{timer_init(&p->WscUpdatePortCfgTimer);timer_init(&p->WscSetupLockTimer);p->WscSetupLockTimerRunning=1;}
 if(buffers){allocate((UCHAR**)&p->pWscRxBuf,64);allocate((UCHAR**)&p->pWscTxBuf,64);allocate((UCHAR**)&p->WscV2Info.ExtraTlv.pTlvData,8);}
}
static void clear_timer_valid(WSC_CTRL *p){
 p->EapolTimer.Valid=p->Wsc2MinsTimer.Valid=p->WscUPnPNodeInfo.UPnPMsgTimer.Valid=p->M2DTimer.Valid=0;
 p->WscPBCTimer.Valid=p->WscScanTimer.Valid=p->WscProfileRetryTimer.Valid=p->WscUpdatePortCfgTimer.Valid=p->WscSetupLockTimer.Valid=0;
 timers=0;}
int main(int argc,char **argv){RTMP_ADAPTER ad;const char *name;int result=0,preserved=1,retry=-1,before;void *old;
 assert(argc==2);name=argv[1];CASE_ADMISSION memset(&ad,0,sizeof(ad));ad.OpMode=OPMODE_AP;
 if(!strncmp(name,"wsc-",4)){
  if(!strcmp(name,"wsc-partial-owner")){allocate(&ad.pHmacData,32);old=ad.pHmacData;before=attempts;result=WscThreadInit(&ad);preserved=(ad.pHmacData==old&&attempts==before);WscThreadStop(&ad);assert(ad.pHmacData==old);release(old);ad.pHmacData=NULL;}
  else{
   if(!strcmp(name,"wsc-hmac-oom"))fail_at=1;
   if(!strcmp(name,"wsc-element-oom"))fail_at=2;
   if(!strcmp(name,"wsc-task-init-failure"))init_fail=1;
   if(!strcmp(name,"wsc-task-attach-failure"))attach_fail=1;
   result=WscThreadInit(&ad);if(result){assert(live==0&&locks==0&&tasks==0&&!ad.WscWorkerInitialized);fail_at=init_fail=attach_fail=0;retry=WscThreadInit(&ad);}
   assert(live==2&&locks==1&&tasks==1&&ready_checks==1);
   if(!strcmp(name,"wsc-repeat-owner")){old=ad.pHmacData;before=attempts;result=WscThreadInit(&ad);preserved=(ad.pHmacData==old&&attempts==before);}
   if(!strcmp(name,"wsc-natural-exit")){assert(ad.wscTask.kthread_task);}
   WscThreadStop(&ad);WscThreadStop(&ad);
   if(!strcmp(name,"wsc-reopen")){retry=WscThreadInit(&ad);assert(ready_checks==2);WscThreadStop(&ad);}
  }
 }else{
  if(!strcmp(name,"cfg-worker-only")||!strcmp(name,"cfg-worker-and-controls"))assert(WscThreadInit(&ad)==0);
  if(strcmp(name,"cfg-no-owner")&&strcmp(name,"cfg-worker-only")){
   control_init(&ad,&ad.ApCfg.MBSSID[0].wdev.WscControl,0,1);
   if(!strcmp(name,"cfg-apcli-owned")||!strcmp(name,"cfg-worker-and-controls"))control_init(&ad,&ad.ApCfg.ApCliTab[0].wdev.WscControl,1,1);
   if(!strcmp(name,"cfg-partial-buffers")){WSC_CTRL *p=&ad.ApCfg.MBSSID[0].wdev.WscControl;release(p->pWscTxBuf);p->pWscTxBuf=NULL;release(p->WscV2Info.ExtraTlv.pTlvData);p->WscV2Info.ExtraTlv.pTlvData=NULL;}
   if(!strcmp(name,"cfg-invalid-timers"))clear_timer_valid(&ad.ApCfg.MBSSID[0].wdev.WscControl);
  }
  if(!strcmp(name,"cfg-user-exit-order")){result=rtmp_cfg_exit(&ad);assert(user_exits==1);}
  else result=WscThreadExit(&ad);
  if(!strcmp(name,"cfg-repeated-exit"))assert(WscThreadExit(&ad)==1);
  assert(!ad.WscConfigInitialized&&!ad.WscWorkerInitialized);
  if(!strcmp(name,"cfg-no-owner")||!strcmp(name,"cfg-worker-only"))assert(control_stops==0&&button_stops==0);
  if(!strcmp(name,"cfg-apcli-unbuilt"))assert(control_stops==1);
 }
 printf("[%d,%d,%d,%d,%d,%d,%d,%d]\n",result,preserved,retry,live,locks,tasks,timers,invalid);
 assert(live==0&&locks==0&&tasks==0&&timers==0&&invalid==0);return 0;
}
'''

def function(text,name):
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:inline\s+)?(?:INT|INT32|UINT32|NDIS_STATUS|BOOLEAN|VOID|void)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    found=list(re.finditer(pattern,masked,re.M))
    if len(found)!=1:raise ValueError('Missing or ambiguous init function: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for match in re.finditer(token+r'|[{}]',text[opening:]):
        if match.group()=='{':depth+=1
        elif match.group()=='}':
            depth-=1
            if not depth:return text[start:opening+match.end()]
    raise ValueError('Unterminated init function: '+name)


def generate_source(texts,variant='current'):
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact WSC variant sources required')
    definitions=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        found=re.findall(pattern,texts[key])
        if len(found)!=1:raise ValueError('Actual WSC declaration missing: '+pattern)
        definitions.append(found[0])
    for name,value in (('SUCCESS',0),('FAILURE',1),('RESOURCES',3)):
        found=re.findall(r'^#define NDIS_STATUS_'+name+r'\s+(0x[0-9a-fA-F]+)\s*$',texts['os_header'],re.M)
        if len(found)!=1 or int(found[0],16)!=value:raise ValueError('Actual status differs: '+name)
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return PREFIX.replace('SOURCE_DEFINITIONS','\n'.join(definitions))+'\n'.join(function(texts[FUNCTION_SOURCES[name]],name)for name in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)


def function_manifest(texts):
    result={name:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}for name,key in FUNCTION_SOURCES.items()}
    result.update({name:{'source':key,'execution':'source-only-not-run','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}for name,key in SOURCE_ONLY_FUNCTION_SOURCES.items()})
    return result
