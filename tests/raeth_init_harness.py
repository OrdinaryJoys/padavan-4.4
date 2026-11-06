"""Whole-function unpublished RAETH bookkeeping model; no MMIO/DMA/network I/O."""
import hashlib
import re
SOURCE_PATHS = {'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
 'bus': 'trunk/linux-4.4.x/drivers/base/bus.c',
 'device_header': 'trunk/linux-4.4.x/include/linux/device.h'}
FUNCTION_SOURCES = {'fe_tx_rx_dec_free': 'raeth', 'fe_tx_rx_dec': 'raeth', 'ei_uninit': 'raeth'}
BODY_ORDER = ('fe_tx_rx_dec_free', 'fe_tx_rx_dec', 'ei_uninit')
SOURCE_ONLY_FUNCTION_SOURCES = {'rather_probe': 'raeth', 'ei_init': 'raeth'}
MODEL_VARIANT = {'MAX_RX_RING_NUM': 4, 'no_MMIO_DMA_network': True,
                 'probe_source_only': True, 'external_lifetime_not_modeled': True,
                 'sysfs_bind_unbind_disabled': True}
FIELDS = ('ret', 'live', 'allocs', 'frees', 'reads', 'napi_deleted', 'tx', 'rx', 'queues')
CASE_NAMES = ('oom-1',
 'oom-2',
 'oom-3',
 'oom-4',
 'oom-5',
 'oom-6',
 'oom-7',
 'oom-8',
 'oom-9',
 'oom-10',
 'oom-11',
 'oom-12',
 'missing-1',
 'missing-2',
 'missing-3',
 'missing-4',
 'missing-5',
 'owned-0',
 'owned-1',
 'owned-2',
 'owned-3',
 'owned-4',
 'owned-5',
 'owned-6',
 'owned-7',
 'owned-8',
 'owned-9',
 'owned-10',
 'owned-11',
 'zero-txq',
 'zero-txd',
 'zero-rx',
 'tx1-overflow',
 'tx2-overflow',
 'tx-sum-overflow',
 'success',
 'single-gmac',
 'retry',
 'late-register-failure',
 'napi-none',
 'napi-full',
 'napi-split',
 'napi-rx',
 'napi-rss2',
 'napi-rss4')
EXPECTED_ROWS = {'oom-1': {'ret': -12,
           'live': 0,
           'allocs': 1,
           'frees': 0,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-2': {'ret': -12,
           'live': 0,
           'allocs': 2,
           'frees': 1,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-3': {'ret': -12,
           'live': 0,
           'allocs': 3,
           'frees': 2,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-4': {'ret': -12,
           'live': 0,
           'allocs': 4,
           'frees': 3,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-5': {'ret': -12,
           'live': 0,
           'allocs': 5,
           'frees': 4,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-6': {'ret': -12,
           'live': 0,
           'allocs': 6,
           'frees': 5,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-7': {'ret': -12,
           'live': 0,
           'allocs': 7,
           'frees': 6,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-8': {'ret': -12,
           'live': 0,
           'allocs': 8,
           'frees': 7,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-9': {'ret': -12,
           'live': 0,
           'allocs': 9,
           'frees': 8,
           'reads': 5,
           'napi_deleted': 0,
           'tx': 777,
           'rx': 888,
           'queues': 999},
 'oom-10': {'ret': -12,
            'live': 0,
            'allocs': 10,
            'frees': 9,
            'reads': 5,
            'napi_deleted': 0,
            'tx': 777,
            'rx': 888,
            'queues': 999},
 'oom-11': {'ret': -12,
            'live': 0,
            'allocs': 11,
            'frees': 10,
            'reads': 5,
            'napi_deleted': 0,
            'tx': 777,
            'rx': 888,
            'queues': 999},
 'oom-12': {'ret': -12,
            'live': 0,
            'allocs': 12,
            'frees': 11,
            'reads': 5,
            'napi_deleted': 0,
            'tx': 777,
            'rx': 888,
            'queues': 999},
 'missing-1': {'ret': -22,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 1,
               'napi_deleted': 0,
               'tx': 777,
               'rx': 888,
               'queues': 999},
 'missing-2': {'ret': -22,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 2,
               'napi_deleted': 0,
               'tx': 777,
               'rx': 888,
               'queues': 999},
 'missing-3': {'ret': -22,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 3,
               'napi_deleted': 0,
               'tx': 777,
               'rx': 888,
               'queues': 999},
 'missing-4': {'ret': -22,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 4,
               'napi_deleted': 0,
               'tx': 777,
               'rx': 888,
               'queues': 999},
 'missing-5': {'ret': -22,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 5,
               'napi_deleted': 0,
               'tx': 777,
               'rx': 888,
               'queues': 999},
 'owned-0': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-1': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-2': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-3': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-4': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-5': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-6': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-7': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-8': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-9': {'ret': -16,
             'live': 1,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'owned-10': {'ret': -16,
              'live': 1,
              'allocs': 0,
              'frees': 0,
              'reads': 0,
              'napi_deleted': 0,
              'tx': 777,
              'rx': 888,
              'queues': 999},
 'owned-11': {'ret': -16,
              'live': 1,
              'allocs': 0,
              'frees': 0,
              'reads': 0,
              'napi_deleted': 0,
              'tx': 777,
              'rx': 888,
              'queues': 999},
 'zero-txq': {'ret': -22,
              'live': 0,
              'allocs': 0,
              'frees': 0,
              'reads': 5,
              'napi_deleted': 0,
              'tx': 777,
              'rx': 888,
              'queues': 999},
 'zero-txd': {'ret': -22,
              'live': 0,
              'allocs': 0,
              'frees': 0,
              'reads': 5,
              'napi_deleted': 0,
              'tx': 777,
              'rx': 888,
              'queues': 999},
 'zero-rx': {'ret': -22,
             'live': 0,
             'allocs': 0,
             'frees': 0,
             'reads': 5,
             'napi_deleted': 0,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'tx1-overflow': {'ret': -22,
                  'live': 0,
                  'allocs': 0,
                  'frees': 0,
                  'reads': 5,
                  'napi_deleted': 0,
                  'tx': 777,
                  'rx': 888,
                  'queues': 999},
 'tx2-overflow': {'ret': -22,
                  'live': 0,
                  'allocs': 0,
                  'frees': 0,
                  'reads': 5,
                  'napi_deleted': 0,
                  'tx': 777,
                  'rx': 888,
                  'queues': 999},
 'tx-sum-overflow': {'ret': -22,
                     'live': 0,
                     'allocs': 0,
                     'frees': 0,
                     'reads': 5,
                     'napi_deleted': 0,
                     'tx': 777,
                     'rx': 888,
                     'queues': 999},
 'success': {'ret': 0,
             'live': 0,
             'allocs': 12,
             'frees': 12,
             'reads': 5,
             'napi_deleted': 0,
             'tx': 2048,
             'rx': 1024,
             'queues': 2},
 'single-gmac': {'ret': 0,
                 'live': 0,
                 'allocs': 12,
                 'frees': 12,
                 'reads': 5,
                 'napi_deleted': 0,
                 'tx': 1024,
                 'rx': 1024,
                 'queues': 1},
 'retry': {'ret': 0,
           'live': 0,
           'allocs': 15,
           'frees': 14,
           'reads': 10,
           'napi_deleted': 0,
           'tx': 2048,
           'rx': 1024,
           'queues': 2},
 'late-register-failure': {'ret': 0,
                           'live': 0,
                           'allocs': 12,
                           'frees': 12,
                           'reads': 5,
                           'napi_deleted': 1,
                           'tx': 2048,
                           'rx': 1024,
                           'queues': 2},
 'napi-none': {'ret': 0,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 0,
               'napi_deleted': 0,
               'tx': 777,
               'rx': 888,
               'queues': 999},
 'napi-full': {'ret': 0,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 0,
               'napi_deleted': 1,
               'tx': 777,
               'rx': 888,
               'queues': 999},
 'napi-split': {'ret': 0,
                'live': 0,
                'allocs': 0,
                'frees': 0,
                'reads': 0,
                'napi_deleted': 2,
                'tx': 777,
                'rx': 888,
                'queues': 999},
 'napi-rx': {'ret': 0,
             'live': 0,
             'allocs': 0,
             'frees': 0,
             'reads': 0,
             'napi_deleted': 1,
             'tx': 777,
             'rx': 888,
             'queues': 999},
 'napi-rss2': {'ret': 0,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 0,
               'napi_deleted': 2,
               'tx': 777,
               'rx': 888,
               'queues': 999},
 'napi-rss4': {'ret': 0,
               'live': 0,
               'allocs': 0,
               'frees': 0,
               'reads': 0,
               'napi_deleted': 4,
               'tx': 777,
               'rx': 888,
               'queues': 999}}
PREFIX = r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
typedef uint32_t u32;
typedef unsigned int atomic_t;
#define MAX_RX_RING_NUM 4
#define GFP_KERNEL 0
#define FE_INT_NAPI 1U
#define FE_INT_NAPI_TX_RX 2U
#define FE_INT_NAPI_RX_ONLY 4U
#define FE_RSS_4RING 8U
#define FE_RSS_2RING 16U
struct sk_buff { int unused; };
struct napi_struct { unsigned int active; };
struct END_DEVICE {
 struct sk_buff **free_skb, **skb_free;
 atomic_t *free_txd_num;
 unsigned int *free_txd_head, *free_txd_tail, *txd_pool_info, *rls_cnt;
 void **netrx_skb_data[4], **netrx0_skb_data;
 unsigned int features;
 struct napi_struct napi,napi_rx,napi_tx,napi_rx_rss0,napi_rx_rss1,napi_rx_rss2,napi_rx_rss3;
};
struct properties { u32 values[5]; };
struct device { struct properties *of_node; };
struct platform_device { struct device dev; };
struct net_device { struct END_DEVICE *private; };
static u32 gmac1_txq_num,gmac1_txq_txd_num,gmac2_txq_num,gmac2_txq_txd_num;
static u32 gmac1_txd_num,gmac2_txd_num,num_tx_desc,total_txq_num,num_rx_desc,num_tx_max_process;
static int fail_at,allocs,frees,live,reads,missing,napi_deleted;
static void *owners[64];
static void *netdev_priv(struct net_device *dev) { return dev->private; }
static void *kcalloc(size_t n,size_t size,int flags) {
 void *p; size_t i;
 (void)flags; allocs++;
 if(allocs==fail_at) return NULL;
 assert(n && size && n <= 4096 && size<=16);
 p=calloc(n,size); assert(p);
 for(i=0;i<64;i++) if(!owners[i]) { owners[i]=p;live++;return p; }
 abort();
}
static void kfree(void *p) {
 size_t i; if(!p) return;
 for(i=0;i<64;i++) if(owners[i]==p) {owners[i]=NULL;frees++;live--;free(p);return;}
 assert(!"foreign or double free");
}
static int of_property_read_u32(struct properties *p,const char *name,u32 *v) {
 static const char *const names[]={"gmac1_txq_num","gmac1_txq_txd_num","gmac2_txq_num","gmac2_txq_txd_num","num_rx_desc"};
 unsigned int i; reads++; if(reads==missing) return -EINVAL;
 for(i=0;i<5;i++) if(!strcmp(names[i],name)) {*v=p->values[i];return 0;}
 abort();
}
static void netif_napi_del(struct napi_struct *napi) {assert(napi->active);napi->active=0;napi_deleted++;}
static void check_zero_slots(struct END_DEVICE *p) {
 unsigned int i,j;
 assert(p->free_skb && p->free_txd_num && p->free_txd_head && p->free_txd_tail && p->txd_pool_info && p->skb_free && p->rls_cnt && p->netrx0_skb_data);
 for(i=0;i<num_tx_desc;i++) assert(!p->free_skb[i] && !p->skb_free[i] && !p->txd_pool_info[i]);
 for(i=0;i<total_txq_num;i++) assert(!p->free_txd_num[i] && !p->free_txd_head[i] && !p->free_txd_tail[i] && !p->rls_cnt[i]);
 for(i=0;i<num_rx_desc;i++) {assert(!p->netrx0_skb_data[i]);for(j=0;j<4;j++) {assert(p->netrx_skb_data[j]);assert(!p->netrx_skb_data[j][i]);}}
}
static void **owner_slot(struct END_DEVICE *p,unsigned int i) {
 switch(i) {
 case 0:return (void**)&p->free_skb; case 1:return (void**)&p->free_txd_num;
 case 2:return (void**)&p->free_txd_head;case 3:return (void**)&p->free_txd_tail;
 case 4:return (void**)&p->txd_pool_info;case 5:return (void**)&p->skb_free;
 case 6:return (void**)&p->rls_cnt;case 7:return (void**)&p->netrx0_skb_data;
 default:assert(i<12);return (void**)&p->netrx_skb_data[i-8];
 }
}
'''
CASE_ADMISSION = '/* CASE_ADMISSION */'
SUFFIX = r'''
int main(int argc,char **argv) {
 struct END_DEVICE adapter={0};
 struct net_device dev={&adapter};
 struct properties props={{1,1024,1,1024,1024}};
 struct platform_device pdev={{&props}};
 const char *name; int ret=0,handled=0;
 if(argc!=2) return 90;
 name=argv[1];
 /* CASE_ADMISSION */
 if(!handled) return 91;
 num_tx_desc=777;num_rx_desc=888;total_txq_num=999;
 if(!strncmp(name,"oom-",4)) fail_at=atoi(name+4);
 else if(!strncmp(name,"missing-",8)) missing=atoi(name+8);
 else if(!strncmp(name,"owned-",6)) {
  void *p=calloc(1,8);assert(p);owners[0]=p;live=1;*owner_slot(&adapter,(unsigned int)atoi(name+6))=p;
 }
 else if(!strcmp(name,"zero-txq")) props.values[0]=0;
 else if(!strcmp(name,"zero-txd")) props.values[1]=0;
 else if(!strcmp(name,"zero-rx")) props.values[4]=0;
 else if(!strcmp(name,"tx1-overflow")) props.values[0]=0xffffffffU;
 else if(!strcmp(name,"tx2-overflow")) props.values[2]=0xffffffffU;
 else if(!strcmp(name,"tx-sum-overflow")) {props.values[1]=0xfffffffeU;props.values[3]=2;}
 else if(!strcmp(name,"single-gmac")) {props.values[2]=0;props.values[3]=0;}
 else if(!strcmp(name,"retry")) fail_at=3;
 if(!strncmp(name,"napi-",5)) {
  if(strcmp(name,"napi-none")) adapter.features=FE_INT_NAPI;
  if(!strcmp(name,"napi-full")) adapter.napi.active=1;
  if(!strcmp(name,"napi-split")) {adapter.features|=FE_INT_NAPI_TX_RX;adapter.napi_tx.active=1;adapter.napi_rx.active=1;}
  if(!strcmp(name,"napi-rx")) {adapter.features|=FE_INT_NAPI_RX_ONLY;adapter.napi_rx.active=1;}
  if(!strcmp(name,"napi-rss2")) {adapter.features|=FE_INT_NAPI_RX_ONLY|FE_RSS_2RING;adapter.napi_rx_rss0.active=1;adapter.napi_rx_rss1.active=1;}
  if(!strcmp(name,"napi-rss4")) {adapter.features|=FE_INT_NAPI_RX_ONLY|FE_RSS_4RING;adapter.napi_rx_rss0.active=1;adapter.napi_rx_rss1.active=1;adapter.napi_rx_rss2.active=1;adapter.napi_rx_rss3.active=1;}
  ei_uninit(&dev);
 } else {
  ret=fe_tx_rx_dec(&adapter,&pdev);
  if(!strcmp(name,"retry")) {assert(ret==-ENOMEM && !live);fail_at=0;ret=fe_tx_rx_dec(&adapter,&pdev);}
  if(!ret) {
   check_zero_slots(&adapter);
   if(!strcmp(name,"late-register-failure")) {adapter.features=FE_INT_NAPI;adapter.napi.active=1;ei_uninit(&dev);}
   fe_tx_rx_dec_free(&adapter);fe_tx_rx_dec_free(&adapter);
  } else if(strncmp(name,"owned-",6)) {
   assert(!live);fe_tx_rx_dec_free(&adapter);
  }
 }
 printf("{\"ret\":%d,\"live\":%d,\"allocs\":%d,\"frees\":%d,\"reads\":%d,\"napi_deleted\":%d,\"tx\":%u,\"rx\":%u,\"queues\":%u}\n",ret,live,allocs,frees,reads,napi_deleted,num_tx_desc,num_rx_desc,total_txq_num);
 if(!strncmp(name,"owned-",6)) fe_tx_rx_dec_free(&adapter);
 assert(!live);
 return 0;
}
'''
def function(text,name):
    matches=list(re.finditer(r'(?m)^(?:static\s+)?(?:int|void)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',text))
    if len(matches)!=1: raise ValueError('Missing/ambiguous whole function '+name)
    start=matches[0].start(); pos=matches[0].end(); depth=1
    while depth and pos<len(text):
        if text[pos]=='{':depth+=1
        if text[pos]=='}':depth-=1
        pos+=1
    if depth:raise ValueError('Incomplete function '+name)
    return text[start:pos]
def function_manifest(texts):
    return {n:hashlib.sha256(function(texts[k],n).encode()).hexdigest()for n,k in FUNCTION_SOURCES.items()}
def source_only_manifest(texts):
    return {n:hashlib.sha256(function(texts[k],n).encode()).hexdigest()for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False):
    if set(texts)!=set(SOURCE_PATHS) or baseline is not False:raise ValueError('Exact current RAETH source required')
    admission='\n'.join('if(!strcmp(name,"'+n+'")) handled=1;'for n in CASE_NAMES)
    return PREFIX+'\n'+'\n\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+'\n'+SUFFIX.replace(CASE_ADMISSION,admission)
