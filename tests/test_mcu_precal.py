"""Native real-size MCU checks; trusted queue/IO/processor seams, no devices.

Current and disabled profiles use full ASAN+UBSan. Historical safe events use
ASAN and GNU89: the vendor null-member offsetof idiom has its own exact UBSan
rejection control. No short or over-capacity event executes in old code.
"""
import hashlib,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
import mcu_precal_harness as h
ROOT=Path(__file__).resolve().parents[1]
FLAGS=('-std=gnu89','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function',
       '-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-but-set-variable')
FIELDS=('case','status','used','unchanged','source_unchanged','checksum','bin_calls','flash_calls',
        'flag_calls','stamps','completion','last_write','queue_calls','queue_status','queue_length',
        'cache_calls','dumps','outer_allocs','outer_copies','outer_processes','outer_frees','outer_length','outer_payload','total')

class McuPrecalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='mcu-precal-');cls.base=Path(cls.temp.name)
        cls.texts={k:(ROOT/p).read_text()for k,p in h.SOURCE_PATHS.items()}
        cls.rows={};cls.sources={}
        clang=shutil.which('clang');gcc=shutil.which('gcc-16')or shutil.which('gcc')
        if not clang or not gcc:raise AssertionError('Clang and GNU C compilers required')
        for profile,cases,b,d in [('current',h.CASE_NAMES,False,False),('baseline',h.BASELINE_CASES,True,False),('disabled',h.DISABLED_CASES,False,True)]:
            p=cls.base/(profile+'.c');p.write_text(h.generate_source(cls.texts,baseline=b,disabled_oracle=d));cls.sources[profile]=p
            outputs=[]
            for compiler,extra in [(clang,('-fsanitize=address'if b else'-fsanitize=address,undefined','-fno-sanitize-recover=undefined')),(gcc,())]:
                binary=cls.base/(profile+('-clang'if compiler==clang else'-gnu'))
                r=subprocess.run([compiler,*FLAGS,*extra,str(p),'-o',str(binary)],capture_output=True,text=True,timeout=30)
                if r.returncode:raise AssertionError(r.stderr)
                rows=[]
                for case in cases:
                    r=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=5)
                    if r.returncode or r.stderr:raise AssertionError(profile+' '+case+' '+r.stderr)
                    row=json.loads(r.stdout)
                    if tuple(row)!=FIELDS or row['case']!=case:raise AssertionError('Exact MCU row schema required')
                    if any(type(v)is not int for k,v in row.items()if k!='case'):raise AssertionError('Integer MCU fields required')
                    rows.append(row)
                outputs.append(rows)
            if outputs[0]!=outputs[1]:raise AssertionError('Clang/GNU rows differ')
            cls.rows[profile]={r['case']:r for r in outputs[0]}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_complete_events_use_real_layout_and_preserve_input(self):
        for name,used,check in [('txlpf',40,2272174358),('txiq',156,998155307),('txdc',156,3398960216),('rxfi',0,625701821),('rxfd',1360,462650317)]:
            r=self.rows['current'][name]
            self.assertEqual((r['status'],r['used'],r['source_unchanged'],r['checksum']),(1,used,1,check))

    def test_six_and_nine_group_batches_fit_real_16k_capacity(self):
        for name,total,check in [('sequence-six',10660,2957632000),('sequence-nine',15964,2528967552)]:
            r=self.rows['current'][name]
            self.assertEqual((r['status'],r['used'],r['last_write'],r['total'],r['stamps'],r['completion'],r['checksum']),(1,0,total,total,1,4,check))
            self.assertLess(total,16384)

    def test_short_events_decline_at_all_three_boundaries(self):
        for kind in ('txlpf','txiq','txdc','rxfi','rxfd'):
            for prefix,status in [('short-',0),('queued-short-',1),('upstream-short-',-1)]:
                r=self.rows['current'][prefix+kind]
                self.assertEqual((r['status'],r['unchanged'],r['source_unchanged'],r['queue_calls'],r['dumps']),(status,1,1,0,0))
        for name in ('upstream-zero','upstream-null'):
            r=self.rows['current'][name];self.assertEqual((r['status'],r['unchanged'],r['queue_calls'],r['dumps']),(-1,1,0,0))

    def test_queue_wrappers_forward_actual_lengths_and_status(self):
        for name,length in [('txlpf',224),('txiq',1300),('txdc',1300),('rxfi',868),('rxfd',1352)]:
            direct=self.rows['current'][name];q=self.rows['current']['queued-'+name];up=self.rows['current']['upstream-'+name]
            self.assertEqual((q['status'],q['used'],q['checksum']),(0,direct['used'],direct['checksum']))
            self.assertEqual((up['status'],up['used'],up['checksum'],up['queue_calls'],up['queue_length'],up['queue_status']),(0,direct['used'],direct['checksum'],1,length,0))
        self.assertEqual((self.rows['current']['upstream-cache']['status'],self.rows['current']['upstream-cache']['cache_calls']),(2,1))

    def test_invalid_events_modes_bitmaps_groups_and_capacity_preserve_state(self):
        names=('null-data','null-store','invalid-id','invalid-mode','mixed-mode','nic-gone','halt','bitmap-zero','bitmap-high','bitmap-unrequested','requested-zero','requested-high','group-high','group-unselected','capacity-full','capacity-beyond','capacity-max','capacity-one-short','flash-small','flash-span-short','flash-null-image','flash-wrong-view')
        for name in names:
            r=self.rows['current'][name]
            self.assertEqual((r['status'],r['unchanged'],r['source_unchanged'],r['bin_calls'],r['flash_calls'],r['flag_calls']),(0,1,1,0,0,0),name)

    def test_corrupt_prior_records_decline_without_mutation(self):
        for name,r in self.rows['current'].items():
            if name.startswith('old-'):
                self.assertEqual((r['status'],r['unchanged'],r['source_unchanged'],r['bin_calls'],r['flag_calls']),(0,1,1,0,0),name)

    def test_duplicates_decline_and_batch_state_is_per_adapter(self):
        for name,used in [('duplicate-txlpf',40),('duplicate-rxfd',1360)]:
            r=self.rows['current'][name];self.assertEqual((r['status'],r['used'],r['unchanged']),(0,used,1))
            old=self.rows['baseline'][name];self.assertEqual((old['status'],old['used']),(1,used*2))
        for name in ('new-batch-rxfd','two-adapters-rxfd'):
            r=self.rows['current'][name];self.assertEqual((r['status'],r['used']),(1,1360))

    def test_persist_failures_do_not_raise_completion(self):
        for name in ('bin-data-failure','flash-data-failure','bin-flag-failure','flash-flag-failure'):
            r=self.rows['current'][name]
            self.assertEqual((r['status'],r['used'],r['stamps'],r['completion']),(0,0,0,0))
            self.assertEqual(r['flag_calls'],1 if 'flag-failure'in name else 0)
        for name in ('flash-data-failure','bin-flag-failure','flash-flag-failure'):
            self.assertEqual(self.rows['baseline'][name]['status'],1)
        self.assertEqual(self.rows['baseline']['flash-data-failure']['completion'],4)
        self.assertEqual((self.rows['current']['flash-good']['status'],self.rows['current']['flash-good']['completion']),(1,4))

    def test_outer_header_guard_precedes_copy_and_subtraction(self):
        for name in ('outer-zero','outer-one','outer-four','outer-eleven','outer-null','outer-uninitialized'):
            r=self.rows['current'][name]
            self.assertEqual((r['status'],r['outer_allocs'],r['outer_copies'],r['outer_processes'],r['unchanged']),(0,0,0,0,1))
        for name,length,payload in [('outer-twelve',12,0),('outer-payload',20,8)]:
            r=self.rows['current'][name]
            self.assertEqual(tuple(r[n]for n in ('outer_allocs','outer_copies','outer_processes','outer_frees','outer_length','outer_payload')),(1,1,1,1,length,payload))
        r=self.rows['current']['outer-alloc-failure'];self.assertEqual((r['outer_allocs'],r['outer_processes']),(1,0))

    def test_restore_validator_accepts_complete_streams_and_declines_malformed_boundaries(self):
        valid={'restore-one':1820,'restore-six':10660,'restore-nine':15964,'restore-padded':16384,'restore-subset-rxfd':15964}
        for name,row in self.rows['current'].items():
            if not name.startswith('restore-'):continue
            self.assertEqual((row['status'],row['unchanged'],row['source_unchanged']),(1 if name in valid else 0,1,1),name)
            self.assertEqual((row['bin_calls'],row['flash_calls'],row['flag_calls']),(0,0,0))
            if name in valid:self.assertEqual(row['total'],valid[name])

    def test_fixed_3ba_functions_match_commit(self):
        text=subprocess.run(['git','show',h.BASELINE_COMMIT+':'+h.SOURCE_PATHS['mcu']],cwd=ROOT,capture_output=True,text=True,check=True).stdout
        for name,body in h.BASELINE_FUNCTIONS.items():
            self.assertEqual(h.function(text,name),body)
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),h.BASELINE_FUNCTIONS_SHA256[name])

    def test_historical_null_offsetof_has_specific_ubsan_rejection(self):
        binary=self.base/'old-ubsan'
        r=subprocess.run([shutil.which('clang'),*FLAGS,'-fsanitize=address,undefined','-fno-sanitize-recover=undefined',str(self.sources['baseline']),'-o',str(binary)],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run([str(binary),'txlpf'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(r.returncode,0)
        self.assertIn("runtime error: member access within null pointer of type 'TXLPF_CAL_INFO_T'",r.stderr)
        self.assertIn('UndefinedBehaviorSanitizer',r.stderr)

    def test_disabled_oracles_fail_positive_observations(self):
        for name in h.DISABLED_CASES:self.assertNotEqual(self.rows['current'][name],self.rows['disabled'][name])
        self.assertEqual((len(self.rows['current']),len(self.rows['baseline']),len(self.rows['disabled'])),(115,17,5))

    def test_invalid_profile_and_missing_actual_declaration_decline(self):
        changed=dict(self.texts);changed['chip']=changed['chip'].replace('#define PRE_CAL_SIZE_ONE_CARD   (16 * 1024)','#define RENAMED_SIZE 1')
        with self.assertRaises(ValueError):h.generate_source(changed)
        with self.assertRaises(ValueError):h.generate_source(self.texts,baseline=1)
        with self.assertRaises(ValueError):h.generate_source(self.texts,baseline=True,disabled_oracle=True)

if __name__=='__main__':unittest.main()
