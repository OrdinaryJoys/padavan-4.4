#!/usr/bin/env python3
"""Actual SR3/ready/scan/probe bodies with inert SPI, clock and registration.

No hardware, daemon, device node or target binary is run by this pure generator.
The model clock advances by ten seconds per cond_resched; it is not real time.
"""
import hashlib
import re

SOURCE_PATHS = {
    'nor': 'trunk/linux-4.4.x/drivers/mtd/spi-nor/spi-nor.c',
    'm25p': 'trunk/linux-4.4.x/drivers/mtd/devices/m25p80.c',
    'nor_header': 'trunk/linux-4.4.x/include/linux/mtd/spi-nor.h',
    'spi_header': 'trunk/linux-4.4.x/include/linux/spi/spi.h',
}
FUNCTIONS = {
    'nor': ('read_sr', 'read_fsr', 'spi_nor_read_dummy_cycles', 'write_enable',
            'spi_nor_sr_ready', 'spi_nor_fsr_ready', 'spi_nor_ready',
            'spi_nor_wait_till_ready_with_timeout', 'spi_nor_wait_till_ready',
            'spi_set_wb_drive_strength', 'spi_nor_scan'),
    'm25p': ('m25p80_read_reg', 'm25p80_write_reg', 'm25p_probe'),
}
BASELINE_COMMIT = '79da63dbb4ff7b4e0d84116427294e2734acd60f'
# Exact public baseline bodies and hashes are filled once by the source audit,
# not fetched from Git or the network when tests/target generation run.
BASELINE_FUNCTIONS = {'read_sr': 'static int read_sr(struct spi_nor *nor)\n'
            '{\n'
            '\tint ret;\n'
            '\tu8 val;\n'
            '\n'
            '\tret = nor->read_reg(nor, SPINOR_OP_RDSR, &val, 1);\n'
            '\tif (ret < 0) {\n'
            '\t\tpr_err("error %d reading SR\\n", (int) ret);\n'
            '\t\treturn ret;\n'
            '\t}\n'
            '\n'
            '\treturn val;\n'
            '}',
 'read_fsr': 'static int read_fsr(struct spi_nor *nor)\n'
             '{\n'
             '\tint ret;\n'
             '\tu8 val;\n'
             '\n'
             '\tret = nor->read_reg(nor, SPINOR_OP_RDFSR, &val, 1);\n'
             '\tif (ret < 0) {\n'
             '\t\tpr_err("error %d reading FSR\\n", ret);\n'
             '\t\treturn ret;\n'
             '\t}\n'
             '\n'
             '\treturn val;\n'
             '}',
 'spi_nor_read_dummy_cycles': 'static inline int spi_nor_read_dummy_cycles(struct spi_nor *nor)\n'
                              '{\n'
                              '\tswitch (nor->flash_read) {\n'
                              '\tcase SPI_NOR_FAST:\n'
                              '\tcase SPI_NOR_DUAL:\n'
                              '\tcase SPI_NOR_QUAD:\n'
                              '\t\treturn 8;\n'
                              '\tcase SPI_NOR_NORMAL:\n'
                              '\t\treturn 0;\n'
                              '\t}\n'
                              '\treturn 0;\n'
                              '}',
 'write_enable': 'static inline int write_enable(struct spi_nor *nor)\n'
                 '{\n'
                 '\treturn nor->write_reg(nor, SPINOR_OP_WREN, NULL, 0);\n'
                 '}',
 'spi_nor_sr_ready': 'static inline int spi_nor_sr_ready(struct spi_nor *nor)\n'
                     '{\n'
                     '\tint sr = read_sr(nor);\n'
                     '\tif (sr < 0)\n'
                     '\t\treturn sr;\n'
                     '\telse\n'
                     '\t\treturn !(sr & SR_WIP);\n'
                     '}',
 'spi_nor_fsr_ready': 'static inline int spi_nor_fsr_ready(struct spi_nor *nor)\n'
                      '{\n'
                      '\tint fsr = read_fsr(nor);\n'
                      '\tif (fsr < 0)\n'
                      '\t\treturn fsr;\n'
                      '\telse\n'
                      '\t\treturn fsr & FSR_READY;\n'
                      '}',
 'spi_nor_ready': 'static int spi_nor_ready(struct spi_nor *nor)\n'
                  '{\n'
                  '\tint sr, fsr;\n'
                  '\tsr = spi_nor_sr_ready(nor);\n'
                  '\tif (sr < 0)\n'
                  '\t\treturn sr;\n'
                  '\tfsr = nor->flags & SNOR_F_USE_FSR ? spi_nor_fsr_ready(nor) : 1;\n'
                  '\tif (fsr < 0)\n'
                  '\t\treturn fsr;\n'
                  '\treturn sr && fsr;\n'
                  '}',
 'spi_nor_wait_till_ready_with_timeout': 'static int spi_nor_wait_till_ready_with_timeout(struct '
                                         'spi_nor *nor,\n'
                                         '\t\t\t\t\t\tunsigned long timeout_jiffies)\n'
                                         '{\n'
                                         '\tunsigned long deadline;\n'
                                         '\tint timeout = 0, ret;\n'
                                         '\n'
                                         '\tdeadline = jiffies + timeout_jiffies;\n'
                                         '\n'
                                         '\twhile (!timeout) {\n'
                                         '\t\tif (time_after_eq(jiffies, deadline))\n'
                                         '\t\t\ttimeout = 1;\n'
                                         '\n'
                                         '\t\tret = spi_nor_ready(nor);\n'
                                         '\t\tif (ret < 0)\n'
                                         '\t\t\treturn ret;\n'
                                         '\t\tif (ret)\n'
                                         '\t\t\treturn 0;\n'
                                         '\n'
                                         '\t\tcond_resched();\n'
                                         '\t}\n'
                                         '\n'
                                         '\tdev_err(nor->dev, "flash operation timed out\\n");\n'
                                         '\n'
                                         '\treturn -ETIMEDOUT;\n'
                                         '}',
 'spi_nor_wait_till_ready': 'static int spi_nor_wait_till_ready(struct spi_nor *nor)\n'
                            '{\n'
                            '\treturn spi_nor_wait_till_ready_with_timeout(nor,\n'
                            '\t\t\t\t\t\t    DEFAULT_READY_WAIT_JIFFIES);\n'
                            '}',
 'spi_set_wb_drive_strength': 'static void spi_set_wb_drive_strength(struct spi_nor *nor)\n'
                              '{\n'
                              '\tint ret;\n'
                              '\tu8 code = 0;\n'
                              '\n'
                              '\tret = nor->read_reg(nor, 0x15, &code, 1);\n'
                              '\tif (ret < 0)\n'
                              '\t\treturn;\n'
                              '\n'
                              '\tpr_debug("winbond spi-nor SR3: %d\\n", code);\n'
                              '\n'
                              '\t/* set Winbond DVP[1:0] as 10 (driving strength 50%) */\n'
                              '\tif ((code & 0x60) == 0x60) {\n'
                              '\t\tcode &= ~0x60;\n'
                              '\t\tcode |= 0x40;\n'
                              '\t\twrite_enable(nor);\n'
                              '\t\tnor->cmd_buf[0] = code;\n'
                              '\t\tnor->write_reg(nor, 0x11, nor->cmd_buf, 1);\n'
                              '\t}\n'
                              '}',
 'spi_nor_scan': 'int spi_nor_scan(struct spi_nor *nor, const char *name, enum read_mode mode)\n'
                 '{\n'
                 '\tconst struct flash_info *info = NULL;\n'
                 '\tstruct device *dev = nor->dev;\n'
                 '\tstruct mtd_info *mtd = &nor->mtd;\n'
                 '\tstruct device_node *np = nor->flash_node;\n'
                 '\tint ret;\n'
                 '\tint i;\n'
                 '\n'
                 '\tret = spi_nor_check(nor);\n'
                 '\tif (ret)\n'
                 '\t\treturn ret;\n'
                 '\n'
                 '\tif (name)\n'
                 '\t\tinfo = spi_nor_match_id(name);\n'
                 "\t/* Try to auto-detect if chip name wasn't specified or not found */\n"
                 '\tif (!info)\n'
                 '\t\tinfo = spi_nor_read_id(nor);\n'
                 '\tif (IS_ERR_OR_NULL(info))\n'
                 '\t\treturn -ENOENT;\n'
                 '\n'
                 '\t/*\n'
                 '\t * If caller has specified name of flash model that can normally be\n'
                 "\t * detected using JEDEC, let's verify it.\n"
                 '\t */\n'
                 '\tif (name && info->id_len) {\n'
                 '\t\tconst struct flash_info *jinfo;\n'
                 '\n'
                 '\t\tjinfo = spi_nor_read_id(nor);\n'
                 '\t\tif (IS_ERR(jinfo)) {\n'
                 '\t\t\treturn PTR_ERR(jinfo);\n'
                 '\t\t} else if (jinfo != info) {\n'
                 '\t\t\t/*\n'
                 '\t\t\t * JEDEC knows better, so overwrite platform ID. We\n'
                 "\t\t\t * can't trust partitions any longer, but we'll let\n"
                 '\t\t\t * mtd apply them anyway, since some partitions may be\n'
                 "\t\t\t * marked read-only, and we don't want to lose that\n"
                 "\t\t\t * information, even if it's not 100% accurate.\n"
                 '\t\t\t */\n'
                 '\t\t\tdev_warn(dev, "found %s, expected %s\\n",\n'
                 '\t\t\t\t jinfo->name, info->name);\n'
                 '\t\t\tinfo = jinfo;\n'
                 '\t\t}\n'
                 '\t}\n'
                 '\n'
                 '\tmutex_init(&nor->lock);\n'
                 '\n'
                 '\t/*\n'
                 '\t * Atmel, SST, Intel/Numonyx, and others serial NOR tend to power up\n'
                 '\t * with the software protection bits set\n'
                 '\t */\n'
                 '\n'
                 '\tif (JEDEC_MFR(info) == SNOR_MFR_ATMEL ||\n'
                 '\t    JEDEC_MFR(info) == SNOR_MFR_INTEL ||\n'
                 '\t    JEDEC_MFR(info) == SNOR_MFR_SST) {\n'
                 '\t\twrite_enable(nor);\n'
                 '\t\twrite_sr(nor, 0);\n'
                 '\t}\n'
                 '\n'
                 '\tif (!mtd->name)\n'
                 '\t\tmtd->name = dev_name(dev);\n'
                 '\tmtd->priv = nor;\n'
                 '\tmtd->type = MTD_NORFLASH;\n'
                 '\tmtd->writesize = 1;\n'
                 '\tmtd->flags = MTD_CAP_NORFLASH;\n'
                 '\tmtd->size = info->sector_size * info->n_sectors;\n'
                 '\tmtd->_erase = spi_nor_erase;\n'
                 '\tmtd->_read = spi_nor_read;\n'
                 '\n'
                 '\t/* NOR protection support for STmicro/Micron chips and similar */\n'
                 '\tif (JEDEC_MFR(info) == SNOR_MFR_MICRON) {\n'
                 '\t\tnor->flash_lock = stm_lock;\n'
                 '\t\tnor->flash_unlock = stm_unlock;\n'
                 '\t\tnor->flash_is_locked = stm_is_locked;\n'
                 '\t}\n'
                 '\n'
                 '\tif (nor->flash_lock && nor->flash_unlock && nor->flash_is_locked) {\n'
                 '\t\tmtd->_lock = spi_nor_lock;\n'
                 '\t\tmtd->_unlock = spi_nor_unlock;\n'
                 '\t\tmtd->_is_locked = spi_nor_is_locked;\n'
                 '\t}\n'
                 '\n'
                 '\t/* sst nor chips use AAI word program */\n'
                 '\tif (info->flags & SST_WRITE)\n'
                 '\t\tmtd->_write = sst_write;\n'
                 '\telse\n'
                 '\t\tmtd->_write = spi_nor_write;\n'
                 '\n'
                 '\tif (info->flags & USE_FSR)\n'
                 '\t\tnor->flags |= SNOR_F_USE_FSR;\n'
                 '\n'
                 '#ifdef CONFIG_MTD_SPI_NOR_USE_4K_SECTORS\n'
                 '\t/* prefer "small sector" erase if possible */\n'
                 '\tif (info->flags & SECT_4K) {\n'
                 '\t\tnor->erase_opcode = SPINOR_OP_BE_4K;\n'
                 '\t\tmtd->erasesize = 4096;\n'
                 '\t} else if (info->flags & SECT_4K_PMC) {\n'
                 '\t\tnor->erase_opcode = SPINOR_OP_BE_4K_PMC;\n'
                 '\t\tmtd->erasesize = 4096;\n'
                 '\t} else\n'
                 '#endif\n'
                 '\t{\n'
                 '\t\tnor->erase_opcode = SPINOR_OP_SE;\n'
                 '\t\tmtd->erasesize = info->sector_size;\n'
                 '\t}\n'
                 '\n'
                 '\tif (info->flags & SPI_NOR_NO_ERASE)\n'
                 '\t\tmtd->flags |= MTD_NO_ERASE;\n'
                 '\n'
                 '\tmtd->dev.parent = dev;\n'
                 '\tnor->page_size = info->page_size;\n'
                 '\tmtd->writebufsize = nor->page_size;\n'
                 '\n'
                 '\tif (np) {\n'
                 '\t\t/* If we were instantiated by DT, use it */\n'
                 '\t\tif (of_property_read_bool(np, "m25p,fast-read"))\n'
                 '\t\t\tnor->flash_read = SPI_NOR_FAST;\n'
                 '\t\telse\n'
                 '\t\t\tnor->flash_read = SPI_NOR_NORMAL;\n'
                 '\t} else {\n'
                 "\t\t/* If we weren't instantiated by DT, default to fast-read */\n"
                 '\t\tnor->flash_read = SPI_NOR_FAST;\n'
                 '\t}\n'
                 '\n'
                 '\t/* Some devices cannot do fast-read, no matter what DT tells us */\n'
                 '\tif (info->flags & SPI_NOR_NO_FR)\n'
                 '\t\tnor->flash_read = SPI_NOR_NORMAL;\n'
                 '\n'
                 '\t/* Quad/Dual-read mode takes precedence over fast/normal */\n'
                 '\tif (mode == SPI_NOR_QUAD && info->flags & SPI_NOR_QUAD_READ) {\n'
                 '\t\tret = set_quad_mode(nor, info);\n'
                 '\t\tif (ret) {\n'
                 '\t\t\tdev_err(dev, "quad mode not supported\\n");\n'
                 '\t\t\treturn ret;\n'
                 '\t\t}\n'
                 '\t\tnor->flash_read = SPI_NOR_QUAD;\n'
                 '\t} else if (mode == SPI_NOR_DUAL && info->flags & SPI_NOR_DUAL_READ) {\n'
                 '\t\tnor->flash_read = SPI_NOR_DUAL;\n'
                 '\t}\n'
                 '\n'
                 '\t/* Default commands */\n'
                 '\tswitch (nor->flash_read) {\n'
                 '\tcase SPI_NOR_QUAD:\n'
                 '\t\tnor->read_opcode = SPINOR_OP_READ_1_1_4;\n'
                 '\t\tbreak;\n'
                 '\tcase SPI_NOR_DUAL:\n'
                 '\t\tnor->read_opcode = SPINOR_OP_READ_1_1_2;\n'
                 '\t\tbreak;\n'
                 '\tcase SPI_NOR_FAST:\n'
                 '\t\tnor->read_opcode = SPINOR_OP_READ_FAST;\n'
                 '\t\tbreak;\n'
                 '\tcase SPI_NOR_NORMAL:\n'
                 '\t\tnor->read_opcode = SPINOR_OP_READ;\n'
                 '\t\tbreak;\n'
                 '\tdefault:\n'
                 '\t\tdev_err(dev, "No Read opcode defined\\n");\n'
                 '\t\treturn -EINVAL;\n'
                 '\t}\n'
                 '\n'
                 '\tnor->program_opcode = SPINOR_OP_PP;\n'
                 '\n'
                 '\tif (JEDEC_MFR(info) == SNOR_MFR_WINBOND)\n'
                 '\t\tspi_set_wb_drive_strength(nor);\n'
                 '\n'
                 '\tif (info->addr_width)\n'
                 '\t\tnor->addr_width = info->addr_width;\n'
                 '\telse if (mtd->size > 0x1000000) {\n'
                 '\t\t/* enable 4-byte addressing if the device exceeds 16MiB */\n'
                 '\t\tnor->addr_width = 4;\n'
                 '\t\tif (JEDEC_MFR(info) == SNOR_MFR_SPANSION ||\n'
                 '\t\t    info->flags & SPI_NOR_4B_OPCODES)\n'
                 '\t\t\tspi_nor_set_4byte_opcodes(nor, info);\n'
                 '\t\telse\n'
                 '\t\t\tset_4byte(nor, info, 1);\n'
                 '\t} else {\n'
                 '\t\tnor->addr_width = 3;\n'
                 '\t}\n'
                 '\n'
                 '\tif (nor->addr_width > SPI_NOR_MAX_ADDR_WIDTH) {\n'
                 '\t\tdev_err(dev, "address width is too large: %u\\n",\n'
                 '\t\t\tnor->addr_width);\n'
                 '\t\treturn -EINVAL;\n'
                 '\t}\n'
                 '\n'
                 '\tnor->read_dummy = spi_nor_read_dummy_cycles(nor);\n'
                 '\n'
                 '\tnor->info = info;\n'
                 '\n'
                 '\tdev_info(dev, "%s (%lld Kbytes)\\n", info->name,\n'
                 '\t\t\t(long long)mtd->size >> 10);\n'
                 '\n'
                 '\tdev_dbg(dev,\n'
                 '\t\t"mtd .name = %s, .size = 0x%llx (%lldMiB), "\n'
                 '\t\t".erasesize = 0x%.8x (%uKiB) .numeraseregions = %d\\n",\n'
                 '\t\tmtd->name, (long long)mtd->size, (long long)(mtd->size >> 20),\n'
                 '\t\tmtd->erasesize, mtd->erasesize / 1024, mtd->numeraseregions);\n'
                 '\n'
                 '\tif (mtd->numeraseregions)\n'
                 '\t\tfor (i = 0; i < mtd->numeraseregions; i++)\n'
                 '\t\t\tdev_dbg(dev,\n'
                 '\t\t\t\t"mtd.eraseregions[%d] = { .offset = 0x%llx, "\n'
                 '\t\t\t\t".erasesize = 0x%.8x (%uKiB), "\n'
                 '\t\t\t\t".numblocks = %d }\\n",\n'
                 '\t\t\t\ti, (long long)mtd->eraseregions[i].offset,\n'
                 '\t\t\t\tmtd->eraseregions[i].erasesize,\n'
                 '\t\t\t\tmtd->eraseregions[i].erasesize / 1024,\n'
                 '\t\t\t\tmtd->eraseregions[i].numblocks);\n'
                 '\treturn 0;\n'
                 '}',
 'm25p80_read_reg': 'static int m25p80_read_reg(struct spi_nor *nor, u8 code, u8 *val, int len)\n'
                    '{\n'
                    '\tstruct m25p *flash = nor->priv;\n'
                    '\tstruct spi_device *spi = flash->spi;\n'
                    '\tint ret;\n'
                    '\n'
                    '\tret = spi_write_then_read(spi, &code, 1, val, len);\n'
                    '\tif (ret < 0)\n'
                    '\t\tdev_err(&spi->dev, "error %d reading %x\\n", ret, code);\n'
                    '\n'
                    '\treturn ret;\n'
                    '}',
 'm25p80_write_reg': 'static int m25p80_write_reg(struct spi_nor *nor, u8 opcode, u8 *buf, int '
                     'len)\n'
                     '{\n'
                     '\tstruct m25p *flash = nor->priv;\n'
                     '\tstruct spi_device *spi = flash->spi;\n'
                     '\n'
                     '\tflash->command[0] = opcode;\n'
                     '\tif (buf)\n'
                     '\t\tmemcpy(&flash->command[1], buf, len);\n'
                     '\n'
                     '\treturn spi_write(spi, flash->command, len + 1);\n'
                     '}',
 'm25p_probe': 'static int m25p_probe(struct spi_device *spi)\n'
               '{\n'
               '\tstruct mtd_part_parser_data\tppdata;\n'
               '\tstruct flash_platform_data\t*data;\n'
               '\tstruct m25p *flash;\n'
               '\tstruct spi_nor *nor;\n'
               '\tenum read_mode mode = SPI_NOR_NORMAL;\n'
               '\tchar *flash_name = NULL;\n'
               '\tint ret;\n'
               '\n'
               '\tdata = dev_get_platdata(&spi->dev);\n'
               '\n'
               '\tflash = devm_kzalloc(&spi->dev, sizeof(*flash), GFP_KERNEL);\n'
               '\tif (!flash)\n'
               '\t\treturn -ENOMEM;\n'
               '\n'
               '\tnor = &flash->spi_nor;\n'
               '\n'
               '\t/* install the hooks */\n'
               '\tnor->read = m25p80_read;\n'
               '\tnor->write = m25p80_write;\n'
               '\tnor->erase = m25p80_erase;\n'
               '\tnor->write_reg = m25p80_write_reg;\n'
               '\tnor->read_reg = m25p80_read_reg;\n'
               '\n'
               '\tnor->dev = &spi->dev;\n'
               '\tnor->flash_node = spi->dev.of_node;\n'
               '\tnor->priv = flash;\n'
               '\n'
               '\tspi_set_drvdata(spi, flash);\n'
               '\tflash->spi = spi;\n'
               '\n'
               '\tif (spi->mode & SPI_RX_QUAD)\n'
               '\t\tmode = SPI_NOR_QUAD;\n'
               '\telse if (spi->mode & SPI_RX_DUAL)\n'
               '\t\tmode = SPI_NOR_DUAL;\n'
               '\n'
               '\tif (data && data->name)\n'
               '\t\tnor->mtd.name = data->name;\n'
               '\n'
               '\t/* For some (historical?) reason many platforms provide two different\n'
               '\t * names in flash_platform_data: "name" and "type". Quite often name is\n'
               '\t * set to "m25p80" and then "type" provides a real chip name.\n'
               '\t * If that\'s the case, respect "type" and ignore a "name".\n'
               '\t */\n'
               '\tif (data && data->type)\n'
               '\t\tflash_name = data->type;\n'
               '\telse\n'
               '\t\tflash_name = spi->modalias;\n'
               '\n'
               '\tret = spi_nor_scan(nor, flash_name, mode);\n'
               '\tif (ret)\n'
               '\t\treturn ret;\n'
               '\n'
               '\tppdata.of_node = spi->dev.of_node;\n'
               '\n'
               '\treturn mtd_device_parse_register(&nor->mtd, NULL, &ppdata,\n'
               '\t\t\tdata ? data->parts : NULL,\n'
               '\t\t\tdata ? data->nr_parts : 0);\n'
               '}'}
BASELINE_FUNCTIONS_SHA256 = {'read_sr': '884acce39aa910c22b28c4f2be52a7c3c9ab1a04ba8a74efb1a2260fa0fecf4a',
 'read_fsr': '2635441acbf07bee57732b28444075ac8b74c69896201047032fedc91f892995',
 'spi_nor_read_dummy_cycles': '30cd0b125e81b2313fcf81604e773afb7f43d652175fd39953d56b07a229bb05',
 'write_enable': 'c274ef5a318a65edc74686764749d07c215636475b6a6eb5fcb168dc4e366a8b',
 'spi_nor_sr_ready': 'aced0002eacd30bb53690b09b41e44b77bcd92278bc940c13b14261828233f68',
 'spi_nor_fsr_ready': '1d249f87a44e3fd3b88978c14c0542b198d906432b1de86ffbe086a72efabc81',
 'spi_nor_ready': '1532db9869b5f62e21c4379968ea70493015685e472ecc8d94251cdcc019f8ef',
 'spi_nor_wait_till_ready_with_timeout': 'a285f742fa64ff0ace2963bb6da7473315918bd3ba05baa00243a5b5a3c347c1',
 'spi_nor_wait_till_ready': 'e50a5f758471d11f485bf392da15a59e6c5622028cb4c792ceb15d34e19a253f',
 'spi_set_wb_drive_strength': 'cc5efe55fa606748cfab4bdc5706f0b433d0bde56f181ede35adc0dc076810af',
 'spi_nor_scan': 'e41534a1cb31cd2594152b380cfd84ab27029ca15d25e765ee731420a864820a',
 'm25p80_read_reg': '979934d406c36c695489a8fb9b4cac2f4830582f3169e6b8c8536f6df3dfff5b',
 'm25p80_write_reg': '1bd7a1a3642b2af49ddcb1ba07960ba35921913a5b64050ac8e86fadc1e61cc4',
 'm25p_probe': 'e175fb97a59bf373900b08ecefc847c04eb201869bb9b598d87494656f9a65ec'}

def extract(text, name):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked = re.sub(tokens, lambda m:' ' * len(m.group()), text)
    pattern = r'(?:static\s+)?(?:inline\s+)?(?:void|int|ssize_t)\s+\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{'
    matches = list(re.finditer(pattern, masked))
    if len(matches) != 1: raise ValueError('Missing/ambiguous actual function: ' + name)
    start=matches[0].start();opening=text.index('{',start);depth=0
    for token in re.finditer(tokens + r'|[{}]', text[opening:]):
        if token.group()=='{': depth+=1
        elif token.group()=='}':
            depth-=1
            if not depth:return text[start:opening+token.end()]
    raise ValueError('Unterminated actual function: ' + name)

def actual_functions(texts):
    return {name:{'source_key':key,'body':extract(texts[key],name)}
            for key,names in FUNCTIONS.items() for name in names}

def _define(text, name):
    found=re.findall(r'^#define[ \t]+'+re.escape(name)+r'[ \t]+([^\n]+)$',text,re.M)
    if len(found)!=1:raise ValueError('Missing/ambiguous production macro: '+name)
    return found[0].split('/*',1)[0].strip()

def production_fragments(texts):
    expected = {
        ('nor','DEFAULT_READY_WAIT_JIFFIES'):'(40UL * HZ)',
        ('nor','SPI_NOR_MAX_ADDR_WIDTH'):'4',
        ('nor','SPI_NOR_MAX_ID_LEN'):'6',
        ('nor_header','SPI_NOR_MAX_CMD_SIZE'):'8',
        ('m25p','MAX_CMD_SIZE'):'6',
        ('nor_header','SNOR_MFR_WINBOND'):'0xef',
        ('nor_header','SR_WIP'):'BIT(0)',
        ('nor_header','FSR_READY'):'BIT(7)',
        ('nor_header','SPINOR_OP_RDSR'):'0x05',
        ('nor_header','SPINOR_OP_RDFSR'):'0x70',
        ('nor_header','SPINOR_OP_WREN'):'0x06',
        ('nor_header','SPINOR_OP_PP'):'0x02',
        ('nor_header','SPINOR_OP_SE'):'0xd8',
        ('nor_header','SPINOR_OP_READ'):'0x03',
        ('nor_header','SPINOR_OP_READ_FAST'):'0x0b',
        ('nor_header','SPINOR_OP_READ_1_1_2'):'0x3b',
        ('nor_header','SPINOR_OP_READ_1_1_4'):'0x6b',
        ('spi_header','SPI_RX_DUAL'):'0x400',
        ('spi_header','SPI_RX_QUAD'):'0x800',
    }
    for (key,name),value in expected.items():
        if _define(texts[key],name)!=value:
            raise ValueError('Production macro differs from reviewed contract: '+name)
    snor=re.search(r'\bSNOR_F_USE_FSR\s*=\s*BIT\(0\)\s*,',texts['nor_header'])
    if not snor:raise ValueError('Production FSR flag differs')
    enum=re.search(r'enum read_mode\s*\{[\s\S]*?\};',texts['nor_header'])
    if not enum or re.sub(r'\s+','',enum.group())!='enumread_mode{SPI_NOR_NORMAL=0,SPI_NOR_FAST,SPI_NOR_DUAL,SPI_NOR_QUAD,};':
        raise ValueError('Production read mode enum differs')
    info=re.search(r'struct flash_info\s*\{[\s\S]*?\n\};',texts['nor'])
    if not info:raise ValueError('Production flash_info declaration missing')
    definitions='\n'.join('#define '+name+' '+value for (key,name),value in expected.items())
    return definitions+'\n#define SNOR_F_USE_FSR BIT(0)\n'+enum.group()+'\n'+info.group()+'\n'

PREFIX = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#undef ETIMEDOUT
#define ETIMEDOUT 110
#undef EAGAIN
#define EAGAIN 11
#undef EOPNOTSUPP
#define EOPNOTSUPP 95
#ifndef __linux__
typedef int64_t loff_t;
#endif
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef unsigned char u_char;
#define BIT(n) (1UL<<(n))
#define HZ 100UL
#define GFP_KERNEL 0
#define MTD_NORFLASH 3
#define MTD_CAP_NORFLASH 1024
#define MTD_NO_ERASE 4096
#define SNOR_MFR_ATMEL 0x1f
#define SNOR_MFR_INTEL 0x89
#define SNOR_MFR_SST 0xbf
#define SNOR_MFR_MICRON 0x20
#define SNOR_MFR_SPANSION 0x01
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p)||IS_ERR(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define JEDEC_MFR(info) ((info)->id[0])
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
struct device_node {int unused;};
struct device {struct device_node*of_node;struct device*parent;};
struct spi_device {struct device dev;unsigned int mode;char*modalias;void*data;};
struct mtd_info;struct spi_nor;struct flash_info;struct erase_info {int unused;};
struct erase_region {uint64_t offset;unsigned int erasesize,numblocks;};
struct mtd_info {
 char*name;void*priv;unsigned int type,writesize,flags,erasesize,writebufsize,numeraseregions;
 uint64_t size;struct device dev;struct erase_region*eraseregions;
 int (*_erase)(struct mtd_info*,struct erase_info*);
 int (*_read)(struct mtd_info*,loff_t,size_t,size_t*,u_char*);
 int (*_write)(struct mtd_info*,loff_t,size_t,size_t*,const u_char*);
 int (*_lock)(void);int (*_unlock)(void);int (*_is_locked)(void);
};
struct spi_nor {
 struct mtd_info mtd;void*priv;struct device*dev;struct device_node*flash_node;
 const struct flash_info*info;unsigned int addr_width,program_opcode,read_opcode,erase_opcode,read_dummy,page_size,flash_read,flags;
 int lock;u8 cmd_buf[8];
 int (*read_reg)(struct spi_nor*,u8,u8*,int);
 int (*write_reg)(struct spi_nor*,u8,u8*,int);
 int (*read)(struct spi_nor*,loff_t,size_t,size_t*,u_char*);
 void (*write)(struct spi_nor*,loff_t,size_t,size_t*,const u_char*);
 int (*erase)(struct spi_nor*,loff_t);
 int (*flash_lock)(void);int (*flash_unlock)(void);int (*flash_is_locked)(void);
};
struct m25p {struct spi_device*spi;struct spi_nor spi_nor;u8 command[6];};
struct flash_platform_data {char*name,*type;void*parts;int nr_parts;};
struct mtd_part_parser_data {struct device_node*of_node;};
static const char*label;static void*allocated_flash;
static int warnings,errors,registered,registration_busy,array_reads,array_busy,array_result;
static int sr3=0x60,initial_sr3=0x60,busy,wel,write_value=-1;
static int status_reads,fsr_reads,sr3_reads,wren_calls,write_calls,wren_busy,write_busy;
static int post_write,sr3_pending,pre_poll,post_poll,fsr_extra,sr_last_wip;
static unsigned long jiffies;
static char sequence[128];
static int is(const char*s){return !strcmp(label,s);}
static void trace(char c){size_t n=strlen(sequence);if(n+1>=sizeof(sequence))abort();sequence[n]=c;sequence[n+1]=0;}
#define dev_warn(device,...) ((void)(device),(void)++warnings)
#define dev_err(device,...) ((void)(device),(void)++errors)
#define dev_info(device,...) ((void)(device))
#define dev_dbg(device,...) ((void)(device))
#define pr_err(...) ((void)++errors)
#define pr_debug(...) ((void)0)
#define mutex_init(p) ((void)(p))
static void cond_resched(void){jiffies+=10UL*HZ;}
static int spi_write_then_read(struct spi_device*spi,const void*tx,unsigned int tlen,void*rx,unsigned int rlen){
 u8 code;int pending,forever;(void)spi;
 if(tlen!=1||rlen!=1)abort();
 code=*(const u8*)tx;
 if(code==0x15){
  trace('R');sr3_reads++;
  if(is("fresh-sr3-read-error")&&sr3_reads==2)return -EIO;
  if(is("sr3-unsupported"))return -EOPNOTSUPP;
  if(is("sr3-read-error"))return -EIO;
  *(u8*)rx=(u8)sr3;return 0;
 }
 if(code==0x05){
  trace('S');status_reads++;
  if((!post_write&&is("pre-ready-error"))||(post_write&&(is("post-ready-error")||is("write-error-accepted-ready-error")||is("write-error-rejected-ready-error"))))return -EIO;
  if(post_write)post_poll++;else pre_poll++;
  forever=(!post_write&&is("pre-ready-timeout"))||(post_write&&(is("post-ready-timeout")||is("write-error-accepted-ready-timeout")||is("deadline-wrap-timeout")));
  pending=busy!=0;
  if(pending&&!forever){
   if(--busy==0&&sr3_pending>=0){sr3=sr3_pending;sr3_pending=-1;wel=0;}
  }
  sr_last_wip=pending;*(u8*)rx=pending?1:0;return 0;
 }
 if(code==0x70){
  trace('F');fsr_reads++;
  if(post_write&&is("fsr-error"))return -EIO;
  if(!busy&&!sr_last_wip&&post_write&&fsr_extra>0){fsr_extra--;*(u8*)rx=0;return 0;}
  *(u8*)rx=busy?0:0x80;return 0;
 }
 abort();
}
static int spi_write(struct spi_device*spi,const void*tx,unsigned int length){
 const u8*p=tx;(void)spi;
 if(p[0]==0x06){
  if(length!=1)abort();
  trace('E');wren_calls++;if(busy)wren_busy++;
  if(is("wren-error"))return -EIO;
  if(!busy)wel=1;
  return is("wren-error-accepted")?-EIO:0;
 }
 if(p[0]==0x11){
  if(length!=2)abort();
  trace('W');write_calls++;write_value=p[1];if(busy)write_busy++;
  if(is("write-error-rejected")||is("write-error-rejected-ready-error")){post_write=1;return -EIO;}
  if(!busy&&wel){busy=2;sr3_pending=p[1];wel=0;}
  post_write=1;
  return (!strncmp(label,"write-error-accepted",20))?-EIO:0;
 }
 abort();
}
static struct flash_platform_data*dev_get_platdata(struct device*d){(void)d;return NULL;}
static void*devm_kzalloc(struct device*d,size_t n,int flags){(void)d;(void)flags;allocated_flash=calloc(1,n);return allocated_flash;}
static void spi_set_drvdata(struct spi_device*s,void*p){s->data=p;}
static char*dev_name(struct device*d){(void)d;return "inert-spi";}
static int of_property_read_bool(struct device_node*n,const char*name){(void)n;return !strcmp(name,"m25p,fast-read");}
static int spi_nor_check(struct spi_nor*n){(void)n;return 0;}
static int write_sr(struct spi_nor*n,u8 v){(void)n;(void)v;abort();}
static int stm_lock(void){return 0;}static int stm_unlock(void){return 0;}static int stm_is_locked(void){return 0;}
static int spi_nor_lock(void){return 0;}static int spi_nor_unlock(void){return 0;}static int spi_nor_is_locked(void){return 0;}
static int spi_nor_erase(struct mtd_info*m,struct erase_info*i){(void)m;(void)i;return 0;}
static int spi_nor_read(struct mtd_info*m,loff_t o,size_t n,size_t*r,u_char*b){(void)m;(void)o;(void)n;(void)r;(void)b;return 0;}
static int spi_nor_write(struct mtd_info*m,loff_t o,size_t n,size_t*r,const u_char*b){(void)m;(void)o;(void)n;(void)r;(void)b;return 0;}
static int sst_write(struct mtd_info*m,loff_t o,size_t n,size_t*r,const u_char*b){return spi_nor_write(m,o,n,r,b);}
static int m25p80_read(struct spi_nor*n,loff_t o,size_t z,size_t*r,u_char*b){(void)n;(void)o;(void)z;(void)r;(void)b;return 0;}
static void m25p80_write(struct spi_nor*n,loff_t o,size_t z,size_t*r,const u_char*b){(void)n;(void)o;(void)z;(void)r;(void)b;}
static int m25p80_erase(struct spi_nor*n,loff_t o){(void)n;(void)o;return 0;}
static int set_quad_mode(struct spi_nor*n,const struct flash_info*i){(void)n;(void)i;abort();}
static int set_4byte(struct spi_nor*n,const struct flash_info*i,int enable){(void)n;(void)i;(void)enable;abort();}
static void spi_nor_set_4byte_opcodes(struct spi_nor*n,const struct flash_info*i){(void)n;(void)i;abort();}
static int mtd_device_parse_register(struct mtd_info*m,const char**types,struct mtd_part_parser_data*p,void*parts,int count){
 (void)m;(void)types;(void)p;(void)parts;(void)count;trace('G');registered++;registration_busy+=!!busy;return 0;
}
'''
POST_DEFINITIONS = r'''
static struct flash_info model_info;
static const struct flash_info*spi_nor_match_id(const char*name){(void)name;return &model_info;}
static const struct flash_info*spi_nor_read_id(struct spi_nor*n){(void)n;return &model_info;}
'''
DRIVER = r'''
int main(int argc,char**argv){
 struct spi_device spi;struct device_node node;struct m25p*flash;int result;
 if(argc!=2)return 90;
 label=argv[1];memset(&spi,0,sizeof(spi));
 memset(&model_info,0,sizeof(model_info));model_info.name="inert-16MiB";
 model_info.id[0]=is("non-winbond")?0xc2:0xef;model_info.sector_size=65536;
 model_info.n_sectors=256;model_info.page_size=256;model_info.flags=SECT_4K;
 spi.dev.of_node=&node;spi.modalias="inert-part";sr3_pending=-1;
 if(is("unchanged-00"))sr3=0;
 if(is("unchanged-20"))sr3=0x20;
 if(is("unchanged-40"))sr3=0x40;
 if(is("preserve-other-bits"))sr3=0xe7;
 if(is("preserve-all-other-bits"))sr3=0xff;
 initial_sr3=sr3;
 if(is("initial-busy")||is("pre-ready-timeout"))busy=2;
 if(is("busy-prior-sr3-other-bits")){busy=2;sr3_pending=0xe0;}
 if(is("busy-prior-sr3-no-change")){busy=2;sr3_pending=0x40;}
 if(is("fsr-normal")||is("fsr-error")||is("fsr-delayed")){
  model_info.flags|=USE_FSR;if(is("fsr-delayed"))fsr_extra=1;
 }
 if(is("deadline-wrap-timeout"))jiffies=~0UL-2000UL;
 result=m25p_probe(&spi);flash=allocated_flash;
 if(registered){trace('A');array_reads++;if(busy){array_busy++;array_result=-EAGAIN;}}
 printf("{\"case\":\"%s\",\"result\":%d,\"registered\":%d,\"registration_busy\":%d,\"array_reads\":%d,\"array_busy\":%d,\"array_result\":",
 label,result,registered,registration_busy,array_reads,array_busy);
 if(array_reads)printf("%d",array_result);else fputs("null",stdout);
 printf(",\"sr3_before\":%d,\"sr3_after\":%d,\"write_value\":%d,\"wel\":%d,\"busy\":%d,\"wren_calls\":%d,\"write_calls\":%d,\"status_reads\":%d,\"fsr_reads\":%d,\"wren_busy\":%d,\"write_busy\":%d,\"warnings\":%d,\"errors\":%d,\"read_opcode\":%u,\"addr_width\":%u,\"read_dummy\":%u,\"jiffies\":%lu,\"sequence\":\"%s\"}\n",
 initial_sr3,sr3,write_value,wel,!!busy,wren_calls,write_calls,status_reads,fsr_reads,wren_busy,write_busy,warnings,errors,
 flash->spi_nor.read_opcode,flash->spi_nor.addr_width,flash->spi_nor.read_dummy,jiffies,sequence);
 free(allocated_flash);return 0;
}
'''

# These expected values are audited model contracts, not discovered by execution.
def expected(name, *, result=0, registered=1, registration_busy=0, busy=0,
             before=0x60, after=0x40, value=0x40, wel=0, wren=1, writes=1,
             status=4, fsr=0, wren_busy=0, write_busy=0, warnings=0, errors=0,
             jiffies=2000, sequence='RSREWSSSGA'):
    return {'case':name,'result':result,'registered':registered,
            'registration_busy':registration_busy,'array_reads':registered,
            'array_busy':registration_busy,'array_result':(-11 if registration_busy else 0) if registered else None,
            'sr3_before':before,'sr3_after':after,'write_value':value,'wel':wel,
            'busy':busy,'wren_calls':wren,'write_calls':writes,'status_reads':status,
            'fsr_reads':fsr,'wren_busy':wren_busy,'write_busy':write_busy,
            'warnings':warnings,'errors':errors,'read_opcode':11,
            'addr_width':3 if registered else 0,'read_dummy':8 if registered else 0,
            'jiffies':jiffies,'sequence':sequence}

CASES = (
    ('normal',expected('normal')),
    ('unchanged-00',expected('unchanged-00',before=0,after=0,value=-1,wren=0,writes=0,status=0,jiffies=0,sequence='RGA')),
    ('unchanged-20',expected('unchanged-20',before=0x20,after=0x20,value=-1,wren=0,writes=0,status=0,jiffies=0,sequence='RGA')),
    ('unchanged-40',expected('unchanged-40',before=0x40,after=0x40,value=-1,wren=0,writes=0,status=0,jiffies=0,sequence='RGA')),
    ('preserve-other-bits',expected('preserve-other-bits',before=0xe7,after=0xc7,value=0xc7)),
    ('preserve-all-other-bits',expected('preserve-all-other-bits',before=0xff,after=0xdf,value=0xdf)),
    ('non-winbond',expected('non-winbond',after=0x60,value=-1,wren=0,writes=0,status=0,jiffies=0,sequence='GA')),
    ('sr3-unsupported',expected('sr3-unsupported',after=0x60,value=-1,wren=0,writes=0,status=0,errors=1,jiffies=0,sequence='RGA')),
    ('sr3-read-error',expected('sr3-read-error',after=0x60,value=-1,wren=0,writes=0,status=0,errors=1,jiffies=0,sequence='RGA')),
    ('wren-error',expected('wren-error',after=0x60,value=-1,writes=0,status=1,warnings=1,jiffies=0,sequence='RSREGA')),
    ('wren-error-accepted',expected('wren-error-accepted',after=0x60,value=-1,wel=1,writes=0,status=1,warnings=1,jiffies=0,sequence='RSREGA')),
    ('write-error-rejected',expected('write-error-rejected',after=0x60,wel=1,status=2,warnings=1,jiffies=0,sequence='RSREWSGA')),
    ('write-error-accepted',expected('write-error-accepted',warnings=1)),
    ('initial-busy',expected('initial-busy',status=6,jiffies=4000,sequence='RSSSREWSSSGA')),
    ('pre-ready-error',expected('pre-ready-error',result=-5,registered=0,after=0x60,value=-1,wren=0,writes=0,status=1,errors=2,jiffies=0,sequence='RS')),
    ('pre-ready-timeout',expected('pre-ready-timeout',result=-110,registered=0,busy=1,after=0x60,value=-1,wren=0,writes=0,status=5,errors=1,jiffies=5000,sequence='RSSSSS')),
    ('post-ready-error',expected('post-ready-error',result=-5,registered=0,busy=1,after=0x60,status=2,errors=2,jiffies=0,sequence='RSREWS')),
    ('post-ready-timeout',expected('post-ready-timeout',result=-110,registered=0,busy=1,after=0x60,status=6,errors=1,jiffies=5000,sequence='RSREWSSSSS')),
    ('write-error-accepted-ready-error',expected('write-error-accepted-ready-error',result=-5,registered=0,busy=1,after=0x60,status=2,errors=2,jiffies=0,sequence='RSREWS')),
    ('write-error-accepted-ready-timeout',expected('write-error-accepted-ready-timeout',result=-110,registered=0,busy=1,after=0x60,status=6,errors=1,jiffies=5000,sequence='RSREWSSSSS')),
    ('write-error-rejected-ready-error',expected('write-error-rejected-ready-error',result=-5,registered=0,after=0x60,wel=1,status=2,errors=2,jiffies=0,sequence='RSREWS')),
    ('deadline-wrap-timeout',expected('deadline-wrap-timeout',result=-110,registered=0,busy=1,after=0x60,status=6,errors=1,jiffies=2999,sequence='RSREWSSSSS')),
    ('fsr-normal',expected('fsr-normal',status=4,fsr=4,sequence='RSFREWSFSFSFGA')),
    ('fsr-error',expected('fsr-error',result=-5,registered=0,busy=1,after=0x60,status=2,fsr=2,errors=2,jiffies=0,sequence='RSFREWSF')),
    ('fsr-delayed',expected('fsr-delayed',status=5,fsr=5,jiffies=3000,sequence='RSFREWSFSFSFSFGA')),
    ('busy-prior-sr3-other-bits',expected('busy-prior-sr3-other-bits',after=0xc0,value=0xc0,status=6,jiffies=4000,sequence='RSSSREWSSSGA')),
    ('busy-prior-sr3-no-change',expected('busy-prior-sr3-no-change',after=0x40,value=-1,wren=0,writes=0,status=3,jiffies=2000,sequence='RSSSRGA')),
    ('fresh-sr3-read-error',expected('fresh-sr3-read-error',after=0x60,value=-1,wren=0,writes=0,status=1,errors=1,jiffies=0,sequence='RSRGA')),
)
BASELINE_CASES = (
    ('normal',expected('normal',registration_busy=1,busy=1,after=0x60,status=0,jiffies=0,sequence='REWGA')),
    ('wren-error',expected('wren-error',after=0x60,wel=0,status=0,jiffies=0,sequence='REWGA')),
    ('wren-error-accepted',expected('wren-error-accepted',registration_busy=1,busy=1,after=0x60,status=0,jiffies=0,sequence='REWGA')),
    ('write-error-rejected',expected('write-error-rejected',after=0x60,wel=1,status=0,jiffies=0,sequence='REWGA')),
    ('write-error-accepted',expected('write-error-accepted',registration_busy=1,busy=1,after=0x60,status=0,jiffies=0,sequence='REWGA')),
    ('post-ready-timeout',expected('post-ready-timeout',registration_busy=1,busy=1,after=0x60,status=0,jiffies=0,sequence='REWGA')),
    ('post-ready-error',expected('post-ready-error',registration_busy=1,busy=1,after=0x60,status=0,jiffies=0,sequence='REWGA')),
    ('initial-busy',expected('initial-busy',registration_busy=1,busy=1,after=0x60,wel=0,status=0,wren_busy=1,write_busy=1,jiffies=0,sequence='REWGA')),
)
LIMITS = (
    'SPI transfers, JEDEC lookup, DT, allocation and MTD registration are inert seams; no device or kernel is run.',
    'Actual ready-loop functions use a model HZ and advancing jiffies; this is not a wall-clock or total SPI queue timeout.',
    'Error numbers are normalized model values, not proof of the real MIPS kernel errno ABI.',
    'Only DRV mask0x60 and target0x40 are retained; no new flash opcode, voltage, frequency, reset or analog value is introduced.',
    'Initial unsupported SR3 and confirmed-ready optional adjustment failures remain best effort; readiness errors block registration.',
)

def generate_source(texts, fixture_root=None, owner_uid=0, baseline=False):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact locked source manifest required')
    if type(baseline)is not bool or type(owner_uid)is not int:raise ValueError('Typed generation arguments required')
    fragments=production_fragments(texts)
    funcs=actual_functions(texts)
    bodies={name:row['body'] for name,row in funcs.items()}
    if baseline:
        if set(BASELINE_FUNCTIONS)!=set(BASELINE_FUNCTIONS_SHA256):raise ValueError('Unpinned baseline')
        for name,body in BASELINE_FUNCTIONS.items():
            if hashlib.sha256(body.encode()).hexdigest()!=BASELINE_FUNCTIONS_SHA256[name]:
                raise ValueError('Changed literal baseline: '+name)
            bodies[name]=body
    order=('m25p80_read_reg','m25p80_write_reg','read_sr','read_fsr','spi_nor_read_dummy_cycles','write_enable',
           'spi_nor_sr_ready','spi_nor_fsr_ready','spi_nor_ready',
           'spi_nor_wait_till_ready_with_timeout','spi_nor_wait_till_ready',
           'spi_set_wb_drive_strength','spi_nor_scan','m25p_probe')
    return PREFIX+'\n'+fragments+'\n'+POST_DEFINITIONS+'\n'+'\n\n'.join(bodies[name] for name in order)+'\n'+DRIVER
