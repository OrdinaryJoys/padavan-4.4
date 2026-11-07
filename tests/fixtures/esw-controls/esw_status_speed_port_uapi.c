static u32 esw_status_speed_port_uapi(u32 port_id_uapi)
{
	u32 port_link, port_duplex, port_speed;
	u32 port_eee, port_fc_rx, port_fc_tx;
	u32 reg_pmsr;
	u32 port_id = get_port_from_uapi(port_id_uapi);

	if (port_id > ESW_EPHY_ID_MAX)
		return 0;

#if defined (RAETH_GE2_MAC_TO_GPHY)
	if (port_id == WAN_PORT_X) {
		reg_pmsr = sysRegRead(REG_ETH_GE2_MAC_STATUS);	// read state from GE2
#if defined (CONFIG_GE2_RGMII_AN)
		reg_pmsr |= ext_gphy_fill_pmsr(CONFIG_MAC_TO_GIGAPHY_MODE_ADDR2);
#endif
	} else
#elif defined (CONFIG_P4_MAC_TO_MT7530_GPHY_P0) || defined (CONFIG_P4_MAC_TO_MT7530_GPHY_P4)
	if (port_id == WAN_PORT_X)
		reg_pmsr = sysRegRead(RALINK_ETH_SW_BASE+REG_ESW_MAC_PMSR_P0 + 0x100*4);	// read state from P4
	else
#endif
		reg_pmsr = esw_reg_get(REG_ESW_MAC_PMSR_P0 + 0x100*port_id);

	port_link = (reg_pmsr & 0x1);

	if (!port_link)
		return 0;

	port_duplex = (reg_pmsr >> 1) & 0x1;
	port_speed  = (reg_pmsr >> 2) & 0x3;
	port_fc_tx  = (reg_pmsr >> 4) & 0x1;
	port_fc_rx  = (reg_pmsr >> 5) & 0x1;
	port_eee    = (reg_pmsr >> 6) & 0x3;

	return ((port_link << 16) | (port_eee << 11) | (port_fc_rx << 10) | (port_fc_tx << 9) | (port_duplex << 8) | port_speed);
}
