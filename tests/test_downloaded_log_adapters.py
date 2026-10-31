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

from downloaded_log_harness import function, generate_source

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/downloaded-log-sources'
PINS = {
    'openssh-10.6p1-log.c': '7a74de1d23092e05f7b55e5fd9d38da6ff1c9b0620c682cde5b014f0511c00f6',
    'openvpn-2.6.23-error.c': '8ba73b3adcccf0a100e45bf49c2b5626de557629ac70cc482c450d3a554d8785',
    'openvpn-2.6.23-ps.c': '6e3fff87e34af3b71ac5d24f87fc1c436c5d807851f99c5d19dbfcf3605d3859',
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
        patches=[(package+'-bounded-log.patch',relative)]
        if package=='openvpn':
            ps=(FIXTURES/'openvpn-2.6.23-ps.c').read_bytes()
            if hashlib.sha256(ps).hexdigest()!=PINS['openvpn-2.6.23-ps.c']:
                raise AssertionError('Pinned port-share source excerpt changed')
            (tree/'src/openvpn/ps.c').write_bytes(ps)
            patches.append(('openvpn-bounded-port-share.patch','src/openvpn/ps.c'))
        for filename,expected in patches:
            patch = ROOT / 'trunk/user' / package / filename
            targets=__import__('re').findall(r'^\+\+\+ ([^\t\n ]+)',patch.read_text(),__import__('re').M)
            originals=__import__('re').findall(r'^--- ([^\t\n ]+)',patch.read_text(),__import__('re').M)
            if targets!=['b/'+expected] or originals!=['a/'+expected]:
                raise AssertionError('Unexpected package patch targets')
            subprocess.run(['patch', '--batch', '--force', '--fuzz=0', '-p1', '-i', str(patch)],
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
            if package=='openvpn':
                self.assertIn('for bounded_patch_file in openvpn-bounded-log.patch openvpn-bounded-port-share.patch;',makefile)
                self.assertIn('patch -d $(SRC_NAME) -p1 --batch --force --fuzz=0 -i ../$$bounded_patch_file || exit 1;',makefile)
            else:
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
                if package=='openvpn':
                    (target.parent/'ps.c').write_bytes((FIXTURES/'openvpn-2.6.23-ps.c').read_bytes())
                    shutil.copyfile(ROOT/'trunk/user/openvpn/openvpn-bounded-port-share.patch',
                                    parent/'openvpn-bounded-port-share.patch')
                command = ['make', '-f', str(ROOT / 'trunk/user' / package / 'Makefile'), 'extract_test']
                for _ in range(2):
                    result = subprocess.run(command, cwd=parent, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(target.read_text(), self.texts[package])
                    if package=='openvpn':
                        self.assertEqual((target.parent/'ps.c').read_text(),(self.root/'openvpn/src/openvpn/ps.c').read_text())
                if package=='openvpn':
                    # A previous build may have only the original central patch.
                    # Its independent reverse check must not unapply that patch.
                    ps=target.parent/'ps.c';ps.write_bytes((FIXTURES/'openvpn-2.6.23-ps.c').read_bytes())
                    result=subprocess.run(command,cwd=parent,capture_output=True,text=True,timeout=5)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual(target.read_text(),self.texts[package])
                    self.assertEqual(ps.read_text(),(self.root/'openvpn/src/openvpn/ps.c').read_text())
                    drift=(FIXTURES/'openvpn-2.6.23-ps.c').read_text().replace('    closelog();','    closelog(); /* changed input */')
                    ps.write_text(drift)
                    result=subprocess.run(command,cwd=parent,capture_output=True,text=True,timeout=5)
                    self.assertNotEqual(result.returncode,0,'drift must not silently reverse/apply source')
                    self.assertEqual(target.read_text(),self.texts[package])
                    self.assertEqual(ps.read_text(),drift)

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

    def test_vpn_port_share_cleanup_object_keeps_fd_without_libc_logger(self):
        original=(FIXTURES/'openvpn-2.6.23-ps.c').read_text()
        patched=(self.root/'openvpn/src/openvpn/ps.c').read_text()
        replacement=('    /* The bounded logger owns no persistent descriptor across fork().\n'
                     '     * Keep the inherited logging state unchanged in this forked child. */')
        self.assertEqual(patched,original.replace('    closelog();',replacement))
        preamble=('#include <syslog.h>\ntypedef int socket_descriptor_t;\n'
                  'extern void openvpn_close_socket(socket_descriptor_t);\n')
        wrapper='\nvoid fixture_close_fds(int keep) { close_fds_except(keep); }\n'
        objects={}
        for label,text in (('fixed',patched),('old',original)):
            source=self.root/('vpn-ps-'+label+'.c')
            source.write_text(preamble+function(text,'close_fds_except')+wrapper)
            output=self.root/('vpn-ps-'+label+'.o')
            built=subprocess.run(['clang','-std=gnu99','-O1','-Wall','-Wextra','-Werror',
                                  '-c',str(source),'-o',str(output)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            symbols=subprocess.run(['nm','-u',str(output)],capture_output=True,text=True)
            self.assertEqual(symbols.returncode,0,symbols.stdout+symbols.stderr)
            names={line.split()[-1].split('@')[0] for line in symbols.stdout.splitlines() if line.split()}
            if sys.platform=='darwin':names={(n[1:] if n.startswith('_') else n).split('$')[0] for n in names}
            self.assertIn('openvpn_close_socket',names)
            if label=='fixed':
                self.assertFalse(names&{'syslog','vsyslog','openlog','closelog','setlogmask'},names)
            else:self.assertIn('closelog',names,'actual old consumer must retain its libc import')
            objects[label]=output
        driver=self.root/'vpn-ps-driver.c'
        driver.write_text(r'''
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
extern void fixture_close_fds(int);
static int keep_fd,drop_fd,seen[101],bad;
void openvpn_close_socket(int fd)
{
    if(fd<3 || fd>100 || fd==keep_fd) { bad=1; return; }
    seen[fd]++;
    /* Only close this child's owned descriptor. Record the remaining
     * production3..100 loop rather than touching sanitizer/runtime fds. */
    if(fd==drop_fd && close(fd)!=0) bad=1;
}
int main(void)
{
    int own[2],fd;
    if(pipe(own)!=0) return 1;
    keep_fd=own[0];drop_fd=own[1];
    if(keep_fd<3 || drop_fd<3 || keep_fd>100 || drop_fd>100) return 2;
    fixture_close_fds(keep_fd);
    if(bad || fcntl(keep_fd,F_GETFD)<0) return 3;
    for(fd=3;fd<=100;fd++) if(seen[fd]!=(fd==keep_fd?0:1)) return 4;
    errno=0;
    if(fcntl(drop_fd,F_GETFD)!=-1 || errno!=EBADF) return 5;
    return close(keep_fd)!=0;
}
''')
        for name,flags in (('native',[]),('sanitized',['-fsanitize=address,undefined'])):
            binary=self.root/('vpn-ps-'+name)
            current_object=objects['fixed']
            if flags:
                current_object=self.root/'vpn-ps-fixed-sanitized.o'
                built=subprocess.run(['clang','-std=gnu99','-O1','-Wall','-Wextra','-Werror',*flags,
                                      '-c',str(self.root/'vpn-ps-fixed.c'),'-o',str(current_object)],capture_output=True,text=True)
                self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            linked=subprocess.run(['clang','-std=gnu99','-O1','-Wall','-Wextra','-Werror',*flags,
                                   str(driver),str(current_object),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(linked.returncode,0,linked.stdout+linked.stderr)
            ran=subprocess.run([str(binary)],capture_output=True,text=True,timeout=3)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertNotIn('AddressSanitizer',ran.stderr);self.assertNotIn('runtime error:',ran.stderr)


if __name__ == '__main__':
    unittest.main()
