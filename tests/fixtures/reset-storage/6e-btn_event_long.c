void
btn_event_long(int btn_id)
{
	int upgrade_fd __attribute__((cleanup(upgrade_gpio_action_release))) = upgrade_action_enter();
	if (upgrade_fd < 0)
		return;
	int ez_action = 0;
	int ez_param = 2;

	if (btn_id == BTN_FN1) {
		ez_action = nvram_get_int("fn1_action_long");
		ez_param = 4;
	} else if (btn_id == BTN_FN2) {
		ez_action = nvram_get_int("fn2_action_long");
		ez_param = 6;
	} else if (btn_id == BTN_WPS) {
		ez_action = nvram_get_int("ez_action_long");
	}

	if (LED_PWR & search_gpio_led())
	{
		if (ez_action == 7 || ez_action == 8)
			LED_CONTROL(LED_PWR, LED_OFF);
		else if (ez_action != 11)
			LED_CONTROL(LED_PWR, LED_ON);
	}

	switch (ez_action)
	{
	case 1: // WiFi 2.4GHz force Enable/Disable trigger
		ez_action_change_wifi2();
		break;
	case 2: // WiFi 5GHz force Enable/Disable trigger
		ez_action_change_wifi5();
		break;
	case 3: // WiFi 2.4 & 5GHz force Enable/Disable trigger
		ez_action_change_wifi2();
		ez_action_change_wifi5();
		break;
	case 4: // Safe removal all USB
		ez_action_usb_saferemoval(0);
		break;
	case 5: // WAN down
		ez_action_wan_down();
		break;
	case 6: // WAN reconnect
		ez_action_wan_reconnect();
		break;
	case 7: // Router reboot
		sys_exit();
		break;
	case 8: // Router shutdown
		ez_action_shutdown();
		break;
	case 9: // WAN up/down toggle
		ez_action_wan_toggle();
		break;
	case 10: // Run user script
		ez_action_user_script(ez_param);
		break;
	case 11: // Front LED toggle
		ez_action_led_toggle();
		break;
	case 12: // WiFi AP Guest 2.4GHz Enable/Disable trigger
		ez_action_change_guest_wifi2();
		break;
	case 13: // WiFi AP Guest 5GHz Enable/Disable trigger
		ez_action_change_guest_wifi5();
		break;
	case 14: // WiFi AP Guest 2.4 & 5GHz Enable/Disable trigger
		ez_action_change_guest_wifi2();
		ez_action_change_guest_wifi5();
		break;
	case 15: // Reset settings
		erase_nvram();
		erase_storage();
		sys_exit();
		break;
#if (BOARD_NUM_USB_PORTS > 1)
	case 21: // Safe removal USB #1
		ez_action_usb_saferemoval(1);
		break;
	case 22: // Safe removal USB #2
		ez_action_usb_saferemoval(2);
		break;
#endif
	}
}
