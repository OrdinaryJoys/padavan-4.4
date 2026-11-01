"""Replay upload preparation without files, devices or the shared RAM writer."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UploadWriterIsolationTests(unittest.TestCase):
    def test_actual_diagnostic_log_refuses_aliases_and_stays_bounded(self):
        text = (ROOT / 'trunk/user/httpd/upload.c').read_text()
        fn = re.search(r'static void\s+fwlog\([^\n]*\)\n\{.*?^\}', text, re.M | re.S)
        self.assertIsNotNone(fn)
        prefix = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
static const char *fixture;
'''
        suffix = r'''
static off_t size(const char *path) {
 struct stat st; assert(!stat(path,&st)); return st.st_size;
}
static void filled(const char *path, size_t bytes) {
 int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600); assert(fd>=0);
 char data[4096];memset(data,'x',sizeof(data));
 while(bytes) {size_t part=bytes>sizeof(data)?sizeof(data):bytes;
  assert(write(fd,data,part)==(ssize_t)part);bytes-=part;}
 assert(!close(fd));assert(!chmod(path,0600));
}
int main(int argc,char **argv) {
 assert(argc==2);fixture=argv[1];umask(077);
 char other[4096];assert(snprintf(other,sizeof(other),"%s-other",fixture)>0);
 fwlog("ready %d",7);assert(size(fixture)==8);
 assert(!unlink(fixture));filled(other,3);
 assert(!symlink(other,fixture));fwlog("forbidden");assert(size(other)==3);
 assert(!unlink(fixture));assert(!link(other,fixture));fwlog("forbidden");assert(size(other)==3);
 assert(!unlink(fixture));assert(!unlink(other));assert(!mkfifo(fixture,0600));
 fwlog("forbidden");assert(!unlink(fixture));
 filled(fixture,5);assert(!chmod(fixture,0644));fwlog("forbidden");assert(size(fixture)==5);
 assert(!chmod(fixture,0600));int lock=open(fixture,O_WRONLY);assert(lock>=0);
 assert(!flock(lock,LOCK_EX|LOCK_NB));fwlog("busy");assert(size(fixture)==5);assert(!close(lock));
 filled(fixture,65530);fwlog("too long");assert(size(fixture)==65530);
 fwlog("12345");assert(size(fixture)==65536);fwlog("full");assert(size(fixture)==65536);
 filled(fixture,0);char longline[2048];memset(longline,'a',sizeof(longline)-1);longline[2047]=0;
 fwlog("%s",longline);assert(size(fixture)==511);
 filled(fixture,0);for(int i=0;i<12;i++) {pid_t pid=fork();assert(pid>=0);
  if(!pid) {for(int j=0;j<200;j++)fwlog("worker %d record %d",i,j);_exit(0);}}
 for(int i=0;i<12;i++){int status;assert(wait(&status)>0);assert(WIFEXITED(status)&&!WEXITSTATUS(status));}
 assert(size(fixture)>0&&size(fixture)<=65536);
 FILE *fp=fopen(fixture,"r");assert(fp);char line[128];
 while(fgets(line,sizeof(line),fp))assert(strchr(line,'\n'));
 assert(!ferror(fp));assert(!fclose(fp));assert(!unlink(fixture));return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='k2p-upload-log-') as temporary:
            source, binary = Path(temporary) / 'test.c', Path(temporary) / 'test'
            source.write_text(prefix + fn.group(0).replace('"/tmp/fwcheck.log"', 'fixture') + suffix)
            compiled = subprocess.run(['clang', '-Wall', '-Wextra', '-Werror',
                                       '-fsanitize=address,undefined', str(source), '-o', str(binary)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            subprocess.run([str(binary), str(Path(temporary) / 'fwcheck.log')],
                           check=True, capture_output=True, timeout=20)

    def test_actual_upload_preparation_never_copies_through_shared_writer(self):
        text = (ROOT / 'trunk/user/httpd/upload.c').read_text()
        fn = re.search(r'void\s+do_upgrade_fw_post\([^\n]*\)\n\{.*?^\}', text, re.M | re.S)
        self.assertIsNotNone(fn)
        prefix = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/statvfs.h>
#define FW_IMG_NAME "/fixture/linux.trx"
/* Idle admission here; transaction/busy controls use the real lease header. */
#define HTTP_UPGRADE_ACTION_GUARD(failure)
typedef struct { unsigned char bytes[64]; } image_header_t;
static int copies, uploads, crcs, crc_result, low_space;
static int unlink_stub(const char *path) { (void)path; return 0; }
static int statvfs_stub(const char *path, struct statvfs *fs) {
 assert(!strcmp(path,"/tmp"));memset(fs,0,sizeof(*fs));
 fs->f_frsize=4096;fs->f_bavail=low_space?0:1024;return 0;
}
static void log_stub(const char *format,...) { (void)format; }
static int system_stub(const char *format,...) {
 if(strstr(format,"cp")||strstr(format,"mtd_write"))copies++;
 return 0;
}
static int cache_stub(const char *path,int value) {
 assert(!strcmp(path,"/proc/sys/vm/drop_caches")&&value==1);return 0;
}
static int header_stub(char *data,long *size) { (void)data;(void)size;return 0; }
static int upload_stub(FILE *f,int n,char *boundary,const char *file,const char *object,
 int (*header)(char*,long*),int header_size) {
 (void)f;(void)n;assert(!boundary&&!strcmp(file,FW_IMG_NAME)&&!strcmp(object,"file"));
 assert(header==header_stub&&header_size==64);uploads++;return 0;
}
static int crc_stub(const char *path) { assert(!strcmp(path,FW_IMG_NAME));crcs++;return crc_result; }
#define unlink unlink_stub
#define statvfs(path,buffer) statvfs_stub(path,buffer)
#define fwlog log_stub
#define httpd_log log_stub
#define doSystem system_stub
#define fput_int cache_stub
#define do_upload_file upload_stub
#define check_header_image header_stub
#define check_crc_image crc_stub
'''
        suffix = r'''
int main(void) {
 for(int failure=0;failure<3;failure++) {
  copies=uploads=crcs=0;low_space=failure==2;crc_result=failure==1?-1:0;
  do_upgrade_fw_post("fixture",NULL,4096,NULL);
  assert(copies==0);assert(uploads==(failure==2?0:1));assert(crcs==uploads);
 }
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='k2p-upload-writer-') as temporary:
            source, binary = Path(temporary) / 'test.c', Path(temporary) / 'test'
            source.write_text(prefix + fn.group(0) + suffix)
            compiled = subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                                       '-fsanitize=address,undefined', str(source), '-o', str(binary)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
