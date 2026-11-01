"""Pure actual admission/entry generator; writer/reboot/owner/fs are inert seams.

This is not a whole real firmware writer or a physical reset experiment. The
separate writer protocol fixture runs the actual snapshot/erase/readback body.
"""
import json
import re

SOURCE_PATHS = {
    'admission': 'trunk/user/mtd_write/resident_admission.h',
    'resident': 'trunk/user/mtd_write/resident_upgrade.h',
    'main': 'trunk/user/mtd_write/fw_upgrade.c',
    'writer': 'trunk/user/mtd_write/upgrade_write.h',
    'makefile': 'trunk/user/mtd_write/Makefile',
    'crc': 'trunk/user/mtd_write/crc32.c',
    'crc_header': 'trunk/user/mtd_write/crc32.h',
}
NAMES = (
    'safe-prewrite', 'verified-reset-error', 'verified-reset-zero', 'unknown',
    'bad-argc', 'bad-command', 'bad-target', 'bad-fd-argument', 'nonempty-environment',
    'wrong-parent', 'lease-unlocked', 'lease-shared', 'lease-other-inode',
    'lease-hardlink', 'lease-mode', 'foreign-exclusive', 'marker-absent',
    'marker-symlink', 'marker-nonempty', 'private-mode', 'attempt-symlink',
    'status-other-parent', 'status-other-leaf', 'exe-symlink', 'exe-other-inode',
    'exe-mode', 'lease-not-tmpfs', 'status-not-tmpfs', 'exe-not-tmpfs', 'statfs-error',
    'owner-mismatch', 'marker-hardlink', 'exe-hardlink', 'exe-open-error',
)

def expected(name):
    accepted = name in NAMES[:4]
    writer = 20 if name == 'safe-prewrite' else (0 if name.startswith('verified-') else 21)
    reset = int(name.startswith('verified-'))
    exclusion = int(name not in ('lease-unlocked', 'lease-shared', 'lease-other-inode'))
    return {'case': name, 'trace': [
        'writer-calls:' + str(int(accepted)),
        'writer-result:' + str(writer if accepted else -1),
        'reboot-calls:' + str(reset),
        'exit:' + str(20 if name == 'safe-prewrite' else 21),
        'fd-balance:1', 'canonical-exclusion:' + str(exclusion)]}

CASES = tuple((n, expected(n)) for n in NAMES)


def function(text, marker):
    start = text.index(marker)
    left = text.index('{', start)
    depth = 0
    for i in range(left, len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if not depth: return text[start:i + 1]
    raise ValueError('unterminated actual function')


def actual_functions(texts):
    result = {}
    for name in ('fwup_resident_tmpfs', 'fwup_resident_same', 'fwup_resident_regular',
                 'fwup_resident_directory', 'fwup_resident_split', 'fwup_resident_admission'):
        result[name] = {'source_key': 'admission', 'body': function(texts['admission'], 'static int ' + name + '(')}
    result['fwup_resident_run'] = {'source_key': 'resident', 'body': function(texts['resident'], 'static int fwup_resident_run(')}
    result['main'] = {'source_key': 'main', 'body': function(texts['main'], 'int main(')}
    return result


def generate_source(texts, fixture_root, owner_uid=0):
    if not isinstance(fixture_root, str) or not fixture_root.startswith('/') or '\n' in fixture_root:
        raise ValueError('absolute private fixture root required')
    if type(owner_uid) is not int or owner_uid < 0: raise ValueError('owner uid')
    for key in SOURCE_PATHS:
        if key not in texts: raise ValueError('missing locked source ' + key)
    for name, value in [('FWUP_SAFE', 20), ('FWUP_UNKNOWN', 21)]:
        if not re.search(r'^#define ' + name + r' ' + str(value) + r'$', texts['writer'], re.M):
            raise ValueError('writer result protocol drift')
    funcs = actual_functions(texts)
    main = funcs['main']['body'].replace('int main(', 'int production_main(', 1)
    private = fixture_root + '/private'
    prefix = PRELUDE.replace('@ROOT@', json.dumps(fixture_root)).replace('@PRIVATE@', json.dumps(private)).replace('@UID@', str(owner_uid))
    return (prefix + '\n' + texts['admission'] + '\n' + texts['resident'] +
            '\n#define _exit fixture_exit\n' + main + '\n#undef _exit\n' + DRIVER)

PRELUDE = r'''
#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/file.h>
#ifdef __linux__
#include <sys/vfs.h>
#else
#include <sys/mount.h>
#endif
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#define ROOT @ROOT@
#define PRIVATE @PRIVATE@
#define FWUP_RESIDENT_PRIVATE PRIVATE
#define FWUP_RESIDENT_OWNER ((uid_t)@UID@)
#define FWUP_SAFE 20
#define FWUP_UNKNOWN 21
static const char *label;
static char attempt[PATH_MAX],status_path[PATH_MAX],exe_path[PATH_MAX],lock_path[PATH_MAX];
static int writer_calls,writer_result=-1,reboot_calls,fd_before,foreign_fd=-1;
static int is(const char *s){return !strcmp(label,s);}
static int count_fds(void){int i,n=0;for(i=0;i<256;i++)if(fcntl(i,F_GETFD)>=0)n++;return n;}
static pid_t fixture_ppid(void){return is("wrong-parent")?77:1;}
static int fixture_statfs(int fd,struct statfs *fs){
 struct stat st;memset(fs,0,sizeof(*fs));
 if(is("statfs-error")){errno=EIO;return -1;}
 if(fstat(fd,&st))return -1;
 fs->f_type=0x01021994;
 if((is("lease-not-tmpfs")&&fd==3)||(is("status-not-tmpfs")&&S_ISDIR(st.st_mode))||
    (is("exe-not-tmpfs")&&S_ISREG(st.st_mode)&&st.st_size>0))fs->f_type=0x1234;
 return 0;
}
static int fixture_fstat(int fd,struct stat *st){
 int r=fstat(fd,st);
 if(!r&&is("owner-mismatch")&&S_ISDIR(st->st_mode))st->st_uid=(uid_t)(@UID@+1);
 return r;
}
static int fixture_exe_open(void){if(is("exe-open-error")){errno=EIO;return -1;}return open(exe_path,O_RDONLY|O_CLOEXEC);}
static ssize_t fixture_readlink(const char *p,char *b,size_t n){size_t z=strlen(exe_path);(void)p;if(z>n)z=n;memcpy(b,exe_path,z);return (ssize_t)z;}
static int fixture_writer(const char*a,const char*b,const char*c){
 (void)a;(void)b;(void)c;writer_calls++;
 writer_result=is("safe-prewrite")?20:((is("verified-reset-zero")||is("verified-reset-error"))?0:21);
 return writer_result;
}
static long fixture_reboot(void){reboot_calls++;errno=EPERM;return is("verified-reset-zero")?0:-1;}
static void fixture_exit(int status) __attribute__((noreturn));
#define FWUP_ADMISSION_PPID fixture_ppid
#define FWUP_ADMISSION_STATFS fixture_statfs
#define FWUP_ADMISSION_EXE_OPEN fixture_exe_open
#define FWUP_ADMISSION_READLINK fixture_readlink
#define FWUP_RESIDENT_WRITE fixture_writer
#define FWUP_RESIDENT_REBOOT() fixture_reboot()
#define fstat fixture_fstat
'''

DRIVER = r'''
#undef fstat
static void fixture_exit(int status){
 int probe,excluded,balance;probe=open(lock_path,O_RDWR|O_CLOEXEC);
 if(probe<0)_exit(94);
 excluded=flock(probe,LOCK_SH|LOCK_NB)<0&&(errno==EAGAIN||errno==EWOULDBLOCK);
 close(probe);balance=count_fds()==fd_before;
 printf("{\"case\":\"%s\",\"trace\":[\"writer-calls:%d\",\"writer-result:%d\",\"reboot-calls:%d\",\"exit:%d\",\"fd-balance:%d\",\"canonical-exclusion:%d\"]}\n",
 label,writer_calls,writer_result,reboot_calls,status,balance,excluded);
 fflush(stdout);_exit(0);
}
static int make_file(const char *p,mode_t mode,const char *text){
 int fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,mode);
 if(fd<0)return -1;
 if(*text&&write(fd,text,strlen(text))!=(ssize_t)strlen(text)){close(fd);return -1;}
 if(fchmod(fd,mode)){close(fd);return -1;}return close(fd);
}
int main(int argc,char **argv){
 char marker[PATH_MAX],alternate[PATH_MAX],other[PATH_MAX];int fd,ac=6;
 char *args[]={"writer","--resident-upgrade","public-image","firmware",status_path,"3",NULL};
 char *empty[]={NULL};char *badenv[]={"PUBLIC_FIXTURE=1",NULL};char **environment=empty;
 if(argc!=2)return 90;
 label=argv[1];umask(077);
 if(mkdir(ROOT,0700)&&errno!=EEXIST)return 91;
 if(mkdir(PRIVATE,0700))return 91;
 if(snprintf(attempt,sizeof(attempt),"%s/fwupgrade.ABC123",PRIVATE)>=(int)sizeof(attempt))return 91;
 if(mkdir(attempt,0700))return 91;
 if(snprintf(status_path,sizeof(status_path),"%s/status",attempt)>=(int)sizeof(status_path))return 91;
 if(snprintf(exe_path,sizeof(exe_path),"%s/writer",attempt)>=(int)sizeof(exe_path))return 91;
 if(snprintf(lock_path,sizeof(lock_path),"%s/firmware-action.lock",PRIVATE)>=(int)sizeof(lock_path))return 91;
 if(snprintf(marker,sizeof(marker),"%s/firmware-upgrade-inhibit",PRIVATE)>=(int)sizeof(marker))return 91;
 if(snprintf(alternate,sizeof(alternate),"%s/alternate",PRIVATE)>=(int)sizeof(alternate))return 91;
 if(snprintf(other,sizeof(other),"%s/other",PRIVATE)>=(int)sizeof(other))return 91;
 if(make_file(marker,0600,"")||make_file(exe_path,0700,"public-code")||make_file(lock_path,0600,""))return 91;
 close(3);fd=open(lock_path,O_RDWR|O_CLOEXEC);if(fd<0)return 91;
 if(fd!=3){if(dup2(fd,3)<0)return 91;close(fd);}if(flock(3,LOCK_EX|LOCK_NB))return 91;
 if(is("bad-argc"))ac=5;
 if(is("bad-command"))args[1]="--upgrade-write";
 if(is("bad-target"))args[3]="Storage";
 if(is("bad-fd-argument"))args[5]="03";
 if(is("nonempty-environment"))environment=badenv;
 if(is("lease-unlocked")&&flock(3,LOCK_UN))return 91;
 if(is("lease-shared")&&flock(3,LOCK_SH|LOCK_NB))return 91;
 if(is("lease-other-inode")){
  close(3);if(make_file(other,0600,""))return 91;fd=open(other,O_RDWR);if(fd!=3){if(fd<0||dup2(fd,3)<0)return 91;close(fd);}
 }
 if(is("foreign-exclusive")){
  if(flock(3,LOCK_UN))return 91;
  foreign_fd=open(lock_path,O_RDWR|O_CLOEXEC);
  if(foreign_fd<0||flock(foreign_fd,LOCK_EX|LOCK_NB))return 91;
 }
 if(is("lease-hardlink")&&link(lock_path,alternate))return 91;
 if(is("lease-mode")&&chmod(lock_path,0644))return 91;
 if(is("marker-absent")&&unlink(marker))return 91;
 if(is("marker-symlink")){if(unlink(marker)||symlink(lock_path,marker))return 91;}
 if(is("marker-hardlink")&&link(marker,alternate))return 91;
 if(is("marker-nonempty")){fd=open(marker,O_WRONLY);if(fd<0||write(fd,"X",1)!=1||close(fd))return 91;}
 if(is("private-mode")&&chmod(PRIVATE,0755))return 91;
 if(is("attempt-symlink")){if(rename(attempt,alternate)||symlink(alternate,attempt))return 91;}
 if(is("status-other-parent"))args[4]="/tmp/status";
 if(is("status-other-leaf")){args[4]=other;}
 if(is("exe-symlink")){if(rename(exe_path,alternate)||symlink(alternate,exe_path))return 91;}
 if(is("exe-other-inode")){
  if(rename(exe_path,alternate)||make_file(exe_path,0700,"public-other-code"))return 91;
  strcpy(exe_path,alternate);
 }
 if(is("exe-mode")&&chmod(exe_path,0755))return 91;
 if(is("exe-hardlink")&&link(exe_path,alternate))return 91;
 fd_before=count_fds();
 production_main(ac,args,environment);
 return 97;
}
'''
