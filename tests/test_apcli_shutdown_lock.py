"""Run the production APCLI RTNL admission with deterministic host threads.

The fixture models lock ownership and stopping publication, not hardware or
Linux RTNL internals. The module itself is also compiled by the MIPS build.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import wdev_lifecycle_harness as h

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615'
SRC = DRIVER / 'embedded/ap/ap_apcli.c'
MAIN = DRIVER / 'os/linux/rt_main_dev.c'
MLME = DRIVER / 'embedded/common/mlme.c'
SCAN = DRIVER / 'embedded/common/scan.c'
CLOSE = DRIVER / 'embedded/common/rtmp_init_inf.c'

C = r'''
#define _DEFAULT_SOURCE
#include <pthread.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <assert.h>
typedef int BOOLEAN;
#define TRUE 1
#define FALSE 0
#define READ_ONCE(x) atomic_load(&(x))
typedef struct { atomic_int dma_removing, stopping; } RTMP_ADAPTER;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static atomic_int attempts, finished, result, flip;
static RTMP_ADAPTER a;
static int RtmpDmaStopping(RTMP_ADAPTER *p) { return atomic_load(&p->stopping); }
static int rtnl_trylock(void) {
 int ok = pthread_mutex_trylock(&lock) == 0;
 atomic_fetch_add(&attempts, 1);
 if (ok && atomic_load(&flip)) atomic_store(&a.stopping, 1);
 return ok;
}
static void rtnl_unlock(void) { assert(pthread_mutex_unlock(&lock) == 0); }
static void msleep(int ms) { usleep((unsigned)ms * 1000); }
static void RtmpOSNetDevProtect(int acquire) {
 if (acquire) assert(pthread_mutex_lock(&lock) == 0); else rtnl_unlock();
}
/* actual production function follows */
%s
static void *worker(void *arg) {
 int r = ApCliAutoConnectLock(&a); (void)arg;
 atomic_store(&result, r);
 if (r) rtnl_unlock();
 atomic_store(&finished, 1);
 return NULL;
}
static void until(atomic_int *v) {
 int n; for (n=0; n<2000 && !atomic_load(v); n++) usleep(1000);
 assert(atomic_load(v));
}
int main(int argc, char **argv) {
 pthread_t t; int i; assert(argc == 2);
 if (!strcmp(argv[1], "post-acquire-stop")) {
  atomic_store(&flip,1); assert(!ApCliAutoConnectLock(&a));
  assert(pthread_mutex_trylock(&lock)==0); rtnl_unlock(); return 0;
 }
 assert(pthread_mutex_lock(&lock)==0);
 assert(pthread_create(&t,NULL,worker,NULL)==0); until(&attempts);
 if (!strcmp(argv[1],"removing")) atomic_store(&a.dma_removing,1);
 else if (!strcmp(argv[1],"stopping")) atomic_store(&a.stopping,1);
 else if (strcmp(argv[1],"retry")) abort();
 if (strcmp(argv[1],"retry")) {
  for (i=0; i<1000 && !atomic_load(&finished); i++) usleep(1000);
  assert(atomic_load(&finished) && !atomic_load(&result));
  /* We still hold RTNL: cancellation must not release the closer's lock. */
  assert(pthread_mutex_trylock(&lock)!=0);
 }
 rtnl_unlock();
 assert(pthread_join(t,NULL)==0);
 if (!strcmp(argv[1],"retry")) assert(atomic_load(&result));
 return 0;
}
'''

class ApCliShutdownLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = os.environ.get('K2P_APCLI_TARGET_CC')
        if target:
            triple = subprocess.check_output([target, '-dumpmachine'], text=True).strip()
            if not triple.startswith('mipsel-') or not shutil.which('qemu-mipsel'):
                raise RuntimeError('MIPS compiler and qemu-mipsel are required')
            print('APCLI_SHUTDOWN_TARGET=mipsel-linux-uclibc;RUNNER=qemu-mipsel', flush=True)

    def test_production_lock_interleavings_and_mutant(self):
        source = h.function(SRC.read_text(), 'ApCliAutoConnectLock')
        self.assertIn('rtnl_trylock()', source)
        with tempfile.TemporaryDirectory(prefix='k2p-apcli-lock-') as tmp:
            src, binary = Path(tmp)/'test.c', Path(tmp)/'test'
            src.write_text(C % source)
            compilers = [shutil.which('gcc-16'), shutil.which('clang')]
            target = os.environ.get('K2P_APCLI_TARGET_CC')
            if target:
                compilers.append(target)
            for cc in compilers:
                self.assertTrue(cc)
                flags = ['-static'] if cc == target and target else []
                subprocess.run([cc,'-std=gnu11','-O2','-pthread','-Wall','-Wextra',
                                '-Werror','-Wno-unused-function','-DCONFIG_K2P_RESET_GUARD',
                                *flags,str(src),'-o',str(binary)],check=True,timeout=90)
                run = [shutil.which('qemu-mipsel'), str(binary)] if cc == target and target else [str(binary)]
                for case in ('removing','stopping','post-acquire-stop','retry'):
                    subprocess.run([*run,case],check=True,timeout=8)
                if cc == target and target and os.environ.get('K2P_APCLI_TARGET_DIR'):
                    dest = Path(os.environ['K2P_APCLI_TARGET_DIR'])
                    shutil.copyfile(src, dest/'target-apcli-shutdown.c')
                    shutil.copyfile(binary, dest/'target-apcli-shutdown.elf')
            # Removing both stop checks must reproduce the stuck worker while
            # the closer retains RTNL, rather than quietly passing the test.
            broken = source.replace('READ_ONCE(pAd->dma_removing) || RtmpDmaStopping(pAd)', '0')
            self.assertNotEqual(source, broken)
            src.write_text(C % broken)
            subprocess.run([compilers[0],'-std=gnu11','-O2','-pthread','-Wno-unused-function',
                            '-DCONFIG_K2P_RESET_GUARD',str(src),'-o',str(binary)],check=True)
            bad = subprocess.run([str(binary),'removing'],capture_output=True,timeout=5)
            self.assertNotEqual(bad.returncode, 0)

    def test_production_shutdown_and_mlme_paths_are_wired(self):
        ap = SRC.read_text()
        for name, count in [('ApCliAutoConnectExec',2),('ApCliSwitchCandidateAP',1)]:
            body = h.function(ap,name)
            self.assertEqual(body.count('ApCliAutoConnectLock(pAd)'),count)
            self.assertEqual(body.count('RtmpOSNetDevProtect(0)'),count)
            self.assertNotIn('RtmpOSNetDevProtect(1)',body)
        main = MAIN.read_text()
        close = h.function(main,'RtmpPhyNetDevCloseAll')
        self.assertLess(close.index('WRITE_ONCE(pAd->dma_removing, TRUE)'),close.index('dev_close('))
        self.assertIn('RtmpPhyNetDevCloseAll(pAd, pAd->net_dev)',h.function(main,'RtmpDmaShutdown'))
        self.assertIn('RTMPDrvClose(pAd, net_dev)',h.function(main,'mt_wifi_close'))
        self.assertIn('MlmeHalt(pAd)',h.function(CLOSE.read_text(),'RTMPDrvClose'))
        self.assertIn('pAd->dma_stopping = TRUE',h.function(main,'RtmpDmaTeardownCheck'))
        self.assertIn('RtmpOSTaskKill(pTask)',h.function(MLME.read_text(),'MlmeHalt'))
        self.assertIn('ApCliAutoConnectExec(pAd, wdev)',SCAN.read_text())

if __name__ == '__main__':
    unittest.main()
