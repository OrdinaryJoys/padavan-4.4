/* Synthetic DNS/process backends around extracted production NTP functions.
 * Never invokes ntpd, resolves a hostname, opens a socket, or changes time. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int fault, production, hang_resolver, hang_config, configured, foreground;
static int inhibited, inhibit_after_stop, launch_failure, wait_fault, config_seen;
static int requested_opts, feeds, alarms[16], alarm_count, log_count, stops, launches;
static double feed_ticks[16];
static volatile int *resolver_ready;
static unsigned fixture_alarm(unsigned seconds)
{
	if (alarm_count < 16) alarms[alarm_count++] = (int)seconds;
	return alarm(seconds && !production ? 1 : seconds);
}
static int fixture_sigaction(int sig, const struct sigaction *action, struct sigaction *old)
{
	if (fault == 1 && sig == SIGALRM && action && action->sa_handler == SIG_DFL) {
		errno = EIO; return -1;
	}
	return sigaction(sig, action, old);
}
static int fixture_sigprocmask(int how, const sigset_t *set, sigset_t *old)
{
	if (fault == 2 && how == SIG_UNBLOCK) { errno = EIO; return -1; }
	return sigprocmask(how, set, old);
}
#define alarm fixture_alarm
#define sigaction(...) fixture_sigaction(__VA_ARGS__)
#define sigprocmask(...) fixture_sigprocmask(__VA_ARGS__)
/* NTP_STARTUP_HEADER */
#undef alarm
#undef sigaction
#undef sigprocmask

#define ENABLE_FEATURE_NTPD_SERVER 1
#define ENABLE_FEATURE_NTPD_CONF 1
#define IF_FEATURE_NTPD_SERVER(...) __VA_ARGS__
#define NOINLINE
#define G_precision_sec 0.001
#define MAXSTRAT 16
#define BURSTPOLL 0
#define MODE_CLIENT 3
#define NTP_VERSION 4
#define STEP_THRESHOLD 1
#define DAEMON_DEVNULL_STDIO 1
#define LOGMODE_NONE 0
#define IPPROTO_IP 0
#define IP_TOS 1
#define IPTOS_LOWDELAY 2
#define PRIO_PROCESS 0
#define PARSE_NORMAL 0
/* NTP_OPTION_ENUM */
typedef struct llist_t { struct llist_t *link; void *data; } llist_t;
typedef struct { union { char sa; } u; } len_and_sockaddr;
typedef struct {
	len_and_sockaddr *p_lsa; char *p_dotted; int p_fd;
	struct { int m_status; } p_xmt_msg; double next_action_time;
} peer_t;
static struct {
	double discipline_jitter, last_script_run, reftime, last_update_recv_time, cur_time;
	int stratum, poll_exp, peer_cnt, verbose, listen_fd; char *script_name, *if_name;
	llist_t *ntp_peers;
} G;
#define G_listen_fd G.listen_fd
static unsigned option_mask32;
static char *opt_complementary;
static int logmode, daemonized, resolved, initialized, bb_got_signal;
static const char *bb_msg_you_must_be_root = "root";
static unsigned fixture_getuid(void) { return 0; }
static void bb_error_msg_and_die(const char *text) { (void)text; _exit(111); }
static void bb_perror_msg_and_die(const char *text) { (void)text; _exit(111); }
static void bb_show_usage(void) { _exit(112); }
static void bb_error_msg(const char *fmt, ...) { (void)fmt; }
static void *xzalloc(size_t size) { void *p = calloc(1,size); assert(p); return p; }
static len_and_sockaddr *xhost2sockaddr(const char *name, int port)
{
	struct sigaction sa; sigset_t mask;
	assert(name && port == 123); resolved++;
	assert(sigaction(SIGALRM,NULL,&sa) == 0 && sa.sa_handler == SIG_DFL);
	assert(sigprocmask(SIG_SETMASK,NULL,&mask) == 0 && !sigismember(&mask,SIGALRM));
	assert(alarm_count && alarms[alarm_count-1] == 10);
	*resolver_ready = 1;
	while (hang_resolver) pause();
	return xzalloc(sizeof(len_and_sockaddr));
}
static char *xmalloc_sockaddr2dotted_noport(const void *address)
{ (void)address; return strdup("192.0.2.1"); }
static void reset_peer_stats(peer_t *p, int level) { (void)p; (void)level; }
static void llist_add_to(llist_t **head, void *data)
{ llist_t *p=xzalloc(sizeof(*p));p->data=data;p->link=*head;*head=p; }
static char *llist_pop(llist_t **head)
{ llist_t *p=*head;char *value=p->data;*head=p->link;free(p);return value; }
static double gettime1900d(void) { G.cur_time=1;return 1; }
static unsigned getopt32(char **argv, const char *format, ...)
{
	va_list ap;llist_t **peers; (void)argv;(void)format;
	va_start(ap,format);peers=va_arg(ap,llist_t **);
	if (!configured) llist_add_to(peers,(void *)"pool.example.invalid");
	va_end(ap);option_mask32=(unsigned)requested_opts;return (unsigned)requested_opts;
}
typedef struct { unsigned lineno; } parser_t;
static parser_t parser;
static parser_t *config_open(const char *path)
{
	assert(!strcmp(path,"/etc/ntp.conf"));*resolver_ready=1;
	while (hang_config) pause();
	return &parser;
}
static int config_read(parser_t *p,char **tokens,int count,int minimum,const char *delims,int flags)
{
	(void)p;(void)count;(void)minimum;(void)delims;(void)flags;
	if(config_seen++)return 0;
	tokens[0]=(char *)"server";tokens[1]=(char *)"config.example.invalid";return 1;
}
static void config_close(parser_t *p) { (void)p; }
static int create_and_bind_dgram_or_die(const char *addr,int port)
{ (void)addr;assert(port==123);return 7; }
static int setsockopt_bindtodevice(int fd,const char *name) { (void)fd;(void)name;return 0; }
static void xfunc_die(void) { _exit(113); }
static void socket_want_pktinfo(int fd) { (void)fd; }
static void setsockopt_int(int fd,int level,int option,int value)
{ (void)fd;(void)level;(void)option;(void)value; }
static void bb_daemonize_or_rexec(int flags,char **argv)
{ (void)argv;assert(flags==1 && alarms[alarm_count-1]==0);daemonized++; }
static int fixture_setpriority(int which,int who,int value)
{ (void)which;(void)who;(void)value;return 0; }
static void record_signo(int sig) { bb_got_signal=sig; }
static void bb_signals(unsigned mask,void (*handler)(int))
{ int sig;for(sig=1;sig<32;sig++)if(mask & (1U<<sig))assert(signal(sig,handler)!=SIG_ERR); }
#define getuid fixture_getuid
#define setpriority fixture_setpriority
#define alarm fixture_alarm
/* NTP_INIT_FUNCTIONS */
#undef getuid
#undef setpriority
#undef alarm

static int ntpc_timer=-1, ntpc_server_idx, ntpc_tries, ntpc_launch_pid=-1;
static int mock_period=1, updated, feeds_stop;
static char server0[64]="first.example.invalid", server1[64]="second.example.invalid";
static char launched_server[64];
#define NTPC_DONE_SCRIPT "/sbin/ntpc_updated"
static int firmware_upgrade_inhibited(void) { return inhibited; }
static char *nvram_safe_get(const char *name)
{ return !strcmp(name,"ntp_server0") ? server0 : server1; }
static int nvram_get_int(const char *name)
{ return !strcmp(name,"ntp_period") ? mock_period : updated; }
static void logmessage(const char *tag,const char *format,...)
{ (void)tag;(void)format;log_count++; }
static void setenv_tz(void) {}
static void kill_services(char **names,int seconds,int force)
{
	assert(!strcmp(names[0],"ntpd") && !names[1] && seconds==3 && force==1);stops++;
	if(inhibit_after_stop)inhibited=1;
}
static pid_t fixture_waitpid(pid_t pid,int *status,int options)
{
	if(wait_fault){errno=wait_fault;return -1;}
	return waitpid(pid,status,options);
}
static void child_init(void)
{
	char *argv[]={(char *)"ntpd",NULL};sigset_t empty;
	assert(signal(SIGALRM,SIG_DFL)!=SIG_ERR && signal(SIGTERM,SIG_DFL)!=SIG_ERR);
	sigemptyset(&empty);assert(sigprocmask(SIG_SETMASK,&empty,NULL)==0);
	requested_opts=OPT_q;hang_resolver=1;ntp_init(argv);_exit(0);
}
static int _eval(char *const argv[],char *path,int timeout,int *pid)
{
	pid_t child;
	assert(!strcmp(argv[0],"/usr/sbin/ntpd") && !strcmp(argv[1],"-qt") &&
	       !strcmp(argv[2],"-S") && !strcmp(argv[3],NTPC_DONE_SCRIPT) &&
	       !strcmp(argv[4],"-p") && argv[5] && !argv[6] && !path && timeout==15 && pid);
	launches++;snprintf(launched_server,sizeof(launched_server),"%s",argv[5]);
	if(launch_failure)return EAGAIN;
	child=fork();assert(child>=0);
	if(!child)child_init();
	*pid=(int)child;return 0;
}
#define waitpid fixture_waitpid
/* NTP_WATCHDOG_FUNCTIONS */
#undef waitpid

static double monotonic(void)
{ struct timespec t;assert(clock_gettime(CLOCK_MONOTONIC,&t)==0);return t.tv_sec+t.tv_nsec/1e9; }
static void wait_ready(void)
{ double end=monotonic()+2;while(!*resolver_ready && monotonic()<end)usleep(1000);assert(*resolver_ready); }
static int stop_child(void)
{
	int status;pid_t pid=ntpc_launch_pid;assert(pid>0);
	assert(kill(pid,SIGTERM)==0);while(waitpid(pid,&status,0)<0)assert(errno==EINTR);
	ntpc_launch_pid=-1;assert(WIFSIGNALED(status)&&WTERMSIG(status)==SIGTERM);return status;
}
static void timer_handler(int sig)
{
	assert(sig==SIGALRM);if(feeds<16)feed_ticks[feeds]=monotonic();feeds++;
	if(!feeds_stop)ntpc_handler();
}
static void free_peers(void)
{
	while(G.ntp_peers){peer_t *p=(peer_t *)llist_pop(&G.ntp_peers);free(p->p_lsa);free(p->p_dotted);free(p);}
}
int main(int argc,char **argv)
{
	const char *name;int status=0, timed=0;double start=monotonic(),elapsed,gap=0;
	pid_t child;char *ntp_argv[]={(char *)"ntpd",NULL};
	assert(argc==2);name=argv[1];
	resolver_ready=mmap(NULL,sizeof(*resolver_ready),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
	assert(resolver_ready!=MAP_FAILED);*resolver_ready=0;
	if(!strncmp(name,"init-",5)) {
		requested_opts=OPT_q;
		if(strstr(name,"noq"))requested_opts=0;
		if(strstr(name,"foreground"))requested_opts|=OPT_n;
		configured=strstr(name,"config")!=NULL;
		if(strstr(name,"timeout") || strstr(name,"ignored") || strstr(name,"blocked")) {
			hang_config=configured;hang_resolver=!configured;timed=1;
		}
		production=strstr(name,"production")!=NULL;
		fault=strstr(name,"sigaction-fail")?1:strstr(name,"mask-fail")?2:0;
		if(timed || fault) {
			child=fork();assert(child>=0);
			if(!child) {
				if(strstr(name,"ignored"))assert(signal(SIGALRM,SIG_IGN)!=SIG_ERR);
				if(strstr(name,"blocked")){sigset_t mask;sigemptyset(&mask);sigaddset(&mask,SIGALRM);assert(!sigprocmask(SIG_BLOCK,&mask,NULL));}
				ntp_init(ntp_argv);_exit(0);
			}
			while(waitpid(child,&status,0)<0)assert(errno==EINTR);
			if(timed)assert(WIFSIGNALED(status)&&WTERMSIG(status)==SIGALRM && *resolver_ready);
			else assert(WIFEXITED(status)&&WEXITSTATUS(status)==111 && !*resolver_ready);
		} else {
			ntp_init(ntp_argv);initialized=1;
			assert(resolved==1 && daemonized==!(requested_opts&OPT_n));
			assert(alarms[0]==10 && alarms[1]==0 && alarm_count==((requested_opts&OPT_q)?3:2));
			if(requested_opts&OPT_q)assert(alarms[2]==10 && (option_mask32&OPT_qq));
			else assert(alarm(0)==0);
			if(!strcmp(name,"init-q-first-reply")){ntp_first_reply();ntp_first_reply();assert(alarm_count==4 && alarms[3]==50 && !(option_mask32&OPT_qq));}
			if(!(requested_opts&OPT_q)){ntp_first_reply();assert(alarm_count==2);}
			free_peers();
		}
	} else if(!strcmp(name,"refresh-inhibited") || !strcmp(name,"refresh-poststop-inhibited")) {
		inhibited=!strcmp(name,"refresh-inhibited");inhibit_after_stop=!inhibited;
		refresh_ntp();assert(!launches && stops==inhibit_after_stop);
	} else if(!strcmp(name,"refresh-fork-fail")) {
		launch_failure=1;refresh_ntp();assert(launches==1 && ntpc_launch_pid==-1 && log_count==1);
	} else if(!strncmp(name,"reap-",5)) {
		if(!strcmp(name,"reap-exited")) {double until=monotonic()+2;child=fork();assert(child>=0);if(!child)_exit(0);ntpc_launch_pid=(int)child;while(ntpc_reap_launcher() && monotonic()<until)usleep(1000);assert(ntpc_launch_pid==-1);}
		else {ntpc_launch_pid=1234;wait_fault=!strcmp(name,"reap-echild")?ECHILD:!strcmp(name,"reap-eintr")?EINTR:EIO;assert(ntpc_reap_launcher()==(wait_fault!=ECHILD));assert(ntpc_launch_pid==(wait_fault==ECHILD?-1:1234));}
	} else if(!strcmp(name,"disabled-reaps")) {
		ntpc_launch_pid=1234;wait_fault=ECHILD;mock_period=0;ntpc_handler();assert(ntpc_launch_pid==-1 && !launches && !stops);
	} else if(!strcmp(name,"timer-async-feed")) {
		struct sigaction sa;struct itimerval timer;
		memset(&sa,0,sizeof(sa));sa.sa_handler=timer_handler;sigemptyset(&sa.sa_mask);assert(!sigaction(SIGALRM,&sa,NULL));
		memset(&timer,0,sizeof(timer));timer.it_value.tv_usec=50000;timer.it_interval=timer.it_value;assert(!setitimer(ITIMER_REAL,&timer,NULL));
		while(feeds<6) { pause(); }
		feeds_stop=1;memset(&timer,0,sizeof(timer));assert(!setitimer(ITIMER_REAL,&timer,NULL));
		for(int i=1;i<6;i++)if(feed_ticks[i]-feed_ticks[i-1]>gap)gap=feed_ticks[i]-feed_ticks[i-1];
		assert(launches==1 && feeds==6 && gap<0.75 && *resolver_ready);status=stop_child();
	} else if(!strcmp(name,"refresh-busy-no-overlap") || !strcmp(name,"stop-resolving-no-pidfile") ||
	          !strcmp(name,"refresh-server-fallback") || !strcmp(name,"refresh-server-alternation")) {
		if(!strcmp(name,"refresh-server-fallback"))server0[0]=server1[0]='\0';
		refresh_ntp();wait_ready();assert(launches==1 && ntpc_launch_pid>0);
		if(!strcmp(name,"refresh-busy-no-overlap")){refresh_ntp();assert(launches==1 && stops==1);}
		if(!strcmp(name,"refresh-server-fallback"))assert(!strcmp(launched_server,"pool.ntp.org"));
		status=stop_child();
		if(!strcmp(name,"refresh-server-alternation")){
			assert(!strcmp(launched_server,"first.example.invalid"));*resolver_ready=0;
			refresh_ntp();wait_ready();assert(!strcmp(launched_server,"second.example.invalid")&&launches==2);status=stop_child();
		}
	} else assert(!"unknown case");
	elapsed=monotonic()-start;
	if(timed)assert(elapsed>=(production?9.5:0.8) && elapsed<(production?13.0:3.0));
	printf("{\"case\":\"%s\",\"status\":%d,\"elapsed_ms\":%ld,\"initialized\":%d,\"timed_out\":%d,\"resolver_reached\":%d,\"launches\":%d,\"stops\":%d,\"feeds\":%d,\"largest_feed_gap_ms\":%ld,\"daemonized\":%d,\"resolved\":%d,\"alarms\":[%d,%d,%d,%d],\"alarm_count\":%d,\"launcher_owned\":%d}\n",
	       name,status,(long)(elapsed*1000),initialized,timed,*resolver_ready,launches,stops,feeds,(long)(gap*1000),daemonized,resolved,alarms[0],alarms[1],alarms[2],alarms[3],alarm_count,ntpc_launch_pid>0);
	munmap((void *)resolver_ready,sizeof(*resolver_ready));return 0;
}
