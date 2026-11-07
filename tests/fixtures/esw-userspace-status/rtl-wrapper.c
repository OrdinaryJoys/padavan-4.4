static int
rtl8367_ioctl(unsigned int cmd, unsigned int par, unsigned int *value)
{
	int fd, retVal = 0;

	fd = open(RTL8367_DEVPATH, O_RDONLY);
	if (fd < 0) {
		perror(RTL8367_DEVPATH);
		return errno;
	}

	cmd &= ((1u << RTL8367_IOCTL_CMD_LENGTH_BITS) - 1);
	cmd |= (par << RTL8367_IOCTL_CMD_LENGTH_BITS);

	if (ioctl(fd, cmd, value) < 0) {
		perror("ioctl");
		retVal = errno;
	}

	close(fd);

	return retVal;
}
