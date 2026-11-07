static int
flash_firmware(void)
{
	const char *script_name = SCRIPT_SHUTDOWN;
	char attempt[] = FW_UPGRADE_PRIVATE "/fwupgrade.XXXXXX";
	char writer[sizeof(attempt) + 16], record[sizeof(attempt) + 16];
	pid_t child;
	int status, result, i, resident = 0, lease = -1, marker_owned = 0;
	int attempt_created = 0;
	struct firmware_upgrade_service services[] = {
		{ "watchdog", firmware_upgrade_stop_watchdog, start_watchdog, 0 },
		{ "rstats", stop_rstats, start_rstats, 0 },
		{ "detect_internet", stop_detect_internet, firmware_upgrade_start_detect, 0 },
		{ "networkmap", stop_networkmap, firmware_upgrade_start_networkmap, 0 },
		{ "lld2d", stop_lltd, start_lltd, 0 },
		{ "infosvr", stop_infosvr, start_infosvr, 0 },
		{ "crond", stop_crond, start_crond, 0 }
	};
	int service_count = sizeof(services) / sizeof(services[0]);

	firmware_upgrade_pid1_active = 1;
	if (firmware_upgrade_inhibited()) {
		logmessage("firmware", "Previous upgrade state is unresolved; queued upgrade/reboot and watchdog rearm inhibited");
		return 1;
	}
	/* Arm the asynchronous PID1 guard before asking for exclusive admission.
	 * Existing supported management actions hold shared leases; abort without
	 * waiting or doing Storage/hook side effects if any are still in flight. */
	lease = upgrade_transaction_enter();
	if (lease < 0) {
		logmessage("firmware", "Upgrade admission is busy or unsafe; upgrade aborted before preparation");
		if (firmware_upgrade_inhibited())
			return 1;
		firmware_upgrade_pid1_active = 0;
		return 0;
	}
	if (firmware_upgrade_inhibit(1) != 0) {
		logmessage("firmware", "Cannot inhibit management actions safely; upgrade aborted before preparation");
		goto safe_cleanup;
	}
	marker_owned = 1;

	/* Fail while management services and the watchdog are still running.
	 * This is a validated save snapshot, not a lock on non-cooperating
	 * Storage writers (including rstats or a user hook's background work). */
	storage_save_time(60);
	status = write_storage_to_mtd();
	if (status != 0) {
		logmessage("firmware", "Storage save failed before upgrade (status %d); upgrade aborted", status);
		goto safe_cleanup;
	}

	/* Run the user hook while core services are still available, so its
	 * failure cannot strand them stopped. Hooks must return 0 on success. */
	if (check_if_file_exist(script_name)) {
		status = shutdown_hook_run(script_name, 0, HOOK_RUNNER_TIMEOUT_MS, HOOK_RUNNER_TERM_MS, HOOK_RUNNER_KILL_MS);
		if (status != 0) {
			logmessage("firmware", "Shutdown hook failed (status %d, runner error %d); upgrade aborted", status, errno);
			goto safe_cleanup;
		}
		/* Preserve completed hook edits before stopping services. On failure
		 * the hook's own side effects cannot be undone, but do not stop any
		 * more services or attempt a firmware write. */
		status = write_storage_to_mtd();
		if (status != 0) {
			logmessage("firmware", "Storage save after shutdown hook failed (status %d); upgrade aborted", status);
			goto safe_cleanup;
		}
	}

	if (!mkdtemp(attempt)) {
		logmessage("firmware", "Cannot create private upgrade attempt; upgrade aborted");
		goto safe_cleanup;
	}
	attempt_created = 1;
	snprintf(writer, sizeof(writer), "%s/writer", attempt);
	snprintf(record, sizeof(record), "%s/status", attempt);
	if (firmware_upgrade_stage_writer(writer) != 0) {
		logmessage("firmware", "Cannot stage trusted upgrade writer; upgrade aborted");
		goto safe_cleanup;
	}
	for (i = 0; i < service_count; i++)
		services[i].running = !!pids(services[i].name);
	if (!services[0].running) {
		logmessage("firmware", "No running watchdog for checked upgrade handoff; upgrade aborted before quiesce");
		goto safe_cleanup;
	}
	/* Request locked mappings before replacing the backing rootfs. This is
	 * a checked syscall guard: Linux 4.4 can ignore some population errors,
	 * so neither complete residency under pressure nor the survival of
	 * other management processes is established by a successful return. */
	if (mlockall(MCL_CURRENT | MCL_FUTURE) != 0) {
		logmessage("firmware", "Cannot request resident upgrade control memory (%s); upgrade aborted before quiesce", strerror(errno));
		goto safe_cleanup;
	}
	resident = 1;
	/* Best-effort global writeback can wait on unrelated filesystems. Keep
	 * services and the watchdog running throughout that prewrite wait. The
	 * RAM writer separately checks its MTD flush, close and full readback. */
	sync();
	if (firmware_upgrade_services(services, service_count, 0) != 0) {
		logmessage("firmware", "Upgrade quiesce failed before writer; recovering stopped services");
		goto safe_recover;
	}
	if (firmware_upgrade_disable_watchdog() != 0) {
		logmessage("firmware", "Hardware watchdog disable was not confirmed; no firmware write, recovering services");
		goto safe_recover;
	}
	status = firmware_upgrade_run(writer, record, lease, &child);
	if (status == FW_UPGRADE_NOT_STARTED) {
		logmessage("firmware", "Upgrade worker could not start; no firmware write, recovering services");
		goto safe_recover;
	}
	/* The static RAM worker owns readback, VERIFIED publication and reset.
	 * A possible write must never require PID1 to format logs, inspect ROMfs
	 * or request a second reset. Only normal exit20 may consult the private
	 * PREWRITE record and enter the safe recovery branch. */
	if (status < 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 20)
		return 1;
	result = firmware_upgrade_result(record, status, child);
	if (result == 1) {
		logmessage("firmware", "Writer rejected upgrade before erase/write; recovering stopped services");
		goto safe_recover;
	}
	/* Intentionally retain the exclusive fd, marker, memory latch and locks.
	 * An untrusted exit20 record is also UNKNOWN. The worker, rather than this
	 * parent, requests the only post-write reset from its RAM-resident image. */
	return 1;

safe_recover:
	if (firmware_upgrade_inhibit(0) != 0) {
		logmessage("firmware", "CRITICAL: cannot clear upgrade inhibit after safe abort; manual recovery required");
		return 1;
	}
	marker_owned = 0;
	if (firmware_upgrade_services(services, service_count, 1) != 0)
		logmessage("firmware", "CRITICAL: upgrade aborted without firmware write; some previous services failed to recover");
safe_cleanup:
	if (marker_owned && firmware_upgrade_inhibit(0) != 0) {
		logmessage("firmware", "CRITICAL: cannot clear preparation inhibit after safe abort; manual recovery required");
		return 1;
	}
	if (attempt_created) {
		unlink(record);
		unlink(writer);
		rmdir(attempt);
	}
	if (resident && munlockall() != 0)
		logmessage("firmware", "CRITICAL: safe upgrade abort could not release resident memory locks");
	if (firmware_upgrade_inhibited())
		return 1;
	upgrade_action_leave(lease);
	firmware_upgrade_pid1_active = 0;
	return 0;
}
