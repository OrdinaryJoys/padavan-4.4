#!/usr/bin/env python3
"""MT7621 controller lifetime and FIFO data paths under explicit inert seams."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import controller_harness as harness

ROOT=Path(__file__).resolve().parents[1]

class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-controller-')
        cls.base=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text() for k,v in harness.SOURCE_PATHS.items()}
        cls.compiler=shutil.which('clang') or shutil.which('cc')
        if not cls.compiler:raise RuntimeError('Host C compiler required')
        cls.expected=dict(harness.CASES)
        cls.binaries={k:cls.compile(cls.texts,k,baseline=b) for k,b in [('current',False),('baseline',True)]}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @classmethod
    def compile(cls,texts,name,baseline=False,raw=None,extra=()):
        c=cls.base/(name+'.c');exe=cls.base/name
        c.write_text(raw if raw is not None else harness.generate_source(texts,baseline=baseline))
        command=[cls.compiler,'-std=gnu89','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-sign-compare','-fsanitize=address,undefined','-fno-sanitize-recover=undefined','-fno-omit-frame-pointer',*extra,str(c),'-o',str(exe)]
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode:raise AssertionError((name,result.stderr))
        return exe

    def run_case(self,name,binary='current'):
        exe=self.binaries.get(binary,binary)
        result=subprocess.run([str(exe),name],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,(name,result.stderr))
        self.assertEqual(result.stderr,'',(name,result.stderr))
        return json.loads(result.stdout)

    def check(self,names):
        for name in names:
            with self.subTest(case=name):self.assertEqual(self.run_case(name),self.expected[name])

    def test_normal_probe_and_smallest_valid_clock_remain_compatible(self):
        self.check(('probe-normal','probe-clock-two'))

    def test_map_clock_get_and_enable_failures_do_not_claim_resources(self):
        self.check(('probe-map-error','probe-clock-get-error','probe-clock-enable-error'))

    def test_clock_get_error_log_matches_returned_errno_and_old_zero_diagnostic_is_visible(self):
        # Keep the 42-row controller contract intact. This actual-body probe
        # checks the logger argument independently through an inert logger.
        logger = """static int diagnostic_error, diagnostic_calls;
static const char *diagnostic_format;
static void capture_diagnostic(const char *format,int error)
{diagnostic_calls++;diagnostic_error=error;diagnostic_format=format;}
#define dev_info(device,format,error) capture_diagnostic((format),(error))"""
        prefix=harness.PREFIX.replace('#define dev_info(...) ((void)0)',logger)
        prefix+='\n'+harness.production_fragments(self.texts)+'\n'+harness.SEAMS+'\n'
        main=r'''int main(void){struct platform_device p;int result;
memset(&p,0,sizeof(p));clk_error=-517;result=mt7621_spi_probe(&p);
printf("{\"result\":%d,\"logged_error\":%d,\"calls\":%d,\"format_matches\":%d}\n",result,diagnostic_error,diagnostic_calls,
 diagnostic_format&&strcmp(diagnostic_format,"unable to get hclk, err = %d\n")==0);return 0;}'''
        bodies={'current':harness.extract(self.texts['controller'],'mt7621_spi_probe'),
                'baseline':harness.BASELINE_FUNCTIONS['mt7621_spi_probe']}
        for label,expected_log in (('current',-517),('baseline',0)):
            with self.subTest(profile=label):
                binary=self.compile(self.texts,'clock-diagnostic-'+label,raw=prefix+bodies[label]+'\n'+main,
                                    extra=('-Wno-unused-variable',))
                result=subprocess.run([str(binary)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
                self.assertEqual(json.loads(result.stdout),{'result':-517,'logged_error':expected_log,'calls':1,'format_matches':1})

    def test_clock_zero_and_one_reject_before_allocation_and_cleanup_clock(self):
        self.check(('probe-clock-zero','probe-clock-one'))

    def test_allocation_and_registration_errors_release_exact_resources_and_drvdata(self):
        self.check(('probe-alloc-error','probe-register-error'))

    def test_declared_reset_defer_and_failure_stop_registration_with_cleanup(self):
        self.check(('probe-reset-defer','probe-reset-error'))

    def test_absent_and_disabled_reset_support_keep_optional_compatibility(self):
        self.check(('probe-reset-absent-error','probe-reset-disabled-error'))

    def test_remove_keeps_clock_through_unregister_and_survives_master_release(self):
        self.check(('remove-normal','remove-retained-ref'))
        self.assertEqual(self.run_case('remove-normal')['master_refs'],0)

    def test_zero_and_fifo_boundary_reads_return_success_and_exact_bytes(self):
        self.check(('read-zero','read-one','read-31','read-32','read-33','read-64'))

    def test_read_timeouts_preserve_only_completed_prefix_and_error(self):
        self.check(('read-error-first','read-error-second'))

    def test_write_unsigned_high_bytes_fifo_boundaries_and_timeout_errors(self):
        self.check(('write-zero','write-one','write-four','write-five','write-seven','write-eight-high','write-36','write-37','write-error-first','write-error-second','write-ff-word'))

    def test_exact_old_bodies_reproduce_defined_lifetime_faults_only(self):
        for name,expected in harness.BASELINE_CASES:
            with self.subTest(case=name):self.assertEqual(self.run_case(name,'baseline'),expected)
        for name,body in harness.BASELINE_FUNCTIONS.items():
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),harness.BASELINE_FUNCTIONS_SHA256[name])
            self.assertIn(body,harness.generate_source(self.texts,baseline=True))
        self.assertEqual(len(harness.BASELINE_CASES),8)
        self.assertFalse(any(name.startswith(('read-','write-')) for name,_ in harness.BASELINE_CASES))

    def test_old_zero_read_and_signed_shift_are_separate_compiler_sanitizer_controls(self):
        # Undefined baseline execution is never frozen into the MIPS row contract.
        prefix=harness.PREFIX+'\n'+harness.production_fragments(self.texts)+'\n'+harness.SEAMS+'\n'
        old_read=harness.BASELINE_FUNCTIONS['mt7621_spi_read']
        c=self.base/'old-zero-read-warning.c'
        c.write_text(prefix+old_read+'\nint main(void){struct mt7621_spi m;u8 b;m.base=regs;return mt7621_spi_read(&m,&b,0);}\n')
        diagnostic=['-Werror=conditional-uninitialized'] if 'clang' in Path(self.compiler).name else ['-Werror=uninitialized','-Werror=maybe-uninitialized']
        command=[self.compiler,'-std=gnu89','-O2','-Wall','-Wextra','-Wno-unused-function','-Wno-sign-compare',*diagnostic,'-c',str(c),'-o',str(self.base/'old-zero-read.o')]
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('uninitialized',result.stderr)
        old_write=harness.BASELINE_FUNCTIONS['mt7621_spi_write']
        exe=self.compile(self.texts,'old-shift-ubsan',raw=prefix+old_write+'\nint main(void){struct mt7621_spi m;u8 b[8]={0};m.base=regs;b[7]=128;return mt7621_spi_write(&m,b,8);}\n',extra=('-std=gnu99','-Wno-unused-variable',))
        result=subprocess.run([str(exe)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('left shift',result.stderr)
        # Fixed historical divider keeps this old UB control independent of the
        # current defensive zero-rate guard. No device clock is accessed.
        import controller_clock_harness as clock
        self.assertEqual(hashlib.sha256(clock.BASELINE_BODY.encode()).hexdigest(),clock.BASELINE_SHA256)
        exe=self.compile(self.texts,'old-zero-div-ubsan',raw=prefix+clock.BASELINE_BODY+'\nint main(void){volatile u32 z=0;return mt7621_spi_get_clk_div(z,z);}\n',extra=('-Wno-unused-variable',))
        result=subprocess.run([str(exe)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('division by zero',result.stderr)

    def test_removed_safety_changes_are_detected_by_behavior_or_asan(self):
        controls=(
            ('lost-allocation-cleanup','mt7621_spi_probe','status = -ENOMEM;\n\t\tgoto err_disable_clk;','return -ENOMEM;','probe-alloc-error'),
            ('lost-rate-one-guard','mt7621_spi_probe','hclk_freq < 2','hclk_freq < 1','probe-clock-one'),
            ('lost-drvdata-clear','mt7621_spi_probe','dev_set_drvdata(&pdev->dev, NULL);','/* removed clear */','probe-register-error'),
            ('lost-reset-error','mt7621_spi_probe','if (status && IS_ENABLED(CONFIG_RESET_CONTROLLER) &&','if (0 && status && IS_ENABLED(CONFIG_RESET_CONTROLLER) &&','probe-reset-defer'),
            ('lost-unprepare','mt7621_spi_remove','clk_disable_unprepare(hclk);','clk_disable(hclk);','remove-normal'),
            ('read-error-swallowed','mt7621_spi_read','if (ret)\n\t\t\treturn ret;','if (0 && ret)\n\t\t\treturn ret;','read-error-first'),
            ('write-error-swallowed','mt7621_spi_write','if (ret)\n\t\t\treturn ret;','if (0 && ret)\n\t\t\treturn ret;','write-error-first'),
        )
        for label,function,before,after,case in controls:
            with self.subTest(control=label):
                texts=copy.deepcopy(self.texts);body=harness.extract(texts['controller'],function)
                self.assertEqual(body.count(before),1)
                texts['controller']=texts['controller'].replace(body,body.replace(before,after))
                exe=self.compile(texts,label)
                self.assertNotEqual(self.run_case(case,exe),self.expected[case])
        texts=copy.deepcopy(self.texts);body=harness.extract(texts['controller'],'mt7621_spi_remove')
        before='hclk = ms->hclk;\n\tspi_unregister_master(master);';after='spi_unregister_master(master);\n\thclk = ms->hclk;'
        self.assertEqual(body.count(before),1);texts['controller']=texts['controller'].replace(body,body.replace(before,after))
        exe=self.compile(texts,'removed-pre-release-clock-save');result=subprocess.run([str(exe),'remove-normal'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('AddressSanitizer',result.stderr)

    def test_generator_rejects_ambiguous_manifest_and_untyped_baseline(self):
        with self.assertRaises(ValueError):harness.generate_source({})
        with self.assertRaises(ValueError):harness.generate_source(self.texts,baseline=1)
        with self.assertRaises(ValueError):harness.generate_source(self.texts,owner_uid=False)
        texts=copy.deepcopy(self.texts);texts['controller']+='\n'+harness.extract(texts['controller'],'mt7621_spi_remove')
        with self.assertRaises(ValueError):harness.generate_source(texts)
        self.assertEqual(len(harness.CASES),34)
        for name,_ in harness.CASES:
            with self.subTest(case=name):self.assertIn(name,harness.DRIVER)

if __name__=='__main__':unittest.main()
