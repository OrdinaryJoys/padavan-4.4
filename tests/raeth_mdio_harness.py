"""Complete MDIO transaction bodies; MMIO/IRQ/time seams are inert, selected schedules use pthread locks."""
import hashlib
import re
SOURCE_PATHS = {'mdio': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mii_mgr.c',
 'ethtool': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/ra_ethtool.c',
 'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
 'header': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.h',
 'config': 'trunk/configs/boards/K2P/kernel-4.4.x.config'}
FUNCTION_SOURCES = {'mii_mgr_attach': 'mdio',
 'mii_mgr_detach': 'mdio',
 'raeth_mdio_lock': 'mdio',
 'raeth_mdio_wait': 'mdio',
 'raeth_mdio_xfer': 'mdio',
 'raeth_mdio_unlock': 'mdio',
 'set_an_polling': 'mdio',
 'mii_mgr_read': 'mdio',
 'mii_mgr_write': 'mdio',
 'mii_mgr_cl45_set_address': 'mdio',
 'mii_mgr_read_cl45': 'mdio',
 'mii_mgr_write_cl45': 'mdio',
 'get_current_phy_address': 'ethtool',
 'mdio_read': 'ethtool',
 'mdio_virt_read': 'ethtool'}
BODY_ORDER = ('mii_mgr_attach',
 'mii_mgr_detach',
 'raeth_mdio_lock',
 'raeth_mdio_wait',
 'raeth_mdio_xfer',
 'raeth_mdio_unlock',
 'set_an_polling',
 'mii_mgr_read',
 'mii_mgr_write',
 'mii_mgr_cl45_set_address',
 'mii_mgr_read_cl45',
 'mii_mgr_write_cl45',
 'get_current_phy_address',
 'mdio_read',
 'mdio_virt_read')
SOURCE_ONLY_FUNCTION_SOURCES = {'rather_probe': 'raeth', 'raether_remove': 'raeth'}
MODEL_VARIANT = {'K2P_MT7621_single_controller': True,
 'frozen_jiffies': True,
 'controller_reads_and_delays_inert': True,
 'selected_pthread_schedules_not_full_kernel_concurrency': True,
 'ethtool_wrapper_forced_model_not_shipping_K2P_CONFIG_RAETH_ETHTOOL': True,
 'ten_ms_busy_poll_budget_not_MMIO_latency_proof': True,
 'exact_controller_command_words_and_initial_busy_write_order': True,
 'logical_feature_bit_values_not_hardware_layout': True}
CASE_NAMES = ('read',
 'write',
 'initial-busy',
 'read-timeout',
 'switch-read',
 'switch-write',
 'switch-fail-1',
 'switch-fail-2',
 'switch-fail-3',
 'switch-shared-budget',
 'cl45-read',
 'cl45-write',
 'cl45-set',
 'cl45-address-failure',
 'cl45-data-failure',
 'cl45-invalid-dev',
 'cl45-invalid-reg',
 'cl45-invalid-value',
 'invalid-phy',
 'invalid-reg',
 'invalid-value',
 'null-read',
 'switch-unaligned',
 'switch-outside',
 'absent',
 'detached',
 'wrapper-read',
 'wrapper-failure',
 'wrapper-virt',
 'phy-ref',
 'phy-absent',
 'concurrent-switch',
 'detach-joins',
 'cl45-late-address')
EXPECTED_ROWS = {'read': {'ret': 1,
          'value': 4630,
          'commands': 1,
          'delay_us': 0,
          'lock_errors': 0,
          'logs': 0,
          'polling': 2147483657,
          'refs': 0,
          'puts': 0,
          'after_free': 0,
          'controller_writes': [68747264, 2216230912]},
 'write': {'ret': 1,
           'value': 3735928559,
           'commands': 1,
           'delay_us': 0,
           'lock_errors': 0,
           'logs': 0,
           'polling': 2147483657,
           'refs': 0,
           'puts': 0,
           'after_free': 0,
           'controller_writes': [68502887, 2215986535]},
 'initial-busy': {'ret': 0,
                  'value': 3735928559,
                  'commands': 0,
                  'delay_us': 10000,
                  'lock_errors': 0,
                  'logs': 1,
                  'polling': 2147483657,
                  'refs': 0,
                  'puts': 0,
                  'after_free': 0,
                  'controller_writes': []},
 'read-timeout': {'ret': 0,
                  'value': 3735928559,
                  'commands': 1,
                  'delay_us': 10000,
                  'lock_errors': 0,
                  'logs': 1,
                  'polling': 2147483657,
                  'refs': 0,
                  'puts': 0,
                  'after_free': 0,
                  'controller_writes': [68747264, 2216230912]},
 'switch-read': {'ret': 1,
                 'value': 1450775076,
                 'commands': 3,
                 'delay_us': 0,
                 'lock_errors': 0,
                 'logs': 0,
                 'polling': 2147483657,
                 'refs': 0,
                 'puts': 0,
                 'after_free': 0,
                 'controller_writes': [1073020929, 3220504577, 33095680, 2180579328, 569966592, 2717450240]},
 'switch-write': {'ret': 1,
                  'value': 3735928559,
                  'commands': 3,
                  'delay_us': 0,
                  'lock_errors': 0,
                  'logs': 0,
                  'polling': 2147483657,
                  'refs': 0,
                  'puts': 0,
                  'after_free': 0,
                  'controller_writes': [1073020929, 3220504577, 32855672, 2180339320, 569709108, 2717192756]},
 'switch-fail-1': {'ret': 0,
                   'value': 3735928559,
                   'commands': 1,
                   'delay_us': 10000,
                   'lock_errors': 0,
                   'logs': 1,
                   'polling': 2147483657,
                   'refs': 0,
                   'puts': 0,
                   'after_free': 0,
                   'controller_writes': [1073020929, 3220504577]},
 'switch-fail-2': {'ret': 0,
                   'value': 3735928559,
                   'commands': 2,
                   'delay_us': 10000,
                   'lock_errors': 0,
                   'logs': 1,
                   'polling': 2147483657,
                   'refs': 0,
                   'puts': 0,
                   'after_free': 0,
                   'controller_writes': [1073020929, 3220504577, 33095680, 2180579328]},
 'switch-fail-3': {'ret': 0,
                   'value': 3735928559,
                   'commands': 3,
                   'delay_us': 10000,
                   'lock_errors': 0,
                   'logs': 1,
                   'polling': 2147483657,
                   'refs': 0,
                   'puts': 0,
                   'after_free': 0,
                   'controller_writes': [1073020929,
                                         3220504577,
                                         33095680,
                                         2180579328,
                                         569966592,
                                         2717450240]},
 'switch-shared-budget': {'ret': 0,
                          'value': 3735928559,
                          'commands': 3,
                          'delay_us': 10000,
                          'lock_errors': 0,
                          'logs': 1,
                          'polling': 2147483657,
                          'refs': 0,
                          'puts': 0,
                          'after_free': 0,
                          'controller_writes': [1073020929,
                                                3220504577,
                                                33095680,
                                                2180579328,
                                                569966592,
                                                2717450240]},
 'cl45-read': {'ret': 1,
               'value': 4151,
               'commands': 2,
               'delay_us': 0,
               'lock_errors': 0,
               'logs': 0,
               'polling': 2147483657,
               'refs': 0,
               'puts': 0,
               'after_free': 0,
               'controller_writes': [102765108, 2250248756, 103546880, 2251030528]},
 'cl45-write': {'ret': 1,
                'value': 3735928559,
                'commands': 2,
                'delay_us': 0,
                'lock_errors': 0,
                'logs': 0,
                'polling': 2147483657,
                'refs': 0,
                'puts': 0,
                'after_free': 0,
                'controller_writes': [102765108, 2250248756, 103053466, 2250537114]},
 'cl45-set': {'ret': 1,
              'value': 3735928559,
              'commands': 1,
              'delay_us': 0,
              'lock_errors': 0,
              'logs': 0,
              'polling': 2147483657,
              'refs': 0,
              'puts': 0,
              'after_free': 0,
              'controller_writes': [102765108, 2250248756]},
 'cl45-address-failure': {'ret': 0,
                          'value': 3735928559,
                          'commands': 1,
                          'delay_us': 10000,
                          'lock_errors': 0,
                          'logs': 1,
                          'polling': 2147483657,
                          'refs': 0,
                          'puts': 0,
                          'after_free': 0,
                          'controller_writes': [102765108, 2250248756]},
 'cl45-data-failure': {'ret': 0,
                       'value': 3735928559,
                       'commands': 2,
                       'delay_us': 10000,
                       'lock_errors': 0,
                       'logs': 1,
                       'polling': 2147483657,
                       'refs': 0,
                       'puts': 0,
                       'after_free': 0,
                       'controller_writes': [102765108, 2250248756, 103546880, 2251030528]},
 'cl45-invalid-dev': {'ret': 0,
                      'value': 3735928559,
                      'commands': 0,
                      'delay_us': 0,
                      'lock_errors': 0,
                      'logs': 0,
                      'polling': 2147483657,
                      'refs': 0,
                      'puts': 0,
                      'after_free': 0,
                      'controller_writes': []},
 'cl45-invalid-reg': {'ret': 0,
                      'value': 3735928559,
                      'commands': 0,
                      'delay_us': 0,
                      'lock_errors': 0,
                      'logs': 0,
                      'polling': 2147483657,
                      'refs': 0,
                      'puts': 0,
                      'after_free': 0,
                      'controller_writes': []},
 'cl45-invalid-value': {'ret': 0,
                        'value': 3735928559,
                        'commands': 0,
                        'delay_us': 0,
                        'lock_errors': 0,
                        'logs': 0,
                        'polling': 2147483657,
                        'refs': 0,
                        'puts': 0,
                        'after_free': 0,
                        'controller_writes': []},
 'invalid-phy': {'ret': 0,
                 'value': 3735928559,
                 'commands': 0,
                 'delay_us': 0,
                 'lock_errors': 0,
                 'logs': 0,
                 'polling': 2147483657,
                 'refs': 0,
                 'puts': 0,
                 'after_free': 0,
                 'controller_writes': []},
 'invalid-reg': {'ret': 0,
                 'value': 3735928559,
                 'commands': 0,
                 'delay_us': 0,
                 'lock_errors': 0,
                 'logs': 0,
                 'polling': 2147483657,
                 'refs': 0,
                 'puts': 0,
                 'after_free': 0,
                 'controller_writes': []},
 'invalid-value': {'ret': 0,
                   'value': 3735928559,
                   'commands': 0,
                   'delay_us': 0,
                   'lock_errors': 0,
                   'logs': 0,
                   'polling': 2147483657,
                   'refs': 0,
                   'puts': 0,
                   'after_free': 0,
                   'controller_writes': []},
 'null-read': {'ret': 0,
               'value': 3735928559,
               'commands': 0,
               'delay_us': 0,
               'lock_errors': 0,
               'logs': 0,
               'polling': 2147483657,
               'refs': 0,
               'puts': 0,
               'after_free': 0,
               'controller_writes': []},
 'switch-unaligned': {'ret': 0,
                      'value': 3735928559,
                      'commands': 0,
                      'delay_us': 0,
                      'lock_errors': 0,
                      'logs': 0,
                      'polling': 2147483657,
                      'refs': 0,
                      'puts': 0,
                      'after_free': 0,
                      'controller_writes': []},
 'switch-outside': {'ret': 0,
                    'value': 3735928559,
                    'commands': 0,
                    'delay_us': 0,
                    'lock_errors': 0,
                    'logs': 0,
                    'polling': 2147483657,
                    'refs': 0,
                    'puts': 0,
                    'after_free': 0,
                    'controller_writes': []},
 'absent': {'ret': 0,
            'value': 3735928559,
            'commands': 0,
            'delay_us': 0,
            'lock_errors': 0,
            'logs': 0,
            'polling': 2147483657,
            'refs': 0,
            'puts': 0,
            'after_free': 0,
            'controller_writes': []},
 'detached': {'ret': 0,
              'value': 3735928559,
              'commands': 0,
              'delay_us': 0,
              'lock_errors': 0,
              'logs': 0,
              'polling': 2147483657,
              'refs': 0,
              'puts': 0,
              'after_free': 0,
              'controller_writes': []},
 'wrapper-read': {'ret': 4630,
                  'value': 4630,
                  'commands': 1,
                  'delay_us': 0,
                  'lock_errors': 0,
                  'logs': 0,
                  'polling': 2147483657,
                  'refs': 0,
                  'puts': 0,
                  'after_free': 0,
                  'controller_writes': [68747264, 2216230912]},
 'wrapper-failure': {'ret': 0,
                     'value': 0,
                     'commands': 0,
                     'delay_us': 10000,
                     'lock_errors': 0,
                     'logs': 1,
                     'polling': 2147483657,
                     'refs': 0,
                     'puts': 0,
                     'after_free': 0,
                     'controller_writes': []},
 'wrapper-virt': {'ret': 4598,
                  'value': 4598,
                  'commands': 1,
                  'delay_us': 0,
                  'lock_errors': 0,
                  'logs': 0,
                  'polling': 2147483657,
                  'refs': 0,
                  'puts': 0,
                  'after_free': 0,
                  'controller_writes': [99155968, 2246639616]},
 'phy-ref': {'ret': 1,
             'value': 1,
             'commands': 0,
             'delay_us': 0,
             'lock_errors': 0,
             'logs': 0,
             'polling': 2147483657,
             'refs': 0,
             'puts': 1,
             'after_free': 0,
             'controller_writes': []},
 'phy-absent': {'ret': 0,
                'value': 0,
                'commands': 0,
                'delay_us': 0,
                'lock_errors': 0,
                'logs': 0,
                'polling': 2147483657,
                'refs': 0,
                'puts': 0,
                'after_free': 0,
                'controller_writes': []},
 'concurrent-switch': {'ret': 1,
                       'value': 1450775076,
                       'commands': 6,
                       'delay_us': 0,
                       'lock_errors': 0,
                       'logs': 0,
                       'polling': 2147483657,
                       'refs': 0,
                       'puts': 0,
                       'after_free': 0,
                       'controller_writes': [1073020929,
                                             3220504577,
                                             33095680,
                                             2180579328,
                                             569966592,
                                             2717450240,
                                             1073020930,
                                             3220504578,
                                             33095680,
                                             2180579328,
                                             569966592,
                                             2717450240]},
 'detach-joins': {'ret': 0,
                  'value': 3735928559,
                  'commands': 3,
                  'delay_us': 0,
                  'lock_errors': 0,
                  'logs': 0,
                  'polling': 2147483657,
                  'refs': 0,
                  'puts': 0,
                  'after_free': 0,
                  'controller_writes': [1073020929, 3220504577, 33095680, 2180579328, 569966592, 2717450240]},
 'cl45-late-address': {'ret': 0,
                       'value': 3735928559,
                       'commands': 1,
                       'delay_us': 10000,
                       'lock_errors': 0,
                       'logs': 1,
                       'polling': 2147483657,
                       'refs': 0,
                       'puts': 0,
                       'after_free': 0,
                       'controller_writes': [102765108, 2250248756]}}
PREFIX = ('\n'
 '#include <stdint.h>\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <string.h>\n'
 '#include <pthread.h>\n'
 '#include <sched.h>\n'
 '#include <assert.h>\n'
 'typedef uint32_t u32;\n'
 'typedef int bool;\n'
 '#define true 1\n'
 '#define false 0\n'
 '#define BIT(n) (1U<<(n))\n'
 '#define GE1_RGMII_FORCE_1000 1\n'
 '#define GE1_TRGMII_FORCE_2000 2\n'
 '#define GE1_TRGMII_FORCE_2600 4\n'
 '#define FE_GE2_SUPPORT 8\n'
 '#define ESW_PHY_POLLING 1\n'
 '#define MDIO_PHY_CONTROL_0 2\n'
 '#define RAETH_MDIO_POLL_US 10\n'
 '#define RAETH_MDIO_POLLS 1000\n'
 '#define DEV_NAME "eth2"\n'
 '#define init_net 0\n'
 '#define DEFINE_SPINLOCK(n) pthread_mutex_t n=PTHREAD_MUTEX_INITIALIZER\n'
 'static DEFINE_SPINLOCK(mdio_bus_lock);\n'
 'static bool mdio_detached = true;\n'
 'static int lock_depth,lock_errors,logs,commands,delay_us,fail_cmd,busy_cycles,remaining;\n'
 'static int page,c45_addr,lock_attempts,device_freed,after_free,refs,put_count;\n'
 'static int threaded,published,allow_finish,detach_done,late_ready,fail_reads;\n'
 'static pthread_mutex_t pause_lock=PTHREAD_MUTEX_INITIALIZER;\n'
 'static pthread_cond_t pause_cond=PTHREAD_COND_INITIALIZER;\n'
 'static u32 control,polling,controller_writes[32];\n'
 'static unsigned int controller_write_count;\n'
 'struct END_DEVICE {u32 architecture,features;struct {int phy_id;}mii_info;};\n'
 'struct PSEUDO_ADAPTER {struct {int phy_id;}mii_info;};\n'
 'struct net_device {void *priv;};\n'
 'static struct END_DEVICE adapter;\n'
 'static struct PSEUDO_ADAPTER pseudo_ad;\n'
 'static struct net_device dev,pseudo;\n'
 'static struct net_device *dev_raether;\n'
 'static void *netdev_priv(struct net_device *d){if(device_freed)after_free++;return d->priv;}\n'
 'static struct net_device *dev_get_by_name(int *net,const char '
 '*name){(void)net;(void)name;if(!dev_raether)return NULL;refs++;return dev_raether;}\n'
 'static void dev_put(struct net_device *d){(void)d;refs--;put_count++;}\n'
 'static int actual_init_net;\n'
 '#undef init_net\n'
 '#define init_net actual_init_net\n'
 '#define enable_mdio(n) ((void)(n))\n'
 '#define spin_lock_irqsave(lock,flags) do{(flags)=0; '
 '__sync_add_and_fetch(&lock_attempts,1);pthread_mutex_lock(lock);if(lock_depth)lock_errors++;lock_depth++;}while(0)\n'
 '#define spin_unlock_irqrestore(lock,flags) '
 'do{(void)(flags);if(lock_depth!=1)lock_errors++;else{lock_depth--;pthread_mutex_unlock(lock);}}while(0)\n'
 '#define pr_err_ratelimited(...) do{if(lock_depth)lock_errors++;logs++;}while(0)\n'
 'static void udelay(unsigned int us){delay_us+=(int)us;}\n'
 'static u32 sys_reg_read(unsigned int reg){\n'
 ' if(lock_depth!=1)lock_errors++;\n'
 ' if(reg==ESW_PHY_POLLING)return polling;\n'
 ' if(control&BIT(31)){\n'
 '  if(fail_cmd==-1 || (fail_cmd>0&&commands==fail_cmd)){if(late_ready && ++fail_reads>1001)fail_cmd=0;else '
 'return control;}\n'
 '  if(remaining>0){remaining--;return control;}\n'
 '  control&=~BIT(31);\n'
 ' }\n'
 ' return control;\n'
 '}\n'
 'static void sys_reg_write(unsigned int reg,u32 val){\n'
 ' if(lock_depth!=1)lock_errors++;\n'
 ' if(reg==ESW_PHY_POLLING){polling=val;return;}\n'
 ' if(controller_write_count<32)controller_writes[controller_write_count++]=val;else lock_errors++;\n'
 ' control=val;\n'
 ' if(!(val&BIT(31)))return;\n'
 ' commands++;remaining=busy_cycles;\n'
 ' unsigned int phy=(val>>20)&31,idx=(val>>25)&31,op=(val>>18)&3;\n'
 ' if(val&BIT(16)){\n'
 '  if(op==1 && phy==31 && idx==31)page=val&0x3ff;\n'
 '  if(op==2){u32 '
 'data=phy==31?(idx==16?(0x5678U^(u32)page):(0x1234U^((u32)page<<4)^idx)):(0x1234U^(phy<<5)^idx);control=BIT(31)|data;}\n'
 ' }else{\n'
 '  if(op==0)c45_addr=val&0xffff;\n'
 '  if(op==3)control=BIT(31)|((phy<<8)^idx^(u32)c45_addr);\n'
 ' }\n'
 ' if(threaded && '
 'commands==1){pthread_mutex_lock(&pause_lock);published=1;pthread_cond_broadcast(&pause_cond);while(!allow_finish)pthread_cond_wait(&pause_cond,&pause_lock);pthread_mutex_unlock(&pause_lock);}\n'
 '}\n')
SUFFIX = ('\n'
 'static u32 thread_values[2];\n'
 'static void *read_thread(void *arg){unsigned long i=(unsigned '
 'long)arg;mii_mgr_read(31,i?0x80:0x40,&thread_values[i]);return NULL;}\n'
 'static void *detach_thread(void *arg){(void)arg;mii_mgr_detach();detach_done=1;device_freed=1;return '
 'NULL;}\n'
 'int main(int argc,char **argv){\n'
 ' if(argc!=2) { return 2; }\n'
 ' const char *name=argv[1];CASE_ADMISSION\n'
 'u32 value=0xdeadbeef,result=0;\n'
 ' '
 'dev.priv=&adapter;pseudo.priv=&pseudo_ad;dev_raether=&dev;adapter.architecture=0;adapter.features=FE_GE2_SUPPORT;adapter.mii_info.phy_id=1;pseudo_ad.mii_info.phy_id=30;polling=0x80000009U;\n'
 ' mii_mgr_attach();lock_attempts=0;\n'
 ' if(!strcmp(name,"absent")){mii_mgr_detach();dev_raether=NULL;}\n'
 ' if(!strcmp(name,"detached"))mii_mgr_detach();\n'
 ' if(!strcmp(name,"initial-busy")||!strcmp(name,"wrapper-failure")){fail_cmd=-1;control=BIT(31);}\n'
 ' if(!strcmp(name,"read-timeout")||!strcmp(name,"cl45-address-failure"))fail_cmd=1;\n'
 ' if(!strcmp(name,"cl45-data-failure"))fail_cmd=2;\n'
 ' if(!strcmp(name,"cl45-late-address")){fail_cmd=1;late_ready=1;}\n'
 ' if(!strcmp(name,"switch-fail-1"))fail_cmd=1;\n'
 ' if(!strcmp(name,"switch-fail-2"))fail_cmd=2;\n'
 ' if(!strcmp(name,"switch-fail-3"))fail_cmd=3;\n'
 ' if(!strcmp(name,"switch-shared-budget"))busy_cycles=400;\n'
 ' if(!strncmp(name,"switch-",7))adapter.architecture=GE1_RGMII_FORCE_1000;\n'
 ' if(!strcmp(name,"concurrent-switch")||!strcmp(name,"detach-joins")){\n'
 '  pthread_t a,b;threaded=1;adapter.architecture=GE1_RGMII_FORCE_1000;\n'
 '  '
 'pthread_create(&a,NULL,read_thread,(void*)0);pthread_mutex_lock(&pause_lock);while(!published)pthread_cond_wait(&pause_cond,&pause_lock);pthread_mutex_unlock(&pause_lock);\n'
 '  if(!strcmp(name,"concurrent-switch"))pthread_create(&b,NULL,read_thread,(void*)1);else '
 'pthread_create(&b,NULL,detach_thread,NULL);\n'
 '  while(__atomic_load_n(&lock_attempts,__ATOMIC_RELAXED)<2)sched_yield();\n'
 '  '
 'pthread_mutex_lock(&pause_lock);allow_finish=1;pthread_cond_broadcast(&pause_cond);pthread_mutex_unlock(&pause_lock);pthread_join(a,NULL);pthread_join(b,NULL);\n'
 '  '
 'if(!strcmp(name,"detach-joins")){value=0xdeadbeef;result=mii_mgr_read(1,2,&value);}else{result=thread_values[0]==((0x5679U<<16)|0x1224U)&&thread_values[1]==((0x567aU<<16)|0x1214U);value=thread_values[0];}\n'
 ' }else '
 'if(!strcmp(name,"cl45-read")||!strcmp(name,"cl45-address-failure")||!strcmp(name,"cl45-data-failure")||!strcmp(name,"cl45-late-address"))result=mii_mgr_read_cl45(2,3,0x1234,&value);\n'
 ' else if(!strcmp(name,"cl45-write"))result=mii_mgr_write_cl45(2,3,0x1234,0x789a);\n'
 ' else if(!strcmp(name,"cl45-set"))result=mii_mgr_cl45_set_address(2,3,0x1234);\n'
 ' else if(!strcmp(name,"cl45-invalid-dev"))result=mii_mgr_read_cl45(2,32,0x1234,&value);\n'
 ' else if(!strcmp(name,"cl45-invalid-reg"))result=mii_mgr_read_cl45(2,3,0x10000,&value);\n'
 ' else if(!strcmp(name,"cl45-invalid-value"))result=mii_mgr_write_cl45(2,3,0x1234,0x10000);\n'
 ' else if(!strcmp(name,"write"))result=mii_mgr_write(1,2,0x4567);\n'
 ' else if(!strcmp(name,"invalid-phy"))result=mii_mgr_read(32,2,&value);\n'
 ' else if(!strcmp(name,"invalid-reg"))result=mii_mgr_read(1,32,&value);\n'
 ' else if(!strcmp(name,"invalid-value"))result=mii_mgr_write(1,2,0x10000);\n'
 ' else if(!strcmp(name,"null-read"))result=mii_mgr_read(1,2,NULL);\n'
 ' else if(!strcmp(name,"switch-write"))result=mii_mgr_write(31,0x40,0x12345678);\n'
 ' else if(!strcmp(name,"switch-unaligned"))result=mii_mgr_read(31,0x41,&value);\n'
 ' else if(!strcmp(name,"switch-outside"))result=mii_mgr_read(31,0x10000,&value);\n'
 ' else if(!strncmp(name,"switch-",7))result=mii_mgr_read(31,0x40,&value);\n'
 ' else '
 'if(!strcmp(name,"wrapper-read")||!strcmp(name,"wrapper-failure")){result=mdio_read(&dev,1,2);value=result;}\n'
 ' else if(!strcmp(name,"wrapper-virt")){result=mdio_virt_read(&pseudo,30,2);value=result;}\n'
 ' else if(!strcmp(name,"phy-ref")){result=get_current_phy_address();value=result;}\n'
 ' else if(!strcmp(name,"phy-absent")){dev_raether=NULL;result=get_current_phy_address();value=result;}\n'
 ' else result=mii_mgr_read(1,2,&value);\n'
 '\n'
 ' '
 'printf("{\\"ret\\":%u,\\"value\\":%u,\\"commands\\":%d,\\"delay_us\\":%d,\\"lock_errors\\":%d,\\"logs\\":%d,\\"polling\\":%u,\\"refs\\":%d,\\"puts\\":%d,\\"after_free\\":%d,\\"controller_writes\\":[",result,value,commands,delay_us,lock_errors,logs,polling,refs,put_count,after_free);\n'
 ' for(unsigned int i=0;i<controller_write_count;i++)printf("%s%u",i?",":"",controller_writes[i]);\n'
 ' printf("]}\\n");return 0;\n'
 '}\n')

def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'(?m)^[A-Za-z_][\w \t*]*\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked))
    if len(matches)!=1:raise ValueError('Missing/ambiguous MDIO body: '+name)
    start=matches[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer('[{}]',masked[opening:]):
        depth+=1 if m.group()=='{'else -1
        if depth==0:return text[start:opening+m.end()]
    raise ValueError('Unterminated MDIO body: '+name)
SOURCE_FRAGMENTS = {'mdio': ('#define RAETH_MDIO_POLL_US 10',
          '#define RAETH_MDIO_POLLS 1000',
          'static DEFINE_SPINLOCK(mdio_bus_lock);',
          'static bool mdio_detached = true;')}
def generate_source(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact MDIO source set required')
    for key,items in SOURCE_FRAGMENTS.items():
        for value in items:
            if texts[key].count(value)!=1:raise ValueError('MDIO declaration/budget drift')
    admission='if ('+' && '.join('strcmp(name,\"'+n+'\")'for n in CASE_NAMES)+') return 2;'
    return PREFIX+'\n'+"\n".join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)
def function_manifest(texts):
    return {n:{'source':k,'full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest(),'execution':'whole-function'}for n,k in FUNCTION_SOURCES.items()}
def source_only_manifest(texts):
    return {n:{'source':k,'full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest(),'execution':'source-only-not-run'}for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
