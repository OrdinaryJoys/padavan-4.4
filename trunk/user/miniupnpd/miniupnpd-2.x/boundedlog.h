/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef MINIUPNPD_BOUNDED_LOG_H
#define MINIUPNPD_BOUNDED_LOG_H
#include <stdarg.h>
#include <syslog.h>
void miniupnpd_openlog(const char *, int, int);
void miniupnpd_closelog(void);
int miniupnpd_setlogmask(int);
void miniupnpd_vsyslog(int, const char *, va_list) __attribute__((format(printf, 2, 0)));
void miniupnpd_syslog(int, const char *, ...) __attribute__((format(printf, 2, 3)));
#endif
