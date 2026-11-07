"""Bounded WTBL commands, response copies, firmware errors and owners."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import wtbl_tlv_harness as h

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ['-std=gnu99', '-O2', '-Wall', '-Wextra', '-Werror']
FIXTURE_SHAS = {
    'CmdExtWtblUpdate.c': 'e29df798da9f811e1ffc98f7e047f9d5abf7673ec000de542db593cba24ea716',
    'CmdExtWtblUpdateCb.c': 'a451301bea9c87799d2945f5044d49902f9f19ffdd64f58d1d9d75de783c651a',
    'AndesSendCmdMsg.c': '62c880a6a0f2dabc4cea9fb4d801f229a0b6b4b060ba8e4798bfe1e8a7f65173',
}


class WtblTlvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='wtbl-tlv-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {k: (ROOT / p).read_text() for k, p in h.SOURCE_PATHS.items()}
        cls.code = h.generate_source(cls.texts)
        cls.compilers = {'gcc': shutil.which('gcc-16') or shutil.which('gcc'), 'clang': shutil.which('clang')}
        if not all(cls.compilers.values()):
            raise AssertionError('GNU GCC and Clang required')
        version = subprocess.check_output([cls.compilers['gcc'], '--version'], text=True, timeout=10)
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('Genuine GNU GCC required')
        cls.binaries = {label: cls.build(cls.code, label, label) for label in cls.compilers}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def build(cls, code, name, label='clang', historical=False):
        source = cls.directory / (name + '.c'); source.write_text(code)
        binary = source.with_suffix('')
        flags = FLAGS + (['-Wno-pointer-sign'] if historical else [])
        if label == 'clang':
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        run = subprocess.run([cls.compilers[label], *flags, str(source), '-o', str(binary)], capture_output=True, text=True, timeout=60)
        if run.returncode or run.stderr:
            raise AssertionError(run.stderr)
        return binary

    def run_case(self, binary, case):
        run = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=5,
                             env=dict(os.environ, ASAN_OPTIONS='halt_on_error=1:symbolize=0', UBSAN_OPTIONS='halt_on_error=1'))
        self.assertEqual((run.returncode, run.stderr), (0, ''), run.stderr)
        return json.loads(run.stdout)

    def test_all_fifty_cases_gnu_and_clang_sanitizers(self):
        self.assertEqual(len(h.CASE_NAMES), 50)
        for label, binary in self.binaries.items():
            for case in h.CASE_NAMES:
                with self.subTest(compiler=label, case=case):
                    self.assertEqual(self.run_case(binary, case), h.EXPECTED_ROWS[case])

    def test_six_whole_functions_real_declarations_and_separate_transport_scope(self):
        self.assertEqual((len(h.FUNCTION_SOURCES), len(h.SOURCE_ONLY_FUNCTION_SOURCES), len(h.FIELDS)), (6, 4, 13))
        self.assertEqual(set(h.CASE_NAMES), set(h.EXPECTED_ROWS))
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.code.count(h.function(self.texts[key], name)), 1)
        self.assertEqual(len(h.function_manifest(self.texts)), 6)
        self.assertEqual(len(h.source_only_manifest(self.texts)), 4)
        self.assertNotIn(h.function(self.texts['core'], 'AndesSendCmdMsg'), self.code)
        self.assertTrue(h.MODEL_VARIANT['short_query_ACK_callback_semantics_not_transport_delivery_claim'])
        self.assertTrue(h.MODEL_VARIANT['kernel_cmd_msg_packet_scheduler_firmware_and_DMA_are_not_executed'])

    def test_actual_seventeen_packed_layout_sizes_match_independent_golden_values(self):
        types = ('GENERIC', 'RX', 'HT', 'VHT', 'PEER_PS', 'TX_PS', 'HDR_TRANS', 'SECURITY_KEY',
                 'BA', 'RDG', 'PROTECTION', 'CLEAR', 'BF', 'SMPS', 'RAW_DATA_RW', 'DUMP', 'SPE')
        assertions = '\n'.join('_Static_assert(sizeof(CMD_WTBL_' + name + '_T)==' + str(size) + ',"layout");'
                               for name, size in zip(types, h.TAG_SIZES))
        assertions += '\n_Static_assert(MAX_BUF_SIZE_OF_WTBL_INFO+100-sizeof(CMD_WTBL_UPDATE_T)==304,"capacity");'
        for label in self.compilers:
            self.build(self.code.replace('int main(', assertions + '\nint main(', 1), 'actual-layout-' + label, label)

    def test_bad_inputs_rejected_before_any_allocation_or_send(self):
        cases = ('bad-operation', 'null-adapter', 'null-set', 'null-nonzero', 'reset-payload',
                 'zero-buffer', 'short-header', 'zero-tlv-length', 'wrong-tlv-size', 'unknown-tag',
                 'over-capacity', 'length-overflow')
        for binary in self.binaries.values():
            for case in cases:
                row = self.run_case(binary, case)
                self.assertEqual((row['ret'], row['alloc_length'], row['packets'], row['msgs'], row['sends']), (2, 0, 0, 0, 0))

    def test_valid_maximum_duplicate_and_dump_queries_retain_capacity_and_release_owners(self):
        for binary in self.binaries.values():
            for case, cap, count in (('query-max-payload', 304, 38), ('query-dump', 260, 1), ('query-duplicate-raw', 32, 2)):
                row = self.run_case(binary, case)
                self.assertEqual((row['capacity'], row['elements'], row['changed'], row['live_packets'], row['live_msgs']), (cap, count, 1, 0, 0))

    def test_fixed_source60_fixtures_preserve_actual_historical_bodies(self):
        directory = ROOT / 'tests/fixtures/wtbl-tlv'
        metadata = json.loads((directory / 'manifest.json').read_text())
        self.assertEqual(set(metadata), set(FIXTURE_SHAS))
        for name, digest in FIXTURE_SHAS.items():
            raw = (directory / name).read_bytes()
            self.assertEqual(metadata[name]['source_commit'], '60ae6bf98bd46b68c648620c599f1aa78073131e')
            self.assertEqual(metadata[name]['sha256'], digest)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            body = raw.decode().rstrip('\n')
            self.assertEqual(h.function(body, name[:-2]), body)

    def test_old_builder_early_returns_leave_packet_and_message_owned(self):
        old = (ROOT / 'tests/fixtures/wtbl-tlv/CmdExtWtblUpdate.c').read_text().rstrip('\n')
        code = self.code.replace(h.function(self.texts['fw'], 'CmdExtWtblUpdate'), old, 1)
        for label in self.compilers:
            binary = self.build(code, 'historical-builder-' + label, label, historical=True)
            for case in ('bad-operation', 'null-set', 'reset-payload'):
                row = self.run_case(binary, case)
                self.assertEqual((row['sends'], row['live_packets'], row['live_msgs']), (0, 1, 1))

    def test_old_callback_does_not_propagate_firmware_rejection(self):
        old = (ROOT / 'tests/fixtures/wtbl-tlv/CmdExtWtblUpdateCb.c').read_text().rstrip('\n')
        code = self.code.replace(h.function(self.texts['fw'], 'CmdExtWtblUpdateCb'), old, 1)
        for label in self.compilers:
            binary = self.build(code, 'historical-callback-' + label, label, historical=True)
            self.assertEqual(self.run_case(binary, 'set-fw-error')['ret'], 1)
            self.assertEqual(h.EXPECTED_ROWS['set-fw-error']['ret'], 5)

    def reject(self, before, after, case, label):
        self.assertEqual(self.code.count(before), 1, before)
        binary = self.build(self.code.replace(before, after, 1), label)
        self.assertNotEqual(self.run_case(binary, case), h.EXPECTED_ROWS[case])

    def test_response_status_size_and_capacity_mutations_are_observable(self):
        mutations = (
            ('if (result.ucExTenCID != EXT_CMD_ID_WTBL_UPDATE)', 'if (FALSE)', 'wrong-cid', 'wrong-cid'),
            ('msg->cmd_return_status = le2cpu32(result.u4Status);', 'msg->cmd_return_status = NDIS_STATUS_SUCCESS;', 'set-fw-error', 'lost-status'),
            ('capacity = msg->wtbl_rsp_capacity;', 'capacity = msg->attr.ctrl.expect_size - 28;', 'query-expect-overwrite', 'mutable-capacity'),
            ('len != offset + capacity', 'len < offset + capacity', 'query-long', 'extra-response'),
            ('requested.u2Tag != tlv.u2Tag ||', 'FALSE ||', 'query-wrong-tag', 'wrong-query-tag'),
        )
        for before, after, case, name in mutations:
            with self.subTest(mutation=name):
                self.reject(before, after, case, name)

    def test_request_size_and_private_snapshot_mutations_are_observable(self):
        self.reject('tlv.u2Length != wtbl_tlv_size(tlv.u2Tag) ||', '(wtbl_tlv_size(tlv.u2Tag), FALSE) ||', 'wrong-tlv-size', 'lost-size-check')
        self.reject('AndesAppendCmdMsg(msg, (char *)payload, u4BufferLen);', 'AndesAppendCmdMsg(msg, (char *)pBuffer, u4BufferLen);', 'snapshot-copy', 'lost-private-snapshot')

    def test_missing_duplicate_source_and_declaration_drift_are_rejected(self):
        with self.assertRaises(ValueError):
            h.generate_source({})
        for name, key in {**h.FUNCTION_SOURCES, **h.SOURCE_ONLY_FUNCTION_SOURCES}.items():
            bad = dict(self.texts); bad[key] += '\n' + h.function(bad[key], name)
            with self.assertRaises(ValueError):
                h.generate_source(bad)
        bad = dict(self.texts); bad['header'] = bad['header'].replace('\tUINT32\t\twtbl_rsp_capacity;', '')
        with self.assertRaises(ValueError):
            h.generate_source(bad)
        bad = dict(self.texts); bad['asic'] = bad['asic'].replace('BA_SESSION_RECP = 2,', 'BA_SESSION_RECP = unknown,')
        with self.assertRaises(ValueError):
            h.generate_source(bad)

    def test_unknown_selector_is_rejected(self):
        for binary in self.binaries.values():
            run = subprocess.run([str(binary), 'unknown'], capture_output=True, text=True, timeout=5)
            self.assertEqual((run.returncode, run.stdout, run.stderr), (91, '', ''))


if __name__ == '__main__':
    unittest.main()
