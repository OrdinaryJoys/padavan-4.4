"""Run current source whole RX functions under safe simulated DMA/allocator seams."""
import json,shutil,subprocess,tempfile,unittest
from pathlib import Path
import rx_transport_harness as h
ROOT=Path(__file__).resolve().parents[1]
FLAGS=('-std=gnu99','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-but-set-variable')
class RxTransportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='k2p-rx-transport-');cls.base=Path(cls.temp.name)
  cls.texts={k:(ROOT/p).read_text()for k,p in h.SOURCE_PATHS.items()};cls.rows={};cls.binaries={}
  clang=shutil.which('clang');gcc=shutil.which('gcc-16')or shutil.which('gcc')
  if not clang or not gcc:raise AssertionError('Clang and GNU C required')
  for v in h.VARIANT_PREFIXES:
   src=cls.base/(v+'.c');src.write_text(h.generate_source(cls.texts,variant=v));outputs=[]
   for compiler,extra in [(clang,('-fsanitize=address,undefined','-fno-sanitize-recover=undefined')),(gcc,())]:
    binary=cls.base/(v+('-clang'if compiler==clang else'-gnu'));r=subprocess.run([compiler,*FLAGS,*extra,str(src),'-o',str(binary)],capture_output=True,text=True,timeout=30)
    if r.returncode:raise AssertionError(r.stderr)
    rows={}
    for n in h.CASE_NAMES:
     r=subprocess.run([str(binary),n],capture_output=True,text=True,timeout=4)
     if r.returncode or r.stderr:raise AssertionError(v+' '+n+' '+r.stderr)
     row=json.loads(r.stdout)
     if tuple(row)!=h.FIELDS or any(type(value)is not int for key,value in row.items()if key!='case'):raise AssertionError('Exact typed RX row required')
     rows[n]=row
    outputs.append(rows);cls.binaries[v]=binary
   if outputs[0]!=outputs[1]:raise AssertionError('Clang/GNU RX observations differ')
   cls.rows[v]=outputs[0]
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_fixed_typed_rows_for_both_actual_build_and_legacy_variants(self):
  self.assertEqual(self.rows,h.EXPECTED_ROWS)
  self.assertEqual((len(h.FUNCTION_SOURCES),len(h.CASE_NAMES)),(14,91))
 def test_packet_length_guards_precede_alloc_copy_and_dispatch(self):
  for v,rows in self.rows.items():
   for n in ('outer-actual-zero','outer-actual-three','outer-actual-eleven','outer-declared-zero','outer-declared-eleven','outer-declared-long','outer-null','chip-short','chip-empty'):
    self.assertEqual(tuple(rows[n][k]for k in ('allocs','copies','dispatch')),(0,0,0),(v,n))
   for n in ('outer-exact','outer-padding','chip-valid'):
    self.assertEqual(tuple(rows[n][k]for k in ('allocs','copies','dispatch')),(1,1,1),(v,n))
 def test_scatter_scan_is_bounded_and_never_publishes_incomplete_chain(self):
  for rows in self.rows.values():
   self.assertEqual((rows['scan-no-last']['status'],rows['scan-no-last']['scans']),(-1,4))
   for n in ('scan-incomplete','scan-io-incomplete','scan-io-dma-limit'):self.assertEqual((rows[n]['status'],rows[n]['length']),(0,0))
   for n in ('scan-zero','scan-piece-big','scan-overflow'):self.assertEqual((rows[n]['status'],rows[n]['length']),(-1,0))
 def test_reservation_failures_preserve_owner_or_install_reserved_first_cell(self):
  for rows in self.rows.values():
   self.assertEqual((rows['get-alloc-fail']['owner_kept'],rows['get-alloc-fail']['read_index']),(1,0))
   self.assertEqual((rows['get-ring0-alloc-fail']['owner_kept'],rows['get-ring0-alloc-fail']['read_index']),(1,1))
   for n,r in rows.items():self.assertEqual((r['dma_safe'],r['content_ok']),(1,1),n)
 def test_drop_state_survives_pending_dma_and_discards_through_last_fragment(self):
  for rows in self.rows.values():
   self.assertEqual((rows['get-bad-chain-incomplete']['discard'],rows['get-bad-chain-incomplete']['read_index']),(1,1))
   for n in ('get-bad-chain-tail','get-bad-chain-resume','get-bad-middle'):
    self.assertEqual((rows[n]['status'],rows[n]['length'],rows[n]['discard']),(1,32,0),n)
 def test_large_expansion_failure_uses_the_original_or_expanded_allocation_family(self):
  r=self.rows['build']['get-ring0-large-scatter-expand-fail'];self.assertEqual((r['frag_frees'],r['heap_frees']),(1,0))
  r=self.rows['build']['get-ring0-large-scatter-follow-fail'];self.assertEqual((r['frag_frees'],r['heap_frees']),(1,1))
  self.assertEqual(self.rows['build']['get-ring0-large-scatter-good']['length'],4800)
 def test_full_header_declarations_and_actual_dispatch_macros_are_source_bound(self):
  for key,fragments in h.SOURCE_ANCHORS.items():
   for fragment in fragments:self.assertIn(fragment,self.texts[key])
  self.assertIn('SDL0:14;',h.PREFIX);self.assertIn('>> 29',h.PREFIX);self.assertIn('#define RXD_SIZE\t\t16',h.PREFIX)
  changed=dict(self.texts);changed['os_header']=changed['os_header'].replace('#define CONFIG_WIFI_BUILD_SKB','#define CHANGED_BUILD_SKB',1)
  with self.assertRaises(ValueError):h.generate_source(changed)
 def test_every_current_body_is_whole_function_and_abi_is_forwarded(self):
  bodies=h.actual_functions(self.texts)
  for v in h.VARIANT_PREFIXES:
   source=h.generate_source(self.texts,variant=v)
   for row in bodies.values():self.assertIn(row['body'],source)
  self.assertIn('ops->rx_event_handler(ad, data, rx_length);',bodies['chip_rx_event_handler']['body'])
  self.assertIn('wire_length > data_len',bodies['AndesMTRxEventHandler']['body'])
  self.assertIn('count < pRxRing->RxRingSize',bodies['rx_scatter_info']['body'])
  self.assertIn('pRxRing->rx_discard',bodies['mtd_pci_get_pkt_from_rx_resource']['body'])
 def test_current_mac_header_minima_preserve_short_controls_and_translated_frames(self):
  valid=('frame-ack','frame-cts','frame-pspoll','frame-rts','frame-bar','frame-ba-compressed','frame-ba-basic-header','frame-mgmt','frame-mgmt-ht','frame-data','frame-qos','frame-addr4','frame-qos-addr4-ht','frame-ethernet','frame-vlan')
  for variant,rows in self.rows.items():
   for name in valid:self.assertEqual(rows[name]['status'],1,(variant,name))
   for name,row in rows.items():
    if name.startswith('frame-'):
     self.assertEqual(tuple(row[k]for k in('allocs','copies','dispatch','releases')),(0,0,0,0),(variant,name))
     if name not in valid:self.assertEqual(row['status'],0,(variant,name))
 def test_legacy_immediate_consumers_validate_before_packet_view_and_sequence_reads(self):
  body=h.function(self.texts['data'],'mt_rx_info_2_blk')
  self.assertLess(body.index('if (!rx_frame_header_valid'),body.index('SET_OS_PKT_DATAPTR'))
  self.assertLess(body.index('if (GET_OS_PKT_LEN(pRxPacket) < LENGTH_802_3)'),body.index('extra_field_offset = IS_VLAN_PACKET'))
  branch=body.index('if ((((FRAME_CONTROL *)&temp_fc)->Type == FC_TYPE_MGMT)')
  self.assertGreater(body.index('fn_sn = *((UINT16 *)(pRxBlk->FC + 22));'),branch)
  self.assertIn('pRxBlk->Addr3 = NULL;',body);self.assertIn('pRxBlk->Addr4 = NULL;',body)
  err=h.function(self.texts['data'],'rtmp_chk_rx_err')
  self.assertLess(err.index('if (!pRxBlk->Addr2 &&'),err.index('if (rxd_base->RxD2.IcvErr)'))
 def test_unknown_variant_or_case_declines(self):
  with self.assertRaises(ValueError):h.generate_source(self.texts,variant='unknown')
  for binary in self.binaries.values():self.assertEqual(subprocess.run([str(binary),'unknown'],capture_output=True).returncode,91)

 def test_normal_rmac_base_optional_groups_and_padding_are_bounded_before_dispatch(self):
  for rows in self.rows.values():
   for n in ('process-ring0-normal-base-short','process-ring0-normal-group1-short','process-ring0-normal-group2-short','process-ring0-normal-large-allgroups-short','process-ring0-normal-pad-underflow'):
    self.assertEqual((rows[n]['status'],rows[n]['dispatch'],rows[n]['releases']),(1,0,1),n)
   for n in ('process-ring0-normal-group1-valid','process-ring0-normal-large-allgroups-valid','process-ring0-normal-large-group1-pad-valid'):
    self.assertEqual((rows[n]['status'],rows[n]['dispatch']),(0,1),n)
