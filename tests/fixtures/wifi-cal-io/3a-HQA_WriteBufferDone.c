static INT32 HQA_WriteBufferDone(
	PRTMP_ADAPTER pAd,
	RTMP_IOCTL_INPUT_STRUCT *WRQ,
	struct _HQA_CMD_FRAME *HqaCmdFrame)
{
	UINT32 Value = 0;
	INT32 Ret = 0;

	MTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s\n", __func__));
	memcpy((PUCHAR)&Value, (PUCHAR)&HqaCmdFrame->Data, 4);
	Value = PKTL_TRAN_TO_HOST(Value);
#if !defined(COMPOS_TESTMODE_WIN) /* 1Todo	Set_EepromBufferWriteBack_Proc */

	switch (Value) {
	case E2P_EFUSE_MODE:
#ifdef RF_LOCKDOWN
		/* update status of Effuse write back */
		pAd->fgQAEffuseWriteBack = TRUE;
#endif /* RF_LOCKDOWN */
		Set_EepromBufferWriteBack_Proc(pAd, "1");
		break;

	case E2P_FLASH_MODE:
		Set_EepromBufferWriteBack_Proc(pAd, "2");
		break;

	case E2P_EEPROM_MODE:
		Set_EepromBufferWriteBack_Proc(pAd, "3");
		break;

	case E2P_BIN_MODE:
		Set_EepromBufferWriteBack_Proc(pAd, "4");
		break;

	default:
		MTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE,
				 ("%s: Unknow write back mode(%d)\n", __func__, Value));
	}

#endif
#ifdef RF_LOCKDOWN
	/* update status of Effuse write back */
	pAd->fgQAEffuseWriteBack = FALSE;
#endif /* RF_LOCKDOWN */
	ResponseToQA(HqaCmdFrame, WRQ, 2, Ret);
	return Ret;
}