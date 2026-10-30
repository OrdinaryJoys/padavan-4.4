#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <arpa/inet.h>
#include "httpd.h"

static int
parse_authority(const char *text, size_t length, int default_port, char host[256], int *port)
{
	size_t end = 0, offset, i;
	unsigned int number = 0;
	if (!length || length >= 256)
		return 0;
	if (text[0] == '[') {
		while (end < length && text[end] != ']') end++;
		if (end == length || end < 2)
			return 0;
		memcpy(host, text + 1, end - 1);
		host[end - 1] = 0;
		{
			struct in6_addr address;
			if (inet_pton(AF_INET6, host, &address) != 1)
				return 0;
		}
		offset = end + 1;
	} else {
		while (end < length && text[end] != ':') end++;
		if (!end)
			return 0;
		for (i = 0; i < end; i++) {
			unsigned char ch = text[i];
			if (!(ch < 128 && (isalnum(ch) || ch == '-' || ch == '.' || ch == '_')))
				return 0;
		}
		memcpy(host, text, end);
		host[end] = 0;
		offset = end;
	}
	*port = default_port;
	if (offset == length)
		return 1;
	if (text[offset++] != ':' || offset == length)
		return 0;
	for (; offset < length; offset++) {
		if (text[offset] < '0' || text[offset] > '9')
			return 0;
		if (number > (65535U - (text[offset] - '0')) / 10)
			return 0;
		number = number * 10 + text[offset] - '0';
		if (number > 65535)
			return 0;
	}
	if (!number)
		return 0;
	*port = number;
	return 1;
}

int
http_same_origin(const char *source, const char *authority, int secure, int referer)
{
	char source_host[256], request_host[256];
	const char *start, *end;
	struct in6_addr left, right;
	int source_port, request_port, source_secure;
	if (!source || !authority)
		return 0;
	if (strncasecmp(source, "https://", 8) == 0) {
		start = source + 8;
		source_secure = 1;
	} else if (strncasecmp(source, "http://", 7) == 0) {
		start = source + 7;
		source_secure = 0;
	} else
		return 0;
	if (source_secure != secure)
		return 0;
	end = start + strcspn(start, "/?#");
	if (!referer && *end)
		return 0;
	if (!parse_authority(start, end - start, secure ? 443 : 80, source_host, &source_port) ||
	    !parse_authority(authority, strlen(authority), secure ? 443 : 80, request_host, &request_port) ||
	    source_port != request_port)
		return 0;
	if (inet_pton(AF_INET6, source_host, &left) == 1 && inet_pton(AF_INET6, request_host, &right) == 1)
		return memcmp(&left, &right, sizeof(left)) == 0;
	return strcasecmp(source_host, request_host) == 0;
}

int
http_csrf_allowed(const char *host, const char *origin, const char *referer,
                  const char *fetch_site, int explicit_request, int secure, int is_get)
{
	if (fetch_site && strcmp(fetch_site, "cross-site") == 0)
		return 0;
	if (origin)
		return http_same_origin(origin, host, secure, 0);
	if (referer)
		return http_same_origin(referer, host, secure, 1);
	if (fetch_site)
		return strcmp(fetch_site, "same-origin") == 0 || (is_get && strcmp(fetch_site, "none") == 0);
	/* This non-simple header is unavailable to a cross-origin browser form.
	 * Headerless command-line requests must opt in explicitly. */
	return explicit_request;
}

static int
readonly_output(const char *name, size_t length)
{
	/* Dispatch names alone do not imply a getter: nvram_dump, bandwidth and
	 * detect_internet can execute scripts, change NVRAM or signal services. */
	static const char *names[] = {
		"uptime", "netdev", "nvram", "firmware_caps_hook",
		"json_system_status", "login_state_hook", "wanlink", "lanlink", "nf_values",
		"get_parameter", "get_nvram_list", "get_flash_time", "get_static_client",
		"get_static_ccount", "get_vpns_client", "wl_auth_list", "wl_bssid_5g", "wl_bssid_2g",
		"nvram_get_x", "nvram_get_list_x", "nvram_get_buf_x", "nvram_get_table_x",
		"nvram_match_x", "nvram_double_match_x", "nvram_match_both_x", "nvram_match_list_x",
		"shown_language_option", "hardware_pins", "dump_syslog", "dump_eth_mib", NULL
	};
	int i;
	for (i = 0; names[i]; i++)
		if (strlen(names[i]) == length && memcmp(name, names[i], length) == 0)
			return 1;
	return 0;
}

int
http_request_changes_state(int post, int head, const char *file, const char *query)
{
	static const char *actions[] = {
		"apply.cgi", "applydb.cgi", "upgrade.cgi", "restore_nv.cgi", "restore_st.cgi",
		"start_apply.htm", "Logout.asp", "logout", "reboot", NULL
	};
	const char *p, *end, *output = NULL;
	size_t output_length = 0;
	int i;
	if (head)
		return 0;
	if (post)
		return 1;
	for (i = 0; actions[i]; i++)
		if (strncmp(file, actions[i], strlen(actions[i])) == 0)
			return 1;
	if (!query || !*query)
		return 0;
	if (strncmp(file, "update.cgi", 10) != 0 || strpbrk(query, "%+"))
		return 1;
	/* Unknown/encoded RPC calls require origin proof; known read-only polling
	 * endpoints remain usable without a CSRF header. */
	for (p = query; *p; p = *end ? end + 1 : end) {
		end = p + strcspn(p, "&;");
		if (end - p >= 7 && memcmp(p, "output=", 7) == 0) {
			if (output)
				return 1;
			output = p + 7;
			output_length = end - output;
		} else if (!(end - p >= 2 && p[0] == '_' && p[1] == '=')) {
			const char *arg = p;
			if (end - p < 5 || memcmp(arg, "arg", 3) != 0)
				return 1;
			arg += 3;
			if (*arg < '0' || *arg > '9')
				return 1;
			while (arg < end && *arg >= '0' && *arg <= '9') arg++;
			if (arg == end || *arg != '=')
				return 1;
		}
	}
	return !output || !readonly_output(output, output_length);
}
