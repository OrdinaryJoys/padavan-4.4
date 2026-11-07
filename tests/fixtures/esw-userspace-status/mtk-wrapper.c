static int
mtk_esw_ioctl(unsigned int cmd, unsigned int par, unsigned int *value)
{
	int fd, retVal = 0;

	fd = open(MTK_ESW_DEVPATH, O_RDONLY);
	if (fd < 0)
	{
		perror(MTK_ESW_DEVPATH);
		return errno;
	}

	cmd &= ((1u << MTK_ESW_IOCTL_CMD_LENGTH_BITS) - 1);
	cmd |= (par << MTK_ESW_IOCTL_CMD_LENGTH_BITS);

	if (ioctl(fd, cmd, value) < 0) {
		perror("ioctl");
		retVal = errno;
	}

	close(fd);

	return retVal;
}
