/* Fixed-board lifetime protection. No allocation, callback, MMIO or wait
 * under lifetime_lock. Probe admission and ancestor removal claims share
 * this lock; a read-only preflight would leave a check-to-use window.
 */
#include <linux/device.h>
#include <linux/device_lifetime.h>
#include <linux/errno.h>
#include <linux/export.h>
#include <linux/module.h>
#include <linux/spinlock.h>

#define LIFETIME_HELD       1U
#define LIFETIME_REMOVING   2U
#define LIFETIME_DETACHING  4U
#define LIFETIME_PROBING    8U
#define LIFETIME_UNCERTAIN 16U
#define LIFETIME_DEPTH     32

static DEFINE_RAW_SPINLOCK(lifetime_lock);

/* Caller holds lifetime_lock. drv == NULL retains a dependency without
 * inventing a driver binding (PCI bus objects are not endpoint ancestors).
 */
static int lifetime_hold(struct device *dev, struct device_driver *drv)
{
	struct device *p;
	struct device_driver *pins[LIFETIME_DEPTH + 1];
	unsigned int depth = 0, count = 0, i;

	for (p = dev; p; p = p->parent) {
		if (++depth > LIFETIME_DEPTH ||
		    (p->lifetime_flags & (LIFETIME_REMOVING | LIFETIME_DETACHING)) ||
		    (p->lifetime_driver && p->lifetime_driver->lifetime_unregistering))
			return -EBUSY;
	}
	/* Pin each distinct driver transactionally before retaining its device. */
	for (p = dev; p; p = p->parent) {
		struct device_driver *owner = p == dev && drv ? drv : p->lifetime_driver;

		if (!owner || owner->lifetime_pinned)
			continue;
		for (i = 0; i < count; i++)
			if (pins[i] == owner)
				break;
		if (i < count)
			continue;
		if (!try_module_get(owner->owner)) {
			while (count)
				module_put(pins[--count]->owner);
			return -EBUSY;
		}
		pins[count++] = owner;
	}
	for (i = 0; i < count; i++)
		pins[i]->lifetime_pinned = true;
	for (p = dev; p; p = p->parent) {
		if (!(p->lifetime_flags & LIFETIME_HELD)) {
			get_device(p);
			p->lifetime_flags |= LIFETIME_HELD;
		}
	}
	return 0;
}

int device_lifetime_probe_begin(struct device *dev, struct device_driver *drv)
{
	struct device *p;
	unsigned int depth = 0;
	unsigned long flags;
	int ret = -EBUSY;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	if (drv->lifetime_unregistering ||
	    (dev->lifetime_flags & LIFETIME_UNCERTAIN) ||
	    ((dev->lifetime_flags & LIFETIME_HELD) &&
	     dev->lifetime_driver && dev->lifetime_driver != drv))
		goto out;
	for (p = dev; p; p = p->parent) {
		if (++depth > LIFETIME_DEPTH ||
		    (p->lifetime_flags & (LIFETIME_REMOVING | LIFETIME_DETACHING)) ||
		    (p->lifetime_driver && p->lifetime_driver->lifetime_unregistering))
			goto out;
	}
	if (drv->no_forced_unbind || (dev->lifetime_flags & LIFETIME_HELD)) {
		ret = lifetime_hold(dev, drv);
		if (ret)
			goto out;
	}
	dev->lifetime_driver = drv;
	dev->lifetime_flags |= LIFETIME_PROBING;
	ret = 0;
out:
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
	return ret;
}

int device_lifetime_depend(struct device *dev, struct device *dependency)
{
	unsigned long flags;
	int ret = 0;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	if (dev->lifetime_flags & LIFETIME_HELD)
		ret = lifetime_hold(dependency, NULL);
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
	return ret;
}

void device_lifetime_probe_end(struct device *dev)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	dev->lifetime_flags &= ~LIFETIME_PROBING;
	if (!(dev->lifetime_flags & LIFETIME_HELD) && !dev->driver)
		dev->lifetime_driver = NULL;
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
}

void device_lifetime_quarantine(struct device *dev)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	dev->lifetime_flags |= LIFETIME_UNCERTAIN;
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
}
EXPORT_SYMBOL(device_lifetime_quarantine);

bool device_lifetime_quarantined(struct device *dev)
{
	return READ_ONCE(dev->lifetime_flags) & LIFETIME_UNCERTAIN;
}

bool device_lifetime_remove_begin(struct device *dev)
{
	unsigned long flags;
	bool allowed;

	if (!dev)
		return true;
	raw_spin_lock_irqsave(&lifetime_lock, flags);
	allowed = !(dev->lifetime_flags & LIFETIME_HELD);
	if (allowed)
		dev->lifetime_flags |= LIFETIME_REMOVING;
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
	return allowed;
}
EXPORT_SYMBOL(device_lifetime_remove_begin);

bool device_lifetime_detach_begin(struct device *dev)
{
	unsigned long flags;
	bool allowed;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	allowed = !(dev->lifetime_flags & (LIFETIME_HELD | LIFETIME_DETACHING));
	if (allowed)
		dev->lifetime_flags |= LIFETIME_DETACHING;
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
	return allowed;
}

void device_lifetime_detach_end(struct device *dev)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	dev->lifetime_flags &= ~LIFETIME_DETACHING;
	if (!dev->driver)
		dev->lifetime_driver = NULL;
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
}

bool device_lifetime_driver_remove(struct device_driver *drv)
{
	unsigned long flags;
	bool allowed;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	allowed = !drv->lifetime_pinned;
	if (allowed)
		drv->lifetime_unregistering = true;
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
	return allowed;
}
EXPORT_SYMBOL(device_lifetime_driver_remove);

/* driver_register already excludes a registered duplicate of this driver. */
void device_lifetime_driver_start(struct device_driver *drv)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	if (!drv->lifetime_pinned)
		drv->lifetime_unregistering = false;
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
}

bool device_lifetime_devres_allowed(struct device *dev)
{
	unsigned long flags;
	bool allowed;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	allowed = !(dev->lifetime_flags & LIFETIME_HELD) ||
		((dev->lifetime_flags & LIFETIME_PROBING) &&
		 !(dev->lifetime_flags & LIFETIME_UNCERTAIN));
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
	return allowed;
}

int device_lifetime_add(struct device *dev)
{
	struct device *p;
	unsigned long flags;
	int ret = 0;

	raw_spin_lock_irqsave(&lifetime_lock, flags);
	for (p = dev; p; p = p->parent)
		if (p->lifetime_flags & (LIFETIME_REMOVING | LIFETIME_DETACHING)) {
			ret = -EBUSY;
			break;
		}
	raw_spin_unlock_irqrestore(&lifetime_lock, flags);
	return ret;
}
