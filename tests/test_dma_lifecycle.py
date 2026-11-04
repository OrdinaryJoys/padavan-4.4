"""Checked DMA error propagation with whole current functions and inert IO."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import dma_lifecycle_harness as h

ROOT=Path(__file__).resolve().parents[1]

class DmaLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-dma-lifecycle-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts)
        source=cls.directory/'dma.c';source.write_text(cls.generated)
        gnu=shutil.which('gcc-16') or shutil.which('gcc')
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation'not in version or 'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for name,compiler in (('clang',shutil.which('clang')),('gcc',gnu)):
            if not compiler:raise AssertionError('Required compiler absent: '+name)
            binary=cls.directory/name
            flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror',
                   '-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']
            if name=='clang':flags+=['-fsanitize=address,undefined']
            result=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=30)
            if result.returncode:raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def cases(self,names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(compiler=binary.name,case=name):
                    result=subprocess.run([str(binary),name],check=True,capture_output=True,text=True,timeout=10)
                    self.assertEqual(json.loads(result.stdout),h.EXPECTED_ROWS[name])

    def test_arm_rejects_busy_nic_loss_and_set_failure(self):
        self.cases(h.CASE_NAMES[:4]+h.CASE_NAMES[-2:])

    def test_stop_reset_and_hal_results_are_not_swallowed(self):
        self.cases(h.CASE_NAMES[4:12])

    def test_first_firmware_arm_failure_never_publishes_readiness(self):
        self.cases(h.CASE_NAMES[12:17])

    def test_final_ready_and_rx_mac_setup_require_successful_arm(self):
        self.cases(h.CASE_NAMES[17:22])

    def test_firmware_restart_status_is_preserved(self):
        self.cases(h.CASE_NAMES[22:24])

    def test_successful_teardown_orders_idle_before_free_and_busy_gap_remains_visible(self):
        self.cases(h.CASE_NAMES[24:27])
        self.assertEqual(h.EXPECTED_ROWS['teardown-busy-residual'][6],2)

    def test_whole_source_functions_and_status_contract_are_bound(self):
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.CASE_NAMES),29)
        self.assertEqual(len(h.function_manifest(self.texts)),15)
        for name,key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        self.assertIn(h.declarations(self.texts),self.generated)
        self.assertNotIn('NdisFreeSpinLock(&pAd->CmdQLock);',self.texts['dma'])
        for name,key in h.SOURCE_ONLY_FUNCTION_SOURCES.items():
            self.assertTrue(h.function(self.texts[key],name))

        self.assertIn('NDIS_STATUS (*FwInit)(struct _RTMP_ADAPTER *pAd);',self.texts['chip_header'])
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')

if __name__=='__main__':unittest.main()
