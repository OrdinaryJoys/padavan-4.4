"""Current PCI functions with inert ownership/API recorders.

This proves callback order and PCI enable accounting, not PCI/DMA operation,
driver-close quiescence, hardware reset, or safe release of busy DMA ownership.
"""
import hashlib
import re

SOURCE_PATHS = {
    'pci': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/pci_main_dev.c',
    'config': 'trunk/configs/boards/K2P/kernel-4.4.x.config',
    'flags': 'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/os/linux/Makefile.mt_wifi_ap',
}
FUNCTION_SOURCES = {'rt_pci_remove': 'pci', 'rt_pci_shutdown': 'pci'}
BODY_ORDER = ('rt_pci_remove', 'rt_pci_shutdown')
CASE_NAMES = ('remove-adapter', 'remove-no-adapter', 'remove-repeat',
              'remove-disabled', 'remove-no-netdev', 'remove-no-netdev-repeat',
              'shutdown-busy', 'shutdown-busy-repeat', 'shutdown-no-netdev')
OBSERVATION_FIELDS = ('enabled_references', 'bus_master', 'netdev_live',
                      'adapter_live', 'dma_owned', 'dma_busy', 'invalid_operations',
                      'event_count', 'events...')
EXPECTED_ROWS = {
    'remove-adapter': [0, 0, 0, 0, 0, 0, 0, 8, 2, 3, 1, 4, 5, 6, 7, 8],
    'remove-no-adapter': [0, 0, 0, 0, 0, 0, 0, 7, 9, 1, 4, 5, 6, 7, 8],
    'remove-repeat': [0, 0, 0, 0, 0, 0, 0, 9, 2, 3, 1, 4, 5, 6, 7, 8, 1],
    'remove-disabled': [0, 0, 0, 0, 0, 0, 0, 7, 2, 3, 1, 4, 5, 6, 7],
    'remove-no-netdev': [0, 0, 0, 0, 0, 0, 0, 2, 1, 8],
    'remove-no-netdev-repeat': [0, 0, 0, 0, 0, 0, 0, 3, 1, 8, 1],
    'shutdown-busy': [1, 0, 1, 1, 1, 1, 0, 1, 1],
    'shutdown-busy-repeat': [1, 0, 1, 1, 1, 1, 0, 2, 1, 1],
    'shutdown-no-netdev': [1, 0, 0, 0, 0, 1, 0, 1, 1],
}

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define VOID void
#define DEVEXIT
typedef unsigned long ULONG;
typedef struct fixture_adapter { int unused,dma_removing; } ADAPTER,RTMP_ADAPTER;
struct net_device { unsigned long base_addr; ADAPTER *adapter; };
typedef struct net_device *PNET_DEV;
struct pci_dev { struct net_device *data; int enabled, master; };
static struct pci_dev *active;
static int events[64], count, netdev_live, adapter_live, dma_owned, dma_busy, invalid;
static void event(int id) { assert(count < 64); events[count++] = id; }
#define MTWF_LOG(...) do { } while (0)
#define rtnl_lock() ((void)0)
#define rtnl_unlock() ((void)0)
static int RtmpDmaBeginRemove(RTMP_ADAPTER *ad){(void)ad;return !dma_busy;}
#define GET_PAD_FROM_NET_DEV(p,n) do { (p) = (n)->adapter; } while (0)
static struct net_device *pci_get_drvdata(struct pci_dev *p) { return p->data; }
static void pci_set_drvdata(struct pci_dev *p, void *data) {
    event(6);
    if (data)
        invalid++;
    p->data = data;
}
static void pci_clear_master(struct pci_dev *p) { event(1); p->master = 0; }
static int pci_is_enabled(struct pci_dev *p) { return p->enabled > 0; }
static void pci_disable_device(struct pci_dev *p) {
    event(8);
    if (p->enabled <= 0)
        invalid++;
    else
        p->enabled--;
    if (!p->enabled)
        p->master = 0;
}
static int RtmpPhyNetDevExit(void *adapter, struct net_device *dev) {
    event(2);
    if (!adapter || !dev || !netdev_live)
        invalid++;
    return 1;
}
static int RtmpRaDevCtrlExit(void *adapter) {
    event(3);
    if (!adapter || !adapter_live || dma_busy)
        invalid++;
    adapter_live = dma_owned = 0;
    return 1;
}
static void RtmpOSNetDevDetach(struct net_device *dev) {
    event(9);
    if (!dev || !netdev_live)
        invalid++;
}
static void iounmap(void *address) {
    event(4);
    if (address != (void *)(uintptr_t)0x1000 || active->master)
        invalid++;
}
static void pci_release_regions(struct pci_dev *p) {
    event(5);
    if (p != active || p->master)
        invalid++;
}
static void RtmpOSNetDevFree(struct net_device *dev) {
    event(7);
    if (!dev || !netdev_live || active->data)
        invalid++;
    netdev_live = 0;
}
''' '\n#define TRUE 1\nstatic int restart_shutdown_attempts,restart_quarantine_reports;\nstatic void RtmpDmaLifecycleLock(RTMP_ADAPTER *ad) { assert(ad); }\nstatic void RtmpDmaLifecycleUnlock(RTMP_ADAPTER *ad) { assert(ad); }\nstatic void netif_device_detach(struct net_device *dev) { assert(dev); }\nstatic void netif_tx_stop_all_queues(struct net_device *dev) { assert(dev); }\n/* Real stop/idle and sticky reporting execute in restart_veto_harness. */\nstatic int RtmpDmaTeardownCheck(RTMP_ADAPTER *ad) { assert(ad);restart_shutdown_attempts++;return !dma_busy; }\nstatic void RtmpDmaQuarantine(RTMP_ADAPTER *ad) { assert(ad);restart_quarantine_reports++; }\n'


SUFFIX = r'''
int main(int argc, char **argv) {
    const char *name;
    struct pci_dev p;
    struct net_device n;
    ADAPTER a;
    int i;
    assert(argc == 2); name = argv[1]; CASE_ADMISSION
    memset(&p, 0, sizeof(p)); memset(&n, 0, sizeof(n)); memset(&a, 0, sizeof(a));
    active = &p; p.data = &n; p.enabled = p.master = 1;
    n.base_addr = 0x1000; n.adapter = &a;
    netdev_live = adapter_live = dma_owned = 1;
    if (!strcmp(name, "remove-no-adapter")) {
        n.adapter = NULL; adapter_live = dma_owned = 0;
    }
    if (!strcmp(name, "remove-disabled")) p.enabled = p.master = 0;
    if (strstr(name, "no-netdev")) {
        p.data = NULL; netdev_live = adapter_live = dma_owned = 0;
    }
    if (!strncmp(name, "shutdown-", 9)) {
        dma_busy = 1;
        rt_pci_shutdown(&p);
        if (!strcmp(name, "shutdown-busy-repeat")) rt_pci_shutdown(&p);
    } else {
        rt_pci_remove(&p);
        if (strstr(name, "repeat")) rt_pci_remove(&p);
    }
    printf("[%d,%d,%d,%d,%d,%d,%d,%d", p.enabled, p.master, netdev_live,
           adapter_live, dma_owned, dma_busy, invalid, count);
    for (i = 0; i < count; i++) printf(",%d", events[i]);
    puts("]");
    return 0;
}
'''


def function(text, name):
    token = r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked = re.sub(token, lambda m: ' ' * len(m.group()), text)
    pattern = r'^static\s+VOID\s+(?:DEVEXIT\s+)?' + re.escape(name) + r'\s*\([^;{}]*\)\s*\{'
    found = list(re.finditer(pattern, masked, re.M))
    if len(found) != 1:
        raise ValueError('Missing/ambiguous PCI lifecycle function: ' + name)
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
    raise ValueError('Unterminated PCI lifecycle function: ' + name)


def actual_functions(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact PCI lifecycle source mapping required')
    config = texts['config']
    if not all(x in config for x in ('CONFIG_CHIP_MT7615E=y', 'CONFIG_MT7615_AP=m',
                                    '# CONFIG_PCI_MSI is not set', '# CONFIG_PM is not set')):
        raise ValueError('Configured K2P PCI/non-MSI/non-PM profile differs')
    if 'EXTRA_CFLAGS += -DMT7615 ' not in texts['flags']:
        raise ValueError('Actual MT7615 compiler selection absent')
    return {name: {'source': key, 'body': function(texts[key], name)}
            for name, key in FUNCTION_SOURCES.items()}


def generate_source(texts):
    bodies = actual_functions(texts)
    admission = 'if(!(' + '||'.join('!strcmp(name,"' + n + '")' for n in CASE_NAMES) + '))return 91;'
    return PREFIX + '\n'.join(bodies[n]['body'] for n in BODY_ORDER) + SUFFIX.replace('CASE_ADMISSION', admission)


def function_manifest(texts):
    return {name: {'source': row['source'], 'execution': 'whole-function',
                   'full_body_sha256': hashlib.sha256(row['body'].encode()).hexdigest()}
            for name, row in actual_functions(texts).items()}
