"""Whole checked DMA APIs, inert IO; failed-stop legacy cleanup stays visible."""
import hashlib
import re
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'dma':BASE+'embedded/common/cmm_mac_pci.c','asic':BASE+'hw_ctrl/cmm_asic.c',
 'andes':BASE+'embedded/mcu/andes_mt.c','chip':BASE+'hw_ctrl/cmm_chip.c',
 'init':BASE+'embedded/common/rtmp_init.c','ready':BASE+'embedded/common/rtmp_init_inf.c',
 'hw':BASE+'hw_ctrl/hw_init.c','fwdl':BASE+'mcu/fwdl.c',
 'flags':BASE+'embedded/include/rtmp_def.h','os_header':BASE+'include/os/rt_linux.h',
 'chip_header':BASE+'include/hw_ctrl/cmm_chip.h','dma_header':BASE+'embedded/include/rtmp_chip.h',
 'asic_mt':BASE+'hw_ctrl/cmm_asic_mt_dmac.c','chip_hw':BASE+'chips/mt7615.c',
 'chip_cr':BASE+'include/chip/mt7615_cr.h','hif_header':BASE+'include/hif/mt_hif_pci.h',
 'mcu':BASE+'embedded/mcu/mcu.c','chip_mt':BASE+'hw_ctrl/cmm_chip_mt.c'}
FUNCTION_SOURCES={'hif_wait_WPDMA_idle':'chip_hw','MtAsicWaitPDMAIdle':'asic_mt',
 'AsicWaitPDMAIdle':'asic','AsicResetWPDMA':'asic','RT28XXDMAEnable':'dma','RT28XXDMAStop':'dma',
 'RT28XXDMAReset':'dma','AndesMTPciFwInit':'andes','chip_fw_init':'chip',
 'WfMcuSysInit':'init','RTMPEnableRxTx':'init','mt_sys_ready':'ready',
 'NICRestartFirmware':'fwdl','WfHifSysExit':'init','WfSysPosExit':'hw'}
SOURCE_ONLY_FUNCTION_SOURCES={'MCUSysPrepare':'mcu','MCUSysInit':'mcu',
 'ChipOpsMCUHook':'mcu','PDMAResetAndRecovery':'chip_mt','MtAsicResetWPDMA':'asic_mt',
 'hif_reset_WPDMA':'chip_hw','hif_set_WPDMA':'chip_hw','RTMPResetTxRxRingMemory':'dma'}
BODY_ORDER=('hif_wait_WPDMA_idle','MtAsicWaitPDMAIdle','AsicWaitPDMAIdle','AsicResetWPDMA','RT28XXDMAEnable','RT28XXDMAStop','RT28XXDMAReset',
 'AndesMTPciFwInit','chip_fw_init','WfMcuSysInit','RTMPEnableRxTx','mt_sys_ready',
 'NICRestartFirmware','WfHifSysExit','WfSysPosExit')
CASE_NAMES=('enable-idle','enable-busy','enable-nic-missing','enable-set-failure',
 'stop-idle','stop-busy','stop-set-failure','reset-idle','reset-busy',
 'reset-set-failure','reset-callback-failure','asic-non-mt','fw-init-idle',
 'fw-init-busy','fw-init-set-failure','fw-init-no-callback','fw-init-non-mt',
 'ready-idle','ready-busy','ready-set-failure','rx-filter-idle','rx-filter-busy',
 'restart-success','restart-failure','teardown-idle','teardown-busy-residual',
 'teardown-reset-failure-residual','enable-busy-to-idle','enable-nic-vanishes')
FIELDS=('result','flags','irq','mcu_inits','ring_live','token_live','unsafe_frees',
 'unsupported','event_count','events...','poll_reads','poll_delays')
EXPECTED_ROWS={'enable-idle': [1, 0, 0, 0, 1, 1, 0, 0, 2, 1, 2, 1, 0], 'enable-busy': [0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 201, 201], 'enable-nic-missing': [0, 256, 0, 0, 1, 1, 0, 0, 0, 0, 0], 'enable-set-failure': [0, 0, 0, 0, 1, 1, 0, 0, 2, 1, 2, 1, 0], 'stop-idle': [1, 0, 0, 0, 1, 1, 0, 0, 2, 3, 1, 1, 0], 'stop-busy': [0, 0, 0, 0, 1, 1, 0, 0, 2, 3, 1, 201, 201], 'stop-set-failure': [0, 0, 0, 0, 1, 1, 0, 0, 1, 3, 0, 0], 'reset-idle': [1, 0, 0, 0, 1, 1, 0, 0, 3, 3, 1, 4, 1, 0], 'reset-busy': [0, 0, 0, 0, 1, 1, 0, 0, 2, 3, 1, 201, 201], 'reset-set-failure': [0, 0, 0, 0, 1, 1, 0, 0, 1, 3, 0, 0], 'reset-callback-failure': [0, 0, 0, 0, 1, 1, 0, 0, 3, 3, 1, 4, 1, 0], 'asic-non-mt': [0, 0, 0, 0, 1, 1, 0, 1, 0, 0, 0], 'fw-init-idle': [0, 285212672, 1, 1, 1, 1, 0, 0, 4, 7, 5, 1, 2, 1, 0], 'fw-init-busy': [1, 0, 0, 1, 1, 1, 0, 0, 4, 7, 5, 1, 6, 201, 201], 'fw-init-set-failure': [1, 0, 0, 1, 1, 1, 0, 0, 5, 7, 5, 1, 2, 6, 1, 0], 'fw-init-no-callback': [1, 0, 0, 1, 1, 1, 0, 0, 1, 7, 0, 0], 'fw-init-non-mt': [1, 0, 0, 1, 1, 1, 0, 0, 1, 7, 0, 0], 'ready-idle': [1, 268435456, 1, 0, 1, 1, 0, 0, 5, 5, 1, 2, 8, 9, 1, 0], 'ready-busy': [0, 0, 0, 0, 1, 1, 0, 0, 3, 5, 1, 6, 201, 201], 'ready-set-failure': [0, 0, 0, 0, 1, 1, 0, 0, 4, 5, 1, 2, 6, 1, 0], 'rx-filter-idle': [1, 0, 0, 0, 1, 1, 0, 0, 4, 1, 2, 8, 9, 1, 0], 'rx-filter-busy': [0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 201, 201], 'restart-success': [0, 0, 0, 0, 1, 1, 0, 0, 1, 10, 0, 0], 'restart-failure': [7, 0, 0, 0, 1, 1, 0, 0, 1, 10, 0, 0], 'teardown-idle': [0, 0, 0, 0, 0, 0, 0, 0, 8, 14, 15, 3, 1, 4, 11, 12, 13, 1, 0], 'teardown-busy-residual': [1, 0, 0, 0, 0, 0, 2, 0, 7, 14, 15, 3, 1, 11, 12, 13, 201, 201], 'teardown-reset-failure-residual': [1, 0, 0, 0, 0, 0, 0, 0, 8, 14, 15, 3, 1, 4, 11, 12, 13, 1, 0], 'enable-busy-to-idle': [1, 0, 0, 0, 1, 1, 0, 0, 2, 1, 2, 3, 2], 'enable-nic-vanishes': [0, 256, 0, 0, 1, 1, 0, 0, 1, 1, 1, 0]}
SOURCE_DECLARATIONS={
 r'^#define NDIS_STATUS_SUCCESS\s+0x[0-9a-fA-F]+\s*$':'os_header',
 r'^#define NDIS_STATUS_FAILURE\s+0x[0-9a-fA-F]+\s*$':'os_header',
 r'^#define fRTMP_ADAPTER_NIC_NOT_EXIST[^\n]*':'flags',
 r'^#define MT_HIF_BASE[^\n]*':'hif_header',
 r'^#define MT_WPDMA_GLO_CFG\s+[^\n]*':'hif_header',
 r'#ifdef RT_BIG_ENDIAN[\s\S]*?#endif /\* RT_BIG_ENDIAN \*/':'chip_cr',
 r'^#define fRTMP_ADAPTER_START_UP[^\n]*':'flags',
 r'^#define fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD[^\n]*':'flags',
 r'enum \{\s*PDMA_TX,\s*PDMA_RX,\s*PDMA_TX_RX,\s*\};':'dma_header'}
PREFIX=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef unsigned int UINT32;typedef void VOID,PKT_TOKEN_CB;typedef int INT,INT32,BOOLEAN,NDIS_STATUS;
#define TRUE 1
#define FALSE 0
#define MT_MAC
#define RESOURCE_PRE_ALLOC
#define HIF_MT 2
#define ASIC_MAC_TXRX_RXV 1
#define ASIC_MAC_TXRX 2
#define FWDL_STAGE_FW_NOT_DL 0
#define MTWF_LOG(...) ((void)0)
SOURCE_DEFINITIONS
struct _RTMP_ADAPTER;
struct _RTMP_CHIP_CAP {int WPDMABurstSIZE;};
struct _RTMP_CHIP_OP {NDIS_STATUS (*FwInit)(struct _RTMP_ADAPTER *pAd);
 BOOLEAN (*hif_wait_dma_idle)(struct _RTMP_ADAPTER *pAd,INT round,INT wait_us);};
struct MCU_CTRL {struct {int stage;} fwdl_ctrl;};
typedef struct _RTMP_ADAPTER {void *hdev_ctrl,*PktTokenCb;unsigned flags;
 struct MCU_CTRL MCUCtrl;struct {int bTXRX_RXV_ON;} CommonCfg;} RTMP_ADAPTER;
static struct _RTMP_CHIP_CAP cap;static struct _RTMP_CHIP_OP ops;
static int poll_reads,poll_delays,busy_before_idle,vanish_on_read;
static int events[64],count,idle=1,set_ok=1,reset_ok=1,mt=1,irq,mcu_inits;
static int ring_live=1,token_live=1,unsafe_frees,unsupported,restart_status;
static void event(int n){assert(count<64);events[count++]=n;}
static struct _RTMP_CHIP_CAP *hc_get_chip_cap(void *p){(void)p;return &cap;}
static struct _RTMP_CHIP_OP *hc_get_chip_ops(void *p){(void)p;return &ops;}
#define IS_HIF_TYPE(p,n) ((void)(p),(void)(n),mt)
#define RTMP_SET_FLAG(p,f) ((p)->flags|=(f))
#define RTMP_CLEAR_FLAG(p,f) ((p)->flags&=~(f))
#define RTMP_IRQ_ENABLE(p) ((void)(p),event(5),irq=1)
#define RTMP_ASIC_INTERRUPT_DISABLE(p) ((void)(p),event(6),irq=0)
#define MCU_CTRL_INIT(p) ((void)(p),event(7),mcu_inits++)
#define WLAN_HOOK_CALL(h,p,n) ((void)(p),(void)(n),event(11))
#define RTMP_TEST_FLAG(p,f) (((p)->flags&(f))!=0)
static void model_read(RTMP_ADAPTER *p,int reg,UINT32 *value){
 WPDMA_GLO_CFG_STRUC word;assert(reg==MT_WPDMA_GLO_CFG);
 if(!poll_reads){event(1);}poll_reads++;word.word=0;
 if(!idle||poll_reads<=busy_before_idle){word.MT7615_field.TxDMABusy=word.MT7615_field.RxDMABusy=1;}
 if(vanish_on_read){p->flags|=fRTMP_ADAPTER_NIC_NOT_EXIST;}
 *value=word.word;}
#define HIF_IO_READ32(p,r,v) model_read(p,r,v)
static int AsicSetWPDMA(RTMP_ADAPTER *p,int txrx,int enable){(void)p;
 assert(txrx==PDMA_TX_RX);event(enable?2:3);return set_ok;}
static void RtmpusecDelay(int n){if(n==1000){poll_delays++;}else{assert(n==50);}}
static int MtAsicResetWPDMA(RTMP_ADAPTER *p){(void)p;event(4);return reset_ok;}
static void AsicNotSupportFunc(RTMP_ADAPTER *p,const char *n){(void)p;(void)n;unsupported++;}
static void AsicSetRxFilter(RTMP_ADAPTER *p){(void)p;event(8);}
static void AsicSetMacTxRx(RTMP_ADAPTER *p,int which,int on){(void)p;(void)which;assert(on);event(9);}
static int mt_restart_fw(RTMP_ADAPTER *p){(void)p;event(10);return restart_status;}
static void RTMPResetTxRxRingMemory(RTMP_ADAPTER *p){(void)p;event(12);
 if(!idle){unsafe_frees++;}assert(ring_live);ring_live=0;}
static void cut_through_deinit(PKT_TOKEN_CB **p){event(13);
 if(!idle){unsafe_frees++;}assert(token_live);token_live=0;*p=NULL;}
static int WfEPROMSysExit(RTMP_ADAPTER *p){(void)p;event(14);return 0;}
static int WfMcuSysExit(RTMP_ADAPTER *p){(void)p;event(15);return 0;}
'''
SUFFIX=r'''
int main(int argc,char **argv){RTMP_ADAPTER ad;const char *name;int result=0,i;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&ad,0,sizeof(ad));ad.PktTokenCb=&ad;ops.FwInit=AndesMTPciFwInit;ops.hif_wait_dma_idle=hif_wait_WPDMA_idle;
 if(strstr(name,"busy")&&!strstr(name,"busy-to-idle"))idle=0;
 if(strstr(name,"busy-to-idle"))busy_before_idle=2;
 if(strstr(name,"nic-missing"))ad.flags|=fRTMP_ADAPTER_NIC_NOT_EXIST;
 if(strstr(name,"nic-vanishes"))vanish_on_read=1;
 if(strstr(name,"set-failure")&&!strstr(name,"reset-failure"))set_ok=0;
 if(strstr(name,"callback-failure")||strstr(name,"reset-failure"))reset_ok=0;
 if(strstr(name,"non-mt"))mt=0;
 if(strstr(name,"no-callback"))ops.FwInit=NULL;
 if(!strncmp(name,"enable-",7))result=RT28XXDMAEnable(&ad);
 else if(!strncmp(name,"stop-",5))result=RT28XXDMAStop(&ad);
 else if(!strncmp(name,"reset-",6))result=RT28XXDMAReset(&ad);
 else if(!strcmp(name,"asic-non-mt"))result=AsicResetWPDMA(&ad);
 else if(!strncmp(name,"fw-init-",8))result=WfMcuSysInit(&ad);
 else if(!strncmp(name,"ready-",6))result=mt_sys_ready(&ad);
 else if(!strncmp(name,"rx-filter-",10))result=RTMPEnableRxTx(&ad);
 else if(!strncmp(name,"restart-",8)){if(strstr(name,"failure"))restart_status=7;result=NICRestartFirmware(&ad);}
 else if(!strncmp(name,"teardown-",9))result=WfSysPosExit(&ad);
 else return 92;
 printf("[%d,%u,%d,%d,%d,%d,%d,%d,%d",result,ad.flags,irq,mcu_inits,
 ring_live,token_live,unsafe_frees,unsupported,count);
 for(i=0;i<count;i++){printf(",%d",events[i]);}printf(",%d,%d]\n",poll_reads,poll_delays);return 0;}
'''

def function(text,name):
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:inline\s+)?(?:VOID|BOOLEAN|INT|INT32|int|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    found=list(re.finditer(pattern,masked,re.M))
    if len(found)!=1:raise ValueError('Missing/ambiguous DMA function: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated DMA function: '+name)

def declarations(texts):
    result=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        found=re.findall(pattern,texts[key],re.M)
        if len(found)!=1:raise ValueError('Missing/ambiguous DMA declaration: '+pattern)
        result.append(found[0])
    return '\n'.join(result)

def generate_source(texts,variant='current'):
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current DMA inputs required')
    prefix=PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts))
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return prefix+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)

def function_manifest(texts):
    return {n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}
