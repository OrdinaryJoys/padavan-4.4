"""Whole LEOPARD PHY poller; MDIO, MMIO, threads and time are inert.

This is a forced variant. K2P is MT7621 and does not start this poller.
"""
import hashlib
import re

SOURCE_PATHS = {
    'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
    'mdio': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mii_mgr.c',
    'config': 'trunk/configs/boards/K2P/kernel-4.4.x.config',
    'header': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.h',
    'mii_header': 'trunk/linux-4.4.x/include/linux/mii.h',
    'mii_uapi': 'trunk/linux-4.4.x/include/uapi/linux/mii.h',
    'mac_header': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_eth_soc.h',
}
FUNCTION_SOURCES = {'mii_resolve_flowctrl_fdx': 'mii_header', 'phy_polling_thread': 'raeth'}
BODY_ORDER = ('mii_resolve_flowctrl_fdx', 'phy_polling_thread')
SOURCE_ONLY_FUNCTION_SOURCES = {
    'ei_open': 'raeth', 'mii_mgr_read': 'mdio', 'mii_mgr_read_cl45': 'mdio',
}
SOURCE_FRAGMENTS = {'config': ('CONFIG_SOC_MT7621=y', 'CONFIG_RAETH=y'),
                    'header': ('#define PHY_POLLING_MS\t\t(1000)', '#include <linux/mii.h>')}
MODEL_VARIANT = {
    'LEOPARD_forced_variant_not_shipping_K2P_MT7621': True,
    'whole_phy_poller_executed': True,
    'MDIO_MMIO_scheduler_time_are_inert': True,
    'failed_MDIO_preserves_output_seam': True,
    'real_kernel_IEEE28B3_pause_helper_executed': True,
    'full_and_half_duplex_all_16_advertisement_pairs': True,
    'hardware_link_EEE_ABI_or_timing_not_proven': True,
    'only_unused_kernel_callback_parameter_warning_disabled': True,
}
FIELDS = ('ret', 'reads', 'writes', 'downs', 'value', 'ticks', 'errors')
LEGACY_CASE_NAMES = (
    'up', 'down', 'eee-clears', 'eee-1g', 'eee-100', 'eee-peer-missing',
    'pause-change', 'speed-100', 'speed-10-half', 'down-up',
    'fail-link', 'fail-local-pause', 'fail-peer-pause', 'fail-speed',
    'fail-local-eee', 'fail-peer-eee', 'initial-fail', 'stopped',
    'retry-link', 'retry-speed',
)
PAUSE_CASE_NAMES = ('pause-fdx-0-0',
 'pause-fdx-0-1',
 'pause-fdx-0-2',
 'pause-fdx-0-3',
 'pause-fdx-1-0',
 'pause-fdx-1-1',
 'pause-fdx-1-2',
 'pause-fdx-1-3',
 'pause-fdx-2-0',
 'pause-fdx-2-1',
 'pause-fdx-2-2',
 'pause-fdx-2-3',
 'pause-fdx-3-0',
 'pause-fdx-3-1',
 'pause-fdx-3-2',
 'pause-fdx-3-3',
 'pause-hdx-0-0',
 'pause-hdx-0-1',
 'pause-hdx-0-2',
 'pause-hdx-0-3',
 'pause-hdx-1-0',
 'pause-hdx-1-1',
 'pause-hdx-1-2',
 'pause-hdx-1-3',
 'pause-hdx-2-0',
 'pause-hdx-2-1',
 'pause-hdx-2-2',
 'pause-hdx-2-3',
 'pause-hdx-3-0',
 'pause-hdx-3-1',
 'pause-hdx-3-2',
 'pause-hdx-3-3')
CASE_NAMES = ('up',
 'down',
 'eee-clears',
 'eee-1g',
 'eee-100',
 'eee-peer-missing',
 'pause-change',
 'speed-100',
 'speed-10-half',
 'down-up',
 'fail-link',
 'fail-local-pause',
 'fail-peer-pause',
 'fail-speed',
 'fail-local-eee',
 'fail-peer-eee',
 'initial-fail',
 'stopped',
 'retry-link',
 'retry-speed',
 'pause-fdx-0-0',
 'pause-fdx-0-1',
 'pause-fdx-0-2',
 'pause-fdx-0-3',
 'pause-fdx-1-0',
 'pause-fdx-1-1',
 'pause-fdx-1-2',
 'pause-fdx-1-3',
 'pause-fdx-2-0',
 'pause-fdx-2-1',
 'pause-fdx-2-2',
 'pause-fdx-2-3',
 'pause-fdx-3-0',
 'pause-fdx-3-1',
 'pause-fdx-3-2',
 'pause-fdx-3-3',
 'pause-hdx-0-0',
 'pause-hdx-0-1',
 'pause-hdx-0-2',
 'pause-hdx-0-3',
 'pause-hdx-1-0',
 'pause-hdx-1-1',
 'pause-hdx-1-2',
 'pause-hdx-1-3',
 'pause-hdx-2-0',
 'pause-hdx-2-1',
 'pause-hdx-2-2',
 'pause-hdx-2-3',
 'pause-hdx-3-0',
 'pause-hdx-3-1',
 'pause-hdx-3-2',
 'pause-hdx-3-3')
EXPECTED_ROWS = {'up': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554034171, 'ticks': 1, 'errors': 0},
 'down': {'ret': 0, 'reads': 1, 'writes': 0, 'downs': 1, 'value': 2779096485, 'ticks': 1, 'errors': 0},
 'eee-clears': {'ret': 0, 'reads': 12, 'writes': 2, 'downs': 0, 'value': 554033979, 'ticks': 2, 'errors': 0},
 'eee-1g': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554034107, 'ticks': 1, 'errors': 0},
 'eee-100': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554034043, 'ticks': 1, 'errors': 0},
 'eee-peer-missing': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033979, 'ticks': 1, 'errors': 0},
 'pause-change': {'ret': 0, 'reads': 12, 'writes': 2, 'downs': 0, 'value': 554033931, 'ticks': 2, 'errors': 0},
 'speed-100': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554034167, 'ticks': 1, 'errors': 0},
 'speed-10-half': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554034113, 'ticks': 1, 'errors': 0},
 'down-up': {'ret': 0, 'reads': 7, 'writes': 1, 'downs': 1, 'value': 554033979, 'ticks': 2, 'errors': 0},
 'fail-link': {'ret': 0, 'reads': 7, 'writes': 1, 'downs': 0, 'value': 554034171, 'ticks': 2, 'errors': 0},
 'fail-local-pause': {'ret': 0, 'reads': 8, 'writes': 1, 'downs': 0, 'value': 554034171, 'ticks': 2, 'errors': 0},
 'fail-peer-pause': {'ret': 0, 'reads': 9, 'writes': 1, 'downs': 0, 'value': 554034171, 'ticks': 2, 'errors': 0},
 'fail-speed': {'ret': 0, 'reads': 10, 'writes': 1, 'downs': 0, 'value': 554034171, 'ticks': 2, 'errors': 0},
 'fail-local-eee': {'ret': 0, 'reads': 11, 'writes': 1, 'downs': 0, 'value': 554034171, 'ticks': 2, 'errors': 0},
 'fail-peer-eee': {'ret': 0, 'reads': 12, 'writes': 1, 'downs': 0, 'value': 554034171, 'ticks': 2, 'errors': 0},
 'initial-fail': {'ret': 0, 'reads': 1, 'writes': 0, 'downs': 0, 'value': 2779096485, 'ticks': 1, 'errors': 0},
 'stopped': {'ret': 0, 'reads': 0, 'writes': 0, 'downs': 0, 'value': 2779096485, 'ticks': 0, 'errors': 0},
 'retry-link': {'ret': 0, 'reads': 13, 'writes': 2, 'downs': 0, 'value': 554033979, 'ticks': 3, 'errors': 0},
 'retry-speed': {'ret': 0, 'reads': 16, 'writes': 2, 'downs': 0, 'value': 554033979, 'ticks': 3, 'errors': 0},
 'pause-fdx-0-0': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-0-1': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-0-2': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-0-3': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-1-0': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-1-1': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033979, 'ticks': 1, 'errors': 0},
 'pause-fdx-1-2': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-1-3': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033979, 'ticks': 1, 'errors': 0},
 'pause-fdx-2-0': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-2-1': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-2-2': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-2-3': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033947, 'ticks': 1, 'errors': 0},
 'pause-fdx-3-0': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033931, 'ticks': 1, 'errors': 0},
 'pause-fdx-3-1': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033979, 'ticks': 1, 'errors': 0},
 'pause-fdx-3-2': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033963, 'ticks': 1, 'errors': 0},
 'pause-fdx-3-3': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033979, 'ticks': 1, 'errors': 0},
 'pause-hdx-0-0': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-0-1': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-0-2': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-0-3': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-1-0': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-1-1': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-1-2': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-1-3': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-2-0': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-2-1': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-2-2': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-2-3': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-3-0': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-3-1': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-3-2': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0},
 'pause-hdx-3-3': {'ret': 0, 'reads': 6, 'writes': 1, 'downs': 0, 'value': 554033921, 'ticks': 1, 'errors': 0}}
# Independent literal truth table: columns/rows are none, PAUSE, ASYM, both.
# Values are the MAC RX bit5 / TX bit4 result of IEEE 28B-3, not outputs
# calculated by the function under test. Half duplex never negotiates PAUSE.
PAUSE_FDX_BITS = ((0, 0, 0, 0), (0, 0x30, 0, 0x30),
                  (0, 0, 0, 0x10), (0, 0x30, 0x20, 0x30))
PREFIX = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
#define BIT(n) (1U << (n))
#define PHY_POLLING_MS 1000U
#define ETHDMASYS_ETH_MAC_BASE 0x1000U
#define pr_info(...) ((void)0)
static const char *case_name;
static int iteration, limit=1, slot, reads, writes, downs, errors, stopped;
static int fail_iteration=-1, fail_slot=-1;
static int pause_matrix, pause_full, pause_local, pause_peer;
static unsigned int value=0xa5a5a5a5U;
static int selected(const char *s) { return strcmp(case_name,s)==0; }
static int kthread_should_stop(void) { return stopped || iteration>=limit; }
static void msleep_interruptible(unsigned int ms) {
 if(ms!=PHY_POLLING_MS)errors++;
 iteration++;slot=0;
}
static int sample(int clause,unsigned int reg,unsigned int *out) {
 int index=slot++;unsigned int result=0;
 static const unsigned int regs[6]={1,4,5,0xa2,0x3c,0x3d};
 reads++;
 if(index<0||index>=6||!out){errors++;return 0;}
 if((index>=3)!=clause || reg!=regs[index])errors++;
 if(iteration==fail_iteration && index==fail_slot)return 0;
 if(index==0)result=(selected("down")||(selected("down-up")&&iteration==0))?0:4;
 else if(index==1)result=pause_matrix?(unsigned int)pause_local<<10:0xc00;
 else if(index==2)result=pause_matrix?(unsigned int)pause_peer<<10:((selected("pause-change")&&iteration)?0:0xc00);
 else if(index==3)result=pause_matrix?(pause_full?0x28U:0):(selected("speed-100")?0x24:(selected("speed-10-half")?0:0x28));
 else {
  result=(pause_matrix||iteration)?0:6;
  if(selected("eee-1g"))result=4;
  if(selected("eee-100"))result=2;
  if(selected("eee-peer-missing")&&index==5)result=0;
 }
 *out=result;return 1;
}
static int mii_mgr_read(unsigned int phy,unsigned int reg,unsigned int *out) {
 if(phy!=0)errors++;
 return sample(0,reg,out);
}
static int mii_mgr_read_cl45(unsigned int phy,unsigned int dev,unsigned int reg,unsigned int *out) {
 if(phy!=0 || dev!=(slot==3?0x1eU:7U))errors++;
 return sample(1,reg,out);
}
static void sys_reg_write(unsigned int reg,unsigned int word) {
 if(reg!=ETHDMASYS_ETH_MAC_BASE+0x200 || slot!=6)errors++;
 writes++;value=word;
}
static void set_ge2_force_link_down(void) { downs++; }
'''
SUFFIX = r'''
int main(int argc,char **argv) {
 (void)mii_resolve_flowctrl_fdx;
 if(argc!=2)return 91;
 case_name=argv[1];
 CASE_ADMISSION
 if(!strncmp(case_name,"pause-fdx-",10)||!strncmp(case_name,"pause-hdx-",10)){
  pause_matrix=1;pause_full=!strncmp(case_name,"pause-fdx-",10);
  if(sscanf(case_name+10,"%d-%d",&pause_local,&pause_peer)!=2)return 92;
 }
 if(selected("eee-clears")||selected("pause-change")||selected("down-up")||!strncmp(case_name,"fail-",5))limit=2;
 if(selected("stopped"))stopped=1;
 if(selected("initial-fail")){fail_iteration=0;fail_slot=0;}
 if(selected("fail-link")){fail_iteration=1;fail_slot=0;}
 if(selected("fail-local-pause")){fail_iteration=1;fail_slot=1;}
 if(selected("fail-peer-pause")){fail_iteration=1;fail_slot=2;}
 if(selected("fail-speed")){fail_iteration=1;fail_slot=3;}
 if(selected("fail-local-eee")){fail_iteration=1;fail_slot=4;}
 if(selected("fail-peer-eee")){fail_iteration=1;fail_slot=5;}
 if(selected("retry-link")||selected("retry-speed")){limit=3;fail_iteration=1;fail_slot=selected("retry-link")?0:3;}
 int ret=phy_polling_thread(NULL);
 printf("{\"ret\":%d,\"reads\":%d,\"writes\":%d,\"downs\":%d,\"value\":%u,\"ticks\":%d,\"errors\":%d}\n",ret,reads,writes,downs,value,iteration,errors);
 return 0;
}
'''


def function(text, name):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked = re.sub(tokens, lambda m: ' ' * len(m.group()), text)
    matches = list(re.finditer(r'(?m)^[A-Za-z_][\w \t*]*\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{', masked))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous PHY poll body: ' + name)
    start = matches[0].start(); opening = masked.index('{', start); depth = 0
    for match in re.finditer('[{}]', masked[opening:]):
        depth += 1 if match.group() == '{' else -1
        if not depth:
            return text[start:opening + match.end()]
    raise ValueError('Unterminated PHY poll body: ' + name)


def generate_source(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact PHY poll source set required')
    for key, fragments in SOURCE_FRAGMENTS.items():
        for fragment in fragments:
            if texts[key].splitlines().count(fragment) != 1:
                raise ValueError('PHY poll configured source drift')
    # Complete source-bound admission, not execution of the shipping opener.
    function(texts['raeth'], 'ei_open')
    constants = []
    for key, names in (('mii_uapi', ('ADVERTISE_PAUSE_CAP', 'ADVERTISE_PAUSE_ASYM', 'FLOW_CTRL_RX', 'FLOW_CTRL_TX')),
                       ('mac_header', ('MAC_MCR_FORCE_RX_FC', 'MAC_MCR_FORCE_TX_FC'))):
        for name in names:
            found = re.findall(r'(?m)^#define\s+' + name + r'\s+[^\n]+', texts[key])
            if len(found) != 1:
                raise ValueError('One real PHY constant definition required: ' + name)
            constants.append(found[0])
    mapping = '\n_Static_assert(MAC_MCR_FORCE_RX_FC == BIT(5), "RX mapping");\n_Static_assert(MAC_MCR_FORCE_TX_FC == BIT(4), "TX mapping");\n'
    admission = 'if (' + ' && '.join('strcmp(case_name,"' + n + '")' for n in CASE_NAMES) + ') return 91;'
    return PREFIX + '\n' + '\n'.join(constants) + mapping + '\n'.join(function(texts[FUNCTION_SOURCES[n]], n) for n in BODY_ORDER) + SUFFIX.replace('CASE_ADMISSION', admission)


def function_manifest(texts):
    return {n: {'source': k, 'execution': 'whole-function', 'full_body_sha256': hashlib.sha256(function(texts[k], n).encode()).hexdigest()} for n, k in FUNCTION_SOURCES.items()}


def source_only_manifest(texts):
    return {n: {'source': k, 'execution': 'source-only-not-run', 'full_body_sha256': hashlib.sha256(function(texts[k], n).encode()).hexdigest()} for n, k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
