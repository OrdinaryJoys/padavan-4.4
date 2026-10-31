"""Actual central logger bodies plus pinned upstream patches; private Unix IO.

SSH's full do_log and VPN open/close are executed with inert surrounding
services. VPN's exact central output expression is tested separately; this
does not run either daemon, authenticate, open a tunnel, or use system syslog.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

from downloaded_log_harness import generate_source

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/downloaded-log-sources'
PINS = {
    'openssh-10.6p1-log.c': '7a74de1d23092e05f7b55e5fd9d38da6ff1c9b0620c682cde5b014f0511c00f6',
    'openvpn-2.6.23-error.c': '8ba73b3adcccf0a100e45bf49c2b5626de557629ac70cc482c450d3a554d8785',
    'smartdns-ba282c8-dns_conf.c': 'c917e70441ef1cef51a4a812a31d72809ec232110174aeaab132029ea2886a5e',
}


def patched_sources(directory):
    texts = {}
    for package, fixture, relative in (
        ('openssh', 'openssh-10.6p1-log.c', 'log.c'),
        ('openvpn', 'openvpn-2.6.23-error.c', 'src/openvpn/error.c'),
        ('smartdns', 'smartdns-ba282c8-dns_conf.c', 'src/dns_conf.c'),
    ):
        data = (FIXTURES / fixture).read_bytes()
        if hashlib.sha256(data).hexdigest() != PINS[fixture]:
            raise AssertionError('Pinned upstream source excerpt changed')
        tree = directory / package
        target = tree / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        patch = ROOT / 'trunk/user' / package / (package + '-bounded-log.patch')
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)],
                       cwd=tree, check=True, capture_output=True)
        texts[package] = target.read_text()
    return texts


class DownloadedLogAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-ssh-vpn-log-', dir='/tmp')
        cls.root = Path(cls.temp.name).resolve()
        cls.path = str(cls.root / 'log').replace('/private/tmp/', '/tmp/')
        cls.texts = patched_sources(cls.root)
        compiler = shutil.which('clang') or shutil.which('cc')
        if not compiler:
            raise AssertionError('C compiler required')
        inputs = dict(cls.texts, header=(ROOT / 'trunk/user/shared/bounded_syslog.h').read_text(),
                      udpxy_util=(ROOT / 'trunk/user/udpxy/util.c').read_text(),
                      xl2tpd_misc=(ROOT / 'trunk/user/xl2tpd/misc.c').read_text(),
                      iapp=(ROOT / 'trunk/user/ralinkiappd/rtmpiapp.c').read_text(),
                      lanauth=(ROOT / 'trunk/user/lanauth/lanauth.c').read_text())
        code = generate_source(inputs, cls.path)
        cfile = cls.root / 'probe.c'
        cfile.write_text(code)
        cls.probes = []
        for name, flags in [('native', []), ('sanitized', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
            probe = cls.root / name
            result = subprocess.run([compiler, '-std=gnu99', '-Wall', '-Wextra', '-Werror', *flags,
                                     str(cfile), '-o', str(probe)], capture_output=True, text=True)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.probes.append(probe)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.receiver.bind(self.path)
        self.receiver.settimeout(0.1)

    def tearDown(self):
        self.receiver.close()
        if Path(self.path).exists():
            Path(self.path).unlink()

    def invoke(self, probe, mode=0, repeat=1, message='literal %n %s %%', expected_exit=0):
        result = subprocess.run([str(probe), str(mode), str(repeat), message],
                                capture_output=True, text=True, timeout=3,
                                env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=' + ('1' if sys.platform.startswith('linux') else '0')})
        self.assertEqual(result.returncode, expected_exit, (result.stdout, result.stderr))
        self.assertNotIn('runtime error:', result.stderr)
        self.assertNotIn('AddressSanitizer', result.stderr)
        return json.loads(result.stdout) if expected_exit == 0 else None

    def frame(self):
        return self.receiver.recv(2048).rstrip(b'\0')

    def drain(self):
        while True:
            try:
                self.receiver.recv(2048)
            except socket.timeout:
                return

    def fill(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
            sender.setblocking(False)
            for count in range(10000):
                try:
                    sender.sendto(b'private-fill', self.path)
                except OSError as error:
                    if error.errno in (errno.EAGAIN, errno.ENOBUFS):
                        self.assertGreater(count, 0)
                        return
                    raise
        self.fail('Private socket did not saturate')

    def test_ssh_priority_pid_and_literal_percent(self):
        for probe in self.probes:
            self.invoke(probe)
            frame = self.frame()
            self.assertTrue(frame.startswith(b'<38>'), frame)
            self.assertRegex(frame, rb'ssh-adapter\[[0-9]+\]: literal %n %s %%$')

    def test_vpn_priority_prefix_context_and_close(self):
        for probe in self.probes:
            self.assertEqual(self.invoke(probe, mode=1), {'null_calls': 1})
            frame = self.frame()
            self.assertTrue(frame.startswith(b'<29>'), frame)
            self.assertRegex(frame, rb'vpn-adapter\[[0-9]+\]: client literal %n %s %%$')

    def test_queue_pressure_returns_and_recovers_for_both_adapters(self):
        for probe in self.probes:
            for mode in (0, 1):
                self.fill()
                start = time.monotonic()
                self.invoke(probe, mode=mode, repeat=128)
                self.assertLess(time.monotonic() - start, 2)
                self.drain()
                self.invoke(probe, mode=mode, message='after-drain')
                self.assertTrue(self.frame().endswith(b'after-drain'))

    def test_ssh_level_filter_and_force_are_preserved(self):
        for probe in self.probes:
            self.invoke(probe, mode=2)
            with self.assertRaises(socket.timeout):
                self.frame()
            self.invoke(probe, mode=5)
            frame = self.frame()
            self.assertTrue(frame.startswith(b'<39>'), frame)
            self.assertTrue(frame.endswith(b'debug1: literal %n %s %%'), frame)

    def test_ssh_error_label_and_existing_500_byte_limit(self):
        for probe in self.probes:
            self.invoke(probe, mode=4, message='x' * 2000)
            frame = self.frame()
            self.assertTrue(frame.startswith(b'<35>'), frame)
            body = frame.split(b']: ', 1)[1]
            self.assertEqual(body, b'error: ' + b'x' * 493)

    def test_missing_receiver_returns_without_creating_files(self):
        self.receiver.close()
        Path(self.path).unlink()
        for probe in self.probes:
            for mode in (0, 1):
                self.invoke(probe, mode=mode, repeat=128)
        self.assertFalse(Path(self.path).exists())

    def test_package_rules_apply_the_explicit_patch(self):
        for package in ('openssh', 'openvpn', 'smartdns'):
            makefile = (ROOT / 'trunk/user' / package / 'Makefile').read_text()
            self.assertIn('patch -d $(SRC_NAME) -p1 --batch --fuzz=0 -i ../' + package + '-bounded-log.patch || exit 1;', makefile)
            self.assertIn('-R --force --dry-run --batch --fuzz=0', makefile)
            self.assertNotIn('-Dsyslog=', makefile)
            self.assertIn('padavan_log_write(', self.texts[package])

    def test_actual_extract_targets_update_existing_trees_and_are_idempotent(self):
        with tempfile.TemporaryDirectory(prefix='k2p-existing-log-source-') as temp:
            for package, fixture, version, relative in (
                ('openssh', 'openssh-10.6p1-log.c', '10.6p1', 'log.c'),
                ('openvpn', 'openvpn-2.6.23-error.c', '2.6.23', 'src/openvpn/error.c'),
                ('smartdns', 'smartdns-ba282c8-dns_conf.c', 'ba282c8', 'src/dns_conf.c'),
            ):
                parent = Path(temp) / package
                target = parent / (package + '-' + version) / relative
                target.parent.mkdir(parents=True)
                target.write_bytes((FIXTURES / fixture).read_bytes())
                patch = package + '-bounded-log.patch'
                shutil.copyfile(ROOT / 'trunk/user' / package / patch, parent / patch)
                command = ['make', '-f', str(ROOT / 'trunk/user' / package / 'Makefile'), 'extract_test']
                for _ in range(2):
                    result = subprocess.run(command, cwd=parent, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(target.read_text(), self.texts[package])

    def test_failed_base_patch_stops_before_bounded_patch(self):
        with tempfile.TemporaryDirectory(prefix='k2p-failed-log-patch-') as temp:
            parent = Path(temp)
            original = FIXTURES / 'openssh-10.6p1-log.c'
            with tarfile.open(parent / 'openssh-10.6p1.tar.gz', 'w:gz') as archive:
                archive.add(original, arcname='openssh-10.6p1/log.c')
            (parent / 'openssh-orig.patch').write_text('deliberately invalid fixture patch\n')
            shutil.copyfile(ROOT / 'trunk/user/openssh/openssh-bounded-log.patch', parent / 'openssh-bounded-log.patch')
            result = subprocess.run(['make', '-f', str(ROOT / 'trunk/user/openssh/Makefile'), 'extract_test'],
                                    cwd=parent, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((parent / 'openssh-10.6p1/log.c').read_bytes(), original.read_bytes())

    def test_udpxy_error_text_and_local0_facility(self):
        for probe in self.probes:
            self.invoke(probe, mode=6)
            frame = self.frame()
            self.assertTrue(frame.startswith(b'<131>'), frame)
            self.assertIn(b']: literal %n %s %%: ', frame)
            self.assertTrue(frame.endswith(os.strerror(errno.EDOM).encode()), frame)

    def test_l2tp_and_iapp_keep_tags_priorities_and_literal_text(self):
        for probe in self.probes:
            for mode, tag in ((7, b'xl2tpd'), (8, b'iappd')):
                self.invoke(probe, mode=mode)
                frame = self.frame()
                self.assertTrue(frame.startswith(b'<28>'), frame)
                self.assertRegex(frame, tag + rb'\[[0-9]+\]: literal %n %s %%$')

    def test_smartdns_config_failure_logs_and_preserves_return_path(self):
        for probe in self.probes:
            self.invoke(probe, mode=10, message='literal%n.fixture')
            frame = self.frame()
            self.assertTrue(frame.startswith(b'<141>'), frame)
            self.assertTrue(frame.endswith(b"smartdns: process config file 'literal%n.fixture' failed at line 13."), frame)

    def test_lanauth_fatal_logs_once_and_exits_with_original_status(self):
        for probe in self.probes:
            self.invoke(probe, mode=9, expected_exit=1)
            frame = self.frame()
            self.assertTrue(frame.startswith(b'<27>'), frame)
            self.assertRegex(frame, rb'lanauth\[[0-9]+\]: literal %n %s %%$')

    def test_network_component_pressure_and_recovery(self):
        for probe in self.probes:
            for mode in (6, 7, 8, 9, 10):
                self.fill()
                start = time.monotonic()
                self.invoke(probe, mode=mode, repeat=1 if mode == 9 else 128,
                            expected_exit=1 if mode == 9 else 0)
                self.assertLess(time.monotonic() - start, 2)
                self.drain()
                self.invoke(probe, mode=mode, message='after-drain', expected_exit=1 if mode == 9 else 0)
                self.assertIn(b'after-drain', self.frame())

    def test_l2tp_empty_error_state_and_newline_cleanup(self):
        for probe in self.probes:
            for message in ('', 'plain error', 'error with newline\n', 'x' * 1024):
                self.invoke(probe, mode=11, message=message)
            with self.assertRaises(socket.timeout):
                self.frame()


if __name__ == '__main__':
    unittest.main()
