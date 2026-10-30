#!/usr/bin/env python3
"""Real bounded runtime reader/callers; no daemon, listener, MTD or device.

The reader is compiled under ASan/UBSan and strict GCC. A private full dnsmasq
--test binary exercises resolv-domain startup. Callback harnesses copy the
actual production bodies; only live server-table/network actions are inert.
Fault switches exist exclusively in the generated test translation unit.

Upstream/server/domain/dynamic-DHCP inputs: 2 MiB, 16 KiB/line, 65536 lines.
Hosts explicitly opt into 16 MiB/262144 lines. The five-second monotonic read
budget is cooperative between syscalls; it cannot bound a blocked kernel/FS.
Regular symlink/hardlink aliases remain supported. Invalid input is rejected
before server-table changes; existing DHCP clear-before-reload semantics and
valid empty/syntactically invalid runtime-file behavior remain unchanged.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'trunk/user/dnsmasq/dnsmasq-2.93'


def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        if text[end] == '{': depth += 1
        elif text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


class DNSRuntimeFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-dns-runtime-code-')
        cls.directory = Path(cls.build.name).resolve()
        src = SOURCE/'src'
        header = (src/'runtime_file.h').read_text()
        reader = (src/'runtime_file.c').read_text()
        option = (src/'option.c').read_text()
        network = (src/'network.c').read_text()
        common = r'''
#include "dnsmasq.h"
#include "runtime_file.h"
#include <stdarg.h>
#undef free
struct daemon *daemon;
static int calls, marked, parsed, cleaned, checked, added, logs, source_fd = -1;
static const char *fault;
static const char *current_path;
static int active_fault(const char *name) { return fault && !strcmp(fault,name); }
static ssize_t fault_pread(int fd,void *p,size_t n,off_t offset) {
  ssize_t result;
  source_fd=fd;
  calls++;
  if(active_fault("read")){errno=EIO;return -1;}
  if(active_fault("interrupt")){errno=EINTR;return -1;}
  if(active_fault("short")&&n>1)n=1;
  result=pread(fd,p,n,offset);
  if(calls==1 && active_fault("grow")) {
    int w=open(current_path,O_WRONLY|O_APPEND);if(w<0)_exit(90);
    if(write(w,"x",1)!=1||close(w))_exit(91);
  }
  if(calls==1 && active_fault("replace")) {
    char other[4096];int w;
    snprintf(other,sizeof(other),"%s.new",current_path);
    w=open(other,O_WRONLY|O_CREAT|O_EXCL,0600);if(w<0)_exit(92);
    if(write(w,"x",1)!=1||close(w)||rename(other,current_path))_exit(93);
  }
  if(calls==1 && active_fault("rewrite")) {
    int w=open(current_path,O_WRONLY);if(w<0)_exit(94);
    if(write(w,"!",1)!=1||close(w))_exit(95);
  }
  if(calls==1 && active_fault("mode")) {
    struct stat st;if(fstat(fd,&st)||chmod(current_path,(st.st_mode&0777)^0200))_exit(96);
  }
  return result;
}
static int fault_clock(clockid_t clock,struct timespec *stamp) {
  static int ticks;
  if(active_fault("clock")){errno=EIO;return -1;}
  if(active_fault("deadline")){stamp->tv_sec=ticks++ ? 6 : 0;stamp->tv_nsec=0;return 0;}
  return clock_gettime(clock,stamp);
}
static int fault_open(const char *path,int flags) {
  if(active_fault("open-fifo")) {
    if(unlink(path)||mkfifo(path,0600))_exit(89);
  }
  return open(path,flags);
}
static int fault_close(int fd) {
  int result=close(fd);
  if(fd==source_fd&&active_fault("close")){errno=EIO;return -1;}
  return result;
}
static void *fault_malloc(size_t n) {
  if(active_fault("allocation")){errno=ENOMEM;return NULL;}return malloc(n);
}
static FILE *fault_fmemopen(void *p,size_t n,const char *m) {
  if(active_fault("stream")){errno=EMFILE;return NULL;}return fmemopen(p,n,m);
}
#define clock_gettime fault_clock
#define open fault_open
#define pread fault_pread
#define close fault_close
#define malloc fault_malloc
#define fmemopen fault_fmemopen
'''
        suffix = r'''
#undef clock_gettime
#undef open
#undef pread
#undef close
#undef malloc
#undef fmemopen
int main(int argc,char **argv) {
  struct dns_runtime_file snapshot;const char *error;int c;size_t bytes=0;
  if(argc<3)return 98;
  fault=getenv("DNS_READER_FAULT");current_path=argv[2];
  if(!strcmp(argv[1],"descriptor")) {
    int fd=open(current_path,O_RDWR|O_APPEND),value;off_t position;
    char moved[4096];
    if(fd<0)return 85;
    position=lseek(fd,0,SEEK_END);
    snprintf(moved,sizeof(moved),"%s.moved",current_path);
    if(rename(current_path,moved))return 86;
    value=open(current_path,O_WRONLY|O_CREAT|O_EXCL,0600);
    if(value<0||write(value,"new",3)!=3||close(value))return 87;
    if(!dns_runtime_file_read_fd_limit(&snapshot,fd,DNS_RUNTIME_FILE_BYTES,
                                       DNS_RUNTIME_FILE_LINES,&error)) {
      fprintf(stderr,"%s\n",error);close(fd);return 1;
    }
    while((c=fgetc(snapshot.stream))!=EOF)bytes++;
    dns_runtime_file_close(&snapshot);
    if(lseek(fd,0,SEEK_CUR)!=position||fcntl(fd,F_GETFD)<0)return 88;
    close(fd);printf("descriptor-bytes=%zu offset-preserved=1 fd-open=1\n",bytes);return 0;
  }
  if(!strcmp(argv[1],"reader")||!strcmp(argv[1],"hosts")) {
    int ok=!strcmp(argv[1],"hosts") ?
      dns_runtime_file_open_limit(&snapshot,current_path,DNS_RUNTIME_HOSTS_BYTES,
                                  DNS_RUNTIME_HOSTS_LINES,&error) :
      dns_runtime_file_open(&snapshot,current_path,&error);
    if(!ok) {
      fprintf(stderr,"%s\n",error);return 1;
    }
    while((c=fgetc(snapshot.stream))!=EOF)bytes++;
    dns_runtime_file_close(&snapshot);
    printf("bytes=%zu reads=%d\n",bytes,calls);return 0;
  }
  return callback(argv[1],argv[2]);
}
'''
        callback = r'''
#undef clock_gettime
#undef open
#undef pread
#undef close
#undef malloc
#undef fmemopen
static void stub_log(int priority,const char *fmt,...) {
  va_list ap;(void)priority;logs++;
  va_start(ap,fmt);vfprintf(stderr,fmt,ap);va_end(ap);fputc('\n',stderr);
}
static void stub_mark(int flag){(void)flag;marked++;}
static void stub_parse(char *file,FILE *stream,int hard,int script) {
  int c;(void)file;(void)hard;(void)script;
  while((c=fgetc(stream))!=EOF)if(c=='\n')parsed++;
}
static void stub_cleanup(void){cleaned++;}
static void stub_check(int n){(void)n;checked++;}
static int stub_add(int flags,union mysockaddr *a,union mysockaddr *s,
                    const char *i,const char *d,union all_addr *l) {
  (void)flags;(void)a;(void)s;(void)i;(void)d;(void)l;added++;return 1;
}
static int fixture_line(FILE *f,char **line,size_t *capacity) {
  ssize_t n=getline(line,capacity,f);
  if(n<0){free(*line);*line=NULL;*capacity=0;return 0;}return 1;
}
#define my_syslog stub_log
#define mark_servers stub_mark
#define read_file stub_parse
#define cleanup_servers stub_cleanup
#define check_servers stub_check
#define add_update_server stub_add
#define get_line_alloc fixture_line
#define LOPT_REV_SERV 332
'''
        callback += function(option,'void read_servers_file(void)')+'\n'
        callback += function(network,'int reload_servers(char *fname)')+'\n'
        callback += r'''
static int callback(char *role,char *path) {
  static struct daemon state;
  int result=0;
  daemon=&state;daemon->servers_file=path;
  if(!strcmp(role,"sequence")) {
    int fd;
    read_servers_file();
    if(marked!=1||parsed!=1||cleaned!=1||checked!=1)return 81;
    if(unlink(path)||mkfifo(path,0600))return 82;
    read_servers_file();
    if(marked!=1||parsed!=1||cleaned!=1||checked!=1||logs!=1)return 83;
    if(unlink(path))return 84;
    fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);
    if(fd<0||write(fd,"server=192.0.2.2\n",17)!=17||close(fd))return 85;
    read_servers_file();
  }
  else if(!strcmp(role,"servers"))read_servers_file();
  else if(!strcmp(role,"resolv"))result=reload_servers(path);
  else return 97;
  printf("marked=%d parsed=%d cleaned=%d checked=%d added=%d logs=%d result=%d\n",
         marked,parsed,cleaned,checked,added,logs,result);
  return 0;
}
'''
        harness = cls.directory/'reader.c'
        harness.write_text(common+reader.replace('#include "dnsmasq.h"','')+
                           callback+suffix)
        cls.binaries=[]
        compilers=[('clang',['-fsanitize=address,undefined'])]
        gcc=shutil.which('gcc-16') or shutil.which('gcc')
        if gcc: compilers.append((gcc,[]))
        for compiler,flags in compilers:
            binary=cls.directory/('reader-'+Path(compiler).name)
            result=subprocess.run([compiler,'-Wall','-Wextra','-Werror','-O1','-g',
                            *flags,'-I'+str(src),str(harness),'-o',str(binary)],
                           capture_output=True,text=True)
            if result.returncode: raise AssertionError(result.stdout+result.stderr)
            cls.binaries.append(binary)
        tree=cls.directory/'dnsmasq'
        shutil.copytree(SOURCE,tree,ignore=shutil.ignore_patterns('*.o','dnsmasq','.copts_*'))
        result=subprocess.run(['make','-j4','CC=clang',
            'COPTS=-DNO_DHCP6 -DNO_TFTP -DNO_INOTIFY -DNO_AUTH -DNO_LOOP',
            'CFLAGS=-O1 -g -Wall -Wextra -fsanitize=address,undefined',
            'LDFLAGS=-fsanitize=address,undefined'],cwd=tree,text=True,capture_output=True)
        if result.returncode: raise AssertionError(result.stdout+result.stderr)
        cls.parser=cls.directory/'dnsmasq-test'
        shutil.copy2(tree/'src/dnsmasq',cls.parser)
        main=tree/'src/dnsmasq.c'
        original=main.read_text()
        stop='  read_opts(argc, argv, compile_opts);'
        if original.count(stop)!=1:raise AssertionError('actual parser stop point changed')
        main.write_text(original.replace(stop,stop+r'''
  {
    struct dhcp_config *entry;struct dhcp_opt *option;int hosts=0,opts=0;
    reread_dhcp();
    for(entry=daemon->dhcp_conf;entry;entry=entry->next)hosts++;
    for(option=daemon->dhcp_opts;option;option=option->next)opts++;
    printf("DYNAMIC_HOSTS=%d DYNAMIC_OPTS=%d\n",hosts,opts);
    return 0;
  }
'''))
        (tree/'src/dnsmasq.o').unlink()
        (tree/'src/dnsmasq').unlink()
        result=subprocess.run(['make','-j4','CC=clang',
            'COPTS=-DNO_DHCP6 -DNO_TFTP -DNO_INOTIFY -DNO_AUTH -DNO_LOOP',
            'CFLAGS=-O1 -g -Wall -Wextra -fsanitize=address,undefined',
            'LDFLAGS=-fsanitize=address,undefined'],cwd=tree,text=True,capture_output=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
        cls.dynamic_parser=tree/'src/dnsmasq'
        if b'DYNAMIC_HOSTS=' not in cls.dynamic_parser.read_bytes():
            raise AssertionError('no-daemon caller stop marker absent')

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='k2p-dns-runtime-fixture-')
        self.base=Path(self.temp.name).resolve()
        self.path=self.base/'runtime.conf'
        self.path.write_text('server=192.0.2.1\n')
        self.env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'}

    def tearDown(self):
        self.temp.cleanup()

    def run_case(self,role='reader',fault=None,path=None):
        results=[]
        for binary in self.binaries:
            env={**self.env,'DNS_READER_FAULT':fault or ''}
            result=subprocess.run([str(binary),role,str(path or self.path)],
                                  text=True,capture_output=True,env=env,timeout=2)
            self.assertNotIn('AddressSanitizer',result.stderr)
            self.assertNotIn('runtime error:',result.stderr)
            results.append(result)
        return results

    def assert_rejected(self,reason,path=None,fault=None):
        for result in self.run_case(path=path,fault=fault):
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertIn(reason,result.stderr)

    def test_regular_empty_final_line_and_short_reads(self):
        for payload in (b'',b'server=192.0.2.1',b'server=192.0.2.1\n'):
            self.path.write_bytes(payload)
            for result in self.run_case(fault='short'):
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('bytes='+str(max(1,len(payload))),result.stdout)

    def test_fifo_directory_device_socket_and_symlink_fifo_rejected(self):
        fifo=self.base/'fifo';os.mkfifo(fifo)
        alias=self.base/'alias';alias.symlink_to(fifo)
        import socket
        sock=socket.socket(socket.AF_UNIX);sock.bind(str(self.base/'socket'))
        try:
            for path in (fifo,alias,self.base,Path('/dev/null'),self.base/'socket'):
                self.assert_rejected('not a regular file',path=path)
        finally: sock.close()

    def test_regular_symlink_and_hardlink_supported(self):
        alias=self.base/'symlink';alias.symlink_to(self.path)
        hard=self.base/'hard';os.link(self.path,hard)
        for path in (alias,hard):
            for result in self.run_case(path=path):
                self.assertEqual(result.returncode,0,result.stderr)

    def test_exact_byte_limit_and_one_byte_over(self):
        self.path.write_bytes(b'#'+b'x'*16382+b'\n')
        self.path.write_bytes(self.path.read_bytes()*128)
        self.assertEqual(self.path.stat().st_size,2*1024*1024)
        for result in self.run_case(): self.assertEqual(result.returncode,0,result.stderr)
        with self.path.open('ab') as f:f.write(b'\n')
        self.assert_rejected('2 MiB')

    def test_line_length_and_count_limits_and_nul(self):
        for payload,reason in ((b'x'*16385,'16 KiB'),(b'\n'*65537,'65536'),
                               (b'\n'*65536+b'x','65536'),(b'server=192.0.2.1\x00','NUL')):
            self.path.write_bytes(payload);self.assert_rejected(reason)
        for payload in (b'x'*16384,b'\n'*65536):
            self.path.write_bytes(payload)
            for result in self.run_case():self.assertEqual(result.returncode,0,result.stderr)

    def test_read_close_alloc_stream_and_signal_storm_fail_closed(self):
        for fault in ('read','close','allocation','stream','interrupt','clock','deadline'):
            self.assert_rejected('runtime DNS input',fault=fault)

    def test_open_race_to_fifo_rejected_without_blocking(self):
        for binary in self.binaries:
            if self.path.exists():self.path.unlink()
            self.path.write_text('server=192.0.2.1\n')
            result=subprocess.run([str(binary),'reader',str(self.path)],
                env={**self.env,'DNS_READER_FAULT':'open-fifo'},capture_output=True,text=True,timeout=2)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertIn('runtime DNS input is not a regular file',result.stderr)

    def test_descriptor_snapshot_binds_writer_inode_and_preserves_offset(self):
        for binary in self.binaries:
            self.path.write_text('server=192.0.2.1\n')
            moved=Path(str(self.path)+'.moved')
            if moved.exists():moved.unlink()
            result=subprocess.run([str(binary),'descriptor',str(self.path)],env=self.env,
                                  capture_output=True,text=True,timeout=2)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('descriptor-bytes=17 offset-preserved=1 fd-open=1',result.stdout)

    def test_hosts_uses_explicit_larger_budget(self):
        self.path.write_bytes((b'#'+b'x'*1022+b'\n')*3072)
        self.assert_rejected('2 MiB')
        for result in self.run_case(role='hosts'):
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('bytes=3145728',result.stdout)

    def test_growth_replacement_rewrite_and_mode_races_rejected(self):
        # Each backend receives fresh input: one must not inherit a prior fault.
        for fault in ('grow','replace','rewrite','mode'):
            for binary in self.binaries:
                self.path.chmod(0o600);self.path.write_text('server=192.0.2.1\n')
                result=subprocess.run([str(binary),'reader',str(self.path)],
                    env={**self.env,'DNS_READER_FAULT':fault},capture_output=True,text=True,timeout=2)
                self.assertEqual(result.returncode,1,(fault,result.stdout,result.stderr))
                self.assertIn('runtime DNS input',result.stderr)

    def test_runtime_failures_preserve_existing_server_tables(self):
        fifo=self.base/'fifo';os.mkfifo(fifo)
        for role in ('servers','resolv'):
            for result in self.run_case(role=role,path=fifo):
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('marked=0 parsed=0 cleaned=0 checked=0 added=0 logs=1',result.stdout)
            self.path.write_bytes(b'x'*16385)
            for result in self.run_case(role=role):
                self.assertIn('marked=0 parsed=0 cleaned=0 checked=0 added=0 logs=1',result.stdout)

    def test_same_process_reload_recovers_after_fifo_without_destroying_old_set(self):
        for binary in self.binaries:
            self.path.write_text('server=192.0.2.1\n')
            result=subprocess.run([str(binary),'sequence',str(self.path)],
                env=self.env,capture_output=True,text=True,timeout=2)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('marked=2 parsed=2 cleaned=2 checked=2 added=0 logs=1',result.stdout)

    def test_runtime_regular_reload_and_atomic_replacement(self):
        for role,payload,expected in (
            ('servers','server=192.0.2.1\n','marked=1 parsed=1 cleaned=1 checked=1'),
            ('resolv','nameserver 192.0.2.1\n','marked=1 parsed=0 cleaned=1 checked=0 added=1')):
            self.path.write_text(payload)
            for result in self.run_case(role=role):self.assertIn(expected,result.stdout)
            replacement=self.base/'replacement';replacement.write_text(payload.replace('.1','.2'))
            replacement.replace(self.path)
            for result in self.run_case(role=role):self.assertIn(expected,result.stdout)

    def test_actual_dynamic_dhcp_file_callbacks_reject_fifo_and_limits(self):
        config=self.base/'dhcp.conf'
        for option,payload,expected in (
            ('dhcp-hostsfile','00:11:22:33:44:55,192.0.2.50,fixture\n','DYNAMIC_HOSTS=1 DYNAMIC_OPTS=0'),
            ('dhcp-optsfile','option:router,192.0.2.1\n','DYNAMIC_HOSTS=0 DYNAMIC_OPTS=1')):
            config.write_text('port=0\nno-hosts\nno-resolv\n'+option+'='+str(self.path)+'\n')
            for content in (payload.encode(),b'x'*16385,b'\n'*65537,None):
                if self.path.exists():self.path.unlink()
                if content is None:os.mkfifo(self.path)
                else:self.path.write_bytes(content)
                result=subprocess.run([str(self.dynamic_parser),'-C',str(config)],
                    env=self.env,capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertNotIn('AddressSanitizer',result.stderr)
                self.assertNotIn('runtime error:',result.stderr)
                self.assertIn(expected if content==payload.encode() else
                              'DYNAMIC_HOSTS=0 DYNAMIC_OPTS=0',result.stdout)
        if self.path.exists():self.path.unlink()

    def test_resolv_domain_real_startup_parser_regular_and_fifo(self):
        config=self.base/'dnsmasq.conf'
        config.write_text('port=0\nno-hosts\nresolv-file='+str(self.path)+'\ndomain=#\n')
        self.path.write_text('search fixture.example\n')
        result=subprocess.run([str(self.parser),'--test','-C',str(config)],
                              env=self.env,capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr)
        self.path.unlink();os.mkfifo(self.path)
        result=subprocess.run([str(self.parser),'--test','-C',str(config)],
                              env=self.env,capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,3,result.stderr)
        self.assertIn('runtime DNS input is not a regular file',result.stderr)


if __name__ == '__main__':
    unittest.main()
