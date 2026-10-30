#!/usr/bin/env python3
"""Actual upgrade writer with ordinary files and inert MTD IOCTL backends.

Neither real devices nor reboot/daemon functions are linked into the harness.
The syscall faults exist only in this separately compiled host test program.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import tempfile
import time
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'trunk/user/mtd_write'
LIMIT = 15925248


def image(payload_bytes=9000, product=b'K2P', boundary=4096):
    data = bytearray(b'\x00' * (64 + payload_bytes))
    data[28:32] = bytes([5, 5, 2, 3])
    data[32:36] = bytes([4, 4, 1, 1])
    data[36:36 + len(product)] = product
    struct.pack_into('>I', data, 60, boundary)
    data[64:] = bytes((n % 251 for n in range(payload_bytes)))
    data[boundary:boundary + 4] = b'hsqs'
    struct.pack_into('>7I', data, 0, 0x27051956, 0, 0, payload_bytes,
                     0x81001000, 0x81001000, zlib.crc32(data[64:]) & 0xffffffff)
    struct.pack_into('>I', data, 4, zlib.crc32(data[:64]) & 0xffffffff)
    return bytes(data)


class FirmwareWriterProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-writer-code-')
        cls.code = Path(cls.build.name).resolve()
        cls.operation = cls.code / 'operation'
        harness = cls.code / 'writer.c'
        harness.write_text(r'''
#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "mtd-abi.h"
static int device_fd=-1,reader_fd=-1,stage=0,device_writes=0,image_reads=0,readbacks=0,sync_calls=0,memory_resident=0;
static int fault(const char*s){const char*p=getenv("WRITER_FAULT");return p&&!strcmp(p,s);}
static void event(const char*s){
 int fd=open(getenv("WRITER_LOG"),O_WRONLY|O_CREAT|O_APPEND,0600);
 if(fd>=0){write(fd,s,strlen(s));write(fd,"\n",1);close(fd);}
}
static void paused(void){
 const char*p=getenv("WRITER_PAUSED");int f=open(p,O_WRONLY|O_CREAT|O_EXCL,0600);
 if(f>=0){write(f,"paused",6);close(f);}for(;;)pause();
}
static int state_is_maybe(void){
 char data[256];int fd=open(getenv("WRITER_STATUS"),O_RDONLY);ssize_t n;
 if(fd<0)return 0;n=read(fd,data,sizeof(data)-1);close(fd);if(n<0)return 0;data[n]=0;
 return strstr(data,"\nstate=MAYBE_WRITTEN\n")!=NULL;
}
static int mock_open(struct mtd_info_user*info,int*reader){
 event("open-device");if(fault("open")){errno=EACCES;return -1;}
 memset(info,0,sizeof(*info));info->size=15925248;info->erasesize=4096;
 info->type=MTD_NORFLASH;info->flags=MTD_WRITEABLE;info->writesize=1;
 if(fault("nand"))info->type=MTD_NANDFLASH;
 if(fault("geometry"))info->erasesize=6000;
 if(fault("partition"))info->size++;
 if(fault("readonly"))info->flags=0;
 device_fd=open(getenv("WRITER_DEVICE"),O_RDWR);*reader=reader_fd=open(getenv("WRITER_DEVICE"),O_RDONLY);return device_fd;
}
static int mock_ioctl(int fd,unsigned long command,void*arg){
 struct erase_info_user*erase=arg;unsigned char empty[4096];off_t offset;
 if(fd!=device_fd||!state_is_maybe()||!memory_resident){event("UNSAFE-IOCTL");errno=EPERM;return -1;}
 if(command==MEMUNLOCK){event("unlock");if(fault("unlock-unsupported")){errno=EOPNOTSUPP;return -1;}
  if(fault("unlock")){errno=EIO;return -1;}return 0;}
 if(command!=MEMERASE){event("UNKNOWN-IOCTL");errno=EINVAL;return -1;}
 event("erase");if(fault("pause-erase"))paused();if(fault("erase")){errno=EIO;return -1;}
 memset(empty,0xff,sizeof(empty));
 for(offset=erase->start;offset<(off_t)(erase->start+erase->length);offset+=(off_t)sizeof(empty))
  if(pwrite(fd,empty,sizeof(empty),offset)!=(ssize_t)sizeof(empty))return -1;
 return 0;
}
static ssize_t device_write(int fd,const void*p,size_t n){
 if(fd!=device_fd||!state_is_maybe()||!memory_resident){event("UNSAFE-WRITE");errno=EPERM;return -1;}
 event("write");device_writes++;
 if(fault("write")){errno=EIO;return -1;}
 if(fault("zero"))return 0;
 if(fault("write-eintr")&&device_writes==1){errno=EINTR;return -1;}
 if(fault("short")&&n>17)n=17;
 if(fault("partial")){if(device_writes>1){errno=ENOSPC;return -1;}if(n>7)n=7;}
 if(fault("change-source")&&device_writes==1){int f=open(getenv("WRITER_IMAGE"),O_WRONLY);if(f>=0){write(f,"X",1);close(f);}}
 return write(fd,p,n);
}
static ssize_t device_read(int fd,void*p,size_t n,off_t offset){
 ssize_t got;readbacks++;
 if(fault("pre-read")&&readbacks==1){errno=EIO;return -1;}
 if(readbacks>1){event("readback");if(fault("readback")){errno=EIO;return -1;}
  if(fault("readback-eintr")&&readbacks==2){errno=EINTR;return -1;}}
 if(fault("readback-short")&&n>13)n=13;
 got=pread(fd,p,n,offset);
 if(readbacks>1&&fault("mismatch")&&got>0)((unsigned char*)p)[0]^=1;
 if(readbacks>1&&fault("padding-mismatch")&&offset+n>9064&&got>0)((unsigned char*)p)[got-1]^=1;
 return got;
}
static int device_sync(int fd){event("device-sync");sync_calls++;
 if(fault("sync")&&sync_calls>1){errno=EIO;return -1;}
 if(fault("pre-sync")){errno=EIO;return -1;}
 if(fault("sync-unsupported")){errno=EINVAL;return -1;}
 if(fault("sync-changed")&&sync_calls==1){errno=EINVAL;return -1;}
 if(fault("sync-changed")&&sync_calls>1){errno=EIO;return -1;}
 return fsync(fd);}
static int device_close(int fd){int r;int writer=fd==device_fd;
 event(writer?"writer-close":"reader-close");r=close(fd);if(writer)device_fd=-1;else reader_fd=-1;
 if((writer&&fault("close"))||(!writer&&fault("reader-close"))){errno=EIO;return -1;}return r;}
static ssize_t image_read(int fd,void*p,size_t n){
 image_reads++;if(fault("image-read")){errno=EIO;return -1;}
 if(fault("image-eintr")&&image_reads==1){errno=EINTR;return -1;}
 if(fault("image-short")&&n>19)n=19;
 if(fault("image-eof"))return 0;return read(fd,p,n);
}
static int image_close(int fd){int r=close(fd);if(fault("image-close")){errno=EIO;return -1;}return r;}
static ssize_t state_write(int fd,const void*p,size_t n){
 char data[256];size_t length=n<sizeof(data)-1?n:sizeof(data)-1;
 memcpy(data,p,length);data[length]=0;
 if(strstr(data,"state=PREWRITE"))stage=1;
 if(strstr(data,"state=MAYBE_WRITTEN"))stage=2;
 if(strstr(data,"state=VERIFIED"))stage=3;
 if((stage==1&&fault("initial-write"))||(stage==2&&fault("maybe-write"))||(stage==3&&fault("verified-write"))){errno=ENOSPC;return -1;}
 return write(fd,p,n);
}
static int state_sync(int fd){struct stat st;fstat(fd,&st);
 if((stage==1&&fault("initial-sync"))||(stage==2&&fault("maybe-sync"))||(stage==3&&fault("verified-sync"))){errno=EIO;return -1;}
 if(S_ISDIR(st.st_mode)&&((stage==2&&fault("maybe-dir-sync"))||(stage==3&&fault("verified-dir-sync")))){errno=EIO;return -1;}
 if(stage==2&&fault("pause-maybe"))paused();return fsync(fd);
}
static int state_close(int fd){int r=close(fd);
 if((stage==1&&fault("initial-close"))||(stage==2&&fault("maybe-close"))||(stage==3&&fault("verified-close"))){errno=EIO;return -1;}return r;}
static int state_rename(int a,const char*b,int c,const char*d){
 if((stage==2&&fault("maybe-rename"))||(stage==3&&fault("verified-rename"))){errno=EIO;return -1;}return renameat(a,b,c,d);}
static void*allocate(size_t n){if(fault("memory")){errno=ENOMEM;return NULL;}return malloc(n);}
static int memory_lock(int flags){event("memory-lock");if(flags!=(MCL_CURRENT|MCL_FUTURE)){errno=EINVAL;return -1;}
 if(fault("memory-lock")){errno=ENOMEM;return -1;}memory_resident=1;return 0;}
static int memory_unlock(void){event("memory-unlock");memory_resident=0;return 0;}
#define FWUP_OPEN_DEVICE mock_open
#define FWUP_IOCTL mock_ioctl
#define FWUP_DEVICE_WRITE device_write
#define FWUP_DEVICE_READ device_read
#define FWUP_DEVICE_SYNC device_sync
#define FWUP_DEVICE_CLOSE device_close
#define FWUP_IMAGE_READ image_read
#define FWUP_IMAGE_CLOSE image_close
#define FWUP_STATE_WRITE state_write
#define FWUP_STATE_SYNC state_sync
#define FWUP_STATE_CLOSE state_close
#define FWUP_STATE_RENAME state_rename
#define FWUP_ALLOC allocate
#define FWUP_MLOCKALL memory_lock
#define FWUP_MUNLOCKALL memory_unlock
#include "upgrade_write.h"
int main(int argc,char**argv){if(argc!=4)return 99;return firmware_upgrade_write(argv[1],argv[2],argv[3]);}
''')
        cls.binary = cls.code / 'writer'
        command = [shutil.which('clang') or shutil.which('cc'), '-Wall', '-Wextra', '-Werror',
                   '-fsanitize=address,undefined', '-g', '-DFWUP_TEST_UID=geteuid()',
                   '-DFWUP_OPERATION_DIR="' + str(cls.operation) + '"',
                   '-I' + str(SOURCE), '-I' + str(ROOT / 'trunk/user/shared/include'),
                   str(harness), str(SOURCE / 'crc32.c'), '-o', str(cls.binary)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode: raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls): cls.build.cleanup()

    def setUp(self):
        if self.operation.exists(): shutil.rmtree(self.operation)
        self.temp = tempfile.TemporaryDirectory(prefix='k2p-writer-case-')
        self.base = Path(self.temp.name).resolve()
        self.attempt = self.base / 'attempt'; self.attempt.mkdir(mode=0o700)
        self.status = self.attempt / 'status'
        self.image = self.base / 'linux.trx'; self.image.write_bytes(image()); self.image.chmod(0o600)
        self.expected = self.image.read_bytes()
        self.device = self.base / 'ordinary-file-mtd'
        with self.device.open('wb') as stream: stream.truncate(LIMIT)
        self.log = self.base / 'events'

    def tearDown(self): self.temp.cleanup()

    def environment(self, fault=None):
        env = dict(os.environ, WRITER_DEVICE=str(self.device), WRITER_IMAGE=str(self.image),
                   WRITER_LOG=str(self.log), WRITER_STATUS=str(self.status))
        if fault: env['WRITER_FAULT'] = fault
        else: env.pop('WRITER_FAULT', None)
        return env

    def run_writer(self, fault=None, target='firmware'):
        result = subprocess.run([str(self.binary), str(self.image), target, str(self.status)],
                                env=self.environment(fault), capture_output=True, text=True, timeout=10)
        self.assertNotIn('AddressSanitizer', result.stderr)
        self.assertNotIn('runtime error:', result.stderr)
        return result

    def events(self): return self.log.read_text().splitlines() if self.log.exists() else []

    def record(self):
        text = self.status.read_text()
        lines = text.splitlines()
        self.assertEqual(len(lines), 6, text)
        self.assertEqual(lines[0], 'K2P_FWUP_V1')
        values = dict(line.split('=', 1) for line in lines[1:])
        self.assertEqual(set(values), {'state', 'pid', 'target', 'image_bytes', 'verified_bytes'})
        self.assertEqual(values['target'], 'firmware')
        self.assertTrue(values['pid'].isdigit())
        self.assertEqual(self.status.stat().st_mode & 0o7777, 0o600)
        self.assertEqual(self.status.stat().st_nlink, 1)
        return values

    def assert_prewrite(self, result):
        self.assertEqual(result.returncode, 20, result.stderr)
        record = self.record(); self.assertEqual(record['state'], 'PREWRITE')
        self.assertEqual((record['image_bytes'], record['verified_bytes']), ('0', '0'))
        self.assertFalse(set(self.events()) & {'unlock', 'erase', 'write', 'UNSAFE-WRITE', 'UNSAFE-IOCTL'})

    def assert_unknown(self, result, state='MAYBE_WRITTEN'):
        self.assertEqual(result.returncode, 21, result.stderr)
        self.assertEqual(self.record()['state'], state)
        self.assertNotIn('UNSAFE-WRITE', self.events()); self.assertNotIn('UNSAFE-IOCTL', self.events())

    def test_complete_write_readback_and_private_verified_record(self):
        result = self.run_writer(); self.assertEqual(result.returncode, 0, result.stderr)
        record = self.record(); self.assertEqual(record['state'], 'VERIFIED')
        self.assertEqual((int(record['image_bytes']), int(record['verified_bytes'])), (len(self.expected), len(self.expected)))
        actual = self.device.read_bytes(); self.assertEqual(actual[:len(self.expected)], self.expected)
        end = (len(self.expected) + 4095) // 4096 * 4096
        self.assertEqual(actual[len(self.expected):end], b'\xff' * (end - len(self.expected)))
        self.assertEqual(self.events().count('erase'), end // 4096)
        self.assertTrue(self.events().index('device-sync') < self.events().index('writer-close') < self.events().index('readback') < self.events().index('reader-close'))

    def test_source_is_immutable_after_preflight(self):
        result = self.run_writer('change-source'); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.image.read_bytes(), self.expected)
        self.assertEqual(self.device.read_bytes()[:len(self.expected)], self.expected)

    def test_partial_device_writes_and_eintr_are_completed(self):
        for fault in ('short', 'write-eintr', 'readback-short', 'readback-eintr', 'image-short', 'image-eintr', 'unlock-unsupported', 'sync-unsupported'):
            with self.subTest(fault=fault):
                self.status.unlink(missing_ok=True)
                result = self.run_writer(fault); self.assertEqual(result.returncode, 0, result.stderr)

    def test_open_and_geometry_failures_are_strict_prewrite(self):
        for fault in ('open', 'nand', 'geometry', 'partition', 'readonly', 'pre-read', 'pre-sync', 'memory'):
            with self.subTest(fault=fault):
                self.status.unlink(missing_ok=True); self.assert_prewrite(self.run_writer(fault))

    def test_image_io_failures_are_strict_prewrite(self):
        for fault in ('image-read', 'image-eof', 'image-close'):
            with self.subTest(fault=fault):
                self.status.unlink(missing_ok=True); self.assert_prewrite(self.run_writer(fault))

    def test_invalid_header_payload_crc_product_and_boundary_are_prewrite(self):
        for offset in (0, 4, 12, 24, 28, 36, 60, 80):
            with self.subTest(offset=offset):
                data = bytearray(self.expected); data[offset] ^= 1
                self.image.write_bytes(data); self.status.unlink(missing_ok=True)
                self.assert_prewrite(self.run_writer())

    def test_valid_crc_wrong_kernel_tag_load_and_entry_are_prewrite(self):
        controls=((32,b'\x03'),(33,b'\x05'),(16,struct.pack('>I',0x80001000)),
                  (20,struct.pack('>I',0x81000ffc)),(20,struct.pack('>I',0x81001001)),
                  (20,struct.pack('>I',0x83001000)))
        for offset,value in controls:
            with self.subTest(offset=offset,value=value.hex()):
                data=bytearray(self.expected);data[offset:offset+len(value)]=value
                data[4:8]=b'\0'*4;struct.pack_into('>I',data,4,zlib.crc32(data[:64])&0xffffffff)
                self.image.write_bytes(data);self.status.unlink(missing_ok=True)
                self.assert_prewrite(self.run_writer())

    def test_oversized_empty_and_nonregular_source_rejected_before_erase(self):
        for data in (b'', b'x' * 63, b'x' * (LIMIT + 1)):
            with self.subTest(size=len(data)):
                self.image.write_bytes(data); self.status.unlink(missing_ok=True)
                self.assert_prewrite(self.run_writer())
        self.image.unlink(); os.mkfifo(self.image, 0o600); self.status.unlink()
        self.assert_prewrite(self.run_writer())

    def test_source_alias_and_world_writable_modes_are_prewrite(self):
        self.image.chmod(0o666); self.assert_prewrite(self.run_writer())
        self.image.chmod(0o600); self.status.unlink()
        alias = self.base / 'alias'; os.link(self.image, alias)
        self.assert_prewrite(self.run_writer()); alias.unlink(); self.status.unlink()
        self.image.unlink(); self.image.symlink_to(self.device)
        self.assert_prewrite(self.run_writer())

    def test_fresh_status_required_no_stale_or_alias_overwrite(self):
        self.status.write_text('stale VERIFIED'); self.status.chmod(0o600)
        result = self.run_writer(); self.assertEqual(result.returncode, 21)
        self.assertEqual(self.status.read_text(), 'stale VERIFIED')
        self.status.unlink(); self.status.symlink_to(self.image)
        self.assertEqual(self.run_writer().returncode, 21); self.assertTrue(self.status.is_symlink())
        self.assertEqual(self.events(), [])

    def test_private_status_directory_required(self):
        self.attempt.chmod(0o755)
        self.assertEqual(self.run_writer().returncode, 21)
        self.assertFalse(self.status.exists()); self.assertEqual(self.events(), [])

    def test_incorrect_target_and_unsafe_parent_component_unknown(self):
        self.assertEqual(self.run_writer(target='Storage').returncode, 21)
        self.assertFalse(self.status.exists())
        self.attempt.rename(self.base / 'real-attempt'); self.attempt.symlink_to(self.base / 'real-attempt', target_is_directory=True)
        self.assertEqual(self.run_writer().returncode, 21); self.assertEqual(self.events(), [])

    def test_initial_status_failure_is_unknown_not_safe(self):
        self.assertEqual(self.run_writer('initial-write').returncode, 21)
        self.assertEqual(self.events(), [])

    def test_status_close_sync_and_rename_failures_never_report_safe(self):
        for fault, state in (('initial-close', 'PREWRITE'), ('initial-sync', 'PREWRITE'),
                             ('maybe-close', 'PREWRITE'), ('maybe-sync', 'PREWRITE'),
                             ('maybe-rename', 'PREWRITE'), ('verified-close', 'MAYBE_WRITTEN'),
                             ('verified-sync', 'MAYBE_WRITTEN'), ('verified-rename', 'MAYBE_WRITTEN')):
            with self.subTest(fault=fault):
                self.status.unlink(missing_ok=True)
                if self.log.exists(): self.log.unlink()
                self.assert_unknown(self.run_writer(fault), state)
                if not fault.startswith('verified'):
                    self.assertFalse(set(self.events()) & {'unlock', 'erase', 'write'})

    def test_memory_residency_failure_is_safe_before_maybe_and_releases_partial_locks(self):
        self.assert_prewrite(self.run_writer('memory-lock'))
        self.assertIn('memory-lock', self.events());self.assertIn('memory-unlock', self.events())
        self.assertLess(self.events().index('memory-lock'), self.events().index('memory-unlock'))

    def test_post_touch_paths_remain_locked_until_process_exit(self):
        for fault in (None, 'erase', 'write', 'readback', 'verified-write'):
            with self.subTest(fault=fault):
                self.status.unlink(missing_ok=True);self.log.unlink(missing_ok=True)
                result=self.run_writer(fault)
                self.assertEqual(result.returncode,0 if fault is None else 21,result.stderr)
                self.assertIn('memory-lock',self.events());self.assertNotIn('memory-unlock',self.events())
                if 'erase' in self.events():self.assertLess(self.events().index('memory-lock'),self.events().index('erase'))

    def test_dynamic_binding_is_eager_in_production_link(self):
        self.assertIn('-Wl,-z,now',(SOURCE/'Makefile').read_text())

    def test_maybe_status_failure_never_touches_flash_and_is_unknown(self):
        self.assert_unknown(self.run_writer('maybe-write'), 'PREWRITE')
        self.assertFalse(set(self.events()) & {'unlock', 'erase', 'write'})

    def test_maybe_directory_sync_failure_is_conservative_unknown(self):
        self.assert_unknown(self.run_writer('maybe-dir-sync'))
        self.assertFalse(set(self.events()) & {'unlock', 'erase', 'write'})

    def test_unlock_erase_write_sync_readback_and_close_failures_are_unknown(self):
        for fault in ('unlock', 'erase', 'write', 'zero', 'partial', 'sync', 'sync-changed', 'readback', 'mismatch', 'padding-mismatch', 'close', 'reader-close'):
            with self.subTest(fault=fault):
                self.status.unlink(missing_ok=True); self.assert_unknown(self.run_writer(fault))

    def test_verified_status_failure_does_not_claim_complete_success(self):
        self.assert_unknown(self.run_writer('verified-write'))
        self.assertEqual(self.device.read_bytes()[:len(self.expected)], self.expected)

    def test_verified_directory_sync_failure_requires_exit_and_state_pair(self):
        self.assert_unknown(self.run_writer('verified-dir-sync'), 'VERIFIED')
        self.assertEqual(self.device.read_bytes()[:len(self.expected)], self.expected)

    def test_real_global_lock_contention_is_unknown_to_avoid_disrupting_other_writer(self):
        self.operation.mkdir(mode=0o700)
        lock = self.operation / 'lock'; lock.write_bytes(b''); lock.chmod(0o600)
        with lock.open('w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assert_unknown(self.run_writer(), 'PREWRITE')
            self.assertFalse(set(self.events()) & {'unlock', 'erase', 'write'})

    def test_unsafe_global_lock_is_never_followed(self):
        self.operation.mkdir(mode=0o700)
        (self.operation / 'lock').symlink_to(self.image)
        self.assert_unknown(self.run_writer(), 'PREWRITE')
        self.assertEqual(self.image.read_bytes(), self.expected)

    def kill_paused(self, fault):
        paused = self.base / 'paused'
        env = self.environment(fault); env['WRITER_PAUSED'] = str(paused)
        process = subprocess.Popen([str(self.binary), str(self.image), 'firmware', str(self.status)],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not paused.exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(0.01)
            self.assertTrue(paused.exists(), 'mock pause point not reached')
            process.kill(); process.communicate(timeout=5)
            self.assertEqual(process.returncode, -signal.SIGKILL)
        finally:
            if process.poll() is None: process.kill(); process.communicate(timeout=5)

    def test_sigkill_after_maybe_does_not_leave_safe_prewrite(self):
        self.kill_paused('pause-erase')
        self.assertEqual(self.record()['state'], 'MAYBE_WRITTEN')
        lock = self.operation / 'lock'
        with lock.open('w') as handle: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_sigkill_during_maybe_publication_may_retain_prewrite_but_not_safe_exit(self):
        self.kill_paused('pause-maybe')
        self.assertEqual(self.record()['state'], 'PREWRITE')
        self.assertFalse(set(self.events()) & {'unlock', 'erase', 'write'})

    def test_only_explicit_upgrade_cli_routes_to_new_protocol_before_getopt(self):
        text = (SOURCE / 'mtd.c').read_text()
        branch = text.index('if (argc > 1 && !strcmp(argv[1], "--upgrade-write"))')
        self.assertLess(branch, text.index('while ((ch = getopt'))
        self.assertIn('return firmware_upgrade_write(argv[2], argv[3], argv[4]);', text)
        self.assertIn('case CMD_WRITE:', text)
        self.assertIn('if (boot)\n\t\tdo_reboot();', text)

    def test_new_writer_has_no_reboot_or_legacy_write_call(self):
        header = (SOURCE / 'upgrade_write.h').read_text()
        self.assertNotIn('do_reboot(', header); self.assertNotIn('system(', header)
        self.assertNotIn('mtd_write(', header)


class FirmwareDeviceDiscoveryTests(unittest.TestCase):
    """Exercise the production /proc label adapter with a synthetic table.

    Only fstat's device type and MEMGETINFO are mocked; production discovery,
    open flags, case-folded exact label selection and dual-fd checks run.
    """
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-mtd-discovery-')
        cls.base = Path(cls.build.name).resolve()
        cls.table = cls.base / 'table'
        cls.prefix = cls.base / 'mtd'
        harness = cls.base / 'discovery.c'
        harness.write_text(r'''
#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "mtd-abi.h"
static int calls;
static int test_stat(int fd,struct stat*st){int r=fstat(fd,st);if(!r&&!getenv("DISCOVER_REGULAR"))st->st_mode=(st->st_mode&07777)|S_IFCHR;return r;}
static int test_ioctl(int fd,unsigned long command,void*p){
 struct mtd_info_user*info=p;(void)fd;calls++;
 if(command!=MEMGETINFO){errno=EINVAL;return -1;}
 memset(info,0,sizeof(*info));info->size=15925248;info->erasesize=65536;
 info->type=MTD_NORFLASH;info->writesize=1;info->flags=MTD_WRITEABLE;
 if(getenv("DISCOVER_RW_MISMATCH")&&calls==1)info->size--;
 if(getenv("DISCOVER_RO_MISMATCH")&&calls==2)info->erasesize=4096;
 return 0;
}
#define FWUP_IOCTL test_ioctl
#define FWUP_MTD_FSTAT test_stat
#include "upgrade_write.h"
int main(void){struct mtd_info_user info;int reader=-1,fd=fwup_open_device(&info,&reader);
 if(fd<0)return 1;close(fd);close(reader);return 0;}
''')
        cls.binary = cls.base / 'discovery'
        result = subprocess.run([shutil.which('clang') or shutil.which('cc'), '-Wall', '-Wextra', '-Werror',
                                 '-Wno-unused-function', '-fsanitize=address,undefined', '-g',
                                 '-DFWUP_TEST_UID=geteuid()', '-DFWUP_MTD_TABLE="' + str(cls.table) + '"',
                                 '-DFWUP_DEVICE_PREFIX="' + str(cls.prefix) + '"',
                                 '-I' + str(SOURCE), '-I' + str(ROOT / 'trunk/user/shared/include'),
                                 str(harness), str(SOURCE / 'crc32.c'), '-o', str(cls.binary)],
                                capture_output=True, text=True)
        if result.returncode: raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls): cls.build.cleanup()

    def setUp(self):
        for path in self.base.glob('mtd*'): path.unlink()
        self.table.write_text('dev: size erasesize name\nmtd3: 00f30000 00010000 "firmware"\n')
        self.device = Path(str(self.prefix) + '3'); self.device.write_bytes(b'ordinary fixture')

    def run_discovery(self, **extra):
        env = dict(os.environ)
        for key in ('DISCOVER_REGULAR', 'DISCOVER_RW_MISMATCH', 'DISCOVER_RO_MISMATCH'): env.pop(key, None)
        result = subprocess.run([str(self.binary)], env={**env, **extra}, capture_output=True, text=True, timeout=5)
        self.assertNotIn('AddressSanitizer', result.stderr)
        self.assertNotIn('runtime error:', result.stderr)
        return result.returncode

    def test_canonical_and_capitalized_exact_label_choose_same_device(self):
        for label in ('firmware', 'Firmware', 'FIRMWARE'):
            with self.subTest(label=label):
                self.table.write_text('mtd3: 00f30000 00010000 "' + label + '"\n')
                self.assertEqual(self.run_discovery(), 0)

    def test_partial_unrelated_and_duplicate_labels_rejected(self):
        for table in ('mtd3: 00f30000 00010000 "firmware-backup"\n',
                      'mtd3: 00f30000 00010000 "Storage"\n',
                      'mtd3: 00f30000 00010000 "firmware"\nmtd4: 00f30000 00010000 "Firmware"\n'):
            with self.subTest(table=table):
                self.table.write_text(table); self.assertEqual(self.run_discovery(), 1)

    def test_proc_geometry_and_rw_info_must_match(self):
        self.assertEqual(self.run_discovery(DISCOVER_RW_MISMATCH='1'), 1)
        self.table.write_text('mtd3: 00f20000 00010000 "firmware"\n')
        self.assertEqual(self.run_discovery(), 1)

    def test_preopened_readonly_geometry_must_match_writer(self):
        self.assertEqual(self.run_discovery(DISCOVER_RO_MISMATCH='1'), 1)

    def test_regular_device_and_device_symlink_rejected(self):
        self.assertEqual(self.run_discovery(DISCOVER_REGULAR='1'), 1)
        self.device.unlink(); self.device.symlink_to(self.table)
        self.assertEqual(self.run_discovery(), 1)


class LegacyFirmwareWriterErrorTests(unittest.TestCase):
    """Compile actual legacy mtd_write and full main; all effects are inert."""
    @classmethod
    def setUpClass(cls):
        from test_httpd_regressions import function
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-legacy-writer-code-')
        cls.code = Path(cls.build.name).resolve()
        text = (SOURCE / 'mtd.c').read_text()
        code = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#define MAX_ARGS 8
#define JFFS2_EOF "\xde\xad\xc0\xde"
#define FWUP_UNKNOWN 21
enum mtd_image_format { MTD_IMAGE_FORMAT_UNKNOWN, MTD_IMAGE_FORMAT_TRX, MTD_IMAGE_FORMAT_SEAMA, MTD_IMAGE_FORMAT_WRGG03 };
static char *buf,*imagefile,*jffs2file,*jffs2dir="";
static enum mtd_image_format imageformat;
static int buflen,quiet,no_erase,jffs2_skip_bytes,erasesize=16;
static int read_calls,write_calls;
static int fault(const char*s){const char*p=getenv("LEGACY_FAULT");return p&&!strcmp(p,s);}
static void event(const char*s){int f=open(getenv("LEGACY_EVENTS"),O_WRONLY|O_CREAT|O_APPEND,0600);if(f>=0){write(f,s,strlen(s));write(f,"\n",1);close(f);}}
static int is_file(int fd,const char*key){struct stat a,b;const char*p=getenv(key);return p&&!fstat(fd,&a)&&!stat(p,&b)&&a.st_ino==b.st_ino&&a.st_dev==b.st_dev;}
static ssize_t test_read(int fd,void*p,size_t n){
 if(is_file(fd,"LEGACY_IMAGE")){
  read_calls++;
  if(fault("read-first")||(fault("read-partial")&&read_calls>1)||(fault("read-block")&&read_calls>1)){errno=EIO;return -1;}
  if(fault("read-eintr")&&read_calls==1){errno=EINTR;return -1;}
  if(fault("read-partial")&&n>7)n=7;
  if(fault("read-short")&&n>3)n=3;
 }return read(fd,p,n);
}
static ssize_t test_write(int fd,const void*p,size_t n){
 if(is_file(fd,"LEGACY_DEVICE")){
  event("write");write_calls++;
  if(fault("write")){errno=EIO;return -1;}
  if(fault("short-write")&&n)n--;
 }return write(fd,p,n);
}
static int test_close(int fd){int device=is_file(fd,"LEGACY_DEVICE"),r=close(fd);if(device){event("close");if(fault("close")){errno=EIO;return -1;}}return r;}
static int mtd_check_open(const char*mtd){(void)mtd;event("open");return open(getenv("LEGACY_DEVICE"),O_RDWR);}
static int mtd_check(const char*mtd){(void)mtd;if(!buf)buf=malloc(16);return buf!=NULL;}
static int mtd_block_is_bad(int fd,int offset){(void)fd;(void)offset;return 0;}
static int mtd_erase_block(int fd,int offset){(void)fd;(void)offset;event("erase");return 0;}
static void indicate_writing(const char*mtd){(void)mtd;}
static int mtd_replace_jffs2(const char*a,int b,int c,const char*d){(void)a;(void)b;(void)c;(void)d;abort();}
static void mtd_parse_jffs2data(const char*a,const char*b){(void)a;(void)b;abort();}
static int fixup(int fd,const char*n){(void)fd;(void)n;abort();}
static int fix3(const char*n,size_t a,size_t b){(void)n;(void)a;(void)b;abort();}
static int resetbc(const char*n){(void)n;abort();}
static int (*trx_fixup)(int,const char*)=fixup;
static int (*mtd_fixtrx)(const char*,size_t,size_t)=fix3;
static int (*mtd_fixseama)(const char*,size_t,size_t)=fix3;
static int (*mtd_fixwrgg)(const char*,size_t,size_t)=fix3;
static int (*mtd_resetbc)(const char*)=resetbc;
static int image_check(int fd,const char*device){(void)fd;(void)device;return 1;}
static int mtd_unlock(const char*n){(void)n;event("unlock");return 0;}
static int mtd_erase(const char*n){(void)n;abort();}
static int mtd_dump(const char*n,int a,int b){(void)n;(void)a;(void)b;abort();}
static int mtd_write_jffs2(const char*a,const char*b,const char*c){(void)a;(void)b;(void)c;abort();}
static int fwup_error(const char*m,int result){(void)m;return result;}
static int firmware_upgrade_write(const char*a,const char*b,const char*c){(void)a;(void)b;(void)c;abort();}
static void usage(void){exit(1);}
static void do_reboot(void){event("INERT-REBOOT");}
static void inert_sync(void){event("INERT-SYNC");}
#define read test_read
#define write test_write
#define close test_close
#define sync inert_sync
'''
        code += function(text, 'mtd_write') + '\n' + function(text, 'main')
        harness = cls.code / 'legacy.c'; harness.write_text(code)
        cls.binary = cls.code / 'legacy'
        result = subprocess.run([shutil.which('clang') or shutil.which('cc'), '-Wall', '-Wextra', '-Werror',
                                 '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-sign-compare',
                                 '-fsanitize=address,undefined', '-g', str(harness), '-o', str(cls.binary)],
                                capture_output=True, text=True)
        if result.returncode: raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls): cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='k2p-legacy-writer-case-')
        self.base = Path(self.temp.name).resolve()
        self.image = self.base / 'storage.bz2'; self.image.write_bytes(b'legacy synthetic payload bytes only!')
        self.device = self.base / 'ordinary-device'; self.device.write_bytes(b'\x00' * 512)
        self.log = self.base / 'events'

    def tearDown(self): self.temp.cleanup()

    def run_legacy(self, fault=None, reboot=False):
        env = dict(os.environ, LEGACY_IMAGE=str(self.image), LEGACY_DEVICE=str(self.device), LEGACY_EVENTS=str(self.log),
                   ASAN_OPTIONS='detect_leaks=0')
        if fault: env['LEGACY_FAULT'] = fault
        else: env.pop('LEGACY_FAULT', None)
        result = subprocess.run([str(self.binary), *(['-r'] if reboot else []), 'write', str(self.image), 'Storage'],
                                env=env, capture_output=True, text=True, timeout=5)
        self.assertNotIn('AddressSanitizer', result.stderr);self.assertNotIn('runtime error:', result.stderr)
        return result, self.log.read_text().splitlines() if self.log.exists() else []

    def test_permanent_read_error_does_not_pad_or_write_residual(self):
        for fault in ('read-first', 'read-partial'):
            with self.subTest(fault=fault):
                self.log.unlink(missing_ok=True)
                result, events = self.run_legacy(fault, reboot=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertNotIn('write', events);self.assertNotIn('erase', events);self.assertNotIn('INERT-REBOOT', events)
                self.assertEqual(self.device.read_bytes(), b'\x00' * 512)

    def test_read_error_after_one_block_is_failure_and_never_reboots(self):
        result, events = self.run_legacy('read-block', reboot=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(events.count('write'), 1); self.assertNotIn('INERT-REBOOT', events)

    def test_short_write_and_write_error_never_reboot(self):
        for fault in ('short-write', 'write'):
            with self.subTest(fault=fault):
                self.log.unlink(missing_ok=True)
                result, events = self.run_legacy(fault, reboot=True)
                self.assertEqual(result.returncode, 1, result.stderr);self.assertNotIn('INERT-REBOOT', events)

    def test_device_close_error_propagates_through_main_and_suppresses_reboot(self):
        result, events = self.run_legacy('close', reboot=True)
        self.assertEqual(result.returncode, 1, result.stderr);self.assertIn('close', events)
        self.assertNotIn('INERT-REBOOT', events)

    def test_normal_legacy_storage_write_and_inert_reboot_route_preserved(self):
        for fault in (None, 'read-short', 'read-eintr'):
            with self.subTest(fault=fault):
                self.log.unlink(missing_ok=True)
                result, events = self.run_legacy(fault, reboot=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = self.image.read_bytes();end = (len(expected) + 15) // 16 * 16
                self.assertEqual(self.device.read_bytes()[:end], expected + b'\xff' * (end - len(expected)))
                self.assertEqual(events.count('INERT-REBOOT'), 1)


if __name__ == '__main__': unittest.main()
