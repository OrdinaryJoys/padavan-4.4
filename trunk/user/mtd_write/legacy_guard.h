/* K2P legacy data-partition admission. Firmware writes belong exclusively to
 * the resident transaction controller. This is not a sandbox against root:
 * direct device syscalls and a root-modified mount namespace are outside it.
 * Only read-only discovery/stat calls occur before admission. */
#ifndef PADAVAN_MTD_LEGACY_GUARD_H
#define PADAVAN_MTD_LEGACY_GUARD_H

#if defined(MTD_K2P_LEGACY_GUARD) && MTD_K2P_LEGACY_GUARD
#ifdef __linux__
#include <sys/sysmacros.h>
#endif
#include <ctype.h>

#ifndef LEGACY_GUARD_PROC_MTD
#define LEGACY_GUARD_PROC_MTD "/proc/mtd"
#endif
#ifndef LEGACY_GUARD_OWNER
#define LEGACY_GUARD_OWNER 0
#endif
#ifndef LEGACY_GUARD_STAT
#define LEGACY_GUARD_STAT stat
#endif

#define LEGACY_GUARD_PARTS 32
#define LEGACY_GUARD_INPUT_BYTES 8192
struct legacy_guard_part {
	unsigned int index;
	unsigned long size;
	char name[64];
};

static void legacy_guard_spaces(char **p)
{
	while (**p == ' ' || **p == '\t')
		++*p;
}

static int legacy_guard_number(char **p, unsigned int base, unsigned long max,
			       unsigned long *value)
{
	char *end;
	if ((base == 10 && !isdigit((unsigned char)**p)) ||
	    (base == 16 && !isxdigit((unsigned char)**p)))
		return 0;
	errno = 0;
	*value = strtoul(*p, &end, base);
	if (errno || end == *p || *value > max)
		return 0;
	*p = end;
	return 1;
}

static int legacy_guard_read_parts(struct legacy_guard_part *parts, unsigned int *count)
{
	char line[256], a[8], b[16], c[16], d[16], extra;
	FILE *stream;
	struct stat st;
	int fd, ok = 0;
	unsigned int used = 0, bytes = 0, firmware = 0, all = 0, storage = 0, config = 0;
	unsigned int bootloader = 0, factory = 0, kernel = 0, rootfs = 0;
	unsigned long kernel_size = 0, rootfs_size = 0;
	fd = open(LEGACY_GUARD_PROC_MTD, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0)
		return 0;
	if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != LEGACY_GUARD_OWNER ||
	    (st.st_mode & 022) || st.st_nlink != 1) {
		close(fd);
		return 0;
	}
	stream = fdopen(fd, "r");
	if (!stream) {
		close(fd);
		return 0;
	}
	if (!fgets(line, sizeof(line), stream) ||
	    sscanf(line, "%7s %15s %15s %15s %c", a, b, c, d, &extra) != 4 ||
	    strcmp(a, "dev:") || strcmp(b, "size") || strcmp(c, "erasesize") || strcmp(d, "name"))
		goto out;
	bytes = strlen(line);
	while (fgets(line, sizeof(line), stream)) {
		unsigned long index, size, erase;
		unsigned int i;
		char *p = line, *name;
		size_t length = strlen(line), namesize;
		if (!length || line[length - 1] != '\n' || used == LEGACY_GUARD_PARTS ||
		    length > LEGACY_GUARD_INPUT_BYTES - bytes || strncmp(p, "mtd", 3))
			goto out;
		bytes += length;
		p += 3;
		if (!legacy_guard_number(&p, 10, 127, &index) || *p++ != ':')
			goto out;
		legacy_guard_spaces(&p);
		if (!legacy_guard_number(&p, 16, 0x1000000UL, &size) || !size ||
		    (*p != ' ' && *p != '\t'))
			goto out;
		legacy_guard_spaces(&p);
		if (!legacy_guard_number(&p, 16, 0x10000UL, &erase) || erase != 0x10000UL ||
		    (*p != ' ' && *p != '\t'))
			goto out;
		legacy_guard_spaces(&p);
		if (*p++ != '"')
			goto out;
		name = p;
		while (*p && *p != '"') {
			if (!isalnum((unsigned char)*p) && *p != '_' && *p != '-')
				goto out;
			p++;
		}
		namesize = p - name;
		if (!namesize || namesize >= sizeof(parts[used].name) || *p++ != '"')
			goto out;
		legacy_guard_spaces(&p);
		if (*p != '\n' || p[1])
			goto out;
		memcpy(parts[used].name, name, namesize);
		parts[used].name[namesize] = 0;
		parts[used].index = (unsigned int)index;
		parts[used].size = size;
		for (i = 0; i < used; ++i)
			if (parts[i].index == index || !strcasecmp(parts[i].name, parts[used].name))
				goto out;
		if (!strcasecmp(parts[used].name, "firmware")) {
			if (size != 0xf30000UL) goto out;
			firmware++;
		} else if (!strcasecmp(parts[used].name, "ALL")) {
			if (size != 0x1000000UL) goto out;
			all++;
		} else if (!strcmp(parts[used].name, "Storage")) {
			if (size != 0x80000UL) goto out;
			storage++;
		} else if (!strcasecmp(parts[used].name, "Config") || !strcasecmp(parts[used].name, "Nvram")) {
			if (size != 0x10000UL) goto out;
			config++;
		} else if (!strcasecmp(parts[used].name, "Bootloader")) {
			if (size != 0x30000UL) goto out;
			bootloader++;
		} else if (!strcasecmp(parts[used].name, "Factory")) {
			if (size != 0x10000UL) goto out;
			factory++;
		} else if (!strcasecmp(parts[used].name, "kernel")) {
			kernel++;
			kernel_size = size;
		} else if (!strcasecmp(parts[used].name, "rootfs")) {
			rootfs++;
			rootfs_size = size;
		} else {
			goto out;
		}
		used++;
	}
	if (ferror(stream) || used != 8 || firmware != 1 || all != 1 || storage != 1 || config != 1 ||
	    bootloader != 1 || factory != 1 || kernel != 1 || rootfs != 1 ||
	    kernel_size > 0xf30000UL || rootfs_size != 0xf30000UL - kernel_size)
		goto out;
	*count = used;
	ok = 1;
out:
	if (fclose(stream))
		ok = 0;
	return ok;
}

static int legacy_guard_data_part(const struct legacy_guard_part *part)
{
	return !strcmp(part->name, "Storage") || !strcasecmp(part->name, "Config") ||
	       !strcasecmp(part->name, "Nvram");
}

static int legacy_guard_target(const char *target, const struct legacy_guard_part *parts, unsigned int count)
{
	char component[PATH_MAX];
	const char *end;
	unsigned int i;
	if (!target || !*target || strnlen(target, PATH_MAX) == PATH_MAX)
		return 0;
	do {
		struct stat st;
		int found = 0;
		size_t length;
		end = strchr(target, ':');
		length = end ? (size_t)(end - target) : strlen(target);
		if (!length)
			return 0;
		memcpy(component, target, length);
		component[length] = 0;
		for (i = 0; i < count; ++i)
			if (!strcmp(component, parts[i].name)) {
				if (!legacy_guard_data_part(&parts[i]))
					return 0;
				found = 1;
				break;
			}
		/* Unknown spellings, paths, symlinks and alternate device names must
		 * resolve read-only to a known MTD char/block device. No writable
		 * open is needed to reject Firmware aliases and whole-flash nodes. */
		if (!found) {
			unsigned int index, kind;
			if (LEGACY_GUARD_STAT(component, &st))
				return 0;
			kind = major(st.st_rdev);
			if (S_ISCHR(st.st_mode) && kind == 90)
				index = minor(st.st_rdev) / 2;
			else if (S_ISBLK(st.st_mode) && kind == 31)
				index = minor(st.st_rdev);
			else
				return 0;
			for (i = 0; i < count; ++i)
				if (parts[i].index == index) {
					if (!legacy_guard_data_part(&parts[i]))
						return 0;
					found = 1;
					break;
				}
			if (!found)
				return 0;
		}
		target = end ? end + 1 : NULL;
	} while (target);
	return 1;
}

static int legacy_firmware_command_allowed(int argc, char **argv, char **erase, int boot)
{
	struct legacy_guard_part parts[LEGACY_GUARD_PARTS];
	unsigned int count = 0, i;
	int readonly = !strcmp(argv[0], "dump") || !strcmp(argv[0], "verify");
	/* Even a read-only -r command has the unsafe shell/raw-reset fallback.
	 * Data saves use no -r; reboot remains a separately guarded rc action. */
	if (boot)
		return 0;
	if (readonly && !erase[0])
		return 1;
	if (!legacy_guard_read_parts(parts, &count))
		return 0;
	if (!readonly && (argc < 2 || !legacy_guard_target(argv[argc - 1], parts, count)))
		return 0;
	for (i = 0; erase[i]; ++i)
		if (!legacy_guard_target(erase[i], parts, count))
			return 0;
	return 1;
}
#endif
#endif
