"""Whole PCI/adapter lifetime functions; inert hardware and real pthread locks.

The native profile uses PCI/MT_MAC with the AP subsystems represented by inert
owner seams. It checks serialized ownership and generic PCI unbind accounting,
not device DMA, Linux RTNL, topology removal, or forced module unloading.
"""
import hashlib
import re
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={
 'os':BASE+'os/linux/rt_main_dev.c','pci':BASE+'os/linux/pci_main_dev.c',
 'adapter':BASE+'embedded/common/rtmp_init.c','free':BASE+'os/linux/rt_profile.c',
 'inf':BASE+'embedded/common/rtmp_init_inf.c','hw':BASE+'hw_ctrl/hw_init.c',
 'dma':BASE+'embedded/common/cmm_mac_pci.c','asic':BASE+'hw_ctrl/cmm_asic.c',
 'header':BASE+'embedded/include/rtmp.h','os_header':BASE+'include/os/rt_linux.h',
 'cookie':BASE+'embedded/include/rtmp_os.h','flags':BASE+'embedded/include/rtmp_def.h',
 'kernel_pci':'trunk/linux-4.4.x/drivers/pci/pci-driver.c',
 'chip':BASE+'chips/mt7615.c','asic_mt':BASE+'hw_ctrl/cmm_asic_mt_dmac.c',
 'chip_cr':BASE+'include/chip/mt7615_cr.h','hif_header':BASE+'include/hif/mt_hif_pci.h',
 'dma_header':BASE+'embedded/include/rtmp_chip.h','tm':BASE+'os/linux/tm.c',
 'andes_core':BASE+'embedded/mcu/andes_core.c','andes_header':BASE+'embedded/include/mcu/andes_core.h'}
FUNCTION_SOURCES={'tm_exit': 'tm',
 'RtmpDmaStopping': 'os',
 'tm_quiesce': 'tm',
 'AndesDmaQuiesce': 'andes_core',
 'RtmpDmaMarkActive': 'os',
 'hif_set_WPDMA': 'chip',
 'MtAsicSetWPDMA': 'asic_mt',
 'RtmpDmaFinalReleaseCheck': 'os',
 'RtmpDmaLifecycleInit': 'os',
 'RtmpDmaLifecycleLock': 'os',
 'RtmpDmaLifecycleUnlock': 'os',
 'RtmpDmaQuarantined': 'os',
 'RtmpDmaResourcesMayRelease': 'os',
 'RtmpDmaLifecycleGet': 'os',
 'RtmpDmaLifecyclePut': 'os',
 'RtmpDmaQuarantine': 'os',
 'RtmpDmaTeardownCheck': 'os',
 'RtmpDmaBeginRemove': 'os',
 'AsicSetWPDMA': 'asic',
 'RT28XXDMAStop': 'dma',
 'RT28XXDMAReset': 'dma',
 'WfHifSysExit': 'adapter',
 'WfSysPosExit': 'hw',
 'RTMPDrvClose': 'inf',
 'mt_wifi_open': 'os',
 'mt_wifi_close': 'os',
 'RtmpRaDevCtrlExit': 'adapter',
 'RTMPFreeAdapter': 'free',
 'rt_pci_remove': 'pci',
 'pci_device_remove': 'kernel_pci'}
SOURCE_ONLY_FUNCTION_SOURCES={'WfInit': 'hw', 'WfMcuInit': 'hw', 'mt_wifi_init': 'inf', 'RTMPAllocAdapterBlock': 'adapter', 'rt_pci_probe': 'pci'}
BODY_ORDER=('tm_exit', 'RtmpDmaStopping', 'tm_quiesce', 'AndesDmaQuiesce', 'RtmpDmaMarkActive', 'hif_set_WPDMA', 'MtAsicSetWPDMA',
 'RtmpDmaFinalReleaseCheck', 'RtmpDmaLifecycleInit', 'RtmpDmaLifecycleLock', 'RtmpDmaLifecycleUnlock',
 'RtmpDmaQuarantined', 'RtmpDmaResourcesMayRelease', 'RtmpDmaLifecycleGet', 'RtmpDmaLifecyclePut', 'RtmpDmaQuarantine',
 'RtmpDmaTeardownCheck', 'RtmpDmaBeginRemove', 'AsicSetWPDMA', 'RT28XXDMAStop', 'RT28XXDMAReset', 'WfHifSysExit',
 'WfSysPosExit', 'RTMPDrvClose', 'mt_wifi_open', 'mt_wifi_close', 'RtmpRaDevCtrlExit', 'RTMPFreeAdapter',
 'rt_pci_remove', 'pci_device_remove')
CASE_GROUPS={'balanced': ('get-put', 'close-idle', 'close-repeat'),
 'duplicate': ('get-duplicate',),
 'module-failure': ('get-module-going', 'enable-unpinned', 'open-irq-failure'),
 'busy-close': ('close-busy',),
 'stop-failure': ('close-stop-failure', 'close-reset-failure', 'close-tasklet-failure'),
 'missing-device': ('close-device-missing',),
 'first-enable': ('first-enable-busy', 'first-enable-stop-failure', 'first-enable-idle'),
 'busy-remove': ('remove-busy', 'remove-stop-failure', 'remove-busy-repeat', 'core-remove-busy',
                 'core-remove-first-enable-busy'),
 'sticky': ('quarantine-retry-idle', 'quarantine-enable', 'quarantine-put'),
 'remove-success': ('remove-idle', 'core-remove-idle', 'remove-never-enabled', 'remove-after-failed-enable'),
 'adapter-guard': ('adapter-exit-quarantine', 'adapter-free-quarantine', 'adapter-exit-active', 'adapter-free-active'),
 'interleaved': ('concurrent-close-open-idle', 'concurrent-close-open-busy', 'concurrent-remove-close-busy',
                 'concurrent-stop-denies-enable', 'terminal-release-denies-open')}
CASE_NAMES=('get-put', 'close-idle', 'close-repeat', 'get-duplicate', 'get-module-going', 'enable-unpinned', 'open-irq-failure',
 'close-busy', 'close-stop-failure', 'close-reset-failure', 'close-tasklet-failure', 'close-device-missing',
 'first-enable-busy', 'first-enable-stop-failure', 'first-enable-idle', 'remove-busy', 'remove-stop-failure',
 'remove-busy-repeat', 'core-remove-busy', 'core-remove-first-enable-busy', 'quarantine-retry-idle',
 'quarantine-enable', 'quarantine-put', 'remove-idle', 'core-remove-idle', 'remove-never-enabled',
 'remove-after-failed-enable', 'adapter-exit-quarantine', 'adapter-free-quarantine', 'adapter-exit-active',
 'adapter-free-active', 'concurrent-close-open-idle', 'concurrent-close-open-busy', 'concurrent-remove-close-busy',
 'concurrent-stop-denies-enable', 'terminal-release-denies-open')
FIELDS=('result', 'pinned', 'quarantined', 'stopping', 'removing', 'running', 'quiesced', 'module_refs', 'pci_refs',
 'adapter_live', 'netdev_live', 'rings_live', 'tokens_live', 'ring_alloc_live', 'mmio_live', 'regions_live', 'irq_live',
 'workers_live', 'unsafe_frees', 'free_count', 'init_calls', 'close_calls', 'unregister_calls', 'enable_calls',
 'disable_calls', 'idle_calls', 'reset_calls', 'module_gets', 'module_puts', 'pci_gets', 'pci_puts', 'core_irq_frees',
 'state_lock_live', 'life_lock_live')
EXPECTED_ROWS={'get-put': [0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1],
 'close-idle': [0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 4, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1],
 'close-repeat': [0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 4, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1],
 'get-duplicate': [0, 1, 0, 0, 0, 0, 1, 1, 2, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1,
                   1],
 'get-module-going': [-16, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0,
                      1, 1],
 'enable-unpinned': [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
                     1],
 'open-irq-failure': [-16, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0,
                      1, 1],
 'close-busy': [-5, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1],
 'close-stop-failure': [-5, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0,
                        1, 1],
 'close-reset-failure': [-5, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 0, 1, 0,
                         0, 1, 1],
 'close-tasklet-failure': [-5, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0,
                           0, 1, 1],
 'close-device-missing': [-5, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0,
                          0, 1, 1],
 'first-enable-busy': [-5, 1, 1, 1, 0, 0, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0,
                       1, 1],
 'first-enable-stop-failure': [-5, 1, 1, 1, 0, 0, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0,
                               1, 0, 0, 1, 1],
 'first-enable-idle': [-1, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 4, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0,
                       1, 1],
 'remove-busy': [0, 1, 1, 1, 1, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1],
 'remove-stop-failure': [0, 1, 1, 1, 1, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0,
                         1, 1],
 'remove-busy-repeat': [0, 1, 1, 1, 1, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0,
                        1, 1],
 'core-remove-busy': [0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1,
                      1],
 'core-remove-first-enable-busy': [0, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1,
                                   0, 1, 1, 1, 1, 1],
 'quarantine-retry-idle': [-16, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1,
                           0, 0, 1, 1],
 'quarantine-enable': [0, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0,
                       1, 1],
 'quarantine-put': [0, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0, 1,
                    1],
 'remove-idle': [0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 9, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
 'core-remove-idle': [0, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 9, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 0,
                      0],
 'remove-never-enabled': [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                          0, 0, 0],
 'remove-after-failed-enable': [0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 9, 1, 1, 1, 1, 1, 1, 1, 1, 1,
                                1, 1, 0, 0, 0],
 'adapter-exit-quarantine': [0, 1, 1, 1, 1, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1,
                             0, 0, 1, 1],
 'adapter-free-quarantine': [0, 1, 1, 1, 1, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1,
                             0, 0, 1, 1],
 'adapter-exit-active': [0, 1, 0, 0, 1, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0,
                         1, 1],
 'adapter-free-active': [0, 1, 0, 0, 1, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0,
                         1, 1],
 'concurrent-close-open-idle': [0, 1, 0, 0, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 4, 2, 1, 0, 2, 1, 1, 1, 2, 1,
                                2, 1, 0, 1, 1],
 'concurrent-close-open-busy': [-16, 1, 1, 1, 0, 1, 0, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0,
                                1, 0, 0, 1, 1],
 'concurrent-remove-close-busy': [-5, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1,
                                  0, 1, 1, 1, 1, 1],
 'concurrent-stop-denies-enable': [0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 4, 1, 1, 0, 1, 1, 1, 1, 1,
                                   1, 1, 1, 0, 1, 1],
 'terminal-release-denies-open': [-16, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                  0, 0, 0, 0, 1, 1]}
SOURCE_DECLARATIONS={'^#define NDIS_STATUS_SUCCESS\\s+0x[0-9a-fA-F]+\\s*$': 'os_header',
 '^#define NDIS_STATUS_FAILURE\\s+0x[0-9a-fA-F]+\\s*$': 'os_header',
 '^#define fRTMP_ADAPTER_NIC_NOT_EXIST[^\\n]*': 'flags',
 '^#define fRTMP_ADAPTER_START_UP[^\\n]*': 'flags',
 '^#define fRTMP_ADAPTER_HALT_IN_PROGRESS[^\\n]*': 'flags',
 '^#define fRTMP_ADAPTER_POLL_IDLE[^\\n]*': 'flags',
 '^#define fRTMP_ADAPTER_INTERRUPT_ACTIVE[^\\n]*': 'flags',
 '^#define fRTMP_ADAPTER_INTERRUPT_REGISTER_TO_OS[^\\n]*': 'flags',
 '^#define fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD[^\\n]*': 'flags',
 '^#define MT_HIF_BASE[^\\n]*': 'hif_header',
 '^#define MT_WPDMA_GLO_CFG\\s+[^\\n]*': 'hif_header',
 '#ifdef RT_BIG_ENDIAN[\\s\\S]*?#endif /\\* RT_BIG_ENDIAN \\*/': 'chip_cr',
 '^#define MULTI_DMA_EN_FEATURE_2\\s+[^\\n]*': 'chip_cr',
 '^#define MULTI_DMA_EN_FEATURE_2_PREFETCH\\s+[^\\n]*': 'chip_cr',
 'enum \\{\\s*PDMA_TX,\\s*PDMA_RX,\\s*PDMA_TX_RX,\\s*\\};': 'dma_header',
 'enum \\{\\s*MCU_INIT,\\s*MCU_TX_HALT,\\s*MCU_RX_HALT,\\s*\\};': 'andes_header'}
PREFIX=r"""
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef void VOID,PKT_TOKEN_CB;
typedef int BOOLEAN,INT,INT32,NDIS_STATUS,MAC_TABLE;
typedef unsigned char UINT8;
typedef unsigned int UINT32,UINT,ra_dma_addr_t,dma_addr_t;
typedef unsigned long ULONG;
typedef char RTMP_STRING;
#define TRUE 1
#define FALSE 0
#define IN
#define LINUX
#define MT_MAC
#define RTMP_PCI_SUPPORT
#define RTMP_MAC_PCI
#define RESOURCE_PRE_ALLOC
#define ERR_RECOVERY
#define DEVEXIT
#define DEVINIT
SOURCE_DEFINITIONS
#define HIF_MT 2
#define PCI_D0 0
#define PCI_UNKNOWN 5
#define RTMP_HALT 1
#define RTMP_DEV_INF_PCI 1
#define RTMP_DEV_INF_PCIE 2
#define MAX_LEN_OF_BSS_TABLE 2
#define MTWF_LOG(...) ((void)0)
#define ASSERT assert
#define READ_ONCE(v) __atomic_load_n(&(v),__ATOMIC_ACQUIRE)
#define WRITE_ONCE(v,n) __atomic_store_n(&(v),(n),__ATOMIC_RELEASE)
struct _RTMP_ADAPTER;
struct net_device {int irq;unsigned long base_addr;struct _RTMP_ADAPTER *adapter;};
typedef struct net_device *PNET_DEV;
struct pci_dev;
struct device {struct pci_dev *pci;};
struct pci_driver {void (*remove)(struct pci_dev *);};
struct pci_dev {struct device dev;struct net_device *data;struct pci_driver *driver;
 int enabled,master,current_state;};
typedef struct {pthread_mutex_t dma_lifecycle_lock,dma_state_lock;struct pci_dev *pci_dev;} COOKIE,*POS_COOKIE;
struct _PCI_HIF_T {int MgmtRingLock,TxBmcRingLock,BcnRingLock,CtrlRingLock;struct {int RingLock;} FwDwloRing;};
struct MCU_CTRL {unsigned long flags;int cmd_msg_task;};
struct tm_ops {int (*exit)(struct _RTMP_ADAPTER *);};
struct _RTMP_CHIP_CAP {int WPDMABurstSIZE;};
typedef struct _RTMP_ADAPTER {
 void *OS_Cookie,*hdev_ctrl,*PktTokenCb,*iw_stats,*stats,*EEPROMImage;struct net_device *net_dev;struct tm_ops *tm_qm_ops,*tm_hif_ops;
 int dma_lifecycle_pinned,dma_quarantined,dma_stopping,dma_removing,dma_running,dma_quiesced,dma_tasks_retired,dma_cmd_task_retired,dma_irq_registered;
 unsigned flags;struct MCU_CTRL MCUCtrl;struct {int bCountryFlag;} CommonCfg;
 int infType,DeQueueRunning[2],MacTab,CmdQLock,TimerQLock,AutoRateLock,BssInfoIdxBitMapLock,WdevListLock;
 int irq_lock,McuCmdLock,LockInterrupt,tssi_lock;
 struct {int queues_retired;} ErrRecoveryCtl;
 struct {void *pIe;} ProbeRespIE[MAX_LEN_OF_BSS_TABLE];
 int Avg_NF[2],Avg_NFx16[2];
} RTMP_ADAPTER,*PRTMP_ADAPTER;
FUNCTION_DECLARATIONS
static struct _RTMP_CHIP_CAP chipcap;
static struct _PCI_HIF_T hif;
static RTMP_ADAPTER *active_ad;
static struct pci_dev *active_pci;
static int module_refs,pci_refs,module_gets,module_puts,pci_gets,pci_puts,module_allowed=1;
static int adapter_live=1,netdev_live=1,rings_live=1,tokens_live=0,ring_alloc_live=1,mmio_live=1,regions_live=1,irq_live,workers_live;
static int unsafe_frees,free_count,init_calls,close_calls,unregister_calls,enable_calls,disable_calls,idle_calls,reset_calls;
static int idle_ok=1,disable_ok=1,reset_ok=1,init_ok=1,request_ok=1,core_irq_frees,pm_calls;
static int state_lock_live,life_lock_live,final_release_authorized;
static int retire_ok=1,retire_calls,command_retire_calls,irq_synchronizes;
static int fixture_task_exit(RTMP_ADAPTER *ad){assert(ad==active_ad);retire_calls++;return retire_ok?0:1;}
static struct tm_ops fixture_qm_ops={fixture_task_exit},fixture_hif_ops={fixture_task_exit};
#define OS_TEST_BIT(n,p) (((*(p))&(1UL<<(n)))!=0)
#define RTMP_OS_TASKLET_KILL(p) ((void)(p),command_retire_calls++)
static void synchronize_irq(int irq){assert(irq==3);irq_synchronizes++;}
#define rtnl_lock() ((void)0)
#define rtnl_unlock() ((void)0)
static pthread_mutex_t schedule_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t schedule_condition=PTHREAD_COND_INITIALIZER;
static int pause_on_idle,idle_entered,release_idle,thread_started[2],thread_result[2];
static void wait_for_idle_release(void){
 if(!pause_on_idle)return;
 assert(!pthread_mutex_lock(&schedule_lock));
 idle_entered=1;assert(!pthread_cond_broadcast(&schedule_condition));
 while(!release_idle)assert(!pthread_cond_wait(&schedule_condition,&schedule_lock));
 assert(!pthread_mutex_unlock(&schedule_lock));
}
static int events[512],event_count;
static pthread_mutex_t record_lock=PTHREAD_MUTEX_INITIALIZER;
static void event(int n){assert(!pthread_mutex_lock(&record_lock));assert(event_count<512);
 events[event_count++]=n;assert(!pthread_mutex_unlock(&record_lock));}
static void assert_owner(void){assert(active_ad);}
static void release_owner(int *live,int id){assert_owner();event(id);
 if(!(adapter_live?RtmpDmaResourcesMayRelease(active_ad):final_release_authorized)){unsafe_frees++;assert(0);}
 if(!*live){unsafe_frees++;assert(0);}*live=0;free_count++;}
static int IS_PCI_INF(RTMP_ADAPTER *ad){(void)ad;return 0;}
static int IS_PCIE_INF(RTMP_ADAPTER *ad){(void)ad;return 1;}
#define IS_HIF_TYPE(p,n) ((void)(p),(void)(n),1)
#define IS_MT7637(p) ((void)(p),0)
#define RTMP_SET_FLAG(p,f) (((RTMP_ADAPTER *)(p))->flags|=(f))
#define RTMP_CLEAR_FLAG(p,f) (((RTMP_ADAPTER *)(p))->flags&=~(f))
#define RTMP_TEST_FLAG(p,f) ((((RTMP_ADAPTER *)(p))->flags&(f))!=0)
#define GET_PAD_FROM_NET_DEV(p,n) ((p)=(n)->adapter)
#define GET_NUM_OF_TX_RING(p) ((void)(p),2)
#define spin_lock_irqsave(p,f) do{(f)=0;assert(!pthread_mutex_lock(p));}while(0)
#define spin_unlock_irqrestore(p,f) do{(void)(f);assert(!pthread_mutex_unlock(p));}while(0)
#define mutex_init(p) do{assert(!pthread_mutex_init((p),NULL));life_lock_live++;}while(0)
#define mutex_lock(p) do{assert(!pthread_mutex_lock(p));}while(0)
#define mutex_unlock(p) do{assert(!pthread_mutex_unlock(p));}while(0)
#define mutex_destroy(p) do{assert(!pthread_mutex_destroy(p));life_lock_live--;}while(0)
#define spin_lock_init(p) do{assert(!pthread_mutex_init((p),NULL));state_lock_live++;}while(0)
static void NdisFreeSpinLock(void *lock){(void)lock;}
static int module_marker;
#define THIS_MODULE (&module_marker)
static int try_module_get(void *module){assert(module==THIS_MODULE);event(1);module_gets++;
 if(!module_allowed){return 0;}module_refs++;return 1;}
static void module_put(void *module){assert(module==THIS_MODULE&&module_refs>0);event(2);module_puts++;module_refs--;}
static struct pci_dev *pci_dev_get(struct pci_dev *p){assert(p==active_pci&&pci_refs>0);event(3);pci_gets++;pci_refs++;return p;}
static void pci_dev_put(struct pci_dev *p){assert(p==active_pci&&pci_refs>0);event(4);pci_puts++;pci_refs--;}
static void pci_clear_master(struct pci_dev *p){assert(p==active_pci);event(5);p->master=0;}
static int pci_is_enabled(struct pci_dev *p){return p->enabled>0;}
static void pci_disable_device(struct pci_dev *p){assert(p==active_pci&&p->enabled>0);event(6);p->enabled--;}
static struct net_device *pci_get_drvdata(struct pci_dev *p){assert(p==active_pci);return p->data;}
static void pci_set_drvdata(struct pci_dev *p,void *data){assert(p==active_pci&&!data);event(7);p->data=data;}
static void pci_release_regions(struct pci_dev *p){assert(p==active_pci);release_owner(&regions_live,8);}
static void iounmap(void *address){assert(address==(void *)(uintptr_t)0x1000);release_owner(&mmio_live,9);}
static void netif_tx_stop_all_queues(struct net_device *n){assert(n==active_ad->net_dev);event(10);}
static void netif_carrier_off(struct net_device *n){assert(n==active_ad->net_dev);event(11);}
static void interrupt_disable(RTMP_ADAPTER *ad){assert(ad==active_ad);event(12);RTMP_CLEAR_FLAG(ad,fRTMP_ADAPTER_INTERRUPT_ACTIVE);}
#define RTMP_ASIC_INTERRUPT_DISABLE(p) interrupt_disable(p)
static struct _RTMP_CHIP_CAP *hc_get_chip_cap(void *p){(void)p;return &chipcap;}
static struct _PCI_HIF_T *hc_get_hif_ctrl(void *p){(void)p;return &hif;}
struct _RTMP_CHIP_OP {int (*hif_set_dma)(RTMP_ADAPTER *,INT32,BOOLEAN,UINT8);};
static struct _RTMP_CHIP_OP chipops;
static struct _RTMP_CHIP_OP *hc_get_chip_ops(void *p){(void)p;return &chipops;}
static UINT32 dma_word;
#define BIT23 (1U<<23)
#define CONFIG_RALINK_MT7621
#define MTK_REV_GTE(p,c,r) ((void)(p),1)
static void model_hif_read(RTMP_ADAPTER *p,int reg,UINT32 *value){assert(p==active_ad&&reg==MT_WPDMA_GLO_CFG);*value=dma_word;}
static void model_hif_write(RTMP_ADAPTER *p,int reg,UINT32 value){WPDMA_GLO_CFG_STRUC word;assert(p==active_ad&&reg==MT_WPDMA_GLO_CFG);
 word.word=value;dma_word=value;
 if(word.MT7615_field.EnableTxDMA||word.MT7615_field.EnableRxDMA){enable_calls++;event(13);}else{disable_calls++;event(14);}}
#define HIF_IO_READ32(p,r,v) model_hif_read(p,r,v)
#define HIF_IO_WRITE32(p,r,v) model_hif_write(p,r,v)
#define HW_IO_READ32(p,r,v) ((void)(p),(void)(r),*(v)=0)
#define HW_IO_WRITE32(p,r,v) ((void)(p),(void)(r),(void)(v))
static int fixture_set_dma(RTMP_ADAPTER *p,INT32 txrx,BOOLEAN enable,UINT8 burst){
 if(!enable&&!disable_ok){disable_calls++;event(14);return 0;}return hif_set_WPDMA(p,txrx,enable,burst);}
static int AsicWaitPDMAIdle(RTMP_ADAPTER *p,int round,int usec){(void)round;(void)usec;
 event(15);idle_calls++;wait_for_idle_release();return idle_ok&&!RTMP_TEST_FLAG(p,fRTMP_ADAPTER_NIC_NOT_EXIST);}
static int AsicResetWPDMA(RTMP_ADAPTER *p){assert(p==active_ad);event(16);reset_calls++;return reset_ok;}
static void AsicNotSupportFunc(RTMP_ADAPTER *p,const char *name){(void)p;(void)name;assert(0);}
static void RtmpusecDelay(int value){(void)value;}
static void RTMPResetTxRxRingMemory(RTMP_ADAPTER *p){assert(p==active_ad);release_owner(&rings_live,17);}
static void RTMPFreeTxRxRingMemory(RTMP_ADAPTER *p){assert(p==active_ad);if(rings_live){release_owner(&rings_live,18);}if(ring_alloc_live){release_owner(&ring_alloc_live,32);}}
static void cut_through_deinit(PKT_TOKEN_CB **p){assert(p==&active_ad->PktTokenCb);if(*p){release_owner(&tokens_live,19);*p=NULL;}}
static void WfEPROMSysExit(RTMP_ADAPTER *p){assert(p==active_ad);event(20);}
static void WfMcuSysExit(RTMP_ADAPTER *p){assert(p==active_ad);event(21);}
static void software_exit(RTMP_ADAPTER *p){assert(p==active_ad);close_calls++;if(workers_live){release_owner(&workers_live,22);}}
#define MlmeHalt(p) ((void)(p))
#define MTPciPollTxRxEmpty(p) ((void)(p))
#define HcSetAllSupportedBandsRadioOff(p) ((void)(p))
#define RT28xxPciAsicRadioOff(p,a,b) ((void)(p),(void)(a),(void)(b),1)
#define MeasureReqTabExit(p) ((void)(p))
#define TpcReqTabExit(p) ((void)(p))
#define RtmpMgmtTaskExit(p) software_exit(p)
#define HwCtrlExit(p) ((void)(p))
#define HwCtrlSerExit(p) ((void)(p))
#define qm_exit(p) ((void)(p))
#define tr_ctl_exit(p) ((void)(p))
#define RTMP_AllTimerListRelease(p) ((void)(p))
#define ba_reordering_resource_release(p) ((void)(p))
#define rtmp_cfg_exit(p) ((void)(p))
#define ExitTxSTypeTable(p) ((void)(p))
#define BackgroundScanDeInit(p) ((void)(p))
#define NdisZeroMemory(p,n) memset((p),0,(n))
#define NICRestartFirmware(p) ((void)(p),0)
#define DISABLE_TX_RX(p,n) ((void)(p),(void)(n))
#define RTMP_SEM_EVENT_DESTORY(p) ((void)(p))
#define free_chip_cap_dep_data(p) ((void)(p))
#define wpf_config_exit(p) ((void)(p))
#define RTMP_OS_FREE_TIMER(p) ((void)(p))
#define RTMP_OS_FREE_LOCK(p) ((void)(p))
#define RTMP_OS_FREE_TASKLET(p) ((void)(p))
#define RTMP_OS_FREE_TASK(p) ((void)(p))
#define RTMP_OS_FREE_SEM(p) ((void)(p))
#define RTMP_OS_FREE_ATOMIC(p) ((void)(p))
#define RTMPFreeHifAdapterBlock(p) ((void)(p))
#define hdev_ctrl_exit(p) ((void)(p))
#define RTMPFreeGlobalUtility() ((void)0)
static void os_free_mem(void *p){if(p==active_ad->OS_Cookie){POS_COOKIE cookie=p;
 assert(!pthread_mutex_destroy(&cookie->dma_lifecycle_lock));life_lock_live--;
 assert(!pthread_mutex_destroy(&cookie->dma_state_lock));state_lock_live--;}}
static void RtmpOsVfree(void *p){assert(p==active_ad);final_release_authorized=RtmpDmaResourcesMayRelease(active_ad);release_owner(&adapter_live,23);}
static void RtmpOSNetDevFree(struct net_device *n){assert(n==active_ad->net_dev&&!active_pci->data);release_owner(&netdev_live,24);}
static void RtmpOSNetDevDetach(struct net_device *n){assert(n==active_ad->net_dev);event(25);}
#define RTMP_DRIVER_MCU_SLEEP_CLEAR(p) ((void)(p))
#define RTMP_DRIVER_OP_MODE_GET(p,n) ((void)(p),*(n)=0)
#define RTMP_DRIVER_IRQ_INIT(p) ((void)(p))
static int load_dev_l1profile(void *p){(void)p;return 0;}
static char *mac,*hostname;
static int RtmpOSIRQRequest(struct net_device *n){assert(n==active_ad->net_dev);event(26);if(!request_ok)return-EBUSY;assert(!irq_live);irq_live++;RTMP_SET_FLAG(active_ad,fRTMP_ADAPTER_INTERRUPT_REGISTER_TO_OS|fRTMP_ADAPTER_INTERRUPT_ACTIVE);return 0;}
static void release_irq(void *p){assert(p==active_ad);release_owner(&irq_live,27);RTMP_CLEAR_FLAG(active_ad,fRTMP_ADAPTER_INTERRUPT_REGISTER_TO_OS);}
#define RTMP_DRIVER_IRQ_RELEASE(p) release_irq(p)
#define RTMP_OS_IRQ_RELEASE(p,n) ((void)(n),release_irq(p))
#define WLAN_HOOK_CALL(h,p,n) ((void)(p),(void)(n))
static void RTMPDrvOpen(void *p){assert(p==active_ad);event(28);}
static int mt_wifi_init(void *p,char *mac_arg,char *host_arg){RTMP_ADAPTER *ad=p;(void)mac_arg;(void)host_arg;
 event(29);init_calls++;workers_live=1;rings_live=tokens_live=1;ad->PktTokenCb=ad;ad->tm_qm_ops=&fixture_qm_ops;ad->tm_hif_ops=&fixture_hif_ops;ad->MCUCtrl.flags=1UL<<MCU_INIT;assert(RtmpDmaMarkActive(ad));
 assert(AsicSetWPDMA(ad,PDMA_TX_RX,1));
 if(!init_ok){if(RtmpDmaTeardownCheck(ad)){software_exit(ad);assert(tm_exit(ad)==0);assert(WfSysPosExit(ad)==0);}return 0;}return 1;}
static int RtmpPhyNetDevExit(void *adapter,struct net_device *net){assert(adapter==active_ad&&net==active_ad->net_dev);
 event(31);unregister_calls++;(void)mt_wifi_close(net);return 1;}
static struct pci_dev *to_pci_dev(struct device *dev){return dev->pci;}
static void pm_runtime_get_sync(struct device *dev){assert(dev==&active_pci->dev);pm_calls++;}
static void pm_runtime_put_noidle(struct device *dev){assert(dev==&active_pci->dev);pm_calls++;}
static void pm_runtime_put_sync(struct device *dev){assert(dev==&active_pci->dev);pm_calls++;}
static void pcibios_free_irq(struct pci_dev *p){assert(p==active_pci);event(30);core_irq_frees++;}
"""
SUFFIX=r"""

static void retained(void){
 assert(adapter_live&&netdev_live&&rings_live&&ring_alloc_live&&tokens_live&&mmio_live&&regions_live);
 assert(active_ad->dma_lifecycle_pinned&&active_ad->dma_quarantined&&active_ad->dma_stopping);
 assert(module_refs==1&&pci_refs>=1&&unsafe_frees==0&&free_count==0);
 assert(!active_pci->master&&active_pci->data==active_ad->net_dev);
 assert(irq_synchronizes==1&&retire_calls==2);
 assert(active_ad->dma_irq_registered&&active_ad->dma_tasks_retired);
 assert(active_ad->tm_qm_ops==&fixture_qm_ops&&active_ad->tm_hif_ops==&fixture_hif_ops);
 assert(!RTMP_TEST_FLAG(active_ad,fRTMP_ADAPTER_INTERRUPT_ACTIVE));
 if(retire_ok)assert(command_retire_calls==1);else assert(command_retire_calls==0);
}
static void acquired(void){
 RtmpDmaLifecycleLock(active_ad);assert(RtmpDmaLifecycleGet(active_ad));RtmpDmaLifecycleUnlock(active_ad);
 assert(module_refs==1&&pci_refs==2&&active_ad->dma_lifecycle_pinned);
}
static void started(void){
 assert(mt_wifi_open(active_ad->net_dev)==0);
 assert(active_ad->dma_running&&irq_live&&workers_live&&module_refs==1&&pci_refs==2);
}
static void *thread_run(void *argument){
 int kind=(int)(intptr_t)argument;int index=kind>=10?1:0;kind%=10;
 assert(!pthread_mutex_lock(&schedule_lock));thread_started[index]=1;
 assert(!pthread_cond_broadcast(&schedule_condition));assert(!pthread_mutex_unlock(&schedule_lock));
 if(kind==0)thread_result[index]=mt_wifi_close(active_ad->net_dev);
 else if(kind==1)thread_result[index]=mt_wifi_open(active_ad->net_dev);
 else if(kind==2){pci_device_remove(&active_pci->dev);thread_result[index]=0;}
 else assert(0);
 return NULL;
}
static void begin_paused_thread(pthread_t *thread,int kind){
 pause_on_idle=1;
 assert(!pthread_create(thread,NULL,thread_run,(void *)(intptr_t)kind));
 assert(!pthread_mutex_lock(&schedule_lock));
 while(!idle_entered)assert(!pthread_cond_wait(&schedule_condition,&schedule_lock));
 assert(!pthread_mutex_unlock(&schedule_lock));
}
static void start_second_thread(pthread_t *thread,int kind){
 assert(!pthread_create(thread,NULL,thread_run,(void *)(intptr_t)(kind+10)));
 assert(!pthread_mutex_lock(&schedule_lock));
 while(!thread_started[1])assert(!pthread_cond_wait(&schedule_condition,&schedule_lock));
 assert(!pthread_mutex_unlock(&schedule_lock));
}
static void release_paused_thread(void){
 assert(!pthread_mutex_lock(&schedule_lock));release_idle=1;
 assert(!pthread_cond_broadcast(&schedule_condition));assert(!pthread_mutex_unlock(&schedule_lock));
}
int main(int argc,char **argv){
 RTMP_ADAPTER ad;COOKIE cookie;struct net_device net;struct pci_dev pci;struct pci_driver driver;
 const char *name;int result=0;pthread_t first,second;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&ad,0,sizeof(ad));memset(&cookie,0,sizeof(cookie));memset(&net,0,sizeof(net));
 memset(&pci,0,sizeof(pci));memset(&driver,0,sizeof(driver));
 active_ad=&ad;active_pci=&pci;ad.OS_Cookie=&cookie;cookie.pci_dev=&pci;ad.net_dev=&net;
 net.adapter=&ad;net.irq=3;net.base_addr=0x1000;pci.data=&net;pci.dev.pci=&pci;pci.driver=&driver;
 pci.enabled=pci.master=1;pci.current_state=PCI_D0;pci_refs=1;driver.remove=rt_pci_remove;
 chipops.hif_set_dma=fixture_set_dma;RtmpDmaLifecycleInit(&ad);
 if(!strcmp(name,"get-put")){
  acquired();assert(RtmpDmaTeardownCheck(&ad));RtmpDmaLifecyclePut(&ad);
  assert(module_refs==0&&pci_refs==1&&!ad.dma_lifecycle_pinned&&ad.dma_quiesced);
 }else if(!strcmp(name,"get-duplicate")){
  acquired();RtmpDmaLifecycleLock(&ad);result=RtmpDmaLifecycleGet(&ad);RtmpDmaLifecycleUnlock(&ad);
  assert(!result&&module_refs==1&&pci_refs==2&&module_gets==1&&pci_gets==1);
 }else if(!strcmp(name,"get-module-going")){
  module_allowed=0;result=mt_wifi_open(&net);
  assert(result&&init_calls==0&&enable_calls==0&&irq_live==0&&module_refs==0&&pci_refs==1);
 }else if(!strcmp(name,"open-irq-failure")){
  request_ok=0;result=mt_wifi_open(&net);
  assert(result==-EBUSY&&init_calls==0&&enable_calls==0&&irq_live==0&&module_refs==0&&pci_refs==1);
  assert(!ad.dma_lifecycle_pinned&&module_puts==1&&pci_puts==1&&idle_calls==0);
 }else if(!strcmp(name,"enable-unpinned")){
  result=AsicSetWPDMA(&ad,PDMA_TX_RX,1);assert(!result&&enable_calls==0);
 }else if(!strcmp(name,"close-idle")||!strcmp(name,"close-repeat")){
  started();result=mt_wifi_close(&net);if(strstr(name,"repeat"))assert(mt_wifi_close(&net)==0);assert(!result&&!ad.dma_running&&!ad.dma_lifecycle_pinned);
  assert(!rings_live&&!tokens_live&&!workers_live&&!irq_live&&ring_alloc_live&&module_refs==0&&pci_refs==1);
 }else if(!strcmp(name,"close-busy")||!strcmp(name,"close-stop-failure")||
          !strcmp(name,"close-reset-failure")||!strcmp(name,"close-device-missing")||!strcmp(name,"close-tasklet-failure")){
  started();
  if(!strcmp(name,"close-tasklet-failure"))retire_ok=0;
  if(!strcmp(name,"close-busy"))idle_ok=0;
  if(!strcmp(name,"close-stop-failure"))disable_ok=0;
  if(!strcmp(name,"close-reset-failure"))reset_ok=0;
  if(!strcmp(name,"close-device-missing"))RTMP_SET_FLAG(&ad,fRTMP_ADAPTER_NIC_NOT_EXIST);
  result=mt_wifi_close(&net);assert(result);retained();assert(irq_live&&workers_live);
 }else if(!strcmp(name,"first-enable-busy")||!strcmp(name,"first-enable-stop-failure")){
  init_ok=0;if(strstr(name,"stop-failure"))disable_ok=0;else idle_ok=0;
  result=mt_wifi_open(&net);assert(result);retained();assert(irq_live&&workers_live&&!ad.dma_running);
 }else if(!strcmp(name,"first-enable-idle")){
  init_ok=0;result=mt_wifi_open(&net);
  assert(result&&!ad.dma_lifecycle_pinned&&module_refs==0&&pci_refs==1&&!irq_live);
 }else if(!strcmp(name,"remove-busy")||!strcmp(name,"remove-stop-failure")||!strcmp(name,"remove-busy-repeat")){
  started();if(strstr(name,"stop-failure"))disable_ok=0;else idle_ok=0;
  rt_pci_remove(&pci);if(strstr(name,"repeat"))rt_pci_remove(&pci);
  retained();assert(unregister_calls==0&&ad.dma_removing);
 }else if(!strcmp(name,"core-remove-first-enable-busy")){
  init_ok=0;idle_ok=0;assert(mt_wifi_open(&net)!=0);pci_device_remove(&pci.dev);
  retained();assert(!ad.dma_running&&!pci.driver&&pci_refs==1&&core_irq_frees==1&&unregister_calls==0);
 }else if(!strcmp(name,"core-remove-busy")){
  started();idle_ok=0;pci_device_remove(&pci.dev);
  retained();assert(!pci.driver&&pci_refs==1&&core_irq_frees==1&&unregister_calls==0);
 }else if(!strcmp(name,"quarantine-retry-idle")||!strcmp(name,"quarantine-enable")||!strcmp(name,"quarantine-put")){
  started();idle_ok=0;assert(mt_wifi_close(&net)!=0);retained();idle_ok=1;
  if(!strcmp(name,"quarantine-retry-idle")){result=mt_wifi_close(&net);assert(result);result=mt_wifi_open(&net);assert(result);}
  else if(!strcmp(name,"quarantine-enable")){int before=enable_calls;result=AsicSetWPDMA(&ad,PDMA_TX_RX,1);assert(!result&&enable_calls==before);}
  else {RtmpDmaLifecyclePut(&ad);assert(module_refs==1&&pci_refs==2);}
  retained();
 }else if(!strcmp(name,"remove-idle")||!strcmp(name,"core-remove-idle")||!strcmp(name,"remove-never-enabled")||!strcmp(name,"remove-after-failed-enable")){
  if(!strcmp(name,"remove-after-failed-enable")){init_ok=0;assert(mt_wifi_open(&net)!=0);}
  else if(strcmp(name,"remove-never-enabled"))started();
  if(!strcmp(name,"core-remove-idle")){pci_device_remove(&pci.dev);assert(!pci.driver&&pci_refs==0&&core_irq_frees==1);}
  else rt_pci_remove(&pci);
  assert(!adapter_live&&!netdev_live&&!mmio_live&&!regions_live&&!rings_live&&!tokens_live&&!ring_alloc_live);
  assert(module_refs==0&&pci_refs<=1&&!ad.dma_lifecycle_pinned&&unregister_calls==1);
 }else if(!strcmp(name,"adapter-exit-quarantine")||!strcmp(name,"adapter-free-quarantine")||
          !strcmp(name,"adapter-exit-active")||!strcmp(name,"adapter-free-active")){
  started();if(strstr(name,"quarantine")){idle_ok=0;assert(mt_wifi_close(&net)!=0);}
  if(strstr(name,"exit-")){result=RtmpRaDevCtrlExit(&ad);assert(!result);}else RTMPFreeAdapter(&ad);
  assert(adapter_live&&rings_live&&ring_alloc_live&&tokens_live&&module_refs==1&&pci_refs==2&&free_count==0);
 }else if(!strcmp(name,"concurrent-close-open-idle")||!strcmp(name,"concurrent-close-open-busy")){
  started();if(strstr(name,"busy"))idle_ok=0;
  begin_paused_thread(&first,0);start_second_thread(&second,1);
  release_paused_thread();assert(!pthread_join(first,NULL));assert(!pthread_join(second,NULL));
  if(strstr(name,"busy")){assert(thread_result[0]&&thread_result[1]);retained();}
  else {assert(!thread_result[0]&&!thread_result[1]);assert(ad.dma_running&&module_refs==1&&pci_refs==2&&init_calls==2);}
  result=thread_result[1];
 }else if(!strcmp(name,"concurrent-remove-close-busy")){
  started();idle_ok=0;begin_paused_thread(&first,2);start_second_thread(&second,0);
  release_paused_thread();assert(!pthread_join(first,NULL));assert(!pthread_join(second,NULL));
  retained();assert(!pci.driver&&pci_refs==1&&thread_result[1]&&unregister_calls==0);result=thread_result[1];
 }else if(!strcmp(name,"concurrent-stop-denies-enable")){
  started();begin_paused_thread(&first,0);
  result=AsicSetWPDMA(&ad,PDMA_TX_RX,1);assert(!result&&enable_calls==1);
  release_paused_thread();assert(!pthread_join(first,NULL));assert(!thread_result[0]&&!ad.dma_running);
 }else if(!strcmp(name,"terminal-release-denies-open")){
  assert(RtmpDmaFinalReleaseCheck(&ad));result=mt_wifi_open(&net);
  assert(result&&init_calls==0&&module_refs==0&&pci_refs==1&&ad.dma_removing);
 }else assert(0);
 assert(unsafe_frees==0);
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",
 result,ad.dma_lifecycle_pinned,ad.dma_quarantined,ad.dma_stopping,ad.dma_removing,ad.dma_running,ad.dma_quiesced,
 module_refs,pci_refs,adapter_live,netdev_live,rings_live,tokens_live,ring_alloc_live,mmio_live,regions_live,irq_live,workers_live,
 unsafe_frees,free_count,init_calls,close_calls,unregister_calls,enable_calls,disable_calls,idle_calls,reset_calls,
 module_gets,module_puts,pci_gets,pci_puts,core_irq_frees,state_lock_live,life_lock_live);
 return 0;
}
"""
def function(text,name):
 token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
 masked=re.sub(token,lambda m:' '*len(m.group()),text)
 pattern=r'^(?:static\s+)?(?:inline\s+)?(?:VOID|BOOLEAN|UCHAR|INT|INT32|int|void|NDIS_STATUS)\s+(?:(?:DEVEXIT|DEVINIT)\s+)?'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
 found=list(re.finditer(pattern,masked,re.M))
 if len(found)!=1:raise ValueError('Missing/ambiguous quarantine function: '+name)
 start=found[0].start();opening=masked.index('{',start);depth=0
 for m in re.finditer(token+r'|[{}]',text[opening:]):
  if m.group()=='{':depth+=1
  elif m.group()=='}':
   depth-=1
   if not depth:return text[start:opening+m.end()]
 raise ValueError('Unterminated quarantine function: '+name)
def declarations(texts):
 rows=[]
 for pattern,key in SOURCE_DECLARATIONS.items():
  matches=re.findall(pattern,texts[key],re.M)
  if len(matches)!=1:raise ValueError('Missing/ambiguous quarantine declaration: '+pattern)
  rows.append(matches[0])
 return '\n'.join(rows)
def generate_source(texts,variant='current'):
 if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current quarantine inputs required')
 admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
 prototypes='\n'.join(function(texts[FUNCTION_SOURCES[n]],n).split('{',1)[0].rstrip()+';'for n in BODY_ORDER)
 return PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts)).replace('FUNCTION_DECLARATIONS',prototypes)+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)
def function_manifest(texts):
 return {n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}
