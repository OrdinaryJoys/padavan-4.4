"""Complete current task init/attach/kill with private ref-counted kernel mocks.

Single serialized lifecycle owner; no kernel task or module is executed.
"""
import hashlib
import re

BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'os':BASE+'os/linux/rt_linux.c','os_header':BASE+'include/os/rt_linux.h',
 'task_header':BASE+'embedded/include/rtmp_os.h'}
FUNCTION_SOURCES={'__RtmpOSTaskInit':'os','__RtmpOSTaskAttach':'os','__RtmpOSTaskKill':'os'}
BODY_ORDER=('__RtmpOSTaskInit','__RtmpOSTaskAttach','__RtmpOSTaskKill')
CASE_NAMES=('create-failure','create-order','natural-early-exit','nonzero-exit',
 'repeat-kill','existing-owner','kill-no-owner')
FIELDS=('result','creates','gets','wakes','stops','puts','destroyed','refs_before_kill',
 'natural_before_kill','owner_preserved','waitqueue_inits','owner_present_final','event_count','events')
EXPECTED_ROWS={
 'create-failure':[1,1,0,0,0,0,0,0,0,1,1,0,1,1],
 'create-order':[0,1,1,1,1,1,1,2,0,1,1,0,6,1,2,3,4,5,6],
 'natural-early-exit':[0,1,1,1,1,1,1,1,1,1,1,0,7,1,2,3,7,4,5,6],
 'nonzero-exit':[0,1,1,1,1,1,1,1,1,1,1,0,7,1,2,3,7,4,5,6],
 'repeat-kill':[1,1,1,1,1,1,1,2,0,1,1,0,6,1,2,3,4,5,6],
 'existing-owner':[1,1,1,1,1,1,1,2,0,1,1,0,6,1,2,3,4,5,6],
 'kill-no-owner':[1,0,0,0,0,0,0,0,0,1,1,0,0]}
PREFIX=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define IN
#define KTHREAD_SUPPORT
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define RTMP_OS_TASK_NAME_LEN 16
#define ASSERT(p) assert(p)
#define MTWF_LOG(...) ((void)0)
#define os_move_mem(d,s,n) memmove((d),(s),(n))
typedef int NDIS_STATUS;typedef char RTMP_STRING;typedef void VOID;
typedef unsigned long ULONG;typedef int LIST_HEADER;
/* The private callback ABI uses ULONG throughout; no kernel ABI is invoked. */
typedef int (*RTMP_OS_TASK_CALLBACK)(ULONG);typedef int (*cast_fn)(ULONG);
struct task_struct;
typedef struct OS_TASK {struct task_struct *kthread_task;int task_killed,kthread_q;void *priv;char taskName[16];} OS_TASK;
struct task_struct {int refs,started,exited,exit_code;cast_fn fn;void *arg;};
static OS_TASK *active;
static int creates,gets,wakes,stops,puts,destroyed,waits,fail_create,natural,callback_result;
static int events[16],event_count;
static void event(int n){assert(event_count<16);events[event_count++]=n;}
#define IS_ERR(p) ((intptr_t)(p)<0)
#define PTR_ERR(p) ((long)(intptr_t)(p))
static void init_waitqueue_head(int *q){assert(active->kthread_task==NULL);*q=++waits;}
static struct task_struct *kthread_create(cast_fn fn,void *arg,const char *name) {
 struct task_struct *t;assert(name);creates++;event(1);assert(active->kthread_task==NULL);
 if(fail_create)return (void*)(intptr_t)-12;
 t=calloc(1,sizeof(*t));assert(t);t->refs=1;t->fn=fn;t->arg=arg;return t;
}
static void get_task_struct(struct task_struct *t){assert(t&&t->refs==1&&!t->started);
 assert(active->kthread_task==NULL);t->refs++;gets++;event(2);}
static void wake_up_process(struct task_struct *t){assert(active->kthread_task==t&&t->refs==2&&!t->started);
 t->started=1;wakes++;event(3);
 if(natural){t->exit_code=t->fn((ULONG)t->arg);t->exited=1;t->refs--;assert(t->refs==1);event(7);}
}
static int kthread_stop(struct task_struct *t){assert(t==active->kthread_task&&t->refs>0&&t->started);
 stops++;event(4);t->refs++; /* temporary internal kernel reference */
 if(!t->exited){t->exit_code=t->fn((ULONG)t->arg);t->exited=1;t->refs--;}
 t->refs--;assert(t->refs==1);return t->exit_code;
}
static void put_task_struct(struct task_struct *t){assert(active->kthread_task==NULL&&t->refs==1&&t->exited);
 puts++;event(5);t->refs--;destroyed++;event(6);free(t);}
static int callback(ULONG value){assert(value==7);return callback_result;}
'''
SUFFIX=r'''
int main(int argc,char **argv){const char *name;OS_TASK task;struct task_struct *saved;
 int result=0,refs=0,early=0,preserved=1,i,old_wait;char old_name[16];void *old_priv;
 assert(argc==2);name=argv[1];CASE_ADMISSION memset(&task,0,sizeof(task));active=&task;
 assert(__RtmpOSTaskInit(&task,"original",(void*)(uintptr_t)8,NULL)==0);
 if(!strcmp(name,"kill-no-owner"))result=__RtmpOSTaskKill(&task);
 else {
  fail_create=!strcmp(name,"create-failure");natural=!strcmp(name,"natural-early-exit")||!strcmp(name,"nonzero-exit");
  if(!strcmp(name,"nonzero-exit"))callback_result=-4;
  result=__RtmpOSTaskAttach(&task,callback,7);
  if(task.kthread_task){refs=task.kthread_task->refs;early=task.kthread_task->exited;}
  if(!strcmp(name,"existing-owner")) {
   saved=task.kthread_task;old_wait=task.kthread_q;old_priv=task.priv;memcpy(old_name,task.taskName,16);task.task_killed=7;
   assert(__RtmpOSTaskInit(&task,"replacement",(void*)(uintptr_t)9,NULL)==1);
   result=__RtmpOSTaskAttach(&task,callback,7);
   preserved=task.kthread_task==saved&&task.task_killed==7&&task.kthread_q==old_wait&&task.priv==old_priv&&!memcmp(old_name,task.taskName,16);
  }
  if(task.kthread_task)assert(__RtmpOSTaskKill(&task)==0);
  if(!strcmp(name,"repeat-kill"))result=__RtmpOSTaskKill(&task);
 }
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d",result,creates,gets,wakes,stops,puts,destroyed,
 refs,early,preserved,waits,task.kthread_task!=NULL,event_count);
 for(i=0;i<event_count;i++){printf(",%d",events[i]);}
 puts("]");assert(task.kthread_task==NULL&&gets==puts&&gets==destroyed);return 0;
}
'''


def function(text,name):
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    found=list(re.finditer(r'^static\s+inline\s+NDIS_STATUS\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked,re.M))
    if len(found)!=1:raise ValueError('Missing/ambiguous task function: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated task function: '+name)


def generate_source(texts,variant='current'):
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current task inputs required')
    for name,value in (('SUCCESS',0),('FAILURE',1)):
        found=re.findall(r'^#define NDIS_STATUS_'+name+r'\s+(0x[0-9a-fA-F]+)\s*$',texts['os_header'],re.M)
        if len(found)!=1 or int(found[0],16)!=value:raise ValueError('Actual task status changed')
    if not re.search(r'^#define RTMP_OS_TASK_NAME_LEN\s+16$',texts['task_header'],re.M):raise ValueError('Task name capacity changed')
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    # Rename only this recorder counter; libc puts remains the real output API.
    prefix=re.sub(r'\bputs\b','put_count',PREFIX)
    prefix=re.sub(r'\bgets\b','get_count',prefix)
    suffix=re.sub(r'\bgets\b','get_count',SUFFIX)
    suffix=suffix.replace('get_count==puts','get_count==put_count').replace('stops,puts,destroyed','stops,put_count,destroyed')
    return prefix+'\n'.join(function(texts['os'],name)for name in BODY_ORDER)+suffix.replace('CASE_ADMISSION',admission)


def function_manifest(texts):
    return {name:{'source':'os','execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts['os'],name).encode()).hexdigest()}
            for name in BODY_ORDER}
