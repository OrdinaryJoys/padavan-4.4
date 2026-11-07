"""Optional FWD lifetime contract; real guards/writers, inert grace periods."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import fwd_lifecycle_harness as h

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ['-std=gnu99', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-pthread']


class FwdLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-fwd-native-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {k: (ROOT / p).read_text() for k, p in h.SOURCE_PATHS.items()}
        cls.code = h.generate_source(cls.texts)
        gcc = shutil.which('gcc-16') or shutil.which('gcc')
        clang = shutil.which('clang')
        if not gcc or not clang:
            raise AssertionError('Genuine GNU compiler and Clang required')
        version = subprocess.check_output([gcc, '--version'], text=True, timeout=10)
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('Genuine GNU compiler required')
        cls.compilers = {'gcc': gcc, 'clang': clang}
        cls.binaries = {n: cls.compile(cls.code, 'current-' + n, n) for n in cls.compilers}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, code, name, compiler, baseline=False):
        p = cls.directory / (name + '.c');p.write_text(code)
        out = p.with_suffix('')
        flags = FLAGS + ['-DBASELINE=' + str(int(baseline))]
        if compiler == 'clang':
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        r = subprocess.run([cls.compilers[compiler], *flags, str(p), '-o', str(out)],
                           capture_output=True, text=True, timeout=60)
        if r.returncode or r.stderr:
            raise AssertionError(r.stderr)
        return out

    @staticmethod
    def run_binary(binary, case):
        return subprocess.run([str(binary), case], capture_output=True, text=True, timeout=10,
                              env=dict(os.environ, ASAN_OPTIONS='halt_on_error=1',
                                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))

    def row(self, binary, case):
        r = self.run_binary(binary, case)
        self.assertEqual((r.returncode, r.stderr), (0, ''), r.stderr)
        row = json.loads(r.stdout)
        self.assertEqual(set(row), {'unsafe_code', 'unsafe_data', 'all_fields', 'rcu_locks', 'srcu_locks',
                                   'rcu_unlocks', 'srcu_unlocks', 'flushes', 'warnings', 'max_writers', 'running', 'pending'})
        self.assertTrue(all(type(v) is int for v in row.values()))
        return row

    def safe_case(self, case):
        result = []
        for compiler, binary in self.binaries.items():
            with self.subTest(compiler=compiler, case=case):
                row = self.row(binary, case)
                self.assertEqual((row['unsafe_code'], row['unsafe_data'], row['all_fields'],
                                  row['running'], row['pending']), (0, 0, 1, 0, 0))
                self.assertEqual(row['rcu_locks'], row['rcu_unlocks'])
                self.assertEqual(row['srcu_locks'], row['srcu_unlocks'])
                result.append(row)
        return result

    def test_empty_fast_path_never_takes_either_reader_or_writer_domain(self):
        for row in self.safe_case('empty'):
            self.assertEqual((row['rcu_locks'], row['srcu_locks'], row['flushes'], row['max_writers']), (0, 0, 0, 0))

    def test_complete_36_member_snapshot_and_repeated_register_retire_work(self):
        for case, flushes in (('all-fields', 2), ('repeat', 6)):
            for row in self.safe_case(case):
                self.assertEqual((row['flushes'], row['max_writers']), (flushes, 1))

    def test_each_ordinary_return_and_goto_releases_process_and_atomic_guards(self):
        for row in self.safe_case('early'):
            self.assertEqual((row['rcu_locks'], row['srcu_locks']), (12, 3))

    def test_controlled_process_atomic_irq_bh_and_irq_disabled_readers_block_retirement(self):
        for case in ('process', 'atomic', 'irq', 'bh', 'irq-off'):
            for row in self.safe_case(case):
                self.assertEqual((row['rcu_locks'], row['srcu_locks']), (0, 1) if case == 'process' else (1, 0))
                self.assertEqual(row['flushes'], 2)

    def test_returned_map_remains_owned_after_callback_until_consumer_scope_exits(self):
        for row in self.safe_case('map'):
            self.assertEqual((row['srcu_locks'], row['flushes']), (1, 2))

    def test_pointer_seen_before_retirement_is_reread_after_domain_acquisition(self):
        for row in self.safe_case('late-reader'):
            self.assertEqual((row['srcu_locks'], row['flushes']), (1, 2))

    def test_concurrent_writers_publish_complete_last_snapshot_and_atomic_writers_refuse(self):
        for row in self.safe_case('writers'):
            self.assertEqual((row['max_writers'], row['flushes']), (1, 3))
        for row in self.safe_case('atomic-writers'):
            self.assertEqual((row['warnings'], row['max_writers'], row['flushes']), (8, 0, 0))

    def test_genuine_fixed60_writers_and_reader_return_before_callback_code_and_map_users(self):
        d = ROOT / 'tests/fixtures/fwd-lifecycle';metadata = json.loads((d / 'manifest.json').read_text())
        self.assertEqual(set(metadata), set(h.BASELINE_SHA256))
        bodies = {}
        for name, digest in h.BASELINE_SHA256.items():
            raw = (d / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            self.assertEqual(metadata[name]['source_commit'], h.BASELINE_COMMIT)
            self.assertEqual(metadata[name]['sha256'], digest)
            bodies[name] = raw.decode()
        for compiler in self.compilers:
            binary = self.compile(h.generate_source(self.texts, bodies), 'historical-' + compiler, compiler, True)
            self.assertEqual(self.row(binary, 'process')['unsafe_code'], 1)
            self.assertEqual(self.row(binary, 'atomic')['unsafe_code'], 1)
            self.assertEqual(self.row(binary, 'map')['unsafe_data'], 1)

    def test_real_guard_writer_and_pointer_lifetime_mutants_are_rejected(self):
        mutants = {
            'no-process-drain': (self.code.replace('synchronize_srcu(&wifi_fwd_srcu);', '(void)synchronize_srcu;'), 'process'),
            'no-atomic-drain': (self.code.replace('synchronize_rcu();', '(void)synchronize_rcu;'), 'irq'),
            'no-work-tail-flush': (self.code.replace('flush_delayed_work(&wifi_fwd_srcu.work);', '(void)flush_delayed_work;'), 'repeat'),
            'no-caller-cleanup': (self.code.replace('__attribute__((cleanup(wifi_fwd_read_end)))', ''), 'early'),
            'atomic-uses-srcu': (self.code.replace('if (in_atomic() || in_interrupt() || irqs_disabled()) {', 'if (0) {'), 'irq'),
            'incomplete-table': (self.code.replace('wifi_fwd_slot = *table;', 'wifi_fwd_slot.wf_fwd_show_entry_hook = table->wf_fwd_show_entry_hook;'), 'all-fields'),
            'no-null-publish': (self.code.replace('rcu_assign_pointer(wifi_fwd_published, NULL);', '(void)wifi_fwd_published;'), 'all-fields'),
            'stale-after-acquire': (self.code.replace('table = srcu_dereference(wifi_fwd_published, &wifi_fwd_srcu);', 'table = &wifi_fwd_slot;'), 'late-reader'),
            'no-writer-lock': (self.code.replace('mutex_lock(&wifi_fwd_writer_lock);', '(void)mutex_lock;').replace('mutex_unlock(&wifi_fwd_writer_lock);', '(void)mutex_unlock;'), 'all-fields'),
        }
        for compiler in self.compilers:
            for name, (code, case) in mutants.items():
                self.assertNotEqual(code, self.code, name)
                binary = self.compile(code, name + '-' + compiler, compiler)
                r = self.run_binary(binary, case)
                with self.subTest(compiler=compiler, mutant=name):
                    if r.returncode == 0:
                        row = json.loads(r.stdout)
                        self.assertTrue(row['all_fields'] != 1 or row['max_writers'] != 1,
                                        'Mutant preserved the fixed semantics: ' + r.stdout)

    def test_all_callers_and_map_scopes_are_bound_without_claiming_full_kernel_execution(self):
        m = h.manifest(self.texts)
        self.assertEqual((m['caller_count'], m['direct_calls'], m['abi_members']), (31, 47, 36))
        self.assertEqual(len(m['source_bound_callers']), 31)
        self.assertFalse(m['all_31_callers_executed'])
        self.assertFalse(m['kernel_rcu_srcu_execution'])
        self.assertFalse(m['provider_module_or_hardware_execution'])
        p = h.parts(self.texts)
        for file, names in h.CALLERS.items():
            name = names[0];body = h.function(self.texts[file], name)
            bad = dict(self.texts);bad[file] = bad[file].replace(body, body.replace('WIFI_FWD_GUARD(wf_fwd_snapshot);', ''))
            with self.assertRaises(ValueError):h.generate_source(bad)
        for file in ('os/linux/rt_profile.c', 'embedded/common/cmm_data.c'):
            self.assertIn('wf_fwd_snapshot->wf_fwd_feedback_map_table', self.texts[file])
        self.assertIn('dont\'t call init_srcu_struct() nor cleanup_srcu_struct()', self.texts['srcu_header'])
        for name in ('__synchronize_srcu', 'process_srcu', 'srcu_reschedule'):
            body = h.function(self.texts['core_srcu'], name)
            self.assertTrue(body)
        self.assertIn('sp->running = false;', h.function(self.texts['core_srcu'], 'srcu_reschedule'))
        for body in (*p['functions'].values(), p['guard'], p['macro']):
            self.assertEqual(self.code.count(body), 1)

    def test_unsupported_srcu_or_license_profiles_fail_compilation_explicitly(self):
        for compiler in self.compilers:
            for name, code, diagnostic in (
                    ('no-srcu', self.code.replace('#define CONFIG_SRCU 1', ''), 'requires CONFIG_SRCU'),
                    ('proprietary', '#define CONFIG_PROPRIETARY_DRIVER 1\n' + self.code, 'GPL-compatible SRCU')):
                p = self.directory / (name + '-' + compiler + '.c');p.write_text(code)
                r = subprocess.run([self.compilers[compiler], *FLAGS, '-DBASELINE=0', str(p), '-o', str(p.with_suffix(''))],
                                   capture_output=True, text=True, timeout=60)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(diagnostic, r.stderr)


if __name__ == '__main__':
    unittest.main()
