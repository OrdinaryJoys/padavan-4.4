#!/usr/bin/env python3
"""Exercise actual rc DNS generation using a confined native I/O harness.

No router, real system configuration, shell command, or daemon is touched.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_httpd_regressions import function, source


class RuntimeDNSConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        text = source('trunk/user/rc/services_ex.c')
        code = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <stdbool.h>
#include <ctype.h>
#include <errno.h>
#include <assert.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <arpa/inet.h>
static const char *root;
static int deny_chmod, deny_truncate, deny_fdopen, foreign_owner;
static int fail_validation, fail_close, validation_calls, exec_calls, last_fd;
static const char *map_path(const char *p) {
    static char out[4096];
    if(!strncmp(p,"/etc/",5) || !strncmp(p,"/tmp/",5)) {
        assert(snprintf(out,sizeof(out),"%s%s",root,p)<(int)sizeof(out)); return out;
    }
    return p;
}
static int audit_open(const char *p,int flags,...) {
    int fd=open(map_path(p),flags,0644); last_fd=fd; return fd;
}
static int audit_fstat(int fd,struct stat *st) {
    int rc=fstat(fd,st); if(!rc && foreign_owner) st->st_uid=geteuid()+1; return rc;
}
static int audit_fchmod(int fd,mode_t m) {
    if(deny_chmod) {errno=EPERM;return -1;} return fchmod(fd,m);
}
static int audit_ftruncate(int fd,off_t length) {
    struct stat st;assert(fstat(fd,&st)==0 && (st.st_mode&0777)==0644);
    if(deny_truncate) {errno=ENOSPC;return -1;} return ftruncate(fd,length);
}
static FILE *audit_fdopen(int fd,const char *mode) {
    if(deny_fdopen) {errno=EMFILE;return NULL;} return fdopen(fd,mode);
}
static int audit_fclose(FILE *fp) {
    int rc=fclose(fp);if(fail_close){errno=ENOSPC;return EOF;}return rc;
}
static char *nvram_safe_get(const char *k) {
    if(!strcmp(k,"lan_ipaddr")) return "192.168.6.1";
    if(!strcmp(k,"lan_netmask")) return "255.255.255.0";
    if(!strcmp(k,"lan_domain")) return "home.invalid";
    if(!strcmp(k,"dhcp_start")) return "192.168.6.10";
    if(!strcmp(k,"dhcp_end")) return "192.168.6.200";
    if(!strcmp(k,"dhcp_staticmac_x0")) return "001122334455";
    if(!strcmp(k,"dhcp_staticip_x0")) return "192.168.6.50";
    if(!strcmp(k,"dhcp_staticname_x0")) return "testbox";
    if(!strcmp(k,"wanx_domain")) return "isp.invalid";
    if(!strcmp(k,"wanx_dns")) return "192.0.2.53";
    return "";
}
static int nvram_get_int(const char *k) {
    if(!strcmp(k,"dhcp_lease"))return 86400;
    if(!strcmp(k,"dhcp_static_x") || !strcmp(k,"dhcp_staticnum_x"))return 1;
    return 0;
}
static int nvram_match(const char *k,const char *v){return !strcmp(k,"dhcp_enable_x") && !strcmp(v,"1");}
static int nvram_invmatch(const char *k,const char *v){return !nvram_match(k,v);}
static int nvram_set(const char *k,const char *v){return 0;}
static in_addr_t inet_addr_safe(const char *s){return inet_addr(s);}
static int is_same_subnet(const char*a,const char*b,const char*m){return (inet_addr(a)&inet_addr(m))==(inet_addr(b)&inet_addr(m));}
static int is_valid_hostname(const char*s){return *s!=0;}
static char *sanity_hostname(char*s){return s;}
static int is_valid_ipv4(const char *s){struct in_addr a;return inet_pton(AF_INET,s,&a)==1;}
static int mkdir_if_none(const char *s,const char *m){return 1;}
static int update_hosts_router(const char*s){return 0;}
static int file_lock(const char *tag){return -1;}
static void file_unlock(int fd){}
static char *next_word(char *out,char *s) {
    int i=0;while(*s && isspace((unsigned char)*s))s++;if(!*s)return NULL;
    while(*s && !isspace((unsigned char)*s)){if(i<255)out[i++]=*s;s++;}out[i]=0;return s;
}
#define foreach(word, list, next) for(next=(char *)(list); (next=next_word(word,next))!=NULL; )
static int doSystem(const char *fmt,...) {
    struct stat st;assert(!strcmp(fmt,"/usr/bin/dnsmasq.sh")||!strcmp(fmt,"/usr/bin/dnsmasq.sh --launch"));
    /* Validation must see newly generated, owner-write-only servers input. */
    assert(stat(map_path("/tmp/dnsmasq.servers"),&st)==0 && (st.st_mode&0777)==0644);
    validation_calls++;return fail_validation;
}
static int eval(const char *s,...){assert(!strcmp(s,"/usr/sbin/dnsmasq"));exec_calls++;return 0;}
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define SYS_USER_NOBODY "nobody"
#define IFNAME_BR "br0"
#define DHCPD_STATIC_MAX 64
#define DHCPD_MULTIMAC_MAX 8
#define DHCPD_RANGE_DEF_TAG "lan"
#define DHCPD_HOSTS_DIR "/etc/dnsmasq/dhcp"
#define DHCPD_LEASE_FILE "/tmp/dnsmasq.leases"
#define DNS_RESOLV_CONF "/etc/resolv.conf"
#define DNS_SERVERS_FILE "/tmp/dnsmasq.servers"
#define DNS_RELAY_CACHE_MAX 1024
#define DNS_RELAY_QUERIES_MAX 150
#define BOARD_NUM_USB_PORTS 0
#define open audit_open
#define fstat audit_fstat
#define fchmod audit_fchmod
#define ftruncate audit_ftruncate
#define fdopen audit_fdopen
#define fclose audit_fclose
'''
        code += text[text.index('static FILE *\nopen_dns_config('):
                     text.index('static void\nsimple_dhcp_range(')]
        code += text[text.index('struct ip4_items_t {'):text.index('static int\nfill_static_ethers(')]
        for name in ('simple_dhcp_range', 'chk_valid_subnet_pool', 'fill_static_ethers',
                     'fill_dnsmasq_servers', 'is_dhcpd_enabled', 'start_dns_dhcpd'):
            code += function(text, name) + '\n'
        code += r'''
#undef open
#undef fstat
#undef fchmod
#undef ftruncate
#undef fdopen
#undef fclose
static void write_old(const char *p) {
    FILE*f=fopen(map_path(p),"w");assert(f);assert(fputs("old-data",f)>=0 && !fclose(f));
    assert(!chmod(map_path(p),0666));
}
static void check_old(const char *p) {
    char b[16]={0};FILE*f=fopen(map_path(p),"r");assert(f);
    assert(fread(b,1,8,f)==8 && !memcmp(b,"old-data",8));fclose(f);
}
static void check_mode(const char *p) {
    struct stat st;assert(!stat(map_path(p),&st) && (st.st_mode&0777)==0644);
}
int main(int argc,char **argv) {
    FILE *fp;struct stat st;char target[4096],linkpath[4096];int rc;
    assert(argc==3);root=argv[2];umask(0);
    if(!strcmp(argv[1],"create")) {
        fp=open_dns_config("/etc/helper.conf",1);assert(fp);assert(!fstat(fileno(fp),&st));
        assert((st.st_mode&0777)==0644);assert(fputs("new",fp)>=0 && !fclose(fp));
    } else if(!strcmp(argv[1],"existing") || !strcmp(argv[1],"preserve") ||
              !strcmp(argv[1],"chmod_fail") || !strcmp(argv[1],"truncate_fail") ||
              !strcmp(argv[1],"foreign_owner")) {
        write_old("/etc/helper.conf");deny_chmod=!strcmp(argv[1],"chmod_fail");
        deny_truncate=!strcmp(argv[1],"truncate_fail");foreign_owner=!strcmp(argv[1],"foreign_owner");
        fp=open_dns_config("/etc/helper.conf",strcmp(argv[1],"preserve")!=0);
        if(deny_chmod || deny_truncate || foreign_owner){assert(!fp);check_old("/etc/helper.conf");}
        else {assert(fp);assert(!fclose(fp));check_mode("/etc/helper.conf");
              if(!strcmp(argv[1],"preserve"))check_old("/etc/helper.conf");
              else assert(!stat(map_path("/etc/helper.conf"),&st)&&st.st_size==0);}
    } else if(!strcmp(argv[1],"fdopen_fail")) {
        deny_fdopen=1;assert(!open_dns_config("/etc/helper.conf",1));
        assert(fcntl(last_fd,F_GETFD)==-1 && errno==EBADF);
    } else if(!strcmp(argv[1],"symlink") || !strcmp(argv[1],"hardlink") || !strcmp(argv[1],"fifo")) {
        write_old("/etc/target.conf");strcpy(target,map_path("/etc/target.conf"));strcpy(linkpath,map_path("/etc/helper.conf"));
        if(!strcmp(argv[1],"symlink"))assert(!symlink(target,linkpath));
        else if(!strcmp(argv[1],"hardlink"))assert(!link(target,linkpath));
        else assert(!mkfifo(linkpath,0666));
        assert(!open_dns_config("/etc/helper.conf",1));check_old("/etc/target.conf");
    } else {
        write_old("/tmp/dnsmasq.leases");write_old("/etc/resolv.conf");
        if(!strcmp(argv[1],"generate_existing")) {
            write_old("/etc/dnsmasq.conf");write_old("/etc/ethers");
            write_old("/tmp/hosts.static");write_old("/tmp/dnsmasq.servers");
            write_old("/etc/dnsmasq/dhcp/dhcp-hosts.rc");
        }
        fail_validation=!strcmp(argv[1],"validation_fail");fail_close=!strcmp(argv[1],"close_fail");
        if(!strcmp(argv[1],"static_symlink") || !strcmp(argv[1],"servers_symlink") || !strcmp(argv[1],"main_symlink")) {
            const char *name=!strcmp(argv[1],"static_symlink")?"/etc/ethers":
                             !strcmp(argv[1],"servers_symlink")?"/tmp/dnsmasq.servers":"/etc/dnsmasq.conf";
            write_old("/etc/target.conf");strcpy(target,map_path("/etc/target.conf"));strcpy(linkpath,map_path(name));
            assert(!symlink(target,linkpath));
        }
        rc=start_dns_dhcpd(0);
        if(fail_validation || fail_close || strstr(argv[1],"symlink")) {
            assert(rc!=0 && exec_calls==0);
            if(strstr(argv[1],"symlink"))check_old("/etc/target.conf");
        } else {
            assert(rc==0 && exec_calls==0 && validation_calls==1);
            check_mode("/etc/dnsmasq.conf");check_mode("/etc/ethers");check_mode("/tmp/hosts.static");
            check_mode("/etc/dnsmasq/dhcp/dhcp-hosts.rc");check_mode("/tmp/dnsmasq.servers");
            check_mode("/tmp/dnsmasq.leases");check_mode("/etc/resolv.conf");
            check_old("/tmp/dnsmasq.leases");check_old("/etc/resolv.conf");
        }
    }
    return 0;
}
'''
        root = Path(cls.tmp.name)
        (root/'driver.c').write_text(code)
        cls.binary = root/'driver'
        completed = subprocess.run(['clang', '-g', '-fsanitize=address,undefined',
                                    '-Werror=implicit-function-declaration', str(root/'driver.c'),
                                    '-o', str(cls.binary)], text=True, capture_output=True)
        if completed.returncode:
            raise AssertionError(completed.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def case(self, name):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'etc/dnsmasq/dhcp').mkdir(parents=True)
            (root/'tmp').mkdir()
            subprocess.run([str(self.binary), name, str(root)], check=True, timeout=5)

    def test_real_helper_handles_permissions_and_nonregular_paths(self):
        for case in ('create', 'existing', 'preserve', 'chmod_fail', 'truncate_fail',
                     'foreign_owner', 'fdopen_fail', 'symlink', 'hardlink', 'fifo'):
            with self.subTest(case=case):
                self.case(case)

    def test_actual_generation_and_launch_failure_paths(self):
        for case in ('generate', 'generate_existing', 'validation_fail', 'close_fail',
                     'static_symlink', 'servers_symlink', 'main_symlink'):
            with self.subTest(case=case):
                self.case(case)


if __name__ == '__main__':
    unittest.main()
