"""Exact source call blocks plus whole QA/status wrappers; no vendor radio runs."""
import hashlib,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
PATHS={'ate':BASE+'ate/mt_mac/mt_testmode.c','qa':BASE+'ate/testmode_ioctl.c',
       'mcu':BASE+'embedded/mcu/andes_mt.c'}
NAMES={'ate':('MtATE_DPD_Cal_Store_Proc','MtATE_DCOC_Cal_Store_Proc'),
       'qa':('HQA_WriteBufferDone',),
       'mcu':('ExtEventPreCalStoreProc','PreCalTxLPFStoreProcHandler','PreCalTxIQStoreProcHandler',
              'PreCalTxDCStoreProcHandler','PreCalRxFIStoreProcHandler','PreCalRxFDStoreProcHandler')}


def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    m=list(re.finditer(r'^(?:static\s+)?(?:INT32|INT|NTSTATUS)\s+'+name+r'\s*\([^;{}]*\)\s*\{',masked,re.M))
    if len(m)!=1:raise ValueError(name)
    start=m[0].start();opening=text.index('{',start);depth=0
    for item in re.finditer(tokens+r'|[{}]',text[opening:]):
        if item.group()=='{':depth+=1
        elif item.group()=='}':
            depth-=1
            if not depth:return text[start:opening+item.end()]
    raise ValueError(name)


def call_blocks(body,callee):
    answer=[]
    for m in re.finditer(r'(?m)^[ \t]*(?:if\s*\(\s*!?\s*)?'+callee+r'\(',body):
        start=m.start()
        if body[start:m.end()].lstrip().startswith('if'):
            opening=body.index('{',m.end());depth=0
            for end in range(opening,len(body)):
                depth+=(body[end]=='{')-(body[end]=='}')
                if not depth:
                    answer.append(body[start:end+1]);break
        else:answer.append(body[start:body.index(';',m.end())+1])
    return answer


PREFIX=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define RF_LOCKDOWN 1
#define RTMP_FLASH_SUPPORT 1
#define PRECAL_RXFI 3
#define E2P_BIN_MODE 4
#define E2P_FLASH_MODE 2
#define E2P_EFUSE_MODE 1
#define E2P_EEPROM_MODE 3
#define fRTMP_ADAPTER_NIC_NOT_EXIST 1
#define RTMP_TEST_FLAG(p,f) ((void)(f),(p)->nic_gone)
#define TXDPD_PART1_LIMIT 2
#define TXDPD_SIZE 4
#define DPD_G20_SIZE 2
#define TXDPD_IMAGE1_SIZE 8
#define TXDPD_IMAGE2_SIZE 8
#define DPDPART1_OFFSET 16
#define DPDPART2_OFFSET 24
#define DCOC_OFFSET 32
#define K_ALL_SIZE 2
#define RXDCOC_SIZE 4
#define PRECALPART_OFFSET 48
#define PKTL_TRAN_TO_HOST(x) (x)
#define MTWF_LOG(a,b,c,args) do{if(0)printf args;}while(0)
typedef unsigned char UCHAR;
typedef UCHAR*PUCHAR;
typedef unsigned int UINT32;
typedef unsigned short UINT16;
typedef int INT,INT32,NTSTATUS;
typedef struct {int E2pAccessMode,PreCalWriteOffSet,fgQAEffuseWriteBack,nic_gone,bDPDReloaded,bDCOCReloaded;void*hdev_ctrl;struct{int e2pCurMode;}E2pCtrl;UCHAR*CalDPDAPart1Image,*CalDPDAPart2Image,*CalDCOCImage,*PreCalStoreBuffer;} RTMP_ADAPTER,*PRTMP_ADAPTER;
static int code,passed,cleanups,flags,rf_count=3,qa_status,qa_rf;
static UCHAR storage[128];
static UINT16 ram52;
static unsigned long get_dev_eeprom_offset(RTMP_ADAPTER*p){(void)p;return 0;}
static int RtmpFlashWriteChecked(void*c,UCHAR*b,unsigned long o,unsigned long n){(void)c;(void)b;(void)o;(void)n;return code;}
static int rtmp_ee_flash_write(RTMP_ADAPTER*p,unsigned long o,UINT16 v){(void)p;(void)o;if(!code)ram52=v;return code;}
static void rtmp_ee_bin_read16(RTMP_ADAPTER*p,unsigned long o,UINT16*v){(void)p;(void)o;*v=ram52;}
static void rtmp_ee_bin_write16(RTMP_ADAPTER*p,unsigned long o,UINT16 v){(void)p;(void)o;ram52=v;}
static int complete_bit(RTMP_ADAPTER*p,unsigned long o,UINT16 v){(void)p;(void)o;if(!code){ram52=v;flags++;}return code;}
#define RT28xx_EEPROM_READ16(p,o,v) ((v)=ram52)
#define RT28xx_EEPROM_WRITE16_CHECKED(p,o,v) complete_bit(p,o,v)
static INT rtmp_cal_write_to_bin(RTMP_ADAPTER*p,UCHAR*b,unsigned long o,unsigned long n){(void)p;(void)b;(void)o;(void)n;return code;}
static INT rtmp_cal_load_from_bin(RTMP_ADAPTER*p,UCHAR*b,unsigned long o,unsigned long n){(void)p;(void)b;(void)o;(void)n;return code;}
static INT rtmp_ee_write_to_bin(RTMP_ADAPTER*p){(void)p;return code?FALSE:TRUE;}
'''


class WifiCalConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='wifi-cal-consumers-');cls.base=Path(cls.temp.name)
        cls.current={n:function((ROOT/p).read_text(),n) for key,p in PATHS.items() for n in NAMES[key]}
        cls.old={}
        for n,wanted in FIXTURE_SHA256.items():
            raw=(ROOT/'tests/fixtures/wifi-cal-io'/('3a-'+n+'.c')).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=wanted:raise AssertionError('Changed fixed3a consumer '+n)
            cls.old[n]=raw.decode()

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def compile_run(self,source,name):
        p=self.base/(name+'.c');b=p.with_suffix('');p.write_text(source)
        outputs=[]
        for compiler,extra in ((shutil.which('clang'),['-fsanitize=address,undefined','-fno-sanitize-recover=undefined']),
                               (shutil.which('gcc-16') or shutil.which('gcc'),[])):
            self.assertIsNotNone(compiler,'Required native C compiler missing')
            r=subprocess.run([compiler,'-std=gnu89','-O1','-Wall','-Wextra','-Werror',
                              '-Wno-unused-function','-Wno-unused-parameter','-Wno-unused-variable',
                              *extra,str(p),'-o',str(b)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([str(b)],capture_output=True,text=True,timeout=5)
            self.assertEqual((r.returncode,r.stderr),(0,''),r.stderr);outputs.append(r.stdout)
        self.assertEqual(outputs[0],outputs[1]);return outputs[0]

    def test_eight_ate_io_call_blocks_fail_before_success_continuation_and_keep_exit_cleanup(self):
        total=0
        for name in NAMES['ate']:
            flag='DPDPassOrFail' if 'DPD_' in name else 'DCOCPassOrFail'
            for callee,count in [('rtmp_cal_write_to_bin',2 if 'DPD_' in name else 1),
                                 ('rtmp_ee_write_to_bin',1),
                                 ('rtmp_cal_load_from_bin',2 if 'DPD_' in name else 1)]:
                old=call_blocks(self.old[name],callee);new=call_blocks(self.current[name],callee)
                self.assertEqual((len(old),len(new)),(count,count))
                for index,(previous,current) in enumerate(zip(old,new)):
                    total+=1
                    for profile,block,wanted in [('current',current,'1 1 1\n0 0 1\n0 0 1\n'),
                                                  ('baseline',previous,'1 1 1\n1 1 1\n1 1 1\n')]:
                        source=PREFIX+'\nstatic int invoke(void){RTMP_ADAPTER a,*pAd=&a;int '+flag+'=TRUE;memset(&a,0,sizeof(a));a.CalDPDAPart1Image=a.CalDPDAPart2Image=a.CalDCOCImage=storage;\n'+block+'\npassed++;goto exit;\nexit:\ncleanups++;return '+flag+';}\n'
                        source+='int main(void){int i,r,values[3]={0,1,-5};for(i=0;i<3;i++){code=values[i];passed=cleanups=0;r=invoke();printf("%d %d %d\\n",r,passed,cleanups);}return 0;}\n'
                        with self.subTest(function=name,callee=callee,index=index,profile=profile):
                            self.assertEqual(self.compile_run(source,name+callee+str(index)+profile),wanted)
            self.assertTrue(self.current[name].rstrip().endswith('return '+flag+';\n}'))
        self.assertEqual(total,8)

    def test_five_checked_flash_call_blocks_fail_before_success_continuation(self):
        total=0
        for name in NAMES['ate']:
            body=self.current[name];flag='DPDPassOrFail'if 'DPD_'in name else'DCOCPassOrFail'
            for callee,count in [('RtmpFlashWriteChecked',2 if 'DPD_'in name else 1),('rtmp_ee_flash_write',1)]:
                calls=list(re.finditer(r'\b'+callee+r'\(',body));self.assertEqual(len(calls),count)
                for index,call in enumerate(calls):
                    start=list(re.finditer(r'(?m)^[ \t]*if \(',body[:call.start()]))[-1].start()
                    opening=body.index('{',call.end());depth=0
                    for end in range(opening,len(body)):
                        depth+=(body[end]=='{')-(body[end]=='}')
                        if not depth:break
                    block=body[start:end+1];total+=1
                    self.assertIn('E2P_FLASH_MODE &&',block)
                    source=PREFIX+'\nstatic int invoke(void){RTMP_ADAPTER a,*pAd=&a;UINT16 doCal1=0x1f;int '+flag+'=TRUE;memset(&a,0,sizeof(a));a.E2pAccessMode=2;a.CalDPDAPart1Image=a.CalDPDAPart2Image=a.CalDCOCImage=storage;\n'+block+'\npassed++;goto exit;\nexit: cleanups++;return '+flag+';}\n'
                    source+='int main(void){int i,r,values[3]={0,1,-5};for(i=0;i<3;i++){code=values[i];passed=cleanups=0;r=invoke();printf("%d %d %d\\n",r,passed,cleanups);}return 0;}'
                    self.assertEqual(self.compile_run(source,'flash-'+name+callee+str(index)),'1 1 1\n0 0 1\n0 0 1\n')
        self.assertEqual(total,5)

    def test_ate_failure_exit_clears_ram_consumers_without_repeating_flash_io(self):
        for name in NAMES['ate']:
            body=self.current[name];flag='DPDPassOrFail'if 'DPD_'in name else'DCOCPassOrFail'
            field='bDPDReloaded'if 'DPD_'in name else'bDCOCReloaded'
            start=body.index('\tif (!'+flag+')',body.index('\nexit:'));opening=body.index('{',start);depth=0
            for end in range(opening,len(body)):
                depth+=(body[end]=='{')-(body[end]=='}')
                if not depth:break
            block=body[start:end+1]
            self.assertNotIn('RtmpFlashWrite',block);self.assertNotIn('rtmp_ee_flash_write',block)
            source=PREFIX+'\nstatic int invoke(int ok){RTMP_ADAPTER a,*pAd=&a;UINT16 doCal1=0;int '+flag+'=ok;memset(&a,0,sizeof(a));a.'+field+'=TRUE;\n'+block+'\nreturn a.'+field+';}\n'
            source+='int main(void){int ok,r;for(ok=0;ok<2;ok++){ram52=0xffff;r=invoke(ok);printf("%d %u\\n",r,(unsigned)ram52);}return 0;}'
            expected='0 '+str(0xffff & ~(0x11 if 'DPD_'in name else 2))+'\n1 65535\n'
            self.assertEqual(self.compile_run(source,'exit-'+name),expected)

    def test_whole_qa_handler_reports_boolean_failure_and_releases_rf_write_state(self):
        prefix=PREFIX+r'''
typedef struct {int unused;} RTMP_IOCTL_INPUT_STRUCT;
struct _HQA_CMD_FRAME {UCHAR Data[4];};
static int Set_EepromBufferWriteBack_Proc(RTMP_ADAPTER*p,char*s){(void)p;(void)s;return code?FALSE:TRUE;}
static void ResponseToQA(struct _HQA_CMD_FRAME*q,RTMP_IOCTL_INPUT_STRUCT*w,int size,int r){(void)q;(void)w;(void)size;qa_status=r;}
'''
        main=r'''
int main(void){RTMP_ADAPTER a;RTMP_IOCTL_INPUT_STRUCT w;struct _HQA_CMD_FRAME q;UINT32 values[5]={1,2,3,4,9};int i,r;
 memset(&a,0,sizeof(a));
 for(code=0;code<2;code++)for(i=0;i<5;i++){memcpy(q.Data,&values[i],4);r=HQA_WriteBufferDone(&a,&w,&q);qa_rf=a.fgQAEffuseWriteBack;printf("%d %d %d\n",r,qa_status,qa_rf);}
 return 0;
}'''
        expected='0 0 0\n'*4+'1 1 0\n'+'1 1 0\n'*5
        for profile,body,wanted in [('current',self.current['HQA_WriteBufferDone'],expected),
                                    ('baseline',self.old['HQA_WriteBufferDone'],'0 0 0\n'*10)]:
            self.assertEqual(self.compile_run(prefix+body+main,'qa-'+profile),wanted)

    def test_actual_event_persist_block_cleans_failed_batch_before_completion_stamp(self):
        body=self.current['ExtEventPreCalStoreProc']
        start=body.index('\tif (EventId == PRECAL_RXFI) {')
        tail=body[start:body.rfind('}')]
        source=PREFIX+'\nstatic RTMP_ADAPTER a;\nstatic int invoke(void){RTMP_ADAPTER*pAd=&a;UINT32 EventId=PRECAL_RXFI,offset=16;UINT16 DoPreCal=0;memset(&a,0,sizeof(a));a.E2pAccessMode=4;a.PreCalStoreBuffer=storage;a.PreCalWriteOffSet=16;\n'+tail+'\n}\n'
        source+='int main(void){int i,r,values[3]={0,1,-5};for(i=0;i<3;i++){code=values[i];flags=0;r=invoke();printf("%d %d %d\\n",r,flags,a.PreCalWriteOffSet);}return 0;}\n'
        self.assertEqual(self.compile_run(source,'event-current'),'1 1 0\n0 0 0\n0 0 0\n')
        self.assertLess(body.index('!pAd->PreCalStoreBuffer'),body.index('requested = pAd->ChGrpMap'))
        old=self.old['ExtEventPreCalStoreProc'];start=old.index('\t\t\tif (pAd->E2pAccessMode == E2P_BIN_MODE)')
        end=old.index('/* Raise DoPreCal bits */',start)
        source=PREFIX+'\nstatic int invoke(void){RTMP_ADAPTER a,*pAd=&a;UINT32 TotalSize=16;memset(&a,0,sizeof(a));a.E2pAccessMode=4;a.PreCalStoreBuffer=storage;\n'+old[start:end]+'\nflags++;return TRUE;}\n'
        source+='int main(void){int i,r,values[3]={0,1,-5};for(i=0;i<3;i++){code=values[i];flags=0;r=invoke();printf("%d %d\\n",r,flags);}return 0;}\n'
        self.assertEqual(self.compile_run(source,'event-baseline'),'1 1\n'*3)

    def test_ate_rejects_unavailable_calibration_spans_before_zeroing_or_stopping_radio(self):
        dpd=self.current['MtATE_DPD_Cal_Store_Proc']
        start=dpd.index('\tif ((kABand && !pAd->CalDPDAPart1Image)')
        end=dpd.index('\t/* Stop TX RX MAC */',start)
        guard=dpd[start:end]
        for profile,block in [('current',guard),('baseline','')]:
            source=PREFIX+'\nstatic int invoke(int req,int present){RTMP_ADAPTER a,*pAd=&a;int kABand=req&1,kGBand=req&2;memset(&a,0,sizeof(a));a.CalDPDAPart1Image=(present&1)?storage:NULL;a.CalDPDAPart2Image=(present&2)?storage:NULL;\n'+block+'\n(void)kABand;(void)kGBand;return TRUE;}\nint main(void){int r,p;for(r=1;r<=3;r++)for(p=0;p<4;p++)printf("%d\\n",invoke(r,p));return 0;}'
            wanted=''.join(str(int((p&r)==r)if profile=='current'else 1)+'\n'for r in range(1,4)for p in range(4))
            self.assertEqual(self.compile_run(source,'dpd-span-'+profile),wanted)
        dcoc=self.current['MtATE_DCOC_Cal_Store_Proc']
        start=dcoc.index('\tif (!pAd->CalDCOCImage)');end=dcoc.index('\tRTMPZeroMemory',start)
        for profile,block,wanted in [('current',dcoc[start:end],'0\n1\n'),('baseline','','1\n1\n')]:
            source=PREFIX+'\nstatic int invoke(int present){RTMP_ADAPTER a,*pAd=&a;memset(&a,0,sizeof(a));a.CalDCOCImage=present?storage:NULL;\n'+block+'\nreturn TRUE;}\nint main(void){printf("%d\\n",invoke(0));printf("%d\\n",invoke(1));return 0;}'
            self.assertEqual(self.compile_run(source,'dcoc-span-'+profile),wanted)

    def test_ate_rejects_removed_or_mixed_modes_before_any_backend_continuation(self):
        expected='1 1\n1 1\n0 0\n0 0\n0 0\n0 0\n'
        for name in NAMES['ate']:
            body=self.current[name]
            start=body.index('\tif (RTMP_TEST_FLAG(pAd, fRTMP_ADAPTER_NIC_NOT_EXIST)')
            opening=body.index('{',start);depth=0
            for end in range(opening,len(body)):
                depth+=(body[end]=='{')-(body[end]=='}')
                if not depth:break
            guard=body[start:end+1]
            source=PREFIX+'\nstatic int invoke(int profile,int callbacks,int removed){RTMP_ADAPTER a,*pAd=&a;memset(&a,0,sizeof(a));a.E2pAccessMode=profile;a.E2pCtrl.e2pCurMode=callbacks;a.nic_gone=removed;\n'+guard+'\npassed++;return TRUE;}\n'
            source+='int main(void){int i,r;int cases[6][3]={{2,2,0},{4,4,0},{2,4,0},{4,2,0},{2,2,1},{4,0,0}};for(i=0;i<6;i++){passed=0;r=invoke(cases[i][0],cases[i][1],cases[i][2]);printf("%d %d\\n",r,passed);}return 0;}\n'
            self.assertEqual(self.compile_run(source,'mode-'+name),expected)

    def test_five_whole_status_wrappers_convert_event_boolean_and_forward_length(self):
        common=PREFIX+r'''
typedef struct {UCHAR*buffer;UINT32 bufferlength;} queue_item,*PCmdQElmt;
#define PRECAL_TXLPF 0
#define PRECAL_TXIQ 1
#define PRECAL_TXDC 2
#define PRECAL_RXFD 4
static int lengths_ok;
'''
        for profile,functions,wanted in [('current',self.current,'1 1 1 1 1 5 5\n0 0 0 0 0 5 5\n'),
                                         ('baseline',self.old,'0 0 0 0 0 5 0\n'*2)]:
            stub='static INT ExtEventPreCalStoreProc(RTMP_ADAPTER*p,UINT32 id,UCHAR*buf'+(',UINT32 length' if profile=='current'else '')+'){(void)p;(void)id;(void)buf;passed++;'+('lengths_ok+=length==37;'if profile=='current'else '')+'return code;}\n'
            main='int main(void){RTMP_ADAPTER a;queue_item q={0};q.bufferlength=37;for(code=0;code<2;code++){passed=lengths_ok=0;'
            for name in NAMES['mcu'][1:]:main+='printf("%d ",(int)'+name+'(&a,&q));'
            main+='printf("%d %d\\n",passed,lengths_ok);}return 0;}'
            body='\n'.join(functions[n]for n in NAMES['mcu'][1:])
            self.assertEqual(self.compile_run(common+stub+body+main,'handlers-'+profile),wanted)


FIXTURE_SHA256 = {'MtATE_DPD_Cal_Store_Proc': '12b13731688a9d43a8868aa7854163c237b323e8a48eb99e403a2494694623aa', 'MtATE_DCOC_Cal_Store_Proc': '3a66e61ffa56c5b85edb592a56888d364fef54df94b9a20a08d2e0d324239aee', 'HQA_WriteBufferDone': '13cf5d75af2eae5a58963ce8f0dd000c92b5db25b734f72e931fae580a06469e', 'ExtEventPreCalStoreProc': '2f765d349ea0a6369f9adb5b5e82de0237ee6744f2cf29bc0c3ad7b46cf8dd28', 'PreCalTxLPFStoreProcHandler': 'a7e3164ff1e0d74668847a338e8c849d399b580fa88cdd2ba44806b0fa140d70', 'PreCalTxIQStoreProcHandler': 'ad42ddb97710b6ceac4f411b83ced802afaa86417034038229c6c4fa8e71967e', 'PreCalTxDCStoreProcHandler': '339a5554bccfa5dcc6a6dcdd273e7a6d5ffe01ba734d4141b28d22112decf38b', 'PreCalRxFIStoreProcHandler': '765ac949ceeb4bd83d74a2cc9d74d6db1dd7f2b18fe9fd995158d2e03a003b09', 'PreCalRxFDStoreProcHandler': '1c91c931236678ee8e2697cb809326219f152b7f2a161b76b112aa95e6bf571b'}

if __name__=='__main__':unittest.main()
