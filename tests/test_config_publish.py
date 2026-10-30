#!/usr/bin/env python3
"""Replay the actual config publisher in private trees with syscall faults.

The fault hooks exist only in a separately compiled test executable. No host
/etc, daemon, network service, flash, or device is accessed.
"""
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'trunk/user/scripts/storage_validate.c'
MAX_BYTES = 2 * 1024 * 1024
PROTOCOL = b'K2P startup config publisher v1\n'


class ConfigPublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-config-code-')
        cls.code = Path(cls.build.name).resolve()
        cls.op = cls.code / 'operation'
        cls.stage = cls.code / 'stage'
        hooks = cls.code / 'hooks.h'
        hooks.write_text(r'''
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
static int fault(const char *s){const char *p=getenv("PUBLISH_FAULT");return p&&!strcmp(p,s);}
static void paused(void){
 const char *p=getenv("PUBLISH_PAUSED");int f=open(p,O_WRONLY|O_CREAT|O_EXCL,0600);
 if(f>=0){write(f,"paused",6);close(f);}for(;;)pause();
}
static ssize_t test_write(int fd,const void*p,size_t n){
 static int calls;
 calls++;
 if(fault("pause-copy")&&calls==1)paused();
 if(fault("short")) return write(fd,p,n>3?3:n);
 if(fault("eintr")&&calls==1){errno=EINTR;return -1;}
 if(fault("zero")) return 0;
 if(fault("partial")){if(calls==1)return write(fd,p,n>7?7:n);errno=ENOSPC;return -1;}
 return write(fd,p,n);
}
static int test_close(int fd){int r=close(fd);if(fault("close")){errno=EIO;return -1;}return r;}
static int test_sync(int fd){
 static int calls;calls++;
 if(fault("file-sync")&&calls==1){errno=EIO;return -1;}
 if(fault("backup-sync")&&calls==2){errno=EIO;return -1;}
 if(fault("published-sync")&&calls==3){errno=EIO;return -1;}
 if(fault("change-before-commit")&&calls==2){
  const char *p=getenv("PUBLISH_DEST");int f=open(p,O_WRONLY|O_TRUNC);if(f<0)return -1;
  if(write(f,"concurrent policy\n",18)!=18){close(f);return -1;}close(f);
 }
 if(fault("same-size-change")&&calls==2){
  const char *p=getenv("PUBLISH_DEST");int f=open(p,O_WRONLY);if(f<0)return -1;
  if(write(f,"X",1)!=1){close(f);return -1;}close(f);
 }
 return fsync(fd);
}
static int test_space(int fd,struct statvfs*st){int r=fstatvfs(fd,st);if(!r&&fault("space"))st->f_bavail=0;return r;}
static int test_rename(int a,const char*b,int c,const char*d){
 if(fault("pause-rename"))paused();
 if(fault("rename")||fault("exdev")){errno=fault("exdev")?EXDEV:EIO;return -1;}
 return renameat(a,b,c,d);
}
static int test_link(int a,const char*b,int c,const char*d,int flags){
 if(fault("first-boot-race")){
  int f=openat(c,d,O_WRONLY|O_CREAT|O_EXCL,0600);
  if(f>=0){write(f,"other valid policy\n",19);close(f);}
 }
 {int r=linkat(a,b,c,d,flags);if(!r&&fault("pause-first-boot-commit"))paused();return r;}
}
static int test_unlink(int a,const char*b,int flags){
 if(fault("cleanup")&&!strcmp(b,"protocol")){errno=EIO;return -1;}return unlinkat(a,b,flags);
}
static ssize_t test_read(int fd,void*p,size_t n){
 if(fault("read")){errno=EIO;return -1;}
 if(fault("read-short")&&n>1)n=1;
 return read(fd,p,n);
}
static int test_stat(int fd,struct stat*st){
 int r=fstat(fd,st);const char*p=getenv("PUBLISH_BAD_OWNER");struct stat other;
 if(!r&&p&&!stat(p,&other)&&st->st_dev==other.st_dev&&st->st_ino==other.st_ino)st->st_uid=(uid_t)(geteuid()+1);
 return r;
}
#define SCP_WRITE test_write
#define SCP_CLOSE test_close
#define SCP_FSYNC test_sync
#define SCP_STATVFS test_space
#define SCP_RENAMEAT test_rename
#define SCP_LINKAT test_link
#define SCP_UNLINKAT test_unlink
#define SCP_READ test_read
#define SCP_FSTAT test_stat
''')
        cls.binary = cls.code / 'publisher'
        command = [shutil.which('clang') or shutil.which('cc'), '-Wall', '-Wextra', '-Werror',
                   '-fsanitize=address,undefined', '-g', '-include', str(hooks),
                   '-DSTARTUP_CONFIG_TEST_UID=geteuid()',
                   '-DSTORAGE_OPERATION_DIR="' + str(cls.op) + '"',
                   '-DSTARTUP_CONFIG_STAGE_DIR="' + str(cls.stage) + '"',
                   str(SOURCE), '-o', str(cls.binary)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        for path in (self.op, self.stage):
            if path.is_symlink() or (path.exists() and not path.is_dir()):
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)
        self.stage.mkdir(mode=0o700)
        self.temp = tempfile.TemporaryDirectory(prefix='k2p-config-case-')
        self.base = Path(self.temp.name).resolve()
        self.inputs = self.base / 'private-inputs'; self.inputs.mkdir(mode=0o700)
        self.parent = self.base / 'storage'; self.parent.mkdir(mode=0o755)
        self.destination = self.parent / 'config'
        self.original = self.inputs / 'original'
        self.candidate = self.inputs / 'candidate'
        self.old = b'PermitRootLogin no\nAllowUsers fixture\n'
        self.new = self.old + b'PasswordAuthentication no\n'
        self.write(self.destination, self.old, 0o644)
        self.write(self.original, self.old)
        self.write(self.candidate, self.new)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, data, mode=0o600):
        path.write_bytes(data); path.chmod(mode)

    def run_publish(self, fault=None, first=False, candidate=None, original=None, destination=None, bad_owner=None):
        env = dict(os.environ, PUBLISH_DEST=str(self.destination))
        if fault: env['PUBLISH_FAULT'] = fault
        else: env.pop('PUBLISH_FAULT', None)
        if bad_owner: env['PUBLISH_BAD_OWNER'] = str(bad_owner)
        else: env.pop('PUBLISH_BAD_OWNER', None)
        result = subprocess.run([str(self.binary), '--publish-config',
                                 str(candidate or self.candidate),
                                 '-' if first else str(original or self.original),
                                 str(destination or self.destination)],
                                capture_output=True, text=True, env=env, timeout=10)
        self.assertNotIn('AddressSanitizer', result.stderr)
        self.assertNotIn('runtime error:', result.stderr)
        return result

    def assert_unpublished(self, result, content=None):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.destination.read_bytes(), self.old if content is None else content)
        self.assertEqual(self.candidate.read_bytes(), self.new)

    def backups(self):
        directory = self.parent / '.config-backups'
        return list(directory.iterdir()) if directory.exists() else []

    def test_replace_atomic_inode_backup_and_private_replacement(self):
        old_inode = self.destination.stat().st_ino
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = Path(result.stdout.strip())
        self.assertEqual(backup, self.parent / '.config-backups/config.before-migration')
        self.assertEqual(backup.stat().st_ino, old_inode)
        self.assertEqual(backup.read_bytes(), self.old)
        self.assertEqual(backup.stat().st_mode & 0o7777, 0o644)
        self.assertEqual(backup.parent.stat().st_mode & 0o7777, 0o700)
        self.assertEqual(self.destination.read_bytes(), self.new)
        self.assertEqual(self.destination.stat().st_mode & 0o7777, 0o600)
        self.assertNotEqual(self.destination.stat().st_ino, old_inode)
        self.assertEqual(self.original.read_bytes(), self.old)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_first_boot_installs_without_backup(self):
        self.destination.unlink()
        result = self.run_publish(first=True)
        self.assertEqual((result.returncode, result.stdout), (0, '-\n'), result.stderr)
        self.assertEqual(self.destination.read_bytes(), self.new)
        self.assertEqual(self.destination.stat().st_nlink, 1)
        self.assertEqual(self.backups(), [])
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_first_boot_never_overwrites_existing_file_or_alias(self):
        self.assert_unpublished(self.run_publish(first=True))
        self.destination.unlink(); self.destination.symlink_to(self.original)
        result = self.run_publish(first=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.destination.is_symlink())

    def test_first_boot_concurrent_creation_is_not_overwritten(self):
        self.destination.unlink()
        result = self.run_publish(first=True, fault='first-boot-race')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.destination.read_bytes(), b'other valid policy\n')

    def test_short_writes_and_eintr_are_completed(self):
        for fault in ('short', 'eintr'):
            with self.subTest(fault=fault):
                self.setUp_again_policy()
                result = self.run_publish(fault)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.destination.read_bytes(), self.new)

    def setUp_again_policy(self):
        self.destination.unlink(missing_ok=True)
        self.write(self.destination, self.old, 0o644)
        backup_dir = self.parent / '.config-backups'
        if backup_dir.exists(): shutil.rmtree(backup_dir)

    def test_partial_enospc_and_zero_write_preserve_old(self):
        for fault in ('partial', 'zero'):
            with self.subTest(fault=fault):
                self.assert_unpublished(self.run_publish(fault))
                self.assertEqual(self.backups(), [])
                self.assertEqual(list(self.stage.iterdir()), [])

    def test_close_fsync_and_space_fail_before_backup(self):
        for fault in ('close', 'file-sync', 'space'):
            with self.subTest(fault=fault):
                self.assert_unpublished(self.run_publish(fault))
                self.assertEqual(self.backups(), [])
                self.assertEqual(list(self.stage.iterdir()), [])

    def test_rename_failure_and_retry_reuse_same_backup_slot(self):
        self.assert_unpublished(self.run_publish('rename'))
        backup = self.backups()[0]
        self.assertEqual(self.destination.stat().st_nlink, 2)
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), backup)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(backup.stat().st_nlink, 1)

    def test_exdev_does_not_fall_back_to_copy_over_destination(self):
        self.assert_unpublished(self.run_publish('exdev'))
        self.assertEqual(len(self.backups()), 1)

    def test_backup_sync_failure_is_uncommitted_and_retryable(self):
        self.assert_unpublished(self.run_publish('backup-sync'))
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.backups()), 1)

    def test_post_commit_sync_error_has_distinct_committed_status(self):
        result = self.run_publish('published-sync')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('published config;', result.stderr)
        self.assertTrue(Path(result.stdout.strip()).is_file())
        self.assertEqual(self.destination.read_bytes(), self.new)

    def test_post_commit_cleanup_error_is_not_reported_as_unpublished(self):
        result = self.run_publish('cleanup')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('published config;', result.stderr)
        self.assertEqual(self.destination.read_bytes(), self.new)
        self.assertTrue(Path(result.stdout.strip()).is_file())
        result = self.run_publish()
        self.assertEqual(result.returncode, 1)  # Snapshot still deliberately describes the old config.
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_read_error_and_short_reads(self):
        self.assert_unpublished(self.run_publish('read'))
        result = self.run_publish('read-short')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.destination.read_bytes(), self.new)

    def test_exact_budget_and_empty_candidate(self):
        for data in (b'', b'x' * MAX_BYTES):
            with self.subTest(size=len(data)):
                self.setUp_again_policy()
                self.write(self.candidate, data)
                result = self.run_publish()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.destination.read_bytes(), data)

    def test_oversize_candidate_or_snapshot_are_rejected(self):
        self.write(self.candidate, b'x' * (MAX_BYTES + 1))
        self.assertEqual(self.run_publish().returncode, 1)
        self.assertEqual(self.destination.read_bytes(), self.old)
        self.write(self.candidate, self.new)
        self.write(self.original, b'x' * (MAX_BYTES + 1))
        self.assert_unpublished(self.run_publish())

    def test_snapshot_bytes_must_match(self):
        self.write(self.original, b'other policy\n')
        self.assert_unpublished(self.run_publish())

    def test_source_symlink_and_hardlink_are_rejected(self):
        for path in (self.candidate, self.original):
            with self.subTest(path=path.name):
                saved = path.read_bytes(); path.unlink(); path.symlink_to(self.destination)
                self.assertEqual(self.run_publish().returncode, 1)
                path.unlink(); self.write(path, saved)
                alias = self.inputs / 'alias'; os.link(path, alias)
                self.assertEqual(self.run_publish().returncode, 1)
                alias.unlink()
        self.assertEqual(self.destination.read_bytes(), self.old)

    def test_source_modes_and_private_parent_are_required(self):
        for mode in (0o644, 0o400, 0o660, 0o4600):
            with self.subTest(mode=oct(mode)):
                self.candidate.chmod(mode)
                self.assertEqual(self.run_publish().returncode, 1)
        self.candidate.chmod(0o600); self.inputs.chmod(0o755)
        self.assert_unpublished(self.run_publish())

    def test_ownership_metadata_negative_controls(self):
        lock = self.prepare_lock()
        for path in (self.candidate, self.original, self.destination, self.parent, self.inputs, lock, self.op):
            with self.subTest(path=path.name):
                self.assert_unpublished(self.run_publish(bad_owner=path))

    def test_destination_alias_special_file_and_writable_mode_rejected(self):
        self.destination.unlink(); self.destination.symlink_to(self.original)
        self.assertEqual(self.run_publish().returncode, 1)
        self.destination.unlink(); os.mkfifo(self.destination, 0o600)
        self.assertEqual(self.run_publish().returncode, 1)
        self.destination.unlink(); self.write(self.destination, self.old, 0o666)
        self.assert_unpublished(self.run_publish())

    def test_unaccounted_destination_hardlink_rejected(self):
        alias = self.base / 'outside-alias'; os.link(self.destination, alias)
        self.assert_unpublished(self.run_publish())
        self.assertEqual(alias.read_bytes(), self.old)

    def test_destination_parent_writable_or_symlink_component_rejected(self):
        self.parent.chmod(0o777)
        self.assert_unpublished(self.run_publish())
        self.parent.chmod(0o755)
        alias = self.base / 'parent-alias'; alias.symlink_to(self.parent, target_is_directory=True)
        self.assert_unpublished(self.run_publish(destination=alias / 'config'))

    def prepare_lock(self):
        self.op.mkdir(mode=0o700)
        lock = self.op / 'lock'; self.write(lock, b'')
        return lock

    def test_real_flock_contention_preserves_old_and_releases_after_exit(self):
        lock = self.prepare_lock()
        with lock.open('w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assert_unpublished(self.run_publish())
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        with lock.open('w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_unsafe_lock_directory_and_lock_inode_rejected(self):
        lock = self.prepare_lock()
        self.op.chmod(0o755); self.assert_unpublished(self.run_publish()); self.op.chmod(0o700)
        for kind in ('mode', 'symlink', 'hardlink', 'fifo'):
            with self.subTest(kind=kind):
                lock.unlink()
                if kind == 'mode': self.write(lock, b'', 0o644)
                elif kind == 'symlink': lock.symlink_to(self.original)
                elif kind == 'hardlink': os.link(self.original, lock)
                else: os.mkfifo(lock, 0o600)
                self.assert_unpublished(self.run_publish())

    def test_unsafe_lock_directory_symlink_rejected(self):
        self.op.symlink_to(self.inputs, target_is_directory=True)
        self.assert_unpublished(self.run_publish())

    def test_unsafe_backup_directory_is_not_followed_or_relaxed(self):
        backup = self.parent / '.config-backups'; backup.symlink_to(self.inputs, target_is_directory=True)
        self.assert_unpublished(self.run_publish()); backup.unlink()
        backup.mkdir(mode=0o755)
        self.assert_unpublished(self.run_publish())
        self.assertEqual(backup.stat().st_mode & 0o7777, 0o755)

    def test_legacy_and_private_slots_share_one_ten_slot_limit(self):
        backup = self.parent / '.config-backups'; backup.mkdir(mode=0o700)
        for slot in range(10):
            name = 'config.before-migration' + ('.' + str(slot) if slot else '')
            self.write((self.parent if slot % 2 else backup) / name, b'prior backup\n')
        self.assert_unpublished(self.run_publish())
        self.assertEqual(len(list(self.parent.glob('config.before-migration*'))) + len(self.backups()), 10)

    def test_existing_backup_aliases_occupy_slots_without_following(self):
        backup = self.parent / '.config-backups'; backup.mkdir(mode=0o700)
        (backup / 'config.before-migration').symlink_to(self.original)
        (self.parent / 'config.before-migration.1').symlink_to(self.original)
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.rstrip().endswith('.2'))
        self.assertEqual(self.original.read_bytes(), self.old)

    def test_multiple_private_accounted_links_reused_but_external_link_rejected(self):
        backup = self.parent / '.config-backups'; backup.mkdir(mode=0o700)
        for slot in ('', '.1'): os.link(self.destination, backup / ('config.before-migration' + slot))
        alias = self.base / 'outside'; os.link(self.destination, alias)
        self.assert_unpublished(self.run_publish()); alias.unlink()
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.backups()), 2)

    def test_change_after_backup_is_not_published(self):
        self.assert_unpublished(self.run_publish('change-before-commit'), b'concurrent policy\n')

    def test_same_size_change_after_backup_is_detected_by_bytes(self):
        self.assert_unpublished(self.run_publish('same-size-change'), b'X' + self.old[1:])

    def kill_paused(self, fault, first=False):
        marker = self.base / 'paused'
        env = dict(os.environ, PUBLISH_FAULT=fault, PUBLISH_DEST=str(self.destination), PUBLISH_PAUSED=str(marker))
        process = subprocess.Popen([str(self.binary), '--publish-config', str(self.candidate),
                                    '-' if first else str(self.original), str(self.destination)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.exists(), 'publisher did not reach the isolated pause point')
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, -signal.SIGKILL, (stdout, stderr))
        finally:
            if process.poll() is None:
                process.kill(); process.communicate(timeout=5)

    def test_sigkill_copy_recovers_stage_and_kernel_releases_lock(self):
        self.kill_paused('pause-copy')
        self.assertEqual(self.destination.read_bytes(), self.old)
        self.assertEqual(len(list(self.stage.iterdir())), 1)
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_sigkill_after_backup_reuses_inode_and_slot(self):
        self.kill_paused('pause-rename')
        self.assertEqual(self.destination.read_bytes(), self.old)
        self.assertEqual(self.destination.stat().st_nlink, 2)
        self.assertEqual(len(self.backups()), 1)
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_sigkill_first_boot_commit_recovers_only_own_link_then_migrates(self):
        self.destination.unlink()
        self.kill_paused('pause-first-boot-commit', first=True)
        self.assertEqual(self.destination.read_bytes(), self.new)
        self.assertEqual(self.destination.stat().st_nlink, 2)
        self.write(self.original, self.new)
        self.write(self.candidate, self.new + b'# subsequent validated migration\n')
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.destination.stat().st_nlink, 1)
        self.assertEqual(list(self.stage.iterdir()), [])

    def make_orphan(self, number=1, marker=PROTOCOL, extra=False, linked=False):
        directory = self.stage / ('.config-publish.1234.' + str(number))
        directory.mkdir(mode=0o700)
        self.write(directory / 'protocol', marker)
        self.write(directory / 'candidate', b'uncommitted temporary bytes\n')
        if extra: self.write(directory / 'unknown', b'preserve me\n')
        if linked: os.link(directory / 'candidate', self.base / ('alias-' + str(number)))
        return directory

    def test_recognized_orphan_is_recovered_under_lock(self):
        orphan = self.make_orphan()
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(orphan.exists())
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_unknown_or_aliased_orphan_is_retained(self):
        orphans = [self.make_orphan(1, extra=True), self.make_orphan(2, marker=b'other protocol\n'),
                   self.make_orphan(3, linked=True)]
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('retained unrecognized', result.stderr)
        for orphan in orphans: self.assertTrue((orphan / 'candidate').is_file())

    def test_unrecognized_staging_budget_is_bounded(self):
        for number in range(20): self.make_orphan(number, extra=True)
        self.assert_unpublished(self.run_publish())
        self.assertEqual(len(list(self.stage.iterdir())), 20)

    def test_explicit_private_old_mode_is_preserved_in_backup(self):
        self.destination.chmod(0o600)
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).stat().st_mode & 0o7777, 0o600)

    def test_helper_makefile_tracks_new_header_dependency(self):
        self.assertIn('storage_validate: storage_validate.c startup_config_publish.h',
                      (SOURCE.parent / 'Makefile').read_text())


if __name__ == '__main__':
    unittest.main()
