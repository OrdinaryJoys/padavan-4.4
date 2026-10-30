#!/usr/bin/env python3
"""Compile actual firmware functions with fake I/O backends; never touch a router.

K2P_TEST_BASELINE=<git ref> runs the same regression cases on an older revision.
"""
import ctypes
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
BASELINE = os.environ.get('K2P_TEST_BASELINE')

def source(path):
    if BASELINE:
        return subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE + ':' + path], text=True)
    return (ROOT / path).read_text()

def function(text, name):
    match = re.search(r'(?:static\s+)?(?:void|int|ssize_t|char\s*\*|FILE\s*\*)\s*\n?\b' + name + r'\s*\(', text)
    if not match:
        raise ValueError(name)
    start = match.start()
    opening = text.index('{', match.end())
    depth = 0
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*|[{}]')
    for item in token.finditer(text, opening):
        if item.group() == '{':
            depth += 1
        elif item.group() == '}':
            depth -= 1
            if not depth:
                return text[start:item.end()]
    raise ValueError(name)

PRELUDE = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <time.h>
#include <arpa/inet.h>
#include <sys/mman.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define UPLOAD_BUF_SIZE 1024
#define PROFILE_HEADER "HDR1"
#define PROFILE_HEADER_NEW "HDR2"
#define NVRAM_SPACE (0x10000-0x01000)
#define BOARD_PID "K2P"
#define FW_MTD_NAME "Firmware"
#define IH_MAGIC 0x27051956
#define O_BINARY 0
typedef struct {uint32_t ih_magic,ih_hcrc,ih_time,ih_size,ih_load,ih_ep,ih_dcrc; uint8_t ih_os,ih_arch,ih_type,ih_comp;uint8_t ih_name[32];} image_header_t;
static unsigned int get_mtd_size(const char*s){return 16*1024*1024;}
#define HTTP_METHOD_GET 1
#define HTTP_METHOD_HEAD 2
#define HTTP_METHOD_POST 3
typedef int (*check_header_t)(const char*,long*);
static int auth_state, auth_valid, action_calls, input_calls, status_code, auth_calls;
static int clear_calls, set_calls, fail_close, fail_write;
static FILE *output_file;
static int http_has_lang = 1;
typedef int uaddr;
typedef struct { int fd; int usa; } conn_item_t;
struct mime_handler { const char *pattern; const char *mime_type; const char *extra_header;
 void (*input)(const char*,FILE*,int,char*); void (*output)(const char*,FILE*); int need_auth; int (*prepare)(const char*); void (*cleanup)(void); };
static void fake_input(const char*u,FILE*f,int n,char*b){input_calls++;}
static void fake_output(const char*u,FILE*f){action_calls++;}
static struct mime_handler mime_handlers[]={{"*","text/html",NULL,fake_input,fake_output,1},{0}};
static void http_request_allow_body(void){}
static void do_cgi_clear(void){}
static void do_uncgi_query(char*q){}
static void do_file(const char*u,FILE*f){}
static void do_ej(const char*u,FILE*f){}
static void usockaddr_to_uaddr(const int*s,uaddr*d){*d=*s;}
static int http_login_check(const uaddr*i){return auth_state;}
static void http_login(const uaddr*i){}
static void http_logout(const uaddr*i){}
static int auth_check(const char*a){auth_calls++;return auth_valid;}
static int match(const char*p,const char*f){return 1;}
static int set_preferred_lang(char*s){return 1;}
static time_t tdate_parse(char*s){return 0;}
static int f_exists(const char*s){return 0;}
static void send_headers(int c,const char*t,const char*h,const char*m,const struct stat*s,FILE*f){status_code=c;}
static void send_error(int c,const char*t,const char*h,const char*m,FILE*f){status_code=c;}
static void send_authenticate(FILE*f){status_code=401;}
static void eat_post_data(FILE*f,int n){}
static void try_pull_data(FILE*f,int n){}
static void fwlog(const char*f,...){}
static void httpd_log(const char*f,...){}
static int is_sys_param(const char*s){return 1;}
static int nvram_clear(void){clear_calls++;return 0;}
static int nvram_set(const char*n,const char*v){set_calls++;return 0;}
static int nvram_unset(const char*n){return 0;}
static FILE *track_fopen(const char*n,const char*m){output_file=fopen(n,m);return output_file;}
static FILE *track_fdopen(int fd,const char*m){output_file=fdopen(fd,m);return output_file;}
static size_t track_fwrite(const void*b,size_t s,size_t n,FILE*f){
 if(f==output_file && fail_write) return 0;
 return fwrite(b,s,n,f);
}
static int track_fclose(FILE*f){int inject=(f==output_file && fail_close);int r=fclose(f);if(inject){errno=ENOSPC;return EOF;}return r;}
'''

class FirmwareRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        upload = source('trunk/user/httpd/upload.c')
        httpd = source('trunk/user/httpd/httpd.c')
        nvram = source('trunk/user/nvram/nvram.c')
        code = PRELUDE + source('trunk/user/httpd/crc32.c')
        guard = ROOT / 'trunk/user/httpd/http_origin_guard.c'
        if guard.exists():
            code += guard.read_text().replace('#include "httpd.h"', '')
        for name in ('parse_content_length', 'parse_multipart_boundary', 'trim_header_value'):
            if re.search(r'\b' + name + r'\s*\(', httpd):
                code += function(httpd, name)
        code += function(httpd, 'handle_request')
        code += function(upload, 'check_header_image') + function(upload, 'check_crc_image')
        code += '\n#define fopen track_fopen\n#define fdopen track_fdopen\n#define fwrite track_fwrite\n#define fclose track_fclose\n'
        names = ['check_header_nvram', 'check_header_bz2']
        if 'multipart_boundary_end(' in upload:
            names.append('multipart_boundary_end')
        names.append('do_upload_file')
        code += '\n'.join(function(upload, n) for n in names)
        code += '\n#undef fopen\n#undef fdopen\n#undef fwrite\n#undef fclose\n'
        code += function(nvram, 'nvram_restore')
        code += r'''
int run_auth(int state,int valid,int method){
 FILE *f=tmpfile(); conn_item_t item={0};
 auth_state=state;auth_valid=valid;action_calls=input_calls=status_code=auth_calls=0;
 fprintf(f,"%s /upgrade.cgi HTTP/1.1\r\nContent-Length: 0\r\nX-K2P-Request: 1\r\n\r\n",method?"POST":"GET");
 rewind(f);handle_request(f,&item);fclose(f);return status_code;
}
int actions(void){return action_calls;}
int inputs(void){return input_calls;}
int checks(void){return auth_calls;}
int run_upload(const char *body,int actual,int declared,int storage,const char *path,int close_fault,int write_fault){
 FILE *f=fmemopen((void*)body,actual,"rb");int r;
 fail_close=close_fault;fail_write=write_fault;output_file=NULL;
 r=do_upload_file(f,declared,storage?"\r\n--boundary":NULL,path,storage?"file_st":"file_nv",storage?check_header_bz2:check_header_nvram,storage?10:8);
 fclose(f);return r;
}
int run_restore(char*path){clear_calls=set_calls=0;return nvram_restore(path);}
int run_image_header(const char*header){long size=0;return check_header_image(header,&size);}
int run_image_crc(const char*path){return check_crc_image(path);}
int clears(void){return clear_calls;}
int sets(void){return set_calls;}
'''
        cfile = Path(cls.tmp.name) / 'regression.c'
        dylib = Path(cls.tmp.name) / 'regression.dylib'
        cfile.write_text(code)
        compiler = shutil.which('clang') or shutil.which('cc')
        subprocess.run([compiler, '-shared', '-fPIC', '-O0', '-g', '-Wno-incompatible-pointer-types', str(cfile), '-o', str(dylib)], check=True, capture_output=True)
        cls.lib = ctypes.CDLL(str(dylib))
        cls.lib.run_upload.argtypes = [ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_int]
        cls.lib.run_restore.argtypes = [ctypes.c_char_p]
        cls.lib.run_image_header.argtypes = [ctypes.c_char_p]
        cls.lib.run_image_crc.argtypes = [ctypes.c_char_p]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_other_peer_cannot_invoke_cgi(self):
        for method in (0, 1):
            with self.subTest(method=method):
                self.assertEqual(self.lib.run_auth(0,0,method),403)
                self.assertEqual(self.lib.actions(),0)
                self.assertEqual(self.lib.inputs(),0)

    def test_valid_current_peer_is_still_authenticated(self):
        self.assertEqual(self.lib.run_auth(3,1,1),200)
        self.assertEqual(self.lib.checks(),1)
        self.assertEqual(self.lib.actions(),1)

    def test_current_peer_bad_credentials_rejected(self):
        self.assertEqual(self.lib.run_auth(3,0,1),401)
        self.assertEqual(self.lib.actions(),0)

    def test_new_peer_requires_credentials(self):
        self.assertEqual(self.lib.run_auth(2,0,1),401)
        self.assertEqual(self.lib.actions(),0)

    def upload(self,payload,storage=False,declared=None,close_fault=0,write_fault=0):
        obj=b'file_st' if storage else b'file_nv'
        body=b'--boundary\r\nContent-Disposition: form-data; name="'+obj+b'"; filename="test"\r\n\r\n'+payload+b'\r\n--boundary--\r\n'
        path=Path(self.tmp.name)/'uploaded'
        result=self.lib.run_upload(body,len(body),len(body) if declared is None else declared,int(storage),os.fsencode(path),close_fault,write_fault)
        return result,path

    def test_profile_upload_preserves_header_and_full_payload(self):
        payload=b'HDR1'+struct.pack('<I',16)+b'name=value\0\0xxxx'
        self.assertEqual(len(payload),24)
        result,path=self.upload(payload)
        self.assertEqual(result,0)
        self.assertEqual(path.read_bytes(),payload)
        self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_truncated_profile_upload_rejected(self):
        result,path=self.upload(b'HDR1'+struct.pack('<I',5000)+b'short')
        self.assertNotEqual(result,0)
        self.assertFalse(path.exists())

    def test_failed_buffer_flush_rejects_upload(self):
        result,path=self.upload(b'HDR1'+struct.pack('<I',4)+b'a=b\0',close_fault=1)
        self.assertNotEqual(result,0)
        self.assertFalse(path.exists())

    def test_short_write_rejects_upload(self):
        result,path=self.upload(b'HDR1'+struct.pack('<I',4)+b'a=b\0',write_fault=1)
        self.assertNotEqual(result,0)
        self.assertFalse(path.exists())

    def test_declared_body_longer_than_received_rejected(self):
        result,path=self.upload(b'HDR1'+struct.pack('<I',4)+b'a=b\0',declared=5000)
        self.assertNotEqual(result,0)
        self.assertFalse(path.exists())

    def test_storage_boundary_crossing_buffer_preserves_bytes(self):
        for amount in (1010,1011,1012,1013,1014,1015,1016,1017,1020,1023,1024,1025,2047):
            with self.subTest(amount=amount):
                payload=b'BZh9\x31\x41\x59\x26\x53\x59'+b'x'*amount
                result,path=self.upload(payload,True)
                self.assertEqual(result,0)
                self.assertEqual(path.read_bytes(),payload)

    def restore(self,payload):
        path=Path(self.tmp.name)/'restore.prf'
        path.write_bytes(payload)
        result=self.lib.run_restore(os.fsencode(path))
        return result

    def test_restore_valid_legacy_profile(self):
        body=b'name=value\0\0'
        self.assertEqual(self.restore(b'HDR1'+struct.pack('<I',len(body))+body),0)
        self.assertEqual(self.lib.clears(),1)
        self.assertEqual(self.lib.sets(),1)

    def test_restore_valid_encoded_profile(self):
        body=b'name=value\0\0'
        encoded=bytes(0xfd if b==0 else 0xff-b for b in body)
        self.assertEqual(self.restore(b'HDR2'+struct.pack('<I',len(body))+encoded),0)
        self.assertEqual(self.lib.clears(),1)
        self.assertEqual(self.lib.sets(),1)

    def test_restore_malformed_payloads_never_clear_live_config(self):
        cases=[b'',b'HDR1',b'HDR1'+struct.pack('<I',0),b'HDR1'+struct.pack('<I',65537),b'HDR1'+struct.pack('<I',50)+b'a=b\0\0',b'HDR1'+struct.pack('<I',4)+b'a=bc',b'HDR1'+struct.pack('<I',4)+b'ab\0\0',b'HDR1'+struct.pack('<I',5)+b'=bad\0']
        for body in cases:
            with self.subTest(body=body[:8]):
                self.assertNotEqual(self.restore(body),0)
                self.assertEqual(self.lib.clears(),0)
                self.assertEqual(self.lib.sets(),0)

    def test_restore_exact_capacity_and_over_capacity(self):
        capacity=0x10000-0x1000
        self.assertEqual(self.restore(b'HDR1'+struct.pack('<I',capacity)+bytes(capacity)),0)
        self.assertNotEqual(self.restore(b'HDR1'+struct.pack('<I',capacity+1)+bytes(capacity+1)),0)
        self.assertEqual(self.lib.clears(),0)

    def image(self,tail=b'',declared=None,corrupt=False):
        body=bytes(2*1024*1024)
        header=bytearray(struct.pack('>7I4B32s',0x27051956,0,0,len(body) if declared is None else declared,0,0,zlib.crc32(body),5,5,2,0,b'ver K2P'))
        header[4:8]=struct.pack('>I',zlib.crc32(header))
        if corrupt: body=b'x'+body[1:]
        path=Path(self.tmp.name)/'image.trx'
        path.write_bytes(header+body+tail)
        return header,path

    def test_image_valid_crc(self):
        header,path=self.image()
        self.assertEqual(self.lib.run_image_header(bytes(header)),0)
        self.assertEqual(self.lib.run_image_crc(os.fsencode(path)),0)

    def test_image_crc_rejects_extra_bytes(self):
        header,path=self.image(tail=b'unchecked trailer')
        self.assertNotEqual(self.lib.run_image_crc(os.fsencode(path)),0)

    def test_image_crc_rejects_corrupt_body(self):
        header,path=self.image(corrupt=True)
        self.assertNotEqual(self.lib.run_image_crc(os.fsencode(path)),0)

    def test_image_header_rejects_wrapping_size(self):
        header,path=self.image(declared=0xfffffff0)
        self.assertNotEqual(self.lib.run_image_header(bytes(header)),0)

if __name__ == '__main__':
    unittest.main()
