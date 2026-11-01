"""Actual rc upgrade C helpers, synthetic files and inert process/device effects."""
import json
from pathlib import Path
import subprocess
from test_httpd_regressions import function, source

FUNCTIONS = (
    'write_storage_to_mtd', 'firmware_upgrade_signal_inhibited', 'firmware_upgrade_signal_fault',
    'firmware_upgrade_inhibited', 'firmware_upgrade_inhibit',
    'firmware_upgrade_stage_writer', 'firmware_upgrade_number', 'firmware_upgrade_result',
    'firmware_upgrade_run', 'firmware_upgrade_start_networkmap', 'firmware_upgrade_start_detect',
    'firmware_upgrade_stop_watchdog', 'firmware_upgrade_disable_watchdog',
    'firmware_upgrade_services', 'flash_firmware')


def generate(root):
    text = source('trunk/user/rc/rc.c')
    structure = text.split('struct firmware_upgrade_service {', 1)[1].split('};', 1)[0]
    code = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/ioctl.h>
#include <sys/reboot.h>
#include <sys/mman.h>
#define SCRIPT_SHUTDOWN "/etc/storage/shutdown_script.sh"
#define FW_IMG_NAME "/tmp/linux.trx"
#define FW_MTD_NAME "firmware"
#define FW_UPGRADE_INHIBIT "firmware-upgrade-inhibit"
#define FW_UPGRADE_MAX_BYTES 15925248UL
#define HOOK_RUNNER_TIMEOUT_MS 30000U
#define HOOK_RUNNER_TERM_MS 2000U
#define HOOK_RUNNER_KILL_MS 1000U
'''
    code += '#define FW_UPGRADE_PRIVATE ' + json.dumps(str(root / 'private')) + '\n'
    code += '#define FW_UPGRADE_WRITER ' + json.dumps(str(root / 'rom-writer')) + '\n'
    code += '#define FIXTURE_HW ' + json.dumps(str(root / 'hardware-fixture')) + '\n'
    code += '#define WD_PID_FILE ' + json.dumps(str(root / 'watchdog.pid')) + '\n'
    code += r'''
static const char *names[]={"watchdog","rstats","detect_internet","networkmap","lld2d","infosvr","crond"};
static int running[7],stops[7],starts[7],first_status,second_status,hook_exists,hook_status,kind;
static int saves,hooks,time_calls,writer_calls,logs,criticals,reboots,syncs,revision,versions[2];
static int stop_fail=-1,start_fail=-1,hw_mode,hw_opens,hw_disables,hw_closes,hw_pings,hw_fd=-1;
static int copy_fd=-1,source_fd=-1,copy_writes,stage_fault,guard_execs;
static int daemon_marker,daemon_calls,hardware_inits;
static int pin_failure,mlocks,munlocks;
static char trace[8192],last_log[512];
static void event(const char*s){assert(strlen(trace)+strlen(s)+2<sizeof(trace));strcat(trace,s);strcat(trace,",");}
static void action(const char*type,int index){char b[80];snprintf(b,sizeof(b),"%s:%s",type,names[index]);event(b);}
static int index_of(const char*s){int i;for(i=0;i<7;i++)if(!strcmp(s,names[i]))return i;assert(0);return -1;}
static int pids(const char*s){return running[index_of(s)];}
static void stop(int i){stops[i]++;action("stop",i);if(i!=stop_fail)running[i]=0;}
static int start(int i){starts[i]++;action("start",i);if(i!=start_fail)running[i]=1;return 0;}
static void stop_rstats(void){stop(1);} static int start_rstats(void){return start(1);}
static void stop_detect_internet(void){stop(2);} static int start_detect_internet(int t){assert(t==0);return start(2);}
static void stop_networkmap(void){stop(3);} static int start_networkmap(int t){assert(t==0);return start(3);}
static void stop_lltd(void){stop(4);} static int start_lltd(void){return start(4);}
static void stop_infosvr(void){stop(5);} static int start_infosvr(void){return start(5);}
static void stop_crond(void){stop(6);} static int start_crond(void){return start(6);}
static void kill_services(char **s,int t,int force){assert(!strcmp(s[0],"watchdog")&&!s[1]&&t==3&&force==1);stop(0);}
static int mock_eval(const char*p,...){assert(!strcmp(p,"/sbin/watchdog"));guard_execs++;return start(0);}
#define eval mock_eval
static int firmware_upgrade_inhibited(void);
static int start_watchdog(void);
static void notify_watchdog_time(void);
static void kill_pidfile_s(const char*p,int sig){assert(sig==SIGHUP);guard_execs++;}
#define OOM_SCORE_ADJ_MIN -1000
#define WD_NORMAL_PERIOD 10
static void catch_sig_watchdog(int sig){}
static void oom_score_adjust(pid_t pid,int value){}
static int nvram_set_int_temp(const char*key,int value){return 0;}
static void hw_watchdog_init(void){hardware_inits++;}
static void wd_alarmtimer(int first,int second){}
static int fixture_daemon(int chdir_flag,int close_flag){int fd;daemon_calls++;if(daemon_marker){fd=open(FW_UPGRADE_PRIVATE "/" FW_UPGRADE_INHIBIT,O_WRONLY|O_CREAT|O_EXCL,0600);assert(fd>=0);close(fd);}return 0;}
static int fixture_sigaction(int sig,const struct sigaction*a,struct sigaction*b){return 0;}
static int fixture_pause(void){assert(0);return 0;}
static int doSystem(const char *fmt,...){
 char command[512];va_list ap;va_start(ap,fmt);vsnprintf(command,sizeof(command),fmt,ap);va_end(ap);
 if(!strcmp(command,"/sbin/mtd_storage.sh save")){assert(saves<2);versions[saves]=revision;saves++;event("save");return saves==1?first_status:second_status;}
 assert(!"Shutdown hooks must use the bounded runner, not doSystem");return -1;
}
/* Integration control for hook outcomes. The actual process/deadline runner
 * is compiled and exercised independently by test_hook_runner.py. */
static int shutdown_hook_run(const char*path,int level,unsigned int timeout,unsigned int term,unsigned int hard){
 assert(level==0&&timeout==30000U&&term==2000U&&hard==1000U);
 assert(!strcmp(path,SCRIPT_SHUTDOWN));hooks++;revision++;event("hook");errno=hook_status<0?ETIMEDOUT:0;return hook_status;
}
static void storage_save_time(int t){assert(t==60);time_calls++;event("time");}
static int check_if_file_exist(const char*p){assert(!strcmp(p,SCRIPT_SHUTDOWN));return hook_exists;}
static void logmessage(const char*tag,const char*fmt,...){va_list ap;assert(!strcmp(tag,"firmware"));logs++;if(strstr(fmt,"CRITICAL"))criticals++;va_start(ap,fmt);vsnprintf(last_log,sizeof(last_log),fmt,ap);va_end(ap);event("log");}
/* Owner mapping is only a portable host-fixture aid: every fixture file still
 * belongs to the test user. Target/real device ownership is not claimed here. */
static int fixture_fstat(int fd,struct stat*s){int r;if(stage_fault==4&&fd==source_fd){errno=EIO;return -1;}r=fstat(fd,s);if(!r){if(s->st_uid==geteuid())s->st_uid=0;if(fd==hw_fd){s->st_mode=(s->st_mode&07777)|S_IFCHR;if(hw_mode==2)s->st_uid=99;if(hw_mode==3)s->st_mode=(s->st_mode&07777)|S_IFREG;}}return r;}
static int fixture_fstatat(int fd,const char*p,struct stat*s,int flags){int r=fstatat(fd,p,s,flags);if(!r&&s->st_uid==geteuid())s->st_uid=0;return r;}
static int fixture_open(const char*p,int flags,...){
 int fd;mode_t mode=0;va_list ap;if(flags&O_CREAT){va_start(ap,flags);mode=va_arg(ap,int);va_end(ap);}
 if(!strcmp(p,"/dev/watchdog")){hw_opens++;event("hardware-open");if(hw_mode==1){errno=EBUSY;return -1;}fd=open(FIXTURE_HW,O_RDWR);hw_fd=fd;return fd;}
 fd=open(p,flags,mode);if(fd>=0&&!strcmp(p,FW_UPGRADE_WRITER))source_fd=fd;if(fd>=0&&strstr(p,"/writer")&&(flags&O_CREAT))copy_fd=fd;return fd;
}
static ssize_t fixture_write(int fd,const void*b,size_t n){if(fd==copy_fd&&(stage_fault==1||stage_fault==5)){if(stage_fault==5||copy_writes++==0)return write(fd,b,n>1?n/2:1);errno=ENOSPC;return -1;}return write(fd,b,n);}
static int fixture_close(int fd){int r=close(fd),fail=0;if(fd==hw_fd){hw_closes++;hw_fd=-1;if(hw_mode==5)fail=1;}if(fd==source_fd){source_fd=-1;if(stage_fault==2)fail=1;}if(fd==copy_fd){copy_fd=-1;if(stage_fault==3)fail=1;}if(fail){errno=EIO;return -1;}return r;}
static int fixture_ioctl(int fd,unsigned long request,...){assert(fd==hw_fd);if(request==_IOR('W',4,int)){hw_disables++;event("hardware-disable");if(hw_mode==4){errno=EOPNOTSUPP;return -1;}return 0;}assert(request==_IOR('W',5,int));hw_pings++;return 0;}
static int fake_reboot(int cmd){assert(cmd==RB_AUTOBOOT);reboots++;event("reboot");errno=EIO;return -1;}
static void fake_sync(void){syncs++;event("sync");}
static int fake_usleep(useconds_t t){assert(t==100000);return 0;}
static int fixture_mlockall(int flags){assert(flags==(MCL_CURRENT|MCL_FUTURE));mlocks++;event("pin");if(pin_failure){errno=ENOMEM;return -1;}return 0;}
static int fixture_munlockall(void){munlocks++;event("unpin");return 0;}
/* The child creates synthetic protocol records only; it never execs a tool,
 * opens MTD, runs hooks, mounts a filesystem, or changes services. */
static int _eval(char*const argv[],char*redirect,int timeout,int*child){
 pid_t pid;char record[256];int fd,n,exit_status=20;const char*state="PREWRITE";unsigned long bytes=0;assert(!redirect&&!timeout&&child);
 assert(strstr(argv[0],FW_UPGRADE_PRIVATE "/fwupgrade.")&&strstr(argv[0],"/writer"));
 assert(!strcmp(argv[1],"--upgrade-write")&&!strcmp(argv[2],FW_IMG_NAME)&&!strcmp(argv[3],"firmware")&&!argv[5]);
 writer_calls++;event("writer");if(kind==10){errno=ENOENT;return ENOENT;}
 pid=fork();assert(pid>=0);if(pid){*child=pid;return 0;}
 if(kind==6)_exit(20);
 if(kind==0||kind==5||kind==13||kind==15||kind==21){state="VERIFIED";bytes=kind==13?0:kind==15?FW_UPGRADE_MAX_BYTES+1:4096;exit_status=kind==5?21:0;}
 if(kind==2){state="MAYBE_WRITTEN";bytes=4096;exit_status=21;}
 if(kind==4)exit_status=21;
 if(kind==20)exit_status=0;
 if(kind==22)bytes=1;
 n=snprintf(record,sizeof(record),"K2P_FWUP_V1\nstate=%s\npid=%lu\ntarget=%s\nimage_bytes=%lu\nverified_bytes=%lu\n",state,kind==16?0:(unsigned long)getpid()+(kind==7),kind==14?"Firmware":"firmware",bytes,!strcmp(state,"VERIFIED")?bytes+(kind==21):0);
 if(kind==17)n--;
 if(kind==18)record[10]=0;
 if(kind==19){char*p=strstr(record,"pid=");assert(p);p[4]='+';}
 fd=open(argv[4],O_WRONLY|O_CREAT|O_EXCL,0600);assert(fd>=0);assert(write(fd,record,n)==n);assert(close(fd)==0);
 if(kind==8){fd=open(argv[4],O_WRONLY|O_APPEND);assert(fd>=0);assert(write(fd,"extra\n",6)==6);close(fd);}
 if(kind==9){char alias[512];snprintf(alias,sizeof(alias),"%s.alias",argv[4]);assert(rename(argv[4],alias)==0);assert(symlink(alias,argv[4])==0);}
 if(kind==11)assert(chmod(argv[4],0644)==0);
 if(kind==12){char alias[512];snprintf(alias,sizeof(alias),"%s.alias",argv[4]);assert(link(argv[4],alias)==0);}
 if(kind==3){kill(getpid(),SIGKILL);_exit(99);}
 _exit(exit_status);
}
#define open fixture_open
#define close fixture_close
#define write fixture_write
#define fstat fixture_fstat
#define fstatat fixture_fstatat
#define ioctl fixture_ioctl
#define reboot fake_reboot
#define sync fake_sync
#define usleep fake_usleep
#define mlockall fixture_mlockall
#define munlockall fixture_munlockall
#define daemon fixture_daemon
#define sigaction(...) fixture_sigaction(__VA_ARGS__)
#define pause fixture_pause
'''
    code += '#define UPGRADE_GUARD_PRIVATE FW_UPGRADE_PRIVATE\n'
    code += source('trunk/user/shared/upgrade_guard.h') + '\n'
    code += 'static volatile sig_atomic_t firmware_upgrade_pid1_active, firmware_upgrade_pid1_fault;\n'
    code += 'struct firmware_upgrade_service {' + structure + '};\n'
    watchdog = source('trunk/user/rc/watchdog.c')
    code += function(watchdog, 'start_watchdog') + '\n' + function(watchdog, 'notify_watchdog_time') + '\n'
    for name in FUNCTIONS:
        code += function(text, name) + '\n'
    code += function(watchdog, 'watchdog_main') + '\n'
    code += r'''
static void json_array(const int*a){int i;putchar('[');for(i=0;i<7;i++)printf("%s%d",i?",":"",a[i]);putchar(']');}
int main(int argc,char**argv){
 int i,mask,phase;assert(argc==13);first_status=atoi(argv[2]);second_status=atoi(argv[3]);hook_exists=atoi(argv[4]);hook_status=atoi(argv[5]);kind=atoi(argv[6]);mask=atoi(argv[7]);stop_fail=atoi(argv[8]);start_fail=atoi(argv[9]);hw_mode=atoi(argv[10]);stage_fault=atoi(argv[11]);pin_failure=atoi(argv[12]);
 for(i=0;i<7;i++)running[i]=!!(mask&(1<<i));
 if(!strcmp(argv[1],"status")){printf("{\"status\":%d}\n",write_storage_to_mtd());return 0;}
 if(!strcmp(argv[1],"guard")){int result=start_watchdog();notify_watchdog_time();printf("{\"result\":%d,\"execs\":%d}\n",result,guard_execs);return 0;}
 if(!strncmp(argv[1],"mainguard",9)){int result;daemon_marker=!strcmp(argv[1],"mainguard-late");result=watchdog_main(0,NULL);printf("{\"result\":%d,\"daemon\":%d,\"hardware_inits\":%d}\n",result,daemon_calls,hardware_inits);return 0;}
 phase=flash_firmware();
 printf("{\"phase\":%d,\"saves\":%d,\"hooks\":%d,\"time_calls\":%d,\"writes\":%d,\"logs\":%d,\"criticals\":%d,\"reboots\":%d,\"syncs\":%d,\"mlocks\":%d,\"munlocks\":%d,\"inhibited\":%d,\"hardware_opens\":%d,\"hardware_disables\":%d,\"hardware_closes\":%d,\"hardware_keepalives\":%d,\"snapshot_revisions\":[%d,%d],\"stops\":",phase,saves,hooks,time_calls,writer_calls,logs,criticals,reboots,syncs,mlocks,munlocks,firmware_upgrade_inhibited(),hw_opens,hw_disables,hw_closes,hw_pings,versions[0],versions[1]);
 json_array(stops);printf(",\"starts\":");json_array(starts);printf(",\"running\":");json_array(running);printf(",\"trace\":\"%s\"}\n",trace);return 0;
}
'''
    return code


def compile_harness(root, superset=False):
    name = 'upgrade-superset' if superset else 'upgrade'
    path = root / (name + '.c')
    prefix = '#define USE_STORAGE 1\n#define USE_USB_SUPPORT 1\n' if superset else ''
    path.write_text(prefix + generate(root))
    binary = root / name
    result = subprocess.run(['clang', '-std=gnu99', '-Wall', '-Wextra', '-Werror',
                             '-fsanitize=address,undefined',
                             '-Wno-unused-parameter', '-Wno-unused-function', str(path), '-o', str(binary)],
                            text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return binary


def compile_consumer(root):
    import re
    core = generate(root).split('static void json_array', 1)[0]
    consumer = function(source('trunk/user/rc/rc.c'), 'handle_notifications')
    code = core + r'''
#undef open
#undef close
#undef write
#undef fstat
#undef fstatat
#include <dirent.h>
static char queue_path[1024],pending_path[1024],names_queue[32][32];
static int total_names,cursor,notification_events,notification_signals,notification_actions;
static int nvram_nf_nat_type,nvram_modem_type,nvram_modem_rule;
#define DIR_RC_NOTIFY queue_path
#define DIR_RC_INCOMPLETE pending_path
/* Real queue files/ownership validation; deterministic order exercises the
 * flash-first batch without depending on a host filesystem's readdir order. */
static struct dirent* ordered_readdir(DIR*directory){
 static struct dirent entry;struct stat st;
 while(cursor<total_names){const char*name=names_queue[cursor++];
  if(fstatat(dirfd(directory),name,&st,AT_SYMLINK_NOFOLLOW)==0){memset(&entry,0,sizeof(entry));snprintf(entry.d_name,sizeof(entry.d_name),"%s",name);return &entry;}
 }return NULL;
}
static int fake_rearm(pid_t pid,int sig){assert(pid==getpid()&&sig==SIGUSR1);notification_signals++;return 0;}
static int notification_printf(const char*fmt,...){if(!strcmp(fmt,"rc notification: %s\n"))notification_events++;return 0;}
'''
    shared = source('trunk/user/shared/notify_rc.c')
    for name in ('valid_event_name', 'rc_notification_open_dir', 'rc_notification_valid_marker'):
        code += function(shared, name) + '\n'
    for line in source('trunk/user/shared/notify_rc.h').splitlines():
        if line.startswith('#define RCN_'):
            code += line + '\n'
    standard = {'handle_notifications', 'flash_firmware', 'firmware_upgrade_inhibited',
                'rc_notification_open_dir', 'rc_notification_valid_marker', 'fdopendir',
                'close', 'readdir', 'strcmp', 'unlinkat', 'snprintf', 'remove', 'printf',
                'fopen', 'fclose', 'closedir', 'kill', 'getpid', 'if', 'for', 'while', 'sizeof', 'defined'}
    calls = set(re.findall(r'\b([a-zA-Z_]\w*)\s*\(', consumer))
    for name in sorted(calls - standard):
        code += '#define ' + name + '(...) 0\n'
    code += '#undef start_logger\n#define start_logger(...) (notification_actions++,0)\n'
    code += '#define readdir ordered_readdir\n#define kill fake_rearm\n#define printf notification_printf\n'
    code += consumer + '\n#undef readdir\n#undef printf\n'
    code += r'''
static int remaining(void){int count=0;struct dirent*entry;DIR*d=opendir(queue_path);assert(d);while((entry=readdir(d)))if(entry->d_name[0]!='.')count++;closedir(d);return count;}
int main(int argc,char**argv){
 char path[1200];int i,fd,rounds;assert(argc==9);umask(0);
 snprintf(queue_path,sizeof(queue_path),"%s/queue",argv[1]);snprintf(pending_path,sizeof(pending_path),"%s/pending",argv[1]);
 assert(mkdir(queue_path,0700)==0&&mkdir(pending_path,0700)==0);
 total_names=atoi(argv[2])+1;assert(total_names<=32);strcpy(names_queue[0],"flash_firmware");
 for(i=1;i<total_names;i++)snprintf(names_queue[i],sizeof(names_queue[i]),"later_%02d",i);
 if(total_names>1)strcpy(names_queue[1],RCN_RESTART_SYSLOG);
 for(i=0;i<total_names;i++){
  snprintf(path,sizeof(path),"%s/%s",queue_path,names_queue[i]);fd=open(path,O_WRONLY|O_CREAT,0600);assert(fd>=0);close(fd);
  snprintf(path,sizeof(path),"%s/%s",pending_path,names_queue[i]);fd=open(path,O_WRONLY|O_CREAT,0600);assert(fd>=0);close(fd);
 }
 first_status=atoi(argv[3]);second_status=atoi(argv[4]);hook_exists=atoi(argv[5]);hook_status=atoi(argv[6]);kind=atoi(argv[7]);rounds=atoi(argv[8]);
 for(i=0;i<7;i++)running[i]=1;
 for(i=0;i<rounds;i++){cursor=0;handle_notifications();}
 printf("{\"events\":%d,\"signals\":%d,\"recognized_actions\":%d,\"remaining\":%d,\"writes\":%d,\"watchdog\":%d,\"watchdog_restarts\":%d,\"inhibited\":%d}\n",notification_events,notification_signals,notification_actions,remaining(),writer_calls,running[0],starts[0],firmware_upgrade_inhibited());
 return 0;
}
'''
    path, binary = root / 'consumer.c', root / 'consumer'
    path.write_text(code)
    result = subprocess.run(['clang', '-Wno-unused-value', '-Wno-unused-function',
                             '-fsanitize=address,undefined', str(path), '-o', str(binary)],
                            text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return binary
