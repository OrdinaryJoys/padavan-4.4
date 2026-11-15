"""Actual NOR shutdown supervisor and worker with simulated concurrent owners.

Kernel scheduling, timer softirq, SPI hardware and flash effects are models.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from mt7621_wdt_harness import function
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'trunk/linux-4.4.x/drivers/mtd/devices/m25p80.c'
C=r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define CONFIG_K2P_RESET_GUARD 1
#define HZ 100UL
#define REBOOT_DMA_UNKNOWN 1
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_SEQ_CST)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_SEQ_CST)
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
struct reboot_guard { int generation; };
struct spi_nor { struct reboot_guard reset_device; };
struct m25p { struct spi_nor spi_nor; };
struct spi_device { struct m25p *data; int dev; };
struct timer_list { void (*function)(unsigned long); unsigned long data; pthread_t thread; int started; };
struct completion {int done;};
#define DECLARE_COMPLETION_ONSTACK(n) struct completion n={0}
struct task_struct {pthread_t thread;int (*fn)(void*);void *arg;int result,refs,started,joined;};
%s
%s
static struct m25p flash={.spi_nor={.reset_device={1}}};static struct spi_device spi={.data=&flash};
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;static pthread_cond_t cv=PTHREAD_COND_INITIALIZER;
static int fire,cancel,callback_entered,callback_release,callback_done,timer_join_entered;
static int restore_entered,restore_release,force_timeout,force_join_timeout,exit_release,restore_error;
static int failures,parks,returned,restore_returned,logs,allow_return,create_oom,hold_callback;
static unsigned long jiffies=100;static struct task_struct task;static struct m25p_shutdown_work *worker_data;
static void *spi_get_drvdata(struct spi_device*s){return s->data;}
static void reboot_guard_fail(struct reboot_guard*g,unsigned int reason){assert(g==&flash.spi_nor.reset_device&&reason==REBOOT_DMA_UNKNOWN);
 assert(!pthread_mutex_lock(&lock));callback_entered=1;assert(!pthread_cond_broadcast(&cv));
 while(hold_callback&&!callback_release) { assert(!pthread_cond_wait(&cv,&lock)); }failures++;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));}
static void reboot_dma_failure_check(bool sleep){assert(sleep);assert(!pthread_mutex_lock(&lock));assert(failures);parks++;assert(!pthread_cond_broadcast(&cv));
 while(!allow_return) { assert(!pthread_cond_wait(&cv,&lock)); }assert(!pthread_mutex_unlock(&lock));}
static void *timer_main(void *data){struct timer_list*t=data;assert(!pthread_mutex_lock(&lock));while(!fire&&!cancel)assert(!pthread_cond_wait(&cv,&lock));
 int run=fire;assert(!pthread_mutex_unlock(&lock));if(run)t->function(t->data);
 assert(!pthread_mutex_lock(&lock));callback_done=1;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));return NULL;}
#define setup_timer_on_stack(t,fn,arg) do {(t)->function=(fn);(t)->data=(arg);(t)->started=0;} while(0)
static void mod_timer(struct timer_list*t,unsigned long deadline){assert(deadline==jiffies+120UL*HZ);t->started=1;assert(!pthread_create(&t->thread,NULL,timer_main,t));}
static void del_timer_sync(struct timer_list*t){assert(t->started);assert(!pthread_mutex_lock(&lock));timer_join_entered=1;cancel=1;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));assert(!pthread_join(t->thread,NULL));t->started=0;}
static void destroy_timer_on_stack(struct timer_list*t){assert(!t->started);}
static void complete(struct completion*c){assert(!pthread_mutex_lock(&lock));c->done=1;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));}
static void wait_for_completion(struct completion*c){assert(!pthread_mutex_lock(&lock));while(!c->done)assert(!pthread_cond_wait(&cv,&lock));assert(!pthread_mutex_unlock(&lock));}
static unsigned long wait_for_completion_timeout(struct completion*c,unsigned long timeout){assert(timeout==100UL*HZ);assert(!pthread_mutex_lock(&lock));
 while(!c->done&&!force_timeout) { assert(!pthread_cond_wait(&cv,&lock)); }int done=c->done;assert(!pthread_mutex_unlock(&lock));return done?1:0;}
static void *worker_main(void *p){struct task_struct*t=p;t->result=t->fn(t->arg);assert(!pthread_mutex_lock(&lock));
 while(force_join_timeout&&!exit_release) { assert(!pthread_cond_wait(&cv,&lock)); }assert(!pthread_mutex_unlock(&lock));return NULL;}
static struct task_struct *fake_kthread_create(int(*fn)(void*),void*arg){if(create_oom)return (void*)-ENOMEM;task.fn=fn;task.arg=arg;worker_data=arg;return &task;}
#define kthread_create(fn,arg,name) fake_kthread_create((fn),(arg))
static void get_task_struct(struct task_struct*t){assert(t==&task);t->refs++;}
static void put_task_struct(struct task_struct*t){assert(t==&task&&t->refs>0);t->refs--;}
static void wake_up_process(struct task_struct*t){t->started=1;assert(!pthread_create(&t->thread,NULL,worker_main,t));}
static int kthread_stop_timeout(struct task_struct*t,unsigned long timeout,int*result){assert(t==&task&&timeout==10UL*HZ);
 if(force_join_timeout){t->refs++;return -ETIMEDOUT;}assert(!pthread_join(t->thread,NULL));t->joined=1;*result=t->result;return 0;}
static int spi_nor_restore(struct spi_nor*n){assert(n==&flash.spi_nor);assert(!pthread_mutex_lock(&lock));restore_entered=1;assert(!pthread_cond_broadcast(&cv));
 while(!restore_release) { assert(!pthread_cond_wait(&cv,&lock)); }restore_returned=1;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));return restore_error;}
#define dev_err(...) do { logs++; } while(0)
%s
%s
%s
static void *run_shutdown(void *unused){(void)unused;m25p_shutdown(&spi);assert(!pthread_mutex_lock(&lock));returned++;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));return NULL;}
static void wait_flag(int *p){while(!*p)assert(!pthread_cond_wait(&cv,&lock));}
int main(int argc,char**argv){pthread_t coordinator;assert(argc==2);
 int blocked=!strcmp(argv[1],"blocked"),race=!strcmp(argv[1],"race"),join_stuck=!strcmp(argv[1],"join-timeout");
 create_oom=!strcmp(argv[1],"oom");hold_callback=race;force_join_timeout=join_stuck;restore_release=!(blocked||race);
 if(!strcmp(argv[1],"error"))restore_error=-EIO;
 assert(!pthread_create(&coordinator,NULL,run_shutdown,NULL));assert(!pthread_mutex_lock(&lock));
 if(create_oom){wait_flag(&parks);assert(failures&&!task.started&&!returned);}
 else {wait_flag(&restore_entered);
  if(blocked){force_timeout=1;assert(!pthread_cond_broadcast(&cv));wait_flag(&parks);assert(failures&&!restore_returned&&!returned&&task.refs>=1);
   restore_release=1;assert(!pthread_cond_broadcast(&cv));wait_flag(&restore_returned);while(!worker_data->done->done)assert(!pthread_cond_wait(&cv,&lock));
   assert(!returned&&parks==1);worker_data->release->done=1;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));assert(!pthread_join(task.thread,NULL));assert(!pthread_mutex_lock(&lock));}
  else if(race){fire=1;assert(!pthread_cond_broadcast(&cv));wait_flag(&callback_entered);restore_release=1;assert(!pthread_cond_broadcast(&cv));wait_flag(&timer_join_entered);assert(!callback_done&&!returned);callback_release=1;assert(!pthread_cond_broadcast(&cv));wait_flag(&parks);assert(failures&&!returned&&task.joined);}
  else if(join_stuck){wait_flag(&parks);assert(failures&&!returned&&task.refs>=2);exit_release=1;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));assert(!pthread_join(task.thread,NULL));assert(!pthread_mutex_lock(&lock));}
  else {wait_flag(&returned);assert(!failures&&!parks&&task.joined&&task.refs==0&&logs==!!restore_error);}
 }
 allow_return=1;assert(!pthread_cond_broadcast(&cv));assert(!pthread_mutex_unlock(&lock));assert(!pthread_join(coordinator,NULL));return 0;}
'''
def generated(mutant=False):
 text=SOURCE.read_text();watch=re.search(r'struct m25p_shutdown_watch\s*\{[^}]+\};',text).group();work=re.search(r'struct m25p_shutdown_work\s*\{[^}]+\};',text).group()
 cb=function(text,'m25p_shutdown_timeout');worker=function(text,'m25p_shutdown_worker');shutdown=function(text,'m25p_shutdown')
 if mutant:
  needle='reboot_guard_fail(&watch->nor->reset_device, REBOOT_DMA_UNKNOWN);';assert cb.count(needle)==1
  cb=cb.replace(needle,'do { assert(!pthread_mutex_lock(&lock)); callback_entered=1; assert(!pthread_cond_broadcast(&cv)); assert(!pthread_mutex_unlock(&lock)); } while (0);')
 return C%(watch,work,worker,cb,shutdown)
class NorShutdownWatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if os.environ.get('K2P_NOR_WATCH_TARGET_CC'):print('NOR_SHUTDOWN_WATCH_TARGET=mipsel-linux-uclibc;RUNNER=qemu-mipsel',flush=True)
 def test_actual_shutdown_with_stalled_and_late_spi(self):
  target=os.environ.get('K2P_NOR_WATCH_TARGET_CC');runner=shutil.which('qemu-mipsel') if target else None
  cc=[('gcc',shutil.which('gcc-16'),[]),('clang',shutil.which('clang'),['-fsanitize=address,undefined','-fno-sanitize-recover=all'])]
  if target:self.assertTrue(runner);cc.append(('target',target,['-static']))
  with tempfile.TemporaryDirectory(prefix='k2p-nor-watch-') as tmp:
   src=Path(tmp)/'watch.c';src.write_text(generated())
   for name,compiler,flags in cc:
    self.assertTrue(compiler);exe=Path(tmp)/name
    subprocess.run([compiler,'-std=gnu11','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter',*flags,str(src),'-o',str(exe)],check=True,timeout=90)
    if name=='target':
     dest=Path(os.environ['K2P_NOR_WATCH_TARGET_DIR']);dest.mkdir(parents=True,exist_ok=True)
     (dest/'target-nor-shutdown-watch.c').write_text(src.read_text());shutil.copyfile(exe,dest/'target-nor-shutdown-watch.elf')
    for case in ('normal','error','oom','blocked','race','join-timeout'):subprocess.run(([runner] if name=='target' else [])+[str(exe),case],check=True,timeout=20)
 def test_dropping_failure_report_is_detected(self):
  with tempfile.TemporaryDirectory(prefix='k2p-nor-watch-negative-') as tmp:
   src=Path(tmp)/'watch.c';src.write_text(generated(True));exe=Path(tmp)/'watch'
   subprocess.run([shutil.which('gcc-16'),'-std=gnu11','-O1','-pthread',str(src),'-o',str(exe)],check=True,timeout=60)
   result=subprocess.run([str(exe),'race'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20);self.assertNotEqual(result.returncode,0)
if __name__=='__main__':unittest.main()
