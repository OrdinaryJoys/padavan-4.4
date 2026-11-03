"""Defensive current CmdQ lifecycle and ownership checks with inert effects."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import cmd_queue_harness as h

ROOT = Path(__file__).resolve().parents[1]


class CmdQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-cmdq-current-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {k: (ROOT / v).read_text() for k, v in h.SOURCE_PATHS.items()}
        cls.generated = h.generate_source(cls.texts)
        path = cls.directory / 'cmdq.c'; path.write_text(cls.generated)
        cls.binary = cls.directory / 'cmdq'
        result = subprocess.run(['clang', '-std=gnu99', '-Wall', '-Wextra', '-Werror',
                                 '-fsanitize=address,undefined', str(path), '-o', str(cls.binary)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def cases(self, names):
        for name, wanted in h.CASES:
            if name not in names:
                continue
            with self.subTest(case=name):
                result = subprocess.run([str(self.binary), name], check=True, capture_output=True,
                                        text=True, timeout=5)
                self.assertEqual(json.loads(result.stdout), wanted)

    def test_invalid_inputs_are_rejected_before_access_or_copy(self):
        self.cases({'null-adapter', 'null-payload', 'nic-absent'})

    def test_stopped_queue_preflight_avoids_any_allocation(self):
        self.cases({'queue-already-stopped'})

    def test_stop_races_release_owned_allocations_and_report_failure(self):
        self.cases({'stop-after-preflight', 'stop-after-element-allocation',
                    'stop-after-payload-allocation'})

    def test_allocation_failures_return_resources_without_leaks_or_wakeup(self):
        self.cases({'element-allocation-failure', 'payload-allocation-failure',
                    'element-success-with-null', 'payload-success-with-null'})

    def test_zero_length_and_normal_copies_preserve_queue_contract(self):
        self.cases({'zero-length-null', 'zero-length-pointer', 'running-copy',
                    'initialized-copy', 'two-copies-fifo'})

    def test_model_embeds_complete_functions_and_actual_declarations(self):
        for name in h.FUNCTIONS:
            self.assertEqual(self.generated.count(h.extract(self.texts['queue'], name)), 1)
        self.assertEqual(set(h.function_manifest(self.texts)), set(h.FUNCTIONS))
        self.assertEqual(len(h.CASES), 16)
        self.assertEqual(len({n for n, _ in h.CASES}), 16)
        self.assertIn('cmdq->size++;', self.generated)
        with self.assertRaises(ValueError):
            h.generate_source({})
        duplicate = dict(self.texts, queue=self.texts['queue'] + '\n' + h.extract(self.texts['queue'], h.FUNCTIONS[2]))
        with self.assertRaisesRegex(ValueError, 'Unique complete'):
            h.generate_source(duplicate)
