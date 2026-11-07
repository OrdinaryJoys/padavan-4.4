static void change_led_mode(u32 led_mode)
{
	if (led_mode != SWAPI_LED_OFF)
		led_mode = SWAPI_LED_LINK_ACT;

	if (g_led_phy_mode != led_mode) {
		g_led_phy_mode = led_mode;
		esw_led_mode(led_mode);
	}
}
