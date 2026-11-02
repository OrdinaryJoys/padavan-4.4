#!/usr/bin/env python3
"""Winbond optional SR3 adjustment: actual helper, ready, scan and probe bodies."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import sr3_startup_harness as harness

ROOT = Path(__file__).resolve().parents[1]

class SR3StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-sr3-startup-')
        cls.base=Path(cls.temp.name).resolve()
        cls.texts={key:(ROOT/path).read_text() for key,path in harness.SOURCE_PATHS.items()}
        cls.expected=dict(harness.CASES)
        cls.binaries={}
        for name,baseline in (('current',False),('baseline',True)):
            cls.binaries[name]=cls.compile(cls.texts,name,baseline=baseline)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls,texts,name,baseline=False,compiler=None,standard='gnu99'):
        c=cls.base/(name+'.c');binary=cls.base/name
        c.write_text(harness.generate_source(texts,baseline=baseline))
        command=[compiler or shutil.which('clang') or shutil.which('cc'),
                 '-std='+standard,'-O1','-g','-Wall','-Wextra','-Werror',
                 '-Wno-unused-function','-Wno-sign-compare']
        if compiler is None:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        built=subprocess.run(command+[str(c),'-o',str(binary)],capture_output=True,text=True,timeout=60)
        if built.returncode:raise AssertionError(built.stderr)
        return binary

    def run_case(self,name,label='current',binary=None):
        run=subprocess.run([str(binary or self.binaries[label]),name],capture_output=True,text=True,timeout=3)
        self.assertEqual(run.returncode,0,(name,run.stderr))
        self.assertEqual(run.stderr,'',(name,run.stderr))
        return json.loads(run.stdout)

    def check(self,names):
        for name in names:
            with self.subTest(case=name):
                self.assertEqual(self.run_case(name),self.expected[name])

    def test_normal_adjustment_waits_and_preserves_all_non_drv_bits(self):
        self.check(('normal','preserve-other-bits','preserve-all-other-bits'))

    def test_no_change_non_winbond_and_optional_unsupported_read_remain_compatible(self):
        names=('unchanged-00','unchanged-20','unchanged-40','non-winbond','sr3-unsupported','sr3-read-error')
        self.check(names)
        for name in names:
            with self.subTest(baseline_case=name):
                self.assertEqual(self.run_case(name,'baseline'),self.expected[name])

    def test_wren_error_never_sends_status_write_including_accepted_wren(self):
        self.check(('wren-error','wren-error-accepted'))
        self.assertEqual(self.run_case('wren-error-accepted')['wel'],1)
        self.assertEqual(self.run_case('wren-error-accepted')['busy'],0)

    def test_optional_write_errors_continue_only_after_positive_ready(self):
        self.check(('write-error-rejected','write-error-accepted'))

    def test_preexisting_busy_is_settled_before_wren(self):
        self.check(('initial-busy','pre-ready-error','pre-ready-timeout'))

    def test_ready_reloads_sr3_and_rechecks_drv_before_writing(self):
        self.check(('busy-prior-sr3-other-bits','busy-prior-sr3-no-change','fresh-sr3-read-error'))
        changed=self.run_case('busy-prior-sr3-other-bits')
        self.assertEqual(changed['write_value'] & ~0x60, 0xe0 & ~0x60)
        self.assertEqual(changed['sr3_after'], 0xc0)
        self.assertEqual(self.run_case('busy-prior-sr3-no-change')['write_calls'],0)
        self.assertEqual(self.run_case('fresh-sr3-read-error')['write_calls'],0)

    def test_write_attempt_requires_ready_even_after_transport_error(self):
        self.check(('post-ready-error','post-ready-timeout',
                    'write-error-accepted-ready-error','write-error-accepted-ready-timeout',
                    'write-error-rejected-ready-error'))

    def test_existing_ready_deadline_wrap_and_fsr_paths_are_preserved(self):
        self.check(('deadline-wrap-timeout','fsr-normal','fsr-error','fsr-delayed'))

    def test_actual_old_helper_registers_busy_chip_and_sends_write_after_wren_error(self):
        for name,expected in harness.BASELINE_CASES:
            with self.subTest(case=name):
                old=self.run_case(name,'baseline')
                self.assertEqual(old,expected)
                self.assertNotEqual(old,self.expected[name])
        self.assertEqual(self.run_case('normal','baseline')['registration_busy'],1)
        self.assertEqual(self.run_case('wren-error','baseline')['write_calls'],1)

    def test_actual_baseline_bytes_and_exact_two_changed_functions_are_pinned(self):
        self.assertEqual(set(harness.BASELINE_FUNCTIONS),set(harness.BASELINE_FUNCTIONS_SHA256))
        for name,body in harness.BASELINE_FUNCTIONS.items():
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),harness.BASELINE_FUNCTIONS_SHA256[name])
        actual=harness.actual_functions(self.texts)
        changed={name for name,row in actual.items() if row['body']!=harness.BASELINE_FUNCTIONS[name]}
        self.assertEqual(changed,{'spi_set_wb_drive_strength','spi_nor_scan'})

    def test_all_actual_exported_functions_and_critical_macros_are_bound(self):
        generated=harness.generate_source(self.texts)
        actual=harness.actual_functions(self.texts)
        self.assertEqual(len(actual),14)
        for name,row in actual.items():
            self.assertEqual(generated.count(row['body']),1,name)
        for key,name,value in [('nor','DEFAULT_READY_WAIT_JIFFIES','(41UL * HZ)'),
                               ('nor_header','SR_WIP','BIT(1)'),
                               ('nor_header','SNOR_MFR_WINBOND','0xee'),
                               ('spi_header','SPI_RX_QUAD','0x1000')]:
            changed=dict(self.texts)
            old=harness._define(changed[key],name)
            changed[key]=changed[key].replace(old,value,1) if name=='DEFAULT_READY_WAIT_JIFFIES' else changed[key]
            if name!='DEFAULT_READY_WAIT_JIFFIES':
                import re
                changed[key]=re.sub(r'(^#define[ \t]+'+name+r'[ \t]+)[^\n]+',
                                    lambda m:m.group(1)+value,changed[key],count=1,flags=re.M)
            with self.subTest(macro=name),self.assertRaises(ValueError):
                harness.generate_source(changed)
        bad=dict(self.texts);bad.pop('nor_header')
        with self.assertRaises(ValueError):harness.generate_source(bad)

    def variant(self,name,old,new):
        texts=dict(self.texts);body=harness.extract(texts['nor'],'spi_set_wb_drive_strength')
        self.assertEqual(body.count(old),1)
        changed=body.replace(old,new)
        texts['nor']=texts['nor'].replace(body,changed,1)
        return self.compile(texts,name)

    def test_removed_post_ready_negative_control_registers_busy_flash(self):
        bad=self.variant('missing-post-ready','ready = spi_nor_wait_till_ready(nor);','ready = 0;')
        row=self.run_case('normal',binary=bad)
        self.assertEqual(row['registration_busy'],1)
        self.assertNotEqual(row,self.expected['normal'])

    def test_removed_pre_ready_negative_control_sends_wren_while_busy(self):
        old='ret = spi_nor_wait_till_ready(nor);\n\t\tif (ret)\n\t\t\treturn ret;'
        bad=self.variant('missing-pre-ready',old,'ret = 0;')
        row=self.run_case('initial-busy',binary=bad)
        self.assertEqual((row['wren_busy'],row['write_busy']),(1,1))
        self.assertNotEqual(row,self.expected['initial-busy'])

    def test_missing_fresh_sample_negative_control_loses_new_sr3_control_bits(self):
        old='ret = nor->read_reg(nor, 0x15, &code, 1);\n\t\tif (ret < 0 || (code & 0x60) != 0x60)\n\t\t\treturn 0;'
        bad=self.variant('missing-fresh-sr3',old,'/* Deliberate stale-sample negative control. */')
        row=self.run_case('busy-prior-sr3-other-bits',binary=bad)
        self.assertEqual((row['write_value'],row['sr3_after']),(0x40,0x40))
        self.assertNotEqual(row,self.expected['busy-prior-sr3-other-bits'])
        row=self.run_case('busy-prior-sr3-no-change',binary=bad)
        self.assertEqual(row['write_calls'],1)
        self.assertNotEqual(row,self.expected['busy-prior-sr3-no-change'])

    def test_ignored_scan_error_negative_control_exposes_busy_mtd(self):
        texts=dict(self.texts)
        old='ret = spi_set_wb_drive_strength(nor);\n\t\tif (ret)\n\t\t\treturn ret;'
        self.assertEqual(texts['nor'].count(old),1)
        texts['nor']=texts['nor'].replace(old,'spi_set_wb_drive_strength(nor);')
        bad=self.compile(texts,'ignored-scan-error')
        row=self.run_case('post-ready-timeout',binary=bad)
        self.assertEqual((row['result'],row['registration_busy']),(0,1))
        self.assertNotEqual(row,self.expected['post-ready-timeout'])

    def test_gcc_gnu89_strict_compile_and_all_current_cases(self):
        gcc=shutil.which('gcc-16') or shutil.which('gcc')
        if not gcc:raise RuntimeError('GCC is required')
        binary=self.compile(self.texts,'gcc-gnu89',compiler=gcc,standard='gnu89')
        for name,expected in harness.CASES:
            with self.subTest(case=name):
                self.assertEqual(self.run_case(name,binary=binary),expected)

if __name__=='__main__':unittest.main()
