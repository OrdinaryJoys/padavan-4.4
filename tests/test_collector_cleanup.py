#!/usr/bin/env python3
"""Owned collector cleanup: exact source bodies, inert faults, safe own children."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import collector_cleanup_harness as H

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ['-std=gnu89', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-Wno-unused-function', '-Wno-unused-parameter', '-Wno-sign-compare',
         '-Wno-pointer-sign', '-fsanitize=address,undefined']


class CollectorCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-collector-cleanup-native-')
        cls.root = Path(cls.temp.name)
        cls.inputs = {key: (ROOT / path).read_text() for key, path in H.SOURCE_PATHS.items()}
        cls.current = cls.compile('current', cls.inputs)
        cls.baseline = cls.compile('baseline', cls.inputs, True)
        cls.rows = {n: cls.run_case(cls.current, n) for n, _ in H.CASES}
        cls.old = {n: cls.run_case(cls.baseline, n) for n, _ in H.BASELINE_CASES}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def compile(cls, name, inputs, baseline=False):
        path = cls.root / name
        text = H.generate_source(inputs, '/tmp/k2p-collector-source-unittest/' +
                                 ('baseline' if baseline else 'current') + '-fixture', 501, baseline)
        path.with_suffix('.c').write_text(text)
        result = subprocess.run(['clang', *FLAGS, str(path.with_suffix('.c')), '-o', str(path)],
                                text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return path

    @classmethod
    def run_case(cls, binary, selector):
        result = subprocess.run([str(binary), str(selector)], text=True, capture_output=True,
                                env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'}, timeout=3)
        if result.returncode or result.stderr:
            raise AssertionError(result.stdout + result.stderr)
        row = json.loads(result.stdout)
        if any(type(value) is not int for value in row.values()):
            raise AssertionError('Every fixture observation is an integer, not bool/float')
        return row

    def mutate(self, name, old, new, selectors):
        inputs = dict(self.inputs)
        self.assertEqual(inputs['collector'].count(old), 1)
        inputs['collector'] = inputs['collector'].replace(old, new, 1)
        binary = self.compile(name, inputs)
        return [self.run_case(binary, n) for n in selectors]

    def test_current_complete_44_typed_observation_contract(self):
        self.assertEqual(len(H.CASES), 44)
        self.assertEqual(self.rows, dict(H.CASES))

    def test_baseline_eight_defined_resource_counterexamples(self):
        self.assertEqual(self.old, dict(H.BASELINE_CASES))
        for selector in (2, 3, 5, 7, 8, 15):
            self.assertEqual(self.old[selector]['accepted'], 1)
            self.assertEqual(self.rows[selector]['accepted'], 0)
        self.assertEqual(self.old[15]['directed_after_loss'], 3)
        self.assertEqual(self.rows[15]['directed_after_loss'], 0)

    def test_group_signal_errors_require_independent_absence(self):
        for good, bad in ((4, 5), (6, 7)):
            self.assertGreater(self.rows[good]['signal_errors'], 0)
            self.assertEqual(self.rows[good]['accepted'], 1)
            self.assertGreater(self.rows[bad]['signal_errors'], 0)
            self.assertEqual(self.rows[bad]['accepted'], 0)
        self.assertEqual(self.rows[8]['accepted'], 0, 'Direct leader error remains conservative')

    def test_only_reaped_leader_and_absent_group_permit_publication(self):
        for row in self.rows.values():
            if row['accepted']:
                self.assertEqual(row['raw_status'], 0)
                self.assertGreater(row['waitpid_calls'], 0)
                self.assertGreater(row['zero_probes'], 0)
                self.assertEqual(row['group_present'], 0)
                self.assertEqual(row['depth'], 1)
                self.assertEqual(row['output_matches'], 1)
            else:
                self.assertEqual(row['depth'], 0)
        for selector in (2, 3, 9, 10, 13, 31, 35):
            self.assertEqual(self.rows[selector]['accepted'], 0)

    def test_no_directed_signal_after_reap_or_observed_ownership_loss(self):
        for row in self.rows.values():
            self.assertEqual(row['directed_after_reap'], 0)
            self.assertEqual(row['directed_after_loss'], 0)
        for selector in (14, 15, 40, 41, 42):
            self.assertEqual(self.rows[selector]['directed_signals'], 0)
            self.assertEqual(self.rows[selector]['raw_status'], -1)

    def test_sigchld_and_signal_restore_fail_closed(self):
        for selector in (16, 17, 18, 19):
            row = self.rows[selector]
            self.assertEqual(row['fork_calls'], 0)
            self.assertEqual(row['accepted'], 0)
        for selector in (20, 21):
            row = self.rows[selector]
            self.assertEqual(row['accepted'], 0)
            self.assertEqual(row['error_kind'], 4)
            self.assertEqual(row['mask_restored'], 1)
            self.assertEqual(row['handlers_restored'], 1)
        for row in self.rows.values():
            self.assertEqual(row['mask_restored'], 1)
            self.assertEqual(row['handlers_restored'], 1)
            if row['fork_calls']:
                self.assertEqual(row['chld_held_at_fork'], 1)

    def test_fast_exit_group_proof_and_unknown_group_rejection(self):
        for selector in (23, 36, 37):
            self.assertEqual(self.rows[selector]['accepted'], 1)
            self.assertEqual(self.rows[selector]['raw_status'], 0)
        for selector in (22, 24, 38, 39, 42):
            self.assertEqual(self.rows[selector]['accepted'], 0)

    def test_cleanup_has_step_and_clock_failure_bounds(self):
        self.assertLessEqual(self.rows[13]['zero_probes'], 64)
        self.assertLessEqual(self.rows[13]['poll_calls'], 66)
        self.assertLessEqual(self.rows[35]['waitpid_calls'], 64)
        self.assertEqual(self.rows[12]['accepted'], 0)
        self.assertEqual(self.rows[29]['fork_calls'], 0)
        self.assertEqual(self.rows[34]['accepted'], 1)
        self.assertEqual(self.rows[34]['waitpid_calls'], 2)

    def test_real_own_short_generators_restore_mask_and_reaping_handler(self):
        code = self.root / 'real-own-children.c'
        code.write_text(r'''
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <string.h>
#include <signal.h>
#include <sys/wait.h>
#include "dynamic_conf.c"
static void reap_own(int signal_number) { int status; (void)signal_number; while(waitpid(-1,&status,WNOHANG)>0){} }
int main(void) {
  int i, raw; struct sigaction action, observed; sigset_t held, original, after;
  memset(&action,0,sizeof(action)); action.sa_handler=reap_own; sigemptyset(&action.sa_mask);
  if(sigaction(SIGCHLD,&action,NULL))return 10;
  sigemptyset(&held);sigaddset(&held,SIGUSR1);
  if(sigprocmask(SIG_BLOCK,&held,&original))return 11;
  for(i=0;i<40;i++) {
    struct conf_script_budget budget={0}; const char *error=NULL; FILE *stream; char text[32]={0};
    stream=conf_script_open_status(i%2?"true":"printf 'cache-size=123\\n'",&budget,&error,&raw);
    if(!stream){fprintf(stderr,"%s\n",error);return 12;}
    if(raw||budget.depth!=1)return 13;
    (void)fread(text,1,sizeof(text)-1,stream);
    if(strcmp(text,i%2?"\n":"cache-size=123\n"))return 14;
    conf_script_close(stream,&budget);if(budget.depth)return 15;
    if(sigaction(SIGCHLD,NULL,&observed)||observed.sa_handler!=reap_own)return 16;
    if(sigprocmask(SIG_SETMASK,NULL,&after)||sigismember(&after,SIGCHLD)!=sigismember(&original,SIGCHLD)||sigismember(&after,SIGUSR1)!=1)return 17;
  }
  action.sa_handler=SIG_IGN;if(sigaction(SIGCHLD,&action,NULL))return 18;
  { struct conf_script_budget budget={0};const char *error=NULL;FILE *stream=conf_script_open("true",&budget,&error);
    if(stream||!strstr(error,"ownership"))return 19; }
  if(sigprocmask(SIG_SETMASK,&original,NULL))return 20;
  puts("{\"rounds\":40,\"handler_restored\":1,\"mask_restored\":1,\"ignored_rejected\":1}");return 0;
}
''')
        binary = self.root / 'real-own-children'
        result = subprocess.run(['clang', *FLAGS, '-I'+str(ROOT/H.SOURCE_PATHS['collector']).rsplit('/',1)[0],
                                 str(code), '-o', str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['rounds'], 40)

    def test_removing_post_reap_group_probe_accepts_residual(self):
        rows = self.mutate('no-empty-group', '          if (kill(-pid, 0) != 0)\n            return errno == ESRCH && clean;',
                           '          return clean;', (2, 3, 5, 7))
        self.assertTrue(all(row['accepted'] for row in rows))
        self.assertTrue(all(row['group_present'] for row in rows))

    def test_removing_any_sticky_ownership_guard_signals_recycled_identity(self):
        mutations = [
            ('main-lost', 'if (errno == ECHILD) pid = -1;', 'if (errno == ECHILD) { }', 40),
            ('fallback-lost', '              pid = -1;\n              *error = "conf-script child ownership unavailable";',
             '              *error = "conf-script child ownership unavailable";', 42),
            ('cleanup-retry', '{ pid = -1; *error = "conf-script process cleanup failed"; goto fail; }',
             '{ *error = "conf-script process cleanup failed"; goto fail; }', 41),
        ]
        for name, before, after, selector in mutations:
            with self.subTest(name=name):
                row = self.mutate(name, before, after, (selector,))[0]
                self.assertGreater(row['directed_after_loss'], 0)
                self.assertGreater(row['directed_signals'], 0)

    def test_removing_sigchld_mask_is_observable(self):
        row = self.mutate('no-child-mask', '  sigaddset(&blocked, SIGCHLD);',
                          '  sigemptyset(&blocked);', (0,))[0]
        self.assertEqual(row['accepted'], 1)
        self.assertEqual(row['chld_held_at_fork'], 0)
        self.assertEqual(self.rows[0]['chld_held_at_fork'], 1)

    def test_ignoring_signal_restore_failure_publishes_output(self):
        before = '  if (!restore_collector_signals(previous, installed_handlers, &previous_mask, masked))\n    { *error = "conf-script signal restore failed"; goto fail; }'
        row = self.mutate('ignore-restore', before,
                          '  (void)restore_collector_signals(previous, installed_handlers, &previous_mask, masked);', (20,))[0]
        self.assertEqual(row['accepted'], 1)
        self.assertEqual(row['mask_restored'], 0)
        self.assertEqual(self.rows[20]['accepted'], 0)
        before='  if (cancelled)\n    { *error = "conf-script execution cancelled"; goto fail; }\n  budget->buffers'
        row=self.mutate('ignore-restore-cancel',before,'  budget->buffers',(43,))[0]
        self.assertEqual(row['accepted'],1)
        self.assertEqual(self.rows[43]['accepted'],0)
        self.assertEqual(self.rows[43]['error_kind'],5)

    def test_baseline_and_inert_process_protocol_contracts_cannot_drift(self):
        mutations=[('no-wnowait','WEXITED | WNOHANG | WNOWAIT','WEXITED | WNOHANG'),
                   ('no-wait-nonblock','waitpid(pid, &status, WNOHANG)','waitpid(pid, &status, 0)'),
                   ('wrong-wait-kind','waitid(P_PID,','waitid(P_ALL,'),
                   ('wrong-kill-target','kill(pid, SIGKILL)','kill(-1, SIGKILL)'),
                   ('leader-is-not-group','kill(-pid, 0)','kill(pid, 0)')]
        for name,before,after in mutations:
            inputs=dict(self.inputs);self.assertEqual(inputs['collector'].count(before),1)
            inputs['collector']=inputs['collector'].replace(before,after,1)
            binary=self.compile(name,inputs)
            result=subprocess.run([str(binary),'0'],capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,90,result.stderr)
            self.assertIn('MODEL_BOUNDARY:',result.stderr)
        self.assertEqual(hashlib.sha256(self.inputs['header'].encode()).hexdigest(), H.BASELINE_HEADER_SHA256)
        changed = dict(H.BASELINE_FUNCTIONS)
        changed['stop_group'] += '\n'
        with mock.patch.object(H,'BASELINE_FUNCTIONS',changed),self.assertRaises(ValueError):
            H.generate_source(self.inputs,'/tmp/k2p-collector-source-corrupt/baseline-fixture',0,True)
        for key, change in [('header','\n'),('collector','\nstatic volatile sig_atomic_t cancelled;\n')]:
            inputs = dict(self.inputs); inputs[key] += change
            with self.subTest(key=key),self.assertRaises(ValueError):
                H.generate_source(inputs,'/tmp/k2p-collector-source-corrupt/current-fixture')


if __name__ == '__main__':
    unittest.main(verbosity=2)
