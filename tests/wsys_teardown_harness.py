"""Source-bound terminal Wsys retirement composed with real last-VIF/DMA gates.

No real firmware, DMA, IRQ, radio or netdev runs. Queue allocation/retirement is
executed separately by hwcmd_owner_harness (including the locked delayed-producer
schedule); here the serialized queue seam copies the actual WIFI_SYS_CTRL declaration.
The 29 selected schedules include support bodies shared with wsys_lifecycle_harness.
Whole-body inclusion does not claim every helper or branch executes. Deep radio,
WCID and MMIO/MCU transports remain source-bound inert seams, except WcReleaseEdca
and the firmware ACK callbacks which are included whole.
"""
import hashlib
import re
SOURCE_PATHS = {'handler': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl.c',
 'cmd': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl_cmd.c',
 'v1': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl_ops_v1.c',
 'v2': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl_ops_v2.c',
 'sys': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/wifi_sys_info.c',
 'wdev': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/wdev.c',
 'asic': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/hw_ctrl/cmm_asic.c',
 'ap': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap.c',
 'apcli': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap_apcli.c',
 'wds': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap_wds.c',
 'entry': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mgmt/mgmt_entrytb.c',
 'header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/hw_ctrl.h',
 'sys_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/common/wifi_sys_info.h',
 'os_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/os/rt_linux.h',
 'lifetime': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_main_dev.c',
 'cfg': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/cfg80211/cfg80211_inf.c',
 'hdev': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev_ctrl.c',
 'radio': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev/radio_ctrl.c',
 'be': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mgmt/be_basic.c',
 'ap_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/ap.h',
 'fw': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/mcu/fw_cmd.c',
 'mcu_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/mcu/mt_cmd.h',
 'core': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mcu/andes_core.c',
 'mt_fw': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/hw_ctrl/cmm_asic_mt_fw.c',
 'wmm': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev/wmm_ctrl.c',
 'dispatch_core': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/cmm_cfg.c',
 'hdev_basic': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev/hdev_basic.c',
 'wtbl': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev/wtbl_ctrl.c',
 'radar': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/cmm_radar.c',
 'basic': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl_basic.c'}
FUNCTION_SOURCES = {'hw_ctrl_flow_v1_open': 'v1',
 'hw_ctrl_flow_v1_close': 'v1',
 'hw_ctrl_flow_v1_link_up': 'v1',
 'hw_ctrl_flow_v1_link_down': 'v1',
 'hw_ctrl_flow_v1_disconnt_act': 'v1',
 'hw_ctrl_flow_v1_connt_act': 'v1',
 'hw_ctrl_flow_v1_peer_update': 'v1',
 'hw_ctrl_ops_v1_register': 'v1',
 'hw_ctrl_flow_v2_open': 'v2',
 'hw_ctrl_flow_v2_close': 'v2',
 'hw_ctrl_flow_v2_link_up': 'v2',
 'hw_ctrl_flow_v2_link_down': 'v2',
 'hw_ctrl_flow_v2_disconnt_act': 'v2',
 'hw_ctrl_flow_v2_connt_act': 'v2',
 'hw_ctrl_flow_v2_peer_update': 'v2',
 'hw_ctrl_ops_v2_register': 'v2',
 'HwCtrlWifiSysOpen': 'handler',
 'HwCtrlWifiSysClose': 'handler',
 'HwCtrlWifiSysLinkUp': 'handler',
 'HwCtrlWifiSysLinkDown': 'handler',
 'HwCtrlWifiSysPeerLinkDown': 'handler',
 'HwCtrlWifiSysPeerLinkUp': 'handler',
 'HwCtrlWifiSysPeerUpdate': 'handler',
 'wifi_sys_queue_work': 'cmd',
 'HW_WIFISYS_OPEN': 'cmd',
 'HW_WIFISYS_CLOSE': 'cmd',
 'HW_WIFISYS_LINKUP': 'cmd',
 'HW_WIFISYS_LINKDOWN': 'cmd',
 'HW_WIFISYS_PEER_LINKUP': 'cmd',
 'HW_WIFISYS_PEER_LINKDOWN': 'cmd',
 'HW_WIFISYS_PEER_UPDATE': 'cmd',
 'HW_WIFISYS_RA_UPDATE': 'cmd',
 'fill_devinfo': 'sys',
 'fill_bssinfo_active': 'sys',
 'fill_bssinfo_deactive': 'sys',
 'fill_bssinfo': 'sys',
 'fill_starec': 'sys',
 'wifi_sys_update_devinfo': 'sys',
 'wifi_sys_update_bssinfo': 'sys',
 'wifi_sys_update_starec': 'sys',
 'wifi_sys_update_starec_info': 'sys',
 'wifi_sys_open': 'sys',
 'wifi_sys_close': 'sys',
 'wifi_sys_conn_act': 'sys',
 'wifi_sys_disconn_act': 'sys',
 'wifi_sys_linkup': 'sys',
 'wifi_sys_linkdown': 'sys',
 'WifiSysUpdateRa': 'sys',
 'WifiSysUpdatePortSecur': 'sys',
 'AsicDevInfoUpdate': 'asic',
 'AsicBssInfoUpdate': 'asic',
 'AsicStaRecUpdate': 'asic',
 'AsicRaParamStaRecUpdate': 'asic',
 'wdev_deinit': 'wdev',
 'wdev_do_open': 'wdev',
 'wdev_do_close': 'wdev',
 'wdev_do_linkup': 'wdev',
 'wdev_do_linkdown': 'wdev',
 'wdev_do_conn_act': 'wdev',
 'wdev_do_disconn_act': 'wdev',
 'ap_link_up': 'ap',
 'ap_conn_act': 'ap',
 'mac_entry_disconn_act': 'entry',
 'ApCli_Remove': 'apcli',
 'WDS_Remove': 'wds',
 'wifi_sys_abort_open': 'sys',
 'wdev_attr_update': 'wdev',
 'apcli_link_up': 'apcli',
 'CmdExtDevInfoUpdateRsp': 'fw',
 'CmdExtBssInfoUpdateRsp': 'fw',
 'CmdExtStaRecUpdateRsp': 'fw',
 'wifi_sys_retire': 'sys',
 'RtmpDmaQuarantined': 'lifetime',
 'RtmpDmaStopping': 'lifetime',
 'RtmpDmaResourcesMayRelease': 'lifetime',
 'RtmpDmaQuarantine': 'lifetime',
 'RtmpDmaTeardownCheck': 'lifetime',
 'virtual_if_down_handler': 'lifetime',
 'WcReleaseEdca': 'wmm',
 'ap_link_down': 'ap',
 'ap_inf_close': 'ap'}
BODY_ORDER = ('RtmpDmaQuarantined',
 'RtmpDmaStopping',
 'RtmpDmaResourcesMayRelease',
 'RtmpDmaQuarantine',
 'RtmpDmaTeardownCheck',
 'WcReleaseEdca',
 'hw_ctrl_flow_v1_open',
 'hw_ctrl_flow_v1_close',
 'hw_ctrl_flow_v1_link_up',
 'hw_ctrl_flow_v1_link_down',
 'hw_ctrl_flow_v1_disconnt_act',
 'hw_ctrl_flow_v1_connt_act',
 'hw_ctrl_flow_v1_peer_update',
 'hw_ctrl_ops_v1_register',
 'hw_ctrl_flow_v2_open',
 'hw_ctrl_flow_v2_close',
 'hw_ctrl_flow_v2_link_up',
 'hw_ctrl_flow_v2_link_down',
 'hw_ctrl_flow_v2_disconnt_act',
 'hw_ctrl_flow_v2_connt_act',
 'hw_ctrl_flow_v2_peer_update',
 'hw_ctrl_ops_v2_register',
 'HwCtrlWifiSysOpen',
 'HwCtrlWifiSysClose',
 'HwCtrlWifiSysLinkUp',
 'HwCtrlWifiSysLinkDown',
 'HwCtrlWifiSysPeerLinkDown',
 'HwCtrlWifiSysPeerLinkUp',
 'HwCtrlWifiSysPeerUpdate',
 'wifi_sys_queue_work',
 'HW_WIFISYS_OPEN',
 'HW_WIFISYS_CLOSE',
 'HW_WIFISYS_LINKUP',
 'HW_WIFISYS_LINKDOWN',
 'HW_WIFISYS_PEER_LINKUP',
 'HW_WIFISYS_PEER_LINKDOWN',
 'HW_WIFISYS_PEER_UPDATE',
 'HW_WIFISYS_RA_UPDATE',
 'fill_devinfo',
 'fill_bssinfo_active',
 'fill_bssinfo_deactive',
 'fill_bssinfo',
 'fill_starec',
 'wifi_sys_update_devinfo',
 'wifi_sys_update_bssinfo',
 'wifi_sys_update_starec',
 'wifi_sys_update_starec_info',
 'wifi_sys_open',
 'wifi_sys_close',
 'wifi_sys_conn_act',
 'wifi_sys_disconn_act',
 'wifi_sys_linkup',
 'wifi_sys_linkdown',
 'WifiSysUpdateRa',
 'WifiSysUpdatePortSecur',
 'AsicDevInfoUpdate',
 'AsicBssInfoUpdate',
 'AsicStaRecUpdate',
 'AsicRaParamStaRecUpdate',
 'wdev_deinit',
 'wdev_do_open',
 'wdev_do_close',
 'wdev_do_linkup',
 'wdev_do_linkdown',
 'wdev_do_conn_act',
 'wdev_do_disconn_act',
 'ap_link_up',
 'ap_conn_act',
 'mac_entry_disconn_act',
 'ApCli_Remove',
 'WDS_Remove',
 'wifi_sys_abort_open',
 'wdev_attr_update',
 'apcli_link_up',
 'CmdExtDevInfoUpdateRsp',
 'CmdExtBssInfoUpdateRsp',
 'CmdExtStaRecUpdateRsp',
 'wifi_sys_retire',
 'ap_link_down',
 'ap_inf_close',
 'virtual_if_down_handler')
SOURCE_ONLY_FUNCTION_SOURCES = {'MacTableDeleteEntry': 'entry',
 'MacTableInsertEntry': 'entry',
 'TRTableResetEntry': 'entry',
 'TRTableInsertEntry': 'entry',
 'TRTableInsertMcastEntry': 'entry',
 'RtmpDmaFinalReleaseCheck': 'lifetime',
 'RTMP_CFG80211_VirtualIF_Remove': 'cfg',
 'APStartUpForMbss': 'ap',
 'APStartUpByBss': 'ap',
 'ap_inf_open': 'ap',
 'HcAcquireRadioForWdev': 'hdev',
 'RcAcquiredBandForObj': 'radio',
 'wlan_operate_init': 'be',
 'AndesSendCmdMsg': 'core',
 'MtAsicSetDevMacByFw': 'mt_fw',
 'MtAsicSetBssidByFw': 'mt_fw',
 'MtAsicSetStaRecByFw': 'mt_fw',
 'CmdExtDevInfoUpdate': 'fw',
 'CmdExtBssInfoUpdate': 'fw',
 'CmdExtStaRecUpdate': 'fw',
 'BssInfoArgumentUnLink': 'wdev',
 'HcReleaseRadioForWdev': 'hdev',
 'RcReleaseBandForObj': 'radio',
 'HcReleaseEdca': 'hdev',
 'HcReleaseGroupKeyWcid': 'hdev',
 'WtcReleaseGroupKeyWcid': 'wtbl',
 'HdevObjDel': 'hdev_basic',
 'UpdateDot11hForWdev': 'radar',
 'RTMP_COM_IoctlHandle': 'dispatch_core',
 'HwCtrlEnqueueCmd': 'basic'}
SOURCE_DECLARATIONS={'struct WIFI_SYS_CTRL \\{[\\s\\S]*?\\n\\};': 'sys_header', 'typedef struct _HWCTRL_OP \\{[\\s\\S]*?\\} HWCTRL_OP;': 'header', 'typedef struct _HW_CTRL_TXD \\{[\\s\\S]*?\\} HW_CTRL_TXD;': 'header', 'enum \\{\\n\\tHWCMD_TYPE_FIRST[\\s\\S]*?\\n\\};': 'header', 'enum \\{\\n\\tHWCMD_ID_FIRST[\\s\\S]*?\\n\\};': 'header', '#define HW_CTRL_TXD_BASIC[^\\n]*\\n(?:[^\\n]*\\\\\\n)*[^\\n]*': 'cmd', '#define HW_CTRL_TXD_RSP[^\\n]*\\n(?:[^\\n]*\\\\\\n)*[^\\n]*': 'cmd', 'typedef struct GNU_PACKED _EVENT_DEVINFO_UPDATE_T \\{[\\s\\S]*?\\} EVENT_DEVINFO_UPDATE_T, \\*P_EVENT_DEVINFO_UPDATE_T;': 'mcu_header', 'typedef struct GNU_PACKED _EVENT_BSSINFO_UPDATE_T \\{[\\s\\S]*?\\} EVENT_BSSINFO_UPDATE_T, \\*P_EVENT_BSSINFO_UPDATE_T;': 'mcu_header', 'typedef struct GNU_PACKED _EVENT_STAREC_UPDATE_T \\{[\\s\\S]*?\\} EVENT_STAREC_UPDATE_T, \\*P_EVENT_STAREC_UPDATE_T;': 'mcu_header'}
STATUS_DECLARATIONS={'^#define NDIS_STATUS_SUCCESS\\s+(0x[0-9a-fA-F]+)\\s*$':0,
 '^#define NDIS_STATUS_FAILURE\\s+(0x[0-9a-fA-F]+)\\s*$':1,
 '^#define NDIS_STATUS_INVALID_DATA\\s+(0x[0-9a-fA-F]+)\\s*$':2,
 '^#define NDIS_STATUS_RESOURCES\\s+(0x[0-9a-fA-F]+)\\s*$':3}
MODEL_BOUNDARY={'whole_production_functions':True,'hardware_hooks_inert':True,
 'queue_admission_copy_seam_inert':True,'real_queue_timeout_retirement_in_hwcmd_component':True,
 'late_completion_before_publication_is_selected_inert_schedule':True,
 'no_claim_of_full_concurrent_entry_delete_or_cfg80211_teardown':True,
 'TXBF_key_EDCA_beacon_subcalls_are_void_or_inert':True,
 'no_hardware_or_kernel_task_execution':True}
FIELDS = ('ret',
 'stop',
 'idle',
 'quarantine',
 'bss',
 'active',
 'radio',
 'entry',
 'ifup',
 'hw',
 'blocked',
 'queued',
 'releases',
 'edca_hw',
 'snoop_hw',
 'sta',
 'errors')
CASE_NAMES = ('last-close',
 'last-close-cached-idle',
 'partial-inited-close',
 'last-close-busy',
 'last-close-tm-fail',
 'last-close-quarantined',
 'last-close-queue-reject',
 'nonlast-close',
 'first-abort-success',
 'first-abort-fw1',
 'first-abort-fw2',
 'first-abort-fw3',
 'first-abort-queue-reject',
 'peer-retire',
 'direct-close-not-idle',
 'helper-not-idle',
 'helper-active-payload',
 'helper-bss-payload',
 'helper-sta-payload',
 'helper-unknown',
 'helper-not-stopping',
 'terminal-quarantined',
 'edca-normal',
 'edca-terminal',
 'late-open',
 'late-linkup',
 'late-peerup',
 'late-peerupdate',
 'late-async-ra')
EXPECTED_ROWS = {'last-close': [0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 0, 0],
 'last-close-cached-idle': [0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 0, 0],
 'partial-inited-close': [0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 0, 0],
 'last-close-busy': [-5, 1, 0, 1, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'last-close-tm-fail': [-5, 1, 0, 1, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'last-close-quarantined': [-5, 1, 0, 1, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'last-close-queue-reject': [-1, 1, 1, 1, 3, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0],
 'nonlast-close': [0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 2, 2, 1, 1, 0, 0],
 'first-abort-success': [1, 0, 0, 0, 0, 0, 0, 0, 1, 3, 0, 2, 2, 1, 1, 0, 0],
 'first-abort-fw1': [0, 1, 0, 1, 3, 1, 1, 0, 1, 1, 0, 1, 0, 0, 0, 1, 0],
 'first-abort-fw2': [0, 1, 0, 1, 3, 1, 1, 0, 1, 2, 0, 1, 0, 0, 0, 0, 0],
 'first-abort-fw3': [0, 1, 0, 1, 0, 1, 1, 0, 1, 3, 0, 2, 1, 1, 0, 0, 0],
 'first-abort-queue-reject': [0, 1, 0, 1, 3, 1, 1, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0],
 'peer-retire': [1, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0],
 'direct-close-not-idle': [1, 1, 0, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'helper-not-idle': [1, 1, 0, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'helper-active-payload': [2, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'helper-bss-payload': [2, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'helper-sta-payload': [2, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'helper-unknown': [1, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'helper-not-stopping': [1, 0, 0, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'terminal-quarantined': [1, 1, 1, 1, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'edca-normal': [0, 0, 0, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0],
 'edca-terminal': [0, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'late-open': [1, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'late-linkup': [1, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'late-peerup': [1, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'late-peerupdate': [1, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0],
 'late-async-ra': [1, 1, 1, 0, 3, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0]}

PREFIX = ('\n'
 '#include <assert.h>\n'
 '#include <errno.h>\n'
 '#define IGMP_SNOOP_SUPPORT\n'
 '#define DBG_CAT_AP 0\n'
 '#define fRTMP_ADAPTER_HALT_IN_PROGRESS 1U\n'
 '#define fRTMP_ADAPTER_START_UP 2U\n'
 '#define fRTMP_ADAPTER_INTERRUPT_ACTIVE 4U\n'
 '#define IS_PCI_INF(a) 1\n'
 '#define IS_PCIE_INF(a) 0\n'
 '#define RTMP_SET_FLAG(a,f) ((a)->Flags|=(f))\n'
 '#define RTMP_CLEAR_FLAG(a,f) ((a)->Flags&=~(f))\n'
 '#define RTMP_TEST_FLAG(a,f) (!!((a)->Flags&(f)))\n'
 '#define READ_ONCE(x) (x)\n'
 '#define GET_PAD_FROM_NET_DEV(a,n) ((a)=(n)->adapter)\n'
 '#define VIRTUAL_IF_NUM(a) ((a)->vif_num)\n'
 '#include <stddef.h>\n'
 '#include <stdint.h>\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <string.h>\n'
 '#define CONFIG_AP_SUPPORT\n'
 '#define RACTRL_FW_OFFLOAD_SUPPORT\n'
 '#define MT_MAC\n'
 '#define GNU_PACKED __attribute__((packed))\n'
 '#define le2cpu32(v) (v)\n'
 '#define le2cpu16(v) (v)\n'
 '#define TRUE 1\n'
 '#define FALSE 0\n'
 '#define NDIS_STATUS_SUCCESS 0\n'
 '#define NDIS_STATUS_FAILURE 1\n'
 '#define NDIS_STATUS_INVALID_DATA 2\n'
 '#define NDIS_STATUS_RESOURCES 3\n'
 '#define WLAN_OPER_STATE_INVALID 0\n'
 '#define WLAN_OPER_STATE_VALID 1\n'
 '#define BSS_INIT 0\n'
 '#define BSS_INITED 1\n'
 '#define BSS_ACTIVE 2\n'
 '#define BSS_READY 3\n'
 '#define ENTRY_STATE_NONE 0\n'
 '#define ENTRY_STATE_SYNC 1\n'
 '#define STATE_DISCONNECT 0\n'
 '#define STATE_CONNECTED 1\n'
 '#define STATE_PORT_SECURE 2\n'
 '#define WDEV_TYPE_AP 1\n'
 '#define WDEV_TYPE_WDS 2\n'
 '#define WDEV_TYPE_APCLI 3\n'
 '#define WDEV_TYPE_GO 4\n'
 '#define OPMODE_AP 1\n'
 '#define HC_STATUS_OK 0\n'
 '#define MSDU_FORBID_CONNECTION_NOT_READY 1\n'
 '#define WPA_802_1X_PORT_SECURED 2\n'
 '#define UMH_WAIT_PROC 1\n'
 '#define MSDU_FORBID_CLEAR(w,f) ((void)(w),(void)(f))\n'
 '#define COPY_MAC_ADDR(d,a) memmove((d),(a),6)\n'
 '#define RTMP_OS_NETDEV_GET_PHYADDR(d) dev_addr\n'
 '#define DEVINFO_ACTIVE_FEATURE 1\n'
 '#define STA_REC_BASIC_STA_RECORD_FEATURE 1\n'
 '#define STA_REC_INSTALL_KEY_FEATURE 2\n'
 '#define STA_REC_RA_COMMON_INFO_FEATURE 4\n'
 '#define STA_REC_RA_FEATURE 8\n'
 '#define STA_REC_RA_UPDATE_FEATURE 16\n'
 '#define CONNECTION_INFRA_BC 1\n'
 '#define HIF_MT 1\n'
 '#define MAC_ADDR_LEN 6\n'
 '#define MAX_APCLI_NUM 2\n'
 '#define MAX_WDS_ENTRY 2\n'
 '#define WCID_ALL 255\n'
 '#define TXOP_0 0\n'
 '#define TXOP_80 80\n'
 '#define AC_BE 0\n'
 '#define PRIO_DEFAULT 0\n'
 '#define BCN_UPDATE_INIT 0\n'
 '#define BCN_UPDATE_IE_CHG 1\n'
 '#define fOP_AP_STATUS_MEDIA_STATE_CONNECTED 1\n'
 '#define WPA_802_1X_PORT_NOT_SECURED 0\n'
 '#define WDEV_BSS_STATE(w) ((w)->bss_info_argument.bss_state)\n'
 '#define WDEV_WITH_BCN_ABILITY(w) 1\n'
 '#define MTWF_LOG(...) ((void)0)\n'
 '#define PRINT_MAC(a) 0\n'
 '#define ASSERT(x) assert(x)\n'
 '#define IS_HIF_TYPE(a,t) 1\n'
 '#define VALID_UCAST_ENTRY_WCID(a,w) ((w)<8)\n'
 '#define GET_MAX_UCAST_NUM(a) 8\n'
 '#define IS_ENTRY_NONE(e) (!(e)->EntryType)\n'
 '#define IS_ENTRY_REPEATER(e) ((e)->EntryType==3)\n'
 '#define IS_ENTRY_CLIENT(e) ((e)->EntryType==1)\n'
 '#define OPSTATUS_SET_FLAG_WDEV(w,f) ((w)->media=1)\n'
 '#define IF_DEV_CONFIG_OPMODE_ON_AP(a) if(1)\n'
 '#define RESET_FLAG_CONN_IN_PROG(a,c) ((c)=0)\n'
 '#define os_zero_mem(p,n) memset((p),0,(n))\n'
 '#define os_move_mem(p,s,n) memmove((p),(s),(n))\n'
 '#define NdisMoveMemory(p,s,n) memmove((p),(s),(n))\n'
 'typedef unsigned long ULONG;\n'
 'typedef void VOID;typedef unsigned char UCHAR,UINT8;typedef uint16_t UINT16;typedef uint32_t '
 'UINT32;typedef int INT,INT32,NTSTATUS,NDIS_STATUS,BOOLEAN;typedef unsigned int UINT;\n'
 'struct net_device {struct _RTMP_ADAPTER *adapter;int irq;};\n'
 'typedef struct {int dma_state_lock;void *pci_dev;} OS_COOKIE,*POS_COOKIE;\n'
 'typedef struct {int RefCnt,bValid;UINT32 WmmSet;} EDCA_PARM;\n'
 'struct radio_dev {void *priv;int Idx;};\n'
 'struct hdev_ctrl {void *priv;};\n'
 'struct hdev_obj {int bWmmAcquired,Idx,WmmIdx;struct radio_dev *rdev;};\n'
 'struct _RTMP_ADAPTER;struct wifi_dev;struct WIFI_SYS_CTRL;struct _STA_REC_CFG_T;struct _STA_REC_CFG_T;\n'
 'typedef NTSTATUS(*HwCmdCb)(struct _RTMP_ADAPTER*,VOID*);\n'
 'typedef struct {int list;} DL_LIST;\n'
 'typedef struct {UINT32 u4Field;UCHAR padding[60];} '
 'CMD_STAREC_AUTO_RATE_UPDATE_T,*P_CMD_STAREC_AUTO_RATE_UPDATE_T;\n'
 'typedef struct {int dummy;} ASIC_SEC_INFO;\n'
 'typedef struct _DEV_INFO_CTRL_T {UCHAR Active,OwnMacIdx,OwnMacAddr[6],BandIdx;UINT32 EnableFeature;DL_LIST '
 'list;} DEV_INFO_CTRL_T;\n'
 'typedef struct _STA_REC_CTRL_T {UINT8 BssIndex,WlanIdx,ConnectionState;UINT32 '
 'ConnectionType,EnableFeature;BOOLEAN IsNewSTARec;ASIC_SEC_INFO asic_sec_info;VOID *priv;DL_LIST list;} '
 'STA_REC_CTRL_T;\n'
 'typedef struct _BSS_INFO_ARGUMENT_T {int bss_state;UINT8 ucBssIndex,ucBcMcWlanIdx,ucPeerWlanIdx;UINT32 '
 'u4ConnectionType,u4BssInfoFeature;UINT8 Bssid[6];DL_LIST list;} BSS_INFO_ARGUMENT_T;\n'
 'SOURCE_DEFINITIONS\n'
 'typedef struct _MAC_TABLE_ENTRY {struct wifi_dev *wdev;int EntryState,EntryType,tr_tb_idx;UINT8 '
 'wcid,Addr[6];UINT32 ConnectionType;struct {UINT32 AKMMap,PairwiseCipher;} SecConfig;} '
 'MAC_TABLE_ENTRY,*PMAC_TABLE_ENTRY;\n'
 'typedef struct _STA_TR_ENTRY {STA_REC_CTRL_T StaRec;struct wifi_dev *wdev;UINT8 Addr[6],OmacIdx;int '
 'PortSecured;} STA_TR_ENTRY;\n'
 'struct wifi_dev_ops {INT(*open)(struct wifi_dev*);INT(*close)(struct wifi_dev*);INT(*linkup)(struct '
 'wifi_dev*,struct _MAC_TABLE_ENTRY*);INT(*linkdown)(struct wifi_dev*);INT(*conn_act)(struct '
 'wifi_dev*,struct _MAC_TABLE_ENTRY*);INT(*disconn_act)(struct wifi_dev*,struct _MAC_TABLE_ENTRY*);};\n'
 'struct wifi_dev {VOID *sys_handle,*if_dev;DEV_INFO_CTRL_T DevInfo;BSS_INFO_ARGUMENT_T '
 'bss_info_argument;struct wifi_dev_ops *wdev_ops;struct hdev_obj *pHObj;int '
 'if_up_down_state,bAllowBeaconing;int '
 'wdev_type,wdev_idx,tr_tb_idx,oper,radio,media,protection,func_idx,PortSecured;UINT8 '
 'OmacIdx,if_addr[6],bssid[6];};\n'
 'struct _APCLI_STRUCT {struct wifi_dev wdev;int ApCliInit,Valid;};\n'
 'typedef struct _RTMP_ADAPTER {struct {HWCTRL_OP hwctrl_ops;} HwCtrl;struct {int bEnableTxBurst,bRdg;} '
 'CommonCfg;struct {STA_TR_ENTRY tr_entry[8];MAC_TABLE_ENTRY Content[8];} MacTab;struct {struct '
 '_APCLI_STRUCT ApCliTab[2];} ApCfg;struct {struct {struct wifi_dev wdev;} WdsEntry[2];int flg_wds_init;} '
 'WdsTab;int '
 'dma_running,dma_stopping,dma_quarantined,dma_lifecycle_pinned,dma_quiesced,dma_irq_registered,dma_cmd_task_retired,vif_num,Flags,qm_wq_state,hif_wq_state;void '
 '*tm_qm_ops,*tm_hif_ops,*OS_Cookie;struct net_device *net_dev;struct wifi_dev *wdev_list[8];int '
 'quarantined,flg_apcli_init,ConInPrgress;struct {INT32(*archSetDevMac)(struct '
 '_RTMP_ADAPTER*,UINT8,UINT8*,UINT8,UINT8,UINT32);INT32(*archSetBssid)(struct '
 '_RTMP_ADAPTER*,BSS_INFO_ARGUMENT_T);INT32(*archSetStaRec)(struct _RTMP_ADAPTER*,struct _STA_REC_CFG_T);} '
 'archOps;} RTMP_ADAPTER,*PRTMP_ADAPTER;\n'
 'typedef struct _STA_REC_CFG_T {int MuarIdx,ConnectionState,ConnectionType;UINT32 u4EnableFeature;UINT8 '
 'ucBssIndex,ucWlanIdx;MAC_TABLE_ENTRY *pEntry;BOOLEAN IsNewSTARec;ASIC_SEC_INFO '
 'asic_sec_info;P_CMD_STAREC_AUTO_RATE_UPDATE_T pRaParam;} STA_REC_CFG_T;\n'
 'typedef struct {struct {int OperaionMode;} AddHtInfo2;} ADD_HT_INFO_IE;\n'
 'typedef struct _HwCmdQElmt {void *buffer;UINT32 bufferlength;} HwCmdQElmt;\n'
 'static int '
 'hw_calls,commits,releases,queued,fail_at,late_at,queue_error,interrupt_context,ra_value,async_pending;\n'
 'static int firmware_ack_error;\n'
 'struct cmd_msg {UINT32 cmd_return_status;};\n'
 'static VOID CmdExtDevInfoUpdateRsp(struct cmd_msg*,char*,UINT16);\n'
 'static VOID CmdExtBssInfoUpdateRsp(struct cmd_msg*,char*,UINT16);\n'
 'static VOID CmdExtStaRecUpdateRsp(struct cmd_msg*,char*,UINT16);\n'
 'static int notifies,starec_exists,rekey,cleaned,detached,freed,attr_error,usermode_calls;\n'
 'static UCHAR dev_addr[6];\n'
 'static RTMP_ADAPTER *active;static struct WIFI_SYS_CTRL saved;\n'
 'BOOLEAN RtmpDmaQuarantined(RTMP_ADAPTER *a);\n'
 '/* Old171 observations run before terminal stop; composed retirement is separate. */\n'
 'BOOLEAN RtmpDmaStopping(RTMP_ADAPTER *a);\n'
 'BOOLEAN RtmpDmaResourcesMayRelease(RTMP_ADAPTER *a);\n'
 'INT wifi_sys_retire(struct _RTMP_ADAPTER *ad, struct WIFI_SYS_CTRL *wsys, UINT32 id);\n'
 'static int in_interrupt(void){return interrupt_context;}\n'
 'static void dump_stack(void){}\n'
 'static int wlan_operate_get_state(struct wifi_dev *w){return w->oper;}\n'
 'static void wlan_operate_set_state(struct wifi_dev *w,int n){w->oper=n;}\n'
 'static INT32 wdev_attr_update(RTMP_ADAPTER *pAd,struct wifi_dev *wdev);\n'
 'static INT32 HcAcquireRadioForWdev(RTMP_ADAPTER *a,struct wifi_dev '
 '*w){assert(a==active);if(attr_error)return 1;w->radio=1;return HC_STATUS_OK;}\n'
 'static void AsicSetMbssWdevIfAddr(RTMP_ADAPTER *a,int i,UCHAR *addr,int '
 'mode){assert(a==active&&addr);(void)i;(void)mode;}\n'
 'VOID RtmpDmaQuarantine(RTMP_ADAPTER *a);\n'
 'VOID WcReleaseEdca(struct hdev_obj *obj);\n'
 'static int call_usermodehelper(char *p,char **argv,char **envp,int '
 'mode){assert(p&&argv&&envp&&mode==UMH_WAIT_PROC);usermode_calls++;return 0;}\n'
 'static void HcReleaseRadioForWdev(RTMP_ADAPTER *a,struct wifi_dev '
 '*w){assert(a==active);if(w->pHObj)WcReleaseEdca(w->pHObj);w->radio=0;releases++;}\n'
 'static int HcGetBandByWdev(struct wifi_dev *w){assert(w);return 0;}\n'
 'static int HcIsRadioAcq(struct wifi_dev *w){return w->radio;}\n'
 'static void UpdateDot11hForWdev(RTMP_ADAPTER *a,struct wifi_dev *w,int on){assert(a==active&&w&&!on);}\n'
 'static void BssInfoArgumentLink(RTMP_ADAPTER *a,struct wifi_dev *w,BSS_INFO_ARGUMENT_T '
 '*b){assert(a==active&&w);b->bss_state=BSS_INITED;b->ucBssIndex=2;b->ucBcMcWlanIdx=0;b->u4ConnectionType=1;}\n'
 'static void BssInfoArgumentUnLink(RTMP_ADAPTER *a,struct wifi_dev '
 '*w){assert(a==active);if(w->pHObj)WcReleaseEdca(w->pHObj);releases++;memset(&w->bss_info_argument,0,sizeof(w->bss_info_argument));}\n'
 'static void add_devinfo(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);commits++;}\n'
 'static void del_devinfo(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);commits++;}\n'
 'static void add_bssinfo(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);commits++;}\n'
 'static void del_bssinfo(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);commits++;}\n'
 'static void add_starec(RTMP_ADAPTER *a,STA_TR_ENTRY *t){assert(a==active&&t);commits++;}\n'
 'static void del_starec(RTMP_ADAPTER *a,STA_TR_ENTRY *t){assert(a==active&&t);commits++;}\n'
 'enum '
 '{WSYS_NOTIFY_OPEN,WSYS_NOTIFY_CLOSE,WSYS_NOTIFY_CONNT_ACT,WSYS_NOTIFY_DISCONNT_ACT,WSYS_NOTIFY_LINKUP,WSYS_NOTIFY_LINKDOWN,WSYS_NOTIFY_STA_UPDATE};\n'
 'static int call_wsys_notifieriers(int n,struct wifi_dev *w,void '
 '*p){(void)p;assert(w);notifies++;if(n==WSYS_NOTIFY_STA_UPDATE)commits++;return 0;}\n'
 'static void HcSetEdca(struct wifi_dev *w){assert(w);}\n'
 'static void hw_set_tx_burst(RTMP_ADAPTER *a,struct wifi_dev *w,int ac,int pr,int lev,int '
 'on){assert(a==active&&w);(void)ac;(void)pr;(void)lev;(void)on;}\n'
 'static void UpdateBeaconHandler(RTMP_ADAPTER *a,struct wifi_dev *w,int n){assert(a==active&&w);(void)n;}\n'
 'static void AsicUpdateRxWCIDTable(RTMP_ADAPTER *a,int i,UINT8 *addr,int add,int '
 'reset){assert(a==active&&addr);(void)i;(void)add;(void)reset;}\n'
 'static void AsicAddRemoveKeyTab(RTMP_ADAPTER *a,ASIC_SEC_INFO *i){assert(a==active&&i);}\n'
 'static void AsicDelWcidTab(RTMP_ADAPTER *a,int i){assert(a==active);(void)i;}\n'
 'static ADD_HT_INFO_IE *wlan_operate_get_addht(struct wifi_dev *w){static ADD_HT_INFO_IE '
 'info;assert(w);return &info;}\n'
 'static void AsicUpdateProtect(RTMP_ADAPTER *a){assert(a==active);}\n'
 'static int get_starec_by_wcid(RTMP_ADAPTER *a,int i){assert(a==active);(void)i;return starec_exists;}\n'
 'static void AsicNotSupportFunc(RTMP_ADAPTER *a,const char *n){assert(a==active&&n);}\n'
 'static void starec_feature_decision(struct wifi_dev *w,UINT32 t,MAC_TABLE_ENTRY *e,UINT32 '
 '*f){assert(w);(void)t;(void)e;*f|=STA_REC_BASIC_STA_RECORD_FEATURE;}\n'
 'static void starec_security_decision(struct wifi_dev *w,MAC_TABLE_ENTRY *e,UCHAR '
 '*s){assert(w);(void)e;*s=STATE_CONNECTED;}\n'
 'static void starec_security_set(struct wifi_dev *w,MAC_TABLE_ENTRY *e,STA_REC_CTRL_T '
 '*s){assert(w&&e&&s);}\n'
 'static void bssinfo_feature_decision(struct wifi_dev *w,UINT32 t,UCHAR i,UINT32 '
 '*f){assert(w);(void)t;(void)i;*f|=1;}\n'
 'static void APKeyTableInit(RTMP_ADAPTER *a,struct wifi_dev *w,STA_REC_CTRL_T '
 '*s){assert(a==active&&w&&s);}\n'
 'static void CheckBMCPortSecured(RTMP_ADAPTER *a,MAC_TABLE_ENTRY *e,int b){assert(a==active&&e);(void)b;}\n'
 'static void APStartRekeyTimer(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);rekey++;}\n'
 'static void deinit_vie_ctrl(struct wifi_dev *w){assert(w);cleaned++;}\n'
 'static void wlan_operate_exit(struct wifi_dev *w){assert(w);cleaned++;}\n'
 'static void hc_obj_exit(struct wifi_dev *w){assert(w);cleaned++;}\n'
 'static int wdev_idx_unreg(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);cleaned++;return '
 'TRUE;}\n'
 'static void RtmpOSNetDevProtect(int n){(void)n;}\n'
 'static void RtmpOSNetDevDetach(void *d){assert(d);detached++;}\n'
 'static void RtmpOSNetDevFree(void *d){assert(d);freed++;}\n'
 'static void ba_session_tear_down_all(RTMP_ADAPTER *a,int i){assert(a==active);(void)i;}\n'
 'static int blocked_hw;\n'
 'static int hook_result(void){hw_calls++;if(RtmpDmaStopping(active)){blocked_hw++;return '
 'NDIS_STATUS_FAILURE;}if(hw_calls==late_at)active->quarantined=1;return '
 'hw_calls==fail_at?NDIS_STATUS_RESOURCES:NDIS_STATUS_SUCCESS;}\n'
 'static INT32 hook_dev(RTMP_ADAPTER *a,UINT8 i,UINT8 *m,UINT8 b,UINT8 on,UINT32 '
 'f){assert(a==active&&m);(void)i;(void)b;(void)on;(void)f;int r=hook_result();struct cmd_msg '
 'msg={1};EVENT_DEVINFO_UPDATE_T event={0};if(r)return '
 'r;event.u4Status=firmware_ack_error;CmdExtDevInfoUpdateRsp(&msg,(char*)&event,sizeof(event));return '
 'msg.cmd_return_status;}\n'
 'static INT32 hook_bss(RTMP_ADAPTER *a,BSS_INFO_ARGUMENT_T b){assert(a==active);(void)b;int '
 'r=hook_result();struct cmd_msg msg={1};EVENT_BSSINFO_UPDATE_T event={0};if(r)return '
 'r;event.u4Status=firmware_ack_error;CmdExtBssInfoUpdateRsp(&msg,(char*)&event,sizeof(event));return '
 'msg.cmd_return_status;}\n'
 'static INT32 hook_sta(RTMP_ADAPTER *a,STA_REC_CFG_T '
 's){assert(a==active);if(s.pRaParam)ra_value=s.pRaParam->u4Field;int r=hook_result();struct cmd_msg '
 'msg={1};EVENT_STAREC_UPDATE_T event={0};if(r)return '
 'r;event.u4Status=firmware_ack_error;CmdExtStaRecUpdateRsp(&msg,(char*)&event,sizeof(event));return '
 'msg.cmd_return_status;}\n'
 'static NTSTATUS hw_ctrl_flow_v1_open(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v1_close(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v1_link_up(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v1_link_down(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v1_disconnt_act(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v1_connt_act(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v1_peer_update(struct WIFI_SYS_CTRL *wsys);\n'
 'VOID hw_ctrl_ops_v1_register(struct _HWCTRL_OP *hwctrl_ops);\n'
 'static NTSTATUS hw_ctrl_flow_v2_open(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v2_close(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v2_link_up(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v2_link_down(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v2_disconnt_act(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v2_connt_act(struct WIFI_SYS_CTRL *wsys);\n'
 'static NTSTATUS hw_ctrl_flow_v2_peer_update(struct WIFI_SYS_CTRL *wsys);\n'
 'VOID hw_ctrl_ops_v2_register(struct _HWCTRL_OP *hwctrl_ops);\n'
 'static NTSTATUS HwCtrlWifiSysOpen(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);\n'
 'static NTSTATUS HwCtrlWifiSysClose(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);\n'
 'static NTSTATUS HwCtrlWifiSysLinkUp(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);\n'
 'static NTSTATUS HwCtrlWifiSysLinkDown(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);\n'
 'static NTSTATUS HwCtrlWifiSysPeerLinkDown(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);\n'
 'static NTSTATUS HwCtrlWifiSysPeerLinkUp(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);\n'
 'static NTSTATUS HwCtrlWifiSysPeerUpdate(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);\n'
 'static NDIS_STATUS wifi_sys_queue_work(struct _RTMP_ADAPTER *ad, UINT32 id, struct WIFI_SYS_CTRL *wsys);\n'
 'NDIS_STATUS HW_WIFISYS_OPEN(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tstruct WIFI_SYS_CTRL *wsys);\n'
 'NDIS_STATUS HW_WIFISYS_CLOSE(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tstruct WIFI_SYS_CTRL *wsys);\n'
 'NDIS_STATUS HW_WIFISYS_LINKUP(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tstruct WIFI_SYS_CTRL *wsys);\n'
 'NDIS_STATUS HW_WIFISYS_LINKDOWN(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tstruct WIFI_SYS_CTRL *wsys);\n'
 'NDIS_STATUS HW_WIFISYS_PEER_LINKUP(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tstruct WIFI_SYS_CTRL *wsys);\n'
 'NDIS_STATUS HW_WIFISYS_PEER_LINKDOWN(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tstruct WIFI_SYS_CTRL *wsys);\n'
 'NDIS_STATUS HW_WIFISYS_PEER_UPDATE(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tstruct WIFI_SYS_CTRL *wsys);\n'
 'NDIS_STATUS HW_WIFISYS_RA_UPDATE(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tstruct WIFI_SYS_CTRL *wsys);\n'
 'static VOID fill_devinfo(\n'
 '\tstruct _RTMP_ADAPTER *pAd,\n'
 '\tstruct wifi_dev *wdev,\n'
 '\tBOOLEAN act,\n'
 '\tstruct _DEV_INFO_CTRL_T *devinfo);\n'
 'static inline VOID fill_bssinfo_active(\n'
 '\tstruct _RTMP_ADAPTER *ad,\n'
 '\tstruct wifi_dev *wdev,\n'
 '\tstruct _BSS_INFO_ARGUMENT_T *bssinfo);\n'
 'static inline VOID fill_bssinfo_deactive(\n'
 '\tstruct _RTMP_ADAPTER *ad,\n'
 '\tstruct wifi_dev *wdev,\n'
 '\tstruct _BSS_INFO_ARGUMENT_T *bssinfo);\n'
 'static VOID fill_bssinfo(\n'
 '\tstruct _RTMP_ADAPTER *ad,\n'
 '\tstruct wifi_dev *wdev,\n'
 '\tBOOLEAN act,\n'
 '\tstruct _BSS_INFO_ARGUMENT_T *bssinfo);\n'
 'static VOID fill_starec(\n'
 '\tstruct _RTMP_ADAPTER *ad,\n'
 '\tstruct _STA_TR_ENTRY *tr_entry,\n'
 '\tstruct _STA_REC_CTRL_T *starec);\n'
 'INT wifi_sys_update_devinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev, struct _DEV_INFO_CTRL_T '
 '*new);\n'
 'INT wifi_sys_update_bssinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev, struct _BSS_INFO_ARGUMENT_T '
 '*new);\n'
 'INT wifi_sys_update_starec(struct _RTMP_ADAPTER *ad, struct _STA_REC_CTRL_T *new);\n'
 'INT wifi_sys_update_starec_info(struct _RTMP_ADAPTER *ad, struct _STA_REC_CTRL_T *new);\n'
 'INT wifi_sys_open(struct wifi_dev *wdev);\n'
 'INT wifi_sys_close(struct wifi_dev *wdev);\n'
 'INT wifi_sys_conn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'INT wifi_sys_disconn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'INT wifi_sys_linkup(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'INT wifi_sys_linkdown(struct wifi_dev *wdev);\n'
 'VOID WifiSysUpdateRa(RTMP_ADAPTER *pAd,\n'
 '\t\t\t\t\t MAC_TABLE_ENTRY *pEntry,\n'
 '\t\t\t\t\t P_CMD_STAREC_AUTO_RATE_UPDATE_T prParam\n'
 '\t\t\t\t\t);\n'
 'VOID WifiSysUpdatePortSecur(RTMP_ADAPTER *pAd, MAC_TABLE_ENTRY *pEntry, ASIC_SEC_INFO *asic_sec_info);\n'
 'INT32 AsicDevInfoUpdate(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tUINT8 OwnMacIdx,\n'
 '\tUINT8 *OwnMacAddr,\n'
 '\tUINT8 BandIdx,\n'
 '\tUINT8 Active,\n'
 '\tUINT32 EnableFeature);\n'
 'INT32 AsicBssInfoUpdate(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tBSS_INFO_ARGUMENT_T bss_info_argument);\n'
 'INT32 AsicStaRecUpdate(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tSTA_REC_CTRL_T *sta_rec_ctrl);\n'
 'INT32 AsicRaParamStaRecUpdate(\n'
 '\tRTMP_ADAPTER *pAd,\n'
 '\tUINT8 WlanIdx,\n'
 '\tP_CMD_STAREC_AUTO_RATE_UPDATE_T prParam,\n'
 '\tUINT32 EnableFeature);\n'
 'INT32 wdev_deinit(RTMP_ADAPTER *pAd, struct wifi_dev *wdev);\n'
 'INT wdev_do_open(struct wifi_dev *wdev);\n'
 'INT wdev_do_close(struct wifi_dev *wdev);\n'
 'INT wdev_do_linkup(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'INT wdev_do_linkdown(struct wifi_dev *wdev);\n'
 'INT wdev_do_conn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'INT wdev_do_disconn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'INT ap_link_up(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'INT ap_conn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'static BOOLEAN mac_entry_disconn_act(struct _RTMP_ADAPTER *pAd, struct _MAC_TABLE_ENTRY *pEntry);\n'
 'VOID ApCli_Remove(RTMP_ADAPTER *pAd);\n'
 'VOID WDS_Remove(RTMP_ADAPTER *pAd);\n'
 'INT wifi_sys_abort_open(struct wifi_dev *wdev);\n'
 'INT apcli_link_up(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);\n'
 'static NTSTATUS dispatch(RTMP_ADAPTER *a,UINT32 id,struct WIFI_SYS_CTRL *w){HwCmdQElmt '
 'c={w,sizeof(*w)};switch(id){case HWCMD_ID_WIFISYS_OPEN:return HwCtrlWifiSysOpen(a,&c);case '
 'HWCMD_ID_WIFISYS_CLOSE:return HwCtrlWifiSysClose(a,&c);case HWCMD_ID_WIFISYS_LINKUP:return '
 'HwCtrlWifiSysLinkUp(a,&c);case HWCMD_ID_WIFISYS_LINKDOWN:return HwCtrlWifiSysLinkDown(a,&c);case '
 'HWCMD_ID_WIFISYS_PEER_LINKUP:return HwCtrlWifiSysPeerLinkUp(a,&c);case '
 'HWCMD_ID_WIFISYS_PEER_LINKDOWN:return HwCtrlWifiSysPeerLinkDown(a,&c);case '
 'HWCMD_ID_WIFISYS_PEER_UPDATE:return HwCtrlWifiSysPeerUpdate(a,&c);default:abort();}}\n'
 'static NDIS_STATUS HwCtrlEnqueueCmd(RTMP_ADAPTER *a,HW_CTRL_TXD '
 't){assert(a==active&&t.CmdType==HWCMD_TYPE_WIFISYS&&t.InformationBufferLength==sizeof(saved));queued++;if(queue_error)return '
 'queue_error;saved=*(struct WIFI_SYS_CTRL*)t.pInformationBuffer;if(!t.NeedWait){async_pending=1;return '
 '0;}assert(t.wait_time==2000&&!t.pRespBuffer&&!t.RespBufferLength);return dispatch(a,t.CmdId,&saved);}\n'
 'static UINT32 HW_CTRL_BASIC_ENQ(RTMP_ADAPTER *a,int type,int id,int len,void *p){HW_CTRL_TXD '
 't;HW_CTRL_TXD_BASIC(a,type,id,len,p,t);return HwCtrlEnqueueCmd(a,t);}\n'
 '\n'
 'static struct wifi_dev *active_wdev;static EDCA_PARM edca;\n'
 'static int '
 'spin_depth,lifecycle_held,busy,tm_error,reset_calls,tm_calls,cmd_retire_calls,edca_hw,snoop_hw,errors;\n'
 '#define spin_lock_irqsave(l,f) do{(void)(l);(f)=0;if(spin_depth++)errors++;}while(0)\n'
 '#define spin_unlock_irqrestore(l,f) do{(void)(l);(void)(f);if(--spin_depth)errors++;}while(0)\n'
 '#define RTMP_ASIC_INTERRUPT_DISABLE(a) RTMP_CLEAR_FLAG(a,fRTMP_ADAPTER_INTERRUPT_ACTIVE)\n'
 'static int tm_quiesce(RTMP_ADAPTER*a){assert(a==active);tm_calls++;return '
 'tm_error?NDIS_STATUS_FAILURE:NDIS_STATUS_SUCCESS;}\n'
 'static void '
 'AndesDmaQuiesce(RTMP_ADAPTER*a){assert(a==active);cmd_retire_calls++;a->dma_cmd_task_retired=TRUE;}\n'
 'static int RT28XXDMAReset(RTMP_ADAPTER*a){assert(a==active);reset_calls++;return !busy;}\n'
 'static void synchronize_irq(int irq){(void)irq;}\n'
 'static void pci_clear_master(void*p){(void)p;}\n'
 'static void netif_tx_stop_all_queues(struct net_device*n){assert(n);}\n'
 'static void netif_carrier_off(struct net_device*n){assert(n);}\n'
 'static void RtmpDmaLifecycleLock(RTMP_ADAPTER*a){assert(a==active&&!lifecycle_held);lifecycle_held=1;}\n'
 'static void RtmpDmaLifecycleUnlock(RTMP_ADAPTER*a){assert(a==active&&lifecycle_held);lifecycle_held=0;}\n'
 'static struct wifi_dev *wdev_search_by_netdev(RTMP_ADAPTER*a,struct '
 'net_device*n){assert(a==active&&n==a->net_dev);return active_wdev;}\n'
 'static void wdev_if_up_down(RTMP_ADAPTER*a,struct wifi_dev*w,int '
 'up){assert(a==active);w->if_up_down_state=up;}\n'
 'static EDCA_PARM *WcGetWmmByIdx(struct hdev_ctrl*c,int n){(void)c;(void)n;return &edca;}\n'
 'static void AsicSetEdcaParm(RTMP_ADAPTER*a,EDCA_PARM*p,struct '
 'wifi_dev*w){assert(a==active&&p&&w);edca_hw++;if(RtmpDmaStopping(a))blocked_hw++;}\n'
 'static void update_igmpinfo(struct wifi_dev*w,int '
 'on){(void)on;snoop_hw++;if(RtmpDmaStopping(w->sys_handle))blocked_hw++;}\n'
 'static void APStopRekeyTimer(RTMP_ADAPTER*a,struct wifi_dev*w){assert(a==active&&w);}\n'
 'static void MbssKickOutStas(RTMP_ADAPTER*a,int idx,int why){assert(a==active);(void)idx;(void)why;}\n'
 '#define REASON_DISASSOC_INACTIVE 1\n'
 '#define BCN_UPDATE_DISABLE_TX 2\n' '\n/* Core restart API recorder; old owner/event observations stay unchanged. */\n#define REBOOT_DMA_RAETH (1U << 0)\n#define REBOOT_DMA_MT7615 (1U << 1)\nstatic unsigned int restart_failure_reports;\nstatic void reboot_dma_failure_report(unsigned int reasons) { restart_failure_reports |= reasons; }\n')

SUFFIX = ('\n'
 'int main(int argc,char **argv){\n'
 ' const char *name;RTMP_ADAPTER ad={0};struct wifi_dev w={0};struct wifi_dev_ops ops={0};\n'
 ' struct net_device net={&ad,7};OS_COOKIE cookie={0};struct hdev_ctrl hc={&ad};struct radio_dev '
 'radio={&hc,0};struct hdev_obj obj={1,0,0,&radio};\n'
 ' struct WIFI_SYS_CTRL ctrl={0};int result=0;UINT32 id=HWCMD_ID_WIFISYS_CLOSE;\n'
 ' if(argc!=2)return 2;\n'
 ' name=argv[1];CASE_ADMISSION\n'
 ' '
 'active=&ad;active_wdev=&w;ad.net_dev=&net;ad.OS_Cookie=&cookie;ad.dma_lifecycle_pinned=TRUE;ad.dma_irq_registered=TRUE;ad.Flags=fRTMP_ADAPTER_START_UP|fRTMP_ADAPTER_INTERRUPT_ACTIVE;ad.tm_qm_ops=(void*)1;\n'
 ' '
 'w.sys_handle=&ad;w.wdev_type=WDEV_TYPE_AP;w.wdev_idx=0;w.radio=1;w.oper=WLAN_OPER_STATE_VALID;w.if_up_down_state=1;w.bAllowBeaconing=TRUE;w.pHObj=&obj;w.DevInfo.Active=1;w.DevInfo.EnableFeature=DEVINFO_ACTIVE_FEATURE;w.bss_info_argument.bss_state=BSS_READY;w.bss_info_argument.u4BssInfoFeature=1;w.wdev_ops=&ops;\n'
 ' '
 'ops.close=ap_inf_close;ops.linkdown=ap_link_down;ops.disconn_act=wifi_sys_disconn_act;ad.wdev_list[0]=&w;edca.RefCnt=1;edca.bValid=TRUE;\n'
 ' '
 'ad.MacTab.tr_entry[0].wdev=&w;ad.MacTab.tr_entry[0].StaRec.ConnectionState=STATE_CONNECTED;ad.MacTab.tr_entry[0].StaRec.priv=&ad.MacTab.tr_entry[0];\n'
 ' '
 'ad.MacTab.Content[0].wdev=&w;ad.MacTab.Content[0].EntryType=1;ad.MacTab.Content[0].tr_tb_idx=0;\n'
 ' '
 'hw_ctrl_ops_v2_register(&ad.HwCtrl.hwctrl_ops);ad.archOps.archSetDevMac=hook_dev;ad.archOps.archSetBssid=hook_bss;ad.archOps.archSetStaRec=hook_sta;\n'
 ' ctrl.wdev=&w;ctrl.DevInfoCtrl.EnableFeature=DEVINFO_ACTIVE_FEATURE;\n'
 ' if(!strcmp(name,"last-close-cached-idle"))ad.dma_quiesced=TRUE;\n'
 ' '
 'if(!strcmp(name,"partial-inited-close")){WDEV_BSS_STATE(&w)=BSS_INITED;ad.MacTab.tr_entry[0].StaRec.ConnectionState=STATE_DISCONNECT;}\n'
 ' if(!strcmp(name,"last-close-busy"))busy=1;\n'
 ' if(!strcmp(name,"last-close-tm-fail"))tm_error=1;\n'
 ' if(!strcmp(name,"last-close-quarantined")){ad.dma_quarantined=1;ad.dma_stopping=1;}\n'
 ' '
 'if(!strcmp(name,"last-close-queue-reject")||!strcmp(name,"first-abort-queue-reject"))queue_error=NDIS_STATUS_FAILURE;\n'
 ' if(!strcmp(name,"nonlast-close"))ad.vif_num=1;\n'
 ' if(!strncmp(name,"first-abort-fw",14))fail_at=name[strlen(name)-1]-\'0\';\n'
 ' '
 'if(!strncmp(name,"last-close",10)||!strcmp(name,"partial-inited-close")||!strcmp(name,"nonlast-close"))result=virtual_if_down_handler(&net);\n'
 ' else if(!strncmp(name,"first-abort-",12))result=wifi_sys_abort_open(&w);\n'
 ' else {\n'
 '  ad.dma_stopping=TRUE;ad.dma_quiesced=TRUE;\n'
 '  '
 'if(!strcmp(name,"peer-retire")){ad.MacTab.Content[0].EntryState=ENTRY_STATE_SYNC;result=mac_entry_disconn_act(&ad,&ad.MacTab.Content[0]);}\n'
 '  else if(!strncmp(name,"late-",5)){\n'
 '   if(!strcmp(name,"late-open"))result=HW_WIFISYS_OPEN(&ad,&ctrl);\n'
 '   else if(!strcmp(name,"late-linkup"))result=HW_WIFISYS_LINKUP(&ad,&ctrl);\n'
 '   else if(!strcmp(name,"late-peerup"))result=HW_WIFISYS_PEER_LINKUP(&ad,&ctrl);\n'
 '   else if(!strcmp(name,"late-peerupdate"))result=HW_WIFISYS_PEER_UPDATE(&ad,&ctrl);\n'
 '   else result=HW_WIFISYS_RA_UPDATE(&ad,&ctrl);\n'
 '  }else '
 'if(!strcmp(name,"direct-close-not-idle")){ad.dma_quiesced=FALSE;result=HW_WIFISYS_CLOSE(&ad,&ctrl);}\n'
 '  else '
 'if(!strcmp(name,"terminal-quarantined")){ad.dma_quarantined=TRUE;result=HW_WIFISYS_CLOSE(&ad,&ctrl);}\n'
 '  else '
 'if(!strncmp(name,"edca-",5)){if(!strcmp(name,"edca-normal")){ad.dma_stopping=FALSE;ad.dma_quiesced=FALSE;}WcReleaseEdca(&obj);}\n'
 '  else {\n'
 '   if(!strcmp(name,"helper-not-idle"))ad.dma_quiesced=FALSE;\n'
 '   if(!strcmp(name,"helper-active-payload"))ctrl.DevInfoCtrl.Active=TRUE;\n'
 '   '
 'if(!strcmp(name,"helper-bss-payload")){id=HWCMD_ID_WIFISYS_LINKDOWN;ctrl.BssInfoCtrl.bss_state=BSS_READY;}\n'
 '   '
 'if(!strcmp(name,"helper-sta-payload")){id=HWCMD_ID_WIFISYS_PEER_LINKDOWN;ctrl.StaRecCtrl.EnableFeature=1;}\n'
 '   if(!strcmp(name,"helper-unknown"))id=0xffffffffU;\n'
 '   if(!strcmp(name,"helper-not-stopping")){ad.dma_stopping=FALSE;ad.dma_quiesced=FALSE;}\n'
 '   result=wifi_sys_retire(&ad,&ctrl,id);\n'
 '  }\n'
 ' }\n'
 ' if(spin_depth||lifecycle_held)errors++;\n'
 ' '
 'printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\\n",result,ad.dma_stopping,ad.dma_quiesced,ad.dma_quarantined,WDEV_BSS_STATE(&w),w.DevInfo.Active,w.radio,ad.MacTab.Content[0].EntryState,w.if_up_down_state,hw_calls,blocked_hw,queued,releases,edca_hw,snoop_hw,ad.MacTab.tr_entry[0].StaRec.ConnectionState,errors);\n'
 ' return 0;\n'
 '}\n')


def function(text,name):
 token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
 masked=re.sub(token,lambda m:' '*len(m.group()),text)
 pattern=r'^(?:static\s+)?(?:inline\s+)?(?:int|UCHAR|INT|INT32|UINT32|NDIS_STATUS|NTSTATUS|BOOLEAN|VOID|void|MAC_TABLE_ENTRY\s*\*|struct\s+radio_dev\s*\*)\s*'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
 found=list(re.finditer(pattern,masked,re.M))
 if len(found)!=1:raise ValueError('Missing or ambiguous Wsys function: '+name)
 start=found[0].start();opening=masked.index('{',start);depth=0
 for match in re.finditer(token+r'|[{}]',text[opening:]):
  if match.group()=='{':depth+=1
  elif match.group()=='}':
   depth-=1
   if not depth:return text[start:opening+match.end()]
 raise ValueError('Unterminated Wsys function: '+name)


def source_declarations(texts):
 result={}
 for pattern,value in STATUS_DECLARATIONS.items():
  rows=list(re.finditer(pattern,texts['os_header'],re.M))
  if len(rows)!=1 or int(rows[0].group(1),16)!=value:raise ValueError('Actual Wsys status differs: '+pattern)
  result[pattern]={'source':'os_header','sha256':hashlib.sha256(rows[0].group().encode()).hexdigest()}
 for pattern,key in SOURCE_DECLARATIONS.items():
  rows=list(re.finditer(pattern,texts[key],re.M))
  if len(rows)!=1:raise ValueError('Actual Wsys declaration missing: '+pattern)
  result[pattern]={'source':key,'sha256':hashlib.sha256(rows[0].group().encode()).hexdigest()}
 return result


def function_manifest(texts):
 return {n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}


def source_only_function_manifest(texts):
 return {n:hashlib.sha256(function(texts[k],n).encode()).hexdigest()for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}


def generate_source(texts,variant='current'):
 if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current Wsys lifecycle sources required')
 source_declarations(texts);source_only_function_manifest(texts)
 definitions='\n'.join(re.search(p,texts[k],re.M).group()for p,k in SOURCE_DECLARATIONS.items())
 admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
 return PREFIX.replace('SOURCE_DEFINITIONS',definitions)+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)
