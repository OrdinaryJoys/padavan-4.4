"""Current resource OOM/return-chain models; no driver, device or flash execution."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import hdev_resource_harness as h

ROOT=Path(__file__).resolve().parents[1]
FLAGS=('-std=gnu99','-Os','-fno-strict-aliasing','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-but-set-variable')


def gnu_compiler():
    for name in ('gcc-16','gcc-15','gcc-14','gcc-13','gcc'):
        exe=shutil.which(name)
        if exe:
            banner=subprocess.check_output([exe,'--version'],text=True)
            if 'clang'not in banner.lower():return exe
    raise RuntimeError('GNU C compiler required for resource source regressions')


class HdevResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='hdev-resource-')
        cls.directory=Path(cls.temp.name)
        cls.texts={key:(ROOT/path).read_text()for key,path in h.SOURCE_PATHS.items()}
        cls.code=h.generate_source(cls.texts)
        cls.gnu=gnu_compiler();cls.clang=shutil.which('clang')
        if not cls.clang:raise RuntimeError('Clang ASan/UBSan required for resource regressions')
        cls.binary=cls.compile(cls.code,'current-gnu',cls.gnu)
        cls.asan=cls.compile(cls.code,'current-asan',cls.clang,('-fsanitize=address,undefined','-fno-omit-frame-pointer'))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls,code,name,compiler,extra=()):
        source=cls.directory/(name+'.c');binary=cls.directory/name;source.write_text(code)
        r=subprocess.run([compiler,*FLAGS,*extra,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=30)
        if r.returncode:raise AssertionError('Source-model compile failed: '+r.stdout+r.stderr)
        return binary

    def run_case(self,binary,name):
        r=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_literal_case_inventory_has_seventeen_whole_functions_and_ten_typed_columns(self):
        self.assertEqual((len(h.CASE_NAMES),len(h.BODY_ORDER),len(h.SOURCE_PATHS),len(h.SOURCE_ONLY_FUNCTION_SOURCES)),(85,17,13,2))
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS));self.assertEqual(len(set(h.CASE_NAMES)),85)
        self.assertEqual(tuple(h.FUNCTION_SOURCES),h.BODY_ORDER)
        for row in h.EXPECTED_ROWS.values():
            self.assertEqual(len(row),10);self.assertTrue(all(type(x)is int for x in row))

    def test_generated_model_keeps_complete_current_bodies_and_explicit_manifests(self):
        manifest=h.function_manifest(self.texts)
        for name,key in h.FUNCTION_SOURCES.items():
            body=h.function(self.texts[key],name);self.assertEqual(self.code.count(body),1)
            self.assertEqual(manifest[name],{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(body.encode()).hexdigest()})
        self.assertNotIn('CASE_ADMISSION',self.code);self.assertNotIn('SOURCE_DEFINITIONS',self.code);self.assertNotIn('FUNCTION_DECLARATIONS',self.code)

    def test_source_declarations_require_unique_complete_status_interface_and_return_types(self):
        self.assertEqual(len(h.SOURCE_DECLARATIONS),11)
        for pattern,key in h.SOURCE_DECLARATIONS.items():
            found=re.findall(pattern,self.texts[key],re.M);self.assertEqual(len(found),1)
            bad=dict(self.texts);bad[key]=bad[key].replace(found[0],'')
            with self.subTest(pattern=pattern),self.assertRaises(ValueError):h.generate_source(bad)

    def test_model_profile_keeps_current_ip_assembly_and_explicit_non_kernel_seams(self):
        for key in ('MT_MAC','IP_ASSEMBLY','RESOURCE_PRE_ALLOC','ring_DMA_hardware_seam','RTMPFreeAdapter_fixture_seam','RtmpDmaFinalReleaseCheck_fixture_seam'):
            self.assertIs(h.MODEL_VARIANT[key],True)
        self.assertIs(h.MODEL_VARIANT['struct_layout_is_real_kernel_ABI'],False)
        self.assertIs(h.MODEL_VARIANT['reduced_preprocessor_omits_other_AP_ATE_features'],True)
        self.assertEqual((h.MODEL_VARIANT['tx_rings'],h.MODEL_VARIANT['rx_rings']),(2,2))

    def test_gnu_strict_oom_retry_duplicate_release_and_return_chain_cases(self):
        for name in h.CASE_NAMES:
            with self.subTest(case=name):self.assertEqual(self.run_case(self.binary,name),h.EXPECTED_ROWS[name])

    def test_clang_asan_ubsan_oom_retry_duplicate_release_and_return_chain_cases(self):
        for name in h.CASE_NAMES:
            with self.subTest(case=name):self.assertEqual(self.run_case(self.asan,name),h.EXPECTED_ROWS[name])

    def mutated(self,name,old,new,selector):
        key=h.FUNCTION_SOURCES[name];texts=dict(self.texts);body=h.function(texts[key],name)
        self.assertEqual(body.count(old),1);texts[key]=texts[key].replace(body,body.replace(old,new))
        binary=self.compile(h.generate_source(texts),'mutant-'+selector,self.gnu)
        self.assertNotEqual(self.run_case(binary,selector),h.EXPECTED_ROWS[selector])

    def test_removed_wmm_oom_check_is_detected_before_wtc_success_publication(self):
        self.mutated('HdevHwResourceInit','if (WcInit(ctrl, &pHwResourceCfg->WmmCtrl) != 0)\n\t\treturn -1;','(void)WcInit(ctrl, &pHwResourceCfg->WmmCtrl);','hw-oom')

    def test_removed_pcie_child_result_check_is_detected_with_stale_success_input(self):
        self.mutated('RTMPInitPCIeDevice','RtmpRaDevCtrlInit(pAd, pAd->infType) != NDIS_STATUS_SUCCESS','(RtmpRaDevCtrlInit(pAd, pAd->infType), FALSE)','pcie-oom-1')

    def test_removed_cross_stage_pci_rollback_is_detected_after_cmm_failure(self):
        self.mutated('alloc_chip_cap_dep_data','free_chip_cap_dep_data_pci(pAd->hdev_ctrl);','(void)0;','all-oom-8')

    def test_removed_final_release_gate_is_detected_with_complete_live_graph(self):
        self.mutated('RtmpRaDevCtrlExit','if (!RtmpDmaFinalReleaseCheck(pAd))\n\t\treturn FALSE;','(void)RtmpDmaFinalReleaseCheck(pAd);','dev-exit-refuse')

    def test_removed_ip_assembly_pointer_array_zeroing_is_detected(self):
        self.mutated('alloc_chip_cap_dep_data_cmm','NdisZeroMemory(pCurIpAssemData, num_of_tx_ring * sizeof(struct ip_assemble_data *));','(void)0;','cmm-retry')

    def test_unlisted_case_cannot_enter_a_model_branch(self):
        r=subprocess.run([str(self.binary),'dev-oom-15'],capture_output=True,text=True,timeout=5)
        self.assertEqual((r.returncode,r.stdout,r.stderr),(91,'',''))

    def test_source_only_outer_destructors_are_not_counted_as_executed_functions(self):
        proof=h.source_only_manifest(self.texts)
        self.assertEqual(set(proof),set(h.SOURCE_ONLY_FUNCTION_SOURCES))
        self.assertTrue(all(row['execution']=='source-only-not-run'for row in proof.values()))
        with self.assertRaises(ValueError):h.generate_source(self.texts,'unreviewed')
        with self.assertRaises(ValueError):h.generate_source(dict(self.texts,extra=''))


if __name__=='__main__':unittest.main()
