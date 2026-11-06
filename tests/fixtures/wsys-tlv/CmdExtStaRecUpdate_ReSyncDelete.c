static INT32 CmdExtStaRecUpdate_ReSyncDelete(
	RTMP_ADAPTER *pAd,
	STA_REC_CFG_T *pStaRecCfg)
{
	struct cmd_msg		*msg = NULL;
	CMD_STAREC_UPDATE_T	CmdStaRecUpdate = {0};
	INT32			Ret = 0;
	UINT16			u2TLVNumber = 0;
	UINT32			size;
	struct _CMD_ATTRIBUTE	attr = {0};
	STA_REC_CFG_T		StaRecCfgForDel = {0};

	StaRecCfgForDel.ucBssIndex = pStaRecCfg->ucBssIndex;
	StaRecCfgForDel.ucWlanIdx = pStaRecCfg->ucWlanIdx;
	StaRecCfgForDel.ConnectionState = STATE_DISCONNECT;
	StaRecCfgForDel.MuarIdx = pStaRecCfg->MuarIdx;
	StaRecCfgForDel.ConnectionType = pStaRecCfg->ConnectionType;
	StaRecCfgForDel.u4EnableFeature = STA_REC_BASIC_STA_RECORD;
	StaRecCfgForDel.pEntry = pStaRecCfg->pEntry;
	size = sizeof(CMD_STAREC_UPDATE_T);
	size += StaRecHandle[STA_REC_BASIC_STA_RECORD].StaRecTagLen;
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
	CmdStaRecUpdate.ucBssIndex = StaRecCfgForDel.ucBssIndex;
	CmdStaRecUpdate.ucWlanIdx = StaRecCfgForDel.ucWlanIdx;
	CmdStaRecUpdate.ucMuarIdx = StaRecCfgForDel.MuarIdx;
	Ret = StaRecHandle[STA_REC_BASIC_STA_RECORD].StaRecTagHandler(pAd, msg, &StaRecCfgForDel);

	if (Ret == NDIS_STATUS_SUCCESS)
		u2TLVNumber++;

	/*insert to head*/
	CmdStaRecUpdate.u2TotalElementNum = cpu2le16(u2TLVNumber);
	CmdStaRecUpdate.ucAppendCmdTLV = TRUE;
#ifdef RT_BIG_ENDIAN
	StaRecCfgForDel.u4EnableFeature = cpu2le32(StaRecCfgForDel.u4EnableFeature);
#endif
	AndesAppendHeadCmdMsg(msg, (char *)&CmdStaRecUpdate,
						  sizeof(CMD_STAREC_UPDATE_T));
	/* Send out CMD */
	Ret = AndesSendCmdMsg(pAd, msg);
error:
	return Ret;
}
