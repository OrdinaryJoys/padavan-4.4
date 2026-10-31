#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#ifdef __linux__
#include <sys/prctl.h>
#endif
static char fixture_proc[PATH_MAX] = "/proc";
static const char *fault = "none", *expected_script;
static pid_t owner, owned_child;
static int forks, waits, exits_seen, group_signals, after_reap, pipe_count;
static int pipe_reads[2] = { -1, -1 };
static unsigned long read_bytes[2];
static int read_error_once;
static int close_barrier[2] = { -1, -1 };
static const char close_witness[] = "CLOSE31_EIO_WITNESS\n";
static volatile sig_atomic_t signals_seen[4], reaped_direct;
static void old_signal(int sig)
{
	if (sig == SIGTERM) signals_seen[0]++;
	if (sig == SIGINT) signals_seen[1]++;
	if (sig == SIGHUP) signals_seen[2]++;
	if (sig == SIGQUIT) signals_seen[3]++;
}
static void old_reaper(int sig)
{
	int saved = errno, status;
	pid_t pid;
	(void)sig;
	while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
		if (pid == owned_child) reaped_direct++;
	}
	errno = saved;
}
static int fixture_fd_close_fault(void)
{
	return !strcmp(fault, "fd-close") || !strcmp(fault, "fd-close-pinned-exit");
}
static pid_t fixture_fork(void)
{
	pid_t pid;
	int barrier = !strcmp(fault, "fd-close");
	forks++;
	if (!strcmp(fault, "fork")) { errno = EAGAIN; return -1; }
	if (barrier)
		assert(pipe(close_barrier) == 0);
	pid = fork();
	if (pid < 0 && barrier) {
		int saved = errno;
		close(close_barrier[0]); close(close_barrier[1]);
		close_barrier[0] = close_barrier[1] = -1;
		errno = saved;
	} else if (pid == 0 && barrier) {
		char byte;
		ssize_t got;
		assert(close(close_barrier[1]) == 0);
		close_barrier[1] = -1;
		do { got = read(close_barrier[0], &byte, 1); } while (got < 0 && errno == EINTR);
		if (got != 1 || byte != 'G') _exit(125);
		assert(close(close_barrier[0]) == 0);
		close_barrier[0] = -1;
	} else if (pid > 0) {
		owned_child = pid;
		if (barrier) {
			assert(close(close_barrier[0]) == 0);
			close_barrier[0] = -1;
		} else if (!strcmp(fault, "fd-close-pinned-exit")) {
			siginfo_t info;
			char witness[sizeof(close_witness)];
			int result;
			ssize_t got;
			memset(&info, 0, sizeof(info));
			do { result = waitid(P_PID, (id_t)pid, &info, WEXITED | WNOWAIT); }
			while (result < 0 && errno == EINTR);
			assert(result == 0 && info.si_pid == pid && info.si_code == CLD_EXITED && info.si_status == 126);
			/* A real close31 witness proves this was the injected setup
			 * exit, rather than an earlier setup failure. Preserve the
			 * existing report schema and account the bytes actually read. */
			do { got = read(pipe_reads[1], witness, sizeof(witness)); }
			while (got < 0 && errno == EINTR);
			assert(got == 20 && !memcmp(witness, close_witness, 20));
			read_bytes[1] += (unsigned long)got;
		}
	}
	return pid;
}
static int fixture_setpgid(pid_t pid, pid_t group)
{
	int result = setpgid(pid, group), saved = errno;
	if (getpid() == owner && !strcmp(fault, "fd-close") && pid == owned_child) {
		/* Release only after the parent has really established the group.
		 * Closing on failure gives the child EOF; its normal setup error
		 * cannot hang this fixture beyond the outer test deadline. */
		if (result == 0) assert(write(close_barrier[1], "G", 1) == 1);
		assert(close(close_barrier[1]) == 0);
		close_barrier[1] = -1;
	}
	errno = saved;
	return result;
}
static int fixture_pipe(int pair[2])
{
	int result;
	if (!strcmp(fault, "pipe")) { errno = EMFILE; return -1; }
	result = pipe(pair);
	if (!result && pipe_count < 2) pipe_reads[pipe_count++] = pair[0];
	return result;
}
static int fixture_close(int fd)
{
	if (getpid() != owner && fixture_fd_close_fault() && fd == 31) {
		ssize_t wrote;
		do { wrote = write(STDERR_FILENO, close_witness, sizeof(close_witness) - 1); }
		while (wrote < 0 && errno == EINTR);
		assert(wrote == 20);
		errno = EIO;
		return -1;
	}
	return close(fd);
}
static ssize_t fixture_read(int fd, void *buffer, size_t size)
{
	ssize_t result;
	struct stat st;
	int i;
	if (read_error_once && fstat(fd, &st) == 0 && S_ISREG(st.st_mode)) {
		errno = read_error_once;
		read_error_once = 0;
		return -1;
	}
	result = read(fd, buffer, size);
	if (result > 0 && getpid() == owner && fstat(fd, &st) == 0 && S_ISFIFO(st.st_mode)) {
		for (i = 0; i < 2; i++) {
			if (fd == pipe_reads[i]) read_bytes[i] += (unsigned long)result;
		}
	}
	return result;
}
static int fixture_waitid(idtype_t kind, id_t pid, siginfo_t *info, int options)
{
	int result;
	waits++;
	assert(kind == P_PID && (options & WNOWAIT));
	if (!strcmp(fault, "wait-eintr") && waits == 1) { errno = EINTR; return -1; }
	if (!strcmp(fault, "wait-invalid")) { errno = EINVAL; return -1; }
	if (!strcmp(fault, "wait-lost")) {
		int status;
		kill((pid_t)pid, SIGKILL);
		while (waitpid((pid_t)pid, &status, 0) < 0 && errno == EINTR) { }
		errno = ECHILD;
		return -1;
	}
	result = waitid(kind, pid, info, options);
	if (!result && info->si_pid == (pid_t)pid) exits_seen++;
	return result;
}
static int fixture_kill(pid_t pid, int sig)
{
	if (pid < 0) {
		siginfo_t info;
		int result;
		memset(&info, 0, sizeof(info));
		result = waitid(P_PID, (id_t)-pid, &info, WEXITED | WNOHANG | WNOWAIT);
		if (result != 0 && errno == ECHILD) after_reap++;
		group_signals++;
	}
	return kill(pid, sig);
}
static int fixture_execv(const char *path, char *const arguments[])
{
	const char *audit = getenv("HOOK_EXEC_AUDIT");
	assert(!strcmp(path, "/bin/sh") && !strcmp(arguments[1], "-c") &&
	       !strcmp(arguments[2], "exec \"$0\" \"$1\"") && !strcmp(arguments[3], expected_script) &&
	       arguments[4] && !arguments[5]);
	if (audit) {
		int fd = open(audit, O_WRONLY | O_CREAT | O_APPEND, 0600);
		assert(fd >= 0 && write(fd, "E", 1) == 1 && close(fd) == 0);
	}
	return execv(path, arguments);
}
#define HOOK_RUNNER_PROC_ROOT fixture_proc
#define fork fixture_fork
#define setpgid fixture_setpgid
#define pipe fixture_pipe
#define close fixture_close
#define read fixture_read
#define waitid fixture_waitid
#define kill fixture_kill
#define execv fixture_execv
#include "hook_runner.h"
#undef fork
#undef setpgid
#undef pipe
#undef close
#undef read
#undef waitid
#undef kill
#undef execv
static int masks_equal(const sigset_t *a, const sigset_t *b)
{
	int sig;
	for (sig = 1; sig < NSIG; sig++) {
		if (sigismember(a, sig) != sigismember(b, sig)) return 0;
	}
	return 1;
}
int main(int argc, char **argv)
{
	FILE *report;
	int result, error, i, restored = 1;
	int64_t start, end;
	sigset_t before, after;
	struct sigaction action, actual, expected_child;
	const int sigs[] = { SIGTERM, SIGINT, SIGHUP, SIGQUIT };
	owner = getpid();
	if (argc == 7 && !strcmp(argv[1], "--scan")) {
		const char *read_error = getenv("HOOK_TEST_READ_ERROR");
		if (read_error) read_error_once = atoi(read_error);
		snprintf(fixture_proc, sizeof(fixture_proc), "%s", argv[2]);
		report = fopen(argv[6], "w"); assert(report);
		assert(hook_runner_now(&start) == 0);
		result = hook_runner_group((pid_t)atoi(argv[3]), (pid_t)atoi(argv[4]), start + atoi(argv[5]));
		error = errno;
		fprintf(report, "{\"result\":%d,\"error\":%d}\n", result, error);
		return fclose(report) != 0;
	}
	assert(argc == 10);
	expected_script = argv[1]; fault = argv[7]; owner = getpid();
	snprintf(fixture_proc, sizeof(fixture_proc), "%s", argv[6]);
	report = fopen(argv[8], "w"); assert(report);
#ifdef __linux__
	assert(prctl(PR_SET_CHILD_SUBREAPER, 1) == 0);
#endif
	memset(&action, 0, sizeof(action)); sigemptyset(&action.sa_mask); action.sa_handler = old_signal;
	for (i = 0; i < 4; i++) assert(sigaction(sigs[i], &action, NULL) == 0);
	action.sa_handler = !strcmp(fault, "chld-ignore") ? SIG_IGN : old_reaper;
	action.sa_flags = !strcmp(fault, "chld-nocldwait") ? SA_NOCLDWAIT : 0;
	assert(sigaction(SIGCHLD, &action, NULL) == 0);
	assert(sigaction(SIGCHLD, NULL, &expected_child) == 0);
	sigemptyset(&before); sigaddset(&before, SIGUSR2); assert(sigprocmask(SIG_SETMASK, &before, NULL) == 0);
	if (!strcmp(argv[9], "high-fd") || fixture_fd_close_fault()) {
		int fd = open("/dev/null", O_RDONLY), wanted = fixture_fd_close_fault() ? 31 : 512;
		struct rlimit limit;
		assert(fd >= 0 && fcntl(fd, F_DUPFD, wanted) == wanted && close(fd) == 0);
		assert(getrlimit(RLIMIT_NOFILE, &limit) == 0); limit.rlim_cur = 64;
		assert(setrlimit(RLIMIT_NOFILE, &limit) == 0);
	}
	if (!strcmp(argv[9], "closed-stdio")) { close(0); close(1); close(2); }
	assert(hook_runner_now(&start) == 0);
	result = shutdown_hook_run(argv[1], atoi(argv[2]), (unsigned int)atoi(argv[3]), (unsigned int)atoi(argv[4]), (unsigned int)atoi(argv[5]));
	error = errno;
	assert(hook_runner_now(&end) == 0 && sigprocmask(SIG_SETMASK, NULL, &after) == 0);
	for (i = 0; i < 4; i++) {
		assert(sigaction(sigs[i], NULL, &actual) == 0);
		if (actual.sa_handler != old_signal) restored = 0;
	}
	assert(sigaction(SIGCHLD, NULL, &actual) == 0);
	if (actual.sa_handler != expected_child.sa_handler || !!(actual.sa_flags & SA_NOCLDWAIT) != !!(expected_child.sa_flags & SA_NOCLDWAIT)) restored = 0;
	fprintf(report, "{\"status\":%d,\"error\":%d,\"timeout\":%d,\"output_limit\":%d,\"background\":%d,\"cancelled\":%d,\"elapsed_ms\":%lld,\"forks\":%d,\"waits\":%d,\"exits_seen\":%d,\"group_signals\":%d,\"signal_after_reap\":%d,\"reaped_direct_by_old_handler\":%d,\"mask_restored\":%d,\"handlers_restored\":%d,\"signals_seen\":[%d,%d,%d,%d],\"read_bytes\":[%lu,%lu],\"group_scan_backend\":\"%s\"}\n",
	        result, error, error == ETIMEDOUT, error == EFBIG, error == EBUSY, error == EINTR, (long long)(end-start), forks, waits, exits_seen, group_signals, after_reap, (int)reaped_direct, masks_equal(&before,&after), restored,
	        (int)signals_seen[0],(int)signals_seen[1],(int)signals_seen[2],(int)signals_seen[3],read_bytes[0],read_bytes[1], !strcmp(fixture_proc,"/proc")?"linux-real-proc":"portable-synthetic-proc");
	return fclose(report) != 0;
}
