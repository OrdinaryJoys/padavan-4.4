"""Whole configured preallocation functions with inert allocation ownership seams.

Fixture ring counts and host structure sizes model cleanup ownership, not the
complete driver ABI, device memory peak, real DMA or normal inline allocation.
"""
import hashlib
import re

SOURCE_PATHS = {
 'pool':'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/cmm_mac_pci.c',
 'sizes':'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/rtmp_def.h',
 'flags':'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/Makefile.mt_wifi_ap'}
FUNCTION_SOURCES = {'desc_ring_alloc':'pool','desc_ring_free':'pool',
 'release_rx_free_buffer':'pool','alloc_rx_free_buffer':'pool',
 'RTMPFreeTxRxRingMemory':'pool','RTMPAllocTxRxRingMemory':'pool'}
BODY_ORDER = ('desc_ring_alloc','desc_ring_free','release_rx_free_buffer','alloc_rx_free_buffer',
 'RTMPFreeTxRxRingMemory','RTMPAllocTxRxRingMemory')
PREALLOC_START = '#ifdef RESOURCE_PRE_ALLOC\nstatic INT desc_ring_free'
PREALLOC_END = '\n#else\n/*\n\t========================================================================'
FUNCTION_REGIONS = {'desc_ring_free':'prealloc','RTMPFreeTxRxRingMemory':'prealloc',
 'RTMPAllocTxRxRingMemory':'prealloc'}
SOURCE_ANCHORS = {'sizes':['#define TXD_SIZE\t\t16\t/* TXD_SIZE = TxD + TxInfo */',
 '#define RXD_SIZE\t\t16','#define TX_DMA_1ST_BUFFER_SIZE  128',
 '#define RX1_BUFFER_SIZE         1700'],'flags':['EXTRA_CFLAGS += -DRESOURCE_PRE_ALLOC']}
OBSERVATION_FIELDS = ('status','attempts','freed_before_cleanup','live_before_cleanup','empty_before_cleanup',
 'first_cleanup_frees','repeat_cleanup_frees','retry_status','retry_attempts','retry_live','final_live',
 'invalid_memory_ops','error_logs')

SUFFIX = r'''
int main(int argc,char**argv){
 RTMP_ADAPTER a;struct os_cookie cookie;const char*name;int pool_mode,status,before[7],delta,again_delta,retry,retry_attempts,retry_live,i,saved_frees;void *meta;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&a,0,sizeof(a));memset(&cookie,0,sizeof(cookie));a.hdev_ctrl=&a;a.OS_Cookie=&cookie;
 a.cap.tx_num=a.cap.rx_num=2;a.cap.tx_size=a.cap.rx0_size=a.cap.rx1_size=3;a.hif.FwDwloRing.ring_size=4;
 pool_mode=!strncmp(name,"pool-",5);
 if(!strncmp(name,"startup-fail-",13))fail_at=atoi(name+13);
 if(!strncmp(name,"pool-fail-",10))fail_at=atoi(name+10);
 if(pool_mode){
  unsigned num=!strcmp(name,"pool-invalid-zero")?0:!strcmp(name,"pool-invalid-max")?65535:3;
  status=alloc_rx_free_buffer(&a,1,num);
  if(!strcmp(name,"pool-reentry")){assert(!status);meta=a.hif.RxRing[1].free_buf;status=alloc_rx_free_buffer(&a,1,3);assert(meta==a.hif.RxRing[1].free_buf&&live==7);}
 }else status=RTMPAllocTxRxRingMemory(&a);
 before[0]=status;before[1]=attempts;before[2]=frees;before[3]=live;before[4]=empty(&a);before[5]=invalid_memory_ops;before[6]=error_logs;
 saved_frees=frees;if(pool_mode)release_rx_free_buffer(&a,1);else RTMPFreeTxRxRingMemory(&a);delta=frees-saved_frees;
 saved_frees=frees;if(pool_mode)release_rx_free_buffer(&a,1);else RTMPFreeTxRxRingMemory(&a);again_delta=frees-saved_frees;
 assert(!live&&empty(&a));for(i=0;i<128;i++)assert(!owned[i]);attempts=frees=fail_at=0;
 retry=pool_mode?alloc_rx_free_buffer(&a,1,3):RTMPAllocTxRxRingMemory(&a);retry_attempts=attempts;retry_live=live;
 if(pool_mode)release_rx_free_buffer(&a,1);else RTMPFreeTxRxRingMemory(&a);
 assert(!live&&empty(&a));for(i=0;i<128;i++)assert(!owned[i]);
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",before[0],before[1],before[2],before[3],before[4],delta,again_delta,retry,retry_attempts,retry_live,live,before[5],before[6]);return 0;
}
'''


def function(text,name):
    if name in FUNCTION_REGIONS:
        if text.count(PREALLOC_START)!=1 or text.count(PREALLOC_END)!=1:
            raise ValueError('Unique RESOURCE_PRE_ALLOC source region required')
        text='static INT desc_ring_free'+text.split(PREALLOC_START,1)[1].split(PREALLOC_END,1)[0]
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:INT|UINT32|VOID|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    matches=list(re.finditer(pattern,masked,re.M))
    if len(matches)!=1:raise ValueError('Missing/ambiguous startup function '+name)
    start=matches[0].start();opening=text.index('{',start);depth=0
    for match in re.finditer(token+r'|[{}]',text[opening:]):
        if match.group()=='{':depth+=1
        elif match.group()=='}':
            depth-=1
            if not depth:return text[start:opening+match.end()]
    raise ValueError('Unterminated startup function '+name)


def actual_functions(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact startup sources required')
    for key,anchors in SOURCE_ANCHORS.items():
        if not all(x in texts[key]for x in anchors):raise ValueError('Changed startup source anchor '+key)
    return {name:{'source':key,'body':function(texts[key],name)}for name,key in FUNCTION_SOURCES.items()}


def generate_source(texts,fixture_root=None,owner_uid=0,variant='prealloc'):
    if variant!='prealloc' or type(owner_uid)is not int or not 0<=owner_uid<2**32:
        raise ValueError('Configured prealloc variant and typed UID required')
    bodies=actual_functions(texts)
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return PREFIX+'\n'+'\n'.join(bodies[n]['body']for n in BODY_ORDER)+'\n'+SUFFIX.replace('CASE_ADMISSION',admission)


def function_manifest(texts):
    bodies=actual_functions(texts)
    return {n:{'execution':'whole-function','full_body_sha256':hashlib.sha256(bodies[n]['body'].encode()).hexdigest()}for n in BODY_ORDER}

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void VOID;typedef void*PVOID;typedef unsigned char UCHAR,UINT8;typedef unsigned short UINT16;
typedef unsigned int UINT32;typedef unsigned long ULONG;typedef int INT,NDIS_STATUS;typedef uintptr_t NDIS_PHYSICAL_ADDRESS;
#define TRUE 1
#define FALSE 0
#define RESOURCE_PRE_ALLOC
#define HIF_RX_IDX0 0
#define HIF_RX_IDX1 1
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_RESOURCES 3
#define ERRLOG_OUT_OF_SHARED_MEMORY 1
#define NDIS_ERROR_CODE_OUT_OF_RESOURCES 1
#define TXD_SIZE 16
#define RXD_SIZE 16
#define TX_DMA_1ST_BUFFER_SIZE 128
#define RX1_BUFFER_SIZE 1700
#define CTL_RING_SIZE 4
#define MTWF_LOG(...) ((void)0)
typedef struct _RTMP_DMABUF {void *AllocVa;NDIS_PHYSICAL_ADDRESS AllocPa;ULONG AllocSize;}RTMP_DMABUF;
typedef struct _RTMP_DMACB {void *fixture_metadata;}RTMP_DMACB;
typedef struct {RTMP_DMACB *Cell;}RTMP_TX_RING;
typedef struct {RTMP_DMACB *Cell;UINT16 free_buf_head,free_buf_tail,free_buf_size,free_buf_64k_head,free_buf_64k_tail,free_buf_64k_size;int rx_discard;RTMP_DMABUF *free_buf,*free_buf_64k;}RTMP_RX_RING;
struct _RTMP_CHIP_CAP {UINT8 tx_num,rx_num;UINT16 tx_size,rx0_size,rx1_size;};
struct _PCI_HIF_T {RTMP_DMABUF TxBufSpace[2],TxDescRing[2],RxDescRing[2],CtrlDescRing;RTMP_TX_RING TxRing[2];RTMP_RX_RING RxRing[2];struct {RTMP_DMABUF DescRing;UINT32 ring_size;}FwDwloRing;};
struct os_cookie {void*pDev;};typedef struct os_cookie *POS_COOKIE;
typedef struct _RTMP_ADAPTER {void *hdev_ctrl,*OS_Cookie,*AdapterHandle;struct _RTMP_CHIP_CAP cap;struct _PCI_HIF_T hif;}RTMP_ADAPTER;
#define GET_NUM_OF_TX_RING(c) ((c)->tx_num)
#define GET_NUM_OF_RX_RING(c) ((c)->rx_num)
#define GET_TX_RING_SIZE(c) ((c)->tx_size)
#define GET_RX0_RING_SIZE(c) ((c)->rx0_size)
#define GET_RX1_RING_SIZE(c) ((c)->rx1_size)
static void *hc_get_hif_ctrl(void*p){return &((RTMP_ADAPTER*)p)->hif;}
static struct _RTMP_CHIP_CAP *hc_get_chip_cap(void*p){return &((RTMP_ADAPTER*)p)->cap;}
static struct os_cookie *hc_get_os_cookie(void*p){return ((RTMP_ADAPTER*)p)->OS_Cookie;}
static int attempts,frees,live,fail_at,invalid_memory_ops,error_logs;static void*owned[128];
static void *fixture_alloc(size_t n){void*p;assert(n&&attempts<128);attempts++;if(attempts==fail_at)return NULL;p=calloc(1,n);assert(p);owned[attempts-1]=p;live++;return p;}
static void fixture_free(void*p){int i;assert(p);for(i=0;i<128;i++)if(owned[i]==p)break;if(i==128){invalid_memory_ops++;assert(!"unowned or repeated free");}owned[i]=NULL;free(p);frees++;live--;}
static void fixture_zero(void*p,size_t n){if(!p&&n){invalid_memory_ops++;assert(!"NULL zero destination");}memset(p,0,n);}
#define NdisZeroMemory(p,n) fixture_zero(p,n)
#define os_free_mem(p) fixture_free(p)
static int os_alloc_mem(void*ad,UCHAR**p,ULONG n){(void)ad;*p=fixture_alloc(n);return *p?NDIS_STATUS_SUCCESS:NDIS_STATUS_FAILURE;}
static void RtmpAllocDescBuf(void*dev,UINT32 index,ULONG n,int cached,void**va,NDIS_PHYSICAL_ADDRESS*pa){(void)dev;(void)index;(void)cached;*va=fixture_alloc(n);*pa=(uintptr_t)*va;}
static void RtmpFreeDescBuf(void*dev,ULONG n,void*va,NDIS_PHYSICAL_ADDRESS pa){(void)dev;(void)n;(void)pa;fixture_free(va);}
static void RTMP_AllocateFirstTxBuffer(void*dev,UINT32 index,ULONG n,int cached,void**va,NDIS_PHYSICAL_ADDRESS*pa){RtmpAllocDescBuf(dev,index,n,cached,va,pa);}
static void RTMP_FreeFirstTxBuffer(void*dev,ULONG n,int cached,void*va,NDIS_PHYSICAL_ADDRESS pa){(void)cached;RtmpFreeDescBuf(dev,n,va,pa);}
static void NdisWriteErrorLogEntry(void*handle,UINT32 code,UINT32 count,ULONG value){(void)handle;(void)code;(void)count;(void)value;error_logs++;}
static int empty(RTMP_ADAPTER*a){int i;struct _PCI_HIF_T*h=&a->hif;for(i=0;i<2;i++)if(h->TxBufSpace[i].AllocVa||h->TxDescRing[i].AllocVa||h->RxDescRing[i].AllocVa||h->TxRing[i].Cell||h->RxRing[i].Cell||h->RxRing[i].free_buf||h->RxRing[i].free_buf_64k||h->RxRing[i].free_buf_size||h->RxRing[i].free_buf_64k_size)return 0;return !h->CtrlDescRing.AllocVa&&!h->FwDwloRing.DescRing.AllocVa;}
'''

CASE_NAMES = ('startup-fail-01',
 'startup-fail-02',
 'startup-fail-03',
 'startup-fail-04',
 'startup-fail-05',
 'startup-fail-06',
 'startup-fail-07',
 'startup-fail-08',
 'startup-fail-09',
 'startup-fail-10',
 'startup-fail-11',
 'startup-fail-12',
 'startup-fail-13',
 'startup-fail-14',
 'startup-fail-15',
 'startup-fail-16',
 'startup-fail-17',
 'startup-fail-18',
 'startup-fail-19',
 'pool-fail-01',
 'pool-fail-02',
 'pool-fail-03',
 'pool-fail-04',
 'pool-fail-05',
 'pool-fail-06',
 'pool-fail-07',
 'startup-success',
 'pool-success',
 'pool-reentry',
 'pool-invalid-zero',
 'pool-invalid-max')
EXPECTED_ROWS = {'startup-fail-01': [3, 1, 0, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-02': [3, 2, 1, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-03': [3, 3, 2, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-04': [3, 4, 3, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-05': [3, 5, 4, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-06': [3, 6, 5, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-07': [3, 7, 6, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-08': [3, 8, 7, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-09': [3, 9, 8, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-10': [3, 10, 9, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-11': [3, 11, 10, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-12': [3, 12, 11, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-13': [3, 13, 12, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-14': [3, 14, 13, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-15': [3, 15, 14, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-16': [3, 16, 15, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-17': [3, 17, 16, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-18': [3, 18, 17, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'startup-fail-19': [3, 19, 18, 0, 1, 0, 0, 0, 19, 19, 0, 0, 1],
 'pool-fail-01': [3, 1, 0, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0],
 'pool-fail-02': [3, 2, 1, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0],
 'pool-fail-03': [3, 3, 2, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0],
 'pool-fail-04': [3, 4, 3, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0],
 'pool-fail-05': [3, 5, 4, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0],
 'pool-fail-06': [3, 6, 5, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0],
 'pool-fail-07': [3, 7, 6, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0],
 'startup-success': [0, 19, 0, 19, 0, 19, 0, 0, 19, 19, 0, 0, 0],
 'pool-success': [0, 7, 0, 7, 0, 7, 0, 0, 7, 7, 0, 0, 0],
 'pool-reentry': [1, 7, 0, 7, 0, 7, 0, 0, 7, 7, 0, 0, 0],
 'pool-invalid-zero': [1, 0, 0, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0],
 'pool-invalid-max': [1, 0, 0, 0, 1, 0, 0, 0, 7, 7, 0, 0, 0]}
