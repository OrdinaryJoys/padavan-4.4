"""Real checked Flash/MTD/QA/PA source functions; inert memory-backed MTD only."""
import hashlib,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
import flash_persist_harness as h
ROOT=Path(__file__).resolve().parents[1]
FLAGS=['-std=gnu89','-Os','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-Wno-unused-variable','-Wno-sign-compare','-Wno-unused-but-set-variable','-fno-strict-aliasing']


class FlashPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='flash-persist-native-');cls.base=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.codes={p:h.generate_source(cls.texts,baseline=p=='baseline',disabled_oracle=p=='disabled')for p in('current','baseline','disabled')}
        cls.binaries={p:cls.compile(c,p)for p,c in cls.codes.items()}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @classmethod
    def compile(cls,code,name,gcc=False):
        source=cls.base/(name+'.c');source.write_text(code);binary=source.with_suffix('')
        compiler=(shutil.which('gcc-16')or shutil.which('gcc'))if gcc else shutil.which('clang')
        if not compiler:raise AssertionError('Required compiler missing')
        extra=[]if gcc else['-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
        r=subprocess.run([compiler,*FLAGS,*extra,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=30)
        if r.returncode or r.stderr:raise AssertionError(r.stderr)
        return binary

    def row(self,case,profile='current'):
        result=subprocess.run([str(self.binaries.get(profile,profile)),case],capture_output=True,text=True,timeout=10)
        self.assertEqual((result.returncode,result.stderr),(0,''),result.stderr)
        return json.loads(result.stdout)

    def test_all_current_cases_have_typed_rows_and_balanced_MTD_and_heap_lifetimes(self):
        for name in h.CASE_NAMES:
            with self.subTest(case=name):
                row=self.row(name);self.assertEqual(len(row),30)
                for key,value in row.items():self.assertIs(type(value),str if key in('case','trace')else int)
                self.assertEqual((row['live_allocs'],row['bad_device'],row['bad_wait']),(0,0,0))
                self.assertEqual(row['get_calls']-row['put_calls'],int('get-error'in name))
                self.assertEqual(row['callbacks'],row['waits'])

    def test_word_errors_propagate_and_never_publish_staged_RAM(self):
        for suffix,status in [('read-error',-5),('short-read',-5),('erase-submit-error',-5),('erase-completion-error',-5),('write-error',-5),('short-write',-5),('stage-alloc-error',-12),('stage-alloc-null',-12),('backend-alloc-error',-12),('get-error',-19),('uninitialized',-22),('null-image',-22),('mode-mismatch',-22),('outside',-22),('cross-word',-22)]:
            with self.subTest(fault=suffix):
                row=self.row('word-'+suffix);self.assertEqual((row['result'],row['RAM_unchanged']),(status,1))
        row=self.row('word-ok');self.assertEqual((row['result'],row['word4'],row['RAM_unchanged'],row['writes']),(0,0x34,0,1))
        self.assertEqual(self.row('word-last-word')['result'],0)

    def test_range_boundaries_null_and_alias_inputs_are_validated_before_IO(self):
        for name in('range-null-input','range-cross-range','range-outside','range-max-length'):
            row=self.row(name);self.assertEqual((row['result'],row['get_calls'],row['RAM_unchanged']),(-22,0,1))
        for name in('range-zero','range-at-end-zero'):
            row=self.row(name);self.assertEqual((row['result'],row['allocs'],row['get_calls']),(0,0,0))
        self.assertEqual(self.row('range-alias')['result'],0)

    def test_raw_checked_API_returns_backend_errors_and_releases_devices(self):
        for name,status in [('raw-ok',0),('raw-null-input',-22),('raw-outside',-22),('raw-zero',0),('raw-erase-submit-error',-5),('raw-short-write',-5)]:
            with self.subTest(case=name):self.assertEqual(self.row(name)['result'],status)
        row=self.row('raw-zero');self.assertEqual((row['get_calls'],row['put_calls'],row['allocs'],row['writes']),(1,1,0,0))

    def test_full_image_commit_checks_exact_length_and_publishes_only_after_success(self):
        for name,status in [('commit-length-mismatch',-22),('commit-null-input',-22),('commit-backend-alloc-error',-12),('commit-write-error',-5)]:
            row=self.row(name);self.assertEqual((row['result'],row['RAM_unchanged']),(status,1))
        self.assertEqual((self.row('commit-ok')['result'],self.row('commit-ok')['RAM_unchanged']),(0,0))

    def test_manual_and_HQA_writeback_propagate_actual_IO_and_QA_cleanup(self):
        for name in('read-error','erase-submit-error','write-error','short-write','uninitialized'):
            row=self.row('writeback-'+name);self.assertEqual(row['result'],0)
            row=self.row('qa-'+name);self.assertEqual((row['result'],row['qa_status'],row['qa_flag']),(1,1,0))
        self.assertEqual(self.row('writeback-flash-ok')['result'],1)
        self.assertEqual((self.row('qa-ok')['result'],self.row('qa-ok')['qa_status'],self.row('qa-ok')['qa_flag']),(0,0,0))

    def test_BIN_to_Flash_writeback_uses_only_its_known_1024_byte_allocation(self):
        row=self.row('writeback-bin-bounded')
        self.assertEqual((row['result'],row['writes'],row['bad_device'],row['RAM_unchanged']),(1,1,0,1))
        # Compare the unsafe historical copy as source only.
        self.assertIn('rtmp_ee_flash_write_all(pAd);',h.BASELINE_FUNCTIONS['Set_EepromBufferWriteBack_Proc'])
        self.assertIn('get_dev_eeprom_size(pAd)',h.BASELINE_FUNCTIONS['rtmp_ee_flash_write_all'])

    def test_PA_trim_batches_exact_old_words_and_flag_in_one_commit(self):
        current=self.row('pa-flash-ok');old=self.row('pa-flash-ok','baseline')
        for key in('result','completion_bit','trim1','trim2','RAM_checksum','Flash_checksum'):self.assertEqual(current[key],old[key])
        self.assertEqual((current['result'],current['trim1'],current['trim2'],current['completion_bit']),(1,0x44,0xcc,1))
        self.assertEqual((current['writes'],old['writes']),(1,9))
        self.assertEqual((self.row('pa-repeat')['writes'],self.row('pa-repeat','baseline')['writes']),(2,18))
        current=self.row('pa-bin-ok');old=self.row('pa-bin-ok','baseline')
        self.assertEqual((current['RAM_checksum'],current['completion_bit'],current['writes']),(old['RAM_checksum'],1,0))

    def test_PA_trim_rejects_all_failure_states_before_publishing_completion(self):
        for name in('pa-read-error','pa-short-read','pa-erase-submit-error','pa-erase-completion-error','pa-write-error','pa-short-write','pa-stage-alloc-error','pa-stage-alloc-null','pa-backend-alloc-error','pa-uninitialized','pa-bin-uninitialized','pa-null-input','pa-null-image','pa-mode-mismatch','pa-invalid-mode','pa-nic-gone','pa-nonmt','pa-small-profile'):
            with self.subTest(case=name):
                row=self.row(name);self.assertEqual((row['result'],row['RAM_unchanged'],row['completion_bit']),(0,1,0))
        row=self.row('pa-write-error');self.assertEqual(row['Flash_unchanged'],0) # partial physical writes cannot be rolled back

    def test_checked_macro_preserves_status_while_legacy_interface_stays_unchanged(self):
        self.assertEqual(self.row('macro-ok')['result'],0)
        self.assertEqual(self.row('macro-write-error')['result'],-5)
        self.assertEqual(self.row('macro-write-error','baseline')['result'],0)
        for case in('macro-missing-op','macro-null-adapter'):
            row=self.row(case);self.assertEqual((row['result'],row['allocs'],row['get_calls']),(-1,0,0))
        for name in('RtmpFlashWrite','rtmp_ee_flash_write_all'):
            self.assertEqual(h.actual_functions(self.texts)[name]['body'],h.BASELINE_FUNCTIONS[name])
        self.assertEqual(h.source_macro(self.texts['chip_header'],'RT28xx_EEPROM_WRITE16'),h.BASELINE_LEGACY_MACRO)

    def test_unsupported_backend_refuses_checked_persistence_without_legacy_success_fabrication(self):
        code=self.codes['current'].replace('#define CONFIG_WIFI_MTD 1','#undef CONFIG_WIFI_MTD')
        binary=self.compile(code,'unsupported')
        row=self.row('raw-ok',binary);self.assertEqual((row['result'],row['writes'],row['get_calls']),(-95,0,0))

    def test_bulk_chunk_protocol_stages_middle_and_commits_last_once(self):
        middle=self.row('bulk-sixteen-flash-ok')
        self.assertEqual((middle['result'],middle['writes'],middle['RAM_unchanged'],middle['Flash_unchanged']),(0,0,0,1))
        last=self.row('bulk-end-flash-ok');old=self.row('bulk-end-flash-ok','baseline')
        self.assertEqual((last['result'],last['writes'],last['RAM_unchanged'],last['qa_status']),(0,1,0,0))
        self.assertEqual((last['RAM_checksum'],last['Flash_checksum']),(old['RAM_checksum'],old['Flash_checksum']))
        self.assertEqual(self.row('bulk-sixteen-bin-ok')['writes'],0)

    def test_bulk_backend_failures_report_failure_and_preserve_current_stage(self):
        for case in ('bulk-end-write-error','bulk-read-error','bulk-short-read','bulk-erase-submit-error',
                     'bulk-erase-completion-error','bulk-write-error','bulk-short-write',
                     'bulk-stage-alloc-error','bulk-stage-alloc-null','bulk-backend-alloc-error'):
            with self.subTest(case=case):
                row=self.row(case)
                self.assertEqual((row['result'],row['qa_status'],row['qa_length'],row['RAM_unchanged']),(1,1,2,1))
        self.assertEqual(self.row('bulk-flash-ok')['writes'],1)

    def test_image_API_compiles_without_Flash_writer_and_keeps_BIN_capacity(self):
        first=h.actual_functions(self.texts)[h.BODY_ORDER[0]]['body']
        self.assertEqual(self.codes['current'].count(first),1)
        prefix=self.codes['current'].split(first,1)[0].replace('#define RTMP_FLASH_SUPPORT 1','#undef RTMP_FLASH_SUPPORT')
        names=('rtmp_ee_flash_image_capacity','rtmp_ee_flash_write_image_checked','rtmp_ee_flash_write_all_checked')
        bodies='\n'.join(h.actual_functions(self.texts)[n]['body']for n in names)
        main='int main(void){RTMP_ADAPTER a;UCHAR image[1024];memset(&a,0,sizeof(a));memset(image,0x55,sizeof(image));cap.ee_inited=1;a.EEPROMImage=image;a.E2pAccessMode=a.E2pCtrl.e2pCurMode=4;return !(rtmp_ee_flash_image_capacity(&a)==1024&&rtmp_ee_flash_write_all_checked(&a)==-95&&image[0]==0x55&&get_calls==0);}'
        binary=self.compile(prefix+'\n'+bodies+'\n'+main,'no-flash-image-api')
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'',''))

    def test_fixed_baselines_and_disabled_bodies_reveal_false_success(self):
        for name in h.BASELINE_CASES:
            if name in('pa-flash-ok','pa-bin-ok')or name.startswith('bulk-'):continue
            with self.subTest(case=name):self.assertNotEqual(self.row(name),self.row(name,'baseline'))
        for name in h.DISABLED_CASES:
            row=self.row(name,'disabled');self.assertEqual((row['allocs'],row['get_calls'],row['writes']),(0,0,0));self.assertNotEqual(row,self.row(name))

    def test_removed_error_and_publication_guards_are_detected(self):
        controls=[('hide-errno','return flash_write(hdev_ctrl, p, a, b);','return (flash_write(hdev_ctrl, p, a, b), 0);','word-write-error'),('premature-RAM','if (!status && image != pAd->EEPROMImage)','if (image != pAd->EEPROMImage)','word-write-error'),('hide-writeback','return rtmp_ee_flash_write_all_checked(pAd) == 0;','return (rtmp_ee_flash_write_all_checked(pAd), TRUE);','qa-write-error'),('hide-PA','status = rtmp_ee_flash_write_image_checked(pAd, image, image_size);','status = (rtmp_ee_flash_write_image_checked(pAd, image, image_size), 0);','pa-write-error')]
        for name,before,after,case in controls:
            with self.subTest(control=name):
                self.assertEqual(self.codes['current'].count(before),1);binary=self.compile(self.codes['current'].replace(before,after),name)
                self.assertNotEqual(self.row(case,binary),self.row(case))

    def test_GNU89_exact_flags_all_fixed_rows_and_Git_bodies_match(self):
        compiler=shutil.which('gcc-16')or shutil.which('gcc');macros=subprocess.run([compiler,'-dM','-E','-x','c','-'],input='',capture_output=True,text=True)
        self.assertNotIn('#define __clang__ ',macros.stdout)
        for profile,names in [('current',h.CASE_NAMES),('baseline',h.BASELINE_CASES),('disabled',h.DISABLED_CASES)]:
            binary=self.compile(self.codes[profile],'gnu-'+profile,gcc=True)
            src=self.base/('gnu-'+profile+'.c');result=subprocess.run([compiler,*FLAGS,'-static','-s','-c',str(src),'-o',str(src.with_suffix('.o'))],capture_output=True,text=True,timeout=30)
            self.assertEqual((result.returncode,result.stderr),(0,''),result.stderr)
            for name in names:self.assertEqual(self.row(name,binary),self.row(name,profile))
        self.assertEqual((len(h.FUNCTION_SOURCES),len(h.BASELINE_FUNCTIONS)),(19,15))
        old={}
        for name,body in h.BASELINE_FUNCTIONS.items():
            key=h.FUNCTION_SOURCES[name]
            if key not in old:old[key]=subprocess.check_output(['git','-C',str(ROOT),'show',h.BASELINE_COMMIT+':'+h.SOURCE_PATHS[key]],text=True)
            self.assertEqual(h.function(old[key],name),body);self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),h.BASELINE_FUNCTIONS_SHA256[name])
        for key,declarations in h.ABI_PROTOTYPES.items():
            for declaration in declarations:
                self.assertEqual(self.texts[key].count(declaration),1)
                damaged=dict(self.texts);damaged[key]=damaged[key].replace(declaration,declaration.replace('INT ','VOID ',1))
                with self.assertRaises(ValueError):h.generate_source(damaged)
        with mock.patch.dict(h.BASELINE_FUNCTIONS,{'RtmpFlashWrite':'changed'}),self.assertRaises(ValueError):h.generate_source(self.texts)
