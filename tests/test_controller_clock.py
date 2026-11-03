"""Actual MT7621 divider: arithmetic boundaries, old controls and mutations."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import controller_clock_harness as h
import controller_harness as controller

ROOT=Path(__file__).resolve().parents[1]


class ControllerClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-clock-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text() for k,v in h.SOURCE_PATHS.items()}
        cls.binaries={key:cls.compile(h.generate_source(cls.texts,baseline=old),key)
                      for key,old in [('current',False),('baseline',True)]}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @classmethod
    def compile(cls,source,name,extra=()):
        path=cls.directory/(name+'.c');binary=cls.directory/name;path.write_text(source)
        result=subprocess.run([shutil.which('clang') or shutil.which('cc'),'-std=gnu89','-O1',
            '-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',
            *extra,str(path),'-o',str(binary)],capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
        return binary

    def row(self,name,profile='current'):
        result=subprocess.run([str(self.binaries.get(profile,profile)),name],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
        return json.loads(result.stdout)

    def test_actual_divider_matches_all_fixed_boundaries_and_safe_reference(self):
        for name,clock,rate,value in h.INPUTS:
            with self.subTest(case=name):
                expected=4095 if not rate else min(4095,max(2,(clock+rate-1)//rate)-2)
                self.assertEqual(value,expected)
                self.assertEqual(self.row(name),dict(case=name,hclk=clock,rate=rate,divider=value))

    def test_fixed_old_body_reproduces_overflow_and_wrong_fast_encoding(self):
        byname={n:v for n,_,_,v in h.INPUTS}
        for name,value in h.BASELINE_EXPECTED.items():
            with self.subTest(case=name):self.assertEqual(self.row(name,'baseline')['divider'],value)
        for name in ('overflow-high','overflow-max','above-half','above-source','max-small'):
            self.assertNotEqual(h.BASELINE_EXPECTED[name],byname[name])

    def test_old_zero_request_is_an_undefined_behavior_control_not_a_pass_case(self):
        result=subprocess.run([str(self.binaries['baseline']),'zero-rate'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertIn('division by zero',result.stderr)

    def test_removed_arithmetic_and_minimum_fixes_are_detected(self):
        raw=h.generate_source(self.texts)
        for name,before,after,case in (
            ('sum-overflow','hclk_freq / freq + (hclk_freq % freq != 0)','(hclk_freq + freq - 1) / freq','overflow-high'),
            ('wrong-minimum','if (div < 2)\n\t\treturn 0;','if (div < 2)\n\t\treturn 2;','above-half')):
            with self.subTest(control=name):
                self.assertEqual(raw.count(before),1)
                binary=self.compile(raw.replace(before,after),name)
                self.assertNotEqual(self.row(case,binary),self.row(case))

    def test_source_constant_baseline_and_manifest_are_checked(self):
        raw=h.generate_source(self.texts);self.assertEqual(raw.count(h.function(self.texts['controller'])),1)
        for wrong in ({},dict(self.texts,extra=''),{'controller':self.texts['controller'].replace('0xfff','0xffe')}):
            with self.assertRaises(ValueError):h.generate_source(wrong)
        with self.assertRaises(ValueError):h.generate_source(self.texts,baseline=1)
        with mock.patch.object(h,'BASELINE_BODY',h.BASELINE_BODY+' '),self.assertRaises(ValueError):h.generate_source(self.texts,baseline=True)

    def test_setup_rejects_frequency_below_exact_hardware_minimum(self):
        body=controller.extract(self.texts['controller'],'mt7621_spi_setup')
        prefix='#include <stdint.h>\n#include <stdio.h>\ntypedef uint32_t u32;\n#define RS_CLK_SEL_M 0xfff\n#define EINVAL 22\n#define dev_info(...) ((void)0)\nstruct spi_device{u32 max_speed_hz;};\nstruct mt7621_spi{u32 hclk_freq;};static struct mt7621_spi instance;\n#define spidev_to_mt7621_spi(spi) (&instance)\n'
        main='int main(void){struct spi_device s;int a,b;instance.hclk_freq=220000000U;s.max_speed_hz=53697U;a=mt7621_spi_setup(&s);s.max_speed_hz=53698U;b=mt7621_spi_setup(&s);printf("%d %d %u\\n",a,b,s.max_speed_hz);return 0;}'
        binary=self.compile(prefix+body+'\n'+main,'exact-minimum-setup')
        result=subprocess.run([str(binary)],text=True,capture_output=True,timeout=5)
        self.assertEqual((result.returncode,result.stderr,result.stdout),(0,'','-22 0 53698\n'))

    def test_probe_advertises_ceiling_minimum_including_smallest_clock(self):
        body=controller.extract(self.texts['controller'],'mt7621_spi_probe')
        raw=controller.PREFIX+'\n'+controller.production_fragments(self.texts)+'\n'+controller.SEAMS+'\n'+body
        for clock,minimum in ((220000000,53698),(2,1)):
            main='int main(void){struct platform_device p;struct spi_master*m;int r;memset(&p,0,sizeof(p));rate='+str(clock)+'U;r=mt7621_spi_probe(&p);m=p.dev.data;printf("%d %u\\n",r,m->min_speed_hz);spi_unregister_master(m);return 0;}'
            binary=self.compile(raw+'\n'+main,'exact-minimum-probe-'+str(clock),
                                extra=('-Wno-unused-function','-Wno-unused-variable'))
            result=subprocess.run([str(binary)],text=True,capture_output=True,timeout=5)
            self.assertEqual((result.returncode,result.stderr,result.stdout),(0,'','0 '+str(minimum)+'\n'))


if __name__=='__main__':unittest.main()
