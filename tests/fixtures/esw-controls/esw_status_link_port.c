static u32 esw_status_link_port(u32 port_id)
{
	u32 reg_pmsr;

#if defined (RAETH_GE2_MAC_TO_GPHY)
	if (port_id == WAN_PORT_X)
		reg_pmsr = sysRegRead(REG_ETH_GE2_MAC_STATUS);	// read state from GE2
	else
#elif defined (CONFIG_P4_MAC_TO_MT7530_GPHY_P0) || defined (CONFIG_P4_MAC_TO_MT7530_GPHY_P4)
	if (port_id == WAN_PORT_X)
		reg_pmsr = sysRegRead(RALINK_ETH_SW_BASE+REG_ESW_MAC_PMSR_P0 + 0x100*4);	// read state from P4
	else
#endif
		reg_pmsr = esw_reg_get(REG_ESW_MAC_PMSR_P0 + 0x100*port_id);

	return (reg_pmsr & 0x1);
}
