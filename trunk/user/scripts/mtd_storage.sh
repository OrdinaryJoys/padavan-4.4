#!/bin/sh
# shellcheck shell=busybox

result=0
mtd_part_name="Storage"
mtd_part_dev="/dev/mtdblock5"
mtd_part_size=65536
dir_storage="/etc/storage"
slk="/tmp/.storage_locked"
tbz="/tmp/storage.tar.bz2"
hsh="/tmp/hashes/storage_md5"
op_lock="/tmp/.storage_operation"
work_dir=""
restore_container=""
lock_owned=0
max_tar_size=8388608

func_get_mtd()
{
	local mtd_part mtd_char mtd_idx mtd_hex
	mtd_part=$(grep "\"$mtd_part_name\"" /proc/mtd)
	mtd_char=$(echo "$mtd_part" | cut -d':' -f1)
	mtd_hex=$(echo "$mtd_part" | cut -d' ' -f2)
	mtd_idx=$(echo "$mtd_char" | cut -c4-5)
	if [ -n "$mtd_idx" ] && [ "$mtd_idx" -ge 4 ]; then
		mtd_part_dev="/dev/mtdblock${mtd_idx}"
		mtd_part_size=$((0x$mtd_hex))
	else
		logger -t "Storage" "Cannot find MTD partition: $mtd_part_name"
		exit 1
	fi
}

func_cleanup()
{
	if [ -n "$restore_container" ] && [ -d "$restore_container" ]; then
		if [ -e "$restore_container/previous" ]; then
			logger -t "Storage" "Retained recovery copy: $restore_container/previous"
		else
			rm -rf "$restore_container"
		fi
	fi
	if [ "$lock_owned" = 1 ]; then
		rm -rf "$work_dir"
		exec 9>&-
	fi
}

func_begin()
{
	[ "$(id -u)" = 0 ] || return 1
	umask 077
	if ! mkdir -m 700 "$op_lock" 2>/dev/null; then
		if [ -L "$op_lock" ] || [ ! -d "$op_lock" ] ||
		   [ "$(stat -c %u "$op_lock" 2>/dev/null)" != 0 ]; then
			logger -t "Storage" "Unsafe storage operation lock"
			return 1
		fi
	fi
	chmod 700 "$op_lock" || return 1
	[ ! -L "$op_lock/lock" ] || return 1
	exec 9> "$op_lock/lock" || return 1
	if ! flock -n 9; then
		exec 9>&-
		logger -t "Storage" "Another storage operation is active"
		return 1
	fi
	# No PID file: the kernel releases flock after all holders exit.
	lock_owned=1
	work_dir="$op_lock/work"
	trap 'func_cleanup' EXIT
	trap 'exit 1' HUP INT TERM
	rm -rf "$work_dir" || return 1
	mkdir -m 700 "$work_dir" || return 1
	tmp="$work_dir/storage.tar"
	func_recover_storage
}

# A killed restore may leave the old tree between the two directory renames.
# Never create a new empty live tree before discovering that retained copy.
func_empty_dir()
{
	local member
	[ -d "$1" ] && [ ! -L "$1" ] || return 1
	for member in "$1"/* "$1"/.[!.]* "$1"/..?*; do
		if [ -e "$member" ] || [ -L "$member" ]; then return 1; fi
	done
	return 0
}

func_check_recovery_container()
{
	local candidate member leaf
	candidate=$1
	leaf=${candidate##*.}
	case "$leaf" in ''|*[!0-9]*) return 1;; esac
	[ -d "$candidate" ] && [ ! -L "$candidate" ] &&
		[ "$(stat -c %u "$candidate" 2>/dev/null)" = 0 ] &&
		[ "$(stat -c %a "$candidate" 2>/dev/null)" = 700 ] || return 1
	for member in "$candidate"/* "$candidate"/.[!.]* "$candidate"/..?*; do
		[ -e "$member" ] || [ -L "$member" ] || continue
		case "${member##*/}" in
		storage|previous)
			[ -d "$member" ] && [ ! -L "$member" ] &&
				[ "$(stat -c %u "$member" 2>/dev/null)" = 0 ] || return 1
			;;
		*) return 1;;
		esac
	done
	if [ -d "$candidate/previous" ]; then
		[ -f "$candidate/previous/start_script.sh" ] &&
			[ ! -L "$candidate/previous/start_script.sh" ] || return 1
	fi
}

func_recover_storage()
{
	local candidate parent previous_count selected
	parent=${dir_storage%/*}
	previous_count=0
	selected=""
	# Inspect every candidate before changing any of them. Multiple retained
	# originals or an untrusted container require an explicit operator choice.
	for candidate in "$parent"/.storage-restore.*; do
		[ -e "$candidate" ] || [ -L "$candidate" ] || continue
		if ! func_check_recovery_container "$candidate"; then
			logger -t "Storage recovery" "Unsafe recovery container retained: $candidate"
			return 1
		fi
		if [ -d "$candidate/previous" ]; then
			previous_count=$((previous_count + 1))
			selected=$candidate
		fi
	done
	if [ "$previous_count" -gt 1 ]; then
		logger -t "Storage recovery" "Multiple recovery copies retained; refusing to choose"
		return 1
	fi
	if [ "$previous_count" = 1 ]; then
		if [ -e "$dir_storage" ] || [ -L "$dir_storage" ]; then
			if ! func_empty_dir "$dir_storage"; then
				logger -t "Storage recovery" "Live tree conflicts with retained copy: $selected/previous"
				return 1
			fi
		fi
		/sbin/storage_validate --rename-directory "$selected/previous" "$dir_storage" || return 1
		logger -t "Storage recovery" "Recovered retained original from $selected/previous"
		rm -rf "$selected" || return 1
	fi
	# No previous tree means publication never moved the original (or old
	# cleanup already finished). Discard only private staging, with live data
	# still present. A missing/unsafe live tree is never silently manufactured.
	for candidate in "$parent"/.storage-restore.*; do
		[ -e "$candidate" ] || [ -L "$candidate" ] || continue
		if [ ! -d "$dir_storage" ] || [ -L "$dir_storage" ]; then
			logger -t "Storage recovery" "Staging retained because live storage is missing: $candidate"
			return 1
		fi
		rm -rf "$candidate" || return 1
	done
}

func_mdir()
{
	[ ! -L "$dir_storage" ] || return 1
	if [ ! -d "$dir_storage" ]; then
		mkdir -p "$dir_storage" && chmod 755 "$dir_storage" || return 1
	fi
}

func_stop_apps()
{
	killall -q rstats
	[ $? -eq 0 ] && sleep 1
}

func_start_apps()
{
	/sbin/rstats 9>&-
}

func_unpack()
{
	local fsz
	# A corrupt stream must not publish its partially decompressed output.
	# POSIX file-size blocks are 512 bytes; stat also enforces the exact cap.
	if ! (ulimit -f 16384 && bzcat "$1" > "$tmp") 2>/dev/null; then
		logger -t "Storage" "Cannot decompress storage, or expanded size limit exceeded"
		return 1
	fi
	fsz=$(stat -c %s "$tmp" 2>/dev/null)
	case "$fsz" in ''|*[!0-9]*) return 1;; esac
	[ "$fsz" -le "$max_tar_size" ] && [ "$fsz" -ge 1024 ]
}

func_record_hash()
{
	local digest _ignored
	md5sum "$tmp" > "$work_dir/hash.pending" || return 1
	read -r digest _ignored < "$work_dir/hash.pending"
	case "$digest" in ''|*[!0-9a-f]*) return 1;; esac
	[ "${#digest}" = 32 ] || return 1
	printf '%s  /tmp/storage.tar\n' "$digest" > "$work_dir/hash.commit" || return 1
	/sbin/storage_validate --replace-file "$work_dir/hash.commit" "$hsh"
}

# Repair the previous candidate's implicit 0700 DNS directory after it has
# been saved with an explicit header.  Only the known public-data layout is
# migrated: private/unknown entries and aliases keep their original boundary.
func_dns_directory_access()
{
	local dnsdir member mode
	dnsdir="$1/dnsmasq"
	if [ ! -e "$dnsdir" ] && [ ! -L "$dnsdir" ]; then
		return 0
	fi
	if [ -L "$dnsdir" ] || [ ! -d "$dnsdir" ] ||
	   [ "$(stat -c %u "$dnsdir" 2>/dev/null)" != 0 ]; then
		logger -t "Storage permissions" "Linked or nonstandard DNS directory retained; review data access manually"
		return 0
	fi
	mode=$(stat -c %a "$dnsdir" 2>/dev/null) || {
		logger -t "Storage permissions" "DNS directory mode is unavailable; retained without permission migration"
		return 0
	}
	[ "$mode" = 700 ] || return 0
	for member in "$dnsdir"/* "$dnsdir"/.[!.]* "$dnsdir"/..?*; do
		[ -e "$member" ] || [ -L "$member" ] || continue
		case "${member##*/}" in
		dnsmasq.conf|hosts|dhcp.conf)
			if [ ! -L "$member" ] && [ -f "$member" ] &&
			   [ "$(stat -c %u "$member" 2>/dev/null)" = 0 ] &&
			   [ "$(stat -c %h "$member" 2>/dev/null)" = 1 ]; then
				continue
			fi
			;;
		esac
		logger -t "Storage permissions" "Private DNS directory with unknown entries or aliases retained; review data access manually"
		return 0
	done
	chmod 755 "$dnsdir" || return 1
	logger -t "Storage permissions" "Repaired known DNS data directory access; file permissions preserved"
	return 0
}

func_install_tar()
{
	local parent available budget old_storage
	parent=${dir_storage%/*}
	available=$(df -Pk "$parent" 2>/dev/null | awk 'NR == 2 {print $4}')
	case "$available" in ''|*[!0-9]*) return 1;; esac
	# The old tree is still present: df free is the budget for the new tree.
	# Reserve 64 KiB for the exchange directory and unrelated small writes.
	[ "$available" -gt 64 ] || return 1
	budget=$((available * 1024 - 65536))
	/sbin/storage_validate "$tmp" "$budget" || return 1
	restore_container="$parent/.storage-restore.$$"
	mkdir -m 700 "$restore_container" || return 1
	mkdir -m 700 "$restore_container/storage" || return 1
	# A private parent keeps archive-supplied directory modes inaccessible
	# while extraction is in progress. -o never restores archive ownership.
	# Legacy backups omit directory headers.  Their implicit parents need
	# 0755 for low-uid readers; explicit private directory/file modes remain.
	if ! (umask 022; tar xof "$tmp" -C "$restore_container/storage") 2>/dev/null; then
		logger -t "Storage restore" "Cannot extract complete validated storage"
		return 1
	fi
	[ -f "$restore_container/storage/start_script.sh" ] &&
		[ ! -L "$restore_container/storage/start_script.sh" ] || return 1
	# Restored configuration must not become replaceable by other users.
	chmod -R go-w "$restore_container/storage" || return 1
	chmod 755 "$restore_container/storage" || return 1
	func_dns_directory_access "$restore_container/storage" || return 1
	old_storage="$restore_container/previous"
	if [ -e "$dir_storage" ]; then
		[ ! -L "$dir_storage" ] || return 1
		/sbin/storage_validate --rename-directory "$dir_storage" "$old_storage" || return 1
	fi
	if ! /sbin/storage_validate --rename-directory "$restore_container/storage" "$dir_storage"; then
		if [ -e "$old_storage" ]; then
			/sbin/storage_validate --rename-directory "$old_storage" "$dir_storage" ||
				logger -t "Storage restore" "Rollback failed; original retained at $old_storage"
		fi
		return 1
	fi
	rm -rf "$old_storage"
}

func_load()
{
	if func_unpack "$mtd_part_dev" && func_install_tar && func_record_hash; then
		rm -f "$slk"
	else
		result=1
		logger -t "Storage load" "Invalid or incomplete storage data: $mtd_part_dev"
	fi
}

func_tarb()
{
	# One recursive invocation includes dotfiles and empty directories, and
	# cannot lose earlier members when an xargs argument batch is exceeded.
	if ! (cd "$dir_storage" &&
		find . -print0 | xargs -0 touch -c -h -t 201001010000.00 &&
		tar -cf "$tmp" .); then
		logger -t "Storage" "Cannot create complete storage tarball"
		return 1
	fi
	/sbin/storage_validate "$tmp" "$max_tar_size"
}

func_save()
{
	local fsz digest previous _ignored archive
	archive="$work_dir/storage.tar.bz2"
	md5sum "$tmp" > "$work_dir/hash.pending" || return 1
	read -r digest _ignored < "$work_dir/hash.pending"
	previous=$(cut -d' ' -f1 "$hsh" 2>/dev/null)
	if [ -n "$digest" ] && [ "$digest" = "$previous" ]; then
		echo "Storage hash is not changed, skip write to MTD partition. Exit."
		return 0
	fi
	if ! bzip2 -c -9 "$tmp" > "$archive"; then
		logger -t "Storage save" "Cannot compress complete storage tarball"
		return 1
	fi
	fsz=$(stat -c %s "$archive" 2>/dev/null)
	case "$fsz" in ''|*[!0-9]*) return 1;; esac
	if [ "$fsz" -lt 16 ] || [ "$fsz" -gt "$mtd_part_size" ]; then
		logger -t "Storage save" "Invalid storage final data size: $fsz"
		return 1
	fi
	if ! mtd_write write "$archive" "$mtd_part_name"; then
		logger -t "Storage save" "Error writing storage MTD; previous hash retained"
		return 1
	fi
	# Commit the hash only after the flash operation succeeds.
	func_record_hash
}

func_backup()
{
	if ! bzip2 -c -9 "$tmp" > "$work_dir/backup.bz2"; then
		logger -t "Storage backup" "Cannot create complete BZ2 file"
		return 1
	fi
	/sbin/storage_validate --publish-backup "$work_dir/backup.bz2" "$tbz"
}

func_restore()
{
	local fsz
	[ -f "$tbz" ] && [ ! -L "$tbz" ] || return 1
	[ "$(stat -c %u "$tbz" 2>/dev/null)" = 0 ] || return 1
	fsz=$(stat -c %s "$tbz" 2>/dev/null)
	case "$fsz" in ''|*[!0-9]*) return 1;; esac
	if [ "$fsz" -lt 16 ] || [ "$fsz" -gt "$mtd_part_size" ]; then
		logger -t "Storage restore" "Invalid BZ2 file size: $fsz"
		return 1
	fi
	# Snapshot the root-owned upload in a private directory before parsing.
	cp "$tbz" "$work_dir/input.bz2" || return 1
	func_unpack "$work_dir/input.bz2" || return 1
	# Validate before stopping apps or changing any current storage files.
	local available parent budget
	parent=${dir_storage%/*}
	available=$(df -Pk "$parent" 2>/dev/null | awk 'NR == 2 {print $4}')
	case "$available" in ''|*[!0-9]*) return 1;; esac
	[ "$available" -gt 64 ] || return 1
	budget=$((available * 1024 - 65536))
	/sbin/storage_validate "$tmp" "$budget" || return 1
	func_stop_apps
	if func_install_tar; then
		rm -f "$slk" "$tbz"
		result=0
	else
		result=1
	fi
	func_start_apps
	return "$result"
}

func_erase()
{
	mtd_write erase $mtd_part_name
	if [ $? -eq 0 ] ; then
		rm -f $hsh
		rm -rf $dir_storage
		mkdir -p -m 755 $dir_storage
		touch "$slk"
	else
		result=1
	fi
}

func_reset()
{
	rm -f $slk
	rm -rf $dir_storage
	mkdir -p -m 755 $dir_storage
}

func_fill()
{
	dir_httpssl="$dir_storage/https"
	dir_dnsmasq="$dir_storage/dnsmasq"
	dir_ovpnsvr="$dir_storage/openvpn/server"
	dir_ovpncli="$dir_storage/openvpn/client"
	dir_sswan="$dir_storage/strongswan"
	dir_sswan_crt="$dir_sswan/ipsec.d"
	dir_inadyn="$dir_storage/inadyn"
	dir_crond="$dir_storage/cron/crontabs"
	dir_wlan="$dir_storage/wlan"
	dir_chnroute="$dir_storage/chinadns"
	#dir_gfwlist="$dir_storage/gfwlist"

	script_start="$dir_storage/start_script.sh"
	script_started="$dir_storage/started_script.sh"
	script_shutd="$dir_storage/shutdown_script.sh"
	script_postf="$dir_storage/post_iptables_script.sh"
	script_postw="$dir_storage/post_wan_script.sh"
	script_inets="$dir_storage/inet_state_script.sh"
	script_vpnsc="$dir_storage/vpns_client_script.sh"
	script_vpncs="$dir_storage/vpnc_server_script.sh"
	script_ezbtn="$dir_storage/ez_buttons_script.sh"

	user_hosts="$dir_dnsmasq/hosts"
	user_dnsmasq_conf="$dir_dnsmasq/dnsmasq.conf"
	user_dhcp_conf="$dir_dnsmasq/dhcp.conf"
	user_ovpnsvr_conf="$dir_ovpnsvr/server.conf"
	user_ovpncli_conf="$dir_ovpncli/client.conf"
	user_inadyn_conf="$dir_inadyn/inadyn.conf"
	user_sswan_conf="$dir_sswan/strongswan.conf"
	user_sswan_ipsec_conf="$dir_sswan/ipsec.conf"
	user_sswan_secrets="$dir_sswan/ipsec.secrets"
	
	chnroute_file="/etc_ro/chnroute.bz2"
	#gfwlist_conf_file="/etc_ro/gfwlist.bz2"

	# create crond dir
	[ ! -d "$dir_crond" ] && mkdir -p -m 730 "$dir_crond"

	# create https dir
	[ ! -d "$dir_httpssl" ] && mkdir -p -m 700 "$dir_httpssl"

	# create chnroute.txt
	if [ ! -d "$dir_chnroute" ] ; then
		if [ -f "$chnroute_file" ]; then
			mkdir -p "$dir_chnroute" && tar jxf "$chnroute_file" -C "$dir_chnroute"
		fi
	fi

	# create gfwlist
	#if [ ! -d "$dir_gfwlist" ] ; then
		#if [ -f "$gfwlist_conf_file" ]; then	
			#mkdir -p "$dir_gfwlist" && tar jxf "$gfwlist_conf_file" -C "$dir_gfwlist"
		#fi
	#fi

	# create start script
	if [ ! -f "$script_start" ] ; then
		reset_ss.sh -a
	fi

	# create started script
	if [ ! -f "$script_started" ] ; then
		cat > "$script_started" <<EOF
#!/bin/sh

### Custom user script
### Called after router started and network is ready

### Example - load ipset modules
#modprobe ip_set
#modprobe ip_set_hash_ip
#modprobe ip_set_hash_net
#modprobe ip_set_bitmap_ip
#modprobe ip_set_list_set
#modprobe xt_set
echo 4096 131072  6291456 > /proc/sys/net/ipv4/tcp_rmem
echo 4194304 >/proc/sys/net/core/rmem_max
echo 212992 > /proc/sys/net/core/rmem_default
#drop caches
sync && echo 3 > /proc/sys/vm/drop_caches

# Roaming assistant for mt76xx WiFi
#iwpriv ra0 set KickStaRssiLow=-85
#iwpriv ra0 set AssocReqRssiThres=-80
#iwpriv rai0 set KickStaRssiLow=-85
#iwpriv rai0 set AssocReqRssiThres=-80

# Mount SATA disk
#mdev -s

#wing <HOST:443> <PASS>
#wing 192.168.1.9:1080
#ipset add gfwlist 8.8.4.4


EOF
		chmod 755 "$script_started"
	fi

	# create shutdown script
	if [ ! -f "$script_shutd" ] ; then
		cat > "$script_shutd" <<EOF
#!/bin/sh

### Custom user script
### Called before router shutdown
### \$1 - action (0: reboot, 1: halt, 2: power-off)

EOF
		chmod 755 "$script_shutd"
	fi

	# create post-iptables script

	if [ ! -f "$script_postf" ] ; then
		cat > "$script_postf" <<EOF
#!/bin/sh

### Custom user script
### Called after internal iptables reconfig (firewall update)

#wing resume

EOF
		chmod 755 "$script_postf"
	fi

	# create post-wan script
	if [ ! -f "$script_postw" ] ; then
		cat > "$script_postw" <<EOF
#!/bin/sh

### Custom user script
### Called after internal WAN up/down action
### \$1 - WAN action (up/down)
### \$2 - WAN interface name (e.g. eth3 or ppp0)
### \$3 - WAN IPv4 address

EOF
		chmod 755 "$script_postw"
	fi

	# create inet-state script
	if [ ! -f "$script_inets" ] ; then
		cat > "$script_inets" <<EOF
#!/bin/sh

### Custom user script
### Called on Internet status changed
### \$1 - Internet status (0/1)
### \$2 - elapsed time (s) from previous state

logger -t "di" "Internet state: \$1, elapsed time: \$2s."

EOF
		chmod 755 "$script_inets"
	fi

	# create vpn server action script
	if [ ! -f "$script_vpnsc" ] ; then
		cat > "$script_vpnsc" <<EOF
#!/bin/sh

### Custom user script
### Called after remote peer connected/disconnected to internal VPN server
### \$1 - peer action (up/down)
### \$2 - peer interface name (e.g. ppp10)
### \$3 - peer local IP address
### \$4 - peer remote IP address
### \$5 - peer name

peer_if="\$2"
peer_ip="\$4"
peer_name="\$5"

### example: add static route to private LAN subnet behind a remote peer

func_ipup()
{
#  if [ "\$peer_name" == "dmitry" ] ; then
#    route add -net 192.168.5.0 netmask 255.255.255.0 dev \$peer_if
#  elif [ "\$peer_name" == "victoria" ] ; then
#    route add -net 192.168.8.0 netmask 255.255.255.0 dev \$peer_if
#  fi
   return 0
}

func_ipdown()
{
#  if [ "\$peer_name" == "dmitry" ] ; then
#    route del -net 192.168.5.0 netmask 255.255.255.0 dev \$peer_if
#  elif [ "\$peer_name" == "victoria" ] ; then
#    route del -net 192.168.8.0 netmask 255.255.255.0 dev \$peer_if
#  fi
   return 0
}

case "\$1" in
up)
  func_ipup
  ;;
down)
  func_ipdown
  ;;
esac

EOF
		chmod 755 "$script_vpnsc"
	fi

	# create vpn client action script
	if [ ! -f "$script_vpncs" ] ; then
		cat > "$script_vpncs" <<EOF
#!/bin/sh

### Custom user script
### Called after internal VPN client connected/disconnected to remote VPN server
### \$1        - action (up/down)
### \$IFNAME   - tunnel interface name (e.g. ppp5 or tun0)
### \$IPLOCAL  - tunnel local IP address
### \$IPREMOTE - tunnel remote IP address
### \$DNS1     - peer DNS1
### \$DNS2     - peer DNS2

# private LAN subnet behind a remote server (example)
peer_lan="192.168.9.0"
peer_msk="255.255.255.0"

### example: add static route to private LAN subnet behind a remote server

func_ipup()
{
#  route add -net \$peer_lan netmask \$peer_msk gw \$IPREMOTE dev \$IFNAME
   return 0
}

func_ipdown()
{
#  route del -net \$peer_lan netmask \$peer_msk gw \$IPREMOTE dev \$IFNAME
   return 0
}

logger -t vpnc-script "\$IFNAME \$1"

case "\$1" in
up)
  func_ipup
  ;;
down)
  func_ipdown
  ;;
esac

EOF
		chmod 755 "$script_vpncs"
	fi

	# create Ez-Buttons script
	if [ ! -f "$script_ezbtn" ] ; then
		cat > "$script_ezbtn" <<EOF
#!/bin/sh

### Custom user script
### Called on WPS or FN button pressed
### \$1 - button param

[ -x /opt/bin/on_wps.sh ] && /opt/bin/on_wps.sh \$1 &

EOF
		chmod 755 "$script_ezbtn"
	fi

	# create user dnsmasq.conf
	[ ! -d "$dir_dnsmasq" ] && mkdir -p -m 755 "$dir_dnsmasq"
	for i in dnsmasq.conf hosts ; do
		[ -f "$dir_storage/$i" ] && mv -n "$dir_storage/$i" "$dir_dnsmasq"
	done
	if [ ! -f "$user_dnsmasq_conf" ] ; then
		cat > "$user_dnsmasq_conf" <<EOF
# Custom user conf file for dnsmasq
# Please add needed params only!

### Web Proxy Automatic Discovery (WPAD)
dhcp-option=252,"\n"

### Set the limit on DHCP leases, the default is 150
#dhcp-lease-max=150

### Add local-only domains, queries are answered from hosts or DHCP only
#local=/router/localdomain/

### Examples:

### Enable built-in TFTP server
#enable-tftp

### Set the root directory for files available via TFTP.
#tftp-root=/opt/srv/tftp

### Make the TFTP server more secure
#tftp-secure

### Set the boot filename for netboot/PXE
#dhcp-boot=pxelinux.0

### Log for all queries
#log-queries

### Keep DHCP host name valid at any times
#dhcp-to-host

EOF
	if [ -f /usr/bin/vlmcsd ]; then
		cat >> "$user_dnsmasq_conf" <<EOF
### vlmcsd related
srv-host=_vlmcs._tcp,my.router,1688,0,100

EOF
	fi

	if [ -f /usr/bin/wing ]; then
		cat >> "$user_dnsmasq_conf" <<EOF
# Custom domains to gfwlist
#gfwlist=mit.edu
#gfwlist=openwrt.org,lede-project.org
#gfwlist=github.com,github.io,githubusercontent.com

EOF
	fi

	if [ -d "${dir_gfwlist:-}" ]; then
		cat >> "$user_dnsmasq_conf" <<EOF
### gfwlist related (resolve by port 5353)
#min-cache-ttl=3600
#conf-dir=/etc/storage/gfwlist

EOF
	fi
		chmod 644 "$user_dnsmasq_conf"
	fi

	# create user dns servers
	if [ ! -f "$user_dhcp_conf" ] ; then
		cat > "$user_dhcp_conf" <<EOF
#6C:96:CF:E0:95:55,192.168.1.10,iMac

EOF
		chmod 644 "$user_dhcp_conf"
	fi

	# create user inadyn.conf"
	[ ! -d "$dir_inadyn" ] && mkdir -p -m 755 "$dir_inadyn"
	if [ ! -f "$user_inadyn_conf" ] ; then
		cat > "$user_inadyn_conf" <<EOF
# Custom user conf file for inadyn DDNS client
# Please add only new custom system!

### Example for twoDNS.de:

#system custom@http_srv_basic_auth
#  ssl
#  checkip-url checkip.two-dns.de /
#  server-name update.twodns.de
#  server-url /update\?hostname=
#  username account
#  password secret
#  alias example.dd-dns.de

EOF
		chmod 644 "$user_inadyn_conf"
	fi

	# create user hosts
	if [ ! -f "$user_hosts" ] ; then
		cat > "$user_hosts" <<EOF
# Custom user hosts file
# Example:
# 192.168.1.100		Boo

EOF
		chmod 644 "$user_hosts"
	fi

	# create user AP confs
	[ ! -d "$dir_wlan" ] && mkdir -p -m 755 "$dir_wlan"
	if [ ! -f "$dir_wlan/AP.dat" ] ; then
		cat > "$dir_wlan/AP.dat" <<EOF
# Custom user AP conf file

EOF
		chmod 644 "$dir_wlan/AP.dat"
	fi

	if [ ! -f "$dir_wlan/AP_5G.dat" ] ; then
		cat > "$dir_wlan/AP_5G.dat" <<EOF
# Custom user AP conf file

EOF
		chmod 644 "$dir_wlan/AP_5G.dat"
	fi

	# create openvpn files
	if [ -x /usr/sbin/openvpn ] ; then
		[ ! -d "$dir_ovpncli" ] && mkdir -p -m 700 "$dir_ovpncli"
		[ ! -d "$dir_ovpnsvr" ] && mkdir -p -m 700 "$dir_ovpnsvr"
		dir_ovpn="$dir_storage/openvpn"
		for i in ca.crt dh1024.pem server.crt server.key server.conf ta.key ; do
			[ -f "$dir_ovpn/$i" ] && mv -n "$dir_ovpn/$i" "$dir_ovpnsvr"
		done
		if [ ! -f "$user_ovpnsvr_conf" ] ; then
			cat > "$user_ovpnsvr_conf" <<EOF
# Custom user conf file for OpenVPN server
# Please add needed params only!

### Max clients limit
max-clients 10

### Internally route client-to-client traffic
client-to-client

### Allow clients with duplicate "Common Name"
;duplicate-cn

### Legacy LZO adaptive compression
;comp-lzo adaptive
;push "comp-lzo adaptive"

### Keepalive and timeout
keepalive 10 60

### Process priority level (0..19)
nice 3

### Syslog verbose level
verb 0
mute 10

EOF
			chmod 644 "$user_ovpnsvr_conf"
		fi

		if [ ! -f "$user_ovpncli_conf" ] ; then
			cat > "$user_ovpncli_conf" <<EOF
# Custom user conf file for OpenVPN client
# Please add needed params only!

### If your server certificates with the nsCertType field set to "server"
remote-cert-tls server

### Process priority level (0..19)
nice 0

### Syslog verbose level
verb 0
mute 10

EOF
			chmod 644 "$user_ovpncli_conf"
		fi
	fi

	# create strongswan files
	if [ -x /usr/sbin/ipsec ] ; then
		[ ! -d "$dir_sswan" ] && mkdir -p -m 700 "$dir_sswan"
		[ ! -d "$dir_sswan_crt" ] && mkdir -p -m 700 "$dir_sswan_crt"
		[ ! -d "$dir_sswan_crt/cacerts" ] && mkdir -p -m 700 "$dir_sswan_crt/cacerts"
		[ ! -d "$dir_sswan_crt/certs" ] && mkdir -p -m 700 "$dir_sswan_crt/certs"
		[ ! -d "$dir_sswan_crt/private" ] && mkdir -p -m 700 "$dir_sswan_crt/private"

		if [ ! -f "$user_sswan_conf" ] ; then
			cat > "$user_sswan_conf" <<EOF
### strongswan.conf - user strongswan configuration file

EOF
			chmod 644 "$user_sswan_conf"
		fi
		if [ ! -f "$user_sswan_ipsec_conf" ] ; then
			cat > "$user_sswan_ipsec_conf" <<EOF
### ipsec.conf - user strongswan IPsec configuration file

EOF
			chmod 644 "$user_sswan_ipsec_conf"
		fi
		if [ ! -f "$user_sswan_secrets" ] ; then
			cat > "$user_sswan_secrets" <<EOF
### ipsec.secrets - user strongswan IPsec secrets file

EOF
			chmod 644 "$user_sswan_secrets"
		fi
	fi
}

func_begin || exit 1

case "$1" in
load)
	func_get_mtd
	func_mdir || exit 1
	func_load
	;;
save)
	[ -f "$slk" ] && exit 1
	func_get_mtd
	func_mdir && func_tarb && func_save || result=1
	;;
backup)
	func_mdir && func_tarb && func_backup || result=1
	;;
restore)
	func_get_mtd
	func_restore || result=1
	;;
erase)
	func_get_mtd
	func_erase
	;;
reset)
	func_stop_apps
	func_reset
	func_fill
	func_start_apps
	;;
fill)
	func_mdir || exit 1
	func_fill
	;;
*)
	echo "Usage: $0 {load|save|backup|restore|erase|reset|fill}"
	exit 1
	;;
esac

exit $result
