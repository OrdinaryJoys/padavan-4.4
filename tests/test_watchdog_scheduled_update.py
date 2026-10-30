"""Real scheduler bodies, timer signals and inert update/reboot backends."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_httpd_regressions import function, source

PRELUDE = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#define BOARD_HAS_5G_RADIO 0
#define RADIO2_ACTIVE 0
#define GUEST2_ACTIVE 1
#define RCN_SCHEDULE_DLINK "schedule_dlink_update"
static int svcStatus[2],enabled=1,ready=1,eligible=1,inhibited,launch_error,time_error,local_error;
static char schedule[32]="11111112359";
static long seconds=100;
static volatile sig_atomic_t feeds,queued,launches,logs;
static double ticks[16];
static int firmware_upgrade_inhibited(void){return inhibited;}
static long uptime(void){return seconds;}
static int nvram_match(const char*k,const char*v){
 assert(!strcmp(v,"1"));
 if(!strcmp(k,"ss_schedule_enable"))return enabled;
 if(!strcmp(k,"ntp_ready"))return ready;
 return 0;
}
static char* nvram_safe_get(const char*k){
 if(!strcmp(k,"ss_schedule"))return schedule;
 if(!strcmp(k,"time_zone_x"))return "UTC";
 return "";
}
static int get_enabled_radio_rt(void){return 0;}
static int is_radio_allowed_rt(void){return 0;}
static int is_guest_allowed_rt(void){return 0;}
static int nvram_set_int_temp(const char*k,int v){(void)k;(void)v;return 0;}
static void logmessage(const char*a,const char*b,...){(void)a;(void)b;logs++;}
static int sys_exit(void){assert(!"unexpected reboot");return 0;}
static void notify_rc(const char*name){assert(!strcmp(name,RCN_SCHEDULE_DLINK));queued++;}
static int _eval(char*const args[],char*output,int timeout,pid_t*child){
 assert(!strcmp(args[0],"/bin/sh")&&!strcmp(args[1],"/usr/bin/update_dlink.sh"));
 assert(!strcmp(args[2],"update")&&!args[3]);assert(!output&&!timeout&&child);
 launches++;*child=1234;return launch_error;
}
static int get_ap_mode(void){return 0;}
static void dnsmasq_process_check(void){}
static void httpd_process_check(void){}
static void inet_handler(int ap){assert(ap==0);}
static void setkernel_tz(void){}
static void storage_save_time(int value){assert(value==10);}
static void hw_watchdog_feed(void){
 struct timespec now;assert(!clock_gettime(CLOCK_MONOTONIC,&now));
 if(feeds<16)ticks[feeds]=now.tv_sec+now.tv_nsec/1e9;
 feeds++;
}
static time_t controlled_time(time_t*value){if(time_error)return(time_t)-1;*value=0;return 0;}
static struct tm* controlled_localtime(const time_t*value){
 static struct tm out;(void)value;if(local_error)return NULL;
 memset(&out,0,sizeof(out));out.tm_wday=5;out.tm_hour=23;out.tm_min=59;return &out;
}
#define time controlled_time
#define localtime controlled_localtime
'''

SUFFIX = r'''
static void alarm_handler(int sig){assert(sig==SIGALRM);watchdog_on_timer();}
int main(int argc,char**argv){
 assert(argc==2);assert(!firmware_upgrade_inhibited());assert(uptime()==100);
 assert(get_enabled_radio_rt()==0 && is_radio_allowed_rt()==0 && is_guest_allowed_rt()==0);
 assert(!nvram_set_int_temp("fixture",0));assert(!nvram_match("fixture","1"));
 assert(!strcmp(nvram_safe_get("time_zone_x"),"UTC"));assert(get_ap_mode()==0);
 if(!strcmp(argv[1],"valid")){
  assert(watchdog_schedule_valid("11111112359"));
  assert(watchdog_schedule_valid("00000100000"));
  assert(!watchdog_schedule_valid(NULL));assert(!watchdog_schedule_valid("111111123590"));
  assert(!watchdog_schedule_valid("00000002359"));assert(!watchdog_schedule_valid("11111112400"));
  assert(!watchdog_schedule_valid("11111112360"));assert(!watchdog_schedule_valid("1111111235x"));
  assert(!watchdog_schedule_valid("21111112359"));
 }else if(!strcmp(argv[1],"time")){
  assert(timecheck_reboot("11111112359")==1);
  assert(timecheck_reboot("00000102359")==1);
  assert(timecheck_reboot("10000002359")==0);
  assert(timecheck_reboot("11111112358")==0);
  assert(timecheck_reboot("11111112400")==0);
  time_error=1;assert(timecheck_reboot("11111112359")==0);time_error=0;
  local_error=1;assert(timecheck_reboot("11111112359")==0);
 }else if(!strcmp(argv[1],"launcher")){
#ifdef APP_SHADOWSOCKS
  start_scheduled_dlink();assert(launches==1&&logs==0);
  launch_error=EAGAIN;start_scheduled_dlink();assert(launches==2&&logs==1);
#endif
 }else if(!strcmp(argv[1],"timer")){
  struct sigaction sa;struct itimerval timer;int i;double gap=0;
  memset(&sa,0,sizeof(sa));sa.sa_handler=alarm_handler;sigemptyset(&sa.sa_mask);
  assert(!sigaction(SIGALRM,&sa,0));memset(&timer,0,sizeof(timer));
  timer.it_value.tv_usec=50000;timer.it_interval=timer.it_value;
  assert(!setitimer(ITIMER_REAL,&timer,0));while(feeds<6)pause();
  memset(&timer,0,sizeof(timer));assert(!setitimer(ITIMER_REAL,&timer,0));
  for(i=1;i<6;i++)if(ticks[i]-ticks[i-1]>gap)gap=ticks[i]-ticks[i-1];
  assert(gap<0.75&&launches==0);
#ifdef APP_SHADOWSOCKS
  assert(queued==1);
#else
  assert(queued==0);
#endif
 }else{
  if(!strcmp(argv[1],"disabled"))enabled=0;
  else if(!strcmp(argv[1],"not-ready"))ready=0;
  else if(!strcmp(argv[1],"inhibited"))inhibited=1;
  else if(!strcmp(argv[1],"bad"))strcpy(schedule,"11111112499");
  else if(!strcmp(argv[1],"debounce")){}
  else if(!strcmp(argv[1],"clock-backward")){}
  else assert(!"unknown scenario");
  svc_timecheck();
#ifdef APP_SHADOWSOCKS
  if(!strcmp(argv[1],"debounce")){
   assert(queued==1);seconds=169;svc_timecheck();assert(queued==1);
   seconds=170;svc_timecheck();assert(queued==2);
  }else if(!strcmp(argv[1],"clock-backward")){
   assert(queued==1);seconds=90;svc_timecheck();assert(queued==2);
   svc_timecheck();assert(queued==2);
  }else assert(queued==0);
#else
  assert(queued==0);
#endif
  assert(launches==0);
 }
 /* Keep inert callback definitions checked in both feature profiles. */
 assert(eligible);return 0;
}
'''


def generate_driver(watchdog, rc, enabled):
    code = PRELUDE
    if enabled:
        code = '#define APP_SHADOWSOCKS 1\n' + code
    for name in ('watchdog_schedule_valid', 'timecheck_reboot'):
        code += function(watchdog, name) + '\n'
    if enabled:
        code += function(watchdog, 'watchdog_schedule_dlink') + '\n'
        code += function(rc, 'start_scheduled_dlink') + '\n'
    for name in ('svc_timecheck', 'watchdog_on_timer'):
        code += function(watchdog, name) + '\n'
    return code + SUFFIX


class ScheduledUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import re
        macro = r'^#define\s+RCN_SCHEDULE_DLINK\s+("[^"\n]+")\s*$'
        if re.findall(macro, source('trunk/user/shared/notify_rc.h'), re.MULTILINE) != re.findall(macro, PRELUDE, re.MULTILINE):
            raise RuntimeError('Scheduled update event header/fixture mismatch')
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-scheduled-update-')
        cls.root = Path(cls.temp.name)
        cls.binaries = {}
        gcc = shutil.which('gcc-16') or shutil.which('gcc')
        if not gcc:
            raise RuntimeError('GCC compiler required')
        for enabled in (True, False):
            cfile = cls.root / f'watchdog-{enabled}.c'
            cfile.write_text(generate_driver(source('trunk/user/rc/watchdog.c'), source('trunk/user/rc/rc.c'), enabled))
            cls.binaries[enabled] = []
            for index, (compiler, flags) in enumerate((('clang', ['-fsanitize=address,undefined']), (gcc, []))):
                binary = cls.root / f'watchdog-{enabled}-{index}'
                result = subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror',
                                         '-Wno-unused-function', *flags, str(cfile), '-o', str(binary)],
                                        capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError(result.stderr)
                cls.binaries[enabled].append(binary)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check_case(self, name, enabled=True):
        for binary in self.binaries[enabled]:
            subprocess.run([str(binary), name], check=True, capture_output=True, timeout=5)

    def test_exact_week_mask_and_time_grammar_without_integer_overflow(self):
        self.check_case('valid')

    def test_full_week_and_selected_day_match_with_time_failures_rejected(self):
        self.check_case('time')

    def test_feed_path_never_waits_for_eligible_update(self):
        self.check_case('timer')

    def test_unbuilt_component_ignores_stale_enabled_schedule(self):
        self.check_case('timer', False)

    def test_monotonic_debounce_replaces_sleep(self):
        self.check_case('debounce')

    def test_monotonic_clock_restart_does_not_keep_stale_deadline(self):
        self.check_case('clock-backward')

    def test_disabled_not_ready_inhibited_and_invalid_never_queue(self):
        for case in ('disabled', 'not-ready', 'inhibited', 'bad'):
            self.check_case(case)

    def test_pid1_launcher_only_spawns_fixed_update_arguments(self):
        self.check_case('launcher')


if __name__ == '__main__':
    unittest.main()
