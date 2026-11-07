VOID wifi_fwd_register(struct wifi_fwd_func_table *table)
{

wf_drv_tbl.wf_fwd_tx_hook = table->wf_fwd_tx_hook;
wf_drv_tbl.wf_fwd_rx_hook = table->wf_fwd_rx_hook;
wf_drv_tbl.wf_fwd_entry_insert_hook = table->wf_fwd_entry_insert_hook;
wf_drv_tbl.wf_fwd_entry_delete_hook = table->wf_fwd_entry_delete_hook;
wf_drv_tbl.wf_fwd_set_cb_num  =  table->wf_fwd_set_cb_num;
wf_drv_tbl.wf_fwd_set_debug_level_hook = table->wf_fwd_set_debug_level_hook;
wf_drv_tbl.wf_fwd_check_active_hook = table->wf_fwd_check_active_hook;
wf_drv_tbl.wf_fwd_get_rep_hook = table->wf_fwd_get_rep_hook;
wf_drv_tbl.wf_fwd_pro_active_hook = table->wf_fwd_pro_active_hook;
wf_drv_tbl.wf_fwd_pro_halt_hook 	= table->wf_fwd_pro_halt_hook;
wf_drv_tbl.wf_fwd_pro_enabled_hook = table->wf_fwd_pro_enabled_hook;
wf_drv_tbl.wf_fwd_pro_disabled_hook 	= table->wf_fwd_pro_disabled_hook;
wf_drv_tbl.wf_fwd_access_schedule_active_hook = table->wf_fwd_access_schedule_active_hook;
wf_drv_tbl.wf_fwd_access_schedule_halt_hook =	table->wf_fwd_access_schedule_halt_hook;
wf_drv_tbl.wf_fwd_hijack_active_hook = table->wf_fwd_hijack_active_hook;
wf_drv_tbl.wf_fwd_hijack_halt_hook = table->wf_fwd_hijack_halt_hook;
wf_drv_tbl.wf_fwd_bpdu_active_hook = table->wf_fwd_bpdu_active_hook;
wf_drv_tbl.wf_fwd_bpdu_halt_hook 	= table->wf_fwd_bpdu_halt_hook;
wf_drv_tbl.wf_fwd_show_entry_hook = table->wf_fwd_show_entry_hook;
wf_drv_tbl.wf_fwd_needed_hook = table->wf_fwd_needed_hook;
wf_drv_tbl.wf_fwd_delete_entry_hook =	table->wf_fwd_delete_entry_hook;
wf_drv_tbl.packet_source_show_entry_hook = table->packet_source_show_entry_hook;
wf_drv_tbl.packet_source_delete_entry_hook = table->packet_source_delete_entry_hook;
wf_drv_tbl.wf_fwd_feedback_map_table 	= table->wf_fwd_feedback_map_table;
wf_drv_tbl.wf_fwd_probe_adapter =	table->wf_fwd_probe_adapter;
wf_drv_tbl.wf_fwd_insert_bridge_mapping_hook = table->wf_fwd_insert_bridge_mapping_hook;
wf_drv_tbl.wf_fwd_insert_repeater_mapping_hook = table->wf_fwd_insert_repeater_mapping_hook;
wf_drv_tbl.wf_fwd_search_mapping_table_hook =	table->wf_fwd_search_mapping_table_hook;
wf_drv_tbl.wf_fwd_delete_entry_inform_hook =	table->wf_fwd_delete_entry_inform_hook;
wf_drv_tbl.wf_fwd_check_device_hook =	table->wf_fwd_check_device_hook;
wf_drv_tbl.wf_fwd_add_entry_inform_hook =	table->wf_fwd_add_entry_inform_hook;
wf_drv_tbl.wf_fwd_set_easy_setup_mode = table->wf_fwd_set_easy_setup_mode;
wf_drv_tbl.wf_fwd_set_bridge_hook = table->wf_fwd_set_bridge_hook;



}
