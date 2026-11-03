INT MtATE_DPD_Cal_Store_Proc(RTMP_ADAPTER *pAd, RTMP_STRING *arg)
{
	ULONG x = simple_strtol(arg, 0, 10);
	TXDPD_RESULT_T TxDpdResult;
	BOOLEAN toCR = FALSE; /* CR to Flash/Bin file */
	UINT16 CentralFreq = 0;
	UINT8 BW = 0;
	UINT8 i = 0;
	UINT8 j = 0;
	ULONG CalOffset = 0;
	USHORT doCal1 = 0;
	UINT8 RetryTimes = 5;
	BOOLEAN DPDPassOrFail = TRUE;
	BOOLEAN kABand = TRUE;
	BOOLEAN kGBand = TRUE;

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

	if (pAd->E2pAccessMode != E2P_FLASH_MODE && pAd->E2pAccessMode != E2P_BIN_MODE) {
		MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				 ("%s: Currently not in FLASH or BIN MODE,return.\n", __func__));
		return FALSE;
	}
	/* Stop TX RX MAC */
	SetATE(pAd, "TXSTOP");
	SetATE(pAd, "RXSTOP");

	/* TXDPD ABand */
	if (kABand) {
		RTMPZeroMemory(pAd->CalDPDAPart1Image, TXDPD_IMAGE1_SIZE);

		/* TXDPD A20  */
		for (i = 0; i < DPD_A20_SIZE; i++) {
			BW = BW_20;
			CentralFreq = DPD_A20Freq[i];
			CalOffset = i * TXDPD_SIZE;

			for (j = 0; j < RetryTimes; j++) {
				RTMPZeroMemory(&TxDpdResult, sizeof(TXDPD_RESULT_T));
				MtCmdGetTXDPDCalResult(pAd, toCR, CentralFreq, BW, ABAND, FALSE, FALSE, &TxDpdResult);
				RtmpusecDelay(10);

				if (TxDpdResult.ResultSuccess)
					break;
			}

			if (TxDpdResult.ResultSuccess) {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("==========TX A20 P1 freq %d save to flash offset %lx ========\n", CentralFreq, DPDPART1_OFFSET + CalOffset));
				ShowDPDData(pAd, TxDpdResult);
				memcpy(pAd->CalDPDAPart1Image + CalOffset, &TxDpdResult.u4DPDG0_WF0_Prim, TXDPD_SIZE);
			} else {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("!!!!!!  A20 freq %d TX still failed after %d retries !!!!!!!!\n", CentralFreq, RetryTimes));
				DPDPassOrFail = FALSE;
				goto exit;
			}
		}

#ifdef RTMP_FLASH_SUPPORT

		if (pAd->E2pAccessMode == E2P_FLASH_MODE)
			RtmpFlashWrite(pAd->hdev_ctrl, pAd->CalDPDAPart1Image,
				get_dev_eeprom_offset(pAd) + DPDPART1_OFFSET, TXDPD_PART1_LIMIT * TXDPD_SIZE);

#endif
		if (pAd->E2pAccessMode == E2P_BIN_MODE)
			rtmp_cal_write_to_bin(pAd, pAd->CalDPDAPart1Image, DPDPART1_OFFSET, TXDPD_PART1_LIMIT * TXDPD_SIZE);

		RtmpusecDelay(20000);
	}
	/* TXDPD G20 */
	if (kGBand) {
		RTMPZeroMemory(pAd->CalDPDAPart2Image, TXDPD_IMAGE2_SIZE);

		for (i = 0; i < DPD_G20_SIZE; i++) {
			BW = BW_20;
			CentralFreq = DPD_G20Freq[i];
			CalOffset = i * TXDPD_SIZE;

			for (j = 0; j < RetryTimes; j++) {
				RTMPZeroMemory(&TxDpdResult, sizeof(TXDPD_RESULT_T));
				MtCmdGetTXDPDCalResult(pAd, toCR, CentralFreq, BW, GBAND, FALSE, FALSE, &TxDpdResult);
				RtmpusecDelay(10);

				if (TxDpdResult.ResultSuccess)
					break;
			}

			if (TxDpdResult.ResultSuccess) {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("==========TX G20 freq %d save to flash offset %lx ========\n", CentralFreq, DPDPART1_OFFSET + DPD_A20_SIZE * TXDPD_SIZE + CalOffset));
				ShowDPDData(pAd, TxDpdResult);
				memcpy(pAd->CalDPDAPart2Image + CalOffset, &TxDpdResult.u4DPDG0_WF0_Prim, TXDPD_SIZE);
			} else {
				MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("!!!!!!  G20 freq %d TX still failed after %d retries !!!!!!!!\n", CentralFreq, RetryTimes));
				DPDPassOrFail = FALSE;
				goto exit;
			}
		}

#ifdef RTMP_FLASH_SUPPORT

		if (pAd->E2pAccessMode == E2P_FLASH_MODE)
			RtmpFlashWrite(pAd->hdev_ctrl, pAd->CalDPDAPart2Image,
				get_dev_eeprom_offset(pAd) + DPDPART2_OFFSET, (DPD_G20_SIZE * TXDPD_SIZE));

#endif

		if (pAd->E2pAccessMode == E2P_BIN_MODE)
			rtmp_cal_write_to_bin(pAd, pAd->CalDPDAPart2Image, DPDPART2_OFFSET, (DPD_G20_SIZE * TXDPD_SIZE));
	}

	/* raise DoCalibrate bits */
	if (pAd->E2pAccessMode == E2P_BIN_MODE)
		rtmp_ee_bin_read16(pAd, 0x52, &doCal1);

#ifdef RTMP_FLASH_SUPPORT

	if (pAd->E2pAccessMode == E2P_FLASH_MODE)
		rtmp_ee_flash_read(pAd, 0x52, &doCal1);

#endif
	doCal1 |= (1 << 0);
	/* raise bit 4 to denote 16 entry TXDPD */
	doCal1 |= (1 << 4);

	if (pAd->E2pAccessMode == E2P_BIN_MODE) {
		rtmp_ee_bin_write16(pAd, 0x52, doCal1);
		rtmp_ee_write_to_bin(pAd);		/* writeback to eeprom file */
	}

#ifdef RTMP_FLASH_SUPPORT

	if (pAd->E2pAccessMode == E2P_FLASH_MODE)
		rtmp_ee_flash_write(pAd, 0x52, doCal1);

#endif
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("raised E2P 0x52 = %x\n", doCal1));

	/* reload test -- for debug only */
	if (pAd->KtoFlashDebug) {
		ULONG CalOffset = 0;
		MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				 ("\n######################### reload caldata for debug ####################################\n"));
		RtmpusecDelay(20000);

#ifdef RTMP_FLASH_SUPPORT

		if (pAd->E2pAccessMode == E2P_FLASH_MODE) {
			RtmpFlashRead(pAd->hdev_ctrl, pAd->CalDPDAPart1Image,
				get_dev_eeprom_offset(pAd) + DPDPART1_OFFSET, TXDPD_IMAGE1_SIZE);
			RtmpFlashRead(pAd->hdev_ctrl, pAd->CalDPDAPart2Image,
				get_dev_eeprom_offset(pAd) + DPDPART2_OFFSET, TXDPD_IMAGE2_SIZE);
		}
#endif

		if (pAd->E2pAccessMode == E2P_BIN_MODE) {
			rtmp_cal_load_from_bin(pAd, pAd->CalDPDAPart1Image, DPDPART1_OFFSET, TXDPD_IMAGE1_SIZE);
			rtmp_cal_load_from_bin(pAd, pAd->CalDPDAPart2Image, DPDPART2_OFFSET, TXDPD_IMAGE2_SIZE);
		}

		/* Find flash offset base on CentralFreq */
		for (i = 0; i < DPD_ALL_SIZE; i++) {
			CalOffset = i * TXDPD_SIZE;
			MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s: reload flash offset [%lx]  freq [%d]=================\n",
					  __func__, CalOffset + DPDPART1_OFFSET, DPD_AllFreq[i]));

			if (i < DPD_A20_SIZE)
				memcpy(&TxDpdResult.u4DPDG0_WF0_Prim, pAd->CalDPDAPart1Image + CalOffset, TXDPD_SIZE);
			else {
				CalOffset = (i - DPD_A20_SIZE) * TXDPD_SIZE;
				memcpy(&TxDpdResult.u4DPDG0_WF0_Prim, pAd->CalDPDAPart2Image + CalOffset, TXDPD_SIZE);
			}

			ShowDPDData(pAd, TxDpdResult);
		}
	}

	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			 ("raised E2P 0x52 = %x\n", doCal1));
exit:
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			 ("====================\n"));
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			 ("TX_SELF_TEST : [%s]\n",
			  (DPDPassOrFail == TRUE) ? "PASS" : "FAIL"));
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			 ("====================\n"));
	return TRUE;
}