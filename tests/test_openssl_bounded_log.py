"""Real pinned BIO methods/private app functions; no whole OpenSSL/OCSP or target execution."""
from pathlib import Path
import hashlib,json,os,re,signal,socket,subprocess,sys,tarfile,tempfile,unittest
from openssl_log_harness import TARGETS,generate_source,patched_sources,read_inputs
ROOT=Path(__file__).resolve().parents[1]
PINS={'bss_log.c':'9b9f7c9c9a1e17d86269664c8b0e6efc4463275a7d07cb2938fa4c81b53afaa8','log.c':'d4d62f93f344d171b232267d9e704d73a50e44b04fd1bb7ce8b21d136ce36d03','log.h':'25a85b61b8a31d3f1e031ff35302fbf66cde937d2d0c8c989e33d7bb74bb7c0f','http_server.c':'b6c5c72e1df783e79926c82528992d05f945db380406fcf0512c17afc3e97537','ocsp.c':'8d92ad9bea9e650ff564ac867260a040c4c536af248ead57ff47fcc84c3fce2b'}
class OpenSSLBoundedLogTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='k2p-ossllog-',dir='/tmp');cls.base=Path(cls.temp.name).resolve();cls.endpoint=cls.base/'log';cls.inputs=read_inputs(ROOT)
  for name,legacy in [('new',False),('old',True)]:
   c=cls.base/(name+'.c');c.write_text(generate_source(cls.inputs,str(cls.endpoint),legacy))
   r=subprocess.run(['clang','-std=gnu99','-O1','-g','-Wall','-Wextra','-Wno-unused-parameter','-Werror','-fsanitize=address,undefined',str(c),'-o',str(c.with_suffix('')),'-pthread'],capture_output=True,text=True)
   if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def setUp(self):self.peer=None
 def tearDown(self):
  if self.peer:self.peer.close()
  if self.endpoint.exists():self.endpoint.unlink()
 def server(self,kind=socket.SOCK_DGRAM):
  self.peer=socket.socket(socket.AF_UNIX,kind);self.peer.bind(str(self.endpoint));self.peer.settimeout(.1)
  if kind==socket.SOCK_STREAM:self.peer.listen(2)
 def drain(self):
  out=[]
  while True:
   try:out.append(self.peer.recv(2048))
   except socket.timeout:break
  return out
 def run_probe(self,mode,binary='new',extra=()):
  r=subprocess.run([str(self.base/binary),mode,*extra],capture_output=True,text=True,timeout=5,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:symbolize=0'})
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  m=re.search(r'RESULT accepted=(-?\d+) alloc=(\d+) free=(\d+) max=(\d+) init=(\d+)',r.stdout);self.assertIsNotNone(m,r.stdout)
  return dict(zip(('accepted','alloc','free','max','init'),map(int,m.groups())))
 def test_pinned_fixtures_and_strict_patch_targets(self):
  for target in TARGETS:self.assertEqual(hashlib.sha256(self.inputs[target].encode()).hexdigest(),PINS[Path(target).name])
  good=patched_sources(self.inputs);self.assertEqual(set(good),set(TARGETS))
  for key,value in [('patch',self.inputs['patch'].replace('b/apps/ocsp.c','b/apps/other.c')),('crypto/bio/bss_log.c',self.inputs['crypto/bio/bss_log.c'].replace('    closelog();','    changed();'))]:
   with self.subTest(key=key),self.assertRaises(ValueError):patched_sources({**self.inputs,key:value})
 def test_normal_priority_literal_format_and_balanced_lifetime(self):
  self.server();r=self.run_probe('bio');msg=self.drain();self.assertEqual(r['accepted'],24);self.assertEqual(r['alloc'],r['free']);self.assertEqual(len(msg),1);self.assertTrue(msg[0].startswith(b'<156>'));self.assertIn(b'bio-a[',msg[0]);self.assertIn(b'literal %n %s %%',msg[0]);self.assertTrue(msg[0].endswith(b'\0'))
 def test_real_datagram_queue_full_and_recovery(self):
  self.server();sender=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);sender.setblocking(False)
  try:
   full=False
   for _ in range(4096):
    try:sender.sendto(b'f'*1024,str(self.endpoint))
    except BlockingIOError:full=True;break
    except OSError as e:
     if e.errno in (35,55,105,11):full=True;break
     raise
   self.assertTrue(full);r=self.run_probe('bio',extra=('128',));self.assertEqual(r['accepted'],24*128);self.drain();self.run_probe('bio');self.assertTrue(any(b'literal'in x for x in self.drain()))
  finally:sender.close()
 def test_old_actual_bio_delegates_to_blocking_backend(self):
  self.server(socket.SOCK_STREAM);p=subprocess.Popen([str(self.base/'old'),'bio','2000'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:symbolize=0'})
  connection,_=self.peer.accept()
  try:
   with self.assertRaises(subprocess.TimeoutExpired) as observed:p.communicate(timeout=.2)
   self.assertIn(b'LEGACY_STREAM_BACKPRESSURE nonblock=0',observed.exception.stderr)
  finally:
   if p.poll()is None:p.kill()
   p.communicate(timeout=2);connection.close()
 def test_old_actual_bio_allocates_entire_input(self):
  r=self.run_probe('long','old');print('OPENSSL_HEAP_OLD '+json.dumps(r,sort_keys=True),file=sys.stderr,flush=True);self.assertEqual(r['accepted'],1024*1024);self.assertEqual(r['max'],1024*1024+1)
 def test_new_large_input_accepted_with_bounded_heap_and_truncation(self):
  self.server();r=self.run_probe('long');print('OPENSSL_HEAP_NEW '+json.dumps(r,sort_keys=True),file=sys.stderr,flush=True);self.assertEqual(r['accepted'],1024*1024);self.assertLessEqual(r['max'],1024);self.assertEqual(r['alloc'],r['free']);msg=self.drain();self.assertEqual(len(msg),1);self.assertEqual(len(msg[0]),1024);self.assertTrue(msg[0].startswith(b'<158>'));self.assertIn(b'[truncated]',msg[0])
 def test_two_bios_do_not_share_tag_or_facility(self):
  self.server();r=self.run_probe('dual');msg=self.drain();self.assertEqual(r['accepted'],32);self.assertEqual([x.split(b'>',1)[0] for x in msg],[b'<156',b'<166',b'<156']);self.assertIn(b'bio-a[',msg[0]);self.assertIn(b'bio-b[',msg[1]);self.assertIn(b'bio-a[',msg[2])
 def test_create_allocation_failure_is_not_success(self):
  r=self.run_probe('fail-create');self.assertEqual(r['accepted'],0);self.assertEqual(r['init'],0);self.assertEqual(r['free'],0)
 def test_ctrl_allocation_failure_rejects_write_then_recovers(self):
  self.server();r=self.run_probe('fail-ctrl');self.assertEqual(r['accepted'],12);msg=self.drain();self.assertEqual(len(msg),1);self.assertIn(b'recovered[',msg[0]);self.assertIn(b'BACK',msg[0])
 def test_negative_null_and_empty_inputs(self):
  for mode in ('negative','null','empty'):
   with self.subTest(mode=mode):self.assertEqual(self.run_probe(mode)['accepted'],0)
 def test_embedded_nul_keeps_existing_c_string_log_semantics(self):
  self.server();r=self.run_probe('embedded');self.assertEqual(r['accepted'],13);msg=self.drain();self.assertIn(b': A\0',msg[0]);self.assertNotIn(b'SECRET',msg[0])
 def test_fork_child_ctrl_and_destroy_leave_parent_bio_valid(self):
  self.server();r=self.run_probe('fork');msg=self.drain();self.assertEqual(r['accepted'],14);self.assertTrue(any(b'child['in x and b'CHILD'in x for x in msg));self.assertTrue(any(b'bio-a['in x and b'PARENT'in x for x in msg));self.assertEqual(r['alloc'],r['free'])
 def test_separate_bios_can_write_from_threads_without_shared_transport_fd(self):
  self.server();r=self.run_probe('thread');self.assertEqual(r['accepted'],32);self.assertEqual(r['alloc'],r['free']);self.assertTrue(self.drain())
 def test_transport_errno_is_preserved(self):
  self.server();r=self.run_probe('transport-errno');self.assertEqual(r['accepted'],1);self.assertIn(b'ERRNO',self.drain()[0])
 def test_actual_app_private_function_keeps_priority_and_errno(self):
  self.server();r=self.run_probe('app');self.assertEqual(r['accepted'],1);msg=self.drain();self.assertTrue(msg[0].startswith(b'<30>'));self.assertIn(b'openssl-fixture[',msg[0]);self.assertIn(b'index file changed, reloading %n',msg[0])
 def test_make_extract_fresh_existing_idempotent_and_drift_rejected(self):
  with tempfile.TemporaryDirectory(prefix='k2p-osslmake-')as td:
   base=Path(td);lib=base/'trunk/libs/libssl';lib.mkdir(parents=True);shared=base/'trunk/user/shared';shared.mkdir(parents=True)
   (lib/'Makefile').write_text(self.inputs['makefile']);(lib/'openssl-bounded-log.patch').write_text(self.inputs['patch']);(shared/'bounded_syslog.h').write_text(self.inputs['header'])
   archive=lib/'openssl-3.5.9.tar.gz'
   with tarfile.open(archive,'w:gz')as t:
    for name in TARGETS:
     f=base/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(self.inputs[name]);t.add(f,arcname='openssl-3.5.9/'+name)
   cmd=['make','extract_test','SRC_SHA256='+hashlib.sha256(archive.read_bytes()).hexdigest()]
   def run():return subprocess.run(cmd,cwd=lib,capture_output=True,text=True)
   a=run();self.assertEqual(a.returncode,0,a.stdout+a.stderr);actual={n:(lib/'openssl-3.5.9'/n).read_text()for n in TARGETS};self.assertEqual(actual,patched_sources(self.inputs))
   self.assertEqual(run().returncode,0);self.assertEqual((lib/'openssl-3.5.9/crypto/bio/padavan_bounded_syslog.h').read_text(),self.inputs['header'])
   for name in TARGETS:(lib/'openssl-3.5.9'/name).write_text(self.inputs[name])
   self.assertEqual(run().returncode,0)
   (lib/'openssl-3.5.9/apps/lib/log.c').write_text(self.inputs['apps/lib/log.c']);self.assertNotEqual(run().returncode,0)
   (lib/'openssl-3.5.9/apps/lib/log.c').write_text(actual['apps/lib/log.c'])
   f=lib/'openssl-3.5.9/crypto/bio/bss_log.c';f.write_text(f.read_text().replace('padavan_log_open(context,','drifted_open(context,'));self.assertNotEqual(run().returncode,0)

 def test_make_config_signature_replaces_legacy_stamp_and_tracks_actual_flags(self):
  with tempfile.TemporaryDirectory(prefix='k2p-ossl-config-')as td:
   base=Path(td);lib=base/'trunk/libs/libssl';lib.mkdir(parents=True);shared=base/'trunk/user/shared';shared.mkdir(parents=True)
   (lib/'Makefile').write_text(self.inputs['makefile']);(lib/'openssl-bounded-log.patch').write_text(self.inputs['patch']);(shared/'bounded_syslog.h').write_text(self.inputs['header'])
   tree=lib/'openssl-3.5.9'
   for name in TARGETS:
    f=tree/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(self.inputs[name])
   configure=tree/'Configure';configure.write_text('#!/bin/sh\nprintf "configure\\n" >> ../configured.calls\nprintf "%s\\n" "$CFLAGS" > ../configured.flags\n');configure.chmod(0o700)
   archive=lib/'openssl-3.5.9.tar.gz';archive.write_bytes(b'public-hash-fixture')
   (lib/'config_done').write_bytes(b'')
   command=['make','config_test','SRC_SHA256='+hashlib.sha256(archive.read_bytes()).hexdigest()]
   def run(*flags):
    r=subprocess.run(command+list(flags),cwd=lib,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   run();self.assertIn('-DPADAVAN_OPENSSL_BOUNDED_LOG',(lib/'configured.flags').read_text());self.assertEqual((lib/'configured.calls').read_text().count('configure'),1)
   run();self.assertEqual((lib/'configured.calls').read_text().count('configure'),1)
   for n,flag in enumerate(('CPUFLAGS=-DRECONFIGURE=1','CROSS_COMPILE=private-other-','CONFIG_IPV6=y','OPENSSL_CIPHERS=no-tests'),2):
    run(flag);self.assertEqual((lib/'configured.calls').read_text().count('configure'),n)
   marker=base/'UNEXPECTED';literal='-DPRIVATE=`touch '+str(marker)+'`';run('CPUFLAGS='+literal);self.assertFalse(marker.exists());self.assertIn(literal,(lib/'configured.flags').read_text())
