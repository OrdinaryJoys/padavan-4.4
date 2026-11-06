"""Actual enabled MAC-clear error chain; inert MDIO/VLAN/UAPI seams, no hardware acceptance."""
import hashlib
import re
SOURCE_PATHS = {'esw': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl_mt762x.c',
 'ioctl': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl.c',
 'header': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl.h',
 'errno_base': 'trunk/linux-4.4.x/include/uapi/asm-generic/errno-base.h',
 'errno': 'trunk/linux-4.4.x/arch/mips/include/uapi/asm/errno.h',
 'kerrno': 'trunk/linux-4.4.x/include/linux/errno.h',
 'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
 'config': 'trunk/configs/boards/K2P/kernel-4.4.x.config'}
FUNCTION_SOURCES = {'mt7530_gsw_wait_wt_mac': 'esw',
 'mt7530_gsw_mac_table_clear': 'esw',
 'esw_mac_table_clear': 'esw',
 'esw_vlan_bridge_isolate': 'esw',
 'change_bridge_mode': 'esw',
 'esw_ioctl_init_post': 'esw',
 'mtk_esw_ioctl': 'ioctl'}
BODY_ORDER = ('mt7530_gsw_wait_wt_mac',
 'mt7530_gsw_mac_table_clear',
 'esw_mac_table_clear',
 'esw_vlan_bridge_isolate',
 'change_bridge_mode',
 'esw_ioctl_init_post',
 'mtk_esw_ioctl')
SOURCE_ONLY_FUNCTION_SOURCES = {'esw_vlan_apply_rules': 'esw',
 'esw_vlan_init_vid1': 'esw',
 'esw_mask_bridge_isolate': 'esw',
 'change_wan_lan_ports_power': 'esw',
 'ei_open': 'raeth'}
SOURCE_DECLARATIONS = {'^#define\\s+MTK_ESW_IOCTL_CMD_LENGTH_BITS\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STATUS_LINK_PORT\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STATUS_LINK_PORTS_WAN\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STATUS_LINK_PORTS_LAN\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STATUS_LINK_CHANGED\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STATUS_SPEED_PORT\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STATUS_BYTES_PORT\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STATUS_MIB_PORT\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STATUS_MIB_RESET_ALL\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_RESET_SWITCH\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_PORTS_POWER\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_PORTS_WAN_LAN_POWER\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_MAC_TABLE_CLEAR\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_BRIDGE_MODE\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_PORT_FORWARD_MASK\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_VLAN_RESET_TABLE\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_VLAN_PVID_WAN_GET\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_VLAN_ACCEPT_PORT_MODE\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_VLAN_CREATE_PORT_VID\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_VLAN_CREATE_ENTRY\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_VLAN_RULE_SET\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_STORM_BROADCAST\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_JUMBO_FRAMES\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_EEE_LPI\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_IGMP_SNOOPING\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_IGMP_STATIC_PORTS\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_LED_MODE\\s+[^\\n]+$': 'header',
 '^#define\\s+MTK_ESW_IOCTL_SPEED_PORT\\s+[^\\n]+$': 'header',
 '^#define\\s+SWAPI_WAN_BRIDGE_DISABLE\\s+[^\\n]+$': 'header',
 '^#define\\s+SWAPI_WAN_BRIDGE_DISABLE_WAN\\s+[^\\n]+$': 'header',
 '^#define\\s+SWAPI_WAN_BWAN_ISOLATION_NONE\\s+[^\\n]+$': 'header',
 '^#define\\s+SWAPI_WAN_BWAN_ISOLATION_BETWEEN\\s+[^\\n]+$': 'header',
 '^#define\\s+SWAPI_VLAN_RULE_WAN_LAN4\\s+[^\\n]+$': 'header',
 '^#define\\s+SWAPI_VLAN_RULE_NUM\\s+[^\\n]+$': 'header',
 '^#define\\s+EIO\\s+[^\\n]+$': 'errno_base',
 '^#define\\s+EFAULT\\s+[^\\n]+$': 'errno_base',
 '^#define\\s+EINVAL\\s+[^\\n]+$': 'errno_base',
 '^#define\\s+ETIMEDOUT\\s+[^\\n]+$': 'errno',
 '^#define\\s+ENOIOCTLCMD\\s+[^\\n]+$': 'kerrno',
 '^static bool g_bridge_apply_pending;': 'esw'}
MODEL_VARIANT = {'K2P_RAETH_ESW_CONTROL': True,
 'shipping_disabled_MT7620_extra_switch': True,
 'whole_MAC_error_chain_execution': True,
 'mdio_controller_is_inert': True,
 'twenty_ms_delay_excludes_MDIO_transaction_budgets_and_lock_wait': True,
 'VLAN_programming_is_inert_side_effect_seam_not_real_algorithm': True,
 'atomic_and_mutex_shims_are_sequential_not_kernel_scheduling': True,
 'wire_layout_is_actual_kernel_ABI': False,
 'ei_open_is_source_only_here_and_whole_function_in_raeth_runtime_model': True}
FIELDS = ('ret',
 'second',
 'writes',
 'reads',
 'delay_us',
 'last_atc',
 'locks',
 'lock_errors',
 'apply',
 'vid1',
 'mask',
 'show',
 'power_down',
 'power_up',
 'sleep_ms',
 'led',
 'mac_enable',
 'ready',
 'allow_irq',
 'bridge',
 'isolation',
 'rule0',
 'pvid',
 'pending')
CASE_NAMES = ('clear-ok',
 'clear-static',
 'clear-write-fail',
 'clear-read-fail',
 'clear-late-read-fail',
 'clear-busy-timeout',
 'clear-busy-then-ok',
 'wrapper-write-fail',
 'ioctl-clear-ok',
 'ioctl-clear-write-fail',
 'ioctl-clear-read-fail',
 'ioctl-clear-busy-timeout',
 'bridge-ok',
 'bridge-write-fail',
 'bridge-read-fail',
 'bridge-busy-timeout',
 'bridge-retry',
 'bridge-old-state-after-fail',
 'bridge-invalid-mode',
 'bridge-invalid-isolation',
 'bridge-uaccess-fail',
 'bridge-pending-init',
 'bridge-noop',
 'disable-wan-ok',
 'disable-wan-write-fail',
 'init-ok',
 'init-write-fail',
 'init-read-fail',
 'init-busy-timeout',
 'init-prior-ready-fail',
 'init-retry',
 'unknown-ioctl')
EXPECTED_ROWS = {'clear-ok': [0, 999, 1, 1, 100, 32770, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'clear-static': [0, 999, 1, 1, 100, 34306, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'clear-write-fail': [-5, 999, 1, 0, 0, 32770, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'clear-read-fail': [-5, 999, 1, 1, 100, 32770, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'clear-late-read-fail': [-5, 999, 1, 2, 200, 32770, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'clear-busy-timeout': [-145,
                        999,
                        1,
                        200,
                        20000,
                        32770,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        7,
                        77,
                        0],
 'clear-busy-then-ok': [0, 999, 1, 3, 300, 32770, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'wrapper-write-fail': [-5, 999, 1, 0, 0, 32770, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'ioctl-clear-ok': [0, 999, 1, 1, 100, 32770, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'ioctl-clear-write-fail': [-5, 999, 1, 0, 0, 32770, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'ioctl-clear-read-fail': [-5, 999, 1, 1, 100, 32770, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0],
 'ioctl-clear-busy-timeout': [-145,
                              999,
                              1,
                              200,
                              20000,
                              32770,
                              1,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              0,
                              7,
                              77,
                              0],
 'bridge-ok': [0, 999, 1, 1, 100, 32770, 1, 0, 1, 0, 1, 1, 1, 1, 500, 0, 0, 1, 1, 1, 1, 9, 2, 0],
 'bridge-write-fail': [-5, 999, 1, 0, 0, 32770, 1, 0, 1, 0, 1, 0, 1, 1, 500, 0, 0, 1, 1, 0, 0, 7, 77, 1],
 'bridge-read-fail': [-5, 999, 1, 1, 100, 32770, 1, 0, 1, 0, 1, 0, 1, 1, 500, 0, 0, 1, 1, 0, 0, 7, 77, 1],
 'bridge-busy-timeout': [-145,
                         999,
                         1,
                         200,
                         20000,
                         32770,
                         1,
                         0,
                         1,
                         0,
                         1,
                         0,
                         1,
                         1,
                         500,
                         0,
                         0,
                         1,
                         1,
                         0,
                         0,
                         7,
                         77,
                         1],
 'bridge-retry': [-5, 0, 2, 1, 100, 32770, 2, 0, 2, 0, 2, 1, 2, 2, 1000, 0, 0, 1, 1, 1, 1, 9, 2, 0],
 'bridge-old-state-after-fail': [-5,
                                 0,
                                 2,
                                 1,
                                 100,
                                 32770,
                                 2,
                                 0,
                                 2,
                                 0,
                                 2,
                                 1,
                                 2,
                                 2,
                                 1000,
                                 0,
                                 0,
                                 1,
                                 1,
                                 0,
                                 0,
                                 7,
                                 2,
                                 0],
 'bridge-invalid-mode': [-22, 999, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 7, 77, 0],
 'bridge-invalid-isolation': [-22, 999, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 7, 77, 0],
 'bridge-uaccess-fail': [-14, 999, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 7, 77, 0],
 'bridge-pending-init': [0, 999, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 7, 77, 0],
 'bridge-noop': [0, 999, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 7, 77, 0],
 'disable-wan-ok': [0, 999, 1, 1, 100, 32770, 1, 0, 0, 1, 1, 1, 1, 1, 500, 0, 0, 1, 1, 8, 1, 7, 77, 0],
 'disable-wan-write-fail': [-5, 999, 1, 0, 0, 32770, 1, 0, 0, 1, 1, 0, 1, 1, 500, 0, 0, 1, 1, 0, 0, 7, 77, 1],
 'init-ok': [0, 999, 1, 1, 100, 32770, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 9, 2, 0],
 'init-write-fail': [-5, 999, 1, 0, 0, 32770, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 7, 77, 1],
 'init-read-fail': [-5, 999, 1, 1, 100, 32770, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 7, 77, 1],
 'init-busy-timeout': [-145,
                       999,
                       1,
                       200,
                       20000,
                       32770,
                       1,
                       0,
                       1,
                       0,
                       1,
                       0,
                       0,
                       0,
                       0,
                       0,
                       1,
                       0,
                       0,
                       0,
                       0,
                       7,
                       77,
                       1],
 'init-prior-ready-fail': [-5, 999, 1, 0, 0, 32770, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 7, 77, 1],
 'init-retry': [-5, 0, 2, 1, 100, 32770, 2, 0, 2, 0, 2, 1, 0, 0, 0, 1, 2, 1, 1, 0, 0, 9, 2, 0],
 'unknown-ioctl': [-515, 999, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 77, 0]}
PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#define CONFIG_RAETH_ESW_CONTROL
#define CONFIG_RALINK_MT7621
#define BIT(n) (1U<<(n))
#define __user
typedef uint32_t u32;
typedef struct {uint64_t RX,TX;} port_bytes_t;
typedef struct {int inert;} esw_mib_counters_t;
struct file {int inert;};
typedef struct {int value;} atomic_t;
SOURCE_DEFINITIONS
FUNCTION_DECLARATIONS
static u32 g_wan_bridge_mode,g_wan_bwan_isolation,g_vlan_rule[SWAPI_VLAN_RULE_NUM],g_vlan_rule_user[SWAPI_VLAN_RULE_NUM],g_vlan_pvid_wan_untagged,g_led_phy_mode;
static atomic_t g_switch_inited,g_switch_allow_irq;
static int esw_access_mutex,depth,lock_errors,locks,writes,reads,delay_us,last_atc,fail_write_at,fail_read_at,busy_reads,always_busy,user_fault;
static int applies,vid1,masks,shows,power_down,power_up,sleeps,leds,macs;
static void mutex_lock(int*p){(void)p;if(depth)lock_errors++;depth++;locks++;}
static void mutex_unlock(int*p){(void)p;if(depth!=1)lock_errors++;depth--;}
static int atomic_read(atomic_t*p){return p->value;}
static void atomic_set(atomic_t*p,int v){p->value=v;}
static void udelay(unsigned n){assert(n==100);delay_us+=(int)n;}
static u32 mii_mgr_write(u32 phy,u32 reg,u32 data){assert(phy==31&&reg==0x80&&(data==0x8002||data==0x8602));writes++;last_atc=(int)data;return writes!=fail_write_at;}
static u32 mii_mgr_read(u32 phy,u32 reg,u32*out){assert(phy==31&&reg==0x80&&out);reads++;if(reads==fail_read_at)return 0;*out=always_busy||reads<=busy_reads?BIT(15):0;return 1;}
static unsigned long copy_from_user(void*d,const void*s,size_t n){if(user_fault)return n;memcpy(d,s,n);return 0;}
static unsigned long copy_to_user(void*d,const void*s,size_t n){(void)d;(void)s;(void)n;return 0;}
#define put_user(v,p) do{(void)(v);(void)(p);}while(0)
static void require_owner(void){assert(depth==1);}
/* Explicit inert VLAN seams reproduce only their source-bound global mutations. */
static void esw_vlan_apply_rules(u32 mode,u32 iso){(void)mode;(void)iso;require_owner();applies++;memcpy(g_vlan_rule,g_vlan_rule_user,sizeof(g_vlan_rule));g_vlan_pvid_wan_untagged=2;}
static void esw_vlan_init_vid1(void){require_owner();vid1++;}
static void esw_mask_bridge_isolate(u32 mode,u32 iso){(void)mode;(void)iso;require_owner();masks++;}
static void esw_show_bridge_partitions(u32 mode){(void)mode;require_owner();shows++;}
static int change_wan_lan_ports_power(u32 on,u32 wan){(void)wan;require_owner();if(on)power_up++;else power_down++;return 1;}
static void msleep(unsigned n){require_owner();assert(n==500);sleeps+=(int)n;}
static void esw_mac_to_phy_enable(void){require_owner();macs++;}
static void esw_led_mode(u32 mode){(void)mode;require_owner();leds++;}
static u32 esw_status_link_port_uapi(u32 p){(void)p;return 0;}
static u32 esw_status_link_ports(int p){(void)p;return 0;}
static u32 esw_status_link_changed(void){return 0;}
static u32 esw_status_speed_port_uapi(u32 p){(void)p;return 0;}
static int esw_status_bytes_port_uapi(u32 p,port_bytes_t*b){(void)p;(void)b;return 0;}
static int esw_status_mib_port_uapi(u32 p,esw_mib_counters_t*b){(void)p;(void)b;return 0;}
static void change_ports_power(u32 a,u32 b){(void)a;(void)b;}
static void esw_vlan_reset_table(void){}
static void vlan_accept_port_mode(u32 a,u32 b){(void)a;(void)b;}
static void vlan_create_entry(u32 a,u32 b,int c){(void)a;(void)b;(void)c;}
static int change_vlan_rule(u32 a,u32 b){(void)a;(void)b;return 0;}
static void change_storm_control_broadcast(u32 a){(void)a;}
static void change_jumbo_frames_accept(u32 a){(void)a;}
static void change_igmp_snooping_control(u32 a){(void)a;}
static void change_igmp_static_ports(u32 a){(void)a;}
static void change_led_mode(u32 a){(void)a;}
static int change_port_link_mode_uapi(u32 a,u32 b){(void)a;(void)b;return 0;}
'''
SUFFIX = r'''
int main(int argc,char**argv){if(argc!=2)return 91;const char*name=argv[1];CASE_ADMISSION
 for(unsigned i=0;i<SWAPI_VLAN_RULE_NUM;i++){g_vlan_rule[i]=7;g_vlan_rule_user[i]=9;}g_vlan_pvid_wan_untagged=77;
 int second=999;long ret;u32 value=1,iso=1;
 if(strstr(name,"write-fail")||!strcmp(name,"bridge-retry")||!strcmp(name,"bridge-old-state-after-fail")||!strcmp(name,"init-retry")||!strcmp(name,"init-prior-ready-fail"))fail_write_at=1;
 if(strstr(name,"read-fail"))fail_read_at=!strcmp(name,"clear-late-read-fail")?2:1;
 if(strstr(name,"busy-timeout"))always_busy=1;
 if(!strcmp(name,"clear-busy-then-ok")||!strcmp(name,"clear-late-read-fail"))busy_reads=2;
 if(!strncmp(name,"clear-",6))ret=mt7530_gsw_mac_table_clear(!strcmp(name,"clear-static"));
 else if(!strcmp(name,"wrapper-write-fail"))ret=esw_mac_table_clear();
 else if(!strncmp(name,"init-",5)){if(!strcmp(name,"init-prior-ready-fail"))g_switch_inited.value=g_switch_allow_irq.value=1;ret=esw_ioctl_init_post();if(!strcmp(name,"init-retry"))second=esw_ioctl_init_post();}
 else if(!strncmp(name,"ioctl-clear-",12))ret=mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_MAC_TABLE_CLEAR,0);
 else if(!strcmp(name,"unknown-ioctl"))ret=mtk_esw_ioctl(NULL,255,0);
 else{g_switch_inited.value=g_switch_allow_irq.value=strcmp(name,"bridge-pending-init")!=0;if(!strcmp(name,"bridge-invalid-mode"))value=9;if(!strcmp(name,"bridge-invalid-isolation"))iso=3;if(!strcmp(name,"bridge-uaccess-fail"))user_fault=1;if(!strcmp(name,"bridge-noop")){value=0;iso=0;for(unsigned i=0;i<SWAPI_VLAN_RULE_NUM;i++)g_vlan_rule_user[i]=7;}if(!strncmp(name,"disable-wan-",12))value=SWAPI_WAN_BRIDGE_DISABLE_WAN;ret=mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_BRIDGE_MODE|(iso<<MTK_ESW_IOCTL_CMD_LENGTH_BITS),(unsigned long)&value);if(!strcmp(name,"bridge-retry"))second=(int)mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_BRIDGE_MODE|(iso<<MTK_ESW_IOCTL_CMD_LENGTH_BITS),(unsigned long)&value);if(!strcmp(name,"bridge-old-state-after-fail")){value=0;iso=0;for(unsigned i=0;i<SWAPI_VLAN_RULE_NUM;i++)g_vlan_rule_user[i]=7;second=(int)mtk_esw_ioctl(NULL,MTK_ESW_IOCTL_BRIDGE_MODE,(unsigned long)&value);}}
 printf("[%ld,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%u,%u,%u,%u,%d]\n",ret,second,writes,reads,delay_us,last_atc,locks,lock_errors,applies,vid1,masks,shows,power_down,power_up,sleeps,leds,macs,g_switch_inited.value,g_switch_allow_irq.value,g_wan_bridge_mode,g_wan_bwan_isolation,g_vlan_rule[0],g_vlan_pvid_wan_untagged,g_bridge_apply_pending);assert(!depth);return 0;}
'''
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

def validate_inputs(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact ESW error source set required')
    for pattern,key in SOURCE_DECLARATIONS.items():
        if len(list(re.finditer(pattern,texts[key],re.M)))!=1:raise ValueError('ESW declaration missing/ambiguous: '+pattern)
    for name,key in FUNCTION_SOURCES.items():function(texts[key],name)
    for name,key in SOURCE_ONLY_FUNCTION_SOURCES.items():function(texts[key],name)
def function_manifest(texts):
    validate_inputs(texts)
    return {n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}
def source_only_manifest(texts):
    validate_inputs(texts)
    return {n:{'source':k,'execution':'source-only-not-run','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
def source_declarations(texts):
    validate_inputs(texts)
    return {p:{'source':k,'sha256':hashlib.sha256(re.search(p,texts[k],re.M).group().encode()).hexdigest()}for p,k in SOURCE_DECLARATIONS.items()}
def generate_source(texts):
    validate_inputs(texts)
    declarations='\n'.join(re.search(p,texts[k],re.M).group()for p,k in SOURCE_DECLARATIONS.items())
    prototypes='\n'.join(function(texts[k],n).split('{',1)[0].strip()+';'for n,k in FUNCTION_SOURCES.items())
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return PREFIX.replace('SOURCE_DEFINITIONS',declarations).replace('FUNCTION_DECLARATIONS',prototypes)+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)
