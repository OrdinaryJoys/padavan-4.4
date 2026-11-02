#!/usr/bin/env python3
"""Actual MT7621 controller bodies under inert host/target adapter seams.

No MMIO, kernel, device, host proc or hardware reset is accessed by this generator.
"""
import hashlib
import re
SOURCE_PATHS = {'controller':'trunk/linux-4.4.x/drivers/spi/spi-mt7621.c'}
FUNCTIONS = {'controller':('mt7621_spi_read','mt7621_spi_write','mt7621_spi_probe','mt7621_spi_remove')}
BASELINE_COMMIT = 'e8c4f633d6e7912e2310836e6844f782c87f3a39'
BASELINE_FUNCTIONS = {'mt7621_spi_read': 'static int mt7621_spi_read(struct mt7621_spi *ms, u8 *buf, size_t len)\n{\n\tsize_t rx_len;\n\tint i, ret;\n\tu32 val = 0;\n\n\twhile (len) {\n\t\trx_len = min_t(size_t, len, MT7621_RX_FIFO_LEN);\n\n\t\twritel((rx_len * 8) << MISO_BIT_CNT_S,\n\t\t       ms->base + SPI_MOREBUF_REG);\n\t\twritel(SPI_MASTER_START, ms->base + SPI_TRANS_REG);\n\n\t\tret = mt7621_spi_busy_wait(ms);\n\t\tif (ret)\n\t\t\treturn ret;\n\n\t\tfor (i = 0; i < rx_len; i++) {\n\t\t\tif ((i % 4) == 0)\n\t\t\t\tval = readl(ms->base + SPI_DIDO_REG(i / 4));\n\t\t\t*buf++ = val & 0xff;\n\t\t\tval >>= 8;\n\t\t}\n\n\t\tlen -= rx_len;\n\t}\n\n\treturn ret;\n}', 'mt7621_spi_write': 'static int mt7621_spi_write(struct mt7621_spi *ms, const u8 *buf, size_t len)\n{\n\tsize_t tx_len, opcode_len, dido_len;\n\tint i, ret;\n\tu32 val;\n\n\twhile (len) {\n\t\ttx_len = min_t(size_t, len, MT7621_TX_FIFO_LEN);\n\n\t\topcode_len = min_t(size_t, tx_len, 4);\n\t\tdido_len = tx_len - opcode_len;\n\n\t\tval = 0;\n\t\tfor (i = 0; i < opcode_len; i++) {\n\t\t\tval <<= 8;\n\t\t\tval |= *buf++;\n\t\t}\n\n\t\twritel(val, ms->base + SPI_OP_ADDR_REG);\n\n\t\tval = 0;\n\t\tfor (i = 0; i < dido_len; i++) {\n\t\t\tval |= (*buf++) << ((i % 4) * 8);\n\n\t\t\tif ((i % 4 == 3) || (i == dido_len - 1)) {\n\t\t\t\twritel(val, ms->base + SPI_DIDO_REG(i / 4));\n\t\t\t\tval = 0;\n\t\t\t}\n\t\t}\n\n\t\twritel(((opcode_len * 8) << CMD_BIT_CNT_S) |\n\t\t       ((dido_len * 8) << MOSI_BIT_CNT_S),\n\t\t       ms->base + SPI_MOREBUF_REG);\n\t\twritel(SPI_MASTER_START, ms->base + SPI_TRANS_REG);\n\n\t\tret = mt7621_spi_busy_wait(ms);\n\t\tif (ret)\n\t\t\treturn ret;\n\n\t\tlen -= tx_len;\n\t}\n\n\treturn 0;\n}', 'mt7621_spi_probe': 'static int mt7621_spi_probe(struct platform_device *pdev)\n{\n\tstruct spi_master *master;\n\tstruct mt7621_spi *ms;\n\tvoid __iomem *base;\n\tstruct resource *r;\n\tu32 hclk_freq;\n\tint status = 0;\n\tstruct clk *hclk;\n\n\tr = platform_get_resource(pdev, IORESOURCE_MEM, 0);\n\tbase = devm_ioremap_resource(&pdev->dev, r);\n\tif (IS_ERR(base))\n\t\treturn PTR_ERR(base);\n\n\thclk = devm_clk_get(&pdev->dev, NULL);\n\tif (IS_ERR(hclk)) {\n\t\tdev_info(&pdev->dev, "unable to get hclk, err = %d\\n", status);\n\t\treturn PTR_ERR(hclk);\n\t}\n\n\tstatus = clk_prepare_enable(hclk);\n\tif (status)\n\t\treturn status;\n\n\thclk_freq = clk_get_rate(hclk);\n\n\tmaster = spi_alloc_master(&pdev->dev, sizeof(*ms));\n\tif (master == NULL)\n\t\treturn -ENOMEM;\n\n\tmaster->mode_bits = SPI_CPOL | SPI_CPHA | SPI_LSB_FIRST | SPI_CS_HIGH;\n\tmaster->flags = SPI_MASTER_HALF_DUPLEX;\n\n\tmaster->setup = mt7621_spi_setup;\n\tmaster->transfer_one_message = mt7621_spi_transfer_one_message;\n\tmaster->bits_per_word_mask = SPI_BPW_MASK(8);\n\tmaster->dev.of_node = pdev->dev.of_node;\n\tmaster->num_chipselect = 2;\n\n\tmaster->min_speed_hz = hclk_freq / (RS_CLK_SEL_M + 2);\n\n\tdev_set_drvdata(&pdev->dev, master);\n\n\tms = spi_master_get_devdata(master);\n\tms->base = base;\n\tms->hclk = hclk;\n\tms->master = master;\n\tms->hclk_freq = hclk_freq;\n\n\tdevice_reset(&pdev->dev);\n\n\treturn spi_register_master(master);\n}', 'mt7621_spi_remove': 'static int mt7621_spi_remove(struct platform_device *pdev)\n{\n\tstruct spi_master *master;\n\tstruct mt7621_spi *ms;\n\n\tmaster = dev_get_drvdata(&pdev->dev);\n\tms = spi_master_get_devdata(master);\n\n\tclk_disable(ms->hclk);\n\tspi_unregister_master(master);\n\n\treturn 0;\n}'}
BASELINE_FUNCTIONS_SHA256 = {'mt7621_spi_read': 'aed29c826bd8cf9e0e7e43ac3fded20c89362ed3acc198d8164f9230c409b5bc', 'mt7621_spi_write': 'f6e0a38ff7cfac843a87f3c9701ab3fc450d7414300900e700f7f5bc4f8bcc68', 'mt7621_spi_probe': '0feb3856c859a08e88cd8c2e5ab1c39d7e444046c10da284dcd4724e73bb47de', 'mt7621_spi_remove': '4e644f0dfda26caf30c9603e490b420c6d3d586dc2574a585d457e7f09cbd80e'}

def extract(text,name):
    tokens=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    masked=re.sub(tokens,lambda m:' '*len(m.group()),text)
    pattern=r'(?:static\s+)?(?:inline\s+)?(?:void|int|ssize_t)\s+\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{'
    matches=list(re.finditer(pattern,masked))
    if len(matches)!=1:raise ValueError('Missing/ambiguous controller function: '+name)
    start=matches[0].start();opening=text.index('{',start);depth=0
    for token in re.finditer(tokens+r'|[{}]',text[opening:]):
        if token.group()=='{':depth+=1
        elif token.group()=='}':
            depth-=1
            if not depth:return text[start:opening+token.end()]
    raise ValueError('Unterminated controller function: '+name)

def actual_functions(texts):
    return {name:{'source_key':key,'body':extract(texts[key],name)} for key,names in FUNCTIONS.items() for name in names}

def production_fragments(texts):
    text=texts['controller'];start=text.index('#define DRIVER_NAME');end=text.index('};',text.index('struct mt7621_spi {',start))+2
    return text[start:end]

PREFIX = r'''
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include <errno.h>
typedef uint32_t u32;typedef uint8_t u8;
#define __iomem
#define BIT(n) (1U<<(n))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define CONFIG_RESET_CONTROLLER 1
#define IS_ENABLED(x) (reset_enabled)
#define IORESOURCE_MEM 0
#define SPI_CPOL 1
#define SPI_CPHA 2
#define SPI_LSB_FIRST 4
#define SPI_CS_HIGH 8
#define SPI_MASTER_HALF_DUPLEX 1
#define SPI_BPW_MASK(n) 1
#define dev_info(...) ((void)0)
#define IS_ERR(p) ((intptr_t)(p)<0 && (intptr_t)(p)>-4096)
#define PTR_ERR(p) ((int)(intptr_t)(p))
struct clk {int unused;};struct device_node {int unused;};struct property {int unused;};
struct device {struct device_node *of_node;void *data;};struct platform_device {struct device dev;};
struct resource {int unused;};struct spi_device {int unused;};struct spi_message {int unused;};
struct spi_master {struct device dev;unsigned mode_bits,flags,bits_per_word_mask,num_chipselect,min_speed_hz;int(*setup)(struct spi_device*);int(*transfer_one_message)(struct spi_master*,struct spi_message*);void *data;};
'''

SEAMS = r'''
static struct clk clkobj;static struct resource resource;static struct device_node node;static struct property prop;
static int enabled,prepared,refs,alloc_fail,reg_error,reset_error,map_error,clk_error,enable_error;
static int registrations,unregisters,clock_at_unregister,reset_calls,reset_enabled=1,reset_declared=1;
static unsigned rate=220000000U;
static char events[128],regs[128];static size_t event_len;
static unsigned mmio_writes,busy_calls,busy_fail,dido0,opcode;
static struct spi_master *allocated;
static void event(char c){if(event_len+1>=sizeof(events))abort();events[event_len++]=c;events[event_len]=0;}
static struct resource *platform_get_resource(struct platform_device*p,int a,int b){(void)p;(void)a;(void)b;return &resource;}
static void *devm_ioremap_resource(struct device*d,struct resource*r){(void)d;(void)r;event('M');return map_error?(void*)(intptr_t)map_error:regs;}
static struct clk *devm_clk_get(struct device*d,void*n){(void)d;(void)n;event('G');return clk_error?(struct clk*)(intptr_t)clk_error:&clkobj;}
static int clk_prepare_enable(struct clk*c){(void)c;event('E');if(enable_error)return enable_error;prepared++;enabled++;return 0;}
static u32 clk_get_rate(struct clk*c){(void)c;event('R');return rate;}
static void clk_disable(struct clk*c){if(c!=&clkobj)abort();event('L');enabled--;}
static void clk_disable_unprepare(struct clk*c){clk_disable(c);event('U');prepared--;}
static struct spi_master *spi_alloc_master(struct device*d,unsigned sz){struct spi_master*m;(void)d;event('A');if(alloc_fail)return NULL;m=calloc(1,sizeof(*m)+sz);if(!m)abort();m->data=m+1;refs++;allocated=m;return m;}
static void *spi_master_get_devdata(struct spi_master*m){return m->data;}
static void spi_master_put(struct spi_master*m){event('P');refs--;if(refs==0){free(m);allocated=NULL;}}
static void dev_set_drvdata(struct device*d,void*p){event(p?'D':'C');d->data=p;}
static void *dev_get_drvdata(struct device*d){return d->data;}
static int mt7621_spi_setup(struct spi_device*s){(void)s;return 0;}
static int mt7621_spi_transfer_one_message(struct spi_master*m,struct spi_message*s){(void)m;(void)s;return 0;}
static int device_reset(struct device*d){(void)d;event('X');reset_calls++;return reset_error;}
static const struct property *of_find_property(const struct device_node*n,const char*k,int*v){(void)v;if(strcmp(k,"resets"))abort();event('F');return n&&reset_declared?&prop:NULL;}
static int spi_register_master(struct spi_master*m){(void)m;event('T');registrations++;return reg_error;}
static void spi_unregister_master(struct spi_master*m){event('N');unregisters++;clock_at_unregister=enabled;spi_master_put(m);}
static void writel(u32 value,void *address){ptrdiff_t off=(char*)address-regs;mmio_writes++;if(off==SPI_DIDO_REG(0))dido0=value;if(off==SPI_OP_ADDR_REG)opcode=value;}
static u32 readl(void *address){(void)address;return 0x44332211U;}
static int mt7621_spi_busy_wait(struct mt7621_spi*m){(void)m;busy_calls++;return busy_fail==busy_calls?-110:0;}
'''

DRIVER = r'''
int main(int argc,char**argv){
 struct platform_device p;struct mt7621_spi ms;u8 bytes[64];size_t n=0,i;int result=0,is_read=0,is_write=0;unsigned sum=0;const char*name;
 if(argc!=2){return 64;}name=argv[1];memset(&p,0,sizeof(p));p.dev.of_node=&node;memset(&ms,0,sizeof(ms));ms.base=regs;memset(bytes,0,sizeof(bytes));
 if(!strcmp(name,"probe-normal")){}
 else if(!strcmp(name,"probe-map-error"))map_error=-5;
 else if(!strcmp(name,"probe-clock-get-error"))clk_error=-517;
 else if(!strcmp(name,"probe-clock-enable-error"))enable_error=-11;
 else if(!strcmp(name,"probe-clock-zero"))rate=0;
 else if(!strcmp(name,"probe-clock-one"))rate=1;
 else if(!strcmp(name,"probe-clock-two"))rate=2;
 else if(!strcmp(name,"probe-alloc-error"))alloc_fail=1;
 else if(!strcmp(name,"probe-reset-defer"))reset_error=-517;
 else if(!strcmp(name,"probe-reset-error"))reset_error=-5;
 else if(!strcmp(name,"probe-reset-absent-error")){reset_error=-2;reset_declared=0;}
 else if(!strcmp(name,"probe-reset-disabled-error")){reset_error=-95;reset_enabled=0;}
 else if(!strcmp(name,"probe-register-error"))reg_error=-16;
 else if(!strcmp(name,"remove-normal")||!strcmp(name,"remove-retained-ref")){}
 else if(!strcmp(name,"read-zero")){is_read=1;n=0;}
 else if(!strcmp(name,"read-one")){is_read=1;n=1;}
 else if(!strcmp(name,"read-31")){is_read=1;n=31;}
 else if(!strcmp(name,"read-32")){is_read=1;n=32;}
 else if(!strcmp(name,"read-33")){is_read=1;n=33;}
 else if(!strcmp(name,"read-64")){is_read=1;n=64;}
 else if(!strcmp(name,"read-error-first")){is_read=1;n=33;busy_fail=1;}
 else if(!strcmp(name,"read-error-second")){is_read=1;n=33;busy_fail=2;}
 else if(!strcmp(name,"write-zero")){is_write=1;n=0;}
 else if(!strcmp(name,"write-one")){is_write=1;n=1;}
 else if(!strcmp(name,"write-four")){is_write=1;n=4;}
 else if(!strcmp(name,"write-five")){is_write=1;n=5;}
 else if(!strcmp(name,"write-seven")){is_write=1;n=7;}
 else if(!strcmp(name,"write-eight-high")){is_write=1;n=8;}
 else if(!strcmp(name,"write-36")){is_write=1;n=36;}
 else if(!strcmp(name,"write-37")){is_write=1;n=37;}
 else if(!strcmp(name,"write-error-first")){is_write=1;n=37;busy_fail=1;}
 else if(!strcmp(name,"write-error-second")){is_write=1;n=37;busy_fail=2;}
 else if(!strcmp(name,"write-ff-word")){is_write=1;n=8;}
 else return 64;
 if(is_read){result=mt7621_spi_read(&ms,bytes,n);for(i=0;i<n;i++)sum+=bytes[i];}
 else if(is_write){for(i=0;i<n;i++)bytes[i]=(u8)(i+1);if(!strcmp(name,"write-eight-high"))bytes[7]=128;if(!strcmp(name,"write-ff-word"))memset(bytes+4,255,4);result=mt7621_spi_write(&ms,bytes,n);}
 else {result=mt7621_spi_probe(&p);if(result==0&&(!strcmp(name,"remove-normal")||!strcmp(name,"remove-retained-ref"))){if(!strcmp(name,"remove-retained-ref"))refs++;result=mt7621_spi_remove(&p);}}
 printf("{\"case\":\"%s\",\"result\":%d,\"enabled\":%d,\"prepared\":%d,\"master_refs\":%d,\"drvdata_set\":%d,\"registrations\":%d,\"unregisters\":%d,\"clock_at_unregister\":%d,\"reset_calls\":%d,\"busy_calls\":%u,\"mmio_writes\":%u,\"rx_sum\":%u,\"dido0\":%u,\"opcode\":%u,\"sequence\":\"%s\"}\n",name,result,enabled,prepared,refs,p.dev.data!=NULL,registrations,unregisters,clock_at_unregister,reset_calls,busy_calls,mmio_writes,sum,dido0,opcode,events);
 if(allocated){free(allocated);allocated=NULL;}return 0;
}
'''

def expected(name, *, result=0, enabled=0, prepared=0, refs=0, drvdata=0, registrations=0, unregisters=0, clock_at_unregister=0, resets=0, busy=0, mmio=0, rx_sum=0, dido0=0, opcode=0, sequence=''):
    return {'case':name,'result':result,'enabled':enabled,'prepared':prepared,'master_refs':refs,'drvdata_set':drvdata,'registrations':registrations,'unregisters':unregisters,'clock_at_unregister':clock_at_unregister,'reset_calls':resets,'busy_calls':busy,'mmio_writes':mmio,'rx_sum':rx_sum,'dido0':dido0,'opcode':opcode,'sequence':sequence}

def live(name,sequence='MGERADXT',**kw):
    return expected(name,enabled=1,prepared=1,refs=1,drvdata=1,registrations=1,resets=1,sequence=sequence,**kw)

CASES=(
 ('probe-normal',live('probe-normal')),
 ('probe-map-error',expected('probe-map-error',result=-5,sequence='M')),
 ('probe-clock-get-error',expected('probe-clock-get-error',result=-517,sequence='MG')),
 ('probe-clock-enable-error',expected('probe-clock-enable-error',result=-11,sequence='MGE')),
 ('probe-clock-zero',expected('probe-clock-zero',result=-22,sequence='MGERLU')),
 ('probe-clock-one',expected('probe-clock-one',result=-22,sequence='MGERLU')),
 ('probe-clock-two',live('probe-clock-two')),
 ('probe-alloc-error',expected('probe-alloc-error',result=-12,sequence='MGERALU')),
 ('probe-reset-defer',expected('probe-reset-defer',result=-517,resets=1,sequence='MGERADXFCPLU')),
 ('probe-reset-error',expected('probe-reset-error',result=-5,resets=1,sequence='MGERADXFCPLU')),
 ('probe-reset-absent-error',live('probe-reset-absent-error',sequence='MGERADXFT')),
 ('probe-reset-disabled-error',live('probe-reset-disabled-error')),
 ('probe-register-error',expected('probe-register-error',result=-16,registrations=1,resets=1,sequence='MGERADXTCPLU')),
 ('remove-normal',expected('remove-normal',registrations=1,unregisters=1,clock_at_unregister=1,resets=1,sequence='MGERADXTNPCLU')),
 ('remove-retained-ref',expected('remove-retained-ref',refs=1,registrations=1,unregisters=1,clock_at_unregister=1,resets=1,sequence='MGERADXTNPCLU')),
 ('read-zero',expected('read-zero')),
 ('read-one',expected('read-one',busy=1,mmio=2,rx_sum=17)),
 ('read-31',expected('read-31',busy=1,mmio=2,rx_sum=1292)),
 ('read-32',expected('read-32',busy=1,mmio=2,rx_sum=1360)),
 ('read-33',expected('read-33',busy=2,mmio=4,rx_sum=1377)),
 ('read-64',expected('read-64',busy=2,mmio=4,rx_sum=2720)),
 ('read-error-first',expected('read-error-first',result=-110,busy=1,mmio=2)),
 ('read-error-second',expected('read-error-second',result=-110,busy=2,mmio=4,rx_sum=1360)),
 ('write-zero',expected('write-zero')),
 ('write-one',expected('write-one',busy=1,mmio=3,opcode=1)),
 ('write-four',expected('write-four',busy=1,mmio=3,opcode=0x01020304)),
 ('write-five',expected('write-five',busy=1,mmio=4,dido0=5,opcode=0x01020304)),
 ('write-seven',expected('write-seven',busy=1,mmio=4,dido0=0x00070605,opcode=0x01020304)),
 ('write-eight-high',expected('write-eight-high',busy=1,mmio=4,dido0=0x80070605,opcode=0x01020304)),
 ('write-36',expected('write-36',busy=1,mmio=11,dido0=0x08070605,opcode=0x01020304)),
 ('write-37',expected('write-37',busy=2,mmio=14,dido0=0x08070605,opcode=37)),
 ('write-error-first',expected('write-error-first',result=-110,busy=1,mmio=11,dido0=0x08070605,opcode=0x01020304)),
 ('write-error-second',expected('write-error-second',result=-110,busy=2,mmio=14,dido0=0x08070605,opcode=37)),
 ('write-ff-word',expected('write-ff-word',busy=1,mmio=4,dido0=0xffffffff,opcode=0x01020304)),
)
BASELINE_CASES=(
 ('probe-normal',live('probe-normal')),
 ('probe-alloc-error',expected('probe-alloc-error',result=-12,enabled=1,prepared=1,sequence='MGERA')),
 ('probe-register-error',expected('probe-register-error',result=-16,enabled=1,prepared=1,refs=1,drvdata=1,registrations=1,resets=1,sequence='MGERADXT')),
 ('probe-reset-defer',live('probe-reset-defer')),
 ('probe-reset-error',live('probe-reset-error')),
 ('probe-clock-zero',live('probe-clock-zero')),
 ('probe-clock-one',live('probe-clock-one')),
 ('remove-normal',expected('remove-normal',prepared=1,drvdata=1,registrations=1,unregisters=1,resets=1,sequence='MGERADXTLNP')),
)
LIMITS=(
 'The actual read/write/probe/remove bodies are embedded; clock/reset/allocation/registration/MMIO/DT callbacks are explicitly inert seams.',
 'The transfer_one_message and setup callbacks stored by probe are inert placeholders; this adapter does not execute SPI queue, real register polls or a kernel.',
 'Clock rates0/1 are model-invalid inputs, not observations from a device; normal divider/MMIO/clock/reset values are unchanged.',
 'Declared OF reset errors propagate only with reset controller support; absent properties and disabled support retain prior optional behavior.',
 'Error numbers are normalized model values, not proof of real MIPS kernel errno ABI; signed-shift UB is separately tested with host UBSan.',
 'Baseline zero-read undefined return and high-bit signed-shift UB are tested as compiler/sanitizer negative controls outside fixed execution rows.',
 'Controller removal cleanup does not prove warm reset, SPI end-to-end deadline, runtime pressure or old efd2 first-hop safety.',
)

def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False):
    if set(texts)!=set(SOURCE_PATHS):raise ValueError('Exact controller source manifest required')
    if type(owner_uid)is not int or type(baseline)is not bool:raise ValueError('Typed generation arguments required')
    functions=actual_functions(texts);bodies={n:r['body'] for n,r in functions.items()}
    if baseline:
        if set(BASELINE_FUNCTIONS)!=set(BASELINE_FUNCTIONS_SHA256):raise ValueError('Unpinned baseline manifest')
        for n,b in BASELINE_FUNCTIONS.items():
            if hashlib.sha256(b.encode()).hexdigest()!=BASELINE_FUNCTIONS_SHA256[n]:raise ValueError('Changed literal baseline: '+n)
        bodies=dict(BASELINE_FUNCTIONS)
    return PREFIX+'\n'+production_fragments(texts)+'\n'+SEAMS+'\n'+'\n\n'.join(bodies[n] for n in FUNCTIONS['controller'])+'\n'+DRIVER
