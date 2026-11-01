/* Public actual function from d67fee5f9fa8957c70d0f869c842a95ce09ce139
 * trunk/user/rc/rc.c; body SHA256 7b98552bbeb4b7dda0176c7194da0697060bcd58d7da2b858971c2f09b8b9742
 * Inert test fixture only; never execute as firmware. */
void 
handle_notifications(void)
{
	int i, stop_handle = 0, queue_fd;
	char notify_name[300];
	DIR *directory;
	/* Do not execute queued reboots/retries or restart services from a rootfs
	 * which a failed writer may already have replaced. Keep markers for
	 * diagnosis; existing WAN, DNS and management processes were preserved. */
	if (firmware_upgrade_inhibited())
		return;

	queue_fd = rc_notification_open_dir(DIR_RC_NOTIFY);
	if (queue_fd < 0)
		return;
	directory = fdopendir(queue_fd);
	if (!directory) {
		close(queue_fd);
		return;
	}

	// handle max 10 requests at once (prevent deadlock)
	for (i=0; i < 10;)
	{
		struct dirent *entry;
		FILE *test_fp;
		
		entry = readdir(directory);
		if (!entry)
			break;
		if (strcmp(entry->d_name, ".") == 0)
			continue;
		if (strcmp(entry->d_name, "..") == 0)
			continue;
		i++;
		if (!rc_notification_valid_marker(queue_fd, entry->d_name)) {
			unlinkat(queue_fd, entry->d_name, 0);
			continue;
		}
		
		/* Remove the marker file. */
		snprintf(notify_name, sizeof(notify_name), "%s/%s", DIR_RC_NOTIFY, entry->d_name);
		remove(notify_name);
		
		printf("rc notification: %s\n", entry->d_name);
		
		/* Take the appropriate action. */
		if (!strcmp(entry->d_name, RCN_RESTART_REBOOT))
		{
			stop_handle = 1;
			sys_exit();
		}
		else if (!strcmp(entry->d_name, "flash_firmware"))
		{
			/* A preflight abort leaves services running: continue draining
			 * coalesced notifications instead of leaving them stranded. */
			stop_handle = flash_firmware();
		}
#if defined (USE_IPV6)
		else if (!strcmp(entry->d_name, RCN_RESTART_IPV6))
		{
			if (!get_ap_mode()) {
				full_restart_ipv6(nvram_ipv6_type);
				nvram_ipv6_type = get_ipv6_type();
			}
		}
		else if (strcmp(entry->d_name, RCN_RESTART_RADV) == 0)
		{
			restart_dhcpd();
		}
#endif
		else if (!strcmp(entry->d_name, RCN_RESTART_WAN))
		{
			full_restart_wan();
		}
		else if (!strcmp(entry->d_name, RCN_RESTART_LAN))
		{
			full_restart_lan();
		}
		else if (!strcmp(entry->d_name, "stop_whole_wan"))
		{
			stop_wan();
		}
		else if (!strcmp(entry->d_name, RCN_RESTART_IPTV))
		{
			int is_ap_mode = get_ap_mode();
			restart_iptv(is_ap_mode);
			if (!is_ap_mode)
				restart_firewall();
		}
		else if(!strcmp(entry->d_name, "deferred_wan_connect"))
		{
			deferred_wan_connect();
		}
		else if(!strcmp(entry->d_name, "auto_wan_reconnect"))
		{
			auto_wan_reconnect();
		}
		else if(!strcmp(entry->d_name, "auto_wan_reconnect_pause"))
		{
			auto_wan_reconnect_pause();
		}
		else if(!strcmp(entry->d_name, "manual_wan_reconnect"))
		{
			manual_wan_reconnect();
		}
		else if(!strcmp(entry->d_name, "manual_wan_disconnect"))
		{
			manual_wan_disconnect();
		}
		else if(!strcmp(entry->d_name, "manual_wisp_reassoc"))
		{
			manual_wisp_reassoc();
		}
		else if(!strcmp(entry->d_name, "manual_ddns_hostname_check"))
		{
			manual_ddns_hostname_check();
		}
#if defined (USE_USB_SUPPORT)
		else if (!strcmp(entry->d_name, RCN_RESTART_MODEM))
		{
			int wan_stopped = 0;
			int modules_reloaded = 0;
			int need_restart_wan = get_usb_modem_wan(0);
			int modem_rule = nvram_get_int("modem_rule");
			int modem_type = nvram_get_int("modem_type");
			if (nvram_modem_rule != modem_rule)
			{
				nvram_modem_rule = modem_rule;
				if (need_restart_wan) {
					wan_stopped = 1;
					stop_wan();
				}
				if (modem_rule > 0) {
					modules_reloaded = 1;
					reload_modem_modules(modem_type, 1);
				} else {
					unload_modem_modules();
				}
			}
			if (nvram_modem_type != modem_type)
			{
				if (nvram_modem_type == 3 || modem_type == 3) {
					if (modem_rule > 0 && !modules_reloaded) {
						if (need_restart_wan && !wan_stopped)
							stop_wan();
						reload_modem_modules(modem_type, 1);
					}
				}
				nvram_modem_type = modem_type;
			}
			if (need_restart_wan)
				full_restart_wan();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_SPOOLER) == 0)
		{
			restart_usb_printer_spoolers();
		}
		else if (!strcmp(entry->d_name, "on_hotplug_usb_printer"))
		{
			// deferred run usb printer daemons
			nvram_set_int_temp("usb_hotplug_lp", 1);
			alarm(5);
		}
		else if (!strcmp(entry->d_name, "on_unplug_usb_printer"))
		{
			// deferred stop usb printer daemons
			nvram_set_int_temp("usb_unplug_lp", 1);
			alarm(5);
		}
		else if (!strcmp(entry->d_name, "on_hotplug_usb_modem"))
		{
			// deferred run usb modem to wan
			nvram_set_int_temp("usb_hotplug_md", 1);
			alarm(5);
		}
		else if (!strcmp(entry->d_name, "on_unplug_usb_modem"))
		{
			// deferred restart wan
			nvram_set_int_temp("usb_unplug_md", 1);
			alarm(5);
		}
#endif
#if defined (USE_STORAGE)
		else if (!strcmp(entry->d_name, "on_hotplug_mass_storage"))
		{
			// deferred run stor apps
			nvram_set_int_temp("usb_hotplug_ms", 1);
			alarm(5);
		}
		else if (!strcmp(entry->d_name, "on_unplug_mass_storage"))
		{
			umount_ejected();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_HDDTUNE) == 0)
		{
			system("/sbin/hddtune.sh");
			set_pagecache_reclaim();
		}
#if defined(APP_FTPD)
		else if (strcmp(entry->d_name, RCN_RESTART_FTPD) == 0)
		{
			restart_ftpd();
		}
#endif
#if defined(APP_SMBD)
		else if (strcmp(entry->d_name, RCN_RESTART_SMBD) == 0)
		{
			restart_smbd();
		}
#endif
#if defined(APP_NFSD)
		else if (strcmp(entry->d_name, RCN_RESTART_NFSD) == 0)
		{
			restart_nfsd();
		}
#endif
#if defined(APP_MINIDLNA)
		else if (strcmp(entry->d_name, "restart_dms_rescan") == 0)
		{
			restart_dms(1);
		}
		else if (strcmp(entry->d_name, RCN_RESTART_DMS) == 0)
		{
			restart_dms(0);
		}
#endif
#if defined(APP_FIREFLY)
		else if (strcmp(entry->d_name, RCN_RESTART_ITUNES) == 0)
		{
			restart_itunes();
		}
#endif
#if defined(APP_TRMD)
		else if (strcmp(entry->d_name, RCN_RESTART_TRMD) == 0)
		{
			restart_torrent();
		}
#endif
#if defined(APP_ARIA)
		else if (strcmp(entry->d_name, RCN_RESTART_ARIA) == 0)
		{
			restart_aria();
		}
#endif
#endif
		else if (strcmp(entry->d_name, RCN_RESTART_HTTPD) == 0)
		{
			restart_httpd();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_TELNETD) == 0)
		{
			stop_telnetd();
			start_telnetd();
		}
#if defined(APP_SSHD)
		else if (strcmp(entry->d_name, RCN_RESTART_SSHD) == 0)
		{
			restart_sshd();
		}
#endif
#if defined(APP_SCUT)
		else if (strcmp(entry->d_name, RCN_RESTART_SCUT) == 0)
		{
			restart_scutclient();
		}
		else if (strcmp(entry->d_name, "stop_scutclient") == 0)
		{
			stop_scutclient();
		}
#endif
#if defined(APP_MENTOHUST)
		else if (strcmp(entry->d_name, RCN_RESTART_MENTOHUST) == 0)
		{
			restart_mentohust();
		}
		else if (strcmp(entry->d_name, "stop_mentohust") == 0)
		{
			stop_mentohust();
		}
#endif
#if defined(APP_TTYD)
		else if (strcmp(entry->d_name, RCN_RESTART_TTYD) == 0)
		{
			restart_ttyd();
		}
#endif
#if defined(APP_SHADOWSOCKS)
		else if (strcmp(entry->d_name, RCN_SCHEDULE_DLINK) == 0)
		{
			/* Fork and return to the queue; do not make the watchdog or
			 * PID1 wait for remote subscription downloads. */
			start_scheduled_dlink();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_SHADOWSOCKS) == 0)
		{
			restart_ss();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_SS_TUNNEL) == 0)
		{
			restart_ss_tunnel();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_CHNROUTE_UPD) == 0)
		{
			update_chnroute();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_GFWLIST_UPD) == 0)
		{
			update_gfwlist();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_DLINK) == 0)
		{
			update_dlink();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_REDLINK) == 0)
		{
			reset_dlink();
		}
#endif
#if defined(APP_VLMCSD)
		else if (strcmp(entry->d_name, RCN_RESTART_VLMCSD) == 0)
		{
			restart_vlmcsd();
		}
#endif
#if defined(APP_ALIDDNS)
		else if (strcmp(entry->d_name, RCN_RESTART_ALIDDNS) == 0)
		{
			restart_aliddns();
		}
#endif
#if defined(APP_ZEROTIER)
		else if (strcmp(entry->d_name, RCN_RESTART_ZEROTIER) == 0)
		{
			restart_zerotier();
		}
#endif
#if defined(APP_DDNSTO)
		else if (strcmp(entry->d_name, RCN_RESTART_DDNSTO) == 0)
		{
			restart_ddnsto();
		}
#endif

#if defined(APP_ALDRIVER)
		else if (strcmp(entry->d_name, RCN_RESTART_ALDRIVER) == 0)
		{
			restart_aldriver();
		}
#endif
#if defined(APP_WIREGUARD)
		else if (strcmp(entry->d_name, RCN_RESTART_WIREGUARD) == 0)
		{
			restart_wireguard();
		}
#endif
#if defined(APP_SQM)
		else if (strcmp(entry->d_name, RCN_RESTART_SQM) == 0)
		{
			restart_sqm();
		}
#endif
#if defined(APP_ADBYBY)
		else if (strcmp(entry->d_name, RCN_RESTART_ADBYBY) == 0)
		{
			restart_adbyby();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_UPDATEADB) == 0)
		{
			update_adb();
		}
#endif
#if defined(APP_ADGUARDHOME)
		else if (strcmp(entry->d_name, RCN_RESTART_ADGUARDHOME) == 0)
		{
			restart_adguardhome();
		}
#endif
#if defined(APP_SMARTDNS)
		else if (strcmp(entry->d_name, RCN_RESTART_SMARTDNS) == 0)
		{
			restart_smartdns();
		}
#endif
#if defined(APP_FRP)
		else if (strcmp(entry->d_name, RCN_RESTART_FRP) == 0)
		{
			restart_frp();
		}
#endif
#if defined(APP_DNSFORWARDER)
		else if (strcmp(entry->d_name, RCN_RESTART_DNSFORWARDER) == 0)
		{
			restart_dnsforwarder();
		}
#endif
#if defined(APP_SMBD) || defined(APP_NMBD)
		else if (strcmp(entry->d_name, RCN_RESTART_NMBD) == 0)
		{
			restart_nmbd();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_WINS) == 0)
		{
			restart_nmbd();
			restart_dhcpd();
			reapply_vpn_server();
		}
#endif
		else if (strcmp(entry->d_name, RCN_RESTART_LLTD) == 0)
		{
			restart_lltd();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_ADSC) == 0)
		{
			restart_infosvr();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_CROND) == 0)
		{
			restart_crond();
		}
		else if (strcmp(entry->d_name, RCN_REAPPLY_VPNSVR) == 0)
		{
			reapply_vpn_server();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_VPNSVR) == 0)
		{
			restart_vpn_server();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_VPNCLI) == 0)
		{
			restart_vpn_client();
		}
		else if (strcmp(entry->d_name, "start_vpn_client") == 0)
		{
			start_vpn_client();
		}
		else if (strcmp(entry->d_name, "stop_vpn_client") == 0)
		{
			stop_vpn_client();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_DDNS) == 0)
		{
			stop_ddns();
			start_ddns(1);
		}
		else if (strcmp(entry->d_name, RCN_RESTART_DI) == 0)
		{
			if (get_ap_mode() || has_wan_ip4(0))
				notify_run_detect_internet(2);
		}
		else if (strcmp(entry->d_name, RCN_RECOVER_DNSMASQ) == 0)
		{
			if (!get_ap_mode() && !is_dns_dhcpd_run())
				start_dns_dhcpd(0);
		}
		else if (strcmp(entry->d_name, RCN_RESTART_DHCPD) == 0)
		{
			if (get_ap_mode())
				update_hosts_ap();
			restart_dhcpd();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_UPNP) == 0)
		{
			restart_upnp();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_SWITCH_CFG) == 0)
		{
			config_bridge(get_ap_mode());
			switch_config_base();
			switch_config_storm();
			switch_config_link();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_SWITCH_VLAN) == 0)
		{
			restart_switch_config_vlan();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_SYSLOG) == 0)
		{
			stop_logger();
			start_logger(0);
		}
		else if (strcmp(entry->d_name, RCN_RESTART_WDG) == 0)
		{
			restart_watchdog_cpu();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_TWEAKS) == 0)
		{
			notify_leds_detect_link();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_NETFILTER) == 0)
		{
			update_router_mode();
			reload_nat_modules();
			restart_firewall();
			flush_conntrack_table(NULL);
		}
		else if (strcmp(entry->d_name, RCN_RESTART_FIREWALL) == 0)
		{
			reload_nat_modules();
			restart_firewall();
		}
		else if (strcmp(entry->d_name, "restart_firewall_wan") == 0)
		{
			restart_firewall();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_NTPC) == 0)
		{
			notify_watchdog_time();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_TIME) == 0)
		{
			stop_logger();
			set_timezone();
			notify_watchdog_time();
			notify_rstats_time();
			start_logger(0);
			restart_crond();
		}
		else if (strcmp(entry->d_name, RCN_RESTART_SYSCTL) == 0)
		{
			restart_all_sysctl();
		}
		else if (!strcmp(entry->d_name, RCN_RESTART_WIFI5))
		{
			int radio_on = get_enabled_radio_wl();
			if (radio_on)
				radio_on = is_radio_allowed_wl();
			restart_wifi_wl(radio_on, 1);
		}
		else if (!strcmp(entry->d_name, RCN_RESTART_WIFI2))
		{
			int radio_on = get_enabled_radio_rt();
			if (radio_on)
				radio_on = is_radio_allowed_rt();
			restart_wifi_rt(radio_on, 1);
		}
		else if (!strcmp(entry->d_name, "control_wifi_guest_wl"))
		{
			int guest_on = is_guest_allowed_wl();
			control_guest_wl(guest_on, 1);
		}
		else if (!strcmp(entry->d_name, "control_wifi_guest_rt"))
		{
			int guest_on = is_guest_allowed_rt();
			control_guest_rt(guest_on, 1);
		}
		else if (!strcmp(entry->d_name, "control_wifi_guest_wl_on"))
		{
			control_guest_wl(1, 0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_guest_wl_off"))
		{
			control_guest_wl(0, 0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_guest_rt_on"))
		{
			control_guest_rt(1, 0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_guest_rt_off"))
		{
			control_guest_rt(0, 0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_radio_wl"))
		{
			int radio_on = get_enabled_radio_wl();
			if (radio_on)
				radio_on = is_radio_allowed_wl();
			control_radio_wl(radio_on, 1);
		}
		else if (!strcmp(entry->d_name, "control_wifi_radio_rt"))
		{
			int radio_on = get_enabled_radio_rt();
			if (radio_on)
				radio_on = is_radio_allowed_rt();
			control_radio_rt(radio_on, 1);
		}
		else if (!strcmp(entry->d_name, "control_wifi_radio_wl_on"))
		{
			control_radio_wl(1, 0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_radio_wl_off"))
		{
			control_radio_wl(0, 0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_radio_rt_on"))
		{
			control_radio_rt(1, 0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_radio_rt_off"))
		{
			control_radio_rt(0, 0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_config_wl"))
		{
			gen_ralink_config_5g(0);
		}
		else if (!strcmp(entry->d_name, "control_wifi_config_rt"))
		{
			gen_ralink_config_2g(0);
		}
		else
		{
			dbg("WARNING: rc notified of unrecognized event `%s'.\n", entry->d_name);
		}
		
		/*
		 * If there hasn't been another request for the same event made since
		 * we started, we can safely remove the ``action incomplete'' marker.
		 * Otherwise, we leave the marker because we'll go through here again
		 * for this even and mark it complete only after we've completed it
		 * without getting another request for the same event while handling
		 * it.
		 */
		test_fp = fopen(notify_name, "r");
		if (test_fp != NULL)
		{
			fclose(test_fp);
		}
		else
		{
			/* Remove the marker file. */
			snprintf(notify_name, sizeof(notify_name), "%s/%s", DIR_RC_INCOMPLETE, entry->d_name);
			remove(notify_name);
		}
		
		if (stop_handle)
			break;
	}

	closedir(directory);
	/* SIGUSR1 may coalesce; drain remaining batches on the next turn. */
	if (i == 10 && !stop_handle)
		kill(getpid(), SIGUSR1);
}
