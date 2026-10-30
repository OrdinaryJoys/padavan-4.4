#!/usr/bin/env python3
"""Compile the shipped validator and replay storage scripts in a private tree.
No router, host /etc, real services or flash device is accessed.
"""
import bz2
import fcntl
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'trunk/user/scripts/mtd_storage.sh'
SOURCE=ROOT/'trunk/user/scripts/storage_validate.c'

def archive(members=(),fmt=tarfile.USTAR_FORMAT):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w',format=fmt) as tf:
        info=tarfile.TarInfo('start_script.sh');info.mode=0o755;data=b'#!/bin/sh\n';info.size=len(data);tf.addfile(info,io.BytesIO(data))
        for name,data,kind,target in members:
            info=tarfile.TarInfo(name);info.mode=0o644;info.type=kind;info.linkname=target
            info.size=len(data) if kind==tarfile.REGTYPE else 0
            tf.addfile(info,io.BytesIO(data) if info.size else None)
    return output.getvalue()

def checksum(header):
    header[148:156]=b' '*8
    header[148:156]=('%06o\0 '%sum(header)).encode()
    return header

class StorageRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory(prefix='k2p-storage-code-')
        cls.validator=Path(cls.shared.name)/'storage_validate'
        subprocess.run([shutil.which('clang') or shutil.which('cc'),'-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(SOURCE),'-o',str(cls.validator)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls): cls.shared.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='k2p-storage-case-')
        self.base=Path(self.temp.name);self.bin=self.base/'bin';self.bin.mkdir()
        self.storage=self.base/'etc/storage';self.storage.mkdir(parents=True)
        (self.storage/'start_script.sh').write_text('#!/bin/sh\n')
        (self.storage/'original').write_text('keep original')
        self.tmp=self.base/'tmp';self.tmp.mkdir();(self.tmp/'hashes').mkdir()
        self.tbz=self.tmp/'storage.tar.bz2';self.hash=self.tmp/'hashes/storage_md5'
        self.proc=self.base/'mtd';self.proc.write_text('mtd6: 00080000 00010000 "Storage"\n')
        self.device=self.base/'mtdblock6';self.flash_calls=self.base/'flash-calls'
        self.env=dict(os.environ,PATH=str(self.bin)+':'+os.environ['PATH'])
        self.stub('tar','export COPYFILE_DISABLE=1\ncase "$1" in -cf|cf) exec /usr/bin/tar --format=ustar "$@";; *) exec /usr/bin/tar "$@";; esac')
        self.stub('storage_validate','exec \"'+str(self.validator)+'\" \"$@\"')
        self.stub('id','echo 0')
        self.stub('flock', "exec python3 -c 'import fcntl,sys; fcntl.flock(int(sys.argv[1]),fcntl.LOCK_EX|fcntl.LOCK_NB)' \"$2\"")
        self.stub('logger','exit 0')
        self.stub('killall','exit 1')
        self.stub('rstats','exit 0')
        self.stub('stat',"""python3 - "$2" "$3" <<'CODE'
import os,sys
fmt=sys.argv[1];path=sys.argv[2]
print(0 if fmt=='%u' else (oct(os.stat(path).st_mode & 0o7777)[2:] if fmt=='%a' else os.path.getsize(path)))
CODE""")
        self.stub('df','printf "Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 65536 0 65536 0%% /fixture\\n"')
        self.stub('md5sum','exec python3 -c \'import hashlib,sys; p=sys.argv[1]; print(hashlib.md5(open(p,"rb").read()).hexdigest()+"  "+p)\' "$1"')
        self.stub('mtd_write','echo write >> "'+str(self.flash_calls)+'"\nexit "${FLASH_RC:-0}"')
        text=SCRIPT.read_text()
        replacements={'/sbin/storage_validate':str(self.bin/'storage_validate'),'/sbin/rstats':str(self.bin/'rstats'),'/etc/storage':str(self.storage),'/tmp/':str(self.tmp)+'/', '/proc/mtd':str(self.proc),'/dev/mtdblock':str(self.base/'mtdblock')}
        for old in sorted(replacements,key=len,reverse=True): text=text.replace(old,replacements[old])
        self.replay=self.base/'replay.sh';self.replay.write_text(text)

    def tearDown(self): self.temp.cleanup()

    def stub(self,name,body):
        path=self.bin/name;path.write_text('#!/bin/sh\n'+body+'\n');path.chmod(0o755)

    def check(self,data,budget=64*1024*1024):
        path=self.base/'test.tar';path.write_bytes(data)
        p=subprocess.run([str(self.validator),str(path),str(budget)],capture_output=True,text=True,timeout=8)
        self.assertNotIn('AddressSanitizer',p.stderr)
        self.assertNotIn('runtime error:',p.stderr)
        return p

    def run_script(self,action,**env):
        return subprocess.run(['sh',str(self.replay),action],env={**self.env,**env},text=True,capture_output=True,timeout=15)

    def test_ustar_hidden_spaces_and_internal_links(self):
        members=[('.hidden',b'hidden',tarfile.REGTYPE,''),('with space',b'x',tarfile.REGTYPE,''),('link',b'',tarfile.SYMTYPE,'with space'),('hard',b'',tarfile.LNKTYPE,'with space')]
        self.assertEqual(self.check(archive(members)).returncode,0)

    def test_ustar_prefix_and_gnu_long_names_links(self):
        name='a'*120+'/value'
        self.assertEqual(self.check(archive([(name,b'x',tarfile.REGTYPE,'')])).returncode,0)
        members=[(name,b'x',tarfile.REGTYPE,''),('soft',b'',tarfile.SYMTYPE,name),('hard',b'',tarfile.LNKTYPE,name)]
        self.assertEqual(self.check(archive(members,tarfile.GNU_FORMAT)).returncode,0)

    def test_v7_headers(self):
        data=bytearray(archive());h=data[:512];h[257:512]=bytes(255);data[:512]=checksum(h)
        self.assertEqual(self.check(data).returncode,0)

    def test_reject_path_and_link_traversal(self):
        for name,kind,target in [('../outside',tarfile.REGTYPE,''),('/outside',tarfile.REGTYPE,''),('a/../../outside',tarfile.REGTYPE,''),('link',tarfile.SYMTYPE,'/etc'),('link',tarfile.SYMTYPE,'../outside'),('link',tarfile.LNKTYPE,'../../outside')]:
            with self.subTest(name=name,target=target): self.assertNotEqual(self.check(archive([(name,b'',kind,target)])).returncode,0)

    def test_reject_gnu_long_override_traversal(self):
        for member in [('a'*120+'/../../outside',b'x',tarfile.REGTYPE,''),('link',b'',tarfile.SYMTYPE,'a'*120+'/../../outside')]:
            self.assertNotEqual(self.check(archive([member],tarfile.GNU_FORMAT)).returncode,0)

    def test_reject_link_as_parent_in_either_order(self):
        for members in [[('pivot',b'',tarfile.SYMTYPE,'safe'),('pivot/file',b'x',tarfile.REGTYPE,'')],[('pivot/file',b'x',tarfile.REGTYPE,''),('pivot',b'',tarfile.SYMTYPE,'safe')]]:
            self.assertNotEqual(self.check(archive(members)).returncode,0)

    def test_reject_duplicate_canonical_paths(self):
        self.assertNotEqual(self.check(archive([('./start_script.sh',b'x',tarfile.REGTYPE,'')])).returncode,0)

    def test_reject_pax_sparse_device_and_fifo(self):
        for kind in [tarfile.XHDTYPE,tarfile.XGLTYPE,tarfile.GNUTYPE_SPARSE,tarfile.CHRTYPE,tarfile.BLKTYPE,tarfile.FIFOTYPE]:
            with self.subTest(kind=kind): self.assertNotEqual(self.check(archive([('bad',b'',kind,'')])).returncode,0)

    def test_reject_malformed_and_truncated_archive(self):
        normal=archive();bad=bytearray(normal);bad[0]^=1
        non_octal=bytearray(normal);h=non_octal[:512];h[124:136]=b'0000000000x\0';non_octal[:512]=checksum(h)
        for data in [b'',normal[:511],normal[:1024],bytes(bad),bytes(non_octal),normal+bytes(511)+b'x']:
            with self.subTest(size=len(data)): self.assertNotEqual(self.check(data).returncode,0)

    def test_reject_oversize_or_insufficient_page_budget(self):
        self.assertNotEqual(self.check(archive(),1).returncode,0)
        self.assertNotEqual(self.check(archive(),-1).returncode,0)
        data=bytearray(archive());h=data[:512];h[124:136]=('%011o\0'%(9*1024*1024)).encode();data[:512]=checksum(h)
        self.assertNotEqual(self.check(data).returncode,0)
        self.assertNotEqual(self.check(archive()+bytes(8*1024*1024)).returncode,0)

    def test_reject_dangling_repeated_extensions_and_data_after_end(self):
        info=tarfile.TarInfo('././@LongLink');info.type=tarfile.GNUTYPE_LONGNAME;info.size=3;info.mode=0o644
        extension=info.tobuf(format=tarfile.GNU_FORMAT)+b'ab\0'+bytes(509)
        for data in [extension+bytes(1024),extension+extension+archive(),archive()+archive()]:
            self.assertNotEqual(self.check(data).returncode,0)

    def test_restore_valid_archive_preserves_payload_and_links(self):
        self.tbz.write_bytes(bz2.compress(archive([('.hidden',b'h',tarfile.REGTYPE,''),('with space',b'value',tarfile.REGTYPE,''),('link',b'',tarfile.SYMTYPE,'with space')])))
        p=self.run_script('restore');self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual((self.storage/'.hidden').read_bytes(),b'h')
        self.assertEqual((self.storage/'with space').read_bytes(),b'value')
        self.assertEqual((self.storage/'link').read_bytes(),b'value')
        self.assertFalse((self.storage/'original').exists())

    def test_restore_rejects_external_link_before_any_extraction(self):
        outside=self.base/'outside';outside.mkdir()
        members=[('pivot',b'',tarfile.SYMTYPE,str(outside)),('pivot/pwn',b'bad',tarfile.REGTYPE,'')]
        self.tbz.write_bytes(bz2.compress(archive(members)))
        p=self.run_script('restore');self.assertNotEqual(p.returncode,0)
        self.assertEqual((self.storage/'original').read_text(),'keep original')
        self.assertFalse((outside/'pwn').exists())

    def test_restore_extraction_failure_keeps_current_storage(self):
        self.tbz.write_bytes(bz2.compress(archive()))
        self.stub('tar','exit 1')
        self.assertNotEqual(self.run_script('restore').returncode,0)
        self.assertEqual((self.storage/'original').read_text(),'keep original')

    def test_restore_snapshot_copy_failure_keeps_current_storage(self):
        self.tbz.write_bytes(bz2.compress(archive()));self.stub('cp','exit 1')
        self.assertNotEqual(self.run_script('restore').returncode,0)
        self.assertEqual((self.storage/'original').read_text(),'keep original')

    def test_restore_install_failure_rolls_back_current_storage(self):
        self.tbz.write_bytes(bz2.compress(archive()))
        self.stub('storage_validate','if [ \"$1\" = --rename-directory ]; then case \"$2\" in *.storage-restore.*/storage) exit 1;; esac; fi\nexec \"'+str(self.validator)+'\" \"$@\"')
        self.assertNotEqual(self.run_script('restore').returncode,0)
        self.assertEqual((self.storage/'original').read_text(),'keep original')

    def test_restore_budget_failure_keeps_current_storage(self):
        self.tbz.write_bytes(bz2.compress(archive()))
        self.stub('df','printf "Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 65536 65500 36 99%% /fixture\\n"')
        self.assertNotEqual(self.run_script('restore').returncode,0)
        self.assertEqual((self.storage/'original').read_text(),'keep original')

    def test_load_corrupt_compressed_stream_never_changes_live_data_or_hash(self):
        self.device.write_bytes(bz2.compress(archive())[:-5]);self.hash.write_text('old hash')
        self.assertNotEqual(self.run_script('load').returncode,0)
        self.assertEqual((self.storage/'original').read_text(),'keep original')
        self.assertEqual(self.hash.read_text(),'old hash')

    def test_decompression_bomb_is_bounded(self):
        self.device.write_bytes(bz2.compress(bytes(9*1024*1024)))
        self.assertNotEqual(self.run_script('load').returncode,0)
        self.assertEqual((self.storage/'original').read_text(),'keep original')

    def test_backup_includes_dotfiles_and_many_members(self):
        # Force argument batching: the historical xargs tar -cf pipeline lost prior batches.
        self.stub('xargs','exec /usr/bin/xargs -n 7 \"$@\"')
        (self.storage/'.hidden').write_text('hidden')
        (self.storage/'with space').write_text('space')
        for i in range(150): (self.storage/('name-%03d'%i)).write_text(str(i))
        p=self.run_script('backup');self.assertEqual(p.returncode,0,p.stderr)
        with tarfile.open(self.tbz,'r:bz2') as tf:
            names={m.name.removeprefix('./') for m in tf.getmembers()}
        self.assertIn('.hidden',names);self.assertIn('with space',names)
        self.assertEqual(len([n for n in names if n.startswith('name-')]),150)
        self.assertEqual(self.tbz.stat().st_mode&0o777,0o600)

    def test_failed_flash_does_not_advance_hash_and_retry_rewrites(self):
        self.hash.write_text('previous hash')
        p=self.run_script('save',FLASH_RC='1');self.assertNotEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.hash.read_text(),'previous hash')
        self.assertEqual(self.flash_calls.read_text().count('write'),1)
        p=self.run_script('save',FLASH_RC='0');self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.flash_calls.read_text().count('write'),2)
        self.assertNotEqual(self.hash.read_text(),'previous hash')
        p=self.run_script('save',FLASH_RC='0');self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.flash_calls.read_text().count('write'),2)

    def test_failed_tar_does_not_publish_stale_or_partial_backup(self):
        self.tbz.write_bytes(b'old good backup');self.stub('tar','echo incomplete > "$2"\nexit 1')
        self.assertNotEqual(self.run_script('backup').returncode,0)
        self.assertEqual(self.tbz.read_bytes(),b'old good backup')

    def test_lock_symlink_or_active_operation_is_not_followed(self):
        lock=self.tmp/'.storage_operation';target=self.base/'lock-target';target.mkdir();(target/'sentinel').write_text('safe');lock.symlink_to(target)
        self.assertNotEqual(self.run_script('backup').returncode,0)
        self.assertEqual((target/'sentinel').read_text(),'safe')
        lock.unlink();lock.mkdir()
        with (lock/'lock').open('w') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertNotEqual(self.run_script('backup').returncode,0)
        self.assertTrue((lock/'lock').exists())

    def test_public_upload_symlink_is_rejected(self):
        target=self.base/'upload-target';target.write_bytes(bz2.compress(archive()));self.tbz.symlink_to(target)
        self.assertNotEqual(self.run_script('restore').returncode,0)
        self.assertTrue(target.exists());self.assertEqual((self.storage/'original').read_text(),'keep original')

    def test_restore_removes_group_world_write_from_config_tree(self):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w',format=tarfile.USTAR_FORMAT) as tf:
            for name,kind,mode,payload in [('start_script.sh',tarfile.REGTYPE,0o777,b'#!/bin/sh\n'),('openssh',tarfile.DIRTYPE,0o777,b''),('openssh/sshd_config',tarfile.REGTYPE,0o666,b'policy'),('dnsmasq',tarfile.DIRTYPE,0o777,b'')]:
                info=tarfile.TarInfo(name);info.type=kind;info.mode=mode;info.size=len(payload)
                tf.addfile(info,io.BytesIO(payload) if payload else None)
        self.tbz.write_bytes(bz2.compress(data.getvalue()))
        p=self.run_script('restore');self.assertEqual(p.returncode,0,p.stderr)
        for path in [self.storage/'openssh',self.storage/'dnsmasq',self.storage/'start_script.sh',self.storage/'openssh/sshd_config']:
            self.assertEqual(path.stat().st_mode & 0o022,0)

    def test_backup_publish_replaces_symlink_itself(self):
        for directory in [False,True]:
            with self.subTest(directory=directory):
                if self.tbz.is_symlink() or self.tbz.exists(): self.tbz.unlink()
                target=self.base/('public-target-dir' if directory else 'public-target-file')
                if directory: target.mkdir()
                else: target.write_text('untouched')
                self.tbz.symlink_to(target)
                p=self.run_script('backup');self.assertEqual(p.returncode,0,p.stderr)
                self.assertFalse(self.tbz.is_symlink())
                if directory: self.assertEqual(list(target.iterdir()),[])
                else: self.assertEqual(target.read_text(),'untouched')

    def test_stale_lock_recovers_and_private_paths_are_removed(self):
        lock=self.tmp/'.storage_operation';lock.mkdir();(lock/'pid').write_text('2147483647')
        p=self.run_script('backup');self.assertEqual(p.returncode,0,p.stderr)
        self.assertTrue((lock/'lock').exists())
        self.assertFalse((lock/'work').exists())
        self.assertFalse(list((self.base/'etc').glob('.storage-restore.*')))

    def test_hash_publish_does_not_follow_existing_directory_symlink(self):
        target=self.base/'hash-target';target.mkdir();self.hash.symlink_to(target)
        p=self.run_script('save');self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse(self.hash.is_symlink())
        self.assertEqual(list(target.iterdir()),[])
        self.assertEqual(self.hash.stat().st_mode&0o777,0o600)

    def test_restarted_rstats_does_not_inherit_storage_lock(self):
        marker=self.base/'rstats-fd-status'
        self.stub('rstats',"""python3 - <<'CODE'
import os
from pathlib import Path
try:
    os.fstat(9)
    status='open'
except OSError:
    status='closed'
Path(%r).write_text(status)
CODE"""%str(marker))
        self.tbz.write_bytes(bz2.compress(archive()))
        p=self.run_script('restore');self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(marker.read_text(),'closed')
        # Negative control proves the fixture can observe an inherited lock.
        text=self.replay.read_text().replace(str(self.bin/'rstats')+' 9>&-',str(self.bin/'rstats'))
        self.replay.write_text(text)
        self.tbz.write_bytes(bz2.compress(archive()))
        p=self.run_script('restore');self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(marker.read_text(),'open')

    def test_prefix_matches_busybox_for_v7_gnu_and_non00_ustar(self):
        for magic,version in [(bytes(6),bytes(2)),(b'ustar ',b'  '),(b'ustar\0',b'99')]:
            data=bytearray(archive());header=data[:512]
            header[257:263]=magic;header[263:265]=version
            header[345:355]=b'unexpected'
            data[:512]=checksum(header)
            # BusyBox extracts unexpected/start_script.sh, never the required root file.
            self.assertNotEqual(self.check(data).returncode,0)

    def test_files_only_tar_charges_implicit_parent_directories(self):
        data=archive([('a/b/c/d/file',b'x',tarfile.REGTYPE,'')])
        self.assertEqual(self.check(data).returncode,0)
        self.assertNotEqual(self.check(data,16384).returncode,0)
        deep=archive([('a/'*65+'file',b'x',tarfile.REGTYPE,'')],tarfile.GNU_FORMAT)
        self.assertNotEqual(self.check(deep).returncode,0)

    def test_reject_regular_file_as_parent_in_both_member_orders(self):
        members=[('a',b'file',tarfile.REGTYPE,''),('a/b',b'',tarfile.DIRTYPE,'')]
        for ordered in [members,list(reversed(members))]:
            self.assertNotEqual(self.check(archive(ordered)).returncode,0)

    def test_restore_replaces_empty_target_recreated_during_exchange(self):
        self.tbz.write_bytes(bz2.compress(archive()))
        self.stub('storage_validate','if [ "$1" = --rename-directory ]; then case "$2" in *.storage-restore.*/storage) mkdir -p "$3";; esac; fi\nexec "'+str(self.validator)+'" "$@"')
        p=self.run_script('restore');self.assertEqual(p.returncode,0,p.stderr)
        self.assertTrue((self.storage/'start_script.sh').is_file())
        self.assertFalse((self.storage/'storage').exists())

    def test_restore_nonempty_recreated_target_preserves_previous_for_recovery(self):
        self.tbz.write_bytes(bz2.compress(archive()))
        self.stub('storage_validate','if [ "$1" = --rename-directory ]; then case "$2" in *.storage-restore.*/storage) mkdir -p "$3"; echo concurrent > "$3/concurrent-service";; esac; fi\nexec "'+str(self.validator)+'" "$@"')
        p=self.run_script('restore');self.assertNotEqual(p.returncode,0)
        self.assertFalse((self.storage/'storage').exists())
        self.assertEqual((self.storage/'concurrent-service').read_text(),'concurrent\n')
        previous=list((self.base/'etc').glob('.storage-restore.*/previous/original'))
        self.assertEqual(len(previous),1)
        self.assertEqual(previous[0].read_text(),'keep original')

    def test_gnu_longname_does_not_hide_busybox_empty_header(self):
        info=tarfile.TarInfo('././@LongLink');info.type=tarfile.GNUTYPE_LONGNAME;info.mode=0o644
        text=b'hidden-member\0';info.size=len(text)
        extension=info.tobuf(format=tarfile.GNU_FORMAT)+text+bytes(512-len(text))
        member=tarfile.TarInfo('');member.mode=0o644;member.size=0
        empty_name=member.tobuf(format=tarfile.GNU_FORMAT)
        data=archive()[:1024]+extension+empty_name+bytes(1024)
        self.assertNotEqual(self.check(data).returncode,0)

    def test_linux_component_and_total_relative_path_limits(self):
        for name in ['a'*300,'/'.join(['b'*254]*16)]:
            for kind in [tarfile.DIRTYPE,tarfile.SYMTYPE]:
                with self.subTest(length=len(name),kind=kind):
                    self.assertNotEqual(self.check(archive([(name,b'',kind,'safe' if kind==tarfile.SYMTYPE else '')],tarfile.GNU_FORMAT)).returncode,0)
        # Long legal GNU paths still work; the cap is2048bytes including slashes.
        legal='/'.join(['c'*255]*8)
        self.assertEqual(len(legal),2047)
        self.assertEqual(self.check(archive([(legal,b'',tarfile.DIRTYPE,'')],tarfile.GNU_FORMAT)).returncode,0)

    def crash_at_rename(self,phase):
        self.tbz.write_bytes(bz2.compress(archive([('new-data',b'new',tarfile.REGTYPE,'')])))
        if phase=='before-original-move':
            trigger='case "$3" in *.storage-restore.*/previous) kill -KILL "$PPID"; exit 0;; esac'
        elif phase=='after-original-move':
            trigger='case "$3" in *.storage-restore.*/previous) "'+str(self.validator)+'" "$@" || exit 1; kill -KILL "$PPID"; exit 0;; esac'
        else:
            trigger='case "$2" in *.storage-restore.*/storage) "'+str(self.validator)+'" "$@" || exit 1; kill -KILL "$PPID"; exit 0;; esac'
        self.stub('storage_validate','if [ "$1" = --rename-directory ]; then '+trigger+'; fi\nexec "'+str(self.validator)+'" "$@"')
        result=self.run_script('restore')
        self.assertNotEqual(result.returncode,0)
        self.stub('storage_validate','exec "'+str(self.validator)+'" "$@"')

    def test_sigkill_between_renames_recovers_unique_original_before_mkdir(self):
        self.crash_at_rename('after-original-move')
        self.assertFalse(self.storage.exists())
        self.assertEqual(len(list((self.base/'etc').glob('.storage-restore.*/previous/original'))),1)
        result=self.run_script('backup');self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.storage/'original').read_text(),'keep original')
        self.assertFalse(list((self.base/'etc').glob('.storage-restore.*')))

    def test_sigkill_before_original_move_discards_only_unpublished_staging(self):
        self.crash_at_rename('before-original-move')
        self.assertEqual((self.storage/'original').read_text(),'keep original')
        result=self.run_script('backup');self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(list((self.base/'etc').glob('.storage-restore.*')))

    def test_sigkill_after_publish_retains_both_trees_and_refuses_ambiguity(self):
        self.crash_at_rename('after-publish')
        self.assertEqual((self.storage/'new-data').read_bytes(),b'new')
        result=self.run_script('backup');self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.storage/'new-data').read_bytes(),b'new')
        previous=list((self.base/'etc').glob('.storage-restore.*/previous/original'))
        self.assertEqual(len(previous),1);self.assertEqual(previous[0].read_text(),'keep original')

    def test_multiple_retained_originals_are_not_automatically_selected(self):
        for pid in [1111,2222]:
            container=self.base/'etc'/('.storage-restore.'+str(pid));container.mkdir(mode=0o700)
            previous=container/'previous';previous.mkdir();(previous/'start_script.sh').write_text('old')
        result=self.run_script('backup');self.assertNotEqual(result.returncode,0)
        self.assertEqual(len(list((self.base/'etc').glob('.storage-restore.*/previous/start_script.sh'))),2)
        self.assertEqual((self.storage/'original').read_text(),'keep original')

    def test_untrusted_recovery_container_is_preserved(self):
        target=self.base/'recovery-target';target.mkdir();(target/'sentinel').write_text('safe')
        container=self.base/'etc'/'.storage-restore.1111';container.symlink_to(target)
        result=self.run_script('backup');self.assertNotEqual(result.returncode,0)
        self.assertTrue(container.is_symlink());self.assertEqual((target/'sentinel').read_text(),'safe')

if __name__=='__main__': unittest.main()
