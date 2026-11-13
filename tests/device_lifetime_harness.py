"""Execute complete production lifetime/driver-core functions with inert kernel services."""
from pathlib import Path
import re
from mt7621_wdt_harness import function
KERNEL = Path(__file__).resolve().parents[1] / 'trunk/linux-4.4.x'
def read(path): return (KERNEL / path).read_text()
def body(path, name): return function(read(path).replace(" DEVINIT ", " "), name)
def noincludes(s): return re.sub(r'^#include .*\n', '', s, flags=re.M)
CORE = noincludes(read('drivers/base/device_lifetime.c'))
HEADER = noincludes(read('include/linux/device_lifetime.h'))
SHIM = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#define CONFIG_K2P_RESET_GUARD 1
#define EXPORT_SYMBOL(x)
#define EXPORT_SYMBOL_GPL(x)
#define DEFINE_RAW_SPINLOCK(x) pthread_mutex_t x = PTHREAD_MUTEX_INITIALIZER
#define raw_spin_lock_irqsave(l, f) do { (f)=0; assert(!pthread_mutex_lock(l)); } while(0)
#define raw_spin_unlock_irqrestore(l, f) do { (void)(f); assert(!pthread_mutex_unlock(l)); } while(0)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
struct module { int refs; bool going; };
struct device; struct device_driver;
struct list_head { struct list_head *prev, *next; int nonempty; };
struct klist_node { struct list_head n_node; };
struct klist { int k_lock; struct list_head k_list; };
struct kobject { void *parent; };
struct device_private { struct device *device; struct klist_node knode_driver, knode_parent, knode_bus; };
struct driver_private { struct klist klist_devices; struct klist_node knode_bus; struct kobject kobj; };
struct kset { struct kobject kobj; };
struct bus_private { int bus_notifier, mutex; struct list_head interfaces; struct kobject devices; struct kset *devices_kset; };
struct bus_type { struct bus_private *p; int (*probe)(struct device *); int (*remove)(struct device *); void *drv_groups, *dev_groups; };
struct device_driver { bool no_forced_unbind, lifetime_pinned, lifetime_unregistering, suppress_bind_attrs; struct module *owner; struct driver_private *p; struct bus_type *bus; void *groups; const char *name; int (*probe)(struct device *); int (*remove)(struct device *); };
struct pm_domain { int (*activate)(struct device *); void (*sync)(struct device *); void (*dismiss)(struct device *); };
struct class_private { int mutex; struct list_head interfaces; };
struct class { struct class_private *p; };
struct device { struct device *parent; unsigned int lifetime_flags; struct device_driver *lifetime_driver, *driver; struct bus_type *bus; struct device_private *p; struct pm_domain *pm_domain; int refs, data; struct kobject kobj; struct class *class; unsigned long devt; struct klist_node knode_class; int devres_lock; struct list_head devres_head; };
struct subsys_interface { struct list_head node; void (*remove_dev)(struct device *, struct subsys_interface *); };
struct class_interface { struct list_head node; void (*remove_dev)(struct device *, struct class_interface *); };
static int effects, callbacks, resources, freed, notifications, dismissed, sysfs, probe_mode, hardware;
static bool try_module_get(struct module *m) { if(!m) return true; if(m->going) return false; m->refs++; return true; }
static void module_put(struct module *m) { if(m) m->refs--; }
static struct device *get_device(struct device *d) { if(d) d->refs++; return d; }
static void put_device(struct device *d) { if(d) { d->refs--; effects++; } }
#define pr_debug(...) ((void)0)
#define pr_err(...) ((void)0)
#define printk(...) ((void)0)
static int warn_on(bool x) { return x; }
#define WARN_ON(x) warn_on(!!(x))
#define WARN(...) ((void)0)
#define WARN_ON_ONCE(x) (!!(x))
#define dev_dbg(...) ((void)0)
#define KERN_ERR ""
#define KERN_WARNING ""
#define EPROBE_DEFER 517
#define BUS_NOTIFY_UNBIND_DRIVER 1
#define BUS_NOTIFY_UNBOUND_DRIVER 2
#define BUS_NOTIFY_DEL_DEVICE 3
#define BUS_NOTIFY_REMOVED_DEVICE 4
#define KOBJ_REMOVE 5
#define MAJOR(x) (x)
#define list_for_each_entry(a,b,c) for ((a)=NULL; (a)!=NULL; (a)=NULL)
#define list_for_each_entry_safe(a,b,c,d) for((a)=NULL,(b)=NULL;(a)!=NULL;(a)=NULL)
#define list_for_each_entry_safe_reverse(a,b,c,d) list_for_each_entry_safe(a,b,c,d)
#define list_entry(ptr,type,member) ((type *)(ptr))
static int list_empty(struct list_head *p) { return !p->nonempty; }
static void list_del(struct list_head *p) { (void)p; effects++; }
static void klist_remove(struct klist_node *p) { (void)p; effects++; }
static void klist_del(struct klist_node *p) { (void)p; effects++; }
static bool klist_node_attached(struct klist_node *p) { (void)p; return true; }
static void spin_lock(int *p) { (void)p; }
static void spin_unlock(int *p) { (void)p; }
#define spin_lock_irqsave(l,f) do { (void)(l); (f)=0; } while(0)
#define spin_unlock_irqrestore(l,f) do { (void)(l); (void)(f); } while(0)
static void mutex_lock(int *p) { (void)p; }
static void mutex_unlock(int *p) { (void)p; }
static void device_lock(struct device *d) { (void)d; }
static void device_unlock(struct device *d) { (void)d; }
static bool driver_allows_async_probing(struct device_driver *r) { (void)r; return false; }
static void async_synchronize_full(void) { effects++; }
static void pm_runtime_get_sync(struct device *d) { (void)d; effects++; }
static void pm_runtime_put_sync(struct device *d) { (void)d; effects++; }
static void driver_sysfs_remove(struct device *d) { (void)d; sysfs++; effects++; }
static int driver_sysfs_add(struct device *d) { (void)d; return 0; }
static void blocking_notifier_call_chain(int *a,int b,struct device *d) { (void)a;(void)b;(void)d; notifications++; effects++; }
static void dev_set_drvdata(struct device *d, void *v) { assert(!v); d->data=0; effects++; }
static void device_pm_check_callbacks(struct device *d) { (void)d; effects++; }
static int release_nodes(struct device *d,struct list_head *a,struct list_head *b,unsigned long f) { (void)d;(void)a;(void)b;(void)f; resources++; effects++; return 0; }
static void remove_bind_files(struct device_driver *r) { (void)r; effects++; }
static void driver_remove_groups(struct device_driver *r,void *g) { (void)r;(void)g; effects++; }
static int driver_attr_uevent;
static void driver_remove_file(struct device_driver *r,void *a) { (void)r;(void)a; effects++; }
static void module_remove_driver(struct device_driver *r) { (void)r; effects++; }
static void kobject_put(struct kobject *k) { (void)k; effects++; }
static void bus_put(struct bus_type *b) { (void)b; effects++; }
static void sysfs_remove_link(struct kobject *k,const char *s) { (void)k;(void)s; effects++; }
static const char *dev_name(struct device *d) { (void)d; return "test"; }
static void device_remove_attrs(struct bus_type *b,struct device *d) { (void)b;(void)d; effects++; }
static void device_remove_groups(struct device *d,void *g) { (void)d;(void)g; effects++; }
static void dpm_sysfs_remove(struct device *d) { (void)d; effects++; }
static void devtmpfs_delete_node(struct device *d) { (void)d; effects++; }
static void device_remove_sys_dev_entry(struct device *d) { (void)d; effects++; }
static int dev_attr_dev, dev_attr_uevent;
static void device_remove_file(struct device *d,void *a) { (void)d;(void)a; effects++; }
static void device_remove_class_symlinks(struct device *d) { (void)d; effects++; }
static void core_device_remove_attrs(struct device *d) { (void)d; effects++; }
static void device_pm_remove(struct device *d) { (void)d; effects++; }
static void driver_deferred_probe_del(struct device *d) { (void)d; effects++; }
static void (*platform_notify_remove)(struct device *);
static void kobject_uevent(struct kobject *k,int e) { (void)k;(void)e; effects++; }
static struct kobject *get_glue_dir(struct device *d) { (void)d; return NULL; }
static void kobject_del(struct kobject *k) { (void)k; effects++; }
static void cleanup_glue_dir(struct device *d,struct kobject *k) { (void)d;(void)k; effects++; }
static int remove_callback(struct device *d) { (void)d; callbacks++; effects++; return -EBUSY; }
static void dismiss_callback(struct device *d) { (void)d; dismissed++; effects++; }
static int probe_callback(struct device *d);
static int atomic_read(int *n) { return *n; }
static void atomic_inc(int *n) { ++*n; }
static void atomic_dec(int *n) { --*n; }
static int probe_count, probe_waitqueue, deferred_trigger_count;
static void wake_up(int *x) { (void)x; }
static int pinctrl_bind_pins(struct device *d) { (void)d; return 0; }
static void pinctrl_init_done(struct device *d) { (void)d; }
static void driver_bound(struct device *d) { assert(d->driver); }
static void driver_deferred_probe_add(struct device *d) { (void)d; }
static void driver_deferred_probe_trigger(void) { }
'''
BASE_FUNCS = [
 ('drivers/base/devres.c','devres_release_all'),
 ('drivers/base/dd.c','__device_release_driver'),('drivers/base/dd.c','device_release_driver'),
 ('drivers/base/dd.c','driver_detach'),('drivers/base/dd.c','really_probe'),('drivers/base/dd.c','device_bind_driver'),
 ('drivers/base/bus.c','bus_remove_driver'),('drivers/base/driver.c','driver_unregister'),
 ('drivers/base/bus.c','bus_remove_device'),('drivers/base/core.c','device_del'),('drivers/base/core.c','device_unregister')]
def base_functions():
 result=[]
 for path,name in BASE_FUNCS:
  s=body(path,name)
  # bus.c and core.c each have a private, unrelated device_remove_attrs function.
  if name=='device_del': s=s.replace('device_remove_attrs(dev);','core_device_remove_attrs(dev);')
  result.append(s)
 return '\n'.join(result)
WRAPPER_SHIM = r'''
struct resource { struct resource *parent; };
struct platform_device { struct device dev; bool id_auto; int id, num_resources; struct resource *resource; };
static int platform_devid_ida;
#define PLATFORM_DEVID_AUTO -2
static void ida_simple_remove(int *a,int b) { (void)a;(void)b; effects++; }
static void release_resource(struct resource *r) { (void)r; resources++; effects++; }
static void platform_device_put(struct platform_device *p) { put_device(&p->dev); }
struct spi_master { struct device dev; bool queued, queue_dead; int queue_lock; struct list_head list; };
static int board_lock;
static int spi_destroy_queue(struct spi_master *m) { (void)m; effects++; return 0; }
static void msleep(int n) { (void)n; }
static int __unregister(struct device *d,void *p) { (void)p; device_unregister(d); return 0; }
static int device_for_each_child(struct device *d,void *p,int (*fn)(struct device *,void *)) { (void)d;(void)p;(void)fn; effects++; return 0; }
struct pci_dev;
struct pci_bus { struct pci_bus *parent; struct device dev; struct device *bridge; struct list_head node, devices; struct pci_dev *self; };
struct pci_dev { struct device dev; struct pci_bus *bus, *subordinate; struct list_head bus_list; int is_added; struct resource resource[2]; };
struct pci_host_bridge { struct device dev; struct pci_bus *bus; };
struct pci_driver { struct device_driver driver; };
#define PCI_NUM_RESOURCES 2
static int pci_bus_sem;
static void pci_cleanup_rom(struct pci_dev *d) { (void)d; effects++; }
static void pci_pme_active(struct pci_dev *d,bool b) { (void)d;(void)b; effects++; }
static void pci_proc_detach_device(struct pci_dev *d) { (void)d; effects++; }
static void pci_remove_sysfs_dev_files(struct pci_dev *d) { (void)d; effects++; }
static void pcie_aspm_exit_link_state(struct pci_dev *d) { (void)d; effects++; }
static void down_write(int *p) { (void)p; }
static void up_write(int *p) { (void)p; }
static void pci_proc_detach_bus(struct pci_bus *b) { (void)b; effects++; }
static void pci_bus_release_busn_res(struct pci_bus *b) { (void)b; resources++; effects++; }
static void pci_remove_legacy_files(struct pci_bus *b) { (void)b; effects++; }
static void pcibios_remove_bus(struct pci_bus *b) { (void)b; effects++; }
static void pci_lock_rescan_remove(void) { }
static void pci_unlock_rescan_remove(void) { }
static bool pci_is_root_bus(struct pci_bus *b) { return !b->parent; }
#define to_pci_host_bridge(d) ((struct pci_host_bridge *)(d))
static void pci_free_dynids(struct pci_driver *r) { (void)r; effects++; }
'''
WRAPPERS = [('drivers/base/platform.c', 'platform_device_del'),('drivers/base/platform.c','platform_device_unregister'),('drivers/spi/spi.c','spi_unregister_master')]+[('drivers/pci/remove.c',n) for n in ('pci_free_resources','pci_stop_dev','pci_destroy_dev','pci_remove_bus','pci_stop_bus_device','pci_remove_bus_device','pci_stop_and_remove_bus_device','pci_stop_and_remove_bus_device_locked','pci_stop_root_bus','pci_remove_root_bus')]+[('drivers/pci/pci-driver.c','pci_unregister_driver')]
SETUP = r'''
static struct module module;
static struct driver_private dp;
static struct bus_private bp;
static struct bus_type bus = { .p=&bp, .probe=probe_callback, .remove=remove_callback };
static struct device_driver driver = { .no_forced_unbind=true, .owner=&module, .p=&dp, .bus=&bus, .name="critical" };
static struct pm_domain pm = { .dismiss=dismiss_callback };
static struct device_private priv;
static void init_device(struct device *d,struct device *p) { memset(d,0,sizeof(*d));d->parent=p;d->p=&priv;d->refs=1;d->data=7;d->kobj.parent=&priv;d->bus=&bus;d->pm_domain=&pm;d->devres_head.prev=d->devres_head.next=&d->devres_head; }
static void protect(struct device *d) { assert(!device_lifetime_probe_begin(d,&driver));d->driver=&driver;device_lifetime_probe_end(d); }
static int probe_callback(struct device *d) { callbacks++; if(probe_mode==1) return -ENOMEM; hardware++; if(probe_mode==2) { device_lifetime_quarantine(d); assert(devres_release_all(d)==-EBUSY); return -EIO; } return 0; }
'''
CASES = r'''
static struct device parent, child;
static pthread_mutex_t event_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t event=PTHREAD_COND_INITIALIZER;
static int step;
static void advance(int s) { pthread_mutex_lock(&event_lock);step=s;pthread_cond_broadcast(&event);pthread_mutex_unlock(&event_lock); }
static void waitfor(int s) { pthread_mutex_lock(&event_lock);while(step<s) pthread_cond_wait(&event,&event_lock);pthread_mutex_unlock(&event_lock); }
static void *probe_first(void *unused) { (void)unused;protect(&child);advance(1);waitfor(2);assert(!device_lifetime_remove_begin(&parent));return NULL; }
static void *remove_first(void *unused) { (void)unused;assert(device_lifetime_remove_begin(&parent));advance(1);waitfor(2);return NULL; }
int main(int argc,char **argv) {
 assert(argc==2); const char *c=argv[1];
 init_device(&parent,NULL);init_device(&child,&parent);
 if(!strcmp(c,"probe-wins") || !strcmp(c,"remove-wins")) {
  pthread_t t; bool probe=!strcmp(c,"probe-wins");
  assert(!pthread_create(&t,NULL,probe?probe_first:remove_first,NULL));waitfor(1);
  if(probe) { assert(!device_lifetime_remove_begin(&parent));assert(parent.refs==2&&child.refs==2&&module.refs==1); }
  else { assert(device_lifetime_probe_begin(&child,&driver)==-EBUSY);assert(!hardware&&parent.refs==1&&child.refs==1&&module.refs==0); }
  advance(2);assert(!pthread_join(t,NULL));return 0;
 }
 if(!strcmp(c,"overlap")) { assert(device_lifetime_detach_begin(&parent));assert(!device_lifetime_detach_begin(&parent));assert(device_lifetime_probe_begin(&child,&driver)==-EBUSY);device_lifetime_detach_end(&parent);protect(&child);assert(!device_lifetime_detach_begin(&parent));return 0; }
 if(!strcmp(c,"module-refusal")) { struct module pm={.going=true};struct device_driver pd={.owner=&pm};parent.lifetime_driver=&pd;assert(device_lifetime_probe_begin(&child,&driver)==-EBUSY);assert(!module.refs&&!driver.lifetime_pinned&&child.refs==1&&parent.refs==1);return 0; }
 if(!strcmp(c,"dependency")) { struct device sibling;init_device(&sibling,&parent);protect(&child);assert(!device_lifetime_depend(&child,&sibling));assert(sibling.refs==2&&!device_lifetime_remove_begin(&sibling));assert(!device_lifetime_depend(&child,&sibling));assert(sibling.refs==2);return 0; }
 if(!strcmp(c,"dependency-removing")) { struct device sibling;init_device(&sibling,&parent);assert(device_lifetime_remove_begin(&sibling));protect(&child);assert(device_lifetime_depend(&child,&sibling)==-EBUSY);assert(sibling.refs==1);return 0; }
 if(!strcmp(c,"nonroot")) { struct device bridge;struct pci_bus b={.parent=(struct pci_bus *)1,.bridge=&bridge};init_device(&bridge,NULL);pci_stop_root_bus(&b);pci_remove_root_bus(&b);assert(!bridge.lifetime_flags&&!effects);return 0; }
 if(!strcmp(c,"driver-race")) { assert(device_lifetime_driver_remove(&driver));assert(device_lifetime_probe_begin(&child,&driver)==-EBUSY);device_lifetime_driver_start(&driver);protect(&child);assert(!device_lifetime_driver_remove(&driver));return 0; }
 if(!strcmp(c,"depth")) { struct device chain[33];for(int i=0;i<33;i++) init_device(&chain[i],i?&chain[i-1]:NULL);assert(device_lifetime_probe_begin(&chain[32],&driver)==-EBUSY);assert(!module.refs);return 0; }
 if(!strcmp(c,"safe-oom") || !strcmp(c,"uncertain") || !strcmp(c,"ordinary")) {
  bool uncertain=!strcmp(c,"uncertain"), ordinary=!strcmp(c,"ordinary");
  driver.no_forced_unbind=!ordinary;probe_mode=uncertain?2:1;assert(really_probe(&child,&driver)==0);assert(callbacks==1);
  if(uncertain) {assert(resources==0&&child.data==7&&child.driver==NULL&&hardware==1);assert(really_probe(&child,&driver)==-EBUSY);assert(callbacks==1);assert(devres_release_all(&child)==-EBUSY);}
  else {assert(resources==1&&child.data==0&&child.driver==NULL&&hardware==0);probe_mode=0;assert(really_probe(&child,&driver)==1);assert(child.driver==&driver);}
  if(ordinary) {assert(!module.refs&&child.refs==1);device_release_driver(&child);assert(callbacks==3&&resources==2&&child.driver==NULL);assert(really_probe(&child,&driver)==1);}
  else {assert(module.refs==1&&child.refs==2&&parent.refs==2);int prior=effects;device_release_driver(&child);assert(effects==prior);}
  return 0;
 }
 if(!strcmp(c,"direct-bind")) { child.driver=&driver;assert(!device_bind_driver(&child));assert(module.refs==1&&child.refs==2);assert(!device_lifetime_driver_remove(&driver));return 0; }
 if(!strcmp(c,"other-driver")) { struct device_driver other={0};protect(&child);assert(device_lifetime_probe_begin(&child,&other)==-EBUSY);assert(child.driver==&driver&&module.refs==1);return 0; }
 if(!strcmp(c,"unrelated-release")) {driver.no_forced_unbind=false;assert(really_probe(&child,&driver)==1);device_release_driver(&child);assert(callbacks==2&&resources==1&&child.data==0&&child.driver==NULL);assert(!module.refs);return 0;}
 protect(&child); effects=0;
 if(!strcmp(c,"release")) device_release_driver(&child);
 else if(!strcmp(c,"parent-release")) device_release_driver(&parent);
 else if(!strcmp(c,"delete")) device_del(&child);
 else if(!strcmp(c,"unregister")) { device_unregister(&child);device_unregister(&child); }
 else if(!strcmp(c,"bus-remove")) bus_remove_device(&child);
 else if(!strcmp(c,"driver-unregister")) {driver_unregister(&driver);driver_unregister(&driver);}
 else if(!strcmp(c,"driver-detach")) { dp.klist_devices.k_list.nonempty=1;driver_detach(&driver); }
 else if(!strcmp(c,"driver-bus")) bus_remove_driver(&driver);
 else if(!strcmp(c,"devres")) assert(devres_release_all(&child)==-EBUSY);
 else if(!strncmp(c,"platform-",9)) { struct platform_device p={0};init_device(&p.dev,NULL);protect(&p.dev);effects=0;if(!strcmp(c,"platform-del"))platform_device_del(&p);else platform_device_unregister(&p);assert(p.dev.refs==2); }
 else if(!strcmp(c,"spi-master")) { struct spi_master m={.queued=true};init_device(&m.dev,NULL);protect(&m.dev);effects=0;spi_unregister_master(&m);assert(!m.queue_dead&&m.dev.refs==2); }
 else if(!strncmp(c,"pci-",4)) { struct pci_host_bridge h={0};struct pci_bus b={.bridge=&h.dev};struct pci_dev d={.bus=&b,.is_added=1};struct pci_driver pd={.driver=driver};init_device(&h.dev,NULL);init_device(&d.dev,&h.dev);init_device(&b.dev,&h.dev);h.bus=&b;protect(&d.dev);assert(!device_lifetime_depend(&d.dev,&b.dev));effects=0;
  if(!strcmp(c,"pci-stop"))pci_stop_bus_device(&d);else if(!strcmp(c,"pci-destroy"))pci_destroy_dev(&d);else if(!strcmp(c,"pci-remove"))pci_remove_bus_device(&d);else if(!strcmp(c,"pci-tree"))pci_stop_and_remove_bus_device_locked(&d);else if(!strcmp(c,"pci-bus"))pci_remove_bus(&b);else if(!strcmp(c,"pci-root-stop"))pci_stop_root_bus(&b);else if(!strcmp(c,"pci-root-remove"))pci_remove_root_bus(&b);else if(!strcmp(c,"pci-driver"))pci_unregister_driver(&pd);else if(!strcmp(c,"pci-bus-direct"))device_unregister(&b.dev);else abort();assert(d.is_added==1&&d.dev.refs==2&&h.dev.refs==2&&h.bus==&b); }
 else abort();
 assert(effects==0&&callbacks==0&&resources==0&&notifications==0&&dismissed==0&&sysfs==0);
 assert(child.data==7&&child.driver==&driver&&child.refs==2&&parent.refs==2&&module.refs==1);return 0;
}
'''
def program(core=CORE, mutate=None):
 functions=base_functions()+'\n'+WRAPPER_SHIM+'\n'+'\n'.join(body(p,n) for p,n in WRAPPERS)
 if mutate:
  old,new=mutate
  assert old in functions,old
  functions=functions.replace(old,new,1)
 return SHIM+HEADER+core+functions+SETUP+CASES
