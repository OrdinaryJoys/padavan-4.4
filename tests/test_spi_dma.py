"""Actual SPI/SG bodies, ownership conservation and failure witnesses."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import struct
import unittest
from unittest import mock
import spi_dma_harness as harness

ROOT = Path(__file__).resolve().parents[1]


class SpiDmaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-spi-dma-')
        cls.base=Path(cls.temp.name)
        cls.texts={key:(ROOT/path).read_text() for key,path in harness.SOURCE_PATHS.items()}
        cls.compiler=shutil.which('clang') or shutil.which('cc')
        if not cls.compiler:raise RuntimeError('Host C compiler is required')
        cls.binaries={kind:cls.compile(cls.texts,kind,baseline=kind=='baseline')
                      for kind in ('current','baseline')}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @classmethod
    def compile(cls,texts,name,baseline=False,raw=None):
        source=cls.base/(name+'.c');binary=cls.base/name
        source.write_text(raw if raw is not None else harness.generate_source(texts,baseline=baseline))
        run=subprocess.run([cls.compiler,'-std=gnu89','-O1','-g','-Wall','-Wextra','-Werror',
                            '-Wno-unused-function','-Wno-unused-parameter','-Wno-unused-variable',
                            '-fsanitize=address,undefined','-fno-sanitize-recover=undefined',
                            str(source),'-o',str(binary)],capture_output=True,text=True,timeout=30)
        if run.returncode:raise AssertionError(run.stderr)
        return binary

    def row(self,case,binary='current'):
        exe=self.binaries.get(binary,binary)
        run=subprocess.run([str(exe),case],capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stderr,'')
        return json.loads(run.stdout)

    def mutate(self,name,function,old,new,count=1):
        texts=copy.copy(self.texts)
        key=next(k for k,names in harness.FUNCTIONS.items() if function in names)
        before=harness.actual_functions(texts)[function]['body']
        self.assertEqual(before.count(old),count)
        texts[key]=texts[key].replace(before,before.replace(old,new,count),1)
        return self.compile(texts,name)

    def test_exact_ten_source_bodies_and_immutable_sg_dependency_baseline(self):
        actual=harness.actual_functions(self.texts)
        self.assertEqual(len(actual),10);self.assertEqual(set(actual),set(harness.BASELINE_FUNCTIONS))
        generated=harness.generate_source(self.texts)
        for name,item in actual.items():
            self.assertEqual(generated.count(item['body']),1)
            if name not in ('spi_map_buf','__spi_map_msg','__spi_unmap_msg'):
                self.assertEqual(item['body'],harness.BASELINE_FUNCTIONS[name])
        for name,body in harness.BASELINE_FUNCTIONS.items():
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),harness.BASELINE_HASHES[name])
        self.assertEqual((len(harness.CASE_NAMES),len(harness.BASELINE_CASE_NAMES)),(36,9))

    def test_all_current_observations_match_fixed_typed_contract(self):
        for case in harness.CASE_NAMES:
            with self.subTest(case=case):
                row=self.row(case);self.assertTrue(harness.validate_row(row))
                self.assertEqual(tuple(row[k] for k in ('live_maps','live_allocs','remaining_sg',
                    'mapped_flag','bad_sg','invalid_free','invalid_unmap','wrong_entries',
                    'wrong_device','wrong_segments')),(0,)*10)
                self.assertEqual(row['maps'],row['unmaps']);self.assertEqual(row['allocs'],row['frees'])

    def test_baseline_reproduces_partial_leaks_chain_indexing_and_eligibility_leaks(self):
        for case in harness.BASELINE_CASE_NAMES:
            with self.subTest(case=case):
                old=self.row(case,'baseline');self.assertTrue(harness.validate_row(old,baseline=True))
                with self.assertRaises(ValueError):harness.validate_row(old)
        self.assertEqual(self.row('tx-fail-second','baseline')['live_maps'],2)
        self.assertEqual(self.row('rx-fail-third','baseline')['live_maps'],4)
        self.assertGreater(self.row('chained-linear','baseline')['bad_sg'],0)
        self.assertEqual(self.row('eligibility-changes','baseline')['live_maps'],6)
        self.assertEqual(self.row('unlimited-dma-length','baseline')['result'],-22)
        self.assertEqual(self.row('unlimited-dma-length')['result'],0)

    def test_each_partial_failure_keeps_errno_and_releases_every_earlier_map(self):
        for index,case in enumerate(('tx-fail-first','rx-fail-first','tx-fail-second',
                                     'rx-fail-second','tx-fail-third','rx-fail-third')):
            row=self.row(case)
            self.assertEqual((row['result'],row['map_calls'],row['maps'],row['unmaps']),
                             (-12,index+1,index,index))

    def test_unwind_removal_does_not_hide_earlier_owners(self):
        loop=('\tlist_for_each_entry(xfer, &msg->transfers, transfer_list) {\n'
              '\t\tspi_unmap_buf(master, rx_dev, &xfer->rx_sg, DMA_FROM_DEVICE);\n'
              '\t\tspi_unmap_buf(master, tx_dev, &xfer->tx_sg, DMA_TO_DEVICE);\n\t}')
        binary=self.mutate('no-unwind','__spi_map_msg',loop,'')
        self.assertEqual(self.row('rx-fail-third',binary)['live_maps'],5)

    def test_chained_iteration_requires_sg_next_instead_of_flat_indexing(self):
        texts=copy.copy(self.texts);before=harness.extract(texts['core'],'spi_map_buf')
        after=before.replace('for_each_sg(sgt->sgl, sg, sgs, i)',
            'for (i = 0; i < sgs; i++)').replace('sg_set_page(sg,','sg_set_page(&sgt->sgl[i],').replace(
            'sg_set_buf(sg,','sg_set_buf(&sgt->sgl[i],')
        self.assertNotEqual(before,after);texts['core']=texts['core'].replace(before,after,1)
        binary=self.compile(texts,'flat-chain-indexing')
        for case in ('chained-linear','chained-vmalloc','chained-offset-vmalloc'):
            self.assertGreater(self.row(case,binary)['bad_sg'],0)

    def test_unmap_uses_original_segment_count_when_dma_merges_entries(self):
        binary=self.mutate('wrong-unmap-count','spi_unmap_buf',
            'dma_unmap_sg(dev, sgt->sgl, sgt->orig_nents, dir);',
            'dma_unmap_sg(dev, sgt->sgl, sgt->nents, dir);')
        self.assertEqual(self.row('dma-merge')['wrong_entries'],0)
        self.assertEqual(self.row('dma-merge',binary)['wrong_entries'],6)

    def test_recorded_ownership_outlives_can_dma_eligibility(self):
        before='\tlist_for_each_entry(xfer, &msg->transfers, transfer_list) {\n'
        binary=self.mutate('requery-eligibility','__spi_unmap_msg',before,
            before+'\t\tif (!master->can_dma(master, msg->spi, xfer)) continue;\n')
        self.assertEqual(self.row('eligibility-changes')['live_maps'],0)
        self.assertEqual(self.row('eligibility-changes',binary)['live_maps'],6)
        self.assertEqual(self.row('eligibility-removed')['live_maps'],0)

    def test_completed_unmap_retires_flag_and_repeat_has_no_new_effect(self):
        row=self.row('double-unmap')
        self.assertEqual((row['unmaps'],row['can_calls'],row['mapped_flag']),(6,3,0))
        binary=self.mutate('stale-mapping-flag','__spi_unmap_msg',
            '\tmaster->cur_msg_mapped = false;\n','')
        self.assertEqual(self.row('double-unmap',binary)['mapped_flag'],1)

    def test_zero_length_does_not_allocate_invalid_sg_table(self):
        row=self.row('zero-length')
        self.assertEqual((row['result'],row['alloc_calls'],row['map_calls']),(0,0,0))
        binary=self.mutate('map-zero-length','__spi_map_msg',
            '!xfer->len || !master->can_dma','!master->can_dma')
        mutated=self.row('zero-length',binary)
        self.assertEqual((mutated['result'],mutated['alloc_calls'],mutated['can_calls']),(0,0,3))
        self.assertEqual(self.row('zero-length')['can_calls'],0)

    def test_alloc_page_chain_failures_retry_dummy_and_premapped_addresses(self):
        for case in ('alloc-fail-first','alloc-fail-second','alloc-fail-later',
                     'vmalloc-page-first','vmalloc-page-later','chain-alloc-partial-fail',
                     'chain-alloc-later-fail','chain-map-later-fail','dummy-alloc-fail'):
            row=self.row(case)
            self.assertEqual((row['result'],row['live_allocs'],row['live_maps']),(-12,0,0))
        row=self.row('retry-after-failure')
        self.assertEqual((row['result'],row['result2'],row['first_live_maps'],row['live_maps']),(-12,0,0,0))
        self.assertEqual(self.row('dummy-restore')['dummy_restored'],1)
        self.assertEqual(self.row('premapped-addresses')['premapped_intact'],1)
        raw=harness.generate_source(self.texts).replace('#define CONFIG_ARCH_HAS_SG_CHAIN 1',
            '#define WARN_ON_ONCE(x) (x)')
        binary=self.compile(self.texts,'no-sg-chaining',raw=raw)
        for case in ('chained-linear','chained-vmalloc'):
            row=self.row(case,binary)
            self.assertEqual((row['result'],row['maps'],row['live_maps'],row['live_allocs']),(-22,0,0,0))
        # Stop before any giant allocation or buffer access. On 64-bit hosts
        # the required SG count cannot fit the unsigned allocation API; on
        # 32-bit hosts the first inert allocator fails instead.
        marker='result=spi_map_msg(&master,&msg);'
        raw=harness.generate_source(self.texts).replace(marker,
            'fail_alloc=1;result=spi_map_buf(&master,&parent,&transfers[0].tx_sg,buffers[0][0],(size_t)-1,DMA_TO_DEVICE);',1)
        binary=self.compile(self.texts,'count-representability',raw=raw)
        row=self.row('normal',binary)
        self.assertEqual((row['result'],row['live_maps'],row['live_allocs']),
                         (-7 if struct.calcsize('P')>4 else -12,0,0))
        overflow=raw.replace('sg_count = len / desc_len + (len % desc_len != 0);',
                             'sg_count = DIV_ROUND_UP(len, desc_len);')
        binary=self.compile(self.texts,'overflowing-round-up',raw=overflow)
        self.assertEqual(self.row('normal',binary)['result'],-22)
        vmalloc=raw.replace('fail_alloc=1;result=spi_map_buf',
                            'vmalloc_mode=1;fail_alloc=1;result=spi_map_buf').replace(
                            'buffers[0][0],(size_t)-1','buffers[0][0]+15,(size_t)-1')
        binary=self.compile(self.texts,'vmalloc-length-offset-overflow',raw=vmalloc)
        self.assertEqual(self.row('normal',binary)['result'], -7 if struct.calcsize('P')>4 else -12)

    def test_manifest_types_baseline_corruption_and_observation_tampering_fail_closed(self):
        with self.assertRaises(ValueError):harness.generate_source({'core':''})
        with self.assertRaises(ValueError):harness.generate_source(self.texts,baseline=1)
        changed=dict(harness.BASELINE_FUNCTIONS);changed['sg_free_table']+='\n'
        with mock.patch.object(harness,'BASELINE_FUNCTIONS',changed):
            with self.assertRaises(ValueError):harness.generate_source(self.texts,baseline=True)
        original=self.row('normal')
        for key,value in [('live_maps',True),('result',0.0),('maps',7),('sequence','')]:
            row=dict(original);row[key]=value
            with self.assertRaises(ValueError):harness.validate_row(row)
        row=dict(original);row['extra']=0
        with self.assertRaises(ValueError):harness.validate_row(row)


if __name__=='__main__':unittest.main()
