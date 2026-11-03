"""Source-bound real-size MCU pre-calibration models with trusted queue and IO seams.

Current functions execute only in userspace with no hardware. Historical safe
controls use complete source events and bounded storage. No old short/overflow
input is executed. All fixtures release resident allocations after observations.
"""
import hashlib,json,re
SOURCE_PATHS = {'mcu': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/mcu/andes_mt.c',
 'rlm': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/phy/rlm_cal_cache.h',
 'cmd': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/mcu/mt_cmd.h',
 'andes': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/mcu/andes_mt.h',
 'chip': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/include/chip/mt7615.h',
 'tables': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/chips/mt7615.c',
 'eeprom': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/eeprom.c',
 'adapter': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/include/rtmp.h'}

FUNCTION_SOURCES = {'rtmp_precal_event_layout': 'mcu',
 'rtmp_precal_store_can_append': 'mcu',
 'ExtEventPreCalStoreProc': 'mcu',
 'PreCalTxLPFStoreProcHandler': 'mcu',
 'PreCalTxIQStoreProcHandler': 'mcu',
 'PreCalTxDCStoreProcHandler': 'mcu',
 'PreCalRxFIStoreProcHandler': 'mcu',
 'PreCalRxFDStoreProcHandler': 'mcu',
 'ExtEventTxLPFCalInfoHandler': 'mcu',
 'ExtEventTxIQCalInfoHandler': 'mcu',
 'ExtEventTxDCCalInfoHandler': 'mcu',
 'ExtEventRxFICalInfoHandler': 'mcu',
 'ExtEventRxFDCalInfoHandler': 'mcu',
 'AndesMTRxEventHandler': 'mcu',
 'rtmp_precal_records_valid': 'eeprom'}

BODY_ORDER = ('rtmp_precal_event_layout',
 'rtmp_precal_store_can_append',
 'ExtEventPreCalStoreProc',
 'PreCalTxLPFStoreProcHandler',
 'PreCalTxIQStoreProcHandler',
 'PreCalTxDCStoreProcHandler',
 'PreCalRxFIStoreProcHandler',
 'PreCalRxFDStoreProcHandler',
 'ExtEventTxLPFCalInfoHandler',
 'ExtEventTxIQCalInfoHandler',
 'ExtEventTxDCCalInfoHandler',
 'ExtEventRxFICalInfoHandler',
 'ExtEventRxFDCalInfoHandler',
 'AndesMTRxEventHandler',
 'rtmp_precal_records_valid')

NEW_FUNCTIONS = ('rtmp_precal_event_layout', 'rtmp_precal_store_can_append', 'rtmp_precal_records_valid')

BASELINE_COMMIT = '3ba292933a5cdbcaac3d5187d2454b387fbfbcc1'

BASELINE_FUNCTIONS = {'ExtEventPreCalStoreProc': 'static INT ExtEventPreCalStoreProc(RTMP_ADAPTER *pAd, UINT32 EventId, UINT8 '
                            '*Data)\n'
                            '{\n'
                            '\tUINT32 Offset = 0, IDOffset = 0, LenOffset = 0, HeaderSize = 0, CalDataSize = '
                            '0, BitMap = 0;\n'
                            '\tUINT32 i, Length, TotalSize, ChGroupId = 0;\n'
                            '\tUINT16 DoPreCal = 0;\n'
                            '\tstatic int rf_count;\n'
                            '\tint rf_countMax;\n'
                            '\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                            '\t\t\t ("\\x1b[41m %s ------------> \\x1b[m\\n", __FUNCTION__));\n'
                            '\trf_countMax = pAd->ChGrpMap == 0x1FF ? 9 : 6;\n'
                            '\n'
                            '\tswitch (EventId) {\n'
                            '\tcase PRECAL_TXLPF: {\n'
                            '\t\tTXLPF_CAL_INFO_T *prTxLPFGetEvent = (TXLPF_CAL_INFO_T *)Data;\n'
                            '\t\t/* Store header */\n'
                            '\t\tHeaderSize = (UINT32)(uintptr_t)&((TXLPF_CAL_INFO_T *)NULL)->au4Data[0];\n'
                            '\t\t/* Update Cal data size */\n'
                            '\t\tCalDataSize = TXLPF_PER_GROUP_DATA_SIZE;\n'
                            '\t\t/* Update channel group BitMap */\n'
                            '\t\tprTxLPFGetEvent->u2BitMap = le2cpu16(prTxLPFGetEvent->u2BitMap);\n'
                            '\t\tBitMap = prTxLPFGetEvent->u2BitMap;\n'
                            '\t\tfor (i = 0; i < CHANNEL_GROUP_NUM*SCN_NUM; i++)\n'
                            '\t\t\tprTxLPFGetEvent->au4Data[i] = le2cpu32(prTxLPFGetEvent->au4Data[i]);\n'
                            '\t}\n'
                            '\tbreak;\n'
                            '\n'
                            '\tcase PRECAL_TXIQ: {\n'
                            '\t\tTXIQ_CAL_INFO_T *prTxIQGetEvent = (TXIQ_CAL_INFO_T *)Data;\n'
                            '\t\t/* Store header */\n'
                            '\t\tHeaderSize = (UINT32)(uintptr_t)&((TXIQ_CAL_INFO_T *)NULL)->au4Data[0];\n'
                            '\t\t/* Update Cal data size */\n'
                            '\t\tCalDataSize = TXIQ_PER_GROUP_DATA_SIZE;\n'
                            '\t\t/* Update channel group BitMap */\n'
                            '\t\tprTxIQGetEvent->u2BitMap = le2cpu16(prTxIQGetEvent->u2BitMap);\n'
                            '\t\tBitMap = prTxIQGetEvent->u2BitMap;\n'
                            '\t\tfor (i = 0; i < CHANNEL_GROUP_NUM*SCN_NUM*6; i++)\n'
                            '\t\t\tprTxIQGetEvent->au4Data[i] = le2cpu32(prTxIQGetEvent->au4Data[i]);\n'
                            '\t}\n'
                            '\tbreak;\n'
                            '\n'
                            '\tcase PRECAL_TXDC: {\n'
                            '\t\tTXDC_CAL_INFO_T *prTxDCGetEvent = (TXDC_CAL_INFO_T *)Data;\n'
                            '\t\t/* Store header */\n'
                            '\t\tHeaderSize = (UINT32)(uintptr_t)&((TXDC_CAL_INFO_T *)NULL)->au4Data[0];\n'
                            '\t\t/* Update Cal data size */\n'
                            '\t\tCalDataSize = TXDC_PER_GROUP_DATA_SIZE;\n'
                            '\t\t/* Update channel group BitMap */\n'
                            '\t\tprTxDCGetEvent->u2BitMap = le2cpu16(prTxDCGetEvent->u2BitMap);\n'
                            '\t\tBitMap = prTxDCGetEvent->u2BitMap;\n'
                            '\t\tfor (i = 0; i < CHANNEL_GROUP_NUM*SCN_NUM*6; i++)\n'
                            '\t\t\tprTxDCGetEvent->au4Data[i] = le2cpu32(prTxDCGetEvent->au4Data[i]);\n'
                            '\t}\n'
                            '\tbreak;\n'
                            '\n'
                            '\tcase PRECAL_RXFI: {\n'
                            '\t\tRXFI_CAL_INFO_T *prRxFIGetEvent = (RXFI_CAL_INFO_T *)Data;\n'
                            '\t\t/* Store header */\n'
                            '\t\tHeaderSize = (UINT32)(uintptr_t)&((RXFI_CAL_INFO_T *)NULL)->au4Data[0];\n'
                            '\t\t/* Update Cal data size */\n'
                            '\t\tCalDataSize = RXFI_PER_GROUP_DATA_SIZE;\n'
                            '\t\t/* Update channel group BitMap */\n'
                            '\t\tprRxFIGetEvent->u2BitMap = le2cpu16(prRxFIGetEvent->u2BitMap);\n'
                            '\t\tBitMap = prRxFIGetEvent->u2BitMap;\n'
                            '\t\tfor (i = 0; i < CHANNEL_GROUP_NUM*SCN_NUM*4; i++)\n'
                            '\t\t\tprRxFIGetEvent->au4Data[i] = le2cpu32(prRxFIGetEvent->au4Data[i]);\n'
                            '\t}\n'
                            '\tbreak;\n'
                            '\n'
                            '\tcase PRECAL_RXFD: {\n'
                            '\t\tRXFD_CAL_INFO_T *prRxFDGetEvent = (RXFD_CAL_INFO_T *)Data;\n'
                            '\t\t/* Store header */\n'
                            '\t\tHeaderSize = (UINT32)(uintptr_t)&((RXFD_CAL_INFO_T *)NULL)->au4Data[0];\n'
                            '\t\t/* Update Cal data size */\n'
                            '\t\tCalDataSize = RXFD_PER_GROUP_DATA_SIZE;\n'
                            '\t\t/* Update channel group BitMap */\n'
                            '\t\tprRxFDGetEvent->u2BitMap = le2cpu16(prRxFDGetEvent->u2BitMap);\n'
                            '\t\tBitMap = prRxFDGetEvent->u2BitMap;\n'
                            '\t\t/* Update group ID */\n'
                            '\t\tprRxFDGetEvent->u4ChGroupId = le2cpu32(prRxFDGetEvent->u4ChGroupId);\n'
                            '\t\tChGroupId = prRxFDGetEvent->u4ChGroupId;\n'
                            '\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                            '\t\t\t\t ("\\x1b[33m%s: RXFD ChGroupId %d\\x1b[m\\n", __FUNCTION__, '
                            'ChGroupId));\n'
                            '\t\tfor (i = 0;\n'
                            '\t\ti < '
                            '(SCN_NUM*RX_SWAGC_LNA_NUM)+(SCN_NUM*RX_FDIQ_LPF_GAIN_NUM*RX_FDIQ_TABLE_SIZE*3);\n'
                            '\t\ti++)\n'
                            '\t\t\tprRxFDGetEvent->au4Data[i] = le2cpu32(prRxFDGetEvent->au4Data[i]);\n'
                            '\t}\n'
                            '\tbreak;\n'
                            '\n'
                            '\tdefault:\n'
                            '\t\tMTWF_LOG(DBG_CAT_CFG, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n'
                            '\t\t\t\t ("\\x1b[41m %s: Not support this calibration item !!!! \\x1b[m\\n", '
                            '__FUNCTION__));\n'
                            '\t\tbreak;\n'
                            '\t}\n'
                            '\n'
                            '\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                            '\t\t\t ("\\x1b[33m%s: EventID = %d, Bitmp = %x\\x1b[m\\n", __FUNCTION__, '
                            'EventId, BitMap));\n'
                            '\t/* Update offset parameter */\n'
                            '\tIDOffset = LenOffset = Offset = pAd->PreCalWriteOffSet;\n'
                            '\tLenOffset += 4; /*Skip ID field*/\n'
                            '\tOffset += 8; /*Skip (ID + Len) field*/\n'
                            '\n'
                            '\tif (pAd->PreCalStoreBuffer != NULL) {\n'
                            '\t\t/* Store ID */\n'
                            '\t\tos_move_mem(pAd->PreCalStoreBuffer + IDOffset, &EventId, sizeof(EventId));\n'
                            '\t\t/* Store header */\n'
                            '\t\tos_move_mem(pAd->PreCalStoreBuffer + Offset, Data, (ULONG)HeaderSize);\n'
                            '\t\tOffset += HeaderSize; /*Skip header*/\n'
                            '\t\tData += HeaderSize; /*Skip header*/\n'
                            '\n'
                            '\t\t/* Store pre-cal data */\n'
                            '\t\tif (EventId == PRECAL_RXFD) {\n'
                            '\t\t\tif ((rf_count < rf_countMax) && (BitMap & (1 << ChGroupId))) {\n'
                            '\t\t\t\trf_count++;\n'
                            '\t\t\t\tos_move_mem(pAd->PreCalStoreBuffer + Offset, Data, CalDataSize);\n'
                            '\t\t\t\tOffset += CalDataSize;\n'
                            '\t\t\t}\n'
                            '\t\t} else {\n'
                            '\t\t\tint count = 0;\n'
                            '\t\t\tint countMax = pAd->ChGrpMap == 0x1FF ? 8 : 5;\n'
                            '\n'
                            '\t\t\tfor (i = 0; i < CHANNEL_GROUP_NUM; i++) {\n'
                            '\t\t\t\tif (count > countMax)\n'
                            '\t\t\t\t\tbreak;\n'
                            '\n'
                            '\t\t\t\tif (BitMap & (1 << i)) {\n'
                            '\t\t\t\t\tcount++;\n'
                            '\t\t\t\t\tos_move_mem(pAd->PreCalStoreBuffer + Offset, Data + i * CalDataSize, '
                            'CalDataSize);\n'
                            '\t\t\t\t\tOffset += CalDataSize;\n'
                            '\t\t\t\t}\n'
                            '\t\t\t}\n'
                            '\t\t}\n'
                            '\n'
                            '\t\t/* Update current temp buffer write-offset */\n'
                            '\t\tpAd->PreCalWriteOffSet = Offset;\n'
                            '\t\t/* Calculate buffer size (len + header + data) for each calibration item '
                            '*/\n'
                            '\t\tLength = Offset - LenOffset;\n'
                            '\t\t/* Store buffer size for each calibration item */\n'
                            '\t\tos_move_mem(pAd->PreCalStoreBuffer + LenOffset, &Length, sizeof(Length));\n'
                            '\n'
                            '\t\t/* The last event ID - update calibration data to flash */\n'
                            '\t\tif (EventId == PRECAL_RXFI) {\n'
                            '\t\t\tTotalSize = pAd->PreCalWriteOffSet;\n'
                            '#ifdef RTMP_FLASH_SUPPORT\n'
                            '\t\t\t/* Write pre-cal data to flash */\n'
                            '\t\t\tif (pAd->E2pAccessMode == E2P_FLASH_MODE)\n'
                            '\t\t\t\tRtmpFlashWrite(pAd->hdev_ctrl, pAd->PreCalStoreBuffer,\n'
                            '\t\t\t\t\tget_dev_eeprom_offset(pAd) + PRECALPART_OFFSET, TotalSize);\n'
                            '#endif/* RTMP_FLASH_SUPPORT */\n'
                            '\t\t\tif (pAd->E2pAccessMode == E2P_BIN_MODE &&\n'
                            '\t\t\t    rtmp_cal_write_to_bin(pAd, pAd->PreCalStoreBuffer,\n'
                            '\t\t\t\tPRECALPART_OFFSET, TotalSize) != NDIS_STATUS_SUCCESS) {\n'
                            '\t\t\t\tpAd->PreCalWriteOffSet = 0;\n'
                            '\t\t\t\trf_count = 0;\n'
                            '\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n'
                            '\t\t\t\t\t("Pre-calibration BIN write failed; completion flag not '
                            'raised\\n"));\n'
                            '\t\t\t\treturn FALSE;\n'
                            '\t\t\t}\n'
                            '\n'
                            '\t\t\t/* Raise DoPreCal bits */\n'
                            '\t\t\tif (pAd->E2pAccessMode == E2P_FLASH_MODE || pAd->E2pAccessMode == '
                            'E2P_BIN_MODE) {\n'
                            '\t\t\t\tRT28xx_EEPROM_READ16(pAd, 0x52, DoPreCal);\n'
                            '\t\t\t\tDoPreCal |= (1 << 2);\n'
                            '\t\t\t\tRT28xx_EEPROM_WRITE16(pAd, 0x52, DoPreCal);\n'
                            '\t\t\t}\n'
                            '\n'
                            '\t\t\t/* Reset parameter */\n'
                            '\t\t\tpAd->PreCalWriteOffSet = 0;\n'
                            '\t\t\trf_count = 0;\n'
                            '\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n'
                            '\t\t\t\t\t ("\\x1b[41m %s: Pre-calibration done !! \\x1b[m\\n", '
                            '__FUNCTION__));\n'
                            '\t\t}\n'
                            '\t} else {\n'
                            '\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n'
                            '\t\t\t\t ("\\x1b[41m %s: PreCalStoreBuffer is NULL !! \\x1b[m\\n", '
                            '__FUNCTION__));\n'
                            '\t\treturn FALSE;\n'
                            '\t}\n'
                            '\n'
                            '\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                            '\t\t\t ("\\x1b[41m %s <------------ \\x1b[m\\n", __FUNCTION__));\n'
                            '\treturn TRUE;\n'
                            '}',
 'PreCalTxLPFStoreProcHandler': 'NTSTATUS PreCalTxLPFStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt '
                                'CMDQelmt)\n'
                                '{\n'
                                '\treturn ExtEventPreCalStoreProc(pAd, PRECAL_TXLPF, CMDQelmt->buffer) ?\n'
                                '\t\tNDIS_STATUS_SUCCESS : NDIS_STATUS_FAILURE;\n'
                                '}',
 'PreCalTxIQStoreProcHandler': 'NTSTATUS PreCalTxIQStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt CMDQelmt)\n'
                               '{\n'
                               '\treturn ExtEventPreCalStoreProc(pAd, PRECAL_TXIQ, CMDQelmt->buffer) ?\n'
                               '\t\tNDIS_STATUS_SUCCESS : NDIS_STATUS_FAILURE;\n'
                               '}',
 'PreCalTxDCStoreProcHandler': 'NTSTATUS PreCalTxDCStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt CMDQelmt)\n'
                               '{\n'
                               '\treturn ExtEventPreCalStoreProc(pAd, PRECAL_TXDC, CMDQelmt->buffer) ?\n'
                               '\t\tNDIS_STATUS_SUCCESS : NDIS_STATUS_FAILURE;\n'
                               '}',
 'PreCalRxFIStoreProcHandler': 'NTSTATUS PreCalRxFIStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt CMDQelmt)\n'
                               '{\n'
                               '\treturn ExtEventPreCalStoreProc(pAd, PRECAL_RXFI, CMDQelmt->buffer) ?\n'
                               '\t\tNDIS_STATUS_SUCCESS : NDIS_STATUS_FAILURE;\n'
                               '}',
 'PreCalRxFDStoreProcHandler': 'NTSTATUS PreCalRxFDStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt CMDQelmt)\n'
                               '{\n'
                               '\treturn ExtEventPreCalStoreProc(pAd, PRECAL_RXFD, CMDQelmt->buffer) ?\n'
                               '\t\tNDIS_STATUS_SUCCESS : NDIS_STATUS_FAILURE;\n'
                               '}',
 'ExtEventTxLPFCalInfoHandler': 'static VOID ExtEventTxLPFCalInfoHandler(\n'
                                '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                                '{\n'
                                '\thex_dump("P_TXLPF_CAL_INFO", Data, Length);\n'
                                '\n'
                                '\tif (RLM_PRECAL_TXLPF_TO_FLASH_CHECK(Data)) {\n'
                                '\t\t/* Store pre-cal data to flash */\n'
                                '\t\tRTEnqueueInternalCmd(pAd, CMDTHRED_PRECAL_TXLPF, (VOID *)Data, '
                                'Length);\n'
                                '\t} else {\n'
                                '\t\tRlmCalCacheTxLpfInfo(pAd->rlmCalCache, Data, Length);\n'
                                '\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                                '\t\t\t\t ("\\x1b[42m%s: Not store to flash !! \\x1b[m\\n", __FUNCTION__));\n'
                                '\t}\n'
                                '\n'
                                '\treturn;\n'
                                '}',
 'ExtEventTxIQCalInfoHandler': 'static VOID ExtEventTxIQCalInfoHandler(\n'
                               '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                               '{\n'
                               '\thex_dump("P_TXIQ_CAL_INFO", Data, Length);\n'
                               '\n'
                               '\tif (RLM_PRECAL_TXIQ_TO_FLASH_CHECK(Data)) {\n'
                               '\t\t/* Store pre-cal data to flash */\n'
                               '\t\tRTEnqueueInternalCmd(pAd, CMDTHRED_PRECAL_TXIQ, (VOID *)Data, Length);\n'
                               '\t} else {\n'
                               '\t\tRlmCalCacheTxIqInfo(pAd->rlmCalCache, Data, Length);\n'
                               '\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                               '\t\t\t\t ("\\x1b[42m%s: Not store to flash !! \\x1b[m\\n", __FUNCTION__));\n'
                               '\t}\n'
                               '\n'
                               '\treturn;\n'
                               '}',
 'ExtEventTxDCCalInfoHandler': 'static VOID ExtEventTxDCCalInfoHandler(\n'
                               '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                               '{\n'
                               '\thex_dump("P_TXDC_CAL_INFO", Data, Length);\n'
                               '\n'
                               '\tif (RLM_PRECAL_TXDC_TO_FLASH_CHECK(Data)) {\n'
                               '\t\t/* Store pre-cal data to flash */\n'
                               '\t\tRTEnqueueInternalCmd(pAd, CMDTHRED_PRECAL_TXDC, (VOID *)Data, Length);\n'
                               '\t} else {\n'
                               '\t\tRlmCalCacheTxDcInfo(pAd->rlmCalCache, Data, Length);\n'
                               '\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                               '\t\t\t\t ("\\x1b[42m%s: Not store to flash !! \\x1b[m\\n", __FUNCTION__));\n'
                               '\t}\n'
                               '\n'
                               '\treturn;\n'
                               '}',
 'ExtEventRxFICalInfoHandler': 'static VOID ExtEventRxFICalInfoHandler(\n'
                               '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                               '{\n'
                               '\thex_dump("P_RXFI_CAL_INFO", Data, Length);\n'
                               '\n'
                               '\tif (RLM_PRECAL_RXFI_TO_FLASH_CHECK(Data)) {\n'
                               '\t\t/* Store pre-cal data to flash */\n'
                               '\t\tRTEnqueueInternalCmd(pAd, CMDTHRED_PRECAL_RXFI, (VOID *)Data, Length);\n'
                               '\t} else {\n'
                               '\t\tRlmCalCacheRxFiInfo(pAd->rlmCalCache, Data, Length);\n'
                               '\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                               '\t\t\t\t ("\\x1b[42m%s: Not store to flash !! \\x1b[m\\n", __FUNCTION__));\n'
                               '\t}\n'
                               '\n'
                               '\treturn;\n'
                               '}',
 'ExtEventRxFDCalInfoHandler': 'static VOID ExtEventRxFDCalInfoHandler(\n'
                               '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                               '{\n'
                               '\thex_dump("P_RXFD_CAL_INFO", Data, Length);\n'
                               '\n'
                               '\tif (RLM_PRECAL_RXFD_TO_FLASH_CHECK(Data)) {\n'
                               '\t\t/* Store pre-cal data to flash */\n'
                               '\t\tRTEnqueueInternalCmd(pAd, CMDTHRED_PRECAL_RXFD, (VOID *)Data, Length);\n'
                               '\t} else {\n'
                               '\t\tRlmCalCacheRxFdInfo(pAd->rlmCalCache, Data, Length);\n'
                               '\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n'
                               '\t\t\t\t ("\\x1b[42m%s: Not store to flash !! \\x1b[m\\n", __FUNCTION__));\n'
                               '\t}\n'
                               '\n'
                               '\treturn;\n'
                               '}',
 'AndesMTRxEventHandler': 'VOID AndesMTRxEventHandler(RTMP_ADAPTER *pAd, UCHAR *data)\n'
                          '{\n'
                          '\tstruct cmd_msg *msg;\n'
                          '\tstruct MCU_CTRL *ctl = &pAd->MCUCtrl;\n'
                          '\tEVENT_RXD *event_rxd = (EVENT_RXD *)data;\n'
                          '\n'
                          '\tif (!OS_TEST_BIT(MCU_INIT, &ctl->flags))\n'
                          '\t\treturn;\n'
                          '\n'
                          '#ifdef RT_BIG_ENDIAN\n'
                          '\tevent_rxd->fw_rxd_0.word = le2cpu32(event_rxd->fw_rxd_0.word);\n'
                          '\tevent_rxd->fw_rxd_1.word = le2cpu32(event_rxd->fw_rxd_1.word);\n'
                          '\tevent_rxd->fw_rxd_2.word = le2cpu32(event_rxd->fw_rxd_2.word);\n'
                          '#endif\n'
                          '\tmsg = AndesAllocCmdMsg(pAd, GET_EVENT_FW_RXD_LENGTH(event_rxd));\n'
                          '\n'
                          '\tif (!msg)\n'
                          '\t\treturn;\n'
                          '\n'
                          '\tAndesAppendCmdMsg(msg, (char *)data, GET_EVENT_FW_RXD_LENGTH(event_rxd));\n'
                          '\tAndesMTRxProcessEvent(pAd, msg);\n'
                          '#if defined(RTMP_PCI_SUPPORT) || defined(RTMP_RBUS_SUPPORT)\n'
                          '\n'
                          '\tRTMPFreeNdisPacket(pAd, msg->net_pkt);\n'
                          '\n'
                          '#endif\n'
                          '\tAndesFreeCmdMsg(msg);\n'
                          '}'}

BASELINE_FUNCTIONS_SHA256 = {'ExtEventPreCalStoreProc': 'd82ba0f3299b617d54f7a72e0ccfad39ec689acd39cf6b3d4cbd9dec5eacca8d',
 'PreCalTxLPFStoreProcHandler': '5361ea42bbceee2d1fba2b7d3eecb4d426e01a975dea7dabb9b0ba967d9f33b3',
 'PreCalTxIQStoreProcHandler': '9776271442d275d5d07ab19bf8a6b38cb2edc7cd6dfe6519ff42a5e3f8c71db1',
 'PreCalTxDCStoreProcHandler': '3f12dafdafccdcb5409295af0864d6e79d90600375d5fbb01db6c5c2cf8421d6',
 'PreCalRxFIStoreProcHandler': '693ea36084448a54d3a478ca2730af4602c3a623f7d43e05bc7aa14a3ad764d9',
 'PreCalRxFDStoreProcHandler': '3a5f113062975fd7debc07f57fd1dc310448588169a9b69b45a901f53b195258',
 'ExtEventTxLPFCalInfoHandler': '3a29620b9321e2b45b41712e07903389631b1252df0be88491813d65d4e43abb',
 'ExtEventTxIQCalInfoHandler': '5ad3bb5316633926fa6934dbb1cf67c1ca19fae1011083a7a0afbc7a73ecdbba',
 'ExtEventTxDCCalInfoHandler': 'c2763bbdd0720438aadc08cf2c436f5615348e1c9ef811671e5a8fdd20cf263b',
 'ExtEventRxFICalInfoHandler': 'cf978fe70ba49eceb55c46eb23036cfb423ae3acc140ab4b9a76720913d4b205',
 'ExtEventRxFDCalInfoHandler': '103f37b958491be3b8a0631d9b5b0e56cd355a56fb62292499a0d5e862d347f5',
 'AndesMTRxEventHandler': '52b37aa57459d3e466f96df625f94742a37249b5f4e35b2e12e372f669d3322e'}

DISABLED_STUBS = {'rtmp_precal_event_layout': 'static BOOLEAN rtmp_precal_event_layout(UINT32 id, UINT32 *header,\n'
                             '\tUINT32 *input, UINT32 *size)\n'
                             '{ return FALSE; }',
 'rtmp_precal_store_can_append': 'static BOOLEAN rtmp_precal_store_can_append(RTMP_ADAPTER *pAd, UINT32 '
                                 'EventId,\n'
                                 '\tUINT32 ChGroupId, UINT32 used, UINT16 requested)\n'
                                 '{ return FALSE; }',
 'ExtEventPreCalStoreProc': 'static INT ExtEventPreCalStoreProc(RTMP_ADAPTER *pAd, UINT32 EventId,\n'
                            '\tUINT8 *Data, UINT32 DataLength)\n'
                            '{ return FALSE; }',
 'PreCalTxLPFStoreProcHandler': 'NTSTATUS PreCalTxLPFStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt '
                                'CMDQelmt)\n'
                                '{ return NDIS_STATUS_FAILURE; }',
 'PreCalTxIQStoreProcHandler': 'NTSTATUS PreCalTxIQStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt CMDQelmt)\n'
                               '{ return NDIS_STATUS_FAILURE; }',
 'PreCalTxDCStoreProcHandler': 'NTSTATUS PreCalTxDCStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt CMDQelmt)\n'
                               '{ return NDIS_STATUS_FAILURE; }',
 'PreCalRxFIStoreProcHandler': 'NTSTATUS PreCalRxFIStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt CMDQelmt)\n'
                               '{ return NDIS_STATUS_FAILURE; }',
 'PreCalRxFDStoreProcHandler': 'NTSTATUS PreCalRxFDStoreProcHandler(PRTMP_ADAPTER pAd, PCmdQElmt CMDQelmt)\n'
                               '{ return NDIS_STATUS_FAILURE; }',
 'ExtEventTxLPFCalInfoHandler': 'static VOID ExtEventTxLPFCalInfoHandler(\n'
                                '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                                '{ return; }',
 'ExtEventTxIQCalInfoHandler': 'static VOID ExtEventTxIQCalInfoHandler(\n'
                               '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                               '{ return; }',
 'ExtEventTxDCCalInfoHandler': 'static VOID ExtEventTxDCCalInfoHandler(\n'
                               '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                               '{ return; }',
 'ExtEventRxFICalInfoHandler': 'static VOID ExtEventRxFICalInfoHandler(\n'
                               '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                               '{ return; }',
 'ExtEventRxFDCalInfoHandler': 'static VOID ExtEventRxFDCalInfoHandler(\n'
                               '\tRTMP_ADAPTER *pAd, UINT8 *Data, UINT32 Length)\n'
                               '{ return; }',
 'AndesMTRxEventHandler': 'VOID AndesMTRxEventHandler(RTMP_ADAPTER *pAd, UCHAR *data)\n{ return; }',
 'rtmp_precal_records_valid': 'static BOOLEAN rtmp_precal_records_valid(const UCHAR *buffer, UINT32 size)\n'
                              '{ return FALSE; }'}

DISABLED_STUBS_SHA256 = {'rtmp_precal_event_layout': '2fd168033284300da61e8069b677892846457900bdeff6164ebaa5cf53007db5',
 'rtmp_precal_store_can_append': '07320baffade15c9052ddc36dbe641a9b56431a4d04774242bc3ec05ba7215ef',
 'ExtEventPreCalStoreProc': '645cb1b95d48a7cf320d5f8c481f1d646e607ff9e3d8d773a3b0604421ed10f9',
 'PreCalTxLPFStoreProcHandler': '9b85e315b7b38e19add7c5a602c6c6774ef8b80f40c563ba7fb6537f49f16424',
 'PreCalTxIQStoreProcHandler': '3161f83ab42338b9260ee6e03dd1fb190a09d41dce0ef14187de5de7a80c5f7b',
 'PreCalTxDCStoreProcHandler': '5327c6546b3b13dc0fc8ceb6d6a17df9f0d6770de4315271fb909c4f1cacf9ef',
 'PreCalRxFIStoreProcHandler': '9226a9df65aab4dd13677c7fcd249e15fcbe50b7dbff67d359577019a5c19c5d',
 'PreCalRxFDStoreProcHandler': '61f9cedf754f7e147800160d299f10926df6d32125e22e7ec551e29699db0d48',
 'ExtEventTxLPFCalInfoHandler': '7566da1a69ca6f4586e749efebedd0e9084eca86916755f1ddc438bab6b440b3',
 'ExtEventTxIQCalInfoHandler': '00ba4ccedf1bdefb8fbb0199734f1dabcd25988546c980ef0cc96d244f8c9107',
 'ExtEventTxDCCalInfoHandler': 'e0c79bac3a6a109a024b95b446c94460450c81579b17cc992d986c95c944e258',
 'ExtEventRxFICalInfoHandler': '985d9919a7eeaaf388dede34cd151b22b983a4a3cd2c9fba928eb31ad3c10d26',
 'ExtEventRxFDCalInfoHandler': '46286317524d774158d1d286705f2d03b3e96a3d06e2588ab9349c899386f0b8',
 'AndesMTRxEventHandler': 'e699193d1c3c3bd448a30b527c77d6fa0cb6ade2b6b55b6076ae3f4499c5e776',
 'rtmp_precal_records_valid': '26b581a16c47f33166f540aa5f4f11570b2c011c532c6dd473a504e575262769'}

RLM_MACROS = ('SCN_NUM','RX_SWAGC_LNA_NUM','RX_FDIQ_LPF_GAIN_NUM','RX_FDIQ_TABLE_SIZE','CHANNEL_GROUP_NUM',
 'TXLPF_PER_GROUP_DATA_SIZE','TXIQ_PER_GROUP_DATA_SIZE','TXDC_PER_GROUP_DATA_SIZE','RXFI_PER_GROUP_DATA_SIZE','RXFD_PER_GROUP_DATA_SIZE',
 'PRECAL_FLASH_MODE','RLM_PRECAL_TXLPF_TO_FLASH_CHECK','RLM_PRECAL_TXIQ_TO_FLASH_CHECK','RLM_PRECAL_TXDC_TO_FLASH_CHECK','RLM_PRECAL_RXFI_TO_FLASH_CHECK','RLM_PRECAL_RXFD_TO_FLASH_CHECK')
EVENT_TYPES = ('TXLPF_CAL_INFO_T','TXIQ_CAL_INFO_T','TXDC_CAL_INFO_T','RXFI_CAL_INFO_T','RXFD_CAL_INFO_T')
CHIP_MACROS = ('DCOC_IMAGE_SIZE','DCOC_OFFSET','DPDPART1_OFFSET','PRECALPART_OFFSET','PRE_CAL_SIZE_ONE_CARD')
CASE_NAMES = ('txlpf',
 'txiq',
 'txdc',
 'rxfi',
 'rxfd',
 'queued-txlpf',
 'queued-txiq',
 'queued-txdc',
 'queued-rxfi',
 'queued-rxfd',
 'upstream-txlpf',
 'upstream-txiq',
 'upstream-txdc',
 'upstream-rxfi',
 'upstream-rxfd',
 'short-txlpf',
 'short-txiq',
 'short-txdc',
 'short-rxfi',
 'short-rxfd',
 'queued-short-txlpf',
 'queued-short-txiq',
 'queued-short-txdc',
 'queued-short-rxfi',
 'queued-short-rxfd',
 'upstream-short-txlpf',
 'upstream-short-txiq',
 'upstream-short-txdc',
 'upstream-short-rxfi',
 'upstream-short-rxfd',
 'upstream-zero',
 'upstream-null',
 'upstream-cache',
 'null-data',
 'null-store',
 'invalid-id',
 'invalid-mode',
 'mixed-mode',
 'nic-gone',
 'halt',
 'bitmap-zero',
 'bitmap-high',
 'bitmap-unrequested',
 'requested-zero',
 'requested-high',
 'group-high',
 'group-unselected',
 'capacity-full',
 'capacity-beyond',
 'capacity-max',
 'capacity-one-short',
 'duplicate-txlpf',
 'duplicate-rxfd',
 'new-batch-rxfd',
 'two-adapters-rxfd',
 'old-short',
 'old-id',
 'old-length-zero',
 'old-length-max',
 'old-header-short',
 'old-bitmap-zero',
 'old-bitmap-high',
 'old-payload-short',
 'old-payload-long',
 'old-group-high',
 'old-group-unselected',
 'old-duplicate-rxfd',
 'old-duplicate-txlpf',
 'sequence-six',
 'sequence-nine',
 'bin-data-failure',
 'flash-data-failure',
 'bin-flag-failure',
 'flash-flag-failure',
 'flash-good',
 'flash-small',
 'flash-span-short',
 'flash-null-image',
 'flash-wrong-view',
 'outer-zero',
 'outer-one',
 'outer-four',
 'outer-eleven',
 'outer-twelve',
 'outer-payload',
 'outer-null',
 'outer-uninitialized',
 'outer-alloc-failure',
 'restore-one',
 'restore-six',
 'restore-nine',
 'restore-padded',
 'restore-subset-rxfd',
 'restore-null',
 'restore-zero',
 'restore-too-large',
 'restore-max',
 'restore-short-seven',
 'restore-truncated',
 'restore-length-zero',
 'restore-length-max',
 'restore-length-unaligned',
 'restore-id',
 'restore-header-short',
 'restore-payload-short',
 'restore-payload-long',
 'restore-bitmap-zero',
 'restore-bitmap-high',
 'restore-bitmap-mismatch',
 'restore-group-high',
 'restore-group-unselected',
 'restore-duplicate-rxfd',
 'restore-missing-rxfd',
 'restore-order',
 'restore-incomplete')
BASELINE_CASES = ('txlpf','txiq','txdc','rxfi','rxfd','queued-txlpf','upstream-txlpf','upstream-cache',
 'duplicate-txlpf','duplicate-rxfd','bin-data-failure','flash-data-failure','bin-flag-failure','flash-flag-failure','flash-good','outer-twelve','outer-payload')
DISABLED_CASES = ('txlpf', 'queued-txlpf', 'upstream-txlpf', 'outer-twelve', 'restore-one')
PREFIX = r'''
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char UCHAR,UINT8;
typedef signed char INT8;
typedef unsigned short UINT16;
typedef unsigned int UINT32,UINT;
typedef unsigned long ULONG;
typedef int INT,NTSTATUS,BOOLEAN;
typedef void VOID;
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define RTMP_FLASH_SUPPORT 1
#define RTMP_PCI_SUPPORT 1
#define GNU_PACKED __attribute__((packed))
#define E2P_BIN_MODE 4
#define E2P_FLASH_MODE 2
#define fRTMP_ADAPTER_NIC_NOT_EXIST 1
#define fRTMP_ADAPTER_HALT_IN_PROGRESS 2
#define RTMP_TEST_FLAG(p,f) ((p)->flags&(f))
#define le2cpu16(v) (v)
#define le2cpu32(v) (v)
#define os_move_mem memmove
#define MTWF_LOG(a,b,c,args) do { if(0)printf args; } while(0)
SOURCE_DECLARATIONS
struct MCU_CTRL{unsigned long flags;};
typedef struct {UINT16 PreCalWriteOffSet,ChGrpMap;int E2pAccessMode,flags;struct {int e2pCurMode;} E2pCtrl;
 UCHAR*PreCalStoreBuffer,*EEPROMImage;void*hdev_ctrl,*rlmCalCache;struct MCU_CTRL MCUCtrl;} RTMP_ADAPTER,*PRTMP_ADAPTER;
typedef struct{UCHAR*buffer;UINT32 bufferlength;} queue_item,*PCmdQElmt;
struct cmd_msg {UCHAR*net_pkt;UINT32 length;};
#define MCU_INIT 0
#define OS_TEST_BIT(n,p) ((*(p)&(1UL<<(n)))!=0)
#define CMDTHRED_PRECAL_TXLPF 0
#define CMDTHRED_PRECAL_TXIQ 1
#define CMDTHRED_PRECAL_TXDC 2
#define CMDTHRED_PRECAL_RXFI 3
#define CMDTHRED_PRECAL_RXFD 4
static const char*case_name;
static int data_status,flag_status,flash_calls,bin_calls,flag_calls,stamp_calls;
static int queue_calls,queue_status=-1,queue_length,cache_calls,dump_calls;
static int outer_allocs,outer_copies,outer_processes,outer_frees,outer_length,outer_payload;
static UINT16 completion;
static UINT32 image_capacity=36264,last_write;
static int get_dev_eeprom_size(RTMP_ADAPTER*p){(void)p;return image_capacity;}
static int get_dev_eeprom_offset(RTMP_ADAPTER*p){(void)p;return 0;}
static int RtmpFlashWriteChecked(void*c,const UCHAR*b,ULONG off,ULONG len){(void)c;(void)b;(void)off;flash_calls++;last_write=len;return data_status;}
static void RtmpFlashWrite(void*c,UCHAR*b,ULONG off,ULONG len){(void)RtmpFlashWriteChecked(c,b,off,len);}
static int rtmp_cal_write_to_bin(RTMP_ADAPTER*p,UCHAR*b,ULONG off,ULONG len){(void)p;(void)b;(void)off;bin_calls++;last_write=len;return data_status;}
static int complete_flag(RTMP_ADAPTER*p,int off,UINT16 value){(void)p;(void)off;flag_calls++;
 if(!flag_status){completion=value;stamp_calls++;}return flag_status;}
#define RT28xx_EEPROM_READ16(p,o,v) ((v)=completion)
#define RT28xx_EEPROM_WRITE16_CHECKED(p,o,v) complete_flag(p,o,v)
#define RT28xx_EEPROM_WRITE16(p,o,v) do{(void)complete_flag(p,o,v);}while(0)
static void hex_dump(const char*n,UINT8*d,UINT32 len){(void)n;(void)d;(void)len;dump_calls++;}
static int cache_info(void*p,UINT8*d,UINT32 len){(void)p;(void)d;(void)len;cache_calls++;return 0;}
#define RlmCalCacheTxLpfInfo cache_info
#define RlmCalCacheTxIqInfo cache_info
#define RlmCalCacheTxDcInfo cache_info
#define RlmCalCacheRxFiInfo cache_info
#define RlmCalCacheRxFdInfo cache_info
NTSTATUS PreCalTxLPFStoreProcHandler(PRTMP_ADAPTER,PCmdQElmt);
NTSTATUS PreCalTxIQStoreProcHandler(PRTMP_ADAPTER,PCmdQElmt);
NTSTATUS PreCalTxDCStoreProcHandler(PRTMP_ADAPTER,PCmdQElmt);
NTSTATUS PreCalRxFIStoreProcHandler(PRTMP_ADAPTER,PCmdQElmt);
NTSTATUS PreCalRxFDStoreProcHandler(PRTMP_ADAPTER,PCmdQElmt);
static NTSTATUS dispatch_queue(RTMP_ADAPTER*p,UINT32 id,queue_item*q){switch(id){
 case PRECAL_TXLPF:return PreCalTxLPFStoreProcHandler(p,q);case PRECAL_TXIQ:return PreCalTxIQStoreProcHandler(p,q);
 case PRECAL_TXDC:return PreCalTxDCStoreProcHandler(p,q);case PRECAL_RXFI:return PreCalRxFIStoreProcHandler(p,q);
 case PRECAL_RXFD:return PreCalRxFDStoreProcHandler(p,q);default:return NDIS_STATUS_FAILURE;}}
/* Trusted CMDQ seam copies exactly the real InformationBufferLength and then
 * invokes the whole production queue wrapper; no driver thread is executed. */
static int RTEnqueueInternalCmd(RTMP_ADAPTER*p,UINT32 id,VOID*data,UINT32 length){queue_item q;
 queue_calls++;queue_length=length;q.buffer=malloc(length?length:1);
 if(!q.buffer)return 1;
 q.bufferlength=length;memcpy(q.buffer,data,length);queue_status=dispatch_queue(p,id,&q);free(q.buffer);return queue_status;}
static struct cmd_msg*AndesAllocCmdMsg(RTMP_ADAPTER*p,UINT32 len){struct cmd_msg*m;(void)p;outer_allocs++;outer_length=len;
 if(!strcmp(case_name,"outer-alloc-failure"))return NULL;
 m=malloc(sizeof(*m));
 if(!m)exit(97);
 m->net_pkt=malloc(len?len:1);
 if(!m->net_pkt)exit(98);
 m->length=len;return m;}
static void AndesAppendCmdMsg(struct cmd_msg*m,char*d,UINT32 len){outer_copies++;memcpy(m->net_pkt,d,len);}
/* Processor seam records the production header-subtraction macro, not the
 * full unsolicited dispatcher or transport receive pipeline. */
static void AndesMTRxProcessEvent(RTMP_ADAPTER*p,struct cmd_msg*m){(void)p;outer_processes++;outer_payload=GET_EVENT_HDR_ADD_PAYLOAD_TOTAL_LEN((EVENT_RXD*)m->net_pkt);}
static void RTMPFreeNdisPacket(RTMP_ADAPTER*p,UCHAR*b){(void)p;free(b);}
static void AndesFreeCmdMsg(struct cmd_msg*m){outer_frees++;free(m);}
'''
MAIN = r'''
static UINT32 checksum(const UCHAR*p,UINT32 len){UINT32 value=2166136261U,i;for(i=0;i<len;i++){value^=p[i];value*=16777619U;}return value;}
static int is(const char*n){return !strcmp(case_name,n);}
static int has(const char*n){return strstr(case_name,n)!=NULL;}
static UINT32 event_size(UINT32 id){switch(id){case 0:return sizeof(TXLPF_CAL_INFO_T);case 1:return sizeof(TXIQ_CAL_INFO_T);case 2:return sizeof(TXDC_CAL_INFO_T);case 3:return sizeof(RXFI_CAL_INFO_T);default:return sizeof(RXFD_CAL_INFO_T);}}
static UINT32 event_header(UINT32 id){return id==0||id==4?8:4;}
static UCHAR*make_event(UINT32 id,UINT16 bitmap,UINT32 group,UINT32 length){UCHAR*p;UINT32 i,value;UINT32 size=event_size(id),header=event_header(id);
 p=malloc(length?length:1);
 if(!p)exit(94);
 memset(p,0,length);
 /* All setup writes fit the allocation, including short input fixtures. */
 if(length>0)p[0]=1;
 if(length>1)p[1]=1;
 if(length>=4)memcpy(p+2,&bitmap,2);
 if(id==4&&length>=8)memcpy(p+4,&group,4);
 for(i=header;i+4<=length&&i<size;i+=4){value=0x12340000U+i;memcpy(p+i,&value,4);}return p;}
static int store_event(RTMP_ADAPTER*p,UINT32 id,UINT16 bitmap,UINT32 group){UINT32 len=event_size(id);UCHAR*d=make_event(id,bitmap,group,len);int r; r=CALL_STORE(p,id,d,len);free(d);return r;}
/* Trusted serialized-file fixture builder, independent of the event appender. */
static UINT32 fixture_record(UCHAR*p,UINT32 id,UINT16 bitmap,UINT32 group){UINT32 count=0,i,header=event_header(id),size=24,length,total;
 if(id==1||id==2)size=144;
 if(id==3)size=96;
 if(id==4){size=1344;count=1;}else for(i=0;i<9;i++)if(bitmap&(1U<<i))count++;
 total=8+header+count*size;length=total-4;memset(p,0,total);memcpy(p,&id,4);memcpy(p+4,&length,4);p[8]=1;p[9]=1;memcpy(p+10,&bitmap,2);
 if(id==4)memcpy(p+12,&group,4);
 return total;}
static UINT32 fixture_stream(UCHAR*p,UINT16 bitmap){UINT32 used=0,i;used+=fixture_record(p+used,0,bitmap,0);used+=fixture_record(p+used,1,bitmap,0);used+=fixture_record(p+used,2,bitmap,0);
 for(i=0;i<9;i++)if(bitmap&(1U<<i))used+=fixture_record(p+used,4,bitmap,i);
 used+=fixture_record(p+used,3,bitmap,0);return used;}
static void upstream(RTMP_ADAPTER*p,UINT32 id,UCHAR*d,UINT32 len){switch(id){case 0:ExtEventTxLPFCalInfoHandler(p,d,len);break;case 1:ExtEventTxIQCalInfoHandler(p,d,len);break;case 2:ExtEventTxDCCalInfoHandler(p,d,len);break;case 3:ExtEventRxFICalInfoHandler(p,d,len);break;case 4:ExtEventRxFDCalInfoHandler(p,d,len);break;}}
int main(int argc,char**argv){RTMP_ADAPTER a,b;queue_item q;UCHAR *store,*image,*data,*prior,*bstore=NULL;UINT32 id=0,len,group=0,i,v,before,after,prior_offset=0,original,used,total=0;UINT16 bitmap=1;int r=-1,known=0,unchanged,source_unchanged,accepted=0,restore_unchanged=1;
 if(argc!=2)return 90;
 case_name=argv[1];CASE_ADMISSION
 if(!known)return 91;
 if(sizeof(TXLPF_CAL_INFO_T)!=224||sizeof(TXIQ_CAL_INFO_T)!=1300||sizeof(TXDC_CAL_INFO_T)!=1300||sizeof(RXFI_CAL_INFO_T)!=868||sizeof(RXFD_CAL_INFO_T)!=1352||sizeof(EVENT_RXD)!=12||PRECALPART_OFFSET!=19880||PRE_CAL_SIZE_ONE_CARD!=16384)return 92;
 memset(&a,0,sizeof(a));a.E2pAccessMode=4;a.E2pCtrl.e2pCurMode=4;a.ChGrpMap=0x1ff;a.MCUCtrl.flags=1;
 store=malloc(PRE_CAL_SIZE_ONE_CARD);image=malloc(36264);prior=malloc(PRE_CAL_SIZE_ONE_CARD);
 if(!store||!image||!prior)return 93;
 memset(store,0x5a,PRE_CAL_SIZE_ONE_CARD);
 memset(image,0x5a,36264);a.PreCalStoreBuffer=store;a.EEPROMImage=image;
 if(has("txiq"))id=1;else if(has("txdc"))id=2;else if(has("rxfi")||has("data-failure")||has("flag-failure")||!strncmp(case_name,"flash-",6))id=3;else if(has("rxfd")||has("group-"))id=4;
 if(!strncmp(case_name,"flash-",6)){a.E2pAccessMode=a.E2pCtrl.e2pCurMode=2;a.PreCalStoreBuffer=image+PRECALPART_OFFSET;}
 if(is("flash-small"))image_capacity=16384;
 if(is("flash-span-short"))image_capacity=36263;
 if(is("flash-null-image"))a.EEPROMImage=NULL;
 if(is("flash-wrong-view"))a.PreCalStoreBuffer=store;
 if(is("bin-data-failure")||is("flash-data-failure"))data_status=-5;
 if(is("bin-flag-failure")||is("flash-flag-failure"))flag_status=-5;
 if(is("invalid-mode"))a.E2pAccessMode=a.E2pCtrl.e2pCurMode=1;
 if(is("mixed-mode"))a.E2pCtrl.e2pCurMode=2;
 if(is("nic-gone"))a.flags=1;
 if(is("halt"))a.flags=2;
 if(is("bitmap-zero"))bitmap=0;
 if(is("bitmap-high"))bitmap=0x200;
 if(is("bitmap-unrequested")){bitmap=2;a.ChGrpMap=1;}if(is("requested-zero"))a.ChGrpMap=0;
 if(is("requested-high"))a.ChGrpMap=0x200;
 if(is("group-high"))group=9;
 if(is("group-unselected")){bitmap=1;group=1;}
 if(has("duplicate-")&&!has("old-")){if(!store_event(&a,id,bitmap,group))return 95;}
 if(is("new-batch-rxfd")){if(!store_event(&a,4,1,0))return 95;a.PreCalWriteOffSet=0;}
 if(is("two-adapters-rxfd")){b=a;bstore=malloc(PRE_CAL_SIZE_ONE_CARD);
 if(!bstore)return 94;
 memset(bstore,0x5a,PRE_CAL_SIZE_ONE_CARD);b.PreCalStoreBuffer=bstore;for(i=0;i<6;i++){a.ChGrpMap=b.ChGrpMap=0x3f;
 if(!store_event(&a,4,0x3f,i)||!store_event(&b,4,0x3f,i))return 95;}a.PreCalWriteOffSet=0;bitmap=0x3f;}
 if(has("old-")){if(!store_event(&a,0,1,0))return 95;id=1;
  if(is("old-short"))a.PreCalWriteOffSet=7;
  if(is("old-id")){v=99;memcpy(a.PreCalStoreBuffer,&v,4);}
  if(is("old-length-zero")){v=0;memcpy(a.PreCalStoreBuffer+4,&v,4);}
  if(is("old-length-max")){v=0xffffffffU;memcpy(a.PreCalStoreBuffer+4,&v,4);}
  if(is("old-header-short")){v=8;memcpy(a.PreCalStoreBuffer+4,&v,4);a.PreCalWriteOffSet=12;}
  if(is("old-bitmap-zero")){v=0;memcpy(a.PreCalStoreBuffer+10,&v,2);}
  if(is("old-bitmap-high")){v=0x200;memcpy(a.PreCalStoreBuffer+10,&v,2);}
  if(is("old-payload-short")){v=35;memcpy(a.PreCalStoreBuffer+4,&v,4);a.PreCalWriteOffSet=39;}
  if(is("old-payload-long")){v=40;memcpy(a.PreCalStoreBuffer+4,&v,4);a.PreCalWriteOffSet=44;}
  if(has("old-group")||is("old-duplicate-rxfd")){a.PreCalWriteOffSet=0;
 if(!store_event(&a,4,1,0))return 95;
   if(is("old-group-high")){v=9;memcpy(a.PreCalStoreBuffer+12,&v,4);}if(is("old-group-unselected")){v=1;memcpy(a.PreCalStoreBuffer+12,&v,4);}
   if(is("old-duplicate-rxfd")){memcpy(a.PreCalStoreBuffer+1360,a.PreCalStoreBuffer,1360);a.PreCalWriteOffSet=2720;}}
  if(is("old-duplicate-txlpf")){memcpy(a.PreCalStoreBuffer+40,a.PreCalStoreBuffer,40);a.PreCalWriteOffSet=80;}
 }
 if(is("capacity-full"))a.PreCalWriteOffSet=16384;
 if(is("capacity-beyond"))a.PreCalWriteOffSet=16385;
 if(is("capacity-max"))a.PreCalWriteOffSet=0xffffU;
 if(is("capacity-one-short"))a.PreCalWriteOffSet=16345;
 len=event_size(id);
 if(has("short-"))len--;
 if(is("upstream-zero"))len=0;
 data=make_event(id,bitmap,group,len);original=checksum(data,len);
 if(is("upstream-cache"))data[0]=0;
 memcpy(prior,a.PreCalStoreBuffer,PRE_CAL_SIZE_ONE_CARD);prior_offset=a.PreCalWriteOffSet;before=checksum(prior,PRE_CAL_SIZE_ONE_CARD);
 if(!strncmp(case_name,"outer-",6)){UCHAR wire[20];UINT32 n=12;
 memset(wire,0,sizeof(wire));
  if(is("outer-zero"))n=0;
 if(is("outer-one"))n=1;
 if(is("outer-four"))n=4;
 if(is("outer-eleven"))n=11;
 if(is("outer-payload"))n=20;
  memcpy(wire,&n,4);
 if(is("outer-uninitialized"))a.MCUCtrl.flags=0;
  AndesMTRxEventHandler(&a,is("outer-null")?NULL:wire);r=outer_processes;
 }else if(!strncmp(case_name,"restore-",8)){UINT32 n=fixture_stream(store,1),rxfd_offset=352,second_rxfd=1712;UINT16 bits=0;UCHAR*validation;UINT32 physical,validation_hash;
 if(is("restore-six"))n=fixture_stream(store,0x3f);
 if(is("restore-nine")||is("restore-subset-rxfd")||is("restore-duplicate-rxfd")||is("restore-missing-rxfd")){n=fixture_stream(store,0x1ff);rxfd_offset=2848;second_rxfd=4208;}
 if(is("restore-padded"))n=16384;
 if(is("restore-subset-rxfd")){for(i=0;i<9;i++){bits=1U<<i;memcpy(store+rxfd_offset+1360*i+10,&bits,2);}}
 if(is("restore-zero"))n=0;
 if(is("restore-too-large"))n=16385;
 if(is("restore-max"))n=0xffffffffU;
 if(is("restore-short-seven"))n=7;
 if(is("restore-truncated"))n--;
 if(is("restore-length-zero")){v=0;memcpy(store+4,&v,4);}
 if(is("restore-length-max")){v=0xfffffffcU;memcpy(store+4,&v,4);}
 if(is("restore-length-unaligned")){v=35;memcpy(store+4,&v,4);}
 if(is("restore-id")){v=99;memcpy(store,&v,4);}
 if(is("restore-header-short")){v=8;memcpy(store+4,&v,4);}
 if(is("restore-payload-short")){v=32;memcpy(store+4,&v,4);}
 if(is("restore-payload-long")){v=40;memcpy(store+4,&v,4);}
 if(is("restore-bitmap-zero"))memcpy(store+10,&bits,2);
 if(is("restore-bitmap-high")){bits=0x200;memcpy(store+10,&bits,2);}
 if(is("restore-bitmap-mismatch")){bits=2;memcpy(store+40+10,&bits,2);}
 if(is("restore-group-high")){v=9;memcpy(store+rxfd_offset+12,&v,4);}
 if(is("restore-group-unselected")){v=1;memcpy(store+rxfd_offset+12,&v,4);}
 if(is("restore-duplicate-rxfd")){v=0;memcpy(store+second_rxfd+12,&v,4);}
 if(is("restore-missing-rxfd")){v=3;memcpy(store+rxfd_offset,&v,4);}
 if(is("restore-order")){v=2;memcpy(store+40,&v,4);}
 if(is("restore-incomplete"))n=352;
 memcpy(prior,store,16384);before=checksum(store,16384);prior_offset=a.PreCalWriteOffSet=n;
 physical=n>16384?16384:n;validation=malloc(physical?physical:1);
 if(!validation)return 96;
 memcpy(validation,store,physical);validation_hash=checksum(validation,physical);
 r=VALIDATE_STORE(is("restore-null")?NULL:validation,n);total=n;
 restore_unchanged=validation_hash==checksum(validation,physical);free(validation);
 }else if(has("sequence-")){UINT32 groups=is("sequence-six")?6:9;bitmap=groups==6?0x3f:0x1ff;a.ChGrpMap=bitmap;r=1;
  r&=store_event(&a,0,bitmap,0);r&=store_event(&a,1,bitmap,0);r&=store_event(&a,2,bitmap,0);for(i=0;i<groups;i++){r&=store_event(&a,4,bitmap,i);total=a.PreCalWriteOffSet;}r&=store_event(&a,3,bitmap,0);total=last_write;
 }else if(!strncmp(case_name,"upstream-",9)){upstream(&a,id,is("upstream-null")?NULL:data,len);r=queue_calls?queue_status:cache_calls?2:-1;
 }else if(!strncmp(case_name,"queued-",7)){q.buffer=data;q.bufferlength=len;r=dispatch_queue(&a,id,&q);
 }else {if(is("null-store"))a.PreCalStoreBuffer=NULL;r=CALL_STORE(&a,is("invalid-id")?99:id,is("null-data")?NULL:data,len);}
 used=a.PreCalWriteOffSet;after=checksum(a.E2pAccessMode==2&&is("flash-wrong-view")?store:!strncmp(case_name,"flash-",6)?image+PRECALPART_OFFSET:store,PRE_CAL_SIZE_ONE_CARD);
 unchanged=before==after&&used==prior_offset;source_unchanged=(is("upstream-cache")?1:original==checksum(data,len))&&restore_unchanged;accepted=r;
 printf("{\"case\":\"%s\",\"status\":%d,\"used\":%u,\"unchanged\":%d,\"source_unchanged\":%d,\"checksum\":%u,\"bin_calls\":%d,\"flash_calls\":%d,\"flag_calls\":%d,\"stamps\":%d,\"completion\":%u,\"last_write\":%u,\"queue_calls\":%d,\"queue_status\":%d,\"queue_length\":%d,\"cache_calls\":%d,\"dumps\":%d,\"outer_allocs\":%d,\"outer_copies\":%d,\"outer_processes\":%d,\"outer_frees\":%d,\"outer_length\":%d,\"outer_payload\":%d,\"total\":%u}\n",case_name,accepted,used,unchanged,source_unchanged,after,bin_calls,flash_calls,flag_calls,stamp_calls,completion,last_write,queue_calls,queue_status,queue_length,cache_calls,dump_calls,outer_allocs,outer_copies,outer_processes,outer_frees,outer_length,outer_payload,total);
 free(data);free(prior);free(bstore);free(store);free(image);return 0;
}
'''

def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'^(?:static\s+)?(?:VOID|INT|NTSTATUS|BOOLEAN)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked,re.M))
    if len(matches)!=1:raise ValueError('Missing/ambiguous MCU function '+name)
    start=matches[0].start();opening=text.index('{',start);depth=0
    for item in re.finditer(tokens+r'|[{}]',text[opening:]):
        if item.group()=='{':depth+=1
        elif item.group()=='}':
            depth-=1
            if not depth:return text[start:opening+item.end()]
    raise ValueError('Unterminated MCU function '+name)


def macro(text,name):
    # Collect precisely continued preprocessor lines, not neighboring code.
    output=[]
    for line in text.splitlines():
        if output and output[-1].rstrip().endswith('\\'):output.append(line);continue
        if re.match(r'^#define[ \t]+'+re.escape(name)+r'(?=[ \t(])',line):
            if output:raise ValueError('Ambiguous macro '+name)
            output=[line]
    if not output:raise ValueError('Missing macro '+name)
    return '\n'.join(output)


def source_declarations(texts):
    for field in ('UINT16 PreCalWriteOffSet;','UINT16 ChGrpMap;'):
        if texts['adapter'].count(field)!=1:raise ValueError('Changed actual adapter calibration field '+field)
    declarations=[macro(texts['rlm'],name)for name in RLM_MACROS]
    for name in EVENT_TYPES:
        found=re.findall(r'typedef struct _'+name+r'\s*\{[^}]+\}\s*'+name+r',\s*\*P_'+name+r';',texts['rlm'])
        if len(found)!=1:raise ValueError('Missing/ambiguous event struct '+name)
        declarations+=found
    found=re.findall(r'typedef enum _PRE_CAL_TYPE\s*\{[^}]+\}\s*PRE_CAL_TYPE;',texts['cmd'])
    if len(found)!=1:raise ValueError('Missing pre-calibration event IDs')
    declarations+=found
    for name in ('FW_RXD_0','FW_RXD_1','FW_RXD_2'):
        found=re.findall(r'typedef union _'+name+r'\s*\{[\s\S]*?\} '+name+r';',texts['cmd'])
        if len(found)!=2:raise ValueError('Changed wire endian declarations')
        declarations.append('#ifdef RT_BIG_ENDIAN\n'+found[0]+'\n#else\n'+found[1]+'\n#endif')
    found=re.findall(r'typedef struct GNU_PACKED _EVENT_RXD_\s*\{[^}]+\}\s*EVENT_RXD;',texts['cmd'])
    if len(found)!=1:raise ValueError('Changed EVENT_RXD declaration')
    declarations+=found
    declarations.extend(macro(texts['andes'],n)for n in ('GET_EVENT_FW_RXD_LENGTH','GET_EVENT_HDR_ADD_PAYLOAD_TOTAL_LEN'))
    for array,size in (('K_AllFreq','K_ALL_SIZE'),('DPD_AllFreq','DPD_ALL_SIZE')):
        found=re.findall(r'UINT16 '+array+r'\[\] = \{[^}]+\};',texts['tables'])
        if len(found)!=1:raise ValueError('Changed actual calibration table '+array)
        declarations+=found
        expression='UINT16 '+size+' = (sizeof('+array+') / sizeof(UINT16));'
        if texts['tables'].count(expression)!=1:raise ValueError('Changed actual table size '+size)
        declarations.append(expression)
    declarations.extend(macro(texts['cmd'],n)for n in ('RXDCOC_SIZE','TXDPD_SIZE'))
    # Flash DCOC origin is selected from the actual conditional definition.
    origin='#define DCOC_FLASH_OFFSET\t\t1024'
    if texts['chip'].count(origin)!=1:raise ValueError('Changed Flash calibration origin')
    declarations.append(origin)
    declarations.extend(macro(texts['chip'],name)for name in CHIP_MACROS)
    return '\n'.join(declarations)


def actual_functions(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact MCU source keys required')
    return {n:{'source':key,'body':function(texts[key],n)}for n,key in FUNCTION_SOURCES.items()}


def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False,disabled_oracle=False):
    if type(baseline)is not bool or type(disabled_oracle)is not bool or baseline and disabled_oracle:raise ValueError('Typed exclusive MCU profile required')
    if type(owner_uid)is not int or not 0<=owner_uid<2**32:raise ValueError('Typed compatibility UID required')
    current=actual_functions(texts)
    for collection,hashes in ((BASELINE_FUNCTIONS,BASELINE_FUNCTIONS_SHA256),(DISABLED_STUBS,DISABLED_STUBS_SHA256)):
        for name,body in collection.items():
            if hashlib.sha256(body.encode()).hexdigest()!=hashes[name]:raise ValueError('Changed fixed MCU control '+name)
    if set(BASELINE_FUNCTIONS)!=set(FUNCTION_SOURCES)-set(NEW_FUNCTIONS):raise ValueError('Changed baseline function set')
    bodies=BASELINE_FUNCTIONS if baseline else DISABLED_STUBS if disabled_oracle else{n:v['body']for n,v in current.items()}
    names=BASELINE_CASES if baseline else DISABLED_CASES if disabled_oracle else CASE_NAMES
    admission='\n'.join('if(!strcmp(case_name,'+json.dumps(n)+'))known=1;'for n in names)
    call='#define CALL_STORE(p,id,data,len) ExtEventPreCalStoreProc(p,id,data'+(')'if baseline else',len)')
    validate='#define VALIDATE_STORE(p,n) '+('((void)(p),(void)(n),0)'if baseline else'rtmp_precal_records_valid(p,n)')
    return PREFIX.replace('SOURCE_DECLARATIONS',source_declarations(texts))+'\n'+call+'\n'+validate+'\n'+'\n'.join(bodies[n]for n in BODY_ORDER if n in bodies)+'\n'+MAIN.replace('CASE_ADMISSION',admission)
