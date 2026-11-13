/*
 * K2P terminal reset ownership. The lock orders admission, failure
 * publication, retirement and reset authority. It never covers driver
 * callbacks, MMIO, waits or allocation. The restart path publishes the
 * sealed phase with release ordering. Only its task can consume it.
 */
#include <linux/errno.h>
#include <linux/export.h>
#include <linux/interrupt.h>
#include <linux/kernel.h>
#include <linux/reboot.h>
#include <linux/reboot_guard.h>
#include <linux/sched.h>
#include <linux/spinlock.h>

#define REBOOT_GUARD_SLOTS 32

enum reboot_guard_phase {
	GUARD_RUNNING,
	GUARD_DRAINING,
	GUARD_SEALED,
};

static DEFINE_RAW_SPINLOCK(guard_lock);
static enum reboot_guard_phase guard_phase;
static struct task_struct *guard_coordinator;
static bool guard_restart;
static unsigned int guard_consumed;
static u32 guard_generation;
static u32 guard_slots[REBOOT_GUARD_SLOTS];
static enum reboot_guard_kind guard_kinds[REBOOT_GUARD_SLOTS];
static unsigned int guard_active;

static bool guard_owns_slot(const struct reboot_guard *guard)
{
	return guard->generation && guard->slot < REBOOT_GUARD_SLOTS &&
		guard_slots[guard->slot] == guard->generation;
}

static int guard_acquire(struct reboot_guard *guard, enum reboot_guard_kind kind)
{
	unsigned int slot;

	if (guard->generation)
		return -EBUSY;
	for (slot = 0; slot < REBOOT_GUARD_SLOTS; slot++)
		if (!guard_slots[slot])
			break;
	if (slot == REBOOT_GUARD_SLOTS || guard_generation == U32_MAX)
		return -ENOSPC;
	guard->slot = slot;
	guard->generation = ++guard_generation;
	guard_slots[slot] = guard->generation;
	guard_kinds[slot] = kind;
	guard_active++;
	return 0;
}

int reboot_guard_begin(struct reboot_guard *guard, enum reboot_guard_kind kind)
{
	unsigned long flags;
	int ret = -ESHUTDOWN;

	raw_spin_lock_irqsave(&guard_lock, flags);
	if (guard_phase == GUARD_RUNNING &&
	    (kind == REBOOT_GUARD_RUNTIME || kind == REBOOT_GUARD_FLASH_DEVICE))
		ret = guard_acquire(guard, kind);
	raw_spin_unlock_irqrestore(&guard_lock, flags);
	return ret;
}
EXPORT_SYMBOL(reboot_guard_begin);

/* The flash mutex serializes the lifetime owner's retirement and this
 * admission. Flash remains usable for persistence until its own shutdown.
 */
int reboot_guard_flash_begin(struct reboot_guard *guard,
			     const struct reboot_guard *device)
{
	unsigned long flags;
	int ret = -ESHUTDOWN;

	raw_spin_lock_irqsave(&guard_lock, flags);
	if (guard_phase < GUARD_SEALED && guard_owns_slot(device) &&
	    guard_kinds[device->slot] == REBOOT_GUARD_FLASH_DEVICE)
		ret = guard_acquire(guard, REBOOT_GUARD_FLASH_IO);
	raw_spin_unlock_irqrestore(&guard_lock, flags);
	return ret;
}
EXPORT_SYMBOL_GPL(reboot_guard_flash_begin);

bool reboot_guard_admit(const struct reboot_guard *guard)
{
	unsigned long flags;
	bool allowed;

	raw_spin_lock_irqsave(&guard_lock, flags);
	allowed = guard_phase == GUARD_RUNNING && guard_owns_slot(guard);
	raw_spin_unlock_irqrestore(&guard_lock, flags);
	return allowed;
}
EXPORT_SYMBOL(reboot_guard_admit);

void reboot_guard_finish(struct reboot_guard *guard)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&guard_lock, flags);
	if (guard_owns_slot(guard)) {
		guard_slots[guard->slot] = 0;
		guard->generation = 0;
		guard_active--;
	} else {
		reboot_dma_failure_report(REBOOT_DMA_UNKNOWN);
	}
	raw_spin_unlock_irqrestore(&guard_lock, flags);
}
EXPORT_SYMBOL(reboot_guard_finish);

/* Unknown completion retains the slot. The same lock orders the failure
 * against any later legitimate completion and against sealing.
 */
void reboot_guard_fail(const struct reboot_guard *guard, unsigned int reason)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&guard_lock, flags);
	reboot_dma_failure_report(reason |
		(guard_owns_slot(guard) ? 0 : REBOOT_DMA_UNKNOWN));
	raw_spin_unlock_irqrestore(&guard_lock, flags);
}
EXPORT_SYMBOL(reboot_guard_fail);

bool reboot_guard_prepare(bool restart)
{
	unsigned long flags;
	bool first;

	raw_spin_lock_irqsave(&guard_lock, flags);
	first = guard_phase == GUARD_RUNNING;
	if (first) {
		guard_coordinator = current;
		guard_restart = restart;
		guard_phase = GUARD_DRAINING;
	}
	raw_spin_unlock_irqrestore(&guard_lock, flags);
	return first;
}

bool reboot_guard_drained(void)
{
	unsigned long flags;
	bool drained;

	raw_spin_lock_irqsave(&guard_lock, flags);
	drained = !guard_active;
	raw_spin_unlock_irqrestore(&guard_lock, flags);
	return drained;
}

bool reboot_guard_seal(void)
{
	unsigned long flags;
	bool allowed;

	raw_spin_lock_irqsave(&guard_lock, flags);
	allowed = guard_phase == GUARD_DRAINING && guard_restart &&
		guard_coordinator == current && !guard_active &&
		!reboot_dma_failures();
	if (allowed)
		smp_store_release(&guard_phase, GUARD_SEALED);
	raw_spin_unlock_irqrestore(&guard_lock, flags);
	return allowed;
}

/* The board calls with local IRQs disabled. A nested IRQ or panic path
 * cannot borrow the interrupted task's authority or wait on this lock.
 */
bool reboot_guard_consume(void)
{
	if (in_interrupt() || smp_load_acquire(&guard_phase) != GUARD_SEALED ||
	    guard_coordinator != current || reboot_dma_failures())
		return false;
	return cmpxchg(&guard_consumed, 0, 1) == 0;
}

void __noreturn reboot_guard_park(bool may_sleep)
{
	if (may_sleep)
		pr_emerg("K2P reset blocked: device ownership or shutdown failure (%#x)\n",
			 reboot_dma_failures());
	else
		local_irq_disable();
	for (;;) {
		if (may_sleep)
			schedule_timeout_uninterruptible(MAX_SCHEDULE_TIMEOUT);
		else
			cpu_relax();
	}
}
