"""Enabled MAC-clear failures through actual bridge, init and ioctl bodies."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import esw_error_harness as h
ROOT=Path(__file__).resolve().parents[1]
FLAGS=['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']

class EswErrorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='k2p-esw-error-');cls.directory=Path(cls.temp.name)
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
 def build(cls,text,name,compiler=None):
  source=cls.directory/(name+'.c');source.write_text(text);binary=source.with_suffix('')
  compiler=compiler or shutil.which('clang');flags=FLAGS+(['-fsanitize=address,undefined']if'clang'in compiler else[])
  r=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
  if r.returncode:raise AssertionError(r.stderr)
  return binary
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def run_case(self,binary,name):
  env={**os.environ,'ASAN_OPTIONS':os.environ.get('ASAN_OPTIONS','')+':detect_stack_use_after_return=1'}
  return subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10,env=env)
 def cases(self,names):
  for b in self.binaries:
   for name in names:
    with self.subTest(compiler=b.name,case=name):
     r=self.run_case(b,name);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),h.EXPECTED_ROWS[name])
 def test_actual_clear_command_and_every_failure_stage_have_distinct_errno(self):self.cases(h.CASE_NAMES[:8])
 def test_bridge_failure_restores_software_comparisons_and_old_or_same_request_retries(self):
  self.cases(('bridge-ok','bridge-write-fail','bridge-read-fail','bridge-busy-timeout','bridge-retry','bridge-old-state-after-fail','bridge-noop','bridge-pending-init','disable-wan-ok','disable-wan-write-fail'))
 def test_init_failure_does_not_publish_ready_or_keep_a_prior_ready_epoch(self):
  self.cases(('init-ok','init-write-fail','init-read-fail','init-busy-timeout','init-prior-ready-fail','init-retry'))
 def test_actual_ioctl_returns_hardware_and_user_copy_failures(self):
  self.cases(('ioctl-clear-ok','ioctl-clear-write-fail','ioctl-clear-read-fail','ioctl-clear-busy-timeout','bridge-invalid-mode','bridge-invalid-isolation','bridge-uaccess-fail','unknown-ioctl'))
 def test_source_bound_contract_names_inert_vlan_and_kernel_concurrency(self):
  self.assertEqual((len(h.FUNCTION_SOURCES),len(h.SOURCE_ONLY_FUNCTION_SOURCES),len(h.CASE_NAMES),len(h.SOURCE_DECLARATIONS)),(7,5,32,40))
  self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS));self.assertEqual(set(h.BODY_ORDER),set(h.FUNCTION_SOURCES));self.assertTrue(all(len(x)==len(h.FIELDS)==24 for x in h.EXPECTED_ROWS.values()))
  for n,k in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[k],n)),1)
  self.assertEqual(len(h.source_declarations(self.texts)),40);self.assertRegex(self.texts['config'],r'(?m)^CONFIG_RAETH_ESW_CONTROL=y$')
  self.assertTrue(h.MODEL_VARIANT['VLAN_programming_is_inert_side_effect_seam_not_real_algorithm']);self.assertTrue(h.MODEL_VARIANT['atomic_and_mutex_shims_are_sequential_not_kernel_scheduling']);self.assertFalse(h.MODEL_VARIANT['wire_layout_is_actual_kernel_ABI'])
  apply=h.function(self.texts['esw'],'esw_vlan_apply_rules');self.assertNotIn('g_vlan_rule[i] = g_vlan_rule_user[i];',apply);self.assertIn('*new_pvid = untg_vid;',apply);publish=h.function(self.texts['esw'],'esw_vlan_bridge_isolate');self.assertIn('g_vlan_rule[i] = g_vlan_rule_user[i];',publish);self.assertIn('g_vlan_pvid_wan_untagged = new_pvid;',publish)
  opening=h.function(self.texts['raeth'],'ei_open');self.assertRegex(opening,r'err = esw_ioctl_init_post\(\);\s*if \(err\)\s*goto fail_dma;')
 def test_pinned_old_whole_functions_reproduce_false_success(self):
  fixture=ROOT/'tests/fixtures/esw-error';manifest=json.loads((fixture/'manifest.json').read_text())
  for n,case in (('mt7530_gsw_wait_wt_mac','clear-read-fail'),('mt7530_gsw_mac_table_clear','clear-write-fail'),('change_bridge_mode','bridge-write-fail'),('esw_ioctl_init_post','init-write-fail'),('mtk_esw_ioctl','ioctl-clear-write-fail')):
   with self.subTest(function=n,case=case):
    raw=(fixture/(n+'.c')).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest[n]['sha256'])
    body=h.function(self.texts[h.FUNCTION_SOURCES[n]],n);code=self.generated.replace(body,raw.decode())
    if n=='esw_ioctl_init_post':
     # Serialize the exact older body externally so the failure is its ignored
     # status/readiness publication rather than its absent internal mutex.
     code=code.replace('ret=esw_ioctl_init_post();','mutex_lock(&esw_access_mutex);ret=esw_ioctl_init_post();mutex_unlock(&esw_access_mutex);')
    r=self.run_case(self.build(code,'old-'+n),case);self.assertEqual(r.returncode,0,r.stderr);self.assertNotEqual(json.loads(r.stdout),h.EXPECTED_ROWS[case]);self.assertEqual(json.loads(r.stdout)[0],0)
 def test_effective_error_ownership_retry_and_uaccess_mutants_must_compile_and_fail(self):
  mutants=(
   ('mt7530_gsw_wait_wt_mac','if (!mii_mgr_read(0x1f, 0x80, &atc_val))','if (mii_mgr_read(0x1f, 0x80, &atc_val) && 0)','clear-read-fail'),
   ('mt7530_gsw_mac_table_clear','if (!mii_mgr_write(0x1f, 0x80, atc_val))','if (mii_mgr_write(0x1f, 0x80, atc_val) && 0)','clear-write-fail'),
   ('mt7530_gsw_wait_wt_mac','return -ETIMEDOUT;','return 0;','clear-busy-timeout'),
   ('esw_mac_table_clear','if (ret)','if (0)','wrapper-write-fail'),
   ('esw_vlan_bridge_isolate','g_bridge_apply_pending = true;\n\t\treturn ret;','g_bridge_apply_pending = true;\n\t\treturn 0;','bridge-write-fail'),
   ('change_bridge_mode','if (ret) {','if (0) {','bridge-write-fail'),
   ('change_bridge_mode',' || g_bridge_apply_pending','','bridge-old-state-after-fail'),
   ('mtk_esw_ioctl','ioctl_result = esw_mac_table_clear();','(void)esw_mac_table_clear();','ioctl-clear-write-fail'),
   ('esw_ioctl_init_post','if (ret)\n\t\tgoto out;\n\n#if','if (0)\n\t\tgoto out;\n\n#if','init-write-fail'),
   ('esw_ioctl_init_post','atomic_set(&g_switch_inited, 0);','(void)g_switch_inited;','init-prior-ready-fail'),
   ('mtk_esw_ioctl','if (copy_from_user(&uint_value, (int __user *)arg, sizeof(int)))','if (copy_from_user(&uint_value, (int __user *)arg, sizeof(int)) && 0)','bridge-uaccess-fail'))
  for i,(n,old,new,case)in enumerate(mutants):
   with self.subTest(function=n,case=case):
    body=h.function(self.texts[h.FUNCTION_SOURCES[n]],n);self.assertEqual(body.count(old),1)
    binary=self.build(self.generated.replace(body,body.replace(old,new)),'mutant-'+str(i));r=self.run_case(binary,case)
    self.assertTrue(r.returncode!=0 or json.loads(r.stdout)!=h.EXPECTED_ROWS[case])
 def test_unknown_case_missing_source_and_duplicate_whole_function_are_rejected(self):
  for binary in self.binaries:self.assertEqual(self.run_case(binary,'unreviewed').returncode,91)
  with self.assertRaises(ValueError):h.generate_source({})
  bad=dict(self.texts);bad['esw']+='\n'+h.function(self.texts['esw'],'esw_mac_table_clear')
  with self.assertRaises(ValueError):h.generate_source(bad)
  bad=dict(self.texts);bad['esw']=bad['esw'].replace('static bool g_bridge_apply_pending;','static bool replaced_pending;')
  with self.assertRaises(ValueError):h.generate_source(bad)

if __name__=='__main__':unittest.main()
