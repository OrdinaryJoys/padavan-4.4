/* dnsmasq is Copyright (c) 2000-2026 Simon Kelley

   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; version 2 dated June, 1991, or
   (at your option) version 3 dated 29 June, 2007.
 
   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
     
   You should have received a copy of the GNU General Public License
   along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#include "dnsmasq.h"
#include "runtime_file.h"

#ifdef __ANDROID__
#  include <android/log.h>
#endif

/* Implement logging to /dev/log asynchronously. If syslogd is 
   making DNS lookups through dnsmasq, and dnsmasq blocks awaiting
   syslogd, then the two daemons can deadlock. We get around this
   by not blocking when talking to syslog, instead we queue up to 
   MAX_LOGS messages. If more are queued, they will be dropped,
   and the drop event itself logged. */

/* The "wire" protocol for logging is defined in RFC 3164 */

/* From RFC 3164 */
#define MAX_MESSAGE 1024
#define LOG_WRITE_ATTEMPTS 128
#define LOG_FLUSH_TIMEOUT_MS 200

/* defaults in case we die() before we log_start() */
static int log_fac = LOG_DAEMON;
static int log_stderr = 0;
static int echo_stderr = 0;
static int log_fd = -1;
static int log_to_file = 0;
static int log_null = 0;
static int entries_alloced = 0;
static int entries_lost = 0;
static int connection_good = 1;
static int max_logs = 0;
static int connection_type = SOCK_DGRAM;

struct log_entry {
  int offset, length;
  pid_t pid; /* to avoid duplicates over a fork */
  struct log_entry *next;
  char payload[MAX_MESSAGE];
};

static struct log_entry *entries = NULL;
static struct log_entry *free_entries = NULL;

static long long log_milliseconds(void)
{
  struct timespec now;
  if (clock_gettime(CLOCK_MONOTONIC, &now) == -1)
    return -1;
  return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

#if !defined(HAVE_SOLARIS_NETWORK) && !defined(__ANDROID__)
static int log_socket(int type)
{
  int flags, fd = socket(AF_UNIX, type, 0), saved;
  if (fd == -1)
    return -1;
  if (fcntl(fd, F_SETFD, FD_CLOEXEC) == -1 ||
      (flags = fcntl(fd, F_GETFL)) == -1 ||
      fcntl(fd, F_SETFL, flags | O_NONBLOCK) == -1)
    goto fail;
#ifdef SO_NOSIGPIPE
  {
    int enabled = 1;
    if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &enabled, sizeof(enabled)) == -1)
      goto fail;
  }
#endif
  return fd;
fail:
  saved = errno;
  close(fd);
  errno = saved;
  return -1;
}

static int log_connect(int fd)
{
  struct sockaddr_un address;
  memset(&address, 0, sizeof(address));
#ifdef HAVE_SOCKADDR_SA_LEN
  address.sun_len = sizeof(address) - sizeof(address.sun_path) + strlen(_PATH_LOG) + 1;
#endif
  address.sun_family = AF_UNIX;
  safe_strncpy(address.sun_path, _PATH_LOG, sizeof(address.sun_path));
  return connect(fd, (struct sockaddr *)&address, sizeof(address));
}

static ssize_t log_socket_send(int fd, const void *data, size_t length)
{
  int flags = 0;
#ifdef MSG_NOSIGNAL
  flags |= MSG_NOSIGNAL;
#endif
#ifdef MSG_DONTWAIT
  flags |= MSG_DONTWAIT;
#endif
  return send(fd, data, length, flags);
}

/* Startup errors and permanent output failures must not re-enter a blocking
 * libc syslog path. This bounded, best-effort fallback owns only its fresh
 * nonblocking socket; it never calls my_syslog recursively. */
static void log_fallback(int priority, const char *func, const char *format, va_list args)
{
  char payload[MAX_MESSAGE], *stamp;
  time_t now;
  int prefix, type = connection_type, attempt;
  size_t length;
  time(&now);
  if (!(stamp = ctime(&now)))
    return;
  prefix = snprintf(payload, sizeof(payload), "<%d>%.15s dnsmasq%s[%d]: ",
                    priority | log_fac, stamp + 4, func, (int)getpid());
  if (prefix < 0 || (size_t)prefix >= sizeof(payload))
    return;
  if (vsnprintf(payload + prefix, sizeof(payload) - (size_t)prefix, format, args) < 0)
    return;
  length = strlen(payload) + 1;
  for (attempt = 0; attempt != 2; attempt++)
    {
      int fd = log_socket(type), error;
      size_t offset = 0, wanted = length - (type == SOCK_DGRAM);
      unsigned int writes = 0;
      if (fd == -1)
        return;
      if (log_connect(fd) == -1)
        {
          error = errno;
          close(fd);
          if (error != EPROTOTYPE)
            return;
          type = type == SOCK_DGRAM ? SOCK_STREAM : SOCK_DGRAM;
          continue;
        }
      connection_type = type;
      while (offset < wanted && writes++ != 4)
        {
          ssize_t count = log_socket_send(fd, payload + offset, wanted - offset);
          if (count == -1 && errno == EINTR)
            continue;
          if (count <= 0 || (size_t)count > wanted - offset)
            break;
          offset += (size_t)count;
        }
      close(fd);
      return;
    }
}
#endif


int log_start(struct passwd *ent_pw, int errfd)
{
  int ret = 0;

  echo_stderr = option_bool(OPT_DEBUG);

  if (daemon->log_fac != -1)
    log_fac = daemon->log_fac;
#ifdef LOG_LOCAL0
  else if (option_bool(OPT_DEBUG))
    log_fac = LOG_LOCAL0;
#endif

  if (daemon->log_file)
    { 
      log_to_file = 1;
      daemon->max_logs = 0;
      if (strcmp(daemon->log_file, "-") == 0)
	{
	  log_stderr = 1;
	  echo_stderr = 0;
	  log_fd = dup(STDERR_FILENO);
	}
    }
  
  max_logs = daemon->max_logs;

  if (!log_reopen(daemon->log_file))
    {
      send_event(errfd, EVENT_LOG_ERR, errno, daemon->log_file ? daemon->log_file : "");
      _exit(0);
    }

  /* if queuing is inhibited, make sure we allocate
     the one required buffer now. */
  if (max_logs == 0)
    {  
      free_entries = safe_malloc(sizeof(struct log_entry));
      free_entries->next = NULL;
      entries_alloced = 1;
    }

  /* If we're running as root and going to change uid later,
     change the ownership here so that the file is always owned by
     the dnsmasq user. Then logrotate can just copy the owner.
     Failure of the chown call is OK, (for instance when started as non-root).
     
     If we've created a file with group-id root, we also make
     the file group-writable. This gives processes in the root group
     write access to the file and avoids the problem that on some systems,
     once the file is owned by the dnsmasq user, it can't be written
     whilst dnsmasq is running as root during startup.
 */
  if (log_to_file && !log_stderr && !log_null && ent_pw && ent_pw->pw_uid != 0)
    {
      struct stat ls;
      if (getgid() == 0 && fstat(log_fd, &ls) == 0 && ls.st_gid == 0 &&
	  (ls.st_mode & S_IWGRP) == 0)
	(void)fchmod(log_fd, ls.st_mode | S_IWGRP);
      if (fchown(log_fd, ent_pw->pw_uid, -1) != 0)
	ret = errno;
    }

  return ret;
}

int log_reopen(char *log_file)
{
  if (!log_stderr)
    {      
      if (log_fd != -1)
	close(log_fd);
      log_null = 0;
      
      /* NOTE: umask is set to 022 by the time this gets called */
      
      if (log_file)
	{
          struct stat st;
          if (strcmp(log_file, "/dev/null") == 0)
            {
              log_fd = dns_runtime_null_open(O_WRONLY|O_APPEND);
              log_null = log_fd != -1;
            }
          else
            {
              log_fd = open(log_file, O_WRONLY|O_CREAT|O_APPEND|O_NONBLOCK|O_CLOEXEC|O_NOCTTY,
                            S_IRUSR|S_IWUSR|S_IRGRP);
              if (log_fd != -1)
                {
                  int status = fstat(log_fd, &st);
                  if (status == -1 || !S_ISREG(st.st_mode))
                    {
                      int error = status == -1 ? errno : EINVAL;
                      close(log_fd);
                      log_fd = -1;
                      errno = error;
                    }
                }
            }
        }
      else
	{
#if defined(HAVE_SOLARIS_NETWORK) || defined(__ANDROID__)
	  /* Solaris logging is "different", /dev/log is not unix-domain socket.
	     Just leave log_fd == -1 and use the vsyslog call for everything.... */
#   define _PATH_LOG ""  /* dummy */
	  return 1;
#else
          /* Even the default one-entry queue must never block DNS or
           * shutdown waiting for a syslog reader to drain its socket. */
          log_fd = log_socket(connection_type);
#endif
	}
    }
  
  return log_fd != -1;
}

static void free_entry(void)
{
  struct log_entry *tmp = entries;
  entries = tmp->next;
  tmp->next = free_entries;
  free_entries = tmp;
}      

static void lost_entry(void)
{
  if (entries_lost < INT_MAX)
    entries_lost++;
}

static void discard_entries(void)
{
  while (entries)
    {
      lost_entry();
      free_entry();
    }
}

static void restart_entry(void)
{
  if (entries)
    {
      entries->length += entries->offset;
      entries->offset = 0;
    }
}

static void log_write(void)
{
  ssize_t rc;
  unsigned int attempts = 0;
  int progressed = 0;
   
  while (entries && attempts++ != LOG_WRITE_ATTEMPTS)
    {
      /* The data in the payload is written with a terminating zero character 
	 and the length reflects this. For a stream connection we need to 
	 send the zero as a record terminator, but this isn't done for a 
	 datagram connection, so treat the length as one less than reality 
	 to elide the zero. If we're logging to a file, turn the zero into 
	 a newline, and leave the length alone. */
      int len_adjust = 0;
      progressed = 0;

      if (log_to_file)
	entries->payload[entries->offset + entries->length - 1] = '\n';
      else if (connection_type == SOCK_DGRAM)
	len_adjust = 1;

      /* Avoid duplicates over a fork() */
      if (entries->pid != getpid())
	{
	  free_entry();
	  progressed = 1;
	  continue;
	}

      connection_good = 1;

      if (log_to_file)
        rc = write(log_fd, entries->payload + entries->offset, entries->length - len_adjust);
#if !defined(HAVE_SOLARIS_NETWORK) && !defined(__ANDROID__)
      else
        rc = log_socket_send(log_fd, entries->payload + entries->offset, entries->length - len_adjust);
#else
      else
        rc = write(log_fd, entries->payload + entries->offset, entries->length - len_adjust);
#endif
      if (rc == 0)
        {
          connection_good = 0;
          return;
        }
      if (rc > 0)
	{
          progressed = 1;
	  entries->length -= rc;
	  entries->offset += rc;
	  if (entries->length == len_adjust)
	    {
	      free_entry();
	      if (entries_lost != 0)
		{
		  int e = entries_lost;
		  entries_lost = 0; /* avoid wild recursion */
		  my_syslog(LOG_WARNING, _("overflow: %d log entries lost"), e);
		}	  
	    }
	  continue;
	}
      
      if (errno == EINTR)
	return;

      if (errno == EAGAIN || errno == EWOULDBLOCK)
	return; /* syslogd busy, go again when select() or poll() says so */
      
      if (errno == ENOBUFS)
	{
	  connection_good = 0;
	  return;
	}

      /* errors handling after this assumes sockets */ 
      if (!log_to_file)
	{
	  /* Once a stream socket hits EPIPE, we have to close and re-open
	     (we ignore SIGPIPE) */
	  if (errno == EPIPE || errno == ECONNRESET)
	    {
	      if (log_reopen(NULL))
                {
                  restart_entry();
                  continue;
                }
	    }
	  else if (errno == ECONNREFUSED || 
		   errno == ENOTCONN || 
		   errno == EDESTADDRREQ)
	    {
	      /* socket went (syslogd down?), try and reconnect. If we fail,
		 stop trying until the next call to my_syslog() 
		 ECONNREFUSED -> connection went down
		 ENOTCONN -> nobody listening
		 (ECONNRESET, EDESTADDRREQ are *BSD equivalents) */
	      
	      /* Got connection back? try again. */
#if !defined(HAVE_SOLARIS_NETWORK) && !defined(__ANDROID__)
	      if (log_connect(log_fd) != -1)
		continue;
#endif
	      
	      /* errors from connect which mean we should keep trying */
	      if (errno == ENOENT || 
		  errno == EALREADY || errno == EINPROGRESS ||
		  errno == ECONNREFUSED ||
		  errno == EISCONN || 
		  errno == EINTR ||
		  errno == EAGAIN || 
		  errno == EWOULDBLOCK)
		{
		  /* try again on next syslog() call */
		  connection_good = 0;
		  return;
		}
	      
	      /* try the other sort of socket... */
	      if (errno == EPROTOTYPE)
		{
		  connection_type = connection_type == SOCK_DGRAM ? SOCK_STREAM : SOCK_DGRAM;
		  if (log_reopen(NULL))
                    {
                      restart_entry();
                      continue;
                    }
		}
	    }
	}

      /* Drop the failed queue before reporting through the bounded fallback.
       * Do not leak the old descriptor or re-enter a blocking libc logger. */
      {
        int saved = errno;
        close(log_fd);
        log_fd = -1;
        connection_good = 0;
        discard_entries();
        my_syslog(LOG_CRIT, _("log failed: %s"), strerror(saved));
      }
      return;
    }
  if (entries && !progressed)
    connection_good = 0;
}

/* priority is one of LOG_DEBUG, LOG_INFO, LOG_NOTICE, etc. See sys/syslog.h.
   OR'd to priority can be MS_TFTP, MS_DHCP, ... to be able to do log separation between
   DNS, DHCP and TFTP services.
   If OR'd with MS_DEBUG, the messages are suppressed unless --log-debug is set. */
void my_syslog(int priority, const char *format, ...)
{
  va_list ap;
  struct log_entry *entry;
  time_t time_now;
  char *p;
  size_t len;
  pid_t pid = getpid();
  char *func = "";

  if ((LOG_FACMASK & priority) == MS_TFTP)
    func = "-tftp";
  else if ((LOG_FACMASK & priority) == MS_DHCP)
    func = "-dhcp";
  else if ((LOG_FACMASK & priority) == MS_SCRIPT)
    func = "-script";
  else if ((LOG_FACMASK & priority) == MS_DEBUG)
    {
      if (!option_bool(OPT_LOG_DEBUG))
	return;
      func = "-debug";
    }
  
#ifdef LOG_PRI
  priority = LOG_PRI(priority);
#else
  /* Solaris doesn't have LOG_PRI */
  priority &= LOG_PRIMASK;
#endif

  if (echo_stderr) 
    {
      fprintf(stderr, "dnsmasq%s: ", func);
      va_start(ap, format);
      vfprintf(stderr, format, ap);
      va_end(ap);
      fputc('\n', stderr);
    }

  if (log_fd == -1)
    {
#ifdef __ANDROID__
      /* do android-specific logging. 
	 log_fd is always -1 on Android except when logging to a file. */
      int alog_lvl;
      
      if (priority <= LOG_ERR)
	alog_lvl = ANDROID_LOG_ERROR;
      else if (priority == LOG_WARNING)
	alog_lvl = ANDROID_LOG_WARN;
      else if (priority <= LOG_INFO)
	alog_lvl = ANDROID_LOG_INFO;
      else
	alog_lvl = ANDROID_LOG_DEBUG;

      va_start(ap, format);
      __android_log_vprint(alog_lvl, "dnsmasq", format, ap);
      va_end(ap);
#elif defined(HAVE_SOLARIS_NETWORK)
      /* fall-back to syslog if we die during startup or 
	 fail during running (always on Solaris). */
      static int isopen = 0;

      if (!isopen)
	{
	  openlog("dnsmasq", LOG_PID, log_fac);
	  isopen = 1;
	}
      va_start(ap, format);  
      vsyslog(priority, format, ap);
      va_end(ap);
#else
      va_start(ap, format);
      log_fallback(priority, func, format, ap);
      va_end(ap);
#endif

      return;
    }
  
  if ((entry = free_entries))
    free_entries = entry->next;
  else if (entries_alloced < max_logs && (entry = malloc(sizeof(struct log_entry))))
    entries_alloced++;
  
  if (!entry)
    lost_entry();
  else
    {
      /* add to end of list, consumed from the start */
      entry->next = NULL;
      if (!entries)
	entries = entry;
      else
	{
	  struct log_entry *tmp;
	  for (tmp = entries; tmp->next; tmp = tmp->next);
	  tmp->next = entry;
	}
      
      time(&time_now);
      p = entry->payload;
      if (!log_to_file)
	p += sprintf(p, "<%d>", priority | log_fac);

      /* Omit timestamp for default daemontools situation */
      if (!log_stderr || !option_bool(OPT_NO_FORK)) 
	p += sprintf(p, "%.15s ", ctime(&time_now) + 4);
      
      p += sprintf(p, "dnsmasq%s[%d]: ", func, (int)pid);
        
      len = p - entry->payload;
      va_start(ap, format);  
      len += vsnprintf(p, MAX_MESSAGE - len, format, ap) + 1; /* include zero-terminator */
      va_end(ap);
      entry->length = len > MAX_MESSAGE ? MAX_MESSAGE : len;
      entry->offset = 0;
      entry->pid = pid;
    }
  
  /* almost always, logging won't block, so try and write this now,
     to save collecting too many log messages during a select loop. */
  log_write();
  
  /* Since we're doing things asynchronously, a cache-dump, for instance,
     can now generate log lines very fast. With a small buffer (desirable),
     that means it can overflow the log-buffer very quickly,
     so that the cache dump becomes mainly a count of how many lines 
     overflowed. To avoid this, we delay here, the delay is controlled 
     by queue-occupancy, and grows exponentially. The delay is limited to (2^8)ms.
     The scaling stuff ensures that when the queue is bigger than 8, the delay
     only occurs for the last 8 entries. Once the queue is full, we stop delaying
     to preserve performance.
  */

  if (entries && max_logs != 0)
    {
      int d;
      
      for (d = 0,entry = entries; entry; entry = entry->next, d++);
      
      if (d == max_logs)
	d = 0;
      else if (max_logs > 8)
	d -= max_logs - 8;

      if (d > 0)
	{
	  struct timespec waiter;
	  waiter.tv_sec = 0;
	  waiter.tv_nsec = 1000000 << (d - 1); /* 1 ms */
	  nanosleep(&waiter, NULL);
      
	  /* Have another go now */
	  log_write();
	}
    } 
}

void set_log_writer(void)
{
  if (entries && log_fd != -1 && connection_good)
    poll_listen(log_fd, POLLOUT);
}

void check_log_writer(int force)
{
  if (log_fd != -1 && (force || poll_check(log_fd, POLLOUT)))
    log_write();
}

void flush_log(void)
{
  long long now = log_milliseconds(), deadline = now < 0 ? -1 : now + LOG_FLUSH_TIMEOUT_MS;
  /* Syslog sockets are nonblocking, including the default one-entry queue.
   * Named files and stderr retain their existing kernel write semantics. */
  while (log_fd != -1)
    {
      struct timespec waiter;
      log_write();
      if (!entries || !connection_good || deadline < 0 ||
          (now = log_milliseconds()) < 0 || now >= deadline)
        break;
      waiter.tv_sec = 0;
      waiter.tv_nsec = 1000000; /* 1 ms */
      nanosleep(&waiter, NULL);
    }
  if (log_fd != -1)
    close(log_fd);
  log_fd = -1;
  connection_good = 0;
  discard_entries();
}

void die(char *message, char *arg1, int exit_code)
{
  char *errmess = strerror(errno);
  
  if (!arg1)
    arg1 = errmess;

  if (!log_stderr)
    {
      echo_stderr = 1; /* print as well as log when we die.... */
      fputc('\n', stderr); /* prettyfy  startup-script message */
    }
  my_syslog(LOG_CRIT, message, arg1, errmess);
  echo_stderr = 0;
  my_syslog(LOG_CRIT, _("FAILED to start up"));
  flush_log();
  
  exit(exit_code);
}
