#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
#include <time.h>
#include <sys/socket.h>
#include "httpd.h"

#ifndef HTTP_HEADER_DEADLINE
#define HTTP_HEADER_DEADLINE 30
#endif
#ifndef HTTP_BODY_DEADLINE
#define HTTP_BODY_DEADLINE 900
#endif
#ifndef HTTP_IO_TIMEOUT
#define HTTP_IO_TIMEOUT 60
#endif

static int64_t request_deadline;

static int64_t
monotonic_ms(void)
{
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
		return -1;
	return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

int
http_request_expired(void)
{
	int64_t now = monotonic_ms();
	if (now < 0 || now >= request_deadline) {
		errno = ETIMEDOUT;
		return 1;
	}
	return 0;
}

int
http_request_begin(int fd)
{
	int flags = fcntl(fd, F_GETFL);
	int64_t now = monotonic_ms();
	if (flags < 0 || now < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) != 0)
		return -1;
	request_deadline = now + HTTP_HEADER_DEADLINE * 1000;
	return 0;
}

void
http_request_allow_body(void)
{
	int64_t now = monotonic_ms();
	if (now >= 0)
		request_deadline = now + HTTP_BODY_DEADLINE * 1000;
}

int
http_request_wait(int fd, int writing)
{
	struct pollfd event;
	int ret;
	int64_t now = monotonic_ms(), idle_deadline;
	if (now < 0)
		return 0;
	idle_deadline = now + HTTP_IO_TIMEOUT * 1000;
	event.fd = fd;
	event.events = writing ? POLLOUT : POLLIN;
	for (;;) {
		int64_t end = request_deadline < idle_deadline ? request_deadline : idle_deadline;
		now = monotonic_ms();
		if (now < 0 || now >= end) {
			errno = ETIMEDOUT;
			return 0;
		}
		event.revents = 0;
		ret = poll(&event, 1, (int)(end - now));
		if (ret < 0 && errno == EINTR)
			continue;
		if (ret > 0) {
			if (event.revents & POLLNVAL) {
				errno = EBADF;
				return 0;
			}
			return 1;
		}
		if (ret == 0)
			errno = ETIMEDOUT;
		return 0;
	}
}

static ssize_t
plain_read(void *cookie, char *buffer, size_t length)
{
	int fd = *(int *)cookie;
	ssize_t count;
	for (;;) {
		if (!http_request_wait(fd, 0))
			return -1;
		count = recv(fd, buffer, length, 0);
		if (count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK))
			continue;
		return count;
	}
}

static ssize_t
plain_write(void *cookie, const char *buffer, size_t length)
{
	int fd = *(int *)cookie;
	ssize_t count;
	size_t sent = 0;
	while (sent < length) {
		if (!http_request_wait(fd, 1))
			return sent ? (ssize_t)sent : -1;
		count = send(fd, buffer + sent, length - sent, 0);
		if (count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK))
			continue;
		if (count <= 0)
			return sent ? (ssize_t)sent : -1;
		sent += count;
	}
	return (ssize_t)sent;
}

static int
plain_close(void *cookie)
{
	int fd = *(int *)cookie;
	free(cookie);
	return close(fd);
}

FILE *
http_client_fopen(int fd)
{
	static const cookie_io_functions_t functions = {
		.read = plain_read, .write = plain_write, .seek = NULL, .close = plain_close
	};
	FILE *stream;
	int *cookie = malloc(sizeof(*cookie));
	if (!cookie)
		return NULL;
	*cookie = fd;
	stream = fopencookie(cookie, "r+", functions);
	if (!stream)
		free(cookie);
	return stream;
}
