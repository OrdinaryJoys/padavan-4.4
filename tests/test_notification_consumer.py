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
static int events,signals;
static int nvram_nf_nat_type;
static int fake_signal(pid_t p,int s){assert(p==getpid() && s==SIGUSR1);signals++;return 0;}
static int fake_printf(const char *f,...){if(!strcmp(f,"rc notification: %s\n"))events++;return 0;}
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
        code+='#define printf fake_printf\n'+consumer+'\n#undef printf\n'
        code+=r'''
int main(int argc,char **argv){
 char path[1200],victim[1200];int i,fd;FILE*f;
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

if __name__=='__main__':unittest.main()
