#!/usr/bin/env python3
"""Actual erase/unlock/main and Storage shell failure chain, ordinary IO only."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import mtd_mutation_harness as h

ROOT = Path(__file__).resolve().parents[1]


class MtdMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-mtd-mutation-')
        cls.base = Path(cls.temp.name).resolve()
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        cls.binaries, cls.codes = {}, {}
        for kind in ('current', 'baseline', 'disabled'):
            code = h.generate_source(cls.texts, str(cls.base / (kind + '-fixtures')),
                                     os.geteuid(), baseline=kind == 'baseline',
                                     disabled_oracle=kind == 'disabled')
            cls.codes[kind] = code
            cls.binaries[kind] = cls.compile(code, kind)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, code, name):
        path = cls.base / (name + '.c')
        path.write_text(code)
        binary = cls.base / name
        result = subprocess.run([shutil.which('clang') or shutil.which('cc'),
                                 '-std=gnu99', '-Os', '-Wall', '-Wextra', '-Werror',
                                 '-Wno-unused-parameter', '-Wno-unused-function',
                                 '-Wno-sign-compare', '-fsanitize=address,undefined',
                                 '-g', str(path), '-o', str(binary)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary

    def row(self, case, kind='current'):
        binary = self.binaries[kind] if isinstance(kind, str) else kind
        result = subprocess.run([str(binary), case], capture_output=True, text=True,
                                timeout=5, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('AddressSanitizer', result.stderr)
        self.assertNotIn('runtime error:', result.stderr)
        return json.loads(result.stdout)

    def mutant(self, function, before, after, name):
        texts = dict(self.texts)
        original = h.legacy.function(texts['mtd'], function)
        self.assertEqual(original.count(before), 1)
        texts['mtd'] = texts['mtd'].replace(original, original.replace(before, after), 1)
        return self.compile(h.generate_source(texts, str(self.base / (name + '-fixtures')),
                                             os.geteuid()), name)

    def test_all_current_cases_and_fixed_baseline_contract(self):
        for case in h.CASE_NAMES:
            with self.subTest(current=case):
                self.assertTrue(h.validate_row(self.row(case)))
        for case in h.BASELINE_CASES:
            with self.subTest(baseline=case):
                self.assertTrue(h.validate_row(self.row(case, 'baseline'), baseline=True))

    def test_old_errors_report_success_and_continue_mutation(self):
        for case in h.BASELINE_CASES[1:]:
            with self.subTest(case=case):
                old, current = self.row(case, 'baseline'), self.row(case)
                self.assertEqual(old['returncode'], 0)
                self.assertEqual(current['returncode'], 1)
                with self.assertRaises(ValueError):
                    h.validate_row(old)
        old = self.row('other-board-reboot-error', 'baseline')
        self.assertIn('raw-reboot', old['trace'])
        self.assertNotIn('reboot', self.row('other-board-reboot-error')['trace'])

    def test_erase_failure_stops_at_first_error_and_closes(self):
        for case, erases in (('erase-error-first', 1), ('erase-error-second', 2)):
            row = self.row(case)
            self.assertEqual((row['returncode'], row['erases'], row['closes']), (1, erases, 2))
            self.assertTrue(row['trace'].endswith('close'))
            self.assertNotIn('primary-write', row['trace'])

    def test_unsupported_unlock_retains_nor_compatibility(self):
        for case in ('erase-ok', 'unlock-unsupported', 'unlock-enotty'):
            row = self.row(case)
            self.assertEqual((row['returncode'], row['unlocks'], row['erases']), (0, 5, 4))
            self.assertEqual(row['bad_range'], 0)

    def test_invalid_geometry_never_erases_or_issues_invalid_range(self):
        for case in ('zero-size', 'negative-size', 'zero-erase', 'negative-erase',
                     'unaligned-size', 'oversized-erase'):
            row = self.row(case)
            self.assertEqual((row['returncode'], row['erases'], row['bad_range']), (1, 0, 0))
            self.assertEqual(row['opens'], row['closes'])

    def test_preerase_and_unlock_failure_prevent_later_writes(self):
        for case in ('preerase-failure', 'preunlock-failure', 'write-unlock-failure',
                     'jffs-unlock-failure', 'block-unlock-error'):
            row = self.row(case)
            self.assertEqual(row['returncode'], 1)
            self.assertFalse(set(row['trace'].split(',')) & {'primary-write', 'jffs2write', 'raw-reboot'})

    def test_colon_target_allocation_failure_and_cleanup(self):
        good = self.row('colon-unlock-ok')
        second = self.row('colon-unlock-second-error')
        self.assertEqual((good['returncode'], second['returncode']), (0, 1))
        for row in (good, second):
            self.assertEqual((row['allocs'], row['frees'], row['opens'], row['closes']), (1, 1, 2, 2))
        row = self.row('colon-alloc-error')
        self.assertEqual((row['returncode'], row['opens'], row['allocs'], row['frees']), (1, 0, 1, 0))

    def test_main_ignoring_erase_result_mutant_is_rejected(self):
        binary = self.mutant('main',
                            'if ((!unlocked && mtd_unlock(device) != 0) || mtd_erase(device) != 0)\n\t\t\t\treturn 1;',
                            'if (!unlocked) mtd_unlock(device);\n\t\t\tmtd_erase(device);', 'ignored-erase-result')
        row = self.row('erase-error-first', binary)
        self.assertEqual((row['returncode'], row['erases']), (0, 1))
        with self.assertRaises(ValueError):
            h.validate_row(row)

    def test_erase_continuing_after_ioctl_failure_mutant_is_rejected(self):
        binary = self.mutant('mtd_erase',
                            '\t\t\t\tgoto out;\n\t\t\t}\n',
                            '\t\t\t}\n', 'ignored-erase-ioctl')
        row = self.row('erase-error-first', binary)
        self.assertEqual((row['returncode'], row['erases']), (0, 4))
        with self.assertRaises(ValueError):
            h.validate_row(row)

    def test_storage_erase_chain_preserves_live_tree_on_failure(self):
        script = (ROOT / 'trunk/user/scripts/mtd_storage.sh').read_text()
        found = re.search(r'func_erase\(\)\n\{[\s\S]*?\n\}', script)
        self.assertIsNotNone(found)
        for kind, expected in (('current', 1), ('baseline', 0)):
            with tempfile.TemporaryDirectory(prefix='k2p-storage-erase-chain-') as name:
                root = Path(name)
                live = root / 'storage'
                live.mkdir()
                (live / 'original').write_text('synthetic live config')
                digest = root / 'hash'
                digest.write_text('synthetic old hash')
                marker = root / 'locked'
                # The shell receives the actual inner CLI status, not the
                # outer model's success status used to emit its JSON record.
                stub = root / 'mtd_write'
                stub.write_text('#!' + str(Path(shutil.which('python3')).resolve()) + '\n'
                                'import json,subprocess,sys\n'
                                'assert sys.argv[1:]==["erase","Storage"]\n'
                                'p=subprocess.run([' + repr(str(self.binaries[kind])) + ',"erase-error-first"],capture_output=True,text=True)\n'
                                'assert p.returncode==0,p.stderr\n'
                                'raise SystemExit(json.loads(p.stdout)["returncode"])\n')
                stub.chmod(0o700)
                code = ('result=0\nmtd_part_name=Storage\nhsh="$FIXTURE_HASH"\n'
                        'dir_storage="$FIXTURE_LIVE"\nslk="$FIXTURE_MARKER"\n' + found.group() +
                        '\nfunc_erase\nexit "$result"\n')
                result = subprocess.run(['/bin/sh', '-c', code], capture_output=True, text=True,
                                        env=dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                                                 FIXTURE_HASH=str(digest), FIXTURE_LIVE=str(live),
                                                 FIXTURE_MARKER=str(marker), ASAN_OPTIONS='detect_leaks=0'), timeout=5)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual((live / 'original').exists(), kind == 'current')
                self.assertEqual(digest.exists(), kind == 'current')
                self.assertEqual(marker.exists(), kind == 'baseline')

    def test_exact_functions_baseline_and_typed_contract_boundaries(self):
        for row in h.actual_functions(self.texts).values():
            self.assertEqual(self.codes['current'].count(row['body']), 1)
        for texts, root, owner, baseline in (({}, '/tmp/inert', 0, False),
                                               (self.texts, 'relative', 0, False),
                                               (self.texts, '/tmp/inert', True, False),
                                               (self.texts, '/tmp/inert', 0, 1)):
            with self.assertRaises(ValueError):
                h.generate_source(texts, root, owner, baseline)
        changed = dict(h.BASELINE_FUNCTIONS)
        changed['mtd_erase'] += '\n'
        with mock.patch.object(h, 'BASELINE_FUNCTIONS', changed), self.assertRaises(ValueError):
            h.generate_source(self.texts, '/tmp/inert', baseline=True)
        row = self.row('erase-ok')
        for key, value in (('returncode', False), ('erases', True), ('bad_range', 1), ('trace', '')):
            wrong = copy.deepcopy(row)
            wrong[key] = value
            with self.assertRaises(ValueError):
                h.validate_row(wrong)

    def test_no_execution_oracle_cannot_satisfy_success_or_failure(self):
        for case in ('erase-ok', 'erase-error-first'):
            row = self.row(case, 'disabled')
            self.assertEqual((row['returncode'], row['trace'], row['opens']), (0, '', 0))
            with self.assertRaises(ValueError):
                h.validate_row(row)
        with self.assertRaises(ValueError):
            h.generate_source(self.texts, '/tmp/inert', baseline=True, disabled_oracle=True)


if __name__ == '__main__':
    unittest.main()
