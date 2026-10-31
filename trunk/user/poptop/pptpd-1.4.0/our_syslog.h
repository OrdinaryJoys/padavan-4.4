/* Component-local bounded logging; each PPTPd executable owns its context. */
#ifndef _PPTPD_SYSLOG_H
#define _PPTPD_SYSLOG_H
#include "../../shared/bounded_syslog.h"
extern struct padavan_log_context pptpd_log_context;
static inline void pptpd_openlog(const char *ident,int options,int facility)
{ padavan_log_open(&pptpd_log_context,ident,options,facility); }
static inline void pptpd_closelog(void)
{ padavan_log_close(&pptpd_log_context); }
static inline int pptpd_setlogmask(int mask)
{ return padavan_log_mask(&pptpd_log_context,mask); }
static inline void pptpd_syslog(int priority,const char *format,...)
{
    va_list arguments;
    va_start(arguments,format);
    padavan_log_vwrite(&pptpd_log_context,priority,format,arguments);
    va_end(arguments);
}
#define syslog_perror(s) pptpd_syslog(LOG_ERR,"%s: %s",(s),strerror(errno))
#endif
