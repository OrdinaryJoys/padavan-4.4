INT32 CmdExtWtblUpdate(RTMP_ADAPTER *pAd, UINT8 ucWlanIdx, UINT8 ucOperation,
					   VOID *pBuffer, UINT32 u4BufferLen)
{
	struct cmd_msg			*msg = NULL;
	CMD_WTBL_UPDATE_T	CmdWtblUpdate = {0};
	INT32					Ret = 0;
	UINT32					u4EnableFeature = 0;
	UINT16					ucTLVNumber = 0;
	UINT16					u2Len = 0;
	UINT32					*pRspPayload = NULL;
	P_CMD_WTBL_GENERIC_TLV_T	pWtblGenericTlv = NULL;
	UINT8					ucRemainingTLVNumber = 0;
	UINT32					u4RemainingTLVBufLen = 0;
	PUCHAR					TempBuffer = (PUCHAR)pBuffer;
	struct _CMD_ATTRIBUTE attr = {0};

	msg = AndesAllocCmdMsg(pAd, MAX_BUF_SIZE_OF_WTBL_INFO + 100);

	if (!msg) {
		Ret = NDIS_STATUS_RESOURCES;
		goto Error0;
	}

	/* Get TVL number from TLV buffer*/
	u4RemainingTLVBufLen = u4BufferLen;

	while (u4RemainingTLVBufLen > 0) {
		pWtblGenericTlv = (P_CMD_WTBL_GENERIC_TLV_T)TempBuffer;

		if (pWtblGenericTlv == NULL) {
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s, pWtblGenericTlv is NULL\n", __func__));
			Ret = NDIS_STATUS_INVALID_DATA;
			break;
		} else if (pWtblGenericTlv->u2Length == 0) {
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s, fail to handle T(%d), L(%d)\n", __func__,
					  pWtblGenericTlv->u2Tag, pWtblGenericTlv->u2Length));
			Ret = NDIS_STATUS_INVALID_DATA;
			break;
		}

		u4EnableFeature |= (1 << (pWtblGenericTlv->u2Tag));
		TempBuffer += pWtblGenericTlv->u2Length;
		u4RemainingTLVBufLen -= pWtblGenericTlv->u2Length;
		ucTLVNumber++;
	}

	if (Ret != 0)
		goto Error1;

	MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s, ucTLVNumber = %d\n", __func__, ucTLVNumber));
	/* Assign vlaue to related parameters */
	TempBuffer = (PUCHAR)pBuffer;
	ucRemainingTLVNumber = ucTLVNumber;
	u4RemainingTLVBufLen = u4BufferLen;

	/* Set correct length and RspPayload buffer with different operation */
	if (ucOperation == RESET_WTBL_AND_SET) {
		if (pBuffer != NULL) {
			/* Reset a specific WCID and set WTBL TLV */
			u2Len = 8;
			pRspPayload = NULL;
		} else if (u4RemainingTLVBufLen == 0) { /* NULL */
			/* Reset a specific WCID only */
			u2Len = 8;
			pRspPayload = NULL;
		}
	} else if (ucOperation == SET_WTBL) {
		if (pBuffer != NULL) {
			u2Len = 8;
			pRspPayload = NULL;
		} else
			return NDIS_STATUS_FAILURE;
	} else if (ucOperation == QUERY_WTBL) {
		if (pBuffer != NULL) {
			u2Len = u4BufferLen + 20 + sizeof(CMD_WTBL_UPDATE_T);
			pRspPayload = (UINT32 *)pBuffer;
		} else
			return NDIS_STATUS_FAILURE;
	} else if (ucOperation == RESET_ALL_WTBL) {
		if (pBuffer == NULL && u4RemainingTLVBufLen == 0) {
			u2Len = 8;
			pRspPayload = NULL;
		} else
			return NDIS_STATUS_FAILURE;
	} else {
		/* Error */
		return NDIS_STATUS_FAILURE;
	}

	SET_CMD_ATTR_MCU_DEST(attr, HOST2N9);
	SET_CMD_ATTR_TYPE(attr, EXT_CID);
	SET_CMD_ATTR_EXT_TYPE(attr, EXT_CMD_ID_WTBL_UPDATE);
	SET_CMD_ATTR_CTRL_FLAGS(attr, INIT_CMD_SET_AND_WAIT_RETRY_RSP);
	SET_CMD_ATTR_RSP_WAIT_MS_TIME(attr, 0);
	SET_CMD_ATTR_RSP_EXPECT_SIZE(attr, u2Len);
	SET_CMD_ATTR_RSP_WB_BUF_IN_CALBK(attr, pRspPayload);
	SET_CMD_ATTR_RSP_HANDLER(attr, CmdExtWtblUpdateCb);
	AndesInitCmdMsg(msg, attr);
	CmdWtblUpdate.ucWlanIdx = ucWlanIdx;
	CmdWtblUpdate.ucOperation = ucOperation;
	CmdWtblUpdate.u2TotalElementNum = cpu2le16(ucTLVNumber);
	AndesAppendCmdMsg(msg, (char *)&CmdWtblUpdate, sizeof(CMD_WTBL_UPDATE_T));
	MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s, ucWlanIdx = %d, ucOperation = %d, u4EnableFeature = 0x%x\n",
			  __func__, ucWlanIdx, ucOperation, u4EnableFeature));
	MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s, ucRemainingTLVNumber = %d, u2RemainingTLVBufLen = %d\n",
			  __func__, ucRemainingTLVNumber, u4RemainingTLVBufLen));

	/* Handle TVL request here */
	while ((ucRemainingTLVNumber > 0) && (u4RemainingTLVBufLen > 0)) {
		/* Get current TLV */
		pWtblGenericTlv = (P_CMD_WTBL_GENERIC_TLV_T)TempBuffer;
		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
				 ("%s, TLV(%d, %d)\n", __func__,
				  pWtblGenericTlv->u2Tag, pWtblGenericTlv->u2Length));

		/* Handle this TLV */
		switch (pWtblGenericTlv->u2Tag) {
		/* Tag = 0 */
		case WTBL_GENERIC: {
			P_CMD_WTBL_GENERIC_T pCmdWtblGeneric =
				(P_CMD_WTBL_GENERIC_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_GENERIC), ucMUARIndex = %d, ucSkipTx = %d,ucCfAck = %d, ucQos = %d, ucQos = %d, ucAdm = %d, PartialAID = %d, aucPeerAddress(%02x:%02x:%02x:%02x:%02x:%02x)\n",
						  __func__,
						  pCmdWtblGeneric->ucMUARIndex,
						  pCmdWtblGeneric->ucSkipTx,
						  pCmdWtblGeneric->ucCfAck,
						  pCmdWtblGeneric->ucQos,
						  pCmdWtblGeneric->ucMesh,
						  pCmdWtblGeneric->ucAdm,
						  pCmdWtblGeneric->u2PartialAID,
						  PRINT_MAC(pCmdWtblGeneric->aucPeerAddress)));
#ifdef RT_BIG_ENDIAN
				pCmdWtblGeneric->u2PartialAID = cpu2le16(pCmdWtblGeneric->u2PartialAID);
#endif
			} else if (ucOperation == QUERY_WTBL) {
				/* No need to fill real parameters when query and
				  *	just append all zero data buffer to msg
				  */
			}

			break;
		}

		/* Tag = 1 */
		case WTBL_RX: {
			P_CMD_WTBL_RX_T	pCmdWtblRx = (P_CMD_WTBL_RX_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_RX), ucRcid = %d, ucRca1 = %d, ucRca2 = %d, ucRv = %d\n",
						  __func__,
						  pCmdWtblRx->ucRcid,
						  pCmdWtblRx->ucRca1,
						  pCmdWtblRx->ucRca2,
						  pCmdWtblRx->ucRv));
			}

			break;
		}

		/* Tag = 2 */
		case WTBL_HT: {
			P_CMD_WTBL_HT_T pCmdWtblHt = (P_CMD_WTBL_HT_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_HT), ucHt = %d, ucLdpc = %d, ucAf = %d, ucMm = %d\n",
						  __func__,
						  pCmdWtblHt->ucHt,
						  pCmdWtblHt->ucLdpc,
						  pCmdWtblHt->ucAf,
						  pCmdWtblHt->ucMm));
			}

			break;
		}

		/* Tag = 3 */
		case WTBL_VHT: {
			P_CMD_WTBL_VHT_T pCmdWtblVht = (P_CMD_WTBL_VHT_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_VHT), ucLdpcVht = %d, ucDynBw= %d, ucVht = %d, ucTxopPsCap = %d\n",
						  __func__,
						  pCmdWtblVht->ucLdpcVht,
						  pCmdWtblVht->ucDynBw,
						  pCmdWtblVht->ucVht,
						  pCmdWtblVht->ucTxopPsCap));
			}

			break;
		}

		/* Tag = 4 */
		case WTBL_PEER_PS: {
			P_CMD_WTBL_PEER_PS_T pCmdWtblPerPs =
				(P_CMD_WTBL_PEER_PS_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_PEER_PS), ucDuIPsm = %d, ucIPsm = %d\n",
						  __func__,
						  pCmdWtblPerPs->ucDuIPsm,
						  pCmdWtblPerPs->ucIPsm));
			}

			break;
		}

		/* Tag = 5 */
		case WTBL_TX_PS: {
			P_CMD_WTBL_TX_PS_T	pCmdWtbTxPs = (P_CMD_WTBL_TX_PS_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_TX_PS), ucTxPs = %d\n",
						  __func__,
						  pCmdWtbTxPs->ucTxPs));
			}

			break;
		}

		/* Tag = 6 */
		case WTBL_HDR_TRANS: {
			P_CMD_WTBL_HDR_TRANS_T	pCmdWtblHdrTrans =
				(P_CMD_WTBL_HDR_TRANS_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_HDR_TRANS), ucTd = %d, ucFd = %d, ucDisRhtr =%d\n",
						  __func__,
						  pCmdWtblHdrTrans->ucTd,
						  pCmdWtblHdrTrans->ucFd,
						  pCmdWtblHdrTrans->ucDisRhtr));
			}

			break;
		}

		/* Tag = 7 */
		case WTBL_SECURITY_KEY: {
			P_CMD_WTBL_SECURITY_KEY_T pCmdWtblSecurityKey =
				(P_CMD_WTBL_SECURITY_KEY_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_SECURITY_KEY), ucAddRemove = %d, ucRkv = %d, ucIkv =%d, ucAlgorithmId = %d, ucKeyId = %d, ucKeyLen = %d\n",
						  __func__,
						  pCmdWtblSecurityKey->ucAddRemove,
						  pCmdWtblSecurityKey->ucRkv,
						  pCmdWtblSecurityKey->ucIkv,
						  pCmdWtblSecurityKey->ucAlgorithmId,
						  pCmdWtblSecurityKey->ucKeyId,
						  pCmdWtblSecurityKey->ucKeyLen));
			}

			break;
		}

		/* Tag = 8 */
		case WTBL_BA: {
			P_CMD_WTBL_BA_T pCmdWtblBa = (P_CMD_WTBL_BA_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				if (pCmdWtblBa->ucBaSessionType == BA_SESSION_RECP) {
					/* Recipient */
					MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
							 ("%s(WTBL_BA, Recipient), ucTid(%d), ucBaSessionType(%d), ucRstBaTid(%d), ucRstBaSel(%d), ucStartRstBaSb(%d), aucPeerAddress(%02x:%02x:%02x:%02x:%02x:%02x)\n",
							  __func__,
							  pCmdWtblBa->ucTid,
							  pCmdWtblBa->ucBaSessionType,
							  pCmdWtblBa->ucRstBaTid,
							  pCmdWtblBa->ucRstBaSel,
							  pCmdWtblBa->ucStartRstBaSb,
							  PRINT_MAC(pCmdWtblBa->aucPeerAddress)));
				} else {
					/* Originator */
					MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
							 ("%s(WTBL_BA, Originator), ucTid(%d), u2Sn(%d), ucBaEn(%d), ucBaSize(%d)\n",
							  __func__,
							  pCmdWtblBa->ucTid,
							  pCmdWtblBa->u2Sn,
							  pCmdWtblBa->ucBaEn,
							  pCmdWtblBa->ucBaSize));
				}
			}
#ifdef RT_BIG_ENDIAN
			pCmdWtblBa->u2Sn = cpu2le16(pCmdWtblBa->u2Sn);
#endif

			break;
		}

		/* Tag = 9 */
		case WTBL_RDG: {
			P_CMD_WTBL_RDG_T	pCmdWtblRdg = (P_CMD_WTBL_RDG_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_RDG), ucRdgBa = %d, ucR = %d\n",
						  __func__,
						  pCmdWtblRdg->ucRdgBa,
						  pCmdWtblRdg->ucR));
			}

			break;
		}

		/* Tag = 10 */
		case WTBL_PROTECTION: {
			P_CMD_WTBL_PROTECTION_T	pCmdWtblProtection =
				(P_CMD_WTBL_PROTECTION_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_PROTECTION), ucRts = %d\n",
						  __func__,
						  pCmdWtblProtection->ucRts));
			}

			break;
		}

		/* Tag = 11 */
		case WTBL_CLEAR: {
			/* bit 0: Clear PSM (WF_WTBLON: 0x60322300, Bit 31 set 1 then set 0) */
			/* bit 1: Clear BA (WTBL2.DW15) */
			/* bit 2: Clear Rx Counter (6019_00002, bit 14) */
			/* bit 3: Clear Tx Counter (6019_0000, bit 15) */
			/* bit 4: Clear ADM Counter (6019_0000, bit 12) */
			/* bit 5: Clear Cipher key (WTBL3)*/
			P_CMD_WTBL_CLEAR_T	pCmdWtblClear = (P_CMD_WTBL_CLEAR_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_CLEAR), ucClear = %x\n",
						  __func__,
						  pCmdWtblClear->ucClear));
			}

			break;
		}

		/* Tag = 12 */
		case WTBL_BF: {
			P_CMD_WTBL_BF_T		pCmdWtblBf = (P_CMD_WTBL_BF_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO, ("%s(WTBL_BF), ucTiBf = %d, ucTeBf = %d, ucTibfVh = %d, ucTebfVht = %d, ucGid = %d, ucPfmuIdx = %d\n",
						 __func__,
						 pCmdWtblBf->ucTiBf,
						 pCmdWtblBf->ucTeBf,
						 pCmdWtblBf->ucTibfVht,
						 pCmdWtblBf->ucTebfVht,
						 pCmdWtblBf->ucGid,
						 pCmdWtblBf->ucPFMUIdx));
			}

			break;
		}

		/* Tag = 13 */
		case WTBL_SMPS: {
			P_CMD_WTBL_SMPS_T pCmdWtblSmPs = (P_CMD_WTBL_SMPS_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_SMPS), ucSmPs = %d\n",
						  __func__,
						  pCmdWtblSmPs->ucSmPs));
			}

			break;
		}

		/* Tag = 14 */
		case WTBL_RAW_DATA_RW: {
			P_CMD_WTBL_RAW_DATA_RW_T pCmdWtblRawDataRw =
				(P_CMD_WTBL_RAW_DATA_RW_T)TempBuffer;
			/* Print argumrnts */
			MTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_INFO,
					 ("%s(WTBL_RAW_DATA_RW), ucWtblIdx = %d, ucWhichDW = %d, u4DwMask = 0x%x, u4DwValue = 0x%x\n",
					  __func__,
					  pCmdWtblRawDataRw->ucWtblIdx,
					  pCmdWtblRawDataRw->ucWhichDW,
					  pCmdWtblRawDataRw->u4DwMask,
					  pCmdWtblRawDataRw->u4DwValue));
#ifdef RT_BIG_ENDIAN
			pCmdWtblRawDataRw->u4DwMask = cpu2le32(pCmdWtblRawDataRw->u4DwMask);
			pCmdWtblRawDataRw->u4DwValue = cpu2le32(pCmdWtblRawDataRw->u4DwValue);
#endif
			break;
		}

		/* Tag = 15 */
		case WTBL_DUMP: {
			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
						 ("%s(WTBL_DUMP), WTBL_BUFFER_SIZE = %d\n",
						  __func__,
						  WTBL_BUFFER_SIZE));
				/* Fill value  format */
				/* No need to fill this argument */
			}

			break;
		}

		/* Tag = 16 */
		case WTBL_SPE: {
			P_CMD_WTBL_SPE_T		pCmdWtblSpe = (P_CMD_WTBL_SPE_T)TempBuffer;

			if ((ucOperation == RESET_WTBL_AND_SET) || (ucOperation == SET_WTBL)) {
				/* Print argumrnts */
				MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO, ("%s(WTBL_BF), ucSpeIdx = %d\n",
						 __func__,
						 pCmdWtblSpe->ucSpeIdx));
			}

			break;
		}

		default: {
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
					 ("%s, Unknown WTBL TLV Tag(%d)\n",
					  __func__, pWtblGenericTlv->u2Tag));
			break;
		}
		}

		/* Advance to next TLV */
		TempBuffer += pWtblGenericTlv->u2Length;
		u4RemainingTLVBufLen -= pWtblGenericTlv->u2Length;
		ucRemainingTLVNumber--;
#ifdef RT_BIG_ENDIAN
		pWtblGenericTlv->u2Length = cpu2le16(pWtblGenericTlv->u2Length);
		pWtblGenericTlv->u2Tag = cpu2le16(pWtblGenericTlv->u2Tag);
#endif
		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
				 ("%s in while loop, ucRemainingTLVNumber = %d, u2RemainingTLVBufLen = %d\n",
				  __func__,
				  ucRemainingTLVNumber, u4RemainingTLVBufLen));
	}

	AndesAppendCmdMsg(msg, (PUCHAR)pBuffer, u4BufferLen);
	/* Send out CMD */
	Ret = AndesSendCmdMsg(pAd, msg);
	goto Success;
Error1:

	if (msg)
		AndesFreeCmdMsg(msg);

	MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
			 ("%s:(Ret = %d)\n", __func__, Ret));
	return Ret;
Success:
Error0:
	MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
			 ("%s:(Ret = %d)\n", __func__, Ret));
	return Ret;
}
