import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_httpd_regressions as common


class RequestGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='k2p-request-guards-')
        directory = common.ROOT / 'trunk/user/httpd'
        httpd = (directory / 'httpd.c').read_text()
        prelude = common.PRELUDE.replace('static void http_logout(const uaddr*i){}', 'static int logout_calls; static void http_logout(const uaddr*i){logout_calls++;}')
        code = prelude + '\n' + (directory / 'http_origin_guard.c').read_text().replace('#include "httpd.h"', '')
        for name in ('parse_content_length', 'parse_multipart_boundary', 'trim_header_value', 'handle_request'):
            code += '\n' + common.function(httpd, name)
        code += r'''
static int prepare_code,prepare_calls,cleanup_calls,status_before_prepare;
static int prepare_download(const char *url){prepare_calls++;status_before_prepare=status_code;return prepare_code;}
static void cleanup_download(void){cleanup_calls++;}
int request(const char *method,const char *path,const char *headers,int state,int valid,int preparation){
 FILE *stream=tmpfile();conn_item_t peer={0};
 auth_state=state;auth_valid=valid;status_code=action_calls=input_calls=prepare_calls=cleanup_calls=logout_calls=0;status_before_prepare=-1;
 prepare_code=preparation;
 mime_handlers[0].prepare=preparation>=0?prepare_download:NULL;
 mime_handlers[0].cleanup=preparation>=0?cleanup_download:NULL;
 fprintf(stream,"%s %s HTTP/1.1\r\n%s\r\n",method,path,headers);
 rewind(stream);handle_request(stream,&peer);fclose(stream);return status_code;
}
int outputs_seen(void){return action_calls;}
int logouts_seen(void){return logout_calls;}
int preparations_seen(void){return prepare_calls;}
int cleanups_seen(void){return cleanup_calls;}
int status_before_preparation(void){return status_before_prepare;}
'''
        path = Path(cls.tmp.name) / 'guards.c'
        library = Path(cls.tmp.name) / 'guards.dylib'
        path.write_text(code)
        result = subprocess.run(['cc', '-shared', '-fPIC', '-O0', str(path), '-o', str(library)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.http_same_origin.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        cls.lib.request.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def request(self, method='GET', path='/index.asp', headers='Host: router\r\n', state=3, valid=1, prepare=-1):
        return self.lib.request(method.encode(), path.encode(), headers.encode(), state, valid, prepare)

    def test_default_ports_and_ipv6_are_compared_as_origins(self):
        for source, host, secure in (
            ('http://ROUTER', 'router:80', 0), ('https://router:443', 'router', 1),
            ('http://[::1]', '[0:0:0:0:0:0:0:1]:80', 0),
            ('https://[2001:db8::1]:443', '[2001:0db8::1]', 1),
            ('http://r.pontoon.fit:2233', 'r.pontoon.fit:2233', 0)):
            with self.subTest(source=source, host=host):
                self.assertEqual(self.lib.http_same_origin(source.encode(), host.encode(), secure, 0), 1)

    def test_origin_prefix_userinfo_scheme_and_bad_ports_are_rejected(self):
        for source in ('http://router.evil', 'http://router@evil', 'https://router',
                       'http://router:81', 'http://router:4294967376', 'http://router:0',
                       'http://router/path', 'null', 'http://[::1]evil'):
            with self.subTest(source=source):
                self.assertEqual(self.lib.http_same_origin(source.encode(), b'router', 0, 0), 0)

    def test_referer_path_does_not_change_its_origin(self):
        self.assertEqual(self.lib.http_same_origin(b'http://router:80/page?arg=x', b'router', 0, 1), 1)
        self.assertEqual(self.lib.http_same_origin(b'http://router.evil/page', b'router', 0, 1), 0)

    def test_headerless_cli_write_requires_explicit_non_simple_header(self):
        self.assertEqual(self.request('POST', '/start_apply.htm'), 403)
        self.assertEqual(self.request('POST', '/start_apply.htm', 'Host: router\r\nX-K2P-Request: 1\r\n'), 200)

    def test_existing_same_origin_browser_form_is_accepted(self):
        self.assertEqual(self.request('POST', '/start_apply.htm', 'Host: router\r\nOrigin: http://router\r\n'), 200)
        self.assertEqual(self.request('POST', '/upgrade.cgi', 'Host: router\r\nReferer: http://router/Advanced_FirmwareUpgrade_Content.asp\r\n'), 200)

    def test_cross_site_request_is_rejected_even_with_explicit_header(self):
        headers = 'Host: router\r\nOrigin: http://evil\r\nX-K2P-Request: 1\r\n'
        self.assertEqual(self.request('POST', '/apply.cgi', headers), 403)
        self.assertEqual(self.lib.outputs_seen(), 0)

    def test_fetch_metadata_is_checked_when_referrer_is_suppressed(self):
        self.assertEqual(self.request('GET', '/upgrade.cgi', 'Host: router\r\nSec-Fetch-Site: cross-site\r\n'), 403)
        self.assertEqual(self.request('POST', '/apply.cgi', 'Host: router\r\nSec-Fetch-Site: same-origin\r\n'), 200)
        self.assertEqual(self.request('POST', '/apply.cgi', 'Host: router\r\nSec-Fetch-Site: same-site\r\n'), 403)

    def test_get_state_changes_are_protected(self):
        for path in ('/apply.cgi?action_mode=Reboot', '/upgrade.cgi', '/restore_nv.cgi',
                     '/restore_st.cgi', '/start_apply.htm', '/Logout.asp', '/logout'):
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path), 403)
                self.assertEqual(self.lib.outputs_seen(), 0)

    def test_read_only_get_queries_and_head_do_not_require_write_proof(self):
        self.assertEqual(self.request('GET', '/update.cgi?output=netdev&_=123'), 200)
        self.assertEqual(self.request('GET', '/update.cgi?output=uptime'), 200)
        self.assertEqual(self.request('HEAD', '/upgrade.cgi'), 200)
        self.assertEqual(self.lib.outputs_seen(), 0)

    def test_read_only_rpc_rejects_explicit_cross_origin_browser_context(self):
        for fields in ('Origin: http://evil\r\n', 'Referer: http://evil/page\r\n',
                       'Sec-Fetch-Site: cross-site\r\n'):
            with self.subTest(fields=fields):
                self.assertEqual(self.request('GET', '/update.cgi?output=nvram', 'Host: router\r\n' + fields), 403)
                self.assertEqual(self.lib.outputs_seen(), 0)

    def test_read_only_rpc_keeps_same_origin_browser_and_cli_queries(self):
        self.assertEqual(self.request('GET', '/update.cgi?output=nvram'), 200)
        self.assertEqual(self.request('GET', '/update.cgi?output=netdev', 'Host: router\r\nReferer: http://router/status.asp\r\n'), 200)

    def test_rpc_write_calls_and_mixed_action_parameters_require_proof(self):
        for query in ('output=update_variables', 'output=asus_nvram_commit',
                      'output=netdev&action_script=reboot', 'output=netdev&action_mode=Apply',
                      'output=netdev&output=asus_nvram_commit', 'output=n%65tdev',
                      'output=nvram_dump&arg0=x&arg1=dlna_rescan',
                      'output=bandwidth&arg0=history&arg1=evil', 'output=detect_internet'):
            with self.subTest(query=query):
                self.assertEqual(self.request('GET', '/update.cgi?' + query), 403)

    def test_head_logout_has_no_session_side_effect(self):
        fields = 'Host: router\r\nOrigin: http://evil\r\nSec-Fetch-Site: cross-site\r\n'
        self.assertEqual(self.request('HEAD', '/Logout.asp', fields), 200)
        self.assertEqual(self.lib.outputs_seen(), 0)
        self.assertEqual(self.lib.logouts_seen(), 0)

    def test_stateful_rpc_queries_reject_cross_site_proof(self):
        fields = 'Host: router\r\nOrigin: http://evil\r\nSec-Fetch-Site: cross-site\r\n'
        for query in ('output=nvram_dump&arg0=x&arg1=dlna_rescan',
                      'output=bandwidth&arg0=history&arg1=evil', 'output=detect_internet'):
            with self.subTest(query=query):
                self.assertEqual(self.request('GET', '/update.cgi?' + query, fields), 403)
                self.assertEqual(self.lib.outputs_seen(), 0)

    def test_cross_peer_and_bad_credentials_still_fail(self):
        fields = 'Host: router\r\nX-K2P-Request: 1\r\n'
        self.assertEqual(self.request('POST', '/upgrade.cgi', fields, state=0), 403)
        self.assertEqual(self.request('POST', '/upgrade.cgi', fields, state=2, valid=0), 401)
        self.assertEqual(self.request('POST', '/upgrade.cgi', fields, state=2, valid=1), 200)

    def test_failed_backup_returns_500_before_any_200_or_file_data(self):
        for method in ('GET', 'HEAD'):
            with self.subTest(method=method):
                self.assertEqual(self.request(method, '/Storage_test.TBZ', prepare=500), 500)
                self.assertEqual(self.lib.status_before_preparation(), 0)
                self.assertEqual(self.lib.outputs_seen(), 0)
                self.assertEqual(self.lib.cleanups_seen(), 1)

    def test_successful_head_prepares_and_cleans_without_sending_backup(self):
        self.assertEqual(self.request('HEAD', '/Settings_test.CFG', prepare=0), 200)
        self.assertEqual(self.lib.preparations_seen(), 1)
        self.assertEqual(self.lib.outputs_seen(), 0)
        self.assertEqual(self.lib.cleanups_seen(), 1)

    def test_successful_get_prepares_before_headers_and_cleans_after_data(self):
        self.assertEqual(self.request('GET', '/Storage_test.TBZ', prepare=0), 200)
        self.assertEqual(self.lib.status_before_preparation(), 0)
        self.assertEqual(self.lib.outputs_seen(), 1)
        self.assertEqual(self.lib.cleanups_seen(), 1)

    def test_production_backup_routes_use_prepare_and_cleanup(self):
        source = (common.ROOT / 'trunk/user/httpd/web_ex.c').read_text()
        self.assertIn('do_nvram_file, 1, prepare_nvram_download, cleanup_nvram_download', source)
        self.assertIn('do_storage_file, 1, prepare_storage_download, cleanup_storage_download', source)

    def test_incomplete_headers_do_not_dispatch_a_request(self):
        self.assertEqual(self.request(headers='Host: router'), 400)
        self.assertEqual(self.lib.outputs_seen(), 0)

    def test_overlong_header_cannot_truncate_origin_into_a_trusted_prefix(self):
        self.assertEqual(self.request(headers='Host: router\r\nOrigin: http://router' + 'x' * 5000 + '\r\n'), 400)
        self.assertEqual(self.lib.outputs_seen(), 0)


if __name__ == '__main__':
    unittest.main()
