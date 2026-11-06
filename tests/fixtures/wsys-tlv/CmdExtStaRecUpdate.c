INT32 CmdExtStaRecUpdate(
	RTMP_ADAPTER *pAd,
	STA_REC_CFG_T StaRecCfg)
{
	struct cmd_msg			*msg = NULL;
	CMD_STAREC_UPDATE_T	    CmdStaRecUpdate = {0};
	INT32					Ret = 0;
	UINT8					i = 0;
	UINT16					u2TLVNumber;
	UINT32					size;
	UCHAR StaRecSupprotNum = sizeof(StaRecHandle) / sizeof(STAREC_HANDLE_T);
	struct _CMD_ATTRIBUTE attr = {0};
	UINT8 retry = STAREC_RETRY;
CmdExtStaRecUpdate_restart:
	u2TLVNumber = 0;
	size = sizeof(CMD_STAREC_UPDATE_T);

	/* Get number of TLV*/
	for (i = 0; i < StaRecSupprotNum; i++) {
		if (StaRecCfg.u4EnableFeature & (1 << StaRecHandle[i].StaRecTag))
			size += StaRecHandle[i].StaRecTagLen;
	}

	msg = AndesAllocCmdMsg(pAd, size);

	if (!msg) {
		Ret = NDIS_STATUS_RESOURCES;
		goto error;
	}

	SET_CMD_ATTR_MCU_DEST(attr, HOST2N9);
	SET_CMD_ATTR_TYPE(attr, EXT_CID);
	SET_CMD_ATTR_EXT_TYPE(attr, EXT_CMD_STAREC_UPDATE);
	SET_CMD_ATTR_CTRL_FLAGS(attr, INIT_LEN_VAR_CMD_SET_AND_WAIT_RETRY_RSP);
	SET_CMD_ATTR_RSP_WAIT_MS_TIME(attr, 0);
	SET_CMD_ATTR_RSP_EXPECT_SIZE(attr, sizeof(EVENT_STAREC_UPDATE_T));
	SET_CMD_ATTR_RSP_WB_BUF_IN_CALBK(attr, NULL);
	SET_CMD_ATTR_RSP_HANDLER(attr, CmdExtStaRecUpdateRsp);
	AndesInitCmdMsg(msg, attr);
	/* Fill WLAN related header here*/
	CmdStaRecUpdate.ucBssIndex = StaRecCfg.ucBssIndex;
	CmdStaRecUpdate.ucWlanIdx = StaRecCfg.ucWlanIdx;
	CmdStaRecUpdate.ucMuarIdx = StaRecCfg.MuarIdx;

	/* Fill RA related parameters */

	for (i = 0; i < StaRecSupprotNum; i++) {
		if ((StaRecCfg.u4EnableFeature & (1 << StaRecHandle[i].StaRecTag))) {
			if (StaRecHandle[i].StaRecTagHandler != NULL) {
				Ret = StaRecHandle[i].StaRecTagHandler(pAd, msg, &StaRecCfg);

				if (Ret == 0)
					u2TLVNumber++;
			} else {
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s: StaRecTag = %d no corresponding function handler.\n",
						  __func__, StaRecHandle[i].StaRecTag));
			}
		}
	}

	MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s: u2TLVNumber(%d)\n", __func__, u2TLVNumber));
	/*insert to head*/
	CmdStaRecUpdate.u2TotalElementNum = cpu2le16(u2TLVNumber);
	CmdStaRecUpdate.ucAppendCmdTLV = TRUE;
	AndesAppendHeadCmdMsg(msg, (char *)&CmdStaRecUpdate,
						  sizeof(CMD_STAREC_UPDATE_T));
	/* Send out CMD */
	Ret = AndesSendCmdMsg(pAd, msg);

	while ((Ret != WLAN_STATUS_SUCCESS) && (retry)) {
		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_WARN,
				 ("%s:(FW Ret = 0x%x retry=%d)\n", __func__, Ret, retry));
		retry--;
		/* something wrong with STAREC update */
		Ret = CmdExtStaRecUpdate_ReSyncDelete(pAd, &StaRecCfg);

		if (Ret != WLAN_STATUS_SUCCESS)
			continue;

		goto CmdExtStaRecUpdate_restart;
	}

error:
	MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s:(Ret = %d)\n", __func__, Ret));
	return Ret;
}
