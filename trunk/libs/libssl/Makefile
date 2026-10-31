SRC_NAME=openssl-3.5.9
SRC_URL=https://github.com/openssl/openssl/releases/download/$(SRC_NAME)/$(SRC_NAME).tar.gz
SRC_SHA256=603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a
# Quote literal build flag values without expanding shell metacharacters.
shell_quote = '$(subst ','"'"',$(1))'

# openssl use CROSS_COMPILE prefix
CC = gcc
AR = ar
RANLIB = ranlib
CXX = g++

COPTS = $(CPUFLAGS) -O3 $(filter-out -O%, $(CFLAGS))
COPTS += $(if $(CONFIG_IPV6),-DOPENSSL_USE_IPV6=1,)
COPTS += -DPADAVAN_OPENSSL_BOUNDED_LOG

CFLAGS := $(COPTS)
CXXFLAGS := $(COPTS)

# Built-in providers avoid a build-host module path in the router image.
# Retain deprecated APIs for existing Padavan consumers and thread support.
OPENSSL_CIPHERS = no-tests no-docs no-fips no-module no-legacy \
  no-cmp no-cms no-ts no-rfc3779 no-sctp no-srp no-ssl3 \
  no-ssl3-method no-async no-dynamic-engine no-afalgeng \
  no-devcryptoeng no-padlockeng no-ml-dsa no-ml-kem no-slh-dsa \
  no-sm2 no-sm3 no-sm4 no-aria no-seed no-idea no-rc5 no-md2 \
  no-mdc2 no-cast no-whirlpool no-camellia no-blake2

ifneq ($(CONFIG_FIRMWARE_INCLUDE_SSWAN),y)
OPENSSL_CIPHERS += no-rc2
endif

ifneq ($(CONFIG_FIRMWARE_INCLUDE_OPENSSL_EC),y)
OPENSSL_CIPHERS += no-ec
endif

all: download_test extract_test config_test
	$(MAKE) -j$(HOST_NCPU) -C $(SRC_NAME)

download_test:
	( if [ ! -f $(SRC_NAME).tar.gz ]; then \
		wget -t5 --timeout=20 -O $(SRC_NAME).tar.gz $(SRC_URL); \
	fi; \
	echo "$(SRC_SHA256)  $(SRC_NAME).tar.gz" | sha256sum -c -; \
	)

extract_test: download_test
	( if [ ! -d $(SRC_NAME) ]; then \
		tar -xf $(SRC_NAME).tar.gz; \
	fi; \
	if patch -d $(SRC_NAME) -p1 --fuzz=0 --force --reverse --dry-run < openssl-bounded-log.patch >/dev/null 2>&1; then \
		:; \
	elif patch -d $(SRC_NAME) -p1 --fuzz=0 --force --forward --dry-run < openssl-bounded-log.patch >/dev/null 2>&1; then \
		patch -d $(SRC_NAME) -p1 --fuzz=0 --force --forward < openssl-bounded-log.patch || exit 1; \
	else \
		echo "OpenSSL bounded logging patch does not match the locked source" >&2; exit 1; \
	fi; \
	for target in $(SRC_NAME)/crypto/bio/padavan_bounded_syslog.h $(SRC_NAME)/apps/include/padavan_bounded_syslog.h; do \
		cmp -s ../../user/shared/bounded_syslog.h "$$target" || cp ../../user/shared/bounded_syslog.h "$$target" || exit 1; \
	done )

config_test: extract_test
	( { sha256sum Makefile openssl-bounded-log.patch ../../user/shared/bounded_syslog.h && \
		printf '%s\n' $(call shell_quote,CFLAGS=$(CFLAGS)) $(call shell_quote,CXXFLAGS=$(CXXFLAGS)) \
		$(call shell_quote,CROSS_COMPILE=$(CROSS_COMPILE)) $(call shell_quote,CONFIG_IPV6=$(CONFIG_IPV6)) \
		$(call shell_quote,OPENSSL_CIPHERS=$(OPENSSL_CIPHERS)); } > .padavan-config-wanted || exit 1; \
	if [ -f ./config_done ] && cmp -s .padavan-config-wanted config_done; then \
		echo "the same configuration"; \
	else \
		$(MAKE) configure && mv -f .padavan-config-wanted config_done || exit 1; \
	fi )

configure:
	( cd $(SRC_NAME) ; \
	CFLAGS=$(call shell_quote,$(CFLAGS)) CXXFLAGS=$(call shell_quote,$(CXXFLAGS)) ./Configure \
		linux-mips32 \
		shared \
		--prefix=$(STAGEDIR) \
		--openssldir=/etc/ssl \
		--libdir=lib \
		$(OPENSSL_CIPHERS) ; \
	)

clean:
	if [ -f $(SRC_NAME)/Makefile ] ; then \
		$(MAKE) -C $(SRC_NAME) clean ; \
	fi ; \
	rm -f config_done .padavan-config-wanted

install:
	$(MAKE) -C $(SRC_NAME) install_sw DESTDIR=""
	$(MAKE) -C $(SRC_NAME) install_ssldirs DESTDIR="$(STAGEDIR)"
	rm -f $(DESTDIR)/lib/libssl.a
	rm -f $(DESTDIR)/lib/libcrypto.a

romfs:
	cp -fP $(DESTDIR)/lib/libssl.so* $(ROMFSDIR)/lib
	cp -fP $(DESTDIR)/lib/libcrypto.so* $(ROMFSDIR)/lib
	cp -fL $(CONFIG_CROSS_COMPILER_ROOT)/mipsel-linux-uclibc/sysroot/lib/libatomic.so.1 $(ROMFSDIR)/lib/libatomic.so.1
	$(ROMFSINST) /etc_ro/openssl.cnf
ifeq ($(CONFIG_FIRMWARE_INCLUDE_OPENSSL_EXE),y)
	$(ROMFSINST) $(SRC_NAME)/apps/openssl /usr/bin/openssl
endif
