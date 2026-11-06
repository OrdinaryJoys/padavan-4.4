/*
 ***************************************************************************
 * MediaTek Inc.
 *
 * All rights reserved. source code is an unpublished work and the
 * use of a copyright notice does not imply otherwise. This source code
 * contains confidential trade secret material of MediaTek. Any attemp
 * or participation in deciphering, decoding, reverse engineering or in any
 * way altering the source code is stricitly prohibited, unless the prior
 * written consent of MediaTek, Inc. is obtained.
 ***************************************************************************

	Module Name:
	wifi_sys_info.c
*/
#include	"rt_config.h"

/*Local function*/
static VOID get_network_type_str(UINT32 Type, CHAR *str)
{
	if (Type & NETWORK_INFRA)
		sprintf(str, "NETWORK_INFRA");
	else if (Type & NETWORK_P2P)
		sprintf(str, "NETWORK_P2P");
	else if (Type & NETWORK_IBSS)
		sprintf(str, "NETWORK_IBSS");
	else if (Type & NETWORK_MESH)
		sprintf(str, "NETWORK_MESH");
	else if (Type & NETWORK_BOW)
		sprintf(str, "NETWORK_BOW");
	else if (Type & NETWORK_WDS)
		sprintf(str, "NETWORK_WDS");
	else
		sprintf(str, "UND");
}

/*
*
*/
#ifdef CONFIG_AP_SUPPORT
#ifdef IGMP_SNOOP_SUPPORT
static VOID update_igmpinfo(struct wifi_dev *wdev, BOOLEAN bActive)
{
	struct _DEV_INFO_CTRL_T *devinfo = &wdev->DevInfo;
	struct _RTMP_ADAPTER *ad = wdev->sys_handle;
	UINT Enable = FALSE;

#ifdef IGMP_TVM_SUPPORT
	if (bActive == TRUE) {
		wdev->pIgmpMcastTable = NULL;
		wdev->IgmpTableSize = 0;
	}
#endif /* IGMP_TVM_SUPPORT */

	if (wdev->wdev_type == WDEV_TYPE_AP) {
		wdev->IgmpSnoopEnable
			= ad->ApCfg.IgmpSnoopEnable[devinfo->BandIdx];

		if (bActive == TRUE && wdev->IgmpSnoopEnable == TRUE) {
			Enable = TRUE;

#ifdef IGMP_TVM_SUPPORT
			wdev->u4AgeOutTime = IGMPMAC_TB_ENTRY_AGEOUT_TIME;
			if (IgmpSnEnableTVMode(ad,
									wdev,
									ad->ApCfg.IsTVModeEnable[devinfo->BandIdx],
									ad->ApCfg.TVModeType[devinfo->BandIdx]))
				Enable = wdev->TVModeType;
#endif /* IGMP_TVM_SUPPORT */
		}

		if (IS_ASIC_CAP(ad, fASIC_CAP_MCU_OFFLOAD))
		CmdMcastCloneEnable(ad, Enable, devinfo->OwnMacIdx);

#ifdef IGMP_TVM_SUPPORT
		if (IS_ASIC_CAP(ad, fASIC_CAP_MCU_OFFLOAD))
			MulticastFilterInitMcastTable(ad, wdev, bActive);
#endif /* IGMP_TVM_SUPPORT */

	}
}
#endif /*IGMP_SNOOP_SUPPORT */
#endif /*CONFIG_AP_SUPPORT*/

/*
*
*/
static VOID dump_devinfo(struct _WIFI_INFO_CLASS *class)
{
	struct _DEV_INFO_CTRL_T *devinfo = NULL;
	struct wifi_dev *wdev = NULL;

	DlListForEach(devinfo, &class->Head, DEV_INFO_CTRL_T, list) {
		wdev = (struct wifi_dev *)devinfo->priv;
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("#####WdevIdx (%d)#####\n", wdev->wdev_idx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("Active: %d\n", devinfo->Active));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("BandIdx: %d\n", devinfo->BandIdx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("EnableFeature: %d\n", devinfo->EnableFeature));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("OwnMacIdx: %d\n", devinfo->OwnMacIdx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("OwnMacAddr: %x:%x:%x:%x:%x:%x\n", PRINT_MAC(devinfo->OwnMacAddr)));
	}
}

/*
*
*/
static VOID dump_bssinfo(struct _WIFI_INFO_CLASS *class)
{
	BSS_INFO_ARGUMENT_T *bss = NULL;
	struct wifi_dev *wdev = NULL;
	CHAR str[128] = "";

	DlListForEach(bss, &class->Head, BSS_INFO_ARGUMENT_T, list) {
		wdev = (struct wifi_dev *)bss->priv;
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("#####WdevIdx (%d)#####\n", wdev->wdev_idx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("State: %d\n", bss->bss_state));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("Bssid: %x:%x:%x:%x:%x:%x\n", PRINT_MAC(bss->Bssid)));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("CipherSuit: %d\n", bss->CipherSuit));
		get_network_type_str(bss->NetworkType, str);
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("NetworkType: %s\n", str));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("OwnMacIdx: %d\n", bss->OwnMacIdx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("BssInfoFeature: %x\n", bss->u4BssInfoFeature));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("ConnectionType: %d\n", bss->u4ConnectionType));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("BcMcWlanIdx: %d\n", bss->ucBcMcWlanIdx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("BssIndex: %d\n", bss->ucBssIndex));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("PeerWlanIdx: %d\n", bss->ucPeerWlanIdx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("WmmIdx: %d\n", bss->WmmIdx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("BcTransmit: (Mode/BW/MCS) %d/%d/%d\n", bss->BcTransmit.field.MODE,
			   bss->BcTransmit.field.BW, bss->BcTransmit.field.MCS));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("McTransmit: (Mode/BW/MCS) %d/%d/%d\n", bss->McTransmit.field.MODE,
			   bss->BcTransmit.field.BW, bss->BcTransmit.field.MCS));
	}
}

/*
*
*/
static VOID dump_starec(struct _WIFI_INFO_CLASS *class)
{
	struct _STA_REC_CTRL_T *starec = NULL;
	struct _STA_TR_ENTRY *tr_entry = NULL;

	DlListForEach(starec, &class->Head, STA_REC_CTRL_T, list) {
		tr_entry = (STA_TR_ENTRY *)starec->priv;
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("#####MacEntry (%d)#####\n", tr_entry->wcid));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("PeerAddr: %x:%x:%x:%x:%x:%x\n", PRINT_MAC(tr_entry->Addr)));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("WlanIdx: %d\n", starec->WlanIdx));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("BssIndex: %d\n", starec->BssIndex));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("ConnectionState: %d\n", starec->ConnectionState));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("ConnectionType: %d\n", starec->ConnectionType));
		MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
			("EnableFeature: %x\n", starec->EnableFeature));
	}
}

/*
*
*/
static VOID add_devinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev)
{
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;
	struct _DEV_INFO_CTRL_T *devinfo = &wdev->DevInfo, *tmp = NULL;

	OS_SEM_LOCK(&wsys->lock);
	DlListForEach(tmp, &wsys->DevInfo.Head, DEV_INFO_CTRL_T, list) {
		if (devinfo == tmp) {
			OS_SEM_UNLOCK(&wsys->lock);
			MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_TRACE,
					 ("%s(): DevInfo %d already exist",
					  __func__, devinfo->OwnMacIdx));
			return;
		}
	}
	DlListAddTail(&wsys->DevInfo.Head, &devinfo->list);
	devinfo->priv = (VOID *)wdev;
	wsys->DevInfo.Num++;
	OS_SEM_UNLOCK(&wsys->lock);
}

/*
*
*/
static VOID add_bssinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev)
{
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;
	struct _BSS_INFO_ARGUMENT_T *bss = &wdev->bss_info_argument, *tmp;

	OS_SEM_LOCK(&wsys->lock);
	DlListForEach(tmp, &wsys->BssInfo.Head, BSS_INFO_ARGUMENT_T, list) {
		if (bss == tmp) {
			OS_SEM_UNLOCK(&wsys->lock);
			MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_TRACE,
					 ("%s(): BssInfo %d already exist",
					  __func__, bss->ucBssIndex));
			return;
		}
	}
	DlListAddTail(&wsys->BssInfo.Head, &bss->list);
	bss->priv = (VOID *)wdev;
	wsys->BssInfo.Num++;
	OS_SEM_UNLOCK(&wsys->lock);
}

/*
*
*/
static VOID add_starec(struct _RTMP_ADAPTER *pAd, STA_TR_ENTRY *tr_entry)
{
	struct _WIFI_SYS_INFO *wsys = &pAd->WifiSysInfo;
	struct _STA_REC_CTRL_T *strec = &tr_entry->StaRec, *tmp = NULL;

	OS_SEM_LOCK(&wsys->lock);
	DlListForEach(tmp, &wsys->StaRec.Head, STA_REC_CTRL_T, list) {
		if (tmp == strec) {
			OS_SEM_UNLOCK(&wsys->lock);
			MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_TRACE,
					 ("%s(): STARec %d already exist\n",
					  __func__, strec->WlanIdx));
			return;
		}
	}
	DlListAddTail(&wsys->StaRec.Head, &strec->list);
	strec->priv = (VOID *)tr_entry;
	wsys->StaRec.Num++;
	OS_SEM_UNLOCK(&wsys->lock);
}

/*
*
*/
struct _STA_REC_CTRL_T *get_starec_by_wcid(struct _RTMP_ADAPTER *ad, INT wcid)
{
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;
	struct _STA_REC_CTRL_T *sta_rec = NULL, *tmp = NULL;

	OS_SEM_LOCK(&wsys->lock);
	DlListForEach(tmp, &wsys->StaRec.Head, STA_REC_CTRL_T, list) {
		if (tmp->WlanIdx == wcid) {
			sta_rec = tmp;
			break;
		}
	}
	OS_SEM_UNLOCK(&wsys->lock);
	return sta_rec;
}

/*
*
*/
static VOID del_devinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev)
{
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;
	struct _DEV_INFO_CTRL_T *devinfo = &wdev->DevInfo;

	OS_SEM_LOCK(&wsys->lock);
	DlListDel(&devinfo->list);
	wsys->DevInfo.Num--;
	OS_SEM_UNLOCK(&wsys->lock);
}

/*
*
*/
static VOID del_bssinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev)
{
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;
	struct _BSS_INFO_ARGUMENT_T *bss = &wdev->bss_info_argument, *tmp;

	OS_SEM_LOCK(&wsys->lock);
	DlListForEach(tmp, &wsys->BssInfo.Head, BSS_INFO_ARGUMENT_T, list) {
		if (tmp == bss) {
			DlListDel(&bss->list);
			wsys->BssInfo.Num--;
			break;
		}
	}
	OS_SEM_UNLOCK(&wsys->lock);
}

/*
*
*/
static VOID del_starec(struct _RTMP_ADAPTER *ad, struct _STA_TR_ENTRY *tr_entry)
{
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;
	struct _STA_REC_CTRL_T *starec = &tr_entry->StaRec, *tmp;

	OS_SEM_LOCK(&wsys->lock);
	DlListForEach(tmp, &wsys->StaRec.Head, STA_REC_CTRL_T, list) {
		if (tmp == starec) {
			DlListDel(&starec->list);
			wsys->StaRec.Num--;
			break;
		}
	}
	OS_SEM_UNLOCK(&wsys->lock);
}

/*
*
*/
static VOID fill_devinfo(
	struct _RTMP_ADAPTER *pAd,
	struct wifi_dev *wdev,
	BOOLEAN act,
	struct _DEV_INFO_CTRL_T *devinfo)
{
	struct _DEV_INFO_CTRL_T *org = &wdev->DevInfo;

	os_move_mem(devinfo, org, sizeof(DEV_INFO_CTRL_T));
	devinfo->Active = act;
	devinfo->OwnMacIdx = wdev->OmacIdx;
	os_move_mem(devinfo->OwnMacAddr, wdev->if_addr, MAC_ADDR_LEN);
	devinfo->EnableFeature = DEVINFO_ACTIVE_FEATURE;
	devinfo->BandIdx = HcGetBandByWdev(wdev);
	MTWF_LOG(DBG_CAT_CLIENT, CATCLIENT_APCLI, DBG_LVL_TRACE,
		("%s(): Active=%d,OwnMacIdx=%d,EnableFeature=%d,BandIdx=%d\n", __func__,
		devinfo->Active, devinfo->OwnMacIdx, devinfo->EnableFeature, devinfo->BandIdx));
}

/*
*
*/
static inline VOID fill_bssinfo_active(
	struct _RTMP_ADAPTER *ad,
	struct wifi_dev *wdev,
	struct _BSS_INFO_ARGUMENT_T *bssinfo)
{
	BssInfoArgumentLink(ad, wdev, bssinfo);
	/* Keep the acquired index/WCID/EDCA discoverable until confirmed close. */
	os_move_mem(&wdev->bss_info_argument, bssinfo, sizeof(*bssinfo));
	WDEV_BSS_STATE(wdev) = BSS_INITED;
	bssinfo->bss_state = BSS_ACTIVE;
}

/*
*
*/
static inline VOID fill_bssinfo_deactive(
	struct _RTMP_ADAPTER *ad,
	struct wifi_dev *wdev,
	struct _BSS_INFO_ARGUMENT_T *bssinfo)
{
	os_move_mem(bssinfo, &wdev->bss_info_argument, sizeof(wdev->bss_info_argument));
	bssinfo->bss_state = BSS_INITED;
}

/*
*
*/
static VOID fill_bssinfo(
	struct _RTMP_ADAPTER *ad,
	struct wifi_dev *wdev,
	BOOLEAN act,
	struct _BSS_INFO_ARGUMENT_T *bssinfo)
{
	if (act)
		fill_bssinfo_active(ad, wdev, bssinfo);
	else
		fill_bssinfo_deactive(ad, wdev, bssinfo);
}

/*
*
*/
static VOID fill_starec(
	struct _RTMP_ADAPTER *ad,
	struct _STA_TR_ENTRY *tr_entry,
	struct _STA_REC_CTRL_T *starec)
{
	os_move_mem(starec, &tr_entry->StaRec, sizeof(tr_entry->StaRec));
}



/*
*
*/
static INT call_wsys_notifieriers(INT val, struct wifi_dev *wdev, void *v)
{
	struct _RTMP_ADAPTER *ad = wdev->sys_handle;
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;
	struct wsys_notify_info info;
	INT ret;

	/*fill wsys notify info*/
	info.wdev = wdev;
	info.v = v;
	/*traversal caller for wsys notify chain*/
	ret = mt_notify_call_chain(&wsys->wsys_notify_head, val, &info);
	return ret;
}

/*export function*/
/*
*
*/
INT register_wsys_notifier(struct _WIFI_SYS_INFO *wsys, struct notify_entry *ne)
{
	INT ret;

	ret = mt_notify_chain_register(&wsys->wsys_notify_head, ne);

	return ret;
}

/*
*
*/
INT unregister_wsys_notifier(struct _WIFI_SYS_INFO *wsys, struct notify_entry *ne)
{
	INT ret;

	ret = mt_notify_chain_unregister(&wsys->wsys_notify_head, ne);
	return ret;
}

/*
*
*/
VOID wifi_sys_reset(struct _WIFI_SYS_INFO *wsys)
{
	DlListInit(&wsys->DevInfo.Head);
	DlListInit(&wsys->StaRec.Head);
	DlListInit(&wsys->BssInfo.Head);

	wsys->DevInfo.Num = 0;
	wsys->StaRec.Num = 0;
	wsys->BssInfo.Num = 0;
}

/*
*
*/
VOID wifi_sys_init(struct _RTMP_ADAPTER *ad)
{
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;

	NdisAllocateSpinLock(ad, &wsys->lock);
	wifi_sys_reset(wsys);
	INIT_NOTIFY_HEAD(ad, &wsys->wsys_notify_head);
}


/*
*
*/
VOID wifi_sys_dump(struct _RTMP_ADAPTER *ad)
{
	struct _WIFI_SYS_INFO *wsys = &ad->WifiSysInfo;

	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("===============================\n"));
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("Current DevInfo Num: %d\n", wsys->DevInfo.Num));
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("===============================\n"));
	dump_devinfo(&wsys->DevInfo);
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("===============================\n"));
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("Current BssInfo Num: %d\n", wsys->BssInfo.Num));
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("===============================\n"));
	dump_bssinfo(&wsys->BssInfo);
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("===============================\n"));
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("Current StaRec Num: %d\n", wsys->StaRec.Num));
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("===============================\n"));
	dump_starec(&wsys->StaRec);
}

/*
*
*/
INT wifi_sys_update_devinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev, struct _DEV_INFO_CTRL_T *new)
{
	INT len = sizeof(wdev->DevInfo) - sizeof(wdev->DevInfo.list);

	if (!new->Active)
		call_wsys_notifieriers(WSYS_NOTIFY_CLOSE, wdev, NULL);
	os_move_mem(&wdev->DevInfo, new, len);
#ifdef CONFIG_AP_SUPPORT
#ifdef IGMP_SNOOP_SUPPORT
	/* Terminal host retirement must not restart a stopped MCU transport. */
	if (!RtmpDmaStopping(ad))
		update_igmpinfo(wdev, new->Active);
#endif
#endif
	if (new->Active) {
		wlan_operate_set_state(wdev, WLAN_OPER_STATE_VALID);
		add_devinfo(ad, wdev);
		/*notify other modules, hw resouce is acquired down*/
		call_wsys_notifieriers(WSYS_NOTIFY_OPEN, wdev, NULL);
	} else {
		del_devinfo(ad, wdev);
		/*release hw resource*/
		HcReleaseRadioForWdev(wdev->sys_handle, wdev);
	}
	return 0;
}

/*
*
*/
INT wifi_sys_update_bssinfo(struct _RTMP_ADAPTER *ad, struct wifi_dev *wdev, struct _BSS_INFO_ARGUMENT_T *new)
{
	BSS_INFO_ARGUMENT_T *bss = &wdev->bss_info_argument;
	INT len = sizeof(wdev->bss_info_argument) - sizeof(bss->list);

	if (new->bss_state >= BSS_ACTIVE) {
		os_move_mem(bss, new, len);
		add_bssinfo(ad, wdev);
		WDEV_BSS_STATE(wdev) = BSS_READY;
		/*notify other modules, bss related setting is done*/
		call_wsys_notifieriers(WSYS_NOTIFY_LINKUP, wdev, bss);
	} else {
		call_wsys_notifieriers(WSYS_NOTIFY_LINKDOWN, wdev, NULL);
		del_bssinfo(ad, wdev);
		BssInfoArgumentUnLink(ad, wdev);
	}
	return 0;
}

/*
*
*/
INT wifi_sys_update_starec(struct _RTMP_ADAPTER *ad, struct _STA_REC_CTRL_T *new)
{
	struct _STA_TR_ENTRY *tr_entry = (struct _STA_TR_ENTRY *) new->priv;
	struct _STA_REC_CTRL_T *sta_rec = &tr_entry->StaRec;
	INT len = sizeof(tr_entry->StaRec) - sizeof(sta_rec->list);

	if (new->ConnectionState == STATE_DISCONNECT)
		call_wsys_notifieriers(WSYS_NOTIFY_DISCONNT_ACT, tr_entry->wdev, tr_entry);
	os_move_mem(sta_rec, new, len);
	if (new->ConnectionState == STATE_DISCONNECT) {
		/*remove starec*/
		del_starec(ad, tr_entry);
	} else {
		add_starec(ad, tr_entry);
		/*notify other modules, starec is prepeare done*/
		call_wsys_notifieriers(WSYS_NOTIFY_CONNT_ACT, tr_entry->wdev, tr_entry);
	}
	return 0;
}

/*
* for peer update usage
*/
INT wifi_sys_update_starec_info(struct _RTMP_ADAPTER *ad, struct _STA_REC_CTRL_T *new)
{
	struct _STA_TR_ENTRY *tr_entry = (struct _STA_TR_ENTRY *) new->priv;
	struct _STA_REC_CTRL_T *sta_rec = &tr_entry->StaRec;
	INT len = sizeof(tr_entry->StaRec) - sizeof(sta_rec->list);

	os_move_mem(sta_rec, new, len);
	call_wsys_notifieriers(WSYS_NOTIFY_STA_UPDATE, tr_entry->wdev, tr_entry);

	return 0;
}


/*wcid: STA is peer root AP, AP is bmc wcid*/
static UINT32 bssinfo_feature_decision(
	struct wifi_dev *wdev,
	UINT32 conn_type,
	UCHAR wcid,
	UINT32 *feature)
{
	struct _RTMP_ADAPTER *ad = (struct _RTMP_ADAPTER *) wdev->sys_handle;
	/*basic features*/
	UINT32 features = (BSS_INFO_OWN_MAC_FEATURE
					   | BSS_INFO_BASIC_FEATURE
					   | BSS_INFO_RF_CH_FEATURE
					   | BSS_INFO_BROADCAST_INFO_FEATURE);

#ifdef RACTRL_FW_OFFLOAD_SUPPORT
	struct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(ad->hdev_ctrl);

	if (cap->fgRateAdaptFWOffload == TRUE)
		features |= BSS_INFO_RA_FEATURE;
#endif

	/*HW BSSID features*/
	if (wdev->OmacIdx > HW_BSSID_MAX)
		features |= BSS_INFO_EXT_BSS_FEATURE;
	else
		features |= BSS_INFO_SYNC_MODE_FEATURE;

#ifdef HW_TX_AMSDU_SUPPORT
	if (IS_ASIC_CAP(ad, fASIC_CAP_HW_TX_AMSDU))
		features |= BSS_INFO_HW_AMSDU_FEATURE;
#endif

	*feature = features;
	return TRUE;
}

/*
*
*/
static VOID starec_security_set(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry, struct _STA_REC_CTRL_T *sta_rec)
{
	ASIC_SEC_INFO *asic_sec_info = &sta_rec->asic_sec_info;
	/* Set key material to Asic */
	os_zero_mem(asic_sec_info, sizeof(ASIC_SEC_INFO));
	asic_sec_info->Operation = SEC_ASIC_ADD_PAIRWISE_KEY;
	asic_sec_info->Direction = SEC_ASIC_KEY_BOTH;
	asic_sec_info->Wcid = entry->wcid;
	asic_sec_info->BssIndex = entry->func_tb_idx;
	asic_sec_info->KeyIdx = entry->SecConfig.PairwiseKeyId;
	asic_sec_info->Cipher = entry->SecConfig.PairwiseCipher;
	asic_sec_info->KeyIdx = entry->SecConfig.PairwiseKeyId;
	os_move_mem(&asic_sec_info->Key, &entry->SecConfig.WepKey[entry->SecConfig.PairwiseKeyId], sizeof(SEC_KEY_INFO));
	os_move_mem(&asic_sec_info->PeerAddr[0], entry->Addr, MAC_ADDR_LEN);
}

/*sta rec feature decision*/
static UINT32 starec_feature_decision(
	struct wifi_dev *wdev,
	UINT32 conn_type,
	struct _MAC_TABLE_ENTRY *entry,
	UINT32 *feature)
{
	/*basic feature*/
	UINT32 features = (STA_REC_BASIC_STA_RECORD_FEATURE
					   | STA_REC_TX_PROC_FEATURE);
	features |= STA_REC_WTBL_FEATURE;

	if (conn_type != CONNECTION_INFRA_BC) {
		/*ht features */
#ifdef DOT11_N_SUPPORT
		starec_ht_feature_decision(wdev, entry, &features);
#ifdef DOT11_VHT_AC
		starec_vht_feature_decision(wdev, entry, &features);
#endif /*DOT11_VHT_AC*/
#ifdef TXBF_SUPPORT
		starec_txbf_feature_decision(wdev, entry, &features);
#endif /* TXBF_SUPPORT */
#endif /*DOT11_N_SUPPORT*/
	}

#ifdef CONFIG_AP_SUPPORT

	if (conn_type == CONNECTION_INFRA_STA)
		starec_ap_feature_decision(wdev, entry, &features);

#endif /*CONFIG_AP_SUPPORT*/
	/*return value, must use or operation*/
	*feature = features;
	return TRUE;
}

static UINT32 starec_security_decision(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry, UCHAR *state)
{
	struct _RTMP_ADAPTER *ad = (struct _RTMP_ADAPTER *)wdev->sys_handle;
	struct _STA_TR_ENTRY *tr_entry;
	UCHAR port_sec = STATE_DISCONNECT;

	/*for bmc case*/
	if (!entry) {
		port_sec = STATE_PORT_SECURE;
		goto end;
	}

	/*for uc case*/
	tr_entry = &ad->MacTab.tr_entry[entry->wcid];

	switch (wdev->wdev_type) {
	case WDEV_TYPE_STA:
	case WDEV_TYPE_TDLS:
		if ((tr_entry->PortSecured == WPA_802_1X_PORT_NOT_SECURED)
			&& (IS_AKM_WPA_CAPABILITY_Entry(entry)))
			port_sec = STATE_CONNECTED;
		else if (tr_entry->PortSecured == WPA_802_1X_PORT_SECURED)
			port_sec = STATE_PORT_SECURE;

		break;

	case WDEV_TYPE_APCLI:
		if (IS_NO_SECURITY_Entry(entry) || IS_CIPHER_WEP_Entry(entry))
			port_sec = STATE_PORT_SECURE;
		else
			port_sec = STATE_CONNECTED;

		break;
#ifdef CONFIG_AP_SUPPORT

	case WDEV_TYPE_AP: {
		if ((tr_entry->PortSecured == WPA_802_1X_PORT_NOT_SECURED)
			&& (IS_AKM_WPA_CAPABILITY_Entry(entry)
#ifdef DOT1X_SUPPORT
				|| IS_IEEE8021X(&entry->SecConfig)
#endif /* DOT1X_SUPPORT */
#ifdef RT_CFG80211_SUPPORT
				|| wdev->IsCFG1xWdev
#endif /* RT_CFG80211_SUPPORT */
				|| entry->bWscCapable))
			port_sec = STATE_CONNECTED;
		else if (tr_entry->PortSecured == WPA_802_1X_PORT_SECURED) {

#ifdef FAST_EAPOL_WAR
		/*
		*	set STATE_CONNECTED first in open security mode,
		*	after asso resp is sent out, then set STATE_PORT_SECURE.
		*/
			port_sec = STATE_CONNECTED;
#else /* FAST_EAPOL_WAR */
			port_sec = STATE_PORT_SECURE;
			CheckBMCPortSecured(ad, entry, TRUE);
#endif /* !FAST_EAPOL_WAR */
		}
	}
	break;
#endif /*CONFIG_AP_SUPPORT*/

	default:
		port_sec = STATE_PORT_SECURE;
		break;
	}

end:
	*state = port_sec;
	return TRUE;
}

/*
*
*/
INT wifi_sys_open(struct wifi_dev *wdev)
{
	struct WIFI_SYS_CTRL wsys;

	if (RtmpDmaQuarantined(wdev->sys_handle))
		return FALSE;

	os_zero_mem(&wsys, sizeof(wsys));
	MTWF_LOG(DBG_CAT_INIT, DBG_SUBCAT_ALL, DBG_LVL_OFF,
		("%s(), wdev idx = %d\n", __func__, wdev->wdev_idx));

	if (!wdev->DevInfo.Active && (wlan_operate_get_state(wdev) == WLAN_OPER_STATE_INVALID)) {
		/*acquire wdev related attribute*/
		if (wdev_attr_update(wdev->sys_handle, wdev) != TRUE)
			return FALSE;

		/* WDS share DevInfo with normal AP */
		if (wdev->wdev_type != WDEV_TYPE_WDS)
			fill_devinfo(wdev->sys_handle, wdev, TRUE, &wsys.DevInfoCtrl);

		wsys.wdev = wdev;
		/*update to hwctrl*/
		if (HW_WIFISYS_OPEN(wdev->sys_handle, &wsys) != NDIS_STATUS_SUCCESS) {
			if (!RtmpDmaQuarantined(wdev->sys_handle)) {
				UpdateDot11hForWdev(wdev->sys_handle, wdev, FALSE);
				HcReleaseRadioForWdev(wdev->sys_handle, wdev);
			}
			return FALSE;
		}
	}

	return TRUE;
}

/*
*
*/
INT wifi_sys_close(struct wifi_dev *wdev)
{
	struct WIFI_SYS_CTRL wsys;

	if (RtmpDmaQuarantined(wdev->sys_handle))
		return FALSE;

	os_zero_mem(&wsys, sizeof(wsys));
	MTWF_LOG(DBG_CAT_INIT, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s(), wdev idx = %d\n",
		__func__, wdev->wdev_idx));

	if (wlan_operate_get_state(wdev) == WLAN_OPER_STATE_VALID) {

		/* WDS share DevInfo with normal AP */
		if (wdev->wdev_type != WDEV_TYPE_WDS)
			fill_devinfo(wdev->sys_handle, wdev, FALSE, &wsys.DevInfoCtrl);

		wsys.wdev = wdev;
		/*update to hwctrl*/
		if (HW_WIFISYS_CLOSE(wdev->sys_handle, &wsys) != NDIS_STATUS_SUCCESS)
			return FALSE;
	}

	return TRUE;
}

/*
*
*/
INT wifi_sys_disconn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry)
{
	struct WIFI_SYS_CTRL wsys;
	struct _RTMP_ADAPTER *ad = (struct _RTMP_ADAPTER *)wdev->sys_handle;
	struct _STA_TR_ENTRY *tr_entry = &ad->MacTab.tr_entry[entry->tr_tb_idx];
	struct _STA_REC_CTRL_T *new_sta = &wsys.StaRecCtrl;

	if (RtmpDmaQuarantined(wdev->sys_handle))
		return FALSE;

	os_zero_mem(&wsys, sizeof(wsys));

	if (entry->EntryState == ENTRY_STATE_SYNC) {
		/* Deactive StaRec in FW */
		new_sta->BssIndex = wdev->bss_info_argument.ucBssIndex;
		new_sta->WlanIdx = entry->wcid;
		new_sta->ConnectionType = entry->ConnectionType;
		new_sta->ConnectionState = STATE_DISCONNECT;
		new_sta->EnableFeature = STA_REC_BASIC_STA_RECORD_FEATURE;
		new_sta->priv = tr_entry;

		if (IS_ENTRY_CLIENT(entry)) {
			/* there is no need to set txop when sta connected */
			wsys.skip_set_txop = TRUE;
		} else if (IS_ENTRY_REPEATER(entry)) {
			/* skip disable txop for repeater case since apcli is connected */
			wsys.skip_set_txop = TRUE;
		}
		wsys.wdev = wdev;
		/*send event for release starec*/
		if (HW_WIFISYS_PEER_LINKDOWN(ad, &wsys) != NDIS_STATUS_SUCCESS)
			return FALSE;
		entry->EntryState = ENTRY_STATE_NONE;
#ifdef CONFIG_AP_SUPPORT

		if (wdev->wdev_type == WDEV_TYPE_AP)
			CheckBMCPortSecured(ad, entry, FALSE);

#endif /* CONFIG_AP_SUPPORT */
	}
	return TRUE;
}

/*wifi system connection action*/
INT wifi_sys_conn_act(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry)
{
	struct _RTMP_ADAPTER *ad = (struct _RTMP_ADAPTER *)wdev->sys_handle;
	struct WIFI_SYS_CTRL wsys;
	struct _STA_REC_CTRL_T *sta_rec = &wsys.StaRecCtrl;
	struct _STA_TR_ENTRY *tr_entry = &ad->MacTab.tr_entry[entry->tr_tb_idx];
	struct _BSS_INFO_ARGUMENT_T *bss = &wdev->bss_info_argument;
	UINT32 features = 0;
	UCHAR state = 0;

	/*star to fill wifi sys control*/
	if (RtmpDmaQuarantined(wdev->sys_handle))
		return FALSE;

	os_zero_mem(&wsys, sizeof(wsys));
	/*generic connection action*/
	/*sta rec feature & security update*/
	starec_feature_decision(wdev, entry->ConnectionType, entry, &features);
	starec_security_decision(wdev, entry, &state);
	/*prepare basic sta rec*/
	fill_starec(ad, tr_entry, sta_rec);
	sta_rec->BssIndex = bss->ucBssIndex;
	sta_rec->WlanIdx = entry->wcid;
	sta_rec->ConnectionType = entry->ConnectionType;
	sta_rec->ConnectionState = state;
	sta_rec->EnableFeature =  features;
	sta_rec->IsNewSTARec = TRUE;
	sta_rec->priv = tr_entry;
	/*prepare starec */
	if (sta_rec->EnableFeature & STA_REC_INSTALL_KEY_FEATURE)
		starec_security_set(wdev, entry, sta_rec);

	if (wdev->wdev_type == WDEV_TYPE_AP)
		wsys.skip_set_txop = TRUE;

	wsys.wdev = wdev;
	if (HW_WIFISYS_PEER_LINKUP(ad, &wsys) != NDIS_STATUS_SUCCESS)
		return FALSE;
	entry->EntryState = ENTRY_STATE_SYNC;
	MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_TRACE,
			 ("===> AsicStaRecUpdate called by (%s), wcid=%d, PortSecured=%d, AKMMap=%d\n",
			  __func__, entry->wcid, sta_rec->ConnectionState, entry->SecConfig.AKMMap));
	return TRUE;
}

/*
*
*/
INT wifi_sys_linkup(struct wifi_dev *wdev, struct _MAC_TABLE_ENTRY *entry)
{
	struct WIFI_SYS_CTRL wsys;
	STA_REC_CTRL_T *sta_rec;
	struct _STA_TR_ENTRY *tr_entry;
	UCHAR state = 0;
	struct _RTMP_ADAPTER *ad = (struct _RTMP_ADAPTER *)wdev->sys_handle;
	struct _BSS_INFO_ARGUMENT_T *bss = &wsys.BssInfoCtrl;
	UINT32 features = 0;
	UCHAR wcid;
	UCHAR *addr = NULL;

	MTWF_LOG(DBG_CAT_INIT, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s(), wdev idx = %d\n",
		__func__, wdev->wdev_idx));

	if (RtmpDmaQuarantined(wdev->sys_handle))
		return FALSE;

	/*if interface down up should not run ap link up (for apstop/apstart check)*/
	if (!HcIsRadioAcq(wdev))
		return TRUE;

	os_zero_mem(&wsys, sizeof(wsys));

	if (WDEV_BSS_STATE(wdev) <= BSS_INITED) {
		/*prepare bssinfo*/
		if (WDEV_BSS_STATE(wdev) == BSS_INIT)
			fill_bssinfo(wdev->sys_handle, wdev, TRUE, bss);
		else {
			/* Retry the reserved BSS instead of acquiring a second owner. */
			os_move_mem(bss, &wdev->bss_info_argument, sizeof(*bss));
			bss->bss_state = BSS_ACTIVE;
		}
#ifdef APCLI_OWE_SUPPORT
		/*To allow OWE ApCli to connect to Open bss*/
		if ((wdev->wdev_type == WDEV_TYPE_APCLI) && IS_AKM_OWE(wdev->SecConfig.AKMMap)) {
			if (IS_AKM_OPEN(entry->SecConfig.AKMMap) && IS_CIPHER_NONE(entry->SecConfig.PairwiseCipher))
				bss->CipherSuit = SecHWCipherSuitMapping(entry->SecConfig.PairwiseCipher);

		}
#endif


		wcid = (entry) ? entry->wcid : bss->ucBcMcWlanIdx;
		bssinfo_feature_decision(wdev, bss->u4ConnectionType, wcid, &features);
		bss->ucPeerWlanIdx = wcid;
		bss->u4BssInfoFeature = features;
		/*wds type should not this bmc starec*/
		if (wdev->wdev_type == WDEV_TYPE_WDS) {
			bss->ucBcMcWlanIdx = wcid;
		} else {
			/*prepare bmc starec*/
			starec_feature_decision(wdev, CONNECTION_INFRA_BC, NULL, &features);
			starec_security_decision(wdev, NULL, &state);
#ifdef MBSS_AS_WDS_AP_SUPPORT
		if (wdev->wds_enable) {
			MTWF_LOG(DBG_CAT_CLIENT, CATCLIENT_APCLI, DBG_LVL_TRACE,("WDS Enable setting 4 address mode for %d entry \n",
					wdev->bss_info_argument.ucBcMcWlanIdx));
			HW_SET_ASIC_WCID_4ADDR_HDR_TRANS(ad, wdev->bss_info_argument.ucBcMcWlanIdx, TRUE);
		}
#endif
			/*1. get tr entry here, since bss info is acquired above */
			tr_entry = &ad->MacTab.tr_entry[wdev->tr_tb_idx];
			sta_rec = &wsys.StaRecCtrl;
			/* BC sta record should always set STATE_PORT_SECURE*/
			sta_rec->BssIndex = bss->ucBssIndex;
			sta_rec->WlanIdx = bss->ucBcMcWlanIdx;
			sta_rec->ConnectionState = state;
			sta_rec->ConnectionType = CONNECTION_INFRA_BC;
			sta_rec->EnableFeature = features;
			sta_rec->IsNewSTARec = TRUE;
			sta_rec->priv = tr_entry;
#ifdef CONFIG_AP_SUPPORT

			if (wdev->wdev_type == WDEV_TYPE_AP)
				APKeyTableInit(ad, wdev, sta_rec);
#endif /*CONFIG_AP_SUPPORT*/

			/*BMC STAREC*/
			addr  = (entry) ? entry->Addr : wdev->bssid;
			os_move_mem(tr_entry->Addr, addr, MAC_ADDR_LEN);
			MTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_TRACE,
					 ("===> AsicStaRecUpdate called by (%s), wcid=%d, PortSecured=%d\n",
				  __func__, bss->ucBcMcWlanIdx, sta_rec->ConnectionState));
		}
		/*update to hw ctrl*/
		wsys.wdev = wdev;
		if (HW_WIFISYS_LINKUP(ad, &wsys) != NDIS_STATUS_SUCCESS)
			return FALSE;
	}

	return TRUE;
}

INT wifi_sys_linkdown(struct wifi_dev *wdev)
{
	struct WIFI_SYS_CTRL wsys;
	struct _STA_REC_CTRL_T *sta_rec;
	struct _STA_TR_ENTRY *tr_entry;
	struct _BSS_INFO_ARGUMENT_T *bss = &wsys.BssInfoCtrl;
	UINT32 features = 0;
	struct _RTMP_ADAPTER *ad = wdev->sys_handle;

	MTWF_LOG(DBG_CAT_INIT, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s(), wdev idx = %d\n",
		__func__, wdev->wdev_idx));

	if (RtmpDmaQuarantined(wdev->sys_handle))
		return FALSE;

	os_zero_mem(&wsys, sizeof(wsys));

	if (WDEV_BSS_STATE(wdev) >= BSS_INITED) {
		fill_bssinfo(ad, wdev, FALSE, bss);
		bssinfo_feature_decision(wdev, bss->u4ConnectionType, bss->ucBcMcWlanIdx, &features);
		bss->u4BssInfoFeature = features;
		/*wds should not bmc starec*/
		if (wdev->wdev_type != WDEV_TYPE_WDS) {
			/*update sta rec.*/
			/*1. get tr entry here, since bss info is acquired above */
			sta_rec = &wsys.StaRecCtrl;
			tr_entry = &ad->MacTab.tr_entry[wdev->tr_tb_idx];
			if (tr_entry->StaRec.ConnectionState) {
				sta_rec->ConnectionState = STATE_DISCONNECT;
				sta_rec->EnableFeature = STA_REC_BASIC_STA_RECORD_FEATURE;
				sta_rec->BssIndex = bss->ucBssIndex;
				sta_rec->ConnectionType = CONNECTION_INFRA_BC;
				sta_rec->WlanIdx = bss->ucBcMcWlanIdx;
				sta_rec->priv = tr_entry;
			}
		}
		/*update to hwctrl for hw seting*/
		wsys.wdev = wdev;
		if (HW_WIFISYS_LINKDOWN(ad, &wsys) != NDIS_STATUS_SUCCESS)
			return FALSE;
	}

	return TRUE;
}

/* Last-VIF/remove teardown has already stopped DMA and MCU admissions.
 * Run on the serialized HwCtrl worker: earlier commands retire before these
 * software owners. This is not an acknowledgement from the stopped firmware. */
INT wifi_sys_retire(struct _RTMP_ADAPTER *ad, struct WIFI_SYS_CTRL *wsys, UINT32 id)
{
	struct wifi_dev *wdev = wsys->wdev;
	struct _STA_REC_CTRL_T *sta = &wsys->StaRecCtrl;

	if (!RtmpDmaStopping(ad) || !RtmpDmaResourcesMayRelease(ad))
		return NDIS_STATUS_FAILURE;
	if ((id == HWCMD_ID_WIFISYS_LINKDOWN || id == HWCMD_ID_WIFISYS_PEER_LINKDOWN) &&
		sta->EnableFeature && (!sta->priv || sta->ConnectionState != STATE_DISCONNECT))
		return NDIS_STATUS_INVALID_DATA;

	switch (id) {
	case HWCMD_ID_WIFISYS_CLOSE:
		if (wsys->DevInfoCtrl.Active)
			return NDIS_STATUS_INVALID_DATA;
		if (wsys->DevInfoCtrl.EnableFeature)
			wifi_sys_update_devinfo(ad, wdev, &wsys->DevInfoCtrl);
		wlan_operate_set_state(wdev, WLAN_OPER_STATE_INVALID);
		UpdateDot11hForWdev(ad, wdev, FALSE);
		break;
	case HWCMD_ID_WIFISYS_LINKDOWN:
		if (wsys->BssInfoCtrl.bss_state >= BSS_ACTIVE)
			return NDIS_STATUS_INVALID_DATA;
		if (sta->EnableFeature)
			wifi_sys_update_starec(ad, sta);
		if (wsys->BssInfoCtrl.u4BssInfoFeature)
			wifi_sys_update_bssinfo(ad, wdev, &wsys->BssInfoCtrl);
		break;
	case HWCMD_ID_WIFISYS_PEER_LINKDOWN:
		if (sta->EnableFeature)
			wifi_sys_update_starec(ad, sta);
		break;
	default:
		return NDIS_STATUS_FAILURE;
	}
	return NDIS_STATUS_SUCCESS;
}

/* Retire every owner published by a failed AP open before its VIF is dropped. */
INT wifi_sys_abort_open(struct wifi_dev *wdev)
{
	struct _RTMP_ADAPTER *ad = wdev->sys_handle;

	if (RtmpDmaQuarantined(ad))
		return FALSE;
	if (wifi_sys_linkdown(wdev) != TRUE || wifi_sys_close(wdev) != TRUE) {
		RtmpDmaQuarantine(ad);
		return FALSE;
	}
	return TRUE;
}

/*register wifi system architecture*/
VOID wifi_sys_ops_register(struct wifi_dev *wdev)
{
	struct wifi_dev_ops *ops = wdev->wdev_ops;
	/*register generic part*/
	ops->open = wifi_sys_open;
	ops->close = wifi_sys_close;
	ops->disconn_act = wifi_sys_disconn_act;
	ops->conn_act = wifi_sys_conn_act;
	ops->linkup = wifi_sys_linkup;
	ops->linkdown = wifi_sys_linkdown;

	/*specific action*/
	switch (wdev->wdev_type) {
#ifdef CONFIG_AP_SUPPORT
	case WDEV_TYPE_AP:
		ops->linkup = ap_link_up;
		ops->linkdown = ap_link_down;
		ops->conn_act = ap_conn_act;
		ops->open = ap_inf_open;
		ops->close = ap_inf_close;
		/* ap_cntl_init(wdev); //snowpin for cntl mgmt */
		break;

#ifdef APCLI_SUPPORT
	case WDEV_TYPE_APCLI:
		ops->linkup = apcli_link_up;
		ops->open = apcli_inf_open;
		ops->close = apcli_inf_close;
		/* sta_cntl_init(wdev); //snowpin for cntl mgmt */
		break;
#endif /*APCLI_SUPPORT*/

#ifdef WDS_SUPPORT
	case WDEV_TYPE_WDS:
		ops->open = wds_inf_open;
		ops->close = wds_inf_close;
		break;
#endif /*WDS_SUPPORT*/
#endif /*CONFIG_AP_SUPPORT*/

	}
}

/*
*
*/
VOID WifiSysUpdatePortSecur(RTMP_ADAPTER *pAd, MAC_TABLE_ENTRY *pEntry, ASIC_SEC_INFO *asic_sec_info)
{
	struct WIFI_SYS_CTRL wsys;
	struct wifi_dev *wdev = pEntry->wdev;
	struct _STA_REC_CTRL_T *sta_ctrl = &wsys.StaRecCtrl;
	struct _STA_TR_ENTRY *tr_entry = &pAd->MacTab.tr_entry[pEntry->tr_tb_idx];
	struct _STA_REC_CTRL_T *org = &tr_entry->StaRec;

	if (org->ConnectionState) {
		os_zero_mem(&wsys, sizeof(wsys));
		sta_ctrl->BssIndex = wdev->bss_info_argument.ucBssIndex;
		sta_ctrl->ConnectionState = STATE_PORT_SECURE;
		sta_ctrl->ConnectionType = pEntry->ConnectionType;
		sta_ctrl->EnableFeature = STA_REC_BASIC_STA_RECORD_FEATURE;
		sta_ctrl->WlanIdx = pEntry->wcid;
		sta_ctrl->IsNewSTARec = FALSE;
		sta_ctrl->priv = tr_entry;
		if (asic_sec_info) {
			sta_ctrl->EnableFeature |= STA_REC_INSTALL_KEY_FEATURE;
			NdisMoveMemory(&sta_ctrl->asic_sec_info, asic_sec_info, sizeof(ASIC_SEC_INFO));
		}

		wsys.wdev = wdev;
		if (HW_WIFISYS_PEER_UPDATE(pAd, &wsys) != NDIS_STATUS_SUCCESS)
			return;
		if (IS_ENTRY_CLIENT(pEntry)) {
			INT32 aid = pEntry->wcid;

			RESET_FLAG_CONN_IN_PROG(aid, pAd->ConInPrgress);
		}

#ifdef CONFIG_AP_SUPPORT
		CheckBMCPortSecured(pAd, pEntry, TRUE);
#endif /* CONFIG_AP_SUPPORT */
#ifdef APCLI_AS_WDS_STA_SUPPORT
		if (IS_ENTRY_APCLI(pEntry)) {
			pEntry->bEnable4Addr = TRUE;
			if (wdev->wds_enable)
				HW_SET_ASIC_WCID_4ADDR_HDR_TRANS(pAd, pEntry->wcid, TRUE);
		}
#endif /* APCLI_AS_WDS_STA_SUPPORT */

#ifdef MBSS_AS_WDS_AP_SUPPORT
		if (IS_ENTRY_CLIENT(pEntry)) {
			pEntry->bEnable4Addr = TRUE;
			if (wdev->wds_enable)
				HW_SET_ASIC_WCID_4ADDR_HDR_TRANS(pAd,pEntry->wcid, TRUE);
			else if(MAC_ADDR_EQUAL(pAd->ApCfg.wds_mac, pEntry->Addr))
				HW_SET_ASIC_WCID_4ADDR_HDR_TRANS(pAd, pEntry->wcid, TRUE);
		}
#endif

#ifdef HOSTAPD_MAP_SUPPORT
		if (IS_ENTRY_CLIENT(pEntry)) {
			BOOLEAN map_a4_peer_en = FALSE;
#if defined(MWDS) || defined(CONFIG_MAP_SUPPORT) || defined(WAPP_SUPPORT)
#if defined(CONFIG_MAP_SUPPORT)
			MTWF_LOG(DBG_CAT_SEC, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("MAP_ENABLE\n"));
#if defined(A4_CONN)
			map_a4_peer_en = map_a4_peer_enable(pAd, pEntry, TRUE);
#endif /* A4_CONN */
			map_send_bh_sta_wps_done_event(pAd, pEntry, TRUE);
#endif /* CONFIG_MAP_SUPPORT */
#ifdef WAPP_SUPPORT
			wapp_send_cli_join_event(pAd, pEntry);
#endif /* WAPP_SUPPORT */
#endif /* defined(MWDS) || defined(CONFIG_MAP_SUPPORT) || defined(WAPP_SUPPORT) */
		}
#endif /* HOSTAPD_MAP_SUPPORT */
	}
}

#ifdef RACTRL_FW_OFFLOAD_SUPPORT
/*
*
*/
VOID WifiSysRaInit(RTMP_ADAPTER *pAd, MAC_TABLE_ENTRY *pEntry)
{
	struct WIFI_SYS_CTRL wsys;
	struct _STA_REC_CTRL_T *sta_rec = &wsys.StaRecCtrl;
	struct _STA_TR_ENTRY *tr_entry = &pAd->MacTab.tr_entry[pEntry->tr_tb_idx];

	os_zero_mem(&wsys, sizeof(wsys));
	sta_rec->BssIndex = pEntry->wdev->bss_info_argument.ucBssIndex;
	sta_rec->WlanIdx = pEntry->wcid;
	sta_rec->ConnectionType = pEntry->ConnectionType;
	sta_rec->ConnectionState = STATE_CONNECTED;
	sta_rec->EnableFeature = STA_REC_RA_FEATURE;
	sta_rec->priv = tr_entry;
	wsys.wdev = pEntry->wdev;
	HW_WIFISYS_PEER_UPDATE(pAd, &wsys);
}


/*
*
*/
VOID WifiSysUpdateRa(RTMP_ADAPTER *pAd,
					 MAC_TABLE_ENTRY *pEntry,
					 P_CMD_STAREC_AUTO_RATE_UPDATE_T prParam
					)
{
	struct WIFI_SYS_CTRL wsys;
	struct _STA_REC_CTRL_T *sta_rec = &wsys.StaRecCtrl;
	struct _STA_TR_ENTRY *tr_entry = &pAd->MacTab.tr_entry[pEntry->tr_tb_idx];

	os_zero_mem(&wsys, sizeof(wsys));
	sta_rec->BssIndex = pEntry->wdev->bss_info_argument.ucBssIndex;
	sta_rec->WlanIdx = pEntry->wcid;
	sta_rec->ConnectionType = pEntry->ConnectionType;
	sta_rec->ConnectionState = STATE_CONNECTED;
	sta_rec->EnableFeature = STA_REC_RA_UPDATE_FEATURE;
	sta_rec->priv = tr_entry;
	if (!prParam)
		return;
	os_move_mem(&wsys.RaParam, prParam, sizeof(wsys.RaParam));
	wsys.ra_param_valid = TRUE;
	wsys.wdev = pEntry->wdev;
	HW_WIFISYS_RA_UPDATE(pAd, &wsys);
}
#endif /*RACTRL_FW_OFFLOAD_SUPPORT*/



VOID wifi_sys_update_wds(RTMP_ADAPTER *pAd, MAC_TABLE_ENTRY *pEntry)
{
	struct WIFI_SYS_CTRL wsys;
	struct wifi_dev *wdev = pEntry->wdev;
	struct _STA_REC_CTRL_T *sta_ctrl = &wsys.StaRecCtrl;
	struct _STA_TR_ENTRY *tr_entry = &pAd->MacTab.tr_entry[pEntry->tr_tb_idx];
	struct _STA_REC_CTRL_T *org = &tr_entry->StaRec;
	UINT32 features = 0;

	if (org->ConnectionState) {
		os_zero_mem(&wsys, sizeof(wsys));
		starec_feature_decision(wdev, pEntry->ConnectionType, pEntry, &features);
		sta_ctrl->BssIndex = wdev->bss_info_argument.ucBssIndex;
		sta_ctrl->ConnectionState = org->ConnectionState;
		sta_ctrl->ConnectionType = pEntry->ConnectionType;
		sta_ctrl->WlanIdx = pEntry->wcid;
		sta_ctrl->EnableFeature =  features;
		sta_ctrl->IsNewSTARec = FALSE;
		sta_ctrl->priv = tr_entry;
		wsys.wdev = wdev;
		HW_WIFISYS_PEER_UPDATE(pAd, &wsys);
	}
}

