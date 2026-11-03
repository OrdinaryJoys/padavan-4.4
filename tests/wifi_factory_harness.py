"""Pure configured MT7615 Factory-read startup chain, without physical IO.

Ten whole actual functions run under RAM and radio recording seams. The
three large parameter/ATE consumers execute explicitly delimited early source
sections; their complete bodies remain source-bound metadata. No claim is made
that later proprietary parsing or ATE teardown executes in this adapter.
"""
import hashlib
import re

BASELINE_COMMIT='6e91276a33d1bd83d416fc8253feb01f30677743'
PREFIX_PATH='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={
 'wifi_flash':PREFIX_PATH+'embedded/common/ee_flash.c',
 'wifi_eeprom':PREFIX_PATH+'embedded/common/eeprom.c',
 'wifi_init':PREFIX_PATH+'embedded/common/rtmp_init.c',
 'wifi_hw':PREFIX_PATH+'hw_ctrl/hw_init.c',
 'wifi_ate':PREFIX_PATH+'ate/mt_mac/mt_ate.c',
 'wifi_testmode':PREFIX_PATH+'ate/mt_mac/mt_testmode.c',
}
FUNCTION_SOURCES={
 'RtmpFlashRead':'wifi_flash','RtmpFlashWrite':'wifi_flash',
 'rtmp_ee_flash_read':'wifi_flash','validFlashEepromID':'wifi_flash',
 'rtmp_ee_flash_write_all':'wifi_flash','rtmp_ee_flash_reset':'wifi_flash',
 'rtmp_ee_flash_init':'wifi_flash',
 'rtmp_nv_init':'wifi_flash','NICReadEEPROMParameters':'wifi_eeprom',
 'WfEPROMSysInit':'wifi_init','WfEPROMInit':'wifi_hw',
 'ate_pci_ate_leave':'wifi_ate','testmode_pci_ate_leave':'wifi_testmode',
}
PROJECTED_FUNCTIONS=('NICReadEEPROMParameters','ate_pci_ate_leave','testmode_pci_ate_leave')
BODY_ORDER=tuple(FUNCTION_SOURCES)
PROJECTIONS={
 'NICReadEEPROMParameters':{
  'start':'\tstruct _RTMP_CHIP_OP *ops =',
  'end':'\n#ifdef PRE_CAL_MT7622_SUPPORT\n\tif', 'include_end':False,
  'prefix':'INT NICReadEEPROMParameters(RTMP_ADAPTER*pAd,RTMP_STRING*mac_addr){\n(void)mac_addr;\n',
  'suffix':'\nparse_calls++;event("parse");return TRUE;\n}',
 },
 'ate_pci_ate_leave':{
  'start':'\tMTWF_LOG(', 'end':'\tNICInitAsicFromEEPROM(pAd);','include_end':True,
  'prefix':'static INT32 ate_pci_ate_leave(RTMP_ADAPTER*pAd){\n',
  'suffix':'\nreturn NDIS_STATUS_SUCCESS;\n}',
 },
 'testmode_pci_ate_leave':{
  'start':'\tMTWF_LOG(', 'end':'\tNICInitAsicFromEEPROM(pAd);','include_end':True,
  'prefix':'static INT32 testmode_pci_ate_leave(RTMP_ADAPTER*pAd){\n',
  'suffix':'\nreturn NDIS_STATUS_SUCCESS;\n}',
 },
}
CASE_NAMES=('direct-read-ok','direct-read-error','direct-read-short','direct-read-erased',
 'direct-allocation-failure','direct-existing-error','direct-reset-failure',
 'boot-read-ok','boot-read-error','boot-read-short','boot-allocation-failure','boot-read-erased',
 'ate-read-ok','ate-read-error','testmode-read-ok','testmode-read-error',
 'direct-default-write-error','boot-default-write-error',
 'direct-default-file-ok','direct-default-file-error','direct-default-short-file-error',
 'direct-default-close-error','direct-default-missing-error','direct-default-short-cache-error',
 'direct-default-invalid-id-error','direct-default-empty-path-error','direct-small-buffer-error',
 'direct-default-oversized-read-error','direct-default-long-cache-ok')
BASELINE_CASES=('direct-read-ok','direct-read-error','direct-read-short','direct-existing-error',
 'boot-read-error','boot-allocation-failure','ate-read-error','testmode-read-error',
 'direct-default-write-error','boot-default-write-error',
 'direct-default-file-error','direct-default-short-file-error','direct-default-close-error',
 'direct-default-missing-error','direct-default-short-cache-error','direct-default-invalid-id-error',
 'direct-default-empty-path-error','direct-default-oversized-read-error')
DISABLED_CASES=('direct-read-ok','direct-read-error')


def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    pattern=r'^(?:static\s+)?(?:void|VOID|int|INT|INT32|BOOLEAN|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    matches=list(re.finditer(pattern,masked,re.M))
    if len(matches)!=1:raise ValueError('Missing/ambiguous WiFi function '+name)
    start=matches[0].start();opening=text.index('{',start);depth=0
    for token in re.finditer(tokens+r'|[{}]',text[opening:]):
        if token.group()=='{':depth+=1
        elif token.group()=='}':
            depth-=1
            if not depth:return text[start:opening+token.end()]
    raise ValueError('Unterminated WiFi function '+name)


def actual_functions(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact configured WiFi source set required')
    return {name:{'source':key,'body':function(texts[key],
             'pci_ate_leave' if name in PROJECTED_FUNCTIONS[1:] else name),
             'execution':'early-section' if name in PROJECTED_FUNCTIONS else 'whole-function'}
            for name,key in FUNCTION_SOURCES.items()}


def execution_sections(functions):
    sections={}
    for name,spec in PROJECTIONS.items():
        body=functions[name]['body'];start=body.index(spec['start'])
        end=body.index(spec['end'],start)+(len(spec['end']) if spec['include_end'] else 0)
        sections[name]=body[start:end]
    return sections


def executed_fragments(functions,disabled_oracle=False):
    sections=execution_sections(functions)
    result={name:(PROJECTIONS[name]['prefix']+sections[name]+PROJECTIONS[name]['suffix']
                  if name in PROJECTIONS else item['body']) for name,item in functions.items()}
    if disabled_oracle:
        result['rtmp_nv_init']='NDIS_STATUS rtmp_nv_init(RTMP_ADAPTER*p){(void)p;return NDIS_STATUS_SUCCESS;}'
    return result


PREFIX=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CONFIG_WIFI_MTD 1
#define PRE_CAL_TRX_SET1_SUPPORT 1
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define TRUE 1
#define FALSE 0
#define E2P_NONE 0
#define E2P_FLASH_MODE 2
#define E2P_SRC_FROM_FLASH 2
#define E2P_SRC_FROM_BIN 8
#define EEPROM_SIZE 64
#define MAX_EEPROM_BUFFER_SIZE 64
#define EEPROM_DEFAULT_FILE_PATH default_path
#define O_RDONLY 0
#define IS_FILE_OPEN_ERR(f) ((f)<0)
#define DCOC_OFFSET 16
#define DPDPART1_OFFSET 24
#define DPDPART2_OFFSET 32
#define MTWF_LOG(a,b,c,args) do{if(0)printf args;}while(0)
#define NdisZeroMemory(p,n) memset(p,0,n)
#define NdisMoveMemory(p,s,n) memcpy(p,s,n)
#define le2cpu16(x) (x)
#define IS_MT7615(p) 1
#define IS_EE_INIT(p) (hc_get_chip_cap((p)->hdev_ctrl)->ee_inited)
typedef unsigned char UCHAR;
typedef unsigned short USHORT;
typedef unsigned short UINT16;
typedef unsigned long ULONG;
typedef int INT;
typedef unsigned int UINT;
typedef int INT32;
typedef int BOOLEAN;
typedef int NDIS_STATUS;
typedef void VOID;
typedef char RTMP_STRING;
typedef UCHAR*PUCHAR;
struct _RTMP_CHIP_CAP {int ee_inited;UCHAR*EEPROM_DEFAULT_BIN;UINT EEPROM_DEFAULT_BIN_SIZE;};
typedef struct {int e2pCurMode,e2pSource;void*BinSource;} EEPROM_CONTROL;
typedef struct {int previous;} RTMP_OS_FS_INFO;
typedef int RTMP_OS_FD;
typedef struct _RTMP_ADAPTER {
 UCHAR*EEPROMImage,*CalDCOCImage,*CalDPDAPart1Image,*CalDPDAPart2Image;
 int bDPDReloaded;unsigned int ChipID;void*hdev_ctrl;EEPROM_CONTROL E2pCtrl;
 int infType,RfIcType;struct {int dbdc_mode;} CommonCfg;
} RTMP_ADAPTER,*PRTMP_ADAPTER;
struct _RTMP_CHIP_OP {NDIS_STATUS(*eeinit)(RTMP_ADAPTER*);};
static struct _RTMP_CHIP_CAP chip_cap;
static struct _RTMP_CHIP_OP chip_ops;
static const char*case_name;
static RTMP_STRING*mac;
static UCHAR default_bytes[96];
static UCHAR*default_path=(UCHAR*)"/inert/default.bin";
static int reads,factorywrites,defaults,parse_calls,radio,asic,allocs,frees_count,exits;
static int fsdepth,fileopens,filereads,filecloses;
static char trace[512];
static int contains(const char*n){return strstr(case_name,n)!=NULL;}
static void event(const char*s){if(strlen(trace)+strlen(s)+2>=sizeof(trace))abort();if(*trace)strcat(trace,",");strcat(trace,s);}
static struct _RTMP_CHIP_CAP*hc_get_chip_cap(void*h){(void)h;return &chip_cap;}
static struct _RTMP_CHIP_OP*hc_get_chip_ops(void*h){(void)h;return &chip_ops;}
static UINT get_dev_eeprom_size(RTMP_ADAPTER*p){(void)p;return contains("small-buffer-error")?32:64;}
static int get_dev_eeprom_offset(RTMP_ADAPTER*p){(void)p;return 0;}
static void os_free_mem(void*p){if(p){frees_count++;event("free");free(p);}}
static int os_alloc_mem(RTMP_ADAPTER*a,UCHAR**p,size_t len){(void)a;allocs++;event("alloc");*p=contains("allocation-failure")?NULL:malloc(len);return *p?0:1;}
static int mt_mtd_read_nm_wifi(char*n,long long offset,size_t len,UCHAR*buf){
 size_t i;(void)n;(void)offset;reads++;event("read");
 if((contains("read-error")&&!contains("oversized-read-error"))||contains("existing-error"))return -5;
 if(contains("read-short")){memset(buf,0,len-1);return -5;}
 if(contains("read-erased")||contains("reset-failure")||contains("default-")||contains("small-buffer-error")){memset(buf,0xff,len);return 0;}
 for(i=0;i<len;i++)buf[i]=(UCHAR)i;
 buf[0]=0x15;buf[1]=0x76;return 0;
}
static int mt_mtd_write_nm_wifi(char*n,long long offset,size_t len,const UCHAR*buf){(void)n;(void)offset;(void)len;(void)buf;factorywrites++;event("factory-write");return contains("default-write-error")?-5:0;}
#define flash_read(c,p,o,n) mt_mtd_read_nm_wifi("Factory",o,n,p)
#define flash_write(c,p,o,n) mt_mtd_write_nm_wifi("Factory",o,n,p)
static void RtmpOSFSInfoChange(RTMP_OS_FS_INFO*info,BOOLEAN enter){if(enter){info->previous=fsdepth;fsdepth++;event("fs-enter");}else{fsdepth=info->previous;event("fs-restore");}}
static RTMP_OS_FD RtmpOSFileOpen(UCHAR*path,int flags,int mode){
 (void)path;(void)flags;(void)mode;defaults++;fileopens++;event("file-open");
 return (contains("default-file-")||contains("short-file-")||contains("close-error")||contains("oversized-read"))?1:-2;
}
static INT RtmpOSFileRead(RTMP_OS_FD fd,UCHAR*buf,INT len){
 INT n=len,i;(void)fd;filereads++;event("file-read");
 if(contains("default-file-error"))return -5;
 if(contains("short-file-error"))n=len/2;
 for(i=0;i<n;i++)buf[i]=(UCHAR)i;
 buf[0]=0x15;buf[1]=0x76;
 return contains("oversized-read-error")?len+1:n;
}
static INT RtmpOSFileClose(RTMP_OS_FD fd){(void)fd;filecloses++;event("file-close");return contains("close-error")?-5:0;}
static UCHAR RandomByte(RTMP_ADAPTER*p){(void)p;return 0x20;}
static void checkAntCapSanity(RTMP_ADAPTER*p){(void)p;event("antenna-check");}
static int RtmpChipOpsEepromHook(RTMP_ADAPTER*p,int type,int mode){(void)p;(void)type;(void)mode;event("hook");return 0;}
static void HcRadioInit(RTMP_ADAPTER*p,int type,int dbdc){(void)p;(void)type;(void)dbdc;radio++;event("radio");}
static UCHAR HcGetRadioRfIC(RTMP_ADAPTER*p){(void)p;return 1;}
#define RTMP_NET_DEV_NICKNAME_INIT(p) ((void)(p))
static void NICInitAsicFromEEPROM(RTMP_ADAPTER*p){(void)p;asic++;event("asic");}
static void WfEPROMHwInit(RTMP_ADAPTER*p){(void)p;asic++;event("hw");}
static INT32 WfEPROMSysExit(RTMP_ADAPTER*p){(void)p;exits++;event("exit");return 0;}
'''


MAIN=r'''
int main(int argc,char**argv){
 RTMP_ADAPTER a;int status,known=0,i;
 if(argc!=2)return 90;
 case_name=argv[1];
 CASE_ADMISSION
 if(!known)return 91;
 memset(&a,0,sizeof(a));a.ChipID=0x7615;a.hdev_ctrl=&chip_cap;chip_cap.ee_inited=1;
 for(i=0;i<96;i++)default_bytes[i]=(UCHAR)i;
 default_bytes[0]=0x15;default_bytes[1]=0x76;
 chip_cap.EEPROM_DEFAULT_BIN=default_bytes;chip_cap.EEPROM_DEFAULT_BIN_SIZE=64;
 if(contains("default-missing-error")||contains("reset-failure"))chip_cap.EEPROM_DEFAULT_BIN=NULL;
 if(contains("short-cache-error"))chip_cap.EEPROM_DEFAULT_BIN_SIZE=2;
 if(contains("long-cache-ok"))chip_cap.EEPROM_DEFAULT_BIN_SIZE=96;
 if(contains("invalid-id-error"))default_bytes[0]=default_bytes[1]=0;
 if(contains("empty-path-error"))default_path=(UCHAR*)"";
 a.E2pCtrl.e2pCurMode=2;a.E2pCtrl.e2pSource=2;a.bDPDReloaded=1;
 a.CalDCOCImage=a.CalDPDAPart1Image=a.CalDPDAPart2Image=(void*)(uintptr_t)1;
 if(contains("existing-error"))a.EEPROMImage=malloc(64);
 chip_ops.eeinit=rtmp_nv_init;
 if(!strncmp(case_name,"boot-",5))status=WfEPROMInit(&a);
 else if(!strncmp(case_name,"ate-",4))status=ate_pci_ate_leave(&a);
 else if(!strncmp(case_name,"testmode-",9))status=testmode_pci_ate_leave(&a);
 else status=rtmp_nv_init(&a);
 printf("{\"case\":\"%s\",\"status\":%d,\"reads\":%d,\"factorywrites\":%d,\"defaults\":%d,\"parse\":%d,\"radio\":%d,\"asic\":%d,\"exits\":%d,\"capinit\":%d,\"image\":%d,\"mode\":%d,\"source\":%d,\"calibrated\":%d,\"allocs\":%d,\"frees\":%d,\"fsdepth\":%d,\"fileopens\":%d,\"filereads\":%d,\"filecloses\":%d,\"trace\":\"%s\"}\n",case_name,status,reads,factorywrites,defaults,parse_calls,radio,asic,exits,chip_cap.ee_inited,a.EEPROMImage!=NULL,a.E2pCtrl.e2pCurMode,a.E2pCtrl.e2pSource,a.bDPDReloaded&&a.CalDCOCImage&&a.CalDPDAPart1Image&&a.CalDPDAPart2Image,allocs,frees_count,fsdepth,fileopens,filereads,filecloses,trace);
 free(a.EEPROMImage);return 0;
}
'''
TAIL=MAIN


def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False,disabled_oracle=False):
    if type(baseline) is not bool or type(disabled_oracle) is not bool or (baseline and disabled_oracle):
        raise ValueError('Typed exclusive WiFi source profile required')
    functions=actual_functions(texts)
    for name,body in BASELINE_FUNCTIONS.items():
        if hashlib.sha256(body.encode()).hexdigest()!=BASELINE_FUNCTIONS_SHA256[name]:
            raise ValueError('Changed fixed WiFi baseline')
    if baseline:
        functions={name:dict(item,body=BASELINE_FUNCTIONS[name]) for name,item in functions.items()}
    fragments=executed_fragments(functions,disabled_oracle)
    bodies='\n'.join(fragments[name] for name in BODY_ORDER)
    admission='\n'.join('if(!strcmp(case_name,"'+name+'"))known=1;' for name in CASE_NAMES)
    return PREFIX+'\n'+bodies+'\n'+MAIN.replace('CASE_ADMISSION',admission)


# Fixed public 6e source bodies, independently compared to Git by offline gates.
BASELINE_FUNCTIONS = {'RtmpFlashRead': 'void RtmpFlashRead(\n\tvoid *hdev_ctrl,\n\tUCHAR *p,\n\tULONG a,\n\tULONG b)\n{\n\tflash_read(hdev_ctrl, p, a, b);\n}', 'RtmpFlashWrite': 'void RtmpFlashWrite(\n\tvoid *hdev_ctrl,\n\tUCHAR *p,\n\tULONG a,\n\tULONG b)\n{\n\tflash_write(hdev_ctrl, p, a, b);\n}', 'rtmp_ee_flash_read': 'BOOLEAN rtmp_ee_flash_read(PRTMP_ADAPTER pAd, UINT16 Offset, UINT16 *pValue)\n{\n\tBOOLEAN IsEmpty = 0;\n\n\tif (!IS_EE_INIT(pAd))\n\t\t*pValue = 0xffff;\n\telse\n\t\tmemcpy(pValue, pAd->EEPROMImage + Offset, 2);\n\n\tif ((*pValue == 0xffff) || (*pValue == 0x0000))\n\t\tIsEmpty = 1;\n\n\treturn IsEmpty;\n}', 'validFlashEepromID': 'static BOOLEAN  validFlashEepromID(RTMP_ADAPTER *pAd)\n{\n\tUSHORT eeFlashId;\n\trtmp_ee_flash_read(pAd, 0, &eeFlashId);\n\n\tif ((pAd->ChipID & 0x0000ffff) == eeFlashId)\n\t\treturn TRUE;\n\n\treturn FALSE;\n}', 'rtmp_ee_flash_write_all': 'VOID rtmp_ee_flash_write_all(PRTMP_ADAPTER pAd)\n{\n\tif (!IS_EE_INIT(pAd))\n\t\treturn;\n\n\tRtmpFlashWrite(pAd->hdev_ctrl, pAd->EEPROMImage, get_dev_eeprom_offset(pAd), get_dev_eeprom_size(pAd));\n}', 'rtmp_ee_flash_init': 'static NDIS_STATUS rtmp_ee_flash_init(PRTMP_ADAPTER pAd, PUCHAR start)\n{\n#ifdef CAL_FREE_IC_SUPPORT\n\tBOOLEAN bCalFree = 0;\n#endif /* CAL_FREE_IC_SUPPORT */\n\tstruct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);\n\tcap->ee_inited = 1;\n\n\tif (validFlashEepromID(pAd) == FALSE) {\n\t\tif (rtmp_ee_flash_reset(pAd, start) != NDIS_STATUS_SUCCESS) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("rtmp_ee_init(): rtmp_ee_flash_init() failed\\n"));\n\t\t\treturn NDIS_STATUS_FAILURE;\n\t\t}\n\n#ifdef CAL_FREE_IC_SUPPORT\n\t\tRTMP_CAL_FREE_IC_CHECK(pAd, bCalFree);\n\n\t\tif (bCalFree) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("Cal Free IC!!\\n"));\n\t\t\tRTMP_CAL_FREE_DATA_GET(pAd);\n\t\t} else\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Non Cal Free IC!!\\n"));\n\n#endif /* CAL_FREE_IC_SUPPORT */\n\t\t/* Random number for the last bytes of MAC address*/\n\t\t{\n\t\t\tUSHORT  Addr45;\n\t\t\trtmp_ee_flash_read(pAd, 0x08, &Addr45);\n\t\t\tAddr45 = Addr45 & 0xff;\n\t\t\tAddr45 = Addr45 | (RandomByte(pAd) & 0xf8) << 8;\n\t\t\t*(UINT16 *)(&pAd->EEPROMImage[0x08]) = le2cpu16(Addr45);\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("The EEPROM in Flash is wrong, use default\\n"));\n\t\t}\n\t\t/*write back  all to flash*/\n\t\trtmp_ee_flash_write_all(pAd);\n\n\t\tif (validFlashEepromID(pAd) == FALSE) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("rtmp_ee_flash_init(): invalid eeprom\\n"));\n\t\t\treturn NDIS_STATUS_FAILURE;\n\t\t}\n\t}\n\n\treturn NDIS_STATUS_SUCCESS;\n}', 'rtmp_nv_init': 'NDIS_STATUS rtmp_nv_init(RTMP_ADAPTER *pAd)\n{\n#ifdef MULTIPLE_CARD_SUPPORT\n\tUCHAR *eepromBuf;\n#endif /* MULTIPLE_CARD_SUPPORT */\n\tEEPROM_CONTROL *pE2pCtrl = &pAd->E2pCtrl;\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("--> rtmp_nv_init\\n"));\n\t/*\n\t\tpAd->EEPROMImage:\n\t\t+----------------------------------------------------------------------------------+\n\t\t| 1K (calibration) | 9K (DCOC) | 9K (DPDA Part1) | 9K (DPDA Part2G) | 16K (PreCal) |\n\t\t+----------------------------------------------------------------------------------+\n\t */\n\tif (pAd->EEPROMImage)\n\t\tos_free_mem(pAd->EEPROMImage);\n\n\tos_alloc_mem(pAd, &pAd->EEPROMImage, get_dev_eeprom_size(pAd));\n\tif (pAd->EEPROMImage) {\n\t\tNdisZeroMemory(pAd->EEPROMImage, get_dev_eeprom_size(pAd));\n\t\tRtmpFlashRead(pAd->hdev_ctrl, pAd->EEPROMImage, get_dev_eeprom_offset(pAd), get_dev_eeprom_size(pAd));\n\n#ifdef PRE_CAL_MT7622_SUPPORT\n\t\tif (IS_MT7622(pAd)) {\n\t\t\tpAd->CalTXLPFGImage = pAd->EEPROMImage + TXLPFG_FLASH_OFFSET;\n\t\t\tpAd->CalTXDCIQImage = pAd->EEPROMImage + TXDCIQ_FLASH_OFFSET;\n\t\t\tpAd->CalTXDPDImage = pAd->EEPROMImage + TXDPD_FLASH_OFFSET;\n\t\t}\n#endif /*PRE_CAL_MT7622_SUPPORT*/\n#ifdef PRE_CAL_TRX_SET1_SUPPORT\n\t\tif (IS_MT7615(pAd)) {\n\t\t\tpAd->CalDCOCImage = pAd->EEPROMImage + DCOC_OFFSET;\n\t\t\tpAd->CalDPDAPart1Image = pAd->EEPROMImage + DPDPART1_OFFSET;\n\t\t\tpAd->CalDPDAPart2Image = pAd->EEPROMImage + DPDPART2_OFFSET;\n\t\t\tpAd->bDPDReloaded = TRUE;\n\t\t}\n#endif /* PRE_CAL_TRX_SET1_SUPPORT */\n\t\tpE2pCtrl->e2pCurMode = E2P_FLASH_MODE;\n\t\tpE2pCtrl->e2pSource = E2P_SRC_FROM_FLASH;\n\t\treturn rtmp_ee_flash_init(pAd, pAd->EEPROMImage);\n\t} else {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t("Allocate %d-byte-of EEPROMImage failed.\\n", get_dev_eeprom_size(pAd)));\n\t\treturn NDIS_STATUS_FAILURE;\n\t}\n}', 'NICReadEEPROMParameters': 'INT NICReadEEPROMParameters(RTMP_ADAPTER *pAd, RTMP_STRING *mac_addr)\n{\n\tUSHORT i, value;\n\tEEPROM_VERSION_STRUC Version;\n\tEEPROM_ANTENNA_STRUC Antenna;\n\tEEPROM_NIC_CONFIG2_STRUC NicConfig2;\n\tUSHORT  Addr01, Addr23, Addr45;\n#ifdef PRE_CAL_TRX_SET2_SUPPORT\n\tUINT16 PreCalSize;\n#endif /* PRE_CAL_TRX_SET2_SUPPORT */\n#if defined(PRE_CAL_TRX_SET2_SUPPORT) || defined(PRE_CAL_MT7622_SUPPORT)\n\tUINT16 DoPreCal = 0;\n#endif /* PRE_CAL_TRX_SET2_SUPPORT */\n#if defined(CAL_BIN_FILE_SUPPORT) && defined(MT7615)\n\tUINT16 DoPATrim = 0;\n#endif /* CAL_BIN_FILE_SUPPORT */\n\tstruct _RTMP_CHIP_OP *ops = hc_get_chip_ops(pAd->hdev_ctrl);\n\n#ifdef PRE_CAL_MT7622_SUPPORT\n\tUINT32 ch;\n#endif /* PRE_CAL_MT7622_SUPPORT */\n\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s()-->\\n", __func__));\n\n\tif (ops->eeinit) {\n#if defined(WCX_SUPPORT)\n\t\t/* do nothing */\n#else\n\t\t/* If we are run in Multicard mode */\n\t\tops->eeinit(pAd);\n\t\tcheckAntCapSanity(pAd);\n#endif /*WCX_SUPPORT */\n#ifdef RF_LOCKDOWN\n\n\t\t/* Merge RF parameters in Effuse to E2p buffer */\n\t\tif (ops->merge_RF_lock_parameter != NULL)\n\t\t\tops->merge_RF_lock_parameter(pAd);\n\n\t\t/* Replace Country code and Country Region in Profile by Effuse content */\n\t\tif (ops->Config_Effuse_Country != NULL)\n\t\t\tops->Config_Effuse_Country(pAd);\n\n#endif /* RF_LOCKDOWN */\n\t}\n\n#ifdef PRE_CAL_MT7622_SUPPORT\n\tif (IS_MT7622(pAd)) {\n\t\t/* Check DoPreCal bits */\n\t\tRT28xx_EEPROM_READ16(pAd, 0x52, DoPreCal);\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t("\\x1b[34m%s: EEPROM 0x52 %x\\x1b[m\\n", __func__, DoPreCal));\n\t\tif (pAd->E2pAccessMode == E2P_FLASH_MODE) {\n\t\t\tif (DoPreCal & (1 << 3)) {\n\t\t\t\tMtCmdSetTxLpfCal_7622(pAd);\n\t\t\t\tMtCmdSetTxDcIqCal_7622(pAd);\n\t\t\t\tfor (ch = 1; ch < 14; ch++)\n\t\t\t\t\tMtCmdSetTxDpdCal_7622(pAd, ch);\n\t\t\t}\n\t\t}\n\t}\n#endif /*PRE_CAL_MT7622_SUPPORT*/\n\n#ifdef PRE_CAL_TRX_SET2_SUPPORT\n\n\tPreCalSize = PRE_CAL_SIZE_ONE_CARD;\n#ifdef CONFIG_RALINK_MT7621\n\t/* Litmit PreCalSize to 12k for MT7622 + MT7615 + MT7615 */\n#ifdef MULTI_INF_SUPPORT\n\tif (multi_inf_get_count() >= 2)\n\t\tPreCalSize = PRE_CAL_SIZE_DUAL_CARD;\n#endif /*MULTI_INF_SUPPORT*/\n#endif /*CONFIG_RALINK_MT7621*/\n\n\t/* Check DoPreCal bits */\n\tRT28xx_EEPROM_READ16(pAd, 0x52, DoPreCal);\n\n\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t ("\\x1b[34m%s: EEPROM 0x52 %x\\x1b[m\\n", __FUNCTION__, DoPreCal));\n\n\t/* Pre Cal only supports Bin or Flash Mode */\n\tif (pAd->E2pAccessMode == E2P_FLASH_MODE || pAd->E2pAccessMode == E2P_BIN_MODE) {\n\t/* Restore when RLM cache is empty */\n\t\tif (!rlmCalCacheDone(pAd->rlmCalCache) && (DoPreCal & (1 << 2))) {\n\t\t\tINT32 ret = 0;\n\t\t\tINT32 ret_cal_data = NDIS_STATUS_SUCCESS;\n\t\t\tret = os_alloc_mem(pAd, &pAd->PreCalReStoreBuffer, PreCalSize);/* Allocate 16K buffer*/\n\n\t\t\tif (ret != NDIS_STATUS_SUCCESS) {\n\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("\\x1b[42m %s : Not enough memory for pre-cal restored buffer!!\\x1b[m\\n", __FUNCTION__));\n\t\t\t} else {\n\t\t\t\t/* Read pre-cal data from flash and store to pre-cal buffer*/\n#ifdef RTMP_FLASH_SUPPORT\n\t\t\t\tif (pAd->E2pAccessMode == E2P_FLASH_MODE)\n\t\t\t\t\tRtmpFlashRead(pAd->hdev_ctrl, pAd->PreCalReStoreBuffer,\n\t\t\t\t\t\t\tget_dev_eeprom_offset(pAd) + PRECALPART_OFFSET, PreCalSize);\n#endif /* RTMP_FLASH_SUPPORT */\n\t\t\t\tif (pAd->E2pAccessMode == E2P_BIN_MODE) {\n\t\t\t\t\tret_cal_data = rtmp_cal_load_from_bin(pAd, pAd->PreCalReStoreBuffer, PRECALPART_OFFSET,\n\t\t\t\t\t\t\t\t\t\t PreCalSize);\n\n\t\t\t\t\tif (ret_cal_data != NDIS_STATUS_SUCCESS) {\n\t\t\t\t\t\t/* Erase DoPreCal bit */\n\t\t\t\t\t\tDoPreCal &= ~(1 << 2);\n\t\t\t\t\t\tRT28xx_EEPROM_WRITE16(pAd, 0x52, DoPreCal);\n\n\t\t\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t("Reset EEPROM 0x52[2] bit, Let FW do On-line Calibration\\n"));\n\t\t\t\t\t}\n\t\t\t\t}\n\n\t\t\t\tif (ret_cal_data == NDIS_STATUS_SUCCESS)\n\t\t\t\t\tret = MtCmdPreCalReStoreProc(pAd, (INT32 *)pAd->PreCalReStoreBuffer);\n\t\t\t}\n\t\t}\n\t} else {\n\t\t/* Force Erase DoPreCal bit for any mode other than Bin & Flash*/\n\t\tDoPreCal &= ~(1 << 2);\n\t\tRT28xx_EEPROM_WRITE16(pAd, 0x52, DoPreCal);\n\t}\n#endif /* PRE_CAL_TRX_SET2_SUPPORT */\n\n#if defined(CAL_BIN_FILE_SUPPORT) && defined(MT7615)\n\tif (IS_MT7615(pAd)) {\n\t\t/* Check DoPATrim bits */\n\t\tRT28xx_EEPROM_READ16(pAd, 0x52, DoPATrim);\n\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t\t("\\x1b[34m%s: EEPROM 0x52 %x\\x1b[m\\n", __func__, DoPATrim));\n\n\t\t/* Restore PA data when EEPROM 0x52[3]=1 */\n\t\tif (DoPATrim & (1 << 3)) {\n\t\t\tINT32 Status = NDIS_STATUS_FAILURE;\n\n\t\t\tStatus = MtCmdCalReStoreFromFileProc(pAd, CAL_RESTORE_PA_TRIM);\n\n\t\t\tif (Status != NDIS_STATUS_SUCCESS) {\n\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t("\\x1b[41m%s : Fail to restore PA data!!\\x1b[m\\n", __func__));\n\t\t\t}\n\t\t}\n\t}\n#endif /* CAL_BIN_FILE_SUPPORT */\n\n\n#ifdef MT_DFS_SUPPORT\t/*Dynamically enable or disable DFS calibration in firmware. Must be performed before power on calibration*/\n\tDfsSetCalibration(pAd, pAd->CommonCfg.DfsParameter.DisableDfsCal);\n#endif\n#ifdef MT_MAC\n#if defined(MT7603) || defined(MT7628) || defined(MT7636) || defined(MT7615) || defined(MT7637) || defined(MT7622)\n\t/*Send EEprom parameter to FW*/\n#ifdef CONFIG_ATE\n\n\tif (!ATE_ON(pAd))\n#endif\n\t{\n\t\t/*configure PA/LNA setting by efuse*/\n\t\tchip_pa_lna_set(pAd, pAd->EEPROMImage);\n\t\t/*configure TSSI sestting by efuse*/\n\t\tchip_tssi_set(pAd, pAd->EEPROMImage);\n\t\tif (IS_MT7603(pAd) || IS_MT7628(pAd) || IS_MT7636(pAd) || IS_MT7615(pAd) || IS_MT7637(pAd) || IS_MT7622(pAd))\n\t\t\tMtCmdEfusBufferModeSet(pAd, pAd->eeprom_type);\n\t}\n\n#endif /*#if defined(MT7603)||defined(MT7628)||defined(MT7636))||defined(MT7615)||defined(MT7622)*/\n#endif /* MT_MAC */\n\t/* Read MAC setting from EEPROM and record as permanent MAC address */\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Initialize MAC Address from E2PROM\\n"));\n\tRT28xx_EEPROM_READ16(pAd, 0x04, Addr01);\n\tRT28xx_EEPROM_READ16(pAd, 0x06, Addr23);\n\tRT28xx_EEPROM_READ16(pAd, 0x08, Addr45);\n\tpAd->PermanentAddress[0] = (UCHAR)(Addr01 & 0xff);\n\tpAd->PermanentAddress[1] = (UCHAR)(Addr01 >> 8);\n\tpAd->PermanentAddress[2] = (UCHAR)(Addr23 & 0xff);\n\tpAd->PermanentAddress[3] = (UCHAR)(Addr23 >> 8);\n\tpAd->PermanentAddress[4] = (UCHAR)(Addr45 & 0xff);\n\tpAd->PermanentAddress[5] = (UCHAR)(Addr45 >> 8);\n\n\t/*more conveninet to test mbssid, so ap\'s bssid &0xf1*/\n\tif (pAd->PermanentAddress[0] == 0xff)\n\t\tpAd->PermanentAddress[0] = RandomByte(pAd) & 0xf8;\n\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("E2PROM MAC: =%02x:%02x:%02x:%02x:%02x:%02x\\n",\n\t\t\t PRINT_MAC(pAd->PermanentAddress)));\n\n\t/* Assign the actually working MAC Address */\n\tif (pAd->bLocalAdminMAC) {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t ("Use the MAC address what is assigned from Configuration file(.dat).\\n"));\n#if defined(BB_SOC) && !defined(NEW_MBSSID_MODE)\n\t\t/* BBUPrepareMAC(pAd, pAd->CurrentAddress); */\n\t\tCOPY_MAC_ADDR(pAd->PermanentAddress, pAd->CurrentAddress);\n\t\tprintk("now bb MainSsid mac %02x:%02x:%02x:%02x:%02x:%02x\\n", PRINT_MAC(pAd->CurrentAddress));\n#endif\n\t} else if (mac_addr &&\n\t\t\t   strlen((RTMP_STRING *)mac_addr) == 17 &&\n\t\t\t   (strcmp(mac_addr, "00:00:00:00:00:00") != 0)) {\n\t\tINT j;\n\t\tRTMP_STRING *macptr;\n\t\tmacptr = (RTMP_STRING *) mac_addr;\n\n\t\tfor (j = 0; j < MAC_ADDR_LEN; j++) {\n\t\t\tAtoH(macptr, &pAd->CurrentAddress[j], 1);\n\t\t\tmacptr = macptr + 3;\n\t\t}\n\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Use the MAC address what is assigned from Moudle Parameter.\\n"));\n\t} else {\n\t\tCOPY_MAC_ADDR(pAd->CurrentAddress, pAd->PermanentAddress);\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Use the MAC address what is assigned from EEPROM.\\n"));\n\t}\n\n\t/* if E2PROM version mismatch with driver\'s expectation, then skip*/\n\t/* all subsequent E2RPOM retieval and set a system error bit to notify GUI*/\n\tRT28xx_EEPROM_READ16(pAd, EEPROM_VERSION_OFFSET, Version.word);\n\tpAd->EepromVersion = Version.field.Version + Version.field.FaeReleaseNumber * 256;\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("E2PROM: Version = %d, FAE release #%d\\n", Version.field.Version,\n\t\t\t Version.field.FaeReleaseNumber));\n\t/* Read BBP default value from EEPROM and store to array(EEPROMDefaultValue) in pAd */\n\tRT28xx_EEPROM_READ16(pAd, EEPROM_NIC1_OFFSET, value);\n\tpAd->EEPROMDefaultValue[EEPROM_NIC_CFG1_OFFSET] = value;\n\t/* EEPROM offset 0x36 - NIC Configuration 1 */\n\tRT28xx_EEPROM_READ16(pAd, EEPROM_NIC2_OFFSET, value);\n\tpAd->EEPROMDefaultValue[EEPROM_NIC_CFG2_OFFSET] = value;\n\tNicConfig2.word = pAd->EEPROMDefaultValue[EEPROM_NIC_CFG2_OFFSET];\n\t{\n\t\tRT28xx_EEPROM_READ16(pAd, EEPROM_COUNTRY_REGION, value);\t/* Country Region*/\n\t\tpAd->EEPROMDefaultValue[EEPROM_COUNTRY_REG_OFFSET] = value;\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Country Region from e2p = %x\\n", value));\n\t}\n\n\tfor (i = 0; i < 8; i++) {\n#if defined(RLT_MAC) || defined(MT_MAC)\n\n\t\t/* TODO: shiang-MT7603, replace below chip based check to this one!! */\n\t\tif (IS_HIF_TYPE(pAd, HIF_RLT) || IS_HIF_TYPE(pAd, HIF_MT))\n\t\t\tbreak;\n\n#endif /* defined(RLT_MAC) || defined(MT_MAC) */\n\t\tRT28xx_EEPROM_READ16(pAd, EEPROM_BBP_BASE_OFFSET + i * 2, value);\n\t\tpAd->EEPROMDefaultValue[i + EEPROM_BBP_ARRAY_OFFSET] = value;\n\t}\n\n\t/* We have to parse NIC configuration 0 at here. */\n\t/* If TSSI did not have preloaded value, it should reset the TxAutoAgc to false */\n\t/* Therefore, we have to read TxAutoAgc control beforehand. */\n\t/* Read Tx AGC control bit */\n\tAntenna.word = pAd->EEPROMDefaultValue[EEPROM_NIC_CFG1_OFFSET];\n\n\t/* TODO: shiang, why we only check oxff00?? */\n\tif (((Antenna.word & 0xFF00) == 0xFF00))\n\t\t/*\tif (Antenna.word == 0xFFFF)*/\n\t\tRTMP_CHIP_ANTENNA_INFO_DEFAULT_RESET(pAd, &Antenna);\n\n\t/* TODO: shiang-7603 */\n\t/* TODO: shiang-MT7615 */\n\tif (IS_MT7603(pAd) || IS_MT7628(pAd) || IS_MT76x6(pAd) || IS_MT7615(pAd) || IS_MT7637(pAd) || IS_MT7622(pAd) ||\n\t\tIS_P18(pAd) || IS_MT7663(pAd))\n\t\tRTMP_CHIP_ANTENNA_INFO_DEFAULT_RESET(pAd, &Antenna);\n\n#ifdef WSC_INCLUDED\n\n\t/* WSC hardware push button function 0811 */\n#ifdef VENDOR_FEATURE7_SUPPORT\n\tWSC_HDR_BTN_MR_HDR_SUPPORT_SET(pAd, 1);\t\t/* always enable PBC support */\n#else\n\tif ((pAd->MACVersion == 0x28600100) || (pAd->MACVersion == 0x28700100))\n\t\tWSC_HDR_BTN_MR_HDR_SUPPORT_SET(pAd, NicConfig2.field.EnableWPSPBC);\n#endif\n#endif /* WSC_INCLUDED */\n#ifdef CONFIG_AP_SUPPORT\n\tIF_DEV_CONFIG_OPMODE_ON_AP(pAd) {\n\t\tif (NicConfig2.word == 0xffff)\n\t\t\tNicConfig2.word = 0;\n\t}\n#endif /* CONFIG_AP_SUPPORT */\n\n\tif (NicConfig2.field.DynamicTxAgcControl == 1)\n\t\tpAd->bAutoTxAgcA = pAd->bAutoTxAgcG = TRUE;\n\telse\n\t\tpAd->bAutoTxAgcA = pAd->bAutoTxAgcG = FALSE;\n\n\t/* Save value for future using */\n\tpAd->NicConfig2.word = NicConfig2.word;\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s(): RxPath = %d, TxPath = %d, RfIcType = %d\\n",\n\t\t\t __func__, Antenna.field.RxPath, Antenna.field.TxPath,\n\t\t\t Antenna.field.RfIcType));\n\t/* Save the antenna for future use*/\n\tpAd->Antenna.word = Antenna.word;\n\t/* Set the RfICType here, then we can initialize RFIC related operation callbacks*/\n\tpAd->Mlme.RealRxPath = (UCHAR) Antenna.field.RxPath;\n\tpAd->RfIcType = (UCHAR) Antenna.field.RfIcType;\n#ifdef MT7615\n\n\t/* TODO: shiang-MT7615 */\n\tif (IS_MT7615(pAd)) {\n\t\tPOS_COOKIE pObj = (POS_COOKIE) pAd->OS_Cookie;\n\n\t\tif (pObj->DeviceID == NIC7611_PCIe_DEVICE_ID)\n\t\t\tpAd->RfIcType = RFIC_7611;\n\t\telse if (pObj->DeviceID == NIC761A_PCIe_DEVICE_ID)\n\t\t\tpAd->RfIcType = RFIC_7615A;\n\t\telse\n\t\t\tpAd->RfIcType = RFIC_7615;\n\t}\n\n#endif /* MT7615 */\n#ifdef MT7622\n\n\tif (IS_MT7622(pAd))\n\t\tpAd->RfIcType = RFIC_7622;\n\n#endif /* MT7622 */\n\n\t/* TODO: shiang-MT7615, how about the EEPROM value of MT series chip?? */\n\tif (!IS_MT7615(pAd) && !IS_MT7622(pAd) && !IS_P18(pAd) && !IS_MT7663(pAd)) {\n\t\tLoadTssiInfoFromEEPROM(pAd);\n\t\tpAd->BbpRssiToDbmDelta = 0x0;\n\t\trtmp_read_freq_offset_from_eeprom(pAd);\n\t\trtmp_read_country_region_from_eeporm(pAd);\n\t\trtmp_read_rssi_langain_from_eeprom(pAd);\n\t}\n\n#ifdef LED_CONTROL_SUPPORT\n\trtmp_read_led_setting_from_eeprom(pAd);\n#endif /* LED_CONTROL_SUPPORT */\n\trtmp_read_txpwr_from_eeprom(pAd);\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s: pAd->Antenna.field.BoardType = %d\\n",\n\t\t\t __func__,\n\t\t\t pAd->Antenna.field.BoardType));\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("<--%s()\\n", __func__));\n\treturn TRUE;\n}', 'WfEPROMSysInit': 'INT32 WfEPROMSysInit(RTMP_ADAPTER *pAd)\n{\n\tUCHAR RfIC;\n\t/* hook e2p operation */\n\tRtmpChipOpsEepromHook(pAd, pAd->infType, E2P_NONE);\n\t/* We should read EEPROM for all cases */\n\t/* TODO: shiang-7603, revise this! */\n\tNICReadEEPROMParameters(pAd, (RTMP_STRING *)mac);\n\tHcRadioInit(pAd, pAd->RfIcType, pAd->CommonCfg.dbdc_mode);\n\t/* +++Add by shiang for debug */\n\tRfIC = HcGetRadioRfIC(pAd);\n\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t ("%s():PhyCtrl=>RfIcType/rf_band_cap = 0x%x/0x%x\\n",\n\t\t\t  __func__, pAd->RfIcType, RfIC));\n\tRTMP_NET_DEV_NICKNAME_INIT(pAd);\n\treturn NDIS_STATUS_SUCCESS;\n}', 'WfEPROMInit': 'INT32 WfEPROMInit(RTMP_ADAPTER *pAd)\n{\n\tINT32 ret = NDIS_STATUS_SUCCESS;\n\t/* #if  defined(COMPOS_WIN) || defined (COMPOS_TESTMODE_WIN) */\n#if  defined(COMPOS_TESTMODE_WIN)\n#else\n\tret = WfEPROMSysInit(pAd);\n\n\tif (ret != NDIS_STATUS_SUCCESS)\n\t\tgoto err;\n\n\tWfEPROMHwInit(pAd);\n\treturn ret;\nerr:\n\tWfEPROMSysExit(pAd);\n#endif\n\treturn ret;\n}', 'ate_pci_ate_leave': 'static INT32 pci_ate_leave(RTMP_ADAPTER *pAd)\n{\n\tstruct _ATE_CTRL *ATECtrl = &pAd->ATECtrl;\n\tUINT32 Index;\n\tTXD_STRUC *pTxD = NULL;\n\tRTMP_TX_RING *pTxRing = &pAd->PciHif.TxRing[QID_AC_BE];\n#ifdef RT_BIG_ENDIAN\n\tTXD_STRUC *pDestTxD = NULL;\n\tUCHAR tx_hw_info[TXD_SIZE];\n#endif /* RT_BIG_ENDIAN */\n\n\tMTWF_LOG(DBG_CAT_TEST,  DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s -->,\\n", __func__));\n\tNICReadEEPROMParameters(pAd, NULL);\n\tNICInitAsicFromEEPROM(pAd);\n\n\tif (ATECtrl->allocated == 1) {\n\t\t/*  Disable PDMA */\n\t\tAsicSetWPDMA(pAd, PDMA_TX_RX, 0);\n\n\t\tfor (Index = 0; Index < TX_RING_SIZE; Index++) {\n\t\t\tPNDIS_PACKET pPacket;\n#ifndef RT_BIG_ENDIAN\n\t\t\tpTxD = (TXD_STRUC *)pAd->PciHif.TxRing[QID_AC_BE].Cell[Index].AllocVa;\n#else\n\t\t\tpDestTxD = (TXD_STRUC *)pAd->TxRing[QID_AC_BE].Cell[Index].AllocVa;\n\t\t\tNdisMoveMemory(&tx_hw_info[0], (UCHAR *)pDestTxD, TXD_SIZE);\n\t\t\tpTxD = (TXD_STRUC *)&tx_hw_info[0];\n\t\t\tRTMPDescriptorEndianChange((PUCHAR)pTxD, TYPE_TXD);\n#endif /* !RT_BIG_ENDIAN */\n\t\t\tpTxD->DMADONE = 0;\n\t\t\tpPacket = pTxRing->Cell[Index].pNdisPacket;\n\n\t\t\tif (pPacket) {\n\t\t\t\tPCI_UNMAP_SINGLE(pAd, pTxD->SDPtr0, pTxD->SDLen0, RTMP_PCI_DMA_TODEVICE);\n\t\t\t\tRELEASE_NDIS_PACKET(pAd, pPacket, NDIS_STATUS_SUCCESS);\n\t\t\t}\n\n\t\t\t/* Always assign pNdisPacket as NULL after clear */\n\t\t\tpTxRing->Cell[Index].pNdisPacket = NULL;\n\t\t\tpPacket = pTxRing->Cell[Index].pNextNdisPacket;\n\n\t\t\tif (pPacket) {\n\t\t\t\tPCI_UNMAP_SINGLE(pAd, pTxD->SDPtr1, pTxD->SDLen1, RTMP_PCI_DMA_TODEVICE);\n\t\t\t\tRELEASE_NDIS_PACKET(pAd, pPacket, NDIS_STATUS_SUCCESS);\n\t\t\t}\n\n\t\t\t/* Always assign pNextNdisPacket as NULL after clear */\n\t\t\tpTxRing->Cell[Index].pNextNdisPacket = NULL;\n#ifdef RT_BIG_ENDIAN\n\t\t\tRTMPDescriptorEndianChange((PUCHAR)pTxD, TYPE_TXD);\n\t\t\tWriteBackToDescriptor((PUCHAR)pDestTxD, (PUCHAR)pTxD, FALSE, TYPE_TXD);\n#endif /* RT_BIG_ENDIAN */\n\t\t}\n\n\t\tATECtrl->allocated = 0;\n\t}\n\n\treturn NDIS_STATUS_SUCCESS;\n}', 'testmode_pci_ate_leave': 'static INT32 pci_ate_leave(RTMP_ADAPTER *pAd)\n{\n\tstruct _ATE_CTRL *ATECtrl = &pAd->ATECtrl;\n\tMTWF_LOG(DBG_CAT_TEST,  DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s\\n", __func__));\n\tNICReadEEPROMParameters(pAd, NULL);\n\tNICInitAsicFromEEPROM(pAd);\n\n\tif (ATECtrl->pate_pkt) {\n\t\tos_free_mem(ATECtrl->pate_pkt);\n\t\tATECtrl->pate_pkt = NULL;\n\t}\n\n\treturn NDIS_STATUS_SUCCESS;\n}'}
BASELINE_FUNCTIONS_SHA256 = {'RtmpFlashRead': 'b96e7a2abf27c7e1514a565f9a403ba400aef554b97e3026dddc5c3c0a8e04ba', 'RtmpFlashWrite': 'd065c4742e7f51e52a14233a3ceb9f56e78ffdc131a18817737a1e7f194e6565', 'rtmp_ee_flash_read': 'ec5f0eb4733323b8bbf6a7f940a7abde85e8286c163a4c500cbe2a653e50ab25', 'validFlashEepromID': 'f5752b55e5ca32e5ec0aea05b532f4451c1a15b6833f28c0c4e084bea1aefabd', 'rtmp_ee_flash_write_all': '9db48e528f4dd8c76c78cb1bdb7aa1d9c01055139c6e2ae7c633c21c42745792', 'rtmp_ee_flash_init': '882d236f06220b19b36077449d8f424a7cec1ada4070a5cc7790e886957775f8', 'rtmp_nv_init': '82a88be3758713dc0857a2340fd4383611988d929f6d72137213a483cc219b8c', 'NICReadEEPROMParameters': 'fb5a31fd0ab052c9cb7af69e4973df830a5d3a616914e918073fa04dfbf1f020', 'WfEPROMSysInit': '78ecfb7a56c79b1a90a01fd22c4402854e91c2476756375a5208507b29bb6d97', 'WfEPROMInit': '95d3ae4458f93a61a7c807115098e5f94ea44289919db30a80b6b430c4993799', 'ate_pci_ate_leave': 'fed2202de2727e59a770702a40400bf7ac9bed7752749f9559095b099dcf3675', 'testmode_pci_ate_leave': '184f002656ddb2c452b9f0d5ff956fa83434d0155bc5bed28bace5428dfb369b'}
BASELINE_FUNCTIONS['rtmp_ee_flash_reset'] = 'static NDIS_STATUS rtmp_ee_flash_reset(RTMP_ADAPTER *pAd, UCHAR *start)\n{\n\tPUCHAR src;\n\tRTMP_OS_FS_INFO osFsInfo;\n\tRTMP_OS_FD srcf;\n\tINT retval;\n\tEEPROM_CONTROL *pE2pCtrl = &pAd->E2pCtrl;\n\tstruct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);\n#ifdef RT_SOC_SUPPORT\n#ifdef MULTIPLE_CARD_SUPPORT\n\tRTMP_STRING BinFilePath[128];\n\tRTMP_STRING *pBinFileName = NULL;\n\tUINT32\tChipVerion = (pAd->MACVersion >> 16);\n\n\tif (rtmp_get_default_bin_file_by_chip(pAd, ChipVerion, &pBinFileName) == TRUE) {\n\t\tif (pAd->MC_RowID > 0)\n\t\t\tsprintf(BinFilePath, "%s%s", EEPROM_2ND_FILE_DIR, pBinFileName);\n\t\telse\n\t\t\tsprintf(BinFilePath, "%s%s", EEPROM_1ST_FILE_DIR, pBinFileName);\n\n\t\tsrc = BinFilePath;\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s(): src = %s\\n", __func__, src));\n\t} else\n#endif /* MULTIPLE_CARD_SUPPORT */\n#endif /* RT_SOC_SUPPORT */\n\t{\n#if defined(MT_MAC) && defined(MT7603)\n\n\t\tif (IS_MT7603(pAd))\n\t\t\tsrc = EEPROM_DEFAULT_7603_FILE_PATH;\n\t\telse\n#endif /* MT_MAC && MT7603 */\n\t\t{\n\t\t\tsrc = EEPROM_DEFAULT_FILE_PATH;\n\t\t}\n\t}\n\n\tpE2pCtrl->e2pSource = E2P_SRC_FROM_BIN;\n\tRtmpOSFSInfoChange(&osFsInfo, TRUE);\n\n\tif (src && *src) {\n\t\tsrcf = RtmpOSFileOpen(src, O_RDONLY, 0);\n\n\t\tif (IS_FILE_OPEN_ERR(srcf)) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t ("--> Error opening file %s\\n", src));\n\n\t\t\tif (cap->EEPROM_DEFAULT_BIN != NULL) {\n\t\t\t\tNdisMoveMemory(start, cap->EEPROM_DEFAULT_BIN,\n\t\t\t\t\t\t\t   cap->EEPROM_DEFAULT_BIN_SIZE > MAX_EEPROM_BUFFER_SIZE ? MAX_EEPROM_BUFFER_SIZE : cap->EEPROM_DEFAULT_BIN_SIZE);\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("Load EEPROM Buffer from default BIN.\\n"));\n\t\t\t\tpE2pCtrl->BinSource = "Default bin";\n\t\t\t\treturn NDIS_STATUS_SUCCESS;\n\t\t\t} else\n\t\t\t\treturn NDIS_STATUS_FAILURE;\n\t\t} else {\n\t\t\t/* The object must have a read method*/\n\t\t\tNdisZeroMemory(start, EEPROM_SIZE);\n\t\t\tretval = RtmpOSFileRead(srcf, start, EEPROM_SIZE);\n\n\t\t\tif (retval < 0) {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("--> Read %s error %d\\n", src, -retval));\n\t\t\t} else {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t\t\t ("--> rtmp_ee_flash_reset copy %s to eeprom buffer\\n", src));\n\t\t\t\tpE2pCtrl->BinSource = src;\n\t\t\t}\n\n\t\t\tretval = RtmpOSFileClose(srcf);\n\n\t\t\tif (retval) {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("--> Error %d closing %s\\n", -retval, src));\n\t\t\t}\n\t\t}\n\t}\n\n\tRtmpOSFSInfoChange(&osFsInfo, FALSE);\n\treturn NDIS_STATUS_SUCCESS;\n}'
BASELINE_FUNCTIONS_SHA256['rtmp_ee_flash_reset'] = 'e9b4287e72481a0743d14146380161f4c0061b32db0a75f05307f43e2bfdf3c8'
