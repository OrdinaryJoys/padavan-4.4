"""Actual cyclic RX pool/allocator/getter identity checks, with inert DMA."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import rx_pool_harness as h

ROOT = Path(__file__).resolve().parents[1]


class RxPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-current-rx-pool-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {k: (ROOT / v).read_text() for k, v in h.SOURCE_PATHS.items()}
        cls.generated = h.generate_source(cls.texts)
        path = cls.directory / 'pool.c'; path.write_text(cls.generated)
        cls.binary = cls.directory / 'pool'
        result = subprocess.run(['clang', '-std=gnu99', '-Wall', '-Wextra', '-Werror',
                                 '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter',
                                 '-fsanitize=address,undefined', str(path), '-o', str(cls.binary)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def cases(self, names):
        for name in h.CASE_NAMES:
            if name not in names:
                continue
            with self.subTest(case=name):
                result = subprocess.run([str(self.binary), name], check=True, capture_output=True,
                                        text=True, timeout=5)
                row = json.loads(result.stdout)
                self.assertEqual(row, h.EXPECTED_ROWS[name])
                self.assertTrue(all(type(x) is int for x in row))

    def test_discarded_descriptors_preserve_fifo_mapping_owners(self):
        self.cases({'pool-drop-first-then-two-valid', 'pool-drop-zero-then-two-valid',
                    'pool-drop-chain-then-valid', 'pool-discard-wait-and-resume'})

    def test_null_reservations_preserve_head_and_owned_descriptor(self):
        self.cases({'pool-null-reserve-and-retry', 'pool-null-head-helpers'})

    def test_scatter_reservation_failures_resume_discard_at_owned_follower(self):
        self.cases({'pool-null-follower-and-resume', 'pool-null-expansion-and-resume'})

    def test_wraparound_and_io_getter_preserve_distinct_live_mappings(self):
        self.cases({'pool-wrap-eight-valid', 'pool-io-drop-first-then-two-valid'})

    def test_model_binds_complete_current_functions_and_fixed_rows(self):
        self.assertEqual(set(h.EXPECTED_ROWS), set(h.CASE_NAMES))
        self.assertEqual(len(h.CASE_NAMES), 10)
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key], name)), 1)
        self.assertEqual(len(h.function_manifest(self.texts)), 13)
        self.assertIn('duplicate live DMA mapping owner', self.generated)
        with self.assertRaises(ValueError):
            h.generate_source({})
        with self.assertRaises(ValueError):
            h.generate_source(self.texts, variant='legacy')
