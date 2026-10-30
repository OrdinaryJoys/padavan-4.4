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
refuse()
{
	logger -t sshd "$*"
	printf 'sshd: %s\n' "$*" >&2
	return 1
}

# Invoked by the EXIT trap registered inside func_start.
# shellcheck disable=SC2329
cleanup()
{
	[ -z "$work_dir" ] || rm -rf "$work_dir"
}

file_hash()
{
	hash_line=$(md5sum "$1") || return 1
	printf '%s\n' "${hash_line%% *}"
}

reserve_migration_backup()
{
	for suffix in '' .1 .2 .3 .4 .5 .6 .7 .8 .9; do
		backup="$sshd_config.before-migration$suffix"
		if (umask 077; set -C; : > "$backup") 2>/dev/null; then
			printf '%s\n' "$backup"
			return 0
		fi
	done
	return 1
}

func_install_default()
{
	# First boot is the only default-generation exception.
	if [ -e "$sshd_config" ] || [ -L "$sshd_config" ]; then
		refuse "existing config blocks first-boot defaults; original preserved"
		return 1
	fi
	if ! func_create_config "$work_dir/default" ||
	   ! /usr/sbin/sshd -t -f "$work_dir/default" > "$work_dir/validation.log" 2>&1; then
		refuse "first-boot default config validation failed; service startup refused"
		[ ! -f "$work_dir/validation.log" ] || cat "$work_dir/validation.log" >&2
		return 1
	fi
	if [ -e "$sshd_config" ] || [ -L "$sshd_config" ]; then
		refuse "config appeared during first-boot validation; original preserved"
		return 1
	fi
	if ! /sbin/storage_validate --replace-file "$work_dir/default" "$sshd_config"; then
		refuse "cannot install validated first-boot config"
		return 1
	fi
	logger -t sshd "first boot: installed validated default sshd_config"
	return 0
}

func_migrate_config()
{
	cat "$sshd_config" > "$work_dir/original" || { refuse "cannot snapshot stored config; original preserved"; return 1; }
	cat "$work_dir/original" > "$work_dir/candidate" || return 1
	# Only remove exact, obsolete default DSA HostKey paths after a successful
	# algorithm query; all authentication, Match and forwarding policy remains.
	if awk -v key="$dir_storage/ssh_host_dsa_key" -v oldkey="$old_path/ssh_host_dsa_key" \
		'$1 == "HostKey" && ($2 == key || $2 == oldkey) && (NF == 2 || $3 ~ /^#/) { found=1 } END { exit !found }' \
		"$work_dir/original"; then
		if ! /usr/bin/ssh -Q key > "$work_dir/keytypes" 2>/dev/null; then
			refuse "cannot query SSH key algorithms; original preserved"
			return 1
		fi
		if ! grep -q '^ssh-dss$' "$work_dir/keytypes"; then
			if ! awk -v key="$dir_storage/ssh_host_dsa_key" -v oldkey="$old_path/ssh_host_dsa_key" \
				'$1 == "HostKey" && ($2 == key || $2 == oldkey) && (NF == 2 || $3 ~ /^#/) { next } { print }' \
				"$work_dir/original" > "$work_dir/candidate"; then
				refuse "cannot prepare DSA migration; original preserved"
				return 1
			fi
		fi
	fi
	if ! /usr/sbin/sshd -t -f "$work_dir/candidate" > "$work_dir/validation.log" 2>&1; then
		refuse "invalid stored config; original preserved; automatic defaults disabled"
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
	migration_backup=$(reserve_migration_backup) || { refuse "cannot reserve migration backup; original preserved"; return 1; }
	if ! cat "$work_dir/original" > "$migration_backup"; then
		rm -f "$migration_backup"
		refuse "cannot preserve pre-migration config; original preserved"
		return 1
	fi
	if ! /sbin/storage_validate --replace-file "$work_dir/candidate" "$sshd_config"; then
		refuse "cannot publish validated DSA migration; original preserved"
		return 1
	fi
	logger -t sshd "validated legacy migration; pre-migration config kept: $migration_backup"
	return 0
}

func_start()
{
	if [ ! -d "$dir_storage" ]; then
		mkdir -p "$dir_storage" && chmod 755 "$dir_storage" || return 1
	fi
	work_dir="$dir_storage/.startup.$$"
	if ! mkdir -m 700 "$work_dir"; then
		work_dir=""
		refuse "cannot reserve config workspace; original preserved"
		return 1
	fi
	trap cleanup EXIT
	trap 'exit 1' HUP INT TERM
	umask 077

	old_path="/etc/storage"
	if [ -f "${old_path}/sshd_config" ] && [ ! -e "$sshd_config" ] && [ ! -L "$sshd_config" ]; then
		mv -n "${old_path}/sshd_config" "$sshd_config" || return 1
	fi
	for i in ssh_host_rsa_key ssh_host_dsa_key ; do
		[ ! -f "${old_path}/${i}" ] || mv -n "${old_path}/${i}" "$dir_storage" || return 1
		[ ! -f "${old_path}/${i}.pub" ] || mv -n "${old_path}/${i}.pub" "$dir_storage" || return 1
	done
	if [ ! -f "$rsa_key" ] || [ ! -f "$ed25519_key" ]; then
		/usr/bin/ssh-keygen -A || return 1
	fi
	if [ ! -e "$sshd_config" ] && [ ! -L "$sshd_config" ]; then
		func_install_default || return 1
	fi
	[ -f "$sshd_config" ] || { refuse "stored config is not a regular file; original preserved"; return 1; }
	func_migrate_config || return 1
	# Re-check the installed path before execution, including relative includes.
	if ! /usr/sbin/sshd -t -f "$sshd_config" > "$work_dir/validation.log" 2>&1; then
		refuse "installed config validation failed; service startup refused"
		cat "$work_dir/validation.log" >&2
		return 1
	fi
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
