"""Actual static-entry/admission bodies with private files and inert writer/reset.

getppid, owner identity, proc-exe and filesystem-type observations are explicit
source-adapter seams. No actual firmware device, signal reset or reboot is used.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from resident_upgrade_harness import SOURCE_PATHS, CASES, generate_source

ROOT = Path(__file__).resolve().parents[1]


class ResidentUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-resident-native-')
        cls.base = Path(cls.temp.name).resolve()
        cls.runtime = cls.base / 'runtime'
        cls.texts = {k: (ROOT / p).read_text() for k, p in SOURCE_PATHS.items()}
        cls.binary = cls.compile(cls.texts, 'current')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, texts, name, runtime=None):
        c = cls.base / (name + '.c'); binary = cls.base / name
        c.write_text(generate_source(texts, str(runtime or cls.runtime), os.geteuid()))
        result = subprocess.run([shutil.which('clang') or shutil.which('cc'),
            '-std=gnu99', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-function', '-Wno-unused-parameter', '-fsanitize=address,undefined',
            str(c), '-o', str(binary)], capture_output=True, text=True)
        if result.returncode: raise AssertionError(result.stderr)
        return binary

    def run_case(self, name, binary=None, runtime=None, expected=True):
        path = runtime or self.runtime
        if path.exists(): shutil.rmtree(path)
        result = subprocess.run([str(binary or self.binary), name], capture_output=True,
                                text=True, timeout=6)
        self.assertNotIn('AddressSanitizer', result.stderr)
        self.assertNotIn('runtime error:', result.stderr)
        self.assertEqual(result.returncode, 0, (name, result.returncode, result.stderr, result.stdout))
        record = json.loads(result.stdout)
        if expected: self.assertEqual(record, dict(CASES)[name])
        return record

    def check(self, names):
        for name in names:
            with self.subTest(case=name): self.run_case(name)

    def test_safe_unknown_and_both_returned_reset_results(self):
        self.check(('safe-prewrite', 'unknown', 'verified-reset-error', 'verified-reset-zero'))

    def test_exact_invocation_and_empty_environment(self):
        self.check(('bad-argc', 'bad-command', 'bad-target', 'bad-fd-argument', 'nonempty-environment'))

    def test_inherited_real_exclusive_lease_not_upgraded_unlocked_or_shared(self):
        self.check(('lease-unlocked', 'lease-shared', 'lease-other-inode', 'foreign-exclusive',
                    'lease-hardlink', 'lease-mode'))

    def test_marker_is_literal_private_regular_and_empty(self):
        self.check(('marker-absent', 'marker-symlink', 'marker-nonempty', 'marker-hardlink'))

    def test_private_attempt_and_exact_status_location(self):
        self.check(('private-mode', 'attempt-symlink', 'status-other-parent', 'status-other-leaf'))

    def test_executed_file_identity_mode_alias_and_open_errors(self):
        self.check(('exe-symlink', 'exe-other-inode', 'exe-mode', 'exe-hardlink', 'exe-open-error'))

    def test_every_required_mapping_is_tmpfs_and_statfs_error_rejects(self):
        self.check(('lease-not-tmpfs', 'status-not-tmpfs', 'exe-not-tmpfs', 'statfs-error'))

    def test_wrong_owner_rejected(self):
        self.run_case('owner-mismatch')

    def test_missing_independent_lock_probe_would_accept_unlocked_fd(self):
        texts = dict(self.texts)
        old = ('if (flock(probe, LOCK_SH | LOCK_NB) == 0)\n\t\tgoto out;\n'
               '\tif ((errno != EWOULDBLOCK && errno != EAGAIN) || flock(lease, LOCK_EX | LOCK_NB) != 0)')
        self.assertEqual(texts['admission'].count(old), 1)
        texts['admission'] = texts['admission'].replace(old, 'if (flock(lease, LOCK_EX | LOCK_NB) != 0)')
        bad = self.compile(texts, 'unsafe-upgrade-lease')
        record = self.run_case('lease-unlocked', bad, expected=False)
        self.assertIn('writer-calls:1', record['trace'])
        self.assertNotEqual(record, dict(CASES)['lease-unlocked'])

    def test_reset_return_must_not_become_safe_prewrite(self):
        texts = dict(self.texts)
        old = '(void)FWUP_RESIDENT_REBOOT();\n\t\treturn FWUP_UNKNOWN;'
        self.assertEqual(texts['resident'].count(old), 1)
        texts['resident'] = texts['resident'].replace(old, '(void)FWUP_RESIDENT_REBOOT();\n\t\treturn FWUP_SAFE;')
        bad = self.compile(texts, 'unsafe-reset-return')
        record = self.run_case('verified-reset-zero', bad, expected=False)
        self.assertIn('exit:20', record['trace'])
        self.assertNotEqual(record, dict(CASES)['verified-reset-zero'])

    def test_real_main_uses_exit_not_return_to_crt(self):
        texts = dict(self.texts)
        old = '_exit(fwup_resident_run(argc, argv, environment));'
        self.assertEqual(texts['main'].count(old), 1)
        texts['main'] = texts['main'].replace(old, 'return fwup_resident_run(argc, argv, environment);')
        bad = self.compile(texts, 'unsafe-crt-return')
        if self.runtime.exists(): shutil.rmtree(self.runtime)
        result = subprocess.run([str(bad), 'safe-prewrite'], capture_output=True, text=True, timeout=6)
        self.assertEqual(result.returncode, 97, result.stderr)
        self.assertEqual(result.stdout, '')

    def test_k2p_profile_make_variables_include_guard_and_static_helper(self):
        make = shutil.which('gmake') or shutil.which('make')
        print_make = self.base / 'print.mk'
        print_make.write_text('__print:\n\t@printf "%s\\n" "$(FWUP_EXEC)" "$(CFLAGS)"\n')
        for product, selected in [('\"K2P\"', True), ('\"K2P-USB\"', True), ('K2P', True), ('\"OTHER\"', False)]:
            with self.subTest(product=product):
                result = subprocess.run([make, '-s', '-f', str(ROOT / SOURCE_PATHS['makefile']),
                    'CONFIG_FIRMWARE_PRODUCT_ID=' + product,
                    '-f', str(print_make), '__print'],
                    cwd=ROOT / 'trunk/user/mtd_write', capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = result.stdout.splitlines()
                self.assertEqual(lines[0] == 'fw_upgrade', selected, result.stdout)
                self.assertEqual('-DMTD_K2P_LEGACY_GUARD=1' in lines[1], selected, result.stdout)

    def test_symlink_ancestor_is_not_admitted(self):
        real = self.base / 'real-parent'; real.mkdir(exist_ok=True)
        alias = self.base / 'alias-parent'
        alias.symlink_to(real, target_is_directory=True)
        runtime = alias / 'runtime'
        binary = self.compile(self.texts, 'alias-root', runtime)
        try:
            record = self.run_case('safe-prewrite', binary, runtime, expected=False)
            self.assertIn('writer-calls:0', record['trace'])
            self.assertIn('exit:21', record['trace'])
        finally:
            alias.unlink()


if __name__ == '__main__': unittest.main()
