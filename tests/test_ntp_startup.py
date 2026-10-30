#!/usr/bin/env python3
"""Real NTP startup/watchdog functions, real signals and inert DNS/process I/O."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_httpd_regressions import function, source

SOURCE_PATHS = {
    'ntpd.c': 'trunk/user/busybox/busybox-1.24.x/networking/ntpd.c',
    'ntp_startup.h': 'trunk/user/busybox/busybox-1.24.x/networking/ntp_startup.h',
    'watchdog.c': 'trunk/user/rc/watchdog.c',
    'fixture.c': 'tests/ntp_startup_fixture.c',
}
FUNCTIONS = {'ntpd.c': ('add_peers', 'ntp_init', 'ntp_first_reply'),
             'watchdog.c': ('ntpc_reap_launcher', 'refresh_ntp', 'is_ntpc_updated', 'ntpc_handler')}
CASE_NAMES = (
    'init-q-first-reply', 'init-q-success', 'init-noq-success', 'init-foreground-q-success', 'init-config-q-success',
    'init-resolver-production-timeout', 'init-resolver-ignored', 'init-resolver-blocked',
    'init-config-timeout', 'init-sigaction-fail', 'init-mask-fail',
    'refresh-inhibited', 'refresh-poststop-inhibited', 'refresh-fork-fail',
    'reap-exited', 'reap-echild', 'reap-eintr', 'reap-error', 'disabled-reaps',
    'timer-async-feed', 'refresh-busy-no-overlap', 'stop-resolving-no-pidfile',
    'refresh-server-fallback', 'refresh-server-alternation',
)


def generate(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('NTP source set differs')
    enum = re.search(r'enum\s*\{\s*OPT_n\s*=.*?\n\};', texts['ntpd.c'], re.S)
    if not enum:
        raise ValueError('NTP actual option enumeration missing')
    result = texts['fixture.c']
    fragments = {
        '/* NTP_STARTUP_HEADER */': texts['ntp_startup.h'],
        '/* NTP_OPTION_ENUM */': enum[0],
        '/* NTP_INIT_FUNCTIONS */': '\n\n'.join(function(texts['ntpd.c'], n) for n in FUNCTIONS['ntpd.c']),
        '/* NTP_WATCHDOG_FUNCTIONS */': '\n\n'.join(function(texts['watchdog.c'], n) for n in FUNCTIONS['watchdog.c']),
    }
    for marker, value in fragments.items():
        if result.count(marker) != 1:
            raise ValueError('NTP fixture marker missing/ambiguous: '+marker)
        result = result.replace(marker, value)
    return result


def source_texts():
    return {key: source(path) for key,path in SOURCE_PATHS.items()}


class NtpStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-ntp-')
        cls.directory = Path(cls.temp.name)
        cls.texts = source_texts()
        cls.generated = generate(cls.texts)
        cls.path = cls.directory/'probe.c'
        cls.path.write_text(cls.generated)
        cls.probes = []
        compiler = shutil.which('cc')
        if not compiler:
            raise RuntimeError('Native C compiler required')
        flags = ['-std=gnu99', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-variable']
        compiled=subprocess.run([compiler,*flags,str(cls.path),'-o',str(cls.directory/'native')],capture_output=True,text=True)
        if compiled.returncode: raise RuntimeError(compiled.stderr)
        cls.probes.append(cls.directory/'native')
        clang = shutil.which('clang')
        if clang:
            subprocess.run([clang,*flags,'-fsanitize=address,undefined','-fno-omit-frame-pointer',
                            str(cls.path),'-o',str(cls.directory/'sanitized')],check=True,capture_output=True)
            cls.probes.append(cls.directory/'sanitized')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, name):
        self.assertIn(name, CASE_NAMES)
        rows=[]
        for probe in self.probes:
            result=subprocess.run([str(probe),name],capture_output=True,text=True,timeout=16)
            self.assertEqual(result.returncode,0,(name,probe.name,result.stdout,result.stderr))
            self.assertNotIn('runtime error:', result.stderr)
            self.assertNotIn('ERROR: AddressSanitizer', result.stderr)
            row=json.loads(result.stdout)
            self.assertEqual(row['case'],name)
            rows.append(row)
        return rows

    def test_success_preserves_q_network_timer(self):
        for name in ('init-q-success','init-foreground-q-success','init-config-q-success'):
            for row in self.run_case(name):
                self.assertEqual(row['alarms'],[10,0,10,0])
                self.assertEqual(row['initialized'],1)

    def test_first_q_reply_rearms_fifty_seconds_only_once(self):
        for row in self.run_case('init-q-first-reply'):
            self.assertEqual(row['alarms'],[10,0,10,50])
            self.assertEqual(row['alarm_count'],4)

    def test_non_q_cancels_only_startup_budget(self):
        for row in self.run_case('init-noq-success'):
            self.assertEqual(row['alarms'],[10,0,0,0])
            self.assertEqual(row['alarm_count'],2)

    def test_real_production_ten_second_resolver_deadline(self):
        for row in self.run_case('init-resolver-production-timeout'):
            self.assertEqual(row['timed_out'],1)
            self.assertGreaterEqual(row['elapsed_ms'],9500)
            self.assertLess(row['elapsed_ms'],13000)

    def test_ignored_inherited_alarm_cannot_disable_deadline(self):
        self.run_case('init-resolver-ignored')

    def test_blocked_inherited_alarm_is_unblocked(self):
        self.run_case('init-resolver-blocked')

    def test_config_read_is_inside_startup_deadline(self):
        self.run_case('init-config-timeout')

    def test_signal_setup_failure_never_reaches_resolver(self):
        for name in ('init-sigaction-fail','init-mask-fail'):
            for row in self.run_case(name):
                self.assertEqual(row['resolver_reached'],0)
                self.assertEqual(row['status'],111<<8)

    def test_upgrade_inhibition_before_and_after_stop(self):
        for name in ('refresh-inhibited','refresh-poststop-inhibited'):
            self.run_case(name)

    def test_async_launch_failure_is_reported_without_owned_pid(self):
        self.run_case('refresh-fork-fail')

    def test_nonblocking_reap_and_error_do_not_reuse_live_pid(self):
        for name in ('reap-exited','reap-echild','reap-eintr','reap-error','disabled-reaps'):
            self.run_case(name)

    def test_hardware_feed_callback_continues_while_resolver_is_blocked(self):
        for row in self.run_case('timer-async-feed'):
            self.assertEqual(row['feeds'],6)
            self.assertEqual(row['launches'],1)
            self.assertLess(row['largest_feed_gap_ms'],750)

    def test_no_overlapping_owned_launcher_and_stop_before_pidfile(self):
        for name in ('refresh-busy-no-overlap','stop-resolving-no-pidfile'):
            self.run_case(name)

    def test_server_fallback_and_alternation_are_preserved(self):
        for name in ('refresh-server-fallback','refresh-server-alternation'):
            self.run_case(name)

    def test_generator_requires_actual_functions_and_all_markers(self):
        for key in ('ntpd.c','watchdog.c','ntp_startup.h','fixture.c'):
            self.assertTrue(hashlib.sha256(self.texts[key].encode()).hexdigest())
        bad=dict(self.texts, **{'fixture.c':self.texts['fixture.c'].replace('/* NTP_OPTION_ENUM */','')})
        with self.assertRaises(ValueError): generate(bad)
        bad=dict(self.texts, **{'watchdog.c':self.texts['watchdog.c'].replace('ntpc_reap_launcher(', 'removed_launcher(')})
        with self.assertRaises(ValueError): generate(bad)


if __name__ == '__main__':
    unittest.main()
