SRC_NAME=curl-8.22.0
SRC_URL=https://curl.se/download/$(SRC_NAME).tar.xz
SRC_SHA256=f7ef3ae8a22e521f289803fe93543eb64c329b58aa73a9e224dfd915a2a5f4f7

LDFLAGS += -Wl,-rpath-link=$(STAGEDIR)/lib

all: download_test extract_test config_test
	$(MAKE) -j$(HOST_NCPU) -C $(SRC_NAME)

download_test:
	( if [ ! -f $(SRC_NAME).tar.xz ]; then \
		wget -t5 --timeout=20 -O $(SRC_NAME).tar.xz $(SRC_URL); \
	fi; \
	echo "$(SRC_SHA256)  $(SRC_NAME).tar.xz" | sha256sum -c -; \
	)

extract_test:
	( if [ ! -d $(SRC_NAME) ]; then \
		tar xf $(SRC_NAME).tar.xz; \
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
	./configure \
		--prefix=$(STAGEDIR) \
		--enable-static \
		--enable-shared \
		$(if $(CONFIG_IPV6),--enable-ipv6,--disable-ipv6) \
		--disable-gopher \
		--disable-ldap \
		--disable-ldaps \
		--disable-rtsp \
		--disable-telnet \
		--disable-tftp \
		--disable-smtp \
		--disable-pop3 \
		--disable-imap \
		--disable-sspi \
		--disable-dict \
		--disable-ares \
		--disable-debug \
		--disable-docs \
		--disable-manual \
		--disable-tls-srp \
		--disable-libcurl-option \
		--disable-threaded-resolver \
		--without-gnutls \
		--with-ca-bundle=/etc/ssl/cert.pem \
		--without-libidn2 \
		--without-libssh2 \
		--without-libssh \
		--without-libpsl \
		--without-brotli \
		--without-zstd \
		--without-nghttp2 \
		--without-nghttp3 \
		--without-ngtcp2 \
		--with-zlib=$(STAGEDIR) \
		--with-openssl=$(STAGEDIR) \
		--host=$(HOST_TARGET) \
		--build=$(HOST_BUILD) ; \
	)

clean:
	if [ -f $(SRC_NAME)/Makefile ] ; then \
		$(MAKE) -C $(SRC_NAME) clean ; \
	fi ; \
	rm -f config_done

install:
	$(MAKE) -C $(SRC_NAME) install DESTDIR=""

romfs:
ifeq ($(CONFIG_FIRMWARE_INCLUDE_CURL),y)
	$(ROMFSINST) -d $(DESTDIR)/bin/curl /usr/bin/curl
endif
	cp -fP $(DESTDIR)/lib/libcurl.so* $(ROMFSDIR)/lib
