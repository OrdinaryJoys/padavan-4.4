/* One-generation startup configuration snapshots. GPL version2 or later. */
#ifndef DNSMASQ_CONF_SNAPSHOT_H
#define DNSMASQ_CONF_SNAPSHOT_H
#include <stdio.h>
#include <stddef.h>
#include <sys/stat.h>
#include "dynamic_conf.h"

#define CONF_SNAPSHOT_FLAT_BYTES CONF_CONFIG_TOTAL_BYTES
#define CONF_SNAPSHOT_MANIFEST_BYTES (1024U * 1024U)
#define CONF_SNAPSHOT_RECORDS 256U
#define CONF_SNAPSHOT_HEADROOM (256U * 1024U)

enum { CONF_SNAPSHOT_OFF, CONF_SNAPSHOT_CAPTURE, CONF_SNAPSHOT_USE };
/* Parses only the private CLI contract. 1=normal continue, 2=seal complete,
 * 0=error. Ordinary invocations without snapshot flags are unchanged. */
int conf_snapshot_cli(int argc, char **argv, struct conf_script_budget *budget,
                      const char **error);
int conf_snapshot_mode(void);
int conf_snapshot_managed(void);
const char *conf_snapshot_overlay(const char *logical);
int conf_snapshot_input_begin(const char *logical, FILE *stream, const char **error);
int conf_snapshot_input_end(FILE *stream, const char **error);
/* Observe an inode-deduplicated path without expanding it a second time. */
int conf_snapshot_input_alias(const char *logical, const struct stat *observed,
                              const char **error);
int conf_snapshot_line(const char *line, const char **error);
int conf_snapshot_script(unsigned int ordinal, unsigned int parent, unsigned int depth,
                         const char *command, const char **error);
int conf_snapshot_directory(const char *directory, const char *filters, const char **error);
FILE *conf_snapshot_stream(void);
int conf_snapshot_finish(const char **error);
void conf_snapshot_dispose(void);
#endif
