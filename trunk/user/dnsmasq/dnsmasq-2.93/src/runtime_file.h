/* Read-only, bounded snapshots of reloadable DNS text files.
 * Copyright (c) 2026. Distributed under GPL version 2 or later. */
#ifndef DNSMASQ_RUNTIME_FILE_H
#define DNSMASQ_RUNTIME_FILE_H

#include <stdio.h>

#define DNS_RUNTIME_FILE_BYTES (2U * 1024U * 1024U)
#define DNS_RUNTIME_LINE_BYTES 16384U
#define DNS_RUNTIME_FILE_LINES 65536U
#define DNS_RUNTIME_READ_MS 5000
#define DNS_RUNTIME_HOSTS_BYTES (16U * 1024U * 1024U)
#define DNS_RUNTIME_HOSTS_LINES 262144U

/* Limits apply per file, not to an entire reload of many files. The deadline
 * is checked between bounded reads; it cannot interrupt a stalled filesystem.
 * The fd variant borrows source and leaves both its offset and lifetime alone.
 * Symlink/hardlink aliases to stable regular files are intentionally accepted. */

struct dns_runtime_file {
  FILE *stream;
  void *contents;
};

int dns_runtime_file_open(struct dns_runtime_file *snapshot, const char *path,
                          const char **error);
int dns_runtime_file_open_limit(struct dns_runtime_file *snapshot, const char *path,
                                size_t byte_limit, unsigned int line_limit,
                                const char **error);
int dns_runtime_file_read_fd_limit(struct dns_runtime_file *snapshot, int source,
                                   size_t byte_limit, unsigned int line_limit,
                                   const char **error);
void dns_runtime_file_close(struct dns_runtime_file *snapshot);

/* Only the fixed literal /dev/null, with a verified standard device identity.
 * flags may contain O_WRONLY or O_RDWR, optionally O_APPEND. The returned
 * descriptor is NONBLOCK/CLOEXEC/NOCTTY and never follows a symlink. */
int dns_runtime_null_open(int flags);

#endif
