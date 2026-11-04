/*
 * mtd - simple memory technology device manipulation tool
 *
 * Copyright (C) 2005      Waldemar Brodkorb <wbx@dass-it.de>,
 * Copyright (C) 2005-2009 Felix Fietkau <nbd@nbd.name>
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License v2
 * as published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
 *
 *
 * The code is based on the linux-mtd examples.
 */

#define _GNU_SOURCE
#include <byteswap.h>
#include <endian.h>
#include <limits.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <fcntl.h>
#include <errno.h>
#include <time.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/param.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/reboot.h>
#include <linux/reboot.h>
#include <mtd/mtd-user.h>
//#include "fis.h"
#include "mtd.h"

//#include <libubox/md5.h>

#define MAX_ARGS 8
#define JFFS2_DEFAULT_DIR	"" /* directory name without /, empty means root dir */

#define TRX_MAGIC		0x48445230	/* "HDR0" */
#define SEAMA_MAGIC		0x5ea3a417
#define WRGG03_MAGIC		0x20080321

#if !defined(__BYTE_ORDER)
#error "Unknown byte order"
#endif

#if __BYTE_ORDER == __BIG_ENDIAN
#define cpu_to_be32(x)	(x)
#define be32_to_cpu(x)	(x)
#define le32_to_cpu(x)	bswap_32(x)
#elif __BYTE_ORDER == __LITTLE_ENDIAN
#define cpu_to_be32(x)	bswap_32(x)
#define be32_to_cpu(x)	bswap_32(x)
#define le32_to_cpu(x)  (x)
#else
#error "Unsupported endianness"
#endif

enum mtd_image_format {
	MTD_IMAGE_FORMAT_UNKNOWN,
	MTD_IMAGE_FORMAT_TRX,
	MTD_IMAGE_FORMAT_SEAMA,
	MTD_IMAGE_FORMAT_WRGG03,
};

static char *buf = NULL;
static size_t buf_capacity;
static char *imagefile = NULL;
static enum mtd_image_format imageformat = MTD_IMAGE_FORMAT_UNKNOWN;
static char *jffs2file = NULL, *jffs2dir = JFFS2_DEFAULT_DIR;
static int buflen = 0;
int quiet;
int no_erase;
int mtdsize = 0;
int erasesize = 0;
int writesize = 0;
int jffs2_skip_bytes=0;
int mtdtype = 0;

static int mtd_open_flags(const char *mtd, bool block, int flags)
{
	FILE *fp;
	char dev[PATH_MAX];
	int i;
	int ret;
	char name[PATH_MAX];

	snprintf(name, sizeof(name), "\"%s\"", mtd);
	if ((fp = fopen("/proc/mtd", "r"))) {
		while (fgets(dev, sizeof(dev), fp)) {
			if (sscanf(dev, "mtd%d:", &i) && strstr(dev, name)) {
				snprintf(dev, sizeof(dev), "/dev/mtd%s/%d", (block ? "block" : ""), i);
				if ((ret=open(dev, flags))<0) {
					snprintf(dev, sizeof(dev), "/dev/mtd%s%d", (block ? "block" : ""), i);
					ret=open(dev, flags);
				}
				fclose(fp);
				return ret;
			}
		}
		fclose(fp);
	}

	return open(mtd, flags);
}

int mtd_open(const char *mtd, bool block)
{
	return mtd_open_flags(mtd, block, O_RDWR | O_SYNC);
}

static int mtd_check_open_flags(const char *mtd, int flags)
{
	struct mtd_info_user mtdInfo;
	int fd;

	fd = mtd_open_flags(mtd, false, flags);
	if(fd < 0) {
		fprintf(stderr, "Could not open mtd device: %s\n", mtd);
		return -1;
	}

	if(ioctl(fd, MEMGETINFO, &mtdInfo)) {
		fprintf(stderr, "Could not get MTD device info from %s\n", mtd);
		close(fd);
		return -1;
	}
	mtdsize = mtdInfo.size;
	erasesize = mtdInfo.erasesize;
	mtdtype = mtdInfo.type;
	writesize = mtdInfo.writesize;

	return fd;
}

int mtd_check_open(const char *mtd)
{
	return mtd_check_open_flags(mtd, O_RDWR | O_SYNC);
}

int mtd_block_is_bad(int fd, int offset)
{
	int r = 0;
	loff_t o = offset;

	if (mtdtype == MTD_NANDFLASH)
	{
		r = ioctl(fd, MEMGETBADBLOCK, &o);
		if (r < 0)
		{
			fprintf(stderr, "Failed to get erase block status\n");
			exit(1);
		}
	}
	return r;
}

int mtd_erase_block(int fd, int offset)
{
	struct erase_info_user mtdEraseInfo;

	mtdEraseInfo.start = offset;
	mtdEraseInfo.length = erasesize;
	ioctl(fd, MEMUNLOCK, &mtdEraseInfo);
	if (ioctl (fd, MEMERASE, &mtdEraseInfo) < 0)
		return -1;

	return 0;
}

int mtd_write_buffer(int fd, const char *buf, int offset, int length)
{
	lseek(fd, offset, SEEK_SET);
	write(fd, buf, length);
	return 0;
}

static int
image_check(int imagefd, const char *mtd)
{
	uint32_t magic;
	int ret = 1;
	int bufread;

	while (buflen < sizeof(magic)) {
		bufread = read(imagefd, buf + buflen, sizeof(magic) - buflen);
		if (bufread < 1)
			break;

		buflen += bufread;
	}

	if (buflen < sizeof(magic)) {
		fprintf(stdout, "Could not get image magic\n");
		return 0;
	}

	magic = ((uint32_t *)buf)[0];

	if (be32_to_cpu(magic) == TRX_MAGIC)
		imageformat = MTD_IMAGE_FORMAT_TRX;
	else if (be32_to_cpu(magic) == SEAMA_MAGIC)
		imageformat = MTD_IMAGE_FORMAT_SEAMA;
	else if (le32_to_cpu(magic) == WRGG03_MAGIC)
		imageformat = MTD_IMAGE_FORMAT_WRGG03;

	switch (imageformat) {
	case MTD_IMAGE_FORMAT_TRX:
		if (trx_check)
			ret = trx_check(imagefd, mtd, buf, &buflen);
		break;
	case MTD_IMAGE_FORMAT_SEAMA:
		break;
	case MTD_IMAGE_FORMAT_WRGG03:
		break;
	default:
#ifdef target_brcm
		if (!strcmp(mtd, "firmware"))
			ret = 0;
#endif
		break;
	}

	return ret;
}

static int mtd_check(const char *mtd)
{
	char targets[PATH_MAX];
	char *next = NULL;
	char *larger;
	size_t length, required = sizeof(uint32_t);
	int fd, valid;

	/* Prepare every target and the largest scratch buffer before main can
	 * enter its pre-erase loop. The writer uses a bounded target copy too. */
	if (!mtd || (length = strnlen(mtd, sizeof(targets))) == sizeof(targets))
		return 0;
	memcpy(targets, mtd, length + 1);
	mtd = targets;

	do {
		next = strchr(mtd, ':');
		if (next) {
			*next = 0;
			next++;
		}

		fd = mtd_check_open(mtd);
		if (fd < 0)
			return 0;

		valid = erasesize > 0;
		if (valid && (size_t)erasesize > required)
			required = (size_t)erasesize;
		if (close(fd) != 0 || !valid)
			return 0;
		mtd = next;
	} while (next);

	if (!buf || required > buf_capacity) {
		larger = realloc(buf, required);
		if (!larger)
			return 0;
		buf = larger;
		buf_capacity = required;
	}

	return 1;
}

static int
mtd_unlock(const char *mtd)
{
	struct erase_info_user mtdLockInfo;
	char *next = NULL;
	char *str = NULL;
	int fd, result = 0;

	if (strchr(mtd, ':')) {
		str = strdup(mtd);
		if (!str)
			return -1;
		mtd = str;
	}

	do {
		next = strchr(mtd, ':');
		if (next) {
			*next = 0;
			next++;
		}

		fd = mtd_check_open(mtd);
		if(fd < 0) {
			fprintf(stderr, "Could not open mtd device: %s\n", mtd);
			result = -1;
			break;
		}

		if (quiet < 2)
			fprintf(stderr, "Unlocking %s ...\n", mtd);

		mtdLockInfo.start = 0;
		mtdLockInfo.length = mtdsize;
		if (mtdsize <= 0 ||
		    (ioctl(fd, MEMUNLOCK, &mtdLockInfo) != 0 &&
		     errno != EOPNOTSUPP && errno != ENOTTY))
			result = -1;
		if (close(fd) != 0)
			result = -1;
		if (result)
			break;
		mtd = next;
	} while (next);

	if (str)
		free(str);

	return result;
}

static int
mtd_erase(const char *mtd)
{
	int fd, result = -1;
	struct erase_info_user mtdEraseInfo;

	if (quiet < 2)
		fprintf(stderr, "Erasing %s ...\n", mtd);

	fd = mtd_check_open(mtd);
	if(fd < 0) {
		fprintf(stderr, "Could not open mtd device: %s\n", mtd);
		return -1;
	}
	/* Never loop forever on a zero step or erase beyond a malformed range. */
	if (mtdsize <= 0 || erasesize <= 0 || erasesize > mtdsize ||
	    mtdsize % erasesize)
		goto out;

	mtdEraseInfo.length = erasesize;

	for (mtdEraseInfo.start = 0;
		 mtdEraseInfo.start < mtdsize;
		 mtdEraseInfo.start += erasesize) {
		if (mtd_block_is_bad(fd, mtdEraseInfo.start)) {
			if (!quiet)
				fprintf(stderr, "\nSkipping bad block at 0x%x   ", mtdEraseInfo.start);
		} else {
			if (ioctl(fd, MEMUNLOCK, &mtdEraseInfo) != 0 &&
			    errno != EOPNOTSUPP && errno != ENOTTY)
				goto out;
			if(ioctl(fd, MEMERASE, &mtdEraseInfo)) {
				fprintf(stderr, "Failed to erase block on %s at 0x%x\n", mtd, mtdEraseInfo.start);
				goto out;
			}
		}
	}

	result = 0;
out:
	if (close(fd) != 0)
		result = -1;
	return result;

}

static int
mtd_dump(const char *mtd, size_t part_offset, size_t size)
{
	int ret = -1;
	int fd;
	char *buffer = NULL;
	size_t offset, chunk, done;

	if (quiet < 2)
		fprintf(stderr, "Dumping %s ...\n", mtd);

	fd = mtd_check_open_flags(mtd, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
	if(fd < 0) {
		fprintf(stderr, "Could not open mtd device: %s\n", mtd);
		return -1;
	}

	/* A dump is an exact physical range, never a best-effort compacted
	 * stream. Check before allocation, seeking or sending any output. */
	if (mtdsize <= 0 || erasesize <= 0 || part_offset >= (size_t)mtdsize)
		goto out;
	if (!size)
		size = (size_t)mtdsize - part_offset;
	if (size > (size_t)mtdsize - part_offset)
		goto out;
	if (part_offset && lseek(fd, (off_t)part_offset, SEEK_SET) != (off_t)part_offset)
		goto out;
	chunk = size < (size_t)erasesize ? size : (size_t)erasesize;
	buffer = malloc(chunk);
	if (!buffer)
		goto out;
	offset = part_offset;
	while (size) {
		size_t length = (size_t)erasesize - offset % (size_t)erasesize;
		if (length > size)
			length = size;
		if (mtd_block_is_bad(fd, (int)(offset - offset % (size_t)erasesize))) {
			fprintf(stderr, "Cannot dump an exact range containing bad block at 0x%08x\n", (unsigned)offset);
			goto out;
		}
		for (done = 0; done < length;) {
			ssize_t count = read(fd, buffer + done, length - done);
			if (count < 0 && errno == EINTR)
				continue;
			if (count <= 0 || (size_t)count > length - done)
				goto out;
			done += (size_t)count;
		}
		for (done = 0; done < length;) {
			ssize_t count = write(STDOUT_FILENO, buffer + done, length - done);
			if (count < 0 && errno == EINTR)
				continue;
			if (count <= 0 || (size_t)count > length - done)
				goto out;
			done += (size_t)count;
		}
		offset += length;
		size -= length;
	}
	ret = 0;

out:
	free(buffer);
	if (close(fd) != 0)
		ret = -1;
	return ret;
}

#if 0
static int
mtd_verify(const char *mtd, char *file)
{
	uint32_t f_md5[4], m_md5[4];
	struct stat s;
	md5_ctx_t ctx;
	int ret = 0;
	int fd;

	if (quiet < 2)
		fprintf(stderr, "Verifying %s against %s ...\n", mtd, file);

	if (stat(file, &s) || md5sum(file, f_md5) < 0) {
		fprintf(stderr, "Failed to hash %s\n", file);
		return -1;
	}

	fd = mtd_check_open(mtd);
	if(fd < 0) {
		fprintf(stderr, "Could not open mtd device: %s\n", mtd);
		return -1;
	}

	md5_begin(&ctx);
	do {
		char buf[256];
		int len = (s.st_size > sizeof(buf)) ? (sizeof(buf)) : (s.st_size);
		int rlen = read(fd, buf, len);

		if (rlen < 0) {
			if (errno == EINTR)
				continue;
			ret = -1;
			goto out;
		}
		if (!rlen)
			break;
		md5_hash(buf, rlen, &ctx);
		s.st_size -= rlen;
	} while (s.st_size > 0);

	md5_end(m_md5, &ctx);

	fprintf(stderr, "%08x%08x%08x%08x - %s\n", m_md5[0], m_md5[1], m_md5[2], m_md5[3], mtd);
	fprintf(stderr, "%08x%08x%08x%08x - %s\n", f_md5[0], f_md5[1], f_md5[2], f_md5[3], file);

	ret = memcmp(f_md5, m_md5, sizeof(m_md5));
	if (!ret)
		fprintf(stderr, "Success\n");
	else
		fprintf(stderr, "Failed\n");

out:
	close(fd);
	return ret;
}
#endif

static void
indicate_writing(const char *mtd)
{
	if (quiet < 2)
		fprintf(stderr, "\nWriting from %s to %s ... ", imagefile, mtd);

	if (!quiet)
		fprintf(stderr, " [ ]");
}

static int
mtd_write(int imagefd, const char *mtd, char *fis_layout, size_t part_offset)
{
	char targets[PATH_MAX];
	char *next = NULL;
	size_t target_length, required;
	int fd, result;
	ssize_t r, w, e;
	ssize_t skip = 0;
	uint32_t offset = 0;
	int jffs2_replaced = 0;
	int skip_bad_blocks = 0;

#ifdef FIS_SUPPORT
	static struct fis_part new_parts[MAX_ARGS];
	static struct fis_part old_parts[MAX_ARGS];
	int n_new = 0, n_old = 0;

	if (fis_layout) {
		const char *tmp = mtd;
		char *word, *brkt;
		int ret;

		memset(&old_parts, 0, sizeof(old_parts));
		memset(&new_parts, 0, sizeof(new_parts));

		do {
			next = strchr(tmp, ':');
			if (!next)
				next = (char *) tmp + strlen(tmp);

			memcpy(old_parts[n_old].name, tmp, next - tmp);

			n_old++;
			tmp = next + 1;
		} while(*next);

		for (word = strtok_r(fis_layout, ",", &brkt);
		     word;
			 word = strtok_r(NULL, ",", &brkt)) {

			tmp = strtok(word, ":");
			strncpy((char *) new_parts[n_new].name, tmp, sizeof(new_parts[n_new].name) - 1);

			tmp = strtok(NULL, ":");
			if (!tmp)
				goto next;

			new_parts[n_new].size = strtoul(tmp, NULL, 0);

			tmp = strtok(NULL, ":");
			if (!tmp)
				goto next;

			new_parts[n_new].loadaddr = strtoul(tmp, NULL, 16);
next:
			n_new++;
		}
		ret = fis_validate(old_parts, n_old, new_parts, n_new);
		if (ret < 0) {
			fprintf(stderr, "Failed to validate the new FIS partition table\n");
			exit(1);
		}
		if (ret == 0)
			fis_layout = NULL;
	}
#endif

	/* mtd_check already bounded this target list before any pre-erase.
	 * Keep the write path free of a second, fallible heap allocation. */
	if (!mtd || (target_length = strnlen(mtd, sizeof(targets))) == sizeof(targets))
		return -1;
	memcpy(targets, mtd, target_length + 1);
	mtd = targets;

	r = 0;

resume:
	next = strchr(mtd, ':');
	if (next) {
		*next = 0;
		next++;
	}

	fd = mtd_check_open(mtd);
	if(fd < 0) {
		fprintf(stderr, "Could not open mtd device: %s\n", mtd);
		exit(1);
	}
	/* Reopening a target must never let changed geometry or carried data
	 * exceed the scratch capacity prepared before main's mutation stage. */
	if (!buf || erasesize <= 0 || buflen < 0 || offset != 0) {
		close(fd);
		return -1;
	}
	required = (size_t)buflen > (size_t)erasesize ? (size_t)buflen : (size_t)erasesize;
	if (required > buf_capacity) {
		close(fd);
		return -1;
	}
	if (part_offset > 0) {
		fprintf(stderr, "Seeking on mtd device '%s' to: %zu\n", mtd, part_offset);
		lseek(fd, part_offset, SEEK_SET);
	}

	indicate_writing(mtd);

	w = e = 0;
	
	for (;;) {
		/* buffer may contain data already (from trx check or last mtd partition write attempt) */
		while (buflen < erasesize) {
			r = read(imagefd, buf + buflen, erasesize - buflen);
			if (r < 0) {
				if ((errno == EINTR) || (errno == EAGAIN))
					continue;
				else {
					perror("read");
					/* Never pad/write a partial buffer after an input error or
					 * report a successful Storage save to the caller. */
					close(fd);
					return -1;
				}
			}

			if (r == 0)
				break;

			buflen += r;
		}

		if (buflen == 0)
			break;

		if (buflen < erasesize) {
			/* Pad block to eraseblock size */
			memset(&buf[buflen], 0xff, erasesize - buflen);
			buflen = erasesize;
		}

		if (skip > 0) {
			skip -= buflen;
			buflen = 0;
			if (skip <= 0)
				indicate_writing(mtd);

			continue;
		}

		if (jffs2file && w >= jffs2_skip_bytes) {
			if (memcmp(buf, JFFS2_EOF, sizeof(JFFS2_EOF) - 1) == 0) {
				if (!quiet)
					fprintf(stderr, "\b\b\b   ");
				if (quiet < 2)
					fprintf(stderr, "\nAppending jffs2 data from %s to %s..\n.", jffs2file, mtd);
				/* got an EOF marker - this is the place to add some jffs2 data */
				skip = mtd_replace_jffs2(mtd, fd, e, jffs2file);
				jffs2_replaced = 1;

				/* don't add it again */
				jffs2file = NULL;

				w += skip;
				e += skip;
				skip -= buflen;
				buflen = 0;
				offset = 0;
				continue;
			}
			/* no EOF marker, make sure we figure out the last inode number
			 * before appending some data */
			mtd_parse_jffs2data(buf, jffs2dir);
		}

		/* need to erase the next block before writing data to it */
		if(!no_erase)
		{
			while (w + buflen > e - skip_bad_blocks) {
				if (!quiet)
					fprintf(stderr, "\b\b\b[e]");

				if (mtd_block_is_bad(fd, e)) {
					if (!quiet)
						fprintf(stderr, "\nSkipping bad block at 0x%08zx   ", e);

					skip_bad_blocks += erasesize;
					e += erasesize;

					// Move the file pointer along over the bad block.
					lseek(fd, erasesize, SEEK_CUR);
					continue;
				}

				if (mtd_erase_block(fd, e) < 0) {
					if (next) {
						if (w < e) {
							write(fd, buf + offset, e - w);
							offset = e - w;
						}
						w = 0;
						e = 0;
						close(fd);
						mtd = next;
						fprintf(stderr, "\b\b\b   \n");
						goto resume;
					} else {
						fprintf(stderr, "Failed to erase block\n");
						exit(1);
					}
				}

				/* erase the chunk */
				e += erasesize;
			}
		}

		if (!quiet)
			fprintf(stderr, "\b\b\b[w]");

		if ((result = write(fd, buf + offset, buflen)) < buflen) {
			if (result < 0) {
				fprintf(stderr, "Error writing image.\n");
				exit(1);
			} else {
				fprintf(stderr, "Insufficient space.\n");
				exit(1);
			}
		}
		w += buflen;

		buflen = 0;
		offset = 0;
	}

	if (jffs2_replaced) {
		switch (imageformat) {
		case MTD_IMAGE_FORMAT_TRX:
			if (trx_fixup)
				trx_fixup(fd, mtd);
			break;
		case MTD_IMAGE_FORMAT_SEAMA:
			if (mtd_fixseama)
				mtd_fixseama(mtd, 0, 0);
			break;
		case MTD_IMAGE_FORMAT_WRGG03:
			if (mtd_fixwrgg)
				mtd_fixwrgg(mtd, 0, 0);
			break;
		default:
			break;
		}
	}

	if (!quiet)
		fprintf(stderr, "\b\b\b\b    ");

	if (quiet < 2)
		fprintf(stderr, "\n");

#ifdef FIS_SUPPORT
	if (fis_layout) {
		if (fis_remap(old_parts, n_old, new_parts, n_new) < 0)
			fprintf(stderr, "Failed to update the FIS partition table\n");
	}
#endif

	if (close(fd) != 0) {
		perror("close");
		return -1;
	}
	return 0;
}

#include "legacy_guard.h"

static void usage(void)
{
	fprintf(stderr, "Usage: mtd [<options> ...] <command> [<arguments> ...] <device>[:<device>...]\n\n"
	"The device is in the format of mtdX (eg: mtd4) or its label.\n"
	"mtd recognizes these commands:\n"
	"        unlock                  unlock the device\n"
	"        refresh                 refresh mtd partition\n"
	"        erase                   erase all data on device\n"
	"        verify                  unsupported; use independent exact readback comparison\n"
	"        dump                    dump an exact range; I/O or bad-block errors fail\n"
	"        write <imagefile>|-     write <imagefile> (use - for stdin) to device\n"
	"        jffs2write <file>       append <file> to the jffs2 partition on the device\n");
	if (mtd_resetbc) {
	    fprintf(stderr,
	"        resetbc <device>        reset the uboot boot counter\n");
	}
	if (mtd_fixtrx) {
	    fprintf(stderr,
	"        fixtrx                  fix the checksum in a trx header on first boot\n");
	}
	if (mtd_fixseama) {
	    fprintf(stderr,
	"        fixseama                fix the checksum in a seama header on first boot\n");
	}
	if (mtd_fixwrgg) {
	    fprintf(stderr,
	"        fixwrgg                 fix the checksum in a wrgg header on first boot\n");
	}
	fprintf(stderr,
	"Following options are available:\n"
	"        -q                      quiet mode (once: no [w] on writing,\n"
	"                                           twice: no status messages)\n"
	"        -n                      write without first erasing the blocks\n"
	"        -r                      reboot after successful command\n"
	"        -f                      force write without trx checks\n"
	"        -e <device>             erase <device> before executing the command\n"
	"        -d <name>               directory for jffs2write, defaults to \"tmp\"\n"
	"        -j <name>               integrate <file> into jffs2 data when writing an image\n"
	"        -s <number>             skip the first n bytes when appending data to the jffs2 partiton, defaults to \"0\"\n"
	"        -p <number>             write beginning at partition offset\n"
	"        -l <length>             the length of data that we want to dump\n");
	if (mtd_fixtrx) {
	    fprintf(stderr,
	"        -o offset               offset of the image header in the partition(for fixtrx)\n");
	}
	if (mtd_fixtrx || mtd_fixseama || mtd_fixwrgg) {
		fprintf(stderr,
	"        -c datasize             amount of data to be used for checksum calculation (for fixtrx / fixseama / fixwrgg)\n");
	}
	fprintf(stderr,
#ifdef FIS_SUPPORT
	"        -F <part>[:<size>[:<entrypoint>]][,<part>...]\n"
	"                                alter the fis partition table to create new partitions replacing\n"
	"                                the partitions provided as argument to the write command\n"
	"                                (only valid together with the write command)\n"
#endif
	"\n"
	"Example: To write linux.trx to mtd4 labeled as linux and reboot afterwards\n"
	"         mtd -r write linux.trx linux\n\n");
	exit(1);
}

static void do_reboot(void)
{
	fprintf(stderr, "Rebooting ...\n");
	fflush(stderr);

	/* try regular reboot method first */
	system("/sbin/reboot");
	sleep(2);

	/* if we're still alive at this point, force the kernel to reboot */
	syscall(SYS_reboot,LINUX_REBOOT_MAGIC1,LINUX_REBOOT_MAGIC2,LINUX_REBOOT_CMD_RESTART,NULL);
}

int main (int argc, char **argv)
{
	int ch, i, boot, imagefd = 0, force, unlocked, dump_incompatible = 0;
	char *erase[MAX_ARGS], *device = NULL;
	char *fis_layout = NULL;
	char *numeric_end;
	size_t offset = 0, data_size = 0, part_offset = 0, dump_len = 0;
	enum {
		CMD_ERASE,
		CMD_WRITE,
		CMD_UNLOCK,
		CMD_JFFS2WRITE,
		CMD_FIXTRX,
		CMD_FIXSEAMA,
		CMD_FIXWRGG,
		CMD_VERIFY,
		CMD_DUMP,
		CMD_RESETBC,
	} cmd = -1;
	/* This dynamic legacy tool must never start a firmware transaction. The
	 * PID1 controller admits only the separate resident helper/session. */
	if (argc > 1 && !strcmp(argv[1], "--upgrade-write")) {
		fputs("mtd_write: firmware protocol moved to the controlled resident upgrade helper\n", stderr);
		return 21;
	}

	erase[0] = NULL;
	boot = 0;
	force = 0;
	buflen = 0;
	quiet = 0;
	no_erase = 0;

	while ((ch = getopt(argc, argv,
#ifdef FIS_SUPPORT
			"F:"
#endif
			"frnqe:d:s:j:p:o:c:l:")) != -1)
		switch (ch) {
			case 'f':
				dump_incompatible = 1;
				force = 1;
				break;
			case 'r':
				boot = 1;
				break;
			case 'n':
				dump_incompatible = 1;
				no_erase = 1;
				break;
			case 'j':
				dump_incompatible = 1;
				jffs2file = optarg;
				break;
			case 's':
				dump_incompatible = 1;
				errno = 0;
				jffs2_skip_bytes = strtoul(optarg, 0, 0);
				if (errno) {
						fprintf(stderr, "-s: illegal numeric string\n");
						usage();
				}
				break;
			case 'q':
				quiet++;
				break;
			case 'e':
				dump_incompatible = 1;
				i = 0;
				while ((erase[i] != NULL) && ((i + 1) < MAX_ARGS))
					i++;

				if (i + 1 >= MAX_ARGS) {
					fputs("mtd_write: too many pre-erase targets\n", stderr);
					return 21;
				}
				erase[i++] = optarg;
				erase[i] = NULL;
				break;
			case 'd':
				dump_incompatible = 1;
				jffs2dir = optarg;
				break;
			case 'p':
				dump_incompatible = 1;
				errno = 0;
				part_offset = strtoul(optarg, 0, 0);
				if (errno) {
					fprintf(stderr, "-p: illegal numeric string\n");
					usage();
				}
				break;
			case 'l':
				errno = 0;
				dump_len = strtoul(optarg, &numeric_end, 0);
				if (errno || optarg[0] < '0' || optarg[0] > '9' || *numeric_end) {
					fprintf(stderr, "-l: illegal numeric string\n");
					return 1;
				}
				break;
			case 'o':
				errno = 0;
				offset = strtoul(optarg, &numeric_end, 0);
				if (errno || optarg[0] < '0' || optarg[0] > '9' || *numeric_end) {
					fprintf(stderr, "-o: illegal numeric string\n");
					return 1;
				}
				break;
			case 'c':
				dump_incompatible = 1;
				errno = 0;
				data_size = strtoul(optarg, 0, 0);
				if (errno) {
					fprintf(stderr, "-c: illegal numeric string\n");
					usage();
				}
				break;
#ifdef FIS_SUPPORT
			case 'F':
				dump_incompatible = 1;
				fis_layout = optarg;
				break;
#endif
			case '?':
			default:
				usage();
		}
	argc -= optind;
	argv += optind;

	if (argc < 2)
		usage();

#if defined(MTD_K2P_LEGACY_GUARD) && MTD_K2P_LEGACY_GUARD
	/* Before mtd_check(), image opens, sync(), pre-erase or any writable MTD
	 * operation. Classification failure never authorizes a legacy write. */
	if (!legacy_firmware_command_allowed(argc, argv, erase, boot)) {
		fputs("mtd_write: legacy firmware/whole-flash mutation and -r are disabled; use the controlled upgrade transaction\n", stderr);
		return 21;
	}
#endif

	if ((strcmp(argv[0], "unlock") == 0) && (argc == 2)) {
		cmd = CMD_UNLOCK;
		device = argv[1];
	} else if ((strcmp(argv[0], "erase") == 0) && (argc == 2)) {
		cmd = CMD_ERASE;
		device = argv[1];
	} else if (((strcmp(argv[0], "resetbc") == 0) && (argc == 2)) && mtd_resetbc) {
		cmd = CMD_RESETBC;
		device = argv[1];
	} else if (((strcmp(argv[0], "fixtrx") == 0) && (argc == 2)) && mtd_fixtrx) {
		cmd = CMD_FIXTRX;
		device = argv[1];
	} else if (((strcmp(argv[0], "fixseama") == 0) && (argc == 2)) && mtd_fixseama) {
		cmd = CMD_FIXSEAMA;
		device = argv[1];
	} else if (((strcmp(argv[0], "fixwrgg") == 0) && (argc == 2)) && mtd_fixwrgg) {
		cmd = CMD_FIXWRGG;
		device = argv[1];
	} else if ((strcmp(argv[0], "verify") == 0) && (argc == 3)) {
		/* The implementation below is disabled. Never claim verification or
		 * reach sync/pre-erase for an operation which cannot verify bytes. */
		fputs("mtd_write: verify is not implemented; use independent exact readback comparison\n", stderr);
		return 1;
	} else if ((strcmp(argv[0], "dump") == 0) && (argc == 2)) {
		/* A backup command must not erase first or silently accept writer
		 * options. Only quiet, offset and length describe a dump. */
		if (dump_incompatible) {
			fputs("mtd_write: dump accepts only -q, -o and -l\n", stderr);
			return 1;
		}
		cmd = CMD_DUMP;
		device = argv[1];
	} else if ((strcmp(argv[0], "write") == 0) && (argc == 3)) {
		cmd = CMD_WRITE;
		device = argv[2];

		if (strcmp(argv[1], "-") == 0) {
			imagefile = "<stdin>";
			imagefd = 0;
		} else {
			imagefile = argv[1];
			if ((imagefd = open(argv[1], O_RDONLY)) < 0) {
				fprintf(stderr, "Couldn't open image file: %s!\n", imagefile);
				exit(1);
			}
		}

		if (!mtd_check(device)) {
			fprintf(stderr, "Can't open device for writing!\n");
			exit(1);
		}
		/* check trx file before erasing or writing anything */
		if (!image_check(imagefd, device) && !force) {
			fprintf(stderr, "Image check failed.\n");
			exit(1);
		}
	} else if ((strcmp(argv[0], "jffs2write") == 0) && (argc == 3)) {
		cmd = CMD_JFFS2WRITE;
		device = argv[2];

		imagefile = argv[1];
		if (!mtd_check(device)) {
			fprintf(stderr, "Can't open device for writing!\n");
			exit(1);
		}
	} else {
		usage();
	}

	/* Read-only backup never waits for unrelated global writeback or enters
	 * the mutating command/reboot pipeline. The legacy guard ran above. */
	if (cmd == CMD_DUMP)
		return mtd_dump(device, offset, dump_len) != 0;

	sync();

	i = 0;
	unlocked = 0;
	while (erase[i] != NULL) {
		if (mtd_unlock(erase[i]) != 0 || mtd_erase(erase[i]) != 0)
			return 1;
		if (strcmp(erase[i], device) == 0)
			unlocked = 1;
		i++;
	}

	switch (cmd) {
		case CMD_UNLOCK:
			if (!unlocked && mtd_unlock(device) != 0)
				return 1;
			break;
		case CMD_VERIFY:
			return 1;
		case CMD_DUMP:
			if (mtd_dump(device, offset, dump_len) != 0)
				return 1;
			break;
		case CMD_ERASE:
			if ((!unlocked && mtd_unlock(device) != 0) || mtd_erase(device) != 0)
				return 1;
			break;
		case CMD_WRITE:
			if (!unlocked && mtd_unlock(device) != 0)
				return 1;
			if (mtd_write(imagefd, device, fis_layout, part_offset) != 0)
				return 1;
			break;
		case CMD_JFFS2WRITE:
			if (!unlocked && mtd_unlock(device) != 0)
				return 1;
			mtd_write_jffs2(device, imagefile, jffs2dir);
			break;
		case CMD_FIXTRX:
			if (mtd_fixtrx) {
				mtd_fixtrx(device, offset, data_size);
			}
			break;
		case CMD_RESETBC:
			if (mtd_resetbc) {
				mtd_resetbc(device);
			}
			break;
		case CMD_FIXSEAMA:
			if (mtd_fixseama)
				mtd_fixseama(device, 0, data_size);
			break;
		case CMD_FIXWRGG:
			if (mtd_fixwrgg)
				mtd_fixwrgg(device, 0, data_size);
			break;
	}

	sync();

	if (boot)
		do_reboot();

	return 0;
}
