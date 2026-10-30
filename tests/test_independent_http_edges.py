#!/usr/bin/env python3
"""Additional current-source HTTP/restore regressions; no router is contacted.

K2P_INDEPENDENT_SNAPSHOT points to pre-extra-fixes C snapshots for negative
controls. Socket tests use a local socketpair and a one-second test timeout.
"""
import ctypes
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest

import test_httpd_regressions as common


def current_source(path):
    snapshot = os.environ.get('K2P_INDEPENDENT_SNAPSHOT')
    if snapshot:
        return (Path(snapshot) / (Path(path).stem + '.pre-extra-fixes.c')).read_text()
    return common.source(path)


class IndependentHttpEdges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='k2p-independent-http-')
        httpd = current_source('trunk/user/httpd/httpd.c')
        upload = current_source('trunk/user/httpd/upload.c')
        nvram = current_source('trunk/user/nvram/nvram.c')
        web = current_source('trunk/user/httpd/web_ex.c')
        prelude = common.PRELUDE.replace(
            'static void fake_input(const char*u,FILE*f,int n,char*b){input_calls++;}',
            'static void fake_input(const char*u,FILE*f,int n,char*b){input_calls++; captured_length=n; snprintf(captured_boundary,sizeof(captured_boundary),"%s",b?b:"");}')
        prelude = prelude.replace('clear_calls++;return 0;', 'clear_calls++;return clear_fault?-1:0;')
        prelude = prelude.replace('set_calls++;return 0;', 'set_calls++;return set_fault?-1:0;')
        prelude = prelude.replace('static void do_file(const char*u,FILE*f){}',
                                  'static void do_file(const char*u,FILE*f){download_calls++;}')
        prelude = prelude.replace('static int f_exists(const char*s){return 0;}',
                                  'static int f_exists(const char*s){return file_exists_value;}')
        code = 'static int captured_length,clear_fault,set_fault,file_exists_value,download_calls,save_read_fault;\nstatic char captured_boundary[128];\n' + prelude
        code += r'''
#include <sys/socket.h>
#include <sys/time.h>
#define HTTP_IO_TIMEOUT 1
static int option_calls, option_eintr;
static int timed_setsockopt(int fd,int level,int option,const void *value,socklen_t size){
 option_calls++;
 if(option_eintr){option_eintr=0;errno=EINTR;return -1;}
 return setsockopt(fd,level,option,value,size);
}
#define setsockopt timed_setsockopt
'''
        if 'set_client_timeouts(' in httpd:
            code += common.function(httpd, 'set_client_timeouts')
        else:
            code += 'static int set_client_timeouts(int fd){return -1;}\n'
        code += '\n#undef setsockopt\n'
        for name in ('parse_content_length', 'parse_multipart_boundary', 'trim_header_value'):
            if name + '(' in httpd:
                code += common.function(httpd, name)
        guard = common.ROOT / 'trunk/user/httpd/http_origin_guard.c'
        if guard.exists():
            code += '\n' + guard.read_text().replace('#include "httpd.h"', '')
        code += common.function(httpd, 'handle_request')
        for name in ('check_header_nvram', 'check_header_bz2', 'multipart_boundary_end', 'do_upload_file'):
            if name + '(' in upload:
                code += common.function(upload, name)
        code += common.function(nvram, 'nvram_restore')
        code += r'''
static unsigned char get_rand(void){return 0;}
static int nvram_getall(char *buf,int size,int temporary){
 if(save_read_fault)return -1;
 memcpy(buf,"name=value\0\0",12);return 0;
}
#define fopen track_fopen
#define fdopen track_fdopen
#define fwrite track_fwrite
#define fclose track_fclose
'''
        code += common.function(nvram, 'nvram_save')
        code += '\n#undef fopen\n#undef fdopen\n#undef fwrite\n#undef fclose\n'
        code += r'''
static int safe_login,valid_login,restore_result,commit_result,reboot_calls,watchdog_starts,commit_calls;
static char applied_page[64];
#define PROFILE_FIFO_UPLOAD "unused-test-profile"
#define PROFILE_FIFO_DOWNLOAD "unused-test-download"
#define STORAGE_FIFO_FILENAME "unused-test-storage"
static int get_login_safe(void){return safe_login;}
static int get_login_valid(void){return valid_login;}
static int doSystem(const char *format,...){return 0;}
static int eval(const char *command,...){
 if(!strcmp(command,"/sbin/watchdog")){watchdog_starts++;return 0;}
 return restore_result;
}
static int nvram_commit(void){commit_calls++;return commit_result;}
static unsigned int skip_sleep(unsigned int seconds){return 0;}
static int skip_unlink(const char *name){return 0;}
static void websApply(FILE *stream,const char *page){snprintf(applied_page,sizeof(applied_page),"%s",page);}
static void sys_reboot(void){reboot_calls++;}
#define sleep skip_sleep
#define unlink skip_unlink
'''
        code += common.function(web, 'do_restore_nv_cgi')
        code += common.function(web, 'do_restore_st_cgi')
        preflight = 'prepare_nvram_download(' in web
        code += 'static int backup_stat(const char *path,struct stat *info){memset(info,0,sizeof(*info));info->st_mode=S_IFREG|0600;info->st_size=10;return 0;}\n#define stat(path,info) backup_stat(path,info)\n'
        if preflight:
            for name in ('cleanup_nvram_download', 'prepare_nvram_download', 'cleanup_storage_download', 'prepare_storage_download'):
                code += common.function(web, name)
        code += '\n#undef stat\n'
        code += common.function(web, 'do_nvram_file')
        code += common.function(web, 'do_storage_file')
        download_preflight = 'if(storage){if(prepare_storage_download("Storage_test.TBZ")!=0)return 0;}else if(prepare_nvram_download("Settings_test.CFG")!=0)return 0;' if preflight else ''
        code += r'''
#undef sleep
#undef unlink
int headers(const char *fields){
 FILE *stream=tmpfile();conn_item_t item={0};
 auth_state=2;auth_valid=1;input_calls=action_calls=status_code=0;captured_length=-1;captured_boundary[0]=0;
 fprintf(stream,"POST /restore_st.cgi HTTP/1.1\r\nX-K2P-Request: 1\r\n%s\r\n",fields);
 rewind(stream);handle_request(stream,&item);fclose(stream);return status_code;
}
int length_seen(void){return captured_length;}
const char *boundary_seen(void){return captured_boundary;}
int timeout_socket(int fd,int interrupted){option_calls=0;option_eintr=interrupted;return set_client_timeouts(fd);}
int timeout_option_calls(void){return option_calls;}
int socket_request(int fd){FILE *stream=fdopen(fd,"r+");conn_item_t item={0};auth_state=2;auth_valid=1;status_code=0;handle_request(stream,&item);fclose(stream);return status_code;}
int socket_status(void){return status_code;}
int backend_restore(const char *path,int fail_clear,int fail_set){clear_fault=fail_clear;set_fault=fail_set;clear_calls=set_calls=0;return nvram_restore((char*)path);}
int backend_sets(void){return set_calls;}
int backend_clears(void){return clear_calls;}
int backend_save(const char *path,int read_fault,int write_fault,int close_fault){save_read_fault=read_fault;fail_write=write_fault;fail_close=close_fault;output_file=NULL;return nvram_save((char*)path);}
int cgi_restore(int storage,int exists,int safe,int valid,int command_result,int flash_result){
 FILE *stream=tmpfile();file_exists_value=exists;safe_login=safe;valid_login=valid;restore_result=command_result;commit_result=flash_result;
 reboot_calls=watchdog_starts=commit_calls=0;applied_page[0]=0;
 if(storage)do_restore_st_cgi("restore_st.cgi",stream);else do_restore_nv_cgi("restore_nv.cgi",stream);
 fclose(stream);return reboot_calls;
}
const char *page_seen(void){return applied_page;}
int commits_seen(void){return commit_calls;}
int watchdog_restarts(void){return watchdog_starts;}
int download_backup(int storage,int command_result){FILE *stream=tmpfile();safe_login=1;restore_result=command_result;download_calls=0;
 if(storage)do_storage_file("Storage_test.TBZ",stream);else do_nvram_file("Settings_test.CFG",stream);
 fclose(stream);return download_calls;}
int storage_upload(const char *data,int size,const char *marker,const char *path){
 FILE *stream=fmemopen((void*)data,size,"rb");int result;
 result=do_upload_file(stream,size,(char*)marker,path,"file_st",check_header_bz2,10);fclose(stream);return result;
}
'''
        code = code.replace('safe_login=1;restore_result=command_result;download_calls=0;', 'safe_login=1;restore_result=command_result;download_calls=0;' + download_preflight)
        source = Path(cls.tmp.name) / 'http-edges.c'
        library = Path(cls.tmp.name) / 'http-edges.dylib'
        source.write_text(code)
        result = subprocess.run(['cc', '-shared', '-fPIC', '-O0', '-g', str(source), '-o', str(library)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.headers.argtypes = [ctypes.c_char_p]
        cls.lib.boundary_seen.restype = ctypes.c_char_p
        cls.lib.page_seen.restype = ctypes.c_char_p
        cls.lib.backend_restore.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        cls.lib.backend_save.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        cls.lib.storage_upload.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_content_length_rejects_invalid_syntax_and_overflow(self):
        for value in ('-4294967295', '-1', '+1', '0x10', '12junk', '', '1,1', '1 2', '50000001', '999999999999999999999'):
            with self.subTest(value=value):
                self.assertEqual(self.lib.headers(('Content-Length: ' + value + '\r\n').encode()), 400)
                self.assertEqual(self.lib.length_seen(), -1)

    def test_content_length_decimal_leading_zeroes(self):
        self.assertEqual(self.lib.headers(b'Content-Length: 010\r\n'), 200)
        self.assertEqual(self.lib.length_seen(), 10)

    def test_equal_duplicate_lengths_are_accepted(self):
        self.assertEqual(self.lib.headers(b'Content-Length: 5\r\nContent-Length: 5\r\n'), 200)
        self.assertEqual(self.lib.length_seen(), 5)

    def test_conflicting_duplicate_lengths_are_rejected(self):
        self.assertEqual(self.lib.headers(b'Content-Length: 5\r\nContent-Length: 6\r\n'), 400)

    def test_quoted_boundary_and_following_parameter(self):
        fields = b'Content-Type: multipart/form-data; boundary="boundary"; charset=UTF-8\r\nContent-Length: 1\r\n'
        self.assertEqual(self.lib.headers(fields), 200)
        self.assertEqual(self.lib.boundary_seen(), b'boundary')

    def test_boundary_parameter_name_is_case_insensitive(self):
        self.lib.headers(b'Content-Type: multipart/form-data; BOUNDARY = boundary\r\n')
        self.assertEqual(self.lib.boundary_seen(), b'boundary')

    def test_marker_prefix_inside_file_is_not_a_delimiter(self):
        for amount in (0, 1000, 1010, 1015, 1023, 2048):
            with self.subTest(amount=amount):
                payload = b'BZh9\x31\x41\x59\x26\x53\x59' + b'x' * amount + b'\r\n--boundaryXstill-file-data'
                body = b'--boundary\r\nContent-Disposition: form-data; name="file_st"\r\n\r\n' + payload + b'\r\n--boundary--\r\n'
                path = Path(self.tmp.name) / 'storage-upload'
                self.assertEqual(self.lib.storage_upload(body, len(body), b'\r\n--boundary', os.fsencode(path)), 0)
                self.assertEqual(path.read_bytes(), payload)

    def test_nvram_clear_failure_is_reported_before_any_set(self):
        payload = b'name=value\0\0'
        path = Path(self.tmp.name) / 'profile'
        path.write_bytes(b'HDR1' + struct.pack('<I', len(payload)) + payload)
        self.assertNotEqual(self.lib.backend_restore(os.fsencode(path), 1, 0), 0)
        self.assertEqual(self.lib.backend_sets(), 0)

    def test_nvram_set_failure_does_not_report_success(self):
        payload = b'first=value\0second=value\0\0'
        path = Path(self.tmp.name) / 'profile'
        path.write_bytes(b'HDR1' + struct.pack('<I', len(payload)) + payload)
        self.assertNotEqual(self.lib.backend_restore(os.fsencode(path), 0, 1), 0)
        self.assertEqual(self.lib.backend_sets(), 1)

    def test_backup_read_or_write_failure_preserves_previous_copy(self):
        for read_fault, write_fault, close_fault in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            with self.subTest(read=read_fault, write=write_fault, close=close_fault):
                path = Path(self.tmp.name) / 'saved-profile'
                path.write_bytes(b'previous-good-backup')
                self.assertNotEqual(self.lib.backend_save(os.fsencode(path), read_fault, write_fault, close_fault), 0)
                self.assertEqual(path.read_bytes(), b'previous-good-backup')
                self.assertEqual(list(path.parent.glob(path.name + '.new.*')), [])

    def test_successful_backup_still_restores_original_format(self):
        path = Path(self.tmp.name) / 'saved-profile'
        self.assertEqual(self.lib.backend_save(os.fsencode(path), 0, 0, 0), 0)
        self.assertEqual(path.read_bytes()[:4], b'HDR2')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.lib.backend_restore(os.fsencode(path), 0, 0), 0)
        self.assertEqual(self.lib.backend_sets(), 1)

    def test_failed_backups_are_not_downloaded(self):
        for storage in (0, 1):
            with self.subTest(storage=storage):
                self.assertEqual(self.lib.download_backup(storage, 1), 0)

    def test_successful_backups_are_still_downloaded(self):
        for storage in (0, 1):
            with self.subTest(storage=storage):
                self.assertEqual(self.lib.download_backup(storage, 0), 1)

    def test_commit_failure_does_not_reboot_or_show_success(self):
        self.assertEqual(self.lib.cgi_restore(0, 1, 1, 0, 0, -1), 0)
        self.assertEqual(self.lib.page_seen(), b'UploadError.asp')
        self.assertEqual(self.lib.watchdog_restarts(), 1)

    def test_restore_failure_does_not_commit_or_reboot(self):
        self.assertEqual(self.lib.cgi_restore(0, 1, 1, 0, 1, 0), 0)
        self.assertEqual(self.lib.commits_seen(), 0)
        self.assertEqual(self.lib.page_seen(), b'UploadError.asp')

    def test_successful_restore_still_commits_and_reboots(self):
        self.assertEqual(self.lib.cgi_restore(0, 1, 1, 0, 0, 0), 1)
        self.assertEqual(self.lib.commits_seen(), 1)
        self.assertEqual(self.lib.page_seen(), b'Uploading.asp')

    def test_storage_command_failure_is_not_success(self):
        self.lib.cgi_restore(1, 1, 1, 0, 1, 0)
        self.assertEqual(self.lib.page_seen(), b'UploadError.asp')

    def test_no_authenticated_session_cannot_restore(self):
        self.assertEqual(self.lib.cgi_restore(0, 1, 0, 0, 0, 0), 0)
        self.assertEqual(self.lib.commits_seen(), 0)

    def test_socket_timeout_setup_failure_is_reported(self):
        self.assertNotEqual(self.lib.timeout_socket(-1, 0), 0)
        self.assertEqual(self.lib.timeout_option_calls(), 1)

    def test_incomplete_first_line_times_out_on_local_socket(self):
        reader, writer = socket.socketpair()
        worker = None
        try:
            fd = os.dup(reader.fileno())
            self.assertEqual(self.lib.timeout_socket(fd, 1), 0)
            self.assertEqual(self.lib.timeout_option_calls(), 3)
            worker = threading.Thread(target=self.lib.socket_request, args=(fd,), daemon=True)
            worker.start()
            writer.sendall(b'G')
            worker.join(2.5)
            blocked = worker.is_alive()
            self.assertFalse(blocked, 'an incomplete unauthenticated line must not block forever')
        finally:
            writer.close()
            reader.close()
            if worker:
                worker.join(1)

    def test_progressing_request_can_outlast_idle_timeout(self):
        reader, writer = socket.socketpair()
        worker = None
        try:
            fd = os.dup(reader.fileno())
            self.assertEqual(self.lib.timeout_socket(fd, 0), 0)
            worker = threading.Thread(target=self.lib.socket_request, args=(fd,), daemon=True)
            worker.start()
            for part in (b'GET /', b'index.asp HTTP/1.1\r\n', b'Content-Length: 0\r\n', b'\r\n'):
                writer.sendall(part)
                if part != b'\r\n':
                    time.sleep(0.4)
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(self.lib.socket_status(), 200)
        finally:
            writer.close()
            reader.close()
            if worker:
                worker.join(1)


if __name__ == '__main__':
    unittest.main()
