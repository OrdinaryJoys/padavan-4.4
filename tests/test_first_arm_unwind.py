"""Checked DMA error propagation with whole current functions and inert IO."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import first_arm_unwind_harness as h

ROOT=Path(__file__).resolve().parents[1]

class FirstArmUnwindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-first-arm-unwind-')
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

    def test_failed_system_init_is_not_cleaned_twice(self):
        self.cases(('sys-failure',))

    def test_every_completed_hardware_stage_unwinds_after_software_retirement(self):
        self.cases(h.CASE_NAMES[1:8])

    def test_first_arm_then_mlme_create_failure_pairs_hardware_and_software_cleanup(self):
        self.cases(('mlme-failure','unwind-busy-residual'))
        self.assertEqual(h.EXPECTED_ROWS['unwind-busy-residual'][14],1)

    def test_ap_or_final_arm_failure_never_publishes_init_success(self):
        self.cases(('ap-arm-failure','ready-arm-failure','success'))

    def test_outer_open_keeps_irq_ownership_and_never_arms_after_request_failure(self):
        self.cases(('open-irq-failure','open-mlme-failure','open-success'))

    def test_whole_source_chain_and_ap_caller_guards_are_bound(self):
        self.assertEqual(len(h.CASE_NAMES),16)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),7)
        for name,key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        boot=h.function(self.texts['ap'],'ApAutoChannelAtBootUp')
        self.assertLess(boot.index('if (!wdev)'),boot.index('vht_bw = wlan_config_get_vht_bw(wdev);'))
        self.assertIn('if (!RTMPEnableRxTx(pAd))',boot)
        scan=h.function(self.texts['ap'],'APOverlappingBSSScan')
        self.assertLess(scan.index('if (!RTMPEnableRxTx(pAd))'),scan.index('RTMP_SET_FLAG(pAd, fRTMP_ADAPTER_START_UP);'))
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')

if __name__=='__main__':unittest.main()
