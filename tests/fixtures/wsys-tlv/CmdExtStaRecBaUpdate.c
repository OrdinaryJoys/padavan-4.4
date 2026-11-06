INT32 CmdExtStaRecBaUpdate(
	struct _RTMP_ADAPTER *pAd,
	STA_REC_BA_CFG_T StaRecBaCfg)
{
	struct _CMD_ATTRIBUTE attr = {0};
	struct cmd_msg *msg = NULL;
	CMD_STAREC_UPDATE_T CmdStaRecUpdate = {0};
	CMD_STAREC_BA_T CmdStaRecBa;
	UINT32 MsgLen;
	INT32 Ret = 0;
	UINT16 ucTLVNumber = 0;

	MsgLen = sizeof(CMD_STAREC_UPDATE_T) + sizeof(CMD_STAREC_BA_T);
	msg = AndesAllocCmdMsg(pAd, MsgLen);

	if (!msg) {
		Ret = NDIS_STATUS_RESOURCES;
		goto error;
	}

	/* Get number of TLV*/
	ucTLVNumber = 1;
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s: ucTLVNumber(%d)\n", __func__, ucTLVNumber));
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
	CmdStaRecUpdate.ucBssIndex = StaRecBaCfg.BssIdx;
	CmdStaRecUpdate.ucWlanIdx = StaRecBaCfg.WlanIdx;
	CmdStaRecUpdate.ucMuarIdx = StaRecBaCfg.MuarIdx;
	CmdStaRecUpdate.u2TotalElementNum = cpu2le16(ucTLVNumber);
	CmdStaRecUpdate.ucAppendCmdTLV = TRUE;
	AndesAppendCmdMsg(msg, (char *)&CmdStaRecUpdate, sizeof(CMD_STAREC_UPDATE_T));
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s: StaRecUpdate:\n", __func__));
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s: ucBssIndex=%d, ucWlanIdx=%d, ucMuarIdx=%d, u2TotalElementNum=%d\n",
			  __func__, CmdStaRecUpdate.ucBssIndex, CmdStaRecUpdate.ucWlanIdx, CmdStaRecUpdate.ucMuarIdx, CmdStaRecUpdate.u2TotalElementNum));
	/* Fill BA related parameters */
	NdisZeroMemory(&CmdStaRecBa, sizeof(CMD_STAREC_BA_T));

	if (StaRecBaCfg.baDirection == ORI_BA) {
		BA_ORI_ENTRY *pBAEntry = (BA_ORI_ENTRY *)StaRecBaCfg.BaEntry;

		CmdStaRecBa.ucAmsduCap = pBAEntry->amsdu_cap;
		CmdStaRecBa.u2BaStartSeq = cpu2le16(pBAEntry->Sequence);
		CmdStaRecBa.u2BaWinSize = cpu2le16(pBAEntry->BAWinSize);
	} else if (StaRecBaCfg.baDirection == RCV_BA) {
		BA_REC_ENTRY *pBAEntry = (BA_REC_ENTRY *)StaRecBaCfg.BaEntry;

		CmdStaRecBa.u2BaStartSeq = cpu2le16(pBAEntry->LastIndSeq);
		CmdStaRecBa.u2BaWinSize = cpu2le16(pBAEntry->BAWinSize);
	} else {
		MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				 ("%s:Invalid BaDirection (baDirection = %d)\n", __func__, StaRecBaCfg.baDirection));
		return Ret;
	}

	CmdStaRecBa.ucBaEenable = StaRecBaCfg.BaEnable;
	CmdStaRecBa.u2Tag = STA_REC_BA;
	CmdStaRecBa.u2Length = sizeof(CMD_STAREC_BA_T);
	CmdStaRecBa.ucTid = StaRecBaCfg.tid;
	CmdStaRecBa.ucBaDirection = StaRecBaCfg.baDirection;
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s: BaInfo:\n", __func__));
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s: u2Tag=%d, u2Length=%d, ucTid=%d, u2BaDirectin=%d, BaEnable=%d, u2BaStartSeq=%d, u2BaWinSize=%d, ucAmsduCap=%d\n",
			  __func__,	CmdStaRecBa.u2Tag, CmdStaRecBa.u2Length, CmdStaRecBa.ucTid, CmdStaRecBa.ucBaDirection,
			  CmdStaRecBa.ucBaEenable, le2cpu16(CmdStaRecBa.u2BaStartSeq), le2cpu16(CmdStaRecBa.u2BaWinSize), CmdStaRecBa.ucAmsduCap));
#ifdef RT_BIG_ENDIAN
	CmdStaRecBa.u2Tag = cpu2le16(CmdStaRecBa.u2Tag);
	CmdStaRecBa.u2Length = cpu2le16(CmdStaRecBa.u2Length);
#endif
	/* Append this feature */
	AndesAppendCmdMsg(msg, (char *)&CmdStaRecBa, sizeof(CMD_STAREC_BA_T));
	/* Send out CMD */
	Ret = AndesSendCmdMsg(pAd, msg);
error:
	MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s:(Ret = %d)\n", __func__, Ret));
	return Ret;
}
