static long mtk_esw_ioctl(struct file *file, unsigned int req, unsigned long arg)
{
	int ioctl_result = 0;
	u32 uint_value = 0;
	u32 uint_result = 0;
	port_bytes_t port_bytes = {0};
	esw_mib_counters_t port_counters;

	unsigned int uint_param = (req >> MTK_ESW_IOCTL_CMD_LENGTH_BITS);
	req &= ((1u << MTK_ESW_IOCTL_CMD_LENGTH_BITS)-1);

	mutex_lock(&esw_access_mutex);

	switch(req)
	{
	case MTK_ESW_IOCTL_STATUS_LINK_PORT: /* used by rc */
		uint_result = esw_status_link_port_uapi(uint_param);
		put_user(uint_result, (unsigned int __user *)arg);
		break;
	case MTK_ESW_IOCTL_STATUS_LINK_PORTS_WAN: /* used by rc */
		uint_result = esw_status_link_ports(1);
		put_user(uint_result, (unsigned int __user *)arg);
		break;
	case MTK_ESW_IOCTL_STATUS_LINK_PORTS_LAN: /* used by rc */
		uint_result = esw_status_link_ports(0);
		put_user(uint_result, (unsigned int __user *)arg);
		break;
	case MTK_ESW_IOCTL_STATUS_LINK_CHANGED: /* used by rc */
		uint_result = esw_status_link_changed();
		put_user(uint_result, (unsigned int __user *)arg);
		break;

	case MTK_ESW_IOCTL_STATUS_SPEED_PORT: /* used by rc */
		uint_result = esw_status_speed_port_uapi(uint_param);
		put_user(uint_result, (unsigned int __user *)arg);
		break;

	case MTK_ESW_IOCTL_STATUS_BYTES_PORT: /* used by rc */
		ioctl_result = esw_status_bytes_port_uapi(uint_param, &port_bytes);
		copy_to_user((port_bytes_t __user *)arg, &port_bytes, sizeof(port_bytes_t));
		break;

	case MTK_ESW_IOCTL_STATUS_MIB_PORT: /* used by rc */
		ioctl_result = esw_status_mib_port_uapi(uint_param, &port_counters);
		copy_to_user((esw_mib_counters_t __user *)arg, &port_counters, sizeof(esw_mib_counters_t));
		break;

	case MTK_ESW_IOCTL_PORTS_POWER: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		change_ports_power(uint_param, uint_value);
		break;

	case MTK_ESW_IOCTL_PORTS_WAN_LAN_POWER: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		change_wan_lan_ports_power(uint_param, uint_value);
		break;
	case MTK_ESW_IOCTL_MAC_TABLE_CLEAR: /* used by rc */
		esw_mac_table_clear();
		break;

	case MTK_ESW_IOCTL_BRIDGE_MODE: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		ioctl_result = change_bridge_mode(uint_param, uint_value);
		break;

	case MTK_ESW_IOCTL_VLAN_RESET_TABLE: /* used by rc */
		esw_vlan_reset_table();
		break;
	case MTK_ESW_IOCTL_VLAN_PVID_WAN_GET: /* used by rc */
		uint_result = g_vlan_pvid_wan_untagged;
		put_user(uint_result, (unsigned int __user *)arg);
		break;
	case MTK_ESW_IOCTL_VLAN_ACCEPT_PORT_MODE:  /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		vlan_accept_port_mode(uint_param, uint_value);
		break;
	case MTK_ESW_IOCTL_VLAN_CREATE_PORT_VID: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		vlan_create_entry(uint_param, uint_value, 1);
		break;
	case MTK_ESW_IOCTL_VLAN_CREATE_ENTRY: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		vlan_create_entry(uint_param, uint_value, 0);
		break;
	case MTK_ESW_IOCTL_VLAN_RULE_SET: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		ioctl_result = change_vlan_rule(uint_param, uint_value);
		break;

	case MTK_ESW_IOCTL_STORM_BROADCAST:  /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		change_storm_control_broadcast(uint_value);
		break;

	case MTK_ESW_IOCTL_JUMBO_FRAMES: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		change_jumbo_frames_accept(uint_value);
		break;

	case MTK_ESW_IOCTL_IGMP_SNOOPING: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		change_igmp_snooping_control(uint_value);
		break;

	case MTK_ESW_IOCTL_IGMP_STATIC_PORTS: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		change_igmp_static_ports(uint_value);
		break;

	case MTK_ESW_IOCTL_LED_MODE: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		change_led_mode(uint_value);
		break;

	case MTK_ESW_IOCTL_SPEED_PORT: /* used by rc */
		copy_from_user(&uint_value, (int __user *)arg, sizeof(int));
		ioctl_result = change_port_link_mode_uapi(uint_param, uint_value);
		break;

	default:
		ioctl_result = -ENOIOCTLCMD;
	}

	mutex_unlock(&esw_access_mutex);

	return ioctl_result;
}