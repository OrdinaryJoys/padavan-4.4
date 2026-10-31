"""Actual native DNS models, immutable public files; no sockets or router IO."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_httpd_regressions import function

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'trunk/user/dnsmasq/dnsmasq-2.93'

DRIVER=r'''
#include <assert.h>
int fixture_fail_after,fixture_allocations,fixture_clock_jump,fixture_clock_calls,fixture_phase,fixture_opens[4];
static int fixture_effects,fixture_scripts;
unsigned int fixture_cache_pool_nodes(void);
static void fixture_update_configs(struct dhcp_config *p){(void)p;fixture_effects++;}
static void fixture_update_leases(void){fixture_effects++;}
static void fixture_update_file(time_t now){(void)now;fixture_effects++;}
static void fixture_update_dns(int force){(void)force;fixture_effects++;}
static void fixture_rerun(void){fixture_scripts++;}
void fixture_before_validate(void){
 if(fixture_phase==1&&getenv("K2P_RELOAD_RACE")){
  const char *path=getenv("K2P_RELOAD_TARGET"),*replacement=getenv("K2P_RELOAD_RACE");
  assert(path&&replacement&&rename(replacement,path)==0);fixture_phase=2;
 }
}
int fixture_record_open(const char *path,int flags,...){
 const char *keys[]={"H1","H2","DH","OP"};unsigned i;char key[80];
 for(i=0;i<4;i++){snprintf(key,sizeof(key),"K2P_RELOAD_%s",keys[i]);
  if(getenv(key)&&!strcmp(path,getenv(key)))fixture_opens[i]++;}
 return open(path,flags);
}
static void fixture_remove_directory(const char *path){
 DIR *dir=opendir(path);struct dirent *entry;char child[PATH_MAX];
 if(!dir)return;
 while((entry=readdir(dir)))if(strcmp(entry->d_name,".")&&strcmp(entry->d_name,"..")){
  snprintf(child,sizeof(child),"%s/%s",path,entry->d_name);assert(unlink(child)==0);
 }
 assert(!closedir(dir)&&!rmdir(path));
}
static void fixture_install(const char *suffix){
 const char *keys[]={"H1","H2","DH","OP"};unsigned i;char key[80];
 for(i=0;i<4;i++){const char *path,*input;
  snprintf(key,sizeof(key),"K2P_RELOAD_%s",keys[i]);path=getenv(key);
  snprintf(key,sizeof(key),"K2P_RELOAD_%s_%s",keys[i],suffix);input=getenv(key);
  if(path&&input){struct stat st;
   if(!stat(path,&st)&&S_ISDIR(st.st_mode))fixture_remove_directory(path);
   if(!stat(input,&st)&&S_ISDIR(st.st_mode))assert(unlink(path)==0);
   assert(rename(input,path)==0);
  }
 }
}
static void fixture_print(const char *stage,int accepted){
 struct crec *entry;struct dhcp_config *config;struct dhcp_opt *opt;
 char one[64]="none",two[64]="none",address[64]="none",value[256]="none";
 entry=cache_find_by_name(NULL,"first.fixture",0,F_IPV4);
 if(entry&&(entry->flags&F_HOSTS))inet_ntop(AF_INET,&entry->addr.addr4,one,sizeof(one));
 entry=cache_find_by_name(NULL,"second.fixture",0,F_IPV4);
 if(entry&&(entry->flags&F_HOSTS))inet_ntop(AF_INET,&entry->addr.addr4,two,sizeof(two));
 for(config=daemon->dhcp_conf;config;config=config->next)
  if(config->flags&CONFIG_ADDR){inet_ntop(AF_INET,&config->addr,address,sizeof(address));break;}
 for(opt=daemon->dhcp_opts;opt;opt=opt->next)
  if(opt->opt==15){assert(opt->len<sizeof(value));memcpy(value,opt->val,opt->len);value[opt->len]=0;break;}
 printf("{\"stage\":\"%s\",\"accepted\":%d,\"first\":\"%s\",\"second\":\"%s\",\"dhcp\":\"%s\",\"option15\":\"%s\",\"effects\":%d,\"scripts\":%d,\"soa\":%u,\"metric\":%u,\"opens\":[%d,%d,%d,%d]}\n",
 stage,accepted,one,two,address,value,fixture_effects,fixture_scripts,daemon->soa_sn,daemon->metrics[METRIC_DNS_CACHE_INSERTED],fixture_opens[0],fixture_opens[1],fixture_opens[2],fixture_opens[3]);fflush(stdout);
}
'''

REPLAY=r'''
  if(getenv("K2P_RELOAD_FIXTURE")){
    const char *fault=getenv("K2P_RELOAD_FAULT"),*target=getenv("K2P_RELOAD_TARGET");
    int accepted,cycles=1,i;unsigned int pool_nodes;struct dhcp_config *permanent;
    daemon->packet_buff_sz=daemon->edns_pktsz+MAXDNAME+RRFIXEDSZ;
    daemon->packet=safe_malloc(daemon->packet_buff_sz);cache_init();
    /* Only the group predicate is synthetic; propagation callbacks below
     * are inert. No DHCP socket, lease database, timer or daemon starts. */
    daemon->dhcp=(struct dhcp_context *)1;
    log_start(NULL,-1);
    accepted=clear_cache_and_reload(1);assert(accepted);fixture_print("initial",accepted);
    fixture_effects=fixture_scripts=0;daemon->soa_sn=100;daemon->metrics[METRIC_DNS_CACHE_INSERTED]=123;
    permanent=daemon->dhcp_conf;
    (void)permanent;
    fixture_install("NEW");
    if(fault&&!strcmp(fault,"fifo")){assert(target&&unlink(target)==0&&mkfifo(target,0600)==0);}
    if(fault&&!strcmp(fault,"missing")){assert(target&&unlink(target)==0);}
    fixture_fail_after=getenv("K2P_RELOAD_ALLOC_FAIL")?atoi(getenv("K2P_RELOAD_ALLOC_FAIL")):0;
    fixture_clock_jump=getenv("K2P_RELOAD_CLOCK_JUMP")?atoi(getenv("K2P_RELOAD_CLOCK_JUMP")):0;
    fixture_allocations=fixture_clock_calls=0;memset(fixture_opens,0,sizeof(fixture_opens));fixture_phase=1;
    if(getenv("K2P_RELOAD_EVENT")){
      int fds[2];assert(pipe(fds)==0);send_event(fds[1],EVENT_RELOAD,0,NULL);close(fds[1]);
      async_event(fds[0],2);close(fds[0]);accepted=fixture_effects!=0;
    }else accepted=clear_cache_and_reload(2);
    fixture_print("attempt",accepted);
    fixture_fail_after=fixture_clock_jump=0;fixture_phase=0;memset(fixture_opens,0,sizeof(fixture_opens));
    fixture_install("FIX");fixture_effects=fixture_scripts=0;
    accepted=clear_cache_and_reload(3);assert(accepted);fixture_print("repaired",accepted);
    if(getenv("K2P_RELOAD_CYCLES"))cycles=atoi(getenv("K2P_RELOAD_CYCLES"));
    pool_nodes=fixture_cache_pool_nodes();
    for(i=1;i<cycles;i++){accepted=clear_cache_and_reload(i+3);assert(accepted);assert(fixture_cache_pool_nodes()==pool_nodes);}
    return 0;
  }
'''

ALLOC_SHIM=r'''
extern int fixture_fail_after,fixture_allocations,fixture_clock_jump,fixture_clock_calls,fixture_phase,fixture_opens[4];
void fixture_before_validate(void);
static void *fixture_malloc(size_t size){
 if(fixture_fail_after&&++fixture_allocations==fixture_fail_after){errno=ENOMEM;return NULL;}
 return malloc(size);
}
static void *fixture_calloc(size_t n,size_t size){
 if(fixture_fail_after&&++fixture_allocations==fixture_fail_after){errno=ENOMEM;return NULL;}
 return calloc(n,size);
}
static int fixture_clock(clockid_t id,struct timespec *now){
 int result=clock_gettime(id,now);if(!result&&fixture_clock_jump&&++fixture_clock_calls>=fixture_clock_jump)now->tv_sec+=11;
 return result;
}
#define malloc fixture_malloc
#define calloc fixture_calloc
#define clock_gettime fixture_clock
'''


class DNSReloadTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory(prefix='k2p-reload-code-')
        cls.tree=Path(cls.build.name).resolve()/'source'
        shutil.copytree(SOURCE,cls.tree,ignore=shutil.ignore_patterns('*.o','dnsmasq','dnsmasq_baseline','.copts_*'))
        path=cls.tree/'src/dnsmasq.c';text=path.read_text()
        text=text.replace('#include "reload_file.h"','#include "reload_file.h"\n'+DRIVER,1)
        body=function(text,'clear_cache_and_reload')
        modified=body.replace('dhcp_update_configs(', 'fixture_update_configs(').replace('lease_update_from_configs()', 'fixture_update_leases()').replace('lease_update_file(', 'fixture_update_file(').replace('lease_update_dns(', 'fixture_update_dns(')
        text=text.replace(body,modified,1)
        body=function(text,'async_event');text=text.replace(body,body.replace('rerun_scripts()', 'fixture_rerun()'),1)
        needle='  read_opts(argc, argv, compile_opts);';assert text.count(needle)==1
        text=text.replace(needle,needle+'\n'+REPLAY,1);path.write_text(text)
        path=cls.tree/'src/cache.c';text=path.read_text()
        text+='\nunsigned int fixture_cache_pool_nodes(void) {struct crec *c;struct nameblock *b;unsigned int count=0; for(c=config_spare;c;c=c->next)count++;for(b=hostblocks;b;b=b->next)count++;return count;}\n'
        path.write_text(text)
        path=cls.tree/'src/reload_file.c';text=path.read_text();text=text.replace('#include "reload_file.h"','#include "reload_file.h"\n'+ALLOC_SHIM,1)
        text=text.replace('int dns_reload_validate(void)\n{','int dns_reload_validate(void)\n{\n  fixture_before_validate();',1);path.write_text(text)
        path=cls.tree/'src/runtime_file.c';text=path.read_text();text=text.replace('#include "runtime_file.h"','#include "runtime_file.h"\nextern int fixture_record_open(const char *,int,...);\n#define open(...) fixture_record_open(__VA_ARGS__)',1);path.write_text(text)
        options='-DNO_DHCP6 -DNO_TFTP -DNO_INOTIFY -DNO_AUTH -DNO_LOOP'
        result=subprocess.run(['make','-j4','CC=clang','COPTS='+options,
                               'CFLAGS=-O1 -g -Wall -Wextra -fsanitize=address,undefined',
                               'LDFLAGS=-fsanitize=address,undefined'],cwd=cls.tree,capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
        cls.binary=cls.tree/'src/dnsmasq'

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='k2p-reload-case-')
        self.root=Path(self.temp.name).resolve()
        self.paths={key:self.root/key.lower() for key in ('H1','H2','DH','OP')}
        self.old={'H1':'192.0.2.51 first.fixture\n','H2':'192.0.2.61 second.fixture\n',
                  'DH':'02:00:00:00:00:51,192.0.2.51,oldclient\n','OP':'15,old.fixture\n'}
        self.new={'H1':'192.0.2.52 first.fixture\n','H2':'192.0.2.62 second.fixture\n',
                  'DH':'02:00:00:00:00:52,192.0.2.52,newclient\n','OP':'15,new.fixture\n'}

    def tearDown(self):self.temp.cleanup()

    def replay(self,key=None,fault=None,bad=None,allocation=None,clock=None,event=False,cycles=None,race=False,directory_files=None):
        env={**os.environ,'K2P_RELOAD_FIXTURE':'1','ASAN_OPTIONS':'detect_leaks='+('1' if sys.platform.startswith('linux') else '0')}
        for name,path in self.paths.items():
            path.write_text(self.old[name]);env['K2P_RELOAD_'+name]=str(path)
            for suffix in ('NEW','FIX'):
                replacement=self.root/(name.lower()+'.'+suffix.lower())
                replacement.write_text((bad.get(name,self.new[name]) if isinstance(bad,dict) else bad) if suffix=='NEW' and bad is not None and (isinstance(bad,dict) or name==key) else self.new[name])
                env['K2P_RELOAD_'+name+'_'+suffix]=str(replacement)
        if directory_files is not None:
            replacement=Path(env['K2P_RELOAD_H1_NEW']);replacement.unlink();replacement.mkdir()
            for index in range(directory_files):(replacement/('%04d'%index)).write_text('192.0.2.52 first.fixture\n')
        if key:env['K2P_RELOAD_TARGET']=str(self.paths[key])
        if race:
            replacement=self.root/'raced-input';replacement.write_text('192.0.2.99 first.fixture\n')
            env['K2P_RELOAD_RACE']=str(replacement)
        if fault:env['K2P_RELOAD_FAULT']=fault
        if allocation:env['K2P_RELOAD_ALLOC_FAIL']=str(allocation)
        if clock:env['K2P_RELOAD_CLOCK_JUMP']=str(clock)
        if event:env['K2P_RELOAD_EVENT']='1'
        if cycles:env['K2P_RELOAD_CYCLES']=str(cycles)
        config=self.root/'main'
        config.write_text('no-hosts\nno-resolv\nlog-facility='+str(self.root/'log')+'\n'+
                          'addn-hosts='+str(self.paths['H1'])+'\naddn-hosts='+str(self.paths['H2'])+'\n'+
                          'dhcp-hostsfile='+str(self.paths['DH'])+'\ndhcp-optsfile='+str(self.paths['OP'])+'\n')
        result=subprocess.run([str(self.binary),'-C',str(config)],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('runtime error:',result.stderr)
        rows=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        self.assertEqual([row['stage'] for row in rows],['initial','attempt','repaired'])
        self.assert_state(rows[0],False);self.assert_state(rows[2],True)
        return rows,result

    def assert_state(self,row,new):
        self.assertEqual((row['first'],row['second'],row['dhcp'],row['option15']),
                         ('192.0.2.52','192.0.2.62','192.0.2.52','new.fixture') if new else
                         ('192.0.2.51','192.0.2.61','192.0.2.51','old.fixture'))

    def assert_rejected(self,**kwargs):
        rows,result=self.replay(**kwargs);row=rows[1]
        self.assertEqual(row['accepted'],0)
        self.assert_state(row,False)
        self.assertEqual((row['effects'],row['scripts'],row['soa'],row['metric']),(0,0,100,123))
        self.assertTrue(all(value<=1 for value in row['opens']),row['opens'])
        self.assertIn('reload transaction rejected; previous hosts/DHCP configuration retained',(self.root/'log').read_text())
        return rows,result

    def test_all_four_candidate_files_commit_together(self):
        rows,_=self.replay();self.assert_state(rows[1],True);self.assertEqual(rows[1]['effects'],4)
        self.assertEqual(rows[1]['opens'],[1,1,1,1])

    def test_second_hosts_fifo_keeps_first_hosts_and_both_dhcp_models(self):self.assert_rejected(key='H2',fault='fifo')
    def test_first_hosts_missing_keeps_all_old_models(self):self.assert_rejected(key='H1',fault='missing')
    def test_bad_hosts_line_aborts_after_an_earlier_valid_file(self):self.assert_rejected(key='H2',bad='not-an-address bad.fixture\n')
    def test_bad_hosts_name_aborts(self):self.assert_rejected(key='H2',bad='192.0.2.62 '+('x'*64)+'.fixture\n')
    def test_dhcp_hosts_fifo_keeps_hosts_and_options(self):self.assert_rejected(key='DH',fault='fifo')
    def test_dhcp_options_fifo_keeps_hosts_and_reservations(self):self.assert_rejected(key='OP',fault='fifo')
    def test_dhcp_hosts_partial_syntax_error_discards_entire_candidate(self):self.assert_rejected(key='DH',bad=self.new['DH']+'this:is:bad:hex,invalid\n')
    def test_dhcp_options_partial_syntax_error_discards_entire_candidate(self):self.assert_rejected(key='OP',bad='15,new.fixture\nnot-an-option,value\n')
    def test_dhcp_input_over_two_mib_is_rejected(self):self.assert_rejected(key='OP',bad='#\n'*(1024*1024+1))
    def test_allocation_failures_before_and_during_parse_preserve_old_models(self):
        for number in (1,5,15,25,35):
            with self.subTest(number=number):self.assert_rejected(allocation=number)
    def test_shared_cooperative_clock_failure_preserves_old_models(self):self.assert_rejected(clock=5)
    def test_real_event_failure_does_not_bump_soa_or_rerun_scripts(self):self.assert_rejected(key='H2',fault='fifo',event=True)
    def test_valid_empty_hosts_file_explicitly_removes_only_that_source(self):
        rows,_=self.replay(key='H1',bad='');self.assertEqual(rows[1]['accepted'],1)
        self.assertEqual((rows[1]['first'],rows[1]['second']),('none','192.0.2.62'))
    def test_valid_empty_dhcp_hosts_explicitly_clears_dynamic_reservations(self):
        rows,_=self.replay(key='DH',bad='');self.assertEqual(rows[1]['accepted'],1)
        self.assertEqual(rows[1]['dhcp'],'none');self.assertEqual(rows[1]['option15'],'new.fixture')
    def test_valid_empty_options_explicitly_clears_dynamic_options(self):
        rows,_=self.replay(key='OP',bad='');self.assertEqual(rows[1]['accepted'],1)
        self.assertEqual(rows[1]['option15'],'none');self.assertEqual(rows[1]['dhcp'],'192.0.2.52')
    def test_path_replacement_after_parse_is_detected_before_any_commit(self):self.assert_rejected(key='H1',race=True)
    def test_single_sixteen_mib_hosts_snapshot_remains_supported(self):
        body=('#'+(' '*62)+'\n')*(262144)
        self.assertEqual(len(body),16*1024*1024)
        rows,_=self.replay(key='H1',bad=body);self.assertEqual(rows[1]['accepted'],1)
        self.assertEqual(rows[1]['first'],'none')
    def test_aggregate_input_budget_rejects_without_partial_models(self):
        body=('#'+(' '*62)+'\n')*(262144)
        self.assert_rejected(bad={'H1':body,'H2':body})
    def test_expanded_directory_file_count_is_bounded_and_preserves_old(self):self.assert_rejected(directory_files=130)
    def test_regular_directory_members_commit_without_rereading(self):
        rows,_=self.replay(directory_files=3);self.assert_state(rows[1],True)
    def test_repeated_success_reuses_valid_live_models(self):self.replay(cycles=40)


class DNSReloadDirectoryBalanceTests(unittest.TestCase):
    """Real expand_filelist with inert stat/scandir and tracked libc entries."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-scandir-balance-')
        root=Path(cls.temp.name)
        text=(SOURCE/'src/option.c').read_text()
        body=function(text.replace('struct hostsfile *expand_filelist','char *expand_filelist',1),'expand_filelist').replace('char *expand_filelist','struct hostsfile *expand_filelist',1)
        prelude=r"""
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#define AH_DIR 1
#define AH_INACTIVE 2
#define SRC_AH 10
#define LOG_ERR 3
#define _(x) x
struct hostsfile {struct hostsfile *next;char *fname;unsigned int index,flags;};
static void *entries[4];static int live[4],outstanding,allocation,fail_at,scan_fail;
static int fixture_stat(const char *path,struct stat *st){memset(st,0,sizeof(*st));st->st_mode=!strcmp(path,"/fixture")?S_IFDIR:S_IFREG;return 0;}
static void fixture_log(int priority,const char *fmt,...){(void)priority;(void)fmt;}
static int file_filter(const struct dirent *entry){(void)entry;return 1;}
static int fixture_scan(const char *path,struct dirent ***out,int(*filter)(const struct dirent *),int(*sort)(const struct dirent **,const struct dirent **)){
 unsigned i;(void)path;(void)filter;(void)sort;
 if(scan_fail){errno=EIO;return -1;}
 *out=malloc(3*sizeof(**out));entries[0]=*out;live[0]=1;outstanding++;
 for(i=0;i<3;i++){(*out)[i]=calloc(1,sizeof(struct dirent));snprintf((*out)[i]->d_name,sizeof((*out)[i]->d_name),"file%u",i);entries[i+1]=(*out)[i];live[i+1]=1;outstanding++;}
 return 3;
}
static void fixture_free(void *ptr){unsigned i;if(!ptr)return;for(i=0;i<4;i++)if(entries[i]==ptr&&live[i]){live[i]=0;outstanding--;break;}free(ptr);}
static void *fixture_malloc(size_t size){if(fail_at&&++allocation==fail_at)return NULL;return calloc(1,size);}
#define stat fixture_stat
#define scandir fixture_scan
#define my_syslog fixture_log
#define whine_malloc fixture_malloc
#define free fixture_free
"""
        driver=r"""
int main(int argc,char **argv){struct hostsfile initial={NULL,"/fixture",10,0},*list,*next;int i;
 if(argc>1)fail_at=atoi(argv[1]);if(argc>2)scan_fail=1;
 for(i=0;i<20;i++){
  list=expand_filelist(&initial);assert(list==&initial);
  if(outstanding)break;
 }
 printf("{\"outstanding\":%d,\"rounds\":%d}\n",outstanding,i);
 for(list=initial.next;list;list=next){next=list->next;free(list->fname);free(list);}
 return 0;
}
"""
        # stat is a function-like macro so struct stat remains the real type.
        prelude=prelude.replace('#define stat fixture_stat','#define stat(...) fixture_stat(__VA_ARGS__)')
        path=root/'probe.c';path.write_text(prelude+body+'\n'+driver)
        cls.binary=root/'probe'
        result=subprocess.run(['clang','-std=c99','-D_DARWIN_C_SOURCE','-D_DEFAULT_SOURCE','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path),'-o',str(cls.binary)],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def run_probe(self,*args):
        result=subprocess.run([str(self.binary),*map(str,args)],capture_output=True,text=True,timeout=5,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        row=json.loads(result.stdout);self.assertEqual(row,{'outstanding':0,'rounds':20})
    def test_scandir_entries_and_vector_are_freed_across_reloads(self):self.run_probe()
    def test_scandir_entries_freed_on_both_model_allocation_failures(self):
        for number in (1,2):
            with self.subTest(number=number):self.run_probe(number)
    def test_scandir_failure_with_no_output_vector_is_safe(self):self.run_probe(0,'fail')


if __name__=='__main__':unittest.main()
