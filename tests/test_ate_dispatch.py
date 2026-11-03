"""Source-bound calibration dispatch tail of SetATE with inert callbacks.

The complete function is hashed as metadata; only the selected tail executes.
kstrtou32 is a trusted checked-primitive seam, not a kernel-parser test.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from wifi_factory_harness import function

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/ate/ate_agent.c'
START='#ifdef PRE_CAL_TRX_SET1_SUPPORT\n\telse if'
FLAGS=['-std=gnu89','-Os','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-Wno-sign-compare']
PREFIX=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#define TRUE 1
#define FALSE 0
#define PRE_CAL_TRX_SET1_SUPPORT 1
#define PRE_CAL_TRX_SET2_SUPPORT 1
#define CAL_BIN_FILE_SUPPORT 1
#define MT7615 1
#define ATE_START (1U<<0)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define MTWF_LOG(a,b,c,args) do{if(0)printf args;}while(0)
typedef uint8_t UINT8;
typedef uint32_t UINT32;
typedef int32_t INT32;
typedef int INT;
typedef char RTMP_STRING;
typedef struct _RTMP_ADAPTER RTMP_ADAPTER,*PRTMP_ADAPTER;
struct _ATE_OPERATION {
 INT(*RxSelfTest)(RTMP_ADAPTER*,RTMP_STRING*);
 INT(*TxDPDTest)(RTMP_ADAPTER*,RTMP_STRING*);
 INT(*PreCalTest)(RTMP_ADAPTER*,UINT8,UINT32);
 INT(*PATrim)(RTMP_ADAPTER*,UINT32*);
};
struct _ATE_CTRL {UINT32 Mode;struct _ATE_OPERATION*ATEOp;};
struct _RTMP_ADAPTER {struct _ATE_CTRL ATECtrl;int mt7615;};
#define IS_MT7615(p) ((p)->mt7615)
static int calls,kind,argument,callback_result,last_ret=-99;
static UINT32 group,trim[4];
static INT rx(RTMP_ADAPTER*p,RTMP_STRING*s){calls++;kind=1;argument=atoi(s);return callback_result;}
static INT dpd(RTMP_ADAPTER*p,RTMP_STRING*s){calls++;kind=2;argument=atoi(s);return callback_result;}
static INT precal(RTMP_ADAPTER*p,UINT8 cal,UINT32 g){calls++;kind=3;argument=cal;group=g;return callback_result;}
static INT patrim(RTMP_ADAPTER*p,UINT32*d){int i;calls++;kind=4;for(i=0;i<4;i++)trim[i]=d[i];return callback_result;}
static int kstrtou32(const char*s,unsigned int base,UINT32*out){
 char*end;unsigned long long value;
 if(*s=='-'||isspace((unsigned char)*s))return -EINVAL;
 errno=0;value=strtoull(s,&end,base);
 if(end==s||errno==ERANGE||value>UINT32_MAX)return -ERANGE;
 if(*end&&!(end[0]=='\n'&&!end[1]))return -EINVAL;
 *out=(UINT32)value;return 0;
}
static char*rstrtok(char*s,const char*d){static char*saved;return strtok_r(s,d,&saved);}
'''
TAIL=r'''
int main(int argc,char**argv){
 RTMP_ADAPTER a;struct _ATE_OPERATION op;char*command;int result;
 if(argc!=6)return 90;
 memset(&a,0,sizeof(a));memset(&op,0,sizeof(op));callback_result=atoi(argv[2]);
 if(atoi(argv[3])==1){op.RxSelfTest=rx;op.TxDPDTest=dpd;op.PreCalTest=precal;op.PATrim=patrim;}
 a.ATECtrl.ATEOp=atoi(argv[3])==2?NULL:&op;a.ATECtrl.Mode=atoi(argv[4])?ATE_START:0;a.mt7615=atoi(argv[5]);
 command=malloc(strlen(argv[1])+1);if(!command)return 91;strcpy(command,argv[1]);
 result=dispatch(&a,command);
 printf("{\"result\":%d,\"ret\":%d,\"calls\":%d,\"kind\":%d,\"argument\":%d,\"group\":%u,\"trim\":[%u,%u,%u,%u]}\n",result,last_ret,calls,kind,argument,group,trim[0],trim[1],trim[2],trim[3]);
 free(command);return 0;
}
'''


def projected_source():
    body=function(SOURCE.read_text(),'SetATE')
    if body.count(START)!=1:raise ValueError('Calibration dispatch extraction marker changed')
    section=body[body.index(START):body.rfind('}')]
    if section.count('\n\tif (!Ret)')!=1 or section.count('err1:\n')!=1:raise ValueError('SetATE return conversion changed')
    observed=section.replace('\n\tif (!Ret)','\n\tlast_ret=Ret;\n\tif (!Ret)').replace('err1:\n','err1:\n\tlast_ret=Ret;\n')
    wrapper='static INT dispatch(PRTMP_ADAPTER pAd,RTMP_STRING*Arg){\nstruct _ATE_CTRL*ATECtrl=&pAd->ATECtrl;struct _ATE_OPERATION*ATEOp=ATECtrl->ATEOp;INT32 Ret=0;UINT32 mode=ATECtrl->Mode;\nif(0)goto err1;\nif(0){}\n'
    metadata={'function':'SetATE','source':str(SOURCE),'execution':'calibration-dispatch-tail',
              'whole_body_sha256':hashlib.sha256(body.encode()).hexdigest(),
              'executed_section_sha256':hashlib.sha256(section.encode()).hexdigest()}
    return PREFIX+wrapper+observed+'\n}\n'+TAIL,metadata,body,section


class AteDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='k2p-ate-dispatch-');cls.directory=Path(cls.temp.name)
        cls.code,cls.metadata,cls.body,cls.section=projected_source()
        cls.binary=cls.compile('clang',shutil.which('clang'),sanitize=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    @classmethod
    def compile(cls,name,compiler,sanitize=False):
        if not compiler:raise AssertionError('Host compiler required')
        path=cls.directory/(name+'.c');binary=cls.directory/name;path.write_text(cls.code);flags=list(FLAGS)
        if sanitize:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        result=subprocess.run([compiler,*flags,str(path),'-o',str(binary)],capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
        return binary
    def row(self,command,outcome=1,present=1,active=1,chip=1,binary=None):
        run=subprocess.run([str(binary or self.binary),command,str(outcome),str(present),str(active),str(chip)],capture_output=True,text=True,timeout=5)
        self.assertEqual((run.returncode,run.stderr),(0,''),run.stderr)
        return json.loads(run.stdout)

    def test_six_set1_callbacks_convert_bool_to_status(self):
        for command,kind,argument in [('RX2GSELFTEST',1,0),('RX5GSELFTEST',1,1),('RXSELFTEST',1,2),
                                      ('TX2GDPD',2,0),('TX5GDPD',2,1),('TXDPD',2,2)]:
            for outcome in (0,1):
                with self.subTest(command=command,outcome=outcome):
                    row=self.row(command,outcome)
                    self.assertEqual([row[k]for k in('result','ret','calls','kind','argument')],
                                     [outcome,1-outcome,1,kind,argument])

    def test_precal_longest_prefix_separators_and_callback_status(self):
        for name,cal in [('PRECAL',0),('PRECALTX',1)]:
            for delimiter in ('_','=',':',' '):
                for outcome in (0,1):
                    with self.subTest(name=name,delimiter=delimiter,outcome=outcome):
                        row=self.row(name+delimiter+'1',outcome)
                        self.assertEqual([row[k]for k in('result','ret','calls','kind','argument','group')],
                                         [outcome,1-outcome,1,3,cal,1])

    def test_decimal_group_parsing_is_checked_without_truncation(self):
        for value in ('0','1','4294967295'):
            row=self.row('PRECAL_'+value,outcome=0)
            self.assertEqual((row['calls'],row['group'],row['result']),(1,int(value),0))
        for value in ('','-1','-0','+1',' 1','4294967296','9'*1024,'1x','1 ','1\nx','0x1'):
            with self.subTest(value=value[:30]):
                row=self.row('PRECAL_'+value)
                self.assertEqual((row['result'],row['calls']),(0,0))

    def test_precal_bare_and_malformed_prefixes_decline(self):
        for command in ('PRECAL','PRECALTX','PRECALX_1','PRECALTXJUNK_1','PRECAL1','PRECALTX1'):
            with self.subTest(command=command):
                row=self.row(command)
                self.assertEqual((row['result'],row['calls']),(0,0))
        for command in ('Z','P','PATR','OTHER_COMMAND'):
            with self.subTest(command=command):self.assertEqual(self.row(command)['calls'],0)

    def test_patrim_accepts_exactly_four_checked_u32_values(self):
        for delimiter in ('_','=',':',' '):
            for outcome in (0,1):
                with self.subTest(delimiter=delimiter,outcome=outcome):
                    row=self.row('PATRIM'+delimiter+'0001-02-fFfF-ABCD',outcome)
                    self.assertEqual([row[k]for k in('result','ret','calls','kind')],[outcome,1-outcome,1,4])
                    self.assertEqual(row['trim'],[1,2,65535,43981])
        row=self.row('PATRIM_0xFFFFFFFF-+2-0000-80000000')
        self.assertEqual((row['result'],row['calls'],row['trim']),(1,1,[4294967295,2,0,2147483648]))

    def test_patrim_rejects_wrong_counts_overflow_and_empty_values(self):
        for payload in ('','1','1-2-3','1-2-3-4-5','-1-2-3-4','1--2-3-4','1-2-3-4-',
                        '100000000-2-3-4','fffffffff-2-3-4','g-2-3-4','1-2-3-4x',
                        ' 1-2-3-4','1-2-3-4 '+'a'*2048,'-'.join(['1']*100)):
            with self.subTest(payload=payload[:35]):
                row=self.row('PATRIM_'+payload)
                self.assertEqual((row['result'],row['calls']),(0,0))
        self.assertEqual(self.row('PATRIM_1-2-3-4',chip=0)['result'],0)

    def test_null_callbacks_null_operations_and_inactive_mode_never_call(self):
        for command in ('RXSELFTEST','TXDPD','PRECAL_1','PRECALTX_1','PATRIM_1-2-3-4'):
            for present in (0,2):
                with self.subTest(command=command,present=present):
                    row=self.row(command,present=present)
                    self.assertEqual((row['result'],row['calls']),(0,0))
            row=self.row(command,active=0)
            self.assertEqual((row['result'],row['calls']),(1,0))

    def test_gnu_strict_projection_and_source_metadata(self):
        compiler=shutil.which('gcc-16')or shutil.which('gcc')
        self.assertIsNotNone(compiler)
        probe=subprocess.run([compiler,'-dM','-E','-x','c','-'],input='',capture_output=True,text=True,timeout=10)
        self.assertEqual(probe.returncode,0);self.assertIn('#define __GNUC__ ',probe.stdout);self.assertNotIn('#define __clang__ ',probe.stdout)
        binary=self.compile('gnu',compiler)
        for command in ('RXSELFTEST','TXDPD','PRECAL_1','PRECALTX=0','PRECAL_4294967295',
                        'PRECAL_4294967296','PRECALTXbad','PATRIM_1-2-3-4','PATRIM_1-2-3-4-5'):
            for outcome in (0,1):
                with self.subTest(command=command,outcome=outcome):
                    self.assertEqual(self.row(command,outcome,binary=binary),self.row(command,outcome))
        self.assertEqual(self.metadata['function'],'SetATE')
        self.assertEqual(self.metadata['execution'],'calibration-dispatch-tail')
        self.assertEqual(self.metadata['whole_body_sha256'],hashlib.sha256(self.body.encode()).hexdigest())
        self.assertIn(self.section,self.body);self.assertNotIn(self.body,self.code)
        kernel_header=ROOT/'trunk/linux-4.4.x/include/linux/kernel.h'
        ate_header=ROOT/'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/ate/include/ate.h'
        self.assertRegex(kernel_header.read_text(),r'kstrtou32\([^)]*\)\s*\{\s*return kstrtouint\(s, base, res\);')
        self.assertRegex(ate_header.read_text(),r'#define\s+fATE_IDLE\s+\(1 << 0\)')


if __name__=='__main__':unittest.main()
