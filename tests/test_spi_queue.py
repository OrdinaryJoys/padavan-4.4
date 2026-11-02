#!/usr/bin/env python3
"""Queue failure ownership, completion and PM balance via actual C bodies."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import spi_queue_harness as harness

ROOT = Path(__file__).resolve().parents[1]


class SpiQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-spi-queue-')
        cls.base = Path(cls.temp.name)
        cls.texts = {key: (ROOT / path).read_text()
                     for key, path in harness.SOURCE_PATHS.items()}
        cls.compiler = shutil.which('clang') or shutil.which('cc')
        if not cls.compiler:
            raise RuntimeError('Host C compiler required')
        cls.expected = dict(harness.CASES)
        cls.binaries = {
            'current': cls.compile(cls.texts, 'current'),
            'baseline': cls.compile(cls.texts, 'baseline', baseline=True),
        }

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, texts, name, baseline=False, raw=None):
        source, exe = cls.base / (name + '.c'), cls.base / name
        source.write_text(raw if raw is not None else harness.generate_source(
            texts, baseline=baseline))
        command = [cls.compiler, '-std=gnu89', '-O1', '-g', '-Wall', '-Wextra',
                   '-Werror', '-Wno-unused-function', '-Wno-unused-variable',
                   '-Wno-unused-parameter', '-fsanitize=address,undefined',
                   '-fno-sanitize-recover=undefined', '-fno-omit-frame-pointer',
                   str(source), '-o', str(exe)]
        compiled = subprocess.run(command, capture_output=True, text=True)
        if compiled.returncode:
            raise AssertionError((name, compiled.stderr))
        return exe

    def run_case(self, name, binary='current'):
        exe = self.binaries.get(binary, binary)
        run = subprocess.run([str(exe), name], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, (name, run.stderr))
        self.assertEqual(run.stderr, '', (name, run.stderr))
        return json.loads(run.stdout)

    def check(self, names):
        for name in names:
            with self.subTest(case=name):
                self.assertEqual(self.run_case(name), self.expected[name])

    def mutate_pump(self, name, old, new, count=1):
        texts = copy.copy(self.texts)
        before = harness.extract(texts['core'], '__spi_pump_messages')
        self.assertGreaterEqual(before.count(old), count)
        after = before.replace(old, new, count)
        self.assertNotEqual(before, after)
        texts['core'] = texts['core'].replace(before, after, 1)
        return self.compile(texts, name)

    def test_exact_manifest_embeds_actual_bodies_and_runtime_pm_flag_fragment(self):
        actual = harness.actual_functions(self.texts)
        self.assertEqual(len(actual), 17)
        self.assertEqual(set(actual), set(harness.BASELINE_FUNCTIONS))
        generated = harness.generate_source(self.texts)
        for name, entry in actual.items():
            with self.subTest(function=name):
                self.assertEqual(entry['source_key'], next(
                    key for key, names in harness.FUNCTIONS.items() if name in names))
                self.assertIn(entry['body'], generated)
                if name != '__spi_pump_messages':
                    self.assertEqual(entry['body'], harness.BASELINE_FUNCTIONS[name])
        self.assertEqual(hashlib.sha256(harness.production_fragments(
            self.texts).encode()).hexdigest(), harness.PRODUCTION_FRAGMENT_SHA256)
        self.assertIn('atomic_add_unless', actual['pm_runtime_put_noidle']['body'])
        self.assertEqual(len(harness.CASES), 33)
        self.assertEqual(len(harness.BASELINE_CASES), 8)
        for name, row in harness.CASES + harness.BASELINE_CASES:
            self.assertEqual(name, row['case'])
            self.assertEqual(len(row), 43)
            for key, value in row.items():
                self.assertIs(type(value), str if key in ('case', 'sequence') else int)

    def test_normal_controller_and_positive_pm_resume_keep_compatibility(self):
        self.check(('normal-mt7621', 'normal-pm', 'normal-pm-positive',
                    'bus-locked', 'async-worker'))

    def test_pm_get_failures_complete_with_original_error_and_retry_next_message(self):
        self.check(('pm-fail-sync', 'pm-fail-persistent', 'pm-fail-queued',
                    'pm-fail-callback-requeue'))

    def test_prepare_failures_never_unprepare_failed_hardware_or_put_twice(self):
        self.check(('prepare-fail-sync', 'prepare-fail-no-pm',
                    'prepare-fail-persistent', 'prepare-fail-queued',
                    'prepare-fail-callback-requeue'))

    def test_later_message_failures_preserve_active_batch_ownership(self):
        self.check(('message-fail', 'map-fail', 'already-busy',
                    'message-fail-already-busy'))

    def test_actual_unmap_and_dummy_restore_bodies_execute_for_mapped_messages(self):
        self.check(('normal-dma', 'normal-dma-dummy'))
        row = self.run_case('normal-dma-dummy')
        self.assertEqual((row['can_dma_calls'], row['dma_unmaps'],
                          row['dummy_restored'], row['dummy_frees']), (1, 2, 2, 2))

    def test_hardware_errors_do_not_unmap_current_message_using_prior_dma_flag(self):
        self.check(('pm-fail-prior-dma', 'prepare-fail-prior-dma',
                    'dma-then-pm-fail', 'dma-then-prepare-fail'))
        for name in ('dma-then-pm-fail', 'dma-then-prepare-fail'):
            row = self.run_case(name)
            self.assertEqual((row['result'], row['result2'], row['returned'],
                              row['completed']), (0, -5, 2, 2))
            self.assertEqual((row['can_dma_calls'], row['dma_unmaps'],
                              row['cur_msg_mapped']), (1, 2, 0))

    def test_missing_mapping_reset_exposes_unmapped_transfer_after_hardware_error(self):
        binary = self.mutate_pump('stale-dma-flag',
                                 '\t\t\tmaster->cur_msg_mapped = false;\n', '', count=2)
        for name in ('pm-fail-prior-dma', 'prepare-fail-prior-dma'):
            with self.subTest(case=name):
                row = self.run_case(name, binary)
                self.assertEqual((row['cur_msg_mapped'], row['can_dma_calls'],
                                  row['unmapped_dma_visits'],
                                  row['unsafe_dma_callback']), (1, 1, 2, 1))
                # An unmapped SG has orig_nents=0: the model distinguishes
                # reaching the DMA helper from actually releasing an SG.
                self.assertEqual(row['dma_unmaps'], 0)

    def test_true_unmap_guard_and_dummy_restore_mutations_are_observable(self):
        texts = copy.copy(self.texts)
        before = harness.actual_functions(texts)['__spi_unmap_msg']['body']
        needle = '\tif (!master->cur_msg_mapped || !master->can_dma)\n\t\treturn 0;'
        self.assertEqual(before.count(needle), 1)
        texts['core'] = texts['core'].replace(before, before.replace(needle, ''), 1)
        binary = self.compile(texts, 'unmap-without-mapped-guard')
        row = self.run_case('pm-fail-prior-dma', binary)
        self.assertEqual((row['cur_msg_mapped'], row['can_dma_calls'],
                          row['unmapped_dma_visits']), (0, 1, 2))
        texts = copy.copy(self.texts)
        before = harness.extract(texts['core'], 'spi_unmap_msg')
        after = before.replace('xfer->tx_buf = NULL;', '(void)0;').replace(
            'xfer->rx_buf = NULL;', '(void)0;')
        self.assertNotEqual(before, after)
        texts['core'] = texts['core'].replace(before, after, 1)
        binary = self.compile(texts, 'unmap-without-dummy-restore')
        self.assertEqual(self.run_case('normal-dma-dummy', binary)['dummy_restored'], 0)

    def test_idle_worker_deferral_stopped_queue_validation_and_destroy_boundaries(self):
        self.check(('empty-idle', 'idle-defer', 'current-message-defer',
                    'idling-defer', 'stopped-sync', 'validate-error',
                    'destroy-idle', 'destroy-busy-boundary'))

    def test_driver_without_finalize_remains_an_explicit_unfixed_contract_boundary(self):
        self.check(('driver-contract-boundary',))
        row = self.run_case('driver-contract-boundary')
        self.assertEqual((row['wait_pending'], row['returned'], row['cur_msg']),
                         (1, 0, 1))

    def test_literal_baseline_reproduces_pending_waits_without_abandoned_callbacks(self):
        for name, row in harness.BASELINE_CASES:
            with self.subTest(case=name):
                self.assertEqual(self.run_case(name, 'baseline'), row)
                if 'fail' in name:
                    self.assertEqual((row['wait_pending'], row['cur_msg']), (1, 1))
                    self.assertEqual(row['returned'], row['completed'])
                    if not name.startswith('dma-then-'):
                        self.assertEqual((row['returned'], row['completed']), (0, 0))
        for name, body in harness.BASELINE_FUNCTIONS.items():
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),
                             harness.BASELINE_FUNCTIONS_SHA256[name])
        self.assertEqual(hashlib.sha256(harness.BASELINE_FRAGMENTS.encode()).hexdigest(),
                         harness.BASELINE_FRAGMENTS_SHA256)

    def test_embedded_baseline_matches_repository_commit_when_history_is_available(self):
        old = {}
        for key, path in harness.SOURCE_PATHS.items():
            show = subprocess.run(['git', 'show', harness.BASELINE_COMMIT + ':' + path],
                                  cwd=ROOT, capture_output=True, text=True)
            if show.returncode:
                self.skipTest('Pinned historical commit is absent from shallow checkout')
            old[key] = show.stdout
        self.assertEqual({n: e['body'] for n, e in harness.actual_functions(old).items()},
                         harness.BASELINE_FUNCTIONS)
        self.assertEqual(harness.production_fragments(old), harness.BASELINE_FRAGMENTS)

    def test_missing_finalize_mutation_retains_current_message_and_pending_wait(self):
        needle = ('\t\t\tmaster->cur_msg->status = ret;\n'
                  '\t\t\tspi_finalize_current_message(master);\n')
        binary = self.mutate_pump('no-error-finalize', needle, '', count=2)
        for case in ('pm-fail-sync', 'prepare-fail-sync'):
            with self.subTest(case=case):
                row = self.run_case(case, binary)
                self.assertEqual((row['wait_pending'], row['returned'],
                                  row['cur_msg'], row['completed']), (1, 0, 1, 0))

    def test_missing_busy_reset_mutation_skips_retry_and_causes_invalid_idle_cleanup(self):
        binary = self.mutate_pump('no-busy-reset',
                                 '\t\t\tmaster->busy = false;\n', '', count=2)
        for case in ('pm-fail-sync', 'prepare-fail-sync'):
            with self.subTest(case=case):
                row = self.run_case(case, binary)
                self.assertGreater(row['unsafe_transfer'], 0)
                self.assertGreater(row['invalid_unprepare'], 0)
                self.assertGreater(row['pm_underflow'], 0)
                self.assertNotEqual(row, self.expected[case])

    def test_upstream_only_finalize_transplant_is_insufficient_for_local_busy_lifetime(self):
        # Reproduce the 2019 upstream status/finalize addition in the old local
        # lifecycle. Local busy/PM cleanup requires the additional ownership fix.
        texts = copy.copy(self.texts)
        before = harness.extract(texts['core'], '__spi_pump_messages')
        old = harness.BASELINE_FUNCTIONS['__spi_pump_messages']
        needle = ('\t\t\tif (master->auto_runtime_pm)\n'
                  '\t\t\t\tpm_runtime_put(master->dev.parent);\n'
                  '\t\t\treturn;')
        added = needle.replace('\t\t\treturn;',
                               '\t\t\tmaster->cur_msg->status = ret;\n'
                               '\t\t\tspi_finalize_current_message(master);\n'
                               '\t\t\treturn;')
        self.assertEqual(old.count(needle), 1)
        texts['core'] = texts['core'].replace(before, old.replace(needle, added), 1)
        binary = self.compile(texts, 'upstream-only-finalize')
        row = self.run_case('prepare-fail-sync', binary)
        self.assertEqual((row['returned'], row['completed']), (2, 2))
        self.assertEqual((row['unsafe_transfer'], row['invalid_unprepare'],
                          row['pm_underflow']), (1, 1, 1))

    def test_failed_get_without_put_noidle_leaks_a_real_pm_entry_reference(self):
        binary = self.mutate_pump('get-ref-leak',
                                 '\t\t\tpm_runtime_put_noidle(master->dev.parent);\n', '')
        row = self.run_case('pm-fail-sync', binary)
        self.assertEqual((row['pm_usage'], row['pm_get'], row['pm_suspend']), (1, 2, 0))

    def test_duplicate_failure_put_is_detected_by_actual_pm_entry_accounting(self):
        needle = '\t\t\tpm_runtime_put_noidle(master->dev.parent);\n'
        binary = self.mutate_pump('double-pm-put', needle,
                                 needle + '\t\t\tpm_runtime_put(master->dev.parent);\n')
        row = self.run_case('pm-fail-sync', binary)
        self.assertGreater(row['pm_underflow'], 0)
        self.assertNotEqual(row, self.expected['pm-fail-sync'])

    def test_original_failure_status_cannot_be_hidden_by_success(self):
        binary = self.mutate_pump('hidden-failure-status',
                                 '\t\t\tmaster->cur_msg->status = ret;',
                                 '\t\t\tmaster->cur_msg->status = 0;', count=2)
        for case in ('pm-fail-sync', 'prepare-fail-sync'):
            with self.subTest(case=case):
                self.assertEqual(self.run_case(case, binary)['result'], 0)
                self.assertLess(self.expected[case]['result'], 0)

    def test_actual_pm_flag_changes_are_observed_not_recreated_by_mock_wrappers(self):
        texts = copy.copy(self.texts)
        old = harness.extract(texts['pm_header'], 'pm_runtime_get_sync')
        self.assertIn('RPM_GET_PUT', old)
        texts['pm_header'] = texts['pm_header'].replace(old, old.replace('RPM_GET_PUT', '0'), 1)
        binary = self.compile(texts, 'get-without-reference-flag')
        row = self.run_case('normal-pm', binary)
        self.assertGreater(row['lock_errors'], 0)
        self.assertEqual(row['unsafe_transfer'], 1)
        self.assertGreater(row['pm_underflow'], 0)

    def test_pump_reentry_before_error_finalize_cannot_take_current_message(self):
        # An eager competing pump runs immediately after busy is cleared under
        # queue_lock. The still-owned cur_msg must make that pump return.
        raw = harness.generate_source(self.texts)
        needle = ('static void model_unlock(struct model_lock*l)'
                  '{if(l->depth!=1)locks_bad++;l->depth--;}')
        replacement = ('static int eager_pump_once;\n'
                       'static void model_unlock(struct model_lock*l)'
                       '{if(l->depth!=1)locks_bad++;l->depth--;'
                       'if(l==&master.queue_lock&&!master.busy&&master.cur_msg&&!eager_pump_once)'
                       '{eager_pump_once=1;__spi_pump_messages(&master,true);}}')
        self.assertEqual(raw.count(needle), 1)
        binary = self.compile(self.texts, 'eager-error-pump', raw=raw.replace(needle, replacement))
        for case in ('pm-fail-sync', 'prepare-fail-sync',
                     'pm-fail-queued', 'prepare-fail-queued'):
            with self.subTest(case=case):
                self.assertEqual(self.run_case(case, binary), self.expected[case])

    def test_changed_literal_baseline_and_wrong_manifests_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Exact SPI queue source manifest'):
            harness.generate_source({'core': self.texts['core']})
        with self.assertRaisesRegex(ValueError, 'Typed generation arguments'):
            harness.generate_source(self.texts, baseline=1)
        changed = dict(harness.BASELINE_FUNCTIONS)
        changed['__spi_pump_messages'] += '\n'
        with mock.patch.object(harness, 'BASELINE_FUNCTIONS', changed):
            with self.assertRaisesRegex(ValueError, 'Changed literal SPI queue baseline'):
                harness.generate_source(self.texts, baseline=True)
        with mock.patch.object(harness, 'BASELINE_FRAGMENTS', harness.BASELINE_FRAGMENTS + '\n'):
            with self.assertRaisesRegex(ValueError, 'Changed literal SPI queue PM flags'):
                harness.generate_source(self.texts, baseline=True)


if __name__ == '__main__':
    unittest.main()
