/* Dedicated K2P/NOR upgrade protocol. Legacy write/Storage commands do not
 * enter this path. No reboot is attempted here, even after verified success. */
#ifndef K2P_UPGRADE_WRITE_H
#define K2P_UPGRADE_WRITE_H
#include <sys/file.h>
#include <sys/mman.h>
#include <strings.h>
#include "crc32.h"

#define FWUP_LIMIT 15925248U
#define FWUP_SAFE 20
#define FWUP_UNKNOWN 21
#ifndef FWUP_OPERATION_DIR
#define FWUP_OPERATION_DIR "/tmp/.firmware_write"
#endif
#ifdef FWUP_TEST_UID
#define FWUP_OWNER ((uid_t)(FWUP_TEST_UID))
#else
#define FWUP_OWNER ((uid_t)0)
#endif
#ifndef FWUP_STATE_WRITE
#define FWUP_STATE_WRITE write
#endif
#ifndef FWUP_STATE_SYNC
#define FWUP_STATE_SYNC fsync
#endif
#ifndef FWUP_STATE_CLOSE
#define FWUP_STATE_CLOSE close
#endif
#ifndef FWUP_STATE_RENAME
#define FWUP_STATE_RENAME renameat
#endif
#ifndef FWUP_IMAGE_READ
#define FWUP_IMAGE_READ read
#endif
#ifndef FWUP_IMAGE_CLOSE
#define FWUP_IMAGE_CLOSE close
#endif
#ifndef FWUP_DEVICE_WRITE
#define FWUP_DEVICE_WRITE write
#endif
#ifndef FWUP_DEVICE_READ
#define FWUP_DEVICE_READ pread
#endif
#ifndef FWUP_DEVICE_SYNC
#define FWUP_DEVICE_SYNC fsync
#endif
#ifndef FWUP_DEVICE_CLOSE
#define FWUP_DEVICE_CLOSE close
#endif
#ifndef FWUP_IOCTL
#define FWUP_IOCTL ioctl
#endif
#ifndef FWUP_MTD_TABLE
#define FWUP_MTD_TABLE "/proc/mtd"
#endif
#ifndef FWUP_DEVICE_PREFIX
#define FWUP_DEVICE_PREFIX "/dev/mtd"
#endif
#ifndef FWUP_MTD_FSTAT
#define FWUP_MTD_FSTAT fstat
#endif
#ifndef FWUP_ALLOC
#define FWUP_ALLOC malloc
#endif
#ifndef FWUP_MLOCKALL
#define FWUP_MLOCKALL mlockall
#endif
#ifndef FWUP_MUNLOCKALL
#define FWUP_MUNLOCKALL munlockall
#endif

struct fwup_status {
	int parent;
	char leaf[128];
	struct stat current;
	unsigned int sequence;
	uint32_t image_bytes;
};

static int fwup_error(const char *message, int result)
{
	fprintf(stderr, "Firmware upgrade writer: %s\n", message);
	return result;
}

static int fwup_directory(const char *path)
{
	char copy[PATH_MAX], *part, *next;
	struct stat st;
	int fd, child;
	if (!path || path[0] != '/' || strlen(path) >= sizeof(copy)) return -1;
	strcpy(copy, path);
	fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
	if (fd < 0) return -1;
	part = copy + 1;
	while (*part) {
		next = strchr(part, '/'); if (next) *next = 0;
		if (!*part || !strcmp(part, ".") || !strcmp(part, "..")) { close(fd); return -1; }
		child = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
		close(fd);
		if (child < 0) return -1;
		if (fstat(child, &st) || (st.st_uid != 0 && st.st_uid != FWUP_OWNER) ||
		    ((st.st_mode & 022) && !(st.st_mode & S_ISVTX))) { close(child); return -1; }
		fd = child;
		if (!next) break;
		part = next + 1;
		if (!*part) { close(fd); return -1; }
	}
	return fd;
}

static int fwup_private_directory(int fd)
{
	struct stat st;
	return fstat(fd, &st) || !S_ISDIR(st.st_mode) || st.st_uid != FWUP_OWNER ||
		(st.st_mode & 07777) != 0700;
}

static int fwup_split(const char *path, char *parent, char *leaf, size_t capacity)
{
	const char *slash, *p;
	size_t n;
	if (!path || path[0] != '/' || strlen(path) >= PATH_MAX) return -1;
	for (p = path; *p; p++) if ((unsigned char)*p < 32 || (unsigned char)*p == 127) return -1;
	slash = strrchr(path, '/');
	if (!slash || !slash[1] || strlen(slash + 1) >= capacity ||
	    !strcmp(slash + 1, ".") || !strcmp(slash + 1, "..")) return -1;
	n = (size_t)(slash - path); if (!n) n = 1;
	memcpy(parent, path, n); parent[n] = 0;
	strcpy(leaf, slash + 1);
	return 0;
}

static int fwup_write_all(int fd, const unsigned char *data, size_t length, int state)
{
	while (length) {
		ssize_t n = state ? FWUP_STATE_WRITE(fd, data, length) : FWUP_DEVICE_WRITE(fd, data, length);
		if (n < 0 && errno == EINTR) continue;
		if (n <= 0 || (size_t)n > length) return -1;
		data += n; length -= (size_t)n;
	}
	return 0;
}

/* Status rename+directory fsync must finish before any unlock/erase/write.
 * A failed update is UNKNOWN even if no destructive call has occurred. */
static int fwup_publish_status(struct fwup_status *s, const char *state, int first)
{
	char temporary[80], record[256];
	struct stat st;
	int fd = -1, n, result = -1;
	n = snprintf(record, sizeof(record), "K2P_FWUP_V1\nstate=%s\npid=%ld\ntarget=firmware\nimage_bytes=%u\nverified_bytes=%u\n",
		state, (long)getpid(), s->image_bytes, !strcmp(state, "VERIFIED") ? s->image_bytes : 0U);
	if (n <= 0 || n >= (int)sizeof(record)) return -1;
	if (first) {
		fd = openat(s->parent, s->leaf, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
		if (fd < 0) return -1;
		temporary[0] = 0;
	} else {
		if (fstatat(s->parent, s->leaf, &st, AT_SYMLINK_NOFOLLOW) ||
		    !S_ISREG(st.st_mode) || st.st_uid != FWUP_OWNER || st.st_nlink != 1 ||
		    (st.st_mode & 07777) != 0600 || st.st_dev != s->current.st_dev || st.st_ino != s->current.st_ino)
			return -1;
		snprintf(temporary, sizeof(temporary), ".fwup.%ld.%u", (long)getpid(), ++s->sequence);
		fd = openat(s->parent, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
		if (fd < 0) return -1;
	}
	if (fchmod(fd, 0600) || fwup_write_all(fd, (const unsigned char *)record, (size_t)n, 1) ||
	    fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != FWUP_OWNER || st.st_nlink != 1 ||
	    (st.st_mode & 07777) != 0600 || st.st_size != n || FWUP_STATE_SYNC(fd)) goto done;
	if (FWUP_STATE_CLOSE(fd)) { fd = -1; goto done; } fd = -1;
	if (!first && FWUP_STATE_RENAME(s->parent, temporary, s->parent, s->leaf)) goto done;
	if (FWUP_STATE_SYNC(s->parent)) goto done;
	s->current = st;
	result = 0;
done:
	if (fd >= 0) close(fd);
	if (!first && temporary[0]) unlinkat(s->parent, temporary, 0);
	return result;
}

static int fwup_lock(void)
{
	char parent[PATH_MAX], leaf[128];
	int p, directory, fd;
	struct stat st;
	if (fwup_split(FWUP_OPERATION_DIR, parent, leaf, sizeof(leaf))) return -1;
	p = fwup_directory(parent); if (p < 0) return -1;
	if (mkdirat(p, leaf, 0700) && errno != EEXIST) { close(p); return -1; }
	directory = openat(p, leaf, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC); close(p);
	if (directory < 0) return -1;
	if (fwup_private_directory(directory)) { close(directory); return -1; }
	fd = openat(directory, "lock", O_WRONLY | O_CREAT | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
	close(directory); if (fd < 0) return -1;
	if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != FWUP_OWNER ||
	    st.st_nlink != 1 || (st.st_mode & 07777) != 0600 || flock(fd, LOCK_EX | LOCK_NB)) {
		close(fd); return -1;
	}
	return fd;
}

#ifndef FWUP_OPEN_DEVICE
static int fwup_open_device(struct mtd_info_user *info, int *reader)
{
	FILE *fp;
	char line[256], name[64], device[PATH_MAX];
	unsigned int index, size, erase, chosen = 0, declared_size = 0, declared_erase = 0, matches = 0;
	struct stat st, read_st;
	struct mtd_info_user read_info;
	int fd;
	fp = fopen(FWUP_MTD_TABLE, "r"); if (!fp) return -1;
	while (fgets(line, sizeof(line), fp)) {
		if (sscanf(line, "mtd%u: %x %x \"%63[^\"]\"", &index, &size, &erase, name) == 4 &&
		    !strcasecmp(name, "firmware")) {
			chosen = index; declared_size = size; declared_erase = erase; matches++;
		}
	}
	fd = ferror(fp); if (fclose(fp)) fd = 1;
	if (fd || matches != 1 || chosen > 255) return -1;
	if (snprintf(device, sizeof(device), "%s%u", FWUP_DEVICE_PREFIX, chosen) >= (int)sizeof(device)) return -1;
	fd = open(device, O_RDWR | O_SYNC | O_NOFOLLOW | O_CLOEXEC);
	if (fd < 0) return -1;
	if (FWUP_MTD_FSTAT(fd, &st) || !S_ISCHR(st.st_mode) ||
	    FWUP_IOCTL(fd, MEMGETINFO, info) || info->size != declared_size || info->erasesize != declared_erase) {
		close(fd); return -1;
	}
	*reader = open(device, O_RDONLY | O_SYNC | O_NOFOLLOW | O_CLOEXEC);
	memset(&read_info, 0, sizeof(read_info));
	if (*reader < 0 || FWUP_MTD_FSTAT(*reader, &read_st) || !S_ISCHR(read_st.st_mode) ||
	    read_st.st_rdev != st.st_rdev || read_st.st_dev != st.st_dev || read_st.st_ino != st.st_ino ||
	    FWUP_IOCTL(*reader, MEMGETINFO, &read_info) || read_info.type != info->type ||
	    read_info.flags != info->flags || read_info.size != info->size ||
	    read_info.erasesize != info->erasesize || read_info.writesize != info->writesize) {
		if (*reader >= 0) close(*reader);
		*reader = -1; close(fd); return -1;
	}
	return fd;
}
#define FWUP_OPEN_DEVICE fwup_open_device
#endif

static uint32_t fwup_be32(const unsigned char *p)
{
	return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

static int fwup_image_valid(const unsigned char *data, size_t size)
{
	unsigned char header[64];
	uint32_t boundary, load, entry;
	if (size < 64 || size > FWUP_LIMIT || fwup_be32(data) != 0x27051956 ||
	    fwup_be32(data + 12) != size - 64 || memcmp(data + 36, "K2P\0", 4) ||
	    data[28] != 5 || data[29] != 5 || data[30] != 2 || (data[31] != 0 && data[31] != 3)) return -1;
	load = fwup_be32(data + 16); entry = fwup_be32(data + 20);
	/* Structural K2P4.4 boot metadata only. Decoded kernel/DTB/entry
	 * validation remains the responsibility of the full image validator. */
	if (data[32] != 4 || data[33] != 4 || load != 0x81001000U ||
	    (entry & 3U) || entry < load || entry - load >= 32U * 1024U * 1024U) return -1;
	memcpy(header, data, sizeof(header)); memset(header + 4, 0, 4);
	if ((crc32(0xffffffffU, header, 64) ^ 0xffffffffU) != fwup_be32(data + 4) ||
	    (crc32(0xffffffffU, data + 64, (int)(size - 64)) ^ 0xffffffffU) != fwup_be32(data + 24)) return -1;
	boundary = fwup_be32(data + 60);
	if (boundary <= 64 || boundary > size - 4 || memcmp(data + boundary, "hsqs", 4)) return -1;
	return 0;
}

static int fwup_same_source(const struct stat *a, const struct stat *b)
{
	return a->st_dev == b->st_dev && a->st_ino == b->st_ino && a->st_mode == b->st_mode &&
		a->st_uid == b->st_uid && a->st_nlink == b->st_nlink && a->st_size == b->st_size &&
		a->st_mtime == b->st_mtime && a->st_ctime == b->st_ctime;
}

static int firmware_upgrade_write(const char *image, const char *target, const char *status)
{
	struct fwup_status state;
	struct mtd_info_user info;
	struct erase_info_user erase;
	struct stat source, now;
	char parent[PATH_MAX], leaf[256];
	unsigned char *snapshot = NULL, readback[16384];
	size_t size = 0, padded = 0, done, chunk;
	int imagefd = -1, device = -1, reader = -1, lock = -1, result = FWUP_UNKNOWN, sync_unsupported = 0;
	int memory_lock_attempted = 0;
	const char *message = "unsafe upgrade invocation or status directory";
	memset(&state, 0, sizeof(state)); state.parent = -1;
	if (geteuid() != FWUP_OWNER || strcmp(target, "firmware") ||
	    fwup_split(status, parent, state.leaf, sizeof(state.leaf))) goto out;
	state.parent = fwup_directory(parent);
	if (state.parent < 0 || fwup_private_directory(state.parent)) goto out;
	if (fwup_publish_status(&state, "PREWRITE", 1)) { message = "cannot initialize a fresh private status record"; goto out; }
	/* Another cooperating writer may already be destructive. A busy/unsafe
	 * global lock is UNKNOWN, not permission to restart the watchdog. */
	lock = fwup_lock(); if (lock < 0) { message = "another firmware operation is active or its lock is unsafe"; goto out; }
	result = FWUP_SAFE;
	if (fwup_split(image, parent, leaf, sizeof(leaf))) { message = "invalid image path"; goto out; }
	imagefd = fwup_directory(parent);
	if (imagefd < 0) { message = "unsafe image parent"; goto out; }
	{
		int fd = openat(imagefd, leaf, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
		close(imagefd); imagefd = fd;
	}
	if (imagefd < 0 || fstat(imagefd, &source) || !S_ISREG(source.st_mode) || source.st_uid != FWUP_OWNER ||
	    source.st_nlink != 1 || (source.st_mode & 022) || source.st_size < 64 || source.st_size > FWUP_LIMIT) {
		message = "unsafe, empty or oversized image"; goto out;
	}
	device = FWUP_OPEN_DEVICE(&info, &reader);
	if (device < 0 || info.type != MTD_NORFLASH || !(info.flags & MTD_WRITEABLE) || info.size != FWUP_LIMIT ||
	    info.writesize != 1 || info.erasesize < 4096 || info.erasesize > 1024U * 1024U ||
	    (info.erasesize & (info.erasesize - 1)) || info.size % info.erasesize) {
		message = "unsupported firmware MTD device or erase geometry"; goto out;
	}
	size = (size_t)source.st_size;
	padded = ((size + info.erasesize - 1) / info.erasesize) * info.erasesize;
	if (padded > info.size || !(snapshot = FWUP_ALLOC(padded))) { message = "cannot allocate bounded immutable image"; goto out; }
	memset(snapshot, 0xff, padded);
	for (done = 0; done < size;) {
		ssize_t n = FWUP_IMAGE_READ(imagefd, snapshot + done, size - done);
		if (n < 0 && errno == EINTR) continue;
		if (n <= 0 || (size_t)n > size - done) { message = "incomplete image read"; goto out; }
		done += (size_t)n;
	}
	if (fstat(imagefd, &now) || !fwup_same_source(&source, &now) || fwup_image_valid(snapshot, size)) {
		message = "image changed or K2P header/CRC validation failed"; goto out;
	}
	if (FWUP_IMAGE_CLOSE(imagefd)) { imagefd = -1; message = "cannot close validated image"; goto out; } imagefd = -1;
	/* Exercise the readback interface before committing to a write. */
	if (reader < 0 || FWUP_DEVICE_READ(reader, readback, 1, 0) != 1 || lseek(device, 0, SEEK_SET) != 0) {
		message = "firmware device readback/seek is unavailable"; goto out;
	}
	/* Linux4.4 mtdchar has no .fsync: vfs_fsync returns EINVAL. Its RW
	 * release performs mtd_sync. Establish that capability before erase,
	 * then close the writer before verifying through the pre-opened reader. */
	if (FWUP_DEVICE_SYNC(device)) {
		if (errno != EINVAL && errno != EOPNOTSUPP && errno != ENOTTY) {
			message = "firmware device sync probe failed before write"; goto out;
		}
		sync_unsupported = errno;
	}
	/* Request residency for image/stack/executable/current libraries before
	 * replacing their backing rootfs. -z now binds symbols before main.
	 * This checked syscall is a guard, not proof that every page faulted in:
	 * Linux4.4 mlockall ignores some internal VMA/populate errors. Neither
	 * this guard nor readback establishes power-loss or hardware boot safety.
	 * An explicit syscall failure still aborts safely before MAYBE. */
	memory_lock_attempted = 1;
	if (FWUP_MLOCKALL(MCL_CURRENT | MCL_FUTURE) != 0) {
		message = "cannot lock complete writer memory before flash"; goto out;
	}
	state.image_bytes = (uint32_t)size;
	result = FWUP_UNKNOWN;
	if (fwup_publish_status(&state, "MAYBE_WRITTEN", 0)) { message = "cannot commit write-stage status; no flash attempted"; goto out; }
	for (done = 0; done < padded; done += info.erasesize) {
		erase.start = (uint32_t)done; erase.length = info.erasesize;
		if (FWUP_IOCTL(device, MEMUNLOCK, &erase) && errno != EOPNOTSUPP && errno != ENOTTY) {
			message = "firmware unlock failed after entering write stage"; goto out;
		}
		if (FWUP_IOCTL(device, MEMERASE, &erase)) { message = "firmware erase may be incomplete"; goto out; }
	}
	if (fwup_write_all(device, snapshot, padded, 0)) { message = "firmware write may be incomplete"; goto out; }
	if (FWUP_DEVICE_SYNC(device) && (!sync_unsupported || errno != sync_unsupported)) {
		message = "firmware sync may be incomplete"; goto out;
	}
	if (FWUP_DEVICE_CLOSE(device)) { device = -1; message = "firmware writer close/sync failed"; goto out; } device = -1;
	for (done = 0; done < padded; done += chunk) {
		size_t have = 0;
		chunk = padded - done; if (chunk > sizeof(readback)) chunk = sizeof(readback);
		while (have < chunk) {
			ssize_t n = FWUP_DEVICE_READ(reader, readback + have, chunk - have, (off_t)(done + have));
			if (n < 0 && errno == EINTR) continue;
			if (n <= 0 || (size_t)n > chunk - have) { message = "firmware readback is incomplete"; goto out; }
			have += (size_t)n;
		}
		if (memcmp(snapshot + done, readback, chunk)) { message = "firmware readback does not match immutable image"; goto out; }
	}
	if (FWUP_DEVICE_CLOSE(reader)) { reader = -1; message = "firmware reader close failed after readback"; goto out; } reader = -1;
	if (fwup_publish_status(&state, "VERIFIED", 0)) { message = "verified flash but final status publication failed"; goto out; }
	result = 0;
out:
	if (imagefd >= 0) close(imagefd);
	if (device >= 0) close(device);
	if (reader >= 0) close(reader);
	free(snapshot);
	if (lock >= 0) close(lock);
	if (state.parent >= 0) close(state.parent);
	/* Preserve residency through error reporting and CRT exit after a
	 * possible write. The kernel releases those locks when this process
	 * exits. A safe prewrite abort may release any partial mlockall work. */
	if (result == FWUP_SAFE && memory_lock_attempted && FWUP_MUNLOCKALL() != 0)
		fprintf(stderr, "Firmware upgrade writer: prewrite memory unlock warning\n");
	if (result) fwup_error(message, result);
	return result;
}
#endif
