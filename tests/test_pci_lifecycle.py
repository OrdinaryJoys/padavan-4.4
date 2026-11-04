"""Current data-only PCI lifecycle ownership and enable-accounting controls."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import pci_lifecycle_harness as h

ROOT = Path(__file__).resolve().parents[1]


class PciLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-current-pci-lifecycle-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        cls.generated = h.generate_source(cls.texts)
        source = cls.directory / 'pci.c'
        source.write_text(cls.generated)
        cls.binaries = []
        gnu = shutil.which('gcc-16')
        if gnu is None and Path('/opt/homebrew/bin/gcc-16').is_file():
            gnu = '/opt/homebrew/bin/gcc-16'
        if gnu is None:
            gnu = shutil.which('gcc')
        if gnu is None:
            raise AssertionError('GNU GCC required for warning parity')
        version = subprocess.run([gnu, '--version'], check=True, capture_output=True,
                                 text=True, timeout=10).stdout
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('The GCC control requires GNU GCC, not a compiler alias')
        for compiler, executable in (('clang', shutil.which('clang')), ('gcc', gnu)):
            if executable is None:
                raise AssertionError('Required strict C compiler absent: ' + compiler)
            binary = cls.directory / compiler
            flags = ['-std=gnu99', '-Os', '-Wall', '-Wextra', '-Werror']
            if compiler == 'clang':
                flags += ['-fsanitize=address,undefined']
            result = subprocess.run([executable, *flags, str(source), '-o', str(binary)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def cases(self, names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(compiler=binary.name, case=name):
                    result = subprocess.run([str(binary), name], check=True, capture_output=True,
                                            text=True, timeout=5)
                    row = json.loads(result.stdout)
                    self.assertEqual(row, h.EXPECTED_ROWS[name])
                    self.assertTrue(all(type(value) is int for value in row))

    def test_remove_balances_enable_and_clears_driver_data_before_netdev_free(self):
        self.cases(('remove-adapter', 'remove-no-adapter', 'remove-disabled'))

    def test_repeat_remove_and_missing_netdev_do_not_release_twice(self):
        self.cases(('remove-repeat', 'remove-no-netdev', 'remove-no-netdev-repeat'))

    def test_shutdown_suppresses_master_without_releasing_busy_dma_ownership(self):
        self.cases(('shutdown-busy', 'shutdown-busy-repeat', 'shutdown-no-netdev'))

    def test_registered_shutdown_and_whole_current_function_contract(self):
        self.assertEqual(len(h.CASE_NAMES), 9)
        self.assertEqual(set(h.CASE_NAMES), set(h.EXPECTED_ROWS))
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key], name)), 1)
        self.assertEqual(len(h.function_manifest(self.texts)), 2)
        self.assertRegex(self.texts['pci'], r'shutdown\s*:\s*rt_pci_shutdown\s*,')
        body = h.function(self.texts['pci'], 'rt_pci_shutdown')
        self.assertEqual(body.count('pci_clear_master(pci_dev);'), 1)
        self.assertNotRegex(body, r'\b(?:iounmap|pci_release_regions|pci_disable_device|RTMPFree\w*|Asic\w*)\s*\(')
        with self.assertRaises(ValueError):
            h.generate_source({})
        changed = dict(self.texts, config=self.texts['config'].replace('CONFIG_CHIP_MT7615E=y', ''))
        with self.assertRaises(ValueError):
            h.generate_source(changed)
