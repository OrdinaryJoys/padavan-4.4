"""Pure whole-function EEPROM BIN/diagnostic variant adapter, RAM IO only.

No file, MTD, credential, router, or radio operation occurs on import or in C.
1024-byte buffers match production BIN bounds; calibration lengths scale to 8. Multicard
selection is enabled in this diagnostic variant; normal lookup selects the
configured-path branch. The native suite also compiles macros-off K2P cases.
"""
import hashlib
import json
import re

BASELINE_COMMIT='3a404e1675467cab79af0ffac454061c1e9150ae'
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'eeprom':BASE+'embedded/common/eeprom.c','flash':BASE+'embedded/common/ee_flash.c',
 'efuse':BASE+'embedded/common/ee_efuse.c','os':BASE+'os/linux/rt_linux.c',
 'os_header':BASE+'embedded/include/rt_os_util.h','eeprom_header':BASE+'embedded/include/eeprom.h',
 'adapter_header':BASE+'embedded/include/rtmp.h','l1_profile':'trunk/configs/boards/K2P/l1profile.dat',
 'ate':BASE+'ate/mt_mac/mt_testmode.c'}
FUNCTION_SOURCES={
 'RtmpOSFileClose':'os','RtmpOSFileCloseChecked':'os','rtmp_ee_bin_capacity':'eeprom',
 'rtmp_ee_bin_read16':'eeprom','rtmp_ee_bin_write16':'eeprom',
 'rtmp_ee_bin_read_with_range':'eeprom','rtmp_ee_bin_write_with_range':'eeprom',
 'rtmp_ee_load_from_bin':'eeprom','rtmp_ee_write_to_bin':'eeprom','rtmp_ee_bin_init':'eeprom',
 'Set_LoadEepromBufferFromBin_Proc':'eeprom','Set_EepromBufferWriteBack_Proc':'eeprom',
 'rtmp_ee_flash_reset':'flash','eFuse_init':'efuse','MtATE_Pre_Cal_Proc':'ate'}
BODY_ORDER=tuple(FUNCTION_SOURCES)
NEW_FUNCTIONS=('RtmpOSFileCloseChecked','rtmp_ee_bin_capacity')
CASE_NAMES=(
 'load-ok','load-zero','load-short','load-read-error','load-close-error',
 'load-open-cache','load-open-no-cache','load-open-short-cache','load-empty-path-cache',
 'load-null-image','load-small-profile','load-allocation-error',
 'load-multicard-first','load-multicard-second','load-multicard-fallback',
 'load-multicard-long-name','load-multicard-null-name',
 'write-ok','write-zero','write-short','write-io-error','write-close-error','write-open-error',
 'write-empty-path','write-null-image','write-small-profile','write-multicard-long-name',
 'set-load-ok','set-load-read-error','set-load-open-cache','set-load-hook-error',
 'set-write-ok','set-write-io-error',
 'word-read-ok','word-read-last','word-read-overflow','word-read-null-value',
 'word-write-ok','word-write-last','word-write-overflow',
 'range-read-ok','range-read-overflow','range-read-null-buffer','range-read-zero',
 'range-write-ok','range-write-overflow','range-write-null-buffer','range-write-zero',
 'init-ok','init-read-error','init-allocation-dcoc','init-allocation-dpd1','init-allocation-dpd2',
 'init-reuse','init-reuse-partial-failure','init-repeat',
 'efuse-ok','efuse-read-error','efuse-open-no-cache','efuse-nonempty','efuse-hook-error',
 'reset-multicard-first','reset-multicard-second','reset-multicard-long-name',
 'init-cal-dcoc-error','init-cal-dpd1-error','init-cal-dpd2-error',
 'set-load-allocation-dcoc','set-load-allocation-dpd1','set-load-allocation-dpd2',
 'set-load-nic-missing','set-load-negative','set-load-repeat',
 'set-load-cal-dcoc-error','set-load-cal-dpd1-error','set-load-cal-dpd2-error',
 'efuse-allocation-dcoc','efuse-allocation-dpd1','efuse-allocation-dpd2',
 'efuse-nic-missing','efuse-repeat',
 'efuse-cal-dcoc-error','efuse-cal-dpd1-error','efuse-cal-dpd2-error',
 'precal-flash-ok','precal-flash-last-group','precal-flash-short','precal-flash-offset-overflow',
 'precal-flash-null-image','precal-flash-nic-missing','precal-flash-mode-mismatch',
 'precal-unsupported-mode','precal-invalid-cal','precal-invalid-group',
 'precal-bin-ok','precal-bin-repeat','precal-bin-allocation-error','precal-bin-command-error',
 'precal-bin-reuse-command-error','precal-flash-command-error',
 'set-load-precal-alias','init-precal-alias','efuse-precal-alias',
 'set-load-precal-owned','init-precal-owned',
)
BASELINE_CASES=(
 'load-ok','load-zero','load-short','load-read-error','load-close-error',
 'load-open-cache','load-open-no-cache','load-open-short-cache','load-empty-path-cache',
 'write-ok','write-zero','write-short','write-io-error','write-close-error','write-open-error','write-empty-path',
 'set-load-ok','set-load-read-error','set-load-open-cache','set-load-hook-error',
 'set-write-ok','set-write-io-error','word-read-ok','word-read-last','word-write-ok','word-write-last',
 'range-read-ok','range-write-ok','init-ok','init-read-error','init-repeat',
 'efuse-ok','efuse-read-error','efuse-open-no-cache','efuse-nonempty','efuse-hook-error',
 'init-cal-dcoc-error','init-cal-dpd1-error','init-cal-dpd2-error',
 'precal-flash-ok','precal-flash-short','precal-bin-ok','precal-bin-repeat',
 'precal-bin-command-error','precal-bin-allocation-error',
)
DISABLED_CASES=('load-ok','write-ok','precal-bin-ok')


def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'^(?:static\s+)?(?:void|int|INT|UINT|BOOLEAN|NDIS_STATUS)\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked,re.M))
    if len(matches)!=1:raise ValueError('Missing/ambiguous BIN function '+name)
    start=matches[0].start();opening=text.index('{',start);depth=0
    for item in re.finditer(tokens+r'|[{}]',text[opening:]):
        if item.group()=='{':depth+=1
        elif item.group()=='}':
            depth-=1
            if not depth:return text[start:opening+item.end()]
    raise ValueError('Unterminated BIN function '+name)


def actual_functions(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact BIN source keys required')
    return {name:{'source':key,'body':function(texts[key],name)}for name,key in FUNCTION_SOURCES.items()}


def precal_declarations(text):
    arrays=[]
    for kind,name in [('UINT16','PreCalGroupList'),('UINT8','PreCalItemList')]:
        matches=re.findall(r'static '+kind+r' '+name+r'\[\] = \{[^{}]*\};',text)
        if len(matches)!=1:raise ValueError('Missing/ambiguous pre-calibration lookup '+name)
        arrays.append(matches[0])
    return '\n'.join(arrays)


PREFIX=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Preserve old unbounded formatting semantics without SDK deprecation tags. */
#undef sprintf
#define sprintf __builtin_sprintf
#define IN
#define OUT
#define RT_SOC_SUPPORT 1
#define MULTIPLE_CARD_SUPPORT 1
#define PRE_CAL_TRX_SET1_SUPPORT 1
#define PRE_CAL_TRX_SET2_SUPPORT 1
#define RTMP_FLASH_SUPPORT 1
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define MAX_EEPROM_BUFFER_SIZE 1024
#define MAX_EEPROM_BIN_FILE_SIZE 1024
#define EEPROM_SIZE 1024
#define DCOC_IMAGE_SIZE 8
#define TXDPD_IMAGE1_SIZE 8
#define TXDPD_IMAGE2_SIZE 8
#define DPDPART1_OFFSET 8
#define DPDPART2_OFFSET 16
#define PRECALPART_OFFSET 32
#define PRE_CAL_SIZE_ONE_CARD 16
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define E2P_NONE 0
#define E2P_EFUSE_MODE 1
#define E2P_FLASH_MODE 2
#define E2P_EEPROM_MODE 3
#define E2P_BIN_MODE 4
#define NUM_OF_E2P_MODE 5
#define E2P_SRC_FROM_FLASH 2
#define E2P_SRC_FROM_EFUSE 1
#define E2P_SRC_FROM_BIN 8
#define O_RDONLY 0
#define O_WRONLY 1
#define O_CREAT 64
#define IS_FILE_OPEN_ERR(fd) ((fd)<0)
#define BIN_FILE_PATH default_path
#define EEPROM_DEFAULT_FILE_PATH default_path
#define EEPROM_1ST_FILE_DIR "/inert/first/"
#define EEPROM_2ND_FILE_DIR "/inert/second/"
#define MTWF_LOG(a,b,c,args) do{if(0)printf args;}while(0)
#define printk(...) ((void)0)
#define NdisMoveMemory(p,s,n) memcpy(p,s,n)
#define NdisZeroMemory(p,n) memset(p,0,n)
#define le2cpu16(x) (x)
typedef unsigned char UCHAR;
typedef unsigned char UINT8;
typedef int INT32;
typedef unsigned short UINT16;
typedef unsigned short USHORT;
typedef unsigned int UINT;
typedef unsigned int UINT32;
typedef int INT;
typedef long LONG;
typedef int BOOLEAN;
typedef int NDIS_STATUS;
typedef char RTMP_STRING;
typedef char*PUCHAR;
typedef int RTMP_OS_FD;
typedef struct {int previous;} RTMP_OS_FS_INFO;
typedef struct {int e2pCurMode,e2pSource;char*BinSource;} EEPROM_CONTROL;
struct _RTMP_CHIP_CAP {UCHAR*EEPROM_DEFAULT_BIN;UINT EEPROM_DEFAULT_BIN_SIZE;char*EEPROM_DEFAULT_BIN_FILE;UINT EFUSE_RESERVED_SIZE,EFUSE_USAGE_MAP_SIZE,EFUSE_USAGE_MAP_START,EFUSE_USAGE_MAP_END;int ee_inited;};
typedef struct _RTMP_ADAPTER {UCHAR*EEPROMImage,*CalDCOCImage,*CalDPDAPart1Image,*CalDPDAPart2Image,*PreCalStoreBuffer,*PreCalReStoreBuffer;UINT16 PreCalWriteOffSet,ChGrpMap;int bDCOCReloaded,bDPDReloaded,bUseEfuse,infType,E2pAccessMode,MC_RowID;UINT MACVersion;void*hdev_ctrl;EEPROM_CONTROL E2pCtrl;} RTMP_ADAPTER,*PRTMP_ADAPTER;
PRECAL_DECLARATIONS
static const char*case_name;
static struct _RTMP_CHIP_CAP cap;
static char*default_path="/inert/eeprom.bin";
static char long_name[180];
static UCHAR cache[1536];
static UINT profile_size=1024;
static int fsdepth,opens,reads,writes,closes,doubleclose,file_alive,allocs,frees_count,live_allocs,hook_calls,cal_allocs;
static void*owned[32];
static char trace[1024];
static int is(const char*n){return !strcmp(case_name,n);}
static int has(const char*n){return strstr(case_name,n)!=NULL;}
#define fRTMP_ADAPTER_NIC_NOT_EXIST 1
#define RTMP_TEST_FLAG(p,f) (has("nic-missing"))
static int callback_mode=E2P_FLASH_MODE;
static int precal_allocs,precal_commands,precal_item,precal_group;
static void event(const char*s){if(strlen(trace)+strlen(s)+2>=sizeof(trace))abort();if(*trace)strcat(trace,",");strcat(trace,s);}
static struct _RTMP_CHIP_CAP*hc_get_chip_cap(void*h){(void)h;return &cap;}
static UINT get_dev_eeprom_size(void*p){(void)p;return profile_size;}
static int os_alloc_mem(RTMP_ADAPTER*a,UCHAR**out,size_t len){int i,fail=0;(void)a;allocs++;event("alloc");
 if(len==8){cal_allocs++;fail=(has("allocation-dcoc")&&cal_allocs==1)||(has("allocation-dpd1")&&cal_allocs==2)||(has("allocation-dpd2")&&cal_allocs==3)||(has("reuse-partial-failure")&&cal_allocs==1);}
 if(len==PRE_CAL_SIZE_ONE_CARD){precal_allocs++;if(is("precal-bin-allocation-error"))fail=1;}
 if(has("load-allocation-error")&&len==MAX_EEPROM_BIN_FILE_SIZE)fail=1;
 *out=fail?NULL:malloc(len);if(!*out)return 1;
 memset(*out,0xcc,len);for(i=0;i<32;i++)if(!owned[i]){owned[i]=*out;live_allocs++;return 0;}abort();}
static void os_free_mem(void*p){int i;if(!p)return;for(i=0;i<32;i++)if(owned[i]==p){owned[i]=NULL;live_allocs--;frees_count++;event("free");free(p);return;}abort();}
static int calibration_owned(void*p){int i;for(i=0;i<32;i++)if(p&&owned[i]==p)return 1;return 0;}
static void RtmpOSFSInfoChange(RTMP_OS_FS_INFO*info,BOOLEAN enter){if(enter){info->previous=fsdepth;fsdepth++;event("fs-enter");}else{fsdepth=info->previous;event("fs-restore");}}
static RTMP_OS_FD RtmpOSFileOpen(char*path,int flags,int mode){(void)path;(void)flags;(void)mode;opens++;event("open");if(has("open-")||is("write-open-error"))return -2;file_alive=1;return 1;}
static INT RtmpOSFileRead(RTMP_OS_FD fd,void*data,INT len){UCHAR*buf=data;int i,n=len;(void)fd;reads++;event("read");if(has("read-error"))return -5;if(has("zero"))n=0;if(has("short"))n=len/2;for(i=0;i<n;i++)buf[i]=(UCHAR)(0xa0+i);if((has("init-cal-")||has("set-load-")||has("efuse-"))&&n>0x53){buf[0x52]=3;buf[0x53]=0;}return n;}
static INT RtmpOSFileWrite(RTMP_OS_FD fd,char*buf,INT len){(void)fd;(void)buf;writes++;event("write");if(has("io-error"))return -5;if(has("zero"))return 0;if(has("short"))return len/2;return len;}
static int filp_close(RTMP_OS_FD fd,void*unused){(void)fd;(void)unused;closes++;event("close");if(!file_alive)doubleclose++;file_alive=0;return has("close-error")?-5:0;}
static BOOLEAN rtmp_get_default_bin_file_by_chip(RTMP_ADAPTER*p,UINT32 v,char**name){(void)p;(void)v;if(!has("multicard")||has("fallback"))return FALSE;*name=has("long-name")?long_name:has("null-name")?NULL:"chip.bin";return TRUE;}
static LONG os_str_tol(const char*s,void*end,int base){(void)end;return strtol(s,NULL,base);}
static int RtmpChipOpsEepromHook(RTMP_ADAPTER*p,int type,int mode){(void)p;(void)type;hook_calls++;event("hook");if(has("hook-error"))return -1;callback_mode=mode;return 0;}
static NDIS_STATUS rtmp_cal_load_from_bin(RTMP_ADAPTER*p,UCHAR*buf,unsigned long off,unsigned long len){(void)p;event("cal-read");if((has("cal-dcoc-error")&&off==0)||(has("cal-dpd1-error")&&off==DPDPART1_OFFSET)||(has("cal-dpd2-error")&&off==DPDPART2_OFFSET))return NDIS_STATUS_FAILURE;memset(buf,0xa5,len);return NDIS_STATUS_SUCCESS;}
static void rtmp_ee_flash_write_all(RTMP_ADAPTER*p){(void)p;event("other-flash-write");}
static void rtmp_ee_write_to_efuse(RTMP_ADAPTER*p){(void)p;event("other-efuse-write");}
static void rtmp_ee_write_to_prom(RTMP_ADAPTER*p){(void)p;event("other-prom-write");}
static void eFuseGetFreeBlockCount(RTMP_ADAPTER*p,UINT*n){(void)p;*n=is("efuse-nonempty")?0:2;}
static void rtmp_ee_load_from_efuse(RTMP_ADAPTER*p){(void)p;event("efuse-read");}
static INT32 MtCmdGetPreCalResult(RTMP_ADAPTER*p,UINT8 item,UINT16 group){(void)p;precal_commands++;precal_item=item;precal_group=group;event("precal-command");return has("command-error")?NDIS_STATUS_FAILURE:NDIS_STATUS_SUCCESS;}
'''

MAIN=r'''
int main(int argc,char**argv){
 RTMP_ADAPTER a;UCHAR image[1024],output[1024],before_image[1024];UINT16 word=0x1234,before_precal_offset,before_precal_group;int status=0,known=0,i,before_access,before_mode,before_source,before_flags,before_callbacks,before_capinit,before_efuse,unchanged,cal_owned,cal_views;UINT offset=2,len=4;UCHAR*buffer=output,*before_dcoc,*before_dpd1,*before_dpd2,*before_precal;
 if(argc!=2)return 90;
 case_name=argv[1];
 CASE_ADMISSION
 if(!known)return 91;
 memset(&a,0,sizeof(a));memset(image,0x55,sizeof(image));memset(output,0x77,sizeof(output));memset(long_name,'z',sizeof(long_name)-1);long_name[sizeof(long_name)-1]=0;
 for(i=0;i<1536;i++)cache[i]=(UCHAR)(0xa0+i);
 a.EEPROMImage=image;a.MACVersion=0x76150000;a.hdev_ctrl=&cap;a.bUseEfuse=1;a.E2pAccessMode=E2P_FLASH_MODE;
 a.E2pCtrl.e2pCurMode=E2P_FLASH_MODE;a.E2pCtrl.e2pSource=E2P_SRC_FROM_FLASH;a.E2pCtrl.BinSource="old-source";
 if(!strncmp(case_name,"efuse-",6)){a.E2pAccessMode=E2P_EFUSE_MODE;a.E2pCtrl.e2pCurMode=E2P_EFUSE_MODE;a.E2pCtrl.e2pSource=E2P_SRC_FROM_EFUSE;callback_mode=E2P_EFUSE_MODE;}
#ifdef PRE_CAL_TRX_SET1_SUPPORT
 if(!strncmp(case_name,"set-load-",9)){a.CalDCOCImage=image+8;a.CalDPDAPart1Image=image+16;a.CalDPDAPart2Image=image+24;a.bDCOCReloaded=a.bDPDReloaded=TRUE;}
#endif
 if(has("set-load-")||has("efuse-")){cache[0x52]=3;cache[0x53]=0;}
 cap.EEPROM_DEFAULT_BIN=cache;cap.EEPROM_DEFAULT_BIN_SIZE=1024;cap.EEPROM_DEFAULT_BIN_FILE=default_path;cap.EFUSE_RESERVED_SIZE=1;cap.ee_inited=1;
 if(has("no-cache"))cap.EEPROM_DEFAULT_BIN=NULL;
 if(has("short-cache"))cap.EEPROM_DEFAULT_BIN_SIZE=2;
 if(has("null-image"))a.EEPROMImage=NULL;
 if(has("small-profile"))profile_size=512;
 if(has("empty-path")){default_path="";cap.EEPROM_DEFAULT_BIN_FILE=default_path;}
 if(has("second"))a.MC_RowID=1;
 if(has("last"))offset=1022;
 if(has("overflow"))offset=1023;
 if(has("null-buffer"))buffer=NULL;
 if(has("range-")&&has("zero")){len=0;buffer=NULL;}
 if(has("reuse")){a.CalDCOCImage=image+8;if(!has("partial-failure")){a.CalDPDAPart1Image=image+16;a.CalDPDAPart2Image=image+24;}}
 if(has("precal-")){a.PreCalWriteOffSet=9;a.ChGrpMap=0xbeef;}
 if(has("precal-bin-")||has("precal-owned")){a.E2pAccessMode=E2P_BIN_MODE;a.E2pCtrl.e2pCurMode=E2P_BIN_MODE;a.E2pCtrl.e2pSource=E2P_SRC_FROM_BIN;callback_mode=E2P_BIN_MODE;a.CalDCOCImage=a.CalDPDAPart1Image=a.CalDPDAPart2Image=NULL;a.bDCOCReloaded=a.bDPDReloaded=FALSE;}
 if(has("precal-alias"))a.PreCalStoreBuffer=image+PRECALPART_OFFSET;
 if(has("precal-owned")||is("precal-bin-reuse-command-error")){if(os_alloc_mem(&a,&a.PreCalStoreBuffer,PRE_CAL_SIZE_ONE_CARD))return 92;}
 if(is("precal-flash-short"))profile_size=PRECALPART_OFFSET+PRE_CAL_SIZE_ONE_CARD-1;
 if(is("precal-flash-offset-overflow"))profile_size=PRECALPART_OFFSET-1;
 if(is("precal-flash-mode-mismatch"))a.E2pCtrl.e2pCurMode=E2P_BIN_MODE;
 if(is("precal-unsupported-mode")){a.E2pAccessMode=E2P_EFUSE_MODE;a.E2pCtrl.e2pCurMode=E2P_EFUSE_MODE;}
 memcpy(before_image,image,sizeof(image));before_access=a.E2pAccessMode;before_mode=a.E2pCtrl.e2pCurMode;before_source=a.E2pCtrl.e2pSource;before_flags=a.bDCOCReloaded+2*a.bDPDReloaded;before_callbacks=callback_mode;before_capinit=cap.ee_inited;before_efuse=a.bUseEfuse;before_dcoc=a.CalDCOCImage;before_dpd1=a.CalDPDAPart1Image;before_dpd2=a.CalDPDAPart2Image;before_precal=a.PreCalStoreBuffer;before_precal_offset=a.PreCalWriteOffSet;before_precal_group=a.ChGrpMap;
 if(!strncmp(case_name,"word-read-",10))status=rtmp_ee_bin_read16(&a,(UINT16)offset,is("word-read-null-value")?NULL:&word);
 else if(!strncmp(case_name,"word-write-",11))status=rtmp_ee_bin_write16(&a,(USHORT)offset,0xa1b2);
 else if(!strncmp(case_name,"range-read-",11))status=rtmp_ee_bin_read_with_range(&a,(UINT16)offset,(UINT16)len,buffer);
 else if(!strncmp(case_name,"range-write-",12))status=rtmp_ee_bin_write_with_range(&a,(USHORT)offset,(USHORT)len,buffer);
 else if(!strncmp(case_name,"precal-",7)){status=MtATE_Pre_Cal_Proc(&a,is("precal-invalid-cal")?1:0,is("precal-invalid-group")?2:is("precal-flash-last-group")?1:0);if(is("precal-bin-repeat")&&status)status=MtATE_Pre_Cal_Proc(&a,0,0);}
 else if(!strncmp(case_name,"set-load-",9)){status=Set_LoadEepromBufferFromBin_Proc(&a,is("set-load-negative")?"-1":"1");if(is("set-load-repeat")&&status)status=Set_LoadEepromBufferFromBin_Proc(&a,"1");}
 else if(!strncmp(case_name,"set-write-",10))status=Set_EepromBufferWriteBack_Proc(&a,"4");
 else if(!strncmp(case_name,"write-",6))status=rtmp_ee_write_to_bin(&a);
 else if(!strncmp(case_name,"init-",5)){status=rtmp_ee_bin_init(&a);if(is("init-repeat")&&!status)status=rtmp_ee_bin_init(&a);}
 else if(!strncmp(case_name,"efuse-",6)){status=eFuse_init(&a);if(is("efuse-repeat")&&!status)status=eFuse_init(&a);}
 else if(!strncmp(case_name,"reset-",6))status=rtmp_ee_flash_reset(&a,image);
 else status=rtmp_ee_load_from_bin(&a);
 unchanged=!memcmp(before_image,image,sizeof(image))&&before_access==a.E2pAccessMode&&before_mode==a.E2pCtrl.e2pCurMode&&before_source==a.E2pCtrl.e2pSource&&before_flags==a.bDCOCReloaded+2*a.bDPDReloaded&&before_callbacks==callback_mode&&before_capinit==cap.ee_inited&&before_efuse==a.bUseEfuse&&before_dcoc==a.CalDCOCImage&&before_dpd1==a.CalDPDAPart1Image&&before_dpd2==a.CalDPDAPart2Image&&before_precal==a.PreCalStoreBuffer&&before_precal_offset==a.PreCalWriteOffSet&&before_precal_group==a.ChGrpMap;
 cal_owned=calibration_owned(a.CalDCOCImage)+2*calibration_owned(a.CalDPDAPart1Image)+4*calibration_owned(a.CalDPDAPart2Image);
 cal_views=(a.CalDCOCImage==image+8)+2*(a.CalDPDAPart1Image==image+16)+4*(a.CalDPDAPart2Image==image+24);
 printf("{\"case\":\"%s\",\"status\":%d,\"fsdepth\":%d,\"opens\":%d,\"reads\":%d,\"writes\":%d,\"closes\":%d,\"doubleclose\":%d,\"allocs\":%d,\"frees\":%d,\"live_allocs\":%d,\"hooks\":%d,\"mode\":%d,\"source\":%d,\"diagnostic\":\"%s\",\"image0\":%u,\"image_last\":%u,\"cal_allocs\":%d,\"cal_flags\":%d,\"cal_control\":%u,\"efuse\":%d,\"word\":%u,\"output0\":%u,\"profile\":%d,\"callbacks\":%d,\"cal_owned\":%d,\"cal_views\":%d,\"unchanged\":%d,\"capinit\":%d,\"precal_present\":%d,\"precal_owned\":%d,\"precal_view\":%d,\"precal_offset\":%u,\"precal_group\":%u,\"precal_allocs\":%d,\"precal_commands\":%d,\"precal_item\":%d,\"precal_command_group\":%d,\"trace\":\"%s\"}\n",case_name,status,fsdepth,opens,reads,writes,closes,doubleclose,allocs,frees_count,live_allocs,hook_calls,a.E2pCtrl.e2pCurMode,a.E2pCtrl.e2pSource,a.E2pCtrl.BinSource?a.E2pCtrl.BinSource:"",image[0],image[1023],cal_allocs,a.bDCOCReloaded+2*a.bDPDReloaded,(unsigned)image[0x52]|((unsigned)image[0x53]<<8),a.bUseEfuse,word,output[0],a.E2pAccessMode,callback_mode,cal_owned,cal_views,unchanged,cap.ee_inited,a.PreCalStoreBuffer!=NULL,calibration_owned(a.PreCalStoreBuffer),a.PreCalStoreBuffer==image+PRECALPART_OFFSET,(unsigned)a.PreCalWriteOffSet,(unsigned)a.ChGrpMap,precal_allocs,precal_commands,precal_item,precal_group,trace);
 for(i=0;i<32;i++)if(owned[i])free(owned[i]);
 return 0;
}
'''


def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False,disabled_oracle=False):
    if type(baseline)is not bool or type(disabled_oracle)is not bool or(baseline and disabled_oracle):
        raise ValueError('Typed exclusive BIN adapter profile required')
    functions=actual_functions(texts)
    if set(BASELINE_FUNCTIONS)!=set(FUNCTION_SOURCES)-set(NEW_FUNCTIONS) or set(DISABLED_STUBS)!=set(FUNCTION_SOURCES):
        raise ValueError('Exact baseline/stub function sets required')
    for name,body in BASELINE_FUNCTIONS.items():
        if hashlib.sha256(body.encode()).hexdigest()!=BASELINE_FUNCTIONS_SHA256[name]:raise ValueError('Changed BIN baseline')
    if baseline:bodies=BASELINE_FUNCTIONS
    elif disabled_oracle:bodies=DISABLED_STUBS
    else:bodies={name:item['body']for name,item in functions.items()}
    for literal in ('#define MAX_EEPROM_BUFFER_SIZE\t1024',):
        if literal not in texts['adapter_header']:raise ValueError('Changed configured BIN allocation bound')
    if 'INDEX0_EEPROM_size=0x4000'not in texts['l1_profile']:raise ValueError('Changed K2P profile size')
    admission='\n'.join('if(!strcmp(case_name,'+json.dumps(name)+'))known=1;'for name in CASE_NAMES)
    code=PREFIX.replace('PRECAL_DECLARATIONS',''if disabled_oracle else precal_declarations(texts['ate']))+'\n'+'\n'.join(bodies[name]for name in BODY_ORDER if name in bodies)+'\n'+MAIN.replace('CASE_ADMISSION',admission)
    return code


# Immutable accepted public baseline bodies, and deliberately inert top-level stubs.
BASELINE_FUNCTIONS = {'RtmpOSFileClose': 'int RtmpOSFileClose(RTMP_OS_FD osfd)\n{\n\tfilp_close(osfd, NULL);\n\treturn 0;\n}', 'rtmp_ee_bin_read16': 'BOOLEAN rtmp_ee_bin_read16(RTMP_ADAPTER *pAd, UINT16 Offset, UINT16 *pValue)\n{\n\tBOOLEAN IsEmpty = 0;\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_INFO, ("%s::Read from EEPROM buffer\\n", __func__));\n\tNdisMoveMemory(pValue, &(pAd->EEPROMImage[Offset]), 2);\n\t*pValue = le2cpu16(*pValue);\n\n\tif ((*pValue == 0xffff) || (*pValue == 0x0000))\n\t\tIsEmpty = 1;\n\n\treturn IsEmpty;\n}', 'rtmp_ee_bin_write16': 'INT rtmp_ee_bin_write16(\n\tIN RTMP_ADAPTER\t *pAd,\n\tIN USHORT\t\t\tOffset,\n\tIN USHORT\t\t\tdata)\n{\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_INFO, ("%s::Write to EEPROM buffer\\n", __func__));\n\tdata = le2cpu16(data);\n\tNdisMoveMemory(&(pAd->EEPROMImage[Offset]), &data, 2);\n\treturn 0;\n}', 'rtmp_ee_bin_read_with_range': 'BOOLEAN rtmp_ee_bin_read_with_range(PRTMP_ADAPTER pAd, UINT16 start, UINT16 Length, UCHAR *pbuf)\n{\n\tBOOLEAN IsEmpty = 0;\n\tUINT16  u2Loop;\n\tUCHAR   ucValue = 0;\n\n\tmemcpy(pbuf, pAd->EEPROMImage + start, Length);\n\n\tfor (u2Loop = 0; u2Loop < Length; u2Loop++)\n\t\tucValue |= pbuf[u2Loop];\n\n\tif ((ucValue == 0xff) || (ucValue == 0x00))\n\t\tIsEmpty = 1;\n\n\treturn IsEmpty;\n}', 'rtmp_ee_bin_write_with_range': 'INT rtmp_ee_bin_write_with_range(PRTMP_ADAPTER pAd, USHORT start, USHORT Length, UCHAR *pbuf)\n{\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_INFO, ("%s::Write data range to EEPROM buffer\\n", __func__));\n\tNdisMoveMemory(&(pAd->EEPROMImage[start]), pbuf, Length);\n\n\treturn 0;\n}', 'rtmp_ee_load_from_bin': 'INT rtmp_ee_load_from_bin(\n\tIN PRTMP_ADAPTER\tpAd)\n{\n\tRTMP_STRING *src = NULL;\n\tINT ret_val;\n\tRTMP_OS_FD srcf;\n\tRTMP_OS_FS_INFO osFSInfo;\n\tEEPROM_CONTROL *pE2pCtrl = &pAd->E2pCtrl;\n\tstruct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);\n\n\tpE2pCtrl->e2pCurMode = E2P_BIN_MODE;\n#ifdef RT_SOC_SUPPORT\n#ifdef MULTIPLE_CARD_SUPPORT\n\tRTMP_STRING bin_file_path[128];\n\tRTMP_STRING *bin_file_name = NULL;\n\tUINT32 chip_ver = (pAd->MACVersion >> 16);\n\n\tif (rtmp_get_default_bin_file_by_chip(pAd, chip_ver, &bin_file_name) == TRUE) {\n\t\tif (pAd->MC_RowID > 0)\n\t\t\tsprintf(bin_file_path, "%s%s", EEPROM_2ND_FILE_DIR, bin_file_name);\n\t\telse\n\t\t\tsprintf(bin_file_path, "%s%s", EEPROM_1ST_FILE_DIR, bin_file_name);\n\n\t\tsrc = bin_file_path;\n\t} else\n#endif /* MULTIPLE_CARD_SUPPORT */\n#endif /* RT_SOC_SUPPORT */\n\t{\n\t\tif (cap->EEPROM_DEFAULT_BIN_FILE != NULL) {\n\t\t\tsrc = cap->EEPROM_DEFAULT_BIN_FILE;\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t\t("%s::bin FileName=%s\\n", __func__, cap->EEPROM_DEFAULT_BIN_FILE));\n\t\t} else {\n\t\t\tsrc = BIN_FILE_PATH;\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s::FileName=%s\\n", __func__, src));\n\t\t}\n\t}\n\n\tRtmpOSFSInfoChange(&osFSInfo, TRUE);\n\n\tif (src && *src) {\n\t\tsrcf = RtmpOSFileOpen(src, O_RDONLY, 0);\n\n\t\tif (IS_FILE_OPEN_ERR(srcf)) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t\t ("%s::Error opening %s\\n", __func__, src));\n\t\t\tgoto error;\n\t\t} else {\n\t\t\tNdisZeroMemory(pAd->EEPROMImage, MAX_EEPROM_BIN_FILE_SIZE);\n\t\t\tret_val = RtmpOSFileRead(srcf, (RTMP_STRING *)pAd->EEPROMImage, MAX_EEPROM_BIN_FILE_SIZE);\n\n\t\t\tif (ret_val > 0) {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("Load EEPROM Buffer from %s\\n", src));\n\t\t\t\tret_val = NDIS_STATUS_SUCCESS;\n\t\t\t} else {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("%s::Read file \\"%s\\" failed(errCode=%d)!\\n", __func__, src, ret_val));\n\t\t\t}\n\t\t}\n\t} else {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t ("%s::Error src or srcf is null\\n", __func__));\n\t\tgoto error;\n\t}\n\n\tret_val = RtmpOSFileClose(srcf);\n\n\tif (ret_val)\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t ("%s::Error %d closing %s\\n", __func__, -ret_val, src));\n\n\tpE2pCtrl->e2pSource = E2P_SRC_FROM_BIN;\n\tpE2pCtrl->BinSource = src;\n\tRtmpOSFSInfoChange(&osFSInfo, FALSE);\n\treturn TRUE;\nerror:\n\n\tif (cap->EEPROM_DEFAULT_BIN != NULL) {\n\t\tNdisMoveMemory(pAd->EEPROMImage, cap->EEPROM_DEFAULT_BIN,\n\t\t\t\t\t   cap->EEPROM_DEFAULT_BIN_SIZE > MAX_EEPROM_BUFFER_SIZE ? MAX_EEPROM_BUFFER_SIZE :\n\t\t\t\t\t   cap->EEPROM_DEFAULT_BIN_SIZE);\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("Load EEPROM Buffer from default BIN.\\n"));\n\t\tpE2pCtrl->e2pSource = E2P_SRC_FROM_BIN;\n\t\tpE2pCtrl->BinSource = "Default bin";\n\t}\n\n\treturn FALSE;\n}', 'rtmp_ee_write_to_bin': 'INT rtmp_ee_write_to_bin(\n\tIN PRTMP_ADAPTER\tpAd)\n{\n\tRTMP_STRING *src = NULL;\n\tINT ret_val;\n\tRTMP_OS_FD srcf;\n\tRTMP_OS_FS_INFO osFSInfo;\n#ifdef RT_SOC_SUPPORT\n#ifdef MULTIPLE_CARD_SUPPORT\n\tRTMP_STRING bin_file_path[128];\n\tRTMP_STRING *bin_file_name = NULL;\n\tUINT32 chip_ver = (pAd->MACVersion >> 16);\n\n\tif (rtmp_get_default_bin_file_by_chip(pAd, chip_ver, &bin_file_name) == TRUE) {\n\t\tif (pAd->MC_RowID > 0)\n\t\t\tsprintf(bin_file_path, "%s%s", EEPROM_2ND_FILE_DIR, bin_file_name);\n\t\telse\n\t\t\tsprintf(bin_file_path, "%s%s", EEPROM_1ST_FILE_DIR, bin_file_name);\n\n\t\tsrc = bin_file_path;\n\t} else\n#endif /* MULTIPLE_CARD_SUPPORT */\n#endif /* RT_SOC_SUPPORT */\n\t{\n\t\tstruct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);\n\n\t\tif (cap->EEPROM_DEFAULT_BIN_FILE != NULL) {\n\t\t\tsrc = cap->EEPROM_DEFAULT_BIN_FILE;\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t("%s::bin FileName=%s\\n", __func__, cap->EEPROM_DEFAULT_BIN_FILE));\n\t\t} else {\n\t\t\tsrc = BIN_FILE_PATH;\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t("%s::src FileName=%s\\n", __func__, src));\n\t\t}\n\t}\n\n\tRtmpOSFSInfoChange(&osFSInfo, TRUE);\n\n\tif (src && *src) {\n\t\tsrcf = RtmpOSFileOpen(src, O_WRONLY | O_CREAT, 0);\n\n\t\tif (IS_FILE_OPEN_ERR(srcf)) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("%s::Error opening %s\\n", __func__, src));\n\t\t\treturn FALSE;\n\t\t} else\n\t\t\tRtmpOSFileWrite(srcf, (RTMP_STRING *)pAd->EEPROMImage, MAX_EEPROM_BIN_FILE_SIZE);\n\t} else {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("%s::Error src or srcf is null\\n", __func__));\n\t\treturn FALSE;\n\t}\n\n\tret_val = RtmpOSFileClose(srcf);\n\n\tif (ret_val)\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("%s::Error %d closing %s\\n", __func__, -ret_val, src));\n\n\tRtmpOSFSInfoChange(&osFSInfo, FALSE);\n\treturn TRUE;\n}', 'rtmp_ee_bin_init': 'static NDIS_STATUS rtmp_ee_bin_init(PRTMP_ADAPTER pAd)\n{\n#ifdef CAL_FREE_IC_SUPPORT\n\tBOOLEAN bCalFree = 0;\n#endif /* CAL_FREE_IC_SUPPORT */\n\trtmp_ee_load_from_bin(pAd);\n#ifdef PRE_CAL_TRX_SET1_SUPPORT\n\t{\n\t\tos_alloc_mem(pAd, &pAd->CalDCOCImage, DCOC_IMAGE_SIZE);\n\t\tos_alloc_mem(pAd, &pAd->CalDPDAPart1Image, TXDPD_IMAGE1_SIZE);\n\t\tos_alloc_mem(pAd, &pAd->CalDPDAPart2Image, TXDPD_IMAGE2_SIZE);\n\t\tNdisZeroMemory(pAd->CalDCOCImage, DCOC_IMAGE_SIZE);\n\t\tNdisZeroMemory(pAd->CalDPDAPart1Image, TXDPD_IMAGE1_SIZE);\n\t\tNdisZeroMemory(pAd->CalDPDAPart2Image, TXDPD_IMAGE2_SIZE);\n\n\t\tif (NDIS_STATUS_SUCCESS == rtmp_cal_load_from_bin(pAd, pAd->CalDCOCImage, 0, DCOC_IMAGE_SIZE))\n\t\t\tpAd->bDCOCReloaded = TRUE;\n\t\telse\n\t\t\tprintk("%s(): bDCOCReloaded = false.\\n", __func__);\n\n\t\tif ((NDIS_STATUS_SUCCESS ==\n\t\t\t\trtmp_cal_load_from_bin(pAd, pAd->CalDPDAPart1Image, DPDPART1_OFFSET, TXDPD_IMAGE1_SIZE)) &&\n\t\t\t(NDIS_STATUS_SUCCESS ==\n\t\t\t\trtmp_cal_load_from_bin(pAd, pAd->CalDPDAPart2Image, DPDPART2_OFFSET, TXDPD_IMAGE2_SIZE)))\n\t\t\tpAd->bDPDReloaded = TRUE;\n\t\telse\n\t\t\tprintk("%s(): bDPDReloaded = false.\\n", __func__);\n\t}\n#endif /* PRE_CAL_TRX_SET1_SUPPORT */\n#ifdef CAL_FREE_IC_SUPPORT\n\tRTMP_CAL_FREE_IC_CHECK(pAd, bCalFree);\n\n\tif (bCalFree) {\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("Cal Free IC!!\\n"));\n\t\tRTMP_CAL_FREE_DATA_GET(pAd);\n\t} else\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Non Cal Free IC!!\\n"));\n\n#endif /* CAL_FREE_IC_SUPPORT */\n\treturn NDIS_STATUS_SUCCESS;\n}', 'Set_LoadEepromBufferFromBin_Proc': 'INT Set_LoadEepromBufferFromBin_Proc(RTMP_ADAPTER *pAd, RTMP_STRING *arg)\n{\n\tLONG bEnable = os_str_tol(arg, 0, 10);\n\tINT result;\n\n\tif (bEnable < 0)\n\t\treturn FALSE;\n\telse {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Load EEPROM buffer from BIN, and change to BIN buffer mode\\n"));\n\t\tresult = rtmp_ee_load_from_bin(pAd);\n\n\t\tif (result == FALSE) {\n\t\t\tstruct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);\n\n\t\t\tif (cap->EEPROM_DEFAULT_BIN != NULL) {\n\t\t\t\tNdisMoveMemory(pAd->EEPROMImage, cap->EEPROM_DEFAULT_BIN,\n\t\t\t\t\t\t\t   cap->EEPROM_DEFAULT_BIN_SIZE > MAX_EEPROM_BUFFER_SIZE ? MAX_EEPROM_BUFFER_SIZE :\n\t\t\t\t\t\t\t   cap->EEPROM_DEFAULT_BIN_SIZE);\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Load EEPROM Buffer from default BIN.\\n"));\n\t\t\t}\n\t\t}\n\n\t\t/* Change to BIN eeprom buffer mode */\n\t\tRtmpChipOpsEepromHook(pAd, pAd->infType, E2P_BIN_MODE);\n\t\treturn TRUE;\n\t}\n}', 'Set_EepromBufferWriteBack_Proc': 'INT Set_EepromBufferWriteBack_Proc(RTMP_ADAPTER *pAd, RTMP_STRING *arg)\n{\n\tUINT e2p_mode = os_str_tol(arg, 0, 10);\n\n\tif (e2p_mode >= NUM_OF_E2P_MODE)\n\t\treturn FALSE;\n\n\tswitch (e2p_mode) {\n#ifdef RTMP_EFUSE_SUPPORT\n\n\tcase E2P_EFUSE_MODE:\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Write EEPROM buffer back to eFuse\\n"));\n\t\trtmp_ee_write_to_efuse(pAd);\n\t\tbreak;\n#endif /* RTMP_EFUSE_SUPPORT */\n#ifdef RTMP_FLASH_SUPPORT\n\n\tcase E2P_FLASH_MODE:\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Write EEPROM buffer back to Flash\\n"));\n\t\trtmp_ee_flash_write_all(pAd);\n\t\tbreak;\n#endif /* RTMP_FLASH_SUPPORT */\n\n\tcase E2P_EEPROM_MODE:\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Write EEPROM buffer back to EEPROM\\n"));\n\t\trtmp_ee_write_to_prom(pAd);\n\t\tbreak;\n\n\tcase E2P_BIN_MODE:\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Write EEPROM buffer back to BIN\\n"));\n\t\trtmp_ee_write_to_bin(pAd);\n\t\tbreak;\n\n\tdefault:\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("%s::do not support this EEPROM access mode\\n", __func__));\n\t\treturn FALSE;\n\t}\n\n\treturn TRUE;\n}', 'rtmp_ee_flash_reset': 'static NDIS_STATUS rtmp_ee_flash_reset(RTMP_ADAPTER *pAd, UCHAR *start)\n{\n\tPUCHAR src;\n\tRTMP_OS_FS_INFO osFsInfo;\n\tRTMP_OS_FD srcf;\n\tINT retval;\n\tNDIS_STATUS status = NDIS_STATUS_FAILURE;\n\tUINT copy_size;\n\tEEPROM_CONTROL *pE2pCtrl = &pAd->E2pCtrl;\n\tstruct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);\n\n#ifdef RT_SOC_SUPPORT\n#ifdef MULTIPLE_CARD_SUPPORT\n\tRTMP_STRING BinFilePath[128];\n\tRTMP_STRING *pBinFileName = NULL;\n\tUINT32\tChipVerion = (pAd->MACVersion >> 16);\n\n\tif (rtmp_get_default_bin_file_by_chip(pAd, ChipVerion, &pBinFileName) == TRUE) {\n\t\tif (pAd->MC_RowID > 0)\n\t\t\tsprintf(BinFilePath, "%s%s", EEPROM_2ND_FILE_DIR, pBinFileName);\n\t\telse\n\t\t\tsprintf(BinFilePath, "%s%s", EEPROM_1ST_FILE_DIR, pBinFileName);\n\n\t\tsrc = BinFilePath;\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s(): src = %s\\n", __func__, src));\n\t} else\n#endif /* MULTIPLE_CARD_SUPPORT */\n#endif /* RT_SOC_SUPPORT */\n\t{\n#if defined(MT_MAC) && defined(MT7603)\n\n\t\tif (IS_MT7603(pAd))\n\t\t\tsrc = EEPROM_DEFAULT_7603_FILE_PATH;\n\t\telse\n#endif /* MT_MAC && MT7603 */\n\t\t{\n\t\t\tsrc = EEPROM_DEFAULT_FILE_PATH;\n\t\t}\n\t}\n\n\tif (!start || get_dev_eeprom_size(pAd) < EEPROM_SIZE)\n\t\treturn NDIS_STATUS_FAILURE;\n\tpE2pCtrl->e2pSource = E2P_SRC_FROM_BIN;\n\tRtmpOSFSInfoChange(&osFsInfo, TRUE);\n\n\tif (src && *src) {\n\t\tsrcf = RtmpOSFileOpen(src, O_RDONLY, 0);\n\n\t\tif (IS_FILE_OPEN_ERR(srcf)) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t ("--> Error opening file %s\\n", src));\n\n\t\t\tcopy_size = cap->EEPROM_DEFAULT_BIN_SIZE > MAX_EEPROM_BUFFER_SIZE ?\n\t\t\t\tMAX_EEPROM_BUFFER_SIZE : cap->EEPROM_DEFAULT_BIN_SIZE;\n\t\t\tif (cap->EEPROM_DEFAULT_BIN != NULL && copy_size >= EEPROM_SIZE &&\n\t\t\t\tcopy_size <= get_dev_eeprom_size(pAd)) {\n\t\t\t\tNdisMoveMemory(start, cap->EEPROM_DEFAULT_BIN, copy_size);\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("Load EEPROM Buffer from default BIN.\\n"));\n\t\t\t\tpE2pCtrl->BinSource = "Default bin";\n\t\t\t\tstatus = NDIS_STATUS_SUCCESS;\n\t\t\t}\n\t\t\tgoto out_restore;\n\t\t} else {\n\t\t\t/* The object must have a read method*/\n\t\t\tNdisZeroMemory(start, EEPROM_SIZE);\n\t\t\tretval = RtmpOSFileRead(srcf, start, EEPROM_SIZE);\n\n\t\t\tif (retval != EEPROM_SIZE) {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("--> Read %s error %d\\n", src, -retval));\n\t\t\t} else {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t\t\t ("--> rtmp_ee_flash_reset copy %s to eeprom buffer\\n", src));\n\t\t\t\tpE2pCtrl->BinSource = src;\n\t\t\t\tstatus = NDIS_STATUS_SUCCESS;\n\t\t\t}\n\n\t\t\tretval = RtmpOSFileClose(srcf);\n\n\t\t\tif (retval) {\n\t\t\t\tstatus = NDIS_STATUS_FAILURE;\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("--> Error %d closing %s\\n", -retval, src));\n\t\t\t}\n\t\t}\n\t}\n\nout_restore:\n\tRtmpOSFSInfoChange(&osFsInfo, FALSE);\n\treturn status;\n}', 'eFuse_init': 'INT eFuse_init(RTMP_ADAPTER *pAd)\n{\n\tUINT EfuseFreeBlock = 0;\n#ifdef CAL_FREE_IC_SUPPORT\n\tBOOLEAN bCalFree = 0;\n#endif\n\tstruct _RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);\n\t/*RT3572 means 3062/3562/3572*/\n\t/*3593 means 3593*/\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t ("NVM is Efuse and its size =%x[%x-%x]\\n",\n\t\t\t  cap->EFUSE_USAGE_MAP_SIZE,\n\t\t\t  cap->EFUSE_USAGE_MAP_START, cap->EFUSE_USAGE_MAP_END));\n\teFuseGetFreeBlockCount(pAd, &EfuseFreeBlock);\n\t/*If the used block of efuse is less than 5. We assume the default value*/\n\t/* of this efuse is empty and change to the buffer mode in odrder to */\n\t/*bring up interfaces successfully.*/\n\n\tif (EfuseFreeBlock >= cap->EFUSE_RESERVED_SIZE) {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t\t ("NVM is efuse and the information is too less to bring up the interface\\n"));\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t\t ("Load EEPROM buffer from BIN, and force to use BIN buffer mode\\n"));\n\t\tpAd->bUseEfuse = FALSE;\n\t\trtmp_ee_load_from_bin(pAd);\n\t\t/* Forse to use BIN eeprom buffer mode */\n\t\tRtmpChipOpsEepromHook(pAd, pAd->infType, E2P_BIN_MODE);\n#ifdef CAL_FREE_IC_SUPPORT\n\t\tRTMP_CAL_FREE_IC_CHECK(pAd, bCalFree);\n\n\t\tif (bCalFree) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("Cal Free IC!!\\n"));\n\t\t\tRTMP_CAL_FREE_DATA_GET(pAd);\n\t\t} else\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Non Cal Free IC!!\\n"));\n\n#endif /* CAL_FREE_IC_SUPPORT */\n\t} else\n\t\trtmp_ee_load_from_efuse(pAd);\n\n\treturn 0;\n}', 'MtATE_Pre_Cal_Proc': 'INT MtATE_Pre_Cal_Proc(RTMP_ADAPTER *pAd, UINT8 CalId, UINT32 ChGrpId)\n{\n\tINT32 ret = NDIS_STATUS_SUCCESS;\n\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t ("%s: Cal Id = %d, ChGrpId = %d\\n", __func__, CalId, ChGrpId));\n\t/* Initialization */\n\tpAd->PreCalWriteOffSet = 0;\n\tpAd->ChGrpMap = PreCalGroupList[ChGrpId];\n\n\tif (pAd->E2pAccessMode == E2P_FLASH_MODE) {\n\t\tpAd->PreCalStoreBuffer = pAd->EEPROMImage + PRECALPART_OFFSET;\n\t} else {\n\t\tret = os_alloc_mem(pAd, &pAd->PreCalStoreBuffer, PRE_CAL_SIZE_ONE_CARD);\n\n\t\tif (ret != NDIS_STATUS_SUCCESS) {\n\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t("\\x1b[42m %s : Not enough memory for pre-cal stored buffer!!\\x1b[m\\n", __func__));\n\t\t}\n\t}\n\n\tif (ret == NDIS_STATUS_SUCCESS)\n\t\tMtCmdGetPreCalResult(pAd, PreCalItemList[CalId], PreCalGroupList[ChGrpId]);\n\n\treturn TRUE;\n}'}
BASELINE_FUNCTIONS_SHA256 = {'RtmpOSFileClose': '13a6fc13c16e376db84ec5c19498e95bca13de70ef60de630546adcebc20bd6a', 'rtmp_ee_bin_read16': '5920ae1aa7257ead6ca6284c8325a9bd0c055bc9fcd1b06508da5ce2a6f4592a', 'rtmp_ee_bin_write16': '559bb932fa3b8fc0a74435336453557292757d52939f0f16b5fcd03b877a854a', 'rtmp_ee_bin_read_with_range': '826cafc575dbaec2ba5329322e6dea0605ba774659267a2e9ceb3ae78655e14a', 'rtmp_ee_bin_write_with_range': '0b1d541f2faad06fd85cd50e5a6e0e803c825ef7099748953c0f7feee9520087', 'rtmp_ee_load_from_bin': '6123ab8b8d162ff0b3f766d3adcd837ddc82f5222e7370662c1fc0365a07602d', 'rtmp_ee_write_to_bin': '8b6517ea55be09d32af46fda9e4a686ab51cdc5b27193c7e832cc609d3237697', 'rtmp_ee_bin_init': '4a9c8dc19b3cad44b7b97ead3ca00f6f53d8997279a5879d7b58907799aef37d', 'Set_LoadEepromBufferFromBin_Proc': 'ecd82c8b90d6b4a7c70609760a1ea15294154a439df08efc41f6cf2326b33aa5', 'Set_EepromBufferWriteBack_Proc': '94c92505c7cadc5f2614a5851662e4236c244eaaeb0af5347460fa9e6d6b9686', 'rtmp_ee_flash_reset': 'a6d03a93bca076b376a693d20384f9465add4349bb5aa442b39fbda37cd344a1', 'eFuse_init': '476d8a1043da8fb688f8ead2d414ab631dc156ccf8e2d32ba37d50caeb56939d', 'MtATE_Pre_Cal_Proc': '125e6adbc3c01dfc56e1b490449b648ba30a1b0b809f2bf003c7b57668415762'}
DISABLED_STUBS = {'RtmpOSFileClose': 'int RtmpOSFileClose(RTMP_OS_FD fd){(void)fd;return 0;}', 'RtmpOSFileCloseChecked': 'int RtmpOSFileCloseChecked(RTMP_OS_FD fd){(void)fd;return 0;}', 'rtmp_ee_bin_capacity': 'static UINT rtmp_ee_bin_capacity(PRTMP_ADAPTER p){(void)p;return 0;}', 'rtmp_ee_bin_read16': 'BOOLEAN rtmp_ee_bin_read16(RTMP_ADAPTER*p,UINT16 o,UINT16*v){(void)p;(void)o;(void)v;return TRUE;}', 'rtmp_ee_bin_write16': 'INT rtmp_ee_bin_write16(RTMP_ADAPTER*p,USHORT o,USHORT v){(void)p;(void)o;(void)v;return 0;}', 'rtmp_ee_bin_read_with_range': 'BOOLEAN rtmp_ee_bin_read_with_range(PRTMP_ADAPTER p,UINT16 o,UINT16 n,UCHAR*b){(void)p;(void)o;(void)n;(void)b;return TRUE;}', 'rtmp_ee_bin_write_with_range': 'INT rtmp_ee_bin_write_with_range(PRTMP_ADAPTER p,USHORT o,USHORT n,UCHAR*b){(void)p;(void)o;(void)n;(void)b;return 0;}', 'rtmp_ee_load_from_bin': 'INT rtmp_ee_load_from_bin(PRTMP_ADAPTER p){(void)p;return TRUE;}', 'rtmp_ee_write_to_bin': 'INT rtmp_ee_write_to_bin(PRTMP_ADAPTER p){(void)p;return TRUE;}', 'rtmp_ee_bin_init': 'static NDIS_STATUS rtmp_ee_bin_init(PRTMP_ADAPTER p){(void)p;return NDIS_STATUS_SUCCESS;}', 'Set_LoadEepromBufferFromBin_Proc': 'INT Set_LoadEepromBufferFromBin_Proc(RTMP_ADAPTER*p,RTMP_STRING*a){(void)p;(void)a;return TRUE;}', 'Set_EepromBufferWriteBack_Proc': 'INT Set_EepromBufferWriteBack_Proc(RTMP_ADAPTER*p,RTMP_STRING*a){(void)p;(void)a;return TRUE;}', 'rtmp_ee_flash_reset': 'static NDIS_STATUS rtmp_ee_flash_reset(RTMP_ADAPTER*p,UCHAR*b){(void)p;(void)b;return NDIS_STATUS_SUCCESS;}', 'eFuse_init': 'INT eFuse_init(RTMP_ADAPTER*p){(void)p;return NDIS_STATUS_SUCCESS;}', 'MtATE_Pre_Cal_Proc': 'INT MtATE_Pre_Cal_Proc(RTMP_ADAPTER*p,UINT8 c,UINT32 g){(void)p;(void)c;(void)g;return TRUE;}'}
DISABLED_STUB_SHA256 = {'RtmpOSFileClose': 'ac49e91299f142af3f7143e4a9227358f54c4318bd0bf8e6abd8309d4c32a3c5', 'RtmpOSFileCloseChecked': '1fded6d6adeaf5869c986c808203cd456bd51ad6ab2e1d7a9b2bcdb93e4e3254', 'rtmp_ee_bin_capacity': '72f82ab0ac8780899692ce5650133b828701da48f26ea9322288c92ddf874dd3', 'rtmp_ee_bin_read16': '4d7b499611836aa9310261d6625e817a03c92e3408a814eddb88c36fe8202b5f', 'rtmp_ee_bin_write16': '267175c9b27b2d363332d30c20d5cbf050bc5b3db9f12b4cec8b70f60fbbd51b', 'rtmp_ee_bin_read_with_range': 'a6b02595c90391921af32a3b204020c872c2e9dc2753730f02aa49f91aa8a834', 'rtmp_ee_bin_write_with_range': 'ac0229b4f15bd9153037c93084a3be62bb138018a9d7d418ebaf9602c3dd2643', 'rtmp_ee_load_from_bin': '42a30944742f1bdef419fbd130122f97cce027a9e6c7602e93a7a8caa4d16278', 'rtmp_ee_write_to_bin': 'cc1c65f3142bc419364690e4e420e660bf00acc41c44b4c4dce0e1edcf701ae9', 'rtmp_ee_bin_init': '1b30443edb8c7486464b48a0faa2f38f1c4120ec741786ee21dadf9bfc5c063b', 'Set_LoadEepromBufferFromBin_Proc': 'f993fd8e9a29b2574c6752e7ad1275b5c2e717c85dcaca8faa819ba6829aff09', 'Set_EepromBufferWriteBack_Proc': '53e8dd07f72970f3e6e629aed00de0fca4aa18a99aae13b3607248bee892b6b4', 'rtmp_ee_flash_reset': '7ae1ce0c1f60e8b9b8f90c55ab0d4ecdf14d40e8ef057bd8ca6a30822571591d', 'eFuse_init': '47272ac0c4bf94e24cb7931e6fef7821fb9de958b7209f1b62e84ce22db35a56', 'MtATE_Pre_Cal_Proc': '79301b344a2904e60587301b0bf5f566dadcdad570af68bdc730cfb33e708e6b'}
