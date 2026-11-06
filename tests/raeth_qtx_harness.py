"""Whole active QDMA TX functions with inert DMA/MMIO and synthetic packet/descriptor layouts."""
import hashlib
import re
SOURCE_PATHS = {'qdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_qdma.c',
                'header': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.h'}
BODY_ORDER = ('cal_frag_txd_num',
 'get_free_txd',
 'get_phy_addr',
 'ring_no_mapping',
 'qdma_tx_desc_alloc',
 'raeth_qtx_map_skb',
 'fe_qdma_tx_unmap',
 'rt2880_qdma_eth_send',
 'rt2880_qdma_eth_send_tso',
 'ei_qdma_start_xmit',
 'ei_qdma_xmit_housekeeping')
FUNCTION_SOURCES = {'cal_frag_txd_num': 'qdma',
 'get_free_txd': 'qdma',
 'get_phy_addr': 'qdma',
 'ring_no_mapping': 'qdma',
 'raeth_qtx_map_skb': 'qdma',
 'fe_qdma_tx_unmap': 'qdma',
 'rt2880_qdma_eth_send': 'qdma',
 'rt2880_qdma_eth_send_tso': 'qdma',
 'ei_qdma_start_xmit': 'qdma',
 'ei_qdma_xmit_housekeeping': 'qdma',
 'qdma_tx_desc_alloc': 'qdma'}
SOURCE_ONLY_FUNCTION_SOURCES = {'fe_qdma_tx_dma_deinit': 'qdma', 'init_pseudo_link_list': 'qdma'}
FUNCTION_DECLARATIONS = ''
SOURCE_FRAGMENTS = {'header': ('struct raeth_qtx_mapping {','struct raeth_qtx_mapping *qtx_mapping;')}
MODEL_VARIANT = {'reduced_tx_descriptors':32,'reduced_fragment_limit':4,'reduced_segment_length':8,
                 'synthetic_skb_and_descriptor_layout':True,'whole_function_execution':True,
                 'DMA_MMIO_cache_sync_inert':True,'lock_depth_checked_not_kernel_scheduling':True,
                 'linear_head_preserves_existing_MT7621_identity_DMA_assumption':True,
                 'idle_stop_source_only_in_this_component':True,'constructor_list_initialization_is_an_inert_seam':True,
                 'hardware_completion_list_is_supplied_by_test':True}
FIELDS = ('ret','maps','unmaps','live','hw','free_desc','queued','freed','dropped','locks','errors')
CASE_NAMES = ('linear',
 'fragment',
 'three-fragments',
 'split-fragment',
 'split-head',
 'complete',
 'complete-split',
 'double-complete',
 'close-unmap',
 'double-unmap',
 'two-netdevs',
 'map-fail-1',
 'map-fail-2',
 'map-fail-3',
 'invalid-fragment-count',
 'invalid-size',
 'invalid-total',
 'no-head',
 'quarantine',
 'stopped',
 'no-owner',
 'no-space',
 'bad-queue',
 'metadata-reuse',
 'ctor-metadata-oom',
 'ctor-coherent-oom',
 'ctor-success',
 'ctor-duplicate',
 'gso-linear',
 'gso-linear-complete')
# Independent fixed semantic rows: successes own maps until completion/idle;
# every failed map leaves the free list and hardware producer untouched.
EXPECTED_ROWS = {'linear': {'ret': 0,
            'maps': 0,
            'unmaps': 0,
            'live': 0,
            'hw': 1,
            'free_desc': 29,
            'queued': 1,
            'freed': 0,
            'dropped': 0,
            'locks': 1,
            'errors': 0},
 'fragment': {'ret': 0,
              'maps': 1,
              'unmaps': 0,
              'live': 1,
              'hw': 1,
              'free_desc': 28,
              'queued': 1,
              'freed': 0,
              'dropped': 0,
              'locks': 1,
              'errors': 0},
 'three-fragments': {'ret': 0,
                     'maps': 3,
                     'unmaps': 0,
                     'live': 3,
                     'hw': 1,
                     'free_desc': 26,
                     'queued': 1,
                     'freed': 0,
                     'dropped': 0,
                     'locks': 1,
                     'errors': 0},
 'split-fragment': {'ret': 0,
                    'maps': 1,
                    'unmaps': 0,
                    'live': 1,
                    'hw': 1,
                    'free_desc': 26,
                    'queued': 1,
                    'freed': 0,
                    'dropped': 0,
                    'locks': 1,
                    'errors': 0},
 'split-head': {'ret': 0,
                'maps': 1,
                'unmaps': 0,
                'live': 1,
                'hw': 1,
                'free_desc': 26,
                'queued': 1,
                'freed': 0,
                'dropped': 0,
                'locks': 1,
                'errors': 0},
 'complete': {'ret': 0,
              'maps': 3,
              'unmaps': 3,
              'live': 0,
              'hw': 1,
              'free_desc': 30,
              'queued': 1,
              'freed': 1,
              'dropped': 0,
              'locks': 2,
              'errors': 0},
 'complete-split': {'ret': 0,
                    'maps': 1,
                    'unmaps': 1,
                    'live': 0,
                    'hw': 1,
                    'free_desc': 30,
                    'queued': 1,
                    'freed': 1,
                    'dropped': 0,
                    'locks': 2,
                    'errors': 0},
 'double-complete': {'ret': 0,
                     'maps': 3,
                     'unmaps': 3,
                     'live': 0,
                     'hw': 1,
                     'free_desc': 30,
                     'queued': 1,
                     'freed': 1,
                     'dropped': 0,
                     'locks': 3,
                     'errors': 0},
 'close-unmap': {'ret': 0,
                 'maps': 3,
                 'unmaps': 3,
                 'live': 0,
                 'hw': 1,
                 'free_desc': 26,
                 'queued': 1,
                 'freed': 0,
                 'dropped': 0,
                 'locks': 1,
                 'errors': 0},
 'double-unmap': {'ret': 0,
                  'maps': 3,
                  'unmaps': 3,
                  'live': 0,
                  'hw': 1,
                  'free_desc': 26,
                  'queued': 1,
                  'freed': 0,
                  'dropped': 0,
                  'locks': 1,
                  'errors': 0},
 'two-netdevs': {'ret': 0,
                 'maps': 6,
                 'unmaps': 6,
                 'live': 0,
                 'hw': 2,
                 'free_desc': 30,
                 'queued': 2,
                 'freed': 2,
                 'dropped': 0,
                 'locks': 3,
                 'errors': 0},
 'map-fail-1': {'ret': 0,
                'maps': 0,
                'unmaps': 0,
                'live': 0,
                'hw': 0,
                'free_desc': 30,
                'queued': 0,
                'freed': 1,
                'dropped': 1,
                'locks': 1,
                'errors': 0},
 'map-fail-2': {'ret': 0,
                'maps': 1,
                'unmaps': 1,
                'live': 0,
                'hw': 0,
                'free_desc': 30,
                'queued': 0,
                'freed': 1,
                'dropped': 1,
                'locks': 1,
                'errors': 0},
 'map-fail-3': {'ret': 0,
                'maps': 2,
                'unmaps': 2,
                'live': 0,
                'hw': 0,
                'free_desc': 30,
                'queued': 0,
                'freed': 1,
                'dropped': 1,
                'locks': 1,
                'errors': 0},
 'invalid-fragment-count': {'ret': 0,
                            'maps': 0,
                            'unmaps': 0,
                            'live': 0,
                            'hw': 0,
                            'free_desc': 30,
                            'queued': 0,
                            'freed': 1,
                            'dropped': 1,
                            'locks': 1,
                            'errors': 0},
 'invalid-size': {'ret': 0,
                  'maps': 0,
                  'unmaps': 0,
                  'live': 0,
                  'hw': 0,
                  'free_desc': 30,
                  'queued': 0,
                  'freed': 1,
                  'dropped': 1,
                  'locks': 1,
                  'errors': 0},
 'invalid-total': {'ret': 0,
                   'maps': 0,
                   'unmaps': 0,
                   'live': 0,
                   'hw': 0,
                   'free_desc': 30,
                   'queued': 0,
                   'freed': 1,
                   'dropped': 1,
                   'locks': 1,
                   'errors': 0},
 'no-head': {'ret': 0,
             'maps': 0,
             'unmaps': 0,
             'live': 0,
             'hw': 0,
             'free_desc': 30,
             'queued': 0,
             'freed': 1,
             'dropped': 1,
             'locks': 1,
             'errors': 0},
 'quarantine': {'ret': 0,
                'maps': 0,
                'unmaps': 0,
                'live': 0,
                'hw': 0,
                'free_desc': 30,
                'queued': 0,
                'freed': 1,
                'dropped': 1,
                'locks': 1,
                'errors': 0},
 'stopped': {'ret': 0,
             'maps': 0,
             'unmaps': 0,
             'live': 0,
             'hw': 0,
             'free_desc': 30,
             'queued': 0,
             'freed': 1,
             'dropped': 1,
             'locks': 1,
             'errors': 0},
 'no-owner': {'ret': 0,
              'maps': 0,
              'unmaps': 0,
              'live': 0,
              'hw': 0,
              'free_desc': 30,
              'queued': 0,
              'freed': 1,
              'dropped': 1,
              'locks': 1,
              'errors': 0},
 'no-space': {'ret': 0,
              'maps': 0,
              'unmaps': 0,
              'live': 0,
              'hw': 0,
              'free_desc': 2,
              'queued': 0,
              'freed': 1,
              'dropped': 1,
              'locks': 1,
              'errors': 0},
 'bad-queue': {'ret': 0,
               'maps': 0,
               'unmaps': 0,
               'live': 0,
               'hw': 0,
               'free_desc': 30,
               'queued': 0,
               'freed': 1,
               'dropped': 1,
               'locks': 1,
               'errors': 0},
 'metadata-reuse': {'ret': 0,
                    'maps': 3,
                    'unmaps': 0,
                    'live': 3,
                    'hw': 1,
                    'free_desc': 26,
                    'queued': 1,
                    'freed': 0,
                    'dropped': 0,
                    'locks': 1,
                    'errors': 0},
 'ctor-metadata-oom': {'ret': 0,
                       'maps': 0,
                       'unmaps': 0,
                       'live': 0,
                       'hw': 0,
                       'free_desc': 30,
                       'queued': 0,
                       'freed': 0,
                       'dropped': 0,
                       'locks': 0,
                       'errors': 0},
 'ctor-coherent-oom': {'ret': 0,
                       'maps': 0,
                       'unmaps': 0,
                       'live': 0,
                       'hw': 0,
                       'free_desc': 30,
                       'queued': 0,
                       'freed': 0,
                       'dropped': 0,
                       'locks': 0,
                       'errors': 0},
 'ctor-success': {'ret': 1,
                  'maps': 0,
                  'unmaps': 0,
                  'live': 0,
                  'hw': 1,
                  'free_desc': 30,
                  'queued': 0,
                  'freed': 0,
                  'dropped': 0,
                  'locks': 0,
                  'errors': 0},
 'ctor-duplicate': {'ret': 0,
                    'maps': 0,
                    'unmaps': 0,
                    'live': 0,
                    'hw': 0,
                    'free_desc': 30,
                    'queued': 0,
                    'freed': 0,
                    'dropped': 0,
                    'locks': 0,
                    'errors': 0},
 'gso-linear': {'ret': 0,
                'maps': 0,
                'unmaps': 0,
                'live': 0,
                'hw': 1,
                'free_desc': 29,
                'queued': 1,
                'freed': 0,
                'dropped': 0,
                'locks': 1,
                'errors': 0},
 'gso-linear-complete': {'ret': 0,
                         'maps': 0,
                         'unmaps': 0,
                         'live': 0,
                         'hw': 1,
                         'free_desc': 30,
                         'queued': 1,
                         'freed': 1,
                         'dropped': 0,
                         'locks': 2,
                         'errors': 0}}
PREFIX = r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#ifdef __clang__
#pragma clang diagnostic ignored "-Wself-assign"
#endif
typedef uint32_t dma_addr_t;
typedef uint32_t u32;
#define MAX_SKB_FRAGS 4
#define MAX_QTXD_LEN 8U
#define QTXD_LEN 16U
#define TOTAL_TXQ_NUM 2
#define DMA_TO_DEVICE 1
#define CHECKSUM_PARTIAL 1
#define FE_TSO 1U
#define FE_TSO_V6 2U
#define FE_GE2_SUPPORT 4U
#define FE_INT_NAPI 8U
#define FE_HW_SFQ 16U
#define FE_CSUM_OFFLOAD 32U
#define FE_HW_VLAN_TX 64U
#define QDMA_QOS_MARK 128U
#define QDMA_QOS_WEB 256U
#define MT7622_FE 2
#define LEOPARD_FE 3
#define HW_SFQ_DL 2
#define HW_SFQ_UP 3
#define IPPROTO_TCP 6
#define NEXTHDR_TCP 6
#define QTX_CTX_PTR 0
#define QTX_DRX_PTR 1
#define QTX_CRX_PTR 2
#define QTX_DTX_PTR 3
#define QTX_SCH_1 4
#define QTX_CFG_0 8
#define QDMA_PAGE 5
#define NUM_PQ 2
#define NUM_PQ_RESV 4
#define QUEUE_OFFSET 1
#define MT7623_FE 4
#define MT7621_FE 1
#define GFP_KERNEL 0
#define READ_ONCE(x) (x)
#define likely(x) (x)
#define unlikely(x) (x)
#define pr_debug(...) ((void)0)
#define pr_err(...) ((void)0)
#define wmb() ((void)0)
#define virt_to_phys(p) ((dma_addr_t)(uintptr_t)(p))
#undef htons
#define htons(x) (x)
struct device { int dummy; };
struct platform_device { struct device dev; };
struct net_device { void *priv; unsigned int trans_start; };
struct net_device_stats { unsigned int tx_packets,tx_bytes,tx_dropped; };
struct PSEUDO_ADAPTER { struct net_device_stats stat; };
struct skb_frag_struct { struct {void *p;} page; unsigned int page_offset,size; };
struct skb_shared_info { unsigned int nr_frags,gso_segs,gso_size; struct skb_frag_struct frags[MAX_SKB_FRAGS]; };
struct sk_buff {unsigned int len,data_len,mark,queue_mapping,ip_summed; unsigned char *data; struct skb_shared_info sh;int freed;};
struct iphdr {unsigned int version,protocol;};
struct ipv6hdr {unsigned int version,nexthdr;};
struct tcphdr {unsigned int check;};
struct QDMA_txdesc {
 struct {dma_addr_t SDP;} txd_info1;
 struct {dma_addr_t NDP;} txd_info2;
 struct {unsigned int SDL,LS_bit,OWN_bit,SWC_bit,PROT,IPOFST,QID;} txd_info3;
 struct {unsigned int SDL,FPORT,TSO,QID,VQID0,TUI_CO,VLAN_TAG;} txd_info4;
};
struct raeth_qtx_mapping {dma_addr_t addr;unsigned int len;};
struct END_DEVICE {
 struct platform_device *qdma_pdev;struct net_device *pseudo_dev;
 struct QDMA_txdesc *txd_pool;struct raeth_qtx_mapping *qtx_mapping;
 unsigned int features,chip_name,tx_cpu_idx,rls_cpu_idx,phy_txd_pool;
 unsigned int *free_txd_head,*free_txd_tail,*txd_pool_info;int *free_txd_num;
 struct sk_buff **skb_free;int page_lock,dma_quarantined,irq_active,tx_full,tx_ring_full;
 struct net_device_stats stat;
};
static struct net_device *dev_raether;
static int constructor,alloc_step,alloc_fail,alloc_live;
static unsigned int num_tx_desc=32,gmac1_txq_num=1,gmac2_txq_num=0,gmac1_txd_num=32,gmac1_txq_txd_num=32,gmac2_txq_txd_num=0;
static unsigned int lan_wan_separate,web_sfq_enable,sfq_prot,jiffies;
static struct {unsigned int vlan1_gap;} sfq_parse_result;
static struct sk_buff *magic_id=(struct sk_buff *)(uintptr_t)0xffffffff;
static struct {int magic;} fake_cb;
#define HNAT_SKB_CB2(skb) (&fake_cb)
#define skb_shinfo(skb) (&(skb)->sh)
#define skb_network_header(skb) ((skb)->data)
#define skb_transport_header(skb) ((skb)->data+16)
#define netdev_priv(dev) ((dev)->priv)
#define skb_vlan_tag_present(skb) 0
#define skb_vlan_tag_get(skb) 0U
static inline void sfq_parse_layer_info(struct sk_buff *s){(void)s;}
static int lock_depth,locks,errors,map_calls,maps,unmaps,live,fail_map,hw,freed;
static unsigned int regs[32],map_lengths[16];

static inline void *kcalloc(unsigned int n,unsigned int size,int flags){(void)flags;alloc_step++;if(alloc_step==alloc_fail)return NULL;void*p=calloc(n,size);if(p)alloc_live++;return p;}
static inline void kfree(void*p){if(p){alloc_live--;free(p);}}
static inline void *dma_alloc_coherent(struct device*d,unsigned int size,dma_addr_t *phy,int flags){(void)d;(void)size;(void)flags;alloc_step++;if(alloc_step==alloc_fail)return NULL;*phy=0x1000;void*p=calloc(num_tx_desc,sizeof(struct QDMA_txdesc));if(p)alloc_live++;return p;}
static inline void init_pseudo_link_list(struct END_DEVICE*e){e->free_txd_num[0]=32;e->free_txd_head[0]=0;e->free_txd_tail[0]=31;}
static inline void model_lock(void){if(lock_depth++)errors++;locks++;}
static inline void model_unlock(void){if(--lock_depth)errors++;}
#define spin_lock_irqsave(lock,flags) do{(void)(lock);(flags)=0;model_lock();}while(0)
#define spin_unlock_irqrestore(lock,flags) do{(void)(lock);(void)(flags);model_unlock();}while(0)
static inline int atomic_read(int *a){if(!lock_depth&&!constructor)errors++;return *a;}
static inline void atomic_sub(int n,int *a){if(!lock_depth&&!constructor)errors++;*a-=n;}
static inline void atomic_add(int n,int *a){if(!lock_depth&&!constructor)errors++;*a+=n;}
static inline dma_addr_t dma_map_page(struct device*d,void*p,unsigned int off,unsigned int len,int dir){
 (void)d;(void)p;(void)off;(void)dir;map_calls++;if(!lock_depth&&!constructor)errors++;
 if(map_calls==fail_map)return 0xffffffffU;
 if(map_calls>=16){errors++;return 0xffffffffU;}map_lengths[map_calls]=len;maps++;live++;return 0x4000U+map_calls*256U;
}
static inline int dma_mapping_error(struct device*d,dma_addr_t a){(void)d;return a==0xffffffffU;}
static inline void dma_unmap_page(struct device*d,dma_addr_t a,unsigned int len,int dir){
 unsigned int i=(a-0x4000U)/256U;(void)d;(void)dir;
 if(i>=16||!map_lengths[i]||map_lengths[i]!=len){errors++;return;}
 map_lengths[i]=0;unmaps++;live--;
}
static inline void dma_sync_single_for_device(struct device*d,dma_addr_t a,unsigned int n,int dir){(void)d;(void)a;(void)n;(void)dir;if(!lock_depth&&!constructor)errors++;}
static inline unsigned int sys_reg_read(int r){return regs[r];}
static inline void sys_reg_write(int r,unsigned int v){if(!lock_depth&&!constructor)errors++;regs[r]=v;if(r==QTX_CTX_PTR)hw++;}
static inline void dev_kfree_skb_any(struct sk_buff*s){if(!s)return;if(s==magic_id||s->freed){errors++;return;}s->freed=1;freed++;}
static inline void netif_wake_queue(struct net_device*d){(void)d;}
'''
SUFFIX = r'''
int main(int argc,char **argv){
 const char *name;struct END_DEVICE e={0};struct platform_device pd={0};struct net_device nd={&e,0},pseudo={0};
 struct PSEUDO_ADAPTER pa={0};struct QDMA_txdesc desc[32]={0};struct raeth_qtx_mapping mapping[32]={{0}};
 struct sk_buff *owners[32]={0};unsigned int head[2]={2,0},tail[2]={31,0},info[32];int count[2]={30,0};
 unsigned char bytes[64]={0};struct sk_buff packet={0},second={0};unsigned int i,last=1,idx=1;int ret;
 if(argc!=2)return 2;
 name=argv[1];
 CASE_ADMISSION
 e.qdma_pdev=&pd;e.txd_pool=desc;e.qtx_mapping=mapping;e.skb_free=owners;e.free_txd_head=head;e.free_txd_tail=tail;e.txd_pool_info=info;e.free_txd_num=count;e.phy_txd_pool=0x1000;e.tx_cpu_idx=1;e.features=FE_TSO|FE_GE2_SUPPORT;e.irq_active=1;e.pseudo_dev=&pseudo;pseudo.priv=&pa;
 for(i=0;i<32;i++)info[i]=i+1;
 desc[0].txd_info2.NDP=e.phy_txd_pool+16;
 packet.data=bytes;packet.len=7;packet.data_len=3;packet.sh.nr_frags=3;
 for(i=0;i<3;i++){packet.sh.frags[i].size=1;packet.sh.frags[i].page.p=bytes;}
 if(!strcmp(name,"linear")){packet.sh.nr_frags=0;packet.data_len=0;packet.len=4;}
 if(!strcmp(name,"fragment")){packet.sh.nr_frags=1;packet.data_len=3;packet.sh.frags[0].size=3;}
 if(!strcmp(name,"split-fragment")||!strcmp(name,"complete-split")){packet.sh.nr_frags=1;packet.data_len=19;packet.len=23;packet.sh.frags[0].size=19;}
 if(!strcmp(name,"split-head")){packet.sh.nr_frags=1;packet.len=23;packet.data_len=3;packet.sh.frags[0].size=3;}
 if(!strncmp(name,"map-fail-",9))fail_map=atoi(name+9);
 if(!strcmp(name,"invalid-fragment-count"))packet.sh.nr_frags=5;
 if(!strcmp(name,"invalid-size"))packet.sh.frags[1].size=0;
 if(!strcmp(name,"invalid-total"))packet.sh.frags[1].size=2;
 if(!strcmp(name,"no-head"))packet.len=packet.data_len;
 if(!strcmp(name,"quarantine"))e.dma_quarantined=1;
 if(!strcmp(name,"stopped"))e.irq_active=0;
 if(!strcmp(name,"no-owner"))e.qtx_mapping=NULL;
 if(!strcmp(name,"no-space"))count[0]=2;
 if(!strcmp(name,"bad-queue"))packet.queue_mapping=3;
 if(!strcmp(name,"two-netdevs")){gmac1_txd_num=16;gmac1_txq_txd_num=16;gmac2_txq_num=1;gmac2_txq_txd_num=16;head[1]=16;tail[0]=15;count[0]=14;count[1]=16;}
 if(!strcmp(name,"metadata-reuse"))for(i=0;i<32;i++){desc[i].txd_info4.FPORT=7;desc[i].txd_info4.TUI_CO=7;desc[i].txd_info4.VLAN_TAG=123;desc[i].txd_info4.TSO=1;}

 if(!strncmp(name,"ctor-",5)){
  constructor=1;dev_raether=&nd;
  if(strcmp(name,"ctor-duplicate")){e.txd_pool=NULL;e.qtx_mapping=NULL;}
  if(!strcmp(name,"ctor-metadata-oom"))alloc_fail=1;
  if(!strcmp(name,"ctor-coherent-oom"))alloc_fail=2;
  ret=qdma_tx_desc_alloc();
  if(!strcmp(name,"ctor-success")){if(ret!=1||alloc_live!=2||!e.txd_pool||!e.qtx_mapping)errors++;kfree(e.qtx_mapping);kfree(e.txd_pool);}
  else if(!strcmp(name,"ctor-duplicate")){if(alloc_step||e.txd_pool!=desc||e.qtx_mapping!=mapping)errors++;}
  else if(alloc_live||e.txd_pool||e.qtx_mapping)errors++;
  goto report;
 }
 if(!strncmp(name,"gso-linear",10)){packet.sh.nr_frags=0;packet.data_len=0;packet.len=4;packet.sh.gso_segs=2;packet.sh.gso_size=1460;((struct iphdr*)bytes)->version=4;((struct iphdr*)bytes)->protocol=IPPROTO_TCP;}
 ret=ei_qdma_start_xmit(&packet,&nd,1);
 if(!strcmp(name,"two-netdevs")){second=packet;second.freed=0;ei_qdma_start_xmit(&second,&nd,2);}
 if(!strcmp(name,"gso-linear-complete")||!strcmp(name,"complete")||!strcmp(name,"complete-split")||!strcmp(name,"double-complete")||!strcmp(name,"two-netdevs")){
  for(i=0;i<32;i++){last=idx;idx=(desc[idx].txd_info2.NDP-e.phy_txd_pool)/16;if(idx==e.tx_cpu_idx)break;}
  if(i==32)errors++;
  regs[QTX_DRX_PTR]=e.phy_txd_pool+last*16;ei_qdma_xmit_housekeeping(&nd,32);
  if(!strcmp(name,"double-complete"))ei_qdma_xmit_housekeeping(&nd,32);
 }
 if(!strcmp(name,"close-unmap")||!strcmp(name,"double-unmap")){
  for(i=0;i<32;i++)fe_qdma_tx_unmap(&e,i);
  if(!strcmp(name,"double-unmap"))for(i=0;i<32;i++)fe_qdma_tx_unmap(&e,i);
 }
 if(!strcmp(name,"metadata-reuse")){idx=1;for(i=0;i<32&&idx!=e.tx_cpu_idx;i++){if(desc[idx].txd_info4.FPORT!=1||desc[idx].txd_info4.TUI_CO||desc[idx].txd_info4.VLAN_TAG||desc[idx].txd_info4.TSO)errors++;idx=(desc[idx].txd_info2.NDP-e.phy_txd_pool)/16;}}
 if(!strncmp(name,"gso-linear",10)&&(desc[1].txd_info4.TSO!=1||((struct tcphdr*)(bytes+16))->check!=1460))errors++;
 report:
 if(lock_depth)errors++;
 printf("{\"ret\":%d,\"maps\":%d,\"unmaps\":%d,\"live\":%d,\"hw\":%d,\"free_desc\":%d,\"queued\":%u,\"freed\":%d,\"dropped\":%u,\"locks\":%d,\"errors\":%d}\n",ret,maps,unmaps,live,hw,count[0]+count[1],e.stat.tx_packets+pa.stat.tx_packets,freed,e.stat.tx_dropped+pa.stat.tx_dropped,locks,errors);return 0;
}
'''

def function(text,name):
    masked=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',lambda m:' '*len(m.group()),text,flags=re.S)
    found=list(re.finditer(r'(?:static\s+)?(?:inline\s+)?(?:unsigned\s+int|int|void|bool)\s+\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked))
    if len(found)!=1:raise ValueError('Missing/ambiguous QTX body: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer('[{}]',masked[opening:]):
        depth+=1 if m.group()=='{' else -1
        if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated QTX body: '+name)
def validate_inputs(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact QTX source inputs required')
    for key,fragments in SOURCE_FRAGMENTS.items():
        for fragment in fragments:
            if fragment not in texts[key]:raise ValueError('QTX ownership declaration changed: '+fragment)
    for name,key in dict(FUNCTION_SOURCES,**SOURCE_ONLY_FUNCTION_SOURCES).items():function(texts[key],name)
def function_manifest(texts):
    validate_inputs(texts)
    return {n:dict(source=k,execution='whole-function',full_body_sha256=hashlib.sha256(function(texts[k],n).encode()).hexdigest())for n,k in FUNCTION_SOURCES.items()}
def source_only_manifest(texts):
    validate_inputs(texts)
    return {n:dict(source=k,execution='source-only-not-run',full_body_sha256=hashlib.sha256(function(texts[k],n).encode()).hexdigest())for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
def generate_source(texts):
    validate_inputs(texts)
    admission='if ('+' && '.join('strcmp(name,"'+n+'")'for n in CASE_NAMES)+') return 2;'
    return PREFIX+'\n'+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+'\n'+SUFFIX.replace('CASE_ADMISSION',admission)
