/* Copyright  2016 MediaTek Inc.
 * Author: Carlos Huang <carlos.huang@mediatek.com>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */
#include "mii_mgr.h"

/* One controller, one complete transaction, including MT7530 page selection.
 * Do not depend on jiffies advancing while local interrupts are masked. */
#define RAETH_MDIO_POLL_US 10
#define RAETH_MDIO_POLLS 1000
static DEFINE_SPINLOCK(mdio_bus_lock);
static bool mdio_detached = true;

void mii_mgr_attach(void)
{
	unsigned long flags;
	spin_lock_irqsave(&mdio_bus_lock, flags);
	mdio_detached = false;
	spin_unlock_irqrestore(&mdio_bus_lock, flags);
}

void mii_mgr_detach(void)
{
	unsigned long flags;
	/* Joining this lock retires users before MMIO/netdev ownership can end. */
	spin_lock_irqsave(&mdio_bus_lock, flags);
	mdio_detached = true;
	spin_unlock_irqrestore(&mdio_bus_lock, flags);
}

static struct END_DEVICE *raeth_mdio_lock(unsigned long *flags)
{
	spin_lock_irqsave(&mdio_bus_lock, *flags);
	if (mdio_detached || !dev_raether) {
		spin_unlock_irqrestore(&mdio_bus_lock, *flags);
		return NULL;
	}
	return netdev_priv(dev_raether);
}

static u32 raeth_mdio_wait(unsigned int *budget)
{
	for (;;) {
		if (!(sys_reg_read(MDIO_PHY_CONTROL_0) & BIT(31)))
			return 1;
		if (!*budget)
			return 0;
		--*budget;
		udelay(RAETH_MDIO_POLL_US);
	}
}

static u32 raeth_mdio_xfer(u32 data, u32 *read_data, unsigned int *budget)
{
	if (!raeth_mdio_wait(budget))
		return 0;
	sys_reg_write(MDIO_PHY_CONTROL_0, data);
	sys_reg_write(MDIO_PHY_CONTROL_0, data | BIT(31));
	if (!raeth_mdio_wait(budget))
		return 0;
	if (read_data)
		*read_data = sys_reg_read(MDIO_PHY_CONTROL_0) & 0xffff;
	return 1;
}

static void raeth_mdio_unlock(unsigned long flags, u32 result)
{
	enable_mdio(0);
	spin_unlock_irqrestore(&mdio_bus_lock, flags);
	if (!result)
		pr_err_ratelimited("MDIO transaction timed out\n");
}

void set_an_polling(u32 an_status)
{
	if (an_status)
		sys_reg_write(ESW_PHY_POLLING,
			      sys_reg_read(ESW_PHY_POLLING) | BIT(31));
	else
		sys_reg_write(ESW_PHY_POLLING,
			      sys_reg_read(ESW_PHY_POLLING) & ~BIT(31));
}

u32 mii_mgr_read(u32 phy_addr, u32 phy_register, u32 *read_data)
{
	struct END_DEVICE *ei_local;
	unsigned long flags;
	unsigned int budget = RAETH_MDIO_POLLS;
	u32 low_word, high_word, an_status = 0, rc = 0;

	if (!read_data || phy_addr > 31)
		return 0;
	ei_local = raeth_mdio_lock(&flags);
	if (!ei_local)
		return 0;
	enable_mdio(1);
	if ((ei_local->architecture &
	     (GE1_RGMII_FORCE_1000 | GE1_TRGMII_FORCE_2000 |
	      GE1_TRGMII_FORCE_2600)) && phy_addr == 31) {
		if (phy_register > 0xffff || (phy_register & 3))
			goto invalid;
		an_status = sys_reg_read(ESW_PHY_POLLING) & BIT(31);
		if (an_status)
			set_an_polling(0);
		if (!raeth_mdio_xfer((1U << 16) | (1U << 18) |
			(phy_addr << 20) | (31U << 25) |
			((phy_register >> 6) & 0x3ff), NULL, &budget) ||
		    !raeth_mdio_xfer((1U << 16) | (2U << 18) |
			(phy_addr << 20) | (((phy_register >> 2) & 15) << 25),
			&low_word, &budget) ||
		    !raeth_mdio_xfer((1U << 16) | (2U << 18) |
			(phy_addr << 20) | (16U << 25), &high_word, &budget))
			goto restore;
		*read_data = (high_word << 16) | low_word;
		rc = 1;
restore:
		if (an_status)
			set_an_polling(1);
	} else if (phy_register <= 31) {
		rc = raeth_mdio_xfer((1U << 16) | (2U << 18) |
			(phy_addr << 20) | (phy_register << 25), &low_word, &budget);
		if (rc)
			*read_data = low_word;
	} else {
		goto invalid;
	}
	raeth_mdio_unlock(flags, rc);
	return rc;
invalid:
	raeth_mdio_unlock(flags, 1);
	return 0;
}
EXPORT_SYMBOL(mii_mgr_read);

u32 mii_mgr_write(u32 phy_addr, u32 phy_register, u32 write_data)
{
	struct END_DEVICE *ei_local;
	unsigned long flags;
	unsigned int budget = RAETH_MDIO_POLLS;
	u32 an_status = 0, rc = 0;

	if (phy_addr > 31)
		return 0;
	ei_local = raeth_mdio_lock(&flags);
	if (!ei_local)
		return 0;
	enable_mdio(1);
	if ((ei_local->architecture &
	     (GE1_RGMII_FORCE_1000 | GE1_TRGMII_FORCE_2000 |
	      GE1_TRGMII_FORCE_2600)) && phy_addr == 31) {
		if (phy_register > 0xffff || (phy_register & 3))
			goto invalid;
		an_status = sys_reg_read(ESW_PHY_POLLING) & BIT(31);
		if (an_status)
			set_an_polling(0);
		rc = raeth_mdio_xfer((1U << 16) | (1U << 18) |
			(phy_addr << 20) | (31U << 25) |
			((phy_register >> 6) & 0x3ff), NULL, &budget) &&
		     raeth_mdio_xfer((1U << 16) | (1U << 18) |
			(phy_addr << 20) | (((phy_register >> 2) & 15) << 25) |
			(write_data & 0xffff), NULL, &budget) &&
		     raeth_mdio_xfer((1U << 16) | (1U << 18) |
			(phy_addr << 20) | (16U << 25) | (write_data >> 16),
			NULL, &budget);
		if (an_status)
			set_an_polling(1);
	} else if (phy_register <= 31 && write_data <= 0xffff) {
		rc = raeth_mdio_xfer((1U << 16) | (1U << 18) |
			(phy_addr << 20) | (phy_register << 25) | write_data,
			NULL, &budget);
	} else {
		goto invalid;
	}
	raeth_mdio_unlock(flags, rc);
	return rc;
invalid:
	raeth_mdio_unlock(flags, 1);
	return 0;
}
EXPORT_SYMBOL(mii_mgr_write);

u32 mii_mgr_cl45_set_address(u32 port_num, u32 dev_addr, u32 reg_addr)
{
	struct END_DEVICE *ei_local;
	unsigned long flags;
	unsigned int budget = RAETH_MDIO_POLLS;
	u32 rc;

	if (port_num > 31 || dev_addr > 31 || reg_addr > 0xffff)
		return 0;
	ei_local = raeth_mdio_lock(&flags);
	if (!ei_local)
		return 0;
	enable_mdio(1);
	rc = raeth_mdio_xfer((dev_addr << 25) | (port_num << 20) | reg_addr,
			     NULL, &budget);
	raeth_mdio_unlock(flags, rc);
	return rc;
}

u32 mii_mgr_read_cl45(u32 port_num, u32 dev_addr, u32 reg_addr, u32 *read_data)
{
	struct END_DEVICE *ei_local;
	unsigned long flags;
	unsigned int budget = RAETH_MDIO_POLLS;
	u32 data, rc;

	if (!read_data || port_num > 31 || dev_addr > 31 || reg_addr > 0xffff)
		return 0;
	ei_local = raeth_mdio_lock(&flags);
	if (!ei_local)
		return 0;
	enable_mdio(1);
	/* Both address and data phases share the lock and one finite budget. */
	rc = raeth_mdio_xfer((dev_addr << 25) | (port_num << 20) | reg_addr,
			     NULL, &budget) &&
	     raeth_mdio_xfer((dev_addr << 25) | (port_num << 20) | (3U << 18),
			     &data, &budget);
	if (rc)
		*read_data = data;
	raeth_mdio_unlock(flags, rc);
	return rc;
}

u32 mii_mgr_write_cl45(u32 port_num, u32 dev_addr, u32 reg_addr, u32 write_data)
{
	struct END_DEVICE *ei_local;
	unsigned long flags;
	unsigned int budget = RAETH_MDIO_POLLS;
	u32 rc;

	if (port_num > 31 || dev_addr > 31 || reg_addr > 0xffff || write_data > 0xffff)
		return 0;
	ei_local = raeth_mdio_lock(&flags);
	if (!ei_local)
		return 0;
	enable_mdio(1);
	rc = raeth_mdio_xfer((dev_addr << 25) | (port_num << 20) | reg_addr,
			     NULL, &budget) &&
	     raeth_mdio_xfer((dev_addr << 25) | (port_num << 20) | (1U << 18) |
			     write_data, NULL, &budget);
	raeth_mdio_unlock(flags, rc);
	return rc;
}
