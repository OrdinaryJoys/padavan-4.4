#!/usr/bin/env python3
"""Real Web/GPIO/PID1 admission and flash return; all hardware effects inert."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest
import upgrade_transaction_harness as h

ROOT=Path(__file__).resolve().parents[1]
BASELINE='8619612929814b518801c3581c2997676e4e640e'
# Public exact old functions from BASELINE, kept locally for depth-one CI.
OLD_FUNCTIONS={
 'apply_cgi':('trunk/user/httpd/web_ex.c','6a8faccfe204d5af7fa2085f2367300db435ec3dfbc3471e3495c691ab2962b4','621dc1a0be4456744d744b35bbcbcb8576ac532fb64c74b63b225ba7cc6476e1'),
 'catch_sig_fatal':('trunk/user/rc/init.c','2320894819e0df32547a1e8e6d712edc3ce103a792c536a2e33e422de8c1c0f8','a613e84b5f4669601e585d772129586e7d5da44001ce00dce1ec744dac6db74f'),
}
FLAGS=['-O1','-std=gnu89','-Wall','-Wextra','-Werror','-Wno-unused-function',
       '-Wno-unused-parameter','-Wno-unused-variable','-fsanitize=address,undefined']

class UpgradeTransactionTests(unittest.TestCase):
    def old_function(self,name):
        source,file_sha,body_sha=OLD_FUNCTIONS[name]
        raw=(ROOT/'tests/fixtures/upgrade-transaction'/('861-'+name+'.c')).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),file_sha)
        body=h.extract(raw.decode(),name)
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),body_sha)
        self.assertTrue(source.startswith('trunk/user/'))
        return body
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='k2p-transaction-')
        cls.directory=Path(cls.tmp.name)
        cls.component_root=cls.directory/'component-private'
        cls.flash_root=cls.directory/'flash-fixture'
        cls.texts={k:(ROOT/p).read_text() for k,p in h.SOURCE_PATHS.items()}
        cls.binary=cls.compile('component',h.generate_source(cls.texts,str(cls.component_root),os.geteuid()))
        cls.flash_binary=cls.compile('flash',h.generate_flash_source(cls.texts,str(cls.flash_root),os.geteuid()))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    @classmethod
    def compile(cls,name,code,old_format=False):
        path=cls.directory/(name+'.c');binary=cls.directory/name;path.write_text(code)
        # One historical-format negative intentionally compiles its unsafe
        # nonliteral format; every current source uses the strict flags.
        flags=FLAGS+(['-Wno-format-security'] if old_format else [])
        result=subprocess.run(['clang',*flags,str(path),'-o',str(binary)],capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
        return binary
    def execute(self,binary,name):
        process=subprocess.Popen([str(binary),name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 text=True,start_new_session=True)
        try:stdout,stderr=process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.communicate(timeout=2);raise
        return process.returncode,stdout,stderr
    def cases(self,*names):
        expected=dict(h.CASES)
        for name in names:
            with self.subTest(case=name):
                status,out,err=self.execute(self.binary,name)
                self.assertEqual(status,0,err);self.assertEqual(json.loads(out),expected[name])
                self.assertFalse(self.component_root.exists())
    def test_header_query_missing_directory_mode_and_errno(self):
        self.cases('query-idle','query-missing-directory','unsafe-directory','marker-rejects-action')
    def test_real_flock_and_cross_process_exclusion(self):
        self.cases('shared-excludes-transaction','transaction-excludes-action','cross-process-sh-exclusion')
    def test_http_auth_and_origin_precede_busy_rejection(self):
        self.cases('http-busy-write','http-busy-auth-failure','http-busy-cross-origin')
    def test_readonly_status_and_head_backup_boundary(self):
        self.cases('http-busy-status','http-busy-status-head','http-busy-backup-head')
    def test_request_prepare_callbacks_hold_lease_and_all_returns_release(self):
        self.cases('http-idle-write','http-backup-prepare-failure','http-backup-head-release')
    def test_direct_mutating_helpers_refuse_before_config_and_signal_effects(self):
        self.cases('direct-reboot-busy','apply-reset-busy','restore-nv-busy','restore-storage-busy',
                   'upgrade-busy-preserves-upload')
    def test_idle_direct_helpers_hold_lease_and_safe_release_reopens(self):
        self.cases('direct-reboot-idle','apply-reset-idle','safe-release-reopens-action')
    def test_upgrade_handoff_and_upload_admission(self):
        self.cases('upgrade-request-handoff','upload-busy','restore-upload-busy')
    def test_gpio_public_and_event_entries_block_before_effects(self):
        self.cases('gpio-short-busy','gpio-long-busy','gpio-reset-busy','gpio-release-busy',
                   'gpio-event-busy-clears-latch')
    def test_gpio_idle_paths_release_nested_leases(self):
        self.cases('gpio-long-idle','gpio-reset-idle','gpio-release-idle')
    def test_actual_cli_entrypoints_refuse_before_erase_or_signal(self):
        self.cases('cli-reboot-busy','cli-halt-busy','cli-reset-busy','cli-reset-idle')
    def test_actual_pid1_signal_latches_event_reaper_and_fatal_mask(self):
        self.cases('phase-active-TERM','phase-active-QUIT','phase-active-SEGV','phase-idle-TERM',
                   'phase-idle-QUIT','phase-events-active','phase-events-idle','phase-reap-active',
                   'phase-reap-idle','init-signal-masks')
    def test_actual_flash_return_latch_marker_and_raw_exclusive_lease(self):
        for name,expected in h.FLASH_CASES:
            with self.subTest(case=name):
                if self.flash_root.exists():shutil.rmtree(self.flash_root)
                status,out,err=self.execute(self.flash_binary,name)
                self.assertEqual(status,0,err);self.assertEqual(json.loads(out),expected)
    def test_percent_group_input_is_literal_and_old_actual_body_fails(self):
        self.cases('apply-group-percent-literal')
        texts=dict(self.texts)
        texts['web']=texts['web'].replace(h.extract(texts['web'],'apply_cgi'),self.old_function('apply_cgi'))
        binary=self.compile('old-format',h.generate_source(texts,str(self.component_root),os.geteuid()),old_format=True)
        status,out,err=self.execute(binary,'apply-group-percent-literal')
        if status==0:self.assertIn('group-literal:0',json.loads(out)['trace'])
        else:self.assertTrue(err)
        if self.component_root.exists():shutil.rmtree(self.component_root)
    def test_old_actual_fatal_function_reproduces_closed_reset_gap(self):
        texts=dict(self.texts)
        texts['init']=texts['init'].replace(h.extract(texts['init'],'catch_sig_fatal'),self.old_function('catch_sig_fatal'))
        binary=self.compile('old-fatal',h.generate_source(texts,str(self.component_root),os.geteuid()))
        status,out,err=self.execute(binary,'phase-active-TERM');self.assertEqual(status,0,err)
        row=json.loads(out);self.assertNotEqual(row,dict(h.CASES)['phase-active-TERM'])
        self.assertIn('broadcast-TERM',row['trace']);self.assertIn('reboot',row['trace'])
    def test_generator_validation_and_actual_bodies_appear_exactly_once(self):
        for root in ('relative','/tmp/bad\nname','/tmp/nonascii-\u4e2d'):
            with self.assertRaises(ValueError):h.generate_source(self.texts,root)
        for uid in (True,-1,2**32):
            with self.assertRaises(ValueError):h.generate_source(self.texts,str(self.component_root),uid)
        with self.assertRaises(ValueError):h.generate_source({},str(self.component_root))
        code=h.generate_source(self.texts,str(self.component_root),os.geteuid())
        for name,record in h.actual_functions(self.texts).items():
            with self.subTest(function=name):self.assertEqual(code.count(record['body']),1)
        self.assertEqual(len(h.CASES),50);self.assertEqual(len(h.FLASH_CASES),6)
    def test_main_loop_guards_are_structurally_before_console_and_deferred_effects(self):
        # Source-structure coverage only, not execution of full PID1 or hardware.
        loop=h.extract(self.texts['init'],'init_main_loop')
        self.assertRegex(loop,r'if \(firmware_upgrade_signal_inhibited\(\)\)\s*\{\s*sigsuspend\(&ss\);\s*continue;')
        self.assertLess(loop.index('firmware_upgrade_signal_inhibited()'),loop.index('shell_pid = run_shell'))
        self.assertRegex(loop,r'handle_notifications\(\);\s*\}\s*if \(firmware_upgrade_signal_inhibited\(\)\)\s*continue;')
        signals=h.extract(self.texts['init'],'init_signals')
        self.assertLess(signals.index('sigaddset(&sa.sa_mask, SIGCHLD)'),signals.index('sigaction(signals_fatal[i]'))

if __name__=='__main__':unittest.main()
