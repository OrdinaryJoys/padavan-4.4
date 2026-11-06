static NTSTATUS HwCtrlWifiSysPeerLinkDown(RTMP_ADAPTER *pAd, HwCmdQElmt *CMDQelmt)
{
	struct WIFI_SYS_CTRL *wsys = (struct WIFI_SYS_CTRL *)CMDQelmt->buffer;

	if (CMDQelmt->bufferlength != sizeof(*wsys) || !wsys ||
		!wsys->wdev || wsys->wdev->sys_handle != pAd)
		return NDIS_STATUS_INVALID_DATA;

	if (pAd->HwCtrl.hwctrl_ops.wifi_sys_disconnt_act)
		return pAd->HwCtrl.hwctrl_ops.wifi_sys_disconnt_act(wsys);
	else {
		AsicNotSupportFunc(pAd, __func__);
		return NDIS_STATUS_FAILURE;
	}
}
