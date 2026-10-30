/*
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of
 * the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston,
 * MA 02111-1307 USA
 */

#include <stdio.h>
#include <stdlib.h>
#define __USE_GNU
#include <string.h>
#include <ctype.h>
#include <stdint.h>
#include <stdarg.h>
#include <errno.h>
#include <sys/statvfs.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/reboot.h>

#include <image.h>

#include "common.h"
#include "httpd.h"

#ifndef O_BINARY
#define O_BINARY	0
#endif

#define IMAGE_HEADER		"HDR0"
#define PROFILE_HEADER		"HDR1"
#define PROFILE_HEADER_NEW	"HDR2"
#define UPLOAD_BUF_SIZE		1024

typedef int (*check_header_t)(const char *, long *);

/* Diagnostic trail for the firmware upload; lives in /tmp and is tiny. */
static void
fwlog(const char *fmt, ...)
{
	struct stat st;
	char line[512];
	int fd, length;
	size_t done = 0;
	ssize_t count;
	va_list ap;

	/* This predictable diagnostic name is in shared /tmp. Never follow a
	 * pre-existing alias or write somebody else's inode as the web daemon. */
	fd = open("/tmp/fwcheck.log", O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
	if (fd < 0)
		return;
	if (flock(fd, LOCK_EX | LOCK_NB) != 0 ||
	    fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != geteuid() ||
	    st.st_nlink != 1 || (st.st_mode & 07777) != 0600 || st.st_size < 0)
		goto out;
	va_start(ap, fmt);
	length = vsnprintf(line, sizeof(line) - 1, fmt, ap);
	va_end(ap);
	if (length < 0)
		goto out;
	if (length > (int)sizeof(line) - 2)
		length = sizeof(line) - 2;
	line[length++] = '\n';
	if (st.st_size > 65536 - length)
		goto out;
	while (done < (size_t)length) {
		count = write(fd, line + done, length - done);
		if (count < 0 && errno == EINTR)
			continue;
		if (count <= 0)
			break;
		done += count;
	}
out:
	close(fd);
}

static int
check_header_bz2(const char *buf, long *file_len)
{
	const unsigned char bz2h_1[3] = { 0x42, 0x5a, 0x68 };
	const unsigned char bz2h_2[6] = { 0x31, 0x41, 0x59, 0x26, 0x53, 0x59 };

	if (memcmp(buf, bz2h_1, 3) == 0 && memcmp(buf+4, bz2h_2, 6) == 0)
		return 0;

	httpd_log("%s: Incorrect %s header!", "Storage restore", "BZ2");

	return -1;
}

static int
check_header_nvram(const char *buf, long *file_len)
{
	uint32_t length;

	memcpy(&length, buf + 4, sizeof(length));
	if (strncmp(buf, PROFILE_HEADER_NEW, 4) == 0)
		length &= 0xffffff;
	else if (strncmp(buf, PROFILE_HEADER, 4) != 0) {
		httpd_log("%s: Incorrect %s header!", "NVRAM restore", "profile");
		return -1;
	}
	/* Both supported profiles use a little-endian, four-byte length. */
	if (length == 0 || (uint64_t)length + 8 > (uint64_t)*file_len)
		return -1;
	*file_len = (long)length + 8;
	return 0;
}

static int
check_header_image(const char *buf, long *file_len)
{
	int pid_asus_len;
	char pid_asus[16];
	image_header_t *hdr = (image_header_t *)buf;

	/* check header magic */
	if (ntohl(hdr->ih_magic) != IH_MAGIC) {
		httpd_log("%s: Incorrect %s header!", "Firmware update", "image");
		return -1;
	}

	pid_asus_len = strlen(BOARD_PID);
	if (pid_asus_len > 12)
		pid_asus_len = 12;

	strncpy(pid_asus, buf+36, pid_asus_len);
	pid_asus[pid_asus_len] = 0;

	if (strcmp(pid_asus, BOARD_PID) != 0) {
		httpd_log("%s: Incorrect image ProductID: %s! Expected is %s.", "Firmware update", pid_asus, BOARD_PID);
		return -2;
	}

	if ((uint64_t)ntohl(hdr->ih_size) + sizeof(image_header_t) > get_mtd_size(FW_MTD_NAME))
		return -1;
	*file_len = (long)ntohl(hdr->ih_size) + sizeof(image_header_t);

	return 0;
}

static int
check_crc_image(const char *fw_image)
{
	int ifd;
	uint32_t checksum, datalen;
	struct stat sbuf;
	unsigned char *ptr = (unsigned char *)MAP_FAILED;
	image_header_t header2;
	image_header_t *hdr, *hdr2=&header2;
	int ret = 0;

	ifd = open(fw_image, O_RDONLY|O_BINARY);
	if (ifd < 0) {
		fwlog("crc: open failed: %s", strerror(errno));
		return -1;
	}

	/* We're a bit of paranoid */
#if defined(_POSIX_SYNCHRONIZED_IO) && !defined(__sun__) && !defined(__FreeBSD__)
	(void) fdatasync (ifd);
#else
	(void) fsync (ifd);
#endif
	if (fstat(ifd, &sbuf) < 0) {
		ret=-1;
		goto checkcrc_fail;
	}

	fwlog("crc: size=%u mtd=%u", (unsigned int)sbuf.st_size, get_mtd_size(FW_MTD_NAME));
	if ((unsigned int)sbuf.st_size < (sizeof(image_header_t) + (2 * 1024 * 1024)) || 
	    (unsigned int)sbuf.st_size > get_mtd_size(FW_MTD_NAME)) {
		ret = -1;
		fwlog("crc: size check failed");
		httpd_log("%s: Firmware image size is invalid!", "Firmware update");
		goto checkcrc_fail;
	}

	ptr = (unsigned char *)mmap(0, sbuf.st_size, PROT_READ, MAP_SHARED, ifd, 0);
	if (ptr == (unsigned char *)MAP_FAILED) {
		ret = -1;
		fwlog("crc: mmap failed: %s", strerror(errno));
		httpd_log("%s: Unable to mmap firmware image!", "Firmware update");
		goto checkcrc_fail;
	}

	hdr = (image_header_t *)ptr;

	memcpy(hdr2, hdr, sizeof(image_header_t));
	memset(&hdr2->ih_hcrc, 0, sizeof(uint32_t));
	checksum = crc32_sp(0, (const char *)hdr2, sizeof(image_header_t));

	fwlog("crc: hdr calc=%08lx stored=%08x", (unsigned long)checksum, ntohl(hdr->ih_hcrc));
	if (checksum != ntohl(hdr->ih_hcrc)) {
		ret = -1;
		httpd_log("%s: Firmware image %s has invalid CRC!", "Firmware update", "header");
		goto checkcrc_fail;
	}

	datalen = ntohl(hdr->ih_size);
	if (datalen != ((unsigned int)sbuf.st_size - sizeof(image_header_t))) {
		ret = -1;
		httpd_log("%s: Firmware image is corrupted! Please check free space in /tmp!", "Firmware update");
		goto checkcrc_fail;
	}

	checksum = crc32_sp(0, (const char *)(ptr + sizeof(image_header_t)), datalen);
	fwlog("crc: body calc=%08lx stored=%08x len=%u", (unsigned long)checksum, ntohl(hdr->ih_dcrc), datalen);
	if (checksum != ntohl(hdr->ih_dcrc)) {
		ret = -1;
		httpd_log("%s: Firmware image %s has invalid CRC!", "Firmware update", "body");
		goto checkcrc_fail;
	}

checkcrc_fail:
	if (ptr != (unsigned char *)MAP_FAILED)
		munmap((void *)ptr, sbuf.st_size);

#if defined(_POSIX_SYNCHRONIZED_IO) && !defined(__sun__) && !defined(__FreeBSD__)
	(void) fdatasync (ifd);
#else
	(void) fsync (ifd);
#endif
	close(ifd);

	return ret;
}

/* A marker prefix inside file data is not a MIME delimiter.  Keep enough
 * lookahead to validate its line ending, including a split closing marker. */
static int
multipart_boundary_end(const char *buf, size_t len, const char *marker, size_t marker_len, int final)
{
	size_t tail;

	if (len < marker_len || memcmp(buf, marker, marker_len) != 0)
		return 0;
	buf += marker_len;
	tail = len - marker_len;
	if (tail >= 2 && buf[0] == '\r' && buf[1] == '\n')
		return 1;
	if (tail >= 1 && buf[0] == '\n')
		return 1;
	if (tail < 2 || buf[0] != '-' || buf[1] != '-')
		return 0;
	return (tail == 2 && final) || (tail >= 3 && buf[2] == '\n') ||
	       (tail >= 4 && buf[2] == '\r' && buf[3] == '\n');
}

static int
do_upload_file(FILE *stream, int clen, char *bndr, const char *fn, const char *obj_name, check_header_t func_hdr, int hdr_size)
{
	FILE *fp = NULL;
	char buf[UPLOAD_BUF_SIZE + 136], buf_obj[32], *pb;
	int fd, count, ch, ret = -1, found_part = 0, found_body = 0;
	size_t pending = 0, keep, offset, bndr_len = bndr ? strlen(bndr) : 0;
	long filelen;

	/* A rejected new request must never leave an older upload actionable. */
	unlink(fn);
	if (clen <= 0 || hdr_size <= 0 || hdr_size > UPLOAD_BUF_SIZE ||
	    (bndr && (bndr_len < 3 || bndr_len >= 128)))
		goto out;

	snprintf(buf_obj, sizeof(buf_obj), "name=\"%s\"", obj_name);
	while (clen > 0) {
		if (!fgets(buf, MIN((size_t)clen + 1, sizeof(buf)), stream))
			goto out;
		clen -= strlen(buf);
		if (!strncasecmp(buf, "Content-Disposition:", 20) && strstr(buf, buf_obj)) {
			found_part = 1;
			break;
		}
	}
	while (found_part && clen > 0) {
		if (!fgets(buf, MIN((size_t)clen + 1, sizeof(buf)), stream))
			goto out;
		clen -= strlen(buf);
		if (!strcmp(buf, "\n") || !strcmp(buf, "\r\n")) {
			found_body = 1;
			break;
		}
	}
	if (!found_body || clen < hdr_size)
		goto out;

	filelen = clen;
	if (fread(buf, 1, hdr_size, stream) != (size_t)hdr_size)
		goto out;
	clen -= hdr_size;
	if (func_hdr(buf, &filelen) != 0 ||
	    (!bndr && (filelen < hdr_size || filelen - hdr_size > clen)))
		goto out;

	fd = open(fn, O_WRONLY|O_CREAT|O_EXCL, 0600);
	if (fd < 0)
		goto out;
	fp = fdopen(fd, "wb");
	if (!fp) {
		close(fd);
		goto out;
	}
	if (fwrite(buf, 1, hdr_size, fp) != (size_t)hdr_size)
		goto out;

	if (!bndr) {
		filelen -= hdr_size;
		while (filelen > 0) {
			count = fread(buf, 1, MIN(filelen, UPLOAD_BUF_SIZE), stream);
			if (count <= 0)
				goto out;
			clen -= count;
			filelen -= count;
			if (fwrite(buf, 1, count, fp) != (size_t)count)
				goto out;
		}
	} else {
		/* Keep a boundary-sized suffix until the next read.  This also
		 * removes a marker split between reads without writing its prefix. */
		int found_boundary = 0;
		while (clen > 0) {
			count = fread(buf + pending, 1, MIN(clen, UPLOAD_BUF_SIZE), stream);
			if (count <= 0)
				goto out;
			clen -= count;
			pending += count;
			pb = NULL;
			for (offset = 0; offset < pending; offset++) {
				if (multipart_boundary_end(buf + offset, pending - offset, bndr, bndr_len, clen == 0) ||
				    multipart_boundary_end(buf + offset, pending - offset, bndr + 1, bndr_len - 1, clen == 0)) {
					pb = buf + offset;
					break;
				}
			}
			if (pb) {
				count = pb - buf;
				if (fwrite(buf, 1, count, fp) != (size_t)count)
					goto out;
				found_boundary = 1;
				break;
			}
			keep = MIN(pending, bndr_len + 4);
			count = pending - keep;
			if (fwrite(buf, 1, count, fp) != (size_t)count)
				goto out;
			memmove(buf, buf + count, keep);
			pending = keep;
		}
		if (!found_boundary)
			goto out;
	}

	/* Content-Length is a promise: an early EOF is an incomplete request. */
	while (clen > 0) {
		if (fgetc(stream) == EOF)
			goto out;
		clen--;
	}
	ret = 0;

out:
	/* Buffered writes may fail only when fclose flushes the final block. */
	if (fp && fclose(fp) != 0)
		ret = -1;
	while (clen-- > 0) {
		if ((ch = fgetc(stream)) == EOF)
			break;
	}
	if (ret != 0)
		unlink(fn);
	return ret;
}

void
do_upgrade_fw_post(const char *url, FILE *stream, int clen, char *boundary)
{
	const char *upload_file = FW_IMG_NAME;
	struct statvfs vfs;
	unsigned long long avail = 0;
	int ret;

	unlink(upload_file);
	unlink("/tmp/fwcheck.log");
	if (statvfs("/tmp", &vfs) == 0)
		avail = (unsigned long long)vfs.f_bavail * vfs.f_frsize;
	fwlog("post: clen=%d avail=%llu", clen, avail);
	if (clen <= 0 || avail < (unsigned long long)clen + (1U << 20)) {
		fwlog("post: not enough free space in /tmp");
		httpd_log("%s: not enough free space in /tmp", "Firmware update");
		return;
	}

	/* delete some files (need free space in /tmp) */
	unlink("/tmp/usb.log");
	unlink("/tmp/syscmd.log");
	doSystem("rm -rf %s", "/tmp/xupnpd-cache");
	doSystem("rm -rf %s", "/tmp/xupnpd-feeds");

	/* rc creates its own exclusive private RAM writer after save preflight.
	 * Never copy an executable through the shared /tmp/mtd_write pathname. */

	/* reclaim RAM from caches */
	fput_int("/proc/sys/vm/drop_caches", 1);

	ret = do_upload_file(stream, clen, NULL, upload_file, "file", check_header_image, sizeof(image_header_t));
	fwlog("post: upload ret=%d", ret);
	if (ret == 0) {
		ret = check_crc_image(upload_file);
		fwlog("post: crc ret=%d", ret);
		if (ret != 0)
			unlink(upload_file);
	}
}

void
do_restore_nv_post(const char *url, FILE *stream, int clen, char *boundary)
{
	const char *upload_file = PROFILE_FIFO_UPLOAD;

	do_upload_file(stream, clen, NULL, upload_file, "file_nv", check_header_nvram, 8);
}

void
do_restore_st_post(const char *url, FILE *stream, int clen, char *boundary)
{
	const char *upload_file = STORAGE_FIFO_FILENAME;
	char bndr[128];

	if (!boundary || !*boundary || strlen(boundary) > sizeof(bndr) - 5) {
		unlink(upload_file);
		return;
	}

	/* BZ2 not store file length in the header, check boundary marker */
	snprintf(bndr, sizeof(bndr), "\r\n--%s", boundary);
	do_upload_file(stream, clen, bndr, upload_file, "file_st", check_header_bz2, 10);
}
