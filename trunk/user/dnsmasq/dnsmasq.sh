#!/bin/sh

filter_aaaa=`nvram get dhcp_filter_aaa`
min_ttl=`nvram get dhcp_min_ttl`
if [ $filter_aaaa = 0 ]; then
sed -i '/filter-aaaa/d' /etc/storage/dnsmasq/dnsmasq.conf
 else 
sed -i '/filter-aaaa/d' /etc/storage/dnsmasq/dnsmasq.conf
	cat >>/etc/storage/dnsmasq/dnsmasq.conf <<EOF
filter-aaaa
EOF
fi

# dnsmasq 2.93 dropped the vendor 'gfwlist' option (shadowsocks gfwlist split).
# This profile builds without shadowsocks, so a stale line would only make
# dnsmasq fail to start. Comment it out instead.
if grep -q '^gfwlist=' /etc/storage/dnsmasq/dnsmasq.conf 2>/dev/null; then
	sed -i 's/^gfwlist=/#gfwlist=/' /etc/storage/dnsmasq/dnsmasq.conf
	logger -t dnsmasq "disabled stale gfwlist= line (option not available)"
fi

# Boot-time guard: a single unknown option in the user's custom file would
# otherwise keep dnsmasq from starting, taking LAN DNS and DHCP down with it.
# If the merged config does not parse, isolate the custom file (kept as .bad)
# and let the generated main config start with defaults.
if [ -f /etc/dnsmasq.conf ] && ! /usr/sbin/dnsmasq --test -C /etc/dnsmasq.conf >/dev/null 2>&1; then
	if [ -s /etc/storage/dnsmasq/dnsmasq.conf ]; then
		mv -f /etc/storage/dnsmasq/dnsmasq.conf /etc/storage/dnsmasq/dnsmasq.conf.bad
		: > /etc/storage/dnsmasq/dnsmasq.conf
		logger -t dnsmasq "config test failed; custom config moved to dnsmasq.conf.bad"
		if /usr/sbin/dnsmasq --test -C /etc/dnsmasq.conf >/dev/null 2>&1; then
			logger -t dnsmasq "config test now passes with defaults"
		else
			logger -t dnsmasq "config test still fails after isolating the custom file"
		fi
	else
		logger -t dnsmasq "config test failed and the custom file is empty"
	fi
fi
