#!/usr/bin/env python3
"""Pure actual-kernel-body SPI completion adapter. No hardware or host I/O on import.

SPI transport/status/locking, address serialization, userspace copying and allocation
are explicit inert seams. The real controller/MMIO and NAND/SST paths are not run.
"""
import hashlib
import json
import re
SOURCE_PATHS = {'m25p': 'trunk/linux-4.4.x/drivers/mtd/devices/m25p80.c', 'nor': 'trunk/linux-4.4.x/drivers/mtd/spi-nor/spi-nor.c', 'core': 'trunk/linux-4.4.x/drivers/mtd/mtdcore.c', 'char': 'trunk/linux-4.4.x/drivers/mtd/mtdchar.c'}
FUNCTIONS = {'m25p': ('m25p_cmdsz', 'm25p80_write', 'm25p80_read', 'm25p80_erase'), 'nor': ('spi_nor_write_page', 'spi_nor_write', 'spi_nor_erase'), 'core': ('mtd_write',), 'char': ('mtdchar_read', 'mtdchar_write')}

def extract(text, name):
    match = re.search(r'(?:static\s+)?(?:inline\s+)?(?:void|int|ssize_t)\s+\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{', text)
    if not match:
        raise ValueError('Missing actual kernel function: ' + name)
    opening = text.index('{', match.start())
    depth = 0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*|[{}]', text[opening:]):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if depth == 0:
                return text[match.start():opening + token.end()]
    raise ValueError('Unterminated actual kernel function: ' + name)

def actual_functions(texts):
    return {name: {'source_key': key, 'body': extract(texts[key], name)}
            for key, names in FUNCTIONS.items() for name in names}

BASELINE_COMMIT = "309080edaec3881af3de869421c87141c056b0b2"
BASELINE_FUNCTIONS = {'m25p_cmdsz': 'static int m25p_cmdsz(struct spi_nor *nor)\n{\n\treturn 1 + nor->addr_width;\n}', 'm25p80_write': 'static void m25p80_write(struct spi_nor *nor, loff_t to, size_t len,\n\t\t\tsize_t *retlen, const u_char *buf)\n{\n\tstruct m25p *flash = nor->priv;\n\tstruct spi_device *spi = flash->spi;\n\tstruct spi_transfer t[2] = {};\n\tstruct spi_message m;\n\tint cmd_sz = m25p_cmdsz(nor);\n\n\tspi_message_init(&m);\n\n\tif (nor->program_opcode == SPINOR_OP_AAI_WP && nor->sst_write_second)\n\t\tcmd_sz = 1;\n\n\tflash->command[0] = nor->program_opcode;\n\tm25p_addr2cmd(nor, to, flash->command);\n\n\tt[0].tx_buf = flash->command;\n\tt[0].len = cmd_sz;\n\tspi_message_add_tail(&t[0], &m);\n\n\tt[1].tx_buf = buf;\n\tt[1].len = len;\n\tspi_message_add_tail(&t[1], &m);\n\n\tspi_sync(spi, &m);\n\n\t*retlen += m.actual_length - cmd_sz;\n}', 'm25p80_read': 'static int m25p80_read(struct spi_nor *nor, loff_t from, size_t len,\n\t\t\tsize_t *retlen, u_char *buf)\n{\n\tstruct m25p *flash = nor->priv;\n\tstruct spi_device *spi = flash->spi;\n\tstruct spi_transfer t[2];\n\tstruct spi_message m;\n\tunsigned int dummy = nor->read_dummy;\n\n\t/* convert the dummy cycles to the number of bytes */\n\tdummy /= 8;\n\n\tspi_message_init(&m);\n\tmemset(t, 0, (sizeof t));\n\n\tflash->command[0] = nor->read_opcode;\n\tm25p_addr2cmd(nor, from, flash->command);\n\n\tt[0].tx_buf = flash->command;\n\tt[0].len = m25p_cmdsz(nor) + dummy;\n\tspi_message_add_tail(&t[0], &m);\n\n\tt[1].rx_buf = buf;\n\tt[1].rx_nbits = m25p80_rx_nbits(nor);\n\tt[1].len = len;\n\tspi_message_add_tail(&t[1], &m);\n\n\tspi_sync(spi, &m);\n\n\t*retlen = m.actual_length - m25p_cmdsz(nor) - dummy;\n\treturn 0;\n}', 'm25p80_erase': 'static int m25p80_erase(struct spi_nor *nor, loff_t offset)\n{\n\tstruct m25p *flash = nor->priv;\n\n\tdev_dbg(nor->dev, "%dKiB at 0x%08x\\n",\n\t\tflash->spi_nor.mtd.erasesize / 1024, (u32)offset);\n\n\t/* Set up command buffer. */\n\tflash->command[0] = nor->erase_opcode;\n\tm25p_addr2cmd(nor, offset, flash->command);\n\n\tspi_write(flash->spi, flash->command, m25p_cmdsz(nor));\n\n\treturn 0;\n}', 'spi_nor_write': 'static int spi_nor_write(struct mtd_info *mtd, loff_t to, size_t len,\n\tsize_t *retlen, const u_char *buf)\n{\n\tstruct spi_nor *nor = mtd_to_spi_nor(mtd);\n\tu32 page_offset, page_size, i;\n\tint ret;\n\n\tdev_dbg(nor->dev, "to 0x%08x, len %zd\\n", (u32)to, len);\n\n\tret = spi_nor_lock_and_prep(nor, SPI_NOR_OPS_WRITE);\n\tif (ret)\n\t\treturn ret;\n\n\twrite_enable(nor);\n\n\tpage_offset = to & (nor->page_size - 1);\n\n\t/* do all the bytes fit onto one page? */\n\tif (page_offset + len <= nor->page_size) {\n\t\tnor->write(nor, to, len, retlen, buf);\n\t} else {\n\t\t/* the size of data remaining on the first page */\n\t\tpage_size = nor->page_size - page_offset;\n\t\tnor->write(nor, to, page_size, retlen, buf);\n\n\t\t/* write everything in nor->page_size chunks */\n\t\tfor (i = page_size; i < len; i += page_size) {\n\t\t\tpage_size = len - i;\n\t\t\tif (page_size > nor->page_size)\n\t\t\t\tpage_size = nor->page_size;\n\n\t\t\tret = spi_nor_wait_till_ready(nor);\n\t\t\tif (ret)\n\t\t\t\tgoto write_err;\n\n\t\t\twrite_enable(nor);\n\n\t\t\tnor->write(nor, to + i, page_size, retlen, buf + i);\n\t\t}\n\t}\n\n\tret = spi_nor_wait_till_ready(nor);\nwrite_err:\n\tspi_nor_unlock_and_unprep(nor, SPI_NOR_OPS_WRITE);\n\treturn ret;\n}', 'spi_nor_erase': 'static int spi_nor_erase(struct mtd_info *mtd, struct erase_info *instr)\n{\n\tstruct spi_nor *nor = mtd_to_spi_nor(mtd);\n\tu32 addr, len;\n\tuint32_t rem;\n\tint ret;\n\n\tdev_dbg(nor->dev, "at 0x%llx, len %lld\\n", (long long)instr->addr,\n\t\t\t(long long)instr->len);\n\n\tdiv_u64_rem(instr->len, mtd->erasesize, &rem);\n\tif (rem)\n\t\treturn -EINVAL;\n\n\taddr = instr->addr;\n\tlen = instr->len;\n\n\tret = spi_nor_lock_and_prep(nor, SPI_NOR_OPS_ERASE);\n\tif (ret)\n\t\treturn ret;\n\n\t/* whole-chip erase? */\n\tif (len == mtd->size) {\n\t\tunsigned long timeout;\n\n\t\twrite_enable(nor);\n\n\t\tif (erase_chip(nor)) {\n\t\t\tret = -EIO;\n\t\t\tgoto erase_err;\n\t\t}\n\n\t\t/*\n\t\t * Scale the timeout linearly with the size of the flash, with\n\t\t * a minimum calibrated to an old 2MB flash. We could try to\n\t\t * pull these from CFI/SFDP, but these values should be good\n\t\t * enough for now.\n\t\t */\n\t\ttimeout = max(CHIP_ERASE_2MB_READY_WAIT_JIFFIES,\n\t\t\t      CHIP_ERASE_2MB_READY_WAIT_JIFFIES *\n\t\t\t      (unsigned long)(mtd->size / SZ_2M));\n\t\tret = spi_nor_wait_till_ready_with_timeout(nor, timeout);\n\t\tif (ret)\n\t\t\tgoto erase_err;\n\n\t/* REVISIT in some cases we could speed up erasing large regions\n\t * by using SPINOR_OP_SE instead of SPINOR_OP_BE_4K.  We may have set up\n\t * to use "small sector erase", but that\'s not always optimal.\n\t */\n\n\t/* "sector"-at-a-time erase */\n\t} else {\n\t\twhile (len) {\n\t\t\twrite_enable(nor);\n\n\t\t\tret = spi_nor_erase_sector(nor, addr);\n\t\t\tif (ret)\n\t\t\t\tgoto erase_err;\n\n\t\t\taddr += mtd->erasesize;\n\t\t\tlen -= mtd->erasesize;\n\n\t\t\tret = spi_nor_wait_till_ready(nor);\n\t\t\tif (ret)\n\t\t\t\tgoto erase_err;\n\t\t}\n\t}\n\n\twrite_disable(nor);\n\n\tspi_nor_unlock_and_unprep(nor, SPI_NOR_OPS_ERASE);\n\n\tinstr->state = MTD_ERASE_DONE;\n\tmtd_erase_callback(instr);\n\n\treturn ret;\n\nerase_err:\n\tspi_nor_unlock_and_unprep(nor, SPI_NOR_OPS_ERASE);\n\tinstr->state = MTD_ERASE_FAILED;\n\treturn ret;\n}', 'mtd_write': 'int mtd_write(struct mtd_info *mtd, loff_t to, size_t len, size_t *retlen,\n\t      const u_char *buf)\n{\n\t*retlen = 0;\n\tif (to < 0 || to >= mtd->size || len > mtd->size - to)\n\t\treturn -EINVAL;\n\tif (!mtd->_write || !(mtd->flags & MTD_WRITEABLE))\n\t\treturn -EROFS;\n\tif (!len)\n\t\treturn 0;\n\treturn mtd->_write(mtd, to, len, retlen, buf);\n}', 'mtdchar_read': 'static ssize_t mtdchar_read(struct file *file, char __user *buf, size_t count,\n\t\t\tloff_t *ppos)\n{\n\tstruct mtd_file_info *mfi = file->private_data;\n\tstruct mtd_info *mtd = mfi->mtd;\n\tsize_t retlen;\n\tsize_t total_retlen=0;\n\tint ret=0;\n\tint len;\n\tsize_t size = count;\n\tchar *kbuf;\n\n\tpr_debug("MTD_read\\n");\n\n\tif (*ppos + count > mtd->size) {\n\t\tif (*ppos < mtd->size)\n\t\t\tcount = mtd->size - *ppos;\n\t\telse\n\t\t\tcount = 0;\n\t}\n\n\tif (!count)\n\t\treturn 0;\n\n\tkbuf = mtd_kmalloc_up_to(mtd, &size);\n\tif (!kbuf)\n\t\treturn -ENOMEM;\n\n\twhile (count) {\n\t\tlen = min_t(size_t, count, size);\n\n\t\tswitch (mfi->mode) {\n\t\tcase MTD_FILE_MODE_OTP_FACTORY:\n\t\t\tret = mtd_read_fact_prot_reg(mtd, *ppos, len,\n\t\t\t\t\t\t     &retlen, kbuf);\n\t\t\tbreak;\n\t\tcase MTD_FILE_MODE_OTP_USER:\n\t\t\tret = mtd_read_user_prot_reg(mtd, *ppos, len,\n\t\t\t\t\t\t     &retlen, kbuf);\n\t\t\tbreak;\n\t\tcase MTD_FILE_MODE_RAW:\n\t\t{\n\t\t\tstruct mtd_oob_ops ops;\n\n\t\t\tops.mode = MTD_OPS_RAW;\n\t\t\tops.datbuf = kbuf;\n\t\t\tops.oobbuf = NULL;\n\t\t\tops.len = len;\n\n\t\t\tret = mtd_read_oob(mtd, *ppos, &ops);\n\t\t\tretlen = ops.retlen;\n\t\t\tbreak;\n\t\t}\n\t\tdefault:\n\t\t\tret = mtd_read(mtd, *ppos, len, &retlen, kbuf);\n\t\t}\n\t\t/* Nand returns -EBADMSG on ECC errors, but it returns\n\t\t * the data. For our userspace tools it is important\n\t\t * to dump areas with ECC errors!\n\t\t * For kernel internal usage it also might return -EUCLEAN\n\t\t * to signal the caller that a bitflip has occurred and has\n\t\t * been corrected by the ECC algorithm.\n\t\t * Userspace software which accesses NAND this way\n\t\t * must be aware of the fact that it deals with NAND\n\t\t */\n\t\tif (!ret || mtd_is_bitflip_or_eccerr(ret)) {\n\t\t\t*ppos += retlen;\n\t\t\tif (copy_to_user(buf, kbuf, retlen)) {\n\t\t\t\tkfree(kbuf);\n\t\t\t\treturn -EFAULT;\n\t\t\t}\n\t\t\telse\n\t\t\t\ttotal_retlen += retlen;\n\n\t\t\tcount -= retlen;\n\t\t\tbuf += retlen;\n\t\t\tif (retlen == 0)\n\t\t\t\tcount = 0;\n\t\t}\n\t\telse {\n\t\t\tkfree(kbuf);\n\t\t\treturn ret;\n\t\t}\n\n\t}\n\n\tkfree(kbuf);\n\treturn total_retlen;\n}', 'mtdchar_write': 'static ssize_t mtdchar_write(struct file *file, const char __user *buf, size_t count,\n\t\t\tloff_t *ppos)\n{\n\tstruct mtd_file_info *mfi = file->private_data;\n\tstruct mtd_info *mtd = mfi->mtd;\n\tsize_t size = count;\n\tchar *kbuf;\n\tsize_t retlen;\n\tsize_t total_retlen=0;\n\tint ret=0;\n\tint len;\n\n\tpr_debug("MTD_write\\n");\n\n\tif (*ppos >= mtd->size)\n\t\treturn -ENOSPC;\n\n\tif (*ppos + count > mtd->size)\n\t\tcount = mtd->size - *ppos;\n\n\tif (!count)\n\t\treturn 0;\n\n\tkbuf = mtd_kmalloc_up_to(mtd, &size);\n\tif (!kbuf)\n\t\treturn -ENOMEM;\n\n\twhile (count) {\n\t\tlen = min_t(size_t, count, size);\n\n\t\tif (copy_from_user(kbuf, buf, len)) {\n\t\t\tkfree(kbuf);\n\t\t\treturn -EFAULT;\n\t\t}\n\n\t\tswitch (mfi->mode) {\n\t\tcase MTD_FILE_MODE_OTP_FACTORY:\n\t\t\tret = -EROFS;\n\t\t\tbreak;\n\t\tcase MTD_FILE_MODE_OTP_USER:\n\t\t\tret = mtd_write_user_prot_reg(mtd, *ppos, len,\n\t\t\t\t\t\t      &retlen, kbuf);\n\t\t\tbreak;\n\n\t\tcase MTD_FILE_MODE_RAW:\n\t\t{\n\t\t\tstruct mtd_oob_ops ops;\n\n\t\t\tops.mode = MTD_OPS_RAW;\n\t\t\tops.datbuf = kbuf;\n\t\t\tops.oobbuf = NULL;\n\t\t\tops.ooboffs = 0;\n\t\t\tops.len = len;\n\n\t\t\tret = mtd_write_oob(mtd, *ppos, &ops);\n\t\t\tretlen = ops.retlen;\n\t\t\tbreak;\n\t\t}\n\n\t\tdefault:\n\t\t\tret = mtd_write(mtd, *ppos, len, &retlen, kbuf);\n\t\t}\n\n\t\t/*\n\t\t * Return -ENOSPC only if no data could be written at all.\n\t\t * Otherwise just return the number of bytes that actually\n\t\t * have been written.\n\t\t */\n\t\tif ((ret == -ENOSPC) && (total_retlen))\n\t\t\tbreak;\n\n\t\tif (!ret) {\n\t\t\t*ppos += retlen;\n\t\t\ttotal_retlen += retlen;\n\t\t\tcount -= retlen;\n\t\t\tbuf += retlen;\n\t\t}\n\t\telse {\n\t\t\tkfree(kbuf);\n\t\t\treturn ret;\n\t\t}\n\t}\n\n\tkfree(kbuf);\n\treturn total_retlen;\n}'}
BASELINE_FUNCTIONS_SHA256 = {'m25p_cmdsz': '06164946643d0788f2dd0ef853227c20cd94ded58c46a36cb7ec6f5515d0c136', 'm25p80_write': '35d0263e4e8a4adfb41d9908bfaa6a76a9ecc423e3e11aa523eb153263525e6d', 'm25p80_read': 'd8fd78d2679243e70a10f725ceea0c1f8ff40bce4ddf21397e80253ba27a3a47', 'm25p80_erase': 'debc17f9fa6d28a8d2560ee87824889faeb845c2d922ceec45e30c34786db77f', 'spi_nor_write': '82be47a0d911e88c696f6fc247112af2ee0774a4b3cbe9fb104b8ca51f4cc09d', 'spi_nor_erase': '69cdb8906e2f216724510ec35d6cb6b6794e2b722e07b1a39b8bdfe17939dbaf', 'mtd_write': 'f473169da18e2f4b15b85699ae056d3a5ffeeb8d00dc8f7fd9793cc4855a5d9d', 'mtdchar_read': '97daea2681f6f1fcee1f4830ac2015566c6fa3c0af280cb1dbd40da85812a96c', 'mtdchar_write': '3904ab46df4c35f98fb012eb66c6100c12a41fd496a6b534b8eaf4e5843c9332'}

PREFIX = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <sys/types.h>
#undef ETIMEDOUT
#define ETIMEDOUT 110
#undef ELOOP
#define ELOOP 40
#undef EOPNOTSUPP
#define EOPNOTSUPP 95
#undef EUCLEAN
#define EUCLEAN 117
#undef EBADMSG
#define EBADMSG 74
#ifndef __linux__
typedef int64_t loff_t;
#endif
typedef unsigned char u8; typedef unsigned char u_char; typedef unsigned int u32;
#define MAX_CMD_SIZE 6
#define __user
#define SPINOR_OP_AAI_WP 0xad
#define SPI_NOR_OPS_WRITE 1
#define SPI_NOR_OPS_ERASE 2
#define SPI_NOR_DUAL 1
#define SPI_NOR_QUAD 2
#define MTD_WRITEABLE 1
#define MTD_FILE_MODE_OTP_FACTORY 1
#define MTD_FILE_MODE_OTP_USER 2
#define MTD_FILE_MODE_RAW 3
#define MTD_OPS_RAW 1
#define MTD_ERASE_DONE 8
#define MTD_ERASE_FAILED 16
#define CHIP_ERASE_2MB_READY_WAIT_JIFFIES 100
#define SZ_2M 2097152UL
#define dev_dbg(...) ((void)0)
#define pr_debug(...) ((void)0)
#define min_t(type,a,b) ((type)(a)<(type)(b)?(type)(a):(type)(b))
#define max(a,b) ((a)>(b)?(a):(b))
struct spi_device { int dummy; };
struct spi_transfer { const void *tx_buf; void *rx_buf; unsigned int len; unsigned int rx_nbits; };
struct spi_message { unsigned int actual_length; struct spi_transfer *transfers[2]; unsigned int count; };
struct spi_nor;
struct mtd_info { size_t size; unsigned int flags,erasesize; struct spi_nor *nor; int (*_write)(struct mtd_info*,loff_t,size_t,size_t*,const u_char*); };
struct spi_nor { void *priv; void *dev; unsigned int addr_width,program_opcode,read_opcode,erase_opcode,read_dummy,page_size,flash_read; int sst_write_second; void (*write)(struct spi_nor*,loff_t,size_t,size_t*,const u_char*); };
struct m25p { struct spi_device *spi; struct spi_nor spi_nor; u8 command[MAX_CMD_SIZE]; };
struct mtd_file_info { struct mtd_info *mtd; int mode; };
struct file { void *private_data; };
struct mtd_oob_ops { int mode; u_char *datbuf,*oobbuf; unsigned int ooboffs; size_t len,retlen; };
struct erase_info { uint64_t addr,len; int state; };
static int fault,transport_calls,ready_calls,write_enable_calls,unlock_calls,pending;
static int copied_bytes,lower_calls,erase_callbacks,allocations,oversize_copy,raw_zeroed=1;
static char sequence[1024];
static void trace(char c){size_t n=strlen(sequence);if(n+1>=sizeof(sequence))abort();sequence[n]=c;sequence[n+1]=0;}
static void spi_message_init(struct spi_message*m){memset(m,0,sizeof(*m));}
static void spi_message_add_tail(struct spi_transfer*t,struct spi_message*m){if(m->count>=2)abort();m->transfers[m->count++]=t;}
static int spi_sync(struct spi_device*spi,struct spi_message*m){
 unsigned int command=m->transfers[0]->len, data=m->transfers[1]->len;
 (void)spi;transport_calls++;pending=1;trace(m->transfers[1]->rx_buf?'R':'P');
 if(fault==1 || (fault==5&&transport_calls==2)){m->actual_length=command;return -EIO;}
 if(fault==2){m->actual_length=0;return -EIO;}
 if(fault==3){m->actual_length=command;return 0;}
 if(fault==4){m->actual_length=command+data+1;return 0;}
 m->actual_length=command+data;
 if(m->transfers[1]->rx_buf)memset(m->transfers[1]->rx_buf,0xff,data);
 return 0;
}
static int spi_write(struct spi_device*spi,const void*buf,size_t size){
 (void)spi;(void)buf;if(size!=4)abort();transport_calls++;trace('E');
 return fault==1?-EIO:0;
}
/* Explicit inert seam: actual command byte count is tested, serialization is not. */
static void m25p_addr2cmd(struct spi_nor*n,unsigned int a,u8*cmd){(void)n;(void)a;memset(cmd+1,0,MAX_CMD_SIZE-1);}
static unsigned int m25p80_rx_nbits(struct spi_nor*n){(void)n;return 0;}
static struct spi_nor*mtd_to_spi_nor(struct mtd_info*m){return m->nor;}
static int spi_nor_lock_and_prep(struct spi_nor*n,int op){(void)n;(void)op;trace('A');return 0;}
static void spi_nor_unlock_and_unprep(struct spi_nor*n,int op){(void)n;(void)op;unlock_calls++;trace('U');}
static int write_enable(struct spi_nor*n){(void)n;write_enable_calls++;trace('W');return (fault==7||(fault==8&&write_enable_calls==2))?-EIO:0;}
static void write_disable(struct spi_nor*n){(void)n;trace('D');}
static int spi_nor_wait_till_ready(struct spi_nor*n){(void)n;ready_calls++;trace('T');if(fault==6)return -ETIMEDOUT;pending=0;return 0;}
static int spi_nor_wait_till_ready_with_timeout(struct spi_nor*n,unsigned long timeout){if(timeout<100)abort();return spi_nor_wait_till_ready(n);}
static uint64_t div_u64_rem(uint64_t n,uint32_t d,uint32_t*r){*r=(uint32_t)(n%d);return n/d;}
static int erase_chip(struct spi_nor*n){struct m25p*f=n->priv;return spi_write(f->spi,f->command,4);}
static void mtd_erase_callback(struct erase_info*i){if(i->state!=MTD_ERASE_DONE)abort();erase_callbacks++;trace('C');}
static int spi_nor_erase_sector(struct spi_nor*n,unsigned int addr);
static void bad_program(struct spi_nor*n,loff_t to,size_t len,size_t*r,const u_char*b){
 (void)n;(void)to;(void)b;trace('B');
 if(fault==10)*r+=len+1;
 else if(fault==11)*r+=len;
}
static void *mtd_kmalloc_up_to(struct mtd_info*m,size_t*s){(void)m;allocations++;return malloc(*s);}
static void kfree(void*p){if(p)allocations--;free(p);}
/* user-copy is inert, avoiding real OOB copying in the old invalid-retlen model. */
static int copy_from_user(void*d,const void*s,size_t n){(void)s;memset(d,0xff,n);return 0;}
static int copy_to_user(void*d,const void*s,size_t n){(void)d;(void)s;if(n>600){oversize_copy++;return 1;}copied_bytes+=(int)n;return 0;}
static int lower_transfer(size_t n,size_t*r,void*b,int reading){
 lower_calls++;trace('L');
 /* A bounded observer stops only the old no-progress body on its third pass. */
 if(lower_calls==3&&(fault==12||fault==18||fault==19))return -ELOOP;
 if(fault==18)return 0;
 if(fault==12||fault==17){*r=0;return 0;}
 *r=(fault==13||fault==16)?n+1:(fault==14&&lower_calls==1?n/2:n);
 if(reading&&*r<=n)memset(b,0xff,*r);
 return (fault==15||fault==16)?-EUCLEAN:0;
}
static int mtd_write_user_prot_reg(struct mtd_info*m,loff_t p,size_t n,size_t*r,void*b){(void)m;(void)p;return lower_transfer(n,r,b,0);}
static int mtd_read_fact_prot_reg(struct mtd_info*m,loff_t p,size_t n,size_t*r,void*b){(void)m;(void)p;return lower_transfer(n,r,b,1);}
static int mtd_read_user_prot_reg(struct mtd_info*m,loff_t p,size_t n,size_t*r,void*b){(void)m;(void)p;return lower_transfer(n,r,b,1);}
static int mtd_write_oob(struct mtd_info*m,loff_t p,struct mtd_oob_ops*o){
 (void)m;(void)p;raw_zeroed &= (o->retlen==0);return lower_transfer(o->len,&o->retlen,o->datbuf,0);
}
static int mtd_read_oob(struct mtd_info*m,loff_t p,struct mtd_oob_ops*o){
 (void)m;(void)p;raw_zeroed &= (o->retlen==0&&o->ooboffs==0);return lower_transfer(o->len,&o->retlen,o->datbuf,1);
}
static int mtd_read(struct mtd_info*m,loff_t p,size_t n,size_t*r,void*b){(void)m;(void)p;return lower_transfer(n,r,b,1);}
static int mtd_is_bitflip_or_eccerr(int ret){return ret==-EUCLEAN||ret==-EBADMSG;}
'''

# Expected results are literal contract values, never obtained by running a body.
def _expected(name, result=0, retlen=0, transport=0, ready=0, wren=0, unlock=0,
              pending=0, position=0, copied=0, lower=0, callback=0, state=0,
              sequence=''):
    return dict(case=name,result=result,retlen=retlen,transport_calls=transport,
                ready_calls=ready,write_enable_calls=wren,unlock_calls=unlock,
                pending=pending,position=position,copied_bytes=copied,
                lower_calls=lower,erase_callbacks=callback,erase_state=state,
                sequence=sequence,allocations=0,raw_zeroed=True)

# (name, route, fault, length, offset, file-mode, literal expected fields)
SPECS = (
 ('write-single',0,0,32,0,0,dict(retlen=32,transport=1,ready=1,wren=1,unlock=1,sequence='AWPTU')),
 ('write-cross-page',0,0,32,250,0,dict(retlen=32,transport=2,ready=2,wren=2,unlock=1,sequence='AWPTWPTU')),
 ('write-multiple',0,0,600,0,0,dict(retlen=600,transport=3,ready=3,wren=3,unlock=1,sequence='AWPTWPTWPTU')),
 ('write-final-ready-error',0,6,32,0,0,dict(result=-110,retlen=32,transport=1,ready=1,wren=1,unlock=1,pending=1,sequence='AWPTU')),
 ('write-data-error',0,1,32,0,0,dict(result=-5,transport=1,wren=1,unlock=1,pending=1,sequence='AWPU')),
 ('write-command-error',0,2,32,0,0,dict(result=-5,transport=1,wren=1,unlock=1,pending=1,sequence='AWPU')),
 ('write-short-completion',0,3,32,0,0,dict(result=-5,transport=1,wren=1,unlock=1,pending=1,sequence='AWPU')),
 ('write-overlong-completion',0,4,32,0,0,dict(result=-5,transport=1,wren=1,unlock=1,pending=1,sequence='AWPU')),
 ('write-second-page-error',0,5,600,0,0,dict(result=-5,retlen=256,transport=2,ready=1,wren=2,unlock=1,pending=1,sequence='AWPTWPU')),
 ('write-enable-first-error',0,7,32,0,0,dict(result=-5,wren=1,unlock=1,sequence='AWU')),
 ('write-enable-second-error',0,8,600,0,0,dict(result=-5,retlen=256,transport=1,ready=1,wren=2,unlock=1,sequence='AWPTWU')),
 ('write-callback-zero',0,9,32,0,0,dict(result=-5,wren=1,unlock=1,sequence='AWBU')),
 ('write-callback-overlong',0,10,32,0,0,dict(result=-5,retlen=33,wren=1,unlock=1,sequence='AWBU')),
 ('write-callback-wrap',0,11,32,0,0,dict(result=-5,retlen=29,wren=1,unlock=1,sequence='AWBU')),
 ('read-normal',1,0,32,0,0,dict(retlen=32,transport=1,pending=1,sequence='R')),
 ('read-data-error',1,1,32,0,0,dict(result=-5,transport=1,pending=1,sequence='R')),
 ('read-command-error',1,2,32,0,0,dict(result=-5,transport=1,pending=1,sequence='R')),
 ('read-short-completion',1,3,32,0,0,dict(result=-5,transport=1,pending=1,sequence='R')),
 ('read-overlong-completion',1,4,32,0,0,dict(result=-5,transport=1,pending=1,sequence='R')),
 ('read-fast-normal',1,0,32,0,1,dict(retlen=32,transport=1,pending=1,sequence='R')),
 ('read-fast-command-error',1,2,32,0,1,dict(result=-5,transport=1,pending=1,sequence='R')),
 ('erase-normal',2,0,32,0,0,dict(transport=1,sequence='E')),
 ('erase-error',2,1,32,0,0,dict(result=-5,transport=1,sequence='E')),
 ('erase-sector-normal',3,0,8192,0,0,dict(transport=2,ready=2,wren=2,unlock=1,callback=1,state=8,sequence='AWETWETDUC')),
 ('erase-sector-enable-first-error',3,7,8192,0,0,dict(result=-5,wren=1,unlock=1,state=16,sequence='AWU')),
 ('erase-sector-enable-second-error',3,8,8192,0,0,dict(result=-5,transport=1,ready=1,wren=2,unlock=1,state=16,sequence='AWETWU')),
 ('erase-sector-transport-error',3,1,8192,0,0,dict(result=-5,transport=1,wren=1,unlock=1,state=16,sequence='AWEU')),
 ('erase-chip-normal',3,0,15925248,0,0,dict(transport=1,ready=1,wren=1,unlock=1,callback=1,state=8,sequence='AWETDUC')),
 ('erase-chip-enable-error',3,7,15925248,0,0,dict(result=-5,wren=1,unlock=1,state=16,sequence='AWU')),
 ('char-write-normal',4,0,32,0,0,dict(result=32,transport=1,ready=1,wren=1,unlock=1,position=32,sequence='AWPTU')),
 ('char-write-transport-error',4,1,32,0,0,dict(result=-5,transport=1,wren=1,unlock=1,pending=1,sequence='AWPU')),
 ('char-write-zero',4,12,32,0,2,dict(result=-5,lower=1,sequence='L')),
 ('char-write-overlong',4,13,32,0,2,dict(result=-5,lower=1,sequence='L')),
 ('char-write-short',4,14,32,0,2,dict(result=32,position=32,lower=2,sequence='LL')),
 ('char-write-raw-zero',4,12,32,0,3,dict(result=-5,lower=1,sequence='L')),
 ('char-read-normal',5,0,32,0,0,dict(result=32,position=32,copied=32,lower=1,sequence='L')),
 ('char-read-overlong',5,13,32,0,0,dict(result=-5,lower=1,sequence='L')),
 ('char-read-ecc-valid',5,15,32,0,0,dict(result=32,position=32,copied=32,lower=1,sequence='L')),
 ('char-read-ecc-overlong',5,16,32,0,0,dict(result=-5,lower=1,sequence='L')),
 ('char-read-zero-eof',5,17,32,0,0,dict(lower=1,sequence='L')),
 ('char-read-short',5,14,32,0,0,dict(result=32,position=32,copied=32,lower=2,sequence='LL')),
 ('char-read-raw-zero',5,17,32,0,3,dict(lower=1,sequence='L')),
)
CASES = tuple((spec[0], _expected(spec[0], **spec[6])) for spec in SPECS)
CASE_NAMES = tuple(name for name, _ in CASES)

MAIN = r'''
int main(int argc,char**argv){
 struct spi_device spi={0};struct m25p flash;struct spi_nor *nor=&flash.spi_nor;
 struct mtd_info mtd;size_t retlen=0,len=32;u_char data[600];int result=0,route=0;
 loff_t pos=0,offset=0;struct mtd_file_info info;struct file file;struct erase_info erase;
 if(argc!=2)return 2;
 memset(&flash,0,sizeof(flash));memset(&mtd,0,sizeof(mtd));memset(&erase,0,sizeof(erase));
 memset(data,0xff,sizeof(data));flash.spi=&spi;nor->priv=&flash;nor->addr_width=3;
 nor->program_opcode=2;nor->read_opcode=3;nor->page_size=256;nor->write=m25p80_write;
 mtd.nor=nor;mtd.size=15925248;mtd.erasesize=4096;mtd.flags=MTD_WRITEABLE;mtd._write=spi_nor_write;
 info.mtd=&mtd;info.mode=0;file.private_data=&info;
 INPUT_CASES
 else return 3;
 if(fault==9||fault==10||fault==11)nor->write=bad_program;
 if(fault==11)retlen=SIZE_MAX-2;
 if(route==0)result=spi_nor_write(&mtd,offset,len,&retlen,data);
 else if(route==1)result=m25p80_read(nor,offset,len,&retlen,data);
 else if(route==2)result=m25p80_erase(nor,offset);
 else if(route==3){erase.addr=(uint64_t)offset;erase.len=len;result=spi_nor_erase(&mtd,&erase);}
 else if(route==4)result=(int)mtdchar_write(&file,(const char*)data,len,&pos);
 else if(route==5)result=(int)mtdchar_read(&file,(char*)data,len,&pos);
 else return 4;
 printf("{\"case\":\"%s\",\"result\":%d,\"retlen\":%llu,\"transport_calls\":%d,\"ready_calls\":%d,\"write_enable_calls\":%d,\"unlock_calls\":%d,\"pending\":%d,\"position\":%lld,\"copied_bytes\":%d,\"lower_calls\":%d,\"erase_callbacks\":%d,\"erase_state\":%d,\"sequence\":\"%s\",\"allocations\":%d,\"raw_zeroed\":%s}\n",argv[1],result,(unsigned long long)retlen,transport_calls,ready_calls,write_enable_calls,unlock_calls,pending,(long long)pos,copied_bytes,lower_calls,erase_callbacks,erase.state,sequence,allocations,raw_zeroed?"true":"false");
 return 0;
}
'''

def generate_source(texts, fixture_root='', owner_uid=0, baseline=False):
    """Return inert C only; fixture_root/owner are unused (no filesystem actions)."""
    del fixture_root, owner_uid
    bodies = BASELINE_FUNCTIONS if baseline else {key: value['body'] for key, value in actual_functions(texts).items()}
    pieces = [PREFIX]
    for key, names in FUNCTIONS.items():
        for name in names:
            if name in bodies:
                pieces.append(bodies[name])
        if key == 'm25p':
            pieces.append('static int spi_nor_erase_sector(struct spi_nor*n,unsigned int addr){return m25p80_erase(n,addr);}')
    branches = []
    for i, (name, route, fault, length, offset, mode, _) in enumerate(SPECS):
        statement = 'if' if i == 0 else 'else if'
        branches.append('%s(!strcmp(argv[1],%s)){route=%d;fault=%d;len=%d;offset=%d;info.mode=%d;%s}' %
                        (statement,json.dumps(name),route,fault,length,offset,mode if route >= 4 else 0,
                         'nor->read_dummy=8;' if route == 1 and mode else ''))
    generated = '\n'.join(pieces) + '\n' + MAIN.replace('INPUT_CASES','\n'.join(branches))
    for name, body in bodies.items():
        if generated.count(body) != 1:
            raise ValueError('Actual function body occurrence is not unique: ' + name)
    return generated

BASELINE_CASES = (
 ('write-data-error',_expected('write-data-error',retlen=0,transport=1,ready=1,wren=1,unlock=1,sequence='AWPTU')),
 ('write-command-error',_expected('write-command-error',retlen=4294967292,transport=1,ready=1,wren=1,unlock=1,sequence='AWPTU')),
 ('read-fast-command-error',_expected('read-fast-command-error',retlen=4294967291,transport=1,pending=1,sequence='R')),
 ('read-overlong-completion',_expected('read-overlong-completion',retlen=33,transport=1,pending=1,sequence='R')),
 ('erase-error',_expected('erase-error',transport=1,sequence='E')),
 ('write-enable-first-error',_expected('write-enable-first-error',retlen=32,transport=1,ready=1,wren=1,unlock=1,sequence='AWPTU')),
 ('erase-sector-enable-first-error',_expected('erase-sector-enable-first-error',transport=2,ready=2,wren=2,unlock=1,callback=1,state=8,sequence='AWETWETDUC')),
 ('erase-chip-enable-error',_expected('erase-chip-enable-error',transport=1,ready=1,wren=1,unlock=1,callback=1,state=8,sequence='AWETDUC')),
 ('char-write-zero',_expected('char-write-zero',result=-40,lower=3,sequence='LLL')),
)
