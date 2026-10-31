/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Default Padavan syslog file lives in shared1777 /tmp. Do not follow an
 * untrusted replacement when opening it, including after rotation/reopen.
 * Explicit other -O destinations keep BusyBox's original semantics. */
#ifndef BB_SYSLOGD_DEFAULT_LOGFILE_H
#define BB_SYSLOGD_DEFAULT_LOGFILE_H

#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef SYSLOGD_DEFAULT_PATH
#define SYSLOGD_DEFAULT_PATH "/tmp/syslog.log"
#endif
#define SYSLOGD_REJECTED_DEFAULT_FILE (-2)

static int default_logfile_owned(const struct stat *status)
{
	return S_ISREG(status->st_mode) && status->st_uid == geteuid()
		&& status->st_nlink == 1;
}

static int default_logfile_same(const struct stat *opened, const struct stat *named)
{
	return default_logfile_owned(opened) && default_logfile_owned(named)
		&& opened->st_dev == named->st_dev && opened->st_ino == named->st_ino;
}

static int default_logfile_reject(int descriptor)
{
	int saved = errno;
	if (descriptor >= 0)
		close(descriptor);
	errno = saved ? saved : EPERM;
	return SYSLOGD_REJECTED_DEFAULT_FILE;
}

static int syslogd_open_logfile(const char *path)
{
	struct stat opened, named;
	int descriptor = -1, flags, descriptor_flags, attempt;

	if (strcmp(path, SYSLOGD_DEFAULT_PATH) != 0)
		return open(path, O_WRONLY | O_CREAT | O_NOCTTY | O_APPEND | O_NONBLOCK, 0666);

	/* Inspect without opening a hostile FIFO/device. The descriptor and
	 * pathname are checked again; this initial inspection alone is not CAS.
	 * An absent name is created exclusively. At most3 racing EEXIST results
	 * are retried; hostile slot churn cannot turn this into a busy loop. */
	for (attempt = 0; attempt < 3; attempt++) {
		int create = 0;
		if (lstat(path, &named) == 0) {
			if (!default_logfile_owned(&named)) {
				errno = EPERM;
				return SYSLOGD_REJECTED_DEFAULT_FILE;
			}
		} else if (errno == ENOENT) {
			create = O_CREAT | O_EXCL;
		} else {
			return SYSLOGD_REJECTED_DEFAULT_FILE;
		}
		descriptor = open(path, O_WRONLY | O_NOCTTY | O_APPEND
				| O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC | create, 0644);
		if (descriptor >= 0)
			break;
		if (create && errno == EEXIST)
			continue;
		{
			int saved = errno;
			/* Preserve ordinary-IO fallback only when no unsafe replacement
			 * is observed. A concurrent disappearance is not an unsafe alias. */
			if (saved == ELOOP || (lstat(path, &named) == 0 && !default_logfile_owned(&named))) {
				errno = saved;
				return SYSLOGD_REJECTED_DEFAULT_FILE;
			}
			errno = saved;
			return -1;
		}
	}
	if (descriptor < 0) {
		errno = EAGAIN;
		return SYSLOGD_REJECTED_DEFAULT_FILE;
	}
	/* log_locally reserves fd1 for explicit -O -. Do not confuse an owned
	 * default file with that option when inherited stdio was closed. */
	if (descriptor <= STDERR_FILENO) {
		int higher = fcntl(descriptor, F_DUPFD_CLOEXEC, STDERR_FILENO + 1);
		if (higher < 0)
			return default_logfile_reject(descriptor);
		close(descriptor);
		descriptor = higher;
	}
	if (fstat(descriptor, &opened) != 0 || !default_logfile_owned(&opened)
	 || lstat(path, &named) != 0 || !default_logfile_same(&opened, &named))
		return default_logfile_reject(descriptor);

	/* Migrate only a verified owned, single-link default regular inode.
	 * Remove old umask0000 write exposure; never broaden0600 or alter an
	 * unknown owner/link/type. Same-UID/root mutation is outside this guard. */
	if ((opened.st_mode & 022)
	 && fchmod(descriptor, (opened.st_mode & 07777) & ~022) != 0)
		return default_logfile_reject(descriptor);
	flags = fcntl(descriptor, F_GETFL);
	descriptor_flags = fcntl(descriptor, F_GETFD);
	if (flags < 0 || !(flags & O_NONBLOCK)
	 || descriptor_flags < 0 || !(descriptor_flags & FD_CLOEXEC)
	 || fstat(descriptor, &opened) != 0 || !default_logfile_owned(&opened)
	 || (opened.st_mode & 022)
	 || lstat(path, &named) != 0 || !default_logfile_same(&opened, &named))
		return default_logfile_reject(descriptor);
	return descriptor;
}
#endif
