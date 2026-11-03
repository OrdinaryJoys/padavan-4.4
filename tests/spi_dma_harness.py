"""Actual SPI mapping and SG allocation/free bodies under inert DMA seams.

No kernel, router, device, MMIO or process-control operation is executed. The
small SG chunk size exercises the actual chained-table algorithm. Allocator and
DMA callbacks and SG link/iterator primitives track logical bounds/ownership;
fixture teardown follows recording.
"""
import hashlib
import re

SOURCE_PATHS = {'core': 'trunk/linux-4.4.x/drivers/spi/spi.c',
                'scatterlist': 'trunk/linux-4.4.x/lib/scatterlist.c'}
FUNCTIONS = {'core': ('spi_map_buf', 'spi_unmap_buf', '__spi_map_msg',
                      '__spi_unmap_msg', 'spi_map_msg', 'spi_unmap_msg'),
             'scatterlist': ('__sg_free_table', 'sg_free_table',
                             '__sg_alloc_table', 'sg_alloc_table')}
BASELINE_COMMIT = '6e91276a33d1bd83d416fc8253feb01f30677743'


def extract(text, name):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked = re.sub(tokens, lambda m: ' ' * len(m.group()), text)
    pattern = (r'(?:static\s+)?(?:inline\s+)?(?:void|int)\s+\b' +
               re.escape(name) + r'\s*\([^;{}]*\)\s*\{')
    matches = list(re.finditer(pattern, masked))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous DMA function: ' + name)
    start = matches[0].start(); opening = text.index('{', start); depth = 0
    for item in re.finditer(tokens + r'|[{}]', text[opening:]):
        if item.group() == '{': depth += 1
        elif item.group() == '}':
            depth -= 1
            if not depth: return text[start:opening + item.end()]
    raise ValueError('Unterminated DMA function: ' + name)


def actual_functions(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact DMA source manifest required')
    out = {}
    for key, names in FUNCTIONS.items():
        text = texts[key]
        if key == 'core':
            text = text[:text.index('#else /* !CONFIG_HAS_DMA */')] + text[
                text.index('#endif /* !CONFIG_HAS_DMA */'):]
        for name in names:
            out[name] = {'source_key': key, 'body': extract(text, name)}
    return out


PREFIX = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <limits.h>
#undef ENOMEM
#undef EINVAL
#define ENOMEM 12
#define EINVAL 22
typedef int bool;
#define true 1
#define false 0
typedef unsigned gfp_t;
#define GFP_KERNEL 0
#define GFP_DMA 0
#define SG_MAX_SINGLE_ALLOC 4
#define CONFIG_ARCH_HAS_SG_CHAIN 1
#define PAGE_SIZE 16
#define unlikely(x) (x)
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define SPI_MASTER_MUST_TX 1
#define SPI_MASTER_MUST_RX 2
struct list_head {struct list_head *next,*prev;};
static void INIT_LIST_HEAD(struct list_head*h){h->next=h;h->prev=h;}
static void list_add_tail(struct list_head*n,struct list_head*h){n->prev=h->prev;n->next=h;h->prev->next=n;h->prev=n;}
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) for(p=container_of((h)->next,__typeof__(*p),m);&(p)->m!=(h);p=container_of((p)->m.next,__typeof__(*p),m))
struct page {uintptr_t address;};
struct scatterlist {struct scatterlist *chain;void*buf;size_t len;int is_chain,is_last;};
struct sg_table {struct scatterlist *sgl;unsigned nents,orig_nents;};
typedef struct scatterlist *sg_alloc_fn(unsigned int,gfp_t);
typedef void sg_free_fn(struct scatterlist*,unsigned int);
struct device {int id;};
struct model_dma_device {struct device*dev;};
struct model_dma_channel {struct model_dma_device*device;};
enum dma_data_direction {DMA_TO_DEVICE=1,DMA_FROM_DEVICE=2};
struct spi_master;
struct spi_device {struct spi_master*master;};
struct spi_transfer {struct list_head transfer_list;const void*tx_buf;void*rx_buf;unsigned len;uintptr_t tx_dma,rx_dma;struct sg_table tx_sg,rx_sg;};
struct spi_message {struct list_head transfers;struct spi_device*spi;unsigned is_dma_mapped;};
struct spi_master {int(*can_dma)(struct spi_master*,struct spi_device*,struct spi_transfer*);struct model_dma_channel*dma_tx,*dma_rx;struct {struct device*parent;} dev;size_t max_dma_len;bool cur_msg_mapped;unsigned flags;void*dummy_tx,*dummy_rx;};
static struct spi_master master;
static struct spi_device spi;
static struct spi_message msg;
static struct spi_transfer transfers[3];
static unsigned char buffers[3][2][256] __attribute__((aligned(16)));
static struct device parent={1},tx_device={2},rx_device={3};
static struct model_dma_device tx_dma_device={&tx_device},rx_dma_device={&rx_device};
static struct model_dma_channel tx_channel={&tx_dma_device},rx_channel={&rx_dma_device};
static struct {struct scatterlist*ptr;unsigned size;int live;} blocks[128];
static struct {struct scatterlist*ptr;struct device*dev;unsigned original;int dir,live;} mappings[64];
static struct page pages[128];
static int alloc_calls,allocs,frees,live_allocs,map_calls,maps,unmaps,live_maps;
static int can_calls,bad_sg,invalid_free,invalid_unmap,wrong_entries,wrong_device,wrong_segments;
static int fail_alloc,fail_map,fail_page,vmalloc_mode,page_calls,merge_mode,eligibility_changed;
static int eligibility_middle,fail_dummy,dummy_allocs,unmap_calls,result,result2,first_live_maps;
static char sequence[256];static unsigned sequence_len;
static void event(char c){if(sequence_len+1<sizeof(sequence)){sequence[sequence_len++]=c;sequence[sequence_len]=0;}}
static int valid_sg(struct scatterlist*sg){int i;uintptr_t a=(uintptr_t)sg;for(i=0;i<128;i++)if(blocks[i].live){uintptr_t lo=(uintptr_t)blocks[i].ptr,hi=lo+blocks[i].size*sizeof(*sg);if(a>=lo&&a<hi&&(a-lo)%sizeof(*sg)==0&&!sg->is_chain)return 1;}bad_sg++;return 0;}
static struct scatterlist*sg_kmalloc(unsigned n,gfp_t flags){int i;(void)flags;alloc_calls++;event('a');if(alloc_calls==fail_alloc)return NULL;for(i=0;i<128;i++)if(!blocks[i].live){/* Extra backing storage permits observing old logical out-of-bounds without executing UB. */blocks[i].ptr=calloc(n+32,sizeof(struct scatterlist));if(!blocks[i].ptr)abort();blocks[i].size=n;blocks[i].live=1;allocs++;live_allocs++;return blocks[i].ptr;}abort();}
static void sg_kfree(struct scatterlist*p,unsigned n){int i;for(i=0;i<128;i++)if(blocks[i].live&&blocks[i].ptr==p){if(blocks[i].size!=n)invalid_free++;blocks[i].live=0;free(p);frees++;live_allocs--;event('f');return;}invalid_free++;}
static void sg_init_table(struct scatterlist*p,unsigned n){memset(p,0,n*sizeof(*p));p[n-1].is_last=1;}
static void sg_mark_end(struct scatterlist*p){p->is_chain=0;p->is_last=1;}
static void sg_chain(struct scatterlist*p,unsigned n,struct scatterlist*next){p[n-1].is_last=0;p[n-1].is_chain=1;p[n-1].chain=next;}
static struct scatterlist*sg_chain_ptr(struct scatterlist*p){return p->chain;}
static struct scatterlist*sg_next(struct scatterlist*p){if(!p||p->is_last)return NULL;p++;if(p->is_chain)return p->chain;return p;}
#define for_each_sg(head,sg,n,i) for(i=0,sg=(head);i<(n);i++,sg=sg_next(sg))
static int is_vmalloc_addr(void*p){(void)p;return vmalloc_mode;}
#define offset_in_page(p) ((uintptr_t)(p)&(PAGE_SIZE-1))
static struct page*vmalloc_to_page(void*p){int i;page_calls++;if(page_calls==fail_page)return NULL;i=page_calls%128;pages[i].address=(uintptr_t)p&~(uintptr_t)(PAGE_SIZE-1);return &pages[i];}
static void sg_set_buf(struct scatterlist*sg,void*p,size_t len){if(!valid_sg(sg))return;sg->buf=p;sg->len=len;}
static void sg_set_page(struct scatterlist*sg,struct page*p,size_t len,size_t off){if(!valid_sg(sg))return;sg->buf=(void*)(p->address+off);sg->len=len;}
static int dma_map_sg(struct device*dev,struct scatterlist*sg,unsigned n,enum dma_data_direction dir){unsigned j;int i;struct scatterlist*item=sg;void*previous=NULL;map_calls++;event('M');if(map_calls==fail_map)return 0;for(j=0;j<n;j++){if(!item||!valid_sg(item)){wrong_segments++;break;}if(!item->len||!item->buf||(previous&&item->buf!=previous))wrong_segments++;previous=item->buf?(char*)item->buf+item->len:NULL;item=sg_next(item);}for(i=0;i<64;i++)if(!mappings[i].live){mappings[i].ptr=sg;mappings[i].dev=dev;mappings[i].original=n;mappings[i].dir=dir;mappings[i].live=1;maps++;live_maps++;return merge_mode?1:(int)n;}abort();}
static void dma_unmap_sg(struct device*dev,struct scatterlist*sg,unsigned n,enum dma_data_direction dir){int i;for(i=0;i<64;i++)if(mappings[i].live&&mappings[i].ptr==sg){if(mappings[i].dev!=dev||mappings[i].dir!=(int)dir)wrong_device++;if(mappings[i].original!=n)wrong_entries++;mappings[i].live=0;live_maps--;unmaps++;event('U');return;}invalid_unmap++;}
static int eligible(struct spi_master*m,struct spi_device*s,struct spi_transfer*x){if(m!=&master||s!=&spi)abort();can_calls++;if(eligibility_changed)return 0;return !(eligibility_middle&&x==&transfers[1]);}
static void*krealloc(void*p,size_t n,unsigned flags){(void)flags;if(fail_dummy)return NULL;dummy_allocs++;return realloc(p,n);}
'''

TAIL = r'''
static void run_unmap(void){unmap_calls++;spi_unmap_msg(&master,&msg);}
int main(int argc,char**argv){int i,remaining_sg=0,dummy_restored=0,premapped_intact=1;const char*name;unsigned length=20,off=0;if(argc!=2)return 90;name=argv[1];memset(&master,0,sizeof(master));memset(&msg,0,sizeof(msg));memset(transfers,0,sizeof(transfers));INIT_LIST_HEAD(&msg.transfers);master.dev.parent=&parent;master.max_dma_len=12;master.can_dma=eligible;spi.master=&master;msg.spi=&spi;
if(!strcmp(name,"tx-fail-first"))fail_map=1;else if(!strcmp(name,"rx-fail-first"))fail_map=2;else if(!strcmp(name,"tx-fail-second"))fail_map=3;else if(!strcmp(name,"rx-fail-second"))fail_map=4;else if(!strcmp(name,"tx-fail-third"))fail_map=5;else if(!strcmp(name,"rx-fail-third"))fail_map=6;
else if(!strcmp(name,"alloc-fail-first"))fail_alloc=1;else if(!strcmp(name,"alloc-fail-second"))fail_alloc=2;else if(!strcmp(name,"alloc-fail-later"))fail_alloc=5;
else if(!strcmp(name,"vmalloc-page-first")){vmalloc_mode=1;fail_page=1;}else if(!strcmp(name,"vmalloc-page-later")){vmalloc_mode=1;fail_page=5;}
else if(!strcmp(name,"chained-linear")){length=60;master.max_dma_len=8;}else if(!strcmp(name,"chained-vmalloc")){length=100;vmalloc_mode=1;}else if(!strcmp(name,"chained-offset-vmalloc")){length=99;off=3;vmalloc_mode=1;}
else if(!strcmp(name,"chain-alloc-partial-fail")){length=60;master.max_dma_len=8;fail_alloc=2;}else if(!strcmp(name,"chain-alloc-later-fail")){length=60;master.max_dma_len=8;fail_alloc=5;}else if(!strcmp(name,"chain-map-later-fail")){length=60;master.max_dma_len=8;fail_map=3;}
else if(!strcmp(name,"unlimited-dma-length"))master.max_dma_len=(size_t)-1;
else if(!strcmp(name,"dma-merge"))merge_mode=1;else if(!strcmp(name,"no-dma")||!strcmp(name,"no-dma-stale"))master.can_dma=NULL;else if(!strcmp(name,"ineligible-middle"))eligibility_middle=1;else if(!strcmp(name,"zero-length"))length=0;else if(!strcmp(name,"separate-dma-devices")){master.dma_tx=&tx_channel;master.dma_rx=&rx_channel;}
else if(!strcmp(name,"dummy-alloc-fail")){master.flags=SPI_MASTER_MUST_TX;fail_dummy=1;}else if(!strcmp(name,"dummy-restore"))master.flags=SPI_MASTER_MUST_TX;
else if(!strcmp(name,"premapped-addresses"))msg.is_dma_mapped=1;
else if(strcmp(name,"normal")&&strcmp(name,"eligibility-changes")&&strcmp(name,"eligibility-removed")&&strcmp(name,"double-unmap")&&strcmp(name,"reuse-message")&&strcmp(name,"retry-after-failure")&&strcmp(name,"tx-only")&&strcmp(name,"rx-only")&&strcmp(name,"mixed-zero"))return 91;
if(!strcmp(name,"no-dma-stale"))master.cur_msg_mapped=1;
for(i=0;i<3;i++){transfers[i].len=length;transfers[i].tx_buf=buffers[i][0]+off;transfers[i].rx_buf=buffers[i][1]+off;transfers[i].tx_dma=17+i;transfers[i].rx_dma=29+i;if(!strcmp(name,"tx-only"))transfers[i].rx_buf=NULL;if(!strcmp(name,"rx-only")||((master.flags&SPI_MASTER_MUST_TX)&&i==1))transfers[i].tx_buf=NULL;if(!strcmp(name,"mixed-zero")&&i==1)transfers[i].len=0;list_add_tail(&transfers[i].transfer_list,&msg.transfers);}
if(!strcmp(name,"retry-after-failure"))fail_map=3;
result=spi_map_msg(&master,&msg);if(!strcmp(name,"eligibility-changes"))eligibility_changed=1;if(!strcmp(name,"eligibility-removed"))master.can_dma=NULL;run_unmap();first_live_maps=live_maps;
if(!strcmp(name,"double-unmap"))run_unmap();
if(!strcmp(name,"reuse-message")||!strcmp(name,"retry-after-failure")){fail_map=0;result2=spi_map_msg(&master,&msg);run_unmap();}
for(i=0;i<3;i++){remaining_sg+=!!transfers[i].tx_sg.orig_nents+!!transfers[i].rx_sg.orig_nents;if((master.flags&SPI_MASTER_MUST_TX)&&i==1&&transfers[i].tx_buf==NULL)dummy_restored++;if(transfers[i].tx_dma!=(uintptr_t)(17+i)||transfers[i].rx_dma!=(uintptr_t)(29+i))premapped_intact=0;}
printf("{\"case\":\"%s\",\"result\":%d,\"result2\":%d,\"alloc_calls\":%d,\"allocs\":%d,\"frees\":%d,\"live_allocs\":%d,\"map_calls\":%d,\"maps\":%d,\"unmaps\":%d,\"live_maps\":%d,\"can_calls\":%d,\"bad_sg\":%d,\"invalid_free\":%d,\"invalid_unmap\":%d,\"wrong_entries\":%d,\"wrong_device\":%d,\"wrong_segments\":%d,\"mapped_flag\":%d,\"remaining_sg\":%d,\"first_live_maps\":%d,\"page_calls\":%d,\"dummy_allocs\":%d,\"dummy_restored\":%d,\"premapped_intact\":%d,\"unmap_calls\":%d,\"sequence\":\"%s\"}\n",name,result,result2,alloc_calls,allocs,frees,live_allocs,map_calls,maps,unmaps,live_maps,can_calls,bad_sg,invalid_free,invalid_unmap,wrong_entries,wrong_device,wrong_segments,master.cur_msg_mapped,remaining_sg,first_live_maps,page_calls,dummy_allocs,dummy_restored,premapped_intact,unmap_calls,sequence);
/* Release only private model backing memory after observations. This does not
 * invoke production unmap or conceal the recorded baseline leaks. */
for(i=0;i<128;i++){if(blocks[i].live)free(blocks[i].ptr);}
free(master.dummy_tx);free(master.dummy_rx);return 0;}
'''

CASE_NAMES = ('normal','tx-fail-first','rx-fail-first','tx-fail-second',
              'rx-fail-second','tx-fail-third','rx-fail-third','alloc-fail-first',
              'alloc-fail-second','alloc-fail-later','vmalloc-page-first',
              'vmalloc-page-later','chained-linear','chained-vmalloc',
              'chained-offset-vmalloc','chain-alloc-partial-fail',
              'chain-alloc-later-fail','chain-map-later-fail','dma-merge',
              'no-dma','no-dma-stale','ineligible-middle','zero-length',
              'separate-dma-devices','dummy-alloc-fail','dummy-restore',
              'premapped-addresses','eligibility-changes','eligibility-removed',
              'double-unmap','reuse-message','retry-after-failure','tx-only',
              'rx-only','mixed-zero','unlimited-dma-length')
BASELINE_CASE_NAMES = ('normal','tx-fail-second','rx-fail-third','chained-linear',
                       'chained-vmalloc','eligibility-changes','zero-length',
                       'retry-after-failure','unlimited-dma-length')


def generate_source(texts, baseline=False):
    if type(baseline) is not bool:
        raise ValueError('Typed DMA generation arguments required')
    actual = actual_functions(texts)
    if baseline:
        if set(BASELINE_FUNCTIONS) != set(actual):
            raise ValueError('Exact DMA baseline manifest required')
        for name, body in BASELINE_FUNCTIONS.items():
            if hashlib.sha256(body.encode()).hexdigest() != BASELINE_HASHES[name]:
                raise ValueError('Changed literal DMA baseline: ' + name)
        bodies = BASELINE_FUNCTIONS
    else:
        bodies = {name:item['body'] for name,item in actual.items()}
    order = ('__sg_free_table','sg_free_table','__sg_alloc_table','sg_alloc_table',
             'spi_map_buf','spi_unmap_buf','__spi_map_msg','__spi_unmap_msg',
             'spi_map_msg','spi_unmap_msg')
    return PREFIX + '\n\n'.join(bodies[name] for name in order) + TAIL


BASELINE_FUNCTIONS = {'spi_map_buf': 'static int spi_map_buf(struct spi_master *master, struct device *dev,\n'
                '\t\t       struct sg_table *sgt, void *buf, size_t len,\n'
                '\t\t       enum dma_data_direction dir)\n'
                '{\n'
                '\tconst bool vmalloced_buf = is_vmalloc_addr(buf);\n'
                '\tint desc_len;\n'
                '\tint sgs;\n'
                '\tstruct page *vm_page;\n'
                '\tvoid *sg_buf;\n'
                '\tsize_t min;\n'
                '\tint i, ret;\n'
                '\n'
                '\tif (vmalloced_buf) {\n'
                '\t\tdesc_len = PAGE_SIZE;\n'
                '\t\tsgs = DIV_ROUND_UP(len + offset_in_page(buf), desc_len);\n'
                '\t} else {\n'
                '\t\tdesc_len = master->max_dma_len;\n'
                '\t\tsgs = DIV_ROUND_UP(len, desc_len);\n'
                '\t}\n'
                '\n'
                '\tret = sg_alloc_table(sgt, sgs, GFP_KERNEL);\n'
                '\tif (ret != 0)\n'
                '\t\treturn ret;\n'
                '\n'
                '\tfor (i = 0; i < sgs; i++) {\n'
                '\n'
                '\t\tif (vmalloced_buf) {\n'
                '\t\t\t/*\n'
                '\t\t\t * Next scatterlist entry size is the minimum between\n'
                '\t\t\t * the desc_len and the remaining buffer length that\n'
                '\t\t\t * fits in a page.\n'
                '\t\t\t */\n'
                '\t\t\tmin = min_t(size_t, desc_len,\n'
                '\t\t\t\t    min_t(size_t, len,\n'
                '\t\t\t\t\t  PAGE_SIZE - offset_in_page(buf)));\n'
                '\t\t\tvm_page = vmalloc_to_page(buf);\n'
                '\t\t\tif (!vm_page) {\n'
                '\t\t\t\tsg_free_table(sgt);\n'
                '\t\t\t\treturn -ENOMEM;\n'
                '\t\t\t}\n'
                '\t\t\tsg_set_page(&sgt->sgl[i], vm_page,\n'
                '\t\t\t\t    min, offset_in_page(buf));\n'
                '\t\t} else {\n'
                '\t\t\tmin = min_t(size_t, len, desc_len);\n'
                '\t\t\tsg_buf = buf;\n'
                '\t\t\tsg_set_buf(&sgt->sgl[i], sg_buf, min);\n'
                '\t\t}\n'
                '\n'
                '\n'
                '\t\tbuf += min;\n'
                '\t\tlen -= min;\n'
                '\t}\n'
                '\n'
                '\tret = dma_map_sg(dev, sgt->sgl, sgt->nents, dir);\n'
                '\tif (!ret)\n'
                '\t\tret = -ENOMEM;\n'
                '\tif (ret < 0) {\n'
                '\t\tsg_free_table(sgt);\n'
                '\t\treturn ret;\n'
                '\t}\n'
                '\n'
                '\tsgt->nents = ret;\n'
                '\n'
                '\treturn 0;\n'
                '}',
 'spi_unmap_buf': 'static void spi_unmap_buf(struct spi_master *master, struct device *dev,\n'
                  '\t\t\t  struct sg_table *sgt, enum dma_data_direction dir)\n'
                  '{\n'
                  '\tif (sgt->orig_nents) {\n'
                  '\t\tdma_unmap_sg(dev, sgt->sgl, sgt->orig_nents, dir);\n'
                  '\t\tsg_free_table(sgt);\n'
                  '\t}\n'
                  '}',
 '__spi_map_msg': 'static int __spi_map_msg(struct spi_master *master, struct spi_message *msg)\n'
                  '{\n'
                  '\tstruct device *tx_dev, *rx_dev;\n'
                  '\tstruct spi_transfer *xfer;\n'
                  '\tint ret;\n'
                  '\n'
                  '\tif (!master->can_dma)\n'
                  '\t\treturn 0;\n'
                  '\n'
                  '\tif (master->dma_tx)\n'
                  '\t\ttx_dev = master->dma_tx->device->dev;\n'
                  '\telse\n'
                  '\t\ttx_dev = master->dev.parent;\n'
                  '\n'
                  '\tif (master->dma_rx)\n'
                  '\t\trx_dev = master->dma_rx->device->dev;\n'
                  '\telse\n'
                  '\t\trx_dev = master->dev.parent;\n'
                  '\n'
                  '\tlist_for_each_entry(xfer, &msg->transfers, transfer_list) {\n'
                  '\t\tif (!master->can_dma(master, msg->spi, xfer))\n'
                  '\t\t\tcontinue;\n'
                  '\n'
                  '\t\tif (xfer->tx_buf != NULL) {\n'
                  '\t\t\tret = spi_map_buf(master, tx_dev, &xfer->tx_sg,\n'
                  '\t\t\t\t\t  (void *)xfer->tx_buf, xfer->len,\n'
                  '\t\t\t\t\t  DMA_TO_DEVICE);\n'
                  '\t\t\tif (ret != 0)\n'
                  '\t\t\t\treturn ret;\n'
                  '\t\t}\n'
                  '\n'
                  '\t\tif (xfer->rx_buf != NULL) {\n'
                  '\t\t\tret = spi_map_buf(master, rx_dev, &xfer->rx_sg,\n'
                  '\t\t\t\t\t  xfer->rx_buf, xfer->len,\n'
                  '\t\t\t\t\t  DMA_FROM_DEVICE);\n'
                  '\t\t\tif (ret != 0) {\n'
                  '\t\t\t\tspi_unmap_buf(master, tx_dev, &xfer->tx_sg,\n'
                  '\t\t\t\t\t      DMA_TO_DEVICE);\n'
                  '\t\t\t\treturn ret;\n'
                  '\t\t\t}\n'
                  '\t\t}\n'
                  '\t}\n'
                  '\n'
                  '\tmaster->cur_msg_mapped = true;\n'
                  '\n'
                  '\treturn 0;\n'
                  '}',
 '__spi_unmap_msg': 'static int __spi_unmap_msg(struct spi_master *master, struct spi_message '
                    '*msg)\n'
                    '{\n'
                    '\tstruct spi_transfer *xfer;\n'
                    '\tstruct device *tx_dev, *rx_dev;\n'
                    '\n'
                    '\tif (!master->cur_msg_mapped || !master->can_dma)\n'
                    '\t\treturn 0;\n'
                    '\n'
                    '\tif (master->dma_tx)\n'
                    '\t\ttx_dev = master->dma_tx->device->dev;\n'
                    '\telse\n'
                    '\t\ttx_dev = master->dev.parent;\n'
                    '\n'
                    '\tif (master->dma_rx)\n'
                    '\t\trx_dev = master->dma_rx->device->dev;\n'
                    '\telse\n'
                    '\t\trx_dev = master->dev.parent;\n'
                    '\n'
                    '\tlist_for_each_entry(xfer, &msg->transfers, transfer_list) {\n'
                    '\t\tif (!master->can_dma(master, msg->spi, xfer))\n'
                    '\t\t\tcontinue;\n'
                    '\n'
                    '\t\tspi_unmap_buf(master, rx_dev, &xfer->rx_sg, DMA_FROM_DEVICE);\n'
                    '\t\tspi_unmap_buf(master, tx_dev, &xfer->tx_sg, DMA_TO_DEVICE);\n'
                    '\t}\n'
                    '\n'
                    '\treturn 0;\n'
                    '}',
 'spi_map_msg': 'static int spi_map_msg(struct spi_master *master, struct spi_message *msg)\n'
                '{\n'
                '\tstruct spi_transfer *xfer;\n'
                '\tvoid *tmp;\n'
                '\tunsigned int max_tx, max_rx;\n'
                '\n'
                '\tif (master->flags & (SPI_MASTER_MUST_RX | SPI_MASTER_MUST_TX)) {\n'
                '\t\tmax_tx = 0;\n'
                '\t\tmax_rx = 0;\n'
                '\n'
                '\t\tlist_for_each_entry(xfer, &msg->transfers, transfer_list) {\n'
                '\t\t\tif ((master->flags & SPI_MASTER_MUST_TX) &&\n'
                '\t\t\t    !xfer->tx_buf)\n'
                '\t\t\t\tmax_tx = max(xfer->len, max_tx);\n'
                '\t\t\tif ((master->flags & SPI_MASTER_MUST_RX) &&\n'
                '\t\t\t    !xfer->rx_buf)\n'
                '\t\t\t\tmax_rx = max(xfer->len, max_rx);\n'
                '\t\t}\n'
                '\n'
                '\t\tif (max_tx) {\n'
                '\t\t\ttmp = krealloc(master->dummy_tx, max_tx,\n'
                '\t\t\t\t       GFP_KERNEL | GFP_DMA);\n'
                '\t\t\tif (!tmp)\n'
                '\t\t\t\treturn -ENOMEM;\n'
                '\t\t\tmaster->dummy_tx = tmp;\n'
                '\t\t\tmemset(tmp, 0, max_tx);\n'
                '\t\t}\n'
                '\n'
                '\t\tif (max_rx) {\n'
                '\t\t\ttmp = krealloc(master->dummy_rx, max_rx,\n'
                '\t\t\t\t       GFP_KERNEL | GFP_DMA);\n'
                '\t\t\tif (!tmp)\n'
                '\t\t\t\treturn -ENOMEM;\n'
                '\t\t\tmaster->dummy_rx = tmp;\n'
                '\t\t}\n'
                '\n'
                '\t\tif (max_tx || max_rx) {\n'
                '\t\t\tlist_for_each_entry(xfer, &msg->transfers,\n'
                '\t\t\t\t\t    transfer_list) {\n'
                '\t\t\t\tif (!xfer->len)\n'
                '\t\t\t\t\tcontinue;\n'
                '\t\t\t\tif (!xfer->tx_buf)\n'
                '\t\t\t\t\txfer->tx_buf = master->dummy_tx;\n'
                '\t\t\t\tif (!xfer->rx_buf)\n'
                '\t\t\t\t\txfer->rx_buf = master->dummy_rx;\n'
                '\t\t\t}\n'
                '\t\t}\n'
                '\t}\n'
                '\n'
                '\treturn __spi_map_msg(master, msg);\n'
                '}',
 'spi_unmap_msg': 'static inline int spi_unmap_msg(struct spi_master *master,\n'
                  '\t\t\t\tstruct spi_message *msg)\n'
                  '{\n'
                  '\tstruct spi_transfer *xfer;\n'
                  '\n'
                  '\tlist_for_each_entry(xfer, &msg->transfers, transfer_list) {\n'
                  '\t\t/*\n'
                  '\t\t * Restore the original value of tx_buf or rx_buf if they are\n'
                  '\t\t * NULL.\n'
                  '\t\t */\n'
                  '\t\tif (xfer->tx_buf == master->dummy_tx)\n'
                  '\t\t\txfer->tx_buf = NULL;\n'
                  '\t\tif (xfer->rx_buf == master->dummy_rx)\n'
                  '\t\t\txfer->rx_buf = NULL;\n'
                  '\t}\n'
                  '\n'
                  '\treturn __spi_unmap_msg(master, msg);\n'
                  '}',
 '__sg_free_table': 'void __sg_free_table(struct sg_table *table, unsigned int max_ents,\n'
                    '\t\t     bool skip_first_chunk, sg_free_fn *free_fn)\n'
                    '{\n'
                    '\tstruct scatterlist *sgl, *next;\n'
                    '\n'
                    '\tif (unlikely(!table->sgl))\n'
                    '\t\treturn;\n'
                    '\n'
                    '\tsgl = table->sgl;\n'
                    '\twhile (table->orig_nents) {\n'
                    '\t\tunsigned int alloc_size = table->orig_nents;\n'
                    '\t\tunsigned int sg_size;\n'
                    '\n'
                    '\t\t/*\n'
                    '\t\t * If we have more than max_ents segments left,\n'
                    "\t\t * then assign 'next' to the sg table after the current one.\n"
                    '\t\t * sg_size is then one less than alloc size, since the last\n'
                    '\t\t * element is the chain pointer.\n'
                    '\t\t */\n'
                    '\t\tif (alloc_size > max_ents) {\n'
                    '\t\t\tnext = sg_chain_ptr(&sgl[max_ents - 1]);\n'
                    '\t\t\talloc_size = max_ents;\n'
                    '\t\t\tsg_size = alloc_size - 1;\n'
                    '\t\t} else {\n'
                    '\t\t\tsg_size = alloc_size;\n'
                    '\t\t\tnext = NULL;\n'
                    '\t\t}\n'
                    '\n'
                    '\t\ttable->orig_nents -= sg_size;\n'
                    '\t\tif (skip_first_chunk)\n'
                    '\t\t\tskip_first_chunk = false;\n'
                    '\t\telse\n'
                    '\t\t\tfree_fn(sgl, alloc_size);\n'
                    '\t\tsgl = next;\n'
                    '\t}\n'
                    '\n'
                    '\ttable->sgl = NULL;\n'
                    '}',
 'sg_free_table': 'void sg_free_table(struct sg_table *table)\n'
                  '{\n'
                  '\t__sg_free_table(table, SG_MAX_SINGLE_ALLOC, false, sg_kfree);\n'
                  '}',
 '__sg_alloc_table': 'int __sg_alloc_table(struct sg_table *table, unsigned int nents,\n'
                     '\t\t     unsigned int max_ents, struct scatterlist *first_chunk,\n'
                     '\t\t     gfp_t gfp_mask, sg_alloc_fn *alloc_fn)\n'
                     '{\n'
                     '\tstruct scatterlist *sg, *prv;\n'
                     '\tunsigned int left;\n'
                     '\n'
                     '\tmemset(table, 0, sizeof(*table));\n'
                     '\n'
                     '\tif (nents == 0)\n'
                     '\t\treturn -EINVAL;\n'
                     '#ifndef CONFIG_ARCH_HAS_SG_CHAIN\n'
                     '\tif (WARN_ON_ONCE(nents > max_ents))\n'
                     '\t\treturn -EINVAL;\n'
                     '#endif\n'
                     '\n'
                     '\tleft = nents;\n'
                     '\tprv = NULL;\n'
                     '\tdo {\n'
                     '\t\tunsigned int sg_size, alloc_size = left;\n'
                     '\n'
                     '\t\tif (alloc_size > max_ents) {\n'
                     '\t\t\talloc_size = max_ents;\n'
                     '\t\t\tsg_size = alloc_size - 1;\n'
                     '\t\t} else\n'
                     '\t\t\tsg_size = alloc_size;\n'
                     '\n'
                     '\t\tleft -= sg_size;\n'
                     '\n'
                     '\t\tif (first_chunk) {\n'
                     '\t\t\tsg = first_chunk;\n'
                     '\t\t\tfirst_chunk = NULL;\n'
                     '\t\t} else {\n'
                     '\t\t\tsg = alloc_fn(alloc_size, gfp_mask);\n'
                     '\t\t}\n'
                     '\t\tif (unlikely(!sg)) {\n'
                     '\t\t\t/*\n'
                     '\t\t\t * Adjust entry count to reflect that the last\n'
                     "\t\t\t * entry of the previous table won't be used for\n"
                     '\t\t\t * linkage.  Without this, sg_kfree() may get\n'
                     '\t\t\t * confused.\n'
                     '\t\t\t */\n'
                     '\t\t\tif (prv)\n'
                     '\t\t\t\ttable->nents = ++table->orig_nents;\n'
                     '\n'
                     ' \t\t\treturn -ENOMEM;\n'
                     '\t\t}\n'
                     '\n'
                     '\t\tsg_init_table(sg, alloc_size);\n'
                     '\t\ttable->nents = table->orig_nents += sg_size;\n'
                     '\n'
                     '\t\t/*\n'
                     '\t\t * If this is the first mapping, assign the sg table header.\n'
                     '\t\t * If this is not the first mapping, chain previous part.\n'
                     '\t\t */\n'
                     '\t\tif (prv)\n'
                     '\t\t\tsg_chain(prv, max_ents, sg);\n'
                     '\t\telse\n'
                     '\t\t\ttable->sgl = sg;\n'
                     '\n'
                     '\t\t/*\n'
                     '\t\t * If no more entries after this one, mark the end\n'
                     '\t\t */\n'
                     '\t\tif (!left)\n'
                     '\t\t\tsg_mark_end(&sg[sg_size - 1]);\n'
                     '\n'
                     '\t\tprv = sg;\n'
                     '\t} while (left);\n'
                     '\n'
                     '\treturn 0;\n'
                     '}',
 'sg_alloc_table': 'int sg_alloc_table(struct sg_table *table, unsigned int nents, gfp_t '
                   'gfp_mask)\n'
                   '{\n'
                   '\tint ret;\n'
                   '\n'
                   '\tret = __sg_alloc_table(table, nents, SG_MAX_SINGLE_ALLOC,\n'
                   '\t\t\t       NULL, gfp_mask, sg_kmalloc);\n'
                   '\tif (unlikely(ret))\n'
                   '\t\t__sg_free_table(table, SG_MAX_SINGLE_ALLOC, false, sg_kfree);\n'
                   '\n'
                   '\treturn ret;\n'
                   '}'}
BASELINE_HASHES = {'spi_map_buf': '4918787fae7ed79b6b0e4dfea73dc799f360e868caefd252a3b771e3a9232e8a',
 'spi_unmap_buf': 'b2f0f90d808749eba1936a56b77e47b7ac03eea5326f2cc552eb2cef59cfe631',
 '__spi_map_msg': 'adb7c3705dd3ab9f04e2a6ce26635b10bffabadae9e7d82cae2b164de95e927c',
 '__spi_unmap_msg': 'ca3576cb4fff37ab136dafc9050824970a4d61aec82c1f392cc0910aa991cb0f',
 'spi_map_msg': '491f79ac35d1be65367916927dd742bfc99c89a05dd7de1a8d9bb9977ef06b7f',
 'spi_unmap_msg': '74edc68f6e2d6194acdc96c2b66ffda40721de2ae2aac894731b76cdc8e23802',
 '__sg_free_table': '51f45c23013882504220e84e47c5f2e2ee8ceba35ccb6e7d05f13db524ff1751',
 'sg_free_table': '6943d067f92a54dce526ad2f321916203f05df679cd5edd69bc2fee3293a9421',
 '__sg_alloc_table': '2fb939de2320dde2eafbf942c6be21eb30277a4ad650385a1091c19138f65389',
 'sg_alloc_table': '282a60d0b684c7faf12ed229d25fbe7d452db96e1713854a1b87c46c882c0a88'}

EXPECTED = {'normal': {'case': 'normal',
            'result': 0,
            'result2': 0,
            'alloc_calls': 6,
            'allocs': 6,
            'frees': 6,
            'live_allocs': 0,
            'map_calls': 6,
            'maps': 6,
            'unmaps': 6,
            'live_maps': 0,
            'can_calls': 3,
            'bad_sg': 0,
            'invalid_free': 0,
            'invalid_unmap': 0,
            'wrong_entries': 0,
            'wrong_device': 0,
            'wrong_segments': 0,
            'mapped_flag': 0,
            'remaining_sg': 0,
            'first_live_maps': 0,
            'page_calls': 0,
            'dummy_allocs': 0,
            'dummy_restored': 0,
            'premapped_intact': 1,
            'unmap_calls': 1,
            'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'tx-fail-first': {'case': 'tx-fail-first',
                   'result': -12,
                   'result2': 0,
                   'alloc_calls': 1,
                   'allocs': 1,
                   'frees': 1,
                   'live_allocs': 0,
                   'map_calls': 1,
                   'maps': 0,
                   'unmaps': 0,
                   'live_maps': 0,
                   'can_calls': 1,
                   'bad_sg': 0,
                   'invalid_free': 0,
                   'invalid_unmap': 0,
                   'wrong_entries': 0,
                   'wrong_device': 0,
                   'wrong_segments': 0,
                   'mapped_flag': 0,
                   'remaining_sg': 0,
                   'first_live_maps': 0,
                   'page_calls': 0,
                   'dummy_allocs': 0,
                   'dummy_restored': 0,
                   'premapped_intact': 1,
                   'unmap_calls': 1,
                   'sequence': 'aMf'},
 'rx-fail-first': {'case': 'rx-fail-first',
                   'result': -12,
                   'result2': 0,
                   'alloc_calls': 2,
                   'allocs': 2,
                   'frees': 2,
                   'live_allocs': 0,
                   'map_calls': 2,
                   'maps': 1,
                   'unmaps': 1,
                   'live_maps': 0,
                   'can_calls': 1,
                   'bad_sg': 0,
                   'invalid_free': 0,
                   'invalid_unmap': 0,
                   'wrong_entries': 0,
                   'wrong_device': 0,
                   'wrong_segments': 0,
                   'mapped_flag': 0,
                   'remaining_sg': 0,
                   'first_live_maps': 0,
                   'page_calls': 0,
                   'dummy_allocs': 0,
                   'dummy_restored': 0,
                   'premapped_intact': 1,
                   'unmap_calls': 1,
                   'sequence': 'aMaMfUf'},
 'tx-fail-second': {'case': 'tx-fail-second',
                    'result': -12,
                    'result2': 0,
                    'alloc_calls': 3,
                    'allocs': 3,
                    'frees': 3,
                    'live_allocs': 0,
                    'map_calls': 3,
                    'maps': 2,
                    'unmaps': 2,
                    'live_maps': 0,
                    'can_calls': 2,
                    'bad_sg': 0,
                    'invalid_free': 0,
                    'invalid_unmap': 0,
                    'wrong_entries': 0,
                    'wrong_device': 0,
                    'wrong_segments': 0,
                    'mapped_flag': 0,
                    'remaining_sg': 0,
                    'first_live_maps': 0,
                    'page_calls': 0,
                    'dummy_allocs': 0,
                    'dummy_restored': 0,
                    'premapped_intact': 1,
                    'unmap_calls': 1,
                    'sequence': 'aMaMaMfUfUf'},
 'rx-fail-second': {'case': 'rx-fail-second',
                    'result': -12,
                    'result2': 0,
                    'alloc_calls': 4,
                    'allocs': 4,
                    'frees': 4,
                    'live_allocs': 0,
                    'map_calls': 4,
                    'maps': 3,
                    'unmaps': 3,
                    'live_maps': 0,
                    'can_calls': 2,
                    'bad_sg': 0,
                    'invalid_free': 0,
                    'invalid_unmap': 0,
                    'wrong_entries': 0,
                    'wrong_device': 0,
                    'wrong_segments': 0,
                    'mapped_flag': 0,
                    'remaining_sg': 0,
                    'first_live_maps': 0,
                    'page_calls': 0,
                    'dummy_allocs': 0,
                    'dummy_restored': 0,
                    'premapped_intact': 1,
                    'unmap_calls': 1,
                    'sequence': 'aMaMaMaMfUfUfUf'},
 'tx-fail-third': {'case': 'tx-fail-third',
                   'result': -12,
                   'result2': 0,
                   'alloc_calls': 5,
                   'allocs': 5,
                   'frees': 5,
                   'live_allocs': 0,
                   'map_calls': 5,
                   'maps': 4,
                   'unmaps': 4,
                   'live_maps': 0,
                   'can_calls': 3,
                   'bad_sg': 0,
                   'invalid_free': 0,
                   'invalid_unmap': 0,
                   'wrong_entries': 0,
                   'wrong_device': 0,
                   'wrong_segments': 0,
                   'mapped_flag': 0,
                   'remaining_sg': 0,
                   'first_live_maps': 0,
                   'page_calls': 0,
                   'dummy_allocs': 0,
                   'dummy_restored': 0,
                   'premapped_intact': 1,
                   'unmap_calls': 1,
                   'sequence': 'aMaMaMaMaMfUfUfUfUf'},
 'rx-fail-third': {'case': 'rx-fail-third',
                   'result': -12,
                   'result2': 0,
                   'alloc_calls': 6,
                   'allocs': 6,
                   'frees': 6,
                   'live_allocs': 0,
                   'map_calls': 6,
                   'maps': 5,
                   'unmaps': 5,
                   'live_maps': 0,
                   'can_calls': 3,
                   'bad_sg': 0,
                   'invalid_free': 0,
                   'invalid_unmap': 0,
                   'wrong_entries': 0,
                   'wrong_device': 0,
                   'wrong_segments': 0,
                   'mapped_flag': 0,
                   'remaining_sg': 0,
                   'first_live_maps': 0,
                   'page_calls': 0,
                   'dummy_allocs': 0,
                   'dummy_restored': 0,
                   'premapped_intact': 1,
                   'unmap_calls': 1,
                   'sequence': 'aMaMaMaMaMaMfUfUfUfUfUf'},
 'alloc-fail-first': {'case': 'alloc-fail-first',
                      'result': -12,
                      'result2': 0,
                      'alloc_calls': 1,
                      'allocs': 0,
                      'frees': 0,
                      'live_allocs': 0,
                      'map_calls': 0,
                      'maps': 0,
                      'unmaps': 0,
                      'live_maps': 0,
                      'can_calls': 1,
                      'bad_sg': 0,
                      'invalid_free': 0,
                      'invalid_unmap': 0,
                      'wrong_entries': 0,
                      'wrong_device': 0,
                      'wrong_segments': 0,
                      'mapped_flag': 0,
                      'remaining_sg': 0,
                      'first_live_maps': 0,
                      'page_calls': 0,
                      'dummy_allocs': 0,
                      'dummy_restored': 0,
                      'premapped_intact': 1,
                      'unmap_calls': 1,
                      'sequence': 'a'},
 'alloc-fail-second': {'case': 'alloc-fail-second',
                       'result': -12,
                       'result2': 0,
                       'alloc_calls': 2,
                       'allocs': 1,
                       'frees': 1,
                       'live_allocs': 0,
                       'map_calls': 1,
                       'maps': 1,
                       'unmaps': 1,
                       'live_maps': 0,
                       'can_calls': 1,
                       'bad_sg': 0,
                       'invalid_free': 0,
                       'invalid_unmap': 0,
                       'wrong_entries': 0,
                       'wrong_device': 0,
                       'wrong_segments': 0,
                       'mapped_flag': 0,
                       'remaining_sg': 0,
                       'first_live_maps': 0,
                       'page_calls': 0,
                       'dummy_allocs': 0,
                       'dummy_restored': 0,
                       'premapped_intact': 1,
                       'unmap_calls': 1,
                       'sequence': 'aMaUf'},
 'alloc-fail-later': {'case': 'alloc-fail-later',
                      'result': -12,
                      'result2': 0,
                      'alloc_calls': 5,
                      'allocs': 4,
                      'frees': 4,
                      'live_allocs': 0,
                      'map_calls': 4,
                      'maps': 4,
                      'unmaps': 4,
                      'live_maps': 0,
                      'can_calls': 3,
                      'bad_sg': 0,
                      'invalid_free': 0,
                      'invalid_unmap': 0,
                      'wrong_entries': 0,
                      'wrong_device': 0,
                      'wrong_segments': 0,
                      'mapped_flag': 0,
                      'remaining_sg': 0,
                      'first_live_maps': 0,
                      'page_calls': 0,
                      'dummy_allocs': 0,
                      'dummy_restored': 0,
                      'premapped_intact': 1,
                      'unmap_calls': 1,
                      'sequence': 'aMaMaMaMaUfUfUfUf'},
 'vmalloc-page-first': {'case': 'vmalloc-page-first',
                        'result': -12,
                        'result2': 0,
                        'alloc_calls': 1,
                        'allocs': 1,
                        'frees': 1,
                        'live_allocs': 0,
                        'map_calls': 0,
                        'maps': 0,
                        'unmaps': 0,
                        'live_maps': 0,
                        'can_calls': 1,
                        'bad_sg': 0,
                        'invalid_free': 0,
                        'invalid_unmap': 0,
                        'wrong_entries': 0,
                        'wrong_device': 0,
                        'wrong_segments': 0,
                        'mapped_flag': 0,
                        'remaining_sg': 0,
                        'first_live_maps': 0,
                        'page_calls': 1,
                        'dummy_allocs': 0,
                        'dummy_restored': 0,
                        'premapped_intact': 1,
                        'unmap_calls': 1,
                        'sequence': 'af'},
 'vmalloc-page-later': {'case': 'vmalloc-page-later',
                        'result': -12,
                        'result2': 0,
                        'alloc_calls': 3,
                        'allocs': 3,
                        'frees': 3,
                        'live_allocs': 0,
                        'map_calls': 2,
                        'maps': 2,
                        'unmaps': 2,
                        'live_maps': 0,
                        'can_calls': 2,
                        'bad_sg': 0,
                        'invalid_free': 0,
                        'invalid_unmap': 0,
                        'wrong_entries': 0,
                        'wrong_device': 0,
                        'wrong_segments': 0,
                        'mapped_flag': 0,
                        'remaining_sg': 0,
                        'first_live_maps': 0,
                        'page_calls': 5,
                        'dummy_allocs': 0,
                        'dummy_restored': 0,
                        'premapped_intact': 1,
                        'unmap_calls': 1,
                        'sequence': 'aMaMafUfUf'},
 'chained-linear': {'case': 'chained-linear',
                    'result': 0,
                    'result2': 0,
                    'alloc_calls': 18,
                    'allocs': 18,
                    'frees': 18,
                    'live_allocs': 0,
                    'map_calls': 6,
                    'maps': 6,
                    'unmaps': 6,
                    'live_maps': 0,
                    'can_calls': 3,
                    'bad_sg': 0,
                    'invalid_free': 0,
                    'invalid_unmap': 0,
                    'wrong_entries': 0,
                    'wrong_device': 0,
                    'wrong_segments': 0,
                    'mapped_flag': 0,
                    'remaining_sg': 0,
                    'first_live_maps': 0,
                    'page_calls': 0,
                    'dummy_allocs': 0,
                    'dummy_restored': 0,
                    'premapped_intact': 1,
                    'unmap_calls': 1,
                    'sequence': 'aaaMaaaMaaaMaaaMaaaMaaaMUfffUfffUfffUfffUfffUfff'},
 'chained-vmalloc': {'case': 'chained-vmalloc',
                     'result': 0,
                     'result2': 0,
                     'alloc_calls': 12,
                     'allocs': 12,
                     'frees': 12,
                     'live_allocs': 0,
                     'map_calls': 6,
                     'maps': 6,
                     'unmaps': 6,
                     'live_maps': 0,
                     'can_calls': 3,
                     'bad_sg': 0,
                     'invalid_free': 0,
                     'invalid_unmap': 0,
                     'wrong_entries': 0,
                     'wrong_device': 0,
                     'wrong_segments': 0,
                     'mapped_flag': 0,
                     'remaining_sg': 0,
                     'first_live_maps': 0,
                     'page_calls': 42,
                     'dummy_allocs': 0,
                     'dummy_restored': 0,
                     'premapped_intact': 1,
                     'unmap_calls': 1,
                     'sequence': 'aaMaaMaaMaaMaaMaaMUffUffUffUffUffUff'},
 'chained-offset-vmalloc': {'case': 'chained-offset-vmalloc',
                            'result': 0,
                            'result2': 0,
                            'alloc_calls': 12,
                            'allocs': 12,
                            'frees': 12,
                            'live_allocs': 0,
                            'map_calls': 6,
                            'maps': 6,
                            'unmaps': 6,
                            'live_maps': 0,
                            'can_calls': 3,
                            'bad_sg': 0,
                            'invalid_free': 0,
                            'invalid_unmap': 0,
                            'wrong_entries': 0,
                            'wrong_device': 0,
                            'wrong_segments': 0,
                            'mapped_flag': 0,
                            'remaining_sg': 0,
                            'first_live_maps': 0,
                            'page_calls': 42,
                            'dummy_allocs': 0,
                            'dummy_restored': 0,
                            'premapped_intact': 1,
                            'unmap_calls': 1,
                            'sequence': 'aaMaaMaaMaaMaaMaaMUffUffUffUffUffUff'},
 'chain-alloc-partial-fail': {'case': 'chain-alloc-partial-fail',
                              'result': -12,
                              'result2': 0,
                              'alloc_calls': 2,
                              'allocs': 1,
                              'frees': 1,
                              'live_allocs': 0,
                              'map_calls': 0,
                              'maps': 0,
                              'unmaps': 0,
                              'live_maps': 0,
                              'can_calls': 1,
                              'bad_sg': 0,
                              'invalid_free': 0,
                              'invalid_unmap': 0,
                              'wrong_entries': 0,
                              'wrong_device': 0,
                              'wrong_segments': 0,
                              'mapped_flag': 0,
                              'remaining_sg': 0,
                              'first_live_maps': 0,
                              'page_calls': 0,
                              'dummy_allocs': 0,
                              'dummy_restored': 0,
                              'premapped_intact': 1,
                              'unmap_calls': 1,
                              'sequence': 'aaf'},
 'chain-alloc-later-fail': {'case': 'chain-alloc-later-fail',
                            'result': -12,
                            'result2': 0,
                            'alloc_calls': 5,
                            'allocs': 4,
                            'frees': 4,
                            'live_allocs': 0,
                            'map_calls': 1,
                            'maps': 1,
                            'unmaps': 1,
                            'live_maps': 0,
                            'can_calls': 1,
                            'bad_sg': 0,
                            'invalid_free': 0,
                            'invalid_unmap': 0,
                            'wrong_entries': 0,
                            'wrong_device': 0,
                            'wrong_segments': 0,
                            'mapped_flag': 0,
                            'remaining_sg': 0,
                            'first_live_maps': 0,
                            'page_calls': 0,
                            'dummy_allocs': 0,
                            'dummy_restored': 0,
                            'premapped_intact': 1,
                            'unmap_calls': 1,
                            'sequence': 'aaaMaafUfff'},
 'chain-map-later-fail': {'case': 'chain-map-later-fail',
                          'result': -12,
                          'result2': 0,
                          'alloc_calls': 9,
                          'allocs': 9,
                          'frees': 9,
                          'live_allocs': 0,
                          'map_calls': 3,
                          'maps': 2,
                          'unmaps': 2,
                          'live_maps': 0,
                          'can_calls': 2,
                          'bad_sg': 0,
                          'invalid_free': 0,
                          'invalid_unmap': 0,
                          'wrong_entries': 0,
                          'wrong_device': 0,
                          'wrong_segments': 0,
                          'mapped_flag': 0,
                          'remaining_sg': 0,
                          'first_live_maps': 0,
                          'page_calls': 0,
                          'dummy_allocs': 0,
                          'dummy_restored': 0,
                          'premapped_intact': 1,
                          'unmap_calls': 1,
                          'sequence': 'aaaMaaaMaaaMfffUfffUfff'},
 'dma-merge': {'case': 'dma-merge',
               'result': 0,
               'result2': 0,
               'alloc_calls': 6,
               'allocs': 6,
               'frees': 6,
               'live_allocs': 0,
               'map_calls': 6,
               'maps': 6,
               'unmaps': 6,
               'live_maps': 0,
               'can_calls': 3,
               'bad_sg': 0,
               'invalid_free': 0,
               'invalid_unmap': 0,
               'wrong_entries': 0,
               'wrong_device': 0,
               'wrong_segments': 0,
               'mapped_flag': 0,
               'remaining_sg': 0,
               'first_live_maps': 0,
               'page_calls': 0,
               'dummy_allocs': 0,
               'dummy_restored': 0,
               'premapped_intact': 1,
               'unmap_calls': 1,
               'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'no-dma': {'case': 'no-dma',
            'result': 0,
            'result2': 0,
            'alloc_calls': 0,
            'allocs': 0,
            'frees': 0,
            'live_allocs': 0,
            'map_calls': 0,
            'maps': 0,
            'unmaps': 0,
            'live_maps': 0,
            'can_calls': 0,
            'bad_sg': 0,
            'invalid_free': 0,
            'invalid_unmap': 0,
            'wrong_entries': 0,
            'wrong_device': 0,
            'wrong_segments': 0,
            'mapped_flag': 0,
            'remaining_sg': 0,
            'first_live_maps': 0,
            'page_calls': 0,
            'dummy_allocs': 0,
            'dummy_restored': 0,
            'premapped_intact': 1,
            'unmap_calls': 1,
            'sequence': ''},
 'no-dma-stale': {'case': 'no-dma-stale',
                  'result': 0,
                  'result2': 0,
                  'alloc_calls': 0,
                  'allocs': 0,
                  'frees': 0,
                  'live_allocs': 0,
                  'map_calls': 0,
                  'maps': 0,
                  'unmaps': 0,
                  'live_maps': 0,
                  'can_calls': 0,
                  'bad_sg': 0,
                  'invalid_free': 0,
                  'invalid_unmap': 0,
                  'wrong_entries': 0,
                  'wrong_device': 0,
                  'wrong_segments': 0,
                  'mapped_flag': 0,
                  'remaining_sg': 0,
                  'first_live_maps': 0,
                  'page_calls': 0,
                  'dummy_allocs': 0,
                  'dummy_restored': 0,
                  'premapped_intact': 1,
                  'unmap_calls': 1,
                  'sequence': ''},
 'ineligible-middle': {'case': 'ineligible-middle',
                       'result': 0,
                       'result2': 0,
                       'alloc_calls': 4,
                       'allocs': 4,
                       'frees': 4,
                       'live_allocs': 0,
                       'map_calls': 4,
                       'maps': 4,
                       'unmaps': 4,
                       'live_maps': 0,
                       'can_calls': 3,
                       'bad_sg': 0,
                       'invalid_free': 0,
                       'invalid_unmap': 0,
                       'wrong_entries': 0,
                       'wrong_device': 0,
                       'wrong_segments': 0,
                       'mapped_flag': 0,
                       'remaining_sg': 0,
                       'first_live_maps': 0,
                       'page_calls': 0,
                       'dummy_allocs': 0,
                       'dummy_restored': 0,
                       'premapped_intact': 1,
                       'unmap_calls': 1,
                       'sequence': 'aMaMaMaMUfUfUfUf'},
 'zero-length': {'case': 'zero-length',
                 'result': 0,
                 'result2': 0,
                 'alloc_calls': 0,
                 'allocs': 0,
                 'frees': 0,
                 'live_allocs': 0,
                 'map_calls': 0,
                 'maps': 0,
                 'unmaps': 0,
                 'live_maps': 0,
                 'can_calls': 0,
                 'bad_sg': 0,
                 'invalid_free': 0,
                 'invalid_unmap': 0,
                 'wrong_entries': 0,
                 'wrong_device': 0,
                 'wrong_segments': 0,
                 'mapped_flag': 0,
                 'remaining_sg': 0,
                 'first_live_maps': 0,
                 'page_calls': 0,
                 'dummy_allocs': 0,
                 'dummy_restored': 0,
                 'premapped_intact': 1,
                 'unmap_calls': 1,
                 'sequence': ''},
 'separate-dma-devices': {'case': 'separate-dma-devices',
                          'result': 0,
                          'result2': 0,
                          'alloc_calls': 6,
                          'allocs': 6,
                          'frees': 6,
                          'live_allocs': 0,
                          'map_calls': 6,
                          'maps': 6,
                          'unmaps': 6,
                          'live_maps': 0,
                          'can_calls': 3,
                          'bad_sg': 0,
                          'invalid_free': 0,
                          'invalid_unmap': 0,
                          'wrong_entries': 0,
                          'wrong_device': 0,
                          'wrong_segments': 0,
                          'mapped_flag': 0,
                          'remaining_sg': 0,
                          'first_live_maps': 0,
                          'page_calls': 0,
                          'dummy_allocs': 0,
                          'dummy_restored': 0,
                          'premapped_intact': 1,
                          'unmap_calls': 1,
                          'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'dummy-alloc-fail': {'case': 'dummy-alloc-fail',
                      'result': -12,
                      'result2': 0,
                      'alloc_calls': 0,
                      'allocs': 0,
                      'frees': 0,
                      'live_allocs': 0,
                      'map_calls': 0,
                      'maps': 0,
                      'unmaps': 0,
                      'live_maps': 0,
                      'can_calls': 0,
                      'bad_sg': 0,
                      'invalid_free': 0,
                      'invalid_unmap': 0,
                      'wrong_entries': 0,
                      'wrong_device': 0,
                      'wrong_segments': 0,
                      'mapped_flag': 0,
                      'remaining_sg': 0,
                      'first_live_maps': 0,
                      'page_calls': 0,
                      'dummy_allocs': 0,
                      'dummy_restored': 1,
                      'premapped_intact': 1,
                      'unmap_calls': 1,
                      'sequence': ''},
 'dummy-restore': {'case': 'dummy-restore',
                   'result': 0,
                   'result2': 0,
                   'alloc_calls': 6,
                   'allocs': 6,
                   'frees': 6,
                   'live_allocs': 0,
                   'map_calls': 6,
                   'maps': 6,
                   'unmaps': 6,
                   'live_maps': 0,
                   'can_calls': 3,
                   'bad_sg': 0,
                   'invalid_free': 0,
                   'invalid_unmap': 0,
                   'wrong_entries': 0,
                   'wrong_device': 0,
                   'wrong_segments': 0,
                   'mapped_flag': 0,
                   'remaining_sg': 0,
                   'first_live_maps': 0,
                   'page_calls': 0,
                   'dummy_allocs': 1,
                   'dummy_restored': 1,
                   'premapped_intact': 1,
                   'unmap_calls': 1,
                   'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'premapped-addresses': {'case': 'premapped-addresses',
                         'result': 0,
                         'result2': 0,
                         'alloc_calls': 6,
                         'allocs': 6,
                         'frees': 6,
                         'live_allocs': 0,
                         'map_calls': 6,
                         'maps': 6,
                         'unmaps': 6,
                         'live_maps': 0,
                         'can_calls': 3,
                         'bad_sg': 0,
                         'invalid_free': 0,
                         'invalid_unmap': 0,
                         'wrong_entries': 0,
                         'wrong_device': 0,
                         'wrong_segments': 0,
                         'mapped_flag': 0,
                         'remaining_sg': 0,
                         'first_live_maps': 0,
                         'page_calls': 0,
                         'dummy_allocs': 0,
                         'dummy_restored': 0,
                         'premapped_intact': 1,
                         'unmap_calls': 1,
                         'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'eligibility-changes': {'case': 'eligibility-changes',
                         'result': 0,
                         'result2': 0,
                         'alloc_calls': 6,
                         'allocs': 6,
                         'frees': 6,
                         'live_allocs': 0,
                         'map_calls': 6,
                         'maps': 6,
                         'unmaps': 6,
                         'live_maps': 0,
                         'can_calls': 3,
                         'bad_sg': 0,
                         'invalid_free': 0,
                         'invalid_unmap': 0,
                         'wrong_entries': 0,
                         'wrong_device': 0,
                         'wrong_segments': 0,
                         'mapped_flag': 0,
                         'remaining_sg': 0,
                         'first_live_maps': 0,
                         'page_calls': 0,
                         'dummy_allocs': 0,
                         'dummy_restored': 0,
                         'premapped_intact': 1,
                         'unmap_calls': 1,
                         'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'eligibility-removed': {'case': 'eligibility-removed',
                         'result': 0,
                         'result2': 0,
                         'alloc_calls': 6,
                         'allocs': 6,
                         'frees': 6,
                         'live_allocs': 0,
                         'map_calls': 6,
                         'maps': 6,
                         'unmaps': 6,
                         'live_maps': 0,
                         'can_calls': 3,
                         'bad_sg': 0,
                         'invalid_free': 0,
                         'invalid_unmap': 0,
                         'wrong_entries': 0,
                         'wrong_device': 0,
                         'wrong_segments': 0,
                         'mapped_flag': 0,
                         'remaining_sg': 0,
                         'first_live_maps': 0,
                         'page_calls': 0,
                         'dummy_allocs': 0,
                         'dummy_restored': 0,
                         'premapped_intact': 1,
                         'unmap_calls': 1,
                         'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'double-unmap': {'case': 'double-unmap',
                  'result': 0,
                  'result2': 0,
                  'alloc_calls': 6,
                  'allocs': 6,
                  'frees': 6,
                  'live_allocs': 0,
                  'map_calls': 6,
                  'maps': 6,
                  'unmaps': 6,
                  'live_maps': 0,
                  'can_calls': 3,
                  'bad_sg': 0,
                  'invalid_free': 0,
                  'invalid_unmap': 0,
                  'wrong_entries': 0,
                  'wrong_device': 0,
                  'wrong_segments': 0,
                  'mapped_flag': 0,
                  'remaining_sg': 0,
                  'first_live_maps': 0,
                  'page_calls': 0,
                  'dummy_allocs': 0,
                  'dummy_restored': 0,
                  'premapped_intact': 1,
                  'unmap_calls': 2,
                  'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'reuse-message': {'case': 'reuse-message',
                   'result': 0,
                   'result2': 0,
                   'alloc_calls': 12,
                   'allocs': 12,
                   'frees': 12,
                   'live_allocs': 0,
                   'map_calls': 12,
                   'maps': 12,
                   'unmaps': 12,
                   'live_maps': 0,
                   'can_calls': 6,
                   'bad_sg': 0,
                   'invalid_free': 0,
                   'invalid_unmap': 0,
                   'wrong_entries': 0,
                   'wrong_device': 0,
                   'wrong_segments': 0,
                   'mapped_flag': 0,
                   'remaining_sg': 0,
                   'first_live_maps': 0,
                   'page_calls': 0,
                   'dummy_allocs': 0,
                   'dummy_restored': 0,
                   'premapped_intact': 1,
                   'unmap_calls': 2,
                   'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUfaMaMaMaMaMaMUfUfUfUfUfUf'},
 'retry-after-failure': {'case': 'retry-after-failure',
                         'result': -12,
                         'result2': 0,
                         'alloc_calls': 9,
                         'allocs': 9,
                         'frees': 9,
                         'live_allocs': 0,
                         'map_calls': 9,
                         'maps': 8,
                         'unmaps': 8,
                         'live_maps': 0,
                         'can_calls': 5,
                         'bad_sg': 0,
                         'invalid_free': 0,
                         'invalid_unmap': 0,
                         'wrong_entries': 0,
                         'wrong_device': 0,
                         'wrong_segments': 0,
                         'mapped_flag': 0,
                         'remaining_sg': 0,
                         'first_live_maps': 0,
                         'page_calls': 0,
                         'dummy_allocs': 0,
                         'dummy_restored': 0,
                         'premapped_intact': 1,
                         'unmap_calls': 2,
                         'sequence': 'aMaMaMfUfUfaMaMaMaMaMaMUfUfUfUfUfUf'},
 'tx-only': {'case': 'tx-only',
             'result': 0,
             'result2': 0,
             'alloc_calls': 3,
             'allocs': 3,
             'frees': 3,
             'live_allocs': 0,
             'map_calls': 3,
             'maps': 3,
             'unmaps': 3,
             'live_maps': 0,
             'can_calls': 3,
             'bad_sg': 0,
             'invalid_free': 0,
             'invalid_unmap': 0,
             'wrong_entries': 0,
             'wrong_device': 0,
             'wrong_segments': 0,
             'mapped_flag': 0,
             'remaining_sg': 0,
             'first_live_maps': 0,
             'page_calls': 0,
             'dummy_allocs': 0,
             'dummy_restored': 0,
             'premapped_intact': 1,
             'unmap_calls': 1,
             'sequence': 'aMaMaMUfUfUf'},
 'rx-only': {'case': 'rx-only',
             'result': 0,
             'result2': 0,
             'alloc_calls': 3,
             'allocs': 3,
             'frees': 3,
             'live_allocs': 0,
             'map_calls': 3,
             'maps': 3,
             'unmaps': 3,
             'live_maps': 0,
             'can_calls': 3,
             'bad_sg': 0,
             'invalid_free': 0,
             'invalid_unmap': 0,
             'wrong_entries': 0,
             'wrong_device': 0,
             'wrong_segments': 0,
             'mapped_flag': 0,
             'remaining_sg': 0,
             'first_live_maps': 0,
             'page_calls': 0,
             'dummy_allocs': 0,
             'dummy_restored': 0,
             'premapped_intact': 1,
             'unmap_calls': 1,
             'sequence': 'aMaMaMUfUfUf'},
 'mixed-zero': {'case': 'mixed-zero',
                'result': 0,
                'result2': 0,
                'alloc_calls': 4,
                'allocs': 4,
                'frees': 4,
                'live_allocs': 0,
                'map_calls': 4,
                'maps': 4,
                'unmaps': 4,
                'live_maps': 0,
                'can_calls': 2,
                'bad_sg': 0,
                'invalid_free': 0,
                'invalid_unmap': 0,
                'wrong_entries': 0,
                'wrong_device': 0,
                'wrong_segments': 0,
                'mapped_flag': 0,
                'remaining_sg': 0,
                'first_live_maps': 0,
                'page_calls': 0,
                'dummy_allocs': 0,
                'dummy_restored': 0,
                'premapped_intact': 1,
                'unmap_calls': 1,
                'sequence': 'aMaMaMaMUfUfUfUf'},
 'unlimited-dma-length': {'case': 'unlimited-dma-length',
                          'result': 0,
                          'result2': 0,
                          'alloc_calls': 6,
                          'allocs': 6,
                          'frees': 6,
                          'live_allocs': 0,
                          'map_calls': 6,
                          'maps': 6,
                          'unmaps': 6,
                          'live_maps': 0,
                          'can_calls': 3,
                          'bad_sg': 0,
                          'invalid_free': 0,
                          'invalid_unmap': 0,
                          'wrong_entries': 0,
                          'wrong_device': 0,
                          'wrong_segments': 0,
                          'mapped_flag': 0,
                          'remaining_sg': 0,
                          'first_live_maps': 0,
                          'page_calls': 0,
                          'dummy_allocs': 0,
                          'dummy_restored': 0,
                          'premapped_intact': 1,
                          'unmap_calls': 1,
                          'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'}}
BASELINE_EXPECTED = {'normal': {'case': 'normal',
            'result': 0,
            'result2': 0,
            'alloc_calls': 6,
            'allocs': 6,
            'frees': 6,
            'live_allocs': 0,
            'map_calls': 6,
            'maps': 6,
            'unmaps': 6,
            'live_maps': 0,
            'can_calls': 6,
            'bad_sg': 0,
            'invalid_free': 0,
            'invalid_unmap': 0,
            'wrong_entries': 0,
            'wrong_device': 0,
            'wrong_segments': 0,
            'mapped_flag': 1,
            'remaining_sg': 0,
            'first_live_maps': 0,
            'page_calls': 0,
            'dummy_allocs': 0,
            'dummy_restored': 0,
            'premapped_intact': 1,
            'unmap_calls': 1,
            'sequence': 'aMaMaMaMaMaMUfUfUfUfUfUf'},
 'tx-fail-second': {'case': 'tx-fail-second',
                    'result': -12,
                    'result2': 0,
                    'alloc_calls': 3,
                    'allocs': 3,
                    'frees': 1,
                    'live_allocs': 2,
                    'map_calls': 3,
                    'maps': 2,
                    'unmaps': 0,
                    'live_maps': 2,
                    'can_calls': 2,
                    'bad_sg': 0,
                    'invalid_free': 0,
                    'invalid_unmap': 0,
                    'wrong_entries': 0,
                    'wrong_device': 0,
                    'wrong_segments': 0,
                    'mapped_flag': 0,
                    'remaining_sg': 2,
                    'first_live_maps': 2,
                    'page_calls': 0,
                    'dummy_allocs': 0,
                    'dummy_restored': 0,
                    'premapped_intact': 1,
                    'unmap_calls': 1,
                    'sequence': 'aMaMaMf'},
 'rx-fail-third': {'case': 'rx-fail-third',
                   'result': -12,
                   'result2': 0,
                   'alloc_calls': 6,
                   'allocs': 6,
                   'frees': 2,
                   'live_allocs': 4,
                   'map_calls': 6,
                   'maps': 5,
                   'unmaps': 1,
                   'live_maps': 4,
                   'can_calls': 3,
                   'bad_sg': 0,
                   'invalid_free': 0,
                   'invalid_unmap': 0,
                   'wrong_entries': 0,
                   'wrong_device': 0,
                   'wrong_segments': 0,
                   'mapped_flag': 0,
                   'remaining_sg': 4,
                   'first_live_maps': 4,
                   'page_calls': 0,
                   'dummy_allocs': 0,
                   'dummy_restored': 0,
                   'premapped_intact': 1,
                   'unmap_calls': 1,
                   'sequence': 'aMaMaMaMaMaMfUf'},
 'chained-linear': {'case': 'chained-linear',
                    'result': 0,
                    'result2': 0,
                    'alloc_calls': 18,
                    'allocs': 18,
                    'frees': 18,
                    'live_allocs': 0,
                    'map_calls': 6,
                    'maps': 6,
                    'unmaps': 6,
                    'live_maps': 0,
                    'can_calls': 6,
                    'bad_sg': 30,
                    'invalid_free': 0,
                    'invalid_unmap': 0,
                    'wrong_entries': 0,
                    'wrong_device': 0,
                    'wrong_segments': 30,
                    'mapped_flag': 1,
                    'remaining_sg': 0,
                    'first_live_maps': 0,
                    'page_calls': 0,
                    'dummy_allocs': 0,
                    'dummy_restored': 0,
                    'premapped_intact': 1,
                    'unmap_calls': 1,
                    'sequence': 'aaaMaaaMaaaMaaaMaaaMaaaMUfffUfffUfffUfffUfffUfff'},
 'chained-vmalloc': {'case': 'chained-vmalloc',
                     'result': 0,
                     'result2': 0,
                     'alloc_calls': 12,
                     'allocs': 12,
                     'frees': 12,
                     'live_allocs': 0,
                     'map_calls': 6,
                     'maps': 6,
                     'unmaps': 6,
                     'live_maps': 0,
                     'can_calls': 6,
                     'bad_sg': 24,
                     'invalid_free': 0,
                     'invalid_unmap': 0,
                     'wrong_entries': 0,
                     'wrong_device': 0,
                     'wrong_segments': 24,
                     'mapped_flag': 1,
                     'remaining_sg': 0,
                     'first_live_maps': 0,
                     'page_calls': 42,
                     'dummy_allocs': 0,
                     'dummy_restored': 0,
                     'premapped_intact': 1,
                     'unmap_calls': 1,
                     'sequence': 'aaMaaMaaMaaMaaMaaMUffUffUffUffUffUff'},
 'eligibility-changes': {'case': 'eligibility-changes',
                         'result': 0,
                         'result2': 0,
                         'alloc_calls': 6,
                         'allocs': 6,
                         'frees': 0,
                         'live_allocs': 6,
                         'map_calls': 6,
                         'maps': 6,
                         'unmaps': 0,
                         'live_maps': 6,
                         'can_calls': 6,
                         'bad_sg': 0,
                         'invalid_free': 0,
                         'invalid_unmap': 0,
                         'wrong_entries': 0,
                         'wrong_device': 0,
                         'wrong_segments': 0,
                         'mapped_flag': 1,
                         'remaining_sg': 6,
                         'first_live_maps': 6,
                         'page_calls': 0,
                         'dummy_allocs': 0,
                         'dummy_restored': 0,
                         'premapped_intact': 1,
                         'unmap_calls': 1,
                         'sequence': 'aMaMaMaMaMaM'},
 'zero-length': {'case': 'zero-length',
                 'result': -22,
                 'result2': 0,
                 'alloc_calls': 0,
                 'allocs': 0,
                 'frees': 0,
                 'live_allocs': 0,
                 'map_calls': 0,
                 'maps': 0,
                 'unmaps': 0,
                 'live_maps': 0,
                 'can_calls': 1,
                 'bad_sg': 0,
                 'invalid_free': 0,
                 'invalid_unmap': 0,
                 'wrong_entries': 0,
                 'wrong_device': 0,
                 'wrong_segments': 0,
                 'mapped_flag': 0,
                 'remaining_sg': 0,
                 'first_live_maps': 0,
                 'page_calls': 0,
                 'dummy_allocs': 0,
                 'dummy_restored': 0,
                 'premapped_intact': 1,
                 'unmap_calls': 1,
                 'sequence': ''},
 'retry-after-failure': {'case': 'retry-after-failure',
                         'result': -12,
                         'result2': 0,
                         'alloc_calls': 9,
                         'allocs': 9,
                         'frees': 7,
                         'live_allocs': 2,
                         'map_calls': 9,
                         'maps': 8,
                         'unmaps': 6,
                         'live_maps': 2,
                         'can_calls': 8,
                         'bad_sg': 0,
                         'invalid_free': 0,
                         'invalid_unmap': 0,
                         'wrong_entries': 0,
                         'wrong_device': 0,
                         'wrong_segments': 0,
                         'mapped_flag': 1,
                         'remaining_sg': 0,
                         'first_live_maps': 2,
                         'page_calls': 0,
                         'dummy_allocs': 0,
                         'dummy_restored': 0,
                         'premapped_intact': 1,
                         'unmap_calls': 2,
                         'sequence': 'aMaMaMfaMaMaMaMaMaMUfUfUfUfUfUf'},
 'unlimited-dma-length': {'case': 'unlimited-dma-length',
                          'result': -22,
                          'result2': 0,
                          'alloc_calls': 0,
                          'allocs': 0,
                          'frees': 0,
                          'live_allocs': 0,
                          'map_calls': 0,
                          'maps': 0,
                          'unmaps': 0,
                          'live_maps': 0,
                          'can_calls': 1,
                          'bad_sg': 0,
                          'invalid_free': 0,
                          'invalid_unmap': 0,
                          'wrong_entries': 0,
                          'wrong_device': 0,
                          'wrong_segments': 0,
                          'mapped_flag': 0,
                          'remaining_sg': 0,
                          'first_live_maps': 0,
                          'page_calls': 0,
                          'dummy_allocs': 0,
                          'dummy_restored': 0,
                          'premapped_intact': 1,
                          'unmap_calls': 1,
                          'sequence': ''}}

def validate_row(row, baseline=False):
    if type(baseline) is not bool or not isinstance(row, dict):
        raise ValueError("Typed DMA observation required")
    expected = (BASELINE_EXPECTED if baseline else EXPECTED).get(row.get("case"))
    if expected is None or set(row) != set(expected):
        raise ValueError("Exact DMA observation fields required")
    if any(type(row[k]) is not type(v) or row[k] != v for k,v in expected.items()):
        raise ValueError("DMA observation differs from fixed contract")
    return True
