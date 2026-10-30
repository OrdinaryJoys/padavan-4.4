#!/usr/bin/env python3
"""Actual header/process tests. Linux uses real /proc; other hosts label fixtures."""
import errno
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from test_httpd_regressions import ROOT, function, source


class HookRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-hook-native-')
        cls.root = Path(cls.temp.name)
        cls.header = cls.root / 'hook_runner.h'
        cls.header.write_text(source('trunk/user/rc/hook_runner.h'))
        cls.fixture = cls.root / 'fixture.c'
        cls.fixture.write_text(source('tests/hook_runner_fixture.c'))
        cls.binary = cls.compile('clang', 'runner', sanitize=True)
        cls.small_scan = cls.compile('clang', 'small-scan', sanitize=True, small=True)

    @classmethod
    def compile(cls, compiler, name, sanitize=False, small=False):
        binary = cls.root / name
        command = [compiler, '-std=gnu99', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(cls.root)]
        if sanitize:
            command += ['-fsanitize=address,undefined']
        if small:
            command += ['-DHOOK_RUNNER_PROC_LIMIT=4']
        if sys.platform.startswith('linux'):
            command += ['-lrt']
        result = subprocess.run([*command, str(cls.fixture), '-o', str(binary)], text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(prefix='case-', dir=self.root)
        self.addCleanup(self.case.cleanup)
        self.path = Path(self.case.name)
        self.proc = self.path / 'proc'; self.proc.mkdir()
        kernel = self.proc / '2'; kernel.mkdir()
        (kernel / 'stat').write_text('2 (kthreadd) S 0 0 0 0 0\n')
        self.script = self.path / 'shutdown.sh'
        self.report = self.path / 'report.json'
        self.audit = self.path / 'exec-audit'
        self.effect = self.path / 'effect'
        self.child_pid = self.path / 'child-pid'
        self.arg_out = self.path / 'argument'
        self.payload = self.path / 'payload'
        self.payload.write_bytes(b'X' * (128 * 1024 + 4096))
        self.env = dict(os.environ, HOOK_EXEC_AUDIT=str(self.audit), HOOK_EFFECT=str(self.effect),
                        HOOK_CHILD_PID=str(self.child_pid), HOOK_ARG_OUT=str(self.arg_out),
                        HOOK_TEST_PAYLOAD=str(self.payload), HOOK_TEST_PROC='' if sys.platform.startswith('linux') else str(self.proc),
                        HOOK_FD_DIRECTORY='/proc/self/fd' if sys.platform.startswith('linux') else '/dev/fd')

    def command(self, body='exit 0\n', timeout=400, term=80, hard=120, fault='none', descriptors='normal',
                level=0, mode=0o755, shebang=True, binary=None):
        self.script.write_text(('#!/bin/sh\n' if shebang else '') + body)
        self.script.chmod(mode)
        proc = Path('/proc') if sys.platform.startswith('linux') else self.proc
        return [str(binary or self.binary), str(self.script), str(level), str(timeout), str(term), str(hard),
                str(proc), fault, str(self.report), descriptors]

    def run_case(self, **options):
        completed = subprocess.run(self.command(**options), env=self.env, capture_output=True, timeout=6)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors='replace'))
        result = json.loads(self.report.read_text())
        self.assertEqual(result['signal_after_reap'], 0, result)
        self.assertEqual((result['mask_restored'], result['handlers_restored']), (1, 1), result)
        self.assertLess(result['elapsed_ms'], 2000, result)
        return result

    @staticmethod
    def background_setup(redirect=''):
        return f'''sleep 100 {redirect} &
bg=$!
printf '%s' "$bg" > "$HOOK_CHILD_PID"
if [ -n "$HOOK_TEST_PROC" ]; then
 mkdir -p "$HOOK_TEST_PROC/$bg"
 printf '%s (hook ) child) S 1 %s 0 0\\n' "$bg" "$$" > "$HOOK_TEST_PROC/$bg/stat"
fi
'''

    def assert_not_live(self, pid):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if sys.platform.startswith('linux'):
                try:
                    record = Path(f'/proc/{pid}/stat').read_text()
                    live = record.rsplit(')', 1)[1].split()[0] != 'Z'
                except FileNotFoundError:
                    live = False
            else:
                result = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
                live = bool(result.stdout.strip()) and not result.stdout.strip().startswith('Z')
            if not live:
                return
            time.sleep(.02)
        self.fail(f'owned hook child {pid} still live')

    def test_normal_exit_zero_action_and_raw_nonzero_statuses(self):
        result = self.run_case(body='printf "%s" "$1" > "$HOOK_ARG_OUT"\nexit 0\n', level=2)
        self.assertEqual(result['status'], 0)
        self.assertEqual(self.arg_out.read_text(), '2')
        self.assertGreater(result['exits_seen'], 0)
        self.assertEqual(result['reaped_direct_by_old_handler'], 0)
        for status in (1, 7, 126):
            with self.subTest(status=status):
                result = self.run_case(body=f'exit {status}\n')
                self.assertEqual((result['status'], result['error']), (status << 8, 0))

    def test_signal_exit_and_child_signal_mask_are_preserved(self):
        for name in ('TERM', 'USR2'):
            with self.subTest(name=name):
                result = self.run_case(body=f'kill -{name} $$\n')
                self.assertEqual(result['status'], getattr(signal, 'SIG' + name))
                self.assertEqual(result['error'], 0)

    def test_literal_path_no_shebang_fallback_and_nonexecutable_script(self):
        self.script = self.path / 'name with spaces $(touch PWN)'
        result = self.run_case(body='printf literal > "$HOOK_EFFECT"\n', shebang=False)
        self.assertEqual(result['status'], 0)
        self.assertEqual(self.effect.read_text(), 'literal')
        self.assertFalse((self.path / 'PWN').exists())
        self.effect.unlink()
        result = self.run_case(body='printf forbidden > "$HOOK_EFFECT"\n', mode=0o600)
        self.assertEqual(result['status'], 126 << 8)
        self.assertFalse(self.effect.exists())

    def test_closed_standard_fds_are_recreated_and_not_cloexec(self):
        result = self.run_case(body='if IFS= read -r value; then exit 33; fi\nprintf OUT\nprintf ERR >&2\n', descriptors='closed-stdio')
        self.assertEqual(result['status'], 0)
        self.assertEqual(result['read_bytes'], [3, 3])

    def test_high_fd_above_lowered_soft_limit_is_closed_before_exec(self):
        result = self.run_case(body='if [ -e "$HOOK_FD_DIRECTORY/512" ]; then exit 44; fi\nexit 0\n', descriptors='high-fd')
        self.assertEqual(result['status'], 0)

    def test_descriptor_close_error_prevents_exec(self):
        result = self.run_case(body='touch "$HOOK_EFFECT"\n', fault='fd-close')
        self.assertEqual(result['status'], 126 << 8)
        self.assertFalse(self.audit.exists())
        self.assertFalse(self.effect.exists())

    def test_fork_and_pipe_setup_failure_never_exec(self):
        for fault in ('fork', 'pipe'):
            with self.subTest(fault=fault):
                result = self.run_case(fault=fault)
                self.assertLess(result['status'], 0)
                self.assertFalse(self.audit.exists())
                self.assertEqual(result['group_signals'], 0)

    def test_nonwaitable_sigchld_policy_rejected_without_child(self):
        for fault in ('chld-ignore', 'chld-nocldwait'):
            with self.subTest(fault=fault):
                result = self.run_case(fault=fault)
                self.assertLess(result['status'], 0)
                self.assertEqual(result['forks'], 0)
                self.assertFalse(self.audit.exists())

    def test_waitid_eintr_is_retried_and_lost_child_is_never_group_signalled(self):
        result = self.run_case(fault='wait-eintr')
        self.assertEqual(result['status'], 0)
        self.assertGreater(result['waits'], 1)
        result = self.run_case(body='sleep 100\n', fault='wait-lost')
        self.assertLess(result['status'], 0)
        self.assertEqual(result['group_signals'], 0)

    def test_closed_output_does_not_hide_hung_child(self):
        result = self.run_case(body='exec 1>&- 2>&-\nsleep 100\n', timeout=100)
        self.assertLess(result['status'], 0)
        self.assertEqual(result['timeout'], 1)
        self.assertGreater(result['group_signals'], 0)

    def test_stdout_stderr_caps_and_fair_drain(self):
        for body in ('cat "$HOOK_TEST_PAYLOAD"\n', 'cat "$HOOK_TEST_PAYLOAD" >&2\n',
                     'while :; do printf "%04096d" 0; printf "%04096d" 1 >&2; done\n'):
            with self.subTest(body=body[:20]):
                result = self.run_case(body=body)
                self.assertLess(result['status'], 0)
                self.assertEqual(result['output_limit'], 1)
                if body.startswith('while'):
                    self.assertTrue(all(size > 0 for size in result['read_bytes']))

    def test_exit_zero_background_is_cleaned_and_still_rejected(self):
        for redirect in ('', '> /dev/null 2>&1'):
            with self.subTest(redirect=redirect):
                # This checks live-descendant policy, not a short timeout.
                # Instrumented shell startup can consume the default400ms
                # fixture budget on slower hosts; timeout has its own tests.
                result = self.run_case(body=self.background_setup(redirect) + 'exit 0\n', timeout=2000)
                self.assertLess(result['status'], 0)
                self.assertEqual(result['background'], 1, result)
                self.assertGreater(result['group_signals'], 0)
                self.assert_not_live(int(self.child_pid.read_text()))

    def test_term_ignoring_group_is_killed_within_absolute_budget(self):
        result = self.run_case(body="trap '' TERM\nprintf ready > \"$HOOK_EFFECT\"\nwhile :; do sleep 100; done\n", timeout=400)
        self.assertEqual(self.effect.read_text(), 'ready')
        self.assertLess(result['status'], 0)
        self.assertEqual(result['timeout'], 1)
        self.assertGreaterEqual(result['group_signals'], 2)

    def test_parent_termination_signals_cleanup_then_call_old_handler_once(self):
        for index, sig in enumerate((signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT)):
            with self.subTest(sig=sig):
                for path in (self.child_pid, self.audit):
                    path.unlink(missing_ok=True)
                command = self.command(body=self.background_setup() + 'wait\n', timeout=3000)
                process = subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    deadline = time.monotonic() + 2
                    while not self.child_pid.exists() and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue(self.child_pid.exists())
                    os.kill(process.pid, sig)
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, stderr.decode(errors='replace'))
                    result = json.loads(self.report.read_text())
                    self.assertLess(result['status'], 0)
                    self.assertEqual(result['cancelled'], 1)
                    self.assertEqual(result['signals_seen'], [int(i == index) for i in range(4)])
                    self.assertEqual((result['signal_after_reap'], result['mask_restored'], result['handlers_restored']), (0, 1, 1))
                    self.assert_not_live(int(self.child_pid.read_text()))
                finally:
                    if process.poll() is None:
                        process.kill(); process.communicate(timeout=2)

    def scan(self, rows, group=700, leader=100, milliseconds=200, error=None, binary=None):
        proc = self.path / ('scan-' + str(time.monotonic_ns())); proc.mkdir()
        for pid, body in rows.items():
            node = proc / str(pid); node.mkdir(); (node / 'stat').write_text(body)
        report = self.path / 'scan.json'
        env = dict(self.env)
        if error is not None: env['HOOK_TEST_READ_ERROR'] = str(error)
        subprocess.run([str(binary or self.binary), '--scan', str(proc), str(group), str(leader), str(milliseconds), str(report)],
                       env=env, capture_output=True, check=True, timeout=3)
        return json.loads(report.read_text())

    def test_proc_group_zero_comm_parentheses_zombies_and_live_members(self):
        rows = {2: '2 (kthreadd) S 0 0 0\n', 100: '100 (leader) S 1 700 0\n',
                101: '101 (name ) has ) parens) Z 1 700 0\n', 102: '102 (other) S 1 701 0\n'}
        self.assertEqual(self.scan(rows)['result'], 0)
        rows[103] = '103 (live ) child) S 1 700 0\n'
        self.assertEqual(self.scan(rows)['result'], 1)

    def test_proc_read_disappearance_and_malformed_deadline_count_fail_closed(self):
        for error in (errno.ENOENT, errno.ESRCH):
            self.assertEqual(self.scan({2: '2 (kthreadd) S 0 0 0\n'}, error=error)['result'], 0)
        self.assertEqual(self.scan({2: 'invalid'}, group=700)['result'], -1)
        self.assertEqual(self.scan({2: '2 (kthreadd) S 0 0\n'}, milliseconds=0)['result'], -1)
        rows = {pid: f'{pid} (other) S 0 0 0\n' for pid in range(2, 8)}
        self.assertEqual(self.scan(rows, binary=self.small_scan)['result'], -1)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Actual Linux /proc process groups are checked on Linux CI/MIPS')
    def test_linux_actual_proc_backend_is_required(self):
        self.assertEqual(self.run_case()['group_scan_backend'], 'linux-real-proc')

    def test_gcc_strict_compile_and_real_header_smoke(self):
        compiler = shutil.which('gcc-16') or shutil.which('gcc')
        self.assertIsNotNone(compiler)
        binary = self.compile(compiler, 'gcc-runner')
        self.assertEqual(self.run_case(binary=binary)['status'], 0)

    def test_production_budgets_and_explicit_rc_link_dependency(self):
        header = self.header.read_text()
        for literal in ('#define HOOK_RUNNER_TIMEOUT_MS 30000U', '#define HOOK_RUNNER_TERM_MS 2000U',
                        '#define HOOK_RUNNER_KILL_MS 1000U', '#define HOOK_RUNNER_STREAM_LIMIT (128U * 1024U)'):
            self.assertIn(literal, header)
        makefile = source('trunk/user/rc/Makefile')
        self.assertIn('-lrt', makefile)
        self.assertIn('rc.o: hook_runner.h', makefile)

    def test_ordinary_shutdown_uses_bounded_hook_and_continues_after_failure(self):
        code = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SCRIPT_SHUTDOWN "/synthetic/shutdown"
#define HOOK_RUNNER_TIMEOUT_MS 30000U
#define HOOK_RUNNER_TERM_MS 2000U
#define HOOK_RUNNER_KILL_MS 1000U
#define USE_STORAGE 1
#define USE_USB_SUPPORT 1
static int hook_status,hooks,logs,saves,unmounts;
static char trace[1024];
static void event(const char*s){strcat(trace,s);strcat(trace,",");}
static int get_ap_mode(void){return 0;}
static int check_if_file_exist(const char*p){assert(!strcmp(p,SCRIPT_SHUTDOWN));return 1;}
static int shutdown_hook_run(const char*p,int level,unsigned int run,unsigned int term,unsigned int hard){
 assert(!strcmp(p,SCRIPT_SHUTDOWN)&&level>=0&&level<=2&&run==30000U&&term==2000U&&hard==1000U);
 hooks++;event("hook");errno=hook_status<0?ETIMEDOUT:0;return hook_status;
}
static void logmessage(const char*tag,const char*fmt,...){assert(!strcmp(tag,"shutdown"));logs++;}
static int write_storage_to_mtd(void){saves++;event("save");return 0;}
#define stop_misc(...) event("misc")
#define stop_services(...) event("services")
#define safe_remove_all_stor_devices(...) event("detach")
#define stop_usb_printer_spoolers(...) event("printers")
#define stop_wan(...) event("wan")
#define stop_services_lan_wan(...) event("lan-services")
#define set_ipv4_forward(...) event("forward")
#define storage_save_time(...) event("time")
#define stop_8021x_all(...) event("8021x")
#define stop_wifi_all_wl(...) event("wifi-wl")
#define stop_wifi_all_rt(...) event("wifi-rt")
#define stop_logger(...) event("logger")
#define stop_lan(...) event("lan")
#define umount_rwfs_partition(...) (unmounts++,event("unmount"))
#define module_smart_unload(...) event("module")
#define LED_CONTROL(...) ((void)0)
'''
        code += function(source('trunk/user/rc/rc.c'), 'shutdown_router')
        code += '\nint main(int argc,char**argv){assert(argc==3);hook_status=atoi(argv[1]);shutdown_router(atoi(argv[2]));printf("{\\"hooks\\":%d,\\"logs\\":%d,\\"saves\\":%d,\\"unmounts\\":%d,\\"trace\\":\\"%s\\"}\\n",hooks,logs,saves,unmounts,trace);return 0;}\n'
        cfile = self.path / 'ordinary.c'; cfile.write_text(code)
        binary = self.path / 'ordinary'
        compiled = subprocess.run(['clang', '-std=gnu99', '-Wall', '-Wextra', '-Werror',
                                   '-Wno-unused-parameter', '-Wno-unused-variable', '-fsanitize=address,undefined',
                                   str(cfile), '-o', str(binary)], capture_output=True, text=True)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        for status in (0, -1, 256, 15):
            for level in (0, 1, 2):
                with self.subTest(status=status, level=level):
                    process = subprocess.run([str(binary), str(status), str(level)], capture_output=True, text=True, check=True)
                    result = json.loads(process.stdout)
                    self.assertEqual((result['hooks'],result['logs'],result['saves'],result['unmounts']), (1,int(status!=0),1,1))
                    trace = result['trace'].strip(',').split(',')
                    self.assertEqual(trace[:3] if level<2 else trace[:2], ['misc','services','hook'] if level<2 else ['misc','hook'])
                    self.assertLess(trace.index('hook'),trace.index('save'))
                    self.assertLess(trace.index('save'),trace.index('unmount'))


if __name__ == '__main__':
    unittest.main()
