#!/usr/bin/env python3
"""Exercise actual TLS callbacks with deterministic OpenSSL I/O outcomes.

These are retry/control-flow tests, not a TLS cryptography interoperability test.
No sockets, router requests, keys or certificates are used.
"""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_httpd_regressions import function
from test_independent_http_edges import current_source


class IndependentTlsTimeouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='k2p-independent-tls-')
        source = current_source('trunk/user/httpd/https.c')
        code = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
typedef int SSL;
typedef int SSL_CTX;
typedef struct {SSL *ssl;int fd;} http_ssl_cookie_t;
#define SSL_ERROR_SYSCALL 5
#define SSL_ERROR_ZERO_RETURN 6
#define SSL_ERROR_WANT_READ 2
#define SSL_ERROR_WANT_WRITE 3
#define SSL_MODE_AUTO_RETRY 4
static SSL_CTX *ssl_ctx;
static SSL mock_ssl;
static int debug_mode,mode,calls,last_error,http_ssl_io;
static int http_request_expired(void){return 0;}
static int http_request_wait(int fd,int writing){return 0;}
static int operation(int length){
 calls++;
 if(mode==0){
  if(calls<4){errno=EAGAIN;last_error=SSL_ERROR_WANT_READ;return -1;}
  errno=0;last_error=SSL_ERROR_ZERO_RETURN;return 0;
 }
 if(mode==1 && calls==1){errno=EINTR;last_error=SSL_ERROR_SYSCALL;return -1;}
 errno=0;return length;
}
static int SSL_read(SSL*s,void*b,int length){return operation(length);}
static int SSL_write(SSL*s,const void*b,int length){return operation(length);}
static int SSL_accept(SSL*s){return operation(1);}
static int SSL_pending(SSL*s){return 0;}
static int SSL_get_error(SSL*s,int result){return last_error;}
static SSL *SSL_new(SSL_CTX*ctx){return &mock_ssl;}
static int SSL_set_mode(SSL*s,int value){return 1;}
static int SSL_set_fd(SSL*s,int fd){return 1;}
static void SSL_free(SSL*s){}
static void ERR_print_errors_fp(FILE*stream){}
static FILE *test_fopencookie(void*cookie,const char*mode,int io){return NULL;}
#define fopencookie test_fopencookie
'''
        if 'ssl_interrupted(' in source:
            code += function(source, 'ssl_interrupted')
        for name in ('http_ssl_read', 'http_ssl_write', 'ssl_server_fopen'):
            code += function(source, name)
        code += r'''
long tls_io(int operation_id,int scenario){
 char data[8]={0};http_ssl_cookie_t cookie={&mock_ssl,1};mode=scenario;calls=0;
 if(operation_id==0)return http_ssl_read(&cookie,data,sizeof(data));
 if(operation_id==1)return http_ssl_write(&cookie,data,sizeof(data));
 ssl_server_fopen(1);return calls;
}
int calls_seen(void){return calls;}
'''
        path = Path(cls.tmp.name) / 'tls.c'
        library = Path(cls.tmp.name) / 'tls.dylib'
        path.write_text(code)
        result = subprocess.run(['cc', '-shared', '-fPIC', '-O0', str(path), '-o', str(library)], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.tls_io.argtypes = [ctypes.c_int, ctypes.c_int]
        cls.lib.tls_io.restype = ctypes.c_long

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_idle_tls_read_does_not_retry_timeout(self):
        self.assertEqual(self.lib.tls_io(0, 0), -1)
        self.assertEqual(self.lib.calls_seen(), 1)

    def test_idle_tls_write_does_not_retry_timeout(self):
        self.assertEqual(self.lib.tls_io(1, 0), -1)
        self.assertEqual(self.lib.calls_seen(), 1)

    def test_idle_tls_handshake_does_not_retry_timeout(self):
        self.assertEqual(self.lib.tls_io(2, 0), 1)

    def test_interrupted_tls_read_retries(self):
        self.assertEqual(self.lib.tls_io(0, 1), 8)
        self.assertEqual(self.lib.calls_seen(), 2)

    def test_interrupted_tls_write_retries(self):
        self.assertEqual(self.lib.tls_io(1, 1), 8)
        self.assertEqual(self.lib.calls_seen(), 2)

    def test_interrupted_tls_handshake_retries(self):
        self.assertEqual(self.lib.tls_io(2, 1), 2)


if __name__ == '__main__':
    unittest.main()
