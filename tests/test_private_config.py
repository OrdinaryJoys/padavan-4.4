#!/usr/bin/env python3
"""Exercise real DDNS file creation and failure paths without any router IO."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_httpd_regressions import function, source


class PrivateConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        text = source('trunk/user/rc/services_ex.c')
        code = r'''
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <assert.h>
#include <errno.h>
#include <string.h>
static int denied, fdopen_fail, last_fd;
static int mock_fchmod(int fd, mode_t mode) {
    if(denied) { errno=EPERM; return -1; }
    return fchmod(fd,mode);
}
static FILE *mock_fdopen(int fd,const char *mode) {
    last_fd=fd;
    if(fdopen_fail) { errno=EMFILE; return NULL; }
    return fdopen(fd,mode);
}
#define fchmod mock_fchmod
#define fdopen mock_fdopen
'''
        code += text[text.index('static FILE *\nopen_private_config('):
                     text.index('static int\nwrite_inadyn_conf(')]
        code += r'''
#undef fchmod
#undef fdopen
static int config_ok, executions;
static int nvram_safe_get_int(const char *k,int a,int b,int c){return 0;}
static int get_ap_mode(void){return 0;}
static int nvram_match(const char*k,const char*v){return 1;}
static void stop_ddns(void){}
static int doSystem(const char*format,...){executions++;return 0;}
static int pids(const char *s){return 1;}
static int is_ntpc_updated(void){return 1;}
static int eval(const char*s,...){executions++;return 0;}
static void logmessage(const char*s,const char*f,...){}
static int write_inadyn_conf(const char *s){return config_ok;}
#define DDNS_CONF_FILE "unused"
#define DDNS_CACHE_DIR "unused"
#define DDNS_DONE_SCRIPT "unused"
#define mkdir(p,m) 0
'''
        code += function(text, 'start_ddns')
        code += function(text, 'notify_ddns_update')
        code += r'''
int main(int argc, char **argv) {
    FILE *f; struct stat st; char buf[16]={0}; assert(argc==3); umask(0);
    if(!strcmp(argv[1],"create")) {
        f=open_private_config(argv[2]); assert(f);
        assert(fstat(fileno(f),&st)==0 && (st.st_mode & 0777)==0600);
        assert(fputs("test",f)>=0 && fclose(f)==0);
    } else if(!strcmp(argv[1],"existing") || !strcmp(argv[1],"chmod_fail")) {
        f=fopen(argv[2],"w");assert(f);fputs("old",f);fclose(f);chmod(argv[2],0666);
        denied=!strcmp(argv[1],"chmod_fail"); f=open_private_config(argv[2]);
        if(denied) {
            assert(f==NULL);f=fopen(argv[2],"r");assert(f);assert(fread(buf,1,3,f)==3);
            assert(!memcmp(buf,"old",3));fclose(f);
        } else {assert(f && fstat(fileno(f),&st)==0 && st.st_size==0 && (st.st_mode & 0777)==0600);fclose(f);}
    } else if(!strcmp(argv[1],"symlink")) {
        char link[1024];snprintf(link,sizeof(link),"%s.link",argv[2]);
        f=fopen(argv[2],"w");assert(f);fputs("old",f);fclose(f);
        assert(symlink(argv[2],link)==0 && open_private_config(link)==NULL);
        assert(stat(argv[2],&st)==0 && st.st_size==3);
    } else if(!strcmp(argv[1],"fdopen_fail")) {
        fdopen_fail=1;assert(open_private_config(argv[2])==NULL);
        assert(fcntl(last_fd,F_GETFD)==-1 && errno==EBADF);
    } else if(!strcmp(argv[1],"failed_start")) {
        config_ok=0;assert(start_ddns(0)==-1 && executions==0);
    } else if(!strcmp(argv[1],"failed_reload")) {
        config_ok=0;assert(notify_ddns_update()==-1 && executions==0);
    } else if(!strcmp(argv[1],"successful_reload")) {
        config_ok=1;assert(notify_ddns_update()==0 && executions==1);
    } else {assert(0);}
    return 0;
}
'''
        root = Path(cls.tmp.name)
        (root/'driver.c').write_text(code)
        cls.binary = root/'driver'
        subprocess.run(['clang', '-g', '-fsanitize=address,undefined', str(root/'driver.c'),
                        '-o', str(cls.binary)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_file_permissions_and_service_failure_paths(self):
        for case in ('create','existing','chmod_fail','symlink','fdopen_fail',
                     'failed_start','failed_reload','successful_reload'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                subprocess.run([str(self.binary), case, str(Path(directory)/'config')], check=True)


if __name__ == '__main__':
    unittest.main()
