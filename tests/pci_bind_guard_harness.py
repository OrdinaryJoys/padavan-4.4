"""PCI manual-bind policy using real initializer/core regions and inert APIs.

This is not a PCI unbind, module unload, device removal or hardware execution.
The driver's init/exit/shutdown and PCI registration functions are complete;
bus_add_driver contributes only its final bind-file decision block.
"""
import hashlib
import re

SOURCE_PATHS = {
    'pci': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/pci_main_dev.c',
    'core': 'trunk/linux-4.4.x/drivers/pci/pci-driver.c',
    'bus': 'trunk/linux-4.4.x/drivers/base/bus.c',
    'config': 'trunk/configs/boards/K2P/kernel-4.4.x.config',
}
BASELINE_COMMIT = '60ae6bf98bd46b68c648620c599f1aa78073131e'
BASELINE_INITIALIZER_SHA256 = 'c7ea843f0c96d7dc63b6e563b42cef96605c282852c22cd6be8bb5a77e09433c'
FUNCTION_SOURCES = {
    '__pci_register_driver': 'core', 'pci_unregister_driver': 'core',
    'rt_pci_shutdown': 'pci', 'rt_pci_init_module': 'pci',
    'rt_pci_cleanup_module': 'pci',
}
CASE_NAMES = ('register', 'core-add-error', 'shutdown', 'cleanup', 'register-error')
FIELDS = ('result', 'registered', 'bind_calls', 'nodes', 'errors', 'shutdowns',
          'removes', 'unregisters', 'dynid_frees', 'core_fields',
          'callback_fields', 'master')
EXPECTED_ROWS = {
    'register': [0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
    'core-add-error': [0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
    'shutdown': [0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0],
    'cleanup': [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1],
    'register-error': [-12, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
}
BASELINE_ROWS = {
    'register': [0, 1, 1, 2, 0, 0, 0, 0, 0, 1, 1, 1],
    'core-add-error': [0, 1, 1, 0, 1, 0, 0, 0, 0, 1, 1, 1],
    'shutdown': [0, 1, 1, 2, 0, 1, 0, 0, 0, 1, 1, 0],
    'cleanup': [0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1],
    'register-error': [-12, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
}
TOKEN = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''


def masked(text):
    return re.sub(TOKEN, lambda m: ' ' * len(m.group()), text)


def block_end(text, opening):
    clean = masked(text)
    depth = 0
    for i in range(opening, len(clean)):
        if clean[i] == '{':
            depth += 1
        elif clean[i] == '}':
            depth -= 1
            if not depth:
                return i + 1
    raise ValueError('Unterminated C region')


def function(text, name):
    clean = masked(text)
    pattern = r'^(?:static\s+)?(?:int|void|VOID)\s+(?:(?:__init|__exit)\s+)?' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{'
    found = list(re.finditer(pattern, clean, re.M))
    if len(found) != 1:
        raise ValueError('Missing/ambiguous PCI policy function: ' + name)
    start = found[0].start()
    opening = clean.index('{', start)
    return text[start:block_end(text, opening)]


def initializer(text):
    clean = masked(text)
    found = list(re.finditer(r'^static\s+struct\s+pci_driver\s+rt_pci_driver\s*=\s*\{', clean, re.M))
    if len(found) != 1:
        raise ValueError('One real PCI driver initializer required')
    start = found[0].start()
    end = block_end(text, clean.index('{', start))
    if not re.match(r'\s*;', clean[end:]):
        raise ValueError('PCI driver initializer terminator absent')
    return text[start:end] + ';'


def bind_guard(text):
    body = function(text, 'bus_add_driver')
    clean = masked(body)
    found = list(re.finditer(r'if\s*\(\s*!\s*drv->suppress_bind_attrs\s*\)\s*\{', clean))
    if len(found) != 1:
        raise ValueError('One final bus bind-file policy block required')
    start = found[0].start()
    end = block_end(body, clean.index('{', start))
    tail = re.match(r'\s*return\s+0\s*;', clean[end:])
    if not tail or 'add_bind_files(drv)' not in clean[start:end]:
        raise ValueError('Final bind guard/ordinary success continuation differs')
    return body[start:end + tail.end()]


def actual_parts(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact PCI policy input set required')
    config = texts['config']
    for flag in ('CONFIG_SYSFS=y', 'CONFIG_MODULE_UNLOAD=y', 'CONFIG_MT7615_AP=m',
                 '# CONFIG_MODULE_FORCE_UNLOAD is not set', '# CONFIG_PM is not set'):
        if flag not in config.splitlines():
            raise ValueError('Configured K2P policy selection absent: ' + flag)
    return {
        'initializer': initializer(texts['pci']),
        'bus_guard': bind_guard(texts['bus']),
        'functions': {n: function(texts[k], n) for n, k in FUNCTION_SOURCES.items()},
    }


PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define VOID void
#define __init
#define __exit
#define DEVEXIT_P(x) x
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(4,4,198)
#define RTMP_DRV_NAME "fixture-mt7615"
#define MTWF_LOG(...) ((void)0)
#define KERN_ERR ""
struct module { int unused; } fixture_owner;
#define THIS_MODULE (&fixture_owner)
struct pci_dev { int master; } fixture_device;
struct pci_device_id { int unused; };
static struct pci_device_id rt_pci_tbl[1];
struct dynids { int lock, list; };
struct device_driver {
 const char *name, *mod_name; void *bus; struct module *owner;
 bool suppress_bind_attrs;
};
struct pci_driver {
 const char *name; struct pci_device_id *id_table;
 int (*probe)(struct pci_dev *,const struct pci_device_id *);
 void (*shutdown)(struct pci_dev *),(*remove)(struct pci_dev *);
 struct device_driver driver; struct dynids dynids;
};
static int pci_bus_type;
static int registered, bind_calls, nodes, errors, shutdowns, removes, unregisters, dynid_frees;
static int registration_error, add_error;
static int rt_pci_probe(struct pci_dev *p,const struct pci_device_id *id)
{ assert(p==&fixture_device&&id==rt_pci_tbl);return 0; }
static void rt_pci_remove(struct pci_dev *p)
{ assert(p==&fixture_device);removes++; }
static void pci_clear_master(struct pci_dev *p)
{ assert(p==&fixture_device);p->master=0;shutdowns++; }
static void spin_lock_init(int *p) { *p=7; }
#define INIT_LIST_HEAD(p) (*(p)=9)
static int add_bind_files(struct device_driver *drv)
{ assert(drv);bind_calls++;if(add_error)return -12;nodes=2;return 0; }
#define printk(...) (errors++)
static int driver_register(struct device_driver *drv);
static void driver_unregister(struct device_driver *drv);
static void pci_free_dynids(struct pci_driver *drv)
{ assert(drv);dynid_frees++; }
int __pci_register_driver(struct pci_driver *,struct module *,const char *);
void pci_unregister_driver(struct pci_driver *);
#define pci_register_driver(p) __pci_register_driver((p),THIS_MODULE,"fixture-module")
'''

SUFFIX = r'''
static int driver_register(struct device_driver *drv)
{
 int error;
 assert(drv==&rt_pci_driver.driver);
 if(registration_error)return -12;
 registered=1;
 BUS_GUARD
}
static void driver_unregister(struct device_driver *drv)
{
 assert(drv==&rt_pci_driver.driver&&registered);
 unregisters++;
 rt_pci_driver.remove(&fixture_device);
 nodes=0;registered=0;
}
int main(int argc,char **argv)
{
 const char *name;int result,core_fields,callback_fields;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 fixture_device.master=1;
 registration_error=!strcmp(name,"register-error");add_error=!strcmp(name,"core-add-error");
 result=rt_pci_init_module();
 core_fields=rt_pci_driver.driver.owner==THIS_MODULE&&rt_pci_driver.driver.bus==&pci_bus_type&&
  !strcmp(rt_pci_driver.driver.name,RTMP_DRV_NAME)&&!strcmp(rt_pci_driver.driver.mod_name,"fixture-module")&&
  rt_pci_driver.dynids.lock==7&&rt_pci_driver.dynids.list==9;
 callback_fields=rt_pci_driver.id_table==rt_pci_tbl&&rt_pci_driver.probe==rt_pci_probe&&
  rt_pci_driver.remove==rt_pci_remove&&rt_pci_driver.shutdown==rt_pci_shutdown;
 if(!result&&!strcmp(name,"shutdown"))rt_pci_driver.shutdown(&fixture_device);
 if(!result&&!strcmp(name,"cleanup"))rt_pci_cleanup_module();
 printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]\n",result,registered,bind_calls,nodes,errors,
  shutdowns,removes,unregisters,dynid_frees,core_fields,callback_fields,fixture_device.master);
 return 0;
}
'''


def generate_source(texts, historical_initializer=None):
    parts = actual_parts(texts)
    selected = parts['initializer']
    if historical_initializer is not None:
        selected = initializer(historical_initializer)
    bodies = parts['functions']
    admission = 'if(!(' + '||'.join('!strcmp(name,"' + n + '")' for n in CASE_NAMES) + '))return 91;'
    return (PREFIX + '\n' + bodies['__pci_register_driver'] + '\n' +
            bodies['pci_unregister_driver'] + '\n' + bodies['rt_pci_shutdown'] + '\n' +
            selected + '\n' + bodies['rt_pci_init_module'] + '\n' +
            bodies['rt_pci_cleanup_module'] + '\n' +
            SUFFIX.replace('BUS_GUARD', parts['bus_guard']).replace('CASE_ADMISSION', admission))


def manifest(texts):
    parts = actual_parts(texts)
    return {
        'whole_functions': {n: {'source': FUNCTION_SOURCES[n], 'sha256': hashlib.sha256(b.encode()).hexdigest()}
                            for n, b in parts['functions'].items()},
        'initializer': {'source': 'pci', 'sha256': hashlib.sha256(parts['initializer'].encode()).hexdigest()},
        'bus_guard': {'source': 'bus', 'execution': 'function-fragment',
                      'sha256': hashlib.sha256(parts['bus_guard'].encode()).hexdigest()},
        'hardware_execution': False, 'complete_module_unload_execution': False,
        'full_bus_add_driver_execution': False,
    }
