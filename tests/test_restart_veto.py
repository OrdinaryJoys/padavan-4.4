"""Native restart admission: whole source bodies, explicit hardware/terminal seams."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import restart_veto_harness as h

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = '29034ee94d511b747ac1fb881b42cc10f6ab623665b8370ff61d19931b2b4f0d'


class RestartVetoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='restart-veto-')
        cls.directory = Path(cls.temporary.name)
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        fixture_bytes = (ROOT / 'tests/fixtures/restart_veto_f9.json').read_bytes()
        if hashlib.sha256(fixture_bytes).hexdigest() != FIXTURE_SHA256:
            raise AssertionError('Exact f9 fixture changed')
        cls.fixture = json.loads(fixture_bytes)
        if cls.fixture['commit'] != h.BASELINE_COMMIT:
            raise AssertionError('Exact old commit required')
        cls.baseline = {key: '' for key in cls.texts}
        # Numeric new reasons are a harness seam for absent f9 report APIs.
        cls.baseline['header'] = cls.texts['header']
        cls.baseline['arch'] = ('#define SYSC_REG_RESET_CTRL 0x034\n'
                                '#define RSTCTL_RESET_PCI BIT(26)\n'
                                '#define RSTCTL_RESET_SYSTEM BIT(0)\n')
        for name, row in cls.fixture['functions'].items():
            if row['sha256'] != hashlib.sha256(row['body'].encode()).hexdigest():
                raise AssertionError('Corrupt exact old function: ' + name)
            key = h.FUNCTION_SOURCES[name]
            if row['path'] != h.SOURCE_PATHS[key]:
                raise AssertionError('Unexpected old source path')
            cls.baseline[key] += row['body'] + '\n'
        gnu = shutil.which('gcc-16')
        clang = shutil.which('clang')
        if not gnu or not clang:
            raise AssertionError('GNU GCC 16 and Clang required')
        version = subprocess.check_output([gnu, '--version'], text=True, timeout=10)
        if 'Free Software Foundation' not in version or '16.' not in version.splitlines()[0]:
            raise AssertionError('Actual GNU GCC 16 required')
        cls.compilers = [('gcc16', gnu), ('clang-sanitized', clang)]
        # ralink_restart's original board callback ignores its command argument.
        cls.flags = ['-std=gnu99', '-O2', '-pthread', '-Wall', '-Wextra', '-Werror',
                     '-Wno-unused-parameter']
        cls.binaries = {}
        for baseline in (False, True):
            code = h.generate_source(cls.baseline if baseline else cls.texts, baseline=baseline)
            for label, compiler in cls.compilers:
                key = ('f9-' if baseline else 'current-') + label
                cls.binaries[key] = cls.compile(code, key, compiler, label)

    @classmethod
    def compile(cls, code, key, compiler, label):
        source = cls.directory / (key + '.c')
        source.write_text(code)
        binary = source.with_suffix('')
        result = subprocess.run([compiler, *cls.flags,
                                 *(['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
                                   if 'clang' in label else []), str(source), '-o', str(binary)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def row(self, binary, name):
        result = subprocess.run([str(binary), name], capture_output=True, text=True,
                                timeout=10, env=dict(os.environ, ASAN_OPTIONS='symbolize=0'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_26_source_bound_schedules_and_624_observation_fields(self):
        for key, binary in self.binaries.items():
            if key.startswith('f9-'):
                continue
            for name in h.CASE_NAMES:
                with self.subTest(binary=key, case=name):
                    self.assertEqual(self.row(binary, name), h.EXPECTED_ROWS[name])

    def test_real_f9_whole_function_negative_controls_reach_reset(self):
        for key, binary in self.binaries.items():
            if not key.startswith('f9-'):
                continue
            for name, expected in h.BASELINE_ROWS.items():
                with self.subTest(binary=key, case=name):
                    row = self.row(binary, name)
                    self.assertEqual(row, expected)
                    self.assertEqual(row['system_reset'], 1)
                    if name != 'success':
                        self.assertNotEqual(row, h.EXPECTED_ROWS[name])

    def test_exact_whole_function_and_integer_ledger_contract(self):
        self.assertEqual((len(h.FUNCTION_SOURCES), len(h.CASE_NAMES), len(h.FIELDS)), (22, 26, 24))
        self.assertEqual(set(h.CASE_NAMES), set(h.EXPECTED_ROWS))
        self.assertEqual(tuple(h.FUNCTION_SOURCES), h.BODY_ORDER)
        generated = h.generate_source(self.texts)
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(generated.count(h.function(self.texts[key], name)), 1)
        self.assertEqual(len(h.function_manifest(self.texts)), 22)
        self.assertEqual(set(self.fixture['functions']), set(h.FUNCTION_SOURCES) - set(h.NEW_FUNCTIONS))
        report = h.function(self.texts['reboot'], 'reboot_dma_failure_report')
        self.assertIn('atomic_or(reasons ? reasons : REBOOT_DMA_UNKNOWN,', report)
        self.assertNotIn('char', report)
        self.assertNotIn('alloc', report)
        self.assertNotIn('atomic_set', self.texts['reboot'])
        prepare = h.function(self.texts['reboot'], 'kernel_restart_prepare')
        self.assertIn('device_shutdown();\n\treboot_dma_failure_check(true);', prepare)
        self.assertIn('extern void kernel_restart_prepare(char *cmd);', self.texts['header'])
        direct = h.function(self.texts['arch'], 'ralink_restart')
        self.assertLess(direct.index('reboot_dma_failure_check(false);'), direct.index('rt_sysc_m32('))
        with self.assertRaises(ValueError):
            h.generate_source({})

    def reject(self, before, after, case, label):
        code = h.generate_source(self.texts)
        self.assertEqual(code.count(before), 1)
        compiler = self.compilers[1][1]
        binary = self.compile(code.replace(before, after), label, compiler, 'clang-sanitized')
        self.assertNotEqual(self.row(binary, case), h.EXPECTED_ROWS[case])

    def test_removed_normal_and_board_gates_are_observably_rejected(self):
        self.reject('device_shutdown();\n\treboot_dma_failure_check(true);',
                    'device_shutdown();', 'raeth-pdma-busy', 'removed-normal-gate')
        self.reject('/* Cover direct/emergency callers and failures reported after prepare. */\n\treboot_dma_failure_check(false);',
                    '/* removed board gate */', 'late-syscore', 'removed-board-gate')

    def test_failure_report_sticky_and_oom_boundary_mutations_are_rejected(self):
        self.reject('atomic_or(reasons ? reasons : REBOOT_DMA_UNKNOWN,\n\t\t  &reboot_dma_failure_reasons);',
                    'atomic_or(reasons ? (reasons & 1U) : REBOOT_DMA_UNKNOWN, &reboot_dma_failure_reasons);',
                    'concurrent-report', 'dropped-concurrent-reason')
        self.reject('if (pAd->dma_running ||\n\t\t(pAd->dma_lifecycle_pinned && !pAd->dma_quiesced))',
                    'if (1)', 'quarantine-pure-oom', 'oom-is-not-dma-failure')


if __name__ == '__main__':
    unittest.main()
