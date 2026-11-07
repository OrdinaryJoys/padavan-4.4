static int change_port_link_mode_uapi(u32 port_id_uapi, u32 port_link_mode)
{
	const char *link_desc = "Auto", *flow_desc = "ON";
	u32 i_port_speed, i_port_flowc, i_port_power;
	u32 esw_phy_ana = 0x05e1;
	u32 esw_phy_mcr = 0x3100; /* 100 FD + auto-negotiation */
	u32 phy_mdio_addr;
	u32 port_id = get_port_from_uapi(port_id_uapi);

	if (port_id > ESW_EPHY_ID_MAX)
		return -EINVAL;

	if (g_port_link_mode[port_id] == port_link_mode)
		return 0;

	phy_mdio_addr = port_id;

	i_port_speed =  (port_link_mode & 0x0F);
	i_port_flowc = ((port_link_mode >> 8) & 0x03);
	i_port_power = (i_port_speed == SWAPI_LINK_SPEED_MODE_FORCE_POWER_OFF) ? 0 : 1;

	if (!i_port_power)
		i_port_speed = SWAPI_LINK_SPEED_MODE_AUTO;

	switch (i_port_speed)
	{
	case SWAPI_LINK_SPEED_MODE_AUTO_100_FD:
		link_desc = "100FD [AN]";
		/* disable ability 100 HD, 10 FD, 10 HD */
		esw_phy_ana &= ~((1<<7)|(1<<6)|(1<<5));
		break;
	case SWAPI_LINK_SPEED_MODE_AUTO_100_HD:
		link_desc = "100HD [AN]";
		/* disable ability 100 FD, 10 FD, 10 HD */
		esw_phy_ana &= ~((1<<8)|(1<<6)|(1<<5));
		/* disable FD */
		esw_phy_mcr &= ~((1<<8));
		break;
	case SWAPI_LINK_SPEED_MODE_AUTO_10_FD:
		link_desc = "10FD [AN]";
		/* disable ability 100 FD, 100 HD, 10 HD */
		esw_phy_ana &= ~((1<<8)|(1<<7)|(1<<5));
		/* set 10Mbps */
		esw_phy_mcr &= ~((1<<13));
		break;
	case SWAPI_LINK_SPEED_MODE_AUTO_10_HD:
		link_desc = "10HD [AN]";
		/* disable ability 100 FD, 100 HD, 10 FD */
		esw_phy_ana &= ~((1<<8)|(1<<7)|(1<<6));
		/* set 10Mbps, disable FD */
		esw_phy_mcr &= ~((1<<13)|(1<<8));
		break;
	case SWAPI_LINK_SPEED_MODE_FORCE_100_FD:
		link_desc = "100FD [Force]";
		/* disable ability 100 HD, 10 FD, 10 HD */
		esw_phy_ana &= ~((1<<7)|(1<<6)|(1<<5));
		/* disable auto-negotiation */
		esw_phy_mcr &= ~((1<<12));
		break;
	case SWAPI_LINK_SPEED_MODE_FORCE_100_HD:
		link_desc = "100HD [Force]";
		/* disable ability 100 FD, 10 FD, 10 HD */
		esw_phy_ana &= ~((1<<8)|(1<<6)|(1<<5));
		/* disable auto-negotiation, disable FD */
		esw_phy_mcr &= ~((1<<12)|(1<<8));
		break;
	case SWAPI_LINK_SPEED_MODE_FORCE_10_FD:
		link_desc = "10FD [Force]";
		/* disable ability 100 FD, 100 HD, 10 HD */
		esw_phy_ana &= ~((1<<8)|(1<<7)|(1<<5));
		/* disable auto-negotiation, set 10Mbps */
		esw_phy_mcr &= ~((1<<13)|(1<<12));
		break;
	case SWAPI_LINK_SPEED_MODE_FORCE_10_HD:
		link_desc = "10HD [Force]";
		/* disable ability 100 FD, 100 HD, 10 FD */
		esw_phy_ana &= ~((1<<8)|(1<<7)|(1<<6));
		/* disable auto-negotiation, set 10Mbps, disable FD */
		esw_phy_mcr &= ~((1<<13)|(1<<12)|(1<<8));
		break;
	}

	switch (i_port_flowc)
	{
	case SWAPI_LINK_FLOW_CONTROL_TX_ASYNC:
	case SWAPI_LINK_FLOW_CONTROL_DISABLE:
		flow_desc = "OFF";
		/* disable pause ability (A6,A5) */
		esw_phy_ana &= ~((1<<11)|(1<<10));
		break;
	}

	/* external GigaPHY */
#if defined (CONFIG_P4_MAC_TO_PHY_MODE)
	if (port_id == 4)
		phy_mdio_addr = CONFIG_MAC_TO_GIGAPHY_MODE_ADDR2;
#endif
#if defined (CONFIG_P5_MAC_TO_PHY_MODE)
	if (port_id == 5)
		phy_mdio_addr = CONFIG_MAC_TO_GIGAPHY_MODE_ADDR;
#elif defined (CONFIG_GE2_RGMII_AN)
	if (port_id == 5)
		phy_mdio_addr = CONFIG_MAC_TO_GIGAPHY_MODE_ADDR2;
#endif

	/* MT7621/MT7530 GSW or external GigaPHY */
#if 1
	{
		u32 esw_phy_gcr = 0;
		
		/* set MII control register [6,13] */
		if (i_port_speed <= SWAPI_LINK_SPEED_MODE_AUTO_1000_FD) {
			/* set 1000 Mbps */
			esw_phy_mcr &= ~(1<<13);
			esw_phy_mcr |=  (1<<6);
		}
		
		/* set auto-negotiation advertisement register [5,6,7,8] */
		if (i_port_speed == SWAPI_LINK_SPEED_MODE_AUTO_1000_FD) {
			/* disable ability 100 FD, 100 HD, 10 FD, 10 HD */
			esw_phy_ana &= ~((1<<8)|(1<<7)|(1<<6)|(1<<5));
			link_desc = "1000FD [AN]";
		}
		
		/* set auto-negotiation advertisement register [11] */
		if (i_port_speed <= SWAPI_LINK_SPEED_MODE_AUTO_1000_FD &&
		    i_port_flowc == SWAPI_LINK_FLOW_CONTROL_TX_ASYNC) {
			/* enable asymmetric pause ability (A6) */
			esw_phy_ana |= (1<<11);
			flow_desc = "TX Asy";
		}
		
		/* set 1000Base-T control register [8,9] */
		mii_mgr_read(phy_mdio_addr, 9, &esw_phy_gcr);
		if (i_port_speed <= SWAPI_LINK_SPEED_MODE_AUTO_1000_FD) {
			/* enable 1000Base-T Advertisement */
			esw_phy_gcr |=  ((1<<9)|(1<<8));
		} else {
			/* disable 1000Base-T Advertisement */
			esw_phy_gcr &= ~((1<<9)|(1<<8));
		}
		mii_mgr_write(phy_mdio_addr, 9, esw_phy_gcr);
	}
#endif

	/* set PHY ability */
	mii_mgr_write(phy_mdio_addr, 4, esw_phy_ana);

	if (i_port_power) {
		if (!(esw_phy_mcr & (1<<12))) {
			/* power-down PHY */
			esw_phy_mcr |= (1<<11);
			
			/* set PHY mode */
			mii_mgr_write(phy_mdio_addr, 0, esw_phy_mcr);
			
			/* wait for PHY down */
			msleep(500);
			
			/* power-up PHY */
			esw_phy_mcr &= ~(1<<11);
		} else {
			/* restart PHY auto-negotiation */
			esw_phy_mcr |= (1<<9);
		}
	} else {
		/* power-down PHY */
		esw_phy_mcr |= (1<<11);
	}

	/* set PHY mode */
	mii_mgr_write(phy_mdio_addr, 0, esw_phy_mcr);

	g_port_link_mode[port_id] = port_link_mode;

	if (!i_port_power) {
		link_desc = "Power OFF";
		flow_desc = "N/A";
	}

	printk("%s - %s link speed: %s, flow control: %s\n",
		MTK_ESW_DEVNAME, get_port_desc(port_id), link_desc, flow_desc);

	return 0;
}
