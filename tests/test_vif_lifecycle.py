"""Current VIF acquisition/rollback with real counter and dispatch functions."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import vif_lifecycle_harness as h

ROOT=Path(__file__).resolve().parents[1]


class VifLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='k2p-vif-lifecycle-')
        cls.directory=Path(cls.temporary.name)
        cls.texts={key:(ROOT/path).read_text()for key,path in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts)
        source=cls.directory/'vif.c';source.write_text(cls.generated)
        gnu=shutil.which('gcc-16')or shutil.which('gcc')
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.compilers=(('gcc',gnu),('clang',shutil.which('clang')))
        cls.binaries=[]
        for label,compiler in cls.compilers:
            if not compiler:raise AssertionError('Required compiler absent: '+label)
            binary=cls.directory/label
            flags=['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter']
            if label=='clang':flags+=['-fsanitize=address,undefined']
            result=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            if result.returncode:raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def cases(self,group):
        for binary in self.binaries:
            for name in h.CASE_GROUPS[group]:
                with self.subTest(compiler=binary.name,case=name):
                    result=subprocess.run([str(binary),name],check=True,capture_output=True,text=True,timeout=10)
                    self.assertEqual(json.loads(result.stdout),h.EXPECTED_ROWS[name])

    def test_first_failed_up_releases_its_init_acquisition(self):self.cases('first-failure')

    def test_failed_nonlast_or_duplicate_pair_preserves_existing_owner(self):self.cases('nonlast-failure')

    def test_missing_wdev_unwinds_only_the_new_acquisition(self):self.cases('missing')

    def test_failed_cleanup_keeps_graph_and_preserves_original_up_error(self):self.cases('cleanup-busy')

    def test_successful_first_and_additional_vif_keep_owned_references(self):self.cases('success')

    def test_zero_count_and_missing_adapter_cannot_underflow_counter(self):self.cases('boundary')

    def test_stopping_quarantined_and_removing_states_reject_new_up(self):self.cases('init-guards')

    def test_last_down_requires_idle_before_wdev_close(self):self.cases('down')

    def test_deinit_propagates_last_backend_error_and_preserves_nonlast(self):self.cases('deinit')

    def test_whole_functions_and_source_status_contract_are_bound(self):
        self.assertEqual(len(h.CASE_NAMES),28)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(set(h.CASE_NAMES),{name for rows in h.CASE_GROUPS.values()for name in rows})
        self.assertEqual(len(h.function_manifest(self.texts)),10)
        for name,key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        for name,key in h.SOURCE_ONLY_FUNCTION_SOURCES.items():self.assertTrue(h.function(self.texts[key],name))
        self.assertIn(h.declarations(self.texts),self.generated)
        caller=h.function(self.texts['os'],'main_virtual_if_open')
        self.assertLess(caller.index('VIRTUAL_IF_INIT(pAd, net_dev)'),caller.index('VIRTUAL_IF_UP(pAd, net_dev)'))
        self.assertLess(caller.index('VIRTUAL_IF_UP(pAd, net_dev)'),caller.index('RT_MOD_INC_USE_COUNT();'))
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')

    def test_missing_rollback_and_unconditional_last_cleanup_are_rejected(self):
        mutations=(('VIRTUAL_IF_DEC(pAd);','(void)pAd;','first-up-failure'),
                   ('if (VIRTUAL_IF_NUM(pAd) == 0)\n\t\tmt_wifi_close','if (TRUE)\n\t\tmt_wifi_close','nonlast-up-failure'))
        body=h.function(self.texts['os'],'virtual_if_up_handler')
        for index,(before,after,selector)in enumerate(mutations):
            with self.subTest(selector=selector):
                self.assertEqual(body.count(before),1)
                texts=dict(self.texts);texts['os']=texts['os'].replace(body,body.replace(before,after))
                source=self.directory/('broken-rollback-'+str(index)+'.c');source.write_text(h.generate_source(texts))
                binary=source.with_suffix('')
                result=subprocess.run([shutil.which('clang'),'-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                    '-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
                self.assertEqual((result.returncode,result.stderr),(0,''),result.stderr)
                result=subprocess.run([str(binary),selector],capture_output=True,text=True,timeout=10)
                self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
