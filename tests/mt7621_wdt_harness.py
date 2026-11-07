"""Whole MT762x stop and watchdog core ioctl; inert MMIO, selected pthread schedules."""
import hashlib
import re

SOURCE_PATHS = {'driver': 'trunk/linux-4.4.x/drivers/watchdog/mt7621_wdt.c',
 'core': 'trunk/linux-4.4.x/drivers/watchdog/watchdog_dev.c',
 'header': 'trunk/linux-4.4.x/include/linux/watchdog.h',
 'uapi': 'trunk/linux-4.4.x/include/uapi/linux/watchdog.h',
 'dts': 'trunk/linux-4.4.x/arch/mips/boot/dts/ralink/mt7621.dtsi'}
BODY_ORDER = ('watchdog_active', 'watchdog_timeout_invalid', 'rt_wdt_w32',
              'rt_wdt_r32', 'mt762x_wdt_ping', 'mt762x_wdt_set_timeout',
              'mt762x_wdt_start', 'mt762x_wdt_stop', 'watchdog_ping',
              'watchdog_start', 'watchdog_stop', 'watchdog_get_status',
              'watchdog_set_timeout', 'watchdog_get_timeleft',
              'watchdog_ioctl_op', 'watchdog_ioctl', 'watchdog_set_nowayout',
              'mt762x_wdt_bootcause', 'mt762x_wdt_probe')
FUNCTION_SOURCES = {'watchdog_active': 'header',
 'watchdog_timeout_invalid': 'header',
 'rt_wdt_w32': 'driver',
 'rt_wdt_r32': 'driver',
 'mt762x_wdt_ping': 'driver',
 'mt762x_wdt_set_timeout': 'driver',
 'mt762x_wdt_start': 'driver',
 'mt762x_wdt_stop': 'driver',
 'watchdog_ping': 'core',
 'watchdog_start': 'core',
 'watchdog_stop': 'core',
 'watchdog_get_status': 'core',
 'watchdog_set_timeout': 'core',
 'watchdog_get_timeleft': 'core',
 'watchdog_ioctl_op': 'core',
 'watchdog_ioctl': 'core',
 'watchdog_set_nowayout': 'header',
 'mt762x_wdt_bootcause': 'driver',
 'mt762x_wdt_probe': 'driver'}
SOURCE_ONLY_FUNCTION_SOURCES = {}
FUNCTION_DECLARATIONS = ''
BASELINE_COMMIT = 'f9c361f682eb742423dd9ebd422a1952af2ec6e0'
BASELINE_FIXTURE_PATH = 'tests/fixtures/mt7621-wdt/f9.json'
BASELINE_FIXTURE_SHA256 = '3cb28a8d98bd351b431bd6197968231696fbf1f5585275a0cf43cc3394414290'
BASELINE_BODY = 'static int mt762x_wdt_stop(struct watchdog_device *w)\n{\n\tu32 t;\n\n\tmt762x_wdt_ping(w);\n\n\tt = rt_wdt_r32(TIMER_REG_TMR1CTL);\n\tt &= ~TMR1CTL_ENABLE;\n\trt_wdt_w32(TIMER_REG_TMR1CTL, t);\n\n\treturn 0;\n}'
BASELINE_SHA256 = 'f9207d3b6242f80c161a61ea98c29b98acaed6af1dd3303ac193f40c05f10634'
BASELINE_PROBE_BODY = 'static int mt762x_wdt_probe(struct platform_device *pdev)\n{\n\tstruct resource *res;\n\tint ret;\n\n\tres = platform_get_resource(pdev, IORESOURCE_MEM, 0);\n\tmt762x_wdt_base = devm_ioremap_resource(&pdev->dev, res);\n\tif (IS_ERR(mt762x_wdt_base))\n\t\treturn PTR_ERR(mt762x_wdt_base);\n\n\tdevice_reset(&pdev->dev);\n\n\tmt762x_wdt_dev.dev = &pdev->dev;\n\tmt762x_wdt_dev.bootstatus = mt762x_wdt_bootcause();\n\tmt762x_wdt_dev.max_timeout = (0xfffful / 1000);\n\tmt762x_wdt_dev.timeout = mt762x_wdt_dev.max_timeout;\n\n\twatchdog_set_nowayout(&mt762x_wdt_dev, nowayout);\n\n\tret = watchdog_register_device(&mt762x_wdt_dev);\n\tif (!ret)\n\t\tdev_info(&pdev->dev, "Initialized\\n");\n\n\treturn 0;\n}'
BASELINE_PROBE_SHA256 = '8ddf5c5ff628948346f2a170301cc327351a677bf98c6b0aa81f7f3e8bbed102'
BASELINE_FUNCTIONS = {'mt762x_wdt_stop': BASELINE_BODY, 'mt762x_wdt_probe': BASELINE_PROBE_BODY}
BASELINE_FUNCTIONS_SHA256 = {'mt762x_wdt_stop': BASELINE_SHA256, 'mt762x_wdt_probe': BASELINE_PROBE_SHA256}
MODEL_VARIANT = {
    'whole_function_execution': True,
    'synthetic_watchdog_device_layout': True,
    'real_watchdog_ioctl_and_stop_wrapper': True,
    'selected_pthread_mutex_schedules_not_kernel_scheduling': True,
    'inert_mmio_not_actual_hardware_or_bus_posting': True,
    'inactive_core_success_does_not_recheck_hardware': True,
    'only_future_booted_fixed_kernel_gets_readback': True,
    'legacy_running_driver_and_upgrade_bridge_not_proven': True,
    'inert_probe_reset_callback_has_no_hardware_effect': True,
    'probe_failure_may_leave_hardware_running': True,
}
FIELDS = ('ret', 'second', 'enabled', 'active', 'status', 'reads',
          'control_writes', 'pings', 'loads', 'contended', 'unlocked_mmio',
          'control_other', 'map_calls', 'reset_calls', 'register_calls',
          'probe_timeout', 'probe_max', 'probe_bootstatus')
CASE_NAMES = ('driver-normal',
 'driver-inactive',
 'driver-stuck',
 'driver-droppedwrite',
 'disable-normal',
 'disable-stuck',
 'disable-droppedwrite',
 'disable-inactive',
 'disable-inactive-hardware-enabled',
 'disable-nowayout',
 'disable-unregistered',
 'disable-bad-user',
 'disable-stuck-retry',
 'disable-dropped-retry',
 'disable-enable',
 'disable-enable-stuck',
 'noop-options',
 'enable-inactive',
 'enable-active',
 'enable-unregistered',
 'disable-preserve-flags',
 'disable-stuck-preserve-flags',
 'concurrent-disable-disable',
 'concurrent-stuck-disable',
 'concurrent-disable-enable',
 'concurrent-stuck-enable',
 'probe-normal',
 'probe-no-resource',
 'probe-map-error',
 'probe-reset-error',
 'probe-reset-defer',
 'probe-stuck',
 'probe-droppedwrite',
 'probe-register-error',
 'probe-nowayout',
 'probe-declared-reset',
 'probe-declared-missing-provider')


def row(ret=0, second=999, enabled=0, active=0, status=0, reads=0,
        control_writes=0, pings=0, loads=0, contended=0, unlocked_mmio=0,
        control_other=0x12340000, map_calls=0, reset_calls=0, register_calls=0,
        probe_timeout=0, probe_max=0, probe_bootstatus=0):
    return dict(zip(FIELDS, (ret, second, enabled, active, status, reads,
                            control_writes, pings, loads, contended,
                            unlocked_mmio, control_other, map_calls, reset_calls,
                            register_calls, probe_timeout, probe_max, probe_bootstatus)))


EXPECTED_ROWS = {'driver-normal': {'ret': 0,
                   'second': 999,
                   'enabled': 0,
                   'active': 1,
                   'status': 1,
                   'reads': 2,
                   'control_writes': 1,
                   'pings': 1,
                   'loads': 0,
                   'contended': 0,
                   'unlocked_mmio': 4,
                   'control_other': 305397760,
                   'map_calls': 0,
                   'reset_calls': 0,
                   'register_calls': 0,
                   'probe_timeout': 0,
                   'probe_max': 0,
                   'probe_bootstatus': 0},
 'driver-inactive': {'ret': 0,
                     'second': 999,
                     'enabled': 0,
                     'active': 0,
                     'status': 0,
                     'reads': 2,
                     'control_writes': 1,
                     'pings': 1,
                     'loads': 0,
                     'contended': 0,
                     'unlocked_mmio': 4,
                     'control_other': 305397760,
                     'map_calls': 0,
                     'reset_calls': 0,
                     'register_calls': 0,
                     'probe_timeout': 0,
                     'probe_max': 0,
                     'probe_bootstatus': 0},
 'driver-stuck': {'ret': -5,
                  'second': 999,
                  'enabled': 1,
                  'active': 1,
                  'status': 1,
                  'reads': 2,
                  'control_writes': 1,
                  'pings': 1,
                  'loads': 0,
                  'contended': 0,
                  'unlocked_mmio': 4,
                  'control_other': 305397760,
                  'map_calls': 0,
                  'reset_calls': 0,
                  'register_calls': 0,
                  'probe_timeout': 0,
                  'probe_max': 0,
                  'probe_bootstatus': 0},
 'driver-droppedwrite': {'ret': -5,
                         'second': 999,
                         'enabled': 1,
                         'active': 1,
                         'status': 1,
                         'reads': 2,
                         'control_writes': 1,
                         'pings': 1,
                         'loads': 0,
                         'contended': 0,
                         'unlocked_mmio': 4,
                         'control_other': 305397760,
                         'map_calls': 0,
                         'reset_calls': 0,
                         'register_calls': 0,
                         'probe_timeout': 0,
                         'probe_max': 0,
                         'probe_bootstatus': 0},
 'disable-normal': {'ret': 0,
                    'second': 999,
                    'enabled': 0,
                    'active': 0,
                    'status': 0,
                    'reads': 2,
                    'control_writes': 1,
                    'pings': 1,
                    'loads': 0,
                    'contended': 0,
                    'unlocked_mmio': 0,
                    'control_other': 305397760,
                    'map_calls': 0,
                    'reset_calls': 0,
                    'register_calls': 0,
                    'probe_timeout': 0,
                    'probe_max': 0,
                    'probe_bootstatus': 0},
 'disable-stuck': {'ret': -5,
                   'second': 999,
                   'enabled': 1,
                   'active': 1,
                   'status': 1,
                   'reads': 2,
                   'control_writes': 1,
                   'pings': 1,
                   'loads': 0,
                   'contended': 0,
                   'unlocked_mmio': 0,
                   'control_other': 305397760,
                   'map_calls': 0,
                   'reset_calls': 0,
                   'register_calls': 0,
                   'probe_timeout': 0,
                   'probe_max': 0,
                   'probe_bootstatus': 0},
 'disable-droppedwrite': {'ret': -5,
                          'second': 999,
                          'enabled': 1,
                          'active': 1,
                          'status': 1,
                          'reads': 2,
                          'control_writes': 1,
                          'pings': 1,
                          'loads': 0,
                          'contended': 0,
                          'unlocked_mmio': 0,
                          'control_other': 305397760,
                          'map_calls': 0,
                          'reset_calls': 0,
                          'register_calls': 0,
                          'probe_timeout': 0,
                          'probe_max': 0,
                          'probe_bootstatus': 0},
 'disable-inactive': {'ret': 0,
                      'second': 999,
                      'enabled': 0,
                      'active': 0,
                      'status': 0,
                      'reads': 0,
                      'control_writes': 0,
                      'pings': 0,
                      'loads': 0,
                      'contended': 0,
                      'unlocked_mmio': 0,
                      'control_other': 305397760,
                      'map_calls': 0,
                      'reset_calls': 0,
                      'register_calls': 0,
                      'probe_timeout': 0,
                      'probe_max': 0,
                      'probe_bootstatus': 0},
 'disable-inactive-hardware-enabled': {'ret': 0,
                                       'second': 999,
                                       'enabled': 1,
                                       'active': 0,
                                       'status': 0,
                                       'reads': 0,
                                       'control_writes': 0,
                                       'pings': 0,
                                       'loads': 0,
                                       'contended': 0,
                                       'unlocked_mmio': 0,
                                       'control_other': 305397760,
                                       'map_calls': 0,
                                       'reset_calls': 0,
                                       'register_calls': 0,
                                       'probe_timeout': 0,
                                       'probe_max': 0,
                                       'probe_bootstatus': 0},
 'disable-nowayout': {'ret': -16,
                      'second': 999,
                      'enabled': 1,
                      'active': 1,
                      'status': 9,
                      'reads': 0,
                      'control_writes': 0,
                      'pings': 0,
                      'loads': 0,
                      'contended': 0,
                      'unlocked_mmio': 0,
                      'control_other': 305397760,
                      'map_calls': 0,
                      'reset_calls': 0,
                      'register_calls': 0,
                      'probe_timeout': 0,
                      'probe_max': 0,
                      'probe_bootstatus': 0},
 'disable-unregistered': {'ret': -19,
                          'second': 999,
                          'enabled': 1,
                          'active': 1,
                          'status': 17,
                          'reads': 0,
                          'control_writes': 0,
                          'pings': 0,
                          'loads': 0,
                          'contended': 0,
                          'unlocked_mmio': 0,
                          'control_other': 305397760,
                          'map_calls': 0,
                          'reset_calls': 0,
                          'register_calls': 0,
                          'probe_timeout': 0,
                          'probe_max': 0,
                          'probe_bootstatus': 0},
 'disable-bad-user': {'ret': -14,
                      'second': 999,
                      'enabled': 1,
                      'active': 1,
                      'status': 1,
                      'reads': 0,
                      'control_writes': 0,
                      'pings': 0,
                      'loads': 0,
                      'contended': 0,
                      'unlocked_mmio': 0,
                      'control_other': 305397760,
                      'map_calls': 0,
                      'reset_calls': 0,
                      'register_calls': 0,
                      'probe_timeout': 0,
                      'probe_max': 0,
                      'probe_bootstatus': 0},
 'disable-stuck-retry': {'ret': -5,
                         'second': 0,
                         'enabled': 0,
                         'active': 0,
                         'status': 0,
                         'reads': 4,
                         'control_writes': 2,
                         'pings': 2,
                         'loads': 0,
                         'contended': 0,
                         'unlocked_mmio': 0,
                         'control_other': 305397760,
                         'map_calls': 0,
                         'reset_calls': 0,
                         'register_calls': 0,
                         'probe_timeout': 0,
                         'probe_max': 0,
                         'probe_bootstatus': 0},
 'disable-dropped-retry': {'ret': -5,
                           'second': 0,
                           'enabled': 0,
                           'active': 0,
                           'status': 0,
                           'reads': 4,
                           'control_writes': 2,
                           'pings': 2,
                           'loads': 0,
                           'contended': 0,
                           'unlocked_mmio': 0,
                           'control_other': 305397760,
                           'map_calls': 0,
                           'reset_calls': 0,
                           'register_calls': 0,
                           'probe_timeout': 0,
                           'probe_max': 0,
                           'probe_bootstatus': 0},
 'disable-enable': {'ret': 0,
                    'second': 999,
                    'enabled': 1,
                    'active': 1,
                    'status': 1,
                    'reads': 3,
                    'control_writes': 3,
                    'pings': 2,
                    'loads': 1,
                    'contended': 0,
                    'unlocked_mmio': 0,
                    'control_other': 65536000,
                    'map_calls': 0,
                    'reset_calls': 0,
                    'register_calls': 0,
                    'probe_timeout': 0,
                    'probe_max': 0,
                    'probe_bootstatus': 0},
 'disable-enable-stuck': {'ret': -5,
                          'second': 999,
                          'enabled': 1,
                          'active': 1,
                          'status': 1,
                          'reads': 2,
                          'control_writes': 1,
                          'pings': 1,
                          'loads': 0,
                          'contended': 0,
                          'unlocked_mmio': 0,
                          'control_other': 305397760,
                          'map_calls': 0,
                          'reset_calls': 0,
                          'register_calls': 0,
                          'probe_timeout': 0,
                          'probe_max': 0,
                          'probe_bootstatus': 0},
 'noop-options': {'ret': 0,
                  'second': 999,
                  'enabled': 1,
                  'active': 1,
                  'status': 1,
                  'reads': 0,
                  'control_writes': 0,
                  'pings': 0,
                  'loads': 0,
                  'contended': 0,
                  'unlocked_mmio': 0,
                  'control_other': 305397760,
                  'map_calls': 0,
                  'reset_calls': 0,
                  'register_calls': 0,
                  'probe_timeout': 0,
                  'probe_max': 0,
                  'probe_bootstatus': 0},
 'enable-inactive': {'ret': 0,
                     'second': 999,
                     'enabled': 1,
                     'active': 1,
                     'status': 1,
                     'reads': 1,
                     'control_writes': 2,
                     'pings': 1,
                     'loads': 1,
                     'contended': 0,
                     'unlocked_mmio': 0,
                     'control_other': 65536000,
                     'map_calls': 0,
                     'reset_calls': 0,
                     'register_calls': 0,
                     'probe_timeout': 0,
                     'probe_max': 0,
                     'probe_bootstatus': 0},
 'enable-active': {'ret': 0,
                   'second': 999,
                   'enabled': 1,
                   'active': 1,
                   'status': 1,
                   'reads': 0,
                   'control_writes': 0,
                   'pings': 0,
                   'loads': 0,
                   'contended': 0,
                   'unlocked_mmio': 0,
                   'control_other': 305397760,
                   'map_calls': 0,
                   'reset_calls': 0,
                   'register_calls': 0,
                   'probe_timeout': 0,
                   'probe_max': 0,
                   'probe_bootstatus': 0},
 'enable-unregistered': {'ret': -19,
                         'second': 999,
                         'enabled': 0,
                         'active': 0,
                         'status': 16,
                         'reads': 0,
                         'control_writes': 0,
                         'pings': 0,
                         'loads': 0,
                         'contended': 0,
                         'unlocked_mmio': 0,
                         'control_other': 305397760,
                         'map_calls': 0,
                         'reset_calls': 0,
                         'register_calls': 0,
                         'probe_timeout': 0,
                         'probe_max': 0,
                         'probe_bootstatus': 0},
 'disable-preserve-flags': {'ret': 0,
                            'second': 999,
                            'enabled': 0,
                            'active': 0,
                            'status': 6,
                            'reads': 2,
                            'control_writes': 1,
                            'pings': 1,
                            'loads': 0,
                            'contended': 0,
                            'unlocked_mmio': 0,
                            'control_other': 305397760,
                            'map_calls': 0,
                            'reset_calls': 0,
                            'register_calls': 0,
                            'probe_timeout': 0,
                            'probe_max': 0,
                            'probe_bootstatus': 0},
 'disable-stuck-preserve-flags': {'ret': -5,
                                  'second': 999,
                                  'enabled': 1,
                                  'active': 1,
                                  'status': 7,
                                  'reads': 2,
                                  'control_writes': 1,
                                  'pings': 1,
                                  'loads': 0,
                                  'contended': 0,
                                  'unlocked_mmio': 0,
                                  'control_other': 305397760,
                                  'map_calls': 0,
                                  'reset_calls': 0,
                                  'register_calls': 0,
                                  'probe_timeout': 0,
                                  'probe_max': 0,
                                  'probe_bootstatus': 0},
 'concurrent-disable-disable': {'ret': 0,
                                'second': 0,
                                'enabled': 0,
                                'active': 0,
                                'status': 0,
                                'reads': 2,
                                'control_writes': 1,
                                'pings': 1,
                                'loads': 0,
                                'contended': 1,
                                'unlocked_mmio': 0,
                                'control_other': 305397760,
                                'map_calls': 0,
                                'reset_calls': 0,
                                'register_calls': 0,
                                'probe_timeout': 0,
                                'probe_max': 0,
                                'probe_bootstatus': 0},
 'concurrent-stuck-disable': {'ret': -5,
                              'second': -5,
                              'enabled': 1,
                              'active': 1,
                              'status': 1,
                              'reads': 4,
                              'control_writes': 2,
                              'pings': 2,
                              'loads': 0,
                              'contended': 1,
                              'unlocked_mmio': 0,
                              'control_other': 305397760,
                              'map_calls': 0,
                              'reset_calls': 0,
                              'register_calls': 0,
                              'probe_timeout': 0,
                              'probe_max': 0,
                              'probe_bootstatus': 0},
 'concurrent-disable-enable': {'ret': 0,
                               'second': 0,
                               'enabled': 1,
                               'active': 1,
                               'status': 1,
                               'reads': 3,
                               'control_writes': 3,
                               'pings': 2,
                               'loads': 1,
                               'contended': 1,
                               'unlocked_mmio': 0,
                               'control_other': 65536000,
                               'map_calls': 0,
                               'reset_calls': 0,
                               'register_calls': 0,
                               'probe_timeout': 0,
                               'probe_max': 0,
                               'probe_bootstatus': 0},
 'concurrent-stuck-enable': {'ret': -5,
                             'second': 0,
                             'enabled': 1,
                             'active': 1,
                             'status': 1,
                             'reads': 2,
                             'control_writes': 1,
                             'pings': 1,
                             'loads': 0,
                             'contended': 1,
                             'unlocked_mmio': 0,
                             'control_other': 305397760,
                             'map_calls': 0,
                             'reset_calls': 0,
                             'register_calls': 0,
                             'probe_timeout': 0,
                             'probe_max': 0,
                             'probe_bootstatus': 0},
 'probe-normal': {'ret': 0,
                  'second': 999,
                  'enabled': 0,
                  'active': 0,
                  'status': 0,
                  'reads': 2,
                  'control_writes': 1,
                  'pings': 1,
                  'loads': 0,
                  'contended': 0,
                  'unlocked_mmio': 4,
                  'control_other': 305397760,
                  'map_calls': 1,
                  'reset_calls': 0,
                  'register_calls': 1,
                  'probe_timeout': 65,
                  'probe_max': 65,
                  'probe_bootstatus': 32},
 'probe-no-resource': {'ret': -22,
                       'second': 999,
                       'enabled': 1,
                       'active': 0,
                       'status': 0,
                       'reads': 0,
                       'control_writes': 0,
                       'pings': 0,
                       'loads': 0,
                       'contended': 0,
                       'unlocked_mmio': 0,
                       'control_other': 305397760,
                       'map_calls': 1,
                       'reset_calls': 0,
                       'register_calls': 0,
                       'probe_timeout': 0,
                       'probe_max': 0,
                       'probe_bootstatus': 0},
 'probe-map-error': {'ret': -12,
                     'second': 999,
                     'enabled': 1,
                     'active': 0,
                     'status': 0,
                     'reads': 0,
                     'control_writes': 0,
                     'pings': 0,
                     'loads': 0,
                     'contended': 0,
                     'unlocked_mmio': 0,
                     'control_other': 305397760,
                     'map_calls': 1,
                     'reset_calls': 0,
                     'register_calls': 0,
                     'probe_timeout': 0,
                     'probe_max': 0,
                     'probe_bootstatus': 0},
 'probe-reset-error': {'ret': -5,
                       'second': 999,
                       'enabled': 1,
                       'active': 0,
                       'status': 0,
                       'reads': 0,
                       'control_writes': 0,
                       'pings': 0,
                       'loads': 0,
                       'contended': 0,
                       'unlocked_mmio': 0,
                       'control_other': 305397760,
                       'map_calls': 1,
                       'reset_calls': 1,
                       'register_calls': 0,
                       'probe_timeout': 0,
                       'probe_max': 0,
                       'probe_bootstatus': 0},
 'probe-reset-defer': {'ret': -517,
                       'second': 999,
                       'enabled': 1,
                       'active': 0,
                       'status': 0,
                       'reads': 0,
                       'control_writes': 0,
                       'pings': 0,
                       'loads': 0,
                       'contended': 0,
                       'unlocked_mmio': 0,
                       'control_other': 305397760,
                       'map_calls': 1,
                       'reset_calls': 1,
                       'register_calls': 0,
                       'probe_timeout': 0,
                       'probe_max': 0,
                       'probe_bootstatus': 0},
 'probe-stuck': {'ret': -5,
                 'second': 999,
                 'enabled': 1,
                 'active': 0,
                 'status': 0,
                 'reads': 2,
                 'control_writes': 1,
                 'pings': 1,
                 'loads': 0,
                 'contended': 0,
                 'unlocked_mmio': 4,
                 'control_other': 305397760,
                 'map_calls': 1,
                 'reset_calls': 0,
                 'register_calls': 0,
                 'probe_timeout': 0,
                 'probe_max': 0,
                 'probe_bootstatus': 0},
 'probe-droppedwrite': {'ret': -5,
                        'second': 999,
                        'enabled': 1,
                        'active': 0,
                        'status': 0,
                        'reads': 2,
                        'control_writes': 1,
                        'pings': 1,
                        'loads': 0,
                        'contended': 0,
                        'unlocked_mmio': 4,
                        'control_other': 305397760,
                        'map_calls': 1,
                        'reset_calls': 0,
                        'register_calls': 0,
                        'probe_timeout': 0,
                        'probe_max': 0,
                        'probe_bootstatus': 0},
 'probe-register-error': {'ret': -16,
                          'second': 999,
                          'enabled': 0,
                          'active': 0,
                          'status': 0,
                          'reads': 2,
                          'control_writes': 1,
                          'pings': 1,
                          'loads': 0,
                          'contended': 0,
                          'unlocked_mmio': 4,
                          'control_other': 305397760,
                          'map_calls': 1,
                          'reset_calls': 0,
                          'register_calls': 1,
                          'probe_timeout': 65,
                          'probe_max': 65,
                          'probe_bootstatus': 32},
 'probe-nowayout': {'ret': 0,
                    'second': 999,
                    'enabled': 0,
                    'active': 0,
                    'status': 8,
                    'reads': 2,
                    'control_writes': 1,
                    'pings': 1,
                    'loads': 0,
                    'contended': 0,
                    'unlocked_mmio': 4,
                    'control_other': 305397760,
                    'map_calls': 1,
                    'reset_calls': 0,
                    'register_calls': 1,
                    'probe_timeout': 65,
                    'probe_max': 65,
                    'probe_bootstatus': 32},
 'probe-declared-reset': {'ret': 0,
                          'second': 999,
                          'enabled': 0,
                          'active': 0,
                          'status': 0,
                          'reads': 2,
                          'control_writes': 1,
                          'pings': 1,
                          'loads': 0,
                          'contended': 0,
                          'unlocked_mmio': 4,
                          'control_other': 305397760,
                          'map_calls': 1,
                          'reset_calls': 1,
                          'register_calls': 1,
                          'probe_timeout': 65,
                          'probe_max': 65,
                          'probe_bootstatus': 32},
 'probe-declared-missing-provider': {'ret': -2,
                                     'second': 999,
                                     'enabled': 1,
                                     'active': 0,
                                     'status': 0,
                                     'reads': 0,
                                     'control_writes': 0,
                                     'pings': 0,
                                     'loads': 0,
                                     'contended': 0,
                                     'unlocked_mmio': 0,
                                     'control_other': 305397760,
                                     'map_calls': 1,
                                     'reset_calls': 1,
                                     'register_calls': 0,
                                     'probe_timeout': 0,
                                     'probe_max': 0,
                                     'probe_bootstatus': 0}}

RAW_PREFIX = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <sys/ioctl.h>
#define __user
#define ENOIOCTLCMD 515
#define IORESOURCE_MEM 0x200
#define IS_ERR(pointer) ((uintptr_t)(pointer) >= (uintptr_t)-4095)
#define PTR_ERR(pointer) ((long)(pointer))
typedef uint32_t u32;
typedef uint32_t __u32;
typedef uint8_t __u8;
typedef int bool;
#define BIT(n) (1U << (n))
#define dev_info(...) ((void)0)
struct watchdog_device;
struct watchdog_ops {
 int (*start)(struct watchdog_device *);
 int (*stop)(struct watchdog_device *);
 int (*ping)(struct watchdog_device *);
 unsigned int (*status)(struct watchdog_device *);
 int (*set_timeout)(struct watchdog_device *, unsigned int);
 unsigned int (*get_timeleft)(struct watchdog_device *);
 long (*ioctl)(struct watchdog_device *, unsigned int, unsigned long);
};
struct mutex { pthread_mutex_t native; };
struct watchdog_device {
 const struct watchdog_info *info;
 const struct watchdog_ops *ops;
 void *dev;
 unsigned int bootstatus, timeout, min_timeout, max_timeout;
 struct mutex lock;
 unsigned long status;
};
struct file { void *private_data; };
struct device { void *of_node; };
struct platform_device { struct device dev; };
struct resource { int unused; };
static struct watchdog_device mt762x_wdt_dev;
static bool nowayout;
static int map_error, reset_error, register_error, no_resource, declared_reset;
static unsigned int map_calls, reset_calls, register_calls;
static struct resource resource;
static pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static __thread int core_lock_depth;
static int schedule_enabled, paused, release_write, contended;
static int fault, fault_limit = -1, faulted;
static unsigned int reads, control_writes, pings, loads, unlocked_mmio;
static u32 control;
static unsigned char mmio_window[0x28];
static void *mt762x_wdt_base = mmio_window;
static void checked(int ret) { if (ret) abort(); }
static void mutex_lock(struct mutex *lock)
{
 int ret = pthread_mutex_trylock(&lock->native);
 if (ret == EBUSY) {
  checked(pthread_mutex_lock(&gate));
  contended = 1;
  checked(pthread_cond_broadcast(&changed));
  checked(pthread_mutex_unlock(&gate));
  checked(pthread_mutex_lock(&lock->native));
 } else checked(ret);
 core_lock_depth++;
}
static void mutex_unlock(struct mutex *lock)
{
 if (core_lock_depth != 1) abort();
 core_lock_depth--;
 checked(pthread_mutex_unlock(&lock->native));
}
static int test_bit(unsigned int bit, const unsigned long *value) { return !!(*value & (1UL << bit)); }
static void set_bit(unsigned int bit, unsigned long *value) { *value |= 1UL << bit; }
static void clear_bit(unsigned int bit, unsigned long *value) { *value &= ~(1UL << bit); }
static int user_read(unsigned int *value, const int *pointer)
{
 if (!pointer) return -EFAULT;
 *value = (unsigned int)*pointer;
 return 0;
}
#define get_user(value,pointer) user_read(&(value), (pointer))
#define put_user(value,pointer) ((pointer) ? (*(pointer) = (value), 0) : -EFAULT)
#define copy_to_user(target,source,size) ((target) ? (memcpy((target),(source),(size)), 0) : 1)
'''

MMIO = r'''
static __attribute__((unused)) const void *of_find_property(void *node, const char *name, int *length)
{
 if (strcmp(name, "resets") || length) abort();
 return declared_reset ? &resource : NULL;
}

static struct resource *platform_get_resource(struct platform_device *pdev, unsigned int type, unsigned int index)
{
 if (type != IORESOURCE_MEM || index) abort();
 return no_resource ? NULL : &resource;
}
static void *devm_ioremap_resource(struct device *device, struct resource *res)
{
 map_calls++;
 if (!res) return (void *)(intptr_t)-EINVAL;
 if (map_error) return (void *)(intptr_t)map_error;
 return mmio_window;
}
static int device_reset(struct device *device) { reset_calls++; return reset_error; }
static int watchdog_register_device(struct watchdog_device *device)
{
 if (device != &mt762x_wdt_dev) abort();
 register_calls++;
 return register_error;
}
static u32 rt_sysc_r32(unsigned int reg)
{
 if (reg != SYSC_RSTSTAT) abort();
 return WDT_RST_CAUSE;
}
static void iowrite32(u32 value, void *address)
{
 unsigned int reg = (unsigned char *)address - mmio_window;
 unlocked_mmio += core_lock_depth == 0;
 if (reg == TIMER_REG_TMRSTAT) {
  if (value != TMR1CTL_RESTART) abort();
  pings++;
 } else if (reg == TIMER_REG_TMR1LOAD) {
  if (value != 30000) abort();
  loads++;
 } else if (reg == TIMER_REG_TMR1CTL) {
  control_writes++;
  if (schedule_enabled && control_writes == 1) {
   checked(pthread_mutex_lock(&gate));
   paused = 1;
   checked(pthread_cond_broadcast(&changed));
   while (!release_write) checked(pthread_cond_wait(&changed, &gate));
   checked(pthread_mutex_unlock(&gate));
  }
  if (!(value & TMR1CTL_ENABLE) && (control & TMR1CTL_ENABLE) &&
      fault && (fault_limit < 0 || faulted < fault_limit)) {
   faulted++;
   if (fault == 1) control = value | TMR1CTL_ENABLE;
   /* fault 2 drops the complete control-register write. */
  } else control = value;
 } else abort();
}
static u32 ioread32(void *address)
{
 if ((unsigned char *)address - mmio_window != TIMER_REG_TMR1CTL) abort();
 unlocked_mmio += core_lock_depth == 0;
 reads++;
 return control;
}
'''


SOURCE_DECLARATIONS = {'(^#define[ \\t]+SYSC_RSTSTAT[ \\t]+[^\\n]+$)': 'driver',
 '(^#define[ \\t]+WDT_RST_CAUSE[ \\t]+[^\\n]+$)': 'driver',
 '(^#define[ \\t]+TIMER_REG_TMRSTAT[ \\t]+[^\\n]+$)': 'driver',
 '(^#define[ \\t]+TIMER_REG_TMR1LOAD[ \\t]+[^\\n]+$)': 'driver',
 '(^#define[ \\t]+TIMER_REG_TMR1CTL[ \\t]+[^\\n]+$)': 'driver',
 '(^#define[ \\t]+TMR1CTL_ENABLE[ \\t]+[^\\n]+$)': 'driver',
 '(^#define[ \\t]+TMR1CTL_RESTART[ \\t]+[^\\n]+$)': 'driver',
 '(^#define[ \\t]+WDOG_ACTIVE[ \\t]+[^\\n]+$)': 'header',
 '(^#define[ \\t]+WDOG_DEV_OPEN[ \\t]+[^\\n]+$)': 'header',
 '(^#define[ \\t]+WDOG_ALLOW_RELEASE[ \\t]+[^\\n]+$)': 'header',
 '(^#define[ \\t]+WDOG_NO_WAY_OUT[ \\t]+[^\\n]+$)': 'header',
 '(^#define[ \\t]+WDOG_UNREGISTERED[ \\t]+[^\\n]+$)': 'header',
 '(^#define[ \\t]+WATCHDOG_IOCTL_BASE[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOC_GETSUPPORT[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOC_GETSTATUS[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOC_GETBOOTSTATUS[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOC_SETOPTIONS[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOC_KEEPALIVE[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOC_SETTIMEOUT[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOC_GETTIMEOUT[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOC_GETTIMELEFT[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOF_SETTIMEOUT[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOF_KEEPALIVEPING[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOF_CARDRESET[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOS_DISABLECARD[ \\t]+[^\\n]+$)': 'uapi',
 '(^#define[ \\t]+WDIOS_ENABLECARD[ \\t]+[^\\n]+$)': 'uapi',
 '(struct watchdog_info \\{[^}]*\\};)': 'uapi'}
SOURCE_FRAGMENTS = {'driver': ('static void __iomem *mt762x_wdt_base;',
            '.start = mt762x_wdt_start,',
            '.stop = mt762x_wdt_stop,'),
 'dts': ('\t\twdt: wdt@100 {\n'
         '\t\t\tcompatible = "mtk,mt7621-wdt";\n'
         '\t\t\treg = <0x100 0x100>;\n'
         '\t\t};',)}
PREFIX = RAW_PREFIX + '\nSOURCE_DEFINITIONS\n' + MMIO

SUFFIX = r'''
struct thread_arg { struct file *file; int options; long result; };
static void *disable_or_enable(void *opaque)
{
 struct thread_arg *arg = opaque;
 arg->result = watchdog_ioctl(arg->file, WDIOC_SETOPTIONS, (unsigned long)&arg->options);
 return NULL;
}
static void concurrent(struct file *file, int enable, long *first, long *second)
{
 pthread_t one, two;
 struct thread_arg a = {file, WDIOS_DISABLECARD, 999};
 struct thread_arg b = {file, enable ? WDIOS_ENABLECARD : WDIOS_DISABLECARD, 999};
 schedule_enabled = 1;
 checked(pthread_create(&one, NULL, disable_or_enable, &a));
 checked(pthread_mutex_lock(&gate));
 while (!paused) checked(pthread_cond_wait(&changed, &gate));
 checked(pthread_mutex_unlock(&gate));
 checked(pthread_create(&two, NULL, disable_or_enable, &b));
 checked(pthread_mutex_lock(&gate));
 while (!contended) checked(pthread_cond_wait(&changed, &gate));
 release_write = 1;
 checked(pthread_cond_broadcast(&changed));
 checked(pthread_mutex_unlock(&gate));
 checked(pthread_join(one, NULL));
 checked(pthread_join(two, NULL));
 *first = a.result;
 *second = b.result;
}
int main(int argc, char **argv)
{
 const char *name;
 struct watchdog_info info;
 struct watchdog_ops ops;
 struct watchdog_device device;
 struct watchdog_device *observed = &device;
 struct platform_device platform;
 struct file file;
 int options = WDIOS_DISABLECARD;
 long first = 999, second = 999;
 if (argc != 2) return 64;
 name = argv[1];
 CASE_ADMISSION
 memset(&info, 0, sizeof(info));
 memset(&platform, 0, sizeof(platform));
 memset(&ops, 0, sizeof(ops));
 memset(&device, 0, sizeof(device));
 ops.start = mt762x_wdt_start;
 ops.stop = mt762x_wdt_stop;
 ops.ping = mt762x_wdt_ping;
 ops.set_timeout = mt762x_wdt_set_timeout;
 device.info = &info;
 device.ops = &ops;
 device.timeout = 30;
 device.min_timeout = 1;
 device.max_timeout = 65;
 device.status = BIT(WDOG_ACTIVE);
 checked(pthread_mutex_init(&device.lock.native, NULL));
 file.private_data = &device;
 control = 0x12340000 | TMR1CTL_ENABLE;
 if (strstr(name, "stuck")) fault = 1;
 if (strstr(name, "dropped")) fault = 2;
 if (strstr(name, "retry")) fault_limit = 1;
 if (!strcmp(name,"driver-inactive") || !strcmp(name,"disable-inactive") ||
     !strcmp(name,"enable-inactive") || !strcmp(name,"enable-unregistered")) {
  device.status = 0;
  control &= ~TMR1CTL_ENABLE;
 }
 if (!strcmp(name,"disable-inactive-hardware-enabled")) device.status = 0;
 if (strstr(name,"nowayout")) device.status |= BIT(WDOG_NO_WAY_OUT);
 if (strstr(name,"unregistered")) device.status |= BIT(WDOG_UNREGISTERED);
 if (strstr(name,"preserve-flags")) device.status |= BIT(WDOG_DEV_OPEN) | BIT(WDOG_ALLOW_RELEASE);
 if (!strncmp(name,"enable-",7)) options = WDIOS_ENABLECARD;
 if (!strncmp(name,"disable-enable",14)) options |= WDIOS_ENABLECARD;
 if (!strcmp(name,"noop-options")) options = 0;
 if (!strncmp(name,"probe-",6)) {
  observed = &mt762x_wdt_dev;
  if (!strcmp(name,"probe-no-resource")) no_resource = 1;
  if (!strcmp(name,"probe-map-error")) map_error = -ENOMEM;
  if (!strcmp(name,"probe-reset-error")) { declared_reset = 1; reset_error = -EIO; }
  if (!strcmp(name,"probe-reset-defer")) { declared_reset = 1; reset_error = -517; }
  if (!strcmp(name,"probe-declared-reset")) declared_reset = 1;
  if (!strcmp(name,"probe-declared-missing-provider")) { declared_reset = 1; reset_error = -ENOENT; }
  if (!strcmp(name,"probe-register-error")) register_error = -EBUSY;
  if (!strcmp(name,"probe-nowayout")) nowayout = 1;
  first = mt762x_wdt_probe(&platform);
 }
 else if (!strncmp(name,"driver-",7)) first = mt762x_wdt_stop(&device);
 else if (!strncmp(name,"concurrent-",11)) concurrent(&file, strstr(name,"enable") != NULL, &first, &second);
 else {
  first = watchdog_ioctl(&file, WDIOC_SETOPTIONS,
                        !strcmp(name,"disable-bad-user") ? 0 : (unsigned long)&options);
  if (strstr(name,"retry")) second = watchdog_ioctl(&file, WDIOC_SETOPTIONS, (unsigned long)&options);
 }
 printf("{\"ret\":%ld,\"second\":%ld,\"enabled\":%d,\"active\":%d,\"status\":%lu,\"reads\":%u,\"control_writes\":%u,\"pings\":%u,\"loads\":%u,\"contended\":%d,\"unlocked_mmio\":%u,\"control_other\":%u,\"map_calls\":%u,\"reset_calls\":%u,\"register_calls\":%u,\"probe_timeout\":%u,\"probe_max\":%u,\"probe_bootstatus\":%u}\n",
        first, second, !!(control & TMR1CTL_ENABLE), watchdog_active(observed),
        observed->status, reads, control_writes, pings, loads, contended,
        unlocked_mmio, control & ~TMR1CTL_ENABLE, map_calls, reset_calls,
        register_calls, mt762x_wdt_dev.timeout, mt762x_wdt_dev.max_timeout,
        mt762x_wdt_dev.bootstatus);
 checked(pthread_mutex_destroy(&device.lock.native));
 return 0;
}
'''


def function(text, name):
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda match: ' ' * len(match.group()), text, flags=re.S)
    pattern = (r'(?:static\s+)?(?:inline\s+)?(?:int|long|bool|void|u32)\s+'
               + re.escape(name) + r'\s*\([^;{}]*\)\s*\{')
    matches = list(re.finditer(pattern, masked))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous watchdog body: ' + name)
    start = matches[0].start()
    opening = masked.index('{', start)
    depth = 0
    for match in re.finditer('[{}]', masked[opening:]):
        depth += 1 if match.group() == '{' else -1
        if not depth:
            return text[start:opening + match.end()]
    raise ValueError('Unterminated watchdog body: ' + name)


def production_fragments(texts):
    fragments = []
    for pattern, key in SOURCE_DECLARATIONS.items():
        matches = re.findall(pattern, texts[key], re.M)
        if len(matches) != 1:
            raise ValueError('Missing/ambiguous watchdog declaration: ' + pattern)
        fragments.append(matches[0])
    return '\n'.join(fragments)


def validate_inputs(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact watchdog sources required')
    for name, key in FUNCTION_SOURCES.items():
        function(texts[key], name)
    production_fragments(texts)
    for key, fragments in SOURCE_FRAGMENTS.items():
        for fragment in fragments:
            if texts[key].count(fragment) != 1:
                raise ValueError('Watchdog source binding differs: ' + fragment)


def function_manifest(texts):
    validate_inputs(texts)
    return {name: dict(source=key, execution='whole-function', full_body_sha256=hashlib.sha256(
        function(texts[key], name).encode()).hexdigest()) for name, key in FUNCTION_SOURCES.items()}


def source_only_manifest(texts):
    validate_inputs(texts)
    return {}


def generate_source(texts, baseline=False):
    validate_inputs(texts)
    if type(baseline) is not bool:
        raise ValueError('Exact boolean baseline profile required')
    for name, body in BASELINE_FUNCTIONS.items():
        if hashlib.sha256(body.encode()).hexdigest() != BASELINE_FUNCTIONS_SHA256[name]:
            raise ValueError('Changed historical watchdog fixture: ' + name)
    if BASELINE_FUNCTIONS['mt762x_wdt_stop'] != BASELINE_BODY or BASELINE_FUNCTIONS['mt762x_wdt_probe'] != BASELINE_PROBE_BODY:
        raise ValueError('Historical watchdog fixture aliases differ')
    bodies = [BASELINE_FUNCTIONS[name] if baseline and name in BASELINE_FUNCTIONS
              else function(texts[FUNCTION_SOURCES[name]], name) for name in BODY_ORDER]
    admission = 'if (' + ' && '.join('strcmp(name,"' + name + '")' for name in CASE_NAMES) + ') return 2;'
    return PREFIX.replace('SOURCE_DEFINITIONS', production_fragments(texts)) + '\n' + '\n'.join(bodies) + '\n' + SUFFIX.replace('CASE_ADMISSION', admission)
