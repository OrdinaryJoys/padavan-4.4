"""Actual legacy erase/unlock/main with inert metadata and flash callbacks.

Only private ordinary fixtures are opened. No MTD, reboot, host proc or
configuration is touched; baseline function bodies are fixed 6e912 literals.
"""
import hashlib
import json
from pathlib import PurePosixPath
import re
import legacy_firmware_harness as legacy

SOURCE_PATHS = dict(legacy.SOURCE_PATHS)
BASELINE_COMMIT = '6e91276a33d1bd83d416fc8253feb01f30677743'
CASE_ARGS = {
    'erase-ok': ['erase', 'Storage'],
    'unlock-ok': ['unlock', 'Storage'],
    'unlock-error': ['erase', 'Storage'],
    'block-unlock-error': ['erase', 'Storage'],
    'unlock-unsupported': ['erase', 'Storage'],
    'unlock-enotty': ['erase', 'Storage'],
    'erase-error-first': ['erase', 'Storage'],
    'erase-error-second': ['erase', 'Storage'],
    'unlock-close-error': ['erase', 'Storage'],
    'erase-close-error': ['erase', 'Storage'],
    'open-error': ['erase', 'Storage'],
    'erase-open-error': ['erase', 'Storage'],
    'zero-size': ['erase', 'Storage'],
    'zero-erase': ['erase', 'Storage'],
    'negative-size': ['erase', 'Storage'],
    'negative-erase': ['erase', 'Storage'],
    'unaligned-size': ['erase', 'Storage'],
    'oversized-erase': ['erase', 'Storage'],
    'preerase-failure': ['-e', 'Storage', 'write', '@IMAGE', 'Config'],
    'preunlock-failure': ['-e', 'Storage', 'write', '@IMAGE', 'Config'],
    'write-unlock-failure': ['write', '@IMAGE', 'Storage'],
    'jffs-unlock-failure': ['jffs2write', '@IMAGE', 'Storage'],
    'colon-unlock-ok': ['unlock', 'Storage:Config'],
    'colon-unlock-second-error': ['unlock', 'Storage:Config'],
    'colon-alloc-error': ['unlock', 'Storage:Config'],
    'other-board-reboot-error': ['-r', 'erase', 'Storage'],
}
CASE_NAMES = tuple(CASE_ARGS)
BASELINE_CASES = ('erase-ok', 'unlock-error', 'block-unlock-error',
                  'erase-error-first', 'erase-error-second', 'unlock-close-error',
                  'erase-close-error', 'preerase-failure', 'preunlock-failure',
                  'write-unlock-failure', 'jffs-unlock-failure',
                  'other-board-reboot-error')

MODEL = r'''
#include <setjmp.h>
#define MEMUNLOCK 23456
#define MEMERASE 23457
struct erase_info_user {uint32_t start,length;};
static int mtdsize,mutation_opens,mutation_closes,mutation_unlocks,mutation_erases;
static int mutation_bad_range,mutation_frees,mutation_allocs,mutation_exit;
static jmp_buf mutation_escape;
static int mutation_is(const char*n){return !strcmp(case_name,n);}
static int mutation_open(const char*n){
 int fd;mutation_opens++;event("writable-open");
 mtdsize=mutation_is("zero-size")?0:mutation_is("negative-size")?-1:mutation_is("unaligned-size")?15:16;
 erasesize=mutation_is("zero-erase")?0:mutation_is("negative-erase")?-4:mutation_is("oversized-erase")?32:4;
 if(mutation_is("open-error")||(mutation_is("erase-open-error")&&mutation_opens==2)){errno=EACCES;return -1;}
 fd=fixture_fd(FIXTURE_DEVICE,O_RDWR);(void)n;return fd;
}
static int mutation_close(int fd){int device=is_device(fd),r=close(fd);if(device){mutation_closes++;event("close");if((mutation_is("unlock-close-error")&&mutation_closes==1)||(mutation_is("erase-close-error")&&mutation_closes==2)){errno=EIO;return -1;}}return r;}
static int mutation_ioctl(int fd,unsigned long command,void*arg){
 struct erase_info_user*x=arg;
 if(!is_device(fd)||(command!=MEMUNLOCK&&command!=MEMERASE))abort();
 if(x->start>16||!x->length||x->length>16-x->start)mutation_bad_range++;
 if(command==MEMUNLOCK){mutation_unlocks++;event("unlock");
  if(mutation_is("unlock-unsupported")){errno=EOPNOTSUPP;return -1;}
  if(mutation_is("unlock-enotty")){errno=ENOTTY;return -1;}
  if(mutation_is("unlock-error")||mutation_is("preunlock-failure")||mutation_is("write-unlock-failure")||mutation_is("jffs-unlock-failure")||(mutation_is("block-unlock-error")&&x->length==4)||(mutation_is("colon-unlock-second-error")&&mutation_opens==2)){errno=EIO;return -1;}
  return 0;
 }
 mutation_erases++;event("erase");
 if(mutation_is("erase-error-first")||mutation_is("preerase-failure")||mutation_is("other-board-reboot-error")||(mutation_is("erase-error-second")&&mutation_erases==2)){errno=EIO;return -1;}
 return 0;
}
static char*mutation_strdup(const char*s){mutation_allocs++;if(mutation_is("colon-alloc-error"))return NULL;return strdup(s);}
static void mutation_free(void*p){if(p)mutation_frees++;free(p);}
static void mutation_abort(int code){mutation_exit=code;longjmp(mutation_escape,1);}
'''


def actual_functions(texts):
    return {name: {'source': 'mtd', 'body': legacy.function(texts['mtd'], name)}
            for name in ('mtd_unlock', 'mtd_erase', 'do_reboot', 'main')}


def generate_source(texts, fixture_root, owner_uid=0, baseline=False, disabled_oracle=False):
    if (set(texts) != set(SOURCE_PATHS) or type(baseline) is not bool or
            type(disabled_oracle) is not bool or (baseline and disabled_oracle)):
        raise ValueError('Exact source keys and baseline boolean required')
    if (not isinstance(fixture_root, str) or not PurePosixPath(fixture_root).is_absolute()
            or any(ord(c) < 32 or ord(c) > 126 for c in fixture_root)):
        raise ValueError('Absolute ASCII fixture root required')
    if type(owner_uid) is not int or owner_uid < 0 or owner_uid > 0xffffffff:
        raise ValueError('Typed fixture owner required')
    source = texts['mtd']
    if baseline:
        for name, body in BASELINE_FUNCTIONS.items():
            if hashlib.sha256(body.encode()).hexdigest() != BASELINE_FUNCTIONS_SHA256[name]:
                raise ValueError('Changed literal mutation baseline: ' + name)
            source = source.replace(legacy.function(source, name), body, 1)
    selected = dict(texts, mtd=source)
    previous = legacy.CASE_ARGS
    try:
        legacy.CASE_ARGS = CASE_ARGS
        code = legacy.generate_source(selected, fixture_root, owner_uid,
                                      enabled=False)
    finally:
        legacy.CASE_ARGS = previous
    # Primary writes and JFFS appends are recording callbacks in this focused
    # erase-dispatch model. Actual legacy writer IO has its separate gate.
    code = code.replace(legacy.function(source, 'mtd_write'),
                        'static int mtd_write(int fd,const char*m,char*f,size_t o){event("primary-write");return 0;}', 1)
    code = code.replace('static int (*trx_fixup)(int,const char*)=fixup;\n', '', 1)
    for pattern in (r'static int mtd_check_open\(const char\*n\)\{[^\n]*\}\n',
                    r'static int mtd_unlock\(const char\*n\)\{[^\n]*\}\n',
                    r'static int mtd_erase\(const char\*n\)\{[^\n]*\}\n'):
        code, count = re.subn(pattern, '', code, count=1)
        if count != 1:
            raise ValueError('Known inert mutation seam required')
    # Model uses real ordinary-file helpers, declared in the locked legacy
    # prelude; only the actual mutation functions below receive IO macros.
    inject = MODEL + '\n#define mtd_check_open mutation_open\n'
    inject += '#define close mutation_close\n#define ioctl mutation_ioctl\n'
    inject += '#define strdup mutation_strdup\n#define free mutation_free\n'
    inject += '#define exit mutation_abort\n'
    inject += legacy.function(source, 'mtd_unlock') + '\n'
    inject += legacy.function(source, 'mtd_erase') + '\n'
    inject += '#undef close\n#undef ioctl\n#undef strdup\n#undef free\n'
    code = code.replace('#define read inert_read', inject + '\n#define read inert_read', 1)
    # Rename the old harmless mtd-check open seam before its callers compile.
    code = code.replace('result=legacy_main(cases[which].argc,cases[which].argv);',
                        'if(!setjmp(mutation_escape))result=legacy_main(cases[which].argc,cases[which].argv);else result=mutation_exit;',1)
    marker = 'static void write_fixture(const char*p,const char*s)'
    code = code.replace(marker, '#undef exit\n#undef mtd_check_open\n' + marker, 1)
    start = code.index(' printf("{\\"case')
    end = code.index('\n return 0;', start)
    code = code[:start] + r''' printf("{\"case\":\"%s\",\"returncode\":%d,\"trace\":\"%s\",\"opens\":%d,\"closes\":%d,\"unlocks\":%d,\"erases\":%d,\"bad_range\":%d,\"allocs\":%d,\"frees\":%d}\n",case_name,result,trace,mutation_opens,mutation_closes,mutation_unlocks,mutation_erases,mutation_bad_range,mutation_allocs,mutation_frees);''' + code[end:]
    if disabled_oracle:
        code = code.replace('if(!setjmp(mutation_escape))result=legacy_main(cases[which].argc,cases[which].argv);else result=mutation_exit;',
                            'result=0;', 1)
    return code


def source_hashes(texts):
    return {key: hashlib.sha256(value.encode()).hexdigest() for key, value in texts.items()}

BASELINE_FUNCTIONS = {'mtd_unlock': 'static int\nmtd_unlock(const char *mtd)\n{\n\tstruct erase_info_user mtdLockInfo;\n\tchar *next = NULL;\n\tchar *str = NULL;\n\tint fd;\n\n\tif (strchr(mtd, \':\')) {\n\t\tstr = strdup(mtd);\n\t\tmtd = str;\n\t}\n\n\tdo {\n\t\tnext = strchr(mtd, \':\');\n\t\tif (next) {\n\t\t\t*next = 0;\n\t\t\tnext++;\n\t\t}\n\n\t\tfd = mtd_check_open(mtd);\n\t\tif(fd < 0) {\n\t\t\tfprintf(stderr, "Could not open mtd device: %s\\n", mtd);\n\t\t\texit(1);\n\t\t}\n\n\t\tif (quiet < 2)\n\t\t\tfprintf(stderr, "Unlocking %s ...\\n", mtd);\n\n\t\tmtdLockInfo.start = 0;\n\t\tmtdLockInfo.length = mtdsize;\n\t\tioctl(fd, MEMUNLOCK, &mtdLockInfo);\n\t\tclose(fd);\n\t\tmtd = next;\n\t} while (next);\n\n\tif (str)\n\t\tfree(str);\n\n\treturn 0;\n}', 'mtd_erase': 'static int\nmtd_erase(const char *mtd)\n{\n\tint fd;\n\tstruct erase_info_user mtdEraseInfo;\n\n\tif (quiet < 2)\n\t\tfprintf(stderr, "Erasing %s ...\\n", mtd);\n\n\tfd = mtd_check_open(mtd);\n\tif(fd < 0) {\n\t\tfprintf(stderr, "Could not open mtd device: %s\\n", mtd);\n\t\texit(1);\n\t}\n\n\tmtdEraseInfo.length = erasesize;\n\n\tfor (mtdEraseInfo.start = 0;\n\t\t mtdEraseInfo.start < mtdsize;\n\t\t mtdEraseInfo.start += erasesize) {\n\t\tif (mtd_block_is_bad(fd, mtdEraseInfo.start)) {\n\t\t\tif (!quiet)\n\t\t\t\tfprintf(stderr, "\\nSkipping bad block at 0x%x   ", mtdEraseInfo.start);\n\t\t} else {\n\t\t\tioctl(fd, MEMUNLOCK, &mtdEraseInfo);\n\t\t\tif(ioctl(fd, MEMERASE, &mtdEraseInfo))\n\t\t\t\tfprintf(stderr, "Failed to erase block on %s at 0x%x\\n", mtd, mtdEraseInfo.start);\n\t\t}\n\t}\n\n\tclose(fd);\n\treturn 0;\n\n}', 'main': 'int main (int argc, char **argv)\n{\n\tint ch, i, boot, imagefd = 0, force, unlocked, dump_incompatible = 0;\n\tchar *erase[MAX_ARGS], *device = NULL;\n\tchar *fis_layout = NULL;\n\tchar *numeric_end;\n\tsize_t offset = 0, data_size = 0, part_offset = 0, dump_len = 0;\n\tenum {\n\t\tCMD_ERASE,\n\t\tCMD_WRITE,\n\t\tCMD_UNLOCK,\n\t\tCMD_JFFS2WRITE,\n\t\tCMD_FIXTRX,\n\t\tCMD_FIXSEAMA,\n\t\tCMD_FIXWRGG,\n\t\tCMD_VERIFY,\n\t\tCMD_DUMP,\n\t\tCMD_RESETBC,\n\t} cmd = -1;\n\t/* This dynamic legacy tool must never start a firmware transaction. The\n\t * PID1 controller admits only the separate resident helper/session. */\n\tif (argc > 1 && !strcmp(argv[1], "--upgrade-write")) {\n\t\tfputs("mtd_write: firmware protocol moved to the controlled resident upgrade helper\\n", stderr);\n\t\treturn 21;\n\t}\n\n\terase[0] = NULL;\n\tboot = 0;\n\tforce = 0;\n\tbuflen = 0;\n\tquiet = 0;\n\tno_erase = 0;\n\n\twhile ((ch = getopt(argc, argv,\n#ifdef FIS_SUPPORT\n\t\t\t"F:"\n#endif\n\t\t\t"frnqe:d:s:j:p:o:c:l:")) != -1)\n\t\tswitch (ch) {\n\t\t\tcase \'f\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\tforce = 1;\n\t\t\t\tbreak;\n\t\t\tcase \'r\':\n\t\t\t\tboot = 1;\n\t\t\t\tbreak;\n\t\t\tcase \'n\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\tno_erase = 1;\n\t\t\t\tbreak;\n\t\t\tcase \'j\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\tjffs2file = optarg;\n\t\t\t\tbreak;\n\t\t\tcase \'s\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\terrno = 0;\n\t\t\t\tjffs2_skip_bytes = strtoul(optarg, 0, 0);\n\t\t\t\tif (errno) {\n\t\t\t\t\t\tfprintf(stderr, "-s: illegal numeric string\\n");\n\t\t\t\t\t\tusage();\n\t\t\t\t}\n\t\t\t\tbreak;\n\t\t\tcase \'q\':\n\t\t\t\tquiet++;\n\t\t\t\tbreak;\n\t\t\tcase \'e\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\ti = 0;\n\t\t\t\twhile ((erase[i] != NULL) && ((i + 1) < MAX_ARGS))\n\t\t\t\t\ti++;\n\n\t\t\t\tif (i + 1 >= MAX_ARGS) {\n\t\t\t\t\tfputs("mtd_write: too many pre-erase targets\\n", stderr);\n\t\t\t\t\treturn 21;\n\t\t\t\t}\n\t\t\t\terase[i++] = optarg;\n\t\t\t\terase[i] = NULL;\n\t\t\t\tbreak;\n\t\t\tcase \'d\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\tjffs2dir = optarg;\n\t\t\t\tbreak;\n\t\t\tcase \'p\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\terrno = 0;\n\t\t\t\tpart_offset = strtoul(optarg, 0, 0);\n\t\t\t\tif (errno) {\n\t\t\t\t\tfprintf(stderr, "-p: illegal numeric string\\n");\n\t\t\t\t\tusage();\n\t\t\t\t}\n\t\t\t\tbreak;\n\t\t\tcase \'l\':\n\t\t\t\terrno = 0;\n\t\t\t\tdump_len = strtoul(optarg, &numeric_end, 0);\n\t\t\t\tif (errno || optarg[0] < \'0\' || optarg[0] > \'9\' || *numeric_end) {\n\t\t\t\t\tfprintf(stderr, "-l: illegal numeric string\\n");\n\t\t\t\t\treturn 1;\n\t\t\t\t}\n\t\t\t\tbreak;\n\t\t\tcase \'o\':\n\t\t\t\terrno = 0;\n\t\t\t\toffset = strtoul(optarg, &numeric_end, 0);\n\t\t\t\tif (errno || optarg[0] < \'0\' || optarg[0] > \'9\' || *numeric_end) {\n\t\t\t\t\tfprintf(stderr, "-o: illegal numeric string\\n");\n\t\t\t\t\treturn 1;\n\t\t\t\t}\n\t\t\t\tbreak;\n\t\t\tcase \'c\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\terrno = 0;\n\t\t\t\tdata_size = strtoul(optarg, 0, 0);\n\t\t\t\tif (errno) {\n\t\t\t\t\tfprintf(stderr, "-c: illegal numeric string\\n");\n\t\t\t\t\tusage();\n\t\t\t\t}\n\t\t\t\tbreak;\n#ifdef FIS_SUPPORT\n\t\t\tcase \'F\':\n\t\t\t\tdump_incompatible = 1;\n\t\t\t\tfis_layout = optarg;\n\t\t\t\tbreak;\n#endif\n\t\t\tcase \'?\':\n\t\t\tdefault:\n\t\t\t\tusage();\n\t\t}\n\targc -= optind;\n\targv += optind;\n\n\tif (argc < 2)\n\t\tusage();\n\n#if defined(MTD_K2P_LEGACY_GUARD) && MTD_K2P_LEGACY_GUARD\n\t/* Before mtd_check(), image opens, sync(), pre-erase or any writable MTD\n\t * operation. Classification failure never authorizes a legacy write. */\n\tif (!legacy_firmware_command_allowed(argc, argv, erase, boot)) {\n\t\tfputs("mtd_write: legacy firmware/whole-flash mutation and -r are disabled; use the controlled upgrade transaction\\n", stderr);\n\t\treturn 21;\n\t}\n#endif\n\n\tif ((strcmp(argv[0], "unlock") == 0) && (argc == 2)) {\n\t\tcmd = CMD_UNLOCK;\n\t\tdevice = argv[1];\n\t} else if ((strcmp(argv[0], "erase") == 0) && (argc == 2)) {\n\t\tcmd = CMD_ERASE;\n\t\tdevice = argv[1];\n\t} else if (((strcmp(argv[0], "resetbc") == 0) && (argc == 2)) && mtd_resetbc) {\n\t\tcmd = CMD_RESETBC;\n\t\tdevice = argv[1];\n\t} else if (((strcmp(argv[0], "fixtrx") == 0) && (argc == 2)) && mtd_fixtrx) {\n\t\tcmd = CMD_FIXTRX;\n\t\tdevice = argv[1];\n\t} else if (((strcmp(argv[0], "fixseama") == 0) && (argc == 2)) && mtd_fixseama) {\n\t\tcmd = CMD_FIXSEAMA;\n\t\tdevice = argv[1];\n\t} else if (((strcmp(argv[0], "fixwrgg") == 0) && (argc == 2)) && mtd_fixwrgg) {\n\t\tcmd = CMD_FIXWRGG;\n\t\tdevice = argv[1];\n\t} else if ((strcmp(argv[0], "verify") == 0) && (argc == 3)) {\n\t\t/* The implementation below is disabled. Never claim verification or\n\t\t * reach sync/pre-erase for an operation which cannot verify bytes. */\n\t\tfputs("mtd_write: verify is not implemented; use independent exact readback comparison\\n", stderr);\n\t\treturn 1;\n\t} else if ((strcmp(argv[0], "dump") == 0) && (argc == 2)) {\n\t\t/* A backup command must not erase first or silently accept writer\n\t\t * options. Only quiet, offset and length describe a dump. */\n\t\tif (dump_incompatible) {\n\t\t\tfputs("mtd_write: dump accepts only -q, -o and -l\\n", stderr);\n\t\t\treturn 1;\n\t\t}\n\t\tcmd = CMD_DUMP;\n\t\tdevice = argv[1];\n\t} else if ((strcmp(argv[0], "write") == 0) && (argc == 3)) {\n\t\tcmd = CMD_WRITE;\n\t\tdevice = argv[2];\n\n\t\tif (strcmp(argv[1], "-") == 0) {\n\t\t\timagefile = "<stdin>";\n\t\t\timagefd = 0;\n\t\t} else {\n\t\t\timagefile = argv[1];\n\t\t\tif ((imagefd = open(argv[1], O_RDONLY)) < 0) {\n\t\t\t\tfprintf(stderr, "Couldn\'t open image file: %s!\\n", imagefile);\n\t\t\t\texit(1);\n\t\t\t}\n\t\t}\n\n\t\tif (!mtd_check(device)) {\n\t\t\tfprintf(stderr, "Can\'t open device for writing!\\n");\n\t\t\texit(1);\n\t\t}\n\t\t/* check trx file before erasing or writing anything */\n\t\tif (!image_check(imagefd, device) && !force) {\n\t\t\tfprintf(stderr, "Image check failed.\\n");\n\t\t\texit(1);\n\t\t}\n\t} else if ((strcmp(argv[0], "jffs2write") == 0) && (argc == 3)) {\n\t\tcmd = CMD_JFFS2WRITE;\n\t\tdevice = argv[2];\n\n\t\timagefile = argv[1];\n\t\tif (!mtd_check(device)) {\n\t\t\tfprintf(stderr, "Can\'t open device for writing!\\n");\n\t\t\texit(1);\n\t\t}\n\t} else {\n\t\tusage();\n\t}\n\n\t/* Read-only backup never waits for unrelated global writeback or enters\n\t * the mutating command/reboot pipeline. The legacy guard ran above. */\n\tif (cmd == CMD_DUMP)\n\t\treturn mtd_dump(device, offset, dump_len) != 0;\n\n\tsync();\n\n\ti = 0;\n\tunlocked = 0;\n\twhile (erase[i] != NULL) {\n\t\tmtd_unlock(erase[i]);\n\t\tmtd_erase(erase[i]);\n\t\tif (strcmp(erase[i], device) == 0)\n\t\t\tunlocked = 1;\n\t\ti++;\n\t}\n\n\tswitch (cmd) {\n\t\tcase CMD_UNLOCK:\n\t\t\tif (!unlocked)\n\t\t\t\tmtd_unlock(device);\n\t\t\tbreak;\n\t\tcase CMD_VERIFY:\n\t\t\treturn 1;\n\t\tcase CMD_DUMP:\n\t\t\tif (mtd_dump(device, offset, dump_len) != 0)\n\t\t\t\treturn 1;\n\t\t\tbreak;\n\t\tcase CMD_ERASE:\n\t\t\tif (!unlocked)\n\t\t\t\tmtd_unlock(device);\n\t\t\tmtd_erase(device);\n\t\t\tbreak;\n\t\tcase CMD_WRITE:\n\t\t\tif (!unlocked)\n\t\t\t\tmtd_unlock(device);\n\t\t\tif (mtd_write(imagefd, device, fis_layout, part_offset) != 0)\n\t\t\t\treturn 1;\n\t\t\tbreak;\n\t\tcase CMD_JFFS2WRITE:\n\t\t\tif (!unlocked)\n\t\t\t\tmtd_unlock(device);\n\t\t\tmtd_write_jffs2(device, imagefile, jffs2dir);\n\t\t\tbreak;\n\t\tcase CMD_FIXTRX:\n\t\t\tif (mtd_fixtrx) {\n\t\t\t\tmtd_fixtrx(device, offset, data_size);\n\t\t\t}\n\t\t\tbreak;\n\t\tcase CMD_RESETBC:\n\t\t\tif (mtd_resetbc) {\n\t\t\t\tmtd_resetbc(device);\n\t\t\t}\n\t\t\tbreak;\n\t\tcase CMD_FIXSEAMA:\n\t\t\tif (mtd_fixseama)\n\t\t\t\tmtd_fixseama(device, 0, data_size);\n\t\t\tbreak;\n\t\tcase CMD_FIXWRGG:\n\t\t\tif (mtd_fixwrgg)\n\t\t\t\tmtd_fixwrgg(device, 0, data_size);\n\t\t\tbreak;\n\t}\n\n\tsync();\n\n\tif (boot)\n\t\tdo_reboot();\n\n\treturn 0;\n}', 'do_reboot': 'static void do_reboot(void)\n{\n\tfprintf(stderr, "Rebooting ...\\n");\n\tfflush(stderr);\n\n\t/* try regular reboot method first */\n\tsystem("/sbin/reboot");\n\tsleep(2);\n\n\t/* if we\'re still alive at this point, force the kernel to reboot */\n\tsyscall(SYS_reboot,LINUX_REBOOT_MAGIC1,LINUX_REBOOT_MAGIC2,LINUX_REBOOT_CMD_RESTART,NULL);\n}'}
BASELINE_FUNCTIONS_SHA256 = {'mtd_unlock': 'fd773815ac9bbbf70d460da4e619da05aa899afc6ec676f63d38f203b7ab8224', 'mtd_erase': '2b071665543a53f94370f5a1a10b46fb48b9b316ec3acd08c999f81d966975eb', 'main': '478d67ce44d3e3f2638a0f271b8070b9a97f204f6eeeae0f31529badd523a36d', 'do_reboot': '5de54df63578744f1ae75ea668361c821c2bfaa0f85c165ab142d3b6c81b70c5'}

EXPECTED = {'erase-ok': {'case': 'erase-ok', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'unlock-ok': {'case': 'unlock-ok', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,sync', 'opens': 1, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'unlock-error': {'case': 'unlock-error', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close', 'opens': 1, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'block-unlock-error': {'case': 'block-unlock-error', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,close', 'opens': 2, 'closes': 2, 'unlocks': 2, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'unlock-unsupported': {'case': 'unlock-unsupported', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'unlock-enotty': {'case': 'unlock-enotty', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'erase-error-first': {'case': 'erase-error-first', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,close', 'opens': 2, 'closes': 2, 'unlocks': 2, 'erases': 1, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'erase-error-second': {'case': 'erase-error-second', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,close', 'opens': 2, 'closes': 2, 'unlocks': 3, 'erases': 2, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'unlock-close-error': {'case': 'unlock-close-error', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close', 'opens': 1, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'erase-close-error': {'case': 'erase-close-error', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'open-error': {'case': 'open-error', 'returncode': 1, 'trace': 'sync,writable-open', 'opens': 1, 'closes': 0, 'unlocks': 0, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'erase-open-error': {'case': 'erase-open-error', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open', 'opens': 2, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'zero-size': {'case': 'zero-size', 'returncode': 1, 'trace': 'sync,writable-open,close', 'opens': 1, 'closes': 1, 'unlocks': 0, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'zero-erase': {'case': 'zero-erase', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,close', 'opens': 2, 'closes': 2, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'negative-size': {'case': 'negative-size', 'returncode': 1, 'trace': 'sync,writable-open,close', 'opens': 1, 'closes': 1, 'unlocks': 0, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'negative-erase': {'case': 'negative-erase', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,close', 'opens': 2, 'closes': 2, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'unaligned-size': {'case': 'unaligned-size', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,close', 'opens': 2, 'closes': 2, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'oversized-erase': {'case': 'oversized-erase', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,close', 'opens': 2, 'closes': 2, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'preerase-failure': {'case': 'preerase-failure', 'returncode': 1, 'trace': 'mtd-check,sync,writable-open,unlock,close,writable-open,unlock,erase,close', 'opens': 2, 'closes': 2, 'unlocks': 2, 'erases': 1, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'preunlock-failure': {'case': 'preunlock-failure', 'returncode': 1, 'trace': 'mtd-check,sync,writable-open,unlock,close', 'opens': 1, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'write-unlock-failure': {'case': 'write-unlock-failure', 'returncode': 1, 'trace': 'mtd-check,sync,writable-open,unlock,close', 'opens': 1, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'jffs-unlock-failure': {'case': 'jffs-unlock-failure', 'returncode': 1, 'trace': 'mtd-check,sync,writable-open,unlock,close', 'opens': 1, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'colon-unlock-ok': {'case': 'colon-unlock-ok', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 2, 'erases': 0, 'bad_range': 0, 'allocs': 1, 'frees': 1}, 'colon-unlock-second-error': {'case': 'colon-unlock-second-error', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,close', 'opens': 2, 'closes': 2, 'unlocks': 2, 'erases': 0, 'bad_range': 0, 'allocs': 1, 'frees': 1}, 'colon-alloc-error': {'case': 'colon-alloc-error', 'returncode': 1, 'trace': 'sync', 'opens': 0, 'closes': 0, 'unlocks': 0, 'erases': 0, 'bad_range': 0, 'allocs': 1, 'frees': 0}, 'other-board-reboot-error': {'case': 'other-board-reboot-error', 'returncode': 1, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,close', 'opens': 2, 'closes': 2, 'unlocks': 2, 'erases': 1, 'bad_range': 0, 'allocs': 0, 'frees': 0}}
BASELINE_EXPECTED = {'erase-ok': {'case': 'erase-ok', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'unlock-error': {'case': 'unlock-error', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'block-unlock-error': {'case': 'block-unlock-error', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'erase-error-first': {'case': 'erase-error-first', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'erase-error-second': {'case': 'erase-error-second', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'unlock-close-error': {'case': 'unlock-close-error', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'erase-close-error': {'case': 'erase-close-error', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'preerase-failure': {'case': 'preerase-failure', 'returncode': 0, 'trace': 'mtd-check,sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,writable-open,unlock,close,primary-write,sync', 'opens': 3, 'closes': 3, 'unlocks': 6, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'preunlock-failure': {'case': 'preunlock-failure', 'returncode': 0, 'trace': 'mtd-check,sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,writable-open,unlock,close,primary-write,sync', 'opens': 3, 'closes': 3, 'unlocks': 6, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'write-unlock-failure': {'case': 'write-unlock-failure', 'returncode': 0, 'trace': 'mtd-check,sync,writable-open,unlock,close,primary-write,sync', 'opens': 1, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'jffs-unlock-failure': {'case': 'jffs-unlock-failure', 'returncode': 0, 'trace': 'mtd-check,sync,writable-open,unlock,close,jffs2write,sync', 'opens': 1, 'closes': 1, 'unlocks': 1, 'erases': 0, 'bad_range': 0, 'allocs': 0, 'frees': 0}, 'other-board-reboot-error': {'case': 'other-board-reboot-error', 'returncode': 0, 'trace': 'sync,writable-open,unlock,close,writable-open,unlock,erase,unlock,erase,unlock,erase,unlock,erase,close,sync,system-reboot,sleep2,raw-reboot', 'opens': 2, 'closes': 2, 'unlocks': 5, 'erases': 4, 'bad_range': 0, 'allocs': 0, 'frees': 0}}


def validate_row(row, baseline=False):
    expected = BASELINE_EXPECTED if baseline else EXPECTED
    if type(row) is not dict or row.get('case') not in expected:
        raise ValueError('Mutation row identity')
    wanted = expected[row['case']]
    if set(row) != set(wanted):
        raise ValueError('Mutation row fields')
    for key, value in wanted.items():
        if type(row[key]) is not type(value) or row[key] != value:
            raise ValueError('Mutation row value: ' + key)
    return True
