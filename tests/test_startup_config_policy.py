#!/usr/bin/env python3
"""Replay actual DNS/SSH startup scripts using private config and daemon stubs.

Validation outcomes are controlled; no router, daemon listener, real key, or
system configuration is touched. Publication uses the shipped C rename helper.
"""
from pathlib import Path
import os
import re
import resource
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartupPolicyFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-startup-code-')
        cls.build_root = Path(cls.build.name).resolve()
        cls.stage_root = cls.build_root/'stage';cls.stage_root.mkdir(mode=0o700)
        cls.operation_root = cls.build_root/'op'
        cls.publisher = cls.build_root/'storage_validate'
        subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                        '-DSTARTUP_CONFIG_TEST_UID=geteuid()',
                        '-DSTARTUP_CONFIG_STAGE_DIR="'+str(cls.stage_root)+'"',
                        '-DSTORAGE_OPERATION_DIR="'+str(cls.operation_root)+'"',
                        str(ROOT/'trunk/user/scripts/storage_validate.c'), '-o', str(cls.publisher)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='k2p-startup-policy-')
        self.base = Path(self.temp.name).resolve()
        self.work_root = self.base/'tmp';self.work_root.mkdir(mode=0o700)
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
                    'MAIN_CONFIG': str(self.main),
                    'WORK_ROOT': str(self.work_root),
                    'REAL_PUBLISHER': str(self.publisher)}
        for key in ('ssh_host_rsa_key', 'ssh_host_ed25519_key'):
            (self.sshdir/key).write_text('synthetic key; never used for cryptography')
        self.custom.write_text('dhcp-ignore=tag:untrusted\nlocal-service\n')
        self.main.write_text('port=0\nconf-file='+str(self.custom)+'\n')
        self.sshconfig.write_text('PasswordAuthentication no\nAllowTcpForwarding no\nPermitRootLogin prohibit-password\n')
        self.custom.chmod(0o644);self.sshconfig.chmod(0o644)
        common = r'''
import hashlib, json, os, pathlib, resource, subprocess, sys
args=sys.argv[1:]
def emit(kind, **values):
    # The real parsers only write their bounded diagnostic stream. Keep the
    # fixture event stream small too, so1.75MiB public inputs do not make the
    # stub itself violate the parser's RLIMIT_FSIZE while recording evidence.
    for key,value in list(values.items()):
        if isinstance(value,str) and len(value)>16384:
            values[key]=value[:1024]
            values[key+'_bytes']=len(value.encode())
            values[key+'_sha256']=hashlib.sha256(value.encode()).hexdigest()
    with open(os.environ['EVENT_LOG'],'a') as stream:
        stream.write(json.dumps({'kind':kind,**values})+'\n')
'''
        self.stub('logger', common + "emit('log', message=' '.join(args))\n")
        self.stub('nvram', common + "assert args[0]=='get'\nprint(os.environ['FILTER_AAAA'] if args[1]=='dhcp_filter_aaa' else os.environ['MIN_TTL'])\n")
        self.stub('stat', common + "p=pathlib.Path(args[-1]);st=p.stat() if '-L' in args else p.lstat();fmt=args[args.index('-c')+1];print(st.st_size if fmt=='%s' else st.st_uid if fmt=='%u' else st.st_nlink if fmt=='%h' else oct(st.st_mode&0o777)[2:])\n")
        self.stub('df', common + "print('Filesystem 1024-blocks Used Available Capacity Mounted')\nprint('fixture 24576 0 '+os.environ.get('TMP_FREE_KIB','24576')+' 0% fixture')\n")
        self.stub('md5sum', common + "p=pathlib.Path(args[0]); print(hashlib.md5(p.read_bytes()).hexdigest()+'  '+str(p))\n")
        self.stub('storage_validate', common + r'''
emit('publish',arguments=args)
if os.environ.get('PUBLISH_FAIL')=='1': sys.exit(1)
result=subprocess.run([os.environ['REAL_PUBLISHER'],*args],capture_output=True)
status=2 if result.returncode==0 and os.environ.get('PUBLISH_WARNING')=='1' else result.returncode
emit('publish-result',status=status)
sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr)
sys.exit(status)
''')
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
if os.environ.get('VALIDATION_FLOOD')=='1':
    while True: os.write(2,b'X'*4096)
includes=[line.split('=',1)[1] for line in text.splitlines() if line.startswith('conf-file=')]
custom='\n'.join(pathlib.Path(name).read_text() for name in includes)
emit('dns-test', path=str(p), config=custom)
if os.environ.get('CHANGE_CUSTOM_POLICY')=='1': pathlib.Path(os.environ['DNS_CONFIG']).write_text('dhcp-ignore=tag:new-restriction\n')
if os.environ.get('CHANGE_INSTALLED_POLICY')=='1' and p==pathlib.Path(os.environ['MAIN_CONFIG']):
    pathlib.Path(os.environ['DNS_CONFIG']).write_text('dhcp-ignore=tag:final-restriction\n')
if os.environ.get('DNS_FAIL')=='1' or 'BadDirective' in text+custom or any(line.lstrip().startswith('gfwlist=') for line in custom.splitlines()):
    print('bad option in private fixture',file=sys.stderr); sys.exit(1)
''')
        self.stub('sshd', common + r'''
if '-t' in args:
    p=pathlib.Path(args[args.index('-f')+1]); text=p.read_text()
    if os.environ.get('VALIDATION_FLOOD')=='1':
        while True: os.write(2,b'X'*4096)
    emit('ssh-test',path=str(p),config=text)
    if os.environ.get('CHANGE_STORED_POLICY')=='1' and p.name=='candidate': pathlib.Path(os.environ['SSH_CONFIG']).write_text('PasswordAuthentication no\nAllowUsers new-restriction\n')
    if os.environ.get('APPEAR_DURING_DEFAULT')=='1' and p.name=='default':
        pathlib.Path(os.environ['SSH_CONFIG']).write_text('PasswordAuthentication no\nAllowUsers restricted\n')
    if os.environ.get('CHANGE_INSTALLED_POLICY')=='1' and p==pathlib.Path(os.environ['SSH_CONFIG']):
        pathlib.Path(os.environ['SSH_CONFIG']).write_text('PasswordAuthentication no\nAllowUsers final-restriction\n')
    if os.environ.get('DEFAULT_FAIL')=='1' and p.name=='default': sys.exit(1)
    bad='BadDirective' in text
    for line in text.splitlines():
        if line.startswith('Include '): bad=bad or 'BadDirective' in pathlib.Path(line[8:]).read_text()
        if line.startswith('HostKey ') and line.split()[1].endswith('/ssh_host_dsa_key') and os.environ.get('DSA_SUPPORTED')!='1': bad=True
    if bad: print('bad configuration in private fixture',file=sys.stderr); sys.exit(1)
else:
    try: os.fstat(9);fd9_open=True
    except OSError: fd9_open=False
    emit('ssh-start',arguments=args,config=pathlib.Path(os.environ['SSH_CONFIG']).read_text(),
         fsize_limit=list(resource.getrlimit(resource.RLIMIT_FSIZE)),fd9_open=fd9_open,
         startup_workspaces=list(map(str,pathlib.Path(os.environ['WORK_ROOT']).glob('.sshd-startup.*'))))
    sys.exit(int(os.environ.get('DAEMON_STATUS','0')))
''')
        mapping = {'/etc/storage/openssh': str(self.sshdir), '/etc/storage/dnsmasq': str(self.dnsdir),
                   '/etc/storage': str(self.storage), '/etc/dnsmasq.conf': str(self.main),
                   '/usr/sbin/dnsmasq': str(self.bin/'dnsmasq'), '/usr/sbin/sshd': str(self.bin/'sshd'),
                   '/usr/bin/ssh-keygen': str(self.bin/'ssh-keygen'), '/usr/bin/ssh': str(self.bin/'ssh'),
                   '/sbin/storage_validate': str(self.bin/'storage_validate'), '/var/run/utmp': str(self.base/'utmp')}
        mapping.update({'/tmp/.dnsmasq-startup':str(self.work_root/'.dnsmasq-startup'),
                        '/tmp/.sshd-startup':str(self.work_root/'.sshd-startup'),
                        'df -Pk /tmp':'df -Pk '+str(self.work_root)})
        self.scripts = {}
        for name, relative in [('dns', 'trunk/user/dnsmasq/dnsmasq.sh'), ('ssh', 'trunk/user/openssh/sshd.sh')]:
            text = (ROOT/relative).read_text()
            pattern='|'.join(re.escape(old) for old in sorted(mapping,key=len,reverse=True))
            text=re.sub(pattern,lambda match:mapping[match.group(0)],text)
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
        self.assertFalse(list(self.work_root.glob('.dnsmasq-startup.*')))
        self.assertFalse(list(self.work_root.glob('.sshd-startup.*')))
        return result

    def events(self, kind):
        import json
        return [row for row in map(json.loads,self.log.read_text().splitlines()) if row['kind']==kind] if self.log.exists() else []

    def add_dsa(self, text=None):
        old=text if text is not None else self.sshconfig.read_text()
        value='HostKey '+str(self.sshdir/'ssh_host_dsa_key')+'\n'+old
        self.sshconfig.write_text(value)
        return value

    def backup_path(self,config,suffix=''):
        return config.parent/'.config-backups'/(config.name+'.before-migration'+suffix)


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
        inode=self.custom.stat().st_ino
        self.assertEqual(self.run_script('dns').returncode,0)
        backups=list((self.dnsdir/'.config-backups').glob('dnsmasq.conf.before-migration*'))
        self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(),original)
        self.assertEqual(backups[0].stat().st_mode&0o777,0o644)
        self.assertEqual(backups[0].stat().st_ino,inode)
        self.assertEqual(backups[0].parent.stat().st_mode&0o777,0o700)
        self.assertIn('dhcp-ignore=tag:untrusted',self.custom.read_text())
        self.assertIn('#gfwlist=',self.custom.read_text())
        self.assertEqual(len(self.events('publish')),1)

    def test_publish_failure_keeps_original_restrictive_policy(self):
        original=self.custom.read_text()+'gfwlist=/old\n';self.custom.write_text(original)
        self.assertNotEqual(self.run_script('dns',PUBLISH_FAIL='1').returncode,0)
        self.assertEqual(self.custom.read_text(),original)
        self.assertFalse(self.backup_path(self.custom).exists())

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
        self.assertTrue(self.backup_path(self.custom,'.1').exists())
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
        self.assertEqual(len(self.events('publish')),1)

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
        inode=self.sshconfig.stat().st_ino
        self.assertEqual(self.run_script('ssh').returncode,0)
        self.assertNotIn('HostKey ',self.sshconfig.read_text())
        for policy in ('PasswordAuthentication no','AllowTcpForwarding no','PermitRootLogin prohibit-password'):
            self.assertIn(policy,self.sshconfig.read_text())
        backup=self.backup_path(self.sshconfig)
        self.assertEqual(backup.read_text(),original);self.assertEqual(backup.stat().st_mode&0o777,0o644)
        self.assertEqual(backup.stat().st_ino,inode)
        self.assertEqual(backup.parent.stat().st_mode&0o777,0o700)
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
        self.assertEqual(len(self.events('publish')),1)

    def test_valid_existing_config_does_not_create_a_backup_or_relax_policy(self):
        original=self.sshconfig.read_bytes()
        self.assertEqual(self.run_script('ssh').returncode,0)
        self.assertEqual(self.sshconfig.read_bytes(),original)
        self.assertEqual(self.events('publish'),[])
        self.assertFalse(list(self.sshdir.glob('*.before-migration*')))


class StartupCapacityPolicyTests(StartupPolicyFixture):
    def config(self,kind):
        return self.custom if kind=='dns' else self.sshconfig

    def large_policy(self,kind,migration=False):
        policy=self.config(kind).read_text()
        if migration:
            policy+=('gfwlist=/legacy.list\n' if kind=='dns' else
                     'HostKey '+str(self.sshdir/'ssh_host_dsa_key')+'\n')
        size=7*1024*1024//4
        padding=('# bounded public capacity fixture\n'*((size-len(policy))//34+2))
        return (policy+padding)[:size-1]+'\n'

    def test_large_unchanged_configs_use_private_tmp_and_no_publication(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind);payload=self.large_policy(kind);path.write_text(payload)
                inode=path.stat().st_ino
                result=self.run_script(kind)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(path.read_text(),payload);self.assertEqual(path.stat().st_ino,inode)
                self.assertEqual(self.events('publish'),[])
                tests=self.events('dns-test' if kind=='dns' else 'ssh-test')
                self.assertTrue(any(str(self.work_root) in row['path'] for row in tests))
                self.assertFalse(list(self.storage.glob('*/.startup.*')))

    def test_large_migration_keeps_original_inode_in_private_backup(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind);payload=self.large_policy(kind,True);path.write_text(payload)
                inode=path.stat().st_ino
                result=self.run_script(kind)
                self.assertEqual(result.returncode,0,result.stderr)
                backup=self.backup_path(path)
                self.assertEqual(backup.read_text(),payload);self.assertEqual(backup.stat().st_ino,inode)
                self.assertEqual(backup.parent.stat().st_mode&0o777,0o700)
                self.assertEqual(path.stat().st_mode&0o777,0o600)

    def test_tmp_free_space_failure_keeps_each_active_policy(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind);original=path.read_bytes()
                result=self.run_script(kind,TMP_FREE_KIB='128')
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(path.read_bytes(),original)
                self.assertIn('temporary space',result.stderr)
                self.assertEqual(self.events('publish'),[])

    def test_inputs_over_two_mib_are_rejected_before_snapshot(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind);payload=b'#'+b'x'*(2*1024*1024);path.write_bytes(payload)
                self.assertNotEqual(self.run_script(kind).returncode,0)
                self.assertEqual(path.read_bytes(),payload)
                self.assertEqual(self.events('publish'),[])
                self.assertEqual(self.events('dns-test' if kind=='dns' else 'ssh-test'),[])

    def test_oversized_link_target_is_measured_with_dereference(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind);target=self.base/(kind+'-large-target')
                target.write_bytes(b'#'+b'x'*(2*1024*1024));path.unlink();path.symlink_to(target)
                self.assertNotEqual(self.run_script(kind).returncode,0)
                self.assertTrue(path.is_symlink());self.assertEqual(target.stat().st_size,2*1024*1024+1)
                self.assertEqual(self.events('publish'),[])

    def test_validation_log_flood_is_bounded_and_policy_is_preserved(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind);original=path.read_bytes()
                result=self.run_script(kind,VALIDATION_FLOOD='1')
                self.assertNotEqual(result.returncode,0)
                self.assertLessEqual(len(result.stderr),65536+4096)
                self.assertEqual(path.read_bytes(),original)
                self.assertEqual(self.events('publish'),[])
                self.assertEqual(self.events('ssh-start'),[])

    def test_partial_snapshot_failure_cleans_tmp_without_publication(self):
        self.stub('cat',r'''
import os,sys
from pathlib import Path
args=sys.argv[1:]
if args and args[0] in (os.environ['DNS_CONFIG'],os.environ['SSH_CONFIG']):
    os.write(1,Path(args[0]).read_bytes()[:8]);sys.exit(1)
os.execv('/bin/cat',['/bin/cat',*args])
''')
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind);original=path.read_bytes()
                self.assertNotEqual(self.run_script(kind).returncode,0)
                self.assertEqual(path.read_bytes(),original)
                self.assertEqual(self.events('publish'),[])

    def test_transformation_over_two_mib_never_changes_original(self):
        payload='gfwlist=/old\n'*150000
        self.assertLess(len(payload),2*1024*1024)
        self.custom.write_text(payload)
        self.assertNotEqual(self.run_script('dns').returncode,0)
        self.assertEqual(self.custom.read_text(),payload)
        self.assertEqual(self.events('publish'),[])

    def test_unchanged_symlink_policy_is_validated_without_replacement(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind);target=self.base/(kind+'-linked-policy');path.rename(target);path.symlink_to(target)
                original=target.read_bytes()
                self.assertEqual(self.run_script(kind).returncode,0)
                self.assertTrue(path.is_symlink());self.assertEqual(target.read_bytes(),original)
                self.assertEqual(self.events('publish'),[])

    def test_linked_policy_needing_migration_is_preserved(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind)
                payload=(path.read_text()+'gfwlist=/legacy\n') if kind=='dns' else self.add_dsa()
                path.write_text(payload);target=self.base/(kind+'-linked-migration');path.rename(target);path.symlink_to(target)
                self.assertNotEqual(self.run_script(kind).returncode,0)
                self.assertTrue(path.is_symlink());self.assertEqual(target.read_text(),payload)
                self.assertEqual(self.events('publish'),[])

    def test_hardlinked_policy_needing_migration_is_preserved(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                path=self.config(kind)
                payload=(path.read_text()+'gfwlist=/legacy\n') if kind=='dns' else self.add_dsa()
                path.write_text(payload);alias=self.base/(kind+'-hardlink');os.link(path,alias)
                self.assertNotEqual(self.run_script(kind).returncode,0)
                self.assertEqual(path.read_text(),payload);self.assertEqual(alias.read_text(),payload)
                self.assertEqual(path.stat().st_ino,alias.stat().st_ino)

    def test_committed_warning_still_revalidates_installed_policy(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                if kind=='dns':self.custom.write_text(self.custom.read_text()+'gfwlist=/legacy\n')
                else:self.add_dsa()
                result=self.run_script(kind,PUBLISH_WARNING='1')
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(any(row['status']==2 for row in self.events('publish-result')))
                self.assertTrue(any('published with' in row['message'] for row in self.events('log')))

    def test_final_validation_policy_change_is_never_hidden(self):
        for kind in ('dns','ssh'):
            with self.subTest(kind=kind):
                result=self.run_script(kind,CHANGE_INSTALLED_POLICY='1')
                self.assertNotEqual(result.returncode,0)
                self.assertIn('final-restriction',self.config(kind).read_text())
                self.assertEqual(self.events('ssh-start'),[])

    def test_daemon_has_no_validation_limit_lock_fd_or_private_workspace(self):
        inherited=list(resource.getrlimit(resource.RLIMIT_FSIZE))
        result=self.run_script('ssh')
        self.assertEqual(result.returncode,0,result.stderr)
        start=self.events('ssh-start')[-1]
        self.assertEqual(start['fsize_limit'],inherited)
        self.assertFalse(start['fd9_open'])
        self.assertEqual(start['startup_workspaces'],[])


if __name__=='__main__':
    unittest.main()
