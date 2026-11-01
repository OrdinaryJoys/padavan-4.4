EXEC = mtd_write

OBJS = mtd.o crc32.o md5.o jffs2.o

CFLAGS += -D__BYTE_ORDER=__LITTLE_ENDIAN
CFLAGS += -ffunction-sections -fdata-sections

LDFLAGS += -Wl,--gc-sections -Wl,-z,now

# These K2P4.4 NOR images require the guarded, static RAM upgrade entry.
MTD_PRODUCT := $(subst ",,$(CONFIG_FIRMWARE_PRODUCT_ID))
ifneq ($(filter K2P K2P-USB,$(MTD_PRODUCT)),)
CFLAGS += -DMTD_K2P_LEGACY_GUARD=1
FWUP_EXEC = fw_upgrade
endif

all: $(EXEC) $(FWUP_EXEC)

mtd.o: mtd.c legacy_guard.h crc32.h

fw_upgrade: fw_upgrade.c upgrade_write.h resident_admission.h resident_upgrade.h crc32.c crc32.h Makefile
	$(CC) $(CFLAGS) -static -Wl,--gc-sections -Wl,-z,now -o $@ fw_upgrade.c crc32.c $(LDLIBS)

$(EXEC): $(OBJS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(OBJS) $(LDLIBS)

romfs:
	$(ROMFSINST) /bin/$(EXEC)
ifneq ($(FWUP_EXEC),)
	$(ROMFSINST) /bin/$(FWUP_EXEC)
endif

clean:
	rm -f $(EXEC) fw_upgrade *.o
