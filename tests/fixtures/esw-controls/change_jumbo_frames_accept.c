static void change_jumbo_frames_accept(u32 jumbo_frames_enabled)
{
	if (jumbo_frames_enabled)
		jumbo_frames_enabled = 1;

	if (g_jumbo_frames_enabled != jumbo_frames_enabled) {
		g_jumbo_frames_enabled = jumbo_frames_enabled;
		printk("%s - jumbo frames accept: %d bytes\n", MTK_ESW_DEVNAME, (jumbo_frames_enabled) ? 9000 : 1536);
		
		esw_jumbo_control(jumbo_frames_enabled);
	}
}
