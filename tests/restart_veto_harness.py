"""Execute whole restart, shutdown and DMA-stop source bodies on a native host.

This is a control-flow/ownership model, not hardware DMA or a Linux kernel.
Atomic operations use host atomics; locks use pthread mutexes; device/list layout,
notifiers, scheduling, IRQ state, MMIO and terminal escape are explicit seams.
A park escapes only in the harness, via longjmp from schedule/cpu_relax. Production
has no escape and no failure clear operation. ASIC enable/idle/reset and worker
retirement are bounded injected hardware/execution seams; their acceptance is
consumed by the real RT28XXDMAStop/Reset and RtmpDmaTeardownCheck bodies.
"""
import hashlib
import re

BASE = 'trunk/linux-4.4.x/'
WIFI = BASE + 'drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS = {'reboot': 'trunk/linux-4.4.x/kernel/reboot.c',
 'header': 'trunk/linux-4.4.x/include/linux/reboot.h',
 'arch': 'trunk/linux-4.4.x/arch/mips/ralink/reset.c',
 'mips': 'trunk/linux-4.4.x/arch/mips/kernel/reset.c',
 'core': 'trunk/linux-4.4.x/drivers/base/core.c',
 'pci_core': 'trunk/linux-4.4.x/drivers/pci/pci-driver.c',
 'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
 'ra_mac': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/ra_mac.c',
 'pdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_pdma.c',
 'qdma': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether_qdma.c',
 'wifi': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/rt_main_dev.c',
 'pci': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/pci_main_dev.c',
 'dma': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/embedded/common/cmm_mac_pci.c'}
FUNCTION_SOURCES = {
    'reboot_dma_failure_report': 'reboot', 'reboot_dma_failures': 'reboot',
    'reboot_dma_failure_check': 'reboot', 'emergency_restart': 'reboot',
    'kernel_restart_prepare': 'reboot', 'kernel_restart': 'reboot',
    'ralink_restart': 'arch', 'machine_restart': 'mips', 'device_shutdown': 'core',
    'pci_device_shutdown': 'pci_core', 'ra2880stop': 'ra_mac',
    'fe_pdma_wait_dma_idle': 'pdma', 'fe_qdma_wait_dma_idle': 'qdma',
    'ei_stop_dma': 'raeth', 'raether_shutdown': 'raeth',
    'RtmpDmaLifecycleLock': 'wifi', 'RtmpDmaLifecycleUnlock': 'wifi',
    'RtmpDmaQuarantine': 'wifi', 'RtmpDmaTeardownCheck': 'wifi',
    'RT28XXDMAStop': 'dma', 'RT28XXDMAReset': 'dma', 'rt_pci_shutdown': 'pci',
}
SOURCE_ONLY_FUNCTION_SOURCES = {}
MODEL_VARIANT = {
    'whole_restart_shutdown_control_flow': True,
    'real_native_atomic_and_pthread_seams': True,
    'scheduler_MMIO_IRQ_terminal_escape_are_seams': True,
    'worker_and_ASIC_operations_are_injected_seams': True,
    'hardware_DMA_or_PCI_drain_proven': False,
    'power_loss_or_independent_watchdog_prevented': False,
    'unreported_DMA_or_all_concurrent_report_windows_prevented': False,
}
SOURCE_DECLARATIONS = {
    r'enum reboot_dma_failure\s*\{[^}]+\};': 'header',
    r'^#define SYSC_REG_RESET_CTRL\s+[^\n]+': 'arch',
    r'^#define RSTCTL_RESET_PCI\s+[^\n]+': 'arch',
    r'^#define RSTCTL_RESET_SYSTEM\s+[^\n]+': 'arch',
}

NEW_FUNCTIONS = ('reboot_dma_failure_report', 'reboot_dma_failures', 'reboot_dma_failure_check')
BASELINE_COMMIT = 'f9c361f682eb742423dd9ebd422a1952af2ec6e0'
CASE_NAMES = (
    'success', 'success-never-enabled', 'raeth-pdma-busy', 'raeth-qdma-busy',
    'wifi-busy', 'wifi-disable-failed', 'wifi-reset-failed', 'wifi-worker-failed',
    'quarantine-active', 'quarantine-then-idle', 'quarantine-pure-oom',
    'quarantine-quiesced', 'repeat-success-after-failure', 'normal-prelatched',
    'prepare-only', 'park-spurious-wake', 'emergency-latched', 'emergency-irq-off',
    'direct-latched', 'direct-irq-off', 'late-migrate', 'late-syscore',
    'concurrent-report', 'zero-report', 'success-emergency', 'success-direct',
)


BODY_ORDER = ('reboot_dma_failure_report', 'reboot_dma_failures', 'reboot_dma_failure_check', 'emergency_restart', 'kernel_restart_prepare', 'kernel_restart', 'ralink_restart', 'machine_restart', 'device_shutdown', 'pci_device_shutdown', 'ra2880stop', 'fe_pdma_wait_dma_idle', 'fe_qdma_wait_dma_idle', 'ei_stop_dma', 'raether_shutdown', 'RtmpDmaLifecycleLock', 'RtmpDmaLifecycleUnlock', 'RtmpDmaQuarantine', 'RtmpDmaTeardownCheck', 'RT28XXDMAStop', 'RT28XXDMAReset', 'rt_pci_shutdown')
FIELDS = ('reasons', 'terminal', 'sleeps', 'spins', 'irq_off', 'callbacks', 'migrate', 'syscore', 'pci_reset', 'system_reset', 'stop', 'idle', 'reset', 'p_reads', 'q_reads', 'clear_master', 'wifi_quarantine', 'wifi_quiesced', 'raeth_quarantine', 'owners', 'workers', 'commands', 'irq_sync', 'events')
EXPECTED_ROWS = {'success': {'reasons': 0,
             'terminal': 3,
             'sleeps': 0,
             'spins': 0,
             'irq_off': 1,
             'callbacks': 2,
             'migrate': 1,
             'syscore': 1,
             'pci_reset': 1,
             'system_reset': 1,
             'stop': 1,
             'idle': 1,
             'reset': 1,
             'p_reads': 2,
             'q_reads': 2,
             'clear_master': 1,
             'wifi_quarantine': 0,
             'wifi_quiesced': 1,
             'raeth_quarantine': 1,
             'owners': 8,
             'workers': 1,
             'commands': 1,
             'irq_sync': 1,
             'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,migrate,syscore,dump,pci-reset,system-reset,'},
 'success-never-enabled': {'reasons': 0,
                           'terminal': 3,
                           'sleeps': 0,
                           'spins': 0,
                           'irq_off': 1,
                           'callbacks': 2,
                           'migrate': 1,
                           'syscore': 1,
                           'pci_reset': 1,
                           'system_reset': 1,
                           'stop': 0,
                           'idle': 0,
                           'reset': 0,
                           'p_reads': 2,
                           'q_reads': 2,
                           'clear_master': 1,
                           'wifi_quarantine': 0,
                           'wifi_quiesced': 0,
                           'raeth_quarantine': 1,
                           'owners': 8,
                           'workers': 0,
                           'commands': 0,
                           'irq_sync': 0,
                           'events': 'notifier,helpers,cpufreq,raeth,pci,migrate,syscore,dump,pci-reset,system-reset,'},
 'raeth-pdma-busy': {'reasons': 1,
                     'terminal': 1,
                     'sleeps': 1,
                     'spins': 0,
                     'irq_off': 0,
                     'callbacks': 2,
                     'migrate': 0,
                     'syscore': 0,
                     'pci_reset': 0,
                     'system_reset': 0,
                     'stop': 1,
                     'idle': 1,
                     'reset': 1,
                     'p_reads': 1001,
                     'q_reads': 2,
                     'clear_master': 1,
                     'wifi_quarantine': 0,
                     'wifi_quiesced': 1,
                     'raeth_quarantine': 1,
                     'owners': 8,
                     'workers': 1,
                     'commands': 1,
                     'irq_sync': 1,
                     'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'raeth-qdma-busy': {'reasons': 1,
                     'terminal': 1,
                     'sleeps': 1,
                     'spins': 0,
                     'irq_off': 0,
                     'callbacks': 2,
                     'migrate': 0,
                     'syscore': 0,
                     'pci_reset': 0,
                     'system_reset': 0,
                     'stop': 1,
                     'idle': 1,
                     'reset': 1,
                     'p_reads': 2,
                     'q_reads': 1001,
                     'clear_master': 1,
                     'wifi_quarantine': 0,
                     'wifi_quiesced': 1,
                     'raeth_quarantine': 1,
                     'owners': 8,
                     'workers': 1,
                     'commands': 1,
                     'irq_sync': 1,
                     'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'wifi-busy': {'reasons': 2,
               'terminal': 1,
               'sleeps': 1,
               'spins': 0,
               'irq_off': 0,
               'callbacks': 2,
               'migrate': 0,
               'syscore': 0,
               'pci_reset': 0,
               'system_reset': 0,
               'stop': 1,
               'idle': 1,
               'reset': 0,
               'p_reads': 2,
               'q_reads': 2,
               'clear_master': 3,
               'wifi_quarantine': 1,
               'wifi_quiesced': 0,
               'raeth_quarantine': 1,
               'owners': 8,
               'workers': 1,
               'commands': 1,
               'irq_sync': 1,
               'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'wifi-disable-failed': {'reasons': 2,
                         'terminal': 1,
                         'sleeps': 1,
                         'spins': 0,
                         'irq_off': 0,
                         'callbacks': 2,
                         'migrate': 0,
                         'syscore': 0,
                         'pci_reset': 0,
                         'system_reset': 0,
                         'stop': 1,
                         'idle': 0,
                         'reset': 0,
                         'p_reads': 2,
                         'q_reads': 2,
                         'clear_master': 3,
                         'wifi_quarantine': 1,
                         'wifi_quiesced': 0,
                         'raeth_quarantine': 1,
                         'owners': 8,
                         'workers': 1,
                         'commands': 1,
                         'irq_sync': 1,
                         'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,'},
 'wifi-reset-failed': {'reasons': 2,
                       'terminal': 1,
                       'sleeps': 1,
                       'spins': 0,
                       'irq_off': 0,
                       'callbacks': 2,
                       'migrate': 0,
                       'syscore': 0,
                       'pci_reset': 0,
                       'system_reset': 0,
                       'stop': 1,
                       'idle': 1,
                       'reset': 1,
                       'p_reads': 2,
                       'q_reads': 2,
                       'clear_master': 3,
                       'wifi_quarantine': 1,
                       'wifi_quiesced': 0,
                       'raeth_quarantine': 1,
                       'owners': 8,
                       'workers': 1,
                       'commands': 1,
                       'irq_sync': 1,
                       'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'wifi-worker-failed': {'reasons': 2,
                        'terminal': 1,
                        'sleeps': 1,
                        'spins': 0,
                        'irq_off': 0,
                        'callbacks': 2,
                        'migrate': 0,
                        'syscore': 0,
                        'pci_reset': 0,
                        'system_reset': 0,
                        'stop': 0,
                        'idle': 0,
                        'reset': 0,
                        'p_reads': 2,
                        'q_reads': 2,
                        'clear_master': 3,
                        'wifi_quarantine': 1,
                        'wifi_quiesced': 0,
                        'raeth_quarantine': 1,
                        'owners': 8,
                        'workers': 1,
                        'commands': 0,
                        'irq_sync': 1,
                        'events': 'notifier,helpers,cpufreq,raeth,pci,'},
 'quarantine-active': {'reasons': 2,
                       'terminal': 1,
                       'sleeps': 1,
                       'spins': 0,
                       'irq_off': 0,
                       'callbacks': 2,
                       'migrate': 0,
                       'syscore': 0,
                       'pci_reset': 0,
                       'system_reset': 0,
                       'stop': 0,
                       'idle': 0,
                       'reset': 0,
                       'p_reads': 2,
                       'q_reads': 2,
                       'clear_master': 3,
                       'wifi_quarantine': 1,
                       'wifi_quiesced': 0,
                       'raeth_quarantine': 1,
                       'owners': 8,
                       'workers': 0,
                       'commands': 0,
                       'irq_sync': 0,
                       'events': 'notifier,helpers,cpufreq,raeth,pci,'},
 'quarantine-then-idle': {'reasons': 2,
                          'terminal': 1,
                          'sleeps': 1,
                          'spins': 0,
                          'irq_off': 0,
                          'callbacks': 2,
                          'migrate': 0,
                          'syscore': 0,
                          'pci_reset': 0,
                          'system_reset': 0,
                          'stop': 0,
                          'idle': 0,
                          'reset': 0,
                          'p_reads': 2,
                          'q_reads': 2,
                          'clear_master': 3,
                          'wifi_quarantine': 1,
                          'wifi_quiesced': 1,
                          'raeth_quarantine': 1,
                          'owners': 8,
                          'workers': 0,
                          'commands': 0,
                          'irq_sync': 0,
                          'events': 'notifier,helpers,cpufreq,raeth,pci,'},
 'quarantine-pure-oom': {'reasons': 0,
                         'terminal': 3,
                         'sleeps': 0,
                         'spins': 0,
                         'irq_off': 1,
                         'callbacks': 2,
                         'migrate': 1,
                         'syscore': 1,
                         'pci_reset': 1,
                         'system_reset': 1,
                         'stop': 0,
                         'idle': 0,
                         'reset': 0,
                         'p_reads': 2,
                         'q_reads': 2,
                         'clear_master': 3,
                         'wifi_quarantine': 1,
                         'wifi_quiesced': 0,
                         'raeth_quarantine': 1,
                         'owners': 8,
                         'workers': 0,
                         'commands': 0,
                         'irq_sync': 0,
                         'events': 'notifier,helpers,cpufreq,raeth,pci,migrate,syscore,dump,pci-reset,system-reset,'},
 'quarantine-quiesced': {'reasons': 0,
                         'terminal': 3,
                         'sleeps': 0,
                         'spins': 0,
                         'irq_off': 1,
                         'callbacks': 2,
                         'migrate': 1,
                         'syscore': 1,
                         'pci_reset': 1,
                         'system_reset': 1,
                         'stop': 0,
                         'idle': 0,
                         'reset': 0,
                         'p_reads': 2,
                         'q_reads': 2,
                         'clear_master': 3,
                         'wifi_quarantine': 1,
                         'wifi_quiesced': 1,
                         'raeth_quarantine': 1,
                         'owners': 8,
                         'workers': 0,
                         'commands': 0,
                         'irq_sync': 0,
                         'events': 'notifier,helpers,cpufreq,raeth,pci,migrate,syscore,dump,pci-reset,system-reset,'},
 'repeat-success-after-failure': {'reasons': 1,
                                  'terminal': 1,
                                  'sleeps': 1,
                                  'spins': 0,
                                  'irq_off': 0,
                                  'callbacks': 2,
                                  'migrate': 0,
                                  'syscore': 0,
                                  'pci_reset': 0,
                                  'system_reset': 0,
                                  'stop': 1,
                                  'idle': 1,
                                  'reset': 1,
                                  'p_reads': 1005,
                                  'q_reads': 6,
                                  'clear_master': 1,
                                  'wifi_quarantine': 0,
                                  'wifi_quiesced': 1,
                                  'raeth_quarantine': 1,
                                  'owners': 8,
                                  'workers': 1,
                                  'commands': 1,
                                  'irq_sync': 1,
                                  'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'normal-prelatched': {'reasons': 1,
                       'terminal': 1,
                       'sleeps': 1,
                       'spins': 0,
                       'irq_off': 0,
                       'callbacks': 2,
                       'migrate': 0,
                       'syscore': 0,
                       'pci_reset': 0,
                       'system_reset': 0,
                       'stop': 1,
                       'idle': 1,
                       'reset': 1,
                       'p_reads': 2,
                       'q_reads': 2,
                       'clear_master': 1,
                       'wifi_quarantine': 0,
                       'wifi_quiesced': 1,
                       'raeth_quarantine': 1,
                       'owners': 8,
                       'workers': 1,
                       'commands': 1,
                       'irq_sync': 1,
                       'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'prepare-only': {'reasons': 1,
                  'terminal': 1,
                  'sleeps': 1,
                  'spins': 0,
                  'irq_off': 0,
                  'callbacks': 2,
                  'migrate': 0,
                  'syscore': 0,
                  'pci_reset': 0,
                  'system_reset': 0,
                  'stop': 1,
                  'idle': 1,
                  'reset': 1,
                  'p_reads': 2,
                  'q_reads': 2,
                  'clear_master': 1,
                  'wifi_quarantine': 0,
                  'wifi_quiesced': 1,
                  'raeth_quarantine': 1,
                  'owners': 8,
                  'workers': 1,
                  'commands': 1,
                  'irq_sync': 1,
                  'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'park-spurious-wake': {'reasons': 1,
                        'terminal': 1,
                        'sleeps': 2,
                        'spins': 0,
                        'irq_off': 0,
                        'callbacks': 2,
                        'migrate': 0,
                        'syscore': 0,
                        'pci_reset': 0,
                        'system_reset': 0,
                        'stop': 1,
                        'idle': 1,
                        'reset': 1,
                        'p_reads': 2,
                        'q_reads': 2,
                        'clear_master': 1,
                        'wifi_quarantine': 0,
                        'wifi_quiesced': 1,
                        'raeth_quarantine': 1,
                        'owners': 8,
                        'workers': 1,
                        'commands': 1,
                        'irq_sync': 1,
                        'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'emergency-latched': {'reasons': 2,
                       'terminal': 2,
                       'sleeps': 0,
                       'spins': 1,
                       'irq_off': 1,
                       'callbacks': 0,
                       'migrate': 0,
                       'syscore': 0,
                       'pci_reset': 0,
                       'system_reset': 0,
                       'stop': 0,
                       'idle': 0,
                       'reset': 0,
                       'p_reads': 0,
                       'q_reads': 0,
                       'clear_master': 0,
                       'wifi_quarantine': 0,
                       'wifi_quiesced': 0,
                       'raeth_quarantine': 0,
                       'owners': 8,
                       'workers': 0,
                       'commands': 0,
                       'irq_sync': 0,
                       'events': ''},
 'emergency-irq-off': {'reasons': 2,
                       'terminal': 2,
                       'sleeps': 0,
                       'spins': 1,
                       'irq_off': 1,
                       'callbacks': 0,
                       'migrate': 0,
                       'syscore': 0,
                       'pci_reset': 0,
                       'system_reset': 0,
                       'stop': 0,
                       'idle': 0,
                       'reset': 0,
                       'p_reads': 0,
                       'q_reads': 0,
                       'clear_master': 0,
                       'wifi_quarantine': 0,
                       'wifi_quiesced': 0,
                       'raeth_quarantine': 0,
                       'owners': 8,
                       'workers': 0,
                       'commands': 0,
                       'irq_sync': 0,
                       'events': ''},
 'direct-latched': {'reasons': 2,
                    'terminal': 2,
                    'sleeps': 0,
                    'spins': 1,
                    'irq_off': 1,
                    'callbacks': 0,
                    'migrate': 0,
                    'syscore': 0,
                    'pci_reset': 0,
                    'system_reset': 0,
                    'stop': 0,
                    'idle': 0,
                    'reset': 0,
                    'p_reads': 0,
                    'q_reads': 0,
                    'clear_master': 0,
                    'wifi_quarantine': 0,
                    'wifi_quiesced': 0,
                    'raeth_quarantine': 0,
                    'owners': 8,
                    'workers': 0,
                    'commands': 0,
                    'irq_sync': 0,
                    'events': ''},
 'direct-irq-off': {'reasons': 2,
                    'terminal': 2,
                    'sleeps': 0,
                    'spins': 1,
                    'irq_off': 1,
                    'callbacks': 0,
                    'migrate': 0,
                    'syscore': 0,
                    'pci_reset': 0,
                    'system_reset': 0,
                    'stop': 0,
                    'idle': 0,
                    'reset': 0,
                    'p_reads': 0,
                    'q_reads': 0,
                    'clear_master': 0,
                    'wifi_quarantine': 0,
                    'wifi_quiesced': 0,
                    'raeth_quarantine': 0,
                    'owners': 8,
                    'workers': 0,
                    'commands': 0,
                    'irq_sync': 0,
                    'events': ''},
 'late-migrate': {'reasons': 2,
                  'terminal': 2,
                  'sleeps': 0,
                  'spins': 1,
                  'irq_off': 1,
                  'callbacks': 2,
                  'migrate': 1,
                  'syscore': 1,
                  'pci_reset': 0,
                  'system_reset': 0,
                  'stop': 1,
                  'idle': 1,
                  'reset': 1,
                  'p_reads': 2,
                  'q_reads': 2,
                  'clear_master': 1,
                  'wifi_quarantine': 0,
                  'wifi_quiesced': 1,
                  'raeth_quarantine': 1,
                  'owners': 8,
                  'workers': 1,
                  'commands': 1,
                  'irq_sync': 1,
                  'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,migrate,syscore,dump,'},
 'late-syscore': {'reasons': 2,
                  'terminal': 2,
                  'sleeps': 0,
                  'spins': 1,
                  'irq_off': 1,
                  'callbacks': 2,
                  'migrate': 1,
                  'syscore': 1,
                  'pci_reset': 0,
                  'system_reset': 0,
                  'stop': 1,
                  'idle': 1,
                  'reset': 1,
                  'p_reads': 2,
                  'q_reads': 2,
                  'clear_master': 1,
                  'wifi_quarantine': 0,
                  'wifi_quiesced': 1,
                  'raeth_quarantine': 1,
                  'owners': 8,
                  'workers': 1,
                  'commands': 1,
                  'irq_sync': 1,
                  'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,migrate,syscore,dump,'},
 'concurrent-report': {'reasons': 255,
                       'terminal': 1,
                       'sleeps': 1,
                       'spins': 0,
                       'irq_off': 0,
                       'callbacks': 2,
                       'migrate': 0,
                       'syscore': 0,
                       'pci_reset': 0,
                       'system_reset': 0,
                       'stop': 1,
                       'idle': 1,
                       'reset': 1,
                       'p_reads': 2,
                       'q_reads': 2,
                       'clear_master': 1,
                       'wifi_quarantine': 0,
                       'wifi_quiesced': 1,
                       'raeth_quarantine': 1,
                       'owners': 8,
                       'workers': 1,
                       'commands': 1,
                       'irq_sync': 1,
                       'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'zero-report': {'reasons': 4,
                 'terminal': 1,
                 'sleeps': 1,
                 'spins': 0,
                 'irq_off': 0,
                 'callbacks': 2,
                 'migrate': 0,
                 'syscore': 0,
                 'pci_reset': 0,
                 'system_reset': 0,
                 'stop': 1,
                 'idle': 1,
                 'reset': 1,
                 'p_reads': 2,
                 'q_reads': 2,
                 'clear_master': 1,
                 'wifi_quarantine': 0,
                 'wifi_quiesced': 1,
                 'raeth_quarantine': 1,
                 'owners': 8,
                 'workers': 1,
                 'commands': 1,
                 'irq_sync': 1,
                 'events': 'notifier,helpers,cpufreq,raeth,pci,wifi-stop,wifi-idle,'},
 'success-emergency': {'reasons': 0,
                       'terminal': 3,
                       'sleeps': 0,
                       'spins': 0,
                       'irq_off': 1,
                       'callbacks': 0,
                       'migrate': 0,
                       'syscore': 0,
                       'pci_reset': 1,
                       'system_reset': 1,
                       'stop': 0,
                       'idle': 0,
                       'reset': 0,
                       'p_reads': 0,
                       'q_reads': 0,
                       'clear_master': 0,
                       'wifi_quarantine': 0,
                       'wifi_quiesced': 0,
                       'raeth_quarantine': 0,
                       'owners': 8,
                       'workers': 0,
                       'commands': 0,
                       'irq_sync': 0,
                       'events': 'dump,pci-reset,system-reset,'},
 'success-direct': {'reasons': 0,
                    'terminal': 3,
                    'sleeps': 0,
                    'spins': 0,
                    'irq_off': 1,
                    'callbacks': 0,
                    'migrate': 0,
                    'syscore': 0,
                    'pci_reset': 1,
                    'system_reset': 1,
                    'stop': 0,
                    'idle': 0,
                    'reset': 0,
                    'p_reads': 0,
                    'q_reads': 0,
                    'clear_master': 0,
                    'wifi_quarantine': 0,
                    'wifi_quiesced': 0,
                    'raeth_quarantine': 0,
                    'owners': 8,
                    'workers': 0,
                    'commands': 0,
                    'irq_sync': 0,
                    'events': 'pci-reset,system-reset,'}}
BASELINE_ROWS = {'success': {'reasons': 0,
             'terminal': 3,
             'sleeps': 0,
             'spins': 0,
             'irq_off': 1,
             'callbacks': 2,
             'migrate': 1,
             'syscore': 1,
             'pci_reset': 1,
             'system_reset': 1,
             'stop': 0,
             'idle': 0,
             'reset': 0,
             'p_reads': 2,
             'q_reads': 2,
             'clear_master': 1,
             'wifi_quarantine': 0,
             'wifi_quiesced': 0,
             'raeth_quarantine': 1,
             'owners': 8,
             'workers': 0,
             'commands': 0,
             'irq_sync': 0,
             'events': 'notifier,helpers,cpufreq,raeth,pci,migrate,syscore,dump,pci-reset,system-reset,'},
 'raeth-pdma-busy': {'reasons': 0,
                     'terminal': 3,
                     'sleeps': 0,
                     'spins': 0,
                     'irq_off': 1,
                     'callbacks': 2,
                     'migrate': 1,
                     'syscore': 1,
                     'pci_reset': 1,
                     'system_reset': 1,
                     'stop': 0,
                     'idle': 0,
                     'reset': 0,
                     'p_reads': 1001,
                     'q_reads': 2,
                     'clear_master': 1,
                     'wifi_quarantine': 0,
                     'wifi_quiesced': 0,
                     'raeth_quarantine': 1,
                     'owners': 8,
                     'workers': 0,
                     'commands': 0,
                     'irq_sync': 0,
                     'events': 'notifier,helpers,cpufreq,raeth,pci,migrate,syscore,dump,pci-reset,system-reset,'},
 'wifi-busy': {'reasons': 0,
               'terminal': 3,
               'sleeps': 0,
               'spins': 0,
               'irq_off': 1,
               'callbacks': 2,
               'migrate': 1,
               'syscore': 1,
               'pci_reset': 1,
               'system_reset': 1,
               'stop': 0,
               'idle': 0,
               'reset': 0,
               'p_reads': 2,
               'q_reads': 2,
               'clear_master': 1,
               'wifi_quarantine': 0,
               'wifi_quiesced': 0,
               'raeth_quarantine': 1,
               'owners': 8,
               'workers': 0,
               'commands': 0,
               'irq_sync': 0,
               'events': 'notifier,helpers,cpufreq,raeth,pci,migrate,syscore,dump,pci-reset,system-reset,'},
 'quarantine-active': {'reasons': 0,
                       'terminal': 3,
                       'sleeps': 0,
                       'spins': 0,
                       'irq_off': 1,
                       'callbacks': 2,
                       'migrate': 1,
                       'syscore': 1,
                       'pci_reset': 1,
                       'system_reset': 1,
                       'stop': 0,
                       'idle': 0,
                       'reset': 0,
                       'p_reads': 2,
                       'q_reads': 2,
                       'clear_master': 2,
                       'wifi_quarantine': 1,
                       'wifi_quiesced': 0,
                       'raeth_quarantine': 1,
                       'owners': 8,
                       'workers': 0,
                       'commands': 0,
                       'irq_sync': 0,
                       'events': 'notifier,helpers,cpufreq,raeth,pci,migrate,syscore,dump,pci-reset,system-reset,'},
 'emergency-latched': {'reasons': 0,
                       'terminal': 3,
                       'sleeps': 0,
                       'spins': 0,
                       'irq_off': 1,
                       'callbacks': 0,
                       'migrate': 0,
                       'syscore': 0,
                       'pci_reset': 1,
                       'system_reset': 1,
                       'stop': 0,
                       'idle': 0,
                       'reset': 0,
                       'p_reads': 0,
                       'q_reads': 0,
                       'clear_master': 0,
                       'wifi_quarantine': 0,
                       'wifi_quiesced': 0,
                       'raeth_quarantine': 0,
                       'owners': 8,
                       'workers': 0,
                       'commands': 0,
                       'irq_sync': 0,
                       'events': 'dump,pci-reset,system-reset,'},
 'direct-latched': {'reasons': 0,
                    'terminal': 3,
                    'sleeps': 0,
                    'spins': 0,
                    'irq_off': 1,
                    'callbacks': 0,
                    'migrate': 0,
                    'syscore': 0,
                    'pci_reset': 1,
                    'system_reset': 1,
                    'stop': 0,
                    'idle': 0,
                    'reset': 0,
                    'p_reads': 0,
                    'q_reads': 0,
                    'clear_master': 0,
                    'wifi_quarantine': 0,
                    'wifi_quiesced': 0,
                    'raeth_quarantine': 0,
                    'owners': 8,
                    'workers': 0,
                    'commands': 0,
                    'irq_sync': 0,
                    'events': 'pci-reset,system-reset,'},
 'late-syscore': {'reasons': 0,
                  'terminal': 3,
                  'sleeps': 0,
                  'spins': 0,
                  'irq_off': 1,
                  'callbacks': 2,
                  'migrate': 1,
                  'syscore': 1,
                  'pci_reset': 1,
                  'system_reset': 1,
                  'stop': 0,
                  'idle': 0,
                  'reset': 0,
                  'p_reads': 2,
                  'q_reads': 2,
                  'clear_master': 1,
                  'wifi_quarantine': 0,
                  'wifi_quiesced': 0,
                  'raeth_quarantine': 1,
                  'owners': 8,
                  'workers': 0,
                  'commands': 0,
                  'irq_sync': 0,
                  'events': 'notifier,helpers,cpufreq,raeth,pci,migrate,syscore,dump,pci-reset,system-reset,'}}

def function(text, name):
    token = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
    masked = re.sub(token, lambda m: ' ' * len(m.group()), text)
    pattern = (r'^(?:static\s+)?(?:inline\s+)?(?:unsigned\s+int|VOID|BOOLEAN|int|void)\s+'
               + re.escape(name) + r'\s*\([^;{}]*\)\s*\{')
    found = list(re.finditer(pattern, masked, re.M))
    if len(found) != 1:
        raise ValueError('Missing/ambiguous restart function: ' + name)
    start = found[0].start()
    opening = masked.index('{', start)
    depth = 0
    for match in re.finditer(token + r'|[{}]', text[opening:]):
        if match.group() == '{':
            depth += 1
        elif match.group() == '}':
            depth -= 1
            if not depth:
                return text[start:opening + match.end()]
    raise ValueError('Unterminated restart function: ' + name)


def function_manifest(texts, baseline=False):
    return {name: {'source': SOURCE_PATHS[key], 'execution': 'whole-function',
                   'sha256': hashlib.sha256(function(texts[key], name).encode()).hexdigest()}
            for name, key in FUNCTION_SOURCES.items() if not (baseline and name in NEW_FUNCTIONS)}


PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void VOID;
typedef int BOOLEAN;
typedef unsigned long ULONG;
typedef unsigned int u32;
#define TRUE 1
#define FALSE 0
#define BIT(n) (1U << (n))
#define IS_ENABLED(x) (x)
#define CONFIG_PCI 1
#define CONFIG_RA_NAT_NONE 1
#define MAX_SCHEDULE_TIMEOUT LONG_MAX
#define SYSTEM_RESTART 1
#define SYS_RESTART 1
#define KMSG_DUMP_EMERG 1
#define KMSG_DUMP_RESTART 2
#define NDIS_STATUS_SUCCESS 0
#define fRTMP_ADAPTER_HALT_IN_PROGRESS BIT(0)
#define fRTMP_ADAPTER_START_UP BIT(1)
#define fRTMP_ADAPTER_INTERRUPT_ACTIVE BIT(2)
#define PDMA_TX_RX 2
#define RX_DMA_BUSY BIT(3)
#define TX_DMA_BUSY BIT(1)
#define TX_WB_DDONE BIT(6)
#define RX_DMA_EN BIT(2)
#define TX_DMA_EN BIT(0)
#define PDMA_GLO_CFG 1
#define DMA_GLO_CFG PDMA_GLO_CFG
#define QDMA_GLO_CFG 2
#define FE_QDMA BIT(4)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_ACQUIRE)
#define WRITE_ONCE(x, v) __atomic_store_n(&(x), (v), __ATOMIC_RELEASE)
#define MTWF_LOG(...) ((void)0)
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
#define pr_emerg(...) ((void)0)
#define dev_info(...) ((void)0)
#define RTMP_SET_FLAG(a, f) ((a)->flags |= (f))
#define RTMP_CLEAR_FLAG(a, f) ((a)->flags &= ~(f))
#define RTMP_TEST_FLAG(a, f) (((a)->flags & (f)) != 0)
SOURCE_DEFINITIONS
/* Atomic seam, with real native concurrent read-modify-write semantics. */
typedef struct { unsigned int counter; } atomic_t;
#define ATOMIC_INIT(x) {x}
static void atomic_or(unsigned int v, atomic_t *a) { __atomic_fetch_or(&a->counter, v, __ATOMIC_SEQ_CST); }
static unsigned int atomic_read(const atomic_t *a) { return __atomic_load_n(&a->counter, __ATOMIC_SEQ_CST); }
static jmp_buf terminal;
static int sleeps, spins, irq_off, in_irq, terminal_kind, sleep_returns;
static int migrate_calls, syscore_calls, pci_reset, system_reset, stop_calls, idle_calls, reset_calls;
static int p_reads, q_reads, clear_master_calls, callbacks, late_phase;
static int busy_p, busy_q, disable_ok = 1, idle_ok = 1, reset_ok = 1, worker_ok = 1;
static int rtnl_depth, lifecycle_depth, worker_calls, command_calls, irq_sync;
static int owners = 8, system_state, reboot_notifier_list, initcall_debug;
static char events[1024];
static void event(const char *s) { assert(strlen(events) + strlen(s) + 2 < sizeof(events));strcat(events,s);strcat(events,","); }
/* These are terminal-only test escapes, never alternate production returns. */
static void local_irq_disable(void) { irq_off = 1; }
static long schedule_timeout_uninterruptible(long n) { assert(n == LONG_MAX && !irq_off && !in_irq);sleeps++;if (sleeps <= sleep_returns)return n;terminal_kind = 1;longjmp(terminal,1); }
static void cpu_relax(void) { assert(irq_off);spins++;terminal_kind = 2;longjmp(terminal,1); }
static void unreachable(void) { terminal_kind = 3;longjmp(terminal,1); }
struct list_head {struct list_head *next,*prev;};
struct kobject {struct list_head entry;};
struct device;
struct shutdown_ops {void (*shutdown)(struct device *);};
struct device {struct device *parent;struct kobject kobj;struct shutdown_ops *class,*bus,*driver;int refs;};
struct kset {struct list_head list;pthread_mutex_t list_lock;};
static struct kset device_set = {.list_lock = PTHREAD_MUTEX_INITIALIZER};
static struct kset *devices_kset = &device_set;
#define list_entry(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
static int list_empty(struct list_head *h) {return h->next == h;}
static void list_del_init(struct list_head *e) {e->next->prev=e->prev;e->prev->next=e->next;e->next=e->prev=e;}
static void list_add_tail(struct list_head *e,struct list_head *h) {e->prev=h->prev;e->next=h;h->prev->next=e;h->prev=e;}
#define spin_lock(l) assert(pthread_mutex_lock(l)==0)
#define spin_unlock(l) assert(pthread_mutex_unlock(l)==0)
#define spin_lock_irqsave(l,f) do {(f)=0;spin_lock(l);}while(0)
#define spin_unlock_irqrestore(l,f) do {(void)(f);spin_unlock(l);}while(0)
static struct device *get_device(struct device *d) {if(d)d->refs++;return d;}
static void put_device(struct device *d) {if(d){assert(d->refs>1);d->refs--;}}
static void device_lock(struct device *d) {(void)d;}
static void device_unlock(struct device *d) {(void)d;}
static void pm_runtime_get_noresume(struct device *d) {(void)d;}
static void pm_runtime_barrier(struct device *d) {(void)d;}
static void cpufreq_suspend(void) {event("cpufreq");}
struct _RTMP_ADAPTER;
struct END_DEVICE;
struct net_device {char name[8];int irq;struct _RTMP_ADAPTER *adapter;struct END_DEVICE *priv;};
struct platform_device {struct device dev;struct net_device *data;};
struct pci_dev;
struct pci_driver {void (*shutdown)(struct pci_dev *);};
struct pci_dev {struct device dev;struct net_device *data;struct pci_driver *driver;int master;};
#define to_pci_dev(d) list_entry(d,struct pci_dev,dev)
struct END_DEVICE {unsigned int features;bool dma_quarantined;struct net_device *pseudo_dev;void *kreset_task,*kphy_poll_task;};
static void *netdev_priv(struct net_device *d) {return d->priv;}
static struct net_device *platform_get_drvdata(struct platform_device *d) {return d->data;}
static inline struct net_device *pci_get_drvdata(struct pci_dev *d) {return d->data;}
#define GET_PAD_FROM_NET_DEV(a,d) ((a)=(d)->adapter)
typedef struct {struct pci_dev *pci_dev;pthread_mutex_t dma_lifecycle_lock,dma_state_lock;} COOKIE,*POS_COOKIE;
typedef struct _RTMP_ADAPTER {void *OS_Cookie;struct net_device *net_dev;bool pci;unsigned int flags;int dma_running,dma_lifecycle_pinned,dma_quiesced,dma_quarantined,dma_stopping,dma_removing,dma_irq_registered;void *tm_qm_ops,*tm_hif_ops;int qm_wq_state,hif_wq_state;} RTMP_ADAPTER;
#define IS_PCI_INF(a) ((a)->pci)
#define IS_PCIE_INF(a) ((a)->pci)
static pthread_mutex_t rtnl = PTHREAD_MUTEX_INITIALIZER;
static void rtnl_lock(void) {assert(pthread_mutex_lock(&rtnl)==0);rtnl_depth++;}
static void rtnl_unlock(void) {assert(rtnl_depth==1);rtnl_depth--;assert(pthread_mutex_unlock(&rtnl)==0);}
static void mutex_lock(pthread_mutex_t *l) {assert(rtnl_depth);assert(pthread_mutex_lock(l)==0);lifecycle_depth++;}
static void mutex_unlock(pthread_mutex_t *l) {assert(lifecycle_depth==1);lifecycle_depth--;assert(pthread_mutex_unlock(l)==0);}
static void netif_device_detach(struct net_device *d) {assert(d && rtnl_depth);}
static void netif_tx_disable(struct net_device *d) {assert(d && rtnl_depth);}
static void netif_tx_stop_all_queues(struct net_device *d) {assert(d);}
static void netif_carrier_off(struct net_device *d) {assert(d);}
static void pci_clear_master(struct pci_dev *p) {p->master=0;clear_master_calls++;}
static void pm_runtime_resume(struct device *d) {(void)d;}
static void pci_msi_shutdown(struct pci_dev *d) {(void)d;}
static void pci_msix_shutdown(struct pci_dev *d) {(void)d;}
static void mii_mgr_detach(void) {assert(!rtnl_depth);}
static void debug_proc_exit(void) {assert(!rtnl_depth);}
static int kthread_stop(void *t) {assert(t && rtnl_depth);return 0;}
static void fe_int_disable(struct net_device *d) {assert(d && rtnl_depth);}
static void synchronize_irq(int irq) {assert(irq);irq_sync++;}
static void interrupt_disable(RTMP_ADAPTER *a) {a->flags &= ~fRTMP_ADAPTER_INTERRUPT_ACTIVE;}
#define RTMP_ASIC_INTERRUPT_DISABLE(a) interrupt_disable(a)
/* Worker and ASIC seams feed real teardown/stop/reset functions. */
static int tm_quiesce(RTMP_ADAPTER *a) {assert(a);worker_calls++;return worker_ok?0:1;}
static void AndesDmaQuiesce(RTMP_ADAPTER *a) {assert(a);command_calls++;}
static int AsicSetWPDMA(RTMP_ADAPTER *a,int which,int enable) {assert(a && which==PDMA_TX_RX && !enable);event("wifi-stop");stop_calls++;return disable_ok;}
static int AsicWaitPDMAIdle(RTMP_ADAPTER *a,int count,int delay) {assert(a && count==200 && delay==1000);event("wifi-idle");idle_calls++;return idle_ok;}
static int AsicResetWPDMA(RTMP_ADAPTER *a) {assert(a);reset_calls++;return reset_ok;}
static unsigned int sys_reg_read(int reg) {if(reg==PDMA_GLO_CFG){p_reads++;return busy_p?RX_DMA_BUSY:0;}assert(reg==QDMA_GLO_CFG);q_reads++;return busy_q?TX_DMA_BUSY:0;}
static void sys_reg_write(int reg,unsigned int v) {assert(reg==PDMA_GLO_CFG || reg==QDMA_GLO_CFG);assert(!(v&(TX_WB_DDONE|RX_DMA_EN|TX_DMA_EN)));}
static void udelay(unsigned int n) {assert(n==10);}
static void rt_sysc_m32(unsigned int clear,unsigned int set,unsigned int reg) {assert(!clear && set==BIT(26) && reg==0x34);event("pci-reset");pci_reset++;}
static void rt_sysc_w32(unsigned int value,unsigned int reg) {assert(value==BIT(0) && reg==0x34 && irq_off);event("system-reset");system_reset++;}
static void mdelay(unsigned int n) {assert(n==50 || n==1000);}
static void blocking_notifier_call_chain(int *list,int state,char *cmd) {assert(list==&reboot_notifier_list && state==SYS_RESTART);(void)cmd;event("notifier");}
static void usermodehelper_disable(void) {event("helpers");}
FUNCTION_PROTOTYPES
static void migrate_to_reboot_cpu(void) {event("migrate");migrate_calls++;if(late_phase==1)reboot_dma_failure_report(REBOOT_DMA_MT7615);}
static void syscore_shutdown(void) {event("syscore");syscore_calls++;if(late_phase==2)reboot_dma_failure_report(REBOOT_DMA_MT7615);}
static void kmsg_dump(int why) {(void)why;event("dump");}
static void do_kernel_restart(char *cmd) {(void)cmd;assert(0);}
static void (*_machine_restart)(char *);
#define machine_emergency_restart() machine_restart(NULL)
'''

SUFFIX = r'''
static void raeth_callback(struct device *d) {event("raeth");callbacks++;raether_shutdown(list_entry(d,struct platform_device,dev));}
static void pci_callback(struct device *d) {event("pci");callbacks++;pci_device_shutdown(d);}
static void *reporter(void *reason) {unsigned int bit=*(unsigned int *)reason;for(int n=0;n<20000;n++)reboot_dma_failure_report(bit);return NULL;}
int main(int argc,char **argv)
{
 assert(argc==2);const char *name=argv[1];CASE_ADMISSION
 static struct shutdown_ops r_ops={raeth_callback},p_ops={pci_callback};
 static struct pci_driver driver={rt_pci_shutdown};
 static struct platform_device platform={0};static struct pci_dev pci={0};
 static COOKIE cookie={.pci_dev=&pci,.dma_lifecycle_lock=PTHREAD_MUTEX_INITIALIZER,.dma_state_lock=PTHREAD_MUTEX_INITIALIZER};
 static struct END_DEVICE end={.features=FE_QDMA,.kreset_task=&cookie,.kphy_poll_task=&cookie};
 static struct net_device rdev={.name="eth0",.irq=1,.priv=&end},wdev={.name="ra0",.irq=2};
 static RTMP_ADAPTER ad={.OS_Cookie=&cookie,.net_dev=&wdev,.pci=true,.flags=fRTMP_ADAPTER_START_UP|fRTMP_ADAPTER_INTERRUPT_ACTIVE,.dma_running=1,.dma_lifecycle_pinned=1,.dma_irq_registered=1};
 wdev.adapter=&ad;platform.data=&rdev;platform.dev.driver=&r_ops;platform.dev.refs=1;pci.data=&wdev;pci.driver=&driver;pci.master=1;pci.dev.bus=&p_ops;pci.dev.refs=1;
 device_set.list.next=device_set.list.prev=&device_set.list;list_add_tail(&pci.dev.kobj.entry,&device_set.list);list_add_tail(&platform.dev.kobj.entry,&device_set.list);_machine_restart=ralink_restart;
 if(!strcmp(name,"raeth-pdma-busy"))busy_p=1;
 if(!strcmp(name,"raeth-qdma-busy"))busy_q=1;
 if(!strcmp(name,"wifi-busy"))idle_ok=0;
 if(!strcmp(name,"wifi-disable-failed"))disable_ok=0;
 if(!strcmp(name,"wifi-reset-failed"))reset_ok=0;
 if(!strcmp(name,"wifi-worker-failed"))worker_ok=0;
 if(!strcmp(name,"success-never-enabled")){ad.dma_running=ad.dma_lifecycle_pinned=ad.dma_irq_registered=0;}
 if(!strcmp(name,"quarantine-pure-oom")){ad.dma_running=ad.dma_lifecycle_pinned=ad.dma_irq_registered=0;RtmpDmaQuarantine(&ad);}
 if(!strcmp(name,"quarantine-quiesced")){ad.dma_running=0;ad.dma_quiesced=1;RtmpDmaQuarantine(&ad);}
 if(!strcmp(name,"quarantine-active") || !strcmp(name,"quarantine-then-idle")){RtmpDmaQuarantine(&ad);if(!strcmp(name,"quarantine-then-idle")){ad.dma_running=0;ad.dma_quiesced=1;}}
 if(!strcmp(name,"repeat-success-after-failure")){busy_p=1;assert(ei_stop_dma(&rdev));busy_p=0;assert(!ei_stop_dma(&rdev));}
 if(!strcmp(name,"normal-prelatched") || !strcmp(name,"prepare-only") || !strcmp(name,"park-spurious-wake"))reboot_dma_failure_report(REBOOT_DMA_RAETH);
 if(!strcmp(name,"park-spurious-wake"))sleep_returns=1;
 if(!strcmp(name,"emergency-latched") || !strcmp(name,"emergency-irq-off") || !strcmp(name,"direct-latched") || !strcmp(name,"direct-irq-off"))reboot_dma_failure_report(REBOOT_DMA_MT7615);
 if(!strcmp(name,"emergency-irq-off") || !strcmp(name,"direct-irq-off")){irq_off=1;in_irq=1;}
 if(!strcmp(name,"late-migrate"))late_phase=1;
 if(!strcmp(name,"late-syscore"))late_phase=2;
 if(!strcmp(name,"concurrent-report")){pthread_t threads[8];unsigned int bits[8];for(int n=0;n<8;n++){bits[n]=BIT(n);assert(!pthread_create(&threads[n],NULL,reporter,&bits[n]));}for(int n=0;n<8;n++)assert(!pthread_join(threads[n],NULL));}
 if(!strcmp(name,"zero-report"))reboot_dma_failure_report(0);
 if(!setjmp(terminal)) {
  if(!strcmp(name,"prepare-only"))kernel_restart_prepare(NULL);
  else if(!strncmp(name,"emergency-",10) || !strcmp(name,"success-emergency"))emergency_restart();
  else if(!strncmp(name,"direct-",7) || !strcmp(name,"success-direct"))ralink_restart(NULL);
  else kernel_restart(NULL);
 }
 assert(owners==8 && !rtnl_depth && !lifecycle_depth && platform.data==&rdev && pci.data==&wdev && ad.net_dev==&wdev);
 printf("{\"reasons\":%u,\"terminal\":%d,\"sleeps\":%d,\"spins\":%d,\"irq_off\":%d,\"callbacks\":%d,\"migrate\":%d,\"syscore\":%d,\"pci_reset\":%d,\"system_reset\":%d,\"stop\":%d,\"idle\":%d,\"reset\":%d,\"p_reads\":%d,\"q_reads\":%d,\"clear_master\":%d,\"wifi_quarantine\":%d,\"wifi_quiesced\":%d,\"raeth_quarantine\":%d,\"owners\":%d,\"workers\":%d,\"commands\":%d,\"irq_sync\":%d,\"events\":\"%s\"}\n",reboot_dma_failures(),terminal_kind,sleeps,spins,irq_off,callbacks,migrate_calls,syscore_calls,pci_reset,system_reset,stop_calls,idle_calls,reset_calls,p_reads,q_reads,clear_master_calls,ad.dma_quarantined,ad.dma_quiesced,end.dma_quarantined,owners,worker_calls,command_calls,irq_sync,events);
 return 0;
}
'''


def declarations(texts):
    rows = []
    for pattern, key in SOURCE_DECLARATIONS.items():
        found = re.findall(pattern, texts[key], re.M)
        if len(found) != 1:
            raise ValueError('Missing restart declaration: ' + pattern)
        rows.append(found[0])
    return '\n'.join(rows)


def generate_source(texts, baseline=False):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact restart source inputs required')
    names = [n for n in FUNCTION_SOURCES if not (baseline and n in NEW_FUNCTIONS)]
    bodies = [function(texts[FUNCTION_SOURCES[n]], n) for n in names]
    prototypes = '\n'.join(b.split('{', 1)[0].strip() + ';' for b in bodies)
    api = ''
    if baseline:
        # f9 has no ledger/API. These inert API seams only allow the same test
        # scenario to present a report to that absent facility; f9 bodies are exact.
        api = ('void reboot_dma_failure_report(unsigned int reasons){(void)reasons;}\n'
               'unsigned int reboot_dma_failures(void){return 0;}\n')
    else:
        match = re.search(r'^static atomic_t reboot_dma_failure_reasons = ATOMIC_INIT\(0\);$', texts['reboot'], re.M)
        if not match:
            raise ValueError('Missing sticky ledger declaration')
        api = match.group()
    # Prototypes must precede hardware/migration seams as well as real bodies.
    prefix = PREFIX.replace('SOURCE_DEFINITIONS', declarations(texts)).replace(
        'FUNCTION_PROTOTYPES', prototypes + '\nvoid reboot_dma_failure_report(unsigned int);\nunsigned int reboot_dma_failures(void);')
    admission = 'if(!(' + '||'.join('!strcmp(name,"' + n + '")' for n in CASE_NAMES) + '))return 91;'
    if baseline:
        # Host atomics are unused when the actual old core has no ledger.
        prefix = re.sub(r'static void atomic_or[^\n]+\nstatic unsigned int atomic_read[^\n]+\n', '', prefix)
        prefix = re.sub(r'static long schedule_timeout_uninterruptible[^\n]+\nstatic void cpu_relax[^\n]+\n', '', prefix)
        prefix = re.sub(r'static inline struct net_device \*pci_get_drvdata[^\n]+\n', '', prefix)
    return prefix + '\n' + api + '\n' + '\n'.join(bodies) + SUFFIX.replace('CASE_ADMISSION', admission)
