static
int mt7530_gsw_wait_wt_mac(void)
{
	u32 i, atc_val;

	for (i = 0; i < 200; i++) {
		udelay(100);
		atc_val = 0;
		mii_mgr_read(0x1f, 0x80, &atc_val);
		if (!(atc_val & BIT(15)))
			return 0;
	}

	return -1;
}