#!/usr/bin/env python3
"""Verify the real init_nodes creation and existing-node correction paths."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_httpd_regressions import function

ROOT=Path(__file__).resolve().parents[1]

class ControlNodeTests(unittest.TestCase):
    def test_existing_and_new_control_nodes_are_private(self):
        code=r'''
#include <sys/types.h>
#include <sys/stat.h>
#ifdef __linux__
#include <sys/sysmacros.h>
#endif
#include <errno.h>
#include <string.h>
#include <assert.h>
static int existing,created_nvram,created_hnat,corrected_nvram,corrected_hnat;
static int fake_mknod(const char *path,mode_t mode,dev_t dev){
 (void)dev;
 if(!strcmp(path,"/dev/nvram")){assert((mode&0777)==0600);created_nvram++;}
 if(!strcmp(path,"/dev/hwnat0")){assert((mode&0777)==0600);created_hnat++;}
 if(existing){errno=EEXIST;return -1;}return 0;
}
static int fake_chmod(const char *path,mode_t mode){
 if(!strcmp(path,"/dev/nvram")){assert(mode==0600);corrected_nvram++;}
 if(!strcmp(path,"/dev/hwnat0")){assert(mode==0600);corrected_hnat++;}
 return 0;
}
#define USE_HW_NAT 1
#define mknod fake_mknod
#define chmod fake_chmod
'''
        code+=function((ROOT/'trunk/user/rc/init.c').read_text(),'init_nodes')
        code+='\nint main(void){init_nodes();existing=1;init_nodes();assert(created_nvram==2 && created_hnat==2 && corrected_nvram==2 && corrected_hnat==2);return 0;}\n'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'test.c').write_text(code)
            r=subprocess.run(['clang','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            subprocess.run([str(p/'test')],check=True)

if __name__=='__main__':unittest.main()
