"""Whole RAETH remove and real driver-core release bodies; hardware/IRQ/refcount seams are inert."""
import hashlib,re
SOURCE_PATHS = {'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
 'pdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_pdma.c',
 'qdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_qdma.c',
 'core': 'trunk/linux-4.4.x/drivers/base/dd.c',
 'header': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.h'}
FUNCTION_SOURCES = {'fe_pdma_wait_dma_idle': 'pdma',
 'fe_qdma_wait_dma_idle': 'qdma',
 'ei_deinit_dma': 'raeth',
 'ei_stop_dma': 'raeth',
 'fe_int_disable': 'raeth',
 'ei_close': 'raeth',
 'raeth_release_resources': 'raeth',
 'raether_remove': 'raeth',
 '__device_release_driver': 'core',
 'raeth_init_pseudo': 'raeth'}
BODY_ORDER = ('fe_pdma_wait_dma_idle',
 'fe_qdma_wait_dma_idle',
 'ei_deinit_dma',
 'ei_stop_dma',
 'fe_int_disable',
 'ei_close',
 'raeth_release_resources',
 'raether_remove',
 '__device_release_driver',
 'raeth_init_pseudo')
SOURCE_ONLY_FUNCTION_SOURCES = {'rather_probe': 'raeth'}
MODEL_VARIANT = {'K2P_MT7621_builtin_tasklet_single_controller': True,
 'whole_driver_core_unconditional_devres_release': True,
 'hardware_MMIO_DMA_IRQ_threads_refcounts_are_inert': True,
 'bounded_DMAPDMA_QDMA_busy_failures': True,
 'foreign_netdev_reference_snapshot_only': True,
 'all_arbitrary_kernel_concurrency_not_proven': True,
 'non_MT7621_clock_enable_rollback_not_proven': True,
 'module_unload_while_MODULE_GOING_not_proven': True,
 'generic_remove_all_profiles_not_claimed': True,
 'reduced_clock_owner_slots': 3,
 'reduced_pseudo_tx_queue_count': 1,
 'structural_layout_refcount_seams_not_kernel_ABI': True}
CASE_NAMES = ('success',
 'pdma-busy',
 'qdma-busy',
 'both-busy',
 'quarantined',
 'foreign-main',
 'foreign-pseudo',
 'nat-rx',
 'nat-tx',
 'module-denied',
 'closed',
 'owned-qdma',
 'no-pseudo',
 'partial-resources',
 'driver-remove',
 'repeat-success',
 'repeat-busy',
 'pseudo-first-oom',
 'pseudo-first-register-fail',
 'pseudo-first-success')
EXPECTED_ROWS = {'success': {'ret': 0,
             'dma': 0,
             'book': 0,
             'irq': 0,
             'bh': 0,
             'threads': 0,
             'module': 0,
             'unregister': 2,
             'free': 2,
             'unmap': 3,
             'region': 1,
             'clock_disable': 1,
             'clock_put': 2,
             'node_put': 1,
             'parent_put': 1,
             'qdma_put': 0,
             'core': 1,
             'devres_unmap': 0,
             'global': 0,
             'drvdata': 0,
             'driver': 0,
             'mdio': 0,
             'proc': 0,
             'close_ret': -16,
             'reset': 1,
             'delay': 0,
             'errors': 0,
             'pseudo_alloc': 0,
             'pseudo_register': 0,
             'pseudo_published': 0},
 'pdma-busy': {'ret': -145,
               'dma': 2,
               'book': 1,
               'irq': 0,
               'bh': 0,
               'threads': 0,
               'module': 1,
               'unregister': 0,
               'free': 0,
               'unmap': 0,
               'region': 0,
               'clock_disable': 0,
               'clock_put': 0,
               'node_put': 0,
               'parent_put': 0,
               'qdma_put': 0,
               'core': 1,
               'devres_unmap': 0,
               'global': 1,
               'drvdata': 0,
               'driver': 0,
               'mdio': 0,
               'proc': 0,
               'close_ret': 999,
               'reset': 0,
               'delay': 10000,
               'errors': 0,
               'pseudo_alloc': 0,
               'pseudo_register': 0,
               'pseudo_published': 1},
 'qdma-busy': {'ret': -145,
               'dma': 2,
               'book': 1,
               'irq': 0,
               'bh': 0,
               'threads': 0,
               'module': 1,
               'unregister': 0,
               'free': 0,
               'unmap': 0,
               'region': 0,
               'clock_disable': 0,
               'clock_put': 0,
               'node_put': 0,
               'parent_put': 0,
               'qdma_put': 0,
               'core': 1,
               'devres_unmap': 0,
               'global': 1,
               'drvdata': 0,
               'driver': 0,
               'mdio': 0,
               'proc': 0,
               'close_ret': 999,
               'reset': 0,
               'delay': 10000,
               'errors': 0,
               'pseudo_alloc': 0,
               'pseudo_register': 0,
               'pseudo_published': 1},
 'both-busy': {'ret': -145,
               'dma': 2,
               'book': 1,
               'irq': 0,
               'bh': 0,
               'threads': 0,
               'module': 1,
               'unregister': 0,
               'free': 0,
               'unmap': 0,
               'region': 0,
               'clock_disable': 0,
               'clock_put': 0,
               'node_put': 0,
               'parent_put': 0,
               'qdma_put': 0,
               'core': 1,
               'devres_unmap': 0,
               'global': 1,
               'drvdata': 0,
               'driver': 0,
               'mdio': 0,
               'proc': 0,
               'close_ret': 999,
               'reset': 0,
               'delay': 20000,
               'errors': 0,
               'pseudo_alloc': 0,
               'pseudo_register': 0,
               'pseudo_published': 1},
 'quarantined': {'ret': -16,
                 'dma': 2,
                 'book': 1,
                 'irq': 0,
                 'bh': 0,
                 'threads': 0,
                 'module': 1,
                 'unregister': 0,
                 'free': 0,
                 'unmap': 0,
                 'region': 0,
                 'clock_disable': 0,
                 'clock_put': 0,
                 'node_put': 0,
                 'parent_put': 0,
                 'qdma_put': 0,
                 'core': 1,
                 'devres_unmap': 0,
                 'global': 1,
                 'drvdata': 0,
                 'driver': 0,
                 'mdio': 0,
                 'proc': 0,
                 'close_ret': 999,
                 'reset': 0,
                 'delay': 0,
                 'errors': 0,
                 'pseudo_alloc': 0,
                 'pseudo_register': 0,
                 'pseudo_published': 1},
 'foreign-main': {'ret': -16,
                  'dma': 2,
                  'book': 1,
                  'irq': 0,
                  'bh': 0,
                  'threads': 0,
                  'module': 1,
                  'unregister': 0,
                  'free': 0,
                  'unmap': 0,
                  'region': 0,
                  'clock_disable': 0,
                  'clock_put': 0,
                  'node_put': 0,
                  'parent_put': 0,
                  'qdma_put': 0,
                  'core': 1,
                  'devres_unmap': 0,
                  'global': 1,
                  'drvdata': 0,
                  'driver': 0,
                  'mdio': 0,
                  'proc': 0,
                  'close_ret': 999,
                  'reset': 0,
                  'delay': 0,
                  'errors': 0,
                  'pseudo_alloc': 0,
                  'pseudo_register': 0,
                  'pseudo_published': 1},
 'foreign-pseudo': {'ret': -16,
                    'dma': 2,
                    'book': 1,
                    'irq': 0,
                    'bh': 0,
                    'threads': 0,
                    'module': 1,
                    'unregister': 0,
                    'free': 0,
                    'unmap': 0,
                    'region': 0,
                    'clock_disable': 0,
                    'clock_put': 0,
                    'node_put': 0,
                    'parent_put': 0,
                    'qdma_put': 0,
                    'core': 1,
                    'devres_unmap': 0,
                    'global': 1,
                    'drvdata': 0,
                    'driver': 0,
                    'mdio': 0,
                    'proc': 0,
                    'close_ret': 999,
                    'reset': 0,
                    'delay': 0,
                    'errors': 0,
                    'pseudo_alloc': 0,
                    'pseudo_register': 0,
                    'pseudo_published': 1},
 'nat-rx': {'ret': -16,
            'dma': 2,
            'book': 1,
            'irq': 0,
            'bh': 0,
            'threads': 0,
            'module': 1,
            'unregister': 0,
            'free': 0,
            'unmap': 0,
            'region': 0,
            'clock_disable': 0,
            'clock_put': 0,
            'node_put': 0,
            'parent_put': 0,
            'qdma_put': 0,
            'core': 1,
            'devres_unmap': 0,
            'global': 1,
            'drvdata': 0,
            'driver': 0,
            'mdio': 0,
            'proc': 0,
            'close_ret': 999,
            'reset': 0,
            'delay': 0,
            'errors': 0,
            'pseudo_alloc': 0,
            'pseudo_register': 0,
            'pseudo_published': 1},
 'nat-tx': {'ret': -16,
            'dma': 2,
            'book': 1,
            'irq': 0,
            'bh': 0,
            'threads': 0,
            'module': 1,
            'unregister': 0,
            'free': 0,
            'unmap': 0,
            'region': 0,
            'clock_disable': 0,
            'clock_put': 0,
            'node_put': 0,
            'parent_put': 0,
            'qdma_put': 0,
            'core': 1,
            'devres_unmap': 0,
            'global': 1,
            'drvdata': 0,
            'driver': 0,
            'mdio': 0,
            'proc': 0,
            'close_ret': 999,
            'reset': 0,
            'delay': 0,
            'errors': 0,
            'pseudo_alloc': 0,
            'pseudo_register': 0,
            'pseudo_published': 1},
 'module-denied': {'ret': -16,
                   'dma': 2,
                   'book': 1,
                   'irq': 0,
                   'bh': 0,
                   'threads': 0,
                   'module': 0,
                   'unregister': 0,
                   'free': 0,
                   'unmap': 0,
                   'region': 0,
                   'clock_disable': 0,
                   'clock_put': 0,
                   'node_put': 0,
                   'parent_put': 0,
                   'qdma_put': 0,
                   'core': 1,
                   'devres_unmap': 0,
                   'global': 1,
                   'drvdata': 0,
                   'driver': 0,
                   'mdio': 0,
                   'proc': 0,
                   'close_ret': 999,
                   'reset': 0,
                   'delay': 0,
                   'errors': 0,
                   'pseudo_alloc': 0,
                   'pseudo_register': 0,
                   'pseudo_published': 1},
 'closed': {'ret': 0,
            'dma': 0,
            'book': 0,
            'irq': 0,
            'bh': 0,
            'threads': 0,
            'module': 0,
            'unregister': 2,
            'free': 2,
            'unmap': 3,
            'region': 1,
            'clock_disable': 1,
            'clock_put': 2,
            'node_put': 1,
            'parent_put': 1,
            'qdma_put': 0,
            'core': 1,
            'devres_unmap': 0,
            'global': 0,
            'drvdata': 0,
            'driver': 0,
            'mdio': 0,
            'proc': 0,
            'close_ret': -16,
            'reset': 1,
            'delay': 0,
            'errors': 0,
            'pseudo_alloc': 0,
            'pseudo_register': 0,
            'pseudo_published': 0},
 'owned-qdma': {'ret': 0,
                'dma': 0,
                'book': 0,
                'irq': 0,
                'bh': 0,
                'threads': 0,
                'module': 0,
                'unregister': 2,
                'free': 2,
                'unmap': 3,
                'region': 1,
                'clock_disable': 1,
                'clock_put': 2,
                'node_put': 1,
                'parent_put': 1,
                'qdma_put': 1,
                'core': 1,
                'devres_unmap': 0,
                'global': 0,
                'drvdata': 0,
                'driver': 0,
                'mdio': 0,
                'proc': 0,
                'close_ret': -16,
                'reset': 1,
                'delay': 0,
                'errors': 0,
                'pseudo_alloc': 0,
                'pseudo_register': 0,
                'pseudo_published': 0},
 'no-pseudo': {'ret': 0,
               'dma': 0,
               'book': 0,
               'irq': 0,
               'bh': 0,
               'threads': 0,
               'module': 0,
               'unregister': 1,
               'free': 1,
               'unmap': 3,
               'region': 1,
               'clock_disable': 1,
               'clock_put': 2,
               'node_put': 1,
               'parent_put': 1,
               'qdma_put': 0,
               'core': 1,
               'devres_unmap': 0,
               'global': 0,
               'drvdata': 0,
               'driver': 0,
               'mdio': 0,
               'proc': 0,
               'close_ret': -16,
               'reset': 1,
               'delay': 0,
               'errors': 0,
               'pseudo_alloc': 0,
               'pseudo_register': 0,
               'pseudo_published': 0},
 'partial-resources': {'ret': 0,
                       'dma': 0,
                       'book': 0,
                       'irq': 0,
                       'bh': 0,
                       'threads': 0,
                       'module': 0,
                       'unregister': 2,
                       'free': 2,
                       'unmap': 1,
                       'region': 0,
                       'clock_disable': 0,
                       'clock_put': 1,
                       'node_put': 0,
                       'parent_put': 1,
                       'qdma_put': 0,
                       'core': 1,
                       'devres_unmap': 0,
                       'global': 0,
                       'drvdata': 0,
                       'driver': 0,
                       'mdio': 0,
                       'proc': 0,
                       'close_ret': -16,
                       'reset': 1,
                       'delay': 0,
                       'errors': 0,
                       'pseudo_alloc': 0,
                       'pseudo_register': 0,
                       'pseudo_published': 0},
 'driver-remove': {'ret': 0,
                   'dma': 0,
                   'book': 0,
                   'irq': 0,
                   'bh': 0,
                   'threads': 0,
                   'module': 0,
                   'unregister': 2,
                   'free': 2,
                   'unmap': 3,
                   'region': 1,
                   'clock_disable': 1,
                   'clock_put': 2,
                   'node_put': 1,
                   'parent_put': 1,
                   'qdma_put': 0,
                   'core': 1,
                   'devres_unmap': 0,
                   'global': 0,
                   'drvdata': 0,
                   'driver': 0,
                   'mdio': 0,
                   'proc': 0,
                   'close_ret': -16,
                   'reset': 1,
                   'delay': 0,
                   'errors': 0,
                   'pseudo_alloc': 0,
                   'pseudo_register': 0,
                   'pseudo_published': 0},
 'repeat-success': {'ret': 0,
                    'dma': 0,
                    'book': 0,
                    'irq': 0,
                    'bh': 0,
                    'threads': 0,
                    'module': 0,
                    'unregister': 2,
                    'free': 2,
                    'unmap': 3,
                    'region': 1,
                    'clock_disable': 1,
                    'clock_put': 2,
                    'node_put': 1,
                    'parent_put': 1,
                    'qdma_put': 0,
                    'core': 1,
                    'devres_unmap': 0,
                    'global': 0,
                    'drvdata': 0,
                    'driver': 0,
                    'mdio': 0,
                    'proc': 0,
                    'close_ret': -16,
                    'reset': 1,
                    'delay': 0,
                    'errors': 0,
                    'pseudo_alloc': 0,
                    'pseudo_register': 0,
                    'pseudo_published': 0},
 'repeat-busy': {'ret': -16,
                 'dma': 2,
                 'book': 1,
                 'irq': 0,
                 'bh': 0,
                 'threads': 0,
                 'module': 1,
                 'unregister': 0,
                 'free': 0,
                 'unmap': 0,
                 'region': 0,
                 'clock_disable': 0,
                 'clock_put': 0,
                 'node_put': 0,
                 'parent_put': 0,
                 'qdma_put': 0,
                 'core': 1,
                 'devres_unmap': 0,
                 'global': 1,
                 'drvdata': 0,
                 'driver': 0,
                 'mdio': 0,
                 'proc': 0,
                 'close_ret': 999,
                 'reset': 0,
                 'delay': 0,
                 'errors': 0,
                 'pseudo_alloc': 0,
                 'pseudo_register': 0,
                 'pseudo_published': 1},
 'pseudo-first-oom': {'ret': 0,
                      'dma': 0,
                      'book': 0,
                      'irq': 0,
                      'bh': 0,
                      'threads': 0,
                      'module': 0,
                      'unregister': 0,
                      'free': 0,
                      'unmap': 0,
                      'region': 0,
                      'clock_disable': 0,
                      'clock_put': 0,
                      'node_put': 0,
                      'parent_put': 0,
                      'qdma_put': 0,
                      'core': 0,
                      'devres_unmap': 0,
                      'global': 1,
                      'drvdata': 1,
                      'driver': 1,
                      'mdio': 0,
                      'proc': 0,
                      'close_ret': 999,
                      'reset': 0,
                      'delay': 0,
                      'errors': 0,
                      'pseudo_alloc': 1,
                      'pseudo_register': 0,
                      'pseudo_published': 0},
 'pseudo-first-register-fail': {'ret': 0,
                                'dma': 0,
                                'book': 0,
                                'irq': 0,
                                'bh': 0,
                                'threads': 0,
                                'module': 0,
                                'unregister': 0,
                                'free': 1,
                                'unmap': 0,
                                'region': 0,
                                'clock_disable': 0,
                                'clock_put': 0,
                                'node_put': 0,
                                'parent_put': 0,
                                'qdma_put': 0,
                                'core': 0,
                                'devres_unmap': 0,
                                'global': 1,
                                'drvdata': 1,
                                'driver': 1,
                                'mdio': 0,
                                'proc': 0,
                                'close_ret': 999,
                                'reset': 0,
                                'delay': 0,
                                'errors': 0,
                                'pseudo_alloc': 1,
                                'pseudo_register': 1,
                                'pseudo_published': 0},
 'pseudo-first-success': {'ret': 0,
                          'dma': 0,
                          'book': 0,
                          'irq': 0,
                          'bh': 0,
                          'threads': 0,
                          'module': 0,
                          'unregister': 0,
                          'free': 0,
                          'unmap': 0,
                          'region': 0,
                          'clock_disable': 0,
                          'clock_put': 0,
                          'node_put': 0,
                          'parent_put': 0,
                          'qdma_put': 0,
                          'core': 0,
                          'devres_unmap': 0,
                          'global': 1,
                          'drvdata': 1,
                          'driver': 1,
                          'mdio': 0,
                          'proc': 0,
                          'close_ret': 999,
                          'reset': 0,
                          'delay': 0,
                          'errors': 0,
                          'pseudo_alloc': 1,
                          'pseudo_register': 1,
                          'pseudo_published': 1}}
PREFIX = ('\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <stdbool.h>\n'
 '#include <stdint.h>\n'
 '#include <string.h>\n'
 '#define BIT(n) (1U<<(n))\n'
 '#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))\n'
 '#define WRITE_ONCE(a,b) ((a)=(b))\n'
 '#define READ_ONCE(a) (a)\n'
 '#define IS_ERR_OR_NULL(a) (!(a))\n'
 '#define THIS_MODULE NULL\n'
 '#define EBUSY 16\n'
 '#define ETIMEDOUT 145\n'
 '#define NETREG_REGISTERED 1\n'
 '#define CONFIG_RAETH_ESW_CONTROL 1\n'
 '#define FE_QDMA BIT(4)\n'
 '#define FE_INT_NAPI 0U\n'
 '#define FE_INT_WORKQ 0U\n'
 '#define FE_INT_TASKLET BIT(7)\n'
 '#define FE_GE2_SUPPORT BIT(9)\n'
 '#define FE_HW_LRO 0U\n'
 '#define FE_RSS_4RING 0U\n'
 '#define FE_RSS_2RING 0U\n'
 '#define FE_INT_NAPI_TX_RX 0U\n'
 '#define FE_INT_NAPI_RX_ONLY 0U\n'
 '#define FE_DMA_QTX BIT(1)\n'
 '#define FE_DMA_PTX BIT(0)\n'
 '#define FE_DMA_PRX BIT(2)\n'
 '#define FE_DMA_QRX BIT(3)\n'
 '#define FE_DMA_EXTRA_RX BIT(4)\n'
 '#define MT7622_FE 7622\n'
 '#define RAETH_FE_INT_ENABLE 10\n'
 '#define QFE_INT_ENABLE 11\n'
 '#define FE_INT_ENABLE2 12\n'
 '#define PDMA_GLO_CFG 1\n'
 '#define QDMA_GLO_CFG 2\n'
 '#define RX_DMA_BUSY BIT(3)\n'
 '#define TX_DMA_BUSY BIT(1)\n'
 '#define BUS_NOTIFY_UNBIND_DRIVER 1\n'
 '#define BUS_NOTIFY_UNBOUND_DRIVER 2\n'
 '#define pr_info(...) ((void)0)\n'
 '#define pr_err(...) ((void)0)\n'
 'typedef unsigned int u32;\n'
 'typedef unsigned long resource_size_t;\n'
 'struct device;\n'
 'struct device_driver { int (*remove)(struct device *); };\n'
 'struct bus_private { int bus_notifier; };\n'
 'struct bus_type { int (*remove)(struct device *); struct bus_private *p; };\n'
 'struct device_private { int knode_driver; };\n'
 'struct dev_pm_domain { void (*dismiss)(struct device *); };\n'
 'struct device { struct device_driver *driver; struct bus_type *bus; struct device_private *p; struct '
 'dev_pm_domain *pm_domain; void *data; int refs; };\n'
 'struct platform_device { struct device dev; };\n'
 'struct net_device { unsigned int features,vlan_features; void *netdev_ops,*ethtool_ops; unsigned char '
 'dev_addr[6]; void *priv; char name[8]; int refs,reg_state,freed; };\n'
 'struct END_DEVICE {\n'
 ' bool dma_quarantined,module_reserved,irq_active,clocks_enabled,frame_region_owned,parent_ref_held;\n'
 ' struct net_device *pseudo_dev;\n'
 ' struct platform_device *qdma_pdev;\n'
 ' void *kreset_task,*kphy_poll_task,*clks[3],*switch_np;\n'
 ' unsigned int irq_requested,features,dma_stages;\n'
 ' int irq0,irq1,irq2,irq3,switch_irq,esw_irq,irq_lock,rx_wq,rx_tasklet;\n'
 ' int napi,napi_tx,napi_rx,napi_rx_rss0,napi_rx_rss1,napi_rx_rss2,napi_rx_rss3;\n'
 ' int chip_name;\n'
 ' resource_size_t frame_start,frame_size;\n'
 '};\n'
 'static struct platform_device parent,qdma;\n'
 'static struct net_device main_dev,pseudo_dev;\n'
 'static struct END_DEVICE priv;\n'
 'static struct net_device *dev_raether;\n'
 'static void *ethdma_mac_base,*ethdma_sysctl_base,*ethdma_frame_engine_base;\n'
 'static void *ra_sw_nat_hook_rx,*ra_sw_nat_hook_tx;\n'
 'static int errors,rtnl_depth,busy_p,busy_q,delay_us,ret,last_close,core_releases;\n'
 'static int dma_live,book_live,irq_live,bh_live,proc_live,mdio_live,thread_live,module_refs;\n'
 'static int '
 'unregistered,freed,unmaps,regions,clock_disables,clock_puts,node_puts,parent_puts,qdma_puts,reset_count,esw_exits,wake_calls;\n'
 'static int module_get_ok=1,phase,devres_managed,devres_unmaps;\n'
 'static void check(int ok) { if(!ok) errors++; }\n'
 'static void *netdev_priv(struct net_device *d) { check(d&&!d->freed); return d->priv; }\n'
 'static struct net_device *platform_get_drvdata(struct platform_device *p) { return p->dev.data; }\n'
 'static void platform_set_drvdata(struct platform_device *p,void *v) { p->dev.data=v; }\n'
 'static void rtnl_lock(void) { check(!rtnl_depth);rtnl_depth++; }\n'
 'static void rtnl_unlock(void) { check(rtnl_depth==1);rtnl_depth--; }\n'
 'static int try_module_get(void *m) { (void)m;if(module_get_ok)module_refs++;return module_get_ok; }\n'
 'static void module_put(void *m) { (void)m;check(module_refs>0);module_refs--; }\n'
 'static void mii_mgr_detach(void) { check(!rtnl_depth);mdio_live=0;phase=1; }\n'
 'static void debug_proc_exit(void) { check(!rtnl_depth&&phase==1);proc_live=0;phase=2; }\n'
 'static void netif_tx_disable(struct net_device *d) { check(rtnl_depth&&d&&!d->freed&&phase>=2); }\n'
 'static int kthread_stop(void *t) { check(t&&rtnl_depth&&thread_live>0);thread_live--;return 0; }\n'
 '#define spin_lock_irqsave(l,f) do { (void)(l); (f)=0; } while(0)\n'
 '#define spin_unlock_irqrestore(l,f) do { (void)(l); (void)(f); } while(0)\n'
 'static void sys_reg_write(int reg,unsigned int value) { '
 '(void)value;check(ethdma_frame_engine_base!=NULL);if(reg>=10)phase=3; }\n'
 'static unsigned int sys_reg_read(int reg) { check(ethdma_frame_engine_base!=NULL);return '
 '(reg==1?busy_p:busy_q)?RX_DMA_BUSY:0; }\n'
 'static void udelay(unsigned int us) { delay_us+=(int)us; }\n'
 'static void free_irq(int irq,void *data) { (void)irq;(void)data;check(irq_live>0&&phase>=3);irq_live--; }\n'
 'static void cancel_work_sync(int *w) { (void)w;check(irq_live==0);bh_live=0; }\n'
 'static void tasklet_kill(int *t) { (void)t;check(irq_live==0);bh_live=0; }\n'
 'static void napi_disable(int *n) { (void)n;bh_live=0; }\n'
 'static void ra2880stop(struct END_DEVICE *p) { (void)p;check(irq_live==0&&bh_live==0); }\n'
 'static void dma_free_stage(void) { check(!busy_p&&!busy_q&&!irq_live&&!bh_live&&dma_live>0);dma_live--; }\n'
 '#define fe_qdma_tx_dma_deinit(d) do { (void)(d);dma_free_stage(); } while(0)\n'
 '#define fe_pdma_tx_dma_deinit(d) do { (void)(d);dma_free_stage(); } while(0)\n'
 '#define fe_pdma_rx_dma_deinit(d) do { (void)(d);dma_free_stage(); } while(0)\n'
 '#define fe_qdma_rx_dma_deinit(d) do { (void)(d);dma_free_stage(); } while(0)\n'
 '#define fe_hw_lro_deinit(d) do { (void)(d);dma_free_stage(); } while(0)\n'
 '#define fe_rss_4ring_deinit(d) do { (void)(d);dma_free_stage(); } while(0)\n'
 '#define fe_rss_2ring_deinit(d) do { (void)(d);dma_free_stage(); } while(0)\n'
 'static int netdev_refcnt_read(struct net_device *d) { check(!d->freed);return d->refs; }\n'
 'static void fe_reset(void) { check(!busy_p&&!busy_q&&!dma_live);reset_count++; }\n'
 'static void virtualif_close(struct net_device *d) { (void)d; }\n'
 'static void fe_sw_deinit(struct END_DEVICE *d) { (void)d; }\n'
 'static int ei_close(struct net_device *);\n'
 'static void unregister_netdevice(struct net_device *d) { '
 'check(rtnl_depth&&d->reg_state==NETREG_REGISTERED&&!dma_live&&!irq_live&&!bh_live&&!thread_live&&!mdio_live&&!proc_live&&d->refs==1);if(d==&main_dev)last_close=ei_close(d);d->reg_state=0;unregistered++; '
 '}\n'
 'static void free_netdev(struct net_device *d) { '
 'check(!d->freed&&!d->reg_state&&!dma_live&&!irq_live&&!bh_live&&!mdio_live&&!proc_live);d->freed=1;freed++; '
 '}\n'
 'static void esw_ioctl_uninit(void) { esw_exits++; }\n'
 'static void device_init_wakeup(struct device *d,bool b) { (void)d;check(!b);wake_calls++; }\n'
 'static void ei_clock_disable(struct END_DEVICE *p) { (void)p;check(!dma_live);clock_disables++; }\n'
 'static void clk_put(void *c) { check(c!=NULL);clock_puts++; }\n'
 'static void of_node_put(void *n) { if(n)node_puts++; }\n'
 'static void iounmap(void *a) { check(a!=NULL&&!dma_live&&!irq_live&&!mdio_live);unmaps++; }\n'
 'static void release_mem_region(resource_size_t a,resource_size_t n) { check(a==100&&n==4096);regions++; }\n'
 'static void platform_device_put(struct platform_device *p) { check(p!=&parent&&p==&qdma);qdma_puts++; }\n'
 'static void fe_tx_rx_dec_free(struct END_DEVICE *p) { (void)p;check(!dma_live);book_live=0; }\n'
 'static void put_device(struct device *d) { check(d==&parent.dev&&d->refs==2);d->refs--;parent_puts++; }\n'
 'static int driver_allows_async_probing(struct device_driver *d) { (void)d;return 1; }\n'
 'static void async_synchronize_full(void) { }\n'
 'static void pm_runtime_get_sync(struct device *d) { (void)d; }\n'
 'static void driver_sysfs_remove(struct device *d) { (void)d; }\n'
 'static void blocking_notifier_call_chain(int *n,int msg,struct device *d) { (void)n;(void)msg;(void)d; }\n'
 'static void pm_runtime_put_sync(struct device *d) { (void)d; }\n'
 'static void devres_release_all(struct device *d) { '
 '(void)d;core_releases++;devres_unmaps+=devres_managed;devres_managed=0; }\n'
 'static void dev_set_drvdata(struct device *d,void *v) { d->data=v; }\n'
 'static void klist_remove(int *n) { (void)n; }\n'
 'static void device_pm_check_callbacks(struct device *d) { (void)d; }\n'
 '\n'
 '#define MAX_PSEUDO_ENTRY 1\n'
 '#define DEV2_NAME "eth3"\n'
 '#define FE_TSO 0U\n'
 '#define FE_TSO_V6 0U\n'
 '#define FE_ETHTOOL 0U\n'
 '#define NETIF_F_HW_CSUM 1U\n'
 '#define NETIF_F_IP_CSUM 2U\n'
 '#define NETIF_F_SG 4U\n'
 '#define NETIF_F_TSO 8U\n'
 '#define NETIF_F_TSO6 16U\n'
 '#define NETIF_F_IPV6_CSUM 32U\n'
 'static int gmac2_txq_num=1,virtualif_netdev_ops,ra_virt_ethtool_ops;\n'
 'struct PSEUDO_ADAPTER { struct net_device *pseudo_dev,*raeth_dev; };\n'
 'static struct PSEUDO_ADAPTER pa;\n'
 'static int pseudo_alloc,pseudo_register,alloc_fail,register_fail;\n'
 'static struct net_device *alloc_etherdev_mqs(unsigned long size,int tx,int rx) { '
 'check(size==sizeof(pa)&&tx==1&&rx==1);pseudo_alloc++;if(alloc_fail)return NULL;pseudo_dev.priv=&pa;return '
 '&pseudo_dev; }\n'
 'static void netif_set_real_num_tx_queues(struct net_device *d,int n) { (void)d;check(n==1); }\n'
 'static void netif_set_real_num_rx_queues(struct net_device *d,int n) { (void)d;check(n==1); }\n'
 'static void ei_mac2_addr_setting(struct net_device *d) { (void)d; }\n'
 'static void set_mac2_address(unsigned char *a) { (void)a; }\n'
 'static void ether_setup(struct net_device *d) { (void)d; }\n'
 'static void ethtool_virt_init(struct net_device *d) { (void)d; }\n'
 'static int register_netdev(struct net_device *d) { pseudo_register++;if(register_fail)return '
 '-12;d->reg_state=NETREG_REGISTERED;return 0; }\n' '\n/* Core restart API recorder; old owner/event observations stay unchanged. */\n#define REBOOT_DMA_RAETH (1U << 0)\n#define REBOOT_DMA_MT7615 (1U << 1)\nstatic unsigned int restart_failure_reports;\nstatic void reboot_dma_failure_report(unsigned int reasons) { restart_failure_reports |= reasons; }\n')

SUFFIX = ('\n'
 'static int bus_remove(struct device *d) { check(d==&parent.dev);ret=raether_remove(&parent);return ret; }\n'
 'static void setup(void) {\n'
 ' static struct device_driver driver;\n'
 ' static struct bus_private bp;\n'
 ' static struct bus_type bus;\n'
 ' static struct device_private dp;\n'
 ' '
 'memset(&priv,0,sizeof(priv));memset(&main_dev,0,sizeof(main_dev));memset(&pseudo_dev,0,sizeof(pseudo_dev));\n'
 ' '
 'parent.dev.driver=&driver;parent.dev.bus=&bus;parent.dev.p=&dp;parent.dev.refs=2;parent.dev.data=&main_dev;\n'
 ' bus.remove=bus_remove;bus.p=&bp;\n'
 ' main_dev.priv=&priv;main_dev.refs=1;main_dev.reg_state=NETREG_REGISTERED;strcpy(main_dev.name,"eth2");\n'
 ' pseudo_dev.priv=&priv;pseudo_dev.refs=1;pseudo_dev.reg_state=NETREG_REGISTERED;\n'
 ' dev_raether=&main_dev;priv.pseudo_dev=&pseudo_dev;priv.features=FE_QDMA|FE_INT_TASKLET|FE_GE2_SUPPORT;\n'
 ' priv.dma_stages=FE_DMA_QTX|FE_DMA_PRX;priv.module_reserved=true;module_refs=1;\n'
 ' priv.irq_active=true;priv.irq_requested=BIT(0)|BIT(5);irq_live=2;bh_live=1;\n'
 ' priv.kreset_task=(void*)5;priv.kphy_poll_task=(void*)6;thread_live=2;\n'
 ' priv.clocks_enabled=true;priv.clks[0]=(void*)7;priv.clks[1]=(void*)8;priv.switch_np=(void*)9;\n'
 ' '
 'priv.frame_region_owned=true;priv.frame_start=100;priv.frame_size=4096;priv.parent_ref_held=true;priv.qdma_pdev=&parent;\n'
 ' ethdma_mac_base=(void*)1;ethdma_sysctl_base=(void*)2;ethdma_frame_engine_base=(void*)3;\n'
 ' dma_live=2;book_live=1;proc_live=1;mdio_live=1;last_close=999;\n'
 '}\n'
 'int main(int argc,char **argv) {\n'
 ' if(argc!=2) { return 2; }\n'
 ' const char *name=argv[1];CASE_ADMISSION\n'
 'int first=0;setup();\n'
 ' '
 'if(!strncmp(name,"pseudo-first-",13)){first=1;priv.pseudo_dev=NULL;pseudo_dev.reg_state=0;dma_live=0;book_live=0;irq_live=0;bh_live=0;thread_live=0;module_refs=0;proc_live=0;mdio_live=0;alloc_fail=!strcmp(name,"pseudo-first-oom");register_fail=!strcmp(name,"pseudo-first-register-fail");}\n'
 ' if(!strcmp(name,"pdma-busy"))busy_p=1;\n'
 ' else if(!strcmp(name,"qdma-busy"))busy_q=1;\n'
 ' else if(!strcmp(name,"both-busy")){busy_p=1;busy_q=1;}\n'
 ' else if(!strcmp(name,"quarantined")||!strcmp(name,"repeat-busy"))priv.dma_quarantined=true;\n'
 ' else if(!strcmp(name,"foreign-main"))main_dev.refs=2;\n'
 ' else if(!strcmp(name,"foreign-pseudo"))pseudo_dev.refs=2;\n'
 ' else if(!strcmp(name,"nat-rx"))ra_sw_nat_hook_rx=(void*)1;\n'
 ' else if(!strcmp(name,"nat-tx"))ra_sw_nat_hook_tx=(void*)1;\n'
 ' else if(!strcmp(name,"module-denied")){priv.module_reserved=false;module_refs=0;module_get_ok=0;}\n'
 ' else '
 'if(!strcmp(name,"closed")){priv.module_reserved=false;module_refs=0;priv.irq_active=false;priv.irq_requested=0;irq_live=0;bh_live=0;priv.dma_stages=0;dma_live=0;priv.kreset_task=NULL;priv.kphy_poll_task=NULL;thread_live=0;}\n'
 ' else if(!strcmp(name,"owned-qdma"))priv.qdma_pdev=&qdma;\n'
 ' else if(!strcmp(name,"no-pseudo")){priv.pseudo_dev=NULL;pseudo_dev.reg_state=0;}\n'
 ' else '
 'if(!strcmp(name,"partial-resources")){priv.clocks_enabled=false;priv.clks[1]=NULL;priv.switch_np=NULL;ethdma_mac_base=NULL;ethdma_sysctl_base=NULL;priv.frame_region_owned=false;priv.qdma_pdev=NULL;}\n'
 ' else if(!strcmp(name,"driver-remove")){parent.dev.bus=NULL;parent.dev.driver->remove=bus_remove;}\n'
 ' else if(!first&&strcmp(name,"success")&&strcmp(name,"repeat-success")&&strcmp(name,"repeat-busy")){return '
 '3;}\n'
 ' if(first)raeth_init_pseudo(&priv,&main_dev);else __device_release_driver(&parent.dev);\n'
 ' if(!strcmp(name,"repeat-success")||!strcmp(name,"repeat-busy")) { '
 'if(!strcmp(name,"repeat-busy"))check(dev_raether!=NULL);__device_release_driver(&parent.dev);check(raether_remove(&parent)==0); '
 '}\n'
 ' '
 'printf("{\\"ret\\":%d,\\"dma\\":%d,\\"book\\":%d,\\"irq\\":%d,\\"bh\\":%d,\\"threads\\":%d,\\"module\\":%d,\\"unregister\\":%d,\\"free\\":%d,\\"unmap\\":%d,\\"region\\":%d,\\"clock_disable\\":%d,\\"clock_put\\":%d,\\"node_put\\":%d,\\"parent_put\\":%d,\\"qdma_put\\":%d,\\"core\\":%d,\\"devres_unmap\\":%d,\\"global\\":%d,\\"drvdata\\":%d,\\"driver\\":%d,\\"mdio\\":%d,\\"proc\\":%d,\\"close_ret\\":%d,\\"reset\\":%d,\\"delay\\":%d,\\"errors\\":%d,\\"pseudo_alloc\\":%d,\\"pseudo_register\\":%d,\\"pseudo_published\\":%d}\\n",ret,dma_live,book_live,irq_live,bh_live,thread_live,module_refs,unregistered,freed,unmaps,regions,clock_disables,clock_puts,node_puts,parent_puts,qdma_puts,core_releases,devres_unmaps,dev_raether!=NULL,parent.dev.data!=NULL,parent.dev.driver!=NULL,mdio_live,proc_live,last_close,reset_count,delay_us,errors,pseudo_alloc,pseudo_register,priv.pseudo_dev!=NULL);\n'
 ' return 0;\n'
 '}\n')
def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'(?m)^[A-Za-z_][\w \t*]*\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked))
    if len(matches)!=1:raise ValueError('Missing/ambiguous remove body: '+name)
    start=matches[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer('[{}]',masked[opening:]):
        depth+=1 if m.group()=='{'else -1
        if depth==0:return text[start:opening+m.end()]
    raise ValueError('Unterminated remove body: '+name)
def generate_source(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact remove source set required')
    admission='if ('+' && '.join('strcmp(name,\"'+n+'\")'for n in CASE_NAMES)+') return 2;'
    return PREFIX+'\n'+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)
def function_manifest(texts):
    return {n:{'source':k,'full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest(),'execution':'whole-function'}for n,k in FUNCTION_SOURCES.items()}
def source_only_manifest(texts):
    return {n:{'source':k,'full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest(),'execution':'source-only-not-run'}for n,k in SOURCE_ONLY_FUNCTION_SOURCES.items()}
