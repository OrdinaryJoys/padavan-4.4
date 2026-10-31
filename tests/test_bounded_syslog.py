"""Real header and central producers, private Unix sockets, ASan/UBSan only."""
from pathlib import Path
import errno
import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import unittest

from bounded_log_harness import generate_source, read_source_inputs

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT/'trunk/user/shared/bounded_syslog.h'

API_DRIVER = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
static const char *fault;
static int sockets,sends,closes,nonblock,cloexec,perror_writes,console_writes,console_fd=-1;
static int matches(const char *s){return fault&&!strcmp(fault,s);}
static int probe_socket(int domain,int kind,int protocol){
 sockets++;if(matches("socket")){errno=EMFILE;return -1;}return socket(domain,kind,protocol);}
static int probe_fcntl(int fd,int op,...){int arg;va_list ap;
 if((matches("getfl")&&op==F_GETFL)||(matches("getfd")&&op==F_GETFD)||
    (matches("setfl")&&op==F_SETFL)||(matches("setfd")&&op==F_SETFD)){errno=EIO;return -1;}
 if(op==F_GETFL||op==F_GETFD)return fcntl(fd,op);
 va_start(ap,op);arg=va_arg(ap,int);va_end(ap);return fcntl(fd,op,arg);}
static ssize_t probe_sendto(int fd,const void *bytes,size_t length,int flags,const struct sockaddr *to,socklen_t size){
 sends++;nonblock=!!(fcntl(fd,F_GETFL)&O_NONBLOCK);cloexec=!!(fcntl(fd,F_GETFD)&FD_CLOEXEC);
 if(matches("again")){errno=EAGAIN;return -1;}if(matches("interrupt")){errno=EINTR;return -1;}
 if(matches("permanent")){errno=EIO;return -1;}if(matches("zero"))return 0;
 return sendto(fd,bytes,length,flags,to,size);}
static int probe_close(int fd){closes++;return close(fd);}
static int probe_open(const char *path,int flags,...){
 (void)path;console_fd=open("/dev/null",flags);return console_fd;}
static ssize_t probe_write(int fd,const void *bytes,size_t length){
 if(fd==STDERR_FILENO)perror_writes++;else if(fd==console_fd)console_writes++;
 return write(fd,bytes,length);}
#define socket probe_socket
#define fcntl probe_fcntl
#define sendto probe_sendto
#define close probe_close
#define open probe_open
#define write probe_write
__HEADER_INCLUDE__
#undef socket
#undef fcntl
#undef sendto
#undef close
#undef open
#undef write
int main(int argc,char **argv){
 struct padavan_log_context c=PADAVAN_LOG_CONTEXT_INIT;
 const char *mode=argc>1?argv[1]:"normal";char payload[4096],ident[1024];int i,old=0;
 fault=argc>2?argv[2]:"";memset(payload,'x',sizeof(payload)-1);payload[sizeof(payload)-1]=0;
 padavan_log_open(&c,"api-probe",LOG_PID,LOG_LOCAL3);errno=EACCES;
 if(!strcmp(mode,"facility")){
  padavan_log_open(&c,NULL,0,LOG_KERN);padavan_log_write(&c,LOG_NOTICE,"KERNEL");
  padavan_log_write(&c,LOG_LOCAL1|LOG_ERR,"OVERRIDE");
 }else if(!strcmp(mode,"mask")){
  old=padavan_log_mask(&c,0);padavan_log_mask(&c,LOG_UPTO(LOG_ERR));
  padavan_log_write(&c,LOG_WARNING,"FILTERED");padavan_log_write(&c,LOG_ERR,"KEPT");
 }else if(!strcmp(mode,"close")){
  padavan_log_mask(&c,LOG_UPTO(LOG_ERR));padavan_log_close(&c);padavan_log_write(&c,LOG_WARNING,"RESET");
 }else if(!strcmp(mode,"format")){
  char reference[128];const char errno_format[]={'%','m',0};
  errno=ENOENT;snprintf(reference,sizeof(reference),errno_format);
  padavan_log_write(&c,LOG_WARNING,"percent=%% value=%d failure=%m",7);
  printf("HOST_ERRNO_TEXT=%s\n",reference);
 }else if(!strcmp(mode,"perror")){
  padavan_log_open(&c,NULL,LOG_PID|LOG_PERROR,LOG_LOCAL3);padavan_log_write(&c,LOG_WARNING,"STDERR-BODY");
 }else if(!strcmp(mode,"console")){
  padavan_log_open(&c,NULL,LOG_CONS,LOG_LOCAL3);padavan_log_write(&c,LOG_WARNING,"CONSOLE-BODY");
 }else if(!strcmp(mode,"long"))padavan_log_write(&c,LOG_WARNING,"%s",payload);
 else if(!strcmp(mode,"owned-ident")){
  char *s=strdup("owned-name");padavan_log_open(&c,s,0,LOG_LOCAL3);memset(s,'z',strlen(s));free(s);
  padavan_log_open(&c,NULL,0,LOG_LOCAL3);padavan_log_write(&c,LOG_WARNING,"OWNED");
 }else if(!strcmp(mode,"alias-ident")){
  padavan_log_open(&c,"abcdef",0,LOG_LOCAL3);padavan_log_open(&c,c.ident+2,0,LOG_LOCAL3);padavan_log_write(&c,LOG_WARNING,"ALIAS");
 }else if(!strcmp(mode,"long-ident")||!strcmp(mode,"unterminated-ident")){
  memset(ident,'q',sizeof(ident));if(!strcmp(mode,"long-ident"))ident[sizeof(ident)-1]=0;
  padavan_log_open(&c,ident,0,LOG_LOCAL3);padavan_log_write(&c,LOG_WARNING,"IDENT-LIMIT");
 }else if(!strcmp(mode,"bad-priority"))padavan_log_write(&c,0x40000000,"INVALID");
 else if(!strcmp(mode,"flood"))for(i=0;i<10000;i++)padavan_log_write(&c,LOG_WARNING,"PUBLIC %d %s",i,payload);
 else padavan_log_write(&c,LOG_WARNING,"NORMAL");
 printf("STATE errno=%d sockets=%d sends=%d closes=%d nonblock=%d cloexec=%d perror=%d console=%d oldmask=%d\n",
   errno,sockets,sends,closes,nonblock,cloexec,perror_writes,console_writes,old);
 return 0;
}
'''


class BoundedSyslogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-bounded-log-',dir='/tmp')
        cls.base=Path(cls.temp.name).resolve();cls.path=cls.base/'syslog'
        inputs=read_source_inputs(ROOT)
        (cls.base/'producer.c').write_text(generate_source(inputs,str(cls.path),str(cls.base/'console')))
        api=API_DRIVER.replace('__HEADER_INCLUDE__','#include '+json.dumps(str(HEADER)))
        (cls.base/'api.c').write_text(api)
        for name in ('api','producer'):
            command=['clang','-std=gnu99','-O1','-g','-Wall','-Wextra','-fsanitize=address,undefined',
                     '-DPADAVAN_LOG_SOCKET='+json.dumps(str(cls.path)),str(cls.base/(name+'.c')),'-o',str(cls.base/name)]
            built=subprocess.run(command,capture_output=True,text=True)
            if built.returncode:raise AssertionError(built.stdout+built.stderr)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.peer=None
        self.env={**os.environ,'ASAN_OPTIONS':'symbolize=0:detect_leaks=0'}

    def tearDown(self):
        if self.peer:self.peer.close()
        if self.path.exists():self.path.unlink()

    def server(self):
        self.peer=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        self.peer.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
        self.peer.bind(str(self.path));self.peer.settimeout(.05)

    def drain(self):
        messages=[]
        if self.peer:
            while True:
                try:messages.append(self.peer.recv(4096))
                except socket.timeout:break
        return messages

    def run_binary(self,name,*args):
        proc=subprocess.Popen([str(self.base/name),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              text=True,env=self.env,start_new_session=True)
        try:out,err=proc.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL);proc.communicate(timeout=2);self.fail('logging producer blocked')
        self.assertEqual(proc.returncode,0,out+err)
        self.assertNotIn('AddressSanitizer',err);self.assertNotIn('runtime error:',err)
        return out,err

    def api(self,mode='normal',fault=''):
        out,err=self.run_binary('api',mode,fault)
        state={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',out)}
        match=re.search(r'^HOST_ERRNO_TEXT=(.*)$',out,re.M)
        if match:state['errno_text']=match[1]
        return state,err

    def test_healthy_framing_and_checked_socket_flags(self):
        self.server();state,_=self.api();wire=self.drain()
        self.assertEqual(len(wire),1);self.assertTrue(wire[0].startswith(b'<156>'))
        self.assertTrue(wire[0].endswith(b'\0'));self.assertRegex(wire[0],rb'api-probe\[\d+\]: NORMAL\0$')
        self.assertEqual((state['nonblock'],state['cloexec'],state['closes'],state['errno']),(1,1,1,errno.EACCES))

    def test_facility_zero_and_explicit_override(self):
        self.server();state,_=self.api('facility');wire=self.drain()
        self.assertEqual(len(wire),2);self.assertTrue(wire[0].startswith(b'<5>'));self.assertTrue(wire[1].startswith(b'<139>'))
        self.assertEqual(state['errno'],errno.EACCES)

    def test_mask_query_and_priority_filter(self):
        self.server();state,_=self.api('mask');wire=self.drain()
        self.assertEqual(state['oldmask'],255);self.assertEqual(len(wire),1)
        self.assertIn(b'KEPT',wire[0]);self.assertNotIn(b'FILTERED',wire[0])

    def test_close_restores_default_context(self):
        self.server();_,_=self.api('close');wire=self.drain()
        self.assertEqual(len(wire),1);self.assertTrue(wire[0].startswith(b'<12>'))
        self.assertTrue(wire[0].endswith(b'syslog: RESET\0'))

    def test_percent_data_errno_extension_and_errno_preservation(self):
        self.server();state,_=self.api('format');wire=self.drain()[0]
        # Preserve the native printf backend, including width/precision/%%m
        # semantics. Darwin lacks GNU %m; the actual uClibc MIPS gate checks
        # expanded strerror text instead of claiming that native limitation
        # proves the target extension.
        self.assertIn(('percent=% value=7 failure='+state['errno_text']).encode(),wire)
        self.assertEqual(state['errno'],errno.ENOENT)

    def test_identifier_is_owned_and_null_open_preserves_it(self):
        self.server();self.api('owned-ident');self.assertIn(b'owned-name: OWNED',self.drain()[0])

    def test_identifier_alias_copy_is_safe(self):
        self.server();self.api('alias-ident');self.assertIn(b'cdef: ALIAS',self.drain()[0])

    def test_long_and_unterminated_identifier_are_bounded(self):
        self.server()
        for mode in ('long-ident','unterminated-ident'):
            self.api(mode);self.assertIn(b'[identifier too long]: IDENT-LIMIT',self.drain()[0])

    def test_long_message_has_bounded_frame_and_marker(self):
        self.server();self.api('long');wire=self.drain()[0]
        self.assertLessEqual(len(wire),1024);self.assertTrue(wire.endswith(b'\0'));self.assertIn(b'[truncated]',wire)

    def test_invalid_priority_never_opens_a_socket(self):
        self.server();state,_=self.api('bad-priority')
        self.assertEqual((state['sockets'],state['sends']),(0,0));self.assertEqual(self.drain(),[])

    def test_socket_and_every_descriptor_flag_failure_are_checked(self):
        self.server()
        for fault in ('socket','getfl','setfl','getfd','setfd'):
            with self.subTest(fault=fault):
                state,_=self.api(fault=fault)
                self.assertEqual(state['sends'],0);self.assertEqual(state['errno'],errno.EACCES)
                self.assertEqual(state['closes'],0 if fault=='socket' else 1)
        self.assertEqual(self.drain(),[])

    def test_send_failure_zero_and_interrupt_never_retry(self):
        self.server()
        for fault in ('again','interrupt','permanent','zero'):
            with self.subTest(fault=fault):
                state,_=self.api(fault=fault)
                self.assertEqual((state['sends'],state['closes'],state['errno']),(1,1,errno.EACCES))

    def test_perror_preserves_explicit_stderr_output(self):
        self.server();state,err=self.api('perror')
        self.assertRegex(err,r'^api-probe\[\d+\]: STDERR-BODY\n$')
        self.assertEqual(state['perror'],1);self.assertEqual(len(self.drain()),1)

    def test_cons_uses_one_checked_nonblocking_character_write(self):
        state,_=self.api('console','again')
        self.assertEqual(state['console'],1);self.assertEqual(state['errno'],errno.EACCES)

    def test_full_queue_is_bounded_and_later_process_recovers(self):
        self.server();state,_=self.api('flood')
        self.assertEqual((state['sends'],state['closes'],state['errno']),(10000,10000,errno.EACCES))
        self.assertGreater(len(self.drain()),0)
        self.api();self.assertIn(b'NORMAL',self.drain()[0])

    def test_missing_receiver_and_restart_are_bounded(self):
        state,_=self.api();self.assertEqual(state['errno'],errno.EACCES)
        self.server();self.api();self.assertIn(b'NORMAL',self.drain()[0])

    def test_actual_eight_central_producers_preserve_messages(self):
        self.server()
        for component in ('header','busybox','miniupnpd','igmp','lldt','pppd','pptpd','inadyn'):
            with self.subTest(component=component):
                out,_=self.run_binary('producer',component,'1','normal')
                self.assertIn('count=1',out);wire=self.drain();self.assertEqual(len(wire),1)
                self.assertIn(b'PUBLIC seq=0',wire[0]);self.assertTrue(wire[0].endswith(b'\0'))

    def test_actual_producers_remain_bounded_with_unread_queue(self):
        self.server()
        for component in ('busybox','miniupnpd','igmp','lldt','pppd','pptpd','inadyn'):
            with self.subTest(component=component):
                out,_=self.run_binary('producer',component,'2000','normal')
                self.assertIn('count=2000',out);self.assertGreater(len(self.drain()),0)

    def test_actual_igmp_long_errno_append_has_no_overflow(self):
        self.server();out,_=self.run_binary('producer','igmp','1','long')
        self.assertIn('count=1',out);wire=self.drain();self.assertEqual(len(wire),1)
        self.assertLess(len(wire[0]),256)

    def test_actual_pptpd_ctrlpacket_translation_unit_compiles_links_and_logs(self):
        # Compile the complete consumer TU with the production HAVE_SYSLOG_H
        # branch selected. The central-adapter fixture above cannot establish
        # that every separate consumer has included its component declarations.
        folder=ROOT/'trunk/user/poptop/pptpd-1.4.0'
        source=folder/'ctrlpacket.c'
        fixed=self.base/'ctrlpacket-fixed.c'
        fixed.write_text(source.read_text())
        command=['clang','-std=gnu99','-O1','-g','-DHAVE_SYSLOG_H=1','-DHAVE_STRERROR=1',
                 '-Werror=implicit-function-declaration','-fsanitize=address,undefined',
                 '-I'+str(folder),'-DPADAVAN_LOG_SOCKET='+json.dumps(str(self.path))]
        object_path=self.base/'ctrlpacket.o'
        built=subprocess.run(command+['-c',str(fixed),'-o',str(object_path)],capture_output=True,text=True)
        self.assertEqual(built.returncode,0,built.stdout+built.stderr)
        driver=self.base/'ctrlpacket-driver.c'
        driver.write_text('#include <stdint.h>\n#include '+json.dumps(str(folder/'our_syslog.h'))+r'''
struct padavan_log_context pptpd_log_context=PADAVAN_LOG_CONTEXT_INIT;
int pptpctrl_debug=0;
uint16_t unique_call_id=0;
extern ssize_t send_pptp_packet(int,void *,size_t);
int main(void)
{
    char packet='x';
    pptpd_openlog("pptpd-ctrlpacket-probe",LOG_PID,LOG_DAEMON);
    if(send_pptp_packet(-1,&packet,1)!=-1 || errno!=EBADF) return 1;
    return 0;
}
''')
        linked=subprocess.run(command+[str(driver),str(object_path),'-o',str(self.base/'ctrlpacket')],
                              capture_output=True,text=True)
        self.assertEqual(linked.returncode,0,linked.stdout+linked.stderr)
        self.server();self.run_binary('ctrlpacket')
        wire=self.drain();self.assertEqual(len(wire),1)
        self.assertTrue(wire[0].startswith(b'<27>'))
        self.assertIn(b"CTRL: Couldn't write packet to client.",wire[0])
        # Recreate the missing-include regression, not an unrelated syntax
        # error: on a host with syslog.h the old conditional hides our API.
        broken=self.base/'ctrlpacket-old-conditional.c'
        broken.write_text(source.read_text().replace('#include "our_syslog.h"',
            '#if HAVE_SYSLOG_H\n#include <syslog.h>\n#else\n#include "our_syslog.h"\n#endif',1))
        rejected=subprocess.run(command+['-c',str(broken),'-o',str(self.base/'ctrlpacket-broken.o')],
                                capture_output=True,text=True)
        self.assertNotEqual(rejected.returncode,0,'old consumer unexpectedly compiled')
        self.assertRegex(rejected.stderr,
                         r"error: (?:call to undeclared function|implicit declaration of function) 'pptpd_syslog'")


if __name__=='__main__':unittest.main()
