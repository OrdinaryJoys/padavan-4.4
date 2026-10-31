"""Actual DNS logging code and private Unix sockets; no global syslog or daemon."""
from pathlib import Path
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'trunk/user/dnsmasq/dnsmasq-2.93'


class DNSLogBackpressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='k2p-log-code-', dir='/tmp')
        cls.tree = Path(cls.build.name).resolve() / 'source'
        shutil.copytree(SOURCE, cls.tree, ignore=shutil.ignore_patterns(
            '*.o', 'dnsmasq', 'dnsmasq_baseline', '.copts_*'))
        main = cls.tree / 'src/dnsmasq.c'
        text = main.read_text()
        support = r'''
const char *k2p_log_path,*k2p_log_fault;
int k2p_libc_calls,k2p_log_sends,k2p_log_connects,k2p_partial_stage;
int k2p_sleep_count,k2p_sleep_max,k2p_sleep_total;
void k2p_log_state(void);void k2p_log_close(void);
static int k2p_fault(const char *name){return k2p_log_fault&&!strcmp(k2p_log_fault,name);}
void k2p_openlog(const char *name,int flags,int facility){(void)name;(void)flags;(void)facility;}
void k2p_vsyslog(int priority,const char *format,va_list args){
 (void)priority;(void)format;(void)args;k2p_libc_calls++;
 write(STDERR_FILENO,"LIBC_VSYSLOG_CALLED\n",20);
}
static int k2p_stream_connected(int fd){int type;socklen_t size=sizeof(type);
 struct sockaddr_un peer;socklen_t length=sizeof(peer);
 return !getsockopt(fd,SOL_SOCKET,SO_TYPE,&type,&size)&&type==SOCK_STREAM&&
        !getpeername(fd,(struct sockaddr *)&peer,&length);}
static ssize_t k2p_log_result(int fd,const void *data,size_t size,int flags,int sending){
 k2p_log_sends++;
 if(k2p_fault("zero"))return 0;
 if(k2p_fault("interrupt")){errno=EINTR;return -1;}
 if(k2p_fault("permanent")){errno=EIO;return -1;}
 if(k2p_fault("connect-cycle")){errno=ECONNREFUSED;return -1;}
 if(k2p_fault("partial-disconnect")&&k2p_stream_connected(fd)){
  if(!k2p_partial_stage++){if(size>7)size=7;}
  else if(k2p_partial_stage==2){errno=EPIPE;return -1;}}
 return sending?send(fd,data,size,flags):write(fd,data,size);}
ssize_t k2p_log_write(int fd,const void *data,size_t size){return k2p_log_result(fd,data,size,0,0);}
ssize_t k2p_log_send(int fd,const void *data,size_t size,int flags){return k2p_log_result(fd,data,size,flags,1);}
int k2p_log_connect(int fd,const struct sockaddr *address,socklen_t length){
 k2p_log_connects++;
 if(k2p_fault("connect-cycle"))return 0;
 if(k2p_fault("in-progress")){errno=EINPROGRESS;return -1;}
 return connect(fd,address,length);}
int k2p_log_fcntl(int fd,int operation,...){va_list ap;int arg;
 if(operation==F_GETFL||operation==F_GETFD){
  if(k2p_fault("get-flags")&&operation==F_GETFL){errno=EIO;return -1;}
  return fcntl(fd,operation);}
 va_start(ap,operation);arg=va_arg(ap,int);va_end(ap);
 if((k2p_fault("set-flags")&&operation==F_SETFL)||
    (k2p_fault("cloexec")&&operation==F_SETFD)){errno=EIO;return -1;}
 return fcntl(fd,operation,arg);}
int k2p_log_nanosleep(const struct timespec *delay,struct timespec *remaining){
 int ms=(int)(delay->tv_sec*1000+delay->tv_nsec/1000000);
 k2p_sleep_count++;k2p_sleep_total+=ms;if(ms>k2p_sleep_max)k2p_sleep_max=ms;
 return nanosleep(delay,remaining);}
static long long k2p_milliseconds(void){struct timespec now;
 if(clock_gettime(CLOCK_MONOTONIC,&now))return -1;
 return (long long)now.tv_sec*1000+now.tv_nsec/1000000;}
'''
        text = text.replace('#include "dnsmasq.h"', '#include "dnsmasq.h"\n'+support)
        needle = '  read_opts(argc, argv, compile_opts);'
        if text.count(needle) != 1:
            raise AssertionError('logging replay stop point changed')
        replay = r'''
  if(getenv("K2P_LOG_MODE")){
    char payload[800],control;const char *mode=getenv("K2P_LOG_MODE");
    int count=atoi(getenv("K2P_LOG_COUNT"));long long before;
    signal(SIGPIPE,SIG_IGN);memset(payload,'x',sizeof(payload)-1);payload[sizeof(payload)-1]=0;
    log_start(NULL,-1);
    if(!strcmp(mode,"closed"))k2p_log_close();
    for(int i=0;i<count;i++)my_syslog(LOG_INFO,"SEQ=%d %s",i,payload);
    printf("READY\n");k2p_log_state();fflush(stdout);
    if(!strcmp(mode,"recover")||!strcmp(mode,"reconnect")){
      if(read(STDIN_FILENO,&control,1)!=1)return 94;
      check_log_writer(1);my_syslog(LOG_INFO,"RECOVERED %s",payload);
      check_log_writer(1);k2p_log_state();
    }
    if(!strcmp(mode,"flush")){
      printf("BEFORE_FLUSH\n");fflush(stdout);before=k2p_milliseconds();
      flush_log();printf("FLUSH_MS=%lld\n",k2p_milliseconds()-before);k2p_log_state();
    }
    printf("DONE\n");fflush(stdout);return 0;
  }
'''
        text = text.replace(needle, '  k2p_log_path=getenv("K2P_LOG_SOCKET");\n'
                            '  k2p_log_fault=getenv("K2P_LOG_FAULT");\n'+needle+replay)
        main.write_text(text)
        log = cls.tree / 'src/log.c'
        definitions = r'''
extern const char *k2p_log_path;
extern int k2p_libc_calls,k2p_log_sends,k2p_log_connects;
extern int k2p_sleep_count,k2p_sleep_max,k2p_sleep_total;
void k2p_openlog(const char *,int,int);void k2p_vsyslog(int,const char *,va_list);
ssize_t k2p_log_write(int,const void *,size_t);ssize_t k2p_log_send(int,const void *,size_t,int);
int k2p_log_connect(int,const struct sockaddr *,socklen_t);int k2p_log_fcntl(int,int,...);
int k2p_log_nanosleep(const struct timespec *,struct timespec *);
#undef _PATH_LOG
#define _PATH_LOG k2p_log_path
#define openlog k2p_openlog
#define vsyslog k2p_vsyslog
#define write k2p_log_write
#define send k2p_log_send
#define connect k2p_log_connect
#define fcntl k2p_log_fcntl
#define nanosleep k2p_log_nanosleep
'''
        inspect = r'''
void k2p_log_close(void){if(log_fd!=-1)close(log_fd);}
void k2p_log_state(void){int count=0,flags=-1,descriptor=-1;struct log_entry *entry;
 for(entry=entries;entry;entry=entry->next)count++;
 if(log_fd!=-1){flags=fcntl(log_fd,F_GETFL);descriptor=fcntl(log_fd,F_GETFD);}
 printf("STATE queue=%d alloc=%d lost=%d fd=%d nonblock=%d cloexec=%d libc=%d sends=%d connects=%d sleeps=%d sleepmax=%d sleeptotal=%d\n",
  count,entries_alloced,entries_lost,log_fd,flags!=-1&&!!(flags&O_NONBLOCK),
  descriptor!=-1&&!!(descriptor&FD_CLOEXEC),k2p_libc_calls,k2p_log_sends,k2p_log_connects,
  k2p_sleep_count,k2p_sleep_max,k2p_sleep_total);
}
'''
        log.write_text(log.read_text().replace('#include "runtime_file.h"',
                                               '#include "runtime_file.h"\n'+definitions)+inspect)
        options='-DNO_DHCP6 -DNO_TFTP -DNO_INOTIFY -DNO_AUTH -DNO_LOOP'
        built=subprocess.run(['make','-j4','CC=clang','COPTS='+options,
                              'CFLAGS=-O1 -g -Wall -Wextra -fsanitize=address,undefined',
                              'LDFLAGS=-fsanitize=address,undefined'],cwd=cls.tree,
                             capture_output=True,text=True)
        if built.returncode:raise AssertionError(built.stdout+built.stderr)
        cls.binary=cls.tree/'src/dnsmasq'

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='k2p-log-',dir='/tmp')
        self.base=Path(self.temp.name).resolve();self.path=self.base/'syslog'
        self.config=self.base/'config';self.sockets=[];self.processes=[]
        self.env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'}

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.communicate(timeout=2)
        for stream in self.sockets:stream.close()
        self.temp.cleanup()

    def server(self,kind=socket.SOCK_DGRAM):
        stream=socket.socket(socket.AF_UNIX,kind)
        stream.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
        stream.bind(str(self.path));stream.settimeout(0.1)
        if kind==socket.SOCK_STREAM:stream.listen(8)
        self.sockets.append(stream);return stream

    def start(self,mode='normal',count=1,async_limit=None,fault='',file=None,bad_config=False):
        text='port=0\nno-hosts\nno-resolv\n'
        if async_limit is not None:text+='log-async='+str(async_limit)+'\n'
        if file is not None:text+='log-facility='+str(file)+'\n'
        if bad_config:text+='PUBLIC_BAD_DIRECTIVE\n'
        self.config.write_text(text)
        env={**self.env,'K2P_LOG_SOCKET':str(self.path),'K2P_LOG_MODE':mode,
             'K2P_LOG_COUNT':str(count),'K2P_LOG_FAULT':fault}
        process=subprocess.Popen([str(self.binary),'-C',str(self.config)],env=env,
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,text=True,start_new_session=True)
        self.processes.append(process);return process

    def finish(self,process,expect=0,input=None):
        try:out,err=process.communicate(input=input,timeout=4)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.communicate(timeout=2)
            self.fail('actual logging code blocked')
        self.assertEqual(process.returncode,expect,err+out)
        self.assertNotIn('AddressSanitizer',err);self.assertNotIn('runtime error:',err)
        return out,err

    @staticmethod
    def states(output):
        return [dict((k,int(v)) for k,v in re.findall(r'(\w+)=(-?\d+)',line))
                for line in output.splitlines() if line.startswith('STATE ')]

    def drain(self,stream):
        data=[]
        while True:
            try:data.append(stream.recv(4096))
            except socket.timeout:return data

    def test_default_socket_has_checked_nonblocking_and_cloexec(self):
        stream=self.server();out,err=self.finish(self.start(count=1))
        state=self.states(out)[0];self.assertEqual((state['nonblock'],state['cloexec'],state['libc']),(1,1,0))
        messages=self.drain(stream);self.assertEqual(len(messages),1)
        self.assertRegex(messages[0],rb'^<\d+>');self.assertIn(b'SEQ=0 ',messages[0]);self.assertNotIn(b'\0',messages[0])

    def test_default_backpressure_retains_one_and_drops_bounded(self):
        self.server();out,_=self.finish(self.start(count=1000))
        state=self.states(out)[0];self.assertEqual(state['queue'],1);self.assertEqual(state['alloc'],1)
        self.assertGreater(state['lost'],0);self.assertEqual(state['libc'],0)
        self.assertEqual(state['sleeps'],0)

    def test_async_queue_cap_survives_backpressure(self):
        for limit in (5,100):
            with self.subTest(limit=limit):
                stream=self.server();out,_=self.finish(self.start(count=1000,async_limit=limit))
                state=self.states(out)[0]
                self.assertEqual((state['queue'],state['alloc']),(limit,limit))
                self.assertGreater(state['lost'],0);self.assertEqual(state['libc'],0)
                self.assertGreater(state['sleeps'],0);self.assertLessEqual(state['sleepmax'],128)
                self.assertLessEqual(state['sleeptotal'],256)
                stream.close();self.path.unlink()

    def test_healthy_async_logging_keeps_every_record(self):
        stream=self.server();out,_=self.finish(self.start(count=4,async_limit=5))
        state=self.states(out)[0]
        self.assertEqual((state['queue'],state['lost'],state['libc']),(0,0,0))
        messages=self.drain(stream);self.assertEqual(len(messages),4)
        for index,message in enumerate(messages):self.assertIn(('SEQ=%d '%index).encode(),message)

    def test_busy_flush_runs_its_real_bounded_budget(self):
        self.server(socket.SOCK_STREAM)
        out,_=self.finish(self.start(mode='flush',count=10000,async_limit=5))
        elapsed=int(re.search(r'FLUSH_MS=(\d+)',out)[1]);self.assertGreaterEqual(elapsed,175);self.assertLess(elapsed,1500)
        self.assertEqual(self.states(out)[-1]['fd'],-1)

    def test_default_unread_stream_never_blocks(self):
        self.server(socket.SOCK_STREAM)
        out,_=self.finish(self.start(count=10000))
        state=self.states(out)[0]
        self.assertEqual((state['queue'],state['alloc'],state['nonblock'],state['cloexec']),(1,1,1,1))
        self.assertGreater(state['lost'],0)

    def ready(self,process):
        # The actual logging loop must reach its handshake without a receiver
        # draining it. communicate() cannot be used until the recovery control.
        import select
        ready,_,_=select.select([process.stdout],[],[],3)
        self.assertTrue(ready,'logging blocked before the private recovery handshake')
        self.assertEqual(process.stdout.readline(),'READY\n')
        return 'READY\n'+process.stdout.readline()

    def test_default_queue_recovers_and_reports_bounded_loss(self):
        stream=self.server();process=self.start(mode='recover',count=1000)
        before=self.ready(process);old=self.drain(stream)
        self.assertGreater(self.states(before)[0]['lost'],0)
        after,_=self.finish(process,input='x');wire=b'\n'.join(old+self.drain(stream))
        self.assertEqual(self.states(after)[-1]['queue'],0)
        self.assertEqual(self.states(after)[-1]['lost'],0)
        self.assertIn(b'overflow: ',wire);self.assertIn(b'RECOVERED ',wire)

    def test_datagram_logger_restart_recovers(self):
        stream=self.server();process=self.start(mode='reconnect',count=1)
        self.ready(process);self.assertIn(b'SEQ=0 ',stream.recv(4096))
        stream.close();self.path.unlink();replacement=self.server()
        after,_=self.finish(process,input='x')
        self.assertIn(b'RECOVERED ',b'\n'.join(self.drain(replacement)))
        self.assertEqual(self.states(after)[-1]['queue'],0)

    def test_default_stream_queue_recovers_after_eagain(self):
        server=self.server(socket.SOCK_STREAM)
        process=self.start(mode='recover',count=10000)
        before=self.ready(process);self.assertEqual(self.states(before)[0]['queue'],1)
        peer,_=server.accept();self.sockets.append(peer);peer.settimeout(.1)
        while True:
            try:
                if not peer.recv(8192):break
            except socket.timeout:break
        after,_=self.finish(process,input='x');payload=b''
        while True:
            data=peer.recv(8192)
            if not data:break
            payload+=data
        self.assertIn(b'RECOVERED ',payload);self.assertIn(b'overflow: ',payload)
        self.assertEqual((self.states(after)[-1]['queue'],self.states(after)[-1]['lost']),(0,0))

    def stream_records(self,fault=''):
        server=self.server(socket.SOCK_STREAM);chunks=[];stop=threading.Event()
        def receive():
            while not stop.is_set():
                try:client,_=server.accept()
                except socket.timeout:continue
                with client:
                    client.settimeout(.1);payload=b''
                    while not stop.is_set():
                        try:data=client.recv(4096)
                        except socket.timeout:continue
                        if not data:break
                        payload+=data
                    chunks.append(payload)
        worker=threading.Thread(target=receive);worker.start()
        try:
            out,err=self.finish(self.start(count=1,fault=fault))
            # Process exit closes each connection; allow the owned reader to
            # consume EOF before ending it. There are no arbitrary sleeps.
            deadline=time.monotonic()+1
            expected=2 if fault else 1
            while len(chunks)<expected and time.monotonic()<deadline:
                stop.wait(.005)
            return out,err,chunks
        finally:
            stop.set();worker.join(2)
            self.assertFalse(worker.is_alive(),'private stream receiver did not exit')

    def test_healthy_stream_preserves_record_terminator(self):
        out,_,chunks=self.stream_records()
        self.assertEqual(self.states(out)[0]['queue'],0)
        self.assertEqual(len(chunks),1)
        self.assertRegex(chunks[0],rb'^<\d+>');self.assertIn(b'SEQ=0 ',chunks[0])
        self.assertTrue(chunks[0].endswith(b'\0'))

    def test_partial_stream_disconnect_restarts_the_whole_record(self):
        out,_,chunks=self.stream_records('partial-disconnect')
        self.assertEqual(self.states(out)[0]['queue'],0)
        self.assertEqual(len(chunks),2)
        self.assertEqual(len(chunks[0]),7)
        self.assertRegex(chunks[1],rb'^<\d+>');self.assertIn(b'SEQ=0 ',chunks[1])
        self.assertTrue(chunks[1].endswith(b'\0'))

    def test_zero_and_interrupted_writes_do_not_spin(self):
        self.server()
        for fault in ('zero','interrupt','connect-cycle','in-progress'):
            with self.subTest(fault=fault):
                out,_=self.finish(self.start(count=1,fault=fault))
                self.assertIn('DONE',out);self.assertEqual(self.states(out)[0]['libc'],0)
                self.assertLessEqual(self.states(out)[0]['sends'],128)

    def test_permanent_error_never_falls_back_to_libc(self):
        self.server();out,err=self.finish(self.start(count=1,fault='permanent'))
        self.assertEqual(self.states(out)[0]['libc'],0);self.assertNotIn('LIBC_VSYSLOG',err)

    def test_closed_descriptor_never_falls_back_to_libc(self):
        self.server();out,err=self.finish(self.start(mode='closed',count=1))
        self.assertEqual(self.states(out)[0]['libc'],0);self.assertNotIn('LIBC_VSYSLOG',err)

    def test_socket_flag_failures_are_checked_and_fallback_is_bounded(self):
        self.server()
        for fault in ('get-flags','set-flags','cloexec'):
            with self.subTest(fault=fault):
                _,err=self.finish(self.start(count=1,fault=fault),expect=3)
                self.assertNotIn('LIBC_VSYSLOG',err)

    def test_missing_socket_and_startup_failure_are_bounded(self):
        out,err=self.finish(self.start(count=3));self.assertNotIn('LIBC_VSYSLOG',err)
        self.assertEqual(self.states(out)[0]['libc'],0)
        _,err=self.finish(self.start(bad_config=True),expect=1)
        self.assertNotIn('LIBC_VSYSLOG',err)

    def test_early_parse_failure_uses_the_private_nonblocking_fallback(self):
        stream=self.server()
        _,err=self.finish(self.start(bad_config=True),expect=1)
        messages=self.drain(stream)
        self.assertNotIn('LIBC_VSYSLOG',err)
        self.assertTrue(any(b'bad option' in message for message in messages))
        self.assertTrue(any(b'FAILED to start up' in message for message in messages))

    def test_healthy_file_and_null_policies_remain_supported(self):
        path=self.base/'regular.log';out,_=self.finish(self.start(count=2,file=path))
        self.assertIn('SEQ=0 ',path.read_text());self.assertIn('SEQ=1 ',path.read_text())
        self.assertEqual(self.states(out)[0]['libc'],0)
        self.finish(self.start(count=2,file='/dev/null'))


if __name__=='__main__':unittest.main()
