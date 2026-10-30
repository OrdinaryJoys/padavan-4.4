#!/usr/bin/env python3
"""Actual shared notification code with only PID 1 signalling replaced."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        source = ROOT / 'trunk/user/shared/notify_rc.c'
        driver = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <assert.h>
#include <string.h>
#include <stdlib.h>
static char queue_path[1024], pending_path[1024];
static int signals, fail_signal, wrong_owner;
static int test_kill(pid_t pid, int sig) {
    assert(pid==1 && sig==SIGUSR1); signals++;
    if(fail_signal) { errno=EPERM; return -1; } return 0;
}
static int test_fstatat(int fd,const char *name,struct stat *st,int flags) {
    int ret=fstatat(fd,name,st,flags);
    if(ret==0 && wrong_owner) st->st_uid=geteuid()+1;
    return ret;
}
#define NOTIFY_RC_H
#define DIR_RC_NOTIFY queue_path
#define DIR_RC_INCOMPLETE pending_path
#define kill test_kill
#define fstatat test_fstatat
'''
        driver += '#include "' + str(source) + '"\n'
        driver += r'''
#undef fstatat
#undef kill
int main(int argc,char **argv) {
    char marker[1200],pending[1200],victim[1200],alias[1200],data[8]={0};
    FILE *file;int fd;struct stat st;
    assert(argc==3);umask(0);
    snprintf(queue_path,sizeof(queue_path),"%s/queue",argv[2]);
    snprintf(pending_path,sizeof(pending_path),"%s/pending",argv[2]);
    snprintf(marker,sizeof(marker),"%s/restart_time",queue_path);
    snprintf(pending,sizeof(pending),"%s/restart_time",pending_path);
    snprintf(victim,sizeof(victim),"%s/victim",argv[2]);
    assert(mkdir(queue_path,0700)==0 && mkdir(pending_path,0700)==0);
    file=fopen(victim,"w");assert(file);fputs("keep",file);fclose(file);
    if(!strcmp(argv[1],"valid")) {
        notify_rc("restart_time");assert(signals==1);
        assert(stat(marker,&st)==0 && (st.st_mode&0777)==0600);
        fd=rc_notification_open_dir(queue_path);assert(fd>=0);
        assert(rc_notification_valid_marker(fd,"restart_time"));close(fd);
    } else if(!strcmp(argv[1],"coalesce")) {
        notify_rc("restart_time");
        file=fopen(marker,"w");assert(file);fputs("keep",file);fclose(file);
        notify_rc("restart_time");assert(signals==2);
        file=fopen(marker,"r");assert(file);assert(fread(data,1,4,file)==4);fclose(file);assert(!memcmp(data,"keep",4));
    } else if(!strcmp(argv[1],"symlink") || !strcmp(argv[1],"hardlink") ||
              !strcmp(argv[1],"directory") || !strcmp(argv[1],"fifo") || !strcmp(argv[1],"wrong_owner")) {
        if(!strcmp(argv[1],"symlink"))assert(symlink(victim,marker)==0);
        if(!strcmp(argv[1],"hardlink"))assert(link(victim,marker)==0);
        if(!strcmp(argv[1],"directory"))assert(mkdir(marker,0700)==0);
        if(!strcmp(argv[1],"fifo"))assert(mkfifo(marker,0600)==0);
        if(!strcmp(argv[1],"wrong_owner")) {fd=open(marker,O_CREAT|O_WRONLY,0600);assert(fd>=0);close(fd);wrong_owner=1;}
        fd=rc_notification_open_dir(queue_path);assert(fd>=0);
        assert(!rc_notification_valid_marker(fd,"restart_time"));close(fd);
        notify_rc("restart_time");assert(signals==0 && access(pending,F_OK)!=0);
        file=fopen(victim,"r");assert(file);assert(fread(data,1,4,file)==4);fclose(file);assert(!memcmp(data,"keep",4));
    } else if(!strcmp(argv[1],"world_writable") || !strcmp(argv[1],"group_writable")) {
        chmod(queue_path,!strcmp(argv[1],"world_writable")?0777:0770);
        assert(rc_notification_open_dir(queue_path)<0);
        notify_rc("restart_time");assert(signals==0 && access(pending,F_OK)!=0);
    } else if(!strcmp(argv[1],"directory_symlink")) {
        snprintf(alias,sizeof(alias),"%s/alias",argv[2]);assert(symlink(queue_path,alias)==0);
        assert(rc_notification_open_dir(alias)<0);
    } else if(!strcmp(argv[1],"invalid_name")) {
        const char *names[]={"", "../victim", "a/b", "bad;reboot", "bad\nname",NULL};int i;
        for(i=0;names[i];i++)notify_rc(names[i]);notify_rc(NULL);assert(signals==0);
    } else if(!strcmp(argv[1],"kill_failure")) {
        fail_signal=1;notify_rc("restart_time");
        assert(signals==1 && access(marker,F_OK)!=0 && access(pending,F_OK)!=0);
    } else if(!strcmp(argv[1],"retain_coalesced_on_kill_failure")) {
        notify_rc("restart_time");fail_signal=1;notify_rc("restart_time");
        assert(signals==2 && access(marker,F_OK)==0 && access(pending,F_OK)==0);
    } else {assert(0);}
    return 0;
}
'''
        (root/'driver.c').write_text(driver)
        cls.binary = root/'driver'
        subprocess.run(['clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                        str(root/'driver.c'),'-o',str(cls.binary)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_markers_and_private_directories(self):
        for case in ('valid','coalesce','symlink','hardlink','directory','fifo','wrong_owner',
                     'world_writable','group_writable','directory_symlink','invalid_name',
                     'kill_failure','retain_coalesced_on_kill_failure'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                subprocess.run([str(self.binary),case,directory],check=True,capture_output=True,timeout=3)


if __name__=='__main__':
    unittest.main()
