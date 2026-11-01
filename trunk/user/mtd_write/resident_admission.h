/* Dedicated static RAM upgrade admission. No production environment overrides. */
#ifndef K2P_RESIDENT_ADMISSION_H
#define K2P_RESIDENT_ADMISSION_H
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/file.h>
#ifdef __linux__
#include <sys/vfs.h>
#else
#include <sys/mount.h>
#endif
#include <fcntl.h>
#include <limits.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

#ifndef FWUP_RESIDENT_PRIVATE
#define FWUP_RESIDENT_PRIVATE "/var/private"
#endif
#ifndef FWUP_RESIDENT_OWNER
#define FWUP_RESIDENT_OWNER ((uid_t)0)
#endif
#ifndef FWUP_ADMISSION_PPID
#define FWUP_ADMISSION_PPID getppid
#endif
#ifndef FWUP_ADMISSION_STATFS
#define FWUP_ADMISSION_STATFS fstatfs
#endif
#ifndef FWUP_ADMISSION_READLINK
#define FWUP_ADMISSION_READLINK readlink
#endif
#ifndef FWUP_ADMISSION_EXE_OPEN
#define FWUP_ADMISSION_EXE_OPEN() open("/proc/self/exe", O_RDONLY | O_CLOEXEC)
#endif
#define FWUP_TMPFS_MAGIC 0x01021994UL

static int fwup_resident_tmpfs(int fd)
{
	struct statfs fs;
	return FWUP_ADMISSION_STATFS(fd, &fs) == 0 &&
		(unsigned long)fs.f_type == FWUP_TMPFS_MAGIC;
}

static int fwup_resident_same(const struct stat *a, const struct stat *b)
{
	return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
		a->st_mode == b->st_mode && a->st_uid == b->st_uid &&
		a->st_nlink == b->st_nlink && a->st_size == b->st_size;
}

static int fwup_resident_regular(const struct stat *st, mode_t mode)
{
	return S_ISREG(st->st_mode) && st->st_uid == FWUP_RESIDENT_OWNER &&
		st->st_nlink == 1 && (st->st_mode & 07777) == mode;
}

/* Walk literal components; a root-owned sticky tmpfs ancestor is permitted. */
static int fwup_resident_directory(const char *path)
{
	char copy[PATH_MAX], *part, *next;
	struct stat st;
	int fd, child;
	if (!path || path[0] != '/' || strlen(path) >= sizeof(copy))
		return -1;
	strcpy(copy, path);
	fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	part = copy + 1;
	while (*part) {
		next = strchr(part, '/');
		if (next)
			*next = 0;
		if (!*part || !strcmp(part, ".") || !strcmp(part, "..")) {
			close(fd);
			return -1;
		}
		child = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
		if (close(fd) != 0) {
			if (child >= 0)
				close(child);
			return -1;
		}
		if (child < 0)
			return -1;
		if (fstat(child, &st) != 0 || !S_ISDIR(st.st_mode) ||
		    (st.st_uid != 0 && st.st_uid != FWUP_RESIDENT_OWNER) ||
		    ((st.st_mode & 022) && !(st.st_mode & S_ISVTX))) {
			close(child);
			return -1;
		}
		fd = child;
		if (!next)
			break;
		part = next + 1;
		if (!*part) {
			close(fd);
			return -1;
		}
	}
	return fd;
}

static int fwup_resident_split(const char *path, char *parent, char *leaf, size_t cap)
{
	const char *slash, *p;
	size_t n;
	if (!path || path[0] != '/' || strlen(path) >= PATH_MAX)
		return -1;
	for (p = path; *p; p++)
		if ((unsigned char)*p < 32 || (unsigned char)*p == 127)
			return -1;
	slash = strrchr(path, '/');
	if (!slash || slash == path || !slash[1] || strlen(slash + 1) >= cap ||
	    !strcmp(slash + 1, ".") || !strcmp(slash + 1, ".."))
		return -1;
	n = (size_t)(slash - path);
	memcpy(parent, path, n);
	parent[n] = 0;
	strcpy(leaf, slash + 1);
	return 0;
}

/* FD3 is the PID1 transaction's inherited open-file-description EX lease.
 * Test shims are compile-time only; the shipped binary always uses real syscalls. */
static int fwup_resident_admission(int lease, const char *status)
{
	char parent[PATH_MAX], leaf[128], executable[PATH_MAX];
	char exe_parent[PATH_MAX], exe_leaf[128];
	const char *attempt;
	struct stat lock_st, path_st, st, executable_st;
	int private_fd = -1, probe = -1, attempt_fd = -1, exe = -1, named_exe = -1;
	int marker = -1, result = -1, saved;
	ssize_t count;
	size_t prefix = strlen(FWUP_RESIDENT_PRIVATE);
	if (lease != 3 || FWUP_ADMISSION_PPID() != 1 ||
	    fwup_resident_split(status, parent, leaf, sizeof(leaf)) != 0 ||
	    strcmp(leaf, "status") || strncmp(parent, FWUP_RESIDENT_PRIVATE, prefix) ||
	    parent[prefix] != '/')
		return -1;
	attempt = parent + prefix + 1;
	if (strncmp(attempt, "fwupgrade.", 10) || strlen(attempt) != 16 || strchr(attempt, '/'))
		return -1;
	for (count = 10; count < 16; count++)
		if (!((attempt[count] >= 'a' && attempt[count] <= 'z') ||
		      (attempt[count] >= 'A' && attempt[count] <= 'Z') ||
		      (attempt[count] >= '0' && attempt[count] <= '9')))
			return -1;
	private_fd = fwup_resident_directory(FWUP_RESIDENT_PRIVATE);
	if (private_fd < 0 || fstat(private_fd, &st) != 0 ||
	    st.st_uid != FWUP_RESIDENT_OWNER || (st.st_mode & 07777) != 0700)
		goto out;
	if (fstat(lease, &lock_st) != 0 || !fwup_resident_regular(&lock_st, 0600) ||
	    !fwup_resident_tmpfs(lease))
		goto out;
	probe = openat(private_fd, "firmware-action.lock", O_RDWR | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
	if (probe < 0 || fstat(probe, &path_st) != 0 ||
	    !fwup_resident_regular(&path_st, 0600) || !fwup_resident_same(&lock_st, &path_st))
		goto out;
	/* Never turn an unlocked inherited FD into valid admission ourselves. */
	if (flock(probe, LOCK_SH | LOCK_NB) == 0)
		goto out;
	if ((errno != EWOULDBLOCK && errno != EAGAIN) || flock(lease, LOCK_EX | LOCK_NB) != 0)
		goto out;
	marker = openat(private_fd, "firmware-upgrade-inhibit", O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
	if (marker < 0 || fstat(marker, &st) != 0 || !fwup_resident_regular(&st, 0600) || st.st_size != 0 ||
	    fstatat(private_fd, "firmware-upgrade-inhibit", &path_st, AT_SYMLINK_NOFOLLOW) != 0 ||
	    !fwup_resident_same(&st, &path_st))
		goto out;
	attempt_fd = openat(private_fd, attempt, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
	if (attempt_fd < 0 || fstat(attempt_fd, &st) != 0 ||
	    st.st_uid != FWUP_RESIDENT_OWNER || (st.st_mode & 07777) != 0700 ||
	    !fwup_resident_tmpfs(attempt_fd))
		goto out;
	exe = FWUP_ADMISSION_EXE_OPEN();
	if (exe < 0 || fstat(exe, &executable_st) != 0 ||
	    !fwup_resident_regular(&executable_st, 0700) || executable_st.st_size <= 0 ||
	    !fwup_resident_tmpfs(exe))
		goto out;
	count = FWUP_ADMISSION_READLINK("/proc/self/exe", executable, sizeof(executable) - 1);
	if (count <= 0 || (size_t)count >= sizeof(executable) - 1)
		goto out;
	executable[count] = 0;
	if (fwup_resident_split(executable, exe_parent, exe_leaf, sizeof(exe_leaf)) != 0 ||
	    strcmp(exe_parent, parent) || strcmp(exe_leaf, "writer"))
		goto out;
	named_exe = openat(attempt_fd, "writer", O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
	if (named_exe < 0 || fstat(named_exe, &st) != 0 ||
	    !fwup_resident_same(&executable_st, &st))
		goto out;
	result = 0;
out:
	saved = errno;
	if (named_exe >= 0 && close(named_exe) != 0) result = -1;
	if (exe >= 0 && close(exe) != 0) result = -1;
	if (attempt_fd >= 0 && close(attempt_fd) != 0) result = -1;
	if (marker >= 0 && close(marker) != 0) result = -1;
	if (probe >= 0 && close(probe) != 0) result = -1;
	if (private_fd >= 0 && close(private_fd) != 0) result = -1;
	errno = saved;
	return result;
}
#endif
