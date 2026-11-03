"""Pure source-bound checked Flash/PA/QA models; no device or real file IO."""
import hashlib,json,re
SOURCE_PATHS = {'flash': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/ee_flash.c',
 'eeprom': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/eeprom.c',
 'ate': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/ate/mt_mac/mt_testmode.c',
 'hqa': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/ate/testmode_ioctl.c',
 'backend': 'trunk/linux-4.4.x/drivers/net/wireless/wifi_utility/mt_wifi_mtd.c',
 'os_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/rt_os_util.h',
 'eeprom_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/eeprom.h',
 'chip_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/hw_ctrl/cmm_chip.h',
 'adapter_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/rtmp.h',
 'profile': 'trunk/configs/boards/K2P/l1profile.dat',
 'hqa_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/ate/include/testmode_ioctl.h',
 'ate_header': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/ate/include/ate.h'}

FUNCTION_SOURCES = {'mt_mtd_erase_complete_wifi': 'backend',
 'mt_mtd_write_nm_wifi': 'backend',
 'RtmpFlashWrite': 'flash',
 'rtmp_ee_init_check': 'flash',
 'RtmpFlashWriteChecked': 'flash',
 'rtmp_ee_flash_image_capacity': 'eeprom',
 'rtmp_ee_flash_write_image_checked': 'eeprom',
 'rtmp_ee_flash_write_all_checked': 'eeprom',
 'rtmp_ee_flash_write': 'flash',
 'rtmp_ee_flash_write_with_range': 'flash',
 'rtmp_ee_flash_write_all': 'flash',
 'rtmp_ee_bin_capacity': 'eeprom',
 'rtmp_ee_bin_write16': 'eeprom',
 'Set_EepromBufferWriteBack_Proc': 'eeprom',
 'MtATE_PA_Trim_Proc': 'ate',
 'memcpy_exs': 'hqa',
 'EEWriteBulk': 'hqa',
 'HQA_WriteBulkEEPROM': 'hqa',
 'HQA_WriteBufferDone': 'hqa'}

BODY_ORDER = ('mt_mtd_erase_complete_wifi',
 'mt_mtd_write_nm_wifi',
 'RtmpFlashWrite',
 'rtmp_ee_init_check',
 'RtmpFlashWriteChecked',
 'rtmp_ee_flash_image_capacity',
 'rtmp_ee_flash_write_image_checked',
 'rtmp_ee_flash_write_all_checked',
 'rtmp_ee_flash_write',
 'rtmp_ee_flash_write_with_range',
 'rtmp_ee_flash_write_all',
 'rtmp_ee_bin_capacity',
 'rtmp_ee_bin_write16',
 'Set_EepromBufferWriteBack_Proc',
 'MtATE_PA_Trim_Proc',
 'memcpy_exs',
 'EEWriteBulk',
 'HQA_WriteBulkEEPROM',
 'HQA_WriteBufferDone')

NEW_FUNCTIONS = ('RtmpFlashWriteChecked',
 'rtmp_ee_flash_image_capacity',
 'rtmp_ee_flash_write_image_checked',
 'rtmp_ee_flash_write_all_checked')

BASELINE_COMMIT = '3ba292933a5cdbcaac3d5187d2454b387fbfbcc1'

CASE_NAMES = ('word-ok',
 'word-read-error',
 'word-short-read',
 'word-erase-submit-error',
 'word-erase-completion-error',
 'word-write-error',
 'word-short-write',
 'word-stage-alloc-error',
 'word-stage-alloc-null',
 'word-backend-alloc-error',
 'word-get-error',
 'word-uninitialized',
 'word-null-image',
 'word-mode-mismatch',
 'word-outside',
 'word-last-word',
 'word-cross-word',
 'range-ok',
 'range-null-input',
 'range-cross-range',
 'range-zero',
 'range-at-end-zero',
 'range-last-word',
 'range-alias',
 'range-outside',
 'range-max-length',
 'raw-ok',
 'raw-null-input',
 'raw-outside',
 'raw-zero',
 'raw-erase-submit-error',
 'raw-short-write',
 'commit-ok',
 'commit-length-mismatch',
 'commit-null-input',
 'commit-backend-alloc-error',
 'commit-write-error',
 'writeback-flash-ok',
 'writeback-read-error',
 'writeback-erase-submit-error',
 'writeback-write-error',
 'writeback-short-write',
 'writeback-uninitialized',
 'writeback-bin-bounded',
 'qa-ok',
 'qa-read-error',
 'qa-erase-submit-error',
 'qa-write-error',
 'qa-short-write',
 'qa-uninitialized',
 'pa-flash-ok',
 'pa-bin-ok',
 'pa-bin-uninitialized',
 'pa-read-error',
 'pa-short-read',
 'pa-erase-submit-error',
 'pa-erase-completion-error',
 'pa-write-error',
 'pa-short-write',
 'pa-stage-alloc-error',
 'pa-stage-alloc-null',
 'pa-backend-alloc-error',
 'pa-uninitialized',
 'pa-null-input',
 'pa-null-image',
 'pa-mode-mismatch',
 'pa-invalid-mode',
 'pa-nic-gone',
 'pa-nonmt',
 'pa-small-profile',
 'pa-repeat',
 'macro-ok',
 'macro-write-error',
 'macro-missing-op',
 'macro-null-adapter',
 'bulk-flash-ok',
 'bulk-endian-data',
 'bulk-sixteen-flash-ok',
 'bulk-end-flash-ok',
 'bulk-bin-ok',
 'bulk-sixteen-bin-ok',
 'bulk-end-write-error',
 'bulk-read-error',
 'bulk-short-read',
 'bulk-erase-submit-error',
 'bulk-erase-completion-error',
 'bulk-write-error',
 'bulk-short-write',
 'bulk-stage-alloc-error',
 'bulk-stage-alloc-null',
 'bulk-backend-alloc-error',
 'bulk-uninitialized',
 'bulk-mode-mismatch',
 'bulk-null-image',
 'bulk-outside',
 'bulk-cross',
 'bulk-offset-odd',
 'bulk-length-odd',
 'bulk-declared-short',
 'bulk-header-short',
 'bulk-truncated-actual',
 'bulk-truncated-payload',
 'bulk-declared-large',
 'bulk-zero',
 'bulk-at-end-zero',
 'bulk-eeprom-missing-op')

BASELINE_CASES = ('word-write-error',
 'word-short-write',
 'word-read-error',
 'word-uninitialized',
 'raw-erase-submit-error',
 'raw-short-write',
 'writeback-write-error',
 'writeback-uninitialized',
 'qa-write-error',
 'qa-uninitialized',
 'pa-flash-ok',
 'pa-bin-ok',
 'pa-bin-uninitialized',
 'pa-write-error',
 'pa-uninitialized',
 'pa-mode-mismatch',
 'pa-invalid-mode',
 'pa-nic-gone',
 'pa-repeat',
 'macro-write-error',
 'macro-missing-op',
 'bulk-flash-ok',
 'bulk-endian-data',
 'bulk-sixteen-flash-ok',
 'bulk-end-flash-ok',
 'bulk-bin-ok',
 'bulk-sixteen-bin-ok',
 'bulk-end-write-error',
 'bulk-stage-alloc-error',
 'bulk-eeprom-missing-op')

DISABLED_CASES = ('word-write-error', 'pa-write-error', 'qa-write-error', 'bulk-write-error')

BASELINE_FUNCTIONS = {'mt_mtd_erase_complete_wifi': 'static void mt_mtd_erase_complete_wifi(struct erase_info *ei)\n'
                               '{\n'
                               '\tcomplete((struct completion *)ei->priv);\n'
                               '}',
 'mt_mtd_write_nm_wifi': 'int mt_mtd_write_nm_wifi(char *name, loff_t to, size_t len, const u_char *buf)\n'
                         '{\n'
                         '\tint ret;\n'
                         '\tsize_t rdlen = 0, wrlen = 0;\n'
                         '\tstruct mtd_info *mtd;\n'
                         '\tstruct erase_info ei = { 0 };\n'
                         '\tu_char *bak = NULL;\n'
                         '#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))\n'
                         '\tDECLARE_COMPLETION_ONSTACK(erase_done);\n'
                         '#endif\n'
                         '\n'
                         '\tif (!name || (!buf && len))\n'
                         '\t\treturn -EINVAL;\n'
                         '\n'
                         '\tmtd = get_mtd_device_nm(name);\n'
                         '\tif (IS_ERR(mtd))\n'
                         '\t\treturn PTR_ERR(mtd);\n'
                         '\n'
                         '\t/* This helper preserves and rewrites only the first eraseblock. */\n'
                         '\tif (!mtd->erasesize || mtd->erasesize > mtd->size || to < 0 ||\n'
                         '\t    to > mtd->erasesize || len > mtd->erasesize - (size_t)to) {\n'
                         '\t\tret = len > mtd->erasesize ? -E2BIG : -EINVAL;\n'
                         '\t\tgoto out_put;\n'
                         '\t}\n'
                         '\tif (!len) {\n'
                         '\t\tret = 0;\n'
                         '\t\tgoto out_put;\n'
                         '\t}\n'
                         '\n'
                         '\tbak = kmalloc(mtd->erasesize, GFP_KERNEL);\n'
                         '\tif (bak == NULL) {\n'
                         '\t\tret = -ENOMEM;\n'
                         '\t\tgoto out_put;\n'
                         '\t}\n'
                         '\n'
                         '\tret = mtd_read(mtd, 0, mtd->erasesize, &rdlen, bak);\n'
                         '\n'
                         '\tif (ret)\n'
                         '\t\tgoto out_free;\n'
                         '\tif (rdlen != mtd->erasesize) {\n'
                         '\t\tret = -EIO;\n'
                         '\t\tgoto out_free;\n'
                         '\t}\n'
                         '\n'
                         '\tmemcpy(bak + to, buf, len);\n'
                         '\n'
                         '#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))\n'
                         '\tei.mtd = mtd;\n'
                         '\tei.callback = mt_mtd_erase_complete_wifi;\n'
                         '\tei.priv = (unsigned long)&erase_done;\n'
                         '#endif\n'
                         '\tei.addr = 0;\n'
                         '\tei.len = mtd->erasesize;\n'
                         '\tret = mtd_erase(mtd, &ei);\n'
                         '\n'
                         '\tif (ret)\n'
                         '\t\tgoto out_free;\n'
                         '#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))\n'
                         '\t/* The callback owns ei until completion, including asynchronous errors. */\n'
                         '\twait_for_completion(&erase_done);\n'
                         '\tif (ei.state != MTD_ERASE_DONE) {\n'
                         '\t\tret = -EIO;\n'
                         '\t\tgoto out_free;\n'
                         '\t}\n'
                         '#endif\n'
                         '\n'
                         '\tret = mtd_write(mtd, 0, mtd->erasesize, &wrlen, bak);\n'
                         '\tif (!ret && wrlen != mtd->erasesize)\n'
                         '\t\tret = -EIO;\n'
                         '\n'
                         'out_free:\n'
                         '\tkfree(bak);\n'
                         'out_put:\n'
                         '\tput_mtd_device(mtd);\n'
                         '\treturn ret;\n'
                         '}',
 'RtmpFlashWrite': 'void RtmpFlashWrite(\n'
                   '\tvoid *hdev_ctrl,\n'
                   '\tUCHAR *p,\n'
                   '\tULONG a,\n'
                   '\tULONG b)\n'
                   '{\n'
                   '\tflash_write(hdev_ctrl, p, a, b);\n'
                   '}',
 'rtmp_ee_init_check': 'static BOOLEAN rtmp_ee_init_check(struct _RTMP_ADAPTER *ad)\n'
                       '{\n'
                       '\tstruct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(ad->hdev_ctrl);\n'
                       '\n'
                       '\treturn cap->ee_inited;\n'
                       '}',
 'rtmp_ee_flash_write': 'int rtmp_ee_flash_write(PRTMP_ADAPTER pAd, USHORT Offset, USHORT Data)\n'
                        '{\n'
                        '\tif (IS_EE_INIT(pAd)) {\n'
                        '\t\tmemcpy(pAd->EEPROMImage + Offset, &Data, 2);\n'
                        '\t\t/*rt_nv_commit();*/\n'
                        '\t\t/*rt_cfg_commit();*/\n'
                        '\t\tRtmpFlashWrite(pAd->hdev_ctrl, pAd->EEPROMImage, get_dev_eeprom_offset(pAd), '
                        'get_dev_eeprom_size(pAd));\n'
                        '\t}\n'
                        '\n'
                        '\treturn 0;\n'
                        '}',
 'rtmp_ee_flash_write_with_range': 'int rtmp_ee_flash_write_with_range(PRTMP_ADAPTER pAd, USHORT start, '
                                   'USHORT Length, UCHAR *pbuf)\n'
                                   '{\n'
                                   '\tif (IS_EE_INIT(pAd)) {\n'
                                   '\t\tmemcpy(pAd->EEPROMImage + start, pbuf, Length);\n'
                                   '\t\t/*rt_nv_commit();*/\n'
                                   '\t\t/*rt_cfg_commit();*/\n'
                                   '\t\tRtmpFlashWrite(pAd->hdev_ctrl, pAd->EEPROMImage, '
                                   'get_dev_eeprom_offset(pAd), get_dev_eeprom_size(pAd));\n'
                                   '\t}\n'
                                   '\n'
                                   '\treturn 0;\n'
                                   '}',
 'rtmp_ee_flash_write_all': 'VOID rtmp_ee_flash_write_all(PRTMP_ADAPTER pAd)\n'
                            '{\n'
                            '\tif (!IS_EE_INIT(pAd))\n'
                            '\t\treturn;\n'
                            '\n'
                            '\tRtmpFlashWrite(pAd->hdev_ctrl, pAd->EEPROMImage, get_dev_eeprom_offset(pAd), '
                            'get_dev_eeprom_size(pAd));\n'
                            '}',
 'rtmp_ee_bin_capacity': 'static UINT rtmp_ee_bin_capacity(PRTMP_ADAPTER pAd)\n'
                         '{\n'
                         '\t/* EEPROMImage is allocated either by the hook (MAX_EEPROM_BUFFER_SIZE)\n'
                         '\t * or flash initialization (the profile size). Use their common lower\n'
                         '\t * bound rather than claiming that the profile is an allocation size. */\n'
                         '\tUINT size;\n'
                         '\n'
                         '\tif (!pAd->EEPROMImage)\n'
                         '\t\treturn 0;\n'
                         '\tsize = get_dev_eeprom_size(pAd);\n'
                         '\treturn size < MAX_EEPROM_BUFFER_SIZE ? size : MAX_EEPROM_BUFFER_SIZE;\n'
                         '}',
 'rtmp_ee_bin_write16': 'INT rtmp_ee_bin_write16(\n'
                        '\tIN RTMP_ADAPTER\t *pAd,\n'
                        '\tIN USHORT\t\t\tOffset,\n'
                        '\tIN USHORT\t\t\tdata)\n'
                        '{\n'
                        '\tUINT capacity = rtmp_ee_bin_capacity(pAd);\n'
                        '\n'
                        '\tif (Offset > capacity || 2 > capacity - Offset)\n'
                        '\t\treturn NDIS_STATUS_FAILURE;\n'
                        '\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_INFO, ("%s::Write to EEPROM '
                        'buffer\\n", __func__));\n'
                        '\tdata = le2cpu16(data);\n'
                        '\tNdisMoveMemory(&(pAd->EEPROMImage[Offset]), &data, 2);\n'
                        '\treturn 0;\n'
                        '}',
 'Set_EepromBufferWriteBack_Proc': 'INT Set_EepromBufferWriteBack_Proc(RTMP_ADAPTER *pAd, RTMP_STRING *arg)\n'
                                   '{\n'
                                   '\tUINT e2p_mode = os_str_tol(arg, 0, 10);\n'
                                   '\n'
                                   '\tif (e2p_mode >= NUM_OF_E2P_MODE)\n'
                                   '\t\treturn FALSE;\n'
                                   '\n'
                                   '\tswitch (e2p_mode) {\n'
                                   '#ifdef RTMP_EFUSE_SUPPORT\n'
                                   '\n'
                                   '\tcase E2P_EFUSE_MODE:\n'
                                   '\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Write EEPROM '
                                   'buffer back to eFuse\\n"));\n'
                                   '\t\trtmp_ee_write_to_efuse(pAd);\n'
                                   '\t\tbreak;\n'
                                   '#endif /* RTMP_EFUSE_SUPPORT */\n'
                                   '#ifdef RTMP_FLASH_SUPPORT\n'
                                   '\n'
                                   '\tcase E2P_FLASH_MODE:\n'
                                   '\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Write EEPROM '
                                   'buffer back to Flash\\n"));\n'
                                   '\t\trtmp_ee_flash_write_all(pAd);\n'
                                   '\t\tbreak;\n'
                                   '#endif /* RTMP_FLASH_SUPPORT */\n'
                                   '\n'
                                   '\tcase E2P_EEPROM_MODE:\n'
                                   '\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Write EEPROM '
                                   'buffer back to EEPROM\\n"));\n'
                                   '\t\trtmp_ee_write_to_prom(pAd);\n'
                                   '\t\tbreak;\n'
                                   '\n'
                                   '\tcase E2P_BIN_MODE:\n'
                                   '\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Write EEPROM '
                                   'buffer back to BIN\\n"));\n'
                                   '\t\treturn rtmp_ee_write_to_bin(pAd);\n'
                                   '\n'
                                   '\tdefault:\n'
                                   '\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("%s::do not '
                                   'support this EEPROM access mode\\n", __func__));\n'
                                   '\t\treturn FALSE;\n'
                                   '\t}\n'
                                   '\n'
                                   '\treturn TRUE;\n'
                                   '}',
 'MtATE_PA_Trim_Proc': 'INT MtATE_PA_Trim_Proc(RTMP_ADAPTER *pAd, PUINT32 pData)\n'
                       '{\n'
                       '\tUINT16 DoPATrim;\n'
                       '\tUINT16 WriteAddr;\n'
                       '\tUINT8 idx;\n'
                       '\tUSHORT *pStoreData = (USHORT *)pData;\n'
                       '\tUSHORT value;\n'
                       '\n'
                       '\tif (IS_MT7615(pAd)) {\n'
                       '\t\tWriteAddr = PA_TRIM_START_ADDR1;\n'
                       '\t\tfor (idx = 0; idx < PA_TRIM_BLOCK_SIZE; idx++) {\n'
                       '\t\t\tvalue = *pStoreData;\n'
                       '\t\t\tRT28xx_EEPROM_WRITE16(pAd, WriteAddr, value);\n'
                       '\t\t\tWriteAddr += 2;\n'
                       '\t\t\tpStoreData++;\n'
                       '\t\t}\n'
                       '\n'
                       '\t\tWriteAddr = PA_TRIM_START_ADDR2;\n'
                       '\t\tfor (idx = 0; idx < PA_TRIM_BLOCK_SIZE; idx++) {\n'
                       '\t\t\tvalue = *pStoreData;\n'
                       '\t\t\tRT28xx_EEPROM_WRITE16(pAd, \tWriteAddr, value);\n'
                       '\t\t\tWriteAddr += 2;\n'
                       '\t\t\tpStoreData++;\n'
                       '\t\t}\n'
                       '\n'
                       '\t\t/* Raise DoPATrim bits */\n'
                       '\t\tRT28xx_EEPROM_READ16(pAd, 0x52, DoPATrim);\n'
                       '\t\tDoPATrim |= (1 << 3);\n'
                       '\t\tRT28xx_EEPROM_WRITE16(pAd, 0x52, DoPATrim);\n'
                       '\n'
                       '\t}\n'
                       '\t\t\treturn TRUE;\n'
                       '}',
 'memcpy_exs': 'static VOID memcpy_exs(PRTMP_ADAPTER pAd, UCHAR *dst, UCHAR *src, ULONG len)\n'
               '{\n'
               '\tULONG i;\n'
               '\tUSHORT *pDst, *pSrc;\n'
               '\n'
               '\tpDst = (USHORT *) dst;\n'
               '\tpSrc = (USHORT *) src;\n'
               '\n'
               '\tfor (i = 0; i < (len >> 1); i++) {\n'
               '\t\t*pDst = PKTS_TRAN_TO_HOST(*pSrc);\n'
               '\t\tpDst++;\n'
               '\t\tpSrc++;\n'
               '\t}\n'
               '\n'
               '\tif ((len % 2) != 0) {\n'
               '\t\tmemcpy(pDst, pSrc, (len % 2));\n'
               '\t\t*pDst = PKTS_TRAN_TO_HOST(*pDst);\n'
               '\t}\n'
               '}',
 'EEWriteBulk': 'static VOID EEWriteBulk(PRTMP_ADAPTER pAd, UINT16 *Data, UINT16 Offset, UINT16 Length)\n'
                '{\n'
                '#if !defined(COMPOS_TESTMODE_WIN) /* 1Todo\tstruct _ATE_CTRL RT28xx_EEPROM_WRITE16 */\n'
                '\tUINT16 Pos;\n'
                '\tUINT16 Value;\n'
                '\tUINT16 Len = Length;\n'
                '\n'
                '\tfor (Pos = 0; Pos < (Len >> 1);) {\n'
                '\t\tValue = Data[Pos];\n'
                '\t\tRT28xx_EEPROM_WRITE16(pAd, Offset + (Pos * 2), Value);\n'
                '\t\tPos++;\n'
                '\t}\n'
                '\n'
                '#endif\n'
                '}',
 'HQA_WriteBulkEEPROM': 'static INT32 HQA_WriteBulkEEPROM(\n'
                        '\tPRTMP_ADAPTER pAd,\n'
                        '\tRTMP_IOCTL_INPUT_STRUCT *WRQ,\n'
                        '\tstruct _HQA_CMD_FRAME *HqaCmdFrame)\n'
                        '{\n'
                        '\tINT32 Ret = 0;\n'
                        '#if !defined(COMPOS_TESTMODE_WIN) /* 1Todo\t RT28xx_EEPROM_WRITE16 */\n'
                        '\tUSHORT Offset;\n'
                        '\tUSHORT Len;\n'
                        '\tUINT16 *Buffer = NULL;\n'
                        '\n'
                        '\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s\\n", __func__));\n'
                        '\tmemcpy(&Offset, HqaCmdFrame->Data, 2);\n'
                        '\tOffset = PKTS_TRAN_TO_HOST(Offset);\n'
                        '\tmemcpy(&Len, HqaCmdFrame->Data + 2, 2);\n'
                        '\tLen = PKTS_TRAN_TO_HOST(Len);\n'
                        '\tRet = os_alloc_mem(pAd, (PUCHAR *)&Buffer, EEPROM_SIZE);\t/* TODO verify */\n'
                        '\n'
                        '\tif (Ret == NDIS_STATUS_FAILURE) {\n'
                        '\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n'
                        '\t\t\t\t ("%s: allocate memory for read EEPROM fail\\n", __func__));\n'
                        '\t\tgoto HQA_WriteBulkEEPROM_RET;\n'
                        '\t}\n'
                        '\n'
                        '\tmemcpy_exs(pAd, (UCHAR *)Buffer + Offset, (UCHAR *)HqaCmdFrame->Data + 4, Len);\n'
                        '#if defined(RTMP_FLASH_SUPPORT)\n'
                        '\n'
                        '\tif (Len == 16)\n'
                        '\t\tmemcpy(pAd->EEPROMImage + Offset, (UCHAR *)Buffer + Offset, Len);\n'
                        '\n'
                        '\tif ((Offset + Len) == EEPROM_SIZE)\n'
                        '\t\trtmp_ee_flash_write_all(pAd);\n'
                        '\n'
                        '\tif (Len != 16)\n'
                        '#endif /* RTMP_FLASH_SUPPORT */\n'
                        '\t{\n'
                        '\t\tif ((Offset + Len) <= EEPROM_SIZE)\n'
                        '\t\t\tEEWriteBulk(pAd, (UINT16 *)(((UCHAR *)Buffer) + Offset), Offset, Len);\n'
                        '\t\telse {\n'
                        '\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n'
                        '\t\t\t\t\t ("%s: exceed EEPROM size(%d)\\n", __func__, EEPROM_SIZE));\n'
                        '\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n'
                        '\t\t\t\t\t ("Offset = %u\\n", Offset));\n'
                        '\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n'
                        '\t\t\t\t\t ("Length = %u\\n", Len));\n'
                        '\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n'
                        '\t\t\t\t\t ("Offset + Length=%u\\n", (Offset + Len)));\n'
                        '\t\t}\n'
                        '\t}\n'
                        '\n'
                        'HQA_WriteBulkEEPROM_RET:\n'
                        '\tResponseToQA(HqaCmdFrame, WRQ, 2 + Len, Ret);\n'
                        '\tif (Buffer)\n'
                        '\t\tos_free_mem(Buffer);\n'
                        '#endif\n'
                        '\treturn Ret;\n'
                        '}',
 'HQA_WriteBufferDone': 'static INT32 HQA_WriteBufferDone(\n'
                        '\tPRTMP_ADAPTER pAd,\n'
                        '\tRTMP_IOCTL_INPUT_STRUCT *WRQ,\n'
                        '\tstruct _HQA_CMD_FRAME *HqaCmdFrame)\n'
                        '{\n'
                        '\tUINT32 Value = 0;\n'
                        '\tINT32 Ret = 0;\n'
                        '\n'
                        '\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s\\n", __func__));\n'
                        '\tmemcpy((PUCHAR)&Value, (PUCHAR)&HqaCmdFrame->Data, 4);\n'
                        '\tValue = PKTL_TRAN_TO_HOST(Value);\n'
                        '#if !defined(COMPOS_TESTMODE_WIN) /* 1Todo\tSet_EepromBufferWriteBack_Proc */\n'
                        '\n'
                        '\tswitch (Value) {\n'
                        '\tcase E2P_EFUSE_MODE:\n'
                        '#ifdef RF_LOCKDOWN\n'
                        '\t\t/* update status of Effuse write back */\n'
                        '\t\tpAd->fgQAEffuseWriteBack = TRUE;\n'
                        '#endif /* RF_LOCKDOWN */\n'
                        '\t\tif (!Set_EepromBufferWriteBack_Proc(pAd, "1"))\n'
                        '\t\t\tRet = NDIS_STATUS_FAILURE;\n'
                        '\t\tbreak;\n'
                        '\n'
                        '\tcase E2P_FLASH_MODE:\n'
                        '\t\tif (!Set_EepromBufferWriteBack_Proc(pAd, "2"))\n'
                        '\t\t\tRet = NDIS_STATUS_FAILURE;\n'
                        '\t\tbreak;\n'
                        '\n'
                        '\tcase E2P_EEPROM_MODE:\n'
                        '\t\tif (!Set_EepromBufferWriteBack_Proc(pAd, "3"))\n'
                        '\t\t\tRet = NDIS_STATUS_FAILURE;\n'
                        '\t\tbreak;\n'
                        '\n'
                        '\tcase E2P_BIN_MODE:\n'
                        '\t\tif (!Set_EepromBufferWriteBack_Proc(pAd, "4"))\n'
                        '\t\t\tRet = NDIS_STATUS_FAILURE;\n'
                        '\t\tbreak;\n'
                        '\n'
                        '\tdefault:\n'
                        '\t\tRet = NDIS_STATUS_FAILURE;\n'
                        '\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                        '\t\t\t\t ("%s: Unknow write back mode(%d)\\n", __func__, Value));\n'
                        '\t}\n'
                        '\n'
                        '#endif\n'
                        '#ifdef RF_LOCKDOWN\n'
                        '\t/* update status of Effuse write back */\n'
                        '\tpAd->fgQAEffuseWriteBack = FALSE;\n'
                        '#endif /* RF_LOCKDOWN */\n'
                        '\tResponseToQA(HqaCmdFrame, WRQ, 2, Ret);\n'
                        '\treturn Ret;\n'
                        '}'}

BASELINE_FUNCTIONS_SHA256 = {'mt_mtd_erase_complete_wifi': '9be65d280452d441843dafe7de219a49bac2ce9cbc1cd255e4392f7e63a8b0ce',
 'mt_mtd_write_nm_wifi': 'fa29fc7d22b877f12b396ffe11b388bbbaf8f6d4c916e279db198dcc1cfaa2a4',
 'RtmpFlashWrite': 'd065c4742e7f51e52a14233a3ceb9f56e78ffdc131a18817737a1e7f194e6565',
 'rtmp_ee_init_check': '33f099596b3c6a37e46955537e13723722a6f397eaba0e620ca490f471bfe206',
 'rtmp_ee_flash_write': '0e54985e90a9765a7ae63103f73a2d2b382fa338e2c17c03934e0c98e994b148',
 'rtmp_ee_flash_write_with_range': '8e6387361aa7c1744c6d202d4ff47314be10d3c1b78c0d3d5a3445dbbd77769d',
 'rtmp_ee_flash_write_all': '9db48e528f4dd8c76c78cb1bdb7aa1d9c01055139c6e2ae7c633c21c42745792',
 'rtmp_ee_bin_capacity': '853ddb34ec601484d649a1a613d7e0fa46b49dc72f53e76da79752f35502f57f',
 'rtmp_ee_bin_write16': '87055542769d3445363d059420529642393988c6d641ac3aac0ad0a78804bacb',
 'Set_EepromBufferWriteBack_Proc': '24223fcbae6f13b1e73c96a0afaa5d7a99d080197efa0445ad108b790b53e9ec',
 'MtATE_PA_Trim_Proc': 'de5e55fe69284d390e3d5253e8b1f735484055401101f37d5445c20a486f565f',
 'memcpy_exs': 'c37d9c17d941e65c7d277977e1dea9082a2c55efa6fb10317b9e2020ccc450ba',
 'EEWriteBulk': '291c3600ca0533f089f97f203c81d990582f36317397c695f17dbc376713300c',
 'HQA_WriteBulkEEPROM': '11a8513313ad210bf76d602fad91f75e194c5cdffee56e3a3d5905bbc68eca74',
 'HQA_WriteBufferDone': '53f5321019109790d94758cd031d10d3bebfadaa3ee61bac868856dfb26b757d'}

DISABLED_STUBS = {'mt_mtd_erase_complete_wifi': 'static void mt_mtd_erase_complete_wifi(struct erase_info *ei)\n{return;}',
 'mt_mtd_write_nm_wifi': 'int mt_mtd_write_nm_wifi(char *name, loff_t to, size_t len, const u_char *buf)\n'
                         '{return 0;}',
 'RtmpFlashWrite': 'void RtmpFlashWrite(\n\tvoid *hdev_ctrl,\n\tUCHAR *p,\n\tULONG a,\n\tULONG b)\n{return;}',
 'rtmp_ee_init_check': 'static BOOLEAN rtmp_ee_init_check(struct _RTMP_ADAPTER *ad)\n{return 0;}',
 'RtmpFlashWriteChecked': 'INT RtmpFlashWriteChecked(void *hdev_ctrl, const UCHAR *p, ULONG a, ULONG b)\n'
                          '{return 0;}',
 'rtmp_ee_flash_image_capacity': 'UINT rtmp_ee_flash_image_capacity(PRTMP_ADAPTER pAd)\n{return 0;}',
 'rtmp_ee_flash_write_image_checked': 'INT rtmp_ee_flash_write_image_checked(PRTMP_ADAPTER pAd, const UCHAR '
                                      '*image, UINT length)\n'
                                      '{return 0;}',
 'rtmp_ee_flash_write_all_checked': 'INT rtmp_ee_flash_write_all_checked(PRTMP_ADAPTER pAd)\n{return 0;}',
 'rtmp_ee_flash_write': 'int rtmp_ee_flash_write(PRTMP_ADAPTER pAd, USHORT Offset, USHORT Data)\n{return 0;}',
 'rtmp_ee_flash_write_with_range': 'int rtmp_ee_flash_write_with_range(PRTMP_ADAPTER pAd, USHORT start, '
                                   'USHORT Length, UCHAR *pbuf)\n'
                                   '{return 0;}',
 'rtmp_ee_flash_write_all': 'VOID rtmp_ee_flash_write_all(PRTMP_ADAPTER pAd)\n{return;}',
 'rtmp_ee_bin_capacity': 'static UINT rtmp_ee_bin_capacity(PRTMP_ADAPTER pAd)\n{return 0;}',
 'rtmp_ee_bin_write16': 'INT rtmp_ee_bin_write16(\n'
                        '\tIN RTMP_ADAPTER\t *pAd,\n'
                        '\tIN USHORT\t\t\tOffset,\n'
                        '\tIN USHORT\t\t\tdata)\n'
                        '{return 0;}',
 'Set_EepromBufferWriteBack_Proc': 'INT Set_EepromBufferWriteBack_Proc(RTMP_ADAPTER *pAd, RTMP_STRING *arg)\n'
                                   '{return TRUE;}',
 'MtATE_PA_Trim_Proc': 'INT MtATE_PA_Trim_Proc(RTMP_ADAPTER *pAd, PUINT32 pData)\n{return TRUE;}',
 'memcpy_exs': 'static VOID memcpy_exs(PRTMP_ADAPTER pAd, UCHAR *dst, UCHAR *src, ULONG len)\n{return;}',
 'EEWriteBulk': 'static VOID EEWriteBulk(PRTMP_ADAPTER pAd, UINT16 *Data, UINT16 Offset, UINT16 Length)\n'
                '{return;}',
 'HQA_WriteBulkEEPROM': 'static INT32 HQA_WriteBulkEEPROM(\n'
                        '\tPRTMP_ADAPTER pAd,\n'
                        '\tRTMP_IOCTL_INPUT_STRUCT *WRQ,\n'
                        '\tstruct _HQA_CMD_FRAME *HqaCmdFrame)\n'
                        '{return 0;}',
 'HQA_WriteBufferDone': 'static INT32 HQA_WriteBufferDone(\n'
                        '\tPRTMP_ADAPTER pAd,\n'
                        '\tRTMP_IOCTL_INPUT_STRUCT *WRQ,\n'
                        '\tstruct _HQA_CMD_FRAME *HqaCmdFrame)\n'
                        '{return 0;}'}

DISABLED_STUB_SHA256 = {'mt_mtd_erase_complete_wifi': 'b98e17d438942412c85c156f9630d57104af1a27617b83175211c61bdb712985',
 'mt_mtd_write_nm_wifi': '7da2491ffd3ca6806934070ad7a58a6a708a2d7c27d812bfe14aa29ceb4982b8',
 'RtmpFlashWrite': '47ce7afb78ccdb7a5ce7d11cfaeaa480ee13c238b1fc0742f3f4fa773d5c3970',
 'rtmp_ee_init_check': '3305ab424078454990d1a58c2dd4fbabf2b23b3a6b3d8cc5348fa9e2f4323960',
 'RtmpFlashWriteChecked': 'd1a44b982b4fa5ea1a2da166bc6ea2638b0da84311345a50439a4a39aa1c2608',
 'rtmp_ee_flash_image_capacity': 'cc960111bbb28c0dee60a2d5082cc0821f7e32e1b241661f41a558fdfaff30da',
 'rtmp_ee_flash_write_image_checked': 'b2cfad2d0f6f35b2c712f4405b857fd38b8b8373c5e2397b05da20e8ecdde625',
 'rtmp_ee_flash_write_all_checked': 'ecc3c7f841c09811b54817f48a7a357750247bf0d846d9abf19654693596decf',
 'rtmp_ee_flash_write': 'd89452ccb0fdfb629c1681871c924d3c9a3ec14d515c3132f0e21b43c04b45eb',
 'rtmp_ee_flash_write_with_range': 'b52451ff6032d1289cf4acef0c96c870dde1ff305d3b9dbdaaae4d2e3bd37570',
 'rtmp_ee_flash_write_all': 'eca54f2bcb4d62a7e9f1d5469b1cef03e0a4033af128413684bb27daab1fd29a',
 'rtmp_ee_bin_capacity': '4d94abd3a98a182f6fda1f26e0c3a6b9424bb5cc065ccfa0dc35bce0490a56bb',
 'rtmp_ee_bin_write16': '8319c9cd485a8d566f8d1e9327cebeb44bbb8d58d5234fb89b64fdf582bd8621',
 'Set_EepromBufferWriteBack_Proc': '50c9674f2f75eb3d63294f45f0b01644e44b22b31fde30b46b1186fda70803ca',
 'MtATE_PA_Trim_Proc': '42c0fb9a83e3d173da438707655dd986c1d7e0eb5e2376e6bdb70561bc0305d4',
 'memcpy_exs': '395d78bf2a3bed5b81d88a253f42e5e539fca8274880646fe05a564db2f5b602',
 'EEWriteBulk': '69720cdd831c6aa562e1ffd116e5665d27b6ea8561465a1d02243078f4d80dac',
 'HQA_WriteBulkEEPROM': '5b0020b9a54f19bafc340948928e7f8b0efd8621e61ad50e672bb9d922491b64',
 'HQA_WriteBufferDone': '751b9c17028529004c48e2cbfdd5e834db0c222c1003cee2754e87aa841e209a'}

BASELINE_LEGACY_MACRO = ('#define RT28xx_EEPROM_WRITE16(_pAd, _offset, _val)\t\t\\\n'
 '\tdo {\\\n'
 '\t\tstruct _RTMP_CHIP_OP *ops = hc_get_chip_ops(_pAd->hdev_ctrl);\\\n'
 '\t\tif (ops->eewrite) \\\n'
 '\t\t\tops->eewrite(_pAd, (_offset), (USHORT)(_val));\\\n'
 '\t} while (0)')

BASELINE_MACRO_SHA256 = '1afac52b37aeaca57155b0d0110ceba4fef662f8a95dd67012e3551c1e63a6ef'

PREFIX = ('#include <stdint.h>\n'
 '#include <arpa/inet.h>\n'
 '#include <stddef.h>\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <string.h>\n'
 '#include <sys/types.h>\n'
 '#if !defined(__linux__)\n'
 'typedef long long loff_t;\n'
 '#endif\n'
 '#define IN\n'
 '#define CONFIG_WIFI_MTD 1\n'
 '#define RTMP_FLASH_SUPPORT 1\n'
 '#define RTMP_EFUSE_SUPPORT 1\n'
 '#define RF_LOCKDOWN 1\n'
 '#define LINUX_VERSION_CODE 0x040400\n'
 '#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))\n'
 '#define GFP_KERNEL 0\n'
 '#define EINVAL 22\n'
 '#define EIO 5\n'
 '#define ENOMEM 12\n'
 '#define EOPNOTSUPP 95\n'
 '#define E2BIG 7\n'
 '#define NDIS_STATUS_SUCCESS 0\n'
 '#define NDIS_STATUS_FAILURE 1\n'
 '#define TRUE 1\n'
 '#define FALSE 0\n'
 '#define E2P_EFUSE_MODE 1\n'
 '#define E2P_FLASH_MODE 2\n'
 '#define E2P_EEPROM_MODE 3\n'
 '#define E2P_BIN_MODE 4\n'
 '#define NUM_OF_E2P_MODE 5\n'
 '#define MAX_EEPROM_BUFFER_SIZE 1024\n'
 '#define EEPROM_SIZE 1024\n'
 '#define PA_TRIM_START_ADDR1 0x338\n'
 '#define PA_TRIM_START_ADDR2 0x3B3\n'
 '#define PA_TRIM_BLOCK_SIZE 4\n'
 '#define MTWF_LOG(a,b,c,args) do{if(0)printf args;}while(0)\n'
 '#define RTMP_TEST_FLAG(p,f) ((p)->nic_gone)\n'
 '#define fRTMP_ADAPTER_NIC_NOT_EXIST 1\n'
 '#define IS_MT7615(p) (is_mt)\n'
 '#define le2cpu16(v) (v)\n'
 '#define OS_NTOHS(v) ntohs(v)\n'
 '#define OS_NTOHL(v) ntohl(v)\n'
 'SOURCE_HQA_NETWORK\n'
 '#define GNU_PACKED __attribute__((packed))\n'
 '#define IOCTLBUFF 2048\n'
 '#define IS_ERR(v) ((intptr_t)(v)<0)\n'
 '#define PTR_ERR(v) ((intptr_t)(v))\n'
 '#define IS_EE_INIT(p) rtmp_ee_init_check(p)\n'
 '#define MTD_ERASE_DONE 1\n'
 '#define MTD_ERASE_FAILED 2\n'
 '#define ERASE_BYTES 65536\n'
 '#define NdisMoveMemory memmove\n'
 '#define NdisZeroMemory(p,n) memset(p,0,n)\n'
 'typedef uint8_t UCHAR,UINT8;typedef uint16_t USHORT,UINT16;typedef uint32_t UINT32;typedef unsigned int '
 'UINT;typedef unsigned long ULONG;typedef int INT,INT32,BOOLEAN,NDIS_STATUS;typedef void VOID;typedef char '
 'RTMP_STRING;typedef UCHAR*PUCHAR;typedef UINT32*PUINT32;\n'
 'struct _RTMP_ADAPTER;struct _RTMP_CHIP_OP{int(*eewrite)(struct _RTMP_ADAPTER*,USHORT,USHORT);};\n'
 'struct _RTMP_CHIP_CAP{int ee_inited;};\n'
 'typedef struct _RTMP_ADAPTER{UCHAR*EEPROMImage;void*hdev_ctrl;int '
 'E2pAccessMode,nic_gone,fgQAEffuseWriteBack;struct{int e2pCurMode;}E2pCtrl;}RTMP_ADAPTER,*PRTMP_ADAPTER;\n'
 'typedef struct{union{struct{char*pointer;UINT16 length,flags;}data;}u;}RTMP_IOCTL_INPUT_STRUCT;\n'
 'SOURCE_HQA_FRAME\n'
 'struct mtd_info{size_t erasesize,size;};\n'
 'struct erase_info{struct mtd_info*mtd;unsigned long priv;loff_t addr;size_t len;int '
 'state;void(*callback)(struct erase_info*);};\n'
 'struct completion{int done;};\n'
 '#define DECLARE_COMPLETION_ONSTACK(n) struct completion n={0}\n'
 'static struct _RTMP_CHIP_CAP cap;static struct _RTMP_CHIP_OP ops;static struct mtd_info '
 'dev={ERASE_BYTES,ERASE_BYTES};static struct erase_info*pending;\n'
 'static unsigned char flash[ERASE_BYTES],original_flash[ERASE_BYTES];static const char*case_name;static '
 'char trace[4096];\n'
 'static unsigned profile_size=16384,image_size;static int '
 'is_mt=1,allocs,frees_count,live_allocs,stage_allocs,backend_allocs,get_calls,put_calls,reads,erases,waits,writes,callbacks,bad_device,bad_wait,qa_status=999,qa_length,legacy_calls,last_offset,last_length;\n'
 'static int has(const char*s){return strstr(case_name,s)!=NULL;}\n'
 'static void event(const char*s){size_t '
 "n=strlen(trace);if(n)trace[n++]=',';if(n+strlen(s)>=sizeof(trace))abort();strcpy(trace+n,s);}\n"
 'static struct _RTMP_CHIP_CAP*hc_get_chip_cap(void*p){(void)p;return &cap;}\n'
 'static struct _RTMP_CHIP_OP*hc_get_chip_ops(void*p){(void)p;return &ops;}\n'
 'static UINT get_dev_eeprom_size(void*p){(void)p;return profile_size;}\n'
 'static UINT get_dev_eeprom_offset(void*p){(void)p;return 0;}\n'
 'static long os_str_tol(const char*s,void*e,int b){(void)e;return strtol(s,NULL,b);}\n'
 'static int os_alloc_mem(RTMP_ADAPTER*p,UCHAR**out,ULONG '
 'n){(void)p;allocs++;stage_allocs++;*out=NULL;event("stage-alloc");if(has("stage-alloc-error"))return '
 '1;if(has("stage-alloc-null"))return 0;*out=malloc(n?n:1);if(!*out)abort();live_allocs++;return 0;}\n'
 'static void os_free_mem(void*p){if(p){frees_count++;live_allocs--;event("stage-free");free(p);}}\n'
 'static void*kmalloc(size_t n,int '
 'flags){void*p;(void)flags;allocs++;backend_allocs++;event("backend-alloc");if(has("backend-alloc-error"))return '
 'NULL;p=malloc(n?n:1);if(!p)abort();live_allocs++;return p;}\n'
 'static void kfree(void*p){if(p){frees_count++;live_allocs--;event("backend-free");free(p);}}\n'
 'static struct '
 'mtd_info*get_mtd_device_nm(char*n){(void)n;get_calls++;event("get");if(has("get-error"))return (struct '
 'mtd_info*)(intptr_t)-19;return &dev;}\n'
 'static void put_mtd_device(struct mtd_info*d){put_calls++;event("put");if(d!=&dev)bad_device++;}\n'
 'static int mtd_read(struct mtd_info*d,loff_t off,size_t '
 'n,size_t*done,UCHAR*b){reads++;event("read");if(d!=&dev||off!=0||n!=ERASE_BYTES)bad_device++;*done=has("short-read")?n-1:n;if(has("read-error")){*done=0;return '
 '-EIO;}memcpy(b,flash,*done);return 0;}\n'
 'static int mtd_erase(struct mtd_info*d,struct '
 'erase_info*e){erases++;event("erase");if(d!=&dev||e->addr||e->len!=ERASE_BYTES)bad_device++;if(has("erase-submit-error"))return '
 '-EIO;memset(flash,0xff,sizeof(flash));pending=e;return 0;}\n'
 'static void complete(struct completion*c){callbacks++;event("callback");c->done=1;}\n'
 'static void wait_for_completion(struct '
 'completion*c){waits++;event("wait");if(!pending){bad_wait++;return;}pending->state=has("erase-completion-error")?MTD_ERASE_FAILED:MTD_ERASE_DONE;pending->callback(pending);pending=NULL;if(!c->done)bad_wait++;}\n'
 'static int mtd_write(struct mtd_info*d,loff_t off,size_t n,size_t*done,const '
 'UCHAR*b){writes++;event("write");if(d!=&dev||off||n!=ERASE_BYTES||pending)bad_device++;*done=has("write-error")?16:has("short-write")?n-1:n;memcpy(flash,b,*done);return '
 'has("write-error")?-EIO:0;}\n'
 '#define flash_write(c,p,o,n) mt_mtd_write_nm_wifi("Factory",o,n,p)\n'
 'static void rtmp_ee_write_to_efuse(RTMP_ADAPTER*p){(void)p;event("efuse");}\n'
 'static void rtmp_ee_write_to_prom(RTMP_ADAPTER*p){(void)p;event("prom");}\n'
 'static int rtmp_ee_write_to_bin(RTMP_ADAPTER*p){(void)p;event("bin");return !has("bin-error");}\n'
 'static int chip_eeprom_read16(RTMP_ADAPTER*p,USHORT '
 'o,USHORT*v){if(!p->EEPROMImage||o+2>image_size){*v=0xffff;return 1;}memcpy(v,p->EEPROMImage+o,2);return '
 '0;}\n'
 '#define RT28xx_EEPROM_READ16(p,o,v) chip_eeprom_read16(p,o,&(v))\n'
 'static void ResponseToQA(struct _HQA_CMD_FRAME*f,RTMP_IOCTL_INPUT_STRUCT*w,int n,int '
 'status){(void)f;(void)w;qa_length=n;qa_status=status;event("qa");}\n'
 '\n'
 'static uint32_t checksum(const UCHAR*p,size_t n){uint32_t h=2166136261u;size_t '
 'i;for(i=0;i<n;i++)h=(h^p[i])*16777619u;return h;}\n'
 '\n'
 'SOURCE_MACROS\n')

MAIN = ('int main(int argc,char**argv)\n'
 '{\n'
 ' RTMP_ADAPTER a;UCHAR before[16384],input[16],*source=input;UINT32 '
 'trim[4]={0x11223344,0x55667788,0x99aabbcc,0xddeeff00};UINT16 word=0;unsigned start=4,length=8;int '
 'result=0,known=0,unchanged,flash_unchanged;struct _HQA_CMD_FRAME q;RTMP_IOCTL_INPUT_STRUCT request;UINT32 '
 'mode=htonl(2);\n'
 ' if(argc!=2)return 90;\n'
 ' case_name=argv[1];\n'
 ' CASE_ADMISSION\n'
 ' if(!known)return 91;\n'
 ' '
 'memset(&a,0,sizeof(a));memset(&q,0,sizeof(q));memset(&request,0,sizeof(request));memset(flash,0x55,sizeof(flash));memset(input,0x33,sizeof(input));cap.ee_inited=1;a.E2pAccessMode=2;a.E2pCtrl.e2pCurMode=2;ops.eewrite=rtmp_ee_flash_write;\n'
 ' if(has("-eeprom")){a.E2pAccessMode=3;a.E2pCtrl.e2pCurMode=3;}\n'
 ' if(has("-bin")){a.E2pAccessMode=4;a.E2pCtrl.e2pCurMode=4;ops.eewrite=rtmp_ee_bin_write16;}\n'
 ' if(has("small-profile"))profile_size=512;\n'
 ' image_size=a.E2pAccessMode==2?profile_size:1024;\n'
 ' '
 'a.EEPROMImage=malloc(image_size);if(!a.EEPROMImage)abort();memset(a.EEPROMImage,0x55,image_size);a.EEPROMImage[0x52]=a.EEPROMImage[0x53]=0;\n'
 ' '
 'memcpy(flash,a.EEPROMImage,image_size);memcpy(original_flash,flash,sizeof(flash));memcpy(before,a.EEPROMImage,image_size);\n'
 ' if(has("uninitialized"))cap.ee_inited=0;\n'
 ' if(has("mode-mismatch"))a.E2pCtrl.e2pCurMode=0;\n'
 ' if(has("invalid-mode"))a.E2pAccessMode=a.E2pCtrl.e2pCurMode=0;\n'
 ' if(has("nic-gone"))a.nic_gone=1;\n'
 ' if(has("nonmt"))is_mt=0;\n'
 ' if(has("missing-op"))ops.eewrite=NULL;\n'
 ' if(has("null-input"))source=NULL;\n'
 ' if(has("last-word"))start=image_size-2;\n'
 ' if(has("cross-word"))start=image_size-1;\n'
 ' if(has("outside"))start=65535;\n'
 ' if(has("cross-range")){start=image_size-4;length=8;}\n'
 ' if(has("max-length"))length=65535;\n'
 ' if(has("zero"))length=0;\n'
 ' if(has("at-end"))start=image_size;\n'
 ' if(has("alias"))source=a.EEPROMImage+2;\n'
 ' if(has("null-image")){free(a.EEPROMImage);a.EEPROMImage=NULL;}\n'
 ' if(!strncmp(case_name,"word-",5))result=rtmp_ee_flash_write(&a,start,0x1234);\n'
 ' else if(!strncmp(case_name,"range-",6))result=rtmp_ee_flash_write_with_range(&a,start,length,source);\n'
 ' else if(!strncmp(case_name,"raw-",4)){\n'
 '  last_offset=has("outside")?ERASE_BYTES:4;last_length=has("zero")?0:8;\n'
 '  RAW_CALL\n'
 ' }\n'
 ' else if(!strncmp(case_name,"commit-",7)){\n'
 '  UCHAR staged[16384];memcpy(staged,before,image_size);staged[0]=0x33;\n'
 '  COMMIT_CALL\n'
 ' }\n'
 ' else if(!strncmp(case_name,"writeback-",10))result=Set_EepromBufferWriteBack_Proc(&a,"2");\n'
 ' else if(!strncmp(case_name,"bulk-",5)){\n'
 '  UINT16 off=4,len=8;unsigned payload;\n'
 '  if(has("sixteen")||has("end")){len=16;}\n'
 '  if(has("end"))off=EEPROM_SIZE-len;\n'
 '  if(has("outside"))off=65534;\n'
 '  if(has("cross"))off=EEPROM_SIZE-4;\n'
 '  if(has("offset-odd"))off=3;\n'
 '  if(has("length-odd"))len=7;\n'
 '  if(has("zero"))len=0;\n'
 '  if(has("at-end-zero"))off=EEPROM_SIZE;\n'
 '  payload=4+len;q.Length=htons(payload);\n'
 '  {UINT16 '
 'wire_off=htons(off),wire_len=htons(len);memcpy(q.Data,&wire_off,2);memcpy(q.Data+2,&wire_len,2);}\n'
 '  memset(q.Data+4,0x33,len);\n'
 '  if(has("endian-data")){q.Data[4]=0x12;q.Data[5]=0x34;}\n'
 '  request.u.data.length=offsetof(struct _HQA_CMD_FRAME,Data)+payload;\n'
 '  if(has("declared-short"))q.Length=htons(3);\n'
 '  if(has("declared-large"))q.Length=htons(sizeof(q.Data)+1);\n'
 '  if(has("header-short"))request.u.data.length=offsetof(struct _HQA_CMD_FRAME,Data)-1;\n'
 '  if(has("truncated-actual"))request.u.data.length--;\n'
 '  if(has("truncated-payload"))q.Length=htons(4);\n'
 '  result=HQA_WriteBulkEEPROM(&a,&request,&q);\n'
 ' }\n'
 ' else '
 'if(!strncmp(case_name,"qa-",3)){memcpy(q.Data,&mode,4);a.fgQAEffuseWriteBack=1;result=HQA_WriteBufferDone(&a,&request,&q);}\n'
 ' else '
 'if(!strncmp(case_name,"pa-",3)){result=MtATE_PA_Trim_Proc(&a,has("null-input")?NULL:trim);if(has("repeat"))result=MtATE_PA_Trim_Proc(&a,trim);}\n'
 ' else if(!strncmp(case_name,"macro-",6)){\n'
 '  RTMP_ADAPTER*p=has("null-adapter")?NULL:&a;\n'
 '  MACRO_CALL\n'
 ' }\n'
 ' else return 92;\n'
 ' '
 'unchanged=!a.EEPROMImage||!memcmp(before,a.EEPROMImage,image_size);flash_unchanged=!memcmp(original_flash,flash,sizeof(flash));\n'
 ' if(a.EEPROMImage)memcpy(&word,a.EEPROMImage+0x52,2);\n'
 ' '
 'printf("{\\"case\\":\\"%s\\",\\"result\\":%d,\\"allocs\\":%d,\\"frees\\":%d,\\"live_allocs\\":%d,\\"stage_allocs\\":%d,\\"backend_allocs\\":%d,\\"get_calls\\":%d,\\"put_calls\\":%d,\\"reads\\":%d,\\"erases\\":%d,\\"waits\\":%d,\\"callbacks\\":%d,\\"writes\\":%d,\\"bad_device\\":%d,\\"bad_wait\\":%d,\\"RAM_unchanged\\":%d,\\"Flash_unchanged\\":%d,\\"completion_bit\\":%d,\\"word4\\":%u,\\"trim1\\":%u,\\"trim2\\":%u,\\"qa_length\\":%d,\\"qa_status\\":%d,\\"qa_flag\\":%d,\\"last_offset\\":%d,\\"last_length\\":%d,\\"RAM_checksum\\":%u,\\"Flash_checksum\\":%u,\\"trace\\":\\"%s\\"}\\n",case_name,result,allocs,frees_count,live_allocs,stage_allocs,backend_allocs,get_calls,put_calls,reads,erases,waits,callbacks,writes,bad_device,bad_wait,unchanged,flash_unchanged,!!(word&8),a.EEPROMImage?(unsigned)a.EEPROMImage[4]:0,a.EEPROMImage&&image_size>PA_TRIM_START_ADDR1?(unsigned)a.EEPROMImage[PA_TRIM_START_ADDR1]:0,a.EEPROMImage&&image_size>PA_TRIM_START_ADDR2?(unsigned)a.EEPROMImage[PA_TRIM_START_ADDR2]:0,qa_length,qa_status,a.fgQAEffuseWriteBack,last_offset,last_length,a.EEPROMImage?checksum(a.EEPROMImage,image_size):0,checksum(flash,sizeof(flash)),trace);\n'
 ' free(a.EEPROMImage);return 0;\n'
 '}\n')

ABI_PROTOTYPES = {'os_header': ('INT RtmpFlashWriteChecked(void *hdev_ctrl, const UCHAR *p, ULONG a, ULONG b);',),
 'eeprom_header': ('UINT rtmp_ee_flash_image_capacity(struct _RTMP_ADAPTER *pAd);',
                   'INT rtmp_ee_flash_write_image_checked(struct _RTMP_ADAPTER *pAd, const UCHAR *image, '
                   'UINT length);',
                   'INT rtmp_ee_flash_write_all_checked(struct _RTMP_ADAPTER *pAd);')}

BASE_PROTOTYPES = {'eeprom_header': ('int rtmp_ee_flash_write_with_range(struct _RTMP_ADAPTER *pAd, USHORT start, USHORT '
                   'Length, UCHAR *pbuf);',)}

HQA_FRAME_DECLARATION = ('struct GNU_PACKED _HQA_CMD_FRAME {\n'
 '\tUINT32\t\tMagicNo;\n'
 '\tUINT16\t\tType;\n'
 '\tUINT16\t\tId;\n'
 '\tUINT16\t\tLength;\n'
 '\tUINT16\t\tSequence;\n'
 '\tUINT8\t\tData[IOCTLBUFF];\n'
 '};')

NETWORK_MACROS = ('#define PKTL_TRAN_TO_HOST(_Val) OS_NTOHL(_Val)', '#define PKTS_TRAN_TO_HOST(_Val) OS_NTOHS(_Val)')

def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'^(?:static\s+)?(?:void|VOID|int|INT|INT32|UINT|BOOLEAN|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked,re.M))
    if len(matches)!=1:raise ValueError('Missing/ambiguous BIN function '+name)
    start=matches[0].start();opening=text.index('{',start);depth=0
    for item in re.finditer(tokens+r'|[{}]',text[opening:]):
        if item.group()=='{':depth+=1
        elif item.group()=='}':
            depth-=1
            if not depth:return text[start:opening+item.end()]
    raise ValueError('Unterminated BIN function '+name)



def source_macro(text,name):
    lines=text.splitlines();matches=[]
    for i,line in enumerate(lines):
        if line.startswith('#define '+name+'('):
            out=[line];i+=1
            while out[-1].endswith('\\'):
                if i>=len(lines):raise ValueError('Unterminated checked EEPROM macro')
                out.append(lines[i]);i+=1
            matches.append('\n'.join(out))
    if len(matches)!=1:raise ValueError('Missing/ambiguous actual EEPROM macro '+name)
    return matches[0]


def actual_functions(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact Flash source keys required')
    return {name:{'source':key,'body':function(texts[key],name)}for name,key in FUNCTION_SOURCES.items()}


def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False,disabled_oracle=False):
    if type(baseline)is not bool or type(disabled_oracle)is not bool or(baseline and disabled_oracle):
        raise ValueError('Typed exclusive Flash profile required')
    if type(owner_uid)is not int or not 0<=owner_uid<2**32:raise ValueError('Typed compatibility UID required')
    current=actual_functions(texts)
    for key,declarations in ABI_PROTOTYPES.items():
        for declaration in declarations:
            if texts[key].count(declaration)!=1:raise ValueError('Checked Flash ABI declaration differs')
    for key,declarations in BASE_PROTOTYPES.items():
        for declaration in declarations:
            if texts[key].count(declaration)!=1:raise ValueError('Legacy Flash ABI declaration differs')
    prototypes='\n'.join(d for values in BASE_PROTOTYPES.values()for d in values)
    if not baseline:prototypes+='\n'+'\n'.join(d for values in ABI_PROTOTYPES.values()for d in values)
    if set(BASELINE_FUNCTIONS)!=set(FUNCTION_SOURCES)-set(NEW_FUNCTIONS):raise ValueError('Baseline function set differs')
    for name,body in BASELINE_FUNCTIONS.items():
        if hashlib.sha256(body.encode()).hexdigest()!=BASELINE_FUNCTIONS_SHA256[name]:raise ValueError('Changed Flash baseline')
    if hashlib.sha256(BASELINE_LEGACY_MACRO.encode()).hexdigest()!=BASELINE_MACRO_SHA256:raise ValueError('Changed baseline macro')
    legacy=source_macro(texts['chip_header'],'RT28xx_EEPROM_WRITE16')
    checked=source_macro(texts['chip_header'],'RT28xx_EEPROM_WRITE16_CHECKED')
    for literal in ('#define PA_TRIM_START_ADDR1   0x338','#define PA_TRIM_START_ADDR2   0x3B3','#define PA_TRIM_BLOCK_SIZE        4'):
        if literal not in texts['eeprom_header']:raise ValueError('Actual PA trim geometry differs')
    if '#define MAX_EEPROM_BUFFER_SIZE\t1024'not in texts['adapter_header']or'INDEX0_EEPROM_size=0x4000'not in texts['profile']:
        raise ValueError('Configured base/profile capacity differs')
    if any(texts['hqa_header'].count(m)!=1 for m in NETWORK_MACROS):raise ValueError('HQA network byte order contract differs')
    if texts['hqa_header'].count(HQA_FRAME_DECLARATION)!=1 or '#define IOCTLBUFF 2048'not in texts['ate_header']:
        raise ValueError('HQA actual frame geometry differs')
    bodies=BASELINE_FUNCTIONS if baseline else DISABLED_STUBS if disabled_oracle else {n:v['body']for n,v in current.items()}
    macros=BASELINE_LEGACY_MACRO if baseline else legacy+'\n'+checked
    if disabled_oracle:macros='#define RT28xx_EEPROM_WRITE16_CHECKED(p,o,v) 0'
    admission='\n'.join('if(!strcmp(case_name,'+json.dumps(n)+'))known=1;'for n in CASE_NAMES)
    main=MAIN.replace('CASE_ADMISSION',admission)
    main=main.replace('RAW_CALL','RtmpFlashWrite(NULL,source,last_offset,last_length);result=0;'if baseline else'result=RtmpFlashWriteChecked(NULL,source,last_offset,last_length);')
    main=main.replace('COMMIT_CALL','(void)staged;rtmp_ee_flash_write_all(&a);result=0;'if baseline else'result=rtmp_ee_flash_write_image_checked(&a,has("null-input")?NULL:staged,has("length-mismatch")?image_size-1:image_size);')
    main=main.replace('MACRO_CALL','result=0;RT28xx_EEPROM_WRITE16(p,4,0x1234);'if baseline else'result=RT28xx_EEPROM_WRITE16_CHECKED(p,4,0x1234);')
    return PREFIX.replace('SOURCE_MACROS',macros).replace('SOURCE_HQA_FRAME',HQA_FRAME_DECLARATION).replace('SOURCE_HQA_NETWORK','\n'.join(NETWORK_MACROS))+'\n'+prototypes+'\n'+'\n'.join(bodies[n]for n in BODY_ORDER if n in bodies)+'\n'+main
