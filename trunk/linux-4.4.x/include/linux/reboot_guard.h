#ifndef _LINUX_REBOOT_GUARD_H
#define _LINUX_REBOOT_GUARD_H

#include <linux/types.h>

/* A zero-initialized handle owns nothing. Move a live handle only while
 * holding the driver's lifecycle lock or before publishing the instance.
 * The core stores numbers, never pointers to device or module storage.
 */
struct reboot_guard {
	u32 generation;
	unsigned int slot;
};

enum reboot_guard_kind {
	REBOOT_GUARD_RUNTIME,
	REBOOT_GUARD_FLASH_DEVICE,
	REBOOT_GUARD_FLASH_IO,
};

int reboot_guard_begin(struct reboot_guard *guard, enum reboot_guard_kind kind);
int reboot_guard_flash_begin(struct reboot_guard *guard,
			     const struct reboot_guard *device);
bool reboot_guard_admit(const struct reboot_guard *guard);
void reboot_guard_finish(struct reboot_guard *guard);
void reboot_guard_fail(const struct reboot_guard *guard, unsigned int reason);

bool reboot_guard_prepare(bool restart);
bool reboot_guard_drained(void);
bool reboot_guard_seal(void);
bool reboot_guard_consume(void);
void __noreturn reboot_guard_park(bool may_sleep);

#endif
