"""Current real cyclic pool/allocator/getter functions with inert DMA identity checks.

The oracle rejects duplicate live mapping ownership before simulated DMA
publication. These checks do not certify real DMA, cache IO or hardware timing.
"""
import hashlib
import re
SOURCE_PATHS = {'hif': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/hif_pci.c',
 'pool': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/cmm_mac_pci.c',
 'allocator': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_rbus_pci_util.c',
 'ring_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/hif/mt_hif_pci.h',
 'os_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/rt_os_util.h'}
FUNCTION_SOURCES = {'alloc_rx_buf_1k': 'pool',
 'free_rx_buf_1k': 'pool',
 'alloc_rx_buf_64k': 'pool',
 'free_rx_buf_64k': 'pool',
 'free_rx_buf': 'pool',
 'RTMP_AllocateRxPacketBuffer': 'allocator',
 'rx_dma_cell_valid': 'hif',
 'ExpandPacketBuffer': 'hif',
 'rx_scatter_info': 'hif',
 'rx_scatter_info_io': 'hif',
 'rx_scatter_gather': 'hif',
 'mtd_pci_get_pkt_from_rx_resource': 'hif',
 'mtd_pci_get_pkt_from_rx_resource_io': 'hif'}
BODY_ORDER = ('alloc_rx_buf_1k',
 'free_rx_buf_1k',
 'alloc_rx_buf_64k',
 'free_rx_buf_64k',
 'free_rx_buf',
 'RTMP_AllocateRxPacketBuffer',
 'rx_dma_cell_valid',
 'ExpandPacketBuffer',
 'rx_scatter_info',
 'rx_scatter_info_io',
 'rx_scatter_gather',
 'mtd_pci_get_pkt_from_rx_resource',
 'mtd_pci_get_pkt_from_rx_resource_io')
PARENT_PREFIX_AUTHORING_SHA256 = '7d3c9275bca750064658efbf6ad7140f5d7c5244d774652bd9e722b9daf04109'
SOURCE_ANCHORS = {'ring_header': ['#define INC_INDEX(_idx, _RingSize)    \\\n'
                 '\t{                                          \\\n'
                 '\t\t(_idx) = (_idx+1) % (_RingSize);       \\\n'
                 '\t}\n',
                 'BOOLEAN rx_discard;',
                 'UINT16 free_buf_head;',
                 'UINT16 free_buf_64k_head;'],
 'os_header': ['enum MEM_ALLOC_TYPE {\n\tDYNAMIC_PAGE_ALLOC,\n\tDYNAMIC_SLAB_ALLOC,\n\tPRE_SLAB_ALLOC,\n};']}

PREFIX = r'''#define GNU_PACKED __attribute__((packed))
#define RXD_SIZE		16
#define RMAC_RXD_0_PKT_TYPE_MASK		0xe0000000
#define RMAC_RXD_0_PKT_RX_BYTE_COUNT_MASK 0x0000ffff
#define RMAC_RX_PKT_TYPE(_x)			(((_x) & RMAC_RXD_0_PKT_TYPE_MASK) >> 29)
#define RMAC_RX_PKT_RX_BYTE_COUNT(_x)	(((_x) & RMAC_RXD_0_PKT_RX_BYTE_COUNT_MASK))
#define RMAC_RX_PKT_TYPE_RX_NORMAL		0x02
#define RMAC_RX_PKT_TYPE_RX_DUP_RFB		0x03
#define RMAC_RX_PKT_TYPE_RX_TXRXV		0x01
#define RMAC_RX_PKT_TYPE_RX_TXS			0x00
#define RMAC_RX_PKT_TYPE_RX_EVENT		0x07
#define RMAC_RX_PKT_TYPE_RX_TMR			0x04
#define RMAC_RX_PKT_TYPE_TXRX_NOTIFY    0x06

#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef uint8_t UCHAR,UINT8,*PUCHAR;typedef uint16_t UINT16;typedef uint32_t UINT32;typedef unsigned int UINT;typedef int INT,BOOLEAN;typedef void VOID;typedef void*PVOID;typedef void*PNDIS_PACKET;typedef uintptr_t NDIS_PHYSICAL_ADDRESS;typedef int NDIS_SPIN_LOCK;
#define TRUE 1
#define FALSE 0
#define RTMP_PCI_SUPPORT
#define RTMP_RBUS_SUPPORT
#define RX_SCATTER
#define UNIFY_FW_CMD
#define CUT_THROUGH

#define SKB_BUF_HEADROOM_RSV 32
#define SKB_BUF_TAILROOM_RSV 32
#define SKB_DATA_ALIGN(n) (n)
#define PAGE_SIZE 4096
#define HIF_RX_IDX0 0
#define HIF_RX_IDX1 1
#define HIF_TX_IDX0 0
#define FREE_BUF_1k 0
#define FREE_BUF_64k 1
#define fASIC_CAP_RX_DMA_SCATTER 1
#define fRTMP_ADAPTER_SYSEM_READY 1
#define fRTMP_ADAPTER_START_UP 2
#define RTMP_PCI_DMA_FROMDEVICE 2
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define MCU_INIT 0
#define fRX_CMD_RSP 1
#define ENABLE_RXD_LOG 0
#define MTWF_LOG(...) ((void)0)
#define OS_TEST_BIT(n,p) ((*(p)&(1UL<<(n)))!=0)
#define le2cpu32(x) (x)
#define os_move_mem(d,s,n) memmove(d,s,n)
#define NdisMoveMemory(d,s,n) memmove(d,s,n)
#define RTMP_SEM_LOCK(p) ((void)(p))
#define RTMP_SEM_UNLOCK(p) ((void)(p))
#define INC_RING_INDEX(i,n) do{(i)=((i)+1)%(n);}while(0)
#define GET_OS_PKT_DATAPTR(p) (((struct packet*)(p))->data)
#define GET_OS_PKT_LEN(p) (((struct packet*)(p))->len)
#define IS_ASIC_CAP(p,c) (((p)->caps&(c))!=0)
#define RTMP_TEST_FLAG(p,f) (((p)->flags&(f))!=0)
#define RX_BLK_SET_FLAG(p,f) ((p)->Flags|=(f))
#define GET_EVENT_FW_RXD_LENGTH(p) ((p)->fw_rxd_0.field.length)
#define GET_EVENT_HDR_ADD_PAYLOAD_TOTAL_LEN(p) (GET_EVENT_FW_RXD_LENGTH(p)-sizeof(EVENT_RXD))
enum MEM_ALLOC_TYPE {DYNAMIC_PAGE_ALLOC,DYNAMIC_SLAB_ALLOC,PRE_SLAB_ALLOC};
typedef	struct GNU_PACKED _RXD_STRUC {
	/* Word	0 */
	UINT32		SDP0;

	/* Word	1 */
	UINT32		SDL1:14;
	UINT32		LS1:1;
	UINT32		BURST:1;
	UINT32		SDL0:14;
	UINT32		LS0:1;
	UINT32		DDONE:1;

	/* Word	2 */
	UINT32		SDP1;
} RXD_STRUC;
typedef struct{void*AllocVa;NDIS_PHYSICAL_ADDRESS AllocPa;UINT32 AllocSize;}RTMP_DMABUF;
typedef struct{void*AllocVa;NDIS_PHYSICAL_ADDRESS AllocPa;RTMP_DMABUF DmaBuf;void*pNdisPacket;}RTMP_DMACB;
typedef struct _RTMP_RX_RING {UINT32 RxDmaIdx,RxSwReadIdx,RxRingSize,RxBufferSize,cur_free_buf_len,sw_read_idx_inc,RxCpuIdx,hw_didx_addr;BOOLEAN rx_discard;RTMP_DMACB*Cell;UINT16 free_buf_head,free_buf_tail,free_buf_size,free_buf_64k_head,free_buf_64k_tail,free_buf_64k_size;RTMP_DMABUF *free_buf,*free_buf_64k;}RTMP_RX_RING;
struct _PCI_HIF_T{RTMP_RX_RING RxRing[2];NDIS_SPIN_LOCK RxRingLock[2];};
typedef struct{void*pDev;}OS_COOKIE,*POS_COOKIE;
struct MCU_CTRL{unsigned long flags;};
struct _RTMP_CHIP_OP;typedef struct _RTMP_ADAPTER{struct _PCI_HIF_T PciHif;void*OS_Cookie,*hdev_ctrl;UINT32 flags,caps;struct MCU_CTRL MCUCtrl;struct _RTMP_CHIP_OP*ops;}RTMP_ADAPTER;
struct _RTMP_CHIP_OP{void(*rx_event_handler)(RTMP_ADAPTER*,UCHAR*,UINT32);};
typedef struct{UINT32 Flags;}RX_BLK;
union _RMAC_RXD_0_UNION{UINT32 word;};
typedef struct GNU_PACKED _RMAC_RXD_0 {
	UINT32 RxByteCnt:16;
	UINT32 EthTypeOffset:7;
	UINT32 IpChkSumOffload:1;
	UINT32 UdpTcpChkSumOffload:1;
	UINT32 RfbGroupVld:4;
	UINT32 PktType:3;
} RMAC_RXD_0, *PRMAC_RXD_0;
typedef struct GNU_PACKED _RMAC_RXD_1 {
	UINT32   HTC:1;
	UINT32   a1_type:2;
	UINT32   BF_RPT:1;
	UINT32   BcnWithBMcst:1;
	UINT32   BcnWithUCast:1;
	UINT32   KeyId:2;
	UINT32   ChFreq:8;
	UINT32   MacHdrLen:6;
	UINT32   HdrOffset:1;
	UINT32   HdrTranslation:1;
	UINT32   PayloadFmt:2;
	UINT32   RxDBssidIdx:6;
} RMAC_RXD_1, *PRMAC_RXD_1;
typedef struct GNU_PACKED _RMAC_RXD_2 {
	UINT32   RxDWlanIdx:8;
	UINT32   RxDTid:4;
	UINT32   SecMode:4;
	UINT32   SwBit:1;
	UINT32   FcsErr:1;
	UINT32   CipherMis:1;
	UINT32   CipherLenMis:1;
	UINT32   IcvErr:1;
	UINT32   TkipMicErr:1;
	UINT32   LenMis:1;
	UINT32   DeAmsduFail:1;
	UINT32   ExMaxRxLen:1;
	UINT32   HdrTransFail:1;
	UINT32   InterestedFrm:1;
	UINT32   FragFrm:1;
	UINT32   NullFrm:1;
	UINT32   NonDataFrm:1;
	UINT32   NonAmpduSfrm:1;
	UINT32   NonAmpduFrm:1;
} RMAC_RXD_2, *PRMAC_RXD_2;
typedef struct GNU_PACKED _RMAC_RXD_3 {
	UINT32   RxVSeq:8;
	UINT32   Tcl:1;
	UINT32   Drop:1;
	UINT32   ClsPkt:1;
	UINT32   OfldPf:2;
	UINT32   MgcPkt:1;
	UINT32   WoWlan:5;
	UINT32   ClsBitMap:10;
	UINT32   PfMode:1;
	UINT32   PfStatus:2;
} RMAC_RXD_3, *PRMAC_RXD_3;
typedef struct GNU_PACKED _RXD_BASE_STRUCT {
	/* DWORD 0 */
	struct _RMAC_RXD_0 RxD0;
	/* DWORD 1 */
	struct _RMAC_RXD_1 RxD1;
	/* DWORD 2 */
	struct _RMAC_RXD_2 RxD2;
	/* DWORD 3 */
	/* struct rmac_rxd_3_normal RxD3;//do unify */
	struct _RMAC_RXD_3 RxD3;
} RXD_BASE_STRUCT, *PRXD_BASE_STRUCT;
#define RMAC_INFO_BASE_SIZE	16
#define RMAC_INFO_GRP_1_SIZE    16
#define RMAC_INFO_GRP_2_SIZE    8
#define RMAC_INFO_GRP_3_SIZE    24
#define RMAC_INFO_GRP_4_SIZE    16
#define RXS_GROUP1 (1 << 0)
#define RXS_GROUP2 (1 << 1)
#define RXS_GROUP3 (1 << 2)
#define RXS_GROUP4 (1 << 3)
typedef union _FW_RXD_0 {
	struct {
		UINT32 length:16;
		UINT32 pkt_type_id:16;
	} field;
	UINT32 word;
} FW_RXD_0;
typedef union _FW_RXD_1 {
	struct {
		UINT32 eid:8;
		UINT32 seq_num:8;
		UINT32 rsv:16;
	} field;
	UINT32 word;
} FW_RXD_1;
typedef union _FW_RXD_2 {
	struct {
		UINT32 ext_eid:8;
		UINT32 rsv:16;
		UINT32 s2d_index:8;
	} field;
	UINT32 word;
} FW_RXD_2;
typedef struct GNU_PACKED _EVENT_RXD_ {
	FW_RXD_0 fw_rxd_0;
	FW_RXD_1 fw_rxd_1;
	FW_RXD_2 fw_rxd_2;
} EVENT_RXD;
struct cmd_msg{void*net_pkt;};
struct packet{unsigned char*data;UINT32 len,capacity;};
static int allocs,copies,dispatch,releases,scans,fail_at;static int frag_frees,heap_frees,build_fail;static unsigned char*allocations[256];static int allocation_count;static UINT32 dma_index=2;
static void*memory(UINT32 n){void*p=calloc(1,n?n:1);if(!p)exit(88);if(allocation_count>=256)exit(89);allocations[allocation_count++]=p;return p;}
static void*alloc(UINT32 n){allocs++;return allocs==fail_at?NULL:memory(n);}
static void*packet(UINT32 n,int counted){struct packet*p=counted?alloc(sizeof(*p)):memory(sizeof(*p));if(!p)return NULL;p->data=memory(n);p->capacity=n;return p;}
static void*tail(void*p,UINT32 n){struct packet*s=p;void*r=s->data+s->len;if(n>s->capacity-s->len)exit(87);s->len+=n;return r;}
#define OS_PKT_TAIL_BUF_EXTEND(p,n) tail(p,n)
#define RELEASE_NDIS_PACKET(ad,p,s) do{(void)(ad);(void)(p);(void)(s);releases++;}while(0)
#define RELEASE_NDIS_PACKET_IRQ(ad,p,s) RELEASE_NDIS_PACKET(ad,p,s)
#define DEV_FREE_FRAG_BUF(p) do{(void)(p);releases++;frag_frees++;}while(0)
#define os_free_mem(p) do{(void)(p);releases++;heap_frees++;}while(0)
#define DEV_ALLOC_FRAG(p,n) ((p)=alloc(n))
#define os_alloc_mem(ad,p,n) (*(p)=alloc(n))
#define DEV_BUILD_SKB(p,raw,n) do{if(build_fail)(p)=NULL;else{(p)=memory(sizeof(struct packet));((struct packet*)(p))->data=(raw);((struct packet*)(p))->capacity=(n)?(n):65536;}}while(0)
#define DEV_SKB_PTR_ADJUST(p,n,raw) do{((struct packet*)(p))->data=(unsigned char*)(raw)+SKB_BUF_HEADROOM_RSV;((struct packet*)(p))->len=(n);}while(0)
#define RTMP_DCACHE_FLUSH(p,n) do{(void)(p);if((n)==RXD_SIZE)scans++;}while(0)
#define PCI_UNMAP_SINGLE(ad,pa,n,dir) pool_unmap(pa,n)
#define HIF_IO_READ32(ad,reg,p) (*(p)=dma_index)
static void*hc_get_hif_ctrl(void*p){return &((RTMP_ADAPTER*)p)->PciHif;}

#define CONFIG_WIFI_BUILD_SKB
#define inline static inline
#define sk_buff packet
typedef unsigned long ULONG;typedef NDIS_PHYSICAL_ADDRESS *PNDIS_PHYSICAL_ADDRESS;
struct device {int unused;};
#define PCI_DMA_FROMDEVICE RTMP_PCI_DMA_FROMDEVICE
#define DEV_ALLOC_SKB(p,n) ((p)=packet(n,1))
#define dma_map_single(dev,va,n,dir) ((void)(dev),(void)(dir),pool_map(va,n))

#define INC_INDEX(_idx, _RingSize)    \
	{                                          \
		(_idx) = (_idx+1) % (_RingSize);       \
	}
'''

POOL_SEAMS = r'''
#include <assert.h>
static RTMP_RX_RING *pool_ring;
static void *pool_va[5];
static int mapped[5],map_calls,unmap_calls,alias_attempts,inject_null_after_first;
static NDIS_PHYSICAL_ADDRESS pool_map(void *va,ULONG size){
 int i;assert(size==64);for(i=0;i<5;i++)if(pool_va[i]==va)break;assert(i<5);
 if(mapped[i]){alias_attempts++;assert(!"duplicate live DMA mapping owner");}
 mapped[i]=1;map_calls++;
 if(inject_null_after_first&&map_calls==5)pool_ring->free_buf[0].AllocVa=NULL;
 return (NDIS_PHYSICAL_ADDRESS)(i+1)*4096;
}
static void pool_unmap(NDIS_PHYSICAL_ADDRESS pa,ULONG size){
 unsigned i=(unsigned)(pa/4096)-1;assert(size==64&&i<5&&mapped[i]);mapped[i]=0;unmap_calls++;
}
static int live_maps(void){int i,n=0;for(i=0;i<5;i++)n+=mapped[i];return n;}
static int owner_check(RTMP_RX_RING *r){
 unsigned i,j;for(i=0;i<r->RxRingSize;i++){
  RTMP_DMACB *c=&r->Cell[i];unsigned slot=(unsigned)(c->DmaBuf.AllocPa/4096)-1;
  if(!c->pNdisPacket||c->DmaBuf.AllocVa!=c->pNdisPacket||slot>=5||!mapped[slot]||pool_va[slot]!=c->pNdisPacket)return 0;
  for(j=0;j<i;j++)if(c->pNdisPacket==r->Cell[j].pNdisPacket)return 0;
 }return 1;
}
'''

CASE_NAMES = ('pool-drop-first-then-two-valid','pool-drop-zero-then-two-valid',
 'pool-drop-chain-then-valid','pool-discard-wait-and-resume','pool-null-reserve-and-retry',
 'pool-null-follower-and-resume','pool-null-expansion-and-resume','pool-wrap-eight-valid',
 'pool-io-drop-first-then-two-valid','pool-null-head-helpers')
OBSERVATION_FIELDS = ('returns','zero_outputs','calls','read_index','discard','pool_head','pool_tail',
 'maps','unmaps','active_maps','aliases','ownership_ok','content_ok')
EXPECTED_ROWS = {
 'pool-drop-first-then-two-valid':[2,1,3,3,0,2,3,7,3,4,0,1,1],
 'pool-drop-zero-then-two-valid':[2,1,3,3,0,2,3,7,3,4,0,1,1],
 'pool-drop-chain-then-valid':[1,2,3,3,0,2,3,7,3,4,0,1,1],
 'pool-discard-wait-and-resume':[1,3,4,3,0,2,3,7,3,4,0,1,1],
 'pool-null-reserve-and-retry':[3,1,4,3,0,2,3,7,3,4,0,1,1],
 'pool-null-follower-and-resume':[1,2,3,3,0,2,3,7,3,4,0,1,1],
 'pool-null-expansion-and-resume':[1,2,3,3,0,2,3,7,3,4,0,1,1],
 'pool-wrap-eight-valid':[8,0,8,0,0,2,3,12,8,4,0,1,1],
 'pool-io-drop-first-then-two-valid':[2,1,3,3,0,2,3,7,3,4,0,1,1],
 'pool-null-head-helpers':[0,0,0,0,0,4,0,4,0,4,0,1,1],
}

SUFFIX = r'''
int main(int argc,char **argv){
 RTMP_ADAPTER a;OS_COOKIE cookie;RTMP_DMACB cells[4];RXD_STRUC d[4];RTMP_DMABUF pool[5],big[2];RTMP_RX_RING *r;
 const char *name;int i,j,returns=0,zeros=0,calls=0,ownership_ok=1,content_ok=1,io=0,steps=3;void *p;UINT32 n,pending=3;BOOLEAN again;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&a,0,sizeof(a));memset(&cookie,0,sizeof(cookie));memset(cells,0,sizeof(cells));memset(d,0,sizeof(d));memset(pool,0,sizeof(pool));memset(big,0,sizeof(big));
 a.hdev_ctrl=&a;a.OS_Cookie=&cookie;a.flags=3;r=&a.PciHif.RxRing[1];pool_ring=r;r->Cell=cells;r->RxRingSize=4;r->RxBufferSize=64;r->RxDmaIdx=3;r->free_buf=pool;r->free_buf_size=5;r->free_buf_64k=big;r->free_buf_64k_size=1;
 for(i=0;i<5;i++){pool[i].AllocSize=64;pool[i].AllocVa=pool_va[i]=memory(64);}
 big[0].AllocVa=memory(65536);big[1].AllocVa=memory(65536);
 for(i=0;i<4;i++){
  cells[i].AllocVa=&d[i];cells[i].AllocPa=(uintptr_t)&d[i];cells[i].DmaBuf.AllocSize=64;
  cells[i].pNdisPacket=RTMP_AllocateRxPacketBuffer(r,NULL,PRE_SLAB_ALLOC,64,&cells[i].DmaBuf.AllocVa,&cells[i].DmaBuf.AllocPa);
  assert(cells[i].pNdisPacket);d[i].SDL0=32;d[i].LS0=1;d[i].DDONE=1;
 }
 assert(r->free_buf_head==4&&live_maps()==4&&owner_check(r));
 if(strstr(name,"drop-first"))d[0].SDL0=65;
 if(strstr(name,"drop-zero"))d[0].SDL0=0;
 if(strstr(name,"drop-chain")||strstr(name,"discard-wait")){d[0].SDL0=65;d[0].LS0=0;}
 if(strstr(name,"discard-wait")){d[1].DDONE=0;steps=4;}
 if(strstr(name,"null-reserve")){pool[4].AllocVa=NULL;steps=4;}
 if(strstr(name,"null-follower")){a.caps=1;d[0].LS0=0;d[0].SDL0=16;d[1].SDL0=24;inject_null_after_first=1;}
 if(strstr(name,"null-expansion")){a.caps=1;d[0].LS0=0;d[0].SDL0=16;d[1].SDL0=24;big[0].AllocVa=NULL;}
 if(strstr(name,"wrap-eight"))steps=8;
 if(strstr(name,"-io-"))io=1;
 if(strstr(name,"null-head-helpers")){
  pool[4].AllocVa=NULL;assert(!alloc_rx_buf_1k(r)&&r->free_buf_head==4&&r->free_buf_tail==0);pool[4].AllocVa=pool_va[4];
  r->free_buf_64k_size=2;r->free_buf_64k_head=1;big[1].AllocVa=NULL;assert(!alloc_rx_buf_64k(r)&&r->free_buf_64k_head==1);
  big[1].AllocVa=big[0].AllocVa;assert(alloc_rx_buf_64k(r)&&r->free_buf_64k_head==0);r->free_buf_64k_size=1;assert(alloc_rx_buf_64k(r)&&r->free_buf_64k_head==0);steps=0;
 }
 for(i=0;i<steps;i++){
  unsigned index=r->RxSwReadIdx;unsigned char byte=(unsigned char)(0x40+i);UINT32 expected=d[index].SDL0;
  if(strstr(name,"discard-wait")&&i==2)d[1].DDONE=1;
  if(strstr(name,"null-reserve")&&i==1)pool[4].AllocVa=pool_va[4];
  if(strstr(name,"null-follower")&&i==1)pool[0].AllocVa=pool_va[0];
  if(strstr(name,"wrap-eight")){d[index].DDONE=1;d[index].SDL0=32;d[index].LS0=1;expected=32;}
  memset(cells[index].DmaBuf.AllocVa,byte,64);n=0xdeadbeef;again=FALSE;
  p=io?mtd_pci_get_pkt_from_rx_resource_io(&a,&again,&pending,1,&n):mtd_pci_get_pkt_from_rx_resource(&a,&again,&pending,1,&n);calls++;
  if(!p){assert(n==0);zeros++;}else{
   returns++;if(n!=expected||n>64)content_ok=0;else for(j=0;j<(int)n;j++)if(((unsigned char*)p)[j]!=byte)content_ok=0;
   free_rx_buf(a.hdev_ctrl,1);
  }
  if(!owner_check(r)||live_maps()!=4)ownership_ok=0;
 }
 printf("[%d,%d,%d,%u,%d,%u,%u,%d,%d,%d,%d,%d,%d]\n",returns,zeros,calls,r->RxSwReadIdx,r->rx_discard,r->free_buf_head,r->free_buf_tail,map_calls,unmap_calls,live_maps(),alias_attempts,ownership_ok,content_ok);
 for(i=0;i<allocation_count;i++) { free(allocations[i]); }
 return 0;
}
'''


def function(text, name):
    token = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked = re.sub(token, lambda m: ' ' * len(m.group()), text)
    pattern = (r'^(?:(?:static|inline)\s+)*(?:INT|VOID|BOOLEAN|PNDIS_PACKET)\s*\*?\s*' +
               re.escape(name) + r'\s*\([^;{}]*\)\s*\{')
    matches = list(re.finditer(pattern, masked, re.M))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous pool function ' + name)
    start = matches[0].start(); opening = text.index('{', start); depth = 0
    for match in re.finditer(token + r'|[{}]', text[opening:]):
        if match.group() == '{':
            depth += 1
        elif match.group() == '}':
            depth -= 1
            if not depth:
                return text[start:opening + match.end()]
    raise ValueError('Unterminated pool function ' + name)


def actual_functions(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact pool sources required')
    for key, anchors in SOURCE_ANCHORS.items():
        for anchor in anchors:
            if anchor not in texts[key]:
                raise ValueError('Changed pool source declaration: ' + key)
    return {name: {'source': key, 'body': function(texts[key], name)}
            for name, key in FUNCTION_SOURCES.items()}


def generate_source(texts, fixture_root=None, owner_uid=0, variant='build'):
    if variant != 'build' or type(owner_uid) is not int or not 0 <= owner_uid < 2**32:
        raise ValueError('Current build variant and typed UID required')
    bodies = actual_functions(texts)
    admission = 'if(!(' + '||'.join('!strcmp(name,"' + n + '")' for n in CASE_NAMES) + '))return 91;'
    return (PREFIX + '\n' + POOL_SEAMS + '\n' + '\n'.join(bodies[n]['body'] for n in BODY_ORDER) +
            '\n' + SUFFIX.replace('CASE_ADMISSION', admission))


def function_manifest(texts):
    bodies = actual_functions(texts)
    return {n: {'execution': 'whole-function', 'full_body_sha256': hashlib.sha256(
        bodies[n]['body'].encode()).hexdigest()} for n in BODY_ORDER}
