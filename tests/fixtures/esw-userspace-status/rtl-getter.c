int phy_status_port_bytes(int port_id_uapi, uint64_t *rx, uint64_t *tx)
{
	port_bytes_t pb;
	int ioctl_result;

	ioctl_result = rtl8367_ioctl(RTL8367_IOCTL_STATUS_BYTES_PORT, port_id_uapi, (unsigned int *)&pb);
	if (ioctl_result < 0)
		return ioctl_result;

	*rx = pb.RX;
	*tx = pb.TX;

	return ioctl_result;
}
