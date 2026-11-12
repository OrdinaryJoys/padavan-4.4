"""NOR address-mode errors, retirement, scan and restart-veto propagation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import nor_address_harness as h

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA256 = '34d89b147fe33a20c5d329f37c200001aa97e7fcfd5fb682bcca5bb03daec07d'

class NorAddressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='nor-address-');cls.root=Path(cls.temp.name)
        cls.texts=h.current_texts();raw=(ROOT/'tests/fixtures/nor-address-35b8.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=FIXTURE_SHA256:raise AssertionError('Historical NOR fixture changed')
        cls.old=json.loads(raw)
        if cls.old['commit']!='35b869aa8b4b81a793dd781df7beb0ea22dee4af' or set(cls.old['functions'])!=set(h.OLD_FUNCTIONS):raise AssertionError('Historical inventory differs')
        for n,row in cls.old['functions'].items():
            if row['path']!=h.SOURCE_PATHS[h.FUNCTION_SOURCES[n]]:raise AssertionError('Historical path differs')
        cls.current=[];cls.previous=[]
        for label,compiler,flags in [('gcc',shutil.which('gcc-16'),[]),('clang',shutil.which('clang'),['-fsanitize=address,undefined','-fno-sanitize-recover=all'])]:
            if not compiler:raise AssertionError('GNU16 and Clang required')
            cls.current.append(cls.compile(h.generate(cls.texts),label,compiler,flags))
            cls.previous.append(cls.compile(h.generate(cls.texts,cls.old),'old-'+label,compiler,flags))
        target=os.environ.get('NOR_ADDRESS_TARGET_CC')
        if target:
            runner=shutil.which('qemu-mipsel')
            if not runner:raise AssertionError('qemu-mipsel required')
            cls.current.append([runner,*cls.compile(h.generate(cls.texts),'mips',target,['-static'])])

    @classmethod
    def compile(cls,code,name,compiler,flags):
        path=cls.root/(name+'.c');path.write_text(code);out=path.with_suffix('')
        r=subprocess.run([compiler,'-std=gnu99','-O2','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-sign-compare',*flags,str(path),'-o',str(out)],capture_output=True,text=True,timeout=60)
        if r.returncode:raise AssertionError(r.stderr)
        return [str(out)]

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def row(self,binary,action='restore',mfr=0xef,op=-1,nth=1,accepted=0,busy=0,prepare=0,unregister=0,sus=0,size=32,flags=0):
        args=[action,mfr,op,nth,accepted,busy,prepare,unregister,sus,size,flags]
        r=subprocess.run([*binary,*map(str,args)],capture_output=True,text=True,timeout=10,env={**os.environ,'ASAN_OPTIONS':'symbolize=0'})
        self.assertEqual(r.returncode,0,(args,r.stderr));self.assertEqual(r.stderr,'');return json.loads(r.stdout)

    def test_enter_exit_manufacturer_protocols_and_ready_completion(self):
        for binary in self.current:
            for mfr in (0xef,0xc2,0x20,0x9d):
                for action,wanted in (('enter',4),('exit',3)):
                    r=self.row(binary,action,mfr=mfr,busy=3)
                    self.assertEqual((r['ret'],r['mode'],r['busy'],r['write_busy'],r['wel']),(0,wanted,0,0,0))
                    if mfr==0xef and action=='exit':self.assertIn(0xc5,r['commands']);self.assertEqual(r['ear'],0)
                    if mfr==0x9d:self.assertEqual(r['commands'],[0x17])

    def test_each_write_enable_failure_stops_the_next_command(self):
        for binary in self.current:
            for accepted in (0,1):
                r=self.row(binary,op=0x06,accepted=accepted)
                self.assertEqual((r['ret'],r['commands'],r['reset']),(-5,[6],0))
                r=self.row(binary,op=0x06,nth=2,accepted=accepted)
                self.assertEqual((r['ret'],r['commands'],r['reset']),(-5,[6,0xe9,4,6],0))

    def test_mode_ear_and_disable_errors_are_not_overwritten_by_success(self):
        for binary in self.current:
            for op,nth in ((0xe9,1),(0xc5,1),(4,1),(4,2)):
                for accepted in (0,1):
                    r=self.row(binary,op=op,nth=nth,accepted=accepted,busy=3)
                    self.assertEqual((r['ret'],r['again'],r['reset'],r['write_busy']),(-5,-5,0,0))
                    self.assertEqual((r['next'],r['restore_error']),(-108,-5))

    def test_initial_busy_read_error_and_postcommand_unknown_fail_closed(self):
        for binary in self.current:
            for options,error,commands in (({'busy':1},-110,[]),({'op':5},-5,[]),({'busy':2},-110,[6,0xe9]),({'busy':4},-5,[6,0xe9])):
                r=self.row(binary,**options)
                self.assertEqual((r['ret'],r['commands'],r['next'],r['write_busy']),(error,commands,-108,0))
            r=self.row(binary,op=0xe9,accepted=1,busy=2)
            self.assertEqual((r['ret'],r['commands']),(-110,[6,0xe9]))

    def test_suspended_and_unreadable_winbond_status_prevent_address_or_reset_commands(self):
        for binary in self.current:
            for action in ('enter','restore','scan'):
                for options,error in (({'sus':1},-16),({'op':0x35},-5)):
                    r=self.row(binary,action,**options)
                    self.assertEqual((r['ret'],r['commands'],r['registered']),(error,[],0))

    def test_restore_retires_io_and_is_idempotent_on_success_and_prepare_error(self):
        for binary in self.current:
            for prepare in (0,-12):
                r=self.row(binary,prepare=prepare)
                self.assertEqual((r['ret'],r['again'],r['restore_error']),(prepare,prepare,prepare))
                self.assertEqual((r['next'],r['restore_started'],r['retired_reads']),(-108,1,0))
                self.assertEqual((r['prepare'],r['unprepare']),(1,0 if prepare else 1))
                self.assertEqual(r['reset'],0 if prepare else 1)

    def test_real_queued_reader_is_rejected_after_locked_restore_success_or_failure(self):
        for binary in self.current:
            for options,result in (({},0),({'op':0xc5},-5)):
                r=self.row(binary,'queued',**options)
                self.assertEqual((r['ret'],r['next'],r['again'],r['retired_reads']),(result,-108,result,0))

    def test_shutdown_latches_all_restore_errors_and_reset_attempt_settles(self):
        for binary in self.current:
            for op in (6,0xe9,0xc5,4,0x66,0x99):
                r=self.row(binary,'shutdown',op=op,accepted=1)
                self.assertEqual((r['failures'],r['restore_error'],r['next'],r['gate_blocked']),(4,-5,-108,1))
                self.assertEqual(r['delay'],1 if op==0x99 else 0)
            r=self.row(binary,'shutdown');self.assertEqual((r['failures'],r['reset'],r['delay'],r['gate_blocked']),(0,1,1,0))

    def test_reset_address_status_and_bank_are_read_back_before_success(self):
        for binary in self.current:
            for options in ({'op':0x15},{'op':0xc8},{'busy':5},{'busy':6}):
                r=self.row(binary,'shutdown',**options)
                self.assertEqual((r['restore_error'],r['failures'],r['gate_blocked']),(-5,4,1))
                self.assertEqual((r['next'],r['again'],r['reset']),(-108,-5,1))

    def test_scan_rejects_mode_errors_before_mtd_registration(self):
        for binary in self.current:
            for mfr,op in ((0xef,6),(0xef,0xb7),(0xef,4),(0xc2,0xb7),(0x20,6),(0x9d,0x17)):
                r=self.row(binary,'scan',mfr=mfr,op=op)
                self.assertEqual((r['ret'],r['registered'],r['failures']),(-5,0,4))
            r=self.row(binary,'scan');self.assertEqual((r['ret'],r['registered'],r['mode']),(0,1,4))

    def test_standard_capacity_and_dedicated_opcodes_keep_mode_path_unentered(self):
        for binary in self.current:
            for options in ({'size':16},{'flags':0x200},{'mfr':1}):
                r=self.row(binary,'scan',op=0xb7,**options)
                self.assertEqual((r['ret'],r['registered'],r['commands']),(0,1,[]))
                r=self.row(binary,'restore',**options)
                self.assertEqual((r['ret'],r['restore_started'],r['commands']),(0,0,[]))

    def test_remove_unregisters_before_restore_and_preserves_restore_failure(self):
        for binary in self.current:
            r=self.row(binary,'remove',unregister=-16)
            self.assertEqual((r['ret'],r['registered'],r['commands'],r['restore_started']),(-16,1,[],0))
            r=self.row(binary,'remove',op=0xe9)
            self.assertEqual((r['ret'],r['registered'],r['failures']),(-5,0,4))

    def test_exact_previous_bodies_reproduce_ignored_failures_and_live_mode_change(self):
        for binary in self.previous:
            r=self.row(binary,'scan',op=6)
            self.assertEqual((r['ret'],r['registered']),(0,1))
            r=self.row(binary,'shutdown',op=0xc5)
            self.assertEqual((r['failures'],r['next']),(0,0));self.assertGreater(r['reset'],0)
            r=self.row(binary,'remove',unregister=-16)
            self.assertEqual(r['ret'],-16);self.assertIn(0xe9,r['commands'])

    def test_whole_production_bodies_and_driver_binding_remain_explicit(self):
        generated=h.generate(self.texts)
        for name,key in h.FUNCTION_SOURCES.items():self.assertEqual(generated.count(h.base.extract(self.texts[key],name)),1,name)
        self.assertIn('int spi_nor_restore(struct spi_nor *nor);',self.texts['nor_header'])
        self.assertIn('.suppress_bind_attrs = true,',self.texts['m25p'])

if __name__=='__main__':unittest.main()
