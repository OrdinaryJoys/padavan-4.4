"""Pure actual-function generator for inert Web/GPIO transaction controls.

All admission file and flock operations are real private-fixture syscalls.
Firmware, config, service, signal and GPIO effects are recording substitutes.
This module does not read files, start processes or access devices on import.
"""
import ast
import json
import re
from pathlib import PurePosixPath

SOURCE_PATHS = {
    'guard': 'trunk/user/shared/upgrade_guard.h',
    'httpd': 'trunk/user/httpd/httpd.c',
    'http_header': 'trunk/user/httpd/httpd.h',
    'origin': 'trunk/user/httpd/http_origin_guard.c',
    'web': 'trunk/user/httpd/web_ex.c',
    'upload': 'trunk/user/httpd/upload.c',
    'buttons': 'trunk/user/rc/btn_action.c',
    'gpio': 'trunk/user/rc/gpio_btn.c',
    'rc': 'trunk/user/rc/rc.c',
    'init': 'trunk/user/rc/init.c',
    'watchdog': 'trunk/user/rc/watchdog.c',
    'upgrade_fixture': 'tests/upgrade_gate_harness.py',
    'http_fixture': 'tests/test_httpd_regressions.py',
}
FUNCTIONS = {
    'rc': ('firmware_upgrade_signal_inhibited', 'firmware_upgrade_signal_fault', 'reset_to_defaults'),
    'init': ('sys_exit', 'sys_stop', 'catch_sig_fatal', 'catch_sig_event', 'catch_sig_reap', 'init_signals'),
    'httpd': ('http_upgrade_action_acquire', 'http_upgrade_action_handoff',
              'http_upgrade_action_release', 'parse_content_length',
              'parse_multipart_boundary', 'trim_header_value', 'handle_request'),
    'web': ('sys_reboot', 'apply_cgi', 'do_upgrade_fw_cgi', 'do_restore_nv_cgi', 'do_restore_st_cgi'),
    'upload': ('do_upgrade_fw_post', 'do_restore_nv_post', 'do_restore_st_post'),
    'buttons': ('upgrade_gpio_action_release', 'btn_event_short', 'btn_event_long', 'btn_reset_action'),
    'gpio': ('upgrade_gpio_event_release', 'btn_released_handle', 'btn_ev_handle'),
}


def extract(text, name):
    match = re.search(r'(?:static\s+)?(?:inline\s+)?(?:void|int|ssize_t|char\s*\*|FILE\s*\*)\s*\n?\b' + name + r'\s*\(', text)
    if not match:
        raise ValueError(name)
    depth = 0
    opening = text.index('{', match.end())
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
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact source keys required')
    if not isinstance(fixture_root, str) or not fixture_root.startswith('/') or any(ord(c) < 32 or ord(c) > 126 for c in fixture_root):
        raise ValueError('Absolute ASCII private fixture root required')
    if type(owner_uid) is not int or owner_uid < 0 or owner_uid > 0xffffffff:
        raise ValueError('Compile-time fixture owner must be a UID')
    tree = ast.parse(texts['http_fixture'])
    prelude = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'PRELUDE' for t in n.targets))
    for line in ('static int http_upgrade_action_acquire(void){return 0;}\n',
                 'static void http_upgrade_action_release(int*owned){}\n',
                 'static void http_upgrade_action_handoff(void){}\n'):
        prelude = prelude.replace(line, '')
    # Use the production cleanup contract, not the old idle fixture macro.
    prelude = '\n'.join(line for line in prelude.splitlines()
                        if not line.startswith('#define HTTP_UPGRADE_ACTION_GUARD'))
    macro = re.search(r'#define HTTP_UPGRADE_ACTION_GUARD\(failure\)(?:[^\n]*\\\n)*[^\n]*', texts['http_header'])
    if not macro:
        raise ValueError('Production cleanup macro missing')
    prelude = prelude.replace('static int f_exists(const char*s){return 0;}',
                              'static int f_exists(const char*s){return 1;}')
    bodies = actual_functions(texts)
    code = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <signal.h>
#include <stdarg.h>
#include <sys/statvfs.h>
#include <sys/wait.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <stdio.h>
#include <string.h>
'''
    code += '\n#define UPGRADE_GUARD_PRIVATE ' + json.dumps(fixture_root) + '\n'
    code += '#define UPGRADE_GUARD_OWNER ((uid_t)' + str(owner_uid) + ')\n'
    code += texts['guard'] + '\n' + prelude + '\n' + macro.group(0) + '\n'
    code += PREFIX
    for array in ('signals_fatal','signals_event'):
        found = re.findall(r'static const int '+array+r'\[\]\s*=\s*\{[^}]*\};',texts['init'])
        if len(found) != 1:
            raise ValueError('Actual signal arrays required')
        code += found[0]+'\n'
    code += MASK_BACKEND
    code += '\n'.join(bodies[name]['body'] for key in ('rc','init') for name in FUNCTIONS[key]) + '\n'
    code += '\n'.join(bodies[name]['body'] for name in FUNCTIONS['httpd']) + '\n'
    # Origin definitions must precede the actual request function.
    request = bodies['handle_request']['body']
    code = code[:code.rfind(request)] + texts['origin'].replace('#include "httpd.h"', '') + '\n' + request + '\n'
    code += '\n'.join(bodies[name]['body'] for name in FUNCTIONS['web']) + '\n'
    code += '\n'.join(bodies[name]['body'] for name in FUNCTIONS['upload']) + '\n'
    code += '\n'.join(bodies[name]['body'] for name in FUNCTIONS['buttons']) + '\n'
    code += '\n'.join(bodies[name]['body'] for name in FUNCTIONS['gpio']) + '\n'
    code += MAIN
    return code


def generate_flash_source(texts, fixture_root, owner_uid=0):
    """Reuse the existing actual state-machine fixture, then probe the return.

    Its documented fstat mapping treats test-user files as uid0, including in
    unprivileged QEMU. MTD/watchdog/mlock/reboot/services are inert callbacks.
    The same C process calls actual flash_firmware and observes its real latch,
    marker and action lease afterwards; no hand-written phase replaces it.
    """
    if set(texts) != set(SOURCE_PATHS) or type(owner_uid) is not int or owner_uid < 0:
        raise ValueError('Exact sources and compile-time fixture identity required')
    if not isinstance(fixture_root, str) or not fixture_root.startswith('/') or any(ord(c) < 32 or ord(c) > 126 for c in fixture_root):
        raise ValueError('Absolute ASCII private fixture root required')
    tree = ast.parse(texts['upgrade_fixture'])
    functions = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'FUNCTIONS' for t in n.targets))
    generate = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate')
    by_path = {path: texts[key] for key,path in SOURCE_PATHS.items()}
    namespace = {'json':json, 'function':extract, 'FUNCTIONS':functions,
                 'source':lambda path:by_path[path]}
    exec(compile(ast.Module(body=[generate],type_ignores=[]), '<pure locked state-machine generator>', 'exec'), namespace)
    core = namespace['generate'](PurePosixPath(fixture_root)).split('static void json_array',1)[0]
    # Observe PREPARE at the real first-save callback, and EX independently of
    # the marker. Only this inert callback is instrumented, not rc functions.
    needle = 'static int doSystem(const char *fmt,...)'
    declarations = 'static int fixture_prepare_checks,fixture_prepare_failed;\nstatic int fixture_raw_shared_allowed(void);\nstatic int firmware_upgrade_signal_inhibited(void);\n'
    if core.count(needle) != 1:
        raise ValueError('Known storage callback required')
    core = core.replace(needle,declarations+needle,1)
    needle = 'if(!strcmp(command,"/sbin/mtd_storage.sh save")){'
    if core.count(needle) != 1:
        raise ValueError('Known first-save dispatch required')
    core = core.replace(needle,needle+'fixture_prepare_checks++;if(!firmware_upgrade_signal_inhibited()||!firmware_upgrade_inhibited()||fixture_raw_shared_allowed())fixture_prepare_failed=1;',1)
    return core + '\n#define HARNESS_ROOT ' + json.dumps(fixture_root) + '\n' + FLASH_MAIN


FLASH_MAIN = r'''
static int fixture_raw_shared_allowed(void){int fd,allowed;fd=open(FW_UPGRADE_PRIVATE "/firmware-action.lock",O_RDWR|O_NOFOLLOW|O_CLOEXEC);assert(fd>=0);allowed=flock(fd,LOCK_SH|LOCK_NB)==0;assert(close(fd)==0);return allowed;}
int main(int argc,char**argv){int i,fd,phase,action_fd,held=-1;const char*name;assert(argc==2);name=argv[1];
 assert(mkdir(HARNESS_ROOT,0700)==0||errno==EEXIST);assert(mkdir(FW_UPGRADE_PRIVATE,0700)==0);
 fd=open(FW_UPGRADE_WRITER,O_WRONLY|O_CREAT|O_EXCL,0700);assert(fd>=0);assert(write(fd,"INERT TEST WRITER",17)==17);assert(close(fd)==0);
 fd=open(FIXTURE_HW,O_WRONLY|O_CREAT|O_EXCL,0600);assert(fd>=0);assert(close(fd)==0);
 for(i=0;i<7;i++){running[i]=1;}
 kind=1;
 if(!strcmp(name,"flash-unknown-return"))kind=2;
 else if(!strcmp(name,"flash-verified-worker-exit"))kind=0;
 else if(!strcmp(name,"flash-save-abort"))first_status=256;
 else if(!strcmp(name,"flash-hook-abort")){hook_exists=1;hook_status=256;}
 else if(!strcmp(name,"flash-action-already-admitted")){held=upgrade_action_enter();assert(held>=0);}
 else assert(!strcmp(name,"flash-safe-prewrite-return"));
 phase=flash_firmware();action_fd=upgrade_action_enter();
 printf("{\"case\":\"%s\",\"trace\":[\"phase:%d\",\"active:%d\",\"marker:%d\",\"action-refused:%d\",\"writer:%d\",\"reboot:%d\",\"raw-shared-after:%d\",\"prepare-checks:%d\",\"prepare-admission-valid:%d\"]}\n",name,phase,firmware_upgrade_signal_inhibited(),upgrade_actions_blocked(),action_fd<0,writer_calls,reboots,fixture_raw_shared_allowed(),fixture_prepare_checks,!fixture_prepare_failed);
 upgrade_action_leave(action_fd);upgrade_action_leave(held);return 0;
}
'''

FLASH_CASES = (
 ('flash-safe-prewrite-return',{'case':'flash-safe-prewrite-return','trace':['phase:0','active:0','marker:0','action-refused:0','writer:1','reboot:0','raw-shared-after:1','prepare-checks:1','prepare-admission-valid:1']}),
 ('flash-unknown-return',{'case':'flash-unknown-return','trace':['phase:1','active:1','marker:1','action-refused:1','writer:1','reboot:0','raw-shared-after:0','prepare-checks:1','prepare-admission-valid:1']}),
 ('flash-verified-worker-exit',{'case':'flash-verified-worker-exit','trace':['phase:1','active:1','marker:1','action-refused:1','writer:1','reboot:0','raw-shared-after:0','prepare-checks:1','prepare-admission-valid:1']}),
 ('flash-save-abort',{'case':'flash-save-abort','trace':['phase:0','active:0','marker:0','action-refused:0','writer:0','reboot:0','raw-shared-after:1','prepare-checks:1','prepare-admission-valid:1']}),
 ('flash-hook-abort',{'case':'flash-hook-abort','trace':['phase:0','active:0','marker:0','action-refused:0','writer:0','reboot:0','raw-shared-after:1','prepare-checks:1','prepare-admission-valid:1']}),
 ('flash-action-already-admitted',{'case':'flash-action-already-admitted','trace':['phase:0','active:0','marker:0','action-refused:0','writer:0','reboot:0','raw-shared-after:1','prepare-checks:0','prepare-admission-valid:1']}),
)


PREFIX = r'''
#define FW_IMG_NAME "/fixture/upload.trx"
#define PROFILE_FIFO_UPLOAD "/fixture/nvram.prf"
#define STORAGE_FIFO_FILENAME "/fixture/storage.bz2"
#define MAX_EVENTS 64
#include <setjmp.h>
#include <sys/reboot.h>
static const char *events[MAX_EVENTS];
static char event_text[MAX_EVENTS][96];
static int event_count, effect_count, transaction_fd=-1, wanted_action;
static int prepare_result, prepare_calls, cleanup_calls, apply_output, upgrade_output;
static int format_service,format_mode,fatal_route,reap_calls;
static int fatal_mask_calls,event_mask_calls,reap_mask_calls,masks_valid=1;
static volatile sig_atomic_t firmware_upgrade_pid1_active,firmware_upgrade_pid1_fault;
static volatile sig_atomic_t sig_term_received,sig_usr1_received,sig_alrm_received;
static jmp_buf fatal_end;
int sys_exit(void);
int sys_stop(void);
static void catch_sig_fatal(int);
static void catch_sig_event(int);
static void catch_sig_reap(int);
#ifndef SIGPWR
/* Darwin lacks SIGPWR. Only this native fixture maps it to an unused valid
 * signal; real Linux/MIPS uses its own SIGPWR from the target headers. */
#define SIGPWR SIGWINCH
#endif
#define ARRAY_SIZE(a) ((int)(sizeof(a)/sizeof((a)[0])))
static const char *wanted_mode=" Reboot ";
static int http_upgrade_action_fd=-1;
static char next_host[128],SystemCmd[128];
static void event(const char *text){assert(event_count<MAX_EVENTS);events[event_count++]=text;}
static void number(const char *name,int value){assert(event_count<MAX_EVENTS);snprintf(event_text[event_count],96,"%s:%d",name,value);events[event_count]=event_text[event_count];event_count++;}
static void exclusive(const char *name){int fd=upgrade_transaction_enter();char text[96];snprintf(text,sizeof(text),"%s:%s",name,fd>=0?"free":"blocked");assert(event_count<MAX_EVENTS);strcpy(event_text[event_count],text);events[event_count]=event_text[event_count];event_count++;upgrade_action_leave(fd);}
static void effect(const char *name){effect_count++;event(name);exclusive("effect-exclusive");}
static int fixture_kill(pid_t pid,int sig){assert((pid==1||pid==-1)&&(sig==SIGTERM||sig==SIGQUIT));effect(pid==-1?"broadcast-TERM":(sig==SIGTERM?"PID1-TERM":"PID1-QUIT"));if(pid==1&&fatal_route)catch_sig_fatal(sig);return 0;}
static int fixture_printf(const char*format,...){(void)format;event("diagnostic");return 0;}
static void reset_signals(void){event("reset-signals");}
static void shutdown_router(int level){event(level?"shutdown:halt":"shutdown:reboot");}
static void fixture_sync(void){event("sync");}
static int fixture_reboot(int command){assert(command==RB_AUTOBOOT);event("reboot");longjmp(fatal_end,1);return -1;}
static int fixture_pause(void){event("fault-quarantine");longjmp(fatal_end,1);return -1;}
static pid_t fixture_waitpid(pid_t pid,int*status,int flags){(void)status;assert(pid==-1&&flags==WNOHANG);return reap_calls++?0:123;}
static void fixture_dprintf(const char*format,...){(void)format;event("reap-diagnostic");}
static void notify_shutdown(void){event("notify-shutdown");}
static int fixture_unlink(const char *name){(void)name;effect("unlink-upload");return 0;}
static unsigned int fixture_sleep(unsigned int seconds){(void)seconds;return 0;}
static int doSystem(const char *format,...){(void)format;effect("command");return 0;}
static int eval(const char *command,...){(void)command;effect("eval");return 0;}
static int nvram_commit(void){effect("nvram-commit");return 0;}
static int nvram_set_int(const char *name,int value){(void)name;(void)value;effect("nvram-set");return 0;}
static int nvram_get_int(const char *name){(void)name;return wanted_action;}
static int get_login_safe(void){return 1;}
static int get_login_valid(void){return 0;}
static void websApply(FILE*f,const char*name){(void)f;event(name);}
static void websRedirect(FILE*f,const char*name){(void)f;(void)name;event("redirect");}
static void websWrite(FILE*f,const char*format,...){(void)f;(void)format;event("response");}
static char *websGetVar(FILE*f,const char*name,const char*otherwise){(void)f;if(!strcmp(name,"action_mode"))return (char*)wanted_mode;if(format_mode&&!strcmp(name,"group_id"))return "%n%08x%%";return (char*)otherwise;}
static char *svc_pop_list(char*list,char sep){(void)list;(void)sep;if(format_service){format_service=0;return "fixture-service";}return NULL;}
static const char *GetServiceId(int sid){return format_mode&&sid==0?"fixture-service":NULL;}
static void validate_cgi(FILE*f,int sid){(void)f;(void)sid;effect("validate-cgi");}
static int apply_cgi_group(FILE*f,int sid,void*v,const char*name,int flag){(void)f;(void)sid;(void)v;(void)flag;if(format_mode)number("group-literal",!strcmp(name,"%n%08x%%"));effect("apply-group");return 0;}
static void sys_script(char*name){(void)name;effect("user-script");}
static int check_header_image(const char*data,long*size){(void)data;(void)size;return 0;}
static int check_header_nvram(const char*data,long*size){(void)data;(void)size;return 0;}
static int check_header_bz2(const char*data,long*size){(void)data;(void)size;return 0;}
static int check_crc_image(const char*name){(void)name;return 0;}
static int do_upload_file(FILE*f,int len,char*b,const char*name,const char*object,check_header_t callback,int size){(void)f;(void)len;(void)b;(void)name;(void)object;(void)callback;(void)size;effect("upload");return 0;}
static int fput_int(const char*name,int value){(void)name;(void)value;effect("drop-cache");return 0;}
static void notify_rc(const char*name){assert(!strcmp(name,"flash_firmware"));event("notify-flash");transaction_fd=upgrade_transaction_enter();event(transaction_fd>=0?"handoff-exclusive:free":"handoff-exclusive:blocked");}
#define GROUP_FLAG_REFRESH 0
#define GROUP_FLAG_DELETE 1
#define GROUP_FLAG_ADD 2
#define GROUP_FLAG_REMOVE 3
#define MIN(a,b) ((a)<(b)?(a):(b))
typedef FILE *webs_t;
#define kill fixture_kill
#define unlink fixture_unlink
#define sleep fixture_sleep
#define printf fixture_printf
#define sync fixture_sync
#define reboot fixture_reboot
#define pause fixture_pause
#define waitpid fixture_waitpid
#define dprintf fixture_dprintf
#define BOARD_HAS_5G_RADIO 1
#define BOARD_NUM_USB_PORTS 0
#define BTN_FN1 1
#define BTN_FN2 2
#define BTN_WPS 4
#define BTN_RESET 8
#define BTN_PRESSED 1
#define BTN_RELEASED 2
#define CANCEL_COUNT 8
#define LONG_COUNT 30
#define RESET_COUNT 50
#define btn_dbg(...) do {} while(0)
typedef struct {char event;int btn_id;} btn_event;
static struct btn_entrys_t {const int btn_id;const char*name;int count;} btn_entrys[]={{BTN_RESET,"reset",0},{BTN_WPS,"wps",0},{0,NULL,0}};
#define LED_PWR 1
#define LED_OFF 0
#define LED_ON 1
static int search_gpio_led(void){return 1;}
static int get_state_led_pwr(void){return 1;}
static void gpio_led_set(int pin,int value){(void)pin;(void)value;effect("LED");}
#define LED_CONTROL(pin,value) gpio_led_set(pin,value)
static void erase_nvram(void){effect("erase-nvram");}
static void erase_storage(void){effect("erase-storage");}
static void ez_action_toggle_wifi2(void){effect("wifi2");}
static void ez_action_toggle_wifi5(void){effect("wifi5");}
static void ez_action_change_wifi2(void){effect("wifi2");}
static void ez_action_change_wifi5(void){effect("wifi5");}
static void ez_action_change_guest_wifi2(void){effect("guest2");}
static void ez_action_change_guest_wifi5(void){effect("guest5");}
static void ez_action_usb_saferemoval(int port){(void)port;effect("USB");}
static void ez_action_wan_down(void){effect("WAN-down");}
static void ez_action_wan_reconnect(void){effect("WAN-restart");}
static void ez_action_wan_toggle(void){effect("WAN-toggle");}
static void ez_action_shutdown(void){sys_stop();}
static void ez_action_user_script(int param){(void)param;effect("user-script");}
static void ez_action_led_toggle(void){effect("LED");}
'''

MASK_BACKEND = r'''
static int fixture_sigaction(int sig,const struct sigaction*sa,struct sigaction*old){int i;(void)old;
 if(sa->sa_handler==catch_sig_fatal){fatal_mask_calls++;if(sigismember(&sa->sa_mask,SIGCHLD)!=1)masks_valid=0;for(i=0;i<ARRAY_SIZE(signals_fatal);i++)if(sigismember(&sa->sa_mask,signals_fatal[i])!=1)masks_valid=0;for(i=0;i<ARRAY_SIZE(signals_event);i++)if(sigismember(&sa->sa_mask,signals_event[i])!=1)masks_valid=0;}
 else if(sa->sa_handler==catch_sig_event){event_mask_calls++;}
 else {assert(sig==SIGCHLD&&sa->sa_handler==catch_sig_reap);reap_mask_calls++;}return 0;}
#define sigaction(...) fixture_sigaction(__VA_ARGS__)
'''

MAIN = r'''
#undef unlink
#undef kill
#undef sleep
#undef printf
#undef sync
#undef reboot
#undef pause
#undef waitpid
#undef dprintf
static void marker(int enabled){char name[4096];int fd;snprintf(name,sizeof(name),"%s/%s",UPGRADE_GUARD_PRIVATE,UPGRADE_GUARD_MARKER);if(enabled){fd=open(name,O_WRONLY|O_CREAT|O_EXCL,0600);assert(fd>=0);assert(close(fd)==0);}else assert(unlink(name)==0);}
static int prepared(const char*name){(void)name;prepare_calls++;event("prepare");exclusive("prepare-exclusive");return prepare_result;}
static void cleaned(void){cleanup_calls++;event("cleanup");}
static void input(const char*u,FILE*f,int n,char*b){(void)u;(void)f;(void)n;(void)b;input_calls++;event("input");exclusive("input-exclusive");}
static void output(const char*u,FILE*f){action_calls++;event("output");exclusive("output-exclusive");if(apply_output)apply_cgi(u,f);if(upgrade_output)do_upgrade_fw_cgi(u,f);}
static void request(const char*method,const char*path,const char*headers,int state,int valid,int preparation){FILE*f=tmpfile();conn_item_t peer={0};assert(f);auth_state=state;auth_valid=valid;status_code=action_calls=input_calls=0;mime_handlers[0].input=input;mime_handlers[0].output=output;mime_handlers[0].prepare=preparation?prepared:NULL;mime_handlers[0].cleanup=preparation?cleaned:NULL;fprintf(f,"%s %s HTTP/1.1\r\n%s\r\n",method,path,headers);rewind(f);handle_request(f,&peer);assert(fclose(f)==0);number("http",status_code);}
static void ensure_directory(void){struct stat st;assert(mkdir(UPGRADE_GUARD_PRIVATE,0700)==0||errno==EEXIST);assert(lstat(UPGRADE_GUARD_PRIVATE,&st)==0&&S_ISDIR(st.st_mode));assert(chmod(UPGRADE_GUARD_PRIVATE,0700)==0);}
int main(int argc,char**argv){const char*c;int fd,other,saved;volatile int marked=0;char lockpath[4096];
 assert(argc==2);c=argv[1];ensure_directory();
 if(!strcmp(c,"query-idle")){errno=EDOM;number("blocked",upgrade_actions_blocked());number("errno-preserved",errno==EDOM);}
 else if(!strcmp(c,"query-missing-directory")){assert(rmdir(UPGRADE_GUARD_PRIVATE)==0);number("blocked",upgrade_actions_blocked());fd=upgrade_action_enter();number("lease-refused",fd<0);upgrade_action_leave(fd);ensure_directory();}
 else if(!strcmp(c,"unsafe-directory")){assert(chmod(UPGRADE_GUARD_PRIVATE,0755)==0);number("blocked",upgrade_actions_blocked());fd=upgrade_action_enter();number("lease-refused",fd<0);upgrade_action_leave(fd);assert(chmod(UPGRADE_GUARD_PRIVATE,0700)==0);}
 else if(!strcmp(c,"shared-excludes-transaction")){fd=upgrade_action_enter();assert(fd>=0);exclusive("during-shared");other=upgrade_action_enter();number("second-shared",other>=0);upgrade_action_leave(other);upgrade_action_leave(fd);}
 else if(!strcmp(c,"transaction-excludes-action")){fd=upgrade_transaction_enter();assert(fd>=0);other=upgrade_action_enter();number("action-refused",other<0);upgrade_action_leave(other);upgrade_action_leave(fd);}
 else if(!strcmp(c,"marker-rejects-action")){marker(1);marked=1;number("blocked",upgrade_actions_blocked());fd=upgrade_action_enter();number("lease-refused",fd<0);upgrade_action_leave(fd);}
 else if(!strcmp(c,"http-idle-write")){request("POST","/apply.cgi","Host: router\r\nOrigin: http://router\r\nContent-Length: 0\r\n",3,1,0);}
 else if(!strcmp(c,"http-busy-write")){marker(1);marked=1;request("POST","/apply.cgi","Host: router\r\nOrigin: http://router\r\nContent-Length: 0\r\n",3,1,0);}
 else if(!strcmp(c,"http-busy-auth-failure")){marker(1);marked=1;request("POST","/apply.cgi","Host: router\r\nOrigin: http://router\r\nContent-Length: 0\r\n",3,0,0);}
 else if(!strcmp(c,"http-busy-cross-origin")){marker(1);marked=1;request("POST","/apply.cgi","Host: router\r\nOrigin: http://elsewhere\r\nContent-Length: 0\r\n",3,1,0);}
 else if(!strcmp(c,"http-busy-status")){marker(1);marked=1;request("GET","/update.cgi?output=uptime","Host: router\r\n",3,1,0);}
 else if(!strcmp(c,"http-busy-status-head")){marker(1);marked=1;request("HEAD","/index.asp","Host: router\r\n",3,1,0);}
 else if(!strcmp(c,"http-busy-backup-head")){marker(1);marked=1;request("HEAD","/Storage_fixture.TBZ","Host: router\r\n",3,1,1);}
 else if(!strcmp(c,"http-backup-prepare-failure")){prepare_result=500;request("GET","/Storage_fixture.TBZ","Host: router\r\n",3,1,1);}
 else if(!strcmp(c,"http-backup-head-release")){request("HEAD","/Storage_fixture.TBZ","Host: router\r\n",3,1,1);}
 else if(!strcmp(c,"direct-reboot-busy")){marker(1);marked=1;sys_reboot();}
 else if(!strcmp(c,"direct-reboot-idle")){sys_reboot();}
 else if(!strcmp(c,"apply-reset-busy")){marker(1);marked=1;wanted_mode=" RestoreNVRAM ";apply_cgi("apply.cgi",NULL);}
 else if(!strcmp(c,"apply-reset-idle")){wanted_mode=" RestoreNVRAM ";apply_cgi("apply.cgi",NULL);}
 else if(!strcmp(c,"restore-nv-busy")){marker(1);marked=1;do_restore_nv_cgi("restore_nv.cgi",NULL);}
 else if(!strcmp(c,"restore-storage-busy")){marker(1);marked=1;do_restore_st_cgi("restore_st.cgi",NULL);}
 else if(!strcmp(c,"upgrade-busy-preserves-upload")){marker(1);marked=1;do_upgrade_fw_cgi("upgrade.cgi",NULL);}
 else if(!strcmp(c,"upgrade-request-handoff")){upgrade_output=1;request("POST","/upgrade.cgi","Host: router\r\nOrigin: http://router\r\nContent-Length: 0\r\n",3,1,0);number("request-fd-cleared",http_upgrade_action_fd<0);}
 else if(!strcmp(c,"upload-busy")){marker(1);marked=1;do_upgrade_fw_post("upgrade.cgi",NULL,4096,NULL);}
 else if(!strcmp(c,"restore-upload-busy")){marker(1);marked=1;do_restore_nv_post("restore_nv.cgi",NULL,4096,NULL);do_restore_st_post("restore_st.cgi",NULL,4096,"x");}
 else if(!strcmp(c,"gpio-short-busy")){marker(1);marked=1;wanted_action=9;btn_event_short(BTN_WPS);}
 else if(!strcmp(c,"gpio-long-busy")){marker(1);marked=1;wanted_action=7;btn_event_long(BTN_WPS);}
 else if(!strcmp(c,"gpio-reset-busy")){marker(1);marked=1;btn_reset_action();}
 else if(!strcmp(c,"gpio-long-idle")){wanted_action=7;btn_event_long(BTN_WPS);}
 else if(!strcmp(c,"gpio-reset-idle")){btn_reset_action();}
 else if(!strcmp(c,"safe-release-reopens-action")){fd=upgrade_transaction_enter();assert(fd>=0);marker(1);other=upgrade_action_enter();number("active-action-refused",other<0);upgrade_action_leave(other);marker(0);upgrade_action_leave(fd);sys_reboot();}
 else if(!strcmp(c,"cross-process-sh-exclusion")){int pipes[2],status;char value;pid_t pid;fd=upgrade_action_enter();assert(fd>=0&&pipe(pipes)==0);pid=fork();assert(pid>=0);if(!pid){int taken;close(pipes[0]);upgrade_action_leave(fd);taken=upgrade_transaction_enter();value=taken<0?'1':'0';upgrade_action_leave(taken);assert(write(pipes[1],&value,1)==1);close(pipes[1]);_exit(0);}close(pipes[1]);assert(read(pipes[0],&value,1)==1);close(pipes[0]);assert(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0);number("child-exclusive-refused",value=='1');upgrade_action_leave(fd);}
 else if(!strcmp(c,"apply-group-percent-literal")){format_mode=format_service=1;wanted_mode=" Add ";apply_cgi("apply.cgi",NULL);}
 else if(!strcmp(c,"cli-reboot-busy")){marker(1);marked=1;number("cli-refused",sys_exit()<0);}
 else if(!strcmp(c,"cli-halt-busy")){marker(1);marked=1;number("cli-refused",sys_stop()<0);}
 else if(!strcmp(c,"cli-reset-busy")){marker(1);marked=1;number("cli-refused",reset_to_defaults()<0);}
 else if(!strcmp(c,"cli-reset-idle")){number("cli-result",reset_to_defaults());}
 else if(!strcmp(c,"phase-active-TERM")||!strcmp(c,"phase-active-QUIT")||!strcmp(c,"phase-active-SEGV")){firmware_upgrade_pid1_active=1;if(!setjmp(fatal_end))catch_sig_fatal(strstr(c,"TERM")?SIGTERM:(strstr(c,"QUIT")?SIGQUIT:SIGSEGV));number("fault-latch",firmware_upgrade_pid1_fault);number("term-latch",sig_term_received);}
 else if(!strcmp(c,"phase-idle-TERM")||!strcmp(c,"phase-idle-QUIT")){if(!setjmp(fatal_end))catch_sig_fatal(strstr(c,"TERM")?SIGTERM:SIGQUIT);number("fault-latch",firmware_upgrade_pid1_fault);number("term-latch",sig_term_received);}
 else if(!strcmp(c,"phase-events-active")||!strcmp(c,"phase-events-idle")){firmware_upgrade_pid1_active=!strcmp(c,"phase-events-active");catch_sig_event(SIGUSR1);catch_sig_event(SIGALRM);catch_sig_event(SIGUSR2);number("usr1-latch",sig_usr1_received);number("alarm-latch",sig_alrm_received);}
 else if(!strcmp(c,"phase-reap-active")||!strcmp(c,"phase-reap-idle")){firmware_upgrade_pid1_active=!strcmp(c,"phase-reap-active");catch_sig_reap(SIGCHLD);number("wait-calls",reap_calls);}
 else if(!strcmp(c,"gpio-release-busy")){marker(1);marked=1;btn_released_handle(BTN_RESET,51);}
 else if(!strcmp(c,"gpio-event-busy-clears-latch")){btn_event ev={BTN_RELEASED,BTN_RESET};marker(1);marked=1;btn_entrys[0].count=51;btn_ev_handle(&ev);number("button-count",btn_entrys[0].count);number("event-cleared",ev.event==0&&ev.btn_id==0);}
 else if(!strcmp(c,"gpio-release-idle")){btn_released_handle(BTN_RESET,51);}
 else if(!strcmp(c,"init-signal-masks")){init_signals();number("fatal-mask-calls",fatal_mask_calls);number("event-mask-calls",event_mask_calls);number("reap-mask-calls",reap_mask_calls);number("masks-valid",masks_valid);}
 else assert(!"Unknown fixed case");
 if(marked){number("marker-retained",upgrade_actions_blocked());marker(0);}
 if(transaction_fd>=0){upgrade_action_leave(transaction_fd);transaction_fd=-1;}
 exclusive("final-exclusive");number("effects",effect_count);
 printf("{\"case\":\"%s\",\"trace\":[",c);for(saved=0;saved<event_count;saved++)printf("%s\"%s\"",saved?",":"",events[saved]);puts("]}");
 snprintf(lockpath,sizeof(lockpath),"%s/%s",UPGRADE_GUARD_PRIVATE,UPGRADE_GUARD_LOCK);assert(unlink(lockpath)==0);assert(rmdir(UPGRADE_GUARD_PRIVATE)==0);return 0;
}
'''

# Independent target checker pins a separate copy of this exact expected table.
EXPECTED = {
 'query-idle': ['blocked:0','errno-preserved:1'],
 'query-missing-directory': ['blocked:0','lease-refused:1'],
 'unsafe-directory': ['blocked:1','lease-refused:1'],
 'shared-excludes-transaction': ['during-shared:blocked','second-shared:1'],
 'transaction-excludes-action': ['action-refused:1'],
 'marker-rejects-action': ['blocked:1','lease-refused:1','marker-retained:1'],
 'http-idle-write': ['input','input-exclusive:blocked','output','output-exclusive:blocked','http:200'],
 'http-busy-write': ['http:503','marker-retained:1'],
 'http-busy-auth-failure': ['http:401','marker-retained:1'],
 'http-busy-cross-origin': ['http:403','marker-retained:1'],
 'http-busy-status': ['output','output-exclusive:blocked','http:200','marker-retained:1'],
 'http-busy-status-head': ['http:200','marker-retained:1'],
 'http-busy-backup-head': ['http:503','marker-retained:1'],
 'http-backup-prepare-failure': ['prepare','prepare-exclusive:blocked','cleanup','http:500'],
 'http-backup-head-release': ['prepare','prepare-exclusive:blocked','cleanup','http:200'],
 'direct-reboot-busy': ['marker-retained:1'],
 'direct-reboot-idle': ['PID1-TERM','effect-exclusive:blocked'],
 'apply-reset-busy': ['marker-retained:1'],
 'apply-reset-idle': ['Restarting.asp','nvram-set','effect-exclusive:blocked','nvram-commit','effect-exclusive:blocked','PID1-TERM','effect-exclusive:blocked'],
 'restore-nv-busy': ['marker-retained:1'],
 'restore-storage-busy': ['marker-retained:1'],
 'upgrade-busy-preserves-upload': ['marker-retained:1'],
 'upgrade-request-handoff': ['input','input-exclusive:blocked','output','output-exclusive:blocked','notify-flash','handoff-exclusive:free','Updating.asp','http:200','request-fd-cleared:1'],
 'upload-busy': ['marker-retained:1'],
 'restore-upload-busy': ['marker-retained:1'],
 'gpio-short-busy': ['marker-retained:1'],
 'gpio-long-busy': ['marker-retained:1'],
 'gpio-reset-busy': ['marker-retained:1'],
 'gpio-long-idle': ['LED','effect-exclusive:blocked','PID1-TERM','effect-exclusive:blocked'],
 'gpio-reset-idle': ['erase-nvram','effect-exclusive:blocked','erase-storage','effect-exclusive:blocked','PID1-TERM','effect-exclusive:blocked'],
 'safe-release-reopens-action': ['active-action-refused:1','PID1-TERM','effect-exclusive:blocked'],
 'cross-process-sh-exclusion': ['child-exclusive-refused:1'],
 'apply-group-percent-literal': ['group-literal:1','apply-group','effect-exclusive:blocked','validate-cgi','effect-exclusive:blocked','redirect'],
 'cli-reboot-busy': ['cli-refused:1','marker-retained:1'],
 'cli-halt-busy': ['cli-refused:1','marker-retained:1'],
 'cli-reset-busy': ['cli-refused:1','marker-retained:1'],
 'cli-reset-idle': ['erase-nvram','effect-exclusive:blocked','PID1-TERM','effect-exclusive:blocked','cli-result:0'],
 'phase-active-TERM': ['fault-latch:0','term-latch:0'],
 'phase-active-QUIT': ['fault-latch:0','term-latch:0'],
 'phase-active-SEGV': ['fault-quarantine','fault-latch:1','term-latch:1'],
 'phase-idle-TERM': ['diagnostic','reset-signals','shutdown:reboot','broadcast-TERM','effect-exclusive:free','sync','reboot','fault-latch:0','term-latch:1'],
 'phase-idle-QUIT': ['diagnostic','shutdown:halt','fault-latch:0','term-latch:1'],
 'phase-events-active': ['usr1-latch:1','alarm-latch:1'],
 'phase-events-idle': ['diagnostic','diagnostic','diagnostic','notify-shutdown','usr1-latch:1','alarm-latch:1'],
 'phase-reap-active': ['wait-calls:2'],
 'phase-reap-idle': ['reap-diagnostic','wait-calls:2'],
 'gpio-release-busy': ['marker-retained:1'],
 'gpio-event-busy-clears-latch': ['button-count:0','event-cleared:1','marker-retained:1'],
 'gpio-release-idle': ['LED','effect-exclusive:blocked','erase-nvram','effect-exclusive:blocked','erase-storage','effect-exclusive:blocked','PID1-TERM','effect-exclusive:blocked'],
 'init-signal-masks': ['fatal-mask-calls:11','event-mask-calls:4','reap-mask-calls:1','masks-valid:1'],
}
_EFFECTS = {'direct-reboot-idle':1,'apply-reset-idle':3,'gpio-long-idle':2,'gpio-reset-idle':3,'safe-release-reopens-action':1,'apply-group-percent-literal':2,'cli-reset-idle':2,'phase-idle-TERM':1,'gpio-release-idle':4}
CASES = tuple((name, {'case':name, 'trace':trace+['final-exclusive:free','effects:'+str(_EFFECTS.get(name,0))]}) for name,trace in EXPECTED.items())
