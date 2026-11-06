"""Whole reset_control_reset; inert provider and sequential atomic shims only."""
import hashlib
import re
SOURCE_PATHS = {'core': 'trunk/linux-4.4.x/drivers/reset/core.c'}
BODY_ORDER = ('reset_control_reset',)
FUNCTION_SOURCES = {'reset_control_reset': 'core'}
SOURCE_ONLY_FUNCTION_SOURCES = {}
FUNCTION_DECLARATIONS = ''
SOURCE_FRAGMENTS = {'core': ('struct reset_control {','atomic_t deassert_count;','atomic_t triggered_count;')}
MODEL_VARIANT = {'whole_function_execution': True, 'synthetic_reset_control_layout': True,
                 'provider_callback_is_inert': True,
                 'atomic_shims_are_sequential_not_kernel_scheduling': True,
                 'machine_restart_and_hardware_are_not_executed': True}
FIELDS = ('ret','second','third','calls','pulses','triggered','deassert','warns','last_id')
CASE_NAMES = ('exclusive-success','exclusive-failure','exclusive-retry','exclusive-repeat',
              'shared-success','shared-repeat','shared-failure','shared-retry-1','shared-retry-2',
              'shared-consumed','shared-deasserted','exclusive-deasserted','null','error-pointer',
              'missing-reset','shared-missing-reset','shared-already-consumed')
EXPECTED_ROWS = {
 'exclusive-success': {'ret':0,'second':999,'third':999,'calls':1,'pulses':1,'triggered':0,'deassert':0,'warns':0,'last_id':13},
 'exclusive-failure': {'ret':-5,'second':999,'third':999,'calls':1,'pulses':0,'triggered':0,'deassert':0,'warns':0,'last_id':13},
 'exclusive-retry': {'ret':-5,'second':0,'third':999,'calls':2,'pulses':1,'triggered':0,'deassert':0,'warns':0,'last_id':13},
 'exclusive-repeat': {'ret':0,'second':0,'third':0,'calls':3,'pulses':3,'triggered':0,'deassert':0,'warns':0,'last_id':13},
 'shared-success': {'ret':0,'second':999,'third':999,'calls':1,'pulses':1,'triggered':1,'deassert':0,'warns':0,'last_id':13},
 'shared-repeat': {'ret':0,'second':0,'third':0,'calls':1,'pulses':1,'triggered':3,'deassert':0,'warns':0,'last_id':13},
 'shared-failure': {'ret':-5,'second':999,'third':999,'calls':1,'pulses':0,'triggered':0,'deassert':0,'warns':0,'last_id':13},
 'shared-retry-1': {'ret':-5,'second':0,'third':999,'calls':2,'pulses':1,'triggered':1,'deassert':0,'warns':0,'last_id':13},
 'shared-retry-2': {'ret':-5,'second':-5,'third':0,'calls':3,'pulses':1,'triggered':1,'deassert':0,'warns':0,'last_id':13},
 'shared-consumed': {'ret':0,'second':0,'third':999,'calls':1,'pulses':1,'triggered':2,'deassert':0,'warns':0,'last_id':13},
 'shared-deasserted': {'ret':-22,'second':999,'third':999,'calls':0,'pulses':0,'triggered':0,'deassert':1,'warns':1,'last_id':-1},
 'exclusive-deasserted': {'ret':0,'second':999,'third':999,'calls':1,'pulses':1,'triggered':0,'deassert':1,'warns':0,'last_id':13},
 'null': {'ret':0,'second':999,'third':999,'calls':0,'pulses':0,'triggered':0,'deassert':0,'warns':0,'last_id':-1},
 'error-pointer': {'ret':-22,'second':999,'third':999,'calls':0,'pulses':0,'triggered':0,'deassert':0,'warns':1,'last_id':-1},
 'missing-reset': {'ret':-524,'second':999,'third':999,'calls':0,'pulses':0,'triggered':0,'deassert':0,'warns':0,'last_id':-1},
 'shared-missing-reset': {'ret':-524,'second':999,'third':999,'calls':0,'pulses':0,'triggered':0,'deassert':0,'warns':0,'last_id':-1},
 'shared-already-consumed': {'ret':0,'second':999,'third':999,'calls':0,'pulses':0,'triggered':2,'deassert':0,'warns':0,'last_id':-1},
}
PREFIX = r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#define EINVAL 22
#define ENOTSUPP 524
typedef struct { int value; } atomic_t;
struct reset_controller_dev;
struct reset_control_ops { int (*reset)(struct reset_controller_dev *, unsigned long); };
struct reset_controller_dev { const struct reset_control_ops *ops; };
struct reset_control {
 struct reset_controller_dev *rcdev;
 unsigned int id;
 int shared;
 atomic_t deassert_count, triggered_count;
};
static int warnings, calls, pulses, failures, last_id = -1;
static struct reset_controller_dev *expected_provider;
#define WARN_ON(x) ((x) ? (warnings++, 1) : 0)
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
static int atomic_read(const atomic_t *p) { return p->value; }
static int atomic_inc_return(atomic_t *p) { return ++p->value; }
static void atomic_dec(atomic_t *p) { --p->value; }
static int inert_reset(struct reset_controller_dev *provider, unsigned long id)
{
 if (provider != expected_provider) abort();
 last_id = (int)id;
 calls++;
 if (calls <= failures) return -5;
 pulses++;
 return 0;
}
'''

SUFFIX = r'''
struct scenario { const char *name; int shared, count, fail, mode, consumed, deassert; };
static const struct scenario scenarios[] = {
 {"exclusive-success",0,1,0,0,0,0}, {"exclusive-failure",0,1,1,0,0,0},
 {"exclusive-retry",0,2,1,0,0,0}, {"exclusive-repeat",0,3,0,0,0,0},
 {"shared-success",1,1,0,0,0,0}, {"shared-repeat",1,3,0,0,0,0},
 {"shared-failure",1,1,1,0,0,0}, {"shared-retry-1",1,2,1,0,0,0},
 {"shared-retry-2",1,3,2,0,0,0}, {"shared-consumed",1,2,0,0,0,0},
 {"shared-deasserted",1,1,0,0,0,1}, {"exclusive-deasserted",0,1,0,0,0,1},
 {"null",0,1,0,1,0,0}, {"error-pointer",0,1,0,2,0,0},
 {"missing-reset",0,1,0,3,0,0}, {"shared-missing-reset",1,1,0,3,0,0},
 {"shared-already-consumed",1,1,0,0,1,0}
};
int main(int argc, char **argv)
{
 struct reset_control_ops ops = { inert_reset };
 struct reset_controller_dev provider = { &ops };
 struct reset_control reset = { &provider, 13, 0, {0}, {0} };
 struct reset_control *argument = &reset;
 const struct scenario *selected = NULL;
 const char *name;
 int result[3] = {999,999,999};
 unsigned int i;
 if (argc != 2) return 64;
 name = argv[1];CASE_ADMISSION
 for (i = 0; i < sizeof(scenarios)/sizeof(scenarios[0]); i++)
  if (!strcmp(argv[1], scenarios[i].name)) selected = &scenarios[i];
 if (!selected) return 64;
 expected_provider = &provider;
 reset.shared = selected->shared;
 reset.triggered_count.value = selected->consumed;
 reset.deassert_count.value = selected->deassert;
 failures = selected->fail;
 if (selected->mode == 1) argument = NULL;
 if (selected->mode == 2) argument = (struct reset_control *)(intptr_t)-22;
 if (selected->mode == 3) ops.reset = NULL;
 for (i = 0; i < (unsigned int)selected->count; i++)
  result[i] = reset_control_reset(argument);
 printf("{\"ret\":%d,\"second\":%d,\"third\":%d,\"calls\":%d,\"pulses\":%d,\"triggered\":%d,\"deassert\":%d,\"warns\":%d,\"last_id\":%d}\n",
        result[0], result[1], result[2], calls, pulses, reset.triggered_count.value,
        reset.deassert_count.value, warnings, last_id);
 return 0;
}
'''

def function(text, name):
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m:' '*len(m.group()),text,flags=re.S)
    found=list(re.finditer(r'(?:static\s+)?(?:inline\s+)?int\s+\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked))
    if len(found)!=1:raise ValueError('Missing/ambiguous reset core body: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer('[{}]',masked[opening:]):
        depth+=1 if m.group()=='{'else -1
        if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated reset core body: '+name)
def validate_inputs(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact reset core source inputs required')
    for key,fragments in SOURCE_FRAGMENTS.items():
        for fragment in fragments:
            if fragment not in texts[key]:raise ValueError('Reset core field declaration differs: '+fragment)
    for name,key in FUNCTION_SOURCES.items():function(texts[key],name)
def function_manifest(texts):
    validate_inputs(texts)
    return {n:dict(source=k,execution='whole-function',full_body_sha256=hashlib.sha256(function(texts[k],n).encode()).hexdigest())for n,k in FUNCTION_SOURCES.items()}
def source_only_manifest(texts):
    validate_inputs(texts)
    return {}
def generate_source(texts):
    validate_inputs(texts)
    admission='if ('+' && '.join('strcmp(name,"'+n+'")'for n in CASE_NAMES)+') return 2;'
    return PREFIX+'\n'+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+'\n'+SUFFIX.replace('CASE_ADMISSION',admission)
