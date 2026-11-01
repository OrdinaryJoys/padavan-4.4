static int
apply_cgi(const char *url, webs_t wp)
{
	char *value;
	char *current_url;
	char *next_url;
	char *script;

	value = websGetVar(wp, "action_mode","");
	current_url = websGetVar(wp, "current_page", "");
	next_url = websGetVar(wp, "next_page", "");
	script = websGetVar(wp, "action_script","");

	snprintf(next_host, sizeof(next_host), "%s", websGetVar(wp, "next_host", ""));

	if (!strcmp(value, " SystemCmd "))
	{
		size_t cmd_len;
		char *cmd_str = websGetVar(wp, "SystemCmd", "");
		
		cmd_len = MIN(sizeof(SystemCmd)-1, strlen(cmd_str));
		strncpy(SystemCmd, cmd_str, cmd_len);
		SystemCmd[cmd_len] = '\0';
		websRedirect(wp, current_url);
		return 0;
	}
	else if (!strcmp(value, " ClearLog "))
	{
		// current only syslog implement this button
		unlink("/tmp/syslog.log");
		websRedirect(wp, current_url);
		return 0;
	}
	else if (!strcmp(value, " Reboot "))
	{
		sys_reboot();
		return 0;
	}
	else if (!strcmp(value, " FreeMemory "))
	{
		doSystem("sync");
		doSystem("echo 3 > /proc/sys/vm/drop_caches");
		return 0;
	}
	else if (!strcmp(value, " RestoreNVRAM "))
	{
		websApply(wp, "Restarting.asp");
		nvram_set_int("restore_defaults", 1);
		nvram_commit();
		sys_reboot();
		return 0;
	}
	else if (!strcmp(value, " RestoreStorage "))
	{
		doSystem("/sbin/mtd_storage.sh %s", "reset");
		return 0;
	}
	else if (!strcmp(value, " CommitFlash "))
	{
		int commit_all = 0, sys_result = 0;
		char *action_id = websGetVar(wp, "nvram_action", "");
		if (strcmp(action_id, "commit_all") == 0)
			commit_all = 1;
		if (commit_all || strcmp(action_id, "commit_nvram") == 0)
			sys_result |= nvram_commit();
		if (commit_all || strcmp(action_id, "commit_storage") == 0)
			sys_result |= doSystem("/sbin/mtd_storage.sh %s", "save");
		websWrite(wp, "{\"sys_result\": %d}", sys_result);
		return 0;
	}
	else if (!strcmp(value, " ExportConfOVPNC "))
	{
		int sys_result = 1;
#if defined(APP_OPENVPN)
		char *common_name = websGetVar(wp, "common_name", "");
		char *rsa_bits = websGetVar(wp, "rsa_bits", "1024");
		int days_valid = atoi(websGetVar(wp, "days_valid", "365"));
		if (strlen(common_name) < 1)
			common_name = "client@ovpn";
		if (get_login_safe())
			sys_result = doSystem("/sbin/ovpn_export_client '%s' %s %d", common_name, rsa_bits, days_valid);
#endif
		websWrite(wp, "{\"sys_result\": %d}", sys_result);
		return 0;
	}
	else if (!strcmp(value, " CreateCertOVPNS "))
	{
		int sys_result = 1;
#if defined(APP_OPENVPN)
		char *common_name = websGetVar(wp, "common_name", "");
		char *rsa_bits = websGetVar(wp, "rsa_bits", "1024");
		int days_valid = atoi(websGetVar(wp, "days_valid", "365"));
		if (strlen(common_name) < 1)
			common_name = "OpenVPN Server";
		if (get_login_safe())
			sys_result = doSystem("/usr/bin/openvpn-cert.sh %s -n '%s' -b %s -d %d", "server", common_name, rsa_bits, days_valid);
#endif
		websWrite(wp, "{\"sys_result\": %d}", sys_result);
		return 0;
	}
	else if (!strcmp(value, " CreateCertHTTPS "))
	{
		int sys_result = 1;
#if defined(SUPPORT_HTTPS)
		char *common_name = websGetVar(wp, "common_name", "");
		char *rsa_bits = websGetVar(wp, "rsa_bits", "1024");
		int days_valid = atoi(websGetVar(wp, "days_valid", "365"));
		if (strlen(common_name) < 1)
			common_name = nvram_safe_get("lan_ipaddr_t");
		if (get_login_safe())
			sys_result = doSystem("/usr/bin/https-cert.sh -n '%s' -b %s -d %d", common_name, rsa_bits, days_valid);
#endif
		websWrite(wp, "{\"sys_result\": %d}", sys_result);
		return 0;
	}
	else
	{
		char *sid_list, *serviceId;
		int sid;
		
		sid_list = websGetVar(wp, "sid_list", "");
		while ((serviceId = svc_pop_list(sid_list, ';')) != NULL) {
			sid = 0;
			while (GetServiceId(sid) != NULL) {
				if (!strcmp(GetServiceId(sid), serviceId))
					break;
				++sid;
			}
			
			if (!strcmp(value, "  Save  ") || !strcmp(value, " Apply "))
				validate_cgi(wp, sid);
			else if (!strcmp(value, "Set") || !strcmp(value, "Unset") || !strcmp(value, "Update"))
				validate_cgi(wp, sid);
			else {
				char *value1 = websGetVar(wp, "action_mode", NULL);
				if (value1 != NULL) {
					char groupId[64];
					snprintf(groupId, sizeof(groupId), websGetVar(wp, "group_id", ""));
					
					if (!strncmp(value1, " Delete ", 8))
						apply_cgi_group(wp, sid, NULL, groupId, GROUP_FLAG_DELETE);
					else if (!strncmp(value1, " Add ", 5))
						apply_cgi_group(wp, sid, NULL, groupId, GROUP_FLAG_ADD);
					else if (!strncmp(value1, " Del ", 5))
						apply_cgi_group(wp, sid, NULL, groupId, GROUP_FLAG_REMOVE);
					else if (!strncmp(value1, " Refresh ", 9))
						apply_cgi_group(wp, sid, NULL, groupId, GROUP_FLAG_REFRESH);
					
					validate_cgi(wp, sid);
				}
			}
			
			sid_list = sid_list+strlen(serviceId)+1;
		}
		
		/* Add for EMI Test page */
		if (strlen(script) > 0)
			sys_script(script);
		
		if (!strcmp(value, "  Save  ") || !strcmp(value, " Apply "))
			websRedirect(wp, next_url);
		else
			websRedirect(wp, current_url);
		
		return 0;
	}

	return 1;
}
