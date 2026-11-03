INT MtATE_DCOC_Cal_Store_Proc(RTMP_ADAPTER *pAd, RTMP_STRING *arg)
{
	ULONG x = simple_strtol(arg, 0, 10);
	RXDCOC_RESULT_T RxDcocResult;
	BOOLEAN toCR = FALSE;
	UINT16 CentralFreq = 0;
	UINT8 BW = 0;
	UINT8 i = 0;
	UINT8 j = 0;
	ULONG CalOffset = 0;
	USHORT doCal1 = 0;
	UINT8 RetryTimes = 5;
	BOOLEAN DCOCPassOrFail = TRUE;
	BOOLEAN kABand = TRUE;
	BOOLEAN kGBand = TRUE;

	if (pAd->E2pAccessMode != E2P_FLASH_MODE && pAd->E2pAccessMode != E2P_BIN_MODE) {
		MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				 ("%s: Currently not in FLASH or BIN MODE,return.\n",
				  __func__));
		return FALSE;
	}

	RTMPZeroMemory(pAd->CalDCOCImage, DCOC_IMAGE_SIZE);

	if (x == 0) { /* 2G */
		kABand = FALSE;
		kGBand = TRUE;
	} else if (x == 1) { /* 5G */
		kABand = TRUE;
		kGBand = FALSE;
	} else { /* all K */
		kABand = TRUE;
		kGBand = TRUE;
	}
	 /* Disable RMAC */
	MtATESetMacTxRx(pAd, ASIC_MAC_RX, FALSE, TESTMODE_BAND0);
	if (IS_ATE_DBDC(pAd))
		MtATESetMacTxRx(pAd, ASIC_MAC_RX, FALSE, TESTMODE_BAND1);

	/* RXDCOC ABand */
	if (kABand) {
		for (i = 0; i < K_A20_SIZE; i++) {
			BW = BW_20;
			CentralFreq = K_A20Freq[i];
			CalOffset = i * RXDCOC_SIZE;

			for (j = 0; j < RetryTimes; j++) {
				RTMPZeroMemory(&RxDcocResult, sizeof(RXDCOC_RESULT_T));
				MtCmdGetRXDCOCCalResult(pAd, toCR, CentralFreq, BW, ABAND, FALSE, FALSE, &RxDcocResult);
				RtmpusecDelay(10);

				if (RxDcocResult.ResultSuccess)
					break;
			}

			if (RxDcocResult.ResultSuccess) {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("========== A20 freq %d save to offset %lx ========\n",
						  CentralFreq, DCOC_OFFSET + CalOffset));
				ShowDCOCData(pAd, RxDcocResult);
				memcpy(pAd->CalDCOCImage + CalOffset, &RxDcocResult.ucDCOCTBL_I_WF0_SX0_LNA[0], RXDCOC_SIZE);
			} else {
				ShowDCOCData(pAd, RxDcocResult);
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("!!!!!!  A20 freq %d RX still failed after %d retries !!!!!!!!\n", CentralFreq, RetryTimes));
				DCOCPassOrFail = FALSE;
				goto exit;
			}
		}

		for (i = 0; i < K_A40_SIZE; i++) {
			BW = BW_40;
			CentralFreq = K_A40Freq[i];
			CalOffset = (K_A20_SIZE + i) * RXDCOC_SIZE;

			for (j = 0; j < RetryTimes; j++) {
				RTMPZeroMemory(&RxDcocResult, sizeof(RXDCOC_RESULT_T));
				MtCmdGetRXDCOCCalResult(pAd, toCR, CentralFreq,	BW, ABAND, FALSE, FALSE, &RxDcocResult);
				RtmpusecDelay(10);

				if (RxDcocResult.ResultSuccess)
					break;
			}

			if (RxDcocResult.ResultSuccess) {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("========== A40 freq %d save to offset %lx ========\n",
						  CentralFreq, DCOC_OFFSET + CalOffset));
				ShowDCOCData(pAd, RxDcocResult);
				memcpy(pAd->CalDCOCImage + CalOffset, &RxDcocResult.ucDCOCTBL_I_WF0_SX0_LNA[0], RXDCOC_SIZE);
			} else {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("!!!!!!  A40 freq %d RX still failed after %d retries !!!!!!!!\n", CentralFreq, RetryTimes));
				DCOCPassOrFail = FALSE;
				goto exit;
			}
		}

		for (i = 0; i < K_A80_SIZE; i++) {
			BW = BW_80;
			CentralFreq = K_A80Freq[i];
			CalOffset = (K_A20_SIZE + K_A40_SIZE + i) * RXDCOC_SIZE;

			for (j = 0; j < RetryTimes; j++) {
				RTMPZeroMemory(&RxDcocResult, sizeof(RXDCOC_RESULT_T));
				MtCmdGetRXDCOCCalResult(pAd, toCR, CentralFreq,	BW, ABAND, FALSE, FALSE, &RxDcocResult);
				RtmpusecDelay(10);

				if (RxDcocResult.ResultSuccess)
					break;
			}

			if (RxDcocResult.ResultSuccess) {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("========== A80 freq %d save to offset %lx ========\n", CentralFreq, DCOC_OFFSET + CalOffset));
				ShowDCOCData(pAd, RxDcocResult);
				memcpy(pAd->CalDCOCImage + CalOffset, &RxDcocResult.ucDCOCTBL_I_WF0_SX0_LNA[0], RXDCOC_SIZE);
			} else {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("!!!!!!  A80 freq %d RX still failed after %d retries !!!!!!!!\n", CentralFreq, RetryTimes));
				DCOCPassOrFail = FALSE;
				goto exit;
			}
		}
	}

	/* RXDCOC GBand */
	if (kGBand) {
		for (i = 0; i < K_G20_SIZE; i++) {
			BW = BW_20;
			CentralFreq = K_G20Freq[i];
			CalOffset = (K_A20_SIZE + K_A40_SIZE + K_A80_SIZE + i) * RXDCOC_SIZE;

			for (j = 0; j < RetryTimes; j++) {
				RTMPZeroMemory(&RxDcocResult, sizeof(RXDCOC_RESULT_T));
				MtCmdGetRXDCOCCalResult(pAd, toCR, CentralFreq, BW, GBAND, FALSE, FALSE, &RxDcocResult);
				RtmpusecDelay(10);

				if (RxDcocResult.ResultSuccess)
					break;
			}

			if (RxDcocResult.ResultSuccess) {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("========== G20 freq %d save to offset %lx ========\n", CentralFreq, DCOC_OFFSET + CalOffset));
				ShowDCOCData(pAd, RxDcocResult);
				memcpy(pAd->CalDCOCImage + CalOffset, &RxDcocResult.ucDCOCTBL_I_WF0_SX0_LNA[0],	RXDCOC_SIZE);
			} else {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("!!!!!!  G20 freq %d RX still failed after %d retries !!!!!!!!\n", CentralFreq, RetryTimes));
				DCOCPassOrFail = FALSE;
				goto exit;
			}
		}
	}

	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
			 ("========== save to offset %x size %d========\n",
#ifdef RTMP_FLASH_SUPPORT
			  get_dev_eeprom_offset(pAd) +
#endif
			  DCOC_OFFSET, (K_ALL_SIZE * RXDCOC_SIZE)));
#ifdef RTMP_FLASH_SUPPORT

	if (pAd->E2pAccessMode == E2P_FLASH_MODE)
		RtmpFlashWrite(pAd->hdev_ctrl, pAd->CalDCOCImage,
			get_dev_eeprom_offset(pAd) + DCOC_OFFSET, (K_ALL_SIZE * RXDCOC_SIZE));

#endif

	if (pAd->E2pAccessMode == E2P_BIN_MODE)
		rtmp_cal_write_to_bin(pAd, pAd->CalDCOCImage, DCOC_OFFSET, (K_ALL_SIZE * RXDCOC_SIZE));

	/* raise DoCalibrate bits */
#ifdef RTMP_FLASH_SUPPORT

	if (pAd->E2pAccessMode == E2P_FLASH_MODE)
		rtmp_ee_flash_read(pAd, 0x52, &doCal1);

#endif

	if (pAd->E2pAccessMode == E2P_BIN_MODE)
		rtmp_ee_bin_read16(pAd, 0x52, &doCal1);

	doCal1 |= (1 << 1);
#ifdef RTMP_FLASH_SUPPORT

	if (pAd->E2pAccessMode == E2P_FLASH_MODE)
		rtmp_ee_flash_write(pAd, 0x52, doCal1);

#endif

	if (pAd->E2pAccessMode == E2P_BIN_MODE) {
		rtmp_ee_bin_write16(pAd, 0x52, doCal1);
		rtmp_ee_write_to_bin(
			pAd);		/* XXX: remember to writeback modified eeprom to file */
	}

	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			 ("raised E2P 0x52 = %x\n", doCal1));

	if (pAd->KtoFlashDebug) {
		ULONG CalOffset = 0;
		MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				 ("######################### reload caldata for debug ####################################\n"));
		RtmpusecDelay(20000);
#ifdef RTMP_FLASH_SUPPORT

		if (pAd->E2pAccessMode == E2P_FLASH_MODE)
			RtmpFlashRead(pAd->hdev_ctrl, pAd->CalDCOCImage,
				get_dev_eeprom_offset(pAd) + DCOC_OFFSET, (K_ALL_SIZE * RXDCOC_SIZE));

#endif

		if (pAd->E2pAccessMode == E2P_BIN_MODE)
			rtmp_cal_load_from_bin(pAd, pAd->CalDCOCImage, DCOC_OFFSET, (K_ALL_SIZE * RXDCOC_SIZE));

		/* Find offset base on CentralFreq */
		for (i = 0; i < K_ALL_SIZE; i++) {
			CalOffset = i * RXDCOC_SIZE;
			MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s: reload from offset [%lx]  freq [%d]=================\n",
					  __func__, CalOffset + DCOC_OFFSET, K_AllFreq[i]));
			memcpy(&RxDcocResult.ucDCOCTBL_I_WF0_SX0_LNA[0],
				   pAd->CalDCOCImage + CalOffset, RXDCOC_SIZE);
			ShowDCOCData(pAd, RxDcocResult);
		}
	}

exit:
	/* Enable RMAC */
	MtATESetMacTxRx(pAd, ASIC_MAC_RX, TRUE, TESTMODE_BAND0);
	if (IS_ATE_DBDC(pAd))
		MtATESetMacTxRx(pAd, ASIC_MAC_RX, TRUE, TESTMODE_BAND1);

	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			 ("====================\n"));
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			 ("RX_SELF_TEST : [%s]\n",
			  (DCOCPassOrFail == TRUE) ? "PASS" : "FAIL"));
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			 ("====================\n"));
	return TRUE;
}