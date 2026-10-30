#!/usr/bin/env python3
"""Exercise the actual hardware-watchdog helpers with fake syscalls only."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_httpd_regressions import function, source

class WatchdogRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        code = r'''
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#define HW_WD_TIMEOUT 60
#define WDIOC_SETTIMEOUT 1
#define WDIOC_GETTIMEOUT 2
#define WDIOC_GETBOOTSTATUS 3
#define WDIOC_KEEPALIVE 4
#define WDIOC_SETOPTIONS 5
#define WDIOS_DISABLECARD 1
static int hw_wd_fd=-1;
static int flags_seen,disables,closes,writes,logs,write_mode,timeout_mode,stop_mode;
static void logmessage(const char*s,const char*f,...){logs++;}
static int mock_open(const char*p,int f,...){flags_seen=f;return 7;}
static int mock_close(int f){closes++;return 0;}
static int mock_ioctl(int f,unsigned long request,...){
 va_list ap;int *value;va_start(ap,request);
 if(request==WDIOC_SETTIMEOUT && timeout_mode){errno=EIO;va_end(ap);return -1;}
 if(request==WDIOC_GETTIMEOUT){value=va_arg(ap,int*);*value=30;}
 if(request==WDIOC_GETBOOTSTATUS){value=va_arg(ap,int*);*value=0x20;}
 if(request==WDIOC_SETOPTIONS){value=va_arg(ap,int*);if(*value==WDIOS_DISABLECARD)disables++;if(stop_mode){errno=EBUSY;va_end(ap);return -1;}}
 va_end(ap);return 0;
}
static ssize_t mock_write(int f,const void*b,size_t n){
 writes++;
 if(write_mode==1 && writes==1){errno=EINTR;return -1;}
 if(write_mode==2){errno=EIO;return -1;}
 return n;
}
#define open mock_open
#define close mock_close
#define ioctl mock_ioctl
#define write mock_write
'''
        text=source('trunk/user/rc/watchdog.c')
        for name in ('hw_watchdog_init','hw_watchdog_feed','hw_watchdog_stop'):
            code += function(text,name)+'\n'
        code += r'''
void reset(int wm,int tm,int sm){hw_wd_fd=-1;flags_seen=disables=closes=writes=logs=0;write_mode=wm;timeout_mode=tm;stop_mode=sm;}
void start(void){hw_watchdog_init();}
void feed(void){hw_watchdog_feed();}
void stop(void){hw_watchdog_stop();}
void set_write_mode(int m){write_mode=m;}
int flags(void){return flags_seen;}
int count_disable(void){return disables;}
int count_close(void){return closes;}
int count_write(void){return writes;}
int count_log(void){return logs;}
int current_fd(void){return hw_wd_fd;}
int cloexec_flag(void){return O_CLOEXEC;}
'''
        cfile=Path(cls.tmp.name)/'watchdog.c';dylib=Path(cls.tmp.name)/'watchdog.dylib'
        cfile.write_text(code)
        subprocess.run([shutil.which('clang') or shutil.which('cc'),'-shared','-fPIC',str(cfile),'-o',str(dylib)],check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(dylib))

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_device_fd_does_not_survive_exec(self):
        self.lib.reset(0,0,0);self.lib.start()
        self.assertTrue(self.lib.flags() & self.lib.cloexec_flag())

    def test_normal_shutdown_disables_before_close(self):
        self.lib.reset(0,0,0);self.lib.start();self.lib.stop()
        self.assertEqual(self.lib.count_disable(),1)
        self.assertEqual(self.lib.count_close(),1)
        self.assertEqual(self.lib.current_fd(),-1)

    def test_interrupted_feed_retried(self):
        self.lib.reset(1,0,0);self.lib.start();self.lib.feed()
        self.assertEqual(self.lib.count_write(),2)
        self.assertEqual(self.lib.current_fd(),7)

    def test_feed_failure_does_not_permanently_abandon_watchdog(self):
        self.lib.reset(2,0,0);self.lib.start();self.lib.feed()
        self.assertEqual(self.lib.current_fd(),7)
        self.lib.set_write_mode(0);self.lib.feed()
        self.assertEqual(self.lib.count_write(),2)
        self.assertEqual(self.lib.count_close(),0)

    def test_nowayout_failure_is_logged(self):
        self.lib.reset(0,0,1);self.lib.start();before=self.lib.count_log();self.lib.stop()
        self.assertGreater(self.lib.count_log(),before)
        self.assertEqual(self.lib.count_disable(),1)

    def test_set_timeout_failure_is_reported(self):
        self.lib.reset(0,1,0);self.lib.start()
        self.assertEqual(self.lib.current_fd(),7)
        self.assertEqual(self.lib.count_log(),3)

if __name__ == '__main__': unittest.main()
