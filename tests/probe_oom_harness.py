"""Unpublished PCI adapter construction and rollback, with inert bus seams.

Actual function bodies implement heap acquisition, partial rollback, stats,
WPF, hdev/RLM allocation, HIF lock pairing, PCI probe and final destruction.
PCI/MMIO/netdev/lock/config-value backends are bounded private models. The
hardware resource init transaction is covered by the separate resource model.
Loop bounds are reduced to three IE and three WPF slots, not target maxima.
No network, module, kernel, Flash or router runs here.
"""
import hashlib
import re

MODEL_VARIANT={'role':'unpublished-constructor-private-inert-model','MULTI_INF_SUPPORT':True,'actual_K2P_MULTI_INF_SUPPORT':False,'CONFIG_WIFI_MSI_SUPPORT':False,'native_extra_MSI_variant':True,'OS_ABL_FUNC_SUPPORT':False,'reduced_IE_slots':3,'reduced_WPF_slots':3,'native_strict_aliasing_disabled_to_match_target':True}
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'init':BASE+'embedded/common/rtmp_init.c','os':BASE+'os/linux/rt_linux.c',
 'pci':BASE+'os/linux/pci_main_dev.c','free':BASE+'os/linux/rt_profile.c',
 'hif':BASE+'embedded/common/hif_pci.c','hdev':BASE+'embedded/hw_ctrl/hdev_ctrl.c',
 'rlm':BASE+'phy/rlm_cal_cache.c','config':BASE+'embedded/wlan_config/config_basic.c',
 'header':BASE+'embedded/include/rtmp.h','os_header':BASE+'include/os/rt_linux.h',
 'config_header':BASE+'embedded/include/wlan_config/config_export.h',
 'wifi_sys':BASE+'embedded/common/wifi_sys_info.c','os_main':BASE+'os/linux/rt_main_dev.c',
 'config_phy':BASE+'embedded/wlan_config/config_phy.c','config_ht':BASE+'embedded/wlan_config/config_ht.c',
 'config_vht':BASE+'embedded/wlan_config/config_vht.c','multi':BASE+'os/linux/multi_main_dev.c'}
FUNCTION_SOURCES={'RtmpOsStatsAlloc':'os','AdapterBlockAllocateMemory':'os',
 'hdev_ctrl_init':'hdev','hdev_ctrl_exit':'hdev','rlmCalCacheInit':'rlm','rlmCalCacheDeinit':'rlm',
 'wpf_config_exit':'config','wpf_config_init':'config','RTMPInitHifAdapterBlock':'hif',
 'RTMPFreeHifAdapterBlock':'hif','RTMPFreeAdapterBlockInit':'init',
 'RTMPAllocAdapterBlock':'init','RTMPFreeAdapter':'free','RtmpRaDevCtrlExit':'init','rt_pci_probe':'pci'}
BODY_ORDER=('RtmpOsStatsAlloc','AdapterBlockAllocateMemory','hdev_ctrl_init','hdev_ctrl_exit',
 'rlmCalCacheInit','rlmCalCacheDeinit','wpf_config_exit','wpf_config_init',
 'RTMPInitHifAdapterBlock','RTMPFreeHifAdapterBlock','RTMPFreeAdapterBlockInit',
 'RTMPAllocAdapterBlock','RTMPFreeAdapter','RtmpRaDevCtrlExit','rt_pci_probe')
SOURCE_ONLY_FUNCTION_SOURCES={'wifi_sys_init':'wifi_sys','RTMPAllocGlobalUtility':'init',
 'hdev_resource_init':'hdev','hdev_resource_exit':'hdev','RtmpDmaFinalReleaseCheck':'os_main',
 'wlan_config_init':'config','wlan_config_exit':'config',
 'phy_cfg_init':'config_phy','phy_cfg_exit':'config_phy',
 'ht_cfg_init':'config_ht','ht_cfg_exit':'config_ht','vht_cfg_init':'config_vht','vht_cfg_exit':'config_vht','multi_inf_adapt_reg':'multi','multi_inf_adapt_unreg':'multi'}
SOURCE_DECLARATIONS={r'^#define NDIS_STATUS_SUCCESS\s+0x[0-9a-fA-F]+\s*$':'os_header',
 r'^#define NDIS_STATUS_FAILURE\s+0x[0-9a-fA-F]+\s*$':'os_header'}
CASE_NAMES=('ctor-oom-2','ctor-oom-3','ctor-oom-4','ctor-oom-5','ctor-oom-6','ctor-oom-7',
 'ctor-oom-8','ctor-oom-9','ctor-oom-10','ctor-oom-11','ctor-oom-12','ctor-oom-13','ctor-oom-14','ctor-oom-15',
 'probe-oom-1','probe-oom-2','probe-oom-3','probe-oom-4','probe-oom-5','probe-oom-6','probe-oom-7',
 'probe-oom-8','probe-oom-9','probe-oom-10','probe-oom-11','probe-oom-12','probe-oom-13','probe-oom-14','probe-oom-15',
 'ctor-success-free','ctor-success-devctrl-free','ctor-failure-retry','ctor-existing-owner',
 'ctor-null-handle','ctor-null-output','ctor-multi-registration-failure','probe-success-free',
 'probe-enable-failure','probe-mask-failure','probe-region-failure','probe-map-failure',
 'probe-pcie-failure','probe-netdev-failure','probe-attach-failure','probe-retained-drvdata',
 'stats-existing-owner','stats-alias-output','wpf-existing-owner','wpf-double-exit',
 'hdev-uninitialized-exit','hdev-initialized-exit','hdev-null-exit','quarantined-final-free',
 'quarantined-devctrl-free','hdev-existing-owner','probe-msi-owned-constructor-failure','probe-msi-request-failure')
FIELDS=('result','heap_live','locks_live','cookie_failure_preserved','early_publications',
 'allocations_after_locks','pci_enabled','regions_live','mapped','bus_master','drvdata_live',
 'unsafe_frees','hardware_resource_exits','owned_graph_retained','device_resource_releases')
CASE_GROUPS={'constructor-oom': ('ctor-oom-2',
                     'ctor-oom-3',
                     'ctor-oom-4',
                     'ctor-oom-5',
                     'ctor-oom-6',
                     'ctor-oom-7',
                     'ctor-oom-8',
                     'ctor-oom-9',
                     'ctor-oom-10',
                     'ctor-oom-11',
                     'ctor-oom-12',
                     'ctor-oom-13',
                     'ctor-oom-14',
                     'ctor-oom-15'),
 'probe-oom': ('probe-oom-1',
               'probe-oom-2',
               'probe-oom-3',
               'probe-oom-4',
               'probe-oom-5',
               'probe-oom-6',
               'probe-oom-7',
               'probe-oom-8',
               'probe-oom-9',
               'probe-oom-10',
               'probe-oom-11',
               'probe-oom-12',
               'probe-oom-13',
               'probe-oom-14',
               'probe-oom-15'),
 'constructor': ('ctor-success-free',
                 'ctor-success-devctrl-free',
                 'ctor-failure-retry',
                 'ctor-existing-owner',
                 'ctor-null-handle',
                 'ctor-null-output',
                 'ctor-multi-registration-failure'),
 'probe': ('probe-success-free',
           'probe-enable-failure',
           'probe-mask-failure',
           'probe-region-failure',
           'probe-map-failure',
           'probe-pcie-failure',
           'probe-netdev-failure',
           'probe-attach-failure',
           'probe-retained-drvdata'),
 'subowners': ('stats-existing-owner',
               'stats-alias-output',
               'wpf-existing-owner',
               'wpf-double-exit',
               'hdev-uninitialized-exit',
               'hdev-initialized-exit',
               'hdev-null-exit'),
 'quarantine': ('quarantined-final-free', 'quarantined-devctrl-free'),
 'extra': ('hdev-existing-owner', 'probe-msi-owned-constructor-failure', 'probe-msi-request-failure')}
EXPECTED_ROWS={'ctor-oom-2': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-3': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-4': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-5': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-6': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-7': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-8': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-9': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-10': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-11': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-12': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-13': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-14': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-oom-15': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-1': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-2': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-3': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-4': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-5': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-6': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-7': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-8': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-9': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-10': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-11': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-12': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-13': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-14': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-oom-15': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-success-free': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-success-devctrl-free': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1],
 'ctor-failure-retry': [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-existing-owner': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-null-handle': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-null-output': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'ctor-multi-registration-failure': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-success-free': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1],
 'probe-enable-failure': [-5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-mask-failure': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-region-failure': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-map-failure': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-pcie-failure': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-netdev-failure': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1],
 'probe-attach-failure': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1],
 'probe-retained-drvdata': [-16, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'stats-existing-owner': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'stats-alias-output': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'wpf-existing-owner': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'wpf-double-exit': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'hdev-uninitialized-exit': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'hdev-initialized-exit': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'hdev-null-exit': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'quarantined-final-free': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0],
 'quarantined-devctrl-free': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
 'hdev-existing-owner': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-msi-owned-constructor-failure': [-19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'probe-msi-request-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1]}
PREFIX=r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void VOID;typedef void *PVOID;typedef int INT,INT32,BOOLEAN,NDIS_STATUS;
typedef unsigned int UINT32,UINT;typedef unsigned char UCHAR;typedef unsigned long ULONG,LONG;
#define IN
#define DEVINIT
#define TRUE 1
#define FALSE 0
#define LINUX 1
#define RTMP_MAC_PCI 1
#define MT_MAC 1
#define MT7615 1
#define CONFIG_ANDES_SUPPORT 1
#define CONFIG_AP_SUPPORT 1
#define APCLI_SUPPORT 1
#define MAC_REPEATER_SUPPORT 1
#define DOT11_N_SUPPORT 1
#define UAPSD_SUPPORT 1
#define RLM_CAL_CACHE_SUPPORT 1
#define RESOURCE_PRE_ALLOC 1
#define MULTI_INF_SUPPORT 1
#define WIRELESS_EXT 22
#define MAX_LEN_OF_BSS_TABLE 3
#define MAX_VIE_LEN 8
#define WDEV_NUM_MAX 3
#define CTL_RING_SIZE 4
#define GFP_ATOMIC 0
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(4,4,198)
#define DMA_BIT_MASK(n) (n)
#define NETIF_F_HIGHDMA 1
#define OPMODE_AP 1
#define HIF_MT 1
#define MAIN_MBSSID 0
SOURCE_DEFINITIONS
#define MTWF_LOG(...) ((void)0)
#define ASSERT(v) assert(v)
#define initList(p) do{*(p)=1;}while(0)
#define os_zero_mem(p,n) memset((p),0,(n))
#define RTMPZeroMemory(p,n) memset((p),0,(n))
#define READ_ONCE(v) (v)
struct _RTMP_ADAPTER;struct net_device;
struct pci_dev {int enabled,regions,mapped,master,irq,msi_enabled;void *drvdata;int dev;};
struct os_cookie {LONG pAd_va;struct pci_dev *pci_dev;void *pDev;};
typedef struct os_cookie *POS_COOKIE;
struct wlan_config {int initialized;};struct wlan_operate {int initialized;};
struct wpf_data {int idx;void *dev;struct wlan_config *conf;struct wlan_operate *oper;};
struct wpf_ctrl {struct wpf_data pf[WDEV_NUM_MAX];};
struct _PCI_HIF_T {int MgmtRingLock,TxBmcRingLock,BcnRingLock,CtrlRingLock;
 struct {int RingLock,ring_size;} FwDwloRing;};
struct hdev_ctrl {void *priv,*cookie,*hif;};
struct net_device_stats {int value;};struct iw_statistics {int value;};
typedef struct {int values[4];} RLM_CAL_CACHE;
struct wifi_dev {int bcn_buf;};typedef struct {struct wifi_dev wdev;} BSS_STRUCT;
typedef struct _RTMP_ADAPTER {void *OS_Cookie,*stats,*iw_stats,*hdev_ctrl,*rlmCalCache;
 int RscTimerMemList,RscTaskMemList,RscLockMemList,RscTaskletMemList,RscSemMemList,RscAtomicMemList,RscTimerCreateList;
 int TimerSemLock,WdevListLock,BssInfoIdxBitMapLock,irq_lock,tssi_lock,LockInterrupt,VirtualIfLock;
 int McuCmdLock,DriverOwnLock,UAPSDEOSPLock,AutoRateLock,OpMode,quarantined;
 struct {int lock;} mpdu_blk_pool,WifiSysInfo;
 struct {int ReptCliEntryLock,CliLinkMapLock,bMACRepeaterEn;BSS_STRUCT MBSSID[1];} ApCfg;
 struct {UCHAR *pIe;} ProbeRespIE[MAX_LEN_OF_BSS_TABLE];
 struct _PCI_HIF_T PciHif;struct wpf_ctrl wpf;
} RTMP_ADAPTER,*PRTMP_ADAPTER;
struct net_device {RTMP_ADAPTER *adapter;int irq;unsigned long base_addr,features;};
typedef int RTMP_OS_NETDEV_OP_HOOK;
typedef struct {int pci_init_succeed;} RT_CMD_PCIE_INIT;
struct pci_device_id {int value;};
FUNCTION_DECLARATIONS
struct allocation {void *p;size_t bytes;int live;};
static struct allocation allocated[128];
static int allocations,allocation_attempt,fail_at,locks_live,allocations_after_locks,unsafe_frees;
static int cookie_failure_preserved,early_publications,hw_exits,owned_graph_retained;
static int fail_enable,fail_mask,fail_region,fail_map,fail_pcie,fail_netdev,fail_attach,fail_multi;
#ifdef CONFIG_WIFI_MSI_SUPPORT
static int fail_msi,msi_enables,msi_disables;
#endif
static int config_initializations,config_exits,dep_live,ring_live,sem_live,device_resource_releases;
static void **watched_output;
static int expect_cookie;static void *cookie_pointer;
static struct pci_dev pci;
static int live_heap(void){int n=0;for(int i=0;i<allocations;i++)n+=allocated[i].live;return n;}
static void *get_memory(size_t n){void *p;allocation_attempt++;
 if(watched_output&&*watched_output)early_publications++;
 if(locks_live)allocations_after_locks++;
 if(fail_at==allocation_attempt)return NULL;
 assert(allocations<128);p=malloc(n);assert(p);if(expect_cookie&&allocation_attempt==1)cookie_pointer=p;allocated[allocations++]=(struct allocation){p,n,1};return p;}
static void release_memory(void *p){int found=-1;if(!p)return;
 for(int i=allocations-1;i>=0;i--)if(allocated[i].p==p&&allocated[i].live){found=i;break;}
 if(found<0){unsafe_frees++;assert(!"unknown or duplicate free");}
 if(p==cookie_pointer)assert(((POS_COOKIE)p)->pAd_va==0);
 allocated[found].live=0;free(p);}
static int os_alloc_mem(void *ad,UCHAR **out,size_t n){(void)ad;*out=get_memory(n);return *out?NDIS_STATUS_SUCCESS:NDIS_STATUS_FAILURE;}
#define os_free_mem(p) release_memory(p)
#define RtmpOsVfree(p) release_memory(p)
static void *vmalloc(size_t n){return get_memory(n);}
static void lock_init(int *p){assert(!*p);*p=1;locks_live++;}
static void lock_free(int *p){if(*p){*p=0;locks_live--;assert(locks_live>=0);}}
#define NdisAllocateSpinLock(ad,p) lock_init(p)
#define NdisFreeSpinLock(p) lock_free(p)
static void RtmpDmaLifecycleInit(RTMP_ADAPTER *ad){assert(ad->OS_Cookie);}
static int RtmpDmaFinalReleaseCheck(RTMP_ADAPTER *ad){return ad&&!ad->quarantined;}
static void RTMPAllocGlobalUtility(void){}
static void RTMPFreeGlobalUtility(void){}
static void wifi_sys_init(RTMP_ADAPTER *ad){lock_init(&ad->WifiSysInfo.lock);}
static void wlan_config_init(struct wlan_config *c){assert(!c->initialized);c->initialized=1;config_initializations++;}
static void wlan_config_exit(struct wlan_config *c){assert(c->initialized);c->initialized=0;config_exits++;}
static int multi_inf_adapt_reg(void *ad){(void)ad;return fail_multi?NDIS_STATUS_FAILURE:NDIS_STATUS_SUCCESS;}
static int multi_inf_adapt_unreg(void *ad){(void)ad;return NDIS_STATUS_SUCCESS;}
static void HdevHwResourceExit(struct hdev_ctrl *ctrl){assert(ctrl&&ctrl->cookie&&ctrl->hif);hw_exits++;}
static void hdev_resource_exit(void *arg){struct hdev_ctrl *ctrl=arg;if(ctrl&&ctrl->cookie){HdevHwResourceExit(ctrl);ctrl->cookie=NULL;ctrl->hif=NULL;}}
#define IS_HIF_TYPE(ad,t) 0
#define AsicSetReptFuncEnable(ad,v) ((void)0)
#define RTMP_OS_FREE_TIMER(ad) ((void)0)
#define RTMP_OS_FREE_LOCK(ad) ((void)0)
#define RTMP_OS_FREE_TASKLET(ad) ((void)0)
#define RTMP_OS_FREE_TASK(ad) ((void)0)
#define RTMP_OS_FREE_SEM(ad) ((void)0)
#define RTMP_OS_FREE_ATOMIC(ad) ((void)0)
#define RTMP_SEM_EVENT_DESTORY(p) do{if(*(p)){assert(sem_live);sem_live=0;*(p)=0;}}while(0)
static void free_chip_cap_dep_data(RTMP_ADAPTER *ad){(void)ad;if(dep_live){dep_live=0;device_resource_releases++;}}
static void RTMPFreeTxRxRingMemory(RTMP_ADAPTER *ad){(void)ad;ring_live=0;}
static void completed_device_init(RTMP_ADAPTER *ad){struct hdev_ctrl *ctrl=ad->hdev_ctrl;assert(ctrl&&!ctrl->cookie&&!dep_live&&!ring_live&&!sem_live);
 ctrl->cookie=ad->OS_Cookie;ctrl->hif=&ad->PciHif;ad->AutoRateLock=1;dep_live=ring_live=sem_live=1;}
static void bcn_buf_deinit(RTMP_ADAPTER *ad,int *buffer){(void)ad;(void)buffer;}
static void *pci_get_drvdata(struct pci_dev *d){return d->drvdata;}
static void pci_set_drvdata(struct pci_dev *d,void *p){d->drvdata=p;}
static int pci_enable_device(struct pci_dev *d){if(fail_enable)return-EIO;d->enabled=1;return 0;}
static void pci_disable_device(struct pci_dev *d){assert(!d->mapped&&!d->regions&&!d->master&&!d->msi_enabled);d->enabled=0;}
static char *pci_name(struct pci_dev *d){(void)d;return "inert-pci";}
static int pci_set_dma_mask(struct pci_dev *d,int mask){assert(d->enabled&&mask==32);return fail_mask?-EIO:0;}
static int pci_set_consistent_dma_mask(struct pci_dev *d,int mask){assert(d->enabled&&mask==32);return 0;}
#ifdef CONFIG_WIFI_MSI_SUPPORT
static int RtmpOsPciMsiEnable(struct pci_dev *d){msi_enables++;if(fail_msi)return-EIO;assert(!d->msi_enabled);d->msi_enabled=1;return 0;}
static void RtmpOsPciMsiDisable(struct pci_dev *d){assert(d->msi_enabled);d->msi_enabled=0;msi_disables++;}
#endif
static int pci_request_regions(struct pci_dev *d,char *name){(void)name;assert(d->enabled);if(fail_region)return-EBUSY;d->regions=1;return 0;}
static unsigned long pci_resource_start(struct pci_dev *d,int i){assert(d->regions&&i==0);return 1;}
static unsigned long pci_resource_len(struct pci_dev *d,int i){assert(d->regions&&i==0);return 1;}
static void *ioremap(unsigned long start,unsigned long bytes){assert(start==1&&bytes==1);if(fail_map)return NULL;pci.mapped=1;return(void*)(uintptr_t)1;}
static void pci_set_master(struct pci_dev *d){assert(d->mapped);d->master=1;}
static void pci_clear_master(struct pci_dev *d){d->master=0;}
static void iounmap(void *p){assert(p==(void*)(uintptr_t)1&&!pci.master);assert(live_heap()==0);pci.mapped=0;}
static void pci_release_regions(struct pci_dev *d){assert(d->regions&&!d->mapped);d->regions=0;}
#define RTMP_DRIVER_PCI_CSR_SET(ad,addr) do{assert((ad)&&(addr)==1);}while(0)
#define RTMP_DRIVER_PCIE_INIT(ad,cfg,dev) do{assert((dev)==&pci);(cfg)->pci_init_succeed=!fail_pcie;if(!fail_pcie)completed_device_init(ad);}while(0)
static struct net_device net;
static struct net_device *RtmpPhyNetDevInit(void *arg,RTMP_OS_NETDEV_OP_HOOK *hook){RTMP_ADAPTER *ad=arg;(void)hook;
 if(fail_netdev)return NULL;
 /* Current resource transaction is separately executed by resource_init_harness. */
 assert(((struct hdev_ctrl*)ad->hdev_ctrl)->cookie==ad->OS_Cookie);
 net.adapter=ad;return &net;}
#define RTMP_DRIVER_CHIP_PREPARE(ad) ((void)0)
#define RTMP_DRIVER_OP_MODE_GET(ad,out) (*(out)=0)
static int RtmpOSNetDevAttach(ULONG mode,struct net_device *n,RTMP_OS_NETDEV_OP_HOOK *hook){(void)mode;(void)hook;assert(n==&net);return fail_attach?-EIO:0;}
static void RtmpOSNetDevFree(struct net_device *n){assert(n==&net);n->adapter=NULL;}
'''
SUFFIX=r'''
static POS_COOKIE cookie_new(void){POS_COOKIE c=NULL;os_alloc_mem(NULL,(UCHAR**)&c,sizeof(*c));assert(c);memset(c,0,sizeof(*c));c->pci_dev=&pci;return c;}
static void initialized_hdev(RTMP_ADAPTER *ad){struct hdev_ctrl *ctrl=ad->hdev_ctrl;assert(ctrl);ctrl->hif=&ad->PciHif;ctrl->cookie=ad->OS_Cookie;}
static void emit(int result){printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",result,live_heap(),locks_live,cookie_failure_preserved,early_publications,allocations_after_locks,pci.enabled,pci.regions,pci.mapped,pci.master,pci.drvdata!=NULL,unsafe_frees,hw_exits,owned_graph_retained,device_resource_releases);}
int main(int argc,char **argv){const char *name;int result=0;VOID *out=NULL;POS_COOKIE cookie=NULL;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 expect_cookie=!strncmp(name,"ctor-",5)||!strncmp(name,"probe-",6)||!strncmp(name,"quarantined-",12);
 if(!strncmp(name,"ctor-oom-",9)||!strcmp(name,"ctor-failure-retry")){
  cookie=cookie_new();fail_at=!strcmp(name,"ctor-failure-retry")?4:atoi(name+9);watched_output=&out;
  result=RTMPAllocAdapterBlock(cookie,&out);assert(result!=NDIS_STATUS_SUCCESS&&out==NULL);
  assert(cookie->pAd_va==0&&live_heap()==1&&locks_live==0);cookie_failure_preserved=1;
  if(!strcmp(name,"ctor-failure-retry")){fail_at=0;result=RTMPAllocAdapterBlock(cookie,&out);assert(result==NDIS_STATUS_SUCCESS&&out);RTMPFreeAdapter(out);}
  else os_free_mem(cookie);
 }else if(!strncmp(name,"probe-oom-",10)){
  fail_at=atoi(name+10);result=rt_pci_probe(&pci,NULL);assert(result<0&&!pci.drvdata&&live_heap()==0&&locks_live==0);
 }else if(!strcmp(name,"ctor-success-free")||!strcmp(name,"ctor-success-devctrl-free")||!strcmp(name,"ctor-existing-owner")||!strcmp(name,"ctor-multi-registration-failure")||strstr(name,"quarantined-")){
  cookie=cookie_new();watched_output=&out;fail_multi=!strcmp(name,"ctor-multi-registration-failure");result=RTMPAllocAdapterBlock(cookie,&out);
  if(fail_multi){assert(result!=NDIS_STATUS_SUCCESS&&!out&&cookie->pAd_va==0&&locks_live==0&&live_heap()==1);cookie_failure_preserved=1;os_free_mem(cookie);}
  else{
   assert(result==NDIS_STATUS_SUCCESS&&out&&cookie->pAd_va==(LONG)out);RTMP_ADAPTER *ad=out;watched_output=NULL;
   if(!strcmp(name,"ctor-existing-owner")){VOID *duplicate=(void*)(uintptr_t)1;int before=live_heap();result=RTMPAllocAdapterBlock(cookie,&duplicate);assert(result!=NDIS_STATUS_SUCCESS&&!duplicate&&live_heap()==before&&cookie->pAd_va==(LONG)ad);}
   if(strstr(name,"quarantined-")){if(!strcmp(name,"quarantined-devctrl-free"))completed_device_init(ad);int before=live_heap();ad->quarantined=1;if(!strcmp(name,"quarantined-devctrl-free"))assert(RtmpRaDevCtrlExit(ad)==FALSE);else RTMPFreeAdapter(ad);assert(live_heap()==before&&locks_live==16&&cookie->pAd_va==(LONG)ad);owned_graph_retained=1;ad->quarantined=0;}
   if(!strcmp(name,"ctor-success-devctrl-free")){completed_device_init(ad);assert(RtmpRaDevCtrlExit(ad)==TRUE);}else if(!strcmp(name,"quarantined-devctrl-free"))assert(RtmpRaDevCtrlExit(ad)==TRUE);else RTMPFreeAdapter(ad);
  }
 }else if(!strcmp(name,"ctor-null-handle")){result=RTMPAllocAdapterBlock(NULL,&out);assert(result!=NDIS_STATUS_SUCCESS&&!out);
 }else if(!strcmp(name,"ctor-null-output")){result=RTMPAllocAdapterBlock(NULL,NULL);assert(result!=NDIS_STATUS_SUCCESS);
 }else if(!strcmp(name,"hdev-existing-owner")){RTMP_ADAPTER ad;memset(&ad,0,sizeof(ad));assert(hdev_ctrl_init(&ad)==0);void *owner=ad.hdev_ctrl;int n=allocation_attempt;result=hdev_ctrl_init(&ad);assert(result==-1&&ad.hdev_ctrl==owner&&allocation_attempt==n);hdev_ctrl_exit(&ad);
 }else if(!strcmp(name,"probe-msi-owned-constructor-failure")){fail_at=2;result=rt_pci_probe(&pci,NULL);assert(result<0&&!pci.drvdata&&live_heap()==0);
 }else if(!strcmp(name,"probe-retained-drvdata")){pci.drvdata=(void*)(uintptr_t)1;result=rt_pci_probe(&pci,NULL);assert(result==-EBUSY&&allocation_attempt==0&&!pci.enabled);pci.drvdata=NULL;
 }else if(!strncmp(name,"probe-",6)){
  fail_enable=!strcmp(name,"probe-enable-failure");fail_mask=!strcmp(name,"probe-mask-failure");fail_region=!strcmp(name,"probe-region-failure");fail_map=!strcmp(name,"probe-map-failure");fail_pcie=!strcmp(name,"probe-pcie-failure");fail_netdev=!strcmp(name,"probe-netdev-failure");fail_attach=!strcmp(name,"probe-attach-failure");
#ifdef CONFIG_WIFI_MSI_SUPPORT
  fail_msi=!strcmp(name,"probe-msi-request-failure");
#endif
  result=rt_pci_probe(&pci,NULL);
  if(!strcmp(name,"probe-success-free")||!strcmp(name,"probe-msi-request-failure")){assert(result==0&&pci.drvdata==&net);assert(RtmpRaDevCtrlExit(net.adapter)==TRUE);RtmpOSNetDevFree(&net);pci.drvdata=NULL;pci_clear_master(&pci);iounmap((void*)(uintptr_t)1);pci_release_regions(&pci);
#ifdef CONFIG_WIFI_MSI_SUPPORT
   if(pci.msi_enabled)RtmpOsPciMsiDisable(&pci);
#endif
   pci_disable_device(&pci);}
  else assert(result<0&&!pci.drvdata&&live_heap()==0&&locks_live==0);
 }else if(!strcmp(name,"stats-existing-owner")){VOID *stats=get_memory(9),*iw=NULL;result=RtmpOsStatsAlloc(&stats,&iw);assert(result==FALSE&&stats&&!iw&&allocation_attempt==1);release_memory(stats);
 }else if(!strcmp(name,"stats-alias-output")){VOID *stats=NULL;result=RtmpOsStatsAlloc(&stats,&stats);assert(result==FALSE&&!stats&&allocation_attempt==0);
 }else if(!strcmp(name,"wpf-existing-owner")||!strcmp(name,"wpf-double-exit")){
  RTMP_ADAPTER ad;memset(&ad,0,sizeof(ad));assert(wpf_config_init(&ad)==NDIS_STATUS_SUCCESS);
  if(!strcmp(name,"wpf-existing-owner")){int n=allocation_attempt;void *owner=ad.wpf.pf[1].conf;result=wpf_config_init(&ad);assert(result!=NDIS_STATUS_SUCCESS&&allocation_attempt==n&&ad.wpf.pf[1].conf==owner);}
  wpf_config_exit(&ad);wpf_config_exit(&ad);assert(config_initializations==config_exits&&live_heap()==0);
 }else if(!strcmp(name,"hdev-uninitialized-exit")||!strcmp(name,"hdev-initialized-exit")||!strcmp(name,"hdev-null-exit")){
  RTMP_ADAPTER ad;memset(&ad,0,sizeof(ad));if(strcmp(name,"hdev-null-exit")){assert(hdev_ctrl_init(&ad)==0);if(!strcmp(name,"hdev-initialized-exit")){ad.OS_Cookie=(void*)(uintptr_t)1;initialized_hdev(&ad);}}
  hdev_ctrl_exit(&ad);hdev_ctrl_exit(&ad);assert(!ad.hdev_ctrl&&live_heap()==0);
 }else assert(!"unknown case");
 assert(live_heap()==0&&locks_live==0&&unsafe_frees==0&&early_publications==0&&allocations_after_locks==0);
 assert(!dep_live&&!ring_live&&!sem_live&&config_initializations==config_exits);
#ifdef CONFIG_WIFI_MSI_SUPPORT
 if(!strcmp(name,"probe-msi-owned-constructor-failure"))assert(msi_enables==1&&msi_disables==1);
 if(!strcmp(name,"probe-msi-request-failure"))assert(msi_enables==1&&msi_disables==0);
#endif
 emit(result);return 0;
}
'''

def function(text,name):
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:inline\s+)?(?:VOID|BOOLEAN|UINT|INT|INT32|int|NDIS_STATUS)\s+(?:(?:DEVINIT|DEVEXIT)\s+)?'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    found=list(re.finditer(pattern,masked,re.M))
    if len(found)!=1:raise ValueError('Missing/ambiguous probe function: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated probe function: '+name)

def declarations(texts):
    rows=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        matches=re.findall(pattern,texts[key],re.M)
        if len(matches)!=1:raise ValueError('Unique source declaration required: '+pattern)
        rows.append(matches[0])
    return '\n'.join(rows)

def function_manifest(texts):
    return {name:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}for name,key in FUNCTION_SOURCES.items()}

def source_only_manifest(texts):
    return {name:{'source':key,'execution':'source-only-not-run','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}for name,key in SOURCE_ONLY_FUNCTION_SOURCES.items()}

def model_data_hash():
    import json
    names=('MODEL_VARIANT','BASE','SOURCE_PATHS','FUNCTION_SOURCES','BODY_ORDER',
           'SOURCE_ONLY_FUNCTION_SOURCES','SOURCE_DECLARATIONS','CASE_NAMES','FIELDS',
           'CASE_GROUPS','EXPECTED_ROWS','PREFIX','SUFFIX')
    values={name:globals()[name]for name in names}
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def generate_source(texts,variant='current'):
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Current complete probe source set required')
    function_manifest(texts);source_only_manifest(texts)
    bodies={n:function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER}
    prototypes='\n'.join(body[:body.index('{')].strip()+';'for body in bodies.values())
    admission='if(!('+'||'.join('!strcmp(name,"'+name+'")'for name in CASE_NAMES)+'))return 91;'
    prefix=PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts)).replace('FUNCTION_DECLARATIONS',prototypes)
    return prefix+'\n'.join(bodies.values())+SUFFIX.replace('CASE_ADMISSION',admission)
