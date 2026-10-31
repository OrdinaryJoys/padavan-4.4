"""Actual canonicalise/check_name ownership comparison; public native fixtures.

IDN libraries are inert API stubs with explicit success/error/allocation
returns. Their surrounding original conversion/failure logic is real code.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from bounded_log_harness import mask

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'trunk/user/dnsmasq/dnsmasq-2.93/src/util.c'

def actual_function(text,name):
    masked=mask(text)
    matches=list(re.finditer(r'(?:static\s+)?(?:int\s+|char\s*\*\s*)'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked))
    if len(matches)!=1:raise ValueError('Missing/ambiguous real canonical function: '+name)
    start=matches[0].start();opening=masked.index('{',start);depth=0
    for item in re.finditer('[{}]',masked[opening:]):
        depth+=1 if item.group()=='{' else -1
        if depth==0:return text[start:opening+item.end()]
    raise ValueError('Unterminated real canonical function')
PREFIX=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MAXDNAME 255
#define MAXLABEL 63
#define _(s) (s)
#define LOG_ERR 3
#define IDNA_SUCCESS 0
#define IDNA_MALLOC_ERROR 1
#define IDNA_DLOPEN_ERROR 2
#define IDN2_NONTRANSITIONAL 0
#define IDN2_VERSION_NUMBER 0x02000003
static int failure,allocations;
static void *fixture_allocate(size_t size){allocations++;return failure==1?NULL:calloc(1,size);}
#define whine_malloc(size) fixture_allocate(size)
#if defined(HAVE_IDN) || defined(HAVE_LIBIDN2)
static void my_syslog(int priority,const char *message,...){(void)priority;(void)message;}
static void malloc_log(void *pointer,size_t size){(void)pointer;(void)size;}
static int fixture_idn(const char *name,char **out,int flags){
 (void)name;(void)flags;allocations++;
 if(failure==1){*out=NULL;return IDNA_MALLOC_ERROR;}
 *out=strdup("converted.fixture");assert(*out);
 return failure==2?99:IDNA_SUCCESS;
}
#define idna_to_ascii_lz fixture_idn
#define idn2_to_ascii_lz fixture_idn
#endif
'''
DRIVER=r'''
int main(int argc,char **argv){
 char oldbuf[4096],newbuf[4096],*old,*current;int old_nomem=-1,nomem=-1,owned=9,old_calls,new_calls;
 assert(argc==3&&strlen(argv[2])<sizeof(oldbuf));failure=atoi(argv[1]);strcpy(oldbuf,argv[2]);strcpy(newbuf,argv[2]);
 allocations=0;old=canonicalise(oldbuf,&old_nomem);old_calls=allocations;
 allocations=0;current=canonicalise_hosts(newbuf,&nomem,&owned);new_calls=allocations;
 assert(!strcmp(oldbuf,newbuf));
#if defined(HAVE_IDN) || defined(HAVE_LIBIDN2)
 assert(!!old==!!current&&old_nomem==nomem&&old_calls==new_calls);
 assert(owned==!!current);if(current)assert(current!=newbuf);
#else
 assert(!owned&&new_calls==0&&nomem==0);
 if(failure!=1){assert(!!old==!!current&&old_nomem==nomem);}
 if(current)assert(current==newbuf);
#endif
 if(old&&current)assert(!strcmp(old,current));
 printf("{\"old_ok\":%d,\"new_ok\":%d,\"old_nomem\":%d,\"nomem\":%d,\"owned\":%d,\"old_allocations\":%d,\"new_allocations\":%d}\n",!!old,!!current,old_nomem,nomem,owned,old_calls,new_calls);
 free(old);if(owned)free(current);return 0;
}
'''


class DNSHostsCanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-hosts-canonical-')
        cls.root=Path(cls.temp.name).resolve()
        text=SOURCE.read_text()
        unit=PREFIX+'\n'.join(actual_function(text,name) for name in ('check_name','canonicalise','canonicalise_hosts'))+DRIVER
        source=cls.root/'canonical.c';source.write_text(unit);cls.programs={}
        for name,flags in [('ascii',[]),('idn',['-DHAVE_IDN']),('idn2',['-DHAVE_LIBIDN2'])]:
            target=cls.root/name
            subprocess.run(['clang','-std=gnu99','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                            *flags,str(source),'-o',str(target)],capture_output=True,check=True)
            cls.programs[name]=target

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def execute(self,profile,name,failure=0):
        result=subprocess.run([str(self.programs[profile]),str(failure),name],capture_output=True,text=True,timeout=5,
                              env={**os.environ,'ASAN_OPTIONS':'detect_leaks='+('1' if sys.platform.startswith('linux') else '0')})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stderr,'')
        return json.loads(result.stdout)

    def test_real_check_name_corpus_matches_owned_original_without_allocating(self):
        # Preserve the upstream permissive root/empty-label behavior too;
        # this optimization must not silently impose a new name policy.
        valid=['.','bad..fixture','Multi.Fixture','MULTI.fixture.','a-b_1.fixture','a\\b.fixture','space name.fixture',
               'a'*63+'.fixture','a.'*126+'a']
        invalid=['','white only\t',' ', 'a'*64+'.fixture', 'a.'*127+'a','bad\nfixture','café.fixture']
        for name in valid+invalid:
            with self.subTest(name=name):
                row=self.execute('ascii',name)
                self.assertEqual(row['new_ok'],int(name in valid))
                self.assertEqual(row['new_allocations'],0)

    def test_borrowed_valid_name_needs_no_temporary_allocation_and_can_be_reused(self):
        for name in ('Multi.Fixture.','alias.fixture','plain'):
            row=self.execute('ascii',name,1)
            self.assertEqual((row['old_ok'],row['old_nomem'],row['new_ok'],row['nomem'],row['owned']),(0,1,1,0,0))
            self.assertEqual(row['new_allocations'],0)

    def test_IDN_ownership_success_and_allocation_or_conversion_failure_match_original(self):
        for profile in ('idn','idn2'):
            for name in ('Mixed.Fixture','café.fixture','plain.fixture','bad..fixture'):
                for failure in (0,1,2):
                    with self.subTest(profile=profile,name=name,failure=failure):
                        row=self.execute(profile,name,failure)
                        self.assertEqual(row['old_ok'],row['new_ok'])
                        self.assertEqual(row['old_nomem'],row['nomem'])
                        self.assertEqual(row['owned'],row['new_ok'])


if __name__=='__main__':unittest.main()
