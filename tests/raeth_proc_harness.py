"""RAETH proc owner model. Creation, subtree traversal and callback rundown are inert seams.

Actual init/exit and proc_remove bodies compile unchanged. The kernel subtree
implementation is source-only; this does not execute real procfs/RCU callbacks.
"""
import hashlib
import re
SOURCE_PATHS = {'proc': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/ra_dbg_proc.c',
 'generic': 'trunk/linux-4.4.x/fs/proc/generic.c',
 'reg': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raeth_reg.h',
 'config': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raeth_config.h'}
FUNCTION_SOURCES = {'debug_proc_init': 'proc', 'debug_proc_exit': 'proc', 'proc_remove': 'generic'}
BODY_ORDER = ('debug_proc_init', 'debug_proc_exit', 'proc_remove')
SOURCE_ONLY_FUNCTION_SOURCES = {'remove_proc_subtree': 'generic'}
MODEL_VARIANT = {'all_optional_diagnostics_enabled_variant': True,
 'minimal_and_rss_variants': True,
 'proc_kernel_subtree_source_only': True,
 'callback_rundown_is_inert': True,
 'external_raw_callers_not_modeled': True}
FIELDS = ('ret',
 'second_ret',
 'created',
 'removed',
 'live',
 'root_publications',
 'mkdir_calls',
 'create_calls',
 'subtree_calls',
 'stale_handles',
 'duplicate_remove',
 'drained')
BASELINE_COMMIT = 'c4d8e113ffba5f85eb5f37a75b3c5f23594ed193'
SOURCE_MACROS = {'PROCREG_DIR': '"mt7621"',
 'PROCREG_SKBFREE': '"skb_free"',
 'PROCREG_TXRING': '"tx_ring"',
 'PROCREG_RXRING': '"rx_ring"',
 'PROCREG_RXRING1': '"rx_ring1"',
 'PROCREG_RXRING2': '"rx_ring2"',
 'PROCREG_RXRING3': '"rx_ring3"',
 'PROCREG_NUM_OF_TXD': '"num_of_txd"',
 'PROCREG_TSO_LEN': '"tso_len"',
 'PROCREG_LRO_STATS': '"lro_stats"',
 'PROCREG_HW_LRO_STATS': '"hw_lro_stats"',
 'PROCREG_HW_LRO_AUTO_TLB': '"hw_lro_auto_tlb"',
 'PROCREG_HW_IO_COHERENT': '"hw_iocoherent"',
 'PROCREG_GMAC': '"gmac"',
 'PROCREG_GMAC2': '"gmac2"',
 'PROCREG_CP0': '"cp0"',
 'PROCREG_ESW_CNT': '"esw_cnt"',
 'PROCREG_ETH_CNT': '"eth_cnt"',
 'PROCREG_SNMP': '"snmp"',
 'PROCREG_SET_LAN_IP': '"set_lan_ip"',
 'PROCREG_SCHE': '"schedule"',
 'PROCREG_INT_DBG': '"int_dbg"'}
SOURCE_FEATURE_MACROS = {'FE_HW_LRO': 'BIT(1)',
 'FE_RSS_4RING': 'BIT(20)',
 'FE_RSS_2RING': 'BIT(2)',
 'FE_HW_IOCOHERENT': 'BIT(19)',
 'FE_ETHTOOL': 'BIT(10)',
 'FE_GE2_SUPPORT': 'BIT(9)',
 'FE_TSO': 'BIT(12)',
 'FE_SW_LRO': 'BIT(3)',
 'USER_SNMPD': 'BIT(23)',
 'TASKLET_WORKQUEUE_SW': 'BIT(24)',
 'FE_RAETH_INT_DBG': 'BIT(22)',
 'MT7622_FE': '(7622)',
 'LEOPARD_FE': '(1985)'}
PREFIX = ('\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <string.h>\n'
 '#define EBUSY 16\n'
 '#define ENOMEM 12\n'
 '#define BIT(n) (1U<<(n))\n'
 '#define S_IRUGO 0444\n'
 '#define pr_debug(...) ((void)0)\n'
 '#define pr_info(...) ((void)0)\n'
 '#define PROCREG_DIR "mt7621"\n'
 '#define PROCREG_SKBFREE "skb_free"\n'
 '#define PROCREG_TXRING "tx_ring"\n'
 '#define PROCREG_RXRING "rx_ring"\n'
 '#define PROCREG_RXRING1 "rx_ring1"\n'
 '#define PROCREG_RXRING2 "rx_ring2"\n'
 '#define PROCREG_RXRING3 "rx_ring3"\n'
 '#define PROCREG_NUM_OF_TXD "num_of_txd"\n'
 '#define PROCREG_TSO_LEN "tso_len"\n'
 '#define PROCREG_LRO_STATS "lro_stats"\n'
 '#define PROCREG_HW_LRO_STATS "hw_lro_stats"\n'
 '#define PROCREG_HW_LRO_AUTO_TLB "hw_lro_auto_tlb"\n'
 '#define PROCREG_HW_IO_COHERENT "hw_iocoherent"\n'
 '#define PROCREG_GMAC "gmac"\n'
 '#define PROCREG_GMAC2 "gmac2"\n'
 '#define PROCREG_CP0 "cp0"\n'
 '#define PROCREG_ESW_CNT "esw_cnt"\n'
 '#define PROCREG_ETH_CNT "eth_cnt"\n'
 '#define PROCREG_SNMP "snmp"\n'
 '#define PROCREG_SET_LAN_IP "set_lan_ip"\n'
 '#define PROCREG_SCHE "schedule"\n'
 '#define PROCREG_INT_DBG "int_dbg"\n'
 '#define FE_HW_LRO BIT(1)\n'
 '#define FE_RSS_4RING BIT(20)\n'
 '#define FE_RSS_2RING BIT(2)\n'
 '#define FE_HW_IOCOHERENT BIT(19)\n'
 '#define FE_ETHTOOL BIT(10)\n'
 '#define FE_GE2_SUPPORT BIT(9)\n'
 '#define FE_TSO BIT(12)\n'
 '#define FE_SW_LRO BIT(3)\n'
 '#define USER_SNMPD BIT(23)\n'
 '#define TASKLET_WORKQUEUE_SW BIT(24)\n'
 '#define FE_RAETH_INT_DBG BIT(22)\n'
 '#define MT7622_FE (7622)\n'
 '#define LEOPARD_FE (1985)\n'
 '\n'
 'struct proc_dir_entry {const char*name;struct proc_dir_entry*parent;int live;};\n'
 'struct END_DEVICE {unsigned features;int chip_name;};\n'
 'struct net_device {struct END_DEVICE local;};\n'
 'static struct net_device netdev,*dev_raether=&netdev;\n'
 'static struct proc_dir_entry '
 '*proc_reg_dir,*proc_gmac,*proc_gmac2,*proc_sys_cp0,*proc_tx_ring,*proc_rx_ring,*proc_skb_free,*proc_ra_snmp,*proc_num_of_txd,*proc_tso_len,*proc_lro_stats,*proc_sche,*proc_int_dbg,*proc_set_lan_ip,*proc_esw_cnt,*proc_eth_cnt;\n'
 'static const int '
 'gmac_fops,gmac2_fops,skb_free_fops,tx_ring_fops,rx_ring_fops,tso_txd_num_fops,tso_len_fops,lro_stats_fops,ra_snmp_seq_fops,switch_count_fops,eth_count_fops,schedule_sw_fops,int_dbg_sw_fops,set_lan_ip_fops;\n'
 'static struct proc_dir_entry entries[80];\n'
 'static int '
 'created,removed,root_publications,mkdir_calls,create_calls,subtree_calls,duplicate_remove,drained;\n'
 'static int fail_mkdir,fail_child,active_callbacks;\n'
 'static struct END_DEVICE*netdev_priv(struct net_device*d){if(!d)abort();return &d->local;}\n'
 'static struct proc_dir_entry*entry_create(const char*name,struct proc_dir_entry*parent){int '
 'i;if(created>=80)abort();for(i=0;i<created;i++){if(entries[i].live&&entries[i].parent==parent&&!strcmp(entries[i].name,name))return '
 'NULL;}entries[created].name=name;entries[created].parent=parent;entries[created].live=1;return '
 '&entries[created++];}\n'
 'static struct proc_dir_entry*proc_mkdir(const char*name,struct '
 'proc_dir_entry*parent){mkdir_calls++;if(fail_mkdir)return NULL;return '
 'entry_create(name,parent);}\n'
 'static struct proc_dir_entry*proc_create(const char*name,unsigned mode,struct '
 'proc_dir_entry*parent,const '
 'void*fops){(void)mode;(void)fops;create_calls++;if(fail_child==create_calls)return '
 'NULL;if(!parent)root_publications++;else if(!parent->live)abort();return '
 'entry_create(name,parent);}\n'
 'static void helper_create(struct proc_dir_entry*d,int '
 'kind){(void)proc_create(PROCREG_RXRING1,0,d,NULL);(void)proc_create(PROCREG_RXRING2,0,d,NULL);(void)proc_create(PROCREG_RXRING3,0,d,NULL);if(kind==5){(void)proc_create(PROCREG_HW_LRO_STATS,0,d,NULL);(void)proc_create(PROCREG_HW_LRO_AUTO_TLB,0,d,NULL);}}\n'
 '#define hwlro_debug_proc_init(d) helper_create(d,5)\n'
 '#define rss_debug_proc_init(d) helper_create(d,3)\n'
 '#define hwioc_debug_proc_init(d) ((void)proc_create(PROCREG_HW_IO_COHERENT,0,d,NULL))\n'
 '/* Old helper exits are inert name-based removals, only needed by old-body controls. */\n'
 'static void remove_proc_entry(const char*name,struct proc_dir_entry*parent){int '
 'i;for(i=0;i<created;i++){if(entries[i].live&&entries[i].parent==parent&&!strcmp(entries[i].name,name)){entries[i].live=0;removed++;return;}}duplicate_remove++;}\n'
 '#define hwlro_debug_proc_exit(d) do '
 '{remove_proc_entry(PROCREG_RXRING1,d);remove_proc_entry(PROCREG_RXRING2,d);remove_proc_entry(PROCREG_RXRING3,d);remove_proc_entry(PROCREG_HW_LRO_STATS,d);remove_proc_entry(PROCREG_HW_LRO_AUTO_TLB,d);}while(0)\n'
 '#define rss_debug_proc_exit(d) do '
 '{remove_proc_entry(PROCREG_RXRING1,d);remove_proc_entry(PROCREG_RXRING2,d);remove_proc_entry(PROCREG_RXRING3,d);}while(0)\n'
 '#define hwioc_debug_proc_exit(d) remove_proc_entry(PROCREG_HW_IO_COHERENT,d)\n'
 'static int remove_proc_subtree(const char*name,struct proc_dir_entry*parent){int '
 'i,j,root=-1;subtree_calls++;for(i=0;i<created;i++){if(entries[i].live&&entries[i].parent==parent&&!strcmp(entries[i].name,name)){root=i;break;}}if(root<0){duplicate_remove++;return '
 '-1;}for(i=0;i<created;i++){struct '
 'proc_dir_entry*p=&entries[i];for(j=0;p&&j<80;j++,p=p->parent){if(p==&entries[root]){if(entries[i].live){entries[i].live=0;removed++;}break;}}}drained+=active_callbacks;active_callbacks=0;return '
 '0;}\n'
 'void proc_remove(struct proc_dir_entry*de);\n')
SUFFIX = ('\n'
 'static int handle_count(void){return '
 '!!proc_reg_dir+!!proc_gmac+!!proc_gmac2+!!proc_sys_cp0+!!proc_tx_ring+!!proc_rx_ring+!!proc_skb_free+!!proc_ra_snmp+!!proc_num_of_txd+!!proc_tso_len+!!proc_lro_stats+!!proc_sche+!!proc_int_dbg+!!proc_set_lan_ip+!!proc_esw_cnt+!!proc_eth_cnt;}\n'
 'int main(int argc,char**argv){const char*name;int ret=0,next=0,i,live=0;if(argc!=2){return '
 '2;}name=argv[1];CASE_ADMISSION\n'
 ' (void)remove_proc_entry;\n'
 ' '
 'netdev.local.features=FE_HW_LRO|FE_HW_IOCOHERENT|FE_ETHTOOL|FE_TSO|FE_SW_LRO|USER_SNMPD|TASKLET_WORKQUEUE_SW|FE_RAETH_INT_DBG;\n'
 ' netdev.local.chip_name=MT7622_FE;\n'
 ' if(!strcmp(name,"directory-oom"))fail_mkdir=1;\n'
 ' if(!strncmp(name,"child-oom-",10))fail_child=atoi(name+10);\n'
 ' if(!strcmp(name,"minimal")){netdev.local.features=0;netdev.local.chip_name=7621;}\n'
 ' '
 'if(!strcmp(name,"rss")){netdev.local.features&=~FE_HW_LRO;netdev.local.features|=FE_RSS_4RING;}\n'
 ' ret=debug_proc_init();\n'
 ' if(!strcmp(name,"duplicate-init"))next=debug_proc_init();\n'
 ' if(!strcmp(name,"active-callbacks"))active_callbacks=3;\n'
 ' debug_proc_exit();\n'
 ' if(!strcmp(name,"repeat-exit"))debug_proc_exit();\n'
 ' if(!strcmp(name,"retry")){fail_child=0;next=debug_proc_init();debug_proc_exit();}\n'
 ' '
 'if(!strcmp(name,"profile-change")){netdev.local.features=0;netdev.local.chip_name=7621;next=debug_proc_init();debug_proc_exit();}\n'
 ' for(i=0;i<created;i++)live+=entries[i].live;\n'
 ' '
 'printf("{\\"ret\\":%d,\\"second_ret\\":%d,\\"created\\":%d,\\"removed\\":%d,\\"live\\":%d,\\"root_publications\\":%d,\\"mkdir_calls\\":%d,\\"create_calls\\":%d,\\"subtree_calls\\":%d,\\"stale_handles\\":%d,\\"duplicate_remove\\":%d,\\"drained\\":%d}\\n",ret,next,created,removed,live,root_publications,mkdir_calls,create_calls,subtree_calls,handle_count(),duplicate_remove,drained);return '
 '0;}\n')
CASE_NAMES = ('full',
 'minimal',
 'rss',
 'directory-oom',
 'duplicate-init',
 'repeat-exit',
 'retry',
 'profile-change',
 'active-callbacks',
 'child-oom-1',
 'child-oom-2',
 'child-oom-3',
 'child-oom-4',
 'child-oom-5',
 'child-oom-6',
 'child-oom-7',
 'child-oom-8',
 'child-oom-9',
 'child-oom-10',
 'child-oom-11',
 'child-oom-12',
 'child-oom-13',
 'child-oom-14',
 'child-oom-15',
 'child-oom-16',
 'child-oom-17',
 'child-oom-18',
 'child-oom-19',
 'child-oom-20')
EXPECTED_ROWS = {'full': {'ret': 0,
          'second_ret': 0,
          'created': 21,
          'removed': 21,
          'live': 0,
          'root_publications': 0,
          'mkdir_calls': 1,
          'create_calls': 20,
          'subtree_calls': 1,
          'stale_handles': 0,
          'duplicate_remove': 0,
          'drained': 0},
 'minimal': {'ret': 0,
             'second_ret': 0,
             'created': 7,
             'removed': 7,
             'live': 0,
             'root_publications': 0,
             'mkdir_calls': 1,
             'create_calls': 6,
             'subtree_calls': 1,
             'stale_handles': 0,
             'duplicate_remove': 0,
             'drained': 0},
 'rss': {'ret': 0,
         'second_ret': 0,
         'created': 19,
         'removed': 19,
         'live': 0,
         'root_publications': 0,
         'mkdir_calls': 1,
         'create_calls': 18,
         'subtree_calls': 1,
         'stale_handles': 0,
         'duplicate_remove': 0,
         'drained': 0},
 'directory-oom': {'ret': -12,
                   'second_ret': 0,
                   'created': 0,
                   'removed': 0,
                   'live': 0,
                   'root_publications': 0,
                   'mkdir_calls': 1,
                   'create_calls': 0,
                   'subtree_calls': 0,
                   'stale_handles': 0,
                   'duplicate_remove': 0,
                   'drained': 0},
 'duplicate-init': {'ret': 0,
                    'second_ret': -16,
                    'created': 21,
                    'removed': 21,
                    'live': 0,
                    'root_publications': 0,
                    'mkdir_calls': 1,
                    'create_calls': 20,
                    'subtree_calls': 1,
                    'stale_handles': 0,
                    'duplicate_remove': 0,
                    'drained': 0},
 'repeat-exit': {'ret': 0,
                 'second_ret': 0,
                 'created': 21,
                 'removed': 21,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'retry': {'ret': 0,
           'second_ret': 0,
           'created': 42,
           'removed': 42,
           'live': 0,
           'root_publications': 0,
           'mkdir_calls': 2,
           'create_calls': 40,
           'subtree_calls': 2,
           'stale_handles': 0,
           'duplicate_remove': 0,
           'drained': 0},
 'profile-change': {'ret': 0,
                    'second_ret': 0,
                    'created': 28,
                    'removed': 28,
                    'live': 0,
                    'root_publications': 0,
                    'mkdir_calls': 2,
                    'create_calls': 26,
                    'subtree_calls': 2,
                    'stale_handles': 0,
                    'duplicate_remove': 0,
                    'drained': 0},
 'active-callbacks': {'ret': 0,
                      'second_ret': 0,
                      'created': 21,
                      'removed': 21,
                      'live': 0,
                      'root_publications': 0,
                      'mkdir_calls': 1,
                      'create_calls': 20,
                      'subtree_calls': 1,
                      'stale_handles': 0,
                      'duplicate_remove': 0,
                      'drained': 3},
 'child-oom-1': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-2': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-3': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-4': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-5': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-6': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-7': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-8': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-9': {'ret': 0,
                 'second_ret': 0,
                 'created': 20,
                 'removed': 20,
                 'live': 0,
                 'root_publications': 0,
                 'mkdir_calls': 1,
                 'create_calls': 20,
                 'subtree_calls': 1,
                 'stale_handles': 0,
                 'duplicate_remove': 0,
                 'drained': 0},
 'child-oom-10': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-11': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-12': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-13': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-14': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-15': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-16': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-17': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-18': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-19': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0},
 'child-oom-20': {'ret': 0,
                  'second_ret': 0,
                  'created': 20,
                  'removed': 20,
                  'live': 0,
                  'root_publications': 0,
                  'mkdir_calls': 1,
                  'create_calls': 20,
                  'subtree_calls': 1,
                  'stale_handles': 0,
                  'duplicate_remove': 0,
                  'drained': 0}}
BASELINE_FUNCTIONS = {'debug_proc_init': 'int debug_proc_init(void)\n'
                    '{\n'
                    '\tstruct END_DEVICE *ei_local = netdev_priv(dev_raether);\n'
                    '\n'
                    '\tif (!proc_reg_dir)\n'
                    '\t\tproc_reg_dir = proc_mkdir(PROCREG_DIR, NULL);\n'
                    '\n'
                    '\tif (ei_local->features & FE_HW_LRO)\n'
                    '\t\thwlro_debug_proc_init(proc_reg_dir);\n'
                    '\telse if (ei_local->features & (FE_RSS_4RING | FE_RSS_2RING))\n'
                    '\t\trss_debug_proc_init(proc_reg_dir);\n'
                    '\n'
                    '\tif (ei_local->features & FE_HW_IOCOHERENT)\n'
                    '\t\thwioc_debug_proc_init(proc_reg_dir);\n'
                    '\tproc_gmac = proc_create(PROCREG_GMAC, 0, proc_reg_dir, &gmac_fops);\n'
                    '\tif (!proc_gmac)\n'
                    '\t\tpr_debug("!! FAIL to create %s PROC !!\\n", PROCREG_GMAC);\n'
                    '\n'
                    '\tif (ei_local->features & (FE_ETHTOOL | FE_GE2_SUPPORT)) {\n'
                    '\t\tproc_gmac2 =\n'
                    '\t\t    proc_create(PROCREG_GMAC2, 0, proc_reg_dir, &gmac2_fops);\n'
                    '\t\tif (!proc_gmac2)\n'
                    '\t\t\tpr_debug("!! FAIL to create %s PROC !!\\n",\n'
                    '\t\t\t\t PROCREG_GMAC2);\n'
                    '\t}\n'
                    '\tproc_skb_free =\n'
                    '\t    proc_create(PROCREG_SKBFREE, 0, proc_reg_dir, &skb_free_fops);\n'
                    '\tif (!proc_skb_free)\n'
                    '\t\tpr_debug("!! FAIL to create %s PROC !!\\n", PROCREG_SKBFREE);\n'
                    '\tproc_tx_ring = proc_create(PROCREG_TXRING, 0, proc_reg_dir,\n'
                    '\t\t\t\t   &tx_ring_fops);\n'
                    '\tif (!proc_tx_ring)\n'
                    '\t\tpr_debug("!! FAIL to create %s PROC !!\\n", PROCREG_TXRING);\n'
                    '\tproc_rx_ring = proc_create(PROCREG_RXRING, 0,\n'
                    '\t\t\t\t   proc_reg_dir, &rx_ring_fops);\n'
                    '\tif (!proc_rx_ring)\n'
                    '\t\tpr_debug("!! FAIL to create %s PROC !!\\n", PROCREG_RXRING);\n'
                    '\n'
                    '\tif (ei_local->features & FE_TSO) {\n'
                    '\t\tproc_num_of_txd =\n'
                    '\t\t    proc_create(PROCREG_NUM_OF_TXD, 0, proc_reg_dir,\n'
                    '\t\t\t\t&tso_txd_num_fops);\n'
                    '\t\tif (!proc_num_of_txd)\n'
                    '\t\t\tpr_debug("!! FAIL to create %s PROC !!\\n",\n'
                    '\t\t\t\t PROCREG_NUM_OF_TXD);\n'
                    '\t\tproc_tso_len =\n'
                    '\t\t    proc_create(PROCREG_TSO_LEN, 0, proc_reg_dir,\n'
                    '\t\t\t\t&tso_len_fops);\n'
                    '\t\tif (!proc_tso_len)\n'
                    '\t\t\tpr_debug("!! FAIL to create %s PROC !!\\n",\n'
                    '\t\t\t\t PROCREG_TSO_LEN);\n'
                    '\t}\n'
                    '\n'
                    '\tif (ei_local->features & FE_SW_LRO) {\n'
                    '\t\tproc_lro_stats =\n'
                    '\t\t    proc_create(PROCREG_LRO_STATS, 0, proc_reg_dir,\n'
                    '\t\t\t\t&lro_stats_fops);\n'
                    '\t\tif (!proc_lro_stats)\n'
                    '\t\t\tpr_debug("!! FAIL to create %s PROC !!\\n",\n'
                    '\t\t\t\t PROCREG_LRO_STATS);\n'
                    '\t}\n'
                    '\n'
                    '\tif (ei_local->features & USER_SNMPD) {\n'
                    '\t\tproc_ra_snmp =\n'
                    '\t\t    proc_create(PROCREG_SNMP, S_IRUGO, proc_reg_dir,\n'
                    '\t\t\t\t&ra_snmp_seq_fops);\n'
                    '\t\tif (!proc_ra_snmp)\n'
                    '\t\t\tpr_debug("!! FAIL to create %s PROC !!\\n",\n'
                    '\t\t\t\t PROCREG_SNMP);\n'
                    '\t}\n'
                    '\tproc_esw_cnt =\n'
                    '\t    proc_create(PROCREG_ESW_CNT, 0, proc_reg_dir, &switch_count_fops);\n'
                    '\tif (!proc_esw_cnt)\n'
                    '\t\tpr_debug("!! FAIL to create %s PROC !!\\n", PROCREG_ESW_CNT);\n'
                    '\n'
                    '\tif (ei_local->chip_name == MT7622_FE || ei_local->chip_name == LEOPARD_FE) '
                    '{\n'
                    '\t\tproc_eth_cnt =\n'
                    '\t\t\tproc_create(PROCREG_ETH_CNT, 0, proc_reg_dir, &eth_count_fops);\n'
                    '\t\tif (!proc_eth_cnt)\n'
                    '\t\t\tpr_debug("!! FAIL to create %s PROC !!\\n", PROCREG_ETH_CNT);\n'
                    '\t}\n'
                    '\n'
                    '\tif (ei_local->features & TASKLET_WORKQUEUE_SW) {\n'
                    '\t\tproc_sche =\n'
                    '\t\t    proc_create(PROCREG_SCHE, 0, proc_reg_dir,\n'
                    '\t\t\t\t&schedule_sw_fops);\n'
                    '\t\tif (!proc_sche)\n'
                    '\t\t\tpr_debug("!! FAIL to create %s PROC !!\\n",\n'
                    '\t\t\t\t PROCREG_SCHE);\n'
                    '\t}\n'
                    '\n'
                    '\tif (ei_local->features & FE_RAETH_INT_DBG) {\n'
                    '\t\tproc_int_dbg =\n'
                    '\t\t    proc_create(PROCREG_INT_DBG, 0, proc_reg_dir,\n'
                    '\t\t\t\t&int_dbg_sw_fops);\n'
                    '\t\tif (!proc_int_dbg)\n'
                    '\t\t\tpr_debug("!! FAIL to create %s PROC !!\\n",\n'
                    '\t\t\t\t PROCREG_INT_DBG);\n'
                    '\t}\n'
                    '\n'
                    '\t/* Set LAN IP address */\n'
                    '\tproc_set_lan_ip =\n'
                    '\t    proc_create(PROCREG_SET_LAN_IP, 0, proc_reg_dir, &set_lan_ip_fops);\n'
                    '\tif (!proc_set_lan_ip)\n'
                    '\t\tpr_debug("!! FAIL to create %s PROC !!\\n", PROCREG_SET_LAN_IP);\n'
                    '\n'
                    '\tpr_debug("PROC INIT OK!\\n");\n'
                    '\treturn 0;\n'
                    '}',
 'debug_proc_exit': 'void debug_proc_exit(void)\n'
                    '{\n'
                    '\tstruct END_DEVICE *ei_local = netdev_priv(dev_raether);\n'
                    '\n'
                    '\tif (ei_local->features & FE_HW_LRO)\n'
                    '\t\thwlro_debug_proc_exit(proc_reg_dir);\n'
                    '\telse if (ei_local->features & (FE_RSS_4RING | FE_RSS_2RING))\n'
                    '\t\trss_debug_proc_exit(proc_reg_dir);\n'
                    '\n'
                    '\tif (ei_local->features & FE_HW_IOCOHERENT)\n'
                    '\t\thwioc_debug_proc_exit(proc_reg_dir);\n'
                    '\n'
                    '\tif (proc_sys_cp0)\n'
                    '\t\tremove_proc_entry(PROCREG_CP0, proc_reg_dir);\n'
                    '\n'
                    '\tif (proc_gmac)\n'
                    '\t\tremove_proc_entry(PROCREG_GMAC, proc_reg_dir);\n'
                    '\n'
                    '\tif (ei_local->features & (FE_ETHTOOL | FE_GE2_SUPPORT)) {\n'
                    '\t\tif (proc_gmac)\n'
                    '\t\t\tremove_proc_entry(PROCREG_GMAC, proc_reg_dir);\n'
                    '\t}\n'
                    '\n'
                    '\tif (proc_skb_free)\n'
                    '\t\tremove_proc_entry(PROCREG_SKBFREE, proc_reg_dir);\n'
                    '\n'
                    '\tif (proc_tx_ring)\n'
                    '\t\tremove_proc_entry(PROCREG_TXRING, proc_reg_dir);\n'
                    '\n'
                    '\tif (proc_rx_ring)\n'
                    '\t\tremove_proc_entry(PROCREG_RXRING, proc_reg_dir);\n'
                    '\n'
                    '\tif (ei_local->features & FE_TSO) {\n'
                    '\t\tif (proc_num_of_txd)\n'
                    '\t\t\tremove_proc_entry(PROCREG_NUM_OF_TXD, proc_reg_dir);\n'
                    '\n'
                    '\t\tif (proc_tso_len)\n'
                    '\t\t\tremove_proc_entry(PROCREG_TSO_LEN, proc_reg_dir);\n'
                    '\t}\n'
                    '\n'
                    '\tif (ei_local->features & FE_SW_LRO) {\n'
                    '\t\tif (proc_lro_stats)\n'
                    '\t\t\tremove_proc_entry(PROCREG_LRO_STATS, proc_reg_dir);\n'
                    '\t}\n'
                    '\n'
                    '\tif (ei_local->features & USER_SNMPD) {\n'
                    '\t\tif (proc_ra_snmp)\n'
                    '\t\t\tremove_proc_entry(PROCREG_SNMP, proc_reg_dir);\n'
                    '\t}\n'
                    '\n'
                    '\tif (proc_esw_cnt)\n'
                    '\t\tremove_proc_entry(PROCREG_ESW_CNT, proc_reg_dir);\n'
                    '\n'
                    '\tif (ei_local->chip_name == MT7622_FE || ei_local->chip_name == LEOPARD_FE) '
                    '{\n'
                    '\t\tif (proc_eth_cnt)\n'
                    '\t\t\tremove_proc_entry(PROCREG_ETH_CNT, proc_reg_dir);\n'
                    '\t}\n'
                    '\n'
                    '\t/* if (proc_reg_dir) */\n'
                    '\t/* remove_proc_entry(PROCREG_DIR, 0); */\n'
                    '\n'
                    '\tpr_debug("proc exit\\n");\n'
                    '}'}
BASELINE_SHA256 = {'debug_proc_init': '5af43a62467daa062d11f4f45bed5a572befac6f3e5dde0c629f0c6acc66f3cd',
 'debug_proc_exit': '89691743f8bfad3e5a75d51481677e18bf7665412a3d831161a3452f45439834'}

def function(text, name):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked = re.sub(tokens, lambda m: ' ' * len(m.group()), text)
    matches = list(re.finditer(r'(?:static\s+)?(?:inline\s+)?(?:int|void)\s+\b'
                              + re.escape(name) + r'\s*\([^;{}]*\)\s*\{', masked))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous NOR admission body: ' + name)
    start = matches[0].start()
    opening = masked.index('{', start)
    depth = 0
    for match in re.finditer('[{}]', masked[opening:]):
        depth += 1 if match.group() == '{' else -1
        if depth == 0:
            return text[start:opening + match.end()]
    raise ValueError('Unterminated NOR admission body: ' + name)



def validate_inputs(texts):
    if set(texts) != set(SOURCE_PATHS): raise ValueError('Exact proc fixture inputs required')
    for name,value in SOURCE_MACROS.items():
        values=re.findall(r'^#define[ \t]+'+re.escape(name)+r'[ \t]+([^\n]+)',texts['reg'],re.M)
        if name=='PROCREG_DIR':
            if value not in [v.strip()for v in values]: raise ValueError('Proc directory changed')
        elif len(values)!=1 or values[0].strip()!=value: raise ValueError('Proc name changed: '+name)
    for name,value in SOURCE_FEATURE_MACROS.items():
        values=re.findall(r'^#define[ \t]+'+re.escape(name)+r'[ \t]+([^\n]+)',texts['config'],re.M)
        if value not in [v.strip()for v in values]: raise ValueError('Proc model feature changed: '+name)
    for name,key in dict(FUNCTION_SOURCES,**SOURCE_ONLY_FUNCTION_SOURCES).items():function(texts[key],name)

def function_manifest(texts):
    validate_inputs(texts)
    return {name:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}for name,key in FUNCTION_SOURCES.items()}

def source_only_manifest(texts):
    validate_inputs(texts)
    return {name:{'source':key,'execution':'source-only-not-run','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()}for name,key in SOURCE_ONLY_FUNCTION_SOURCES.items()}

def generate_source(texts,baseline=False):
    validate_inputs(texts)
    bodies={name:function(texts[key],name)for name,key in FUNCTION_SOURCES.items()}
    if baseline:bodies.update(BASELINE_FUNCTIONS)
    admission='if ('+' && '.join('strcmp(name,"'+n+'")'for n in CASE_NAMES)+') return 2;'
    return PREFIX+'\n'+'\n'.join(bodies[n]for n in BODY_ORDER)+'\n'+SUFFIX.replace('CASE_ADMISSION',admission)
