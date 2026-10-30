#!/usr/bin/env python3
"""Replay actual DNS/SSH startup scripts using private config and daemon stubs.

Validation outcomes are controlled; no router, daemon listener, real key, or
system configuration is touched. Publication uses the shipped C rename helper.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartupPolicyFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-startup-code-')
        cls.publisher = Path(cls.build.name)/'storage_validate'
        subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                        str(ROOT/'trunk/user/scripts/storage_validate.c'), '-o', str(cls.publisher)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='k2p-startup-policy-')
        self.base = Path(self.temp.name)
        self.storage = self.base/'storage'
        self.dnsdir = self.storage/'dnsmasq'
        self.sshdir = self.storage/'openssh'
        self.dnsdir.mkdir(parents=True)
        self.sshdir.mkdir()
        self.custom = self.dnsdir/'dnsmasq.conf'
        self.main = self.base/'main.conf'
        self.sshconfig = self.sshdir/'sshd_config'
        self.log = self.base/'events'
        self.bin = self.base/'bin'
        self.bin.mkdir()
        self.env = {**os.environ, 'PATH': str(self.bin)+':'+os.environ['PATH'],
                    'EVENT_LOG': str(self.log), 'SSH_CONFIG': str(self.sshconfig),
                    'SSH_KEYDIR': str(self.sshdir), 'DNS_CONFIG': str(self.custom), 'FILTER_AAAA': '0', 'MIN_TTL': '0',
                    'REAL_PUBLISHER': str(self.publisher)}
        for key in ('ssh_host_rsa_key', 'ssh_host_ed25519_key'):
            (self.sshdir/key).write_text('synthetic key; never used for cryptography')
        self.custom.write_text('dhcp-ignore=tag:untrusted\nlocal-service\n')
        self.main.write_text('port=0\nconf-file='+str(self.custom)+'\n')
        self.sshconfig.write_text('PasswordAuthentication no\nAllowTcpForwarding no\nPermitRootLogin prohibit-password\n')
        common = r'''
import hashlib, json, os, pathlib, sys
args=sys.argv[1:]
def emit(kind, **values):
    with open(os.environ['EVENT_LOG'],'a') as stream:
        stream.write(json.dumps({'kind':kind,**values})+'\n')
'''
        self.stub('logger', common + "emit('log', message=' '.join(args))\n")
        self.stub('nvram', common + "assert args[0]=='get'\nprint(os.environ['FILTER_AAAA'] if args[1]=='dhcp_filter_aaa' else os.environ['MIN_TTL'])\n")
        self.stub('md5sum', common + "p=pathlib.Path(args[0]); print(hashlib.md5(p.read_bytes()).hexdigest()+'  '+str(p))\n")
        self.stub('storage_validate', common + "emit('publish', arguments=args)\nif os.environ.get('PUBLISH_FAIL')=='1': sys.exit(1)\nos.execv(os.environ['REAL_PUBLISHER'],[os.environ['REAL_PUBLISHER'],*args])\n")
        self.stub('ssh-keygen', common + "emit('keygen')\np=pathlib.Path(os.environ['SSH_KEYDIR'])\nfor name in ['ssh_host_rsa_key','ssh_host_ed25519_key']: (p/name).write_text('synthetic key')\n")
        self.stub('ssh', common + r'''
assert args==['-Q','key']
emit('keyquery')
if os.environ.get('KEY_QUERY_FAIL')=='1': sys.exit(1)
print('ssh-ed25519\nssh-rsa')
if os.environ.get('DSA_SUPPORTED')=='1': print('ssh-dss')
''')
        self.stub('dnsmasq', common + r'''
assert args[:2]==['--test','-C']
p=pathlib.Path(args[2]); text=p.read_text()
includes=[line.split('=',1)[1] for line in text.splitlines() if line.startswith('conf-file=')]
custom='\n'.join(pathlib.Path(name).read_text() for name in includes)
emit('dns-test', path=str(p), config=custom)
if os.environ.get('CHANGE_CUSTOM_POLICY')=='1': pathlib.Path(os.environ['DNS_CONFIG']).write_text('dhcp-ignore=tag:new-restriction\n')
if os.environ.get('DNS_FAIL')=='1' or 'BadDirective' in text+custom or any(line.lstrip().startswith('gfwlist=') for line in custom.splitlines()):
    print('bad option in private fixture',file=sys.stderr); sys.exit(1)
''')
        self.stub('sshd', common + r'''
if '-t' in args:
    p=pathlib.Path(args[args.index('-f')+1]); text=p.read_text()
    emit('ssh-test',path=str(p),config=text)
    if os.environ.get('CHANGE_STORED_POLICY')=='1' and p.name=='candidate': pathlib.Path(os.environ['SSH_CONFIG']).write_text('PasswordAuthentication no\nAllowUsers new-restriction\n')
    if os.environ.get('APPEAR_DURING_DEFAULT')=='1' and p.name=='default':
        pathlib.Path(os.environ['SSH_CONFIG']).write_text('PasswordAuthentication no\nAllowUsers restricted\n')
    if os.environ.get('DEFAULT_FAIL')=='1' and p.name=='default': sys.exit(1)
    bad='BadDirective' in text
    for line in text.splitlines():
        if line.startswith('Include '): bad=bad or 'BadDirective' in pathlib.Path(line[8:]).read_text()
        if line.startswith('HostKey ') and line.split()[1].endswith('/ssh_host_dsa_key') and os.environ.get('DSA_SUPPORTED')!='1': bad=True
    if bad: print('bad configuration in private fixture',file=sys.stderr); sys.exit(1)
else:
    emit('ssh-start',arguments=args,config=pathlib.Path(os.environ['SSH_CONFIG']).read_text())
    sys.exit(int(os.environ.get('DAEMON_STATUS','0')))
''')
        mapping = {'/etc/storage/openssh': str(self.sshdir), '/etc/storage/dnsmasq': str(self.dnsdir),
                   '/etc/storage': str(self.storage), '/etc/dnsmasq.conf': str(self.main),
                   '/usr/sbin/dnsmasq': str(self.bin/'dnsmasq'), '/usr/sbin/sshd': str(self.bin/'sshd'),
                   '/usr/bin/ssh-keygen': str(self.bin/'ssh-keygen'), '/usr/bin/ssh': str(self.bin/'ssh'),
                   '/sbin/storage_validate': str(self.bin/'storage_validate'), '/var/run/utmp': str(self.base/'utmp')}
        self.scripts = {}
        for name, relative in [('dns', 'trunk/user/dnsmasq/dnsmasq.sh'), ('ssh', 'trunk/user/openssh/sshd.sh')]:
            text = (ROOT/relative).read_text()
            for old in sorted(mapping, key=len, reverse=True): text=text.replace(old,mapping[old])
            path=self.base/(name+'.sh');path.write_text(text);self.scripts[name]=path

    def tearDown(self):
        self.temp.cleanup()

    def stub(self, name, code):
        path=self.bin/name;path.write_text('#!/usr/bin/env python3\n'+code);path.chmod(0o755)

    def run_script(self, name, **changes):
        args=['sh',str(self.scripts[name])]+(['start'] if name=='ssh' else [])
        result=subprocess.run(args,env={**self.env,**changes},text=True,capture_output=True,timeout=10)
        self.assertFalse(list(self.dnsdir.glob('.startup.*')))
        self.assertFalse(list(self.sshdir.glob('.startup.*')))
        return result

    def events(self, kind):
        import json
        return [row for row in map(json.loads,self.log.read_text().splitlines()) if row['kind']==kind] if self.log.exists() else []

    def add_dsa(self, text=None):
        old=text if text is not None else self.sshconfig.read_text()
        value='HostKey '+str(self.sshdir/'ssh_host_dsa_key')+'\n'+old
        self.sshconfig.write_text(value)
        return value


class DNSStartupPolicyTests(StartupPolicyFixture):
    def test_invalid_custom_policy_is_preserved_without_empty_defaults(self):
        original='dhcp-ignore=tag:untrusted\nlocal-service\nBadDirective yes\nfilter-aaaa\n'
        self.custom.write_text(original)
        result=self.run_script('dns')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.custom.read_text(),original)
        self.assertIn('automatic defaults disabled',result.stderr)
        self.assertEqual(self.events('publish'),[])
        self.assertEqual(list(self.dnsdir.glob('*.before-migration*')),[])

    def test_policy_changed_during_validation_is_not_overwritten(self):
        result=self.run_script('dns',CHANGE_CUSTOM_POLICY='1')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.custom.read_text(),'dhcp-ignore=tag:new-restriction\n')
        self.assertEqual(self.events('publish'),[])

    def test_invalid_generated_main_does_not_discard_valid_custom_policy(self):
        original=self.custom.read_bytes();self.main.write_text(self.main.read_text()+'BadDirective yes\n')
        self.assertNotEqual(self.run_script('dns').returncode,0)
        self.assertEqual(self.custom.read_bytes(),original)
        self.assertEqual(self.events('publish'),[])

    def test_known_legacy_migration_keeps_original_and_restrictive_lines(self):
        original=self.custom.read_text()+'gfwlist=/etc/storage/legacy.list\n'
        self.custom.write_text(original)
        self.assertEqual(self.run_script('dns').returncode,0)
        backups=list(self.dnsdir.glob('dnsmasq.conf.before-migration*'))
        self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(),original)
        self.assertEqual(backups[0].stat().st_mode&0o777,0o600)
        self.assertIn('dhcp-ignore=tag:untrusted',self.custom.read_text())
        self.assertIn('#gfwlist=',self.custom.read_text())
        self.assertEqual(len(self.events('publish')),1)

    def test_publish_failure_keeps_original_restrictive_policy(self):
        original=self.custom.read_text()+'gfwlist=/old\n';self.custom.write_text(original)
        self.assertNotEqual(self.run_script('dns',PUBLISH_FAIL='1').returncode,0)
        self.assertEqual(self.custom.read_text(),original)
        self.assertEqual((self.dnsdir/'dnsmasq.conf.before-migration').read_text(),original)

    def test_first_boot_missing_custom_is_created_only_after_validation(self):
        self.custom.unlink()
        self.assertNotEqual(self.run_script('dns',DNS_FAIL='1').returncode,0)
        self.assertFalse(self.custom.exists())
        self.assertEqual(self.run_script('dns').returncode,0)
        self.assertTrue(self.custom.is_file())
        self.assertEqual(self.custom.stat().st_mode&0o777,0o600)

    def test_existing_backup_is_not_overwritten_and_second_start_does_not_remigrate(self):
        (self.dnsdir/'dnsmasq.conf.before-migration').write_text('prior evidence')
        self.custom.write_text(self.custom.read_text()+'gfwlist=/old\n')
        self.assertEqual(self.run_script('dns').returncode,0)
        self.assertEqual((self.dnsdir/'dnsmasq.conf.before-migration').read_text(),'prior evidence')
        self.assertTrue((self.dnsdir/'dnsmasq.conf.before-migration.1').exists())
        publications=len(self.events('publish'))
        self.assertEqual(self.run_script('dns').returncode,0)
        self.assertEqual(len(self.events('publish')),publications)

    def test_ten_migration_backups_are_preserved_when_slots_are_exhausted(self):
        original=self.custom.read_text()+'gfwlist=/old\n';self.custom.write_text(original)
        for suffix in ['',*['.'+str(i) for i in range(1,10)]]:
            (self.dnsdir/('dnsmasq.conf.before-migration'+suffix)).write_text('prior evidence'+suffix)
        result=self.run_script('dns')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.custom.read_text(),original)
        self.assertEqual(len(list(self.dnsdir.glob('*.before-migration*'))),10)
        for suffix in ['',*['.'+str(i) for i in range(1,10)]]:
            self.assertEqual((self.dnsdir/('dnsmasq.conf.before-migration'+suffix)).read_text(),'prior evidence'+suffix)
        self.assertEqual(self.events('publish'),[])

    def test_missing_include_cannot_validate_an_unreferenced_candidate(self):
        original=self.custom.read_bytes();self.main.write_text('port=0\n')
        self.assertNotEqual(self.run_script('dns').returncode,0)
        self.assertEqual(self.custom.read_bytes(),original)
        self.assertEqual(self.events('publish'),[])


class SSHStartupPolicyTests(StartupPolicyFixture):
    def test_invalid_stored_policy_is_preserved_and_daemon_is_not_started(self):
        original=self.sshconfig.read_text()+'BadDirective yes\n';self.sshconfig.write_text(original)
        result=self.run_script('ssh')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)
        self.assertIn('automatic defaults disabled',result.stderr)
        self.assertEqual(self.events('ssh-start'),[])
        self.assertEqual(self.events('publish'),[])

    def test_valid_dsa_migration_preserves_authentication_and_original(self):
        original=self.add_dsa()
        self.assertEqual(self.run_script('ssh').returncode,0)
        self.assertNotIn('HostKey ',self.sshconfig.read_text())
        for policy in ('PasswordAuthentication no','AllowTcpForwarding no','PermitRootLogin prohibit-password'):
            self.assertIn(policy,self.sshconfig.read_text())
        backup=self.sshdir/'sshd_config.before-migration'
        self.assertEqual(backup.read_text(),original);self.assertEqual(backup.stat().st_mode&0o777,0o600)
        self.assertEqual(len(self.events('ssh-start')),1)

    def test_failed_dsa_candidate_keeps_even_obsolete_original_line(self):
        original=self.add_dsa(self.sshconfig.read_text()+'BadDirective yes\n')
        self.assertNotEqual(self.run_script('ssh').returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)
        self.assertEqual(self.events('ssh-start'),[])
        self.assertEqual(self.events('publish'),[])

    def test_supported_dsa_and_similarly_named_rsa_paths_are_not_deleted(self):
        original=self.add_dsa()
        self.assertEqual(self.run_script('ssh',DSA_SUPPORTED='1').returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)
        self.sshconfig.write_text('HostKey '+str(self.sshdir/'ssh_host_dsa_key_backup')+'\n'+self.sshconfig.read_text().split('\n',1)[1])
        original=self.sshconfig.read_text()
        self.assertEqual(self.run_script('ssh').returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)

    def test_algorithm_query_failure_keeps_policy_and_refuses_start(self):
        original=self.add_dsa()
        self.assertNotEqual(self.run_script('ssh',KEY_QUERY_FAIL='1').returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)
        self.assertEqual(self.events('ssh-start'),[])

    def test_comment_only_dsa_reference_does_not_require_algorithm_query(self):
        original='# HostKey '+str(self.sshdir/'ssh_host_dsa_key')+'\n'+self.sshconfig.read_text()
        self.sshconfig.write_text(original)
        self.assertEqual(self.run_script('ssh',KEY_QUERY_FAIL='1').returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)
        self.assertEqual(self.events('keyquery'),[])

    def test_policy_changed_during_validation_is_not_overwritten(self):
        result=self.run_script('ssh',CHANGE_STORED_POLICY='1')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.sshconfig.read_text(),'PasswordAuthentication no\nAllowUsers new-restriction\n')
        self.assertEqual(self.events('ssh-start'),[])
        self.assertEqual(self.events('publish'),[])

    def test_first_boot_default_exception_is_validated_and_logged(self):
        self.sshconfig.unlink()
        self.assertEqual(self.run_script('ssh').returncode,0)
        self.assertIn('PermitRootLogin yes',self.sshconfig.read_text())
        self.assertTrue(any('first boot:' in row['message'] for row in self.events('log')))
        self.assertEqual(len(self.events('ssh-start')),1)

    def test_first_boot_validation_failure_leaves_no_active_config(self):
        self.sshconfig.unlink()
        self.assertNotEqual(self.run_script('ssh',DEFAULT_FAIL='1').returncode,0)
        self.assertFalse(self.sshconfig.exists())
        self.assertEqual(self.events('ssh-start'),[])

    def test_new_policy_appearing_during_default_validation_is_preserved(self):
        self.sshconfig.unlink()
        self.assertNotEqual(self.run_script('ssh',APPEAR_DURING_DEFAULT='1').returncode,0)
        self.assertIn('AllowUsers restricted',self.sshconfig.read_text())
        self.assertEqual(self.events('publish'),[])
        self.assertEqual(self.events('ssh-start'),[])

    def test_invalid_included_policy_is_not_hidden_by_migration(self):
        included=self.sshdir/'restrictions.conf';included.write_text('AllowUsers restricted\nBadDirective yes\n')
        original=self.add_dsa(self.sshconfig.read_text()+'Include '+str(included)+'\n')
        self.assertNotEqual(self.run_script('ssh').returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)
        self.assertEqual(self.events('ssh-start'),[])

    def test_publish_failure_preserves_original_and_prevents_daemon_start(self):
        original=self.add_dsa()
        self.assertNotEqual(self.run_script('ssh',PUBLISH_FAIL='1').returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)
        self.assertEqual(self.events('ssh-start'),[])

    def test_ten_migration_backups_are_preserved_when_slots_are_exhausted(self):
        original=self.add_dsa()
        for suffix in ['',*['.'+str(i) for i in range(1,10)]]:
            (self.sshdir/('sshd_config.before-migration'+suffix)).write_text('prior evidence'+suffix)
        result=self.run_script('ssh')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.sshconfig.read_text(),original)
        self.assertEqual(len(list(self.sshdir.glob('*.before-migration*'))),10)
        for suffix in ['',*['.'+str(i) for i in range(1,10)]]:
            self.assertEqual((self.sshdir/('sshd_config.before-migration'+suffix)).read_text(),'prior evidence'+suffix)
        self.assertEqual(self.events('ssh-start'),[])
        self.assertEqual(self.events('publish'),[])

    def test_valid_existing_config_does_not_create_a_backup_or_relax_policy(self):
        original=self.sshconfig.read_bytes()
        self.assertEqual(self.run_script('ssh').returncode,0)
        self.assertEqual(self.sshconfig.read_bytes(),original)
        self.assertEqual(self.events('publish'),[])
        self.assertFalse(list(self.sshdir.glob('*.before-migration*')))


if __name__=='__main__':
    unittest.main()
