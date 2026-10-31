/* SPDX-License-Identifier: BSD-2-Clause */
#include "boundedlog.h"
#include "../../shared/bounded_syslog.h"

static struct padavan_log_context upnp_log_context = PADAVAN_LOG_CONTEXT_INIT;

void miniupnpd_openlog(const char *ident, int options, int facility)
{
    padavan_log_open(&upnp_log_context, ident, options, facility);
}

void miniupnpd_closelog(void)
{
    padavan_log_close(&upnp_log_context);
}

int miniupnpd_setlogmask(int mask)
{
    return padavan_log_mask(&upnp_log_context, mask);
}

void miniupnpd_vsyslog(int priority, const char *format, va_list arguments)
{
    padavan_log_vwrite(&upnp_log_context, priority, format, arguments);
}

void miniupnpd_syslog(int priority, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    miniupnpd_vsyslog(priority, format, arguments);
    va_end(arguments);
}
