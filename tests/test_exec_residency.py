"""Test actual static ELF segment locking code with inert memory/MTD effects."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from mt7621_wdt_harness import function

ROOT=Path(__file__).resolve().parents[1]
HEADER=ROOT/'trunk/user/mtd_write/upgrade_write.h'

class ExecResidencyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='k2p-exec-lock-');cls.addClassCleanup(cls.tmp.cleanup);cls.dir=Path(cls.tmp.name)
  text=HEADER.read_text();read=function(text,'fwup_exec_read');lock=function(text,'fwup_lock_executable')
  source=r'''#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>
#ifdef __linux__
#include <sys/vfs.h>
#else
#include <sys/mount.h>
#endif
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#ifdef __APPLE__
#define SELFMAG 4
#define ELFMAG "\177ELF"
#define EI_CLASS 4
#define EI_DATA 5
#define EI_VERSION 6
#define ELFCLASS32 1
#define ELFDATA2LSB 1
#define EV_CURRENT 1
#define ET_EXEC 2
#define EM_MIPS 8
#define PT_LOAD 1
#define PT_DYNAMIC 2
#define PT_INTERP 3
#define PF_X 1
#define PF_W 2
#define PF_R 4
typedef struct { unsigned char e_ident[16]; uint16_t e_type,e_machine; uint32_t e_version,e_entry,e_phoff,e_shoff,e_flags; uint16_t e_ehsize,e_phentsize,e_phnum,e_shentsize,e_shnum,e_shstrndx; } Elf32_Ehdr;
typedef struct { uint32_t p_type,p_offset,p_vaddr,p_paddr,p_filesz,p_memsz,p_flags,p_align; } Elf32_Phdr;
#else
#include <elf.h>
#endif
#include <stdio.h>
static int locks=0,reads=0;
static int fault(const char *s){const char *x=getenv("FAULT");return x&&!strcmp(x,s);}
static int fake_open(void){if(fault("open")){errno=EIO;return -1;}return open(getenv("ELF_PATH"),O_RDONLY);}
static int fake_fs(int fd,struct statfs *fs){(void)fd;memset(fs,0,sizeof(*fs));if(fault("statfs"))return -1;fs->f_type=fault("wrongfs")?0:0x01021994UL;return 0;}
static ssize_t fake_read(int fd,void *p,size_t n,off_t offset){reads++;if(fault("eintr")&&reads==1){errno=EINTR;return -1;}if(fault("read-error")){errno=EIO;return -1;}if(fault("read-zero"))return 0;if(fault("read-short")&&n>3)n=3;return pread(fd,p,n,offset);}
static int fake_mlock(const void *p,size_t n){locks++;printf("%lx:%lu\\n",(unsigned long)(uintptr_t)p,(unsigned long)n);if(fault("lock-first")||(fault("lock-second")&&locks==2)){errno=ENOMEM;return -1;}return 0;}
static int fake_close(int fd){int r=close(fd);return fault("close")?-1:r;}
#define FWUP_OWNER ((uid_t)getuid())
#define FWUP_EXEC_OPEN fake_open
#define FWUP_EXEC_STATFS fake_fs
#define FWUP_EXEC_MLOCK fake_mlock
#define FWUP_EXEC_CLOSE fake_close
#define pread fake_read
''' + '\n'+read+'\n'+lock+'\nint main(void){return fwup_lock_executable()==0?0:1;}\n'
  cls.src=cls.dir/'probe.c';cls.src.write_text(source)
  compilers=[('gcc16',shutil.which('gcc-16'),[]),('clang',shutil.which('clang'),[])]
  if os.environ.get('K2P_EXEC_RESIDENCY_CC'):
   compilers.append(('mips',os.environ['K2P_EXEC_RESIDENCY_CC'],[shutil.which('qemu-mipsel')]))
  cls.compilers=compilers;cls.runners=[]
  for label,cc,runner in compilers:
   if not cc or not all(runner):raise RuntimeError('required compiler/runner missing')
   exe=cls.dir/label
   flags=['-static'] if label=='mips' else (['-fsanitize=address,undefined','-fno-sanitize-recover=all'] if label=='clang' else [])
   p=subprocess.run([cc,'-std=gnu99','-O2','-Wall','-Wextra','-Werror',*flags,str(cls.src),'-o',str(exe)],capture_output=True,text=True)
   if p.returncode:raise RuntimeError(p.stderr)
   cls.runners.append([*runner,str(exe)])
   if label=='mips' and os.environ.get('K2P_EXEC_RESIDENCY_DIR'):
    out=Path(os.environ['K2P_EXEC_RESIDENCY_DIR']);out.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(cls.src,out/'target-exec-residency.c');shutil.copyfile(exe,out/'target-exec-residency.elf')
    print('EXEC_RESIDENCY_TARGET=mipsel-linux-uclibc;RUNNER=qemu-mipsel',flush=True)
 def image(self,**kw):
  ident=b'\x7fELF'+bytes([1,1,1])+bytes(9)
  eh=struct.pack('<16sHHIIIIIHHHHHH',ident,kw.get('type',2),kw.get('machine',8),1,0x400160,kw.get('phoff',52),0,0,52,32,kw.get('phnum',2),0,0,0)
  a=struct.pack('<IIIIIIII',1,0,0x400000,0,512,4096,kw.get('first_flags',5),4096)
  b=struct.pack('<IIIIIIII',kw.get('second_type',1),0,kw.get('second_addr',0x500000),0,512,kw.get('second_mem',8192),kw.get('second_flags',6),4096)
  return (eh+a+b).ljust(512,b'\0')
 def run_probe(self,runner,image,fault='',mode=0o700):
  p=self.dir/'writer-image';p.write_bytes(image);p.chmod(mode)
  return subprocess.run(runner,env={**os.environ,'ELF_PATH':str(p),'FAULT':fault},capture_output=True,text=True,timeout=10)
 def test_valid_segments_and_transient_reads(self):
  for runner in self.runners:
   for fault in ('','eintr','read-short'):
    with self.subTest(runner=runner,fault=fault):
     p=self.run_probe(runner,self.image(),fault);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.count('400000:4096'),1);self.assertEqual(p.stdout.count('500000:8192'),1)
 def test_invalid_segments_and_failure_are_rejected(self):
  cases=[(self.image(),'open',0o700),(self.image(),'statfs',0o700),(self.image(),'wrongfs',0o700),(self.image(),'read-error',0o700),(self.image(),'read-zero',0o700),(self.image(),'lock-first',0o700),(self.image(),'lock-second',0o700),(self.image(),'close',0o700),(self.image(),'',0o755),(self.image(machine=3),'',0o700),(self.image(type=3),'',0o700),(self.image(phoff=0),'',0o700),(self.image(phoff=500),'',0o700),(self.image()+bytes(1024*1024),'',0o700),(self.image(phnum=65),'',0o700),(self.image(first_flags=7),'',0o700),(self.image(second_type=3),'',0o700),(self.image(second_flags=4),'',0o700),(self.image(second_addr=0xfffff000,second_mem=8192),'',0o700),(self.image(second_mem=0x500000),'',0o700)]
  for runner in self.runners:
   for i,(raw,fault,mode) in enumerate(cases):
    with self.subTest(runner=runner,case=i):self.assertEqual(self.run_probe(runner,raw,fault,mode).returncode,1)
 def test_missing_or_ignored_segment_lock_controls_are_detected(self):
  text=self.src.read_text()
  original='if (FWUP_EXEC_MLOCK((const void *)(uintptr_t)ph.p_vaddr, ph.p_memsz)) goto out;'
  self.assertEqual(text.count(original),1)
  variants=(('missing','if (0 && FWUP_EXEC_MLOCK((const void *)(uintptr_t)ph.p_vaddr, ph.p_memsz)) goto out;'),('ignored','(void)FWUP_EXEC_MLOCK((const void *)(uintptr_t)ph.p_vaddr, ph.p_memsz);'))
  for label,cc,runner in self.compilers:
   for name,replacement in variants:
    with self.subTest(compiler=label,variant=name):
     src=self.dir/(label+'-'+name+'.c');exe=self.dir/(label+'-'+name);src.write_text(text.replace(original,replacement))
     flags=['-static'] if label=='mips' else (['-fsanitize=address,undefined','-fno-sanitize-recover=all'] if label=='clang' else [])
     result=subprocess.run([cc,'-std=gnu99','-O2','-Wall','-Wextra','-Werror',*flags,str(src),'-o',str(exe)],capture_output=True,text=True)
     self.assertEqual(result.returncode,0,result.stderr)
     result=self.run_probe([*runner,str(exe)],self.image(),'lock-first' if name=='ignored' else '')
     self.assertEqual(result.returncode,0,result.stderr)
     if name=='missing':self.assertNotIn('400000:4096',result.stdout)
     else:self.assertIn('500000:8192',result.stdout)
if __name__=='__main__':unittest.main()
