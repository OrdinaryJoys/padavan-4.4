#include <linux/version.h>
#include <linux/module.h>
#include <linux/types.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/err.h>
#include <linux/slab.h>
#include <linux/completion.h>
#include <asm/io.h>
#include <linux/mtd/mtd.h>
#include <linux/mtd/map.h>
#include <linux/mtd/concat.h>
#include <linux/mtd/partitions.h>
#if defined (CONFIG_MIPS)
#include <asm/addrspace.h>
#endif

#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))
static void mt_mtd_erase_complete_wifi(struct erase_info *ei)
{
	complete((struct completion *)ei->priv);
}
#endif

int mt_mtd_write_nm_wifi(char *name, loff_t to, size_t len, const u_char *buf)
{
	int ret;
	size_t rdlen = 0, wrlen = 0;
	struct mtd_info *mtd;
	struct erase_info ei = { 0 };
	u_char *bak = NULL;
#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))
	DECLARE_COMPLETION_ONSTACK(erase_done);
#endif

	if (!name || (!buf && len))
		return -EINVAL;

	mtd = get_mtd_device_nm(name);
	if (IS_ERR(mtd))
		return PTR_ERR(mtd);

	/* This helper preserves and rewrites only the first eraseblock. */
	if (!mtd->erasesize || mtd->erasesize > mtd->size || to < 0 ||
	    to > mtd->erasesize || len > mtd->erasesize - (size_t)to) {
		ret = len > mtd->erasesize ? -E2BIG : -EINVAL;
		goto out_put;
	}
	if (!len) {
		ret = 0;
		goto out_put;
	}

	bak = kmalloc(mtd->erasesize, GFP_KERNEL);
	if (bak == NULL) {
		ret = -ENOMEM;
		goto out_put;
	}

	ret = mtd_read(mtd, 0, mtd->erasesize, &rdlen, bak);

	if (ret)
		goto out_free;
	if (rdlen != mtd->erasesize) {
		ret = -EIO;
		goto out_free;
	}

	memcpy(bak + to, buf, len);

#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))
	ei.mtd = mtd;
	ei.callback = mt_mtd_erase_complete_wifi;
	ei.priv = (unsigned long)&erase_done;
#endif
	ei.addr = 0;
	ei.len = mtd->erasesize;
	ret = mtd_erase(mtd, &ei);

	if (ret)
		goto out_free;
#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))
	/* The callback owns ei until completion, including asynchronous errors. */
	wait_for_completion(&erase_done);
	if (ei.state != MTD_ERASE_DONE) {
		ret = -EIO;
		goto out_free;
	}
#endif

	ret = mtd_write(mtd, 0, mtd->erasesize, &wrlen, bak);
	if (!ret && wrlen != mtd->erasesize)
		ret = -EIO;

out_free:
	kfree(bak);
out_put:
	put_mtd_device(mtd);
	return ret;
}
EXPORT_SYMBOL(mt_mtd_write_nm_wifi);


int mt_mtd_read_nm_wifi(char *name, loff_t from, size_t len, u_char *buf)
{
	int ret;
	size_t rdlen = 0;
	struct mtd_info *mtd;

	if (!name || (!buf && len))
		return -EINVAL;

	mtd = get_mtd_device_nm(name);
	if (IS_ERR(mtd))
		return PTR_ERR(mtd);
	if (from < 0 || (u64)from > mtd->size || len > mtd->size - (u64)from) {
		ret = -EINVAL;
		goto out_put;
	}
	if (!len) {
		ret = 0;
		goto out_put;
	}

	ret = mtd_read(mtd, from, len, &rdlen, buf);

	if (!ret && rdlen != len)
		ret = -EIO;

out_put:
	put_mtd_device(mtd);

	return ret;
}
EXPORT_SYMBOL(mt_mtd_read_nm_wifi);
