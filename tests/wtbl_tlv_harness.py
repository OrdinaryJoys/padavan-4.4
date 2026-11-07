"""Whole WTBL builder/validator/callback and packet/msg allocator.

Transport, packet allocation, logging and firmware responses are inert seams.
The real AndesSendCmdMsg is executed separately by dma_command_harness.
"""
import hashlib
import re

SOURCE_PATHS = {
    'fw': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/mcu/fw_cmd.c',
    'core': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mcu/andes_core.c',
    'header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/mcu/mt_cmd.h',
    'os': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/os/rt_linux.h',
    'asic': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/hw_ctrl/cmm_asic_mt.h',
}
FUNCTION_SOURCES = {'AndesAllocCmdMsg': 'core', 'AndesAppendCmdMsg': 'core',
                    'wtbl_tlv_size': 'fw', 'wtbl_tlv_validate': 'fw',
                    'CmdExtWtblUpdateCb': 'fw', 'CmdExtWtblUpdate': 'fw'}
BODY_ORDER = ('AndesAllocCmdMsg', 'AndesAppendCmdMsg', 'wtbl_tlv_size',
              'wtbl_tlv_validate', 'CmdExtWtblUpdateCb', 'CmdExtWtblUpdate')
SOURCE_ONLY_FUNCTION_SOURCES = {'AndesInitCmdMsg': 'core', 'AndesSendCmdMsg': 'core',
                              'AndesForceFreeCmdMsg': 'core', 'WtblDwQuery': 'fw'}
SOURCE_DECLARATIONS = {
    'header': (
        ('enum WTBL_TLV {', '} CMD_WTBL_DUMP_T, *P_CMD_WTBL_DUMP_T;'),
        ('typedef struct GNU_PACKED _EVENT_EXT_CMD_RESULT_T {', '} EVENT_EXT_CMD_RESULT_T, *PEVENT_EXT_CMD_RESULT_T;'),
        ('#define SET_CMD_ATTR_MCU_DEST', '/* CMD ATTRIBUTE ctrl flags related Macro */'),
    ),
}
SOURCE_ENUM_NAMES = ('HOST2N9', 'EXT_CID', 'EXT_CMD_ID_WTBL_UPDATE', 'INIT_CMD_SET_AND_WAIT_RETRY_RSP')
SOURCE_ENUMS = {'header': SOURCE_ENUM_NAMES, 'asic': ('BA_SESSION_RECP',)}
SOURCE_MACRO_NAMES = ('MAC_ADDR_LEN', 'NDIS_STATUS_SUCCESS', 'NDIS_STATUS_FAILURE',
                      'NDIS_STATUS_INVALID_DATA', 'NDIS_STATUS_RESOURCES')
SOURCE_FRAGMENTS = {'header': ('\tUINT32\t\twtbl_rsp_capacity;',)}
MODEL_VARIANT = {
    'six_whole_functions_executed': True,
    'actual_WTBL_packed_declarations_and_constants_extracted': True,
    'kernel_cmd_msg_packet_scheduler_firmware_and_DMA_are_not_executed': True,
    'whole_transport_status_verified_separately_by_dma_command_harness': True,
    'query_response_prefix_is_existing_contract_not_hardware_ABI_proof': True,
    'short_query_ACK_callback_semantics_not_transport_delivery_claim': True,
    'allocator_seam_uses_memcpy_to_avoid_model_only_pointer_aliasing': True,
    'MIPS_little_endian_shipping_layout_requires_target_object_binding': True,
    'synthetic_big_endian_is_not_a_real_big_endian_ABI_test': True,
}
TAG_SIZES = (20, 12, 8, 8, 8, 8, 8, 44, 28, 8, 8, 8, 12, 8, 16, 260, 8)
FIELDS = ('ret', 'alloc_length', 'packets', 'msgs', 'sends', 'wire_len', 'elements',
          'capacity', 'expect', 'changed', 'live_packets', 'live_msgs', 'errors')
CASE_NAMES = (
    'tag-0', 'tag-1', 'tag-2', 'tag-3', 'tag-4', 'tag-5', 'tag-6', 'tag-7',
    'tag-8', 'tag-9', 'tag-10', 'tag-11', 'tag-12', 'tag-13', 'tag-14', 'tag-15', 'tag-16',
    'reset-set-empty', 'reset-all-empty', 'query-generic', 'query-dump', 'query-multi',
    'query-duplicate-raw', 'set-fw-error', 'no-response', 'wrong-cid',
    'query-short', 'query-long', 'query-wrong-tag', 'query-wrong-size',
    'query-ack-zero', 'query-ack-error', 'query-expect-overwrite',
    'bad-operation', 'null-adapter', 'null-set', 'null-nonzero', 'reset-payload',
    'zero-buffer', 'short-header', 'zero-tlv-length', 'wrong-tlv-size', 'unknown-tag',
    'over-capacity', 'length-overflow', 'packet-oom', 'msg-oom', 'max-payload', 'query-max-payload', 'snapshot-copy',
)
EXPECTED_ROWS = {'tag-0': {'ret': 0,
           'alloc_length': 28,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 28,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-1': {'ret': 0,
           'alloc_length': 20,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 20,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-2': {'ret': 0,
           'alloc_length': 16,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 16,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-3': {'ret': 0,
           'alloc_length': 16,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 16,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-4': {'ret': 0,
           'alloc_length': 16,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 16,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-5': {'ret': 0,
           'alloc_length': 16,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 16,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-6': {'ret': 0,
           'alloc_length': 16,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 16,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-7': {'ret': 0,
           'alloc_length': 52,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 52,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-8': {'ret': 0,
           'alloc_length': 36,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 36,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-9': {'ret': 0,
           'alloc_length': 16,
           'packets': 1,
           'msgs': 1,
           'sends': 1,
           'wire_len': 16,
           'elements': 1,
           'capacity': 0,
           'expect': 8,
           'changed': 0,
           'live_packets': 0,
           'live_msgs': 0,
           'errors': 0},
 'tag-10': {'ret': 0,
            'alloc_length': 16,
            'packets': 1,
            'msgs': 1,
            'sends': 1,
            'wire_len': 16,
            'elements': 1,
            'capacity': 0,
            'expect': 8,
            'changed': 0,
            'live_packets': 0,
            'live_msgs': 0,
            'errors': 0},
 'tag-11': {'ret': 0,
            'alloc_length': 16,
            'packets': 1,
            'msgs': 1,
            'sends': 1,
            'wire_len': 16,
            'elements': 1,
            'capacity': 0,
            'expect': 8,
            'changed': 0,
            'live_packets': 0,
            'live_msgs': 0,
            'errors': 0},
 'tag-12': {'ret': 0,
            'alloc_length': 20,
            'packets': 1,
            'msgs': 1,
            'sends': 1,
            'wire_len': 20,
            'elements': 1,
            'capacity': 0,
            'expect': 8,
            'changed': 0,
            'live_packets': 0,
            'live_msgs': 0,
            'errors': 0},
 'tag-13': {'ret': 0,
            'alloc_length': 16,
            'packets': 1,
            'msgs': 1,
            'sends': 1,
            'wire_len': 16,
            'elements': 1,
            'capacity': 0,
            'expect': 8,
            'changed': 0,
            'live_packets': 0,
            'live_msgs': 0,
            'errors': 0},
 'tag-14': {'ret': 0,
            'alloc_length': 24,
            'packets': 1,
            'msgs': 1,
            'sends': 1,
            'wire_len': 24,
            'elements': 1,
            'capacity': 0,
            'expect': 8,
            'changed': 0,
            'live_packets': 0,
            'live_msgs': 0,
            'errors': 0},
 'tag-15': {'ret': 0,
            'alloc_length': 268,
            'packets': 1,
            'msgs': 1,
            'sends': 1,
            'wire_len': 268,
            'elements': 1,
            'capacity': 0,
            'expect': 8,
            'changed': 0,
            'live_packets': 0,
            'live_msgs': 0,
            'errors': 0},
 'tag-16': {'ret': 0,
            'alloc_length': 16,
            'packets': 1,
            'msgs': 1,
            'sends': 1,
            'wire_len': 16,
            'elements': 1,
            'capacity': 0,
            'expect': 8,
            'changed': 0,
            'live_packets': 0,
            'live_msgs': 0,
            'errors': 0},
 'reset-set-empty': {'ret': 0,
                     'alloc_length': 8,
                     'packets': 1,
                     'msgs': 1,
                     'sends': 1,
                     'wire_len': 8,
                     'elements': 0,
                     'capacity': 0,
                     'expect': 8,
                     'changed': 0,
                     'live_packets': 0,
                     'live_msgs': 0,
                     'errors': 0},
 'reset-all-empty': {'ret': 0,
                     'alloc_length': 8,
                     'packets': 1,
                     'msgs': 1,
                     'sends': 1,
                     'wire_len': 8,
                     'elements': 0,
                     'capacity': 0,
                     'expect': 8,
                     'changed': 0,
                     'live_packets': 0,
                     'live_msgs': 0,
                     'errors': 0},
 'query-generic': {'ret': 0,
                   'alloc_length': 28,
                   'packets': 1,
                   'msgs': 1,
                   'sends': 1,
                   'wire_len': 28,
                   'elements': 1,
                   'capacity': 20,
                   'expect': 48,
                   'changed': 1,
                   'live_packets': 0,
                   'live_msgs': 0,
                   'errors': 0},
 'query-dump': {'ret': 0,
                'alloc_length': 268,
                'packets': 1,
                'msgs': 1,
                'sends': 1,
                'wire_len': 268,
                'elements': 1,
                'capacity': 260,
                'expect': 288,
                'changed': 1,
                'live_packets': 0,
                'live_msgs': 0,
                'errors': 0},
 'query-multi': {'ret': 0,
                 'alloc_length': 40,
                 'packets': 1,
                 'msgs': 1,
                 'sends': 1,
                 'wire_len': 40,
                 'elements': 2,
                 'capacity': 32,
                 'expect': 60,
                 'changed': 1,
                 'live_packets': 0,
                 'live_msgs': 0,
                 'errors': 0},
 'query-duplicate-raw': {'ret': 0,
                         'alloc_length': 40,
                         'packets': 1,
                         'msgs': 1,
                         'sends': 1,
                         'wire_len': 40,
                         'elements': 2,
                         'capacity': 32,
                         'expect': 60,
                         'changed': 1,
                         'live_packets': 0,
                         'live_msgs': 0,
                         'errors': 0},
 'set-fw-error': {'ret': 5,
                  'alloc_length': 28,
                  'packets': 1,
                  'msgs': 1,
                  'sends': 1,
                  'wire_len': 28,
                  'elements': 1,
                  'capacity': 0,
                  'expect': 8,
                  'changed': 0,
                  'live_packets': 0,
                  'live_msgs': 0,
                  'errors': 0},
 'no-response': {'ret': 1,
                 'alloc_length': 28,
                 'packets': 1,
                 'msgs': 1,
                 'sends': 1,
                 'wire_len': 28,
                 'elements': 1,
                 'capacity': 0,
                 'expect': 8,
                 'changed': 0,
                 'live_packets': 0,
                 'live_msgs': 0,
                 'errors': 0},
 'wrong-cid': {'ret': 2,
               'alloc_length': 28,
               'packets': 1,
               'msgs': 1,
               'sends': 1,
               'wire_len': 28,
               'elements': 1,
               'capacity': 0,
               'expect': 8,
               'changed': 0,
               'live_packets': 0,
               'live_msgs': 0,
               'errors': 0},
 'query-short': {'ret': 2,
                 'alloc_length': 28,
                 'packets': 1,
                 'msgs': 1,
                 'sends': 1,
                 'wire_len': 28,
                 'elements': 1,
                 'capacity': 20,
                 'expect': 48,
                 'changed': 0,
                 'live_packets': 0,
                 'live_msgs': 0,
                 'errors': 0},
 'query-long': {'ret': 2,
                'alloc_length': 28,
                'packets': 1,
                'msgs': 1,
                'sends': 1,
                'wire_len': 28,
                'elements': 1,
                'capacity': 20,
                'expect': 48,
                'changed': 0,
                'live_packets': 0,
                'live_msgs': 0,
                'errors': 0},
 'query-wrong-tag': {'ret': 2,
                     'alloc_length': 16,
                     'packets': 1,
                     'msgs': 1,
                     'sends': 1,
                     'wire_len': 16,
                     'elements': 1,
                     'capacity': 8,
                     'expect': 36,
                     'changed': 0,
                     'live_packets': 0,
                     'live_msgs': 0,
                     'errors': 0},
 'query-wrong-size': {'ret': 2,
                      'alloc_length': 28,
                      'packets': 1,
                      'msgs': 1,
                      'sends': 1,
                      'wire_len': 28,
                      'elements': 1,
                      'capacity': 20,
                      'expect': 48,
                      'changed': 0,
                      'live_packets': 0,
                      'live_msgs': 0,
                      'errors': 0},
 'query-ack-zero': {'ret': 2,
                    'alloc_length': 28,
                    'packets': 1,
                    'msgs': 1,
                    'sends': 1,
                    'wire_len': 28,
                    'elements': 1,
                    'capacity': 20,
                    'expect': 48,
                    'changed': 0,
                    'live_packets': 0,
                    'live_msgs': 0,
                    'errors': 0},
 'query-ack-error': {'ret': 5,
                     'alloc_length': 28,
                     'packets': 1,
                     'msgs': 1,
                     'sends': 1,
                     'wire_len': 28,
                     'elements': 1,
                     'capacity': 20,
                     'expect': 48,
                     'changed': 0,
                     'live_packets': 0,
                     'live_msgs': 0,
                     'errors': 0},
 'query-expect-overwrite': {'ret': 0,
                            'alloc_length': 28,
                            'packets': 1,
                            'msgs': 1,
                            'sends': 1,
                            'wire_len': 28,
                            'elements': 1,
                            'capacity': 20,
                            'expect': 48,
                            'changed': 1,
                            'live_packets': 0,
                            'live_msgs': 0,
                            'errors': 0},
 'bad-operation': {'ret': 2,
                   'alloc_length': 0,
                   'packets': 0,
                   'msgs': 0,
                   'sends': 0,
                   'wire_len': 0,
                   'elements': 0,
                   'capacity': 0,
                   'expect': 0,
                   'changed': 0,
                   'live_packets': 0,
                   'live_msgs': 0,
                   'errors': 0},
 'null-adapter': {'ret': 2,
                  'alloc_length': 0,
                  'packets': 0,
                  'msgs': 0,
                  'sends': 0,
                  'wire_len': 0,
                  'elements': 0,
                  'capacity': 0,
                  'expect': 0,
                  'changed': 0,
                  'live_packets': 0,
                  'live_msgs': 0,
                  'errors': 0},
 'null-set': {'ret': 2,
              'alloc_length': 0,
              'packets': 0,
              'msgs': 0,
              'sends': 0,
              'wire_len': 0,
              'elements': 0,
              'capacity': 0,
              'expect': 0,
              'changed': 0,
              'live_packets': 0,
              'live_msgs': 0,
              'errors': 0},
 'null-nonzero': {'ret': 2,
                  'alloc_length': 0,
                  'packets': 0,
                  'msgs': 0,
                  'sends': 0,
                  'wire_len': 0,
                  'elements': 0,
                  'capacity': 0,
                  'expect': 0,
                  'changed': 0,
                  'live_packets': 0,
                  'live_msgs': 0,
                  'errors': 0},
 'reset-payload': {'ret': 2,
                   'alloc_length': 0,
                   'packets': 0,
                   'msgs': 0,
                   'sends': 0,
                   'wire_len': 0,
                   'elements': 0,
                   'capacity': 0,
                   'expect': 0,
                   'changed': 0,
                   'live_packets': 0,
                   'live_msgs': 0,
                   'errors': 0},
 'zero-buffer': {'ret': 2,
                 'alloc_length': 0,
                 'packets': 0,
                 'msgs': 0,
                 'sends': 0,
                 'wire_len': 0,
                 'elements': 0,
                 'capacity': 0,
                 'expect': 0,
                 'changed': 0,
                 'live_packets': 0,
                 'live_msgs': 0,
                 'errors': 0},
 'short-header': {'ret': 2,
                  'alloc_length': 0,
                  'packets': 0,
                  'msgs': 0,
                  'sends': 0,
                  'wire_len': 0,
                  'elements': 0,
                  'capacity': 0,
                  'expect': 0,
                  'changed': 0,
                  'live_packets': 0,
                  'live_msgs': 0,
                  'errors': 0},
 'zero-tlv-length': {'ret': 2,
                     'alloc_length': 0,
                     'packets': 0,
                     'msgs': 0,
                     'sends': 0,
                     'wire_len': 0,
                     'elements': 0,
                     'capacity': 0,
                     'expect': 0,
                     'changed': 0,
                     'live_packets': 0,
                     'live_msgs': 0,
                     'errors': 0},
 'wrong-tlv-size': {'ret': 2,
                    'alloc_length': 0,
                    'packets': 0,
                    'msgs': 0,
                    'sends': 0,
                    'wire_len': 0,
                    'elements': 0,
                    'capacity': 0,
                    'expect': 0,
                    'changed': 0,
                    'live_packets': 0,
                    'live_msgs': 0,
                    'errors': 0},
 'unknown-tag': {'ret': 2,
                 'alloc_length': 0,
                 'packets': 0,
                 'msgs': 0,
                 'sends': 0,
                 'wire_len': 0,
                 'elements': 0,
                 'capacity': 0,
                 'expect': 0,
                 'changed': 0,
                 'live_packets': 0,
                 'live_msgs': 0,
                 'errors': 0},
 'over-capacity': {'ret': 2,
                   'alloc_length': 0,
                   'packets': 0,
                   'msgs': 0,
                   'sends': 0,
                   'wire_len': 0,
                   'elements': 0,
                   'capacity': 0,
                   'expect': 0,
                   'changed': 0,
                   'live_packets': 0,
                   'live_msgs': 0,
                   'errors': 0},
 'length-overflow': {'ret': 2,
                     'alloc_length': 0,
                     'packets': 0,
                     'msgs': 0,
                     'sends': 0,
                     'wire_len': 0,
                     'elements': 0,
                     'capacity': 0,
                     'expect': 0,
                     'changed': 0,
                     'live_packets': 0,
                     'live_msgs': 0,
                     'errors': 0},
 'packet-oom': {'ret': 3,
                'alloc_length': 28,
                'packets': 0,
                'msgs': 0,
                'sends': 0,
                'wire_len': 0,
                'elements': 0,
                'capacity': 0,
                'expect': 0,
                'changed': 0,
                'live_packets': 0,
                'live_msgs': 0,
                'errors': 0},
 'msg-oom': {'ret': 3,
             'alloc_length': 28,
             'packets': 1,
             'msgs': 0,
             'sends': 0,
             'wire_len': 0,
             'elements': 0,
             'capacity': 0,
             'expect': 0,
             'changed': 0,
             'live_packets': 0,
             'live_msgs': 0,
             'errors': 0},
 'max-payload': {'ret': 0,
                 'alloc_length': 312,
                 'packets': 1,
                 'msgs': 1,
                 'sends': 1,
                 'wire_len': 312,
                 'elements': 38,
                 'capacity': 0,
                 'expect': 8,
                 'changed': 0,
                 'live_packets': 0,
                 'live_msgs': 0,
                 'errors': 0},
 'query-max-payload': {'ret': 0,
                       'alloc_length': 312,
                       'packets': 1,
                       'msgs': 1,
                       'sends': 1,
                       'wire_len': 312,
                       'elements': 38,
                       'capacity': 304,
                       'expect': 332,
                       'changed': 1,
                       'live_packets': 0,
                       'live_msgs': 0,
                       'errors': 0},
 'snapshot-copy': {'ret': 0,
                   'alloc_length': 28,
                   'packets': 1,
                   'msgs': 1,
                   'sends': 1,
                   'wire_len': 28,
                   'elements': 1,
                   'capacity': 0,
                   'expect': 8,
                   'changed': 1,
                   'live_packets': 0,
                   'live_msgs': 0,
                   'errors': 0}}
PREFIX = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
typedef uint8_t UCHAR, UINT8, *PUCHAR;
typedef uint16_t UINT16; typedef uint32_t UINT32; typedef int32_t INT32;
typedef char *PCHAR; typedef void VOID; typedef int BOOLEAN;
#define TRUE 1
#define FALSE 0
#define GNU_PACKED __attribute__((packed))
#define MT7615 1
#define cpu2le16(x) ((UINT16)(x))
#define cpu2le32(x) ((UINT32)(x))
#define le2cpu16(x) ((UINT16)(x))
#define le2cpu32(x) ((UINT32)(x))
#define PRINT_MAC(x) (x)[0],(x)[1],(x)[2],(x)[3],(x)[4],(x)[5]
#define os_move_mem memcpy
#define os_zero_mem(p,n) memset(p,0,n)
static void trace_log(const char *fmt,...) { (void)fmt; }
#define MTWF_LOG(a,b,c,args) trace_log args
struct cmd_msg;
struct _CMD_ATTRIBUTE {
 int mcu_dest,type,ext_type;
 struct { int flags; UINT16 wait_ms_time,expect_size; } ctrl;
 struct { UINT32 *wb_buf_in_calbk; void (*handler)(struct cmd_msg *,char *,UINT16); } rsp;
};
typedef struct _CMD_ATTRIBUTE CMD_ATTRIBUTE;
struct packet { UCHAR data[2048]; unsigned int length,capacity,reserved; struct {struct cmd_msg *msg;} cb; };
typedef struct packet *PNDIS_PACKET;
struct cmd_msg { struct _CMD_ATTRIBUTE attr; void *priv; PNDIS_PACKET net_pkt;
 INT32 cmd_return_status; UINT32 wtbl_rsp_capacity; };
typedef struct { int cmd_header_len,cmd_padding_len; } RTMP_CHIP_CAP;
struct MCU_CTRL { int alloc_cmd_msg; };
typedef struct _RTMP_ADAPTER { void *hdev_ctrl; struct MCU_CTRL MCUCtrl; } RTMP_ADAPTER;
static const char *case_name;
static int alloc_length,packets,msgs,sends,wire_len,elements,capacity_seen,expect_seen,errors;
static int live_packets,live_msgs;
static PNDIS_PACKET retained_packet;static PUCHAR retained_msg;
static UCHAR input[512],before[512],response[600],wire[512];
static RTMP_CHIP_CAP chip_cap={16,4};
static RTMP_CHIP_CAP *hc_get_chip_cap(void *p) { (void)p; return &chip_cap; }
static int selected(const char *s) { return strcmp(case_name,s)==0; }
static PNDIS_PACKET RTMP_AllocateFragPacketBuffer(RTMP_ADAPTER *ad,int n) {
 (void)ad;alloc_length=n-chip_cap.cmd_header_len-chip_cap.cmd_padding_len;
 if(selected("packet-oom"))return NULL;
 if(n<0 || n>1024){errors++;return NULL;}
 PNDIS_PACKET p=calloc(1,sizeof(*p));if(!p)abort();p->capacity=(unsigned)n;
 packets++;live_packets++;retained_packet=p;return p;
}
static void reserve_packet(PNDIS_PACKET p,unsigned int n) {p->reserved=n;p->length=n;}
#define OS_PKT_RESERVE(p,n) reserve_packet(p,n)
#define CMD_MSG_CB(p) (&(p)->cb)
static void os_alloc_mem(void *ad,void *out,size_t n) {
 (void)ad;PUCHAR allocated=NULL;
 if(!selected("msg-oom")){allocated=malloc(n);if(!allocated)abort();memset(allocated,0xa5,n);msgs++;live_msgs++;retained_msg=allocated;}
 memcpy(out,&allocated,sizeof(allocated));
 if(allocated && selected("snapshot-copy")){UINT16 tag=1,len=12;memcpy(input+8,&tag,2);memcpy(input+10,&len,2);}
}
static void RTMPFreeNdisPacket(RTMP_ADAPTER *ad,PNDIS_PACKET p) {
 (void)ad;if(!p || live_packets<=0){errors++;return;}live_packets--;free(p);
}
static void *extend_packet(PNDIS_PACKET p,unsigned int n) {
 if(n>p->capacity || p->length>p->capacity-n){errors++;abort();}
 void *tail=p->data+p->length;p->length+=n;return tail;
}
#define OS_PKT_TAIL_BUF_EXTEND(p,n) extend_packet(p,n)
#define AndesFreeCmdMsg(msg) do { live_msgs--;free(msg); } while(0)
static void AndesInitCmdMsg(struct cmd_msg *msg,CMD_ATTRIBUTE attr) {
 msg->attr=attr;msg->cmd_return_status=1;
}
static INT32 AndesSendCmdMsg(RTMP_ADAPTER *ad,struct cmd_msg *msg);
'''
TRANSPORT = r'''
static INT32 AndesSendCmdMsg(RTMP_ADAPTER *ad,struct cmd_msg *msg) {
 int query=msg->attr.rsp.wb_buf_in_calbk!=NULL;
 sends++;wire_len=(int)(msg->net_pkt->length-msg->net_pkt->reserved);
 if(wire_len<8 || wire_len>(int)sizeof(wire)){errors++;abort();}
 memcpy(wire,msg->net_pkt->data+msg->net_pkt->reserved,(size_t)wire_len);
 memcpy(&elements,wire+2,2);
 if(memcmp(wire+8,before+8,(size_t)wire_len-8))errors++;
 capacity_seen=(int)msg->wtbl_rsp_capacity;expect_seen=msg->attr.ctrl.expect_size;
 if(msg->attr.mcu_dest!=HOST2N9 || msg->attr.type!=EXT_CID ||
    msg->attr.ext_type!=EXT_CMD_ID_WTBL_UPDATE ||
    msg->attr.ctrl.flags!=INIT_CMD_SET_AND_WAIT_RETRY_RSP)errors++;
 UINT16 length=8;memset(response,0,sizeof(response));response[0]=EXT_CMD_ID_WTBL_UPDATE;
 if(query) {
  unsigned int n=(unsigned int)(wire_len-8);
  length=(UINT16)(28+n);memcpy(response+28,wire+8,n);
  for(unsigned int offset=0;offset<n;){
   UINT16 len;memcpy(&len,response+28+offset+2,2);
   if(len<4 || len>n-offset){errors++;abort();}
   if(len>4)response[28+offset+4]=0x5a;
   offset+=len;
  }
  if(selected("query-short"))length--;
  if(selected("query-long"))length++;
  if(selected("query-wrong-tag")){UINT16 tag=3;memcpy(response+28,&tag,2);}
  if(selected("query-wrong-size")){UINT16 len=4;memcpy(response+30,&len,2);}
  if(selected("query-ack-zero")||selected("query-ack-error")) {
   memset(response,0,8);response[0]=EXT_CMD_ID_WTBL_UPDATE;length=8;
   if(selected("query-ack-error"))response[4]=5;
  }
 }
 if(selected("set-fw-error"))response[4]=5;
 if(selected("wrong-cid"))response[0]=0x33;
 if(selected("query-expect-overwrite")) {
  msg->attr.ctrl.expect_size=29; /* mutable transport state must not become capacity */
 }
 if(!selected("no-response"))msg->attr.rsp.handler(msg,(char *)response,length);
 INT32 ret=msg->cmd_return_status;
 RTMPFreeNdisPacket(ad,msg->net_pkt);live_msgs--;free(msg);return ret;
}
'''
SUFFIX = r'''
static const unsigned int tag_sizes[17]={20,12,8,8,8,8,8,44,28,8,8,8,12,8,16,260,8};
static unsigned int add_tlv(unsigned int offset,UINT16 tag) {
 UINT16 len=(UINT16)tag_sizes[tag];memcpy(input+offset,&tag,2);memcpy(input+offset+2,&len,2);
 return offset+len;
}
int main(int argc,char **argv) {
 if(argc!=2)return 91;
 case_name=argv[1];
 CASE_ADMISSION
 memset(input,0,sizeof(input));input[0]=0x11;input[511]=0x22;
 unsigned int length=add_tlv(8,0)-8;UINT8 operation=SET_WTBL;
 if(!strncmp(case_name,"tag-",4))length=add_tlv(8,(UINT16)atoi(case_name+4))-8;
 if(!strncmp(case_name,"query-",6))operation=QUERY_WTBL;
 if(selected("query-dump"))length=add_tlv(8,15)-8;
 if(selected("query-wrong-tag"))length=add_tlv(8,2)-8;
 if(selected("query-multi"))length=add_tlv(add_tlv(8,0),1)-8;
 if(selected("query-duplicate-raw"))length=add_tlv(add_tlv(8,14),14)-8;
 if(selected("max-payload")||selected("query-max-payload")) {
  unsigned int off=8;for(int i=0;i<38;i++)off=add_tlv(off,2);length=off-8;
 }
 VOID *buffer=input+8;RTMP_ADAPTER ad={0};RTMP_ADAPTER *adapter=&ad;
 if(selected("reset-set-empty")){buffer=NULL;length=0;operation=RESET_WTBL_AND_SET;}
 if(selected("reset-all-empty")){buffer=NULL;length=0;operation=RESET_ALL_WTBL;}
 if(selected("bad-operation"))operation=0;
 if(selected("null-adapter"))adapter=NULL;
 if(selected("null-set")){buffer=NULL;length=0;}
 if(selected("null-nonzero"))buffer=NULL;
 if(selected("reset-payload"))operation=RESET_ALL_WTBL;
 if(selected("zero-buffer"))length=0;
 if(selected("short-header"))length=3;
 if(selected("zero-tlv-length")){UINT16 len=0;memcpy(input+10,&len,2);}
 if(selected("wrong-tlv-size")){UINT16 len=8;memcpy(input+10,&len,2);length=8;}
 if(selected("unknown-tag")){UINT16 tag=17;memcpy(input+8,&tag,2);}
 if(selected("over-capacity"))length=305;
 if(selected("length-overflow"))length=UINT32_MAX;
 memcpy(before,input,sizeof(input));
 INT32 ret=CmdExtWtblUpdate(adapter,7,operation,buffer,length);
 int changed=memcmp(input,before,sizeof(input))!=0;
 if(input[0]!=0x11 || input[511]!=0x22)errors++;
 printf("{\"ret\":%d,\"alloc_length\":%d,\"packets\":%d,\"msgs\":%d,\"sends\":%d,\"wire_len\":%d,\"elements\":%d,\"capacity\":%d,\"expect\":%d,\"changed\":%d,\"live_packets\":%d,\"live_msgs\":%d,\"errors\":%d}\n",ret,alloc_length,packets,msgs,sends,wire_len,elements,capacity_seen,expect_seen,changed,live_packets,live_msgs,errors);
 if(live_msgs)free(retained_msg);
 if(live_packets)free(retained_packet);
 /* The fixed old early-return fixture is allowed to demonstrate, then release,
  * its private model allocations so historical regression tests are ASan clean. */
 return 0;
}
'''


def function(text, name):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked = re.sub(tokens, lambda m: ' ' * len(m.group()), text)
    found = list(re.finditer(r'(?m)^[A-Za-z_][\w \t*]*\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{', masked))
    if len(found) != 1:
        raise ValueError('Missing/ambiguous WTBL body: ' + name)
    start = found[0].start(); opening = masked.index('{', start); depth = 0
    for match in re.finditer('[{}]', masked[opening:]):
        depth += 1 if match.group() == '{' else -1
        if not depth:
            return text[start:opening + match.end()]
    raise ValueError('Unterminated WTBL body: ' + name)


def declarations(texts):
    pieces = []
    for name in SOURCE_MACRO_NAMES:
        values = re.findall(r'(?m)^#define\s+' + re.escape(name) + r'\s+[^\n]+$', texts['os'])
        if len(values) != 1:
            raise ValueError('Missing/ambiguous WTBL macro: ' + name)
        pieces.append(values[0])
    for key, names in SOURCE_ENUMS.items():
        for name in names:
            values = re.findall(r'(?m)^\s*' + re.escape(name) + r'\s*=\s*(?:0x[0-9A-Fa-f]+|[0-9]+)\s*,', texts[key])
            if len(values) != 1:
                raise ValueError('Missing/ambiguous WTBL enum: ' + name)
            pieces.append('enum {' + values[0] + '};')
    for key, spans in SOURCE_DECLARATIONS.items():
        for begin, end in spans:
            if texts[key].count(begin) != 1 or texts[key].count(end) != 1:
                raise ValueError('Missing/ambiguous WTBL declaration')
            a = texts[key].index(begin); b = texts[key].index(end, a)
            pieces.append(texts[key][a:b + len(end)])
    return '\n'.join(pieces)


def generate_source(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact WTBL source set required')
    for key, fragments in SOURCE_FRAGMENTS.items():
        for fragment in fragments:
            if texts[key].splitlines().count(fragment) != 1:
                raise ValueError('Independent WTBL capacity declaration drift')
    for n, key in SOURCE_ONLY_FUNCTION_SOURCES.items():
        function(texts[key], n)
    admission = 'if (' + ' && '.join('strcmp(case_name,"' + n + '")' for n in CASE_NAMES) + ') return 91;'
    return PREFIX + declarations(texts) + '\n' + '\n'.join(function(texts[FUNCTION_SOURCES[n]], n) for n in BODY_ORDER) + TRANSPORT + SUFFIX.replace('CASE_ADMISSION', admission)


def function_manifest(texts):
    return {n: {'source': k, 'execution': 'whole-function', 'full_body_sha256': hashlib.sha256(function(texts[k], n).encode()).hexdigest()} for n, k in FUNCTION_SOURCES.items()}


def source_only_manifest(texts):
    return {n: {'source': k, 'execution': 'source-only-not-run', 'full_body_sha256': hashlib.sha256(function(texts[k], n).encode()).hexdigest()} for n, k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
