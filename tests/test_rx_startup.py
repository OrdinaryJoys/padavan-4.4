"""Current configured ring/pool startup allocation failure ownership regressions."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import rx_startup_harness as h

ROOT=Path(__file__).resolve().parents[1]


class RxStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-current-rx-startup-')
        cls.directory=Path(cls.temp.name);cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts);path=cls.directory/'startup.c';path.write_text(cls.generated)
        cls.binary=cls.directory/'startup'
        result=subprocess.run(['clang','-std=gnu99','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                               '-fsanitize=address,undefined',str(path),'-o',str(cls.binary)],capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def cases(self,names):
        for name in h.CASE_NAMES:
            if name not in names:continue
            with self.subTest(case=name):
                result=subprocess.run([str(self.binary),name],check=True,capture_output=True,text=True,timeout=5)
                row=json.loads(result.stdout);self.assertEqual(row,h.EXPECTED_ROWS[name]);self.assertTrue(all(type(x)is int for x in row))
    def test_all_nineteen_cold_ring_allocations_fail_cleanly_and_retry(self):
        self.cases({n for n in h.CASE_NAMES if n.startswith('startup-fail-')})
    def test_all_seven_pool_allocations_fail_cleanly_and_retry(self):
        self.cases({n for n in h.CASE_NAMES if n.startswith('pool-fail-')})
    def test_complete_success_and_repeated_teardown_are_owned(self):
        self.cases({'startup-success','pool-success'})
    def test_reentry_preserves_existing_pool_and_invalid_sizes_allocate_nothing(self):
        self.cases({'pool-reentry','pool-invalid-zero','pool-invalid-max'})
    def test_whole_functions_select_actual_configured_source_region(self):
        self.assertEqual(set(h.EXPECTED_ROWS),set(h.CASE_NAMES));self.assertEqual(len(h.CASE_NAMES),31)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        self.assertEqual(len(h.function_manifest(self.texts)),6)
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,variant='inline')
    def test_both_inline_and_prealloc_callers_check_pool_and_cells(self):
        text=self.texts['pool']
        self.assertEqual(text.count('if (alloc_rx_free_buffer(pAd, num, RxRingSize) != NDIS_STATUS_SUCCESS)'),2)
        self.assertEqual(text.count('!pTxRing->Cell) {'),2)
        self.assertIn('!pRxRing->Cell) {',text);self.assertIn('!rx_ring->Cell) {',text)
