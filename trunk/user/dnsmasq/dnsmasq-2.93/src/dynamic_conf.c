/* Collect configuration generators before interpreting any of their output.
 * This bounds ordinary generator process groups; it is not a sandbox for
 * arbitrary root code (which can deliberately escape its process group).
 * Copyright (c) 2026. Distributed under GPL version 2 or later. */
#define _POSIX_C_SOURCE 200809L
#include "dynamic_conf.h"
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <poll.h>
#include <time.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <dirent.h>

static volatile sig_atomic_t cancelled;

static void cancel_script(int signal_number)
{
  (void)signal_number;
  cancelled = 1;
}

static long long monotonic_ms(void)
{
  struct timespec now;
  if (clock_gettime(CLOCK_MONOTONIC, &now) == -1)
    return -1;
  return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

int conf_script_check(const struct conf_script_budget *budget)
{
  long long now;
  if (!budget->deadline)
    return 1;
  now = monotonic_ms();
  return now >= 0 && now < budget->deadline;
}

/* Keep the child waitable until the group has been signalled, avoiding PID
 * reuse between reaping the leader and cleaning up a descendant's pipe. */
static int child_done(pid_t pid, int *success)
{
  siginfo_t info;
  memset(&info, 0, sizeof(info));
  if (waitid(P_PID, (id_t)pid, &info, WEXITED | WNOHANG | WNOWAIT) == -1)
    return errno == EINTR ? 0 : -1;
  if (!info.si_pid)
    return 0;
  *success = info.si_code == CLD_EXITED && info.si_status == 0;
  return 1;
}

/* All directed signals precede the sole reap. Afterwards only signal-0
 * probes are used: PGID reuse can conservatively reject, never target a new
 * process. A zombie-only group is also rejected until it disappears. */
static int stop_group(pid_t pid, int group, int exited, int *raw_status)
{
  long long end, now;
  int status, success = 0, clean = 1, reaped = 0;
  unsigned int attempt;
  pid_t result;

  if (child_done(pid, &success) < 0)
    return 0;
  if (kill(group ? -pid : pid, SIGTERM) != 0 && errno != ESRCH && !group)
    clean = 0;
  end = monotonic_ms();
  if (end < 0)
    clean = 0;
  else if (!exited)
    {
      end += 200;
      for (attempt = 0; attempt < 64; attempt++)
        {
          int done = child_done(pid, &success);
          if (done < 0)
            return 0;
          if (done)
            break;
          now = monotonic_ms();
          if (now < 0 || now >= end)
            { if (now < 0) clean = 0; break; }
          if (poll(NULL, 0, 10) < 0 && errno != EINTR)
            { clean = 0; break; }
        }
    }
  /* Even an earlier cleanup error cannot justify a signal after ECHILD. */
  if (child_done(pid, &success) < 0)
    return 0;
  /* A group-directed signal may fail for an already zombie-only group.
   * Only the later independent absence probe can establish cleanup then. */
  if (group)
    kill(-pid, SIGKILL);
  /* Cover a pre-exec group failure or a leader which changed its group. */
  if (kill(pid, SIGKILL) != 0 && errno != ESRCH)
    clean = 0;
  end = monotonic_ms();
  if (end < 0)
    clean = 0;
  else
    end += 300;
  for (attempt = 0; attempt < 64; attempt++)
    {
      if (!reaped)
        {
          result = waitpid(pid, &status, WNOHANG);
          if (result == pid)
            {
              reaped = 1;
              if (raw_status) *raw_status = status;
            }
          else if (result < 0 && errno != EINTR)
            return 0;
        }
      if (reaped)
        {
          if (!group)
            return clean;
          if (kill(-pid, 0) != 0)
            return errno == ESRCH && clean;
        }
      now = monotonic_ms();
      if (end < 0 || now < 0 || now >= end)
        return 0;
      if (poll(NULL, 0, 10) < 0 && errno != EINTR)
        return 0;
    }
  /* No synchronous reap guarantee for a task stuck in kernel I/O. Neither a
   * sent SIGKILL nor reaping only the leader permits output publication. */
  return 0;
}

static int restore_collector_signals(const struct sigaction previous[2],
                                     int installed, const sigset_t *mask, int masked)
{
  int i, restored = 1;
  const int signals[] = {SIGTERM, SIGINT};
  for (i = 0; i < installed; i++)
    if (sigaction(signals[i], &previous[i], NULL) != 0)
      restored = 0;
  if (masked && sigprocmask(SIG_SETMASK, mask, NULL) != 0)
    restored = 0;
  return restored;
}

static int prepare_fd(int fd, int nonblock)
{
  int flags;
  if (fcntl(fd, F_SETFD, FD_CLOEXEC) == -1)
    return 0;
  if (!nonblock)
    return 1;
  flags = fcntl(fd, F_GETFL);
  return flags != -1 && fcntl(fd, F_SETFL, flags | O_NONBLOCK) != -1;
}

static int close_inherited(long max_fd)
{
  DIR *directory = opendir("/proc/self/fd");
  struct dirent *entry;
  int complete = 1;
  if (!directory)
    directory = opendir("/dev/fd");
  if (directory)
    {
      int own_fd = dirfd(directory);
      for (;;)
        {
          char *end;
          long fd;
          errno = 0;
          entry = readdir(directory);
          if (!entry)
            {
              if (errno) complete = 0;
              break;
            }
          fd = strtol(entry->d_name, &end, 10);
          if (*entry->d_name && !*end && fd > 2 && fd != own_fd &&
              close((int)fd) == -1 && errno != EBADF)
            complete = 0;
        }
      if (closedir(directory) == -1) complete = 0;
      if (complete) return 1;
    }
  {
    long fd;
    for (fd = 3; fd < max_fd; fd++)
      if (close((int)fd) == -1 && errno != EBADF)
        return 0;
  }
  return 1;
}

/* SIGCHLD stays blocked while the leader pins its PID. Cleanup must reap the
 * owned leader and observe the original group absent before output is used.
 * Zombie-only groups and PGID reuse conservatively reject; trusted scripts
 * which deliberately change session/group are not contained by this runner. */
FILE *conf_script_open_status(const char *command, struct conf_script_budget *budget,
                              const char **error, int *raw_status)
{
  FILE *output = NULL;
  char *collected = NULL;
  int pipes[2][2] = {{-1, -1}, {-1, -1}};
  struct pollfd readers[2];
  pid_t pid = -1;
  size_t bytes = 0, capacity = 0, stderr_bytes = 0, line = 0;
  long long now, deadline;
  long max_fd;
  int i, done = 0, success = 0, group = 0, masked = 0;
  const int cancel_signals[] = {SIGTERM, SIGINT};
  struct sigaction action, previous[2], child_action;
  sigset_t blocked, previous_mask;
  int installed_handlers = 0;

  if (raw_status) *raw_status = -1;
  *error = "conf-script resource setup failed";
  cancelled = 0;
  sigemptyset(&blocked);
  sigaddset(&blocked, SIGCHLD);
  if (sigprocmask(SIG_BLOCK, &blocked, &previous_mask) != 0)
    goto fail;
  masked = 1;
  if (sigaction(SIGCHLD, NULL, &child_action) != 0 ||
      child_action.sa_handler == SIG_IGN || (child_action.sa_flags & SA_NOCLDWAIT))
    { *error = "conf-script child ownership unavailable"; goto fail; }
  memset(&action, 0, sizeof(action));
  action.sa_handler = cancel_script;
  sigemptyset(&action.sa_mask);
  for (i = 0; i != 2; i++)
    {
      if (sigaction(cancel_signals[i], &action, &previous[i]) == -1)
        goto fail;
      installed_handlers++;
    }
  now = monotonic_ms();
  if (now < 0)
    goto fail;
  if (!budget->deadline)
    budget->deadline = now + CONF_SCRIPT_TOTAL_MS;
  if (now >= budget->deadline)
    { *error = "conf-script total time budget exceeded"; goto fail; }
  if (budget->calls >= CONF_SCRIPT_MAX_CALLS || budget->depth >= CONF_SCRIPT_MAX_DEPTH)
    { *error = "conf-script invocation or nesting limit exceeded"; goto fail; }
  budget->calls++;
  deadline = now + CONF_SCRIPT_TIMEOUT_MS;
  if (deadline > budget->deadline)
    deadline = budget->deadline;
  if (pipe(pipes[0]) == -1 || pipe(pipes[1]) == -1)
    goto fail;
  for (i = 0; i != 2; i++)
    if (!prepare_fd(pipes[i][0], 1) || !prepare_fd(pipes[i][1], 0))
      goto fail;
  max_fd = sysconf(_SC_OPEN_MAX);
  if (max_fd < 0)
    goto fail;
  pid = fork();
  if (pid == -1)
    goto fail;
  if (pid == 0)
    {
      int nullfd, fd;
      size_t signal_index;
      const int signals[] = {SIGHUP, SIGINT, SIGQUIT, SIGTERM, SIGALRM,
                             SIGUSR1, SIGUSR2, SIGCHLD, SIGPIPE, SIGXFSZ};
      struct sigaction action;
      sigset_t empty;
      if (setpgid(0, 0) == -1 ||
          dup2(pipes[0][1], STDOUT_FILENO) == -1 ||
          dup2(pipes[1][1], STDERR_FILENO) == -1)
        _exit(126);
      nullfd = open("/dev/null", O_RDONLY);
      if (nullfd == -1 || dup2(nullfd, STDIN_FILENO) == -1)
        _exit(126);
      for (fd = 0; fd < 3; fd++)
        if (fcntl(fd, F_SETFD, 0) == -1)
          _exit(126);
      memset(&action, 0, sizeof(action));
      action.sa_handler = SIG_DFL;
      sigemptyset(&action.sa_mask);
      for (signal_index = 0; signal_index < sizeof(signals) / sizeof(signals[0]); signal_index++)
        sigaction(signals[signal_index], &action, NULL);
      sigemptyset(&empty);
      sigprocmask(SIG_SETMASK, &empty, NULL);
      if (!close_inherited(max_fd))
        _exit(126);
      execl("/bin/sh", "sh", "-c", command, (char *)NULL);
      _exit(127);
    }
  if (setpgid(pid, pid) == 0)
    group = 1;
  else
    {
      int group_error = errno;
      pid_t observed;
      if (group_error != EACCES && group_error != ESRCH)
        goto fail;
      errno = 0;
      observed = getpgid(pid);
      if (observed == pid)
        group = 1;
      else if (observed < 0 && errno == ESRCH)
        {
          int observed_done = child_done(pid, &success);
          if (observed_done < 0 && errno == ECHILD)
            {
              pid = -1;
              *error = "conf-script child ownership unavailable";
              goto fail;
            }
          /* The pre-exec child exits 126 if setpgid fails. An owned exit0
           * proves it established this group before exec, even when the
           * exited child's getpgid is no longer observable on this host. */
          if (observed_done == 1 && success)
            group = 1;
          else
            goto fail;
        }
      else
        goto fail;
    }
  for (i = 0; i != 2; i++)
    {
      close(pipes[i][1]); pipes[i][1] = -1;
      readers[i].fd = pipes[i][0];
      readers[i].events = POLLIN;
      readers[i].revents = 0;
    }
  while (1)
    {
      int remaining, result;
      if (cancelled)
        { *error = "conf-script execution cancelled"; goto fail; }
      now = monotonic_ms();
      if (now < 0 || now >= deadline)
        { *error = "conf-script time budget exceeded"; goto fail; }
      if (readers[0].fd == -1 && readers[1].fd == -1)
        {
          done = child_done(pid, &success);
          if (done < 0)
            {
              *error = errno == ECHILD ? "conf-script child ownership unavailable" :
                                        "conf-script child wait failed";
              /* ECHILD permanently revokes this identity. A later waitid
               * must not authorize signals to a recycled child PID. */
              if (errno == ECHILD) pid = -1;
              goto fail;
            }
          if (done)
            break;
        }
      remaining = (int)(deadline - now);
      if (remaining > 25)
        remaining = 25;
      result = poll(readers, 2, remaining);
      if (result == -1 && errno != EINTR)
        goto fail;
      for (i = 0; i != 2; i++)
        if (readers[i].fd != -1 && readers[i].revents)
          {
            char buffer[4096];
            ssize_t count = read(readers[i].fd, buffer, sizeof(buffer));
            size_t j;
            if (count < 0)
              {
                if (errno == EINTR || errno == EAGAIN)
                  continue;
                goto fail;
              }
            if (count == 0)
              {
                close(readers[i].fd); pipes[i][0] = readers[i].fd = -1;
                continue;
              }
            if (i == 1)
              {
                stderr_bytes += (size_t)count;
                if (stderr_bytes > CONF_SCRIPT_STDERR_BYTES)
                  { *error = "conf-script diagnostic output limit exceeded"; goto fail; }
                continue;
              }
            if ((size_t)count > CONF_SCRIPT_MAX_BYTES - bytes ||
                (size_t)count > CONF_SCRIPT_TOTAL_BYTES - budget->bytes)
              { *error = "conf-script output budget exceeded"; goto fail; }
            for (j = 0; j < (size_t)count; j++)
              if (buffer[j] == '\0' ||
                  (buffer[j] != '\n' && ++line > CONF_SCRIPT_LINE_BYTES))
                { *error = "conf-script NUL or overlong output line"; goto fail; }
              else if (buffer[j] == '\n')
                line = 0;
            if (bytes + (size_t)count > capacity)
              {
                char *grown;
                size_t next = capacity ? capacity : 4096;
                while (next < bytes + (size_t)count)
                  next *= 2;
                grown = realloc(collected, next);
                if (!grown)
                  { *error = "conf-script output allocation failed"; goto fail; }
                collected = grown;
                capacity = next;
              }
            memcpy(collected + bytes, buffer, (size_t)count);
            bytes += (size_t)count;
            budget->bytes += (size_t)count;
          }
    }
  if (!stop_group(pid, group, done, raw_status))
    { pid = -1; *error = "conf-script process cleanup failed"; goto fail; }
  pid = -1;
  if (cancelled)
    { *error = "conf-script execution cancelled"; goto fail; }
  if (!success)
    { *error = CONF_SCRIPT_STATUS_ERROR; goto fail; }
  /* No disk file: --test inherits a deliberately small diagnostic file limit.
   * A memory stream keeps that limit from rejecting valid generated config. */
  if (!collected)
    {
      collected = malloc(1);
      if (!collected)
        goto fail;
      collected[0] = '\n'; bytes = 1;
    }
  output = fmemopen(collected, bytes, "r");
  if (!output)
    { *error = "conf-script output stream failed"; goto fail; }
  if (!restore_collector_signals(previous, installed_handlers, &previous_mask, masked))
    { *error = "conf-script signal restore failed"; goto fail; }
  if (cancelled)
    { *error = "conf-script execution cancelled"; goto fail; }
  budget->buffers[budget->depth] = collected;
  budget->depth++;
  return output;

fail:
  if (pid > 0)
    stop_group(pid, group, done, raw_status);
  for (i = 0; i != 2; i++)
    {
      if (pipes[i][0] != -1) close(pipes[i][0]);
      if (pipes[i][1] != -1) close(pipes[i][1]);
    }
  if (output)
    fclose(output);
  free(collected);
  restore_collector_signals(previous, installed_handlers, &previous_mask, masked);
  return NULL;
}

FILE *conf_script_open(const char *command, struct conf_script_budget *budget,
                       const char **error)
{
  return conf_script_open_status(command, budget, error, NULL);
}

void conf_script_close(FILE *stream, struct conf_script_budget *budget)
{
  fclose(stream);
  if (budget->depth)
    {
      budget->depth--;
      free(budget->buffers[budget->depth]);
      budget->buffers[budget->depth] = NULL;
    }
}

/* Startup configuration is text with finite lines, files and aggregate input.
 * Runtime DHCP hosts/opts readers deliberately keep their existing grammar. */
int conf_config_line(FILE *stream, char **buffer, size_t *capacity,
                     size_t *file_bytes, struct conf_script_budget *budget,
                     const char **error)
{
  size_t used = 0;
  for (;;)
    {
      int c;
      if (!(used & 1023) && !conf_script_check(budget))
        { *error = "conf-script total parsing time budget exceeded"; return -1; }
      c = getc(stream);
      if (c == EOF)
        {
          if (ferror(stream))
            { *error = "configuration input read failed"; return -1; }
          if (used)
            {
              (*buffer)[used] = 0;
              if (budget->input_bytes) budget->input_bytes(stream,*buffer,used);
              return 1;
            }
          free(*buffer); *buffer = NULL; *capacity = 0;
          return 0;
        }
      if (++*file_bytes > (budget->trusted_flat==stream?CONF_CONFIG_TOTAL_BYTES:CONF_CONFIG_MAX_BYTES) ||
          ++budget->parsed_bytes > CONF_CONFIG_TOTAL_BYTES)
        { *error = "configuration input byte budget exceeded"; return -1; }
      if (c == 0 || (c != '\n' && used == CONF_SCRIPT_LINE_BYTES))
        { *error = "configuration NUL or overlong input line"; return -1; }
      if (used + 1 >= *capacity)
        {
          char *grown;
          size_t next = *capacity ? *capacity * 2 : 256;
          if (next > CONF_SCRIPT_LINE_BYTES + 1)
            next = CONF_SCRIPT_LINE_BYTES + 1;
          grown = realloc(*buffer, next);
          if (!grown)
            { *error = "configuration line allocation failed"; return -1; }
          *buffer = grown; *capacity = next;
        }
      (*buffer)[used] = 0;
      if (c == '\n')
        {
          if (budget->input_bytes) {
            budget->input_bytes(stream,*buffer,used);
            budget->input_bytes(stream,"\n",1);
          }
          return 1;
        }
      (*buffer)[used++] = (char)c;
    }
}
