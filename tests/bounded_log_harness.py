"""Pure actual-source logging replay shared by native and MIPS inert probes.

It never starts a service, interface, listener, routing or kernel-log reader.
Only a selected central producer is invoked. Namespace/UID ownership and real
socket backpressure are the caller's responsibility, not this generated main.
"""
import json
import re
import io
import tarfile
from pathlib import Path

SOURCE_PATHS = {
    'common': 'trunk/user/shared/bounded_syslog.h',
    'busybox': 'trunk/user/busybox/busybox-1.24.x/libbb/bounded_syslog.c',
    'busybox_info': 'trunk/user/busybox/busybox-1.24.x/libbb/info_msg.c',
    'busybox_error': 'trunk/user/busybox/busybox-1.24.x/libbb/verror_msg.c',
    'miniupnpd': 'trunk/user/miniupnpd/miniupnpd-2.x/boundedlog.c',
    'igmp': 'trunk/user/igmpproxy/igmpproxy-0.1/src/syslog.c',
    'lldt': 'trunk/user/lldt/src/util.c',
    'pppd': 'trunk/user/pppd/pppd/utils.c',
    'pptpd': 'trunk/user/poptop/pptpd-1.4.0/our_syslog.h',
}
INADYN_SOURCE_PATHS = {
    'archive': 'trunk/user/inadyn/inadyn-2.8.1.tar.xz',
    'vendor_patch': 'trunk/user/inadyn/inadyn-2.8.1.patch',
    'bounded_patch': 'trunk/user/inadyn/inadyn-bounded-log.patch',
}


def patched_inadyn_source(archive, vendor_patch, bounded_patch):
    if re.search(r'^\+\+\+\s+\S*src/log\.c(?:\s|$)', vendor_patch, re.M):
        raise ValueError('Vendor patch now changes inadyn logger; review before replay')
    with tarfile.open(fileobj=io.BytesIO(archive)) as package:
        member = package.getmember('inadyn-2.8.1/src/log.c')
        if not member.isfile() or member.size > 65536:
            raise ValueError('inadyn logger is not a bounded regular archive member')
        old = package.extractfile(member).read().decode().splitlines(True)
    lines = bounded_patch.splitlines(True)
    if lines[:2] != ['--- a/src/log.c\n', '+++ b/src/log.c\n']:
        raise ValueError('Require exactly the known inadyn logger patch path')
    result, cursor, index = [], 0, 2
    while index < len(lines):
        match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[index])
        if not match:
            raise ValueError('Unsupported inadyn patch hunk')
        start, consumed, produced = int(match[1])-1, 0, 0
        if not cursor <= start <= len(old):
            raise ValueError('inadyn hunk order/extent changed')
        result.extend(old[cursor:start]); cursor = start; index += 1
        if len(result) != int(match[3])-1:
            raise ValueError('inadyn new hunk position changed')
        while index < len(lines) and not lines[index].startswith('@@ '):
            line = lines[index]; index += 1
            if line[:1] not in (' ', '+', '-'):
                raise ValueError('Invalid inadyn patch line')
            if line[0] in ' -':
                if cursor >= len(old) or old[cursor] != line[1:]:
                    raise ValueError('inadyn patch context changed')
                cursor += 1; consumed += 1
            if line[0] in ' +':
                result.append(line[1:]); produced += 1
        if consumed != int(match[2] or 1) or produced != int(match[4] or 1):
            raise ValueError('inadyn patch line counts changed')
    result.extend(old[cursor:])
    return ''.join(result)


def read_source_inputs(repository):
    repository = Path(repository)
    result = {key:(repository/path).read_text() for key,path in SOURCE_PATHS.items()}
    result['inadyn'] = patched_inadyn_source(
        (repository/INADYN_SOURCE_PATHS['archive']).read_bytes(),
        (repository/INADYN_SOURCE_PATHS['vendor_patch']).read_text(),
        (repository/INADYN_SOURCE_PATHS['bounded_patch']).read_text())
    return result


def mask(text):
    return re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*',
                  lambda item: ' ' * len(item.group()), text)


def function(text, name):
    # The final alternative accommodates this tree's original K&R log_write.
    pattern = r'(?:static\s+)?(?:void|int)\s+(?:FAST_FUNC\s+)?' + re.escape(name) + r'\s*\([^;{}]*\)(?:\s|\b(?:int|char)\b[^{}]*;)*\s*\{'
    masked = mask(text)
    matches = list(re.finditer(pattern, masked))
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous actual producer function: ' + name)
    begin = matches[0].start()
    opening = masked.index('{', begin)
    depth = 0
    for item in re.finditer(r'[{}]', masked[opening:]):
        depth += 1 if item.group() == '{' else -1
        if depth == 0:
            return text[begin:opening + item.end()]
    raise ValueError('Unterminated producer function: ' + name)


def declaration(text, value):
    if text.count(value) != 1:
        raise ValueError('Producer context declaration changed: ' + value)
    return value


def without_includes(text):
    return re.sub(r'^\s*#\s*include[^\n]*\n', '\n', text, flags=re.M)


def generate_source(inputs, socket_path='/dev/log', console_path='/dev/console'):
    if set(inputs) != set(SOURCE_PATHS) | {'inadyn'}:
        raise ValueError('Require the exact actual producer source set')
    prefix = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <syslog.h>
#define FAST_FUNC
#define ENABLE_FEATURE_SYSLOG 1
typedef signed char smallint;
typedef int bool_t;
#define TRUE 1
#ifndef INTERNAL_NOPRI
#define INTERNAL_NOPRI 0x10
#endif
enum { LOGMODE_NONE=0, LOGMODE_STDIO=1, LOGMODE_SYSLOG=2, LOGMODE_BOTH=3 };
const char *applet_name="logging-fixture";
const char *g_Progname="lld2d";
int log_to_fd=-1,debug=0;
static void fflush_all(void) { (void)fflush(NULL); }
static ssize_t full_write(int fd,const void *bytes,size_t length) { return write(fd,bytes,length); }
static void xfunc_die(void) { exit(77); }
'''
    prefix += '#define PADAVAN_LOG_SOCKET ' + json.dumps(str(socket_path)) + '\n'
    prefix += '#define PADAVAN_LOG_CONSOLE ' + json.dumps(str(console_path)) + '\n'
    parts = [prefix, inputs['common']]
    for key in ('busybox', 'busybox_error', 'busybox_info', 'miniupnpd', 'igmp'):
        parts.append(without_includes(inputs[key]))
    text = inputs['lldt']
    parts.extend((declaration(text, 'static bool_t use_syslog;'),
                  declaration(text, 'static struct padavan_log_context lldt_log_context = PADAVAN_LOG_CONTEXT_INIT;')))
    parts.extend(function(text, name) for name in ('util_use_syslog', 'warn', 'die'))
    text = inputs['pppd']
    parts.append(declaration(text, 'static struct padavan_log_context ppp_log_context = PADAVAN_LOG_CONTEXT_INIT;'))
    parts.extend(function(text, name) for name in ('ppp_log_open', 'ppp_log_close', 'ppp_log_mask', 'ppp_syslog', 'log_write'))
    parts.append(without_includes(inputs['pptpd']))
    parts.append('struct padavan_log_context pptpd_log_context = PADAVAN_LOG_CONTEXT_INIT;')
    text = inputs['inadyn']
    parts.extend((declaration(text, 'static struct padavan_log_context inadyn_log_context = PADAVAN_LOG_CONTEXT_INIT;'),
                  declaration(text, 'static int level   = LOG_NOTICE;'),
                  declaration(text, 'static int enabled = 0;')))
    parts.extend(function(text, name) for name in ('log_init', 'log_exit', 'vlogit', 'logit'))
    parts.append(r'''
int main(int argc,char **argv) {
 const char *component=argc>1?argv[1]:"header";
 const char *mode=argc>3?argv[3]:"normal";
 int count=argc>2?atoi(argv[2]):1,i,saved;
 char payload[4096],line[4608];
 struct padavan_log_context direct=PADAVAN_LOG_CONTEXT_INIT;
 if(count<0||count>20000)return 90;
 memset(payload,'x',sizeof(payload)-1);payload[sizeof(payload)-1]=0;
 if(strcmp(mode,"long"))payload[70]=0;
 if(!strcmp(component,"busybox")) {bb_openlog("busybox-probe",LOG_PID,LOG_DAEMON);logmode=LOGMODE_SYSLOG;}
 else if(!strcmp(component,"miniupnpd"))miniupnpd_openlog("miniupnpd",LOG_PID|LOG_CONS,LOG_DAEMON);
 else if(!strcmp(component,"igmp")) {igmp_log_open();LogLevel=LOG_DEBUG;}
 else if(!strcmp(component,"lldt"))util_use_syslog();
 else if(!strcmp(component,"pppd"))ppp_log_open("pppd",LOG_PID|LOG_NDELAY,LOG_LOCAL2);
 else if(!strcmp(component,"pptpd")) {pptpd_openlog("pptpd",LOG_PID,LOG_DAEMON);(void)pptpd_setlogmask(0);}
 else if(!strcmp(component,"inadyn"))log_init("inadyn",1,1);
 else if(!strcmp(component,"header"))padavan_log_open(&direct,"header-probe",LOG_PID,LOG_LOCAL3);
 else return 91;
 errno=EACCES;
 for(i=0;i<count;i++) {
  snprintf(line,sizeof(line),"PUBLIC seq=%d %s",i,payload);
  saved=errno;
  if(!strcmp(component,"busybox"))bb_info_msg("%s",line);
  else if(!strcmp(component,"miniupnpd"))miniupnpd_syslog(LOG_WARNING,"%s",line);
  else if(!strcmp(component,"igmp"))my_log(LOG_WARNING,!strcmp(mode,"long")?EINVAL:0,"%s",line);
  else if(!strcmp(component,"lldt"))warn("%s",line);
  else if(!strcmp(component,"pppd"))log_write(LOG_WARNING,line);
  else if(!strcmp(component,"pptpd"))pptpd_syslog(LOG_WARNING,"%s",line);
  else if(!strcmp(component,"inadyn"))logit(LOG_WARNING,"%s",line);
  else padavan_log_write(&direct,LOG_WARNING,"%s",line);
  if(errno!=saved)return 92;
 }
 if(!strcmp(component,"pptpd"))pptpd_closelog();
 printf("PRODUCER component=%s count=%d errno=%d\n",component,count,errno);
 return 0;
}
''')
    return '\n'.join(parts)
