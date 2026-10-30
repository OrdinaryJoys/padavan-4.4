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
/*
 * Frontend command-line utility for Linux NVRAM layer
 *
 * Copyright 2004, ASUSTeK Inc.
 * All Rights Reserved.
 * 
 * THIS SOFTWARE IS OFFERED "AS IS", AND BROADCOM GRANTS NO WARRANTIES OF ANY
 * KIND, EXPRESS OR IMPLIED, BY STATUTE, COMMUNICATION OR OTHERWISE. BROADCOM
 * SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS
 * FOR A SPECIFIC PURPOSE OR NONINFRINGEMENT CONCERNING THIS SOFTWARE.
 *
 * $Id: nvram.c,v 1.1 2007/06/08 10:22:42 arthur Exp $
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>

#include <bcmnvram.h>

#include <nvram_linux.h>

#define PROFILE_HEADER		"HDR1"
#define PROFILE_HEADER_NEW	"HDR2"

static void usage(void)
{
	printf("Usage: nvram [get name] [set name=value] [settmp name=value] [unset name]\n"
	       "             [show] [showall] [clear] [save fn] [restore fn] [commit]\n");
	exit(1);
}

static unsigned char get_rand()
{
	unsigned char buf[1];
	FILE *fp;

	fp = fopen("/dev/urandom", "r");
	if (fp == NULL) {
		return 0;
	}
	fread(buf, 1, 1, fp);
	fclose(fp);

	return buf[0];
}

static int is_sys_param(char *p)
{
	struct nvram_pair *np;
	extern struct nvram_pair router_defaults[];
	extern struct nvram_pair tables_defaults[];

	for (np = router_defaults; np->name; np++)
	{
		if (strcmp(p, np->name)==0)
			return 1;
	}

	for (np = tables_defaults; np->name; np++)
	{
		if (strstr(p, np->name))
			return 1;
	}

	return 0;
}

static int nvram_save(char *file)
{
	FILE *fp = NULL;
	char *name, *end, *limit, *buf = NULL, *candidate = NULL;
	size_t count, i;
	uint32_t filelen;
	unsigned char rand = 0, temp;
	int fd, candidate_created = 0, ret = -1;

	buf = malloc(NVRAM_SPACE);
	if (!buf)
		goto out;
	buf[0] = 0;
	if (nvram_getall(buf, NVRAM_SPACE, 0) != 0)
		goto out;

	count = 0;
	limit = buf + NVRAM_SPACE;
	for (name = buf; name < limit && *name; name = end + 1) {
		end = memchr(name, 0, limit - name);
		if (!end)
			goto out;
		count += end - name + 1;
	}
	if (name == limit)
		goto out;
	filelen = count + (1024 - count % 1024);
	if (filelen > NVRAM_SPACE)
		goto out;
	rand = get_rand() % 30;

	/* Publish only a completely written backup, preserving any old copy on
	 * read, allocation, write or flush failure. mkstemp also keeps it private. */
	candidate = malloc(strlen(file) + sizeof(".new.XXXXXX"));
	if (!candidate)
		goto out;
	sprintf(candidate, "%s.new.XXXXXX", file);
	fd = mkstemp(candidate);
	if (fd < 0)
		goto out;
	candidate_created = 1;
	fp = fdopen(fd, "wb");
	if (!fp) {
		close(fd);
		goto out;
	}
	if (fwrite(PROFILE_HEADER_NEW, 1, 4, fp) != 4 ||
	    fwrite(&filelen, 1, 3, fp) != 3 || fwrite(&rand, 1, 1, fp) != 1)
		goto out;

	for (i = 0; i < count; i++) {
		if (buf[i] == 0)
			buf[i] = 0xfd + get_rand() % 3;
		else
			buf[i] = 0xff - buf[i] + rand;
	}
	if (fwrite(buf, 1, count, fp) != count)
		goto out;
	for (i = count; i < filelen; i++) {
		temp = 0xfd + get_rand() % 3;
		if (fwrite(&temp, 1, 1, fp) != 1)
			goto out;
	}
	if (ferror(fp) || fflush(fp) != 0)
		goto out;
	if (fclose(fp) != 0) {
		fp = NULL;
		goto out;
	}
	fp = NULL;
	if (rename(candidate, file) != 0)
		goto out;
	ret = 0;
out:
	if (fp)
		fclose(fp);
	if (ret != 0 && candidate_created)
		unlink(candidate);
	free(candidate);
	free(buf);
	return ret;
}

static int nvram_restore(char *file)
{
	FILE *fp;
	char header[8], *p, *v, *end, *limit, *buf;
	uint32_t filelen;
	size_t i;
	unsigned char rand;
	int encoded, ret = 1;

	if ((fp = fopen(file, "rb")) == NULL)
		return -1;
	if (fread(header, 1, sizeof(header), fp) != sizeof(header)) {
		fclose(fp);
		return 1;
	}
	memcpy(&filelen, header + 4, sizeof(filelen));
	encoded = memcmp(header, PROFILE_HEADER_NEW, 4) == 0;
	if (encoded)
		filelen &= 0xffffff;
	else if (memcmp(header, PROFILE_HEADER, 4) != 0) {
		fclose(fp);
		return 1;
	}
	if (filelen == 0 || filelen > NVRAM_SPACE) {
		fclose(fp);
		return 1;
	}
	buf = malloc(filelen);
	if (!buf) {
		fclose(fp);
		return -1;
	}
	if (fread(buf, 1, filelen, fp) != filelen || ferror(fp))
		goto out;
	if (encoded) {
		rand = (unsigned char)header[7];
		for (i = 0; i < filelen; i++) {
			if ((unsigned char)buf[i] >= 0xfd)
				buf[i] = 0;
			else
				buf[i] = 0xff + rand - (unsigned char)buf[i];
		}
	}

	/* Validate every entry and the terminating empty entry before clearing
	 * any live configuration.  Never scan beyond the uploaded payload. */
	limit = buf + filelen;
	for (p = buf; p < limit && *p; p = end + 1) {
		end = memchr(p, 0, limit - p);
		if (!end || !memchr(p, '=', end - p) || *p == '=')
			goto out;
	}
	if (p == limit)
		goto out;

	if (nvram_clear() != 0)
		goto out;
	for (p = buf; *p; p = end + 1) {
		end = p + strlen(p);
		v = strchr(p, '=');
		*v++ = 0;
		if (is_sys_param(p) && nvram_set(p, v) != 0)
			goto out;
	}
	ret = 0;

out:
	fclose(fp);
	free(buf);
	return ret;
}

static int nvram_show(int show_all)
{
	char *name, *buf;
	int buf_len, size;

	buf_len = NVRAM_SPACE;
	if (show_all)
		buf_len *= 2;

	buf = malloc(buf_len);
	if (!buf) {
		perror ("Out of memory!\n");
		return -1;
	}

	buf[0] = 0;
	nvram_getall(buf, buf_len, show_all);

	for (name = buf; *name; name += strlen(name) + 1)
		puts(name);

	if (!show_all) {
		size = sizeof(struct nvram_header) + (int) name - (int) buf;
		printf("\nsize: %d bytes (%d left)\n", size, NVRAM_SPACE - size);
	}

	free(buf);

	return 0;
}

/* NVRAM utility */
int
main(int argc, char **argv)
{
	char *name, *value;
	int ret = 0;

	/* Skip program name */
	--argc;
	++argv;

	if (!*argv)
		usage();

	/* Process the remaining arguments. */
	for (; *argv; argv++) {
		if (!strcmp(*argv, "get")) {
			if (*++argv) {
				if ((value = nvram_get(*argv)))
					puts(value);
			}
		}
		else if (!strcmp(*argv, "settmp")) {
			if (*++argv) {
				char buf[1024];
				strncpy(value = buf, *argv, sizeof(buf)-1);
				name = strsep(&value, "=");
				nvram_set_temp(name, value);
			}
		}
		else if (!strcmp(*argv, "set")) {
			if (*++argv) {
				char buf[1024];
				strncpy(value = buf, *argv, sizeof(buf)-1);
				name = strsep(&value, "=");
				nvram_set(name, value);
			}
		}
		else if (!strcmp(*argv, "unset")) {
			if (*++argv)
				nvram_unset(*argv);
		}
		else if (!strcmp(*argv, "clear")) {
			nvram_clear();
		}
		else if (!strcmp(*argv, "commit")) {
			nvram_commit();
			break;
		}
		else if (!strcmp(*argv, "save")) {
			if (*++argv)
				ret |= nvram_save(*argv);
			break;
		}
		else if (!strcmp(*argv, "restore")) {
			if (*++argv)
				ret |= nvram_restore(*argv);
			break;
		}
		else if (!strcmp(*argv, "show")) {
			ret |= nvram_show(0);
			break;
		}
		else if (!strcmp(*argv, "showall")) {
			ret |= nvram_show(1);
			break;
		}
		if (!*argv)
			break;
	}

	return ret;
}
