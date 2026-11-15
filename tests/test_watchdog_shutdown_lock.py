"""Real watchdog shutdown/remove bodies with simulated MMIO and contended mutex.

This does not model the hardware counter, scheduler or MMIO bus.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from mt7621_wdt_harness import function

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'trunk/linux-4.4.x/drivers/watchdog/mt7621_wdt.c'

FIXTURE = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#define CONFIG_K2P_RESET_GUARD 1
#define HZ 100UL
#define time_after_eq(a,b) ((long)((a)-(b)) >= 0)
#define REBOOT_WATCHDOG_UNSAFE 8
#define WDOG_ACTIVE 0
struct reboot_guard { int generation; };
struct watchdog_device { pthread_mutex_t lock; unsigned long status; };
struct platform_device { int dev; };
static struct watchdog_device mt762x_wdt_dev = {PTHREAD_MUTEX_INITIALIZER,1};
static struct reboot_guard watchdog_guard = {1};
static bool watchdog_retired;
static unsigned long jiffies;
static pthread_mutex_t barrier = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
static bool owner_ready, release_owner;
static int tries, fail_tries, failure, park, stops, finishes, unregisters, stuck;
static jmp_buf trapped;
static void *hold_lock(void *unused) {
 (void)unused; assert(!pthread_mutex_lock(&mt762x_wdt_dev.lock));
 assert(!pthread_mutex_lock(&barrier)); owner_ready=true; assert(!pthread_cond_broadcast(&cv));
 while(!release_owner) assert(!pthread_cond_wait(&cv,&barrier));
 assert(!pthread_mutex_unlock(&barrier)); assert(!pthread_mutex_unlock(&mt762x_wdt_dev.lock)); return NULL;
}
static int mutex_trylock(pthread_mutex_t *m) { tries++; if(tries<=fail_tries)return 0; return !pthread_mutex_trylock(m); }
static void mutex_unlock(pthread_mutex_t *m) { assert(!pthread_mutex_unlock(m)); }
static void msleep(unsigned int ms) { assert(ms==20); jiffies+=2; }
static void reboot_guard_fail(struct reboot_guard *g,unsigned int why) { assert(g==&watchdog_guard && why==REBOOT_WATCHDOG_UNSAFE); failure++; }
static void reboot_guard_finish(struct reboot_guard *g) { assert(g==&watchdog_guard);g->generation=0; finishes++; }
static void reboot_dma_failure_check(bool may_sleep) { assert(may_sleep && failure); park++; longjmp(trapped,1); }
static int mt762x_wdt_stop(struct watchdog_device *w) { assert(w==&mt762x_wdt_dev); stops++;return stuck ? -EIO : 0; }
static void clear_bit(unsigned int b,unsigned long *w) { *w &= ~(1UL<<b); }
static void watchdog_unregister_device(struct watchdog_device *w) { assert(w==&mt762x_wdt_dev); unregisters++; }
#define dev_err(...) ((void)0)
%s
%s
%s
int main(int argc,char **argv) {
 struct platform_device p={0}; pthread_t t; bool held;
 assert(argc==2); held=!strcmp(argv[1],"held") || !strcmp(argv[1],"wrap") || !strcmp(argv[1],"remove-held");
 if(!strcmp(argv[1],"wrap"))jiffies=~0UL-40;
 if(!strcmp(argv[1],"retry"))fail_tries=3;
 if(!strcmp(argv[1],"stuck"))stuck=1;
 if(held) { assert(!pthread_create(&t,0,hold_lock,0)); assert(!pthread_mutex_lock(&barrier));
  while(!owner_ready) { assert(!pthread_cond_wait(&cv,&barrier)); }
  assert(!pthread_mutex_unlock(&barrier)); }
 if(!setjmp(trapped)) {
  if(!strcmp(argv[1],"remove-held") || !strcmp(argv[1],"remove")) mt762x_wdt_remove(&p);
  else mt762x_wdt_shutdown(&p);
  assert(!held);
 }
 if(held) { assert(park==1 && failure==1 && !watchdog_retired && !stops && !finishes && !unregisters);
  assert(watchdog_guard.generation && mt762x_wdt_dev.status==1);
  assert(!pthread_mutex_lock(&barrier));release_owner=true;assert(!pthread_cond_broadcast(&cv));
  assert(!pthread_mutex_unlock(&barrier));assert(!pthread_join(t,0));
 } else if(stuck) { assert(watchdog_retired && stops==1 && failure==1 && !finishes && !park); }
 else { assert(watchdog_retired && stops==1 && !failure && finishes==1 && !park && !mt762x_wdt_dev.status);
  assert(unregisters==(!strcmp(argv[1],"remove") ? 1 : 0));
  if(fail_tries)assert(tries==4 && jiffies==6);
 }
 return 0;
}
'''

class WatchdogShutdownLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('K2P_WDT_LOCK_TARGET_CC'):
            print('WDT_SHUTDOWN_LOCK_TARGET=mipsel-linux-uclibc;RUNNER=qemu-mipsel', flush=True)

    def test_actual_bodies_and_concurrent_owners(self):
        code = SOURCE.read_text()
        bodies = [function(code, n) for n in ('mt762x_wdt_shutdown_lock', 'mt762x_wdt_shutdown', 'mt762x_wdt_remove')]
        text = FIXTURE % tuple(bodies)
        cc = [('gcc', shutil.which('gcc-16'), []), ('clang', shutil.which('clang'), ['-fsanitize=address,undefined', '-fno-sanitize-recover=all'])]
        target = os.environ.get('K2P_WDT_LOCK_TARGET_CC')
        if target:
            runner = shutil.which('qemu-mipsel')
            self.assertTrue(runner, 'qemu-mipsel required')
            cc.append(('target', target, ['-static']))
        with tempfile.TemporaryDirectory(prefix='k2p-wdt-lock-') as tmp:
            c=Path(tmp)/'case.c';c.write_text(text)
            for name, compiler, flags in cc:
                self.assertTrue(compiler, name)
                exe=Path(tmp)/name
                subprocess.run([compiler,'-std=gnu11','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter',*flags,str(c),'-o',str(exe)],check=True,timeout=90)
                if name=='target':
                    dest=Path(os.environ['K2P_WDT_LOCK_TARGET_DIR']);dest.mkdir(parents=True,exist_ok=True)
                    (dest/'target-wdt-shutdown-lock.c').write_text(text);shutil.copyfile(exe,dest/'target-wdt-shutdown-lock.elf')
                for scenario in ('normal','retry','held','wrap','stuck','remove','remove-held'):
                    subprocess.run(([runner] if name=='target' else [])+[str(exe),scenario],check=True,timeout=20)

    def test_unreported_failure_negative_control(self):
        code=SOURCE.read_text(); helper=function(code,'mt762x_wdt_shutdown_lock')
        self.assertIn('reboot_guard_fail(&watchdog_guard, REBOOT_WATCHDOG_UNSAFE);',helper)
        mutant=helper.replace('reboot_guard_fail(&watchdog_guard, REBOOT_WATCHDOG_UNSAFE);','(void)0;')
        text=FIXTURE % (mutant,function(code,'mt762x_wdt_shutdown'),function(code,'mt762x_wdt_remove'))
        with tempfile.TemporaryDirectory(prefix='k2p-wdt-negative-') as tmp:
            c=Path(tmp)/'case.c';c.write_text(text);exe=Path(tmp)/'case'
            subprocess.run([shutil.which('gcc-16'),'-std=gnu11','-O1','-pthread',str(c),'-o',str(exe)],check=True,timeout=60)
            result=subprocess.run([str(exe),'held'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            self.assertNotEqual(result.returncode,0)

if __name__ == '__main__': unittest.main()
