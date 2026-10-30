/* Private expanded startup configuration transactions. GPL2 or later. */
#ifndef NO_LARGEFILE
#define _LARGEFILE_SOURCE 1
#define _FILE_OFFSET_BITS 64
#endif
#define _GNU_SOURCE
#include "conf_snapshot.h"
#include "snapshot_sha256.h"
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdint.h>
#include <errno.h>
#include <limits.h>
#include <dirent.h>
#include <time.h>

enum { SNAP_FILE=1, SNAP_DIRECTORY=2, SNAP_SCRIPT=3 };
struct snap_meta { uint64_t value[9]; };
struct snap_record {
  unsigned int kind, overlay, ordinal, parent, depth;
  char *path, *real, *filters;
  struct snap_meta target, leaf;
  unsigned char digest[32];
  struct snapshot_sha256 running;
  size_t bytes;
  int fd;
};
struct snap_buffer { unsigned char *data; size_t length, capacity, position; };
static struct {
  int mode, managed, directory, flat, sealed;
  char *path, *overlay, *candidate;
  unsigned char token[16], flat_hash[32];
  size_t flat_bytes;
  struct snap_meta flat_meta, ticket_meta, directory_meta;
  struct snap_record records[CONF_SNAPSHOT_RECORDS];
  unsigned int count;
  struct snapshot_sha256 flat_running;
  unsigned char flat_buffer[4096];
  size_t flat_buffered;
  struct conf_script_budget *budget;
  FILE *stream;
} snap = { .directory=-1, .flat=-1 };

static int snap_fail(const char **error, const char *reason) { *error=reason; return 0; }
static int snap_clock(struct conf_script_budget *budget)
{
  struct timespec now;
  if(clock_gettime(CLOCK_MONOTONIC,&now))return 0;
  budget->deadline=(long long)now.tv_sec*1000+now.tv_nsec/1000000+CONF_SCRIPT_TOTAL_MS;
  return 1;
}
static void meta_from(struct snap_meta *m,const struct stat *s)
{
  m->value[0]=s->st_dev;m->value[1]=s->st_ino;m->value[2]=s->st_mode;
  m->value[3]=s->st_uid;m->value[4]=s->st_gid;m->value[5]=s->st_nlink;
  m->value[6]=s->st_size;m->value[7]=s->st_mtime;m->value[8]=s->st_ctime;
}
static int meta_equal(const struct snap_meta *a,const struct snap_meta *b,int directory)
{
  unsigned int i;
  for(i=0;i<(directory?5U:9U);i++)if(a->value[i]!=b->value[i])return 0;
  return 1;
}
static int text_path(const char *path)
{
  const unsigned char *p=(const unsigned char *)path;
  if(!path||!*path||strlen(path)>=PATH_MAX)return 0;
  for(;*p;p++)if(*p<32||*p==127)return 0;
  return 1;
}
static char *absolute_path(const char *path)
{
  char cwd[PATH_MAX],full[PATH_MAX];
  if(!text_path(path))return NULL;
  if(path[0]=='/')return strdup(path);
  if(!getcwd(cwd,sizeof(cwd))||snprintf(full,sizeof(full),"%s/%s",cwd,path)>=(int)sizeof(full))return NULL;
  return strdup(full);
}
static int secure_directory(const char *path)
{
  char copy[PATH_MAX],*part,*next;struct stat st;int fd,child;
  if(!text_path(path)||path[0]!='/')return -1;
  strcpy(copy,path);fd=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
  if(fd<0)return -1;
  part=copy+1;
  while(*part){
    next=strchr(part,'/');if(next)*next=0;
    if(!*part||!strcmp(part,".")||!strcmp(part,"..")){close(fd);return -1;}
    child=openat(fd,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);close(fd);
    if(child<0)return -1;
    if(fstat(child,&st)||(st.st_uid!=0&&st.st_uid!=geteuid())||
       ((st.st_mode&022)&&!(st.st_mode&S_ISVTX))){close(child);return -1;}
    fd=child;if(!next)break;part=next+1;
    if(!*part){close(fd);return -1;}
  }
  return fd;
}
static int open_directory(const char *path,int create)
{
  char copy[PATH_MAX],*leaf;struct stat st;int parent,fd;
  if(!text_path(path)||path[0]!='/')return -1;
  strcpy(copy,path);leaf=strrchr(copy,'/');
  if(!leaf||!leaf[1]||strlen(leaf+1)>255)return -1;
  *leaf++=0;parent=secure_directory(*copy?copy:"/");
  if(parent<0)return -1;
  if(create&&mkdirat(parent,leaf,0700)){close(parent);return -1;}
  fd=openat(parent,leaf,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);close(parent);
  if(fd<0)return -1;
  if(fstat(fd,&st)||st.st_uid!=geteuid()||(st.st_mode&07777)!=0700){close(fd);return -1;}
  meta_from(&snap.directory_meta,&st);
  return fd;
}
static int private_file(int directory,const char *leaf,size_t maximum,struct snap_meta *meta)
{
  struct stat st;int fd=openat(directory,leaf,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
  if(fd<0)return -1;
  if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_uid!=geteuid()||st.st_nlink!=1||
     (st.st_mode&07777)!=0400||st.st_size<0||(uint64_t)st.st_size>maximum){close(fd);return -1;}
  if(meta)meta_from(meta,&st);
  return fd;
}
static int reserve_write(int fd,const void *data,size_t size)
{
  const unsigned char *p=data;struct statvfs space;
  while(size){
    size_t chunk=size>4096?4096:size;ssize_t written;
    if(!conf_script_check(snap.budget)||fstatvfs(fd,&space)||
       (uint64_t)space.f_bavail*space.f_frsize<chunk+CONF_SNAPSHOT_HEADROOM)return 0;
    do written=write(fd,p,chunk);while(written<0&&errno==EINTR);
    if(written<=0||(size_t)written>chunk)return 0;
    p+=written;size-=(size_t)written;
  }
  return 1;
}
static int flat_write(const void *data,size_t size)
{
  const unsigned char *p=data;
  while(size){
    size_t take=sizeof(snap.flat_buffer)-snap.flat_buffered;if(take>size)take=size;
    memcpy(snap.flat_buffer+snap.flat_buffered,p,take);snap.flat_buffered+=take;p+=take;size-=take;
    if(snap.flat_buffered==sizeof(snap.flat_buffer)){
      if(!reserve_write(snap.flat,snap.flat_buffer,snap.flat_buffered))return 0;
      snap.flat_buffered=0;
    }
  }
  return 1;
}
static int seal_file(int fd,struct snap_meta *meta)
{
  struct stat st;int ok=0;
  if(!fchmod(fd,0400)&&!fsync(fd)&&!fstat(fd,&st)&&S_ISREG(st.st_mode)&&
     st.st_uid==geteuid()&&st.st_nlink==1&&(st.st_mode&07777)==0400){
    if(meta)meta_from(meta,&st);
    ok=1;
  }
  if(close(fd))ok=0;
  return ok;
}
static int buffer_put(struct snap_buffer *b,const void *data,size_t size)
{
  size_t next;unsigned char *grown;
  if(size>CONF_SNAPSHOT_MANIFEST_BYTES-b->length)return 0;
  if(b->length+size>b->capacity){
    next=b->capacity?b->capacity:4096;
    while(next<b->length+size)next*=2;
    if(next>CONF_SNAPSHOT_MANIFEST_BYTES)next=CONF_SNAPSHOT_MANIFEST_BYTES;
    grown=realloc(b->data,next);if(!grown)return 0;b->data=grown;b->capacity=next;
  }
  memcpy(b->data+b->length,data,size);b->length+=size;return 1;
}
static int buffer_get(struct snap_buffer *b,void *data,size_t size)
{
  if(size>b->length-b->position)return 0;
  memcpy(data,b->data+b->position,size);b->position+=size;return 1;
}
static int put_number(struct snap_buffer *b,uint64_t n)
{
  unsigned char value[8];unsigned int i;
  for(i=0;i<8;i++)value[7-i]=(unsigned char)(n>>(i*8));
  return buffer_put(b,value,8);
}
static int get_number(struct snap_buffer *b,uint64_t *n)
{
  unsigned char value[8];unsigned int i;if(!buffer_get(b,value,8))return 0;
  *n=0;for(i=0;i<8;i++)*n=(*n<<8)|value[i];return 1;
}
static int put_string(struct snap_buffer *b,const char *s)
{
  size_t length=s?strlen(s):0;return put_number(b,length)&&buffer_put(b,s?s:"",length);
}
static int get_string(struct snap_buffer *b,char **s,size_t maximum)
{
  uint64_t n;if(!get_number(b,&n)||n>maximum||n>b->length-b->position)return 0;
  *s=malloc((size_t)n+1);if(!*s)return 0;
  if(!buffer_get(b,*s,(size_t)n)){free(*s);*s=NULL;return 0;}
  if(memchr(*s,0,(size_t)n)){free(*s);*s=NULL;return 0;}(*s)[n]=0;return 1;
}
static int put_meta(struct snap_buffer *b,const struct snap_meta *m)
{
  unsigned int i;for(i=0;i<9;i++)if(!put_number(b,m->value[i]))return 0;return 1;
}
static int get_meta(struct snap_buffer *b,struct snap_meta *m)
{
  unsigned int i;for(i=0;i<9;i++)if(!get_number(b,&m->value[i]))return 0;return 1;
}
static struct snap_record *new_record(unsigned int kind,const char **error)
{
  struct snap_record *r;
  if(snap.count==CONF_SNAPSHOT_RECORDS){snap_fail(error,"snapshot graph record limit exceeded");return NULL;}
  r=&snap.records[snap.count++];memset(r,0,sizeof(*r));r->kind=kind;r->fd=-1;return r;
}
static int describe_path(struct snap_record *r,const char *path,int fd)
{
  struct stat st;char resolved[PATH_MAX];char *logical=absolute_path(path);
  if(!logical||!realpath(path,resolved)||fstat(fd,&st)){free(logical);return 0;}
  r->path=logical;r->real=strdup(resolved);meta_from(&r->target,&st);
  if(!r->real||lstat(path,&st))return 0;
  meta_from(&r->leaf,&st);return 1;
}
static void input_bytes(FILE *stream,const void *data,size_t size)
{
  unsigned int i;int fd=fileno(stream);
  if(fd<0)return;
  for(i=0;i<snap.count;i++)if(snap.records[i].kind==SNAP_FILE&&snap.records[i].fd==fd){
    snapshot_sha_update(&snap.records[i].running,data,size);snap.records[i].bytes+=size;return;
  }
}
int conf_snapshot_mode(void){return snap.mode;}
int conf_snapshot_managed(void){return snap.mode&&snap.managed;}
const char *conf_snapshot_overlay(const char *logical)
{
  char *path;int match;
  if(snap.mode!=CONF_SNAPSHOT_CAPTURE||!snap.overlay)return logical;
  path=absolute_path(logical);if(!path)return logical;
  match=!strcmp(path,snap.overlay);free(path);
  return match?snap.candidate:logical;
}
int conf_snapshot_input_begin(const char *logical,FILE *stream,const char **error)
{
  struct snap_record *r;const char *actual=conf_snapshot_overlay(logical);
  if(snap.mode!=CONF_SNAPSHOT_CAPTURE)return 1;
  r=new_record(SNAP_FILE,error);if(!r)return 0;
  if(!describe_path(r,actual,fileno(stream)))return snap_fail(error,"cannot bind snapshot source identity");
  if(actual!=logical){
    char *p=absolute_path(logical);if(!p)return snap_fail(error,"invalid snapshot logical overlay");
    free(r->path);r->path=p;r->overlay=1;
  }
  if(!S_ISREG((mode_t)r->target.value[2])||r->target.value[6]>CONF_CONFIG_MAX_BYTES)
    return snap_fail(error,"snapshot input is not bounded regular text");
  r->fd=fileno(stream);snapshot_sha_init(&r->running);return 1;
}
int conf_snapshot_input_end(FILE *stream,const char **error)
{
  unsigned int i;struct stat st;struct snap_meta current;int fd=fileno(stream);
  if(snap.mode!=CONF_SNAPSHOT_CAPTURE)return 1;
  for(i=0;i<snap.count;i++)if(snap.records[i].kind==SNAP_FILE&&snap.records[i].fd==fd){
    struct snap_record *r=&snap.records[i];
    if(fstat(fd,&st))return snap_fail(error,"snapshot input stat failed");
    meta_from(&current,&st);
    if(!meta_equal(&r->target,&current,0)||r->bytes!=r->target.value[6])
      return snap_fail(error,"snapshot input changed during capture");
    snapshot_sha_final(&r->running,r->digest);r->fd=-1;return 1;
  }
  return snap_fail(error,"snapshot input tracking mismatch");
}
int conf_snapshot_line(const char *line,const char **error)
{
  size_t length;
  if(snap.mode!=CONF_SNAPSHOT_CAPTURE)return 1;
  length=strlen(line);
  if(length+1>CONF_SNAPSHOT_FLAT_BYTES-snap.flat_bytes||
     !flat_write(line,length)||!flat_write("\n",1))
    return snap_fail(error,"snapshot expansion exceeds space or byte budget");
  snapshot_sha_update(&snap.flat_running,line,length);snapshot_sha_update(&snap.flat_running,"\n",1);
  snap.flat_bytes+=length+1;return 1;
}
int conf_snapshot_script(unsigned int ordinal,unsigned int parent,unsigned int depth,const char *command,const char **error)
{
  struct snap_record *r;
  if(snap.mode!=CONF_SNAPSHOT_CAPTURE)return 1;
  r=new_record(SNAP_SCRIPT,error);if(!r)return 0;
  r->ordinal=ordinal;r->parent=parent;r->depth=depth;
  snapshot_sha_init(&r->running);snapshot_sha_update(&r->running,command,strlen(command));
  snapshot_sha_final(&r->running,r->digest);return 1;
}

static int suffix_matches(const char *name,const char *suffix,size_t length)
{
  size_t n=strlen(name);return n>length&&!memcmp(name+n-length,suffix,length);
}
static int select_name(const char *name,const char *filters)
{
  const char *p=filters?filters:"",*end;size_t n=strlen(name);int required=0,matched=0;
  if(!n||name[0]=='.'||name[n-1]=='~'||(name[0]=='#'&&name[n-1]=='#'))return 0;
  while(*p){
    end=strchr(p,'\n');if(!end||end==p+1||(*p!='M'&&*p!='I'))return -1;
    if(*p=='M'){required=1;if(suffix_matches(name,p+1,(size_t)(end-p-1)))matched=1;}
    else if(suffix_matches(name,p+1,(size_t)(end-p-1)))return 0;
    p=end+1;
  }
  return !required||matched;
}
static int name_order(const void *a,const void *b)
{
  return strcmp(*(char *const *)a,*(char *const *)b);
}
static int directory_hash(const char *directory,const char *filters,unsigned int *entries,
                           unsigned int *selected,unsigned char digest[32])
{
  DIR *stream;struct dirent *entry;char *names[CONF_CONFIG_MAX_FILES];
  struct snapshot_sha256 hash;unsigned int count=0,i;int ok=0;
  stream=opendir(directory);if(!stream)return 0;
  while(1){
    char full[PATH_MAX];struct stat st;int match;
    if(!conf_script_check(snap.budget))goto out;
    errno=0;entry=readdir(stream);
    if(!entry){if(errno)goto out;break;}
    if(++*entries>CONF_CONFIG_MAX_DIR_ENTRIES)goto out;
    match=select_name(entry->d_name,filters);if(match<0)goto out;if(!match)continue;
    if(snprintf(full,sizeof(full),"%s/%s",directory,entry->d_name)>=(int)sizeof(full)||
       !text_path(full)||stat(full,&st))goto out;
    if(!S_ISREG(st.st_mode))continue;
    if(++*selected>CONF_CONFIG_MAX_FILES||count==CONF_CONFIG_MAX_FILES)goto out;
    names[count]=strdup(entry->d_name);if(!names[count])goto out;count++;
  }
  qsort(names,count,sizeof(names[0]),name_order);snapshot_sha_init(&hash);
  for(i=0;i<count;i++){
    size_t n=strlen(names[i]);unsigned char length[2]={(unsigned char)(n>>8),(unsigned char)n};
    snapshot_sha_update(&hash,length,2);snapshot_sha_update(&hash,names[i],n);
  }
  snapshot_sha_final(&hash,digest);ok=1;
out:
  if(closedir(stream))ok=0;
  for(i=0;i<count;i++)free(names[i]);
  return ok;
}
int conf_snapshot_directory(const char *directory,const char *filters,const char **error)
{
  struct snap_record *r;int fd;unsigned int entries=0,selected=0;
  if(snap.mode!=CONF_SNAPSHOT_CAPTURE)return 1;
  r=new_record(SNAP_DIRECTORY,error);if(!r)return 0;
  fd=open(directory,O_RDONLY|O_DIRECTORY|O_NONBLOCK|O_CLOEXEC);if(fd<0)return snap_fail(error,"snapshot directory open failed");
  if(!describe_path(r,directory,fd)){close(fd);return snap_fail(error,"snapshot directory identity failed");}
  if(close(fd))return snap_fail(error,"snapshot directory close failed");
  r->filters=strdup(filters?filters:"");
  if(!r->filters||strlen(r->filters)>CONF_SCRIPT_LINE_BYTES||
     !directory_hash(directory,r->filters,&entries,&selected,r->digest))
    return snap_fail(error,"snapshot directory listing exceeds its budget");
  return 1;
}
static int hash_descriptor(int fd,size_t maximum,unsigned char digest[32],size_t *size)
{
  struct snapshot_sha256 hash;unsigned char data[4096];ssize_t n;
  *size=0;snapshot_sha_init(&hash);
  while(1){
    if(!conf_script_check(snap.budget))return 0;
    do n=read(fd,data,sizeof(data));while(n<0&&errno==EINTR);
    if(n<0||(n>0&&(size_t)n>maximum-*size))return 0;
    if(!n)break;
    snapshot_sha_update(&hash,data,(size_t)n);*size+=(size_t)n;
  }
  snapshot_sha_final(&hash,digest);return 1;
}
int conf_snapshot_input_alias(const char *logical,uint64_t observed_device,uint64_t observed_inode,const char **error)
{
  const char *actual=conf_snapshot_overlay(logical);
  struct snap_record current,after,*same=NULL,*source=NULL,*record;
  unsigned char digest[32];unsigned int i;size_t size=0,total=0;
  int fd=-1,ok=0;
  if(snap.mode!=CONF_SNAPSHOT_CAPTURE)return 1;
  memset(&current,0,sizeof(current));memset(&after,0,sizeof(after));
  fd=open(actual,O_RDONLY|O_NONBLOCK|O_CLOEXEC);
  if(fd<0||!describe_path(&current,actual,fd))goto out;
  if(actual!=logical){
    char *path=absolute_path(logical);if(!path)goto out;
    free(current.path);current.path=path;current.overlay=1;
  }
  if(!S_ISREG((mode_t)current.target.value[2])||current.target.value[6]>CONF_CONFIG_MAX_BYTES||
     current.target.value[0]!=observed_device||current.target.value[1]!=observed_inode)goto out;
  for(i=0;i<snap.count;i++)if(snap.records[i].kind==SNAP_FILE){
    record=&snap.records[i];
    if(record->target.value[0]==current.target.value[0]&&
       record->target.value[1]==current.target.value[1])source=record;
    if(!strcmp(record->path,current.path))same=record;
    if(record->target.value[6]>CONF_CONFIG_TOTAL_BYTES-total)goto out;
    total+=(size_t)record->target.value[6];
  }
  /* A stale pre-open stat must not cause a file which was never captured to
   * disappear behind dnsmasq's inode deduplication. */
  if(!source)goto out;
  if(same){
    if(strcmp(same->real,current.real)||same->overlay!=current.overlay||
       !meta_equal(&same->target,&current.target,0)||
       !meta_equal(&same->leaf,&current.leaf,0))goto out;
  }else if(snap.budget->files>=CONF_CONFIG_MAX_FILES||
           current.target.value[6]>CONF_CONFIG_TOTAL_BYTES-total)goto out;
  if(!hash_descriptor(fd,CONF_CONFIG_MAX_BYTES,digest,&size)||size!=current.target.value[6]||
     !describe_path(&after,actual,fd)||strcmp(after.real,current.real)||
     !meta_equal(&after.target,&current.target,0)||!meta_equal(&after.leaf,&current.leaf,0))goto out;
  if(same){
    /* Recursive includes may reach their own still-open record. input_end and
     * finish bind that record's complete parsed SHA before a manifest exists. */
    if(same->fd<0&&memcmp(same->digest,digest,32))goto out;
  }else{
    record=new_record(SNAP_FILE,error);if(!record)goto out;
    *record=current;current.path=current.real=NULL;record->kind=SNAP_FILE;
    record->fd=-1;record->bytes=size;
    memcpy(record->digest,digest,32);snap.budget->files++;
  }
  ok=1;
out:
  if(fd>=0&&close(fd))ok=0;
  free(current.path);free(current.real);free(after.path);free(after.real);
  return ok?1:snap_fail(error,"snapshot duplicate source identity or SHA256 changed");
}
static int verify_graph(int promote)
{
  unsigned int i,entries=0,selected=0,files=0,overlays=0,scripts=0;
  size_t total=0;
  for(i=0;i<snap.count;i++){
    struct snap_record *r=&snap.records[i],current;int fd;struct stat st;
    unsigned char digest[32];size_t size=0;
    memset(&current,0,sizeof(current));current.fd=-1;
    if(r->kind==SNAP_SCRIPT){
      if(++scripts>CONF_SCRIPT_MAX_CALLS||r->ordinal!=scripts||r->depth<1||
         r->depth>CONF_SCRIPT_MAX_DEPTH||r->parent>=r->ordinal)return 0;
      continue;
    }
    if(!r->path||r->path[0]!='/'||!r->real||!text_path(r->path)||!text_path(r->real))return 0;
    {
      const char *input=(r->overlay&&snap.mode==CONF_SNAPSHOT_CAPTURE&&!promote)?snap.candidate:r->path;
      fd=open(input,O_RDONLY|O_NONBLOCK|O_CLOEXEC);
      if(fd>=0&&!describe_path(&current,input,fd)){close(fd);free(current.path);free(current.real);return 0;}
    }
    if(fd<0)return 0;
    if(r->kind==SNAP_FILE){
      if(++files>CONF_CONFIG_MAX_FILES||!S_ISREG((mode_t)current.target.value[2])||
         current.target.value[6]>CONF_CONFIG_MAX_BYTES||
         r->target.value[6]>CONF_CONFIG_MAX_BYTES||
         current.target.value[6]>CONF_CONFIG_TOTAL_BYTES-total)goto bad;
      total+=(size_t)current.target.value[6];
      if(r->overlay&&++overlays>1)goto bad;
      if(!(promote&&r->overlay)&&
         (strcmp(current.real,r->real)||!meta_equal(&current.target,&r->target,0)||
          !meta_equal(&current.leaf,&r->leaf,0)))goto bad;
      if(!hash_descriptor(fd,CONF_CONFIG_MAX_BYTES,digest,&size)||size!=current.target.value[6]||
         memcmp(digest,r->digest,32)||fstat(fd,&st))goto bad;
      {struct snap_meta after;meta_from(&after,&st);if(!meta_equal(&after,&current.target,0))goto bad;}
      if(promote&&r->overlay){
        free(r->real);r->real=current.real;current.real=NULL;
        r->target=current.target;r->leaf=current.leaf;
      }
    }else if(r->kind==SNAP_DIRECTORY){
      if(!S_ISDIR((mode_t)current.target.value[2])||r->overlay||!r->filters||
         strcmp(current.real,r->real)||!meta_equal(&current.target,&r->target,1)||
         !meta_equal(&current.leaf,&r->leaf,1)||
         !directory_hash(r->path,r->filters,&entries,&selected,digest)||memcmp(digest,r->digest,32))goto bad;
    }else goto bad;
    if(close(fd)){free(current.path);free(current.real);return 0;}
    free(current.path);free(current.real);continue;
bad:
    close(fd);free(current.path);free(current.real);return 0;
  }
  return overlays==1;
}

static int write_manifest(int state)
{
  static const unsigned char magic[16]="DNS-SNAPSHOT-V1";
  struct snap_buffer b={0};struct snapshot_sha256 hash;unsigned char digest[32];
  unsigned int i;int fd=-1,ok=0;const char *leaf=state==1?"manifest":"manifest.next";
  if(!buffer_put(&b,magic,16)||!put_number(&b,1)||!put_number(&b,(uint64_t)state)||
     !put_number(&b,(uint64_t)snap.managed)||!put_number(&b,snap.count)||
     !put_number(&b,snap.flat_bytes)||!buffer_put(&b,snap.token,16)||
     !buffer_put(&b,snap.flat_hash,32)||!put_string(&b,snap.path)||!put_string(&b,snap.overlay)||
     !put_meta(&b,&snap.directory_meta)||!put_meta(&b,&snap.flat_meta)||!put_meta(&b,&snap.ticket_meta))goto out;
  for(i=0;i<snap.count;i++){
    struct snap_record *r=&snap.records[i];
    if(!put_number(&b,r->kind)||!put_number(&b,r->overlay)||!put_number(&b,r->ordinal)||
       !put_number(&b,r->parent)||!put_number(&b,r->depth)||!put_string(&b,r->path)||
       !put_string(&b,r->real)||!put_string(&b,r->filters)||!put_meta(&b,&r->target)||
       !put_meta(&b,&r->leaf)||!buffer_put(&b,r->digest,32))goto out;
  }
  snapshot_sha_init(&hash);snapshot_sha_update(&hash,b.data,b.length);snapshot_sha_final(&hash,digest);
  if(!buffer_put(&b,digest,32))goto out;
  fd=openat(snap.directory,leaf,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  if(fd<0||!reserve_write(fd,b.data,b.length))goto out;
  {int current=fd;fd=-1;if(!seal_file(current,NULL))goto out;}
  if(state==2&&renameat(snap.directory,leaf,snap.directory,"manifest"))goto out;
  if(fsync(snap.directory))goto out;
  ok=1;
out:
  if(fd>=0)close(fd);
  if(!ok&&state==2)unlinkat(snap.directory,leaf,0);
  free(b.data);return ok;
}
static int read_manifest(int expected_state)
{
  static const unsigned char magic[16]="DNS-SNAPSHOT-V1";
  struct snap_buffer b={0};struct snap_meta current_dir=snap.directory_meta;
  struct snapshot_sha256 hash;unsigned char digest[32],prefix[16];uint64_t n;
  char *path=NULL;unsigned int i;int fd=-1,ok=0;struct stat st;
  fd=private_file(snap.directory,"manifest",CONF_SNAPSHOT_MANIFEST_BYTES,NULL);
  if(fd<0||fstat(fd,&st)||st.st_size<32)goto out;
  b.length=b.capacity=(size_t)st.st_size;b.data=malloc(b.length);if(!b.data)goto out;
  for(i=0;i<b.length;){
    ssize_t count=read(fd,b.data+i,b.length-i);
    if(count<0&&errno==EINTR)continue;
    if(count<=0)goto out;
    i+=(unsigned int)count;
  }
  if(close(fd)){fd=-1;goto out;}fd=-1;
  b.length-=32;snapshot_sha_init(&hash);snapshot_sha_update(&hash,b.data,b.length);snapshot_sha_final(&hash,digest);
  if(memcmp(digest,b.data+b.length,32)||!buffer_get(&b,prefix,16)||memcmp(prefix,magic,16)||
     !get_number(&b,&n)||n!=1||!get_number(&b,&n)||n!=(unsigned int)expected_state||
     !get_number(&b,&n)||n!=(unsigned int)snap.managed||
     !get_number(&b,&n)||!n||n>CONF_SNAPSHOT_RECORDS)goto out;
  snap.count=(unsigned int)n;
  if(!get_number(&b,&n)||n>CONF_SNAPSHOT_FLAT_BYTES)goto out;
  snap.flat_bytes=(size_t)n;
  if(!buffer_get(&b,snap.token,16)||!buffer_get(&b,snap.flat_hash,32)||
     !get_string(&b,&path,PATH_MAX-1)||strcmp(path,snap.path)||
     !get_string(&b,&snap.overlay,PATH_MAX-1)||!text_path(snap.overlay)||snap.overlay[0]!='/'||
     !get_meta(&b,&snap.directory_meta)||!meta_equal(&current_dir,&snap.directory_meta,1)||
     !get_meta(&b,&snap.flat_meta)||!get_meta(&b,&snap.ticket_meta))goto out;
  for(i=0;i<snap.count;i++){
    struct snap_record *r=&snap.records[i];r->fd=-1;
    if(!get_number(&b,&n)||n<1||n>3)goto out;
    r->kind=(unsigned int)n;
    if(!get_number(&b,&n)||n>1)goto out;
    r->overlay=(unsigned int)n;
    if(!get_number(&b,&n)||n>CONF_SCRIPT_MAX_CALLS)goto out;
    r->ordinal=(unsigned int)n;
    if(!get_number(&b,&n)||n>CONF_SCRIPT_MAX_CALLS)goto out;
    r->parent=(unsigned int)n;
    if(!get_number(&b,&n)||n>CONF_SCRIPT_MAX_DEPTH)goto out;
    r->depth=(unsigned int)n;
    if(!get_string(&b,&r->path,PATH_MAX-1)||!get_string(&b,&r->real,PATH_MAX-1)||
       !get_string(&b,&r->filters,CONF_SCRIPT_LINE_BYTES)||!get_meta(&b,&r->target)||
       !get_meta(&b,&r->leaf)||!buffer_get(&b,r->digest,32))goto out;
    if(r->overlay&&(r->kind!=SNAP_FILE||strcmp(r->path,snap.overlay)))goto out;
    if(r->kind==SNAP_SCRIPT&&(r->overlay||*r->path||*r->real||*r->filters))goto out;
  }
  if(b.position!=b.length)goto out;
  ok=1;
out:
  if(fd>=0)close(fd);
  free(path);free(b.data);return ok;
}
static int parse_ticket(const char *text,unsigned char token[16])
{
  unsigned int i;
  if(!text||strlen(text)!=32)return 0;
  for(i=0;i<16;i++){
    int a=text[2*i],b=text[2*i+1];
    if(!((a>='0'&&a<='9')||(a>='a'&&a<='f'))||!((b>='0'&&b<='9')||(b>='a'&&b<='f')))return 0;
    token[i]=(unsigned char)(((a<='9'?a-'0':a-'a'+10)<<4)|(b<='9'?b-'0':b-'a'+10));
  }
  return 1;
}
static int create_ticket(void)
{
  static const char hex[]="0123456789abcdef";char data[33];unsigned int i;int fd,random;
  random=open("/dev/urandom",O_RDONLY|O_CLOEXEC);if(random<0)return 0;
  for(i=0;i<16;){
    ssize_t n=read(random,snap.token+i,16-i);
    if(n<0&&errno==EINTR)continue;
    if(n<=0){close(random);return 0;}i+=(unsigned int)n;
  }
  if(close(random))return 0;
  for(i=0;i<16;i++){data[2*i]=hex[snap.token[i]>>4];data[2*i+1]=hex[snap.token[i]&15];}data[32]='\n';
  fd=openat(snap.directory,"ticket",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
  if(fd<0)return 0;
  if(!reserve_write(fd,data,sizeof(data))){close(fd);return 0;}
  return seal_file(fd,&snap.ticket_meta);
}
static int verify_ticket(const unsigned char expected[16])
{
  char data[34];unsigned char token[16];struct snap_meta meta;int fd;ssize_t size,extra;
  fd=private_file(snap.directory,"ticket",33,&meta);if(fd<0)return 0;
  do size=read(fd,data,33);while(size<0&&errno==EINTR);
  do extra=read(fd,data+33,1);while(extra<0&&errno==EINTR);
  if(close(fd)||size!=33||extra||data[32]!='\n')return 0;
  data[32]=0;
  return parse_ticket(data,token)&&!memcmp(token,expected,16)&&!memcmp(token,snap.token,16)&&
    meta_equal(&meta,&snap.ticket_meta,0);
}
static int open_flat(void)
{
  unsigned char digest[32];struct snap_meta meta;size_t size;int fd;
  fd=private_file(snap.directory,"flat.conf",CONF_SNAPSHOT_FLAT_BYTES,&meta);if(fd<0)return 0;
  if(meta.value[6]!=snap.flat_bytes||!meta_equal(&meta,&snap.flat_meta,0)||
     !hash_descriptor(fd,CONF_SNAPSHOT_FLAT_BYTES,digest,&size)||size!=snap.flat_bytes||
     memcmp(digest,snap.flat_hash,32)||lseek(fd,0,SEEK_SET)!=0){close(fd);return 0;}
  snap.stream=fdopen(fd,"r");if(!snap.stream){close(fd);return 0;}
  snap.budget->trusted_flat=snap.stream;return 1;
}
static int candidate_safe(const char *path)
{
  char copy[PATH_MAX],*leaf;struct stat st;int parent,fd,ok=0;
  if(!text_path(path)||path[0]!='/')return 0;
  strcpy(copy,path);leaf=strrchr(copy,'/');if(!leaf||!leaf[1])return 0;*leaf++=0;
  parent=secure_directory(*copy?copy:"/");if(parent<0)return 0;
  if(fstat(parent,&st)||st.st_uid!=geteuid()||(st.st_mode&07777)!=0700){close(parent);return 0;}
  fd=openat(parent,leaf,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);close(parent);
  if(fd<0)return 0;
  if(!fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_uid==geteuid()&&st.st_nlink==1&&
     (st.st_mode&07777)==0600&&st.st_size>=0&&(uint64_t)st.st_size<=CONF_CONFIG_MAX_BYTES)ok=1;
  if(close(fd))ok=0;
  return ok;
}
int conf_snapshot_cli(int argc,char **argv,struct conf_script_budget *budget,const char **error)
{
  const char *directory=NULL,*overlay=NULL,*candidate=NULL,*ticket=NULL,*main_file=NULL;
  unsigned char expected[16];int action=0,managed=0,test=0,found=0,i;
  for(i=1;i<argc;i++)if(!strncmp(argv[i],"--snapshot-",11))found=1;
  if(!found)return 1;
  for(i=1;i<argc;i++){
    const char *a=argv[i];
    if(!strcmp(a,"--snapshot-managed")){if(managed)goto invalid;managed=1;continue;}
    if(!strcmp(a,"--test")){if(test)goto invalid;test=1;continue;}
    if(!strcmp(a,"-C")||!strcmp(a,"--conf-file")){
      if(main_file||++i==argc)goto invalid;
      main_file=argv[i];continue;
    }
    if(!strncmp(a,"--conf-file=",12)){if(main_file)goto invalid;main_file=a+12;continue;}
    if(!strcmp(a,"--snapshot-capture")||!strcmp(a,"--snapshot-use")||!strcmp(a,"--snapshot-seal")){
      if(action||++i==argc)goto invalid;
      action=!strcmp(a,"--snapshot-capture")?1:!strcmp(a,"--snapshot-use")?2:3;directory=argv[i];continue;
    }
    if(!strcmp(a,"--snapshot-overlay")){if(overlay||++i==argc)goto invalid;overlay=argv[i];continue;}
    if(!strcmp(a,"--snapshot-candidate")){if(candidate||++i==argc)goto invalid;candidate=argv[i];continue;}
    if(!strcmp(a,"--snapshot-ticket")){if(ticket||++i==argc)goto invalid;ticket=argv[i];continue;}
    goto invalid;
  }
  if(!action||!directory||(action==1?(!test||!main_file||!overlay||!candidate||ticket):
       (main_file||overlay||candidate||!ticket||(action==3&&test))))goto invalid;
  snap.budget=budget;snap.mode=action;snap.managed=managed;
  if(!snap_clock(budget))return snap_fail(error,"snapshot monotonic clock unavailable");
  snap.directory=open_directory(directory,action==1);
  if(snap.directory<0)return snap_fail(error,"snapshot directory is not fresh, private and literal");
  snap.path=realpath(directory,NULL);if(!snap.path)return snap_fail(error,"snapshot directory identity unavailable");
  if(action==1){
    snap.overlay=absolute_path(overlay);snap.candidate=absolute_path(candidate);
    if(!snap.overlay||!snap.candidate||!candidate_safe(snap.candidate))
      return snap_fail(error,"snapshot candidate is not private single-link regular data");
    if(!create_ticket())return snap_fail(error,"snapshot ticket creation failed");
    snap.flat=openat(snap.directory,"flat.conf",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(snap.flat<0)return snap_fail(error,"snapshot flat creation failed");
    snapshot_sha_init(&snap.flat_running);budget->input_bytes=input_bytes;return 1;
  }
  if(!parse_ticket(ticket,expected)||!read_manifest(action==3?1:2)||!verify_ticket(expected))
    return snap_fail(error,"snapshot manifest, state or ticket is invalid");
  if(!verify_graph(action==3))return snap_fail(error,"snapshot source graph changed");
  if(!open_flat())return snap_fail(error,"snapshot flat identity or SHA256 changed");
  if(action==3){
    if(fclose(snap.stream))return snap_fail(error,"snapshot flat close failed");
    snap.stream=NULL;budget->trusted_flat=NULL;
    if(!write_manifest(2))return snap_fail(error,"snapshot seal publication failed");
    conf_snapshot_dispose();return 2;
  }
  snap.sealed=1;return 1;
invalid:
  return snap_fail(error,"snapshot CLI contract is invalid");
}
FILE *conf_snapshot_stream(void){return snap.stream;}
int conf_snapshot_finish(const char **error)
{
  if(snap.mode==CONF_SNAPSHOT_CAPTURE){
    if(!verify_graph(0))return snap_fail(error,"snapshot source changed during capture");
    if(snap.flat_buffered&&!reserve_write(snap.flat,snap.flat_buffer,snap.flat_buffered))
      return snap_fail(error,"snapshot final output space exhausted");
    {int fd=snap.flat;snap.flat=-1;if(!seal_file(fd,&snap.flat_meta))return snap_fail(error,"snapshot flat publication failed");}
    snapshot_sha_final(&snap.flat_running,snap.flat_hash);
    if(!open_flat())return snap_fail(error,"snapshot capture flat integrity check failed");
    if(fclose(snap.stream)){snap.stream=NULL;return snap_fail(error,"snapshot capture flat close failed");}
    snap.stream=NULL;snap.budget->trusted_flat=NULL;
    if(!write_manifest(1))return snap_fail(error,"snapshot complete manifest publication failed");
  }else if(snap.mode==CONF_SNAPSHOT_USE){
    struct stat st;struct snap_meta meta;
    if(!snap.sealed||!snap.stream||fstat(fileno(snap.stream),&st)||ferror(snap.stream))
      return snap_fail(error,"snapshot verified stream is unavailable");
    meta_from(&meta,&st);
    if(!meta_equal(&meta,&snap.flat_meta,0)||!verify_graph(0))
      return snap_fail(error,"snapshot source or immutable flat changed during replay");
    if(fclose(snap.stream)){snap.stream=NULL;return snap_fail(error,"snapshot replay close failed");}
    snap.stream=NULL;snap.budget->trusted_flat=NULL;
  }
  conf_snapshot_dispose();return 1;
}
void conf_snapshot_dispose(void)
{
  unsigned int i;
  if(snap.stream)fclose(snap.stream);
  if(snap.flat>=0)close(snap.flat);
  if(snap.directory>=0)close(snap.directory);
  for(i=0;i<snap.count;i++){free(snap.records[i].path);free(snap.records[i].real);free(snap.records[i].filters);}
  free(snap.path);free(snap.overlay);free(snap.candidate);
  if(snap.budget){snap.budget->input_bytes=NULL;snap.budget->trusted_flat=NULL;}
  memset(&snap,0,sizeof(snap));snap.directory=snap.flat=-1;
}
