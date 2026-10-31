/* One cooperative, bounded hosts/DHCP reload transaction in the event loop. */
#ifndef DNSMASQ_RELOAD_FILE_H
#define DNSMASQ_RELOAD_FILE_H

#define DNS_RELOAD_INPUT_BYTES (32U * 1024U * 1024U)
#define DNS_RELOAD_MODEL_BYTES (32U * 1024U * 1024U)
#define DNS_RELOAD_FILES 128U
#define DNS_RELOAD_DIRECTORY_ENTRIES 4096U
#define DNS_RELOAD_TIME_MS 10000

int dns_reload_begin(void);
int dns_reload_active(void);
int dns_reload_ok(void);
void dns_reload_fail(const char *reason);
const char *dns_reload_error(void);
void *dns_reload_malloc(size_t size);
void *dns_reload_track(void *pointer, size_t size);
void dns_reload_free(void *pointer);
int dns_reload_read(struct dns_runtime_file *input, const char *path, int hosts);
struct hostsfile *dns_reload_files(struct hostsfile *old);
void dns_reload_free_files(struct hostsfile *list);
int dns_reload_validate(void);
void dns_reload_end(int publish);

#endif
