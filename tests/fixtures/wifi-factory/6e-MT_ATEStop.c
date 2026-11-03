static INT32 MT_ATEStop(RTMP_ADAPTER *pAd)
{
	struct _ATE_CTRL *ATECtrl = &pAd->ATECtrl;
	struct _ATE_IF_OPERATION *if_ops = ATECtrl->ATEIfOps;
	INT32 Ret = 0;
#ifdef CONFIG_AP_SUPPORT
	INT32 IdBss, MaxNumBss = pAd->ApCfg.BssidNum;
	BSS_STRUCT *pMbss = &pAd->ApCfg.MBSSID[MAIN_MBSSID];
#endif
	UCHAR Channel = HcGetRadioChannel(pAd);

	MTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s\n", __func__));
	AsicSetMacTxRx(pAd, ASIC_MAC_RXV, FALSE);
	NICInitializeAdapter(pAd);
#ifdef RTMP_MAC_PCI

	if (if_ops->clean_test_rx_frame)
		if_ops->clean_test_rx_frame(pAd);

#endif /* RTMP_MAC_PCI */
	/* if usb  call this two function , FW will hang~~ */

	if (if_ops->clean_trx_q)
		if_ops->clean_trx_q(pAd);

	if (if_ops->ate_leave)
		if_ops->ate_leave(pAd);

	AsicSetRxFilter(pAd);
	RTMPEnableRxTx(pAd);
	hc_reset_radio(pAd);
#ifdef CONFIG_AP_SUPPORT
	APStartUp(pAd, pMbss, AP_BSS_OPER_ALL);
#endif /* CONFIG_AP_SUPPROT  */
	RTMP_OS_NETDEV_START_QUEUE(pAd->net_dev);
#ifdef CONFIG_AP_SUPPORT
	IF_DEV_CONFIG_OPMODE_ON_AP(pAd) {
		if (MaxNumBss > MAX_MBSSID_NUM(pAd))
			MaxNumBss = MAX_MBSSID_NUM(pAd);

		/*  first IdBss must not be 0 (BSS0), must be 1 (BSS1) */
		for (IdBss = FIRST_MBSSID; IdBss < MAX_MBSSID_NUM(pAd); IdBss++) {
			if (pAd->ApCfg.MBSSID[IdBss].wdev.if_dev)
				RTMP_OS_NETDEV_START_QUEUE(pAd->ApCfg.MBSSID[IdBss].wdev.if_dev);
		}
	}
#endif

	/* MT7636 Test Mode Freqency offset restore*/
	if (ATECtrl->en_man_set_freq == 1) {
		MTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("MT76x6 Manual Set Frequency Restore\n"));
		RTMP_IO_WRITE32(pAd, FREQ_OFFSET_MANUAL_ENABLE, ATECtrl->en_man_freq_restore);
		RTMP_IO_WRITE32(pAd, FREQ_OFFSET_MANUAL_VALUE, ATECtrl->normal_freq_restore);
		ATECtrl->normal_freq_restore = 0;
		ATECtrl->en_man_freq_restore = 0;
		ATECtrl->en_man_set_freq = 0;
	}

	RTMP_OS_EXIT_COMPLETION(&ATECtrl->cmd_done);
	ATECtrl->Mode = ATE_STOP;

	if ((MTK_REV_GTE(pAd, MT7603, MT7603E1)) ||
		(MTK_REV_GTE(pAd, MT7628, MT7628E1))) {
		UINT32 Value;

		RTMP_IO_READ32(pAd, CR_RFINTF_00, &Value);
		Value &= ~CR_RFINTF_CAL_NSS_MASK;
		Value |= CR_RFINTF_CAL_NSS(0x0);
		RTMP_IO_WRITE32(pAd, CR_RFINTF_00, Value);
	}

	return Ret;
}
