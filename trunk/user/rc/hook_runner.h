#ifndef K2P_HOOK_RUNNER_H
#define K2P_HOOK_RUNNER_H
/* Bounded execution for the trusted root shutdown hook, not a sandbox.
 * A script which changes session/group or performs uninterruptible I/O can
 * escape cleanup; failure never authorizes a firmware write. */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define HOOK_RUNNER_TIMEOUT_MS 30000U
#define HOOK_RUNNER_TERM_MS 2000U
#define HOOK_RUNNER_KILL_MS 1000U
#define HOOK_RUNNER_STREAM_LIMIT (128U * 1024U)
#ifndef HOOK_RUNNER_PROC_LIMIT
#define HOOK_RUNNER_PROC_LIMIT 8192U
#endif
#ifndef HOOK_RUNNER_PROC_ROOT
#define HOOK_RUNNER_PROC_ROOT "/proc"
#endif

static volatile sig_atomic_t hook_runner_cancelled;
static const int hook_runner_cancel_signals[] = { SIGTERM, SIGINT, SIGHUP, SIGQUIT };

static void
hook_runner_cancel(int sig)
{
	if (sig == SIGTERM)
		hook_runner_cancelled |= 1;
	else if (sig == SIGINT)
		hook_runner_cancelled |= 2;
	else if (sig == SIGHUP)
		hook_runner_cancelled |= 4;
	else if (sig == SIGQUIT)
		hook_runner_cancelled |= 8;
}

static int
hook_runner_now(int64_t *value)
{
	struct timespec ts;
	if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
		return -1;
	if (ts.tv_sec < 0 || (uint64_t)ts.tv_sec > (uint64_t)INT64_MAX / 1000U ||
	    ts.tv_nsec < 0 || ts.tv_nsec >= 1000000000L) {
		errno = EOVERFLOW;
		return -1;
	}
	*value = (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
	return 0;
}

/* No process is reaped here. Holding the direct child with WNOWAIT pins its
 * PID/PGID until all group signals and inspections have finished. */
static int
hook_runner_observe(pid_t child, int *done)
{
	siginfo_t info;
	int result, retries = 0;
	memset(&info, 0, sizeof(info));
	do {
		result = waitid(P_PID, (id_t)child, &info, WEXITED | WNOHANG | WNOWAIT);
	} while (result != 0 && errno == EINTR && !hook_runner_cancelled && ++retries < 32);
	if (result != 0)
		return -1;
	*done = info.si_pid == child;
	return 0;
}

/* 0: no live descendants in the group; 1: live member; -1: not proven.
 * Ignore zombies, but never infer disappearance merely from sent SIGKILL.
 * Both the directory walk and per-process reads have explicit budgets. */
static int
hook_runner_group(pid_t group, pid_t leader, int64_t deadline)
{
	DIR *directory;
	struct dirent *entry;
	unsigned int count = 0;
	int result = 0, failure = 0;
	int64_t now;

	directory = opendir(HOOK_RUNNER_PROC_ROOT);
	if (!directory)
		return -1;
	for (;;) {
		const char *p;
		char path[64], data[512], state, *closing;
		long candidate;
		int fd, parent, pgid;
		ssize_t size;
		if (hook_runner_now(&now) != 0) {
			failure = errno;
			break;
		}
		if (now >= deadline) {
			failure = ETIMEDOUT;
			break;
		}
		errno = 0;
		entry = readdir(directory);
		if (!entry) {
			failure = errno;
			break;
		}
		if (++count > HOOK_RUNNER_PROC_LIMIT) {
			failure = EOVERFLOW;
			break;
		}
		p = entry->d_name;
		if (*p < '0' || *p > '9')
			continue;
		for (; *p >= '0' && *p <= '9'; p++) { }
		if (*p)
			continue;
		errno = 0;
		candidate = strtol(entry->d_name, NULL, 10);
		if (errno || candidate <= 0 || candidate > INT_MAX) {
			failure = EOVERFLOW;
			break;
		}
		if ((pid_t)candidate == leader)
			continue;
		if (snprintf(path, sizeof(path), "%s/stat", entry->d_name) >= (int)sizeof(path)) {
			failure = EOVERFLOW;
			break;
		}
		fd = openat(dirfd(directory), path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
		if (fd < 0) {
			if (errno == ENOENT || errno == ESRCH)
				continue;
			failure = errno;
			break;
		}
		do {
			size = read(fd, data, sizeof(data) - 1);
		} while (size < 0 && errno == EINTR && hook_runner_now(&now) == 0 && now < deadline);
		if (size <= 0) {
			int read_error = size < 0 ? errno : EIO;
			if (close(fd) != 0) {
				failure = errno;
				break;
			}
			if (read_error == ENOENT || read_error == ESRCH)
				continue;
			failure = read_error;
			break;
		}
		if (close(fd) != 0) {
			failure = errno;
			break;
		}
		data[size] = 0;
		/* comm may itself contain ')' or spaces; numeric fields follow the
		 * final closing parenthesis in a real /proc/PID/stat record. */
		closing = strrchr(data, ')');
		if (!closing || sscanf(closing + 1, " %c %d %d", &state, &parent, &pgid) != 3 || pgid < 0) {
			failure = EIO;
			break;
		}
		if ((pid_t)pgid == group && state != 'Z') {
			result = 1;
			break;
		}
	}
	if (closedir(directory) != 0 && !failure)
		failure = errno;
	if (failure) {
		errno = failure;
		return -1;
	}
	return result;
}

/* Enumerate actual descriptors, including any above a subsequently lowered
 * RLIMIT_NOFILE. Never use a guessed upper bound that can leak inherited FDs. */
static int
hook_runner_close_fds(void)
{
	DIR *directory;
	struct dirent *entry;
	unsigned int count = 0;
	int failure = 0;

	directory = opendir("/proc/self/fd");
	if (!directory)
		directory = opendir("/dev/fd");
	if (!directory)
		return -1;
	for (;;) {
		const char *p;
		long fd;
		errno = 0;
		entry = readdir(directory);
		if (!entry) {
			failure = errno;
			break;
		}
		if (++count > HOOK_RUNNER_PROC_LIMIT) {
			failure = EOVERFLOW;
			break;
		}
		p = entry->d_name;
		if (*p < '0' || *p > '9')
			continue;
		for (; *p >= '0' && *p <= '9'; p++) { }
		if (*p)
			continue;
		errno = 0;
		fd = strtol(entry->d_name, NULL, 10);
		if (errno || fd < 0 || fd > INT_MAX) {
			failure = EOVERFLOW;
			break;
		}
		if (fd <= STDERR_FILENO || fd == dirfd(directory))
			continue;
		if (close((int)fd) != 0 && errno != EBADF) {
			failure = errno;
			break;
		}
	}
	if (closedir(directory) != 0 && !failure)
		failure = errno;
	errno = failure;
	return failure ? -1 : 0;
}

/* Each stream gets one nonblocking read per turn. Neither a noisy stdout nor
 * a pipe closed by a still-running child can starve the wall-clock check. */
static int
hook_runner_drain(int pipes[2], unsigned long sizes[2], int enforce_limit)
{
	char buffer[4096];
	int i;
	for (i = 0; i < 2; i++) {
		ssize_t got;
		if (pipes[i] < 0)
			continue;
		got = read(pipes[i], buffer, sizeof(buffer));
		if (got > 0) {
			if (sizes[i] <= HOOK_RUNNER_STREAM_LIMIT)
				sizes[i] += (unsigned long)got;
			if (enforce_limit && sizes[i] > HOOK_RUNNER_STREAM_LIMIT) {
				errno = EFBIG;
				return -1;
			}
		} else if (got == 0) {
			int fd = pipes[i];
			pipes[i] = -1;
			if (close(fd) != 0)
				return -1;
		} else if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
			return -1;
		}
	}
	return 0;
}

static int
hook_runner_pause(int pipes[2], int milliseconds)
{
	struct pollfd descriptors[2];
	int i, result;
	for (i = 0; i < 2; i++) {
		descriptors[i].fd = pipes[i];
		descriptors[i].events = POLLIN | POLLHUP;
		descriptors[i].revents = 0;
	}
	result = poll(descriptors, 2, milliseconds);
	if (result < 0 && errno != EINTR)
		return -1;
	return 0;
}

/* Negative: runner/setup/deadline/cleanup failure, with errno preserved.
 * Otherwise return the original waitpid status, including child signals.
 * Failure cleanup is bounded; it does not claim rollback of hook side effects. */
static int
shutdown_hook_run(const char *script, int level, unsigned int timeout_ms,
                  unsigned int term_ms, unsigned int kill_ms)
{
	int output[2] = { -1, -1 }, error_output[2] = { -1, -1 }, pipes[2] = { -1, -1 };
	unsigned long sizes[2] = { 0, 0 };
	sigset_t blocked, previous, running_mask;
	struct sigaction old_actions[4], cancel_action, child_action;
	pid_t child = -1, waited;
	int status = -1, failure = 0, masked = 0, group = 0, owned = 0, done = 0, i;
	int installed = 0;
	sig_atomic_t cancelled = 0;
	int64_t start, now, deadline;

	if (!script || !*script || level < 0 || level > 2 || !timeout_ms ||
	    timeout_ms > HOOK_RUNNER_TIMEOUT_MS || term_ms > HOOK_RUNNER_TERM_MS || kill_ms > HOOK_RUNNER_KILL_MS) {
		errno = EINVAL;
		return -1;
	}
	if (hook_runner_now(&start) != 0)
		return -1;
	deadline = start + timeout_ms;
	if (pipe(output) != 0 || pipe(error_output) != 0) {
		failure = errno;
		goto finish;
	}
	for (i = 0; i < 2; i++) {
		int *pair = i ? error_output : output;
		if (fcntl(pair[0], F_SETFD, FD_CLOEXEC) != 0 || fcntl(pair[1], F_SETFD, FD_CLOEXEC) != 0 ||
		    fcntl(pair[0], F_SETFL, O_NONBLOCK) != 0) {
			failure = errno;
			goto finish;
		}
	}
	sigemptyset(&blocked);
	sigaddset(&blocked, SIGCHLD);
	for (i = 0; i < 4; i++)
		sigaddset(&blocked, hook_runner_cancel_signals[i]);
	if (sigprocmask(SIG_BLOCK, &blocked, &previous) != 0) {
		failure = errno;
		goto finish;
	}
	masked = 1;
	if (sigaction(SIGCHLD, NULL, &child_action) != 0) {
		failure = errno;
		goto finish;
	}
	if (child_action.sa_handler == SIG_IGN || (child_action.sa_flags & SA_NOCLDWAIT)) {
		failure = EINVAL;
		goto finish;
	}
	hook_runner_cancelled = 0;
	memset(&cancel_action, 0, sizeof(cancel_action));
	cancel_action.sa_handler = hook_runner_cancel;
	cancel_action.sa_mask = blocked;
	for (i = 0; i < 4; i++) {
		if (sigaction(hook_runner_cancel_signals[i], &cancel_action, &old_actions[i]) != 0) {
			failure = errno;
			goto finish;
		}
		installed++;
	}
	child = fork();
	if (child < 0) {
		failure = errno;
		goto finish;
	}
	if (child == 0) {
		char action[16];
		char *args[] = { "/bin/sh", "-c", "exec \"$0\" \"$1\"", (char *)script, action, NULL };
		const int signals[] = { SIGTERM, SIGQUIT, SIGINT, SIGCHLD, SIGHUP, SIGALRM, SIGPIPE, SIGUSR1, SIGUSR2 };
		struct sigaction reset;
		int nullfd;
		if (setpgid(0, 0) != 0)
			_exit(126);
		memset(&reset, 0, sizeof(reset));
		reset.sa_handler = SIG_DFL;
		sigemptyset(&reset.sa_mask);
		for (i = 0; i < (int)(sizeof(signals) / sizeof(signals[0])); i++) {
			if (sigaction(signals[i], &reset, NULL) != 0)
				_exit(126);
		}
		sigemptyset(&blocked);
		if (sigprocmask(SIG_SETMASK, &blocked, NULL) != 0)
			_exit(126);
		nullfd = open("/dev/null", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
		if (nullfd < 0 || dup2(nullfd, STDIN_FILENO) < 0 || dup2(output[1], STDOUT_FILENO) < 0 ||
		    dup2(error_output[1], STDERR_FILENO) < 0)
			_exit(126);
		/* dup2 is a no-op when source==target and then retains CLOEXEC. */
		if (fcntl(STDIN_FILENO, F_SETFD, 0) != 0 || fcntl(STDOUT_FILENO, F_SETFD, 0) != 0 ||
		    fcntl(STDERR_FILENO, F_SETFD, 0) != 0 || hook_runner_close_fds() != 0)
			_exit(126);
		snprintf(action, sizeof(action), "%d", level);
		execv(args[0], args);
		_exit(127);
	}
	owned = 1;
	if (setpgid(child, child) == 0 || getpgid(child) == child)
		group = 1;
	else {
		failure = errno ? errno : EIO;
		goto cleanup;
	}
	if (close(output[1]) != 0) {
		output[1] = -1;
		failure = errno;
		goto cleanup;
	}
	output[1] = -1;
	if (close(error_output[1]) != 0) {
		error_output[1] = -1;
		failure = errno;
		goto cleanup;
	}
	error_output[1] = -1;
	pipes[0] = output[0]; output[0] = -1;
	pipes[1] = error_output[0]; error_output[0] = -1;
	running_mask = previous;
	sigaddset(&running_mask, SIGCHLD);
	if (sigprocmask(SIG_SETMASK, &running_mask, NULL) != 0) {
		failure = errno;
		goto cleanup;
	}
	for (;;) {
		int active;
		if (hook_runner_cancelled) {
			failure = EINTR;
			goto cleanup;
		}
		if (hook_runner_now(&now) != 0) {
			failure = errno;
			goto cleanup;
		}
		if (now >= deadline) {
			failure = ETIMEDOUT;
			goto cleanup;
		}
		if (hook_runner_observe(child, &done) != 0) {
			failure = errno;
			if (failure == ECHILD)
				owned = 0;
			goto cleanup;
		}
		if (hook_runner_drain(pipes, sizes, 1) != 0) {
			failure = errno;
			goto cleanup;
		}
		if (done) {
			active = hook_runner_group(child, child, deadline);
			if (active != 0) {
				failure = active > 0 ? EBUSY : errno;
				goto cleanup;
			}
			if (pipes[0] < 0 && pipes[1] < 0)
				break;
		}
		if (hook_runner_pause(pipes, deadline - now > 50 ? 50 : (int)(deadline - now)) != 0) {
			failure = errno;
			goto cleanup;
		}
	}
	goto reap;

cleanup:
	/* The child is still owned/unreaped here. No group signal is sent after
	 * final waitpid, even if cleanup inspection failed or a child stays D. */
	if (owned) {
		int stage;
		for (stage = 0; stage < 2; stage++) {
			unsigned int budget = stage ? kill_ms : term_ms;
			int attempts = 0;
			kill(group ? -child : child, stage ? SIGKILL : SIGTERM);
			if (hook_runner_now(&now) != 0)
				continue;
			deadline = now + budget;
			while (++attempts <= 100) {
				int active;
				if (hook_runner_now(&now) != 0 || now >= deadline)
					break;
				if (hook_runner_observe(child, &done) != 0) {
					if (errno == ECHILD)
						owned = 0;
					break;
				}
				hook_runner_drain(pipes, sizes, 0);
				active = group && done ? hook_runner_group(child, child, deadline) : 1;
				if (done && active == 0 && pipes[0] < 0 && pipes[1] < 0)
					goto reap;
				hook_runner_pause(pipes, deadline - now > 50 ? 50 : (int)(deadline - now));
			}
			if (!owned)
				break;
		}
	}
reap:
	if (owned) {
		int retries = 0;
		do {
			waited = waitpid(child, &status, WNOHANG);
		} while (waited < 0 && errno == EINTR && ++retries < 32);
		if (waited != child && !failure)
			failure = waited < 0 ? errno : EBUSY;
	}
finish:
	for (i = 0; i < 2; i++) {
		if (output[i] >= 0 && close(output[i]) != 0 && !failure)
			failure = errno;
		if (error_output[i] >= 0 && close(error_output[i]) != 0 && !failure)
			failure = errno;
		if (pipes[i] >= 0 && close(pipes[i]) != 0 && !failure)
			failure = errno;
	}
	if (masked) {
		if (sigprocmask(SIG_BLOCK, &blocked, NULL) != 0 && !failure)
			failure = errno;
		cancelled = hook_runner_cancelled;
		hook_runner_cancelled = 0;
		if (cancelled && !failure)
			failure = EINTR;
		for (i = 0; i < installed; i++) {
			if (sigaction(hook_runner_cancel_signals[i], &old_actions[i], NULL) != 0 && !failure)
				failure = errno;
		}
		if (sigprocmask(SIG_SETMASK, &previous, NULL) != 0 && !failure)
			failure = errno;
		/* Honor the caller's original semantics only after owned children
		 * have been signalled/reaped and all temporary descriptors closed. */
		for (i = 0; i < 4; i++) {
			if (cancelled & (1 << i))
				kill(getpid(), hook_runner_cancel_signals[i]);
		}
	}
	errno = failure;
	return failure ? -1 : status;
}
#endif
