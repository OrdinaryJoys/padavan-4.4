"""Actual VIF INIT/UP/DOWN/DEINIT and counter functions with inert backends.

The exercised protocol is the current Linux caller's serialized INIT then UP.
Callback failure means rejection before publication in the current AP profile.
Hardware open/close are explicit stage seams; their real PCI/DMA ownership is
tested separately by dma_quarantine_harness. No kernel or network runs here.
"""
import hashlib
import re

BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'os':BASE+'os/linux/rt_main_dev.c','wdev':BASE+'embedded/common/wdev.c',
 'counter':BASE+'embedded/common/cmm_info.c','cfg':BASE+'embedded/common/cmm_cfg.c',
 'header':BASE+'embedded/include/rtmp.h','os_header':BASE+'include/os/rt_linux.h'}
FUNCTION_SOURCES={'VIRTUAL_IF_INC':'counter','VIRTUAL_IF_DEC':'counter','VIRTUAL_IF_NUM':'counter',
 'wdev_if_up_down':'wdev','wdev_do_open':'wdev','wdev_do_close':'wdev',
 'virtual_if_init_handler':'os','virtual_if_up_handler':'os',
 'virtual_if_down_handler':'os','virtual_if_deinit_handler':'os'}
SOURCE_ONLY_FUNCTION_SOURCES={'mt_wifi_open':'os','mt_wifi_close':'os',
 'main_virtual_if_open':'os','RTMP_COM_IoctlHandle':'cfg'}
BODY_ORDER=('VIRTUAL_IF_INC','VIRTUAL_IF_DEC','VIRTUAL_IF_NUM','wdev_if_up_down',
 'wdev_do_open','wdev_do_close','virtual_if_init_handler','virtual_if_up_handler',
 'virtual_if_down_handler','virtual_if_deinit_handler')
CASE_GROUPS={
 'first-failure':('first-up-failure','first-callback-missing','first-hardware-open-failure'),
 'nonlast-failure':('nonlast-up-failure','duplicate-init-up-failure'),
 'missing':('first-missing-wdev','nonlast-missing-wdev'),
 'cleanup-busy':('first-up-failure-busy','first-up-failure-stop-error','first-missing-wdev-busy'),
 'success':('first-up-success','nonlast-up-success'),
 'boundary':('up-with-zero-count','up-null-adapter','init-null-adapter','down-null-adapter','deinit-null-adapter'),
 'init-guards':('init-quarantined','init-removing','up-stopping-after-init','up-removing-after-init'),
 'down':('last-down-idle','last-down-busy','nonlast-down','down-callback-error'),
 'deinit':('last-deinit-idle','last-deinit-busy','nonlast-deinit')}
CASE_NAMES=('first-up-failure','first-callback-missing','first-hardware-open-failure',
 'nonlast-up-failure','duplicate-init-up-failure','first-missing-wdev','nonlast-missing-wdev',
 'first-up-failure-busy','first-up-failure-stop-error','first-missing-wdev-busy',
 'first-up-success','nonlast-up-success','up-with-zero-count','up-null-adapter',
 'init-null-adapter','down-null-adapter','deinit-null-adapter','init-quarantined',
 'init-removing','up-stopping-after-init','up-removing-after-init','last-down-idle',
 'last-down-busy','nonlast-down','down-callback-error','last-deinit-idle',
 'last-deinit-busy','nonlast-deinit')
FIELDS=('result','vif_count','if_up','other_if_up','hardware_live','pinned','quarantined',
 'irq_live','rings_live','tokens_live','wdev_published','hardware_opens','hardware_closes',
 'callback_opens','callback_closes','lookups','teardown_checks','unsafe_frees')
EXPECTED_ROWS = {'first-up-failure': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 0],
 'first-callback-missing': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0],
 'first-hardware-open-failure': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
 'nonlast-up-failure': [-1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 1, 0, 1, 0, 0],
 'duplicate-init-up-failure': [-1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 0, 1, 0, 1, 0, 0],
 'first-missing-wdev': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0],
 'nonlast-missing-wdev': [-1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0],
 'first-up-failure-busy': [-1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0],
 'first-up-failure-stop-error': [-1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0],
 'first-missing-wdev-busy': [-1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 0],
 'first-up-success': [0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0],
 'nonlast-up-success': [0, 2, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 0, 1, 0, 1, 0, 0],
 'up-with-zero-count': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'up-null-adapter': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'init-null-adapter': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'down-null-adapter': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'deinit-null-adapter': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'init-quarantined': [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'init-removing': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'up-stopping-after-init': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0],
 'up-removing-after-init': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0],
 'last-down-idle': [0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0],
 'last-down-busy': [-5, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0],
 'nonlast-down': [0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0],
 'down-callback-error': [-1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 0],
 'last-deinit-idle': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0],
 'last-deinit-busy': [-5, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0],
 'nonlast-deinit': [0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0]}
SOURCE_DECLARATIONS={r'^#define NDIS_STATUS_SUCCESS\s+0x[0-9a-fA-F]+\s*$':'os_header',
 r'^#define NDIS_STATUS_FAILURE\s+0x[0-9a-fA-F]+\s*$':'os_header'}
PREFIX=r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
typedef void VOID;typedef int INT,BOOLEAN;typedef unsigned int UINT;typedef unsigned long ULONG;
#define TRUE 1
#define FALSE 0
#define MTWF_LOG(...) ((void)0)
#define READ_ONCE(v) (v)
SOURCE_DEFINITIONS
struct _RTMP_ADAPTER;
struct wifi_dev;
struct wdev_ops {int (*open)(struct wifi_dev *);int (*close)(struct wifi_dev *);};
struct wifi_dev {int if_up_down_state,wdev_idx;struct wdev_ops *wdev_ops;};
struct net_device {struct _RTMP_ADAPTER *adapter;};
typedef struct _RTMP_ADAPTER {UINT VirtualIfCnt;pthread_mutex_t VirtualIfLock,lifecycle;
 int dma_removing,dma_stopping,dma_quarantined,dma_lifecycle_pinned;
 struct net_device *net_dev;} RTMP_ADAPTER;
FUNCTION_DECLARATIONS
static RTMP_ADAPTER *active;
static struct wifi_dev wdev;
static int other_if_up,hardware_live,irq_live,rings_live,tokens_live,wdev_published;
static int hardware_opens,hardware_closes,callback_opens,callback_closes,lookups,teardown_checks,unsafe_frees;
static int callback_open_ok=1,callback_close_ok=1,lookup_ok=1,hardware_open_status,busy,stop_failure;
#define OS_SPIN_LOCK_IRQSAVE(p,f) do{(void)(f);assert(!pthread_mutex_lock(p));}while(0)
#define OS_SPIN_UNLOCK_IRQRESTORE(p,f) do{(void)(f);assert(!pthread_mutex_unlock(p));}while(0)
#define GET_PAD_FROM_NET_DEV(p,n) ((p)=(n)->adapter)
static int callback_open(struct wifi_dev *p){assert(p==&wdev);callback_opens++;
 if(!callback_open_ok)return FALSE;
 assert(!wdev_published);wdev_published=1;return TRUE;}
static int callback_close(struct wifi_dev *p){assert(p==&wdev);callback_closes++;
 if(!callback_close_ok)return FALSE;
 assert(wdev_published);wdev_published=0;return TRUE;}
static struct wdev_ops callbacks={callback_open,callback_close};
static struct wifi_dev *wdev_search_by_netdev(RTMP_ADAPTER *ad,struct net_device *net){
 assert(ad==active&&net==ad->net_dev);lookups++;return lookup_ok?&wdev:NULL;}
static int RtmpDmaQuarantined(RTMP_ADAPTER *ad){assert(ad==active);return ad->dma_quarantined;}
static int RtmpDmaStopping(RTMP_ADAPTER *ad){assert(ad==active);return ad->dma_stopping||ad->dma_quarantined;}
static void RtmpDmaQuarantine(RTMP_ADAPTER *ad){assert(ad==active);ad->dma_stopping=ad->dma_quarantined=1;}
static void RtmpDmaLifecycleLock(RTMP_ADAPTER *ad){assert(!pthread_mutex_lock(&ad->lifecycle));}
static void RtmpDmaLifecycleUnlock(RTMP_ADAPTER *ad){assert(!pthread_mutex_unlock(&ad->lifecycle));}
static int RtmpDmaTeardownCheck(RTMP_ADAPTER *ad){assert(ad==active);teardown_checks++;
 if(busy||stop_failure||ad->dma_quarantined){ad->dma_quarantined=1;ad->dma_stopping=1;return FALSE;}
 ad->dma_stopping=1;return TRUE;}
static int mt_wifi_open(void *net){assert(net==active->net_dev);hardware_opens++;
 if(hardware_open_status)return hardware_open_status;
 assert(!hardware_live);hardware_live=irq_live=rings_live=tokens_live=1;active->dma_lifecycle_pinned=1;return 0;}
static int mt_wifi_close(void *net){assert(net==active->net_dev);hardware_closes++;
 if(active->VirtualIfCnt!=0){unsafe_frees++;assert(0);}
 if(!RtmpDmaTeardownCheck(active))return-EIO;
 hardware_live=irq_live=rings_live=tokens_live=0;active->dma_lifecycle_pinned=0;return 0;}
'''
SUFFIX=r'''
static void existing_owner(int count){active->VirtualIfCnt=(UINT)count;other_if_up=count>0;
 hardware_live=irq_live=rings_live=tokens_live=1;active->dma_lifecycle_pinned=1;}
int main(int argc,char **argv){RTMP_ADAPTER ad;struct net_device net;const char *name;int result=0;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&ad,0,sizeof(ad));memset(&net,0,sizeof(net));memset(&wdev,0,sizeof(wdev));
 active=&ad;net.adapter=&ad;ad.net_dev=&net;wdev.wdev_ops=&callbacks;
 assert(!pthread_mutex_init(&ad.VirtualIfLock,NULL));assert(!pthread_mutex_init(&ad.lifecycle,NULL));
 if(!strcmp(name,"first-up-failure")||!strcmp(name,"first-callback-missing")||
    !strcmp(name,"first-missing-wdev")||!strcmp(name,"first-up-failure-busy")||
    !strcmp(name,"first-up-failure-stop-error")||!strcmp(name,"first-missing-wdev-busy")||
    !strcmp(name,"first-up-success")||!strcmp(name,"up-stopping-after-init")||
    !strcmp(name,"up-removing-after-init")){
  assert(virtual_if_init_handler(&net)==0);assert(ad.VirtualIfCnt==1&&hardware_live&&ad.dma_lifecycle_pinned);
  if(strstr(name,"missing-wdev"))lookup_ok=0;
  if(strstr(name,"failure"))callback_open_ok=0;
  if(!strcmp(name,"first-callback-missing"))wdev.wdev_ops=NULL;
  if(strstr(name,"busy"))busy=1;
  if(strstr(name,"stop-error"))stop_failure=1;
  if(!strcmp(name,"up-stopping-after-init"))ad.dma_stopping=1;
  if(!strcmp(name,"up-removing-after-init"))ad.dma_removing=1;
  result=virtual_if_up_handler(&net);
  if(!strcmp(name,"first-up-success")){
   assert(result==0&&ad.VirtualIfCnt==1&&wdev.if_up_down_state&&wdev_published);
   assert(hardware_closes==0&&hardware_live&&ad.dma_lifecycle_pinned);
  }else{
   assert(result==-1&&ad.VirtualIfCnt==0&&!wdev.if_up_down_state&&!wdev_published&&hardware_closes==1);
   if(busy||stop_failure){assert(ad.dma_quarantined&&ad.dma_lifecycle_pinned&&hardware_live&&irq_live&&rings_live&&tokens_live);}
   else assert(!ad.dma_lifecycle_pinned&&!hardware_live&&!irq_live&&!rings_live&&!tokens_live);
  }
 }else if(!strcmp(name,"nonlast-up-failure")||!strcmp(name,"nonlast-missing-wdev")||
          !strcmp(name,"nonlast-up-success")||!strcmp(name,"duplicate-init-up-failure")){
  existing_owner(1);
  if(!strcmp(name,"duplicate-init-up-failure")){wdev.if_up_down_state=1;wdev_published=1;}
  assert(virtual_if_init_handler(&net)==0&&ad.VirtualIfCnt==2);
  if(strstr(name,"failure"))callback_open_ok=0;
  if(strstr(name,"missing"))lookup_ok=0;
  result=virtual_if_up_handler(&net);
  assert(other_if_up&&hardware_live&&ad.dma_lifecycle_pinned&&hardware_opens==0&&hardware_closes==0);
  if(!strcmp(name,"nonlast-up-success"))assert(result==0&&ad.VirtualIfCnt==2&&wdev.if_up_down_state&&wdev_published);
  else{assert(result==-1&&ad.VirtualIfCnt==1);assert(wdev.if_up_down_state==!strcmp(name,"duplicate-init-up-failure"));}
 }else if(!strcmp(name,"first-hardware-open-failure")){
  hardware_open_status=-EBUSY;result=virtual_if_init_handler(&net);
  assert(result!=0&&ad.VirtualIfCnt==0&&!hardware_live&&!ad.dma_lifecycle_pinned&&callback_opens==0&&hardware_closes==0);
 }else if(!strcmp(name,"up-with-zero-count")){
  result=virtual_if_up_handler(&net);assert(result==-1&&ad.VirtualIfCnt==0&&hardware_closes==0&&callback_opens==0);
 }else if(strstr(name,"null-adapter")){
  net.adapter=NULL;
  if(!strcmp(name,"up-null-adapter"))result=virtual_if_up_handler(&net);
  else if(!strcmp(name,"init-null-adapter"))result=virtual_if_init_handler(&net);
  else if(!strcmp(name,"down-null-adapter"))result=virtual_if_down_handler(&net);
  else result=virtual_if_deinit_handler(&net);
  assert(result==-1&&ad.VirtualIfCnt==0&&hardware_opens==0&&hardware_closes==0);
 }else if(!strcmp(name,"init-quarantined")||!strcmp(name,"init-removing")){
  if(strstr(name,"quarantined"))ad.dma_quarantined=1;else ad.dma_removing=1;
  result=virtual_if_init_handler(&net);assert(result!=0&&ad.VirtualIfCnt==0&&hardware_opens==0);
 }else if(!strcmp(name,"last-down-idle")||!strcmp(name,"last-down-busy")||
          !strcmp(name,"nonlast-down")||!strcmp(name,"down-callback-error")){
  existing_owner(!strcmp(name,"nonlast-down")?1:0);wdev.if_up_down_state=1;wdev_published=1;
  if(strstr(name,"busy"))busy=1;
  if(strstr(name,"callback-error"))callback_close_ok=0;
  result=virtual_if_down_handler(&net);
  if(busy){assert(result==-EIO&&wdev.if_up_down_state&&wdev_published&&callback_closes==0&&ad.dma_quarantined);}
  else if(!callback_close_ok)assert(result==-1&&!wdev.if_up_down_state&&wdev_published);
  else assert(result==0&&!wdev.if_up_down_state&&!wdev_published);
  assert(hardware_live&&ad.dma_lifecycle_pinned&&hardware_closes==0);
  if(!strcmp(name,"nonlast-down"))assert(ad.VirtualIfCnt==1&&other_if_up&&teardown_checks==0);
 }else if(!strcmp(name,"last-deinit-idle")||!strcmp(name,"last-deinit-busy")||!strcmp(name,"nonlast-deinit")){
  existing_owner(!strcmp(name,"nonlast-deinit")?1:0);if(strstr(name,"busy"))busy=1;
  result=virtual_if_deinit_handler(&net);
  if(!strcmp(name,"nonlast-deinit"))assert(result==0&&hardware_live&&hardware_closes==0&&other_if_up);
  else if(busy)assert(result==-EIO&&hardware_live&&ad.dma_lifecycle_pinned&&hardware_closes==1);
  else assert(result==0&&!hardware_live&&!ad.dma_lifecycle_pinned&&hardware_closes==1);
 }else assert(0);
 assert(ad.VirtualIfCnt<=2&&unsafe_frees==0);
 printf("[%d,%u,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",result,ad.VirtualIfCnt,
 wdev.if_up_down_state,other_if_up,hardware_live,ad.dma_lifecycle_pinned,ad.dma_quarantined,irq_live,rings_live,tokens_live,
 wdev_published,hardware_opens,hardware_closes,callback_opens,callback_closes,lookups,teardown_checks,unsafe_frees);
 assert(!pthread_mutex_destroy(&ad.VirtualIfLock));assert(!pthread_mutex_destroy(&ad.lifecycle));return 0;}
'''

def function(text,name):
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:inline\s+)?(?:VOID|BOOLEAN|UINT|INT|INT32|int|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    found=list(re.finditer(pattern,masked,re.M))
    if len(found)!=1:raise ValueError('Missing/ambiguous VIF function: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated VIF function: '+name)

def declarations(texts):
    rows=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        matches=re.findall(pattern,texts[key],re.M)
        if len(matches)!=1:raise ValueError('Missing/ambiguous VIF declaration: '+pattern)
        rows.append(matches[0])
    return '\n'.join(rows)

def generate_source(texts,variant='current'):
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current VIF inputs required')
    admission='if(!('+'||'.join('!strcmp(name,"'+name+'")'for name in CASE_NAMES)+'))return 91;'
    prototypes='\n'.join(function(texts[FUNCTION_SOURCES[n]],n).split('{',1)[0].rstrip()+';'for n in BODY_ORDER)
    prefix=PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts)).replace('FUNCTION_DECLARATIONS',prototypes)
    return prefix+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)

def function_manifest(texts):
    return {n:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],n).encode()).hexdigest()}for n,key in FUNCTION_SOURCES.items()}
