"""MDIO failures and fresh EEE state in the actual forced-variant poller."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import raeth_phy_poll_harness as h

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ['-std=gnu99', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter']


class RaethPhyPollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='raeth-phy-poll-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {k: (ROOT / p).read_text() for k, p in h.SOURCE_PATHS.items()}
        cls.code = h.generate_source(cls.texts)
        cls.compilers = {'gcc': shutil.which('gcc-16') or shutil.which('gcc'), 'clang': shutil.which('clang')}
        if not all(cls.compilers.values()):
            raise AssertionError('GNU GCC and Clang required')
        version = subprocess.check_output([cls.compilers['gcc'], '--version'], text=True, timeout=10)
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('Genuine GNU GCC required')
        cls.binaries = {label: cls.build(cls.code, label, label) for label in cls.compilers}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def build(cls, code, name, label='clang'):
        source = cls.directory / (name + '.c'); source.write_text(code)
        binary = source.with_suffix('')
        flags = FLAGS + (['-fsanitize=address,undefined', '-fno-sanitize-recover=all'] if label == 'clang' else [])
        run = subprocess.run([cls.compilers[label], *flags, str(source), '-o', str(binary)], capture_output=True, text=True, timeout=60)
        if run.returncode or run.stderr:
            raise AssertionError(run.stderr)
        return binary

    def run_case(self, binary, case):
        run = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=5,
                             env=dict(os.environ, ASAN_OPTIONS='halt_on_error=1:symbolize=0', UBSAN_OPTIONS='halt_on_error=1'))
        self.assertEqual((run.returncode, run.stderr), (0, ''), run.stderr)
        return json.loads(run.stdout)

    def test_all_twenty_complete_failure_recovery_and_link_samples(self):
        for label, binary in self.binaries.items():
            for case in h.LEGACY_CASE_NAMES:
                with self.subTest(compiler=label, case=case):
                    self.assertEqual(self.run_case(binary, case), h.EXPECTED_ROWS[case])

    def test_whole_poller_and_explicit_forced_variant_source_scope(self):
        self.assertEqual((len(h.FUNCTION_SOURCES), len(h.CASE_NAMES), len(h.FIELDS)), (2, 52, 7))
        self.assertEqual(set(h.CASE_NAMES), set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.source_only_manifest(self.texts)), 3)
        self.assertEqual(self.code.count(h.function(self.texts['raeth'], 'phy_polling_thread')), 1)
        self.assertEqual(self.code.count(h.function(self.texts['mii_header'], 'mii_resolve_flowctrl_fdx')), 1)
        opened = h.function(self.texts['raeth'], 'ei_open')
        self.assertIn('if (ei_local->chip_name == LEOPARD_FE)', opened)
        self.assertIn('kthread_create(phy_polling_thread, NULL, "phy_polling_kthread")', opened)
        self.assertIn('CONFIG_SOC_MT7621=y', self.texts['config'].splitlines())
        self.assertTrue(h.MODEL_VARIANT['LEOPARD_forced_variant_not_shipping_K2P_MT7621'])
        self.assertTrue(h.MODEL_VARIANT['hardware_link_EEE_ABI_or_timing_not_proven'])

    def test_all_16_advertisement_pairs_resolve_directionally_and_half_duplex_disables_pause(self):
        self.assertEqual((len(h.LEGACY_CASE_NAMES), len(h.PAUSE_CASE_NAMES)), (20, 32))
        for label, binary in self.binaries.items():
            for case in h.PAUSE_CASE_NAMES:
                with self.subTest(compiler=label, case=case):
                    self.assertEqual(self.run_case(binary, case), h.EXPECTED_ROWS[case])

    def test_fixed_old_whole_body_reproduces_stale_eee_and_false_state_after_failed_reads(self):
        fixture = ROOT / 'tests/fixtures/raeth-phy-poll'
        metadata = json.loads((fixture / 'manifest.json').read_text())['phy_polling_thread.c']
        raw = (fixture / 'phy_polling_thread.c').read_bytes()
        self.assertEqual(metadata['source_commit'], '60ae6bf98bd46b68c648620c599f1aa78073131e')
        self.assertEqual(metadata['sha256'], '7e04459e50d870e059a63754715d3fc5c72d8a573c5aea0a1204a6a26a32375c')
        self.assertEqual(metadata['sha256'], hashlib.sha256(raw).hexdigest())
        old = raw.decode().rstrip('\n')
        current = h.function(self.texts['raeth'], 'phy_polling_thread')
        for label in self.compilers:
            binary = self.build(self.code.replace(current, old, 1), 'historical-' + label, label)
            self.assertEqual(self.run_case(binary, 'eee-clears')['value'], 0x2105e3fb)
            self.assertEqual(self.run_case(binary, 'fail-link')['downs'], 1)
            self.assertEqual(self.run_case(binary, 'fail-peer-eee')['writes'], 2)
            self.assertEqual(self.run_case(binary, 'pause-fdx-0-0')['value'], 0x2105e33b)
            self.assertEqual(self.run_case(binary, 'pause-fdx-2-2')['value'], 0x2105e33b)
            self.assertEqual(self.run_case(binary, 'pause-fdx-3-2')['value'], 0x2105e30b)
            self.assertEqual(self.run_case(binary, 'pause-fdx-2-3')['value'], 0x2105e30b)
            self.assertEqual(self.run_case(binary, 'pause-hdx-3-3')['value'], 0x2105e331)

    def test_missing_duplicate_bodies_and_unreviewed_profile_are_rejected(self):
        for name, key in {**h.FUNCTION_SOURCES, **h.SOURCE_ONLY_FUNCTION_SOURCES}.items():
            bad = dict(self.texts); body = h.function(bad[key], name)
            bad[key] += '\n' + body
            with self.assertRaises(ValueError):
                h.function(bad[key], name)
        with self.assertRaises(ValueError):
            h.generate_source({})
        bad = dict(self.texts); bad['config'] = bad['config'].replace('CONFIG_SOC_MT7621=y', '# CONFIG_SOC_MT7621 is not set')
        with self.assertRaises(ValueError):
            h.generate_source(bad)
        bad = dict(self.texts); bad['header'] = bad['header'].replace('#define PHY_POLLING_MS\t\t(1000)', '#define PHY_POLLING_MS 1')
        with self.assertRaises(ValueError):
            h.generate_source(bad)

    def reject(self, before, after, case, label):
        self.assertEqual(self.code.count(before), 1)
        binary = self.build(self.code.replace(before, after, 1), label)
        self.assertNotEqual(self.run_case(binary, case), h.EXPECTED_ROWS[case])

    def test_each_of_six_ignored_read_failures_is_observable(self):
        calls = (
            ('mii_mgr_read(0x0, 0x1, &link_status)', 'fail-link'),
            ('mii_mgr_read(0x0, 0x4, &fc_phy)', 'fail-local-pause'),
            ('mii_mgr_read(0x0, 0x5, &fc_lp)', 'fail-peer-pause'),
            ('mii_mgr_read_cl45(0, 0x1e, 0xa2, &link_speed)', 'fail-speed'),
            ('mii_mgr_read_cl45(0, 0x7, 0x3c, &local_eee)', 'fail-local-eee'),
            ('mii_mgr_read_cl45(0, 0x7, 0x3d, &lp_eee)', 'fail-peer-eee'),
        )
        for index, (call, case) in enumerate(calls):
            with self.subTest(call=call):
                self.reject('!' + call, '(' + call + ', 0)', case, 'ignored-mdio-' + str(index))

    def test_sticky_eee_and_late_stop_mutations_are_rejected(self):
        changed = self.code.replace('unsigned int val_tmp, pause;', 'unsigned int val_tmp = 1, pause;', 1)
        self.assertEqual(changed.count('\t\t\tval_tmp = 1;'), 1)
        changed = changed.replace('\t\t\tval_tmp = 1;', '', 1)
        binary = self.build(changed, 'sticky-eee')
        self.assertNotEqual(self.run_case(binary, 'eee-clears'), h.EXPECTED_ROWS['eee-clears'])
        self.reject('for (;;) {\n\t\tif (kthread_should_stop())\n\t\t\tbreak;',
                    'for (;;) {', 'stopped', 'late-stop')

    def test_pause_equality_swapped_direction_and_half_duplex_mutants_are_rejected(self):
        self.reject('pause = mii_resolve_flowctrl_fdx(fc_phy, fc_lp);',
                    'pause = ((fc_phy & 0xc00) == (fc_lp & 0xc00)) ? (FLOW_CTRL_RX | FLOW_CTRL_TX) : 0;',
                    'pause-fdx-0-0', 'false-pause-equality')
        self.reject('if (pause & FLOW_CTRL_RX)\n\t\t\t\t\tval_tmp |= BIT(5);',
                    'if (pause & FLOW_CTRL_RX)\n\t\t\t\t\tval_tmp |= BIT(4);',
                    'pause-fdx-3-2', 'wrong-rx-bit')
        self.reject('if (pause & FLOW_CTRL_TX)\n\t\t\t\t\tval_tmp |= BIT(4);',
                    'if (pause & FLOW_CTRL_TX)\n\t\t\t\t\tval_tmp |= BIT(5);',
                    'pause-fdx-2-3', 'wrong-tx-bit')
        self.reject('if (duplex) {', 'if (1) { (void)duplex;',
                    'pause-hdx-3-3', 'half-duplex-pause')

    def test_failed_link_query_is_not_a_force_down_event(self):
        self.reject('if (!mii_mgr_read(0x0, 0x1, &link_status))\n\t\t\tgoto poll_wait;',
                    'if (!mii_mgr_read(0x0, 0x1, &link_status)) { set_ge2_force_link_down(); goto poll_wait; }',
                    'fail-link', 'false-link-down')

    def test_unknown_case_is_rejected_before_polling(self):
        for binary in self.binaries.values():
            run = subprocess.run([str(binary), 'unreviewed'], capture_output=True, text=True, timeout=5)
            self.assertEqual((run.returncode, run.stdout, run.stderr), (91, '', ''))
