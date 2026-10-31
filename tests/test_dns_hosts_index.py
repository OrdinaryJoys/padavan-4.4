"""Actual native shadow models: indexed bulk hosts, no listener or router IO."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_dns_reload_transaction as transaction

REPORT = r'''
extern int fixture_hosts_index_empty(void);
extern unsigned int fixture_hosts_hash_size(void);
extern unsigned int fixture_hosts_total(void);
static void fixture_index_report(const char *stage)
{
 const char *names[]={"repeated.fixture","multi.fixture","alias.fixture","b.fixture"};
 unsigned int i,v4[4]={0},v6[4]={0},first=0,last=0,order=2166136261U,again=2166136261U,configured=0,cname=0;struct crec *entry;
 union all_addr address;char reverse[256]="none";
 for(i=0;i<4;i++) {
  entry=NULL;while((entry=cache_find_by_name(entry,(char *)names[i],0,F_IPV4))) {
   if(i==0) { if(!v4[i])first=ntohl(entry->addr.addr4.s_addr);last=ntohl(entry->addr.addr4.s_addr);order=(order^last)*16777619U; }
   if(i==1&&(entry->flags&F_CONFIG))configured++;
   v4[i]++;
  }
  entry=NULL;while((entry=cache_find_by_name(entry,(char *)names[i],0,F_IPV6)))v6[i]++;
 }
 entry=NULL;while((entry=cache_find_by_name(entry,"repeated.fixture",0,F_IPV4)))again=(again^ntohl(entry->addr.addr4.s_addr))*16777619U;
 if((entry=cache_find_by_name(NULL,"alias.fixture",0,F_CNAME))&&entry->addr.cname.is_name_ptr&&!strcmp(entry->addr.cname.target.name,"first.fixture"))cname=1;
 assert(inet_pton(AF_INET,"10.0.0.1",&address)==1);
 if((entry=cache_find_by_addr(NULL,&address,0,F_IPV4)))
  snprintf(reverse,sizeof(reverse),"%s",cache_get_name(entry));
 fprintf(stderr,"INDEX {\"stage\":\"%s\",\"empty\":%d,\"hash_size\":%u,\"v4\":[%u,%u,%u,%u],\"v6\":[%u,%u,%u,%u],\"reverse\":\"%s\",\"ancestor\":%d,\"hosts\":%u,\"first\":%u,\"last\":%u,\"order\":%u,\"order_again\":%u,\"configured\":%u,\"cname\":%u}\n",stage,fixture_hosts_index_empty(),fixture_hosts_hash_size(),v4[0],v4[1],v4[2],v4[3],v6[0],v6[1],v6[2],v6[3],reverse,cache_find_non_terminal("fixture",0),fixture_hosts_total(),first,last,order,again,configured,cname);
}
'''

CHECKPOINTS = r'''
#include "runtime_file.h"
static void fixture_checkpoint_checks(void)
{
 unsigned int i,work=0;void *small;struct dns_runtime_file input;
 dns_reload_initial(0);
 fixture_clock_jump=0;
 fixture_clock_error=1;assert(!dns_reload_begin()&&!dns_reload_active());fixture_clock_error=0;
 assert(dns_reload_begin());
 fixture_clock_calls=0;fixture_clock_jump=1;fixture_clock_add_ms=500;
 for(i=0;i<DNS_RELOAD_CHECK_WORK-1;i++)assert(dns_reload_work_ok());
 assert(fixture_clock_calls==0);
 assert(!dns_reload_work_ok()&&fixture_clock_calls==1);
 assert(!dns_reload_work_ok());dns_reload_end(0);
 fixture_clock_jump=0;assert(dns_reload_begin());
 fixture_clock_calls=0;fixture_clock_jump=1;
 assert(!dns_reload_ok()&&fixture_clock_calls==1);dns_reload_end(0);
 fixture_clock_jump=0;assert(dns_reload_begin());
 fixture_clock_calls=0;fixture_clock_jump=1;
 /* A chain's256-step check is forced, never another64-way batch. */
 for(i=0;i<255;i++)assert(dns_reload_step(&work));
 assert(fixture_clock_calls==0);
 assert(!dns_reload_step(&work)&&fixture_clock_calls==1);dns_reload_end(0);
 fixture_clock_jump=0;assert(dns_reload_begin());
 fixture_clock_calls=0;fixture_clock_jump=1;
 assert(!dns_reload_malloc(DNS_RELOAD_FORCE_ALLOCATION)&&fixture_clock_calls==1);dns_reload_end(0);
 fixture_clock_jump=0;assert(dns_reload_begin());
 fixture_clock_calls=0;fixture_expire_after_calloc=1;
 assert(!dns_reload_malloc(DNS_RELOAD_FORCE_ALLOCATION)&&fixture_clock_calls==1);dns_reload_end(0);
 fixture_clock_jump=0;assert(dns_reload_begin());
 fixture_clock_calls=0;fixture_clock_jump=1;
 assert(!dns_reload_read(&input,getenv("K2P_RELOAD_H1"),1)&&fixture_clock_calls==1);dns_reload_end(0);
 fixture_clock_jump=0;assert(dns_reload_begin());
 fixture_clock_calls=0;fixture_clock_jump=1;
 small=dns_reload_malloc(8);assert(small&&fixture_clock_calls==0);
 assert(!dns_reload_validate()&&fixture_clock_calls==1);dns_reload_end(0);
 fixture_clock_jump=0;assert(dns_reload_begin());fixture_clock_error=1;
 assert(!dns_reload_validate()&&!dns_reload_work_ok());fixture_clock_error=0;dns_reload_end(0);
 fixture_clock_jump=0;fixture_clock_calls=0;
}
'''

PROBES = r'''
static int fixture_hosts_stream_locks;
static void fixture_hosts_lock(FILE *stream) { flockfile(stream);fixture_hosts_stream_locks++; }
static void fixture_hosts_unlock(FILE *stream) { assert(fixture_hosts_stream_locks>0);fixture_hosts_stream_locks--;funlockfile(stream); }
#define flockfile(stream) fixture_hosts_lock(stream)
#define funlockfile(stream) fixture_hosts_unlock(stream)
int fixture_hosts_index_empty(void)
{ return !hosts_index.names && !hosts_index.addresses && !hosts_index.name_blocks && !hosts_index.address_blocks && fixture_hosts_stream_locks==0; }
unsigned int fixture_hosts_hash_size(void) { return (unsigned int)hash_size; }
unsigned int fixture_hosts_total(void)
{ int i;unsigned int count=0;struct crec *entry;for(i=0;i<hash_size;i++)for(entry=hash_table[i];entry;entry=entry->hash_next)if((entry->flags&F_HOSTS)&&(entry->flags&(F_IPV4|F_IPV6)))count++;return count; }
'''


class DNSHostsIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original_driver = transaction.DRIVER
        original_replay = transaction.REPLAY
        original_alloc = transaction.ALLOC_SHIM
        original_copy = transaction.shutil.copytree
        def copy(*args, **kwargs):
            result = original_copy(*args, **kwargs)
            if Path(args[0]) == transaction.SOURCE:
                path = Path(result)/'src/cache.c'
                # Wrappers are defined before real lock sites; only private
                # host snapshot FILE lock/unlock calls are observed.
                code=path.read_text()
                lock_code=PROBES[:PROBES.index('int fixture_hosts_index_empty')]
                code=code.replace('#include "reload_file.h"','#include "reload_file.h"\n#include <assert.h>\n'+lock_code,1)
                path.write_text(code+'\n'+PROBES[PROBES.index('int fixture_hosts_index_empty'):])
            return result
        transaction.DRIVER = ('int fixture_clock_error,fixture_expire_after_calloc;\nstatic void fixture_index_report(const char *);\n'+
            original_driver.replace('fflush(stdout);', 'fflush(stdout);fixture_index_report(stage);', 1)+REPORT+CHECKPOINTS)
        transaction.ALLOC_SHIM = ('extern int fixture_clock_error,fixture_expire_after_calloc;\n'+original_alloc.replace(
            ' int result=clock_gettime(id,now);',
            ' int result;if(fixture_clock_error){errno=EIO;return -1;}result=clock_gettime(id,now);',1).replace(
            ' return calloc(n,size);',' {void *value=calloc(n,size);if(fixture_expire_after_calloc){fixture_clock_jump=1;fixture_expire_after_calloc=0;}return value;}',1))
        transaction.REPLAY = original_replay.replace('fixture_print("repaired",accepted);','fixture_print("repaired",accepted);if(getenv("K2P_RELOAD_CHECKPOINTS"))fixture_checkpoint_checks();',1)
        try:
            with patch.object(transaction.shutil, 'copytree', side_effect=copy):
                transaction.DNSReloadTransactionTests.setUpClass.__func__(cls)
        finally:
            transaction.DRIVER = original_driver
            transaction.REPLAY = original_replay
            transaction.ALLOC_SHIM = original_alloc

    @classmethod
    def tearDownClass(cls):
        transaction.DNSReloadTransactionTests.tearDownClass.__func__(cls)

    setUp = transaction.DNSReloadTransactionTests.setUp
    tearDown = transaction.DNSReloadTransactionTests.tearDown
    replay = transaction.DNSReloadTransactionTests.replay
    assert_state = transaction.DNSReloadTransactionTests.assert_state
    assert_rejected = transaction.DNSReloadTransactionTests.assert_rejected

    def indexed_replay(self, **kwargs):
        rows, result = self.replay(**kwargs)
        reports = [json.loads(line[6:]) for line in result.stderr.splitlines() if line.startswith('INDEX ')]
        self.assertEqual([item['stage'] for item in reports], ['initial','attempt','repaired'])
        self.assertTrue(all(item['empty'] == 1 for item in reports), reports)
        return rows, reports, result

    @staticmethod
    def same_name(count):
        return ''.join('10.%d.%d.%d repeated.fixture\n'%((i>>16)&255,(i>>8)&255,i&255) for i in range(count))

    @staticmethod
    def colliding_names(count):
        # Invert the actual public FNV low ten bits. All names collide in
        # the production 1024-bucket name index, not a reduced test table.
        mask, prime = 1023, 16777619
        inverse = pow(prime, -1, 1024)
        target = 0
        for value in reversed(b'.fixture'):
            target = ((target*inverse)&mask)^value
        allowed = b'0123456789abcdefghijklmnopqrstuvwxyz'
        final_before = (target*inverse)&mask
        names, number = [], 0
        while len(names) < count:
            prefix = 'collision%d-'%number
            number += 1
            value = 2166136261&mask
            for character in prefix.encode():
                value = ((value^character)*prime)&mask
            for first in allowed:
                second = (((value^first)*prime)&mask)^final_before
                if second < 256 and second in allowed:
                    name = prefix+chr(first)+chr(second)+'.fixture'
                    check = 2166136261&mask
                    for character in name.encode():check=((check^character)*prime)&mask
                    assert check == 0
                    names.append(name)
                    break
        return names

    def test_twenty_thousand_same_name_addresses_commit_after_rehash(self):
        rows, reports, _ = self.indexed_replay(bad={'H1':self.new['H1']+self.same_name(20000)})
        self.assertEqual(rows[1]['accepted'], 1)
        self.assertEqual(reports[1]['v4'][0], 20000)
        self.assertGreater(reports[1]['hash_size'], 64)

    def test_case_canonical_names_families_aliases_and_duplicate_addresses(self):
        first = self.new['H1']+'10.0.0.1 Multi.Fixture alias.fixture\n10.0.0.2 multi.fixture\n10.0.0.1 MULTI.FIXTURE.\n2001:db8::1 Multi.Fixture alias.fixture\n'
        second = self.new['H2']+'10.0.0.2 MULTI.fixture\n2001:db8::1 multi.fixture\n'
        rows, reports, _ = self.indexed_replay(bad={'H1':first,'H2':second})
        self.assertEqual(rows[1]['accepted'], 1)
        self.assertEqual(reports[1]['v4'][1:3], [2,1])
        self.assertEqual(reports[1]['v6'][1:3], [1,1])
        self.assertEqual(reports[1]['reverse'].lower(), 'multi.fixture')
        self.assertEqual(reports[1]['ancestor'], 1)

    def test_real_ancestor_replaces_empty_then_additional_addresses_do_not_remove_it(self):
        first = self.new['H1']+'10.0.0.3 child.b.fixture\n10.0.0.4 B.fixture\n10.0.0.5 b.fixture\n'
        rows, reports, _ = self.indexed_replay(bad={'H1':first})
        self.assertEqual(rows[1]['accepted'], 1)
        self.assertEqual(reports[1]['v4'][3], 2)
        self.assertEqual(reports[1]['ancestor'], 1)

    def test_index_initialization_and_block_allocation_failures_preserve_entire_old_group(self):
        for number in (1,5,10,15,20,25,35):
            with self.subTest(allocation=number):
                rows, reports, _ = self.indexed_replay(allocation=number)
                self.assertEqual(rows[1]['accepted'], 0)
                self.assert_state(rows[1], False)
                self.assertEqual(reports[1]['v4'][0], 0)

    def test_parse_failure_after_many_indexed_records_clears_roots_and_preserves_old(self):
        first = self.new['H1']+self.same_name(4000)+'not-an-address malformed.fixture\n'
        rows, reports, _ = self.indexed_replay(bad={'H1':first})
        self.assertEqual(rows[1]['accepted'], 0)
        self.assert_state(rows[1], False)
        self.assertEqual(reports[1]['v4'][0], 0)

    def test_repeated_large_commits_release_temporary_indexes(self):
        self.new['H1'] += self.same_name(2000)
        rows, reports, _ = self.indexed_replay(cycles=40)
        self.assertEqual(rows[1]['accepted'], 1)
        self.assertEqual(reports[2]['v4'][0], 2000)

    def test_real_fixed_bucket_collisions_keep_all_distinct_records(self):
        first = self.new['H1']+''.join('10.0.0.1 '+name+'\n' for name in self.colliding_names(200))
        rows, reports, _ = self.indexed_replay(bad={'H1':first})
        self.assertEqual(rows[1]['accepted'], 1)
        self.assertEqual(reports[1]['hosts'], 202)

    def test_long_real_collision_chains_still_hit_existing_time_budget_and_keep_old(self):
        first = self.new['H1']+''.join('10.0.0.1 '+name+'\n' for name in self.colliding_names(40000))
        rows, reports, _ = self.indexed_replay(bad={'H1':first})
        self.assertEqual(rows[1]['accepted'], 0)
        self.assert_state(rows[1], False)
        self.assertEqual(reports[1]['hosts'], 2)
        self.assertIn('hot reload cooperative time budget exceeded',(self.root/'log').read_text())

    def test_no_round_robin_order_survives_other_names_and_rehash_generations(self):
        first = self.new['H1']+''.join(
            '10.%d.%d.%d repeated.fixture\n11.%d.%d.%d other%d.fixture\n'%
            ((i>>16)&255,(i>>8)&255,i&255,(i>>16)&255,(i>>8)&255,i&255,i)
            for i in range(2000))
        original_run = transaction.subprocess.run
        def run(argv, **kwargs):
            return original_run(list(argv)+['--no-round-robin'], **kwargs)
        with patch.object(transaction.subprocess, 'run', side_effect=run):
            rows, reports, _ = self.indexed_replay(bad={'H1':first})
        self.assertEqual(rows[1]['accepted'], 1)
        self.assertEqual(reports[1]['v4'][0], 2000)
        self.assertEqual(reports[1]['hosts'], 4002)
        # no-round-robin promises stable query order, not original file
        # order across cache bucket collisions and a reload/rehash.
        self.assertEqual(reports[1]['order'], reports[1]['order_again'])

    def test_static_host_record_duplicate_and_cname_alias_keep_configuration_semantics(self):
        first = self.new['H1']+'192.0.2.100 MULTI.fixture\n192.0.2.101 multi.fixture\n'
        original_run = transaction.subprocess.run
        def run(argv, **kwargs):
            return original_run(list(argv)+['--host-record=Multi.Fixture,192.0.2.100','--cname=alias.fixture,first.fixture'], **kwargs)
        with patch.object(transaction.subprocess, 'run', side_effect=run):
            rows, reports, _ = self.indexed_replay(bad={'H1':first})
        self.assertEqual(rows[1]['accepted'], 1)
        self.assertEqual(reports[1]['v4'][1], 2)
        self.assertEqual(reports[1]['configured'], 1)
        self.assertTrue(all(report['cname'] == 1 for report in reports))

    def test_private_locked_snapshot_tokenizer_keeps_whitespace_comments_and_final_eof(self):
        first=self.new['H1']+'\t10.0.0.1 Multi.Fixture\talias.fixture # public comment\r\n\n2001:db8::1 multi.fixture\t# tail\n10.0.0.2 MULTI.fixture'
        rows,reports,_=self.indexed_replay(bad={'H1':first})
        self.assertEqual(rows[1]['accepted'],1)
        self.assertEqual(reports[1]['v4'][1:3],[2,1])
        self.assertEqual(reports[1]['v6'][1],1)

    def test_stream_unlocks_after_forced_mid_parse_deadline_and_repairs(self):
        rows,reports,_=self.indexed_replay(bad={'H1':self.new['H1']+self.same_name(2000)},clock=20)
        self.assertEqual(rows[1]['accepted'],0)
        self.assert_state(rows[1],False)
        self.assertTrue(all(report['empty']==1 for report in reports))

    def test_small_work_batch_and_forced_large_read_validate_and_chain_boundaries(self):
        with patch.dict(transaction.os.environ,{'K2P_RELOAD_CHECKPOINTS':'1'}):
            rows,_,_=self.indexed_replay()
        self.assertEqual(rows[1]['accepted'],1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
