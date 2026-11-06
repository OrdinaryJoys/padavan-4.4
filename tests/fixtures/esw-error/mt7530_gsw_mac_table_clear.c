static
int mt7530_gsw_mac_table_clear(int static_only)
{
	u32 atc_val;

	/* clear all (non)static MAC entries */
	atc_val = (static_only) ? 0x8602 : 0x8002;

	mii_mgr_write(0x1f, 0x80, atc_val);

	return mt7530_gsw_wait_wt_mac();
}