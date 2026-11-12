"""Whole RAETH MAC functions; netdev state and MMIO are explicit inert seams."""
from pathlib import Path
from raeth_runtime_harness import function

SOURCE_PATHS = {
    'raeth': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/raether.c',
    'mac': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/ra_mac.c',
}
FUNCTION_SOURCES = {
    'set_mac_address': 'mac', 'set_mac2_address': 'mac',
    'ei_set_mac_addr': 'raeth', 'ei_set_mac2_addr': 'raeth',
    'ei_mac_addr_setting': 'raeth',
}
PREFIX = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
struct sockaddr { unsigned short family; unsigned char sa_data[14]; };
struct net_device { unsigned char dev_addr[32]; int addr_len, running, addr_assign_type; };
#define NET_ADDR_RANDOM 1
#define GDMA1_MAC_ADRH 0
#define GDMA1_MAC_ADRL 1
#define GDMA2_MAC_ADRH 2
#define GDMA2_MAC_ADRL 3
static u32 regs[4];
static unsigned writes;
static void sys_reg_write(unsigned address, unsigned long value) { regs[address] = (u32)value; writes++; }
static int netif_running(struct net_device *dev) { return dev->running; }
static int is_valid_ether_addr(const unsigned char *p) {
    unsigned i, any = 0; for (i=0;i<6;i++) any |= p[i];
    return any && !(p[0] & 1);
}
static void random_ether_addr(unsigned char *p) {
    static const unsigned char random[6] = {2,0xab,0xcd,0xef,0x12,0x34};
    memcpy(p, random, 6);
}
'''
SUFFIX = r'''
int main(int argc, char **argv) {
    struct net_device dev = {{2,0x12,0x80,0x34,0x56,0x78},6,0,0};
    struct sockaddr addr = {1,{2,0x98,0xfe,0xdc,0xba,0x76}};
    int ret = 0, second;
    unsigned i;
    if (argc != 2) return 2;
    for (i=0;i<4;i++) regs[i] = 0xdeadbeef;
    second = !strncmp(argv[1],"second-",7);
    dev.running = strstr(argv[1],"-up") != NULL;
    if (strstr(argv[1],"zero")) memset(addr.sa_data,0,6);
    if (strstr(argv[1],"multicast")) addr.sa_data[0] = 1;
    if (!strncmp(argv[1],"init-",5)) {
        if (!strcmp(argv[1],"init-invalid")) memset(dev.dev_addr,0,6);
        ei_mac_addr_setting(&dev);
    } else if (second) ret = ei_set_mac2_addr(&dev,&addr);
    else ret = ei_set_mac_addr(&dev,&addr);
    printf("{\"ret\":%d,\"mac\":\"", ret);
    for (i=0;i<6;i++) printf("%02x",dev.dev_addr[i]);
    printf("\",\"registers\":[%u,%u,%u,%u],\"writes\":%u,\"random\":%d}\n",
           regs[0],regs[1],regs[2],regs[3],writes,dev.addr_assign_type);
    return 0;
}
'''

def generate_source(texts):
    return PREFIX + '\n'.join(function(texts[k], n) for n,k in FUNCTION_SOURCES.items()) + SUFFIX

def current_texts(root=None):
    root = root or Path(__file__).resolve().parents[1]
    return {k:(root/p).read_text() for k,p in SOURCE_PATHS.items()}
