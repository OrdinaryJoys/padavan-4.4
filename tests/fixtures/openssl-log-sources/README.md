# Public OpenSSL log fixtures

These five files are exact regular-file bytes from the official OpenSSL3.5.9 archive,
SHA256 603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a.
Their original Apache2.0 copyright/license notices remain intact. test_openssl_bounded_log.py
pins each SHA256 and only applies the firmware's exact five-target logging patch.

Native tests compile the actual Unix BIO method bodies against inert BIO scaffolding
and actual patched app logger functions. The old blocking-dependency control uses the
actual uClibc-ng1.0.38 syslog functions with native mutex/ABI glue, a private STREAM
endpoint and a bounded socket buffer, not host /dev/log or actual MIPS execution. The old
large-input allocation observation is from the unchanged real slg_write body. Native
scaffolding does not prove the target BIO ABI; a separate Linux CI probe links public
BIO APIs to the actual shipped libcrypto. Same-BIO concurrent use retains OpenSSL's
caller serialization requirements. No OCSP daemon or real private key is used.
