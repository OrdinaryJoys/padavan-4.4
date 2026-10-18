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
