"""Real log_locally and write helpers, native private paths/faults, never target execution."""
from pathlib import Path
import json,re
from bounded_log_harness import function
SOURCE_PATHS={'log':'trunk/user/busybox/busybox-1.24.x/sysklogd/syslogd.c','header':'trunk/user/busybox/busybox-1.24.x/sysklogd/default_logfile.h','safe_write':'trunk/user/busybox/busybox-1.24.x/libbb/safe_write.c','full_write':'trunk/user/busybox/busybox-1.24.x/libbb/full_write.c','old':'tests/fixtures/syslogd-before-default-guard.c'}
def read_inputs(root):return {k:(root/v).read_text()for k,v in SOURCE_PATHS.items()}
PREFIX=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdint.h>
#include <dirent.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#define FAST_FUNC
#define ENABLE_FEATURE_ROTATE_LOGFILE 1
#define LONE_DASH(p) (!strcmp((p),"-"))
static const char*fault,*alias_target,*protected_path;
static int open_calls,close_calls,chmod_calls,stat_calls,lstat_calls,console_calls,stderr_writes,write_calls,last_flags;
static int match(const char*s){return fault&&!strcmp(fault,s);}
static int fixture_open(const char*p,int flags,...){mode_t m=0;va_list a;open_calls++;last_flags=flags;if(match("eexist_storm")){errno=EEXIST;return -1;}if(match("open_fail")){errno=EACCES;return -1;}if(flags&O_CREAT){va_start(a,flags);m=(mode_t)va_arg(a,int);va_end(a);}return open(p,flags,m);}
static int fixture_close(int fd){close_calls++;return close(fd);}
static int fixture_fstat(int fd,struct stat*s){stat_calls++;if(match("fstat_fail")||(match("late_fstat_fail")&&stat_calls==3)){memset(s,0,sizeof(*s));s->st_size=0x11111111;errno=EIO;return -1;}return fstat(fd,s);}
static int fixture_lstat(const char*p,struct stat*s){int r;lstat_calls++;r=lstat(p,s);if(r<0&&errno==ENOENT&&lstat_calls==1&&(match("symlink_race")||match("hardlink_race"))){if(match("symlink_race")){if(symlink(alias_target,p))exit(91);}else if(link(alias_target,p))exit(92);errno=ENOENT;}return r;}
static uid_t fixture_euid(void){return geteuid()+(match("foreign_owner")?1:0);}
static int fixture_chmod(int fd,mode_t m){chmod_calls++;if(match("chmod_fail")){errno=EACCES;return -1;}return fchmod(fd,m);}
static int fixture_fcntl(int fd,int op,...){int value;va_list a;if(match("fcntl_fail")){errno=EIO;return -1;}if(op==F_GETFL){value=fcntl(fd,op);return match("missing_nonblock")?value&~O_NONBLOCK:value;}if(op==F_GETFD){value=fcntl(fd,op);return match("missing_cloexec")?value&~FD_CLOEXEC:value;}va_start(a,op);value=va_arg(a,int);va_end(a);if(op==F_DUPFD_CLOEXEC&&match("dup_fail")){errno=EMFILE;return -1;}return fcntl(fd,op,value);}
static ssize_t fixture_write(int fd,const void*p,size_t n){write_calls++;if(fd==2)stderr_writes++;return write(fd,p,n);}
static int fixture_unlink(const char*p){int r=unlink(p);if(!r&&match("rotation_symlink")&&!strcmp(p,protected_path)){if(symlink(alias_target,p))exit(96);}return r;}
static int device_open(const char*p,int flags){(void)p;(void)flags;console_calls++;return -1;}
#define DEV_CONSOLE "/no-real-console"
typedef struct{const char*path;int fd;time_t last_log_time;unsigned size;uint8_t isRegular;}logFile_t;
static struct{unsigned logFileSize,logFileRotate;}G={65536,0};
#define unlink fixture_unlink
#define open fixture_open
#define close fixture_close
#define fstat fixture_fstat
#define lstat fixture_lstat
#define fchmod fixture_chmod
#define fcntl fixture_fcntl
#define geteuid fixture_euid
#define write fixture_write
'''
DRIVER=r'''
#undef unlink
#undef open
#undef close
#undef fstat
#undef lstat
#undef fchmod
#undef fcntl
#undef geteuid
#undef write
static int count_fds(void){DIR*d=opendir("/dev/fd");struct dirent*e;int n=0;if(!d)return-1;while((e=readdir(d)))if(strcmp(e->d_name,".")&&strcmp(e->d_name,".."))n++;if(closedir(d))return-1;return n;}
int main(int argc,char**argv){logFile_t file;int before,after,last_fd,nonblock=0,cloexec=0,saved_stdout=-1,first_fd;
 if(argc!=5)return 90;fault=argv[2];alias_target=argv[3];protected_path=SYSLOGD_DEFAULT_PATH;
 if(!strcmp(argv[4],"close-stdin"))close(0);
 if(!strcmp(argv[4],"close-stdout")){saved_stdout=dup(1);close(1);}
 before=count_fds();memset(&file,0,sizeof(file));file.path=argv[1];file.fd=-1;umask(0);
 if(!strcmp(argv[4],"rotation"))G.logFileSize=1;
 log_locally(time(NULL),"PUBLIC_APPEND\n",&file);first_fd=file.fd;
 if(!strcmp(argv[4],"recover")){if(file.fd>1)close(file.fd);file.fd=-1;if(unlink(protected_path)&&errno!=ENOENT)return 93;{int fd=open(protected_path,O_WRONLY|O_CREAT|O_EXCL,0644);if(fd<0)return94;close(fd);}fault="";log_locally(time(NULL)+1,"RECOVERED\n",&file);}
 if(!strcmp(argv[4],"retry")){fault="";log_locally(time(NULL)+1,"RECOVERED\n",&file);}
 if(!strcmp(argv[4],"reopen"))log_locally(time(NULL)+1,"REOPENED\n",&file);
 if(!strcmp(argv[4],"reopen-alias")){if(unlink(protected_path)||symlink(alias_target,protected_path))return 97;log_locally(time(NULL)+1,"REOPENED\n",&file);}
 last_fd=file.fd;if(file.fd>1){nonblock=!!(fcntl(file.fd,F_GETFL)&O_NONBLOCK);cloexec=!!(fcntl(file.fd,F_GETFD)&FD_CLOEXEC);close(file.fd);}
 if(saved_stdout>=0){if(dup2(saved_stdout,1)<0)return95;close(saved_stdout);}
 after=count_fds();printf("{\"first_fd\":%d,\"last_fd\":%d,\"fd_before\":%d,\"fd_after\":%d,\"open_calls\":%d,\"close_calls\":%d,\"chmod_calls\":%d,\"console_calls\":%d,\"stderr_writes\":%d,\"write_calls\":%d,\"last_flags\":%d,\"nonblock\":%d,\"cloexec\":%d,\"regular\":%u,\"size\":%u}\n",first_fd,last_fd,before,after,open_calls,close_calls,chmod_calls,console_calls,stderr_writes,write_calls,last_flags,nonblock,cloexec,(unsigned)file.isRegular,file.size);return0;}
'''.replace('return94','return 94').replace('return95','return 95').replace('return0','return 0')

def generate_source(inputs,path,legacy=False):
 header='#define SYSLOGD_DEFAULT_PATH '+json.dumps(path)+'\n'+inputs['header']+'\n'
 writes='\n'.join(re.sub(r'^#include[^\n]*\n','',inputs[name],flags=re.M)for name in ('safe_write','full_write'))
 return PREFIX+header+writes+function(inputs['old']if legacy else inputs['log'],'log_locally')+DRIVER
