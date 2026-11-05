"""Source-extracted constructor and PCI failure ownership tests."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import probe_oom_harness as h
ROOT=Path(__file__).resolve().parents[1]

class ProbeOOMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='k2p-probe-oom-')
        cls.directory=Path(cls.temporary.name)
        cls.texts={key:(ROOT/path).read_text()for key,path in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts)
        cls.source=cls.directory/'probe.c';cls.source.write_text(cls.generated)
        gnu=shutil.which('gcc-16')or shutil.which('gcc')
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
        clang=shutil.which('clang')
        if not clang:raise AssertionError('Clang ASan/UBSan required')
        cls.compilers=(('gcc',gnu),('clang',clang));cls.binaries=[];cls.msi_binaries=[]
        for label,compiler in cls.compilers:
            for msi in (False,True):
                binary=cls.directory/(label+('-msi'if msi else ''))
                flags=['-std=gnu99','-Os','-fno-strict-aliasing','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-but-set-variable']
                if msi:flags+=['-DCONFIG_WIFI_MSI_SUPPORT=1']
                if label=='clang':flags+=['-fsanitize=address,undefined']
                result=subprocess.run([compiler,*flags,str(cls.source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
                if result.returncode:raise AssertionError(result.stderr)
                (cls.msi_binaries if msi else cls.binaries).append(binary)
    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()
    def cases(self,group):
        for binary in self.binaries:
            for name in h.CASE_GROUPS[group]:
                with self.subTest(compiler=binary.name,case=name):
                    r=subprocess.run([str(binary),name],check=True,capture_output=True,text=True,timeout=10)
                    self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
    def test_unpublished_constructor_heap_failures_retain_caller_cookie(self):self.cases('constructor-oom')
    def test_probe_heap_failures_unwind_cookie_master_mapping_regions(self):self.cases('probe-oom')
    def test_constructor_success_retry_reinit_and_late_registration_failure(self):self.cases('constructor')
    def test_pci_early_late_failures_use_correct_owner_graph(self):self.cases('probe')
    def test_stats_wpf_hdev_partial_and_duplicate_owners(self):self.cases('subowners')
    def test_quarantine_blocks_final_adapter_and_devctrl_release(self):self.cases('quarantine')
    def test_extra_hdev_and_msi_admission(self):self.cases('extra')
    def test_optional_msi_variant_releases_only_acquired_vectors(self):
        names=('probe-msi-owned-constructor-failure','probe-msi-request-failure','probe-region-failure',
               'probe-map-failure','probe-attach-failure','probe-success-free','probe-oom-1')
        for binary in self.msi_binaries:
            for name in names:
                with self.subTest(compiler=binary.name,case=name):
                    r=subprocess.run([str(binary),name],check=True,capture_output=True,text=True,timeout=10)
                    self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
    def test_complete_functions_and_explicit_variant_are_bound(self):
        self.assertEqual(len(h.CASE_NAMES),78)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(set(h.CASE_NAMES),{n for names in h.CASE_GROUPS.values()for n in names})
        self.assertTrue(all(type(row)is list and len(row)==len(h.FIELDS)and all(type(x)is int for x in row)for row in h.EXPECTED_ROWS.values()))
        self.assertEqual(len(h.function_manifest(self.texts)),17)
        self.assertEqual(len(h.source_only_manifest(self.texts)),15)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        self.assertIn(h.declarations(self.texts),self.generated)
        self.assertTrue(h.MODEL_VARIANT['MULTI_INF_SUPPORT'])
        self.assertFalse(h.MODEL_VARIANT['actual_K2P_MULTI_INF_SUPPORT'])
        self.assertFalse(h.MODEL_VARIANT['CONFIG_WIFI_MSI_SUPPORT'])
        self.assertTrue(h.MODEL_VARIANT['native_extra_MSI_variant'])
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')
    def test_current_beacon_packet_and_lock_owner_states(self):
        for binary in self.binaries:
            for name in h.CASE_GROUPS['beacon']:
                with self.subTest(compiler=binary.name,case=name):
                    r=subprocess.run([str(binary),name],check=True,capture_output=True,text=True,timeout=10)
                    self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
    def test_current_beacon_field_and_destruction_order_are_source_bound(self):
        self.assertTrue(h.MODEL_VARIANT['CONFIG_AP_SUPPORT'])
        self.assertTrue(h.MODEL_VARIANT['model_HIF_MT'])
        self.assertTrue(h.MODEL_VARIANT['actual_K2P_HIF_MT'])
        self.assertEqual(len(h.SOURCE_FIELD_CONSTRAINTS),1)
        field='BOOLEAN BcnContentLockInitialized;'
        self.assertEqual(self.generated.count(field),1)
        for name in ('bcn_buf_init','bcn_buf_deinit'):
            body=h.function(self.texts['bcn'],name);self.assertEqual(self.generated.count(body),1)
            self.assertIn('struct _PCI_HIF_T *hif = &pAd->PciHif;',body)
        init=h.function(self.texts['bcn'],'bcn_buf_init')
        self.assertLess(init.index('RTMPAllocateNdisPacket'),init.index('NdisAllocateSpinLock'))
        self.assertLess(init.index('NdisAllocateSpinLock'),init.index('BcnContentLockInitialized = TRUE;'))
        self.assertLess(init.index('BcnContentLockInitialized = TRUE;'),init.index('RTMP_SEM_LOCK(&hif->BcnRingLock);'))
        free=h.function(self.texts['free'],'RTMPFreeAdapter')
        self.assertLess(free.index('bcn_buf_deinit('),free.index('NdisFreeSpinLock('))
        self.assertLess(free.index('bcn_buf_deinit('),free.index('hdev_ctrl_exit(pAd);'))
        bad=dict(self.texts);bad['header']=bad['header'].replace(field,'UCHAR BcnContentLockInitialized;')
        with self.assertRaises(ValueError):h.generate_source(bad)
    def test_constructor_publication_and_early_cleanup_are_transactional(self):
        body=h.function(self.texts['init'],'RTMPAllocAdapterBlock');publish='*ppAdapter = (VOID *)pAd;'
        self.assertEqual(body.count(publish),1)
        for token in ('wpf_config_init(pAd)','wifi_sys_init(pAd)','multi_inf_adapt_reg((VOID *)pAd)'):
            self.assertLess(body.index(token),body.index(publish))
        self.assertLess(body.index('wpf_config_init(pAd)'),body.index('NdisAllocateSpinLock'))
        self.assertIn('NDIS_STATUS wpf_config_init(',self.texts['config_header'])
        probe=h.function(self.texts['pci'],'rt_pci_probe')
        self.assertLess(probe.index('pci_get_drvdata(pdev)'),probe.index('pci_enable_device(pdev)'))
        self.assertLess(probe.index('pci_clear_master(pdev)'),probe.index('iounmap((void *)(csr_addr))'))
        free=h.function(self.texts['free'],'RTMPFreeAdapter')
        for lock in ('WifiSysInfo.lock','VirtualIfLock','TimerSemLock'):self.assertIn('NdisFreeSpinLock(&pAd->'+lock+');',free)
        self.assertIn('hif = &pAd->PciHif;',free)
        exit_body=h.function(self.texts['init'],'RtmpRaDevCtrlExit')
        self.assertNotIn('wpf_config_exit(pAd)',exit_body);self.assertNotIn('ProbeRespIE[index]',exit_body)
    def reject(self,texts,name,label):
        source=self.directory/(label+'.c');source.write_text(h.generate_source(texts));binary=source.with_suffix('')
        r=subprocess.run([shutil.which('clang'),'-std=gnu99','-Os','-fno-strict-aliasing','-Wall','-Wextra','-Werror',
            '-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-but-set-variable','-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(r.returncode,0,'Removed protection unexpectedly accepted '+name)
    def test_old_stats_second_allocation_failure_is_detected(self):
        old=subprocess.check_output(['git','-C',str(ROOT),'show','5ce45fccc96d085f2786b509a51abcba2a136f80:'+h.SOURCE_PATHS['os']]).decode()
        texts=dict(self.texts);texts['os']=texts['os'].replace(h.function(texts['os'],'RtmpOsStatsAlloc'),h.function(old,'RtmpOsStatsAlloc'))
        self.reject(texts,'ctor-oom-4','old-stats-double-free')
    def test_removed_cookie_publication_wpf_master_late_cleanup_guards_are_detected(self):
        mutations=(
          ('pci','rt_pci_probe','os_free_mem(handle);','(void)handle;','probe-oom-2'),
          ('init','RTMPAllocAdapterBlock','if (RtmpOsStatsAlloc','*ppAdapter = (VOID *)pAd;\n\tif (RtmpOsStatsAlloc','ctor-success-free'),
          ('config','wpf_config_init','if (pf->oper == NULL)','if (FALSE)','ctor-oom-11'),
          ('pci','rt_pci_probe','if (radev_initialized)\n\t\tRtmpRaDevCtrlExit(pAd);\n\telse\n\t\tRTMPFreeAdapter(pAd);','if (radev_initialized)\n\t\tRTMPFreeAdapter(pAd);\n\telse\n\t\tRTMPFreeAdapter(pAd);','probe-attach-failure'),
          ('pci','rt_pci_probe','pci_clear_master(pdev);','(void)pdev;','probe-oom-1'))
        for index,(key,name,before,after,selector)in enumerate(mutations):
            with self.subTest(selector=selector):
                original=h.function(self.texts[key],name);self.assertEqual(original.count(before),1)
                texts=dict(self.texts);texts[key]=texts[key].replace(original,original.replace(before,after))
                self.reject(texts,selector,'removed-protection-'+str(index))
