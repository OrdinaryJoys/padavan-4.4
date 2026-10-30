"""Actual DNS runtime consumers with public files, no listener or router IO."""
from pathlib import Path
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'trunk/user/dnsmasq/dnsmasq-2.93'
LEASE = '0 00:11:22:33:44:55 192.0.2.72 publicfixture *\n'


class DNSRuntimeConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-dns-consumer-code-')
        cls.tree = Path(cls.build.name).resolve() / 'source'
        shutil.copytree(SOURCE, cls.tree, ignore=shutil.ignore_patterns(
            '*.o', 'dnsmasq', 'dnsmasq_baseline', '.copts_*'))
        main = cls.tree / 'src/dnsmasq.c'
        text = main.read_text()
        text = text.replace('#include "dnsmasq.h"',
                            '#include "dnsmasq.h"\n#include "dynamic_conf.h"')
        needle = '  read_opts(argc, argv, compile_opts);'
        if text.count(needle) != 1:
            raise AssertionError('consumer replay stop point changed')
        replay = r'''
  /* Private test copy: actual consumers run before any socket setup. */
  if (getenv("K2P_CONSUMER_OPERATION")) {
    const char *op=getenv("K2P_CONSUMER_OPERATION");
    const char *path=getenv("K2P_CONSUMER_INPUT");
    printf("BEFORE=%s\n",op);fflush(stdout);
    log_start(NULL,-1);
    if (!strcmp(op,"hosts")) {
      cache_init();
      printf("HOSTS=%d\n",read_hostsfile((char *)path,SRC_AH,0,NULL,0));
    }
    if (!strcmp(op,"status")) {
      struct conf_script_budget budget={0};const char *error;int raw=-99,status;
      FILE *stream=conf_script_open_status(path,&budget,&error,&raw);
      printf("STREAM=%d RAW=%d\n",stream!=NULL,raw);
      if(stream)conf_script_close(stream,&budget);
      else printf("ERROR=%s\n",error);
      errno=0;
      printf("REAPED=%d\n",waitpid(-1,&status,WNOHANG)==-1&&errno==ECHILD);
    }
#ifdef HAVE_DHCP
    if (!strcmp(op,"lease")) {
      struct in_addr address;struct dhcp_lease *found;
      daemon->packet_buff_sz=daemon->edns_pktsz+MAXDNAME+RRFIXEDSZ;
      daemon->packet=safe_malloc(daemon->packet_buff_sz);
      dhcp_common_init();lease_init(0);
      inet_pton(AF_INET,"192.0.2.72",&address);found=lease_find_by_addr(address);
      printf("LEASE_FOUND=%d\n",found!=NULL);
      if(found)printf("LEASE_HOST=%s\n",found->hostname?found->hostname:"");
      if(daemon->lease_stream) {
        int fd=fileno(daemon->lease_stream),flags=fcntl(fd,F_GETFL);
        printf("APPEND=%d NONBLOCK=%d CLOEXEC=%d\n",!!(flags&O_APPEND),
               !!(flags&O_NONBLOCK),!!(fcntl(fd,F_GETFD)&FD_CLOEXEC));
        if(getenv("K2P_CONSUMER_APPEND")) {
          if(fseek(daemon->lease_stream,0,SEEK_SET)||
             fputs("0 00:11:22:33:44:66 192.0.2.73 appended *\n",daemon->lease_stream)==EOF||
             fflush(daemon->lease_stream))return 97;
        }
      }
    }
#else
    if (!strcmp(op,"lease"))return 98;
#endif
    printf("AFTER=%s\n",op);fflush(stdout);return 0;
  }
'''
        main.write_text(text.replace(needle, needle + replay))
        options = ('-DNO_DHCP6 -DNO_TFTP -DNO_INOTIFY -DNO_AUTH -DNO_LOOP '
                   '-DCONF_SCRIPT_TIMEOUT_MS=800 -DCONF_SCRIPT_TOTAL_MS=2400')
        result = subprocess.run(['make', '-j4', 'CC=clang', 'COPTS=' + options,
                                 'CFLAGS=-O1 -g -Wall -Wextra -fsanitize=address,undefined',
                                 'LDFLAGS=-fsanitize=address,undefined'], cwd=cls.tree,
                                text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.binary = cls.tree / 'src/dnsmasq'
        if b'LEASE_FOUND=%d' not in cls.binary.read_bytes():
            raise AssertionError('actual DHCP consumer was not compiled')

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='k2p-dns-consumer-')
        self.base = Path(self.temp.name).resolve()
        self.config = self.base / 'main'
        self.input = self.base / 'input'
        self.log = self.base / 'log'
        self.script = self.base / 'public-init.sh'
        self.pidfile = self.base / 'child-pid'
        self.env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'}

    def tearDown(self):
        self.temp.cleanup()

    def run_consumer(self, operation, extra='', expect=0, input_path=None, append=False):
        path = input_path or self.input
        self.config.write_text('port=0\nno-hosts\nno-resolv\nlog-facility=' +
                               str(path if operation == 'log' else self.log) + '\n' + extra)
        env = {**self.env, 'K2P_CONSUMER_OPERATION': operation,
               'K2P_CONSUMER_INPUT': str(path)}
        if append:
            env['K2P_CONSUMER_APPEND'] = '1'
        start = time.monotonic()
        process = subprocess.Popen([str(self.binary), '-C', str(self.config)], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            out, err = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=2)
            self.fail('actual consumer blocked beyond its private fixture deadline')
        self.assertEqual(process.returncode, expect, err + out)
        self.assertNotIn('AddressSanitizer', err)
        self.assertNotIn('runtime error:', err)
        self.assertLess(time.monotonic() - start, 4.5)
        return out, err

    def lease(self, extra='', expect=0, append=False):
        return self.run_consumer('lease', 'dhcp-range=192.0.2.10,192.0.2.100,1h\n' +
                                 'dhcp-leasefile=' + str(self.input) + '\n' + extra,
                                 expect=expect, append=append)

    def init_script(self, body, expect=0, command_prefix=''):
        self.script.write_text('#!/bin/sh\n' + body + '\n')
        self.script.chmod(0o700)
        return self.lease('leasefile-ro\ndhcp-script=' + command_prefix + str(self.script) + '\n',
                          expect=expect)

    def assert_owned_child_gone(self):
        if not self.pidfile.exists():
            return
        pid = int(self.pidfile.read_text())
        for _ in range(30):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            state = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True,
                                   text=True, timeout=2).stdout.strip()
            if not state or state.startswith('Z'):
                return
            time.sleep(0.02)
        self.fail('owned fixture child remains alive')

    def test_hosts_regular_record_loads(self):
        self.input.write_text('192.0.2.61 public.fixture\n')
        out, _ = self.run_consumer('hosts')
        self.assertIn('HOSTS=1\n', out)

    def test_hosts_regular_symlink_and_hardlink_remain_supported(self):
        target = self.base / 'target';target.write_text('192.0.2.61 public.fixture\n')
        for alias in ('symlink', 'hardlink'):
            with self.subTest(alias=alias):
                if alias == 'symlink':self.input.symlink_to(target)
                else:os.link(target, self.input)
                out, _ = self.run_consumer('hosts');self.assertIn('HOSTS=1\n', out)
                self.input.unlink()

    def test_hosts_over_two_mib_is_accepted_with_larger_policy(self):
        self.input.write_bytes(b'# public padding\n' * 196608 + b'192.0.2.61 public.fixture\n')
        self.assertGreater(self.input.stat().st_size, 2 * 1024 * 1024)
        out, _ = self.run_consumer('hosts');self.assertIn('HOSTS=1\n', out)

    def test_hosts_fifo_and_fifo_alias_are_rejected_without_blocking(self):
        target=self.base/'fifo';os.mkfifo(target,0o600)
        for alias in (False,True):
            with self.subTest(alias=alias):
                if alias:self.input.symlink_to(target)
                out,_=self.run_consumer('hosts',input_path=self.input if alias else target)
                self.assertIn('HOSTS=0\n',out)

    def test_hosts_oversize_nul_and_overlong_line_are_rejected(self):
        for payload in (b'\0',b'#'+b'x'*16385+b'\n',b'x'*(16*1024*1024+1)):
            with self.subTest(size=len(payload)):
                self.input.write_bytes(payload);out,_=self.run_consumer('hosts')
                self.assertIn('HOSTS=0\n',out)

    def test_log_new_and_existing_regular_file_preserve_contents(self):
        self.run_consumer('log');self.assertTrue(self.input.is_file())
        self.input.write_bytes(b'preserved\n');self.run_consumer('log')
        self.assertEqual(self.input.read_bytes(),b'preserved\n')

    def test_log_regular_alias_is_supported(self):
        target=self.base/'target';target.write_bytes(b'preserved\n');self.input.symlink_to(target)
        self.run_consumer('log');self.assertEqual(target.read_bytes(),b'preserved\n')

    def test_log_fifo_without_reader_fails_startup_promptly(self):
        os.mkfifo(self.input,0o600);_,err=self.run_consumer('log',expect=3)
        self.assertIn('log',err.lower())

    def test_log_fifo_with_reader_is_still_refused_as_nonregular(self):
        os.mkfifo(self.input,0o600);fd=os.open(self.input,os.O_RDONLY|os.O_NONBLOCK)
        try:self.run_consumer('log',expect=3)
        finally:os.close(fd)

    def test_lease_regular_database_is_loaded_and_writer_kept(self):
        self.input.write_text(LEASE);out,_=self.lease()
        self.assertIn('LEASE_FOUND=1\n',out);self.assertIn('LEASE_HOST=publicfixture\n',out)
        self.assertIn('APPEND=1 NONBLOCK=1 CLOEXEC=1\n',out)

    def test_lease_writer_remains_append_even_after_seek(self):
        self.input.write_text(LEASE);self.lease(append=True)
        self.assertEqual(self.input.read_text(),LEASE+'0 00:11:22:33:44:66 192.0.2.73 appended *\n')

    def test_lease_missing_file_is_created(self):
        out,_=self.lease();self.assertTrue(self.input.is_file());self.assertIn('LEASE_FOUND=0\n',out)

    def test_lease_regular_symlink_preserves_target(self):
        target=self.base/'target';target.write_text(LEASE);self.input.symlink_to(target)
        out,_=self.lease();self.assertIn('LEASE_FOUND=1\n',out);self.assertEqual(target.read_text(),LEASE)

    def test_lease_fifo_and_alias_are_rejected(self):
        target=self.base/'fifo';os.mkfifo(target,0o600)
        self.input.symlink_to(target);self.lease(expect=3)
        self.input.unlink();os.mkfifo(self.input,0o600);self.lease(expect=3)

    def test_lease_oversized_initial_database_is_rejected_without_write(self):
        self.input.write_bytes(b'#x\n'*(2097152//3+1));before=self.input.read_bytes()
        self.lease(expect=3);self.assertEqual(self.input.read_bytes(),before)

    def test_lease_init_script_valid_format_and_init_argument(self):
        out,_=self.init_script('[ "$1" = init ] || exit 9\nprintf '+shlex.quote(LEASE))
        self.assertIn('LEASE_FOUND=1\n',out);self.assertIn('LEASE_HOST=publicfixture\n',out)
        self.assertFalse(self.input.exists())

    def test_lease_init_nonzero_exit_keeps_upstream_offset(self):
        _,err=self.init_script('exit 7',expect=17)
        self.assertIn('lease-init script returned exit code 7',err)

    def test_lease_init_signal_is_refused_without_waitstatus_misread(self):
        _,err=self.init_script('kill -TERM $$',expect=3,command_prefix='exec ')
        self.assertIn('bounded lease-init failed',err)

    def test_lease_init_eof_then_hang_is_bounded_and_reaped(self):
        _,err=self.init_script('printf "%s" "$$" > '+str(self.pidfile)+
                               '\nexec 1>&- 2>&-\nexec sleep 4',expect=3)
        self.assertIn('lease-init',err);self.assert_owned_child_gone()

    def test_lease_init_orphan_held_pipe_is_killed(self):
        _,err=self.init_script('sleep 4 &\nprintf "%s" "$!" > '+str(self.pidfile)+'\nexit 0',expect=3)
        self.assertIn('lease-init',err);self.assert_owned_child_gone()

    def test_lease_init_output_failure_does_not_become_exit0_success(self):
        payload=self.base/'payload';payload.write_bytes(LEASE.encode()*50000)
        _,err=self.init_script('cat '+str(payload)+'\nexit 0',expect=3)
        self.assertIn('bounded lease-init failed',err)

    def test_optional_raw_waitstatus_api_reports_real_reap(self):
        for command,raw,stream in [('exit 0',0,1),('exit 7',7<<8,0),('kill -TERM $$',signal.SIGTERM,0)]:
            with self.subTest(command=command):
                out,_=self.run_consumer('status',input_path=command)
                self.assertIn('STREAM=%d RAW=%d\n'%(stream,raw),out);self.assertIn('REAPED=1\n',out)


if __name__ == '__main__':
    unittest.main()
