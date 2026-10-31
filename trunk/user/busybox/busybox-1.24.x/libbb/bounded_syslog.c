/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "libbb.h"
#include "../../../shared/bounded_syslog.h"

static struct padavan_log_context bb_log_context = PADAVAN_LOG_CONTEXT_INIT;

void FAST_FUNC bb_openlog(const char *ident, int options, int facility)
{
    padavan_log_open(&bb_log_context, ident, options, facility);
}

void FAST_FUNC bb_closelog(void)
{
    padavan_log_close(&bb_log_context);
}

int FAST_FUNC bb_setlogmask(int mask)
{
    return padavan_log_mask(&bb_log_context, mask);
}

void FAST_FUNC bb_vsyslog(int priority, const char *format, va_list arguments)
{
    padavan_log_vwrite(&bb_log_context, priority, format, arguments);
}

void FAST_FUNC bb_syslog(int priority, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    bb_vsyslog(priority, format, arguments);
    va_end(arguments);
}
