/* One cooperative, bounded hosts/DHCP reload transaction in the event loop. */
#ifndef DNSMASQ_RELOAD_FILE_H
#define DNSMASQ_RELOAD_FILE_H

#define DNS_RELOAD_INPUT_BYTES (32U * 1024U * 1024U)
#define DNS_RELOAD_MODEL_BYTES (32U * 1024U * 1024U)
#define DNS_RELOAD_FILES 128U
#define DNS_RELOAD_DIRECTORY_ENTRIES 4096U
#define DNS_RELOAD_TIME_MS 10000
#define DNS_RELOAD_HOT_TIME_MS 250
#define DNS_RELOAD_SYSTEM_HEADROOM_BYTES (16U * 1024U * 1024U)
/* Only small, bounded model/parser operations use the batched check. Input
 * reads, validation, and every256-step chain walk keep forced clock checks. */
#define DNS_RELOAD_CHECK_WORK 64U
#define DNS_RELOAD_FORCE_ALLOCATION 4096U

void dns_reload_initial(int initial);
int dns_reload_begin(void);
int dns_reload_active(void);
int dns_reload_ok(void);
int dns_reload_work_ok(void);
static inline int dns_reload_step(unsigned int *work)
{ return (++*work & 255U) || dns_reload_ok(); }
void dns_reload_fail(const char *reason);
const char *dns_reload_error(void);
void *dns_reload_malloc(size_t size);
void *dns_reload_track(void *pointer, size_t size);
void dns_reload_free(void *pointer);
int dns_reload_read(struct dns_runtime_file *input, const char *path, int hosts);
void dns_reload_close(struct dns_runtime_file *input);
struct hostsfile *dns_reload_files(struct hostsfile *old);
void dns_reload_free_files(struct hostsfile *list);
int dns_reload_validate(void);
void dns_reload_end(int publish);

#endif
