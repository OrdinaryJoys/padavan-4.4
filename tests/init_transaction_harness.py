"""Actual software-init transactions with private allocation/task recorders.

No DMA/MMIO/kernel tasks execute; adapter lifecycle parents are source-only.
"""
import hashlib
import re
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'tr':BASE+'embedded/common/cmm_data.c',
 'basic':BASE+'embedded/hw_ctrl/hw_ctrl_basic.c','sys':BASE+'embedded/common/rtmp_init_inf.c',
 'mgmt':BASE+'os/linux/rt_rbus_pci_drv.c','ba':BASE+'embedded/common/ba_action.c',
 'spectrum':BASE+'embedded/common/spectrum.c','qm':BASE+'embedded/common/qm.c',
 'tm':BASE+'os/linux/tm.c','adapter':BASE+'embedded/common/rtmp_init.c',
 'free':BASE+'os/linux/rt_profile.c','tr_header':BASE+'embedded/include/tr.h',
 'hw_header':BASE+'embedded/include/hw_ctrl.h','rtmp_header':BASE+'embedded/include/rtmp.h',
 'task_header':BASE+'embedded/include/rtmp_os.h','os_header':BASE+'include/os/rt_linux.h',
 'chip_header':BASE+'include/hw_ctrl/cmm_chip.h','qm_header':BASE+'embedded/include/qm.h',
 'lifetime':BASE+'os/linux/rt_main_dev.c'}
FUNCTION_SOURCES={'tr_ctl_init':'tr','tr_ctl_exit':'tr','ser_init':'basic',
 'HwCtrlSerExit':'basic','ser_exit':'basic','HwCtrlInit':'basic','HwCtrlExit':'basic',
 'RtmpMgmtTaskInit':'mgmt','RtmpMgmtTaskExit':'mgmt',
 'ba_reordering_resource_init':'ba','ba_reordering_resource_release':'ba',
 'MeasureReqTabInit':'spectrum','MeasureReqTabExit':'spectrum',
 'TpcReqTabInit':'spectrum','TpcReqTabExit':'spectrum','qm_init':'qm','qm_exit':'qm',
 'tm_init':'tm','tm_exit':'tm','rtmp_sys_task_exit':'sys','rtmp_sys_init':'sys','rtmp_sys_exit':'sys'}
SOURCE_ONLY_FUNCTION_SOURCES={'RTMPAllocAdapterBlock':'adapter','RTMPFreeAdapter':'free',
 'RtmpDmaStopping':'lifetime','RtmpDmaTeardownCheck':'lifetime','RtmpDmaQuarantine':'lifetime'}
BODY_ORDER=('tr_ctl_init','tr_ctl_exit','ser_init','HwCtrlSerExit','ser_exit','HwCtrlInit',
 'HwCtrlExit','RtmpMgmtTaskInit','RtmpMgmtTaskExit','ba_reordering_resource_init',
 'ba_reordering_resource_release','MeasureReqTabInit','MeasureReqTabExit','TpcReqTabInit',
 'TpcReqTabExit','qm_init','qm_exit','tm_init','tm_exit','rtmp_sys_task_exit','rtmp_sys_init','rtmp_sys_exit')
SOURCE_DECLARATIONS={
 r'enum ASIC_CAP \{[\s\S]*?\n\};':'chip_header',
 r'enum HIF_TYPE \{[\s\S]*?\n\};':'chip_header',
 r'enum queue_mm \{[\s\S]*?\n\};':'qm_header',
 r'#define TASKLET_METHOD 1':'chip_header',
 r'#define CMWQ_METHOD 2':'chip_header',
 r'#define GET_NUM_OF_TX_RING\(_chipCap\)\s+\(\(_chipCap\)->num_of_tx_ring\)':'chip_header',
 r'typedef enum _RTMP_TASK_STATUS_ \{[\s\S]*?\} RTMP_TASK_STATUS;':'task_header',
 r'struct tx_delay_control \{[\s\S]*?\n\};':'tr_header',
 r'struct tr_delay_control \{[\s\S]*?\n\};':'tr_header',
 r'struct tr_flow_control \{[\s\S]*?\n\};':'tr_header',
 r'struct tx_rx_ctl \{[\s\S]*?\n\};':'tr_header',
 r'typedef struct _HWCTRL_OP \{[\s\S]*?\} HWCTRL_OP;':'hw_header',
 r'typedef struct _HW_CTRL_T \{[\s\S]*?\} HW_CTRL_T;':'hw_header',
 r'struct reordering_list \{[\s\S]*?\n\};':'rtmp_header',
 r'struct reordering_mpdu \{[\s\S]*?\n\};':'rtmp_header',
 r'struct reordering_mpdu_pool \{[\s\S]*?\n\};':'rtmp_header'}
CASE_NAMES=('tr-oom1','tr-oom2','tr-oom3','tr-normal','tr-owner','tr-partial','tr-reopen',
 'ser-init-failure','ser-attach-failure','ser-normal','ser-owner','ser-joined','ser-natural-exit','ser-reopen',
 'hw-init-failure','hw-attach-failure','hw-ser-init-failure','hw-ser-attach-failure','hw-normal','hw-owner','hw-reopen',
 'mgmt-init-failure','mgmt-attach-failure','mgmt-normal','ba-oom','ba-owner','ba-reopen',
 'qm-init-failure','qm-notify-failure','qm-normal','qm-owner',
 'tm-qm-failure','tm-hif-failure','tm-invalid-method','tm-normal','tm-owner',
 'sys-mgmt-init-failure','sys-mgmt-attach-failure','sys-hw-init-failure','sys-hw-attach-failure',
 'sys-ser-init-failure','sys-ser-attach-failure','sys-config-failure','sys-ba-oom','sys-measure-oom',
 'sys-tpc-oom','sys-tr-oom1','sys-tr-oom2','sys-tr-oom3','sys-qm-failure','sys-tm-qm-failure',
 'sys-tm-hif-failure','sys-normal','sys-owner','sys-reopen',
 'sys-old-ser','sys-old-ba','sys-old-measure','sys-old-tpc','sys-old-tr','sys-retired',
 'tm-stop-refusal','tm-retired-refusal','tm-hif-rollback-failure','tm-exit-qm-failure','tm-exit-hif-failure',
 'sys-tm-rollback-failure','sys-task-exit-failure','sys-exit-failure','sys-init-retirement-failure','sys-stop-refusal','sys-tr-release-failure')
FIELDS=('result','preserved','retry_result','source_owned_released','adapter_lock_retained',
        'final_allocations','final_locks','invalid_operations')
EXPECTED_ROWS={
 'sys-tr-release-failure':[0,1,-1,0,1,0,0,0],
 'sys-stop-refusal':[0,1,1,1,1,0,0,0],
 'tm-stop-refusal':[1,1,0,1,1,0,0,0], 'tm-retired-refusal':[1,1,0,1,1,0,0,0],
 'tm-hif-rollback-failure':[3,1,0,1,1,0,0,0], 'tm-exit-qm-failure':[1,1,0,1,1,0,0,0], 'tm-exit-hif-failure':[1,1,0,1,1,0,0,0],
 'sys-tm-rollback-failure':[0,1,-1,0,1,0,0,0], 'sys-task-exit-failure':[1,1,-1,0,1,0,0,0],
 'sys-exit-failure':[0,1,-1,0,1,0,0,0], 'sys-init-retirement-failure':[0,1,-1,0,1,0,0,0],

 'tr-oom1':[3,1,0,1,1,0,0,0], 'tr-oom2':[3,1,0,1,1,0,0,0], 'tr-oom3':[3,1,0,1,1,0,0,0],
 'tr-normal':[0,1,-1,1,1,0,0,0], 'tr-owner':[1,1,-1,1,1,0,0,0], 'tr-partial':[1,1,-1,1,1,0,0,0], 'tr-reopen':[0,1,0,1,1,0,0,0],
 'ser-init-failure':[3,1,0,1,1,0,0,0], 'ser-attach-failure':[3,1,0,1,1,0,0,0], 'ser-normal':[0,1,-1,1,1,0,0,0],
 'ser-owner':[1,1,-1,1,1,0,0,0], 'ser-joined':[0,1,-1,1,1,0,0,0], 'ser-natural-exit':[0,1,-1,1,1,0,0,0], 'ser-reopen':[0,1,0,1,1,0,0,0],
 'hw-init-failure':[3,1,0,1,1,0,0,0], 'hw-attach-failure':[3,1,0,1,1,0,0,0],
 'hw-ser-init-failure':[3,1,0,1,1,0,0,0], 'hw-ser-attach-failure':[3,1,0,1,1,0,0,0],
 'hw-normal':[0,1,-1,1,1,0,0,0], 'hw-owner':[1,1,-1,1,1,0,0,0], 'hw-reopen':[0,1,0,1,1,0,0,0],
 'mgmt-init-failure':[3,1,0,1,1,0,0,0], 'mgmt-attach-failure':[3,1,0,1,1,0,0,0], 'mgmt-normal':[0,1,-1,1,1,0,0,0],
 'ba-oom':[0,1,1,1,1,0,0,0], 'ba-owner':[0,1,-1,1,1,0,0,0], 'ba-reopen':[1,1,1,1,1,0,0,0],
 'qm-init-failure':[3,1,0,1,1,0,0,0], 'qm-notify-failure':[1,1,0,1,1,0,0,0], 'qm-normal':[0,1,-1,1,1,0,0,0], 'qm-owner':[1,1,-1,1,1,0,0,0],
 'tm-qm-failure':[3,1,0,1,1,0,0,0], 'tm-hif-failure':[3,1,0,1,1,0,0,0], 'tm-invalid-method':[1,1,0,1,1,0,0,0], 'tm-normal':[0,1,-1,1,1,0,0,0], 'tm-owner':[1,1,-1,1,1,0,0,0],
 'sys-mgmt-init-failure':[0,1,1,1,1,0,0,0], 'sys-mgmt-attach-failure':[0,1,1,1,1,0,0,0],
 'sys-hw-init-failure':[0,1,1,1,1,0,0,0], 'sys-hw-attach-failure':[0,1,1,1,1,0,0,0],
 'sys-ser-init-failure':[0,1,1,1,1,0,0,0], 'sys-ser-attach-failure':[0,1,1,1,1,0,0,0],
 'sys-config-failure':[0,1,1,1,1,0,0,0], 'sys-ba-oom':[0,1,1,1,1,0,0,0], 'sys-measure-oom':[0,1,1,1,1,0,0,0],
 'sys-tpc-oom':[0,1,1,1,1,0,0,0], 'sys-tr-oom1':[0,1,1,1,1,0,0,0], 'sys-tr-oom2':[0,1,1,1,1,0,0,0], 'sys-tr-oom3':[0,1,1,1,1,0,0,0],
 'sys-qm-failure':[0,1,1,1,1,0,0,0], 'sys-tm-qm-failure':[0,1,1,1,1,0,0,0], 'sys-tm-hif-failure':[0,1,1,1,1,0,0,0],
 'sys-normal':[1,1,-1,1,1,0,0,0], 'sys-owner':[0,1,-1,1,1,0,0,0], 'sys-reopen':[1,1,1,1,1,0,0,0],
 'sys-old-ser':[0,1,-1,1,1,0,0,0], 'sys-old-ba':[0,1,-1,1,1,0,0,0],
 'sys-old-measure':[0,1,-1,1,1,0,0,0], 'sys-old-tpc':[0,1,-1,1,1,0,0,0],
 'sys-old-tr':[0,1,-1,1,1,0,0,0], 'sys-retired':[1,1,-1,1,1,0,0,0]}
PREFIX=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void VOID,*PVOID,*PNDIS_PACKET;typedef unsigned char UCHAR,UINT8,*PUCHAR;
typedef unsigned short UINT16;typedef uint32_t UINT32;typedef unsigned long ULONG;
typedef int INT,INT32,NTSTATUS,NDIS_STATUS,BOOLEAN,NDIS_SPIN_LOCK;typedef char RTMP_STRING;
#define RtmpDmaResourcesMayRelease(p) ((void)(p),1)
#define RtmpDmaQuarantined(p) ((p)->dma_quarantined)
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_RESOURCES 3
#define KTHREAD_SUPPORT
#define ERR_RECOVERY
#define DOT11_N_SUPPORT
#define MT_MAC
#define CONFIG_TX_DELAY
#define MTWF_LOG(...) ((void)0)
#define NdisZeroMemory(p,n) memset((p),0,(n))
#define ASSERT(p) assert(p)
#define MAX_LEN_OF_BA_REC_TABLE 2
#define MAX_REORDERING_MPDU_NUM 4
#define Recipient_NONE 0
#define fRTMP_ADAPTER_INTERRUPT_REGISTER_TO_OS 1
#define RTMP_CLEAR_FLAG(p,f) ((p)->flags&=~(f))
#define IS_HIF_TYPE(p,t) ((void)(p),(t)==HIF_MT)
#define IS_ASIC_CAP(p,c) (((p)->caps&(c))!=0)
#define DATA_QUE_MAX_NUMS 256
#define CR4_SET_ID_CONFIG_TX_DELAY_MODE 1
#define TX_DELAY_MODE_ARG1_TX_BATCH_CNT 2
#define TX_DELAY_MODE_ARG1_TX_DELAY_TIMEOUT_US 3
#define TX_DELAY_MODE_ARG1_PKT_LENGTHS 4
#define GET_TIMER_FUNCTION(n) NULL
#define RTMP_OS_TASK_LEGALITY(p) ((p)->kthread_task!=NULL)
#define RTMP_OS_NETDEV_GET_DEVNAME(p) (p)
typedef struct {int initialized;} RALINK_TIMER_STRUCT;
typedef struct node {struct node *next,*prev;} DL_LIST;
typedef struct _TX_BLOCK_DEV {DL_LIST list;void *NetDev;} TX_BLOCK_DEV;
typedef struct {void *kthread_task,*priv;} RTMP_OS_TASK;
typedef struct {void *head,*tail;UINT32 size;int CmdQState;} HwCmdQ;
typedef struct {int inert;} HwFlagCtrl;
#define SER_TIME_ID_END 8
struct WIFI_SYS_CTRL;
SOURCE_DEFINITIONS
struct _RTMP_ADAPTER;
struct qm_ops {INT(*init)(struct _RTMP_ADAPTER*);INT(*exit)(struct _RTMP_ADAPTER*);};
struct tm_ops {INT(*init)(struct _RTMP_ADAPTER*);INT(*exit)(struct _RTMP_ADAPTER*);};
typedef struct _RTMP_CHIP_CAP {int qm,qm_tm,hif_tm,tx_delay_support;UINT8 num_of_tx_ring;} RTMP_CHIP_CAP;
typedef struct {int REC_BA_Status;struct reordering_list list;} BA_REC_ENTRY;
typedef struct {BA_REC_ENTRY BARecEntry[MAX_LEN_OF_BA_REC_TABLE];} BA_TABLE;
typedef struct {int inert;} MEASURE_REQ_TAB,TPC_REQ_TAB;
typedef struct _RTMP_ADAPTER {int dma_tasks_retired,dma_stopping,dma_quarantined;struct tx_rx_ctl tr_ctl;HW_CTRL_T HwCtrl;RTMP_OS_TASK cmdQTask;
 HwCmdQ CmdQ;int CmdQLock,BATabLock,cfg_lock,txs_lock,flags,WifiSysInfo,caps,fp_que_max_size;
 struct {int errRecovState,status,queues_retired,recovery_failed;} ErrRecoveryCtl;
 struct {void *pMeasureReqTab,*pTpcReqTab;int MeasureReqTabLock,TpcReqTabLock;} CommonCfg;
 struct reordering_mpdu_pool mpdu_blk_pool;BA_TABLE BATable;
 struct qm_ops *qm_ops;struct tm_ops *tm_qm_ops,*tm_hif_ops;RTMP_CHIP_CAP *hdev_ctrl;char *net_dev;
} RTMP_ADAPTER,*PRTMP_ADAPTER;
#define ERR_RECOV_STOP_IDLE 0
static int live,locks,tasks,timers,invalid,attempts,fail_at,init_attempts,attach_attempts;
static int init_fail_at,attach_fail_at,cfg_fail,qm_fail,notify_fail,tm_qm_fail,tm_hif_fail;
static int qm_live,notify_live,tm_qm_live,tm_hif_live,software_stage;
static int tm_qm_exit_fail,tm_hif_exit_fail,tm_retirement_fail,tm_qm_joined,tm_hif_joined;
/* The full DMA parent runs in quarantine; these explicit seams model an
 * unarmed transport and injectable task join outcomes for software stages. */
static int RtmpDmaStopping(RTMP_ADAPTER *ad){return ad->dma_stopping||ad->dma_quarantined;}
static int RtmpDmaTeardownCheck(RTMP_ADAPTER *ad){ad->dma_stopping=1;return !ad->dma_quarantined;}
static void RtmpDmaQuarantine(RTMP_ADAPTER *ad){ad->dma_quarantined=1;}
static int tm_wq_retirement_check(RTMP_ADAPTER *ad){(void)ad;return tm_retirement_fail?1:0;}
static void *objects[64];
static void alloc(UCHAR **out,size_t n){int i;*out=NULL;attempts++;if(attempts==fail_at)return;
 *out=calloc(1,n);assert(*out);for(i=0;i<64;i++)if(!objects[i]){objects[i]=*out;live++;return;}abort();}
static void release(void *p){int i;assert(p);for(i=0;i<64;i++)if(objects[i]==p){objects[i]=NULL;live--;free(p);return;}invalid++;abort();}
#define os_alloc_mem(a,p,n) ((void)(a),alloc((p),(n)))
#define os_free_mem(p) release(p)
static void alloc_lock(int *p){assert(!*p);*p=1;locks++;}
static void free_lock(int *p){assert(*p==1);*p=0;locks--;}
#define NdisAllocateSpinLock(a,p) ((void)(a),alloc_lock(p))
#define NdisFreeSpinLock(p) free_lock(p)
#define NdisAcquireSpinLock(p) assert(*(p)==1)
#define NdisReleaseSpinLock(p) assert(*(p)==1)
#define RTMP_SEM_LOCK(p) assert(*(p)==1)
#define RTMP_SEM_UNLOCK(p) assert(*(p)==1)
#define RTMP_SPIN_LOCK_IRQSAVE(p,f) ((void)(f),assert(*(p)==1))
#define RTMP_SPIN_UNLOCK_IRQRESTORE(p,f) ((void)(f),assert(*(p)==1))
static void DlListInit(DL_LIST *p){p->next=p->prev=p;}
#define DlListFirst(p,t,m) ((void)(p),(t*)NULL)
#define DlListDel(p) ((void)(p),abort())
#define RTMP_OS_NETDEV_WAKE_QUEUE(p) ((void)(p),abort())
static void init_timer(RALINK_TIMER_STRUCT *p){assert(!p->initialized);p->initialized=1;timers++;}
static void release_timer(RALINK_TIMER_STRUCT *p,int *cancel){assert(p->initialized);p->initialized=0;timers--;*cancel=1;}
#define RTMPInitTimer(a,p,f,c,r) ((void)(a),(void)(f),(void)(c),(void)(r),init_timer(p))
#define RTMPSetTimer(p,n) ((void)(n),assert((p)->initialized))
#define RTMPReleaseTimer(p,c) release_timer((p),(c))
static RTMP_CHIP_CAP *hc_get_chip_cap(void *p){assert(p);return p;}
static int task_init(RTMP_OS_TASK *p,const char *name,RTMP_ADAPTER *ad){(void)name;assert(!p->kthread_task);
 init_attempts++;if(init_attempts==init_fail_at)return 3;p->priv=ad;return 0;}
#define RTMP_OS_TASK_INIT(p,n,a) task_init((p),(n),(a))
static int ser_ctrl_task(ULONG n){(void)n;return 0;}
static int HwCtrlThread(ULONG n){(void)n;return 0;}
static int RTPCICmdThread(ULONG n){(void)n;return 0;}
static int RtmpOSTaskAttach(RTMP_OS_TASK *p,INT(*fn)(ULONG),ULONG n){assert(fn);assert(n==(ULONG)p);assert(!p->kthread_task);
 attach_attempts++;if(attach_attempts==attach_fail_at)return 3;p->kthread_task=p;tasks++;return 0;}
static int RtmpOSTaskKill(RTMP_OS_TASK *p){if(p->kthread_task){p->kthread_task=NULL;tasks--;}return 0;}
VOID HwCtrlExit(RTMP_ADAPTER *ad);
/* This init model owns task stages only. Command/flag data retirement is
 * executed by hwcmd_owner_harness; these seams require a completed join. */
static VOID HwCtrlCmdHandler(RTMP_ADAPTER *ad){assert(ad->HwCtrl.HwCtrlQ.CmdQState==RTMP_TASK_STAT_STOPED);assert(!RTMP_OS_TASK_LEGALITY(&ad->HwCtrl.HwCtrlTask));}
static VOID HwCtrlFlagHandler(RTMP_ADAPTER *ad){assert(ad->HwCtrl.HwCtrlQ.CmdQState==RTMP_TASK_STAT_STOPED);assert(!RTMP_OS_TASK_LEGALITY(&ad->HwCtrl.HwCtrlTask));}
static void RtmpCmdQInit(RTMP_ADAPTER *ad){alloc_lock(&ad->CmdQLock);ad->CmdQ.CmdQState=RTMP_TASK_STAT_INITED;}
static void RtmpCmdQExit(RTMP_ADAPTER *ad){assert(ad->CmdQLock);}
static void ba_enqueue_head(struct reordering_list *l,struct reordering_mpdu *m){m->next=l->next;l->next=m;l->qlen++;}
static struct reordering_mpdu *ba_reordering_mpdu_dequeue(struct reordering_list *l){(void)l;return NULL;}
static void ba_mpdu_blk_free(RTMP_ADAPTER *ad,struct reordering_mpdu *p){(void)ad;(void)p;abort();}
#define RELEASE_NDIS_PACKET(a,p,s) ((void)(a),(void)(p),(void)(s),abort())
static int qminit(RTMP_ADAPTER *ad){(void)ad;assert(!qm_live);if(qm_fail)return 3;qm_live=1;return 0;}
static int qmexit(RTMP_ADAPTER *ad){(void)ad;assert(qm_live);assert(!tm_qm_live&&!tm_hif_live);qm_live=0;return 0;}
static struct qm_ops ge_qm_ops={qminit,qmexit},fp_qm_ops={qminit,qmexit},ge_fair_qm_ops={qminit,qmexit},fp_fair_qm_ops={qminit,qmexit};
static int qm_notify_register(RTMP_ADAPTER *ad){assert(ad->qm_ops&&qm_live&&!notify_live);if(notify_fail)return -1;notify_live=1;return 0;}
static void qm_notify_unregister(RTMP_ADAPTER *ad){assert(ad->qm_ops&&notify_live);notify_live=0;}
static void MtCmdCr4Set(RTMP_ADAPTER *ad,int n,int k,int v){(void)ad;(void)n;(void)k;(void)v;}
static int tmqinit(RTMP_ADAPTER *ad){(void)ad;assert(!tm_qm_live);if(tm_qm_fail)return 3;tm_qm_live=1;tm_qm_joined=0;return 0;}
static int tmqexit(RTMP_ADAPTER *ad){(void)ad;assert(tm_qm_live||tm_qm_joined);assert(!tm_hif_live);if(tm_qm_exit_fail)return 1;tm_qm_live=0;tm_qm_joined=1;return 0;}
static int tmhinit(RTMP_ADAPTER *ad){(void)ad;assert(tm_qm_live&&!tm_hif_live);if(tm_hif_fail)return 3;tm_hif_live=1;tm_hif_joined=0;return 0;}
static int tmhexit(RTMP_ADAPTER *ad){(void)ad;assert(tm_hif_live||tm_hif_joined);if(tm_hif_exit_fail)return 1;tm_hif_live=0;tm_hif_joined=1;return 0;}
static struct tm_ops tm_tasklet_qm_ops={tmqinit,tmqexit},tm_tasklet_hif_ops={tmhinit,tmhexit};
static struct tm_ops tm_wq_qm_ops={tmqinit,tmqexit},tm_wq_hif_ops={tmhinit,tmhexit};
static void wifi_sys_reset(int *p){assert(!*p);*p=1;}
static int rtmp_cfg_init(RTMP_ADAPTER *ad,RTMP_STRING *name){(void)name;alloc_lock(&ad->cfg_lock);alloc_lock(&ad->BATabLock);software_stage=1;return !cfg_fail;}
static void rtmp_cfg_exit(RTMP_ADAPTER *ad){assert(!tasks&&!qm_live&&!notify_live&&!tm_qm_live&&!tm_hif_live);assert(!ad->mpdu_blk_pool.mem);
 assert(!ad->CommonCfg.pMeasureReqTab&&!ad->CommonCfg.pTpcReqTab);assert(!ad->tr_ctl.tr_flow_ctl.TxFlowBlockState);free_lock(&ad->BATabLock);free_lock(&ad->cfg_lock);software_stage=0;ad->WifiSysInfo=0;}
static void InitTxSTypeTable(RTMP_ADAPTER *ad){alloc_lock(&ad->txs_lock);}
static void InitTxSCommonCallBack(RTMP_ADAPTER *ad){assert(ad->txs_lock);}
static void ExitTxSTypeTable(RTMP_ADAPTER *ad){free_lock(&ad->txs_lock);}
static void RTMP_AllTimerListRelease(RTMP_ADAPTER *ad){(void)ad;assert(timers==0);}
'''

SUFFIX=r'''
static void reset_faults(void){fail_at=init_fail_at=attach_fail_at=cfg_fail=qm_fail=notify_fail=tm_qm_fail=tm_hif_fail=tm_qm_exit_fail=tm_hif_exit_fail=tm_retirement_fail=0;}
static void tr_clear(RTMP_ADAPTER *ad){assert(tr_ctl_exit(ad)==0);assert(tr_ctl_exit(ad)==0);}
static void mgmt_clear(RTMP_ADAPTER *ad){RtmpMgmtTaskExit(ad);NdisFreeSpinLock(&ad->CmdQLock);}
static int tr_owned(RTMP_ADAPTER *ad){struct tr_flow_control *f=&ad->tr_ctl.tr_flow_ctl;return f->TxFlowBlockState!=NULL||f->TxBlockLock!=NULL||f->TxBlockDevList!=NULL;}
static void clean_check(RTMP_ADAPTER *ad){assert(live==0&&locks==1&&tasks==0&&timers==0);assert(!tr_owned(ad));
 assert(!ad->HwCtrl.ser_initialized&&!ad->HwCtrl.HwCtrlTask.kthread_task&&!ad->HwCtrl.ser_task.kthread_task);
 assert(!ad->qm_ops&&!ad->tm_qm_ops&&!ad->tm_hif_ops&&!qm_live&&!notify_live&&!tm_qm_live&&!tm_hif_live);}
int main(int argc,char **argv){RTMP_ADAPTER ad;RTMP_CHIP_CAP cap={FAST_PATH_QM,TASKLET_METHOD,TASKLET_METHOD,1,3};
 const char *name;int result=0,preserved=1,retry=-1,before,phase,source_owned_released=1;void *owner;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&ad,0,sizeof(ad));ad.hdev_ctrl=&cap;ad.caps=fASIC_CAP_MCU_OFFLOAD;alloc_lock(&ad.mpdu_blk_pool.lock);
 if(!strncmp(name,"tr-",3)){
  if(!strncmp(name,"tr-oom",6))fail_at=name[6]-'0';
  if(!strcmp(name,"tr-owner")){assert(tr_ctl_init(&ad)==0);owner=ad.tr_ctl.tr_flow_ctl.TxBlockLock;before=attempts;result=tr_ctl_init(&ad);preserved=(owner==ad.tr_ctl.tr_flow_ctl.TxBlockLock&&before==attempts);tr_clear(&ad);}
  else if(!strcmp(name,"tr-partial")){alloc((UCHAR**)&ad.tr_ctl.tr_flow_ctl.TxFlowBlockState,3);owner=ad.tr_ctl.tr_flow_ctl.TxFlowBlockState;result=tr_ctl_init(&ad);preserved=(owner==ad.tr_ctl.tr_flow_ctl.TxFlowBlockState&&tr_ctl_exit(&ad)==1);release(owner);ad.tr_ctl.tr_flow_ctl.TxFlowBlockState=NULL;}
  else{result=tr_ctl_init(&ad);if(result){assert(!tr_owned(&ad)&&live==0&&locks==1&&timers==0);assert(attempts==fail_at);reset_faults();retry=tr_ctl_init(&ad);}assert(tr_owned(&ad)&&live==3&&locks==4&&timers==1);tr_clear(&ad);if(!strcmp(name,"tr-reopen")){retry=tr_ctl_init(&ad);tr_clear(&ad);}}
 }else if(!strncmp(name,"ser-",4)){
  if(!strcmp(name,"ser-init-failure"))init_fail_at=1;
  if(!strcmp(name,"ser-attach-failure"))attach_fail_at=1;
  result=ser_init(&ad);if(result){assert(!ad.HwCtrl.ser_initialized&&!ad.HwCtrl.ser_task.kthread_task&&locks==1);reset_faults();retry=ser_init(&ad);}assert(ad.HwCtrl.ser_initialized&&locks==2&&tasks==1);owner=ad.HwCtrl.ser_task.kthread_task;
  if(!strcmp(name,"ser-owner")){before=init_attempts;result=ser_init(&ad);preserved=(before==init_attempts&&owner==ad.HwCtrl.ser_task.kthread_task);}
  if(!strcmp(name,"ser-joined")){HwCtrlSerExit(&ad);assert(tasks==0&&locks==2&&ad.HwCtrl.ser_initialized);}
  if(!strcmp(name,"ser-natural-exit")){ad.HwCtrl.ser_func_state=RTMP_TASK_STAT_UNKNOWN;assert(ad.HwCtrl.ser_initialized);}
  assert(ser_exit(&ad)==0);assert(ser_exit(&ad)==0);if(!strcmp(name,"ser-reopen")){retry=ser_init(&ad);HwCtrlSerExit(&ad);assert(ser_exit(&ad)==0);}
 }else if(!strncmp(name,"hw-",3)){
  if(!strcmp(name,"hw-init-failure"))init_fail_at=1;
  if(!strcmp(name,"hw-attach-failure"))attach_fail_at=1;
  if(!strcmp(name,"hw-ser-init-failure"))init_fail_at=2;
  if(!strcmp(name,"hw-ser-attach-failure"))attach_fail_at=2;
  result=HwCtrlInit(&ad);if(result){assert(locks==1&&tasks==0&&!ad.HwCtrl.ser_initialized);HwCtrlExit(&ad);assert(locks==1);reset_faults();retry=HwCtrlInit(&ad);}assert(tasks==2&&locks==3);
  if(!strcmp(name,"hw-owner")){owner=ad.HwCtrl.HwCtrlTask.kthread_task;before=init_attempts;result=HwCtrlInit(&ad);preserved=(before==init_attempts&&owner==ad.HwCtrl.HwCtrlTask.kthread_task);}
  HwCtrlExit(&ad);HwCtrlExit(&ad);if(!strcmp(name,"hw-reopen")){retry=HwCtrlInit(&ad);HwCtrlExit(&ad);}
 }else if(!strncmp(name,"mgmt-",5)){
  if(!strcmp(name,"mgmt-init-failure"))init_fail_at=1;
  if(!strcmp(name,"mgmt-attach-failure"))attach_fail_at=1;
  result=RtmpMgmtTaskInit(&ad);if(result){assert(tasks==0&&locks==1);reset_faults();retry=RtmpMgmtTaskInit(&ad);}assert(tasks==1&&locks==2);mgmt_clear(&ad);
 }else if(!strncmp(name,"ba-",3)){
  alloc_lock(&ad.BATabLock);if(!strcmp(name,"ba-oom"))fail_at=1;result=ba_reordering_resource_init(&ad,4);if(!result){assert(!ad.mpdu_blk_pool.mem&&locks==2&&live==0);reset_faults();retry=ba_reordering_resource_init(&ad,4);}assert(live==1&&locks==2);
  if(!strcmp(name,"ba-owner")){owner=ad.mpdu_blk_pool.mem;before=attempts;result=ba_reordering_resource_init(&ad,4);preserved=(owner==ad.mpdu_blk_pool.mem&&attempts==before);}
  ba_reordering_resource_release(&ad);assert(!ad.mpdu_blk_pool.mem&&!ad.mpdu_blk_pool.freelist.next&&!ad.mpdu_blk_pool.freelist.qlen);if(!strcmp(name,"ba-reopen")){retry=ba_reordering_resource_init(&ad,4);ba_reordering_resource_release(&ad);}free_lock(&ad.BATabLock);
 }else if(!strncmp(name,"qm-",3)){
  if(!strcmp(name,"qm-init-failure"))qm_fail=1;
  if(!strcmp(name,"qm-notify-failure"))notify_fail=1;
  result=qm_init(&ad);if(result){assert(!ad.qm_ops&&!qm_live&&!notify_live);reset_faults();retry=qm_init(&ad);}if(!strcmp(name,"qm-owner")){owner=ad.qm_ops;result=qm_init(&ad);preserved=(owner==ad.qm_ops&&notify_live==1);}assert(qm_exit(&ad)==0);assert(qm_exit(&ad)==0);
 }else if(!strcmp(name,"tm-stop-refusal")||!strcmp(name,"tm-retired-refusal")){
  if(strstr(name,"stop"))ad.dma_stopping=1;else ad.dma_tasks_retired=1;
  result=tm_init(&ad);assert(result==1&&!ad.tm_qm_ops&&!ad.tm_hif_ops&&!tm_qm_live&&!tm_hif_live);
  ad.dma_stopping=0;ad.dma_tasks_retired=0;retry=tm_init(&ad);assert(retry==0);assert(tm_exit(&ad)==0);
 }else if(!strcmp(name,"tm-hif-rollback-failure")){
  tm_hif_fail=tm_qm_exit_fail=1;result=tm_init(&ad);assert(result==3&&ad.tm_qm_ops&&!ad.tm_hif_ops&&tm_qm_live&&!tm_hif_live);
  assert(tm_exit(&ad)==1&&ad.tm_qm_ops&&tm_qm_live);reset_faults();retry=tm_exit(&ad);assert(retry==0);
  assert(tm_init(&ad)==0&&tm_exit(&ad)==0);
 }else if(!strcmp(name,"tm-exit-qm-failure")||!strcmp(name,"tm-exit-hif-failure")){
  assert(tm_init(&ad)==0);if(strstr(name,"qm-failure"))tm_qm_exit_fail=1;else tm_hif_exit_fail=1;
  result=tm_exit(&ad);assert(result==1&&ad.tm_qm_ops&&ad.tm_hif_ops&&tm_qm_live&&!ad.dma_tasks_retired);
  if(tm_hif_exit_fail)assert(tm_hif_live);else assert(!tm_hif_live&&tm_hif_joined);
  reset_faults();retry=tm_exit(&ad);assert(retry==0&&!tm_qm_live&&!tm_hif_live);
 }else if(!strncmp(name,"tm-",3)){
  if(!strcmp(name,"tm-qm-failure"))tm_qm_fail=1;
  if(!strcmp(name,"tm-hif-failure"))tm_hif_fail=1;
  if(!strcmp(name,"tm-invalid-method"))cap.qm_tm=99;
  result=tm_init(&ad);if(result){assert(!ad.tm_qm_ops&&!ad.tm_hif_ops&&!tm_qm_live&&!tm_hif_live);reset_faults();cap.qm_tm=TASKLET_METHOD;retry=tm_init(&ad);}if(!strcmp(name,"tm-owner")){owner=ad.tm_qm_ops;result=tm_init(&ad);preserved=(owner==ad.tm_qm_ops&&tm_hif_live==1);}assert(tm_exit(&ad)==0);assert(tm_exit(&ad)==0);
 }else if(!strcmp(name,"sys-tr-release-failure")){
  assert(rtmp_sys_init(&ad,NULL)==TRUE);owner=ad.tr_ctl.tr_flow_ctl.TxBlockDevList;
  /* Deliberate invariant fault: exercise the real TR partial-owner refusal. */
  ad.tr_ctl.tr_flow_ctl.TxBlockDevList=NULL;result=rtmp_sys_exit(&ad);
  assert(result==FALSE&&ad.dma_quarantined&&ad.dma_stopping&&!ad.tm_qm_ops&&!ad.tm_hif_ops&&!ad.qm_ops&&tr_owned(&ad)&&software_stage&&tasks==0&&live==6&&locks==10&&timers==1);
  source_owned_released=0;
  /* Restore only the private fixture's removed pointer for leak-free process teardown. */
  ad.tr_ctl.tr_flow_ctl.TxBlockDevList=owner;ad.dma_quarantined=0;assert(rtmp_sys_exit(&ad)==TRUE);
 }else if(!strcmp(name,"sys-stop-refusal")){
  ad.dma_stopping=1;result=rtmp_sys_init(&ad,NULL);clean_check(&ad);assert(result==FALSE&&ad.WifiSysInfo==0&&!attempts&&!init_attempts);
  ad.dma_stopping=0;retry=rtmp_sys_init(&ad,NULL);assert(retry==TRUE);assert(rtmp_sys_exit(&ad)==TRUE);
 }else if(!strcmp(name,"sys-tm-rollback-failure")||!strcmp(name,"sys-task-exit-failure")||!strcmp(name,"sys-exit-failure")||!strcmp(name,"sys-init-retirement-failure")){
  if(!strcmp(name,"sys-tm-rollback-failure")){tm_hif_fail=tm_qm_exit_fail=1;result=rtmp_sys_init(&ad,NULL);}
  else if(!strcmp(name,"sys-init-retirement-failure")){tm_hif_fail=tm_retirement_fail=1;result=rtmp_sys_init(&ad,NULL);}
  else {assert(rtmp_sys_init(&ad,NULL));if(!strcmp(name,"sys-task-exit-failure")){tm_hif_exit_fail=1;result=rtmp_sys_task_exit(&ad);}else{tm_qm_exit_fail=1;result=rtmp_sys_exit(&ad);}}
  assert(ad.dma_quarantined&&ad.dma_stopping&&!ad.dma_tasks_retired&&qm_live&&tr_owned(&ad)&&software_stage&&tasks==3&&live==6&&locks==12&&timers==1);
  if(!strcmp(name,"sys-tm-rollback-failure"))assert(ad.tm_qm_ops&&!ad.tm_hif_ops&&tm_qm_live&&!tm_hif_live);
  if(!strcmp(name,"sys-task-exit-failure"))assert(ad.tm_qm_ops&&ad.tm_hif_ops&&tm_qm_live&&tm_hif_live);
  if(!strcmp(name,"sys-exit-failure"))assert(ad.tm_qm_ops&&ad.tm_hif_ops&&tm_qm_live&&!tm_hif_live);
  if(!strcmp(name,"sys-init-retirement-failure"))assert(!ad.tm_qm_ops&&!ad.tm_hif_ops&&!tm_qm_live&&!tm_hif_live);
  source_owned_released=0;
  /* Private inert fixture hygiene after the retained observation. This is
   * deliberately not a production reset, recovery or hardware-drain proof. */
  reset_faults();ad.dma_quarantined=0;assert(rtmp_sys_exit(&ad)==TRUE);
 }else if(!strncmp(name,"sys-old-",8)){
  if(!strcmp(name,"sys-old-ser")){assert(ser_init(&ad)==0);owner=ad.HwCtrl.ser_task.kthread_task;before=init_attempts;result=rtmp_sys_init(&ad,NULL);preserved=(ad.HwCtrl.ser_task.kthread_task==owner&&before==init_attempts&&ad.WifiSysInfo==0);assert(ser_exit(&ad)==0);}
  if(!strcmp(name,"sys-old-ba")){alloc_lock(&ad.BATabLock);assert(ba_reordering_resource_init(&ad,4));owner=ad.mpdu_blk_pool.mem;before=attempts;result=rtmp_sys_init(&ad,NULL);preserved=(ad.mpdu_blk_pool.mem==owner&&attempts==before&&ad.WifiSysInfo==0);ba_reordering_resource_release(&ad);free_lock(&ad.BATabLock);}
  if(!strcmp(name,"sys-old-measure")){assert(MeasureReqTabInit(&ad)==0);owner=ad.CommonCfg.pMeasureReqTab;before=attempts;result=rtmp_sys_init(&ad,NULL);preserved=(ad.CommonCfg.pMeasureReqTab==owner&&attempts==before&&ad.WifiSysInfo==0);MeasureReqTabExit(&ad);}
  if(!strcmp(name,"sys-old-tpc")){assert(TpcReqTabInit(&ad)==0);owner=ad.CommonCfg.pTpcReqTab;before=attempts;result=rtmp_sys_init(&ad,NULL);preserved=(ad.CommonCfg.pTpcReqTab==owner&&attempts==before&&ad.WifiSysInfo==0);TpcReqTabExit(&ad);}
  if(!strcmp(name,"sys-old-tr")){alloc((UCHAR**)&ad.tr_ctl.tr_flow_ctl.TxFlowBlockState,3);owner=ad.tr_ctl.tr_flow_ctl.TxFlowBlockState;before=attempts;result=rtmp_sys_init(&ad,NULL);preserved=(ad.tr_ctl.tr_flow_ctl.TxFlowBlockState==owner&&before==attempts&&ad.WifiSysInfo==0);release(owner);ad.tr_ctl.tr_flow_ctl.TxFlowBlockState=NULL;}
 }else{
  assert(!strncmp(name,"sys-",4));
  if(!strcmp(name,"sys-mgmt-init-failure"))init_fail_at=1;
  if(!strcmp(name,"sys-mgmt-attach-failure"))attach_fail_at=1;
  if(!strcmp(name,"sys-hw-init-failure"))init_fail_at=2;
  if(!strcmp(name,"sys-hw-attach-failure"))attach_fail_at=2;
  if(!strcmp(name,"sys-ser-init-failure"))init_fail_at=3;
  if(!strcmp(name,"sys-ser-attach-failure"))attach_fail_at=3;
  if(!strcmp(name,"sys-config-failure"))cfg_fail=1;
  if(!strcmp(name,"sys-ba-oom"))fail_at=1;
  if(!strcmp(name,"sys-measure-oom"))fail_at=2;
  if(!strcmp(name,"sys-tpc-oom"))fail_at=3;
  if(!strncmp(name,"sys-tr-oom",10))fail_at=3+name[10]-'0';
  if(!strcmp(name,"sys-qm-failure"))qm_fail=1;
  if(!strcmp(name,"sys-tm-qm-failure"))tm_qm_fail=1;
  if(!strcmp(name,"sys-tm-hif-failure"))tm_hif_fail=1;
  result=rtmp_sys_init(&ad,NULL);if(!result){clean_check(&ad);reset_faults();assert(!ad.dma_quarantined);/* Fresh enclosing lifecycle acquisition after complete software rollback. */ad.dma_stopping=0;ad.WifiSysInfo=0;retry=rtmp_sys_init(&ad,NULL);assert(retry==TRUE);}assert(tasks==3&&live==6&&locks==12&&timers==1&&software_stage&&qm_live&&tm_qm_live&&tm_hif_live);
  if(!strcmp(name,"sys-owner")){owner=ad.tr_ctl.tr_flow_ctl.TxBlockLock;before=init_attempts;result=rtmp_sys_init(&ad,NULL);preserved=(owner==ad.tr_ctl.tr_flow_ctl.TxBlockLock&&before==init_attempts&&ad.WifiSysInfo==1);}
  if(!strcmp(name,"sys-retired")){rtmp_sys_task_exit(&ad);assert(tasks==0&&!qm_live&&!tm_qm_live&&!tm_hif_live&&!tr_owned(&ad)&&timers==0);rtmp_sys_task_exit(&ad);}
  rtmp_sys_exit(&ad);if(!strcmp(name,"sys-reopen")){clean_check(&ad);assert(!ad.dma_quarantined);/* Fresh parent lifetime after complete exit. */ad.dma_stopping=0;retry=rtmp_sys_init(&ad,NULL);assert(retry==TRUE);rtmp_sys_exit(&ad);}
 }
 clean_check(&ad);phase=(ad.mpdu_blk_pool.lock==1);free_lock(&ad.mpdu_blk_pool.lock);
 printf("[%d,%d,%d,%d,%d,%d,%d,%d]\n",result,preserved,retry,source_owned_released,phase,live,locks,invalid);assert(live==0&&locks==0&&tasks==0&&timers==0&&invalid==0);return 0;
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
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current init sources required')
    definitions=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        found=re.findall(pattern,texts[key])
        if len(found)!=1:raise ValueError('Actual init declaration missing: '+pattern)
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
