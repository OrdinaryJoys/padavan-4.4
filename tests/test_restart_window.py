"""Final reset observation windows: native sanitizers, target MIPS and old code."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import restart_window_harness as h

ROOT = Path(__file__).resolve().parents[1]
BASE = '8c49bb0192b6cbbefe1f1dd6be383443ce705495'
FIXTURE_SHA256 = 'ee63b768f7aa17278bdc4ff0a80bc2515056f403f57d81e38b68f6dc323cd4fd'


class RestartWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='restart-window-')
        cls.root = Path(cls.temp.name); cls.texts = h.current_texts()
        raw = (ROOT/'tests/fixtures/restart-window-8c49.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
            raise AssertionError('Historical restart fixture changed')
        old = json.loads(raw)
        if old['commit'] != BASE or set(old['functions']) != set(h.FUNCTION_SOURCES):
            raise AssertionError('Historical whole-function inventory differs')
        baseline = dict(cls.texts)
        for name, row in old['functions'].items():
            key = h.FUNCTION_SOURCES[name]
            if row['path'] != h.SOURCE_PATHS[key]: raise AssertionError('Wrong historical source')
            baseline[key] = baseline[key].replace(h.function(baseline[key], name), row['body'])
        cls.current = []; cls.old = []
        compilers = [('gcc', shutil.which('gcc-16'), []),
                     ('clang', shutil.which('clang'), ['-fsanitize=address,undefined','-fno-sanitize-recover=all'])]
        if not all(c for _,c,_ in compilers): raise AssertionError('GNU16 and Clang required')
        for label, compiler, flags in compilers:
            for pci in (0, 1):
                cls.current.append((pci, cls.compile(h.generate(cls.texts), label+str(pci), compiler, flags, pci)))
                cls.old.append((pci, cls.compile(h.generate(baseline), 'old-'+label+str(pci), compiler, flags, pci)))
        target = os.environ.get('RESTART_WINDOW_TARGET_CC')
        if target:
            runner = shutil.which('qemu-mipsel')
            if not runner: raise AssertionError('qemu-mipsel required with target compiler')
            for pci in (0, 1):
                binary = cls.compile(h.generate(cls.texts), 'mips'+str(pci), target, ['-static'], pci)
                cls.current.append((pci, [runner,*binary]))

    @classmethod
    def compile(cls, code, name, compiler, flags, pci):
        path = cls.root/(name+'.c'); path.write_text(code); out = path.with_suffix('')
        r = subprocess.run([compiler,'-std=gnu99','-O2','-pthread','-Wall','-Wextra','-Werror',
                            '-Wno-unused-parameter',f'-DWITH_PCI={pci}',*flags,str(path),'-o',str(out)],
                           capture_output=True,text=True,timeout=60)
        if r.returncode: raise AssertionError(r.stderr)
        return [str(out)]

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def run_case(self, command, case):
        r = subprocess.run([*command,case],capture_output=True,text=True,timeout=10,
                           env={**os.environ,'ASAN_OPTIONS':'symbolize=0'})
        self.assertEqual(r.returncode,0,r.stderr); self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def test_success_masks_local_interrupts_before_both_reset_writes(self):
        for pci, binary in self.current:
            row = self.run_case(binary,'success')
            self.assertEqual(row,dict(reasons=0,terminal=2,irq_off=1,injected=0,gate_reads=2,
                                     pci_reset=pci,system_reset=1,pci_irq_off=pci,system_irq_off=1,delay_calls=pci))

    def test_irq_mask_edge_report_vetoes_every_reset(self):
        for pci, binary in self.current:
            row = self.run_case(binary,'irq-mask-edge')
            self.assertEqual(row,dict(reasons=2,terminal=1,irq_off=1,injected=1,gate_reads=1,
                                     pci_reset=0,system_reset=0,pci_irq_off=0,system_irq_off=0,delay_calls=0))

    def check_late(self, case):
        for pci, binary in self.current:
            if case != 'after-first-read' and not pci: continue
            row = self.run_case(binary,case)
            self.assertEqual(row,dict(reasons=2,terminal=1,irq_off=1,injected=1,gate_reads=2,
                                     pci_reset=pci,system_reset=0,pci_irq_off=pci,system_irq_off=0,delay_calls=pci))

    def test_cross_cpu_report_after_first_observation_vetoes_system_reset(self):
        self.check_late('after-first-read')

    def test_cross_cpu_report_during_pci_write_vetoes_system_reset(self):
        self.check_late('pci-write')

    def test_cross_cpu_report_during_pci_settle_vetoes_system_reset(self):
        self.check_late('pci-delay')

    def test_preexisting_failure_is_sticky_and_stops_before_pci(self):
        for _, binary in self.current:
            row = self.run_case(binary,'preexisting')
            self.assertEqual((row['reasons'],row['terminal'],row['pci_reset'],row['system_reset']), (1,1,0,0))

    def test_exact_previous_functions_reproduce_the_two_unchecked_windows(self):
        for pci, binary in self.old:
            for case in ('irq-mask-edge','after-first-read','pci-write','pci-delay'):
                if not pci and case in ('pci-write','pci-delay'): continue
                row = self.run_case(binary,case)
                self.assertEqual((row['reasons'],row['injected'],row['system_reset']), (2,1,1))

    def test_whole_bodies_and_board_registration_remain_bound(self):
        code = h.generate(self.texts)
        for name, key in h.FUNCTION_SOURCES.items():
            self.assertEqual(code.count(h.function(self.texts[key],name)),1)
        self.assertIn('_machine_restart = ralink_restart;', self.texts['arch'])
        body = h.function(self.texts['arch'],'ralink_restart')
        self.assertLess(body.index('local_irq_disable();'),body.index('reboot_dma_failure_check(false);'))
        self.assertEqual(body.count('reboot_dma_failure_check(false);'),2)
        self.assertLess(body.index('mdelay(50);'),body.rindex('reboot_dma_failure_check(false);'))


if __name__ == '__main__': unittest.main()
