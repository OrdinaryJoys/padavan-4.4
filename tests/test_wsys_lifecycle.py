"""Wsys result propagation, reserved-stage cleanup and copied RA payload regressions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wsys_lifecycle_harness as h
ROOT=Path(__file__).resolve().parents[1]


class WsysLifecycleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='k2p-wsys-lifecycle-')
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
   '-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']
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

 def test_composed_status_stage_ownership_and_payload_matrix(self):
  self.cases(h.CASE_NAMES)

 def test_whole_body_and_literal_case_contract(self):
  self.assertEqual(len(h.FUNCTION_SOURCES),72)
  self.assertEqual(len(h.CASE_NAMES),171)
  self.assertEqual(set(h.BODY_ORDER),set(h.FUNCTION_SOURCES))
  self.assertEqual(set(h.EXPECTED_ROWS),set(h.CASE_NAMES))
  self.assertEqual(len(h.source_declarations(self.texts)),14)
  self.assertEqual(len(h.source_only_function_manifest(self.texts)),22)
  for name,key in h.FUNCTION_SOURCES.items():
   self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
  with self.assertRaises(ValueError):h.generate_source({})
  with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')

 def test_raw_cleanup_parents_stop_before_release_on_failed_or_uncertain_wsys(self):
  body=h.function(self.texts['entry'],'MacTableDeleteEntry')
  self.assertLess(body.index('if (!mac_entry_disconn_act(pAd, pEntry))'),body.index('NdisAcquireSpinLock(&pAd->MacTabLock);'))
  tail=body[body.index('if (!mac_entry_disconn_act(pAd, pEntry))'):]
  self.assertLess(tail.index('return FALSE;'),tail.index('TRTableResetEntry(pAd, wcid);'))
  for name,key,release in(('TRTableResetEntry','entry','NdisFreeSpinLock'),
   ('wdev_deinit','wdev','wlan_operate_exit(wdev);'),
   ('ApCli_Remove','apcli','RtmpOSNetDevDetach'),('WDS_Remove','wds','RtmpOSNetDevDetach')):
   body=h.function(self.texts[key],name)
   self.assertLess(body.index('RtmpDmaQuarantined(pAd)'),body.index(release))
  for name,call in(('ap_inf_open','if (!APStartUpForMbss('),('ap_inf_close','if (wdev_do_linkdown(wdev) != TRUE)'),('APStartUpByBss','if (wdev_do_open(wdev) != TRUE)')):
   self.assertIn(call,h.function(self.texts['ap'],name))
  self.assertIn('BOOLEAN APStartUpForMbss(',self.texts['ap_header'])
  self.assertNotIn('os_alloc_mem',h.function(self.texts['sys'],'WifiSysUpdateRa'))
  self.assertNotIn('os_alloc_mem',h.function(self.texts['sys'],'wifi_sys_conn_act'))
  self.assertNotIn('VOID *priv;',self.texts['sys_header'].split('struct WIFI_SYS_CTRL {',1)[1].split('};',1)[0])

 def test_independent_source_mutants_break_observed_stage_contracts(self):
  mutations=(
   ('HwCtrlWifiSysOpen','return NDIS_STATUS_FAILURE;','return FALSE;','handler-0-missing'),
   ('AsicDevInfoUpdate','return NDIS_STATUS_FAILURE;','return FALSE;','v1-open-missing'),
   ('wifi_sys_queue_work','return NDIS_STATUS_FAILURE;','return NDIS_STATUS_SUCCESS;','v1-open-irq'),
   ('hw_ctrl_flow_v1_open','if (status != NDIS_STATUS_SUCCESS || RtmpDmaQuarantined(ad))','if (FALSE)','v1-open-fwfail'),
   ('hw_ctrl_flow_v2_link_up','if (status != NDIS_STATUS_SUCCESS || RtmpDmaQuarantined(ad))','if (FALSE)','v2-linkup-fwfail'),
   ('fill_bssinfo_active','WDEV_BSS_STATE(wdev) = BSS_INITED;','WDEV_BSS_STATE(wdev) = BSS_READY;','v1-linkup-fwfail'),
   ('wifi_sys_conn_act','return FALSE;','return TRUE;','v1-conn-reject'),
   ('mac_entry_disconn_act','return FALSE;','return TRUE;','cleanup-disconn-failure'),
   ('WifiSysUpdateRa','os_move_mem(&wsys.RaParam, prParam, sizeof(wsys.RaParam));','wsys.RaParam.u4Field = 0;','v1-ra-ok'),
   ('wdev_deinit','if (RtmpDmaQuarantined(pAd))','if (FALSE)','cleanup-deinit-quarantined'),
   ('wifi_sys_open','if (wdev_attr_update(wdev->sys_handle, wdev) != TRUE)','if (FALSE)','v1-open-attrfail'),
   ('wifi_sys_abort_open','RtmpDmaQuarantine(ad);','/* missing containment */','rollback-second'),
   ('CmdExtDevInfoUpdateRsp','msg->cmd_return_status = EventExtCmdResult->u4Status;','/* lost status */','response-dev-error'),
   ('CmdExtBssInfoUpdateRsp','msg->cmd_return_status = EventExtCmdResult->u4Status;','/* lost status */','response-bss-error'),
   ('CmdExtStaRecUpdateRsp','if (!Data || Len < sizeof(EVENT_STAREC_UPDATE_T))','if (FALSE)','response-sta-short'))
  for index,(name,old,new,case)in enumerate(mutations):
   with self.subTest(function=name,case=case):
    body=h.function(self.texts[h.FUNCTION_SOURCES[name]],name)
    self.assertIn(old,body)
    source=self.directory/('wsys-mutant-'+str(index)+'.c')
    source.write_text(self.generated.replace(body,body.replace(old,new)))
    binary=source.with_suffix('')
    build=subprocess.run([shutil.which('clang'),*self.flags,'-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
    self.assertEqual(build.returncode,0,build.stderr)
    result=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10)
    self.assertTrue(result.returncode!=0 or json.loads(result.stdout)!=h.EXPECTED_ROWS[case])


if __name__=='__main__':unittest.main()
