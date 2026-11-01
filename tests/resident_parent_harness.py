"""Pure actual PID1 worker-spawn adapter; exec is an inert child recorder."""
import json
import re

SOURCE_PATHS = {'rc': 'trunk/user/rc/rc.c'}
FUNCTIONS = {'rc': ('firmware_upgrade_spawn', 'firmware_upgrade_run')}


def extract(text, name):
    match = re.search(r'static\s+int\s+' + name + r'\s*\([^;{}]*\)\s*\{', text)
    if not match:
        raise ValueError(name)
    start, depth = text.index('{',match.start()), 0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*|[{}]',text[start:]):
        if token.group()=='{':depth+=1
        elif token.group()=='}':
            depth-=1
            if not depth:return text[match.start():start+token.end()]
    raise ValueError(name)


def generate_source(texts, fixture_root, owner_uid=0):
    if set(texts)!=set(SOURCE_PATHS) or type(fixture_root) is not str or not fixture_root.startswith('/') or any(ord(c)<32 or ord(c)>126 for c in fixture_root):
        raise ValueError('Exact sources and absolute ASCII fixture required')
    if type(owner_uid) is not int or not 0<=owner_uid<2**32:
        raise ValueError('Invalid fixture owner')
    code = PREFIX + '\n#define FIXTURE_ROOT ' + json.dumps(fixture_root) + '\n'
    code += '#define FIXTURE_OWNER ' + str(owner_uid) + '\n'
    code += BODY
    code += '\n'.join(extract(texts['rc'],name) for name in FUNCTIONS['rc'])
    code += MAIN
    return code


PREFIX = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#define FW_IMG_NAME "/fixture/image"
#define FW_MTD_NAME "firmware"
'''

BODY = r'''
static const char *mode;
static pid_t controller;
static int high_fd, wait_interrupted;
static char marker_path[PATH_MAX],lock_path[PATH_MAX];
static int fault(const char *name){return !strcmp(mode,name);}
static int is_child(void){return getpid()!=controller;}
static pid_t fixture_fork(void){if(fault("fork-failure")){errno=EAGAIN;return -1;}return fork();}
static int fixture_dup2(int a,int b){if(fault("dup-failure")){errno=EBADF;return -1;}return dup2(a,b);}
static int fixture_fcntl(int fd,int command,...){
 va_list ap;int arg=0;if(command==F_SETFD){va_start(ap,command);arg=va_arg(ap,int);va_end(ap);}
 if(is_child()&&command==F_SETFD&&fault("cloexec-failure")){errno=EIO;return -1;}
 return command==F_SETFD?fcntl(fd,command,arg):fcntl(fd,command);
}
static int fixture_close(int fd){int result=close(fd);if(is_child()&&fd==high_fd&&fault("close-failure")){errno=EIO;return -1;}return result;}
static int fixture_sigprocmask(int how,const sigset_t *set,sigset_t *old){
 if(set&&((is_child()&&how==SIG_SETMASK&&fault("child-mask-failure"))||
   (!is_child()&&how==SIG_BLOCK&&fault("parent-mask-failure"))||
   (!is_child()&&how==SIG_SETMASK&&fault("parent-restore-failure")))){errno=EIO;return -1;}
 return sigprocmask(how,set,old);
}
static pid_t fixture_setsid(void){if(fault("setsid-failure")){errno=EPERM;return -1;}return setsid();}
static DIR *fixture_opendir(const char *path){
 assert(!strcmp(path,"/proc/self/fd"));if(fault("opendir-failure")){errno=EIO;return NULL;}
#ifdef __APPLE__
 /* Portable native fixture only. Linux/MIPS exercises the actual proc path. */
 return opendir("/dev/fd");
#else
 return opendir(path);
#endif
}
static struct dirent *fixture_readdir(DIR *d){if(fault("readdir-failure")){errno=EIO;return NULL;}return readdir(d);}
static int fixture_closedir(DIR *d){int result=closedir(d);if(fault("closedir-failure")){errno=EIO;return -1;}return result;}
static pid_t fixture_waitpid(pid_t pid,int *status,int flags){
 if(fault("wait-eintr")&&!wait_interrupted++){errno=EINTR;return -1;}return waitpid(pid,status,flags);
}
static int fixture_execve(const char *writer,char *const args[],char *const environment[]){
 int observations[8],fd,locked,i,length;struct stat lease,canonical;sigset_t mask;char output[256];
 observations[0]=!strcmp(writer,"/fixture/trusted-worker")&&args[0]&&!strcmp(args[0],writer)&&
  args[1]&&!strcmp(args[1],"--resident-upgrade")&&args[2]&&!strcmp(args[2],FW_IMG_NAME)&&
  args[3]&&!strcmp(args[3],FW_MTD_NAME)&&args[4]&&!strcmp(args[4],marker_path)&&
  args[5]&&!strcmp(args[5],"3")&&!args[6];
 observations[1]=environment&&!environment[0];
 observations[2]=fstat(3,&lease)==0&&stat(lock_path,&canonical)==0&&lease.st_dev==canonical.st_dev&&
  lease.st_ino==canonical.st_ino&&lease.st_uid==FIXTURE_OWNER;
 observations[3]=fcntl(3,F_GETFD)==0;
 observations[4]=1;for(i=0;i<3;i++)if(fcntl(i,F_GETFD)>=0||errno!=EBADF)observations[4]=0;
 observations[5]=fcntl(high_fd,F_GETFD)<0&&errno==EBADF;
 sigprocmask(SIG_SETMASK,NULL,&mask);
 observations[6]=sigismember(&mask,SIGTERM)&&sigismember(&mask,SIGQUIT)&&sigismember(&mask,SIGCHLD)&&
  sigismember(&mask,SIGHUP)&&sigismember(&mask,SIGALRM)&&sigismember(&mask,SIGINT);
 fd=open(lock_path,O_RDWR);assert(fd>=0);locked=flock(fd,LOCK_SH|LOCK_NB);observations[7]=locked<0&&(errno==EWOULDBLOCK||errno==EAGAIN);close(fd);
 fd=open(marker_path,O_WRONLY|O_CREAT|O_EXCL,0600);assert(fd>=0);
 length=snprintf(output,sizeof(output),"%d,%d,%d,%d,%d,%d,%d,%d",observations[0],observations[1],observations[2],observations[3],observations[4],observations[5],observations[6],observations[7]);
 assert(write(fd,output,length)==length);assert(close(fd)==0);
 if(fault("exec-failure")){errno=ENOENT;return -1;}
 _exit(fault("child-safe20")?20:fault("unexpected-zero")?0:21);
}
#define fork fixture_fork
#define dup2 fixture_dup2
#define fcntl fixture_fcntl
#define close fixture_close
#define sigprocmask fixture_sigprocmask
#define setsid fixture_setsid
#define opendir fixture_opendir
#define readdir fixture_readdir
#define closedir fixture_closedir
#define waitpid fixture_waitpid
#define execve fixture_execve
'''

MAIN = r'''
#undef fork
#undef dup2
#undef fcntl
#undef close
#undef sigprocmask
#undef setsid
#undef opendir
#undef readdir
#undef closedir
#undef waitpid
#undef execve
int main(int argc,char **argv){
 int lease,fd,status,seen=0,restored,i;pid_t child;sigset_t original,before,after;char body[256]={0};ssize_t count;
 assert(argc==2);mode=argv[1];controller=getpid();assert(mkdir(FIXTURE_ROOT,0700)==0||errno==EEXIST);
 assert(snprintf(lock_path,sizeof(lock_path),"%s/action.lock",FIXTURE_ROOT)<(int)sizeof(lock_path));
 assert(snprintf(marker_path,sizeof(marker_path),"%s/child-record",FIXTURE_ROOT)<(int)sizeof(marker_path));
 lease=open(lock_path,O_RDWR|O_CREAT|O_EXCL,0600);assert(lease>=0);
 if(fault("fd3")){if(lease!=3){assert(dup2(lease,3)==3);close(lease);lease=3;}}
 else{fd=fcntl(lease,F_DUPFD,10);assert(fd>=10);close(lease);lease=fd;}
 assert(fcntl(lease,F_SETFD,FD_CLOEXEC)==0&&flock(lease,LOCK_EX|LOCK_NB)==0);
 high_fd=fcntl(lease,F_DUPFD,300);assert(high_fd>=300);
 sigemptyset(&before);sigaddset(&before,SIGUSR2);assert(sigprocmask(SIG_SETMASK,&before,&original)==0);
 status=firmware_upgrade_run("/fixture/trusted-worker",marker_path,fault("invalid-lease")?-1:lease,&child);
 assert(sigprocmask(SIG_SETMASK,NULL,&after)==0);restored=1;
 for(i=1;i<NSIG;i++)if(sigismember(&before,i)!=sigismember(&after,i))restored=0;
 assert(sigprocmask(SIG_SETMASK,&original,NULL)==0);
 fd=open(marker_path,O_RDONLY);if(fd>=0){count=read(fd,body,sizeof(body)-1);assert(count>0);body[count]=0;close(fd);seen=1;}
 printf("{\"case\":\"%s\",\"status\":%d,\"child_created\":%d,\"parent_mask_restored\":%d,\"exec_record\":%d,\"observations\":[%s]}\n",mode,status,child>1,restored,seen,body);
 close(high_fd);close(lease);return 0;
}
'''


def expected(name, status=5376, child=1, restored=1, executed=1):
    return name, {'case':name,'status':status,'child_created':child,
                  'parent_mask_restored':restored,'exec_record':executed,
                  'observations':[1]*8 if executed else []}


CASES = (
    expected('fd3'), expected('fd-high'), expected('child-safe20',status=5120),
    expected('unexpected-zero',status=0), expected('exec-failure'), expected('wait-eintr'),
    expected('fork-failure',status=-1,child=0,executed=0),
    expected('invalid-lease',status=-1,child=0,executed=0),
    expected('parent-mask-failure',status=-1,child=0,executed=0),
    expected('parent-restore-failure',status=-1,restored=0),
    *(expected(name,executed=0) for name in ('child-mask-failure','dup-failure',
       'cloexec-failure','setsid-failure','opendir-failure','readdir-failure',
       'closedir-failure','close-failure')),
)
