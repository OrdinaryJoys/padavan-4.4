"""Whole actual BIN IO/initialization and explicit multicard regression controls."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import wifi_bin_io_harness as h

ROOT=Path(__file__).resolve().parents[1]


class WifiBinIOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-wifi-bin-')
        cls.base=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.codes={name:h.generate_source(cls.texts,**opts)for name,opts in
                   [('current',{}),('baseline',{'baseline':True}),('disabled',{'disabled_oracle':True})]}
        cls.binaries={name:cls.compile(code,name)for name,code in cls.codes.items()}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @classmethod
    def compile(cls,code,name,compiler=None,sanitize=True):
        c=cls.base/(name+'.c');binary=cls.base/name;c.write_text(code)
        flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
               '-Wno-unused-function','-Wno-sign-compare']
        if sanitize:flags+=['-fsanitize=address,undefined','-fno-inline','-fsanitize-address-use-after-return=always']
        result=subprocess.run([compiler or shutil.which('clang'),*flags,str(c),'-o',str(binary)],
                              capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
        return binary

    def row(self,case,profile='current'):
        result=subprocess.run([str(self.binaries.get(profile,profile)),case],capture_output=True,
                              text=True,timeout=5,env=dict(os.environ,ASAN_OPTIONS='detect_stack_use_after_return=1'))
        self.assertEqual((result.returncode,result.stderr),(0,''),result.stderr)
        return json.loads(result.stdout)

    def test_all_defined_positive_cases_and_profiles_are_typed_and_clean(self):
        for profile,names in [('current',h.CASE_NAMES),('baseline',h.BASELINE_CASES),('disabled',h.DISABLED_CASES)]:
            for case in names:
                with self.subTest(profile=profile,case=case):
                    row=self.row(case,profile)
                    self.assertEqual(row['case'],case)
                    self.assertTrue(all(type(v)is(str if k in ('case','diagnostic','trace')else int)for k,v in row.items()))
                    self.assertEqual(row['doubleclose'],0)
                    if profile=='current':self.assertEqual(row['fsdepth'],0)
        self.assertEqual((len(h.CASE_NAMES),len(h.BASELINE_CASES),len(h.DISABLED_CASES)),(84,39,2))

    def test_failed_file_reload_preserves_old_ram_and_metadata(self):
        for case in ('load-zero','load-short','load-read-error','load-close-error','load-open-no-cache',
                     'load-open-short-cache','load-null-image','load-small-profile','load-allocation-error'):
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual((row['status'],row['image0'],row['image_last']),(0,85,85))
                self.assertEqual((row['mode'],row['source'],row['diagnostic']),(2,2,'old-source'))
                self.assertEqual(row['live_allocs'],0)
        old=self.row('load-short','baseline')
        self.assertEqual((old['status'],old['image0'],old['image_last']),(1,160,0))

    def test_complete_file_and_valid_cached_default_are_successful(self):
        for case,label in [('load-ok','/inert/eeprom.bin'),('load-open-cache','Default bin'),
                           ('load-empty-path-cache','Default bin')]:
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual((row['status'],row['image0'],row['image_last']),(1,160,159))
                self.assertEqual((row['mode'],row['source'],row['diagnostic']),(4,8,label))
        old=self.row('load-open-cache','baseline')
        self.assertEqual((old['status'],old['fsdepth']),(0,1))

    def test_file_write_requires_exact_length_and_checked_close(self):
        self.assertEqual(self.row('write-ok')['status'],1)
        for case in ('write-zero','write-short','write-io-error','write-close-error'):
            with self.subTest(case=case):
                self.assertEqual((self.row(case)['status'],self.row(case)['closes']),(0,1))
                self.assertEqual(self.row(case,'baseline')['status'],1)
        for case in ('write-open-error','write-empty-path'):
            self.assertEqual(self.row(case)['fsdepth'],0)
            self.assertEqual(self.row(case,'baseline')['fsdepth'],1)

    def test_multicard_labels_survive_return_and_k2p_macro_profile_keeps_path(self):
        for case,status in [('load-multicard-first',1),('load-multicard-second',1),
                            ('reset-multicard-first',0),('reset-multicard-second',0)]:
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual((row['status'],row['diagnostic']),(status,'Multicard default bin'))
        code=self.codes['current'].replace('#define RT_SOC_SUPPORT 1\n#define MULTIPLE_CARD_SUPPORT 1\n','').replace('profile_size=1024;','profile_size=16384;')
        self.assertNotEqual(code,self.codes['current'])
        binary=self.compile(code,'configured-k2p-macros-off')
        for case in ('load-multicard-first','load-multicard-second','reset-multicard-first'):
            self.assertEqual(self.row(case,binary)['diagnostic'],'/inert/eeprom.bin')
        self.assertEqual(self.row('load-multicard-fallback')['diagnostic'],'/inert/eeprom.bin')

    def test_old_multicard_stack_pointer_and_path_overflow_are_asan_controls(self):
        for case,diagnostic in [('load-multicard-first','stack-use-after-return'),
                                ('reset-multicard-first','stack-use-after-return'),
                                ('load-multicard-long-name','stack-buffer-overflow'),
                                ('write-multicard-long-name','stack-buffer-overflow'),
                                ('reset-multicard-long-name','stack-buffer-overflow')]:
            with self.subTest(case=case):
                result=subprocess.run([str(self.binaries['baseline']),case],capture_output=True,text=True,timeout=5,
                                      env=dict(os.environ,ASAN_OPTIONS='detect_stack_use_after_return=1'))
                self.assertNotEqual(result.returncode,0);self.assertIn(diagnostic,result.stderr)
                self.assertNotIn(case,h.BASELINE_CASES)
        for case in ('load-multicard-long-name','write-multicard-long-name','reset-multicard-long-name'):
            self.assertEqual(self.row(case)['opens'],0)

    def test_word_and_range_accessors_fail_before_overrun_or_null_copy(self):
        for case in ('word-read-overflow','word-read-null-value','word-write-overflow',
                     'range-read-overflow','range-read-null-buffer','range-write-overflow','range-write-null-buffer'):
            self.assertEqual(self.row(case)['status'],1)
        self.assertEqual(self.row('word-read-overflow')['word'],65535)
        self.assertEqual(self.row('word-write-last')['image_last'],161)
        self.assertEqual((self.row('range-read-zero')['status'],self.row('range-write-zero')['status']),(1,0))
        for case in ('word-read-overflow','word-write-overflow','range-read-overflow','range-write-overflow'):
            result=subprocess.run([str(self.binaries['baseline']),case],capture_output=True,text=True,timeout=5)
            self.assertNotEqual(result.returncode,0);self.assertIn('stack-buffer-overflow',result.stderr)

    def test_init_load_and_each_allocation_failure_stop_before_null_memset(self):
        self.assertEqual(self.row('init-read-error')['status'],1)
        self.assertEqual(self.row('init-read-error')['cal_allocs'],3)
        self.assertEqual(self.row('init-read-error')['live_allocs'],0)
        for case in ('init-allocation-dcoc','init-allocation-dpd1','init-allocation-dpd2','init-reuse-partial-failure'):
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual((row['status'],row['live_allocs']),(1,0))
                self.assertEqual((row['mode'],row['source'],row['diagnostic']),(2,2,'old-source'))
                self.assertEqual((row['image0'],row['image_last'],row['reads']),(85,85,0))
        result=subprocess.run([str(self.binaries['baseline']),'init-allocation-dcoc'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0)
        self.assertTrue('runtime error:'in result.stderr or 'AddressSanitizer'in result.stderr)

    def test_repeated_init_reuses_owned_calibration_and_never_frees_flash_aliases(self):
        new=self.row('init-repeat');old=self.row('init-repeat','baseline')
        self.assertEqual((new['cal_allocs'],new['live_allocs'],new['cal_flags']),(3,3,3))
        self.assertEqual((old['cal_allocs'],old['live_allocs']),(6,6))
        alias=self.row('init-reuse')
        self.assertEqual((alias['status'],alias['cal_allocs'],alias['live_allocs']),(0,3,3))
        # The allocator seam aborts any attempt to free a preexisting alias.
        self.assertEqual(self.row('init-reuse-partial-failure')['live_allocs'],0)

    def test_failed_optional_calibration_clears_ram_bits_used_by_hardware(self):
        for case,bits,flags in [('init-cal-dcoc-error',1,2),('init-cal-dpd1-error',2,1),
                                ('init-cal-dpd2-error',2,1)]:
            with self.subTest(case=case):
                current=self.row(case);old=self.row(case,'baseline')
                self.assertEqual((current['status'],current['cal_flags'],current['cal_control']),(0,flags,bits))
                self.assertEqual((old['cal_flags'],old['cal_control']),(flags,3))
        for mask,case in [('1','init-cal-dcoc-error'),('0','init-cal-dpd1-error')]:
            before='do_cal &= ~(1 << '+mask+');'
            self.assertEqual(self.codes['current'].count(before),1)
            binary=self.compile(self.codes['current'].replace(before,'do_cal &= ~0;'),'lost-cal-bit-'+mask)
            self.assertEqual(self.row(case,binary)['cal_control'],3)

    def test_control_and_efuse_callers_propagate_failure_before_hook(self):
        for case in ('set-load-read-error','efuse-read-error','efuse-open-no-cache'):
            with self.subTest(case=case):
                new=self.row(case);old=self.row(case,'baseline')
                self.assertEqual(new['hooks'],0);self.assertEqual(old['hooks'],1)
                self.assertEqual((new['mode'],new['source']),((1,1)if case.startswith('efuse-')else(2,2)))
                self.assertEqual((new['unchanged'],new['cal_owned'],new['live_allocs']),(1,0,0))
                self.assertEqual(new['cal_views'],0 if case.startswith('efuse-')else 7)
        self.assertEqual(self.row('set-write-io-error')['status'],0)
        self.assertEqual(self.row('set-write-io-error','baseline')['status'],1)
        self.assertEqual(self.row('efuse-read-error')['efuse'],1)
        for case,status in [('set-load-hook-error',0),('efuse-hook-error',1)]:
            self.assertEqual(self.row(case)['status'],status)

    def test_setter_and_empty_efuse_publish_complete_bin_ownership(self):
        for case,status,hooks in [('set-load-ok',1,1),('set-load-open-cache',1,1),
                                  ('set-load-repeat',1,2),('efuse-ok',0,1),('efuse-repeat',0,2)]:
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual([row[k]for k in('status','profile','mode','source','callbacks','hooks')],
                                 [status,4,4,8,4,hooks])
                self.assertEqual([row[k]for k in('cal_owned','cal_views','cal_allocs','live_allocs','cal_flags')],
                                 [7,0,3,3,3])
                self.assertEqual(row['cal_control'],3)
                if case.startswith('efuse-'):self.assertEqual(row['efuse'],0)
        old=self.row('set-load-ok','baseline')
        self.assertEqual([old[k]for k in('profile','mode','callbacks','cal_owned','cal_views')],[2,4,4,0,7])
        old=self.row('efuse-ok','baseline')
        self.assertEqual([old[k]for k in('profile','mode','callbacks','cal_owned')],[1,4,4,0])

    def test_transition_allocation_failures_preserve_ram_views_profile_and_callbacks(self):
        for prefix,status,profile,views in [('set-load-',0,2,7),('efuse-',1,1,0)]:
            for part in ('dcoc','dpd1','dpd2'):
                with self.subTest(prefix=prefix,part=part):
                    row=self.row(prefix+'allocation-'+part)
                    self.assertEqual([row[k]for k in('status','unchanged','profile','mode','callbacks','cal_views','cal_owned','live_allocs')],
                                     [status,1,profile,profile,profile,views,0,0])
                    self.assertEqual([row[k]for k in('hooks','opens','reads')],[0,0,0])
                    self.assertEqual(row['efuse'],1)

    def test_missing_nic_and_disabled_setter_decline_without_side_effects(self):
        for case,status,profile in [('set-load-nic-missing',0,2),('set-load-negative',0,2),
                                    ('efuse-nic-missing',1,1)]:
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual([row[k]for k in('status','profile','callbacks','unchanged')],[status,profile,profile,1])
                self.assertEqual([row[k]for k in('allocs','opens','reads','hooks')],[0,0,0,0])

    def test_transition_calibration_failures_select_online_fallback(self):
        for prefix,status in [('set-load-',1),('efuse-',0)]:
            for part,bits,flags in [('dcoc',1,2),('dpd1',2,1),('dpd2',2,1)]:
                with self.subTest(prefix=prefix,part=part):
                    row=self.row(prefix+'cal-'+part+'-error')
                    self.assertEqual([row[k]for k in('status','profile','callbacks','cal_owned','cal_views','cal_control','cal_flags')],
                                     [status,4,4,7,0,bits,flags])

    def test_hook_failure_keeps_owned_buffers_identifiable_for_cleanup(self):
        for case,status,callbacks in [('set-load-hook-error',0,2),('efuse-hook-error',1,1)]:
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual([row[k]for k in('status','profile','mode','source','callbacks','cal_owned','cal_views','live_allocs')],
                                 [status,4,0,0,callbacks,7,0,3])
                self.assertEqual(row['capinit'],0)
                self.assertEqual(row['efuse'],1)

    def test_source_variant_without_set1_calibration_still_publishes_bin_profile(self):
        before='#define PRE_CAL_TRX_SET1_SUPPORT 1\n'
        self.assertEqual(self.codes['current'].count(before),1)
        binary=self.compile(self.codes['current'].replace(before,''),'without-set1-calibration')
        for case,status in [('set-load-ok',1),('efuse-ok',0)]:
            with self.subTest(case=case):
                row=self.row(case,binary)
                self.assertEqual([row[k]for k in('status','profile','mode','source','callbacks','cal_allocs','cal_owned','cal_views')],
                                 [status,4,4,8,4,0,0,0])
        for case,status,profile in [('set-load-read-error',0,2),('efuse-read-error',1,1),
                                    ('set-load-nic-missing',0,2),('efuse-nic-missing',1,1)]:
            with self.subTest(case=case):
                row=self.row(case,binary)
                self.assertEqual([row[k]for k in('status','profile','callbacks','unchanged','live_allocs')],
                                 [status,profile,profile,1,0])

    def test_removed_exact_io_and_error_propagation_changes_are_detected(self):
        code=self.codes['current']
        controls=(
            ('short-load','status = ret_val == MAX_EEPROM_BIN_FILE_SIZE;','status = ret_val >= 0;','load-short',1),
            ('ignored-close','if (RtmpOSFileCloseChecked(srcf))','if ((RtmpOSFileCloseChecked(srcf), 0))','load-close-error',1),
            ('short-cache','cap->EEPROM_DEFAULT_BIN_SIZE >= MAX_EEPROM_BIN_FILE_SIZE','cap->EEPROM_DEFAULT_BIN_SIZE > 0','load-open-short-cache',1),
            ('ignored-setload','if (result != NDIS_STATUS_SUCCESS)\n\t\t\treturn FALSE;',
             'if (result != NDIS_STATUS_SUCCESS && 0)\n\t\t\treturn FALSE;','set-load-read-error',1),
        )
        for name,before,after,case,occurrence in controls:
            with self.subTest(control=name):
                self.assertGreaterEqual(code.count(before),occurrence)
                binary=self.compile(code.replace(before,after,occurrence),'mutant-'+name)
                self.assertNotEqual(self.row(case,binary),self.row(case))

    def test_gnu_exact_gate_compile_flags_and_all_defined_rows(self):
        compiler=shutil.which('gcc-16')or shutil.which('gcc')
        self.assertIsNotNone(compiler)
        probe=subprocess.run([compiler,'-dM','-E','-x','c','-'],input='',capture_output=True,text=True,timeout=10)
        self.assertEqual(probe.returncode,0);self.assertIn('#define __GNUC__ ',probe.stdout);self.assertNotIn('#define __clang__ ',probe.stdout)
        flags=['-std=gnu99','-Os','-static','-s','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-Wno-sign-compare']
        for profile,names in [('current',h.CASE_NAMES),('baseline',h.BASELINE_CASES),('disabled',h.DISABLED_CASES)]:
            c=self.base/('gnu-'+profile+'.c');c.write_text(self.codes[profile]);result=subprocess.run([compiler,*flags,'-c',str(c),'-o',str(self.base/('gnu-'+profile+'.o'))],capture_output=True,text=True,timeout=30)
            self.assertEqual((result.returncode,result.stderr),(0,''),result.stderr)
            binary=self.compile(self.codes[profile],'gnu-'+profile,compiler=compiler,sanitize=False)
            for case in names:self.assertEqual(self.row(case,binary),self.row(case,profile))

    def test_source_manifest_full_functions_baseline_and_stub_contracts(self):
        self.assertEqual((len(h.FUNCTION_SOURCES),len(h.BASELINE_FUNCTIONS)),(14,12))
        for name,item in h.actual_functions(self.texts).items():self.assertEqual(self.codes['current'].count(item['body']),1)
        for name,body in h.BASELINE_FUNCTIONS.items():self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),h.BASELINE_FUNCTIONS_SHA256[name])
        for name,body in h.DISABLED_STUBS.items():self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),h.DISABLED_STUB_SHA256[name])
        for text,opts in (({},{}),(self.texts,{'baseline':1}),(self.texts,{'baseline':True,'disabled_oracle':True})):
            with self.assertRaises(ValueError):h.generate_source(text,**opts)
        with mock.patch.dict(h.BASELINE_FUNCTIONS,{'rtmp_ee_load_from_bin':'wrong'}),self.assertRaises(ValueError):h.generate_source(self.texts)
        for case in h.DISABLED_CASES:
            row=self.row(case,'disabled');self.assertEqual((row['status'],row['trace'],row['opens']),(1,'',0));self.assertNotEqual(row,self.row(case))


if __name__=='__main__':unittest.main()
