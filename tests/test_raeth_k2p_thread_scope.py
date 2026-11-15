"""Source-bound K2P thread reachability and chip-identification failure tests."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from mt7621_wdt_harness import function

ROOT=Path(__file__).resolve().parents[1]
K=ROOT/'trunk/linux-4.4.x'
SOURCE=K/'drivers/net/ethernet/raeth/raether.c'
PREFIX=r'''
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <strings.h>
#include <string.h>
#define MT7621_FE 7621
#define MT7622_FE 7622
#define MT7623_FE 7623
#define LEOPARD_FE 7650
struct END_DEVICE { int chip_name; };
struct device {void *of_node;};
struct platform_device {struct device dev;};
static const char *value;
static int retcode;
static int of_property_read_string(void*n,const char*k,const char**out){(void)n;assert(!strcmp(k,"compatible"));if(retcode)return retcode;*out=value;return 0;}
#define pr_info(...) ((void)0)
'''
SUFFIX=r'''
int main(int argc,char**argv){struct END_DEVICE d={0};struct platform_device p={0};int ret;
 assert(argc==2);
 if(!strcmp(argv[1],"missing")){retcode=-ENOENT;value=0;ret=fe_chip_name_config(&d,&p);assert(ret==-ENOENT && !d.chip_name);}
 else if(!strcmp(argv[1],"invalid")){value="bad-device";ret=fe_chip_name_config(&d,&p);assert(ret==-ENODEV && !d.chip_name);}
 else {value=argv[1];ret=fe_chip_name_config(&d,&p);assert(!ret);
  if(!strcmp(value,"mediatek,mt7621-eth"))assert(d.chip_name==MT7621_FE);
  else if(!strcmp(value,"mediatek,mt7623-eth"))assert(d.chip_name==MT7623_FE);
  else if(!strcmp(value,"mediatek,leopard-eth"))assert(d.chip_name==LEOPARD_FE);
  else abort();}
 return 0;}
'''

class RaethK2pThreadScopeTests(unittest.TestCase):
 def test_target_k2p_dts_and_only_thread_creation_conditions(self):
  text=SOURCE.read_text();op=function(text,'ei_open');chip=function(text,'fe_chip_name_config');probe=function(text,'rather_probe')
  dts=(K/'arch/mips/boot/dts/ralink/k2p.dts').read_text();dtsi=(K/'arch/mips/boot/dts/ralink/mt7621.dtsi').read_text()
  cfg=(ROOT/'trunk/configs/boards/K2P/kernel-4.4.x.config').read_text()
  self.assertIn('CONFIG_RALINK_BUILTIN_DTB_NAME="k2p"',cfg);self.assertIn('#include "mt7621.dtsi"',dts)
  self.assertRegex(dtsi,r'raeth:\s*raeth@1e100000\s*\{\s*compatible\s*=\s*"mediatek,mt7621-eth"')
  self.assertIn('!strcasecmp(pm, "mediatek,mt7621-eth")',chip);self.assertIn('ei_local->chip_name = MT7621_FE;',chip)
  self.assertEqual(text.count('kthread_create(fe_reset_thread,'),1);self.assertEqual(text.count('kthread_create(phy_polling_thread,'),1)
  self.assertRegex(op,r'if\s*\(\(ei_local->chip_name == MT7623_FE\)\s*&&\s*\(ei_local->features & FE_HW_LRO\)\)\s*\{\s*ei_local->kreset_task\s*=\s*kthread_create\(fe_reset_thread,')
  self.assertRegex(op,r'if\s*\(ei_local->chip_name == LEOPARD_FE\)\s*\{[\s\S]*?ei_local->kphy_poll_task\s*=\s*kthread_create\(phy_polling_thread,')
  self.assertIn('ret = fe_chip_name_config(ei_local, pdev);\n\tif (ret)\n\t\tgoto err_free_dev;',probe)
  self.assertLess(probe.index('ret = fe_chip_name_config('),probe.index('raeth_arch_setting('))
 def test_chip_lookup_errors_are_propagated(self):
  code=PREFIX+function(SOURCE.read_text(),'fe_chip_name_config')+SUFFIX
  with tempfile.TemporaryDirectory(prefix='k2p-raeth-chip-') as tmp:
   src=Path(tmp)/'chip.c';src.write_text(code);exe=Path(tmp)/'chip'
   for compiler,flags in [(shutil.which('gcc-16'),[]),(shutil.which('clang'),['-fsanitize=address,undefined','-fno-sanitize-recover=all'])]:
    self.assertTrue(compiler);subprocess.run([compiler,'-std=gnu11','-O1','-Wall','-Wextra','-Werror',*flags,str(src),'-o',str(exe)],check=True,timeout=60)
    for case in ('missing','invalid','mediatek,mt7621-eth','mediatek,mt7623-eth','mediatek,leopard-eth'):
     subprocess.run([str(exe),case],check=True,timeout=10)
   mutant=code.replace('\tif (ret)\n\t\treturn ret;','\t/* removed error check */',1)
   self.assertNotEqual(mutant,code);src.write_text(mutant)
   subprocess.run([shutil.which('clang'),'-std=gnu11','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(exe)],check=True,timeout=60)
   result=subprocess.run([str(exe),'missing'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
   self.assertNotEqual(result.returncode,0)
if __name__=='__main__':unittest.main()
