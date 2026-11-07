"""Real forwarding publication/guard bodies with inert RCU/SRCU backends.

All 31 callers are source-bound; only the named control reader executes whole.
The map user and grace-period implementation are explicit native models, not
kernel scheduler, packet path, provider module, or hardware execution.
"""
import hashlib
import re
from pci_bind_guard_harness import masked, block_end

BASE = 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
CALLERS = {
    'os/linux/rt_profile.c': ('ApCliLinkCoverRxPolicy', 'RTMPSendPackets', 'announce_802_3_packet'),
    'embedded/ap/ap.c': ('APStartUpForMbss', 'APStopByBss'),
    'embedded/ap/ap_apcli.c': ('ApCliIfDown', 'ApCliLinkDown', 'ApCliLinkUp', 'IsApCliLinkUp', 'apcli_inf_open'),
    'embedded/ap/ap_assoc.c': ('IAPP_L2_Update_Frame_Send',),
    'embedded/ap/ap_data.c': ('ap_fp_tx_pkt_allowed', 'ap_rx_pkt_foward', 'ap_tx_pkt_allowed'),
    'embedded/ap/ap_repeater.c': ('ReptTxPktCheckHandler',),
    'embedded/common/cmm_data.c': ('announce_or_forward_802_3_pkt', 'indicate_802_11_pkt'),
    'embedded/common/cmm_info.c': ('Set_PacketSourceDeleteEntry', 'Set_PacketSourceShowEntry',
        'Set_WifiFwdAccessSchedule_Proc', 'Set_WifiFwdBpdu_Proc', 'Set_WifiFwdBridge_Proc',
        'Set_WifiFwdDeleteEntry', 'Set_WifiFwdHijack_Proc', 'Set_WifiFwdRepDevice',
        'Set_WifiFwdShowEntry', 'Set_WifiFwd_Proc', 'WifiFwdSet'),
    'embedded/common/rtmp_init.c': ('UserCfgInit',),
    'embedded/mgmt/mgmt_entrytb.c': ('MacTableDeleteEntry', 'MacTableInsertEntry'),
}
SOURCE_PATHS = {p: BASE + p for p in CALLERS}
SOURCE_PATHS.update({
    'header': BASE + 'include/os/rt_linux.h',
    'core_srcu': 'trunk/linux-4.4.x/kernel/rcu/srcu.c',
    'srcu_header': 'trunk/linux-4.4.x/include/linux/srcu.h',
    'config': 'trunk/configs/boards/K2P/kernel-4.4.x.config',
})
FUNCTION_NAMES = ('wifi_fwd_read_begin', 'wifi_fwd_read_end', 'wifi_fwd_drain',
                  'wifi_fwd_register', 'wifi_fwd_unregister')
BASELINE_COMMIT = '60ae6bf98bd46b68c648620c599f1aa78073131e'
BASELINE_SHA256 = {
    'wifi_fwd_register.c': '6d8ec3c3063bb030f27a4bf9f2de2eeaf4d38c8abbaf77c739428eeff2dd4f4f',
    'wifi_fwd_unregister.c': '07d8a495c878ec81db3fd3c3c5ff7c1cf02ccff8e99323da17ec639f3f497ed5',
    'Set_WifiFwdShowEntry.c': '069401939065dcc183a7e847d291ac571f6f1468eaf7b04526363fcfb85f0029',
}


def function(text, name):
    clean = masked(text)
    pattern = r'^(?:(?:static|inline)\s+)?(?:[A-Za-z_]\w*\s+|\*\s*)+?' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{'
    matches = list(re.finditer(pattern, clean, re.M))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous forwarding function: ' + name)
    start = matches[0].start()
    return text[start:block_end(text, clean.index('{', start))]


def declaration(text, name):
    clean = masked(text)
    matches = list(re.finditer(r'(?m)^struct\s+' + name + r'\s*\{', clean))
    if len(matches) != 1:
        raise ValueError('One forwarding declaration required: ' + name)
    start = matches[0].start();end = block_end(text, clean.index('{', start))
    if not re.match(r'\s*;', clean[end:]):
        raise ValueError('Declaration terminator absent')
    return text[start:end] + ';'


def parts(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact forwarding input set required')
    profile = texts['os/linux/rt_profile.c'];header = texts['header']
    for flag in ('CONFIG_SRCU=y', 'CONFIG_CHIP_MT7615E=y', 'CONFIG_MT7615_AP=m'):
        if flag not in texts['config'].splitlines():
            raise ValueError('Configured forwarding/SRCU profile differs')
    if 'wf_drv_tbl' in ''.join(masked(texts[p]) for p in CALLERS):
        raise ValueError('Unowned mutable forwarding table remains')
    bodies = {p + ':' + n: function(texts[p], n) for p, names in CALLERS.items() for n in names}
    for name, body in bodies.items():
        clean = masked(body);opening = clean.index('{') + 1
        if clean.count('WIFI_FWD_GUARD(wf_fwd_snapshot);') != 1:
            raise ValueError('Exactly one whole-caller guard required: ' + name)
        if not re.match(r'\s*#if defined\(CONFIG_WIFI_PKT_FWD\) \|\| defined\(CONFIG_WIFI_PKT_FWD_MODULE\)\s*WIFI_FWD_GUARD\(wf_fwd_snapshot\);\s*#endif', clean[opening:]):
            raise ValueError('Guard must precede every original caller statement: ' + name)
    calls = sum(len(re.findall(r'\bwf_fwd_snapshot->\w+\s*\(', masked(b))) for b in bodies.values())
    if calls != 47 or len(bodies) != 31:
        raise ValueError('All 47 direct calls and 31 full caller scopes required')
    macro_match = re.search(r'(?m)^#define WIFI_FWD_GUARD\(name\)[\s\S]*?(?=\n\n)', header)
    if not macro_match or 'cleanup(wifi_fwd_read_end)' not in macro_match[0]:
        raise ValueError('Automatic cleanup declaration required')
    start = profile.index('static DEFINE_MUTEX(wifi_fwd_writer_lock);')
    end = profile.index('static const struct wifi_fwd_func_table __rcu *wifi_fwd_published;', start)
    globals_ = profile[start:end] + 'static const struct wifi_fwd_func_table __rcu *wifi_fwd_published;'
    check_start = profile.index('#if !defined(CONFIG_SRCU)')
    checks = profile[check_start:profile.index('#include <linux/srcu.h>', check_start)]
    return dict(table=declaration(header, 'wifi_fwd_func_table'),
                guard=declaration(header, 'wifi_fwd_read_guard'), macro=macro_match[0],
                globals=globals_, checks=checks, callers=bodies,
                functions={n: function(profile, n) for n in FUNCTION_NAMES})


PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#define VOID void
#define INT int
#define TRUE 1
#define IN
typedef char RTMP_STRING;
typedef void RTMP_ADAPTER;
typedef void *PRTMP_ADAPTER;
#define CONFIG_SRCU 1
#define CONFIG_WIFI_PKT_FWD 1
#define __rcu
struct sk_buff; struct net_device; struct APCLI_BRIDGE_LEARNING_MAPPING_STRUCT;
struct delayed_work { int running,pending; };
struct srcu_struct { struct delayed_work work; };
#define DEFINE_STATIC_SRCU(n) static struct srcu_struct n = {{0,0}}
#define DEFINE_MUTEX(n) pthread_mutex_t n=PTHREAD_MUTEX_INITIALIZER
static pthread_mutex_t state=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv=PTHREAD_COND_INITIALIZER;
static __thread int context,thread_id;
static int readers[2],locks[2],unlocks[2],syncs[2],flushes,warnings,unsafe_code,unsafe_data;
static int entered,release_reader,writer_done,provider_live=1,map_ready,map_value=73,is_map;
static int pause_writer,release_writer,writer_attempts,writer_acquisitions,max_writers,active_writers;
static int pause_fast,fast_entered,release_fast,fast_reads;
static void lock_state(void){assert(!pthread_mutex_lock(&state));}
static void unlock_state(void){assert(!pthread_mutex_unlock(&state));}
static void wake(void){assert(!pthread_cond_broadcast(&cv));}
static void wait_state(void){assert(!pthread_cond_wait(&cv,&state));}
static void wait_value(int *p,int n){lock_state();while(*p<n)wait_state();unlock_state();}
static void after_pointer_read(void){if(thread_id!=7||!pause_fast||fast_reads++)return;lock_state();fast_entered=1;wake();while(!release_fast)wait_state();unlock_state();}
#define READ_ONCE(p) ({ __typeof__(p) value=__atomic_load_n(&(p),__ATOMIC_ACQUIRE);after_pointer_read();value; })
#define rcu_assign_pointer(p,v) __atomic_store_n(&(p),(v),__ATOMIC_RELEASE)
#define rcu_dereference(p) READ_ONCE(p)
#define srcu_dereference(p,s) ((void)(s),READ_ONCE(p))
static int in_atomic(void){return context==1;}
static int in_interrupt(void){return context==2||context==3;}
static int irqs_disabled(void){return context==4;}
static int warn_once(int bad){if(bad)warnings++;return bad;}
#define WARN_ON_ONCE(v) warn_once(!!(v))
static void rcu_read_lock(void){lock_state();readers[0]++;locks[0]++;unlock_state();}
static void rcu_read_unlock(void){lock_state();assert(readers[0]>0);readers[0]--;unlocks[0]++;wake();unlock_state();}
static int srcu_read_lock(struct srcu_struct *s){assert(!context);(void)s;lock_state();readers[1]++;locks[1]++;unlock_state();return 0;}
static void srcu_read_unlock(struct srcu_struct *s,int idx){assert(!context&&!idx);(void)s;lock_state();assert(readers[1]>0);readers[1]--;unlocks[1]++;wake();unlock_state();}
static void synchronize_rcu(void){lock_state();syncs[0]++;wake();while(readers[0])wait_state();if(thread_id==1&&pause_writer){entered=1;wake();while(!release_writer)wait_state();}unlock_state();}
static void synchronize_srcu(struct srcu_struct *s){lock_state();syncs[1]++;s->work.running=s->work.pending=1;wake();while(readers[1])wait_state();unlock_state();}
static void flush_delayed_work(struct delayed_work *w){lock_state();flushes++;w->running=w->pending=0;unlock_state();}
static void mutex_lock(pthread_mutex_t *m){lock_state();writer_attempts++;wake();unlock_state();assert(!pthread_mutex_lock(m));lock_state();writer_acquisitions++;active_writers++;if(active_writers>max_writers)max_writers=active_writers;unlock_state();}
static void mutex_unlock(pthread_mutex_t *m){lock_state();assert(active_writers==1);active_writers--;unlock_state();assert(!pthread_mutex_unlock(m));}
'''

SUFFIX = r'''
static void callback(void)
{
 lock_state();entered=1;wake();while(!release_reader)wait_state();
 if(!provider_live){unsafe_code++;}unlock_state();
}
static void feedback(void *ad,void **a,void **b,void **c)
{(void)ad;*a=&map_value;*b=NULL;*c=NULL;}
static void read_map(void)
{
#if BASELINE
 const struct wifi_fwd_func_table *snapshot=&wf_drv_tbl;
#else
 WIFI_FWD_GUARD(snapshot);
#endif
 void *a=NULL,*b=NULL,*c=NULL;
 if(snapshot->wf_fwd_feedback_map_table)snapshot->wf_fwd_feedback_map_table(NULL,&a,&b,&c);
 lock_state();map_ready=1;wake();while(!release_reader)wait_state();
 if(a){if(!provider_live)unsafe_data++;assert(*(int*)a==73);}unlock_state();
}
static int early(int value)
{
 WIFI_FWD_GUARD(snapshot);
 (void)snapshot;
 if(value==0)return 7;
 if(value==1)goto out;
 return 9;
out:return 8;
}
static void *reader_thread(void *arg)
{thread_id=7;context=(int)(intptr_t)arg;if(is_map)read_map();else Set_WifiFwdShowEntry(NULL,NULL);return NULL;}
static struct wifi_fwd_func_table table_a,table_b;
static void *unregister_thread(void *arg)
{(void)arg;wifi_fwd_unregister();lock_state();provider_live=0;writer_done=1;wake();unlock_state();return NULL;}
static void *register_thread(void *arg)
{thread_id=(int)(intptr_t)arg;wifi_fwd_register(thread_id==1?&table_a:&table_b);return NULL;}
int main(int argc,char **argv)
{
 pthread_t reader,writer,second;int i,ctx=0,all_fields=1;
 const char *name;struct wifi_fwd_read_guard g;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 (void)&wifi_fwd_slot;(void)&wifi_fwd_writer_lock;
 (void)wifi_fwd_drain;(void)mutex_lock;(void)mutex_unlock;(void)warn_once;
 memset(&table_a,0,sizeof(table_a));memset(&table_b,0,sizeof(table_b));
 FILL_TABLE
 table_b=table_a;
 table_a.wf_fwd_show_entry_hook=callback;table_a.wf_fwd_feedback_map_table=feedback;
 table_b.wf_fwd_show_entry_hook=NULL;
 if(!strcmp(name,"empty")){
  for(i=0;i<5;i++){context=i;g=wifi_fwd_read_begin();assert(g.table==&wifi_fwd_empty);wifi_fwd_read_end(&g);}
 }else if(!strcmp(name,"all-fields")){
  wifi_fwd_register(&table_b);g=wifi_fwd_read_begin();all_fields=!memcmp(g.table,&table_b,sizeof(table_b));wifi_fwd_read_end(&g);wifi_fwd_unregister();
 }else if(!strcmp(name,"repeat")){
  for(i=0;i<3;i++){wifi_fwd_register(&table_b);wifi_fwd_unregister();assert(!wifi_fwd_srcu.work.running&&!wifi_fwd_srcu.work.pending);}
 }else if(!strcmp(name,"early")){
  wifi_fwd_register(&table_b);for(context=0;context<5;context++)for(i=0;i<3;i++)assert(early(i)==i+7);context=0;assert(!readers[0]&&!readers[1]);wifi_fwd_unregister();
 }else if(!strcmp(name,"writers")){
  pause_writer=1;assert(!pthread_create(&writer,NULL,register_thread,(void*)1));wait_value(&entered,1);
  assert(!pthread_create(&second,NULL,register_thread,(void*)2));wait_value(&writer_attempts,2);
  lock_state();release_writer=1;wake();unlock_state();assert(!pthread_join(writer,NULL));assert(!pthread_join(second,NULL));
  g=wifi_fwd_read_begin();all_fields=!memcmp(g.table,&table_b,sizeof(table_b));wifi_fwd_read_end(&g);wifi_fwd_unregister();
 }else if(!strcmp(name,"atomic-writers")){
  for(context=1;context<5;context++){wifi_fwd_register(&table_b);wifi_fwd_unregister();}
  context=0;assert(!wifi_fwd_published);
 }else if(!strcmp(name,"late-reader")){
  wifi_fwd_register(&table_a);pause_fast=1;release_reader=1;
  assert(!pthread_create(&reader,NULL,reader_thread,NULL));wait_value(&fast_entered,1);
  wifi_fwd_unregister();provider_live=0;lock_state();release_fast=1;wake();unlock_state();
  assert(!pthread_join(reader,NULL));assert(!entered&&!unsafe_code);
 }else{
  if(!strcmp(name,"atomic"))ctx=1;else if(!strcmp(name,"irq"))ctx=2;else if(!strcmp(name,"bh"))ctx=3;else if(!strcmp(name,"irq-off"))ctx=4;
  if(!strcmp(name,"map"))is_map=1;
  wifi_fwd_register(&table_a);syncs[0]=syncs[1]=0;
  assert(!pthread_create(&reader,NULL,reader_thread,(void*)(intptr_t)ctx));
  wait_value(is_map?&map_ready:&entered,1);assert(!pthread_create(&writer,NULL,unregister_thread,NULL));
#if BASELINE
  wait_value(&writer_done,1);
#else
  lock_state();while(!syncs[ctx?0:1]&&!writer_done)wait_state();assert(!writer_done);unlock_state();
#endif
  lock_state();release_reader=1;wake();unlock_state();assert(!pthread_join(reader,NULL));assert(!pthread_join(writer,NULL));
 }
 assert(!readers[0]&&!readers[1]);
 assert(!wifi_fwd_published);
 printf("{\"unsafe_code\":%d,\"unsafe_data\":%d,\"all_fields\":%d,\"rcu_locks\":%d,\"srcu_locks\":%d,\"rcu_unlocks\":%d,\"srcu_unlocks\":%d,\"flushes\":%d,\"warnings\":%d,\"max_writers\":%d,\"running\":%d,\"pending\":%d}\n",unsafe_code,unsafe_data,all_fields,locks[0],locks[1],unlocks[0],unlocks[1],flushes,warnings,max_writers,wifi_fwd_srcu.work.running,wifi_fwd_srcu.work.pending);
 return 0;
}
'''
CASES = ('empty', 'all-fields', 'repeat', 'early', 'writers', 'atomic-writers', 'late-reader',
         'process', 'atomic', 'irq', 'bh', 'irq-off', 'map')


def generate_source(texts, baseline=None):
    p = parts(texts)
    # Real typed, noncalled stubs let the full 36-member copy be observed.
    callbacks = []
    fill = []
    for index, m in enumerate(re.finditer(r'(?m)^\s*(\w+(?:\s+\w+)*)\s*\(\*(\w+)\)\s*\(([^;]*)\);', p['table'])):
        ret, name, args = m.groups()
        params = []
        if args.strip() != 'void':
            for arg in args.split(','):
                n = re.search(r'(\w+)\s*$', arg).group(1)
                params.append('(void)' + n + ';')
        callbacks.append('static ' + ret + ' cb_' + name + '(' + args + '){' + ''.join(params) +
                         ('' if ret.strip() == 'void' else 'return 0;') + '}')
        fill.append('table_a.' + name + '=cb_' + name + ';')
    if len(fill) != 36:
        raise ValueError('All 36 real typed callback members required')
    f = dict(p['functions'])
    reader = function(texts['embedded/common/cmm_info.c'], 'Set_WifiFwdShowEntry')
    extra = ''
    if baseline:
        f['wifi_fwd_register'] = baseline['wifi_fwd_register.c'].rstrip()
        f['wifi_fwd_unregister'] = baseline['wifi_fwd_unregister.c'].rstrip()
        reader = baseline['Set_WifiFwdShowEntry.c'].rstrip()
        extra = 'static struct wifi_fwd_func_table wf_drv_tbl;\n'
    admission = 'if(!(' + '||'.join('!strcmp(name,"' + n + '")' for n in CASES) + '))return 91;'
    return (PREFIX + '\n' + p['checks'] + '\n' + p['table'] + '\n' + p['guard'] + '\n' +
            p['macro'] + '\n' + p['globals'] + '\n' + extra + '\n' +
            '\n'.join(f[n] for n in FUNCTION_NAMES) + '\n' + reader + '\n' +
            '\n'.join(callbacks) + '\n' +
            SUFFIX.replace('FILL_TABLE', '\n'.join(fill)).replace('CASE_ADMISSION', admission))


def manifest(texts):
    p = parts(texts)
    digest = lambda b: hashlib.sha256(b.encode()).hexdigest()
    return {'native_whole_functions': {n: digest(b) for n, b in p['functions'].items()},
            'native_control_reader': digest(function(texts['embedded/common/cmm_info.c'], 'Set_WifiFwdShowEntry')),
            'source_bound_callers': {n: digest(b) for n, b in p['callers'].items()},
            'source_only_kernel_srcu': {n: digest(function(texts['core_srcu'], n))
                                      for n in ('__synchronize_srcu', 'srcu_reschedule', 'process_srcu')},
            'table_declaration': digest(p['table']), 'guard_declaration': digest(p['guard']),
            'cleanup_macro': digest(p['macro']),
            'caller_count': 31, 'direct_calls': 47, 'abi_members': 36,
            'all_31_callers_executed': False, 'kernel_rcu_srcu_execution': False,
            'provider_module_or_hardware_execution': False}
