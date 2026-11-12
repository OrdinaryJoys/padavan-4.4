"""MAC failure atomicity, raw-address initialization and unsigned MMIO packing."""
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import raeth_mac_harness as h

ROOT = Path(__file__).resolve().parents[1]
OLD = '2b02d767a1f1f53f6a8e318417439382cdaf722b'
FIXTURE_SHA = 'e3c43465758307ca3ad8fbe9b2456bc0db46cb879c12d228690b0e974b864467'
UNCHANGED = [0xdeadbeef] * 4


class RaethMacTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='raeth-mac-')
        cls.directory = Path(cls.temp.name)
        cls.texts = h.current_texts()
        fixture = (ROOT/'tests/fixtures/raeth-mac/2b02-before.json').read_bytes()
        if hashlib.sha256(fixture).hexdigest() != FIXTURE_SHA:
            raise AssertionError('Historical whole-function fixture changed')
        data = json.loads(fixture)
        if data['commit'] != OLD or set(data['functions']) != set(h.FUNCTION_SOURCES):
            raise AssertionError('Historical fixture source identity changed')
        baseline = {k:'' for k in h.SOURCE_PATHS}
        for name, row in data['functions'].items():
            key = h.FUNCTION_SOURCES[name]
            if row['path'] != h.SOURCE_PATHS[key]: raise AssertionError('Wrong source')
            baseline[key] += row['body'] + '\n'
        cls.current = []
        cls.old = []
        gcc, clang = shutil.which('gcc-16'), shutil.which('clang')
        if not gcc or not clang: raise AssertionError('GNU16 and Clang required')
        for label, compiler, flags in (
            ('gcc', gcc, []),
            ('clang', clang, ['-fsanitize=address,undefined','-fno-sanitize-recover=all']),
        ):
            cls.current.append(cls.compile(h.generate_source(cls.texts),label,compiler,flags))
            cls.old.append(cls.compile(h.generate_source(baseline),'old-'+label,compiler,flags))
        # Required by the locked Linux build, never treated as a skipped test.
        target = os.environ.get('RAETH_MAC_TARGET_CC')
        if target:
            runner = shutil.which('qemu-mipsel')
            if not runner: raise AssertionError('Target compiler requires qemu-mipsel')
            command = cls.compile(h.generate_source(cls.texts),'mips',target,['-static'])
            cls.current.append([runner,*command])

    @classmethod
    def compile(cls, code, name, compiler, flags):
        source = cls.directory/(name+'.c'); source.write_text(code)
        binary = source.with_suffix('')
        result = subprocess.run([compiler,'-std=gnu99','-O2','-Wall','-Wextra','-Werror',
                                 *flags,str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
        if result.returncode: raise AssertionError(result.stderr)
        return [str(binary)]

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def run_case(self, binary, name, success=True):
        r = subprocess.run([*binary,name],capture_output=True,text=True,timeout=10,
                           env={**os.environ,'ASAN_OPTIONS':'symbolize=0'})
        if not success: return r
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stderr,'')
        return json.loads(r.stdout)

    def check(self, name, *, ret=0, mac='021280345678', registers=None, writes=0, random=0):
        expected = dict(ret=ret,mac=mac,registers=registers or UNCHANGED,writes=writes,random=random)
        for binary in self.current:
            with self.subTest(binary=binary,case=name):
                target_expected = dict(expected)
                # MIPS Linux errno ABI differs from macOS and x86 Linux.
                if len(binary) == 2 and ret == -errno.EADDRNOTAVAIL:
                    target_expected['ret'] = -126
                self.assertEqual(self.run_case(binary,name),target_expected)

    def test_busy_interfaces_keep_both_software_and_hardware_addresses(self):
        for name in ('main-up','second-up'): self.check(name,ret=-errno.EBUSY)

    def test_invalid_addresses_never_mutate_either_interface(self):
        for interface in ('main','second'):
            for state in ('up','down'):
                for invalid in ('zero','multicast'):
                    self.check(f'{interface}-{state}-{invalid}',ret=-errno.EADDRNOTAVAIL)

    def test_down_interfaces_program_only_their_own_mac_registers(self):
        self.check('main-down',mac='0298fedcba76',registers=[0x0298,0xfedcba76,*UNCHANGED[:2]],writes=2)
        self.check('second-down',mac='0298fedcba76',registers=[*UNCHANGED[:2],0x0298,0xfedcba76],writes=2)

    def test_initialization_uses_full_valid_or_generated_raw_address(self):
        self.check('init-valid',registers=[0x0212,0x80345678,*UNCHANGED[:2]],writes=2)
        self.check('init-invalid',mac='02abcdef1234',registers=[0x02ab,0xcdef1234,*UNCHANGED[:2]],writes=2,random=1)

    def test_exact_old_busy_callbacks_demonstrate_changed_software_only(self):
        for name in ('main-up','second-up'):
            for binary in self.old:
                row = self.run_case(binary,name)
                self.assertEqual(row,dict(ret=-errno.EBUSY,mac='0298fedcba76',registers=UNCHANGED,writes=0,random=0))

    def test_exact_old_initializer_demonstrates_sockaddr_offset_and_overlap(self):
        row = self.run_case(self.old[0],'init-valid')
        self.assertEqual(row['mac'],'803456780000')
        r = self.run_case(self.old[1],'init-valid',success=False)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('memcpy-param-overlap',r.stderr)

    def test_exact_old_high_bit_shift_triggers_undefined_behavior(self):
        for name in ('main-down','second-down'):
            r = self.run_case(self.old[1],name,success=False)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('left shift of 254 by 24',r.stderr)

    def test_production_callbacks_and_probe_retain_real_wiring(self):
        text = self.texts['raeth']
        self.assertIn('.ndo_set_mac_address = ei_set_mac_addr,',text)
        self.assertIn('.ndo_set_mac_address = ei_set_mac2_addr,',text)
        self.assertIn('ei_mac_addr_setting(netdev);',h.function(text,'rather_probe'))
        code = h.generate_source(self.texts)
        for name,key in h.FUNCTION_SOURCES.items():
            self.assertEqual(code.count(h.function(self.texts[key],name)),1)


if __name__ == '__main__': unittest.main()
