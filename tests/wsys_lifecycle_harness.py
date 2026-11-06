"""Source-bound Wsys status and ownership transactions with inert hardware seams.

No real firmware, DMA, IRQ, radio or netdev runs. Queue allocation/retirement is
executed separately by hwcmd_owner_harness; here the composed queue seam copies
the actual WIFI_SYS_CTRL declaration and injects recorded admission outcomes.
"""
import hashlib
import re
SOURCE_PATHS={'handler': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl.c', 'cmd': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl_cmd.c', 'v1': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl_ops_v1.c', 'v2': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hw_ctrl_ops_v2.c', 'sys': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/wifi_sys_info.c', 'wdev': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/wdev.c', 'asic': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/hw_ctrl/cmm_asic.c', 'ap': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap.c', 'apcli': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap_apcli.c', 'wds': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/ap/ap_wds.c', 'entry': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mgmt/mgmt_entrytb.c', 'header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/hw_ctrl.h', 'sys_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/common/wifi_sys_info.h', 'os_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/os/rt_linux.h', 'lifetime': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_main_dev.c', 'cfg': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/cfg80211/cfg80211_inf.c', 'hdev': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev_ctrl.c', 'radio': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev/radio_ctrl.c', 'be': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mgmt/be_basic.c', 'ap_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/ap.h', 'fw': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/mcu/fw_cmd.c', 'mcu_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/mcu/mt_cmd.h', 'core': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mcu/andes_core.c', 'mt_fw': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/hw_ctrl/cmm_asic_mt_fw.c'}
FUNCTION_SOURCES={'hw_ctrl_flow_v1_open': 'v1', 'hw_ctrl_flow_v1_close': 'v1', 'hw_ctrl_flow_v1_link_up': 'v1', 'hw_ctrl_flow_v1_link_down': 'v1', 'hw_ctrl_flow_v1_disconnt_act': 'v1', 'hw_ctrl_flow_v1_connt_act': 'v1', 'hw_ctrl_flow_v1_peer_update': 'v1', 'hw_ctrl_ops_v1_register': 'v1', 'hw_ctrl_flow_v2_open': 'v2', 'hw_ctrl_flow_v2_close': 'v2', 'hw_ctrl_flow_v2_link_up': 'v2', 'hw_ctrl_flow_v2_link_down': 'v2', 'hw_ctrl_flow_v2_disconnt_act': 'v2', 'hw_ctrl_flow_v2_connt_act': 'v2', 'hw_ctrl_flow_v2_peer_update': 'v2', 'hw_ctrl_ops_v2_register': 'v2', 'HwCtrlWifiSysOpen': 'handler', 'HwCtrlWifiSysClose': 'handler', 'HwCtrlWifiSysLinkUp': 'handler', 'HwCtrlWifiSysLinkDown': 'handler', 'HwCtrlWifiSysPeerLinkDown': 'handler', 'HwCtrlWifiSysPeerLinkUp': 'handler', 'HwCtrlWifiSysPeerUpdate': 'handler', 'wifi_sys_queue_work': 'cmd', 'HW_WIFISYS_OPEN': 'cmd', 'HW_WIFISYS_CLOSE': 'cmd', 'HW_WIFISYS_LINKUP': 'cmd', 'HW_WIFISYS_LINKDOWN': 'cmd', 'HW_WIFISYS_PEER_LINKUP': 'cmd', 'HW_WIFISYS_PEER_LINKDOWN': 'cmd', 'HW_WIFISYS_PEER_UPDATE': 'cmd', 'HW_WIFISYS_RA_UPDATE': 'cmd', 'fill_devinfo': 'sys', 'fill_bssinfo_active': 'sys', 'fill_bssinfo_deactive': 'sys', 'fill_bssinfo': 'sys', 'fill_starec': 'sys', 'wifi_sys_update_devinfo': 'sys', 'wifi_sys_update_bssinfo': 'sys', 'wifi_sys_update_starec': 'sys', 'wifi_sys_update_starec_info': 'sys', 'wifi_sys_open': 'sys', 'wifi_sys_close': 'sys', 'wifi_sys_conn_act': 'sys', 'wifi_sys_disconn_act': 'sys', 'wifi_sys_linkup': 'sys', 'wifi_sys_linkdown': 'sys', 'WifiSysUpdateRa': 'sys', 'WifiSysUpdatePortSecur': 'sys', 'AsicDevInfoUpdate': 'asic', 'AsicBssInfoUpdate': 'asic', 'AsicStaRecUpdate': 'asic', 'AsicRaParamStaRecUpdate': 'asic', 'wdev_deinit': 'wdev', 'wdev_do_open': 'wdev', 'wdev_do_close': 'wdev', 'wdev_do_linkup': 'wdev', 'wdev_do_linkdown': 'wdev', 'wdev_do_conn_act': 'wdev', 'wdev_do_disconn_act': 'wdev', 'ap_link_up': 'ap', 'ap_conn_act': 'ap', 'mac_entry_disconn_act': 'entry', 'ApCli_Remove': 'apcli', 'WDS_Remove': 'wds', 'wifi_sys_abort_open': 'sys', 'wdev_attr_update': 'wdev', 'apcli_link_up': 'apcli', 'CmdExtDevInfoUpdateRsp': 'fw', 'CmdExtBssInfoUpdateRsp': 'fw', 'CmdExtStaRecUpdateRsp': 'fw', 'wifi_sys_retire': 'sys'}
BODY_ORDER=('hw_ctrl_flow_v1_open', 'hw_ctrl_flow_v1_close', 'hw_ctrl_flow_v1_link_up', 'hw_ctrl_flow_v1_link_down', 'hw_ctrl_flow_v1_disconnt_act', 'hw_ctrl_flow_v1_connt_act', 'hw_ctrl_flow_v1_peer_update', 'hw_ctrl_ops_v1_register', 'hw_ctrl_flow_v2_open', 'hw_ctrl_flow_v2_close', 'hw_ctrl_flow_v2_link_up', 'hw_ctrl_flow_v2_link_down', 'hw_ctrl_flow_v2_disconnt_act', 'hw_ctrl_flow_v2_connt_act', 'hw_ctrl_flow_v2_peer_update', 'hw_ctrl_ops_v2_register', 'HwCtrlWifiSysOpen', 'HwCtrlWifiSysClose', 'HwCtrlWifiSysLinkUp', 'HwCtrlWifiSysLinkDown', 'HwCtrlWifiSysPeerLinkDown', 'HwCtrlWifiSysPeerLinkUp', 'HwCtrlWifiSysPeerUpdate', 'wifi_sys_queue_work', 'HW_WIFISYS_OPEN', 'HW_WIFISYS_CLOSE', 'HW_WIFISYS_LINKUP', 'HW_WIFISYS_LINKDOWN', 'HW_WIFISYS_PEER_LINKUP', 'HW_WIFISYS_PEER_LINKDOWN', 'HW_WIFISYS_PEER_UPDATE', 'HW_WIFISYS_RA_UPDATE', 'fill_devinfo', 'fill_bssinfo_active', 'fill_bssinfo_deactive', 'fill_bssinfo', 'fill_starec', 'wifi_sys_update_devinfo', 'wifi_sys_update_bssinfo', 'wifi_sys_update_starec', 'wifi_sys_update_starec_info', 'wifi_sys_open', 'wifi_sys_close', 'wifi_sys_conn_act', 'wifi_sys_disconn_act', 'wifi_sys_linkup', 'wifi_sys_linkdown', 'WifiSysUpdateRa', 'WifiSysUpdatePortSecur', 'AsicDevInfoUpdate', 'AsicBssInfoUpdate', 'AsicStaRecUpdate', 'AsicRaParamStaRecUpdate', 'wdev_deinit', 'wdev_do_open', 'wdev_do_close', 'wdev_do_linkup', 'wdev_do_linkdown', 'wdev_do_conn_act', 'wdev_do_disconn_act', 'ap_link_up', 'ap_conn_act', 'mac_entry_disconn_act', 'ApCli_Remove', 'WDS_Remove', 'wifi_sys_abort_open', 'wdev_attr_update', 'apcli_link_up', 'CmdExtDevInfoUpdateRsp', 'CmdExtBssInfoUpdateRsp', 'CmdExtStaRecUpdateRsp', 'wifi_sys_retire')
SOURCE_ONLY_FUNCTION_SOURCES={'MacTableDeleteEntry': 'entry', 'MacTableInsertEntry': 'entry', 'TRTableResetEntry': 'entry', 'TRTableInsertEntry': 'entry', 'TRTableInsertMcastEntry': 'entry', 'RtmpDmaQuarantine': 'lifetime', 'RtmpDmaFinalReleaseCheck': 'lifetime', 'RTMP_CFG80211_VirtualIF_Remove': 'cfg', 'APStartUpForMbss': 'ap', 'APStartUpByBss': 'ap', 'ap_inf_open': 'ap', 'ap_inf_close': 'ap', 'HcAcquireRadioForWdev': 'hdev', 'RcAcquiredBandForObj': 'radio', 'wlan_operate_init': 'be', 'AndesSendCmdMsg': 'core', 'MtAsicSetDevMacByFw': 'mt_fw', 'MtAsicSetBssidByFw': 'mt_fw', 'MtAsicSetStaRecByFw': 'mt_fw', 'CmdExtDevInfoUpdate': 'fw', 'CmdExtBssInfoUpdate': 'fw', 'CmdExtStaRecUpdate': 'fw'}
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
FIELDS=('result','dev_active','oper','bss','entry','hw_calls','commits','releases','quarantined','queued','ra_value')
CASE_NAMES=('v1-open-ok', 'v1-open-fwfail', 'v1-open-missing', 'v1-open-oom', 'v1-open-reject', 'v1-open-irq', 'v1-open-late', 'v1-close-ok', 'v1-close-fwfail', 'v1-close-missing', 'v1-close-oom', 'v1-close-reject', 'v1-close-irq', 'v1-close-late', 'v1-linkup-ok', 'v1-linkup-fwfail', 'v1-linkup-missing', 'v1-linkup-oom', 'v1-linkup-reject', 'v1-linkup-irq', 'v1-linkup-late', 'v1-linkdown-ok', 'v1-linkdown-fwfail', 'v1-linkdown-missing', 'v1-linkdown-oom', 'v1-linkdown-reject', 'v1-linkdown-irq', 'v1-linkdown-late', 'v1-conn-ok', 'v1-conn-fwfail', 'v1-conn-missing', 'v1-conn-oom', 'v1-conn-reject', 'v1-conn-irq', 'v1-conn-late', 'v1-disconn-ok', 'v1-disconn-fwfail', 'v1-disconn-missing', 'v1-disconn-oom', 'v1-disconn-reject', 'v1-disconn-irq', 'v1-disconn-late', 'v1-linkup-second', 'v1-linkdown-second', 'v1-linkup-retry', 'v1-linkdown-retry', 'v1-peer-ok', 'v1-peer-fwfail', 'v1-peer-second', 'v1-peer-missing', 'v1-peer-late', 'v1-ra-ok', 'v1-ra-fwfail', 'v1-ra-oom', 'v1-ra-reject', 'v1-ra-null', 'v2-open-ok', 'v2-open-fwfail', 'v2-open-missing', 'v2-open-oom', 'v2-open-reject', 'v2-open-irq', 'v2-open-late', 'v2-close-ok', 'v2-close-fwfail', 'v2-close-missing', 'v2-close-oom', 'v2-close-reject', 'v2-close-irq', 'v2-close-late', 'v2-linkup-ok', 'v2-linkup-fwfail', 'v2-linkup-missing', 'v2-linkup-oom', 'v2-linkup-reject', 'v2-linkup-irq', 'v2-linkup-late', 'v2-linkdown-ok', 'v2-linkdown-fwfail', 'v2-linkdown-missing', 'v2-linkdown-oom', 'v2-linkdown-reject', 'v2-linkdown-irq', 'v2-linkdown-late', 'v2-conn-ok', 'v2-conn-fwfail', 'v2-conn-missing', 'v2-conn-oom', 'v2-conn-reject', 'v2-conn-irq', 'v2-conn-late', 'v2-disconn-ok', 'v2-disconn-fwfail', 'v2-disconn-missing', 'v2-disconn-oom', 'v2-disconn-reject', 'v2-disconn-irq', 'v2-disconn-late', 'v2-linkup-second', 'v2-linkdown-second', 'v2-linkup-retry', 'v2-linkdown-retry', 'v2-peer-ok', 'v2-peer-fwfail', 'v2-peer-second', 'v2-peer-missing', 'v2-peer-late', 'v2-ra-ok', 'v2-ra-fwfail', 'v2-ra-oom', 'v2-ra-reject', 'v2-ra-null', 'handler-0-missing', 'handler-0-invalid', 'handler-1-missing', 'handler-1-invalid', 'handler-2-missing', 'handler-2-invalid', 'handler-3-missing', 'handler-3-invalid', 'handler-4-missing', 'handler-4-invalid', 'handler-5-missing', 'handler-5-invalid', 'handler-6-missing', 'handler-6-invalid', 'cleanup-deinit-quarantined', 'cleanup-deinit-ok', 'cleanup-apcli-quarantined', 'cleanup-wds-quarantined', 'cleanup-disconn-failure', 'cleanup-disconn-ok', 'cleanup-disconn-null', 'aplink-reject', 'aplink-ok', 'apconn-reject', 'secure-reject', 'secure-ok', 'v1-open-attrfail', 'v1-reserved-close', 'v2-open-attrfail', 'v2-reserved-close', 'rollback-ok', 'rollback-fwfail', 'rollback-second', 'rollback-closefail', 'rollback-oom', 'rollback-reject', 'rollback-late', 'apclilink-ok', 'apclilink-reject', 'apclilink-fwfail', 'apclilink-second', 'apclilink-retry', 'v1-open-fwack', 'v1-linkup-fwack', 'v2-open-fwack', 'v2-linkup-fwack', 'response-dev-ok', 'response-dev-error', 'response-dev-short', 'response-dev-null', 'response-bss-ok', 'response-bss-error', 'response-bss-short', 'response-bss-null', 'response-sta-ok', 'response-sta-error', 'response-sta-short', 'response-sta-null', 'linkup-quarantined-no-radio')
EXPECTED_ROWS={'v1-open-ok': [1, 1, 1, 0, 0, 1, 1, 0, 0, 1, 0], 'v1-open-fwfail': [0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0], 'v1-open-missing': [0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0], 'v1-open-oom': [0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0], 'v1-open-reject': [0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0], 'v1-open-irq': [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0], 'v1-open-late': [0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0], 'v1-close-ok': [1, 0, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'v1-close-fwfail': [0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0], 'v1-close-missing': [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0], 'v1-close-oom': [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0], 'v1-close-reject': [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0], 'v1-close-irq': [0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0], 'v1-close-late': [0, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0], 'v1-linkup-ok': [1, 1, 1, 3, 0, 2, 2, 0, 0, 1, 0], 'v1-linkup-fwfail': [0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0], 'v1-linkup-missing': [0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0], 'v1-linkup-oom': [0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0], 'v1-linkup-reject': [0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0], 'v1-linkup-irq': [0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0], 'v1-linkup-late': [0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 0], 'v1-linkdown-ok': [1, 1, 1, 0, 0, 2, 2, 1, 0, 1, 0], 'v1-linkdown-fwfail': [0, 1, 1, 3, 0, 1, 0, 0, 0, 1, 0], 'v1-linkdown-missing': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-linkdown-oom': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-linkdown-reject': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-linkdown-irq': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'v1-linkdown-late': [0, 1, 1, 3, 0, 1, 0, 0, 1, 1, 0], 'v1-conn-ok': [1, 1, 1, 3, 1, 1, 1, 0, 0, 1, 0], 'v1-conn-fwfail': [0, 1, 1, 3, 0, 1, 0, 0, 0, 1, 0], 'v1-conn-missing': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-conn-oom': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-conn-reject': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-conn-irq': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'v1-conn-late': [0, 1, 1, 3, 0, 1, 0, 0, 1, 1, 0], 'v1-disconn-ok': [1, 1, 1, 3, 0, 1, 1, 0, 0, 1, 0], 'v1-disconn-fwfail': [0, 1, 1, 3, 1, 1, 0, 0, 0, 1, 0], 'v1-disconn-missing': [0, 1, 1, 3, 1, 0, 0, 0, 0, 1, 0], 'v1-disconn-oom': [0, 1, 1, 3, 1, 0, 0, 0, 0, 1, 0], 'v1-disconn-reject': [0, 1, 1, 3, 1, 0, 0, 0, 0, 1, 0], 'v1-disconn-irq': [0, 1, 1, 3, 1, 0, 0, 0, 0, 0, 0], 'v1-disconn-late': [0, 1, 1, 3, 1, 1, 0, 0, 1, 1, 0], 'v1-linkup-second': [0, 1, 1, 1, 0, 2, 0, 0, 0, 1, 0], 'v1-linkdown-second': [0, 1, 1, 3, 0, 2, 1, 0, 0, 1, 0], 'v1-linkup-retry': [1, 1, 1, 3, 0, 3, 2, 0, 0, 2, 0], 'v1-linkdown-retry': [1, 1, 1, 0, 0, 3, 2, 1, 0, 2, 0], 'v1-peer-ok': [0, 1, 1, 3, 0, 3, 1, 0, 0, 1, 0], 'v1-peer-fwfail': [3, 1, 1, 3, 0, 1, 0, 0, 0, 1, 0], 'v1-peer-second': [3, 1, 1, 3, 0, 2, 0, 0, 0, 1, 0], 'v1-peer-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-peer-late': [1, 1, 1, 3, 0, 1, 0, 0, 1, 1, 0], 'v1-ra-ok': [0, 1, 1, 3, 0, 1, 0, 0, 0, 1, 42], 'v1-ra-fwfail': [3, 1, 1, 3, 0, 1, 0, 0, 0, 1, 42], 'v1-ra-oom': [3, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-ra-reject': [1, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v1-ra-null': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'v2-open-ok': [1, 1, 1, 0, 0, 1, 1, 0, 0, 1, 0], 'v2-open-fwfail': [0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0], 'v2-open-missing': [0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0], 'v2-open-oom': [0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0], 'v2-open-reject': [0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0], 'v2-open-irq': [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0], 'v2-open-late': [0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0], 'v2-close-ok': [1, 0, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'v2-close-fwfail': [0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0], 'v2-close-missing': [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0], 'v2-close-oom': [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0], 'v2-close-reject': [0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0], 'v2-close-irq': [0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0], 'v2-close-late': [0, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0], 'v2-linkup-ok': [1, 1, 1, 3, 0, 2, 2, 0, 0, 1, 0], 'v2-linkup-fwfail': [0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0], 'v2-linkup-missing': [0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0], 'v2-linkup-oom': [0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0], 'v2-linkup-reject': [0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0], 'v2-linkup-irq': [0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0], 'v2-linkup-late': [0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 0], 'v2-linkdown-ok': [1, 1, 1, 0, 0, 2, 2, 1, 0, 1, 0], 'v2-linkdown-fwfail': [0, 1, 1, 3, 0, 1, 0, 0, 0, 1, 0], 'v2-linkdown-missing': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-linkdown-oom': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-linkdown-reject': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-linkdown-irq': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'v2-linkdown-late': [0, 1, 1, 3, 0, 1, 0, 0, 1, 1, 0], 'v2-conn-ok': [1, 1, 1, 3, 1, 1, 1, 0, 0, 1, 0], 'v2-conn-fwfail': [0, 1, 1, 3, 0, 1, 0, 0, 0, 1, 0], 'v2-conn-missing': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-conn-oom': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-conn-reject': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-conn-irq': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'v2-conn-late': [0, 1, 1, 3, 0, 1, 0, 0, 1, 1, 0], 'v2-disconn-ok': [1, 1, 1, 3, 0, 1, 1, 0, 0, 1, 0], 'v2-disconn-fwfail': [0, 1, 1, 3, 1, 1, 0, 0, 0, 1, 0], 'v2-disconn-missing': [0, 1, 1, 3, 1, 0, 0, 0, 0, 1, 0], 'v2-disconn-oom': [0, 1, 1, 3, 1, 0, 0, 0, 0, 1, 0], 'v2-disconn-reject': [0, 1, 1, 3, 1, 0, 0, 0, 0, 1, 0], 'v2-disconn-irq': [0, 1, 1, 3, 1, 0, 0, 0, 0, 0, 0], 'v2-disconn-late': [0, 1, 1, 3, 1, 1, 0, 0, 1, 1, 0], 'v2-linkup-second': [0, 1, 1, 1, 0, 2, 0, 0, 0, 1, 0], 'v2-linkdown-second': [0, 1, 1, 3, 0, 2, 1, 0, 0, 1, 0], 'v2-linkup-retry': [1, 1, 1, 3, 0, 3, 2, 0, 0, 2, 0], 'v2-linkdown-retry': [1, 1, 1, 0, 0, 3, 2, 1, 0, 2, 0], 'v2-peer-ok': [0, 1, 1, 3, 0, 3, 1, 0, 0, 1, 0], 'v2-peer-fwfail': [3, 1, 1, 3, 0, 1, 0, 0, 0, 1, 0], 'v2-peer-second': [3, 1, 1, 3, 0, 2, 0, 0, 0, 1, 0], 'v2-peer-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-peer-late': [1, 1, 1, 3, 0, 1, 0, 0, 1, 1, 0], 'v2-ra-ok': [0, 1, 1, 3, 0, 1, 0, 0, 0, 1, 42], 'v2-ra-fwfail': [3, 1, 1, 3, 0, 1, 0, 0, 0, 1, 42], 'v2-ra-oom': [3, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-ra-reject': [1, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'v2-ra-null': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-0-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-0-invalid': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-1-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-1-invalid': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-2-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-2-invalid': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-3-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-3-invalid': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-4-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-4-invalid': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-5-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-5-invalid': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-6-missing': [1, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'handler-6-invalid': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'cleanup-deinit-quarantined': [0, 1, 1, 3, 0, 0, 0, 0, 1, 0, 0], 'cleanup-deinit-ok': [1, 1, 1, 3, 0, 0, 0, 0, 0, 0, 4], 'cleanup-apcli-quarantined': [1, 1, 1, 3, 0, 0, 0, 0, 1, 0, 0], 'cleanup-wds-quarantined': [1, 1, 1, 3, 0, 0, 0, 0, 1, 0, 0], 'cleanup-disconn-failure': [0, 1, 1, 3, 1, 0, 0, 0, 0, 1, 0], 'cleanup-disconn-ok': [1, 1, 1, 3, 0, 1, 1, 0, 0, 1, 0], 'cleanup-disconn-null': [1, 1, 1, 3, 1, 0, 0, 0, 0, 0, 0], 'aplink-reject': [0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0], 'aplink-ok': [1, 1, 1, 3, 0, 2, 2, 0, 0, 1, 2], 'apconn-reject': [0, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'secure-reject': [1, 1, 1, 3, 0, 0, 0, 0, 0, 1, 0], 'secure-ok': [0, 1, 1, 3, 0, 1, 1, 0, 0, 1, 0], 'v1-open-attrfail': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'v1-reserved-close': [1, 0, 0, 0, 0, 3, 2, 2, 0, 3, 0], 'v2-open-attrfail': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'v2-reserved-close': [1, 0, 0, 0, 0, 3, 2, 2, 0, 3, 0], 'rollback-ok': [1, 0, 0, 0, 0, 3, 3, 2, 0, 2, 0], 'rollback-fwfail': [0, 1, 1, 3, 0, 1, 0, 0, 1, 1, 0], 'rollback-second': [0, 1, 1, 3, 0, 2, 1, 0, 1, 1, 0], 'rollback-closefail': [0, 1, 1, 0, 0, 3, 2, 1, 1, 2, 0], 'rollback-oom': [0, 1, 1, 3, 0, 0, 0, 0, 1, 1, 0], 'rollback-reject': [0, 1, 1, 3, 0, 0, 0, 0, 1, 1, 0], 'rollback-late': [0, 1, 1, 3, 0, 1, 0, 0, 1, 1, 0], 'apclilink-ok': [1, 1, 1, 3, 0, 2, 2, 0, 0, 1, 2], 'apclilink-reject': [0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0], 'apclilink-fwfail': [0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0], 'apclilink-second': [0, 1, 1, 1, 0, 2, 0, 0, 0, 1, 0], 'apclilink-retry': [1, 1, 1, 3, 0, 3, 2, 0, 0, 2, 2], 'v1-open-fwack': [0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0], 'v1-linkup-fwack': [0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0], 'v2-open-fwack': [0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0], 'v2-linkup-fwack': [0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0], 'response-dev-ok': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-dev-error': [5, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-dev-short': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-dev-null': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-bss-ok': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-bss-error': [5, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-bss-short': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-bss-null': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-sta-ok': [0, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-sta-error': [5, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-sta-short': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'response-sta-null': [2, 1, 1, 3, 0, 0, 0, 0, 0, 0, 0], 'linkup-quarantined-no-radio': [0, 1, 1, 3, 0, 0, 0, 0, 1, 0, 0]}

PREFIX=r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CONFIG_AP_SUPPORT
#define RACTRL_FW_OFFLOAD_SUPPORT
#define MT_MAC
#define GNU_PACKED __attribute__((packed))
#define le2cpu32(v) (v)
#define le2cpu16(v) (v)
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_INVALID_DATA 2
#define NDIS_STATUS_RESOURCES 3
#define WLAN_OPER_STATE_INVALID 0
#define WLAN_OPER_STATE_VALID 1
#define BSS_INIT 0
#define BSS_INITED 1
#define BSS_ACTIVE 2
#define BSS_READY 3
#define ENTRY_STATE_NONE 0
#define ENTRY_STATE_SYNC 1
#define STATE_DISCONNECT 0
#define STATE_CONNECTED 1
#define STATE_PORT_SECURE 2
#define WDEV_TYPE_AP 1
#define WDEV_TYPE_WDS 2
#define WDEV_TYPE_APCLI 3
#define WDEV_TYPE_GO 4
#define OPMODE_AP 1
#define HC_STATUS_OK 0
#define MSDU_FORBID_CONNECTION_NOT_READY 1
#define WPA_802_1X_PORT_SECURED 2
#define UMH_WAIT_PROC 1
#define MSDU_FORBID_CLEAR(w,f) ((void)(w),(void)(f))
#define COPY_MAC_ADDR(d,a) memmove((d),(a),6)
#define RTMP_OS_NETDEV_GET_PHYADDR(d) dev_addr
#define DEVINFO_ACTIVE_FEATURE 1
#define STA_REC_BASIC_STA_RECORD_FEATURE 1
#define STA_REC_INSTALL_KEY_FEATURE 2
#define STA_REC_RA_COMMON_INFO_FEATURE 4
#define STA_REC_RA_FEATURE 8
#define STA_REC_RA_UPDATE_FEATURE 16
#define CONNECTION_INFRA_BC 1
#define HIF_MT 1
#define MAC_ADDR_LEN 6
#define MAX_APCLI_NUM 2
#define MAX_WDS_ENTRY 2
#define WCID_ALL 255
#define TXOP_0 0
#define TXOP_80 80
#define AC_BE 0
#define PRIO_DEFAULT 0
#define BCN_UPDATE_INIT 0
#define BCN_UPDATE_IE_CHG 1
#define fOP_AP_STATUS_MEDIA_STATE_CONNECTED 1
#define WPA_802_1X_PORT_NOT_SECURED 0
#define WDEV_BSS_STATE(w) ((w)->bss_info_argument.bss_state)
#define WDEV_WITH_BCN_ABILITY(w) 1
#define MTWF_LOG(...) ((void)0)
#define PRINT_MAC(a) 0
#define ASSERT(x) assert(x)
#define IS_HIF_TYPE(a,t) 1
#define VALID_UCAST_ENTRY_WCID(a,w) ((w)<8)
#define GET_MAX_UCAST_NUM(a) 8
#define IS_ENTRY_NONE(e) (!(e)->EntryType)
#define IS_ENTRY_REPEATER(e) ((e)->EntryType==3)
#define IS_ENTRY_CLIENT(e) ((e)->EntryType==1)
#define OPSTATUS_SET_FLAG_WDEV(w,f) ((w)->media=1)
#define IF_DEV_CONFIG_OPMODE_ON_AP(a) if(1)
#define RESET_FLAG_CONN_IN_PROG(a,c) ((c)=0)
#define os_zero_mem(p,n) memset((p),0,(n))
#define os_move_mem(p,s,n) memmove((p),(s),(n))
#define NdisMoveMemory(p,s,n) memmove((p),(s),(n))
typedef void VOID;typedef unsigned char UCHAR,UINT8;typedef uint16_t UINT16;typedef uint32_t UINT32;typedef int INT,INT32,NTSTATUS,NDIS_STATUS,BOOLEAN;typedef unsigned int UINT;
struct _RTMP_ADAPTER;struct wifi_dev;struct WIFI_SYS_CTRL;struct _STA_REC_CFG_T;struct _STA_REC_CFG_T;
typedef NTSTATUS(*HwCmdCb)(struct _RTMP_ADAPTER*,VOID*);
typedef struct {int list;} DL_LIST;
typedef struct {UINT32 u4Field;UCHAR padding[60];} CMD_STAREC_AUTO_RATE_UPDATE_T,*P_CMD_STAREC_AUTO_RATE_UPDATE_T;
typedef struct {int dummy;} ASIC_SEC_INFO;
typedef struct _DEV_INFO_CTRL_T {UCHAR Active,OwnMacIdx,OwnMacAddr[6],BandIdx;UINT32 EnableFeature;DL_LIST list;} DEV_INFO_CTRL_T;
typedef struct _STA_REC_CTRL_T {UINT8 BssIndex,WlanIdx,ConnectionState;UINT32 ConnectionType,EnableFeature;BOOLEAN IsNewSTARec;ASIC_SEC_INFO asic_sec_info;VOID *priv;DL_LIST list;} STA_REC_CTRL_T;
typedef struct _BSS_INFO_ARGUMENT_T {int bss_state;UINT8 ucBssIndex,ucBcMcWlanIdx,ucPeerWlanIdx;UINT32 u4ConnectionType,u4BssInfoFeature;UINT8 Bssid[6];DL_LIST list;} BSS_INFO_ARGUMENT_T;
SOURCE_DEFINITIONS
typedef struct _MAC_TABLE_ENTRY {struct wifi_dev *wdev;int EntryState,EntryType,tr_tb_idx;UINT8 wcid,Addr[6];UINT32 ConnectionType;struct {UINT32 AKMMap,PairwiseCipher;} SecConfig;} MAC_TABLE_ENTRY,*PMAC_TABLE_ENTRY;
typedef struct _STA_TR_ENTRY {STA_REC_CTRL_T StaRec;struct wifi_dev *wdev;UINT8 Addr[6],OmacIdx;int PortSecured;} STA_TR_ENTRY;
struct wifi_dev_ops {INT(*open)(struct wifi_dev*);INT(*close)(struct wifi_dev*);INT(*linkup)(struct wifi_dev*,struct _MAC_TABLE_ENTRY*);INT(*linkdown)(struct wifi_dev*);INT(*conn_act)(struct wifi_dev*,struct _MAC_TABLE_ENTRY*);INT(*disconn_act)(struct wifi_dev*,struct _MAC_TABLE_ENTRY*);};
struct wifi_dev {VOID *sys_handle,*if_dev;DEV_INFO_CTRL_T DevInfo;BSS_INFO_ARGUMENT_T bss_info_argument;struct wifi_dev_ops *wdev_ops;int wdev_type,wdev_idx,tr_tb_idx,oper,radio,media,protection,func_idx,PortSecured;UINT8 OmacIdx,if_addr[6],bssid[6];};
struct _APCLI_STRUCT {struct wifi_dev wdev;int ApCliInit,Valid;};
typedef struct _RTMP_ADAPTER {struct {HWCTRL_OP hwctrl_ops;} HwCtrl;struct {int bEnableTxBurst,bRdg;} CommonCfg;struct {STA_TR_ENTRY tr_entry[8];MAC_TABLE_ENTRY Content[8];} MacTab;struct {struct _APCLI_STRUCT ApCliTab[2];} ApCfg;struct {struct {struct wifi_dev wdev;} WdsEntry[2];int flg_wds_init;} WdsTab;int quarantined,flg_apcli_init,ConInPrgress;struct {INT32(*archSetDevMac)(struct _RTMP_ADAPTER*,UINT8,UINT8*,UINT8,UINT8,UINT32);INT32(*archSetBssid)(struct _RTMP_ADAPTER*,BSS_INFO_ARGUMENT_T);INT32(*archSetStaRec)(struct _RTMP_ADAPTER*,struct _STA_REC_CFG_T);} archOps;} RTMP_ADAPTER,*PRTMP_ADAPTER;
typedef struct _STA_REC_CFG_T {int MuarIdx,ConnectionState,ConnectionType;UINT32 u4EnableFeature;UINT8 ucBssIndex,ucWlanIdx;MAC_TABLE_ENTRY *pEntry;BOOLEAN IsNewSTARec;ASIC_SEC_INFO asic_sec_info;P_CMD_STAREC_AUTO_RATE_UPDATE_T pRaParam;} STA_REC_CFG_T;
typedef struct {struct {int OperaionMode;} AddHtInfo2;} ADD_HT_INFO_IE;
typedef struct _HwCmdQElmt {void *buffer;UINT32 bufferlength;} HwCmdQElmt;
static int hw_calls,commits,releases,queued,fail_at,late_at,queue_error,interrupt_context,ra_value,async_pending;
static int firmware_ack_error;
struct cmd_msg {UINT32 cmd_return_status;};
static VOID CmdExtDevInfoUpdateRsp(struct cmd_msg*,char*,UINT16);
static VOID CmdExtBssInfoUpdateRsp(struct cmd_msg*,char*,UINT16);
static VOID CmdExtStaRecUpdateRsp(struct cmd_msg*,char*,UINT16);
static int notifies,starec_exists,rekey,cleaned,detached,freed,attr_error,usermode_calls;
static UCHAR dev_addr[6];
static RTMP_ADAPTER *active;static struct WIFI_SYS_CTRL saved;
static int RtmpDmaQuarantined(RTMP_ADAPTER *a){return a->quarantined;}
/* Old171 observations run before terminal stop; composed retirement is separate. */
static int RtmpDmaStopping(RTMP_ADAPTER *a){return a->quarantined;}
static int RtmpDmaResourcesMayRelease(RTMP_ADAPTER *a){(void)a;return 0;}
INT wifi_sys_retire(struct _RTMP_ADAPTER *ad, struct WIFI_SYS_CTRL *wsys, UINT32 id);
static int in_interrupt(void){return interrupt_context;}
static void dump_stack(void){}
static int wlan_operate_get_state(struct wifi_dev *w){return w->oper;}
static void wlan_operate_set_state(struct wifi_dev *w,int n){w->oper=n;}
static INT32 wdev_attr_update(RTMP_ADAPTER *pAd,struct wifi_dev *wdev);
static INT32 HcAcquireRadioForWdev(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active);if(attr_error)return 1;w->radio=1;return HC_STATUS_OK;}
static void AsicSetMbssWdevIfAddr(RTMP_ADAPTER *a,int i,UCHAR *addr,int mode){assert(a==active&&addr);(void)i;(void)mode;}
static void RtmpDmaQuarantine(RTMP_ADAPTER *a){a->quarantined=1;}
static int call_usermodehelper(char *p,char **argv,char **envp,int mode){assert(p&&argv&&envp&&mode==UMH_WAIT_PROC);usermode_calls++;return 0;}
static void HcReleaseRadioForWdev(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active);w->radio=0;releases++;}
static int HcGetBandByWdev(struct wifi_dev *w){assert(w);return 0;}
static int HcIsRadioAcq(struct wifi_dev *w){return w->radio;}
static void UpdateDot11hForWdev(RTMP_ADAPTER *a,struct wifi_dev *w,int on){assert(a==active&&w&&!on);}
static void BssInfoArgumentLink(RTMP_ADAPTER *a,struct wifi_dev *w,BSS_INFO_ARGUMENT_T *b){assert(a==active&&w);b->bss_state=BSS_INITED;b->ucBssIndex=2;b->ucBcMcWlanIdx=0;b->u4ConnectionType=1;}
static void BssInfoArgumentUnLink(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active);releases++;memset(&w->bss_info_argument,0,sizeof(w->bss_info_argument));}
static void add_devinfo(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);commits++;}
static void del_devinfo(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);commits++;}
static void add_bssinfo(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);commits++;}
static void del_bssinfo(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);commits++;}
static void add_starec(RTMP_ADAPTER *a,STA_TR_ENTRY *t){assert(a==active&&t);commits++;}
static void del_starec(RTMP_ADAPTER *a,STA_TR_ENTRY *t){assert(a==active&&t);commits++;}
enum {WSYS_NOTIFY_OPEN,WSYS_NOTIFY_CLOSE,WSYS_NOTIFY_CONNT_ACT,WSYS_NOTIFY_DISCONNT_ACT,WSYS_NOTIFY_LINKUP,WSYS_NOTIFY_LINKDOWN,WSYS_NOTIFY_STA_UPDATE};
static int call_wsys_notifieriers(int n,struct wifi_dev *w,void *p){(void)p;assert(w);notifies++;if(n==WSYS_NOTIFY_STA_UPDATE)commits++;return 0;}
static void HcSetEdca(struct wifi_dev *w){assert(w);}
static void hw_set_tx_burst(RTMP_ADAPTER *a,struct wifi_dev *w,int ac,int pr,int lev,int on){assert(a==active&&w);(void)ac;(void)pr;(void)lev;(void)on;}
static void UpdateBeaconHandler(RTMP_ADAPTER *a,struct wifi_dev *w,int n){assert(a==active&&w);(void)n;}
static void AsicUpdateRxWCIDTable(RTMP_ADAPTER *a,int i,UINT8 *addr,int add,int reset){assert(a==active&&addr);(void)i;(void)add;(void)reset;}
static void AsicAddRemoveKeyTab(RTMP_ADAPTER *a,ASIC_SEC_INFO *i){assert(a==active&&i);}
static void AsicDelWcidTab(RTMP_ADAPTER *a,int i){assert(a==active);(void)i;}
static ADD_HT_INFO_IE *wlan_operate_get_addht(struct wifi_dev *w){static ADD_HT_INFO_IE info;assert(w);return &info;}
static void AsicUpdateProtect(RTMP_ADAPTER *a){assert(a==active);}
static int get_starec_by_wcid(RTMP_ADAPTER *a,int i){assert(a==active);(void)i;return starec_exists;}
static void AsicNotSupportFunc(RTMP_ADAPTER *a,const char *n){assert(a==active&&n);}
static void starec_feature_decision(struct wifi_dev *w,UINT32 t,MAC_TABLE_ENTRY *e,UINT32 *f){assert(w);(void)t;(void)e;*f|=STA_REC_BASIC_STA_RECORD_FEATURE;}
static void starec_security_decision(struct wifi_dev *w,MAC_TABLE_ENTRY *e,UCHAR *s){assert(w);(void)e;*s=STATE_CONNECTED;}
static void starec_security_set(struct wifi_dev *w,MAC_TABLE_ENTRY *e,STA_REC_CTRL_T *s){assert(w&&e&&s);}
static void bssinfo_feature_decision(struct wifi_dev *w,UINT32 t,UCHAR i,UINT32 *f){assert(w);(void)t;(void)i;*f|=1;}
static void APKeyTableInit(RTMP_ADAPTER *a,struct wifi_dev *w,STA_REC_CTRL_T *s){assert(a==active&&w&&s);}
static void CheckBMCPortSecured(RTMP_ADAPTER *a,MAC_TABLE_ENTRY *e,int b){assert(a==active&&e);(void)b;}
static void APStartRekeyTimer(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);rekey++;}
static void deinit_vie_ctrl(struct wifi_dev *w){assert(w);cleaned++;}
static void wlan_operate_exit(struct wifi_dev *w){assert(w);cleaned++;}
static void hc_obj_exit(struct wifi_dev *w){assert(w);cleaned++;}
static int wdev_idx_unreg(RTMP_ADAPTER *a,struct wifi_dev *w){assert(a==active&&w);cleaned++;return TRUE;}
static void RtmpOSNetDevProtect(int n){(void)n;}
static void RtmpOSNetDevDetach(void *d){assert(d);detached++;}
static void RtmpOSNetDevFree(void *d){assert(d);freed++;}
static void ba_session_tear_down_all(RTMP_ADAPTER *a,int i){assert(a==active);(void)i;}
static int hook_result(void){hw_calls++;if(hw_calls==late_at)active->quarantined=1;return hw_calls==fail_at?NDIS_STATUS_RESOURCES:NDIS_STATUS_SUCCESS;}
static INT32 hook_dev(RTMP_ADAPTER *a,UINT8 i,UINT8 *m,UINT8 b,UINT8 on,UINT32 f){assert(a==active&&m);(void)i;(void)b;(void)on;(void)f;int r=hook_result();struct cmd_msg msg={1};EVENT_DEVINFO_UPDATE_T event={0};if(r)return r;event.u4Status=firmware_ack_error;CmdExtDevInfoUpdateRsp(&msg,(char*)&event,sizeof(event));return msg.cmd_return_status;}
static INT32 hook_bss(RTMP_ADAPTER *a,BSS_INFO_ARGUMENT_T b){assert(a==active);(void)b;int r=hook_result();struct cmd_msg msg={1};EVENT_BSSINFO_UPDATE_T event={0};if(r)return r;event.u4Status=firmware_ack_error;CmdExtBssInfoUpdateRsp(&msg,(char*)&event,sizeof(event));return msg.cmd_return_status;}
static INT32 hook_sta(RTMP_ADAPTER *a,STA_REC_CFG_T s){assert(a==active);if(s.pRaParam)ra_value=s.pRaParam->u4Field;int r=hook_result();struct cmd_msg msg={1};EVENT_STAREC_UPDATE_T event={0};if(r)return r;event.u4Status=firmware_ack_error;CmdExtStaRecUpdateRsp(&msg,(char*)&event,sizeof(event));return msg.cmd_return_status;}
static NTSTATUS hw_ctrl_flow_v1_open(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v1_close(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v1_link_up(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v1_link_down(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v1_disconnt_act(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v1_connt_act(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v1_peer_update(struct WIFI_SYS_CTRL *wsys);
VOID hw_ctrl_ops_v1_register(struct _HWCTRL_OP *hwctrl_ops);
static NTSTATUS hw_ctrl_flow_v2_open(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v2_close(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v2_link_up(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v2_link_down(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v2_disconnt_act(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v2_connt_act(struct WIFI_SYS_CTRL *wsys);
static NTSTATUS hw_ctrl_flow_v2_peer_update(struct WIFI_SYS_CTRL *wsys);
VOID hw_ctrl_ops_v2_register(struct _HWCTRL_OP *hwctrl_ops);
static NTSTATUS HwCtrlWifiSysOpen(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);
static NTSTATUS HwCtrlWifiSysClose(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);
static NTSTATUS HwCtrlWifiSysLinkUp(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);
static NTSTATUS HwCtrlWifiSysLinkDown(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);
static NTSTATUS HwCtrlWifiSysPeerLinkDown(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);
static NTSTATUS HwCtrlWifiSysPeerLinkUp(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);
static NTSTATUS HwCtrlWifiSysPeerUpdate(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt);
static NDIS_STATUS wifi_sys_queue_work(struct _RTMP_ADAPTER *ad, UINT32 id, struct WIFI_SYS_CTRL *wsys);
NDIS_STATUS HW_WIFISYS_OPEN(
	RTMP_ADAPTER *pAd,
	struct WIFI_SYS_CTRL *wsys);
NDIS_STATUS HW_WIFISYS_CLOSE(
	RTMP_ADAPTER *pAd,
	struct WIFI_SYS_CTRL *wsys);
NDIS_STATUS HW_WIFISYS_LINKUP(
	RTMP_ADAPTER *pAd,
	struct WIFI_SYS_CTRL *wsys);
NDIS_STATUS HW_WIFISYS_LINKDOWN(
	RTMP_ADAPTER *pAd,
	struct WIFI_SYS_CTRL *wsys);
NDIS_STATUS HW_WIFISYS_PEER_LINKUP(
	RTMP_ADAPTER *pAd,
	struct WIFI_SYS_CTRL *wsys);
NDIS_STATUS HW_WIFISYS_PEER_LINKDOWN(
	RTMP_ADAPTER *pAd,
	struct WIFI_SYS_CTRL *wsys);
NDIS_STATUS HW_WIFISYS_PEER_UPDATE(
	RTMP_ADAPTER *pAd,
	struct WIFI_SYS_CTRL *wsys);
NDIS_STATUS HW_WIFISYS_RA_UPDATE(
	RTMP_ADAPTER *pAd,
	struct WIFI_SYS_CTRL *wsys);
static VOID fill_devinfo(
	struct _RTMP_ADAPTER *pAd,
	struct wifi_dev *wdev,
	BOOLEAN act,
	struct _DEV_INFO_CTRL_T *devinfo);
static inline VOID fill_bssinfo_active(
	struct _RTMP_ADAPTER *ad,
	struct wifi_dev *wdev,
	struct _BSS_INFO_ARGUMENT_T *bssinfo);
static inline VOID fill_bssinfo_deactive(
	struct _RTMP_ADAPTER *ad,
	struct wifi_dev *wdev,
	struct _BSS_INFO_ARGUMENT_T *bssinfo);
static VOID fill_bssinfo(
	struct _RTMP_ADAPTER *ad,
	struct wifi_dev *wdev,
	BOOLEAN act,
	struct _BSS_INFO_ARGUMENT_T *bssinfo);
static VOID fill_starec(
	struct _RTMP_ADAPTER *ad,
	struct _STA_TR_ENTRY *tr_entry,
	struct _STA_REC_CTRL_T *starec);
INT wifi_sys_update_devinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev, struct _DEV_INFO_CTRL_T *new);
INT wifi_sys_update_bssinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev, struct _BSS_INFO_ARGUMENT_T *new);
INT wifi_sys_update_starec(struct _RTMP_ADAPTER *ad, struct _STA_REC_CTRL_T *new);
INT wifi_sys_update_starec_info(struct _RTMP_ADAPTER *ad, struct _STA_REC_CTRL_T *new);
INT wifi_sys_open(struct wifi_dev *wdev);
INT wifi_sys_close(struct wifi_dev *wdev);
INT wifi_sys_conn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
INT wifi_sys_disconn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
INT wifi_sys_linkup(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
INT wifi_sys_linkdown(struct wifi_dev *wdev);
VOID WifiSysUpdateRa(RTMP_ADAPTER *pAd,
					 MAC_TABLE_ENTRY *pEntry,
					 P_CMD_STAREC_AUTO_RATE_UPDATE_T prParam
					);
VOID WifiSysUpdatePortSecur(RTMP_ADAPTER *pAd, MAC_TABLE_ENTRY *pEntry, ASIC_SEC_INFO *asic_sec_info);
INT32 AsicDevInfoUpdate(
	RTMP_ADAPTER *pAd,
	UINT8 OwnMacIdx,
	UINT8 *OwnMacAddr,
	UINT8 BandIdx,
	UINT8 Active,
	UINT32 EnableFeature);
INT32 AsicBssInfoUpdate(
	RTMP_ADAPTER *pAd,
	BSS_INFO_ARGUMENT_T bss_info_argument);
INT32 AsicStaRecUpdate(
	RTMP_ADAPTER *pAd,
	STA_REC_CTRL_T *sta_rec_ctrl);
INT32 AsicRaParamStaRecUpdate(
	RTMP_ADAPTER *pAd,
	UINT8 WlanIdx,
	P_CMD_STAREC_AUTO_RATE_UPDATE_T prParam,
	UINT32 EnableFeature);
INT32 wdev_deinit(RTMP_ADAPTER *pAd, struct wifi_dev *wdev);
INT wdev_do_open(struct wifi_dev *wdev);
INT wdev_do_close(struct wifi_dev *wdev);
INT wdev_do_linkup(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
INT wdev_do_linkdown(struct wifi_dev *wdev);
INT wdev_do_conn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
INT wdev_do_disconn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
INT ap_link_up(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
INT ap_conn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
static BOOLEAN mac_entry_disconn_act(struct _RTMP_ADAPTER *pAd, struct _MAC_TABLE_ENTRY *pEntry);
VOID ApCli_Remove(RTMP_ADAPTER *pAd);
VOID WDS_Remove(RTMP_ADAPTER *pAd);
INT wifi_sys_abort_open(struct wifi_dev *wdev);
INT apcli_link_up(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry);
static NTSTATUS dispatch(RTMP_ADAPTER *a,UINT32 id,struct WIFI_SYS_CTRL *w){HwCmdQElmt c={w,sizeof(*w)};switch(id){case HWCMD_ID_WIFISYS_OPEN:return HwCtrlWifiSysOpen(a,&c);case HWCMD_ID_WIFISYS_CLOSE:return HwCtrlWifiSysClose(a,&c);case HWCMD_ID_WIFISYS_LINKUP:return HwCtrlWifiSysLinkUp(a,&c);case HWCMD_ID_WIFISYS_LINKDOWN:return HwCtrlWifiSysLinkDown(a,&c);case HWCMD_ID_WIFISYS_PEER_LINKUP:return HwCtrlWifiSysPeerLinkUp(a,&c);case HWCMD_ID_WIFISYS_PEER_LINKDOWN:return HwCtrlWifiSysPeerLinkDown(a,&c);case HWCMD_ID_WIFISYS_PEER_UPDATE:return HwCtrlWifiSysPeerUpdate(a,&c);default:abort();}}
static NDIS_STATUS HwCtrlEnqueueCmd(RTMP_ADAPTER *a,HW_CTRL_TXD t){assert(a==active&&t.CmdType==HWCMD_TYPE_WIFISYS&&t.InformationBufferLength==sizeof(saved));queued++;if(queue_error)return queue_error;saved=*(struct WIFI_SYS_CTRL*)t.pInformationBuffer;if(!t.NeedWait){async_pending=1;return 0;}assert(t.wait_time==2000&&!t.pRespBuffer&&!t.RespBufferLength);return dispatch(a,t.CmdId,&saved);}
static UINT32 HW_CTRL_BASIC_ENQ(RTMP_ADAPTER *a,int type,int id,int len,void *p){HW_CTRL_TXD t;HW_CTRL_TXD_BASIC(a,type,id,len,p,t);return HwCtrlEnqueueCmd(a,t);}
'''
SUFFIX=r'''
int main(int argc,char **argv){const char *name,*op;RTMP_ADAPTER ad;struct wifi_dev w;struct wifi_dev_ops ops;MAC_TABLE_ENTRY *e;struct WIFI_SYS_CTRL ctrl;HwCmdQElmt direct;CMD_STAREC_AUTO_RATE_UPDATE_T param;int result=0;assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&ad,0,sizeof(ad));memset(&w,0,sizeof(w));memset(&ops,0,sizeof(ops));memset(&ctrl,0,sizeof(ctrl));memset(&param,0,sizeof(param));active=&ad;e=&ad.MacTab.Content[1];w.sys_handle=&ad;w.wdev_type=WDEV_TYPE_AP;w.wdev_ops=&ops;w.radio=1;w.DevInfo.Active=1;w.oper=1;w.bss_info_argument.bss_state=BSS_READY;w.bss_info_argument.ucBssIndex=2;w.bss_info_argument.ucBcMcWlanIdx=0;w.bss_info_argument.u4BssInfoFeature=1;e->wdev=&w;e->EntryType=1;e->wcid=1;e->tr_tb_idx=1;e->ConnectionType=1;ad.MacTab.tr_entry[0].wdev=&w;ad.MacTab.tr_entry[1].wdev=&w;ad.MacTab.tr_entry[0].StaRec.ConnectionState=STATE_CONNECTED;ad.MacTab.tr_entry[1].StaRec.ConnectionState=STATE_CONNECTED;ad.ConInPrgress=1;
 ad.archOps.archSetDevMac=hook_dev;ad.archOps.archSetBssid=hook_bss;ad.archOps.archSetStaRec=hook_sta;ops.open=wifi_sys_open;ops.close=wifi_sys_close;ops.linkup=wifi_sys_linkup;ops.linkdown=wifi_sys_linkdown;ops.conn_act=wifi_sys_conn_act;ops.disconn_act=wifi_sys_disconn_act;
 if(strstr(name,"v2-"))hw_ctrl_ops_v2_register(&ad.HwCtrl.hwctrl_ops);else hw_ctrl_ops_v1_register(&ad.HwCtrl.hwctrl_ops);
 if(strstr(name,"-fwack"))firmware_ack_error=5;
 if(strstr(name,"-attrfail"))attr_error=1;
 if(strstr(name,"-oom"))queue_error=3;
 if(strstr(name,"-reject"))queue_error=1;
 if(strstr(name,"-irq"))interrupt_context=1;
 if(strstr(name,"-fwfail")||strstr(name,"-retry"))fail_at=1;
 if(strstr(name,"-second"))fail_at=2;
 if(strstr(name,"-closefail"))fail_at=3;
 if(strstr(name,"-late"))late_at=1;
 if(strstr(name,"-missing")){ad.archOps.archSetDevMac=NULL;ad.archOps.archSetBssid=NULL;ad.archOps.archSetStaRec=NULL;}
 op=name+(name[0]=='v'?3:0);
 if(!strcmp(op,"linkup-quarantined-no-radio")){ad.quarantined=1;w.radio=0;result=wifi_sys_linkup(&w,NULL);}
 else if(!strncmp(op,"open-",5)){w.DevInfo.Active=0;w.oper=0;w.bss_info_argument.bss_state=0;result=wdev_do_open(&w);}
 else if(!strncmp(op,"reserved-close",14)){w.bss_info_argument.bss_state=0;ad.MacTab.tr_entry[0].StaRec.ConnectionState=0;fail_at=1;assert(!wifi_sys_linkup(&w,NULL)&&WDEV_BSS_STATE(&w)==BSS_INITED);fail_at=0;result=wifi_sys_abort_open(&w);}
 else if(!strncmp(op,"rollback-",9))result=wifi_sys_abort_open(&w);
 else if(!strncmp(op,"close-",6)){w.bss_info_argument.bss_state=0;result=wdev_do_close(&w);}
 else if(!strncmp(op,"linkup-",7)){w.bss_info_argument.bss_state=0;ad.MacTab.tr_entry[0].StaRec.ConnectionState=0;result=wifi_sys_linkup(&w,NULL);if(strstr(name,"-retry")){assert(!result&&w.bss_info_argument.bss_state==BSS_INITED);fail_at=0;result=wifi_sys_linkup(&w,NULL);}}
 else if(!strncmp(op,"linkdown-",9)){result=wdev_do_linkdown(&w);if(strstr(name,"-retry")){assert(!result&&w.bss_info_argument.bss_state==BSS_READY);fail_at=0;result=wdev_do_linkdown(&w);}}
 else if(!strncmp(op,"conn-",5))result=wifi_sys_conn_act(&w,e);
 else if(!strncmp(op,"disconn-",8)){e->EntryState=ENTRY_STATE_SYNC;result=wdev_do_disconn_act(&w,e);}
 else if(!strncmp(op,"peer-",5)){ctrl.wdev=&w;ctrl.StaRecCtrl.priv=&ad.MacTab.tr_entry[1];ctrl.StaRecCtrl.WlanIdx=1;ctrl.StaRecCtrl.ConnectionState=STATE_PORT_SECURE;ctrl.StaRecCtrl.EnableFeature=STA_REC_RA_COMMON_INFO_FEATURE|STA_REC_RA_FEATURE|STA_REC_BASIC_STA_RECORD_FEATURE;result=HW_WIFISYS_PEER_UPDATE(&ad,&ctrl);}
 else if(!strncmp(op,"ra-",3)){param.u4Field=42;WifiSysUpdateRa(&ad,e,strstr(name,"-null")?NULL:&param);param.u4Field=99;if(async_pending)result=dispatch(&ad,HWCMD_ID_WIFISYS_PEER_UPDATE,&saved);else result=queue_error?queue_error:0;}
 else if(!strncmp(op,"response-",9)){struct cmd_msg msg={9};EVENT_STAREC_UPDATE_T event={0};char tiny[1]={0};char *data=strstr(name,"-null")?NULL:(strstr(name,"-short")?tiny:(char*)&event);UINT16 len=strstr(name,"-short")?1:sizeof(event);event.u4Status=strstr(name,"-error")?5:0;if(strstr(name,"-dev-"))CmdExtDevInfoUpdateRsp(&msg,data,len);else if(strstr(name,"-bss-"))CmdExtBssInfoUpdateRsp(&msg,data,len);else CmdExtStaRecUpdateRsp(&msg,data,len);result=msg.cmd_return_status;}
 else if(!strncmp(op,"handler-",8)){int i=op[8]-'0';assert(i>=0&&i<7);memset(&ad.HwCtrl.hwctrl_ops,0,sizeof(ad.HwCtrl.hwctrl_ops));ctrl.wdev=&w;direct.buffer=&ctrl;direct.bufferlength=strstr(name,"-invalid")?sizeof(ctrl)-1:sizeof(ctrl);switch(i){case 0:result=HwCtrlWifiSysOpen(&ad,&direct);break;case 1:result=HwCtrlWifiSysClose(&ad,&direct);break;case 2:result=HwCtrlWifiSysLinkUp(&ad,&direct);break;case 3:result=HwCtrlWifiSysLinkDown(&ad,&direct);break;case 4:result=HwCtrlWifiSysPeerLinkUp(&ad,&direct);break;case 5:result=HwCtrlWifiSysPeerLinkDown(&ad,&direct);break;case 6:result=HwCtrlWifiSysPeerUpdate(&ad,&direct);break;}}
 else if(!strncmp(op,"cleanup-",8)){if(strstr(name,"quarantined"))ad.quarantined=1;if(strstr(name,"deinit")){result=wdev_deinit(&ad,&w);ra_value=cleaned;}else if(strstr(name,"apcli")){ad.ApCfg.ApCliTab[0].wdev.if_dev=&ad;ApCli_Remove(&ad);result=ad.ApCfg.ApCliTab[0].wdev.if_dev!=NULL;ra_value=freed;}else if(strstr(name,"wds")){ad.WdsTab.WdsEntry[0].wdev.if_dev=&ad;WDS_Remove(&ad);result=ad.WdsTab.WdsEntry[0].wdev.if_dev!=NULL;ra_value=freed;}else {e->EntryState=ENTRY_STATE_SYNC;if(strstr(name,"-failure"))queue_error=1;result=mac_entry_disconn_act(&ad,strstr(name,"-null")?NULL:e);}}
 else if(!strncmp(op,"apclilink-",10)){w.wdev_type=WDEV_TYPE_APCLI;w.bss_info_argument.bss_state=0;result=apcli_link_up(&w,e);if(strstr(name,"-retry")){assert(!result&&WDEV_BSS_STATE(&w)==BSS_INITED);fail_at=0;result=apcli_link_up(&w,e);}ra_value=ad.ApCfg.ApCliTab[0].Valid+usermode_calls;}
 else if(!strncmp(op,"aplink-",7)){w.bss_info_argument.bss_state=0;result=ap_link_up(&w,NULL);ra_value=w.media+rekey;}
 else if(!strncmp(op,"apconn-",7))result=ap_conn_act(&w,e);
 else if(!strncmp(op,"secure-",7)){WifiSysUpdatePortSecur(&ad,e,NULL);result=ad.ConInPrgress;}
 else abort();
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",result,w.DevInfo.Active,w.oper,w.bss_info_argument.bss_state,e->EntryState,hw_calls,commits,releases,ad.quarantined,queued,ra_value);return 0;}
'''


def function(text,name):
 token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
 masked=re.sub(token,lambda m:' '*len(m.group()),text)
 pattern=r'^(?:static\s+)?(?:inline\s+)?(?:INT|INT32|UINT32|NDIS_STATUS|NTSTATUS|BOOLEAN|VOID|void|MAC_TABLE_ENTRY\s*\*|struct\s+radio_dev\s*\*)\s*'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
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
