"""Fault injection against complete active K2P RAETH runtime source bodies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import raeth_runtime_harness as h
ROOT=Path(__file__).resolve().parents[1]

class RaethRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='raeth-runtime-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/p).read_text() for k,p in h.SOURCE_PATHS.items()}
        cls.code=h.generate_source(cls.texts)
        cls.source=cls.directory/'current.c';cls.source.write_text(cls.code)
        gcc=shutil.which('gcc-16')or shutil.which('gcc')
        clang=shutil.which('clang')
        if not gcc or not clang:raise AssertionError('GNU GCC and Clang required')
        v=subprocess.check_output([gcc,'--version'],text=True,timeout=10)
        if 'Free Software Foundation'not in v or'clang'in v.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for label,compiler in (('gcc',gcc),('clang',clang)):
            binary=cls.directory/label
            args=[compiler,'-std=gnu99','-Os','-fno-strict-aliasing','-Wall','-Wextra','-Werror']
            if label=='clang':args+=['-fsanitize=address,undefined']
            r=subprocess.run([*args,str(cls.source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            if r.returncode:raise AssertionError(r.stderr)
            cls.binaries.append(binary)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def rows(self,names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(binary=binary.name,case=name):
                    r=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertEqual(r.stderr,'')
                    self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
    def test_all_twelve_active_coherent_and_buffer_allocation_failures_unwind(self):
        self.rows([n for n in h.CASE_NAMES if n.startswith('oom-')])
    def test_all_seven_rx_mapping_failures_unmap_only_successful_owners(self):
        self.rows([n for n in h.CASE_NAMES if n.startswith('map-')])
    def test_irq_failures_unwind_owned_handlers_and_balance_module_pin(self):
        self.rows(('irq-1','irq-2','irq-twice','module-denied','esw-post-eio','esw-post-timeout'))
    def test_permanent_pdma_or_qdma_busy_keeps_all_dma_owners_and_pin(self):
        self.rows(('close-pbusy','close-qbusy','init-pbusy','init-qbusy','quarantine-reopen','quarantine-close'))
    def test_success_retry_duplicate_open_and_idempotent_close(self):
        self.rows(('success','reopen','open-twice','close-twice','prx-owned','qrx-owned','fq-retry','pdma-tx-oom','pdma-tx-success'))
    def test_tasklet_stop_admission_prevents_rearming_or_self_rescheduling(self):
        self.rows(('tasklet-running','tasklet-stopped'))
    def test_rx_oom_map_and_build_failures_preserve_old_mapped_ring_buffer(self):
        self.rows(('rx-oom','rx-map','rx-build'))
    def test_rx_descriptor_length_is_bounded_before_build_or_packet_delivery(self):
        self.rows(('rx-short','rx-long','rx-min','rx-max','rx-no-pseudo','rx-zero'))
    def test_complete_source_bodies_and_explicit_profile_limits(self):
        self.assertEqual(len(h.FUNCTION_SOURCES),25)
        self.assertEqual(len(h.CASE_NAMES),51)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        for name,key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.code.count(h.function(self.texts[key],name)),1)
        self.assertEqual(len(h.source_only_manifest(self.texts)),3)
        self.assertTrue(h.MODEL_VARIANT['K2P_MT7621_QTX_PRX_tasklet'])
        self.assertTrue(h.MODEL_VARIANT['real_hardware_fence_not_proven'])
        self.assertTrue(h.MODEL_VARIANT['TX_fragment_mapping_helper_is_inert'])
        self.assertNotIn('rt2880_eth_recv',h.SOURCE_ONLY_FUNCTION_SOURCES)
        with self.assertRaises(ValueError):h.generate_source({})
    def test_dma_enable_and_reset_are_after_fallible_open_and_idle_evidence(self):
        opened=h.function(self.texts['raeth'],'ei_open')
        self.assertLess(opened.index('err = fe_int_enable(dev);'),opened.index('ei_start_dma(dev);'))
        self.assertLess(opened.index('ei_start_dma(dev);'),opened.index('netif_start_queue(dev);'))
        init=h.function(self.texts['raeth'],'ei_init_qtx_prx')
        self.assertNotIn('set_fe_pdma_glo_cfg();',init)
        self.assertNotIn('set_fe_qdma_glo_cfg();',init)
        closed=h.function(self.texts['raeth'],'ei_close')
        self.assertLess(closed.index('netif_tx_disable(dev);'),closed.index('fe_int_disable(dev);'))
        self.assertLess(closed.index('err = ei_stop_dma(dev);'),closed.index('ei_deinit_dma(dev);'))
        self.assertLess(closed.index('ei_deinit_dma(dev);'),closed.index('fe_reset();'))
        disabled=h.function(self.texts['raeth'],'fe_int_disable')
        self.assertNotIn('reset_task',disabled)
        self.assertIn('free_irq(ei_local->switch_irq, NULL);',disabled)
    def test_actual_config_selects_the_modeled_k2p_paths(self):
        config=ROOT/h.SOURCE_PATHS['config']
        probe=self.directory/'profile.c'
        probe.write_text('#include <stdio.h>\n#define BIT(n) (1U<<(n))\n#define CONFIG_SOC_MT7621\n#include "'+str(config)+'"\nint main(void){printf("%u %u %u %u %u %u %u\\n",FE_QDMA_TX,FE_QDMA_RX,FE_INT_TASKLET,FE_INT_NAPI,FE_HW_LRO,FE_RSS_4RING,FE_HW_SFQ);return 0;}\n')
        binary=self.directory/'profile'
        subprocess.run([shutil.which('gcc-16')or shutil.which('gcc'),'-std=gnu99','-Wall','-Wextra','-Werror',str(probe),'-o',str(binary)],check=True,capture_output=True,text=True,timeout=30)
        self.assertEqual(subprocess.check_output([str(binary)],text=True,timeout=5),'65536 0 128 0 0 0 0\n')
        self.assertIn('#define CONFIG_RAETH_RW_PDMAPTR_FROM_VAR',h.PREFIX)
        rx=h.function(self.texts['raeth'],'rt2880_eth_recv')
        self.assertLess(rx.index('DDONE_bit == 0'),rx.index('dma_rmb();'))
        self.assertLess(rx.index('dma_rmb();'),rx.index('length = rx_ring->rxd_info2.PLEN0;'))

    def reject(self,before,after,case,label):
        self.assertEqual(self.code.count(before),1,label)
        code=self.code.replace(before,after,1)
        source=self.directory/(label+'.c');source.write_text(code);binary=source.with_suffix('')
        r=subprocess.run([shutil.which('clang'),'-std=gnu99','-Os','-fno-strict-aliasing','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        env=dict(os.environ);env['ASAN_OPTIONS']=env.get('ASAN_OPTIONS','')+':symbolize=0'
        r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10,env=env)
        if r.returncode==0:self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case],label)
    def test_missing_local_allocation_unwind_is_rejected(self):
        self.reject('no_rx_mem:\n\tfe_pdma_rx_dma_deinit(dev);','no_rx_mem:\n\t/* dropped unwind */','oom-8','pdma-leak')
    def test_wrong_switch_irq_dev_id_is_rejected(self):
        self.reject('err = esw_ioctl_init_post();','err = 0; (void)esw_ioctl_init_post();','esw-post-eio','ignored-esw-post-error')
        self.reject('free_irq(ei_local->switch_irq, NULL);','free_irq(ei_local->switch_irq, dev);','success','switch-owner')
    def test_missing_qdma_stop_is_rejected(self):
        self.reject('sys_reg_write(QDMA_GLO_CFG, reg_value);','/* omitted QDMA stop */','success','qdma-stop')
    def test_busy_close_releasing_dma_is_rejected(self):
        self.reject('err = ei_stop_dma(dev);\n\tif (err)\n\t\treturn err;','err = ei_stop_dma(dev);\n\t(void)err; /* ignored failed idle */','close-qbusy','busy-free')
    def test_rx_build_failure_freeing_old_ring_owner_is_rejected(self):
        self.reject('raeth_free_skb_data(new_data);\n\t\t\tpr_err("build_skb failed','raeth_free_skb_data(rx_data);\n\t\t\tpr_err("build_skb failed','rx-build','old-rx-free')
    def test_missing_rx_length_guard_is_rejected(self):
        self.reject('if (unlikely(length < ETH_HLEN || length > MAX_RX_LENGTH ||\n\t\t\t     (rx_ring->rxd_info4.SP == 2 && !p_ad)))','if (0)','rx-long','rx-bound')
