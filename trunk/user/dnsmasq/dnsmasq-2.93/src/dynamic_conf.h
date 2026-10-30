/* Bounded conf-script collection, shared by startup and --test parsing.
 * Copyright (c) 2026. Distributed under GPL version 2 or later. */
#ifndef DNSMASQ_DYNAMIC_CONF_H
#define DNSMASQ_DYNAMIC_CONF_H

#include <stdio.h>
#include <stddef.h>

#ifndef CONF_SCRIPT_TIMEOUT_MS
#define CONF_SCRIPT_TIMEOUT_MS 10000
#endif
#ifndef CONF_SCRIPT_TOTAL_MS
#define CONF_SCRIPT_TOTAL_MS 30000
#endif
#define CONF_SCRIPT_MAX_BYTES (2U * 1024U * 1024U)
#define CONF_SCRIPT_TOTAL_BYTES (4U * 1024U * 1024U)
#define CONF_SCRIPT_STDERR_BYTES 65536U
#define CONF_SCRIPT_LINE_BYTES 16384U
#define CONF_SCRIPT_MAX_CALLS 16U
#define CONF_SCRIPT_MAX_DEPTH 8U
#define CONF_CONFIG_MAX_BYTES (2U * 1024U * 1024U)
#define CONF_CONFIG_TOTAL_BYTES (16U * 1024U * 1024U)
#define CONF_CONFIG_MAX_FILES 128U
#define CONF_CONFIG_MAX_DEPTH 32U
#define CONF_CONFIG_MAX_DIR_ENTRIES 4096U

struct conf_script_budget {
  long long deadline;
  size_t bytes;
  unsigned int calls, depth;
  size_t parsed_bytes;
  unsigned int files, parse_depth;
  unsigned int directory_entries, directory_files;
  FILE *trusted_flat;
  void (*input_bytes)(FILE *, const void *, size_t);
  char *buffers[CONF_SCRIPT_MAX_DEPTH];
};

int conf_script_check(const struct conf_script_budget *budget);
FILE *conf_script_open(const char *command, struct conf_script_budget *budget,
                       const char **error);
void conf_script_close(FILE *stream, struct conf_script_budget *budget);
int conf_config_line(FILE *stream, char **buffer, size_t *capacity,
                     size_t *file_bytes, struct conf_script_budget *budget,
                     const char **error);

#endif
