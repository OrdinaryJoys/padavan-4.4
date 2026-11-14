"""Run the production RAETH shutdown/RTNL functions with owned-lock threads.

The fixture models device/owner state and jiffies. It does not execute Linux
RTNL, kernel scheduling, an interrupt controller or physical DMA hardware.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from mt7621_wdt_harness import function

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c'

FIXTURE = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CONFIG_K2P_RESET_GUARD 1
#define HZ 100UL
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
#define WRITE_ONCE(a,b) ((a)=(b))
#define REBOOT_DMA_RAETH 1
#undef ETIMEDOUT
#define ETIMEDOUT 110
#define pr_err(...) ((void)0)
struct reboot_guard { int generation; };
struct net_device { int attached, tx; void *priv; char name[12]; };
struct END_DEVICE { bool dma_quarantined; struct reboot_guard reset_device,reset_dma;
 struct net_device *pseudo_dev; void *kreset_task,*kphy_poll_task; };
struct platform_device { struct net_device *dev; };
static struct END_DEVICE owner;
static struct net_device main_dev, pseudo;
static struct platform_device platform;
static pthread_mutex_t network = PTHREAD_MUTEX_INITIALIZER, barrier = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static int start_owner, owns_lock, release_owner, phase, owner_started, failure, parks;
static int locks,unlock_count,detach_count,mdio_count,proc_count,tx_count,irq_count,stop_count,finished;
static unsigned long jiffies;
static jmp_buf parked;
static const char *scenario;
static void *owner_thread(void *p) {
 (void)p; assert(!pthread_mutex_lock(&barrier));
 while(!start_owner) assert(!pthread_cond_wait(&changed,&barrier));
 assert(!pthread_mutex_unlock(&barrier)); assert(!pthread_mutex_lock(&network));
 assert(!pthread_mutex_lock(&barrier)); owns_lock=1; assert(!pthread_cond_broadcast(&changed));
 while(!release_owner) assert(!pthread_cond_wait(&changed,&barrier));
 assert(!pthread_mutex_unlock(&barrier)); assert(!pthread_mutex_unlock(&network)); return NULL;
}
static void start_contender(void) {
 assert(!pthread_mutex_lock(&barrier));start_owner=1;assert(!pthread_cond_broadcast(&changed));
 while(!owns_lock) assert(!pthread_cond_wait(&changed,&barrier));
 assert(!pthread_mutex_unlock(&barrier));owner_started=1;
}
static int rtnl_trylock(void) {
 if (!strcmp(scenario,"retry") && phase==0 && locks++<3) return 0;
 if(pthread_mutex_trylock(&network))return 0;
 return 1;
}
static void rtnl_unlock(void) { unlock_count++; assert(!pthread_mutex_unlock(&network)); }
static void msleep(int ms) { assert(ms==20); jiffies+=2; }
static void reboot_guard_fail(struct reboot_guard *g,unsigned int why) { assert(g==&owner.reset_device&&why==REBOOT_DMA_RAETH);failure++; }
static void reboot_guard_finish(struct reboot_guard *g) { assert(g->generation);g->generation=0;finished++; }
static void reboot_dma_failure_check(bool sleep) { assert(sleep && failure); parks++; longjmp(parked,1); }
static struct net_device *platform_get_drvdata(struct platform_device *p) { return p->dev; }
static void *netdev_priv(struct net_device *d) { return d->priv; }
static void netif_device_detach(struct net_device *d) { d->attached=0;detach_count++; }
static void mii_mgr_detach(void) { phase=1;mdio_count++; }
static void debug_proc_exit(void) { proc_count++; if(!strcmp(scenario,"second"))start_contender(); }
static void netif_tx_disable(struct net_device *d) { d->tx=0;tx_count++; }
static int kthread_stop(void *p) { assert(p);return 0; }
static int fe_int_disable(struct net_device *d) { assert(d);irq_count++;return 0; }
static int ei_stop_dma(struct net_device *d) { assert(d);stop_count++;return 0; }
%s
%s
int main(int argc,char **argv) {
 pthread_t worker; int jumped;
 assert(argc==2);scenario=argv[1];platform.dev=&main_dev;main_dev.priv=&owner;
 main_dev.attached=pseudo.attached=1;main_dev.tx=pseudo.tx=1;owner.pseudo_dev=&pseudo;
 owner.reset_device.generation=1;owner.reset_dma.generation=1;
 if(!strcmp(scenario,"first")||!strcmp(scenario,"wrap")||!strcmp(scenario,"second")){
  assert(!pthread_create(&worker,NULL,owner_thread,NULL));
  if(strcmp(scenario,"second"))start_contender();
 }
 if(!strcmp(scenario,"wrap"))jiffies=~0UL-2*HZ;
 jumped=setjmp(parked);
 if(!jumped)raether_shutdown(&platform);
 if(!strcmp(scenario,"first")||!strcmp(scenario,"wrap")) {
  assert(jumped && failure==1 && parks==1 && owner_started);
  assert(!detach_count && !mdio_count && !proc_count && !tx_count && !irq_count && !stop_count && !finished);
  assert(owner.reset_device.generation && owner.reset_dma.generation && !owner.dma_quarantined);
 } else if(!strcmp(scenario,"second")) {
  assert(jumped && failure==1 && parks==1 && owner_started);
  assert(detach_count==2 && mdio_count==1 && proc_count==1 && !tx_count && !irq_count && !stop_count && !finished);
  assert(owner.reset_device.generation && owner.reset_dma.generation && owner.dma_quarantined);
 } else {
  assert(!jumped && !failure && !parks && detach_count==2 && mdio_count==1 && proc_count==1);
  assert(tx_count==2 && irq_count==1 && stop_count==1 && finished==2 && unlock_count==2);
  assert(!owner.reset_device.generation && !owner.reset_dma.generation);
  if(!strcmp(scenario,"retry"))assert(jiffies==6);
 }
 if(owner_started){
  assert(!pthread_mutex_lock(&barrier));release_owner=1;assert(!pthread_cond_broadcast(&changed));
  assert(!pthread_mutex_unlock(&barrier));assert(!pthread_join(worker,NULL));
 }
 return 0;
}
'''

class RaethShutdownRtnlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = os.environ.get('K2P_RAETH_RTNL_TARGET_CC')
        if target:
            triple = subprocess.check_output([target, '-dumpmachine'], text=True).strip()
            if not triple.startswith('mipsel-') or not shutil.which('qemu-mipsel'):
                raise RuntimeError('MIPS compiler and qemu-mipsel are required')
            print('RAETH_RTNL_TARGET=mipsel-linux-uclibc;RUNNER=qemu-mipsel', flush=True)

    def test_real_shutdown_lock_interleavings_and_negative_control(self):
        source = SOURCE.read_text()
        helper = function(source,'raether_shutdown_rtnl')
        shutdown = function(source,'raether_shutdown')
        code = FIXTURE % (helper,shutdown)
        with tempfile.TemporaryDirectory(prefix='k2p-raeth-rtnl-') as tmp:
            src, binary = Path(tmp)/'test.c', Path(tmp)/'test'
            src.write_text(code)
            target = os.environ.get('K2P_RAETH_RTNL_TARGET_CC')
            compilers = [(shutil.which('gcc-16'), [], []),
                         (shutil.which('clang'), ['-fsanitize=address,undefined','-fno-sanitize-recover=all'], [])]
            if target:
                compilers.append((target,['-static'],[shutil.which('qemu-mipsel')]))
            for cc, flags, runner in compilers:
                self.assertTrue(cc and all(runner))
                subprocess.run([cc,'-std=gnu11','-O2','-pthread','-Wall','-Wextra','-Werror',
                                '-Wno-unused-function',*flags,str(src),'-o',str(binary)],check=True,timeout=90)
                for case in ('normal','retry','first','second','wrap'):
                    subprocess.run([*runner,str(binary),case],check=True,timeout=12,
                                   env={**os.environ,'ASAN_OPTIONS':'symbolize=0'})
                if cc==target and target and os.environ.get('K2P_RAETH_RTNL_TARGET_DIR'):
                    dest=Path(os.environ['K2P_RAETH_RTNL_TARGET_DIR'])
                    shutil.copyfile(src,dest/'target-raeth-rtnl.c')
                    shutil.copyfile(binary,dest/'target-raeth-rtnl.elf')
            old='reboot_guard_fail(&ei_local->reset_device, REBOOT_DMA_RAETH);'
            self.assertEqual(helper.count(old),1)
            src.write_text(FIXTURE % (helper.replace(old,'(void)0;'),shutdown))
            subprocess.run([compilers[0][0],'-std=gnu11','-O2','-pthread','-Wno-unused-function',
                            str(src),'-o',str(binary)],check=True,timeout=90)
            broken=subprocess.run([str(binary),'first'],capture_output=True,timeout=12)
            self.assertNotEqual(broken.returncode,0)

    def test_both_shutdown_acquisitions_are_guarded(self):
        source=SOURCE.read_text()
        helper=function(source,'raether_shutdown_rtnl')
        shutdown=function(source,'raether_shutdown')
        self.assertIn('40UL * HZ',helper)
        self.assertIn('time_after_eq(jiffies, deadline)',helper)
        self.assertLess(helper.index('reboot_guard_fail('),helper.index('return -ETIMEDOUT;'))
        self.assertEqual(shutdown.count('raether_shutdown_rtnl(ei_local)'),2)
        self.assertEqual(shutdown.count('reboot_dma_failure_check(true);'),2)
        self.assertLess(shutdown.index('mii_mgr_detach();'),shutdown.rindex('raether_shutdown_rtnl(ei_local)'))
        self.assertLess(shutdown.rindex('raether_shutdown_rtnl(ei_local)'),shutdown.index('ei_stop_dma(dev)'))

if __name__ == '__main__':
    unittest.main()
