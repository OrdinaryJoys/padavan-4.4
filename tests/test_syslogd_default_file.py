"""Actual BusyBox function+helpers, private native filesystem/faults only.
Foreign-owner checks use an explicit euid fixture; actual UID99 is a CI gate.
"""
from pathlib import Path
import hashlib,json,os,signal,subprocess,tempfile,unittest
from syslogd_file_harness import generate_source,read_inputs
ROOT=Path(__file__).resolve().parents[1]
class SyslogdDefaultFileTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='k2p-logfile-',dir='/tmp');cls.base=Path(cls.temp.name).resolve();cls.path=cls.base/'syslog.log';cls.target=cls.base/'target';cls.custom=cls.base/'custom';cls.inputs=read_inputs(ROOT)
  for name,legacy in [('new',False),('old',True)]:
   f=cls.base/(name+'.c');f.write_text(generate_source(cls.inputs,str(cls.path),legacy));r=subprocess.run(['clang','-std=gnu99','-O1','-g','-Wall','-Wextra','-Wno-unused-function','-Wno-deprecated-declarations','-Werror','-fsanitize=address,undefined',str(f),'-o',str(f.with_suffix(''))],capture_output=True,text=True)
   if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def setUp(self):
  for p in (self.path,self.target,self.custom):
   if p.is_dir()and not p.is_symlink():p.rmdir()
   else:p.unlink(missing_ok=True)
  self.target.write_bytes(b'');self.target.chmod(0o600)
 def run_probe(self,fault='',action='plain',path=None,binary='new'):
  r=subprocess.run([str(self.base/binary),str(self.path if path is None else path),fault,str(self.target),action],capture_output=True,text=True,timeout=4,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:symbolize=0'})
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);observation=json.loads(r.stdout.splitlines()[-1]);self.assertEqual(observation['fd_before'],observation['fd_after']);return observation,r
 def rejected(self,observation,result):
  self.assertEqual(observation['first_fd'],-2);self.assertEqual(observation['write_calls'],0);self.assertEqual(observation['console_calls'],0);self.assertEqual(observation['stderr_writes'],0);self.assertEqual(result.stderr,'');self.assertEqual(self.target.read_bytes(),b'')
 def test_original_function_fixture_is_bound_to_before_guard_revision(self):
  self.assertEqual(hashlib.sha256(self.inputs['old'].encode()).hexdigest(),'846342dc06085cff55a864a356c818ca770f1fb96b474234ec886fb29bf9efc9')
 def test_late_default_rotation_stat_failure_has_zero_initialized_size(self):
  o,r=self.run_probe('late_fstat_fail');self.assertEqual(o['regular'],0);self.assertEqual(o['size'],14);self.assertEqual(self.path.read_bytes(),b'PUBLIC_APPEND\n')
 def test_new_default_is0644_even_umask0000_nonblock_cloexec(self):
  o,r=self.run_probe();self.assertEqual(self.path.stat().st_mode&0o777,0o644);self.assertEqual(self.path.read_bytes(),b'PUBLIC_APPEND\n');self.assertEqual(o['nonblock'],1);self.assertEqual(o['cloexec'],1);self.assertGreaterEqual(o['last_fd'],3)
 def test_owned_legacy_modes_only_lose_group_other_write_and_private0600_stays(self):
  for mode,expected in [(0o666,0o644),(0o600,0o600),(0o660,0o640)]:
   self.path.write_bytes(b'');self.path.chmod(mode);o,r=self.run_probe();self.assertEqual(self.path.stat().st_mode&0o777,expected);self.assertEqual(o['chmod_calls'],0 if mode==0o600 else 1)
 def test_symlink_rejected_without_follow_chmod_write_or_fallback(self):
  self.target.chmod(0o666);self.path.symlink_to(self.target);o,r=self.run_probe();self.rejected(o,r);self.assertEqual(o['open_calls'],0);self.assertEqual(o['chmod_calls'],0);self.assertEqual(self.target.stat().st_mode&0o777,0o666)
 def test_hardlink_rejected_without_mutating_existing_target(self):
  self.target.chmod(0o666);os.link(self.target,self.path);o,r=self.run_probe();self.rejected(o,r);self.assertEqual(o['open_calls'],0);self.assertEqual(o['chmod_calls'],0);self.assertEqual(self.target.stat().st_mode&0o777,0o666)
 def test_fifo_and_directory_rejected_before_open(self):
  for kind in ('fifo','directory'):
   if kind=='fifo':os.mkfifo(self.path)
   else:self.path.mkdir()
   o,r=self.run_probe();self.rejected(o,r);self.assertEqual(o['open_calls'],0)
   self.path.rmdir()if self.path.is_dir()else self.path.unlink()
 def test_foreign_owner_model_is_not_chowned_chmodded_or_written(self):
  self.path.write_bytes(b'');self.path.chmod(0o666);o,r=self.run_probe('foreign_owner');self.rejected(o,r);self.assertEqual(o['open_calls'],0);self.assertEqual(o['chmod_calls'],0);self.assertEqual(self.path.stat().st_mode&0o777,0o666)
 def test_creation_slot_race_symlink_and_hardlink_are_rechecked(self):
  for fault in ('symlink_race','hardlink_race'):
   self.path.unlink(missing_ok=True);self.target.chmod(0o666);o,r=self.run_probe(fault);self.rejected(o,r);self.assertEqual(o['chmod_calls'],0);self.assertEqual(self.target.stat().st_mode&0o777,0o666)
  self.path.unlink(missing_ok=True);o,r=self.run_probe('eexist_storm');self.rejected(o,r);self.assertEqual(o['open_calls'],3)
 def test_safe_owned_mode_migration_failure_drops_and_retry_recovers(self):
  self.path.write_bytes(b'');self.path.chmod(0o666);o,r=self.run_probe('chmod_fail','retry');self.assertEqual(o['first_fd'],-2);self.assertGreaterEqual(o['last_fd'],3);self.assertEqual(o['console_calls'],0);self.assertEqual(self.path.read_bytes(),b'RECOVERED\n');self.assertEqual(self.path.stat().st_mode&0o777,0o644)
 def test_descriptor_or_metadata_failures_close_and_drop_without_fallback(self):
  for fault in ('fstat_fail','fcntl_fail','missing_nonblock','missing_cloexec'):
   self.path.unlink(missing_ok=True);o,r=self.run_probe(fault);self.rejected(o,r);self.assertGreaterEqual(o['close_calls'],1)
 def test_closed_stdin_or_stdout_does_not_turn_default_into_dash_output(self):
  for action in ('close-stdin','close-stdout'):
   self.path.unlink(missing_ok=True);o,r=self.run_probe('',action);self.assertGreaterEqual(o['last_fd'],3);self.assertEqual(self.path.read_bytes(),b'PUBLIC_APPEND\n');self.assertEqual(o['cloexec'],1)
 def test_low_descriptor_dup_failure_is_safe_closed_and_nonfatal(self):
  o,r=self.run_probe('dup_fail','close-stdin');self.rejected(o,r);self.assertGreaterEqual(o['close_calls'],1)
 def test_every_second_reopen_revalidates_name(self):
  o,r=self.run_probe('','reopen');self.assertEqual(o['open_calls'],2);self.assertEqual(self.path.read_bytes(),b'PUBLIC_APPEND\nREOPENED\n')
  self.path.unlink();o,r=self.run_probe('','reopen-alias');self.assertEqual(o['last_fd'],-2);self.assertEqual(self.target.read_bytes(),b'');self.assertEqual(o['console_calls'],0)
 def test_rotation_recreates_safe_default_and_rejects_replacement_gap(self):
  self.path.write_bytes(b'old-data\n');o,r=self.run_probe('','rotation');self.assertEqual(o['open_calls'],2);self.assertEqual(self.path.read_bytes(),b'PUBLIC_APPEND\n');self.assertEqual(self.path.stat().st_mode&0o777,0o644)
  self.path.write_bytes(b'old-data\n');o,r=self.run_probe('rotation_symlink','rotation');self.assertEqual(o['last_fd'],-2);self.assertEqual(o['console_calls'],0);self.assertEqual(self.target.read_bytes(),b'')
 def test_rejected_path_admin_repair_recovers_in_same_process(self):
  self.path.symlink_to(self.target);o,r=self.run_probe('','recover');self.assertEqual(o['first_fd'],-2);self.assertGreaterEqual(o['last_fd'],3);self.assertEqual(self.path.read_bytes(),b'RECOVERED\n');self.assertEqual(o['console_calls'],0);self.assertEqual(r.stderr,'')
 def test_unsafe_default_never_falls_back_into_full_blocking_stderr(self):
  self.path.symlink_to(self.target);read_fd,write_fd=os.pipe();os.set_blocking(write_fd,False)
  try:
   while True:
    try:os.write(write_fd,b'x'*4096)
    except BlockingIOError:break
   os.set_blocking(write_fd,True);p=subprocess.Popen([str(self.base/'new'),str(self.path),'',str(self.target),'plain'],stdout=subprocess.PIPE,stderr=write_fd,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:symbolize=0'})
   try:out,_=p.communicate(timeout=3)
   except subprocess.TimeoutExpired:p.kill();p.communicate(timeout=2);self.fail('default rejection blocked in stderr fallback')
   self.assertEqual(p.returncode,0);o=json.loads(out.splitlines()[-1]);self.assertEqual(o['console_calls'],0);self.assertEqual(o['stderr_writes'],0)
  finally:os.close(read_fd);os.close(write_fd)
 def test_generic_rotation_fstat_failure_does_not_consume_undefined_size(self):
  o,r=self.run_probe('fstat_fail',path=self.custom);self.assertEqual(o['regular'],0);self.assertEqual(o['size'],14)
  self.custom.unlink();old,_=self.run_probe('fstat_fail',path=self.custom,binary='old');self.assertEqual(old['regular'],0);self.assertEqual(old['size'],0x11111111+14)
 def test_explicit_custom_symlink_and_stdout_keep_legacy_policy(self):
  self.custom.symlink_to(self.target);o,r=self.run_probe(path=self.custom);self.assertEqual(self.target.read_bytes(),b'PUBLIC_APPEND\n');self.assertEqual(o['cloexec'],0)
  o,r=self.run_probe(path='-');self.assertTrue(r.stdout.startswith('PUBLIC_APPEND\n'));self.assertEqual(o['last_fd'],1)
 def test_explicit_custom_fifo_remains_supported(self):
  os.mkfifo(self.custom);reader=os.open(self.custom,os.O_RDONLY|os.O_NONBLOCK)
  try:o,r=self.run_probe(path=self.custom);self.assertEqual(os.read(reader,100),b'PUBLIC_APPEND\n');self.assertEqual(o['regular'],0)
  finally:os.close(reader)
