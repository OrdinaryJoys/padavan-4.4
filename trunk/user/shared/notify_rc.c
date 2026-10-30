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

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <sys/types.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <limits.h>
#include <sys/stat.h>

#include "notify_rc.h"

static int
valid_event_name(const char *name)
{
	size_t i;
	if (!name || !*name || strlen(name) > NAME_MAX)
		return 0;
	for (i = 0; name[i]; i++) {
		unsigned char c = name[i];
		if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
		      (c >= '0' && c <= '9') || c == '_' || c == '-'))
			return 0;
	}
	return 1;
}

int
rc_notification_open_dir(const char *path)
{
	struct stat st;
	int fd = open(path, O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
	if (fd < 0)
		return -1;
	if (fstat(fd, &st) != 0 || st.st_uid != geteuid() ||
	    (st.st_mode & 0022) != 0) {
		close(fd);
		errno = EPERM;
		return -1;
	}
	return fd;
}

int
rc_notification_valid_marker(int fd, const char *event_name)
{
	struct stat st;
	return valid_event_name(event_name) &&
	       fstatat(fd, event_name, &st, AT_SYMLINK_NOFOLLOW) == 0 &&
	       S_ISREG(st.st_mode) && st.st_uid == geteuid() &&
	       st.st_nlink == 1 && (st.st_mode & 0022) == 0;
}

/* Existing trusted markers coalesce requests, without truncating anything. */
static int
create_marker(int fd, const char *event_name)
{
	int marker = openat(fd, event_name,
	                    O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0600);
	if (marker >= 0) {
		close(marker);
		return 1;
	}
	if (errno == EEXIST && rc_notification_valid_marker(fd, event_name))
		return 0;
	return -1;
}

static void notify_rc_internal(const char *event_name, int wait_sec)
{
	int i, pending = -1, queue = -1, created_pending = -1, created_queue = -1;
	struct stat st;
	if (!valid_event_name(event_name)) {
		errno = EINVAL;
		goto error;
	}
	pending = rc_notification_open_dir(DIR_RC_INCOMPLETE);
	queue = rc_notification_open_dir(DIR_RC_NOTIFY);
	if (pending < 0 || queue < 0)
		goto error;
	created_pending = create_marker(pending, event_name);
	if (created_pending < 0)
		goto error;
	created_queue = create_marker(queue, event_name);
	if (created_queue < 0 || kill(1, SIGUSR1) != 0)
		goto error;

	if (wait_sec > 0) {
		for (i = 0; i < wait_sec; i++) {
			if (fstatat(pending, event_name, &st, AT_SYMLINK_NOFOLLOW) != 0)
				break;
			if (!rc_notification_valid_marker(pending, event_name))
				break;
			sleep(1);
		}
	}
	close(queue);
	close(pending);
	return;
error:
	perror("notify_rc");
	if (created_queue == 1)
		unlinkat(queue, event_name, 0);
	if (created_pending == 1)
		unlinkat(pending, event_name, 0);
	if (queue >= 0)
		close(queue);
	if (pending >= 0)
		close(pending);
}

void notify_rc(const char *event_name)
{
	notify_rc_internal(event_name, 0);
}

void notify_rc_and_wait(const char *event_name, int wait_sec)
{
	notify_rc_internal(event_name, wait_sec);
}
