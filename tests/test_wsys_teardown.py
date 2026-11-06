"""Composed last-VIF stop/idle, terminal retirement and first-init rollback proof.

Native models use inert hardware/queue seams; real locked publication schedules
are separately exercised by test_hwcmd_owner. This suite never accesses hardware.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wsys_teardown_harness as h
ROOT = Path(__file__).resolve().parents[1]
BASELINE = '5f7eca673b3791bf2f3f05c00ae03abc058dcdff'
BASELINE_HANDLER_SHA256 = {
 'HwCtrlWifiSysClose': '1cd6a083046867ff0cc55f5b5a9e2c8092f958f2874568d082da78e094a419d3',
 'HwCtrlWifiSysLinkDown': 'e9082c3e8aff462986971323b5ea812ab5d5564a93dc2987b49ad783c56d5057',
 'HwCtrlWifiSysPeerLinkDown': 'f5a0fa864028ca99c35f40ff5ac5c4ff45065a4e9dd2fa2f232ecd2afa7056a4',
}


class WsysTeardownTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp = tempfile.TemporaryDirectory(prefix='k2p-wsys-terminal-')
  cls.directory = Path(cls.temp.name)
  cls.texts = {k:(ROOT/v).read_text() for k,v in h.SOURCE_PATHS.items()}
  cls.generated = h.generate_source(cls.texts)
  cls.flags = ['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror',
   '-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']
  gnu = shutil.which('gcc-16') or ('/opt/homebrew/bin/gcc-16' if Path('/opt/homebrew/bin/gcc-16').is_file() else shutil.which('gcc'))
  if not gnu: raise AssertionError('GNU GCC required')
  version = subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
  if 'Free Software Foundation' not in version or 'clang' in version.lower(): raise AssertionError('True GNU GCC required')
  cls.binaries = []
  for label,compiler in (('clang',shutil.which('clang')),('gcc',gnu)):
   if not compiler: raise AssertionError('Required compiler absent: '+label)
   source = cls.directory/(label+'.c'); source.write_text(cls.generated)
   binary = source.with_suffix('')
   result = subprocess.run([compiler,*cls.flags,*(['-fsanitize=address,undefined'] if label=='clang' else []),
    str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
   if result.returncode: raise AssertionError(result.stderr)
   cls.binaries.append(binary)

 @classmethod
 def tearDownClass(cls): cls.temp.cleanup()

 def run_case(self,binary,name):
  env = os.environ.copy(); env['ASAN_OPTIONS'] = env.get('ASAN_OPTIONS','')+':detect_stack_use_after_return=1'
  result = subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10,env=env)
  self.assertEqual(result.returncode,0,result.stderr)
  return json.loads(result.stdout)

 def cases(self,names):
  for binary in self.binaries:
   for name in names:
    with self.subTest(compiler=binary.name,case=name):
     self.assertEqual(self.run_case(binary,name),h.EXPECTED_ROWS[name])

 def mutant(self,label,changes,case):
  text = self.generated
  for name,old,new in changes:
   body = h.function(self.texts[h.FUNCTION_SOURCES[name]],name)
   self.assertEqual(body.count(old),1,(name,old))
   text = text.replace(body,body.replace(old,new))
  return self.rejected_source(label,text,case)

 def rejected_source(self,label,text,case):
  source = self.directory/(label+'.c'); source.write_text(text)
  binary = source.with_suffix('')
  built = subprocess.run([shutil.which('clang'),*self.flags,'-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
  self.assertEqual(built.returncode,0,built.stderr)
  result = subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10)
  self.assertTrue(result.returncode!=0 or json.loads(result.stdout)!=h.EXPECTED_ROWS[case],label)

 def test_last_close_retires_host_owners_only_after_actual_idle_gate(self):
  self.cases(('last-close','last-close-cached-idle','partial-inited-close'))

 def test_busy_failed_join_and_quarantine_preserve_live_owner_graph(self):
  self.cases(('last-close-busy','last-close-tm-fail','last-close-quarantined'))

 def test_terminal_fifo_failure_quarantines_before_outer_release(self):
  self.cases(('last-close-queue-reject',))

 def test_nonlast_close_preserves_normal_ack_and_hardware_path(self):
  self.cases(('nonlast-close',))

 def test_first_init_abort_keeps_ordinary_firmware_rollback_and_failures(self):
  self.cases(('first-abort-success','first-abort-fw1','first-abort-fw2','first-abort-fw3','first-abort-queue-reject'))

 def test_terminal_payload_and_stop_idle_admission(self):
  self.cases(('direct-close-not-idle','helper-not-idle','helper-active-payload','helper-bss-payload',
   'helper-sta-payload','helper-unknown','helper-not-stopping','terminal-quarantined'))

 def test_terminal_peer_and_edca_retirement_have_no_mcu_side_effect(self):
  self.cases(('peer-retire','edca-normal','edca-terminal'))

 def test_late_nonterminal_producers_never_borrow_payload(self):
  self.cases(('late-open','late-linkup','late-peerup','late-peerupdate','late-async-ra'))

 def test_whole_bodies_exact_cases_and_explicit_source_only_boundaries(self):
  self.assertEqual(len(h.CASE_NAMES),29)
  self.assertEqual(len(h.FUNCTION_SOURCES),81)
  self.assertEqual(len(h.SOURCE_PATHS),30)
  self.assertEqual(set(h.BODY_ORDER),set(h.FUNCTION_SOURCES))
  self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
  self.assertEqual(len(h.source_declarations(self.texts)),14)
  self.assertEqual(len(h.source_only_function_manifest(self.texts)),30)
  for name,key in h.FUNCTION_SOURCES.items(): self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
  with self.assertRaises(ValueError): h.generate_source({})
  with self.assertRaises(ValueError): h.generate_source(self.texts,'legacy')
  andes = h.function(self.texts['core'],'AndesSendCmdMsg')
  self.assertIn('RtmpDmaStopping(ad)',andes)
  queue = h.function(self.texts['basic'],'HwCtrlEnqueueCmd')
  self.assertLess(queue.index('NdisAcquireSpinLock(&pHwCtrl->HwCtrlQLock);'),queue.index('if (HwCtrlTxd.CmdType == HWCMD_TYPE_WIFISYS && RtmpDmaStopping(pAd)'))
  self.assertLess(queue.index('if (HwCtrlTxd.CmdType == HWCMD_TYPE_WIFISYS && RtmpDmaStopping(pAd)'),queue.index('os_kref_get(&cmdqelmt->refcnt)'))

 def test_immutable_pre_followup_handlers_reproduce_last_close_regression(self):
  text = self.generated
  for name,digest in BASELINE_HANDLER_SHA256.items():
   fixture = (ROOT/'tests/fixtures/wsys-terminal'/(name+'.c')).read_text()
   self.assertEqual(hashlib.sha256(fixture.encode()).hexdigest(),digest,BASELINE+':'+name)
   self.assertEqual(h.function(fixture,name)+'\n',fixture)
   text = text.replace(h.function(self.texts['handler'],name),fixture.rstrip())
  self.rejected_source('baseline-terminal-handlers',text,'last-close')

 def test_removing_terminal_state_validation_breaks_observations(self):
  self.mutant('missing-idle-check',(('wifi_sys_retire',
   'if (!RtmpDmaStopping(ad) || !RtmpDmaResourcesMayRelease(ad))','if (FALSE)'),),'helper-not-idle')

 def test_reintroducing_hardware_work_or_omitting_containment_is_detected(self):
  changes = (
   ('edca-hw','WcReleaseEdca','if (!RtmpDmaStopping(pAd))','if (TRUE)','edca-terminal'),
   ('igmp-hw','wifi_sys_update_devinfo','if (!RtmpDmaStopping(ad))','if (TRUE)','last-close'),
   ('lost-quarantine','virtual_if_down_handler','if (RtmpDmaStopping(pAd))','if (FALSE)','last-close-queue-reject'),
  )
  for label,name,old,new,case in changes:
   with self.subTest(mutant=label): self.mutant(label,((name,old,new),),case)

 def test_missing_early_nonterminal_guards_is_observable_even_with_handler_guard(self):
  self.mutant('late-sync-borrow',(('wifi_sys_queue_work',
   'if (RtmpDmaStopping(ad) &&','if (FALSE &&'),),'late-open')
  self.mutant('late-async-borrow',(('HW_WIFISYS_RA_UPDATE',
   'if (!wsys || !wsys->wdev || RtmpDmaStopping(pAd))','if (!wsys || !wsys->wdev)'),),'late-async-ra')


if __name__=='__main__': unittest.main()
