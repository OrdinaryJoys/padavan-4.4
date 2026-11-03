#!/usr/bin/env python3
"""Actual queued SPI admission, callback and removal bodies under inert seams.

No generated probe calls real kernel, device, process, clock or resource APIs.
Stopped waits longjmp to a read-only observation and never resume callbacks.
"""
import hashlib
import re
import spi_queue_harness as queue

SOURCE_PATHS = {**queue.SOURCE_PATHS,
                'header': 'trunk/linux-4.4.x/include/linux/spi/spi.h',
                'controller': 'trunk/linux-4.4.x/drivers/spi/spi-mt7621.c',
                'driver_core': 'trunk/linux-4.4.x/drivers/base/dd.c'}
FUNCTIONS = {**queue.FUNCTIONS,
             'core': (*queue.FUNCTIONS['core'], 'spi_init_queue',
                      'spi_start_queue', '__spi_async', 'spi_async',
                      'spi_async_locked', 'spi_unregister_master'),
             'controller': ('mt7621_spi_remove',),
             'driver_core': ('__device_release_driver',)}
BASELINE_COMMIT = '6e91276a33d1bd83d416fc8253feb01f30677743'
BASELINE_FUNCTIONS = {'__pm_runtime_idle': 'int __pm_runtime_idle(struct device *dev, int rpmflags)\n'
                      '{\n'
                      '\tunsigned long flags;\n'
                      '\tint retval;\n'
                      '\n'
                      '\tif (rpmflags & RPM_GET_PUT) {\n'
                      '\t\tif (!atomic_dec_and_test(&dev->power.usage_count))\n'
                      '\t\t\treturn 0;\n'
                      '\t}\n'
                      '\n'
                      '\tmight_sleep_if(!(rpmflags & RPM_ASYNC) && !dev->power.irq_safe);\n'
                      '\n'
                      '\tspin_lock_irqsave(&dev->power.lock, flags);\n'
                      '\tretval = rpm_idle(dev, rpmflags);\n'
                      '\tspin_unlock_irqrestore(&dev->power.lock, flags);\n'
                      '\n'
                      '\treturn retval;\n'
                      '}',
 '__pm_runtime_suspend': 'int __pm_runtime_suspend(struct device *dev, int rpmflags)\n'
                         '{\n'
                         '\tunsigned long flags;\n'
                         '\tint retval;\n'
                         '\n'
                         '\tif (rpmflags & RPM_GET_PUT) {\n'
                         '\t\tif (!atomic_dec_and_test(&dev->power.usage_count))\n'
                         '\t\t\treturn 0;\n'
                         '\t}\n'
                         '\n'
                         '\tmight_sleep_if(!(rpmflags & RPM_ASYNC) && !dev->power.irq_safe);\n'
                         '\n'
                         '\tspin_lock_irqsave(&dev->power.lock, flags);\n'
                         '\tretval = rpm_suspend(dev, rpmflags);\n'
                         '\tspin_unlock_irqrestore(&dev->power.lock, flags);\n'
                         '\n'
                         '\treturn retval;\n'
                         '}',
 '__pm_runtime_resume': 'int __pm_runtime_resume(struct device *dev, int rpmflags)\n'
                        '{\n'
                        '\tunsigned long flags;\n'
                        '\tint retval;\n'
                        '\n'
                        '\tmight_sleep_if(!(rpmflags & RPM_ASYNC) && !dev->power.irq_safe &&\n'
                        '\t\t\tdev->power.runtime_status != RPM_ACTIVE);\n'
                        '\n'
                        '\tif (rpmflags & RPM_GET_PUT)\n'
                        '\t\tatomic_inc(&dev->power.usage_count);\n'
                        '\n'
                        '\tspin_lock_irqsave(&dev->power.lock, flags);\n'
                        '\tretval = rpm_resume(dev, rpmflags);\n'
                        '\tspin_unlock_irqrestore(&dev->power.lock, flags);\n'
                        '\n'
                        '\treturn retval;\n'
                        '}',
 'pm_runtime_get_sync': 'static inline int pm_runtime_get_sync(struct device *dev)\n'
                        '{\n'
                        '\treturn __pm_runtime_resume(dev, RPM_GET_PUT);\n'
                        '}',
 'pm_runtime_put': 'static inline int pm_runtime_put(struct device *dev)\n'
                   '{\n'
                   '\treturn __pm_runtime_idle(dev, RPM_GET_PUT | RPM_ASYNC);\n'
                   '}',
 'pm_runtime_put_autosuspend': 'static inline int pm_runtime_put_autosuspend(struct device *dev)\n'
                               '{\n'
                               '\treturn __pm_runtime_suspend(dev,\n'
                               '\t    RPM_GET_PUT | RPM_ASYNC | RPM_AUTO);\n'
                               '}',
 'pm_runtime_put_noidle': 'static inline void pm_runtime_put_noidle(struct device *dev)\n'
                          '{\n'
                          '\tatomic_add_unless(&dev->power.usage_count, -1, 0);\n'
                          '}',
 '__spi_unmap_msg': 'static int __spi_unmap_msg(struct spi_master *master, struct spi_message *msg)\n'
                    '{\n'
                    '\tstruct spi_transfer *xfer;\n'
                    '\tstruct device *tx_dev, *rx_dev;\n'
                    '\n'
                    '\tif (!master->cur_msg_mapped || !master->can_dma)\n'
                    '\t\treturn 0;\n'
                    '\n'
                    '\tif (master->dma_tx)\n'
                    '\t\ttx_dev = master->dma_tx->device->dev;\n'
                    '\telse\n'
                    '\t\ttx_dev = master->dev.parent;\n'
                    '\n'
                    '\tif (master->dma_rx)\n'
                    '\t\trx_dev = master->dma_rx->device->dev;\n'
                    '\telse\n'
                    '\t\trx_dev = master->dev.parent;\n'
                    '\n'
                    '\tlist_for_each_entry(xfer, &msg->transfers, transfer_list) {\n'
                    '\t\tif (!master->can_dma(master, msg->spi, xfer))\n'
                    '\t\t\tcontinue;\n'
                    '\n'
                    '\t\tspi_unmap_buf(master, rx_dev, &xfer->rx_sg, DMA_FROM_DEVICE);\n'
                    '\t\tspi_unmap_buf(master, tx_dev, &xfer->tx_sg, DMA_TO_DEVICE);\n'
                    '\t}\n'
                    '\n'
                    '\treturn 0;\n'
                    '}',
 'spi_unmap_msg': 'static inline int spi_unmap_msg(struct spi_master *master,\n'
                  '\t\t\t\tstruct spi_message *msg)\n'
                  '{\n'
                  '\tstruct spi_transfer *xfer;\n'
                  '\n'
                  '\tlist_for_each_entry(xfer, &msg->transfers, transfer_list) {\n'
                  '\t\t/*\n'
                  '\t\t * Restore the original value of tx_buf or rx_buf if they are\n'
                  '\t\t * NULL.\n'
                  '\t\t */\n'
                  '\t\tif (xfer->tx_buf == master->dummy_tx)\n'
                  '\t\t\txfer->tx_buf = NULL;\n'
                  '\t\tif (xfer->rx_buf == master->dummy_rx)\n'
                  '\t\t\txfer->rx_buf = NULL;\n'
                  '\t}\n'
                  '\n'
                  '\treturn __spi_unmap_msg(master, msg);\n'
                  '}',
 '__spi_pump_messages': 'static void __spi_pump_messages(struct spi_master *master, bool in_kthread)\n'
                        '{\n'
                        '\tunsigned long flags;\n'
                        '\tbool was_busy = false;\n'
                        '\tint ret;\n'
                        '\n'
                        '\t/* Lock queue */\n'
                        '\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                        '\n'
                        '\t/* Make sure we are not already running a message */\n'
                        '\tif (master->cur_msg) {\n'
                        '\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\t\treturn;\n'
                        '\t}\n'
                        '\n'
                        '\t/* If another context is idling the device then defer */\n'
                        '\tif (master->idling) {\n'
                        '\t\tqueue_kthread_work(&master->kworker, &master->pump_messages);\n'
                        '\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\t\treturn;\n'
                        '\t}\n'
                        '\n'
                        '\t/* Check if the queue is idle */\n'
                        '\tif (list_empty(&master->queue) || !master->running) {\n'
                        '\t\tif (!master->busy) {\n'
                        '\t\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\t\t\treturn;\n'
                        '\t\t}\n'
                        '\n'
                        '\t\t/* Only do teardown in the thread */\n'
                        '\t\tif (!in_kthread) {\n'
                        '\t\t\tqueue_kthread_work(&master->kworker,\n'
                        '\t\t\t\t\t   &master->pump_messages);\n'
                        '\t\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\t\t\treturn;\n'
                        '\t\t}\n'
                        '\n'
                        '\t\tmaster->busy = false;\n'
                        '\t\tmaster->idling = true;\n'
                        '\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\n'
                        '\t\tkfree(master->dummy_rx);\n'
                        '\t\tmaster->dummy_rx = NULL;\n'
                        '\t\tkfree(master->dummy_tx);\n'
                        '\t\tmaster->dummy_tx = NULL;\n'
                        '\t\tif (master->unprepare_transfer_hardware &&\n'
                        '\t\t    master->unprepare_transfer_hardware(master))\n'
                        '\t\t\tdev_err(&master->dev,\n'
                        '\t\t\t\t"failed to unprepare transfer hardware\\n");\n'
                        '\t\tif (master->auto_runtime_pm) {\n'
                        '\t\t\tpm_runtime_mark_last_busy(master->dev.parent);\n'
                        '\t\t\tpm_runtime_put_autosuspend(master->dev.parent);\n'
                        '\t\t}\n'
                        '\t\ttrace_spi_master_idle(master);\n'
                        '\n'
                        '\t\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                        '\t\tmaster->idling = false;\n'
                        '\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\t\treturn;\n'
                        '\t}\n'
                        '\n'
                        '\t/* Extract head of queue */\n'
                        '\tmaster->cur_msg =\n'
                        '\t\tlist_first_entry(&master->queue, struct spi_message, queue);\n'
                        '\n'
                        '\tlist_del_init(&master->cur_msg->queue);\n'
                        '\tif (master->busy)\n'
                        '\t\twas_busy = true;\n'
                        '\telse\n'
                        '\t\tmaster->busy = true;\n'
                        '\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\n'
                        '\tif (!was_busy && master->auto_runtime_pm) {\n'
                        '\t\tret = pm_runtime_get_sync(master->dev.parent);\n'
                        '\t\tif (ret < 0) {\n'
                        '\t\t\tdev_err(&master->dev, "Failed to power device: %d\\n",\n'
                        '\t\t\t\tret);\n'
                        '\t\t\t/* get_sync increments the usage count even on failure. */\n'
                        '\t\t\tpm_runtime_put_noidle(master->dev.parent);\n'
                        '\t\t\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                        '\t\t\tmaster->busy = false;\n'
                        '\t\t\tmaster->cur_msg_mapped = false;\n'
                        '\t\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\t\t\tmaster->cur_msg->status = ret;\n'
                        '\t\t\tspi_finalize_current_message(master);\n'
                        '\t\t\treturn;\n'
                        '\t\t}\n'
                        '\t}\n'
                        '\n'
                        '\tif (!was_busy)\n'
                        '\t\ttrace_spi_master_busy(master);\n'
                        '\n'
                        '\tif (!was_busy && master->prepare_transfer_hardware) {\n'
                        '\t\tret = master->prepare_transfer_hardware(master);\n'
                        '\t\tif (ret) {\n'
                        '\t\t\tdev_err(&master->dev,\n'
                        '\t\t\t\t"failed to prepare transfer hardware\\n");\n'
                        '\n'
                        '\t\t\tif (master->auto_runtime_pm)\n'
                        '\t\t\t\tpm_runtime_put(master->dev.parent);\n'
                        '\t\t\t/* The next message must retry hardware preparation. */\n'
                        '\t\t\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                        '\t\t\tmaster->busy = false;\n'
                        '\t\t\tmaster->cur_msg_mapped = false;\n'
                        '\t\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                        '\t\t\ttrace_spi_master_idle(master);\n'
                        '\t\t\tmaster->cur_msg->status = ret;\n'
                        '\t\t\tspi_finalize_current_message(master);\n'
                        '\t\t\treturn;\n'
                        '\t\t}\n'
                        '\t}\n'
                        '\n'
                        '\ttrace_spi_message_start(master->cur_msg);\n'
                        '\n'
                        '\tif (master->prepare_message) {\n'
                        '\t\tret = master->prepare_message(master, master->cur_msg);\n'
                        '\t\tif (ret) {\n'
                        '\t\t\tdev_err(&master->dev,\n'
                        '\t\t\t\t"failed to prepare message: %d\\n", ret);\n'
                        '\t\t\tmaster->cur_msg->status = ret;\n'
                        '\t\t\tspi_finalize_current_message(master);\n'
                        '\t\t\treturn;\n'
                        '\t\t}\n'
                        '\t\tmaster->cur_msg_prepared = true;\n'
                        '\t}\n'
                        '\n'
                        '\tret = spi_map_msg(master, master->cur_msg);\n'
                        '\tif (ret) {\n'
                        '\t\tmaster->cur_msg->status = ret;\n'
                        '\t\tspi_finalize_current_message(master);\n'
                        '\t\treturn;\n'
                        '\t}\n'
                        '\n'
                        '\tret = master->transfer_one_message(master, master->cur_msg);\n'
                        '\tif (ret) {\n'
                        '\t\tdev_err(&master->dev,\n'
                        '\t\t\t"failed to transfer one message from queue\\n");\n'
                        '\t\treturn;\n'
                        '\t}\n'
                        '}',
 'spi_finalize_current_message': 'void spi_finalize_current_message(struct spi_master *master)\n'
                                 '{\n'
                                 '\tstruct spi_message *mesg;\n'
                                 '\tunsigned long flags;\n'
                                 '\tint ret;\n'
                                 '\n'
                                 '\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                                 '\tmesg = master->cur_msg;\n'
                                 '\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                                 '\n'
                                 '\tspi_unmap_msg(master, mesg);\n'
                                 '\n'
                                 '\tif (master->cur_msg_prepared && master->unprepare_message) {\n'
                                 '\t\tret = master->unprepare_message(master, mesg);\n'
                                 '\t\tif (ret) {\n'
                                 '\t\t\tdev_err(&master->dev,\n'
                                 '\t\t\t\t"failed to unprepare message: %d\\n", ret);\n'
                                 '\t\t}\n'
                                 '\t}\n'
                                 '\n'
                                 '\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                                 '\tmaster->cur_msg = NULL;\n'
                                 '\tmaster->cur_msg_prepared = false;\n'
                                 '\tqueue_kthread_work(&master->kworker, &master->pump_messages);\n'
                                 '\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                                 '\n'
                                 '\ttrace_spi_message_done(mesg);\n'
                                 '\n'
                                 '\tmesg->state = NULL;\n'
                                 '\tif (mesg->complete)\n'
                                 '\t\tmesg->complete(mesg->context);\n'
                                 '}',
 'spi_stop_queue': 'static int spi_stop_queue(struct spi_master *master)\n'
                   '{\n'
                   '\tunsigned long flags;\n'
                   '\tunsigned limit = 500;\n'
                   '\tint ret = 0;\n'
                   '\n'
                   '\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                   '\n'
                   '\t/*\n'
                   '\t * This is a bit lame, but is optimized for the common execution path.\n'
                   '\t * A wait_queue on the master->busy could be used, but then the common\n'
                   '\t * execution path (pump_messages) would be required to call wake_up or\n'
                   '\t * friends on every SPI message. Do this instead.\n'
                   '\t */\n'
                   '\t/* A synchronous pump may be rolling back with busy already cleared. */\n'
                   '\twhile ((!list_empty(&master->queue) || master->busy ||\n'
                   '\t\tmaster->cur_msg) && limit--) {\n'
                   '\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                   '\t\tusleep_range(10000, 11000);\n'
                   '\t\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                   '\t}\n'
                   '\n'
                   '\tif (!list_empty(&master->queue) || master->busy || master->cur_msg)\n'
                   '\t\tret = -EBUSY;\n'
                   '\telse\n'
                   '\t\tmaster->running = false;\n'
                   '\n'
                   '\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                   '\n'
                   '\tif (ret) {\n'
                   '\t\tdev_warn(&master->dev,\n'
                   '\t\t\t "could not stop message queue\\n");\n'
                   '\t\treturn ret;\n'
                   '\t}\n'
                   '\treturn ret;\n'
                   '}',
 'spi_destroy_queue': 'static int spi_destroy_queue(struct spi_master *master)\n'
                      '{\n'
                      '\tint ret;\n'
                      '\n'
                      '\tret = spi_stop_queue(master);\n'
                      '\n'
                      '\t/*\n'
                      '\t * flush_kthread_worker will block until all work is done.\n'
                      '\t * If the reason that stop_queue timed out is that the work will never\n'
                      '\t * finish, then it does no good to call flush/stop thread, so\n'
                      '\t * return anyway.\n'
                      '\t */\n'
                      '\tif (ret) {\n'
                      '\t\tdev_err(&master->dev, "problem destroying queue\\n");\n'
                      '\t\treturn ret;\n'
                      '\t}\n'
                      '\n'
                      '\tflush_kthread_worker(&master->kworker);\n'
                      '\tkthread_stop(master->kworker_task);\n'
                      '\n'
                      '\treturn 0;\n'
                      '}',
 '__spi_queued_transfer': 'static int __spi_queued_transfer(struct spi_device *spi,\n'
                          '\t\t\t\t struct spi_message *msg,\n'
                          '\t\t\t\t bool need_pump)\n'
                          '{\n'
                          '\tstruct spi_master *master = spi->master;\n'
                          '\tunsigned long flags;\n'
                          '\n'
                          '\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                          '\n'
                          '\tif (!master->running) {\n'
                          '\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                          '\t\treturn -ESHUTDOWN;\n'
                          '\t}\n'
                          '\tmsg->actual_length = 0;\n'
                          '\tmsg->status = -EINPROGRESS;\n'
                          '\n'
                          '\tlist_add_tail(&msg->queue, &master->queue);\n'
                          '\tif (!master->busy && need_pump)\n'
                          '\t\tqueue_kthread_work(&master->kworker, &master->pump_messages);\n'
                          '\n'
                          '\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                          '\treturn 0;\n'
                          '}',
 'spi_queued_transfer': 'static int spi_queued_transfer(struct spi_device *spi, struct spi_message *msg)\n'
                        '{\n'
                        '\treturn __spi_queued_transfer(spi, msg, true);\n'
                        '}',
 'spi_complete': 'static void spi_complete(void *arg)\n{\n\tcomplete(arg);\n}',
 '__spi_sync': 'static int __spi_sync(struct spi_device *spi, struct spi_message *message,\n'
               '\t\t      int bus_locked)\n'
               '{\n'
               '\tDECLARE_COMPLETION_ONSTACK(done);\n'
               '\tint status;\n'
               '\tstruct spi_master *master = spi->master;\n'
               '\tunsigned long flags;\n'
               '\n'
               '\tstatus = __spi_validate(spi, message);\n'
               '\tif (status != 0)\n'
               '\t\treturn status;\n'
               '\n'
               '\tmessage->complete = spi_complete;\n'
               '\tmessage->context = &done;\n'
               '\tmessage->spi = spi;\n'
               '\n'
               '\tSPI_STATISTICS_INCREMENT_FIELD(&master->statistics, spi_sync);\n'
               '\tSPI_STATISTICS_INCREMENT_FIELD(&spi->statistics, spi_sync);\n'
               '\n'
               '\tif (!bus_locked)\n'
               '\t\tmutex_lock(&master->bus_lock_mutex);\n'
               '\n'
               "\t/* If we're not using the legacy transfer method then we will\n"
               '\t * try to transfer in the calling context so special case.\n'
               '\t * This code would be less tricky if we could remove the\n'
               '\t * support for driver implemented message queues.\n'
               '\t */\n'
               '\tif (master->transfer == spi_queued_transfer) {\n'
               '\t\tspin_lock_irqsave(&master->bus_lock_spinlock, flags);\n'
               '\n'
               '\t\ttrace_spi_message_submit(message);\n'
               '\n'
               '\t\tstatus = __spi_queued_transfer(spi, message, false);\n'
               '\n'
               '\t\tspin_unlock_irqrestore(&master->bus_lock_spinlock, flags);\n'
               '\t} else {\n'
               '\t\tstatus = spi_async_locked(spi, message);\n'
               '\t}\n'
               '\n'
               '\tif (!bus_locked)\n'
               '\t\tmutex_unlock(&master->bus_lock_mutex);\n'
               '\n'
               '\tif (status == 0) {\n'
               '\t\t/* Push out the messages in the calling context if we\n'
               '\t\t * can.\n'
               '\t\t */\n'
               '\t\tif (master->transfer == spi_queued_transfer) {\n'
               '\t\t\tSPI_STATISTICS_INCREMENT_FIELD(&master->statistics,\n'
               '\t\t\t\t\t\t       spi_sync_immediate);\n'
               '\t\t\tSPI_STATISTICS_INCREMENT_FIELD(&spi->statistics,\n'
               '\t\t\t\t\t\t       spi_sync_immediate);\n'
               '\t\t\t__spi_pump_messages(master, false);\n'
               '\t\t}\n'
               '\n'
               '\t\twait_for_completion(&done);\n'
               '\t\tstatus = message->status;\n'
               '\t}\n'
               '\tmessage->context = NULL;\n'
               '\treturn status;\n'
               '}',
 'spi_init_queue': 'static int spi_init_queue(struct spi_master *master)\n'
                   '{\n'
                   '\tstruct sched_param param = { .sched_priority = MAX_RT_PRIO - 1 };\n'
                   '\n'
                   '\tmaster->running = false;\n'
                   '\tmaster->busy = false;\n'
                   '\n'
                   '\tinit_kthread_worker(&master->kworker);\n'
                   '\tmaster->kworker_task = kthread_run(kthread_worker_fn,\n'
                   '\t\t\t\t\t   &master->kworker, "%s",\n'
                   '\t\t\t\t\t   dev_name(&master->dev));\n'
                   '\tif (IS_ERR(master->kworker_task)) {\n'
                   '\t\tdev_err(&master->dev, "failed to create message pump task\\n");\n'
                   '\t\treturn PTR_ERR(master->kworker_task);\n'
                   '\t}\n'
                   '\tinit_kthread_work(&master->pump_messages, spi_pump_messages);\n'
                   '\n'
                   '\t/*\n'
                   '\t * Master config will indicate if this controller should run the\n'
                   '\t * message pump with high (realtime) priority to reduce the transfer\n'
                   '\t * latency on the bus by minimising the delay between a transfer\n'
                   '\t * request and the scheduling of the message pump thread. Without this\n'
                   '\t * setting the message pump thread will remain at default priority.\n'
                   '\t */\n'
                   '\tif (master->rt) {\n'
                   '\t\tdev_info(&master->dev,\n'
                   '\t\t\t"will run message pump with realtime priority\\n");\n'
                   '\t\tsched_setscheduler(master->kworker_task, SCHED_FIFO, &param);\n'
                   '\t}\n'
                   '\n'
                   '\treturn 0;\n'
                   '}',
 'spi_start_queue': 'static int spi_start_queue(struct spi_master *master)\n'
                    '{\n'
                    '\tunsigned long flags;\n'
                    '\n'
                    '\tspin_lock_irqsave(&master->queue_lock, flags);\n'
                    '\n'
                    '\tif (master->running || master->busy) {\n'
                    '\t\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                    '\t\treturn -EBUSY;\n'
                    '\t}\n'
                    '\n'
                    '\tmaster->running = true;\n'
                    '\tmaster->cur_msg = NULL;\n'
                    '\tspin_unlock_irqrestore(&master->queue_lock, flags);\n'
                    '\n'
                    '\tqueue_kthread_work(&master->kworker, &master->pump_messages);\n'
                    '\n'
                    '\treturn 0;\n'
                    '}',
 '__spi_async': 'static int __spi_async(struct spi_device *spi, struct spi_message *message)\n'
                '{\n'
                '\tstruct spi_master *master = spi->master;\n'
                '\n'
                '\tmessage->spi = spi;\n'
                '\n'
                '\tSPI_STATISTICS_INCREMENT_FIELD(&master->statistics, spi_async);\n'
                '\tSPI_STATISTICS_INCREMENT_FIELD(&spi->statistics, spi_async);\n'
                '\n'
                '\ttrace_spi_message_submit(message);\n'
                '\n'
                '\treturn master->transfer(spi, message);\n'
                '}',
 'spi_async': 'int spi_async(struct spi_device *spi, struct spi_message *message)\n'
              '{\n'
              '\tstruct spi_master *master = spi->master;\n'
              '\tint ret;\n'
              '\tunsigned long flags;\n'
              '\n'
              '\tret = __spi_validate(spi, message);\n'
              '\tif (ret != 0)\n'
              '\t\treturn ret;\n'
              '\n'
              '\tspin_lock_irqsave(&master->bus_lock_spinlock, flags);\n'
              '\n'
              '\tif (master->bus_lock_flag)\n'
              '\t\tret = -EBUSY;\n'
              '\telse\n'
              '\t\tret = __spi_async(spi, message);\n'
              '\n'
              '\tspin_unlock_irqrestore(&master->bus_lock_spinlock, flags);\n'
              '\n'
              '\treturn ret;\n'
              '}',
 'spi_async_locked': 'int spi_async_locked(struct spi_device *spi, struct spi_message *message)\n'
                     '{\n'
                     '\tstruct spi_master *master = spi->master;\n'
                     '\tint ret;\n'
                     '\tunsigned long flags;\n'
                     '\n'
                     '\tret = __spi_validate(spi, message);\n'
                     '\tif (ret != 0)\n'
                     '\t\treturn ret;\n'
                     '\n'
                     '\tspin_lock_irqsave(&master->bus_lock_spinlock, flags);\n'
                     '\n'
                     '\tret = __spi_async(spi, message);\n'
                     '\n'
                     '\tspin_unlock_irqrestore(&master->bus_lock_spinlock, flags);\n'
                     '\n'
                     '\treturn ret;\n'
                     '\n'
                     '}',
 'spi_unregister_master': 'void spi_unregister_master(struct spi_master *master)\n'
                          '{\n'
                          '\tint dummy;\n'
                          '\n'
                          '\tif (master->queued) {\n'
                          '\t\tif (spi_destroy_queue(master))\n'
                          '\t\t\tdev_err(&master->dev, "queue remove failed\\n");\n'
                          '\t}\n'
                          '\n'
                          '\tmutex_lock(&board_lock);\n'
                          '\tlist_del(&master->list);\n'
                          '\tmutex_unlock(&board_lock);\n'
                          '\n'
                          '\tdummy = device_for_each_child(&master->dev, NULL, __unregister);\n'
                          '\tdevice_unregister(&master->dev);\n'
                          '}',
 'mt7621_spi_remove': 'static int mt7621_spi_remove(struct platform_device *pdev)\n'
                      '{\n'
                      '\tstruct spi_master *master;\n'
                      '\tstruct mt7621_spi *ms;\n'
                      '\tstruct clk *hclk;\n'
                      '\n'
                      '\tmaster = dev_get_drvdata(&pdev->dev);\n'
                      '\tms = spi_master_get_devdata(master);\n'
                      '\n'
                      '\thclk = ms->hclk;\n'
                      '\tspi_unregister_master(master);\n'
                      '\tdev_set_drvdata(&pdev->dev, NULL);\n'
                      '\tclk_disable_unprepare(hclk);\n'
                      '\n'
                      '\treturn 0;\n'
                      '}',
 '__device_release_driver': 'static void __device_release_driver(struct device *dev)\n'
                            '{\n'
                            '\tstruct device_driver *drv;\n'
                            '\n'
                            '\tdrv = dev->driver;\n'
                            '\tif (drv) {\n'
                            '\t\tif (driver_allows_async_probing(drv))\n'
                            '\t\t\tasync_synchronize_full();\n'
                            '\n'
                            '\t\tpm_runtime_get_sync(dev);\n'
                            '\n'
                            '\t\tdriver_sysfs_remove(dev);\n'
                            '\n'
                            '\t\tif (dev->bus)\n'
                            '\t\t\tblocking_notifier_call_chain(&dev->bus->p->bus_notifier,\n'
                            '\t\t\t\t\t\t     BUS_NOTIFY_UNBIND_DRIVER,\n'
                            '\t\t\t\t\t\t     dev);\n'
                            '\n'
                            '\t\tpm_runtime_put_sync(dev);\n'
                            '\n'
                            '\t\tif (dev->bus && dev->bus->remove)\n'
                            '\t\t\tdev->bus->remove(dev);\n'
                            '\t\telse if (drv->remove)\n'
                            '\t\t\tdrv->remove(dev);\n'
                            '\t\tdevres_release_all(dev);\n'
                            '\t\tdev->driver = NULL;\n'
                            '\t\tdev_set_drvdata(dev, NULL);\n'
                            '\t\tif (dev->pm_domain && dev->pm_domain->dismiss)\n'
                            '\t\t\tdev->pm_domain->dismiss(dev);\n'
                            '\n'
                            '\t\tklist_remove(&dev->p->knode_driver);\n'
                            '\t\tdevice_pm_check_callbacks(dev);\n'
                            '\t\tif (dev->bus)\n'
                            '\t\t\tblocking_notifier_call_chain(&dev->bus->p->bus_notifier,\n'
                            '\t\t\t\t\t\t     BUS_NOTIFY_UNBOUND_DRIVER,\n'
                            '\t\t\t\t\t\t     dev);\n'
                            '\n'
                            '\t}\n'
                            '}'}
BASELINE_HASHES = {'__pm_runtime_idle': '69300cca88f5920371a9a1b2db4bf72118383f23357795553225581341d1acf0',
 '__pm_runtime_suspend': '9c4a4a9535bbf175f0f58f9b1925a49f199092cb9fc1b596ac0d6ce14fb2ed00',
 '__pm_runtime_resume': '080402cb90ae588f878aeac63736e180234e7a28e92fe80cc6224ce5097b113a',
 'pm_runtime_get_sync': '910e9c4a6aee0bb7d1f13df3f4266c18f68bda268b59f86f86d009300d0a54a0',
 'pm_runtime_put': '476d677071b9a848bd943ba5fc244f3c19fa058376bbec6dab79ed69e4659d49',
 'pm_runtime_put_autosuspend': '78cd3d6686d91c5eb4a44c3b27b44d910c3930949d085309e98684ce305bd7a8',
 'pm_runtime_put_noidle': '021f73d9483c1b17bf226402a2cac8f92177f9d84e167a2d6f317b6f4768f261',
 '__spi_unmap_msg': 'ca3576cb4fff37ab136dafc9050824970a4d61aec82c1f392cc0910aa991cb0f',
 'spi_unmap_msg': '74edc68f6e2d6194acdc96c2b66ffda40721de2ae2aac894731b76cdc8e23802',
 '__spi_pump_messages': '89891b70c11e0cf07537015dbce8b216e5bb5c3d4ac1e30ac22c141ad8b1b037',
 'spi_finalize_current_message': '0c0435f2b0694152dab661874024eb49752bdf6d488f761500a890b30a1a65d9',
 'spi_stop_queue': '58b073ca4e765b6c4cc9e8ab63a02beed7e4433fff3486300a8d4b043961a7dc',
 'spi_destroy_queue': 'd45ba960e85ad855794d2fa01e3d4a0d3ffec44f167ee2b8e9b099f731348c14',
 '__spi_queued_transfer': '06d71ffa9ee8519c96ecdfccf841fa5b77e7c1fad2d46f8e95952e1022d83950',
 'spi_queued_transfer': '8c67964f4bc3bb79566d337bb6e1856ca2eb1561df80943ba88eb71af608b4f9',
 'spi_complete': '3792e96dc2f1cf239cfe98eb9c73b5191e0521712bb2c4d445f753488ec27f99',
 '__spi_sync': 'd28a65ecb4f673ba6cdaa776477a864581a418756a2cd121ad6aa106251528b4',
 'spi_init_queue': '89cd49eb7b8f2b3b0e9ccdf8528d52322b96867880d4f1f5996078e109d801d3',
 'spi_start_queue': 'bc74d998e1e1fa125fb0b2dcf6b6282739c69d15629c57d016be71b35721432d',
 '__spi_async': '6b4532350cba59ed45c7dc356936736d3cc5989d434768495b8cde00162c60e4',
 'spi_async': '6945b885f7cc2dabd8b1edc157cf9619dfb1821eee3f2d3f5cf17507bbb2d6a1',
 'spi_async_locked': '14c922e11d752bc40a2997a473c77ecd8121a63f749708075da8d24cdcd2fbac',
 'spi_unregister_master': 'a06212e5e8192268bec40b32f72f36ce0ae4c3403a9614d398b15a5702a5f292',
 'mt7621_spi_remove': '8892ce893731be12eb7ab9e15c35e7b700fc7f2a25156bfb7580071e6401a099',
 '__device_release_driver': 'f275ec268059c2d3fcbdc849316db5e97c90b4d85a21b3ad11bb7d52b4432034'}


def actual_functions(texts):
    out = queue.actual_functions({key:texts[key] for key in queue.SOURCE_PATHS})
    for key in ('core','controller','driver_core'):
        for name in FUNCTIONS[key]:
            if name not in out:
                out[name] = {'source_key':key,'body':queue.extract(texts[key],name)}
    return out


EXT_TYPES = r'''
struct device;
struct device_driver {int (*remove)(struct device*);};
struct device_private {int knode_driver;};
struct dev_pm_domain {void (*dismiss)(struct device*);};
struct bus_private {int bus_notifier;};
struct bus_type {struct bus_private *p;int (*remove)(struct device*);};
'''
EXT_GLOBALS = r'''
struct clk {int live;};
struct mt7621_spi {struct clk *hclk;};
struct platform_device {struct device dev;};
struct sched_param {int sched_priority;};
static struct platform_device pdev;
static struct device_driver pdriver;
static struct device_private pprivate;
static struct mt7621_spi ms;
static struct clk hclk;
static struct model_lock board_lock;
static int outer_returned,child_unregister,master_unregister,clock_off,devres;
static int unsafe_release,after_release,freed,hook_kind,hook_fired,stop_observed;
static int stop_after=520,drain_on_sleep,finish_on_sleep,late_admission,late_result=999;
static int callback_live,callback_overlap,callback_reentry,callback_observe,validate_calls,retire_on_sleep,work_pending;
static int init_fail,init_result,queue_result;
static void outer_remove(void);
int spi_async(struct spi_device*,struct spi_message*);
int spi_async_locked(struct spi_device*,struct spi_message*);
static void __device_release_driver(struct device*);
static void check_release(void){if(master.cur_msg||master.busy||master.idling||master.queue_users||master.queue_callbacks||!list_empty(&master.queue)||!stops||callback_live||((hook_kind==1||hook_kind==2)&&hook_fired))unsafe_release++;}
static void model_msleep(unsigned ms){if(ms!=20)abort();if(sleeps>=stop_after||!sleeps){stop_observed=1;longjmp(wait_stop,1);}}
#define msleep model_msleep
#define dev_info(...) ((void)0)
#define list_del list_del_init
#define MAX_RT_PRIO 100
#define SCHED_FIFO 1
#define IS_ERR(p) ((long)(p)<0)
#define PTR_ERR(p) ((long)(p))
static int task;
static void init_kthread_worker(struct kthread_worker*w){(void)w;}
static void init_kthread_work(struct kthread_work*w,void(*fn)(struct kthread_work*)){(void)w;(void)fn;}
static int kthread_worker_fn(void*p){(void)p;return 0;}
static void *model_kthread_run(void){return init_fail?(void*)-12:&task;}
#define kthread_run(fn,data,fmt,name) model_kthread_run()
static int sched_setscheduler(void*t,int p,struct sched_param*s){(void)t;(void)p;(void)s;return 0;}
static const char *dev_name(struct device*d){(void)d;return "inert-controller";}
static void spi_pump_messages(struct kthread_work*w){(void)w;__spi_pump_messages(&master,true);}
static void *dev_get_drvdata(struct device*d){return d->driver_data;}
static void *spi_master_get_devdata(struct spi_master*m){if(m!=&master)abort();return &ms;}
static void dev_set_drvdata(struct device*d,void*p){d->driver_data=p;}
static void clk_disable_unprepare(struct clk*c){if(c!=&hclk)abort();check_release();clock_off++;}
static int __unregister(struct device*d,void*p){(void)d;(void)p;return 0;}
static int device_for_each_child(struct device*d,void*p,int(*fn)(struct device*,void*)){if(d!=&master.dev||p||fn!=__unregister)abort();check_release();child_unregister++;return 0;}
static void device_unregister(struct device*d){if(d!=&master.dev)abort();check_release();master_unregister++;}
static int driver_allows_async_probing(struct device_driver*d){(void)d;return 0;}
static void async_synchronize_full(void){abort();}
static void driver_sysfs_remove(struct device*d){(void)d;}
static void pm_runtime_put_sync(struct device*d){if(d!=&pdev.dev)abort();d->power.usage_count.count--;}
static void devres_release_all(struct device*d){if(d!=&pdev.dev)abort();check_release();devres++;freed=1;}
static void klist_remove(int*p){if(p!=&pprivate.knode_driver)abort();}
static void device_pm_check_callbacks(struct device*d){(void)d;}
#define BUS_NOTIFY_UNBIND_DRIVER 1
#define BUS_NOTIFY_UNBOUND_DRIVER 2
static void blocking_notifier_call_chain(int*p,int e,struct device*d){(void)p;(void)e;(void)d;}
'''


def prefix():
    text = queue.PREFIX
    old = 'struct device {struct device *parent;struct {atomic_t usage_count;struct model_lock lock;int irq_safe,runtime_status;} power;};'
    new = EXT_TYPES + old.replace('struct device *parent;',
          'struct device *parent;struct device_driver *driver;struct device_private *p;struct bus_type *bus;struct dev_pm_domain *pm_domain;void *driver_data;')
    if text.count(old) != 1:raise ValueError('Lifecycle device model anchor changed')
    text = text.replace(old,new).replace('struct list_head queue;struct spi_message*cur_msg;',
                                        'struct list_head queue,list;struct spi_message*cur_msg;')
    text = text.replace('int sync,immediate;', 'int sync,immediate,spi_async;').replace('bool busy,idling,running,queued,queue_dead,','bool busy,idling,running,queued,queue_dead,bus_lock_flag,rt,')
    text = text.replace('static void event(char c)', EXT_GLOBALS+'\nstatic void event(char c)',1)
    old = queue.extract(text,'spi_async_locked')
    text = text.replace(old,'')
    old = queue.extract(text,'model_lock')
    text = text.replace(old,'static void model_lock(struct model_lock*l){if(freed&&(l==&master.queue_lock||l==&master.bus_lock_spinlock||l==&master.bus_lock_mutex))after_release++;if(l->depth)locks_bad++;l->depth++;}')
    old = queue.extract(text,'model_unlock')
    text = text.replace(old,r'''static void model_unlock(struct model_lock*l){if(l->depth!=1)locks_bad++;if(hook_kind==2&&l==&master.bus_lock_spinlock&&!hook_fired&&!list_empty(&master.queue)){hook_fired=1;outer_remove();longjmp(wait_stop,2);}l->depth--;if(hook_kind==1&&l==&master.queue_lock&&!hook_fired&&!list_empty(&master.queue)){hook_fired=1;outer_remove();longjmp(wait_stop,2);}}''')
    old = queue.extract(text,'pm_entry')
    text = text.replace(old,'static void pm_entry(struct device*d){if((d!=&parent&&d!=&pdev.dev)||master.queue_lock.depth)locks_bad++;}')
    old = queue.extract(text,'usleep_range')
    text = text.replace(old,r'''static void usleep_range(unsigned a,unsigned b){if(a!=10000||b!=11000||master.queue_lock.depth)abort();sleeps++;if(retire_on_sleep==1)master.idling=false;else if(retire_on_sleep==2)master.queue_users=0;else if(retire_on_sleep==3)master.queue_callbacks=0;retire_on_sleep=0;if(late_admission){late_admission=0;late_result=spi_async(&spi,&m2);}if(finish_on_sleep){finish_on_sleep=0;master.cur_msg->status=0;spi_finalize_current_message(&master);}if(drain_on_sleep)__spi_pump_messages(&master,true);if(sleeps>=stop_after){stop_observed=1;longjmp(wait_stop,1);}}''')
    old = queue.extract(text,'queue_kthread_work')
    text = text.replace(old,'static void queue_kthread_work(struct kthread_worker*w,struct kthread_work*k){if(w!=&master.kworker||k!=&master.pump_messages)abort();work_queued++;work_pending=1;}')
    old = queue.extract(text,'__spi_validate')
    text = text.replace(old,'static int __spi_validate(struct spi_device*s,struct spi_message*q){if(s!=&spi||!q)abort();validate_calls++;return validate_error;}')
    old = queue.extract(text,'async_complete')
    text = text.replace(old,r'''static void async_complete(void*context){struct spi_message*q=context;int before;if(q!=&m1&&q!=&m2)abort();if(master.cur_msg||master.queue_lock.depth)completion_bad++;if(callback_live)callback_overlap++;callback_live++;completed++;completion_order=completion_order*10+q->id;if(callback_observe&&q==&m1){callback_observe=0;outer_remove();}if(callback_reentry==1&&q==&m1){callback_reentry=0;queue_result=spi_async(&spi,&m2);before=transfers;__spi_pump_messages(&master,false);if(transfers!=before)callback_overlap++;}else if(callback_reentry==2&&q==&m1){callback_reentry=0;queue_result=spi_async(&spi,&m2);before=transfers;if(work_pending){work_pending=0;__spi_pump_messages(&master,true);}if(transfers!=before)callback_overlap++;}callback_live--;}''')
    return text


DRIVER = r'''
static int model_platform_remove(struct device*d){return mt7621_spi_remove((struct platform_device*)d);}
static void outer_remove(void){__device_release_driver(&pdev.dev);outer_returned++;}
static void init_message(struct spi_message*q,int id){memset(q,0,sizeof(*q));INIT_LIST_HEAD(&q->queue);INIT_LIST_HEAD(&q->transfers);INIT_LIST_HEAD(&q->xfer.transfer_list);list_add_tail(&q->xfer.transfer_list,&q->transfers);q->id=id;q->state=q;q->spi=&spi;q->context=q;q->complete=async_complete;}
static void setup(void){memset(&master,0,sizeof(master));memset(&parent,0,sizeof(parent));memset(&spi,0,sizeof(spi));memset(&pdev,0,sizeof(pdev));INIT_LIST_HEAD(&master.queue);INIT_LIST_HEAD(&master.list);master.dev.parent=&parent;parent.power.runtime_status=1;master.running=true;master.queued=true;master.transfer=spi_queued_transfer;master.transfer_one_message=transfer_msg;spi.master=&master;init_message(&m1,1);init_message(&m2,2);pdev.dev.driver=&pdriver;pdriver.remove=model_platform_remove;pdev.dev.p=&pprivate;pdev.dev.driver_data=&master;ms.hclk=&hclk;}
int main(int argc,char**argv){const char*name;int jumped;if(argc!=2)return 2;name=argv[1];setup();jumped=setjmp(wait_stop);if(!jumped){
 if(!strcmp(name,"remove-idle"))outer_remove();
 else if(!strcmp(name,"remove-stuck-current")){master.cur_msg=&m1;master.busy=true;outer_remove();}
 else if(!strcmp(name,"remove-current-finishes")){master.cur_msg=&m1;master.busy=true;finish_on_sleep=1;drain_on_sleep=1;outer_remove();}
 else if(!strcmp(name,"remove-owned-idling")){master.idling=true;outer_remove();}
 else if(!strcmp(name,"remove-owned-user")){master.queue_users=1;outer_remove();}
 else if(!strcmp(name,"remove-owned-callback")){master.queue_callbacks=1;outer_remove();}
 else if(!strcmp(name,"remove-idling-retires")){master.idling=true;retire_on_sleep=1;outer_remove();}
 else if(!strcmp(name,"remove-user-retires")){master.queue_users=1;retire_on_sleep=2;outer_remove();}
 else if(!strcmp(name,"remove-callback-retires")){master.queue_callbacks=1;retire_on_sleep=3;outer_remove();}
 else if(!strcmp(name,"remove-drain-existing")){result=spi_async(&spi,&m1);drain_on_sleep=1;outer_remove();}
 else if(!strcmp(name,"remove-late-admission")){result=spi_async(&spi,&m1);drain_on_sleep=1;late_admission=1;outer_remove();}
 else if(!strcmp(name,"sync-paused-before-pump")){hook_kind=1;drain_on_sleep=1;result=__spi_sync(&spi,&m1,0);}
 else if(!strcmp(name,"async-paused-before-unlock")){hook_kind=2;drain_on_sleep=1;result=spi_async(&spi,&m1);}
 else if(!strcmp(name,"async-locked-paused-before-unlock")){hook_kind=2;drain_on_sleep=1;result=spi_async_locked(&spi,&m1);}
 else if(!strcmp(name,"callback-remove-interleave")){callback_observe=1;drain_on_sleep=1;result=spi_async(&spi,&m1);__spi_pump_messages(&master,true);}
 else if(!strcmp(name,"callback-next-transfer")){callback_reentry=1;result=spi_async(&spi,&m1);__spi_pump_messages(&master,true);while(!list_empty(&master.queue)||master.busy)__spi_pump_messages(&master,true);}
 else if(!strcmp(name,"callback-worker-wakeup")){int budget=8;callback_reentry=2;result=spi_async(&spi,&m1);while(work_pending&&budget--){work_pending=0;__spi_pump_messages(&master,true);}}
 else if(!strcmp(name,"preentered-enqueue-closed")){master.queue_users=1;master.queue_dead=true;result=__spi_queued_transfer(&spi,&m1,false);master.queue_users--;}
 else if(!strcmp(name,"sync-closed")){master.queue_dead=true;result=__spi_sync(&spi,&m1,0);}
 else if(!strcmp(name,"async-closed")){master.queue_dead=true;result=spi_async(&spi,&m1);}
 else if(!strcmp(name,"async-locked-closed")){master.queue_dead=true;result=spi_async_locked(&spi,&m1);}
 else if(!strcmp(name,"validate-sync")){validate_error=-EINVAL;result=__spi_sync(&spi,&m1,0);}
 else if(!strcmp(name,"validate-async")){validate_error=-EINVAL;result=spi_async(&spi,&m1);}
 else if(!strcmp(name,"validate-async-locked")){validate_error=-EINVAL;result=spi_async_locked(&spi,&m1);}
 else if(!strcmp(name,"bus-locked-async")){master.bus_lock_flag=true;result=spi_async(&spi,&m1);}
 else if(!strcmp(name,"stopped-sync")){master.running=false;result=__spi_sync(&spi,&m1,0);}
 else if(!strcmp(name,"resume-closed")){master.queue_dead=true;master.running=false;result=spi_start_queue(&master);}
 else if(!strcmp(name,"init-clears")){master.queue_dead=true;master.queue_users=9;master.queue_callbacks=8;result=spi_init_queue(&master);}
 else if(!strcmp(name,"init-fails")){init_fail=1;result=spi_init_queue(&master);}
 else return 3;
 }
printf("{\"case\":\"%s\",\"result\":%d,\"jumped\":%d,\"blocked\":%d,\"outer_returned\":%d,\"child_unregister\":%d,\"master_unregister\":%d,\"clock_off\":%d,\"devres\":%d,\"unsafe_release\":%d,\"after_release\":%d,\"queue_dead\":%d,\"users\":%u,\"callbacks\":%u,\"idling\":%d,\"cur_msg\":%d,\"busy\":%d,\"sleeps\":%d,\"flush\":%d,\"stop\":%d,\"completed\":%d,\"transfers\":%d,\"late_result\":%d,\"queue_result\":%d,\"callback_overlap\":%d,\"completion_order\":%d,\"transfer_order\":%d,\"lock_errors\":%d,\"validate_calls\":%d,\"queue_pending\":%d,\"work_pending\":%d}\n",name,result,jumped,stop_observed,outer_returned,child_unregister,master_unregister,clock_off,devres,unsafe_release,after_release,master.queue_dead,master.queue_users,master.queue_callbacks,master.idling,master.cur_msg!=NULL,master.busy,sleeps,flushes,stops,completed,transfers,late_result,queue_result,callback_overlap,completion_order,transfer_order,locks_bad,validate_calls,!list_empty(&master.queue),work_pending);return 0;}
'''
CASE_NAMES = ('remove-idle','remove-stuck-current','remove-current-finishes',
              'remove-owned-idling','remove-owned-user','remove-owned-callback',
              'remove-idling-retires','remove-user-retires','remove-callback-retires',
              'remove-drain-existing','remove-late-admission',
              'sync-paused-before-pump','async-paused-before-unlock',
              'async-locked-paused-before-unlock',
              'callback-remove-interleave','callback-next-transfer','callback-worker-wakeup',
              'preentered-enqueue-closed',
              'sync-closed','async-closed','async-locked-closed','validate-sync',
              'validate-async','validate-async-locked','bus-locked-async',
              'stopped-sync','resume-closed','init-clears','init-fails')


def generate_source(texts, fixture_root=None, owner_uid=0, baseline=False):
    if set(texts) != set(SOURCE_PATHS):raise ValueError('Exact lifecycle source manifest required')
    if type(baseline) is not bool or type(owner_uid) is not int or owner_uid<0:raise ValueError('Typed lifecycle profile required')
    fields = re.search(r'\tbool\t+running;\n\tbool\t+queue_dead;\n'
                       r'\tunsigned int\t+queue_users;\n'
                       r'\tunsigned int\t+queue_callbacks;', texts['header'])
    if fields is None:raise ValueError('Actual ownership field declarations differ')
    actual=actual_functions(texts)
    bodies={name:entry['body'] for name,entry in actual.items()}
    if baseline:
        if set(BASELINE_FUNCTIONS)!=set(BASELINE_HASHES):raise ValueError('Unpinned lifecycle baseline')
        for name,body in BASELINE_FUNCTIONS.items():
            if hashlib.sha256(body.encode()).hexdigest()!=BASELINE_HASHES[name]:raise ValueError('Changed lifecycle baseline: '+name)
        bodies=dict(BASELINE_FUNCTIONS)
    order=[name for names in FUNCTIONS.values() for name in names]
    # __spi_sync references async_locked, and async entry references __spi_async.
    model = prefix()
    needle = ('bool busy,idling,running,queued,queue_dead,bus_lock_flag,rt,'
              'cur_msg_prepared,cur_msg_mapped,auto_runtime_pm;unsigned queue_users,queue_callbacks;')
    if model.count(needle)!=1:raise ValueError('Ownership model field anchor changed')
    model=model.replace(needle, 'bool busy,idling,queued,bus_lock_flag,rt,'
                        'cur_msg_prepared,cur_msg_mapped,auto_runtime_pm;'+fields.group())
    return model+'\n'+queue.production_fragments(texts)+'\n'+'\n\n'.join(bodies[name] for name in order if name in bodies)+'\n'+DRIVER

CURRENT_CASES = (('remove-idle',
  {'case': 'remove-idle',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-stuck-current',
  {'case': 'remove-stuck-current',
   'result': 0,
   'jumped': 1,
   'blocked': 1,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 1,
   'busy': 1,
   'sleeps': 520,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-current-finishes',
  {'case': 'remove-current-finishes',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 1,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 1}),
 ('remove-owned-idling',
  {'case': 'remove-owned-idling',
   'result': 0,
   'jumped': 1,
   'blocked': 1,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 1,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 520,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-owned-user',
  {'case': 'remove-owned-user',
   'result': 0,
   'jumped': 1,
   'blocked': 1,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 1,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 520,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-owned-callback',
  {'case': 'remove-owned-callback',
   'result': 0,
   'jumped': 1,
   'blocked': 1,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 1,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 520,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-idling-retires',
  {'case': 'remove-idling-retires',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 1,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-user-retires',
  {'case': 'remove-user-retires',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 1,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-callback-retires',
  {'case': 'remove-callback-retires',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 1,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-drain-existing',
  {'case': 'remove-drain-existing',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 2,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('remove-late-admission',
  {'case': 'remove-late-admission',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 2,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 1,
   'late_result': -108,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('sync-paused-before-pump',
  {'case': 'sync-paused-before-pump',
   'result': 0,
   'jumped': 1,
   'blocked': 1,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 1,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 520,
   'flush': 0,
   'stop': 0,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('async-paused-before-unlock',
  {'case': 'async-paused-before-unlock',
   'result': 0,
   'jumped': 1,
   'blocked': 1,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 1,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 520,
   'flush': 0,
   'stop': 0,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('async-locked-paused-before-unlock',
  {'case': 'async-locked-paused-before-unlock',
   'result': 0,
   'jumped': 1,
   'blocked': 1,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 1,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 520,
   'flush': 0,
   'stop': 0,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('callback-remove-interleave',
  {'case': 'callback-remove-interleave',
   'result': 0,
   'jumped': 1,
   'blocked': 1,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 1,
   'idling': 0,
   'cur_msg': 0,
   'busy': 1,
   'sleeps': 520,
   'flush': 0,
   'stop': 0,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('callback-next-transfer',
  {'case': 'callback-next-transfer',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 2,
   'transfers': 2,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 12,
   'transfer_order': 12,
   'lock_errors': 0,
   'validate_calls': 2,
   'queue_pending': 0,
   'work_pending': 1}),
 ('callback-worker-wakeup',
  {'case': 'callback-worker-wakeup',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 2,
   'transfers': 2,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 12,
   'transfer_order': 12,
   'lock_errors': 0,
   'validate_calls': 2,
   'queue_pending': 0,
   'work_pending': 0}),
 ('preentered-enqueue-closed',
  {'case': 'preentered-enqueue-closed',
   'result': -108,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('sync-closed',
  {'case': 'sync-closed',
   'result': -108,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('async-closed',
  {'case': 'async-closed',
   'result': -108,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('async-locked-closed',
  {'case': 'async-locked-closed',
   'result': -108,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('validate-sync',
  {'case': 'validate-sync',
   'result': -22,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('validate-async',
  {'case': 'validate-async',
   'result': -22,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('validate-async-locked',
  {'case': 'validate-async-locked',
   'result': -22,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('bus-locked-async',
  {'case': 'bus-locked-async',
   'result': -16,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('stopped-sync',
  {'case': 'stopped-sync',
   'result': -108,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('resume-closed',
  {'case': 'resume-closed',
   'result': -108,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('init-clears',
  {'case': 'init-clears',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('init-fails',
  {'case': 'init-fails',
   'result': -12,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}))
BASELINE_CASES = (('remove-idle',
  {'case': 'remove-idle',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-stuck-current',
  {'case': 'remove-stuck-current',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 1,
   'busy': 1,
   'sleeps': 500,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-current-finishes',
  {'case': 'remove-current-finishes',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 1,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 1}),
 ('remove-owned-idling',
  {'case': 'remove-owned-idling',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 1,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-owned-user',
  {'case': 'remove-owned-user',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 1,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-owned-callback',
  {'case': 'remove-owned-callback',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 1,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-idling-retires',
  {'case': 'remove-idling-retires',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 1,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-user-retires',
  {'case': 'remove-user-retires',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 1,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-callback-retires',
  {'case': 'remove-callback-retires',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 1,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 1,
   'stop': 1,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('remove-drain-existing',
  {'case': 'remove-drain-existing',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 2,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('remove-late-admission',
  {'case': 'remove-late-admission',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 3,
   'flush': 1,
   'stop': 1,
   'completed': 2,
   'transfers': 2,
   'late_result': 0,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 12,
   'transfer_order': 12,
   'lock_errors': 0,
   'validate_calls': 2,
   'queue_pending': 0,
   'work_pending': 1}),
 ('sync-paused-before-pump',
  {'case': 'sync-paused-before-pump',
   'result': 0,
   'jumped': 2,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 2,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('async-paused-before-unlock',
  {'case': 'async-paused-before-unlock',
   'result': 0,
   'jumped': 2,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 2,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('async-locked-paused-before-unlock',
  {'case': 'async-locked-paused-before-unlock',
   'result': 0,
   'jumped': 2,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 2,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('callback-remove-interleave',
  {'case': 'callback-remove-interleave',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 1,
   'child_unregister': 1,
   'master_unregister': 1,
   'clock_off': 1,
   'devres': 1,
   'unsafe_release': 4,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 1,
   'flush': 1,
   'stop': 1,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('callback-next-transfer',
  {'case': 'callback-next-transfer',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 2,
   'transfers': 2,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 2,
   'completion_order': 12,
   'transfer_order': 12,
   'lock_errors': 0,
   'validate_calls': 2,
   'queue_pending': 0,
   'work_pending': 1}),
 ('callback-worker-wakeup',
  {'case': 'callback-worker-wakeup',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 2,
   'transfers': 2,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 2,
   'completion_order': 12,
   'transfer_order': 12,
   'lock_errors': 0,
   'validate_calls': 2,
   'queue_pending': 0,
   'work_pending': 0}),
 ('preentered-enqueue-closed',
  {'case': 'preentered-enqueue-closed',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 1,
   'work_pending': 0}),
 ('sync-closed',
  {'case': 'sync-closed',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 1,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 1,
   'transfers': 1,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 1,
   'transfer_order': 1,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 1}),
 ('async-closed',
  {'case': 'async-closed',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 1,
   'work_pending': 1}),
 ('async-locked-closed',
  {'case': 'async-locked-closed',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 1,
   'work_pending': 1}),
 ('validate-sync',
  {'case': 'validate-sync',
   'result': -22,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('validate-async',
  {'case': 'validate-async',
   'result': -22,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('validate-async-locked',
  {'case': 'validate-async-locked',
   'result': -22,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('bus-locked-async',
  {'case': 'bus-locked-async',
   'result': -16,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('stopped-sync',
  {'case': 'stopped-sync',
   'result': -108,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 1,
   'queue_pending': 0,
   'work_pending': 0}),
 ('resume-closed',
  {'case': 'resume-closed',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 1}),
 ('init-clears',
  {'case': 'init-clears',
   'result': 0,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 1,
   'users': 9,
   'callbacks': 8,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}),
 ('init-fails',
  {'case': 'init-fails',
   'result': -12,
   'jumped': 0,
   'blocked': 0,
   'outer_returned': 0,
   'child_unregister': 0,
   'master_unregister': 0,
   'clock_off': 0,
   'devres': 0,
   'unsafe_release': 0,
   'after_release': 0,
   'queue_dead': 0,
   'users': 0,
   'callbacks': 0,
   'idling': 0,
   'cur_msg': 0,
   'busy': 0,
   'sleeps': 0,
   'flush': 0,
   'stop': 0,
   'completed': 0,
   'transfers': 0,
   'late_result': 999,
   'queue_result': 0,
   'callback_overlap': 0,
   'completion_order': 0,
   'transfer_order': 0,
   'lock_errors': 0,
   'validate_calls': 0,
   'queue_pending': 0,
   'work_pending': 0}))
LIMITS = (
    'Only actual queued SPI/core and driver remove/release bodies execute; list, locks, scheduling, PM, hardware and resource operations use inert seams.',
    'Stopping after520 virtual sleeps is an observation of a still-blocked unregister, not a kernel timeout, successful return, or forced cancellation.',
    'A controller which never completes may block unregister indefinitely so owned worker/callback resources are not freed; no finite end-to-end SPI deadline is promised.',
    'Protocol drivers must retire callers before device lifetime ends. Arbitrary stale pointers and controller IRQ/DMA tails beyond the core callback remain driver ownership contracts.',
    'Callbacks may requeue asynchronously but may not invoke sleeping unregister or synchronous transfers from their non-sleeping completion context.',
    'No device, real kernel locks, SMP scheduling, flash, reboot, host proc or private backup is accessed by this probe.',
    'No physical warm reset, real memory pressure, efd2 first-hop migration or historical cause is established.',
)


def validate_row(row, baseline=False):
    if type(baseline) is not bool or not isinstance(row,dict):raise ValueError('Typed lifecycle observation required')
    expected=dict(BASELINE_CASES if baseline else CURRENT_CASES).get(row.get('case'))
    if expected is None or set(row)!=set(expected):raise ValueError('Unknown/incomplete lifecycle observation')
    if any(type(row[key]) is not type(value) or row[key]!=value for key,value in expected.items()):
        raise ValueError('Lifecycle ownership/ordering outcome differs: '+row['case'])
    return True
