"""NOR admission checks use actual C bodies and an inert, independently asserted bus model."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import nor_admission_harness as h

ROOT = Path(__file__).resolve().parents[1]


class NorAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-nor-admission-')
        cls.base = Path(cls.temp.name)
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        cls.expected = dict(h.CASES)
        cls.current = cls.compile(cls.texts, 'current')
        cls.baseline = cls.compile(cls.texts, 'baseline', baseline=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, texts, name, baseline=False, compiler=None):
        source, binary = cls.base / (name + '.c'), cls.base / name
        source.write_text(h.generate_source(texts, baseline=baseline))
        command = [compiler or shutil.which('clang') or shutil.which('cc'),
                   '-std=gnu89', '-O1', '-g', '-Wall', '-Wextra', '-Werror']
        if compiler is None:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined',
                        '-fno-omit-frame-pointer']
        built = subprocess.run(command + [str(source), '-o', str(binary)],
                               capture_output=True, text=True, timeout=45)
        if built.returncode:
            raise AssertionError((name, built.stderr))
        return binary

    def row(self, name, binary=None):
        result = subprocess.run([str(binary or self.current), name],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, (name, result.stderr))
        self.assertEqual(result.stderr, '', name)
        return json.loads(result.stdout)

    def check(self, names):
        for name in names:
            with self.subTest(case=name):
                self.assertEqual(self.row(name), self.expected[name])

    def mutate(self, old, new, label):
        texts = dict(self.texts)
        body = h.extract(texts['nor'], 'spi_nor_lock_and_prep')
        self.assertEqual(body.count(old), 1)
        texts['nor'] = texts['nor'].replace(body, body.replace(old, new), 1)
        return self.compile(texts, label)

    def test_ready_and_transient_busy_read_write_sector_and_chip(self):
        self.check(('read-ready', 'read-busy', 'write-ready', 'write-busy',
                    'erase-ready', 'erase-busy', 'erase-chip-ready', 'erase-chip-busy'))

    def test_permanent_busy_and_status_error_reject_before_data_or_wren(self):
        self.check(('read-permanent', 'read-status-error', 'write-permanent',
                    'write-status-error', 'erase-permanent', 'erase-status-error',
                    'erase-chip-permanent'))
        for name in ('read-permanent', 'write-permanent', 'erase-permanent'):
            row = self.row(name)
            self.assertEqual((row['mutations'], row['wren_calls'], row['reads']), (0, 0, 0))

    def test_optional_prepare_ownership_and_error_pairing(self):
        self.check(('read-prepare-error', 'write-prepare-error', 'erase-prepare-error',
                    'read-no-prepare-busy', 'read-no-prepare-permanent'))

    def test_fsr_and_jiffies_wrap_preserve_existing_ready_policy(self):
        self.check(('read-fsr', 'read-fsr-error', 'read-wrap-permanent'))

    def test_lock_and_unlock_use_same_admission(self):
        self.check(('lock-op-busy', 'unlock-op-permanent'))

    def test_accepted_failed_program_is_settled_before_next_operation(self):
        self.check(('accepted-read', 'accepted-write', 'accepted-erase'))
        for name in ('accepted-read', 'accepted-write', 'accepted-erase'):
            row = self.row(name)
            self.assertEqual(row['result'], -5)
            self.assertEqual((row['commands_while_busy'], row['read_while_busy']), (0, 0))

    def test_fixed_previous_admission_demonstrates_ignored_commands_and_busy_reads(self):
        self.assertEqual(hashlib.sha256(h.BASELINE_ADMISSION.encode()).hexdigest(),
                         h.BASELINE_ADMISSION_SHA256)
        old = self.row('accepted-read', self.baseline)
        self.assertEqual((old['result'], old['next_result'], old['read_while_busy']), (-5, 0, 1))
        self.assertEqual(old['data0'], 0xff)
        for name in ('accepted-write', 'accepted-erase'):
            with self.subTest(case=name):
                old = self.row(name, self.baseline)
                self.assertEqual((old['result'], old['next_result'], old['mutations']), (-5, 0, 1))
                self.assertEqual(old['commands_while_busy'], 2)
                self.assertNotEqual(old, self.expected[name])

    def test_removed_ready_gate_negative_control_is_detected(self):
        binary = self.mutate('ret = spi_nor_wait_till_ready(nor);', 'ret = 0;', 'no-ready')
        row = self.row('write-busy', binary)
        self.assertGreater(row['commands_while_busy'], 0)
        self.assertEqual(row['mutations'], 0)
        self.assertNotEqual(row, self.expected['write-busy'])

    def test_failed_ready_must_unprepare_before_mutex_release(self):
        binary = self.mutate('nor->unprepare(nor, ops);', '(void)nor;', 'no-unprepare')
        result = subprocess.run([str(binary), 'read-permanent'], capture_output=True,
                                text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)

    def test_optional_operation_wrappers_retire_the_exact_prepared_operation(self):
        self.check(('lock-wrapper-ready', 'unlock-wrapper-ready', 'islocked-wrapper-ready'))
        for function, case in (('spi_nor_lock', 'lock-wrapper-ready'),
                               ('spi_nor_unlock', 'unlock-wrapper-ready'),
                               ('spi_nor_is_locked', 'islocked-wrapper-ready')):
            with self.subTest(function=function):
                old = h.BASELINE_OPERATION_BODIES[function]
                self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),
                                 h.BASELINE_OPERATION_SHA256[function])
                texts = dict(self.texts)
                current = h.extract(texts['nor'], function)
                texts['nor'] = texts['nor'].replace(current, old, 1)
                binary = self.compile(texts, function + '-old-op')
                result = subprocess.run([str(binary), case], capture_output=True,
                                        text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)

    def test_exact_function_inputs_macros_and_enum_are_bound(self):
        actual = h.actual_functions(self.texts)
        self.assertEqual(len(actual), 20)
        generated = h.generate_source(self.texts)
        for name, row in actual.items():
            self.assertEqual(generated.count(row['body']), 1, name)
        self.assertEqual(len(h.CASES), 31)
        self.assertEqual(len(set(h.CASE_NAMES)), 31)
        for key in h.SOURCE_PATHS:
            bad = dict(self.texts)
            del bad[key]
            with self.assertRaises(ValueError): h.generate_source(bad)
        bad = dict(self.texts, nor=self.texts['nor'] + '\n' + actual['spi_nor_read']['body'])
        with self.assertRaises(ValueError): h.generate_source(bad)
        for name in h.MACROS:
            bad = dict(self.texts)
            import re
            bad['header'] = re.sub(r'(^#define[ \t]+' + name + r'[ \t]+)[^\n]+',
                                   r'\g<1>0xee', bad['header'], count=1, flags=re.M)
            with self.subTest(macro=name), self.assertRaises(ValueError): h.generate_source(bad)

    def test_gcc_strict_compile_and_every_case(self):
        compiler = shutil.which('gcc-16') or shutil.which('gcc-15')
        if not compiler and os.uname().sysname == 'Linux':
            compiler = shutil.which('gcc')
        if not compiler: raise RuntimeError('GCC is required for strict NOR admission fixture')
        binary = self.compile(self.texts, 'gcc-strict', compiler=compiler)
        for name, expected in h.CASES:
            with self.subTest(case=name): self.assertEqual(self.row(name, binary), expected)


if __name__ == '__main__': unittest.main()
