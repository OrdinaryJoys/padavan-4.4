"""Whole userspace switch status bodies; syscalls and rstats iteration are inert.

RTL8367 is a disabled compatibility variant in K2P.  Its symbolic ioctl values
are explicit test seams, not a claim about the missing RTL kernel wire ABI.
Only the ESW for-loop is executed from process_rstats; procfs/history are absent.
"""
import re

SOURCE_PATHS = {
    'mtk': 'trunk/user/rc/switch_mtk_esw.c',
    'rtl': 'trunk/user/rc/switch_rtl8367.c',
    'rstats': 'trunk/user/rc/rstats.c',
    'mtk_header': 'trunk/linux-4.4.x/drivers/net/ethernet/raeth/mtk_esw/ioctl.h',
}
WRAPPERS = {'mtk': 'mtk_esw_ioctl', 'rtl': 'rtl8367_ioctl'}
PREFIXES = {'mtk': 'MTK_ESW', 'rtl': 'RTL8367'}
RX = 0x123456789ABCDEF0
TX = 0xFEDCBA9876543200
CANARY_RX = 0xA1A2A3A4A5A6A7A8
CANARY_TX = 0xB1B2B3B4B5B6B7B8
CASES = ('wrap-open', 'wrap-ioctl', 'wrap-ok', 'get-open', 'get-ioctl',
         'get-ok', 'get-pos5', 'get-pos13', 'get-neg5', 'get-max', 'get-min',
         'consume-open', 'consume-ioctl', 'consume-ok', 'consume-pos5',
         'consume-neg5', 'consume-stub-ok')
MODEL_VARIANT = {
    'whole_wrappers_and_getters': True,
    'whole_source_bound_ESW_loop': True,
    'whole_process_rstats_execution': False,
    'syscalls_perror_and_history_are_inert': True,
    'RTL8367_shipping_K2P': False,
    'RTL8367_wire_ABI_validated': False,
    'BOARD_NUM_ETH_EPHY_is_explicit_five_port_seam': True,
}


def masked(text):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'
    return re.sub(tokens, lambda match: ' ' * len(match.group()), text)


def block_end(text, opening):
    depth = 0
    for match in re.finditer('[{}]', text[opening:]):
        depth += 1 if match.group() == '{' else -1
        if depth == 0:
            return opening + match.end()
    raise ValueError('Unterminated ESW userspace block')


def function(text, name):
    clean = masked(text)
    pattern = (r'(?m)^(?:static\s+)?(?:inline\s+)?(?:int|void)\s+' +
               re.escape(name) + r'\s*\([^;{}]*\)\s*\{')
    matches = list(re.finditer(pattern, clean))
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous ESW userspace function: ' + name)
    start = matches[0].start()
    return text[start:block_end(clean, clean.index('{', start))]


def consumer_loop(text):
    body = function(text, 'process_rstats')
    regions = list(re.finditer(r'(?m)^#if !defined\(RSTATS_SKIP_ESW\)\n([\s\S]*?)^#endif\b', body))
    if len(regions) != 1:
        raise ValueError('Exactly one enabled rstats ESW region required')
    region = regions[0].group(1)
    clean = masked(region)
    starts = list(re.finditer(r'(?m)^\s*for\s*\([^{}]*\)\s*\{', clean))
    if len(starts) != 1:
        raise ValueError('Exactly one complete rstats ESW for-loop required')
    start = starts[0].start()
    end = block_end(clean, clean.index('{', start))
    if clean[:start].strip() or clean[end:].strip():
        raise ValueError('Unexpected code outside rstats ESW for-loop')
    return region[start:end]


def validate_inputs(texts):
    if set(texts) != set(SOURCE_PATHS):
        raise ValueError('Exact userspace ESW source set required')
    for backend, wrapper in WRAPPERS.items():
        function(texts[backend], wrapper)
        function(texts[backend], 'phy_status_port_bytes')
    consumer_loop(texts['rstats'])
    declarations(texts)


def declarations(texts):
    header = texts['mtk_header']
    out = []
    for name in ('MTK_ESW_DEVPATH', 'MTK_ESW_IOCTL_CMD_LENGTH_BITS',
                 'MTK_ESW_IOCTL_STATUS_BYTES_PORT'):
        hits = list(re.finditer(r'(?m)^#define\s+' + name + r'\s+[^\n]+$', header))
        if len(hits) != 1:
            raise ValueError('Missing/ambiguous ESW declaration: ' + name)
        out.append(hits[0].group())
    hits = list(re.finditer(r'typedef struct port_bytes_s\s*\{[^{}]*\}\s*port_bytes_t;', masked(header)))
    if len(hits) != 1:
        raise ValueError('Missing/ambiguous port byte type')
    out.append(header[hits[0].start():hits[0].end()])
    return '\n'.join(out)


def expected(case):
    ret, rx, tx = 0, CANARY_RX, CANARY_TX
    opens = ioctls = closes = perrors = getters = 0
    records = []
    if case.startswith('wrap-'):
        opens = 1
        if case == 'wrap-open':
            ret, perrors = 13, 1
        else:
            ioctls = closes = 1
            rx, tx = RX + 2, TX + 2
            if case == 'wrap-ioctl':
                ret, perrors = 5, 1
    elif case.startswith('get-'):
        getters = 1
        if case in ('get-open', 'get-ioctl', 'get-ok'):
            opens = 1
            if case == 'get-open':
                ret, perrors = -13, 1
            else:
                ioctls = closes = 1
                if case == 'get-ioctl':
                    ret, perrors = -5, 1
                else:
                    rx, tx = RX + 3, TX + 3
        else:
            ret = {'get-pos5': -5, 'get-pos13': -13, 'get-neg5': -5,
                   'get-max': -2147483647, 'get-min': -2147483648}[case]
    elif case.startswith('consume-'):
        getters = 5
        if case in ('consume-open', 'consume-ioctl', 'consume-ok'):
            opens = 5
            if case == 'consume-open':
                perrors = 5
            else:
                ioctls = closes = 5
                if case == 'consume-ioctl':
                    perrors = 5
        if case in ('consume-ok', 'consume-stub-ok'):
            records = [['ESW_P' + str(port), 3, RX + port, TX + port]
                       for port in range(5)]
    else:
        raise ValueError('Unknown case')
    return [ret, rx, tx, opens, ioctls, closes, perrors, getters, records]


PREFIX = r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
SOURCE_DECLARATIONS
/* The disabled RTL backend has no kernel UAPI header in this checkout. */
#define RTL8367_DEVPATH "/inert-test/rtl8367"
#define RTL8367_IOCTL_CMD_LENGTH_BITS 8
#define RTL8367_IOCTL_STATUS_BYTES_PORT 26
#define BOARD_NUM_ETH_EPHY 5
#define PAYLOAD_RX UINT64_C(0x123456789abcdef0)
#define PAYLOAD_TX UINT64_C(0xfedcba9876543200)
#define CANARY_RX UINT64_C(0xa1a2a3a4a5a6a7a8)
#define CANARY_TX UINT64_C(0xb1b2b3b4b5b6b7b8)
static int fail_open, fail_ioctl, inject_wrapper, inject_getter, status;
static int opens, ioctls, closes, perrors, getters, iterations;
static struct { char name[16]; long ticks; uint64_t rx, tx; } records[5];
static int inert_open(const char *path, int flags)
{
 assert(!strcmp(path, BACKEND_DEVPATH) && flags == O_RDONLY);
 opens++;
 if (fail_open) { errno = EACCES; return -1; }
 return 42;
}
static int inert_ioctl(int fd, unsigned int cmd, unsigned int *value)
{
 unsigned int port = cmd >> BACKEND_BITS;
 port_bytes_t *pb = (port_bytes_t *)value;
 assert(fd == 42 && port < 5);
 assert((cmd & ((1u << BACKEND_BITS) - 1u)) == BACKEND_BYTES);
 ioctls++;
 /* A failing kernel may already have changed its private output buffer. */
 pb->RX = PAYLOAD_RX + port; pb->TX = PAYLOAD_TX + port;
 if (fail_ioctl) { errno = EIO; return -1; }
 return 0;
}
static void inert_perror(const char *message)
{
 assert(!strcmp(message, BACKEND_DEVPATH) || !strcmp(message, "ioctl"));
 perrors++; errno = EDOM;
}
static int inert_close(int fd)
{
 assert(fd == 42); closes++; errno = EBADF; return -1;
}
#define open inert_open
#define ioctl inert_ioctl
#define perror inert_perror
#define close inert_close
#define BACKEND_WRAPPER actual_ioctl_wrapper
WHOLE_WRAPPER
#undef BACKEND_WRAPPER
#undef open
#undef ioctl
#undef perror
#undef close
/* Dispatch to the real whole wrapper unless an explicit status seam is set. */
static int BACKEND_WRAPPER(unsigned int cmd, unsigned int port, unsigned int *value)
{
 if (inject_wrapper) {
  port_bytes_t *pb = (port_bytes_t *)value;
  (void)cmd; pb->RX = PAYLOAD_RX + port; pb->TX = PAYLOAD_TX + port;
  return status;
 }
 return actual_ioctl_wrapper(cmd, port, value);
}
#define phy_status_port_bytes actual_port_bytes_getter
WHOLE_GETTER
#undef phy_status_port_bytes
static int phy_status_port_bytes(int port, uint64_t *rx, uint64_t *tx)
{
 getters++;
 if (inject_getter) {
  *rx = PAYLOAD_RX + (unsigned int)port;
  *tx = PAYLOAD_TX + (unsigned int)port;
  return status;
 }
 return actual_port_bytes_getter(port, rx, tx);
}
static int iterate_netdev(const char *name, int index, int wan, long ticks, uint64_t *counter)
{
 assert(iterations < 5 && index == 0 && wan == 0);
 assert(snprintf(records[iterations].name, sizeof(records[iterations].name), "%s", name) > 0);
 records[iterations].ticks = ticks;
 records[iterations].rx = counter[0]; records[iterations].tx = counter[1];
 iterations++; return 1;
}
/* Entire source ESW loop; all other process_rstats branches are excluded. */
static void run_consumer(void)
{
 int i; char buf[256]; long ticks = 3;
 uint64_t counter[2] = {CANARY_RX, CANARY_TX};
WHOLE_CONSUMER_LOOP
}
'''

SUFFIX = r'''
int main(int argc, char **argv)
{
 const char *name; int ret = 0; uint64_t rx = CANARY_RX, tx = CANARY_TX;
 if (argc != 2) return 91;
 name = argv[1]; CASE_ADMISSION
 fail_open = strstr(name, "-open") != NULL;
 fail_ioctl = strstr(name, "-ioctl") != NULL;
 if (!strncmp(name, "get-", 4) && strcmp(name, "get-open") &&
     strcmp(name, "get-ioctl") && strcmp(name, "get-ok")) {
  inject_wrapper = 1;
  if (!strcmp(name, "get-max")) status = INT_MAX;
  else if (!strcmp(name, "get-min")) status = INT_MIN;
  else if (!strcmp(name, "get-pos13")) status = 13;
  else status = !strcmp(name, "get-neg5") ? -5 : 5;
 }
 if (!strcmp(name, "consume-pos5") || !strcmp(name, "consume-neg5") ||
     !strcmp(name, "consume-stub-ok")) {
  inject_getter = 1;
  status = !strcmp(name, "consume-pos5") ? 5 :
           (!strcmp(name, "consume-neg5") ? -5 : 0);
 }
 if (!strncmp(name, "wrap-", 5)) {
  port_bytes_t pb = {CANARY_RX, CANARY_TX};
  ret = actual_ioctl_wrapper(BACKEND_BYTES, 2, (unsigned int *)&pb);
  rx = pb.RX; tx = pb.TX;
 } else if (!strncmp(name, "get-", 4)) ret = phy_status_port_bytes(3, &rx, &tx);
 else run_consumer();
 printf("[%d,%" PRIu64 ",%" PRIu64 ",%d,%d,%d,%d,%d,[", ret, rx, tx,
        opens, ioctls, closes, perrors, getters);
 for (int i = 0; i < iterations; i++)
  printf("%s[\"%s\",%ld,%" PRIu64 ",%" PRIu64 "]", i ? "," : "",
         records[i].name, records[i].ticks, records[i].rx, records[i].tx);
 puts("]]");
 return 0;
}
'''


def generate_source(texts, backend, replacements=None):
    validate_inputs(texts)
    if backend not in WRAPPERS:
        raise ValueError('Unknown ESW backend')
    wrapper = WRAPPERS[backend]
    prefix = PREFIXES[backend]
    parts = {'wrapper': function(texts[backend], wrapper),
             'getter': function(texts[backend], 'phy_status_port_bytes'),
             'consumer': consumer_loop(texts['rstats'])}
    if replacements:
        if set(replacements) - set(parts):
            raise ValueError('Unknown whole-body replacement')
        parts.update(replacements)
    code = PREFIX.replace('SOURCE_DECLARATIONS', declarations(texts))
    code = code.replace('WHOLE_WRAPPER', parts['wrapper'])
    code = code.replace('WHOLE_GETTER', parts['getter'])
    code = code.replace('WHOLE_CONSUMER_LOOP', parts['consumer'])
    admission = 'if (!(' + ' || '.join('!strcmp(name, "' + case + '")' for case in CASES) + ')) return 91;'
    code += SUFFIX.replace('CASE_ADMISSION', admission)
    # Macro substitution renames only the call/definition seam at preprocessing.
    for placeholder, value in (('BACKEND_WRAPPER', wrapper),
                               ('BACKEND_DEVPATH', prefix + '_DEVPATH'),
                               ('BACKEND_BITS', prefix + '_IOCTL_CMD_LENGTH_BITS'),
                               ('BACKEND_BYTES', prefix + '_IOCTL_STATUS_BYTES_PORT')):
        code = code.replace(placeholder, value)
    return code
