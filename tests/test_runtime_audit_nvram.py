#!/usr/bin/env python3
"""Compile the real NVRAM open/ioctl handlers with counted privilege backends.

Only native temporary binaries run. No device, flash, or user configuration IO.
K2P_TEST_BASELINE=<ref> also exercises the previous source revision.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_httpd_regressions import ROOT, source


def handler(text, name):
    start = re.search(r'static\s+(?:int|long)\s+' + name + r'\s*\(', text).start()
    opening = text.index('{', start)
    depth = 0
    tokens = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*|[{}]')
    for item in tokens.finditer(text, opening):
        if item.group() == '{':
            depth += 1
        elif item.group() == '}':
            depth -= 1
            if not depth:
                return text[start:item.end()]
    raise ValueError(name)


class RuntimeNVRAMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        candidates = list(ROOT.glob('trunk/linux-*.x/drivers/nvram/nvram_linux.c'))
        if len(candidates) != 1:
            raise AssertionError('Expected exactly one active kernel NVRAM driver')
        cls.text = source(str(candidates[0].relative_to(ROOT)))
        header = source(str(candidates[0].parents[2].relative_to(ROOT)/'include/nvram/bcmnvram.h'))
        code = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#define CAP_SYS_ADMIN 21
#define THIS_MODULE ((void *)0)
#define __user
struct file { int f_mode; };
struct inode { int unused; };
typedef struct { int unused; } anvram_ioctl_t;
static int has_capability, privilege_checks, backend_calls, user_accesses;
static int module_gets, module_puts;
static int capable(int cap) {assert(cap==CAP_SYS_ADMIN);privilege_checks++;return has_capability;}
static int nvram_commit(void) {assert(has_capability);backend_calls++;return 101;}
static int nvram_clear(void) {assert(has_capability);backend_calls++;return 102;}
static int user_nvram_set(anvram_ioctl_t *p) {
    assert(has_capability && p==(void *)0x1234);backend_calls++;user_accesses++;return 103;
}
static int user_nvram_get(anvram_ioctl_t *p) {
    assert(has_capability && p==(void *)0x1234);backend_calls++;user_accesses++;return 104;
}
static int try_module_get(void *p){module_gets++;return 1;}
static void module_put(void *p){module_puts++;}
'''
        definitions = re.findall(r'^#define\s+(NVRAM_IOCTL_\w+)\s+([^\n]+)', header, re.M)
        code += ''.join('#define '+key+' '+value+'\n' for key, value in definitions)
        for name in ('dev_nvram_ioctl', 'dev_nvram_open', 'dev_nvram_release'):
            code += handler(cls.text, name) + '\n'
        code += r'''
static unsigned int operation(const char *s) {
    if(!strcmp(s,"commit"))return NVRAM_IOCTL_COMMIT;
    if(!strcmp(s,"clear"))return NVRAM_IOCTL_CLEAR;
    if(!strcmp(s,"set"))return NVRAM_IOCTL_SET;
    if(!strcmp(s,"get"))return NVRAM_IOCTL_GET;
    return 0xdead;
}
int main(int argc,char **argv) {
    struct file file={0};struct inode inode={0};long rc;unsigned int req;
    assert(argc==3);
    has_capability=!strcmp(argv[1],"authorized");
    if(!strcmp(argv[2],"open")) {
        rc=dev_nvram_open(&inode,&file);
        if(has_capability)assert(rc==0 && module_gets==1 && privilege_checks==1);
        else assert(rc==-EPERM && module_gets==0 && backend_calls==0 && privilege_checks==1);
    } else if(!strcmp(argv[2],"capability_loss")) {
        has_capability=1;assert(dev_nvram_open(&inode,&file)==0 && module_gets==1);
        has_capability=0;privilege_checks=0;
        /* Read-only, inherited or leaked fd cannot bypass an ioctl re-check. */
        assert(dev_nvram_ioctl(&file,NVRAM_IOCTL_GET,1)==-EPERM);
        assert(backend_calls==0 && user_accesses==0 && privilege_checks==1);
        assert(dev_nvram_release(&inode,&file)==0 && module_puts==1);
    } else {
        req=operation(argv[2]);
        rc=dev_nvram_ioctl(&file,req,has_capability?0x1234:1);
        if(!has_capability) {
            assert(rc==-EPERM && backend_calls==0 && user_accesses==0 && privilege_checks==1);
        } else if(req==0xdead) {
            assert(rc==-EINVAL && backend_calls==0 && user_accesses==0 && privilege_checks==1);
        } else {
            long expected=req==NVRAM_IOCTL_COMMIT?101:req==NVRAM_IOCTL_CLEAR?102:req==NVRAM_IOCTL_SET?103:104;
            assert(rc==expected && backend_calls==1 && privilege_checks==1);
            assert(user_accesses==((req==NVRAM_IOCTL_GET || req==NVRAM_IOCTL_SET)?1:0));
        }
    }
    return 0;
}
'''
        root = Path(cls.tmp.name)
        (root/'driver.c').write_text(code)
        cls.binary = root/'driver'
        completed = subprocess.run(['clang', '-g', '-fsanitize=address,undefined',
                                    '-Werror=implicit-function-declaration', str(root/'driver.c'),
                                    '-o', str(cls.binary)], text=True, capture_output=True)
        if completed.returncode:
            raise AssertionError(completed.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_real_handler_privileged_and_denied_operations(self):
        for privilege in ('authorized', 'unauthorized'):
            for operation in ('open', 'commit', 'clear', 'set', 'get', 'unknown'):
                with self.subTest(privilege=privilege, operation=operation):
                    subprocess.run([str(self.binary), privilege, operation], check=True,
                                   capture_output=True, timeout=3)

    def test_privilege_loss_does_not_grant_access_or_leak_module_reference(self):
        subprocess.run([str(self.binary), 'unauthorized', 'capability_loss'], check=True,
                       capture_output=True, timeout=3)

    def test_device_has_no_alternate_read_write_or_mmap_path(self):
        body = re.search(r'static const struct file_operations dev_nvram_fops\s*=\s*\{([\s\S]*?)\};', self.text).group(1)
        self.assertIn('dev_nvram_ioctl', body)
        self.assertIn('dev_nvram_open', body)
        for name in ('read', 'write', 'mmap', 'compat_ioctl'):
            self.assertNotRegex(body, r'(?:\.' + name + r'\s*=|\b' + name + r'\s*:)')


if __name__ == '__main__':
    unittest.main()
