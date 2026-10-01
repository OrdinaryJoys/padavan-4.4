SRC_NAME=openvpn-2.6.23
SRC_URL=https://github.com/OpenVPN/openvpn/releases/download/v2.6.23/$(SRC_NAME).tar.gz
SRC_SHA256=4041c709162bec1325abf5aa8cf27a255cc477c634b15ee310411c701fc40a96

CFLAGS += -ffunction-sections -fdata-sections -fvisibility=hidden
LDFLAGS += -Wl,--gc-sections

all: download_test extract_test config_test
	$(MAKE) -j$(HOST_NCPU) -C $(SRC_NAME)

download_test:
	( if [ ! -f $(SRC_NAME).tar.gz ]; then \
		wget -t5 --timeout=20 -O $(SRC_NAME).tar.gz $(SRC_URL); \
	fi; \
	echo "$(SRC_SHA256)  $(SRC_NAME).tar.gz" | sha256sum -c -; \
	)

extract_test:
	( if [ ! -d $(SRC_NAME) ]; then \
		tar -xf $(SRC_NAME).tar.gz; \
	fi )

config_test:
	( if [ -f ./config_done ]; then \
		echo "the same configuration"; \
	else \
		make configure && touch config_done; \
	fi )

configure:
	( cd $(SRC_NAME) ; \
	PKG_CONFIG_LIBDIR="$(STAGEDIR)/lib/pkgconfig" \
	IFCONFIG=/sbin/ifconfig \
	ROUTE=/sbin/route \
	NETSTAT=/bin/netstat \
	./configure \
		--prefix=/usr \
		--disable-debug \
		--disable-plugins \
		--disable-pkcs11 \
		--disable-ofb-cfb \
		--disable-selinux \
		--disable-systemd \
		--disable-iproute2 \
		--disable-unit-tests \
		--disable-management \
		--disable-dco \
		--disable-lz4 \
		--enable-small \
		--enable-multihome \
		--enable-fragment \
		--enable-def-auth \
		--enable-lzo \
		--with-crypto-library=openssl \
		--with-sysroot=$(STAGEDIR) \
		--host=$(HOST_TARGET) \
		--build=$(HOST_BUILD) ; \
	)

clean:
	if [ -f $(SRC_NAME)/Makefile ] ; then \
		$(MAKE) -C $(SRC_NAME) distclean ; \
	fi ; \
	rm -f config_done

romfs:
	$(ROMFSINST) $(SRC_NAME)/src/openvpn/openvpn /usr/sbin/openvpn
	$(ROMFSINST) /usr/bin/openvpn-cert.sh
