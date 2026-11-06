"""MCU publication and per-sender ownership with inert hardware effects."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import dma_command_harness as h
ROOT=Path(__file__).resolve().parents[1]

class DmaCommandLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='k2p-dma-command-')
        cls.directory=Path(cls.temporary.name)
        cls.texts={key:(ROOT/path).read_text()for key,path in h.SOURCE_PATHS.items()}
        cls.generated=h.generate_source(cls.texts)
        source=cls.directory/'command.c';source.write_text(cls.generated)
        gnu=shutil.which('gcc-16')or shutil.which('gcc')
        if not gnu:raise AssertionError('GNU GCC required')
        version=subprocess.run([gnu,'--version'],check=True,capture_output=True,text=True,timeout=10).stdout
        if 'Free Software Foundation'not in version or'clang'in version.lower():raise AssertionError('True GNU GCC required')
        cls.binaries=[]
        for label,compiler in(('clang',shutil.which('clang')),('gcc',gnu)):
            if not compiler:raise AssertionError('Required compiler absent: '+label)
            binary=cls.directory/label
            flags=['-std=gnu99','-Os','-pthread','-Wall','-Wextra','-Werror',
                   '-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable']
            if label=='clang':flags+=['-fsanitize=address,undefined']
            result=subprocess.run([compiler,*flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            if result.returncode:raise AssertionError(result.stderr)
            cls.binaries.append(binary)
    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()
    def cases(self,group):
        self.assertTrue(h.CASE_GROUPS[group])
        for binary in self.binaries:
            for name in h.CASE_GROUPS[group]:
                with self.subTest(compiler=binary.name,case=name):
                    result=subprocess.run([str(binary),name],check=True,capture_output=True,text=True,timeout=20)
                    self.assertEqual(json.loads(result.stdout),h.EXPECTED_ROWS[name])
    def test_admission_failure_and_irq_async_ownership(self):self.cases('admission')
    def test_normal_ring_success_and_full_queue_sync_async(self):self.cases('normal')
    def test_firmware_download_ring_success_and_full_queue_sync_async(self):self.cases('firmware')
    def test_low_publication_requires_live_nonterminal_owner(self):self.cases('low-guard')
    def test_queued_terminal_failures_preserve_sync_sender(self):self.cases('queued-stop')
    def test_controller_not_initialized_and_missing_callback_fail_unpublished(self):self.cases('controller')
    def test_one_sender_drain_failure_cannot_free_or_fail_another_sender(self):self.cases('cross-sender')
    def test_terminal_rejection_cannot_retry_or_wait_on_freed_message(self):self.cases('retry')
    def test_controller_cleanup_distinguishes_waiter_and_transferred_metadata(self):self.cases('cleanup')
    def test_publication_and_stop_have_one_serialized_order(self):self.cases('interleaved')
    def test_wsys_firmware_status_or_missing_callback_reaches_waiting_sender(self):self.cases('wsys-fwack')
    def test_message_and_packet_barriers_reject_private_source_mutants(self):
        edits=(
            ('AndesTakeQueuedCmdMsg','if (entry == pending)','if (entry != NULL)','cross-sync-normal-fail'),
            ('AndesRejectUnpublishedCmdMsg','if (IS_CMD_MSG_NEED_SYNC_WITH_FW_FLAG_SET(msg))',
             'if (FALSE)','normal-sync-full'),
            ('AndesMTPciKickOutCmdMsgFwDlRing',
             'if (!pAd->dma_lifecycle_pinned || pAd->dma_stopping || pAd->dma_quarantined)',
             'if (FALSE)','low-stop-fw'),
            ('AndesForceFreeCmdMsg','if (ad && msg->retry_pkt && msg->retry_pkt != msg->net_pkt)',
             'if (FALSE)','async-retry-kick-fail'),
            ('AndesSendCmdMsg',' msg->attr.ext_type == EXT_CMD_ID_DEVINFO_UPDATE ||',' FALSE ||','wsys-dev-sync-error'),
            ('AndesSendCmdMsg','msg->cmd_return_status = NDIS_STATUS_FAILURE;','msg->cmd_return_status = NDIS_STATUS_SUCCESS;','wsys-dev-sync-noresponse'))
        for index,(name,old,new,case)in enumerate(edits):
            with self.subTest(function=name,case=case):
                body=h.function(self.texts[h.FUNCTION_SOURCES[name]],name)
                self.assertEqual(body.count(old),1)
                self.assertEqual(self.generated.count(body),1)
                source=self.directory/('mutant-'+str(index)+'.c')
                source.write_text(self.generated.replace(body,body.replace(old,new)))
                binary=source.with_suffix('')
                compiled=subprocess.run([shutil.which('clang'),'-std=gnu99','-Os','-pthread',
                    '-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-parameter',
                    '-Wno-unused-but-set-variable','-fsanitize=address,undefined',str(source),'-o',str(binary)],
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(compiled.returncode,0,compiled.stderr)
                result=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=20)
                self.assertTrue(result.returncode!=0 or json.loads(result.stdout)!=h.EXPECTED_ROWS[case])
    def test_whole_function_and_fixed_case_contract(self):
        names=[n for group in h.CASE_GROUPS.values()for n in group]
        self.assertEqual(set(names),set(h.CASE_NAMES));self.assertEqual(len(names),len(set(names)))
        self.assertEqual(set(h.EXPECTED_ROWS),set(h.CASE_NAMES))
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(self.generated.count(h.function(self.texts[key],name)),1)
        for name,key in h.SOURCE_ONLY_FUNCTION_SOURCES.items():self.assertTrue(h.function(self.texts[key],name))
        self.assertEqual(set(h.function_manifest(self.texts)),set(h.FUNCTION_SOURCES))
        with self.assertRaises(ValueError):h.generate_source({})
        with self.assertRaises(ValueError):h.generate_source(self.texts,'legacy')

if __name__=='__main__':unittest.main()
