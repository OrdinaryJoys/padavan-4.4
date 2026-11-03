"""Configured MT7615 startup preserves Factory on failed calibration reads."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import wifi_factory_harness as h

ROOT=Path(__file__).resolve().parents[1]


class WifiFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-wifi-factory-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text() for k,v in h.SOURCE_PATHS.items()}
        cls.source=h.generate_source(cls.texts)
        cls.binaries={name:cls.compile(h.generate_source(cls.texts,**options),name)
                      for name,options in [('current',{}),('baseline',{'baseline':True}),
                                           ('disabled',{'disabled_oracle':True})]}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @classmethod
    def compile(cls,source,name):
        path=cls.directory/(name+'.c');binary=cls.directory/name;path.write_text(source)
        result=subprocess.run([shutil.which('clang') or shutil.which('cc'),'-std=gnu89','-O1',
            '-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter',
            '-fsanitize=address,undefined','-fno-sanitize-recover=undefined',str(path),'-o',str(binary)],
            capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
        return binary

    def row(self,case,profile='current'):
        result=subprocess.run([str(self.binaries.get(profile,profile)),case],
                              capture_output=True,text=True,timeout=5)
        self.assertEqual((result.returncode,result.stderr),(0,''),result.stderr)
        return json.loads(result.stdout)

    def test_all_current_paths_keep_read_failures_out_of_parser_and_factory(self):
        for case in h.CASE_NAMES:
            with self.subTest(case=case):
                row=self.row(case)
                failed=any(n in case for n in ('error','short','allocation-failure','reset-failure'))
                self.assertEqual(row['status'],int(failed))
                writes=case in ('direct-read-erased','boot-read-erased','direct-default-write-error',
                                'boot-default-write-error','direct-default-file-ok','direct-default-long-cache-ok')
                self.assertEqual(row['factorywrites'],int(writes));self.assertEqual(row['fsdepth'],0)
                if failed:
                    self.assertEqual([row[k] for k in ('parse','radio','asic','capinit','image','mode','source','calibrated')],[0]*8)
                    self.assertEqual(row['frees'],row['allocs']-int('allocation-failure' in case)+int('existing' in case))
                self.assertTrue(all(type(value) is (str if key in ('case','trace') else int)
                                    for key,value in row.items()))

    def test_fixed_old_read_failure_reproduces_default_factory_writeback(self):
        for case in ('direct-read-error','direct-read-short','direct-existing-error',
                     'boot-read-error','ate-read-error','testmode-read-error'):
            with self.subTest(case=case):
                old=self.row(case,'baseline');new=self.row(case)
                self.assertEqual((old['status'],old['defaults'],old['factorywrites']),(0,1,1))
                self.assertEqual((new['status'],new['defaults'],new['factorywrites']),(1,0,0))
        old=self.row('boot-allocation-failure','baseline')
        self.assertEqual((old['status'],old['image'],old['radio'],old['asic']),(0,0,1,1))

    def test_successful_reads_keep_calibration_and_do_not_write_factory(self):
        for case in ('direct-read-ok','boot-read-ok','ate-read-ok','testmode-read-ok'):
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual([row[k] for k in ('status','factorywrites','defaults')],[0,0,0])
                self.assertEqual([row[k] for k in ('capinit','image','calibrated')],[1,1,1])
                self.assertEqual([row[k] for k in ('mode','source')],[2,2])

    def test_proven_successful_read_of_invalid_eeprom_keeps_existing_default_policy(self):
        for case in ('direct-read-erased','boot-read-erased'):
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual((row['status'],row['reads'],row['defaults'],row['factorywrites']),(0,1,1,1))
                self.assertLess(row['trace'].index('read'),row['trace'].index('factory-write'))

    def test_failed_default_writeback_does_not_report_success_or_start_radio(self):
        for case in ('direct-default-write-error','boot-default-write-error'):
            with self.subTest(case=case):
                old=self.row(case,'baseline');new=self.row(case)
                self.assertEqual((old['status'],old['factorywrites']),(0,1))
                self.assertEqual((new['status'],new['factorywrites']),(1,1))
                self.assertEqual([new[k] for k in ('image','capinit','calibrated','parse','radio','asic')],[0]*6)

    def test_default_loader_restores_fs_context_and_checks_exact_file_and_cache(self):
        for case in ('direct-default-file-error','direct-default-short-file-error','direct-default-close-error',
                     'direct-default-missing-error','direct-default-short-cache-error',
                     'direct-default-invalid-id-error','direct-default-empty-path-error',
                     'direct-default-oversized-read-error'):
            with self.subTest(case=case):
                row=self.row(case);old=self.row(case,'baseline')
                self.assertEqual((row['status'],row['factorywrites'],row['fsdepth']),(1,0,0))
                self.assertNotEqual(old,row)
                if row['filereads']:self.assertEqual(row['filecloses'],1)
        for case in ('direct-read-error','direct-default-missing-error'):
            self.assertEqual(self.row(case,'baseline')['fsdepth'],1)
        for case in ('direct-default-file-ok','direct-default-long-cache-ok'):
            row=self.row(case);self.assertEqual((row['status'],row['factorywrites'],row['fsdepth']),(0,1,0))

    def test_default_buffer_overflow_old_control_is_excluded_from_target_baselines(self):
        result=subprocess.run([str(self.binaries['baseline']),'direct-small-buffer-error'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertIn('heap-buffer-overflow',result.stderr)
        self.assertEqual(self.row('direct-small-buffer-error')['factorywrites'],0)
        self.assertNotIn('direct-small-buffer-error',h.BASELINE_CASES)

    def test_normal_boot_checks_init_before_radio_and_hardware(self):
        good=self.row('boot-read-ok');bad=self.row('boot-read-error')
        self.assertEqual((good['parse'],good['radio'],good['asic'],good['exits']),(1,1,1,0))
        self.assertEqual((bad['parse'],bad['radio'],bad['asic'],bad['exits']),(0,0,0,1))
        self.assertEqual(bad['trace'],'hook,alloc,read,free,exit')

    def test_both_ate_consumers_stop_before_asic_after_failed_read(self):
        for prefix in ('ate','testmode'):
            with self.subTest(consumer=prefix):
                self.assertEqual(self.row(prefix+'-read-ok')['asic'],1)
                self.assertEqual(self.row(prefix+'-read-error')['asic'],0)

    def test_removing_read_and_consumer_guards_is_detected(self):
        controls=(
            ('drop-read-check','if (read_status) {','if (0) {','direct-read-error'),
            ('drop-eeprom-check','if (ops->eeinit(pAd) != NDIS_STATUS_SUCCESS)\n\t\t\treturn FALSE;',
             'ops->eeinit(pAd);','boot-read-error'),
            ('drop-boot-check','if (!NICReadEEPROMParameters(pAd, (RTMP_STRING *)mac))\n\t\treturn NDIS_STATUS_FAILURE;',
             'NICReadEEPROMParameters(pAd, (RTMP_STRING *)mac);','boot-read-error'),
            ('drop-fs-restore','RtmpOSFSInfoChange(&osFsInfo, FALSE);','(void)osFsInfo;','direct-read-erased'),
            ('allow-short-file','if (retval != EEPROM_SIZE) {','if (retval < 0) {','direct-default-short-file-error'),
            ('allow-short-cache','copy_size >= EEPROM_SIZE &&','1 &&','direct-default-short-cache-error'),
            ('ignore-close-error','status = NDIS_STATUS_FAILURE;\n\t\t\t\tMTWF_LOG','status = NDIS_STATUS_SUCCESS;\n\t\t\t\tMTWF_LOG','direct-default-close-error'),
            ('drop-default-id-check','/* Validate the loaded buffer before replacing physical calibration. */\n\t\tif (validFlashEepromID(pAd) == FALSE)',
             '/* Validate the loaded buffer before replacing physical calibration. */\n\t\tif (0)','direct-default-invalid-id-error'),
            ('ignore-default-write-result','if (mt_mtd_write_nm_wifi("Factory", get_dev_eeprom_offset(pAd),\n\t\t\tget_dev_eeprom_size(pAd), pAd->EEPROMImage))',
             'if ((mt_mtd_write_nm_wifi("Factory", get_dev_eeprom_offset(pAd),\n\t\t\tget_dev_eeprom_size(pAd), pAd->EEPROMImage), 0))','direct-default-write-error'),
        )
        for name,before,after,case in controls:
            with self.subTest(control=name):
                self.assertEqual(self.source.count(before),1)
                binary=self.compile(self.source.replace(before,after),name)
                self.assertNotEqual(self.row(case,binary),self.row(case))
        before='if (!NICReadEEPROMParameters(pAd, NULL))\n\t\treturn NDIS_STATUS_FAILURE;'
        self.assertEqual(self.source.count(before),2)
        for index,case in enumerate(('ate-read-error','testmode-read-error')):
            pieces=self.source.split(before)
            pieces[index]+='NICReadEEPROMParameters(pAd, NULL);'
            mutated=before.join(pieces[:index+1])+''.join(pieces[index+1:]) if index==1 else pieces[0]+pieces[1]+before+pieces[2]
            binary=self.compile(mutated,'drop-ate-check-'+str(index))
            self.assertNotEqual(self.row(case,binary),self.row(case))

    def test_disabled_success_status_cannot_substitute_for_read_execution(self):
        for case in h.DISABLED_CASES:
            with self.subTest(case=case):
                row=self.row(case,'disabled')
                self.assertEqual((row['status'],row['reads'],row['factorywrites'],row['trace']),(0,0,0,''))
                self.assertNotEqual(row,self.row(case))
        self.assertEqual((len(h.CASE_NAMES),len(h.BASELINE_CASES),len(h.DISABLED_CASES)),(29,18,2))

    def test_full_body_binding_and_early_projections_are_explicit(self):
        functions=h.actual_functions(self.texts);sections=h.execution_sections(functions)
        self.assertEqual(len(functions),13);self.assertEqual(set(sections),set(h.PROJECTED_FUNCTIONS))
        fragments=h.executed_fragments(functions)
        self.assertEqual(tuple(fragments),h.BODY_ORDER)
        for name,item in functions.items():
            with self.subTest(function=name):
                if name in h.PROJECTED_FUNCTIONS:
                    self.assertEqual(item['execution'],'early-section')
                    self.assertIn(sections[name],item['body']);self.assertIn(sections[name],fragments[name])
                    self.assertNotIn(item['body'],self.source)
                else:
                    self.assertEqual(item['execution'],'whole-function');self.assertIn(item['body'],self.source)
        for name,body in h.BASELINE_FUNCTIONS.items():
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),h.BASELINE_FUNCTIONS_SHA256[name])
        for texts,options in (({},{}),(self.texts,{'baseline':1}),
                              (self.texts,{'baseline':True,'disabled_oracle':True})):
            with self.assertRaises(ValueError):h.generate_source(texts,**options)
        with mock.patch.dict(h.BASELINE_FUNCTIONS,{'rtmp_nv_init':'wrong'}):
            with self.assertRaises(ValueError):h.generate_source(self.texts)

    def test_legacy_ate_stop_propagates_leave_failure_before_resume(self):
        fixture=ROOT/'tests/fixtures/wifi-factory/6e-MT_ATEStop.c'
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),
                         'b86c6a4b6b693d3257ae21bda6c8e90e6cf0100ed036114bddfcef6ecbf5fdcc')
        current=h.function(self.texts['wifi_ate'],'MT_ATEStop')
        old=fixture.read_text()
        prefix=r'''
#include <stdio.h>
#define NDIS_STATUS_SUCCESS 0
typedef struct {int unused;} RTMP_ADAPTER;
static int code,resumed;
struct ops {int(*ate_leave)(RTMP_ADAPTER*);};
static int leave(RTMP_ADAPTER*p){(void)p;return code;}
'''
        for name,body,expected in [('current',current,'0 1\n1 0\n-5 0\n'),
                                   ('baseline',old,'0 1\n0 1\n0 1\n')]:
            start=body.index('\tif (if_ops->ate_leave)')
            end=body.index('\n\tAsicSetRxFilter(pAd);',start)
            block=body[start:end]
            source=prefix+'\nstatic int invoke(void){RTMP_ADAPTER a,*pAd=&a;struct ops value={leave},*if_ops=&value;int Ret=0;\n'+block+'\nresumed++;return Ret;}\n'
            source+='int main(void){int i,result,codes[3]={0,1,-5};for(i=0;i<3;i++){code=codes[i];resumed=0;result=invoke();printf("%d %d\\n",result,resumed);}return 0;}'
            binary=self.compile(source,'legacy-stop-'+name)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=5)
            self.assertEqual((result.returncode,result.stderr,result.stdout),(0,'',expected))


if __name__=='__main__':unittest.main()
