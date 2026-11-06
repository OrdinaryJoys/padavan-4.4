int esw_ioctl_init_post(void)
{
	/* configure bridge isolation mode via forwards mask */
	esw_mask_bridge_isolate(g_wan_bridge_mode, g_wan_bwan_isolation);

	/* enable MAC for all PHY ports */
	esw_mac_to_phy_enable();

	/* configure bridge isolation mode via VLAN */
	esw_vlan_bridge_isolate(g_wan_bridge_mode, g_wan_bwan_isolation, 1, 1, 1);

#if defined (CONFIG_RAETH_ESW_IGMP_SNOOP_HW)
	/* configure igmp/mld snooping */
	esw_igmp_flood_to_cpu( (g_igmp_snooping_enabled && !g_igmp_static_ports) ? 1 : 0 );
	esw_igmp_mld_snooping(g_igmp_snooping_enabled, g_igmp_snooping_enabled);
#endif

	/* configure leds */
	esw_led_mode(g_led_phy_mode);

	atomic_set(&g_switch_inited, 1);
	atomic_set(&g_switch_allow_irq, 1);

	return 0;
}