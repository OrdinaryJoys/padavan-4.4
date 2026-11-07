"""RAETH terminal shutdown and complete platform dispatcher fault regressions."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import raeth_shutdown_harness as h

ROOT=Path(__file__).resolve().parents[1]

class RaethShutdownTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='raeth-shutdown-');cls.root=Path(cls.temp.name)
  cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()};cls.code=h.generate_source(cls.texts)
  cls.flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror'];cls.compilers=[('gcc',shutil.which('gcc-16')),('clang',shutil.which('clang'))]
  if any(not cc for _,cc in cls.compilers):raise AssertionError('GNU16 and Clang required')
  cc=cls.compilers[0][1];version=subprocess.check_output([cc,'--version'],text=True);major=subprocess.check_output([cc,'-dumpversion'],text=True).split('.')[0].strip()
  if 'Free Software Foundation'not in version or'clang'in version.lower()or major!='16':raise AssertionError('True GNU major16 required')
  cls.binaries={}
  for label,cc in cls.compilers:cls.binaries[label]=cls.compile_code(cls.code,label,cc)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 @classmethod
 def compile_code(cls,code,name,cc=None):
  cc=cc or cls.compilers[1][1];src=cls.root/(name+'.c');src.write_text(code);binary=src.with_suffix('')
  flags=cls.flags+(['-fsanitize=address,undefined']if 'clang'in subprocess.check_output([cc,'--version'],text=True).lower()else[])
  r=subprocess.run([cc,*flags,str(src),'-o',str(binary)],capture_output=True,text=True,timeout=60)
  if r.returncode:raise AssertionError(r.stderr)
  return binary
 def run_row(self,binary,case):
  r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=5,env=dict(os.environ,ASAN_OPTIONS='symbolize=0'))
  return r,json.loads(r.stdout)if r.stdout else None
 def reject_code(self,code,case,label):
  binary=self.compile_code(code,label);r,row=self.run_row(binary,case)
  self.assertTrue(r.returncode!=0 or row!=h.EXPECTED_ROWS[case],label)
 def mutate(self,name,old,new,case,label,source='raeth'):
  texts=dict(self.texts);body=h.function(texts[source],name);self.assertEqual(body.count(old),1,label)
  texts[source]=texts[source].replace(body,body.replace(old,new,1),1)
  self.reject_code(h.generate_source(texts),case,label)
 def test_all_typed_terminal_shutdown_idle_and_busy_observations(self):
  for label,binary in self.binaries.items():
   for case in h.CASE_NAMES:
    with self.subTest(compiler=label,case=case):
     r,row=self.run_row(binary,case);self.assertEqual((r.returncode,r.stderr),(0,''),r.stderr);self.assertEqual(row,h.EXPECTED_ROWS[case])
   self.assertEqual(self.run_row(binary,'unknown-selector')[0].returncode,91)
 def test_complete_body_declaration_and_source_only_execution_boundaries(self):
  self.assertEqual((len(h.FUNCTION_SOURCES),len(h.SOURCE_ONLY_FUNCTION_SOURCES),len(h.SOURCE_DECLARATIONS)),(7,3,3))
  self.assertEqual(len(h.function_manifest(self.texts)),7);self.assertEqual(len(h.source_only_manifest(self.texts)),3)
  self.assertEqual(len(h.source_declarations(self.texts)),3)
  for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.code.count(h.function(self.texts[key],name)),1)
  for name,key in h.SOURCE_ONLY_FUNCTION_SOURCES.items():self.assertNotIn(h.function(self.texts[key],name),self.code)
  self.assertTrue(h.MODEL_VARIANT['actual_platform_drv_shutdown_whole_executed'])
  self.assertTrue(h.MODEL_VARIANT['platform_core_reboot_source_only_not_compiled_bound_here'])
  self.assertTrue(h.MODEL_VARIANT['hardware_DMA_IRQ_threads_RTNL_and_module_references_are_inert'])
 def test_fixed_actual_source60_initializer_executes_the_missing_callback_regression(self):
  old=h.BASELINE_INITIALIZER;manifest=h.BASELINE_MANIFEST
  self.assertEqual(manifest['source_commit'],'60ae6bf98bd46b68c648620c599f1aa78073131e')
  self.assertEqual(manifest['path'],h.SOURCE_PATHS['raeth']);self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),manifest['sha256'])
  self.assertNotIn('.shutdown',old)
  pattern=next(iter(h.SOURCE_DECLARATIONS));current=re.findall(pattern,self.texts['raeth'],re.M);self.assertEqual(len(current),1)
  texts=dict(self.texts);texts['raeth']=texts['raeth'].replace(current[0],old,1);code=h.generate_source(texts)
  for label,cc in self.compilers:
   r,row=self.run_row(self.compile_code(code,'old-initializer-'+label,cc),'up-pseudo')
   self.assertEqual((r.returncode,r.stderr),(0,''));self.assertEqual((row['quarantined'],row['main_attached'],row['pseudo_attached'],row['stop_calls'],row['pm_detach']),(0,1,1,0,1))
   self.assertNotEqual(row,h.EXPECTED_ROWS['up-pseudo'])
 def test_missing_wrong_callback_and_duplicate_initializer_are_not_accepted(self):
  for label,needle,replacement in [('missing-callback','\t.shutdown = raether_shutdown,',''),('wrong-callback','\t.shutdown = raether_shutdown,','\t.shutdown = alternate_shutdown,')]:
   texts=dict(self.texts);self.assertEqual(texts['raeth'].count(needle),1);texts['raeth']=texts['raeth'].replace(needle,replacement,1)
   code=h.generate_source(texts)
   if label=='wrong-callback':code=code.replace('static const char raeth_string[]=', 'static void alternate_shutdown(struct platform_device *p) { (void)p; }\nstatic const char raeth_string[]=')
   self.reject_code(code,'up-pseudo',label)
  texts=dict(self.texts);texts['raeth']+='\n'+h.BASELINE_INITIALIZER
  with self.assertRaises(ValueError):h.generate_source(texts)
 def test_success_and_busy_keep_every_owner_and_module_reference(self):
  for case in h.CASE_NAMES:
   row=h.EXPECTED_ROWS[case];self.assertEqual((row['releases'],row['resets'],row['module_gets'],row['module_puts']),(0,0,0,0))
  self.mutate('raether_shutdown','err = ei_stop_dma(dev);','err = ei_stop_dma(dev);\n\tei_deinit_dma(dev);','pdma-busy','free-after-busy')
  self.mutate('raether_shutdown','err = ei_stop_dma(dev);','err = ei_stop_dma(dev);\n\tfe_reset();','up-pseudo','reset-after-idle')
  self.mutate('raether_shutdown','err = ei_stop_dma(dev);','err = ei_stop_dma(dev);\n\tmodule_put(THIS_MODULE);','up-pseudo','shutdown-module-put')
  self.mutate('raether_shutdown','err = ei_stop_dma(dev);','err = ei_stop_dma(dev);\n\t(void)try_module_get(THIS_MODULE);','no-module-pin-up','shutdown-module-get')
 def test_tx_threads_irq_join_and_detach_order_mutants_are_detected(self):
  self.mutate('raether_shutdown','\tnetif_tx_disable(dev);','\t/* missing main TX join */','up-pseudo','missing-tx')
  self.mutate('raether_shutdown','\tfe_int_disable(dev);','\t/* missing IRQ join */','up-pseudo','missing-irq')
  self.mutate('raether_shutdown','\tfe_int_disable(dev);\n\terr = ei_stop_dma(dev);','\terr = ei_stop_dma(dev);\n\tfe_int_disable(dev);','up-pseudo','idle-before-irq')
  self.mutate('raether_shutdown','\t\tkthread_stop(ei_local->kreset_task);','\t\t/* missing thread join */','up-pseudo','missing-thread')
  self.mutate('raether_shutdown','\tWRITE_ONCE(ei_local->dma_quarantined, true);','\tWRITE_ONCE(ei_local->dma_quarantined, false);','up-pseudo','reopen-allowed')
  self.mutate('raether_shutdown','\trtnl_unlock();\n\t/* Readers','\t/* still holding RTNL */\n\t/* Readers','up-pseudo','retire-under-rtnl')
 def test_bounded_idle_and_platform_pm_continuation_mutants_are_detected(self):
  self.mutate('raether_shutdown','err = ei_stop_dma(dev);','err = 0;','pdma-busy','skip-stop-idle')
  self.mutate('ei_stop_dma','qdma_err = fe_qdma_wait_dma_idle();','qdma_err = 0;','qdma-busy','skip-qdma-idle')
  self.mutate('fe_pdma_wait_dma_idle','loop_cnt < 1000','loop_cnt < 999','pdma-busy','wrong-poll-bound','pdma')
  self.mutate('platform_drv_shutdown','\tdev_pm_domain_detach(_dev, true);','\tif (!priv.dma_quarantined) dev_pm_domain_detach(_dev, true);','pdma-busy','pretend-shutdown-veto','platform')
  self.mutate('ei_close','\tif (ei_local->dma_quarantined)\n\t\treturn -EBUSY;','\t/* quarantine guard lost */','shutdown-close','close-frees-after-shutdown')
 def test_parser_exact_source_set_and_actual_profile_are_fail_closed(self):
  with self.assertRaises(ValueError):h.generate_source({})
  texts=dict(self.texts);texts['config']=texts['config'].replace('CONFIG_RAETH=y','CONFIG_RAETH=m')
  with self.assertRaises(ValueError):h.generate_source(texts)
  body=h.function(self.texts['raeth'],'raether_shutdown')
  self.assertEqual(h.function('/* ignored { } */\n'+body+'\n/* ignored */','raether_shutdown'),body)
  with self.assertRaises(ValueError):h.function(body+'\n'+body,'raether_shutdown')
  with self.assertRaises(ValueError):h.function('static void raether_shutdown(struct platform_device *p);','raether_shutdown')
 def test_literal_scenarios_keep_typed_rows_and_forced_variants_explicit(self):
  self.assertEqual((len(h.CASE_NAMES),len(h.FIELDS)),(27,31));self.assertEqual(tuple(h.EXPECTED_ROWS),h.CASE_NAMES)
  for name,row in h.EXPECTED_ROWS.items():
   self.assertEqual(tuple(row),h.FIELDS,name);self.assertTrue(all(type(v)is int for v in row.values()),name)
  self.assertEqual(h.EXPECTED_ROWS['both-busy']['delay'],20000)
  self.assertEqual(h.EXPECTED_ROWS['repeat-busy']['delay'],20000)
  self.assertEqual(h.EXPECTED_ROWS['busy-then-idle']['pdma_reads'],1001)
  self.assertTrue(h.MODEL_VARIANT['forced_WORKQ_NAPI_are_nonshipping_variants'])
  for name in ('forced-workq','forced-napi','forced-napi-txrx','forced-napi-rss2','forced-napi-rss4'):self.assertIn(name,h.CASE_NAMES)
 def test_actual_reboot_dispatch_is_source_only_and_void_cannot_veto_reset(self):
  register=h.function(self.texts['platform'],'__platform_driver_register');prepare=h.function(self.texts['reboot'],'kernel_restart_prepare')
  self.assertIn('drv->driver.shutdown = platform_drv_shutdown;',register)
  self.assertIn('device_shutdown();',prepare);self.assertIn('usermodehelper_disable();',prepare)
  self.assertIn('dev->driver->shutdown(dev);',h.function(self.texts['core'],'device_shutdown'))
  self.assertTrue(h.MODEL_VARIANT['void_shutdown_cannot_veto_machine_reset'])
  for name in ('pdma-busy','qdma-busy','both-busy'):
   row=h.EXPECTED_ROWS[name];self.assertEqual(row['pm_detach'],1);self.assertEqual(row['owners'],31)

if __name__=='__main__':unittest.main()
