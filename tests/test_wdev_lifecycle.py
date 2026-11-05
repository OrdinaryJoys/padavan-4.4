"""Whole functions with controlled allocator, stop and registration faults."""
import json
import re
from pathlib import Path
import shutil,subprocess,tempfile,unittest
import wdev_lifecycle_harness as h
ROOT=Path(__file__).resolve().parents[1]
FLAGS=['-std=gnu99','-Os','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-but-set-variable']
class WdevLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-wdev-lifecycle-');cls.root=Path(cls.temp.name)
        cls.texts={k:(ROOT/p).read_text()for k,p in h.SOURCE_PATHS.items()};cls.generated=h.generate_source(cls.texts)
        cls.source=cls.root/'current.c';cls.source.write_text(cls.generated)
        gcc=shutil.which('gcc-16')or shutil.which('gcc');clang=shutil.which('clang')
        if not gcc or not clang:raise AssertionError('GNU GCC and Clang ASan/UBSan required')
        version=subprocess.run([gcc,'--version'],capture_output=True,text=True,check=True).stdout
        if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.clang=clang;cls.binaries=[]
        for label,cc,extra in [('gnu',gcc,[]),('asan',clang,['-fsanitize=address,undefined','-fno-sanitize-recover=all'])]:
            binary=cls.root/label;r=subprocess.run([cc,*FLAGS,*extra,str(cls.source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            if r.returncode:raise AssertionError(r.stderr)
            cls.binaries.append(binary)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def cases(self,group):
        for binary in self.binaries:
            for name in h.CASE_GROUPS[group]:
                with self.subTest(binary=binary.name,case=name):
                    r=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
                    self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
    def test_main_registration_failure_and_unpublished_ops_free(self):self.cases('main')
    def test_mbss_partial_publication_retry_cached_beacons_and_shrunk_count(self):self.cases('mbss')
    def test_all_interfaces_close_before_configuration_and_workers_retire(self):self.cases('closeall')
    def test_quarantine_keeps_registered_owner_graph(self):self.cases('quarantine')
    def test_vendor_ie_two_allocations_preserve_previous_chain_and_payload(self):self.cases('vie')
    def test_model_full_bodies_manifests_typed_rows_and_explicit_inert_scope(self):
        self.assertEqual(len(h.CASE_NAMES),54);self.assertEqual(len(h.BODY_ORDER),15)
        # Legacy target GCC treats a local identifier named main as -Wmain.
        # Retain the C entry point and forbid shadowing without weakening flags.
        token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
        masked=re.sub(token,lambda m:' '*len(m.group()),self.generated)
        self.assertEqual(re.findall(r'\bmain\b',masked),['main'])
        self.assertIn('PNET_DEV root_netdev=NULL;',self.generated)

        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS));self.assertEqual(set(h.CASE_NAMES),{n for ns in h.CASE_GROUPS.values()for n in ns})
        self.assertEqual(len(h.function_manifest(self.texts)),15);self.assertEqual(len(h.source_only_manifest(self.texts)),7)
        for n,k in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[k],n)),1)
        for row in h.EXPECTED_ROWS.values():self.assertTrue(type(row)is list and len(row)==len(h.FIELDS) and all(type(x)is int for x in row))
        self.assertTrue(h.MODEL_VARIANT['dev_close_ignores_ndo_stop_status']);self.assertFalse(h.MODEL_VARIANT['real_RTNl_or_threads_executed'])
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')
    def test_pointer_return_body_is_whole_and_dispatch_callers_are_source_only(self):
        body=h.function(self.texts['main'],'RtmpPhyNetDevInit');self.assertTrue(body.startswith('PNET_DEV RtmpPhyNetDevInit'))
        bad=dict(self.texts);bad['main']=bad['main'].replace(body,body.replace('PNET_DEV RtmpPhyNetDevInit','PNET_UNKNOWN RtmpPhyNetDevInit',1))
        with self.assertRaises(ValueError):h.generate_source(bad)
        for n in ('APCli_Init','WDS_Init','Monitor_Init','RTMP_COM_IoctlHandle'):self.assertEqual(h.source_only_manifest(self.texts)[n]['execution'],'source-only-not-run')
    def reject(self,key,name,before,after,case,label):
        texts=dict(self.texts);original=h.function(texts[key],name);self.assertEqual(original.count(before),1)
        texts[key]=texts[key].replace(original,original.replace(before,after));src=self.root/(label+'.c');src.write_text(h.generate_source(texts));binary=src.with_suffix('')
        r=subprocess.run([self.clang,*FLAGS,'-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(binary)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr);r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(r.returncode,0,'Removed protection accepted '+case)
    def test_removed_final_retirement_and_remove_latch_are_detected(self):
        self.reject('main','RtmpPhyNetDevCloseAll','pAd->RscTimerCreateList.size == 0','TRUE','closeall-timer-busy','no-timer-check')
        self.reject('main','RtmpPhyNetDevCloseAll','WRITE_ONCE(pAd->dma_removing, TRUE);','(void)pAd;','closeall-open-excluded','no-remove-latch')
    def test_early_configuration_release_is_detected(self):
        body=h.function(self.texts['main'],'RtmpPhyNetDevExit');before='wpf_exit(pAd);';self.assertEqual(body.count(before),1)
        changed=body.replace(before,'').replace('#ifdef CONFIG_AP_SUPPORT','wpf_exit(pAd);\n#ifdef CONFIG_AP_SUPPORT',1)
        self.reject('main','RtmpPhyNetDevExit',body,changed,'closeall-success','early-config-release')
    def test_unpublished_netdev_ops_leak_is_detected(self):
        self.reject('os','RtmpOSNetDevFree','vfree((void *)pNetDev->netdev_ops);','(void)pNetDev;','free-unpublished-ops','no-ops-free')
    def test_missing_mbss_rollback_and_main_close_fallback_are_detected(self):
        body=h.function(self.texts['mbss'],'MBSS_Init');pos=body.index('if (status != NDIS_STATUS_SUCCESS)')
        changed=body[:pos]+body[pos:].replace('wdev_deinit(pAd, wdev);','(void)wdev;',1)
        self.reject('mbss','MBSS_Init',body,changed,'mbss-attach-first-failure','no-mbss-unregister')
        self.reject('main','RtmpPhyNetDevCloseAll','if (net_dev && (net_dev->flags & IFF_UP))','if (FALSE)','closeall-main-fallback','no-main-fallback')
    def test_removed_vendor_failure_free_and_old_payload_update_are_detected(self):
        self.reject('vendor','insert_vie','if (vie)\n\t\tos_free_mem(vie);','(void)vie;','vie-payload-oom','leaked-private-vie')
        current=h.function(self.texts['vendor'],'add_vie')
        old=subprocess.check_output(['git','-C',str(ROOT),'show','a23aaa4e11894cad9306bc87bbac3ed310dcf3de:'+h.SOURCE_PATHS['vendor']]).decode()
        self.reject('vendor','add_vie',current,h.function(old,'add_vie'),'vie-update-oom','old-vie-replace')
    def test_old_wdev_registration_order_is_detected(self):
        current=h.function(self.texts['wdev'],'wdev_init')
        old=subprocess.check_output(['git','-C',str(ROOT),'show','a23aaa4e11894cad9306bc87bbac3ed310dcf3de:'+h.SOURCE_PATHS['wdev']]).decode()
        self.reject('wdev','wdev_init',current,h.function(old,'wdev_init'),'vie-registration-failure-preserves','old-wdev-reg-order')

    def test_actual_exit_releases_main_vie_and_checks_registered_owner_before_deinit(self):
        self.cases('main_exit')
        self.assertRegex(self.texts['header'],r'\bCHAR\s+wdev_idx\s*;')
        self.reject('main','RtmpPhyNetDevExit','wdev_deinit(ad, main_wdev);','(void)main_wdev;','exit-main-vie-owner','no-main-wdev-retirement')
        self.reject('main','RtmpPhyNetDevExit','(UINT)main_wdev->wdev_idx < WDEV_NUM_MAX','main_wdev->wdev_idx < WDEV_NUM_MAX','exit-main-negative-index','no-unsigned-index-guard')
