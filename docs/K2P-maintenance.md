# K2P maintenance (2026-10-01)

The direct upstream main branch is already included in this fork. Keep the board and network drivers from this fork.

This update installs the Mozilla CA bundle from https://curl.se/ca/cacert.pem (2026-09-25; SHA256 a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505) in the firmware, selects it as libcurl's default trust store, and enables DDNS TLS certificate verification. A nonempty /etc/storage/cacert.pem remains an optional persistent override. User inadyn.conf overrides are preserved.

The firmware image must fit the K2P firmware partition (15,925,248 bytes). Build and image validation do not establish runtime compatibility; do not flash automatically. No device credentials or backups belong in this repository.

Components: curl 8.22.0 (official release 2026-09-02) and OpenSSL 1.1.1w, with SHA256 checked before extraction. The existing OpenSSL vendor patch passes git apply --check against 1.1.1w. OpenSSL 1.1.1w is an end-of-life compatibility update, not a supported TLS stack. Kernel, dnsmasq, SSH and other legacy components are not represented as current or secure by this update. A supported OpenSSL migration needs separate compatibility and device testing.
