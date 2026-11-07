INT Set_WifiFwdShowEntry(
	IN PRTMP_ADAPTER pAd,
	IN RTMP_STRING *arg)
{
	if (wf_drv_tbl.wf_fwd_show_entry_hook)
		wf_drv_tbl.wf_fwd_show_entry_hook();

	return TRUE;
}
