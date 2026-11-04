"""Current SER software lifetime controls; no DMA or hardware execution."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import ser_lifecycle_harness as h

ROOT=Path(__file__).resolve().parents[1]


class SerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-current-ser-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts)
        source=cls.directory/'ser.c';source.write_text(cls.generated)
        gnu=shutil.which('gcc-16')
        if gnu is None and Path('/opt/homebrew/bin/gcc-16').is_file():gnu='/opt/homebrew/bin/gcc-16'
        if gnu is None:gnu=shutil.which('gcc')
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation'not in version or 'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for name,compiler in (('clang',shutil.which('clang')),('gcc',gnu)):
            if not compiler:raise AssertionError('Required compiler absent: '+name)
            binary=cls.directory/name
            flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror','-pthread',
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
                    row=json.loads(result.stdout);self.assertEqual(row,h.EXPECTED_ROWS[name])
                    self.assertTrue(all(type(value)is int for value in row))

    def test_hif_failure_keeps_queues_retired_and_rejects_repeat_without_rearming(self):
        self.cases(('hif-failure','hif-failure-repeat','hif-success'))

    def test_halted_or_failed_recovery_has_no_queue_or_mmio_effects(self):
        self.cases(('recovery-halted','recovery-failed-entry'))

    def test_event_producer_stops_after_halt_failure_or_software_retirement(self):
        self.cases(('producer-running','producer-halted','producer-failed','producer-stopped'))

    def test_serialized_stop_joins_once_before_owner_release_and_clears_nonzero_exit(self):
        self.cases(('stop-normal','stop-repeat','stop-nonzero-exit','stop-before-owner-release'))

    def test_reopen_resets_only_new_software_recovery_ownership(self):
        self.cases(('ser-reopen-reset',))

    def test_close_joins_an_inflight_recovery_before_releasing_owner(self):
        self.cases(('stop-during-recovery',))

    def test_whole_functions_and_actual_close_order_are_bound(self):
        self.assertEqual(len(h.CASE_NAMES),15)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),7)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        close=h.function(self.texts['close'],'RTMPDrvClose')
        self.assertLess(close.index('RTMP_OS_IRQ_RELEASE'),close.index('HwCtrlSerExit(pAd);'))
        self.assertLess(close.index('HwCtrlSerExit(pAd);'),close.index('tr_ctl_exit(pAd);'))
        self.assertLess(close.index('HwCtrlSerExit(pAd);'),close.index('tm_exit(pAd);'))
        self.assertRegex(close,r'if \(!pAd->ErrRecoveryCtl.queues_retired\) \{[\s\S]*?tm_exit\(pAd\);[\s\S]*?qm_exit\(pAd\);[\s\S]*?queues_retired = TRUE;\s*\}')
        producer=h.function(self.texts['command'],'RTMP_MAC_RECOVERY')
        self.assertLess(producer.index('NdisAcquireSpinLock'),producer.index('RTCMDUp('))
        self.assertLess(producer.index('RTCMDUp('),producer.rindex('NdisReleaseSpinLock'))
        self.assertIn(h.declarations(self.texts['header']),self.generated)
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')


if __name__=='__main__':unittest.main()
