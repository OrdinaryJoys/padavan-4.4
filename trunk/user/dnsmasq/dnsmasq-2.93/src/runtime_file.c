/* A FIFO must never hold the DNS event loop in fopen(), and a regular file
 * must not evade the byte/line limits by growing during a reload. Validate a
 * complete private memory snapshot before callers parse any bytes from it.
 * Configured symlinks and hardlinks to ordinary files remain supported; this
 * reader neither changes their permissions nor imposes a new owner policy.
 * O_NONBLOCK cannot impose a wall-clock bound on a stalled kernel/filesystem.
 * Copyright (c) 2026. Distributed under GPL version 2 or later. */
#include "dnsmasq.h"
#include "runtime_file.h"
#ifdef __linux__
#include <sys/sysmacros.h>
#endif

static int runtime_null_device(const struct stat *metadata)
{
  if (!S_ISCHR(metadata->st_mode))
    return 0;
#ifdef __linux__
  return major(metadata->st_rdev) == 1 && minor(metadata->st_rdev) == 3;
#elif defined(__APPLE__)
  /* The native test host's standard null device. Firmware uses Linux1:3. */
  return major(metadata->st_rdev) == 3 && minor(metadata->st_rdev) == 2;
#else
  return 0;
#endif
}

int dns_runtime_null_open(int flags)
{
  struct stat before, opened, after;
  int fd, status, saved;
  if ((flags & ~(O_ACCMODE|O_APPEND)) ||
      ((flags & O_ACCMODE) != O_WRONLY && (flags & O_ACCMODE) != O_RDWR))
    {
      errno = EINVAL;
      return -1;
    }
  if (lstat("/dev/null", &before) == -1)
    return -1;
  if (!runtime_null_device(&before))
    {
      errno = EINVAL;
      return -1;
    }
  fd = open("/dev/null", flags|O_NONBLOCK|O_CLOEXEC|O_NOCTTY|O_NOFOLLOW);
  if (fd == -1)
    return -1;
  status = fstat(fd, &opened);
  if (status == 0)
    status = lstat("/dev/null", &after);
  if (status == -1 || !runtime_null_device(&opened) || !runtime_null_device(&after) ||
      before.st_dev != opened.st_dev || before.st_ino != opened.st_ino ||
      before.st_rdev != opened.st_rdev || after.st_dev != opened.st_dev ||
      after.st_ino != opened.st_ino || after.st_rdev != opened.st_rdev)
    {
      saved = status == -1 ? errno : EINVAL;
      close(fd);
      errno = saved;
      return -1;
    }
  return fd;
}

static int runtime_same_file(const struct stat *a, const struct stat *b)
{
  if (a->st_dev != b->st_dev || a->st_ino != b->st_ino ||
      a->st_mode != b->st_mode || a->st_uid != b->st_uid ||
      a->st_gid != b->st_gid || a->st_nlink != b->st_nlink ||
      a->st_size != b->st_size || a->st_mtime != b->st_mtime ||
      a->st_ctime != b->st_ctime)
    return 0;
#ifdef __APPLE__
  return a->st_mtimespec.tv_nsec == b->st_mtimespec.tv_nsec &&
    a->st_ctimespec.tv_nsec == b->st_ctimespec.tv_nsec;
#else
  return a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
    a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
#endif
}

int dns_runtime_file_unchanged(const char *path, const struct stat *metadata)
{
  struct stat current;
  return stat(path, &current) == 0 && runtime_same_file(metadata, &current);
}

static long long runtime_milliseconds(void)
{
  struct timespec now;
  if (clock_gettime(CLOCK_MONOTONIC, &now) == -1)
    return -1;
  return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

/* Own fd on entry, including every failure. pread keeps a persistent lease
 * writer's shared open-file offset intact. No live records are parsed here. */
static int runtime_read_owned(struct dns_runtime_file *snapshot, int fd,
                              const char *path, const struct stat *before,
                              size_t byte_limit, unsigned int line_limit,
                              long long group_deadline, const char **error)
{
  struct stat opened, after, named;
  unsigned char *bytes = NULL, extra, verify[4096];
  size_t size, used = 0, line = 0, lines = 0, i;
  unsigned int interrupts = 0;
  long long deadline, now;
  ssize_t count;

  memset(snapshot, 0, sizeof(*snapshot));
  *error = "runtime DNS input has invalid reader limits";
  if (group_deadline < 0 || !byte_limit || byte_limit > DNS_RUNTIME_HOSTS_BYTES ||
      !line_limit || line_limit > DNS_RUNTIME_HOSTS_LINES)
    goto fail;
  *error = "runtime DNS input is not a regular file";
  if (fstat(fd, &opened) == -1 || !S_ISREG(opened.st_mode))
    goto fail;
  *error = "runtime DNS input changed while opening";
  if (before && !runtime_same_file(before, &opened))
    goto fail;
  *error = byte_limit == DNS_RUNTIME_FILE_BYTES ?
    "runtime DNS input exceeds the 2 MiB byte limit" :
    "runtime DNS input exceeds its byte limit";
  if (opened.st_size < 0 || (uint64_t)opened.st_size > byte_limit)
    goto fail;
  size = (size_t)opened.st_size;
  *error = "runtime DNS input clock failed";
  if ((now = runtime_milliseconds()) < 0)
    goto fail;
  deadline = now + DNS_RUNTIME_READ_MS;
  if (group_deadline > 0 && group_deadline < deadline) deadline = group_deadline;
  *error = "runtime DNS input read time budget exceeded";
  if (now >= deadline) goto fail;
  *error = "runtime DNS input allocation failed";
  if (!(bytes = malloc(size ? size : 1)))
    goto fail;
  while (used < size)
    {
      size_t take = size - used;
      *error = "runtime DNS input read time budget exceeded";
      if ((now = runtime_milliseconds()) < 0 || now >= deadline)
        goto fail;
      if (take > 4096)
        take = 4096;
      *error = "runtime DNS input read failed or changed size";
      count = pread(fd, bytes + used, take, (off_t)used);
      if (count < 0 && errno == EINTR && interrupts++ < 16)
        continue;
      if (count <= 0 || (size_t)count > take)
        goto fail;
      used += (size_t)count;
    }
  do
    {
      *error = "runtime DNS input read time budget exceeded";
      if ((now = runtime_milliseconds()) < 0 || now >= deadline)
        goto fail;
      *error = "runtime DNS input read failed or changed size";
      count = pread(fd, &extra, 1, (off_t)size);
    }
  while (count < 0 && errno == EINTR && interrupts++ < 16);
  if (count != 0)
    goto fail;

  /* Equal size and timestamps do not prove unchanged contents: filesystem
   * timestamps may have coarse resolution. Re-read through this same fd and
   * compare bounded chunks with the private snapshot, using the original
   * deadline. This detects persistent rewrites, including mixed first-pass
   * chunks, without a second whole-file allocation or parsing live bytes.
   * A non-cooperating writer can still change an already verified range or
   * restore identical bytes; this is not an atomic filesystem snapshot. */
  used = 0;
  while (used < size)
    {
      size_t take = size - used;
      *error = "runtime DNS input read time budget exceeded";
      if ((now = runtime_milliseconds()) < 0 || now >= deadline)
        goto fail;
      if (take > sizeof(verify))
        take = sizeof(verify);
      *error = "runtime DNS input verification read failed or changed size";
      count = pread(fd, verify, take, (off_t)used);
      if (count < 0 && errno == EINTR && interrupts++ < 16)
        continue;
      if (count <= 0 || (size_t)count > take)
        goto fail;
      *error = "runtime DNS input contents changed while reading";
      if (memcmp(bytes + used, verify, (size_t)count))
        goto fail;
      used += (size_t)count;
    }
  do
    {
      *error = "runtime DNS input read time budget exceeded";
      if ((now = runtime_milliseconds()) < 0 || now >= deadline)
        goto fail;
      *error = "runtime DNS input verification read failed or changed size";
      count = pread(fd, &extra, 1, (off_t)size);
    }
  while (count < 0 && errno == EINTR && interrupts++ < 16);
  if (count != 0)
    goto fail;

  *error = "runtime DNS input changed while reading";
  if (fstat(fd, &after) == -1 || !runtime_same_file(&opened, &after) ||
      (path && (stat(path, &named) == -1 || !runtime_same_file(&opened, &named))))
    goto fail;
  if (close(fd) == -1)
    {
      fd = -1;
      *error = "runtime DNS input close failed";
      goto fail;
    }
  fd = -1;

  for (i = 0; i < size; i++)
    {
      if ((i & 4095) == 0)
        {
          *error = "runtime DNS input read time budget exceeded";
          if ((now = runtime_milliseconds()) < 0 || now >= deadline)
            goto fail;
        }
      *error = "runtime DNS input contains a NUL byte";
      if (bytes[i] == 0)
        goto fail;
      if (bytes[i] == '\n')
        {
          line = 0;
          lines++;
        }
      else if (++line > DNS_RUNTIME_LINE_BYTES)
        {
          *error = "runtime DNS input exceeds the 16 KiB line limit";
          goto fail;
        }
      *error = line_limit == DNS_RUNTIME_FILE_LINES ?
        "runtime DNS input exceeds the 65536 line limit" :
        "runtime DNS input exceeds its line count limit";
      if (lines > line_limit)
        goto fail;
    }
  if (line && lines == line_limit)
    goto fail;

  *error = "runtime DNS input read time budget exceeded";
  if ((now = runtime_milliseconds()) < 0 || now >= deadline) goto fail;

  /* Older memory-stream implementations need a nonempty buffer. A blank
   * line is equivalent to an empty file for all callers of this reader. */
  if (!size)
    bytes[0] = '\n';
  *error = "runtime DNS input memory stream failed";
  if (!(snapshot->stream = fmemopen(bytes, size ? size : 1, "r")))
    goto fail;
  snapshot->contents = bytes;
  snapshot->size = size;
  snapshot->metadata = opened;
  return 1;

fail:
  if (fd != -1)
    close(fd);
  free(bytes);
  return 0;
}

int dns_runtime_file_open_limit_deadline(struct dns_runtime_file *snapshot, const char *path,
                                size_t byte_limit, unsigned int line_limit,
                                long long group_deadline, const char **error)
{
  struct stat before;
  int fd;
  memset(snapshot, 0, sizeof(*snapshot));
  *error = "runtime DNS input cannot be read";
  if (stat(path, &before) == -1)
    return 0;
  *error = "runtime DNS input is not a regular file";
  if (!S_ISREG(before.st_mode))
    return 0;
  *error = "runtime DNS input cannot be opened";
  fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOCTTY);
  if (fd == -1)
    return 0;
  return runtime_read_owned(snapshot, fd, path, &before, byte_limit, line_limit, group_deadline, error);
}

int dns_runtime_file_open_limit(struct dns_runtime_file *snapshot, const char *path,
                                size_t byte_limit, unsigned int line_limit, const char **error)
{
  return dns_runtime_file_open_limit_deadline(snapshot, path, byte_limit, line_limit, 0, error);
}

int dns_runtime_file_read_fd_limit(struct dns_runtime_file *snapshot, int source,
                                   size_t byte_limit, unsigned int line_limit,
                                   const char **error)
{
  int fd;
  memset(snapshot, 0, sizeof(*snapshot));
  *error = "runtime DNS input descriptor cannot be duplicated";
  if ((fd = fcntl(source, F_DUPFD_CLOEXEC, 0)) == -1)
    return 0;
  return runtime_read_owned(snapshot, fd, NULL, NULL, byte_limit, line_limit, 0, error);
}

int dns_runtime_file_open(struct dns_runtime_file *snapshot, const char *path,
                          const char **error)
{
  return dns_runtime_file_open_limit(snapshot, path, DNS_RUNTIME_FILE_BYTES,
                                      DNS_RUNTIME_FILE_LINES, error);
}

void dns_runtime_file_close(struct dns_runtime_file *snapshot)
{
  if (snapshot->stream)
    fclose(snapshot->stream);
  free(snapshot->contents);
  memset(snapshot, 0, sizeof(*snapshot));
}
