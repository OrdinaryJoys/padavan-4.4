"""Actual flash+queue: no postwrite parent stdio/path/free tail."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import resident_consumer_harness as h

ROOT = Path(__file__).resolve().parents[1]


class ResidentConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-resident-consumer-')
        cls.base = Path(cls.temp.name).resolve()
        cls.fixture = cls.base / 'fixture'
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        cls.code = h.generate_source(cls.texts, str(cls.fixture), os.geteuid())
        source = cls.base / 'consumer.c'; source.write_text(cls.code)
        cls.binary = cls.base / 'consumer'
        result = subprocess.run(['clang', '-std=gnu99', '-Os', '-Wall', '-Wextra', '-Werror',
                                 '-Wno-unused-parameter', '-Wno-unused-function',
                                 '-fsanitize=address,undefined', '-g', str(source), '-o', str(cls.binary)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_cases(self, names):
        for name, wanted in h.CASES:
            if name not in names:
                continue
            with self.subTest(case=name):
                if self.fixture.exists():
                    shutil.rmtree(self.fixture)
                result = subprocess.run([str(self.binary), name], capture_output=True, text=True,
                                        timeout=8, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('AddressSanitizer', result.stderr)
                self.assertNotIn('runtime error:', result.stderr)
                self.assertEqual(json.loads(result.stdout), wanted)

    def test_unknown_and_verified_return_skip_all_tail_and_second_fs_queries(self):
        self.run_cases({'consumer-unknown', 'consumer-verified-return'})

    def test_signal_exec_and_untrusted_safe_records_never_resume_tail(self):
        self.run_cases({'consumer-signal', 'consumer-exec-failure', 'consumer-untrusted20', 'consumer-mismatched20'})

    def test_authenticated_prewrite_recovers_and_preserves_full_drain_rearm(self):
        self.run_cases({'consumer-safe20'})

    def test_preparation_aborts_retain_original_queue_cleanup(self):
        self.run_cases({'consumer-first-save-abort', 'consumer-hook-abort'})

    def test_exact_old_actual_consumer_exposes_postwrite_tail(self):
        self.run_cases({'old-consumer-negative'})

    def test_source_identity_and_pure_generator_are_strict(self):
        for data in h.actual_functions(self.texts).values():
            self.assertEqual(self.code.count(data['body']), 1)
        old = h.extract(self.texts['old_consumer'], 'handle_notifications')
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(), h.OLD_CONSUMER_SHA256)
        self.assertEqual(self.code.count(old), 1)
        for owner in (True, -1, 2**32):
            with self.assertRaises(ValueError):
                h.generate_source(self.texts, str(self.fixture), owner)
        with self.assertRaises(ValueError):
            h.generate_source({}, str(self.fixture))
        with self.assertRaises(ValueError):
            h.generate_source(self.texts, 'relative', 0)
        changed = dict(self.texts, old_consumer=self.texts['old_consumer'].replace('fopen(notify_name', 'fopen( notify_name'))
        with self.assertRaises(ValueError):
            h.generate_source(changed, str(self.fixture))


if __name__ == '__main__':
    unittest.main()
