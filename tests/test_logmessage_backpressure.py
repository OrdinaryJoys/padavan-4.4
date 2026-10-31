"""Real shared logger, private AF_UNIX socket only; no system log or device IO."""
from pathlib import Path
import errno
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from test_httpd_regressions import function, source


class LogmessageBackpressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-logmessage-code-')
        cls.root = Path(cls.build.name)
        actual = function(source('trunk/user/shared/shutils.c'), 'logmessage')
        if actual.count('"/dev/log"') != 1:
            raise AssertionError('Shared logging endpoint changed')
        # Substitute only the fixed endpoint in an isolated source copy.
        actual = actual.replace('"/dev/log"', 'fixture_path')
        code = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <time.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <syslog.h>
static const char *fixture_path;
static int inject, socket_calls, closes, sends, flags_ok;
static int socket_backend(int domain,int type,int protocol) {
 socket_calls++;if(inject==1){errno=EMFILE;return -1;}
 return socket(domain,type,protocol);
}
static int fcntl_backend(int fd,int command,...) {
 va_list ap;int arg;va_start(ap,command);
 if(inject==2&&command==F_GETFL){va_end(ap);errno=EBADF;return -1;}
 if(inject==3&&command==F_SETFL){va_end(ap);errno=EPERM;return -1;}
 if(inject==4&&command==F_GETFD){va_end(ap);errno=EBADF;return -1;}
 if(inject==5&&command==F_SETFD){va_end(ap);errno=EPERM;return -1;}
 if(command==F_GETFL||command==F_GETFD){va_end(ap);return fcntl(fd,command);}
 arg=va_arg(ap,int);va_end(ap);return fcntl(fd,command,arg);
}
static ssize_t sendto_backend(int fd,const void *data,size_t size,int flags,const struct sockaddr *address,socklen_t len) {
 sends++;flags_ok=!!(fcntl(fd,F_GETFL)&O_NONBLOCK)&&!!(fcntl(fd,F_GETFD)&FD_CLOEXEC)&&
  (flags&(MSG_DONTWAIT|MSG_NOSIGNAL))==(MSG_DONTWAIT|MSG_NOSIGNAL);
 if(inject>=6){errno=inject==6?EINTR:inject==7?ENOBUFS:EAGAIN;return -1;}
 return sendto(fd,data,size,flags,address,len);
}
static int close_backend(int fd){closes++;return close(fd);}
#define socket socket_backend
#define fcntl fcntl_backend
#define sendto sendto_backend
#define close close_backend
'''
        code += actual
        code += r'''
int main(int argc,char **argv) {
 int repeat,i;if(argc!=5)return 90;fixture_path=argv[1];inject=atoi(argv[2]);repeat=atoi(argv[3]);
 for(i=0;i<repeat;i++){errno=EDOM;logmessage("watchdog-proof","%s",argv[4]);if(errno!=EDOM)return 91;}
 printf("{\"socket_calls\":%d,\"closes\":%d,\"sends\":%d,\"flags_ok\":%d}\n",socket_calls,closes,sends,flags_ok);
 return 0;
}
'''
        cfile = cls.root / 'probe.c'
        cfile.write_text(code)
        cls.probes = []
        compiler = shutil.which('clang') or shutil.which('cc')
        if not compiler:
            raise AssertionError('C compiler required')
        for name, extra in [('native', []), ('sanitized', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
            target = cls.root / name
            subprocess.run([compiler, '-std=gnu99', '-Wall', '-Wextra', '-Werror', *extra,
                            str(cfile), '-o', str(target)], check=True, capture_output=True)
            cls.probes.append(target)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='k2p-logmessage-', dir='/tmp')
        self.path = str(Path(self.temp.name).resolve() / 'log')
        # Darwin Unix socket names have a smaller pathname budget.
        self.path = self.path.replace('/private/tmp/', '/tmp/')
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.server.bind(self.path)
        self.server.settimeout(0.2)

    def tearDown(self):
        self.server.close()
        self.temp.cleanup()

    def invoke(self, probe, *, message='literal %n %s %% proof', inject=0, repeat=1):
        result = subprocess.run([str(probe), self.path, str(inject), str(repeat), message],
                                capture_output=True, text=True, timeout=3,
                                env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=' +
                                     ('1' if sys.platform.startswith('linux') else '0')})
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertNotIn('runtime error:', result.stderr)
        self.assertNotIn('ERROR: AddressSanitizer', result.stderr)
        return json.loads(result.stdout)

    def drain(self):
        frames = []
        while True:
            try:
                frames.append(self.server.recv(2048))
            except socket.timeout:
                return frames

    def fill(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as filler:
            filler.setblocking(False)
            for i in range(10000):
                try:
                    filler.sendto(b'private-queue-fill', self.path)
                except BlockingIOError:
                    self.assertGreater(i, 0)
                    return i
                except OSError as error:
                    if error.errno in (errno.ENOBUFS, errno.EAGAIN):
                        self.assertGreater(i, 0)
                        return i
                    raise
        self.fail('Private AF_UNIX queue did not reach backpressure')

    def test_literal_percent_sequences_preserved_and_original_priority_retained(self):
        for probe in self.probes:
            row = self.invoke(probe)
            frame = self.server.recv(2048)
            self.assertTrue(frame.startswith(b'<8>'), frame)
            self.assertTrue(frame.endswith(b'watchdog-proof: literal %n %s %% proof'), frame)
            self.assertEqual(row, dict(socket_calls=1, closes=1, sends=1, flags_ok=1))

    def test_full_kernel_queue_drops_promptly_and_then_recovers(self):
        for probe in self.probes:
            self.fill()
            started = time.monotonic()
            row = self.invoke(probe, repeat=128)
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(row['socket_calls'], 128)
            self.assertEqual(row['closes'], 128)
            self.assertEqual(row['sends'], 128)
            self.assertEqual(row['flags_ok'], 1)
            self.drain()
            self.invoke(probe, message='recovered-after-drain')
            self.assertTrue(self.server.recv(2048).endswith(b'watchdog-proof: recovered-after-drain'))

    def test_missing_receiver_returns_and_next_call_reconnects(self):
        self.server.close()
        Path(self.path).unlink()
        for probe in self.probes:
            row = self.invoke(probe)
            self.assertEqual((row['sends'], row['closes']), (1, 1))
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.server.bind(self.path)
        self.server.settimeout(0.2)
        for probe in self.probes:
            self.invoke(probe, message='receiver-recreated')
            self.assertTrue(self.server.recv(2048).endswith(b'receiver-recreated'))

    def test_flag_setup_errors_close_once_without_send_or_sync_fallback(self):
        for probe in self.probes:
            for mode in range(1, 6):
                row = self.invoke(probe, inject=mode)
                self.assertEqual(row['socket_calls'], 1)
                self.assertEqual(row['sends'], 0)
                self.assertEqual(row['closes'], 0 if mode == 1 else 1)

    def test_interruption_buffer_error_and_wouldblock_do_not_retry(self):
        for probe in self.probes:
            for mode in (6, 7, 8):
                row = self.invoke(probe, inject=mode)
                self.assertEqual((row['socket_calls'], row['closes'], row['sends'], row['flags_ok']), (1, 1, 1, 1))

    def test_long_body_is_bounded_and_descriptor_count_stays_balanced(self):
        for probe in self.probes:
            row = self.invoke(probe, message='x' * 4096)
            frame = self.server.recv(2048)
            body = frame.split(b'watchdog-proof: ', 1)[1]
            self.assertEqual(body, b'x' * 511)
            self.assertLess(len(frame), 640)
            self.assertEqual(row['socket_calls'], row['closes'])


if __name__ == '__main__':
    unittest.main()
