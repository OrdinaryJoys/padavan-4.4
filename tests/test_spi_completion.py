#!/usr/bin/env python3
"""Real kernel function bodies with private, inert SPI/user-copy backends."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import spi_completion_harness as harness

REPOSITORY = Path(__file__).resolve().parents[1]

class SPICompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='k2p-spi-completion-')
        cls.build = Path(cls.temporary.name).resolve()
        cls.texts = {key:(REPOSITORY/path).read_text() for key,path in harness.SOURCE_PATHS.items()}
        cls.expected = dict(harness.CASES)
        cc = shutil.which('clang') or shutil.which('cc')
        if not cc:
            raise RuntimeError('Native C compiler is required')
        cls.binaries = {}
        for label, baseline in (('current',False),('baseline',True)):
            source = cls.build/(label+'.c')
            source.write_text(harness.generate_source(cls.texts,str(cls.build),0,baseline=baseline))
            binary = cls.build/label
            command = [cc,'-std=gnu99','-O1','-g','-Wall','-Wextra','-Werror',
                       '-Wno-unused-function','-Wno-sign-compare','-Wno-pointer-sign',
                       '-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)]
            built = subprocess.run(command,capture_output=True,text=True,timeout=60)
            if built.returncode:
                raise AssertionError(built.stderr)
            cls.binaries[label] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_case(self,name,label='current'):
        run = subprocess.run([str(self.binaries[label]),name],capture_output=True,text=True,timeout=3)
        self.assertEqual(run.returncode,0,(name,label,run.stdout,run.stderr))
        self.assertEqual(run.stderr,'',(name,label,run.stderr))
        return json.loads(run.stdout)

    def assert_cases(self,names):
        for name in names:
            with self.subTest(case=name):
                self.assertEqual(self.run_case(name),self.expected[name])

    def test_normal_page_boundaries_and_final_ready_wait(self):
        self.assert_cases(('write-single','write-cross-page','write-multiple','write-final-ready-error'))

    def test_program_spi_failures_and_malformed_completion(self):
        self.assert_cases(('write-data-error','write-command-error','write-short-completion',
                           'write-overlong-completion','write-second-page-error'))

    def test_write_enable_and_void_callback_progress(self):
        self.assert_cases(('write-enable-first-error','write-enable-second-error','write-callback-zero',
                           'write-callback-overlong','write-callback-wrap'))

    def test_read_transport_and_fast_read_lengths(self):
        self.assert_cases(name for name in self.expected if name.startswith('read-'))

    def test_erase_command_errors_and_both_write_enable_paths(self):
        self.assert_cases(name for name in self.expected if name.startswith('erase-'))

    def test_character_write_progress_and_valid_short_results(self):
        self.assert_cases(name for name in self.expected if name.startswith('char-write-'))

    def test_character_read_bounds_ecc_and_eof(self):
        self.assert_cases(name for name in self.expected if name.startswith('char-read-'))

    def test_old_actual_transport_bodies_reproduce_underflow_and_false_success(self):
        for name,expected in harness.BASELINE_CASES[:5]:
            with self.subTest(case=name):
                row=self.run_case(name,'baseline')
                self.assertEqual(row,expected)
                self.assertNotEqual(row,self.expected[name])

    def test_old_actual_write_enable_errors_were_ignored(self):
        for name,expected in harness.BASELINE_CASES[5:8]:
            with self.subTest(case=name):
                self.assertEqual(self.run_case(name,'baseline'),expected)
                self.assertNotEqual(expected,self.expected[name])

    def test_old_actual_character_write_repeats_without_progress(self):
        name,expected=harness.BASELINE_CASES[-1]
        self.assertEqual(self.run_case(name,'baseline'),expected)
        self.assertEqual(expected['lower_calls'],3)
        self.assertEqual(self.run_case(name)['lower_calls'],1)

    def test_original_success_order_and_counts_are_preserved(self):
        for name in ('write-single','write-cross-page','write-multiple','read-normal',
                     'read-fast-normal','erase-normal','erase-sector-normal','erase-chip-normal'):
            with self.subTest(case=name):
                self.assertEqual(self.run_case(name,'baseline'),self.expected[name])
                self.assertEqual(self.run_case(name),self.expected[name])

    def test_public_baseline_function_identity_is_pinned(self):
        self.assertEqual(set(harness.BASELINE_FUNCTIONS),set(harness.BASELINE_FUNCTIONS_SHA256))
        for name,body in harness.BASELINE_FUNCTIONS.items():
            with self.subTest(function=name):
                self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),harness.BASELINE_FUNCTIONS_SHA256[name])
        self.assertNotIn('spi_nor_write_page',harness.BASELINE_FUNCTIONS)

    def test_gcc_strict_actual_function_compile_and_all_cases(self):
        gcc = shutil.which('gcc-16') or shutil.which('gcc')
        if not gcc:
            raise RuntimeError('GCC is required for actual kernel body compile validation')
        source = self.build/'current.c'
        binary = self.build/'gcc-current'
        built = subprocess.run([gcc,'-std=gnu99','-Os','-Wall','-Wextra','-Werror',
                                '-Wno-unused-function','-Wno-sign-compare','-Wno-pointer-sign',
                                str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
        self.assertEqual(built.returncode,0,built.stderr)
        for name,expected in harness.CASES:
            run=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=3)
            self.assertEqual(run.returncode,0,(name,run.stderr))
            self.assertEqual(json.loads(run.stdout),expected)

    def test_actual_body_export_is_unique_and_complete(self):
        actual=harness.actual_functions(self.texts)
        self.assertEqual(len(actual),10)
        generated=harness.generate_source(self.texts)
        for name,record in actual.items():
            with self.subTest(function=name):
                self.assertEqual(record['body'],harness.extract(self.texts[record['source_key']],name))
                self.assertEqual(generated.count(record['body']),1)

if __name__ == '__main__':
    unittest.main()
