/* Actual public BIO API probe, dynamically linked to shipped libcrypto.
 * No OCSP server/key, fake BIO layout, daemon or hardware operation. */
#define _GNU_SOURCE
#include <openssl/bio.h>
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <syslog.h>
#include <unistd.h>

struct write_result { int input, accepted; };
static struct write_result results[128];
static unsigned int used;
static int count_fds(void)
{
    DIR *directory = opendir("/proc/self/fd");
    struct dirent *entry;
    int count = 0, own;
    if (directory == NULL) return -1;
    own = dirfd(directory);
    errno = 0;
    while ((entry = readdir(directory)) != NULL) {
        char *end;
        long number;
        if (entry->d_name[0] == '.') continue;
        number = strtol(entry->d_name, &end, 10);
        if (*end != 0) { closedir(directory); return -1; }
        if (number != own) count++;
    }
    {
        int read_error = errno, close_result = closedir(directory);
        if (read_error != 0 || close_result != 0) return -1;
    }
    return count;
}

static int record_write(BIO *bio, const char *text, int length)
{
    int accepted;
    if (used == sizeof(results) / sizeof(results[0])) return 0;
    accepted = BIO_write(bio, text, length);
    results[used].input = length;
    results[used++].accepted = accepted;
    return accepted == length;
}

int main(int argc, char **argv)
{
    BIO *a, *b;
    const char *mode;
    const char normal[] = "WARNING literal %n %s %%";
    int before, after, entry_errno = EDOM, write_errno, child_status = -1, ok = 1;
    unsigned int i;
    if (argc != 2) return 2;
    mode = argv[1];
    if (strcmp(mode,"normal") && strcmp(mode,"per-bio") && strcmp(mode,"long") &&
        strcmp(mode,"pressure") && strcmp(mode,"control") && strcmp(mode,"fork") && strcmp(mode,"empty")) return 3;
    before = count_fds();
    if (before < 3 || (a = BIO_new(BIO_s_log())) == NULL) return 4;
    b = BIO_new(BIO_s_log());
    if (b == NULL) { BIO_free(a); return 4; }
    (void)BIO_ctrl(a, BIO_CTRL_SET, LOG_LOCAL3, (void *)"bio-a");
    (void)BIO_ctrl(b, BIO_CTRL_SET, LOG_LOCAL4, (void *)"bio-b");
    errno = entry_errno;
    if (!strcmp(mode,"normal")) ok = record_write(a,normal,sizeof(normal)-1);
    else if (!strcmp(mode,"per-bio")) {
        ok = record_write(a,"WARNING ONE",11) && record_write(b,"INFO TWO",8) && record_write(a,"WARNING THREE",13);
    } else if (!strcmp(mode,"pressure")) {
        for (i=0;i<128;i++) if (!record_write(a,normal,sizeof(normal)-1)) ok=0;
    } else if (!strcmp(mode,"long")) {
        char *data = malloc(1048576);
        if (data == NULL) { BIO_free(a); BIO_free(b); return 5; }
        memset(data,'x',1048576);memcpy(data,"INFO ",5);
        ok = record_write(a,data,1048576);free(data);
    } else if (!strcmp(mode,"control")) {
        char *name = strdup("owned-name");
        if (name == NULL) { BIO_free(a); BIO_free(b); return 5; }
        (void)BIO_ctrl(a,BIO_CTRL_SET,LOG_LOCAL5,name);memset(name,'z',strlen(name));free(name);
        ok = record_write(a,"WARNING OWNED",13);
        for (i=0;i<32;i++) (void)BIO_ctrl(a,BIO_CTRL_SET,LOG_LOCAL3,(void *)"updated-name");
        ok = record_write(a,"WARNING UPDATED",15) && ok;
    } else if (!strcmp(mode,"fork")) {
        pid_t child = fork();
        if (child < 0) { BIO_free(a); BIO_free(b); return 6; }
        if (child == 0) {
            int accepted;
            (void)BIO_ctrl(a,BIO_CTRL_SET,LOG_LOCAL5,(void *)"bio-child");
            accepted = BIO_write(a,"WARNING CHILD",13);
            BIO_free(a);BIO_free(b);_exit(accepted == 13 ? 0 : 7);
        }
        if (waitpid(child,&child_status,0) != child) { BIO_free(a);BIO_free(b);return 6; }
        ok = child_status == 0 && record_write(a,"WARNING PARENT",14);
    } else ok = record_write(a,"",0);
    write_errno = errno;
    BIO_free(a);BIO_free(b);after = count_fds();
    printf("{\"schema_version\":1,\"mode\":\"%s\",\"calls\":[",mode);
    for (i=0;i<used;i++) printf("%s{\"input\":%d,\"accepted\":%d}",i?",":"",results[i].input,results[i].accepted);
    printf("],\"fd_before\":%d,\"fd_after\":%d,\"errno_entry\":%d,\"errno_after_write\":%d,\"child_status\":%d}\n",before,after,entry_errno,write_errno,child_status);
    return ok && after == before ? 0 : 8;
}
