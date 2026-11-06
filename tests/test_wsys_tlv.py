"""Atomic station TLV construction using real builder/retirement bodies."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wsys_tlv_harness as h
ROOT=Path(__file__).resolve().parents[1]
FLAGS=['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']

class WsysTlvTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='k2p-wsys-tlv-');cls.directory=Path(cls.temp.name)
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
 def test_allocation_failure_and_invalid_selected_owner_never_send_partial(self):
  self.cases(('normal','bcmc','cmd-oom','wtbl-oom','wtbl-status-fail','missing-entry','missing-wdev','null-handler','unknown-feature','ra-reject'))
 def test_actual_selected_builder_bodies_compose_one_complete_message(self):
  self.cases(('ra-ok','ra-update-ok','bf-ok','amsdu-ok','ht-ok','vht-ok','ap-ps-ok','key-ok','all-selected'))
 def test_firmware_retry_cannot_relabel_permanent_builder_failure(self):
  self.cases(('fw-retry-ok','fw-fail','resync-fail','retry-cmd-oom','retry-wtbl-oom','resync-ok','resync-null','resync-oom','resync-builder-fail'))
 def test_ba_input_validation_precedes_allocation_and_consumes_one_sender(self):
  self.cases(('ba-ori','ba-rcv','ba-invalid','ba-null','ba-oom','ba-ori-disable','ba-rcv-disable','forcefree-no-retry','forcefree-distinct-retry'))
 def test_whole_bodies_and_source_only_contract_have_no_hardware_claim(self):
  self.assertEqual((len(h.CASE_NAMES),len(h.FUNCTION_SOURCES),len(h.SOURCE_ONLY_FUNCTION_SOURCES)),(37,19,2))
  self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS));self.assertEqual(set(h.BODY_ORDER),set(h.FUNCTION_SOURCES))
  self.assertEqual(len(h.source_declarations(self.texts)),5)
  for n,k in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[k],n)),1)
  self.assertIn(h.table(self.texts['fw']),self.generated)
  resync=h.function(self.texts['fw'],'CmdExtStaRecUpdate_ReSyncDelete');self.assertIn('StaRecCfgForDel.u4EnableFeature = STA_REC_BASIC_STA_RECORD_FEATURE;',resync)
  # Identity constraint only: current basic builder does not consume this feature member.
  decision=h.function(self.texts['sys'],'starec_feature_decision');self.assertIn('features |= STA_REC_WTBL_FEATURE;',decision)
  self.assertTrue(h.MODEL_VARIANT['synthetic_wire_layout']);self.assertFalse(h.MODEL_VARIANT['wire_layout_is_actual_kernel_ABI'])
  self.assertTrue(h.MODEL_VARIANT['prior_eleven_observations_preserved_as_prefix']);self.assertTrue(h.MODEL_VARIANT['serialized_logical_header_TLV_order_BA_fields_observed'])
  self.assertTrue(all(len(row)==12 and len(row[-1])==row[6] for row in h.EXPECTED_ROWS.values()))
 def test_pinned_previous_code_reproduces_oom_partial_success_and_leak(self):
  fixture=ROOT/'tests/fixtures/wsys-tlv';manifest=json.loads((fixture/'manifest.json').read_text())
  for n,case in (('StaRecUpdateWtbl','wtbl-oom'),('CmdExtStaRecUpdate','wtbl-oom'),('CmdExtStaRecUpdate_ReSyncDelete','resync-builder-fail'),('CmdExtStaRecBaUpdate','ba-invalid')):
   with self.subTest(old_function=n,case=case):
    raw=(fixture/(n+'.c')).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest[n]['sha256'])
    current=h.function(self.texts['fw'],n);binary=self.build(self.generated.replace(current,raw.decode()),'old-'+n)
    r=self.run_case(binary,case);self.assertTrue(r.returncode!=0 or json.loads(r.stdout)!=h.EXPECTED_ROWS[case])
 def test_independent_mutants_break_atomicity_and_real_force_free_ownership(self):
  mutations=(
   ('StaRecUpdateWtbl','if (Status != NDIS_STATUS_SUCCESS || pStarec_wtbl == NULL)','if (FALSE)','wtbl-oom'),
   ('StaRecUpdateWtbl','pEntry == NULL || pEntry->wdev == NULL','pEntry == NULL','missing-wdev'),
   ('CmdExtStaRecUpdate','if (Ret != NDIS_STATUS_SUCCESS)','if (FALSE)','wtbl-oom'),
   ('CmdExtStaRecUpdate','AndesForceFreeCmdMsg(msg);','(void)msg;','wtbl-oom'),
   ('CmdExtStaRecUpdate','if (StaRecCfg.u4EnableFeature & ~selected)','if (FALSE)','unknown-feature'),
   ('CmdExtStaRecUpdate','if (!StaRecHandle[i].StaRecTagHandler)','if (FALSE)','null-handler'),
   ('CmdExtStaRecUpdate_ReSyncDelete','if (Ret != NDIS_STATUS_SUCCESS)','if (FALSE)','resync-builder-fail'),
   ('CmdExtStaRecBaUpdate','CmdStaRecBa.ucBaDirection = StaRecBaCfg.baDirection;','CmdStaRecBa.ucBaDirection = 0;','ba-ori'),
   ('CmdExtStaRecBaUpdate','CmdStaRecBa.ucBaEenable = StaRecBaCfg.BaEnable;','CmdStaRecBa.ucBaEenable = 0;','ba-ori'),
   ('CmdExtStaRecBaUpdate','cpu2le16(pBAEntry->Sequence)','cpu2le16(pBAEntry->Sequence ^ 1U)','ba-ori'),
   ('CmdExtStaRecBaUpdate','cpu2le16(pBAEntry->LastIndSeq)','cpu2le16(pBAEntry->LastIndSeq ^ 1U)','ba-rcv'),
   ('CmdExtStaRecBaUpdate','CmdStaRecBa.ucTid = StaRecBaCfg.tid;','CmdStaRecBa.ucTid = 0;','ba-rcv'),
   ('CmdExtStaRecBaUpdate','CmdStaRecUpdate.ucWlanIdx = StaRecBaCfg.WlanIdx;','CmdStaRecUpdate.ucWlanIdx = 0;','ba-ori'),
   ('CmdExtStaRecBaUpdate','CmdStaRecBa.ucAmsduCap = pBAEntry->amsdu_cap;','CmdStaRecBa.ucAmsduCap = 0;','ba-ori'),
   ('CmdExtStaRecBaUpdate','CmdStaRecBa.u2BaStartSeq = cpu2le16(pBAEntry->Sequence);\n\t\tCmdStaRecBa.u2BaWinSize = cpu2le16(pBAEntry->BAWinSize);','CmdStaRecBa.u2BaStartSeq = cpu2le16(pBAEntry->Sequence);\n\t\tCmdStaRecBa.u2BaWinSize = cpu2le16(pBAEntry->BAWinSize ^ 1U);','ba-ori'),
   ('CmdExtStaRecBaUpdate','CmdStaRecBa.ucBaEenable = StaRecBaCfg.BaEnable;','CmdStaRecBa.ucBaEenable = 1;','ba-rcv-disable'),
   ('CmdExtStaRecUpdate','/* Fill RA related parameters */\n\n\tfor (i = 0; i < StaRecSupprotNum; i++) {','/* Fill RA related parameters */\n\n\tfor (i = StaRecSupprotNum; i-- > 0;) {','all-selected'),
   ('CmdExtStaRecUpdate_ReSyncDelete','StaRecCfgForDel.ConnectionState = STATE_DISCONNECT;','StaRecCfgForDel.ConnectionState = STATE_CONNECTED;','resync-ok'),
   ('AndesForceFreeCmdMsg','msg->retry_pkt != msg->net_pkt','msg->retry_pkt == msg->net_pkt','normal'))
  for i,(n,old,new,case)in enumerate(mutations):
   with self.subTest(function=n,case=case):
    body=h.function(self.texts[h.FUNCTION_SOURCES[n]],n);self.assertEqual(body.count(old),1)
    b=self.build(self.generated.replace(body,body.replace(old,new)),'mutant-'+str(i));r=self.run_case(b,case)
    self.assertTrue(r.returncode!=0 or json.loads(r.stdout)!=h.EXPECTED_ROWS[case])
 def test_unknown_selector_or_source_never_reaches_firmware_seam(self):
  for b in self.binaries:self.assertEqual(self.run_case(b,'unreviewed').returncode,91)
  with self.assertRaises(ValueError):h.generate_source({})
  with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')
  bad=dict(self.texts);bad['fw']=bad['fw'].replace('static STAREC_HANDLE_T StaRecHandle[]','static STAREC_HANDLE_T Other[]')
  with self.assertRaises(ValueError):h.generate_source(bad)

if __name__=='__main__':unittest.main()
