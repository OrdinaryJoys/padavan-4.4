"""Current whole CmdQ functions and real declarations with inert fault seams.

No historical invalid-pointer implementation is executed. This isolated model
does not certify real kernel scheduling, queue budgets or system memory peaks.
"""
import hashlib
import re

SOURCE_PATHS = {
    'queue': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/cmm_cmd.c',
    'header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/cmm_cmd.h',
    'os': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/rtmp_os.h',
    'linux': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/os/rt_linux.h',
}
FUNCTION_SOURCES = {'RTInitializeCmdQ': 'queue', 'RTThreadDequeueCmd': 'queue', 'RTEnqueueInternalCmd': 'queue'}
BODY_ORDER = ('RTInitializeCmdQ', 'RTThreadDequeueCmd', 'RTEnqueueInternalCmd')
FUNCTIONS = ('RTInitializeCmdQ', 'RTThreadDequeueCmd', 'RTEnqueueInternalCmd')
OBSERVATION_FIELDS = ('status', 'allocation_attempts', 'frees_before_drain', 'live_before_drain',
                      'queued', 'wakeups', 'locks', 'unlocks', 'copies', 'metadata_ok', 'payload_ok')
CASES = (
    ('null-adapter', [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1]),
    ('null-payload', [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1]),
    ('nic-absent', [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1]),
    ('queue-already-stopped', [1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1]),
    ('stop-after-preflight', [1, 2, 2, 0, 0, 0, 2, 2, 1, 1, 1]),
    ('stop-after-element-allocation', [1, 2, 2, 0, 0, 0, 2, 2, 1, 1, 1]),
    ('stop-after-payload-allocation', [1, 2, 2, 0, 0, 0, 2, 2, 1, 1, 1]),
    ('element-allocation-failure', [3, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1]),
    ('payload-allocation-failure', [3, 2, 1, 0, 0, 0, 1, 1, 0, 1, 1]),
    ('element-success-with-null', [3, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1]),
    ('payload-success-with-null', [3, 2, 1, 0, 0, 0, 1, 1, 0, 1, 1]),
    ('zero-length-null', [0, 1, 0, 1, 1, 1, 2, 2, 0, 1, 1]),
    ('zero-length-pointer', [0, 1, 0, 1, 1, 1, 2, 2, 0, 1, 1]),
    ('running-copy', [0, 2, 0, 2, 1, 1, 2, 2, 1, 1, 1]),
    ('initialized-copy', [0, 2, 0, 2, 1, 1, 2, 2, 1, 1, 1]),
    ('two-copies-fifo', [0, 4, 0, 4, 2, 2, 4, 4, 2, 1, 1]),
)


def extract(text, name):
    matches = list(re.finditer(r'^(?:VOID|NDIS_STATUS)\s+' + re.escape(name) +
                              r'\s*\([^;{}]*\)\s*\{', text, re.M))
    if len(matches) != 1:
        raise ValueError('Unique complete CmdQ function required: ' + name)
    match = matches[0]
    start, depth = text.index('{', match.start()), 0
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*|[{}]'
    for token in re.finditer(tokens, text[start:]):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if not depth:
                return text[match.start():start + token.end()]
    raise ValueError('Unterminated CmdQ function: ' + name)


def segment(text, start, end):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('Unique production declaration boundaries required')
    return text.split(start, 1)[1].split(end, 1)[0]


def generate_source(texts):
    if set(texts) != set(SOURCE_PATHS) or not all(type(x) is str for x in texts.values()):
        raise ValueError('Exact CmdQ sources required')
    types = 'typedef struct _CmdQElmt' + segment(texts['header'], 'typedef struct _CmdQElmt', '#define NDIS_OID')
    states = 'typedef enum _RTMP_TASK_STATUS_' + segment(texts['os'], 'typedef enum _RTMP_TASK_STATUS_', '#define RTMP_OS_TASK_NAME_LEN')
    statuses = []
    for name in ('NDIS_STATUS_SUCCESS', 'NDIS_STATUS_FAILURE', 'NDIS_STATUS_RESOURCES'):
        definitions = re.findall(r'^#define\s+' + name + r'\s+0x[0-9a-fA-F]+\s*$', texts['linux'], re.M)
        if len(definitions) != 1:
            raise ValueError('Unique real NDIS status required: ' + name)
        statuses.append(definitions[0])
    return (PREFIX + '\n' + '\n'.join(statuses) + '\n' + types + '\n' + states +
            '\n' + SEAMS + '\n' + '\n'.join(extract(texts['queue'], n) for n in BODY_ORDER) + MAIN)


def function_manifest(texts):
    return {name: {'execution': 'whole-function', 'full_body_sha256': hashlib.sha256(
        extract(texts[FUNCTION_SOURCES[name]], name).encode()).hexdigest()} for name in BODY_ORDER}


PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define IN
#define OUT
#define TRUE 1
#define FALSE 0
typedef void VOID;
typedef void *PVOID;
typedef unsigned char UCHAR, *PUCHAR, BOOLEAN;
typedef unsigned int UINT, UINT32;
typedef unsigned long ULONG;
typedef int NDIS_STATUS;
#define NDIS_OID UINT
#define fRTMP_ADAPTER_NIC_NOT_EXIST 1
#define MTWF_LOG(...) ((void)0)
'''

SEAMS = r'''
typedef struct _RTMP_ADAPTER { CmdQ CmdQ; int CmdQLock, cmdQTask, missing; } RTMP_ADAPTER, *PRTMP_ADAPTER;
static RTMP_ADAPTER adapter;
static int attempts, frees, live, locks, unlocks, copies, wakeups, held;
static int fail_at, null_at, stop_at, stop_after_unlock;
static void *owned[8];
static int fixture_missing(RTMP_ADAPTER *p, int flag) { assert(p && flag==1); return p->missing; }
#define RTMP_TEST_FLAG(p,f) fixture_missing(p,f)
static void fixture_lock(int *lock, ULONG *flag) { assert(lock==&adapter.CmdQLock && !held); held=1; *flag=0; locks++; }
static void fixture_unlock(int *lock, ULONG *flag) {
 assert(lock==&adapter.CmdQLock && held && *flag==0); held=0; unlocks++;
 if(stop_after_unlock && unlocks==1)adapter.CmdQ.CmdQState=RTMP_TASK_STAT_STOPED;
}
#define RTMP_SPIN_LOCK_IRQSAVE(p,f) fixture_lock(p,f)
#define RTMP_SPIN_UNLOCK_IRQRESTORE(p,f) fixture_unlock(p,f)
static NDIS_STATUS fixture_alloc(RTMP_ADAPTER *p, PUCHAR *out, size_t size) {
 assert(p==&adapter && out && size && !held); *out=NULL; attempts++;
 if(stop_at==attempts)adapter.CmdQ.CmdQState=RTMP_TASK_STAT_STOPED;
 if(fail_at==attempts)return NDIS_STATUS_RESOURCES;
 if(null_at==attempts)return NDIS_STATUS_SUCCESS;
 assert(attempts<=8); *out=calloc(1,size); assert(*out); owned[attempts-1]=*out; live++;
 return NDIS_STATUS_SUCCESS;
}
#define os_alloc_mem(p,o,s) fixture_alloc(p,o,s)
static void fixture_free(void *p) {
 int i, found=0; assert(p && !held);
 for(i=0;i<8;i++)if(owned[i]==p){owned[i]=NULL;found=1;break;}
 assert(found); free(p); frees++; live--;
}
#define os_free_mem(p) fixture_free(p)
static void fixture_copy(void *out, const void *in, size_t size) {
 assert(out && in && size && !held); copies++; memcpy(out,in,size);
}
#define NdisMoveMemory(o,i,s) fixture_copy(o,i,s)
#define NdisZeroMemory(o,s) memset(o,0,s)
static void fixture_wake(int *task) { assert(task==&adapter.cmdQTask && !held && adapter.CmdQ.size); wakeups++; }
#define RTCMDUp(p) fixture_wake(p)
'''

MAIN = r'''
int main(int argc, char **argv) {
 const char *name; unsigned char input[4]={0x11,0x22,0x33,0x44};
 const unsigned char wanted[4]={0x11,0x22,0x33,0x44};
 RTMP_ADAPTER *p=&adapter; void *data=input; UINT length=sizeof(input);
 int status, count=1, i, payload_ok=1, metadata_ok=1, saved[11]; PCmdQElmt e;
 assert(argc==2); name=argv[1]; RTInitializeCmdQ(&adapter.CmdQ); adapter.CmdQ.CmdQState=RTMP_TASK_STAT_RUNNING;
 if(!strcmp(name,"null-adapter"))p=NULL;
 else if(!strcmp(name,"null-payload"))data=NULL;
 else if(!strcmp(name,"nic-absent"))adapter.missing=1;
 else if(!strcmp(name,"queue-already-stopped"))adapter.CmdQ.CmdQState=RTMP_TASK_STAT_STOPED;
 else if(!strcmp(name,"stop-after-preflight"))stop_after_unlock=1;
 else if(!strcmp(name,"stop-after-element-allocation"))stop_at=1;
 else if(!strcmp(name,"stop-after-payload-allocation"))stop_at=2;
 else if(!strcmp(name,"element-allocation-failure"))fail_at=1;
 else if(!strcmp(name,"payload-allocation-failure"))fail_at=2;
 else if(!strcmp(name,"element-success-with-null"))null_at=1;
 else if(!strcmp(name,"payload-success-with-null"))null_at=2;
 else if(!strcmp(name,"zero-length-null")){length=0;data=NULL;}
 else if(!strcmp(name,"zero-length-pointer"))length=0;
 else if(!strcmp(name,"running-copy")){}
 else if(!strcmp(name,"initialized-copy"))adapter.CmdQ.CmdQState=RTMP_TASK_STAT_INITED;
 else if(!strcmp(name,"two-copies-fifo"))count=2;
 else return 2;
 status=RTEnqueueInternalCmd(p,0x51,data,length);
 if(count==2){assert(status==NDIS_STATUS_SUCCESS);status=RTEnqueueInternalCmd(p,0x52,data,length);}
 memset(input,0xfd,sizeof(input)); i=0;
 for(e=adapter.CmdQ.head;e;e=e->next,i++){
  if(e->command!=(UINT)(0x51+i) || e->CmdFromNdis!=FALSE || e->bufferlength!=length)metadata_ok=0;
  if(length ? (!e->buffer || e->buffer==input || memcmp(e->buffer,wanted,length)) : e->buffer!=NULL)payload_ok=0;
 }
 assert(!held && i==(int)adapter.CmdQ.size);
 saved[0]=status;saved[1]=attempts;saved[2]=frees;saved[3]=live;saved[4]=adapter.CmdQ.size;
 saved[5]=wakeups;saved[6]=locks;saved[7]=unlocks;saved[8]=copies;saved[9]=metadata_ok;saved[10]=payload_ok;
 while(adapter.CmdQ.size){
  RTThreadDequeueCmd(&adapter.CmdQ,&e);assert(e);
  if(e->buffer)os_free_mem(e->buffer);
  os_free_mem(e);
 }
 assert(!live && !adapter.CmdQ.head && !adapter.CmdQ.tail);
 for(i=0;i<8;i++)assert(!owned[i]);
 printf("[");for(i=0;i<11;i++)printf("%s%d",i?",":"",saved[i]);puts("]"); return 0;
}
'''
