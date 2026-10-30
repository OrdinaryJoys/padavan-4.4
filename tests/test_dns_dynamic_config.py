#!/usr/bin/env python3
"""Real dnsmasq parser and conf-script regressions with harmless local fixtures.

The production binary is used for --test. A second copy changes only main's
statement immediately after read_opts to return, exercising ordinary startup
parsing without creating a listener. Reduced compile-time deadlines keep host
regressions quick; production uses 10s/script and 30s/process.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import resource
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'trunk/user/dnsmasq/dnsmasq-2.93'


class DNSDynamicConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-dns-dynamic-code-')
        cls.build_root = Path(cls.build.name).resolve()
        tree = cls.build_root/'source'
        shutil.copytree(SOURCE, tree, ignore=shutil.ignore_patterns(
            '*.o', 'dnsmasq', 'dnsmasq_baseline', '.copts_*'))
        options = ('-DNO_DHCP -DNO_DHCP6 -DNO_TFTP -DNO_INOTIFY -DNO_AUTH '
                   '-DNO_LOOP -DCONF_SCRIPT_TIMEOUT_MS=800 -DCONF_SCRIPT_TOTAL_MS=2400')
        result = subprocess.run(['make', '-j4', 'CC=clang', 'COPTS='+options,
                                 'CFLAGS=-O1 -g -Wall -Wextra -fsanitize=address,undefined',
                                 'LDFLAGS=-fsanitize=address,undefined'], cwd=tree,
                                text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stdout+result.stderr)
        cls.binary = cls.build_root/'dnsmasq-test'
        shutil.copy2(tree/'src/dnsmasq', cls.binary)
        main = tree/'src/dnsmasq.c'
        text = main.read_text()
        needle = '  read_opts(argc, argv, compile_opts);'
        if text.count(needle) != 1:
            raise AssertionError('ordinary startup parser stop point changed')
        text = text.replace(needle, needle+'\n  printf("PARSED_CACHE=%d\\n", daemon->cachesize);\n  return 0;')
        main.write_text(text)
        # Some external workspaces have one-second timestamp resolution.
        # Force a new object; never accidentally execute an ordinary daemon.
        (tree/'src/dnsmasq.o').unlink()
        (tree/'src/dnsmasq').unlink()
        result = subprocess.run(['make', '-j4', 'CC=clang', 'COPTS='+options,
                                 'CFLAGS=-O1 -g -Wall -Wextra -fsanitize=address,undefined',
                                 'LDFLAGS=-fsanitize=address,undefined'], cwd=tree,
                                text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stdout+result.stderr)
        cls.parse_binary = cls.build_root/'dnsmasq-startup-parser'
        shutil.copy2(tree/'src/dnsmasq', cls.parse_binary)
        if b'PARSED_CACHE=%d' not in cls.parse_binary.read_bytes():
            raise AssertionError('parse-only stop marker absent from compiled binary')
        resolver = cls.build_root/'resolver.c'
        resolver.write_text(r'''
#include <netdb.h>
#include <unistd.h>
int getaddrinfo(const char *name,const char *service,const struct addrinfo *hints,struct addrinfo **result) {
  (void)name;(void)service;(void)hints;(void)result;
  write(2,"RESOLVER_STUB_CALLED\n",21);return EAI_NONAME;
}
''')
        resolver_object = cls.build_root/'resolver.o'
        subprocess.run(['clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                        '-c',str(resolver),'-o',str(resolver_object)],check=True,capture_output=True)
        cls.resolver_binary = cls.build_root/'dnsmasq-resolver-hook'
        subprocess.run(['clang','-fsanitize=address,undefined','-o',str(cls.resolver_binary),
                        *map(str,sorted((tree/'src').glob('*.o'))),str(resolver_object)],
                       check=True,capture_output=True)
        # Compile the actual collector again with only public, compile-time
        # failure wrappers. No production runtime fault switch is introduced.
        harness = cls.build_root/'collector.c'
        harness.write_text(r'''
#define _POSIX_C_SOURCE 200809L
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <poll.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
static int fault(const char *s) { const char *f=getenv("COLLECTOR_FAULT");return f&&!strcmp(f,s); }
static pid_t test_fork(void) { if(fault("fork")){errno=EAGAIN;return -1;}return fork(); }
static int test_pipe(int p[2]) { if(fault("pipe")){errno=EMFILE;return -1;}return pipe(p); }
static int test_fcntl(int fd,int op,...) {
  if(op==F_GETFL)return fcntl(fd,op);
  va_list ap;int arg;va_start(ap,op);arg=va_arg(ap,int);va_end(ap);
  if(fault("cloexec")&&op==F_SETFD){errno=EIO;return -1;}
  return fcntl(fd,op,arg);
}
static void *test_realloc(void *p,size_t n) {if(fault("allocation")){errno=ENOMEM;return NULL;}return realloc(p,n);}
static FILE *test_fmemopen(void *p,size_t n,const char *m) {if(fault("stream")){errno=EMFILE;return NULL;}return fmemopen(p,n,m);}
static ssize_t test_read(int fd,void *p,size_t n) {if(fault("read")){errno=EIO;return -1;}return read(fd,p,n);}
static int test_poll(struct pollfd *p,nfds_t n,int t) {if(fault("poll")&&n){errno=EIO;return -1;}return poll(p,n,t);}
static int test_clock(clockid_t id,struct timespec *t) {if(fault("clock")){errno=EIO;return -1;}return clock_gettime(id,t);}
#define fork test_fork
#define pipe test_pipe
#define fcntl test_fcntl
#define realloc test_realloc
#define fmemopen test_fmemopen
#define read test_read
#define poll test_poll
#define clock_gettime test_clock
#include "dynamic_conf.c"
int main(int argc,char **argv) {
  struct conf_script_budget b={0};const char *error;FILE *f;int c,status;
  if(argc!=2)return 99;
  if(fault("calls"))b.calls=CONF_SCRIPT_MAX_CALLS;
  if(fault("depth"))b.depth=CONF_SCRIPT_MAX_DEPTH;
  f=conf_script_open(argv[1],&b,&error);
  if(!f){fprintf(stderr,"%s\n",error);return 1;}
  if(fault("closed-stdio")) {
    char line[64];if(!fgets(line,sizeof(line),f)||strcmp(line,"cache-size=123\n"))return 97;
  }
  while((c=fgetc(f))!=EOF)putchar(c);
  conf_script_close(f,&b);
  if(b.depth||waitpid(-1,&status,WNOHANG)!=-1||errno!=ECHILD)return 98;
  return 0;
}
'''.replace('#include <errno.h>', '#include <errno.h>\n#include <stdarg.h>'))
        cls.collector = cls.build_root/'collector'
        subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                        '-fsanitize=address,undefined', '-DCONF_SCRIPT_TIMEOUT_MS=800',
                        '-DCONF_SCRIPT_TOTAL_MS=2400', '-I'+str(SOURCE/'src'),
                        str(harness), '-o', str(cls.collector)], check=True,
                       capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='k2p-dns-dynamic-')
        self.base = Path(self.temp.name).resolve()
        self.config = self.base/'dns.conf'
        self.generator = self.base/'generate.sh'
        self.env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'}

    def tearDown(self):
        self.temp.cleanup()

    def script(self, body):
        self.generator.write_text('#!/bin/sh\n'+body+'\n')
        self.generator.chmod(0o700)
        return str(self.generator)

    def run_parser(self, command, startup=False, extra='', fsize=None):
        self.config.write_text('port=0\nno-resolv\nconf-script='+command+'\n'+extra)
        argv = [str(self.parse_binary if startup else self.binary)]
        if not startup:
            argv.append('--test')
        argv += ['-C', str(self.config)]
        def limits():
            if fsize is not None:
                resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        start = time.monotonic()
        result = subprocess.run(argv, env=self.env, text=True, capture_output=True,
                                timeout=5, preexec_fn=limits if fsize is not None else None)
        self.assertNotIn('AddressSanitizer', result.stderr)
        self.assertNotIn('runtime error:', result.stderr)
        self.assertLess(time.monotonic()-start, 4)
        return result

    def assert_rejected(self, command, reason, **kwargs):
        result = self.run_parser(command, **kwargs)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(reason, result.stderr)
        return result

    def test_normal_generator_is_accepted_in_test_and_ordinary_startup_parser(self):
        command = self.script("printf 'cache-size=123\\n'")
        self.assertEqual(self.run_parser(command).returncode, 0)
        result = self.run_parser(command, startup=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PARSED_CACHE=123', result.stdout)

    def test_shell_command_and_last_line_without_newline_are_compatible(self):
        result = self.run_parser("printf 'cache-size=124'", startup=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PARSED_CACHE=124', result.stdout)

    def test_empty_output_is_accepted(self):
        self.assertEqual(self.run_parser('true').returncode, 0)

    def test_stderr_is_drained_without_becoming_configuration(self):
        result = self.run_parser("printf diagnostic >&2; printf 'cache-size=125\\n'", startup=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PARSED_CACHE=125', result.stdout)

    def test_nonzero_exit_output_is_not_applied_or_parsed(self):
        result = self.assert_rejected("printf 'NotAValidOption\\n'; exit 7", 'nonzero status')
        self.assertNotIn('bad option', result.stderr)

    def test_missing_command_is_rejected(self):
        self.assert_rejected('/nonexistent/public-fixture-command', 'nonzero status')

    def test_closed_stdout_and_stderr_do_not_hide_a_hung_child(self):
        self.assert_rejected('exec 1>&- 2>&-; sleep 30', 'time budget', startup=True)

    def test_eof_waits_for_child_exit(self):
        self.assert_rejected("printf 'cache-size=123\\n'; exec 1>&- 2>&-; sleep 30", 'time budget')

    def test_child_exit_does_not_hide_descendant_held_pipes(self):
        pidfile = self.base/'descendant.pid'
        self.assert_rejected('sleep 30 & echo $! > '+str(pidfile)+'; exit 0', 'time budget')
        pid = int(pidfile.read_text())
        state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], text=True,
                               capture_output=True).stdout.strip()
        self.assertTrue(not state or state.startswith('Z'), state)

    def test_term_ignoring_group_is_killed_and_leader_is_reaped(self):
        command = self.script("trap '' TERM; exec 1>&- 2>&-; while :; do sleep 1; done")
        self.assert_rejected(command, 'time budget')
        result = subprocess.run([str(self.collector), command], env=self.env,
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_stdout_flood_is_rejected(self):
        self.assert_rejected('yes "# harmless comment"', 'output budget')

    def test_stderr_flood_is_rejected(self):
        self.assert_rejected('yes diagnostic >&2', 'diagnostic output limit')

    def test_oversize_line_is_rejected_without_truncating_it(self):
        command = self.script("printf '#'; head -c 16384 /dev/zero | tr '\\000' x")
        self.assert_rejected(command, 'overlong output line')

    def test_embedded_nul_is_rejected(self):
        self.assert_rejected("printf 'cache-size=123\\000\\n'", 'NUL')

    def test_recursive_command_strings_are_bounded(self):
        command = self.script("printf 'conf-script=%s recursive\\n' \"$0\"")+' recursive'
        self.assert_rejected(command, 'nesting limit')

    def test_plain_generator_filename_retains_inode_deduplication(self):
        command = self.script("printf 'conf-script=%s\\ncache-size=126\\n' \"$0\"")
        result = self.run_parser(command, startup=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PARSED_CACHE=126', result.stdout)

    def test_sequential_generator_count_is_bounded(self):
        self.config.write_text('port=0\n'+''.join('conf-script=true\n' for _ in range(17)))
        result = subprocess.run([str(self.binary), '--test', '-C', str(self.config)],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('invocation or nesting limit', result.stderr)

    def test_many_generators_share_one_total_deadline(self):
        self.config.write_text('port=0\n'+''.join('conf-script=sleep 0.2\n' for _ in range(12)))
        start = time.monotonic()
        result = subprocess.run([str(self.binary), '--test', '-C', str(self.config)],
                                env=self.env, capture_output=True, text=True, timeout=4)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('time budget', result.stderr)
        self.assertLess(time.monotonic()-start, 3)

    def test_cumulative_output_budget_survives_stream_release(self):
        body = '#'+(' harmless comment'*100)+'\n'
        data = self.base/'public-generated.conf'
        data.write_text(body*900)
        self.config.write_text('port=0\n'+''.join('conf-script=cat '+str(data)+'\n' for _ in range(4)))
        result = subprocess.run([str(self.binary), '--test', '-C', str(self.config)],
                                env=self.env, capture_output=True, text=True, timeout=4)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('output budget', result.stderr)

    def test_generated_output_does_not_consume_validation_file_size_limit(self):
        command = self.script("i=0; while [ $i -lt 4000 ]; do printf '# harmless configuration comment\\n'; i=$((i+1)); done")
        result = self.run_parser(command, fsize=32768)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_output_and_line_limits_are_accepted(self):
        data = self.base/'public-generated.conf'
        line = '#'+('x'*16383)
        data.write_text((line+'\n')*127+'#'+('x'*16256))
        self.assertEqual(data.stat().st_size,2*1024*1024)
        result = self.run_parser('cat '+str(data),fsize=32768)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_long_command_in_error_context_is_bounded(self):
        self.assert_rejected("printf 'BadDirective\\n'; #"+'x'*16000, 'bad option')

    def test_generated_fifo_include_is_rejected_before_blocking_open(self):
        fifo = self.base/'public.fifo'; os.mkfifo(fifo)
        for startup in (False,True):
            with self.subTest(startup=startup):
                self.assert_rejected("printf 'conf-file="+str(fifo)+"\\n'",'not a regular file',startup=startup)

    def test_generated_device_include_is_rejected(self):
        self.assert_rejected("printf 'conf-file=/dev/zero\\n'",'not a regular file',startup=True)

    def test_stdin_include_is_explicitly_rejected(self):
        self.assert_rejected("printf 'conf-file=-\\n'",'stdin configuration',startup=True)
        result = subprocess.run([str(self.binary),'--test','-C','-'],env=self.env,
                                capture_output=True,text=True,timeout=3,input='port=0\n')
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('stdin configuration',result.stderr)

    def test_dev_null_and_symlink_to_regular_include_remain_compatible(self):
        included = self.base/'included.conf'; included.write_text('cache-size=127\n')
        alias = self.base/'include-alias'; alias.symlink_to(included.name)
        result = self.run_parser("printf 'conf-file=/dev/null\\nconf-file="+str(alias)+"\\n'",startup=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PARSED_CACHE=127',result.stdout)

    def test_generated_include_cannot_bypass_line_and_nul_limits(self):
        included = self.base/'included.conf'
        command = "printf 'conf-file="+str(included)+"\\n'"
        for text in ('#'+'x'*16384, 'cache-size=127\0\n'):
            with self.subTest(text_bytes=len(text)):
                included.write_text(text)
                self.assert_rejected(command,'NUL or overlong input line')

    def test_generated_include_cannot_bypass_per_file_byte_limit(self):
        included = self.base/'included.conf'
        included.write_text(('#'+'x'*8190+'\n')*256+'\n')
        self.assertEqual(included.stat().st_size,2*1024*1024+1)
        self.assert_rejected("printf 'conf-file="+str(included)+"\\n'",'input byte budget')

    def test_generated_include_cannot_bypass_aggregate_byte_limit(self):
        names = []
        for i in range(8):
            included = self.base/('include-'+str(i))
            included.write_text(('#'+'x'*8190+'\n')*256)
            names.append(str(included))
        command = "printf '"+''.join('conf-file='+name+'\\n' for name in names)+"'"
        self.assert_rejected(command,'input byte budget')

    def test_generated_include_cannot_bypass_file_count_limit(self):
        names = []
        for i in range(128):
            included = self.base/('include-'+str(i));included.write_text('# harmless\n')
            names.append(str(included))
        command = "printf '"+''.join('conf-file='+name+'\\n' for name in names)+"'"
        self.assert_rejected(command,'file count limit')

    def test_generated_include_cannot_bypass_nesting_limit(self):
        for i in range(33):
            included = self.base/('include-'+str(i))
            included.write_text('conf-file='+str(self.base/('include-'+str(i+1)))+'\n' if i<32 else '# harmless\n')
        self.assert_rejected("printf 'conf-file="+str(self.base/'include-0')+"\\n'",'include nesting limit')

    def test_generated_conf_dir_file_collection_is_bounded_before_sorting(self):
        directory = self.base/'conf.d'; directory.mkdir()
        for i in range(129):
            (directory/('%03d.conf'%i)).write_text('# harmless\n')
        self.assert_rejected("printf 'conf-dir="+str(directory)+"\\n'",'directory file budget')

    def test_generated_conf_dir_ignored_entries_are_globally_bounded(self):
        directories = []
        for k in range(2):
            directory = self.base/('ignored-'+str(k));directory.mkdir();directories.append(directory)
            for i in range(2048):
                (directory/('.ignored-%04d'%i)).touch()
        command = "printf '"+''.join('conf-dir='+str(d)+'\\n' for d in directories)+"'"
        self.assert_rejected(command,'directory entry budget')

    def test_small_conf_dir_preserves_suffix_filter_and_sort_order(self):
        directory = self.base/'conf.d'; directory.mkdir()
        (directory/'b.conf').write_text('local-service\n')
        (directory/'a.conf').write_text('cache-size=128\n')
        for name in ('bad.skip','.hidden.conf','backup.conf~'):
            (directory/name).write_text('BadDirective\n')
        result = self.run_parser("printf 'conf-dir="+str(directory)+",*.conf\\n'",startup=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PARSED_CACHE=128',result.stdout)
        # Repeated cache-size is intentionally invalid. The error belongs to
        # b.conf only when the valid a.conf has been parsed first.
        (directory/'b.conf').write_text('cache-size=129\n')
        result = self.run_parser("printf 'conf-dir="+str(directory)+",*.conf\\n'")
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('illegal repeated keyword',result.stderr)
        self.assertIn(str(directory/'b.conf'),result.stderr)

    def test_dynamic_hostname_upstream_never_enters_blocking_resolver(self):
        included = self.base/'hostname.conf';included.write_text('server=resolver.fixture.invalid\n')
        cases = [
            ('server=resolver.fixture.invalid\n',False,True),
            ('server=192.0.2.53\n',True,False),
            ("conf-script=printf 'server=resolver.fixture.invalid\\n'\n",False,False),
            ("conf-script=printf 'server=192.0.2.53\\n'\n",True,False),
            ("conf-script=printf 'conf-file="+str(included)+"\\n'\n",False,False),
        ]
        for text,accepted,resolver_called in cases:
            with self.subTest(config=text):
                self.config.write_text('port=0\n'+text)
                result = subprocess.run([str(self.resolver_binary),'--test','-C',str(self.config)],
                                        env=self.env,capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,0 if accepted else 1,result.stderr)
                self.assertEqual('RESOLVER_STUB_CALLED' in result.stderr,resolver_called)
                if not accepted and not resolver_called:
                    self.assertIn('hostname upstream is not supported after conf-script',result.stderr)

    def test_collector_setup_and_read_failures_are_closed(self):
        for fault in ('fork', 'pipe', 'cloexec', 'allocation', 'stream', 'read', 'poll', 'clock', 'calls', 'depth'):
            with self.subTest(fault=fault):
                result = subprocess.run([str(self.collector), "printf 'cache-size=123\\n'"],
                                        env={**self.env, 'COLLECTOR_FAULT': fault},
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertNotIn('Sanitizer', result.stderr)

    def test_successful_collector_releases_child_and_memory_stream(self):
        result = subprocess.run([str(self.collector), "printf 'cache-size=123\\n'"],
                                env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'cache-size=123\n')

    def test_generator_does_not_inherit_parent_file_descriptors(self):
        with (self.base/'public-held-file').open('w') as held:
            command = ('if [ -e /dev/fd/'+str(held.fileno())+
                       ' ]; then exit 7; fi; printf "cache-size=123\\n"')
            result = subprocess.run([str(self.collector),command],env=self.env,
                                    pass_fds=(held.fileno(),),capture_output=True,
                                    text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'cache-size=123\n')

    def test_closed_parent_stdio_does_not_leave_cloexec_on_child_stdout(self):
        def close_stdio():
            for fd in (0, 1, 2):
                os.close(fd)
        result = subprocess.run([str(self.collector), "printf 'cache-size=123\\n'"],
                                env={**self.env, 'COLLECTOR_FAULT':'closed-stdio'},
                                capture_output=True, preexec_fn=close_stdio, timeout=3)
        self.assertEqual(result.returncode, 0)

    def test_parent_termination_cleans_running_generator_group(self):
        pidfile = self.base/'generator.pid'
        command = self.script('echo $$ > '+str(pidfile)+"; trap '' TERM; sleep 30")
        self.config.write_text('port=0\nconf-script='+command+'\n')
        process = subprocess.Popen([str(self.binary),'--test','-C',str(self.config)],
                                   env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline = time.monotonic()+1
            while not pidfile.exists() and time.monotonic()<deadline:
                time.sleep(0.01)
            self.assertTrue(pidfile.exists())
            process.terminate()
            stdout, stderr = process.communicate(timeout=3)
            self.assertEqual(process.returncode,1,stderr)
            self.assertIn('cancelled',stderr)
            state = subprocess.run(['ps','-o','stat=','-p',pidfile.read_text().strip()],
                                   text=True,capture_output=True).stdout.strip()
            self.assertTrue(not state or state.startswith('Z'),state)
        finally:
            if process.poll() is None:
                process.kill(); process.communicate()

    def prepare_wrapper(self, body):
        work = self.base/'work'; work.mkdir(mode=0o700)
        custom = self.base/'custom.conf'
        custom.write_text('conf-script='+self.script(body)+'\nlocal-service\n')
        main = self.base/'main.conf'; main.write_text('port=0\nconf-file='+str(custom)+'\n')
        bin_dir = self.base/'bin'; bin_dir.mkdir()
        for name, code in {
            'nvram': '#!/bin/sh\nprintf "0\\n"\n',
            'logger': '#!/bin/sh\nexit 0\n',
            'df': '#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 24576 0 24576 0%% fixture\\n"\n',
            'stat': '#!/usr/bin/env python3\nimport os,sys\na=sys.argv[1:];print(os.stat(a[-1]).st_size)\n',
            'md5sum': '#!/usr/bin/env python3\nimport hashlib,sys\nprint(hashlib.md5(open(sys.argv[1],"rb").read()).hexdigest()+"  "+sys.argv[1])\n',
        }.items():
            path = bin_dir/name; path.write_text(code); path.chmod(0o700)
        text = (ROOT/'trunk/user/dnsmasq/dnsmasq.sh').read_text()
        mapping = {'/etc/storage/dnsmasq/dnsmasq.conf': str(custom),
                   '/etc/dnsmasq.conf': str(main), '/usr/sbin/dnsmasq': str(self.binary),
                   '/tmp/.dnsmasq-startup': str(work/'.dnsmasq-startup')}
        pattern = '|'.join(re.escape(k) for k in sorted(mapping,key=len,reverse=True))
        wrapper = self.base/'startup.sh'
        wrapper.write_text(re.sub(pattern, lambda m:mapping[m.group(0)], text))
        return wrapper, custom, main, work, {**self.env, 'PATH': str(bin_dir)+':'+os.environ['PATH']}

    def check_wrapper_failure(self, failing_call):
        counter = self.base/'counter'
        body = ('n=0; [ ! -f '+str(counter)+' ] || n=$(cat '+str(counter)+'); '
                'n=$((n+1)); printf "%s" "$n" > '+str(counter)+'; '
                'if [ "$n" = '+str(failing_call)+' ]; then exec 1>&- 2>&-; sleep 30; fi; '
                "printf 'cache-size=123\\n'")
        wrapper, custom, main, work, env = self.prepare_wrapper(body)
        original = hashlib.sha256(custom.read_bytes()).hexdigest()
        result = subprocess.run(['sh',str(wrapper)], env=env, capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertEqual(int(counter.read_text()),failing_call)
        self.assertEqual(hashlib.sha256(custom.read_bytes()).hexdigest(),original)
        self.assertFalse(list(work.iterdir()))
        self.assertFalse(list(self.base.rglob('*.before-migration*')))

    def test_wrapper_first_validation_timeout_preserves_original(self):
        self.check_wrapper_failure(1)

    def test_wrapper_second_validation_timeout_preserves_original(self):
        self.check_wrapper_failure(2)

    def test_third_startup_parse_has_its_own_guard_and_preserves_config(self):
        counter = self.base/'counter'
        body = ('n=0; [ ! -f '+str(counter)+' ] || n=$(cat '+str(counter)+'); '
                'n=$((n+1)); printf "%s" "$n" > '+str(counter)+'; '
                'if [ "$n" = 3 ]; then exec 1>&- 2>&-; sleep 30; fi; '
                "printf 'cache-size=123\\n'")
        wrapper, custom, main, work, env = self.prepare_wrapper(body)
        original = custom.read_bytes()
        result = subprocess.run(['sh',str(wrapper)],env=env,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(counter.read_text(),'2')
        result = subprocess.run([str(self.parse_binary),'-C',str(main)],env=env,
                                capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('time budget',result.stderr)
        self.assertEqual(counter.read_text(),'3')
        self.assertEqual(custom.read_bytes(),original)
        self.assertFalse(list(work.iterdir()))

    def test_three_successful_generations_are_not_claimed_as_identical(self):
        counter = self.base/'counter'
        body = ('n=0; [ ! -f '+str(counter)+' ] || n=$(cat '+str(counter)+'); '
                'n=$((n+1)); printf "%s" "$n" > '+str(counter)+'; '
                "printf 'cache-size=%s\\n' \"$n\"")
        wrapper, custom, main, work, env = self.prepare_wrapper(body)
        original = custom.read_bytes()
        result = subprocess.run(['sh',str(wrapper)],env=env,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        result = subprocess.run([str(self.parse_binary),'-C',str(main)],env=env,
                                capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PARSED_CACHE=3',result.stdout)
        self.assertEqual(counter.read_text(),'3')
        self.assertEqual(custom.read_bytes(),original)
        self.assertFalse(list(work.iterdir()))


if __name__ == '__main__':
    unittest.main()
