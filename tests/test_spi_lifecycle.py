#!/usr/bin/env python3
"""Actual SPI ownership and outer resource release regression controls."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import spi_lifecycle_harness as harness

ROOT=Path(__file__).resolve().parents[1]


class SpiLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='spi-lifecycle-')
        cls.root=Path(cls.temporary.name)
        cls.texts={key:(ROOT/path).read_text() for key,path in harness.SOURCE_PATHS.items()}
        cls.codes={};cls.binaries={}
        for mode in ('current','baseline'):
            cls.codes[mode]=harness.generate_source(cls.texts,baseline=mode=='baseline')
            cls.binaries[mode]=cls.compile_source(cls.codes[mode],mode)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    @classmethod
    def compile_source(cls,code,name):
        path=cls.root/(name+'.c');path.write_text(code);binary=cls.root/name
        run=subprocess.run([shutil.which('clang') or shutil.which('cc'),'-std=gnu89','-Os',
                            '-Wall','-Wextra','-Werror','-Wno-unused-function',
                            '-Wno-unused-parameter','-Wno-unused-variable',
                            '-Wno-unused-but-set-variable','-Wno-sign-compare',
                            '-fsanitize=address,undefined','-g',str(path),'-o',str(binary)],
                           capture_output=True,text=True,timeout=30)
        if run.returncode:raise AssertionError(run.stderr)
        return binary

    def row(self,name,binary='current'):
        binary=self.binaries.get(binary,binary)
        run=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=5)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertNotIn('AddressSanitizer',run.stderr)
        self.assertNotIn('runtime error:',run.stderr)
        return json.loads(run.stdout)

    def mutate(self,name,function,old,new,count=1):
        before=harness.queue.extract(self.texts['core'],function)
        self.assertEqual(before.count(old),count)
        texts=dict(self.texts);texts['core']=texts['core'].replace(before,before.replace(old,new,count),1)
        return self.compile_source(harness.generate_source(texts),name)

    def test_all_current_and_fixed_baseline_observations(self):
        self.assertEqual(len(harness.CASE_NAMES),29)
        for mode in ('current','baseline'):
            for name in harness.CASE_NAMES:
                with self.subTest(mode=mode,name=name):
                    self.assertTrue(harness.validate_row(self.row(name,mode),baseline=mode=='baseline'))

    def test_owned_resources_are_retained_instead_of_timed_out_and_freed(self):
        for name in ('remove-stuck-current','remove-owned-idling','remove-owned-user',
                     'remove-owned-callback','sync-paused-before-pump',
                     'async-paused-before-unlock','async-locked-paused-before-unlock',
                     'callback-remove-interleave'):
            current=self.row(name);old=self.row(name,'baseline')
            self.assertEqual((current['blocked'],current['outer_returned'],current['unsafe_release']),(1,0,0))
            self.assertEqual((current['child_unregister'],current['master_unregister'],
                              current['clock_off'],current['devres']),(0,0,0,0))
            self.assertEqual((old['outer_returned'],old['unsafe_release']),(1,4))

    def test_completed_work_and_retired_users_allow_the_actual_outer_remove_tail(self):
        for name in ('remove-idle','remove-current-finishes','remove-drain-existing',
                     'remove-idling-retires','remove-user-retires','remove-callback-retires'):
            row=self.row(name)
            self.assertEqual((row['outer_returned'],row['child_unregister'],row['master_unregister'],
                              row['clock_off'],row['devres'],row['flush'],row['stop']),(1,1,1,1,1,1,1))
            self.assertEqual((row['users'],row['callbacks'],row['unsafe_release'],row['after_release']),(0,0,0,0))

    def test_completion_requeue_cannot_start_a_transfer_before_callback_returns(self):
        for name in ('callback-next-transfer','callback-worker-wakeup'):
            row=self.row(name);old=self.row(name,'baseline')
            self.assertEqual((row['completed'],row['transfers'],row['completion_order'],
                              row['transfer_order'],row['callback_overlap']),(2,2,12,12,0))
            self.assertEqual(old['callback_overlap'],2)

    def test_closed_admissions_reject_all_api_frames_before_validation(self):
        for name in ('sync-closed','async-closed','async-locked-closed'):
            row=self.row(name)
            self.assertEqual((row['result'],row['validate_calls'],row['users'],row['queue_pending']),(-108,0,0,0))
        self.assertEqual(self.row('preentered-enqueue-closed')['result'],-108)
        self.assertEqual(self.row('resume-closed')['result'],-108)
        self.assertEqual(self.row('remove-late-admission')['late_result'],-108)

    def test_validation_lock_and_enqueue_errors_retire_all_frame_ownership(self):
        for name,error in (('validate-sync',-22),('validate-async',-22),
                           ('validate-async-locked',-22),('bus-locked-async',-16),('stopped-sync',-108)):
            row=self.row(name)
            self.assertEqual((row['result'],row['users'],row['callbacks'],row['queue_pending']),(error,0,0,0))
        for name in ('init-clears','init-fails'):
            self.assertEqual((self.row(name)['queue_dead'],self.row(name)['users'],self.row(name)['callbacks']),(0,0,0))

    def test_actual_source_bodies_header_fields_and_fixed_baseline_are_bound(self):
        actual=harness.actual_functions(self.texts)
        self.assertEqual((len(actual),len(harness.BASELINE_FUNCTIONS)),(27,25))
        for entry in actual.values():self.assertEqual(self.codes['current'].count(entry['body']),1)
        for name,body in harness.BASELINE_FUNCTIONS.items():
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),harness.BASELINE_HASHES[name])
            self.assertEqual(self.codes['baseline'].count(body),1)
        self.assertIn('\tunsigned int\t\t\tqueue_callbacks;',self.codes['current'])
        for texts in ({'core':self.texts['core']},
                      {**self.texts,'header':self.texts['header'].replace('queue_callbacks;','missing_callbacks;')}):
            with self.assertRaises(ValueError):harness.generate_source(texts)
        with self.assertRaises(ValueError):harness.generate_source(self.texts,baseline=1)

    def test_changed_baseline_and_typed_report_tampering_are_rejected(self):
        changed=dict(harness.BASELINE_FUNCTIONS);changed['spi_unregister_master']+='\n'
        with mock.patch.object(harness,'BASELINE_FUNCTIONS',changed),self.assertRaises(ValueError):
            harness.generate_source(self.texts,baseline=True)
        original=self.row('remove-idle')
        for key,value in (('unsafe_release',False),('stop',0),('clock_off',2),('extra',0)):
            row=copy.deepcopy(original);row[key]=value
            with self.assertRaises(ValueError):harness.validate_row(row)
        row=dict(original);row.pop('users')
        with self.assertRaises(ValueError):harness.validate_row(row)

    def test_original_unregister_and_missing_admission_latch_reproduce_failure(self):
        before=harness.queue.extract(self.texts['core'],'spi_unregister_master')
        texts=dict(self.texts);texts['core']=texts['core'].replace(before,harness.BASELINE_FUNCTIONS['spi_unregister_master'],1)
        binary=self.compile_source(harness.generate_source(texts),'old-unregister')
        self.assertEqual(self.row('remove-stuck-current',binary)['unsafe_release'],4)
        binary=self.mutate('open-unregister','spi_unregister_master','master->queue_dead = true;','master->queue_dead = false;')
        self.assertEqual(self.row('remove-late-admission',binary)['late_result'],0)

    def test_stop_predicate_must_include_each_retiring_owner(self):
        for field,name in (('master->idling','remove-owned-idling'),
                           ('master->queue_users','remove-owned-user'),
                           ('master->queue_callbacks','remove-owned-callback')):
            before=harness.queue.extract(self.texts['core'],'spi_stop_queue')
            self.assertEqual(before.count(field),2)
            after=before.replace(field,'false')
            texts=dict(self.texts);texts['core']=texts['core'].replace(before,after,1)
            binary=self.compile_source(harness.generate_source(texts),'no-'+name)
            self.assertEqual(self.row(name,binary)['unsafe_release'],4)

    def test_every_api_frame_requires_entry_and_validation_error_retirement(self):
        for function,paused,invalid in (('__spi_sync','sync-paused-before-pump','validate-sync'),
                                        ('spi_async','async-paused-before-unlock','validate-async'),
                                        ('spi_async_locked','async-locked-paused-before-unlock','validate-async-locked')):
            before=harness.queue.extract(self.texts['core'],function)
            enter='\tif (queued) {\n'
            begin=before.index(enter);end=before.index('\n\t}',begin)+3
            texts=dict(self.texts);texts['core']=texts['core'].replace(before,before[:begin]+before[end:],1)
            binary=self.compile_source(harness.generate_source(texts),'no-enter-'+function)
            self.assertEqual(self.row(paused,binary)['unsafe_release'],4)
            binary=self.mutate('no-leave-'+function,function,'\t\tspi_queue_leave(master);','\t\t(void)master;')
            self.assertEqual(self.row(invalid,binary)['users'],1)

    def test_callback_guard_and_post_callback_worker_wakeup_are_both_required(self):
        binary=self.mutate('overlap-callback','__spi_pump_messages',
                           'master->cur_msg || master->queue_callbacks','master->cur_msg')
        self.assertGreater(self.row('callback-next-transfer',binary)['callback_overlap'],0)
        before=harness.queue.extract(self.texts['core'],'spi_finalize_current_message')
        queue='\tqueue_kthread_work(&master->kworker, &master->pump_messages);\n'
        after=before.replace(queue,'',1).replace('\tmaster->cur_msg_prepared = false;\n',
                                              '\tmaster->cur_msg_prepared = false;\n'+queue,1)
        texts=dict(self.texts);texts['core']=texts['core'].replace(before,after,1)
        binary=self.compile_source(harness.generate_source(texts),'early-worker-wakeup')
        row=self.row('callback-worker-wakeup',binary)
        self.assertEqual((row['completed'],row['transfers'],row['queue_pending'],row['work_pending']),(1,1,1,0))

    def test_callback_retirement_cannot_be_moved_before_callback(self):
        before=harness.queue.extract(self.texts['core'],'spi_finalize_current_message')
        increment='\tmaster->queue_callbacks++;\n'
        after=before.replace(increment,'',1).replace('\tmaster->queue_callbacks--;\n','',1)
        texts=dict(self.texts);texts['core']=texts['core'].replace(before,after,1)
        binary=self.compile_source(harness.generate_source(texts),'no-callback-owner')
        self.assertEqual(self.row('callback-remove-interleave',binary)['unsafe_release'],4)

    def test_preentered_submitter_must_recheck_admission_after_quiescing(self):
        binary=self.mutate('late-enqueue','__spi_queued_transfer',
                           '!master->running || master->queue_dead','!master->running')
        row=self.row('preentered-enqueue-closed',binary)
        self.assertEqual((row['result'],row['queue_pending']),(0,1))


if __name__=='__main__':unittest.main()
