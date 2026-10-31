#!/usr/bin/env python3
"""Exercise the actual HTTP receive implementation on host socket pairs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "trunk/user/miniupnpd/miniupnpd-2.x"
CONFIG = '''
#define OS_VERSION "test"
#define UPNP_VERSION_MAJOR_STR "1"
#define UPNP_VERSION_MINOR_STR "0"
#define UPNP_VERSION_MAJOR 1
#define UPNP_VERSION_MINOR 0
#define MINIUPNPD_VERSION "test"
'''
DRIVER = r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>
static int allocations, fail_allocation, soap_calls;
static void *test_realloc(void *p, size_t n) {
    allocations++;
    if(fail_allocation) { fail_allocation=0; return NULL; }
    return realloc(p,n);
}
#define realloc test_realloc
#include "upnphttp.c"
#undef realloc
/* Resource-limit tests isolate the logging backend; producer backpressure is
 * exercised separately against actual boundedlog.c and private sockets. */
void miniupnpd_syslog(int priority, const char *format, ...) {
    (void)priority; (void)format;
}
int set_non_blocking(int fd) { return fcntl(fd,F_SETFL,O_NONBLOCK) == 0; }
char *genRootDesc(int *len) { *len=7; return strdup("<root/>"); }
char *genWANIPCn(int *len) { return genRootDesc(len); }
char *genWANCfg(int *len) { return genRootDesc(len); }
void ExecuteSoapAction(struct upnphttp *h, const char *s, int n) {
    (void)s; (void)n;
    assert(h->req_buf[h->req_buflen] == '\0');
    assert(h->req_buflen-h->req_contentoff == h->req_contentlen);
    soap_calls++; h->state=EToDelete;
}
void SoapError(struct upnphttp *h, int code, const char *s) {
    (void)code; (void)s; h->state=EToDelete;
}
static void feed(struct upnphttp *h, int fd, const char *s, int len) {
    assert(write(fd,s,len)==len); Process_upnphttp(h);
}
int main(int argc, char **argv) {
    int fds[2], i, n; char response[1024], header[256];
    char chunk[2048]; struct upnphttp *h;
    assert(argc==2 && socketpair(AF_UNIX,SOCK_STREAM,0,fds)==0);
    h=New_upnphttp(fds[0]); assert(h); memset(chunk,'x',sizeof(chunk));
    if(strcmp(argv[1],"get")==0) {
        const char *q="GET /rootDesc.xml HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n";
        feed(h,fds[1],q,strlen(q));
        n=read(fds[1],response,sizeof(response)-1); assert(n>0); response[n]=0;
        assert(strstr(response,"200 OK") && strstr(response,"<root/>"));
    } else if(strcmp(argv[1],"header_boundary")==0) {
        const char *q="GET /rootDesc.xml HTTP/1.1\r\nX: ";
        int pad=65536-strlen(q)-4;
        feed(h,fds[1],q,strlen(q));
        while(pad>0) { n=pad>(int)sizeof(chunk) ? (int)sizeof(chunk) : pad;
            feed(h,fds[1],chunk,n); pad-=n; }
        for(i=0;i<4;i++) feed(h,fds[1],&"\r\n\r\n"[i],1);
        assert(h->req_contentoff==65536 && h->state==EToDelete);
        n=read(fds[1],response,sizeof(response)-1); assert(n>0); response[n]=0;
        assert(strstr(response,"200 OK"));
    } else if(strcmp(argv[1],"headers")==0) {
        feed(h,fds[1],"GET / HTTP/1.1\r\nX: ",19);
        for(i=0;i<80 && h->state!=EToDelete;i++) feed(h,fds[1],chunk,sizeof(chunk));
        assert(h->state==EToDelete && h->req_buflen<=65536+2048);
        n=read(fds[1],response,sizeof(response)-1); assert(n>0); response[n]=0;
        assert(strstr(response,"HTTP/1.1 400 Bad Request"));
    } else if(strcmp(argv[1],"content_limit")==0) {
        const char *q="POST /ctl/IPConn HTTP/1.1\r\nContent-Length: 1048577\r\n\r\n";
        feed(h,fds[1],q,strlen(q));
        n=read(fds[1],response,sizeof(response)-1); assert(n>0); response[n]=0;
        assert(strstr(response,"413") && soap_calls==0);
    } else if(strcmp(argv[1],"fragmented")==0 || strcmp(argv[1],"max_body")==0) {
        int body=strcmp(argv[1],"max_body")==0 ? 1048576 : 8192;
        int step=body==8192 ? 1 : sizeof(chunk);
        n=snprintf(header,sizeof(header),"POST /ctl/IPConn HTTP/1.1\r\nSOAPAction: x\r\nContent-Length: %d\r\n\r\n",body);
        feed(h,fds[1],header,n);
        assert(h->state==EWaitingForHttpContent);
        for(i=0;i<body;i+=step) feed(h,fds[1],chunk,step);
        assert(soap_calls==1 && allocations<=11);
        printf("body=%d allocations=%d\n",body,allocations);
    } else if(strcmp(argv[1],"no_overread")==0) {
        const char *q="POST /ctl/IPConn HTTP/1.1\r\nSOAPAction: x\r\nContent-Length: 1\r\n\r\n";
        feed(h,fds[1],q,strlen(q)); feed(h,fds[1],"xTRAILING",9);
        assert(soap_calls==1);
        assert(read(fds[0],response,sizeof(response))==8);
    } else if(strcmp(argv[1],"coalesced")==0) {
        const char *q="POST /ctl/IPConn HTTP/1.1\r\nSOAPAction: x\r\nContent-Length: 4\r\n\r\nbody";
        feed(h,fds[1],q,strlen(q)); assert(soap_calls==1);
    } else if(strcmp(argv[1],"allocation_failure")==0) {
        fail_allocation=1; feed(h,fds[1],"GET /",5);
        assert(h->state==EToDelete && h->req_buf==NULL && soap_calls==0);
    } else if(strcmp(argv[1],"body_allocation_failure")==0) {
        const char *q="POST /ctl/IPConn HTTP/1.1\r\nSOAPAction: x\r\nContent-Length: 8192\r\n\r\n";
        feed(h,fds[1],q,strlen(q));
        feed(h,fds[1],chunk,sizeof(chunk));
        fail_allocation=1; feed(h,fds[1],chunk,sizeof(chunk));
        assert(h->state==EToDelete && soap_calls==0 && h->req_buf[h->req_buflen]==0);
    } else { assert(0); }
    close(fds[1]); Delete_upnphttp(h); return 0;
}
'''

class HttpReceiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "config.h").write_text(CONFIG)
        (root / "driver.c").write_text(DRIVER)
        cls.binary = root / "driver"
        subprocess.run([os.environ.get("CC", "clang"), "-g", "-O1",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        "-I", str(root), "-I", str(SOURCE), str(root / "driver.c"),
                        "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_receive_paths(self):
        for scenario in ("get", "header_boundary", "headers", "content_limit", "fragmented", "max_body",
                         "no_overread", "coalesced", "allocation_failure", "body_allocation_failure"):
            with self.subTest(scenario=scenario):
                subprocess.run([str(self.binary), scenario], check=True, timeout=15)

if __name__ == "__main__":
    unittest.main()
