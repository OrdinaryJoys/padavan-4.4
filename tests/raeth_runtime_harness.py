"""RAETH active K2P runtime model. Hardware, DMA, IRQ, scheduler and TX mapping seams are inert."""
import hashlib
import re
SOURCE_PATHS = {'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
 'pdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_pdma.c',
 'qdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_qdma.c',
 'mac': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/ra_mac.c',
 'header': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.h',
 'config': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raeth_config.h',
 'errno': 'trunk/linux-4.4.x/arch/mips/include/uapi/asm/errno.h'}
FUNCTION_SOURCES = {'fe_pdma_wait_dma_idle': 'pdma',
 'fe_qdma_wait_dma_idle': 'qdma',
 'fe_pdma_rx_dma_init': 'pdma',
 'fe_pdma_rx_dma_deinit': 'pdma',
 'fe_pdma_tx_dma_init': 'pdma',
 'fe_pdma_tx_dma_deinit': 'pdma',
 'fe_qdma_rx_dma_init': 'qdma',
 'fe_qdma_rx_dma_deinit': 'qdma',
 'fe_qdma_tx_dma_init': 'qdma',
 'fe_qdma_tx_dma_deinit': 'qdma',
 'fq_qdma_init': 'qdma',
 'ra2880stop': 'mac',
 'ei_init_qtx_prx': 'raeth',
 'ei_init_dma': 'raeth',
 'ei_deinit_dma': 'raeth',
 'ei_start_dma': 'raeth',
 'ei_stop_dma': 'raeth',
 'fe_request_irq': 'raeth',
 'fe_int_enable': 'raeth',
 'fe_int_disable': 'raeth',
 'ei_open': 'raeth',
 'ei_close': 'raeth',
 'ei_receive': 'raeth',
 'rt2880_eth_recv': 'raeth',
 'fe_dma_rx_cal_idx_init': 'raeth'}
BODY_ORDER = ('fe_pdma_wait_dma_idle',
 'fe_qdma_wait_dma_idle',
 'fe_pdma_rx_dma_deinit',
 'fe_pdma_rx_dma_init',
 'fe_pdma_tx_dma_init',
 'fe_pdma_tx_dma_deinit',
 'fe_qdma_rx_dma_deinit',
 'fe_qdma_rx_dma_init',
 'fe_qdma_tx_dma_deinit',
 'fq_qdma_init',
 'fe_qdma_tx_dma_init',
 'ra2880stop',
 'ei_deinit_dma',
 'fe_dma_rx_cal_idx_init',
 'ei_init_qtx_prx',
 'ei_init_dma',
 'ei_start_dma',
 'ei_stop_dma',
 'fe_request_irq',
 'fe_int_disable',
 'fe_int_enable',
 'ei_open',
 'ei_close',
 'ei_receive',
 'rt2880_eth_recv')
SOURCE_ONLY_FUNCTION_SOURCES = {'raether_remove': 'raeth', 'ei_init_ptx_prx': 'raeth', 'ei_init_qtx_qrx': 'raeth'}
MODEL_VARIANT = {'K2P_MT7621_QTX_PRX_tasklet': True,
 'reduced_rx_desc': 4,
 'reduced_qrx_desc': 3,
 'reduced_tx_desc': 8,
 'HW_LRO_RSS_SFQ_NAPI_disabled': True,
 'scheduler_IRQ_MMIO_DMA_are_inert': True,
 'RTNL_serialization_is_assumed': True,
 'real_hardware_fence_not_proven': True,
 'generic_remove_not_modeled': True,
 'TX_fragment_mapping_helper_is_inert': True,
 'TX_descriptor_constructor_is_inert': True,
 'logical_descriptor_fields_not_hardware_layout': True,
 'rx_packet_delivery_source_only': False,
 'RW_PDMAPTR_FROM_VAR_enabled': True,
 'Linux_MIPS_ETIMEDOUT': 145,
 'CONFIG_RAETH_ESW_CONTROL_enabled_checked_post_init_inert_seam': True}
SOURCE_FRAGMENTS = {'config': ('#define CONFIG_RAETH_RW_PDMAPTR_FROM_VAR',
            '#define CONFIG_RA_NETWORK_TASKLET_BH',
            '#define CONFIG_RAETH_QDMA',
            '/*#define CONFIG_RAETH_QDMATX_QDMARX*/',
            '/*#define CONFIG_HW_SFQ*/',
            '/*#define CONFIG_RAETH_RSS_4RING*/',
            '/*#define CONFIG_RAETH_RSS_2RING*/'),
 'errno': ('#define ETIMEDOUT\t145\t/* Connection timed out */',)}
FIELDS = ('delivered',
 'dropped',
 'ret',
 'second_ret',
 'live',
 'maps',
 'irq_live',
 'module',
 'quarantine',
 'stages',
 'dma_on',
 'queue',
 'schedules',
 'rearms',
 'errors')
CASE_NAMES = ('oom-1',
 'oom-2',
 'oom-3',
 'oom-4',
 'oom-5',
 'oom-6',
 'oom-7',
 'oom-8',
 'oom-9',
 'oom-10',
 'oom-11',
 'oom-12',
 'map-1',
 'map-2',
 'map-3',
 'map-4',
 'map-5',
 'map-6',
 'map-7',
 'irq-1',
 'irq-2',
 'success',
 'close-pbusy',
 'close-qbusy',
 'open-twice',
 'close-twice',
 'reopen',
 'init-pbusy',
 'init-qbusy',
 'tasklet-stopped',
 'tasklet-running',
 'irq-twice',
 'module-denied',
 'rx-oom',
 'rx-map',
 'rx-build',
 'rx-short',
 'rx-long',
 'rx-min',
 'rx-max',
 'pdma-tx-oom',
 'pdma-tx-success',
 'prx-owned',
 'qrx-owned',
 'fq-retry',
 'rx-no-pseudo',
 'rx-zero',
 'quarantine-reopen',
 'quarantine-close',
 'esw-post-eio',
 'esw-post-timeout')
EXPECTED_ROWS = {'oom-1': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-2': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-3': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-4': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-5': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-6': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-7': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-8': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-9': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'oom-10': {'delivered': 0,
            'dropped': 0,
            'ret': -12,
            'second_ret': 0,
            'live': 0,
            'maps': 0,
            'irq_live': 0,
            'module': 0,
            'quarantine': 0,
            'stages': 0,
            'dma_on': 0,
            'queue': 0,
            'schedules': 0,
            'rearms': 0,
            'errors': 0},
 'oom-11': {'delivered': 0,
            'dropped': 0,
            'ret': -12,
            'second_ret': 0,
            'live': 0,
            'maps': 0,
            'irq_live': 0,
            'module': 0,
            'quarantine': 0,
            'stages': 0,
            'dma_on': 0,
            'queue': 0,
            'schedules': 0,
            'rearms': 0,
            'errors': 0},
 'oom-12': {'delivered': 0,
            'dropped': 0,
            'ret': -12,
            'second_ret': 0,
            'live': 0,
            'maps': 0,
            'irq_live': 0,
            'module': 0,
            'quarantine': 0,
            'stages': 0,
            'dma_on': 0,
            'queue': 0,
            'schedules': 0,
            'rearms': 0,
            'errors': 0},
 'map-1': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'map-2': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'map-3': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'map-4': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'map-5': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'map-6': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'map-7': {'delivered': 0,
           'dropped': 0,
           'ret': -12,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'irq-1': {'delivered': 0,
           'dropped': 0,
           'ret': -16,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'irq-2': {'delivered': 0,
           'dropped': 0,
           'ret': -16,
           'second_ret': 0,
           'live': 0,
           'maps': 0,
           'irq_live': 0,
           'module': 0,
           'quarantine': 0,
           'stages': 0,
           'dma_on': 0,
           'queue': 0,
           'schedules': 0,
           'rearms': 0,
           'errors': 0},
 'success': {'delivered': 0,
             'dropped': 0,
             'ret': 0,
             'second_ret': 0,
             'live': 0,
             'maps': 0,
             'irq_live': 0,
             'module': 0,
             'quarantine': 0,
             'stages': 0,
             'dma_on': 0,
             'queue': 0,
             'schedules': 0,
             'rearms': 2,
             'errors': 0},
 'close-pbusy': {'delivered': 0,
                 'dropped': 0,
                 'ret': -145,
                 'second_ret': 0,
                 'live': 12,
                 'maps': 7,
                 'irq_live': 0,
                 'module': 1,
                 'quarantine': 1,
                 'stages': 11,
                 'dma_on': 0,
                 'queue': 0,
                 'schedules': 0,
                 'rearms': 2,
                 'errors': 0},
 'close-qbusy': {'delivered': 0,
                 'dropped': 0,
                 'ret': -145,
                 'second_ret': 0,
                 'live': 12,
                 'maps': 7,
                 'irq_live': 0,
                 'module': 1,
                 'quarantine': 1,
                 'stages': 11,
                 'dma_on': 0,
                 'queue': 0,
                 'schedules': 0,
                 'rearms': 2,
                 'errors': 0},
 'open-twice': {'delivered': 0,
                'dropped': 0,
                'ret': 0,
                'second_ret': -16,
                'live': 12,
                'maps': 7,
                'irq_live': 2,
                'module': 1,
                'quarantine': 0,
                'stages': 11,
                'dma_on': 1,
                'queue': 1,
                'schedules': 0,
                'rearms': 2,
                'errors': 0},
 'close-twice': {'delivered': 0,
                 'dropped': 0,
                 'ret': 0,
                 'second_ret': 0,
                 'live': 0,
                 'maps': 0,
                 'irq_live': 0,
                 'module': 0,
                 'quarantine': 0,
                 'stages': 0,
                 'dma_on': 0,
                 'queue': 0,
                 'schedules': 0,
                 'rearms': 2,
                 'errors': 0},
 'reopen': {'delivered': 0,
            'dropped': 0,
            'ret': 0,
            'second_ret': 0,
            'live': 12,
            'maps': 7,
            'irq_live': 2,
            'module': 1,
            'quarantine': 0,
            'stages': 11,
            'dma_on': 1,
            'queue': 1,
            'schedules': 0,
            'rearms': 4,
            'errors': 0},
 'init-pbusy': {'delivered': 0,
                'dropped': 0,
                'ret': -145,
                'second_ret': 0,
                'live': 0,
                'maps': 0,
                'irq_live': 0,
                'module': 0,
                'quarantine': 0,
                'stages': 0,
                'dma_on': 0,
                'queue': 0,
                'schedules': 0,
                'rearms': 0,
                'errors': 0},
 'init-qbusy': {'delivered': 0,
                'dropped': 0,
                'ret': -145,
                'second_ret': 0,
                'live': 0,
                'maps': 0,
                'irq_live': 0,
                'module': 0,
                'quarantine': 0,
                'stages': 0,
                'dma_on': 0,
                'queue': 0,
                'schedules': 0,
                'rearms': 0,
                'errors': 0},
 'tasklet-stopped': {'delivered': 0,
                     'dropped': 0,
                     'ret': 0,
                     'second_ret': 0,
                     'live': 0,
                     'maps': 0,
                     'irq_live': 0,
                     'module': 0,
                     'quarantine': 0,
                     'stages': 0,
                     'dma_on': 0,
                     'queue': 0,
                     'schedules': 0,
                     'rearms': 2,
                     'errors': 0},
 'tasklet-running': {'delivered': 0,
                     'dropped': 0,
                     'ret': 0,
                     'second_ret': 0,
                     'live': 12,
                     'maps': 7,
                     'irq_live': 2,
                     'module': 1,
                     'quarantine': 0,
                     'stages': 11,
                     'dma_on': 1,
                     'queue': 1,
                     'schedules': 1,
                     'rearms': 2,
                     'errors': 0},
 'irq-twice': {'delivered': 0,
               'dropped': 0,
               'ret': 0,
               'second_ret': -16,
               'live': 12,
               'maps': 7,
               'irq_live': 2,
               'module': 1,
               'quarantine': 0,
               'stages': 11,
               'dma_on': 1,
               'queue': 1,
               'schedules': 0,
               'rearms': 2,
               'errors': 0},
 'module-denied': {'delivered': 0,
                   'dropped': 0,
                   'ret': -1,
                   'second_ret': 0,
                   'live': 0,
                   'maps': 0,
                   'irq_live': 0,
                   'module': 0,
                   'quarantine': 0,
                   'stages': 0,
                   'dma_on': 0,
                   'queue': 0,
                   'schedules': 0,
                   'rearms': 0,
                   'errors': 0},
 'rx-oom': {'delivered': 0,
            'dropped': 1,
            'ret': 2,
            'second_ret': 0,
            'live': 12,
            'maps': 7,
            'irq_live': 2,
            'module': 1,
            'quarantine': 0,
            'stages': 11,
            'dma_on': 1,
            'queue': 1,
            'schedules': 0,
            'rearms': 2,
            'errors': 0},
 'rx-map': {'delivered': 0,
            'dropped': 1,
            'ret': 2,
            'second_ret': 0,
            'live': 12,
            'maps': 7,
            'irq_live': 2,
            'module': 1,
            'quarantine': 0,
            'stages': 11,
            'dma_on': 1,
            'queue': 1,
            'schedules': 0,
            'rearms': 2,
            'errors': 0},
 'rx-build': {'delivered': 0,
              'dropped': 1,
              'ret': 2,
              'second_ret': 0,
              'live': 12,
              'maps': 7,
              'irq_live': 2,
              'module': 1,
              'quarantine': 0,
              'stages': 11,
              'dma_on': 1,
              'queue': 1,
              'schedules': 0,
              'rearms': 2,
              'errors': 0},
 'rx-short': {'delivered': 0,
              'dropped': 1,
              'ret': 2,
              'second_ret': 0,
              'live': 12,
              'maps': 7,
              'irq_live': 2,
              'module': 1,
              'quarantine': 0,
              'stages': 11,
              'dma_on': 1,
              'queue': 1,
              'schedules': 0,
              'rearms': 2,
              'errors': 0},
 'rx-long': {'delivered': 0,
             'dropped': 1,
             'ret': 2,
             'second_ret': 0,
             'live': 12,
             'maps': 7,
             'irq_live': 2,
             'module': 1,
             'quarantine': 0,
             'stages': 11,
             'dma_on': 1,
             'queue': 1,
             'schedules': 0,
             'rearms': 2,
             'errors': 0},
 'rx-min': {'delivered': 1,
            'dropped': 0,
            'ret': 2,
            'second_ret': 0,
            'live': 12,
            'maps': 7,
            'irq_live': 2,
            'module': 1,
            'quarantine': 0,
            'stages': 11,
            'dma_on': 1,
            'queue': 1,
            'schedules': 0,
            'rearms': 2,
            'errors': 0},
 'rx-max': {'delivered': 1,
            'dropped': 0,
            'ret': 2,
            'second_ret': 0,
            'live': 12,
            'maps': 7,
            'irq_live': 2,
            'module': 1,
            'quarantine': 0,
            'stages': 11,
            'dma_on': 1,
            'queue': 1,
            'schedules': 0,
            'rearms': 2,
            'errors': 0},
 'pdma-tx-oom': {'delivered': 0,
                 'dropped': 0,
                 'ret': -12,
                 'second_ret': 0,
                 'live': 0,
                 'maps': 0,
                 'irq_live': 0,
                 'module': 0,
                 'quarantine': 0,
                 'stages': 0,
                 'dma_on': 0,
                 'queue': 0,
                 'schedules': 0,
                 'rearms': 0,
                 'errors': 0},
 'pdma-tx-success': {'delivered': 0,
                     'dropped': 0,
                     'ret': 0,
                     'second_ret': 0,
                     'live': 0,
                     'maps': 0,
                     'irq_live': 0,
                     'module': 0,
                     'quarantine': 0,
                     'stages': 0,
                     'dma_on': 0,
                     'queue': 0,
                     'schedules': 0,
                     'rearms': 0,
                     'errors': 0},
 'prx-owned': {'delivered': 0,
               'dropped': 0,
               'ret': 0,
               'second_ret': -16,
               'live': 12,
               'maps': 7,
               'irq_live': 2,
               'module': 1,
               'quarantine': 0,
               'stages': 11,
               'dma_on': 1,
               'queue': 1,
               'schedules': 0,
               'rearms': 2,
               'errors': 0},
 'qrx-owned': {'delivered': 0,
               'dropped': 0,
               'ret': 0,
               'second_ret': -16,
               'live': 12,
               'maps': 7,
               'irq_live': 2,
               'module': 1,
               'quarantine': 0,
               'stages': 11,
               'dma_on': 1,
               'queue': 1,
               'schedules': 0,
               'rearms': 2,
               'errors': 0},
 'fq-retry': {'delivered': 0,
              'dropped': 0,
              'ret': -12,
              'second_ret': 0,
              'live': 12,
              'maps': 7,
              'irq_live': 2,
              'module': 1,
              'quarantine': 0,
              'stages': 11,
              'dma_on': 1,
              'queue': 1,
              'schedules': 0,
              'rearms': 2,
              'errors': 0},
 'rx-no-pseudo': {'delivered': 0,
                  'dropped': 1,
                  'ret': 2,
                  'second_ret': 0,
                  'live': 12,
                  'maps': 7,
                  'irq_live': 2,
                  'module': 1,
                  'quarantine': 0,
                  'stages': 11,
                  'dma_on': 1,
                  'queue': 1,
                  'schedules': 0,
                  'rearms': 2,
                  'errors': 0},
 'rx-zero': {'delivered': 0,
             'dropped': 1,
             'ret': 2,
             'second_ret': 0,
             'live': 12,
             'maps': 7,
             'irq_live': 2,
             'module': 1,
             'quarantine': 0,
             'stages': 11,
             'dma_on': 1,
             'queue': 1,
             'schedules': 0,
             'rearms': 2,
             'errors': 0},
 'quarantine-reopen': {'delivered': 0,
                       'dropped': 0,
                       'ret': -145,
                       'second_ret': -16,
                       'live': 12,
                       'maps': 7,
                       'irq_live': 0,
                       'module': 1,
                       'quarantine': 1,
                       'stages': 11,
                       'dma_on': 0,
                       'queue': 0,
                       'schedules': 0,
                       'rearms': 2,
                       'errors': 0},
 'quarantine-close': {'delivered': 0,
                      'dropped': 0,
                      'ret': -145,
                      'second_ret': -16,
                      'live': 12,
                      'maps': 7,
                      'irq_live': 0,
                      'module': 1,
                      'quarantine': 1,
                      'stages': 11,
                      'dma_on': 0,
                      'queue': 0,
                      'schedules': 0,
                      'rearms': 2,
                      'errors': 0},
 'esw-post-eio': {'delivered': 0,
                  'dropped': 0,
                  'ret': -5,
                  'second_ret': 0,
                  'live': 0,
                  'maps': 0,
                  'irq_live': 0,
                  'module': 0,
                  'quarantine': 0,
                  'stages': 0,
                  'dma_on': 0,
                  'queue': 0,
                  'schedules': 0,
                  'rearms': 0,
                  'errors': 0},
 'esw-post-timeout': {'delivered': 0,
                      'dropped': 0,
                      'ret': -145,
                      'second_ret': 0,
                      'live': 0,
                      'maps': 0,
                      'irq_live': 0,
                      'module': 0,
                      'quarantine': 0,
                      'stages': 0,
                      'dma_on': 0,
                      'queue': 0,
                      'schedules': 0,
                      'rearms': 0,
                      'errors': 0}}
FUNCTION_DECLARATIONS = ''
PREFIX = ('/* Inert seams include optional-profile stubs and production signed loop indices. */\n'
 '#pragma GCC diagnostic ignored "-Wunused-function"\n'
 '#pragma GCC diagnostic ignored "-Wunused-variable"\n'
 '#pragma GCC diagnostic ignored "-Wunused-parameter"\n'
 '#pragma GCC diagnostic ignored "-Wsign-compare"\n'
 '#pragma GCC diagnostic ignored "-Wmisleading-indentation"\n'
 '#include <stdbool.h>\n'
 '#include <stdint.h>\n'
 '#include <stdio.h>\n'
 '#include <stdlib.h>\n'
 '#include <string.h>\n'
 '#include <errno.h>\n'
 '#undef ETIMEDOUT\n'
 '#define ETIMEDOUT 145\n'
 '#define BIT(n) (1U<<(n))\n'
 '#define GFP_KERNEL 0\n'
 '#define GFP_ATOMIC 0\n'
 '#define __GFP_ZERO 0\n'
 '#define DMA_FROM_DEVICE 1\n'
 '#define MAX_RX_LENGTH 1536\n'
 '#define NET_IP_ALIGN 2\n'
 '#define NET_SKB_PAD 32\n'
 '#define SKB_DATA_ALIGN(n) (n)\n'
 '#define CONFIG_RAETH_RW_PDMAPTR_FROM_VAR\n'
 '#define NUM_QRX_DESC 3\n'
 '#define NUM_QDMA_PAGE 4\n'
 '#define QDMA_PAGE_SIZE 64\n'
 '#define QTXD_LEN sizeof(struct QDMA_txdesc)\n'
 '#define FE_DMA_PRX BIT(0)\n'
 '#define FE_DMA_QRX BIT(1)\n'
 '#define FE_DMA_PTX BIT(2)\n'
 '#define FE_DMA_QTX BIT(3)\n'
 '#define FE_DMA_EXTRA_RX BIT(4)\n'
 '#define FE_QDMA BIT(4)\n'
 '#define FE_QDMA_TX BIT(16)\n'
 '#define FE_INT_TASKLET BIT(7)\n'
 '#define FE_GE2_SUPPORT BIT(9)\n'
 '#define FE_DLY_INT BIT(0)\n'
 '#define FE_HW_VLAN_RX BIT(15)\n'
 '#define MT7621_FE 1\n'
 '#define MT7622_FE 2\n'
 '#define MT7623_FE 3\n'
 '#define LEOPARD_FE 4\n'
 '#define GE1_SGMII_AN BIT(0)\n'
 '#define GE2_SGMII_AN BIT(1)\n'
 '#define GE2_RGMII_AN BIT(2)\n'
 '#define LEOPARD_EPHY_GMII BIT(3)\n'
 '#define RAETH_ESW BIT(4)\n'
 '#define RX_DMA_EN BIT(2)\n'
 '#define TX_DMA_EN BIT(0)\n'
 '#define TX_WB_DDONE BIT(6)\n'
 '#define RX_DMA_BUSY BIT(3)\n'
 '#define TX_DMA_BUSY BIT(1)\n'
 '#define THIS_MODULE NULL\n'
 '#define RAETH_VERSION "model"\n'
 '#define MT_TRIGGER_LOW 0\n'
 '#define NUM_RX_MAX_PROCESS 16\n'
 '#define IS_ERR(p) ((intptr_t)(p)<0 && (intptr_t)(p)>-4096)\n'
 '#define PTR_ERR(p) ((int)(intptr_t)(p))\n'
 '#define likely(x) (x)\n'
 '#define unlikely(x) (x)\n'
 '#define READ_ONCE(x) (x)\n'
 '#define WRITE_ONCE(x,v) ((x)=(v))\n'
 '#define pr_err(...) do {} while(0)\n'
 '#define pr_info(...) do {} while(0)\n'
 '#define pr_warn(...) do {} while(0)\n'
 '#define pr_debug(...) do {} while(0)\n'
 '#define spin_lock_irqsave(lock,flags) do { (void)(lock); (flags)=0; } while(0)\n'
 '#define spin_unlock_irqrestore(lock,flags) do { (void)(lock); (void)(flags); } while(0)\n'
 '#define INIT_WORK(w,f) do { (void)(w); (void)(f); } while(0)\n'
 '#define SET_PDMA_LRO_RXD_PREFETCH_EN(x) do { (void)(x); } while(0)\n'
 '#define phys_to_bus(x) (x)\n'
 '#define cpu_to_le32(x) (x)\n'
 'typedef uint32_t dma_addr_t;\n'
 'typedef uint32_t u32;\n'
 'typedef int (*irq_handler_t)(int, void *);\n'
 'struct device { struct device *parent; };\n'
 'struct device_node { int unused; };\n'
 'struct platform_device { struct device dev; };\n'
 'struct mtk_gsw { unsigned int irq; };\n'
 'struct napi_struct {int unused;};\n'
 'struct skb_shared_info { unsigned int unused; };\n'
 'struct net_device;\n'
 'struct sk_buff { unsigned char *head,*data;struct net_device *dev;unsigned int '
 'protocol,ip_summed,pkt_type,len,alg,magic; };\n'
 'struct net_device_stats {unsigned int rx_packets,rx_bytes,rx_dropped;};\n'
 'struct PSEUDO_ADAPTER {struct net_device_stats stat;};\n'
 'struct PDMA_rxdesc { struct {u32 PDP0;} rxd_info1; struct {u32 DDONE_bit,LS0,PLEN0,TAG;} rxd_info2;struct '
 '{u32 VID;} rxd_info3;struct {u32 SP,L4VLD;} rxd_info4; };\n'
 'struct PDMA_txdesc { struct {u32 LS0_bit,DDONE_bit;} txd_info2; };\n'
 'struct QDMA_txdesc {struct {u32 SDP;} txd_info1;struct {u32 NDP;} txd_info2;struct {u32 SDL;} '
 'txd_info3;};\n'
 'struct END_DEVICE;\n'
 'struct net_device { struct device dev; char name[8]; unsigned char dev_addr[6]; void *priv; };\n'
 'struct END_DEVICE {\n'
 ' struct platform_device *qdma_pdev; struct device_node *switch_np;\n'
 ' struct PDMA_rxdesc *rx_ring[4],*qrx_ring; struct PDMA_txdesc *tx_ring0;\n'
 ' struct QDMA_txdesc *txd_pool,*free_head; unsigned int *free_page_head; void *qtx_mapping;\n'
 ' dma_addr_t phy_rx_ring[4],phy_qrx_ring,phy_tx_ring0,phy_txd_pool,phy_free_page_head;\n'
 ' unsigned int phy_free_head,prx_mapped,qrx_mapped,dma_stages,features,architecture,chip_name;\n'
 ' unsigned int tx_ring_full,free_idx,irq_requested,switch_irq,irq0,irq1,irq2,irq3,esw_irq,tx_mask,rx_mask;\n'
 ' unsigned int fe_rx_int_enable,rx_calc_idx[4],tx_cpu_owner_idx0; bool '
 'irq_active,dma_quarantined,module_reserved;\n'
 ' void *netrx_skb_data_storage[4][4],*netrx0_storage[3]; void **netrx_skb_data[4],**netrx0_skb_data;\n'
 ' struct sk_buff *skb_free[8]; struct net_device *pseudo_dev;\n'
 ' int irq_lock,rx_wq,rx_tasklet,napi_tx,napi_rx,napi,napi_rx_rss0,napi_rx_rss1,napi_rx_rss2,napi_rx_rss3;\n'
 ' void *kreset_task,*kphy_poll_task; char lan_ip4_addr[16];\n'
 ' struct net_device_stats stat;int lro_mgr;\n'
 ' int (*ei_eth_recv)(struct net_device *,void *,int);\n'
 '};\n'
 'static struct END_DEVICE adapter;\n'
 'static struct net_device main_dev,pseudo_dev;\n'
 'static struct PSEUDO_ADAPTER pseudo_adapter;\n'
 'static unsigned int fail_build,delivered;\n'
 'static int lro_flush_needed;\n'
 'static struct platform_device qdev;\n'
 'static struct device parent;\n'
 'static struct net_device *dev_raether=&main_dev;\n'
 'static struct QDMA_txdesc *free_head;\n'
 'static unsigned int num_rx_desc=4,num_tx_desc=8,gmac1_txd_num=4,gmac2_txd_num=4;\n'
 'static int mac_to_gigaphy_mode_addr2;\n'
 'static void *owners[128];\n'
 'static unsigned int '
 'owner_count,alloc_calls,fail_alloc,mapping_calls,fail_map,live_maps,irq_calls,fail_irq,irq_live,module_refs,fail_module,delays,pbusy,qbusy,queue_started,schedules,rearms,errors,reset_calls;\n'
 'static unsigned int regfile[256];\n'
 'static void *irq_data[32]; static bool irq_owned[32],mapped[128];\n'
 'static void *netdev_priv(struct net_device *dev) { return dev->priv; }\n'
 'static void *alloc_owner(size_t size) { if (++alloc_calls==fail_alloc)return NULL;void '
 '*p=calloc(1,size);if(!p)abort();owners[owner_count++]=p;return p; }\n'
 'static void free_owner(void *p) { if(!p)return;for(unsigned int '
 'i=0;i<owner_count;i++)if(owners[i]==p){free(p);owners[i]=NULL;return;}errors++; }\n'
 'static void *dma_alloc_coherent(struct device *d,size_t n,dma_addr_t *a,int f) { (void)d;(void)f;void '
 '*p=alloc_owner(n);*a=p ? 0x1000U+alloc_calls*256U : 0;return p; }\n'
 'static void dma_free_coherent(struct device *d,size_t n,void *p,dma_addr_t a) { '
 '(void)d;(void)n;(void)a;free_owner(p); }\n'
 'static void *raeth_alloc_skb_data(size_t n,int f) { (void)f;return alloc_owner(n); }\n'
 'static void raeth_free_skb_data(void *p) { free_owner(p); }\n'
 'static dma_addr_t dma_map_single(struct device *d,void *p,size_t n,int dir) { '
 '(void)d;(void)p;(void)dir;if(n!=MAX_RX_LENGTH)errors++;if(++mapping_calls==fail_map)return '
 'UINT32_MAX;mapped[mapping_calls]=true;live_maps++;return mapping_calls; }\n'
 'static int dma_mapping_error(struct device *d,dma_addr_t a) {(void)d;return a==UINT32_MAX;}\n'
 'static void dma_unmap_single(struct device *d,dma_addr_t a,size_t n,int dir) { '
 '(void)d;(void)dir;if(n!=MAX_RX_LENGTH||a>=128||!mapped[a]){errors++;return;}mapped[a]=false;live_maps--; '
 '}\n'
 'static void dev_kfree_skb_any(struct sk_buff *p) {free_owner(p);}\n'
 'static void kfree(void *p) {free_owner(p);}\n'
 'static void udelay(unsigned int n) {if(n!=10)errors++;delays++;}\n'
 'static int dummy_irq(int irq,void *data) {(void)irq;(void)data;return 0;}\n'
 'static int request_irq(unsigned int irq,irq_handler_t h,unsigned long f,const char *name,void *data) { '
 '(void)h;(void)f;(void)name;if(++irq_calls==fail_irq)return '
 '-EBUSY;if(irq>=32||irq_owned[irq]){errors++;return '
 '-EBUSY;}irq_owned[irq]=true;irq_data[irq]=data;irq_live++;return 0; }\n'
 'static int request_threaded_irq(unsigned int irq,irq_handler_t h,void *t,unsigned long f,const char '
 '*n,void *data) {(void)t;return request_irq(irq,h,f,n,data);}\n'
 'static void free_irq(unsigned int irq,void *data) '
 '{if(irq>=32||!irq_owned[irq]||irq_data[irq]!=data){errors++;return;}irq_owned[irq]=false;irq_live--;}\n'
 'static int try_module_get(void *m) {(void)m;if(fail_module)return 0;module_refs++;return 1;}\n'
 'static void module_put(void *m) {(void)m;if(!module_refs)errors++;else module_refs--;}\n'
 'static void tasklet_init(int *t,void (*f)(unsigned long),unsigned long n) {(void)f;(void)n;*t=1;}\n'
 'static void tasklet_kill(int *t) {if(!*t)errors++;*t=0;}\n'
 'static void tasklet_schedule(int *t) {(void)t;schedules++;}\n'
 'static void tasklet_hi_schedule(int *t) {tasklet_schedule(t);}\n'
 'static void schedule_work(int *w) {(void)w;schedules++;}\n'
 'static void cancel_work_sync(int *w) {(void)w;}\n'
 'static void napi_enable(int *n) {(void)n;}\n'
 'static void napi_disable(int *n) {(void)n;}\n'
 'static void ei_receive_tasklet(unsigned long n) {(void)n;}\n'
 'static void ei_receive_workq(int *w) {(void)w;}\n'
 'static void *kthread_create(int (*f)(void *),void *d,const char *n) {(void)f;(void)d;(void)n;return (void '
 '*)1;}\n'
 'static void wake_up_process(void *p) {(void)p;}\n'
 'static void kthread_stop(void *p) {(void)p;}\n'
 'static int fe_reset_thread(void *d) {(void)d;return 0;}\n'
 'static int phy_polling_thread(void *d) {(void)d;return 0;}\n'
 'static void netif_start_queue(struct net_device *d) {(void)d;queue_started=1;}\n'
 'static void netif_tx_disable(struct net_device *d) {if(d==&main_dev)queue_started=0;}\n'
 'static void virtualif_close(struct net_device *d) {(void)d;}\n'
 'static void ei_reset_statistics(struct END_DEVICE *e) {(void)e;}\n'
 'static void fe_reset(void) {reset_calls++;}\n'
 'static void fe_gmac_reset(void) {}\n'
 'static void fe_sw_init(void) {}\n'
 'static void fe_sw_preinit(struct END_DEVICE *e) {(void)e;}\n'
 'static void fe_sw_deinit(struct END_DEVICE *e) {(void)e;}\n'
 'static void fe_set_sw_lro_my_ip(char *ip) {(void)ip;}\n'
 'static int forward_config(struct net_device *d) {(void)d;return 0;}\n'
 'static void set_mac_address(unsigned char *a) {(void)a;}\n'
 'static void mii_mgr_write(unsigned int a,unsigned int b,unsigned int c) {(void)a;(void)b;(void)c;}\n'
 'static void mii_mgr_write_cl45(unsigned int a,unsigned int b,unsigned int c,unsigned int d) '
 '{(void)a;(void)b;(void)c;(void)d;}\n'
 'static struct platform_device *of_find_device_by_node(struct device_node *n) {(void)n;return &qdev;}\n'
 'static struct mtk_gsw *platform_get_drvdata(struct platform_device *d) {static struct mtk_gsw '
 'g={6};(void)d;return &g;}\n'
 'static void put_device(struct device *d) {(void)d;}\n'
 'static int sfq_init(struct net_device *d) {(void)d;abort();}\n'
 'static int fe_hw_lro_init(struct net_device *d) {(void)d;abort();}\n'
 'static int fe_rss_4ring_init(struct net_device *d) {(void)d;abort();}\n'
 'static int fe_rss_2ring_init(struct net_device *d) {(void)d;abort();}\n'
 'static void fe_hw_lro_deinit(struct net_device *d) {(void)d;abort();}\n'
 'static void fe_rss_4ring_deinit(struct net_device *d) {(void)d;abort();}\n'
 'static void fe_rss_2ring_deinit(struct net_device *d) {(void)d;abort();}\n'
 'static int ei_init_ptx_prx(struct net_device *d) {(void)d;abort();}\n'
 'static int ei_init_qtx_qrx(struct net_device *d) {(void)d;abort();}\n'
 'static bool qdma_tx_desc_alloc(void) '
 '{adapter.txd_pool=dma_alloc_coherent(&qdev.dev,num_tx_desc*QTXD_LEN,&adapter.phy_txd_pool,0);return '
 'adapter.txd_pool!=NULL;}\n'
 'static void fe_qdma_tx_unmap(struct END_DEVICE *e,unsigned int i) {(void)e;(void)i;}\n'
 'static int fe_int_disable(struct net_device *dev);\n'
 'static void ei_deinit_dma(struct net_device *dev);\n'
 '\n'
 '#define ETH_HLEN 14\n'
 '#define ETH_P_8021Q 0x8100\n'
 '#define CHECKSUM_UNNECESSARY 1\n'
 '#define CHECKSUM_NONE 0\n'
 '#define PACKET_HOST 0\n'
 '#define HNAT_MAGIC_TAG 0\n'
 '#define HIT_BIND_FORCE_TO_CPU 1\n'
 '#define skb_hnat_alg(skb) ((skb)->alg)\n'
 '#define skb_hnat_magic_tag(skb) ((skb)->magic)\n'
 '#define skb_hnat_reason(skb) 0\n'
 '#define prefetch(p) do {(void)(p);}while(0)\n'
 '#define wmb() do {}while(0)\n'
 '#define dma_rmb() do {}while(0)\n'
 '#undef htons\n'
 '#define htons(x) (x)\n'
 'static struct sk_buff *raeth_build_skb(void *p,unsigned int n) {(void)n;if(fail_build)return NULL;struct '
 'sk_buff *s=alloc_owner(sizeof(*s));s->head=p;s->data=p;return s;}\n'
 'static void skb_reserve(struct sk_buff *s,unsigned int n) {s->data+=n;}\n'
 'static void skb_put(struct sk_buff *s,unsigned int n) {if(n>MAX_RX_LENGTH)errors++;s->len=n;}\n'
 'static unsigned int eth_type_trans(struct sk_buff *s,struct net_device *d) {(void)s;(void)d;return 0;}\n'
 'static void __vlan_hwaccel_put_tag(struct sk_buff *s,unsigned int a,unsigned int b) '
 '{(void)s;(void)a;(void)b;}\n'
 'static void netif_rx(struct sk_buff *s) {delivered++;free_owner(s->head);free_owner(s);}\n'
 'static void netif_receive_skb(struct sk_buff *s) {netif_rx(s);}\n'
 'static void lro_receive_skb(int *mgr,struct sk_buff *s,void *n) {(void)mgr;(void)n;netif_rx(s);}\n'
 'static void ei_lro_flush_all(int *mgr) {(void)mgr;}\n'
 'static void fe_rx_desc_init(struct PDMA_rxdesc *r,dma_addr_t a) '
 '{r->rxd_info1.PDP0=a;r->rxd_info2.DDONE_bit=0;}\n'
 '#define ADMA_LRO_CTRL_DW0 32\n'
 '#define ADMA_MULTI_RXD_PREFETCH_EN 33\n'
 '#define ADMA_RXD_PREFETCH_EN 34\n'
 '#define DELAY_INT_INIT 35\n'
 '#define FE_HW_LRO 0\n'
 '#define FE_HW_SFQ 0\n'
 '#define FE_INT_ENABLE2 38\n'
 '#define FE_INT_GRP 39\n'
 '#define FE_INT_NAPI 0\n'
 '#define FE_INT_NAPI_RX_ONLY 0\n'
 '#define FE_INT_NAPI_TX_RX 0\n'
 '#define FE_INT_WORKQ 0\n'
 '#define FE_IRQ_SEPARATE 0\n'
 '#define FE_QDMA_RX 0\n'
 '#define FE_RSS_2RING 0\n'
 '#define FE_RSS_4RING 0\n'
 '#define FE_SW_LRO 0\n'
 '#define FOE_ALG_HEAD 49\n'
 '#define FOE_ALG_TAIL 50\n'
 '#define FOE_INFO_START_ADDR_HEAD 51\n'
 '#define FOE_INFO_START_ADDR_TAIL 52\n'
 '#define FOE_MAGIC_GE 53\n'
 '#define FOE_MAGIC_TAG_HEAD 54\n'
 '#define FOE_MAGIC_TAG_TAIL 55\n'
 '#define FOE_TAG_PROTECT_HEAD 56\n'
 '#define FOE_TAG_PROTECT_TAIL 57\n'
 '#define IS_SPACE_AVAILABLE_HEAD 58\n'
 '#define IS_SPACE_AVAILABLE_TAIL 59\n'
 '#define LRO_RX1_DLY_INT 60\n'
 '#define LRO_RX2_DLY_INT 61\n'
 '#define LRO_RX3_DLY_INT 62\n'
 '#define MAC1_LINK 63\n'
 '#define MAC2_LINK 64\n'
 '#define PDMA_GLO_CFG 65\n'
 '#define PDMA_INT_GRP1 66\n'
 '#define PDMA_INT_GRP2 67\n'
 '#define PDMA_INT_GRP3 68\n'
 '#define PDMA_LRO_DLY_INT_EN 69\n'
 '#define PDMA_RST_CFG 70\n'
 '#define PST_DRX_IDX0 71\n'
 '#define PST_DTX_IDX0 72\n'
 '#define QDMA_DELAY_INT 73\n'
 '#define QDMA_FQ_BLEN 74\n'
 '#define QDMA_FQ_CNT 75\n'
 '#define QDMA_FQ_HEAD 76\n'
 '#define QDMA_FQ_TAIL 77\n'
 '#define QDMA_GLO_CFG 78\n'
 '#define QDMA_INT_GRP1 79\n'
 '#define QDMA_INT_GRP2 80\n'
 '#define QDMA_RST_CFG 81\n'
 '#define QFE_INT_ALL 82\n'
 '#define QFE_INT_DLY_INIT 83\n'
 '#define QFE_INT_ENABLE 84\n'
 '#define QRX_BASE_PTR_0 85\n'
 '#define QRX_CRX_IDX_0 86\n'
 '#define QRX_MAX_CNT_0 87\n'
 '#define RAETH_DLY_INT_CFG 88\n'
 '#define RAETH_FE_INT_ALL 89\n'
 '#define RAETH_FE_INT_DLY_INIT 90\n'
 '#define RAETH_FE_INT_ENABLE 91\n'
 '#define RAETH_RX_CALC_IDX0 92\n'
 '#define RING0_RX_DLY_INT 93\n'
 '#define RING1_RX_DLY_INT 94\n'
 '#define RING2_RX_DLY_INT 95\n'
 '#define RING3_RX_DLY_INT 96\n'
 '#define RLS_DLY_INT 97\n'
 '#define RLS_DONE_INT 98\n'
 '#define RSS_INT_DLY_INT 99\n'
 '#define RSS_INT_DLY_INT_2RING 100\n'
 '#define RSS_RX_DLY_INT 101\n'
 '#define RSS_RX_DLY_INT0 102\n'
 '#define RX_BASE_PTR0 103\n'
 '#define RX_CALC_IDX0 104\n'
 '#define RX_CALC_IDX1 105\n'
 '#define RX_CALC_IDX2 106\n'
 '#define RX_CALC_IDX3 107\n'
 '#define RX_DLY_INT 108\n'
 '#define RX_DONE_INT0 109\n'
 '#define RX_DONE_INT1 110\n'
 '#define RX_DONE_INT2 111\n'
 '#define RX_DONE_INT3 112\n'
 '#define RX_MAX_CNT0 113\n'
 '#define TAG_PROTECT 114\n'
 '#define TX_BASE_PTR0 115\n'
 '#define TX_CTX_IDX0 116\n'
 '#define TX_DLY_INT 117\n'
 '#define TX_DONE_INT0 118\n'
 '#define TX_MAX_CNT0 119\n'
 '#define ei_fe_interrupt dummy_irq\n'
 '#define ei_interrupt dummy_irq\n'
 '#define ei_interrupt_napi dummy_irq\n'
 '#define ei_interrupt_napi_rx_only dummy_irq\n'
 '#define ei_interrupt_napi_sep dummy_irq\n'
 '#define ei_rx_interrupt dummy_irq\n'
 '#define ei_rx_interrupt_napi dummy_irq\n'
 '#define ei_rx_interrupt_napi_g0 dummy_irq\n'
 '#define ei_rx_interrupt_napi_g1 dummy_irq\n'
 '#define ei_rx_interrupt_napi_rss0 dummy_irq\n'
 '#define ei_rx_interrupt_napi_rss1 dummy_irq\n'
 '#define ei_rx_interrupt_napi_sep dummy_irq\n'
 '#define ei_tx_interrupt dummy_irq\n'
 '#define ei_tx_interrupt_napi dummy_irq\n'
 '#define ei_tx_interrupt_napi_sep dummy_irq\n'
 '#define esw_interrupt dummy_irq\n'
 '#define gsw_interrupt dummy_irq\n'
 '#define DMA_GLO_CFG PDMA_GLO_CFG\n'
 'static unsigned int sys_reg_read(unsigned int r) {if(r==PDMA_GLO_CFG&&pbusy)return '
 'regfile[r]|RX_DMA_BUSY;if(r==QDMA_GLO_CFG&&qbusy)return regfile[r]|TX_DMA_BUSY;return regfile[r];}\n'
 'static void sys_reg_write(unsigned int r,unsigned int value) '
 '{regfile[r]=value;if((r==RAETH_FE_INT_ENABLE||r==QFE_INT_ENABLE)&&value)rearms++;}\n'
 'static void set_fe_pdma_glo_cfg(void) {sys_reg_write(PDMA_GLO_CFG,TX_DMA_EN|RX_DMA_EN);}\n'
 'static void set_fe_qdma_glo_cfg(void) {sys_reg_write(QDMA_GLO_CFG,TX_DMA_EN|RX_DMA_EN);}\n'
 'static int receive_stub(struct net_device *d,void *n,int b) {(void)d;(void)n;(void)b;return 17;}\n'
 '\n'
 '#define CONFIG_RAETH_ESW_CONTROL 1\n'
 'static int fail_esw_post;\n'
 'static int esw_ioctl_init_post(void) { return fail_esw_post; }\n')
SUFFIX = ('\n'
 'int main(int argc,char **argv) {\n'
 ' if(argc!=2)return 2;const char *name=argv[1];CASE_ADMISSION\n'
 ' '
 'main_dev.priv=&adapter;main_dev.dev.parent=&parent;strcpy(main_dev.name,"eth2");pseudo_dev.priv=&pseudo_adapter;\n'
 ' '
 'adapter.qdma_pdev=&qdev;adapter.pseudo_dev=&pseudo_dev;adapter.features=FE_QDMA|FE_QDMA_TX|FE_INT_TASKLET|FE_GE2_SUPPORT|FE_DLY_INT;adapter.chip_name=MT7621_FE;\n'
 ' '
 'adapter.irq0=1;adapter.irq1=2;adapter.irq2=3;adapter.irq3=4;adapter.esw_irq=5;adapter.fe_rx_int_enable=RAETH_FE_INT_ENABLE;adapter.ei_eth_recv=receive_stub;\n'
 ' for(unsigned int '
 'i=0;i<4;i++)adapter.netrx_skb_data[i]=adapter.netrx_skb_data_storage[i];adapter.netrx0_skb_data=adapter.netrx0_storage;\n'
 ' if(sscanf(name,"oom-%u",&fail_alloc)!=1)fail_alloc=0;\n'
 ' if(sscanf(name,"map-%u",&fail_map)!=1)fail_map=0;\n'
 ' if(sscanf(name,"irq-%u",&fail_irq)!=1)fail_irq=0;\n'
 ' '
 'if(!strcmp(name,"init-pbusy"))pbusy=1;if(!strcmp(name,"init-qbusy"))qbusy=1;if(!strcmp(name,"module-denied"))fail_module=1;\n'
 ' if(!strcmp(name,"esw-post-eio"))fail_esw_post=-5;\n'
 ' if(!strcmp(name,"esw-post-timeout"))fail_esw_post=-145;\n'
 ' int ret,second=0;\n'
 ' if(!strcmp(name,"pdma-tx-oom")||!strcmp(name,"pdma-tx-success")) {\n'
 '  if(!strcmp(name,"pdma-tx-oom"))fail_alloc=1;\n'
 '  ret=fe_pdma_tx_dma_init(&main_dev);\n'
 '  if(!ret){adapter.skb_free[0]=alloc_owner(sizeof(struct sk_buff));adapter.skb_free[1]=(struct sk_buff '
 '*)0xffffffff;fe_pdma_tx_dma_deinit(&main_dev);fe_pdma_tx_dma_deinit(&main_dev);}\n'
 ' } else {if(!strcmp(name,"fq-retry"))fail_alloc=12;ret=ei_open(&main_dev);}\n'
 ' if(!strcmp(name,"fq-retry")){fail_alloc=0;second=ei_open(&main_dev);}\n'
 ' if(!ret) {\n'
 '  if(!strncmp(name,"pdma-tx-",8)) {}\n'
 '  else if(!strncmp(name,"rx-",3)) {\n'
 '   adapter.rx_ring[0][0].rxd_info2.DDONE_bit=1;adapter.rx_ring[0][0].rxd_info2.PLEN0=64;\n'
 '   if(!strcmp(name,"rx-no-pseudo")){adapter.pseudo_dev=NULL;adapter.rx_ring[0][0].rxd_info4.SP=2;}\n'
 '   if(!strcmp(name,"rx-zero"))adapter.rx_ring[0][0].rxd_info2.PLEN0=0;\n'
 '   regfile[RAETH_RX_CALC_IDX0]=num_rx_desc-1;\n'
 '   if(!strcmp(name,"rx-oom"))fail_alloc=alloc_calls+1;\n'
 '   if(!strcmp(name,"rx-map"))fail_map=mapping_calls+1;\n'
 '   if(!strcmp(name,"rx-build"))fail_build=1;\n'
 '   if(!strcmp(name,"rx-short"))adapter.rx_ring[0][0].rxd_info2.PLEN0=13;\n'
 '   if(!strcmp(name,"rx-long"))adapter.rx_ring[0][0].rxd_info2.PLEN0=MAX_RX_LENGTH+1;\n'
 '   if(!strcmp(name,"rx-min"))adapter.rx_ring[0][0].rxd_info2.PLEN0=14;\n'
 '   if(!strcmp(name,"rx-max"))adapter.rx_ring[0][0].rxd_info2.PLEN0=MAX_RX_LENGTH;\n'
 '   ret=rt2880_eth_recv(&main_dev,NULL,1);\n'
 '  }\n'
 '  else\n'
 '  if(!strcmp(name,"prx-owned"))second=fe_pdma_rx_dma_init(&main_dev);\n'
 '  else if(!strcmp(name,"qrx-owned"))second=fe_qdma_rx_dma_init(&main_dev);\n'
 '  else if(!strcmp(name,"open-twice"))second=ei_open(&main_dev);\n'
 '  else if(!strcmp(name,"irq-twice"))second=fe_int_enable(&main_dev);\n'
 '  else if(!strcmp(name,"tasklet-running"))ei_receive();\n'
 '  else {\n'
 '   '
 'if(!strcmp(name,"close-pbusy"))pbusy=1;if(!strcmp(name,"close-qbusy")||!strncmp(name,"quarantine-",11))qbusy=1;\n'
 '   ret=ei_close(&main_dev);\n'
 '   if(!strcmp(name,"quarantine-reopen"))second=ei_open(&main_dev);\n'
 '   if(!strcmp(name,"quarantine-close"))second=ei_close(&main_dev);\n'
 '   if(!strcmp(name,"close-twice"))second=ei_close(&main_dev);\n'
 '   if(!strcmp(name,"reopen"))second=ei_open(&main_dev);\n'
 '   if(!strcmp(name,"tasklet-stopped"))ei_receive();\n'
 '  }\n'
 ' }\n'
 ' unsigned int live=0;for(unsigned int i=0;i<owner_count;i++)if(owners[i])live++;\n'
 ' for(unsigned int i=0;i<num_rx_desc;i++)if(adapter.netrx_skb_data[0][i]) {\n'
 '  bool owned=false;for(unsigned int '
 'j=0;j<owner_count;j++)if(owners[j]==adapter.netrx_skb_data[0][i])owned=true;\n'
 '  if(!owned)errors++;\n'
 ' }\n'
 ' for(unsigned int i=0;i<NUM_QRX_DESC;i++)if(adapter.netrx0_skb_data[i]) {\n'
 '  bool owned=false;for(unsigned int '
 'j=0;j<owner_count;j++)if(owners[j]==adapter.netrx0_skb_data[i])owned=true;\n'
 '  if(!owned)errors++;\n'
 ' }\n'
 ' unsigned int dma_on=((regfile[PDMA_GLO_CFG]|regfile[QDMA_GLO_CFG])&(RX_DMA_EN|TX_DMA_EN))!=0;\n'
 ' '
 'printf("{\\"delivered\\":%u,\\"dropped\\":%u,\\"ret\\":%d,\\"second_ret\\":%d,\\"live\\":%u,\\"maps\\":%u,\\"irq_live\\":%u,\\"module\\":%u,\\"quarantine\\":%u,\\"stages\\":%u,\\"dma_on\\":%u,\\"queue\\":%u,\\"schedules\\":%u,\\"rearms\\":%u,\\"errors\\":%u}\\n",delivered,adapter.stat.rx_dropped,ret,second,live,live_maps,irq_live,module_refs,adapter.dma_quarantined,adapter.dma_stages,dma_on,queue_started,schedules,rearms,errors);\n'
 ' if(delays>2000)return 3;\n'
 ' for(unsigned int i=0;i<owner_count;i++)free(owners[i]);return 0;\n'
 '}\n')

def function(text, name):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked = re.sub(tokens, lambda m: ' ' * len(m.group()), text)
    matches = list(re.finditer(r'(?:static\s+)?(?:inline\s+)?(?:int|void|bool)\s+\b'
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
    if set(texts)!=set(SOURCE_PATHS): raise ValueError('Exact runtime source inputs required')
    for key,fragments in SOURCE_FRAGMENTS.items():
        for text in fragments:
            if text not in texts[key]: raise ValueError('K2P profile changed: '+text)
    for name,key in dict(FUNCTION_SOURCES,**SOURCE_ONLY_FUNCTION_SOURCES).items():function(texts[key],name)
def function_manifest(texts):
    validate_inputs(texts)
    return {name:{'source':key,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()} for name,key in FUNCTION_SOURCES.items()}
def source_only_manifest(texts):
    validate_inputs(texts)
    return {name:{'source':key,'execution':'source-only-not-run','full_body_sha256':hashlib.sha256(function(texts[key],name).encode()).hexdigest()} for name,key in SOURCE_ONLY_FUNCTION_SOURCES.items()}
def generate_source(texts):
    validate_inputs(texts)
    bodies={name:function(texts[key],name)for name,key in FUNCTION_SOURCES.items()}
    admission='if ('+' && '.join('strcmp(name,"'+n+'")' for n in CASE_NAMES)+') return 2;'
    return PREFIX+'\n'+'\n'.join(bodies[n] for n in BODY_ORDER)+'\n'+SUFFIX.replace('CASE_ADMISSION',admission)
