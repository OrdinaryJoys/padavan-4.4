"""Fault-injected complete current init functions; no hardware execution."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wsc_init_harness as h

ROOT=Path(__file__).resolve().parents[1]


class WscVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-wsc-variant-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts)
        source=cls.directory/'init.c';source.write_text(cls.generated)
        gnu=shutil.which('gcc-16')or('/opt/homebrew/bin/gcc-16'if Path('/opt/homebrew/bin/gcc-16').is_file()else shutil.which('gcc'))
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

    def cases(self,prefix):
        for binary in self.binaries:
            for name in h.CASE_NAMES:
                if not name.startswith(prefix):continue
                with self.subTest(compiler=binary.name,case=name):
                    result=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    row=json.loads(result.stdout);self.assertEqual(row,h.EXPECTED_ROWS[name])
                    self.assertTrue(all(type(value)is int for value in row))

    def test_worker_buffers_are_zero_and_owned_before_wake_and_faults_are_transactional(self):self.cases('wsc-')
    def test_partial_or_unbuilt_configuration_uses_only_its_owners(self):self.cases('cfg-')

    def test_whole_functions_case_set_and_native_variant_are_explicit(self):
        self.assertEqual(len(h.CASE_NAMES),20)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),12)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        self.assertIn('#define WSC_INCLUDED',h.PREFIX)
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')

    def test_current_k2p_profile_does_not_compile_wsc(self):
        config=(ROOT/'trunk/configs/boards/K2P/kernel-4.4.x.config').read_text()
        self.assertIn('# CONFIG_WSC_INCLUDED is not set',config)
        self.assertIn('# CONFIG_WSC_V2_SUPPORT is not set',config)
        self.assertNotIn('CONFIG_WSC_INCLUDED=y',config)

    def test_parent_starts_wsc_after_configuration_and_propagates_failure(self):
        init=h.function(self.texts['sys'],'rtmp_sys_init')
        mgmt=h.function(self.texts['mgmt'],'RtmpMgmtTaskInit')
        self.assertNotIn('WscThreadInit(pAd)',mgmt)
        self.assertLess(init.index('rtmp_cfg_init(pAd, pHostName)'),init.index('status = WscThreadInit(pAd);'))
        self.assertRegex(init,r'status = WscThreadInit\(pAd\);\s*if \(status != NDIS_STATUS_SUCCESS\)\s*goto fail;')

    def test_timer_and_configuration_cleanup_precede_parent_free_and_are_distinct(self):
        task=h.function(self.texts['sys'],'rtmp_sys_task_exit')
        self.assertLess(task.index('WscThreadExit(pAd);'),task.index('RTMP_AllTimerListRelease(pAd);'))
        mgmt=h.function(self.texts['mgmt'],'RtmpMgmtTaskExit')
        self.assertIn('WscThreadStop(pAd);',mgmt);self.assertNotIn('WscThreadExit(pAd)',mgmt)
        cfg=h.function(self.texts['sys'],'rtmp_cfg_exit')
        self.assertLess(cfg.index('WscThreadExit(pAd);'),cfg.index('UserCfgExit(pAd);'))
        stop=h.function(self.texts['wsc'],'WscThreadStop')
        self.assertNotIn('ApCfg',stop);self.assertNotIn('RTMPReleaseTimer',stop)

    def test_actual_header_and_constructor_ownership_flags_are_bound(self):
        for field in ('WscWorkerInitialized','WscConfigInitialized'):
            self.assertRegex(self.texts['rtmp_header'],r'BOOLEAN\s+'+field+r';')
        self.assertRegex(self.texts['wsc_header'],r'BOOLEAN\s+WscPeerListInitialized;')
        cfg=h.function(self.texts['adapter'],'UserCfgInit')
        uuid=h.function(self.texts['wsc'],'WscUUIDInit')
        self.assertIn('pWscControl->WscPeerListInitialized = TRUE;',cfg)
        self.assertIn('pAd->WscConfigInitialized = TRUE;',cfg)
        self.assertIn('pWpsCtrl->WscPeerListInitialized = TRUE;',uuid)
        self.assertIn('if (!pWpsCtrl->WscPeerListInitialized)',uuid)

    def test_variant_zeroing_and_write_sentinel_precede_task_attach(self):
        init=h.function(self.texts['wsc'],'WscThreadInit')
        attach=init.index('RtmpOSTaskAttach(')
        for statement in ('NdisZeroMemory(hmac, 2048);','NdisZeroMemory(element, sizeof(*element));',
                          'pAd->WriteWscCfgToDatFile = 0xFF;','pAd->WscWorkerInitialized = TRUE;'):
            self.assertLess(init.index(statement),attach)


if __name__=='__main__':unittest.main()

