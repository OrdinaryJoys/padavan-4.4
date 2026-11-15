SRC_NAME = wireguard-tools-1.0.20260223
SRC_URL = https://git.zx2c4.com/wireguard-tools/snapshot/wireguard-tools-1.0.20260223.tar.xz
SRC_SHA256 = af459827b80bfd31b83b08077f4b5843acb7d18ad9a33a2ef532d3090f291fbf
THISDIR = $(shell pwd)

all: download_test extract_test
	$(MAKE) -C $(SRC_NAME)/src WITH_BASHCOMPLETION=no WITH_WGQUICK=yes WITH_SYSTEMDUNITS=no wg

download_test:
	@set -eu; archive="$(SRC_NAME).tar.xz"; tmp="$$archive.tmp.$$$$"; \
	trap 'rm -f "$$tmp"' EXIT; trap 'exit 1' HUP INT TERM; \
	if [ -f "$$archive" ] && printf '%s  %s\n' '$(SRC_SHA256)' "$$archive" | sha256sum -c -; then \
		exit 0; \
	fi; \
	for attempt in 1 2 3; do \
		rm -f "$$tmp"; \
		if wget -t2 --timeout=20 -O "$$tmp" '$(SRC_URL)' && \
		   printf '%s  %s\n' '$(SRC_SHA256)' "$$tmp" | sha256sum -c -; then \
			mv -f "$$tmp" "$$archive"; exit 0; \
		fi; \
	done; \
	echo "Unable to download a verified $(SRC_NAME) archive" >&2; exit 1

extract_test:
	( if [ ! -d $(SRC_NAME) ]; then \
		tar -xf $(SRC_NAME).tar.xz; \
	fi )

clean:
	if [ -f $(SRC_NAME)/src/Makefile ] ; then \
		$(MAKE) -C $(SRC_NAME)/src clean ; \
	fi

romfs:
	$(ROMFSINST) -p +x $(THISDIR)/$(SRC_NAME)/src/wg /usr/bin/wg

