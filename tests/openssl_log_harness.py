"""Pinned OpenSSL Unix BIO/app logging bodies; inert BIO scaffolding, real private socket IO."""
from pathlib import Path
import hashlib
import json
import re
import tempfile
import subprocess
from bounded_log_harness import function

SOURCE_PATHS={'legacy_libc':'trunk/libc/uClibc-ng-1.0.38/libc/misc/syslog/syslog.c','header':'trunk/user/shared/bounded_syslog.h','makefile':'trunk/libs/libssl/Makefile','patch':'trunk/libs/libssl/openssl-bounded-log.patch'}
TARGETS=('crypto/bio/bss_log.c','apps/include/log.h','apps/lib/log.c','apps/lib/http_server.c','apps/ocsp.c')
for name in TARGETS:SOURCE_PATHS[name]='tests/fixtures/openssl-log-sources/'+Path(name).name

def read_inputs(root):return {key:(root/path).read_text() for key,path in SOURCE_PATHS.items()}
def patched_sources(inputs):
 patch=inputs['patch'];expected=list(TARGETS)
 if re.findall(r'^--- a/(.+)$',patch,re.M)!=expected or re.findall(r'^\+\+\+ b/(.+)$',patch,re.M)!=expected:raise ValueError('Unexpected OpenSSL patch targets')
 with tempfile.TemporaryDirectory(prefix='k2p-openssl-patch-')as td:
  base=Path(td)
  for name in TARGETS:
   path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(inputs[name])
  r=subprocess.run(['patch','-p1','--force','--forward','--fuzz=0'],input=patch,text=True,cwd=base,capture_output=True)
  if r.returncode:raise ValueError('Locked OpenSSL patch did not apply: '+r.stdout+r.stderr)
  return {name:(base/name).read_text() for name in TARGETS}

PREFIX=r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>
#include <syslog.h>
static size_t alloc_calls,free_calls,max_alloc,fail_at;
static void *fixture_malloc(size_t n){void*p;alloc_calls++;if(alloc_calls==fail_at)return NULL;if(n>max_alloc)max_alloc=n;p=malloc(n);return p;}
static void *fixture_zalloc(size_t n){void*p=fixture_malloc(n);if(p)memset(p,0,n);return p;}
static void fixture_free(void*p){if(p)free_calls++;free(p);}
#define OPENSSL_malloc fixture_malloc
#define OPENSSL_zalloc fixture_zalloc
#define OPENSSL_free fixture_free
#define BIO_TYPE_MEM 1
#define BIO_CTRL_SET 4
#define BIO_snprintf snprintf
typedef struct bio_st BIO;
struct bio_st { int init,num; void *ptr; };
typedef struct bio_method_st {
 int type;const char*name;
 int(*write_ex)(BIO*,const char*,size_t,size_t*);int(*write)(BIO*,const char*,int);
 int(*read_ex)(BIO*,char*,size_t,size_t*);int(*read)(BIO*,char*,int);
 int(*puts)(BIO*,const char*);int(*gets)(BIO*,char*,int);
 long(*ctrl)(BIO*,int,long,void*);int(*create)(BIO*);int(*destroy)(BIO*);long(*callback)(BIO*,int,void*);
} BIO_METHOD;
static int bwrite_conv(BIO*b,const char*s,size_t n,size_t*out){(void)b;(void)s;(void)n;(void)out;return 0;}
'''
DRIVER=r'''
static void *thread_write(void*p){BIO*b=p;int i;for(i=0;i<16;i++)if(slg_write(b,"WARNING THREAD",14)!=14)return(void*)1;return NULL;}
int main(int argc,char**argv){
 BIO a={0},b={0};const char*mode=argc>1?argv[1]:"bio";int accepted=0,st=0;size_t n=0;char *payload=NULL;
 (void)fixture_zalloc;(void)padavan_log_open;(void)padavan_log_write;(void)padavan_log_mask;(void)padavan_log_close;
 if(!strcmp(mode,"fail-create")){fail_at=1;accepted=slg_new(&a);slg_free(&a);printf("RESULT accepted=%d alloc=%zu free=%zu max=%zu init=%d\n",accepted,alloc_calls,free_calls,max_alloc,a.init);return accepted?91:0;}
 if(!slg_new(&a)||!slg_new(&b))return 90;
 slg_ctrl(&a,BIO_CTRL_SET,LOG_LOCAL3,"bio-a");slg_ctrl(&b,BIO_CTRL_SET,LOG_LOCAL4,"bio-b");
 if(!strcmp(mode,"dual")){accepted=slg_write(&a,"WARNING ONE",11);accepted+=slg_write(&b,"INFO TWO",8);accepted+=slg_write(&a,"WARNING THREE",13);}
 else if(!strcmp(mode,"long")){n=1024*1024;payload=malloc(n);memset(payload,'x',n);memcpy(payload,"INFO ",5);accepted=slg_write(&a,payload,(int)n);free(payload);}
 else if(!strcmp(mode,"negative"))accepted=slg_write(&a,NULL,-1);
 else if(!strcmp(mode,"null"))accepted=slg_write(&a,NULL,1);
 else if(!strcmp(mode,"empty"))accepted=slg_write(&a,NULL,0);
 else if(!strcmp(mode,"embedded")){const char data[]={'I','N','F','O',' ','A',0,'S','E','C','R','E','T'};accepted=slg_write(&a,data,sizeof(data));}
 else if(!strcmp(mode,"fail-ctrl")){fail_at=alloc_calls+1;slg_ctrl(&a,BIO_CTRL_SET,LOG_LOCAL3,"failed");accepted=slg_write(&a,"WARNING LOST",12);fail_at=0;slg_ctrl(&a,BIO_CTRL_SET,LOG_LOCAL3,"recovered");accepted+=slg_write(&a,"WARNING BACK",12);}
 else if(!strcmp(mode,"thread")){pthread_t ta,tb;void*ra,*rb;pthread_create(&ta,NULL,thread_write,&a);pthread_create(&tb,NULL,thread_write,&b);pthread_join(ta,&ra);pthread_join(tb,&rb);if(ra||rb)return 93;accepted=32;}
 else if(!strcmp(mode,"fork")){pid_t p=fork();if(p<0)return 94;if(!p){slg_ctrl(&a,BIO_CTRL_SET,LOG_LOCAL5,"child");slg_write(&a,"WARNING CHILD",13);slg_free(&a);slg_free(&b);_exit(0);}if(waitpid(p,&st,0)!=p||st)return 95;accepted=slg_write(&a,"WARNING PARENT",14);}
 else if(!strcmp(mode,"transport-errno")){errno=EDOM;xsyslog(&a,LOG_WARNING,"ERRNO");if(errno!=EDOM)return 98;accepted=1;}
 else if(!strcmp(mode,"app")){ossl_app_log_open("openssl-fixture",LOG_PID,LOG_DAEMON);errno=EDOM;ossl_app_log_write(LOG_INFO,"index file changed, reloading %%n");if(errno!=EDOM)return 96;accepted=1;}
 else {int i,count=argc>2?atoi(argv[2]):1;if(count<0||count>2000)return 97;for(i=0;i<count;i++)accepted+=slg_write(&a,"WARNING literal %n %s %%",24);}
 slg_free(&a);slg_free(&b);
 printf("RESULT accepted=%d alloc=%zu free=%zu max=%zu init=%d\n",accepted,alloc_calls,free_calls,max_alloc,a.init);return 0;
}
'''

def generate_source(inputs,endpoint,legacy=False):
 sources={name:inputs[name] for name in TARGETS} if legacy else patched_sources(inputs)
 bio=re.sub(r'^#include[^\n]*\n','',sources['crypto/bio/bss_log.c'],flags=re.M)
 if legacy:
  # Keep original BIO + full real uClibc logging functions. Only mutex/ABI
  # glue, the private endpoint and a small socket send buffer are adapted.
  # This remains a native replay, never host /dev/log or target libc execution.
  pre=PREFIX+'\nstatic struct padavan_log_context app_log_context=PADAVAN_LOG_CONTEXT_INIT;\n'
 else:pre=PREFIX+'\n#define PADAVAN_OPENSSL_BOUNDED_LOG 1\n'
 header='#define PADAVAN_LOG_SOCKET '+json.dumps(endpoint)+'\n#define PADAVAN_LOG_CONSOLE '+json.dumps(endpoint+'.console')+'\n'+inputs['header']+'\n'
 if legacy:
  libc=inputs['legacy_libc'].replace('#include <bits/uClibc_mutex.h>','')
  address='static const struct sockaddr_un SyslogAddr = { .sun_family = AF_UNIX, .sun_path = '+json.dumps(endpoint)+' };'
  libc,n=re.subn(r'static const struct sockaddr SyslogAddr = \{.*?\n\};',lambda _:address,libc,count=1,flags=re.S)
  if n!=1:raise ValueError('Missing exact legacy syslog private address')
  libc=libc.replace('static const char truncate_msg[12] =', 'static const char truncate_msg[12] FIXTURE_NONSTRING =')
  libc=libc.replace('connect(fd, &SyslogAddr, sizeof(SyslogAddr))','connect(fd, (const struct sockaddr *)&SyslogAddr, sizeof(SyslogAddr))')
  adapter=r'''
#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif
#define __USE_BSD 1
#if defined(__GNUC__) && !defined(__clang__)
#define FIXTURE_NONSTRING __attribute__((nonstring))
#else
#define FIXTURE_NONSTRING
#endif
typedef unsigned char smalluint;
#define __UCLIBC_MUTEX_STATIC(n,v) static pthread_mutex_t n=v
#define __UCLIBC_MUTEX_LOCK(n) ((void)pthread_mutex_lock(&(n)))
#define __UCLIBC_MUTEX_UNLOCK(n) ((void)pthread_mutex_unlock(&(n)))
#define __set_errno(v) (errno=(v))
#define libc_hidden_def(n)
#define strong_alias(a,b)
static int fixture_libc_socket(int family,int kind,int protocol){int fd=socket(family,kind,protocol);int limit=4096;if(fd>=0)(void)setsockopt(fd,SOL_SOCKET,SO_SNDBUF,&limit,sizeof(limit));return fd;}
static ssize_t fixture_libc_send(int fd,const void*data,size_t size,int flags){struct pollfd p={fd,POLLOUT,0};if(poll(&p,1,0)==0)fprintf(stderr,"LEGACY_STREAM_BACKPRESSURE nonblock=%d\n",!!(fcntl(fd,F_GETFL)&O_NONBLOCK));return send(fd,data,size,flags);}
#define socket fixture_libc_socket
#define send fixture_libc_send
#define openlog fixture_openlog
#define closelog fixture_closelog
#define syslog fixture_syslog
#define setlogmask fixture_setlogmask
'''
  adapter+='#include <paths.h>\n#undef _PATH_CONSOLE\n#define _PATH_CONSOLE '+json.dumps(endpoint+'.console')+'\n'+'#if defined(__APPLE__) && defined(__clang__)\n#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wdeprecated-declarations"\n#endif\n'+libc+'\n#if defined(__APPLE__) && defined(__clang__)\n#pragma clang diagnostic pop\n#endif\n#undef socket\n#undef send\n'
  app='''static void ossl_app_log_open(const char*n,int o,int f){fixture_openlog(n,o,f);}
static void ossl_app_log_write(int p,const char*f,...){(void)p;(void)f;}
'''
  return PREFIX+header+adapter+bio+app+DRIVER
 app=sources['apps/lib/log.c'];names=('ossl_app_log_open','ossl_app_log_vwrite','ossl_app_log_write')
 functions='\n'.join(function(app,name) for name in names)
 return pre+header+'\nstatic struct padavan_log_context app_log_context=PADAVAN_LOG_CONTEXT_INIT;\n'+functions+'\n'+bio+DRIVER
