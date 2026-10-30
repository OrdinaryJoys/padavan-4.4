#!/usr/bin/env python3
"""Actual receive/send/list/select helpers under deterministic monotonic time."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_miniupnp_http_limits import CONFIG, DRIVER, SOURCE

CLOCK = r'''
#include <time.h>
#ifdef __linux__
#include <sys/sysinfo.h>
#endif
static time_t fake_now=1000;
static int fail_clock,fail_nonblock,fail_malloc;
static void *checked_malloc(size_t n) { if(fail_malloc) {fail_malloc=0;return NULL;} return malloc(n); }
#ifdef __linux__
static int fake_sysinfo(struct sysinfo *info) {
    if(fail_clock) return -1;
    memset(info,0,sizeof(*info));info->uptime=fake_now;return 0;
}
#define sysinfo(info) fake_sysinfo(info)
#else
static int fake_clock(clockid_t id,struct timespec *now) {
    (void)id;if(fail_clock) return -1;now->tv_sec=fake_now;now->tv_nsec=0;return 0;
}
#define clock_gettime(id,now) fake_clock(id,now)
#endif
#define malloc checked_malloc
'''
SCENARIOS = r'''
    } else if(strcmp(argv[1],"connection_limit")==0) {
        struct upnphttp *items[UPNPHTTP_MAX_CONNECTIONS],*replacement;
        int peers[UPNPHTTP_MAX_CONNECTIONS],extra[2];
        items[0]=h;peers[0]=fds[1];
        for(i=1;i<(int)UPNPHTTP_MAX_CONNECTIONS;i++) {
            int pair[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0);
            items[i]=New_upnphttp(pair[0]);peers[i]=pair[1];assert(items[i]);
        }
        assert(http_connection_count==UPNPHTTP_MAX_CONNECTIONS);
        assert(socketpair(AF_UNIX,SOCK_STREAM,0,extra)==0);
        assert(New_upnphttp(extra[0])==NULL);
        Delete_upnphttp(items[1]);close(peers[1]);
        replacement=New_upnphttp(extra[0]);assert(replacement);
        assert(http_connection_count==UPNPHTTP_MAX_CONNECTIONS);
        Delete_upnphttp(replacement);close(extra[1]);
        for(i=2;i<(int)UPNPHTTP_MAX_CONNECTIONS;i++) {Delete_upnphttp(items[i]);close(peers[i]);}
    } else if(strcmp(argv[1],"high_fd")==0) {
        assert(New_upnphttp(FD_SETSIZE)==NULL && http_connection_count==1);
    } else if(strcmp(argv[1],"constructor_failures")==0) {
        int pair[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0);
        fail_nonblock=1;assert(New_upnphttp(pair[0])==NULL);fail_nonblock=0;
        fail_malloc=1;assert(New_upnphttp(pair[0])==NULL);
        fail_clock=1;assert(New_upnphttp(pair[0])==NULL);fail_clock=0;
        assert(http_connection_count==1 && http_buffer_bytes==0);
        close(pair[0]);close(pair[1]);
    } else if(strcmp(argv[1],"request_aggregate")==0 || strcmp(argv[1],"response_aggregate")==0) {
        struct upnphttp *items[4];int peers[4];size_t used;
        items[0]=h;peers[0]=fds[1];
        for(i=1;i<4;i++) {int pair[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0);items[i]=New_upnphttp(pair[0]);peers[i]=pair[1];assert(items[i]);}
        for(i=0;i<3;i++) {
            if(strcmp(argv[1],"request_aggregate")==0) assert(http_resize(items[i],0,1024*1024));
            else assert(BuildHeader_upnphttp(items[i],200,"OK",1024*1024)==0);
        }
        used=http_buffer_bytes;
        assert(!http_resize(items[3],0,1024*1024+1));
        assert(http_buffer_bytes==used && items[3]->req_buf==NULL);
        Delete_upnphttp(items[1]);close(peers[1]);
        assert(http_resize(items[3],0,1024*1024+1));
        assert(http_buffer_bytes<=UPNPHTTP_BUFFER_LIMIT);
        Delete_upnphttp(items[2]);Delete_upnphttp(items[3]);close(peers[2]);close(peers[3]);
    } else if(strcmp(argv[1],"realloc_peak")==0) {
        struct upnphttp *other;int pair[2];size_t used;char *original;
        assert(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0);other=New_upnphttp(pair[0]);assert(other);
        assert(http_resize(h,0,1024*1024));assert(http_resize(other,1,2*1024*1024));
        used=http_buffer_bytes;original=h->req_buf;
        assert(!http_resize(h,0,1024*1024+65536));
        assert(http_buffer_bytes==used && h->req_buf==original && h->req_bufalloc==1024*1024);
        Delete_upnphttp(other);close(pair[1]);
    } else if(strcmp(argv[1],"response_allocation_failure")==0) {
        size_t used;char *original;
        assert(BuildHeader_upnphttp(h,200,"OK",4096)==0);
        used=http_buffer_bytes;original=h->res_buf;fail_allocation=1;
        assert(BuildHeader_upnphttp(h,200,"OK",8192)<0);
        assert(h->res_buf==original && http_buffer_bytes==used && h->res_buflen==0);
    } else if(strcmp(argv[1],"invalid_response_lengths")==0) {
        assert(BuildHeader_upnphttp(h,200,"OK",-1)<0);
        assert(http_buffer_bytes==0);
        assert(BuildHeader_upnphttp(h,200,"OK",INT_MAX)<0);
        assert(http_buffer_bytes==0);
    } else if(strcmp(argv[1],"idle_timeout")==0 || strcmp(argv[1],"clock_failure")==0) {
        struct httplisthead head;fd_set reads,writes;int maximum=-1;struct timeval timeout={600,0};
        LIST_INIT(&head);LIST_INSERT_HEAD(&head,h,entries);FD_ZERO(&reads);FD_ZERO(&writes);
        fake_now=1009;
        assert(Prepare_upnphttp_fds(&head,&reads,&writes,&maximum,&timeout)==1);
        assert(timeout.tv_sec==1 && timeout.tv_usec==0 && FD_ISSET(h->socket,&reads));
        if(strcmp(argv[1],"clock_failure")==0) fail_clock=1;else fake_now=1010;
        Process_upnphttp_fds(&head,&reads,&writes);
        assert(head.lh_first==NULL && http_connection_count==0);h=NULL;
    } else if(strcmp(argv[1],"absolute_timeout")==0 || strcmp(argv[1],"ready_at_deadline")==0) {
        struct httplisthead head;fd_set reads,writes;int maximum=-1;struct timeval timeout={600,0},poll={0,0};
        LIST_INIT(&head);LIST_INSERT_HEAD(&head,h,entries);FD_ZERO(&reads);FD_ZERO(&writes);
        if(strcmp(argv[1],"absolute_timeout")==0) {
            fake_now=1009;feed(h,fds[1],"GET /rootDesc.xml HTTP/1.1\r\nX: ",strlen("GET /rootDesc.xml HTTP/1.1\r\nX: "));
            fake_now=1018;feed(h,fds[1],"x",1);fake_now=1027;feed(h,fds[1],"x",1);
            fake_now=1029;feed(h,fds[1],"x",1);
            assert(h->last_io_at==1029 && h->accepted_at==1000);
        } else fake_now=1009;
        assert(Prepare_upnphttp_fds(&head,&reads,&writes,&maximum,&timeout)==1);
        assert(timeout.tv_sec==1);
        if(strcmp(argv[1],"ready_at_deadline")==0) {
            const char *q="GET /rootDesc.xml HTTP/1.1\r\n\r\n";assert(write(fds[1],q,strlen(q))==(ssize_t)strlen(q));
            assert(select(maximum+1,&reads,&writes,NULL,&poll)>0);fake_now=1010;
        } else fake_now=1030;
        Process_upnphttp_fds(&head,&reads,&writes);
        assert(head.lh_first==NULL && http_buffer_bytes==0);h=NULL;
        assert(read(fds[1],response,sizeof(response))<=0);
    } else if(strcmp(argv[1],"sending_timeout")==0) {
        struct httplisthead head;fd_set reads,writes;int maximum=-1,small=4096;struct timeval timeout={600,0};char *body=calloc(1,1024*1024);
        assert(body);setsockopt(h->socket,SOL_SOCKET,SO_SNDBUF,&small,sizeof(small));
        BuildResp2_upnphttp(h,200,"OK",body,1024*1024);free(body);
        SendRespAndClose_upnphttp(h);assert(h->state==ESendingAndClosing);
        LIST_INIT(&head);LIST_INSERT_HEAD(&head,h,entries);FD_ZERO(&reads);FD_ZERO(&writes);
        assert(Prepare_upnphttp_fds(&head,&reads,&writes,&maximum,&timeout)==1);
        assert(FD_ISSET(h->socket,&writes));fake_now=1010;
        Process_upnphttp_fds(&head,&reads,&writes);
        assert(head.lh_first==NULL && http_buffer_bytes==0);h=NULL;
    } else if(strcmp(argv[1],"continue_writable")==0) {
        struct httplisthead head;fd_set reads,writes;int maximum=-1;struct timeval timeout={600,0},poll={0,0};
        assert(BuildHeader_upnphttp(h,100,"Continue",0)==0);h->state=ESendingContinue;
        LIST_INIT(&head);LIST_INSERT_HEAD(&head,h,entries);FD_ZERO(&reads);FD_ZERO(&writes);
        assert(Prepare_upnphttp_fds(&head,&reads,&writes,&maximum,&timeout)==1);
        assert(FD_ISSET(h->socket,&writes) && !FD_ISSET(h->socket,&reads));
        assert(select(maximum+1,&reads,&writes,NULL,&poll)>0);
        Process_upnphttp_fds(&head,&reads,&writes);assert(h->state==EWaitingForHttpContent);
        LIST_REMOVE(h,entries);
    } else if(strcmp(argv[1],"completed_cleanup")==0) {
        struct httplisthead head;fd_set reads,writes;int maximum=-1;struct timeval timeout={600,0};
        assert(http_resize(h,0,4096) && http_resize(h,1,8192));h->state=EToDelete;
        LIST_INIT(&head);LIST_INSERT_HEAD(&head,h,entries);FD_ZERO(&reads);FD_ZERO(&writes);
        assert(Prepare_upnphttp_fds(&head,&reads,&writes,&maximum,&timeout)==0);
        assert(head.lh_first==NULL && http_buffer_bytes==0 && http_connection_count==0);h=NULL;
'''

class GlobalHttpLimits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();root=Path(cls.tmp.name)
        driver=DRIVER.replace('#define realloc test_realloc',CLOCK+'\n#define realloc test_realloc',1)
        driver=driver.replace('#undef realloc','#undef realloc\n#undef malloc',1)
        driver=driver.replace('return fcntl(fd,F_SETFL,O_NONBLOCK) == 0;','return !fail_nonblock && fcntl(fd,F_SETFL,O_NONBLOCK) == 0;',1)
        driver=driver.replace('    } else { assert(0); }',SCENARIOS+'    } else { assert(0); }',1)
        driver=driver.replace('Delete_upnphttp(h); return 0;','Delete_upnphttp(h); assert(http_connection_count==0 && http_buffer_bytes==0); return 0;',1)
        (root/'config.h').write_text(CONFIG);(root/'driver.c').write_text(driver);cls.binary=root/'driver'
        subprocess.run([os.environ.get('CC','clang'),'-g','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root),'-I',str(SOURCE),str(root/'driver.c'),'-o',str(cls.binary)],check=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_global_limits_and_real_select_helpers(self):
        for scenario in ['connection_limit','high_fd','constructor_failures','request_aggregate','response_aggregate','realloc_peak','response_allocation_failure','invalid_response_lengths','idle_timeout','absolute_timeout','ready_at_deadline','sending_timeout','continue_writable','completed_cleanup','clock_failure']:
            with self.subTest(scenario=scenario):subprocess.run([str(self.binary),scenario],check=True,timeout=15)

if __name__=='__main__':unittest.main()
