"""Actual timed kthread stop body under explicit task/stack ownership models."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from mt7621_wdt_harness import function
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'trunk/linux-4.4.x/kernel/kthread.c'
C=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
struct completion {int done;};
struct kthread {unsigned long flags;struct completion exited;};
struct task_struct {int refs,stack_refs,exit_code,live,wakes,unparks;struct kthread kt;};
#define KTHREAD_SHOULD_STOP 1
#undef ETIMEDOUT
#define ETIMEDOUT 145
static int wait_calls;static unsigned long wait_budget;
static void get_task_struct(struct task_struct*t){t->refs++;}
static void put_task_struct(struct task_struct*t){assert(t->refs>0);t->refs--;}
static void put_task_stack(struct task_struct*t){assert(t->stack_refs==1);t->stack_refs--;}
static struct kthread *to_live_kthread(struct task_struct*t){if(!t->live)return NULL;t->stack_refs++;return &t->kt;}
static void set_bit(int n,unsigned long*p){*p|=1UL<<n;}
static void __kthread_unpark(struct task_struct*t,struct kthread*k){assert(k==&t->kt);t->unparks++;}
static void wake_up_process(struct task_struct*t){t->wakes++;}
static unsigned long wait_for_completion_timeout(struct completion*c,unsigned long t){wait_calls++;wait_budget=t;return c->done?1:0;}
%s
int main(int argc,char**argv){struct task_struct task={.refs=1,.live=1,.exit_code=-145};int out=777,rc;assert(argc==2);
 if(!strcmp(argv[1],"invalid")){assert(kthread_stop_timeout(&task,100,NULL)==-EINVAL);assert(task.refs==1&&!task.stack_refs&&!task.wakes);return 0;}
 if(!strcmp(argv[1],"done"))task.kt.exited.done=1;
 else if(!strcmp(argv[1],"gone"))task.live=0;
 else if(strcmp(argv[1],"timeout"))abort();
 rc=kthread_stop_timeout(&task,100,&out);
 if(!strcmp(argv[1],"timeout")){
  assert(rc==-ETIMEDOUT && out==777 && task.refs==2 && !task.stack_refs);
  assert((task.kt.flags&(1UL<<KTHREAD_SHOULD_STOP)) && task.wakes==1 && task.unparks==1 && wait_calls==1 && wait_budget==100);
  task.live=0;task.exit_code=0;assert(task.refs==2);put_task_struct(&task);assert(task.refs==1);
 }else {
  assert(rc==0 && out==-145 && task.refs==1 && !task.stack_refs);
  if(task.live)assert(wait_calls==1 && task.wakes==1 && task.unparks==1);
  else assert(!wait_calls && !task.wakes && !task.unparks);
 }
 return 0;}
'''
class KthreadStopTimeoutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if os.environ.get('K2P_KTHREAD_TIMEOUT_TARGET_CC'):print('KTHREAD_STOP_TIMEOUT_TARGET=mipsel-linux-uclibc;RUNNER=qemu-mipsel',flush=True)
 def test_actual_stop_balances_refs_and_separates_exit_code(self):
  target=os.environ.get('K2P_KTHREAD_TIMEOUT_TARGET_CC');runner=shutil.which('qemu-mipsel') if target else None
  compilers=[('gcc',shutil.which('gcc-16'),[]),('clang',shutil.which('clang'),['-fsanitize=address,undefined','-fno-sanitize-recover=all'])]
  if target:self.assertTrue(runner);compilers.append(('target',target,['-static']))
  body=function(SOURCE.read_text(),'kthread_stop_timeout');code=C%body
  with tempfile.TemporaryDirectory(prefix='k2p-kthread-timeout-') as tmp:
   src=Path(tmp)/'test.c';src.write_text(code)
   for name,cc,flags in compilers:
    self.assertTrue(cc);exe=Path(tmp)/name
    subprocess.run([cc,'-std=gnu11','-O1','-Wall','-Wextra','-Werror',*flags,str(src),'-o',str(exe)],check=True,timeout=60)
    if name=='target':
     dest=Path(os.environ['K2P_KTHREAD_TIMEOUT_TARGET_DIR']);dest.mkdir(parents=True,exist_ok=True)
     (dest/'target-kthread-stop-timeout.c').write_text(code);shutil.copyfile(exe,dest/'target-kthread-stop-timeout.elf')
    for case in ('done','gone','timeout','invalid'):subprocess.run(([runner] if name=='target' else [])+[str(exe),case],check=True,timeout=10)
 def test_timeout_without_reference_is_detected(self):
  body=function(SOURCE.read_text(),'kthread_stop_timeout');needle='\tget_task_struct(k);';self.assertEqual(body.count(needle),1)
  code=C%body.replace(needle,'\t/* no retained reference */',1)
  with tempfile.TemporaryDirectory(prefix='k2p-kthread-negative-') as tmp:
   src=Path(tmp)/'test.c';src.write_text(code);exe=Path(tmp)/'test'
   subprocess.run([shutil.which('gcc-16'),'-std=gnu11','-O1',str(src),'-o',str(exe)],check=True,timeout=60)
   done=subprocess.run([str(exe),'timeout'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10);self.assertNotEqual(done.returncode,0)
if __name__=='__main__':unittest.main()
