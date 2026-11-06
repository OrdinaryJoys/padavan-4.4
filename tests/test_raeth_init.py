"""Fault injection on actual RAETH bookkeeping and ndo rollback functions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import raeth_init_harness as h
ROOT=Path(__file__).resolve().parents[1]

class RaethInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='raeth-init-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/p).read_text()for k,p in h.SOURCE_PATHS.items()}
        cls.code=h.generate_source(cls.texts)
        cls.source=cls.directory/'current.c';cls.source.write_text(cls.code)
        gcc=shutil.which('gcc-16')or shutil.which('gcc')
        clang=shutil.which('clang')
        if not gcc or not clang:raise AssertionError('GNU and Clang required')
        version=subprocess.check_output([gcc,'--version'],text=True,timeout=10)
        if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for name,compiler in (('gcc',gcc),('clang',clang)):
            binary=cls.directory/name
            cmd=[compiler,'-std=gnu99','-Os','-fno-strict-aliasing','-Wall','-Wextra','-Werror']
            if name=='clang':cmd+=['-fsanitize=address,undefined']
            subprocess.run([*cmd,str(cls.source),'-o',str(binary)],check=True,capture_output=True,text=True,timeout=60)
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
    def test_each_allocation_failure_has_no_published_global_or_retained_heap(self):
        self.rows([n for n in h.CASE_NAMES if n.startswith('oom-')])
    def test_missing_or_overflowing_dimensions_are_rejected_before_allocation(self):
        self.rows([n for n in h.CASE_NAMES if n.startswith('missing-')or n in ('zero-txq','zero-txd','zero-rx','tx1-overflow','tx2-overflow','tx-sum-overflow')])
    def test_all_existing_owners_are_retained_without_allocating(self):
        self.rows([n for n in h.CASE_NAMES if n.startswith('owned-')])
    def test_success_zeroes_slots_retry_succeeds_and_free_is_idempotent(self):
        self.rows(('success','single-gmac','retry'))
    def test_ndo_uninit_retires_only_matching_napi_owners(self):
        self.rows([n for n in h.CASE_NAMES if n.startswith('napi-')or n=='late-register-failure'])
    def test_full_functions_and_explicit_source_only_probe_boundary(self):
        self.assertEqual(len(h.CASE_NAMES),45);self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),3);self.assertEqual(len(h.source_only_manifest(self.texts)),2)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.code.count(h.function(self.texts[key],name)),1)
        self.assertEqual(h.MODEL_VARIANT['MAX_RX_RING_NUM'],4)
        header=(ROOT/'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.h').read_text()
        self.assertRegex(header,r'#define\s+MAX_RX_RING_NUM\s+4\b')
        with self.assertRaises(ValueError):h.generate_source({})
    def test_probe_stops_before_mmio_and_unwinds_publication_on_error(self):
        body=h.function(self.texts['raeth'],'rather_probe')
        self.assertIn('ret = fe_tx_rx_dec(ei_local, pdev);\n\tif (ret)\n\t\tgoto err_free_dev;',body)
        self.assertLess(body.index('ret = fe_tx_rx_dec('),body.index('of_iomap('))
        cleanup=body[body.index('err_free_dev:'):]
        for token in ('mii_mgr_detach();','debug_proc_exit();','raeth_release_resources(ei_local, pdev);','dev_raether = NULL;','free_netdev(netdev);'):
            self.assertEqual(cleanup.count(token),1)
        self.assertLess(cleanup.index('mii_mgr_detach();'),cleanup.index('raeth_release_resources('))
        self.assertLess(cleanup.index('raeth_release_resources('),cleanup.index('dev_raether = NULL;'))
        self.assertLess(cleanup.index('dev_raether = NULL;'),cleanup.index('free_netdev(netdev);'))
        owners=h.function(self.texts['raeth'],'raeth_release_resources')
        for token in ('ei_clock_disable(ei_local);','of_node_put(ei_local->switch_np);','platform_device_put(ei_local->qdma_pdev);','fe_tx_rx_dec_free(ei_local);','put_device(&pdev->dev);'):
            self.assertEqual(owners.count(token),1)
        self.assertIn('ei_local->qdma_pdev != pdev',owners)
        self.assertNotIn('devm_',body)
        self.assertIn('if (!ethdma_sysctl_base)',body)
        self.assertIn('of_node_put(node);',body)
        self.assertLess(body.index('if (dev_raether)'),body.index('alloc_etherdev_mqs('))
        self.assertNotRegex(self.texts['raeth'],r'static int __init ei_init\(')
    def test_builtin_driver_blocks_manual_unbind_with_unretired_dma(self):
        body=self.texts['raeth'].split('static struct platform_driver raeth_driver = {',1)[1].split('module_platform_driver',1)[0]
        self.assertIn('.suppress_bind_attrs = true,',body)
        self.assertIn('if (!drv->suppress_bind_attrs) {\n\t\terror = add_bind_files(drv);',self.texts['bus'])
        self.assertRegex(self.texts['device_header'],r'bool\s+suppress_bind_attrs;')
        self.assertTrue(h.MODEL_VARIANT['sysfs_bind_unbind_disabled'])
    def reject(self,code,case,label):
        source=self.directory/(label+'.c');source.write_text(code);binary=source.with_suffix('')
        r=subprocess.run([shutil.which('clang'),'-std=gnu99','-Os','-fno-strict-aliasing','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        env=dict(os.environ);env['ASAN_OPTIONS']=env.get('ASAN_OPTIONS','')+':symbolize=0'
        r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10,env=env)
        if r.returncode==0:
            self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case],'Removed guard unexpectedly accepted')
    def test_oom_rollback_removal_is_rejected(self):
        before='no_mem:\n\tfe_tx_rx_dec_free(ei_local);'
        self.assertEqual(self.code.count(before),1)
        self.reject(self.code.replace(before,'no_mem:\n\t/* missing rollback */'), 'oom-7','no-rollback')
    def test_global_publication_before_allocation_is_rejected(self):
        before='\t/* Zero unused slots so later partial initialization cannot invent owners. */'
        self.assertEqual(self.code.count(before),1)
        self.reject(self.code.replace(before,'\tnum_tx_desc = tx;\n'+before),'oom-2','early-publish')
    def test_missing_napi_cleanup_is_rejected(self):
        before='\t\tnetif_napi_del(&ei_local->napi_rx_rss3);'
        self.assertEqual(self.code.count(before),1)
        self.reject(self.code.replace(before,'\t\t/* missing NAPI owner */'),'napi-rss4','missing-napi')
    def test_old_recursive_netdev_uninit_is_not_reintroduced(self):
        old=subprocess.check_output(['git','-C',str(ROOT),'show','c4d8e113ffba5f85eb5f37a75b3c5f23594ed193:'+h.SOURCE_PATHS['raeth']],text=True)
        body=h.function(old,'ei_uninit')
        self.assertIn('unregister_netdev(dev);',body);self.assertIn('free_netdev(dev);',body)
        current=h.function(self.texts['raeth'],'ei_uninit')
        self.assertNotIn('unregister_netdev(',current);self.assertNotIn('free_netdev(',current)
        # The core owns registration; a modeled recursive unregister aborts immediately.
        extra='''\n#define FE_GE2_SUPPORT 32U
#define pr_info(...) ((void)0)
#define debug_proc_exit() ((void)0)
#define unregister_netdev(dev) do { (void)(dev); abort(); } while(0)
#define free_netdev(dev) do { (void)(dev); abort(); } while(0)
'''
        # The old optional pseudo_dev access is retained as an inert structural seam.
        code=self.code.replace('struct END_DEVICE {','struct END_DEVICE {\n struct net_device *pseudo_dev;')
        code=code.replace(current,extra+body).replace('name=argv[1];','name=argv[1]; (void)netif_napi_del;')
        self.reject(code,'napi-full','old-recursive-uninit')

if __name__=='__main__':unittest.main()
