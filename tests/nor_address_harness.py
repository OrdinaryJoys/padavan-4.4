"""Whole NOR mode/scan/restore and m25p lifecycle bodies, inert register bus.

Register effects and ready time are explicit models. pthread mutexes exercise
queued admission; they do not emulate Linux mutexes, SPI hardware or SMP reset.
"""
from pathlib import Path
import re
import sr3_startup_harness as base

SOURCE_PATHS = dict(base.SOURCE_PATHS, cfi_header="trunk/linux-4.4.x/include/linux/mtd/cfi.h", reboot="trunk/linux-4.4.x/kernel/reboot.c", reboot_header="trunk/linux-4.4.x/include/linux/reboot.h")
FUNCTION_SOURCES = {
    **{n: "reboot" for n in ("reboot_dma_failure_report","reboot_dma_failures","reboot_dma_failure_check")},
    **{n: 'nor' for n in ('read_sr','read_fsr','read_cr','write_enable','write_disable',
        'spi_nor_read_dummy_cycles','spi_nor_sr_ready','spi_nor_fsr_ready','spi_nor_ready',
        'spi_nor_wait_till_ready_with_timeout','spi_nor_wait_till_ready',
        'spi_nor_finish_mode_write','set_4byte','spi_nor_lock_and_prep',
        'spi_nor_unlock_and_unprep','spi_nor_restore','spi_set_wb_drive_strength','spi_nor_scan')},
    **{n: 'm25p' for n in ('m25p80_read_reg','m25p80_write_reg','m25p_probe','m25p_remove','m25p_shutdown')},
}
OLD_FUNCTIONS = ('set_4byte','spi_nor_lock_and_prep','spi_nor_restore','spi_nor_scan',
                 'm25p_remove','m25p_shutdown')

MODEL = r'''
#undef ESHUTDOWN
#define ESHUTDOWN 108
#include <setjmp.h>
typedef struct {unsigned int value;} atomic_t;
#define ATOMIC_INIT(v) {v}
static atomic_t reboot_dma_failure_reasons = ATOMIC_INIT(0);
static void atomic_or(unsigned int v,atomic_t*p){__atomic_fetch_or(&p->value,v,__ATOMIC_SEQ_CST);}
static unsigned int atomic_read(atomic_t*p){return __atomic_load_n(&p->value,__ATOMIC_SEQ_CST);}
#define MAX_SCHEDULE_TIMEOUT 100
#define pr_emerg(...) ((void)0)
static jmp_buf gate_escape;
static int gate_blocked;
static void local_irq_disable(void){}
static void cpu_relax(void){gate_blocked=1;longjmp(gate_escape,1);}
static void schedule_timeout_uninterruptible(long n){(void)n;abort();}
static void *allocated_flash;
static struct flash_info model_info;
static int warnings,errors,registered,registration_busy,busy,opcode_mode;
static int failop=-1,failnth=1,accepted,busy_kind,prepare_error,unregister_error,suspended;
static int mode,ear,wel,reset_enabled,reset_calls,delay_calls,prepare_calls,unprepare_calls;
static int ops[256],trace_ops[128],trace_count,write_busy,read_calls,retired_reads;
static unsigned long jiffies;
static int thread_mode,entered,release_bus,thread_restore,thread_read;
static pthread_mutex_t barrier=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition=PTHREAD_COND_INITIALIZER;
static void trace(char c){(void)c;}
#define dev_warn(device,...) ((void)(device),(void)++warnings)
#define dev_err(device,...) ((void)(device),(void)++errors)
#define dev_info(device,...) ((void)(device))
#define dev_dbg(device,...) ((void)(device))
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)++errors)
#define pr_debug(...) ((void)0)
static void mutex_init(pthread_mutex_t *p){assert(!pthread_mutex_init(p,NULL));}
static void mutex_lock(pthread_mutex_t *p){assert(!pthread_mutex_lock(p));}
static void mutex_unlock(pthread_mutex_t *p){assert(!pthread_mutex_unlock(p));}
#ifdef CONFIG_K2P_RESET_GUARD
static int fake_lock_failures;
static int mutex_trylock(pthread_mutex_t *p){
 if(fake_lock_failures>0){fake_lock_failures--;return 0;}
 return pthread_mutex_trylock(p)==0;
}
static void msleep(unsigned int ms){assert(ms==20);jiffies+=2;}
#endif
static void cond_resched(void){jiffies+=10UL*HZ;}
static void udelay(unsigned int n){assert(n==100);delay_calls++;}
static int fail(int op){ops[op]++;return op==failop && ops[op]==failnth;}
static int spi_write_then_read(struct spi_device *s,const void *tx,unsigned int tn,void *rx,unsigned int rn){
 int op=*(const u8*)tx;(void)s;assert(tn==1&&rn==1);read_calls++;
 if(fail(op))return -EIO;
 if(op==0x05){
  if(busy_kind==4&&trace_count)return -EIO;
  *(u8*)rx=busy?1:0;
  if(busy && busy_kind!=1 && busy_kind!=2)busy--;
 }else if(op==0x35)*(u8*)rx=suspended?0x80:0;
 else if(op==0x70)*(u8*)rx=busy?0:0x80;
 else if(op==0x15)*(u8*)rx=mode==4?1:0;
 else if(op==0xc8)*(u8*)rx=(u8)ear; /* optional SR3 already configured */
 else abort();
 return 0;
}
static int spi_write(struct spi_device *s,const void *tx,unsigned int n){
 const u8 *p=tx;int op=p[0],error;(void)s;
 assert(trace_count<128);trace_ops[trace_count++]=op;write_busy+=!!busy;
 error=fail(op);if(error&&!accepted)return -EIO;
 if(op==0x06){assert(n==1);wel=1;}
 else if(op==0x04){assert(n==1);wel=0;}
 else if(op==0xb7||op==0xe9){
  assert(n==1);mode=op==0xb7?4:3;if(op==0xe9&&model_info.id[0]==0xef)ear=1;
  if(thread_mode&&op==0xe9){
   assert(!pthread_mutex_lock(&barrier));entered=1;assert(!pthread_cond_broadcast(&condition));
   while(!release_bus)assert(!pthread_cond_wait(&condition,&barrier));
   assert(!pthread_mutex_unlock(&barrier));
  }
  if(busy_kind==2||busy_kind==3)busy=2;
 }else if(op==0xc5){assert(n==2&&p[1]==0);ear=0;if(busy_kind==2||busy_kind==3)busy=2;}
 else if(op==0x17){assert(n==2);mode=p[1]&0x80?4:3;if(busy_kind==2||busy_kind==3)busy=2;}
 else if(op==0x66){assert(n==1);reset_enabled=1;}
 else if(op==0x99){assert(n==1&&reset_enabled);reset_calls++;mode=busy_kind==5?4:3;ear=busy_kind==6?1:0;busy=1;}
 else abort();
 return error?-EIO:0;
}
static int prepare(struct spi_nor *n,enum spi_nor_ops op){(void)n;assert(op==SPI_NOR_OPS_WRITE||op==SPI_NOR_OPS_READ);prepare_calls++;return prepare_error;}
static void unprepare(struct spi_nor *n,enum spi_nor_ops op){(void)n;assert(op==SPI_NOR_OPS_WRITE||op==SPI_NOR_OPS_READ);unprepare_calls++;}
static void *spi_get_drvdata(struct spi_device *s){return s->data;}
static int mtd_device_unregister(struct mtd_info *m){(void)m;if(unregister_error)return unregister_error;registered=0;return 0;}
'''

DRIVER = r'''
static void *restore_thread(void *n){thread_restore=spi_nor_restore(n);return NULL;}
static void *read_thread(void *n){
 thread_read=spi_nor_lock_and_prep(n,SPI_NOR_OPS_READ);
 if(!thread_read)spi_nor_unlock_and_unprep(n,SPI_NOR_OPS_READ);
 return NULL;
}
static void check_gate(void){if(!setjmp(gate_escape))reboot_dma_failure_check(false);}
int main(int argc,char **argv){
 struct spi_device spi={0};struct device_node node;struct m25p flash={0};struct spi_nor *n=&flash.spi_nor;
 int result=0,next=777,again=777,count_before=0;const char *action;pthread_t first,second;
 assert(argc==12);action=argv[1];model_info.id[0]=(u8)atoi(argv[2]);failop=atoi(argv[3]);failnth=atoi(argv[4]);
 accepted=atoi(argv[5]);busy_kind=atoi(argv[6]);prepare_error=atoi(argv[7]);unregister_error=atoi(argv[8]);
 suspended=atoi(argv[9]);model_info.n_sectors=atoi(argv[10])==32?512:256;model_info.flags=atoi(argv[11]);
 model_info.name="inert-nor";model_info.sector_size=65536;model_info.page_size=256;
 spi.dev.of_node=&node;spi.modalias="inert-part";spi.data=&flash;flash.spi=&spi;
 n->dev=&spi.dev;n->priv=&flash;n->info=&model_info;n->read_reg=m25p80_read_reg;n->write_reg=m25p80_write_reg;
 n->addr_width=model_info.n_sectors==512?4:3;n->prepare=prepare;n->unprepare=unprepare;
 if(busy_kind==1)busy=2;
 mode=!strcmp(action,"scan")||!strcmp(action,"enter")?3:(int)n->addr_width;ear=mode==4?1:0;
 if(!strcmp(action,"scan")){
  result=m25p_probe(&spi);n=allocated_flash?&((struct m25p*)allocated_flash)->spi_nor:n;
 }else{
  mutex_init(&n->lock);
  if(!strcmp(action,"enter"))result=set_4byte(n,&model_info,1);
  else if(!strcmp(action,"exit"))result=set_4byte(n,&model_info,0);
  else if(!strcmp(action,"remove")){registered=1;result=m25p_remove(&spi);}
  else if(!strcmp(action,"shutdown"))m25p_shutdown(&spi);
  else if(!strcmp(action,"queued")){
   thread_mode=1;assert(!pthread_create(&first,NULL,restore_thread,n));
   assert(!pthread_mutex_lock(&barrier));while(!entered)assert(!pthread_cond_wait(&condition,&barrier));
   assert(pthread_mutex_trylock(&n->lock)==EBUSY);assert(!pthread_create(&second,NULL,read_thread,n));
   release_bus=1;assert(!pthread_cond_broadcast(&condition));assert(!pthread_mutex_unlock(&barrier));
   assert(!pthread_join(first,NULL));assert(!pthread_join(second,NULL));result=thread_restore;next=thread_read;
  }else if(!strcmp(action,"restore"))result=spi_nor_restore(n);
  else abort();
  if(!strcmp(action,"restore")||!strcmp(action,"shutdown")||!strcmp(action,"queued")){
   count_before=trace_count;again=spi_nor_restore(n);assert(trace_count==count_before);
   count_before=read_calls;
   if(strcmp(action,"queued"))next=spi_nor_lock_and_prep(n,SPI_NOR_OPS_READ);
   if(!next && strcmp(action,"queued"))spi_nor_unlock_and_unprep(n,SPI_NOR_OPS_READ);
   retired_reads=read_calls-count_before;
  }
 }
 check_gate();
 printf("{\"gate_blocked\":%d,\"ret\":%d,\"next\":%d,\"again\":%d,\"registered\":%d,\"mode\":%d,\"ear\":%d,\"wel\":%d,"
        "\"busy\":%d,\"write_busy\":%d,\"prepare\":%d,\"unprepare\":%d,\"restore_started\":%d,"
        "\"restore_error\":%d,\"failures\":%u,\"reset\":%d,\"delay\":%d,\"opcode_mode\":%d,\"retired_reads\":%d,\"commands\":[",
        gate_blocked,result,next,again,registered,mode,ear,wel,busy,write_busy,prepare_calls,unprepare_calls,n->restore_started,
        n->restore_error,reboot_dma_failures(),reset_calls,delay_calls,opcode_mode,retired_reads);
 for(int i=0;i<trace_count;i++){printf("%s%d",i?",":"",trace_ops[i]);}
 puts("]}");
 free(allocated_flash);return 0;
}
'''

def current_texts():
    root = Path(__file__).resolve().parents[1]
    return {k:(root/v).read_text() for k,v in SOURCE_PATHS.items()}

def generate(texts, old=None):
    prefix = base.PREFIX.split('static const char*label;')[0]
    prefix = '#include <assert.h>\n#include <pthread.h>\n' + prefix
    prefix = prefix.replace('int lock,restore_started,restore_error;',
        'pthread_mutex_t lock;int restore_started,restore_error;')
    prefix = prefix.replace(' int (*read_reg)',
        ' int (*prepare)(struct spi_nor*,enum spi_nor_ops);void (*unprepare)(struct spi_nor*,enum spi_nor_ops);\n int (*read_reg)')
    enum = re.search(r'enum spi_nor_ops\s*\{[^}]+\};', texts['nor_header']).group()
    prefix = prefix.replace('struct spi_nor {',enum+'\nstruct spi_nor {')
    fragments = base.production_fragments(texts)
    fragments += '\n' + re.search(r'enum reboot_dma_failure\s*\{[^}]+\};', texts['reboot_header']).group()
    fragments += "\n#define CFI_MFR_MACRONIX " + base._define(texts["cfi_header"], "CFI_MFR_MACRONIX")
    fragments += '\n'+'\n'.join('#define '+n+' '+base._define(texts['nor_header'],n)
        for n in ('SNOR_MFR_MACRONIX','SPINOR_OP_RDCR','SPINOR_OP_WRDI','SPINOR_OP_EN4B','SPINOR_OP_EX4B','SPINOR_OP_WREAR','SPINOR_OP_BRWR'))
    stubs = base.PREFIX.split('static struct flash_platform_data*dev_get_platdata')[1].split('static int set_4byte')[0]
    stubs = 'static struct flash_platform_data*dev_get_platdata'+stubs
    stubs += '\nstatic void spi_nor_set_4byte_opcodes(struct spi_nor*n,const struct flash_info*i){(void)n;(void)i;opcode_mode++;}\n'
    stubs += 'static int mtd_device_parse_register'+base.PREFIX.split('static int mtd_device_parse_register')[1]
    definitions = base.POST_DEFINITIONS.replace('static struct flash_info model_info;','')
    bodies = {n:base.extract(texts[k],n) for n,k in FUNCTION_SOURCES.items()}
    if old:
        bodies.update({n:r['body'] for n,r in old['functions'].items()})
        bodies['spi_nor_restore']='#define spi_nor_restore legacy_spi_nor_restore\n'+bodies['spi_nor_restore']+'\n#undef spi_nor_restore\nstatic int spi_nor_restore(struct spi_nor*n){legacy_spi_nor_restore(n);return 0;}'
    order=('reboot_dma_failure_report','reboot_dma_failures','reboot_dma_failure_check','m25p80_read_reg','m25p80_write_reg','read_sr','read_fsr','read_cr','write_enable','write_disable',
           'spi_nor_read_dummy_cycles','spi_nor_sr_ready','spi_nor_fsr_ready','spi_nor_ready',
           'spi_nor_wait_till_ready_with_timeout','spi_nor_wait_till_ready','spi_nor_finish_mode_write','set_4byte',
           'spi_nor_lock_and_prep','spi_nor_unlock_and_unprep','spi_nor_restore','spi_set_wb_drive_strength',
           'spi_nor_scan','m25p_probe','m25p_remove','m25p_shutdown')
    driver=DRIVER
    if old:
        driver=driver.replace('assert(trace_count==count_before);','(void)count_before;')
    return prefix+'\n'+fragments+'\n'+MODEL+'\n'+stubs+'\n'+definitions+'\n'+'\n\n'.join(bodies[n]for n in order)+'\n'+driver
