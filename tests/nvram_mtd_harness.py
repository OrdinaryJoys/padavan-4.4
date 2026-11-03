"""Pure actual NVRAM/WiFi MTD adapter with inert RAM and completion callbacks.

No MTD, proc, reboot, configuration or host device operation is performed.
The old range-overrun ASan control is deliberately outside target pass cases.
"""
import hashlib
import re

SOURCE_PATHS = {'nvram_mtd': 'trunk/linux-4.4.x/drivers/net/wireless/wifi_utility/mt_wifi_mtd.c'}
BASELINE_COMMIT = '6e91276a33d1bd83d416fc8253feb01f30677743'
FUNCTIONS = ('mt_mtd_erase_complete_wifi', 'mt_mtd_write_nm_wifi', 'mt_mtd_read_nm_wifi')
CASE_NAMES = (
 'write-ok', 'write-offset', 'write-boundary', 'write-negative', 'write-past-block',
 'write-overflow', 'write-too-large', 'write-zero', 'write-zero-end', 'write-null',
 'write-name-null', 'write-zero-erase', 'write-small-device', 'write-lookup-failure',
 'write-allocation-failure', 'write-read-error', 'write-short-read', 'write-erase-error',
 'write-erase-failed-state', 'write-async', 'write-async-failed', 'write-io-error',
 'write-short-io', 'read-ok', 'read-offset', 'read-negative', 'read-overflow',
 'read-past-end', 'read-short', 'read-io-error', 'read-zero-end', 'read-lookup-failure',
)
BASELINE_CASES = ('write-ok', 'write-offset', 'write-short-read', 'write-short-io',
                  'write-async', 'write-async-failed', 'read-ok', 'read-short',
                  'read-io-error', 'read-lookup-failure')
DISABLED_CASES = ('write-ok', 'write-short-read')


def function(text, name):
    matches = list(re.finditer(r'^(?:static )?(?:int|void) '+re.escape(name)+r'\([^;]+?\)\n\{', text, re.M))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous actual backend function '+name)
    start = matches[0].start()
    body = text.index('{', matches[0].start())
    depth = 1
    for position in range(body+1, len(text)):
        depth += (text[position] == '{') - (text[position] == '}')
        if depth == 0:
            return text[start:position+1]
    raise ValueError('Unterminated backend function')


def actual_functions(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact NVRAM backend source keys required')
    return {name: {'source': 'nvram_mtd', 'body': function(texts['nvram_mtd'], name)}
            for name in FUNCTIONS}


PREFIX = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#define loff_t long long
typedef uint64_t u64;
#define u_char unsigned char
/* The mock backend returns the target Linux errno, also on macOS hosts. */
#undef EBADMSG
#define EBADMSG 74
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(4,4,302)
#define GFP_KERNEL 0
#define MTD_ERASE_DONE 8
#define MTD_ERASE_FAILED 16
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define PTR_ERR(p) ((long)(p))
#define printk(...) ((void)0)
struct mtd_info {uint64_t size;uint32_t erasesize;};
struct erase_info {struct mtd_info*mtd;uint64_t addr,len;void(*callback)(struct erase_info*);unsigned long priv;unsigned char state;};
struct completion {unsigned int done;};
#define DECLARE_COMPLETION_ONSTACK(name) struct completion name={0}
static const char*case_name;
static struct mtd_info device;
static struct erase_info*pending;
static u_char flash[32];
static int get_count,puts_count,allocs,frees_count,reads,erases,writes,waits,premature;
static char trace[256];
static int is(const char*n){return !strcmp(case_name,n);}
static void event(const char*s){if(strlen(trace)+strlen(s)+2>=sizeof(trace))abort();if(*trace)strcat(trace,",");strcat(trace,s);}
static void complete(struct completion*c){event("complete");c->done++;}
static struct mtd_info*get_mtd_device_nm(const char*n){
 (void)n;get_count++;event("get");if(is("write-lookup-failure")||is("read-lookup-failure"))return (void*)(intptr_t)-ENODEV;return &device;
}
static void put_mtd_device(struct mtd_info*m){if(m!=&device)abort();puts_count++;event("put");}
static void*kmalloc(size_t n,int flags){void*p;(void)flags;allocs++;event("alloc");if(is("write-allocation-failure"))return NULL;p=malloc(n);if(p)memset(p,0xcc,n);return p;}
static void kfree(void*p){if(p){frees_count++;event("free");free(p);}}
static int mtd_read(struct mtd_info*m,loff_t from,size_t len,size_t*out,u_char*buf){
 size_t n=len;(void)m;reads++;event("read");*out=0;
 if(is("write-read-error")||is("read-io-error"))return -EBADMSG;
 if(is("write-short-read")||is("read-short"))n=len-1;
 if(from<0||(uint64_t)from>sizeof(flash)||n>sizeof(flash)-(uint64_t)from)return -EINVAL;
 memcpy(buf,flash+(size_t)from,n);*out=n;return 0;
}
static void finish(struct erase_info*ei){
 ei->state=(is("write-erase-failed-state")||is("write-async-failed"))?MTD_ERASE_FAILED:MTD_ERASE_DONE;
 if(ei->state==MTD_ERASE_DONE)memset(flash,0xff,(size_t)ei->len);
 if(ei->callback)ei->callback(ei);
}
static int mtd_erase(struct mtd_info*m,struct erase_info*ei){
 (void)m;erases++;event("erase");if(is("write-erase-error"))return -EIO;
 if(is("write-async")||is("write-async-failed")){pending=ei;return 0;}
 finish(ei);return 0;
}
static void wait_for_completion(struct completion*c){
 waits++;event("wait");if(pending){struct erase_info*ei=pending;pending=NULL;finish(ei);}if(!c->done)abort();c->done--;
}
static int mtd_write(struct mtd_info*m,loff_t to,size_t len,size_t*out,const u_char*buf){
 size_t n=len;(void)m;writes++;event("write");*out=0;if(pending)premature++;
 if(is("write-io-error"))return -EROFS;
 if(is("write-short-io"))n=len-1;
 if(to<0||(uint64_t)to>sizeof(flash)||n>sizeof(flash)-(uint64_t)to)return -EINVAL;
 memcpy(flash+(size_t)to,buf,n);*out=n;return 0;
}
'''

MAIN = r'''
int main(int argc,char**argv){
 u_char input[32],output[32];const u_char*buf=input;char*name="Config";loff_t offset=0;size_t len=4;int result,i,known=0;
 if(argc!=2)return 90;
 case_name=argv[1];
 CASE_ADMISSION
 if(!known)return 91;
 memset(output,0,sizeof(output));for(i=0;i<32;i++){flash[i]=(u_char)i;input[i]=(u_char)(0xa0+i);}
 device.size=32;device.erasesize=16;
 if(is("write-offset")||is("read-offset"))offset=8;
 if(is("write-boundary"))offset=12;
 if(is("write-negative")||is("read-negative"))offset=-1;
 if(is("write-past-block"))offset=16;
 if(is("write-overflow")||is("read-overflow"))offset=LLONG_MAX;
 if(is("write-too-large"))len=17;
 if(is("write-zero")||is("write-zero-end")||is("read-zero-end"))len=0;
 if(is("write-zero-end"))offset=16;
 if(is("read-zero-end"))offset=32;
 if(is("write-null"))buf=NULL;
 if(is("write-name-null"))name=NULL;
 if(is("write-zero-erase"))device.erasesize=0;
 if(is("write-small-device"))device.size=8;
 if(is("read-past-end"))offset=30;
 if(!strncmp(case_name,"read-",5))result=mt_mtd_read_nm_wifi(name,offset,len,output);
 else result=mt_mtd_write_nm_wifi(name,offset,len,buf);
 printf("{\"case\":\"%s\",\"result\":%d,\"trace\":\"%s\",\"gets\":%d,\"puts\":%d,\"allocs\":%d,\"frees\":%d,\"reads\":%d,\"erases\":%d,\"writes\":%d,\"waits\":%d,\"premature\":%d,\"byte0\":%u,\"byte8\":%u,\"byte15\":%u}\n",case_name,result,trace,get_count,puts_count,allocs,frees_count,reads,erases,writes,waits,premature,flash[0],flash[8],flash[15]);
 return 0;
}
'''


def generate_source(texts, fixture_root=None, owner_uid=0, baseline=False, disabled_oracle=False):
    if (set(texts) != set(SOURCE_PATHS) or type(baseline) is not bool or
            type(disabled_oracle) is not bool or (baseline and disabled_oracle)):
        raise ValueError('Exact backend source keys and typed profile required')
    functions = actual_functions(texts)
    for name, body in BASELINE_FUNCTIONS.items():
        if hashlib.sha256(body.encode()).hexdigest() != BASELINE_FUNCTIONS_SHA256[name]:
            raise ValueError('Changed fixed NVRAM backend baseline')
    if baseline:
        bodies = '\n'.join(BASELINE_FUNCTIONS.values())
    elif disabled_oracle:
        bodies = ('int mt_mtd_write_nm_wifi(char*n,loff_t o,size_t l,const u_char*b){(void)n;(void)o;(void)l;(void)b;return 0;}\n'
                  'int mt_mtd_read_nm_wifi(char*n,loff_t o,size_t l,u_char*b){(void)n;(void)o;(void)l;(void)b;return 0;}')
    else:
        bodies = '\n'.join(item['body'] for item in functions.values())
    names = CASE_NAMES+('write-overrun-control',)
    admission = '\n'.join('if(!strcmp(case_name,"'+name+'"))known=1;' for name in names)
    main = MAIN.replace('CASE_ADMISSION',admission).replace(
        'if(is("write-past-block"))offset=16;',
        'if(is("write-past-block")||is("write-overrun-control"))offset=16;')
    return PREFIX+'\n'+bodies+'\n'+main


# Immutable literal old bodies and their reviewed hashes are appended below.
BASELINE_FUNCTIONS = {'mt_mtd_write_nm_wifi': 'int mt_mtd_write_nm_wifi(char *name, loff_t to, size_t len, const u_char *buf)\n{\n\tint ret = -1;\n\tsize_t rdlen, wrlen;\n\tstruct mtd_info *mtd;\n\tstruct erase_info ei;\n\tu_char *bak = NULL;\n\n\tmtd = get_mtd_device_nm(name);\n\tif (IS_ERR(mtd))\n\t\treturn -1;\n\n\tif (len > mtd->erasesize) {\n\t\tput_mtd_device(mtd);\n\t\treturn -E2BIG;\n\t}\n\n\tbak = kmalloc(mtd->erasesize, GFP_KERNEL);\n\tif (bak == NULL) {\n\t\tput_mtd_device(mtd);\n\t\treturn -ENOMEM;\n\t}\n\n\tret = mtd_read(mtd, 0, mtd->erasesize, &rdlen, bak);\n\n\tif (ret != 0) {\n\t\tput_mtd_device(mtd);\n\t\tkfree(bak);\n\t\treturn ret;\n\t}\n\n\tif (rdlen != mtd->erasesize)\n\t\tprintk("warning: ra_mtd_write: rdlen is not equal to erasesize\\n");\n\n\tmemcpy(bak + to, buf, len);\n\n#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))\n\tei.mtd = mtd;\n\tei.callback = NULL;\n\tei.priv = 0;\n#endif\n\tei.addr = 0;\n\tei.len = mtd->erasesize;\n\tret = mtd_erase(mtd, &ei);\n\n\tif (ret != 0) {\n\t\tput_mtd_device(mtd);\n\t\tkfree(bak);\n\t\treturn ret;\n\t}\n\n\tret = mtd_write(mtd, 0, mtd->erasesize, &wrlen, bak);\n\n\n\n\tput_mtd_device(mtd);\n\tkfree(bak);\n\treturn ret;\n}', 'mt_mtd_read_nm_wifi': 'int mt_mtd_read_nm_wifi(char *name, loff_t from, size_t len, u_char *buf)\n{\n\tint ret;\n\tsize_t rdlen;\n\tstruct mtd_info *mtd;\n\n\tmtd = get_mtd_device_nm(name);\n\tif (IS_ERR(mtd))\n\t\treturn -1;\n\n\tret = mtd_read(mtd, from, len, &rdlen, buf);\n\n\tif (rdlen != len)\n\t\t\tprintk("warning: ra_mtd_read_nm: rdlen is not equal to len\\n");\n\n\tput_mtd_device(mtd);\n\n\treturn ret;\n}'}
BASELINE_FUNCTIONS_SHA256 = {'mt_mtd_write_nm_wifi': '95f7b668e6a6e59f4464723a03cb09f8ac4907dab35151f4446cfcb15bcecf27', 'mt_mtd_read_nm_wifi': 'cfcd0e8a72c2dc8cef71745afaffcf246c052250f95ef2f453b6cc0633266a13'}
