"""Whole unconfigured META bodies, inert IO, and historical ASan witnesses."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import meta_nvram_harness as h

SOURCE=Path(__file__).resolve().parents[1]
FLAGS=('-std=gnu89','-Os','-Wall','-Wextra','-Werror','-Wno-unused-function',
       '-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-but-set-variable',
       '-Wno-sign-compare','-fno-builtin-memcpy')

def known_historical_width_error(stderr):
    errors=[line for line in stderr.splitlines()if re.search(r'\b(?:fatal )?error:',line)]
    # GCC16/glibc can print the parameterized spelling array-bounds=.
    # Accept only this same warning family on the historical UINT16 value;
    # unrelated compile failures must still fail the regression.
    return bool(errors) and 'oid_nvram_rw' in stderr and all(
        re.search(r'\[-Werror=(?:array-bounds=?|stringop-overflow|stringop-overread)\]',line)
        and re.search(r"object [‘']value[’']",line) for line in errors)

class MetaNvramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-meta-native-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(SOURCE/p).read_text()for k,p in h.SOURCE_PATHS.items()}
        cls.compiler=shutil.which('clang')or shutil.which('cc')
        if not cls.compiler:raise AssertionError('Host C compiler required')
        cls.binaries={p:cls.compile(p,baseline=p=='baseline',disabled=p=='disabled')for p in('current','baseline','disabled')}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    @classmethod
    def build(cls,name,baseline=False,disabled=False,source=None,compiler=None,sanitize=True):
        code=h.generate_source(cls.texts,baseline=baseline,disabled_oracle=disabled)if source is None else source
        path=cls.directory/(name+'.c');path.write_text(code);binary=cls.directory/name
        flags=list(FLAGS)
        if sanitize:flags+=['-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
        run=subprocess.run([compiler or cls.compiler,*flags,str(path),'-o',str(binary)],capture_output=True,text=True,timeout=90)
        return binary,run
    @classmethod
    def compile(cls,*args,**kwargs):
        binary,run=cls.build(*args,**kwargs)
        if run.returncode:raise AssertionError(run.stderr)
        return binary
    def run_case(self,case,profile='current',binary=None,success=True):
        run=subprocess.run([str(binary or self.binaries[profile]),case],capture_output=True,text=True,timeout=10,
                           env=dict(os.environ,ASAN_OPTIONS='halt_on_error=1'))
        if success:
            self.assertEqual(run.returncode,0,run.stderr)
            return json.loads(run.stdout)
        self.assertNotEqual(run.returncode,0,'Historical unsafe case unexpectedly succeeded')
        self.assertTrue('AddressSanitizer'in run.stderr or'runtime error'in run.stderr,run.stderr)
        return run.stderr

    def test_actual_protocol_full_bodies_public_baseline_and_unconfigured_scope(self):
        old=subprocess.check_output(['git','-C',str(SOURCE),'show',h.BASELINE_COMMIT+':'+h.SOURCE_PATHS['meta']],text=True)
        self.assertEqual({n:h.function(old,n)for n in h.FUNCTION_SOURCES},h.BASELINE_FUNCTIONS)
        self.assertEqual({n:hashlib.sha256(b.encode()).hexdigest()for n,b in h.BASELINE_FUNCTIONS.items()},h.BASELINE_FUNCTIONS_SHA256)
        code=h.generate_source(self.texts)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(code.count(h.function(self.texts[key],name)),1)
        self.assertIn('UINT16\tdata;',h.declarations(self.texts['header']))
        for name,value in re.findall(r'^#define (OID_CUSTOM_\w+) (0x[0-9A-F]+)$',h.PREFIX,re.M):
            self.assertRegex(self.texts['header'],r'#define\s+'+name+r'\s+'+value+r'\b')
        makefile=(SOURCE/'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615_ap/Makefile').read_text()
        self.assertNotIn('meta_agent.o',makefile)

    def test_twenty_current_two_safe_historical_two_disabled_cases_are_typed_and_bounded(self):
        for profile,names in(('current',h.CASE_NAMES),('baseline',h.BASELINE_CASES),('disabled',h.DISABLED_CASES)):
            for name in names:
                with self.subTest(profile=profile,case=name):
                    row=self.run_case(name,profile);self.assertEqual(len(row),14)
                    self.assertEqual({k for k,v in row.items()if type(v)is str},{'case'})
                    self.assertEqual(row['allocs'],row['frees']);self.assertEqual(row['tail_intact'],1)
        self.assertEqual(self.run_case('stub-error')['status'],17)
        self.assertEqual(self.run_case('stub-error','baseline')['status'],0)
        self.assertEqual(self.run_case('set-low','disabled')['writes'],0)

    def test_full_sixteen_bit_value_and_widened_high_index_preserve_adjacent_bytes(self):
        low=self.run_case('set-low');high=self.run_case('set-high');query=self.run_case('query-high')
        self.assertEqual((low['response_value'],low['low_hi'],low['low_lo'],low['high_hi'],low['high_lo']),(0xabcd,0xab,0xcd,0x56,0x78))
        self.assertEqual((high['low_hi'],high['low_lo'],high['high_hi'],high['high_lo']),(0x12,0x34,0xab,0xcd))
        self.assertEqual(query['response_value'],0x5678)
        for name in('null-image','short-image','invalid-method','short-payload'):
            row=self.run_case(name);self.assertEqual((row['status'],row['writes'],row['copies_out']),(2,0,0))
        self.assertEqual(self.run_case('getsize-null')['response_value'],512)

    def test_dispatcher_response_bounds_copy_faults_and_bin_failures_propagate(self):
        for name in('truncated-total','oversized-total','null-wrq','invalid-ioctl'):
            row=self.run_case(name);self.assertEqual((row['status'],row['allocs'],row['copies_in']),(2,0,0))
        for name in('response-too-long','response-too-small-cap'):
            row=self.run_case(name);self.assertEqual((row['status'],row['copies_out']),(2,0))
        self.assertEqual(self.run_case('oversized-inner')['status'],2)
        self.assertEqual(self.run_case('write-error')['status'],1)
        self.assertEqual(self.run_case('copyin-error')['status'],-14)
        self.assertEqual(self.run_case('copyout-error')['status'],-14)

    def test_historical_four_byte_stack_write_and_read_are_asan_failures(self):
        for case in('set-low','query-high'):
            text=self.run_case(case,'baseline',success=False)
            self.assertIn('stack-buffer-overflow',text)

    def test_historical_oversized_dispatch_copy_and_raw_user_debug_access_fail(self):
        self.assertIn('heap-buffer-overflow',self.run_case('oversized-total','baseline',success=False))
        source=h.generate_source(self.texts,baseline=True).replace('w.u.data.pointer=user;',
            'w.u.data.pointer=selected("copyin-error")?(void*)1:user;')
        binary=self.compile('old-user-pointer',source=source)
        self.run_case('copyin-error',binary=binary,success=False)
        current=h.generate_source(self.texts).replace('w.u.data.pointer=user;',
            'w.u.data.pointer=selected("copyin-error")?(void*)1:user;')
        safe=self.compile('staged-user-pointer',source=current)
        self.assertEqual(self.run_case('copyin-error',binary=safe)['status'],-14)
        # Simulate userspace withdrawing its output buffer after copy_to_user
        # succeeds; response debug must inspect the retained kernel response.
        for old,name in((True,'old-response-debug'),(False,'staged-response-debug')):
            code=h.generate_source(self.texts,baseline=old)
            code=code.replace('w.u.data.length=12;status=resp_to_meta(command,h,&w,0,0);',
                'w.u.data.pointer=malloc(sizeof(user));memcpy(w.u.data.pointer,user,sizeof(user));w.u.data.length=12;status=resp_to_meta(command,h,&w,0,0);')
            code=code.replace('if(selected("copyout-error"))return 1;memcpy(d,s,n);return 0;',
                'if(selected("copyout-error"))return 1;memcpy(d,s,n);if(selected("response-zero"))free(d);return 0;')
            binary=self.compile(name,source=code)
            if old:self.assertIn('heap-use-after-free',self.run_case('response-zero',binary=binary,success=False))
            else:self.assertEqual(self.run_case('response-zero',binary=binary)['status'],0)

    def test_removed_width_index_and_response_guards_are_observable(self):
        source=h.generate_source(self.texts)
        narrow=source.replace('idx = (UINT32)cmd->idx * 2;','idx = (UINT8)(cmd->idx * 2);')
        self.assertNotEqual(narrow,source)
        binary=self.compile('narrow-index',source=narrow)
        self.assertNotEqual(self.run_case('set-high',binary=binary),self.run_case('set-high'))
        width=source.replace('memcpy(&value, &cmd->data, sizeof(value));','memcpy(&value, &cmd->data, 4);')
        self.assertNotEqual(width,source)
        self.run_case('set-low',binary=self.compile('wide-copy',source=width),success=False)
        response=source.replace('(UINT32)len > sizeof(rsp->data)','0').replace('(UINT32)len > wrq->u.data.length - header_len','0')
        self.assertNotEqual(response,source)
        row=self.run_case('response-too-small-cap',binary=self.compile('response-no-cap',source=response))
        self.assertNotEqual((row['status'],row['copies_out']),(2,0))

    def test_gnu_strict_current_and_disabled_profiles_match_clang(self):
        compiler=shutil.which('gcc-16')or shutil.which('gcc')
        if not compiler:raise AssertionError('GNU-compatible compiler required')
        for profile,names in(('current',h.CASE_NAMES),('disabled',h.DISABLED_CASES)):
            binary=self.compile('gcc-'+profile,disabled=profile=='disabled',compiler=compiler,sanitize=False)
            for name in names:self.assertEqual(self.run_case(name,profile,binary=binary),self.run_case(name,profile))

    def test_gnu_historical_profile_runs_safe_cases_or_rejects_known_width_error(self):
        # Exercise both real GCC diagnostic spellings even on hosts whose
        # libc does not enable fortify for the intentionally unsafe body.
        old="gcc-baseline.c: In function 'oid_nvram_rw':\nerror: memcpy writes past object 'value' [-Werror=array-bounds]\n"
        gcc16="In function ‘memcpy’, inlined from ‘oid_nvram_rw’:\nerror: ‘__builtin___memcpy_chk’ forming offset [2, 3] is out of the bounds [0, 2] of object ‘value’ with type ‘UINT16’ [-Werror=array-bounds=]\n"
        for diagnostic in (old,gcc16,old+gcc16):
            self.assertTrue(known_historical_width_error(diagnostic))
        for diagnostic in ('',gcc16.replace('value','other'),gcc16.replace('array-bounds=','format'),
                           gcc16.replace('array-bounds=','array-bounds=='),
                           gcc16.replace('oid_nvram_rw','other_function'),
                           gcc16+'fatal error: missing.h: No such file or directory\n'):
            self.assertFalse(known_historical_width_error(diagnostic),diagnostic)
        compiler=shutil.which('gcc-16')or shutil.which('gcc')
        if not compiler:raise AssertionError('GNU-compatible compiler required')
        # The complete historical body intentionally retains its bad memcpy
        # width. glibc fortify may reject it even when only safe cases are run.
        # This control uses the same strict flags as current/disabled profiles.
        binary,run=self.build('gcc-baseline',baseline=True,compiler=compiler,sanitize=False)
        if not run.returncode:
            for name in h.BASELINE_CASES:
                self.assertEqual(self.run_case(name,'baseline',binary=binary),self.run_case(name,'baseline'))
            return
        self.assertTrue(known_historical_width_error(run.stderr),run.stderr)
        self.assertIn('oid_nvram_rw',run.stderr)
        self.assertRegex(run.stderr,r"object [‘']value[’']|[‘']value[’'] declared here")

if __name__=='__main__':unittest.main()
