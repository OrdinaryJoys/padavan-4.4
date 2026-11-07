"""Source-bound MT7621/P5 switch control model; MDIO/MMIO/locking are inert.

Executes actual VLAN construction, VTCR, bridge, MIB and ioctl bodies. This is
software fault injection, not a hardware rollback or device acceptance result.
"""
import hashlib
import re

SOURCE_PATHS = {
 'esw':'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl_mt762x.c',
 'ioctl':'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl.c',
 'header':'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl.h',
 'mt762x':'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl_mt762x.h',
 'common':'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/esw_common.h',
 'regs':'trunk/linux-4.4.x/drivers/net/ethernet/raeth/ra_ioctl.h',
 'config':'trunk/configs/boards/K2P/kernel-4.4.x.config',
 'capability':'trunk/linux-4.4.x/kernel/capability.c',
 'capheader':'trunk/linux-4.4.x/include/uapi/linux/capability.h',
 'errno_base':'trunk/linux-4.4.x/include/uapi/asm-generic/errno-base.h',
 'errno':'trunk/linux-4.4.x/arch/mips/include/uapi/asm/errno.h',
 'kerrno':'trunk/linux-4.4.x/include/linux/errno.h'}
BODY_ORDER = ('esw_reg_read',
 'esw_reg_write',
 'mt7530_gsw_wait_wt_mac',
 'mt7530_gsw_mac_table_clear',
 'esw_get_port_mib_rgoc',
 'esw_get_port_mib_tgoc',
 'get_ports_mask_lan_for_mode',
 'get_ports_mask_lan',
 'get_ports_mask_wan_for_mode',
 'get_ports_mask_wan',
 'get_ports_mask_from_uapi',
 'get_port_from_uapi',
 'esw_port_matrix_set',
 'esw_port_ingress_mode_set',
 'esw_port_attrib_set',
 'esw_port_accept_set',
 'esw_vlan_pvid_set',
 'esw_igmp_flood_to_cpu',
 'esw_igmp_ports_config',
 'esw_igmp_mld_snooping',
 'esw_igmp_apply',
 'esw_mac_table_clear',
 'esw_wait_vtcr',
 'esw_write_vtcr',
 'esw_vlan_set',
 'esw_vlan_reset_table',
 'find_vlan_slot',
 'find_free_min_pvid',
 'is_vlan_rule_included',
 'is_wan_vid_valid',
 'esw_vlan_apply_rules',
 'esw_vlan_init_vid1',
 'esw_mask_bridge_isolate',
 'esw_vlan_bridge_isolate',
 'esw_mac_to_phy_enable',
 'esw_port_phy_power',
 'esw_led_mode',
 'esw_status_link_port',
 'esw_status_speed_port_uapi',
 'esw_status_link_port_uapi',
 'esw_status_link_ports',
 'esw_status_link_changed',
 'esw_status_mib_port_uapi',
 'esw_status_bytes_port_uapi',
 'change_ports_power',
 'change_wan_lan_ports_power_for_mode',
 'change_wan_lan_ports_power',
 'change_bridge_mode',
 'vlan_accept_port_mode',
 'vlan_create_entry',
 'change_igmp_static_ports',
 'change_igmp_snooping_control',
 'change_vlan_rule',
 'esw_ioctl_init_post',
 'fill_bridge_members',
 'mtk_esw_ioctl',
 'esw_storm_control',
 'esw_jumbo_control',
 'change_led_mode',
 'change_storm_control_broadcast',
 'change_jumbo_frames_accept',
 'change_port_link_mode_uapi')
FUNCTION_SOURCES = {'esw_reg_read': 'esw',
 'esw_reg_write': 'esw',
 'mt7530_gsw_wait_wt_mac': 'esw',
 'mt7530_gsw_mac_table_clear': 'esw',
 'esw_get_port_mib_rgoc': 'esw',
 'esw_get_port_mib_tgoc': 'esw',
 'get_ports_mask_lan_for_mode': 'esw',
 'get_ports_mask_lan': 'esw',
 'get_ports_mask_wan_for_mode': 'esw',
 'get_ports_mask_wan': 'esw',
 'get_ports_mask_from_uapi': 'esw',
 'get_port_from_uapi': 'esw',
 'esw_port_matrix_set': 'esw',
 'esw_port_ingress_mode_set': 'esw',
 'esw_port_attrib_set': 'esw',
 'esw_port_accept_set': 'esw',
 'esw_vlan_pvid_set': 'esw',
 'esw_igmp_flood_to_cpu': 'esw',
 'esw_igmp_ports_config': 'esw',
 'esw_igmp_mld_snooping': 'esw',
 'esw_igmp_apply': 'esw',
 'esw_mac_table_clear': 'esw',
 'esw_wait_vtcr': 'esw',
 'esw_write_vtcr': 'esw',
 'esw_vlan_set': 'esw',
 'esw_vlan_reset_table': 'esw',
 'find_vlan_slot': 'esw',
 'find_free_min_pvid': 'esw',
 'is_vlan_rule_included': 'esw',
 'is_wan_vid_valid': 'esw',
 'esw_vlan_apply_rules': 'esw',
 'esw_vlan_init_vid1': 'esw',
 'esw_mask_bridge_isolate': 'esw',
 'esw_vlan_bridge_isolate': 'esw',
 'esw_mac_to_phy_enable': 'esw',
 'esw_port_phy_power': 'esw',
 'esw_led_mode': 'esw',
 'esw_status_link_port': 'esw',
 'esw_status_speed_port_uapi': 'esw',
 'esw_status_link_port_uapi': 'esw',
 'esw_status_link_ports': 'esw',
 'esw_status_link_changed': 'esw',
 'esw_status_mib_port_uapi': 'esw',
 'esw_status_bytes_port_uapi': 'esw',
 'change_ports_power': 'esw',
 'change_wan_lan_ports_power_for_mode': 'esw',
 'change_wan_lan_ports_power': 'esw',
 'change_bridge_mode': 'esw',
 'vlan_accept_port_mode': 'esw',
 'vlan_create_entry': 'esw',
 'change_igmp_static_ports': 'esw',
 'change_igmp_snooping_control': 'esw',
 'change_vlan_rule': 'esw',
 'esw_ioctl_init_post': 'esw',
 'fill_bridge_members': 'ioctl',
 'mtk_esw_ioctl': 'ioctl',
 'esw_storm_control': 'esw',
 'esw_jumbo_control': 'esw',
 'change_led_mode': 'esw',
 'change_storm_control_broadcast': 'esw',
 'change_jumbo_frames_accept': 'esw',
 'change_port_link_mode_uapi': 'esw'}
SOURCE_ONLY_FUNCTION_SOURCES = {'capable':'capability','esw_reg_get':'esw','esw_reg_set':'esw'}
HEADER_KEYS = ('common','header','mt762x')
SOURCE_DECLARATIONS = {
 r'^#define\s+REG_ESW_ISC\s+[^\n]+$':'regs',
 r'^#define\s+REG_ESW_VLAN_VTCR\s+[^\n]+$':'regs',
 r'^#define\s+REG_ESW_VLAN_VAWD1\s+[^\n]+$':'regs',
 r'^#define\s+REG_ESW_VLAN_VAWD2\s+[^\n]+$':'regs',
 r'^#define\s+CAP_NET_ADMIN\s+[^\n]+$':'capheader',
 r'^#define\s+EPERM\s+[^\n]+$':'errno_base',
 r'^#define\s+EIO\s+[^\n]+$':'errno_base',
 r'^#define\s+EFAULT\s+[^\n]+$':'errno_base',
 r'^#define\s+EINVAL\s+[^\n]+$':'errno_base',
 r'^#define\s+ETIMEDOUT\s+[^\n]+$':'errno',
 r'^#define\s+ENOIOCTLCMD\s+[^\n]+$':'kerrno',
 r'^static DEFINE_MUTEX\(esw_access_mutex\);[\s\S]+?static u32 g_vlan_pvid_wan_untagged\s*=\s*2;':'esw'}
CONFIG_NAMES = ('CONFIG_RAETH_ESW_PORT_WAN','CONFIG_RAETH_ESW_PORT_LAN1','CONFIG_RAETH_ESW_PORT_LAN2','CONFIG_RAETH_ESW_PORT_LAN3','CONFIG_RAETH_ESW_PORT_LAN4')
MODEL_VARIANT = {
 'actual_K2P_MT7530_P5_HW_IGMP_header_branch':True,
 'actual_vlan_construction_and_vtcr_and_mib_and_ioctl':True,
 'mdio_mmio_and_wait_are_inert_fault_injection':True,
 'mutex_atomic_shims_are_not_kernel_concurrency':True,
 'native_ABI_padding_checked_not_MIPS_binary_layout_proof':True,
 'partial_hardware_writes_are_not_rolled_back':True,
 'residual_storm_jumbo_led_link_mode_setters_are_inert':False,
 'controls_and_link_speed_getters_are_actual_whole_functions':True,
 'legacy_reg_get_set_are_source_only_unused_compatibility_symbols':True}
FIELDS = ('ret','state_ok','boundary_ok')
CASE_NAMES = ('mib-invalid-canary',
 'mib-success-zero-padding',
 'mib-every-read-failure',
 'mib-ioctl-invalid-no-copy',
 'mib-ioctl-read-failure-no-copy',
 'mib-ioctl-success',
 'mib-output-efault',
 'bytes-invalid-no-copy',
 'bytes-read-failure-no-copy',
 'bytes-output-efault',
 'all-setter-efault-no-hardware',
 'all-admin-commands-denied-no-effects',
 'unprivileged-pure-reads',
 'link-change-denied-not-consumed',
 'link-change-efault-restored',
 'admin-positive-mutation',
 'scalar-output-efault',
 'vtcr-write-failure',
 'vtcr-read-failure',
 'vtcr-busy-timeout',
 'vtcr-busy-then-ready',
 'vlan-set-every-write-failure',
 'vlan-set-read-failure',
 'vlan-set-success',
 'vlan-delete-write-failure',
 'vlan-delete-read-failure',
 'vlan-delete-partial-preserves-tail',
 'vlan-delete-retry',
 'port-rmw-read-failure-no-write',
 'port-rmw-write-failure',
 'apply-every-mdio-failure-no-publication',
 'apply-success-stages-only',
 'bridge-every-mdio-failure-retryable',
 'bridge-old-request-recovery',
 'init-every-mdio-failure-no-ready',
 'igmp-every-mdio-failure-retryable',
 'phy-read-failure-no-state',
 'phy-write-failure-no-state',
 'vlan-uncertain-read-cleanup',
 'vlan-uncertain-timeout-cleanup',
 'vlan-prior-busy-no-overwrite',
 'vlan-prior-busy-then-ready',
 'led-every-mdio-failure',
 'led-same-request-retry',
 'led-old-request-recovery',
 'led-success-and-noop',
 'storm-every-port-failure',
 'storm-same-request-retry',
 'storm-old-request-recovery',
 'storm-rate-encoding-and-normalization',
 'jumbo-every-mdio-failure',
 'jumbo-same-request-retry',
 'jumbo-old-request-recovery',
 'jumbo-success-preserves-unrelated-bits',
 'link-auto-every-mdio-failure',
 'link-force-every-mdio-failure',
 'link-same-request-retry',
 'link-old-request-recovery',
 'link-force-off-success',
 'link-invalid-mode-no-effects',
 'controls-ioctl-propagates-errors',
 'controls-ambiguous-write-old-request-recovery',
 'status-every-query-read-failure-no-copy',
 'status-invalid-port-no-copy',
 'status-success-packed-and-down',
 'status-direct-read-failure-preserves-output',
 'init-failure-invalidates-control-cache',
 'init-success-invalidates-control-cache')
EXPECTED_ROWS = {'vlan-uncertain-read-cleanup': [0, 1, 1],
 'vlan-uncertain-timeout-cleanup': [0, 1, 1],
 'vlan-prior-busy-no-overwrite': [-145, 1, 1],
 'vlan-prior-busy-then-ready': [0, 1, 1],
 'mib-invalid-canary': [-22, 1, 1],
 'mib-success-zero-padding': [0, 1, 1],
 'mib-every-read-failure': [-5, 1, 1],
 'mib-ioctl-invalid-no-copy': [-22, 1, 1],
 'mib-ioctl-read-failure-no-copy': [-5, 1, 1],
 'mib-ioctl-success': [0, 1, 1],
 'mib-output-efault': [-14, 1, 1],
 'bytes-invalid-no-copy': [-22, 1, 1],
 'bytes-read-failure-no-copy': [-5, 1, 1],
 'bytes-output-efault': [-14, 1, 1],
 'all-setter-efault-no-hardware': [-14, 1, 1],
 'all-admin-commands-denied-no-effects': [-1, 1, 1],
 'unprivileged-pure-reads': [0, 1, 1],
 'link-change-denied-not-consumed': [-1, 1, 1],
 'link-change-efault-restored': [-14, 1, 1],
 'admin-positive-mutation': [0, 1, 1],
 'scalar-output-efault': [-14, 1, 1],
 'vtcr-write-failure': [-5, 1, 1],
 'vtcr-read-failure': [-5, 1, 1],
 'vtcr-busy-timeout': [-145, 1, 1],
 'vtcr-busy-then-ready': [0, 1, 1],
 'vlan-set-every-write-failure': [-5, 1, 1],
 'vlan-set-read-failure': [-5, 1, 1],
 'vlan-set-success': [0, 1, 1],
 'vlan-delete-write-failure': [-5, 1, 1],
 'vlan-delete-read-failure': [-5, 1, 1],
 'vlan-delete-partial-preserves-tail': [-5, 1, 1],
 'vlan-delete-retry': [0, 1, 1],
 'port-rmw-read-failure-no-write': [-5, 1, 1],
 'port-rmw-write-failure': [-5, 1, 1],
 'apply-every-mdio-failure-no-publication': [-5, 1, 1],
 'apply-success-stages-only': [0, 1, 1],
 'bridge-every-mdio-failure-retryable': [-5, 1, 1],
 'bridge-old-request-recovery': [0, 1, 1],
 'init-every-mdio-failure-no-ready': [-5, 1, 1],
 'igmp-every-mdio-failure-retryable': [-5, 1, 1],
 'phy-read-failure-no-state': [-5, 1, 1],
 'phy-write-failure-no-state': [-5, 1, 1],
 'led-every-mdio-failure': [-5, 1, 1],
 'led-same-request-retry': [0, 1, 1],
 'led-old-request-recovery': [0, 1, 1],
 'led-success-and-noop': [0, 1, 1],
 'storm-every-port-failure': [-5, 1, 1],
 'storm-same-request-retry': [0, 1, 1],
 'storm-old-request-recovery': [0, 1, 1],
 'storm-rate-encoding-and-normalization': [0, 1, 1],
 'jumbo-every-mdio-failure': [-5, 1, 1],
 'jumbo-same-request-retry': [0, 1, 1],
 'jumbo-old-request-recovery': [0, 1, 1],
 'jumbo-success-preserves-unrelated-bits': [0, 1, 1],
 'link-auto-every-mdio-failure': [-5, 1, 1],
 'link-force-every-mdio-failure': [-5, 1, 1],
 'link-same-request-retry': [0, 1, 1],
 'link-old-request-recovery': [0, 1, 1],
 'link-force-off-success': [0, 1, 1],
 'link-invalid-mode-no-effects': [-22, 1, 1],
 'controls-ioctl-propagates-errors': [-5, 1, 1],
 'controls-ambiguous-write-old-request-recovery': [0, 1, 1],
 'status-every-query-read-failure-no-copy': [-5, 1, 1],
 'status-invalid-port-no-copy': [-22, 1, 1],
 'status-success-packed-and-down': [0, 1, 1],
 'status-direct-read-failure-preserves-output': [-5, 1, 1],
 'init-failure-invalidates-control-cache': [0, 1, 1],
 'init-success-invalidates-control-cache': [0, 1, 1]}
PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#define __KERNEL__
#define __user
#define CONFIG_RALINK_MT7621 1
#define CONFIG_RAETH_ESW_CONTROL 1
#define BIT(n) (1U<<(n))
#define VLAN_ENTRY_ID_MAX 15
#define printk(...) do{}while(0)
#define DEFINE_MUTEX(n) int n
#define DECLARE_BITMAP(n,b) unsigned char n[b]
#define ATOMIC_INIT(n) {n}
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;
typedef struct {int value;} atomic_t;
struct file {int inert;};
HEADERS_AND_DEFINITIONS
FUNCTION_DECLARATIONS
static u32 regs[32768],phy[32][32];
static unsigned char hardware_vlan[4096];
static int command_stuck;
static int reads,writes,op,fail_op,fail_read_at,fail_write_at,busy_reads,always_busy,delays;
static int accept_failed_write;
static int locks,depth,copy_in,copy_out,user_fault,admin=1,stub_changes;
int capable(int cap){assert(cap==CAP_NET_ADMIN);return admin;}
static void mutex_lock(int*p){(void)p;assert(!depth);depth++;locks++;}
static void mutex_unlock(int*p){(void)p;assert(depth==1);depth--;}
static int atomic_read(atomic_t*p){return p->value;}
static void atomic_set(atomic_t*p,int n){p->value=n;}
static int atomic_cmpxchg(atomic_t*p,int a,int b){int old=p->value;if(old==a)p->value=b;return old;}
static int test_bit(unsigned n,unsigned char*b){assert(n<4096);return b[n]!=0;}
static void set_bit(unsigned n,unsigned char*b){assert(n<4096);b[n]=1;}
static void clear_bit(unsigned n,unsigned char*b){assert(n<4096);b[n]=0;}
static void udelay(unsigned n){assert(n==100);delays+=(int)n;}
static void msleep(unsigned n){assert(n==500);}
static u32 mii_mgr_read(u32 addr,u32 reg,u32*out){assert(out);reads++;op++;if(op==fail_op||reads==fail_read_at)return 0;if(addr==31){assert(reg/4<32768);*out=regs[reg/4];if(reg==REG_ESW_VLAN_VTCR||reg==0x80){if(always_busy||busy_reads-->0||(command_stuck&&reg==REG_ESW_VLAN_VTCR&&(*out&BIT(31))))*out|=reg==0x80?BIT(15):BIT(31);else{*out&=~(reg==0x80?BIT(15):BIT(31));regs[reg/4]=*out;}}}else{assert(addr<32&&reg<32);*out=phy[addr][reg];}return 1;}
static u32 mii_mgr_write(u32 addr,u32 reg,u32 data){writes++;op++;int failed=op==fail_op||writes==fail_write_at;if(failed&&!accept_failed_write)return 0;if(addr==31){assert(reg/4<32768);regs[reg/4]=data;if(reg==REG_ESW_VLAN_VTCR){unsigned cmd=(data>>12)&7,vid=data&4095;if(cmd==1)hardware_vlan[vid]=1;else if(cmd==2)hardware_vlan[vid]=0;}}else{assert(addr<32&&reg<32);phy[addr][reg]=data;}return !failed;}
static unsigned long copy_from_user(void*d,const void*s,size_t n){copy_in++;if(user_fault)return n;memcpy(d,s,n);return 0;}
static unsigned long copy_to_user(void*d,const void*s,size_t n){copy_out++;if(user_fault)return n;memcpy(d,s,n);return 0;}
#define put_user(v,p) copy_to_user((p),&(u32){v},sizeof(u32))
static void esw_show_bridge_partitions(u32 mode){(void)mode;}
'''
SUFFIX = r'''
static void reset_model(void){memset(regs,0,sizeof(regs));memset(phy,0,sizeof(phy));memset(g_vlan_pool,0,sizeof(g_vlan_pool));memset(g_vlan_pending,0,sizeof(g_vlan_pending));memset(hardware_vlan,0,sizeof(hardware_vlan));command_stuck=0;memset(g_vlan_rule,0,sizeof(g_vlan_rule));memset(g_vlan_rule_user,0,sizeof(g_vlan_rule_user));memset(g_port_phy_power,0,sizeof(g_port_phy_power));memset(g_port_link_mode,0,sizeof(g_port_link_mode));memset(g_bwan_member,0,sizeof(g_bwan_member));reads=writes=op=fail_op=fail_read_at=fail_write_at=busy_reads=always_busy=delays=locks=depth=copy_in=copy_out=user_fault=stub_changes=0;admin=1;accept_failed_write=0;g_led_apply_pending=g_storm_apply_pending=g_jumbo_apply_pending=false;memset(g_link_apply_pending,0,sizeof(g_link_apply_pending));g_led_phy_mode=SWAPI_LED_LINK_ACT;g_storm_rate_limit=0;g_jumbo_frames_enabled=0;g_wan_bridge_mode=g_wan_bwan_isolation=0;g_bridge_apply_pending=false;g_igmp_apply_pending=false;g_igmp_snooping_enabled=1;g_igmp_static_ports=0;g_vlan_pvid_wan_untagged=77;g_switch_inited.value=g_switch_allow_irq.value=g_port_link_changed.value=0;g_vlan_rule[0]=7;g_vlan_rule_user[0]=9;fill_bridge_members();}
static int no_effects(void){return !reads&&!writes&&!copy_in&&!copy_out&&!locks&&!depth&&!stub_changes&&g_vlan_rule[0]==7&&g_port_link_changed.value==1;}
static const unsigned setters[]={MTK_ESW_IOCTL_PORTS_POWER,MTK_ESW_IOCTL_PORTS_WAN_LAN_POWER,MTK_ESW_IOCTL_BRIDGE_MODE,MTK_ESW_IOCTL_VLAN_ACCEPT_PORT_MODE,MTK_ESW_IOCTL_VLAN_CREATE_PORT_VID,MTK_ESW_IOCTL_VLAN_CREATE_ENTRY,MTK_ESW_IOCTL_VLAN_RULE_SET,MTK_ESW_IOCTL_STORM_BROADCAST,MTK_ESW_IOCTL_JUMBO_FRAMES,MTK_ESW_IOCTL_IGMP_SNOOPING,MTK_ESW_IOCTL_IGMP_STATIC_PORTS,MTK_ESW_IOCTL_LED_MODE,MTK_ESW_IOCTL_SPEED_PORT};
int main(int argc,char**argv){if(argc!=2)return 91;const char*name=argv[1];CASE_ADMISSION
 long ret=0;int state=1,boundary=1,total=0;u32 value=1,out_pvid=88;unsigned char out[sizeof(esw_mib_counters_t)] __attribute__((aligned(__alignof__(esw_mib_counters_t)))),saved[sizeof(out)];memset(out,0xa7,sizeof(out));memcpy(saved,out,sizeof(out));reset_model();
 if(!strcmp(name,"mib-invalid-canary")){ret=esw_status_mib_port_uapi(99,(esw_mib_counters_t*)out);state=!memcmp(out,saved,sizeof(out));boundary=!op;}
 else if(!strcmp(name,"mib-success-zero-padding")){ret=esw_status_mib_port_uapi(SWAPI_PORT_LAN1,(esw_mib_counters_t*)out);for(unsigned i=0;i<sizeof(out);i++)state&=out[i]==0;boundary=reads==19&&!writes;}
 else if(!strcmp(name,"mib-every-read-failure")){for(int i=1;i<=19;i++){reset_model();fail_read_at=i;memcpy(out,saved,sizeof(out));ret=esw_status_mib_port_uapi(SWAPI_PORT_LAN1,(esw_mib_counters_t*)out);state&=ret==-EIO&&!memcmp(out,saved,sizeof(out));boundary&=reads==i&&!writes;}}
 else if(!strncmp(name,"mib-ioctl-",10)||!strcmp(name,"mib-output-efault")){unsigned port=strstr(name,"invalid")?99:SWAPI_PORT_LAN1;if(strstr(name,"read-failure"))fail_read_at=8;if(strstr(name,"efault"))user_fault=1;ret=mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_STATUS_MIB_PORT|(port<<8),(unsigned long)out);if(!strcmp(name,"mib-ioctl-success")){for(unsigned i=0;i<sizeof(out);i++)state&=out[i]==0;boundary=copy_out==1;}else{state=!memcmp(out,saved,sizeof(out));boundary=copy_out==(strstr(name,"efault")?1:0);}}
 else if(!strncmp(name,"bytes-",6)){unsigned port=strstr(name,"invalid")?99:SWAPI_PORT_LAN1;if(strstr(name,"read-failure"))fail_read_at=3;if(strstr(name,"efault"))user_fault=1;ret=mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_STATUS_BYTES_PORT|(port<<8),(unsigned long)out);state=!memcmp(out,saved,sizeof(out));boundary=copy_out==(strstr(name,"efault")?1:0);}
 else if(!strcmp(name,"all-setter-efault-no-hardware")){for(unsigned i=0;i<sizeof(setters)/sizeof(setters[0]);i++){reset_model();user_fault=1;ret=mtk_esw_ioctl(NULL,setters[i],(unsigned long)&value);state&=ret==-EFAULT&&!op&&!stub_changes&&g_vlan_rule[0]==7&&g_vlan_rule_user[0]==9;boundary&=copy_in==1&&!copy_out&&locks==1&&!depth;}}
 else if(!strcmp(name,"all-admin-commands-denied-no-effects")){for(unsigned i=0;i<sizeof(setters)/sizeof(setters[0])+3;i++){reset_model();admin=0;user_fault=1;g_port_link_changed.value=1;unsigned cmd=i<sizeof(setters)/sizeof(setters[0])?setters[i]:i==sizeof(setters)/sizeof(setters[0])?MTK_ESW_IOCTL_MAC_TABLE_CLEAR:i==sizeof(setters)/sizeof(setters[0])+1?MTK_ESW_IOCTL_VLAN_RESET_TABLE:MTK_ESW_IOCTL_STATUS_LINK_CHANGED;ret=mtk_esw_ioctl(NULL,cmd,(unsigned long)&value);state&=ret==-EPERM;boundary&=no_effects();}}
 else if(!strcmp(name,"unprivileged-pure-reads")){const unsigned cmds[]={MTK_ESW_IOCTL_STATUS_LINK_PORT,MTK_ESW_IOCTL_STATUS_LINK_PORTS_WAN,MTK_ESW_IOCTL_STATUS_LINK_PORTS_LAN,MTK_ESW_IOCTL_STATUS_SPEED_PORT,MTK_ESW_IOCTL_STATUS_BYTES_PORT,MTK_ESW_IOCTL_STATUS_MIB_PORT,MTK_ESW_IOCTL_VLAN_PVID_WAN_GET};for(unsigned i=0;i<sizeof(cmds)/sizeof(cmds[0]);i++){reset_model();admin=0;ret=mtk_esw_ioctl(NULL,cmds[i]|(SWAPI_PORT_LAN1<<8),(unsigned long)out);state&=ret==0;boundary&=!writes&&!copy_in&&copy_out==1;}}
 else if(!strcmp(name,"link-change-denied-not-consumed")){admin=0;g_port_link_changed.value=1;ret=mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_STATUS_LINK_CHANGED,(unsigned long)&value);state=g_port_link_changed.value==1;boundary=no_effects();}
 else if(!strcmp(name,"link-change-efault-restored")){user_fault=1;g_port_link_changed.value=1;ret=mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_STATUS_LINK_CHANGED,(unsigned long)&value);state=g_port_link_changed.value==1;boundary=copy_out==1&&!op&&!depth;}
 else if(!strcmp(name,"admin-positive-mutation")){ret=mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_MAC_TABLE_CLEAR,0);state=ret==0;boundary=reads==1&&writes==1&&locks==1;}
 else if(!strcmp(name,"scalar-output-efault")){user_fault=1;ret=mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_VLAN_PVID_WAN_GET,(unsigned long)&value);state=value==1;boundary=copy_out==1&&!depth;}
 else if(!strncmp(name,"vtcr-",5)){if(strstr(name,"write-failure"))fail_write_at=1;if(strstr(name,"read-failure"))fail_read_at=1;if(strstr(name,"timeout"))always_busy=1;if(strstr(name,"then-ready"))busy_reads=2;ret=esw_write_vtcr(1,100);state=!test_bit(100,g_vlan_pool);boundary=strstr(name,"write-failure")?writes==1&&reads==1:strstr(name,"read-failure")?!writes&&reads==1:strstr(name,"timeout")?!writes&&reads==200&&delays==20000:writes==1&&reads==4&&delays==400;}
 else if(!strcmp(name,"vlan-set-every-write-failure")){for(int i=1;i<=3;i++){reset_model();fail_write_at=i;ret=esw_vlan_set(100,0,3,3,0,0);state&=ret==-EIO&&!test_bit(100,g_vlan_pool);boundary&=writes==i&&reads>=1;}}
 else if(!strcmp(name,"vlan-set-read-failure")){fail_read_at=1;ret=esw_vlan_set(100,0,3,3,0,0);state=!test_bit(100,g_vlan_pool);boundary=!writes&&reads==1;}
 else if(!strcmp(name,"vlan-set-success")){ret=esw_vlan_set(100,0,3,3,0,0);state=test_bit(100,g_vlan_pool);boundary=writes==3&&reads==3;}
 else if(!strncmp(name,"vlan-delete-",12)){memset(g_vlan_pool,0,sizeof(g_vlan_pool));set_bit(100,g_vlan_pool);set_bit(101,g_vlan_pool);if(strstr(name,"read-failure"))fail_read_at=1;else fail_write_at=strstr(name,"partial")?2:1;ret=esw_vlan_reset_table();state=test_bit(101,g_vlan_pool)&&(strstr(name,"partial")?!test_bit(100,g_vlan_pool):test_bit(100,g_vlan_pool));boundary=ret==-EIO;if(strstr(name,"retry")){fail_write_at=0;ret=esw_vlan_reset_table();state&=!test_bit(100,g_vlan_pool)&&!test_bit(101,g_vlan_pool);boundary&=ret==0;}}
 else if(!strncmp(name,"port-rmw-",9)){if(strstr(name,"read-failure"))fail_read_at=1;else fail_write_at=1;regs[REG_ESW_PORT_PVC_P0/4]=0xabcdef00;ret=esw_port_attrib_set(0,3);state=regs[REG_ESW_PORT_PVC_P0/4]==0xabcdef00;boundary=reads==1&&writes==(strstr(name,"read-failure")?0:1);}
 else if(!strcmp(name,"apply-success-stages-only")){ret=esw_vlan_apply_rules(1,1,&out_pvid);state=g_vlan_rule[0]==7&&g_vlan_pvid_wan_untagged==77&&out_pvid==2;boundary=reads>0&&writes>0;}
 else if(!strcmp(name,"apply-every-mdio-failure-no-publication")){ret=esw_vlan_apply_rules(1,1,&out_pvid);total=op;for(int i=1;i<=total;i++){reset_model();out_pvid=88;fail_op=i;ret=esw_vlan_apply_rules(1,1,&out_pvid);state&=ret==-EIO&&g_vlan_rule[0]==7&&g_vlan_pvid_wan_untagged==77&&out_pvid==88;boundary&=op==i;}}
 else if(!strcmp(name,"bridge-every-mdio-failure-retryable")){g_switch_inited.value=1;ret=change_bridge_mode(1,1);total=op;for(int i=1;i<=total;i++){reset_model();g_switch_inited.value=1;fail_op=i;ret=change_bridge_mode(1,1);state&=ret==-EIO&&g_bridge_apply_pending&&g_wan_bridge_mode==0&&g_wan_bwan_isolation==0&&g_vlan_rule[0]==7&&g_vlan_pvid_wan_untagged==77;boundary&=op>=i;}}
 else if(!strcmp(name,"bridge-old-request-recovery")){g_switch_inited.value=1;fail_op=8;ret=change_bridge_mode(1,1);state=ret==-EIO&&g_bridge_apply_pending;fail_op=0;g_vlan_rule_user[0]=7;ret=change_bridge_mode(0,0);state&=!g_bridge_apply_pending&&g_wan_bridge_mode==0&&g_vlan_rule[0]==7;boundary=!depth;}
 else if(!strcmp(name,"init-every-mdio-failure-no-ready")){ret=esw_ioctl_init_post();total=op;for(int i=1;i<=total;i++){reset_model();g_switch_inited.value=g_switch_allow_irq.value=1;fail_op=i;ret=esw_ioctl_init_post();state&=ret==-EIO&&!g_switch_inited.value&&!g_switch_allow_irq.value&&g_bridge_apply_pending&&g_vlan_rule[0]==7&&g_vlan_pvid_wan_untagged==77;boundary&=!depth&&op==i;}}
 else if(!strcmp(name,"igmp-every-mdio-failure-retryable")){ret=change_igmp_snooping_control(0);total=op;for(int i=1;i<=total;i++){reset_model();fail_op=i;ret=change_igmp_snooping_control(0);state&=ret==-EIO&&g_igmp_snooping_enabled==1&&g_igmp_apply_pending;fail_op=0;int retry=change_igmp_snooping_control(1);boundary&=retry==0&&!g_igmp_apply_pending;}}
 else if(!strncmp(name,"vlan-uncertain-",15)||!strncmp(name,"vlan-prior-busy-",16)){if(strstr(name,"read-cleanup"))fail_read_at=3;else command_stuck=1;ret=esw_vlan_set(100,0,3,3,0,0);state=ret==(strstr(name,"read-cleanup")?-EIO:-ETIMEDOUT)&&hardware_vlan[100]&&test_bit(100,g_vlan_pending)&&!test_bit(100,g_vlan_pool);int prior_writes=writes;if(strstr(name,"no-overwrite")){ret=esw_vlan_set(101,0,3,3,0,0);state&=hardware_vlan[100]&&!hardware_vlan[101]&&test_bit(100,g_vlan_pending);boundary=ret==-ETIMEDOUT&&writes==prior_writes;}else{fail_read_at=0;command_stuck=0;if(strstr(name,"then-ready")){busy_reads=2;ret=esw_vlan_set(101,0,3,3,0,0);state&=ret==0&&hardware_vlan[100]&&hardware_vlan[101]&&test_bit(101,g_vlan_pool);}ret=esw_vlan_reset_table();boundary=ret==0&&!hardware_vlan[100]&&!hardware_vlan[101]&&!test_bit(100,g_vlan_pending)&&!test_bit(101,g_vlan_pool);}}
 else if(!strncmp(name,"phy-",4)){phy[1][0]=BIT(11);if(strstr(name,"read"))fail_read_at=1;else fail_write_at=1;ret=esw_port_phy_power(1,1,0);state=g_port_phy_power[1]==0;boundary=reads==1&&writes==(strstr(name,"read")?0:1);}

 else if(!strncmp(name,"led-",4)){if(strstr(name,"every")){for(int i=1;i<=2;i++){reset_model();fail_op=i;regs[0x7d00/4]=0xa5a00000;ret=change_led_mode(SWAPI_LED_OFF);state&=ret==-EIO&&g_led_phy_mode==SWAPI_LED_LINK_ACT&&g_led_apply_pending;boundary&=op==i&&writes==(i==1?0:1);}}else if(strstr(name,"retry")||strstr(name,"recovery")){fail_write_at=1;ret=change_led_mode(SWAPI_LED_OFF);state=ret==-EIO&&g_led_apply_pending;fail_write_at=0;int before=op;ret=change_led_mode(strstr(name,"recovery")?SWAPI_LED_LINK_ACT:SWAPI_LED_OFF);state&=!g_led_apply_pending&&g_led_phy_mode==(strstr(name,"recovery")?SWAPI_LED_LINK_ACT:SWAPI_LED_OFF);boundary=op==before+2;}else{regs[0x7d00/4]=0xa5afffff;ret=change_led_mode(SWAPI_LED_OFF);state=g_led_phy_mode==SWAPI_LED_OFF&&regs[0x7d00/4]==(0xa5afffff&~0x77777u);int before=op;ret=change_led_mode(SWAPI_LED_OFF);boundary=op==before;}}
 else if(!strncmp(name,"storm-",6)){if(strstr(name,"encoding")){const u32 rates[]={0,5,100,1023,1024},words[]={0,0xc2050505,0xc2645a09,0xc3ff1602,0};for(unsigned k=0;k<5;k++){reset_model();g_storm_apply_pending=true;ret=change_storm_control_broadcast(rates[k]);state&=ret==0&&g_storm_rate_limit==(rates[k]>=1024?0:rates[k])&&!g_storm_apply_pending;for(unsigned j=0;j<=4;j++)boundary&=regs[(REG_ESW_PORT_BSR_P0+0x100*j)/4]==words[k];}}else{for(int i=1;i<=5;i++){reset_model();fail_write_at=i;ret=change_storm_control_broadcast(100);state&=ret==-EIO&&g_storm_rate_limit==0&&g_storm_apply_pending;boundary&=writes==i;if(!strstr(name,"every")){fail_write_at=0;int before=writes;ret=change_storm_control_broadcast(strstr(name,"recovery")?0:100);state&=ret==0&&!g_storm_apply_pending&&g_storm_rate_limit==(strstr(name,"recovery")?0:100);boundary&=writes==before+5;for(unsigned j=0;j<=4;j++)state&=regs[(REG_ESW_PORT_BSR_P0+0x100*j)/4]==(strstr(name,"recovery")?0:0xc2645a09);}}}}
 else if(!strncmp(name,"jumbo-",6)){if(strstr(name,"every")){for(int i=1;i<=2;i++){reset_model();fail_op=i;regs[REG_ESW_MAC_GMACCR/4]=0xabcd0000;ret=change_jumbo_frames_accept(1);state&=ret==-EIO&&g_jumbo_frames_enabled==0&&g_jumbo_apply_pending;boundary&=op==i&&writes==(i==1?0:1);}}else if(strstr(name,"retry")||strstr(name,"recovery")){fail_write_at=1;ret=change_jumbo_frames_accept(1);state=ret==-EIO&&g_jumbo_apply_pending;fail_write_at=0;int before=op;ret=change_jumbo_frames_accept(strstr(name,"recovery")?0:1);state&=!g_jumbo_apply_pending&&g_jumbo_frames_enabled==(strstr(name,"recovery")?0:1);boundary=op==before+2;}else{regs[REG_ESW_MAC_GMACCR/4]=0xabcdffff;ret=change_jumbo_frames_accept(1);state=g_jumbo_frames_enabled==1&&regs[REG_ESW_MAC_GMACCR/4]==0xabcdffe7;int before=op;ret=change_jumbo_frames_accept(1);boundary=op==before;}}
 else if(!strncmp(name,"link-auto-",10)||!strncmp(name,"link-force-every",16)||!strcmp(name,"link-same-request-retry")||!strcmp(name,"link-old-request-recovery")){u32 mode=strstr(name,"link-auto")?SWAPI_LINK_SPEED_MODE_AUTO_100_FD:SWAPI_LINK_SPEED_MODE_FORCE_100_FD;int limit=mode==SWAPI_LINK_SPEED_MODE_FORCE_100_FD?5:4;for(int i=1;i<=limit;i++){reset_model();phy[3][9]=0xa5a5;g_port_phy_power[3]=1;fail_op=i;ret=change_port_link_mode_uapi(SWAPI_PORT_LAN1,mode);state&=ret==-EIO&&g_port_link_mode[3]==0&&g_port_phy_power[3]==1&&g_link_apply_pending[3];boundary&=op==i&&writes==i-1;if(strstr(name,"retry")||strstr(name,"recovery")){fail_op=0;int before=op;ret=change_port_link_mode_uapi(SWAPI_PORT_LAN1,strstr(name,"recovery")?0:mode);state&=ret==0&&!g_link_apply_pending[3]&&g_port_link_mode[3]==(strstr(name,"recovery")?0:mode);boundary&=op>before;}}}
 else if(!strcmp(name,"link-force-off-success")){g_port_phy_power[3]=1;ret=change_port_link_mode_uapi(SWAPI_PORT_LAN1,SWAPI_LINK_SPEED_MODE_FORCE_POWER_OFF);state=g_port_link_mode[3]==SWAPI_LINK_SPEED_MODE_FORCE_POWER_OFF&&!g_port_phy_power[3]&&!g_link_apply_pending[3]&&(phy[3][0]&BIT(11));int before=op;ret=change_port_link_mode_uapi(SWAPI_PORT_LAN1,SWAPI_LINK_SPEED_MODE_FORCE_POWER_OFF);boundary=op==before;}
 else if(!strcmp(name,"link-invalid-mode-no-effects")){const u32 invalid[]={10,11,12,13,14,0x300,0x10000};for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++){reset_model();ret=change_port_link_mode_uapi(SWAPI_PORT_LAN1,invalid[i]);state&=ret==-EINVAL&&!g_link_apply_pending[3]&&g_port_link_mode[3]==0;boundary&=!op;}ret=change_port_link_mode_uapi(99,1);boundary&=!op;}
 else if(!strcmp(name,"controls-ioctl-propagates-errors")){const unsigned cmds[]={MTK_ESW_IOCTL_LED_MODE,MTK_ESW_IOCTL_STORM_BROADCAST,MTK_ESW_IOCTL_JUMBO_FRAMES,MTK_ESW_IOCTL_SPEED_PORT};const u32 values[]={SWAPI_LED_OFF,100,1,SWAPI_LINK_SPEED_MODE_FORCE_100_FD};for(unsigned i=0;i<4;i++){reset_model();fail_op=1;value=values[i];ret=mtk_esw_ioctl(NULL,cmds[i]|(SWAPI_PORT_LAN1<<8),(unsigned long)&value);state&=ret==-EIO;boundary&=copy_in==1&&!copy_out&&locks==1&&!depth;}}
 else if(!strcmp(name,"controls-ambiguous-write-old-request-recovery")){for(unsigned i=0;i<5;i++){reset_model();accept_failed_write=1;fail_write_at=i>=3?(int)i:1;if(i==0)ret=change_led_mode(SWAPI_LED_OFF);else if(i==1)ret=change_storm_control_broadcast(100);else if(i==2)ret=change_jumbo_frames_accept(1);else ret=change_port_link_mode_uapi(SWAPI_PORT_LAN1,SWAPI_LINK_SPEED_MODE_FORCE_100_FD);state&=ret==-EIO;accept_failed_write=fail_write_at=0;int before=op;if(i==0){ret=change_led_mode(SWAPI_LED_LINK_ACT);state&=(regs[0x7d00/4]&0x77777)==0x77777;}else if(i==1){ret=change_storm_control_broadcast(0);for(unsigned j=0;j<=4;j++)state&=regs[(REG_ESW_PORT_BSR_P0+0x100*j)/4]==0;}else if(i==2){ret=change_jumbo_frames_accept(0);state&=(regs[REG_ESW_MAC_GMACCR/4]&63)==37;}else{ret=change_port_link_mode_uapi(SWAPI_PORT_LAN1,0);state&=(phy[3][0]&(BIT(11)|BIT(12)|BIT(9)))==(BIT(12)|BIT(9));}boundary&=ret==0&&op>before;}}
 else if(!strcmp(name,"status-every-query-read-failure-no-copy")){const unsigned cmds[]={MTK_ESW_IOCTL_STATUS_LINK_PORT,MTK_ESW_IOCTL_STATUS_LINK_PORTS_WAN,MTK_ESW_IOCTL_STATUS_LINK_PORTS_LAN,MTK_ESW_IOCTL_STATUS_SPEED_PORT};for(unsigned i=0;i<4;i++){reset_model();fail_read_at=i==2?2:1;value=0xabcdef01;ret=mtk_esw_ioctl(NULL,cmds[i]|(SWAPI_PORT_LAN1<<8),(unsigned long)&value);state&=ret==-EIO&&value==0xabcdef01;boundary&=!copy_out&&!writes&&reads==fail_read_at;}}
 else if(!strcmp(name,"status-invalid-port-no-copy")){const unsigned cmds[]={MTK_ESW_IOCTL_STATUS_LINK_PORT,MTK_ESW_IOCTL_STATUS_SPEED_PORT};for(unsigned i=0;i<2;i++){reset_model();value=0xabcdef01;ret=mtk_esw_ioctl(NULL,cmds[i]|(99<<8),(unsigned long)&value);state&=ret==-EINVAL&&value==0xabcdef01;boundary&=!op&&!copy_out;}}
 else if(!strcmp(name,"status-success-packed-and-down")){regs[(REG_ESW_MAC_PMSR_P0+0x300)/4]=0x7b;ret=esw_status_speed_port_uapi(SWAPI_PORT_LAN1,&value);state=value==0x10f02;ret=esw_status_link_port_uapi(SWAPI_PORT_LAN1,&value);state&=value==1;ret=esw_status_link_ports(0,&value);state&=value==1;regs[(REG_ESW_MAC_PMSR_P0+0x300)/4]=0;ret=esw_status_speed_port_uapi(SWAPI_PORT_LAN1,&value);state&=value==0;boundary=!writes;}
 else if(!strcmp(name,"status-direct-read-failure-preserves-output")){for(unsigned i=0;i<4;i++){reset_model();fail_read_at=1;value=0xabcdef01;if(i==0)ret=esw_status_link_port(3,&value);else if(i==1)ret=esw_status_link_port_uapi(SWAPI_PORT_LAN1,&value);else if(i==2)ret=esw_status_speed_port_uapi(SWAPI_PORT_LAN1,&value);else ret=esw_status_link_ports(0,&value);state&=ret==-EIO&&value==0xabcdef01;boundary&=reads==1&&!writes;}}

 else if(!strncmp(name,"init-failure-invalidates-",25)||!strncmp(name,"init-success-invalidates-",25)){g_switch_inited.value=g_switch_allow_irq.value=1;g_storm_rate_limit=100;g_jumbo_frames_enabled=1;g_port_link_mode[3]=SWAPI_LINK_SPEED_MODE_FORCE_100_FD;if(strstr(name,"failure"))fail_op=1;ret=esw_ioctl_init_post();state=(strstr(name,"failure")?ret==-EIO&&!g_switch_inited.value&&g_led_apply_pending:ret==0&&g_switch_inited.value&&!g_led_apply_pending)&&g_storm_apply_pending&&g_jumbo_apply_pending&&g_link_apply_pending[3];fail_op=0;int before=op;ret=change_led_mode(g_led_phy_mode);boundary=ret==0&&op==before+(strstr(name,"failure")?2:0);before=op;ret=change_storm_control_broadcast(100);boundary&=ret==0&&op==before+5;before=op;ret=change_jumbo_frames_accept(1);boundary&=ret==0&&op==before+2;before=op;ret=change_port_link_mode_uapi(SWAPI_PORT_LAN1,SWAPI_LINK_SPEED_MODE_FORCE_100_FD);boundary&=ret==0&&op==before+5&&!g_led_apply_pending&&!g_storm_apply_pending&&!g_jumbo_apply_pending&&!g_link_apply_pending[3];}
 else return 92;
 printf("[%ld,%d,%d]\n",ret,state,boundary);assert(!depth);return 0;}
'''
def source_declarations(texts):
    result={}
    for pattern,key in SOURCE_DECLARATIONS.items():
        matches=list(re.finditer(pattern,texts[key],re.M))
        if len(matches)!=1:raise ValueError('ESW VLAN declaration missing/ambiguous: '+pattern)
        result[pattern]=matches[0].group()
    return result
def validate_inputs(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact VLAN sources required')
    source_declarations(texts)
    if not re.search(r'(?m)^CONFIG_MULTIUSER=y$',texts['config']):raise ValueError('MULTIUSER capability implementation required')
    for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items():function(texts[k],n)
    for n,k in FUNCTION_SOURCES.items():function(texts[k],n)
def generate_source(texts):
    validate_inputs(texts)
    definitions=[]
    for n in CONFIG_NAMES:
        m=re.findall(r'(?m)^'+n+r'=(\d+)$',texts['config'])
        if len(m)!=1:raise ValueError('K2P port definition absent: '+n)
        definitions.append('#define '+n+' '+m[0])
    definitions.extend(texts[k].replace('#include "esw_common.h"','') for k in HEADER_KEYS)
    definitions.extend(source_declarations(texts).values())
    bodies=[function(texts[FUNCTION_SOURCES[n]],n) for n in BODY_ORDER]
    prototypes='\n'.join(body[:body.index('{')].strip()+';'for body in bodies)
    admission='if(!('+ '||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return PREFIX.replace('HEADERS_AND_DEFINITIONS','\n'.join(definitions)).replace('FUNCTION_DECLARATIONS',prototypes)+'\n'+'\n\n'.join(bodies)+'\n'+SUFFIX.replace('CASE_ADMISSION',admission)
def function_manifest(texts):
    validate_inputs(texts)
    return {n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}

def source_only_manifest(texts):
    validate_inputs(texts)
    return {n:{"source":k,"execution":"source-only","full_body_sha256":hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}

def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'(?m)^(?:static\s+)?[A-Za-z_][\w \t*]*\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked))
    if len(matches)!=1:raise ValueError('Missing/ambiguous MDIO body: '+name)
    start=matches[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer('[{}]',masked[opening:]):
        depth+=1 if m.group()=='{'else -1
        if depth==0:return text[start:opening+m.end()]
    raise ValueError('Unterminated MDIO body: '+name)

