"""Whole driver lifetime functions with inert owners and real host mutexes.

The native model does not run a kernel, a PCI bus, IRQs, or device DMA.  Its
pthread schedules test the driver's serialized state transitions, not Linux
RTNL, PCI hotplug, or the full production callback graph.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import dma_quarantine_harness as h

ROOT = Path(__file__).resolve().parents[1]


class DmaQuarantineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='k2p-dma-quarantine-')
        cls.directory = Path(cls.temporary.name)
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        cls.generated = h.generate_source(cls.texts)
        source = cls.directory / 'quarantine.c'
        source.write_text(cls.generated)
        gnu = shutil.which('gcc-16') or shutil.which('gcc')
        if not gnu:
            raise AssertionError('GNU GCC required')
        version = subprocess.run([gnu, '--version'], check=True, capture_output=True,
                                 text=True, timeout=10).stdout
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('True GNU GCC required')
        cls.binaries = []
        for label, compiler in (('clang', shutil.which('clang')), ('gcc', gnu)):
            if not compiler:
                raise AssertionError('Required compiler absent: ' + label)
            binary = cls.directory / label
            flags = ['-std=gnu99', '-Os', '-pthread', '-Wall', '-Wextra', '-Werror',
                     '-Wno-unused-variable', '-Wno-unused-parameter',
                     '-Wno-unused-but-set-variable']
            if label == 'clang':
                flags += ['-fsanitize=address,undefined']
            result = subprocess.run([compiler, *flags, str(source), '-o', str(binary)],
                                    capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def cases(self, group):
        selected = h.CASE_GROUPS[group]
        self.assertTrue(selected)
        for binary in self.binaries:
            for name in selected:
                with self.subTest(compiler=binary.name, case=name):
                    result = subprocess.run([str(binary), name], check=True,
                                            capture_output=True, text=True, timeout=20)
                    self.assertEqual(json.loads(result.stdout), h.EXPECTED_ROWS[name])

    def test_module_and_pci_references_balance_on_normal_lifetime(self):
        self.cases('balanced')

    def test_duplicate_acquisition_does_not_duplicate_pins(self):
        self.cases('duplicate')

    def test_failed_module_acquisition_prevents_first_arm(self):
        self.cases('module-failure')

    def test_busy_close_preserves_complete_owner_graph(self):
        self.cases('busy-close')

    def test_failed_disable_preserves_complete_owner_graph(self):
        self.cases('stop-failure')

    def test_missing_device_cannot_be_misread_as_safe_idle(self):
        self.cases('missing-device')

    def test_first_enable_failure_keeps_irq_and_hardware_owners(self):
        self.cases('first-enable')

    def test_busy_remove_never_unregisters_or_releases_pci_resources(self):
        self.cases('busy-remove')

    def test_sticky_quarantine_rejects_retry_and_reenable(self):
        self.cases('sticky')

    def test_successful_remove_releases_each_owner_once(self):
        self.cases('remove-success')

    def test_direct_adapter_cleanup_cannot_bypass_quarantine(self):
        self.cases('adapter-guard')

    def test_interleaved_close_open_and_remove_have_one_serialized_owner(self):
        self.cases('interleaved')

    def test_whole_function_sources_and_case_contract_are_bound(self):
        grouped = [name for names in h.CASE_GROUPS.values() for name in names]
        self.assertEqual(set(grouped), set(h.CASE_NAMES))
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertEqual(set(h.CASE_NAMES), set(h.EXPECTED_ROWS))
        self.assertEqual(set(h.function_manifest(self.texts)), set(h.FUNCTION_SOURCES))
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key], name)), 1)
        for name, key in h.SOURCE_ONLY_FUNCTION_SOURCES.items():
            self.assertTrue(h.function(self.texts[key], name))
        self.assertIn(h.declarations(self.texts), self.generated)
        with self.assertRaises(ValueError):
            h.generate_source({})
        with self.assertRaises(ValueError):
            h.generate_source(self.texts, 'legacy')

    def test_removed_stop_setter_and_outer_remove_barriers_are_rejected(self):
        mutations = (
            ('RtmpDmaTeardownCheck', 'os', 'if (!RT28XXDMAReset(pAd)) {',
             'if (FALSE) {', 'close-busy'),
            ('hif_set_WPDMA', 'chip',
             'if (enable && (!pAd->dma_lifecycle_pinned ||',
             'if (FALSE && (!pAd->dma_lifecycle_pinned ||', 'enable-unpinned'),
            ('rt_pci_remove', 'pci',
             'if (!RtmpDmaBeginRemove((RTMP_ADAPTER *)pAd)) {',
             'if (FALSE) {', 'remove-busy'),
        )
        for index, (name, key, before, after, selector) in enumerate(mutations):
            with self.subTest(function=name):
                body = h.function(self.texts[key], name)
                self.assertEqual(body.count(before), 1)
                changed = dict(self.texts)
                changed[key] = changed[key].replace(body, body.replace(before, after))
                source = self.directory / ('removed-barrier-' + str(index) + '.c')
                source.write_text(h.generate_source(changed))
                binary = source.with_suffix('')
                result = subprocess.run([
                    shutil.which('clang'), '-std=gnu99', '-Os', '-pthread',
                    '-Wall', '-Wextra', '-Werror', '-Wno-unused-variable',
                    '-Wno-unused-parameter', '-Wno-unused-but-set-variable',
                    '-fsanitize=address,undefined', str(source), '-o', str(binary),
                ], capture_output=True, text=True, timeout=60)
                self.assertEqual((result.returncode, result.stderr), (0, ''), result.stderr)
                rejected = subprocess.run([str(binary), selector], capture_output=True,
                                          text=True, timeout=20)
                self.assertNotEqual(rejected.returncode, 0)


if __name__ == '__main__':
    unittest.main()
