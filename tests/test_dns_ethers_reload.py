"""Real ethers/DHCP transaction regressions with private native source copies.

Only the copied ETHERSFILE constant and an early main replay are changed.
The replay returns before network listeners, daemonization, router I/O or
lease initialization. The original parser uses normal host entropy/time reads.
ASan/UBSan checks actual allocation/clone/free code; a repeated transaction
also asserts metadata bookkeeping is empty. This is not a full leak detector.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'trunk/user/dnsmasq/dnsmasq-2.93'

DRIVER = r'''
static void ethers_test_seed(void) {
  struct dhcp_config *c=safe_malloc(sizeof(*c));struct hwaddr_config *h,*h2;
  struct dhcp_netid_list *tag;struct dhcp_netid *filter;
  memset(c,0,sizeof(*c));
  c->flags=CONFIG_NAME|CONFIG_ADDR|CONFIG_CLID|CONFIG_TIME;
  c->hostname=safe_malloc(21);memcpy(c->hostname,"original\0old.example",21);c->domain=c->hostname+9;
  c->clid=safe_malloc(3);memcpy(c->clid,"\x01\x02\x03",3);c->clid_len=3;
  c->lease_time=3600;c->decline_time=7;inet_pton(AF_INET,"127.0.0.51",&c->addr);
  h=safe_malloc(sizeof(*h));memset(h,0,sizeof(*h));
  h->hwaddr[0]=2;h->hwaddr[5]=0x51;h->hwaddr_len=6;h->hwaddr_type=ARPHRD_ETHER;c->hwaddr=h;
  if(!getenv("ETHERS_TEST_SINGLE")) {
    h2=safe_malloc(sizeof(*h2));memcpy(h2,h,sizeof(*h2));h2->hwaddr[5]=0x52;h->next=h2;
  }
  tag=safe_malloc(sizeof(*tag));memset(tag,0,sizeof(*tag));
  tag->list=safe_malloc(sizeof(*tag->list));memset(tag->list,0,sizeof(*tag->list));
  tag->list->net=strdup("retained");c->netid=tag;
  filter=safe_malloc(sizeof(*filter));memset(filter,0,sizeof(*filter));filter->net=strdup("filtered");c->filter=filter;
#ifdef HAVE_DHCP6
  c->addr6=safe_malloc(sizeof(*c->addr6));memset(c->addr6,0,sizeof(*c->addr6));
  inet_pton(AF_INET6,"2001:db8::51",&c->addr6->addr.addr6);c->addr6->prefixlen=64;
  c->addr6->flags=ADDRLIST_PREFIX;c->addr6->decline_time=11;c->flags|=CONFIG_ADDR6;
#endif
  c->next=daemon->dhcp_conf;daemon->dhcp_conf=c;
}
static void ethers_test_dump(int result) {
  struct dhcp_config *c;int n=0;
  printf("BEGIN RESULT=%d ACTIVE=%d TRACKED=%d\n",result,dns_reload_active(),ethers_test_tracked());
  for(c=daemon->dhcp_conf;c;c=c->next) {
    struct hwaddr_config *h;struct dhcp_netid_list *tag;struct dhcp_netid *filter;char address[64];int i;
    if(++n>32)exit(91);
    if(c->flags&CONFIG_ADDR)inet_ntop(AF_INET,&c->addr,address,sizeof(address));else strcpy(address,"-");
    printf("C ptr=%p flags=%u addr=%s name=%s domain=%s lease=%u decline=%lld clid=",
      (void*)c,c->flags,address,(c->flags&CONFIG_NAME)&&c->hostname?c->hostname:"-",c->domain?c->domain:"-",
      c->lease_time,(long long)c->decline_time);
    for(i=0;i<c->clid_len;i++)printf("%02x",c->clid[i]);
    printf(" hardware=");
    for(h=c->hwaddr;h;h=h->next) {for(i=0;i<h->hwaddr_len;i++)printf("%02x",h->hwaddr[i]);printf(",");}
    printf(" tags=");for(tag=c->netid;tag;tag=tag->next)printf("%s,",tag->list->net);
    printf(" filter=");for(filter=c->filter;filter;filter=filter->next)printf("%s,",filter->net);
#ifdef HAVE_DHCP6
    {struct addrlist *a;char v6[64];printf(" ipv6=");
     for(a=c->addr6;a;a=a->next){inet_ntop(AF_INET6,&a->addr.addr6,v6,sizeof(v6));
      printf("%s,%d,%d,%lld;",v6,a->flags,a->prefixlen,(long long)a->decline_time);}
     printf(" addr6ptr=%p",(void*)c->addr6);}
#endif
    printf(" pointers=%p/%p/%p/%p/%p/%p\n",(void*)c->hostname,(void*)c->domain,(void*)c->clid,
      (void*)c->hwaddr,(void*)c->netid,(void*)c->filter);
  }
  printf("END COUNT=%d\n",n);fflush(stdout);
}
static int ethers_test_replace(const char *kind,char *first,char *second) {
  int status=0;const char *fixed=getenv("ETHERS_TEST_FIXED");
  if(unlink(fixed)&&errno!=ENOENT)return 92;
  if(!strcmp(kind,"fifo")) {if(mkfifo(fixed,0600))return 93;}
  else if(strcmp(kind,"missing")&&link(first,fixed))return 94;
  if(!dns_reload_begin())return 95;
  status=dhcp_reload_prepare();
  if(status&&!strcmp(kind,"race")) {if(unlink(fixed)||link(second,fixed))return 96;}
  status=status&&dns_reload_validate();
  if(status) {dhcp_reload_commit();dns_reload_end(1);}
  else {dhcp_reload_abort();dns_reload_end(0);}
  ethers_test_dump(status);return 0;
}
static int ethers_test_main(void) {
  const char *plan=getenv("ETHERS_TEST_PLAN");FILE *f;char line[8192];int result,steps=0;
  if(!plan)return 97;
  log_start(NULL,-1);
  if(getenv("ETHERS_TEST_SEED"))ethers_test_seed();
  ethers_test_dump(1);
  if(!(f=fopen(plan,"r")))return 98;
  while(fgets(line,sizeof(line),f)) {
    char *kind=strtok(line," \n"),*first=strtok(NULL," \n"),*second=strtok(NULL," \n");
    if(!kind||++steps>1000)return 99;
    ethers_test_fail_after(steps==2&&getenv("ETHERS_TEST_FAIL_AFTER")?atoi(getenv("ETHERS_TEST_FAIL_AFTER")):-1);
    result=ethers_test_replace(kind,first,second);if(result)return result;
  }
  if(fclose(f))return 100;
  return 0;
}
'''


class DNSEthersReloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory(prefix='k2p-ethers-source-')
        cls.base=Path(cls.build.name).resolve();cls.tree=cls.base/'source';cls.fixed=cls.base/'ethers'
        shutil.copytree(SOURCE,cls.tree,ignore=shutil.ignore_patterns('*.o','dnsmasq','dnsmasq_baseline','.copts_*'))
        config=cls.tree/'src/config.h';text=config.read_text()
        needle='#define ETHERSFILE "/etc/ethers"'
        if text.count(needle)!=1:raise AssertionError('private ethers constant changed')
        config.write_text(text.replace(needle,'#define ETHERSFILE '+json.dumps(str(cls.fixed))))
        # Observe real bookkeeping after transaction cleanup, with no runtime
        # environment bypass in the production module.
        tracker=cls.tree/'src/reload_file.c'
        original_tracker=tracker.read_text()
        signature='void *dns_reload_malloc(size_t size)'
        if original_tracker.count(signature)!=1:raise AssertionError('allocator injection boundary changed')
        tracker.write_text(original_tracker.replace(signature,'static void *ethers_original_malloc(size_t size)'))
        with tracker.open('a') as stream:stream.write(r'''
static int ethers_fail_after=-1,ethers_allocation_calls;
void ethers_test_fail_after(int n){ethers_fail_after=n;ethers_allocation_calls=0;}
void *dns_reload_malloc(size_t size){
 if(dns_reload_active()&&ethers_fail_after>=0&&ethers_allocation_calls++==ethers_fail_after){
  dns_reload_fail("inert ethers allocation failure");return NULL;}
 return ethers_original_malloc(size);}

int ethers_test_tracked(void){unsigned int i;int count=0;
 for(i=0;i<RELOAD_HASH;i++){struct reload_allocation *p;
  for(p=reload.allocations[i];p;p=p->next)count++;}
 return count+(reload.identities!=NULL);}
''')
        main=cls.tree/'src/dnsmasq.c';text=main.read_text()
        text=text.replace('#include "dnsmasq.h"','#include "dnsmasq.h"\n#include "runtime_file.h"\n#include "reload_file.h"\nint ethers_test_tracked(void);\nvoid ethers_test_fail_after(int);\n'+DRIVER,1)
        needle='  read_opts(argc, argv, compile_opts);'
        if text.count(needle)!=1:raise AssertionError('early parser replay stop point changed')
        main.write_text(text.replace(needle,needle+'\n  return ethers_test_main();'))
        result=subprocess.run(['make','-j4','CC=clang',
            'COPTS=-DNO_TFTP -DNO_INOTIFY -DNO_AUTH -DNO_LOOP',
            'CFLAGS=-O1 -g -Wall -Wextra -fsanitize=address,undefined',
            'LDFLAGS=-fsanitize=address,undefined'],cwd=cls.tree,text=True,capture_output=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
        cls.binary=cls.tree/'src/dnsmasq'
        if b'BEGIN RESULT=' not in cls.binary.read_bytes():raise AssertionError('inert replay missing')

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='k2p-ethers-case-');self.directory=Path(self.temp.name).resolve()
        self.config=self.directory/'dnsmasq.conf';self.plan=self.directory/'plan'
        self.config.write_text('port=0\nno-hosts\nno-resolv\nread-ethers\nlog-facility='+str(self.directory/'log')+'\n')

    def tearDown(self):
        self.temp.cleanup()
        if self.fixed.exists() or self.fixed.is_symlink():self.fixed.unlink()

    def run_plan(self,payloads,seed=False,single=False,fail_after=None):
        instructions=[]
        for i,payload in enumerate(payloads):
            if payload in ('fifo','missing'):instructions.append(payload+'\n');continue
            if isinstance(payload,tuple):
                first=self.directory/('first'+str(i));second=self.directory/('second'+str(i))
                first.write_bytes(payload[0]);second.write_bytes(payload[1]);instructions.append('race '+str(first)+' '+str(second)+'\n')
            else:
                path=self.directory/('input'+str(i));path.write_bytes(payload);instructions.append('file '+str(path)+'\n')
        self.plan.write_text(''.join(instructions))
        env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','ETHERS_TEST_PLAN':str(self.plan),'ETHERS_TEST_FIXED':str(self.fixed)}
        if seed:env['ETHERS_TEST_SEED']='1'
        if single:env['ETHERS_TEST_SINGLE']='1'
        if fail_after is not None:env['ETHERS_TEST_FAIL_AFTER']=str(fail_after)
        result=subprocess.run([str(self.binary),'-C',str(self.config)],env=env,text=True,capture_output=True,timeout=12)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotIn('AddressSanitizer',result.stderr);self.assertNotIn('runtime error:',result.stderr)
        states=[]
        for block in result.stdout.split('BEGIN ')[1:]:
            header,*lines=block.splitlines();fields=dict(x.split('=',1) for x in header.split())
            entries=[dict(x.split('=',1) for x in line.split()[1:]) for line in lines if line.startswith('C ')]
            self.assertEqual(fields['ACTIVE'],'0');self.assertEqual(fields['TRACKED'],'0')
            states.append(dict(result=int(fields['RESULT']),entries=entries))
        self.assertEqual(len(states),len(payloads)+1,result.stdout)
        return states

    def test_regular_ip_hostname_and_empty_commit(self):
        states=self.run_plan([b'02:00:00:00:00:51 127.0.0.51\n',b'02:00:00:00:00:52 fixture.example\n',b''])
        self.assertEqual(states[1]['entries'][0]['addr'],'127.0.0.51')
        self.assertEqual(states[2]['entries'][0]['name'],'fixture.example')
        self.assertEqual(states[2]['entries'][0]['hardware'],'020000000052,')
        self.assertEqual(states[3]['entries'],[])

    def test_fifo_missing_malformed_and_budgets_preserve_live_entries(self):
        old=b'02:00:00:00:00:51 127.0.0.51\n'
        for bad in ('fifo','missing',b'02:00:00:00:00:52 127.0.0.52\nnot-a-mac malformed\n',
                    b'02:00:00:00:00:52 999.0.0.1\n',b'02:00:00:00:00:52 illegal/name\n',
                    b'#'+b'x'*16384+b'\n',b'#'+b'x'*(2*1024*1024),b'\n'*65537):
            with self.subTest(kind=str(bad)[:60]):
                states=self.run_plan([old,bad])
                self.assertEqual(states[1]['result'],1);self.assertEqual(states[2]['result'],0)
                self.assertEqual(states[2]['entries'],states[1]['entries'])

    def test_candidate_static_override_failure_cannot_write_through(self):
        states=self.run_plan([b'02:00:00:00:00:99 127.0.0.51\nnot-a-mac malformed\n'],seed=True)
        self.assertEqual(states[1]['result'],0)
        self.assertEqual(states[1]['entries'],states[0]['entries'])
        old=states[0]['entries'][0]
        self.assertEqual((old['name'],old['domain'],old['clid'],old['hardware'],old['tags'],old['filter']),
                         ('original','old.example','010203','020000000051,020000000052,','retained,','filtered,'))

    def test_successful_static_clone_keeps_owned_fields_and_overrides_hardware_tail(self):
        states=self.run_plan([b'02:00:00:00:00:99 127.0.0.51\n'],seed=True)
        old,new=states[0]['entries'][0],states[1]['entries'][0]
        self.assertEqual(states[1]['result'],1);self.assertNotEqual(old['ptr'],new['ptr'])
        for field in ('name','domain','clid','tags','filter','lease','decline'):
            self.assertEqual(old[field],new[field],field)
        self.assertEqual(new['hardware'],'020000000099,')
        for a,b in zip(old['pointers'].split('/'),new['pointers'].split('/')):self.assertNotEqual(a,b)

    def test_ipv6_address_list_is_deep_cloned_with_all_metadata(self):
        states=self.run_plan([b'02:00:00:00:00:99 127.0.0.51\n'],seed=True)
        old,new=states[0]['entries'][0],states[1]['entries'][0]
        self.assertEqual(states[1]['result'],1)
        self.assertEqual(old['ipv6'],new['ipv6'])
        self.assertIn('2001:db8::51,',new['ipv6'])
        self.assertTrue(new['ipv6'].endswith(',64,11;'))
        self.assertNotEqual(old['addr6ptr'],new['addr6ptr'])

    def test_hostname_override_clears_old_domain_and_abort_preserves_it(self):
        changed=b'02:00:00:00:00:51 replacement.new.example\n'
        states=self.run_plan([changed+b'bad invalid\n',changed],seed=True,single=True)
        self.assertEqual(states[1]['result'],0);self.assertEqual(states[1]['entries'],states[0]['entries'])
        self.assertEqual(states[2]['result'],1)
        self.assertEqual(states[2]['entries'][0]['name'],'replacement.new.example')
        self.assertEqual(states[2]['entries'][0]['domain'],'-')
        self.assertEqual(states[2]['entries'][0]['clid'],'010203')

    def test_partial_clone_allocation_failures_preserve_owned_live_graph(self):
        failures=successes=0
        for index in range(32):
            states=self.run_plan([b'',b'02:00:00:00:00:99 127.0.0.51\n'],seed=True,fail_after=index)
            if states[2]['result']==0:
                failures+=1;self.assertEqual(states[2]['entries'],states[1]['entries'],index)
            else:
                successes+=1;self.assertEqual(states[2]['entries'][0]['hardware'],'020000000099,')
        self.assertGreaterEqual(failures,10)
        self.assertGreater(successes,0)

    def test_precommit_path_race_preserves_previous_graph(self):
        old=b'02:00:00:00:00:51 127.0.0.51\n';new=b'02:00:00:00:00:52 127.0.0.52\n'
        states=self.run_plan([old,(new,old)])
        self.assertEqual(states[2]['result'],0);self.assertEqual(states[2]['entries'],states[1]['entries'])

    def test_duplicates_keep_first_and_repeated_commit_abort_cleanup(self):
        old=b'02:00:00:00:00:51 fixture.example\n02:00:00:00:00:52 fixture.example\n'
        states=self.run_plan([old]+[value for _ in range(40) for value in (b'not-a-mac invalid\n',old,b'')])
        self.assertEqual(states[1]['entries'][0]['hardware'],'020000000051,')
        self.assertEqual(len(states[1]['entries']),1)
        for i in range(2,len(states),3):
            self.assertEqual(states[i]['result'],0)
            self.assertEqual(states[i+1]['result'],1)
            self.assertEqual(states[i+2]['entries'],[])


if __name__=='__main__':unittest.main()
