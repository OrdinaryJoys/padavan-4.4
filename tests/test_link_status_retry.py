"""Link sampling errors preserve pairs and retry after consuming a change event."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import link_status_retry_harness as h

ROOT = Path(__file__).resolve().parents[1]


class LinkStatusRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-link-status-retry-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        cls.generated = h.generate_source(cls.texts)
        gcc = shutil.which('gcc-16') or shutil.which('gcc')
        clang = shutil.which('clang')
        if not gcc or not clang:
            raise AssertionError('Genuine GNU GCC and Clang required')
        version = subprocess.check_output([gcc, '--version'], text=True, timeout=10)
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('Genuine GNU GCC required')
        cls.compilers = [('gcc', gcc), ('clang', clang)]
        cls.binaries = [cls.build(cls.generated, name, compiler)
                        for name, compiler in cls.compilers]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def build(cls, text, name, compiler=None):
        source = cls.directory / (name + '.c')
        source.write_text(text)
        binary = source.with_suffix('')
        compiler = compiler or shutil.which('clang')
        flags = ['-std=gnu99', '-O2', '-Wall', '-Wextra', '-Werror']
        if 'clang' in compiler:
            flags += ['-fsanitize=address,undefined']
        run = subprocess.run([compiler, *flags, str(source), '-o', str(binary)],
                             capture_output=True, text=True, timeout=60)
        if run.returncode:
            raise AssertionError(run.stderr)
        return binary

    def run_case(self, binary, name):
        env = {**os.environ, 'ASAN_OPTIONS': os.environ.get('ASAN_OPTIONS', '') +
               ':detect_stack_use_after_return=1'}
        return subprocess.run([str(binary), name], capture_output=True, text=True,
                              timeout=10, env=env)

    def cases(self, names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(compiler=binary.name, case=name):
                    run = self.run_case(binary, name)
                    self.assertEqual((run.returncode, run.stderr), (0, ''))
                    self.assertEqual(json.loads(run.stdout), h.EXPECTED_ROWS[name])

    def test_complete_pair_success_no_change_and_business_handlers(self):
        self.cases(('success-no-change',))

    def test_wan_lan_and_repeated_failures_keep_pair_and_retry_without_irq(self):
        self.cases(('wan-failure-retry', 'lan-failure-retry', 'repeated-failure',
                    'initialized-wan-failure', 'initialized-lan-failure'))

    def test_failed_event_read_forces_retry_and_keeps_business_handlers_running(self):
        self.cases(('event-failure-retry', 'initialized-event-failure'))

    def test_ap_aggregate_uses_complete_new_pair_and_clears_after_failure(self):
        self.cases(('ap-failure-clear', 'ap-wan-failure'))

    def test_real_wan_entry_maps_query_failure_and_uses_configured_or_ap_port(self):
        self.cases(('wan-entry',))

    def test_pinned_old_whole_timer_reproduces_partial_pair_and_lost_retry(self):
        fixture = ROOT / 'tests/fixtures/link-status-retry'
        manifest = json.loads((fixture / 'manifest.json').read_text())
        raw = (fixture / 'dl_on_timer.c').read_bytes()
        self.assertEqual(manifest['dl_on_timer']['source_commit'],
                         '97b961d3735c2452f64b34d916b3d6dfaf7dae96')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['dl_on_timer']['sha256'])
        body = h.function(self.texts['timer'], 'dl_on_timer')
        for label, compiler in self.compilers:
            binary = self.build(self.generated.replace(body, raw.decode().strip()),
                                'old-' + label, compiler)
            for name in ('wan-failure-retry', 'event-failure-retry', 'ap-failure-clear'):
                run = self.run_case(binary, name)
                self.assertEqual((run.returncode, run.stderr), (0, ''))
                self.assertNotEqual(json.loads(run.stdout), h.EXPECTED_ROWS[name])

    def test_source_binding_unknown_case_and_compiled_retry_publication_mutants(self):
        self.assertEqual((len(h.FUNCTION_SOURCES), len(h.CASE_NAMES), len(h.FIELDS)), (2, 11, 8))
        self.assertEqual(set(h.CASE_NAMES), set(h.EXPECTED_ROWS))
        for name, rows in h.EXPECTED_ROWS.items():
            width = len(h.WAN_ENTRY_FIELDS) if name == 'wan-entry' else len(h.FIELDS)
            self.assertTrue(all(len(row) == width for row in rows))
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key], name)), 1)
        self.assertTrue(h.MODEL_VARIANT['actual_whole_timer_and_wan_entry'])
        for binary in self.binaries:
            self.assertEqual(self.run_case(binary, 'unknown').returncode, 91)
        with self.assertRaises(ValueError):
            h.generate_source({})
        bad = dict(self.texts)
        bad['timer'] += '\n' + h.function(self.texts['timer'], 'dl_on_timer')
        with self.assertRaises(ValueError):
            h.generate_source(bad)
        mutants = (
            ('\t\tdl_initialized = 0;\n\t} else if',
             '\t\tdl_initialized = 1;\n\t} else if', 'event-failure-retry'),
            ('\t\t} else {\n\t\t\tdl_initialized = 0;',
             '\t\t} else {\n\t\t\tdl_initialized = 1;', 'wan-failure-retry'),
            ('if (wan_link >= 0 && lan_result == 0)',
             'if (wan_link >= 0 || lan_result == 0)', 'lan-failure-retry'),
            ('lan_link |= wan_link;', 'lan_link |= dl_status_wan;', 'ap-failure-clear'),
        )
        body = h.function(self.texts['timer'], 'dl_on_timer')
        for index, (old, new, name) in enumerate(mutants):
            self.assertEqual(body.count(old), 1)
            binary = self.build(self.generated.replace(body, body.replace(old, new)),
                                'mutant-' + str(index))
            run = self.run_case(binary, name)
            self.assertEqual((run.returncode, run.stderr), (0, ''))
            self.assertNotEqual(json.loads(run.stdout), h.EXPECTED_ROWS[name])


if __name__ == '__main__':
    unittest.main()
