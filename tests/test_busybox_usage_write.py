"""Exercise the real BusyBox host usage generator under write failures."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'trunk/user/busybox/busybox-1.24.x/applets/usage.c'

class BusyboxUsageWriteTests(unittest.TestCase):
 def test_complete_output_and_failure_propagation(self):
  cc = shutil.which('cc')
  self.assertIsNotNone(cc)
  with tempfile.TemporaryDirectory(prefix='busybox-usage-') as name:
   root=Path(name)
   (root/'autoconf.h').write_text('#define ENABLE_NOMMU 0\n')
   (root/'usage.h').write_text('')
   (root/'applets.h').write_text('MAKE_USAGE("z", "xyz")\nMAKE_USAGE("a", "hello")\n')
   (root/'stub.c').write_text('''#include <errno.h>\n#include <stdlib.h>\n#include <string.h>\n#include <unistd.h>\nssize_t test_write(int fd,const void *p,size_t n) { static int once; const char *m=getenv("WRITE_MODE"); if (!strcmp(m,"eintr") && !once++) { errno=EINTR; return -1; } if (!strcmp(m,"zero")) return 0; if (!strcmp(m,"error")) { errno=ENOSPC; return -1; } if (!strcmp(m,"short") && n>2) n=2; return write(fd,p,n); }\n''')
   subprocess.run([cc,'-std=gnu99','-O2','-Wall','-Wextra','-Werror','-I',str(root),'-Dwrite=test_write','-c',str(SOURCE),'-o',str(root/'usage.o')],check=True,capture_output=True)
   subprocess.run([cc,'-std=gnu99','-Wall','-Wextra','-Werror',str(root/'stub.c'),str(root/'usage.o'),'-o',str(root/'usage')],check=True,capture_output=True)
   for mode in ('short','eintr','zero','error'):
    with self.subTest(mode=mode):
     done=subprocess.run([str(root/'usage')],env={**os.environ,'WRITE_MODE':mode},capture_output=True,timeout=5)
     self.assertEqual(done.returncode,0 if mode in ('short','eintr') else 1)
     self.assertEqual(done.stdout,b'hello\0xyz\0' if mode in ('short','eintr') else b'')
 def test_generation_refuses_failed_producer_and_preserves_existing_header(self):
  generator=SOURCE.with_name('usage_compressed')
  with tempfile.TemporaryDirectory(prefix='busybox-compressed-') as name:
   root=Path(name); output=root/'usage_compressed.h'; writer=root/'usage'
   output.write_text('previous header\n')
   writer.write_text('#!/bin/sh\nprintf partial\nexit 1\n');writer.chmod(0o755)
   result=subprocess.run(['sh',str(generator),str(output),str(root)],capture_output=True,timeout=5)
   self.assertNotEqual(result.returncode,0)
   self.assertEqual(output.read_text(),'previous header\n')
   self.assertEqual(sorted(p.name for p in root.iterdir()),['usage','usage_compressed.h'])
   writer.write_text('#!/bin/sh\nprintf "hello\\000world\\000"\n')
   result=subprocess.run(['sh',str(generator),str(output),str(root)],env={**os.environ,'DD':'false'},capture_output=True,timeout=5)
   self.assertNotEqual(result.returncode,0)
   self.assertEqual(output.read_text(),'previous header\n')
   result=subprocess.run(['sh',str(generator),str(output),str(root)],capture_output=True,timeout=5)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertIn('#define UNPACKED_USAGE',output.read_text())
   self.assertIn('#define PACKED_USAGE',output.read_text())
   self.assertEqual(sorted(p.name for p in root.iterdir()),['usage','usage_compressed.h'])
if __name__=='__main__':unittest.main()
