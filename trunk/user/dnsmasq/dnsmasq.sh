#!/bin/sh
# Validate compatible migrations without replacing invalid policy with defaults.
custom_config=/etc/storage/dnsmasq/dnsmasq.conf
main_config=/etc/dnsmasq.conf
work_dir=""
max_config_bytes=2097152
max_log_bytes=65536
validation_sequence=0
launch=0
case "$#" in
0) ;;
1) [ "$1" = --launch ] || exit 1; launch=1;;
*) exit 1;;
esac

refuse()
{
	logger -t dnsmasq "$*"
	printf 'dnsmasq: %s\n' "$*" >&2
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
	local status size status_file producer
	validation_sequence=$((validation_sequence + 1))
	status_file="$work_dir/validation-status.$validation_sequence"
	[ ! -e "$status_file" ] && [ ! -L "$status_file" ] || return 1
	# Capture may write a16MiB flat snapshot. Bound diagnostics separately;
	# pipeline success alone is never the producer's process exit status.
	(
		(ulimit -f 32768 && /usr/sbin/dnsmasq "$@")
		producer=$?
		(set -C; printf '%s\n' "$producer" > "$status_file")
	) 2>&1 | (ulimit -f 128 && head -c 65537 > "$work_dir/validation.log")
	status=$?
	[ "$status" = 0 ] || return 1
	[ -f "$status_file" ] && [ ! -L "$status_file" ] || return 1
	[ "$(stat -c %h "$status_file")" = 1 ] || return 1
	[ "$(stat -c %s "$status_file")" = 2 ] || return 1
	IFS= read -r producer < "$status_file" || return 1
	[ "$producer" = 0 ] || return 1
	size=$(stat -c %s "$work_dir/validation.log" 2>/dev/null) || return 1
	case "$size" in ''|*[!0-9]*) return 1;; esac
	[ "$size" -le "$max_log_bytes" ]
}

reserve_workspace()
{
	local available needed suffix candidate
	# Firmware upload bytes already in/tmp are counted by df. Budget includes
	# original+candidate+estimated main, a bounded log and metadata headroom.
	# Snapshot output uses its actual size and checks free space each4KiB;
	# do not reserve its16MiB upper bound and reject every uploaded firmware.
	needed=$(($1 + max_config_bytes + $2 + max_log_bytes + 262144))
	available=$(df -Pk /tmp 2>/dev/null | awk 'NR == 2 {print $4}')
	case "$available" in ''|*[!0-9]*) return 1;; esac
	[ "$available" -ge $(((needed + 1023) / 1024)) ] || return 1
	# CONFIG_MKTEMP is disabled. Never reuse/delete someone else's reservation.
	for suffix in 0 1 2 3 4 5 6 7 8 9; do
		candidate="/tmp/.dnsmasq-startup.$$.$suffix"
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
	migration_backup=$(/sbin/storage_validate --publish-config "$1" "$2" "$custom_config")
	status=$?
	case "$status" in
	0) return 0;;
	2) logger -t dnsmasq "validated config published with cleanup/durability warning"; return 0;;
	*) refuse "validated config publication failed; inspect active config and preserved policy"; return 1;;
	esac
}

umask 077
main_size=$(file_size "$main_config") || { refuse "generated main config is missing or exceeds2MiB; service startup refused"; exit 1; }
parent=${custom_config%/*}
[ -d "$parent" ] || { refuse "custom config directory is missing; service startup refused"; exit 1; }
existed=0
original_size=0
if [ -e "$custom_config" ] || [ -L "$custom_config" ]; then
	original_size=$(file_size "$custom_config") || { refuse "custom config is not regular or exceeds2MiB; original preserved"; exit 1; }
	existed=1
fi
reserve_workspace "$original_size" "$main_size" || { refuse "insufficient temporary space or no private workspace; original preserved"; exit 1; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
if [ "$existed" = 1 ]; then
	bounded_copy "$custom_config" "$work_dir/original" || { refuse "cannot snapshot bounded custom config; original preserved"; exit 1; }
else
	: > "$work_dir/original" || exit 1
fi

filter_aaaa=$(nvram get dhcp_filter_aaa) || exit 1
case "$filter_aaaa" in 0|1) ;; *) refuse "invalid AAAA setting; original preserved; service startup refused"; exit 1;; esac
# Restrict edits to the legacy options controlled by this firmware's UI.
if ! (ulimit -f 4096 && sed -e '/^[[:space:]]*filter-aaaa[[:space:]]*\(#.*\)\{0,1\}$/d' \
	-e 's/^\([[:space:]]*\)gfwlist=/\1#gfwlist=/' \
	"$work_dir/original" > "$work_dir/custom" &&
	{ [ "$filter_aaaa" != 1 ] || printf 'filter-aaaa\n' >> "$work_dir/custom"; }); then
	refuse "cannot prepare bounded legacy migration; original preserved"
	exit 1
fi
file_size "$work_dir/custom" >/dev/null || { refuse "migrated config exceeds2MiB; original preserved"; exit 1; }

# The parser overlays the candidate at its logical live path, expands every
# startup include/generator once in order, and binds the original source graph.
set -- --test -C "$main_config" --snapshot-capture "$work_dir/snapshot" \
	--snapshot-overlay "$custom_config" --snapshot-candidate "$work_dir/custom"
[ "$launch" = 0 ] || set -- "$@" --snapshot-managed
if ! validate_config "$@"; then
	refuse "invalid custom config or bounded validation failed; original preserved; automatic defaults disabled"
	cat "$work_dir/validation.log" >&2
	exit 1
fi
[ -f "$work_dir/snapshot/manifest" ] && [ ! -L "$work_dir/snapshot/manifest" ] || exit 1
snapshot_ticket=$(cat "$work_dir/snapshot/ticket") || exit 1
case "$snapshot_ticket" in ''|*[!0-9a-f]*) exit 1;; esac
case "$snapshot_ticket" in ????????????????????????????????) ;; *) exit 1;; esac
original_hash=$(file_hash "$work_dir/original") || exit 1
candidate_hash=$(file_hash "$work_dir/custom") || exit 1
if [ "$existed" = 1 ]; then
	current_hash=$(file_hash "$custom_config") || exit 1
	[ "$current_hash" = "$original_hash" ] || { refuse "custom config changed during validation; original preserved"; exit 1; }
	if [ "$original_hash" = "$candidate_hash" ]; then
		:
	else
		[ ! -L "$custom_config" ] || { refuse "linked custom config needs manual migration; original preserved"; exit 1; }
		publish_config "$work_dir/custom" "$work_dir/original" || exit 1
		logger -t dnsmasq "validated legacy migration; pre-migration config kept: $migration_backup"
	fi
else
	if [ -e "$custom_config" ] || [ -L "$custom_config" ]; then
		refuse "custom config appeared during validation; original preserved"
		exit 1
	fi
	publish_config "$work_dir/custom" - || exit 1
	logger -t dnsmasq "first boot: installed validated custom config"
fi
set -- --snapshot-seal "$work_dir/snapshot" --snapshot-ticket "$snapshot_ticket"
[ "$launch" = 0 ] || set -- "$@" --snapshot-managed
if ! validate_config "$@"; then
	refuse "installed policy retained but snapshot sealing failed; service startup refused"
	cat "$work_dir/validation.log" >&2
	exit 1
fi
set -- --test --snapshot-use "$work_dir/snapshot" --snapshot-ticket "$snapshot_ticket"
[ "$launch" = 0 ] || set -- "$@" --snapshot-managed
if ! validate_config "$@"; then
	refuse "installed policy retained but sealed snapshot validation failed; service startup refused"
	cat "$work_dir/validation.log" >&2
	exit 1
fi
installed_hash=$(file_hash "$custom_config") || exit 1
[ "$installed_hash" = "$candidate_hash" ] || { refuse "installed config changed after publication; service startup refused"; exit 1; }
if [ "$launch" = 1 ]; then
	# The daemon's invoking parent returns only after its startup handshake.
	# Startup parsing is complete before then; runtime hosts/leases/servers
	# stay live and service readiness is not established by this return alone.
	/usr/sbin/dnsmasq --snapshot-use "$work_dir/snapshot" --snapshot-ticket "$snapshot_ticket" --snapshot-managed ||
		{ refuse "sealed snapshot service startup failed"; exit 1; }
fi
exit 0
