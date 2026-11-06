"""Authorization and fault checks on inert whole RAETH ioctl handlers."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import raeth_ioctl_harness as h
ROOT=Path(__file__).resolve().parents[1]

class RaethIoctlTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='raeth-ioctl-');cls.directory=Path(cls.temp.name)
  cls.texts={k:(ROOT/p).read_text()for k,p in h.SOURCE_PATHS.items()};cls.code=h.generate_source(cls.texts)
  source=cls.directory/'current.c';source.write_text(cls.code)
  gcc=shutil.which('gcc-16')or shutil.which('gcc');clang=shutil.which('clang')
  if not gcc or not clang:raise AssertionError('GNU GCC and Clang required')
  version=subprocess.check_output([gcc,'--version'],text=True,timeout=10)
  if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
  cls.binaries=[]
  for name,compiler in(('gcc',gcc),('clang',clang)):
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
     self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
 def test_all_private_request_types_require_privilege_before_usercopy_or_hardware(self):self.rows([n for n in h.CASE_NAMES if n.startswith('unauthorized-')])
 def test_all_partial_input_copies_stop_without_hardware_or_shared_lock(self):self.rows([n for n in h.CASE_NAMES if n.startswith('copy-fail-')])
 def test_register_and_mii_replies_copy_after_unlock_and_report_copy_failure(self):self.rows([n for n in h.CASE_NAMES if n.startswith('read-')or n.startswith('out-fail-')])
 def test_writes_and_mdio_failures_propagate_outcomes(self):self.rows([n for n in h.CASE_NAMES if n.startswith('write-')or n.startswith('mdio-fail-')])
 def test_qdma_bounds_preserve_table_and_lan_state_on_failure(self):self.rows([n for n in h.CASE_NAMES if n.startswith('qdma-')or n.startswith('esw-')or n.startswith('magic-')])
 def test_phy_switch_ephy_ip_and_feature_routes_avoid_descriptor_lock(self):self.rows(('phy-dump','switch-valid','ephy-valid','ephy-fail','ip-valid','ip-unterminated','ingress-valid','egress-valid','sfq-disabled','sfq-on','sfq-off','ingress-port-7','egress-onoff-2'))
 def test_terminal_and_unknown_admissions_are_closed(self):self.rows(('quarantined','unknown'))
 def test_pseudo_interface_uses_same_checked_hardware_owner_path(self):self.rows([n for n in h.CASE_NAMES if n.startswith('pseudo-')])
 def test_whole_functions_actual_uapi_layout_and_source_only_dispatch_boundaries(self):
  self.assertEqual(len(h.CASE_NAMES),78);self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
  self.assertEqual(len(h.function_manifest(self.texts)),3);self.assertEqual(len(h.source_only_manifest(self.texts)),1)
  for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.code.count(h.function(self.texts[key],name)),1)
  for name in('esw_reg','ra_mii_ioctl_data','ra_switch_ioctl_data','qdma_ioctl_data','ephy_ioctl_data','esw_rate'):
   actual=re.search(r'struct '+name+r' \{[\s\S]*?\};',self.texts['ioctl_header']).group();self.assertIn(actual,h.PREFIX)
  core=h.function(self.texts['core'],'dev_ioctl');private=core[core.index('Unknown or private ioctl.'):]
  self.assertIn('rtnl_lock();',private);self.assertIn('ret = dev_ifsioc(net, &ifr, cmd);',private);self.assertNotIn('capable(',private)
  self.assertIn('#define EOPNOTSUPP\t122\t',self.texts['mips_errno']);self.assertIn('spin_lock_irqsave(&mdio_bus_lock, *flags);',self.texts['mdio']);self.assertNotIn('time_after(',self.texts['mdio'])
  self.assertTrue(h.MODEL_VARIANT['RTNL_dispatch_and_MDIO_wait_source_only']);self.assertFalse(h.MODEL_VARIANT['actual_user_pointer_access_or_ioctl_executed'])
  with self.assertRaises(ValueError):h.generate_source({})
 def reject(self,code,case,label):
  source=self.directory/(label+'.c');source.write_text(code);binary=source.with_suffix('')
  r=subprocess.run([shutil.which('clang'),'-std=gnu99','-Os','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
  self.assertEqual(r.returncode,0,r.stderr)
  r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10,env=dict(os.environ,ASAN_OPTIONS='symbolize=0'))
  if not r.returncode:self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case],'Semantic fault unexpectedly accepted')
 def test_removed_authorization_and_partial_copy_guards_are_rejected(self):
  self.assertEqual(self.code.count('if (!capable(CAP_NET_ADMIN))'),1)
  self.reject(self.code.replace('if (!capable(CAP_NET_ADMIN))','if (capable(CAP_NET_ADMIN) && 0)'),'unauthorized-qdma','no-authorization')
  old='if (copy_from_user(request, ifr->ifr_data, request_size))\n\t\treturn -EFAULT;';self.assertEqual(self.code.count(old),1)
  self.reject(self.code.replace(old,'(void)copy_from_user(request, ifr->ifr_data, request_size);'),'copy-fail-qdma','ignored-copy-fault')
 def test_removed_qdma_bounds_and_nested_error_propagation_are_rejected(self):
  old='if ((data->off & 0xff) >= ARRAY_SIZE(M2Q_table))';self.assertEqual(self.code.count(old),1)
  self.reject(self.code.replace(old,'if (0)'),'qdma-map-64','missing-map-bound')
  old='ret = ei_qdma_ioctl(dev, ifr, &qdma_data);';self.assertEqual(self.code.count(old),1)
  self.reject(self.code.replace(old,'(void)ei_qdma_ioctl(dev, ifr, &qdma_data);'),'qdma-large','ignored-nested-error')
 def test_atomic_usercopy_and_missing_ip_termination_guards_are_rejected(self):
  old='if (copy_from_user(request, ifr->ifr_data, request_size))\n\t\treturn -EFAULT;'
  replacement='model_lock();\n\tif (copy_from_user(request, ifr->ifr_data, request_size)) { model_unlock(); return -EFAULT; }\n\tmodel_unlock();'
  self.reject(self.code.replace(old,replacement),'read-qdma','atomic-usercopy')
  old='if (!memchr(ip_tmp, 0, sizeof(ip_tmp)))';self.assertEqual(self.code.count(old),1)
  self.reject(self.code.replace(old,'if (0)'),'ip-unterminated','unterminated-ip')
 def test_removed_mdio_error_propagation_is_rejected(self):
  body=h.function(self.texts['raeth'],'ei_ioctl');self.assertEqual(body.count('ret = -EIO;'),6)
  self.reject(self.code.replace(body,body.replace('ret = -EIO;','ret = 0;')),'mdio-fail-mii-read','ignored-mdio-error')

if __name__=='__main__':unittest.main()
