/*
 * Reset Controller framework
 *
 * Copyright 2013 Philipp Zabel, Pengutronix
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */
#include <linux/atomic.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/export.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/reset.h>
#include <linux/reset-controller.h>
#include <linux/slab.h>

static DEFINE_MUTEX(reset_list_mutex);
static LIST_HEAD(reset_controller_list);

/**
 * struct reset_control - a reset control
 * @rcdev: a pointer to the reset controller device
 *         this reset control belongs to
 * @list: list entry for the rcdev's reset controller list
 * @id: ID of the reset controller in the reset
 *      controller device
 * @refcnt: Number of gets of this reset_control
 * @shared: Is this a shared (1), or an exclusive (0) reset_control?
 * @deassert_cnt: Number of times this reset line has been deasserted
 * @triggered_count: Shared reset requests; after shared_busy is cleared a
 *                   positive value means the provider pulse has completed.
 * @shared_busy: Nonblocking exclusion for shared provider/count transitions.
 */
struct reset_control {
	struct reset_controller_dev *rcdev;
	struct list_head list;
	unsigned int id;
	unsigned int refcnt;
	bool shared;
	atomic_t deassert_count;
	atomic_t triggered_count;
	atomic_t shared_busy;
};

/* Do not spin or sleep behind a provider: it may itself sleep, or be called
 * from atomic context when the provider permits that. A concurrent shared
 * caller must retry rather than observe success before the provider returns.
 * cmpxchg/xchg also publish provider completion before the next owner. */
static int reset_control_try_shared(struct reset_control *rstc)
{
	if (rstc->shared && atomic_cmpxchg(&rstc->shared_busy, 0, 1))
		return -EAGAIN;

	return 0;
}

static int reset_control_shared_done(struct reset_control *rstc, int result)
{
	if (rstc->shared)
		atomic_xchg(&rstc->shared_busy, 0);

	return result;
}

/**
 * of_reset_simple_xlate - translate reset_spec to the reset line number
 * @rcdev: a pointer to the reset controller device
 * @reset_spec: reset line specifier as found in the device tree
 * @flags: a flags pointer to fill in (optional)
 *
 * This simple translation function should be used for reset controllers
 * with 1:1 mapping, where reset lines can be indexed by number without gaps.
 */
static int of_reset_simple_xlate(struct reset_controller_dev *rcdev,
			  const struct of_phandle_args *reset_spec)
{
	if (reset_spec->args[0] >= rcdev->nr_resets)
		return -EINVAL;

	return reset_spec->args[0];
}

/**
 * reset_controller_register - register a reset controller device
 * @rcdev: a pointer to the initialized reset controller device
 */
int reset_controller_register(struct reset_controller_dev *rcdev)
{
	if (!rcdev->of_xlate) {
		rcdev->of_reset_n_cells = 1;
		rcdev->of_xlate = of_reset_simple_xlate;
	}

	INIT_LIST_HEAD(&rcdev->reset_control_head);

	mutex_lock(&reset_list_mutex);
	list_add(&rcdev->list, &reset_controller_list);
	mutex_unlock(&reset_list_mutex);

	return 0;
}
EXPORT_SYMBOL_GPL(reset_controller_register);

/**
 * reset_controller_unregister - unregister a reset controller device
 * @rcdev: a pointer to the reset controller device
 */
void reset_controller_unregister(struct reset_controller_dev *rcdev)
{
	mutex_lock(&reset_list_mutex);
	list_del(&rcdev->list);
	mutex_unlock(&reset_list_mutex);
}
EXPORT_SYMBOL_GPL(reset_controller_unregister);

static void devm_reset_controller_release(struct device *dev, void *res)
{
	reset_controller_unregister(*(struct reset_controller_dev **)res);
}

/**
 * devm_reset_controller_register - resource managed reset_controller_register()
 * @dev: device that is registering this reset controller
 * @rcdev: a pointer to the initialized reset controller device
 *
 * Managed reset_controller_register(). For reset controllers registered by
 * this function, reset_controller_unregister() is automatically called on
 * driver detach. See reset_controller_register() for more information.
 */
int devm_reset_controller_register(struct device *dev,
				   struct reset_controller_dev *rcdev)
{
	struct reset_controller_dev **rcdevp;
	int ret;

	rcdevp = devres_alloc(devm_reset_controller_release, sizeof(*rcdevp),
			      GFP_KERNEL);
	if (!rcdevp)
		return -ENOMEM;

	ret = reset_controller_register(rcdev);
	if (!ret) {
		*rcdevp = rcdev;
		devres_add(dev, rcdevp);
	} else {
		devres_free(rcdevp);
	}

	return ret;
}
EXPORT_SYMBOL_GPL(devm_reset_controller_register);

/**
 * reset_control_reset - reset the controlled device
 * @rstc: reset controller
 *
 * On a shared reset line the actual reset pulse is only triggered once for the
 * lifetime of the reset_control instance: for all but the first caller this is
 * a no-op.
 * Consumers must not use reset_control_(de)assert on shared reset lines when
 * reset_control_reset has been used.
 * A shared provider operation already in progress returns -EAGAIN without
 * consuming a request. Provider failure also leaves the pulse retryable.
 *
 * If rstc is NULL it is an optional reset and the function will just
 * return 0.
 */
int reset_control_reset(struct reset_control *rstc)
{
	int ret;

	if (!rstc)
		return 0;

	if (WARN_ON(IS_ERR(rstc)))
		return -EINVAL;

	if (!rstc->rcdev->ops->reset)
		return -ENOTSUPP;

	ret = reset_control_try_shared(rstc);
	if (ret)
		return ret;

	if (rstc->shared) {
		if (WARN_ON(atomic_read(&rstc->deassert_count) != 0))
			return reset_control_shared_done(rstc, -EINVAL);

		if (WARN_ON(atomic_read(&rstc->triggered_count) < 0))
			return reset_control_shared_done(rstc, -EINVAL);

		/* Only the consumed/not-consumed distinction is functional. Keep
		 * historical positive accounting without allowing signed wrap. */
		if (atomic_read(&rstc->triggered_count) == INT_MAX)
			return reset_control_shared_done(rstc, 0);

		if (atomic_inc_return(&rstc->triggered_count) != 1)
			return reset_control_shared_done(rstc, 0);
	}

	ret = rstc->rcdev->ops->reset(rstc->rcdev, rstc->id);
	/* A successful shared pulse is consumed; only failure permits retry. */
	if (rstc->shared && ret)
		atomic_dec(&rstc->triggered_count);

	return reset_control_shared_done(rstc, ret);
}
EXPORT_SYMBOL_GPL(reset_control_reset);

/**
 * reset_control_assert - asserts the reset line
 * @rstc: reset controller
 *
 * Calling this on an exclusive reset controller guarantees that the reset
 * will be asserted. When called on a shared reset controller the line may
 * still be deasserted, as long as other users keep it so.
 *
 * For shared reset controls a driver cannot expect the hw's registers and
 * internal state to be reset, but must be prepared for this to happen.
 * Consumers must not use reset_control_reset on shared reset lines when
 * reset_control_(de)assert has been used.
 * A shared operation in progress returns -EAGAIN without releasing a
 * deassert reference. Provider failure likewise preserves that reference.
 *
 * If rstc is NULL it is an optional reset and the function will just
 * return 0.
 */
int reset_control_assert(struct reset_control *rstc)
{
	int ret;

	if (!rstc)
		return 0;

	if (WARN_ON(IS_ERR(rstc)))
		return -EINVAL;

	if (!rstc->rcdev->ops->assert)
		return -ENOTSUPP;

	ret = reset_control_try_shared(rstc);
	if (ret)
		return ret;

	if (rstc->shared) {
		if (WARN_ON(atomic_read(&rstc->triggered_count) != 0))
			return reset_control_shared_done(rstc, -EINVAL);

		if (WARN_ON(atomic_read(&rstc->deassert_count) <= 0))
			return reset_control_shared_done(rstc, -EINVAL);

		if (atomic_dec_return(&rstc->deassert_count) != 0)
			return reset_control_shared_done(rstc, 0);
	}

	ret = rstc->rcdev->ops->assert(rstc->rcdev, rstc->id);
	if (rstc->shared && ret)
		atomic_inc(&rstc->deassert_count);

	return reset_control_shared_done(rstc, ret);
}
EXPORT_SYMBOL_GPL(reset_control_assert);

/**
 * reset_control_deassert - deasserts the reset line
 * @rstc: reset controller
 *
 * After calling this function, the reset is guaranteed to be deasserted.
 * Consumers must not use reset_control_reset on shared reset lines when
 * reset_control_(de)assert has been used.
 * A shared operation in progress returns -EAGAIN without acquiring a
 * deassert reference. A failed provider call is not counted either.
 *
 * If rstc is NULL it is an optional reset and the function will just
 * return 0.
 */
int reset_control_deassert(struct reset_control *rstc)
{
	int ret;

	if (!rstc)
		return 0;

	if (WARN_ON(IS_ERR(rstc)))
		return -EINVAL;

	if (!rstc->rcdev->ops->deassert)
		return -ENOTSUPP;

	ret = reset_control_try_shared(rstc);
	if (ret)
		return ret;

	if (rstc->shared) {
		if (WARN_ON(atomic_read(&rstc->triggered_count) != 0))
			return reset_control_shared_done(rstc, -EINVAL);

		if (WARN_ON(atomic_read(&rstc->deassert_count) < 0))
			return reset_control_shared_done(rstc, -EINVAL);

		if (atomic_read(&rstc->deassert_count) == INT_MAX)
			return reset_control_shared_done(rstc, -EOVERFLOW);

		if (atomic_inc_return(&rstc->deassert_count) != 1)
			return reset_control_shared_done(rstc, 0);
	}

	ret = rstc->rcdev->ops->deassert(rstc->rcdev, rstc->id);
	if (rstc->shared && ret)
		atomic_dec(&rstc->deassert_count);

	return reset_control_shared_done(rstc, ret);
}
EXPORT_SYMBOL_GPL(reset_control_deassert);

/**
 * reset_control_status - returns a negative errno if not supported, a
 * positive value if the reset line is asserted, or zero if the reset
 * line is not asserted or if the desc is NULL (optional reset).
 * @rstc: reset controller
 */
int reset_control_status(struct reset_control *rstc)
{
	if (!rstc)
		return 0;

	if (WARN_ON(IS_ERR(rstc)))
		return -EINVAL;

	if (rstc->rcdev->ops->status)
		return rstc->rcdev->ops->status(rstc->rcdev, rstc->id);

	return -ENOTSUPP;
}
EXPORT_SYMBOL_GPL(reset_control_status);

static struct reset_control *__reset_control_get(
				struct reset_controller_dev *rcdev,
				unsigned int index, bool shared)
{
	struct reset_control *rstc;

	lockdep_assert_held(&reset_list_mutex);

	list_for_each_entry(rstc, &rcdev->reset_control_head, list) {
		if (rstc->id == index) {
			if (WARN_ON(!rstc->shared || !shared))
				return ERR_PTR(-EBUSY);

			if (rstc->refcnt == UINT_MAX)
				return ERR_PTR(-EOVERFLOW);

			rstc->refcnt++;
			return rstc;
		}
	}

	rstc = kzalloc(sizeof(*rstc), GFP_KERNEL);
	if (!rstc)
		return ERR_PTR(-ENOMEM);

	if (!try_module_get(rcdev->owner)) {
		kfree(rstc);
		return ERR_PTR(-ENODEV);
	}

	rstc->rcdev = rcdev;
	list_add(&rstc->list, &rcdev->reset_control_head);
	rstc->id = index;
	rstc->refcnt = 1;
	rstc->shared = shared;

	return rstc;
}

static void __reset_control_put(struct reset_control *rstc)
{
	lockdep_assert_held(&reset_list_mutex);

	if (--rstc->refcnt)
		return;

	module_put(rstc->rcdev->owner);

	list_del(&rstc->list);
	kfree(rstc);
}

struct reset_control *__of_reset_control_get(struct device_node *node,
				     const char *id, int index, bool shared,
				     bool optional)
{
	struct reset_control *rstc;
	struct reset_controller_dev *r, *rcdev;
	struct of_phandle_args args;
	int rstc_id;
	int ret;

	if (!node)
		return ERR_PTR(-EINVAL);

	if (id) {
		index = of_property_match_string(node,
						 "reset-names", id);
		if (index == -EILSEQ)
			return ERR_PTR(index);
		if (index < 0)
			return optional ? NULL : ERR_PTR(-ENOENT);
	}

	ret = of_parse_phandle_with_args(node, "resets", "#reset-cells",
					 index, &args);
	if (ret == -EINVAL)
		return ERR_PTR(ret);
	if (ret)
		return optional ? NULL : ERR_PTR(ret);

	mutex_lock(&reset_list_mutex);
	rcdev = NULL;
	list_for_each_entry(r, &reset_controller_list, list) {
		if (args.np == r->of_node) {
			rcdev = r;
			break;
		}
	}
	of_node_put(args.np);

	if (!rcdev) {
		mutex_unlock(&reset_list_mutex);
		return ERR_PTR(-EPROBE_DEFER);
	}

	if (WARN_ON(args.args_count != rcdev->of_reset_n_cells)) {
		mutex_unlock(&reset_list_mutex);
		return ERR_PTR(-EINVAL);
	}

	rstc_id = rcdev->of_xlate(rcdev, &args);
	if (rstc_id < 0) {
		mutex_unlock(&reset_list_mutex);
		return ERR_PTR(rstc_id);
	}

	/* reset_list_mutex also protects the rcdev's reset_control list */
	rstc = __reset_control_get(rcdev, rstc_id, shared);

	mutex_unlock(&reset_list_mutex);

	return rstc;
}
EXPORT_SYMBOL_GPL(__of_reset_control_get);

/**
 * reset_control_put - free the reset controller
 * @rstc: reset controller
 *
 * NULL optional controls and error pointers have no reference to release.
 * The consumer must finish its operations before releasing their reference.
 */

void reset_control_put(struct reset_control *rstc)
{
	if (IS_ERR_OR_NULL(rstc))
		return;

	mutex_lock(&reset_list_mutex);
	__reset_control_put(rstc);
	mutex_unlock(&reset_list_mutex);
}
EXPORT_SYMBOL_GPL(reset_control_put);

static void devm_reset_control_release(struct device *dev, void *res)
{
	reset_control_put(*(struct reset_control **)res);
}

struct reset_control *__devm_reset_control_get(struct device *dev,
				     const char *id, int index, bool shared,
				     bool optional)
{
	struct reset_control **ptr, *rstc;

	ptr = devres_alloc(devm_reset_control_release, sizeof(*ptr),
			   GFP_KERNEL);
	if (!ptr)
		return ERR_PTR(-ENOMEM);

	rstc = __of_reset_control_get(dev ? dev->of_node : NULL,
				      id, index, shared, optional);
	if (!IS_ERR_OR_NULL(rstc)) {
		*ptr = rstc;
		devres_add(dev, ptr);
	} else {
		devres_free(ptr);
	}

	return rstc;
}
EXPORT_SYMBOL_GPL(__devm_reset_control_get);

/**
 * device_reset - find reset controller associated with the device
 *                and perform reset
 * @dev: device to be reset by the controller
 *
 * Convenience wrapper for reset_control_get() and reset_control_reset().
 * This is useful for the common case of devices with single, dedicated reset
 * lines.
 */
int device_reset(struct device *dev)
{
	struct reset_control *rstc;
	int ret;

	rstc = reset_control_get(dev, NULL);
	if (IS_ERR(rstc))
		return PTR_ERR(rstc);

	ret = reset_control_reset(rstc);

	reset_control_put(rstc);

	return ret;
}
EXPORT_SYMBOL_GPL(device_reset);
