"""Unconfigured META source variant under inert user-copy/BIN seams.

Three complete source functions run, not the otherwise unconfigured META
translation unit or a shipped object. The old missing NVRAM typedef is supplied
only as a model alias to the actual packed EEPROM wire declaration. Unsafe old
width/dispatcher cases are reserved for native ASan failure witnesses.
"""
import hashlib
import re

BASELINE_COMMIT='3a404e1675467cab79af0ffac454061c1e9150ae'
SOURCE_PATHS={'meta':'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/ate/meta_agent.c',
             'header':'trunk/linux-4.4.x/drivers/net/wireless/mediatek/mt7615/ate/include/meta_agent.h'}
FUNCTION_SOURCES={'resp_to_meta':'meta','oid_nvram_rw':'meta','do_meta_cmd':'meta'}
CASE_NAMES=('set-low','set-high','query-high','getsize-null','invalid-method','short-payload',
 'truncated-total','oversized-total','oversized-inner','null-image','short-image',
 'write-error','copyin-error','copyout-error','stub-error','null-wrq','invalid-ioctl',
 'response-too-long','response-too-small-cap','response-zero')
BASELINE_CASES=('stub-error','response-zero')
DISABLED_CASES=('set-low','stub-error')

def function(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    found=list(re.finditer(r'^(?:static\s+)?INT32\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',masked,re.M))
    if len(found)!=1:raise ValueError('Missing/ambiguous META function '+name)
    start=found[0].start();opening=text.index('{',start);depth=0
    for token in re.finditer(tokens+r'|[{}]',text[opening:]):
        if token.group()=='{':depth+=1
        elif token.group()=='}':
            depth-=1
            if not depth:return text[start:opening+token.end()]
    raise ValueError('Unterminated META function '+name)

def declarations(header):
    result=[]
    for name in('_META_CMD_HDR','_PARAM_CUSTOM_EEPROM_RW'):
        matches=re.findall(r'struct GNU_PACKED '+name+r'\s*\{[^{}]*\};',header)
        if len(matches)!=1:raise ValueError('Missing packed META protocol '+name)
        result.append(matches[0])
    return '\n'.join(result)

PREFIX=r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
typedef uint8_t UINT8;typedef uint16_t UINT16;typedef uint32_t UINT32;typedef int32_t INT32;typedef unsigned char UCHAR;typedef UCHAR*PUCHAR;typedef char RTMP_STRING;
#define GNU_PACKED __attribute__((packed))
#define MTPRIV_IOCTL_META_SET 0x8be8
#define MTPRIV_IOCTL_META_QUERY 0x8be9
#define PARAM_EEPROM_READ_METHOD_READ 1
#define PARAM_EEPROM_READ_METHOD_GETSIZE 0
#define NDIS_STATUS_SUCCESS 0
#define NDIS_STATUS_FAILURE 1
#define NDIS_STATUS_INVALID_DATA 2
#define EEPROM_SIZE 512
#define _DUMP_HEX_ 1
#define DBG_CAT_TEST 0
#define DBG_SUBCAT_ALL 0
#define DBG_LVL_TRACE 0
#define DBG_LVL_ERROR 0
#define DBG_LVL_OFF 0
static int logs;
static void model_log(const char*format,...){char output[1024];va_list args;va_start(args,format);vsnprintf(output,sizeof(output),format,args);va_end(args);logs++;}
#define MTWF_LOG(a,b,c,args) do{model_log args;}while(0)
typedef struct _RTMP_ADAPTER {UCHAR*EEPROMImage;UINT32 image_size;}RTMP_ADAPTER,*PRTMP_ADAPTER;
typedef struct{union{struct{void*pointer;unsigned short length;}data;}u;}RTMP_IOCTL_INPUT_STRUCT;
static const char*case_name;static int copies_in,copies_out,allocs,frees,writes;
static int selected(const char*s){return !strcmp(case_name,s);}
static UINT32 get_dev_eeprom_size(PRTMP_ADAPTER a){return a->image_size;}
static int rtmp_ee_write_to_bin(PRTMP_ADAPTER a){(void)a;writes++;return !selected("write-error");}
static void os_alloc_mem_suspend(PRTMP_ADAPTER a,UCHAR**p,size_t n){void*value;(void)a;value=malloc(n);memcpy(p,&value,sizeof(value));if(value)allocs++;}
static void os_free_mem(void*p){if(p){frees++;free(p);}}
#define os_zero_mem(p,n) memset(p,0,n)
static int copy_from_user(void*d,const void*s,size_t n){copies_in++;if(selected("copyin-error"))return 1;memcpy(d,s,n);return 0;}
static int copy_to_user(void*d,const void*s,size_t n){copies_out++;if(selected("copyout-error"))return 1;memcpy(d,s,n);return 0;}
#define OID_CUSTOM_IF_VER 0xFFA0C000
#define OID_CUSTOM_MCR_RW 0xFFA0C801
#define OID_CUSTOM_EEPROM_RW 0xFFA0C803
#define OID_CUSTOM_EFUSE_RW 0xFFA0C805
#define OID_CUSTOM_TEST_MODE 0xFFA0C901
#define OID_CUSTOM_ABORT_TEST_MODE 0xFFA0C906
#define OID_CUSTOM_MTK_WIFI_TEST 0xFFA0C911
#define OID_CUSTOM_CFG_SRC_TYPE 0xFFA0C942
#define OID_CUSTOM_EEPROM_TYPE 0xFFA0C943
#define OID_CUSTOM_MTK_NVRAM_RW 0xFFA0C941
'''

DISPATCH=r'''
static INT32 stub_oid(INT32 c,PRTMP_ADAPTER a,RTMP_IOCTL_INPUT_STRUCT*w,struct _META_CMD_HDR*h){(void)c;(void)a;(void)w;(void)h;return 17;}
typedef INT32(*META_CMD_HANDLER)(INT32,PRTMP_ADAPTER,RTMP_IOCTL_INPUT_STRUCT*,struct _META_CMD_HDR*);
static META_CMD_HANDLER OID_HANDLE[]={stub_oid,stub_oid,stub_oid,stub_oid,stub_oid,stub_oid,stub_oid,stub_oid,stub_oid,oid_nvram_rw};
'''

TAIL=r'''
int main(int argc,char**argv){
 unsigned char user[sizeof(struct _META_CMD_HDR)+32],image[512];
 struct _META_CMD_HDR*h=(struct _META_CMD_HDR*)user;
 struct _PARAM_CUSTOM_EEPROM_RW*c=(struct _PARAM_CUSTOM_EEPROM_RW*)h->data;
 RTMP_ADAPTER a;RTMP_IOCTL_INPUT_STRUCT w;INT32 status;UINT16 value=0xabcd;int command=MTPRIV_IOCTL_META_SET;
 if(argc!=2)return 90;
 case_name=argv[1];memset(user,0,sizeof(user));memset(image,0xee,sizeof(image));memset(&w,0,sizeof(w));
 image[0]=0x12;image[1]=0x34;image[510]=0x56;image[511]=0x78;
 a.EEPROMImage=image;a.image_size=sizeof(image);w.u.data.pointer=user;w.u.data.length=12+sizeof(*c);
 h->oid=OID_CUSTOM_MTK_NVRAM_RW;h->len_in=sizeof(*c);h->len_out=sizeof(*c);c->method=1;memcpy(&c->data,&value,sizeof(value));h->data[5]=0xa5;h->data[6]=0x5a;
 if(selected("set-high")||selected("query-high"))c->idx=255;
 if(selected("query-high")||selected("getsize-null")){command=MTPRIV_IOCTL_META_QUERY;}
 if(selected("getsize-null")){c->method=0;a.EEPROMImage=NULL;}
 if(selected("invalid-method"))c->method=9;
 if(selected("short-payload")){w.u.data.length=16;h->len_in=h->len_out=4;}
 if(selected("truncated-total"))w.u.data.length=11;
 if(selected("oversized-total"))w.u.data.length=sizeof(user);
 if(selected("oversized-inner"))h->len_in=2049;
 if(selected("null-image"))a.EEPROMImage=NULL;
 if(selected("short-image")){c->idx=255;a.image_size=511;}
 if(selected("stub-error"))h->oid=OID_CUSTOM_IF_VER;
 if(selected("invalid-ioctl"))command=0;
 if(selected("response-too-long")){w.u.data.length=sizeof(*h);status=resp_to_meta(command,h,&w,2049,0);}
 else if(selected("response-too-small-cap")){w.u.data.length=16;status=resp_to_meta(command,h,&w,5,0);}
 else if(selected("response-zero")){w.u.data.length=12;status=resp_to_meta(command,h,&w,0,0);}
 else status=do_meta_cmd(command,&a,selected("null-wrq")?NULL:&w,NULL);
 memcpy(&value,&c->data,sizeof(value));
 printf("{\"case\":\"%s\",\"status\":%d,\"copies_in\":%d,\"copies_out\":%d,\"allocs\":%d,\"frees\":%d,\"writes\":%d,\"response_len\":%u,\"response_value\":%u,\"low_hi\":%u,\"low_lo\":%u,\"high_hi\":%u,\"high_lo\":%u,\"tail_intact\":%d}\n",case_name,status,copies_in,copies_out,allocs,frees,writes,w.u.data.length,value,image[0],image[1],image[510],image[511],h->data[5]==0xa5&&h->data[6]==0x5a);
 return 0;
}
'''

def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False,disabled_oracle=False):
    if set(texts)!=set(SOURCE_PATHS)or type(baseline)is not bool or type(disabled_oracle)is not bool:
        raise ValueError('Exact META source/profile mapping required')
    functions={name:function(texts[key],name)for name,key in FUNCTION_SOURCES.items()}
    if baseline:
        if {n:hashlib.sha256(b.encode()).hexdigest()for n,b in BASELINE_FUNCTIONS.items()}!=BASELINE_FUNCTIONS_SHA256:
            raise ValueError('META old body bytes changed')
        functions=dict(BASELINE_FUNCTIONS)
    if disabled_oracle:
        functions={name:body[:body.index('{')]+'{return 0;}'for name,body in functions.items()}
    protocol=declarations(texts['header'])
    alias='\ntypedef struct _PARAM_CUSTOM_EEPROM_RW PARAM_CUSTOM_NVRAM_RW;\n'
    return PREFIX+protocol+alias+functions['resp_to_meta']+'\n'+functions['oid_nvram_rw']+'\n'+DISPATCH+functions['do_meta_cmd']+'\n'+TAIL

BASELINE_FUNCTIONS = {'resp_to_meta': 'static INT32 resp_to_meta(INT32 ioctl_cmd, struct _META_CMD_HDR *rsp, RTMP_IOCTL_INPUT_STRUCT *wrq, INT32 len, INT32 status)\n{\n\tif (ioctl_cmd == MTPRIV_IOCTL_META_SET)\n\t\trsp->len_in = len;\n\telse if (ioctl_cmd == MTPRIV_IOCTL_META_QUERY)\n\t\trsp->len_out = len;\n\n\twrq->u.data.length = sizeof(rsp->oid) + sizeof(rsp->len_in) + sizeof(rsp->len_out) + len;\n\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE,   ("WRQ->u.data.length = %u, oid: %lu, rsp: %lu, rsp->len: 0x%x\\n", wrq->u.data.length, sizeof(rsp->oid), sizeof(rsp->len_in), len));\n\n\tif (copy_to_user(wrq->u.data.pointer, (UCHAR *)(rsp), wrq->u.data.length)) {\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("copy_to_user() fail in %s\\n", __func__));\n\t\treturn -EFAULT;\n\t}\n\n#ifdef _DUMP_HEX_\n\t{\n\t\tUCHAR *pSrcBufVA = wrq->u.data.pointer;\n\t\tUINT32 SrcBufLen = wrq->u.data.length;\n\t\tunsigned char *pt;\n\t\tINT32 x;\n\n\t\tpt = pSrcBufVA;\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s: %p, len = %d\\n", "META_IOCTL Ret Content", pSrcBufVA, SrcBufLen));\n\n\t\tfor (x = 0; x < SrcBufLen; x++) {\n\t\t\tif (x % 16 == 0)\n\t\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("0x%04x : ", x));\n\n\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%02x ", ((unsigned char)pt[x])));\n\n\t\t\tif (x % 16 == 15)\n\t\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("\\n", __func__));\n\t\t}\n\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s\\n", __func__));\n\t}\n#endif\n\treturn 0;\n}', 'oid_nvram_rw': 'static INT32 oid_nvram_rw(INT32 ioctl_cmd, PRTMP_ADAPTER pAd, RTMP_IOCTL_INPUT_STRUCT *WRQ, struct _META_CMD_HDR *cmd_hdr)\n{\n\tPARAM_CUSTOM_NVRAM_RW *cmd = (PARAM_CUSTOM_NVRAM_RW *)cmd_hdr->data;\n\tINT32 status = NDIS_STATUS_SUCCESS;\n\tUINT16 value = 0;\n\tUINT8 idx = cmd->idx << 1;\n\n\tif (ioctl_cmd == MTPRIV_IOCTL_META_SET) {\n\t\tmemcpy((PUCHAR)&value, &cmd->data, 4);\n\t\tpAd->EEPROMImage[idx] = (0xff00 & value) >> 8;\n\t\tpAd->EEPROMImage[idx + 1] = (0x00ff & value);\n\t\trtmp_ee_write_to_bin(pAd);\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s-SET, method:0x%x ,offset:0x%x, valu:0x%x, EEPROMImage:0x%x\\n", __func__, cmd->method, idx, value, pAd->EEPROMImage[idx]));\n\t} else if (ioctl_cmd == MTPRIV_IOCTL_META_QUERY) {\n\t\tif (cmd->method == PARAM_EEPROM_READ_METHOD_READ) {\n\t\t\tvalue |= pAd->EEPROMImage[idx];\n\t\t\tvalue <<= 8;\n\t\t\tvalue |= pAd->EEPROMImage[idx + 1];\n\t\t} else if (cmd->method == PARAM_EEPROM_READ_METHOD_GETSIZE)\n\t\t\tvalue = EEPROM_SIZE;\n\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE,  ("%s-QUREY, method:0x%x ,offset:0x%x, valu:0x%x\\n", __func__, cmd->method, idx, value));\n\t} else {\n\t}\n\n\tmemcpy(&cmd->data, &value, 4);\n\tstatus =  resp_to_meta(ioctl_cmd, cmd_hdr, WRQ, sizeof(*cmd), status);\n\treturn status;\n}', 'do_meta_cmd': 'INT32 do_meta_cmd(INT32 ioctl_cmd, PRTMP_ADAPTER\tpAd, RTMP_IOCTL_INPUT_STRUCT *WRQ, RTMP_STRING *wrq_name)\n{\n\tINT32 Status = NDIS_STATUS_SUCCESS;\n\tstruct _META_CMD_HDR *cmd_hdr;\n\tUINT32 oid = 0;\n\tINT32 ret = 0;\n\n\tos_alloc_mem_suspend(pAd, (UCHAR **)&cmd_hdr, sizeof(*cmd_hdr));\n\n\tif (!cmd_hdr) {\n\t\tStatus = -ENOMEM;\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE,   ("%s, cmd_hdr NULL\\n", __func__));\n\t\tgoto ERROR0;\n\t}\n\n\tif (!WRQ) {\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE,   ("%s. wrq is null\\n", __func__));\n\t\tgoto ERROR0;\n\t}\n\n\tos_zero_mem(cmd_hdr, sizeof(*cmd_hdr));\n\tStatus = copy_from_user((PUCHAR)cmd_hdr, WRQ->u.data.pointer, WRQ->u.data.length);\n#ifdef _DUMP_HEX_\n\t{\n\t\tUCHAR *pSrcBufVA = WRQ->u.data.pointer;\n\t\tUINT32 SrcBufLen = WRQ->u.data.length;\n\t\tunsigned char *pt;\n\t\tINT32 x;\n\n\t\tpt = pSrcBufVA;\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%s: %p, len = %d\\n",\n\t\t\t\t "META_IOCTL Content", pSrcBufVA, SrcBufLen));\n\n\t\tfor (x = 0; x < SrcBufLen; x++) {\n\t\t\tif (x % 16 == 0)\n\t\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("0x%04x : ", x));\n\n\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("%02x ", (unsigned char)pt[x]));\n\n\t\t\tif (x % 16 == 15)\n\t\t\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("\\n"));\n\t\t}\n\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_OFF, ("\\n"));\n\t}\n#endif\n\n\tif (Status) {\n\t\tStatus = -EFAULT;\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s, copy_from_user error\\n", __func__));\n\t\tgoto ERROR1;\n\t}\n\n\toid = cmd_hdr->oid;\n\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_TRACE, ("%s() ==>,OID:0x%x, len:0x%x\\n", __func__, oid, WRQ->u.data.length));\n\n\tswitch (oid) {\n\tcase OID_CUSTOM_IF_VER:\n\t\tret = (*OID_HANDLE[0])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_MCR_RW:\n\t\tret = (*OID_HANDLE[1])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_EEPROM_RW:\n\t\tret = (*OID_HANDLE[2])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_EFUSE_RW:\n\t\tret = (*OID_HANDLE[3])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_TEST_MODE:\n\t\tret = (*OID_HANDLE[4])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_ABORT_TEST_MODE:\n\t\tret = (*OID_HANDLE[5])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_MTK_WIFI_TEST:\n\t\tret = (*OID_HANDLE[6])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_CFG_SRC_TYPE:\n\t\tret = (*OID_HANDLE[7])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_EEPROM_TYPE:\n\t\tret = (*OID_HANDLE[8])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tcase OID_CUSTOM_MTK_NVRAM_RW:\n\t\tret = (*OID_HANDLE[9])(ioctl_cmd, pAd, WRQ, cmd_hdr);\n\t\tbreak;\n\n\tdefault:\n\t\tStatus = NDIS_STATUS_FAILURE;\n\t\tMTWF_LOG(DBG_CAT_TEST, DBG_SUBCAT_ALL, DBG_LVL_ERROR, ("Unknown oid number of AT command = %x\\n", oid));\n\t\tgoto ERROR1;\n\t}\n\nERROR1:\n\tos_free_mem(cmd_hdr);\nERROR0:\n\treturn Status;\n}'}
BASELINE_FUNCTIONS_SHA256 = {'resp_to_meta': '2d39eb026101bc70de0e659416fb6e7ec998659d57c44714d908a89c4b3b33b1', 'oid_nvram_rw': '3a175d73c66d831ffb13c982bdda8af4107f7727ee012221776c311d0d860a29', 'do_meta_cmd': '810422898d825c3c44542b4ded65103c4276e9ef38091318c20f66a283b4f9dd'}
