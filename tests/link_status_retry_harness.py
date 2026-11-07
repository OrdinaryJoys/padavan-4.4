"""Actual link timer and WAN query, with inert ioctl/NVRAM/action seams.

This checks retry/publication logic, not PHY behavior, IRQ timing or networking.
"""
import re

SOURCE_PATHS = {
    'timer': 'trunk/user/rc/detect_link.c',
    'wan': 'trunk/user/rc/net_wan.c',
    'uapi': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl.h',
}
FUNCTION_SOURCES = {'dl_on_timer': 'timer', 'get_wan_ether_link_direct': 'wan'}
FIELDS = ('wan', 'lan', 'event_reads', 'wan_reads', 'lan_reads',
          'wan_handles', 'lan_handles', 'wisp_handles')
WAN_ENTRY_FIELDS = ('result', 'port', 'nvram_reads')
CASE_NAMES = ('success-no-change', 'wan-failure-retry', 'lan-failure-retry',
              'event-failure-retry', 'repeated-failure', 'ap-failure-clear',
              'ap-wan-failure', 'initialized-wan-failure',
              'initialized-lan-failure', 'initialized-event-failure', 'wan-entry')
EXPECTED_ROWS = {
    'success-no-change': [[1, 0, 1, 1, 1, 1, 1, 1],
                          [1, 0, 2, 1, 1, 2, 2, 2],
                          [0, 1, 3, 2, 2, 3, 3, 3]],
    'wan-failure-retry': [[0, 1, 1, 1, 1, 1, 1, 1],
                          [1, 0, 2, 2, 2, 2, 2, 2],
                          [1, 0, 3, 2, 2, 3, 3, 3]],
    'lan-failure-retry': [[0, 1, 1, 1, 1, 1, 1, 1],
                          [1, 0, 2, 2, 2, 2, 2, 2],
                          [1, 0, 3, 2, 2, 3, 3, 3]],
    'event-failure-retry': [[1, 0, 1, 0, 0, 1, 1, 1],
                            [0, 1, 2, 1, 1, 2, 2, 2],
                            [0, 1, 3, 1, 1, 3, 3, 3]],
    'repeated-failure': [[0, 1, 1, 1, 1, 1, 1, 1],
                         [0, 1, 2, 2, 2, 2, 2, 2],
                         [1, 0, 3, 3, 3, 3, 3, 3]],
    'ap-failure-clear': [[1, 1, 1, 1, 1, 0, 1, 0],
                         [0, 0, 2, 2, 2, 0, 2, 0],
                         [1, 1, 3, 3, 3, 0, 3, 0]],
    'ap-wan-failure': [[1, 1, 1, 1, 1, 0, 1, 0],
                       [0, 0, 2, 2, 2, 0, 2, 0],
                       [0, 0, 3, 2, 2, 0, 3, 0]],
    'initialized-wan-failure': [[1, 0, 1, 1, 1, 1, 1, 1],
                                [1, 0, 2, 2, 2, 2, 2, 2],
                                [0, 1, 3, 3, 3, 3, 3, 3]],
    'initialized-lan-failure': [[1, 0, 1, 1, 1, 1, 1, 1],
                                [1, 0, 2, 2, 2, 2, 2, 2],
                                [0, 1, 3, 3, 3, 3, 3, 3]],
    'initialized-event-failure': [[1, 0, 1, 1, 1, 1, 1, 1],
                                  [1, 0, 2, 1, 1, 2, 2, 2],
                                  [0, 1, 3, 2, 2, 3, 3, 3]],
    'wan-entry': [[1, 0, 1], [0, 4, 2], [1, 0, 2], [-1, 0, 3]],
}
MODEL_VARIANT = {
    'actual_whole_timer_and_wan_entry': True,
    'queries_and_actions_are_inert': True,
    'USB_branch_disabled': True,
    'LAN_void_pointer_shim_allows_pinned_old_signed_local': True,
    'hardware_and_kernel_concurrency_are_not_proven': True,
}


def function(text, name):
    matches = list(re.finditer(r'(?m)^(?:static\s+)?(?:int|void)\s+' +
                              re.escape(name) + r'\s*\(', text))
    if len(matches) != 1:
        raise ValueError('missing or ambiguous whole function: ' + name)
    match = matches[0]
    start = text.index('{', match.end())
    depth, end = 1, start + 1
    while depth and end < len(text):
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    if depth:
        raise ValueError('unclosed whole function: ' + name)
    return text[match.start():end]


PREFIX = r'''
#include <stdio.h>
#include <string.h>
struct sample { int event_error; unsigned changed; int wan_error;
                unsigned wan; int lan_error; unsigned lan; };
static struct sample samples[3];
static int tick, dl_is_ap_mode, dl_counter_total;
static int dl_status_wan, dl_status_lan, dl_status_wisp;
static int event_reads, wan_reads, lan_reads, wan_handles, lan_handles, wisp_handles;
static int nvram_port, nvram_reads, last_port;
static int nvram_get_int(const char *key)
{ if (strcmp(key, "wan_src_phy")) return -1; nvram_reads++; return nvram_port; }
static int phy_status_port_link(int port, unsigned *result)
{ wan_reads++; last_port=port; if(samples[tick].wan_error)return samples[tick].wan_error;
  *result=samples[tick].wan; return 0; }
static int phy_status_port_link_changed(unsigned *result)
{ event_reads++; if(samples[tick].event_error)return samples[tick].event_error;
  *result=samples[tick].changed; return 0; }
/* The old whole timer passes int*, the current timer passes unsigned int*.
 * This inert seam writes the same 32-bit value; it is not an ABI assertion. */
static int phy_status_port_link_lan_all(void *output)
{ unsigned *result=output; lan_reads++; if(samples[tick].lan_error)return samples[tick].lan_error;
  *result=samples[tick].lan; return 0; }
static void dl_handle_link_wan(void) { wan_handles++; }
static void dl_handle_link_lan(void) { lan_handles++; }
static void dl_handle_link_wisp(void) { wisp_handles++; }
static int get_wan_wisp_active(int *state) { *state=1; return 1; }
'''
SUFFIX = r'''
static void row(void)
{ printf("[%d,%d,%d,%d,%d,%d,%d,%d]",dl_status_wan,dl_status_lan,event_reads,
         wan_reads,lan_reads,wan_handles,lan_handles,wisp_handles); }
int main(int argc, char **argv)
{
 const char *name; int r;
 if(argc!=2)return 90;
 name=argv[1];
 if(!strcmp(name,"wan-entry")) {
  printf("[");
  nvram_port=-3;samples[0].wan=1;r=get_wan_ether_link_direct(0);
  printf("[%d,%d,%d],",r,last_port,nvram_reads);
  nvram_port=4;samples[0].wan=0;r=get_wan_ether_link_direct(0);
  printf("[%d,%d,%d],",r,last_port,nvram_reads);
  samples[0].wan=1;r=get_wan_ether_link_direct(1);
  printf("[%d,%d,%d],",r,last_port,nvram_reads);
  nvram_port=0;samples[0].wan_error=5;r=get_wan_ether_link_direct(0);
  printf("[%d,%d,%d]]\n",r,last_port,nvram_reads);
  return 0;
 }
 samples[0].wan=samples[1].wan=samples[2].wan=1;
 if(!strcmp(name,"success-no-change")) {
  samples[2].changed=1;samples[2].wan=0;samples[2].lan=1;
 } else if(!strcmp(name,"initialized-wan-failure")||
           !strcmp(name,"initialized-lan-failure")||
           !strcmp(name,"initialized-event-failure")) {
  samples[1].changed=1;samples[1].wan=0;samples[1].lan=1;
  samples[2].wan=0;samples[2].lan=1;
  if(!strcmp(name,"initialized-wan-failure"))samples[1].wan_error=5;
  else if(!strcmp(name,"initialized-lan-failure"))samples[1].lan_error=5;
  else samples[1].event_error=5;
 } else if(!strcmp(name,"wan-failure-retry")||!strcmp(name,"lan-failure-retry")||
           !strcmp(name,"repeated-failure")) {
  dl_status_lan=1;samples[0].changed=1;
  if(!strcmp(name,"lan-failure-retry"))samples[0].lan_error=5;
  else samples[0].wan_error=5;
  if(!strcmp(name,"repeated-failure"))samples[1].lan_error=5;
 } else if(!strcmp(name,"event-failure-retry")) {
  dl_status_wan=1;samples[0].event_error=5;
  samples[1].wan=0;samples[1].lan=1;
 } else if(!strcmp(name,"ap-failure-clear")||!strcmp(name,"ap-wan-failure")) {
  dl_is_ap_mode=1;dl_status_wan=dl_status_lan=1;
  samples[0].wan=samples[1].wan=samples[2].wan=0;
  if(!strcmp(name,"ap-wan-failure"))samples[0].wan_error=5;
  else {samples[0].lan_error=5;samples[2].changed=1;samples[2].wan=1;}
 } else return 91;
 printf("[");
 for(tick=0;tick<3;tick++){if(tick)printf(",");dl_on_timer();row();}
 printf("]\n");return 0;
}
'''


def generate_source(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('missing or unknown source keys')
    declarations = re.findall(r'(?m)^#define\s+SWAPI_PORT_WAN\s+[^\n]+$', texts['uapi'])
    if len(declarations) != 1:
        raise ValueError('missing or ambiguous WAN port definition')
    bodies = [function(texts[FUNCTION_SOURCES[name]], name)
              for name in ('get_wan_ether_link_direct', 'dl_on_timer')]
    return PREFIX + '\n' + declarations[0] + '\n' + '\n'.join(bodies) + '\n' + SUFFIX
