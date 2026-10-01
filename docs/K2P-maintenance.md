# K2P maintenance (2026-10-01)

The direct upstream main branch is already included in this fork. Preserve this fork's board and network drivers.

Components: curl 8.22.0, OpenSSL 3.5.9 LTS, OpenSSH 9.9p2 and OpenVPN 2.6.23. Verify each source archive's pinned SHA256 before extraction. OpenSSL uses built-in providers and ships the MIPS atomic runtime. Deprecated APIs remain available for legacy Padavan consumers. Post-quantum algorithms are omitted from this 16MB profile; ordinary TLS 1.2/1.3, RSA, ECC, AES and ChaCha20 remain.

Install the Mozilla CA bundle from https://curl.se/ca/cacert.pem (2026-09-25; SHA256 a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505). Use it as libcurl's default trust store, restore trust paths on boot and enable DDNS TLS certificate verification. A nonempty /etc/storage/cacert.pem remains a persistent override. Preserve user inadyn.conf overrides.

The OpenSSH shared-library/moduli adaptation is ported from vb1980/padavan-4.4 (openssh-orig.patch blob ca4fdb2f063785b61ee049ae282b931cf11cb2d8), checked against the official 9.9p2 source. Install sshd-session, required by this SSH release, in /usr/libexec.

The image must fit the K2P firmware partition (15,925,248 bytes). Build and image validation do not establish runtime compatibility; do not flash automatically. Kernel, dnsmasq and other legacy components are not represented as current by this update. TLS security defaults and SSH/VPN interoperability still require device tests. Do not commit device credentials or backups.
