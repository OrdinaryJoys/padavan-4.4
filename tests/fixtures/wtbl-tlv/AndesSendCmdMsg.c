INT32 AndesSendCmdMsg(PRTMP_ADAPTER ad, struct cmd_msg *msg)
{
	struct MCU_CTRL *ctl = &ad->MCUCtrl;
	BOOLEAN is_cmd_need_wait = IS_CMD_MSG_NEED_SYNC_WITH_FW_FLAG_SET(msg);
	int ret = NDIS_STATUS_SUCCESS;
#ifdef CONFIG_RECOVERY_ON_INTERRUPT_MISS
#ifdef INTELP6_SUPPORT
	struct _RTMP_CHIP_OP *ops = hc_get_chip_ops(ad->hdev_ctrl);
#endif
#endif

	/* These Wsys commands require an explicit valid firmware acknowledgement. */
	if (msg->attr.ext_type == EXT_CMD_STAREC_UPDATE ||
		msg->attr.ext_type == EXT_CMD_ID_DEVINFO_UPDATE ||
		msg->attr.ext_type == EXT_CMD_ID_BSSINFO_UPDATE)
		msg->cmd_return_status = NDIS_STATUS_FAILURE;

	/* The send API consumes an unqueued message on every admission failure. */
	if (RtmpDmaStopping(ad)) {
		AndesForceFreeCmdMsg(msg);
		return NDIS_STATUS_FAILURE;
	}
	if (in_interrupt() && IS_CMD_MSG_NEED_SYNC_WITH_FW_FLAG_SET(msg)) {
		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				 ("BUG: %s is called from invalid context\n",
				  __func__));
		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				 ("%s: Command type = %x, Extension command type = %x\n",
				  __func__, msg->attr.type, msg->attr.ext_type));
		AndesForceFreeCmdMsg(msg);
		return NDIS_STATUS_FAILURE;
	}

	if (!RTMP_TEST_FLAG(ad, fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD)     ||
		RTMP_TEST_FLAG(ad, fRTMP_ADAPTER_NIC_NOT_EXIST)         ||
		RTMP_TEST_FLAG(ad, fRTMP_ADAPTER_SUSPEND)) {
		if (!RTMP_TEST_FLAG(ad, fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD)) {
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s: Could not send in band command due to diablefRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD\n",
					  __func__));
		} else if (RTMP_TEST_FLAG(ad, fRTMP_ADAPTER_NIC_NOT_EXIST)) {
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s: Could not send in band command due to fRTMP_ADAPTER_NIC_NOT_EXIST\n",
					  __func__));
		} else if (RTMP_TEST_FLAG(ad, fRTMP_ADAPTER_SUSPEND)) {
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s: Could not send in band command due to fRTMP_ADAPTER_SUSPEND\n",
					  __func__));
		}

		MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				 ("%s: Command type = %x, Extension command type = %x\n",
				  __func__, msg->attr.type, msg->attr.ext_type));

		AndesForceFreeCmdMsg(msg);
		return NDIS_STATUS_FAILURE;
	}

#ifdef DBG_STARVATION
	starv_dbg_init(&ctl->block, &msg->starv);
	starv_dbg_get(&msg->starv);
#endif /*DBG_STARVATION*/
	AndesQueueTailCmdMsg(&ctl->txq, msg, tx_start);
retransmit:

	/* The caller kicks only its own queued message.  Synchronous failures
	 * complete its waiting object; an error after publication retains the
	 * ack/ring owner until completion or controller cleanup.
	 */
	ret = AndesDequeueAndKickOutCmdMsgs(ad, msg);

	/* Wait for response */
	if (is_cmd_need_wait) {
		enum cmd_msg_state state = 0;
		ULONG IsComplete;

		IsComplete = AndesWaitForCompleteTimeout(msg, msg->attr.ctrl.wait_ms_time);

		if (!OS_TEST_BIT(MCU_INIT, &ctl->flags)) {
			/*If need wait, clean up will trigger complete for here to free msg*/
			ret = NDIS_STATUS_FAILURE;
			if (msg->state == tx_kickout_fail)
				AndesForceFreeCmdMsg(msg);
			else {
				AndesTakeQueuedCmdMsg(ctl, &ctl->ackq, msg);
				AndesFreeCmdMsg(msg);
			}
			goto bailout;
		}

		if (!IsComplete) {
			ret = NDIS_STATUS_FAILURE;
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("FWCmdTimeout: command (%x), ext_cmd_type (%x), seq(%d), timeout(%dms)\n",
					  msg->attr.type, msg->attr.ext_type,
					  msg->seq,
					  (msg->attr.ctrl.wait_ms_time == 0) ?
					  CMD_MSG_TIMEOUT : msg->attr.ctrl.wait_ms_time));
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("pAd->Flags  = 0x%.8lx\n", ad->Flags));
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("txq qlen = %d\n", AndesQueueLen(ctl, &ctl->txq)));
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("rxq qlen = %d\n", AndesQueueLen(ctl, &ctl->rxq)));
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("kickq qlen = %d\n", AndesQueueLen(ctl, &ctl->kickq)));
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("ackq qlen = %d\n", AndesQueueLen(ctl, &ctl->ackq)));
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("tx_doneq.qlen = %d\n", AndesQueueLen(ctl, &ctl->tx_doneq)));
			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("rx_done qlen = %d\n", AndesQueueLen(ctl, &ctl->rx_doneq)));

			if (msg->state == wait_cmd_out_and_ack) {
				AndesTakeQueuedCmdMsg(ctl, &ctl->ackq, msg);
			} else if (msg->state == wait_ack)
				AndesTakeQueuedCmdMsg(ctl, &ctl->ackq, msg);

			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("%s: msg state = %d\n", __func__, msg->state));
			AndesIncErrorCount(ctl, error_tx_timeout_fail);
			state = tx_timeout_fail;

			if (msg->retry_times > 0)
				msg->retry_times--;

			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("msg->retry_times = %d\n", msg->retry_times));
#ifdef CONFIG_RECOVERY_ON_INTERRUPT_MISS
#ifdef INTELP6_SUPPORT
			/* To many continuous soft reboot on puma6 plateform make HW to go in unstabe state and
			 * driver fails to communicate with FW
			*/
			ad->ErrRecoveryCheck++;
			if (ops->heart_beat_check)
				ops->heart_beat_check(ad);
			if (RTMP_TEST_FLAG(ad, fRTMP_ADAPTER_INTERRUPT_ACTIVE)) {
				MTWF_LOG(DBG_CAT_HIF, CATHIF_PCI, DBG_LVL_OFF, ("Disabling interrupt\n"));
				RTMP_ASIC_INTERRUPT_DISABLE(ad);
			}
			MTWF_LOG(DBG_CAT_HIF, CATHIF_PCI, DBG_LVL_OFF, ("Enabling interrupt\n"));
			RTMP_ASIC_INTERRUPT_ENABLE(ad);
#else
			ASSERT(FALSE);
#endif
#else
			ASSERT(FALSE);
#endif
		} else {
			if (msg->state == tx_kickout_fail) {
				ret = NDIS_STATUS_FAILURE;
				state = tx_kickout_fail;
				if (msg->retry_times > 0)
					msg->retry_times--;
			} else {
				ret = NDIS_STATUS_SUCCESS;
				if (msg->state == wait_cmd_out_and_ack) {
					AndesTakeQueuedCmdMsg(ctl, &ctl->ackq, msg);
				} else if (msg->state == wait_ack)
					AndesTakeQueuedCmdMsg(ctl, &ctl->ackq, msg);

				state = tx_done;
				msg->retry_times = 0;
			}
		}

		if (RtmpDmaStopping(ad))
			msg->retry_times = 0;
		/* A failed clone cannot supply a retransmission packet. */
		if (is_cmd_need_wait && (msg->retry_times > 0) && msg->retry_pkt) {
			if (state == tx_kickout_fail)
				RTMPFreeNdisPacket(ad, msg->net_pkt);
			RTMP_OS_EXIT_COMPLETION(&msg->ack_done);
			RTMP_OS_INIT_COMPLETION(&msg->ack_done);
			msg->net_pkt = msg->retry_pkt;
			msg->retry_pkt = NULL;
			state = tx_retransmit;
			AndesQueueHeadCmdMsg(&ctl->txq, msg, state);
			goto retransmit;
		} else {
			/* No ring owns an unpublished packet.  Its waiting sender
			 * consumes both packet and any unused retry clone exactly once.
			 */
			if (state == tx_kickout_fail) {
				AndesForceFreeCmdMsg(msg);
				goto bailout;
			}
			if (ret == NDIS_STATUS_SUCCESS &&
				(msg->attr.ext_type == EXT_CMD_STAREC_UPDATE ||
				 msg->attr.ext_type == EXT_CMD_ID_DEVINFO_UPDATE ||
				 msg->attr.ext_type == EXT_CMD_ID_BSSINFO_UPDATE)) {
				/* Preserve firmware rejection and malformed/missing response errors. */
				ret = msg->cmd_return_status;
			}

			MTWF_LOG(DBG_CAT_FW, DBG_SUBCAT_ALL, DBG_LVL_INFO,
					 ("%s: msg state = %d\n", __func__, state));
			/* msg will be free after enqueuing to tx_doneq. So msg is not able to pass FW's response to caller. */
			AndesQueueTailCmdMsg(&ctl->tx_doneq, msg, state);
		}
#ifdef CONFIG_RECOVERY_ON_INTERRUPT_MISS
#ifdef INTELP6_SUPPORT
		if (IsComplete)
			ad->ErrRecoveryCheck = 0;
#endif
#endif
	}
bailout:
	return ret;
}
