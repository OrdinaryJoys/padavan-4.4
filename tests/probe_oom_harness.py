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

MODEL_VARIANT = {'role': 'unpublished-constructor-private-inert-model',
 'MULTI_INF_SUPPORT': True,
 'actual_K2P_MULTI_INF_SUPPORT': False,
 'CONFIG_WIFI_MSI_SUPPORT': False,
 'native_extra_MSI_variant': True,
 'OS_ABL_FUNC_SUPPORT': False,
 'reduced_IE_slots': 3,
 'reduced_WPF_slots': 3,
 'native_strict_aliasing_disabled_to_match_target': True,
 'CONFIG_AP_SUPPORT': True,
 'actual_K2P_CONFIG_AP_SUPPORT': True,
 'model_HIF_MT': True,
 'actual_K2P_HIF_MT': True,
 'BCN_OFFLOAD_SUPPORT': False,
 'reduced_beacon_packet_bytes': 64,
 'beacon_packet_and_lock_ownership_asserted': True,
 'same_wdev_repeat_init_reuses_owner': True,
 'uninitialized_beacon_cleanup_requires_retired_callers': True,
 'reduced_MBSSID_slots': 3,
 'all_embedded_beacon_slots_freed_after_count_shrinks': True}

BASE = 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'

SOURCE_PATHS = {'init': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/rtmp_init.c',
 'os': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_linux.c',
 'pci': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/pci_main_dev.c',
 'free': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_profile.c',
 'hif': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/hif_pci.c',
 'hdev': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/hw_ctrl/hdev_ctrl.c',
 'rlm': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/phy/rlm_cal_cache.c',
 'config': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/wlan_config/config_basic.c',
 'header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/rtmp.h',
 'os_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/os/rt_linux.h',
 'config_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/wlan_config/config_export.h',
 'wifi_sys': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/wifi_sys_info.c',
 'os_main': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_main_dev.c',
 'config_phy': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/wlan_config/config_phy.c',
 'config_ht': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/wlan_config/config_ht.c',
 'config_vht': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/wlan_config/config_vht.c',
 'multi': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/multi_main_dev.c',
 'bcn': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/bcn.c',
 'chip_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/hw_ctrl/cmm_chip.h',
 'bcn_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/bcn.h'}

FUNCTION_SOURCES = {'RtmpOsStatsAlloc': 'os',
 'AdapterBlockAllocateMemory': 'os',
 'hdev_ctrl_init': 'hdev',
 'hdev_ctrl_exit': 'hdev',
 'rlmCalCacheInit': 'rlm',
 'rlmCalCacheDeinit': 'rlm',
 'wpf_config_exit': 'config',
 'wpf_config_init': 'config',
 'RTMPInitHifAdapterBlock': 'hif',
 'RTMPFreeHifAdapterBlock': 'hif',
 'RTMPFreeAdapterBlockInit': 'init',
 'RTMPAllocAdapterBlock': 'init',
 'RTMPFreeAdapter': 'free',
 'RtmpRaDevCtrlExit': 'init',
 'rt_pci_probe': 'pci',
 'bcn_buf_init': 'bcn',
 'bcn_buf_deinit': 'bcn'}

BODY_ORDER = ('RtmpOsStatsAlloc',
 'AdapterBlockAllocateMemory',
 'hdev_ctrl_init',
 'hdev_ctrl_exit',
 'rlmCalCacheInit',
 'rlmCalCacheDeinit',
 'wpf_config_exit',
 'wpf_config_init',
 'RTMPInitHifAdapterBlock',
 'RTMPFreeHifAdapterBlock',
 'RTMPFreeAdapterBlockInit',
 'RTMPAllocAdapterBlock',
 'RTMPFreeAdapter',
 'RtmpRaDevCtrlExit',
 'rt_pci_probe',
 'bcn_buf_init',
 'bcn_buf_deinit')

SOURCE_ONLY_FUNCTION_SOURCES = {'wifi_sys_init': 'wifi_sys',
 'RTMPAllocGlobalUtility': 'init',
 'hdev_resource_init': 'hdev',
 'hdev_resource_exit': 'hdev',
 'RtmpDmaFinalReleaseCheck': 'os_main',
 'wlan_config_init': 'config',
 'wlan_config_exit': 'config',
 'phy_cfg_init': 'config_phy',
 'phy_cfg_exit': 'config_phy',
 'ht_cfg_init': 'config_ht',
 'ht_cfg_exit': 'config_ht',
 'vht_cfg_init': 'config_vht',
 'vht_cfg_exit': 'config_vht',
 'multi_inf_adapt_reg': 'multi',
 'multi_inf_adapt_unreg': 'multi'}

SOURCE_DECLARATIONS = {'^#define NDIS_STATUS_SUCCESS\\s+0x[0-9a-fA-F]+\\s*$': 'os_header',
 '^#define NDIS_STATUS_FAILURE\\s+0x[0-9a-fA-F]+\\s*$': 'os_header',
 '^#define NDIS_STATUS_RESOURCES\\s+0x[0-9a-fA-F]+\\s*$': 'os_header',
 'enum HIF_TYPE \\{[\\s\\S]*?\\n\\};': 'chip_header',
 'enum BCN_TX_STATE \\{[\\s\\S]*?\\n\\};': 'header',
 'typedef enum _BCN_GEN_METHOD \\{[\\s\\S]*?\\} BCN_GEN_METHOD;': 'bcn_header'}

CASE_NAMES = ('ctor-oom-2',
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
 'ctor-oom-15',
 'probe-oom-1',
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
 'probe-oom-15',
 'ctor-success-free',
 'ctor-success-devctrl-free',
 'ctor-failure-retry',
 'ctor-existing-owner',
 'ctor-null-handle',
 'ctor-null-output',
 'ctor-multi-registration-failure',
 'probe-success-free',
 'probe-enable-failure',
 'probe-mask-failure',
 'probe-region-failure',
 'probe-map-failure',
 'probe-pcie-failure',
 'probe-netdev-failure',
 'probe-attach-failure',
 'probe-retained-drvdata',
 'stats-existing-owner',
 'stats-alias-output',
 'wpf-existing-owner',
 'wpf-double-exit',
 'hdev-uninitialized-exit',
 'hdev-initialized-exit',
 'hdev-null-exit',
 'quarantined-final-free',
 'quarantined-devctrl-free',
 'hdev-existing-owner',
 'probe-msi-owned-constructor-failure',
 'probe-msi-request-failure',
 'bcn-never-init',
 'bcn-post-hdev-exit',
 'bcn-adapter-lock-order',
 'bcn-packet-failure',
 'bcn-packet-resources',
 'bcn-packet-invalid',
 'bcn-packet-success-null',
 'bcn-repeat-init',
 'bcn-repeat-deinit',
 'bcn-tim-only',
 'bcn-both-packets',
 'bcn-existing-packet-init',
 'bcn-noowner-repeat',
 'bcn-alloc-owner-retry',
 'bcn-foreign-owner',
 'bcn-missing-packet',
 'bcn-noowner-tim-only',
 'bcn-noowner-beacon-only',
 'bcn-all-slots-final-free',
 'bcn-shrunk-count-final-free',
 'bcn-empty-slot-repeat-final-free')

FIELDS = ('result',
 'heap_live',
 'locks_live',
 'cookie_failure_preserved',
 'early_publications',
 'allocations_after_locks',
 'pci_enabled',
 'regions_live',
 'mapped',
 'bus_master',
 'drvdata_live',
 'unsafe_frees',
 'hardware_resource_exits',
 'owned_graph_retained',
 'device_resource_releases')

CASE_GROUPS = {'constructor-oom': ('ctor-oom-2',
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
 'extra': ('hdev-existing-owner',
           'probe-msi-owned-constructor-failure',
           'probe-msi-request-failure'),
 'beacon': ('bcn-never-init',
            'bcn-post-hdev-exit',
            'bcn-adapter-lock-order',
            'bcn-packet-failure',
            'bcn-packet-resources',
            'bcn-packet-invalid',
            'bcn-packet-success-null',
            'bcn-repeat-init',
            'bcn-repeat-deinit',
            'bcn-tim-only',
            'bcn-both-packets',
            'bcn-existing-packet-init',
            'bcn-noowner-repeat',
            'bcn-alloc-owner-retry',
            'bcn-foreign-owner',
            'bcn-missing-packet',
            'bcn-noowner-tim-only',
            'bcn-noowner-beacon-only',
            'bcn-all-slots-final-free',
            'bcn-shrunk-count-final-free',
            'bcn-empty-slot-repeat-final-free')}

EXPECTED_ROWS = {'ctor-oom-2': [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
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
 'probe-msi-request-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1],
 'bcn-never-init': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'bcn-post-hdev-exit': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-adapter-lock-order': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-packet-failure': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-packet-resources': [3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-packet-invalid': [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-packet-success-null': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-repeat-init': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-repeat-deinit': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-tim-only': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-both-packets': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-existing-packet-init': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-noowner-repeat': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'bcn-alloc-owner-retry': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-foreign-owner': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-missing-packet': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-noowner-tim-only': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'bcn-noowner-beacon-only': [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'bcn-all-slots-final-free': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-shrunk-count-final-free': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
 'bcn-empty-slot-repeat-final-free': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0]}

SOURCE_FIELD_CONSTRAINTS = {'BOOLEAN BcnContentLockInitialized;': 'header'}

PREFIX = ('\n'
 '#include <assert.h>\n'
 '#include <errno.h>\n'
 '#include <stdint.h>\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <string.h>\n'
 'typedef void VOID;typedef void *PVOID;typedef int INT,INT32,BOOLEAN,NDIS_STATUS;\n'
 'typedef unsigned int UINT32,UINT;typedef unsigned char UCHAR;typedef unsigned long ULONG,LONG;\n'
 '#define IN\n'
 '#define DEVINIT\n'
 '#define TRUE 1\n'
 '#define FALSE 0\n'
 '#define LINUX 1\n'
 '#define RTMP_MAC_PCI 1\n'
 '#define MT_MAC 1\n'
 '#define MT7615 1\n'
 '#define CONFIG_ANDES_SUPPORT 1\n'
 '#define CONFIG_AP_SUPPORT 1\n'
 '#define APCLI_SUPPORT 1\n'
 '#define MAC_REPEATER_SUPPORT 1\n'
 '#define DOT11_N_SUPPORT 1\n'
 '#define UAPSD_SUPPORT 1\n'
 '#define RLM_CAL_CACHE_SUPPORT 1\n'
 '#define RESOURCE_PRE_ALLOC 1\n'
 '#define MULTI_INF_SUPPORT 1\n'
 '#define WIRELESS_EXT 22\n'
 '#define MAX_LEN_OF_BSS_TABLE 3\n'
 '#define MAX_VIE_LEN 8\n'
 '#define WDEV_NUM_MAX 3\n'
 '#define CTL_RING_SIZE 4\n'
 '#define GFP_ATOMIC 0\n'
 '#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))\n'
 '#define LINUX_VERSION_CODE KERNEL_VERSION(4,4,198)\n'
 '#define DMA_BIT_MASK(n) (n)\n'
 '#define NETIF_F_HIGHDMA 1\n'
 '#define OPMODE_AP 1\n'
 '#define MAX_BEACON_LENGTH 64\n'
 '#define MAIN_MBSSID 0\n'
 'SOURCE_DEFINITIONS\n'
 '#define MTWF_LOG(...) ((void)0)\n'
 '#define ASSERT(v) assert(v)\n'
 '#define initList(p) do{*(p)=1;}while(0)\n'
 '#define os_zero_mem(p,n) do{assert((p)!=NULL);memset((p),0,(n));}while(0)\n'
 '#define RTMPZeroMemory(p,n) memset((p),0,(n))\n'
 '#define READ_ONCE(v) (v)\n'
 'struct _RTMP_ADAPTER;struct net_device;\n'
 'struct pci_dev {int enabled,regions,mapped,master,irq,msi_enabled;void *drvdata;int dev;};\n'
 'struct os_cookie {LONG pAd_va;struct pci_dev *pci_dev;void *pDev;};\n'
 'typedef struct os_cookie *POS_COOKIE;\n'
 'struct wlan_config {int initialized;};struct wlan_operate {int initialized;};\n'
 'struct wpf_data {int idx;void *dev;struct wlan_config *conf;struct wlan_operate *oper;};\n'
 'struct wpf_ctrl {struct wpf_data pf[WDEV_NUM_MAX];};\n'
 'struct _PCI_HIF_T {int MgmtRingLock,TxBmcRingLock,BcnRingLock,CtrlRingLock;\n'
 ' struct {int RingLock,ring_size;} FwDwloRing;};\n'
 'struct hdev_ctrl {void *priv,*cookie,*hif;};\n'
 'struct net_device_stats {int value;};struct iw_statistics {int value;};\n'
 'typedef struct {int values[4];} RLM_CAL_CACHE;\n'
 'struct wifi_dev;\n'
 'typedef struct _BCN_BUF_STRUCT {enum BCN_TX_STATE bcn_state;void *BeaconPkt;int '
 'cap_ie_pos;struct wifi_dev *pWdev;struct {void *TimPkt;} tim_buf;int BcnContentLock;\n'
 ' STATE_FIELDS\n'
 ' int BcnUpdateMethod;} BCN_BUF_STRUC;\n'
 'struct wifi_dev {BCN_BUF_STRUC bcn_buf;};typedef struct {struct wifi_dev wdev;} BSS_STRUCT;\n'
 'typedef struct _RTMP_CHIP_CAP {int fgBcnOffloadSupport;} RTMP_CHIP_CAP;\n'
 'typedef struct _RTMP_ADAPTER {void *OS_Cookie,*stats,*iw_stats,*hdev_ctrl,*rlmCalCache;\n'
 ' int '
 'RscTimerMemList,RscTaskMemList,RscLockMemList,RscTaskletMemList,RscSemMemList,RscAtomicMemList,RscTimerCreateList;\n'
 ' int '
 'TimerSemLock,WdevListLock,BssInfoIdxBitMapLock,irq_lock,tssi_lock,LockInterrupt,VirtualIfLock;\n'
 ' int McuCmdLock,DriverOwnLock,UAPSDEOSPLock,AutoRateLock,OpMode,quarantined,hif_type;\n'
 ' struct {int lock;} mpdu_blk_pool,WifiSysInfo;\n'
 ' struct {int ReptCliEntryLock,CliLinkMapLock,bMACRepeaterEn;int BssidNum;BSS_STRUCT MBSSID[3];} '
 'ApCfg;\n'
 ' struct {UCHAR *pIe;} ProbeRespIE[MAX_LEN_OF_BSS_TABLE];\n'
 ' struct _PCI_HIF_T PciHif;struct wpf_ctrl wpf;\n'
 '} RTMP_ADAPTER,*PRTMP_ADAPTER;\n'
 'struct net_device {RTMP_ADAPTER *adapter;int irq;unsigned long base_addr,features;};\n'
 'typedef int RTMP_OS_NETDEV_OP_HOOK;\n'
 'typedef struct {int pci_init_succeed;} RT_CMD_PCIE_INIT;\n'
 'struct pci_device_id {int value;};\n'
 'FUNCTION_DECLARATIONS\n'
 'struct allocation {void *p;size_t bytes;int live;};\n'
 'static struct allocation allocated[128];\n'
 'static int '
 'allocations,allocation_attempt,fail_at,locks_live,allocations_after_locks,unsafe_frees;\n'
 'static int cookie_failure_preserved,early_publications,hw_exits,owned_graph_retained;\n'
 'static int '
 'fail_enable,fail_mask,fail_region,fail_map,fail_pcie,fail_netdev,fail_attach,fail_multi;\n'
 '#ifdef CONFIG_WIFI_MSI_SUPPORT\n'
 'static int fail_msi,msi_enables,msi_disables;\n'
 '#endif\n'
 'static int '
 'config_initializations,config_exits,dep_live,ring_live,sem_live,device_resource_releases;\n'
 'static void **watched_output;\n'
 'static int '
 'packet_allocating,packet_status,packet_null_success,packet_calls,packet_frees,sem_checks;\n'
 'static int expect_cookie;static void *cookie_pointer;\n'
 'static struct pci_dev pci;\n'
 'static int live_heap(void){int n=0;for(int i=0;i<allocations;i++)n+=allocated[i].live;return '
 'n;}\n'
 'static void *get_memory(size_t n){void *p;allocation_attempt++;\n'
 ' if(watched_output&&*watched_output)early_publications++;\n'
 ' if(locks_live&&!packet_allocating)allocations_after_locks++;\n'
 ' if(fail_at==allocation_attempt)return NULL;\n'
 ' '
 'assert(allocations<128);p=malloc(n);assert(p);if(expect_cookie&&allocation_attempt==1)cookie_pointer=p;allocated[allocations++]=(struct '
 'allocation){p,n,1};return p;}\n'
 'static void release_memory(void *p){int found=-1;if(!p)return;\n'
 ' for(int i=allocations-1;i>=0;i--)if(allocated[i].p==p&&allocated[i].live){found=i;break;}\n'
 ' if(found<0){unsafe_frees++;assert(!"unknown or duplicate free");}\n'
 ' if(p==cookie_pointer)assert(((POS_COOKIE)p)->pAd_va==0);\n'
 ' allocated[found].live=0;free(p);}\n'
 'static int os_alloc_mem(void *ad,UCHAR **out,size_t n){(void)ad;*out=get_memory(n);return '
 '*out?NDIS_STATUS_SUCCESS:NDIS_STATUS_FAILURE;}\n'
 '#define os_free_mem(p) release_memory(p)\n'
 '#define RtmpOsVfree(p) release_memory(p)\n'
 'static void *vmalloc(size_t n){return get_memory(n);}\n'
 'static void lock_init(int *p){assert(!*p);*p=1;locks_live++;}\n'
 'static void lock_free(int *p){if(*p){*p=0;locks_live--;assert(locks_live>=0);}}\n'
 '#define NdisAllocateSpinLock(ad,p) lock_init(p)\n'
 '#define NdisFreeSpinLock(p) lock_free(p)\n'
 'static void RtmpDmaLifecycleInit(RTMP_ADAPTER *ad){assert(ad->OS_Cookie);}\n'
 'static int RtmpDmaFinalReleaseCheck(RTMP_ADAPTER *ad){return ad&&!ad->quarantined;}\n'
 'static void RTMPAllocGlobalUtility(void){}\n'
 'static void RTMPFreeGlobalUtility(void){}\n'
 'static void wifi_sys_init(RTMP_ADAPTER *ad){lock_init(&ad->WifiSysInfo.lock);}\n'
 'static void wlan_config_init(struct wlan_config '
 '*c){assert(!c->initialized);c->initialized=1;config_initializations++;}\n'
 'static void wlan_config_exit(struct wlan_config '
 '*c){assert(c->initialized);c->initialized=0;config_exits++;}\n'
 'static int multi_inf_adapt_reg(void *ad){(void)ad;return '
 'fail_multi?NDIS_STATUS_FAILURE:NDIS_STATUS_SUCCESS;}\n'
 'static int multi_inf_adapt_unreg(void *ad){(void)ad;return NDIS_STATUS_SUCCESS;}\n'
 'static void HdevHwResourceExit(struct hdev_ctrl '
 '*ctrl){assert(ctrl&&ctrl->cookie&&ctrl->hif);hw_exits++;}\n'
 'static void hdev_resource_exit(void *arg){struct hdev_ctrl '
 '*ctrl=arg;if(ctrl&&ctrl->cookie){HdevHwResourceExit(ctrl);ctrl->cookie=NULL;ctrl->hif=NULL;}}\n'
 'static RTMP_CHIP_CAP fake_cap;\n'
 'static RTMP_CHIP_CAP *hc_get_chip_cap(void *arg){assert(arg);return &fake_cap;}\n'
 '#define IS_HIF_TYPE(ad,t) ((ad)->hif_type==(t))\n'
 'static void sem_check(int *p){assert(p&&*p==1);sem_checks++;}\n'
 '#define RTMP_SEM_LOCK(p) sem_check(p)\n'
 '#define RTMP_SEM_UNLOCK(p) sem_check(p)\n'
 'static NDIS_STATUS RTMPAllocateNdisPacket(RTMP_ADAPTER *ad,void **out,void *header,int hlen,void '
 '*data,int bytes){\n'
 ' '
 '(void)ad;(void)header;(void)hlen;(void)data;assert(bytes==MAX_BEACON_LENGTH);packet_calls++;*out=NULL;\n'
 ' if(packet_status)return packet_status;\n'
 ' if(packet_null_success)return NDIS_STATUS_SUCCESS;\n'
 ' packet_allocating=1;*out=get_memory((size_t)bytes);packet_allocating=0;return '
 '*out?NDIS_STATUS_SUCCESS:NDIS_STATUS_FAILURE;\n'
 '}\n'
 'static void RTMPFreeNdisPacket(RTMP_ADAPTER *ad,void '
 '*pkt){(void)ad;assert(pkt);packet_frees++;release_memory(pkt);}\n'
 '#define AsicSetReptFuncEnable(ad,v) ((void)0)\n'
 '#define RTMP_OS_FREE_TIMER(ad) ((void)0)\n'
 '#define RTMP_OS_FREE_LOCK(ad) ((void)0)\n'
 '#define RTMP_OS_FREE_TASKLET(ad) ((void)0)\n'
 '#define RTMP_OS_FREE_TASK(ad) ((void)0)\n'
 '#define RTMP_OS_FREE_SEM(ad) ((void)0)\n'
 '#define RTMP_OS_FREE_ATOMIC(ad) ((void)0)\n'
 '#define RTMP_SEM_EVENT_DESTORY(p) do{if(*(p)){assert(sem_live);sem_live=0;*(p)=0;}}while(0)\n'
 'static void free_chip_cap_dep_data(RTMP_ADAPTER '
 '*ad){(void)ad;if(dep_live){dep_live=0;device_resource_releases++;}}\n'
 'static void RTMPFreeTxRxRingMemory(RTMP_ADAPTER *ad){(void)ad;ring_live=0;}\n'
 'static void completed_device_init(RTMP_ADAPTER *ad){struct hdev_ctrl '
 '*ctrl=ad->hdev_ctrl;assert(ctrl&&!ctrl->cookie&&!dep_live&&!ring_live&&!sem_live);\n'
 ' '
 'ctrl->cookie=ad->OS_Cookie;ctrl->hif=&ad->PciHif;ad->AutoRateLock=1;dep_live=ring_live=sem_live=1;}\n'
 'static void *pci_get_drvdata(struct pci_dev *d){return d->drvdata;}\n'
 'static void pci_set_drvdata(struct pci_dev *d,void *p){d->drvdata=p;}\n'
 'static int pci_enable_device(struct pci_dev *d){if(fail_enable)return-EIO;d->enabled=1;return '
 '0;}\n'
 'static void pci_disable_device(struct pci_dev '
 '*d){assert(!d->mapped&&!d->regions&&!d->master&&!d->msi_enabled);d->enabled=0;}\n'
 'static char *pci_name(struct pci_dev *d){(void)d;return "inert-pci";}\n'
 'static int pci_set_dma_mask(struct pci_dev *d,int mask){assert(d->enabled&&mask==32);return '
 'fail_mask?-EIO:0;}\n'
 'static int pci_set_consistent_dma_mask(struct pci_dev *d,int '
 'mask){assert(d->enabled&&mask==32);return 0;}\n'
 '#ifdef CONFIG_WIFI_MSI_SUPPORT\n'
 'static int RtmpOsPciMsiEnable(struct pci_dev '
 '*d){msi_enables++;if(fail_msi)return-EIO;assert(!d->msi_enabled);d->msi_enabled=1;return 0;}\n'
 'static void RtmpOsPciMsiDisable(struct pci_dev '
 '*d){assert(d->msi_enabled);d->msi_enabled=0;msi_disables++;}\n'
 '#endif\n'
 'static int pci_request_regions(struct pci_dev *d,char '
 '*name){(void)name;assert(d->enabled);if(fail_region)return-EBUSY;d->regions=1;return 0;}\n'
 'static unsigned long pci_resource_start(struct pci_dev *d,int i){assert(d->regions&&i==0);return '
 '1;}\n'
 'static unsigned long pci_resource_len(struct pci_dev *d,int i){assert(d->regions&&i==0);return '
 '1;}\n'
 'static void *ioremap(unsigned long start,unsigned long '
 'bytes){assert(start==1&&bytes==1);if(fail_map)return '
 'NULL;pci.mapped=1;return(void*)(uintptr_t)1;}\n'
 'static void pci_set_master(struct pci_dev *d){assert(d->mapped);d->master=1;}\n'
 'static void pci_clear_master(struct pci_dev *d){d->master=0;}\n'
 'static void iounmap(void '
 '*p){assert(p==(void*)(uintptr_t)1&&!pci.master);assert(live_heap()==0);pci.mapped=0;}\n'
 'static void pci_release_regions(struct pci_dev '
 '*d){assert(d->regions&&!d->mapped);d->regions=0;}\n'
 '#define RTMP_DRIVER_PCI_CSR_SET(ad,addr) do{assert((ad)&&(addr)==1);}while(0)\n'
 '#define RTMP_DRIVER_PCIE_INIT(ad,cfg,dev) '
 'do{assert((dev)==&pci);((RTMP_ADAPTER*)(ad))->OpMode=OPMODE_AP;((RTMP_ADAPTER*)(ad))->hif_type=HIF_MT;(cfg)->pci_init_succeed=!fail_pcie;if(!fail_pcie)completed_device_init(ad);}while(0)\n'
 'static struct net_device net;\n'
 'static struct net_device *RtmpPhyNetDevInit(void *arg,RTMP_OS_NETDEV_OP_HOOK *hook){RTMP_ADAPTER '
 '*ad=arg;(void)hook;\n'
 ' if(fail_netdev)return NULL;\n'
 ' /* Current resource transaction is separately executed by resource_init_harness. */\n'
 ' assert(((struct hdev_ctrl*)ad->hdev_ctrl)->cookie==ad->OS_Cookie);\n'
 ' net.adapter=ad;return &net;}\n'
 '#define RTMP_DRIVER_CHIP_PREPARE(ad) ((void)0)\n'
 '#define RTMP_DRIVER_OP_MODE_GET(ad,out) (*(out)=0)\n'
 'static int RtmpOSNetDevAttach(ULONG mode,struct net_device *n,RTMP_OS_NETDEV_OP_HOOK '
 '*hook){(void)mode;(void)hook;assert(n==&net);return fail_attach?-EIO:0;}\n'
 'static void RtmpOSNetDevFree(struct net_device *n){assert(n==&net);n->adapter=NULL;}\n')

SUFFIX = ('\n'
 'static POS_COOKIE cookie_new(void){POS_COOKIE '
 'c=NULL;os_alloc_mem(NULL,(UCHAR**)&c,sizeof(*c));assert(c);memset(c,0,sizeof(*c));c->pci_dev=&pci;return '
 'c;}\n'
 'static void initialized_hdev(RTMP_ADAPTER *ad){struct hdev_ctrl '
 '*ctrl=ad->hdev_ctrl;assert(ctrl);ctrl->hif=&ad->PciHif;ctrl->cookie=ad->OS_Cookie;}\n'
 'static void emit(int '
 'result){printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\\n",result,live_heap(),locks_live,cookie_failure_preserved,early_publications,allocations_after_locks,pci.enabled,pci.regions,pci.mapped,pci.master,pci.drvdata!=NULL,unsafe_frees,hw_exits,owned_graph_retained,device_resource_releases);}\n'
 'int main(int argc,char **argv){const char *name;int result=0;VOID *out=NULL;POS_COOKIE '
 'cookie=NULL;\n'
 ' assert(argc==2);name=argv[1];CASE_ADMISSION\n'
 ' '
 'expect_cookie=!strncmp(name,"ctor-",5)||!strncmp(name,"probe-",6)||!strncmp(name,"quarantined-",12)||!strncmp(name,"bcn-",4);\n'
 '  if(!strncmp(name,"bcn-",4)){\n'
 '  cookie=cookie_new();assert(RTMPAllocAdapterBlock(cookie,&out)==NDIS_STATUS_SUCCESS&&out);\n'
 '  RTMP_ADAPTER *ad=out;ad->OpMode=OPMODE_AP;ad->hif_type=HIF_MT;\n'
 '  struct wifi_dev *wdev=&ad->ApCfg.MBSSID[MAIN_MBSSID].wdev;BCN_BUF_STRUC *info=&wdev->bcn_buf;\n'
 '  int base_locks=locks_live,freed=0;\n'
 '  if(!strcmp(name,"bcn-never-init")||!strncmp(name,"bcn-noowner-",12)){\n'
 '   assert(((struct hdev_ctrl*)ad->hdev_ctrl)->hif==NULL);\n'
 '   '
 'if(!strcmp(name,"bcn-noowner-tim-only"))assert(RTMPAllocateNdisPacket(ad,&info->tim_buf.TimPkt,NULL,0,NULL,MAX_BEACON_LENGTH)==NDIS_STATUS_SUCCESS);\n'
 '   '
 'if(!strcmp(name,"bcn-noowner-beacon-only"))assert(RTMPAllocateNdisPacket(ad,&info->BeaconPkt,NULL,0,NULL,MAX_BEACON_LENGTH)==NDIS_STATUS_SUCCESS);\n'
 '   '
 'result=bcn_buf_deinit(ad,info);assert(!info->BeaconPkt&&!info->tim_buf.TimPkt&&!info->pWdev);\n'
 '   assert(result==TRUE&&!sem_checks&&locks_live==base_locks);\n'
 '   '
 'if(!strcmp(name,"bcn-noowner-repeat")){assert(bcn_buf_deinit(ad,info)==TRUE);assert(!sem_checks);}\n'
 '  }else{\n'
 '   initialized_hdev(ad);\n'
 '   '
 'if(!strcmp(name,"bcn-packet-failure")||!strcmp(name,"bcn-packet-resources")||!strcmp(name,"bcn-packet-invalid")||!strcmp(name,"bcn-packet-success-null")){\n'
 '    '
 'packet_status=!strcmp(name,"bcn-packet-failure")?NDIS_STATUS_FAILURE:!strcmp(name,"bcn-packet-resources")?NDIS_STATUS_RESOURCES:!strcmp(name,"bcn-packet-invalid")?2:0;\n'
 '    packet_null_success=!strcmp(name,"bcn-packet-success-null");result=bcn_buf_init(ad,wdev);\n'
 '    '
 'assert(result!=NDIS_STATUS_SUCCESS&&!info->BeaconPkt&&!info->BcnContentLockInitialized&&!info->BcnContentLock);\n'
 '    assert(locks_live==base_locks&&!sem_checks);\n'
 '   }else{\n'
 '    '
 'if(!strcmp(name,"bcn-existing-packet-init"))assert(RTMPAllocateNdisPacket(ad,&info->BeaconPkt,NULL,0,NULL,MAX_BEACON_LENGTH)==NDIS_STATUS_SUCCESS);\n'
 '    if(!strcmp(name,"bcn-alloc-owner-retry")){\n'
 '     packet_status=NDIS_STATUS_RESOURCES;assert(bcn_buf_init(ad,wdev)==NDIS_STATUS_RESOURCES);\n'
 '     assert(!info->BcnContentLockInitialized&&locks_live==base_locks);packet_status=0;\n'
 '    }\n'
 '    result=bcn_buf_init(ad,wdev);assert(result==NDIS_STATUS_SUCCESS);\n'
 '    '
 'assert(info->BcnContentLockInitialized&&info->BcnContentLock&&info->BeaconPkt&&info->pWdev==wdev&&info->bcn_state==BCN_TX_IDLE);\n'
 '    assert(locks_live==base_locks+1);\n'
 '    if(!strcmp(name,"bcn-repeat-init")){int calls=packet_calls;void '
 '*owner=info->BeaconPkt;result=bcn_buf_init(ad,wdev);assert(result==NDIS_STATUS_SUCCESS&&packet_calls==calls&&info->BeaconPkt==owner&&locks_live==base_locks+1);}\n'
 '    if(!strcmp(name,"bcn-foreign-owner")){struct wifi_dev foreign={0};info->pWdev=&foreign;int '
 'calls=packet_calls;void '
 '*owner=info->BeaconPkt;result=bcn_buf_init(ad,wdev);assert(result==NDIS_STATUS_FAILURE&&info->pWdev==&foreign&&info->BeaconPkt==owner&&packet_calls==calls&&locks_live==base_locks+1);}\n'
 '    '
 'if(!strcmp(name,"bcn-missing-packet")){RTMPFreeNdisPacket(ad,info->BeaconPkt);info->BeaconPkt=NULL;int '
 'calls=packet_calls;result=bcn_buf_init(ad,wdev);assert(result==NDIS_STATUS_FAILURE&&info->BcnContentLockInitialized&&info->pWdev==wdev&&packet_calls==calls&&locks_live==base_locks+1);}\n'
 '    if(!strcmp(name,"bcn-post-hdev-exit")){hdev_resource_exit(ad->hdev_ctrl);assert(((struct '
 'hdev_ctrl*)ad->hdev_ctrl)->hif==NULL);}\n'
 '    if(!strcmp(name,"bcn-tim-only")||!strcmp(name,"bcn-both-packets")){\n'
 '     '
 'assert(RTMPAllocateNdisPacket(ad,&info->tim_buf.TimPkt,NULL,0,NULL,MAX_BEACON_LENGTH)==NDIS_STATUS_SUCCESS);\n'
 '     '
 'if(!strcmp(name,"bcn-tim-only")){RTMPFreeNdisPacket(ad,info->BeaconPkt);info->BeaconPkt=NULL;}\n'
 '    }\n'
 '    '
 'if(!strcmp(name,"bcn-all-slots-final-free")||!strcmp(name,"bcn-shrunk-count-final-free")||!strcmp(name,"bcn-empty-slot-repeat-final-free")){\n'
 '     int packets=1;\n'
 '     for(int slot=1;slot<3;slot++){\n'
 '      if(slot==1&&!strcmp(name,"bcn-empty-slot-repeat-final-free")){\n'
 '       assert(bcn_buf_deinit(ad,&ad->ApCfg.MBSSID[slot].wdev.bcn_buf)==TRUE);\n'
 '       assert(bcn_buf_deinit(ad,&ad->ApCfg.MBSSID[slot].wdev.bcn_buf)==TRUE);\n'
 '      '
 '}else{assert(bcn_buf_init(ad,&ad->ApCfg.MBSSID[slot].wdev)==NDIS_STATUS_SUCCESS);packets++;}\n'
 '     }\n'
 '     ad->ApCfg.BssidNum=!strcmp(name,"bcn-shrunk-count-final-free")?1:3;\n'
 '     '
 'RTMPFreeAdapter(ad);out=NULL;freed=1;assert(packet_frees==packets&&locks_live==0);result=0;\n'
 '    }else if(!strcmp(name,"bcn-adapter-lock-order")){\n'
 '     RTMPFreeAdapter(ad);out=NULL;freed=1;assert(packet_frees==1&&locks_live==0);result=0;\n'
 '    }else{\n'
 '     int operation_status=result;assert(bcn_buf_deinit(ad,info)==TRUE);\n'
 '     '
 'assert(!info->BcnContentLockInitialized&&!info->BcnContentLock&&!info->BeaconPkt&&!info->tim_buf.TimPkt&&!info->pWdev);\n'
 '     assert(locks_live==base_locks);\n'
 '     if(!strcmp(name,"bcn-repeat-deinit")){int '
 'checked=sem_checks;assert(bcn_buf_deinit(ad,info)==TRUE);assert(sem_checks==checked&&locks_live==base_locks);}\n'
 '     '
 'result=(!strcmp(name,"bcn-repeat-init")||!strcmp(name,"bcn-existing-packet-init")||!strcmp(name,"bcn-alloc-owner-retry")||!strcmp(name,"bcn-foreign-owner")||!strcmp(name,"bcn-missing-packet"))?operation_status:TRUE;\n'
 '    }\n'
 '   }\n'
 '  }\n'
 '  if(!freed){assert(!info->BcnContentLockInitialized);RTMPFreeAdapter(ad);out=NULL;}\n'
 ' }else\n'
 'if(!strncmp(name,"ctor-oom-",9)||!strcmp(name,"ctor-failure-retry")){\n'
 '  '
 'cookie=cookie_new();fail_at=!strcmp(name,"ctor-failure-retry")?4:atoi(name+9);watched_output=&out;\n'
 '  result=RTMPAllocAdapterBlock(cookie,&out);assert(result!=NDIS_STATUS_SUCCESS&&out==NULL);\n'
 '  assert(cookie->pAd_va==0&&live_heap()==1&&locks_live==0);cookie_failure_preserved=1;\n'
 '  '
 'if(!strcmp(name,"ctor-failure-retry")){fail_at=0;result=RTMPAllocAdapterBlock(cookie,&out);assert(result==NDIS_STATUS_SUCCESS&&out);RTMPFreeAdapter(out);}\n'
 '  else os_free_mem(cookie);\n'
 ' }else if(!strncmp(name,"probe-oom-",10)){\n'
 '  '
 'fail_at=atoi(name+10);result=rt_pci_probe(&pci,NULL);assert(result<0&&!pci.drvdata&&live_heap()==0&&locks_live==0);\n'
 ' }else '
 'if(!strcmp(name,"ctor-success-free")||!strcmp(name,"ctor-success-devctrl-free")||!strcmp(name,"ctor-existing-owner")||!strcmp(name,"ctor-multi-registration-failure")||strstr(name,"quarantined-")){\n'
 '  '
 'cookie=cookie_new();watched_output=&out;fail_multi=!strcmp(name,"ctor-multi-registration-failure");result=RTMPAllocAdapterBlock(cookie,&out);\n'
 '  '
 'if(fail_multi){assert(result!=NDIS_STATUS_SUCCESS&&!out&&cookie->pAd_va==0&&locks_live==0&&live_heap()==1);cookie_failure_preserved=1;os_free_mem(cookie);}\n'
 '  else{\n'
 '   assert(result==NDIS_STATUS_SUCCESS&&out&&cookie->pAd_va==(LONG)out);RTMP_ADAPTER '
 '*ad=out;watched_output=NULL;\n'
 '   if(!strcmp(name,"ctor-existing-owner")){VOID *duplicate=(void*)(uintptr_t)1;int '
 'before=live_heap();result=RTMPAllocAdapterBlock(cookie,&duplicate);assert(result!=NDIS_STATUS_SUCCESS&&!duplicate&&live_heap()==before&&cookie->pAd_va==(LONG)ad);}\n'
 '   '
 'if(strstr(name,"quarantined-")){if(!strcmp(name,"quarantined-devctrl-free"))completed_device_init(ad);int '
 'before=live_heap();ad->quarantined=1;if(!strcmp(name,"quarantined-devctrl-free"))assert(RtmpRaDevCtrlExit(ad)==FALSE);else '
 'RTMPFreeAdapter(ad);assert(live_heap()==before&&locks_live==16&&cookie->pAd_va==(LONG)ad);owned_graph_retained=1;ad->quarantined=0;}\n'
 '   '
 'if(!strcmp(name,"ctor-success-devctrl-free")){completed_device_init(ad);assert(RtmpRaDevCtrlExit(ad)==TRUE);}else '
 'if(!strcmp(name,"quarantined-devctrl-free"))assert(RtmpRaDevCtrlExit(ad)==TRUE);else '
 'RTMPFreeAdapter(ad);\n'
 '  }\n'
 ' }else '
 'if(!strcmp(name,"ctor-null-handle")){result=RTMPAllocAdapterBlock(NULL,&out);assert(result!=NDIS_STATUS_SUCCESS&&!out);\n'
 ' }else '
 'if(!strcmp(name,"ctor-null-output")){result=RTMPAllocAdapterBlock(NULL,NULL);assert(result!=NDIS_STATUS_SUCCESS);\n'
 ' }else if(!strcmp(name,"hdev-existing-owner")){RTMP_ADAPTER '
 'ad;memset(&ad,0,sizeof(ad));assert(hdev_ctrl_init(&ad)==0);void *owner=ad.hdev_ctrl;int '
 'n=allocation_attempt;result=hdev_ctrl_init(&ad);assert(result==-1&&ad.hdev_ctrl==owner&&allocation_attempt==n);hdev_ctrl_exit(&ad);\n'
 ' }else '
 'if(!strcmp(name,"probe-msi-owned-constructor-failure")){fail_at=2;result=rt_pci_probe(&pci,NULL);assert(result<0&&!pci.drvdata&&live_heap()==0);\n'
 ' }else '
 'if(!strcmp(name,"probe-retained-drvdata")){pci.drvdata=(void*)(uintptr_t)1;result=rt_pci_probe(&pci,NULL);assert(result==-EBUSY&&allocation_attempt==0&&!pci.enabled);pci.drvdata=NULL;\n'
 ' }else if(!strncmp(name,"probe-",6)){\n'
 '  '
 'fail_enable=!strcmp(name,"probe-enable-failure");fail_mask=!strcmp(name,"probe-mask-failure");fail_region=!strcmp(name,"probe-region-failure");fail_map=!strcmp(name,"probe-map-failure");fail_pcie=!strcmp(name,"probe-pcie-failure");fail_netdev=!strcmp(name,"probe-netdev-failure");fail_attach=!strcmp(name,"probe-attach-failure");\n'
 '#ifdef CONFIG_WIFI_MSI_SUPPORT\n'
 '  fail_msi=!strcmp(name,"probe-msi-request-failure");\n'
 '#endif\n'
 '  result=rt_pci_probe(&pci,NULL);\n'
 '  '
 'if(!strcmp(name,"probe-success-free")||!strcmp(name,"probe-msi-request-failure")){assert(result==0&&pci.drvdata==&net);assert(RtmpRaDevCtrlExit(net.adapter)==TRUE);RtmpOSNetDevFree(&net);pci.drvdata=NULL;pci_clear_master(&pci);iounmap((void*)(uintptr_t)1);pci_release_regions(&pci);\n'
 '#ifdef CONFIG_WIFI_MSI_SUPPORT\n'
 '   if(pci.msi_enabled)RtmpOsPciMsiDisable(&pci);\n'
 '#endif\n'
 '   pci_disable_device(&pci);}\n'
 '  else assert(result<0&&!pci.drvdata&&live_heap()==0&&locks_live==0);\n'
 ' }else if(!strcmp(name,"stats-existing-owner")){VOID '
 '*stats=get_memory(9),*iw=NULL;result=RtmpOsStatsAlloc(&stats,&iw);assert(result==FALSE&&stats&&!iw&&allocation_attempt==1);release_memory(stats);\n'
 ' }else if(!strcmp(name,"stats-alias-output")){VOID '
 '*stats=NULL;result=RtmpOsStatsAlloc(&stats,&stats);assert(result==FALSE&&!stats&&allocation_attempt==0);\n'
 ' }else if(!strcmp(name,"wpf-existing-owner")||!strcmp(name,"wpf-double-exit")){\n'
 '  RTMP_ADAPTER ad;memset(&ad,0,sizeof(ad));assert(wpf_config_init(&ad)==NDIS_STATUS_SUCCESS);\n'
 '  if(!strcmp(name,"wpf-existing-owner")){int n=allocation_attempt;void '
 '*owner=ad.wpf.pf[1].conf;result=wpf_config_init(&ad);assert(result!=NDIS_STATUS_SUCCESS&&allocation_attempt==n&&ad.wpf.pf[1].conf==owner);}\n'
 '  '
 'wpf_config_exit(&ad);wpf_config_exit(&ad);assert(config_initializations==config_exits&&live_heap()==0);\n'
 ' }else '
 'if(!strcmp(name,"hdev-uninitialized-exit")||!strcmp(name,"hdev-initialized-exit")||!strcmp(name,"hdev-null-exit")){\n'
 '  RTMP_ADAPTER '
 'ad;memset(&ad,0,sizeof(ad));if(strcmp(name,"hdev-null-exit")){assert(hdev_ctrl_init(&ad)==0);if(!strcmp(name,"hdev-initialized-exit")){ad.OS_Cookie=(void*)(uintptr_t)1;initialized_hdev(&ad);}}\n'
 '  hdev_ctrl_exit(&ad);hdev_ctrl_exit(&ad);assert(!ad.hdev_ctrl&&live_heap()==0);\n'
 ' }else assert(!"unknown case");\n'
 ' '
 'assert(live_heap()==0&&locks_live==0&&unsafe_frees==0&&early_publications==0&&allocations_after_locks==0);\n'
 ' assert(!dep_live&&!ring_live&&!sem_live&&config_initializations==config_exits);\n'
 '#ifdef CONFIG_WIFI_MSI_SUPPORT\n'
 ' '
 'if(!strcmp(name,"probe-msi-owned-constructor-failure"))assert(msi_enables==1&&msi_disables==1);\n'
 ' if(!strcmp(name,"probe-msi-request-failure"))assert(msi_enables==1&&msi_disables==0);\n'
 '#endif\n'
 ' emit(result);return 0;\n'
 '}\n')

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
           'CASE_GROUPS','EXPECTED_ROWS','SOURCE_FIELD_CONSTRAINTS','PREFIX','SUFFIX')
    values={name:globals()[name]for name in names}
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def generate_source(texts,variant='current'):
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Current complete probe source set required')
    function_manifest(texts);source_only_manifest(texts)
    bodies={n:function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER}
    prototypes='\n'.join(body[:body.index('{')].strip()+';'for body in bodies.values())
    admission='if(!('+'||'.join('!strcmp(name,"'+name+'")'for name in CASE_NAMES)+'))return 91;'
    fields=[]
    for pattern,key in SOURCE_FIELD_CONSTRAINTS.items():
        matches=re.findall(pattern,texts[key],re.M)
        if len(matches)!=1:raise ValueError('Unique beacon field declaration required: '+pattern)
        fields.append(matches[0])
    prefix=PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts)).replace('STATE_FIELDS','\n'.join(fields)).replace('FUNCTION_DECLARATIONS',prototypes)
    return prefix+'\n'.join(bodies.values())+SUFFIX.replace('CASE_ADMISSION',admission)
