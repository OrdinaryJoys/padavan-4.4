#!/usr/bin/env python3
"""Actual legacy main/functions, real read-only table parser, inert MTD/reset."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import legacy_firmware_harness as harness

ROOT = Path(__file__).resolve().parents[1]


class LegacyFirmwareGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-legacy-admission-')
        cls.base = Path(cls.temp.name).resolve()
        cls.texts = {key: (ROOT / path).read_text() for key, path in harness.SOURCE_PATHS.items()}
        cls.binaries = {}
        for enabled in (True, False):
            name = 'enabled' if enabled else 'other-board'
            code = harness.generate_source(cls.texts, str(cls.base / (name + '-fixtures')), os.geteuid(), enabled)
            path = cls.base / (name + '.c'); path.write_text(code)
            binary = cls.base / name
            result = subprocess.run([shutil.which('clang') or shutil.which('cc'), '-std=gnu99', '-Os',
                                     '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                                     '-Wno-unused-function', '-Wno-sign-compare',
                                     '-fsanitize=address,undefined', '-g', str(path), '-o', str(binary)],
                                    text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.binaries[enabled] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, name, enabled=True):
        result = subprocess.run([str(self.binaries[enabled]), name], text=True, capture_output=True,
                                timeout=5, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('AddressSanitizer', result.stderr)
        self.assertNotIn('runtime error:', result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record['case'], name)
        return record

    def assert_rejected_before_effects(self, name):
        record = self.run_case(name)
        self.assertEqual(record, {'case': name, 'returncode': 21, 'trace': '',
                                  'device_reads': 0, 'corrupted': 0})

    def test_old_stage_protocol_is_never_a_new_writer_entry(self):
        for name in ('old-stage-protocol', 'malformed-stage-protocol'):
            self.assert_rejected_before_effects(name)

    def test_firmware_write_with_and_without_reboot_is_blocked(self):
        for name in ('firmware-write', 'firmware-write-reboot'):
            self.assert_rejected_before_effects(name)

    def test_char_block_directory_short_and_symlink_aliases_are_blocked(self):
        for name in harness.CASE_NAMES[4:12]:
            self.assert_rejected_before_effects(name)

    def test_firmware_overlap_and_all_partition_are_blocked(self):
        for name in ('kernel-overlap', 'rootfs-overlap', 'all-label', 'all-device'):
            self.assert_rejected_before_effects(name)

    def test_fix_reset_and_jffs_commands_cannot_mutate_firmware(self):
        for name in harness.CASE_NAMES[16:21]:
            self.assert_rejected_before_effects(name)

    def test_preerase_is_admitted_before_primary_write_or_read(self):
        for name in ('preerase-firmware', 'preerase-firmware-read', 'colon-preerase'):
            self.assert_rejected_before_effects(name)

    def test_colon_target_cannot_hide_firmware_after_storage(self):
        self.assert_rejected_before_effects('colon-firmware')

    def test_even_readonly_or_storage_reboot_flags_are_blocked(self):
        for name in ('reboot-storage-read', 'reboot-storage-write'):
            self.assert_rejected_before_effects(name)

    def test_unknown_and_regular_path_targets_are_not_mtd_authority(self):
        for name in ('unknown-target', 'regular-file-target'):
            self.assert_rejected_before_effects(name)

    def test_bad_duplicate_overflow_truncated_and_unknown_tables_fail_closed(self):
        for name in (*harness.CASE_NAMES[29:35], 'missing-partition-table', 'oversized-partition-line'):
            self.assert_rejected_before_effects(name)

    def test_preerase_argument_array_is_bounded_before_the_terminator(self):
        for enabled in (True, False):
            row = self.run_case('too-many-preerase', enabled=enabled)
            self.assertEqual(row, {'case': 'too-many-preerase', 'returncode': 21, 'trace': '',
                                   'device_reads': 0, 'corrupted': 0})

    def test_storage_and_nvram_writes_remain_admitted_without_reboot(self):
        for name in ('safe-storage-write', 'safe-nvram-write', 'safe-storage-device'):
            row = self.run_case(name)
            self.assertEqual(row['returncode'], 0)
            trace = row['trace'].split(',')
            self.assertIn('write', trace)
            self.assertIn('writable-open', trace)
            self.assertNotIn('system-reboot', trace)
            self.assertNotIn('raw-reboot', trace)
            self.assertEqual(row['corrupted'], 0)

    def test_config_erase_retained_and_readonly_firmware_dump_needs_no_table(self):
        row = self.run_case('safe-config-erase')
        self.assertEqual(row['returncode'], 0)
        self.assertIn('erase', row['trace'].split(','))
        for name in ('readonly-firmware-dump', 'readonly-bad-table'):
            row = self.run_case(name)
            self.assertEqual(row['returncode'], 0)
            self.assertEqual(row['trace'], 'sync,dump,sync')

    def test_other_board_disabled_control_exposes_original_silent_corruption(self):
        row = self.run_case('disabled-guard-silent-corruption', enabled=False)
        self.assertEqual(row['returncode'], 0)
        self.assertEqual(row['corrupted'], 1)
        self.assertEqual(row['device_reads'], 0)
        self.assertTrue(row['trace'].endswith('system-reboot,sleep2,raw-reboot'))
        self.assertIn('write', row['trace'].split(','))

    def test_generator_embeds_actual_bodies_once_and_no_unknown_source_keys(self):
        code = harness.generate_source(self.texts, str(self.base / 'identity'), os.geteuid())
        for data in harness.actual_functions(self.texts).values():
            self.assertEqual(code.count(data['body']), 1)
        with self.assertRaises(ValueError):
            harness.generate_source({**self.texts, 'extra': ''}, '/private/tmp/test', 0)
        with self.assertRaises(ValueError):
            harness.generate_source(self.texts, 'relative', 0)


if __name__ == '__main__':
    unittest.main()
