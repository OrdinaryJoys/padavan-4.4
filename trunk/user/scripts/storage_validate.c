/* Validate a bounded storage tar before any member reaches the filesystem.
 * Supports the V7/USTAR/GNU long-name subset produced by BusyBox tar.
 * No archive entry is ever extracted by this program. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "startup_config_publish.h"

#define BLOCK 512U
#define MAX_TAR (8U * 1024U * 1024U)
#define MAX_NAME 4096U
#define MAX_ENTRIES 4096U
#define MAX_NAMES (1024U * 1024U)
#define MAX_DEPTH 64U
#define MAX_COMPONENT 255U
#define MAX_RELATIVE 2048U

struct entry { char *name; int link; int type; };
static struct entry entries[MAX_ENTRIES];
static unsigned int count, directory_count;
static char *directories[MAX_ENTRIES];
static size_t names_size;
static uint64_t needed;
static int have_start;

static int fail(const char *reason)
{
	fprintf(stderr, "Invalid storage archive: %s\n", reason);
	return 1;
}

static int octal(const unsigned char *p, size_t len, uint64_t *value)
{
	size_t i = 0;
	uint64_t n = 0;
	while (i < len && p[i] == ' ') i++;
	for (; i < len && p[i] >= '0' && p[i] <= '7'; i++) {
		if (n > (UINT64_MAX - 7) / 8) return -1;
		n = n * 8 + (p[i] - '0');
	}
	for (; i < len; i++)
		if (p[i] && p[i] != ' ') return -1;
	*value = n;
	return 0;
}

static int field(char *out, size_t capacity, const unsigned char *p, size_t len)
{
	size_t n = 0;
	while (n < len && p[n]) n++;
	if (n >= capacity) return -1;
	memcpy(out, p, n);
	out[n] = 0;
	return 0;
}

/* Canonicalise harmless ./ and repeated slashes; never interpret .. . */
static int path(char *out, const char *in)
{
	const char *p = in, *end;
	size_t n = 0, length;
	if (!*p || *p == '/') return -1;
	while (*p) {
		while (*p == '/') p++;
		if (!*p) break;
		end = strchr(p, '/');
		length = end ? (size_t)(end - p) : strlen(p);
		if (length > MAX_COMPONENT || (length == 2 && p[0] == '.' && p[1] == '.')) return -1;
		if (!(length == 1 && p[0] == '.')) {
			size_t i;
			if (n + length + 1 >= MAX_NAME) return -1;
			for (i = 0; i < length; i++)
				if ((unsigned char)p[i] < 32 || (unsigned char)p[i] == 127) return -1;
			if (n) out[n++] = '/';
			memcpy(out + n, p, length);
			n += length;
		}
		p += length;
	}
	if (!n) out[n++] = '.';
	if (n > MAX_RELATIVE) return -1;
	out[n] = 0;
	return 0;
}

static int ancestor(const char *parent, const char *child)
{
	size_t n = strlen(parent);
	return strncmp(parent, child, n) == 0 && child[n] == '/';
}

/* Legacy backups list files without their parent directory headers. */
static int charge_directory(const char *name, size_t len, uint64_t budget)
{
	unsigned int i;
	for (i = 0; i < directory_count; i++)
		if (strlen(directories[i]) == len && !memcmp(directories[i], name, len)) return 0;
	if (directory_count == MAX_ENTRIES || names_size + len + 1 > MAX_NAMES) return -1;
	needed += 4096;
	if (needed > budget) return -1;
	directories[directory_count] = malloc(len + 1);
	if (!directories[directory_count]) return -1;
	memcpy(directories[directory_count], name, len);
	directories[directory_count][len] = 0;
	names_size += len + 1;
	directory_count++;
	return 0;
}

static int remember(const char *name, const char *link, int type, uint64_t size,
		    uint64_t budget)
{
	unsigned int i, depth = 1;
	const char *slash;
	int target = -1;
	size_t len = strlen(name) + 1;
	if (count == MAX_ENTRIES || names_size + len > MAX_NAMES) return -1;
	for (i = 0; i < count; i++) {
		if (!strcmp(entries[i].name, name)) return -1;
		if ((entries[i].type != '5' && ancestor(entries[i].name, name)) ||
		    (type != '5' && ancestor(name, entries[i].name))) return -1;
		if (link && !strcmp(entries[i].name, link) && entries[i].type == '0') target = (int)i;
	}
	/* A hardlink must name an earlier ordinary member, never a symlink. */
	if (type == '1' && target < 0) return -1;
	if (!strcmp(name, ".") && type != '5') return -1;
	if (!strcmp(name, "start_script.sh")) {
		if (type != '0') return -1;
		have_start = 1;
	}
	for (slash = name; *slash; slash++) {
		if (*slash == '/') {
			if (++depth > MAX_DEPTH || charge_directory(name, slash - name, budget)) return -1;
		}
	}
	if (type == '5' && charge_directory(name, strlen(name), budget)) return -1;
	if (type == '2') size = strlen(link) + 1;
	needed += ((size + 4095) / 4096) * 4096 + 4096;
	if (needed > budget) return -1;
	if (names_size + len > MAX_NAMES) return -1;
	entries[count].name = malloc(len);
	if (!entries[count].name) return -1;
	memcpy(entries[count].name, name, len);
	entries[count].link = type == '1' || type == '2';
	entries[count].type = type;
	names_size += len;
	count++;
	return 0;
}

static int validate(FILE *fp, uint64_t budget)
{
	unsigned char h[BLOCK];
	char name[MAX_NAME], canon[MAX_NAME], link[MAX_NAME], canon_link[MAX_NAME];
	char long_name[MAX_NAME] = {0}, long_link[MAX_NAME] = {0}, prefix[156];
	uint64_t size, checksum, mode, sum;
	unsigned int zeros = 0;
	size_t got, i;
	int type;
	while ((got = fread(h, 1, sizeof(h), fp)) == sizeof(h)) {
		sum = 0;
		for (i = 0; i < sizeof(h); i++) sum += h[i];
		if (!sum) { zeros++; continue; }
		if (zeros) return fail("data after end marker");
		if (!h[0] && !h[345]) return fail("nonzero empty-name header");
		if (octal(h + 148, 8, &checksum)) return fail("checksum encoding");
		sum = 0;
		for (i = 0; i < sizeof(h); i++) sum += i >= 148 && i < 156 ? ' ' : h[i];
		if (sum != checksum) return fail("header checksum");
		if (memcmp(h + 257, "ustar\0", 6) && memcmp(h + 257, "ustar ", 6) &&
		    memcmp(h + 257, "\0\0\0\0\0\0", 6)) return fail("unknown tar format");
		if (octal(h + 124, 12, &size) || size > MAX_TAR ||
		    octal(h + 100, 8, &mode) || (mode & ~0777U)) return fail("size or mode");
		type = h[156] ? h[156] : '0';
		if (type == 'L' || type == 'K') {
			char *dest = type == 'L' ? long_name : long_link;
			uint64_t offset = 0;
			int ended = 0;
			if (*dest || !size || size >= MAX_NAME) return fail("long-name extension");
			while (offset < size) {
				if (fread(h, 1, sizeof(h), fp) != sizeof(h)) return fail("truncated extension");
				for (i = 0; i < sizeof(h) && offset < size; i++, offset++) {
					if (!h[i]) ended = 1;
					else if (ended) return fail("long-name trailing bytes");
					dest[offset] = h[i];
				}
			}
			if (!ended || !*dest) return fail("unterminated long-name extension");
			continue;
		}
		if (type != '0' && type != '1' && type != '2' && type != '5')
			return fail("unsupported type (including PAX, sparse or device)");
		if (type != '0' && size) return fail("payload on non-regular member");
		if (field(name, sizeof(name), h, 100) || field(link, sizeof(link), h + 157, 100))
			return fail("name length");
		/* Match BusyBox 1.24: it combines prefix for every accepted format,
		 * including V7/GNU/non-00 USTAR, before a GNU L override. */
		{
			if (field(prefix, sizeof(prefix), h + 345, 155)) return fail("prefix length");
			if (*prefix) {
				char combined[MAX_NAME];
				if (snprintf(combined, sizeof(combined), "%s/%s", prefix, name) >= (int)sizeof(combined))
					return fail("combined name length");
				strcpy(name, combined);
			}
		}
		if (*long_name) strcpy(name, long_name);
		if (*long_link) strcpy(link, long_link);
		long_name[0] = long_link[0] = 0;
		if (type == '0' && *name && name[strlen(name) - 1] == '/') {
			if (size) return fail("payload on V7 directory");
			type = '5';
		}
		if (path(canon, name)) return fail("member path");
		if (type == '1' || type == '2') {
			if (path(canon_link, link)) return fail("link target");
		} else if (*link) return fail("unexpected link target");
		if (remember(canon, type == '1' || type == '2' ? canon_link : NULL,
			     type, size, budget)) return fail("duplicate, non-directory parent or extraction budget");
		while (size) {
			if (fread(h, 1, sizeof(h), fp) != sizeof(h)) return fail("truncated payload");
			size = size > BLOCK ? size - BLOCK : 0;
		}
	}
	if (got || ferror(fp) || zeros < 2 || *long_name || *long_link || !have_start)
		return fail("truncated archive or missing start_script.sh");
	return 0;
}

int main(int argc, char **argv)
{
	FILE *fp;
	struct stat st;
	char *end;
	unsigned long long budget;
	unsigned int i;
	int result;
	if (argc == 5 && !strcmp(argv[1], "--publish-config"))
		return startup_config_publish(argv[2], argv[3], argv[4]);
	/* rename(2) replaces the final path itself. BusyBox mv follows a
	 * destination symlink to a directory, which is unsafe in public /tmp. */
	if (argc == 4 && !strcmp(argv[1], "--rename-directory")) {
		if (lstat(argv[2], &st) || !S_ISDIR(st.st_mode) || st.st_uid != geteuid())
			return fail("unsafe directory source");
		return rename(argv[2], argv[3]) ? fail("cannot rename directory") : 0;
	}
	if (argc == 4 && (!strcmp(argv[1], "--publish-backup") || !strcmp(argv[1], "--replace-file"))) {
		if (lstat(argv[2], &st) || !S_ISREG(st.st_mode) ||
		    st.st_uid != geteuid() || (st.st_mode & 077)) return fail("unsafe backup source");
		return rename(argv[2], argv[3]) ? fail("cannot publish backup") : 0;
	}
	if (argc != 3) return fail("usage: storage_validate archive.tar available-bytes");
	errno = 0;
	budget = strtoull(argv[2], &end, 10);
	if (errno || argv[2][0] < '0' || argv[2][0] > '9' || *end || !budget) return fail("invalid budget");
	fp = fopen(argv[1], "rb");
	if (!fp) return fail("cannot open archive");
	if (fstat(fileno(fp), &st) || !S_ISREG(st.st_mode) || st.st_size < 1024 ||
	    st.st_size > MAX_TAR || st.st_size % BLOCK) {
		fclose(fp);
		return fail("archive file size");
	}
	result = validate(fp, budget);
	fclose(fp);
	for (i = 0; i < count; i++) free(entries[i].name);
	for (i = 0; i < directory_count; i++) free(directories[i]);
	return result;
}
