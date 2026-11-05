/***************************************************************************
 * MediaTek Inc.
 * 4F, No. 2 Technology 5th Rd.
 * Science-based Industrial Park
 * Hsin-chu, Taiwan, R.O.C.
 *
 * (c) Copyright 1997-2017, MediaTek, Inc.
 *
 * All rights reserved. MediaTek source code is an unpublished work and the
 * use of a copyright notice does not imply otherwise. This source code
 * contains confidential trade secret material of MediaTek. Any attemp
 * or participation in deciphering, decoding, reverse engineering or in any
 * way altering the source code is stricitly prohibited, unless the prior
 * written consent of MediaTek Technology, Inc. is obtained.
 ***************************************************************************

*/
#include "rt_config.h"

#ifndef CONFIG_PROPRIETARY_DRIVER

enum tm_wq_state {
	TM_WQ_IDLE,
	TM_WQ_INITIALIZING,
	TM_WQ_ACTIVE,
	TM_WQ_EXITING,
	TM_WQ_CANCELLED,
};

/* PCI scheduling may already own dma_state_lock: never acquire it from
 * tm_wq_lock. Allocation and destroy_workqueue must run outside both locks.
 */
static DEFINE_SPINLOCK(tm_wq_lock);

static INT tm_wq_prepare(struct workqueue_struct **owner, UINT8 *state,
	BOOLEAN *enabled)
{
	ULONG flags;
	INT ret = NDIS_STATUS_FAILURE;

	spin_lock_irqsave(&tm_wq_lock, flags);
	if (!*owner && *state == TM_WQ_IDLE) {
		*state = TM_WQ_INITIALIZING;
		if (enabled)
			*enabled = FALSE;
		ret = NDIS_STATUS_SUCCESS;
	}
	spin_unlock_irqrestore(&tm_wq_lock, flags);
	return ret;
}

static VOID tm_wq_abort(UINT8 *state)
{
	ULONG flags;

	spin_lock_irqsave(&tm_wq_lock, flags);
	*state = TM_WQ_IDLE;
	spin_unlock_irqrestore(&tm_wq_lock, flags);
}

static INT tm_wq_publish(RTMP_ADAPTER *pAd, struct workqueue_struct **owner,
	UINT8 *state, struct workqueue_struct *wq, BOOLEAN *enabled)
{
	ULONG flags;
	INT ret = NDIS_STATUS_FAILURE;
#if defined(LINUX) && defined(RTMP_PCI_SUPPORT)
	ULONG dma_flags = 0;
	BOOLEAN pci = IS_PCI_INF(pAd) || IS_PCIE_INF(pAd);

	if (pci)
		spin_lock_irqsave(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, dma_flags);
#endif
	spin_lock_irqsave(&tm_wq_lock, flags);
	if (*state == TM_WQ_INITIALIZING && !*owner &&
		!RtmpDmaStopping(pAd)) {
		*owner = wq;
		*state = TM_WQ_ACTIVE;
		if (enabled)
			*enabled = TRUE;
		ret = NDIS_STATUS_SUCCESS;
	}
	spin_unlock_irqrestore(&tm_wq_lock, flags);
#if defined(LINUX) && defined(RTMP_PCI_SUPPORT)
	if (pci)
		spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, dma_flags);
#endif
	return ret;
}

static INT tm_wq_destroy(struct workqueue_struct **owner, UINT8 *state,
	BOOLEAN *enabled)
{
	struct workqueue_struct *wq;
	ULONG flags;

	spin_lock_irqsave(&tm_wq_lock, flags);
	if (*state == TM_WQ_INITIALIZING) {
		/* The allocator retains its private queue until publication fails. */
		*state = TM_WQ_CANCELLED;
		spin_unlock_irqrestore(&tm_wq_lock, flags);
		return NDIS_STATUS_FAILURE;
	}
	if ((*state != TM_WQ_IDLE && *state != TM_WQ_ACTIVE) ||
		((*state == TM_WQ_IDLE) != (*owner == NULL))) {
		spin_unlock_irqrestore(&tm_wq_lock, flags);
		return NDIS_STATUS_FAILURE;
	}
	if (enabled)
		*enabled = FALSE;
	wq = *owner;
	*owner = NULL;
	*state = wq ? TM_WQ_EXITING : TM_WQ_IDLE;
	spin_unlock_irqrestore(&tm_wq_lock, flags);
	if (wq) {
		destroy_workqueue(wq);
		/* A fresh INIT_WORK may not replace work owned by the drain. */
		spin_lock_irqsave(&tm_wq_lock, flags);
		*state = TM_WQ_IDLE;
		spin_unlock_irqrestore(&tm_wq_lock, flags);
	}
	return NDIS_STATUS_SUCCESS;
}

static INT tm_wq_retirement_check(RTMP_ADAPTER *pAd)
{
	ULONG flags;
	INT ret = NDIS_STATUS_SUCCESS;

	spin_lock_irqsave(&tm_wq_lock, flags);
	if (pAd->qm_wq_state == TM_WQ_INITIALIZING)
		pAd->qm_wq_state = TM_WQ_CANCELLED;
	if (pAd->hif_wq_state == TM_WQ_INITIALIZING)
		pAd->hif_wq_state = TM_WQ_CANCELLED;
	if ((pAd->qm_wq_state != TM_WQ_IDLE && pAd->qm_wq_state != TM_WQ_ACTIVE) ||
		(pAd->hif_wq_state != TM_WQ_IDLE && pAd->hif_wq_state != TM_WQ_ACTIVE))
		ret = NDIS_STATUS_FAILURE;
	spin_unlock_irqrestore(&tm_wq_lock, flags);
	return ret;
}

static VOID ge_tx_pkt_deq_work(struct work_struct *work)
{
	RTMP_ADAPTER *pAd = container_of(work, struct _RTMP_ADAPTER, tx_deq_work);

	ge_tx_pkt_deq_func(pAd);
}

static VOID fp_tx_pkt_deq_work(struct work_struct *work)
{
	RTMP_ADAPTER *pAd = container_of(work, struct _RTMP_ADAPTER, tx_deq_work);

	fp_tx_pkt_deq_func(pAd);
}

static VOID fp_fair_tx_pkt_deq_work(struct work_struct *work)
{
	RTMP_ADAPTER *pAd = container_of(work, struct _RTMP_ADAPTER, tx_deq_work);

	fp_fair_tx_pkt_deq_func(pAd);
}

static INT tm_wq_qm_init(RTMP_ADAPTER *pAd)
{
	struct workqueue_struct *wq;
	RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);
	UINT8 qm = cap->qm;

	if (qm != FAST_PATH_QM && qm != FAST_PATH_FAIR_QM &&
		qm != GENERIC_QM && qm != GENERIC_FAIR_QM)
		return NDIS_STATUS_FAILURE;
	if (tm_wq_prepare(&pAd->qm_wq, &pAd->qm_wq_state,
		&pAd->tx_dequeue_scheduable) != NDIS_STATUS_SUCCESS)
		return NDIS_STATUS_FAILURE;

#if (KERNEL_VERSION(2, 6, 37) <= LINUX_VERSION_CODE)
	wq = alloc_workqueue("qm_wq", WQ_MEM_RECLAIM | WQ_UNBOUND, 0);
#else
	wq = create_singlethread_workqueue("qm_wq");
#endif
	if (!wq) {
		tm_wq_abort(&pAd->qm_wq_state);
		return NDIS_STATUS_RESOURCES;
	}

	if (qm == FAST_PATH_QM) {
		INIT_WORK(&pAd->tx_deq_work, fp_tx_pkt_deq_work);
	} else if (qm == FAST_PATH_FAIR_QM) {
		INIT_WORK(&pAd->tx_deq_work, fp_fair_tx_pkt_deq_work);
	} else if ((qm == GENERIC_QM) || (qm == GENERIC_FAIR_QM)) {
		INIT_WORK(&pAd->tx_deq_work, ge_tx_pkt_deq_work);
	}
	if (tm_wq_publish(pAd, &pAd->qm_wq, &pAd->qm_wq_state, wq,
		&pAd->tx_dequeue_scheduable) != NDIS_STATUS_SUCCESS) {
		destroy_workqueue(wq);
		tm_wq_abort(&pAd->qm_wq_state);
		return NDIS_STATUS_FAILURE;
	}
	return NDIS_STATUS_SUCCESS;
}

static VOID tx_dma_done_work(struct work_struct *work)
{
	POS_COOKIE obj = container_of(work, struct os_cookie, tx_dma_done_work);
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)((ULONG)(obj->pAd_va));

	tx_dma_done_func(pAd);
}

static VOID rx_done_work(struct work_struct *work)
{
	POS_COOKIE obj = container_of(work, struct os_cookie, rx_done_work[HIF_RX_IDX0]);
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)((ULONG)(obj->pAd_va));

	rx_done_func(pAd);
}

static VOID rx1_done_work(struct work_struct *work)
{
	POS_COOKIE obj = container_of(work, struct os_cookie, rx_done_work[HIF_RX_IDX1]);
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)((ULONG)(obj->pAd_va));

	rx1_done_func(pAd);
}

#ifdef ERR_RECOVERY
static VOID mt_mac_recovery_work(struct work_struct *work)
{
	POS_COOKIE obj = container_of(work, struct os_cookie, mac_recovery_work);
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)((ULONG)(obj->pAd_va));

	mt_mac_recovery_func(pAd);
}
#endif

#ifdef CONFIG_FWOWN_SUPPORT
static VOID mt_mac_fw_own_work(struct work_struct *work)
{
	POS_COOKIE obj = container_of(work, struct os_cookie, mac_fw_own_work);
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)((ULONG)(obj->pAd_va));

	mt_mac_fw_own_func(pAd);
}
#endif

#ifdef MULTI_LAYER_INTERRUPT
static VOID mt_subsys_int_work(struct work_struct *work)
{
	POS_COOKIE obj = container_of(work, struct os_cookie, subsys_int_work);
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)((ULONG)(obj->pAd_va));

	mt_subsys_int_func(pAd);
}
#endif

static INT tm_wq_hif_pci_init(RTMP_ADAPTER *pAd)
{
	struct workqueue_struct *wq;
	POS_COOKIE obj = (POS_COOKIE)pAd->OS_Cookie;

	if (tm_wq_prepare(&obj->hif_wq, &pAd->hif_wq_state, NULL) !=
		NDIS_STATUS_SUCCESS)
		return NDIS_STATUS_FAILURE;
#if (KERNEL_VERSION(2, 6, 37) <= LINUX_VERSION_CODE)
	wq = alloc_workqueue("hif_wq", WQ_MEM_RECLAIM | WQ_UNBOUND, 0);
#else
	wq = create_singlethread_workqueue("hif_wq");
#endif
	if (!wq) {
		tm_wq_abort(&pAd->hif_wq_state);
		return NDIS_STATUS_RESOURCES;
	}

	INIT_WORK(&obj->tx_dma_done_work, tx_dma_done_work);
	INIT_WORK(&obj->rx_done_work[HIF_RX_IDX0], rx_done_work);
	INIT_WORK(&obj->rx_done_work[HIF_RX_IDX1], rx1_done_work);

#ifdef ERR_RECOVERY
	INIT_WORK(&obj->mac_recovery_work, mt_mac_recovery_work);
#endif

#ifdef CONFIG_FWOWN_SUPPORT
	INIT_WORK(&obj->mac_fw_own_work, mt_mac_fw_own_work);
#endif

#ifdef MULTI_LAYER_INTERRUPT
	INIT_WORK(&obj->subsys_int_work, mt_subsys_int_work);
#endif

	if (tm_wq_publish(pAd, &obj->hif_wq, &pAd->hif_wq_state, wq, NULL) !=
		NDIS_STATUS_SUCCESS) {
		destroy_workqueue(wq);
		tm_wq_abort(&pAd->hif_wq_state);
		return NDIS_STATUS_FAILURE;
	}
	return NDIS_STATUS_SUCCESS;
}

static INT tm_wq_hif_init(RTMP_ADAPTER *pAd)
{
	INT ret = NDIS_STATUS_FAILURE;

	if (IS_PCI_INF(pAd) || IS_PCIE_INF(pAd) || IS_RBUS_INF(pAd)) {
		ret = tm_wq_hif_pci_init(pAd);
	}

	return ret;
}

static INT tm_wq_hif_pci_exit(RTMP_ADAPTER *pAd)
{
	POS_COOKIE obj = (POS_COOKIE)pAd->OS_Cookie;

	return tm_wq_destroy(&obj->hif_wq, &pAd->hif_wq_state, NULL);
}

static INT tm_wq_hif_exit(RTMP_ADAPTER *pAd)
{
	INT ret = NDIS_STATUS_SUCCESS;

	if (IS_PCI_INF(pAd) || IS_PCIE_INF(pAd) || IS_RBUS_INF(pAd)) {
		ret = tm_wq_hif_pci_exit(pAd);
	}

	return ret;
}

static INT tm_wq_qm_exit(RTMP_ADAPTER *pAd)
{
	return tm_wq_destroy(&pAd->qm_wq, &pAd->qm_wq_state,
		&pAd->tx_dequeue_scheduable);
}

static INT tm_wq_qm_schedule_taskOwned(RTMP_ADAPTER *pAd, enum task_type type)
{
	INT ret = NDIS_STATUS_SUCCESS;
	ULONG flags;

	spin_lock_irqsave(&tm_wq_lock, flags);
	if (pAd->qm_wq_state != TM_WQ_ACTIVE || !pAd->qm_wq) {
		spin_unlock_irqrestore(&tm_wq_lock, flags);
		return NDIS_STATUS_FAILURE;
	}

	switch (type) {
	case TX_DEQ_TASK:
		if (pAd->tx_dequeue_scheduable
#ifdef INTELP6_UDMA_CPU_LOAD_OPTIMIZATION
			&& !pAd->is_blocked
#endif
			) {
			queue_work(pAd->qm_wq, &pAd->tx_deq_work);
		}
		break;

	default:
		break;

	}

	spin_unlock_irqrestore(&tm_wq_lock, flags);
	return ret;
}

static INT tm_wq_qm_schedule_task(RTMP_ADAPTER *pAd, enum task_type type)
{
#if defined(LINUX) && defined(RTMP_PCI_SUPPORT)
	if (IS_PCI_INF(pAd) || IS_PCIE_INF(pAd)) {
		ULONG flags;
		INT ret;
		spin_lock_irqsave(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		if (pAd->dma_stopping || pAd->dma_quarantined) {
			spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
			return NDIS_STATUS_FAILURE;
		}
		ret = tm_wq_qm_schedule_taskOwned(pAd, type);
		spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		return ret;
	}
#endif
	return tm_wq_qm_schedule_taskOwned(pAd, type);
}

static INT tm_wq_hif_schedule_taskOwned(RTMP_ADAPTER *pAd, enum task_type type)
{
	INT ret = NDIS_STATUS_SUCCESS;
	POS_COOKIE obj = (POS_COOKIE)pAd->OS_Cookie;
	ULONG flags;

	spin_lock_irqsave(&tm_wq_lock, flags);
	if (pAd->hif_wq_state != TM_WQ_ACTIVE || !obj->hif_wq) {
		spin_unlock_irqrestore(&tm_wq_lock, flags);
		return NDIS_STATUS_FAILURE;
	}

	switch (type) {
	case CMD_MSG_TASK:

		break;

	case TX_DONE_TASK:
		queue_work(obj->hif_wq, &obj->tx_dma_done_work);
		break;

	case RX_DONE_TASK:
		queue_work(obj->hif_wq, &obj->rx_done_work[HIF_RX_IDX0]);
		break;

	case RX1_DONE_TASK:
		queue_work(obj->hif_wq, &obj->rx_done_work[HIF_RX_IDX1]);
		break;

#ifdef ERR_RECOVERY
	case ERROR_RECOVERY_TASK:
		queue_work(obj->hif_wq, &obj->mac_recovery_work);
		break;
#endif

#ifdef CONFIG_FWOWN_SUPPORT
	case FW_OWN_TASK:
		queue_work(obj->hif_wq, &obj->mac_fw_own_work);
		break;
#endif

#ifdef MULTI_LAYER_INTERRUPT
	case SUBSYS_INT_TASK:
		queue_work(obj->hif_wq, &obj->subsys_int_work);
		break;
#endif

	default:

		break;
	}

	spin_unlock_irqrestore(&tm_wq_lock, flags);
	return ret;
}

static INT tm_wq_hif_schedule_task(RTMP_ADAPTER *pAd, enum task_type type)
{
#if defined(LINUX) && defined(RTMP_PCI_SUPPORT)
	if (IS_PCI_INF(pAd) || IS_PCIE_INF(pAd)) {
		ULONG flags;
		INT ret;
		spin_lock_irqsave(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		if (pAd->dma_stopping || pAd->dma_quarantined) {
			spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
			return NDIS_STATUS_FAILURE;
		}
		ret = tm_wq_hif_schedule_taskOwned(pAd, type);
		spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		return ret;
	}
#endif
	return tm_wq_hif_schedule_taskOwned(pAd, type);
}


static INT tm_wq_qm_schedule_task_onOwned(RTMP_ADAPTER *pAd, INT cpu, enum task_type type)
{
	INT ret = NDIS_STATUS_SUCCESS;
	ULONG flags;

	spin_lock_irqsave(&tm_wq_lock, flags);
	if (pAd->qm_wq_state != TM_WQ_ACTIVE || !pAd->qm_wq) {
		spin_unlock_irqrestore(&tm_wq_lock, flags);
		return NDIS_STATUS_FAILURE;
	}

	switch (type) {
	case TX_DEQ_TASK:
		if (pAd->tx_dequeue_scheduable
#ifdef INTELP6_UDMA_CPU_LOAD_OPTIMIZATION
			&& !pAd->is_blocked
#endif
		) {
			queue_work_on(cpu, pAd->qm_wq, &pAd->tx_deq_work);
		}
		break;
	default:

		break;
	}

	spin_unlock_irqrestore(&tm_wq_lock, flags);
	return ret;
}

static INT tm_wq_qm_schedule_task_on(RTMP_ADAPTER *pAd, INT cpu, enum task_type type)
{
#if defined(LINUX) && defined(RTMP_PCI_SUPPORT)
	if (IS_PCI_INF(pAd) || IS_PCIE_INF(pAd)) {
		ULONG flags;
		INT ret;
		spin_lock_irqsave(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		if (pAd->dma_stopping || pAd->dma_quarantined) {
			spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
			return NDIS_STATUS_FAILURE;
		}
		ret = tm_wq_qm_schedule_task_onOwned(pAd, cpu, type);
		spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		return ret;
	}
#endif
	return tm_wq_qm_schedule_task_onOwned(pAd, cpu, type);
}

static INT tm_wq_hif_schedule_task_onOwned(RTMP_ADAPTER *pAd, INT cpu, enum task_type type)
{
	INT ret = NDIS_STATUS_SUCCESS;
	POS_COOKIE obj = (POS_COOKIE)pAd->OS_Cookie;
	ULONG flags;

	spin_lock_irqsave(&tm_wq_lock, flags);
	if (pAd->hif_wq_state != TM_WQ_ACTIVE || !obj->hif_wq) {
		spin_unlock_irqrestore(&tm_wq_lock, flags);
		return NDIS_STATUS_FAILURE;
	}

	switch (type) {
	case CMD_MSG_TASK:

		break;

	case TX_DONE_TASK:
		queue_work_on(cpu, obj->hif_wq, &obj->tx_dma_done_work);
		break;

	case RX_DONE_TASK:
		queue_work_on(cpu, obj->hif_wq, &obj->rx_done_work[HIF_RX_IDX0]);
		break;

	case RX1_DONE_TASK:
		queue_work_on(cpu, obj->hif_wq, &obj->rx_done_work[HIF_RX_IDX1]);
		break;

#ifdef ERR_RECOVERY
	case ERROR_RECOVERY_TASK:
		queue_work_on(cpu, obj->hif_wq, &obj->mac_recovery_work);
		break;
#endif

#ifdef CONFIG_FWOWN_SUPPORT
	case FW_OWN_TASK:
		queue_work_on(cpu, obj->hif_wq, &obj->mac_fw_own_work);
		break;
#endif

#ifdef MULTI_LAYER_INTERRUPT
	case SUBSYS_INT_TASK:
		queue_work_on(cpu, obj->hif_wq, &obj->subsys_int_work);
		break;
#endif

	default:

		break;
	}

	spin_unlock_irqrestore(&tm_wq_lock, flags);
	return ret;
}

static INT tm_wq_hif_schedule_task_on(RTMP_ADAPTER *pAd, INT cpu, enum task_type type)
{
#if defined(LINUX) && defined(RTMP_PCI_SUPPORT)
	if (IS_PCI_INF(pAd) || IS_PCIE_INF(pAd)) {
		ULONG flags;
		INT ret;
		spin_lock_irqsave(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		if (pAd->dma_stopping || pAd->dma_quarantined) {
			spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
			return NDIS_STATUS_FAILURE;
		}
		ret = tm_wq_hif_schedule_task_onOwned(pAd, cpu, type);
		spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		return ret;
	}
#endif
	return tm_wq_hif_schedule_task_onOwned(pAd, cpu, type);
}

struct tm_ops tm_wq_qm_ops = {
	.init = tm_wq_qm_init,
	.exit = tm_wq_qm_exit,
	.schedule_task = tm_wq_qm_schedule_task,
	.schedule_task_on = tm_wq_qm_schedule_task_on,
};

struct tm_ops tm_wq_hif_ops = {
	.init = tm_wq_hif_init,
	.exit = tm_wq_hif_exit,
	.schedule_task = tm_wq_hif_schedule_task,
	.schedule_task_on = tm_wq_hif_schedule_task_on,
};
#endif /*CONFIG_PROPRIETARY_DRIVER*/

static VOID ge_tx_pkt_deq_tasklet(ULONG param)
{
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)param;

	ge_tx_pkt_deq_func(pAd);
}

static VOID fp_tx_pkt_deq_tasklet(ULONG param)
{
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)param;

	fp_tx_pkt_deq_func(pAd);
}

static VOID fp_fair_tx_pkt_deq_tasklet(ULONG param)
{
	RTMP_ADAPTER *pAd = (RTMP_ADAPTER *)param;

	fp_fair_tx_pkt_deq_func(pAd);
}

static INT tm_tasklet_qm_init(RTMP_ADAPTER *pAd)
{
	INT ret = NDIS_STATUS_SUCCESS;
	RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);

	if (cap->qm == FAST_PATH_QM) {
		RTMP_OS_TASKLET_INIT(pAd, &pAd->tx_deque_tasklet, fp_tx_pkt_deq_tasklet, (unsigned long)pAd);
	} else if (cap->qm == FAST_PATH_FAIR_QM) {
		RTMP_OS_TASKLET_INIT(pAd, &pAd->tx_deque_tasklet, fp_fair_tx_pkt_deq_tasklet, (unsigned long)pAd);
	} else if ((cap->qm == GENERIC_QM) || (cap->qm == GENERIC_FAIR_QM)) {
		RTMP_OS_TASKLET_INIT(pAd, &pAd->tx_deque_tasklet, ge_tx_pkt_deq_tasklet, (unsigned long)pAd);
	}
	pAd->tx_dequeue_scheduable = TRUE;

	return ret;
}

static VOID tx_dma_done_tasklet(unsigned long data)
{
	PRTMP_ADAPTER pAd = (PRTMP_ADAPTER)data;

	tx_dma_done_func(pAd);
}

static VOID tr_done_tasklet(unsigned long data)
{
	PRTMP_ADAPTER pAd = (PRTMP_ADAPTER)data;

	tr_done_func(pAd);
}

static VOID rx_done_tasklet(unsigned long data)
{
	PRTMP_ADAPTER pAd = (PRTMP_ADAPTER)data;

	rx_done_func(pAd);
}

static VOID rx1_done_tasklet(unsigned long data)
{
	PRTMP_ADAPTER pAd = (PRTMP_ADAPTER)data;

	rx1_done_func(pAd);
}

#ifdef ERR_RECOVERY
static VOID mt_mac_recovery_tasklet(unsigned long data)
{
	PRTMP_ADAPTER pAd = (PRTMP_ADAPTER)data;

	mt_mac_recovery_func(pAd);
}
#endif

#ifdef CONFIG_FWOWN_SUPPORT
static VOID mt_mac_fw_own_tasklet(unsigned long data)
{
	PRTMP_ADAPTER pAd = (PRTMP_ADAPTER)data;

	mt_mac_fw_own_func(pAd);
}
#endif

#ifdef MULTI_LAYER_INTERRUPT
static VOID subsys_int_tasklet(unsigned long data)
{
	PRTMP_ADAPTER pAd = (PRTMP_ADAPTER)data;

	mt_subsys_int_func(pAd);
}
#endif

static INT tm_tasklet_hif_pci_init(RTMP_ADAPTER *pAd)
{
	POS_COOKIE obj = (POS_COOKIE)pAd->OS_Cookie;

	RTMP_OS_TASKLET_INIT(pAd, &obj->rx_done_task[HIF_RX_IDX0], rx_done_tasklet, (unsigned long)pAd);
	RTMP_OS_TASKLET_INIT(pAd, &obj->rx_done_task[HIF_RX_IDX1], rx1_done_tasklet, (unsigned long)pAd);

#ifdef ERR_RECOVERY
	RTMP_OS_TASKLET_INIT(pAd, &obj->mac_error_recovey_task, mt_mac_recovery_tasklet, (unsigned long)pAd);
#endif /* ERR_RECOVERY */

#ifdef CONFIG_FWOWN_SUPPORT
	RTMP_OS_TASKLET_INIT(pAd, &obj->mt_mac_fw_own_task, mt_mac_fw_own_tasklet, (unsigned long)pAd);
#endif /* CONFIG_FWOWN_SUPPORT */

#ifdef MULTI_LAYER_INTERRUPT
	RTMP_OS_TASKLET_INIT(pAd, &obj->subsys_int_task, subsys_int_tasklet, (unsigned long)pAd);
#endif

	RTMP_OS_TASKLET_INIT(pAd, &obj->tx_dma_done_task, tx_dma_done_tasklet, (unsigned long)pAd);

	RTMP_OS_TASKLET_INIT(pAd, &obj->tr_done_task, tr_done_tasklet, (unsigned long)pAd);

#ifdef CONFIG_AP_SUPPORT
	IF_DEV_CONFIG_OPMODE_ON_AP(pAd)
	{
	}
#endif /* CONFIG_AP_SUPPORT */

	return NDIS_STATUS_SUCCESS;
}

static INT tm_tasklet_hif_init(RTMP_ADAPTER *pAd)
{
	INT ret = NDIS_STATUS_SUCCESS;

	if (IS_PCI_INF(pAd) || IS_RBUS_INF(pAd)) {
		ret = tm_tasklet_hif_pci_init(pAd);
	}

	return ret;
}

static INT tm_tasklet_qm_exit(RTMP_ADAPTER *pAd)
{
	INT ret = NDIS_STATUS_SUCCESS;

	pAd->tx_dequeue_scheduable = FALSE;

	RTMP_OS_TASKLET_KILL(&pAd->tx_deque_tasklet);

	return ret;
}

static INT tm_tasklet_hif_pci_exit(RTMP_ADAPTER *pAd)
{
	POS_COOKIE obj = (POS_COOKIE)pAd->OS_Cookie;
	INT ret = NDIS_STATUS_SUCCESS;

	RTMP_OS_TASKLET_KILL(&obj->rx_done_task[HIF_RX_IDX0]);
	RTMP_OS_TASKLET_KILL(&obj->rx_done_task[HIF_RX_IDX1]);

#ifdef ERR_RECOVERY
	RTMP_OS_TASKLET_KILL(&obj->mac_error_recovey_task);
#endif /* ERR_RECOVERY */

#ifdef CONFIG_FWOWN_SUPPORT
	RTMP_OS_TASKLET_KILL(&obj->mt_mac_fw_own_task);
#endif /* CONFIG_FWOWN_SUPPORT */

#ifdef MULTI_LAYER_INTERRUPT
	RTMP_OS_TASKLET_KILL(&obj->subsys_int_task);
#endif

	RTMP_OS_TASKLET_KILL(&obj->tx_dma_done_task);
	RTMP_OS_TASKLET_KILL(&obj->tr_done_task);

#ifdef CONFIG_AP_SUPPORT
	IF_DEV_CONFIG_OPMODE_ON_AP(pAd) {
	}
#endif /* CONFIG_AP_SUPPORT */

	return ret;
}

static INT tm_tasklet_hif_exit(RTMP_ADAPTER *pAd)
{
	INT ret = NDIS_STATUS_SUCCESS;

	if (IS_PCI_INF(pAd) || IS_RBUS_INF(pAd)) {
		ret = tm_tasklet_hif_pci_exit(pAd);
	}

	return ret;
}

static INT tm_tasklet_qm_schedule_taskOwned(RTMP_ADAPTER *pAd, enum task_type type)
{
	INT ret = NDIS_STATUS_SUCCESS;

	switch (type) {
	case TX_DEQ_TASK:
		if (pAd->tx_dequeue_scheduable
#ifdef INTELP6_UDMA_CPU_LOAD_OPTIMIZATION
			&& !pAd->is_blocked
#endif
		) {
			RTMP_OS_TASKLET_SCHE(&pAd->tx_deque_tasklet);
		}

		break;

	default:

		break;
	}

	return ret;
}

static INT tm_tasklet_qm_schedule_task(RTMP_ADAPTER *pAd, enum task_type type)
{
#if defined(LINUX) && defined(RTMP_PCI_SUPPORT)
	if (IS_PCI_INF(pAd) || IS_PCIE_INF(pAd)) {
		ULONG flags;
		INT ret;
		spin_lock_irqsave(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		if (pAd->dma_stopping || pAd->dma_quarantined) {
			spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
			return NDIS_STATUS_FAILURE;
		}
		ret = tm_tasklet_qm_schedule_taskOwned(pAd, type);
		spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		return ret;
	}
#endif
	return tm_tasklet_qm_schedule_taskOwned(pAd, type);
}

static INT tm_tasklet_hif_schedule_taskOwned(RTMP_ADAPTER *pAd, enum task_type type)
{
	INT ret = NDIS_STATUS_SUCCESS;
	POS_COOKIE obj = (POS_COOKIE)pAd->OS_Cookie;

	switch (type) {
	case CMD_MSG_TASK:

		break;

	case TX_DONE_TASK:
		RTMP_OS_TASKLET_SCHE(&obj->tx_dma_done_task);
		break;

	case RX_DONE_TASK:
		RTMP_OS_TASKLET_SCHE(&obj->rx_done_task[HIF_RX_IDX0]);
		break;

	case RX1_DONE_TASK:
		RTMP_OS_TASKLET_SCHE(&obj->rx_done_task[HIF_RX_IDX1]);
		break;

#ifdef ERR_RECOVERY
	case ERROR_RECOVERY_TASK:
		RTMP_OS_TASKLET_SCHE(&obj->mac_error_recovey_task);
		break;
#endif

#ifdef CONFIG_FWOWN_SUPPORT
	case FW_OWN_TASK:
		RTMP_OS_TASKLET_SCHE(&obj->mt_mac_fw_own_task);
		break;
#endif

#ifdef MULTI_LAYER_INTERRUPT
	case SUBSYS_INT_TASK:
		RTMP_OS_TASKLET_SCHE(&obj->subsys_int_task);
		break;
#endif

	case TR_DONE_TASK:
		RTMP_OS_TASKLET_SCHE(&obj->tr_done_task);
		break;

	default:

		break;
	}

	return ret;
}

static INT tm_tasklet_hif_schedule_task(RTMP_ADAPTER *pAd, enum task_type type)
{
#if defined(LINUX) && defined(RTMP_PCI_SUPPORT)
	if (IS_PCI_INF(pAd) || IS_PCIE_INF(pAd)) {
		ULONG flags;
		INT ret;
		spin_lock_irqsave(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		if (pAd->dma_stopping || pAd->dma_quarantined) {
			spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
			return NDIS_STATUS_FAILURE;
		}
		ret = tm_tasklet_hif_schedule_taskOwned(pAd, type);
		spin_unlock_irqrestore(&((POS_COOKIE)pAd->OS_Cookie)->dma_state_lock, flags);
		return ret;
	}
#endif
	return tm_tasklet_hif_schedule_taskOwned(pAd, type);
}

struct tm_ops tm_tasklet_qm_ops = {
	.init = tm_tasklet_qm_init,
	.exit = tm_tasklet_qm_exit,
	.schedule_task = tm_tasklet_qm_schedule_task,
};

struct tm_ops tm_tasklet_hif_ops = {
	.init = tm_tasklet_hif_init,
	.exit = tm_tasklet_hif_exit,
	.schedule_task = tm_tasklet_hif_schedule_task,
};


INT tm_init(RTMP_ADAPTER *pAd)
{
	RTMP_CHIP_CAP *cap = hc_get_chip_cap(pAd->hdev_ctrl);
	struct tm_ops *qm_ops = NULL, *hif_ops = NULL;
	INT ret;

	if (pAd->tm_qm_ops || pAd->tm_hif_ops || pAd->dma_tasks_retired ||
		RtmpDmaStopping(pAd))
		return NDIS_STATUS_FAILURE;
	if (cap->qm_tm == TASKLET_METHOD)
		qm_ops = &tm_tasklet_qm_ops;
#ifndef CONFIG_PROPRIETARY_DRIVER
	else if (cap->qm_tm == CMWQ_METHOD)
		qm_ops = &tm_wq_qm_ops;
#endif
	if (cap->hif_tm == TASKLET_METHOD)
		hif_ops = &tm_tasklet_hif_ops;
#ifndef CONFIG_PROPRIETARY_DRIVER
	else if (cap->hif_tm == CMWQ_METHOD)
		hif_ops = &tm_wq_hif_ops;
#endif
	if (!qm_ops || !hif_ops)
		return NDIS_STATUS_FAILURE;

	ret = qm_ops->init(pAd);
	if (ret != NDIS_STATUS_SUCCESS)
		return ret;
	pAd->tm_qm_ops = qm_ops;
	ret = hif_ops->init(pAd);
	if (ret != NDIS_STATUS_SUCCESS) {
		if (qm_ops->exit(pAd) == NDIS_STATUS_SUCCESS)
			pAd->tm_qm_ops = NULL;
		return ret;
	}
	pAd->tm_hif_ops = hif_ops;
	return NDIS_STATUS_SUCCESS;
}

INT tm_quiesce(RTMP_ADAPTER *pAd)
{
	struct tm_ops *qm_ops = pAd->tm_qm_ops;
	struct tm_ops *hif_ops = pAd->tm_hif_ops;
	INT ret = NDIS_STATUS_SUCCESS, status;

#ifndef CONFIG_PROPRIETARY_DRIVER
	ret = tm_wq_retirement_check(pAd);
#endif
	if (pAd->dma_tasks_retired)
		return ret;
	if (hif_ops) {
		status = hif_ops->exit(pAd);
		if (ret == NDIS_STATUS_SUCCESS)
			ret = status;
		if (status != NDIS_STATUS_SUCCESS)
			return ret;
	}
	if (qm_ops) {
		status = qm_ops->exit(pAd);
		if (ret == NDIS_STATUS_SUCCESS)
			ret = status;
	}
	if (ret == NDIS_STATUS_SUCCESS)
		pAd->dma_tasks_retired = TRUE;
	/* Do not clear the ops: timers/late callers may still query them.
	 * Their scheduling entries reject the terminal stopping latch.
	 */
	return ret;
}

INT tm_exit(RTMP_ADAPTER *pAd)
{
	struct tm_ops *qm_ops = pAd->tm_qm_ops;
	struct tm_ops *hif_ops = pAd->tm_hif_ops;
	INT ret = NDIS_STATUS_SUCCESS, status;

#ifndef CONFIG_PROPRIETARY_DRIVER
	ret = tm_wq_retirement_check(pAd);
#endif
	if (hif_ops && !pAd->dma_tasks_retired) {
		status = hif_ops->exit(pAd);
		if (ret == NDIS_STATUS_SUCCESS)
			ret = status;
		if (status != NDIS_STATUS_SUCCESS)
			return ret;
	}
	if (qm_ops && !pAd->dma_tasks_retired) {
		status = qm_ops->exit(pAd);
		if (ret == NDIS_STATUS_SUCCESS)
			ret = status;
	}
	if (ret != NDIS_STATUS_SUCCESS)
		return ret;
	pAd->tm_qm_ops = NULL;
	pAd->tm_hif_ops = NULL;
	pAd->dma_tasks_retired = FALSE;
	return ret;
}
