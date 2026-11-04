"""Repaired whole token/HIF functions under private native allocator controls."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import token_init_harness as h

ROOT = Path(__file__).resolve().parents[1]


class TokenInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-current-token-init-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {key:(ROOT/path).read_text() for key,path in h.SOURCE_PATHS.items()}
        cls.generated = h.generate_source(cls.texts)
        source = cls.directory/'token.c';source.write_text(cls.generated)
        gnu = shutil.which('gcc-16')
        if gnu is None and Path('/opt/homebrew/bin/gcc-16').is_file():gnu='/opt/homebrew/bin/gcc-16'
        if gnu is None:gnu=shutil.which('gcc')
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('GCC control requires GNU GCC, not a compiler alias')
        cls.binaries=[]
        for name,compiler in (('clang',shutil.which('clang')),('gcc',gnu)):
            if not compiler:raise AssertionError('Required compiler absent: '+name)
            binary=cls.directory/name
            # The whole legacy functions contain unused OS-adapter parameters
            # and a pre-existing unused local; retain every other warning.
            flags=['-std=gnu99','-Os','-Wall','-Wextra','-Werror',
                   '-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-but-set-variable']
            if name=='clang':flags+=['-fsanitize=address,undefined']
            result=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],
                                  capture_output=True,text=True,timeout=30)
            if result.returncode:raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def cases(self,names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(compiler=binary.name,case=name):
                    result=subprocess.run([str(binary),name],check=True,capture_output=True,text=True,timeout=10)
                    row=json.loads(result.stdout)
                    self.assertEqual(row,h.EXPECTED_ROWS[name])
                    self.assertTrue(all(type(value)is int for value in row))

    def test_each_allocation_failure_rolls_back_and_can_retry(self):
        self.cases(h.CASE_NAMES[:7])

    def test_complete_owner_and_repeated_init_preserve_existing_queues(self):
        self.cases(('token-normal','token-repeat-owner'))

    def test_queue_init_preserves_both_published_and_unpublished_owners(self):
        self.cases(('queue-repeat','queue-unpublished-owner'))

    def test_hif_propagates_ring_or_token_failure_before_hardware_init(self):
        self.cases(('hif-ring-failure','hif-token-oom','hif-normal'))

    def test_repeated_hif_init_does_not_free_an_existing_owner(self):
        self.cases(('hif-existing-owner','hif-direct-existing-owner'))

    def test_invalid_init_arguments_do_not_allocate_or_publish(self):
        self.cases(('null-output','null-adapter'))

    def test_model_binds_complete_current_functions_and_actual_header_structs(self):
        self.assertEqual(len(h.CASE_NAMES),18)
        self.assertEqual(set(h.CASE_NAMES),set(h.EXPECTED_ROWS))
        self.assertEqual(len(h.FIELDS),16)
        for name,key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        self.assertEqual(len(h.function_manifest(self.texts)),6)
        self.assertIn(h.declarations(self.texts['header']),self.generated)
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')
        for binary in self.binaries:
            bad=subprocess.run([str(binary),'unlisted'],capture_output=True,timeout=5)
            self.assertEqual(bad.returncode,91)


if __name__=='__main__':unittest.main()
