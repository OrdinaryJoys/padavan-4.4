static struct pci_driver rt_pci_driver = {
name:
	RTMP_DRV_NAME,
id_table :
	rt_pci_tbl,
probe :
	rt_pci_probe,
shutdown :
	rt_pci_shutdown,
#if LINUX_VERSION_CODE >= 0x20412
remove :
	DEVEXIT_P(rt_pci_remove),
#else
remove :
	__devexit(rt_pci_remove),
#endif

#if (KERNEL_VERSION(2, 5, 0) <= LINUX_VERSION_CODE)
#ifdef CONFIG_PM
suspend :
	rt_pci_suspend,
resume :
	rt_pci_resume,
#endif
#endif
};
