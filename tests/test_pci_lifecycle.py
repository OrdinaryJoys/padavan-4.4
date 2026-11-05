"""Current data-only PCI lifecycle ownership and enable-accounting controls."""
import errno
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import pci_lifecycle_harness as h

ROOT = Path(__file__).resolve().parents[1]


class PciLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-current-pci-lifecycle-')
        cls.directory = Path(cls.temp.name)
        cls.texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
        cls.generated = h.generate_source(cls.texts)
        source = cls.directory / 'pci.c'
        source.write_text(cls.generated)
        cls.binaries = []
        gnu = shutil.which('gcc-16')
        if gnu is None and Path('/opt/homebrew/bin/gcc-16').is_file():
            gnu = '/opt/homebrew/bin/gcc-16'
        if gnu is None:
            gnu = shutil.which('gcc')
        if gnu is None:
            raise AssertionError('GNU GCC required for warning parity')
        version = subprocess.run([gnu, '--version'], check=True, capture_output=True,
                                 text=True, timeout=10).stdout
        if 'Free Software Foundation' not in version or 'clang' in version.lower():
            raise AssertionError('The GCC control requires GNU GCC, not a compiler alias')
        cls.compilers = (('clang', shutil.which('clang')), ('gcc', gnu))
        for compiler, executable in cls.compilers:
            if executable is None:
                raise AssertionError('Required strict C compiler absent: ' + compiler)
            binary = cls.directory / compiler
            flags = ['-std=gnu99', '-Os', '-Wall', '-Wextra', '-Werror']
            if compiler == 'clang':
                flags += ['-fsanitize=address,undefined']
            result = subprocess.run([executable, *flags, str(source), '-o', str(binary)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.binaries.append(binary)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def cases(self, names):
        for binary in self.binaries:
            for name in names:
                with self.subTest(compiler=binary.name, case=name):
                    result = subprocess.run([str(binary), name], check=True, capture_output=True,
                                            text=True, timeout=5)
                    row = json.loads(result.stdout)
                    self.assertEqual(row, h.EXPECTED_ROWS[name])
                    self.assertTrue(all(type(value) is int for value in row))

    def test_remove_balances_enable_and_clears_driver_data_before_netdev_free(self):
        self.cases(('remove-adapter', 'remove-no-adapter', 'remove-disabled'))

    def test_repeat_remove_and_missing_netdev_do_not_release_twice(self):
        self.cases(('remove-repeat', 'remove-no-netdev', 'remove-no-netdev-repeat'))

    def test_shutdown_suppresses_master_without_releasing_busy_dma_ownership(self):
        self.cases(('shutdown-busy', 'shutdown-busy-repeat', 'shutdown-no-netdev'))

    def test_registered_shutdown_and_whole_current_function_contract(self):
        self.assertEqual(len(h.CASE_NAMES), 9)
        self.assertEqual(set(h.CASE_NAMES), set(h.EXPECTED_ROWS))
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(self.generated.count(h.function(self.texts[key], name)), 1)
        self.assertEqual(len(h.function_manifest(self.texts)), 2)
        self.assertRegex(self.texts['pci'], r'shutdown\s*:\s*rt_pci_shutdown\s*,')
        body = h.function(self.texts['pci'], 'rt_pci_shutdown')
        self.assertEqual(body.count('pci_clear_master(pci_dev);'), 1)
        self.assertNotRegex(body, r'\b(?:iounmap|pci_release_regions|pci_disable_device|RTMPFree\w*|Asic\w*)\s*\(')
        with self.assertRaises(ValueError):
            h.generate_source({})
        changed = dict(self.texts, config=self.texts['config'].replace('CONFIG_CHIP_MT7615E=y', ''))
        with self.assertRaises(ValueError):
            h.generate_source(changed)

    def test_current_probe_failure_labels_release_each_acquired_resource_once(self):
        # Execute only this current cleanup fragment with ordinary memory and
        # inert recorders. This is not a complete probe, PCI or DMA proof.
        source = self.texts['pci']
        begin = 'static int DEVINIT rt_pci_probe('
        self.assertEqual(source.count(begin), 1)
        start = source.index(begin)
        end = source.index('\n}', start) + 2
        probe = source[start:end]
        marker = '\nerr_out_free_netdev:\n'
        self.assertEqual(probe.count(marker), 1)
        tail = probe[probe.index(marker) + 1:]
        # Refuse a duplicate source call before compiling any counterexample.
        self.assertEqual(tail.count('pci_release_regions(pdev);'), 1)
        for fragment in ('BOOLEAN radev_initialized = FALSE;', 'radev_initialized = TRUE;',
                         'pci_set_master(pdev);'):
            self.assertEqual(probe.count(fragment), 1)
        initialized = 'if (pci_config.pci_init_succeed != TRUE)\n\t\tgoto err_out_free_radev;'
        self.assertEqual(probe.count(initialized), 1)
        self.assertLess(probe.index(initialized), probe.index('radev_initialized = TRUE;'))
        self.assertLess(probe.index('radev_initialized = TRUE;'), probe.index('RtmpPhyNetDevInit('))
        self.assertLess(probe.index('pci_set_master(pdev);'), probe.index('rv = RTMPAllocAdapterBlock('))
        ownership = ('if (radev_initialized)\n\t\tRtmpRaDevCtrlExit(pAd);\n'
                     '\telse\n\t\tRTMPFreeAdapter(pAd);')
        self.assertEqual(tail.count(ownership), 1)
        for fragment in ('RtmpRaDevCtrlExit(pAd);', 'RTMPFreeAdapter(pAd);',
                         'pci_clear_master(pdev);', 'iounmap((void *)(csr_addr));',
                         'pci_disable_device(pdev);'):
            self.assertEqual(tail.count(fragment), 1)
        self.assertLess(tail.index(ownership), tail.index('pci_clear_master(pdev);'))
        self.assertLess(tail.index('pci_clear_master(pdev);'), tail.index('iounmap((void *)(csr_addr));'))
        self.assertLess(tail.index('iounmap((void *)(csr_addr));'), tail.index('pci_release_regions(pdev);'))
        self.assertLess(tail.index('pci_release_regions(pdev);'), tail.index('pci_disable_device(pdev);'))
        self.assertLess(tail.index('pci_set_drvdata(pdev, NULL);'), tail.index('RtmpOSNetDevFree(net_dev);'))
        prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define MTWF_LOG(...) do { } while (0)
struct pci_dev { int unused; };
struct net_device { int unused; };
static struct pci_dev device;
static struct net_device netdev;
static int adapter, mapping;
static int enabled, regions, mapped, adapter_live, netdev_live;
static int devctrl_live, master, drvdata_live, devctrls, clears, drvclears;
static int releases, unmaps, adapters, netdevs, disables, events[8], count;
static void event(int n) { assert(count < 8); events[count++] = n; }
static void RtmpOSNetDevFree(struct net_device *p) {
    assert(p == &netdev && netdev_live && !drvdata_live && !netdevs);
    netdev_live = 0; netdevs++; event(1);
}
static void RTMPFreeAdapter(void *p) {
    assert(p == &adapter && adapter_live && !devctrl_live && !netdev_live && !adapters);
    assert(mapped && master); adapter_live = 0; adapters++; event(2);
}
static void RtmpRaDevCtrlExit(void *p) {
    assert(p == &adapter && adapter_live && devctrl_live && !devctrls);
    devctrl_live = 0; devctrls++; event(6); RTMPFreeAdapter(p);
}
static void pci_clear_master(struct pci_dev *p) {
    assert(p == &device && enabled && mapped && master && !clears);
    assert(!adapter_live && !devctrl_live && !netdev_live);
    master = 0; clears++; event(7);
}
static void iounmap(void *p) {
    assert(p == &mapping && mapped && !master && !adapter_live && !devctrl_live);
    mapped = 0; unmaps++; event(3);
}
static void pci_release_regions(struct pci_dev *p) {
    assert(p == &device && regions && !mapped && !master);
    regions = 0; releases++; event(4);
}
static void pci_disable_device(struct pci_dev *p) {
    assert(p == &device && enabled && !regions && !mapped && !master);
    enabled = 0; disables++; event(5);
}
static void pci_set_drvdata(struct pci_dev *p,void *data) {
    assert(p == &device && !data && drvdata_live && !drvclears);
    drvdata_live = 0; drvclears++;
}
static int cleanup(int which, int initialized) {
    struct net_device *net_dev = &netdev;
    struct pci_dev *pdev = &device;
    void *pAd = &adapter;
    int radev_initialized = initialized;
    unsigned long csr_addr = (unsigned long)(uintptr_t)&mapping;
    switch (which) {
    case 0: goto err_out;
    case 1: goto err_out_free_res;
    case 2: goto err_out_iounmap;
    case 3: goto err_out_free_radev;
    case 4: goto err_out_free_netdev;
    default: abort();
    }
'''
        suffix = r'''
int main(int argc, char **argv) {
    int which, initialized, result, i;
    assert(argc == 3); which = atoi(argv[1]); initialized = atoi(argv[2]);
    assert(which >= 0 && which <= 4 && (initialized == 0 || initialized == 1));
    assert(!initialized || which >= 3); assert(which != 4 || initialized);
    enabled = 1; regions = which >= 1; mapped = which >= 2;
    adapter_live = which >= 3; netdev_live = which >= 4;
    devctrl_live = initialized; master = mapped; drvdata_live = netdev_live;
    result = cleanup(which, initialized);
    printf("[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d", result, netdevs,
           adapters, unmaps, releases, disables, regions, mapped,
           adapter_live, netdev_live, enabled, devctrls, clears,
           devctrl_live, master, drvdata_live, drvclears, count);
    for (i = 0; i < count; i++) printf(",%d", events[i]);
    puts("]"); return 0;
}
'''
        code = prefix + tail + '\n' + suffix
        cleanup_source = self.directory / 'probe-cleanup.c'
        cleanup_source.write_text(code)
        for compiler, executable in self.compilers:
            binary = self.directory / ('probe-cleanup-' + compiler)
            flags = ['-std=gnu99', '-Os', '-Wall', '-Wextra', '-Werror']
            if compiler == 'clang':
                flags += ['-fsanitize=address,undefined']
            result = subprocess.run([executable, *flags, str(cleanup_source), '-o', str(binary)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual((result.returncode, result.stderr), (0, ''), result.stderr)
            scenarios = [(which, int(which >= 4)) for which in range(5)] + [(3, 1)]
            for which, initialized in scenarios:
                with self.subTest(compiler=compiler, failure_label=which, devctrl_owned=initialized):
                    result = subprocess.run([str(binary), str(which), str(initialized)], capture_output=True,
                                            text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn('AddressSanitizer', result.stderr)
                    self.assertNotIn('runtime error:', result.stderr)
                    events = list(range(5 - which, 6))
                    if which >= 2:
                        events.insert(events.index(3), 7)
                    if initialized:
                        events.insert(events.index(2), 6)
                    expected = [-errno.ENODEV, int(which >= 4), int(which >= 3),
                                int(which >= 2), int(which >= 1), 1, 0, 0, 0, 0, 0,
                                initialized, int(which >= 2), 0, 0, 0, int(which >= 4),
                                len(events)] + events
                    self.assertEqual(json.loads(result.stdout), expected)
