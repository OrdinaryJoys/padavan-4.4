static VOID CmdExtWtblUpdateCb(struct cmd_msg *msg, char *data, UINT16 len)
{
	struct _EVENT_EXT_CMD_RESULT_T *EventExtCmdResult =
		(struct _EVENT_EXT_CMD_RESULT_T *)data;
	UINT32	u4Len = len - 20 - sizeof(CMD_WTBL_UPDATE_T);
	PUCHAR	pData = (PCHAR)(data + 20 + sizeof(CMD_WTBL_UPDATE_T));
	PUCHAR	pRspPayload = (PUCHAR)msg->attr.rsp.wb_buf_in_calbk;

	if (pRspPayload == NULL) {
		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
				 ("%s: EventExtCmdResult.ucExTenCID = 0x%x\n",
				  __func__, EventExtCmdResult->ucExTenCID));
		EventExtCmdResult->u4Status = le2cpu32(EventExtCmdResult->u4Status);
		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
				 ("%s: EventExtCmdResult.u4Status = 0x%x\n",
				  __func__, EventExtCmdResult->u4Status));
	} else {
		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
				 ("%s: Copy query result to buffer\n", __func__));
		os_move_mem(pRspPayload, pData, u4Len);
	}
}
