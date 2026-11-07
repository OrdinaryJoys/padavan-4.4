	for (i = 0; i < BOARD_NUM_ETH_EPHY; i++) {
		if (phy_status_port_bytes(i, &counter[0], &counter[1]) < 0)
			continue;
		snprintf(buf, sizeof(buf), "ESW_P%d", i);
		if (!iterate_netdev(buf, 0, 0, ticks, counter))
			continue;
	}
