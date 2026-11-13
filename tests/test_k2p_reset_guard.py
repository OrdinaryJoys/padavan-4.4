"""Run production K2P guard and selected driver bodies with inert hardware."""

import os
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import nor_address_harness as nor
import probe_oom_harness as pci
import raeth_runtime_harness as raeth
from mt7621_wdt_harness import function

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "trunk/linux-4.4.x"


def source(path):
    return (KERNEL / path).read_text()


def without_includes(text):
    return re.sub(r"^#include .*\n", "", text, flags=re.M)


HEADER = without_includes(source("include/linux/reboot_guard.h"))
CORE = without_includes(source("kernel/reboot_guard.c"))
SHIM = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#define CONFIG_K2P_RESET_GUARD 1
#undef ESHUTDOWN
#define ESHUTDOWN 108
#define U32_MAX UINT32_MAX
#define __noreturn __attribute__((noreturn))
#define MAX_SCHEDULE_TIMEOUT 100
#define EXPORT_SYMBOL(x)
#define EXPORT_SYMBOL_GPL(x)
#define DEFINE_RAW_SPINLOCK(x) pthread_mutex_t x = PTHREAD_MUTEX_INITIALIZER
#define raw_spin_lock_irqsave(lock, flags) do { (flags) = 0; assert(!pthread_mutex_lock(lock)); } while (0)
#define raw_spin_unlock_irqrestore(lock, flags) do { (void)(flags); assert(!pthread_mutex_unlock(lock)); } while (0)
#define smp_load_acquire(p) __atomic_load_n(p, __ATOMIC_ACQUIRE)
#define smp_store_release(p, v) __atomic_store_n(p, v, __ATOMIC_RELEASE)
#define cmpxchg(p, old, new) __sync_val_compare_and_swap(p, old, new)
typedef uint32_t u32;
typedef uint16_t u16;
static _Thread_local unsigned int task;
static _Thread_local bool interrupt_context;
#define current ((struct task_struct *)&task)
#define in_interrupt() interrupt_context
'''
REASONS = re.search(r"enum reboot_dma_failure\s*\{[^}]+\};",
                    source("include/linux/reboot.h")).group()
RECORD = r'''
static unsigned int failure_reasons;
static void reboot_dma_failure_report(unsigned int reasons)
{
    __atomic_fetch_or(&failure_reasons, reasons, __ATOMIC_RELAXED);
}
static unsigned int reboot_dma_failures(void)
{
    return __atomic_load_n(&failure_reasons, __ATOMIC_RELAXED);
}
static void local_irq_disable(void) {}
static void schedule_timeout_uninterruptible(long n) { (void)n; abort(); }
static void cpu_relax(void) { abort(); }
#define pr_emerg(...) ((void)0)
'''

COORDINATOR_TEST = r'''
#include <setjmp.h>
static jmp_buf escape;
static int pci_writes, system_writes;
static _Thread_local bool irqs_off;
#define IS_ENABLED(option) 1
#define BIT(n) (1U << (n))
#define SYSC_REG_RESET_CTRL 0x34
#define RSTCTL_RESET_PCI BIT(26)
#define RSTCTL_RESET_SYSTEM BIT(0)
#define local_irq_disable() (irqs_off = true)
#define reboot_guard_park(sleep) longjmp(escape, 1)
#define unreachable() longjmp(escape, 2)
static void ralink_reset_update(u32 clear, u32 set)
{
    assert(irqs_off && !clear && set == BIT(26));
    pci_writes++;
}
static void rt_sysc_w32(u32 value, unsigned int reg)
{
    assert(irqs_off && value == BIT(0) && reg == 0x34);
    system_writes++;
}
static void mdelay(unsigned int n) { assert(n == 50); }
'''
CONCURRENT_CASES = r'''
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static struct reboot_guard adapter;
static int step;
static void reach(int n)
{
    assert(!pthread_mutex_lock(&mutex));
    step = n;
    assert(!pthread_cond_broadcast(&condition));
    assert(!pthread_mutex_unlock(&mutex));
}
static void await(int n)
{
    assert(!pthread_mutex_lock(&mutex));
    while (step < n)
        assert(!pthread_cond_wait(&condition, &mutex));
    assert(!pthread_mutex_unlock(&mutex));
}
static void *producer(void *unused)
{
    assert(!reboot_guard_begin(&adapter, REBOOT_GUARD_RUNTIME));
    reach(1);                  /* Failure detected, publication delayed. */
    await(2);
    reboot_guard_fail(&adapter, REBOOT_DMA_MT7615);
    reboot_guard_finish(&adapter);
    return NULL;
}
static void *second_coordinator(void *unused)
{
    assert(!reboot_guard_prepare(true));
    assert(!reboot_guard_seal());
    assert(!reboot_guard_consume());
    return NULL;
}
static int run_board(void)
{
    int ret = setjmp(escape);
    if (!ret)
        ralink_restart(NULL);
    return ret;
}
int main(int argc, char **argv)
{
    struct reboot_guard flash = {0}, io = {0}, late = {0}, stale;
    pthread_t worker;
    const char *name = argv[1];
    assert(argc == 2);
    if (!strcmp(name, "delayed-failure")) {
        assert(!pthread_create(&worker, NULL, producer, NULL));
        await(1);
        assert(reboot_guard_prepare(true));
        assert(!reboot_guard_seal());
        assert(run_board() == 1 && !pci_writes && !system_writes);
        reach(2);
        assert(!pthread_join(worker, NULL));
        assert(reboot_guard_drained());
        assert(reboot_dma_failures() == REBOOT_DMA_MT7615);
        assert(!reboot_guard_seal());
    } else if (!strcmp(name, "normal")) {
        assert(!reboot_guard_begin(&flash, REBOOT_GUARD_FLASH_DEVICE));
        assert(!reboot_guard_begin(&adapter, REBOOT_GUARD_RUNTIME));
        assert(reboot_guard_admit(&adapter));
        assert(reboot_guard_prepare(true));
        assert(!reboot_guard_admit(&adapter));
        assert(reboot_guard_begin(&late, REBOOT_GUARD_RUNTIME) == -ESHUTDOWN);
        assert(reboot_guard_flash_begin(&io, &adapter) == -ESHUTDOWN);
        assert(!reboot_guard_flash_begin(&io, &flash));
        reboot_guard_finish(&adapter);
        assert(!reboot_guard_seal());
        reboot_guard_finish(&io);
        reboot_guard_finish(&flash);
        assert(reboot_guard_flash_begin(&late, &flash) == -ESHUTDOWN);
        assert(reboot_guard_seal());
        assert(!pthread_create(&worker, NULL, second_coordinator, NULL));
        assert(!pthread_join(worker, NULL));
        interrupt_context = true;
        assert(run_board() == 1 && !pci_writes && !system_writes);
        interrupt_context = false;
        assert(run_board() == 2 && pci_writes == 1 && system_writes == 1);
        assert(run_board() == 1 && pci_writes == 1 && system_writes == 1);
    } else if (!strcmp(name, "stale-owner")) {
        assert(!reboot_guard_begin(&adapter, REBOOT_GUARD_RUNTIME));
        stale = adapter;
        reboot_guard_finish(&adapter);
        assert(!reboot_guard_begin(&adapter, REBOOT_GUARD_RUNTIME));
        assert(stale.slot == adapter.slot);
        reboot_guard_finish(&stale);
        assert(reboot_dma_failures() == REBOOT_DMA_UNKNOWN);
        assert(!reboot_guard_drained());
        reboot_guard_finish(&adapter);
        assert(reboot_guard_prepare(true) && !reboot_guard_seal());
    } else if (!strcmp(name, "capacity")) {
        struct reboot_guard tokens[REBOOT_GUARD_SLOTS] = {{0}};
        for (unsigned int i = 0; i < REBOOT_GUARD_SLOTS; i++)
            assert(!reboot_guard_begin(&tokens[i], REBOOT_GUARD_RUNTIME));
        assert(reboot_guard_begin(&late, REBOOT_GUARD_RUNTIME) == -ENOSPC);
        for (unsigned int i = 0; i < REBOOT_GUARD_SLOTS; i++)
            reboot_guard_finish(&tokens[i]);
        assert(reboot_guard_prepare(true) && reboot_guard_seal());
    } else if (!strcmp(name, "direct")) {
        assert(run_board() == 1 && !pci_writes && !system_writes);
    } else {
        abort();
    }
    return 0;
}
'''


def core_program(core=CORE):
    return (SHIM + HEADER + REASONS + RECORD + core + COORDINATOR_TEST
            + function(source("arch/mips/ralink/reset.c"), "ralink_restart")
            + CONCURRENT_CASES)


def nor_program():
    code = nor.generate(nor.current_texts())
    code = code.replace("int restore_started,restore_error;",
                        "int restore_started,restore_error; struct reboot_guard reset_device,reset_io;")
    code = code.replace(",writebufsize,numeraseregions;", ",writebufsize;int numeraseregions;")
    anchor = "static int spi_nor_lock_and_prep("
    position = code.index(anchor)
    code = (code[:position] + CORE
            + function(source("drivers/mtd/spi-nor/spi-nor.c"), "spi_nor_settle_error")
            + code[position:])
    code = code.replace("static int m25p_probe(", r'''
#define kzalloc(n, flags) devm_kzalloc(NULL, n, flags)
#define kfree(p) do { free(p); allocated_flash = NULL; } while (0)
static void get_device(struct device *dev) { assert(dev); }
static void put_device(struct device *dev) { assert(dev); }
static int m25p_probe(''')
    code = code.replace("mutex_init(&n->lock);",
                        "mutex_init(&n->lock); assert(!reboot_guard_begin(&n->reset_device, REBOOT_GUARD_FLASH_DEVICE));")
    code = code.replace("if(!thread_read)spi_nor_unlock_and_unprep(n,SPI_NOR_OPS_READ);",
                        "if(!thread_read){spi_nor_settle_error(n,0);spi_nor_unlock_and_unprep(n,SPI_NOR_OPS_READ);}")
    return SHIM + HEADER + "#define SR_WEL 2\n" + code


def pci_program():
    texts = {k: (ROOT / v).read_text() for k, v in pci.SOURCE_PATHS.items()}
    code = pci.generate_source(texts)
    code = code.replace("void *pDev;};", "void *pDev;struct reboot_guard reset_device,reset_dma;};")
    drain = function(texts["pci"], "RtmpPciDrain")
    boundary = r'''
#define PCI_COMMAND 4
#define PCI_COMMAND_MASTER 4
#define PCI_EXP_DEVSTA 10
#define PCI_EXP_DEVSTA_TRPND 32
static bool pci_is_pcie(struct pci_dev *d) { return d != NULL; }
static int pci_pcie_cap(struct pci_dev *d) { assert(d); return 64; }
static void msleep(int ms) { assert(ms == 100 || ms == 200 || ms == 400); }
static int pci_read_config_word(struct pci_dev *d, int reg, u16 *value)
{
    if (reg == PCI_COMMAND)
        *value = d->master ? PCI_COMMAND_MASTER : 0;
    else
        *value = 0;
    return 0;
}
'''
    anchor = code.rindex("static int DEVINIT rt_pci_probe(")
    code = code[:anchor] + boundary + drain + code[anchor:]
    code = code.replace("result=rt_pci_probe(&pci,NULL);",
                        "result=rt_pci_probe(&pci,NULL); assert(!pci.master); "
                        "if (result) assert(reboot_guard_drained());")
    code = code.replace("struct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);",
                        "struct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl); (void)cap;")
    return SHIM + HEADER + REASONS + RECORD + CORE + code


def raeth_program():
    texts = {k: (ROOT / v).read_text() for k, v in raeth.SOURCE_PATHS.items()}
    code = raeth.generate_source(texts)
    code = code.replace("irq_active,dma_quarantined,module_reserved;",
                        "irq_active,dma_quarantined,module_reserved; struct reboot_guard reset_device,reset_dma;")
    code = code.replace("static unsigned int restart_failure_reports;",
                        "#define restart_failure_reports failure_reasons")
    code = code.replace("static void reboot_dma_failure_report(unsigned int reasons) { restart_failure_reports |= reasons; }", "")
    code = code.replace("main_dev.priv=&adapter;",
                        "assert(!reboot_guard_begin(&adapter.reset_device, REBOOT_GUARD_RUNTIME));main_dev.priv=&adapter;")
    code = code.replace("unsigned int dma_on=",
                        "assert(!!adapter.reset_dma.generation == !!adapter.dma_quarantined);"
                        "unsigned int dma_on=")
    return SHIM + HEADER + REASONS + RECORD + CORE + code


def watchdog_program():
    driver = source("drivers/watchdog/mt7621_wdt.c")
    stubs = r'''
#define BIT(n) (1U << (n))
#define TIMER_REG_TMR1CTL 0x20
#define TIMER_REG_TMR1LOAD 0x24
#define TMR1CTL_ENABLE BIT(7)
#define WDOG_ACTIVE 0
struct watchdog_device { pthread_mutex_t lock; unsigned long status; unsigned int timeout; };
struct platform_device { int dev; };
static struct watchdog_device mt762x_wdt_dev = {PTHREAD_MUTEX_INITIALIZER, 1, 20};
static struct reboot_guard watchdog_guard;
static bool watchdog_retired;
static bool stuck;
static u32 control = TMR1CTL_ENABLE;
static unsigned int control_writes;
static void rt_wdt_w32(unsigned int reg, u32 value)
{
    if (reg == TIMER_REG_TMR1CTL) {
        control_writes++;
        control = value | (stuck ? TMR1CTL_ENABLE : 0);
    }
}
static u32 rt_wdt_r32(unsigned int reg) { assert(reg == TIMER_REG_TMR1CTL); return control; }
static int mt762x_wdt_ping(struct watchdog_device *w) { assert(w); return 0; }
static void mutex_lock(pthread_mutex_t *lock) { assert(!pthread_mutex_lock(lock)); }
static void mutex_unlock(pthread_mutex_t *lock) { assert(!pthread_mutex_unlock(lock)); }
static void clear_bit(unsigned int bit, unsigned long *word) { *word &= ~(1UL << bit); }
#define dev_err(...) ((void)0)
'''
    cases = r'''
int main(int argc, char **argv)
{
    struct platform_device p = {0};
    assert(argc == 2);
    stuck = !strcmp(argv[1], "stuck");
    assert(!reboot_guard_begin(&watchdog_guard, REBOOT_GUARD_RUNTIME));
    assert(reboot_guard_prepare(true));
    assert(mt762x_wdt_start(&mt762x_wdt_dev) == -ESHUTDOWN);
    assert(!control_writes);
    mt762x_wdt_shutdown(&p);
    mt762x_wdt_shutdown(&p);
    assert(control_writes == 1);
    assert(mt762x_wdt_start(&mt762x_wdt_dev) == -ESHUTDOWN);
    if (stuck) {
        assert(control & TMR1CTL_ENABLE);
        assert(mt762x_wdt_dev.status == 1);
        assert(reboot_dma_failures() == REBOOT_WATCHDOG_UNSAFE);
        assert(!reboot_guard_drained() && !reboot_guard_seal());
    } else {
        assert(!(control & TMR1CTL_ENABLE));
        assert(!mt762x_wdt_dev.status);
        assert(!reboot_dma_failures());
        assert(reboot_guard_drained() && reboot_guard_seal());
    }
    return 0;
}
'''
    bodies = ("mt762x_wdt_set_timeout", "mt762x_wdt_start", "mt762x_wdt_stop",
              "mt762x_wdt_shutdown")
    return (SHIM + HEADER + REASONS + RECORD + CORE + stubs
            + "\n".join(function(driver, name) for name in bodies) + cases)


class K2pResetGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="k2p-guard-")
        cls.path = Path(cls.tmp.name)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.compilers = [
            ("gcc", shutil.which("gcc-16"), [], []),
            ("clang", shutil.which("clang"),
             ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"], []),
        ]
        target = os.environ.get("K2P_RESET_GUARD_TARGET_CC")
        if target:
            runner = shutil.which("qemu-mipsel")
            assert runner, "qemu-mipsel required with target compiler"
            cls.compilers.append(("mips", target, ["-static"], [runner]))

    def compile(self, name, code):
        path = self.path / (name + ".c")
        path.write_text(code)
        for label, compiler, flags, runner in self.compilers:
            self.assertTrue(compiler)
            output = self.path / (name + "-" + label)
            r = subprocess.run([compiler, "-std=gnu11", "-O2", "-pthread",
                                "-Wall", "-Wextra", "-Werror",
                                "-Wno-unused-parameter", "-Wno-unused-function",
                                "-Wno-misleading-indentation", *flags,
                                str(path), "-o", str(output)],
                               text=True, capture_output=True, timeout=90)
            self.assertEqual(r.returncode, 0, r.stderr)
            yield [*runner, str(output)]

    def run_case(self, cmd, *args):
        return subprocess.run([*cmd, *args], capture_output=True, text=True, timeout=15,
                              env={**os.environ, "ASAN_OPTIONS": "symbolize=0"})

    def test_ownership_closes_final_window_and_normal_path_can_reset(self):
        for cmd in self.compile("core", core_program()):
            for case in ("delayed-failure", "normal", "stale-owner", "capacity", "direct"):
                with self.subTest(compiler=cmd, case=case):
                    result = self.run_case(cmd, case)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_counterexample_if_seal_ignores_active_owners(self):
        broken = CORE.replace("guard_coordinator == current && !guard_active &&",
                              "guard_coordinator == current &&")
        self.assertNotEqual(broken, CORE)
        for cmd in self.compile("broken", core_program(broken)):
            result = self.run_case(cmd, "delayed-failure")
            self.assertIn("!reboot_guard_seal()", result.stderr)
            self.assertNotEqual(result.returncode, 0)

    def test_nor_shutdown_closes_three_byte_and_dedicated_opcode_devices(self):
        for cmd in self.compile("nor", nor_program()):
            for size, flags in (("16", "0"), ("32", "512")):
                args = ("shutdown", "239", "-1", "1", "0", "0", "0", "0", "0", size, flags)
                result = self.run_case(cmd, *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                row = json.loads(result.stdout)
                self.assertEqual((row["failures"], row["next"], row["reset"], row["commands"]),
                                 (0, -108, 0, []))
            result = self.run_case(cmd, "shutdown", "239", "-1", "1", "0", "1",
                                   "0", "0", "0", "16", "0")
            self.assertEqual(result.returncode, 0, result.stderr)
            row = json.loads(result.stdout)
            self.assertEqual((row["failures"], row["gate_blocked"], row["next"]), (4, 1, -108))

    def test_pci_probe_never_sets_master_even_when_adapter_allocation_fails(self):
        for cmd in self.compile("pci", pci_program()):
            for case in ("probe-oom-1", "probe-oom-2", "probe-attach-failure", "probe-success-free"):
                result = self.run_case(cmd, case)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_raeth_first_open_oom_and_close_stop_failure(self):
        for cmd in self.compile("raeth", raeth_program()):
            for case, quarantined in (("oom-1", 0), ("close-qbusy", 1)):
                result = self.run_case(cmd, case)
                self.assertEqual(result.returncode, 0, result.stderr)
                row = json.loads(result.stdout)
                self.assertLess(row["ret"], 0)
                self.assertEqual(row["quarantine"], quarantined)
                self.assertEqual(row["dma_on"], 0)
                if not quarantined:
                    self.assertEqual((row["live"], row["maps"], row["irq_live"], row["module"]),
                                     (0, 0, 0, 0))

    def test_watchdog_shutdown_vetoes_reset_if_disable_did_not_stick(self):
        for cmd in self.compile("watchdog", watchdog_program()):
            for case in ("stopped", "stuck"):
                result = self.run_case(cmd, case)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
