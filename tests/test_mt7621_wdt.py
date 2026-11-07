"""Actual MT762x stop/core ioctl, inert MMIO, old body and selected real mutex schedules."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import mt7621_wdt_harness as h

ROOT = Path(__file__).resolve().parents[1]


class Mt7621WatchdogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='mt7621-wdt-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        cls.code = h.generate_source(cls.texts)
        cls.compilers = [('gcc', shutil.which('gcc-16') or shutil.which('gcc')),
                         ('clang', shutil.which('clang'))]
        for name, compiler in cls.compilers:
            if not compiler:
                raise AssertionError('GNU GCC and Clang required')
            version = subprocess.check_output([compiler, '--version'], text=True, timeout=10)
            if name == 'gcc' and ('Free Software Foundation' not in version or 'clang' in version.lower()):
                raise AssertionError('True GNU GCC required')
        cls.binaries = cls.compile_code(cls.code, 'current')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile_code(cls, code, label):
        source = cls.directory / (label + '.c')
        source.write_text(code)
        binaries = []
        for name, compiler in cls.compilers:
            binary = cls.directory / (label + '-' + name)
            flags = ['-std=gnu99', '-Os', '-pthread', '-Wall', '-Wextra', '-Werror',
                     '-Wno-unused-parameter', '-Wno-implicit-fallthrough']
            if name == 'clang':
                flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined']
            result = subprocess.run([compiler, *flags, str(source), '-o', str(binary)],
                                    capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(result.stderr)
            binaries.append(binary)
        return binaries

    def result(self, binary, name):
        run = subprocess.run([str(binary), name], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stderr, '')
        return json.loads(run.stdout)

    def rows(self, names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(binary=binary.name, case=name):
                    self.assertEqual(self.result(binary, name), h.EXPECTED_ROWS[name])

    def test_whole_driver_stop_reports_normal_stuck_and_dropped_disable_write(self):
        self.rows(h.CASE_NAMES[:4])

    def test_real_ioctl_preserves_error_and_active_state_until_retry_succeeds(self):
        self.rows(('disable-normal', 'disable-stuck', 'disable-droppedwrite',
                   'disable-stuck-retry', 'disable-dropped-retry',
                   'disable-enable', 'disable-enable-stuck',
                   'disable-preserve-flags', 'disable-stuck-preserve-flags'))

    def test_core_inactive_nowayout_unregister_and_user_access_boundaries(self):
        self.rows(('disable-inactive', 'disable-inactive-hardware-enabled',
                   'disable-nowayout', 'disable-unregistered', 'disable-bad-user',
                   'noop-options', 'enable-inactive', 'enable-active', 'enable-unregistered'))
        # This is the existing core's software-state boundary, not a hardware
        # disarm assertion. The inactive wrapper never calls the driver.
        self.assertEqual(h.EXPECTED_ROWS['disable-inactive-hardware-enabled']['enabled'], 1)
        self.assertEqual(h.EXPECTED_ROWS['disable-inactive-hardware-enabled']['reads'], 0)

    def test_selected_real_mutex_schedules_serialize_stop_retry_and_enable(self):
        self.rows(h.CASE_NAMES[22:26])

    def test_whole_probe_rejects_reset_stop_and_registration_failures(self):
        self.rows(h.CASE_NAMES[26:])
        for name in ('probe-reset-error', 'probe-reset-defer', 'probe-stuck', 'probe-droppedwrite', 'probe-declared-missing-provider'):
            self.assertEqual(h.EXPECTED_ROWS[name]['register_calls'], 0)
            # Failing probe is not a guarantee that the hardware was stopped.
            self.assertEqual(h.EXPECTED_ROWS[name]['enabled'], 1)

    def test_complete_function_manifest_and_explicit_non_hardware_boundaries(self):
        self.assertEqual((len(h.FUNCTION_SOURCES), len(h.CASE_NAMES)), (19, 37))
        self.assertEqual(set(h.CASE_NAMES), set(h.EXPECTED_ROWS))
        self.assertEqual(set(h.function_manifest(self.texts)), set(h.FUNCTION_SOURCES))
        self.assertEqual(h.source_only_manifest(self.texts), {})
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.code.count(h.function(self.texts[key], name)), 1)
        for key in ('real_watchdog_ioctl_and_stop_wrapper',
                    'selected_pthread_mutex_schedules_not_kernel_scheduling',
                    'inert_mmio_not_actual_hardware_or_bus_posting',
                    'inactive_core_success_does_not_recheck_hardware',
                    'only_future_booted_fixed_kernel_gets_readback',
                    'legacy_running_driver_and_upgrade_bridge_not_proven',
                    'inert_probe_reset_callback_has_no_hardware_effect',
                    'probe_failure_may_leave_hardware_running'):
            self.assertIs(h.MODEL_VARIANT[key], True)
        self.assertIn('if (err == 0)\n\t\tclear_bit(WDOG_ACTIVE', h.function(self.texts['core'], 'watchdog_stop'))
        self.assertIn('if (err < 0)\n\t\t\t\treturn err;', h.function(self.texts['core'], 'watchdog_ioctl'))

    def test_ambiguous_source_unknown_case_and_changed_fixture_are_rejected(self):
        with self.assertRaises(ValueError):
            h.generate_source({})
        with self.assertRaises(ValueError):
            h.generate_source(self.texts, baseline=1)
        with mock.patch.object(h, 'BASELINE_BODY', h.BASELINE_BODY + ' '), self.assertRaises(ValueError):
            h.generate_source(self.texts, baseline=True)
        for key, name in (('driver', 'mt762x_wdt_stop'), ('core', 'watchdog_ioctl')):
            wrong = dict(self.texts)
            wrong[key] += '\n' + h.function(wrong[key], name)
            with self.assertRaises(ValueError):
                h.generate_source(wrong)
        for binary in self.binaries:
            run = subprocess.run([str(binary), 'unknown'], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(run.stdout, '')

    def reject(self, code, cases, label):
        for binary in self.compile_code(code, label):
            for name in cases:
                with self.subTest(control=label, binary=binary.name, case=name):
                    self.assertNotEqual(self.result(binary, name), h.EXPECTED_ROWS[name])

    def test_pinned_f9_real_stop_is_a_valid_false_success_negative_control(self):
        raw = (ROOT / h.BASELINE_FIXTURE_PATH).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), h.BASELINE_FIXTURE_SHA256)
        fixture = json.loads(raw)
        self.assertEqual(fixture, {'source_commit': h.BASELINE_COMMIT,
                                  'source_path': h.SOURCE_PATHS['driver'],
                                  'functions': {name: {'body': body, 'sha256': h.BASELINE_FUNCTIONS_SHA256[name]}
                                                for name, body in h.BASELINE_FUNCTIONS.items()}})
        old = subprocess.check_output(['git', 'show', h.BASELINE_COMMIT + ':' + h.SOURCE_PATHS['driver']],
                                      cwd=ROOT, text=True, timeout=10)
        body = h.function(old, 'mt762x_wdt_stop')
        self.assertEqual(body, h.BASELINE_BODY)
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), h.BASELINE_SHA256)
        probe = h.function(old, 'mt762x_wdt_probe')
        self.assertEqual(probe, h.BASELINE_PROBE_BODY)
        self.assertEqual(hashlib.sha256(probe.encode()).hexdigest(), h.BASELINE_PROBE_SHA256)
        old_code = h.generate_source(self.texts, baseline=True)
        self.assertEqual(old_code.count(body), 1)
        for binary in self.compile_code(old_code, 'f9-real-stop'):
            direct = self.result(binary, 'driver-stuck')
            self.assertEqual((direct['ret'], direct['enabled'], direct['active'], direct['reads']), (0, 1, 1, 1))
            for name in ('disable-stuck', 'disable-droppedwrite'):
                actual = self.result(binary, name)
                self.assertEqual((actual['ret'], actual['enabled'], actual['active'], actual['reads']), (0, 1, 0, 1))
                self.assertNotEqual(actual, h.EXPECTED_ROWS[name])
            for name in ('probe-normal', 'probe-reset-error', 'probe-register-error', 'probe-stuck'):
                actual = self.result(binary, name)
                self.assertEqual((actual['ret'], actual['enabled'], actual['active'], actual['register_calls']), (0, 1, 0, 1))
                self.assertNotEqual(actual, h.EXPECTED_ROWS[name])

    def test_readback_and_core_error_propagation_mutants_are_rejected(self):
        readback = 'if (rt_wdt_r32(TIMER_REG_TMR1CTL) & TMR1CTL_ENABLE)\n\t\treturn -EIO;'
        self.assertEqual(self.code.count(readback), 1)
        self.reject(self.code.replace(readback, 'if (0)\n\t\treturn -EIO;'),
                    ('driver-stuck', 'disable-droppedwrite'), 'no-readback')
        self.reject(self.code.replace(readback, 'if (rt_wdt_r32(TIMER_REG_TMR1CTL) & TMR1CTL_ENABLE)\n\t\treturn 0;'),
                    ('disable-stuck',), 'ignore-readback')
        wrapper = h.function(self.texts['core'], 'watchdog_stop')
        mutated = wrapper.replace('if (err == 0)\n\t\tclear_bit(WDOG_ACTIVE', 'if (1)\n\t\tclear_bit(WDOG_ACTIVE')
        self.assertNotEqual(wrapper, mutated)
        self.reject(self.code.replace(wrapper, mutated), ('disable-stuck-retry',), 'clear-active-on-failure')
        ioctl = h.function(self.texts['core'], 'watchdog_ioctl')
        before = 'err = watchdog_stop(wdd);\n\t\t\tif (err < 0)\n\t\t\t\treturn err;'
        self.assertEqual(ioctl.count(before), 1)
        mutated = ioctl.replace(before, 'err = watchdog_stop(wdd);\n\t\t\tif (err < 0)\n\t\t\t\treturn 0;')
        self.reject(self.code.replace(ioctl, mutated), ('disable-stuck',), 'swallow-ioctl-error')

    def test_probe_reset_stop_and_registration_error_mutants_are_rejected(self):
        probe = h.function(self.texts['driver'], 'mt762x_wdt_probe')
        reset = 'ret = device_reset(&pdev->dev);\n\t\tif (ret)\n\t\t\treturn ret;'
        stop = 'ret = mt762x_wdt_stop(&mt762x_wdt_dev);\n\tif (ret)\n\t\treturn ret;'
        self.assertEqual(probe.count(reset), 1)
        self.assertEqual(probe.count(stop), 1)
        for label, before, after, cases in (
            ('ignored-probe-reset', reset, 'ret = device_reset(&pdev->dev);', ('probe-reset-error', 'probe-reset-defer', 'probe-declared-missing-provider')),
            ('always-reset', 'if (of_find_property(pdev->dev.of_node, "resets", NULL))', 'if (1)', ('probe-normal',)),
            ('missing-probe-stop', stop, 'ret = 0;', ('probe-normal', 'probe-stuck')),
            ('ignored-probe-stop', stop, 'ret = mt762x_wdt_stop(&mt762x_wdt_dev);', ('probe-stuck',)),
            ('ignored-probe-register', '\treturn ret;\n}', '\treturn 0;\n}', ('probe-register-error',)),
        ):
            mutated = probe.replace(before, after)
            self.assertNotEqual(probe, mutated)
            self.reject(self.code.replace(probe, mutated), cases, label)


if __name__ == '__main__':
    unittest.main()
