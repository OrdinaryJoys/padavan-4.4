VOID wifi_fwd_unregister(VOID)
{

wf_drv_tbl.wf_fwd_tx_hook = NULL;
wf_drv_tbl.wf_fwd_rx_hook = NULL;
wf_drv_tbl.wf_fwd_entry_insert_hook = NULL;
wf_drv_tbl.wf_fwd_entry_delete_hook = NULL;
wf_drv_tbl.wf_fwd_set_cb_num = NULL;
wf_drv_tbl.wf_fwd_set_debug_level_hook = NULL;
wf_drv_tbl.wf_fwd_check_active_hook = NULL;
wf_drv_tbl.wf_fwd_get_rep_hook = NULL;
wf_drv_tbl.wf_fwd_pro_active_hook = NULL;
wf_drv_tbl.wf_fwd_pro_halt_hook = NULL;
wf_drv_tbl.wf_fwd_pro_enabled_hook = NULL;
wf_drv_tbl.wf_fwd_pro_disabled_hook = NULL;
wf_drv_tbl.wf_fwd_access_schedule_active_hook = NULL;
wf_drv_tbl.wf_fwd_access_schedule_halt_hook = NULL;
wf_drv_tbl.wf_fwd_hijack_active_hook = NULL;
wf_drv_tbl.wf_fwd_hijack_halt_hook = NULL;
wf_drv_tbl.wf_fwd_bpdu_active_hook = NULL;
wf_drv_tbl.wf_fwd_bpdu_halt_hook = NULL;
wf_drv_tbl.wf_fwd_show_entry_hook = NULL;
wf_drv_tbl.wf_fwd_needed_hook = NULL;
wf_drv_tbl.wf_fwd_delete_entry_hook = NULL;
wf_drv_tbl.packet_source_show_entry_hook = NULL;
wf_drv_tbl.packet_source_delete_entry_hook = NULL;
wf_drv_tbl.wf_fwd_feedback_map_table = NULL;
wf_drv_tbl.wf_fwd_probe_adapter = NULL;
wf_drv_tbl.wf_fwd_insert_bridge_mapping_hook = NULL;
wf_drv_tbl.wf_fwd_insert_repeater_mapping_hook = NULL;
wf_drv_tbl.wf_fwd_search_mapping_table_hook = NULL;
wf_drv_tbl.wf_fwd_delete_entry_inform_hook = NULL;
wf_drv_tbl.wf_fwd_check_device_hook = NULL;
wf_drv_tbl.wf_fwd_add_entry_inform_hook = NULL;
wf_drv_tbl.wf_fwd_set_easy_setup_mode = NULL;
wf_drv_tbl.wf_fwd_set_bridge_hook = NULL;


}
