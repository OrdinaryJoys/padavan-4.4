SRC_NAME=miniupnpd-2.3.11

# reference to iptables package
IPT_VERSION:=iptables-1.8.7

# IPv6/IGDv2 stay off (Windows does not support IGDv2 and UPnP breaks).
# --leasefile / --vendorcfg match the keys written by rc into /etc/miniupnpd.conf.
CONFIG_OPTIONS:=--firewall=iptables --leasefile --vendorcfg

IPTABLESPATH=$(ROOTDIR)/user/iptables/$(IPT_VERSION)

all:
	cd $(SRC_NAME) && ./configure $(CONFIG_OPTIONS)
	$(MAKE) -C $(SRC_NAME) -f Makefile.linux IPTABLESPATH=$(IPTABLESPATH)

clean:
	$(MAKE) -C $(SRC_NAME) -f Makefile.linux clean
	rm -f miniupnpd

romfs:
	cp $(SRC_NAME)/miniupnpd .
	$(ROMFSINST) /usr/bin/miniupnpd
