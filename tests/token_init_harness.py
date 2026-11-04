"""Complete current token/HIF init functions with private allocation/IO recorders.

Only the repaired current source is admitted. This model does not execute DMA,
networking, module code or hardware, and makes no DMA-idle claim.
"""
import hashlib
import re

BASE = 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS = {'token': BASE+'embedded/common/cut_through.c',
                'hif': BASE+'embedded/common/rtmp_init.c',
                'hardware': BASE+'hw_ctrl/hw_init.c',
                'header': BASE+'embedded/include/cut_through.h',
                'os_header': BASE+'include/os/rt_linux.h'}
FUNCTION_SOURCES = {'cut_through_token_list_destroy': 'token',
                    'cut_through_token_list_init': 'token',
                    'cut_through_deinit': 'token', 'cut_through_init': 'token',
                    'WfHifSysInit': 'hif', 'WfHifInit': 'hardware'}
BODY_ORDER = ('cut_through_token_list_destroy', 'cut_through_token_list_init', 'cut_through_deinit', 'cut_through_init', 'WfHifSysInit', 'WfHifInit')
CASE_NAMES = ('token-cb-oom', 'token-tx-list-oom', 'token-tx-id-oom',
              'token-tx-entry-oom', 'token-rx-list-oom', 'token-rx-id-oom',
              'token-rx-entry-oom', 'token-normal', 'token-repeat-owner',
              'queue-repeat', 'queue-unpublished-owner', 'hif-ring-failure',
              'hif-token-oom', 'hif-normal', 'hif-existing-owner',
              'hif-direct-existing-owner', 'null-output', 'null-adapter')
FIELDS = ('result', 'attempts', 'live_before_cleanup', 'locks_before_cleanup',
          'owner_present', 'preserved', 'retry_result', 'retry_valid',
          'live_final', 'locks_final', 'ring_calls', 'disables', 'cleanup_calls',
          'hardware_init_calls', 'hooks', 'invalid_operations')
EXPECTED_ROWS = {'token-cb-oom': [0, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
 'token-tx-list-oom': [0, 2, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
 'token-tx-id-oom': [0, 3, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
 'token-tx-entry-oom': [0, 4, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
 'token-rx-list-oom': [0, 5, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
 'token-rx-id-oom': [0, 6, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
 'token-rx-entry-oom': [0, 7, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
 'token-normal': [1, 7, 7, 3, 1, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'token-repeat-owner': [0, 7, 7, 3, 1, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'queue-repeat': [1, 3, 3, 1, 0, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'queue-unpublished-owner': [0, 1, 1, 0, 0, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'hif-ring-failure': [2, 0, 0, 0, 0, 1, -1, 0, 0, 0, 1, 1, 1, 0, 0, 0],
 'hif-token-oom': [3, 1, 0, 0, 0, 1, -1, 0, 0, 0, 1, 1, 1, 0, 0, 0],
 'hif-normal': [0, 7, 7, 3, 1, 1, -1, 0, 0, 0, 1, 1, 0, 1, 1, 0],
 'hif-existing-owner': [1, 7, 7, 3, 1, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'hif-direct-existing-owner': [1, 7, 7, 3, 1, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'null-output': [0, 0, 0, 0, 0, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
 'null-adapter': [0, 0, 0, 0, 0, 1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0]}

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void VOID; typedef unsigned char UCHAR,UINT8; typedef uint16_t UINT16;
typedef int16_t INT16; typedef uint32_t UINT32; typedef long LONG;
typedef uintptr_t NDIS_PHYSICAL_ADDRESS; typedef void *PNDIS_PACKET;
typedef int INT,INT32,BOOLEAN,NDIS_STATUS,NDIS_SPIN_LOCK;
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_RESOURCES 3
#define RESOURCE_PRE_ALLOC
#define CUT_THROUGH
#define ____cacheline_aligned
#define MTWF_LOG(...) ((void)0)
#define NdisZeroMemory(p,n) memset((p),0,(n))
#define os_zero_mem(p,n) memset((p),0,(n))
#define fASIC_CAP_MCU_OFFLOAD 1
#define IS_ASIC_CAP(p,c) (((p)->caps&(c))!=0)
#define RTMP_PCI_DMA_TODEVICE 1
#define CUT_THROUGH_TYPE_TX 1
#define CUT_THROUGH_TYPE_RX 2
#define CUT_THROUGH_TYPE_BOTH 3
#define DEFAUT_PKT_TX_TOKEN_ID_MAX 4095
#define TX_TOKEN_HIGH 0
#define RTMP_SEM_LOCK(p) assert(*(p)==1)
#define RTMP_SEM_UNLOCK(p) assert(*(p)==1)
static int attempts,fail_at,live,locks,invalid;
static int ring_calls,disables,cleanup_calls,hardware_calls,hooks,ring_status;
static void *objects[32];
static void allocate(UCHAR **out,size_t n) {
    int i; attempts++; *out=NULL;
    if (attempts==fail_at) return;
    *out=malloc(n); assert(*out!=NULL);
    for(i=0;i<32;i++) if(objects[i]==NULL) {objects[i]=*out;live++;return;}
    abort();
}
static void release(void *p) {
    int i; assert(p!=NULL);
    for(i=0;i<32;i++) if(objects[i]==p) {objects[i]=NULL;live--;free(p);return;}
    invalid++; abort();
}
#define os_alloc_mem(a,p,n) ((void)(a),allocate((p),(n)))
#define os_free_mem(p) release(p)
#define NdisAllocateSpinLock(a,p) do{(void)(a);assert(*(p)==0);*(p)=1;locks++;}while(0)
#define NdisFreeSpinLock(p) do{assert(*(p)==1);*(p)=0;locks--;}while(0)
#define PCI_UNMAP_SINGLE(a,p,n,d) do{(void)(a);(void)(p);(void)(n);(void)(d);abort();}while(0)
#define RELEASE_NDIS_PACKET(a,p,s) do{(void)(a);(void)(p);(void)(s);abort();}while(0)
typedef struct _RTMP_ADAPTER {VOID *PktTokenCb;int caps;} RTMP_ADAPTER;
typedef struct {int inert;} HIF_INFO_T;
static void RT28XXDMADisable(RTMP_ADAPTER *p){assert(p);disables++;}
static int RTMPInitTxRxRingMemory(RTMP_ADAPTER *p){assert(p);ring_calls++;return ring_status;}
static void WfHifHwInit(RTMP_ADAPTER *p,HIF_INFO_T *i){assert(p&&i);hardware_calls++;}
#define WLAN_HOOK_CALL(a,p,n) do{(void)(p);(void)(n);hooks++;}while(0)
static INT32 WfHifSysExit(RTMP_ADAPTER *p);
'''

SUFFIX = r'''
static INT32 WfHifSysExit(RTMP_ADAPTER *p) {
    cleanup_calls++; cut_through_deinit((PKT_TOKEN_CB **)&p->PktTokenCb); return 0;
}
static int valid(PKT_TOKEN_CB *p) {
    UINT32 i;PKT_TOKEN_QUEUE *q[2];int j;
    if(!p||!p->tx_id_list.token_inited||!p->rx_id_list.token_inited)return 0;
    q[0]=&p->tx_id_list;q[1]=&p->rx_id_list;
    for(j=0;j<2;j++) {
        assert(q[j]->list&&q[j]->list->free_id&&q[j]->list->pkt_token);
        assert(q[j]->list->id_head==0&&q[j]->list->id_tail==4096);
        assert(q[j]->list->FreeTokenCnt==4096);
        for(i=0;i<4096;i++)assert(q[j]->list->free_id[i]==i);
        assert(q[j]->list->free_id[4096]==p->pkt_tkid_invalid);
    }
    return 1;
}
int main(int argc,char **argv) {
    const char *name;RTMP_ADAPTER ad;PKT_TOKEN_CB cb,*saved;
    HIF_INFO_T info;int r=0,preserved=1,retry=-1,retry_valid=0,snap_a,snap_l,snap_k,snap_p;
    int i,oom=0;assert(argc==2);name=argv[1];CASE_ADMISSION
    memset(&ad,0,sizeof(ad));memset(&cb,0,sizeof(cb));memset(&info,0,sizeof(info));
    for(i=0;i<7;i++)if(!strcmp(name,oom_names[i])){fail_at=i+1;oom=1;}
    if(oom||!strcmp(name,"token-normal"))r=cut_through_init(&ad.PktTokenCb,&ad);
    else if(!strcmp(name,"token-repeat-owner")) {
        assert(cut_through_init(&ad.PktTokenCb,&ad));saved=ad.PktTokenCb;
        r=cut_through_init(&ad.PktTokenCb,&ad);preserved=ad.PktTokenCb==saved&&valid(saved);
    } else if(!strcmp(name,"queue-repeat")) {
        cb.pAd=&ad;cb.pkt_tx_tkid_cnt=4;cb.pkt_tx_tkid_aray=5;cb.pkt_tkid_invalid=9;
        assert(cut_through_token_list_init(&cb,&cb.tx_id_list));saved=(void*)cb.tx_id_list.list;
        r=cut_through_token_list_init(&cb,&cb.tx_id_list);preserved=(void*)cb.tx_id_list.list==saved;
    } else if(!strcmp(name,"queue-unpublished-owner")) {
        allocate((UCHAR**)&cb.tx_id_list.list,sizeof(PKT_TOKEN_LIST));saved=(void*)cb.tx_id_list.list;
        r=cut_through_token_list_init(&cb,&cb.tx_id_list);preserved=(void*)cb.tx_id_list.list==saved;
    } else if(!strcmp(name,"hif-ring-failure")) {ring_status=2;r=WfHifInit(&ad);}
    else if(!strcmp(name,"hif-token-oom")) {fail_at=1;r=WfHifInit(&ad);}
    else if(!strcmp(name,"hif-normal"))r=WfHifInit(&ad);
    else if(strstr(name,"existing-owner")) {
        assert(cut_through_init(&ad.PktTokenCb,&ad));saved=ad.PktTokenCb;
        if(!strcmp(name,"hif-direct-existing-owner"))r=WfHifSysInit(&ad,&info);
        else r=WfHifInit(&ad);
        preserved=ad.PktTokenCb==saved&&valid(saved);
    } else if(!strcmp(name,"null-output"))r=cut_through_init(NULL,&ad);
    else if(!strcmp(name,"null-adapter"))r=cut_through_init(&ad.PktTokenCb,NULL);
    else abort();
    snap_a=attempts;snap_l=live;snap_k=locks;snap_p=ad.PktTokenCb!=NULL;
    if(ad.PktTokenCb)assert(valid(ad.PktTokenCb));
    if(oom) {
        assert(!ad.PktTokenCb&&live==0&&locks==0);fail_at=0;
        retry=cut_through_init(&ad.PktTokenCb,&ad);retry_valid=valid(ad.PktTokenCb);
    }
    if(ad.PktTokenCb)cut_through_deinit((PKT_TOKEN_CB**)&ad.PktTokenCb);
    if(!strcmp(name,"queue-repeat"))cut_through_token_list_destroy(&cb,&cb.tx_id_list,CUT_THROUGH_TYPE_TX);
    if(!strcmp(name,"queue-unpublished-owner"))release(cb.tx_id_list.list);
    printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",r,snap_a,snap_l,snap_k,
           snap_p,preserved,retry,retry_valid,live,locks,ring_calls,disables,cleanup_calls,hardware_calls,hooks,invalid);
    assert(live==0&&locks==0&&invalid==0);return 0;
}
'''


def function(text, name):
    token = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked = re.sub(token, lambda m: ' ' * len(m.group()), text)
    pattern = r'^(?:static\s+)?(?:INT|INT32)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    matches = list(re.finditer(pattern, masked, re.M))
    if len(matches) != 1:raise ValueError('Missing/ambiguous token function: '+name)
    start=matches[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated token function: '+name)


def declarations(text):
    names=('ENTRY','LIST','QUEUE','CB');result=[]
    for name in names:
        pattern=r'typedef struct _PKT_TOKEN_'+name+r'\s*\{[\s\S]*?\}\s*PKT_TOKEN_'+name+r'(?:\s+____cacheline_aligned)?;'
        found=re.findall(pattern,text)
        if len(found)!=1:raise ValueError('Actual token declaration missing: '+name)
        result.append(found[0])
    if '#define DEFAUT_PKT_TX_TOKEN_ID_MAX 4095'not in text:raise ValueError('Token capacity changed')
    return '\n'.join(result)


def actual_functions(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact token/HIF source map required')
    return {name:{'source':key,'body':function(texts[key],name)}for name,key in FUNCTION_SOURCES.items()}


def generate_source(texts,variant='current'):
    if variant!='current':raise ValueError('Only repaired current token source is executable')
    bodies=actual_functions(texts)
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    array='static const char *oom_names[7]={'+','.join('"'+n+'"'for n in CASE_NAMES[:7])+'};\n'
    for name,value in (('SUCCESS',0),('FAILURE',1),('RESOURCES',3)):
        found=re.findall(r'^#define NDIS_STATUS_'+name+r'\s+(0x[0-9a-fA-F]+)\s*$',texts['os_header'],re.M)
        if len(found)!=1 or int(found[0],16)!=value:raise ValueError('Actual NDIS status changed: '+name)
    return PREFIX+declarations(texts['header'])+'\n'+array+'\n'.join(bodies[n]['body']for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)


def function_manifest(texts):
    return {name:{'source':row['source'],'execution':'whole-function',
                  'full_body_sha256':hashlib.sha256(row['body'].encode()).hexdigest()}
            for name,row in actual_functions(texts).items()}
