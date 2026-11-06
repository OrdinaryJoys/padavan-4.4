"""HW command OOM, response ownership and selected worker retirement schedules."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import hwcmd_owner_harness as h
ROOT=Path(__file__).resolve().parents[1]


class HwcmdOwnerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='k2p-hwcmd-owner-')
  cls.directory=Path(cls.temp.name)
  cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
  cls.generated=h.generate_source(cls.texts)
  cls.source=cls.directory/'hwcmd.c';cls.source.write_text(cls.generated)
  gnu=shutil.which('gcc-16')or('/opt/homebrew/bin/gcc-16'if Path('/opt/homebrew/bin/gcc-16').is_file()else shutil.which('gcc'))
  if not gnu:raise AssertionError('GNU GCC required')
  version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
  if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
  cls.binaries=[]
  cls.flags=['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror',
   '-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']
  for label,compiler in(('clang',shutil.which('clang')),('gcc',gnu)):
   if not compiler:raise AssertionError('Required compiler absent: '+label)
   binary=cls.directory/label
   result=subprocess.run([compiler,*cls.flags,*(['-fsanitize=address,undefined']if label=='clang'else[]),
    str(cls.source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
   if result.returncode:raise AssertionError(result.stderr)
   cls.binaries.append(binary)

 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()

 def cases(self,names):
  for binary in self.binaries:
   for name in names:
    with self.subTest(compiler=binary.name,case=name):
     env=os.environ.copy();env['ASAN_OPTIONS']=env.get('ASAN_OPTIONS','')+':detect_stack_use_after_return=1'
     result=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10,env=env)
     self.assertEqual(result.returncode,0,result.stderr)
     self.assertEqual(json.loads(result.stdout),h.EXPECTED_ROWS[name])

 def test_each_allocation_failure_and_rejected_publish_retires_only_local_command(self):
  self.cases(h.CASE_NAMES[:7])

 def test_sync_async_success_and_command_private_response_lifetime(self):
  self.cases(('normal-sync','normal-async','response-complete','response-timeout-queued','normal-callback'))

 def test_invalid_borrowed_buffers_and_oversized_temperature_response_are_rejected(self):
  self.cases(('null-input','null-response','async-response','temperature-too-large','temperature-null','temperature-api-failure'))

 def test_late_start_flags_and_selected_worker_exit_race_preserve_one_consumer(self):
  self.cases(('exit-before-start','flag-late-stop','flag-after-stop','active-worker-vs-exit',
   'exit-retirement-failure','repeat-exit','command-stop-before-handler',
   'exit-without-threadfn','response-exit-without-threadfn'))

 def test_handler_failure_absence_or_exit_completion_cannot_publish_bogus_success(self):
  self.cases(('response-handler-failure','response-no-handler','response-exit-before-start'))

 def test_independent_source_mutants_are_detected(self):
  mutations=(
   ('HwCtrlEnqueueCmd','os_kref_init(&cmdqelmt->refcnt);','if (!HwCtrlTxd.InformationBufferLength) os_kref_init(&cmdqelmt->refcnt);','payload-oom-sync'),
   ('HwCtrlEnqueueCmd','status = cmdqelmt->result;','status = NDIS_STATUS_SUCCESS;','response-handler-failure'),
   ('HwCtrlSetFlag','if (!(pHwCtrl->HwCtrlQ.CmdQState & RTMP_TASK_CAN_DO_INSERT))','if (FALSE)','flag-late-stop'),
   ('HwCtrlThread','if (pHwCtrl->HwCtrlQ.CmdQState == RTMP_TASK_STAT_INITED)','if (TRUE)','exit-before-start'),
   ('HwCtrlExit','NdisAcquireSpinLock(&pHwCtrl->HwCtrlQLock);\n\tpHwCtrl->HwCtrlQ.CmdQState = RTMP_TASK_STAT_STOPED;\n\tNdisReleaseSpinLock(&pHwCtrl->HwCtrlQLock);','HwCtrlCmdHandler(pAd);','active-worker-vs-exit'),
   ('HwCtrlGetTemperature','CMDQelmt->RspBufferLen != sizeof(temperature)','FALSE','temperature-too-large'),
   ('HwCtrlExit','HwCtrlCmdHandler(pAd);','/* missing post-join drain */','exit-without-threadfn'))
  for index,(name,old,new,case)in enumerate(mutations):
   with self.subTest(function=name,case=case):
    body=h.function(self.texts[h.FUNCTION_SOURCES[name]],name)
    self.assertEqual(body.count(old),1)
    source=self.directory/('mutant-'+str(index)+'.c')
    source.write_text(self.generated.replace(body,body.replace(old,new)))
    binary=source.with_suffix('')
    result=subprocess.run([shutil.which('clang'),*self.flags,'-fsanitize=address,undefined',
     str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
    self.assertEqual(result.returncode,0,result.stderr)
    try:result=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=3)
    except subprocess.TimeoutExpired:continue
    self.assertTrue(result.returncode!=0 or json.loads(result.stdout)!=h.EXPECTED_ROWS[case])

 def test_whole_function_declaration_and_case_contract_is_complete(self):
  self.assertEqual(len(h.CASE_NAMES),30)
  self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
  self.assertEqual(len(h.function_manifest(self.texts)),9)
  self.assertEqual(len(h.source_only_function_manifest(self.texts)),8)
  for name,key in h.FUNCTION_SOURCES.items():
   self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
  self.assertEqual(len(h.source_declarations(self.texts)),13)
  self.assertIn('if (!test_bit(KTHREAD_SHOULD_STOP, &self.flags)) {',self.texts['kernel_task'])
  self.assertIn('ret = threadfn(data);',self.texts['kernel_task'])
  with self.assertRaises(ValueError):h.generate_source({})
  with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')

 def test_terminal_callers_check_quarantine_before_the_next_resource_release(self):
  for name,next_release in(('rtmp_sys_task_exit','RtmpMgmtTaskExit(pAd);'),
   ('RTMPDrvClose','NICRestartFirmware(pAd)'),('rtmp_sys_init','if (mgmt)')):
   body=h.function(self.texts['init'],name)
   # rtmp_sys_init's only HwCtrlExit belongs to the fail-stage unwind.
   index=body.index('HwCtrlExit(pAd);');tail=body[index:]
   self.assertLess(tail.index('if (RtmpDmaQuarantined(pAd))'),tail.index(next_release))


if __name__=='__main__':unittest.main()
