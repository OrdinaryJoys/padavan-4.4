#!/bin/sh
# Validate compatible migrations without replacing invalid policy with defaults.
custom_config=/etc/storage/dnsmasq/dnsmasq.conf
main_config=/etc/dnsmasq.conf
work_dir=""

refuse()
{
	logger -t dnsmasq "$*"
	printf 'dnsmasq: %s\n' "$*" >&2
	return 1
}

file_hash()
{
	hash_line=$(md5sum "$1") || return 1
	printf '%s\n' "${hash_line%% *}"
}

reserve_migration_backup()
{
	for suffix in '' .1 .2 .3 .4 .5 .6 .7 .8 .9; do
		backup="$custom_config.before-migration$suffix"
		if (umask 077; set -C; : > "$backup") 2>/dev/null; then
			printf '%s\n' "$backup"
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

[ -f "$main_config" ] || { refuse "generated main config is missing; service startup refused"; exit 1; }
parent=${custom_config%/*}
[ -d "$parent" ] || { refuse "custom config directory is missing; service startup refused"; exit 1; }
work_dir="$parent/.startup.$$"
if ! mkdir -m 700 "$work_dir"; then
	work_dir=""
	refuse "cannot reserve migration workspace; original preserved"
	exit 1
fi
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
umask 077
existed=0
if [ -e "$custom_config" ] || [ -L "$custom_config" ]; then
	[ -f "$custom_config" ] || { refuse "custom config is not a regular file; original preserved"; exit 1; }
	cat "$custom_config" > "$work_dir/original" || { refuse "cannot snapshot custom config; original preserved"; exit 1; }
	existed=1
else
	: > "$work_dir/original" || exit 1
fi

filter_aaaa=$(nvram get dhcp_filter_aaa) || exit 1
case "$filter_aaaa" in 0|1) ;; *) refuse "invalid AAAA setting; original preserved; service startup refused"; exit 1;; esac
# Restrict edits to the legacy options controlled by this firmware's UI.
if ! sed -e '/^[[:space:]]*filter-aaaa[[:space:]]*\(#.*\)\{0,1\}$/d' \
	-e 's/^\([[:space:]]*\)gfwlist=/\1#gfwlist=/' \
	"$work_dir/original" > "$work_dir/custom"; then
	refuse "cannot prepare legacy migration; original preserved"
	exit 1
fi
if [ "$filter_aaaa" = 1 ]; then
	printf 'filter-aaaa\n' >> "$work_dir/custom" || exit 1
fi

# Validate the full generated config with only its custom include redirected.
if ! awk -v old="conf-file=$custom_config" -v new="conf-file=$work_dir/custom" \
	'{ if ($0 == old) { print new; found=1 } else print } END { if (!found) exit 1 }' \
	"$main_config" > "$work_dir/main"; then
	refuse "cannot locate generated custom include; original preserved; service startup refused"
	exit 1
fi
if ! /usr/sbin/dnsmasq --test -C "$work_dir/main" > "$work_dir/validation.log" 2>&1; then
	refuse "invalid custom config; original preserved; automatic defaults disabled"
	cat "$work_dir/validation.log" >&2
	exit 1
fi
original_hash=$(file_hash "$work_dir/original") || exit 1
candidate_hash=$(file_hash "$work_dir/custom") || exit 1
if [ "$existed" = 1 ]; then
	current_hash=$(file_hash "$custom_config") || exit 1
	[ "$current_hash" = "$original_hash" ] || { refuse "custom config changed during validation; original preserved"; exit 1; }
	if [ "$original_hash" = "$candidate_hash" ]; then
		exit 0
	fi
	[ ! -L "$custom_config" ] || { refuse "linked custom config needs manual migration; original preserved"; exit 1; }
	migration_backup=$(reserve_migration_backup) || { refuse "cannot reserve migration backup; original preserved"; exit 1; }
	if ! cat "$work_dir/original" > "$migration_backup"; then
		rm -f "$migration_backup"
		refuse "cannot preserve pre-migration config; original preserved"
		exit 1
	fi
else
	if [ -e "$custom_config" ] || [ -L "$custom_config" ]; then
		refuse "custom config appeared during validation; original preserved"
		exit 1
	fi
fi
# rename(2) replaces the path itself, avoiding mv's into-directory behavior.
if ! /sbin/storage_validate --replace-file "$work_dir/custom" "$custom_config"; then
	refuse "cannot publish validated migration; original preserved"
	exit 1
fi
if [ "$existed" = 1 ]; then
	logger -t dnsmasq "validated legacy migration; pre-migration config kept: $migration_backup"
else
	logger -t dnsmasq "first boot: installed validated custom config"
fi

exit 0
