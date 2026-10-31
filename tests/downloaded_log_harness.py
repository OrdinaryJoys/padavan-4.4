"""Pure locked-source generator for isolated central logger component probes.

The caller supplies already patched archive text plus exact current source/header.
It performs no IO, subprocess, daemon, network, or device actions. The generated
program alone is executed in explicit test isolation by the callers.
"""
import json
import re

def function(text, name):
    match = re.search(r'(?:static\s+)?(?:void|int|ssize_t|char\s*\*|FILE\s*\*)\s*\n?\b' + name + r'\s*\(', text)
    if not match:
        raise ValueError(name)
    start = match.start()
    opening = text.index('{', match.end())
    depth = 0
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*|[{}]')
    for item in token.finditer(text, opening):
        if item.group() == '{':
            depth += 1
        elif item.group() == '}':
            depth -= 1
            if not depth:
                return text[start:item.end()]
    raise ValueError(name)


def generate_source(inputs, endpoint):
    code = '#define _GNU_SOURCE\n#define PADAVAN_LOG_SOCKET ' + json.dumps(endpoint) + '\n'
    code += inputs['header'] + '\n'
    code += r'''
#include <stdlib.h>
#include <stdbool.h>
typedef enum { SYSLOG_LEVEL_QUIET, SYSLOG_LEVEL_FATAL, SYSLOG_LEVEL_ERROR,
 SYSLOG_LEVEL_INFO, SYSLOG_LEVEL_VERBOSE, SYSLOG_LEVEL_DEBUG1,
 SYSLOG_LEVEL_DEBUG2, SYSLOG_LEVEL_DEBUG3 } LogLevel;
typedef void (log_handler_fn)(LogLevel,int,const char*,void*);
static struct padavan_log_context padavan_ssh_log = PADAVAN_LOG_CONTEXT_INIT;
static struct padavan_log_context padavan_vpn_log = PADAVAN_LOG_CONTEXT_INIT;
static LogLevel log_level=SYSLOG_LEVEL_INFO;
static int log_on_stderr,log_stderr_fd=2;
static int log_facility=LOG_AUTH;
static const char *argv0="ssh-adapter",*__progname="ssh-adapter";
static log_handler_fn *log_handler;
static void *log_handler_ctx;
#define MSGBUFSIZ 1024
#define LOG_STDERR_VIS 0
#define LOG_SYSLOG_VIS 0
/* Inert ASCII quoting compatibility: queue/format transport is under test,
 * not upstream visual escaping. Production retains the complete strnvis. */
static size_t fixture_copy(char *out,const char *in,size_t size) {
 size_t len=strlen(in);if(size){size_t n=len<size-1?len:size-1;memcpy(out,in,n);out[n]=0;}return len;
}
#ifdef strlcpy
#undef strlcpy
#endif
#define strlcpy fixture_copy
static int strnvis(char*out,const char*in,size_t size,int flags){(void)flags;return (int)fixture_copy(out,in,size);}
'''
    code += function(inputs['openssh'], 'do_log')
    code += r'''
static void ssh_entry(LogLevel level,int force,const char *fmt,...) {
 va_list ap;va_start(ap,fmt);do_log(level,force,NULL,fmt,ap);va_end(ap);
}
#define SYSLOG_CAPABILITY 1
#define LOG_OPENVPN LOG_DAEMON
#define PACKAGE "openvpn"
static FILE *msgfp;
static bool std_redir,use_syslog;
static char *pgmname_syslog;
static int null_calls;
static char *string_alloc(const char *text,void *arena){(void)arena;return strdup(text);}
static void set_std_files_to_null(bool socket){(void)socket;null_calls++;}
'''
    code += function(inputs['openvpn'], 'open_syslog')
    code += function(inputs['openvpn'], 'close_syslog')
    expression = inputs['openvpn'].split('            padavan_log_write(', 1)[1].split(');', 1)[0]
    code += 'static void vpn_emit(const char *message) { int level=LOG_NOTICE; const char *prefix="client", *prefix_sep=" ", *m1=message; padavan_log_write(' + expression + '); }\n'
    code += r'''
#include <assert.h>
static struct padavan_log_context udpxy_log = PADAVAN_LOG_CONTEXT_INIT;
static struct padavan_log_context l2tp_syslog = PADAVAN_LOG_CONTEXT_INIT;
static struct padavan_log_context lanauth_log = PADAVAN_LOG_CONTEXT_INIT;
static struct padavan_log_context iapp_syslog = PADAVAN_LOG_CONTEXT_INIT;
static struct padavan_log_context smartdns_config_log = PADAVAN_LOG_CONTEXT_INIT;
/* Explicit file/tlog destinations remain separate; these callbacks are inert. */
static int tmfprintf(FILE *fp,const char *fmt,...){(void)fp;(void)fmt;return 0;}
static struct {int syslog;} gconfig = {1};
static int syslog_nesting;
#define BINARY "xl2tpd"
struct call { int error, result, needclose; char errormsg[256]; };
#define RESULT_ERROR 2
'''
    util = inputs['udpxy_util']
    for name in ('udpxy_openlog', 'udpxy_closelog', 'udpxy_syslog', 'mperror'):
        code += function(util, name)
    misc = inputs['xl2tpd_misc']
    macro = misc.split('#define SYSLOG_CALL(code)', 1)[1].split('\nvoid init_log', 1)[0]
    code += '\n#define SYSLOG_CALL(code)' + macro + '\n'
    for name in ('init_log', 'close_log', 'l2tp_log', 'set_error'):
        code += function(misc, name)
    code += function(inputs['iapp'], 'iapp_log')
    # fatal's exit is a normal process exit, confined to this test child.
    code += function(inputs['lanauth'], 'fatal')
    code += r'''
#define CONF_RET_ERR 1
#define CONF_RET_WARN 2
#define TLOG_ERROR 1
#define TLOG_WARN 2
#define tlog(...) ((void)0)
static int _config_item[1], config_before, config_after;
static void _dns_conf_load_pre(void){config_before++;}
static void _dns_conf_load_post(void){config_after++;}
static int load_conf(const char *file,const void *items,int (*callback)(const char*,int,int))
{(void)items;return callback(file,13,CONF_RET_ERR);}
'''
    for name in ('_conf_printf', 'dns_server_load_conf'):
        code += function(inputs['smartdns'], name)
    code += r'''
int main(int argc,char **argv) {
 int i,repeat,mode; if(argc!=4)return 90;mode=atoi(argv[1]);repeat=atoi(argv[2]);
 if(padavan_log_mask(&padavan_ssh_log,0)!=0xff)return 94;
 if(mode==1||mode==3){open_syslog("vpn-adapter",true);open_syslog("ignored-second-open",true);}
 if(mode==6)udpxy_openlog("udpxy",LOG_PID,LOG_LOCAL0);
 if(mode==8)padavan_log_open(&iapp_syslog,"iappd",LOG_PID,LOG_DAEMON);
 if(mode==9)padavan_log_open(&lanauth_log,"lanauth",LOG_PID,LOG_DAEMON);
 for(i=0;i<repeat;i++) {
  errno=EDOM;
  if(mode==1||mode==3)vpn_emit(argv[3]);
  else if(mode==2)ssh_entry(SYSLOG_LEVEL_DEBUG1,0,"%s",argv[3]);
  else if(mode==4)ssh_entry(SYSLOG_LEVEL_ERROR,0,"%s",argv[3]);
  else if(mode==5)ssh_entry(SYSLOG_LEVEL_DEBUG1,1,"%s",argv[3]);
  else if(mode==6)mperror(NULL,EDOM,"%s",argv[3]);
  else if(mode==7)l2tp_log(LOG_WARNING,"%s",argv[3]);
  else if(mode==8)iapp_log(LOG_WARNING,"%s",argv[3]);
  else if(mode==9)fatal("%s",argv[3]);
  else if(mode==10){if(dns_server_load_conf(argv[3])!=-1||config_before!=i+1||config_after!=i+1)return 93;}
  else if(mode==11){
   struct call call;size_t length=strlen(argv[3]);
   memset(&call,0,sizeof(call));set_error(&call,7,"%s",argv[3]);
   if(length>=sizeof(call.errormsg))length=sizeof(call.errormsg)-1;
   if(length&&argv[3][length-1]=='\n')length--;
   if(call.error!=7||call.result!=RESULT_ERROR||call.needclose!=-1||
      strlen(call.errormsg)!=length||memcmp(call.errormsg,argv[3],length))return 95;
  }
  else ssh_entry(SYSLOG_LEVEL_INFO,0,"%s",argv[3]);
  if(errno!=EDOM)return 91;
 }
 if(mode==1||mode==3){close_syslog();if(use_syslog||pgmname_syslog)return 92;}
 if(mode==6)udpxy_closelog();
 if(mode==7)close_log();
 printf("{\"null_calls\":%d}\n",null_calls);
 return 0;
}
'''
    return code
