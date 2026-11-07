"""Complete RAETH shutdown/idle/IRQ and platform dispatch bodies with inert interfaces.

The actual driver initializer is executed through the whole platform dispatcher.
Core device shutdown/reboot entry points are source-only. No physical reset,
real DMA fence, full Linux ABI, module unload or arbitrary concurrency is proven.
"""
import hashlib
import re

SOURCE_PATHS = {'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
 'pdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_pdma.c',
 'qdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_qdma.c',
 'platform': 'trunk/linux-4.4.x/drivers/base/platform.c',
 'core': 'trunk/linux-4.4.x/drivers/base/core.c',
 'reboot': 'trunk/linux-4.4.x/kernel/reboot.c',
 'errno': 'trunk/linux-4.4.x/arch/mips/include/uapi/asm/errno.h',
 'errno_base': 'trunk/linux-4.4.x/include/uapi/asm-generic/errno-base.h',
 'config': 'trunk/configs/boards/K2P/kernel-4.4.x.config'}

FUNCTION_SOURCES = {'fe_pdma_wait_dma_idle': 'pdma',
 'fe_qdma_wait_dma_idle': 'qdma',
 'ei_stop_dma': 'raeth',
 'fe_int_disable': 'raeth',
 'ei_close': 'raeth',
 'raether_shutdown': 'raeth',
 'platform_drv_shutdown': 'platform'}

BODY_ORDER = ('fe_pdma_wait_dma_idle',
 'fe_qdma_wait_dma_idle',
 'ei_stop_dma',
 'fe_int_disable',
 'ei_close',
 'raether_shutdown',
 'platform_drv_shutdown')

SOURCE_ONLY_FUNCTION_SOURCES = {'__platform_driver_register': 'platform', 'device_shutdown': 'core', 'kernel_restart_prepare': 'reboot'}

SOURCE_DECLARATIONS = {'^(static struct platform_driver raeth_driver = \\{[\\s\\S]*?^\\};)': 'raeth',
 '^(#define ETIMEDOUT\\s+145[^\\n]*)$': 'errno',
 '^(#define\\s+EBUSY\\s+16[^\\n]*)$': 'errno_base'}

SOURCE_FRAGMENTS = {'raeth': ('module_platform_driver(raeth_driver);',),
 'config': ('CONFIG_RAETH=y', 'CONFIG_SOC_MT7621=y', 'CONFIG_RAETH_ESW_CONTROL=y')}

MODEL_VARIANT = {'K2P_MT7621_builtin_tasklet_shutdown': True,
 'forced_WORKQ_NAPI_are_nonshipping_variants': True,
 'actual_platform_drv_shutdown_whole_executed': True,
 'platform_core_reboot_source_only_not_compiled_bound_here': True,
 'hardware_DMA_IRQ_threads_RTNL_and_module_references_are_inert': True,
 'partial_device_struct_not_kernel_ABI': True,
 'void_shutdown_cannot_veto_machine_reset': True,
 'all_DMA_MMIO_clock_parent_module_owners_retained_even_after_idle': True,
 'platform_pm_domain_detach_runs_even_after_busy': True,
 'init_remove_callbacks_in_initializer_are_inert': True,
 'arbitrary_kernel_scheduling_or_reset_hardware_not_proven': True}

BASELINE_INITIALIZER = ('static struct platform_driver raeth_driver = {\n'
 '\t.probe = rather_probe,\n'
 '\t.remove = raether_remove,\n'
 '\t.driver = {\n'
 '\t\t   .name = raeth_string,\n'
 '\t\t   .owner = THIS_MODULE,\n'
 '\t\t   /* Keep manual detach disabled until physical DMA/consumer retirement is tested. */\n'
 '\t\t   .suppress_bind_attrs = true,\n'
 '\t\t   .of_match_table = raether_of_ids,\n'
 '\t\t   /* .pm = &raeth_pm_ops, */\n'
 '\t\t   },\n'
 '};')

BASELINE_MANIFEST = {'source_commit': '60ae6bf98bd46b68c648620c599f1aa78073131e',
 'path': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
 'region': 'whole-raeth_driver-initializer',
 'sha256': '69de82f8edecb499d6f9ab0a84bb4521741530d36e4127b6307719f46ca4af08'}

CASE_NAMES = ('no-drvdata',
 'never-opened',
 'closed',
 'up-main',
 'up-pseudo',
 'partial-init',
 'quarantined-up',
 'pdma-busy',
 'qdma-busy',
 'both-busy',
 'no-qdma',
 'repeat-idle',
 'repeat-busy',
 'busy-then-idle',
 'idle-then-busy',
 'shutdown-close',
 'busy-shutdown-close',
 'never-opened-close',
 'no-module-pin-up',
 'forced-workq',
 'forced-napi',
 'forced-napi-txrx',
 'forced-napi-rss2',
 'forced-napi-rss4',
 'no-threads',
 'partial-irqs',
 'inactive-irq-requested')

FIELDS = ('errors',
 'quarantined',
 'main_attached',
 'pseudo_attached',
 'tx_joins',
 'tx_live',
 'irq_live',
 'bh_live',
 'threads',
 'module_refs',
 'module_reserved',
 'owners',
 'dma_stages',
 'mdio',
 'proc',
 'stop_calls',
 'pdma_reads',
 'qdma_reads',
 'delay',
 'pm_detach',
 'close_ret',
 'releases',
 'resets',
 'module_gets',
 'module_puts',
 'detach_calls',
 'proc_exits',
 'irq_writes',
 'spin_depth',
 'rtnl_depth',
 'logs')

EXPECTED_ROWS = {'no-drvdata': {'errors': 0,
                'quarantined': 0,
                'main_attached': 1,
                'pseudo_attached': 1,
                'tx_joins': 0,
                'tx_live': 2,
                'irq_live': 6,
                'bh_live': 1,
                'threads': 2,
                'module_refs': 1,
                'module_reserved': 1,
                'owners': 31,
                'dma_stages': 6,
                'mdio': 1,
                'proc': 1,
                'stop_calls': 0,
                'pdma_reads': 0,
                'qdma_reads': 0,
                'delay': 0,
                'pm_detach': 1,
                'close_ret': 999,
                'releases': 0,
                'resets': 0,
                'module_gets': 0,
                'module_puts': 0,
                'detach_calls': 0,
                'proc_exits': 0,
                'irq_writes': 0,
                'spin_depth': 0,
                'rtnl_depth': 0,
                'logs': 0},
 'never-opened': {'errors': 0,
                  'quarantined': 1,
                  'main_attached': 0,
                  'pseudo_attached': -1,
                  'tx_joins': 1,
                  'tx_live': 0,
                  'irq_live': 0,
                  'bh_live': 0,
                  'threads': 0,
                  'module_refs': 0,
                  'module_reserved': 0,
                  'owners': 31,
                  'dma_stages': 0,
                  'mdio': 0,
                  'proc': 0,
                  'stop_calls': 1,
                  'pdma_reads': 1,
                  'qdma_reads': 1,
                  'delay': 0,
                  'pm_detach': 1,
                  'close_ret': 999,
                  'releases': 0,
                  'resets': 0,
                  'module_gets': 0,
                  'module_puts': 0,
                  'detach_calls': 1,
                  'proc_exits': 1,
                  'irq_writes': 3,
                  'spin_depth': 0,
                  'rtnl_depth': 0,
                  'logs': 0},
 'closed': {'errors': 0,
            'quarantined': 1,
            'main_attached': 0,
            'pseudo_attached': -1,
            'tx_joins': 1,
            'tx_live': 0,
            'irq_live': 0,
            'bh_live': 0,
            'threads': 0,
            'module_refs': 0,
            'module_reserved': 0,
            'owners': 31,
            'dma_stages': 0,
            'mdio': 0,
            'proc': 0,
            'stop_calls': 1,
            'pdma_reads': 1,
            'qdma_reads': 1,
            'delay': 0,
            'pm_detach': 1,
            'close_ret': 999,
            'releases': 0,
            'resets': 0,
            'module_gets': 0,
            'module_puts': 0,
            'detach_calls': 1,
            'proc_exits': 1,
            'irq_writes': 3,
            'spin_depth': 0,
            'rtnl_depth': 0,
            'logs': 0},
 'up-main': {'errors': 0,
             'quarantined': 1,
             'main_attached': 0,
             'pseudo_attached': -1,
             'tx_joins': 1,
             'tx_live': 0,
             'irq_live': 0,
             'bh_live': 0,
             'threads': 0,
             'module_refs': 1,
             'module_reserved': 1,
             'owners': 31,
             'dma_stages': 6,
             'mdio': 0,
             'proc': 0,
             'stop_calls': 1,
             'pdma_reads': 1,
             'qdma_reads': 1,
             'delay': 0,
             'pm_detach': 1,
             'close_ret': 999,
             'releases': 0,
             'resets': 0,
             'module_gets': 0,
             'module_puts': 0,
             'detach_calls': 1,
             'proc_exits': 1,
             'irq_writes': 6,
             'spin_depth': 0,
             'rtnl_depth': 0,
             'logs': 0},
 'up-pseudo': {'errors': 0,
               'quarantined': 1,
               'main_attached': 0,
               'pseudo_attached': 0,
               'tx_joins': 2,
               'tx_live': 0,
               'irq_live': 0,
               'bh_live': 0,
               'threads': 0,
               'module_refs': 1,
               'module_reserved': 1,
               'owners': 31,
               'dma_stages': 6,
               'mdio': 0,
               'proc': 0,
               'stop_calls': 1,
               'pdma_reads': 1,
               'qdma_reads': 1,
               'delay': 0,
               'pm_detach': 1,
               'close_ret': 999,
               'releases': 0,
               'resets': 0,
               'module_gets': 0,
               'module_puts': 0,
               'detach_calls': 1,
               'proc_exits': 1,
               'irq_writes': 6,
               'spin_depth': 0,
               'rtnl_depth': 0,
               'logs': 0},
 'partial-init': {'errors': 0,
                  'quarantined': 1,
                  'main_attached': 0,
                  'pseudo_attached': 0,
                  'tx_joins': 2,
                  'tx_live': 0,
                  'irq_live': 0,
                  'bh_live': 0,
                  'threads': 0,
                  'module_refs': 1,
                  'module_reserved': 1,
                  'owners': 7,
                  'dma_stages': 4,
                  'mdio': 0,
                  'proc': 0,
                  'stop_calls': 1,
                  'pdma_reads': 1,
                  'qdma_reads': 1,
                  'delay': 0,
                  'pm_detach': 1,
                  'close_ret': 999,
                  'releases': 0,
                  'resets': 0,
                  'module_gets': 0,
                  'module_puts': 0,
                  'detach_calls': 1,
                  'proc_exits': 1,
                  'irq_writes': 6,
                  'spin_depth': 0,
                  'rtnl_depth': 0,
                  'logs': 0},
 'quarantined-up': {'errors': 0,
                    'quarantined': 1,
                    'main_attached': 0,
                    'pseudo_attached': 0,
                    'tx_joins': 2,
                    'tx_live': 0,
                    'irq_live': 0,
                    'bh_live': 0,
                    'threads': 0,
                    'module_refs': 1,
                    'module_reserved': 1,
                    'owners': 31,
                    'dma_stages': 6,
                    'mdio': 0,
                    'proc': 0,
                    'stop_calls': 1,
                    'pdma_reads': 1,
                    'qdma_reads': 1,
                    'delay': 0,
                    'pm_detach': 1,
                    'close_ret': 999,
                    'releases': 0,
                    'resets': 0,
                    'module_gets': 0,
                    'module_puts': 0,
                    'detach_calls': 1,
                    'proc_exits': 1,
                    'irq_writes': 6,
                    'spin_depth': 0,
                    'rtnl_depth': 0,
                    'logs': 0},
 'pdma-busy': {'errors': 0,
               'quarantined': 1,
               'main_attached': 0,
               'pseudo_attached': 0,
               'tx_joins': 2,
               'tx_live': 0,
               'irq_live': 0,
               'bh_live': 0,
               'threads': 0,
               'module_refs': 1,
               'module_reserved': 1,
               'owners': 31,
               'dma_stages': 6,
               'mdio': 0,
               'proc': 0,
               'stop_calls': 1,
               'pdma_reads': 1000,
               'qdma_reads': 1,
               'delay': 10000,
               'pm_detach': 1,
               'close_ret': 999,
               'releases': 0,
               'resets': 0,
               'module_gets': 0,
               'module_puts': 0,
               'detach_calls': 1,
               'proc_exits': 1,
               'irq_writes': 6,
               'spin_depth': 0,
               'rtnl_depth': 0,
               'logs': 3},
 'qdma-busy': {'errors': 0,
               'quarantined': 1,
               'main_attached': 0,
               'pseudo_attached': 0,
               'tx_joins': 2,
               'tx_live': 0,
               'irq_live': 0,
               'bh_live': 0,
               'threads': 0,
               'module_refs': 1,
               'module_reserved': 1,
               'owners': 31,
               'dma_stages': 6,
               'mdio': 0,
               'proc': 0,
               'stop_calls': 1,
               'pdma_reads': 1,
               'qdma_reads': 1000,
               'delay': 10000,
               'pm_detach': 1,
               'close_ret': 999,
               'releases': 0,
               'resets': 0,
               'module_gets': 0,
               'module_puts': 0,
               'detach_calls': 1,
               'proc_exits': 1,
               'irq_writes': 6,
               'spin_depth': 0,
               'rtnl_depth': 0,
               'logs': 3},
 'both-busy': {'errors': 0,
               'quarantined': 1,
               'main_attached': 0,
               'pseudo_attached': 0,
               'tx_joins': 2,
               'tx_live': 0,
               'irq_live': 0,
               'bh_live': 0,
               'threads': 0,
               'module_refs': 1,
               'module_reserved': 1,
               'owners': 31,
               'dma_stages': 6,
               'mdio': 0,
               'proc': 0,
               'stop_calls': 1,
               'pdma_reads': 1000,
               'qdma_reads': 1000,
               'delay': 20000,
               'pm_detach': 1,
               'close_ret': 999,
               'releases': 0,
               'resets': 0,
               'module_gets': 0,
               'module_puts': 0,
               'detach_calls': 1,
               'proc_exits': 1,
               'irq_writes': 6,
               'spin_depth': 0,
               'rtnl_depth': 0,
               'logs': 4},
 'no-qdma': {'errors': 0,
             'quarantined': 1,
             'main_attached': 0,
             'pseudo_attached': 0,
             'tx_joins': 2,
             'tx_live': 0,
             'irq_live': 0,
             'bh_live': 0,
             'threads': 0,
             'module_refs': 1,
             'module_reserved': 1,
             'owners': 31,
             'dma_stages': 6,
             'mdio': 0,
             'proc': 0,
             'stop_calls': 1,
             'pdma_reads': 1,
             'qdma_reads': 0,
             'delay': 0,
             'pm_detach': 1,
             'close_ret': 999,
             'releases': 0,
             'resets': 0,
             'module_gets': 0,
             'module_puts': 0,
             'detach_calls': 1,
             'proc_exits': 1,
             'irq_writes': 4,
             'spin_depth': 0,
             'rtnl_depth': 0,
             'logs': 0},
 'repeat-idle': {'errors': 0,
                 'quarantined': 1,
                 'main_attached': 0,
                 'pseudo_attached': 0,
                 'tx_joins': 4,
                 'tx_live': 0,
                 'irq_live': 0,
                 'bh_live': 0,
                 'threads': 0,
                 'module_refs': 1,
                 'module_reserved': 1,
                 'owners': 31,
                 'dma_stages': 6,
                 'mdio': 0,
                 'proc': 0,
                 'stop_calls': 2,
                 'pdma_reads': 2,
                 'qdma_reads': 2,
                 'delay': 0,
                 'pm_detach': 2,
                 'close_ret': 999,
                 'releases': 0,
                 'resets': 0,
                 'module_gets': 0,
                 'module_puts': 0,
                 'detach_calls': 2,
                 'proc_exits': 2,
                 'irq_writes': 9,
                 'spin_depth': 0,
                 'rtnl_depth': 0,
                 'logs': 0},
 'repeat-busy': {'errors': 0,
                 'quarantined': 1,
                 'main_attached': 0,
                 'pseudo_attached': 0,
                 'tx_joins': 4,
                 'tx_live': 0,
                 'irq_live': 0,
                 'bh_live': 0,
                 'threads': 0,
                 'module_refs': 1,
                 'module_reserved': 1,
                 'owners': 31,
                 'dma_stages': 6,
                 'mdio': 0,
                 'proc': 0,
                 'stop_calls': 2,
                 'pdma_reads': 2000,
                 'qdma_reads': 2,
                 'delay': 20000,
                 'pm_detach': 2,
                 'close_ret': 999,
                 'releases': 0,
                 'resets': 0,
                 'module_gets': 0,
                 'module_puts': 0,
                 'detach_calls': 2,
                 'proc_exits': 2,
                 'irq_writes': 9,
                 'spin_depth': 0,
                 'rtnl_depth': 0,
                 'logs': 6},
 'busy-then-idle': {'errors': 0,
                    'quarantined': 1,
                    'main_attached': 0,
                    'pseudo_attached': 0,
                    'tx_joins': 4,
                    'tx_live': 0,
                    'irq_live': 0,
                    'bh_live': 0,
                    'threads': 0,
                    'module_refs': 1,
                    'module_reserved': 1,
                    'owners': 31,
                    'dma_stages': 6,
                    'mdio': 0,
                    'proc': 0,
                    'stop_calls': 2,
                    'pdma_reads': 1001,
                    'qdma_reads': 2,
                    'delay': 10000,
                    'pm_detach': 2,
                    'close_ret': 999,
                    'releases': 0,
                    'resets': 0,
                    'module_gets': 0,
                    'module_puts': 0,
                    'detach_calls': 2,
                    'proc_exits': 2,
                    'irq_writes': 9,
                    'spin_depth': 0,
                    'rtnl_depth': 0,
                    'logs': 3},
 'idle-then-busy': {'errors': 0,
                    'quarantined': 1,
                    'main_attached': 0,
                    'pseudo_attached': 0,
                    'tx_joins': 4,
                    'tx_live': 0,
                    'irq_live': 0,
                    'bh_live': 0,
                    'threads': 0,
                    'module_refs': 1,
                    'module_reserved': 1,
                    'owners': 31,
                    'dma_stages': 6,
                    'mdio': 0,
                    'proc': 0,
                    'stop_calls': 2,
                    'pdma_reads': 1001,
                    'qdma_reads': 2,
                    'delay': 10000,
                    'pm_detach': 2,
                    'close_ret': 999,
                    'releases': 0,
                    'resets': 0,
                    'module_gets': 0,
                    'module_puts': 0,
                    'detach_calls': 2,
                    'proc_exits': 2,
                    'irq_writes': 9,
                    'spin_depth': 0,
                    'rtnl_depth': 0,
                    'logs': 3},
 'shutdown-close': {'errors': 0,
                    'quarantined': 1,
                    'main_attached': 0,
                    'pseudo_attached': 0,
                    'tx_joins': 2,
                    'tx_live': 0,
                    'irq_live': 0,
                    'bh_live': 0,
                    'threads': 0,
                    'module_refs': 1,
                    'module_reserved': 1,
                    'owners': 31,
                    'dma_stages': 6,
                    'mdio': 0,
                    'proc': 0,
                    'stop_calls': 1,
                    'pdma_reads': 1,
                    'qdma_reads': 1,
                    'delay': 0,
                    'pm_detach': 1,
                    'close_ret': -16,
                    'releases': 0,
                    'resets': 0,
                    'module_gets': 0,
                    'module_puts': 0,
                    'detach_calls': 1,
                    'proc_exits': 1,
                    'irq_writes': 6,
                    'spin_depth': 0,
                    'rtnl_depth': 0,
                    'logs': 0},
 'busy-shutdown-close': {'errors': 0,
                         'quarantined': 1,
                         'main_attached': 0,
                         'pseudo_attached': 0,
                         'tx_joins': 2,
                         'tx_live': 0,
                         'irq_live': 0,
                         'bh_live': 0,
                         'threads': 0,
                         'module_refs': 1,
                         'module_reserved': 1,
                         'owners': 31,
                         'dma_stages': 6,
                         'mdio': 0,
                         'proc': 0,
                         'stop_calls': 1,
                         'pdma_reads': 1000,
                         'qdma_reads': 1,
                         'delay': 10000,
                         'pm_detach': 1,
                         'close_ret': -16,
                         'releases': 0,
                         'resets': 0,
                         'module_gets': 0,
                         'module_puts': 0,
                         'detach_calls': 1,
                         'proc_exits': 1,
                         'irq_writes': 6,
                         'spin_depth': 0,
                         'rtnl_depth': 0,
                         'logs': 3},
 'never-opened-close': {'errors': 0,
                        'quarantined': 1,
                        'main_attached': 0,
                        'pseudo_attached': -1,
                        'tx_joins': 1,
                        'tx_live': 0,
                        'irq_live': 0,
                        'bh_live': 0,
                        'threads': 0,
                        'module_refs': 0,
                        'module_reserved': 0,
                        'owners': 31,
                        'dma_stages': 0,
                        'mdio': 0,
                        'proc': 0,
                        'stop_calls': 1,
                        'pdma_reads': 1,
                        'qdma_reads': 1,
                        'delay': 0,
                        'pm_detach': 1,
                        'close_ret': -16,
                        'releases': 0,
                        'resets': 0,
                        'module_gets': 0,
                        'module_puts': 0,
                        'detach_calls': 1,
                        'proc_exits': 1,
                        'irq_writes': 3,
                        'spin_depth': 0,
                        'rtnl_depth': 0,
                        'logs': 0},
 'no-module-pin-up': {'errors': 0,
                      'quarantined': 1,
                      'main_attached': 0,
                      'pseudo_attached': 0,
                      'tx_joins': 2,
                      'tx_live': 0,
                      'irq_live': 0,
                      'bh_live': 0,
                      'threads': 0,
                      'module_refs': 0,
                      'module_reserved': 0,
                      'owners': 31,
                      'dma_stages': 6,
                      'mdio': 0,
                      'proc': 0,
                      'stop_calls': 1,
                      'pdma_reads': 1,
                      'qdma_reads': 1,
                      'delay': 0,
                      'pm_detach': 1,
                      'close_ret': 999,
                      'releases': 0,
                      'resets': 0,
                      'module_gets': 0,
                      'module_puts': 0,
                      'detach_calls': 1,
                      'proc_exits': 1,
                      'irq_writes': 6,
                      'spin_depth': 0,
                      'rtnl_depth': 0,
                      'logs': 0},
 'forced-workq': {'errors': 0,
                  'quarantined': 1,
                  'main_attached': 0,
                  'pseudo_attached': 0,
                  'tx_joins': 2,
                  'tx_live': 0,
                  'irq_live': 0,
                  'bh_live': 0,
                  'threads': 0,
                  'module_refs': 1,
                  'module_reserved': 1,
                  'owners': 31,
                  'dma_stages': 6,
                  'mdio': 0,
                  'proc': 0,
                  'stop_calls': 1,
                  'pdma_reads': 1,
                  'qdma_reads': 1,
                  'delay': 0,
                  'pm_detach': 1,
                  'close_ret': 999,
                  'releases': 0,
                  'resets': 0,
                  'module_gets': 0,
                  'module_puts': 0,
                  'detach_calls': 1,
                  'proc_exits': 1,
                  'irq_writes': 6,
                  'spin_depth': 0,
                  'rtnl_depth': 0,
                  'logs': 0},
 'forced-napi': {'errors': 0,
                 'quarantined': 1,
                 'main_attached': 0,
                 'pseudo_attached': 0,
                 'tx_joins': 2,
                 'tx_live': 0,
                 'irq_live': 0,
                 'bh_live': 0,
                 'threads': 0,
                 'module_refs': 1,
                 'module_reserved': 1,
                 'owners': 31,
                 'dma_stages': 6,
                 'mdio': 0,
                 'proc': 0,
                 'stop_calls': 1,
                 'pdma_reads': 1,
                 'qdma_reads': 1,
                 'delay': 0,
                 'pm_detach': 1,
                 'close_ret': 999,
                 'releases': 0,
                 'resets': 0,
                 'module_gets': 0,
                 'module_puts': 0,
                 'detach_calls': 1,
                 'proc_exits': 1,
                 'irq_writes': 6,
                 'spin_depth': 0,
                 'rtnl_depth': 0,
                 'logs': 0},
 'forced-napi-txrx': {'errors': 0,
                      'quarantined': 1,
                      'main_attached': 0,
                      'pseudo_attached': 0,
                      'tx_joins': 2,
                      'tx_live': 0,
                      'irq_live': 0,
                      'bh_live': 0,
                      'threads': 0,
                      'module_refs': 1,
                      'module_reserved': 1,
                      'owners': 31,
                      'dma_stages': 6,
                      'mdio': 0,
                      'proc': 0,
                      'stop_calls': 1,
                      'pdma_reads': 1,
                      'qdma_reads': 1,
                      'delay': 0,
                      'pm_detach': 1,
                      'close_ret': 999,
                      'releases': 0,
                      'resets': 0,
                      'module_gets': 0,
                      'module_puts': 0,
                      'detach_calls': 1,
                      'proc_exits': 1,
                      'irq_writes': 6,
                      'spin_depth': 0,
                      'rtnl_depth': 0,
                      'logs': 0},
 'forced-napi-rss2': {'errors': 0,
                      'quarantined': 1,
                      'main_attached': 0,
                      'pseudo_attached': 0,
                      'tx_joins': 2,
                      'tx_live': 0,
                      'irq_live': 0,
                      'bh_live': 0,
                      'threads': 0,
                      'module_refs': 1,
                      'module_reserved': 1,
                      'owners': 31,
                      'dma_stages': 6,
                      'mdio': 0,
                      'proc': 0,
                      'stop_calls': 1,
                      'pdma_reads': 1,
                      'qdma_reads': 1,
                      'delay': 0,
                      'pm_detach': 1,
                      'close_ret': 999,
                      'releases': 0,
                      'resets': 0,
                      'module_gets': 0,
                      'module_puts': 0,
                      'detach_calls': 1,
                      'proc_exits': 1,
                      'irq_writes': 6,
                      'spin_depth': 0,
                      'rtnl_depth': 0,
                      'logs': 0},
 'forced-napi-rss4': {'errors': 0,
                      'quarantined': 1,
                      'main_attached': 0,
                      'pseudo_attached': 0,
                      'tx_joins': 2,
                      'tx_live': 0,
                      'irq_live': 0,
                      'bh_live': 0,
                      'threads': 0,
                      'module_refs': 1,
                      'module_reserved': 1,
                      'owners': 31,
                      'dma_stages': 6,
                      'mdio': 0,
                      'proc': 0,
                      'stop_calls': 1,
                      'pdma_reads': 1,
                      'qdma_reads': 1,
                      'delay': 0,
                      'pm_detach': 1,
                      'close_ret': 999,
                      'releases': 0,
                      'resets': 0,
                      'module_gets': 0,
                      'module_puts': 0,
                      'detach_calls': 1,
                      'proc_exits': 1,
                      'irq_writes': 6,
                      'spin_depth': 0,
                      'rtnl_depth': 0,
                      'logs': 0},
 'no-threads': {'errors': 0,
                'quarantined': 1,
                'main_attached': 0,
                'pseudo_attached': 0,
                'tx_joins': 2,
                'tx_live': 0,
                'irq_live': 0,
                'bh_live': 0,
                'threads': 0,
                'module_refs': 1,
                'module_reserved': 1,
                'owners': 31,
                'dma_stages': 6,
                'mdio': 0,
                'proc': 0,
                'stop_calls': 1,
                'pdma_reads': 1,
                'qdma_reads': 1,
                'delay': 0,
                'pm_detach': 1,
                'close_ret': 999,
                'releases': 0,
                'resets': 0,
                'module_gets': 0,
                'module_puts': 0,
                'detach_calls': 1,
                'proc_exits': 1,
                'irq_writes': 6,
                'spin_depth': 0,
                'rtnl_depth': 0,
                'logs': 0},
 'partial-irqs': {'errors': 0,
                  'quarantined': 1,
                  'main_attached': 0,
                  'pseudo_attached': 0,
                  'tx_joins': 2,
                  'tx_live': 0,
                  'irq_live': 0,
                  'bh_live': 0,
                  'threads': 0,
                  'module_refs': 1,
                  'module_reserved': 1,
                  'owners': 31,
                  'dma_stages': 6,
                  'mdio': 0,
                  'proc': 0,
                  'stop_calls': 1,
                  'pdma_reads': 1,
                  'qdma_reads': 1,
                  'delay': 0,
                  'pm_detach': 1,
                  'close_ret': 999,
                  'releases': 0,
                  'resets': 0,
                  'module_gets': 0,
                  'module_puts': 0,
                  'detach_calls': 1,
                  'proc_exits': 1,
                  'irq_writes': 6,
                  'spin_depth': 0,
                  'rtnl_depth': 0,
                  'logs': 0},
 'inactive-irq-requested': {'errors': 0,
                            'quarantined': 1,
                            'main_attached': 0,
                            'pseudo_attached': 0,
                            'tx_joins': 2,
                            'tx_live': 0,
                            'irq_live': 0,
                            'bh_live': 0,
                            'threads': 0,
                            'module_refs': 1,
                            'module_reserved': 1,
                            'owners': 31,
                            'dma_stages': 6,
                            'mdio': 0,
                            'proc': 0,
                            'stop_calls': 1,
                            'pdma_reads': 1,
                            'qdma_reads': 1,
                            'delay': 0,
                            'pm_detach': 1,
                            'close_ret': 999,
                            'releases': 0,
                            'resets': 0,
                            'module_gets': 0,
                            'module_puts': 0,
                            'detach_calls': 1,
                            'proc_exits': 1,
                            'irq_writes': 3,
                            'spin_depth': 0,
                            'rtnl_depth': 0,
                            'logs': 0}}

PREFIX = ('\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <stdbool.h>\n'
 '#include <stdint.h>\n'
 '#include <string.h>\n'
 '#define BIT(n) (1U<<(n))\n'
 '#define WRITE_ONCE(a,b) ((a)=(b))\n'
 '#define THIS_MODULE NULL\n'
 '#define FE_QDMA BIT(0)\n'
 '#define FE_GE2_SUPPORT BIT(1)\n'
 '#define FE_INT_TASKLET BIT(2)\n'
 '#define FE_INT_WORKQ BIT(3)\n'
 '#define FE_INT_NAPI BIT(4)\n'
 '#define FE_INT_NAPI_TX_RX BIT(5)\n'
 '#define FE_INT_NAPI_RX_ONLY BIT(6)\n'
 '#define FE_RSS_2RING BIT(7)\n'
 '#define FE_RSS_4RING BIT(8)\n'
 '#define MT7622_FE 7622\n'
 '#define RAETH_FE_INT_ENABLE 10\n'
 '#define QFE_INT_ENABLE 11\n'
 '#define FE_INT_ENABLE2 12\n'
 '#define PDMA_GLO_CFG 1\n'
 '#define QDMA_GLO_CFG 2\n'
 '#define RX_DMA_BUSY BIT(3)\n'
 '#define TX_DMA_BUSY BIT(1)\n'
 '#define pr_err(...) do { logs++; } while(0)\n'
 'struct platform_device;\n'
 'struct device_driver { const char *name; void *owner; bool suppress_bind_attrs; const void '
 '*of_match_table; };\n'
 'struct device { struct device_driver *driver; void *data; };\n'
 'struct platform_device { struct device dev; };\n'
 'struct platform_driver { int (*probe)(struct platform_device *); int (*remove)(struct platform_device '
 '*); void (*shutdown)(struct platform_device *); struct device_driver driver; };\n'
 'struct net_device { void *priv; int attached,tx_live; char name[8]; };\n'
 'struct END_DEVICE {\n'
 ' bool dma_quarantined,module_reserved,irq_active;\n'
 ' struct net_device *pseudo_dev;\n'
 ' void *kreset_task,*kphy_poll_task;\n'
 ' unsigned int features,irq_requested,dma_stages;\n'
 ' int irq_lock,irq0,irq1,irq2,irq3,switch_irq,esw_irq;\n'
 ' int rx_wq,rx_tasklet,napi,napi_tx,napi_rx,napi_rx_rss0,napi_rx_rss1,napi_rx_rss2,napi_rx_rss3;\n'
 ' int chip_name;\n'
 '};\n'
 'static struct platform_device parent;\n'
 'static struct net_device main_dev,pseudo_dev;\n'
 'static struct END_DEVICE priv;\n'
 'static int errors,rtnl_depth,spin_depth,phase;\n'
 'static int irq_live,bh_live,thread_live,owners=31,module_refs=1,mdio_live=1,proc_live=1;\n'
 'static int '
 'tx_joins,stop_calls,pdma_reads,qdma_reads,delay_us,pm_detach,releases,resets,module_gets,module_puts,detach_calls,proc_exits,irq_writes,logs;\n'
 'static int busy_p,busy_q;\n'
 'static void check(int ok) { if(!ok)errors++; }\n'
 'static void *netdev_priv(struct net_device *d) { check(d==&main_dev);return d->priv; }\n'
 'static struct net_device *platform_get_drvdata(struct platform_device *p) { check(p==&parent);return '
 'p->dev.data; }\n'
 'static struct platform_device *to_platform_device(struct device *d) { check(d==&parent.dev);return '
 '&parent; }\n'
 'static struct platform_driver *to_platform_driver(struct device_driver *d);\n'
 'static void rtnl_lock(void) { check(rtnl_depth==0);rtnl_depth++; }\n'
 'static void rtnl_unlock(void) { check(rtnl_depth==1);rtnl_depth--; }\n'
 'static void netif_device_detach(struct net_device *d) { '
 'check(rtnl_depth==1&&priv.dma_quarantined);d->attached=0; }\n'
 'static void mii_mgr_detach(void) { '
 'check(rtnl_depth==0&&!main_dev.attached&&(!priv.pseudo_dev||!pseudo_dev.attached));mdio_live=0;phase=1;detach_calls++; '
 '}\n'
 'static void debug_proc_exit(void) { check(rtnl_depth==0&&phase==1);proc_live=0;phase=2;proc_exits++; '
 '}\n'
 'static void netif_tx_disable(struct net_device *d) { '
 'check(rtnl_depth==1&&phase>=2);d->tx_live=0;tx_joins++; }\n'
 'static int kthread_stop(void *p) { '
 'check(p&&rtnl_depth==1&&thread_live>0&&!main_dev.tx_live&&(!priv.pseudo_dev||!pseudo_dev.tx_live));thread_live--;return '
 '0; }\n'
 '#define spin_lock_irqsave(l,f) do { (void)(l);check(!spin_depth);spin_depth++;(f)=0; } while(0)\n'
 '#define spin_unlock_irqrestore(l,f) do { (void)(l);(void)(f);check(spin_depth==1);spin_depth--; } '
 'while(0)\n'
 'static void sys_reg_write(int reg,unsigned int value) { '
 'check(rtnl_depth==1&&value==0&&reg>=10);phase=3;irq_writes++; }\n'
 'static void free_irq(int irq,void *data) { '
 '(void)irq;(void)data;check(!priv.irq_active&&phase==3&&irq_live>0&&!spin_depth);irq_live--; }\n'
 'static void cancel_work_sync(int *w) { (void)w;check(!irq_live);bh_live=0; }\n'
 'static void tasklet_kill(int *t) { (void)t;check(!irq_live);bh_live=0; }\n'
 'static void napi_disable(int *n) { (void)n;check(!irq_live);bh_live=0; }\n'
 'static void ra2880stop(struct END_DEVICE *p) { '
 '(void)p;check(rtnl_depth==1&&!irq_live&&!bh_live&&!thread_live&&!main_dev.tx_live&&(!priv.pseudo_dev||!pseudo_dev.tx_live));stop_calls++; '
 '}\n'
 'static unsigned int sys_reg_read(int reg) { '
 'check(rtnl_depth==1&&stop_calls>0&&!spin_depth);if(reg==1){pdma_reads++;return '
 'busy_p?RX_DMA_BUSY:0;}check(reg==2);qdma_reads++;return busy_q?TX_DMA_BUSY:0; }\n'
 'static void udelay(unsigned int us) { delay_us+=(int)us; }\n'
 'static void ei_deinit_dma(struct net_device *d) { (void)d;releases++;owners=0;priv.dma_stages=0; }\n'
 'static void fe_reset(void) { resets++; }\n'
 'static void fe_sw_deinit(struct END_DEVICE *p) { (void)p;releases++; }\n'
 'static void virtualif_close(struct net_device *d) { (void)d; }\n'
 'static void module_put(void *m) { (void)m;module_refs--;module_puts++; }\n'
 '#define try_module_get(m) ((void)(m),module_gets++,1)\n'
 '#define free_netdev(d) do { (void)(d);releases++;owners=0; } while(0)\n'
 '#define unregister_netdevice(d) do { (void)(d);releases++; } while(0)\n'
 'static int rather_probe(struct platform_device *p) { (void)p;return 0; }\n'
 'static int raether_remove(struct platform_device *p) { (void)p;return 0; }\n'
 'static const char raeth_string[]="RAETH_DRV";\n'
 'static const int raether_of_ids[1]={0};\n'
 'FUNCTION_DECLARATIONS\n'
 'SOURCE_DEFINITIONS\n'
 'static struct platform_driver *to_platform_driver(struct device_driver *d) { '
 'check(d==&raeth_driver.driver);return &raeth_driver; }\n'
 'static void dev_pm_domain_detach(struct device *d,bool off) { '
 'check(d==&parent.dev&&off&&!rtnl_depth);pm_detach++; }\n' '\n/* Core restart API recorder; old owner/event observations stay unchanged. */\n#define REBOOT_DMA_RAETH (1U << 0)\n#define REBOOT_DMA_MT7615 (1U << 1)\nstatic unsigned int restart_failure_reports;\nstatic void reboot_dma_failure_report(unsigned int reasons) { restart_failure_reports |= reasons; }\n')


SUFFIX = ('\n'
 'int main(int argc,char **argv)\n'
 '{\n'
 ' const char *name=argc>1?argv[1]:"";\n'
 ' int close_ret=999,action=0;\n'
 ' CASE_ADMISSION\n'
 ' (void)&raether_shutdown;\n'
 ' main_dev.priv=&priv;main_dev.attached=1;main_dev.tx_live=1;\n'
 ' pseudo_dev.attached=1;pseudo_dev.tx_live=1;\n'
 ' parent.dev.data=&main_dev;parent.dev.driver=&raeth_driver.driver;\n'
 ' priv.pseudo_dev=&pseudo_dev;priv.features=FE_QDMA|FE_GE2_SUPPORT|FE_INT_TASKLET;\n'
 ' priv.module_reserved=true;priv.irq_active=true;priv.irq_requested=63;priv.dma_stages=6;\n'
 ' priv.kreset_task=(void*)1;priv.kphy_poll_task=(void*)2;\n'
 ' irq_live=6;bh_live=1;thread_live=2;\n'
 ' if(!strcmp(name,"no-drvdata")) parent.dev.data=NULL;\n'
 ' if(!strcmp(name,"never-opened")||!strcmp(name,"closed")||!strcmp(name,"never-opened-close")) {\n'
 '  '
 'priv.module_reserved=false;module_refs=0;priv.irq_active=false;priv.irq_requested=0;priv.dma_stages=0;irq_live=bh_live=thread_live=0;priv.kreset_task=priv.kphy_poll_task=NULL;priv.pseudo_dev=NULL;main_dev.tx_live=0;\n'
 ' }\n'
 ' if(!strcmp(name,"up-main")) {priv.pseudo_dev=NULL;priv.features&=~FE_GE2_SUPPORT;}\n'
 ' if(!strcmp(name,"partial-init")) '
 '{priv.irq_requested=1;irq_live=1;priv.kphy_poll_task=NULL;thread_live=1;priv.dma_stages=4;owners=7;}\n'
 ' if(!strcmp(name,"quarantined-up"))priv.dma_quarantined=true;\n'
 ' '
 'if(!strcmp(name,"pdma-busy")||!strcmp(name,"both-busy")||!strcmp(name,"repeat-busy")||!strcmp(name,"busy-then-idle")||!strcmp(name,"busy-shutdown-close"))busy_p=1;\n'
 ' if(!strcmp(name,"qdma-busy")||!strcmp(name,"both-busy")||!strcmp(name,"no-qdma"))busy_q=1;\n'
 ' if(!strcmp(name,"no-qdma"))priv.features&=~FE_QDMA;\n'
 ' '
 'if(!strcmp(name,"repeat-idle")||!strcmp(name,"repeat-busy")||!strcmp(name,"busy-then-idle")||!strcmp(name,"idle-then-busy"))action=1;\n'
 ' if(!strcmp(name,"no-module-pin-up")){priv.module_reserved=false;module_refs=0;}\n'
 ' if(!strcmp(name,"forced-workq"))priv.features=(priv.features&~FE_INT_TASKLET)|FE_INT_WORKQ;\n'
 ' if(!strcmp(name,"forced-napi"))priv.features=(priv.features&~FE_INT_TASKLET)|FE_INT_NAPI;\n'
 ' '
 'if(!strcmp(name,"forced-napi-txrx"))priv.features=(priv.features&~FE_INT_TASKLET)|FE_INT_NAPI|FE_INT_NAPI_TX_RX;\n'
 ' '
 'if(!strcmp(name,"forced-napi-rss2"))priv.features=(priv.features&~FE_INT_TASKLET)|FE_INT_NAPI|FE_INT_NAPI_RX_ONLY|FE_RSS_2RING;\n'
 ' '
 'if(!strcmp(name,"forced-napi-rss4"))priv.features=(priv.features&~FE_INT_TASKLET)|FE_INT_NAPI|FE_INT_NAPI_RX_ONLY|FE_RSS_4RING;\n'
 ' if(!strcmp(name,"no-threads")){priv.kreset_task=priv.kphy_poll_task=NULL;thread_live=0;}\n'
 ' if(!strcmp(name,"partial-irqs")){priv.irq_requested=3;irq_live=2;}\n'
 ' '
 'if(!strcmp(name,"inactive-irq-requested")){priv.irq_requested=3;irq_live=2;priv.irq_active=false;bh_live=0;}\n'
 ' platform_drv_shutdown(&parent.dev);\n'
 ' '
 'if(action){if(!strcmp(name,"busy-then-idle"))busy_p=0;if(!strcmp(name,"idle-then-busy"))busy_p=1;platform_drv_shutdown(&parent.dev);}\n'
 ' '
 'if(!strcmp(name,"shutdown-close")||!strcmp(name,"busy-shutdown-close")||!strcmp(name,"never-opened-close"))close_ret=ei_close(&main_dev);\n'
 ' '
 'printf("{\\"errors\\":%d,\\"quarantined\\":%d,\\"main_attached\\":%d,\\"pseudo_attached\\":%d,\\"tx_joins\\":%d,\\"tx_live\\":%d,\\"irq_live\\":%d,\\"bh_live\\":%d,\\"threads\\":%d,\\"module_refs\\":%d,\\"module_reserved\\":%d,\\"owners\\":%d,\\"dma_stages\\":%d,\\"mdio\\":%d,\\"proc\\":%d,\\"stop_calls\\":%d,\\"pdma_reads\\":%d,\\"qdma_reads\\":%d,\\"delay\\":%d,\\"pm_detach\\":%d,\\"close_ret\\":%d,\\"releases\\":%d,\\"resets\\":%d,\\"module_gets\\":%d,\\"module_puts\\":%d,\\"detach_calls\\":%d,\\"proc_exits\\":%d,\\"irq_writes\\":%d,\\"spin_depth\\":%d,\\"rtnl_depth\\":%d,\\"logs\\":%d}\\n",errors,priv.dma_quarantined,main_dev.attached,priv.pseudo_dev?pseudo_dev.attached:-1,tx_joins,main_dev.tx_live+(priv.pseudo_dev?pseudo_dev.tx_live:0),irq_live,bh_live,thread_live,module_refs,priv.module_reserved,owners,priv.dma_stages,mdio_live,proc_live,stop_calls,pdma_reads,qdma_reads,delay_us,pm_detach,close_ret,releases,resets,module_gets,module_puts,detach_calls,proc_exits,irq_writes,spin_depth,rtnl_depth,logs);\n'
 ' return errors?7:0;\n'
 '}\n')


def mask(text):
    return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\'',lambda m:' '*len(m.group()),text)

def function(text,name):
    clean=mask(text)
    pattern=r'^(?:static\s+)?(?:inline\s+)?(?:int|void)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    matches=list(re.finditer(pattern,clean,re.M))
    if len(matches)!=1:raise ValueError('Missing/ambiguous shutdown function: '+name)
    start=matches[0].start();opening=clean.index('{',start);depth=0
    for pos in range(opening,len(clean)):
        depth+=1 if clean[pos]=='{' else -1 if clean[pos]=='}' else 0
        if not depth:return text[start:pos+1]
    raise ValueError('Unterminated shutdown body: '+name)

def source_declarations(texts):
    result={}
    for pattern,key in SOURCE_DECLARATIONS.items():
        rows=re.findall(pattern,texts[key],re.M)
        if len(rows)!=1 or not isinstance(rows[0],str):raise ValueError('Unique shutdown declaration required')
        result[pattern]={'source':key,'sha256':hashlib.sha256(rows[0].encode()).hexdigest()}
    return result

def generate_source(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact shutdown source set required')
    for key,rows in SOURCE_FRAGMENTS.items():
        for row in rows:
            if sum(line.strip()==row for line in texts[key].splitlines())!=1:raise ValueError('Shutdown source profile mismatch')
    bodies={n:function(texts[k],n)for n,k in FUNCTION_SOURCES.items()}
    definitions=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        rows=re.findall(pattern,texts[key],re.M)
        if len(rows)!=1:raise ValueError('Unique shutdown source declaration required')
        definitions.append(rows[0])
    prefix=PREFIX.replace('FUNCTION_DECLARATIONS','\n'.join(v.split('{',1)[0].rstrip()+';'for v in bodies.values())).replace('SOURCE_DEFINITIONS','\n'.join(definitions))
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return prefix+'\n'.join(bodies.values())+SUFFIX.replace('CASE_ADMISSION',admission)

def function_manifest(texts):
    return {n:{'source':k,'full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest(),'execution':'whole-function'}for n,k in FUNCTION_SOURCES.items()}

def source_only_manifest(texts):
    return {n:{'source':k,'full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest(),'execution':'source-only-not-run'}for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
