"""Manual bind-file admission, real PCI registration bodies, inert callbacks."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import pci_bind_guard_harness as h

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ['-std=gnu99', '-O2', '-Wall', '-Wextra', '-Werror']


class PciBindGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-pci-bind-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {k: (ROOT / p).read_text() for k, p in h.SOURCE_PATHS.items()}
        cls.current = h.generate_source(cls.texts)
        gcc = shutil.which('gcc-16') or shutil.which('gcc')
        clang = shutil.which('clang')
        if not gcc or not clang:
            raise AssertionError('Genuine GNU compiler and Clang required')
        version = subprocess.check_output([gcc, '--version'], text=True, timeout=10)
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('Genuine GNU compiler required')
        cls.compilers = {'gcc': gcc, 'clang': clang}
        cls.binaries = {label: cls.build(cls.current, 'current-' + label, label)
                        for label in cls.compilers}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def build(cls, code, name, label):
        source = cls.directory / (name + '.c')
        source.write_text(code)
        binary = source.with_suffix('')
        # Retain the historical GNU "name:" initializer byte-for-byte.
        # This narrow Clang compatibility flag does not suppress C bounds,
        # lifetime, type, return-value or sanitizer diagnostics.
        flags = FLAGS + (['-Wno-gnu-designator', '-fsanitize=address,undefined',
                          '-fno-sanitize-recover=all'] if label == 'clang' else [])
        run = subprocess.run([cls.compilers[label], *flags, str(source), '-o', str(binary)],
                             capture_output=True, text=True, timeout=60)
        if run.returncode or run.stderr:
            raise AssertionError('Strict actual-region compile failed:\n' + run.stderr)
        return binary

    def run_case(self, binary, name):
        run = subprocess.run([str(binary), name], capture_output=True, text=True, timeout=10,
                             env=dict(os.environ, ASAN_OPTIONS='halt_on_error=1',
                                      UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
        self.assertEqual((run.returncode, run.stderr), (0, ''), run.stderr)
        row = json.loads(run.stdout)
        self.assertEqual(len(row), len(h.FIELDS))
        self.assertTrue(all(type(value) is int for value in row))
        return row

    def test_exact_whole_functions_initializer_and_final_core_fragment_are_source_bound(self):
        parts = h.actual_parts(self.texts)
        self.assertEqual(set(parts['functions']), {'__pci_register_driver', 'pci_unregister_driver',
                                                 'rt_pci_init_module', 'rt_pci_cleanup_module', 'rt_pci_shutdown'})
        for body in (*parts['functions'].values(), parts['initializer'], parts['bus_guard']):
            self.assertEqual(self.current.count(body), 1)
        manifest = h.manifest(self.texts)
        self.assertEqual(len(manifest['whole_functions']), 5)
        self.assertEqual(manifest['bus_guard']['execution'], 'function-fragment')
        self.assertFalse(manifest['hardware_execution'])
        self.assertFalse(manifest['complete_module_unload_execution'])
        self.assertFalse(manifest['full_bus_add_driver_execution'])
        self.assertIn('.suppress_bind_attrs = true', parts['initializer'])
        self.assertIn('if (!drv->suppress_bind_attrs)', parts['bus_guard'])

    def test_current_registration_excludes_manual_nodes_and_keeps_initialized_core_fields(self):
        for label, binary in self.binaries.items():
            for name in ('register', 'core-add-error', 'register-error'):
                with self.subTest(compiler=label, case=name):
                    self.assertEqual(self.run_case(binary, name), h.EXPECTED_ROWS[name])

    def test_registered_shutdown_and_normal_cleanup_dispatch_remain_available(self):
        for label, binary in self.binaries.items():
            for name in ('shutdown', 'cleanup'):
                with self.subTest(compiler=label, case=name):
                    self.assertEqual(self.run_case(binary, name), h.EXPECTED_ROWS[name])

    def test_fixed_60_initializer_reproduces_manual_bind_exposure_and_preserves_callbacks(self):
        fixture = ROOT / 'tests/fixtures/pci-bind-guard'
        raw = (fixture / 'rt_pci_driver.c').read_bytes()
        metadata = json.loads((fixture / 'manifest.json').read_text())
        self.assertEqual(set(metadata), {'rt_pci_driver.c'})
        self.assertEqual(hashlib.sha256(raw).hexdigest(), h.BASELINE_INITIALIZER_SHA256)
        self.assertEqual(metadata['rt_pci_driver.c']['sha256'], h.BASELINE_INITIALIZER_SHA256)
        self.assertEqual(metadata['rt_pci_driver.c']['source_commit'], h.BASELINE_COMMIT)
        self.assertEqual(metadata['rt_pci_driver.c']['source_path'], h.SOURCE_PATHS['pci'])
        self.assertEqual(h.initializer(raw.decode()) + '\n', raw.decode())
        for label in self.compilers:
            binary = self.build(h.generate_source(self.texts, raw.decode()), 'historical-' + label, label)
            for name in h.CASE_NAMES:
                with self.subTest(compiler=label, case=name):
                    self.assertEqual(self.run_case(binary, name), h.BASELINE_ROWS[name])
            self.assertNotEqual(self.run_case(binary, 'register'), h.EXPECTED_ROWS['register'])

    def test_executable_guard_registration_and_callback_mutants_break_semantics(self):
        mutants = {
            'allow-bind': self.current.replace('.suppress_bind_attrs = true', '.suppress_bind_attrs = false'),
            'core-overwrite': self.current.replace('drv->driver.name = drv->name;',
                                                 'drv->driver.suppress_bind_attrs = false; drv->driver.name = drv->name;'),
            'inverted-core': self.current.replace('if (!drv->suppress_bind_attrs)', 'if (drv->suppress_bind_attrs)'),
            'drop-shutdown': self.current.replace('shutdown :\n\trt_pci_shutdown,', 'shutdown :\n\tNULL,'),
            'drop-remove': self.current.replace('DEVEXIT_P(rt_pci_remove)', 'NULL'),
            'drop-owner': self.current.replace('drv->driver.owner = owner;', 'drv->driver.owner = NULL; (void)owner;'),
        }
        for label in self.compilers:
            for name, source in mutants.items():
                self.assertNotEqual(source, self.current, name)
                # Avoid dispatching intentionally NULL callbacks: the register
                # observation independently checks the actual pointer slots.
                binary = self.build(source, 'mutant-' + name + '-' + label, label)
                with self.subTest(compiler=label, mutant=name):
                    self.assertNotEqual(self.run_case(binary, 'register'), h.EXPECTED_ROWS['register'])

    def test_source_parser_rejects_missing_duplicate_wrong_guard_and_config_inputs(self):
        for name, key in h.FUNCTION_SOURCES.items():
            body = h.function(self.texts[key], name)
            for text in (self.texts[key].replace(body, ''), self.texts[key] + '\n' + body):
                bad = dict(self.texts);bad[key] = text
                with self.subTest(function=name), self.assertRaises(ValueError):
                    h.generate_source(bad)
        actual = h.initializer(self.texts['pci'])
        for text in (self.texts['pci'].replace(actual, ''), self.texts['pci'] + '\n' + actual):
            bad = dict(self.texts);bad['pci'] = text
            with self.assertRaises(ValueError):h.generate_source(bad)
        for old, new in (('if (!drv->suppress_bind_attrs)', 'if (drv->suppress_bind_attrs)'),
                         ('add_bind_files(drv)', 'unrelated(drv)')):
            bad = dict(self.texts);bad['bus'] = bad['bus'].replace(old, new)
            with self.assertRaises(ValueError):h.generate_source(bad)
        for flag in ('CONFIG_SYSFS=y', 'CONFIG_MODULE_UNLOAD=y', 'CONFIG_MT7615_AP=m',
                     '# CONFIG_MODULE_FORCE_UNLOAD is not set', '# CONFIG_PM is not set'):
            bad = dict(self.texts);bad['config'] = bad['config'].replace(flag, '')
            with self.assertRaises(ValueError):h.generate_source(bad)
        with self.assertRaises(ValueError):h.generate_source({})

    def test_unadmitted_cases_do_not_execute_registration(self):
        self.assertEqual(set(h.EXPECTED_ROWS), set(h.BASELINE_ROWS))
        self.assertEqual(tuple(h.EXPECTED_ROWS), h.CASE_NAMES)
        self.assertEqual(len(h.FIELDS), 12)
        for binary in self.binaries.values():
            run = subprocess.run([str(binary), 'unadmitted'], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 91)
            self.assertEqual((run.stdout, run.stderr), ('', ''))


if __name__ == '__main__':
    unittest.main()
