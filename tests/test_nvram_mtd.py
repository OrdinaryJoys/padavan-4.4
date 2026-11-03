"""Actual NVRAM MTD helpers: range, exact IO and erase callback lifetime."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import nvram_mtd_harness as h

ROOT = Path(__file__).resolve().parents[1]


class NvramMtdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-nvram-mtd-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {k:(ROOT/v).read_text() for k,v in h.SOURCE_PATHS.items()}
        cls.source = h.generate_source(cls.texts)
        cls.binaries = {name:cls.compile(h.generate_source(cls.texts,**options),name)
                        for name,options in [('current',{}),('baseline',{'baseline':True}),
                                             ('disabled',{'disabled_oracle':True})]}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, source, name, extra=()):
        path = cls.directory/(name+'.c');binary = cls.directory/name;path.write_text(source)
        result = subprocess.run([shutil.which('clang') or shutil.which('cc'),'-std=gnu89','-O1',
            '-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined',
            '-fno-sanitize-recover=undefined',*extra,str(path),'-o',str(binary)],
            capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
        return binary

    def run_case(self, case, profile='current'):
        result = subprocess.run([str(self.binaries.get(profile,profile)),case],
                                capture_output=True,text=True,timeout=5)
        self.assertEqual((result.returncode,result.stderr),(0,''),result.stderr)
        return json.loads(result.stdout)

    def test_all_current_boundaries_return_expected_status_and_release_resources(self):
        errors = {
            'write-negative':-22,'write-past-block':-22,'write-overflow':-22,
            'write-too-large':-7,'write-null':-22,'write-name-null':-22,
            'write-zero-erase':-7,'write-small-device':-22,'write-lookup-failure':-19,
            'write-allocation-failure':-12,'write-read-error':-74,'write-short-read':-5,
            'write-erase-error':-5,'write-erase-failed-state':-5,'write-async-failed':-5,
            'write-io-error':-30,'write-short-io':-5,'read-negative':-22,
            'read-overflow':-22,'read-past-end':-22,'read-short':-5,
            'read-io-error':-74,'read-lookup-failure':-19,
        }
        self.assertEqual(len(h.CASE_NAMES),32)
        for case in h.CASE_NAMES:
            with self.subTest(case=case):
                row = self.run_case(case)
                self.assertEqual(row['result'],errors.get(case,0));self.assertEqual(row['case'],case)
                self.assertTrue(all(type(value) is (str if key in ('case','trace') else int)
                                    for key,value in row.items()))
                self.assertEqual(row['gets']-row['puts'],int('lookup-failure' in case))
                self.assertEqual(row['allocs']-row['frees'],int(case=='write-allocation-failure'))
                self.assertEqual(row['premature'],0)

    def test_invalid_ranges_and_zero_length_never_allocate_read_or_erase(self):
        for case in ('write-negative','write-past-block','write-overflow','write-too-large',
                     'write-zero','write-zero-end','write-null','write-name-null',
                     'write-zero-erase','write-small-device','read-negative','read-overflow',
                     'read-past-end','read-zero-end'):
            with self.subTest(case=case):
                row=self.run_case(case)
                self.assertEqual([row[k] for k in ('allocs','reads','erases','writes','waits')],[0]*5)
                self.assertEqual([row[k] for k in ('byte0','byte8','byte15')],[0,8,15])

    def test_in_block_offsets_and_shared_environment_bytes_are_preserved(self):
        expected={'write-ok':[160,8,15], 'write-offset':[0,160,15], 'write-boundary':[0,8,163]}
        for case,values in expected.items():
            with self.subTest(case=case):
                row=self.run_case(case)
                self.assertEqual([row[k] for k in ('byte0','byte8','byte15')],values)
                self.assertEqual(row['trace'],'get,alloc,read,erase,complete,wait,write,free,put')

    def test_short_preservation_read_stops_before_erase_and_uninitialized_bytes(self):
        row=self.run_case('write-short-read')
        self.assertEqual((row['result'],row['erases'],row['writes'],row['byte15']),(-5,0,0,15))
        old=self.run_case('write-short-read','baseline')
        self.assertEqual((old['result'],old['erases'],old['writes'],old['byte15']),(0,1,1,204))

    def test_short_write_and_short_public_read_do_not_report_commit_success(self):
        for case in ('write-short-io','read-short'):
            with self.subTest(case=case):
                self.assertEqual(self.run_case(case)['result'],-5)
                self.assertEqual(self.run_case(case,'baseline')['result'],0)

    def test_sync_and_async_erase_ownership_precedes_write_and_checks_completion_state(self):
        for case in ('write-async','write-async-failed'):
            with self.subTest(case=case):
                row=self.run_case(case);self.assertEqual(row['waits'],1)
                self.assertLess(row['trace'].index('wait'),row['trace'].index('complete'))
                if case=='write-async':
                    self.assertLess(row['trace'].index('complete'),row['trace'].index('write'));self.assertEqual(row['writes'],1)
                else:self.assertEqual((row['writes'],row['result']),(0,-5))
                self.assertEqual(self.run_case(case,'baseline')['premature'],1)
        failed=self.run_case('write-erase-failed-state');self.assertEqual((failed['writes'],failed['result']),(0,-5))

    def test_fixed_old_range_overrun_is_a_separate_asan_failure_control(self):
        result=subprocess.run([str(self.binaries['baseline']),'write-overrun-control'],
                              capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertIn('heap-buffer-overflow',result.stderr)
        current=self.run_case('write-overrun-control')
        self.assertEqual((current['result'],current['erases'],current['writes']),(-22,0,0))
        self.assertNotIn('write-overrun-control',h.CASE_NAMES+h.BASELINE_CASES+h.DISABLED_CASES)

    def test_removed_length_and_wait_guards_change_observed_behavior(self):
        mutations=(
            ('short-read','if (rdlen != mtd->erasesize) {','if (0) {','write-short-read'),
            ('short-write','if (!ret && wrlen != mtd->erasesize)','if (0)','write-short-io'),
            ('short-public-read','if (!ret && rdlen != len)','if (0)','read-short'),
            ('no-wait','wait_for_completion(&erase_done);','/* removed completion wait */','write-async'),
        )
        for name,before,after,case in mutations:
            with self.subTest(control=name):
                self.assertEqual(self.source.count(before),1)
                binary=self.compile(self.source.replace(before,after),name)
                self.assertNotEqual(self.run_case(case,binary),self.run_case(case))

    def test_disabled_oracle_cannot_equal_success_or_failed_mutation_paths(self):
        for case in h.DISABLED_CASES:
            with self.subTest(case=case):
                row=self.run_case(case,'disabled')
                self.assertEqual((row['result'],row['trace'],row['writes']),(0,'',0));self.assertNotEqual(row,self.run_case(case))
        self.assertEqual(len(h.CASE_NAMES)+len(h.BASELINE_CASES)+len(h.DISABLED_CASES),44)

    def test_actual_nvram_commit_and_ioctl_propagate_backend_failure(self):
        text=(ROOT/'trunk/linux-4.4.x/drivers/nvram/nvram_linux.c').read_text()
        def extract(name):
            matches=list(re.finditer(r'^(?:static )?(?:int|long)\s*\n?'+name+r'\([^;{}]*\)\s*\{',text,re.M))
            self.assertEqual(len(matches),1)
            start=matches[0].start();opening=text.index('{',start);depth=0
            for token in re.finditer(r'"(?:\\.|[^"\\])*"|/\*[\s\S]*?\*/|//[^\n]*|[{}]',text[opening:]):
                if token.group()=='{':depth+=1
                elif token.group()=='}':
                    depth-=1
                    if not depth:return text[start:opening+token.end()]
            raise AssertionError('Missing NVRAM function body')
        prefix=r'''
#define NVRAM_SPACE 12
#define NVRAM_MTD_OFFSET 4
#define MTD_NVRAM_NAME "Config"
#define NVRAM_IOCTL_COMMIT 10
#define NVRAM_IOCTL_CLEAR 20
#define NVRAM_IOCTL_SET 30
#define NVRAM_IOCTL_GET 40
#define CAP_SYS_ADMIN 21
#define __user
#define spin_lock_irqsave(lock,flags) ((void)(lock),(flags)=0)
#define spin_unlock_irqrestore(lock,flags) ((void)(lock),(void)(flags))
#define mutex_lock(lock) ((void)(lock))
#define mutex_unlock(lock) ((void)(lock))
#define ra_mtd_read_nm mt_mtd_read_nm_wifi
#define ra_mtd_write_nm mt_mtd_write_nm_wifi
struct nvram_header {unsigned char data[NVRAM_SPACE];};
struct file {int unused;};
typedef int anvram_ioctl_t;
static int nvram_major=228,nvram_lock,nvram_sem;
static void*kzalloc(size_t n,int flags){(void)flags;return calloc(1,n);}
static int _nvram_generate(struct nvram_header*h,int temp){int i;(void)temp;for(i=0;i<NVRAM_SPACE;i++)((unsigned char*)h)[i]=(unsigned char)(0xa0+i);return 0;}
static int capable(int cap){(void)cap;return 1;}
static int nvram_clear(void){return 0;}
static int user_nvram_set(anvram_ioctl_t*p){(void)p;return 0;}
static int user_nvram_get(anvram_ioctl_t*p){(void)p;return 0;}
'''
        main=r'''
int main(int argc,char**argv){int i;long result;if(argc!=2)return 90;case_name=argv[1];for(i=0;i<32;i++)flash[i]=(u_char)i;device.size=32;device.erasesize=16;result=dev_nvram_ioctl(NULL,NVRAM_IOCTL_COMMIT,0);printf("%ld %d %d %u\n",result,erases,writes,flash[0]);return 0;}
'''
        for profile in ('current','baseline'):
            functions='\n'.join(item['body'] for item in h.actual_functions(self.texts).values()) if profile=='current' else '\n'.join(h.BASELINE_FUNCTIONS.values())
            binary=self.compile(h.PREFIX+'\n'+functions+prefix+extract('nvram_commit')+'\n'+extract('dev_nvram_ioctl')+main,'actual-commit-'+profile,extra=('-Wno-unused-parameter',))
            for case,current in [('write-short-read','-5 0 0 0\n'),('write-short-io','-5 1 1 0\n')]:
                result=subprocess.run([str(binary),case],text=True,capture_output=True,timeout=5)
                expected=current if profile=='current' else '0 1 1 0\n'
                self.assertEqual((result.returncode,result.stderr,result.stdout),(0,'',expected))

    def test_baseline_literals_source_contract_and_profiles_are_bound(self):
        functions=h.actual_functions(self.texts);self.assertEqual(tuple(functions),h.FUNCTIONS)
        for name,item in functions.items():self.assertEqual(self.source.count(item['body']),1)
        for name,body in h.BASELINE_FUNCTIONS.items():
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),h.BASELINE_FUNCTIONS_SHA256[name])
        for texts,options in (({},{}),(dict(self.texts,extra=''),{}),(self.texts,{'baseline':1}),
                              (self.texts,{'baseline':True,'disabled_oracle':True})):
            with self.assertRaises(ValueError):h.generate_source(texts,**options)
        with mock.patch.dict(h.BASELINE_FUNCTIONS,{'mt_mtd_read_nm_wifi':'wrong'}):
            with self.assertRaises(ValueError):h.generate_source(self.texts)


if __name__=='__main__':unittest.main()
