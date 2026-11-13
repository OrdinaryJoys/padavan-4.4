/*
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 2 as published
 * by the Free Software Foundation.
 *
 * Copyright (C) 2008-2009 Gabor Juhos <juhosg@openwrt.org>
 * Copyright (C) 2008 Imre Kaloz <kaloz@openwrt.org>
 * Copyright (C) 2013 John Crispin <blogic@openwrt.org>
 */

#include <linux/pm.h>
#include <linux/reboot.h>
#include <linux/reboot_guard.h>
#include <linux/io.h>
#include <linux/of.h>
#include <linux/delay.h>
#include <linux/reset-controller.h>

#include <asm/reboot.h>

#include <asm/mach-ralink/ralink_regs.h>

/* Reset Control */
#define SYSC_REG_RESET_CTRL	0x034

#define RSTCTL_RESET_PCI	BIT(26)
#define RSTCTL_RESET_SYSTEM	BIT(0)

#ifdef CONFIG_K2P_RESET_GUARD
static DEFINE_RAW_SPINLOCK(ralink_reset_lock);

void ralink_reset_update(u32 clear, u32 set)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&ralink_reset_lock, flags);
	rt_sysc_m32(clear, set, SYSC_REG_RESET_CTRL);
	rt_sysc_r32(SYSC_REG_RESET_CTRL);
	raw_spin_unlock_irqrestore(&ralink_reset_lock, flags);
}
EXPORT_SYMBOL_GPL(ralink_reset_update);

static int ralink_change_device_reset(unsigned long id, bool assert)
{
	struct reboot_guard guard = { 0 };
	int ret;

	if (id < 8 || id >= 32)
		return -EINVAL;
	ret = reboot_guard_begin(&guard, REBOOT_GUARD_RUNTIME);
	if (ret)
		return ret;
	ralink_reset_update(assert ? 0 : BIT(id), assert ? BIT(id) : 0);
	reboot_guard_finish(&guard);
	return 0;
}
#endif

static int ralink_assert_device(struct reset_controller_dev *rcdev,
				unsigned long id)
{
#ifdef CONFIG_K2P_RESET_GUARD
	return ralink_change_device_reset(id, true);
#else
	u32 val;

	if (id < 8)
		return -1;

	val = rt_sysc_r32(SYSC_REG_RESET_CTRL);
	val |= BIT(id);
	rt_sysc_w32(val, SYSC_REG_RESET_CTRL);

	return 0;
#endif
}

static int ralink_deassert_device(struct reset_controller_dev *rcdev,
				  unsigned long id)
{
#ifdef CONFIG_K2P_RESET_GUARD
	return ralink_change_device_reset(id, false);
#else
	u32 val;

	if (id < 8)
		return -1;

	val = rt_sysc_r32(SYSC_REG_RESET_CTRL);
	val &= ~BIT(id);
	rt_sysc_w32(val, SYSC_REG_RESET_CTRL);

	return 0;
#endif
}

static int ralink_reset_device(struct reset_controller_dev *rcdev,
			       unsigned long id)
{
#ifdef CONFIG_K2P_RESET_GUARD
	struct reboot_guard guard = { 0 };
	int ret;

	if (id < 8 || id >= 32)
		return -EINVAL;
	ret = reboot_guard_begin(&guard, REBOOT_GUARD_RUNTIME);
	if (ret)
		return ret;
	ralink_reset_update(0, BIT(id));
	ralink_reset_update(BIT(id), 0);
	reboot_guard_finish(&guard);
#else
	ralink_assert_device(rcdev, id);
	return ralink_deassert_device(rcdev, id);
#endif
#ifdef CONFIG_K2P_RESET_GUARD
	return 0;
#endif
}

static struct reset_control_ops reset_ops = {
	.reset = ralink_reset_device,
	.assert = ralink_assert_device,
	.deassert = ralink_deassert_device,
};

static struct reset_controller_dev reset_dev = {
	.ops			= &reset_ops,
	.owner			= THIS_MODULE,
	.nr_resets		= 32,
	.of_reset_n_cells	= 1,
};

void ralink_rst_init(void)
{
	reset_dev.of_node = of_find_compatible_node(NULL, NULL,
						"ralink,rt2880-reset");
	if (!reset_dev.of_node)
		pr_err("Failed to find reset controller node");
	else
		reset_controller_register(&reset_dev);
}

static void ralink_restart(char *command)
{
	/* Stop local IRQ reporters before inspecting the sticky failure state. */
	local_irq_disable();
#ifdef CONFIG_K2P_RESET_GUARD
	if (!reboot_guard_consume())
		reboot_guard_park(false);
#else
	/* Cover direct/emergency callers and failures reported after prepare. */
	reboot_dma_failure_check(false);
#endif
	if (IS_ENABLED(CONFIG_PCI)) {
#ifdef CONFIG_K2P_RESET_GUARD
		ralink_reset_update(0, RSTCTL_RESET_PCI);
#else
		rt_sysc_m32(0, RSTCTL_RESET_PCI, SYSC_REG_RESET_CTRL);
#endif
		mdelay(50);
	}

	/* Another CPU can report while PCI reset settles. Never proceed to the
	 * system reset with a failure visible after that wait. This is a final
	 * observation, not proof that all other CPUs or DMA have stopped. */
#ifndef CONFIG_K2P_RESET_GUARD
	reboot_dma_failure_check(false);
#endif
	rt_sysc_w32(RSTCTL_RESET_SYSTEM, SYSC_REG_RESET_CTRL);
	unreachable();
}

static int __init mips_reboot_setup(void)
{
	_machine_restart = ralink_restart;

	return 0;
}

arch_initcall(mips_reboot_setup);
