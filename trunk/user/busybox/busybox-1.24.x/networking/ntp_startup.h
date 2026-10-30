/* Bound startup before daemonization, including libc DNS and config reads.
 * The normal -q network timer starts separately once initialization is done.
 * This is a process deadline, not a guarantee against uninterruptible I/O. */
#ifndef NTP_STARTUP_H
#define NTP_STARTUP_H

#include <signal.h>
#include <string.h>
#include <unistd.h>

#define NTP_STARTUP_TIMEOUT 10

static int ntp_startup_budget_begin(void)
{
	struct sigaction action;
	sigset_t signals;

	/* record_signo only sets a flag: a blocked resolver would not inspect it.
	 * Use the default terminating disposition until startup has completed,
	 * including when the applet inherited an ignored or blocked SIGALRM. */
	memset(&action, 0, sizeof(action));
	action.sa_handler = SIG_DFL;
	if (sigemptyset(&action.sa_mask) != 0 ||
	    sigaction(SIGALRM, &action, NULL) != 0)
		return -1;
	if (sigemptyset(&signals) != 0 || sigaddset(&signals, SIGALRM) != 0 ||
	    sigprocmask(SIG_UNBLOCK, &signals, NULL) != 0)
		return -1;
	alarm(NTP_STARTUP_TIMEOUT);
	return 0;
}

static void ntp_startup_budget_end(void)
{
	alarm(0);
}

#endif
