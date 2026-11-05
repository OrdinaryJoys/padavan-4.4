"""Complete CMWQ lifecycle functions with an inert host queue contract.

Real pthread locks/orderings are exercised. The queue/allocation/IRQ seams do
not execute Linux workqueues, a target module, MMIO or hardware. CMWQ code can
be compiled into the real tm.o while the current K2P capability selects TASKLET.
"""
import hashlib
import re
MODEL_VARIANT = {
 'role':'private-inert-CMWQ-lifecycle-model',
 'model_qm_tm':'CMWQ_METHOD','model_hif_tm':'CMWQ_METHOD',
 'actual_K2P_qm_tm':'TASKLET_METHOD','actual_K2P_hif_tm':'TASKLET_METHOD',
 'CMWQ_present_in_actual_tm_object':True,
 'Linux_workqueue_execution_performed':False,
 'kernel_callback_ABI_proven':False,
 'host_pointer_width_is_inert_seam':True,
 'ERR_RECOVERY':True,'CONFIG_FWOWN_SUPPORT':True,'MULTI_LAYER_INTERRUPT':True,
 'extra_optional_branches_are_model_selection_not_actual_K2P_claim':True,
 'native_legacy_workqueue_allocator_branch_also_tested':True,
}
BASE = 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS = {'tm':BASE+'os/linux/tm.c','rtmp_header':BASE+'embedded/include/rtmp.h',
 'os_header':BASE+'include/os/rt_linux.h','tm_header':BASE+'embedded/include/tm.h',
 'chip_header':BASE+'include/hw_ctrl/cmm_chip.h','os':BASE+'os/linux/rt_main_dev.c',
 'qm_header':BASE+'embedded/include/qm.h'}
FUNCTION_SOURCES = {'RtmpDmaQuarantined':'os','RtmpDmaStopping':'os',
 'tm_wq_prepare':'tm','tm_wq_abort':'tm','tm_wq_publish':'tm','tm_wq_destroy':'tm',
 'tm_wq_retirement_check':'tm','ge_tx_pkt_deq_work':'tm','fp_tx_pkt_deq_work':'tm',
 'fp_fair_tx_pkt_deq_work':'tm','tm_wq_qm_init':'tm','tx_dma_done_work':'tm',
 'rx_done_work':'tm','rx1_done_work':'tm','mt_mac_recovery_work':'tm',
 'mt_mac_fw_own_work':'tm','mt_subsys_int_work':'tm','tm_wq_hif_pci_init':'tm',
 'tm_wq_hif_init':'tm','tm_wq_hif_pci_exit':'tm','tm_wq_hif_exit':'tm',
 'tm_wq_qm_exit':'tm','tm_wq_qm_schedule_taskOwned':'tm','tm_wq_qm_schedule_task':'tm',
 'tm_wq_hif_schedule_taskOwned':'tm','tm_wq_hif_schedule_task':'tm',
 'tm_wq_qm_schedule_task_onOwned':'tm','tm_wq_qm_schedule_task_on':'tm',
 'tm_wq_hif_schedule_task_onOwned':'tm','tm_wq_hif_schedule_task_on':'tm',
 'tm_init':'tm','tm_quiesce':'tm','tm_exit':'tm'}
BODY_ORDER = ('RtmpDmaQuarantined','RtmpDmaStopping','tm_wq_prepare','tm_wq_abort',
 'tm_wq_publish','tm_wq_destroy','tm_wq_retirement_check','ge_tx_pkt_deq_work',
 'fp_tx_pkt_deq_work','fp_fair_tx_pkt_deq_work','tm_wq_qm_init','tx_dma_done_work',
 'rx_done_work','rx1_done_work','mt_mac_recovery_work','mt_mac_fw_own_work',
 'mt_subsys_int_work','tm_wq_hif_pci_init','tm_wq_hif_init','tm_wq_hif_pci_exit',
 'tm_wq_hif_exit','tm_wq_qm_exit','tm_wq_qm_schedule_taskOwned',
 'tm_wq_qm_schedule_task','tm_wq_hif_schedule_taskOwned','tm_wq_hif_schedule_task',
 'tm_wq_qm_schedule_task_onOwned','tm_wq_qm_schedule_task_on',
 'tm_wq_hif_schedule_task_onOwned','tm_wq_hif_schedule_task_on',
 'tm_init','tm_quiesce','tm_exit')
SOURCE_ONLY_FUNCTION_SOURCES = {'RtmpDmaTeardownCheck':'os'}
SOURCE_DECLARATIONS = {r'enum tm_wq_state \{[\s\S]*?\n\};':'tm',
 r'static DEFINE_SPINLOCK\(tm_wq_lock\);':'tm',
 r'enum task_type \{[\s\S]*?\n\};':'tm_header',
 r'struct tm_ops \{[\s\S]*?\n\} ____cacheline_aligned;':'tm_header',
 r'enum queue_mm \{[\s\S]*?\n\};':'qm_header',
 r'#define TASKLET_METHOD 1':'chip_header',r'#define CMWQ_METHOD 2':'chip_header'}
SOURCE_FIELD_CONSTRAINTS = {r'UINT8 qm_wq_state;':'rtmp_header',r'UINT8 hif_wq_state;':'rtmp_header'}
CASE_NAMES = ('qm-oom','hif-oom','hif-rollback-oom','normal-fast','normal-fair',
 'normal-generic','normal-generic-fair','qm-owner','hif-owner','tm-owner',
 'qm-invalid-mode','hif-invalid-bus','qm-before-init','hif-before-init',
 'qm-after-exit','hif-after-exit','qm-on-after-exit','hif-on-after-exit',
 'qm-normal-schedule','qm-on-schedule','hif-normal-schedule','hif-on-schedule',
 'pci-stop-schedule','pci-quarantine-schedule','rbus-normal',
 'qm-allocate-cancel','hif-allocate-cancel','qm-late-stop','hif-late-stop',
 'rbus-allocate-cancel','qm-drain-admission','hif-drain-admission',
 'qm-exit-partial-retry','qm-quiesce-partial-retry','hif-exit-partial-retry',
 'hif-quiesce-partial-retry','rollback-drain-retained','quiesce-idempotent',
 'worker-requeue-qm','worker-requeue-hif','tm-stop-refusal','tm-retired-refusal')
FIELDS = ('result','secondary_result','preserved','work_done','final_queues',
 'final_qm_state','final_hif_state','final_ops','final_retired','invalid_operations')
EXPECTED_ROWS = {'qm-oom': [3, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-oom': [3, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-rollback-oom': [3, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'normal-fast': [0, -1, 1, 1, 0, 0, 0, 0, 0, 0],
 'normal-fair': [0, -1, 1, 1, 0, 0, 0, 0, 0, 0],
 'normal-generic': [0, -1, 1, 1, 0, 0, 0, 0, 0, 0],
 'normal-generic-fair': [0, -1, 1, 1, 0, 0, 0, 0, 0, 0],
 'qm-owner': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-owner': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'tm-owner': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-invalid-mode': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-invalid-bus': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-before-init': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-before-init': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-after-exit': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-after-exit': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-on-after-exit': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-on-after-exit': [1, -1, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-normal-schedule': [0, -1, 1, 1, 0, 0, 0, 0, 0, 0],
 'qm-on-schedule': [0, -1, 1, 1, 0, 0, 0, 0, 0, 0],
 'hif-normal-schedule': [0, -1, 1, 6, 0, 0, 0, 0, 0, 0],
 'hif-on-schedule': [0, -1, 1, 6, 0, 0, 0, 0, 0, 0],
 'pci-stop-schedule': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'pci-quarantine-schedule': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'rbus-normal': [0, -1, 1, 1, 0, 0, 0, 0, 0, 0],
 'qm-allocate-cancel': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-allocate-cancel': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-late-stop': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-late-stop': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'rbus-allocate-cancel': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-drain-admission': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-drain-admission': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-exit-partial-retry': [1, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'qm-quiesce-partial-retry': [1, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-exit-partial-retry': [1, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'hif-quiesce-partial-retry': [1, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'rollback-drain-retained': [1, 3, 1, 0, 0, 0, 0, 0, 0, 0],
 'quiesce-idempotent': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'worker-requeue-qm': [0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
 'worker-requeue-hif': [0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
 'tm-stop-refusal': [1, 0, 1, 0, 0, 0, 0, 0, 0, 0],
 'tm-retired-refusal': [1, 0, 1, 0, 0, 0, 0, 0, 0, 0]}

PREFIX = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#define ____cacheline_aligned
#define LINUX 1
#define RTMP_PCI_SUPPORT 1
#define ERR_RECOVERY 1
#define CONFIG_FWOWN_SUPPORT 1
#define MULTI_LAYER_INTERRUPT 1
#define TRUE 1
#define FALSE 0
#define VOID void
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_RESOURCES 3
#define HIF_RX_IDX0 0
#define HIF_RX_IDX1 1
#define WQ_MEM_RECLAIM 1
#define WQ_UNBOUND 2
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#ifndef LINUX_VERSION_CODE
#define LINUX_VERSION_CODE KERNEL_VERSION(4,4,198)
#endif
#define DEFINE_SPINLOCK(n) pthread_mutex_t n=PTHREAD_MUTEX_INITIALIZER
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_RELAXED)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
typedef int INT;
typedef int BOOLEAN;
typedef uint8_t UINT8;
typedef uintptr_t ULONG;
struct _RTMP_ADAPTER;
struct workqueue_struct;
struct work_struct {void (*func)(struct work_struct *);int initialized,queued;};
struct workqueue_struct {int live,id,count;struct work_struct *pending[16];};
SOURCE_DEFINITIONS
struct os_cookie {pthread_mutex_t dma_state_lock;ULONG pAd_va;
 struct workqueue_struct *hif_wq;struct work_struct tx_dma_done_work,rx_done_work[2],
 mac_recovery_work,mac_fw_own_work,subsys_int_work;};
typedef struct os_cookie *POS_COOKIE;
typedef struct {int qm,qm_tm,hif_tm;} RTMP_CHIP_CAP;
typedef struct _RTMP_ADAPTER {void *OS_Cookie;RTMP_CHIP_CAP *hdev_ctrl;
 int inf,dma_stopping,dma_quarantined,dma_tasks_retired,tx_dequeue_scheduable;
 STATE_FIELDS
 struct workqueue_struct *qm_wq;
 struct work_struct tx_deq_work;struct tm_ops *tm_qm_ops,*tm_hif_ops;
} RTMP_ADAPTER;
#define IS_PCI_INF(p) ((p)->inf==1)
#define IS_PCIE_INF(p) ((p)->inf==2)
#define IS_RBUS_INF(p) ((p)->inf==3)
static RTMP_CHIP_CAP *hc_get_chip_cap(RTMP_CHIP_CAP *p){return p;}
static pthread_mutex_t *known_wq_lock;
static __thread int lock_depth,wq_depth;
static void take_lock(pthread_mutex_t *p){if(p!=known_wq_lock)assert(!wq_depth);
 assert(pthread_mutex_lock(p)==0);lock_depth++;if(p==known_wq_lock)wq_depth++;}
static void drop_lock(pthread_mutex_t *p){assert(lock_depth>0);if(p==known_wq_lock){assert(wq_depth==1);wq_depth--;}
 lock_depth--;assert(pthread_mutex_unlock(p)==0);}
#define spin_lock_irqsave(p,f) do{(f)=0;take_lock(p);}while(0)
#define spin_unlock_irqrestore(p,f) do{(void)(f);drop_lock(p);}while(0)
static pthread_mutex_t event_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t event_cond=PTHREAD_COND_INITIALIZER;
static int block_alloc,block_destroy,event_ready,event_resume,attempts,fail_at;
static int created,destroyed,live,work_done,invalid,queue_calls,init_work_calls,legacy_calls;
static int callback_requeue,callback_result=-1;
static struct workqueue_struct *registry[32];
static RTMP_ADAPTER *active_ad;
static INT tm_wq_qm_schedule_task(RTMP_ADAPTER *,enum task_type);
static INT tm_wq_hif_schedule_task(RTMP_ADAPTER *,enum task_type);
static INT tm_wq_qm_init(RTMP_ADAPTER *);
static INT tm_wq_hif_init(RTMP_ADAPTER *);
static INT tm_wq_qm_exit(RTMP_ADAPTER *);
static INT tm_wq_hif_exit(RTMP_ADAPTER *);
static INT tm_init(RTMP_ADAPTER *);
static INT tm_exit(RTMP_ADAPTER *);
static INT tm_quiesce(RTMP_ADAPTER *);
static void pause_here(void){assert(!lock_depth);assert(pthread_mutex_lock(&event_lock)==0);
 event_ready=1;assert(pthread_cond_broadcast(&event_cond)==0);while(!event_resume)assert(pthread_cond_wait(&event_cond,&event_lock)==0);
 assert(pthread_mutex_unlock(&event_lock)==0);}
static void wait_here(void){assert(pthread_mutex_lock(&event_lock)==0);while(!event_ready)assert(pthread_cond_wait(&event_cond,&event_lock)==0);
 assert(pthread_mutex_unlock(&event_lock)==0);}
static void resume_here(void){assert(pthread_mutex_lock(&event_lock)==0);event_resume=1;assert(pthread_cond_broadcast(&event_cond)==0);assert(pthread_mutex_unlock(&event_lock)==0);}
static struct workqueue_struct *allocate_queue(const char *name,int flags,int count){struct workqueue_struct *q;int i;
 (void)name;(void)flags;(void)count;assert(!lock_depth);attempts++;if(attempts==block_alloc)pause_here();if(attempts==fail_at)return NULL;
 q=calloc(1,sizeof(*q));assert(q);q->live=1;q->id=++created;live++;
 for(i=0;i<32;i++){if(!registry[i]){registry[i]=q;return q;}}
 abort();}
#if (KERNEL_VERSION(2, 6, 37) <= LINUX_VERSION_CODE)
#define alloc_workqueue(n,f,c) allocate_queue(n,f,c)
#else
static struct workqueue_struct *create_singlethread_workqueue(const char *n){legacy_calls++;return allocate_queue(n,0,1);}
#endif
static void init_work(struct work_struct *w,void(*fn)(struct work_struct *)){assert(!lock_depth&&!w->queued&&fn);w->func=fn;w->initialized=1;init_work_calls++;}
#define INIT_WORK(w,f) init_work(w,f)
static int queue_work(struct workqueue_struct *q,struct work_struct *w){assert(wq_depth==1&&q&&q->live&&w->initialized&&w->func);queue_calls++;
 if(w->queued){return 0;}
 assert(q->count<16);q->pending[q->count++]=w;w->queued=1;return 1;}
static int queue_work_on(int cpu,struct workqueue_struct *q,struct work_struct *w){assert(cpu>=0&&cpu<8);return queue_work(q,w);}
static void run_queue(struct workqueue_struct *q){int i;assert(!lock_depth&&q&&q->live);for(i=0;i<q->count;i++){struct work_struct *w=q->pending[i];assert(w->queued&&w->initialized);w->queued=0;w->func(w);}q->count=0;}
static void destroy_workqueue(struct workqueue_struct *q){int i;assert(!lock_depth&&q&&q->live);if(q->id==block_destroy)pause_here();run_queue(q);q->live=0;live--;destroyed++;
 for(i=0;i<32;i++){if(registry[i]==q){registry[i]=NULL;free(q);return;}}
 invalid++;abort();}
static void callback(RTMP_ADAPTER *ad,int kind){assert(ad==active_ad&&!lock_depth);work_done++;
 if(callback_requeue==kind){callback_requeue=0;callback_result=kind==1?tm_wq_qm_schedule_task(ad,TX_DEQ_TASK):tm_wq_hif_schedule_task(ad,TX_DONE_TASK);}}
static void ge_tx_pkt_deq_func(RTMP_ADAPTER *p){callback(p,1);}
static void fp_tx_pkt_deq_func(RTMP_ADAPTER *p){callback(p,1);}
static void fp_fair_tx_pkt_deq_func(RTMP_ADAPTER *p){callback(p,1);}
static void tx_dma_done_func(RTMP_ADAPTER *p){callback(p,2);}
static void rx_done_func(RTMP_ADAPTER *p){callback(p,2);}
static void rx1_done_func(RTMP_ADAPTER *p){callback(p,2);}
static void mt_mac_recovery_func(RTMP_ADAPTER *p){callback(p,2);}
static void mt_mac_fw_own_func(RTMP_ADAPTER *p){callback(p,2);}
static void mt_subsys_int_func(RTMP_ADAPTER *p){callback(p,2);}
/* Actual TASKLET work lives in other complete components; this CMWQ model
 * deliberately rejects that backend rather than simulating its execution. */
static INT unused_backend(RTMP_ADAPTER *p){(void)p;abort();}
static struct tm_ops tm_tasklet_qm_ops={.init=unused_backend,.exit=unused_backend};
static struct tm_ops tm_tasklet_hif_ops={.init=unused_backend,.exit=unused_backend};
static struct tm_ops tm_wq_qm_ops={.init=tm_wq_qm_init,.exit=tm_wq_qm_exit};
static struct tm_ops tm_wq_hif_ops={.init=tm_wq_hif_init,.exit=tm_wq_hif_exit};
'''

SUFFIX = r'''
struct request {RTMP_ADAPTER *ad;int operation,result;};
static void *invoke(void *opaque){struct request *r=opaque;
 switch(r->operation){case 1:r->result=tm_wq_qm_init(r->ad);break;
 case 2:r->result=tm_wq_hif_init(r->ad);break;case 3:r->result=tm_init(r->ad);break;
 case 4:r->result=tm_wq_qm_exit(r->ad);break;case 5:r->result=tm_wq_hif_exit(r->ad);break;
 default:abort();}return NULL;}
static void set_stopping(RTMP_ADAPTER *ad,int quarantined){POS_COOKIE obj=ad->OS_Cookie;ULONG flags;
 spin_lock_irqsave(&obj->dma_state_lock,flags);ad->dma_stopping=1;ad->dma_quarantined=quarantined;
 spin_unlock_irqrestore(&obj->dma_state_lock,flags);}
static void reset_events(void){event_ready=event_resume=0;block_alloc=block_destroy=0;}
static void all_gone(RTMP_ADAPTER *ad){POS_COOKIE obj=ad->OS_Cookie;
 assert(!ad->qm_wq&&!obj->hif_wq&&ad->qm_wq_state==TM_WQ_IDLE&&ad->hif_wq_state==TM_WQ_IDLE&&live==0);}
static void cleanup(RTMP_ADAPTER *ad){assert(tm_exit(ad)==0);assert(tm_wq_hif_exit(ad)==0);assert(tm_wq_qm_exit(ad)==0);all_gone(ad);}
int main(int argc,char **argv){RTMP_ADAPTER ad;struct os_cookie obj;
 RTMP_CHIP_CAP cap={FAST_PATH_QM,CMWQ_METHOD,CMWQ_METHOD};const char *name;int result=0,secondary=-1,preserved=1,before;
 pthread_t thread;struct request req;struct workqueue_struct *qowner,*howner;int original_created;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&ad,0,sizeof(ad));memset(&obj,0,sizeof(obj));ad.OS_Cookie=&obj;ad.hdev_ctrl=&cap;ad.inf=1;active_ad=&ad;known_wq_lock=&tm_wq_lock;
 assert(pthread_mutex_init(&obj.dma_state_lock,NULL)==0);obj.pAd_va=(ULONG)&ad;
 if(!strcmp(name,"qm-oom")||!strcmp(name,"hif-oom")||!strcmp(name,"hif-rollback-oom")){
  fail_at=!strcmp(name,"hif-rollback-oom")?2:1;
  result=!strcmp(name,"qm-oom")?tm_wq_qm_init(&ad):!strcmp(name,"hif-oom")?tm_wq_hif_init(&ad):tm_init(&ad);
  assert(result==3&&!ad.tm_qm_ops&&!ad.tm_hif_ops&&!ad.tx_dequeue_scheduable);all_gone(&ad);
  fail_at=0;secondary=tm_init(&ad);assert(secondary==0);cleanup(&ad);
 }else if(!strncmp(name,"normal-",7)||!strcmp(name,"rbus-normal")){
  if(!strcmp(name,"normal-fair"))cap.qm=FAST_PATH_FAIR_QM;
  if(!strcmp(name,"normal-generic"))cap.qm=GENERIC_QM;
  if(!strcmp(name,"normal-generic-fair"))cap.qm=GENERIC_FAIR_QM;
  if(!strcmp(name,"rbus-normal"))ad.inf=3;
  result=tm_init(&ad);assert(result==0&&ad.tm_qm_ops&&ad.tm_hif_ops&&live==2);
  assert(tm_wq_qm_schedule_task(&ad,TX_DEQ_TASK)==0);run_queue(ad.qm_wq);assert(work_done==1);cleanup(&ad);
 }else if(!strcmp(name,"qm-owner")||!strcmp(name,"hif-owner")||!strcmp(name,"tm-owner")){
  assert(tm_init(&ad)==0);qowner=ad.qm_wq;howner=obj.hif_wq;before=init_work_calls;original_created=created;
  result=!strcmp(name,"qm-owner")?tm_wq_qm_init(&ad):!strcmp(name,"hif-owner")?tm_wq_hif_init(&ad):tm_init(&ad);
  preserved=ad.qm_wq==qowner&&obj.hif_wq==howner&&init_work_calls==before&&created==original_created;assert(result==1&&preserved);cleanup(&ad);
 }else if(!strcmp(name,"qm-invalid-mode")||!strcmp(name,"hif-invalid-bus")){
  if(!strcmp(name,"qm-invalid-mode")){cap.qm=99;result=tm_wq_qm_init(&ad);}else{ad.inf=99;result=tm_wq_hif_init(&ad);}
  assert(result==1&&!attempts&&!init_work_calls);all_gone(&ad);
 }else if(strstr(name,"before-init")||strstr(name,"after-exit")){
  if(strstr(name,"after-exit")){assert(tm_init(&ad)==0);cleanup(&ad);}
  if(!strncmp(name,"qm-on-",6))result=tm_wq_qm_schedule_task_on(&ad,2,TX_DEQ_TASK);
  else if(!strncmp(name,"hif-on-",7))result=tm_wq_hif_schedule_task_on(&ad,2,RX_DONE_TASK);
  else if(!strncmp(name,"qm-",3))result=tm_wq_qm_schedule_task(&ad,TX_DEQ_TASK);
  else result=tm_wq_hif_schedule_task(&ad,RX_DONE_TASK);
  assert(result==1&&!queue_calls);cleanup(&ad);
 }else if(strstr(name,"normal-schedule")||strstr(name,"on-schedule")){
  assert(tm_init(&ad)==0);
  if(!strncmp(name,"qm-",3)){
   result=strstr(name,"on-schedule")?tm_wq_qm_schedule_task_on(&ad,2,TX_DEQ_TASK):tm_wq_qm_schedule_task(&ad,TX_DEQ_TASK);
   assert(queue_calls==1);run_queue(ad.qm_wq);assert(work_done==1);
  }else{
   int tasks[]={TX_DONE_TASK,RX_DONE_TASK,RX1_DONE_TASK,ERROR_RECOVERY_TASK,FW_OWN_TASK,SUBSYS_INT_TASK};unsigned i;
   for(i=0;i<sizeof(tasks)/sizeof(tasks[0]);i++){
    result=strstr(name,"on-schedule")?tm_wq_hif_schedule_task_on(&ad,2,tasks[i]):tm_wq_hif_schedule_task(&ad,tasks[i]);assert(result==0);
   }
   assert(queue_calls==6);run_queue(obj.hif_wq);assert(work_done==6);
  }assert(result==0);cleanup(&ad);
 }else if(!strcmp(name,"pci-stop-schedule")||!strcmp(name,"pci-quarantine-schedule")){
  assert(tm_init(&ad)==0);set_stopping(&ad,strstr(name,"quarantine")!=NULL);
  result=tm_wq_qm_schedule_task(&ad,TX_DEQ_TASK);secondary=tm_wq_hif_schedule_task_on(&ad,2,RX_DONE_TASK);
  assert(result==1&&secondary==1&&!queue_calls);cleanup(&ad);
 }else if(strstr(name,"allocate-cancel")||strstr(name,"late-stop")){
  int ishif=!strncmp(name,"hif-",4),isfull=strstr(name,"allocate-cancel")&&!strstr(name,"rbus");
  if(strstr(name,"rbus"))ad.inf=3;
  block_alloc=(ishif&&isfull)?2:1;req=(struct request){&ad,isfull?3:ishif?2:1,-1};
  assert(pthread_create(&thread,NULL,invoke,&req)==0);wait_here();
  if(strstr(name,"late-stop")){set_stopping(&ad,0);result=1;}
  else result=isfull?(ishif?tm_exit(&ad):tm_quiesce(&ad)):tm_wq_qm_exit(&ad);
  assert(result==1&&!ad.dma_tasks_retired);resume_here();assert(pthread_join(thread,NULL)==0);secondary=req.result;assert(secondary==1);
  all_gone(&ad);assert(!ad.tm_qm_ops&&!ad.tm_hif_ops);reset_events();ad.dma_stopping=0;ad.dma_quarantined=0;
  assert(tm_init(&ad)==0);cleanup(&ad);
 }else if(strstr(name,"drain-admission")){
  int ishif=!strncmp(name,"hif-",4);assert(tm_init(&ad)==0);qowner=ad.qm_wq;howner=obj.hif_wq;block_destroy=ishif?howner->id:qowner->id;
  req=(struct request){&ad,ishif?5:4,-1};assert(pthread_create(&thread,NULL,invoke,&req)==0);wait_here();before=init_work_calls;original_created=created;
  result=ishif?tm_wq_hif_init(&ad):tm_wq_qm_init(&ad);secondary=ishif?tm_wq_hif_exit(&ad):tm_wq_qm_exit(&ad);
  assert(result==1&&secondary==1&&before==init_work_calls&&created==original_created);
  assert((ishif?tm_wq_hif_schedule_task_on(&ad,1,RX_DONE_TASK):tm_wq_qm_schedule_task(&ad,TX_DEQ_TASK))==1&&!queue_calls);
  resume_here();assert(pthread_join(thread,NULL)==0&&req.result==0);reset_events();cleanup(&ad);
 }else if(strstr(name,"partial-retry")){
  int ishif=!strncmp(name,"hif-",4),quiesce=strstr(name,"quiesce")!=NULL;assert(tm_init(&ad)==0);qowner=ad.qm_wq;howner=obj.hif_wq;
  block_destroy=ishif?howner->id:qowner->id;req=(struct request){&ad,ishif?5:4,-1};assert(pthread_create(&thread,NULL,invoke,&req)==0);wait_here();
  result=quiesce?tm_quiesce(&ad):tm_exit(&ad);assert(result==1&&ad.tm_qm_ops&&ad.tm_hif_ops&&!ad.dma_tasks_retired);
  if(ishif)assert(ad.qm_wq==qowner&&ad.qm_wq_state==TM_WQ_ACTIVE&&destroyed==0);
  else assert(!obj.hif_wq&&ad.hif_wq_state==TM_WQ_IDLE&&destroyed==1);
  resume_here();assert(pthread_join(thread,NULL)==0&&req.result==0);reset_events();secondary=quiesce?tm_quiesce(&ad):tm_exit(&ad);assert(secondary==0);
  assert(created==2&&destroyed==2);cleanup(&ad);
 }else if(!strcmp(name,"rollback-drain-retained")){
  fail_at=2;block_destroy=1;req=(struct request){&ad,3,-1};assert(pthread_create(&thread,NULL,invoke,&req)==0);wait_here();
  assert(ad.tm_qm_ops&&!ad.tm_hif_ops&&ad.qm_wq_state==TM_WQ_EXITING);result=tm_exit(&ad);
  assert(result==1&&ad.tm_qm_ops&&!ad.tm_hif_ops);resume_here();assert(pthread_join(thread,NULL)==0);secondary=req.result;assert(secondary==3);all_gone(&ad);
  assert(!ad.tm_qm_ops);reset_events();fail_at=0;assert(tm_init(&ad)==0);cleanup(&ad);
 }else if(!strcmp(name,"quiesce-idempotent")){
  assert(tm_init(&ad)==0);set_stopping(&ad,0);result=tm_quiesce(&ad);assert(result==0&&ad.dma_tasks_retired&&ad.tm_qm_ops&&ad.tm_hif_ops);
  secondary=tm_quiesce(&ad);assert(secondary==0&&created==2&&destroyed==2);cleanup(&ad);
 }else if(!strncmp(name,"worker-requeue-",15)){
  int ishif=strstr(name,"hif")!=NULL;assert(tm_init(&ad)==0);callback_requeue=ishif?2:1;
  assert((ishif?tm_wq_hif_schedule_task(&ad,TX_DONE_TASK):tm_wq_qm_schedule_task(&ad,TX_DEQ_TASK))==0);
  result=tm_exit(&ad);secondary=callback_result;assert(result==0&&secondary==1&&work_done==1&&queue_calls==1);cleanup(&ad);
 }else if(!strcmp(name,"tm-stop-refusal")||!strcmp(name,"tm-retired-refusal")){
  if(strstr(name,"stop"))set_stopping(&ad,0);else ad.dma_tasks_retired=1;
  result=tm_init(&ad);assert(result==1&&!attempts&&!ad.tm_qm_ops&&!ad.tm_hif_ops);ad.dma_tasks_retired=0;ad.dma_stopping=0;
  secondary=tm_init(&ad);assert(secondary==0);cleanup(&ad);
 }else abort();
 assert(live==0&&created==destroyed&&!invalid&&!lock_depth&&!ad.tm_qm_ops&&!ad.tm_hif_ops&&!ad.dma_tasks_retired);
 #if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,37)
 assert(legacy_calls==attempts);
 #else
 assert(legacy_calls==0);
 #endif
 assert(pthread_mutex_destroy(&obj.dma_state_lock)==0);
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",result,secondary,preserved,work_done,live,ad.qm_wq_state,ad.hif_wq_state,
 ad.tm_qm_ops!=NULL||ad.tm_hif_ops!=NULL,ad.dma_tasks_retired,invalid);return 0;
}
'''


def function(text, name):
    token = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked = re.sub(token,lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'^(?:static\s+)?(?:INT|VOID|BOOLEAN)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked,re.M))
    if len(matches)!=1:raise ValueError('Missing/ambiguous CMWQ function: '+name)
    start=matches[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unbalanced CMWQ function: '+name)


def _match(texts,pattern,key):
    if key not in texts:raise ValueError('Missing CMWQ source '+key)
    rows=list(re.finditer(pattern,texts[key]))
    if len(rows)!=1:raise ValueError('Missing/ambiguous CMWQ declaration '+pattern)
    return rows[0].group()


def declarations(texts):
    return '\n'.join(_match(texts,p,k) for p,k in SOURCE_DECLARATIONS.items())


def source_declarations(texts):
    result={}
    for pattern,key in {**SOURCE_DECLARATIONS,**SOURCE_FIELD_CONSTRAINTS}.items():
        result[pattern]={'source':key,'sha256':hashlib.sha256(_match(texts,pattern,key).encode()).hexdigest()}
    return result


def function_manifest(texts):
    return {name:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()} for name,key in FUNCTION_SOURCES.items()}


def source_only_function_manifest(texts):
    return {name:hashlib.sha256(function(texts[key],name).encode()).hexdigest() for name,key in SOURCE_ONLY_FUNCTION_SOURCES.items()}


def generate_source(texts,variant='current'):
    if variant!='current':raise ValueError('Only current inert CMWQ model supported')
    for key in SOURCE_PATHS:
        if key not in texts:raise ValueError('Missing CMWQ source '+key)
    source_declarations(texts);source_only_function_manifest(texts)
    prefix=PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts)).replace('STATE_FIELDS','\n'.join(_match(texts,p,k)for p,k in SOURCE_FIELD_CONSTRAINTS.items()))
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return prefix+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n) for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)
