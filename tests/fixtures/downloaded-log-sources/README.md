# Public upstream logger fixtures

Unmodified full C source files retain their upstream copyright and license notices.
They are inert source data for applying the exact package patches and executing
central logger bodies with isolated IO and inert surrounding services. Neither
SSH authentication nor VPN/tunnel/daemon behavior is exercised.

- OpenSSH 10.6p1 log.c: archive from https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-10.6p1.tar.gz, archive SHA256 a9dc9565dffe8640f64d863cd29a32bc4a3dbdec0566a7fc44c5d6ee767d5f39; member SHA256 7a74de1d23092e05f7b55e5fd9d38da6ff1c9b0620c682cde5b014f0511c00f6.
- OpenVPN 2.6.23 src/openvpn/error.c: archive from https://github.com/OpenVPN/openvpn/releases/download/v2.6.23/openvpn-2.6.23.tar.gz, archive SHA256 4041c709162bec1325abf5aa8cf27a255cc477c634b15ee310411c701fc40a96; member SHA256 8ba73b3adcccf0a100e45bf49c2b5626de557629ac70cc482c450d3a554d8785.

Production still builds the complete hash-verified upstream archives using the
package Makefiles. These fixtures do not replace the production source archive.

- SmartDNS ba282c8 src/dns_conf.c: tracked archive SHA256 3bf08285529d72168a4a0707cee27680e619229ffb00329bd63cc3a5efd8b092; member SHA256 c917e70441ef1cef51a4a812a31d72809ec232110174aeaab132029ea2886a5e. Only the config-load syslog branch is exercised, with inert parser/tlog callbacks.
