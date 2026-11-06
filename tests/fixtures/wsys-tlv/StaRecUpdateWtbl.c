static INT32 StaRecUpdateWtbl(RTMP_ADAPTER *pAd, struct cmd_msg *msg, VOID *args)
{
	STA_REC_CFG_T		*pStaRecCfg = (STA_REC_CFG_T *)args;
	MAC_TABLE_ENTRY	*pEntry = pStaRecCfg->pEntry;
	P_CMD_STAREC_WTBL_T	pStarec_wtbl = NULL;
	BOOLEAN		IsBCMCWCID = FALSE;
	CMD_WTBL_GENERIC_T	rWtblGeneric = {0};	/* Tag = 0, Generic */
	CMD_WTBL_RX_T		rWtblRx = {0};		/* Tage = 1, Rx */
#ifdef DOT11_N_SUPPORT
	CMD_WTBL_HT_T		rWtblHt = {0};		/* Tag = 2, HT */
#ifdef DOT11_VHT_AC
	CMD_WTBL_VHT_T		rWtblVht = {0};		/* Tag = 3, VHT */
#endif /* DOT11_VHT_AC */
#endif /* DOT11_N_SUPPORT */
	CMD_WTBL_TX_PS_T	rWtblTxPs = {0};	/* Tag = 5, TxPs */
#if defined(HDR_TRANS_TX_SUPPORT) || defined(HDR_TRANS_RX_SUPPORT)
	CMD_WTBL_HDR_TRANS_T	rWtblHdrTrans = {0};	/* Tag = 6, Hdr Trans */
#endif /* HDR_TRANS_TX_SUPPORT */
	CMD_WTBL_RDG_T		rWtblRdg = {0};		/* Tag = 9, Rdg */
#ifdef TXBF_SUPPORT
	CMD_WTBL_BF_T           rWtblBf = {0};		/* Tag = 12, BF */
#endif /* TXBF_SUPPORT */
	CMD_WTBL_SMPS_T		rWtblSmPs = {0};	/* Tag = 13, SMPS */
	CMD_WTBL_SPE_T          rWtblSpe = {0};		/* Tag = 16, SPE */
	UCHAR		*pTlvBuffer = NULL;
	UCHAR		*pTempBuffer = NULL;
	UINT32		u4TotalTlvLen = 0;
	UCHAR		ucTotalTlvNumber = 0;
	NDIS_STATUS	Status = NDIS_STATUS_SUCCESS;
	P_CMD_WTBL_UPDATE_T	pCmdWtblUpdate = NULL;
	/* Allocate TLV msg */
	Status = os_alloc_mem(pAd, (UCHAR **)&pStarec_wtbl, sizeof(CMD_STAREC_WTBL_T));
	os_zero_mem(pStarec_wtbl, sizeof(CMD_STAREC_WTBL_T));
	if (pStarec_wtbl == NULL)
		return -1;

	pStarec_wtbl->u2Tag = cpu2le16(STA_REC_WTBL);
	pStarec_wtbl->u2Length = cpu2le16(sizeof(CMD_STAREC_WTBL_T));

	if (pStaRecCfg->ConnectionType == CONNECTION_INFRA_BC)
		IsBCMCWCID = TRUE;

	/* Tag = 1 */
	rWtblRx.ucRv = 1;
	rWtblRx.ucRca2 = 1;

	if (IsBCMCWCID) {
		/* Tag = 0 */
		rWtblGeneric.ucMUARIndex = 0x0e;

		os_move_mem(rWtblGeneric.aucPeerAddress, BROADCAST_ADDR, MAC_ADDR_LEN);

		//tmp solution to update STA mode AP address
		IF_DEV_CONFIG_OPMODE_ON_STA(pAd) {

			WIFI_SYS_INFO_T *pWifiSysInfo = &pAd->WifiSysInfo;
			WIFI_INFO_CLASS_T *pWifiClass = &pWifiSysInfo->BssInfo;
			BSS_INFO_ARGUMENT_T *pBssInfo = NULL;

			OS_SEM_LOCK(&pWifiSysInfo->lock);
			
			DlListForEach(pBssInfo, &pWifiClass->Head, BSS_INFO_ARGUMENT_T, list) {

				if (pBssInfo->ucBssIndex == pStaRecCfg->ucBssIndex){
					//Update to AP MAC when in STA mode
					os_move_mem(rWtblGeneric.aucPeerAddress, pBssInfo->Bssid, MAC_ADDR_LEN);
				}
			}

			OS_SEM_UNLOCK(&pWifiSysInfo->lock);
		}

		/* Tag = 1 */
		rWtblRx.ucRca1 = 1;
		/* Tag = 6 */
#ifdef HDR_TRANS_TX_SUPPORT

		if (pAd->OpMode == OPMODE_AP) {
			rWtblHdrTrans.ucFd = 1;
			rWtblHdrTrans.ucTd = 0;
		}

#endif
	} else {

		struct wifi_dev *wdev = NULL;

		if (pEntry == NULL){

			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("\n\nERROR%s: No MacEntry. widx=%d ConnTyp=0x%x feat=0x%x\n\n\n",
					  __func__, pStaRecCfg->ucWlanIdx, pStaRecCfg->ConnectionType, pStaRecCfg->u4EnableFeature));

			os_free_mem(pStarec_wtbl);

			return -1;
		}

		wdev = pEntry->wdev;
    
		/* Tag = 0 */
		//rWtblGeneric.ucMUARIndex = pEntry->wdev->OmacIdx;
		rWtblGeneric.ucQos = CLIENT_STATUS_TEST_FLAG(pEntry, fCLIENT_STATUS_WMM_CAPABLE) ? 1 : 0;
		rWtblGeneric.u2PartialAID = cpu2le16(pEntry->Aid);
		rWtblGeneric.ucMUARIndex = pStaRecCfg->MuarIdx;

		/* Tag = 0 */
		os_move_mem(rWtblGeneric.aucPeerAddress, pEntry->Addr, MAC_ADDR_LEN);

		if (CLIENT_STATUS_TEST_FLAG(pEntry, fCLIENT_STATUS_RDG_CAPABLE)
			&& CLIENT_STATUS_TEST_FLAG(pEntry, fCLIENT_STATUS_RALINK_CHIPSET))
			rWtblGeneric.ucAadOm = 1;

		/* Tag = 1 */
		if ((wdev->wdev_type == WDEV_TYPE_APCLI) ||
			(wdev->wdev_type == WDEV_TYPE_STA))
			rWtblRx.ucRca1 = 1;

#ifdef HDR_TRANS_TX_SUPPORT

		/* Tag = 6 */
		if (wdev->wdev_type == WDEV_TYPE_STA) {
			rWtblHdrTrans.ucFd = 0;
			rWtblHdrTrans.ucTd = 1;
		} else if (wdev->wdev_type == WDEV_TYPE_AP) {
			rWtblHdrTrans.ucFd = 1;
			rWtblHdrTrans.ucTd = 0;
		} else if (wdev->wdev_type == WDEV_TYPE_APCLI) {
			rWtblHdrTrans.ucFd = 0;
			rWtblHdrTrans.ucTd = 1;
		} else if (wdev->wdev_type == WDEV_TYPE_WDS) {
			rWtblHdrTrans.ucFd = 1;
			rWtblHdrTrans.ucTd = 1;
		} else
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s: Unknown wdev type(%d) do not support header translation\n",
					  __func__, pEntry->wdev->wdev_type));

#endif /* HDR_TRANS_TX_SUPPORT */
#ifdef HDR_TRANS_RX_SUPPORT

		if (IS_CIPHER_TKIP_Entry(pEntry))
			rWtblHdrTrans.ucDisRhtr = 1;
		else
			rWtblHdrTrans.ucDisRhtr = 0;

#endif /* HDR_TRANS_RX_SUPPORT */
#ifdef DOT11_N_SUPPORT

		if (IS_HT_STA(pEntry)) {
			/* Tag = 0 */
			rWtblGeneric.ucQos = 1;
			rWtblGeneric.ucBafEn = 0;

			/* Tag = 2 */
			rWtblHt.ucHt = 1;
			rWtblHt.ucMm = pEntry->MpduDensity;
			rWtblHt.ucAf = pEntry->MaxRAmpduFactor;

			if (CLIENT_STATUS_TEST_FLAG(pEntry, fCLIENT_STATUS_RDG_CAPABLE)) {
				/* Tga = 9 */
				rWtblRdg.ucR = 1;

				if (IS_MT7615(pAd) || IS_MT7622(pAd) || IS_P18(pAd) || IS_MT7663(pAd))
					rWtblRdg.ucRdgBa = 0;
				else
					rWtblRdg.ucRdgBa = 1;
			}

			/* Tag = 13*/
			if (pEntry->MmpsMode == MMPS_DYNAMIC)
				rWtblSmPs.ucSmPs = 1;
			else
				rWtblSmPs.ucSmPs = 0;

#ifdef DOT11_VHT_AC

			/* Tag = 3 */
			if (IS_VHT_STA(pEntry))
				rWtblVht.ucVht = 1;

#endif /* DOT11_VHT_AC */
		}

#endif /* DOT11_N_SUPPORT */
	}

	/* Tag = 5 */
	rWtblTxPs.ucTxPs = 0;
#ifdef TXBF_SUPPORT

	if (!IsBCMCWCID) {
		/* Tag = 0xc */
		rWtblBf.ucGid     = 0;
		rWtblBf.ucPFMUIdx = pAd->rStaRecBf.u2PfmuId;

		if (IS_HT_STA(pEntry)) {
			if (pAd->CommonCfg.RegTransmitSetting.field.ITxBfEn)
				rWtblBf.ucTiBf	  = (pEntry->rStaRecBf.fgETxBfCap > 0) ? FALSE : TRUE;
			else
				rWtblBf.ucTiBf	  = FALSE;

			if (pAd->CommonCfg.ETxBfEnCond)
				rWtblBf.ucTeBf	  = pEntry->rStaRecBf.fgETxBfCap;
			else
				rWtblBf.ucTeBf	  = FALSE;
		}

		if (IS_VHT_STA(pEntry)) {
			if (pAd->CommonCfg.RegTransmitSetting.field.ITxBfEn)
				rWtblBf.ucTibfVht = (pEntry->rStaRecBf.fgETxBfCap > 0) ? FALSE : TRUE;
			else
				rWtblBf.ucTibfVht = FALSE;

			if (pAd->CommonCfg.ETxBfEnCond)
				rWtblBf.ucTebfVht = pEntry->rStaRecBf.fgETxBfCap;
			else
				rWtblBf.ucTebfVht = FALSE;
		}
	}

#endif /* TXBF_SUPPORT */
	/* Tag = 0x10 */
	rWtblSpe.ucSpeIdx = 0;
	/* From WTBL COMMAND in STEREC TLV */
	pCmdWtblUpdate = (P_CMD_WTBL_UPDATE_T)&pStarec_wtbl->aucBuffer[0];
	pTlvBuffer = &pCmdWtblUpdate->aucBuffer[0];
	/* Append TLV msg */
	pTempBuffer = pTlvAppend(
					  pTlvBuffer,
					  (WTBL_GENERIC),
					  (sizeof(CMD_WTBL_GENERIC_T)),
					  &rWtblGeneric,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
	pTempBuffer = pTlvAppend(
					  pTempBuffer,
					  (WTBL_RX),
					  (sizeof(CMD_WTBL_RX_T)),
					  &rWtblRx,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
#ifdef DOT11_N_SUPPORT
	pTempBuffer = pTlvAppend(
					  pTempBuffer,
					  (WTBL_HT),
					  (sizeof(CMD_WTBL_HT_T)),
					  &rWtblHt,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
	pTempBuffer = pTlvAppend(
					  pTempBuffer,
					  (WTBL_RDG),
					  (sizeof(CMD_WTBL_RDG_T)),
					  &rWtblRdg,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
	pTempBuffer = pTlvAppend(
					  pTempBuffer,
					  (WTBL_SMPS),
					  (sizeof(CMD_WTBL_SMPS_T)),
					  &rWtblSmPs,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
#ifdef DOT11_VHT_AC
	pTempBuffer = pTlvAppend(
					  pTempBuffer,
					  (WTBL_VHT),
					  (sizeof(CMD_WTBL_VHT_T)),
					  &rWtblVht,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
#endif /* DOT11_VHT_AC */
#endif /* DOT11_N_SUPPORT */
	pTempBuffer = pTlvAppend(
					  pTempBuffer,
					  (WTBL_TX_PS),
					  (sizeof(CMD_WTBL_TX_PS_T)),
					  &rWtblTxPs,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
#if defined(HDR_TRANS_RX_SUPPORT) || defined(HDR_TRANS_TX_SUPPORT)
	pTempBuffer = pTlvAppend(
					  pTempBuffer,
					  (WTBL_HDR_TRANS),
					  (sizeof(CMD_WTBL_HDR_TRANS_T)),
					  &rWtblHdrTrans,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
#endif /* HDR_TRANS_RX_SUPPORT || HDR_TRANS_TX_SUPPORT */
#ifdef TXBF_SUPPORT

	if (pAd->rStaRecBf.u2PfmuId != 0xFFFF) {
		pTempBuffer = pTlvAppend(
						  pTempBuffer,
						  (WTBL_BF),
						  (sizeof(CMD_WTBL_BF_T)),
						  &rWtblBf,
						  &u4TotalTlvLen,
						  &ucTotalTlvNumber);
	}

#endif /* TXBF_SUPPORT */
	pTempBuffer = pTlvAppend(
					  pTempBuffer,
					  (WTBL_SPE),
					  (sizeof(CMD_WTBL_SPE_T)),
					  &rWtblSpe,
					  &u4TotalTlvLen,
					  &ucTotalTlvNumber);
	pCmdWtblUpdate->u2TotalElementNum = cpu2le16(ucTotalTlvNumber);
	pCmdWtblUpdate->ucWlanIdx = pStaRecCfg->ucWlanIdx;
	pCmdWtblUpdate->ucOperation = RESET_WTBL_AND_SET; /* In STAREC, currently reset and set only. */
	/* Append this feature */
	AndesAppendCmdMsg(msg, (char *)pStarec_wtbl, sizeof(CMD_STAREC_WTBL_T));
	os_free_mem(pStarec_wtbl);
	return 0;
}
