"""Cross driver-core/devres and complete RAETH remove source-body fault models."""
import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
import raeth_remove_harness as h
ROOT=Path(__file__).resolve().parents[1]
class RaethRemoveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='raeth-remove-');cls.root=Path(cls.temp.name)
  cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()};cls.code=h.generate_source(cls.texts)
  cls.flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror'];cls.compilers=[('gcc',shutil.which('gcc-16')or shutil.which('gcc')),('clang',shutil.which('clang'))]
  if any(not cc for _,cc in cls.compilers):raise AssertionError('GNU GCC and Clang required')
  version=subprocess.check_output([cls.compilers[0][1],'--version'],text=True)
  if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
  cls.binaries=[]
  for label,cc in cls.compilers:
   src=cls.root/(label+'.c');src.write_text(cls.code);binary=src.with_suffix('')
   r=subprocess.run([cc,*cls.flags,*(['-fsanitize=address,undefined']if label=='clang'else[]),str(src),'-o',str(binary)],capture_output=True,text=True,timeout=60)
   if r.returncode:raise AssertionError(r.stderr)
   cls.binaries.append(binary)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_complete_remove_core_release_and_every_owner_fault_observation(self):
  for binary in self.binaries:
   for case in h.CASE_NAMES:
    with self.subTest(binary=binary.name,case=case):
     r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=5)
     self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case])
 def test_complete_sources_explicit_ownership_and_scoped_concurrency_claims(self):
  self.assertEqual((len(h.FUNCTION_SOURCES),len(h.CASE_NAMES)),(10,20));self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
  self.assertEqual(len(h.source_only_manifest(self.texts)),1)
  for n,k in h.FUNCTION_SOURCES.items():self.assertEqual(self.code.count(h.function(self.texts[k],n)),1)
  core=h.function(self.texts['core'],'__device_release_driver')
  self.assertIn('drv->remove(dev);\n\t\tdevres_release_all(dev);',core);self.assertIn('dev_set_drvdata(dev, NULL);',core)
  probe=h.function(self.texts['raeth'],'rather_probe');release=h.function(self.texts['raeth'],'raeth_release_resources')
  self.assertNotIn('devm_',probe)
  for token in ('get_device(&pdev->dev);','request_mem_region(','ioremap(res->start,','clk_get(&pdev->dev,','platform_set_drvdata(pdev, netdev);'):self.assertIn(token,probe)
  for token in ('put_device(&pdev->dev);','release_mem_region(','clk_put(','ei_local->qdma_pdev != pdev'):self.assertIn(token,release)
  self.assertNotIn('->dev.release(',release)
  remove=h.function(self.texts['raeth'],'raether_remove')
  self.assertLess(remove.index('mii_mgr_detach();'),remove.index('raeth_release_resources('))
  self.assertLess(remove.index('fe_int_disable(dev);'),remove.index('err = ei_stop_dma(dev);'))
  self.assertLess(remove.index('if (err ||'),remove.index('unregister_netdevice(dev);'))
  pseudo=h.function(self.texts['raeth'],'raeth_init_pseudo');self.assertIn('if (register_netdev(dev)) {',pseudo)
  self.assertLess(pseudo.index('if (register_netdev(dev)) {'),pseudo.index('p_ad->pseudo_dev = dev;'))
  self.assertTrue(h.MODEL_VARIANT['foreign_netdev_reference_snapshot_only']);self.assertTrue(h.MODEL_VARIANT['generic_remove_all_profiles_not_claimed'])
  with self.assertRaises(ValueError):h.generate_source({})
 def reject(self,old,new,case,label):
  self.assertIn(old,self.code);src=self.root/(label+'.c');src.write_text(self.code.replace(old,new,1));binary=src.with_suffix('')
  r=subprocess.run([self.compilers[1][1],*self.flags,'-fsanitize=address,undefined',str(src),'-o',str(binary)],capture_output=True,text=True,timeout=60)
  self.assertEqual(r.returncode,0,r.stderr)
  r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=5,env=dict(os.environ,ASAN_OPTIONS='symbolize=0'))
  if not r.returncode:self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case],label)
 def test_ignored_idle_foreign_consumers_and_quarantine_patterns_reject(self):
  self.reject('if (err || was_quarantined || foreign_users || !ei_local->module_reserved)','if (was_quarantined || foreign_users || !ei_local->module_reserved)','pdma-busy','ignored-idle')
  self.reject('if (err || was_quarantined || foreign_users || !ei_local->module_reserved)','(void)foreign_users;\n\tif (err || was_quarantined || !ei_local->module_reserved)','foreign-main','ignored-users')
  self.reject('if (err || was_quarantined || foreign_users || !ei_local->module_reserved)','(void)was_quarantined;\n\tif (err || foreign_users || !ei_local->module_reserved)','quarantined','ignored-quarantine')
 def test_irq_owner_devres_and_qdma_borrowed_owner_regressions_reject(self):
  self.reject('\tfe_int_disable(dev);\n\terr = ei_stop_dma(dev);\n\tforeign_users','\t/* missing IRQ/BH join */\n\terr = ei_stop_dma(dev);\n\tforeign_users','success','missing-irq-join')
  self.reject('ei_local->qdma_pdev && ei_local->qdma_pdev != pdev','ei_local->qdma_pdev','success','borrowed-parent-put')
  self.reject('if (register_netdev(dev)) {','if ((register_netdev(dev), 0)) {','pseudo-first-register-fail','ignored-pseudo-registration')
  self.reject('devres_managed,devres_unmaps;','devres_managed=3,devres_unmaps;','pdma-busy','devm-unmaps-after-failure')
if __name__=='__main__':unittest.main()
