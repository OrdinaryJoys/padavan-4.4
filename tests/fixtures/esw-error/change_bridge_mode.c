static int change_bridge_mode(u32 wan_bwan_isolation, u32 wan_bridge_mode)
{
	int i, bridge_changed, br_iso_changed, vlan_rule_changed, power_changed;

	if (wan_bridge_mode > SWAPI_WAN_BRIDGE_DISABLE_WAN)
		return -EINVAL;

	if (wan_bwan_isolation > SWAPI_WAN_BWAN_ISOLATION_BETWEEN)
		return -EINVAL;

	if (wan_bridge_mode == SWAPI_WAN_BRIDGE_DISABLE)
		wan_bwan_isolation = SWAPI_WAN_BWAN_ISOLATION_NONE;

	bridge_changed = (g_wan_bridge_mode != wan_bridge_mode) ? 1 : 0;
	br_iso_changed = (g_wan_bwan_isolation != wan_bwan_isolation) ? 1 : 0;
	vlan_rule_changed = 0;
	for (i = 0; i <= SWAPI_VLAN_RULE_WAN_LAN4; i++) {
		if (g_vlan_rule[i] != g_vlan_rule_user[i]) {
			vlan_rule_changed = 1;
			break;
		}
	}

	// set global bridge_mode first
	g_wan_bridge_mode = wan_bridge_mode;
	g_wan_bwan_isolation = wan_bwan_isolation;

	if (atomic_read(&g_switch_inited) == 0)
		return 0;

	power_changed = 0;
	if (bridge_changed || vlan_rule_changed) {
		power_changed = change_wan_lan_ports_power(0, 1);
		if (power_changed) {
			// wait for PHY link down
			msleep(500);
		}
	}

	if (bridge_changed || br_iso_changed)
		esw_mask_bridge_isolate(wan_bridge_mode, wan_bwan_isolation);

	esw_vlan_bridge_isolate(wan_bridge_mode, wan_bwan_isolation, bridge_changed, br_iso_changed, vlan_rule_changed);

	if (power_changed)
		change_wan_lan_ports_power(1, 1);

	return 0;
}