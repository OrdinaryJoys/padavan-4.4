"""Fault-injected complete current init functions; no hardware execution."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import init_transaction_harness as h

ROOT=Path(__file__).resolve().parents[1]


class InitTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-init-transaction-')
        cls.directory=Path(cls.temp.name)
        cls.texts={k:(ROOT/v).read_text()for k,v in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts)
        source=cls.directory/'init.c';source.write_text(cls.generated)
        gnu=shutil.which('gcc-16')or('/opt/homebrew/bin/gcc-16'if Path('/opt/homebrew/bin/gcc-16').is_file()else shutil.which('gcc'))
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation'not in version or 'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for name,compiler in (('clang',shutil.which('clang')),('gcc',gnu)):
            if not compiler:raise AssertionError('Required compiler absent: '+name)
            binary=cls.directory/name
            flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror',
                   '-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']
            if name=='clang':flags+=['-fsanitize=address,undefined']
            result=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=30)
            if result.returncode:raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def cases(self,prefix):
        for binary in self.binaries:
            for name in h.CASE_NAMES:
                if not name.startswith(prefix):continue
                with self.subTest(compiler=binary.name,case=name):
                    result=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    row=json.loads(result.stdout);self.assertEqual(row,h.EXPECTED_ROWS[name])
                    self.assertTrue(all(type(value)is int for value in row))

    def test_tr_allocations_preserve_old_owner_and_reverse_only_local_resources(self):self.cases('tr-')
    def test_ser_failure_status_and_lock_owner_survive_worker_exit_and_early_join(self):self.cases('ser-')
    def test_hw_control_rolls_back_local_ser_failure_without_double_exit(self):self.cases('hw-')
    def test_management_partial_initialization_releases_only_command_owner(self):self.cases('mgmt-')
    def test_ba_pool_memory_failure_and_reopen_retain_adapter_lock(self):self.cases('ba-')
    def test_qm_failure_preserves_status_and_notifier_owner(self):self.cases('qm-')
    def test_tm_stages_check_each_status_and_reverse_completed_first_stage(self):self.cases('tm-')
    def test_outer_system_init_unwinds_completed_stages_and_retries(self):self.cases('sys-')

    def test_model_covers_whole_functions_and_exact_declared_case_set(self):
        self.assertEqual(len(h.CASE_NAMES),72)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.function_manifest(self.texts)),27)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')

    def test_adapter_lock_parent_lifetime_is_bound_and_ring_cleanup_does_not_own_it(self):
        alloc=h.function(self.texts['adapter'],'RTMPAllocAdapterBlock')
        free=h.function(self.texts['free'],'RTMPFreeAdapter')
        ba=h.function(self.texts['ba'],'ba_reordering_resource_init')
        self.assertEqual(alloc.count('NdisAllocateSpinLock(pAd, &pAd->mpdu_blk_pool.lock);'),1)
        self.assertLess(alloc.index('RtmpOsStatsAlloc'),alloc.index('NdisAllocateSpinLock(pAd, &pAd->mpdu_blk_pool.lock);'))
        self.assertLess(alloc.index('NdisAllocateSpinLock(pAd, &pAd->mpdu_blk_pool.lock);'),alloc.index('*ppAdapter = (VOID *)pAd;'))
        self.assertEqual(free.count('NdisFreeSpinLock(&pAd->mpdu_blk_pool.lock);'),1)
        self.assertNotIn('NdisAllocateSpinLock',ba)


    def test_removed_rollback_and_cleanup_status_barriers_preserve_detection(self):
        mutations=(
            ('rtmp_sys_init','if (tm_exit(pAd) != NDIS_STATUS_SUCCESS) {','if (FALSE) {','sys-tm-rollback-failure'),
            ('rtmp_sys_task_exit','if (tm_exit(pAd) != NDIS_STATUS_SUCCESS) {','if (FALSE) {','sys-task-exit-failure'),
            ('rtmp_sys_exit','if (rtmp_sys_task_exit(pAd) != NDIS_STATUS_SUCCESS)','if (FALSE)','sys-exit-failure'),
            ('tm_init','pAd->tm_qm_ops = qm_ops;','(void)qm_ops;','tm-hif-rollback-failure'),
            ('tm_exit','if (ret != NDIS_STATUS_SUCCESS)\n\t\treturn ret;','if (FALSE)\n\t\treturn ret;','tm-exit-qm-failure'),
            ('rtmp_sys_init','if (RtmpDmaStopping(pAd) ||','if (FALSE ||','sys-stop-refusal'),
            ('rtmp_sys_task_exit','if (tr_ctl_exit(pAd) != NDIS_STATUS_SUCCESS) {','if (FALSE) {','sys-tr-release-failure'),
        )
        for index,(name,before,after,case)in enumerate(mutations):
            with self.subTest(function=name,case=case):
                key=h.FUNCTION_SOURCES[name];body=h.function(self.texts[key],name)
                self.assertEqual(body.count(before),1)
                texts=dict(self.texts);texts[key]=texts[key].replace(body,body.replace(before,after))
                source=self.directory/('removed-rollback-'+str(index)+'.c');source.write_text(h.generate_source(texts))
                binary=source.with_suffix('')
                built=subprocess.run([shutil.which('clang'),'-std=gnu99','-Os','-Wall','-Wextra','-Werror',
                    '-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable',
                    '-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
                self.assertEqual((built.returncode,built.stderr),(0,''),built.stderr)
                rejected=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10)
                self.assertNotEqual(rejected.returncode,0)


if __name__=='__main__':unittest.main()
