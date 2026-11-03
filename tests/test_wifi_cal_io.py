"""Actual calibration IO/close lifetimes and explicit NIC pre-cal section."""
import hashlib,json,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
import wifi_cal_io_harness as h
ROOT=Path(__file__).resolve().parents[1]
FLAGS=['-std=gnu89','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter','-Wno-unused-variable']


def lost_old_free_row(completed,current):
    """Accept only the deliberate one-buffer leak, with its exact typed row."""
    expected=dict(current)
    if current['case']!='restore-previous-ok' or current['trace'].split(',').count('free')!=1:
        raise AssertionError('Unexpected lost-old-free control input')
    expected.update(frees=current['frees']-1,live_allocs=current['live_allocs']+1,
                    trace=','.join(x for x in current['trace'].split(',')if x!='free'))
    row=json.loads(completed.stdout)
    if (type(row)is not dict or set(row)!=set(expected) or
            any(type(row[k])is not type(expected[k])for k in expected)or row!=expected):
        raise AssertionError('Lost-old-free control lacks its exact typed resource delta')
    if completed.returncode==0:
        if completed.stderr:raise AssertionError('Unexpected successful-control diagnostic')
    else:
        pattern=(r'\n={10,}\n==[0-9]+==ERROR: LeakSanitizer: detected memory leaks\n\n'
                 r'Direct leak of 64 byte\(s\) in 1 object\(s\) allocated from:\n'
                 r'(?:[ \t]+#[0-9]+ [^\n]+\n)+\n'
                 r'SUMMARY: AddressSanitizer: 64 byte\(s\) leaked in 1 allocation\(s\)\.\n')
        if completed.returncode!=1 or not re.fullmatch(pattern,completed.stderr):
            raise AssertionError('Unexpected lost-old-free sanitizer failure: '+completed.stderr)
    return row


class WifiCalIOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='wifi-cal-native-')
        cls.base=Path(cls.temp.name);cls.texts={k:(ROOT/v).read_text() for k,v in h.SOURCE_PATHS.items()}
        cls.codes={name:h.generate_source(cls.texts,**kw) for name,kw in
                   [('current',{}),('baseline',{'baseline':True}),('disabled',{'disabled_oracle':True})]}
        cls.binaries={n:cls.compile(s,n) for n,s in cls.codes.items()}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @classmethod
    def compile(cls,source,name,gcc=False):
        p=cls.base/(name+'.c');p.write_text(source);b=p.with_suffix('')
        compiler=(shutil.which('gcc-16') or shutil.which('gcc')) if gcc else shutil.which('clang')
        if not compiler:raise AssertionError('Required native compiler absent')
        extra=[] if gcc else ['-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
        r=subprocess.run([compiler,*FLAGS,*extra,str(p),'-o',str(b)],capture_output=True,text=True,timeout=30)
        if r.returncode:raise AssertionError(r.stderr)
        return b

    def row(self,case,profile='current'):
        b=self.binaries.get(profile,profile);r=subprocess.run([str(b),case],capture_output=True,text=True,timeout=5)
        self.assertEqual((r.returncode,r.stderr),(0,''),r.stderr);return json.loads(r.stdout)

    def test_all55_current_rows_have_balanced_resources_and_typed_status(self):
        successes={'read-ok','read-zero-len','read-first','read-second','write-ok','write-zero-len',
                   'data-read-ok','data-write-ok'}
        restore_fail={'restore-flash-read-error','restore-flash-read-short','restore-alloc-error',
                      'restore-alloc-null','restore-command-error','restore-previous-error','restore-zero-size'}
        for case in h.CASE_NAMES:
            with self.subTest(case=case):
                r=self.row(case)
                expected=(int(case not in restore_fail) if case.startswith('restore-') else
                          0 if case=='legacy-close-error' else -5 if case=='checked-close-error' else
                          int(case not in successes))
                self.assertEqual(r['result'],expected);self.assertEqual((r['fsdepth'],r['bad_close']),(0,0))
                self.assertEqual(len(r),26)
                for key,value in r.items():self.assertIs(type(value),str if key in ('case','trace') else int)

    def test_failed_and_short_reads_preserve_old_destination_until_checked_close(self):
        for case in ('read-error','read-short','read-zero','read-oversized','read-open-error','read-empty',
                     'read-close-error','read-null','read-offset-max','read-length-max','read-alloc-error',
                     'read-alloc-null','data-read-short','data-read-close-error'):
            with self.subTest(case=case):
                r=self.row(case);self.assertEqual((r['result'],r['buf0'],r['buf15'],r['live_allocs']),(1,85,85,0))
        r=self.row('read-ok');self.assertEqual((r['result'],r['buf0'],r['buf15']),(0,51,51))
        self.assertEqual((r['opens'],r['closes']),(1,1))

    def test_invalid_numeric_and_null_inputs_do_not_open_files(self):
        for family in ('read','write'):
            for suffix in ('null','offset-max','length-max'):
                with self.subTest(family=family,suffix=suffix):
                    r=self.row(family+'-'+suffix)
                    self.assertEqual((r['result'],r['opens'],r['closes'],r['allocs']),(1,0,0,0))
            r=self.row(family+'-zero-len');self.assertEqual((r['result'],r['opens'],r['allocs']),(0,0,0))

    def test_all_four_wrappers_and_card_paths_keep_status_conventions(self):
        for case in ('read-ok','write-ok','data-read-ok','data-write-ok'):self.assertEqual(self.row(case)['result'],0)
        for case in ('data-read-nonmt','data-write-nonmt'):
            r=self.row(case);self.assertEqual((r['result'],r['opens']),(1,0))
        self.assertEqual(self.row('read-first')['path'],1);self.assertEqual(self.row('read-second')['path'],2)

    def test_checked_close_exposes_failure_and_legacy_close_remains_zero(self):
        self.assertEqual((self.row('legacy-close-error')['result'],self.row('checked-close-error')['result']),(0,-5))
        for case in ('read-close-error','write-close-error','data-read-close-error','data-write-close-error'):
            r=self.row(case);self.assertEqual((r['result'],r['closes'],r['bad_close']),(1,1,0))

    def test_flash_read_or_allocation_failure_stops_before_restore_and_parser(self):
        for case in ('restore-flash-read-error','restore-flash-read-short','restore-alloc-error',
                     'restore-alloc-null','restore-previous-error','restore-zero-size'):
            r=self.row(case);self.assertEqual((r['result'],r['commands'],r['parsed'],r['flagwrites']),(0,0,0,0))
            self.assertEqual(r['precal'],int('previous' in case))
        r=self.row('restore-command-error');self.assertEqual((r['result'],r['commands'],r['parsed'],r['precal']),(0,1,0,1))

    def test_missing_bin_calibration_keeps_online_fallback_without_using_partial_data(self):
        for case in ('restore-bin-error','restore-bin-short','restore-bin-close-error'):
            r=self.row(case);self.assertEqual((r['result'],r['commands'],r['parsed'],r['calbits'],r['live_allocs']),(1,0,1,0,0))
        r=self.row('restore-bin-ok');self.assertEqual((r['commands'],r['parsed'],r['poison'],r['live_allocs']),(1,1,0,1))

    def test_previous_owned_restore_image_survives_failures_and_retires_on_success(self):
        bad=self.row('restore-previous-error');good=self.row('restore-previous-ok');twice=self.row('restore-repeat')
        self.assertEqual((bad['precal'],bad['live_allocs'],bad['frees']),(1,1,1))
        self.assertEqual((good['live_allocs'],good['frees']),(1,1))
        self.assertEqual((twice['commands'],twice['live_allocs'],twice['frees']),(2,1,1))

    def test_fixed_old_failures_and_disabled_execution_are_distinct(self):
        for case in h.BASELINE_CASES:
            with self.subTest(case=case):self.assertNotEqual(self.row(case,'baseline'),self.row(case))
        self.assertEqual(self.row('read-open-error','baseline')['fsdepth'],1)
        self.assertEqual(self.row('restore-flash-read-error','baseline')['poison'],1)
        self.assertEqual(self.row('restore-alloc-error','baseline')['parsed'],1)
        for case in h.DISABLED_CASES:
            r=self.row(case,'disabled')
            self.assertEqual((r['allocs'],r['reads'],r['commands'],r['trace']),(0,0,0,''))
            self.assertNotEqual(r,self.row(case))

    def test_removed_exact_io_close_restore_and_startup_guards_are_detected(self):
        source=self.codes['current']
        changes=(
            ('short-io','if (count == (INT)len)','if (count >= 0)','read-short'),
            ('hide-close','return filp_close(osfd, NULL);','return (filp_close(osfd, NULL), 0);','read-close-error'),
            ('lost-fs','RtmpOSFSInfoChange(&osFSInfo, FALSE);','(void)osFSInfo;','read-error'),
            ('ignore-mtd','if (status) {','if (0) {','restore-flash-read-error'),
            ('lost-caller','if (!rtmp_eeprom_restore_precal(pAd, PreCalSize, DoPreCal))\n\t\treturn FALSE;',
             'rtmp_eeprom_restore_precal(pAd, PreCalSize, DoPreCal);','restore-alloc-error'),
            ('lost-old-free','if (pAd->PreCalReStoreBuffer)\n\t\tos_free_mem(pAd->PreCalReStoreBuffer);','(void)pAd;','restore-previous-ok'),
        )
        for name,before,after,case in changes:
            with self.subTest(control=name):
                self.assertEqual(source.count(before),1)
                mutant=source.replace(before,after);current=self.row(case)
                if name=='lost-old-free':
                    # LSan can terminate before libc flushes stdout. Flush only
                    # this private negative control, keeping every model/driver unchanged.
                    terminal=' free(a.PreCalReStoreBuffer);\n return 0;'
                    self.assertEqual(mutant.count(terminal),1)
                    mutant=mutant.replace(terminal,' fflush(stdout);\n'+terminal)
                b=self.compile(mutant,name)
                if name!='lost-old-free':
                    self.assertNotEqual(self.row(case,b),current)
                    continue
                result=subprocess.run([str(b),case],capture_output=True,text=True,timeout=5)
                row=lost_old_free_row(result,current);self.assertNotEqual(row,current)
                # Replay the Linux diagnostic from CI41590074389 on all hosts.
                diagnostic=("\n=================================================================\n"
                    "==17734==ERROR: LeakSanitizer: detected memory leaks\n\n"
                    "Direct leak of 64 byte(s) in 1 object(s) allocated from:\n"
                    "    #0 0x5636b5f7314e in __interceptor_malloc (/tmp/wifi-cal-native-pvgc8xft/lost-old-free+0xa514e) (BuildId: 820a04f274e23a79815f167e2081fbff1e7c162d)\n"
                    "    #1 0x5636b5faf150 in main (/tmp/wifi-cal-native-pvgc8xft/lost-old-free+0xe1150) (BuildId: 820a04f274e23a79815f167e2081fbff1e7c162d)\n"
                    "    #2 0x7f38a4029d8f  (/lib/x86_64-linux-gnu/libc.so.6+0x29d8f) (BuildId: 6a6cb5a80fd5e5bb5bf3aeaa111add98e88843a5)\n\n"
                    "SUMMARY: AddressSanitizer: 64 byte(s) leaked in 1 allocation(s).\n")
                stdout=json.dumps(row)
                self.assertEqual(lost_old_free_row(subprocess.CompletedProcess([],1,stdout,diagnostic),current),row)
                self.assertEqual(lost_old_free_row(subprocess.CompletedProcess([],0,stdout,''),current),row)
                wrong_type=dict(row,live_allocs=str(row['live_allocs']))
                faults=[(2,stdout,diagnostic),(-11,stdout,diagnostic),(0,stdout,diagnostic),
                        (1,stdout,diagnostic.replace('64 byte','128 byte')),
                        (1,stdout,diagnostic.replace('1 object','2 object')),
                        (1,stdout,diagnostic.replace('1 allocation','2 allocation')),
                        (1,stdout,diagnostic+'unrelated failure\n'),
                        (1,stdout,'AddressSanitizer: heap-use-after-free\n'),
                        (1,json.dumps(current),diagnostic),(1,json.dumps(wrong_type),diagnostic),
                        (1,'',diagnostic)]
                for code,out,err in faults:
                    with self.assertRaises((AssertionError,ValueError)):
                        lost_old_free_row(subprocess.CompletedProcess([],code,out,err),current)

    def test_strict_gnu89_all69_cases_match_clang(self):
        compiler=shutil.which('gcc-16') or shutil.which('gcc')
        macros=subprocess.run([compiler,'-dM','-E','-x','c','-'],input='',capture_output=True,text=True,timeout=10)
        self.assertIn('#define __GNUC__ ',macros.stdout);self.assertNotIn('#define __clang__ ',macros.stdout)
        for mode,cases in [('current',h.CASE_NAMES),('baseline',h.BASELINE_CASES),('disabled',h.DISABLED_CASES)]:
            b=self.compile(self.codes[mode],'gcc-'+mode,gcc=True)
            source=self.base/('gcc-'+mode+'.c')
            object_flags=[flag for flag in FLAGS if flag!='-O1']+['-Os','-static','-s','-c']
            r=subprocess.run([compiler,*object_flags,str(source),'-o',str(source.with_suffix('.o'))],
                             capture_output=True,text=True,timeout=30)
            self.assertEqual((r.returncode,r.stderr),(0,''),r.stderr)
            for case in cases:
                with self.subTest(profile=mode,case=case):self.assertEqual(self.row(case,b),self.row(case,mode))

    def test_platform_loff_alias_uses_linux_declaration_or_64bit_fallback(self):
        start=h.PREFIX.index('#if !defined(__linux__)\n')
        end=h.PREFIX.index('\n',h.PREFIX.index('typedef char model_loff_t_is_64_bits',start))
        declaration=h.PREFIX[start:end]
        self.assertIn('#include <sys/types.h>',h.PREFIX)
        main='\nint main(void){return sizeof(loff_t)==8?0:1;}\n'
        for gcc in(False,True):
            for profile,prefix in [('linux','\n#define __linux__ 1\ntypedef long loff_t;\n'),
                                   ('fallback','\n#undef __linux__\n')]:
                binary=self.compile(prefix+declaration+main,'loff-'+profile+str(gcc),gcc=gcc)
                result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=5)
                self.assertEqual((result.returncode,result.stderr),(0,''),result.stderr)
            old=self.base/('old-loff'+str(gcc)+'.c')
            old.write_text('typedef long loff_t;\ntypedef long long loff_t;\n'+main)
            compiler=(shutil.which('gcc-16')or shutil.which('gcc'))if gcc else shutil.which('clang')
            result=subprocess.run([compiler,*FLAGS,'-c',str(old),'-o',str(old.with_suffix('.o'))],
                                  capture_output=True,text=True,timeout=30)
            self.assertNotEqual(result.returncode,0);self.assertIn('loff_t',result.stderr)

    def test_full_body_hashes_and_observed_nic_section_are_explicit(self):
        functions=h.actual_functions(self.texts);self.assertEqual((len(functions),len(h.BASELINE_FUNCTIONS)),(9,6))
        self.assertEqual(sum(x['execution']=='whole-function' for x in functions.values()),8)
        self.assertNotIn(functions['NICReadEEPROMParameters']['body'],self.codes['current'])
        for name,item in functions.items():
            if name!='NICReadEEPROMParameters':self.assertIn(item['body'],self.codes['current'])
            self.assertNotIn(item['body'],self.codes['disabled'])
        for name,body in h.BASELINE_FUNCTIONS.items():self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),h.BASELINE_FUNCTIONS_SHA256[name])
        with mock.patch.dict(h.BASELINE_FUNCTIONS,{'RtmpOSFileClose':'wrong'}):
            with self.assertRaises(ValueError):h.generate_source(self.texts)
        with self.assertRaises(ValueError):h.generate_source(dict(self.texts,os_header=''))
        self.assertEqual((len(h.CASE_NAMES),len(h.BASELINE_CASES),len(h.DISABLED_CASES)),(55,12,2))


if __name__=='__main__':unittest.main()
