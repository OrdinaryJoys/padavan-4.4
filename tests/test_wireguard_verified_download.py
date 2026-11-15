"""Exercise the real download recipe with deterministic fake network responses."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
MAKEFILE=ROOT/'trunk/user/wireguard-tools/Makefile'
WGET=r'''#!/usr/bin/env python3
import os,sys
from pathlib import Path
p=Path(os.environ['MOCK_COUNT']);count=int(p.read_text()) if p.exists() else 0
p.write_text(str(count+1));parts=os.environ['MOCK_SEQUENCE'].split(',');mode=parts[min(count,len(parts)-1)]
args=sys.argv;dest=Path(args[args.index('-O')+1])
if mode=='good':dest.write_bytes(Path(os.environ['MOCK_BODY']).read_bytes())
elif mode=='empty':dest.write_bytes(b'')
elif mode=='bad':dest.write_bytes(b'incorrect body')
elif mode=='fail':dest.write_bytes(b'incomplete');sys.exit(8)
else:sys.exit(9)
'''

class WireguardVerifiedDownloadTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='k2p-wireguard-');self.addCleanup(self.tmp.cleanup)
  self.dir=Path(self.tmp.name)/'directory with spaces';self.dir.mkdir();self.bin=self.dir/'bin';self.bin.mkdir()
  self.body=self.dir/'source-body';self.body.write_bytes(b'known and pinned source archive\n');self.digest=hashlib.sha256(self.body.read_bytes()).hexdigest()
  self.count=self.dir/'attempts';self.archive=self.dir/'fixture.tar.xz'
  wget=self.bin/'wget';wget.write_text(WGET);wget.chmod(0o755)
 def run_download(self,sequence):
  env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],MOCK_COUNT=str(self.count),MOCK_BODY=str(self.body),MOCK_SEQUENCE=sequence)
  return subprocess.run(['make','-f',str(MAKEFILE),'download_test','SRC_NAME=fixture','SRC_URL=https://example.invalid/source','SRC_SHA256='+self.digest],cwd=self.dir,env=env,text=True,capture_output=True,timeout=20)
 def count_attempts(self):return int(self.count.read_text()) if self.count.exists() else 0
 def assert_no_temporary_files(self):self.assertEqual(list(self.dir.glob('fixture.tar.xz.tmp.*')),[])
 def test_valid_cached_archive_never_calls_network(self):
  self.archive.write_bytes(self.body.read_bytes());r=self.run_download('fail')
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.count_attempts(),0);self.assert_no_temporary_files()
 def test_empty_response_is_retried_and_verified_before_publish(self):
  r=self.run_download('empty,good');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  self.assertEqual(self.count_attempts(),2);self.assertEqual(self.archive.read_bytes(),self.body.read_bytes());self.assert_no_temporary_files()
 def test_invalid_cache_is_replaced_only_with_verified_data(self):
  self.archive.write_bytes(b'old corrupt file');r=self.run_download('bad,good')
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.count_attempts(),2)
  self.assertEqual(self.archive.read_bytes(),self.body.read_bytes());self.assert_no_temporary_files()
 def test_exhausted_attempts_fail_and_preserve_previous_file(self):
  old=b'existing corrupt cache';self.archive.write_bytes(old);r=self.run_download('fail,empty,bad')
  self.assertNotEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.count_attempts(),3)
  self.assertEqual(self.archive.read_bytes(),old);self.assert_no_temporary_files()
if __name__=='__main__':unittest.main()
