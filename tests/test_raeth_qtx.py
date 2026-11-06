"""Fault and retirement checks on whole QDMA TX source functions; no hardware IO."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import raeth_qtx_harness as h
ROOT=Path(__file__).resolve().parents[1]

class RaethQtxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='raeth-qtx-');cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/p).read_text()for k,p in h.SOURCE_PATHS.items()}
        cls.code=h.generate_source(cls.texts);source=cls.directory/'current.c';source.write_text(cls.code)
        gcc=shutil.which('gcc-16')or shutil.which('gcc');clang=shutil.which('clang')
        if not gcc or not clang:raise AssertionError('GNU GCC and Clang required')
        version=subprocess.check_output([gcc,'--version'],text=True,timeout=10)
        if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for name,compiler in (('gcc',gcc),('clang',clang)):
            binary=cls.directory/name;flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror']
            if name=='clang':flags+=['-fsanitize=address,undefined']
            r=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            if r.returncode:raise AssertionError(r.stderr)
            cls.binaries.append(binary)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def rows(self,names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(binary=binary.name,case=name):
                    r=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
                    self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'')
                    self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
    def test_new_mapping_constructor_oom_and_duplicate_owner_admission(self):
        self.rows(('ctor-metadata-oom','ctor-coherent-oom','ctor-success','ctor-duplicate'))
    def test_linear_gso_uses_tso_even_with_one_descriptor_and_releases_skb(self):
        self.rows(('gso-linear','gso-linear-complete'))
    def test_mapping_failures_rollback_before_descriptor_or_hardware_publication(self):
        self.rows(('map-fail-1','map-fail-2','map-fail-3'))
    def test_valid_linear_fragment_and_split_packets_retain_dma_ownership(self):
        self.rows(('linear','fragment','three-fragments','split-fragment','split-head'))
    def test_completion_unmaps_exactly_once_before_packet_release(self):
        self.rows(('complete','complete-split','double-complete'))
    def test_idle_owner_release_and_repeated_unmap_are_idempotent(self):
        self.rows(('close-unmap','double-unmap'))
    def test_primary_pseudo_and_completion_use_same_descriptor_lock(self):
        self.rows(('two-netdevs',))
    def test_invalid_skb_geometry_and_queue_are_rejected_without_mapping(self):
        self.rows(('invalid-fragment-count','invalid-size','invalid-total','no-head','bad-queue'))
    def test_quarantined_stopped_missing_owner_and_full_ring_admission(self):
        self.rows(('quarantine','stopped','no-owner','no-space'))
    def test_full_function_and_explicit_inert_layout_boundaries(self):
        self.assertEqual(len(h.CASE_NAMES),30);self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),11);self.assertEqual(len(h.source_only_manifest(self.texts)),2)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.code.count(h.function(self.texts[key],name)),1)
        self.assertTrue(h.MODEL_VARIANT['synthetic_skb_and_descriptor_layout'])
        self.assertTrue(h.MODEL_VARIANT['DMA_MMIO_cache_sync_inert'])
        with self.assertRaises(ValueError):h.generate_source({})
    def test_reused_descriptors_receive_current_packet_metadata(self):
        self.rows(('metadata-reuse',))
    def test_constructor_checks_mapping_metadata_allocation_and_pool_failure(self):
        body=h.function(self.texts['qdma'],'qdma_tx_desc_alloc')
        self.assertLess(body.index('if (ei_local->txd_pool || ei_local->qtx_mapping)'),body.index('kcalloc('))
        self.assertLess(body.index('if (!ei_local->qtx_mapping)'),body.index('dma_alloc_coherent('))
        failure=body[body.index('if (!ei_local->txd_pool)'):body.index('/* set all txd_pool_info')]
        self.assertIn('kfree(ei_local->qtx_mapping);',failure);self.assertIn('ei_local->qtx_mapping = NULL;',failure)
        deinit=h.function(self.texts['qdma'],'fe_qdma_tx_dma_deinit')
        self.assertLess(deinit.index('fe_qdma_tx_unmap(ei_local, i);'),deinit.index('dma_free_coherent('))
        self.assertIn('kfree(ei_local->qtx_mapping);',deinit);self.assertIn('ei_local->qtx_mapping = NULL;',deinit)
    def reject(self,code,case,label):
        source=self.directory/(label+'.c');source.write_text(code);binary=source.with_suffix('')
        r=subprocess.run([shutil.which('clang'),'-std=gnu99','-Os','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10,env=dict(os.environ,ASAN_OPTIONS='symbolize=0'))
        if not r.returncode:self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case],'Fault unexpectedly accepted')
    def test_missing_mapping_rollback_is_rejected(self):
        body=h.function(self.texts['qdma'],'raeth_qtx_map_skb');before='dma_unmap_page(&ei_local->qdma_pdev->dev,\n\t\t\t\t\tmaps[i].addr, maps[i].len, DMA_TO_DEVICE);'
        self.assertEqual(body.count(before),1)
        self.reject(self.code.replace(body,body.replace(before,'/* missing rollback */')),'map-fail-3','no-rollback')
    def test_missing_completion_unmap_is_rejected(self):
        before='\t\tfe_qdma_tx_unmap(ei_local, ctx_offset);';self.assertEqual(self.code.count(before),1)
        self.reject(self.code.replace(before,'/* missing completed ownership */'),'complete','no-completion-unmap')
    def test_missing_shared_producer_lock_is_rejected(self):
        body=h.function(self.texts['qdma'],'ei_qdma_start_xmit')
        changed=body.replace('spin_lock_irqsave(&ei_local->page_lock, flags);','flags=0;').replace('spin_unlock_irqrestore(&ei_local->page_lock, flags);','(void)flags;')
        self.reject(self.code.replace(body,changed),'three-fragments','no-producer-lock')
    def test_stale_fragment_metadata_copy_is_rejected(self):
        body=h.function(self.texts['qdma'],'rt2880_qdma_eth_send_tso')
        before='dummy_desc = init_dummy_desc;'
        self.assertEqual(body.count(before),2)
        stale='dummy_desc = *cpu_ptr;'
        self.reject(self.code.replace(body,body.replace(before,stale)),'metadata-reuse','stale-fragment-metadata')
    def test_old_map_error_continuation_does_not_pass_current_fault_contract(self):
        old=subprocess.check_output(['git','-C',str(ROOT),'show','6ae86c7a097cfcf8113a2e0d0c174216a5726806:'+h.SOURCE_PATHS['qdma']],text=True,timeout=30)
        oldbody=h.function(old,'rt2880_qdma_eth_send_tso')
        self.assertIn('dma_map_page(',oldbody);self.assertNotIn('dma_unmap_page(',old)
        code=self.code.replace(h.function(self.texts['qdma'],'rt2880_qdma_eth_send_tso'),oldbody)
        code=code.replace(h.function(self.texts['qdma'],'raeth_qtx_map_skb'),'')
        self.reject(code,'map-fail-2','old-map-error')

if __name__=='__main__':unittest.main()
