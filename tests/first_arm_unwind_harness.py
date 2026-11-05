"""Whole WiFi init/error chain with private staged owners; no hardware execution."""
import hashlib
import re
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'inf':BASE+'embedded/common/rtmp_init_inf.c','hw':BASE+'hw_ctrl/hw_init.c',
 'ap':BASE+'embedded/ap/ap.c','flags':BASE+'embedded/include/rtmp_def.h',
 'os_header':BASE+'include/os/rt_linux.h','open':BASE+'os/linux/rt_main_dev.c'}
FUNCTION_SOURCES={'WfMcuInit':'hw','WfInit':'hw','rtmp_ap_init':'ap',
 'mt_sys_ready':'inf','mt_wifi_init':'inf','WfSysPosExit':'hw','mt_wifi_open':'open'}
SOURCE_ONLY_FUNCTION_SOURCES={'ApAutoChannelAtBootUp':'ap','APOverlappingBSSScan':'ap','RTMPDrvClose':'inf','RtmpOSIRQRequest':'open','rtmp_sys_task_exit':'inf'}
BODY_ORDER=('WfMcuInit','WfInit','rtmp_ap_init','mt_sys_ready','WfSysPosExit','mt_wifi_init','mt_wifi_open')
CASE_NAMES=('sys-failure','top-failure','hif-failure','mcu-sys-failure',
 'mcu-hw-failure','eeprom-failure','mac-failure','phy-failure','mlme-failure',
 'ap-arm-failure','ready-arm-failure','success','unwind-busy-retained','open-irq-failure','open-mlme-failure','open-success')
FIELDS=('result','flags','sys_live','hif_live','mcu_live','eeprom_live',
 'mlme_live','ap_live','tm_live','qm_live','tr_live','ser_live','armed',
 'invalid_operations','unsafe_hif_cleanup','sys_exits','event_count','events...','irq_requests','irq_releases','irq_live','hw_live','mgmt_live','timers_live')
EXPECTED_ROWS={'sys-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0], 'top-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 8, 1, 2, 20, 25, 26, 17, 21, 20, 0, 0, 0, 0, 0, 0], 'hif-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 9, 1, 2, 3, 20, 25, 26, 17, 21, 20, 0, 0, 0, 0, 0, 0], 'mcu-sys-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 13, 1, 2, 3, 4, 20, 25, 26, 17, 6, 20, 7, 21, 20, 0, 0, 0, 0, 0, 0], 'mcu-hw-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 14, 1, 2, 3, 4, 5, 20, 25, 26, 17, 6, 20, 7, 21, 20, 0, 0, 0, 0, 0, 0], 'eeprom-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 14, 1, 2, 3, 4, 5, 8, 20, 25, 26, 17, 6, 7, 21, 20, 0, 0, 0, 0, 0, 0], 'mac-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 16, 1, 2, 3, 4, 5, 8, 10, 20, 25, 26, 17, 9, 6, 7, 21, 20, 0, 0, 0, 0, 0, 0], 'phy-failure': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 17, 1, 2, 3, 4, 5, 8, 10, 11, 20, 25, 26, 17, 9, 6, 7, 21, 20, 0, 0, 0, 0, 0, 0], 'mlme-failure': [0, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 19, 1, 2, 3, 4, 5, 8, 10, 11, 12, 13, 20, 25, 26, 17, 9, 6, 7, 21, 20, 0, 0, 0, 0, 0, 0], 'ap-arm-failure': [0, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 22, 1, 2, 3, 4, 5, 8, 10, 11, 12, 14, 15, 16, 13, 20, 25, 26, 17, 9, 6, 7, 21, 20, 0, 0, 0, 0, 0, 0], 'ready-arm-failure': [0, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 23, 1, 2, 3, 4, 5, 8, 10, 11, 12, 14, 15, 15, 16, 13, 20, 25, 26, 17, 9, 6, 7, 21, 20, 0, 0, 0, 0, 0, 0], 'success': [1, 285212674, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 12, 1, 2, 3, 4, 5, 8, 10, 11, 12, 14, 15, 15, 0, 0, 0, 1, 1, 1], 'unwind-busy-retained': [0, 16777280, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 9, 1, 2, 3, 4, 5, 8, 10, 11, 12, 0, 0, 0, 1, 1, 1], 'open-mlme-failure': [-1, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 21, 22, 1, 2, 3, 4, 5, 8, 10, 11, 12, 13, 20, 25, 26, 17, 9, 6, 7, 21, 20, 23, 1, 1, 0, 0, 0, 0], 'open-success': [0, 285212674, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 14, 22, 1, 2, 3, 4, 5, 8, 10, 11, 12, 14, 15, 15, 24, 1, 0, 1, 1, 1, 1], 'open-irq-failure': [-16, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 22, 1, 0, 0, 0, 0, 0]}
SOURCE_DECLARATIONS={
 r'^#define NDIS_STATUS_SUCCESS\s+0x[0-9a-fA-F]+\s*$':'os_header',
 r'^#define NDIS_STATUS_FAILURE\s+0x[0-9a-fA-F]+\s*$':'os_header',
 r'^#define fRTMP_ADAPTER_START_UP[^\n]*':'flags',
 r'^#define fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD[^\n]*':'flags',
 r'^#define fRTMP_ADAPTER_HALT_IN_PROGRESS[^\n]*':'flags',
 r'^#define fRTMP_ADAPTER_INTERRUPT_ACTIVE[^\n]*':'flags',
 r'^#define fRTMP_ADAPTER_INTERRUPT_REGISTER_TO_OS[^\n]*':'flags'}
PREFIX=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
typedef unsigned long ULONG;typedef unsigned int dma_addr_t,ra_dma_addr_t;
typedef void VOID;typedef char RTMP_STRING;typedef unsigned char UCHAR,UINT8;
typedef int INT,INT32,NDIS_STATUS,BOOLEAN;
#define TRUE 1
#define FALSE 0
#define CONFIG_AP_SUPPORT
#define ERR_RECOVERY
#define DBDC_BAND_NUM 2
#define MAIN_MBSSID 0
#define HIF_MT 2
#define fOP_AP_STATUS_MEDIA_STATE_CONNECTED 0
#define MTWF_LOG(...) ((void)0)
SOURCE_DEFINITIONS
struct wifi_dev {int unused;};
typedef struct {int ChListNum;} CHANNEL_CTRL;
typedef struct {int ioctl_if,ioctl_if_type;} COOKIE,*POS_COOKIE;
struct _RTMP_CHIP_CAP {int unused;};
typedef struct _RTMP_ADAPTER {void *OS_Cookie,*hdev_ctrl,*net_dev;unsigned flags;
 int OpMode,dma_running,dma_irq_registered;unsigned char CurrentAddress[6];
 struct {struct {struct wifi_dev wdev;} MBSSID[1];} ApCfg;
 struct {int ucEDCCACtrl[2];} CommonCfg;
 struct {int Enabled[2];} OneSecMibBucket;
 struct {int Enabled;} MsMibBucket;
 struct {int queues_retired;} ErrRecoveryCtl;} RTMP_ADAPTER;
struct net_device {RTMP_ADAPTER *adapter;};
static char *mac,*hostname;static int irq_requests,irq_releases,irq_live;
static struct _RTMP_CHIP_CAP cap;static CHANNEL_CTRL channels[2];
static int hw_live,mgmt_live,timers_live;
static int stage,busy,events[128],count,invalid,sys_live,hif_live,mcu_live,eeprom_live;
static int lifetime_quarantined;
static int mlme_live,ap_live,tm_live,qm_live,tr_live,ser_live,armed,unsafe_hif,sys_exits,rx_calls;
static void event(int n){assert(count<128);events[count++]=n;}
#define IS_HIF_TYPE(p,n) ((void)(p),(void)(n),1)
#define IF_DEV_CONFIG_OPMODE_ON_AP(p) if((void)(p),1)
#define RT_CONFIG_IF_OPMODE_ON_AP(p) if((void)(p),1)
#define RTMP_TEST_FLAG(p,f) (((p)->flags&(f))!=0)
#define RTMP_SET_FLAG(p,f) ((p)->flags|=(f))
#define RTMP_CLEAR_FLAG(p,f) ((p)->flags&=~(f))
#define RTMP_CLEAR_FLAGS(p) ((p)->flags=0)
#define OPSTATUS_CLEAR_FLAG(p,f) ((void)(p),(void)(f))
#define RTMP_IRQ_ENABLE(p) ((void)(p))
#define RTMP_ASIC_INTERRUPT_DISABLE(p) ((void)(p))
/* Inert lifecycle seam: the full production graph is exercised by the
 * separate dma_quarantine_harness, including module/PCI refs and real locks. */
#define RtmpDmaLifecycleLock(p) ((void)(p))
#define RtmpDmaLifecycleUnlock(p) ((void)(p))
#define RtmpDmaLifecycleGet(p) ((void)(p),!lifetime_quarantined)
#define RtmpDmaLifecyclePut(p) ((void)(p))
static int RtmpDmaTeardownCheck(RTMP_ADAPTER *p){if(busy){lifetime_quarantined=1;
 RTMP_SET_FLAG(p,fRTMP_ADAPTER_HALT_IN_PROGRESS);RTMP_CLEAR_FLAG(p,fRTMP_ADAPTER_START_UP);return 0;}return !lifetime_quarantined;}
#define RtmpDmaResourcesMayRelease(p) ((void)(p),!lifetime_quarantined)
static int HcGetBandByWdev(struct wifi_dev *p){(void)p;return 0;}
static CHANNEL_CTRL *hc_get_channel_ctrl(void *p,int n){(void)p;return &channels[n];}
static struct _RTMP_CHIP_CAP *hc_get_chip_cap(void *p){(void)p;return &cap;}
static void mt_chip_info_show(RTMP_ADAPTER *p){(void)p;}
static void rtmp_hif_data_init(RTMP_ADAPTER *p){(void)p;}
static int rtmp_sys_init(RTMP_ADAPTER *p,char *name){(void)name;event(1);
 if(stage==1){return 0;}sys_live=tm_live=qm_live=tr_live=ser_live=hw_live=mgmt_live=timers_live=1;p->ErrRecoveryCtl.queues_retired=0;return 1;}
static void rtmp_sys_task_exit(RTMP_ADAPTER *p){event(20);ser_live=0;
 if(hw_live){event(25);hw_live=0;}if(mgmt_live){event(26);mgmt_live=0;}
 if(!p->ErrRecoveryCtl.queues_retired){tm_live=qm_live=0;p->ErrRecoveryCtl.queues_retired=1;}tr_live=0;if(timers_live){event(17);timers_live=0;}}
static int rtmp_sys_exit(RTMP_ADAPTER *p){event(21);sys_exits++;if(!sys_live){invalid++;}
 rtmp_sys_task_exit(p);sys_live=0;RTMP_CLEAR_FLAG(p,fRTMP_ADAPTER_INTERRUPT_REGISTER_TO_OS);return 1;}
static int WfTopInit(RTMP_ADAPTER *p){(void)p;event(2);return stage==2?1:0;}
static int WfHifInit(RTMP_ADAPTER *p){(void)p;event(3);if(stage==3){return 1;}hif_live=1;return 0;}
static int WfMcuSysInit(RTMP_ADAPTER *p){(void)p;event(4);mcu_live=1;if(stage==4){return 1;}armed=1;RTMP_SET_FLAG(p,fRTMP_ADAPTER_START_UP|fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD);return 0;}
static int WfMcuHwInit(RTMP_ADAPTER *p){(void)p;event(5);return stage==5?1:0;}
static int WfMcuSysExit(RTMP_ADAPTER *p){(void)p;event(6);if(!mcu_live){invalid++;}mcu_live=0;RTMP_CLEAR_FLAG(p,fRTMP_ADAPTER_START_UP|fRTMP_ADAPTER_MCU_SEND_IN_BAND_CMD);return 0;}
static int WfHifSysExit(RTMP_ADAPTER *p){(void)p;event(7);if(!hif_live){invalid++;}
 if(armed&&(tm_live||qm_live||tr_live||ser_live||hw_live||mgmt_live||timers_live)){invalid++;}
 if(busy){unsafe_hif++;}hif_live=0;if(!busy){armed=0;}return busy?1:0;}
static int WfEPROMInit(RTMP_ADAPTER *p){(void)p;event(8);if(stage==6){return 1;}eeprom_live=1;return 0;}
static int WfEPROMSysExit(RTMP_ADAPTER *p){(void)p;event(9);if(!eeprom_live){invalid++;}eeprom_live=0;return 0;}
static int WfMacInit(RTMP_ADAPTER *p){(void)p;event(10);return stage==7?1:0;}
static int WfPhyInit(RTMP_ADAPTER *p){(void)p;event(11);return stage==8?1:0;}
static void HWCtrlOpsReg(RTMP_ADAPTER *p){(void)p;}
static int MlmeInit(RTMP_ADAPTER *p){(void)p;event(12);mlme_live=1;return stage==9?1:0;}
static void MlmeHalt(RTMP_ADAPTER *p){(void)p;event(13);if(!mlme_live){invalid++;}mlme_live=0;}
static void NICInitializeAsic(RTMP_ADAPTER *p){(void)p;}
static void tx_pwr_comp_init(RTMP_ADAPTER *p){(void)p;}
static void RTMPIoctlRvRDebug_Init(RTMP_ADAPTER *p){(void)p;}
static void APOneShotSettingInitialize(RTMP_ADAPTER *p){(void)p;}
static void APInitForMain(RTMP_ADAPTER *p){(void)p;event(14);ap_live=1;}
static void RtmpOSNetDevAddrSet(int op,void *net,void *mac,void *extra){(void)op;(void)net;(void)mac;(void)extra;}
static int RTMPEnableRxTx(RTMP_ADAPTER *p){(void)p;event(15);rx_calls++;
 return !((stage==10&&rx_calls==1)||(stage==11&&rx_calls==2));}
static void APShutdown(RTMP_ADAPTER *p){(void)p;event(16);if(!ap_live){invalid++;}ap_live=0;}
static void AutoChSelInit(RTMP_ADAPTER *p){(void)p;}
static void EDCCACtrlCmd(RTMP_ADAPTER *p,int band,int v){(void)p;(void)band;(void)v;}

#define GET_PAD_FROM_NET_DEV(p,n) ((p)=(n)->adapter)
#define RTMP_DRIVER_MCU_SLEEP_CLEAR(p) ((void)(p))
#define RTMP_DRIVER_OP_MODE_GET(p,n) ((void)(p),*(n)=0)
#define RTMP_DRIVER_IRQ_INIT(p) ((void)(p))
#define RTMP_DRIVER_IRQ_RELEASE(p) ((void)(p),event(23),irq_releases++,irq_live--)
#define WLAN_HOOK_CALL(h,p,n) ((void)(p),(void)(n))
static int load_dev_l1profile(void *p){(void)p;return 0;}
static int RtmpOSIRQRequest(struct net_device *n){(void)n;event(22);irq_requests++;
 if(stage==12){return -16;}irq_live=1;return 0;}
static void RTMPDrvOpen(void *p){(void)p;event(24);}

'''
SUFFIX=r'''
int main(int argc,char **argv){RTMP_ADAPTER ad;COOKIE cookie;const char *name;int result,i;struct net_device net;
 assert(argc==2);name=argv[1];CASE_ADMISSION
 memset(&ad,0,sizeof(ad));memset(&cookie,0,sizeof(cookie));ad.OS_Cookie=&cookie;net.adapter=&ad;
 if(!strcmp(name,"sys-failure"))stage=1;
 else if(!strcmp(name,"open-irq-failure"))stage=12;
 else if(!strcmp(name,"open-mlme-failure"))stage=9;
 else if(!strcmp(name,"top-failure"))stage=2;
 else if(!strcmp(name,"hif-failure"))stage=3;
 else if(!strcmp(name,"mcu-sys-failure"))stage=4;
 else if(!strcmp(name,"mcu-hw-failure"))stage=5;
 else if(!strcmp(name,"eeprom-failure"))stage=6;
 else if(!strcmp(name,"mac-failure"))stage=7;
 else if(!strcmp(name,"phy-failure"))stage=8;
 else if(!strcmp(name,"mlme-failure"))stage=9;
 else if(!strcmp(name,"ap-arm-failure"))stage=10;
 else if(!strcmp(name,"ready-arm-failure"))stage=11;
 else if(!strcmp(name,"unwind-busy-retained")){stage=9;busy=1;}
 if(!strncmp(name,"open-",5)){result=mt_wifi_open(&net);}else{result=mt_wifi_init(&ad,NULL,NULL);}
 printf("[%d,%u,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d",
 result,ad.flags,sys_live,hif_live,mcu_live,eeprom_live,mlme_live,ap_live,
 tm_live,qm_live,tr_live,ser_live,armed,invalid,unsafe_hif,sys_exits,count);
 for(i=0;i<count;i++){printf(",%d",events[i]);}printf(",%d,%d,%d,%d,%d,%d]\n",irq_requests,irq_releases,irq_live,hw_live,mgmt_live,timers_live);return 0;}
'''

def function(text,name):
    token=r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\])*"'
    masked=re.sub(token,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:inline\s+)?(?:VOID|BOOLEAN|UCHAR|INT|INT32|int|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    found=list(re.finditer(pattern,masked,re.M))
    if len(found)!=1:raise ValueError('Missing/ambiguous init unwind function: '+name)
    start=found[0].start();opening=masked.index('{',start);depth=0
    for m in re.finditer(token+r'|[{}]',text[opening:]):
        if m.group()=='{':depth+=1
        elif m.group()=='}':
            depth-=1
            if not depth:return text[start:opening+m.end()]
    raise ValueError('Unterminated init unwind function: '+name)

def declarations(texts):
    result=[]
    for pattern,key in SOURCE_DECLARATIONS.items():
        found=re.findall(pattern,texts[key],re.M)
        if len(found)!=1:raise ValueError('Missing init unwind declaration: '+pattern)
        result.append(found[0])
    return '\n'.join(result)

def generate_source(texts,variant='current'):
    if variant!='current' or set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact current init unwind inputs required')
    prefix=PREFIX.replace('SOURCE_DEFINITIONS',declarations(texts))
    admission='if(!('+'||'.join('!strcmp(name,"'+n+'")'for n in CASE_NAMES)+'))return 91;'
    return prefix+'\n'.join(function(texts[FUNCTION_SOURCES[n]],n)for n in BODY_ORDER)+SUFFIX.replace('CASE_ADMISSION',admission)

def function_manifest(texts):
    return {n:{'source':k,'execution':'whole-function','full_body_sha256':hashlib.sha256(function(texts[k],n).encode()).hexdigest()}for n,k in FUNCTION_SOURCES.items()}
