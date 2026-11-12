"""Whole restart gate/board bodies with deterministic local/remote report seams.

MMIO, IRQ masking, the 50 ms delay and terminal escape are explicit models.
A joined pthread injects a real atomic report at the selected observation point;
this does not simulate all Linux scheduling, other-CPU stopping or physical DMA.
"""
from pathlib import Path
import re
from raeth_runtime_harness import function

SOURCE_PATHS = {
    'reboot': 'trunk/linux-4.4.x/kernel/reboot.c',
    'arch': 'trunk/linux-4.4.x/arch/mips/ralink/reset.c',
    'header': 'trunk/linux-4.4.x/include/linux/reboot.h',
}
FUNCTION_SOURCES = {
    'reboot_dma_failure_report': 'reboot',
    'reboot_dma_failures': 'reboot',
    'reboot_dma_failure_check': 'reboot',
    'ralink_restart': 'arch',
}
PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <pthread.h>
typedef struct { unsigned int value; } atomic_t;
#define ATOMIC_INIT(n) {n}
#define BIT(n) (1U << (n))
#define IS_ENABLED(n) WITH_PCI
#define MAX_SCHEDULE_TIMEOUT 100
#define pr_emerg(...) ((void)0)
static jmp_buf escape;
static const char *scenario;
static int irq_off, injected, gate_reads, pci_reset, system_reset;
static int pci_irq_off, system_irq_off, terminal, delay_calls;
void reboot_dma_failure_report(unsigned int);
static void *reporter(void *unused) {
    (void)unused; reboot_dma_failure_report(2); return NULL;
}
static void inject(const char *point) {
    pthread_t t;
    if (injected || strcmp(scenario, point)) return;
    injected = 1;
    assert(!pthread_create(&t, NULL, reporter, NULL));
    assert(!pthread_join(t, NULL));
}
static void atomic_or(unsigned int n, atomic_t *p) {
    __atomic_fetch_or(&p->value, n, __ATOMIC_SEQ_CST);
}
static unsigned int atomic_read(atomic_t *p) {
    unsigned int value = __atomic_load_n(&p->value, __ATOMIC_SEQ_CST);
    gate_reads++;
    if (gate_reads == 1) inject("after-first-read");
    if (gate_reads == 2) inject("after-final-read");
    return value;
}
static void local_irq_disable(void) {
    if (!irq_off) inject("irq-mask-edge");
    irq_off = 1;
}
static void cpu_relax(void) { terminal = 1; longjmp(escape, 1); }
static void schedule_timeout_uninterruptible(long n) { (void)n; assert(0); }
static void rt_sysc_m32(unsigned int clear, unsigned int set, unsigned int reg) {
    assert(!clear && set == BIT(26) && reg == 0x34);
    pci_reset++; pci_irq_off = irq_off; inject("pci-write");
}
static void mdelay(unsigned int n) {
    assert(n == 50); delay_calls++; inject("pci-delay");
}
static void rt_sysc_w32(unsigned int value, unsigned int reg) {
    assert(value == BIT(0) && reg == 0x34);
    system_reset++; system_irq_off = irq_off;
}
#define unreachable() do { terminal = 2; longjmp(escape, 1); } while (0)
'''
SUFFIX = r'''
int main(int argc, char **argv) {
    assert(argc == 2); scenario = argv[1];
    if (!strcmp(scenario, "preexisting")) reboot_dma_failure_report(1);
    if (!setjmp(escape)) ralink_restart(NULL);
    printf("{\"reasons\":%u,\"terminal\":%d,\"irq_off\":%d,\"injected\":%d,"
           "\"gate_reads\":%d,\"pci_reset\":%d,\"system_reset\":%d,"
           "\"pci_irq_off\":%d,\"system_irq_off\":%d,\"delay_calls\":%d}\n",
           __atomic_load_n(&reboot_dma_failure_reasons.value, __ATOMIC_SEQ_CST),
           terminal, irq_off, injected, gate_reads, pci_reset, system_reset,
           pci_irq_off, system_irq_off, delay_calls);
    return 0;
}
'''

def current_texts():
    root = Path(__file__).resolve().parents[1]
    return {k: (root/p).read_text() for k,p in SOURCE_PATHS.items()}

def generate(texts):
    definitions = []
    for key, pattern in (
        ('header', r'enum reboot_dma_failure\s*\{[^}]+\};'),
        ('reboot', r'^static atomic_t reboot_dma_failure_reasons = ATOMIC_INIT\(0\);$'),
        ('arch', r'^#define SYSC_REG_RESET_CTRL\s+[^\n]+'),
        ('arch', r'^#define RSTCTL_RESET_PCI\s+[^\n]+'),
        ('arch', r'^#define RSTCTL_RESET_SYSTEM\s+[^\n]+'),
    ):
        matches = re.findall(pattern, texts[key], re.M)
        if len(matches) != 1: raise ValueError('Missing/ambiguous definition: '+pattern)
        definitions.append(matches[0])
    return PREFIX+'\n'+'\n'.join(definitions)+'\n'+'\n'.join(
        function(texts[k], n) for n,k in FUNCTION_SOURCES.items())+SUFFIX
