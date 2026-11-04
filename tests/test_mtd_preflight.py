"""Current actual MTD preflight/main capacity checks; no device/proc access."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import mtd_preflight_harness as h

ROOT = Path(__file__).resolve().parents[1]


class MtdPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-mtd-preflight-')
        cls.base = Path(cls.temp.name).resolve()
        (cls.base / 'image').write_bytes(b'ordinary non-firmware fixture\n' * 2500)
        (cls.base / 'device').write_bytes(bytes(131072))
        cls.texts = {name: (ROOT / path).read_text() for name, path in h.SOURCE_PATHS.items()}
        cls.code = h.generate_source(cls.texts, cls.base)
        source = cls.base / 'current.c'
        source.write_text(cls.code)
        cls.binary = cls.base / 'current'
        compiler = shutil.which('clang') or shutil.which('cc')
        cls.flags = ['-std=gnu89', '-O1', '-Wall', '-Wextra', '-Werror',
                     '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-sign-compare']
        run = subprocess.run([compiler, *cls.flags, '-fsanitize=address,undefined', '-g',
                              str(source), '-o', str(cls.binary)], capture_output=True, text=True, timeout=30)
        if run.returncode:
            raise AssertionError(run.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def row(self, case, binary=None):
        self.assertIn(case, h.CASES)
        size = 70000 if case == 'configured-k2p' else 64 if case == 'resume-offset-refused' else 24
        (self.base / 'image').write_bytes((b'ordinary fixture' * ((size + 15) // 16))[:size])
        run = subprocess.run([str(binary or self.binary), case], capture_output=True,
                              text=True, timeout=5)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn('AddressSanitizer', run.stderr)
        self.assertNotIn('runtime error:', run.stderr)
        row = json.loads(run.stdout.splitlines()[-1])
        self.assertEqual(row['bad_range'], 0)
        self.assertEqual(row['live_fds'], 0)
        self.assertEqual(row['name_allocations'], 0)
        self.assertEqual(row['late_allocations'], 0)
        return row

    def before_mutation(self, row):
        self.assertNotEqual(row['returncode'], 0)
        self.assertEqual((row['unlocks'], row['erases'], row['writes']), (0, 0, 0))
        self.assertNotIn('sync', row['trace'].split(','))

    def test_exact_current_functions_are_embedded_without_rewriting(self):
        for name in h.FUNCTIONS:
            self.assertEqual(self.code.count(h.function(self.texts['mtd'], name)), 1)
        self.assertEqual(len(h.CASES), 22)
        self.assertEqual(set(h.source_hashes(self.texts)), set(h.FUNCTIONS))

    def test_configured_64k_scratch_and_preerase_path_remain_compatible(self):
        row = self.row('configured-k2p')
        self.assertEqual(row['returncode'], 0)
        self.assertEqual((row['allocations'], row['allocation_bytes'], row['capacity']), (1, 65536, 65536))
        self.assertGreater(row['writes'], 0)
        trace = row['trace'].split(',')
        self.assertLess(trace.index('scratch-allocation'), trace.index('sync'))
        self.assertLess(trace.index('scratch-allocation'), trace.index('pre-erase'))

    def test_all_targets_are_checked_before_one_maximum_scratch_allocation(self):
        for case in ('small-large', 'large-small', 'resume-larger', 'name-allocation-refused'):
            with self.subTest(case=case):
                row = self.row(case)
                self.assertEqual(row['returncode'], 0)
                self.assertEqual((row['allocations'], row['allocation_bytes'], row['capacity']), (1, 64, 64))
                trace = row['trace'].split(',')
                self.assertEqual(trace[:5], ['metadata-open', 'metadata-close', 'metadata-open',
                                             'metadata-close', 'scratch-allocation'])
                self.assertLess(trace.index('scratch-allocation'), trace.index('pre-erase'))
        resumed = self.row('resume-larger')
        self.assertEqual(resumed['writer_ready'], 2)

    def test_scratch_allocation_failures_cannot_reach_main_preerase_even_with_force(self):
        for case in ('scratch-refused', 'existing-scratch-growth-refused'):
            with self.subTest(case=case):
                row = self.row(case)
                self.before_mutation(row)
                self.assertEqual(row['allocation_bytes'], 64)
                self.assertEqual(row['image_reads'], 0)
                self.assertEqual(row['old_allocation_preserved'], case == 'existing-scratch-growth-refused')

    def test_open_and_close_failures_refuse_before_allocation_and_preerase(self):
        for case in ('first-open-error', 'second-open-error', 'first-close-error', 'second-close-error'):
            with self.subTest(case=case):
                row = self.row(case)
                self.before_mutation(row)
                self.assertEqual(row['allocations'], 0)
                self.assertEqual(row['opens'] - row['closes'], 1 if 'open-error' in case else 0)

    def test_invalid_or_unrepresentable_preflight_inputs_fail_before_mutation(self):
        for case in ('zero-erase', 'negative-erase', 'null-target', 'overlong-target'):
            with self.subTest(case=case):
                row = self.row(case)
                self.before_mutation(row)
                self.assertEqual(row['allocations'], 0)
                if 'target' in case:
                    self.assertEqual(row['opens'], 0)

    def test_writer_checks_reopened_geometry_before_image_io_or_device_write(self):
        row = self.row('writer-geometry-growth')
        self.assertNotEqual(row['returncode'], 0)
        self.assertEqual((row['writes'], row['writer_ready']), (0, 0))
        self.assertEqual(row['image_reads'], 1)  # Only the real main's initial image_check.

    def test_actual_writer_refuses_missing_or_insufficient_scratch_without_dereference(self):
        for case in ('writer-null-buffer', 'writer-short-capacity', 'writer-negative-length',
                     'writer-carried-length', 'writer-zero-erase'):
            with self.subTest(case=case):
                row = self.row(case)
                self.assertNotEqual(row['returncode'], 0)
                self.assertEqual((row['image_reads'], row['writes'], row['erases'], row['writer_ready']), (0, 0, 0, 0))

    def test_partial_transition_never_treats_capacity_as_valid_carried_data(self):
        row = self.row('resume-offset-refused')
        self.assertNotEqual(row['returncode'], 0)
        self.assertEqual(row['capacity'], 128)
        self.assertEqual((row['writer_ready'], row['writes'], row['written_bytes']), (2, 1, 16))

    def test_gnu89_warning_clean_current_functions_and_all_cases(self):
        compiler = shutil.which('gcc-16') or shutil.which('gcc-15') or shutil.which('gcc') or shutil.which('cc')
        macros = subprocess.run([compiler, '-dM', '-E', '-x', 'c', '-'], input='',
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(macros.returncode, 0, macros.stderr)
        self.assertIn('#define __GNUC__ ', macros.stdout)
        self.assertNotIn('#define __clang__ ', macros.stdout)
        source = self.base / 'gnu-current.c'
        source.write_text(self.code)
        binary = self.base / 'gnu-current'
        run = subprocess.run([compiler, *self.flags, str(source), '-o', str(binary)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stderr, '')
        for case in h.CASES:
            with self.subTest(case=case):
                self.row(case, binary)


if __name__ == '__main__':
    unittest.main()
