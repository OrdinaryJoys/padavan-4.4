#!/usr/bin/env python3
"""Actual watchdog callbacks with real timer signals and inert router effects."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

from test_httpd_regressions import function, source


class WatchdogDnsRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-watchdog-dns-')
        cls.root = Path(cls.temp.name)
        text = source('trunk/user/rc/watchdog.c')
        bodies = '\n'.join(function(text, name) for name in
                           ('dnsmasq_process_check', 'watchdog_on_timer'))
        code = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/time.h>
#include <stdlib.h>
#define RCN_RECOVER_DNSMASQ "recover_dnsmasq"
static volatile sig_atomic_t feeds,notifications,starts,logs,queries;
static double ticks[16];
static int dnsmasq_missing,ap_mode,inhibited,dns_running;
static int firmware_upgrade_inhibited(void){return inhibited;}
static int is_dns_dhcpd_run(void){queries++;return dns_running;}
static int get_ap_mode(void){return ap_mode;}
static void logmessage(const char*a,const char*b){assert(!strcmp(a,"watchdog"));(void)b;logs++;}
static void notify_rc(const char*name){assert(!strcmp(name,RCN_RECOVER_DNSMASQ));notifications++;}
static void hw_watchdog_feed(void){
 struct timespec t;assert(clock_gettime(CLOCK_MONOTONIC,&t)==0);
 if(feeds<16)ticks[feeds]=(double)t.tv_sec+t.tv_nsec/1e9;
 feeds++;
}
static void svc_timecheck(void){}
static void httpd_process_check(void){}
static void inet_handler(int a){(void)a;}
static void setkernel_tz(void){}
static void storage_save_time(int a){(void)a;}
/* This slow DNS stub makes the old synchronous callback visibly miss ticks. */
static int start_dns_dhcpd(int ap){
 struct timespec delay={1,0};assert(ap==0);starts++;
 while(nanosleep(&delay,&delay)) {}
 return 0;
}
'''
        code += bodies + r'''
static void alarm_handler(int sig){assert(sig==SIGALRM);watchdog_on_timer();}
static void timer_case(void){
 struct sigaction sa;struct itimerval timer;int i;double largest=0;
 memset(&sa,0,sizeof(sa));sa.sa_handler=alarm_handler;sigemptyset(&sa.sa_mask);
 assert(sigaction(SIGALRM,&sa,0)==0);
 memset(&timer,0,sizeof(timer));timer.it_value.tv_usec=50000;timer.it_interval=timer.it_value;
 assert(setitimer(ITIMER_REAL,&timer,0)==0);
 while(feeds<6)pause();
 memset(&timer,0,sizeof(timer));assert(setitimer(ITIMER_REAL,&timer,0)==0);
 for(i=1;i<6;i++)if(ticks[i]-ticks[i-1]>largest)largest=ticks[i]-ticks[i-1];
 assert(starts==0 && largest<0.75);
 if(ap_mode || inhibited)assert(notifications==0 && queries==0 && logs==0);
 else assert(notifications==3 && logs==3);
 printf("{\"feeds\":%d,\"notifications\":%d,\"starts\":%d,\"largest_feed_gap\":%.6f}\n",
        (int)feeds,(int)notifications,(int)starts,largest);
}
int main(int argc,char**argv){
 assert(argc==2);assert(firmware_upgrade_inhibited()==0);
 if(!strcmp(argv[1],"timer") || !strcmp(argv[1],"timer_ap") || !strcmp(argv[1],"timer_inhibited")){
  ap_mode=!strcmp(argv[1],"timer_ap");inhibited=!strcmp(argv[1],"timer_inhibited");timer_case();
 }else if(!strcmp(argv[1],"missing")){
  dnsmasq_process_check();assert(dnsmasq_missing==1 && notifications==0 && logs==0);
  dnsmasq_process_check();assert(dnsmasq_missing==0 && notifications==1 && logs==1 && starts==0);
 }else if(!strcmp(argv[1],"healthy")){
  dnsmasq_missing=1;dns_running=1;dnsmasq_process_check();
  assert(dnsmasq_missing==0 && notifications==0 && logs==0 && starts==0);
 }else if(!strcmp(argv[1],"inhibited")){
  dnsmasq_missing=1;inhibited=1;dnsmasq_process_check();
  assert(dnsmasq_missing==0 && notifications==0 && queries==0 && logs==0);
 }else if(!strcmp(argv[1],"inhibit_release")){
  dnsmasq_process_check();assert(dnsmasq_missing==1);
  inhibited=1;dnsmasq_process_check();assert(dnsmasq_missing==0 && queries==1);
  inhibited=0;dnsmasq_process_check();assert(dnsmasq_missing==1 && notifications==0);
  dnsmasq_process_check();assert(dnsmasq_missing==0 && notifications==1 && starts==0);
 }else if(!strcmp(argv[1],"slow_stub_control")){
  struct timespec before,after;double elapsed;
  assert(clock_gettime(CLOCK_MONOTONIC,&before)==0);start_dns_dhcpd(0);
  assert(clock_gettime(CLOCK_MONOTONIC,&after)==0);
  elapsed=after.tv_sec-before.tv_sec+(after.tv_nsec-before.tv_nsec)/1e9;
  assert(starts==1 && elapsed>=0.9);
 }else if(!strcmp(argv[1],"notify_stub_control"))notify_rc(RCN_RECOVER_DNSMASQ);
 else assert(0);
 return 0;
}
'''
        cfile = cls.root / 'callbacks.c'
        cfile.write_text(code)
        compilers = [('clang', ['-fsanitize=address,undefined'])]
        gcc = shutil.which('gcc-16') or shutil.which('gcc')
        if not gcc:
            raise RuntimeError('A GCC-compatible strict C compiler is required')
        compilers.append((gcc, []))
        cls.binaries = []
        for index, (compiler, flags) in enumerate(compilers):
            binary = cls.root / f'callbacks-{index}'
            result = subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror',
                                     *flags, str(cfile), '-o', str(binary)],
                                    capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, name):
        results = []
        for binary in self.binaries:
            with self.subTest(binary=binary.name):
                results.append(subprocess.run([str(binary), name], check=True,
                                              capture_output=True, text=True, timeout=5))
        return results

    def test_real_sigalrm_ticks_keep_feeding_without_starting_dns(self):
        for result in self.run_case('timer'):
            observed = json.loads(result.stdout)
            self.assertGreaterEqual(observed['feeds'], 6)
            self.assertEqual((observed['notifications'], observed['starts']), (3, 0))

    def test_missing_dns_requires_two_checks_and_only_queues_recovery(self):
        self.run_case('missing')

    def test_healthy_dns_resets_missing_counter(self):
        self.run_case('healthy')

    def test_upgrade_inhibit_resets_counter_before_query_log_or_queue(self):
        self.run_case('inhibited')

    def test_upgrade_inhibit_release_requires_two_fresh_missing_checks(self):
        self.run_case('inhibit_release')

    def test_access_point_timer_keeps_feeding_without_dns_recovery(self):
        self.run_case('timer_ap')

    def test_inhibited_timer_keeps_feeding_without_dns_recovery(self):
        self.run_case('timer_inhibited')

    def test_slow_dns_stub_control_really_waits_one_second(self):
        self.run_case('slow_stub_control')


if __name__ == '__main__':
    unittest.main()
