/* Prepare immutable per-file bytes and candidate allocations before changing
 * live hosts/DHCP data. Bodies are released after parsing; aggregate counters
 * and final path identities remain until the group commits. A filesystem
 * syscall in uninterruptible sleep is outside this cooperative deadline. */
#include "dnsmasq.h"
#include "runtime_file.h"
#include "reload_file.h"

#define RELOAD_HASH 4096U
struct reload_allocation {
  struct reload_allocation *next;
  void *pointer;
  size_t bytes;
};
struct reload_identity {
  struct reload_identity *next;
  char *path;
  struct stat metadata;
};
static struct {
  int active, failed, next_index;
  const char *reason;
  size_t input_bytes, model_bytes;
  unsigned int files, directory_entries;
  long long deadline;
  struct reload_identity *identities;
  struct reload_allocation *allocations[RELOAD_HASH];
} reload;

static long long reload_clock(void)
{
  struct timespec now;
  if (clock_gettime(CLOCK_MONOTONIC, &now))
    return -1;
  return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

int dns_reload_active(void) { return reload.active; }
void dns_reload_fail(const char *reason)
{
  if (reload.active && !reload.failed)
    { reload.failed = 1; reload.reason = reason; }
}
const char *dns_reload_error(void)
{ return reload.reason ? reload.reason : "reload preparation failed"; }

int dns_reload_ok(void)
{
  long long now;
  if (!reload.active)
    return 1;
  if (!reload.failed && ((now = reload_clock()) < 0 || now >= reload.deadline))
    dns_reload_fail("reload cooperative time budget exceeded");
  return !reload.failed;
}

int dns_reload_begin(void)
{
  long long now;
  if (reload.active || (now = reload_clock()) < 0)
    return 0;
  memset(&reload, 0, sizeof(reload));
  reload.active = 1;
  reload.deadline = now + DNS_RELOAD_TIME_MS;
  reload.next_index = daemon->host_index;
  return 1;
}

void *dns_reload_track(void *pointer, size_t size)
{
  struct reload_allocation *item;
  unsigned int bucket;
  if (!reload.active || !pointer)
    return pointer;
  if (!dns_reload_ok() || DNS_RELOAD_MODEL_BYTES - reload.model_bytes < sizeof(*item) ||
      size > DNS_RELOAD_MODEL_BYTES - reload.model_bytes - sizeof(*item) ||
      !(item = malloc(sizeof(*item))))
    {
      free(pointer);
      dns_reload_fail("reload candidate allocation budget or memory exhausted");
      return NULL;
    }
  item->pointer = pointer;
  item->bytes = size + sizeof(*item);
  bucket = ((uintptr_t)pointer >> 3) % RELOAD_HASH;
  item->next = reload.allocations[bucket];
  reload.allocations[bucket] = item;
  reload.model_bytes += item->bytes;
  return pointer;
}

void *dns_reload_malloc(size_t size)
{
  void *pointer;
  if (!reload.active)
    return whine_malloc(size);
  if (!dns_reload_ok() || size > DNS_RELOAD_MODEL_BYTES - reload.model_bytes)
    { dns_reload_fail("reload candidate allocation budget exhausted"); return NULL; }
  if (!(pointer = calloc(1, size)))
    { dns_reload_fail("reload candidate allocation failed"); return NULL; }
  return dns_reload_track(pointer, size);
}

void dns_reload_free(void *pointer)
{
  struct reload_allocation **up, *item;
  if (reload.active && pointer)
    for (up = &reload.allocations[((uintptr_t)pointer >> 3) % RELOAD_HASH]; (item = *up); up = &item->next)
      if (item->pointer == pointer)
        {
          *up = item->next;
          reload.model_bytes -= item->bytes;
          free(item);
          break;
        }
  free(pointer);
}

static int remember(const char *path, const struct stat *metadata)
{
  struct reload_identity *item = dns_reload_malloc(sizeof(*item));
  size_t size = strlen(path) + 1;
  if (!item || !(item->path = dns_reload_malloc(size)))
    return 0;
  memcpy(item->path, path, size);
  item->metadata = *metadata;
  item->next = reload.identities;
  reload.identities = item;
  return 1;
}

int dns_reload_read(struct dns_runtime_file *input, const char *path, int hosts)
{
  const char *error;
  size_t limit = hosts ? DNS_RUNTIME_HOSTS_BYTES : DNS_RUNTIME_FILE_BYTES;
  if (!reload.active)
    return dns_runtime_file_open_limit(input, path, limit,
      hosts ? DNS_RUNTIME_HOSTS_LINES : DNS_RUNTIME_FILE_LINES, &error);
  if (!dns_reload_ok() || reload.files >= DNS_RELOAD_FILES)
    { dns_reload_fail("reload file-count budget exceeded"); return 0; }
  if (limit > DNS_RELOAD_INPUT_BYTES - reload.input_bytes)
    limit = DNS_RELOAD_INPUT_BYTES - reload.input_bytes;
  if (!limit || !dns_runtime_file_open_limit(input, path, limit,
      hosts ? DNS_RUNTIME_HOSTS_LINES : DNS_RUNTIME_FILE_LINES, &error))
    { dns_reload_fail(limit ? error : "reload aggregate input byte budget exceeded"); return 0; }
  reload.files++;
  reload.input_bytes += input->size;
  if (!remember(path, &input->metadata) || !dns_reload_ok())
    { dns_runtime_file_close(input); return 0; }
  return 1;
}

static int name_compare(const void *a, const void *b)
{ return strcmp(*(char *const *)a, *(char *const *)b); }

static struct hostsfile *append_file(struct hostsfile ***tail, const char *path,
                                    unsigned int index, unsigned int flags)
{
  struct hostsfile *item = dns_reload_malloc(sizeof(*item));
  size_t size = strlen(path) + 1;
  if (!item || !(item->fname = dns_reload_malloc(size)))
    return NULL;
  memcpy(item->fname, path, size);
  item->index = index;
  item->flags = flags;
  **tail = item;
  *tail = &item->next;
  return item;
}

struct hostsfile *dns_reload_files(struct hostsfile *old)
{
  struct hostsfile *root, *known, *list = NULL, **tail = &list;
  for (root = old; root; root = root->next)
    if (root->index >= (unsigned int)reload.next_index && root->index < INT_MAX)
      reload.next_index = root->index + 1;
  for (root = old; root && dns_reload_ok(); root = root->next)
    if (!(root->flags & AH_DIR))
      {
        struct stat before;
        if (stat(root->fname, &before))
          { dns_reload_fail("reload required input is missing or inaccessible"); break; }
        if (!S_ISDIR(before.st_mode))
          {
            if (!append_file(&tail, root->fname, root->index, root->flags & ~AH_INACTIVE))
              break;
          }
        else
          {
            DIR *directory;
            struct dirent *entry;
            char **names;
            unsigned int count = 0, i;
            if (!append_file(&tail, root->fname, root->index, root->flags | AH_INACTIVE) ||
                !(names = dns_reload_malloc(DNS_RELOAD_DIRECTORY_ENTRIES * sizeof(*names))))
              break;
            if (!(directory = opendir(root->fname)))
              { dns_reload_fail("reload directory cannot be opened"); break; }
            while (dns_reload_ok())
              {
                size_t len;
                errno = 0;
                entry = readdir(directory);
                if (!entry)
                  { if (errno) dns_reload_fail("reload directory read failed"); break; }
                if (++reload.directory_entries > DNS_RELOAD_DIRECTORY_ENTRIES)
                  { dns_reload_fail("reload directory entry budget exceeded"); break; }
                len = strlen(entry->d_name);
                if (!len || entry->d_name[0] == '.' || entry->d_name[len-1] == '~' ||
                    (entry->d_name[0] == '#' && entry->d_name[len-1] == '#'))
                  continue;
                names[count] = dns_reload_malloc(len + 1);
                if (!names[count]) break;
                memcpy(names[count++], entry->d_name, len + 1);
              }
            if (closedir(directory)) dns_reload_fail("reload directory close failed");
            if (!remember(root->fname, &before)) break;
            qsort(names, count, sizeof(*names), name_compare);
            for (i = 0; i < count && dns_reload_ok(); i++)
              {
                struct stat child;
                size_t length = strlen(root->fname) + strlen(names[i]) + 2;
                char *path = dns_reload_malloc(length);
                unsigned int index;
                if (!path) break;
                snprintf(path, length, "%s/%s", root->fname, names[i]);
                if (stat(path, &child))
                  { dns_reload_fail("reload directory member changed or is inaccessible"); break; }
                if (S_ISDIR(child.st_mode))
                  { dns_reload_free(path); continue; }
                for (known = old; known; known = known->next)
                  if ((known->flags & AH_DIR) && !strcmp(known->fname, path)) break;
                if (known) index = known->index;
                else if (reload.next_index >= INT_MAX)
                  { dns_reload_fail("reload source-index space exhausted"); break; }
                else index = reload.next_index++;
                append_file(&tail, path, index, AH_DIR);
                dns_reload_free(path);
              }
            for (i = 0; i < count; i++) dns_reload_free(names[i]);
            dns_reload_free(names);
          }
      }
  return list;
}

void dns_reload_free_files(struct hostsfile *list)
{
  while (list)
    { struct hostsfile *next = list->next; dns_reload_free(list->fname); dns_reload_free(list); list = next; }
}

int dns_reload_validate(void)
{
  struct reload_identity *item;
  for (item = reload.identities; item && dns_reload_ok(); item = item->next)
    if (!dns_runtime_file_unchanged(item->path, &item->metadata))
      dns_reload_fail("reload input identity changed before commit");
  return dns_reload_ok();
}

void dns_reload_end(int publish)
{
  struct reload_identity *identity = reload.identities;
  unsigned int i;
  while (identity)
    {
      struct reload_identity *next = identity->next;
      dns_reload_free(identity->path); dns_reload_free(identity); identity = next;
    }
  for (i = 0; i < RELOAD_HASH; i++)
    {
      struct reload_allocation *item = reload.allocations[i];
      while (item)
        {
          struct reload_allocation *next = item->next;
          if (!publish) free(item->pointer);
          free(item); item = next;
        }
    }
  if (publish) daemon->host_index = reload.next_index;
  memset(&reload, 0, sizeof(reload));
}
