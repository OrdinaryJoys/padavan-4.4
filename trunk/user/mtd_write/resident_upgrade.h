/* Final post-write userspace belongs to this static RAM process, not old PID1. */
#ifndef K2P_RESIDENT_UPGRADE_H
#define K2P_RESIDENT_UPGRADE_H
#ifndef FWUP_RESIDENT_WRITE
#define FWUP_RESIDENT_WRITE firmware_upgrade_write
#endif
#ifndef FWUP_RESIDENT_REBOOT
#include <sys/syscall.h>
#include <linux/reboot.h>
#define FWUP_RESIDENT_REBOOT() syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2, LINUX_REBOOT_CMD_RESTART, 0)
#endif
static int fwup_resident_run(int argc, char **argv, char **environment)
{
	int result;
	if (argc != 6 || !argv || !argv[1] || !argv[2] || !argv[3] || !argv[4] || !argv[5] ||
	    strcmp(argv[1], "--resident-upgrade") || strcmp(argv[3], "firmware") ||
	    strcmp(argv[5], "3") || !environment || environment[0] ||
	    fwup_resident_admission(3, argv[4]) != 0)
		return FWUP_UNKNOWN;
	result = FWUP_RESIDENT_WRITE(argv[2], argv[3], argv[4]);
	if (result == 0) {
		/* Full readback was verified. Any syscall return, even zero, is a
		 * failed reset handoff: never resume normal shutdown or report SAFE. */
		(void)FWUP_RESIDENT_REBOOT();
		return FWUP_UNKNOWN;
	}
	return result == FWUP_SAFE ? FWUP_SAFE : FWUP_UNKNOWN;
}
#endif
