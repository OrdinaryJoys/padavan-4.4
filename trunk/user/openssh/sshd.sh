#!/bin/sh

dir_storage="/etc/storage/openssh"
sshd_config="$dir_storage/sshd_config"

rsa_key="$dir_storage/ssh_host_rsa_key"
ed25519_key="$dir_storage/ssh_host_ed25519_key"

func_create_config()
{
	config_output=${1:-$sshd_config}
	cat > "$config_output" <<EOF || return 1
# The strategy used for options in this file is to specify options with
# their default value where possible, but leave them commented.
# Uncommented options override the default value.

#Port 22
#AddressFamily any
#ListenAddress 0.0.0.0
#ListenAddress ::

# The default requires explicit activation of protocol 1
#Protocol 2

# HostKey for protocol version 1
#HostKey ${dir_storage}/ssh_host_key

# HostKeys for protocol version 2
HostKey ${rsa_key}
#HostKey ${dir_storage}/ssh_host_ecdsa_key
HostKey ${ed25519_key}

# Lifetime and size of ephemeral version 1 server key
#KeyRegenerationInterval 1h
#ServerKeyBits 1024

# Ciphers and keying
#RekeyLimit default none

# Logging
# obsoletes QuietMode and FascistLogging
#SyslogFacility AUTH
#LogLevel INFO

# Authentication:

LoginGraceTime 1m
PermitRootLogin yes
#StrictModes yes
MaxAuthTries 3
#MaxSessions 10

#RSAAuthentication yes
#PubkeyAuthentication yes

# The default is to check both .ssh/authorized_keys and .ssh/authorized_keys2
# but this is overridden so installations will only check .ssh/authorized_keys
AuthorizedKeysFile	.ssh/authorized_keys

#AuthorizedPrincipalsFile none

#AuthorizedKeysCommand none
#AuthorizedKeysCommandUser nobody

# For this to work you will also need host keys in ${dir_storage}/ssh_known_hosts
#RhostsRSAAuthentication no
# similar for protocol version 2
#HostbasedAuthentication no
# Change to yes if you don't trust ~/.ssh/known_hosts for
# RhostsRSAAuthentication and HostbasedAuthentication
IgnoreUserKnownHosts yes
# Don't read the user's ~/.rhosts and ~/.shosts files
#IgnoreRhosts yes

# To disable tunneled clear text passwords, change to no here!
#PasswordAuthentication yes
#PermitEmptyPasswords no

# Change to no to disable s/key passwords
ChallengeResponseAuthentication no

AllowAgentForwarding no
#AllowTcpForwarding yes
#GatewayPorts no
#X11Forwarding no
#X11DisplayOffset 10
#X11UseLocalhost yes
#PermitTTY yes
#PrintMotd yes
#PrintLastLog yes
#TCPKeepAlive yes
#UseLogin no
#PermitUserEnvironment no
#Compression delayed
#ClientAliveInterval 0
#ClientAliveCountMax 3
#UseDNS no
PidFile /var/run/sshd.pid
#MaxStartups 10:30:100
#PermitTunnel no
#ChrootDirectory none
#VersionAddendum none

# no default banner path
#Banner none

# override default of no subsystems
Subsystem	sftp	/usr/libexec/sftp-server

EOF
	chmod 600 "$config_output"
}

# Existing policy is never replaced by permissive defaults after a parse error.
work_dir=""
max_config_bytes=2097152
max_log_bytes=65536

refuse()
{
	logger -t sshd "$*"
	printf 'sshd: %s\n' "$*" >&2
	return 1
}

file_size()
{
	local size
	[ -f "$1" ] || return 1
	size=$(stat -L -c %s "$1" 2>/dev/null) || return 1
	case "$size" in ''|*[!0-9]*) return 1;; esac
	[ "$size" -le "$max_config_bytes" ] || return 1
	printf '%s\n' "$size"
}

file_hash()
{
	file_size "$1" >/dev/null || return 1
	hash_line=$(md5sum "$1") || return 1
	printf '%s\n' "${hash_line%% *}"
}

bounded_copy()
{
	# Target ash uses512-byte file-size blocks; post-check also covers hosts.
	(ulimit -f 4096 && cat "$1" > "$2") || return 1
	file_size "$2" >/dev/null
}

validate_config()
{
	local status size
	#64blocks is32KiB on target ash, at most64KiB on supported host shells.
	(ulimit -f 64 && /usr/sbin/sshd -t -f "$1") > "$work_dir/validation.log" 2>&1
	status=$?
	size=$(stat -c %s "$work_dir/validation.log" 2>/dev/null) || return 1
	case "$size" in ''|*[!0-9]*) return 1;; esac
	[ "$size" -le "$max_log_bytes" ] && [ "$status" = 0 ]
}

reserve_workspace()
{
	local available needed suffix candidate
	# Firmware upload bytes already in/tmp are counted by df. Budget includes
	# original+candidate+generated main, a bounded log and metadata headroom.
	needed=$(($1 + max_config_bytes + $2 + max_log_bytes + 262144))
	available=$(df -Pk /tmp 2>/dev/null | awk 'NR == 2 {print $4}')
	case "$available" in ''|*[!0-9]*) return 1;; esac
	[ "$available" -ge $(((needed + 1023) / 1024)) ] || return 1
	# CONFIG_MKTEMP is disabled. Never reuse/delete someone else's reservation.
	for suffix in 0 1 2 3 4 5 6 7 8 9; do
		candidate="/tmp/.sshd-startup.$$.$suffix"
		if mkdir -m 700 "$candidate" 2>/dev/null; then
			work_dir=$candidate
			return 0
		fi
	done
	return 1
}

# Invoked by the EXIT trap after a workspace is successfully reserved.
# shellcheck disable=SC2329
cleanup()
{
	[ -z "$work_dir" ] || rm -rf "$work_dir"
}

publish_config()
{
	local status
	# The helper owns the Storage lock and the same-filesystem transaction.
	migration_backup=$(/sbin/storage_validate --publish-config "$1" "$2" "$sshd_config")
	status=$?
	case "$status" in
	0) return 0;;
	2) logger -t sshd "validated config published with cleanup/durability warning"; return 0;;
	*) refuse "validated config publication failed; inspect active config and preserved policy"; return 1;;
	esac
}

func_install_default()
{
	# First boot is the only default-generation exception.
	if [ -e "$sshd_config" ] || [ -L "$sshd_config" ]; then
		refuse "existing config blocks first-boot defaults; original preserved"
		return 1
	fi
	if ! (ulimit -f 4096 && func_create_config "$work_dir/default") ||
	   ! file_size "$work_dir/default" >/dev/null || ! validate_config "$work_dir/default"; then
		refuse "first-boot default config validation failed; service startup refused"
		[ ! -f "$work_dir/validation.log" ] || cat "$work_dir/validation.log" >&2
		return 1
	fi
	if [ -e "$sshd_config" ] || [ -L "$sshd_config" ]; then
		refuse "config appeared during first-boot validation; original preserved"
		return 1
	fi
	if ! publish_config "$work_dir/default" -; then
		refuse "cannot install validated first-boot config"
		return 1
	fi
	logger -t sshd "first boot: installed validated default sshd_config"
	return 0
}

func_migrate_config()
{
	bounded_copy "$sshd_config" "$work_dir/original" || { refuse "cannot snapshot bounded stored config; original preserved"; return 1; }
	bounded_copy "$work_dir/original" "$work_dir/candidate" || return 1
	# Only remove exact, obsolete default DSA HostKey paths after a successful
	# algorithm query; all authentication, Match and forwarding policy remains.
	if awk -v key="$dir_storage/ssh_host_dsa_key" -v oldkey="$old_path/ssh_host_dsa_key" \
		'$1 == "HostKey" && ($2 == key || $2 == oldkey) && (NF == 2 || $3 ~ /^#/) { found=1 } END { exit !found }' \
		"$work_dir/original"; then
		if ! (ulimit -f 64 && /usr/bin/ssh -Q key) > "$work_dir/keytypes" 2>/dev/null; then
			refuse "cannot query SSH key algorithms; original preserved"
			return 1
		fi
		if ! grep -q '^ssh-dss$' "$work_dir/keytypes"; then
			if ! (ulimit -f 4096 && awk -v key="$dir_storage/ssh_host_dsa_key" -v oldkey="$old_path/ssh_host_dsa_key" \
				'$1 == "HostKey" && ($2 == key || $2 == oldkey) && (NF == 2 || $3 ~ /^#/) { next } { print }' \
				"$work_dir/original" > "$work_dir/candidate"); then
				refuse "cannot prepare DSA migration; original preserved"
				return 1
			fi
		fi
	fi
	file_size "$work_dir/candidate" >/dev/null || { refuse "migrated config exceeds2MiB; original preserved"; return 1; }
	if ! validate_config "$work_dir/candidate"; then
		refuse "invalid stored config or bounded validation failed; original preserved; automatic defaults disabled"
		cat "$work_dir/validation.log" >&2
		return 1
	fi
	original_hash=$(file_hash "$work_dir/original") || return 1
	candidate_hash=$(file_hash "$work_dir/candidate") || return 1
	current_hash=$(file_hash "$sshd_config") || return 1
	[ "$current_hash" = "$original_hash" ] || { refuse "stored config changed during validation; original preserved"; return 1; }
	if [ "$original_hash" = "$candidate_hash" ]; then
		return 0
	fi
	[ ! -L "$sshd_config" ] || { refuse "linked stored config needs manual migration; original preserved"; return 1; }
	if ! publish_config "$work_dir/candidate" "$work_dir/original"; then
		refuse "cannot publish validated DSA migration; original preserved"
		return 1
	fi
	logger -t sshd "validated legacy migration; pre-migration config kept: $migration_backup"
	return 0
}

func_start()
{
	umask 077
	if [ ! -d "$dir_storage" ]; then
		mkdir -p "$dir_storage" && chmod 755 "$dir_storage" || return 1
	fi
	old_path="/etc/storage"
	if [ -f "${old_path}/sshd_config" ] && [ ! -e "$sshd_config" ] && [ ! -L "$sshd_config" ]; then
		mv -n "${old_path}/sshd_config" "$sshd_config" || return 1
	fi
	for i in ssh_host_rsa_key ssh_host_dsa_key ; do
		[ ! -f "${old_path}/${i}" ] || mv -n "${old_path}/${i}" "$dir_storage" || return 1
		[ ! -f "${old_path}/${i}.pub" ] || mv -n "${old_path}/${i}.pub" "$dir_storage" || return 1
	done
	original_size=0
	if [ -e "$sshd_config" ] || [ -L "$sshd_config" ]; then
		original_size=$(file_size "$sshd_config") || { refuse "stored config is not regular or exceeds2MiB; original preserved"; return 1; }
	fi
	reserve_workspace "$original_size" 0 || { refuse "insufficient temporary space or no private workspace; original preserved"; return 1; }
	trap cleanup EXIT
	trap 'exit 1' HUP INT TERM
	if [ ! -f "$rsa_key" ] || [ ! -f "$ed25519_key" ]; then
		/usr/bin/ssh-keygen -A || return 1
	fi
	if [ ! -e "$sshd_config" ] && [ ! -L "$sshd_config" ]; then
		func_install_default || return 1
	fi
	[ -f "$sshd_config" ] || { refuse "stored config is not a regular file; original preserved"; return 1; }
	func_migrate_config || return 1
	# Re-check the installed path before execution, including relative includes.
	if ! validate_config "$sshd_config"; then
		refuse "installed config validation failed; service startup refused"
		cat "$work_dir/validation.log" >&2
		return 1
	fi
	installed_hash=$(file_hash "$sshd_config") || return 1
	[ "$installed_hash" = "$candidate_hash" ] || { refuse "stored config changed during final validation; service startup refused"; return 1; }
	# All private staging is gone before a long-lived daemon is launched.
	cleanup || { refuse "cannot remove private startup workspace; service startup refused"; return 1; }
	work_dir=""
	touch /var/run/utmp
	if [ -n "$1" ]; then
		/usr/sbin/sshd -o PasswordAuthentication=no
	else
		/usr/sbin/sshd
	fi
}

func_stop()
{
	killall -q sshd
}

func_reload()
{
	kill -SIGHUP "$(cat /var/run/sshd.pid)"
}

case "$1" in
start)
	func_start "${2:-}"
	exit $?
	;;
stop)
	func_stop
	;;
reload)
	func_reload
	;;
*)
	echo "Usage: $0 {start|stop|reload}"
	exit 1
	;;
esac

exit 0
