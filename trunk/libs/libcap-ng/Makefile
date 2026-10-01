SRC_NAME=libcap-ng-0.9.6
SRC_URL=https://codeload.github.com/stevegrubb/libcap-ng/tar.gz/c382c641ca5730442289c09d3c3d30cc2c8635a9
SRC_SHA256=6d67537dbe456ab63448b252b1b8a248027c7ff3d0642e4033a16be72cbc4f6e

all: download_test extract_test config_test
	$(MAKE) -j$(HOST_NCPU) -C $(SRC_NAME)/src SUBDIRS=

download_test:
	( if [ ! -f $(SRC_NAME).tar.gz ]; then \
		wget -t5 --timeout=20 -O $(SRC_NAME).tar.gz $(SRC_URL); \
	fi; \
	echo "$(SRC_SHA256)  $(SRC_NAME).tar.gz" | sha256sum -c -; \
	)

extract_test:
	( if [ ! -d $(SRC_NAME) ]; then \
		mkdir $(SRC_NAME) && \
		tar -xf $(SRC_NAME).tar.gz --strip-components=1 -C $(SRC_NAME); \
	fi )

config_test:
	( if [ ! -f config_done ]; then \
		$(MAKE) configure && touch config_done; \
	fi )

configure:
	( cd $(SRC_NAME) && \
	autoreconf -fi && \
	./configure \
		--prefix=$(STAGEDIR) \
		--libdir=$(STAGEDIR)/lib \
		--enable-shared \
		--disable-static \
		--disable-cap-audit \
		--disable-deprecated \
		--without-python \
		--without-python3 \
		--with-capability_header=$(CONFIG_CROSS_COMPILER_ROOT)/mipsel-linux-uclibc/sysroot/usr/include/linux/capability.h \
		--host=$(HOST_TARGET) \
		--build=$(HOST_BUILD) ; \
	)

install:
	$(MAKE) -C $(SRC_NAME)/src install SUBDIRS= DESTDIR=""

romfs:
	cp -fP $(DESTDIR)/lib/libcap-ng.so* $(ROMFSDIR)/lib

clean:
	if [ -f $(SRC_NAME)/Makefile ]; then \
		$(MAKE) -C $(SRC_NAME) distclean; \
	fi
	rm -f config_done
