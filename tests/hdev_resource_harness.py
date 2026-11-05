"""Private complete resource source models; hardware and Linux APIs are explicit inert seams."""
import hashlib
import re

MODEL_VARIANT = {'role': 'private-prepublication-resource-inert-model',
 'MT_MAC': True,
 'IP_ASSEMBLY': True,
 'RESOURCE_PRE_ALLOC': True,
 'CONFIG_AP_SUPPORT': False,
 'reduced_preprocessor_omits_other_AP_ATE_features': True,
 'tx_rings': 2,
 'rx_rings': 2,
 'Wmm_sets': 2,
 'struct_layout_is_real_kernel_ABI': False,
 'ring_DMA_hardware_seam': True,
 'RtmpChipOpsHook_seam': True,
 'RTMPFreeAdapter_fixture_seam': True,
 'RtmpDmaFinalReleaseCheck_fixture_seam': True}

SOURCE_PATHS = {'wmm': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev/wmm_ctrl.c',
 'basic': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev/hdev_basic.c',
 'hdev': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev_ctrl.c',
 'init': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/rtmp_init.c',
 'dma': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/cmm_mac_pci.c',
 'pcie': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_rbus_pci_drv.c',
 'hif_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/hif/hif.h',
 'os_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/os/rt_linux.h',
 'chip_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/hw_ctrl/cmm_chip.h',
 'hdev_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/hdev_ctrl.h',
 'basic_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/hdev/hdev_basic.h',
 'free': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_profile.c',
 'open': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_main_dev.c'}

FUNCTION_SOURCES = {'WcGetWmmNum': 'wmm',
 'WcInit': 'wmm',
 'WcExit': 'wmm',
 'HdevHwResourceInit': 'basic',
 'HdevHwResourceExit': 'basic',
 'hdev_resource_init': 'hdev',
 'hdev_resource_exit': 'hdev',
 'alloc_chip_cap_dep_data_pci': 'dma',
 'free_chip_cap_dep_data_pci': 'dma',
 'alloc_chip_cap_dep_data_cmm': 'init',
 'free_chip_cap_dep_data_cmm': 'init',
 'alloc_chip_cap_dep_data': 'init',
 'free_chip_cap_dep_data': 'init',
 'RtmpChipOpsRegister': 'init',
 'RtmpRaDevCtrlInit': 'init',
 'RtmpRaDevCtrlExit': 'init',
 'RTMPInitPCIeDevice': 'pcie'}

SOURCE_ONLY_FUNCTION_SOURCES = {'RTMPFreeAdapter': 'free', 'RtmpDmaFinalReleaseCheck': 'open'}

BODY_ORDER = ('WcGetWmmNum',
 'WcInit',
 'WcExit',
 'HdevHwResourceInit',
 'HdevHwResourceExit',
 'hdev_resource_init',
 'hdev_resource_exit',
 'alloc_chip_cap_dep_data_pci',
 'free_chip_cap_dep_data_pci',
 'alloc_chip_cap_dep_data_cmm',
 'free_chip_cap_dep_data_cmm',
 'alloc_chip_cap_dep_data',
 'free_chip_cap_dep_data',
 'RtmpChipOpsRegister',
 'RtmpRaDevCtrlInit',
 'RtmpRaDevCtrlExit',
 'RTMPInitPCIeDevice')

SOURCE_DECLARATIONS = {'(#define NDIS_STATUS_SUCCESS\\s+0x00)': 'os_header',
 '(#define NDIS_STATUS_FAILURE\\s+0x01)': 'os_header',
 '(#define NDIS_STATUS_RESOURCES\\s+0x03)': 'os_header',
 '(typedef enum _RTMP_INF_TYPE_ \\{[\\s\\S]*?\\} RTMP_INF_TYPE;)': 'hif_header',
 '(#define IS_PCIE_INF\\(_pAd\\)[^\\n]+)': 'hif_header',
 '(#define IS_PCI_INF\\(_pAd\\)[^\\n]+)': 'hif_header',
 '(#define IS_RBUS_INF\\(_pAd\\)[^\\n]+)': 'hif_header',
 '(#define GET_NUM_OF_TX_RING\\(_chipCap\\)[^\\n]+)': 'chip_header',
 '(#define GET_NUM_OF_RX_RING\\(_chipCap\\)[^\\n]+)': 'chip_header',
 '(INT hdev_resource_init\\(void \\*hdev_ctrl\\);)': 'hdev_header',
 '(INT HdevHwResourceInit\\(struct hdev_ctrl \\*ctrl\\);)': 'basic_header'}

CASE_NAMES = ('pci-oom-1',
 'pci-oom-2',
 'pci-oom-3',
 'pci-oom-4',
 'pci-oom-5',
 'pci-oom-6',
 'pci-oom-7',
 'cmm-oom-1',
 'cmm-oom-2',
 'cmm-oom-3',
 'cmm-oom-4',
 'cmm-oom-5',
 'cmm-oom-6',
 'all-oom-1',
 'all-oom-2',
 'all-oom-3',
 'all-oom-4',
 'all-oom-5',
 'all-oom-6',
 'all-oom-7',
 'all-oom-8',
 'all-oom-9',
 'all-oom-10',
 'all-oom-11',
 'all-oom-12',
 'all-oom-13',
 'dev-oom-1',
 'dev-oom-2',
 'dev-oom-3',
 'dev-oom-4',
 'dev-oom-5',
 'dev-oom-6',
 'dev-oom-7',
 'dev-oom-8',
 'dev-oom-9',
 'dev-oom-10',
 'dev-oom-11',
 'dev-oom-12',
 'dev-oom-13',
 'dev-oom-14',
 'pcie-oom-1',
 'pcie-oom-2',
 'pcie-oom-3',
 'pcie-oom-4',
 'pcie-oom-5',
 'pcie-oom-6',
 'pcie-oom-7',
 'pcie-oom-8',
 'pcie-oom-9',
 'pcie-oom-10',
 'pcie-oom-11',
 'pcie-oom-12',
 'pcie-oom-13',
 'pcie-oom-14',
 'wc-zero',
 'wc-oom',
 'wc-success',
 'wc-duplicate',
 'wc-repeat-exit',
 'hw-oom',
 'hw-success',
 'resource-oom',
 'resource-success',
 'resource-duplicate',
 'resource-repeat-exit',
 'resource-retry',
 'cmm-retry',
 'pci-retry',
 'all-retry',
 'all-duplicate',
 'all-repeat-free',
 'wrapper-existing-cmm',
 'zero-tx',
 'zero-rx',
 'dev-chip-fail',
 'dev-ring-fail',
 'dev-success',
 'dev-duplicate',
 'dev-success-exit',
 'dev-exit-refuse',
 'pcie-config-fail',
 'pcie-unknown',
 'pcie-success',
 'pcie-chip-fail',
 'pcie-ring-fail')

EXPECTED_ROWS = {'pci-oom-1': [3, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'pci-oom-2': [3, 0, 0, 0, 0, 0, 0, 0, 2, 1],
 'pci-oom-3': [3, 0, 0, 0, 0, 0, 0, 0, 3, 1],
 'pci-oom-4': [3, 0, 0, 0, 0, 0, 0, 0, 4, 1],
 'pci-oom-5': [3, 0, 0, 0, 0, 0, 0, 0, 5, 1],
 'pci-oom-6': [3, 0, 0, 0, 0, 0, 0, 0, 6, 1],
 'pci-oom-7': [3, 0, 0, 0, 0, 0, 0, 0, 7, 1],
 'cmm-oom-1': [3, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'cmm-oom-2': [3, 0, 0, 0, 0, 0, 0, 0, 2, 1],
 'cmm-oom-3': [3, 0, 0, 0, 0, 0, 0, 0, 3, 1],
 'cmm-oom-4': [3, 0, 0, 0, 0, 0, 0, 0, 4, 1],
 'cmm-oom-5': [3, 0, 0, 0, 0, 0, 0, 0, 5, 1],
 'cmm-oom-6': [3, 0, 0, 0, 0, 0, 0, 0, 6, 1],
 'all-oom-1': [3, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'all-oom-2': [3, 0, 0, 0, 0, 0, 0, 0, 2, 1],
 'all-oom-3': [3, 0, 0, 0, 0, 0, 0, 0, 3, 1],
 'all-oom-4': [3, 0, 0, 0, 0, 0, 0, 0, 4, 1],
 'all-oom-5': [3, 0, 0, 0, 0, 0, 0, 0, 5, 1],
 'all-oom-6': [3, 0, 0, 0, 0, 0, 0, 0, 6, 1],
 'all-oom-7': [3, 0, 0, 0, 0, 0, 0, 0, 7, 1],
 'all-oom-8': [3, 0, 0, 0, 0, 0, 0, 0, 8, 1],
 'all-oom-9': [3, 0, 0, 0, 0, 0, 0, 0, 9, 1],
 'all-oom-10': [3, 0, 0, 0, 0, 0, 0, 0, 10, 1],
 'all-oom-11': [3, 0, 0, 0, 0, 0, 0, 0, 11, 1],
 'all-oom-12': [3, 0, 0, 0, 0, 0, 0, 0, 12, 1],
 'all-oom-13': [3, 0, 0, 0, 0, 0, 0, 0, 13, 1],
 'dev-oom-1': [1, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'dev-oom-2': [1, 0, 0, 0, 0, 0, 1, 0, 2, 1],
 'dev-oom-3': [1, 0, 0, 0, 0, 0, 1, 0, 3, 1],
 'dev-oom-4': [1, 0, 0, 0, 0, 0, 1, 0, 4, 1],
 'dev-oom-5': [1, 0, 0, 0, 0, 0, 1, 0, 5, 1],
 'dev-oom-6': [1, 0, 0, 0, 0, 0, 1, 0, 6, 1],
 'dev-oom-7': [1, 0, 0, 0, 0, 0, 1, 0, 7, 1],
 'dev-oom-8': [1, 0, 0, 0, 0, 0, 1, 0, 8, 1],
 'dev-oom-9': [1, 0, 0, 0, 0, 0, 1, 0, 9, 1],
 'dev-oom-10': [1, 0, 0, 0, 0, 0, 1, 0, 10, 1],
 'dev-oom-11': [1, 0, 0, 0, 0, 0, 1, 0, 11, 1],
 'dev-oom-12': [1, 0, 0, 0, 0, 0, 1, 0, 12, 1],
 'dev-oom-13': [1, 0, 0, 0, 0, 0, 1, 0, 13, 1],
 'dev-oom-14': [1, 0, 0, 0, 0, 0, 1, 0, 14, 1],
 'pcie-oom-1': [0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'pcie-oom-2': [0, 0, 0, 0, 0, 0, 1, 0, 2, 1],
 'pcie-oom-3': [0, 0, 0, 0, 0, 0, 1, 0, 3, 1],
 'pcie-oom-4': [0, 0, 0, 0, 0, 0, 1, 0, 4, 1],
 'pcie-oom-5': [0, 0, 0, 0, 0, 0, 1, 0, 5, 1],
 'pcie-oom-6': [0, 0, 0, 0, 0, 0, 1, 0, 6, 1],
 'pcie-oom-7': [0, 0, 0, 0, 0, 0, 1, 0, 7, 1],
 'pcie-oom-8': [0, 0, 0, 0, 0, 0, 1, 0, 8, 1],
 'pcie-oom-9': [0, 0, 0, 0, 0, 0, 1, 0, 9, 1],
 'pcie-oom-10': [0, 0, 0, 0, 0, 0, 1, 0, 10, 1],
 'pcie-oom-11': [0, 0, 0, 0, 0, 0, 1, 0, 11, 1],
 'pcie-oom-12': [0, 0, 0, 0, 0, 0, 1, 0, 12, 1],
 'pcie-oom-13': [0, 0, 0, 0, 0, 0, 1, 0, 13, 1],
 'pcie-oom-14': [0, 0, 0, 0, 0, 0, 1, 0, 14, 1],
 'wc-zero': [-1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
 'wc-oom': [-1, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'wc-success': [0, 1, 0, 0, 0, 0, 0, 0, 1, 1],
 'wc-duplicate': [-1, 1, 0, 0, 0, 0, 0, 0, 1, 1],
 'wc-repeat-exit': [0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'hw-oom': [-1, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'hw-success': [0, 1, 0, 0, 0, 1, 1, 0, 1, 1],
 'resource-oom': [-1, 0, 0, 0, 0, 0, 0, 0, 1, 1],
 'resource-success': [0, 1, 0, 0, 1, 1, 1, 0, 1, 1],
 'resource-duplicate': [-1, 1, 0, 0, 1, 1, 1, 0, 1, 1],
 'resource-repeat-exit': [0, 0, 0, 0, 0, 0, 1, 0, 1, 1],
 'resource-retry': [0, 1, 0, 0, 1, 1, 1, 0, 1, 1],
 'cmm-retry': [0, 6, 4, 0, 0, 0, 0, 0, 6, 1],
 'pci-retry': [0, 7, 4, 0, 0, 0, 0, 0, 7, 1],
 'all-retry': [0, 13, 8, 0, 0, 0, 0, 0, 13, 1],
 'all-duplicate': [1, 13, 8, 0, 0, 0, 0, 0, 13, 1],
 'all-repeat-free': [0, 0, 0, 0, 0, 0, 0, 0, 13, 1],
 'wrapper-existing-cmm': [1, 6, 4, 0, 0, 0, 0, 0, 7, 1],
 'zero-tx': [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
 'zero-rx': [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
 'dev-chip-fail': [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
 'dev-ring-fail': [1, 0, 0, 0, 0, 0, 1, 0, 14, 1],
 'dev-success': [0, 14, 9, 1, 1, 1, 1, 0, 14, 1],
 'dev-duplicate': [1, 14, 9, 1, 1, 1, 1, 0, 14, 1],
 'dev-success-exit': [1, 0, 0, 0, 0, 0, 1, 0, 14, 1],
 'dev-exit-refuse': [0, 14, 9, 1, 1, 1, 1, 0, 14, 1],
 'pcie-config-fail': [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
 'pcie-unknown': [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
 'pcie-success': [1, 14, 9, 1, 1, 1, 1, 1, 14, 1],
 'pcie-chip-fail': [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
 'pcie-ring-fail': [0, 0, 0, 0, 0, 0, 1, 0, 14, 1]}

OBSERVATION_COLUMNS = ('last_raw_status',
 'heap_live',
 'locks_live',
 'ring_owner',
 'resource_cookie',
 'wtc_live',
 'wtc_init_calls',
 'pci_init_succeed',
 'allocation_attempts',
 'cur_ip_array_zero')

PREFIX = ('/* Private reduced-field source model; none of these structs is the kernel ABI. */\n'
 '#include <stdlib.h>\n'
 '#include <stdio.h>\n'
 '#include <string.h>\n'
 '#include <assert.h>\n'
 '#define RTMP_MAC_PCI 1\n'
 '#define MT_MAC 1\n'
 '#define IP_ASSEMBLY 1\n'
 '#define RESOURCE_PRE_ALLOC 1\n'
 '#define FALSE 0\n'
 '#define TRUE 1\n'
 '#define VOID void\n'
 '#define IN\n'
 '#define fOP_STATUS_ADVANCE_POWER_SAVE_PCIE_DEVICE 1\n'
 '#define OPSTATUS_CLEAR_FLAG(a,f) do{(void)(a);(void)(f);}while(0)\n'
 '#define WLAN_HOOK_INIT() do{hook_init_calls++;}while(0)\n'
 '#define MTWF_LOG(...) do{}while(0)\n'
 'typedef int NDIS_STATUS; typedef int INT; typedef int INT32; typedef unsigned int UINT32;\n'
 'typedef int BOOLEAN; typedef unsigned char UINT8; typedef unsigned char UCHAR; typedef unsigned short '
 'USHORT; typedef unsigned long ULONG;\n'
 'struct hdev_ctrl;\n'
 'SOURCE_DEFINITIONS\n'
 'typedef int NDIS_SPIN_LOCK;\n'
 'typedef struct { int zero; } QUEUE_HEADER;\n'
 'typedef struct { int zero; } DL_LIST;\n'
 'typedef struct { int zero[4]; } RTMP_DMABUF;\n'
 'typedef struct { int zero[8]; } RTMP_TX_RING;\n'
 'typedef struct { int zero[8]; } RTMP_RX_RING;\n'
 'typedef struct _RTMP_CHIP_CAP { UINT8 num_of_tx_ring,num_of_rx_ring,WmmHwNum,MCUType; } RTMP_CHIP_CAP;\n'
 'typedef struct { int bValid,WmmSet,RefCnt; } EDCA_PARM;\n'
 'typedef struct { EDCA_PARM *pWmmSet; } WMM_CTRL_T;\n'
 'typedef struct { WMM_CTRL_T WmmCtrl; UCHAR concurrent_bands; } HD_RESOURCE_CFG;\n'
 'struct _PCI_HIF_T { RTMP_DMABUF *TxBufSpace,*TxDescRing,*RxDescRing; RTMP_TX_RING *TxRing; RTMP_RX_RING '
 '*RxRing; NDIS_SPIN_LOCK *TxRingLock,*RxRingLock; };\n'
 'struct os_cookie { USHORT DeviceID; };\n'
 'typedef struct os_cookie *POS_COOKIE;\n'
 'typedef struct _RTMP_ADAPTER {\n'
 ' void *hdev_ctrl; POS_COOKIE OS_Cookie; RTMP_INF_TYPE infType;\n'
 ' BOOLEAN *DeQueueRunning; NDIS_SPIN_LOCK *DeQueueLock,*TxSwQueueLock;\n'
 ' QUEUE_HEADER *TxSwQueue; DL_LIST *assebQueue; void *cur_ip_assem_data;\n'
 ' struct _PCI_HIF_T PciHif; int AutoRateLock,RscSemMemList,MCUCtrl,archOps;\n'
 ' int ChipID,HWVersion,FWVersion;\n'
 '} RTMP_ADAPTER;\n'
 'typedef RTMP_ADAPTER *PRTMP_ADAPTER;\n'
 'struct hdev_ctrl { RTMP_CHIP_CAP chip_cap; HD_RESOURCE_CFG HwResourceCfg; RTMP_ADAPTER *priv; void '
 '*cookie,*hif,*mcu_ctrl,*arch_ops; };\n'
 'typedef struct { void *pPciDev; int ConfigDeviceID; BOOLEAN pci_init_succeed; } RT_CMD_PCIE_INIT;\n'
 'static int attempts,fail_at,live,lock_live,ring_owner,ring_calls,ring_fail,chip_fail,pci_fail;\n'
 'static int '
 'wtc_live,wtc_init_calls,wtc_exit_calls,rc_calls,hdev_exit_calls,hook_init_calls,adapter_freed,release_allowed=1;\n'
 'static void *owners[128];\n'
 'static NDIS_STATUS os_alloc_mem(void *unused,UCHAR **out,size_t size) {\n'
 ' (void)unused;attempts++;if(attempts==fail_at){*out=NULL;return NDIS_STATUS_RESOURCES;}\n'
 ' *out=malloc(size);assert(*out);memset(*out,0xa5,size);\n'
 ' for(int i=0;i<128;i++){if(!owners[i]){owners[i]=*out;live++;return NDIS_STATUS_SUCCESS;}}\n'
 ' abort();\n'
 '}\n'
 'static void os_free_mem(void *p) {assert(p);for(int '
 'i=0;i<128;i++)if(owners[i]==p){owners[i]=NULL;live--;free(p);return;}abort();}\n'
 'static RTMP_CHIP_CAP *hc_get_chip_cap(void *p) {return &((struct hdev_ctrl *)p)->chip_cap;}\n'
 'static struct _PCI_HIF_T *hc_get_hif_ctrl(void *p) {return ((struct hdev_ctrl *)p)->hif;}\n'
 'static void lock_init(int *p) {assert(*p==0);*p=1;lock_live++;}\n'
 'static void lock_free(int *p) {assert(*p==1);*p=0;lock_live--;}\n'
 '#define NdisZeroMemory(p,n) memset(p,0,n)\n'
 '#define os_zero_mem(p,n) memset(p,0,n)\n'
 '#define NdisAllocateSpinLock(a,p) do{(void)(a);lock_init(p);}while(0)\n'
 '#define NdisFreeSpinLock(p) lock_free(p)\n'
 '#define OS_NdisAllocateSpinLock(p) lock_init(p)\n'
 '#define OS_NdisFreeSpinLock(p) lock_free(p)\n'
 '#define RTMP_SEM_EVENT_INIT(p,l) do{(void)(l);lock_init(p);}while(0)\n'
 '#define RTMP_SEM_EVENT_DESTORY(p) lock_free(p)\n'
 '#define DlListInit(p) do{(p)->zero=0;}while(0)\n'
 'static void RcInit(struct hdev_ctrl *c){rc_calls++;c->HwResourceCfg.concurrent_bands=1;}\n'
 'static void WtcInit(struct hdev_ctrl *c){(void)c;assert(!wtc_live);wtc_live=1;wtc_init_calls++;}\n'
 'static void WtcExit(struct hdev_ctrl *c){(void)c;assert(wtc_live==1);wtc_live=0;wtc_exit_calls++;}\n'
 'static void HdevExit(struct hdev_ctrl *c,UCHAR band){(void)c;assert(band==0);hdev_exit_calls++;}\n'
 'static int RtmpChipOpsHook(RTMP_ADAPTER *ad){if(chip_fail)return -1;RTMP_CHIP_CAP '
 '*c=hc_get_chip_cap(ad->hdev_ctrl);c->num_of_tx_ring=2;c->num_of_rx_ring=2;c->WmmHwNum=2;c->MCUType=1;return '
 '0;}\n'
 'static void ChipOpsMCUHook(RTMP_ADAPTER *ad,int type){(void)ad;assert(type==1);}\n'
 'static void get_dev_config_idx(RTMP_ADAPTER *ad){(void)ad;}\n'
 'static void AsicGetMacInfo(RTMP_ADAPTER *ad,int *a,int *b,int *c){(void)ad;*a=*b=*c=1;}\n'
 'static int RTMPAllocTxRxRingMemory(RTMP_ADAPTER *ad){(void)ad;ring_calls++;if(ring_fail)return '
 'NDIS_STATUS_RESOURCES;assert(!ring_owner);ring_owner=1;return NDIS_STATUS_SUCCESS;}\n'
 'static void RTMPFreeTxRxRingMemory(RTMP_ADAPTER *ad){(void)ad;ring_owner=0;}\n'
 'static int RtmpDmaFinalReleaseCheck(RTMP_ADAPTER *ad){(void)ad;return release_allowed;}\n'
 'static void RTMPFreeAdapter(RTMP_ADAPTER *ad);\n'
 'static void pci_read_config_word(void *p,int slot,USHORT *id){(void)p;(void)slot;*id=0x7615;}\n'
 'static USHORT le2cpu16(USHORT id){return id;}\n'
 'static NDIS_STATUS mt_pci_chip_cfg(RTMP_ADAPTER *ad,USHORT id){(void)ad;assert(id==0x7615);return '
 'pci_fail?NDIS_STATUS_FAILURE:NDIS_STATUS_SUCCESS;}\n'
 'FUNCTION_DECLARATIONS\n')

SUFFIX = ('static void RTMPFreeAdapter(RTMP_ADAPTER '
 '*ad){assert(!adapter_freed);hdev_resource_exit(ad->hdev_ctrl);adapter_freed=1;}\n'
 'int main(int argc,char **argv){\n'
 ' if(argc!=2){return 90;}\n'
 ' const char *name=argv[1];CASE_ADMISSION\n'
 ' struct os_cookie cookie={0};struct hdev_ctrl hd={0};\n'
 ' RTMP_ADAPTER ad={.hdev_ctrl=&hd,.OS_Cookie=&cookie,.infType=RTMP_DEV_INF_PCIE};\n'
 ' '
 'hd.priv=&ad;hd.hif=&ad.PciHif;hd.chip_cap.num_of_tx_ring=2;hd.chip_cap.num_of_rx_ring=2;hd.chip_cap.WmmHwNum=2;\n'
 ' RT_CMD_PCIE_INIT cfg={.pPciDev=&hd,.pci_init_succeed=FALSE};int ret=0;\n'
 ' if(!strncmp(name,"pci-oom-",8)){fail_at=atoi(name+8);ret=alloc_chip_cap_dep_data_pci(&hd);}\n'
 ' else if(!strncmp(name,"cmm-oom-",8)){fail_at=atoi(name+8);ret=alloc_chip_cap_dep_data_cmm(&ad);}\n'
 ' else if(!strncmp(name,"all-oom-",8)){fail_at=atoi(name+8);ret=alloc_chip_cap_dep_data(&ad);}\n'
 ' else if(!strncmp(name,"dev-oom-",8)){fail_at=atoi(name+8);ret=RtmpRaDevCtrlInit(&ad,RTMP_DEV_INF_PCIE);}\n'
 ' else '
 'if(!strncmp(name,"pcie-oom-",9)){fail_at=atoi(name+9);cfg.pci_init_succeed=TRUE;RTMPInitPCIeDevice(&cfg,&ad);ret=cfg.pci_init_succeed;}\n'
 ' else if(!strcmp(name,"wc-zero")){hd.chip_cap.WmmHwNum=0;ret=WcInit(&hd,&hd.HwResourceCfg.WmmCtrl);}\n'
 ' else if(!strcmp(name,"wc-oom")){fail_at=1;ret=WcInit(&hd,&hd.HwResourceCfg.WmmCtrl);}\n'
 ' else if(!strcmp(name,"wc-success")){ret=WcInit(&hd,&hd.HwResourceCfg.WmmCtrl);}\n'
 ' else '
 'if(!strcmp(name,"wc-duplicate")){assert(WcInit(&hd,&hd.HwResourceCfg.WmmCtrl)==0);ret=WcInit(&hd,&hd.HwResourceCfg.WmmCtrl);}\n'
 ' else '
 'if(!strcmp(name,"wc-repeat-exit")){assert(WcInit(&hd,&hd.HwResourceCfg.WmmCtrl)==0);assert(WcExit(&hd.HwResourceCfg.WmmCtrl)==0);ret=WcExit(&hd.HwResourceCfg.WmmCtrl);}\n'
 ' else if(!strcmp(name,"hw-oom")){fail_at=1;ret=HdevHwResourceInit(&hd);}\n'
 ' else if(!strcmp(name,"hw-success")){ret=HdevHwResourceInit(&hd);}\n'
 ' else if(!strcmp(name,"resource-oom")){fail_at=1;ret=hdev_resource_init(&hd);}\n'
 ' else if(!strcmp(name,"resource-success")){ret=hdev_resource_init(&hd);}\n'
 ' else '
 'if(!strcmp(name,"resource-duplicate")){assert(hdev_resource_init(&hd)==0);ret=hdev_resource_init(&hd);}\n'
 ' else '
 'if(!strcmp(name,"resource-repeat-exit")){assert(hdev_resource_init(&hd)==0);hdev_resource_exit(&hd);hdev_resource_exit(&hd);}\n'
 ' else '
 'if(!strcmp(name,"resource-retry")){fail_at=1;assert(hdev_resource_init(&hd)==-1);assert(live==0);fail_at=0;attempts=0;ret=hdev_resource_init(&hd);}\n'
 ' else '
 'if(!strcmp(name,"cmm-retry")){fail_at=2;assert(alloc_chip_cap_dep_data_cmm(&ad)==NDIS_STATUS_RESOURCES);assert(!live&&!lock_live);fail_at=0;attempts=0;ret=alloc_chip_cap_dep_data_cmm(&ad);}\n'
 ' else '
 'if(!strcmp(name,"pci-retry")){fail_at=7;assert(alloc_chip_cap_dep_data_pci(&hd)==NDIS_STATUS_RESOURCES);assert(!live&&!lock_live);fail_at=0;attempts=0;ret=alloc_chip_cap_dep_data_pci(&hd);}\n'
 ' else '
 'if(!strcmp(name,"all-retry")){fail_at=13;assert(alloc_chip_cap_dep_data(&ad)==NDIS_STATUS_RESOURCES);assert(!live&&!lock_live);fail_at=0;attempts=0;ret=alloc_chip_cap_dep_data(&ad);}\n'
 ' else '
 'if(!strcmp(name,"all-duplicate")){assert(alloc_chip_cap_dep_data(&ad)==NDIS_STATUS_SUCCESS);ret=alloc_chip_cap_dep_data(&ad);}\n'
 ' else '
 'if(!strcmp(name,"all-repeat-free")){assert(alloc_chip_cap_dep_data(&ad)==NDIS_STATUS_SUCCESS);free_chip_cap_dep_data(&ad);free_chip_cap_dep_data(&ad);}\n'
 ' else '
 'if(!strcmp(name,"wrapper-existing-cmm")){assert(alloc_chip_cap_dep_data_cmm(&ad)==NDIS_STATUS_SUCCESS);attempts=0;ret=alloc_chip_cap_dep_data(&ad);}\n'
 ' else if(!strcmp(name,"zero-tx")){hd.chip_cap.num_of_tx_ring=0;ret=alloc_chip_cap_dep_data(&ad);}\n'
 ' else if(!strcmp(name,"zero-rx")){hd.chip_cap.num_of_rx_ring=0;ret=alloc_chip_cap_dep_data(&ad);}\n'
 ' else if(!strcmp(name,"dev-chip-fail")){chip_fail=1;ret=RtmpRaDevCtrlInit(&ad,RTMP_DEV_INF_PCIE);}\n'
 ' else if(!strcmp(name,"dev-ring-fail")){ring_fail=1;ret=RtmpRaDevCtrlInit(&ad,RTMP_DEV_INF_PCIE);}\n'
 ' else if(!strcmp(name,"dev-success")){ret=RtmpRaDevCtrlInit(&ad,RTMP_DEV_INF_PCIE);}\n'
 ' else '
 'if(!strcmp(name,"dev-duplicate")){assert(RtmpRaDevCtrlInit(&ad,RTMP_DEV_INF_PCIE)==NDIS_STATUS_SUCCESS);ret=RtmpRaDevCtrlInit(&ad,RTMP_DEV_INF_PCIE);}\n'
 ' else '
 'if(!strcmp(name,"dev-success-exit")){assert(RtmpRaDevCtrlInit(&ad,RTMP_DEV_INF_PCIE)==NDIS_STATUS_SUCCESS);ret=RtmpRaDevCtrlExit(&ad);}\n'
 ' else '
 'if(!strcmp(name,"dev-exit-refuse")){assert(RtmpRaDevCtrlInit(&ad,RTMP_DEV_INF_PCIE)==NDIS_STATUS_SUCCESS);release_allowed=0;ret=RtmpRaDevCtrlExit(&ad);}\n'
 ' else '
 'if(!strcmp(name,"pcie-config-fail")){pci_fail=1;cfg.pci_init_succeed=TRUE;RTMPInitPCIeDevice(&cfg,&ad);ret=cfg.pci_init_succeed;}\n'
 ' else '
 'if(!strcmp(name,"pcie-unknown")){ad.infType=RTMP_DEV_INF_UNKNOWN;cfg.pci_init_succeed=TRUE;RTMPInitPCIeDevice(&cfg,&ad);ret=cfg.pci_init_succeed;}\n'
 ' else '
 'if(!strcmp(name,"pcie-success")){cfg.pci_init_succeed=TRUE;RTMPInitPCIeDevice(&cfg,&ad);ret=cfg.pci_init_succeed;}\n'
 ' else '
 'if(!strcmp(name,"pcie-chip-fail")){chip_fail=1;cfg.pci_init_succeed=TRUE;RTMPInitPCIeDevice(&cfg,&ad);ret=cfg.pci_init_succeed;}\n'
 ' else '
 'if(!strcmp(name,"pcie-ring-fail")){ring_fail=1;cfg.pci_init_succeed=TRUE;RTMPInitPCIeDevice(&cfg,&ad);ret=cfg.pci_init_succeed;}\n'
 ' else return 92;\n'
 ' int zero_ip=1;\n'
 ' if(ad.cur_ip_assem_data){for(int i=0;i<2;i++){if(((void **)ad.cur_ip_assem_data)[i]!=NULL)zero_ip=0;}}\n'
 ' '
 'printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\\n",ret,live,lock_live,ring_owner,hd.cookie!=NULL,wtc_live,wtc_init_calls,cfg.pci_init_succeed,attempts,zero_ip);\n'
 ' /* Private fixture cleanup follows observation, including intentionally retained graphs. */\n'
 ' for(int i=0;i<128;i++)if(owners[i]){free(owners[i]);owners[i]=NULL;}\n'
 ' return 0;\n'
 '}\n')


def require(value,message):
    if not value:raise ValueError(message)

def function(source, name):
    token = r'"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked = re.sub(token, lambda m: ' '*len(m.group()), source)
    pattern = r'^(?:static\s+)?(?:inline\s+)?(?:VOID|INT|INT32|UINT32|UCHAR|BOOLEAN|NTSTATUS|NDIS_STATUS|int|void|bool|UINT|ULONG)\s+(?:(?:DEVINIT|DEVEXIT)\s+)?'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    found = list(re.finditer(pattern, masked, re.M))
    require(len(found) == 1, 'Missing/ambiguous current init/DMA function: '+name)
    start = found[0].start(); opening = masked.index('{', start); depth = 0
    for match in re.finditer(token+r'|[{}]', source[opening:]):
        if match.group() == '{': depth += 1
        elif match.group() == '}':
            depth -= 1
            if not depth: return source[start:opening+match.end()]
    raise ValueError('Unterminated current function: '+name)

def declarations(texts):
    out=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        found=re.findall(pattern,texts[key],re.M)
        require(len(found)==1 and type(found[0])is str,'Unique complete resource declaration required: '+pattern)
        out.append(found[0])
    return '\n'.join(out)

def generate_source(texts,variant='current'):
    require(variant=='current' and set(texts)==set(SOURCE_PATHS),'Exact current resource model inputs required')
    bodies={name:function(texts[FUNCTION_SOURCES[name]],name)for name in BODY_ORDER}
    prefix=PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts))
    prefix=prefix.replace('FUNCTION_DECLARATIONS','\n'.join(body.split('{',1)[0].rstrip()+';'for body in bodies.values()))
    admission='if(!('+'||'.join('!strcmp(name,"'+name+'")'for name in CASE_NAMES)+'))return 91;'
    return prefix+'\n'.join(bodies.values())+SUFFIX.replace('CASE_ADMISSION',admission)

def function_manifest(texts):
    return {name:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}for name,key in FUNCTION_SOURCES.items()}

def source_only_manifest(texts):
    return {name:{'source':key,'execution':'source-only-not-run','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}for name,key in SOURCE_ONLY_FUNCTION_SOURCES.items()}

def model_data_hash():
    import json
    names=('MODEL_VARIANT','SOURCE_PATHS','FUNCTION_SOURCES','SOURCE_ONLY_FUNCTION_SOURCES','BODY_ORDER','SOURCE_DECLARATIONS','CASE_NAMES','EXPECTED_ROWS','OBSERVATION_COLUMNS','PREFIX','SUFFIX')
    return hashlib.sha256(json.dumps({k:globals()[k]for k in names},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
