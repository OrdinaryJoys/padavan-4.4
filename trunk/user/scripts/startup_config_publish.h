/* Bounded, fail-closed publication of an already validated startup config.
 * The Storage lock excludes cooperating save/restore operations.  It does not
 * turn an arbitrary root writer into a transaction participant. */
#ifndef STARTUP_CONFIG_PUBLISH_H
#define STARTUP_CONFIG_PUBLISH_H
#include <fcntl.h>
#include <limits.h>
#include <sys/file.h>
#include <sys/statvfs.h>
#include <dirent.h>

#ifndef STORAGE_OPERATION_DIR
#define STORAGE_OPERATION_DIR "/tmp/.storage_operation"
#endif
#ifndef STARTUP_CONFIG_STAGE_DIR
#define STARTUP_CONFIG_STAGE_DIR "/etc"
#endif
#ifdef STARTUP_CONFIG_TEST_UID
#define SCP_OWNER ((uid_t)(STARTUP_CONFIG_TEST_UID))
#else
#define SCP_OWNER ((uid_t)0)
#endif
#ifndef SCP_WRITE
#define SCP_WRITE write
#endif
#ifndef SCP_CLOSE
#define SCP_CLOSE close
#endif
#ifndef SCP_FSYNC
#define SCP_FSYNC fsync
#endif
#ifndef SCP_STATVFS
#define SCP_STATVFS fstatvfs
#endif
#ifndef SCP_RENAMEAT
#define SCP_RENAMEAT renameat
#endif
#ifndef SCP_LINKAT
#define SCP_LINKAT linkat
#endif
#ifndef SCP_UNLINKAT
#define SCP_UNLINKAT unlinkat
#endif
#ifndef SCP_READ
#define SCP_READ read
#endif
#ifndef SCP_FSTAT
#define SCP_FSTAT fstat
#endif
#define SCP_MAX_BYTES (2U * 1024U * 1024U)
#define SCP_RESERVE_BYTES (16U * 1024U)
#define SCP_PROTOCOL "K2P startup config publisher v1\n"

static int scp_error(const char *message)
{
	fprintf(stderr, "Startup config publish: %s\n", message);
	return 1;
}

/* Walk every component: O_NOFOLLOW on only the final parent would still
 * accept a symlink in an earlier path component. */
static int scp_directory(const char *path)
{
	char copy[PATH_MAX], *part, *next;
	int fd, child;
	struct stat st;
	if (!path || path[0] != '/' || strlen(path) >= sizeof(copy)) return -1;
	strcpy(copy, path);
	fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
	if (fd < 0) return -1;
	part = copy + 1;
	while (*part) {
		next = strchr(part, '/');
		if (next) *next = 0;
		if (!*part || !strcmp(part, ".") || !strcmp(part, "..")) { close(fd); return -1; }
		child = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
		close(fd);
		if (child < 0) return -1;
		if (SCP_FSTAT(child, &st) || (st.st_uid != 0 && st.st_uid != SCP_OWNER) ||
		    ((st.st_mode & 022) && !(st.st_mode & S_ISVTX))) { close(child); return -1; }
		fd = child;
		if (!next) break;
		part = next + 1;
		if (!*part) { close(fd); return -1; }
	}
	return fd;
}

static int scp_safe_directory(int fd, mode_t exact)
{
	struct stat st;
	return SCP_FSTAT(fd, &st) || !S_ISDIR(st.st_mode) || st.st_uid != SCP_OWNER ||
		(exact ? (st.st_mode & 07777) != exact : (st.st_mode & 022) != 0);
}

static int scp_split(const char *path, char *parent, char *leaf)
{
	const char *slash;
	size_t n;
	if (!path || path[0] != '/' || strlen(path) >= PATH_MAX) return -1;
	slash = strrchr(path, '/');
	if (!slash || !slash[1] || strlen(slash + 1) > 220 ||
	    !strcmp(slash + 1, ".") || !strcmp(slash + 1, "..")) return -1;
	n = slash - path;
	if (!n) n = 1;
	memcpy(parent, path, n); parent[n] = 0;
	strcpy(leaf, slash + 1);
	return 0;
}

static int scp_private_source(const char *path, struct stat *st)
{
	char parent[PATH_MAX], leaf[256];
	int directory, fd;
	if (scp_split(path, parent, leaf)) return -1;
	directory = scp_directory(parent);
	if (directory < 0) return -1;
	if (scp_safe_directory(directory, 0700)) { close(directory); return -1; }
	fd = openat(directory, leaf, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
	close(directory);
	if (fd < 0) return -1;
	if (SCP_FSTAT(fd, st) || !S_ISREG(st->st_mode) || st->st_uid != SCP_OWNER ||
	    st->st_nlink != 1 || (st->st_mode & 07777) != 0600 ||
	    st->st_size < 0 || (uint64_t)st->st_size > SCP_MAX_BYTES) { close(fd); return -1; }
	return fd;
}

static int scp_same_metadata(const struct stat *a, const struct stat *b)
{
	return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
		a->st_mode == b->st_mode && a->st_uid == b->st_uid && a->st_gid == b->st_gid &&
		a->st_nlink == b->st_nlink && a->st_size == b->st_size &&
		a->st_mtime == b->st_mtime && a->st_ctime == b->st_ctime;
}

static ssize_t scp_read(int fd, void *data, size_t size)
{
	ssize_t n;
	do { n = SCP_READ(fd, data, size); } while (n < 0 && errno == EINTR);
	return n;
}

static int scp_equal(int a, int b)
{
	unsigned char x[16384], y[16384];
	size_t total = 0;
	ssize_t nx, ny;
	if (lseek(a, 0, SEEK_SET) < 0 || lseek(b, 0, SEEK_SET) < 0) return -1;
	for (;;) {
		nx = scp_read(a, x, sizeof(x));
		if (nx < 0) return -1;
		ny = 0;
		while (ny < nx) {
			ssize_t n = scp_read(b, y + ny, (size_t)(nx - ny));
			if (n <= 0) return -1;
			ny += n;
		}
		if (nx && memcmp(x, y, (size_t)nx)) return -1;
		total += (size_t)nx;
		if (total > SCP_MAX_BYTES) return -1;
		if (!nx) return scp_read(b, y, 1) == 0 ? 0 : -1;
	}
}

static int scp_copy(int source, int target, off_t expected)
{
	unsigned char data[16384];
	size_t total = 0;
	ssize_t n;
	if (lseek(source, 0, SEEK_SET) < 0) return -1;
	while ((n = scp_read(source, data, sizeof(data))) > 0) {
		ssize_t done = 0;
		total += (size_t)n;
		if (total > SCP_MAX_BYTES || total > (uint64_t)expected) return -1;
		while (done < n) {
			ssize_t wrote = SCP_WRITE(target, data + done, (size_t)(n - done));
			if (wrote < 0 && errno == EINTR) continue;
			if (wrote <= 0 || wrote > n - done) return -1;
			done += wrote;
		}
	}
	return n < 0 || total != (uint64_t)expected ? -1 : 0;
}

static int scp_lock(void)
{
	char parent[PATH_MAX], leaf[256];
	struct stat st;
	int parentfd, directory, fd;
	if (scp_split(STORAGE_OPERATION_DIR, parent, leaf)) return -1;
	parentfd = scp_directory(parent);
	if (parentfd < 0) return -1;
	if (mkdirat(parentfd, leaf, 0700) && errno != EEXIST) { close(parentfd); return -1; }
	directory = openat(parentfd, leaf, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
	close(parentfd);
	if (directory < 0) return -1;
	if (scp_safe_directory(directory, 0700)) { close(directory); return -1; }
	fd = openat(directory, "lock", O_WRONLY | O_CREAT | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
	close(directory);
	if (fd < 0) return -1;
	if (SCP_FSTAT(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != SCP_OWNER ||
	    st.st_nlink != 1 || (st.st_mode & 07777) != 0600 || flock(fd, LOCK_EX | LOCK_NB)) {
		close(fd); return -1;
	}
	return fd;
}

static int scp_open_destination(int parent, const char *leaf, struct stat *st)
{
	int fd = openat(parent, leaf, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0) return -1;
	if (SCP_FSTAT(fd, st) || !S_ISREG(st->st_mode) || st->st_uid != SCP_OWNER ||
	    st->st_nlink < 1 || (st->st_mode & 022) || (st->st_mode & 07000) ||
	    st->st_size < 0 || (uint64_t)st->st_size > SCP_MAX_BYTES) { close(fd); return -1; }
	return fd;
}

static void scp_backup_name(char *out, size_t capacity, const char *leaf, unsigned int slot)
{
	if (slot) snprintf(out, capacity, "%s.before-migration.%u", leaf, slot);
	else snprintf(out, capacity, "%s.before-migration", leaf);
}

/* A failed/interrupted prior attempt may have linked the old inode already.
 * Reuse only links fully accounted for by these ten private backup slots. */
static int scp_account_links(int backup, const char *leaf, const struct stat *old,
			      char *reuse, size_t capacity)
{
	unsigned int slot, links = 0;
	struct stat st;
	char name[256];
	reuse[0] = 0;
	if (backup >= 0) {
		for (slot = 0; slot < 10; slot++) {
			scp_backup_name(name, sizeof(name), leaf, slot);
			if (fstatat(backup, name, &st, AT_SYMLINK_NOFOLLOW)) {
				if (errno != ENOENT) return -1;
				continue;
			}
			if (st.st_dev == old->st_dev && st.st_ino == old->st_ino) {
				if (!S_ISREG(st.st_mode) || st.st_uid != SCP_OWNER) return -1;
				if (!links) snprintf(reuse, capacity, "%s", name);
				links++;
			}
		}
	}
	return old->st_nlink == (nlink_t)(links + 1) ? 0 : -1;
}

static int scp_stage_name(const char *name)
{
	const char *p;
	if (strncmp(name, ".config-publish.", 16)) return 0;
	p = name + 16;
	if (*p < '0' || *p > '9') return 0;
	while (*p >= '0' && *p <= '9') p++;
	if (*p++ != '.' || *p < '0' || *p > '9') return 0;
	while (*p >= '0' && *p <= '9') p++;
	return !*p;
}

static int scp_clean_orphan(int parent, const char *name, int destination_parent,
			    const char *destination_leaf)
{
	int fd = -1, marker = -1, result = -1, have_candidate = 0, duplicate = -1;
	struct stat st, destination;
	char protocol[sizeof(SCP_PROTOCOL)];
	DIR *dir = NULL;
	struct dirent *entry;
	unsigned int members = 0;
	fd = openat(parent, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
	if (fd < 0 || scp_safe_directory(fd, 0700)) goto done;
	marker = openat(fd, "protocol", O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
	if (marker < 0 || SCP_FSTAT(marker, &st) || !S_ISREG(st.st_mode) || st.st_uid != SCP_OWNER ||
	    st.st_nlink != 1 || (st.st_mode & 07777) != 0600 ||
	    st.st_size != (off_t)(sizeof(SCP_PROTOCOL) - 1) ||
	    scp_read(marker, protocol, sizeof(protocol)) != (ssize_t)(sizeof(SCP_PROTOCOL) - 1) ||
	    memcmp(protocol, SCP_PROTOCOL, sizeof(SCP_PROTOCOL) - 1)) goto done;
	duplicate = dup(fd);
	if (duplicate < 0) goto done;
	dir = fdopendir(duplicate);
	if (!dir) goto done;
	duplicate = -1;
	errno = 0;
	while ((entry = readdir(dir))) {
		if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
		if (++members > 2) goto done;
		if (!strcmp(entry->d_name, "protocol")) continue;
		if (strcmp(entry->d_name, "candidate") ||
		    fstatat(fd, "candidate", &st, AT_SYMLINK_NOFOLLOW) || !S_ISREG(st.st_mode) ||
		    st.st_uid != SCP_OWNER || (st.st_mode & 07777) != 0600 ||
		    st.st_size < 0 || (uint64_t)st.st_size > SCP_MAX_BYTES) goto done;
		if (st.st_nlink != 1 &&
		    (st.st_nlink != 2 || fstatat(destination_parent, destination_leaf, &destination, AT_SYMLINK_NOFOLLOW) ||
		     !S_ISREG(destination.st_mode) || destination.st_dev != st.st_dev || destination.st_ino != st.st_ino ||
		     destination.st_uid != st.st_uid || destination.st_mode != st.st_mode ||
		     destination.st_size != st.st_size || destination.st_nlink != 2)) goto done;
		have_candidate = 1;
	}
	if (errno) goto done;
	if (have_candidate && unlinkat(fd, "candidate", 0)) goto done;
	if (unlinkat(fd, "protocol", 0) || unlinkat(parent, name, AT_REMOVEDIR)) goto done;
	result = 0;
done:
	if (dir) closedir(dir);
	if (duplicate >= 0) close(duplicate);
	if (marker >= 0) close(marker);
	if (fd >= 0) close(fd);
	return result;
}

static int scp_recover_stages(int parent, int destination_parent, const char *destination_leaf)
{
	int duplicate = dup(parent);
	DIR *dir;
	struct dirent *entry;
	unsigned int seen = 0, retained = 0;
	if (duplicate < 0) return -1;
	dir = fdopendir(duplicate);
	if (!dir) { close(duplicate); return -1; }
	errno = 0;
	while ((entry = readdir(dir))) {
		if (++seen > 4096) { closedir(dir); return -1; }
		if (!scp_stage_name(entry->d_name)) continue;
		if (scp_clean_orphan(parent, entry->d_name, destination_parent, destination_leaf)) {
			fprintf(stderr, "Startup config publish: retained unrecognized local staging directory: %s\n", entry->d_name);
			if (++retained >= 20) { closedir(dir); return -1; }
		}
		errno = 0;
	}
	if (errno) { closedir(dir); return -1; }
	closedir(dir);
	return 0;
}

/* Return 0 only after commit and cleanup.  Return 1 means no publication;
 * return 2 explicitly means committed, with a sync/cleanup warning. */
static int startup_config_publish(const char *candidate, const char *original,
				  const char *destination)
{
	char parent_path[PATH_MAX], leaf[256], stage_name[80] = {0};
	char backup_name[256] = {0}, reuse_name[256] = {0}, backup_path[PATH_MAX];
	struct stat candidate_st, original_st, old_st, now, stage_st, parent_st;
	struct statvfs space;
	int source = -1, snapshot = -1, old = -1, parent = -1, backup = -1;
	int stage_parent = -1, stage = -1, local = -1, lock = -1, marker = -1;
	int exists = strcmp(original, "-") != 0, result = 1, committed = 0;
	unsigned int attempt;
	const char *reason = "unsafe publication input";
	if (geteuid() != SCP_OWNER) return scp_error("root privilege required");
	if (scp_split(destination, parent_path, leaf)) goto done;
	lock = scp_lock();
	if (lock < 0) { reason = "Storage operation lock unsafe or busy"; goto done; }
	parent = scp_directory(parent_path);
	if (parent < 0 || scp_safe_directory(parent, 0) || SCP_FSTAT(parent, &parent_st)) {
		reason = "unsafe destination parent"; goto done;
	}
	stage_parent = scp_directory(STARTUP_CONFIG_STAGE_DIR);
	if (stage_parent < 0 || scp_safe_directory(stage_parent, 0) ||
	    SCP_FSTAT(stage_parent, &now) || now.st_dev != parent_st.st_dev) {
		reason = "unsafe or cross-filesystem local staging parent"; goto done;
	}
	/* Recover a committed first-boot link before capturing the original
	 * inode/link count, so our own orphan is not mistaken for an alias. */
	if (scp_recover_stages(stage_parent, parent, leaf)) {
		reason = "too many or unreadable local staging remnants"; goto done;
	}
	source = scp_private_source(candidate, &candidate_st);
	if (source < 0) { reason = "unsafe candidate file"; goto done; }
	if (exists) {
		snapshot = scp_private_source(original, &original_st);
		old = scp_open_destination(parent, leaf, &old_st);
		if (snapshot < 0 || old < 0 || scp_equal(snapshot, old)) {
			reason = "original snapshot does not match safe destination"; goto done;
		}
		backup = openat(parent, ".config-backups", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
		if ((backup < 0 && errno != ENOENT) || (backup >= 0 && scp_safe_directory(backup, 0700)) ||
		    scp_account_links(backup, leaf, &old_st, reuse_name, sizeof(reuse_name))) {
			reason = "unsafe backup directory or unaccounted destination hardlink"; goto done;
		}
	} else if (!fstatat(parent, leaf, &now, AT_SYMLINK_NOFOLLOW) || errno != ENOENT) {
		reason = "first-boot destination already exists"; goto done;
	}
	if (SCP_STATVFS(stage_parent, &space) || !space.f_frsize ||
	    (uint64_t)space.f_bavail > UINT64_MAX / (uint64_t)space.f_frsize ||
	    (uint64_t)space.f_bavail * (uint64_t)space.f_frsize <
		(uint64_t)candidate_st.st_size + SCP_RESERVE_BYTES ||
	    (space.f_favail != (fsfilcnt_t)-1 && space.f_favail < 4)) {
		reason = "insufficient local staging space"; goto done;
	}
	for (attempt = 0; attempt < 20; attempt++) {
		snprintf(stage_name, sizeof(stage_name), ".config-publish.%ld.%u", (long)getpid(), attempt);
		if (!mkdirat(stage_parent, stage_name, 0700)) break;
		if (errno != EEXIST) { stage_name[0] = 0; reason = "cannot reserve local staging directory"; goto done; }
	}
	if (attempt == 20) { stage_name[0] = 0; reason = "local staging slots occupied"; goto done; }
	stage = openat(stage_parent, stage_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
	if (stage < 0 || scp_safe_directory(stage, 0700)) { reason = "unsafe local staging directory"; goto done; }
	marker = openat(stage, "protocol", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
	if (marker < 0 || fchmod(marker, 0600) ||
	    write(marker, SCP_PROTOCOL, sizeof(SCP_PROTOCOL) - 1) != (ssize_t)(sizeof(SCP_PROTOCOL) - 1) ||
	    fsync(marker)) { reason = "cannot mark private local staging directory"; goto done; }
	if (close(marker)) { marker = -1; reason = "cannot close local staging marker"; goto done; }
	marker = -1;
	local = openat(stage, "candidate", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
	if (local < 0 || fchmod(local, 0600) || scp_copy(source, local, candidate_st.st_size) ||
	    SCP_FSTAT(local, &stage_st) || !S_ISREG(stage_st.st_mode) || stage_st.st_nlink != 1 ||
	    stage_st.st_uid != SCP_OWNER || (stage_st.st_mode & 07777) != 0600 ||
	    stage_st.st_size != candidate_st.st_size || SCP_FSYNC(local)) {
		reason = "cannot write and sync complete local candidate"; goto done;
	}
	if (SCP_CLOSE(local)) { local = -1; reason = "cannot close complete local candidate"; goto done; }
	local = -1;
	local = openat(stage, "candidate", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
	if (local < 0 || scp_equal(source, local) ||
	    SCP_FSTAT(source, &now) || !scp_same_metadata(&candidate_st, &now)) {
		reason = "candidate changed during publication"; goto done;
	}
	close(local); local = -1;
	if (exists) {
		if (SCP_FSTAT(snapshot, &now) || !scp_same_metadata(&original_st, &now) ||
		    scp_equal(snapshot, old) || SCP_FSTAT(old, &now) || !scp_same_metadata(&old_st, &now) ||
		    fstatat(parent, leaf, &now, AT_SYMLINK_NOFOLLOW) || !scp_same_metadata(&old_st, &now)) {
			reason = "destination changed before publication"; goto done;
		}
		if (backup < 0 && mkdirat(parent, ".config-backups", 0700) && errno != EEXIST) {
			reason = "cannot create private backup directory"; goto done;
		}
		if (backup < 0) backup = openat(parent, ".config-backups", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
		if (backup < 0 || scp_safe_directory(backup, 0700)) { reason = "unsafe private backup directory"; goto done; }
		if (reuse_name[0]) snprintf(backup_name, sizeof(backup_name), "%s", reuse_name);
		for (attempt = 0; !reuse_name[0] && attempt < 10; attempt++) {
			scp_backup_name(backup_name, sizeof(backup_name), leaf, attempt);
			/* Legacy flat backups and new private backups share ten slots. */
			if (!fstatat(parent, backup_name, &now, AT_SYMLINK_NOFOLLOW)) continue;
			if (errno != ENOENT) { reason = "cannot inspect legacy backup slot"; goto done; }
			if (!SCP_LINKAT(parent, leaf, backup, backup_name, 0)) break;
			if (errno != EEXIST) { reason = "cannot preserve pre-migration inode"; goto done; }
		}
		if (!reuse_name[0] && attempt == 10) { backup_name[0] = 0; reason = "all ten migration backup slots are occupied"; goto done; }
		if (snprintf(backup_path, sizeof(backup_path), "%s/.config-backups/%s", parent_path, backup_name) >= (int)sizeof(backup_path)) {
			reason = "backup path is too long"; goto done;
		}
		if (fstatat(backup, backup_name, &now, AT_SYMLINK_NOFOLLOW) ||
		    now.st_dev != old_st.st_dev || now.st_ino != old_st.st_ino ||
		    now.st_mode != old_st.st_mode || now.st_uid != old_st.st_uid || now.st_gid != old_st.st_gid ||
		    now.st_size != old_st.st_size || scp_equal(snapshot, old) ||
		    scp_account_links(backup, leaf, &now, reuse_name, sizeof(reuse_name)) || SCP_FSYNC(backup)) {
			reason = "cannot verify and sync pre-migration backup"; goto done;
		}
		/* Creating our hardlink changes ctime/nlink, so compare explicitly. */
		if (scp_equal(snapshot, old) || fstatat(parent, leaf, &now, AT_SYMLINK_NOFOLLOW) ||
		    now.st_dev != old_st.st_dev || now.st_ino != old_st.st_ino ||
		    now.st_mode != old_st.st_mode || now.st_uid != old_st.st_uid || now.st_gid != old_st.st_gid ||
		    now.st_size != old_st.st_size || now.st_mtime != old_st.st_mtime ||
		    SCP_RENAMEAT(stage, "candidate", parent, leaf)) {
			reason = "cannot atomically replace unchanged destination"; goto done;
		}
	} else {
		/* linkat, unlike rename, cannot overwrite a config created meanwhile. */
		if (SCP_LINKAT(stage, "candidate", parent, leaf, 0)) {
			reason = "cannot install first-boot config without replacement"; goto done;
		}
	}
	committed = 1;
	result = 0;
	if (SCP_FSYNC(parent)) { reason = "published config; destination directory sync warning"; result = 2; }
done:
	if (local >= 0) close(local);
	if (marker >= 0) close(marker);
	if (stage >= 0) {
		if (SCP_UNLINKAT(stage, "candidate", 0) && errno != ENOENT && committed) {
			reason = "published config; local candidate cleanup warning"; result = 2;
		}
		if (SCP_UNLINKAT(stage, "protocol", 0) && errno != ENOENT && committed) {
			reason = "published config; local marker cleanup warning"; result = 2;
		}
		close(stage);
	}
	if (stage_name[0] && stage_parent >= 0 && SCP_UNLINKAT(stage_parent, stage_name, AT_REMOVEDIR) && committed) {
		reason = "published config; local staging cleanup warning"; result = 2;
	}
	if (source >= 0) close(source);
	if (snapshot >= 0) close(snapshot);
	if (old >= 0) close(old);
	if (backup >= 0) close(backup);
	if (parent >= 0) close(parent);
	if (stage_parent >= 0) close(stage_parent);
	if (lock >= 0) close(lock);
	if (committed) {
		if (exists) {
			puts(backup_path);
		} else puts("-");
		if (fflush(stdout)) { reason = "published config; result output warning"; result = 2; }
		if (result) scp_error(reason);
		return result;
	}
	return scp_error(reason);
}
#endif
