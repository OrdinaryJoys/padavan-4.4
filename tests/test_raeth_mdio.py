"""Complete MDIO bodies with fixed ticks, failures and selected real lock schedules."""
import json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
import raeth_mdio_harness as h
ROOT=Path(__file__).resolve().parents[1]
class RaethMdioTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='raeth-mdio-');cls.root=Path(cls.temp.name)
  cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()};cls.code=h.generate_source(cls.texts)
  cls.flags=['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter']
  cls.compilers=[('gcc',shutil.which('gcc-16')or shutil.which('gcc')),('clang',shutil.which('clang'))]
  version=subprocess.check_output([cls.compilers[0][1],'--version'],text=True)
  if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
  cls.binaries=[]
  for label,cc in cls.compilers:
   src=cls.root/(label+'.c');src.write_text(cls.code);binary=src.with_suffix('')
   subprocess.run([cc,*cls.flags,*(['-fsanitize=address,undefined']if label=='clang'else[]),str(src),'-o',str(binary)],check=True,capture_output=True,text=True,timeout=60);cls.binaries.append(binary)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_fixed_tick_deadlines_every_failure_and_selected_pthread_retirement(self):
  for binary in self.binaries:
   for case in h.CASE_NAMES:
    with self.subTest(binary=binary.name,case=case):
     r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=5)
     self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case])
 def test_complete_source_bodies_and_explicit_shipping_boundaries(self):
  self.assertEqual((len(h.FUNCTION_SOURCES),len(h.CASE_NAMES)),(15,34))
  self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
  for n,k in h.FUNCTION_SOURCES.items():self.assertEqual(self.code.count(h.function(self.texts[k],n)),1)
  self.assertEqual(len(h.source_only_manifest(self.texts)),2)
  self.assertTrue(h.MODEL_VARIANT['ethtool_wrapper_forced_model_not_shipping_K2P_CONFIG_RAETH_ETHTOOL'])
  self.assertNotRegex(self.texts['config'],r'(?m)^CONFIG_RAETH_ETHTOOL=[ym]$')
  self.assertNotIn('jiffies',h.function(self.texts['mdio'],'raeth_mdio_wait'))
  probe=h.function(self.texts['raeth'],'rather_probe');self.assertLess(probe.index('spin_lock_init(&ei_local->page_lock)'),probe.index('debug_proc_init()'))
  self.assertLess(probe.index('mii_mgr_attach();'),probe.index('ethtool_init(netdev);'))
 def test_prototypes_duplicates_and_budget_declaration_drift_reject(self):
  text=self.texts['mdio'];body=h.function(text,'raeth_mdio_lock')
  self.assertEqual(h.function('struct END_DEVICE *raeth_mdio_lock(unsigned long *flags);\n'+text,'raeth_mdio_lock'),body)
  with self.assertRaises(ValueError):h.function(text+'\n'+body,'raeth_mdio_lock')
  bad=dict(self.texts);bad['mdio']=bad['mdio'].replace('#define RAETH_MDIO_POLLS 1000','#define RAETH_MDIO_POLLS 2000')
  with self.assertRaises(ValueError):h.generate_source(bad)
 def reject(self,old,new,case,label):
  self.assertIn(old,self.code);src=self.root/(label+'.c');src.write_text(self.code.replace(old,new,1));binary=src.with_suffix('')
  result=subprocess.run([self.compilers[1][1],*self.flags,'-fsanitize=address,undefined',str(src),'-o',str(binary)],capture_output=True,text=True,timeout=60)
  if result.returncode:return
  try:r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=1)
  except subprocess.TimeoutExpired:return
  if r.returncode==0:self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case],label)
 def test_old_failure_patterns_are_rejected_without_real_io(self):
  self.reject('if (!*budget)\n\t\t\treturn 0;','if (0)\n\t\t\treturn 0;','initial-busy','unbounded-clock')
  self.reject('if (!raeth_mdio_wait(budget))\n\t\treturn 0;','*budget = RAETH_MDIO_POLLS;\n\tif (!raeth_mdio_wait(budget))\n\t\treturn 0;','switch-shared-budget','per-command-budget')
  self.reject('NULL, &budget) &&\n\t     raeth_mdio_xfer((dev_addr << 25) | (port_num << 20) | (3U << 18),','NULL, &budget),\n\t     raeth_mdio_xfer((dev_addr << 25) | (port_num << 20) | (3U << 18),','cl45-late-address','ignore-address-failure')
  self.reject('if (mdio_detached || !dev_raether)','if (!dev_raether)','detach-joins','lost-retirement')
  self.reject('dev_put(cur_dev_p);','/* missing reference release */','phy-ref','leaked-netdev')
 def test_transaction_lock_and_poll_restore_mutations_reject(self):
  self.reject('(write_data & 0xffff)','((write_data & 0xffff) ^ 1U)','switch-write','switch-write-payload-bit')
  self.reject('| write_data,','| (write_data ^ 1U),','write','c22-write-payload-bit')
  self.reject('write_data, NULL, &budget)','(write_data ^ 1U), NULL, &budget)','cl45-write','c45-write-payload-bit')
  self.reject('sys_reg_write(MDIO_PHY_CONTROL_0, data);','/* omitted initial command write */','write','lost-initial-write')
  self.reject('spin_lock_irqsave(&mdio_bus_lock, *flags);','*flags = 0; /* missing lock */','read','missing-bus-lock')
  self.reject('if (an_status)\n\t\t\tset_an_polling(1);','if (0)\n\t\t\tset_an_polling(1);','switch-fail-2','lost-poll-restore')
