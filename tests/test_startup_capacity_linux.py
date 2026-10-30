"""Real bounded tmpfs replay; services/keys/publication effects stay in fixtures."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_BYTES = 1792 * 1024
FIRMWARE_BYTES = 9_607_128


def payload(header):
    data = header.encode()
    filler = b'# public capacity fixture\n'
    data += (filler * ((CONFIG_BYTES - len(data)) // len(filler) + 1))[:CONFIG_BYTES - len(data)]
    return data[:-1] + b'\n'


def namespace_case(kind):
    # Imported as a module, never exposed as another TestCase to discovery.
    import test_startup_config_policy as policy
    cls = policy.StartupPolicyFixture
    cls.setUpClass()
    fixture = cls(unittest.defaultTestLoader.getTestCaseNames(cls)[0])
    mounted = []
    try:
        fixture.setUp()
        etc = fixture.base / 'bounded-etc'
        etc.mkdir()
        for directory, size, mode in ((etc, '6M', '0755'), (fixture.work_root, '24M', '0700')):
            subprocess.run(['mount', '-n', '-t', 'tmpfs', '-o', f'size={size},mode={mode}',
                            'tmpfs', str(directory)], check=True, capture_output=True)
            mounted.append(directory)
        old_storage = fixture.storage
        fixture.storage = etc / 'storage'
        shutil.copytree(old_storage, fixture.storage)
        fixture.dnsdir = fixture.storage / 'dnsmasq'
        fixture.sshdir = fixture.storage / 'openssh'
        fixture.custom = fixture.dnsdir / 'dnsmasq.conf'
        fixture.sshconfig = fixture.sshdir / 'sshd_config'
        fixture.env.update(SSH_CONFIG=str(fixture.sshconfig), SSH_KEYDIR=str(fixture.sshdir),
                           DNS_CONFIG=str(fixture.custom))
        for script in fixture.scripts.values():
            script.write_text(script.read_text().replace(str(old_storage), str(fixture.storage)))
        fixture.main.write_text('port=0\nconf-file=' + str(fixture.custom) + '\n')
        # Use the real capacity reading, not portable host-test df estimates.
        (fixture.bin / 'df').unlink(missing_ok=True)
        (fixture.bin / 'stat').unlink(missing_ok=True)
        # Parser stubs record bounded metadata; a 64KiB validator log limit
        # must not be defeated by the fixture writing megabytes to EVENT_LOG.
        for stub in fixture.bin.iterdir():
            text = stub.read_text()
            text = text.replace("{'kind':kind,**values}",
                                "{'kind':kind,**{k:(len(v) if k=='config' else v) for k,v in values.items()}}")
            stub.write_text(text)
        publisher = fixture.base / 'namespace-publisher'
        compiler = '/usr/lib/llvm-14/bin/clang' if Path('/usr/lib/llvm-14/bin/clang').exists() else 'clang'
        subprocess.run([compiler, '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                        '-DSTARTUP_CONFIG_TEST_UID=geteuid()',
                        f'-DSTORAGE_OPERATION_DIR="{fixture.base / "namespace-operation"}"',
                        f'-DSTARTUP_CONFIG_STAGE_DIR="{etc}"',
                        str(ROOT / 'trunk/user/scripts/storage_validate.c'), '-o', str(publisher)],
                       check=True, capture_output=True)
        fixture.env['REAL_PUBLISHER'] = str(publisher)
        dns_header = 'dhcp-ignore=tag:untrusted\nlocal-service\n'
        ssh_header = 'PasswordAuthentication no\nAllowTcpForwarding no\nPermitRootLogin prohibit-password\n'
        if kind == 'dns-migration':
            dns_header = 'gfwlist=/tmp/public-unused-fixture\n' + dns_header
        if kind == 'ssh-migration':
            ssh_header = 'HostKey ' + str(fixture.sshdir / 'ssh_host_dsa_key') + '\n' + ssh_header
        original_dns, original_ssh = payload(dns_header), payload(ssh_header)
        fixture.custom.write_bytes(original_dns)
        fixture.sshconfig.write_bytes(original_ssh)
        with (fixture.work_root / 'synthetic-upload.trx').open('wb') as stream:
            remaining = FIRMWARE_BYTES
            while remaining:
                chunk = b'x' * min(remaining, 1024 * 1024)
                stream.write(chunk)
                remaining -= len(chunk)
        free_before = os.statvfs(etc).f_bavail * os.statvfs(etc).f_frsize
        assert free_before < 2 * CONFIG_BYTES, 'fixture did not reproduce the old staging shortage'
        for name in ('dns', 'ssh'):
            result = fixture.run_script(name)
            assert result.returncode == 0, (kind, name, result.returncode, result.stdout, result.stderr)
        assert len(fixture.events('ssh-start')) == 1
        if kind == 'unchanged':
            assert fixture.custom.read_bytes() == original_dns
            assert fixture.sshconfig.read_bytes() == original_ssh
            assert not fixture.events('publish')
        else:
            parent, old, current = ((fixture.dnsdir, original_dns, fixture.custom)
                                    if kind == 'dns-migration' else (fixture.sshdir, original_ssh, fixture.sshconfig))
            backups = list((parent / '.config-backups').glob('*.before-migration*'))
            assert len(backups) == 1 and backups[0].read_bytes() == old
            assert (parent / '.config-backups').stat().st_mode & 0o777 == 0o700
            assert current.read_bytes() != old and current.stat().st_mode & 0o777 == 0o600
        assert not list(fixture.work_root.glob('.*-startup.*'))
        assert not list(etc.glob('.config-publish.*'))
        return {'case': kind, 'status': 'PASS', 'etc_bytes': 6 * 1024 * 1024,
                'tmp_bytes': 24 * 1024 * 1024, 'config_bytes_each': CONFIG_BYTES,
                'synthetic_firmware_bytes': FIRMWARE_BYTES, 'free_etc_before': free_before,
                'dns_exit': 0, 'ssh_exit': 0, 'old_two_copy_staging_cannot_fit': True}
    finally:
        for directory in reversed(mounted):
            subprocess.run(['umount', str(directory)], check=True, capture_output=True)
        if hasattr(fixture, 'temp'):
            fixture.tearDown()
        cls.tearDownClass()


@unittest.skipUnless(sys.platform.startswith('linux'), 'Real tmpfs namespaces require Linux')
class StartupCapacityLinuxTests(unittest.TestCase):
    def test_two_large_configs_with_firmware_and_atomic_migration_fit_real_tmpfs(self):
        command = (['sudo', '-n'] if os.geteuid() else []) + [
            'env', 'PATH=' + os.environ['PATH'], 'unshare', '--mount', '--fork',
            '--kill-child=KILL', '--propagation', 'private', sys.executable,
            str(Path(__file__).resolve()), '--namespace-child']
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        records = json.loads(result.stdout)
        self.assertEqual([row['case'] for row in records], ['unchanged', 'dns-migration', 'ssh-migration'])
        self.assertTrue(all(row['status'] == 'PASS' for row in records))


if __name__ == '__main__' and sys.argv[1:] == ['--namespace-child']:
    if os.geteuid() != 0 or not sys.platform.startswith('linux'):
        raise SystemExit('Isolated Linux root child required')
    if os.stat('/proc/self/ns/mnt').st_ino == os.stat('/proc/1/ns/mnt').st_ino:
        raise SystemExit('Private mount namespace required')
    root_mounts = [line.split() for line in Path('/proc/self/mountinfo').read_text().splitlines()
                   if line.split()[4] == '/']
    if len(root_mounts) != 1 or any(field.startswith('shared:')
            for field in root_mounts[0][6:root_mounts[0].index('-')]):
        raise SystemExit('Private mount propagation required')
    print(json.dumps([namespace_case(kind) for kind in ('unchanged', 'dns-migration', 'ssh-migration')]))
elif __name__ == '__main__':
    unittest.main()
