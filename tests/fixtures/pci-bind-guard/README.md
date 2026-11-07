The complete `rt_pci_driver` initializer is copied verbatim from commit
`60ae6bf98bd46b68c648620c599f1aa78073131e`; manifest.json records its source
path and SHA256. The regression pins that same SHA independently.

The historical initializer keeps the default `suppress_bind_attrs=false`.
Combined with the actual PCI registration body and final bus bind-file
decision block, it reproduces exposure of the manual bind/unbind files.
The current initializer prevents their creation without removing module
cleanup or PCI shutdown callbacks.

This fixture neither performs PCI removal nor proves module unloading or
DMA retirement. Only the named native registration bodies, full initializer,
and final bus function fragment execute; all hardware/driver core interfaces
are inert recorders. Physical removal and other PCI sysfs controls remain
outside this policy guard.
