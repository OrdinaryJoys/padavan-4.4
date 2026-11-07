"""Whole MCU send/dequeue/publication functions with private owners.

Packets, IRQ context, completions, queues and MMIO are inert host recorders.
Real pthread locks/schedules exercise selected software ownership; no kernel,
device, physical DMA or full driver concurrency is executed.
"""
import hashlib
import re
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'core':BASE+'embedded/mcu/andes_core.c','mt':BASE+'embedded/mcu/andes_mt.c',
 'os':BASE+'os/linux/rt_main_dev.c','cmd_header':BASE+'include/mcu/mt_cmd.h',
 'core_header':BASE+'embedded/include/mcu/andes_core.h',
 'os_header':BASE+'include/os/rt_linux.h','flags':BASE+'embedded/include/rtmp_def.h',
 'ring_header':BASE+'include/os/rt_linux_cmm.h'}
FUNCTION_SOURCES={'AndesTakeQueuedCmdMsg':'core','AndesFreeCmdMsg':'core','AndesForceFreeCmdMsg':'core','AndesCleanupCmdMsg':'core','AndesRejectUnpublishedCmdMsg':'core','RtmpDmaQuarantined':'os','RtmpDmaStopping':'os',
 'AndesMTPciKickOutCmdMsgOwned':'mt','AndesMTPciKickOutCmdMsg':'mt',
 'AndesMTPciKickOutCmdMsgFwDlRingOwned':'mt','AndesMTPciKickOutCmdMsgFwDlRing':'mt',
 'AndesDequeueAndKickOutCmdMsgs':'core','AndesWaitForCompleteTimeout':'core','AndesSendCmdMsg':'core'}
SOURCE_ONLY_FUNCTION_SOURCES={'AndesCtrlPciExit':'core','AndesCmdMsgBh':'core','AndesBhSchedule':'core','AndesBhScheduleOwned':'core'}
BODY_ORDER=('AndesTakeQueuedCmdMsg','AndesFreeCmdMsg','AndesForceFreeCmdMsg','AndesCleanupCmdMsg','AndesRejectUnpublishedCmdMsg','RtmpDmaQuarantined','RtmpDmaStopping','AndesMTPciKickOutCmdMsgOwned','AndesMTPciKickOutCmdMsg',
 'AndesMTPciKickOutCmdMsgFwDlRingOwned','AndesMTPciKickOutCmdMsgFwDlRing',
 'AndesDequeueAndKickOutCmdMsgs','AndesWaitForCompleteTimeout','AndesSendCmdMsg')
CASE_GROUPS={'admission': ('admit-stop-sync', 'admit-stop-async', 'irq-sync-reject', 'irq-async-ok'), 'normal': ('normal-sync-ok', 'normal-async-ok', 'normal-sync-full', 'normal-async-full'), 'firmware': ('fw-sync-ok', 'fw-async-ok', 'fw-sync-full', 'fw-async-full'), 'low-guard': ('low-stop-normal', 'low-stop-fw', 'low-nopin-normal', 'low-quarantine-fw'), 'queued-stop': ('queue-stop-sync', 'queue-stop-async', 'queue-missing-sync'), 'cross-sender': ('cross-sync-normal-fail', 'cross-async-normal-fail', 'cross-postpub-sync-fail', 'cross-postpub-async-fail', 'cross-cleanup-sync', 'cross-cleanup-async'), 'retry': ('sync-kick-error-no-retry', 'sync-clone-null', 'async-retry-kick-fail', 'force-clone-alias', 'sync-retry-fail'), 'cleanup': ('cleanup-done-sync', 'cleanup-pending-sync', 'cleanup-pending-async'), 'controller': ('normal-sync-mcu-off', 'normal-async-mcu-off', 'fw-sync-mcu-off', 'fw-async-mcu-off', 'callback-missing-sync'), 'interleaved': ('normal-kick-vs-stop', 'fw-kick-vs-stop'), 'wsys-fwack': ('wsys-dev-sync-error', 'wsys-bss-sync-error', 'wsys-sta-sync-error', 'wsys-dev-sync-noresponse'), 'wtbl-fwack': ('wsys-wtbl-sync-error', 'wsys-wtbl-sync-noresponse', 'wsys-wtbl-sync-ok')}
CASE_NAMES=('admit-stop-sync', 'admit-stop-async', 'irq-sync-reject', 'irq-async-ok', 'normal-sync-ok', 'normal-async-ok', 'normal-sync-full', 'normal-async-full', 'fw-sync-ok', 'fw-async-ok', 'fw-sync-full', 'fw-async-full', 'low-stop-normal', 'low-stop-fw', 'low-nopin-normal', 'low-quarantine-fw', 'queue-stop-sync', 'queue-stop-async', 'queue-missing-sync', 'cross-sync-normal-fail', 'cross-async-normal-fail', 'sync-kick-error-no-retry', 'normal-kick-vs-stop', 'fw-kick-vs-stop', 'sync-clone-null', 'async-retry-kick-fail', 'force-clone-alias', 'cleanup-done-sync', 'cleanup-pending-sync', 'cross-postpub-sync-fail', 'cross-postpub-async-fail', 'normal-sync-mcu-off', 'normal-async-mcu-off', 'fw-sync-mcu-off', 'fw-async-mcu-off', 'cleanup-pending-async', 'sync-retry-fail', 'cross-cleanup-sync', 'cross-cleanup-async', 'callback-missing-sync', 'wsys-dev-sync-error', 'wsys-bss-sync-error', 'wsys-sta-sync-error', 'wsys-dev-sync-noresponse', 'wsys-wtbl-sync-error', 'wsys-wtbl-sync-noresponse', 'wsys-wtbl-sync-ok')
FIELDS=('result_a','result_b','created','freed','live','wait_calls','completion_calls',
 'kick_calls','maps','writes','clones','txq','ackq','doneq','normal_index','fw_index',
 'stopping','errors','blocked_stop_seen','retry_reinitializations','before_live','before_txq','before_ackq','before_doneq','before_unqueued','packet_allocs','packet_frees','packet_live','before_packet_live','before_unowned_unmapped_packets')
EXPECTED_ROWS={'admit-stop-sync': [1, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'admit-stop-async': [1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'irq-sync-reject': [1, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'irq-async-ok': [0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0], 'normal-sync-ok': [0, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0], 'normal-async-ok': [0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0], 'normal-sync-full': [1, 0, 1, 1, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'normal-async-full': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'fw-sync-ok': [0, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0], 'fw-async-ok': [0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0], 'fw-sync-full': [1, 0, 1, 1, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'fw-async-full': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'low-stop-normal': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'low-stop-fw': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'low-nopin-normal': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'low-quarantine-fw': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'queue-stop-sync': [1, 0, 1, 1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'queue-stop-async': [1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'queue-missing-sync': [1, 0, 1, 1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'cross-sync-normal-fail': [1, 0, 2, 2, 0, 2, 4, 2, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 2, 2, 0, 1, 0], 'cross-async-normal-fail': [1, 0, 2, 2, 0, 1, 2, 2, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 2, 2, 0, 1, 0], 'sync-kick-error-no-retry': [1, 0, 1, 1, 0, 1, 2, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 0], 'normal-kick-vs-stop': [0, 1, 2, 2, 0, 0, 0, 2, 1, 1, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 2, 0, 0, 1, 1, 2, 2, 0, 2, 0], 'fw-kick-vs-stop': [0, 1, 2, 2, 0, 0, 0, 2, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 2, 0, 0, 1, 1, 2, 2, 0, 2, 0], 'sync-clone-null': [1, 0, 1, 1, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'async-retry-kick-fail': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 0], 'force-clone-alias': [0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'cleanup-done-sync': [0, 0, 1, 1, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0], 'cleanup-pending-sync': [0, 0, 1, 1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0], 'cross-postpub-sync-fail': [0, 0, 2, 2, 0, 2, 4, 2, 2, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 2, 0, 0, 2, 0, 2, 2, 0, 2, 0], 'cross-postpub-async-fail': [-1, 0, 2, 2, 0, 1, 2, 2, 2, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 2, 0, 0, 2, 0, 2, 2, 0, 2, 0], 'normal-sync-mcu-off': [1, 0, 1, 1, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'normal-async-mcu-off': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'fw-sync-mcu-off': [1, 0, 1, 1, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'fw-async-mcu-off': [1, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'cleanup-pending-async': [0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'sync-retry-fail': [1, 0, 1, 1, 0, 3, 6, 3, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 3, 3, 0, 0, 0], 'cross-cleanup-sync': [1, 0, 1, 1, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'cross-cleanup-async': [1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'callback-missing-sync': [1, 0, 1, 1, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0], 'wsys-dev-sync-error': [5, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0], 'wsys-bss-sync-error': [5, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0], 'wsys-sta-sync-error': [5, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0], 'wsys-dev-sync-noresponse': [1, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0], 'wsys-wtbl-sync-error': [5, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0], 'wsys-wtbl-sync-noresponse': [1, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0], 'wsys-wtbl-sync-ok': [0, 0, 1, 1, 0, 1, 2, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0]}
SOURCE_DECLARATIONS={
 r'^#define NDIS_STATUS_SUCCESS\s+0x[0-9a-fA-F]+\s*$':'os_header',
 r'^#define NDIS_STATUS_FAILURE\s+0x[0-9a-fA-F]+\s*$':'os_header',
 r'^#define fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD[^\n]*':'flags',
 r'^#define fRTMP_ADAPTER_NIC_NOT_EXIST[^\n]*':'flags',
 r'^#define fRTMP_ADAPTER_SUSPEND[^\n]*':'flags',
 r'^#define CMD_MSG_TIMEOUT[^\n]*':'core_header',
 r'enum cmd_msg_state \{[\s\S]*?\n\};':'cmd_header',
 r'enum \{\s*MCU_INIT,\s*MCU_TX_HALT,\s*MCU_RX_HALT,\s*\};':'core_header',
 r'^#define CTL_RING_SIZE[^\n]*':'ring_header',
 r'^#define RTMP_OS_EXIT_COMPLETION\(__pCompletion\)\s+\\\n\s+complete\(__pCompletion\)':'ring_header',
 r'^#define RTMP_OS_COMPLETE\(__pCompletion\)\s+\\\n\s+complete\(__pCompletion\)':'ring_header',
 r'^#define RTMP_OS_INIT_COMPLETION\(__pCompletion\)\s+\\\n\s+init_completion\(__pCompletion\)':'ring_header',
 r'^#define RTMP_OS_WAIT_FOR_COMPLETION_TIMEOUT\(__pCompletion, __Timeout\)\s+\\\n\s+wait_for_completion_timeout\(__pCompletion, __Timeout\)':'ring_header'}
PREFIX=r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef void VOID;typedef int INT,INT32,BOOLEAN;typedef unsigned int UINT,UINT32;
typedef unsigned long ULONG;typedef unsigned char UCHAR,UINT8;
#define TRUE 1
#define FALSE 0
#define LINUX
#define RTMP_PCI_SUPPORT
#define RTMP_MAC_PCI
#define MT7615
#define READ_ONCE(v) __atomic_load_n(&(v),__ATOMIC_ACQUIRE)
#define MEM_ALLOC_FLAG 0
#define RTMP_PCI_DMA_TODEVICE 1
#define MTWF_LOG(...) ((void)0)
#define ASSERT assert
#define EXT_CMD_STAREC_UPDATE 0x25
#define EXT_CMD_ID_BSSINFO_UPDATE 0x26
#define EXT_CMD_ID_DEVINFO_UPDATE 0x2a
#define EXT_CMD_ID_WTBL_UPDATE 0x32
SOURCE_DEFINITIONS
typedef pthread_mutex_t NDIS_SPIN_LOCK;
struct cmd_msg;
typedef struct {struct cmd_msg *items[32];int count;} DL_LIST;
typedef struct packet {unsigned char payload[16];int valid;} PACKET,*PNDIS_PACKET;
typedef struct {int unused;} PACKET_INFO;
typedef struct {int LastSec0,LastSec1,SDLen0,SDLen1;UINT32 SDPtr0;int Burst,DMADONE;} TXD_STRUC;
#define TXD_SIZE sizeof(TXD_STRUC)
typedef struct {void *AllocVa;unsigned long AllocPa;void *pNdisPacket,*pNextNdisPacket;UINT32 PacketPa;} CELL;
typedef struct {CELL Cell[CTL_RING_SIZE];UINT32 TxCpuIdx,TxDmaIdx,TxSwFreeIdx,hw_cidx_addr;
 pthread_mutex_t RingLock;} RTMP_RING,RTMP_CTRL_RING;
struct _PCI_HIF_T {RTMP_CTRL_RING CtrlRing;pthread_mutex_t CtrlRingLock;RTMP_RING FwDwloRing;};
typedef struct {pthread_mutex_t dma_state_lock;} COOKIE,*POS_COOKIE;
struct MCU_CTRL {pthread_mutex_t msg_lock;int free_cmd_msg;unsigned flags;DL_LIST txq,ackq,tx_doneq,rxq,kickq,rx_doneq;};
typedef struct _RTMP_ADAPTER {void *OS_Cookie,*hdev_ctrl;struct MCU_CTRL MCUCtrl;unsigned Flags;
 int dma_lifecycle_pinned,dma_stopping,dma_quarantined;} RTMP_ADAPTER,*PRTMP_ADAPTER;
typedef struct completion {int done;struct cmd_msg *owner;} COMPLETION;
struct cmd_msg {int id,sync;void *priv;PNDIS_PACKET net_pkt,retry_pkt;enum cmd_msg_state state;
 unsigned seq,retry_times;ULONG sending_time_in_jiffies;int cmd_return_status;
 struct {int type,ext_type;struct {ULONG wait_ms_time;} ctrl;} attr;COMPLETION ack_done;};
struct _RTMP_CHIP_OP {void (*andes_fill_cmd_header)(struct cmd_msg *,void *);
 INT32 (*pci_kick_out_cmd_msg)(RTMP_ADAPTER *,struct cmd_msg *);};
FUNCTION_DECLARATIONS
static RTMP_ADAPTER adapter;static COOKIE cookie;static struct _PCI_HIF_T hif;
static struct _RTMP_CHIP_OP ops;static TXD_STRUC descriptors[2][CTL_RING_SIZE];
static pthread_mutex_t queue_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t schedule_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t schedule_cond=PTHREAD_COND_INITIALIZER;
static int created,freed,waits,completions,kicks,maps,writes,clones,errors,reinitializations;
static int normal_free=1,firmware_free=1,irq_context,fw_mode,fail_msg_id;
static int hold_foreign,foreign_queued,foreign_release,postpub_failure,clone_fail,stop_on_kick;
static int packet_allocs,packet_frees,device_retired;static PNDIS_PACKET packets[32];static int packet_mapped[32];
static int pause_publication,publication_paused,publication_release,stop_started,blocked_stop_seen;
static struct cmd_msg *live[8];static ULONG jiffies=100;
static void alive(struct cmd_msg *msg){int i;for(i=0;i<8;i++)if(live[i]==msg)return;assert(!"use of freed/unowned message");}
static int sync_flag(struct cmd_msg *msg){alive(msg);return msg->sync;}
#define IS_CMD_MSG_NEED_SYNC_WITH_FW_FLAG_SET(m) sync_flag(m)
#define IS_PCI_INF(p) ((void)(p),0)
#define IS_PCIE_INF(p) ((void)(p),1)
#define IS_RBUS_INF(p) ((void)(p),0)
#define RTMP_TEST_FLAG(p,f) (((p)->Flags&(f))!=0)
#define OS_TEST_BIT(b,p) ((*(p)&(1u<<(b)))!=0)
static int in_interrupt(void){return irq_context;}
#define spin_lock_irqsave(p,f) do{(f)=0;assert(!pthread_mutex_lock(p));}while(0)
#define spin_unlock_irqrestore(p,f) do{(void)(f);assert(!pthread_mutex_unlock(p));}while(0)
#define RTMP_SPIN_LOCK_IRQSAVE(p,f) do{*(f)=0;assert(!pthread_mutex_lock(p));}while(0)
#define RTMP_SPIN_UNLOCK_IRQRESTORE(p,f) do{assert(*(f)==0);assert(!pthread_mutex_unlock(p));}while(0)
static struct _PCI_HIF_T *hc_get_hif_ctrl(void *p){(void)p;return &hif;}
static struct _RTMP_CHIP_OP *hc_get_chip_ops(void *p){(void)p;return &ops;}
static int normal_available(RTMP_ADAPTER *p){(void)p;return normal_free;}
static int firmware_available(RTMP_RING *p){assert(p==&hif.FwDwloRing);return firmware_free;}
#define GET_CTRLRING_FREENO(p) normal_available(p)
#define GET_FWDWLORING_FREENO(p) firmware_available(p)
static void packet_info(PNDIS_PACKET p,PACKET_INFO *info,UCHAR **out,UINT *length){
 (void)info;assert(p);*out=p->valid?p->payload:NULL;*length=sizeof(p->payload);}
#define RTMP_QueryPacketInfo(p,i,o,n) packet_info(p,i,o,n)
static UINT32 map_packet(void *p,UCHAR *data,UINT n,int a,int direction){int i;
 assert(p==&adapter&&data&&n==16&&a==0&&direction==RTMP_PCI_DMA_TODEVICE);for(i=0;i<32;i++)if(packets[i]&&packets[i]->payload==data){packet_mapped[i]=1;break;}assert(i<32);maps++;return 0x2000u;}
#define PCI_MAP_SINGLE(p,d,n,a,v) map_packet(p,d,n,a,v)
#define RTMP_DCACHE_FLUSH(a,n) ((void)(n))
#define INC_RING_INDEX(i,n) ((i)=((i)+1)%(n))
static void publication(void *p,UINT32 address,UINT32 index){assert(p==&adapter);(void)address;assert(index>0);
 assert(!pthread_mutex_lock(&schedule_lock));
 if(pause_publication){publication_paused=1;assert(!pthread_cond_broadcast(&schedule_cond));
  while(!publication_release)assert(!pthread_cond_wait(&schedule_cond,&schedule_lock));}
 assert(!pthread_mutex_unlock(&schedule_lock));writes++;}
#define HIF_IO_WRITE32(p,a,v) publication(p,a,v)
static void unlink_unlocked(DL_LIST *q,struct cmd_msg *msg){int i;
 for(i=0;i<q->count;i++)if(q->items[i]==msg){memmove(q->items+i,q->items+i+1,(q->count-i-1)*sizeof(q->items[0]));q->count--;return;}}
static void AndesUnlinkCmdMsg(struct cmd_msg *msg,DL_LIST *q){alive(msg);assert(!pthread_mutex_lock(&queue_lock));
 unlink_unlocked(q,msg);assert(!pthread_mutex_unlock(&queue_lock));}
static void append(DL_LIST *q,struct cmd_msg *msg,enum cmd_msg_state state,int head){int a,b;DL_LIST *all[]={&adapter.MCUCtrl.txq,&adapter.MCUCtrl.ackq,&adapter.MCUCtrl.tx_doneq};alive(msg);
 assert(!pthread_mutex_lock(&queue_lock));assert(q->count<32);for(a=0;a<3;a++)for(b=0;b<all[a]->count;b++)assert(all[a]->items[b]!=msg);msg->state=state;
 if(head){memmove(q->items+1,q->items,q->count*sizeof(q->items[0]));q->items[0]=msg;}
 else{q->items[q->count]=msg;}q->count++;assert(!pthread_mutex_unlock(&queue_lock));
 if(q==&adapter.MCUCtrl.txq&&hold_foreign&&msg->id==0){assert(!pthread_mutex_lock(&schedule_lock));
  foreign_queued=1;assert(!pthread_cond_broadcast(&schedule_cond));
  while(!foreign_release){assert(!pthread_cond_wait(&schedule_cond,&schedule_lock));}assert(!pthread_mutex_unlock(&schedule_lock));}}
static void AndesQueueTailCmdMsg(DL_LIST *q,struct cmd_msg *m,enum cmd_msg_state s){append(q,m,s,0);}
static void AndesQueueHeadCmdMsg(DL_LIST *q,struct cmd_msg *m,enum cmd_msg_state s){append(q,m,s,1);}
static struct cmd_msg *AndesDequeueCmdMsg(struct MCU_CTRL *ctl,DL_LIST *q){struct cmd_msg *msg=NULL;
 assert(ctl==&adapter.MCUCtrl);assert(!pthread_mutex_lock(&queue_lock));
 if(q->count){msg=q->items[0];unlink_unlocked(q,msg);}assert(!pthread_mutex_unlock(&queue_lock));return msg;}
static PNDIS_PACKET new_packet(void){int i;PNDIS_PACKET p=calloc(1,sizeof(*p));assert(p);p->valid=1;
 for(i=0;i<32;i++){if(!packets[i]){packets[i]=p;packet_mapped[i]=0;packet_allocs++;return p;}}assert(0);return NULL;}
static void RTMPFreeNdisPacket(RTMP_ADAPTER *ad,PNDIS_PACKET packet){int i;assert(ad==&adapter&&packet);
 for(i=0;i<32;i++){if(packets[i]==packet){assert(!packet_mapped[i]||device_retired);packets[i]=NULL;free(packet);packet_frees++;return;}}assert(!"packet double free");}
static void os_free_mem(struct cmd_msg *msg){int i;alive(msg);for(i=0;i<8;i++)if(live[i]==msg){live[i]=NULL;break;}free(msg);freed++;}
#define OS_SPIN_LOCK_IRQSAVE(p,f) RTMP_SPIN_LOCK_IRQSAVE(p,f)
#define OS_SPIN_UNLOCK_IRQRESTORE(p,f) RTMP_SPIN_UNLOCK_IRQRESTORE(p,f)
static NDIS_SPIN_LOCK *AndesGetSpinLock(struct MCU_CTRL *ctl,DL_LIST *q){(void)q;assert(ctl==&adapter.MCUCtrl);return &queue_lock;}
static void _AndesUnlinkCmdMsg(struct cmd_msg *msg,DL_LIST *q){alive(msg);unlink_unlocked(q,msg);}
#define DlListForEach(msg,q,type,member) for(int fixture_i=0;fixture_i<(q)->count&&(((msg)=(q)->items[fixture_i]),1);fixture_i++)
#define DlListForEachSafe(msg,tmp,q,type,member) for((msg)=((q)->count?(q)->items[0]:NULL);(msg);(msg)=((q)->count?(q)->items[0]:NULL))
#define DlListInit(q) ((q)->count=0)
static void AndesBhSchedule(RTMP_ADAPTER *p){struct cmd_msg *msg;assert(p==&adapter);if(RtmpDmaStopping(p))return;
 while((msg=AndesDequeueCmdMsg(&adapter.MCUCtrl,&adapter.MCUCtrl.tx_doneq))!=NULL){
  if(!msg->sync)AndesFreeCmdMsg(msg);else{AndesQueueHeadCmdMsg(&adapter.MCUCtrl.tx_doneq,msg,msg->state);break;}}}
static void completed(COMPLETION *done){alive(done->owner);done->done++;completions++;}
static void complete(COMPLETION *done){completed(done);}
static int response_error_code,response_valid;
static ULONG wait_for_completion_timeout(COMPLETION *done,ULONG ticks){struct cmd_msg *msg=done->owner;(void)ticks;
 alive(msg);assert(msg->sync&&!irq_context);waits++;
 if(!done->done&&msg->state==wait_ack){if(response_error_code||response_valid)msg->cmd_return_status=response_error_code;AndesUnlinkCmdMsg(msg,&adapter.MCUCtrl.ackq);completed(done);}
 if(done->done){done->done--;return 1;}return 0;}
#define RTMPMsecsToJiffies(n) (n)
static void init_completion(COMPLETION *p){alive(p->owner);p->done=0;reinitializations++;}
static void clone_packet(PNDIS_PACKET packet,PNDIS_PACKET *out){assert(packet&&!*out);if(clone_fail){*out=NULL;return;}*out=new_packet();**out=*packet;clones++;}
#define OS_PKT_CLONE(ad,p,out,f) do{(void)(ad);(void)(f);clone_packet(p,&(out));}while(0)
static unsigned AndesGetCmdMsgSeq(RTMP_ADAPTER *p){(void)p;return 7;}
static void AndesIncErrorCount(struct MCU_CTRL *ctl,int error){(void)ctl;(void)error;errors++;}
#define error_tx_timeout_fail 1
static INT32 selected_kick(RTMP_ADAPTER *p,struct cmd_msg *msg){alive(msg);kicks++;
 if(msg->id==fail_msg_id&&!postpub_failure){if(stop_on_kick){assert(!pthread_mutex_lock(&cookie.dma_state_lock));adapter.dma_stopping=1;assert(!pthread_mutex_unlock(&cookie.dma_state_lock));}return NDIS_STATUS_FAILURE;}
 {INT32 ret=fw_mode?AndesMTPciKickOutCmdMsgFwDlRing(p,msg):AndesMTPciKickOutCmdMsg(p,msg);return msg->id==fail_msg_id&&postpub_failure?-1:ret;}}
'''
SUFFIX=r'''
static struct cmd_msg *new_msg(int id,int sync){struct cmd_msg *m=calloc(1,sizeof(*m));assert(m&&id<8&&!live[id]);
 m->id=id;m->sync=sync;m->priv=&adapter;m->retry_times=1;m->ack_done.owner=m;
 m->net_pkt=new_packet();live[id]=m;created++;return m;}
static void fixture_init(void){int i,j;assert(!pthread_mutex_init(&cookie.dma_state_lock,NULL));
 assert(!pthread_mutex_init(&hif.CtrlRingLock,NULL));assert(!pthread_mutex_init(&hif.FwDwloRing.RingLock,NULL));
 assert(!pthread_mutex_init(&adapter.MCUCtrl.msg_lock,NULL));adapter.OS_Cookie=&cookie;adapter.dma_lifecycle_pinned=1;adapter.Flags=fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD;
 adapter.MCUCtrl.flags=1u<<MCU_INIT;ops.pci_kick_out_cmd_msg=selected_kick;fail_msg_id=-1;
 for(i=0;i<2;i++)for(j=0;j<CTL_RING_SIZE;j++)(i?&hif.FwDwloRing:&hif.CtrlRing)->Cell[j].AllocVa=&descriptors[i][j];}
static void cleanup(void){struct cmd_msg *msg;DL_LIST *qs[]={&adapter.MCUCtrl.txq,&adapter.MCUCtrl.ackq,&adapter.MCUCtrl.tx_doneq};int i;
 for(i=0;i<3;i++)AndesCleanupCmdMsg(&adapter,qs[i]);
 device_retired=1;for(i=0;i<8;i++)if(live[i])AndesForceFreeCmdMsg(live[i]);
 for(i=0;i<32;i++)if(packets[i])RTMPFreeNdisPacket(&adapter,packets[i]);
 assert(!pthread_mutex_destroy(&adapter.MCUCtrl.msg_lock));
 assert(!pthread_mutex_destroy(&hif.CtrlRingLock));assert(!pthread_mutex_destroy(&hif.FwDwloRing.RingLock));
 assert(!pthread_mutex_destroy(&cookie.dma_state_lock));}
struct send_job{struct cmd_msg *msg;int result;};
static void *send_thread(void *arg){struct send_job *job=arg;job->result=AndesSendCmdMsg(&adapter,job->msg);return NULL;}
static void *kick_thread(void *arg){struct send_job *job=arg;job->result=selected_kick(&adapter,job->msg);return NULL;}
static void *stop_thread(void *arg){(void)arg;assert(!pthread_mutex_lock(&schedule_lock));stop_started=1;
 assert(!pthread_cond_broadcast(&schedule_cond));assert(!pthread_mutex_unlock(&schedule_lock));
 assert(!pthread_mutex_lock(&cookie.dma_state_lock));adapter.dma_stopping=1;assert(!pthread_mutex_unlock(&cookie.dma_state_lock));return NULL;}
int main(int argc,char **argv){const char *name;struct cmd_msg *msg;int a=0,b=0,i,before_live=0,before_unqueued=0,before_tx,before_ack,before_done,before_packets=0,before_orphan_packets=0;pthread_t first,second;struct send_job job;
 assert(argc==2);name=argv[1];CASE_ADMISSION fixture_init();
 fw_mode=!strncmp(name,"fw-",3)||strstr(name,"-fw")!=NULL;
 if(strstr(name,"kick-vs-stop")){
  job.msg=new_msg(0,0);pause_publication=1;assert(!pthread_create(&first,NULL,kick_thread,&job));
  assert(!pthread_mutex_lock(&schedule_lock));while(!publication_paused)assert(!pthread_cond_wait(&schedule_cond,&schedule_lock));
  assert(!pthread_mutex_unlock(&schedule_lock));assert(!pthread_create(&second,NULL,stop_thread,NULL));
  assert(!pthread_mutex_lock(&schedule_lock));while(!stop_started)assert(!pthread_cond_wait(&schedule_cond,&schedule_lock));
  blocked_stop_seen=(pthread_mutex_trylock(&cookie.dma_state_lock)==EBUSY);assert(blocked_stop_seen);
  publication_release=1;assert(!pthread_cond_broadcast(&schedule_cond));assert(!pthread_mutex_unlock(&schedule_lock));
  assert(!pthread_join(first,NULL));assert(!pthread_join(second,NULL));a=job.result;
  msg=new_msg(1,0);b=selected_kick(&adapter,msg);
 }else if(!strncmp(name,"cross-",6)){
  hold_foreign=1;fail_msg_id=0;postpub_failure=strstr(name,"postpub")!=NULL;job.msg=new_msg(0,strstr(name,"-sync")!=NULL);
  assert(!pthread_create(&first,NULL,send_thread,&job));
  assert(!pthread_mutex_lock(&schedule_lock));while(!foreign_queued)assert(!pthread_cond_wait(&schedule_cond,&schedule_lock));
  assert(!pthread_mutex_unlock(&schedule_lock));if(strstr(name,"cross-cleanup")){AndesCleanupCmdMsg(&adapter,&adapter.MCUCtrl.txq);adapter.MCUCtrl.flags=0;}else{msg=new_msg(1,1);b=AndesSendCmdMsg(&adapter,msg);}
  assert(!pthread_mutex_lock(&schedule_lock));foreign_release=1;assert(!pthread_cond_broadcast(&schedule_cond));
  assert(!pthread_mutex_unlock(&schedule_lock));assert(!pthread_join(first,NULL));a=job.result;
 }else if(!strncmp(name,"cleanup-",8)){
  msg=new_msg(0,strstr(name,"-sync")!=NULL);if(strstr(name,"done")){assert(!selected_kick(&adapter,msg));AndesUnlinkCmdMsg(msg,&adapter.MCUCtrl.ackq);AndesQueueTailCmdMsg(&adapter.MCUCtrl.tx_doneq,msg,tx_done);AndesCleanupCmdMsg(&adapter,&adapter.MCUCtrl.tx_doneq);}
  else{AndesQueueTailCmdMsg(&adapter.MCUCtrl.txq,msg,tx_start);AndesCleanupCmdMsg(&adapter,&adapter.MCUCtrl.txq);}
 }else if(!strcmp(name,"force-clone-alias")){msg=new_msg(0,0);msg->retry_pkt=msg->net_pkt;AndesForceFreeCmdMsg(msg);
 }else if(!strncmp(name,"low-",4)){
  msg=new_msg(0,0);if(strstr(name,"nopin"))adapter.dma_lifecycle_pinned=0;
  else if(strstr(name,"quarantine"))adapter.dma_quarantined=1;else adapter.dma_stopping=1;
  a=selected_kick(&adapter,msg);
 }else if(!strncmp(name,"queue-",6)){
  msg=new_msg(0,strstr(name,"-sync")!=NULL);AndesQueueTailCmdMsg(&adapter.MCUCtrl.txq,msg,tx_start);
  if(strstr(name,"missing"))adapter.Flags|=fRTMP_ADAPTER_NIC_NOT_EXIST;else adapter.dma_stopping=1;
  a=AndesDequeueAndKickOutCmdMsgs(&adapter,msg);
 }else{
  msg=new_msg(0,strstr(name,"-sync")!=NULL);if(strstr(name,"-full")){normal_free=firmware_free=0;}
  if(!strncmp(name,"admit-stop",10))adapter.dma_stopping=1;
  if(!strncmp(name,"irq-",4))irq_context=1;
  if(!strcmp(name,"sync-kick-error-no-retry")){msg->sync=1;msg->retry_times=3;fail_msg_id=0;stop_on_kick=1;}
  if(!strcmp(name,"sync-clone-null")){msg->sync=1;msg->retry_times=3;fail_msg_id=0;clone_fail=1;}
  if(!strcmp(name,"async-retry-kick-fail")){msg->sync=0;msg->retry_times=3;fail_msg_id=0;}
  if(!strcmp(name,"sync-retry-fail")){msg->sync=1;msg->retry_times=3;fail_msg_id=0;}
  if(strstr(name,"mcu-off"))adapter.MCUCtrl.flags=0;
  if(!strcmp(name,"callback-missing-sync"))ops.pci_kick_out_cmd_msg=NULL;
  if(!strncmp(name,"wsys-",5)){msg->attr.ext_type=strstr(name,"-dev-")?EXT_CMD_ID_DEVINFO_UPDATE:(strstr(name,"-bss-")?EXT_CMD_ID_BSSINFO_UPDATE:(strstr(name,"-wtbl-")?EXT_CMD_ID_WTBL_UPDATE:EXT_CMD_STAREC_UPDATE));response_error_code=(strstr(name,"noresponse")||strstr(name,"sync-ok"))?0:5;response_valid=strstr(name,"-wtbl-")&&!strstr(name,"noresponse");}
  a=AndesSendCmdMsg(&adapter,msg);
 }
 before_tx=adapter.MCUCtrl.txq.count;before_ack=adapter.MCUCtrl.ackq.count;before_done=adapter.MCUCtrl.tx_doneq.count;
 for(i=0;i<8;i++)if(live[i]){int q,j,owned=0;DL_LIST *all[]={&adapter.MCUCtrl.txq,&adapter.MCUCtrl.ackq,&adapter.MCUCtrl.tx_doneq};before_live++;for(q=0;q<3;q++)for(j=0;j<all[q]->count;j++)if(all[q]->items[j]==live[i])owned=1;if(!owned)before_unqueued++;}
 for(i=0;i<32;i++)if(packets[i]){int j,owned=packet_mapped[i];before_packets++;for(j=0;j<8;j++)if(live[j]&&(live[j]->net_pkt==packets[i]||live[j]->retry_pkt==packets[i]))owned=1;if(!owned)before_orphan_packets++;}
 cleanup();
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%u,%u,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",
 a,b,created,freed,created-freed,waits,completions,kicks,maps,writes,clones,
 adapter.MCUCtrl.txq.count,adapter.MCUCtrl.ackq.count,adapter.MCUCtrl.tx_doneq.count,
 hif.CtrlRing.TxCpuIdx,hif.FwDwloRing.TxCpuIdx,adapter.dma_stopping,errors,blocked_stop_seen,reinitializations,before_live,before_tx,before_ack,before_done,before_unqueued,packet_allocs,packet_frees,packet_allocs-packet_frees,before_packets,before_orphan_packets);
 for(i=0;i<8;i++){assert(!live[i]);}return 0;}
'''
def function(text,name):
 token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
 masked=re.sub(token,lambda m:' '*len(m.group()),text)
 pattern=r'^(?:static\s+)?(?:inline\s+)?(?:VOID|BOOLEAN|UCHAR|INT|INT32|ULONG|int|void|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
 found=list(re.finditer(pattern,masked,re.M))
 if len(found)!=1:raise ValueError('Missing/ambiguous command function: '+name)
 start=found[0].start();opening=masked.index('{',start);depth=0
 for m in re.finditer(token+r'|[{}]',text[opening:]):
  if m.group()=='{':depth+=1
  elif m.group()=='}':
   depth-=1
   if not depth:return text[start:opening+m.end()]
 raise ValueError('Unterminated command function: '+name)
def generate_source(texts,variant='current'):
 if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current command inputs required')
 declarations=[]
 for pattern,key in SOURCE_DECLARATIONS.items():
  matches=re.findall(pattern,texts[key],re.M)
  if len(matches)!=1 or not isinstance(matches[0],str):raise ValueError('Unique actual command declaration required: '+pattern)
  declarations.append(matches[0])
 bodies={n:function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER}
 prototypes='\n'.join(body.split('{',1)[0].rstrip()+';'for body in bodies.values())
 admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
 return PREFIX.replace('SOURCE_DEFINITIONS','\n'.join(declarations)).replace('FUNCTION_DECLARATIONS',prototypes)+'\n'.join(bodies.values())+SUFFIX.replace('CASE_ADMISSION',admission)
def function_manifest(texts):
 return {n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}
