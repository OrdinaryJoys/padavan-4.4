/* SPDX-License-Identifier: BSD-2-Clause
 * Copyright (c) 2026 OrdinaryJoys contributors
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 * THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT ANY EXPRESS OR IMPLIED WARRANTY,
 * INCLUDING MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE. IN NO EVENT
 * SHALL THE COPYRIGHT HOLDERS BE LIABLE FOR ANY DAMAGES ARISING FROM ITS USE.
 */
#ifndef PADAVAN_BOUNDED_SYSLOG_H
#define PADAVAN_BOUNDED_SYSLOG_H

#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <syslog.h>
#include <time.h>
#include <unistd.h>

#ifndef PADAVAN_LOG_SOCKET
#define PADAVAN_LOG_SOCKET "/dev/log"
#endif
#ifndef PADAVAN_LOG_CONSOLE
#define PADAVAN_LOG_CONSOLE "/dev/console"
#endif

/* Each component owns its context, without process-wide libc interposition.
 * Ident is copied and always terminated: valid identifiers up to959 bytes fit
 * the existing1024-byte syslog frame; longer ones use an explicit marker.
 * Callers must serialize context changes if they share it across threads.
 * No persistent descriptor survives a write, fork, or exec. LOG_NDELAY is kept
 * as context state; each write owns a fresh socket instead of pre-opening one.
 * Socket backpressure never retries or waits. Explicit LOG_PERROR/stderr and
 * best-effort nonblocking LOG_CONS output retain separate kernel IO semantics;
 * this API is neither a hard real-time nor an async-signal-safe guarantee.
 */
struct padavan_log_context {
    char ident[960];
    int options, facility;
    unsigned int mask;
};
#define PADAVAN_LOG_CONTEXT_INIT { "syslog", 0, LOG_USER, 0xffU }

static inline void padavan_log_open(struct padavan_log_context *context,
                                    const char *ident, int options, int facility)
{
    int saved = errno;
    if (ident) {
        size_t length = 0;
        while (length < sizeof(context->ident) && ident[length]) length++;
        if (length == sizeof(context->ident))
            memcpy(context->ident, "[identifier too long]", sizeof("[identifier too long]"));
        else {
            memmove(context->ident, ident, length);
            context->ident[length] = 0;
        }
    }
    context->options = options;
    if (!(facility & ~LOG_FACMASK)) context->facility = facility;
    errno = saved;
}

static inline void padavan_log_close(struct padavan_log_context *context)
{
    int saved = errno;
    memcpy(context->ident, "syslog", sizeof("syslog"));
    context->options = 0;
    context->facility = LOG_USER;
    context->mask = 0xffU;
    errno = saved;
}

static inline int padavan_log_mask(struct padavan_log_context *context, int mask)
{
    int old = (int)context->mask;
    if (mask) context->mask = (unsigned int)mask & 0xffU;
    return old;
}

static inline int padavan_log_descriptor(int descriptor)
{
    int flags = fcntl(descriptor, F_GETFL), fdflags;
    return flags >= 0 && fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) == 0 &&
           (fdflags = fcntl(descriptor, F_GETFD)) >= 0 &&
           fcntl(descriptor, F_SETFD, fdflags | FD_CLOEXEC) == 0;
}

static inline void padavan_log_console(const char *message, size_t length)
{
    int descriptor = open(PADAVAN_LOG_CONSOLE, O_WRONLY | O_NOCTTY | O_NONBLOCK);
    struct stat status;
    if (descriptor >= 0) {
        if (padavan_log_descriptor(descriptor) && fstat(descriptor, &status) == 0 && S_ISCHR(status.st_mode))
            (void)write(descriptor, message, length);
        (void)close(descriptor);
    }
}

static inline void padavan_log_vwrite(struct padavan_log_context *context,
                                      int priority, const char *format, va_list arguments)
{
    int saved = errno, count, descriptor = -1, flags = 0, sent = 0;
    char frame[1026], stamp[32];
    size_t used, body, stderr_start;
    struct tm calendar;
    struct sockaddr_un address;
    time_t now;
    if ((priority & ~(LOG_PRIMASK | LOG_FACMASK)) ||
        !(context->mask & LOG_MASK(LOG_PRI(priority)))) goto done;
    if (!(priority & LOG_FACMASK)) priority |= context->facility;
    now = time(NULL);
    stamp[0] = 0;
    if (localtime_r(&now, &calendar) && !strftime(stamp, sizeof(stamp), "%b %e %T", &calendar)) stamp[0] = 0;
    count = snprintf(frame, 1024, "<%d>%s%s", priority, stamp, stamp[0] ? " " : "");
    if (count < 0 || count >= 1024) goto done;
    used = stderr_start = (size_t)count;
    count = (context->options & LOG_PID) ?
        snprintf(frame + used, 1024 - used, "%s[%ld]: ", context->ident, (long)getpid()) :
        snprintf(frame + used, 1024 - used, "%s: ", context->ident);
    if (count < 0 || (size_t)count >= 1024 - used) goto done;
    used += (size_t)count;
    body = used;
    errno = saved; /* GNU %m observes the caller's errno, not setup calls. */
    count = vsnprintf(frame + used, 1024 - used, format, arguments);
    if (count < 0) goto done;
    if ((size_t)count >= 1024 - used) {
        static const char truncated[] = "[truncated] ";
        size_t marker = sizeof(truncated) - 1;
        used = 1023;
        if (used - body > marker) {
            memmove(frame + body + marker, frame + body, used - body - marker);
            memcpy(frame + body, truncated, marker);
        }
        frame[used] = 0;
    } else used += (size_t)count;
#ifdef LOG_PERROR
    if (context->options & LOG_PERROR) {
        frame[used] = '\n';
        (void)write(STDERR_FILENO, frame + stderr_start, used - stderr_start + 1);
        frame[used] = 0;
    }
#endif
    memset(&address, 0, sizeof(address));
    if (sizeof(PADAVAN_LOG_SOCKET) > sizeof(address.sun_path)) goto console;
    memcpy(address.sun_path, PADAVAN_LOG_SOCKET, sizeof(PADAVAN_LOG_SOCKET));
    address.sun_family = AF_UNIX;
#if defined(__APPLE__) || defined(__FreeBSD__) || defined(__NetBSD__) || defined(__OpenBSD__)
    address.sun_len = (unsigned char)(offsetof(struct sockaddr_un, sun_path) + sizeof(PADAVAN_LOG_SOCKET));
#endif
    descriptor = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (descriptor >= 0) {
        if (padavan_log_descriptor(descriptor)) {
#ifdef MSG_NOSIGNAL
            flags |= MSG_NOSIGNAL;
#endif
#ifdef MSG_DONTWAIT
            flags |= MSG_DONTWAIT;
#endif
            sent = sendto(descriptor, frame, used + 1, flags,
                          (struct sockaddr *)&address, sizeof(address)) == (ssize_t)(used + 1);
        }
        (void)close(descriptor);
    }
console:
    if (!sent && (context->options & LOG_CONS)) {
        char *start = strchr(frame, '>');
        if (start) {
            frame[used] = '\r'; frame[used + 1] = '\n';
            padavan_log_console(start + 1, used - (size_t)(start + 1 - frame) + 2);
        }
    }
done:
    errno = saved;
}

static inline void padavan_log_write(struct padavan_log_context *context,
                                     int priority, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    padavan_log_vwrite(context, priority, format, arguments);
    va_end(arguments);
}
#endif
