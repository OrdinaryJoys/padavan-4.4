"""Actual enabled switch VLAN and uaccess chain with native fault injection."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import esw_vlan_harness as h
ROOT=Path(__file__).resolve().parents[1]
FLAGS=['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']
class EswVlanTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='k2p-esw-vlan-');cls.directory=Path(cls.temp.name)
  cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()};cls.generated=h.generate_source(cls.texts)
  gnu=shutil.which('gcc-16')or('/opt/homebrew/bin/gcc-16'if Path('/opt/homebrew/bin/gcc-16').is_file()else shutil.which('gcc'))
  if not gnu:raise AssertionError('True GNU GCC required')
  version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
  if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
  cls.binaries=[]
  for label,compiler in(('clang',shutil.which('clang')),('gcc',gnu)):
   if not compiler:raise AssertionError('Compiler absent: '+label)
   cls.binaries.append(cls.build(cls.generated,label,compiler))
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 @classmethod
 def build(cls,text,name,compiler=None):
  source=cls.directory/(name+'.c');source.write_text(text);binary=source.with_suffix('');compiler=compiler or shutil.which('clang')
  flags=FLAGS+(['-fsanitize=address,undefined']if'clang'in compiler else[])
  r=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
  if r.returncode:raise AssertionError(r.stderr)
  return binary
 def run_case(self,binary,name):
  env={**os.environ,'ASAN_OPTIONS':os.environ.get('ASAN_OPTIONS','')+':detect_stack_use_after_return=1'}
  return subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10,env=env)
 def cases(self,names):
  for binary in self.binaries:
   for name in names:
    with self.subTest(compiler=binary.name,case=name):
     r=self.run_case(binary,name);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
 def test_mib_invalid_and_every_read_failure_preserve_canary_and_success_clears_all_bytes(self):self.cases(h.CASE_NAMES[:10])
 def test_every_scalar_setter_rejects_fault_before_hardware_and_denied_admin_has_no_effects(self):self.cases(h.CASE_NAMES[10:17])
 def test_vtcr_write_read_and_bounded_busy_error_have_distinct_results(self):self.cases(h.CASE_NAMES[17:21])
 def test_vlan_set_does_not_publish_failed_entry_and_delete_retains_failed_tail(self):self.cases(h.CASE_NAMES[21:28])
 def test_real_vlan_apply_bridge_init_igmp_and_phy_failures_do_not_publish_success(self):self.cases(h.CASE_NAMES[28:42])
 def test_led_failures_retries_and_success(self):self.cases(h.CASE_NAMES[42:46])
 def test_storm_all_ports_retry_and_rate_encodings(self):self.cases(h.CASE_NAMES[46:50])
 def test_jumbo_checked_rmw_and_retry(self):self.cases(h.CASE_NAMES[50:54])
 def test_link_mode_all_mdio_stages_and_validation(self):self.cases(h.CASE_NAMES[54:60])
 def test_ioctl_ambiguous_writes_getters_and_control_cache_epochs(self):self.cases(h.CASE_NAMES[60:])
 def test_pinned_old_controls_reproduce_ignored_error_early_cache_and_false_down(self):
  fixture=ROOT/'tests/fixtures/esw-controls';manifest=json.loads((fixture/'manifest.json').read_text())
  for n,case in (('change_led_mode','led-every-mdio-failure'),('change_storm_control_broadcast','storm-every-port-failure'),('change_jumbo_frames_accept','jumbo-every-mdio-failure'),('change_port_link_mode_uapi','link-force-every-mdio-failure'),('esw_status_link_port','status-direct-read-failure-preserves-output'),('esw_status_speed_port_uapi','status-direct-read-failure-preserves-output')):
   with self.subTest(function=n,case=case):
    raw=(fixture/(n+'.c')).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest[n]['sha256']);body=h.function(self.texts['esw'],n)
    if n=='change_port_link_mode_uapi':replacement=raw.decode()
    else:
     alias='#define '+n+' old_'+n+'\n'+raw.decode()+'#undef '+n+'\n'
     if n.startswith('esw_status'):
      alias=h.function(self.texts['esw'],'esw_reg_get')+'\n'+alias
      param='port_id' if n=='esw_status_link_port'else'port_id_uapi'
      wrapper='static int '+n+'(u32 '+param+', u32 *result){*result=old_'+n+'('+param+');return 0;}'
     else:wrapper='static int '+n+'(u32 value){old_'+n+'(value);return 0;}'
     replacement=alias+wrapper
    binary=self.build(self.generated.replace(body,replacement),'old-control-'+n);r=self.run_case(binary,case);self.assertEqual(r.returncode,0,r.stderr);self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case])
 def test_control_and_getter_mutants_compile_and_expose_lost_error_or_retry(self):
  mutants=(
   ('change_led_mode','if (ret)\n\t\treturn ret;','if (ret && 0)\n\t\treturn ret;','led-every-mdio-failure'),
   ('change_led_mode',' && !g_led_apply_pending','','led-old-request-recovery'),
   ('change_storm_control_broadcast','if (ret)\n\t\t\treturn ret;','if (ret && 0)\n\t\t\treturn ret;','storm-every-port-failure'),
   ('change_storm_control_broadcast',' && !g_storm_apply_pending','','storm-old-request-recovery'),
   ('change_jumbo_frames_accept','if (ret)\n\t\treturn ret;','if (ret && 0)\n\t\treturn ret;','jumbo-every-mdio-failure'),
   ('change_jumbo_frames_accept',' && !g_jumbo_apply_pending','','jumbo-old-request-recovery'),
   ('esw_jumbo_control','if (ret)\n\t\treturn ret;','if (ret && 0)\n\t\treturn ret;','jumbo-every-mdio-failure'),
   ('change_port_link_mode_uapi','if (!mii_mgr_read(phy_mdio_addr, 9, &esw_phy_gcr))','if (!mii_mgr_read(phy_mdio_addr, 9, &esw_phy_gcr) && 0)','link-force-every-mdio-failure'),
   ('change_port_link_mode_uapi','if (!mii_mgr_write(phy_mdio_addr, 9, esw_phy_gcr))','if (!mii_mgr_write(phy_mdio_addr, 9, esw_phy_gcr) && 0)','link-force-every-mdio-failure'),
   ('change_port_link_mode_uapi','if (!mii_mgr_write(phy_mdio_addr, 4, esw_phy_ana))','if (!mii_mgr_write(phy_mdio_addr, 4, esw_phy_ana) && 0)','link-force-every-mdio-failure'),
   ('change_port_link_mode_uapi','\n\t\t\tif (!mii_mgr_write(phy_mdio_addr, 0, esw_phy_mcr))','\n\t\t\tif (!mii_mgr_write(phy_mdio_addr, 0, esw_phy_mcr) && 0)','link-force-every-mdio-failure'),
   ('change_port_link_mode_uapi','\n\tif (!mii_mgr_write(phy_mdio_addr, 0, esw_phy_mcr))','\n\tif (!mii_mgr_write(phy_mdio_addr, 0, esw_phy_mcr) && 0)','link-force-every-mdio-failure'),
   ('change_port_link_mode_uapi',' && !g_link_apply_pending[port_id]','','link-old-request-recovery'),
   ('mtk_esw_ioctl','ioctl_result = change_led_mode(uint_value);','(void)change_led_mode(uint_value);','controls-ioctl-propagates-errors'),
   ('esw_status_link_port','if (ret)\n\t\t\treturn ret;','if (ret)\n\t\t\treturn 0;','status-direct-read-failure-preserves-output'),
   ('esw_status_speed_port_uapi','if (ret)\n\t\t\treturn ret;','if (ret)\n\t\t\treturn 0;','status-direct-read-failure-preserves-output'),
   ('esw_ioctl_init_post','g_storm_apply_pending = true;','g_storm_apply_pending = false;','init-success-invalidates-control-cache'),
   ('esw_ioctl_init_post','memset(g_link_apply_pending, 1, sizeof(g_link_apply_pending));','memset(g_link_apply_pending, 0, sizeof(g_link_apply_pending));','init-failure-invalidates-control-cache'))
  for i,(n,old,new,case)in enumerate(mutants):
   with self.subTest(function=n,case=case):
    body=h.function(self.texts[h.FUNCTION_SOURCES[n]],n);self.assertEqual(body.count(old),1);binary=self.build(self.generated.replace(body,body.replace(old,new)),'controls-mutant-'+str(i));r=self.run_case(binary,case);self.assertTrue(r.returncode!=0 or json.loads(r.stdout)!=h.EXPECTED_ROWS[case])
 def test_exact_source_binding_and_enabled_variant_contract(self):
  self.assertEqual(len(h.CASE_NAMES),68);self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS));self.assertEqual(len(h.BODY_ORDER),62)
  self.assertEqual(len(h.FIELDS),3);self.assertTrue(all(len(row)==3 for row in h.EXPECTED_ROWS.values()))
  for n,k in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[k],n)),1)
  self.assertIn('#define CONFIG_RAETH_ESW_IGMP_SNOOP_HW',self.texts['common']);self.assertIn('#define CONFIG_GE2_INTERNAL_GMAC_P5',self.texts['common'])
  self.assertIn('CONFIG_MULTIUSER=y',self.texts['config']);cap=h.function(self.texts['capability'],'capable');self.assertIn('ns_capable(&init_user_ns, cap)',cap)
  ioctl=h.function(self.texts['ioctl'],'mtk_esw_ioctl');self.assertLess(ioctl.index('capable(CAP_NET_ADMIN)'),ioctl.index('mutex_lock'));self.assertLess(ioctl.index('capable(CAP_NET_ADMIN)'),ioctl.index('copy_from_user'))
  self.assertTrue(h.MODEL_VARIANT['partial_hardware_writes_are_not_rolled_back']);self.assertTrue(h.MODEL_VARIANT['mutex_atomic_shims_are_not_kernel_concurrency'])
 def test_pinned_old_ioctl_reproduces_invalid_mib_copy_and_unprivileged_change(self):
  fixture=ROOT/'tests/fixtures/esw-error';manifest=json.loads((fixture/'manifest.json').read_text());raw=(fixture/'mtk_esw_ioctl.c').read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest['mtk_esw_ioctl']['sha256'])
  body=h.function(self.texts['ioctl'],'mtk_esw_ioctl')
  # The pinned ioctl predates the checked query API. Compatibility adapters
  # leave its full original bytes intact; these negative cases exercise MIB
  # publication and permission checks, not query return-value semantics.
  adapters=''
  for n,t in (('esw_status_link_port_uapi','u32'),('esw_status_link_ports','int'),('esw_status_speed_port_uapi','u32')):
   adapters+='static u32 old_ioctl_'+n+'('+t+' p){u32 value=0;(void)'+n+'(p,&value);return value;}\n'
  for n in ('esw_status_link_port_uapi','esw_status_link_ports','esw_status_speed_port_uapi'):adapters+='#define '+n+'(p) old_ioctl_'+n+'(p)\n'
  replacement=adapters+raw.decode()
  for n in ('esw_status_link_port_uapi','esw_status_link_ports','esw_status_speed_port_uapi'):replacement+='\n#undef '+n+'\n'
  binary=self.build(self.generated.replace(body,replacement),'old-ioctl')
  for case in ('mib-ioctl-invalid-no-copy','all-admin-commands-denied-no-effects'):
   r=self.run_case(binary,case);self.assertEqual(r.returncode,0,r.stderr);self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case])
 def test_effective_canary_authorization_vtcr_bitmap_and_publish_mutants_fail(self):
  mutants=(
   ('mtk_esw_ioctl','if (!ioctl_result && copy_to_user((esw_mib_counters_t __user *)arg','if (copy_to_user((esw_mib_counters_t __user *)arg','mib-ioctl-invalid-no-copy'),
   ('mtk_esw_ioctl','if (!capable(CAP_NET_ADMIN))','if (!capable(CAP_NET_ADMIN) && 0)','all-admin-commands-denied-no-effects'),
   ('mtk_esw_ioctl','if (copy_from_user(&uint_value, (int __user *)arg, sizeof(int)))','if (copy_from_user(&uint_value, (int __user *)arg, sizeof(int)) && 0)','all-setter-efault-no-hardware'),
   ('mtk_esw_ioctl','atomic_set(&g_port_link_changed, 1);','(void)g_port_link_changed;','link-change-efault-restored'),
   ('esw_status_mib_port_uapi','memset(&value, 0, sizeof(value));','memset(&value, 0x99, sizeof(value));','mib-success-zero-padding'),
   ('esw_wait_vtcr','return -ETIMEDOUT;','return 0;','vtcr-busy-timeout'),
   ('esw_wait_vtcr','ret = esw_reg_read(REG_ESW_VLAN_VTCR, &reg_vtcr);\n\t\tif (ret)\n\t\t\treturn ret;','ret = esw_reg_read(REG_ESW_VLAN_VTCR, &reg_vtcr);\n\t\tif (ret)\n\t\t\treturn 0;','vtcr-read-failure'),
   ('esw_vlan_set','set_bit(cvid, g_vlan_pending);','(void)g_vlan_pending;','vlan-uncertain-read-cleanup'),
   ('esw_vlan_reset_table',' && !test_bit(i, g_vlan_pending)','','vlan-uncertain-read-cleanup'),
   ('esw_vlan_set','ret = esw_wait_vtcr();\n\tif (ret)\n\t\treturn ret;','ret = esw_wait_vtcr();\n\tif (ret && 0)\n\t\treturn ret;','vlan-prior-busy-no-overwrite'),
   ('esw_vlan_set','ret = esw_reg_write(REG_ESW_VLAN_VAWD1, reg_val);','set_bit(cvid, g_vlan_pool);\n\tret = esw_reg_write(REG_ESW_VLAN_VAWD1, reg_val);','vlan-set-every-write-failure'),
   ('esw_vlan_reset_table','ret = esw_write_vtcr(2, i);','clear_bit(i, g_vlan_pool);\n\t\tret = esw_write_vtcr(2, i);','vlan-delete-write-failure'),
   ('esw_vlan_apply_rules','*new_pvid = untg_vid;','*new_pvid = untg_vid;\n\tg_vlan_pvid_wan_untagged = untg_vid;','apply-success-stages-only'),
   ('change_bridge_mode','g_bridge_apply_pending = true;','g_bridge_apply_pending = false;','bridge-every-mdio-failure-retryable'),
   ('esw_ioctl_init_post','atomic_set(&g_switch_inited, 0);','(void)g_switch_inited;','init-every-mdio-failure-no-ready'))
  for i,(n,old,new,case)in enumerate(mutants):
   with self.subTest(function=n,case=case):
    body=h.function(self.texts[h.FUNCTION_SOURCES[n]],n);self.assertEqual(body.count(old),1);binary=self.build(self.generated.replace(body,body.replace(old,new)),'mutant-'+str(i));r=self.run_case(binary,case)
    self.assertTrue(r.returncode!=0 or json.loads(r.stdout)!=h.EXPECTED_ROWS[case])
 def test_unknown_case_and_missing_or_ambiguous_sources_fail_closed(self):
  for binary in self.binaries:self.assertEqual(self.run_case(binary,'unreviewed').returncode,91)
  with self.assertRaises(ValueError):h.generate_source({})
  bad=dict(self.texts);bad['esw']+='\n'+h.function(self.texts['esw'],'esw_write_vtcr')
  with self.assertRaises(ValueError):h.generate_source(bad)
  bad=dict(self.texts);bad['config']=bad['config'].replace('CONFIG_MULTIUSER=y','CONFIG_MULTIUSER=n')
  with self.assertRaises(ValueError):h.generate_source(bad)
if __name__=='__main__':unittest.main()
