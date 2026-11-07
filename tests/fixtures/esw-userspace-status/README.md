These are exact older userspace switch bodies from source commit
`97b961d3735c2452f64b34d916b3d6dfaf7dae96`. `manifest.json` records their
source paths and SHA256 values. The MTK/RTL ioctl wrappers and byte getters
are whole functions; the rstats fixture is the complete ESW `for` loop from
the `#if !defined(RSTATS_SKIP_ESW)` branch of `process_rstats`.

The tests compile each older body against the otherwise current source-bound
chain using both GNU GCC 16 at `-O2 -Wall -Wextra -Werror` and Clang with the
same flags plus AddressSanitizer and UndefinedBehaviorSanitizer. Each fixture
must compile and run, then fail the corrected semantic expectation: saved
errno survives an errno-changing `perror`, a getter never publishes a failed
sample, and the consumer accepts only a zero status.

All syscall, diagnostic, output-counter, and history operations are inert
seams. The enabled MTK constants and port-byte type are extracted from the
actual header. The checkout has no RTL8367 kernel UAPI header, so its command
constants are explicit symbolic seams; RTL8367 is a disabled compatibility
variant for K2P. The harness executes the complete ESW loop, not the rest of
`process_rstats`, and uses an explicit five-port board seam. These tests do
not access a switch, procfs, device nodes, real history, or the network and
do not validate a physical/kernel ioctl wire ABI.
