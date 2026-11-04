"""Current MTD preflight/main/writer with private files and inert device seams.

No production discovery, ioctl, proc, flash operation or reboot is executed.
No old unsafe buffer implementation is compiled or run.
"""
import hashlib
import json
from pathlib import Path

from legacy_firmware_harness import function

SOURCE_PATHS = {'mtd': 'trunk/user/mtd_write/mtd.c'}
FUNCTIONS = ('mtd_check', 'image_check', 'mtd_write', 'main')
MAIN_CASES = (
    'configured-k2p', 'small-large', 'large-small', 'resume-larger',
    'scratch-refused', 'existing-scratch-growth-refused',
    'first-open-error', 'second-open-error', 'first-close-error', 'second-close-error',
    'zero-erase', 'negative-erase', 'name-allocation-refused', 'writer-geometry-growth',
    'resume-offset-refused',
)
DIRECT_CASES = (
    'null-target', 'overlong-target', 'writer-null-buffer', 'writer-short-capacity',
    'writer-negative-length', 'writer-carried-length', 'writer-zero-erase',
)
CASES = MAIN_CASES + DIRECT_CASES

PREFIX = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <setjmp.h>
#define MAX_ARGS 8
#define JFFS2_EOF "\xde\xad\xc0\xde"
#define TRX_MAGIC 0x48445230
#define SEAMA_MAGIC 0x5ea3a417
#define WRGG03_MAGIC 0x20080321
#define be32_to_cpu(x) __builtin_bswap32(x)
#define le32_to_cpu(x) (x)
/* Admission has its own gate; this adapter never discovers proc/device nodes. */
#define MTD_K2P_LEGACY_GUARD 0
enum mtd_image_format { MTD_IMAGE_FORMAT_UNKNOWN, MTD_IMAGE_FORMAT_TRX, MTD_IMAGE_FORMAT_SEAMA, MTD_IMAGE_FORMAT_WRGG03 };
static char *buf,*imagefile,*jffs2file,*jffs2dir="";
static size_t buf_capacity,physical_bytes;
static enum mtd_image_format imageformat;
static int buflen,quiet=2,no_erase,jffs2_skip_bytes,erasesize;
static const char *case_name;
static int opens,closes,allocs,name_allocs,late_allocs,unlocks,erases,writes,reads;
static int mutation_started,main_exit,bad_range,write_started,block_erases;
static size_t requested,written_bytes;
static int live_fds[32],live_count;
static char trace[4096];
static size_t trace_used;
static jmp_buf escape;
static int is_case(const char *name){return !strcmp(case_name,name);}
static void event(const char *name){
 int n=snprintf(trace+trace_used,sizeof(trace)-trace_used,"%s%s",trace_used?",":"",name);
 if(n<0||(size_t)n>=sizeof(trace)-trace_used)abort();
 trace_used+=(size_t)n;
}
static int fixture_fd(const char *path,int flags){
 struct stat st;int fd=open(path,flags|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0||fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_nlink!=1)abort();
 return fd;
}
static int geometry(const char *name){
 if(is_case("resume-offset-refused"))return !strcmp(name,"Nvram")?128:!strcmp(name,"Storage")?64:16;
 if(is_case("configured-k2p"))return 65536;
 if(is_case("zero-erase"))return 0;
 if(is_case("negative-erase"))return -16;
 if(is_case("writer-geometry-growth")&&mutation_started)return 32;
 if(is_case("writer-zero-erase"))return 0;
 if(is_case("large-small"))return !strcmp(name,"Storage")?64:16;
 return !strcmp(name,"Config")?64:16;
}
static int mtd_check_open(const char *name){
 int fd;
 if(strcmp(name,"Storage")&&strcmp(name,"Config")&&strcmp(name,"Nvram"))abort();
 opens++;event("metadata-open");erasesize=geometry(name);
 if((is_case("first-open-error")&&opens==1)||(is_case("second-open-error")&&opens==2)){
  errno=EACCES;return -1;
 }
 fd=fixture_fd(FIXTURE_DEVICE,O_RDWR);
 if(live_count==32)abort();
 live_fds[live_count++]=fd;return fd;
}
static int seam_close(int fd){
 int i,result;
 for(i=0;i<live_count&&live_fds[i]!=fd;i++);
 if(i==live_count)abort();
 live_fds[i]=live_fds[--live_count];
 result=close(fd);closes++;event("metadata-close");
 if((is_case("first-close-error")&&closes==1)||(is_case("second-close-error")&&closes==2)){
  errno=EIO;return -1;
 }
 return result;
}
static void *seam_realloc(void *old,size_t length){
 void *result;
 allocs++;requested=length;event("scratch-allocation");
 if(mutation_started){late_allocs++;event("late-allocation");}
 if(is_case("scratch-refused")||is_case("existing-scratch-growth-refused")){errno=ENOMEM;return NULL;}
 result=realloc(old,length);if(result)physical_bytes=length;
 return result;
}
static void *seam_malloc(size_t length){return seam_realloc(NULL,length);}
static char *seam_strdup(const char *text){
 size_t length=strlen(text)+1;char *copy;
 name_allocs++;event("name-allocation");
 if(mutation_started){late_allocs++;event("late-allocation");}
 if(is_case("name-allocation-refused")){errno=ENOMEM;return NULL;}
 copy=malloc(length);if(copy)memcpy(copy,text,length);return copy;
}
static int seam_open(const char *path,int flags,...){
 if(strcmp(path,FIXTURE_IMAGE)||flags!=O_RDONLY)abort();
 return fixture_fd(path,flags);
}
static int range_ok(const void *address,size_t length){
 uintptr_t start=(uintptr_t)address,base=(uintptr_t)buf;
 return buf&&start>=base&&start-base<=physical_bytes&&length<=physical_bytes-(start-base);
}
static ssize_t seam_read(int fd,void *address,size_t length){
 reads++;event("image-read");
 if(!range_ok(address,length)){bad_range++;errno=EFAULT;return -1;}
 return read(fd,address,length);
}
static ssize_t seam_write(int fd,const void *address,size_t length){
 (void)fd;writes++;event("write");
 if(!range_ok(address,length)){bad_range++;errno=EFAULT;return -1;}
 written_bytes+=length;return (ssize_t)length;
}
static int mtd_block_is_bad(int fd,int offset){(void)fd;(void)offset;return 0;}
static int mtd_erase_block(int fd,int offset){
 (void)fd;(void)offset;erases++;block_erases++;event("erase");
 if((is_case("resume-larger")&&block_erases==1)||
    (is_case("resume-offset-refused")&&(block_erases==1||block_erases==3))){errno=EIO;return -1;}
 return 0;
}
static void indicate_writing(const char *name){(void)name;write_started++;event("writer-ready");}
static int mtd_replace_jffs2(const char*a,int b,int c,const char*d){(void)a;(void)b;(void)c;(void)d;abort();}
static void mtd_parse_jffs2data(const char*a,const char*b){(void)a;(void)b;abort();}
static int (*trx_check)(int,const char*,char*,int*)=NULL;
static int (*trx_fixup)(int,const char*)=NULL;
static int (*mtd_fixtrx)(const char*,size_t,size_t)=NULL;
static int (*mtd_fixseama)(const char*,size_t,size_t)=NULL;
static int (*mtd_fixwrgg)(const char*,size_t,size_t)=NULL;
static int (*mtd_resetbc)(const char*)=NULL;
static int mtd_unlock(const char *name){(void)name;unlocks++;mutation_started=1;event("unlock");return 0;}
static int mtd_erase(const char *name){(void)name;erases++;mutation_started=1;event("pre-erase");return 0;}
static int mtd_dump(const char*a,size_t b,size_t c){(void)a;(void)b;(void)c;abort();}
static int mtd_write_jffs2(const char*a,const char*b,const char*c){(void)a;(void)b;(void)c;abort();}
static void do_reboot(void){event("forbidden-reboot");abort();}
static void usage(void){main_exit=98;longjmp(escape,1);}
static void seam_exit(int code){main_exit=code;longjmp(escape,1);}
static void seam_sync(void){mutation_started=1;event("sync");}
'''

SUFFIX = r'''
int main(int argc,char **argv){
 char *args[]={"probe","-q","-q","-f","-e","Config","write",FIXTURE_IMAGE,"Storage:Config",NULL};
 char overlong[PATH_MAX+1];char *volatile old=NULL;int result,image_fd;
 if(argc!=2)return 99;
 case_name=argv[1];
 if(is_case("existing-scratch-growth-refused")){
  old=malloc(8);if(!old)abort();memset(old,0x5a,8);buf=old;buf_capacity=physical_bytes=8;
 }
 if(is_case("null-target"))result=mtd_check(NULL)?0:1;
 else if(is_case("overlong-target")){
  memset(overlong,'a',PATH_MAX);overlong[PATH_MAX]=0;result=mtd_check(overlong)?0:1;
 }else if(!strncmp(case_name,"writer-",7)&&!is_case("writer-geometry-growth")){
  buf=malloc(16);if(!buf)abort();buf_capacity=physical_bytes=16;
  if(is_case("writer-null-buffer")){free(buf);buf=NULL;buf_capacity=physical_bytes=0;}
  if(is_case("writer-short-capacity"))buf_capacity=8;
  if(is_case("writer-negative-length"))buflen=-1;
  if(is_case("writer-carried-length"))buflen=17;
  image_fd=fixture_fd(FIXTURE_IMAGE,O_RDONLY);
  result=mtd_write(image_fd,"Storage",NULL,0)!=0;
  if(close(image_fd))abort();
 }else{
  if(is_case("configured-k2p")||is_case("writer-geometry-growth"))args[8]="Storage";
  if(is_case("resume-offset-refused"))args[8]="Storage:Config:Storage:Nvram";
  if(!setjmp(escape))result=preflight_main(9,args);else result=main_exit;
 }
 printf("{\"case\":\"%s\",\"returncode\":%d,\"trace\":\"%s\",\"opens\":%d,\"closes\":%d,\"live_fds\":%d,\"allocations\":%d,\"allocation_bytes\":%lu,\"capacity\":%lu,\"name_allocations\":%d,\"late_allocations\":%d,\"unlocks\":%d,\"erases\":%d,\"writes\":%d,\"image_reads\":%d,\"written_bytes\":%lu,\"bad_range\":%d,\"writer_ready\":%d,\"old_allocation_preserved\":%s}\n",
 case_name,result,trace,opens,closes,live_count,allocs,(unsigned long)requested,(unsigned long)buf_capacity,
 name_allocs,late_allocs,unlocks,erases,writes,reads,(unsigned long)written_bytes,bad_range,write_started,
 old&&buf==old&&physical_bytes==8&&buf[0]==0x5a?"true":"false");
 while(live_count)if(close(live_fds[--live_count]))abort();
 free(buf);return 0;
}
'''


def generate_source(texts, fixture_root):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact preflight source key required')
    root = Path(fixture_root)
    if not root.is_absolute() or any(c in str(root) for c in '\n\r\0'):
        raise ValueError('Private absolute fixture path required')
    defines = '\n'.join('#define %s %s' % (name, json.dumps(str(root / leaf)))
                        for name, leaf in (('FIXTURE_IMAGE', 'image'), ('FIXTURE_DEVICE', 'device')))
    bodies = {name: function(texts['mtd'], name) for name in FUNCTIONS}
    macros = '\n#define realloc seam_realloc\n#define malloc seam_malloc\n#define strdup seam_strdup\n'
    macros += '#define open seam_open\n#define close seam_close\n#define read seam_read\n#define write seam_write\n'
    macros += '#define sync seam_sync\n#define exit seam_exit\n'
    code = defines + '\n' + PREFIX + macros
    code += '\n\n'.join(bodies[name] for name in FUNCTIONS[:-1])
    code += '\n#define main preflight_main\n' + bodies['main'] + '\n#undef main\n'
    code += ''.join('#undef ' + name + '\n' for name in
                    ('realloc', 'malloc', 'strdup', 'open', 'close', 'read', 'write', 'sync', 'exit'))
    return code + SUFFIX


def source_hashes(texts):
    return {name: hashlib.sha256(function(texts['mtd'], name).encode()).hexdigest()
            for name in FUNCTIONS}
