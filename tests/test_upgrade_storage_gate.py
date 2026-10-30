#!/usr/bin/env python3
"""Exercise actual rc upgrade/save functions with inert service/flash backends."""
import fcntl
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_httpd_regressions import function, source
import test_storage_regressions as storage_fixture


class UpgradeStorageGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-upgrade-gate-code-')
        root = Path(cls.temp.name)
        code = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#define SCRIPT_SHUTDOWN "/etc/storage/shutdown_script.sh"
#define FW_IMG_NAME "/tmp/linux.trx"
#define FW_MTD_NAME "firmware"
#define USE_STORAGE 1
#define USE_USB_SUPPORT 1
static int first_status,second_status,hook_status,hook_exists,firmware_status;
static int saves,hooks,stops_misc,stops_services,detach_calls,spool_calls,kills,writes;
static int syncs,sleeps,watchdog=1,restarts,logs,time_calls,revision,versions[2];
static char trace[4096];
static void event(const char*s){assert(strlen(trace)+strlen(s)+2<sizeof(trace));strcat(trace,s);strcat(trace,",");}
static int doSystem(const char*fmt,...){
 char command[512];va_list ap;va_start(ap,fmt);vsnprintf(command,sizeof(command),fmt,ap);va_end(ap);
 if(!strcmp(command,"/sbin/mtd_storage.sh save")){
  assert(saves<2);versions[saves]=revision;event("save");saves++;return saves==1?first_status:second_status;
 }
 assert(!strcmp(command,SCRIPT_SHUTDOWN " 0"));event("hook");hooks++;revision++;return hook_status;
}
static void logmessage(const char*tag,const char*fmt,...){assert(!strcmp(tag,"firmware"));logs++;event("log");}
static void stop_misc(void){stops_misc++;watchdog=0;event("stop_misc");}
static void stop_services(int all){assert(all==0);stops_services++;event("stop_services");}
static int check_if_file_exist(const char*path){assert(!strcmp(path,SCRIPT_SHUTDOWN));return hook_exists;}
static void safe_remove_all_stor_devices(int all){assert(all==0);detach_calls++;event("detach");}
static void stop_usb_printer_spoolers(void){spool_calls++;event("spool");}
static void stop_igmpproxy(const char*unused){event("igmp");}
static void kill_services(char**names,int timeout,int force){assert(timeout==6&&force==1);kills++;event("kill");}
static void storage_save_time(int seconds){assert(seconds==60);time_calls++;event("time");}
static void fake_sync(void){syncs++;event("sync");}
static void fake_sleep(int seconds){assert(seconds==1);sleeps++;event("sleep");}
#define sync fake_sync
#define sleep fake_sleep
static int eval(const char*program,const char*a,const char*b,const char*image,const char*target){
 assert(!strcmp(program,"/tmp/mtd_write")&&!strcmp(a,"-r")&&!strcmp(b,"write"));
 assert(!strcmp(image,FW_IMG_NAME)&&!strcmp(target,FW_MTD_NAME));writes++;event("writer");return firmware_status;
}
static void start_watchdog(void){watchdog=1;restarts++;event("restart_watchdog");}
'''
        text = source('trunk/user/rc/rc.c')
        code += function(text, 'write_storage_to_mtd') + '\n' + function(text, 'flash_firmware')
        core = code
        code += r'''
/* Other existing callers may deliberately ignore the new int result. */
static void noncritical_caller(void){write_storage_to_mtd();}
int main(int argc,char**argv){
 assert(argc==7);first_status=atoi(argv[1]);second_status=atoi(argv[2]);hook_exists=atoi(argv[3]);hook_status=atoi(argv[4]);firmware_status=atoi(argv[5]);
 if(!strcmp(argv[6],"status")){int status=write_storage_to_mtd();printf("{\"status\":%d}\n",status);return 0;}
 int phase=flash_firmware();
 printf("{\"phase\":%d,\"saves\":%d,\"hooks\":%d,\"stop_misc\":%d,\"stop_services\":%d,\"detach\":%d,\"spool\":%d,\"kills\":%d,\"writes\":%d,\"syncs\":%d,\"sleeps\":%d,\"watchdog\":%d,\"watchdog_restarts\":%d,\"logs\":%d,\"time_calls\":%d,\"revision\":%d,\"snapshot_revisions\":[%d,%d],\"trace\":\"%s\"}\n",
 phase,saves,hooks,stops_misc,stops_services,detach_calls,spool_calls,kills,writes,syncs,sleeps,watchdog,restarts,logs,time_calls,revision,versions[0],versions[1],trace);
 return 0;
}
'''
        src = root / 'upgrade.c'; src.write_text(code)
        cls.binary = root / 'upgrade'
        compiled = subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                                   '-Wno-unused-function', str(src), '-o', str(cls.binary)],
                                  capture_output=True, text=True)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        cls.queue_binary = root / 'consumer'
        cls.compile_consumer(core, root, cls.queue_binary)

    @staticmethod
    def compile_consumer(core, root, binary):
        consumer = function(source('trunk/user/rc/rc.c'), 'handle_notifications')
        code = '#define _GNU_SOURCE\n' + core + r'''
#undef sync
#undef sleep
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <dirent.h>
#include <signal.h>
#include <errno.h>
#include <limits.h>
static char queue_path[1024],pending_path[1024],names[32][32];
static int total_names,cursor,notification_events,notification_signals,notification_actions,nvram_nf_nat_type,nvram_modem_type,nvram_modem_rule;
#define DIR_RC_NOTIFY queue_path
#define DIR_RC_INCOMPLETE pending_path
/* Real files/fstatat/ownership helpers; controlled directory order makes the
 * flash-first dispatch independent of the host filesystem's readdir order. */
static struct dirent* ordered_readdir(DIR*directory){
 static struct dirent entry;struct stat st;
 while(cursor<total_names){const char*name=names[cursor++];
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
        standard = {'handle_notifications', 'flash_firmware', 'rc_notification_open_dir',
                    'rc_notification_valid_marker', 'fdopendir', 'close', 'readdir', 'strcmp',
                    'unlinkat', 'snprintf', 'remove', 'printf', 'fopen', 'fclose', 'closedir',
                    'kill', 'getpid', 'if', 'for', 'while', 'sizeof', 'defined'}
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
 total_names=atoi(argv[2])+1;assert(total_names<=32);strcpy(names[0],"flash_firmware");
 for(i=1;i<total_names;i++)snprintf(names[i],sizeof(names[i]),"later_%02d",i);
 if(total_names>1)strcpy(names[1],RCN_RESTART_SYSLOG);
 for(i=0;i<total_names;i++){
  snprintf(path,sizeof(path),"%s/%s",queue_path,names[i]);fd=open(path,O_WRONLY|O_CREAT,0600);assert(fd>=0);close(fd);
  snprintf(path,sizeof(path),"%s/%s",pending_path,names[i]);fd=open(path,O_WRONLY|O_CREAT,0600);assert(fd>=0);close(fd);
 }
 first_status=atoi(argv[3]);second_status=atoi(argv[4]);hook_exists=atoi(argv[5]);hook_status=atoi(argv[6]);firmware_status=atoi(argv[7]);rounds=atoi(argv[8]);
 for(i=0;i<rounds;i++){cursor=0;handle_notifications();}
 printf("{\"events\":%d,\"signals\":%d,\"recognized_actions\":%d,\"remaining\":%d,\"writes\":%d,\"stop_misc\":%d,\"watchdog\":%d,\"watchdog_restarts\":%d,\"saves\":%d,\"hooks\":%d}\n",notification_events,notification_signals,notification_actions,remaining(),writes,stops_misc,watchdog,restarts,saves,hooks);
 return 0;
}
'''
        path = root / 'consumer.c'; path.write_text(code)
        result = subprocess.run(['clang', '-Wno-unused-value', '-Wno-unused-function',
                                 '-fsanitize=address,undefined', str(path), '-o', str(binary)],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, first=0, second=0, hook=False, hook_status=0, firmware=0, mode='flash'):
        completed = subprocess.run([str(self.binary), str(first), str(second), str(int(hook)),
                                    str(hook_status), str(firmware), mode],
                                   check=True, text=True, capture_output=True, timeout=5)
        return json.loads(completed.stdout)

    def assert_no_shutdown_or_flash(self, result):
        for key in ('stop_misc', 'stop_services', 'detach', 'spool', 'kills', 'writes', 'syncs', 'sleeps', 'watchdog_restarts'):
            self.assertEqual(result[key], 0, (key, result))
        self.assertEqual(result['watchdog'], 1)
        self.assertEqual(result['logs'], 1)
        self.assertEqual(result['phase'], 0)

    def test_save_propagates_success_exit_signal_and_system_failure(self):
        for status in (0, 256, -1, 9, 15, 36608):
            with self.subTest(status=status):
                self.assertEqual(self.run_case(first=status, mode='status')['status'], status)

    def test_first_save_failures_do_not_run_hook_or_shutdown(self):
        for status in (256, -1, 9, 15, 36608):
            with self.subTest(status=status):
                result = self.run_case(first=status, hook=True)
                self.assert_no_shutdown_or_flash(result)
                self.assertEqual((result['saves'], result['hooks'], result['time_calls']), (1, 0, 1))

    def test_busy_actual_storage_lock_aborts_before_shutdown(self):
        storage_fixture.StorageRegression.setUpClass()
        fixture = storage_fixture.StorageRegression('runTest'); fixture.setUp()
        try:
            lock = fixture.tmp / '.storage_operation'; lock.mkdir(mode=0o700)
            with (lock / 'lock').open('w') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                failed = fixture.run_script('save')
            self.assertEqual(failed.returncode, 1)
            self.assertFalse(fixture.flash_calls.exists())
            result = self.run_case(first=failed.returncode << 8, hook=True)
            self.assert_no_shutdown_or_flash(result)
            self.assertEqual(result['hooks'], 0)
        finally:
            fixture.tearDown(); storage_fixture.StorageRegression.tearDownClass()

    def test_without_hook_success_saves_once_then_uses_existing_stop_order(self):
        result = self.run_case()
        self.assertEqual(result['phase'], 1)
        self.assertEqual((result['saves'], result['hooks'], result['writes'], result['logs']), (1, 0, 1, 0))
        self.assertEqual(result['trace'].strip(',').split(','),
                         ['time', 'save', 'stop_misc', 'stop_services', 'detach', 'spool', 'igmp', 'kill', 'sync', 'sleep', 'writer'])

    def test_hook_changes_are_saved_before_any_services_stop(self):
        result = self.run_case(hook=True)
        self.assertEqual((result['saves'], result['hooks'], result['writes']), (2, 1, 1))
        self.assertEqual(result['snapshot_revisions'], [0, 1])
        self.assertEqual(result['trace'].strip(',').split(',')[:6], ['time', 'save', 'hook', 'save', 'stop_misc', 'stop_services'])

    def test_hook_failure_aborts_without_second_save_or_stopping_services(self):
        for status in (256, -1, 15):
            with self.subTest(status=status):
                result = self.run_case(hook=True, hook_status=status)
                self.assert_no_shutdown_or_flash(result)
                self.assertEqual((result['saves'], result['hooks'], result['revision']), (1, 1, 1))

    def test_second_save_failure_aborts_before_shutdown_but_cannot_undo_hook(self):
        for status in (256, -1, 9, 15):
            with self.subTest(status=status):
                result = self.run_case(second=status, hook=True)
                self.assert_no_shutdown_or_flash(result)
                self.assertEqual((result['saves'], result['hooks'], result['revision']), (2, 1, 1))

    def test_firmware_eval_failure_keeps_existing_watchdog_restart(self):
        for hook in (False, True):
            with self.subTest(hook=hook):
                result = self.run_case(hook=hook, firmware=51)
                self.assertEqual((result['writes'], result['watchdog_restarts'], result['watchdog']), (1, 1, 1))
                self.assertEqual(result['phase'], 1)

    def queue_case(self, later=1, first=256, second=0, hook=False, hook_status=0, firmware=0, rounds=1):
        with tempfile.TemporaryDirectory(prefix='k2p-upgrade-queue-') as temp:
            result = subprocess.run([str(self.queue_binary), temp, str(later), str(first), str(second),
                                     str(int(hook)), str(hook_status), str(firmware), str(rounds)],
                                    check=True, text=True, capture_output=True, timeout=5)
        return json.loads(result.stdout)

    def test_consumer_preflight_and_hook_aborts_continue_to_later_marker(self):
        for options in ({'first': 256}, {'first': 0, 'hook': True, 'hook_status': 256},
                        {'first': 0, 'second': 256, 'hook': True}):
            with self.subTest(options=options):
                result = self.queue_case(**options)
                self.assertEqual((result['events'], result['remaining'], result['writes'], result['stop_misc']), (2, 0, 0, 0))
                self.assertEqual((result['watchdog'], result['watchdog_restarts']), (1, 0))
                self.assertEqual(result['recognized_actions'], 1)

    def test_consumer_abort_rearms_and_drains_more_than_ten_markers(self):
        result = self.queue_case(later=25, rounds=3)
        self.assertEqual((result['events'], result['signals'], result['remaining'], result['writes']), (26, 2, 0, 0))
        self.assertEqual(result['recognized_actions'], 1)

    def test_consumer_stops_after_entering_writer_phase_even_when_writer_fails(self):
        for firmware in (0, 51):
            with self.subTest(firmware=firmware):
                result = self.queue_case(later=25, first=0, hook=True, firmware=firmware)
                self.assertEqual((result['events'], result['signals'], result['remaining'], result['writes']), (1, 0, 25, 1))
                self.assertEqual(result['stop_misc'], 1)
                self.assertEqual(result['recognized_actions'], 0)

    def test_shipped_default_shutdown_hook_is_successful_comment_only_script(self):
        text = source('trunk/user/scripts/mtd_storage.sh')
        match = re.search(r'cat > "\$script_shutd" <<EOF\n(.*?)\nEOF', text, re.S)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertTrue(all(not line.strip() or line.lstrip().startswith('#') for line in body.splitlines()))
        with tempfile.TemporaryDirectory(prefix='k2p-default-hook-') as temp:
            script = Path(temp) / 'shutdown.sh'; script.write_text(body + '\n')
            self.assertEqual(subprocess.run(['sh', str(script), '0'], capture_output=True, timeout=5).returncode, 0)

    def test_public_prototype_exposes_the_save_result(self):
        self.assertRegex(source('trunk/user/rc/rc.h'), r'\bint\s+write_storage_to_mtd\(void\);')


if __name__ == '__main__':
    unittest.main()
