#ifndef _LINUX_DEVICE_LIFETIME_H
#define _LINUX_DEVICE_LIFETIME_H

#include <linux/types.h>

struct device;
struct device_driver;

/* K2P fixed hardware cannot be hot-removed safely. These holds protect
 * objects, mappings and module text, not active hardware/reset ownership.
 * No hold is released during this boot. Ordinary shutdown is independent.
 */
#ifdef CONFIG_K2P_RESET_GUARD
int device_lifetime_probe_begin(struct device *dev, struct device_driver *drv);
void device_lifetime_probe_end(struct device *dev);
int device_lifetime_depend(struct device *dev, struct device *dependency);
void device_lifetime_quarantine(struct device *dev);
bool device_lifetime_quarantined(struct device *dev);
bool device_lifetime_remove_begin(struct device *dev);
bool device_lifetime_detach_begin(struct device *dev);
void device_lifetime_detach_end(struct device *dev);
bool device_lifetime_driver_remove(struct device_driver *drv);
void device_lifetime_driver_start(struct device_driver *drv);
bool device_lifetime_devres_allowed(struct device *dev);
int device_lifetime_add(struct device *dev);
#else
static inline int device_lifetime_probe_begin(struct device *d, struct device_driver *r) { return 0; }
static inline void device_lifetime_probe_end(struct device *d) { }
static inline int device_lifetime_depend(struct device *d, struct device *p) { return 0; }
static inline void device_lifetime_quarantine(struct device *d) { }
static inline bool device_lifetime_quarantined(struct device *d) { return false; }
static inline bool device_lifetime_remove_begin(struct device *d) { return true; }
static inline bool device_lifetime_detach_begin(struct device *d) { return true; }
static inline void device_lifetime_detach_end(struct device *d) { }
static inline bool device_lifetime_driver_remove(struct device_driver *d) { return true; }
static inline void device_lifetime_driver_start(struct device_driver *d) { }
static inline bool device_lifetime_devres_allowed(struct device *d) { return true; }
static inline int device_lifetime_add(struct device *d) { return 0; }
#endif
#endif
