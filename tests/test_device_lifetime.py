"""K2P no-detach: real core paths, failure rollback and deterministic races."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import device_lifetime_harness as h

class DeviceLifetimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='k2p-lifetime-');cls.addClassCleanup(cls.tmp.cleanup);cls.path=Path(cls.tmp.name)
  cls.compilers=[('gcc',shutil.which('gcc-16'),[],[]),('clang',shutil.which('clang'),['-fsanitize=address,undefined','-fno-sanitize-recover=all'],[])]
  if os.environ.get('K2P_LIFETIME_TARGET_CC'):
   cls.compilers.append(('mips',os.environ['K2P_LIFETIME_TARGET_CC'],['-static'],[shutil.which('qemu-mipsel')]))
  cls.receipt=os.environ.get('K2P_LIFETIME_REPORT')
  if cls.receipt:
   assert os.environ.get('K2P_LIFETIME_TARGET_CC'), 'Receipt requires real target compiler'
   cls.receipt=Path(cls.receipt);cls.executions=[];cls.binaries={}
   cls.receipt.parent.mkdir(parents=True,exist_ok=True)
 @classmethod
 def tearDownClass(cls):
  if cls.receipt:
   cls.receipt.write_text(json.dumps({'schema_version':1,'binaries':cls.binaries,'executions':cls.executions},indent=2)+'\n')
 def compile(self,name,code,only_gcc=False):
  src=self.path/(name+'.c');src.write_text(code)
  for label,cc,flags,runner in self.compilers[:1] if only_gcc else self.compilers:
   self.assertTrue(cc);self.assertTrue(all(runner));out=self.path/(name+'-'+label)
   done=subprocess.run([cc,'-std=gnu11','-O2','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-but-set-variable',*flags,str(src),'-o',str(out)],capture_output=True,text=True,timeout=90)
   self.assertEqual(done.returncode,0,done.stderr)
   if label=='mips' and self.receipt:
    data=out.read_bytes();self.assertEqual(data[:7],b'\x7fELF\x01\x01\x01');self.assertEqual(int.from_bytes(data[18:20],'little'),8)
    stem='target-device-lifetime-exec-'+name
    shutil.copyfile(out,self.receipt.parent/(stem+'.elf'));shutil.copyfile(src,self.receipt.parent/(stem+'.c'))
    self.binaries[out.name]={'name':name,'elf_file':stem+'.elf','source_file':stem+'.c','elf_sha256':hashlib.sha256(data).hexdigest(),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'compiler':cc,'compiler_target':subprocess.check_output([cc,'-dumpmachine'],text=True).strip(),'runner':runner[0],'runner_version':subprocess.check_output([runner[0],'--version'],text=True).splitlines()[0]}
   yield [*runner,str(out)]
 def run_case(self,cmd,case):
  result=subprocess.run([*cmd,case],capture_output=True,text=True,timeout=12,env={**os.environ,'ASAN_OPTIONS':'symbolize=0'})
  if self.receipt and Path(cmd[-1]).name in self.binaries:
   self.executions.append({'binary':Path(cmd[-1]).name,'case':case,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
  return result
 def test_production_lifetime_and_all_destructive_wrappers(self):
  cases=('probe-wins','remove-wins','overlap','module-refusal','dependency','dependency-removing','driver-race','nonroot','depth','safe-oom','uncertain','ordinary','direct-bind','other-driver','unrelated-release','release','parent-release','delete','unregister','bus-remove','driver-unregister','driver-detach','driver-bus','devres','platform-del','platform-unregister','spi-master','pci-stop','pci-destroy','pci-remove','pci-tree','pci-bus','pci-root-stop','pci-root-remove','pci-driver','pci-bus-direct')
  for cmd in self.compile('production',h.program()):
   for case in cases:
    with self.subTest(compiler=cmd,case=case):
     done=self.run_case(cmd,case);self.assertEqual(done.returncode,0,done.stderr)
 def test_mutants_cannot_skip_parent_claim_module_pin_or_exclusive_detach(self):
  mutations=[('ancestor','for (p = dev; p; p = p->parent)','for (p = dev; p == dev; p = NULL)','probe-wins'),('module','if (!try_module_get(owner->owner))','if (false)','module-refusal'),('exclusive','(LIFETIME_HELD | LIFETIME_DETACHING)','LIFETIME_HELD','overlap'),('quarantine','(dev->lifetime_flags & LIFETIME_UNCERTAIN) ||','false ||','uncertain'),('resources','!(dev->lifetime_flags & LIFETIME_UNCERTAIN)','true','uncertain')]
  for label,old,new,case in mutations:
   with self.subTest(label=label):
    self.assertIn(old,h.CORE);broken=h.CORE.replace(old,new)
    for cmd in self.compile('broken-'+label,h.program(core=broken),True):
     done=self.run_case(cmd,case);self.assertNotEqual(done.returncode,0,'Mutation escaped: '+label)
 def test_disabling_each_top_level_gate_is_detected(self):
  # Mutate all occurrences in the selected complete function, not the lower helpers.
  function_cases=[('drivers/base/dd.c','__device_release_driver','release','device_lifetime_detach_begin(dev)'),('drivers/base/core.c','device_unregister','unregister','device_lifetime_remove_begin(dev)'),('drivers/base/bus.c','bus_remove_device','bus-remove','device_lifetime_remove_begin(dev)'),('drivers/base/driver.c','driver_unregister','driver-unregister','device_lifetime_driver_remove(drv)'),('drivers/base/bus.c','bus_remove_driver','driver-bus','device_lifetime_driver_remove(drv)'),('drivers/base/platform.c','platform_device_unregister','platform-unregister','device_lifetime_remove_begin(&pdev->dev)'),('drivers/spi/spi.c','spi_unregister_master','spi-master','device_lifetime_remove_begin(&master->dev)'),('drivers/pci/remove.c','pci_destroy_dev','pci-destroy','device_lifetime_remove_begin(&dev->dev)'),('drivers/pci/remove.c','pci_remove_bus','pci-bus','device_lifetime_remove_begin(bus->bridge)'),('drivers/pci/remove.c','pci_remove_root_bus','pci-root-remove','device_lifetime_remove_begin(bus->bridge)'),('drivers/pci/pci-driver.c','pci_unregister_driver','pci-driver','device_lifetime_driver_remove(&drv->driver)')]
  for path,name,case,gate in function_cases:
   with self.subTest(name=name):
    original=h.body(path,name);self.assertIn(gate,original);broken=original.replace(gate,'true')
    for cmd in self.compile('skip-'+name,h.program(mutate=(original,broken)),True):
     done=self.run_case(cmd,case);self.assertNotEqual(done.returncode,0,'Mutation escaped: '+name)

 def test_critical_marks_are_only_in_k2p_profile(self):
  import re
  paths=('drivers/mtd/devices/m25p80.c','drivers/spi/spi-mt7621.c','drivers/net/ethernet/raeth/raether.c','drivers/watchdog/mt7621_wdt.c','drivers/net/wireless/mediatek/mt7615/os/linux/pci_main_dev.c')
  for path in paths:
   text=h.read(path)
   self.assertEqual(text.count('.no_forced_unbind = true,'),1,path)
   self.assertRegex(text,r'#ifdef CONFIG_K2P_RESET_GUARD\s*(?:\.suppress_bind_attrs = true,\s*)?\.no_forced_unbind = true,\s*(?:\.suppress_bind_attrs = true,\s*)?#endif' if 'spi-mt7621' not in path else r'#ifdef CONFIG_K2P_RESET_GUARD\s*\.suppress_bind_attrs = true,\s*\.no_forced_unbind = true,\s*(?:\.suppress_bind_attrs = true,\s*)?#endif')
  code='#include <stdbool.h>\n#include <assert.h>\n'+h.HEADER+'\nint main(void){assert(!device_lifetime_probe_begin(0,0));assert(device_lifetime_remove_begin(0));assert(device_lifetime_detach_begin(0));assert(device_lifetime_devres_allowed(0));assert(device_lifetime_driver_remove(0));assert(!device_lifetime_quarantined(0));return 0;}'
  for cmd in self.compile('disabled',code):
   done=self.run_case(cmd,'disabled');self.assertEqual(done.returncode,0,done.stderr)
 def test_pci_dependencies_and_fallible_registration_precede_hardware(self):
  probe=h.body('drivers/pci/pci-driver.c','pci_device_probe')
  self.assertLess(probe.index('device_lifetime_depend'),probe.index('pci_assign_irq'))
  bus=h.body('drivers/base/bus.c','bus_add_driver')
  self.assertLess(bus.index('driver_add_groups(drv, drv->groups)'),bus.index('driver_attach(drv)'))
  for name in ('m25p_probe','mt762x_wdt_probe','rt_pci_probe'):
   path={'m25p_probe':'drivers/mtd/devices/m25p80.c','mt762x_wdt_probe':'drivers/watchdog/mt7621_wdt.c','rt_pci_probe':'drivers/net/wireless/mediatek/mt7615/os/linux/pci_main_dev.c'}[name]
   self.assertIn('device_lifetime_quarantine(',h.body(path,name))

 def test_astra_parent_pins_and_complete_pci_probe_regressions(self):
  import device_lifetime_peer_cases as peer
  cases=('chain-pins','late-ancestor','deep-rollback','no-readd','exact-depth','failed-probe-owner','pci-probe-blocked','pci-probe-admitted','pci-probe-irq-failure')
  for cmd in self.compile('peer-production',peer.program()):
   for case in cases:
    with self.subTest(compiler=cmd,case=case):
     done=self.run_case(cmd,case);self.assertEqual(done.returncode,0,done.stderr)
 def test_astra_negative_controls_for_ancestor_pin_readd_and_pci_probe(self):
  import device_lifetime_peer_cases as peer
  old='struct device_driver *owner = p == dev && drv ? drv : p->lifetime_driver;'
  self.assertIn(old,h.CORE)
  pin=h.CORE.replace(old,'struct device_driver *owner = p == dev && drv ? drv : NULL;')
  old='for (p = dev; p; p = p->parent)\n\t\tif (p->lifetime_flags'
  self.assertIn(old,h.CORE)
  readd=h.CORE.replace(old,'dev->lifetime_flags &= ~LIFETIME_REMOVING;\n\t'+old)
  for label,code,case in [('pin',peer.program(core=pin),'chain-pins'),('readd',peer.program(core=readd),'no-readd'),('pci',peer.program(pci_mutation=True),'pci-probe-blocked')]:
   for cmd in self.compile('peer-negative-'+label,code):
    done=self.run_case(cmd,case);self.assertNotEqual(done.returncode,0,'Peer negative escaped: '+label)

if __name__=='__main__':unittest.main()
