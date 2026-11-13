"""Astra-authored extra owner/PCI probe cases, retained after independent review."""
import device_lifetime_harness as h
PCI_SHIM = r'''
static int irq_calls, pci_probe_calls, irq_failure;
#define to_pci_dev(d) ((struct pci_dev *)(d))
#define to_pci_driver(d) ((struct pci_driver *)(d))
static void pci_assign_irq(struct pci_dev *d) { (void)d; irq_calls++; }
static int pcibios_alloc_irq(struct pci_dev *d) { (void)d; return irq_failure; }
static void pcibios_free_irq(struct pci_dev *d) { (void)d; }
static struct pci_dev *pci_dev_get(struct pci_dev *d) { get_device(&d->dev);return d; }
static void pci_dev_put(struct pci_dev *d) { put_device(&d->dev); }
static int __pci_device_probe(struct pci_driver *r,struct pci_dev *d) { (void)r;(void)d;pci_probe_calls++;return 0; }
'''

CASES = r'''
static void chain_pins(void) {
 struct device a,b,c; struct module ma={0},mb={0};
 struct device_driver da={.owner=&ma},db={.owner=&mb};
 init_device(&a,NULL);init_device(&b,&a);init_device(&c,&b);
 a.lifetime_driver=a.driver=&da;b.lifetime_driver=b.driver=&db;
 int original=module.refs;
 protect(&c);
 assert(ma.refs==1&&mb.refs==1&&module.refs==original+1);
 assert(da.lifetime_pinned&&db.lifetime_pinned);
 assert(a.refs==2&&b.refs==2&&c.refs==2);
 assert(!device_lifetime_driver_remove(&da));
 assert(!device_lifetime_driver_remove(&db));
 assert(!device_lifetime_remove_begin(&a));
 assert(!device_lifetime_remove_begin(&b));
 protect(&c);
 assert(ma.refs==1&&mb.refs==1&&module.refs==original+1);
}
static void late_ancestor_binding(void) {
 struct device a,c;struct module late={0};
 struct device_driver owner={.owner=&late};
 init_device(&a,NULL);init_device(&c,&a);protect(&c);
 assert(!a.lifetime_driver&&a.refs==2);
 assert(!device_lifetime_probe_begin(&a,&owner));
 a.driver=&owner;device_lifetime_probe_end(&a);
 assert(late.refs==1&&owner.lifetime_pinned);
 assert(a.lifetime_driver==&owner&&a.refs==2);
 assert(!device_lifetime_driver_remove(&owner));
}
static void deep_transaction_rollback(void) {
 struct device a,b,c;struct module ma={.going=true},mb={0},mc={0};
 struct device_driver da={.owner=&ma},db={.owner=&mb},dc={.owner=&mc,.no_forced_unbind=true};
 init_device(&a,NULL);init_device(&b,&a);init_device(&c,&b);
 a.lifetime_driver=&da;b.lifetime_driver=&db;
 assert(device_lifetime_probe_begin(&c,&dc)==-EBUSY);
 assert(!ma.refs&&!mb.refs&&!mc.refs);
 assert(!da.lifetime_pinned&&!db.lifetime_pinned&&!dc.lifetime_pinned);
 assert(a.refs==1&&b.refs==1&&c.refs==1);
 assert(!a.lifetime_flags&&!b.lifetime_flags&&!c.lifetime_flags);
}
static void no_readd_cancels_claim(void) {
 struct device a,c;init_device(&a,NULL);init_device(&c,&a);
 assert(device_lifetime_remove_begin(&a));
 assert(device_lifetime_add(&a)==-EBUSY);
 assert(device_lifetime_add(&c)==-EBUSY);
 assert(device_lifetime_probe_begin(&c,&driver)==-EBUSY);
 assert(a.lifetime_flags&LIFETIME_REMOVING);
}
static void exact_depth_and_unrelated_dependency(void) {
 struct device chain[32],ordinary,dep;struct module m={0};
 struct device_driver d={.owner=&m,.no_forced_unbind=true};
 for(int i=0;i<32;i++)init_device(&chain[i],i?&chain[i-1]:NULL);
 assert(!device_lifetime_probe_begin(&chain[31],&d));
 chain[31].driver=&d;device_lifetime_probe_end(&chain[31]);
 for(int i=0;i<32;i++)assert(chain[i].refs==2);
 assert(m.refs==1);
 init_device(&ordinary,NULL);init_device(&dep,NULL);
 assert(!device_lifetime_depend(&ordinary,&dep));
 assert(dep.refs==1&&!dep.lifetime_flags);
}
static void safe_failure_does_not_authorize_different_driver(void) {
 struct device d;struct module m={0};struct device_driver other={.owner=&m};
 init_device(&d,NULL);probe_mode=1;
 assert(really_probe(&d,&driver)==0);
 assert(!d.driver&&d.lifetime_driver==&driver);
 assert(device_lifetime_probe_begin(&d,&other)==-EBUSY);
 assert(!m.refs&&!other.lifetime_pinned);
 probe_mode=0;assert(really_probe(&d,&driver)==1);
 assert(d.driver==&driver);
}
static void actual_pci_probe(bool removed,bool irq_error) {
 struct device bridge;
 struct pci_bus root={0},leaf={.parent=&root};
 struct pci_dev endpoint={.bus=&leaf};
 init_device(&bridge,NULL);init_device(&root.dev,&bridge);
 init_device(&leaf.dev,&bridge);init_device(&endpoint.dev,&bridge);
 root.bridge=leaf.bridge=&bridge;
 if(removed)assert(device_lifetime_remove_begin(&root.dev));
 protect(&endpoint.dev);irq_failure=irq_error?-EAGAIN:0;
 int ret=pci_device_probe(&endpoint.dev);
 if(removed) {
  assert(ret==-EBUSY&&!irq_calls&&!pci_probe_calls);
  assert(endpoint.dev.refs==2&&root.dev.refs==1);
 } else {
  assert(root.dev.refs==2&&leaf.dev.refs==2&&irq_calls==1);
  assert(!device_lifetime_remove_begin(&root.dev));
  assert(!device_lifetime_remove_begin(&leaf.dev));
  assert(ret==(irq_error?-EAGAIN:0));
  assert(pci_probe_calls==(irq_error?0:1));
  assert(endpoint.dev.refs==(irq_error?2:3));
 }
}
int main(int argc,char **argv) {
 assert(argc==2);
 if(!strcmp(argv[1],"chain-pins"))chain_pins();
 else if(!strcmp(argv[1],"late-ancestor"))late_ancestor_binding();
 else if(!strcmp(argv[1],"deep-rollback"))deep_transaction_rollback();
 else if(!strcmp(argv[1],"no-readd"))no_readd_cancels_claim();
 else if(!strcmp(argv[1],"exact-depth"))exact_depth_and_unrelated_dependency();
 else if(!strcmp(argv[1],"failed-probe-owner"))safe_failure_does_not_authorize_different_driver();
 else if(!strcmp(argv[1],"pci-probe-blocked"))actual_pci_probe(true,false);
 else if(!strcmp(argv[1],"pci-probe-admitted"))actual_pci_probe(false,false);
 else if(!strcmp(argv[1],"pci-probe-irq-failure"))actual_pci_probe(false,true);
 else abort();
 return 0;
}
'''

def program(core=h.CORE,pci_mutation=False):
 source=h.program(core=core).replace(h.CASES,CASES)
 pci_body=h.body('drivers/pci/pci-driver.c','pci_device_probe')
 if pci_mutation:
  assert 'device_lifetime_depend(dev, &bus->dev)' in pci_body
  pci_body=pci_body.replace('device_lifetime_depend(dev, &bus->dev)','0')
 return source.replace(h.SETUP,PCI_SHIM+pci_body+h.SETUP)
