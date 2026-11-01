static void
catch_sig_fatal(int sig)
{
	sig_term_received = 1;

	printf("%s signal: %s\n", "fatal", strsignal(sig));

	if (sig == SIGQUIT) {
		shutdown_router(1);
		return;
	}

	reset_signals();

	shutdown_router(0);

	kill(-1, SIGTERM);
	sleep(1);
	sync();

#ifdef MTD_FLASH_32M_REBOOT_BUG
	system("/bin/mtd_write -r unlock mtd1");
#else
	reboot(RB_AUTOBOOT);
#endif

	do {
		sleep(1);
	} while (1);
}
