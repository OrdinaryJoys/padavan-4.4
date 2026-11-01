"""Pure actual-function generator; all MTD/reset effects are inert.

The compile-time fixture path and owner model are not production bypasses.
The regular files, /proc/mtd text and read-only stat alias model are synthetic.
"""
import hashlib
import json
from pathlib import Path
import re

SOURCE_PATHS = {
    'mtd': 'trunk/user/mtd_write/mtd.c',
    'legacy_guard': 'trunk/user/mtd_write/legacy_guard.h',
}
CASE_ARGS = {
    'old-stage-protocol': ['--upgrade-write', '@IMAGE', 'firmware', '@STATUS'],
    'malformed-stage-protocol': ['--upgrade-write'],
    'firmware-write': ['write', '@IMAGE', 'firmware'],
    'firmware-write-reboot': ['-r', 'write', '@IMAGE', 'firmware'],
    'firmware-char-alias': ['write', '@IMAGE', '/dev/mtd3'],
    'firmware-ro-alias': ['erase', '/dev/mtd3ro'],
    'firmware-directory-alias': ['unlock', '/dev/mtd/3'],
    'firmware-block-alias': ['write', '@IMAGE', '/dev/mtdblock3'],
    'firmware-block-directory-alias': ['erase', '/dev/mtdblock/3'],
    'firmware-short-alias': ['write', '@IMAGE', 'mtd3'],
    'firmware-symlink-alias': ['write', '@IMAGE', '/fixture/firmware-link'],
    'firmware-renumbered-alias': ['write', '@IMAGE', '/dev/mtd11'],
    'kernel-overlap': ['write', '@IMAGE', 'kernel'],
    'rootfs-overlap': ['write', '@IMAGE', 'rootfs'],
    'all-label': ['erase', 'ALL'],
    'all-device': ['unlock', '/dev/mtd7'],
    'firmware-fixtrx': ['fixtrx', 'firmware'],
    'firmware-fixseama': ['fixseama', 'firmware'],
    'firmware-fixwrgg': ['fixwrgg', 'firmware'],
    'firmware-resetbc': ['resetbc', 'firmware'],
    'firmware-jffs2write': ['jffs2write', '@IMAGE', 'firmware'],
    'preerase-firmware': ['-e', 'firmware', 'write', '@IMAGE', 'Storage'],
    'preerase-firmware-read': ['-e', '/dev/mtdblock3', 'dump', 'Storage'],
    'colon-firmware': ['write', '@IMAGE', 'Storage:firmware'],
    'colon-preerase': ['-e', 'Storage:ALL', 'write', '@IMAGE', 'Config'],
    'reboot-storage-read': ['-r', 'dump', 'Storage'],
    'reboot-storage-write': ['-r', 'write', '@IMAGE', 'Storage'],
    'unknown-target': ['write', '@IMAGE', '/fixture/unknown'],
    'regular-file-target': ['write', '@IMAGE', '@IMAGE'],
    'bad-partition-table': ['write', '@IMAGE', 'Storage'],
    'duplicate-index-table': ['write', '@IMAGE', 'Storage'],
    'duplicate-name-table': ['write', '@IMAGE', 'Storage'],
    'overflow-table': ['write', '@IMAGE', 'Storage'],
    'truncated-table': ['write', '@IMAGE', 'Storage'],
    'unknown-partition-table': ['write', '@IMAGE', 'Storage'],
    'safe-storage-write': ['write', '@IMAGE', 'Storage'],
    'safe-config-erase': ['erase', 'Config'],
    'safe-nvram-write': ['write', '@IMAGE', 'Nvram'],
    'safe-storage-device': ['write', '@IMAGE', '/dev/mtd6'],
    'readonly-firmware-dump': ['dump', 'firmware'],
    'readonly-bad-table': ['dump', 'firmware'],
    'disabled-guard-silent-corruption': ['-r', 'write', '@IMAGE', 'firmware'],
    'too-many-preerase': ['-e', 'Storage'] * 8 + ['write', '@IMAGE', 'Storage'],
    'missing-partition-table': ['write', '@IMAGE', 'Storage'],
    'oversized-partition-line': ['write', '@IMAGE', 'Storage'],
}
CASE_NAMES = tuple(CASE_ARGS)
REJECTED_CASES = CASE_NAMES[:35]


def function(text, name):
    match = re.search(r'(?:static\s+)?(?:void|int|ssize_t|char\s*\*|FILE\s*\*)\s*\n?\b' + name + r'\s*\(', text)
    if not match:
        raise ValueError(name)
    opening = text.index('{', match.end())
    depth = 0
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*|[{}]')
    for item in token.finditer(text, opening):
        if item.group() == '{':
            depth += 1
        elif item.group() == '}':
            depth -= 1
            if not depth:
                return text[match.start():item.end()]
    raise ValueError(name)


def actual_functions(texts):
    return {name: {'source': 'mtd', 'body': function(texts['mtd'], name)}
            for name in ('image_check', 'mtd_write', 'do_reboot', 'main')}


PREFIX = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#include <limits.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <stdarg.h>
#ifdef __linux__
#include <sys/sysmacros.h>
#endif
#define MAX_ARGS 8
#define JFFS2_EOF "\xde\xad\xc0\xde"
#define TRX_MAGIC 0x48445230
#define SEAMA_MAGIC 0x5ea3a417
#define WRGG03_MAGIC 0x20080321
#define be32_to_cpu(x) __builtin_bswap32(x)
#define le32_to_cpu(x) (x)
enum mtd_image_format { MTD_IMAGE_FORMAT_UNKNOWN, MTD_IMAGE_FORMAT_TRX, MTD_IMAGE_FORMAT_SEAMA, MTD_IMAGE_FORMAT_WRGG03 };
static char *buf,*imagefile,*jffs2file,*jffs2dir="";
static enum mtd_image_format imageformat;
static int buflen,quiet,no_erase,jffs2_skip_bytes,erasesize=16;
static int (*trx_check)(int,const char*,char*,int*)=NULL;
static const char *case_name;
static char trace[4096];
static int trace_used,corrupted,device_reads;
static void event(const char*s){int n=snprintf(trace+trace_used,sizeof(trace)-(size_t)trace_used,"%s%s",trace_used?",":"",s);if(n<0||(size_t)n>=sizeof(trace)-(size_t)trace_used)abort();trace_used+=n;}
static int fixture_fd(const char*p,int flags){int fd=open(p,flags|O_NOFOLLOW|O_CLOEXEC);struct stat st;if(fd<0||fstat(fd,&st)||!S_ISREG(st.st_mode))abort();return fd;}
static int mtd_check_open(const char*n){(void)n;event("writable-open");return fixture_fd(FIXTURE_DEVICE,O_RDWR);}
static int mtd_check(const char*n){(void)n;event("mtd-check");if(!buf)buf=malloc(16);return buf!=NULL;}
static int mtd_block_is_bad(int fd,int n){(void)fd;(void)n;return 0;}
static int mtd_erase_block(int fd,int n){(void)fd;(void)n;event("erase");return 0;}
static void indicate_writing(const char*n){(void)n;}
static int mtd_replace_jffs2(const char*a,int b,int c,const char*d){(void)a;(void)b;(void)c;(void)d;abort();}
static void mtd_parse_jffs2data(const char*a,const char*b){(void)a;(void)b;abort();}
static int fixup(int fd,const char*n){(void)fd;(void)n;event("fixup");return 0;}
static int fix3(const char*n,size_t a,size_t b){(void)n;(void)a;(void)b;event("fix");return 0;}
static int resetbc(const char*n){(void)n;event("resetbc");return 0;}
static int (*trx_fixup)(int,const char*)=fixup;
static int (*mtd_fixtrx)(const char*,size_t,size_t)=fix3;
static int (*mtd_fixseama)(const char*,size_t,size_t)=fix3;
static int (*mtd_fixwrgg)(const char*,size_t,size_t)=fix3;
static int (*mtd_resetbc)(const char*)=resetbc;
static int mtd_unlock(const char*n){(void)n;event("unlock");return 0;}
static int mtd_erase(const char*n){(void)n;event("erase");return 0;}
static int mtd_dump(const char*n,int a,int b){(void)n;(void)a;(void)b;event("dump");return 0;}
static int mtd_write_jffs2(const char*a,const char*b,const char*c){(void)a;(void)b;(void)c;event("jffs2write");return 0;}
static void usage(void){event("usage");exit(98);}
static void inert_sync(void){event("sync");}
static int inert_system(const char*s){if(strcmp(s,"/sbin/reboot"))abort();event("system-reboot");return -1;}
static unsigned int inert_sleep(unsigned int s){if(s!=2)abort();event("sleep2");return 0;}
static long inert_syscall(long number,...){(void)number;event("raw-reboot");return -1;}
static int is_device(int fd){struct stat a,b;return !fstat(fd,&a)&&!stat(FIXTURE_DEVICE,&b)&&a.st_dev==b.st_dev&&a.st_ino==b.st_ino;}
static ssize_t inert_read(int fd,void*p,size_t n){if(is_device(fd))device_reads++;return read(fd,p,n);}
static ssize_t inert_write(int fd,const void*p,size_t n){
 ssize_t r=write(fd,p,n);
 if(is_device(fd)){event("write");if(!strcmp(case_name,"disabled-guard-silent-corruption")&&r>0){unsigned char x=0xa5;if(pwrite(fd,&x,1,0)!=1)abort();corrupted=1;}}
 return r;
}
static int alias_stat(const char*p,struct stat*st){
 unsigned index=0;int block=0;const char*s=NULL;char*end;
 if(!strcmp(p,"/fixture/firmware-link")){index=3;}
 else{
  if(!strncmp(p,"/dev/mtdblock/",14)){s=p+14;block=1;}
  else if(!strncmp(p,"/dev/mtdblock",13)){s=p+13;block=1;}
  else if(!strncmp(p,"/dev/mtd/",9))s=p+9;
  else if(!strncmp(p,"/dev/mtd",8))s=p+8;
  else if(!strncmp(p,"mtd",3))s=p+3;
  if(!s||!*s)return stat(p,st);
  index=(unsigned)strtoul(s,&end,10);if((*end&&strcmp(end,"ro"))||index>127){errno=ENOENT;return -1;}
 }
 memset(st,0,sizeof(*st));st->st_mode=block?S_IFBLK:S_IFCHR;st->st_rdev=makedev(block?31:90,block?index:index*2);return 0;
}
#define LEGACY_GUARD_STAT alias_stat
#define SYS_reboot 123456
#define LINUX_REBOOT_MAGIC1 0xfee1dead
#define LINUX_REBOOT_MAGIC2 672274793
#define LINUX_REBOOT_CMD_RESTART 0x01234567
'''

SUFFIX = r'''
static void write_fixture(const char*p,const char*s){int fd=open(p,O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW,0600);if(fd<0||write(fd,s,strlen(s))!=(ssize_t)strlen(s)||close(fd))abort();}
int main(int argc,char**argv){
 const char *table="dev:    size   erasesize  name\n"
 "mtd0: 00030000 00010000 \"Bootloader\"\n"
 "mtd1: 00010000 00010000 \"Config\"\n"
 "mtd2: 00010000 00010000 \"Factory\"\n"
 "mtd3: 00f30000 00010000 \"firmware\"\n"
 "mtd4: 001b9fd0 00010000 \"kernel\"\n"
 "mtd5: 00d76030 00010000 \"rootfs\"\n"
 "mtd6: 00080000 00010000 \"Storage\"\n"
 "mtd7: 01000000 00010000 \"ALL\"\n";
 char modified[9000],*p;int which=-1,result;size_t i;
 if(argc!=2)return 99;
 case_name=argv[1];
 for(i=0;i<sizeof(cases)/sizeof(cases[0]);i++)if(!strcmp(case_name,cases[i].name))which=(int)i;
 if(which<0)return 99;
 if(mkdir(FIXTURE_ROOT,0700)&&errno!=EEXIST)abort();
 write_fixture(FIXTURE_IMAGE,"ordinary synthetic non-firmware input bytes only\n");
 write_fixture(FIXTURE_DEVICE,"initial ordinary file bytes\n");
 if(strlen(table)>=sizeof(modified))abort();
 strcpy(modified,table);
 if(!strcmp(case_name,"bad-partition-table")||!strcmp(case_name,"readonly-bad-table"))strcpy(modified,"malformed\n");
 else if(!strcmp(case_name,"duplicate-index-table"))strcat(modified,"mtd3: 00080000 00010000 \"Nvram\"\n");
 else if(!strcmp(case_name,"duplicate-name-table"))strcat(modified,"mtd9: 00080000 00010000 \"Storage\"\n");
 else if(!strcmp(case_name,"overflow-table"))strcat(modified,"mtd429496729600000: 00080000 00010000 \"Storage\"\n");
 else if(!strcmp(case_name,"truncated-table"))modified[strlen(modified)-1]=0;
 else if(!strcmp(case_name,"unknown-partition-table"))strcat(modified,"mtd9: 00010000 00010000 \"unknown\"\n");
 else if(!strcmp(case_name,"missing-partition-table")){p=strstr(modified,"mtd0:");if(!p)abort();memmove(p,strchr(p,'\n')+1,strlen(strchr(p,'\n')+1)+1);}
 else if(!strcmp(case_name,"oversized-partition-line")){memset(modified,'a',300);modified[300]='\n';modified[301]=0;}
 else if(!strcmp(case_name,"safe-nvram-write")){p=strstr(modified,"Config");if(!p)abort();memcpy(p,"Nvram ",6);p[5]='"';memmove(p+6,p+7,strlen(p+7)+1);}
 else if(!strcmp(case_name,"firmware-renumbered-alias")){p=strstr(modified,"mtd3:");if(!p)abort();memmove(p+5,p+4,strlen(p+4)+1);memcpy(p,"mtd11",5);}
 write_fixture(LEGACY_GUARD_PROC_MTD,modified);
 optind=1;
 result=legacy_main(cases[which].argc,cases[which].argv);
 free(buf);buf=NULL;
 printf("{\"case\":\"%s\",\"returncode\":%d,\"trace\":\"%s\",\"device_reads\":%d,\"corrupted\":%d}\n",case_name,result,trace,device_reads,corrupted);
 return 0;
}
'''


def generate_source(texts, fixture_root, owner_uid=0, enabled=True):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('source key set')
    root = str(Path(fixture_root))
    if not root.startswith('/') or '\x00' in root or not isinstance(owner_uid, int) or isinstance(owner_uid, bool):
        raise ValueError('fixture identity')
    defs = '\n'.join('#define %s %s' % (key, json.dumps(value)) for key, value in {
        'FIXTURE_ROOT': root, 'FIXTURE_IMAGE': root + '/image', 'FIXTURE_DEVICE': root + '/device',
        'LEGACY_GUARD_PROC_MTD': root + '/proc-mtd',
    }.items())
    defs += '\n#define LEGACY_GUARD_OWNER %d\n#define MTD_K2P_LEGACY_GUARD %d\n' % (owner_uid, int(bool(enabled)))
    rows = []
    for name, args in CASE_ARGS.items():
        literals = ['"probe"'] + [({'@IMAGE': 'FIXTURE_IMAGE', '@STATUS': '"unused-status"'}.get(a) or json.dumps(a)) for a in args]
        rows.append('{%s,%d,{%s,NULL}}' % (json.dumps(name), len(literals), ','.join(literals)))
    cases = 'struct fixture_case {const char*name;int argc;char*argv[32];};\nstatic struct fixture_case cases[]={\n' + ',\n'.join(rows) + '\n};\n'
    functions = actual_functions(texts)
    code = defs + PREFIX + '\n' + texts['legacy_guard'] + '\n'
    code += '#define read inert_read\n#define write inert_write\n#define sync inert_sync\n#define system inert_system\n#define sleep inert_sleep\n#define syscall inert_syscall\n'
    code += '\n\n'.join(functions[n]['body'] for n in ('image_check', 'mtd_write', 'do_reboot'))
    code += '\n#define main legacy_main\n' + functions['main']['body'] + '\n#undef main\n'
    code += '#undef read\n#undef write\n#undef sync\n#undef system\n#undef sleep\n#undef syscall\n'
    return code + cases + SUFFIX


def source_hashes(texts):
    return {key: hashlib.sha256(value.encode()).hexdigest() for key, value in texts.items()}
