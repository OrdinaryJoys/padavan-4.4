"""Pure actual flash/consumer composition, with inert hardware/exec effects.

Only fixture callback boundaries are observed; actual C function bodies are
inserted unchanged. A fixed old source fixture proves the rejected tail.
"""
import ast
import hashlib
import json
from pathlib import PurePosixPath
import re

SOURCE_PATHS = {
    'rc': 'trunk/user/rc/rc.c',
    'watchdog': 'trunk/user/rc/watchdog.c',
    'guard': 'trunk/user/shared/upgrade_guard.h',
    'notify': 'trunk/user/shared/notify_rc.c',
    'notify_header': 'trunk/user/shared/notify_rc.h',
    'upgrade_fixture': 'tests/upgrade_gate_harness.py',
    'old_consumer': 'tests/fixtures/resident-consumer/d67-handle-notifications.c',
}
FUNCTIONS = {
    'rc': ('handle_notifications', 'flash_firmware', 'firmware_upgrade_run',
           'firmware_upgrade_signal_inhibited'),
    'notify': ('valid_event_name', 'rc_notification_open_dir', 'rc_notification_valid_marker'),
}
OLD_CONSUMER_SHA256 = '7b98552bbeb4b7dda0176c7194da0697060bcd58d7da2b858971c2f09b8b9742'


def extract(text, name):
    match = re.search(r'(?:static\s+)?(?:void|int|ssize_t|char\s*\*|FILE\s*\*)\s*\n?\b' + name + r'\s*\(', text)
    if not match:
        raise ValueError(name)
    opening = text.index('{', match.end())
    depth = 0
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*|[{}]')
    for item in token.finditer(text, opening):
        if item.group() == '{':
            depth += 1
        elif item.group() == '}':
            depth -= 1
            if not depth:
                return text[match.start():item.end()]
    raise ValueError(name)


def actual_functions(texts):
    return {name: {'source_key': key, 'body': extract(texts[key], name)}
            for key, names in FUNCTIONS.items() for name in names}


def generate_source(texts, fixture_root, owner_uid=0):
    if set(texts) != set(SOURCE_PATHS) or type(owner_uid) is not int or not 0 <= owner_uid < 2**32:
        raise ValueError('Exact source and owner required')
    if type(fixture_root) is not str or not fixture_root.startswith('/') or any(ord(c) < 32 or ord(c) > 126 for c in fixture_root):
        raise ValueError('Absolute ASCII fixture required')
    old = extract(texts['old_consumer'], 'handle_notifications')
    if hashlib.sha256(old.encode()).hexdigest() != OLD_CONSUMER_SHA256:
        raise ValueError('Fixed old actual consumer binding')
    tree = ast.parse(texts['upgrade_fixture'])
    functions = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'FUNCTIONS' for t in n.targets))
    generator = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate')
    by_path = {path: texts[key] for key, path in SOURCE_PATHS.items()}
    scope = {'json': json, 'function': extract, 'FUNCTIONS': functions,
             'source': lambda path: by_path[path]}
    exec(compile(ast.Module(body=[generator], type_ignores=[]), '<locked pure core>', 'exec'), scope)
    core = scope['generate'](PurePosixPath(fixture_root)).split('static void json_array', 1)[0]
    log_callback = 'static void logmessage(const char*tag,const char*fmt,...){'
    if core.count(log_callback) != 1:
        raise ValueError('Known inert log observer required')
    core = core.replace(log_callback, 'static void observe(int index);\n' + log_callback + 'observe(4);', 1)
    flash = extract(texts['rc'], 'flash_firmware')
    if core.count(flash) != 1:
        raise ValueError('Exactly one actual flash body')
    # The callback observes the real wait result before actual flash resumes.
    # It is not a replacement for flash or the actual wait/status parser.
    observer = r'''
static int consumer_after_writer,consumer_after_flash;
static int consumer_post[6],consumer_second[6],consumer_round;
static int observed_worker_run(const char*w,const char*r,int lease,pid_t*child){int status=firmware_upgrade_run(w,r,lease,child);consumer_after_writer=1;return status;}
#define firmware_upgrade_run observed_worker_run
'''
    core = core.replace(flash, observer + flash + '\n#undef firmware_upgrade_run\n', 1)
    code = core + '\n#define CONSUMER_ROOT ' + json.dumps(fixture_root) + '\n' + PREFIX
    for name in FUNCTIONS['notify']:
        code += extract(texts['notify'], name) + '\n'
    code += '\n'.join(line for line in texts['notify_header'].splitlines() if line.startswith('#define RCN_')) + '\n'
    consumer = extract(texts['rc'], 'handle_notifications')
    standard = {'handle_notifications', 'flash_firmware', 'firmware_upgrade_inhibited',
                'firmware_upgrade_signal_inhibited', 'rc_notification_open_dir',
                'rc_notification_valid_marker', 'fdopendir', 'close', 'readdir',
                'strcmp', 'unlinkat', 'snprintf', 'remove', 'printf', 'fopen', 'fclose',
                'closedir', 'kill', 'getpid', 'if', 'for', 'while', 'sizeof', 'defined'}
    calls = set(re.findall(r'\b([a-zA-Z_]\w*)\s*\(', consumer + '\n' + old))
    for name in sorted(calls - standard):
        code += '#define ' + name + '(...) fixture_noop()\n'
    code += '#undef start_logger\n#define start_logger(...) (consumer_actions++,fixture_noop())\n'
    code += '#undef control_guest_wl\n#define control_guest_wl(value,level) ((void)(value),(void)(level),fixture_noop())\n'
    code += '#undef control_guest_rt\n#define control_guest_rt(value,level) ((void)(value),(void)(level),fixture_noop())\n'
    code += CALLBACKS
    code += consumer + '\n'
    code += '#define handle_notifications old_handle_notifications\n' + old + '\n#undef handle_notifications\n'
    code += MAIN
    return code


PREFIX = r'''
#undef open
#undef close
#undef write
#undef fstat
#undef fstatat
#include <dirent.h>
static char queue_path[1024],pending_path[1024],queue_names[32][32];
static int queue_count,queue_cursor,consumer_events,consumer_signals,consumer_actions;
static int consumer_memory_queries,consumer_old;
static int nvram_nf_nat_type,nvram_modem_type,nvram_modem_rule;
static int fixture_noop(void){return 0;}
#define DIR_RC_NOTIFY queue_path
#define DIR_RC_INCOMPLETE pending_path
static void observe(int index){if(consumer_after_writer||consumer_after_flash){consumer_post[index]++;if(consumer_round==2)consumer_second[index]++;}}
static int observed_flash(void){int phase=flash_firmware();consumer_after_flash=1;return phase;}
static int observed_memory(void){consumer_memory_queries++;return firmware_upgrade_signal_inhibited();}
static int observed_filesystem(void){observe(5);return firmware_upgrade_inhibited();}
static FILE* observed_fopen(const char*p,const char*m){observe(0);return fopen(p,m);}
static int observed_snprintf(char*p,size_t n,const char*f,...){int result;va_list ap;observe(1);va_start(ap,f);result=vsnprintf(p,n,f,ap);va_end(ap);return result;}
static int observed_remove(const char*p){observe(2);return remove(p);}
static int observed_closedir(DIR*d){observe(3);return closedir(d);}
static void observed_log(const char*tag,const char*f,...){(void)tag;(void)f;observe(4);}
static int observed_printf(const char*f,...){if(!strcmp(f,"rc notification: %s\n"))consumer_events++;return 0;}
static int observed_rearm(pid_t pid,int sig){assert(pid==getpid()&&sig==SIGUSR1);consumer_signals++;return 0;}
static struct dirent* observed_readdir(DIR*d){
 static struct dirent e;struct stat st;
 while(queue_cursor<queue_count){const char*n=queue_names[queue_cursor++];if(!fstatat(dirfd(d),n,&st,AT_SYMLINK_NOFOLLOW)){
  memset(&e,0,sizeof(e));assert(strlen(n)<sizeof(e.d_name));strcpy(e.d_name,n);return &e;
 }}return NULL;
}
'''

CALLBACKS = r'''
#define flash_firmware observed_flash
#define firmware_upgrade_signal_inhibited observed_memory
#define firmware_upgrade_inhibited observed_filesystem
#define fopen observed_fopen
#undef snprintf
#define snprintf observed_snprintf
#define remove observed_remove
#define closedir observed_closedir
#define logmessage observed_log
#define readdir observed_readdir
#define printf observed_printf
#define kill observed_rearm
'''

MAIN = r'''
#undef flash_firmware
#undef firmware_upgrade_signal_inhibited
#undef firmware_upgrade_inhibited
#undef fopen
#undef snprintf
#undef remove
#undef closedir
#undef logmessage
#undef readdir
#undef printf
#undef kill
static void put_counts(const int*v){int i;putchar('[');for(i=0;i<6;i++)printf("%s%d",i?",":"",v[i]);putchar(']');}
static int queue_remaining(void){int n=0;struct dirent*e;DIR*d=opendir(queue_path);assert(d);while((e=readdir(d)))if(e->d_name[0]!='.')n++;assert(!closedir(d));return n;}
int main(int argc,char**argv){
 const char*name;char path[1300];int fd,i,initial_memory,remaining,pending;
 assert(argc==2);name=argv[1];assert(mkdir(CONSUMER_ROOT,0700)==0||errno==EEXIST);
 (void)nvram_nf_nat_type;(void)nvram_modem_type;(void)nvram_modem_rule;
 assert(mkdir(FW_UPGRADE_PRIVATE,0700)==0);
 fd=open(FW_UPGRADE_WRITER,O_WRONLY|O_CREAT|O_EXCL,0700);assert(fd>=0);assert(write(fd,"INERT WRITER",12)==12);assert(close(fd)==0);
 fd=open(FIXTURE_HW,O_WRONLY|O_CREAT|O_EXCL,0600);assert(fd>=0);assert(close(fd)==0);
 assert(snprintf(queue_path,sizeof(queue_path),"%s/queue",CONSUMER_ROOT)<(int)sizeof(queue_path));
 assert(snprintf(pending_path,sizeof(pending_path),"%s/pending",CONSUMER_ROOT)<(int)sizeof(pending_path));
 assert(mkdir(queue_path,0700)==0&&mkdir(pending_path,0700)==0);
 queue_count=13;strcpy(queue_names[0],"flash_firmware");
 for(i=1;i<queue_count;i++)assert(snprintf(queue_names[i],sizeof(queue_names[i]),"later_%02d",i)<(int)sizeof(queue_names[i]));
 strcpy(queue_names[1],RCN_RESTART_SYSLOG);
 for(i=0;i<queue_count;i++){
  assert(snprintf(path,sizeof(path),"%s/%s",queue_path,queue_names[i])<(int)sizeof(path));fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);assert(fd>=0);assert(!close(fd));
  assert(snprintf(path,sizeof(path),"%s/%s",pending_path,queue_names[i])<(int)sizeof(path));fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);assert(fd>=0);assert(!close(fd));
 }
 for(i=0;i<7;i++)running[i]=1;
 kind=1;
 if(!strcmp(name,"consumer-unknown"))kind=2;
 else if(!strcmp(name,"consumer-verified-return"))kind=0;
 else if(!strcmp(name,"consumer-signal"))kind=3;
 else if(!strcmp(name,"consumer-exec-failure"))kind=10;
 else if(!strcmp(name,"consumer-untrusted20"))kind=6;
 else if(!strcmp(name,"consumer-mismatched20"))kind=7;
 else if(!strcmp(name,"consumer-first-save-abort"))first_status=256;
 else if(!strcmp(name,"consumer-hook-abort")){hook_exists=1;hook_status=256;}
 else if(!strcmp(name,"old-consumer-negative")){consumer_old=1;kind=2;}
 else assert(!strcmp(name,"consumer-safe20"));
 for(consumer_round=1;consumer_round<=2;consumer_round++){
  queue_cursor=0;
  if(consumer_old)old_handle_notifications();else handle_notifications();
 }
 initial_memory=firmware_upgrade_signal_inhibited();remaining=queue_remaining();
 assert(snprintf(path,sizeof(path),"%s/flash_firmware",pending_path)<(int)sizeof(path));pending=access(path,F_OK)==0;
 printf("{\"case\":\"%s\",\"active\":%d,\"events\":%d,\"signals\":%d,\"actions\":%d,\"remaining\":%d,\"pending_flash\":%d,\"writer_calls\":%d,\"reboots\":%d,\"watchdog_running\":%d,\"memory_queries\":%d,\"post\":",name,initial_memory,consumer_events,consumer_signals,consumer_actions,remaining,pending,writer_calls,reboots,running[0],consumer_memory_queries);
 put_counts(consumer_post);printf(",\"second\":");put_counts(consumer_second);puts("}");return 0;
}
'''


def record(name, held=True, writes=1, old=False):
    return {'case': name, 'active': int(held), 'events': 1 if held else 13,
            'signals': 0 if held else 1, 'actions': 0 if held else 1,
            'remaining': 12 if held else 0, 'pending_flash': int(held and not old),
            'writer_calls': writes, 'reboots': 0, 'watchdog_running': int(not held),
            'memory_queries': 0 if old else 2,
            'post': [1, 1, 1, 1, 0, 1] if old else [0] * 6 if held else [13, 25, 25, 2, int(writes > 0), 1],
            'second': [0, 0, 0, 0, 0, 1] if old else [0] * 6 if held else [3, 6, 6, 1, 0, 1]}


CASES = tuple((name, record(name)) for name in (
    'consumer-unknown', 'consumer-verified-return', 'consumer-signal',
    'consumer-exec-failure', 'consumer-untrusted20', 'consumer-mismatched20')) + (
    ('consumer-safe20', record('consumer-safe20', False)),
    ('consumer-first-save-abort', record('consumer-first-save-abort', False, 0)),
    ('consumer-hook-abort', record('consumer-hook-abort', False, 0)),
    ('old-consumer-negative', record('old-consumer-negative', old=True)),
)
