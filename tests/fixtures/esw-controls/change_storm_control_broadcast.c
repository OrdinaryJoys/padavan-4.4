static void change_storm_control_broadcast(u32 control_rate_mbps)
{
	u32 i;
	char rate_desc[16];

	if (control_rate_mbps >= 1024)
		control_rate_mbps = 0;

	if (g_storm_rate_limit != control_rate_mbps) {
		g_storm_rate_limit = control_rate_mbps;
		
		if (control_rate_mbps > 0)
			snprintf(rate_desc, sizeof(rate_desc), "%d mbps", control_rate_mbps);
		else
			strcpy(rate_desc, "off");
		
		printk("%s - set broadcast storm control rate as: %s\n", MTK_ESW_DEVNAME, rate_desc);
		
		for (i = 0; i <= ESW_EPHY_ID_MAX; i++) {
			if ((1u << i) & ESW_MASK_EXCLUDE)
				continue;
			esw_storm_control(i, 1, 0, 0, control_rate_mbps);
		}
	}
}
