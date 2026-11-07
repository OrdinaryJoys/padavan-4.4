static int phy_polling_thread(void *data)
{
	unsigned int link_status, link_speed, duplex;
	unsigned int local_eee, lp_eee;
	unsigned int fc_phy, fc_lp;
	unsigned int val_tmp;

	pr_info("%s called\n", __func__);
	val_tmp = 1;
	for (;;) {
		mii_mgr_read(0x0, 0x1, &link_status);
		link_status = (link_status >> 2) & 0x1;
		if (link_status) {
			mii_mgr_read(0x0, 0x4, &fc_phy);
			mii_mgr_read(0x0, 0x5, &fc_lp);
			if ((fc_phy & 0xc00) == (fc_lp & 0xc00))
				val_tmp = val_tmp | 0x30;
			else
				val_tmp = val_tmp & (~0x30);
			mii_mgr_read_cl45(0, 0x1e, 0xa2, &link_speed);
			duplex = link_speed & 0x20;
			if (duplex)
				val_tmp = val_tmp | 0x2;
			else
				val_tmp = val_tmp & (~0x2);
			link_speed = link_speed & 0xe;
			val_tmp = val_tmp & (~0xc);
			if (link_speed == 0x04)
				val_tmp = val_tmp | (0x4);
			else if (link_speed == 0x08)
				val_tmp = val_tmp | (0x8);
			mii_mgr_read_cl45(0, 0x7, 0x3c, &local_eee);
			mii_mgr_read_cl45(0, 0x7, 0x3d, &lp_eee);
			if ((local_eee & 0x4) == 4 && (lp_eee & 0x4) == 4)/*1g eee*/
				val_tmp = val_tmp | 0x80;
			if ((local_eee & 0x2) == 2 && ((lp_eee & 0x2) == 2))/*100m eee*/
				val_tmp = val_tmp | 0x40;
			val_tmp = val_tmp & 0xff;
			sys_reg_write(ETHDMASYS_ETH_MAC_BASE + 0x200, 0x2105e300 | val_tmp);
		} else {
			/*force link down*/
			set_ge2_force_link_down();
		}

		msleep_interruptible(PHY_POLLING_MS);
		if (kthread_should_stop())
			break;
	}

	pr_info("%s leaved\n", __func__);
	return 0;
}
