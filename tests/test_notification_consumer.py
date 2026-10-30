#!/usr/bin/env python3
"""Compile the real queue consumer while replacing router-only callbacks."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_httpd_regressions import function

ROOT=Path(__file__).resolve().parents[1]


class ConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        root=Path(cls.tmp.name)
        consumer=function((ROOT/'trunk/user/rc/rc.c').read_text(),'handle_notifications')
        standard={'handle_notifications','rc_notification_open_dir','rc_notification_valid_marker',
                  'firmware_upgrade_inhibited','get_ap_mode','is_dns_dhcpd_run','start_dns_dhcpd',
                  'fdopendir','close','readdir','strcmp','unlinkat','snprintf','remove','printf',
                  'fopen','fclose','closedir','kill','getpid','if','for','while','sizeof','defined'}
        calls=set(re.findall(r'\b([a-zA-Z_]\w*)\s*\(',consumer))
        code=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <assert.h>
#include <string.h>
#include <dirent.h>
#include <signal.h>
static char queue_path[1024],pending_path[1024];
static int events,signals,producer_signals,dns_starts,dns_stops,dns_running,ap_mode,inhibited,start_failure;
static int nvram_nf_nat_type;
static int fake_signal(pid_t p,int s){assert(s==SIGUSR1);if(p==1)producer_signals++;else {assert(p==getpid());signals++;}return 0;}
static int fake_printf(const char *f,...){if(!strcmp(f,"rc notification: %s\n"))events++;return 0;}
static int firmware_upgrade_inhibited(void){return inhibited;}
static int get_ap_mode(void){return ap_mode;}
static int is_dns_dhcpd_run(void){return dns_running;}
static int start_dns_dhcpd(int ap){assert(ap==0);dns_starts++;if(!start_failure)dns_running=1;return start_failure;}
#define NOTIFY_RC_H
#define DIR_RC_NOTIFY queue_path
#define DIR_RC_INCOMPLETE pending_path
#define kill fake_signal
'''
        code+='#include "'+str(ROOT/'trunk/user/shared/notify_rc.c')+'"\n'
        for line in (ROOT/'trunk/user/shared/notify_rc.h').read_text().splitlines():
            if line.startswith('#define RCN_'):code+=line+'\n'
        for name in sorted(calls-standard):
            code+='#define '+name+'(...) 0\n'
        code+='#undef restart_dhcpd\n#define restart_dhcpd(...) (dns_stops++,0)\n'
        code+='#define printf fake_printf\n'+consumer+'\n#undef printf\n'
        code+=r'''
int main(int argc,char **argv){
 char path[1200],victim[1200],pending[1200];int i,fd;FILE*f;
 assert(argc==3);umask(0);
 snprintf(queue_path,sizeof(queue_path),"%s/queue",argv[2]);
 snprintf(pending_path,sizeof(pending_path),"%s/pending",argv[2]);
 assert(mkdir(queue_path,0700)==0 && mkdir(pending_path,0700)==0);
 if(!strcmp(argv[1],"batches")){
  for(i=0;i<25;i++){snprintf(path,sizeof(path),"%s/event_%02d",queue_path,i);fd=open(path,O_WRONLY|O_CREAT,0600);assert(fd>=0);close(fd);}
  handle_notifications();assert(events==10 && signals==1);
  handle_notifications();assert(events==20 && signals==2);
  handle_notifications();assert(events==25 && signals==2);
 }else if(!strcmp(argv[1],"unsafe_markers")){
  snprintf(victim,sizeof(victim),"%s/victim",argv[2]);f=fopen(victim,"w");assert(f);fputs("keep",f);fclose(f);
  snprintf(path,sizeof(path),"%s/flash_firmware",queue_path);assert(symlink(victim,path)==0);
  snprintf(path,sizeof(path),"%s/restart_reboot",queue_path);fd=open(path,O_WRONLY|O_CREAT,0666);assert(fd>=0);close(fd);
  handle_notifications();assert(events==0 && signals==0);
  f=fopen(victim,"r");assert(f && fgetc(f)=='k');fclose(f);
 }else if(!strcmp(argv[1],"writable_queue")){
  chmod(queue_path,0777);snprintf(path,sizeof(path),"%s/restart_reboot",queue_path);fd=open(path,O_WRONLY|O_CREAT,0600);assert(fd>=0);close(fd);
  handle_notifications();assert(events==0 && signals==0 && access(path,F_OK)==0);
 }else if(!strncmp(argv[1],"dns_",4)){
  notify_rc(RCN_RECOVER_DNSMASQ);
  snprintf(path,sizeof(path),"%s/%s",queue_path,RCN_RECOVER_DNSMASQ);
  snprintf(pending,sizeof(pending),"%s/%s",pending_path,RCN_RECOVER_DNSMASQ);
  assert(producer_signals==1 && access(path,F_OK)==0 && access(pending,F_OK)==0);
  if(!strcmp(argv[1],"dns_healthy"))dns_running=1;
  else if(!strcmp(argv[1],"dns_ap"))ap_mode=1;
  else if(!strcmp(argv[1],"dns_inhibited")){
   inhibited=1;handle_notifications();
   assert(events==0 && dns_starts==0 && access(path,F_OK)==0 && access(pending,F_OK)==0);
   inhibited=0;
  }else if(!strcmp(argv[1],"dns_coalesced")){
   notify_rc(RCN_RECOVER_DNSMASQ);assert(producer_signals==2);
  }else if(!strcmp(argv[1],"dns_start_failure"))start_failure=5;
  else assert(!strcmp(argv[1],"dns_missing"));
  handle_notifications();
  assert(events==1 && dns_stops==0 && dns_starts==(!ap_mode && strcmp(argv[1],"dns_healthy")!=0));
  assert(access(path,F_OK)!=0 && access(pending,F_OK)!=0);
  handle_notifications();assert(events==1 && dns_starts<=1);
 }else {assert(0);}return 0;
}
'''
        (root/'driver.c').write_text(code)
        cls.binary=root/'driver'
        p=subprocess.run(['clang','-Wno-unused-value','-fsanitize=address,undefined',str(root/'driver.c'),'-o',str(cls.binary)],capture_output=True,text=True)
        if p.returncode:raise RuntimeError(p.stderr)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_actual_consumer_dispatch(self):
        for scenario in ('batches','unsafe_markers','writable_queue'):
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as directory:
                subprocess.run([str(self.binary),scenario,directory],check=True,capture_output=True,timeout=3)

    def dns_case(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([str(self.binary),scenario,directory],check=True,capture_output=True,timeout=3)

    def test_dns_recovery_starts_missing_daemon_without_stop(self):
        self.dns_case('dns_missing')

    def test_dns_recovery_does_not_restart_daemon_restored_before_dispatch(self):
        self.dns_case('dns_healthy')

    def test_dns_recovery_skips_access_point_mode(self):
        self.dns_case('dns_ap')

    def test_dns_recovery_preserves_markers_while_upgrade_inhibited(self):
        self.dns_case('dns_inhibited')

    def test_dns_recovery_requests_coalesce_to_one_start(self):
        self.dns_case('dns_coalesced')

    def test_dns_start_failure_consumes_one_request_without_stop(self):
        self.dns_case('dns_start_failure')

if __name__=='__main__':unittest.main()
