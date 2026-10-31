/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BOUNDED_PPP_LOG_H
#define BOUNDED_PPP_LOG_H
void ppp_log_open(const char *, int, int);
void ppp_log_close(void);
int ppp_log_mask(int);
void ppp_syslog(int, const char *, ...) __attribute__((format(printf, 2, 3)));
#endif
