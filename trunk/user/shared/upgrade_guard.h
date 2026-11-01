/* Cooperative admission for supported management mutations and upgrades.
 * The marker is an inter-process guard; PID1's signal path must use its own
 * sig_atomic_t latch instead of doing filesystem I/O from a signal handler.
 * Shared action leases cover synchronous side effects already admitted when
 * an upgrade asks for its exclusive lease. This is not a sandbox for root or
 * arbitrary background work launched by a user hook. */
#ifndef K2P_UPGRADE_GUARD_H
#define K2P_UPGRADE_GUARD_H
#include <errno.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef UPGRADE_GUARD_PRIVATE
#define UPGRADE_GUARD_PRIVATE "/var/private"
#endif
#ifndef UPGRADE_GUARD_MARKER
#define UPGRADE_GUARD_MARKER "firmware-upgrade-inhibit"
#endif
#ifndef UPGRADE_GUARD_LOCK
#define UPGRADE_GUARD_LOCK "firmware-action.lock"
#endif
#ifndef UPGRADE_GUARD_OWNER
#define UPGRADE_GUARD_OWNER ((uid_t)0)
#endif

static inline int upgrade_guard_directory(void)
{
	struct stat st;
	int fd = open(UPGRADE_GUARD_PRIVATE,
		O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
	if (fd < 0)
		return -1;
	if (fstat(fd, &st) != 0) {
		int error = errno;
		close(fd);
		errno = error;
		return -1;
	}
	if (!S_ISDIR(st.st_mode) || st.st_uid != UPGRADE_GUARD_OWNER ||
	    (st.st_mode & 07777) != 0700) {
		close(fd);
		errno = EACCES;
		return -1;
	}
	return fd;
}

/* Preserve caller errno. Missing early-boot directory/marker is idle; any
 * other unsafe/unavailable marker state is not permission to mutate. */
static inline int upgrade_actions_blocked(void)
{
	struct stat st;
	int saved = errno, fd, result;
	fd = upgrade_guard_directory();
	if (fd < 0)
		result = errno != ENOENT;
	else {
		result = fstatat(fd, UPGRADE_GUARD_MARKER, &st, AT_SYMLINK_NOFOLLOW);
		result = result == 0 || errno != ENOENT;
		if (close(fd) != 0)
			result = 1;
	}
	errno = saved;
	return result;
}

static inline void upgrade_action_leave(int fd)
{
	int saved = errno;
	if (fd >= 0)
		close(fd);
	errno = saved;
}

static inline int upgrade_guard_enter(int operation)
{
	struct stat st;
	int parent, fd, error;
	if (upgrade_actions_blocked()) {
		errno = EBUSY;
		return -1;
	}
	parent = upgrade_guard_directory();
	if (parent < 0)
		return -1;
	fd = openat(parent, UPGRADE_GUARD_LOCK,
		O_RDWR | O_CREAT | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
	error = errno;
	if (close(parent) != 0) {
		error = errno;
		upgrade_action_leave(fd);
		errno = error;
		return -1;
	}
	if (fd < 0) {
		errno = error;
		return -1;
	}
	if (fstat(fd, &st) != 0) {
		error = errno;
		upgrade_action_leave(fd);
		errno = error;
		return -1;
	}
	if (!S_ISREG(st.st_mode) || st.st_uid != UPGRADE_GUARD_OWNER ||
	    st.st_nlink != 1 || (st.st_mode & 07777) != 0600) {
		upgrade_action_leave(fd);
		errno = EACCES;
		return -1;
	}
	if (flock(fd, operation | LOCK_NB) != 0) {
		error = errno;
		upgrade_action_leave(fd);
		errno = error;
		return -1;
	}
	/* The other actor can create a marker between our first check and flock.
	 * Its old exclusive lease must be released before this one can be acquired;
	 * the second check prevents admitting an action into an unresolved state. */
	if (upgrade_actions_blocked()) {
		upgrade_action_leave(fd);
		errno = EBUSY;
		return -1;
	}
	return fd;
}

static inline int upgrade_action_enter(void)
{
	return upgrade_guard_enter(LOCK_SH);
}

static inline int upgrade_transaction_enter(void)
{
	return upgrade_guard_enter(LOCK_EX);
}
#endif
