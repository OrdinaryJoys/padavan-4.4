"""Whole wdev/netdev functions; RTNL/dev_close/tasks/config/allocation are inert.
Three slots replace target maxima. No kernel, device or real scheduling runs.
"""
import hashlib,re
MODEL_VARIANT = {'role': 'private-wdev-netdev-retirement-inert-model',
 'CONFIG_AP_SUPPORT': True,
 'MBSS_SUPPORT': True,
 'ERR_RECOVERY': True,
 'reduced_MBSSID_slots': 3,
 'reduced_WDEV_slots': 3,
 'APCLI_SUPPORT': False,
 'WDS_SUPPORT': False,
 'SNIFFER_SUPPORT': False,
 'WSC_INCLUDED': False,
 'RT_CFG80211_SUPPORT': False,
 'MULTIPLE_CARD_SUPPORT': False,
 'HOSTAPD_SUPPORT': False,
 'MULTI_PROFILE': False,
 'CREATE_ALL_INTERFACE_AT_INIT': False,
 'CONFIG_CSO_SUPPORT': False,
 'CONFIG_TSO_SUPPORT': False,
 'OS_ABL_FUNC_SUPPORT': False,
 'dev_close_ignores_ndo_stop_status': True,
 'controlled_close_callback_interleavings': True,
 'real_RTNl_or_threads_executed': False,
 'actual_K2P_CMWQ_enabled': False,
 'beacon_payloads_symbolic_here_actual_owner_model_in_probe_component': True,
 'vendor_ie_each_target_transactional': True,
 'vendor_multi_frame_atomic_rollback_claimed': False,
 'vendor_running_reader_concurrency_proved': False,
 'one_registered_netdev_one_detach_protocol': True,
 'arbitrary_full_Exit_repetition_claimed': False,
 'fixture_private_retained_owner_cleanup_after_observation': True,
 'model_signed_wdev_index': True,
 'actual_CHAR_signedness_not_assumed': True,
 'main_VIE_freed_by_actual_Exit': True}

BASE = 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'

SOURCE_PATHS = {'main': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_main_dev.c',
 'os': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_linux.c',
 'mbss': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap_mbss.c',
 'cfg': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/cmm_cfg.c',
 'wdev': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/wdev.c',
 'apcli': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap_apcli.c',
 'wds': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap_wds.c',
 'sniffer': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/sniffer_radiotap.c',
 'vendor': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/vendor.c',
 'os_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/os/rt_linux.h',
 'header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/rtmp.h',
 'free': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_profile.c',
 'vendor_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/vendor.h'}

FUNCTION_SOURCES = {'get_vie_ctrl': 'vendor',
 'insert_vie': 'vendor',
 'find_oui_oitype': 'vendor',
 'add_vie': 'vendor',
 'init_vie_ctrl': 'vendor',
 'deinit_vie_ctrl': 'vendor',
 'wdev_init': 'wdev',
 'wdev_deinit': 'wdev',
 'rtmp_netdev_set': 'cfg',
 'RtmpOSNetDevFree': 'os',
 'RtmpPhyNetDevInit': 'main',
 'MBSS_Init': 'mbss',
 'MBSS_Remove': 'mbss',
 'RtmpPhyNetDevCloseAll': 'main',
 'RtmpPhyNetDevExit': 'main'}

BODY_ORDER = ('get_vie_ctrl',
 'insert_vie',
 'find_oui_oitype',
 'add_vie',
 'init_vie_ctrl',
 'deinit_vie_ctrl',
 'wdev_init',
 'wdev_deinit',
 'rtmp_netdev_set',
 'RtmpOSNetDevFree',
 'RtmpPhyNetDevInit',
 'MBSS_Init',
 'MBSS_Remove',
 'RtmpPhyNetDevCloseAll',
 'RtmpPhyNetDevExit')

SOURCE_ONLY_FUNCTION_SOURCES = {'RTMP_COM_IoctlHandle': 'cfg',
 'virtual_if_up_handler': 'main',
 'mt_wifi_open': 'main',
 'APCli_Init': 'apcli',
 'WDS_Init': 'wds',
 'Monitor_Init': 'sniffer',
 'RTMPFreeAdapter': 'free'}

SOURCE_DECLARATIONS = {'^#define NDIS_STATUS_SUCCESS\\s+0x[0-9a-fA-F]+\\s*$': 'os_header',
 '^#define NDIS_STATUS_FAILURE\\s+0x[0-9a-fA-F]+\\s*$': 'os_header',
 '^#define NDIS_STATUS_RESOURCES\\s+0x[0-9a-fA-F]+\\s*$': 'os_header',
 'typedef enum vendor_ie_in_frame_type \\{[\\s\\S]*?\\} VIE_FRM_TYPE;': 'vendor_header',
 'typedef struct vie_struct \\{[\\s\\S]*?\\} VIE_STRUCT;': 'vendor_header',
 'typedef struct vie_ctrl_struct \\{[\\s\\S]*?\\} VIE_CTRL;': 'vendor_header'}

CASE_NAMES = ('main-create-failure',
 'main-ops-allocation-failure',
 'main-private-failure',
 'main-wdev-registration-failure',
 'main-ops-registration-failure',
 'main-success',
 'wdev-registration-failure',
 'free-unpublished-ops',
 'free-detached-ops',
 'mbss-prefix-failure',
 'mbss-create-first-failure',
 'mbss-create-second-failure',
 'mbss-registration-first-failure',
 'mbss-registration-second-failure',
 'mbss-ops-first-failure',
 'mbss-ops-second-failure',
 'mbss-attach-first-failure',
 'mbss-attach-second-failure',
 'mbss-repeat-init',
 'mbss-shrunk-remove',
 'mbss-live-remove',
 'mbss-quarantined-remove',
 'closeall-success',
 'closeall-repeat',
 'closeall-main-fallback',
 'closeall-open-excluded',
 'closeall-count-busy',
 'closeall-started-busy',
 'closeall-hw-task-busy',
 'closeall-hw-queue-busy',
 'closeall-cmd-task-busy',
 'closeall-timer-busy',
 'closeall-ser-task-busy',
 'closeall-ser-owner-busy',
 'closeall-dma-busy',
 'closeall-stop-status-failed-but-retired',
 'exit-quarantined',
 'vie-node-oom',
 'vie-payload-oom',
 'vie-invalid-controller',
 'vie-null-output',
 'vie-null-wdev',
 'vie-null-frame',
 'vie-append-existing',
 'vie-update-oom',
 'vie-update-success',
 'vie-zero-length',
 'vie-repeat-init',
 'vie-repeat-deinit',
 'vie-registration-failure-preserves',
 'exit-main-vie-owner',
 'exit-main-unregistered',
 'exit-main-negative-index',
 'exit-main-wrong-owner')

FIELDS = ('result',
 'net_live',
 'ops_live',
 'wdev_live',
 'unsafe_frees',
 'retention_observed',
 'beacon_owners_preserved',
 'remove_latched')

CASE_GROUPS = {'main': ('main-create-failure',
          'main-ops-allocation-failure',
          'main-private-failure',
          'main-wdev-registration-failure',
          'main-ops-registration-failure',
          'main-success',
          'wdev-registration-failure',
          'free-unpublished-ops',
          'free-detached-ops'),
 'mbss': ('mbss-prefix-failure',
          'mbss-create-first-failure',
          'mbss-create-second-failure',
          'mbss-registration-first-failure',
          'mbss-registration-second-failure',
          'mbss-ops-first-failure',
          'mbss-ops-second-failure',
          'mbss-attach-first-failure',
          'mbss-attach-second-failure',
          'mbss-repeat-init',
          'mbss-shrunk-remove',
          'mbss-live-remove',
          'mbss-quarantined-remove'),
 'closeall': ('closeall-success',
              'closeall-repeat',
              'closeall-main-fallback',
              'closeall-open-excluded',
              'closeall-count-busy',
              'closeall-started-busy',
              'closeall-hw-task-busy',
              'closeall-hw-queue-busy',
              'closeall-cmd-task-busy',
              'closeall-timer-busy',
              'closeall-ser-task-busy',
              'closeall-ser-owner-busy',
              'closeall-dma-busy',
              'closeall-stop-status-failed-but-retired'),
 'quarantine': ('exit-quarantined',),
 'vie': ('vie-node-oom',
         'vie-payload-oom',
         'vie-invalid-controller',
         'vie-null-output',
         'vie-null-wdev',
         'vie-null-frame',
         'vie-append-existing',
         'vie-update-oom',
         'vie-update-success',
         'vie-zero-length',
         'vie-repeat-init',
         'vie-repeat-deinit',
         'vie-registration-failure-preserves'),
 'main_exit': ('exit-main-vie-owner',
               'exit-main-unregistered',
               'exit-main-negative-index',
               'exit-main-wrong-owner')}

EXPECTED_ROWS = {'main-create-failure': [0, 0, 0, 0, 0, 0, 1, 0],
 'main-ops-allocation-failure': [0, 0, 0, 0, 0, 0, 1, 0],
 'main-private-failure': [0, 0, 0, 0, 0, 0, 1, 0],
 'main-wdev-registration-failure': [0, 0, 0, 0, 0, 0, 1, 0],
 'main-ops-registration-failure': [0, 0, 0, 0, 0, 0, 1, 0],
 'main-success': [1, 0, 0, 0, 0, 0, 1, 1],
 'wdev-registration-failure': [0, 0, 0, 0, 0, 0, 1, 0],
 'free-unpublished-ops': [1, 0, 0, 0, 0, 0, 1, 0],
 'free-detached-ops': [1, 0, 0, 0, 0, 0, 1, 0],
 'mbss-prefix-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-create-first-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-create-second-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-registration-first-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-registration-second-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-ops-first-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-ops-second-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-attach-first-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-attach-second-failure': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-repeat-init': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-shrunk-remove': [1, 0, 0, 0, 0, 0, 1, 1],
 'mbss-live-remove': [1, 0, 0, 0, 0, 1, 1, 1],
 'mbss-quarantined-remove': [1, 0, 0, 0, 0, 1, 1, 1],
 'closeall-success': [1, 0, 0, 0, 0, 0, 1, 1],
 'closeall-repeat': [1, 0, 0, 0, 0, 0, 1, 1],
 'closeall-main-fallback': [1, 0, 0, 0, 0, 0, 1, 1],
 'closeall-open-excluded': [1, 0, 0, 0, 0, 0, 1, 1],
 'closeall-count-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-started-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-hw-task-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-hw-queue-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-cmd-task-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-timer-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-ser-task-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-ser-owner-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-dma-busy': [0, 0, 0, 0, 0, 1, 1, 1],
 'closeall-stop-status-failed-but-retired': [1, 0, 0, 0, 0, 0, 1, 1],
 'exit-quarantined': [0, 0, 0, 0, 0, 1, 1, 1],
 'vie-node-oom': [0, 0, 0, 0, 0, 0, 1, 0],
 'vie-payload-oom': [0, 0, 0, 0, 0, 0, 1, 0],
 'vie-invalid-controller': [0, 0, 0, 0, 0, 0, 1, 0],
 'vie-null-output': [0, 0, 0, 0, 0, 0, 1, 0],
 'vie-null-wdev': [0, 0, 0, 0, 0, 0, 1, 0],
 'vie-null-frame': [0, 0, 0, 0, 0, 0, 1, 0],
 'vie-append-existing': [1, 0, 0, 0, 0, 0, 1, 0],
 'vie-update-oom': [0, 0, 0, 0, 0, 0, 1, 0],
 'vie-update-success': [1, 0, 0, 0, 0, 0, 1, 0],
 'vie-zero-length': [1, 0, 0, 0, 0, 0, 1, 0],
 'vie-repeat-init': [1, 0, 0, 0, 0, 0, 1, 0],
 'vie-repeat-deinit': [1, 0, 0, 0, 0, 0, 1, 0],
 'vie-registration-failure-preserves': [0, 0, 0, 0, 0, 0, 1, 0],
 'exit-main-vie-owner': [1, 0, 0, 0, 0, 0, 1, 1],
 'exit-main-unregistered': [1, 0, 0, 0, 0, 1, 1, 1],
 'exit-main-negative-index': [1, 0, 0, 0, 0, 1, 1, 1],
 'exit-main-wrong-owner': [1, 0, 0, 0, 0, 1, 1, 1]}

SOURCE_FIELD_CONSTRAINTS = {}

PREFIX = ('\n'
 '#include <assert.h>\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <string.h>\n'
 'typedef void VOID;typedef int INT,INT32,BOOLEAN,NDIS_STATUS;typedef signed char INT8,CHAR;\n'
 'typedef unsigned int UINT,UINT32;typedef unsigned long ULONG;typedef unsigned char UCHAR;\n'
 '#define TRUE 1\n'
 '#define FALSE 0\n'
 '#define CONFIG_AP_SUPPORT 1\n'
 '#define MBSS_SUPPORT 1\n'
 '#define ERR_RECOVERY 1\n'
 '#define WIRELESS_EXT 22\n'
 '#define WDEV_NUM_MAX 3\n'
 '#define HW_BEACON_MAX_NUM 3\n'
 '#define FIRST_MBSSID 1\n'
 '#define MAIN_MBSSID 0\n'
 '#define MAC_ADDR_LEN 6\n'
 '#define INT_MBSSID 2\n'
 '#define OPMODE_AP 1\n'
 '#define IFF_UP 1\n'
 '#define MSDU_FORBID_CONNECTION_NOT_READY 0\n'
 '#define fRTMP_ADAPTER_START_UP 1\n'
 '#define RTMP_TASK_STAT_UNKNOWN 0\n'
 '#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))\n'
 '#define LINUX_VERSION_CODE KERNEL_VERSION(4,4,198)\n'
 'SOURCE_DEFINITIONS\n'
 '#define VIE_BEACON_BITMAP (1 << VIE_BEACON)\n'
 '#define VIE_PROBE_REQ_BITMAP (1 << VIE_PROBE_REQ)\n'
 '#define VIE_PROBE_RESP_BITMAP (1 << VIE_PROBE_RESP)\n'
 '#define VIE_ASSOC_REQ_BITMAP (1 << VIE_ASSOC_REQ)\n'
 '#define VIE_ASSOC_RESP_BITMAP (1 << VIE_ASSOC_RESP)\n'
 '#define VIE_AUTH_REQ_BITMAP (1 << VIE_AUTH_REQ)\n'
 '#define VIE_AUTH_RESP_BITMAP (1 << VIE_AUTH_RESP)\n'
 '#define MTWF_LOG(...) ((void)0)\n'
 '#define ASSERT(v) assert(v)\n'
 '#define READ_ONCE(v) (v)\n'
 '#define WRITE_ONCE(v,x) ((v)=(x))\n'
 '#define RTMP_TEST_FLAG(a,f) (((a)->flags&(f))!=0)\n'
 '#define RTMP_OS_TASK_LEGALITY(t) (*(t)!=0)\n'
 '#define VIRTUAL_IF_NUM(a) ((a)->virtual_count)\n'
 '#define NdisZeroMemory(p,n) memset((p),0,(n))\n'
 '#define NdisEqualMemory(a,b,n) (memcmp((a),(b),(n))==0)\n'
 '#define NdisCopyMemory(d,s,n) memcpy((d),(s),(n))\n'
 '#define NdisMoveMemory(d,s,n) memcpy((d),(s),(n))\n'
 '#define os_zero_mem(d,n) memset((d),0,(n))\n'
 'enum WDEV_TYPE {WDEV_TYPE_AP=1};\n'
 'struct _RTMP_ADAPTER;struct net_device;\n'
 'typedef struct net_device *PNET_DEV;\n'
 'struct wifi_dev {CHAR wdev_idx;int wdev_type;PNET_DEV if_dev;INT8 func_idx;void '
 '*func_dev,*sys_handle;\n'
 ' VIE_CTRL vie_ctrl[VIE_FRM_TYPE_MAX];int '
 'tr_tb_idx,OpStatusFlags,forbid_data_tx,bAllowBeaconing,registered,vie_live,hc_live;\n'
 ' UCHAR bssid[6];struct {void *BeaconPkt;} bcn_buf;};\n'
 'typedef struct {struct wifi_dev wdev;} BSS_STRUCT;\n'
 'struct _RTMP_CHIP_CAP {int wmm_detect_method;};\n'
 'struct wifi_dev_ops {int ignored;};\n'
 'struct mt_dev_priv {int ignored;};\n'
 'struct net_device {struct _RTMP_ADAPTER *adapter;struct wifi_dev *wdev;\n'
 ' void *netdev_ops;int flags,published,id;char name[16];};\n'
 'typedef struct {void '
 '(*open)(void),(*stop)(void),(*xmit)(void),(*ioctl)(void),(*get_stats)(void);\n'
 ' ULONG priv_flags;int needProtcted;struct wifi_dev *wdev;UCHAR devAddr[6];} '
 'RTMP_OS_NETDEV_OP_HOOK;\n'
 'typedef struct _RTMP_ADAPTER {PNET_DEV net_dev;void *hdev_ctrl;INT '
 'OpMode,FlgMbssInit,flags,virtual_count;\n'
 ' BOOLEAN dma_removing,quarantined,dma_ok;struct wifi_dev *wdev_list[WDEV_NUM_MAX];\n'
 ' struct {INT BssidNum;BSS_STRUCT MBSSID[HW_BEACON_MAX_NUM];} ApCfg;\n'
 ' struct {int HwCtrlTask,ser_task,ser_initialized;struct {int CmdQState;} HwCtrlQ;} HwCtrl;\n'
 ' int cmdQTask;struct {int size;} RscTimerCreateList;} RTMP_ADAPTER;\n'
 'FUNCTION_DECLARATIONS\n'
 'static struct wifi_dev_ops ap_wdev_ops;\n'
 'static struct _RTMP_CHIP_CAP cap;\n'
 'static RTMP_ADAPTER *current;\n'
 'static int '
 'net_live,ops_live,wdev_live,unsafe_frees,protect,lifecycle,create_calls,reg_calls,ops_calls,attach_calls;\n'
 'static int fail_create,fail_ops_alloc,fail_priv,fail_reg,fail_ops,fail_attach,fail_prefix;\n'
 'static int bad_main_owner;\n'
 'static int closes,config_exits,stop_mode,open_rejects,concurrent_open,retention_observed;\n'
 '\n'
 'static int beacon_tags[HW_BEACON_MAX_NUM];\n'
 'static int vie_heap,vie_alloc_calls,vie_fail;\n'
 'static struct {void *ptr;int live;} vie_allocations[128];static int vie_records;\n'
 'static int os_alloc_mem(void *a,UCHAR **out,size_t '
 'n){(void)a;vie_alloc_calls++;*out=NULL;if(vie_alloc_calls==vie_fail)return '
 'NDIS_STATUS_RESOURCES;\n'
 ' '
 'assert(vie_records<128);*out=malloc(n?n:1);assert(*out);memset(*out,0xa5,n?n:1);vie_allocations[vie_records++]=(typeof(vie_allocations[0])){*out,1};vie_heap++;return '
 'NDIS_STATUS_SUCCESS;}\n'
 'static void os_free_mem(void *p){for(int '
 'i=vie_records-1;i>=0;i--)if(vie_allocations[i].ptr==p&&vie_allocations[i].live){vie_allocations[i].live=0;vie_heap--;free(p);return;}assert(!"bad '
 'VIE free");}\n'
 'static void no_op(void){}\n'
 '#define main_virtual_if_open no_op\n'
 '#define main_virtual_if_close no_op\n'
 '#define rt28xx_send_packets no_op\n'
 '#define rt28xx_ioctl no_op\n'
 '#define RT28xx_get_ether_stats64 no_op\n'
 'static struct _RTMP_CHIP_CAP *hc_get_chip_cap(void *h){assert(h);return &cap;}\n'
 '\n'
 'static int wdev_idx_reg(RTMP_ADAPTER *a,struct wifi_dev '
 '*w){reg_calls++;if(fail_reg==reg_calls)return-1;\n'
 ' for(int '
 'i=0;i<WDEV_NUM_MAX;i++)if(!a->wdev_list[i]){assert(!w->registered);a->wdev_list[i]=w;w->wdev_idx=(CHAR)i;w->registered=1;wdev_live++;return '
 'i;}\n'
 ' return-1;}\n'
 'static void wdev_idx_unreg(RTMP_ADAPTER *a,struct wifi_dev *w){assert(w->registered);\n'
 ' for(int '
 'i=0;i<WDEV_NUM_MAX;i++)if(a->wdev_list[i]==w){a->wdev_list[i]=NULL;w->registered=0;wdev_live--;return;}\n'
 ' assert(!"registered wdev absent");}\n'
 'static void hc_obj_init(struct wifi_dev *w,int '
 'i){assert(w->registered&&i>=0&&!w->hc_live);w->hc_live=1;}\n'
 'static void hc_obj_exit(struct wifi_dev *w){assert(w->hc_live);w->hc_live=0;}\n'
 'static void wlan_operate_exit(struct wifi_dev *w){assert(w->registered);assert(!config_exits);}\n'
 'static int wdev_ops_register(struct wifi_dev *w,enum WDEV_TYPE t,struct wifi_dev_ops *o,UCHAR '
 'm){\n'
 ' (void)t;(void)o;(void)m;assert(w->registered&&w->hc_live);ops_calls++;return '
 'ops_calls!=fail_ops;}\n'
 'static void vfree(void *p){assert(p&&ops_live>0);free(p);ops_live--;}\n'
 'static void free_netdev(PNET_DEV '
 'n){assert(n&&n->netdev_ops==NULL&&net_live>0);free(n);net_live--;}\n'
 'static PNET_DEV model_create(int slot){PNET_DEV '
 'n;create_calls++;if(create_calls==fail_create)return NULL;\n'
 ' '
 'n=calloc(1,sizeof(*n));assert(n);net_live++;if(create_calls==fail_ops_alloc){free_netdev(n);return '
 'NULL;}\n'
 ' '
 'n->netdev_ops=malloc(8);assert(n->netdev_ops);ops_live++;n->id=slot;snprintf(n->name,sizeof(n->name),"inert%d",slot);return '
 'n;}\n'
 'static PNET_DEV RtmpOSNetDevCreate(UINT32 r,UINT32 *i,INT t,UCHAR s,size_t n,void *name,BOOLEAN '
 'suffix){\n'
 ' (void)r;(void)i;(void)t;(void)n;(void)name;(void)suffix;return model_create(s);}\n'
 'static int model_snprintf(void *d,size_t n,const char *fmt,char *name){return '
 'snprintf(d,n,fmt,name);}\n'
 '#undef snprintf\n'
 '#define snprintf model_snprintf\n'
 'static char *get_dev_name_prefix(RTMP_ADAPTER *a,int type){(void)a;(void)type;return '
 'fail_prefix?NULL:"inert";}\n'
 '#define RTMP_OS_NETDEV_GET_WDEV(n) ((n)->wdev)\n'
 '#define RTMP_OS_NETDEV_GET_DEVNAME(n) ((n)->name)\n'
 '#define RTMP_OS_NETDEV_SET_WDEV(n,w) ((n)->wdev=(w))\n'
 '#define RTMP_OS_NETDEV_SET_PRIV(n,a) ((n)->adapter=fail_priv?NULL:(a))\n'
 '#define RTMP_OS_NETDEV_GET_PRIV(n) ((n)->adapter)\n'
 '#define RTMP_DRIVER_MAIN_INF_GET(a,out) (*(out)=1)\n'
 '#define RTMP_DRIVER_MAIN_INF_CREATE(a,out) (*(out)=model_create(0))\n'
 '#define RTMP_DRIVER_OP_MODE_GET(a,out) (*(out)=OPMODE_AP)\n'
 '#define RTMP_DRIVER_NET_DEV_SET(a,n) rtmp_netdev_set((a),(n))\n'
 'static int RtmpOSNetDevAttach(ULONG mode,PNET_DEV n,RTMP_OS_NETDEV_OP_HOOK *h){\n'
 ' (void)mode;assert(n->wdev==h->wdev&&n->wdev->registered&&!n->published);attach_calls++;\n'
 ' if(attach_calls==fail_attach)return NDIS_STATUS_FAILURE;\n'
 ' n->published=1;return NDIS_STATUS_SUCCESS;}\n'
 'static void RtmpOSNetDevProtect(int '
 'on){if(on){assert(!protect);protect=1;}else{assert(protect&&!lifecycle);protect=0;}}\n'
 'static void RtmpDmaLifecycleLock(RTMP_ADAPTER '
 '*a){assert(a==current&&protect&&!lifecycle);lifecycle=1;}\n'
 'static void RtmpDmaLifecycleUnlock(RTMP_ADAPTER '
 '*a){assert(a==current&&protect&&lifecycle);lifecycle=0;}\n'
 'static int RtmpDmaResourcesMayRelease(RTMP_ADAPTER *a){return !a->quarantined;}\n'
 'static int RtmpDmaFinalReleaseCheck(RTMP_ADAPTER *a){return a->dma_ok&&!a->quarantined;}\n'
 'static void retire_model(RTMP_ADAPTER *a){a->virtual_count=0;a->flags=0;a->HwCtrl.HwCtrlTask=0;\n'
 ' '
 'a->HwCtrl.HwCtrlQ.CmdQState=0;a->cmdQTask=0;a->RscTimerCreateList.size=0;a->HwCtrl.ser_task=0;a->HwCtrl.ser_initialized=0;a->dma_ok=1;}\n'
 'static int fully_retired(RTMP_ADAPTER *a){return '
 '!a->virtual_count&&!a->flags&&!a->HwCtrl.HwCtrlTask&&\n'
 ' !a->HwCtrl.HwCtrlQ.CmdQState&&!a->cmdQTask&&!a->RscTimerCreateList.size&&!a->HwCtrl.ser_task&&\n'
 ' !a->HwCtrl.ser_initialized&&a->dma_ok&&!a->quarantined;}\n'
 'static void dev_close(PNET_DEV n){RTMP_ADAPTER '
 '*a=n->adapter;assert(protect&&!lifecycle&&a==current&&a->dma_removing);\n'
 ' assert(n->flags&IFF_UP);closes++;if(concurrent_open){assert(a->dma_removing);open_rejects++;}\n'
 ' n->flags&=~IFF_UP;assert(a->virtual_count>0);a->virtual_count--;\n'
 ' if(!a->virtual_count){retire_model(a);switch(stop_mode){case 1:a->virtual_count=1;break;case '
 '2:a->flags=1;break;\n'
 ' case 3:a->HwCtrl.HwCtrlTask=1;break;case 4:a->HwCtrl.HwCtrlQ.CmdQState=1;break;case '
 '5:a->cmdQTask=1;break;\n'
 ' case 6:a->RscTimerCreateList.size=1;break;case 7:a->HwCtrl.ser_task=1;break;case '
 '8:a->HwCtrl.ser_initialized=1;break;\n'
 ' case 9:a->dma_ok=0;break;default:break;}}\n'
 ' /* Kernel ignores ndo_stop status; mode10 is status failure with completed retirement. */\n'
 '}\n'
 'static void RtmpOSNetDevDetach(PNET_DEV '
 'n){assert(protect&&fully_retired(current)&&!(n->flags&IFF_UP)&&!config_exits&&n->published);\n'
 ' if(n->netdev_ops){vfree(n->netdev_ops);n->netdev_ops=NULL;}n->published=0;}\n'
 'static void wpf_exit(void *v){RTMP_ADAPTER '
 '*a=v;assert(fully_retired(a)&&a->dma_removing&&net_live==1&&(wdev_live==0||bad_main_owner));config_exits++;}\n'
 '#define RT28xx_MBSS_Remove(a) MBSS_Remove(a)\n')

SUFFIX = ('\n'
 'static void initial(RTMP_ADAPTER '
 '*a){memset(a,0,sizeof(*a));a->hdev_ctrl=&cap;a->OpMode=OPMODE_AP;a->dma_ok=1;a->ApCfg.BssidNum=3;\n'
 ' for(int i=0;i<3;i++){a->ApCfg.MBSSID[i].wdev.bcn_buf.BeaconPkt=&beacon_tags[i];}current=a;}\n'
 'static void beacons(RTMP_ADAPTER *a){for(int '
 'i=0;i<3;i++)assert(a->ApCfg.MBSSID[i].wdev.bcn_buf.BeaconPkt==&beacon_tags[i]);}\n'
 'static void prepare_live(RTMP_ADAPTER '
 '*a){a->flags=1;a->HwCtrl.HwCtrlTask=1;a->cmdQTask=1;a->HwCtrl.HwCtrlQ.CmdQState=1;\n'
 ' a->RscTimerCreateList.size=1;a->HwCtrl.ser_task=1;a->HwCtrl.ser_initialized=1;\n'
 ' for(int '
 'i=0;i<3;i++)if(a->wdev_list[i]&&a->wdev_list[i]->if_dev){a->wdev_list[i]->if_dev->flags|=IFF_UP;a->virtual_count++;}}\n'
 'static void cleanup(RTMP_ADAPTER *a,PNET_DEV '
 'main){stop_mode=0;a->quarantined=0;retire_model(a);\n'
 ' for(int '
 'i=0;i<3;i++)if(a->wdev_list[i]&&a->wdev_list[i]->if_dev)a->wdev_list[i]->if_dev->flags&=~IFF_UP;\n'
 ' '
 'assert(RtmpPhyNetDevExit(a,main));assert(main==a->net_dev&&!main->wdev&&!a->ApCfg.MBSSID[0].wdev.if_dev&&wdev_live==0&&!vie_heap);\n'
 ' a->net_dev=NULL;RtmpOSNetDevFree(main);}\n'
 'int main(int argc,char **argv){const char *name;RTMP_ADAPTER a;RTMP_OS_NETDEV_OP_HOOK '
 'hook={0};PNET_DEV main=NULL;int result=1;\n'
 ' assert(argc==2);name=argv[1];CASE_ADMISSION initial(&a);\n'
 ' if(!strncmp(name,"vie-",4)){\n'
 ' struct wifi_dev *w=&a.ApCfg.MBSSID[0].wdev;struct vie_struct *out=(void*)1;UCHAR '
 'first[]={1,2,3},second[]={4,5,6,7};\n'
 ' init_vie_ctrl(w);\n'
 ' '
 'if(!strcmp(name,"vie-node-oom")||!strcmp(name,"vie-payload-oom")){vie_fail=!strcmp(name,"vie-node-oom")?1:2;\n'
 ' '
 'result=insert_vie(w,&out,VIE_BEACON_BITMAP,1,sizeof(first),first);assert(result!=NDIS_STATUS_SUCCESS&&!out&&!vie_heap&&!w->vie_ctrl[0].vie_num&&!w->vie_ctrl[0].vie_in_frm);result=0;\n'
 ' }else '
 'if(!strcmp(name,"vie-invalid-controller")){result=insert_vie(w,&out,0x8000,1,3,first);assert(result!=NDIS_STATUS_SUCCESS&&!out&&!vie_alloc_calls);result=0;\n'
 ' }else '
 'if(!strcmp(name,"vie-null-output")){result=insert_vie(w,NULL,1,1,3,first);assert(result!=NDIS_STATUS_SUCCESS&&!vie_alloc_calls);result=0;\n'
 ' }else '
 'if(!strcmp(name,"vie-null-wdev")){result=insert_vie(NULL,&out,1,1,3,first);assert(result!=NDIS_STATUS_SUCCESS&&!out&&!vie_alloc_calls);result=0;\n'
 ' }else '
 'if(!strcmp(name,"vie-null-frame")){result=insert_vie(w,&out,1,1,3,NULL);assert(result!=NDIS_STATUS_SUCCESS&&!out&&!vie_alloc_calls);result=0;\n'
 ' }else{\n'
 ' '
 'assert(insert_vie(w,&out,1,0x11223344,sizeof(first),first)==NDIS_STATUS_SUCCESS&&out&&vie_heap==2&&out->next_vie==NULL);\n'
 ' struct vie_struct *owner=out;UCHAR '
 '*payload=owner->ie_ctnt;assert(!memcmp(payload,first,sizeof(first))&&w->vie_ctrl[0].vie_num==1);\n'
 ' '
 'if(!strcmp(name,"vie-append-existing")){assert(insert_vie(w,&out,1,2,4,second)==NDIS_STATUS_SUCCESS&&owner->next_vie==out&&w->vie_ctrl[0].vie_num==2&&vie_heap==4&&out->next_vie==NULL);}\n'
 ' '
 'if(!strcmp(name,"vie-update-oom")){vie_fail=vie_alloc_calls+1;result=add_vie(&a,w,1,0x11223344,4,second);assert(result!=NDIS_STATUS_SUCCESS&&owner->ie_ctnt==payload&&owner->vie_length==3&&!memcmp(payload,first,3)&&vie_heap==2&&w->vie_ctrl[0].vie_num==1);result=0;}\n'
 ' '
 'if(!strcmp(name,"vie-update-success")){assert(add_vie(&a,w,1,0x11223344,4,second)==NDIS_STATUS_SUCCESS&&owner->ie_ctnt!=payload&&owner->vie_length==4&&!memcmp(owner->ie_ctnt,second,4)&&vie_heap==2&&w->vie_ctrl[0].vie_num==1);}\n'
 ' '
 'if(!strcmp(name,"vie-zero-length")){assert(add_vie(&a,w,1,0x11223344,0,NULL)==NDIS_STATUS_SUCCESS&&owner->vie_length==0&&vie_heap==2);}\n'
 ' if(!strcmp(name,"vie-registration-failure-preserves")){PNET_DEV '
 'n=model_create(0);fail_reg=1;result=wdev_init(&a,w,WDEV_TYPE_AP,n,0,NULL,&a);assert(!result&&!w->if_dev&&w->vie_ctrl[0].vie_in_frm==owner&&vie_heap==2);RtmpOSNetDevFree(n);}\n'
 ' }\n'
 ' init_vie_ctrl(w);assert(!vie_heap&&!w->vie_ctrl[0].vie_in_frm&&!w->vie_ctrl[0].vie_num);\n'
 ' if(!strcmp(name,"vie-repeat-init"))init_vie_ctrl(w);\n'
 ' deinit_vie_ctrl(w);if(!strcmp(name,"vie-repeat-deinit"))deinit_vie_ctrl(w);assert(!vie_heap);\n'
 ' }else if(!strncmp(name,"free-",5)){PNET_DEV '
 'n=model_create(0);if(!strcmp(name,"free-detached-ops")){vfree(n->netdev_ops);n->netdev_ops=NULL;}RtmpOSNetDevFree(n);\n'
 ' }else if(!strcmp(name,"wdev-registration-failure")){PNET_DEV n=model_create(0);fail_reg=1;\n'
 ' result=wdev_init(&a,&a.ApCfg.MBSSID[0].wdev,WDEV_TYPE_AP,n,0,NULL,&a);\n'
 ' assert(!result&&!a.ApCfg.MBSSID[0].wdev.if_dev&&!wdev_live);RtmpOSNetDevFree(n);\n'
 ' }else if(!strncmp(name,"main-",5)){\n'
 ' '
 'fail_create=!strcmp(name,"main-create-failure");fail_ops_alloc=!strcmp(name,"main-ops-allocation-failure");\n'
 ' '
 'fail_priv=!strcmp(name,"main-private-failure");fail_reg=!strcmp(name,"main-wdev-registration-failure");fail_ops=!strcmp(name,"main-ops-registration-failure");\n'
 ' main=RtmpPhyNetDevInit(&a,&hook);result=main!=NULL;\n'
 ' '
 'if(!strcmp(name,"main-success")){assert(main==a.net_dev&&wdev_live==1);main->published=1;cleanup(&a,main);}\n'
 ' else assert(!result&&!main&&!a.net_dev&&!wdev_live&&!a.ApCfg.MBSSID[0].wdev.if_dev);\n'
 ' }else{\n'
 ' main=RtmpPhyNetDevInit(&a,&hook);assert(main);main->published=1;\n'
 ' reg_calls=ops_calls=create_calls=attach_calls=0;\n'
 ' fail_prefix=!strcmp(name,"mbss-prefix-failure");\n'
 ' '
 'fail_create=!strcmp(name,"mbss-create-first-failure")?1:!strcmp(name,"mbss-create-second-failure")?2:0;\n'
 ' '
 'fail_reg=!strcmp(name,"mbss-registration-first-failure")?1:!strcmp(name,"mbss-registration-second-failure")?2:0;\n'
 ' fail_ops=!strcmp(name,"mbss-ops-first-failure")?1:!strcmp(name,"mbss-ops-second-failure")?2:0;\n'
 ' '
 'fail_attach=!strcmp(name,"mbss-attach-first-failure")?1:!strcmp(name,"mbss-attach-second-failure")?2:0;\n'
 ' MBSS_Init(&a,&hook);beacons(&a);assert(a.FlgMbssInit);\n'
 ' if(strstr(name,"failure")){int expected=strstr(name,"second")?2:1;\n'
 ' '
 'assert(a.ApCfg.BssidNum==expected&&wdev_live==expected&&net_live==expected&&ops_live==expected);\n'
 ' for(int i=expected;i<3;i++)assert(a.ApCfg.MBSSID[i].wdev.if_dev==NULL);}\n'
 ' if(!strcmp(name,"mbss-repeat-init")){int '
 'calls=create_calls;MBSS_Init(&a,&hook);assert(create_calls==calls);beacons(&a);}\n'
 ' '
 'if(!strcmp(name,"mbss-shrunk-remove")){a.ApCfg.BssidNum=1;MBSS_Remove(&a);assert(wdev_live==1&&net_live==1&&ops_live==1);beacons(&a);MBSS_Remove(&a);}\n'
 ' if(!strcmp(name,"mbss-live-remove")||!strcmp(name,"mbss-quarantined-remove")){\n'
 ' int '
 'before=net_live;a.flags=!strcmp(name,"mbss-live-remove");a.quarantined=!strcmp(name,"mbss-quarantined-remove");\n'
 ' '
 'MBSS_Remove(&a);assert(net_live==before&&wdev_live==3);beacons(&a);retention_observed=1;a.flags=a.quarantined=0;}\n'
 ' if(!strncmp(name,"closeall-",9)){\n'
 ' const char '
 '*busy[]={"closeall-count-busy","closeall-started-busy","closeall-hw-task-busy","closeall-hw-queue-busy","closeall-cmd-task-busy","closeall-timer-busy","closeall-ser-task-busy","closeall-ser-owner-busy","closeall-dma-busy"};\n'
 ' for(int i=0;i<9;i++)if(!strcmp(name,busy[i]))stop_mode=i+1;\n'
 ' if(!strcmp(name,"closeall-stop-status-failed-but-retired"))stop_mode=10;\n'
 ' concurrent_open=!strcmp(name,"closeall-open-excluded");prepare_live(&a);\n'
 ' struct wifi_dev '
 '*saved=a.wdev_list[0];if(!strcmp(name,"closeall-main-fallback"))a.wdev_list[0]=NULL;\n'
 ' '
 'result=RtmpPhyNetDevCloseAll(&a,main);if(!strcmp(name,"closeall-main-fallback"))a.wdev_list[0]=saved;\n'
 ' '
 'assert(!protect&&!lifecycle&&a.dma_removing&&closes==3);if(concurrent_open)assert(open_rejects==3);\n'
 ' if(stop_mode>0&&stop_mode<10){assert(!result&&!fully_retired(&a));int '
 'n=net_live;assert(!RtmpPhyNetDevExit(&a,main));assert(!config_exits&&net_live==n&&wdev_live==3);retention_observed=1;}\n'
 ' else{assert(result&&fully_retired(&a));if(!strcmp(name,"closeall-repeat")){int '
 'n=closes;assert(RtmpPhyNetDevCloseAll(&a,main));assert(closes==n);}}\n'
 ' }\n'
 ' if(!strcmp(name,"exit-quarantined")){a.quarantined=1;int '
 'n=net_live;result=RtmpPhyNetDevExit(&a,main);assert(!result&&!config_exits&&net_live==n&&!a.dma_removing);retention_observed=1;}\n'
 '\n'
 ' if(!strncmp(name,"exit-main-",10)){\n'
 '  struct wifi_dev *w=&a.ApCfg.MBSSID[0].wdev;struct wifi_dev foreign={0};UCHAR '
 'payload[]={9,8,7};\n'
 '  assert(add_vie(&a,w,1,1,3,payload)==NDIS_STATUS_SUCCESS&&vie_heap==2);\n'
 '  '
 'if(!strcmp(name,"exit-main-vie-owner")){assert(add_vie(&a,&a.ApCfg.MBSSID[2].wdev,1,2,3,payload)==NDIS_STATUS_SUCCESS&&vie_heap==4);prepare_live(&a);}\n'
 '  else{bad_main_owner=1;\n'
 '   if(!strcmp(name,"exit-main-unregistered")){a.wdev_list[0]=NULL;w->registered=0;wdev_live--;}\n'
 '   if(!strcmp(name,"exit-main-negative-index"))w->wdev_idx=(CHAR)-1;\n'
 '   '
 'if(!strcmp(name,"exit-main-wrong-owner")){foreign.registered=1;a.wdev_list[0]=&foreign;w->registered=0;}\n'
 '  }\n'
 '  result=RtmpPhyNetDevExit(&a,main);assert(result&&a.dma_removing&&!main->wdev&&!w->if_dev);\n'
 '  if(bad_main_owner){assert(vie_heap==2&&w->vie_ctrl[0].vie_num==1);retention_observed=1;\n'
 '   /* Corrupted/unregistered associations are outside the registered owner\n'
 '    * protocol. Explicit private fixture disposal follows the observation;\n'
 '    * it is not credited as production cleanup or a recovery guarantee. */\n'
 '   '
 'deinit_vie_ctrl(w);if(a.wdev_list[0]){a.wdev_list[0]->registered=0;a.wdev_list[0]=NULL;wdev_live--;}\n'
 '  }else assert(!vie_heap&&!wdev_live&&closes==3);\n'
 '  assert(!vie_heap&&!wdev_live&&config_exits==1);beacons(&a);RtmpOSNetDevFree(main);main=NULL;\n'
 ' }\n'
 ' if(main){beacons(&a);cleanup(&a,main);}\n'
 ' }\n'
 ' beacons(&a);assert(net_live==0&&ops_live==0&&wdev_live==0&&!protect&&!lifecycle);\n'
 ' '
 'printf("[%d,%d,%d,%d,%d,%d,1,%d]\\n",result,net_live,ops_live,wdev_live,unsafe_frees,retention_observed,a.dma_removing);\n'
 ' return 0;\n'
 '}\n')

def function(text,name):
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:inline\s+)?(?:VOID|BOOLEAN|UINT|INT|INT32|int|void|PNET_DEV|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    found=list(re.finditer(pattern,masked,re.M))
    if len(found)!=1:raise ValueError('Missing/ambiguous wdev function: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated function: '+name)

def declarations(texts):
    rows=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        matches=re.findall(pattern,texts[key],re.M)
        if len(matches)!=1:raise ValueError('Unique declaration required: '+pattern)
        rows.append(matches[0])
    return '\n'.join(rows)

def function_manifest(texts):
    return {n:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],n).encode()).hexdigest()}for n,key in FUNCTION_SOURCES.items()}

def source_only_manifest(texts):
    return {n:{'source':key,'execution':'source-only-not-run','full_body_sha256':hashlib.sha256(function(texts[key],n).encode()).hexdigest()}for n,key in SOURCE_ONLY_FUNCTION_SOURCES.items()}

def model_data_hash():
    import json
    names=('MODEL_VARIANT','BASE','SOURCE_PATHS','FUNCTION_SOURCES','BODY_ORDER','SOURCE_ONLY_FUNCTION_SOURCES','SOURCE_DECLARATIONS','CASE_NAMES','FIELDS','CASE_GROUPS','EXPECTED_ROWS','SOURCE_FIELD_CONSTRAINTS','PREFIX','SUFFIX')
    return hashlib.sha256(json.dumps({n:globals()[n]for n in names},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def generate_source(texts,variant='current'):
    if variant!='current'or set(texts)!=set(SOURCE_PATHS):raise ValueError('Current complete wdev source set required')
    function_manifest(texts);source_only_manifest(texts)
    bodies={n:function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER}
    prototypes='\n'.join(b[:b.index('{')].strip()+';'for b in bodies.values())
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts)).replace('FUNCTION_DECLARATIONS',prototypes)+'\n'.join(bodies.values())+SUFFIX.replace('CASE_ADMISSION',admission)

