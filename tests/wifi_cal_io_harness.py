"""Pure calibration-file IO and explicit NIC pre-cal section adapter.

Eight whole current production functions execute under ordinary RAM/IO seams.
Only the marked PRE_CAL_SET2 section of NICReadEEPROMParameters executes;
the complete proprietary parser remains hash-bound metadata, not executed.
"""
import hashlib
import re

BASELINE_COMMIT='3a404e1675467cab79af0ffac454061c1e9150ae'
BASE='trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/'
SOURCE_PATHS={'eeprom':BASE+'embedded/common/eeprom.c',
              'os':BASE+'os/linux/rt_linux.c',
              'os_header':BASE+'embedded/include/rt_os_util.h'}
FUNCTION_SOURCES={
 'RtmpOSFileClose':'os','RtmpOSFileCloseChecked':'os',
 'rtmp_cal_bin_io':'eeprom','rtmp_cal_load_from_bin':'eeprom',
 'rtmp_cal_write_to_bin':'eeprom','Cal_Data_Load_From_Bin':'eeprom',
 'Cal_Data_Write_To_Bin':'eeprom','rtmp_eeprom_restore_precal':'eeprom',
 'NICReadEEPROMParameters':'eeprom'}
CURRENT_NAMES=tuple(FUNCTION_SOURCES)
BASELINE_NAMES=('RtmpOSFileClose','rtmp_cal_load_from_bin','rtmp_cal_write_to_bin',
                'Cal_Data_Load_From_Bin','Cal_Data_Write_To_Bin','NICReadEEPROMParameters')
CASE_NAMES=(
 'read-ok','read-error','read-short','read-zero','read-oversized','read-open-error',
 'read-empty','read-close-error','read-null','read-zero-len','read-offset-max',
 'read-length-max','read-alloc-error','read-alloc-null','read-first','read-second',
 'write-ok','write-error','write-short','write-zero','write-oversized','write-open-error',
 'write-empty','write-close-error','write-null','write-zero-len','write-offset-max',
 'write-length-max','data-read-ok','data-read-short','data-read-close-error','data-read-nonmt',
 'data-write-ok','data-write-short','data-write-close-error','data-write-nonmt',
 'restore-flash-ok','restore-flash-read-error','restore-flash-read-short',
 'restore-alloc-error','restore-alloc-null','restore-cached','restore-no-bit',
 'restore-other-mode','restore-bin-ok','restore-bin-error','restore-bin-short',
 'restore-bin-close-error','restore-command-error','restore-previous-ok',
 'restore-previous-error','restore-repeat','restore-zero-size',
 'legacy-close-error','checked-close-error')
BASELINE_CASES=('read-error','read-short','read-open-error','read-close-error',
 'write-error','write-short','write-open-error','write-close-error',
 'data-read-short','data-write-short','restore-flash-read-error','restore-alloc-error')
DISABLED_CASES=('read-ok','restore-flash-ok')
HEADER_CURRENT='int RtmpOSFileClose(RTMP_OS_FD osfd);\nint RtmpOSFileCloseChecked(RTMP_OS_FD osfd);'
HEADER_BASELINE='int RtmpOSFileClose(RTMP_OS_FD osfd);'


def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'^(?:static\s+)?(?:int|INT|BOOLEAN|NDIS_STATUS)\s+'+
                           re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked,re.M))
    if len(matches)!=1:raise ValueError('Missing/ambiguous calibration function '+name)
    start=matches[0].start();opening=text.index('{',start);depth=0
    for token in re.finditer(tokens+r'|[{}]',text[opening:]):
        if token.group()=='{':depth+=1
        elif token.group()=='}':
            depth-=1
            if not depth:return text[start:opening+token.end()]
    raise ValueError('Unterminated calibration function '+name)


def actual_functions(texts):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact calibration source set required')
    return {name:{'source':source,'body':function(texts[source],name),
                  'execution':'precal-section' if name=='NICReadEEPROMParameters' else 'whole-function'}
            for name,source in FUNCTION_SOURCES.items()}


def execution_section(body):
    start=body.index('\tPreCalSize = PRE_CAL_SIZE_ONE_CARD;')
    end=body.index('#endif /* PRE_CAL_TRX_SET2_SUPPORT */',start)
    return body[start:end]


def fragments(functions):
    result={name:item['body'] for name,item in functions.items()}
    result['NICReadEEPROMParameters']=(
        'static BOOLEAN observed_nic_restore(RTMP_ADAPTER*pAd)\n{\n UINT16 PreCalSize,DoPreCal=0;\n'+
        execution_section(result['NICReadEEPROMParameters'])+'\n parsed++;event("parse");return TRUE;\n}')
    return result


PREFIX=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define IN
#define TRUE 1
#define FALSE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define CONFIG_RT_FIRST_CARD 1
#define CONFIG_RT_SECOND_CARD 1
#define CONFIG_RALINK_MT7621 1
#define MULTI_INF_SUPPORT 1
#define RTMP_FLASH_SUPPORT 1
#define CONFIG_WIFI_MTD 1
#define E2P_FLASH_MODE 2
#define E2P_BIN_MODE 4
#define O_RDONLY 0
#define O_WRONLY 1
#define O_CREAT 2
#define PRECALPART_OFFSET 32
#define PRE_CAL_SIZE_ONE_CARD precal_size
#define PRE_CAL_SIZE_DUAL_CARD 48
#define CAL_FILE_PATH base_path
#define FIRST_CAL_FILE_PATH first_path
#define SECOND_CAL_FILE_PATH second_path
#define CAL_BIN_FILE_PATH base_path
#define FIRST_CAL_BIN_FILE_PATH first_path
#define SECOND_CAL_BIN_FILE_PATH second_path
#define IS_MT7615(p) (is_mt)
#define MTWF_LOG(a,b,c,args) do{if(0)printf args;}while(0)
#define NdisMoveMemory(d,s,n) memcpy(d,s,n)
#define NdisZeroMemory(p,n) memset(p,0,n)
#define RT28xx_EEPROM_READ16(p,o,v) do{(void)(p);(void)(o);(v)=calbits;}while(0)
#define RT28xx_EEPROM_WRITE16(p,o,v) do{(void)(p);(void)(o);flagwrites++;calbits=(v);event("flag");}while(0)
typedef unsigned char UCHAR;
typedef unsigned char UINT8;
typedef unsigned char u_char;
typedef unsigned short UINT16;
typedef unsigned int UINT32;
typedef unsigned long ULONG;
typedef long long loff_t;
typedef int INT;
typedef int INT32;
typedef int BOOLEAN;
typedef int NDIS_STATUS;
typedef char RTMP_STRING;
typedef struct {int live,pos;} file_handle;
typedef file_handle*RTMP_OS_FD;
typedef struct {int unused;} RTMP_OS_FS_INFO;
typedef struct _RTMP_ADAPTER {int dev_idx,E2pAccessMode;void*hdev_ctrl,*rlmCalCache;UCHAR*PreCalReStoreBuffer;} RTMP_ADAPTER,*PRTMP_ADAPTER;
#define IS_FILE_OPEN_ERR(p) (!(p)||(intptr_t)(p)<0)
static const char*case_name;
static char*base_path=(char*)"base",*first_path=(char*)"first",*second_path=(char*)"second";
static int allocs,frees_count,live_allocs,opens,closes,reads,writes,seeks,fsdepth,badclose,commands,parsed,flagwrites;
static int lastoffset,lastlen,pathid,is_mt=1,calbits=4,precal_size=64,poison,legacy_calls,checked_calls;
static file_handle handle;
static char trace[2048];
static int has(const char*s){return strstr(case_name,s)!=NULL;}
static void event(const char*s){size_t n=strlen(trace);if(n)trace[n++]=',';if(n+strlen(s)>=sizeof(trace))abort();strcpy(trace+n,s);}
static INT os_alloc_mem(RTMP_ADAPTER*p,UCHAR**out,ULONG n){
 (void)p;allocs++;event("alloc");*out=NULL;
 if(has("alloc-error")||n>4096)return 1;
 if(has("alloc-null"))return 0;
 *out=malloc(n?n:1);if(!*out)abort();memset(*out,0xaa,n);live_allocs++;return 0;
}
static void os_free_mem(void*p){if(p){frees_count++;live_allocs--;event("free");free(p);}}
static void RtmpOSFSInfoChange(RTMP_OS_FS_INFO*p,int on){(void)p;fsdepth+=on?1:-1;event(on?"fs+":"fs-");if(fsdepth<0)abort();}
static RTMP_OS_FD RtmpOSFileOpen(char*p,int flags,int mode){
 (void)flags;(void)mode;opens++;event("open");pathid=!strcmp(p,"first")?1:!strcmp(p,"second")?2:3;
 if(has("open-error"))return (RTMP_OS_FD)(intptr_t)-1;
 handle.live=1;return &handle;
}
static int filp_close(RTMP_OS_FD p,void*unused){(void)unused;closes++;event("close");if(!p||p!=&handle||!p->live){badclose++;return -9;}p->live=0;return has("close-error")?-5:0;}
static void RtmpOSFileSeek(RTMP_OS_FD p,int offset){if(p!=&handle||!p->live)abort();seeks++;event("seek");lastoffset=offset;p->pos=offset;}
static int count_io(int n){if(has("error")&&!has("close-error"))return -5;if(has("short"))return n/2;if(has("zero")&&!has("zero-len"))return 0;if(has("oversized"))return n+1;return n;}
static int RtmpOSFileRead(RTMP_OS_FD p,char*buf,int n){
 int count,i;reads++;event("read");lastlen=n;if(p!=&handle||!p->live||n<0||n>4096)abort();count=count_io(n);
 for(i=0;i<(count<0?1:count>n?n:count);i++) {
  buf[i]=count<0?0x11:0x33;
 }
 return count;
}
static int RtmpOSFileWrite(RTMP_OS_FD p,char*buf,int n){(void)buf;writes++;event("write");lastlen=n;if(p!=&handle||!p->live||n<0)abort();return count_io(n);}
static int rlmCalCacheDone(void*p){(void)p;return has("cached");}
static int multi_inf_get_count(void){return 1;}
static unsigned int get_dev_eeprom_offset(RTMP_ADAPTER*p){(void)p;return 16;}
static int mt_mtd_read_nm_wifi(char*name,loff_t offset,size_t n,u_char*buf){
 size_t i;(void)name;reads++;lastoffset=(int)offset;lastlen=(int)n;event("mtd-read");
 if(has("read-error")||has("previous-error")){buf[0]=0x11;return -5;}
 if(has("read-short")){memset(buf,0x33,n/2);return -5;}
 for(i=0;i<n;i++) {
  buf[i]=0x33;
 }
 return 0;
}
static void RtmpFlashRead(void*p,UCHAR*buf,unsigned int offset,unsigned int n){(void)p;mt_mtd_read_nm_wifi((char*)"Factory",offset,n,buf);}
static int MtCmdPreCalReStoreProc(RTMP_ADAPTER*p,INT32*buf){UCHAR*b=(UCHAR*)buf;(void)p;commands++;event("command");if(b[0]!=0x33||b[precal_size-1]!=0x33)poison++;return has("command-error")?1:0;}
'''

MAIN=r'''
int main(int argc,char**argv)
{
 RTMP_ADAPTER a;UCHAR buf[16];ULONG offset=4,length=16;UCHAR*pointer=buf;
 int result=0,known=0;
 if(argc!=2)return 90;
 case_name=argv[1];
 CASE_ADMISSION
 if(!known)return 91;
 memset(&a,0,sizeof(a));memset(buf,0x55,sizeof(buf));a.dev_idx=2;a.E2pAccessMode=2;
 if(has("-first"))a.dev_idx=0;
 if(has("-second"))a.dev_idx=1;
 if(has("-empty"))base_path=(char*)"";
 if(has("-null")&&!has("alloc-null"))pointer=NULL;
 if(has("-zero-len")){pointer=NULL;length=0;}
 if(has("-offset-max"))offset=0xffffffffUL;
 if(has("-length-max"))length=0xffffffffUL;
 if(has("-nonmt"))is_mt=0;
 if(has("restore-bin"))a.E2pAccessMode=4;
 if(has("other-mode"))a.E2pAccessMode=3;
 if(has("no-bit"))calbits=0;
 if(has("zero-size"))precal_size=0;
 if(has("previous")){a.PreCalReStoreBuffer=malloc(64);if(!a.PreCalReStoreBuffer)abort();memset(a.PreCalReStoreBuffer,0x77,64);live_allocs++;}
 MODE_CALL
 printf("{\"case\":\"%s\",\"result\":%d,\"fsdepth\":%d,\"allocs\":%d,\"frees\":%d,\"live_allocs\":%d,\"opens\":%d,\"closes\":%d,\"reads\":%d,\"writes\":%d,\"seeks\":%d,\"offset\":%d,\"length\":%d,\"path\":%d,\"commands\":%d,\"parsed\":%d,\"flagwrites\":%d,\"calbits\":%d,\"buf0\":%u,\"buf15\":%u,\"precal\":%d,\"poison\":%d,\"legacy_close\":%d,\"checked_close\":%d,\"bad_close\":%d,\"trace\":\"%s\"}\n",
 case_name,result,fsdepth,allocs,frees_count,live_allocs,opens,closes,reads,writes,seeks,lastoffset,lastlen,pathid,commands,parsed,flagwrites,calbits,buf[0],buf[15],a.PreCalReStoreBuffer!=NULL,poison,legacy_calls,checked_calls,badclose,trace);
 free(a.PreCalReStoreBuffer);
 return 0;
}
'''
CALL=r'''
 if(!strncmp(case_name,"read-",5))result=rtmp_cal_load_from_bin(&a,pointer,offset,length);
 else if(!strncmp(case_name,"write-",6))result=rtmp_cal_write_to_bin(&a,pointer,offset,length);
 else if(!strncmp(case_name,"data-read-",10))result=Cal_Data_Load_From_Bin(&a,pointer,(UINT32)offset,(UINT32)length);
 else if(!strncmp(case_name,"data-write-",11))result=Cal_Data_Write_To_Bin(&a,pointer,(UINT32)offset,(UINT32)length);
 else if(has("legacy-close")){handle.live=1;legacy_calls++;result=RtmpOSFileClose(&handle);}
 else if(has("checked-close")){handle.live=1;checked_calls++;CHECKED_CALL}
 else {result=observed_nic_restore(&a);if(has("repeat")&&result)result=observed_nic_restore(&a);}
'''


def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False,disabled_oracle=False):
    if (type(baseline)is not bool or type(disabled_oracle)is not bool or
            baseline and disabled_oracle or type(owner_uid)is not int or not 0<=owner_uid<2**32):
        raise ValueError('Typed exclusive calibration source mode required')
    if fixture_root is not None and (type(fixture_root)is not str or not fixture_root.startswith('/') or
                                     any(not 32<=ord(c)<127 for c in fixture_root)):
        raise ValueError('Absolute ASCII fixture root required')
    functions=actual_functions(texts)
    if texts['os_header'].count(HEADER_CURRENT)!=1:raise ValueError('Checked close declarations changed')
    for name,body in BASELINE_FUNCTIONS.items():
        if hashlib.sha256(body.encode()).hexdigest()!=BASELINE_FUNCTIONS_SHA256[name]:
            raise ValueError('Changed calibration baseline '+name)
    if baseline:
        functions={name:dict(functions[name],body=body) for name,body in BASELINE_FUNCTIONS.items()}
    code=fragments(functions)
    bodies='' if disabled_oracle else '\n'.join(code.values())
    call='(void)offset;(void)length;(void)pointer;result=0;' if disabled_oracle else CALL.replace('CHECKED_CALL',
          'result=0;' if baseline else 'result=RtmpOSFileCloseChecked(&handle);')
    admission='\n'.join('if(!strcmp(case_name,"'+name+'"))known=1;' for name in CASE_NAMES)
    header=HEADER_BASELINE if baseline else HEADER_CURRENT
    return PREFIX+'\n'+header+'\n'+bodies+'\n'+MAIN.replace('CASE_ADMISSION',admission).replace('MODE_CALL',call)

BASELINE_FUNCTIONS = {'RtmpOSFileClose': 'int RtmpOSFileClose(RTMP_OS_FD osfd)\n{\n\tfilp_close(osfd, NULL);\n\treturn 0;\n}', 'rtmp_cal_load_from_bin': 'NDIS_STATUS rtmp_cal_load_from_bin(\n\tIN PRTMP_ADAPTER\tpAd,\n\tIN UCHAR *buf,\n\tIN ULONG offset,\n\tIN ULONG len)\n{\n\tRTMP_STRING *src = NULL;\n\tINT ret_val;\n\tRTMP_OS_FD srcf;\n\tRTMP_OS_FS_INFO osFSInfo;\n#ifdef CONFIG_RT_FIRST_CARD\n\n\tif (pAd->dev_idx == 0)\n\t\tsrc = FIRST_CAL_FILE_PATH;\n\telse\n#endif /* CONFIG_RT_FIRST_CARD */\n#ifdef CONFIG_RT_SECOND_CARD\n\t\tif (pAd->dev_idx == 1)\n\t\t\tsrc = SECOND_CAL_FILE_PATH;\n\t\telse\n#endif /* CONFIG_RT_SECOND_CARD */\n\t\t\tsrc = CAL_FILE_PATH;\n\n\t/* MTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s::FileName=%s\\n", __func__, src)); */\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s::FileName=%s\\n", __func__, src));\t\t/* Anjan - debug */\n\tRtmpOSFSInfoChange(&osFSInfo, TRUE);\n\n\tif (src && *src) {\n\t\tsrcf = RtmpOSFileOpen(src, O_RDONLY, 0);\n\n\t\tif (IS_FILE_OPEN_ERR(srcf)) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t ("%s::Error opening %s\\n", __func__, src));\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t\t ("\\e[0;31m Run RXDCOC/TXDPD/PRECAL cmds to generate caldata files\\e[m\\n"));\n\t\t\treturn NDIS_STATUS_FAILURE;\n\t\t} else {\n\t\t\tRtmpOSFileSeek(srcf, offset);\n\t\t\tret_val = RtmpOSFileRead(srcf, (RTMP_STRING *)buf, len);\n\n\t\t\tif (ret_val > 0) {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("Load from %s (Read = %d)\\n", src, ret_val));\n\t\t\t\tret_val = NDIS_STATUS_SUCCESS;\n\t\t\t} else {\n\t\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("%s::Read file \\"%s\\" failed(errCode=%d)!\\n", __func__, src, ret_val));\n\t\t\t}\n\t\t}\n\t} else {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t ("%s::Error src or srcf is null\\n", __func__));\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("FAIL!!! Load Cal Data from file.\\n"));\n\t\treturn NDIS_STATUS_FAILURE;\n\t}\n\n\tret_val = RtmpOSFileClose(srcf);\n\n\tif (ret_val)\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t ("%s::Error %d closing %s\\n", __func__, -ret_val, src));\n\n\tRtmpOSFSInfoChange(&osFSInfo, FALSE);\n\treturn NDIS_STATUS_SUCCESS;\n}', 'rtmp_cal_write_to_bin': 'NDIS_STATUS rtmp_cal_write_to_bin(\n\tIN PRTMP_ADAPTER\tpAd,\n\tIN UCHAR *buf,\n\tIN ULONG offset,\n\tIN ULONG len)\n{\n\tRTMP_STRING *src = NULL;\n\tINT ret_val;\n\tRTMP_OS_FD srcf;\n\tRTMP_OS_FS_INFO osFSInfo;\n#ifdef CONFIG_RT_FIRST_CARD\n\n\tif (pAd->dev_idx == 0)\n\t\tsrc = FIRST_CAL_FILE_PATH;\n\telse\n#endif /* CONFIG_RT_FIRST_CARD */\n#ifdef CONFIG_RT_SECOND_CARD\n\t\tif (pAd->dev_idx == 1)\n\t\t\tsrc = SECOND_CAL_FILE_PATH;\n\t\telse\n#endif /* CONFIG_RT_SECOND_CARD */\n\t\t\tsrc = CAL_FILE_PATH;\n\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s::FileName=%s\\n", __func__, src));\n\tRtmpOSFSInfoChange(&osFSInfo, TRUE);\n\n\tif (src && *src) {\n\t\tsrcf = RtmpOSFileOpen(src, O_WRONLY | O_CREAT, 0);\n\n\t\tif (IS_FILE_OPEN_ERR(srcf)) {\n\t\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("%s::Error opening %s\\n", __func__, src));\n\t\t\treturn NDIS_STATUS_FAILURE;\n\t\t} else {\n\t\t\tRtmpOSFileSeek(srcf, offset);\n\t\t\tRtmpOSFileWrite(srcf, (RTMP_STRING *)buf, len);\n\t\t}\n\t} else {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("%s::Error src or srcf is null\\n", __func__));\n\t\treturn NDIS_STATUS_FAILURE;\n\t}\n\n\tret_val = RtmpOSFileClose(srcf);\n\n\tif (ret_val)\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("%s::Error %d closing %s\\n", __func__, -ret_val, src));\n\n\tRtmpOSFSInfoChange(&osFSInfo, FALSE);\n\treturn NDIS_STATUS_SUCCESS;\n}', 'Cal_Data_Load_From_Bin': 'INT Cal_Data_Load_From_Bin(\n\t\tIN PRTMP_ADAPTER pAd,\n\t\tIN UINT8 *Buf,\n\t\tIN UINT32 Offset,\n\t\tIN UINT32 Len)\n{\n\tINT32 retval, Status = NDIS_STATUS_FAILURE;\n\tRTMP_STRING *pSrc = NULL;\n\tRTMP_OS_FD pSrcf;\n\tRTMP_OS_FS_INFO osFSInfo;\n\n\t\tif (IS_MT7615(pAd)) {\n\n#ifdef CONFIG_RT_FIRST_CARD\n\t\tif (pAd->dev_idx == 0) {\n\t\t\tpSrc = FIRST_CAL_BIN_FILE_PATH;\n\t\t} else\n#endif /* CONFIG_RT_FIRST_CARD */\n#ifdef CONFIG_RT_SECOND_CARD\n\t\tif (pAd->dev_idx == 1) {\n\t\t\tpSrc = SECOND_CAL_BIN_FILE_PATH;\n\t\t} else {\n#endif /* CONFIG_RT_SECOND_CARD */\n\t\t\tpSrc = CAL_BIN_FILE_PATH;\n#ifdef CONFIG_RT_SECOND_CARD\n\t\t}\n#endif /* CONFIG_RT_SECOND_CARD */\n\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t("\\x1b[32m%s: FileName = %s\\x1b[m\\n", __func__, pSrc));\n\n\t\t/* Change limits of authority in order to read/write file */\n\t\tRtmpOSFSInfoChange(&osFSInfo, TRUE);\n\n\t\t/* Create file descriptor */\n\t\tpSrcf = RtmpOSFileOpen(pSrc, O_RDONLY, 0);\n\t\tif (IS_FILE_OPEN_ERR(pSrcf)) {\n\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t("\\x1b[41m%s: Error opening %s\\x1b[m\\n", __func__, pSrc));\n\t\t\tgoto error;\n\t\t}\n\n\t\tRtmpOSFileSeek(pSrcf, Offset);\n\t\tretval = RtmpOSFileRead(pSrcf, (RTMP_STRING *)Buf, Len);\n\t\tif (retval < 0) {\n\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t("\\x1b[41m%s : Fail to load data from %s !!\\x1b[m\\n", __func__, pSrc));\n\t\t\tgoto error;\n\t\t}\n\n\t\t/* Close file descriptor */\n\t\tif (!IS_FILE_OPEN_ERR(pSrcf)) {\n\t\t\tretval = RtmpOSFileClose(pSrcf);\n\t\t\tif (retval) {\n\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t("\\x1b[41m%s: Error %d closing %s\\x1b[m\\n", __func__, -retval, pSrc));\n\t\t\t\tgoto error;\n\t\t\t}\n\t\t}\n\n\t\t/* Change limits of authority in order to read/write file */\n\t\tRtmpOSFSInfoChange(&osFSInfo, FALSE);\n\n\t\t/* Update status */\n\t\tStatus = NDIS_STATUS_SUCCESS;\n\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t\t("\\x1b[42m%s : Load data from %s success!!\\x1b[m\\n", __func__, pSrc));\n\n\t\treturn Status;\n\n\terror:\n\t\t/* Close file descriptor */\n\t\tif (!IS_FILE_OPEN_ERR(pSrcf)) {\n\t\t\tretval = RtmpOSFileClose(pSrcf);\n\t\t\tif (retval) {\n\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t("\\x1b[41m%s: Error %d closing %s\\x1b[m\\n", __func__, -retval, pSrc));\n\t\t\t}\n\t\t}\n\n\t\t/* Change limits of authority in order to read/write file */\n\t\tRtmpOSFSInfoChange(&osFSInfo, FALSE);\n\t}\n\treturn Status;\n}', 'Cal_Data_Write_To_Bin': 'INT Cal_Data_Write_To_Bin(\n\tIN PRTMP_ADAPTER pAd,\n\tIN UINT8 *Buf,\n\tIN UINT32 Offset,\n\tIN UINT32 Len)\n{\n\tINT32 retval, Status = NDIS_STATUS_FAILURE;\n\tRTMP_STRING *pSrc = NULL;\n\tRTMP_OS_FD pSrcf;\n\tRTMP_OS_FS_INFO osFSInfo;\n\n\tif (IS_MT7615(pAd)) {\n#ifdef CONFIG_RT_FIRST_CARD\n\t\tif (pAd->dev_idx == 0) {\n\t\t\tpSrc = FIRST_CAL_BIN_FILE_PATH;\n\t\t} else\n#endif /* CONFIG_RT_FIRST_CARD */\n#ifdef CONFIG_RT_SECOND_CARD\n\t\tif (pAd->dev_idx == 1) {\n\t\t\tpSrc = SECOND_CAL_BIN_FILE_PATH;\n\t\t} else {\n#endif /* CONFIG_RT_SECOND_CARD */\n\t\t\tpSrc = CAL_BIN_FILE_PATH;\n#ifdef CONFIG_RT_SECOND_CARD\n\t\t}\n#endif /* CONFIG_RT_SECOND_CARD */\n\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t("\\x1b[32m%s: FileName = %s\\x1b[m\\n", __func__, pSrc));\n\n\t\t/* Change limits of authority in order to read/write file */\n\t\tRtmpOSFSInfoChange(&osFSInfo, TRUE);\n\n\t\t/* Create file descriptor */\n\t\tpSrcf = RtmpOSFileOpen(pSrc, O_WRONLY|O_CREAT, 0);\n\t\tif (IS_FILE_OPEN_ERR(pSrcf)) {\n\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t("\\x1b[41m%s: Error opening %s\\x1b[m\\n", __func__, pSrc));\n\t\t\tgoto error;\n\t\t}\n\n\t\tRtmpOSFileSeek(pSrcf, Offset);\n\t\tretval = RtmpOSFileWrite(pSrcf, (RTMP_STRING *)Buf, Len);\n\t\tif (retval < 0) {\n\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t("\\x1b[41m%s : Fail to write data to %s !!\\x1b[m\\n", __func__, pSrc));\n\t\t\tgoto error;\n\t\t}\n\n\t\t/* Close file descriptor */\n\t\tif (!IS_FILE_OPEN_ERR(pSrcf)) {\n\t\t\tretval = RtmpOSFileClose(pSrcf);\n\t\t\tif (retval) {\n\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t("\\x1b[41m%s: Error %d closing %s\\x1b[m\\n", __func__, -retval, pSrc));\n\t\t\t\tgoto error;\n\t\t\t}\n\t\t}\n\n\t\t/* Change limits of authority in order to read/write file */\n\t\tRtmpOSFSInfoChange(&osFSInfo, FALSE);\n\n\t\t/* Update status */\n\t\tStatus = NDIS_STATUS_SUCCESS;\n\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t\t("\\x1b[42m%s: Store data to %s done !!\\x1b[m \\n", __func__, pSrc));\n\n\t\treturn Status;\n\n\terror:\n\t\t/* Close file descriptor */\n\t\tif (!IS_FILE_OPEN_ERR(pSrcf)) {\n\t\t\tretval = RtmpOSFileClose(pSrcf);\n\t\t\tif (retval) {\n\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t("\\x1b[41m%s: Error %d closing %s\\x1b[m\\n", __func__, -retval, pSrc));\n\t\t\t}\n\t\t}\n\n\t\t/* Change limits of authority in order to read/write file */\n\t\tRtmpOSFSInfoChange(&osFSInfo, FALSE);\n\t}\n\treturn Status;\n\n}', 'NICReadEEPROMParameters': 'INT NICReadEEPROMParameters(RTMP_ADAPTER *pAd, RTMP_STRING *mac_addr)\n{\n\tUSHORT i, value;\n\tEEPROM_VERSION_STRUC Version;\n\tEEPROM_ANTENNA_STRUC Antenna;\n\tEEPROM_NIC_CONFIG2_STRUC NicConfig2;\n\tUSHORT  Addr01, Addr23, Addr45;\n#ifdef PRE_CAL_TRX_SET2_SUPPORT\n\tUINT16 PreCalSize;\n#endif /* PRE_CAL_TRX_SET2_SUPPORT */\n#if defined(PRE_CAL_TRX_SET2_SUPPORT) || defined(PRE_CAL_MT7622_SUPPORT)\n\tUINT16 DoPreCal = 0;\n#endif /* PRE_CAL_TRX_SET2_SUPPORT */\n#if defined(CAL_BIN_FILE_SUPPORT) && defined(MT7615)\n\tUINT16 DoPATrim = 0;\n#endif /* CAL_BIN_FILE_SUPPORT */\n\tstruct _RTMP_CHIP_OP *ops = hc_get_chip_ops(pAd->hdev_ctrl);\n\n#ifdef PRE_CAL_MT7622_SUPPORT\n\tUINT32 ch;\n#endif /* PRE_CAL_MT7622_SUPPORT */\n\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s()-->\\n", __func__));\n\n\tif (ops->eeinit) {\n#if defined(WCX_SUPPORT)\n\t\t/* do nothing */\n#else\n\t\t/* If we are run in Multicard mode */\n\t\tif (ops->eeinit(pAd) != NDIS_STATUS_SUCCESS)\n\t\t\treturn FALSE;\n\t\tcheckAntCapSanity(pAd);\n#endif /*WCX_SUPPORT */\n#ifdef RF_LOCKDOWN\n\n\t\t/* Merge RF parameters in Effuse to E2p buffer */\n\t\tif (ops->merge_RF_lock_parameter != NULL)\n\t\t\tops->merge_RF_lock_parameter(pAd);\n\n\t\t/* Replace Country code and Country Region in Profile by Effuse content */\n\t\tif (ops->Config_Effuse_Country != NULL)\n\t\t\tops->Config_Effuse_Country(pAd);\n\n#endif /* RF_LOCKDOWN */\n\t}\n\n#ifdef PRE_CAL_MT7622_SUPPORT\n\tif (IS_MT7622(pAd)) {\n\t\t/* Check DoPreCal bits */\n\t\tRT28xx_EEPROM_READ16(pAd, 0x52, DoPreCal);\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t("\\x1b[34m%s: EEPROM 0x52 %x\\x1b[m\\n", __func__, DoPreCal));\n\t\tif (pAd->E2pAccessMode == E2P_FLASH_MODE) {\n\t\t\tif (DoPreCal & (1 << 3)) {\n\t\t\t\tMtCmdSetTxLpfCal_7622(pAd);\n\t\t\t\tMtCmdSetTxDcIqCal_7622(pAd);\n\t\t\t\tfor (ch = 1; ch < 14; ch++)\n\t\t\t\t\tMtCmdSetTxDpdCal_7622(pAd, ch);\n\t\t\t}\n\t\t}\n\t}\n#endif /*PRE_CAL_MT7622_SUPPORT*/\n\n#ifdef PRE_CAL_TRX_SET2_SUPPORT\n\n\tPreCalSize = PRE_CAL_SIZE_ONE_CARD;\n#ifdef CONFIG_RALINK_MT7621\n\t/* Litmit PreCalSize to 12k for MT7622 + MT7615 + MT7615 */\n#ifdef MULTI_INF_SUPPORT\n\tif (multi_inf_get_count() >= 2)\n\t\tPreCalSize = PRE_CAL_SIZE_DUAL_CARD;\n#endif /*MULTI_INF_SUPPORT*/\n#endif /*CONFIG_RALINK_MT7621*/\n\n\t/* Check DoPreCal bits */\n\tRT28xx_EEPROM_READ16(pAd, 0x52, DoPreCal);\n\n\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t ("\\x1b[34m%s: EEPROM 0x52 %x\\x1b[m\\n", __FUNCTION__, DoPreCal));\n\n\t/* Pre Cal only supports Bin or Flash Mode */\n\tif (pAd->E2pAccessMode == E2P_FLASH_MODE || pAd->E2pAccessMode == E2P_BIN_MODE) {\n\t/* Restore when RLM cache is empty */\n\t\tif (!rlmCalCacheDone(pAd->rlmCalCache) && (DoPreCal & (1 << 2))) {\n\t\t\tINT32 ret = 0;\n\t\t\tINT32 ret_cal_data = NDIS_STATUS_SUCCESS;\n\t\t\tret = os_alloc_mem(pAd, &pAd->PreCalReStoreBuffer, PreCalSize);/* Allocate 16K buffer*/\n\n\t\t\tif (ret != NDIS_STATUS_SUCCESS) {\n\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t ("\\x1b[42m %s : Not enough memory for pre-cal restored buffer!!\\x1b[m\\n", __FUNCTION__));\n\t\t\t} else {\n\t\t\t\t/* Read pre-cal data from flash and store to pre-cal buffer*/\n#ifdef RTMP_FLASH_SUPPORT\n\t\t\t\tif (pAd->E2pAccessMode == E2P_FLASH_MODE)\n\t\t\t\t\tRtmpFlashRead(pAd->hdev_ctrl, pAd->PreCalReStoreBuffer,\n\t\t\t\t\t\t\tget_dev_eeprom_offset(pAd) + PRECALPART_OFFSET, PreCalSize);\n#endif /* RTMP_FLASH_SUPPORT */\n\t\t\t\tif (pAd->E2pAccessMode == E2P_BIN_MODE) {\n\t\t\t\t\tret_cal_data = rtmp_cal_load_from_bin(pAd, pAd->PreCalReStoreBuffer, PRECALPART_OFFSET,\n\t\t\t\t\t\t\t\t\t\t PreCalSize);\n\n\t\t\t\t\tif (ret_cal_data != NDIS_STATUS_SUCCESS) {\n\t\t\t\t\t\t/* Erase DoPreCal bit */\n\t\t\t\t\t\tDoPreCal &= ~(1 << 2);\n\t\t\t\t\t\tRT28xx_EEPROM_WRITE16(pAd, 0x52, DoPreCal);\n\n\t\t\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t("Reset EEPROM 0x52[2] bit, Let FW do On-line Calibration\\n"));\n\t\t\t\t\t}\n\t\t\t\t}\n\n\t\t\t\tif (ret_cal_data == NDIS_STATUS_SUCCESS)\n\t\t\t\t\tret = MtCmdPreCalReStoreProc(pAd, (INT32 *)pAd->PreCalReStoreBuffer);\n\t\t\t}\n\t\t}\n\t} else {\n\t\t/* Force Erase DoPreCal bit for any mode other than Bin & Flash*/\n\t\tDoPreCal &= ~(1 << 2);\n\t\tRT28xx_EEPROM_WRITE16(pAd, 0x52, DoPreCal);\n\t}\n#endif /* PRE_CAL_TRX_SET2_SUPPORT */\n\n#if defined(CAL_BIN_FILE_SUPPORT) && defined(MT7615)\n\tif (IS_MT7615(pAd)) {\n\t\t/* Check DoPATrim bits */\n\t\tRT28xx_EEPROM_READ16(pAd, 0x52, DoPATrim);\n\n\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_OFF,\n\t\t\t\t("\\x1b[34m%s: EEPROM 0x52 %x\\x1b[m\\n", __func__, DoPATrim));\n\n\t\t/* Restore PA data when EEPROM 0x52[3]=1 */\n\t\tif (DoPATrim & (1 << 3)) {\n\t\t\tINT32 Status = NDIS_STATUS_FAILURE;\n\n\t\t\tStatus = MtCmdCalReStoreFromFileProc(pAd, CAL_RESTORE_PA_TRIM);\n\n\t\t\tif (Status != NDIS_STATUS_SUCCESS) {\n\t\t\t\tMTWF_LOG(DBG_CAT_ALL, DBG_SUBCAT_ALL, DBG_LVL_ERROR,\n\t\t\t\t\t\t("\\x1b[41m%s : Fail to restore PA data!!\\x1b[m\\n", __func__));\n\t\t\t}\n\t\t}\n\t}\n#endif /* CAL_BIN_FILE_SUPPORT */\n\n\n#ifdef MT_DFS_SUPPORT\t/*Dynamically enable or disable DFS calibration in firmware. Must be performed before power on calibration*/\n\tDfsSetCalibration(pAd, pAd->CommonCfg.DfsParameter.DisableDfsCal);\n#endif\n#ifdef MT_MAC\n#if defined(MT7603) || defined(MT7628) || defined(MT7636) || defined(MT7615) || defined(MT7637) || defined(MT7622)\n\t/*Send EEprom parameter to FW*/\n#ifdef CONFIG_ATE\n\n\tif (!ATE_ON(pAd))\n#endif\n\t{\n\t\t/*configure PA/LNA setting by efuse*/\n\t\tchip_pa_lna_set(pAd, pAd->EEPROMImage);\n\t\t/*configure TSSI sestting by efuse*/\n\t\tchip_tssi_set(pAd, pAd->EEPROMImage);\n\t\tif (IS_MT7603(pAd) || IS_MT7628(pAd) || IS_MT7636(pAd) || IS_MT7615(pAd) || IS_MT7637(pAd) || IS_MT7622(pAd))\n\t\t\tMtCmdEfusBufferModeSet(pAd, pAd->eeprom_type);\n\t}\n\n#endif /*#if defined(MT7603)||defined(MT7628)||defined(MT7636))||defined(MT7615)||defined(MT7622)*/\n#endif /* MT_MAC */\n\t/* Read MAC setting from EEPROM and record as permanent MAC address */\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Initialize MAC Address from E2PROM\\n"));\n\tRT28xx_EEPROM_READ16(pAd, 0x04, Addr01);\n\tRT28xx_EEPROM_READ16(pAd, 0x06, Addr23);\n\tRT28xx_EEPROM_READ16(pAd, 0x08, Addr45);\n\tpAd->PermanentAddress[0] = (UCHAR)(Addr01 & 0xff);\n\tpAd->PermanentAddress[1] = (UCHAR)(Addr01 >> 8);\n\tpAd->PermanentAddress[2] = (UCHAR)(Addr23 & 0xff);\n\tpAd->PermanentAddress[3] = (UCHAR)(Addr23 >> 8);\n\tpAd->PermanentAddress[4] = (UCHAR)(Addr45 & 0xff);\n\tpAd->PermanentAddress[5] = (UCHAR)(Addr45 >> 8);\n\n\t/*more conveninet to test mbssid, so ap\'s bssid &0xf1*/\n\tif (pAd->PermanentAddress[0] == 0xff)\n\t\tpAd->PermanentAddress[0] = RandomByte(pAd) & 0xf8;\n\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("E2PROM MAC: =%02x:%02x:%02x:%02x:%02x:%02x\\n",\n\t\t\t PRINT_MAC(pAd->PermanentAddress)));\n\n\t/* Assign the actually working MAC Address */\n\tif (pAd->bLocalAdminMAC) {\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE,\n\t\t\t\t ("Use the MAC address what is assigned from Configuration file(.dat).\\n"));\n#if defined(BB_SOC) && !defined(NEW_MBSSID_MODE)\n\t\t/* BBUPrepareMAC(pAd, pAd->CurrentAddress); */\n\t\tCOPY_MAC_ADDR(pAd->PermanentAddress, pAd->CurrentAddress);\n\t\tprintk("now bb MainSsid mac %02x:%02x:%02x:%02x:%02x:%02x\\n", PRINT_MAC(pAd->CurrentAddress));\n#endif\n\t} else if (mac_addr &&\n\t\t\t   strlen((RTMP_STRING *)mac_addr) == 17 &&\n\t\t\t   (strcmp(mac_addr, "00:00:00:00:00:00") != 0)) {\n\t\tINT j;\n\t\tRTMP_STRING *macptr;\n\t\tmacptr = (RTMP_STRING *) mac_addr;\n\n\t\tfor (j = 0; j < MAC_ADDR_LEN; j++) {\n\t\t\tAtoH(macptr, &pAd->CurrentAddress[j], 1);\n\t\t\tmacptr = macptr + 3;\n\t\t}\n\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Use the MAC address what is assigned from Moudle Parameter.\\n"));\n\t} else {\n\t\tCOPY_MAC_ADDR(pAd->CurrentAddress, pAd->PermanentAddress);\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("Use the MAC address what is assigned from EEPROM.\\n"));\n\t}\n\n\t/* if E2PROM version mismatch with driver\'s expectation, then skip*/\n\t/* all subsequent E2RPOM retieval and set a system error bit to notify GUI*/\n\tRT28xx_EEPROM_READ16(pAd, EEPROM_VERSION_OFFSET, Version.word);\n\tpAd->EepromVersion = Version.field.Version + Version.field.FaeReleaseNumber * 256;\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("E2PROM: Version = %d, FAE release #%d\\n", Version.field.Version,\n\t\t\t Version.field.FaeReleaseNumber));\n\t/* Read BBP default value from EEPROM and store to array(EEPROMDefaultValue) in pAd */\n\tRT28xx_EEPROM_READ16(pAd, EEPROM_NIC1_OFFSET, value);\n\tpAd->EEPROMDefaultValue[EEPROM_NIC_CFG1_OFFSET] = value;\n\t/* EEPROM offset 0x36 - NIC Configuration 1 */\n\tRT28xx_EEPROM_READ16(pAd, EEPROM_NIC2_OFFSET, value);\n\tpAd->EEPROMDefaultValue[EEPROM_NIC_CFG2_OFFSET] = value;\n\tNicConfig2.word = pAd->EEPROMDefaultValue[EEPROM_NIC_CFG2_OFFSET];\n\t{\n\t\tRT28xx_EEPROM_READ16(pAd, EEPROM_COUNTRY_REGION, value);\t/* Country Region*/\n\t\tpAd->EEPROMDefaultValue[EEPROM_COUNTRY_REG_OFFSET] = value;\n\t\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("Country Region from e2p = %x\\n", value));\n\t}\n\n\tfor (i = 0; i < 8; i++) {\n#if defined(RLT_MAC) || defined(MT_MAC)\n\n\t\t/* TODO: shiang-MT7603, replace below chip based check to this one!! */\n\t\tif (IS_HIF_TYPE(pAd, HIF_RLT) || IS_HIF_TYPE(pAd, HIF_MT))\n\t\t\tbreak;\n\n#endif /* defined(RLT_MAC) || defined(MT_MAC) */\n\t\tRT28xx_EEPROM_READ16(pAd, EEPROM_BBP_BASE_OFFSET + i * 2, value);\n\t\tpAd->EEPROMDefaultValue[i + EEPROM_BBP_ARRAY_OFFSET] = value;\n\t}\n\n\t/* We have to parse NIC configuration 0 at here. */\n\t/* If TSSI did not have preloaded value, it should reset the TxAutoAgc to false */\n\t/* Therefore, we have to read TxAutoAgc control beforehand. */\n\t/* Read Tx AGC control bit */\n\tAntenna.word = pAd->EEPROMDefaultValue[EEPROM_NIC_CFG1_OFFSET];\n\n\t/* TODO: shiang, why we only check oxff00?? */\n\tif (((Antenna.word & 0xFF00) == 0xFF00))\n\t\t/*\tif (Antenna.word == 0xFFFF)*/\n\t\tRTMP_CHIP_ANTENNA_INFO_DEFAULT_RESET(pAd, &Antenna);\n\n\t/* TODO: shiang-7603 */\n\t/* TODO: shiang-MT7615 */\n\tif (IS_MT7603(pAd) || IS_MT7628(pAd) || IS_MT76x6(pAd) || IS_MT7615(pAd) || IS_MT7637(pAd) || IS_MT7622(pAd) ||\n\t\tIS_P18(pAd) || IS_MT7663(pAd))\n\t\tRTMP_CHIP_ANTENNA_INFO_DEFAULT_RESET(pAd, &Antenna);\n\n#ifdef WSC_INCLUDED\n\n\t/* WSC hardware push button function 0811 */\n#ifdef VENDOR_FEATURE7_SUPPORT\n\tWSC_HDR_BTN_MR_HDR_SUPPORT_SET(pAd, 1);\t\t/* always enable PBC support */\n#else\n\tif ((pAd->MACVersion == 0x28600100) || (pAd->MACVersion == 0x28700100))\n\t\tWSC_HDR_BTN_MR_HDR_SUPPORT_SET(pAd, NicConfig2.field.EnableWPSPBC);\n#endif\n#endif /* WSC_INCLUDED */\n#ifdef CONFIG_AP_SUPPORT\n\tIF_DEV_CONFIG_OPMODE_ON_AP(pAd) {\n\t\tif (NicConfig2.word == 0xffff)\n\t\t\tNicConfig2.word = 0;\n\t}\n#endif /* CONFIG_AP_SUPPORT */\n\n\tif (NicConfig2.field.DynamicTxAgcControl == 1)\n\t\tpAd->bAutoTxAgcA = pAd->bAutoTxAgcG = TRUE;\n\telse\n\t\tpAd->bAutoTxAgcA = pAd->bAutoTxAgcG = FALSE;\n\n\t/* Save value for future using */\n\tpAd->NicConfig2.word = NicConfig2.word;\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s(): RxPath = %d, TxPath = %d, RfIcType = %d\\n",\n\t\t\t __func__, Antenna.field.RxPath, Antenna.field.TxPath,\n\t\t\t Antenna.field.RfIcType));\n\t/* Save the antenna for future use*/\n\tpAd->Antenna.word = Antenna.word;\n\t/* Set the RfICType here, then we can initialize RFIC related operation callbacks*/\n\tpAd->Mlme.RealRxPath = (UCHAR) Antenna.field.RxPath;\n\tpAd->RfIcType = (UCHAR) Antenna.field.RfIcType;\n#ifdef MT7615\n\n\t/* TODO: shiang-MT7615 */\n\tif (IS_MT7615(pAd)) {\n\t\tPOS_COOKIE pObj = (POS_COOKIE) pAd->OS_Cookie;\n\n\t\tif (pObj->DeviceID == NIC7611_PCIe_DEVICE_ID)\n\t\t\tpAd->RfIcType = RFIC_7611;\n\t\telse if (pObj->DeviceID == NIC761A_PCIe_DEVICE_ID)\n\t\t\tpAd->RfIcType = RFIC_7615A;\n\t\telse\n\t\t\tpAd->RfIcType = RFIC_7615;\n\t}\n\n#endif /* MT7615 */\n#ifdef MT7622\n\n\tif (IS_MT7622(pAd))\n\t\tpAd->RfIcType = RFIC_7622;\n\n#endif /* MT7622 */\n\n\t/* TODO: shiang-MT7615, how about the EEPROM value of MT series chip?? */\n\tif (!IS_MT7615(pAd) && !IS_MT7622(pAd) && !IS_P18(pAd) && !IS_MT7663(pAd)) {\n\t\tLoadTssiInfoFromEEPROM(pAd);\n\t\tpAd->BbpRssiToDbmDelta = 0x0;\n\t\trtmp_read_freq_offset_from_eeprom(pAd);\n\t\trtmp_read_country_region_from_eeporm(pAd);\n\t\trtmp_read_rssi_langain_from_eeprom(pAd);\n\t}\n\n#ifdef LED_CONTROL_SUPPORT\n\trtmp_read_led_setting_from_eeprom(pAd);\n#endif /* LED_CONTROL_SUPPORT */\n\trtmp_read_txpwr_from_eeprom(pAd);\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s: pAd->Antenna.field.BoardType = %d\\n",\n\t\t\t __func__,\n\t\t\t pAd->Antenna.field.BoardType));\n\tMTWF_LOG(DBG_CAT_HW, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("<--%s()\\n", __func__));\n\treturn TRUE;\n}'}
BASELINE_FUNCTIONS_SHA256 = {'RtmpOSFileClose': '13a6fc13c16e376db84ec5c19498e95bca13de70ef60de630546adcebc20bd6a', 'rtmp_cal_load_from_bin': 'e3ab568eba9b405c3da11b3cbfa26604eb7c6a36e0b6d8be7074284192dc64c3', 'rtmp_cal_write_to_bin': '51703c4eefdec589b6d34e17f881d4f3b434dfd4420df9b929ef2b1a602a8d19', 'Cal_Data_Load_From_Bin': '020b4763a6efadab8e7cae73033772e1f20084e37629a5367a909472cd883720', 'Cal_Data_Write_To_Bin': '33a36b5e5f9001be3c51841e8a00b45e9dea2cb74059e3cc28e10c32d8ec98f3', 'NICReadEEPROMParameters': '053c48deb7195143291d8616a9c0d5b184f56b071c1f92a3f33c2aba644c0fc4'}
