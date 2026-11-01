#!/usr/bin/env python3
"""Actual rc upgrade state machine with synthetic files and inert backends."""
import fcntl
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_httpd_regressions import source
import test_storage_regressions as storage_fixture
from upgrade_gate_harness import compile_harness, compile_consumer


class UpgradeStorageGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-upgrade-gate-code-')
        cls.root = Path(cls.temp.name)
        cls.binary = compile_harness(cls.root)
        cls.superset_binary = compile_harness(cls.root, superset=True)
        cls.queue_binary = compile_consumer(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def prepare_fixture(self, marker=False, trusted_mode=0o755):
        private = self.root / 'private'
        if private.exists():
            shutil.rmtree(private)
        private.mkdir(mode=0o700)
        writer = self.root / 'rom-writer'
        writer.write_bytes(b'SYNTHETIC-INERT-WRITER\n' * 319)
        writer.chmod(trusted_mode)
        (self.root / 'hardware-fixture').write_bytes(b'')
        if marker:
            (private / 'firmware-upgrade-inhibit').touch(mode=0o600)

    def run_case(self, first=0, second=0, hook=False, hook_status=0, kind=1,
                 mask=127, stop_fail=-1, start_fail=-1, hardware=0, stage_fault=0,
                 mode='flash', marker=False, trusted_mode=0o755, pin_failure=False):
        self.prepare_fixture(marker, trusted_mode)
        result = subprocess.run([str(self.binary), mode, str(first), str(second), str(int(hook)),
                                 str(hook_status), str(kind), str(mask), str(stop_fail), str(start_fail),
                                 str(hardware), str(stage_fault), str(int(pin_failure))], check=True, capture_output=True,
                                text=True, timeout=5)
        return json.loads(result.stdout)

    def assert_before_quiesce(self, result):
        self.assertEqual(result['phase'], 0)
        self.assertEqual(result['writes'], 0)
        self.assertEqual(result['stops'], [0] * 7)
        self.assertEqual(result['starts'], [0] * 7)
        self.assertEqual(result['hardware_opens'], 0)
        self.assertEqual(result['reboots'], 0)
        self.assertEqual(result['inhibited'], 0)
        self.assertEqual(result['munlocks'], 0)

    def assert_safe_recovery(self, result, mask=127):
        self.assertEqual(result['phase'], 0)
        self.assertEqual(result['reboots'], 0)
        self.assertEqual(result['inhibited'], 0)
        self.assertEqual(result['running'], [int(bool(mask & (1 << i))) for i in range(7)])
        self.assertEqual(result['starts'], [int(bool(mask & (1 << i))) for i in range(7)])
        self.assertEqual((result['mlocks'], result['munlocks']), (1, 1))

    def test_save_propagates_success_exit_signal_and_system_failure(self):
        for status in (0, 256, -1, 9, 15, 36608):
            with self.subTest(status=status):
                self.assertEqual(self.run_case(first=status, mode='status')['status'], status)

    def test_first_save_failures_do_not_run_hook_or_quiesce(self):
        for status in (256, -1, 9, 15, 36608):
            with self.subTest(status=status):
                result = self.run_case(first=status, hook=True)
                self.assert_before_quiesce(result)
                self.assertEqual((result['saves'], result['hooks'], result['time_calls']), (1, 0, 1))

    def test_busy_actual_storage_lock_aborts_before_quiesce(self):
        storage_fixture.StorageRegression.setUpClass()
        fixture = storage_fixture.StorageRegression('runTest')
        fixture.setUp()
        try:
            lock = fixture.tmp / '.storage_operation'
            lock.mkdir(mode=0o700)
            with (lock / 'lock').open('w') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                failed = fixture.run_script('save')
            self.assertEqual(failed.returncode, 1)
            self.assertFalse(fixture.flash_calls.exists())
            result = self.run_case(first=failed.returncode << 8, hook=True)
            self.assert_before_quiesce(result)
            self.assertEqual(result['hooks'], 0)
        finally:
            fixture.tearDown()
            storage_fixture.StorageRegression.tearDownClass()

    def test_hook_failure_and_second_save_failure_do_not_quiesce(self):
        for status in (256, -1, 15):
            for kwargs in ({'hook_status': status}, {'second': status}):
                with self.subTest(kwargs=kwargs):
                    result = self.run_case(hook=True, **kwargs)
                    self.assert_before_quiesce(result)
                    self.assertEqual(result['hooks'], 1)

    def test_default_comment_only_shutdown_template_exits_zero(self):
        script = source('trunk/user/scripts/mtd_storage.sh')
        template = script.split('cat > "$script_shutd" <<EOF', 1)[1].split('\nEOF', 1)[0]
        result = subprocess.run(['sh'], input=template, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_int_save_header_prototype(self):
        self.assertIn('int write_storage_to_mtd(void);', source('trunk/user/rc/rc.h'))

    def test_private_trusted_writer_failure_stops_nothing(self):
        for options in ({'trusted_mode': 0o777}, {'trusted_mode': 0o644},
                        *({'stage_fault': mode} for mode in (1, 2, 3, 4))):
            with self.subTest(options=options):
                result = self.run_case(**options)
                self.assert_before_quiesce(result)
                self.assertEqual([p.name for p in (self.root / 'private').iterdir()], ['firmware-action.lock'])
        self.assert_safe_recovery(self.run_case(stage_fault=5))

    def test_initially_absent_watchdog_is_rejected_without_hardware_open(self):
        result = self.run_case(mask=126)
        self.assert_before_quiesce(result)
        self.assertEqual(result['running'][0], 0)

    def test_memory_pinning_failure_aborts_before_inhibit_quiesce_or_writer(self):
        result = self.run_case(pin_failure=True)
        self.assert_before_quiesce(result)
        self.assertEqual((result['mlocks'], result['munlocks']), (1, 0))

    def test_safe_prewrite_restores_only_previously_running_daemons(self):
        for mask in (1, 3, 43, 127):
            with self.subTest(mask=mask):
                result = self.run_case(mask=mask)
                self.assert_safe_recovery(result, mask)
                self.assertEqual(result['writes'], 1)
                self.assertEqual(result['hardware_disables'], 1)
                trace = result['trace'].strip(',').split(',')
                self.assertLess(trace.index('hardware-disable'), trace.index('writer'))
                self.assertEqual(trace[-2:], ['start:watchdog', 'unpin'])
                self.assertEqual([p.name for p in (self.root / 'private').iterdir()], ['firmware-action.lock'])

    def test_storage_usb_superset_compiles_without_detach_or_unknown_service_restart(self):
        original = self.binary
        try:
            self.binary = self.superset_binary
            self.assert_safe_recovery(self.run_case(mask=43), mask=43)
        finally:
            self.binary = original

    def test_hook_edits_saved_before_quiesce_and_safe_recovery(self):
        result = self.run_case(hook=True)
        self.assert_safe_recovery(result)
        self.assertEqual((result['saves'], result['hooks']), (2, 1))
        self.assertEqual(result['snapshot_revisions'], [0, 1])
        self.assertEqual(result['trace'].split(',')[:4], ['time', 'save', 'hook', 'save'])

    def test_quiesce_failure_does_not_open_hardware_or_run_writer(self):
        for index in (0, 1, 6):
            with self.subTest(index=index):
                result = self.run_case(stop_fail=index)
                self.assertEqual(result['phase'], 0)
                self.assertEqual(result['writes'], 0)
                self.assertEqual(result['hardware_opens'], 0)
                self.assertEqual(result['running'], [1] * 7)
                self.assertEqual(result['starts'][index], 0)
                self.assertEqual(result['inhibited'], 0)

    def test_hardware_open_owner_type_disable_and_close_failure_never_write(self):
        for mode in (1, 2, 3, 4, 5):
            with self.subTest(mode=mode):
                result = self.run_case(hardware=mode)
                self.assert_safe_recovery(result)
                self.assertEqual(result['writes'], 0)
                self.assertEqual(result['hardware_opens'], 1)
                self.assertEqual(result['hardware_closes'], int(mode != 1))
                self.assertEqual(result['hardware_disables'], int(mode in (4, 5)))

    def test_recovery_start_failure_is_detected_by_pid_not_success_return(self):
        result = self.run_case(start_fail=0)
        self.assertEqual(result['phase'], 0)
        self.assertEqual(result['inhibited'], 0)
        self.assertEqual(result['running'][0], 0)
        self.assertEqual(result['starts'][0], 1)
        self.assertGreaterEqual(result['logs'], 3)
        self.assertEqual(result['criticals'], 1)
        self.assertEqual(result['reboots'], 0)

    def test_unknown_signal_exec_missing_stale_unsafe_and_malformed_results_never_restore(self):
        for kind in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22):
            with self.subTest(kind=kind):
                result = self.run_case(kind=kind)
                self.assertEqual(result['phase'], 1)
                self.assertEqual(result['writes'], 1)
                self.assertEqual(result['starts'], [0] * 7)
                self.assertEqual(result['running'], [0] * 7)
                self.assertEqual(result['inhibited'], 1)
                self.assertEqual(result['reboots'], 0)
                self.assertEqual(result['criticals'], 1)
                self.assertEqual((result['mlocks'], result['munlocks']), (1, 0))
                self.assertTrue(list((self.root / 'private').glob('fwupgrade.*/writer')))

    def test_verified_normal_exit_requests_direct_reboot_without_recovery(self):
        result = self.run_case(kind=0)
        self.assertEqual((result['phase'], result['writes'], result['reboots']), (1, 1, 1))
        self.assertEqual(result['starts'], [0] * 7)
        self.assertEqual(result['inhibited'], 1)
        self.assertEqual(result['criticals'], 1)  # inert reboot returns: no success claim
        self.assertEqual(result['syncs'], 2)
        self.assertEqual((result['mlocks'], result['munlocks']), (1, 0))

    def test_existing_inhibit_refuses_retry_before_save_hook_or_stops(self):
        result = self.run_case(marker=True, hook=True)
        self.assertEqual((result['phase'], result['saves'], result['hooks'], result['writes']), (1, 0, 0, 0))
        self.assertEqual(result['stops'], [0] * 7)

    def test_watchdog_start_and_wan_notify_do_not_rearm_while_inhibited(self):
        result = self.run_case(mode='guard', marker=True, mask=0)
        self.assertNotEqual(result['result'], 0)
        self.assertEqual(result['execs'], 0)
        baseline = self.run_case(mode='guard', mask=0)
        self.assertEqual(baseline['result'], 0)
        self.assertEqual(baseline['execs'], 2)

    def test_watchdog_main_refuses_existing_or_during_daemonize_inhibit_before_hardware_arm(self):
        for mode, marker, daemon_calls in [('mainguard', True, 0), ('mainguard-late', False, 1)]:
            with self.subTest(mode=mode):
                result = self.run_case(mode=mode, marker=marker)
                self.assertNotEqual(result['result'], 0)
                self.assertEqual(result['daemon'], daemon_calls)
                self.assertEqual(result['hardware_inits'], 0)

    def queue_case(self, later=1, first=256, second=0, hook=False, hook_status=0, kind=1, rounds=1):
        self.prepare_fixture()
        with tempfile.TemporaryDirectory(prefix='k2p-upgrade-queue-') as temp:
            result = subprocess.run([str(self.queue_binary), temp, str(later), str(first), str(second),
                                     str(int(hook)), str(hook_status), str(kind), str(rounds)],
                                    check=True, text=True, capture_output=True, timeout=5)
        return json.loads(result.stdout)

    def test_consumer_preflight_and_safe_writer_abort_continue_to_later_marker(self):
        for options in ({'first': 256}, {'first': 0, 'hook': True, 'hook_status': 256},
                        {'first': 0, 'second': 256, 'hook': True}, {'first': 0}):
            with self.subTest(options=options):
                result = self.queue_case(**options)
                self.assertEqual((result['events'], result['remaining'], result['recognized_actions']), (2, 0, 1))
                self.assertEqual((result['inhibited'], result['watchdog']), (0, 1))

    def test_consumer_safe_abort_rearms_and_drains_more_than_ten_markers(self):
        for first in (0, 256):
            result = self.queue_case(first=first, later=25, rounds=3)
            self.assertEqual((result['events'], result['signals'], result['remaining']), (26, 2, 0))
            self.assertEqual(result['recognized_actions'], 1)

    def test_consumer_unknown_and_reboot_return_hold_this_and_future_batches(self):
        for kind in (0, 2, 3, 6):
            with self.subTest(kind=kind):
                result = self.queue_case(first=0, later=25, kind=kind, rounds=3)
                self.assertEqual((result['events'], result['signals'], result['remaining'], result['writes']), (1, 0, 25, 1))
                self.assertEqual((result['recognized_actions'], result['inhibited'], result['watchdog_restarts']), (0, 1, 0))


if __name__ == '__main__':
    unittest.main()
