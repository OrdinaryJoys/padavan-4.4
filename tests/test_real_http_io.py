"""Real local socket/OpenSSL tests for the firmware's client I/O functions."""
import ctypes
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

import test_httpd_regressions as common


class RealHttpIo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('openssl') or not shutil.which('pkg-config'):
            raise unittest.SkipTest('openssl and pkg-config development dependencies required')
        package = subprocess.run(['pkg-config', '--cflags', '--libs', 'openssl'], capture_output=True, text=True)
        if package.returncode:
            raise unittest.SkipTest('OpenSSL development headers/library required')
        flags = package.stdout.split()
        if Path('/opt/homebrew/opt/openssl@3/include/openssl/ssl.h').exists():
            flags = ['-I/opt/homebrew/opt/openssl@3/include', '-L/opt/homebrew/opt/openssl@3/lib', '-lssl', '-lcrypto']
        cls.tmp = tempfile.TemporaryDirectory(prefix='k2p-real-http-io-')
        cls.cert = Path(cls.tmp.name) / 'certificate.pem'
        cls.key = Path(cls.tmp.name) / 'key.pem'
        subprocess.run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-x509', '-sha256',
                        '-days', '1', '-subj', '/CN=localhost', '-keyout', str(cls.key), '-out', str(cls.cert)],
                       check=True, capture_output=True)
        directory = common.ROOT / 'trunk/user/httpd'
        tls = (directory / 'https.c').read_text()
        code = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/socket.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#define HTTP_HEADER_DEADLINE 2
#define HTTP_BODY_DEADLINE 5
#define HTTP_IO_TIMEOUT 3
#ifdef __APPLE__
typedef struct {ssize_t (*read)(void*,char*,size_t);ssize_t (*write)(void*,const char*,size_t);void *seek;int (*close)(void*);} cookie_io_functions_t;
struct cookie_bridge {void *cookie;cookie_io_functions_t io;};
static int bridge_read(void*p,char*b,int n){struct cookie_bridge*c=p;return c->io.read(c->cookie,b,n);}
static int bridge_write(void*p,const char*b,int n){struct cookie_bridge*c=p;return c->io.write(c->cookie,b,n);}
static int bridge_close(void*p){struct cookie_bridge*c=p;int r=c->io.close(c->cookie);free(c);return r;}
static FILE *portable_cookie(void*cookie,const char*mode,cookie_io_functions_t io){
 struct cookie_bridge *c=malloc(sizeof(*c));FILE*f;if(!c)return NULL;c->cookie=cookie;c->io=io;
 f=funopen(c,bridge_read,bridge_write,NULL,bridge_close);if(!f)free(c);return f;
}
#define fopencookie portable_cookie
#endif
'''
        code += '\n' + (directory / 'http_client_io.c').read_text().replace('#include "httpd.h"', '')
        code += r'''
typedef struct {SSL *ssl;int fd;} http_ssl_cookie_t;
static SSL_CTX *ssl_ctx;
static int debug_mode,write_waits,read_waits;
static int tls_wait(int fd,int writing){if(writing)write_waits++;else read_waits++;return http_request_wait(fd,writing);}
#define http_request_wait tls_wait
'''
        for name in ('ssl_interrupted', 'http_ssl_read', 'http_ssl_write', 'http_ssl_close'):
            code += '\n' + common.function(tls, name)
        start = tls.index('static const cookie_io_functions_t http_ssl_io')
        code += '\n' + tls[start:tls.index('};', start) + 2]
        code += '\n' + common.function(tls, 'ssl_server_fopen')
        httpd = (directory / 'httpd.c').read_text()
        prelude = common.PRELUDE.replace('static void http_request_allow_body(void){}', '')
        prelude = prelude.replace('static void try_pull_data(FILE*f,int n){}', '')
        prelude = prelude.replace('static void fake_input(const char*u,FILE*f,int n,char*b){input_calls++;}',
                                  'static void fake_input(const char*u,FILE*f,int n,char*b){while(n-->0 && fgetc(f)!=EOF){}input_calls++;}')
        code += '\n' + prelude
        code += '\n' + (directory / 'http_origin_guard.c').read_text().replace('#include "httpd.h"', '')
        for name in ('parse_content_length', 'parse_multipart_boundary', 'trim_header_value'):
            code += '\n' + common.function(httpd, name)
        if 'try_pull_data(' in httpd:
            code += '\n' + common.function(httpd, 'try_pull_data')
        code += '\n' + common.function(httpd, 'handle_request')
        code += r'''
#undef http_request_wait
int waits_for_write(void){return write_waits;}
int waits_for_read(void){return read_waits;}
int serve_plain_line(int fd){
 FILE *stream;char line[256];int result=-1;
 if(http_request_begin(fd)!=0){close(fd);return -1;}
 stream=http_client_fopen(fd);if(!stream){close(fd);return -1;}
 if(fgets(line,sizeof(line),stream) && strchr(line,'\n'))result=0;
 fclose(stream);return result;
}
int serve_plain_request(int fd){
 FILE *stream;conn_item_t peer={0};int result;
 if(http_request_begin(fd)!=0){close(fd);return -1;}
 stream=http_client_fopen(fd);if(!stream){close(fd);return -1;}
 auth_state=2;auth_valid=1;status_code=0;
 handle_request(stream,&peer);result=status_code;fclose(stream);return result;
}
int serve_plain_file(int fd){
 FILE *stream;char *payload;int result=-1;
 if(http_request_begin(fd)!=0){close(fd);return -1;}
 http_request_allow_body();stream=http_client_fopen(fd);if(!stream){close(fd);return -1;}
 payload=malloc(256*1024);if(!payload){fclose(stream);return -1;}memset(payload,'z',256*1024);
 if(fwrite(payload,1,256*1024,stream)==256*1024 && fflush(stream)==0)result=0;
 free(payload);fclose(stream);return result;
}
int serve_tls(int fd,const char *certificate,const char *key,int mode){
 FILE *stream=NULL;char input[256],output[1024];int result=-1,i;
 read_waits=write_waits=0;
 ssl_ctx=SSL_CTX_new(TLS_server_method());
 if(!ssl_ctx)goto done;
 if(SSL_CTX_use_certificate_file(ssl_ctx,certificate,SSL_FILETYPE_PEM)!=1 ||
    SSL_CTX_use_PrivateKey_file(ssl_ctx,key,SSL_FILETYPE_PEM)!=1 || http_request_begin(fd)!=0)goto done;
 stream=ssl_server_fopen(fd);if(!stream)goto done;
 if(mode==2){if(fgets(input,sizeof(input),stream) && strchr(input,'\n'))result=0;goto done;}
 if(fread(input,1,1,stream)!=1)goto done;
 http_request_allow_body();
 if(mode==1 && fread(input,1,4,stream)!=4)goto done;
 memset(output,'z',sizeof(output));
 for(i=0;i<256;i++)if(fwrite(output,1,sizeof(output),stream)!=sizeof(output))goto done;
 if(fflush(stream)!=0)goto done;
 result=0;
done:
 if(stream)fclose(stream);else close(fd);
 if(ssl_ctx)SSL_CTX_free(ssl_ctx);ssl_ctx=NULL;
 return result;
}
'''
        path = Path(cls.tmp.name) / 'real-io.c'
        library = Path(cls.tmp.name) / 'real-io.dylib'
        path.write_text(code)
        build = subprocess.run(['cc', '-shared', '-fPIC', '-O0', str(path), '-o', str(library), *flags], capture_output=True, text=True)
        if build.returncode:
            raise RuntimeError(build.stderr)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.serve_tls.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def start(self, tls=False, mode=0, request=False, plain_file=False):
        server, peer = socket.socketpair()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        result = []
        fd = server.detach()
        if tls:
            target = lambda: self.lib.serve_tls(fd, bytes(self.cert), bytes(self.key), mode)
        elif request:
            target = lambda: self.lib.serve_plain_request(fd)
        elif plain_file:
            target = lambda: self.lib.serve_plain_file(fd)
        else:
            target = lambda: self.lib.serve_plain_line(fd)
        worker = threading.Thread(target=lambda: result.append(target()), daemon=True)
        worker.start()
        return peer, worker, result

    def client(self, peer):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        peer.settimeout(6)
        return context.wrap_socket(peer, server_hostname='localhost')

    def test_continuous_plain_header_trickle_hits_total_deadline(self):
        peer, worker, result = self.start()
        started = time.monotonic()
        try:
            for _ in range(30):
                try:
                    peer.sendall(b'G')
                except OSError:
                    break
                time.sleep(0.1)
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result, [-1])
            self.assertLess(time.monotonic() - started, 3.2)
        finally:
            peer.close()
            worker.join(1)

    def test_real_tls_handshake_and_backpressured_file_transfer(self):
        peer, worker, result = self.start(tls=True)
        with self.client(peer) as client:
            client.sendall(b'R')
            time.sleep(0.2)
            data = bytearray()
            while len(data) < 256 * 1024:
                part = client.recv(65536)
                if not part:
                    break
                data.extend(part)
            self.assertEqual(data, b'z' * (256 * 1024))
        worker.join(1)
        self.assertEqual(result, [0])
        self.assertGreater(self.lib.waits_for_write(), 0)

    def test_completed_post_does_not_wait_for_extra_body_bytes(self):
        peer, worker, result = self.start(request=True)
        try:
            peer.sendall(b'POST /start_apply.htm HTTP/1.1\r\nHost: router\r\nX-K2P-Request: 1\r\nContent-Length: 4\r\n\r\nDATA')
            worker.join(1.5)
            self.assertFalse(worker.is_alive(), 'completed POST must dispatch before the peer closes')
            self.assertEqual(result, [200])
        finally:
            peer.close()
            worker.join(1)

    def test_plain_backpressured_file_transfer_is_complete(self):
        peer, worker, result = self.start(plain_file=True)
        peer.settimeout(6)
        try:
            time.sleep(0.2)
            data = bytearray()
            while len(data) < 256 * 1024:
                part = peer.recv(65536)
                if not part:
                    break
                data.extend(part)
            self.assertEqual(data, b'z' * (256 * 1024))
            worker.join(1)
            self.assertEqual(result, [0])
        finally:
            peer.close()
            worker.join(1)

    def test_authenticated_body_uses_separate_longer_budget(self):
        peer, worker, result = self.start(tls=True, mode=1)
        with self.client(peer) as client:
            client.sendall(b'R')
            for _ in range(4):
                time.sleep(0.6)
                client.sendall(b'b')
            count = 0
            while count < 256 * 1024:
                part = client.recv(65536)
                if not part:
                    break
                count += len(part)
            self.assertEqual(count, 256 * 1024)
        worker.join(1)
        self.assertEqual(result, [0])

    def test_continuous_tls_header_trickle_hits_total_deadline(self):
        peer, worker, result = self.start(tls=True, mode=2)
        with self.client(peer) as client:
            for _ in range(30):
                try:
                    client.sendall(b'G')
                except OSError:
                    break
                time.sleep(0.1)
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [-1])

    def test_fragmented_real_client_hello_cannot_extend_handshake_forever(self):
        peer, worker, result = self.start(tls=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        client = context.wrap_bio(incoming, outgoing, server_side=False, server_hostname='localhost')
        with self.assertRaises(ssl.SSLWantReadError):
            client.do_handshake()
        hello = outgoing.read()
        started = time.monotonic()
        try:
            for part in hello[:30]:
                try:
                    peer.sendall(bytes([part]))
                except OSError:
                    break
                time.sleep(0.1)
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result, [-1])
            self.assertLess(time.monotonic() - started, 3.2)
        finally:
            peer.close()
            worker.join(1)


if __name__ == '__main__':
    unittest.main()
