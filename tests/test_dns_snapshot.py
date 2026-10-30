"""Actual native snapshot parser; no daemon listener or user script executes."""
from pathlib import Path
import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
import unittest

import test_dns_dynamic_config as parser_fixture

ROOT = Path(__file__).resolve().parents[1]


class DNSSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parser_fixture.DNSDynamicConfigTests.setUpClass.__func__(cls)
        cls.sha_probe = cls.build_root/'sha-probe'
        code = cls.build_root/'sha-probe.c'
        code.write_text(r'''
#include <stdio.h>
#include "snapshot_sha256.h"
int main(void){struct snapshot_sha256 s;unsigned char b[4096],d[32];size_t n;unsigned i;
snapshot_sha_init(&s);while((n=fread(b,1,sizeof(b),stdin)))snapshot_sha_update(&s,b,n);
if(ferror(stdin))return 1;snapshot_sha_final(&s,d);for(i=0;i<32;i++)printf("%02x",d[i]);return 0;}
''')
        subprocess.run(['clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                        '-I'+str(ROOT/'trunk/user/dnsmasq/dnsmasq-2.93/src'),str(code),
                        '-o',str(cls.sha_probe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        parser_fixture.DNSDynamicConfigTests.setUp(self)
        self.main = self.base/'main.conf'
        self.custom = self.base/'custom.conf'
        self.candidate = self.base/'candidate'
        self.cache = self.base/'snapshot'
        self.counter = self.base/'counter'
        self.script('echo ran >> '+str(self.counter)+"; printf 'cache-size=123\\n'")
        self.custom.write_text('conf-script='+str(self.generator)+'\n')
        self.main.write_text('port=0\nno-hosts\nno-resolv\nconf-file='+str(self.custom)+'\n')
        self.refresh_candidate()

    tearDown = parser_fixture.DNSDynamicConfigTests.tearDown
    script = parser_fixture.DNSDynamicConfigTests.script

    def refresh_candidate(self, text=None):
        self.candidate.write_bytes(self.custom.read_bytes() if text is None else text.encode())
        self.candidate.chmod(0o600)

    def execute(self, args, ordinary=False, expect=0):
        binary = self.parse_binary if ordinary else self.binary
        result = subprocess.run([str(binary),*map(str,args)],env=self.env,text=True,
                                capture_output=True,timeout=8)
        self.assertEqual(result.returncode,expect,result.stderr)
        self.assertNotIn('AddressSanitizer',result.stderr)
        self.assertNotIn('runtime error:',result.stderr)
        return result

    def capture(self, managed=True, expect=0):
        args=['--test','-C',self.main,'--snapshot-capture',self.cache,
              '--snapshot-overlay',self.custom,'--snapshot-candidate',self.candidate]
        if managed:args.append('--snapshot-managed')
        return self.execute(args,expect=expect)

    def ticket(self):
        return (self.cache/'ticket').read_text().strip()

    def seal(self, managed=True, expect=0):
        args=['--snapshot-seal',self.cache,'--snapshot-ticket',self.ticket()]
        if managed:args.append('--snapshot-managed')
        return self.execute(args,expect=expect)

    def use(self, ordinary=False, managed=True, expect=0, token=None, cache=None):
        args=[] if ordinary else ['--test']
        args+=['--snapshot-use',cache or self.cache,'--snapshot-ticket',token or self.ticket()]
        if managed:args.append('--snapshot-managed')
        return self.execute(args,ordinary=ordinary,expect=expect)

    def prepared(self):
        self.capture();self.seal()

    def test_streaming_sha256_matches_independent_standard_vectors(self):
        for data in (b'',b'abc',bytes(range(256))*257,b'a'*1000000):
            with self.subTest(bytes=len(data)):
                result=subprocess.run([str(self.sha_probe)],input=data,capture_output=True,env=self.env,timeout=3)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.decode(),hashlib.sha256(data).hexdigest())

    def test_capture_seal_two_tests_and_ordinary_start_parse_execute_once(self):
        self.capture();self.seal();self.use()
        result=self.use(ordinary=True)
        self.assertIn('PARSED_CACHE=123',result.stdout)
        self.assertEqual(self.counter.read_text(),'ran\n')
        for name in ('flat.conf','manifest','ticket'):
            st=(self.cache/name).stat()
            self.assertEqual(st.st_mode&0o7777,0o400);self.assertEqual(st.st_nlink,1)
        self.assertEqual(self.cache.stat().st_mode&0o7777,0o700)
        flat=(self.cache/'flat.conf').read_bytes();manifest=(self.cache/'manifest').read_bytes()
        self.assertNotIn(b'conf-script=',flat);self.assertNotIn(b'conf-file=',flat)
        self.assertEqual(manifest[72:104],hashlib.sha256(flat).digest())
        self.assertEqual(manifest[-32:],hashlib.sha256(manifest[:-32]).digest())
        self.assertEqual(struct.unpack_from('>Q',manifest,24)[0],2)

    def test_raw_quotes_and_inline_comments_preserve_lexical_meaning(self):
        text='txt-record=snapshot.example,"a b,#,c" # private harmless fixture\n'+self.custom.read_text()
        self.custom.write_text(text);self.refresh_candidate();self.prepared();self.use()
        self.assertIn(text.splitlines()[0],(self.cache/'flat.conf').read_text())

    def test_nested_scripts_are_expanded_inline_in_original_order(self):
        inner=self.base/'inner.sh';counts=self.base/'inner-count'
        inner.write_text('#!/bin/sh\necho ran >> '+str(counts)+
                         '\nprintf "server=/middle.example/192.0.2.2\\n"\n');inner.chmod(0o700)
        self.script('echo ran >> '+str(self.counter)+
                    "\nprintf 'server=/first.example/192.0.2.1\\nconf-script="+str(inner)+
                    " nested\\nserver=/last.example/192.0.2.3\\n'")
        self.prepared();self.use();self.use(ordinary=True)
        flat=(self.cache/'flat.conf').read_text()
        self.assertLess(flat.index('first.example'),flat.index('middle.example'))
        self.assertLess(flat.index('middle.example'),flat.index('last.example'))
        self.assertEqual(self.counter.read_text(),'ran\n');self.assertEqual(counts.read_text(),'ran\n')

    def test_candidate_is_sha_bound_to_atomic_published_new_inode(self):
        self.refresh_candidate(self.custom.read_text()+'local-service\n')
        self.capture()
        staging=self.base/'installed';staging.write_bytes(self.candidate.read_bytes());staging.chmod(0o600)
        os.replace(staging,self.custom)
        self.seal();self.use()

    def test_overlay_mismatch_rejects_seal_without_defaults(self):
        self.refresh_candidate(self.custom.read_text()+'local-service\n');original=self.custom.read_bytes()
        self.capture();result=self.seal(expect=1)
        self.assertIn('snapshot',result.stderr);self.assertEqual(self.custom.read_bytes(),original)
        self.assertEqual(self.counter.read_text(),'ran\n')

    def test_missing_firstboot_custom_can_only_seal_after_matching_install(self):
        data=self.custom.read_bytes();self.custom.unlink();self.refresh_candidate(data.decode())
        self.capture();self.seal(expect=1)
        self.custom.write_bytes(data);self.custom.chmod(0o600);self.seal();self.use()

    def test_changed_command_string_before_seal_is_rejected(self):
        self.capture();self.custom.write_text('conf-script='+str(self.generator)+' changed\n')
        self.seal(expect=1);self.assertEqual(self.counter.read_text(),'ran\n')

    def test_changed_command_string_after_seal_is_rejected_before_exec(self):
        self.prepared();self.custom.write_text('conf-script='+str(self.generator)+' changed\n')
        self.use(expect=1);self.assertEqual(self.counter.read_text(),'ran\n')

    def test_nested_input_content_change_is_rejected(self):
        included=self.base/'included.conf';included.write_text('local-service\n')
        self.custom.write_text(self.custom.read_text()+'conf-file='+str(included)+'\n')
        self.refresh_candidate();self.prepared()
        included.write_text('no-poll\n');self.use(expect=1)
        self.assertEqual(self.counter.read_text(),'ran\n')

    def test_input_alias_retarget_with_identical_bytes_is_rejected(self):
        original=self.base/'included.conf';other=self.base/'other.conf'
        original.write_text('local-service\n');other.write_bytes(original.read_bytes())
        alias=self.base/'alias';alias.symlink_to(original.name)
        self.custom.write_text(self.custom.read_text()+'conf-file='+str(alias)+'\n')
        self.refresh_candidate();self.prepared();alias.unlink();alias.symlink_to(other.name)
        self.use(expect=1)

    def test_inode_deduplicated_conf_file_alias_is_still_bound(self):
        original=self.base/'shared.conf';other=self.base/'other.conf'
        original.write_text('server=/public.example/192.0.2.1\n')
        other.write_bytes(original.read_bytes());alias=self.base/'alias.conf'
        initial=self.custom.read_text()
        self.custom.write_text(initial+'conf-file='+str(original)+'\nconf-file='+str(alias)+'\n')
        self.refresh_candidate()
        for phase in ('before-seal','after-seal'):
            with self.subTest(phase=phase):
                alias.symlink_to(original.name);self.capture()
                if phase=='after-seal':self.seal()
                alias.unlink();alias.symlink_to(other.name)
                result=self.seal(expect=1) if phase=='before-seal' else self.use(expect=1)
                self.assertIn('snapshot',result.stderr)
                self.assertEqual(self.counter.read_text(),'ran\n')
                shutil.rmtree(self.cache);alias.unlink();self.counter.unlink()

    def test_inode_deduplicated_conf_dir_alias_is_still_bound(self):
        original=self.base/'shared.conf';other=self.base/'other.conf'
        original.write_text('server=/public.example/192.0.2.1\n')
        other.write_bytes(original.read_bytes());directory=self.base/'conf.d';directory.mkdir()
        alias=directory/'alias.conf'
        self.custom.write_text(self.custom.read_text()+'conf-file='+str(original)+
                               '\nconf-dir='+str(directory)+',*.conf\n')
        self.refresh_candidate()
        for phase in ('before-seal','after-seal'):
            with self.subTest(phase=phase):
                alias.symlink_to(original);self.capture()
                if phase=='after-seal':self.seal()
                alias.unlink();alias.symlink_to(other)
                result=self.seal(expect=1) if phase=='before-seal' else self.use(expect=1)
                self.assertIn('snapshot',result.stderr)
                self.assertEqual(self.counter.read_text(),'ran\n')
                shutil.rmtree(self.cache);alias.unlink();self.counter.unlink()

    def test_same_logical_path_dedup_reuses_record_without_reexpansion(self):
        included=self.base/'included.conf'
        included.write_text('server=/once.example/192.0.2.1\nconf-file='+str(included)+'\n')
        self.custom.write_text(self.custom.read_text()+'conf-file='+str(self.custom)+'\n'+
                               ('conf-file='+str(included)+'\n')*130)
        self.refresh_candidate();self.prepared();self.use();self.use(ordinary=True)
        self.assertEqual(self.counter.read_text(),'ran\n')
        self.assertEqual((self.cache/'flat.conf').read_text().count('once.example'),1)
        # main, overlay, script and included: repeated logical names add no
        # aliases, including the overlay's recursive still-open reference.
        self.assertEqual(struct.unpack_from('>Q',(self.cache/'manifest').read_bytes(),40)[0],4)

    def test_same_content_input_inode_replacement_after_seal_is_rejected(self):
        self.prepared();new=self.base/'replacement';new.write_bytes(self.custom.read_bytes())
        os.replace(new,self.custom);self.use(expect=1)

    def test_selected_conf_dir_addition_and_order_change_are_rejected(self):
        directory=self.base/'conf.d';directory.mkdir()
        (directory/'b.conf').write_text('server=/b.example/192.0.2.2\n')
        self.custom.write_text(self.custom.read_text()+'conf-dir='+str(directory)+',*.conf\n')
        self.refresh_candidate();self.prepared()
        (directory/'a.conf').write_text('server=/a.example/192.0.2.1\n');self.use(expect=1)

    def test_ignored_private_backup_directory_does_not_invalidate_selected_graph(self):
        directory=self.base/'conf.d';directory.mkdir()
        (directory/'a.conf').write_text('server=/a.example/192.0.2.1\n')
        self.custom.write_text(self.custom.read_text()+'conf-dir='+str(directory)+',*.conf\n')
        self.refresh_candidate();self.capture()
        backup=directory/'.config-backups';backup.mkdir(mode=0o700)
        (backup/'retained').write_text('private fixture backup')
        self.seal();self.use()

    def test_capture_never_reuses_an_existing_cache_directory(self):
        self.capture();before=(self.cache/'manifest').read_bytes();self.capture(expect=1)
        self.assertEqual((self.cache/'manifest').read_bytes(),before)
        self.assertEqual(self.counter.read_text(),'ran\n')

    def test_replay_requires_sealed_state_and_exact_ticket(self):
        self.capture();self.use(expect=1);self.seal()
        wrong=('0' if self.ticket()[0]!='0' else '1')+self.ticket()[1:]
        self.use(token=wrong,expect=1)
        self.assertEqual(self.counter.read_text(),'ran\n')

    def test_cache_directory_alias_is_rejected(self):
        self.prepared();alias=self.base/'snapshot-alias';alias.symlink_to(self.cache.name)
        self.use(cache=alias,expect=1)

    def test_flat_symlink_hardlink_or_writable_mode_is_rejected(self):
        self.prepared();flat=self.cache/'flat.conf';data=flat.read_bytes()
        saved=self.base/'saved-flat';flat.rename(saved);flat.symlink_to(saved)
        self.use(expect=1);flat.unlink();os.link(saved,flat);self.use(expect=1)
        flat.unlink();flat.write_bytes(data);flat.chmod(0o600);self.use(expect=1)
        self.assertEqual(self.counter.read_text(),'ran\n')

    def test_manifest_corruption_or_truncation_is_rejected(self):
        self.prepared();manifest=self.cache/'manifest';data=manifest.read_bytes()
        for payload in (data[:-1],data[:40],data[:120]+b'X'+data[121:]):
            manifest.chmod(0o600);manifest.write_bytes(payload);manifest.chmod(0o400)
            self.use(expect=1)

    def test_ticket_alias_and_content_change_are_rejected(self):
        self.prepared();ticket=self.cache/'ticket';value=self.ticket()
        stored=self.base/'stored-ticket';ticket.rename(stored);ticket.symlink_to(stored)
        self.execute(['--test','--snapshot-use',self.cache,'--snapshot-ticket',value,'--snapshot-managed'],expect=1)
        ticket.unlink();ticket.write_text('0'*32+'\n');ticket.chmod(0o400)
        self.execute(['--test','--snapshot-use',self.cache,'--snapshot-ticket',value,'--snapshot-managed'],expect=1)

    def test_managed_foreground_options_are_rejected_and_original_unchanged(self):
        for option in ('no-daemon','keep-in-foreground'):
            self.custom.write_text(option+'\n');self.refresh_candidate();before=self.custom.read_bytes()
            self.capture(expect=1);self.assertEqual(self.custom.read_bytes(),before)
            shutil.rmtree(self.cache)

    def test_snapshot_static_hostname_is_rejected_before_resolver(self):
        self.custom.write_text('server=resolver.fixture.invalid\n');self.refresh_candidate()
        result=self.capture(expect=1)
        self.assertIn('hostname upstream',result.stderr)
        self.assertFalse((self.cache/'manifest').exists())

    def test_flat_over_two_mib_uses_only_the_verified_stream_exception(self):
        extra=[]
        for part in range(2):
            path=self.base/('addresses-'+str(part))
            path.write_text(''.join('address=/public%05d.example.invalid/192.0.2.1\n'%i
                                    for i in range(part*25000,(part+1)*25000)))
            self.assertLess(path.stat().st_size,2*1024*1024);extra.append(path)
        self.custom.write_text(self.custom.read_text()+''.join('conf-file='+str(x)+'\n' for x in extra))
        self.refresh_candidate();self.prepared()
        self.assertGreater((self.cache/'flat.conf').stat().st_size,2*1024*1024)
        self.use();self.use(ordinary=True)
        # The same bytes as an ordinary raw config still hit its2MiB cap.
        raw=self.base/'raw-too-large';shutil.copyfile(self.cache/'flat.conf',raw)
        self.execute(['--test','-C',raw],expect=1)
        self.assertEqual(self.counter.read_text(),'ran\n')

    def test_capture_failure_has_no_complete_marker_and_does_not_publish(self):
        self.custom.write_text('BadDirective\n');self.refresh_candidate();original=self.custom.read_bytes()
        self.capture(expect=1)
        self.assertFalse((self.cache/'manifest').exists())
        self.assertEqual(self.custom.read_bytes(),original)

    def test_generated_error_context_does_not_log_full_secret_command(self):
        secret='PUBLIC_FIXTURE_SECRET_MARKER'
        self.script("printf 'BadDirective\\n'")
        self.custom.write_text('conf-script='+str(self.generator)+' '+secret+'\n')
        self.refresh_candidate();result=self.capture(expect=1)
        self.assertNotIn(secret,result.stdout+result.stderr)
        self.assertIn('script 1',result.stderr)


if __name__ == '__main__':
    unittest.main()
