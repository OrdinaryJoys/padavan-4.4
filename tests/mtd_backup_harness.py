"""Actual legacy backup path with synthetic metadata and inert MTD/stdout effects.

No device, procfs, erase, reset or firmware payload is used. Baseline bodies are
literal 3af01e18 fixtures so a shallow checkout preserves negative controls.
"""
import hashlib
import json
from pathlib import Path
import re
import legacy_firmware_harness as legacy

SOURCE_PATHS = dict(legacy.SOURCE_PATHS)
BASELINE_COMMIT = "3af01e18af99e4329a65636f6e854fedf94a9fc3"
CASE_ARGS = {
    "normal": ["dump", "firmware"],
    "sync-blocking": ["dump", "firmware"],
    "storage": ["dump", "Storage"],
    "alias": ["dump", "/dev/mtd3"],
    "offset-default": ["-o", "3", "dump", "firmware"],
    "unaligned-range": ["-o", "3", "-l", "7", "dump", "firmware"],
    "explicit-zero-length": ["-o", "3", "-l", "0", "dump", "firmware"],
    "last-byte": ["-o", "15", "-l", "1", "dump", "firmware"],
    "offset-at-end": ["-o", "16", "dump", "firmware"],
    "offset-beyond-end": ["-o", "17", "dump", "firmware"],
    "range-overflow": ["-o", "15", "-l", "2", "dump", "firmware"],
    "huge-range": ["-l", "4294967295", "dump", "firmware"],
    "bad-length": ["-l", "garbage", "dump", "firmware"],
    "negative-length": ["-l", "-1", "dump", "firmware"],
    "trailing-length": ["-l", "1junk", "dump", "firmware"],
    "empty-length": ["-l", "", "dump", "firmware"],
    "bad-offset": ["-o", "1junk", "dump", "firmware"],
    "negative-offset": ["-o", "-1", "dump", "firmware"],
    "overflow-offset": ["-o", "184467440737095516160", "dump", "firmware"],
    "zero-size": ["dump", "firmware"],
    "negative-size": ["dump", "firmware"],
    "zero-erase": ["dump", "firmware"],
    "negative-erase": ["dump", "firmware"],
    "open-error": ["dump", "firmware"],
    "metadata-error": ["dump", "firmware"],
    "seek-error": ["-o", "1", "dump", "firmware"],
    "wrong-seek": ["-o", "1", "dump", "firmware"],
    "alloc-error": ["dump", "firmware"],
    "read-eintr": ["dump", "firmware"],
    "short-read": ["dump", "firmware"],
    "early-eof": ["dump", "firmware"],
    "read-error": ["dump", "firmware"],
    "read-again": ["dump", "firmware"],
    "write-eintr": ["dump", "firmware"],
    "short-write": ["dump", "firmware"],
    "zero-write": ["dump", "firmware"],
    "write-error": ["dump", "firmware"],
    "write-again": ["dump", "firmware"],
    "close-error": ["dump", "firmware"],
    "nand-offset": ["-o", "3", "-l", "7", "dump", "firmware"],
    "nand-bad": ["-o", "3", "-l", "7", "dump", "firmware"],
    "verify-firmware": ["verify", "@IMAGE", "firmware"],
    "verify-storage": ["verify", "@IMAGE", "Storage"],
    "verify-preerase": ["-e", "Storage", "verify", "@IMAGE", "firmware"],
    "dump-preerase": ["-e", "Storage", "dump", "firmware"],
    "dump-noerase": ["-n", "dump", "firmware"],
    "dump-force": ["-f", "dump", "firmware"],
    "dump-write-offset": ["-p", "0", "dump", "firmware"],
    "dump-jffs": ["-j", "unused", "dump", "firmware"],
    "dump-skip": ["-s", "0", "dump", "firmware"],
    "dump-directory": ["-d", "unused", "dump", "firmware"],
    "dump-checksum": ["-c", "0", "dump", "firmware"],
    "reboot-dump": ["-r", "dump", "firmware"],
    "reboot-verify": ["-r", "verify", "@IMAGE", "firmware"],
    "protected-preerase": ["-e", "/dev/mtd3", "dump", "Storage"],
    "protected-write": ["write", "@IMAGE", "/dev/mtd3"],
    "old-protocol": ["--upgrade-write", "@IMAGE", "firmware", "unused"],
}
CASE_NAMES = tuple(CASE_ARGS)
BASELINE_CASES = ("normal", "short-read", "early-eof", "read-error", "write-error", "short-write", "seek-error", "alloc-error", "verify-firmware", "verify-storage", "dump-preerase", "trailing-length")

MODEL = r'''
#include <stdbool.h>
#include <stddef.h>
#ifndef __linux__
typedef long long loff_t;
#endif
#define MEMGETINFO 1
#define MEMGETBADBLOCK 2
#define MTD_NANDFLASH 4
struct mtd_info_user {unsigned int size, erasesize, writesize; unsigned char type;};
static int mtdsize,writesize,mtdtype;
static int opens,open_flags,closes,reads,writes,seeks,allocs,frees,metas,bad_checks;
static int physical_bad[16],position,out_size,was_read_eintr,was_write_eintr;
static char opened_path[128],output[64];
static void *allocation;
static int iscase(const char*n){return !strcmp(case_name,n);}
static int dump_open(const char*p,int flags){opens++;open_flags=flags;snprintf(opened_path,sizeof(opened_path),"%s",p);event("open");if(iscase("open-error")){errno=EACCES;return -1;}position=0;return 777;}
static FILE* dump_fopen(const char*p,const char*mode){if(strcmp(p,"/proc/mtd")||strcmp(mode,"r"))abort();return fopen(LEGACY_GUARD_PROC_MTD,"r");}
static int dump_close(int fd){if(fd!=777)abort();closes++;event("close");if(iscase("close-error")){errno=EIO;return -1;}return 0;}
static int dump_ioctl(int fd,unsigned long req,void*p){if(fd!=777)abort();if(req==MEMGETINFO){struct mtd_info_user*x=p;metas++;event("metadata");if(iscase("metadata-error")){errno=EIO;return -1;}x->size=iscase("zero-size")?0:iscase("negative-size")?(unsigned)-1:16;x->erasesize=iscase("zero-erase")?0:iscase("negative-erase")?(unsigned)-1:4;x->writesize=1;x->type=(iscase("nand-offset")||iscase("nand-bad"))?MTD_NANDFLASH:3;return 0;}if(req==MEMGETBADBLOCK){long long off=*(loff_t*)p;if(bad_checks>=16)abort();physical_bad[bad_checks++]=(int)off;return iscase("nand-bad")&&off==4;}abort();}
static off_t dump_seek(int fd,off_t off,int whence){if(fd!=777||whence!=SEEK_SET)abort();seeks++;if(iscase("seek-error")){errno=EIO;return -1;}if(iscase("wrong-seek"))return off+1;position=(int)off;return off;}
static void* dump_malloc(size_t n){allocs++;if(iscase("alloc-error"))return NULL;if(allocation)abort();allocation=malloc(n);return allocation;}
static void dump_free(void*p){if(!p)return;if(p!=allocation)abort();frees++;free(p);allocation=NULL;}
static ssize_t dump_read(int fd,void*p,size_t n){size_t count=n;if(fd!=777)abort();reads++;if(iscase("read-eintr")&&!was_read_eintr++){errno=EINTR;return -1;}if(iscase("read-error")||iscase("read-again")){errno=iscase("read-again")?EAGAIN:EIO;return -1;}if(iscase("early-eof"))return 0;if(iscase("short-read")&&count>2)count=2;if(position<0||position+(int)count>16)abort();memcpy(p,&"0123456789ABCDEF"[position],count);position+=(int)count;return (ssize_t)count;}
static ssize_t dump_write(int fd,const void*p,size_t n){size_t count=n;if(fd!=STDOUT_FILENO)abort();writes++;if(iscase("write-eintr")&&!was_write_eintr++){errno=EINTR;return -1;}if(iscase("write-error")||iscase("write-again")){errno=iscase("write-again")?EAGAIN:EIO;return -1;}if(iscase("zero-write"))return 0;if(iscase("short-write")&&count>2)count=2;if(out_size+(int)count>=64)abort();memcpy(output+out_size,p,count);out_size+=(int)count;output[out_size]=0;return (ssize_t)count;}
'''


def actual_functions(texts):
    source=texts['mtd']
    names=('mtd_open_flags','mtd_open','mtd_check_open_flags','mtd_check_open','mtd_block_is_bad','mtd_check','mtd_dump','main')
    return {name:{'source':'mtd','body':legacy.function(source,name)} for name in names}


def source_hashes(texts):
    return {key:hashlib.sha256(value.encode()).hexdigest() for key,value in texts.items()}


def generate_source(texts,fixture_root,owner_uid=0,baseline=False,disabled_oracle=False):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('source key set')
    source=texts['mtd']
    bodies=BASELINE_FUNCTIONS if baseline else {n:v['body'] for n,v in actual_functions(texts).items()}
    if baseline:
        source=source.replace(legacy.function(source,'main'),bodies['main'])
    selected=dict(texts,mtd=source)
    previous=legacy.CASE_ARGS
    try:
        legacy.CASE_ARGS=CASE_ARGS
        code=legacy.generate_source(selected,fixture_root,owner_uid)
    finally:
        legacy.CASE_ARGS=previous
    code=re.sub(r'static int mtd_check\(const char\*n\)\{[^\n]*\}\n','',code,count=1)
    code=re.sub(r'static int mtd_check_open\(const char\*n\)\{[^\n]*\}\n','',code,count=1)
    code=re.sub(r'static int mtd_dump\(const char\*n,int a,int b\)\{[^\n]*\}\n','',code,count=1)
    code=re.sub(r'static int mtd_block_is_bad\(int fd,int n\)\{[^\n]*\}\n','',code,count=1)
    names=('mtd_open','mtd_check_open','mtd_block_is_bad','mtd_check','mtd_dump') if baseline else tuple(n for n in bodies if n!='main')
    functions='\n\n'.join(bodies[n] for n in names)
    maps={'open':'dump_open','fopen':'dump_fopen','close':'dump_close','ioctl':'dump_ioctl','lseek':'dump_seek','malloc':'dump_malloc','free':'dump_free','read':'dump_read','write':'dump_write'}
    inject=MODEL+'\n'+''.join('#define %s %s\n'%p for p in maps.items())+functions+'\n'+''.join('#undef %s\n'%n for n in maps)
    code=code.replace('static void inert_sync(void){event("sync");}', 'static void inert_sync(void){if(!strcmp(case_name,"sync-blocking"))abort();event("sync");}',1)
    code=code.replace('#define read inert_read',inject+'\n#define read inert_read',1)
    old='printf("{\\"case\\":\\"%s\\",\\"returncode\\":%d,\\"trace\\":\\"%s\\",\\"device_reads\\":%d,\\"corrupted\\":%d}\\n",case_name,result,trace,device_reads,corrupted);'
    start=code.index(' printf("{\\"case')
    end=code.index('\n return 0;',start)
    report=r''' printf("{\"case\":\"%s\",\"returncode\":%d,\"trace\":\"%s\",\"opens\":%d,\"flags\":%d,\"readonly\":%d,\"nonblock\":%d,\"cloexec\":%d,\"path\":\"%s\",\"closes\":%d,\"reads\":%d,\"writes\":%d,\"seeks\":%d,\"allocs\":%d,\"frees\":%d,\"metadata\":%d,\"output\":\"%s\",\"bad_offsets\":[",case_name,result,trace,opens,open_flags,(open_flags&O_ACCMODE)==O_RDONLY,!!(open_flags&O_NONBLOCK),!!(open_flags&O_CLOEXEC),opened_path,closes,reads,writes,seeks,allocs,frees,metas,output);
 for(i=0;i<(size_t)bad_checks;i++)printf("%s%d",i?",":"",physical_bad[i]);
 puts("]}");
 free(allocation);allocation=NULL;'''
    code=code[:start]+report+code[end:]
    if disabled_oracle:
        code=code.replace('result=legacy_main(cases[which].argc,cases[which].argv);','result=0;')
    return code


BASELINE_FUNCTIONS = {'mtd_open': 'int mtd_open(const char *mtd, bool block)\n{\n\tFILE *fp;\n\tchar dev[PATH_MAX];\n\tint i;\n\tint ret;\n\tint flags = O_RDWR | O_SYNC;\n\tchar name[PATH_MAX];\n\n\tsnprintf(name, sizeof(name), "\\"%s\\"", mtd);\n\tif ((fp = fopen("/proc/mtd", "r"))) {\n\t\twhile (fgets(dev, sizeof(dev), fp)) {\n\t\t\tif (sscanf(dev, "mtd%d:", &i) && strstr(dev, name)) {\n\t\t\t\tsnprintf(dev, sizeof(dev), "/dev/mtd%s/%d", (block ? "block" : ""), i);\n\t\t\t\tif ((ret=open(dev, flags))<0) {\n\t\t\t\t\tsnprintf(dev, sizeof(dev), "/dev/mtd%s%d", (block ? "block" : ""), i);\n\t\t\t\t\tret=open(dev, flags);\n\t\t\t\t}\n\t\t\t\tfclose(fp);\n\t\t\t\treturn ret;\n\t\t\t}\n\t\t}\n\t\tfclose(fp);\n\t}\n\n\treturn open(mtd, flags);\n}', 'mtd_check_open': 'int mtd_check_open(const char *mtd)\n{\n\tstruct mtd_info_user mtdInfo;\n\tint fd;\n\n\tfd = mtd_open(mtd, false);\n\tif(fd < 0) {\n\t\tfprintf(stderr, "Could not open mtd device: %s\\n", mtd);\n\t\treturn -1;\n\t}\n\n\tif(ioctl(fd, MEMGETINFO, &mtdInfo)) {\n\t\tfprintf(stderr, "Could not get MTD device info from %s\\n", mtd);\n\t\tclose(fd);\n\t\treturn -1;\n\t}\n\tmtdsize = mtdInfo.size;\n\terasesize = mtdInfo.erasesize;\n\tmtdtype = mtdInfo.type;\n\twritesize = mtdInfo.writesize;\n\n\treturn fd;\n}', 'mtd_block_is_bad': 'int mtd_block_is_bad(int fd, int offset)\n{\n\tint r = 0;\n\tloff_t o = offset;\n\n\tif (mtdtype == MTD_NANDFLASH)\n\t{\n\t\tr = ioctl(fd, MEMGETBADBLOCK, &o);\n\t\tif (r < 0)\n\t\t{\n\t\t\tfprintf(stderr, "Failed to get erase block status\\n");\n\t\t\texit(1);\n\t\t}\n\t}\n\treturn r;\n}', 'mtd_dump': 'static int\nmtd_dump(const char *mtd, int part_offset, int size)\n{\n\tint ret = 0, offset = 0;\n\tint fd;\n\tchar *buf;\n\n\tif (quiet < 2)\n\t\tfprintf(stderr, "Dumping %s ...\\n", mtd);\n\n\tfd = mtd_check_open(mtd);\n\tif(fd < 0) {\n\t\tfprintf(stderr, "Could not open mtd device: %s\\n", mtd);\n\t\treturn -1;\n\t}\n\n\tif (!size)\n\t\tsize = mtdsize;\n\n\tif (part_offset)\n\t\tlseek(fd, part_offset, SEEK_SET);\n\n\tbuf = malloc(erasesize);\n\tif (!buf)\n\t\treturn -1;\n\n\tdo {\n\t\tint len = (size > erasesize) ? (erasesize) : (size);\n\t\tint rlen = read(fd, buf, len);\n\n\t\tif (rlen < 0) {\n\t\t\tif (errno == EINTR)\n\t\t\t\tcontinue;\n\t\t\tret = -1;\n\t\t\tgoto out;\n\t\t}\n\t\tif (!rlen || rlen != len)\n\t\t\tbreak;\n\t\tif (mtd_block_is_bad(fd, offset)) {\n\t\t\tfprintf(stderr, "skipping bad block at 0x%08x\\n", offset);\n\t\t} else {\n\t\t\tsize -= rlen;\n\t\t\twrite(1, buf, rlen);\n\t\t}\n\t\toffset += rlen;\n\t} while (size > 0);\n\nout:\n\tclose(fd);\n\treturn ret;\n}', 'main': 'int main (int argc, char **argv)\n{\n\tint ch, i, boot, imagefd = 0, force, unlocked;\n\tchar *erase[MAX_ARGS], *device = NULL;\n\tchar *fis_layout = NULL;\n\tsize_t offset = 0, data_size = 0, part_offset = 0, dump_len = 0;\n\tenum {\n\t\tCMD_ERASE,\n\t\tCMD_WRITE,\n\t\tCMD_UNLOCK,\n\t\tCMD_JFFS2WRITE,\n\t\tCMD_FIXTRX,\n\t\tCMD_FIXSEAMA,\n\t\tCMD_FIXWRGG,\n\t\tCMD_VERIFY,\n\t\tCMD_DUMP,\n\t\tCMD_RESETBC,\n\t} cmd = -1;\n\t/* This dynamic legacy tool must never start a firmware transaction. The\n\t * PID1 controller admits only the separate resident helper/session. */\n\tif (argc > 1 && !strcmp(argv[1], "--upgrade-write")) {\n\t\tfputs("mtd_write: firmware protocol moved to the controlled resident upgrade helper\\n", stderr);\n\t\treturn 21;\n\t}\n\n\terase[0] = NULL;\n\tboot = 0;\n\tforce = 0;\n\tbuflen = 0;\n\tquiet = 0;\n\tno_erase = 0;\n\n\twhile ((ch = getopt(argc, argv,\n#ifdef FIS_SUPPORT\n\t\t\t"F:"\n#endif\n\t\t\t"frnqe:d:s:j:p:o:c:l:")) != -1)\n\t\tswitch (ch) {\n\t\t\tcase \'f\':\n\t\t\t\tforce = 1;\n\t\t\t\tbreak;\n\t\t\tcase \'r\':\n\t\t\t\tboot = 1;\n\t\t\t\tbreak;\n\t\t\tcase \'n\':\n\t\t\t\tno_erase = 1;\n\t\t\t\tbreak;\n\t\t\tcase \'j\':\n\t\t\t\tjffs2file = optarg;\n\t\t\t\tbreak;\n\t\t\tcase \'s\':\n\t\t\t\terrno = 0;\n\t\t\t\tjffs2_skip_bytes = strtoul(optarg, 0, 0);\n\t\t\t\tif (errno) {\n\t\t\t\t\t\tfprintf(stderr, "-s: illegal numeric string\\n");\n\t\t\t\t\t\tusage();\n\t\t\t\t}\n\t\t\t\tbreak;\n\t\t\tcase \'q\':\n\t\t\t\tquiet++;\n\t\t\t\tbreak;\n\t\t\tcase \'e\':\n\t\t\t\ti = 0;\n\t\t\t\twhile ((erase[i] != NULL) && ((i + 1) < MAX_ARGS))\n\t\t\t\t\ti++;\n\n\t\t\t\tif (i + 1 >= MAX_ARGS) {\n\t\t\t\t\tfputs("mtd_write: too many pre-erase targets\\n", stderr);\n\t\t\t\t\treturn 21;\n\t\t\t\t}\n\t\t\t\terase[i++] = optarg;\n\t\t\t\terase[i] = NULL;\n\t\t\t\tbreak;\n\t\t\tcase \'d\':\n\t\t\t\tjffs2dir = optarg;\n\t\t\t\tbreak;\n\t\t\tcase \'p\':\n\t\t\t\terrno = 0;\n\t\t\t\tpart_offset = strtoul(optarg, 0, 0);\n\t\t\t\tif (errno) {\n\t\t\t\t\tfprintf(stderr, "-p: illegal numeric string\\n");\n\t\t\t\t\tusage();\n\t\t\t\t}\n\t\t\t\tbreak;\n\t\t\tcase \'l\':\n\t\t\t\terrno = 0;\n\t\t\t\tdump_len = strtoul(optarg, 0, 0);\n\t\t\t\tif (errno) {\n\t\t\t\t\tfprintf(stderr, "-l: illegal numeric string\\n");\n\t\t\t\t\tusage();\n\t\t\t\t}\n\t\t\t\tbreak;\n\t\t\tcase \'o\':\n\t\t\t\terrno = 0;\n\t\t\t\toffset = strtoul(optarg, 0, 0);\n\t\t\t\tif (errno) {\n\t\t\t\t\tfprintf(stderr, "-o: illegal numeric string\\n");\n\t\t\t\t\tusage();\n\t\t\t\t}\n\t\t\t\tbreak;\n\t\t\tcase \'c\':\n\t\t\t\terrno = 0;\n\t\t\t\tdata_size = strtoul(optarg, 0, 0);\n\t\t\t\tif (errno) {\n\t\t\t\t\tfprintf(stderr, "-c: illegal numeric string\\n");\n\t\t\t\t\tusage();\n\t\t\t\t}\n\t\t\t\tbreak;\n#ifdef FIS_SUPPORT\n\t\t\tcase \'F\':\n\t\t\t\tfis_layout = optarg;\n\t\t\t\tbreak;\n#endif\n\t\t\tcase \'?\':\n\t\t\tdefault:\n\t\t\t\tusage();\n\t\t}\n\targc -= optind;\n\targv += optind;\n\n\tif (argc < 2)\n\t\tusage();\n\n#if defined(MTD_K2P_LEGACY_GUARD) && MTD_K2P_LEGACY_GUARD\n\t/* Before mtd_check(), image opens, sync(), pre-erase or any writable MTD\n\t * operation. Classification failure never authorizes a legacy write. */\n\tif (!legacy_firmware_command_allowed(argc, argv, erase, boot)) {\n\t\tfputs("mtd_write: legacy firmware/whole-flash mutation and -r are disabled; use the controlled upgrade transaction\\n", stderr);\n\t\treturn 21;\n\t}\n#endif\n\n\tif ((strcmp(argv[0], "unlock") == 0) && (argc == 2)) {\n\t\tcmd = CMD_UNLOCK;\n\t\tdevice = argv[1];\n\t} else if ((strcmp(argv[0], "erase") == 0) && (argc == 2)) {\n\t\tcmd = CMD_ERASE;\n\t\tdevice = argv[1];\n\t} else if (((strcmp(argv[0], "resetbc") == 0) && (argc == 2)) && mtd_resetbc) {\n\t\tcmd = CMD_RESETBC;\n\t\tdevice = argv[1];\n\t} else if (((strcmp(argv[0], "fixtrx") == 0) && (argc == 2)) && mtd_fixtrx) {\n\t\tcmd = CMD_FIXTRX;\n\t\tdevice = argv[1];\n\t} else if (((strcmp(argv[0], "fixseama") == 0) && (argc == 2)) && mtd_fixseama) {\n\t\tcmd = CMD_FIXSEAMA;\n\t\tdevice = argv[1];\n\t} else if (((strcmp(argv[0], "fixwrgg") == 0) && (argc == 2)) && mtd_fixwrgg) {\n\t\tcmd = CMD_FIXWRGG;\n\t\tdevice = argv[1];\n\t} else if ((strcmp(argv[0], "verify") == 0) && (argc == 3)) {\n\t\tcmd = CMD_VERIFY;\n\t\timagefile = argv[1];\n\t\tdevice = argv[2];\n\t} else if ((strcmp(argv[0], "dump") == 0) && (argc == 2)) {\n\t\tcmd = CMD_DUMP;\n\t\tdevice = argv[1];\n\t} else if ((strcmp(argv[0], "write") == 0) && (argc == 3)) {\n\t\tcmd = CMD_WRITE;\n\t\tdevice = argv[2];\n\n\t\tif (strcmp(argv[1], "-") == 0) {\n\t\t\timagefile = "<stdin>";\n\t\t\timagefd = 0;\n\t\t} else {\n\t\t\timagefile = argv[1];\n\t\t\tif ((imagefd = open(argv[1], O_RDONLY)) < 0) {\n\t\t\t\tfprintf(stderr, "Couldn\'t open image file: %s!\\n", imagefile);\n\t\t\t\texit(1);\n\t\t\t}\n\t\t}\n\n\t\tif (!mtd_check(device)) {\n\t\t\tfprintf(stderr, "Can\'t open device for writing!\\n");\n\t\t\texit(1);\n\t\t}\n\t\t/* check trx file before erasing or writing anything */\n\t\tif (!image_check(imagefd, device) && !force) {\n\t\t\tfprintf(stderr, "Image check failed.\\n");\n\t\t\texit(1);\n\t\t}\n\t} else if ((strcmp(argv[0], "jffs2write") == 0) && (argc == 3)) {\n\t\tcmd = CMD_JFFS2WRITE;\n\t\tdevice = argv[2];\n\n\t\timagefile = argv[1];\n\t\tif (!mtd_check(device)) {\n\t\t\tfprintf(stderr, "Can\'t open device for writing!\\n");\n\t\t\texit(1);\n\t\t}\n\t} else {\n\t\tusage();\n\t}\n\n\tsync();\n\n\ti = 0;\n\tunlocked = 0;\n\twhile (erase[i] != NULL) {\n\t\tmtd_unlock(erase[i]);\n\t\tmtd_erase(erase[i]);\n\t\tif (strcmp(erase[i], device) == 0)\n\t\t\tunlocked = 1;\n\t\ti++;\n\t}\n\n\tswitch (cmd) {\n\t\tcase CMD_UNLOCK:\n\t\t\tif (!unlocked)\n\t\t\t\tmtd_unlock(device);\n\t\t\tbreak;\n\t\tcase CMD_VERIFY:\n\t\t//\tmtd_verify(device, imagefile);\n\t\t\tbreak;\n\t\tcase CMD_DUMP:\n\t\t\tmtd_dump(device, offset, dump_len);\n\t\t\tbreak;\n\t\tcase CMD_ERASE:\n\t\t\tif (!unlocked)\n\t\t\t\tmtd_unlock(device);\n\t\t\tmtd_erase(device);\n\t\t\tbreak;\n\t\tcase CMD_WRITE:\n\t\t\tif (!unlocked)\n\t\t\t\tmtd_unlock(device);\n\t\t\tif (mtd_write(imagefd, device, fis_layout, part_offset) != 0)\n\t\t\t\treturn 1;\n\t\t\tbreak;\n\t\tcase CMD_JFFS2WRITE:\n\t\t\tif (!unlocked)\n\t\t\t\tmtd_unlock(device);\n\t\t\tmtd_write_jffs2(device, imagefile, jffs2dir);\n\t\t\tbreak;\n\t\tcase CMD_FIXTRX:\n\t\t\tif (mtd_fixtrx) {\n\t\t\t\tmtd_fixtrx(device, offset, data_size);\n\t\t\t}\n\t\t\tbreak;\n\t\tcase CMD_RESETBC:\n\t\t\tif (mtd_resetbc) {\n\t\t\t\tmtd_resetbc(device);\n\t\t\t}\n\t\t\tbreak;\n\t\tcase CMD_FIXSEAMA:\n\t\t\tif (mtd_fixseama)\n\t\t\t\tmtd_fixseama(device, 0, data_size);\n\t\t\tbreak;\n\t\tcase CMD_FIXWRGG:\n\t\t\tif (mtd_fixwrgg)\n\t\t\t\tmtd_fixwrgg(device, 0, data_size);\n\t\t\tbreak;\n\t}\n\n\tsync();\n\n\tif (boot)\n\t\tdo_reboot();\n\n\treturn 0;\n}', 'mtd_check': "static int mtd_check(const char *mtd)\n{\n\tchar *next = NULL;\n\tchar *str = NULL;\n\tint fd;\n\n\tif (strchr(mtd, ':')) {\n\t\tstr = strdup(mtd);\n\t\tmtd = str;\n\t}\n\n\tdo {\n\t\tnext = strchr(mtd, ':');\n\t\tif (next) {\n\t\t\t*next = 0;\n\t\t\tnext++;\n\t\t}\n\n\t\tfd = mtd_check_open(mtd);\n\t\tif (fd < 0)\n\t\t\treturn 0;\n\n\t\tif (!buf)\n\t\t\tbuf = malloc(erasesize);\n\n\t\tclose(fd);\n\t\tmtd = next;\n\t} while (next);\n\n\tif (str)\n\t\tfree(str);\n\n\treturn 1;\n}"}


def expected_row(name, baseline=False):
    """Independent byte/range and failure contract; flags are platform values."""
    if name not in (BASELINE_CASES if baseline else CASE_NAMES):
        raise ValueError('case')
    row = dict(case=name,returncode=0,trace='open,metadata,close',
               opens=1,readonly=1,nonblock=1,cloexec=1,path='/dev/mtd/3',
               closes=1,reads=4,writes=4,seeks=0,allocs=1,frees=1,
               metadata=1,output='0123456789ABCDEF',bad_offsets=[])
    if baseline:
        row.update(trace='sync,open,metadata,close,sync',readonly=0,nonblock=0,cloexec=0,frees=0)
        if name in ('short-read','early-eof','read-error'):
            row.update(reads=1,writes=0,output='')
        if name=='write-error':row['output']=''
        if name=='short-write':row['output']='014589CD'
        if name=='seek-error':row['seeks']=1
        if name=='alloc-error':
            row.update(trace='sync,open,metadata,sync',closes=0,reads=0,writes=0,output='')
        if name in ('verify-firmware','verify-storage'):
            row.update(trace='sync,sync',opens=0,readonly=1,path='',closes=0,reads=0,writes=0,allocs=0,metadata=0,output='')
        if name=='dump-preerase':row['trace']='sync,unlock,erase,open,metadata,close,sync'
        if name=='trailing-length':row.update(reads=1,writes=1,output='0')
        return row
    if name=='storage':row['path']='/dev/mtd/6'
    if name=='alias':row['path']='/dev/mtd3'
    if name in ('offset-default','explicit-zero-length'):
        row.update(seeks=1,output='3456789ABCDEF')
    if name in ('unaligned-range','nand-offset'):
        row.update(seeks=1,reads=3,writes=3,output='3456789')
    if name=='last-byte':row.update(seeks=1,reads=1,writes=1,output='F')
    if name=='read-eintr':row['reads']=5
    if name=='short-read':row['reads']=8
    if name=='write-eintr':row['writes']=5
    if name=='short-write':row['writes']=8
    if name=='nand-offset':row['bad_offsets']=[0,4,8]
    no_effects = ('bad-length','negative-length','trailing-length','empty-length','bad-offset',
                  'negative-offset','overflow-offset','verify-firmware','verify-storage','verify-preerase',
                  'dump-preerase','dump-noerase','dump-force','dump-write-offset','dump-jffs',
                  'dump-skip','dump-directory','dump-checksum','reboot-dump','reboot-verify',
                  'protected-preerase','protected-write','old-protocol')
    if name in no_effects:
        row.update(returncode=21 if name in no_effects[-5:] else 1,trace='',opens=0,
                   nonblock=0,cloexec=0,path='',closes=0,reads=0,writes=0,seeks=0,
                   allocs=0,frees=0,metadata=0,output='')
        return row
    failures = ('offset-at-end','offset-beyond-end','range-overflow','huge-range',
                'zero-size','negative-size','zero-erase','negative-erase','open-error',
                'metadata-error','seek-error','wrong-seek','alloc-error','early-eof',
                'read-error','read-again','zero-write','write-error','write-again','close-error','nand-bad')
    if name in failures:
        row.update(returncode=1,trace='open,metadata,close',reads=0,writes=0,
                   allocs=0,frees=0,output='')
        if name=='open-error':row.update(trace='open,open',opens=2,path='/dev/mtd3',closes=0,metadata=0)
        if name in ('seek-error','wrong-seek'):row['seeks']=1
        if name=='alloc-error':row['allocs']=1
        if name in ('early-eof','read-error','read-again'):
            row.update(reads=1,allocs=1,frees=1)
        if name in ('zero-write','write-error','write-again'):
            row.update(reads=1,writes=1,allocs=1,frees=1)
        if name=='close-error':row.update(reads=4,writes=4,allocs=1,frees=1,output='0123456789ABCDEF')
        if name=='nand-bad':row.update(seeks=1,reads=1,writes=1,allocs=1,frees=1,output='3',bad_offsets=[0,4])
    return row


def validate_row(row, baseline=False):
    if not isinstance(row,dict) or not isinstance(row.get('case'),str):
        raise ValueError('row identity')
    expected=expected_row(row['case'],baseline)
    if set(row)!=set(expected)|{'flags'}:raise ValueError('row keys')
    for key,value in expected.items():
        if type(row[key]) is not type(value) or row[key]!=value:
            raise ValueError('row %s %s'%(row['case'],key))
    if type(row['flags']) is not int or row['flags']<0:
        raise ValueError('flags type')
    if any(type(item) is not int for item in row['bad_offsets']):
        raise ValueError('bad block offset type')
    return True
