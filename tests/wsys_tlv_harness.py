"""Whole-source station TLV assembly and unsubmitted-message retirement model.

The actual builder, dispatch, retry and force-free bodies run. Packet/queue,
allocator, firmware and hardware-dependent packing helpers are inert seams.
Synthetic wide wire structs deliberately do not claim the real kernel ABI.
"""
import hashlib
import re
SOURCE_PATHS = {'fw': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/mcu/fw_cmd.c',
 'core': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mcu/andes_core.c',
 'header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/mcu/mt_cmd.h',
 'sys': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/wifi_sys_info.c',
 'os_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/os/rt_linux.h',
 'core_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/mcu/andes_core.h'}
FUNCTION_SOURCES = {'pTlvAppend': 'fw',
 'StaRecUpdateBasic': 'fw',
 'StaRecUpdateRa': 'fw',
 'StaRecUpdateRaInfo': 'fw',
 'StaRecUpdateRaUpdate': 'fw',
 'StaRecUpdateBf': 'fw',
 'StaRecUpdateAmsdu': 'fw',
 'StaRecUpdateTxProc': 'fw',
 'StaRecUpdateHtInfo': 'fw',
 'StaRecUpdateVhtInfo': 'fw',
 'StaRecUpdateApPs': 'fw',
 'StaRecUpdateSecKey': 'fw',
 'StaRecUpdateWtbl': 'fw',
 'CmdExtStaRecUpdate_ReSyncDelete': 'fw',
 'CmdExtStaRecUpdate': 'fw',
 'CmdExtStaRecBaUpdate': 'fw',
 'AndesAppendCmdMsg': 'core',
 'AndesAppendHeadCmdMsg': 'core',
 'AndesForceFreeCmdMsg': 'core'}
BODY_ORDER = ('AndesAppendCmdMsg',
 'AndesAppendHeadCmdMsg',
 'AndesForceFreeCmdMsg',
 'pTlvAppend',
 'StaRecUpdateBasic',
 'StaRecUpdateRa',
 'StaRecUpdateRaInfo',
 'StaRecUpdateRaUpdate',
 'StaRecUpdateBf',
 'StaRecUpdateAmsdu',
 'StaRecUpdateTxProc',
 'StaRecUpdateHtInfo',
 'StaRecUpdateVhtInfo',
 'StaRecUpdateApPs',
 'StaRecUpdateSecKey',
 'StaRecUpdateWtbl',
 'CmdExtStaRecUpdate_ReSyncDelete',
 'CmdExtStaRecUpdate',
 'CmdExtStaRecBaUpdate')
SOURCE_ONLY_FUNCTION_SOURCES = {'AndesSendCmdMsg': 'core', 'starec_feature_decision': 'sys'}
SOURCE_DECLARATIONS = {'^#define NDIS_STATUS_SUCCESS\\s+0x00\\s*$': 'os_header',
 '^#define NDIS_STATUS_FAILURE\\s+0x01\\s*$': 'os_header',
 '^#define NDIS_STATUS_INVALID_DATA\\s+0x02\\s*$': 'os_header',
 '^#define NDIS_STATUS_RESOURCES\\s+0x03\\s*$': 'os_header',
 '^static STAREC_HANDLE_T StaRecHandle\\[\\] = \\{[\\s\\S]*?^\\};': 'fw',
 '^VOID AndesForceFreeCmdMsg\\(struct cmd_msg \\*msg\\);$': 'core_header'}
MODEL_VARIANT = {'kind': 'mt7615-current-tlv-construction',
 'DOT11_N_SUPPORT': True,
 'DOT11_VHT_AC': True,
 'TXBF_SUPPORT': True,
 'HDR_TRANS_RX_SUPPORT': True,
 'HDR_TRANS_TX_SUPPORT': True,
 'RACTRL_FW_OFFLOAD_SUPPORT': True,
 'HW_TX_AMSDU_SUPPORT': False,
 'CONFIG_STA_SUPPORT': False,
 'synthetic_wire_layout': True,
 'wire_layout_is_actual_kernel_ABI': False,
 'firmware': 'inert',
 'queue': 'inert',
 'allocator': 'fault-injected',
 'force_free_body': 'whole-function',
 'serialized_logical_header_TLV_order_BA_fields_observed': True,
 'prior_eleven_observations_preserved_as_prefix': True,
 'retry_packet_alias_NULL_and_distinct_owner_seams': True,
 'resync_feature_mask_member_not_consumed_by_basic_builder': True,
 'observation_width': 12,
 'observation_last_column': 'ordered send records: '
                            '[bss_u8,wlan_u8,muar_u8,total_u16,append_u8,tags_u16_list,[basic_type_u32,basic_state_u8],[ba_tid_u8,direction_u8,enable_u8,seq_u16,window_u16,amsdu_u8]]',
 'observation_values': 'JSON integers (never booleans); header/BA ranges follow synthetic declared '
                       'UCHAR/UINT16/UINT32 fields',
 'synthetic_wire_layout_and_control_constants_not_real_firmware_ABI': True}
CASE_NAMES = ('normal',
 'bcmc',
 'cmd-oom',
 'wtbl-oom',
 'wtbl-status-fail',
 'missing-entry',
 'missing-wdev',
 'null-handler',
 'unknown-feature',
 'ra-reject',
 'ra-ok',
 'ra-update-ok',
 'bf-ok',
 'amsdu-ok',
 'ht-ok',
 'vht-ok',
 'ap-ps-ok',
 'key-ok',
 'all-selected',
 'fw-retry-ok',
 'fw-fail',
 'resync-fail',
 'retry-cmd-oom',
 'retry-wtbl-oom',
 'resync-ok',
 'resync-null',
 'resync-oom',
 'resync-builder-fail',
 'ba-ori',
 'ba-rcv',
 'ba-invalid',
 'ba-null',
 'ba-oom',
 'ba-ori-disable',
 'ba-rcv-disable',
 'forcefree-no-retry',
 'forcefree-distinct-retry')
# ret, msg_alloc, msg_free, packet_free, wtbl_alloc, wtbl_free, sends,
# live_msg, live_packet, completion_end, final_header_TLV_count.
EXPECTED_ROWS = {'normal': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 3, [[0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'bcmc': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 3, [[0, 0, 0, 3, 1, [0, 8, 13], [1, 1], [0, 0, 0, 0, 0, 0]]]],
 'cmd-oom': [3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, []],
 'wtbl-oom': [3, 1, 1, 1, 1, 0, 0, 0, 0, 1, 0, []],
 'wtbl-status-fail': [3, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, []],
 'missing-entry': [-1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, []],
 'missing-wdev': [-1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, []],
 'null-handler': [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, []],
 'unknown-feature': [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, []],
 'ra-reject': [-1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, []],
 'ra-ok': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 4, [[0, 0, 0, 4, 1, [0, 1, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'ra-update-ok': [0,
                  1,
                  1,
                  1,
                  1,
                  1,
                  1,
                  0,
                  0,
                  1,
                  4,
                  [[0, 0, 0, 4, 1, [0, 3, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'bf-ok': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 4, [[0, 0, 0, 4, 1, [0, 4, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'amsdu-ok': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 4, [[0, 0, 0, 4, 1, [0, 5, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'ht-ok': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 4, [[0, 0, 0, 4, 1, [0, 8, 9, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'vht-ok': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 4, [[0, 0, 0, 4, 1, [0, 8, 10, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'ap-ps-ok': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 4, [[0, 0, 0, 4, 1, [0, 8, 11, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'key-ok': [0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 4, [[0, 0, 0, 4, 1, [0, 8, 12, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'all-selected': [0,
                  1,
                  1,
                  1,
                  1,
                  1,
                  1,
                  0,
                  0,
                  1,
                  11,
                  [[0, 0, 0, 11, 1, [0, 1, 3, 4, 5, 8, 9, 10, 11, 12, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'fw-retry-ok': [0,
                 3,
                 3,
                 3,
                 2,
                 2,
                 3,
                 0,
                 0,
                 3,
                 3,
                 [[0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]],
                  [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]],
                  [0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'fw-fail': [5,
             7,
             7,
             7,
             4,
             4,
             7,
             0,
             0,
             7,
             3,
             [[0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]],
              [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]],
              [0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]],
              [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]],
              [0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]],
              [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]],
              [0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'resync-fail': [5,
                 4,
                 4,
                 4,
                 1,
                 1,
                 4,
                 0,
                 0,
                 4,
                 1,
                 [[0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]],
                  [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]],
                  [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]],
                  [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]]]],
 'retry-cmd-oom': [3,
                   3,
                   2,
                   2,
                   1,
                   1,
                   2,
                   0,
                   0,
                   2,
                   1,
                   [[0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]],
                    [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]]]],
 'retry-wtbl-oom': [3,
                    3,
                    3,
                    3,
                    2,
                    1,
                    2,
                    0,
                    0,
                    3,
                    1,
                    [[0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]],
                     [0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]]]],
 'resync-ok': [0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, [[0, 0, 0, 1, 1, [0], [2, 0], [0, 0, 0, 0, 0, 0]]]],
 'resync-null': [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, []],
 'resync-oom': [3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, []],
 'resync-builder-fail': [5, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, []],
 'ba-ori': [0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, [[3, 17, 9, 1, 1, [6], [0, 0], [5, 1, 32, 2748, 64, 1]]]],
 'ba-rcv': [0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, [[4, 18, 10, 1, 1, [6], [0, 0], [6, 2, 64, 801, 32, 0]]]],
 'ba-invalid': [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, []],
 'ba-null': [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, []],
 'ba-oom': [3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, []],
 'ba-ori-disable': [0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, [[3, 17, 9, 1, 1, [6], [0, 0], [5, 1, 0, 2748, 64, 1]]]],
 'ba-rcv-disable': [0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, [[4, 18, 10, 1, 1, [6], [0, 0], [6, 2, 0, 801, 32, 0]]]],
 'forcefree-no-retry': [0,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        0,
                        0,
                        1,
                        3,
                        [[0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]],
 'forcefree-distinct-retry': [0,
                              1,
                              1,
                              2,
                              1,
                              1,
                              1,
                              0,
                              0,
                              1,
                              3,
                              [[0, 0, 0, 3, 1, [0, 8, 13], [2, 1], [0, 0, 0, 0, 0, 0]]]]}
PREFIX = ('\n'
 '#include <assert.h>\n'
 '#include <stddef.h>\n'
 '#include <stdint.h>\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <string.h>\n'
 '#define CONFIG_AP_SUPPORT\n'
 '#define APCLI_SUPPORT\n'
 '#define DOT11_N_SUPPORT\n'
 '#define DOT11_VHT_AC\n'
 '#define TXBF_SUPPORT\n'
 '#define HDR_TRANS_TX_SUPPORT\n'
 '#define HDR_TRANS_RX_SUPPORT\n'
 '#define RACTRL_FW_OFFLOAD_SUPPORT\n'
 '#define MAC_REPEATER_SUPPORT\n'
 '#define TRUE 1\n'
 '#define FALSE 0\n'
 '#define WLAN_STATUS_SUCCESS 0\n'
 '#define STAREC_RETRY 3\n'
 '#define HOST2N9 1\n'
 '#define EXT_CID 2\n'
 '#define EXT_CMD_STAREC_UPDATE 3\n'
 '#define INIT_LEN_VAR_CMD_SET_AND_WAIT_RETRY_RSP 4\n'
 '#define MAC_ADDR_LEN 6\n'
 '#define STAREC_COMMON_EXTRAINFO_V2 1\n'
 '#define STAREC_COMMON_EXTRAINFO_NEWSTAREC 2\n'
 '#define STATE_DISCONNECT 0\n'
 '#define STATE_CONNECTED 1\n'
 '#define CONNECTION_INFRA_BC 1\n'
 '#define WDEV_TYPE_AP 1\n'
 '#define WDEV_TYPE_APCLI 2\n'
 '#define WDEV_TYPE_STA 3\n'
 '#define WDEV_TYPE_WDS 4\n'
 '#define OPMODE_AP 1\n'
 '#define MMPS_DYNAMIC 1\n'
 '#define ORI_BA 1\n'
 '#define RCV_BA 2\n'
 '#define RESET_WTBL_AND_SET 1\n'
 '#define RVLAN 1\n'
 '#define TX_PROC_ACM_CFG_EN 2\n'
 '#define TX_PROC_ACM_CFG_BK 4\n'
 '#define TX_PROC_ACM_CFG_BE 8\n'
 '#define TX_PROC_ACM_CFG_VI 16\n'
 '#define TX_PROC_ACM_CFG_VO 32\n'
 '#define MTWF_LOG(...) ((void)0)\n'
 '#define CLIENT_STATUS_TEST_FLAG(p,f) ((void)(p),0)\n'
 '#define IS_ENTRY_APCLI(p) ((void)(p),0)\n'
 '#define IS_ENTRY_REPEATER(p) ((void)(p),0)\n'
 '#define IS_CIPHER_TKIP_Entry(p) ((void)(p),0)\n'
 '#define IS_HT_STA(p) ((void)(p),1)\n'
 '#define IS_VHT_STA(p) ((void)(p),1)\n'
 '#define IS_MT7615(p) ((void)(p),1)\n'
 '#define IS_MT7622(p) ((void)(p),0)\n'
 '#define IS_P18(p) ((void)(p),0)\n'
 '#define IS_MT7663(p) ((void)(p),0)\n'
 '#define IF_DEV_CONFIG_OPMODE_ON_STA(ad) if (0)\n'
 '#define DlListForEach(p,h,t,m) for ((void)(h),(p)=NULL;(p)!=NULL;(p)=NULL)\n'
 '#define OS_SEM_LOCK(p) ((void)(p))\n'
 '#define OS_SEM_UNLOCK(p) ((void)(p))\n'
 '#define cpu2le16(v) (v)\n'
 '#define cpu2le32(v) (v)\n'
 '#define le2cpu16(v) (v)\n'
 '#define le2cpu32(v) (v)\n'
 'typedef uint8_t UINT8,UCHAR,*PUCHAR,BOOLEAN;typedef uint16_t UINT16;typedef uint32_t UINT32;typedef '
 'unsigned long ULONG;typedef int32_t INT32,NDIS_STATUS;typedef void VOID;\n'
 'static const UCHAR BROADCAST_ADDR[6]={255,255,255,255,255,255};\n'
 'enum '
 '{STA_REC_BASIC_STA_RECORD=0,STA_REC_RA,STA_REC_RA_COMMON_INFO,STA_REC_RA_UPDATE,STA_REC_BF,STA_REC_AMSDU,STA_REC_BA,STA_REC_RED,STA_REC_TX_PROC,STA_REC_BASIC_HT_INFO,STA_REC_BASIC_VHT_INFO,STA_REC_AP_PS,STA_REC_INSTALL_KEY,STA_REC_WTBL};\n'
 '#define STA_REC_BASIC_STA_RECORD_FEATURE (1U<<STA_REC_BASIC_STA_RECORD)\n'
 '#define WTBL_GENERIC 0\n'
 '#define WTBL_RX 1\n'
 '#define WTBL_HT 2\n'
 '#define WTBL_VHT 3\n'
 '#define WTBL_TX_PS 5\n'
 '#define WTBL_HDR_TRANS 6\n'
 '#define WTBL_RDG 9\n'
 '#define WTBL_BF 12\n'
 '#define WTBL_SMPS 13\n'
 '#define WTBL_SPE 16\n'
 '/* Deliberately synthetic/wide wire layout: control flow and ownership only. */\n'
 'typedef struct Wire {UINT16 '
 'u2Tag,u2Length,u2AID,u2ExtraInfo,u2HtCap,u2VhtRxMcsMap,u2VhtTxMcsMap,u2StaListenInterval,u2BaStartSeq,u2BaWinSize,u2PartialAID,u2PFMUIdx;UINT32 '
 'u4ConnectionType,u4TxProcFlag,u4VhtCap;UCHAR aucPeerMacAddr[6],aucPeerAddress[6];UCHAR '
 'ucConnectionState,ucIsQBSS,ucMaxMpduSize,ucMaxAmsduNum,ucStaBmpTriggerAC,ucStaBmpDeliveryAC,ucStaMaxSPLength,ucTid,ucBaDirection,ucAmsduCap,ucBaEenable,ucRv,ucRca2,ucRca1,ucMUARIndex,ucQos,ucBafEn,ucAadOm,ucFd,ucTd,ucDisRhtr,ucHt,ucMm,ucAf,ucR,ucRdgBa,ucSmPs,ucVht,ucTxPs,ucSpeIdx,ucGid,ucPFMUIdx,ucTiBf,ucTeBf,ucTibfVht,ucTebfVht;} '
 'Wire;\n'
 'typedef Wire '
 'CMD_STAREC_COMMON_T,CMD_STAREC_AUTO_RATE_T,CMD_STAREC_AUTO_RATE_CFG_T,CMD_STAREC_AUTO_RATE_UPDATE_T,CMD_STAREC_BF,CMD_STAREC_AMSDU_T,CMD_STAREC_BA_T,CMD_STAREC_RED_T,CMD_STAREC_TX_PROC_T,CMD_STAREC_HT_INFO_T,CMD_STAREC_VHT_INFO_T,CMD_STAREC_PS_T,CMD_WTBL_SECURITY_KEY_T,CMD_WTBL_GENERIC_T,CMD_WTBL_RX_T,CMD_WTBL_HT_T,CMD_WTBL_VHT_T,CMD_WTBL_TX_PS_T,CMD_WTBL_HDR_TRANS_T,CMD_WTBL_RDG_T,CMD_WTBL_BF_T,CMD_WTBL_SMPS_T,CMD_WTBL_SPE_T,*P_CMD_WTBL_GENERIC_TLV_T;\n'
 'typedef struct {UINT8 ucBssIndex,ucWlanIdx;UINT16 u2TotalElementNum;UINT8 '
 'ucAppendCmdTLV,ucMuarIdx,aucReserve[2];} CMD_STAREC_UPDATE_T;\n'
 'typedef struct {UINT8 ucWlanIdx,ucOperation;UINT16 u2TotalElementNum;UCHAR aucBuffer[4096];} '
 'CMD_WTBL_UPDATE_T,*P_CMD_WTBL_UPDATE_T;\n'
 'typedef struct {UINT16 u2Tag,u2Length;UCHAR aucBuffer[8192];} CMD_STAREC_WTBL_T,*P_CMD_STAREC_WTBL_T;\n'
 'struct wifi_dev {int wdev_type;};\n'
 'typedef struct {int Wcid,Operation,Direction;} ASIC_SEC_INFO;\n'
 'typedef struct {struct wifi_dev *wdev;UINT16 Aid;UCHAR '
 'Addr[6],AMsduSize,bACMBit[4],bAPSDCapablePerAC[4],bAPSDDeliverEnabledPerAC[4],MaxSPLength,MpduDensity,MaxRAmpduFactor,MmpsMode;struct '
 '{UINT16 HtCapInfo;} HTCapability;struct {UINT32 vht_cap;struct {UINT16 rx_mcs_map,tx_mcs_map;} mcs_set;} '
 'vht_cap_ie;struct {int fgETxBfCap;} rStaRecBf;int RaEntry,RaInternal;} MAC_TABLE_ENTRY;\n'
 'typedef struct {UINT8 ucBssIndex,ucWlanIdx,MuarIdx,ConnectionState,IsNewSTARec;UINT32 '
 'ConnectionType,u4EnableFeature;MAC_TABLE_ENTRY*pEntry;VOID*pRaParam;ASIC_SEC_INFO asic_sec_info;} '
 'STA_REC_CFG_T;\n'
 'typedef struct {int amsdu_cap,Sequence,BAWinSize;} BA_ORI_ENTRY;\n'
 'typedef struct {int LastIndSeq,BAWinSize;} BA_REC_ENTRY;\n'
 'typedef struct {int BssIdx,WlanIdx,MuarIdx,baDirection,BaEnable,tid;void*BaEntry;} STA_REC_BA_CFG_T;\n'
 'typedef struct {int ucBssIndex;UCHAR Bssid[6];} BSS_INFO_ARGUMENT_T;\n'
 'typedef struct {int Head;} WIFI_INFO_CLASS_T;\n'
 'typedef struct {int lock;WIFI_INFO_CLASS_T BssInfo;} WIFI_SYS_INFO_T;\n'
 'struct MCU_CTRL {int msg_lock,free_cmd_msg;};\n'
 'typedef struct _RTMP_ADAPTER {struct MCU_CTRL MCUCtrl;int OpMode;struct {struct {int ITxBfEn;} field;} '
 'unused;struct {struct {struct {int ITxBfEn;} field;} RegTransmitSetting;int ETxBfEnCond;} CommonCfg;struct '
 '{int u2PfmuId;} rStaRecBf;WIFI_SYS_INFO_T WifiSysInfo;} RTMP_ADAPTER;\n'
 'typedef struct Packet {size_t len,cap;UCHAR data[32768];} Packet,*PNDIS_PACKET;\n'
 'struct cmd_msg {void*priv;Packet*net_pkt,*retry_pkt;int sync;};\n'
 'struct _CMD_ATTRIBUTE {int dummy;};\n'
 'typedef struct {UINT32 StaRecTag,StaRecTagLen;INT32(*StaRecTagHandler)(RTMP_ADAPTER*,struct '
 'cmd_msg*,VOID*);} STAREC_HANDLE_T;\n'
 '#define SET_CMD_ATTR_MCU_DEST(a,v) ((void)(a))\n'
 '#define SET_CMD_ATTR_TYPE(a,v) ((void)(a))\n'
 '#define SET_CMD_ATTR_EXT_TYPE(a,v) ((void)(a))\n'
 '#define SET_CMD_ATTR_CTRL_FLAGS(a,v) ((void)(a))\n'
 '#define SET_CMD_ATTR_RSP_WAIT_MS_TIME(a,v) ((void)(a))\n'
 '#define SET_CMD_ATTR_RSP_EXPECT_SIZE(a,v) ((void)(a))\n'
 '#define SET_CMD_ATTR_RSP_WB_BUF_IN_CALBK(a,v) ((void)(a))\n'
 '#define SET_CMD_ATTR_RSP_HANDLER(a,v) ((void)(a))\n'
 '#define IS_CMD_MSG_NEED_SYNC_WITH_FW_FLAG_SET(m) ((m)->sync)\n'
 'FUNCTION_DECLARATIONS\n'
 'SOURCE_DEFINITIONS\n'
 'static int '
 'lock_depth,completion_end,msg_alloc,msg_free,pkt_free,wtbl_alloc,wtbl_free,sends,live_msg,live_pkt,cmd_fail_at,wtbl_fail_at,status_fail,final_header;\n'
 'static int send_results[8],send_result_count,retry_owner_kind;\n'
 'struct ObservedCommand { unsigned int bss,wlan,muar,total,append,tags[32],count; unsigned int '
 'basic_type,basic_state,ba_tid,ba_direction,ba_enable,ba_seq,ba_window,ba_amsdu; };\n'
 'static struct ObservedCommand observed[8];\n'
 'static void *tlv_owner;\n'
 'static void completion_exit(void*p){(void)p;completion_end++;}\n'
 '#define RTMP_OS_EXIT_COMPLETION(p) completion_exit(p)\n'
 '#define OS_SPIN_LOCK_IRQSAVE(p,f) do{(void)(p);(void)(f);assert(!lock_depth);lock_depth++;}while(0)\n'
 '#define OS_SPIN_UNLOCK_IRQRESTORE(p,f) '
 'do{(void)(p);(void)(f);assert(lock_depth==1);lock_depth--;}while(0)\n'
 '#define ack_done sync\n'
 'static void '
 'os_free_mem(void*p){assert(p);if(p==tlv_owner){wtbl_free++;tlv_owner=NULL;}else{msg_free++;live_msg--;}free(p);}\n'
 'static NDIS_STATUS os_alloc_mem(RTMP_ADAPTER*a,UCHAR**p,size_t '
 'n){(void)a;wtbl_alloc++;*p=NULL;if(wtbl_alloc==wtbl_fail_at)return '
 'NDIS_STATUS_RESOURCES;*p=calloc(1,n);assert(*p);tlv_owner=*p;return status_fail?NDIS_STATUS_RESOURCES:0;}\n'
 '#define os_zero_mem(p,n) memset(p,0,n)\n'
 '#define os_move_mem(d,s,n) memmove(d,s,n)\n'
 '#define NdisZeroMemory(d,n) memset(d,0,n)\n'
 'static void*tail_extend(Packet*p,size_t '
 'n){assert(p&&p->len+n<=p->cap);void*r=p->data+p->len;p->len+=n;return r;}\n'
 'static void*head_extend(Packet*p,size_t '
 'n){assert(p&&p->len+n<=p->cap);memmove(p->data+n,p->data,p->len);p->len+=n;return p->data;}\n'
 '#define OS_PKT_TAIL_BUF_EXTEND(p,n) tail_extend(p,n)\n'
 '#define OS_PKT_HEAD_BUF_EXTEND(p,n) head_extend(p,n)\n'
 'static void RTMPFreeNdisPacket(RTMP_ADAPTER*a,Packet*p){assert(a&&p);pkt_free++;live_pkt--;free(p);}\n'
 'static struct cmd_msg*AndesAllocCmdMsg(RTMP_ADAPTER*a,UINT32 '
 'size){msg_alloc++;if(msg_alloc==cmd_fail_at)return NULL;assert(size<=32768);struct '
 'cmd_msg*m=calloc(1,sizeof(*m));assert(m);m->priv=a;m->net_pkt=calloc(1,sizeof(Packet));assert(m->net_pkt);m->net_pkt->cap=size;m->retry_pkt=m->net_pkt;live_msg++;live_pkt++;if(retry_owner_kind==1)m->retry_pkt=NULL;else '
 'if(retry_owner_kind==2){m->retry_pkt=calloc(1,sizeof(Packet));assert(m->retry_pkt);live_pkt++;}return m;}\n'
 'static void AndesInitCmdMsg(struct cmd_msg*m,struct _CMD_ATTRIBUTE a){(void)a;m->sync=1;}\n'
 'static void StaRecAutoRateParamSet(int*a,Wire*b){(void)a;b->u2Tag=STA_REC_RA;b->u2Length=sizeof(*b);}\n'
 'static void '
 'StaRecAutoRateUpdate(int*a,int*b,void*c,Wire*d){(void)a;(void)b;assert(c);d->u2Tag=STA_REC_RA_UPDATE;d->u2Length=sizeof(*d);}\n'
 'static void '
 'StaRecBfUpdate(MAC_TABLE_ENTRY*a,Wire*b){assert(a);b->u2Tag=STA_REC_BF;b->u2Length=sizeof(*b);}\n'
 'static void fill_wtbl_key_info_struc(ASIC_SEC_INFO*a,Wire*b){(void)a;(void)b;}\n'
 'static INT32 AndesSendCmdMsg(RTMP_ADAPTER*a,struct cmd_msg*m);\n')
SUFFIX = ('\n'
 '\n'
 'static INT32 AndesSendCmdMsg(RTMP_ADAPTER*a,struct cmd_msg*m) {\n'
 ' assert(a&&m&&m->net_pkt&&sends<8);\n'
 ' CMD_STAREC_UPDATE_T '
 'h;assert(m->net_pkt->len>=sizeof(h));memcpy(&h,m->net_pkt->data,sizeof(h));final_header=h.u2TotalElementNum;\n'
 ' struct ObservedCommand '
 '*o=&observed[sends];o->bss=h.ucBssIndex;o->wlan=h.ucWlanIdx;o->muar=h.ucMuarIdx;o->total=h.u2TotalElementNum;o->append=h.ucAppendCmdTLV;\n'
 ' size_t position=sizeof(h);\n'
 ' while(position<m->net_pkt->len) {\n'
 '  UINT16 '
 'tag,length;assert(position+4<=m->net_pkt->len);memcpy(&tag,m->net_pkt->data+position,2);memcpy(&length,m->net_pkt->data+position+2,2);\n'
 '  assert(length>=4&&position+length<=m->net_pkt->len&&o->count<32);o->tags[o->count++]=tag;\n'
 '  if(tag==STA_REC_BASIC_STA_RECORD){Wire '
 'w;assert(length==sizeof(w));memcpy(&w,m->net_pkt->data+position,sizeof(w));o->basic_type=w.u4ConnectionType;o->basic_state=w.ucConnectionState;}\n'
 '  if(tag==STA_REC_BA){Wire '
 'w;assert(length==sizeof(w));memcpy(&w,m->net_pkt->data+position,sizeof(w));o->ba_tid=w.ucTid;o->ba_direction=w.ucBaDirection;o->ba_enable=w.ucBaEenable;o->ba_seq=w.u2BaStartSeq;o->ba_window=w.u2BaWinSize;o->ba_amsdu=w.ucAmsduCap;}\n'
 '  position+=length;\n'
 ' }\n'
 ' assert(position==m->net_pkt->len&&o->count==h.u2TotalElementNum);\n'
 ' int result=sends<send_result_count?send_results[sends]:0;sends++;AndesForceFreeCmdMsg(m);return result;\n'
 '}\n'
 'static void print_observed_commands(void) {\n'
 ' printf("[");\n'
 ' for(int i=0;i<sends;i++) {\n'
 '  struct ObservedCommand *o=&observed[i];\n'
 '  printf("%s[%u,%u,%u,%u,%u,[",i?",":"",o->bss,o->wlan,o->muar,o->total,o->append);\n'
 '  for(unsigned int j=0;j<o->count;j++)printf("%s%u",j?",":"",o->tags[j]);\n'
 '  '
 'printf("],[%u,%u],[%u,%u,%u,%u,%u,%u]]",o->basic_type,o->basic_state,o->ba_tid,o->ba_direction,o->ba_enable,o->ba_seq,o->ba_window,o->ba_amsdu);\n'
 ' }\n'
 ' printf("]");\n'
 '}\n'
 'static INT32 fault_builder(RTMP_ADAPTER*a,struct cmd_msg*m,VOID*p){(void)a;(void)m;(void)p;return 5;}\n'
 'int main(int argc,char**argv){if(argc!=2)return 90;const char*name=argv[1];CASE_ADMISSION\n'
 ' RTMP_ADAPTER ad={0};struct wifi_dev w={WDEV_TYPE_AP};MAC_TABLE_ENTRY '
 'entry={0};entry.wdev=&w;STA_REC_CFG_T cfg={0};int '
 'ra=1;cfg.pEntry=&entry;cfg.pRaParam=&ra;cfg.ConnectionType=2;cfg.ConnectionState=STATE_CONNECTED;cfg.u4EnableFeature=(1U<<STA_REC_BASIC_STA_RECORD)|(1U<<STA_REC_TX_PROC)|(1U<<STA_REC_WTBL);ad.rStaRecBf.u2PfmuId=1;\n'
 ' if(!strcmp(name,"cmd-oom")||!strcmp(name,"resync-oom")||!strcmp(name,"ba-oom"))cmd_fail_at=1;\n'
 ' if(!strcmp(name,"wtbl-oom"))wtbl_fail_at=1;\n'
 ' if(!strcmp(name,"forcefree-no-retry"))retry_owner_kind=1;\n'
 ' if(!strcmp(name,"forcefree-distinct-retry"))retry_owner_kind=2;\n'
 ' if(!strcmp(name,"wtbl-status-fail"))status_fail=1;\n'
 ' if(!strcmp(name,"missing-entry"))cfg.pEntry=NULL;\n'
 ' if(!strcmp(name,"missing-wdev"))entry.wdev=NULL;\n'
 ' if(!strcmp(name,"bcmc")){cfg.ConnectionType=CONNECTION_INFRA_BC;cfg.pEntry=NULL;}\n'
 ' if(!strcmp(name,"null-handler"))cfg.u4EnableFeature|=1U<<STA_REC_BA;\n'
 ' if(!strcmp(name,"unknown-feature"))cfg.u4EnableFeature|=1U<<31;\n'
 ' '
 'if(!strcmp(name,"ra-reject")){cfg.u4EnableFeature=(1U<<STA_REC_BASIC_STA_RECORD)|(1U<<STA_REC_RA);cfg.pEntry=NULL;}\n'
 ' const char*extra[]={"ra-ok","ra-update-ok","bf-ok","amsdu-ok","ht-ok","vht-ok","ap-ps-ok","key-ok"};int '
 'tags[]={STA_REC_RA,STA_REC_RA_UPDATE,STA_REC_BF,STA_REC_AMSDU,STA_REC_BASIC_HT_INFO,STA_REC_BASIC_VHT_INFO,STA_REC_AP_PS,STA_REC_INSTALL_KEY};for(int '
 'i=0;i<8;i++)if(!strcmp(name,extra[i]))cfg.u4EnableFeature|=1U<<tags[i];\n'
 ' if(!strcmp(name,"all-selected"))for(int i=0;i<8;i++)cfg.u4EnableFeature|=1U<<tags[i];\n'
 ' '
 'if(!strcmp(name,"fw-retry-ok")||!strcmp(name,"retry-cmd-oom")||!strcmp(name,"retry-wtbl-oom")){send_results[0]=5;send_result_count=3;}\n'
 ' if(!strcmp(name,"retry-cmd-oom"))cmd_fail_at=3;\n'
 ' if(!strcmp(name,"retry-wtbl-oom"))wtbl_fail_at=2;\n'
 ' if(!strcmp(name,"fw-fail")){for(int i=0;i<8;i++)send_results[i]=i%2?0:5;send_result_count=8;}\n'
 ' if(!strcmp(name,"resync-fail")){for(int i=0;i<8;i++)send_results[i]=5;send_result_count=8;}\n'
 ' INT32 result;\n'
 ' '
 'if(!strncmp(name,"resync-",7)&&strcmp(name,"resync-fail")){if(!strcmp(name,"resync-builder-fail"))StaRecHandle[0].StaRecTagHandler=fault_builder;result=CmdExtStaRecUpdate_ReSyncDelete(&ad,!strcmp(name,"resync-null")?NULL:&cfg);}\n'
 ' else if(!strncmp(name,"ba-",3)){BA_ORI_ENTRY ori={1,0xabc,64};BA_REC_ENTRY '
 'rec={0x321,32};STA_REC_BA_CFG_T '
 'b={0};b.baDirection=!strncmp(name,"ba-rcv",6)?RCV_BA:ORI_BA;b.BaEntry=b.baDirection==ORI_BA?(void*)&ori:(void*)&rec;b.BssIdx=b.baDirection==ORI_BA?3:4;b.WlanIdx=b.baDirection==ORI_BA?17:18;b.MuarIdx=b.baDirection==ORI_BA?9:10;b.tid=b.baDirection==ORI_BA?5:6;b.BaEnable=strstr(name,"disable")?0:1<<b.tid;if(!strcmp(name,"ba-invalid"))b.baDirection=0;if(!strcmp(name,"ba-null"))b.BaEntry=NULL;result=CmdExtStaRecBaUpdate(&ad,b);}\n'
 ' else result=CmdExtStaRecUpdate(&ad,cfg);\n'
 ' '
 'printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,",result,msg_alloc,msg_free,pkt_free,wtbl_alloc,wtbl_free,sends,live_msg,live_pkt,completion_end,final_header);print_observed_commands();printf("]\\n");assert(!tlv_owner&&!lock_depth&&!live_msg&&!live_pkt);return '
 '0;}\n')

def function(text,name):
 pattern=r'(?m)^[\w \t*]+\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
 hits=list(re.finditer(pattern,text))
 if len(hits)!=1:raise ValueError('Function missing/ambiguous: '+name)
 start=hits[0].start();pos=hits[0].end();depth=1
 # Production bodies contain no braces in strings relevant to these boundaries.
 state='code';quote=''
 while pos<len(text)and depth:
  c=text[pos];n=text[pos:pos+2]
  if state=='code':
   if n=='/*':state='comment';pos+=2;continue
   if n=='//':state='line';pos+=2;continue
   if c in ('"',"'"):state='quote';quote=c
   elif c=='{':depth+=1
   elif c=='}':depth-=1
  elif state=='comment'and n=='*/':state='code';pos+=2;continue
  elif state=='line'and c=='\n':state='code'
  elif state=='quote':
   if c=='\\':pos+=2;continue
   if c==quote:state='code'
  pos+=1
 if depth:raise ValueError('Unbalanced function '+name)
 return text[start:pos]

def table(text):
 p=re.search(r'(?ms)^static STAREC_HANDLE_T StaRecHandle\[\] = \{.*?^\};',text)
 if not p:raise ValueError('Actual station TLV table absent')
 return p.group()

def source_declarations(texts):
 result={}
 for pattern,key in SOURCE_DECLARATIONS.items():
  rows=list(re.finditer(pattern,texts[key],re.M))
  if len(rows)!=1:raise ValueError('Source declaration missing/ambiguous: '+pattern)
  result[pattern]={'source':key,'sha256':hashlib.sha256(rows[0].group().encode()).hexdigest()}
 return result

def function_manifest(texts):return{n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}
def source_only_function_manifest(texts):return{n:hashlib.sha256(function(texts[k],n).encode()).hexdigest()for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
def generate_source(texts,variant='current'):
 if variant!='current'or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current TLV source set required')
 source_declarations(texts);source_only_function_manifest(texts)
 bodies=[]
 for n in BODY_ORDER:
  bodies.append(function(texts[FUNCTION_SOURCES[n]],n))
 admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
 declarations='\n'.join(re.search(pattern,texts[key],re.M).group()for pattern,key in SOURCE_DECLARATIONS.items())
 prototypes='\n'.join(function(texts[k],n).split('{',1)[0].strip()+';'for n,k in FUNCTION_SOURCES.items())
 return PREFIX.replace('FUNCTION_DECLARATIONS',prototypes).replace('SOURCE_DEFINITIONS',declarations)+'\n'.join(bodies)+SUFFIX.replace('CASE_ADMISSION',admission)
