void
btn_reset_action(void)
{
	int upgrade_fd __attribute__((cleanup(upgrade_gpio_action_release))) = upgrade_action_enter();
	if (upgrade_fd < 0)
		return;
	erase_nvram();
	erase_storage();
	sys_exit();
}
