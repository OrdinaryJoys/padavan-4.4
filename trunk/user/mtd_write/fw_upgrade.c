/* Static, staged RAM-only dedicated upgrade entry. Never use the legacy CRT
 * return/stdio/shutdown path after firmware may have been touched. */
#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mtd/mtd-user.h>
#include "upgrade_write.h"
#include "resident_admission.h"
#include "resident_upgrade.h"

int main(int argc, char **argv, char **environment)
{
	_exit(fwup_resident_run(argc, argv, environment));
}
