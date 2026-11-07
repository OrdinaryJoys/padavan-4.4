"""Real userspace wrapper/getter and complete rstats ESW-loop regressions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import esw_userspace_status_harness as h

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ['-std=gnu99', '-O2', '-Wall', '-Wextra', '-Werror']


class EswUserspaceStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-esw-userspace-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        gcc = shutil.which('gcc-16')
        clang = shutil.which('clang')
        if not gcc or not clang:
            raise AssertionError('Genuine GNU GCC 16 and Clang are required')
        version = subprocess.check_output([gcc, '--version'], text=True, timeout=10)
        major = subprocess.check_output([gcc, '-dumpversion'], text=True, timeout=10).strip().split('.')[0]
        if 'Free Software Foundation' not in version or 'clang' in version.lower() or major != '16':
            raise AssertionError('Genuine GNU GCC 16 required')
        cls.compilers = {'gcc16': gcc, 'clang': clang}
        cls.generated = {backend: h.generate_source(cls.texts, backend) for backend in h.WRAPPERS}
        cls.binaries = {(backend, label): cls.build(code, backend + '-' + label, label)
                        for backend, code in cls.generated.items() for label in cls.compilers}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def build(cls, text, name, label):
        source = cls.directory / (name + '.c')
        source.write_text(text)
        binary = source.with_suffix('')
        flags = FLAGS + (['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
                         if label == 'clang' else [])
        run = subprocess.run([cls.compilers[label], *flags, str(source), '-o', str(binary)],
                             capture_output=True, text=True, timeout=60)
        if run.returncode or run.stderr:
            raise AssertionError('Strict compile failed for ' + name + ':\n' + run.stderr)
        return binary

    def run_case(self, binary, name):
        env = dict(os.environ)
        env['ASAN_OPTIONS'] = 'detect_stack_use_after_return=1:halt_on_error=1'
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        return subprocess.run([str(binary), name], capture_output=True, text=True,
                              timeout=10, env=env)

    def cases(self, names):
        for (backend, label), binary in self.binaries.items():
            for name in names:
                with self.subTest(backend=backend, compiler=label, case=name):
                    run = self.run_case(binary, name)
                    self.assertEqual((run.returncode, run.stderr), (0, ''))
                    self.assertEqual(json.loads(run.stdout), h.expected(name))

    def test_whole_wrappers_preserve_open_ioctl_errno_across_perror_and_close(self):
        self.cases(('wrap-open', 'wrap-ioctl', 'wrap-ok'))

    def test_whole_getters_reject_every_nonzero_status_without_publishing_canaries(self):
        self.cases(('get-open', 'get-ioctl', 'get-pos5', 'get-pos13',
                    'get-neg5', 'get-max', 'get-min'))

    def test_zero_status_publishes_exact_uint64_values_through_both_real_backends(self):
        self.cases(('get-ok',))

    def test_complete_rstats_loop_skips_real_failures_and_iterates_exact_success_values(self):
        self.cases(('consume-open', 'consume-ioctl', 'consume-ok'))

    def test_consumer_rejects_future_positive_and_negative_errors_and_accepts_only_zero(self):
        self.cases(('consume-pos5', 'consume-neg5', 'consume-stub-ok'))

    def test_source_binding_rejects_missing_duplicate_bodies_regions_and_declarations(self):
        self.assertEqual(len(h.CASES), 17)
        self.assertEqual(len(set(h.CASES)), 17)
        self.assertTrue(h.MODEL_VARIANT['whole_source_bound_ESW_loop'])
        self.assertFalse(h.MODEL_VARIANT['whole_process_rstats_execution'])
        self.assertFalse(h.MODEL_VARIANT['RTL8367_shipping_K2P'])
        self.assertFalse(h.MODEL_VARIANT['RTL8367_wire_ABI_validated'])
        for backend, wrapper in h.WRAPPERS.items():
            self.assertEqual(self.generated[backend].count(h.function(self.texts[backend], wrapper)), 1)
            self.assertEqual(self.generated[backend].count(h.function(self.texts[backend], 'phy_status_port_bytes')), 1)
            self.assertEqual(self.generated[backend].count(h.consumer_loop(self.texts['rstats'])), 1)
            bad = dict(self.texts)
            bad[backend] += '\n' + h.function(self.texts[backend], wrapper)
            with self.assertRaises(ValueError):
                h.generate_source(bad, backend)
            bad = dict(self.texts)
            bad[backend] = bad[backend].replace(h.function(bad[backend], 'phy_status_port_bytes'), '')
            with self.assertRaises(ValueError):
                h.generate_source(bad, backend)
        with self.assertRaises(ValueError):
            h.generate_source({}, 'mtk')
        bad = dict(self.texts)
        bad['rstats'] += '\n' + h.function(bad['rstats'], 'process_rstats')
        with self.assertRaises(ValueError):
            h.generate_source(bad, 'mtk')
        bad = dict(self.texts)
        loop = h.consumer_loop(bad['rstats'])
        bad['rstats'] = bad['rstats'].replace(loop, loop + '\n' + loop)
        with self.assertRaises(ValueError):
            h.generate_source(bad, 'mtk')
        bad = dict(self.texts)
        bad['mtk_header'] += '\n#define MTK_ESW_IOCTL_STATUS_BYTES_PORT 26\n'
        with self.assertRaises(ValueError):
            h.generate_source(bad, 'mtk')
        for binary in self.binaries.values():
            self.assertEqual(self.run_case(binary, 'unreviewed').returncode, 91)

    def test_pinned_old_whole_wrappers_getters_and_consumer_compile_and_reproduce_errors(self):
        fixture = ROOT / 'tests/fixtures/esw-userspace-status'
        manifest = json.loads((fixture / 'manifest.json').read_text())
        self.assertEqual(len(manifest), 5)
        for filename, metadata in manifest.items():
            raw = (fixture / filename).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), metadata['sha256'])
            self.assertEqual(metadata['source_commit'], '97b961d3735c2452f64b34d916b3d6dfaf7dae96')
            backends = tuple(h.WRAPPERS) if filename.startswith('rstats-') else (filename.split('-')[0],)
            kind = 'consumer' if filename.startswith('rstats-') else filename.split('-')[1].split('.')[0]
            cases = {'wrapper': ('wrap-open', 'wrap-ioctl'),
                     'getter': ('get-pos5',), 'consumer': ('consume-pos5',)}[kind]
            for backend in backends:
                code = h.generate_source(self.texts, backend, {kind: raw.decode().rstrip('\n')})
                for label in self.compilers:
                    binary = self.build(code, 'old-' + filename + '-' + backend + '-' + label, label)
                    for name in cases:
                        with self.subTest(fixture=filename, backend=backend, compiler=label, case=name):
                            run = self.run_case(binary, name)
                            self.assertEqual((run.returncode, run.stderr), (0, ''))
                            self.assertNotEqual(json.loads(run.stdout), h.expected(name))

    def test_effective_close_errno_getter_and_consumer_mutants_compile_and_fail_semantics(self):
        for backend, wrapper in h.WRAPPERS.items():
            whole_wrapper = h.function(self.texts[backend], wrapper)
            whole_getter = h.function(self.texts[backend], 'phy_status_port_bytes')
            loop = h.consumer_loop(self.texts['rstats'])
            mutants = [('close-errno', 'wrapper', whole_wrapper, '\n\treturn retVal;\n}',
                        '\n\treturn errno;\n}', 'wrap-ok'),
                       ('getter-positive', 'getter', whole_getter, 'if (ioctl_result != 0)',
                        'if (ioctl_result < 0)', 'get-pos5'),
                       ('consumer-positive', 'consumer', loop,
                        'phy_status_port_bytes(i, &counter[0], &counter[1]) != 0',
                        'phy_status_port_bytes(i, &counter[0], &counter[1]) < 0', 'consume-pos5')]
            for name, kind, body, old, new, case in mutants:
                self.assertEqual(body.count(old), 1)
                code = h.generate_source(self.texts, backend, {kind: body.replace(old, new)})
                for label in self.compilers:
                    with self.subTest(mutant=name, backend=backend, compiler=label):
                        binary = self.build(code, 'mutant-' + backend + '-' + name + '-' + label, label)
                        run = self.run_case(binary, case)
                        self.assertEqual((run.returncode, run.stderr), (0, ''))
                        self.assertNotEqual(json.loads(run.stdout), h.expected(case))


if __name__ == '__main__':
    unittest.main()
