static void
dl_on_timer(void)
{
	static int dl_initialized = 0;
	int is_ap_mode = dl_is_ap_mode;
	unsigned int is_link_changed;

	dl_counter_total++;

	is_link_changed = 0;
	phy_status_port_link_changed(&is_link_changed);
	if (is_link_changed || !dl_initialized) {
		int phy_link;
		
		phy_link = get_wan_ether_link_direct(is_ap_mode);
		if (phy_link >= 0)
			dl_status_wan = phy_link;
		
		phy_link = 0;
		if (phy_status_port_link_lan_all(&phy_link) == 0)
			dl_status_lan = phy_link;
		
		if (is_ap_mode)
			dl_status_lan |= dl_status_wan;
		
		if (!dl_initialized)
			dl_initialized = 1;
	}

	if (!is_ap_mode) {
		dl_handle_link_wan();
		
		if (get_wan_wisp_active(&dl_status_wisp))
			dl_handle_link_wisp();
	}

	dl_handle_link_lan();
#if defined (USE_USB_SUPPORT)
	dl_handle_link_usb(0);
#endif
}
