/*
 ***************************************************************************
 * Ralink Tech Inc.
 * 4F, No. 2 Technology 5th Rd.
 * Science-based Industrial Park
 * Hsin-chu, Taiwan, R.O.C.
 *
 * (c) Copyright 2002-2004, Ralink Technology, Inc.
 *
 * All rights reserved. Ralink's source code is an unpublished work and the
 * use of a copyright notice does not imply otherwise. This source code
 * contains confidential trade secret material of Ralink Tech. Any attemp
 * or participation in deciphering, decoding, reverse engineering or in any
 * way altering the source code is stricitly prohibited, unless the prior
 * written consent of Ralink Technology, Inc. is obtained.
 ***************************************************************************

	Module Name:
	ee_flash.c

	Abstract:
	Miniport generic portion header file

	Revision History:
	Who         When          What
	--------    ----------    ----------------------------------------------
*/

#ifdef RTMP_FLASH_SUPPORT

#include "rt_config.h"
#include "hdev/hdev.h"

#ifdef CONFIG_WIFI_MTD
/*
* @ used mtd mode flash partition from proprietary driver mt_wifi_mtd.c
*/
int mt_mtd_write_nm_wifi(char *name, loff_t to, size_t len, const u_char *buf);
int mt_mtd_read_nm_wifi(char *name, loff_t from, size_t len, u_char *buf);

#define flash_read(_ctrl, _ptr, _offset, _len) mt_mtd_read_nm_wifi("Factory", _offset, (size_t)_len, _ptr)
#define flash_write(_ctrl, _ptr, _offset, _len) mt_mtd_write_nm_wifi("Factory", _offset, (size_t)_len, _ptr)

#endif /*CONFIG_WIFI_MTD*/


void RtmpFlashRead(
	void *hdev_ctrl,
	UCHAR *p,
	ULONG a,
	ULONG b)
{
	flash_read(hdev_ctrl, p, a, b);
}

void RtmpFlashWrite(
	void *hdev_ctrl,
	UCHAR *p,
	ULONG a,
	ULONG b)
{
	flash_write(hdev_ctrl, p, a, b);
}



static NDIS_STATUS rtmp_ee_flash_init(PRTMP_ADAPTER pAd, PUCHAR start);

INT RtmpFlashWriteChecked(void *hdev_ctrl, const UCHAR *p, ULONG a, ULONG b)
{
	/* Other legacy backends lack an audited persistence result. */
#ifdef CONFIG_WIFI_MTD
	if (!p && b)
		return -EINVAL;
	return flash_write(hdev_ctrl, p, a, b);
#else
	return -EOPNOTSUPP;
#endif
}

static BOOLEAN rtmp_ee_init_check(struct _RTMP_ADAPTER *ad)
{
	struct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(ad->hdev_ctrl);

	return cap->ee_inited;
}

#define IS_EE_INIT(_ad) (rtmp_ee_init_check(_ad))

/*******************************************************************************
  *
  *	Flash-based EEPROM read/write procedures.
  *		some chips use the flash memory instead of internal EEPROM to save the
  *		calibration info, we need these functions to do the read/write.
  *
  ******************************************************************************/
BOOLEAN rtmp_ee_flash_read(PRTMP_ADAPTER pAd, UINT16 Offset, UINT16 *pValue)
{
	BOOLEAN IsEmpty = 0;

	if (!IS_EE_INIT(pAd))
		*pValue = 0xffff;
	else
		memcpy(pValue, pAd->EEPROMImage + Offset, 2);

	if ((*pValue == 0xffff) || (*pValue == 0x0000))
		IsEmpty = 1;

	return IsEmpty;
}


int rtmp_ee_flash_write(PRTMP_ADAPTER pAd, USHORT Offset, USHORT Data)
{
	return rtmp_ee_flash_write_with_range(pAd, Offset, sizeof(Data), (UCHAR *)&Data);
}


BOOLEAN rtmp_ee_flash_read_with_range(PRTMP_ADAPTER pAd, UINT16 start, UINT16 Length, UCHAR *pbuf)
{
	BOOLEAN IsEmpty = 0;
	UINT16  u2Loop;
	UCHAR   ucValue = 0;

	if (!IS_EE_INIT(pAd))
		*pbuf = 0xff;
	else
		memcpy(pbuf, pAd->EEPROMImage + start, Length);

	for (u2Loop = 0; u2Loop < Length; u2Loop++)
		ucValue |= pbuf[u2Loop];

	if ((ucValue == 0xff) || (ucValue == 0x00))
		IsEmpty = 1;

	return IsEmpty;
}


int rtmp_ee_flash_write_with_range(PRTMP_ADAPTER pAd, USHORT start, USHORT Length, UCHAR *pbuf)
{
	UINT capacity = rtmp_ee_flash_image_capacity(pAd);
	UCHAR *image = NULL;
	INT status;

	if (!capacity || start > capacity || Length > capacity - start || (!pbuf && Length))
		return -EINVAL;
	if (!Length)
		return 0;
	if (os_alloc_mem(pAd, &image, capacity) != NDIS_STATUS_SUCCESS || !image)
		return -ENOMEM;
	memcpy(image, pAd->EEPROMImage, capacity);
	memmove(image + start, pbuf, Length);
	status = rtmp_ee_flash_write_image_checked(pAd, image, capacity);
	os_free_mem(image);
	return status;
}


VOID rtmp_ee_flash_read_all(PRTMP_ADAPTER pAd, USHORT *Data)
{
	if (!IS_EE_INIT(pAd))
		return;

	memcpy(Data, pAd->EEPROMImage, get_dev_eeprom_size(pAd));
}


VOID rtmp_ee_flash_write_all(PRTMP_ADAPTER pAd)
{
	if (!IS_EE_INIT(pAd))
		return;

	RtmpFlashWrite(pAd->hdev_ctrl, pAd->EEPROMImage, get_dev_eeprom_offset(pAd), get_dev_eeprom_size(pAd));
}


static NDIS_STATUS rtmp_ee_flash_reset(RTMP_ADAPTER *pAd, UCHAR *start)
{
	PUCHAR src;
	RTMP_OS_FS_INFO osFsInfo;
	RTMP_OS_FD srcf;
	INT retval;
	NDIS_STATUS status = NDIS_STATUS_FAILURE;
	UINT copy_size;
	EEPROM_CONTROL *pE2pCtrl = &pAd->E2pCtrl;
	struct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);

#ifdef RT_SOC_SUPPORT
#ifdef MULTIPLE_CARD_SUPPORT
	RTMP_STRING BinFilePath[128];
	RTMP_STRING *pBinFileName = NULL;
	UINT32	ChipVerion = (pAd->MACVersion >> 16);
	INT path_len;
	BOOLEAN local_path = FALSE;

	if (rtmp_get_default_bin_file_by_chip(pAd, ChipVerion, &pBinFileName) == TRUE) {
		if (!pBinFileName || !*pBinFileName)
			return NDIS_STATUS_FAILURE;
		path_len = snprintf(BinFilePath, sizeof(BinFilePath), "%s%s",
			pAd->MC_RowID > 0 ? EEPROM_2ND_FILE_DIR : EEPROM_1ST_FILE_DIR, pBinFileName);
		if (path_len < 0 || path_len >= sizeof(BinFilePath))
			return NDIS_STATUS_FAILURE;
		src = BinFilePath;
		local_path = TRUE;
		MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s(): src = %s\n", __func__, src));
	} else
#endif /* MULTIPLE_CARD_SUPPORT */
#endif /* RT_SOC_SUPPORT */
	{
#if defined(MT_MAC) && defined(MT7603)

		if (IS_MT7603(pAd))
			src = EEPROM_DEFAULT_7603_FILE_PATH;
		else
#endif /* MT_MAC && MT7603 */
		{
			src = EEPROM_DEFAULT_FILE_PATH;
		}
	}

	if (!start || get_dev_eeprom_size(pAd) < EEPROM_SIZE)
		return NDIS_STATUS_FAILURE;
	pE2pCtrl->e2pSource = E2P_SRC_FROM_BIN;
	RtmpOSFSInfoChange(&osFsInfo, TRUE);

	if (src && *src) {
		srcf = RtmpOSFileOpen(src, O_RDONLY, 0);

		if (IS_FILE_OPEN_ERR(srcf)) {
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
					 ("--> Error opening file %s\n", src));

			copy_size = cap->EEPROM_DEFAULT_BIN_SIZE > MAX_EEPROM_BUFFER_SIZE ?
				MAX_EEPROM_BUFFER_SIZE : cap->EEPROM_DEFAULT_BIN_SIZE;
			if (cap->EEPROM_DEFAULT_BIN != NULL && copy_size >= EEPROM_SIZE &&
				copy_size <= get_dev_eeprom_size(pAd)) {
				NdisMoveMemory(start, cap->EEPROM_DEFAULT_BIN, copy_size);
				MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("Load EEPROM Buffer from default BIN.\n"));
				pE2pCtrl->BinSource = "Default bin";
				status = NDIS_STATUS_SUCCESS;
			}
			goto out_restore;
		} else {
			/* The object must have a read method*/
			NdisZeroMemory(start, EEPROM_SIZE);
			retval = RtmpOSFileRead(srcf, start, EEPROM_SIZE);

			if (retval != EEPROM_SIZE) {
				MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("--> Read %s error %d\n", src, -retval));
			} else {
				MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,
						 ("--> rtmp_ee_flash_reset copy %s to eeprom buffer\n", src));
#if defined(RT_SOC_SUPPORT) && defined(MULTIPLE_CARD_SUPPORT)
				pE2pCtrl->BinSource = local_path ? "Multicard default bin" : (RTMP_STRING *)src;
#else
				pE2pCtrl->BinSource = src;
#endif
				status = NDIS_STATUS_SUCCESS;
			}

			retval = RtmpOSFileCloseChecked(srcf);

			if (retval) {
				status = NDIS_STATUS_FAILURE;
				MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
						 ("--> Error %d closing %s\n", -retval, src));
			}
		}
	}

out_restore:
	RtmpOSFSInfoChange(&osFsInfo, FALSE);
	return status;
}

#ifdef LINUX
/* 0 -- Show ee buffer */
/* 1 -- force reset to default */
/* 2 -- Change ee settings */
int	Set_EECMD_Proc(
	IN	PRTMP_ADAPTER	pAd,
	IN	PUCHAR			arg)
{
	USHORT i;
	i = os_str_tol(arg, 0, 10);

	switch (i) {
	case 0: {
		USHORT value, k;

		for (k = 0; k < EEPROM_SIZE; k += 2) {
			RT28xx_EEPROM_READ16(pAd, k, value);
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%4.4x ", value));

			if (((k + 2) % 0x20) == 0)
				MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("\n"));
		}
	}
	break;

	case 1:
		if (pAd->infType == RTMP_DEV_INF_RBUS) {
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("EEPROM reset to default......\n"));
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("The last byte of MAC address will be re-generated...\n"));

			if (rtmp_ee_flash_reset(pAd, pAd->EEPROMImage) != NDIS_STATUS_SUCCESS) {
				MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("Set_EECMD_Proc: rtmp_ee_flash_reset() failed\n"));
				return FALSE;
			}

			/* Random number for the last bytes of MAC address*/
			{
				USHORT  Addr45;
				rtmp_ee_flash_read(pAd, 0x08, &Addr45);
				Addr45 = Addr45 & 0xff;
				Addr45 = Addr45 | (RandomByte(pAd) & 0xf8) << 8;
				MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Addr45 = %4x\n", Addr45));
				rtmp_ee_flash_write(pAd, 0x08, Addr45);
			}
			rtmp_ee_flash_read(pAd, 0, &i);

			if ((i != 0x2880) && (i != 0x2860)) {
				MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("Set_EECMD_Proc: invalid eeprom\n"));
				return FALSE;
			}
		}

		break;

	case 2: {
		USHORT offset, value = 0;
		PUCHAR p;
		p = arg + 2;
		offset = os_str_tol(p, 0, 10);
		p += 2;

		while (*p != '\0') {
			if (*p >= '0' && *p <= '9')
				value = (value << 4) + (*p - 0x30);
			else if (*p >= 'a' && *p <= 'f')
				value = (value << 4) + (*p - 0x57);
			else if (*p >= 'A' && *p <= 'F')
				value = (value << 4) + (*p - 0x37);

			p++;
		}

		RT28xx_EEPROM_WRITE16(pAd, offset, value);
	}
	break;

	default:
		break;
	}

	return TRUE;
}
#endif /* LINUX */


static BOOLEAN  validFlashEepromID(RTMP_ADAPTER *pAd)
{
	USHORT eeFlashId;
	rtmp_ee_flash_read(pAd, 0, &eeFlashId);

	if ((pAd->ChipID & 0x0000ffff) == eeFlashId)
		return TRUE;

	return FALSE;
}


static NDIS_STATUS rtmp_ee_flash_init(PRTMP_ADAPTER pAd, PUCHAR start)
{
#ifdef CAL_FREE_IC_SUPPORT
	BOOLEAN bCalFree = 0;
#endif /* CAL_FREE_IC_SUPPORT */
	struct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);
	cap->ee_inited = 1;

	if (validFlashEepromID(pAd) == FALSE) {
		if (rtmp_ee_flash_reset(pAd, start) != NDIS_STATUS_SUCCESS) {
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("rtmp_ee_init(): rtmp_ee_flash_init() failed\n"));
			return NDIS_STATUS_FAILURE;
		}

#ifdef CAL_FREE_IC_SUPPORT
		RTMP_CAL_FREE_IC_CHECK(pAd, bCalFree);

		if (bCalFree) {
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("Cal Free IC!!\n"));
			RTMP_CAL_FREE_DATA_GET(pAd);
		} else
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Non Cal Free IC!!\n"));

#endif /* CAL_FREE_IC_SUPPORT */
		/* Random number for the last bytes of MAC address*/
		{
			USHORT  Addr45;
			rtmp_ee_flash_read(pAd, 0x08, &Addr45);
			Addr45 = Addr45 & 0xff;
			Addr45 = Addr45 | (RandomByte(pAd) & 0xf8) << 8;
			*(UINT16 *)(&pAd->EEPROMImage[0x08]) = le2cpu16(Addr45);
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("The EEPROM in Flash is wrong, use default\n"));
		}
		/* Validate the loaded buffer before replacing physical calibration. */
		if (validFlashEepromID(pAd) == FALSE) {
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				("rtmp_ee_flash_init(): invalid eeprom\n"));
			return NDIS_STATUS_FAILURE;
		}
		/*write back  all to flash*/
#ifdef CONFIG_WIFI_MTD
		if (mt_mtd_write_nm_wifi("Factory", get_dev_eeprom_offset(pAd),
			get_dev_eeprom_size(pAd), pAd->EEPROMImage)) {
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				("Factory EEPROM default writeback failed\n"));
			return NDIS_STATUS_FAILURE;
		}
#else
		rtmp_ee_flash_write_all(pAd);
#endif

	}

	return NDIS_STATUS_SUCCESS;
}


NDIS_STATUS rtmp_nv_init(RTMP_ADAPTER *pAd)
{
	NDIS_STATUS init_status;
	UINT image_size = get_dev_eeprom_size(pAd);
#ifdef CONFIG_WIFI_MTD
	INT read_status;
#endif
#ifdef MULTIPLE_CARD_SUPPORT
	UCHAR *eepromBuf;
#endif /* MULTIPLE_CARD_SUPPORT */
	EEPROM_CONTROL *pE2pCtrl = &pAd->E2pCtrl;
	struct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);

#ifdef PRE_CAL_TRX_SET2_SUPPORT
	/* Preserve live store contexts until their normal driver teardown. */
	if (pAd->PreCalStoreBuffer)
		return NDIS_STATUS_FAILURE;
#endif
	cap->ee_inited = 0;
	pE2pCtrl->e2pCurMode = E2P_NONE;
	pE2pCtrl->e2pSource = 0;
#ifdef PRE_CAL_MT7622_SUPPORT
	pAd->CalTXLPFGImage = NULL;
	pAd->CalTXDCIQImage = NULL;
	pAd->CalTXDPDImage = NULL;
#endif
#ifdef PRE_CAL_TRX_SET1_SUPPORT
	/* BIN calibration buffers are separate allocations; Flash uses views. */
	if (pAd->E2pAccessMode == E2P_BIN_MODE) {
		if (pAd->CalDCOCImage)
			os_free_mem(pAd->CalDCOCImage);
		if (pAd->CalDPDAPart1Image)
			os_free_mem(pAd->CalDPDAPart1Image);
		if (pAd->CalDPDAPart2Image)
			os_free_mem(pAd->CalDPDAPart2Image);
	}
	pAd->CalDCOCImage = NULL;
	pAd->CalDPDAPart1Image = NULL;
	pAd->CalDPDAPart2Image = NULL;
	pAd->bDCOCReloaded = FALSE;
	pAd->bDPDReloaded = FALSE;
#endif
	MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("--> rtmp_nv_init\n"));
	/*
		pAd->EEPROMImage:
		+----------------------------------------------------------------------------------+
		| 1K (calibration) | 9K (DCOC) | 9K (DPDA Part1) | 9K (DPDA Part2G) | 16K (PreCal) |
		+----------------------------------------------------------------------------------+
	 */
	if (pAd->EEPROMImage)
		os_free_mem(pAd->EEPROMImage);
	pAd->EEPROMImage = NULL;
	/* Reject a profile too small for the base EEPROM before any read. */
	if (image_size < EEPROM_SIZE)
		return NDIS_STATUS_FAILURE;

	os_alloc_mem(pAd, &pAd->EEPROMImage, image_size);
	if (pAd->EEPROMImage) {
		NdisZeroMemory(pAd->EEPROMImage, image_size);
#ifdef CONFIG_WIFI_MTD
		/* An IO failure is not an invalid EEPROM to replace with defaults. */
		read_status = mt_mtd_read_nm_wifi("Factory", get_dev_eeprom_offset(pAd),
			get_dev_eeprom_size(pAd), pAd->EEPROMImage);
		if (read_status) {
			MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				("Factory EEPROM read failed: %d\n", read_status));
			goto fail;
		}
#else
		RtmpFlashRead(pAd->hdev_ctrl, pAd->EEPROMImage, get_dev_eeprom_offset(pAd), get_dev_eeprom_size(pAd));
#endif

#ifdef PRE_CAL_MT7622_SUPPORT
		if (IS_MT7622(pAd)) {
			pAd->CalTXLPFGImage = pAd->EEPROMImage + TXLPFG_FLASH_OFFSET;
			pAd->CalTXDCIQImage = pAd->EEPROMImage + TXDCIQ_FLASH_OFFSET;
			pAd->CalTXDPDImage = pAd->EEPROMImage + TXDPD_FLASH_OFFSET;
		}
#endif /*PRE_CAL_MT7622_SUPPORT*/
#ifdef PRE_CAL_TRX_SET1_SUPPORT
		if (IS_MT7615(pAd)) {
			if (DCOC_OFFSET <= image_size && DCOC_IMAGE_SIZE <= image_size - DCOC_OFFSET)
				pAd->CalDCOCImage = pAd->EEPROMImage + DCOC_OFFSET;
			if (DPDPART1_OFFSET <= image_size && TXDPD_IMAGE1_SIZE <= image_size - DPDPART1_OFFSET)
				pAd->CalDPDAPart1Image = pAd->EEPROMImage + DPDPART1_OFFSET;
			if (DPDPART2_OFFSET <= image_size && TXDPD_IMAGE2_SIZE <= image_size - DPDPART2_OFFSET)
				pAd->CalDPDAPart2Image = pAd->EEPROMImage + DPDPART2_OFFSET;
			pAd->bDCOCReloaded = pAd->CalDCOCImage != NULL;
			pAd->bDPDReloaded = pAd->CalDPDAPart1Image && pAd->CalDPDAPart2Image;
		}
#endif /* PRE_CAL_TRX_SET1_SUPPORT */
		pE2pCtrl->e2pCurMode = E2P_FLASH_MODE;
		pE2pCtrl->e2pSource = E2P_SRC_FROM_FLASH;
		init_status = rtmp_ee_flash_init(pAd, pAd->EEPROMImage);
		if (init_status != NDIS_STATUS_SUCCESS)
			goto fail;
		pAd->E2pAccessMode = E2P_FLASH_MODE;
#ifdef PRE_CAL_TRX_SET1_SUPPORT
		if (IS_MT7615(pAd) && (!pAd->bDCOCReloaded || !pAd->bDPDReloaded)) {
			UINT16 do_cal;

			/* Consumers use the RAM request bits, not the reload flags. */
			NdisMoveMemory(&do_cal, pAd->EEPROMImage + 0x52, sizeof(do_cal));
			do_cal = le2cpu16(do_cal);
			if (!pAd->bDCOCReloaded)
				do_cal &= ~(1 << 1);
			if (!pAd->bDPDReloaded)
				do_cal &= ~(1 << 0);
			do_cal = le2cpu16(do_cal);
			NdisMoveMemory(pAd->EEPROMImage + 0x52, &do_cal, sizeof(do_cal));
		}
#endif
		return init_status;
	} else {
		MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,
				("Allocate %d-byte-of EEPROMImage failed.\n", get_dev_eeprom_size(pAd)));
		return NDIS_STATUS_FAILURE;
	}

fail:
	cap->ee_inited = 0;
	pE2pCtrl->e2pCurMode = E2P_NONE;
	pE2pCtrl->e2pSource = 0;
#ifdef PRE_CAL_MT7622_SUPPORT
	pAd->CalTXLPFGImage = NULL;
	pAd->CalTXDCIQImage = NULL;
	pAd->CalTXDPDImage = NULL;
#endif
#ifdef PRE_CAL_TRX_SET1_SUPPORT
	pAd->CalDCOCImage = NULL;
	pAd->CalDPDAPart1Image = NULL;
	pAd->CalDPDAPart2Image = NULL;
	pAd->bDCOCReloaded = FALSE;
	pAd->bDPDReloaded = FALSE;
#endif
	os_free_mem(pAd->EEPROMImage);
	pAd->EEPROMImage = NULL;
	return NDIS_STATUS_FAILURE;
}

#endif /* RTMP_FLASH_SUPPORT */

