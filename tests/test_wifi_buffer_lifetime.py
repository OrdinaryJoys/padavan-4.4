"""Source-bound BIN/Flash buffer lifetime tests with RAM-only IO seams.

The BIN and Flash initializers execute whole current functions. Close executes
the explicitly delimited calibration/EEPROM cleanup section from RTMPDrvClose;
reopen executes the hook's image allocation section. No hardware, radio, or
remainder of adapter teardown is represented by those sections.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import wifi_bin_io_harness as h

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / h.BASE


def lifecycle_source():
    texts = {key: (ROOT / path).read_text() for key, path in h.SOURCE_PATHS.items()}
    chip = (BASE / 'chips/mt7615.c').read_text()
    command_header = (BASE / 'include/mcu/mt_cmd.h').read_text()
    chip_header = (BASE / 'include/chip/mt7615.h').read_text()
    sizes = []
    for array, stride in [('K_AllFreq', 'RXDCOC_SIZE'), ('DPD_A20Freq', 'TXDPD_SIZE'),
                          ('DPD_G20Freq', 'TXDPD_SIZE')]:
        entries = re.search(r'UINT16 ' + array + r'\[\] = \{([^}]+)\}', chip).group(1)
        count = len(re.findall(r'\d+', entries))
        width = int(re.search(r'^#define ' + stride + r' (\d+)$', command_header, re.M).group(1))
        sizes.append(count * width)
    if sizes != [8704, 9504, 648]:
        raise ValueError('Changed calibration spans require explicit lifetime expectations')
    for expression in ('#define DCOC_FLASH_OFFSET\t\t1024',
                       '#define DCOC_OFFSET\t\t     (DCOC_FLASH_OFFSET)',
                       '#define DPDPART1_OFFSET\t        (DCOC_OFFSET + DCOC_IMAGE_SIZE)',
                       '#define DPDPART2_OFFSET\t\t(DCOC_OFFSET + DCOC_IMAGE_SIZE + TXDPD_IMAGE1_SIZE)'):
        if expression not in chip_header:
            raise ValueError('Changed calibration layout')

    prefix = h.PREFIX.replace('#define RT_SOC_SUPPORT 1\n#define MULTIPLE_CARD_SUPPORT 1\n', '')
    for before, after in [('#define DCOC_IMAGE_SIZE 8', '#define DCOC_IMAGE_SIZE 8704'),
                          ('#define TXDPD_IMAGE1_SIZE 8', '#define TXDPD_IMAGE1_SIZE 9504'),
                          ('#define TXDPD_IMAGE2_SIZE 8', '#define TXDPD_IMAGE2_SIZE 648'),
                          ('#define DPDPART1_OFFSET 8', '#define DPDPART1_OFFSET 9728'),
                          ('#define DPDPART2_OFFSET 16', '#define DPDPART2_OFFSET 19232'),
                          ('static int fsdepth,', 'static int allocation_enabled=1,flash_reads;\nstatic int fsdepth,'),
                          ('if(has("open-")||is("write-open-error"))',
                           'if((has("open-")&&!has("close-open"))||is("write-open-error"))'),
                          ('if(has("read-error"))return -5;', 'if(allocation_enabled&&has("read-error"))return -5;')]:
        if prefix.count(before) != 1:
            raise ValueError('Changed lifetime seam: ' + before)
        prefix = prefix.replace(before, after)
    start = prefix.index(' if(len==8)')
    end = prefix.index('\n if(has("load-allocation-error")', start)
    prefix = prefix[:start] + r'''
 if(len==DCOC_IMAGE_SIZE||len==TXDPD_IMAGE1_SIZE||len==TXDPD_IMAGE2_SIZE){cal_allocs++;
  fail=allocation_enabled&&((has("allocation-dcoc")&&len==DCOC_IMAGE_SIZE)||(has("allocation-dpd1")&&len==TXDPD_IMAGE1_SIZE)||(has("allocation-dpd2")&&len==TXDPD_IMAGE2_SIZE));}
 if(allocation_enabled&&has("image-allocation-error")&&len==MAX_EEPROM_BUFFER_SIZE)fail=1;
 if(allocation_enabled&&has("flash-allocation-error")&&len==profile_size)fail=1;''' + prefix[end:]
    prefix += r'''
#define CONFIG_WIFI_MTD 1
#define IS_MT7615(p) 1
#define DCOC_OFFSET 1024
static int get_dev_eeprom_offset(RTMP_ADAPTER*p){(void)p;return 0;}
static int mt_mtd_read_nm_wifi(char*n,int off,UINT len,UCHAR*buf){(void)n;(void)off;flash_reads++;event("flash-read");if(allocation_enabled&&has("read-error"))return -5;memset(buf,0x55,len);buf[0x52]=3;buf[0x53]=0;return 0;}
static NDIS_STATUS rtmp_ee_flash_init(RTMP_ADAPTER*p,UCHAR*image){(void)p;(void)image;cap.ee_inited=1;return NDIS_STATUS_SUCCESS;}
static int is_owned(void*p){int i;for(i=0;i<32;i++)if(p&&owned[i]==p)return 1;return 0;}
'''
    functions = h.actual_functions(texts)
    bodies = '\n'.join(functions[name]['body'] for name in h.BODY_ORDER)
    bodies += '\n' + h.function(texts['flash'], 'rtmp_nv_init')
    close_text = (BASE / 'embedded/common/rtmp_init_inf.c').read_text()
    close_start = close_text.index('VOID RTMPDrvClose(')
    section_start = close_text.index('#ifdef PRE_CAL_TRX_SET1_SUPPORT', close_start)
    image_release = '\tos_free_mem(pAd->EEPROMImage);\n\tpAd->EEPROMImage = NULL;'
    section_end = close_text.index(image_release, section_start) + len(image_release)
    close_section = close_text[section_start:section_end]
    bodies += '\nstatic void close_calibration(RTMP_ADAPTER*pAd){\n' + close_section + '\n}\n'
    hook = h.function(texts['eeprom'], 'RtmpChipOpsEepromHook')
    allocation = '\tif (pAd->EEPROMImage == NULL)\n\t\tos_alloc_mem(pAd, &pAd->EEPROMImage, MAX_EEPROM_BUFFER_SIZE);'
    if hook.count(allocation) != 1:
        raise ValueError('Changed reopen image allocation section')
    bodies += '\nstatic void reopen_image(RTMP_ADAPTER*pAd){\n' + allocation + '\n}\n'
    return prefix + '\n' + bodies + r'''
int main(int argc,char**argv){
 RTMP_ADAPTER a;UCHAR snapshot[32768];UCHAR*previous_image,*previous_dcoc,*previous_dpd1,*previous_dpd2;
 int status=0,i,previous_mode,previous_source,previous_access,previous_flags,unchanged,views,owned_mask,close_clear=-1;
 UINT snapshot_size=1024;
 if(argc!=2)return 90;
 case_name=argv[1];memset(&a,0,sizeof(a));a.hdev_ctrl=&cap;a.MACVersion=0x76150000;
 a.E2pAccessMode=E2P_FLASH_MODE;a.E2pCtrl.e2pCurMode=E2P_FLASH_MODE;a.E2pCtrl.e2pSource=E2P_SRC_FROM_FLASH;a.E2pCtrl.BinSource="old-source";
 cap.EEPROM_DEFAULT_BIN=cache;cap.EEPROM_DEFAULT_BIN_SIZE=1024;cap.EEPROM_DEFAULT_BIN_FILE=default_path;
 allocation_enabled=0;
 if(os_alloc_mem(&a,&a.EEPROMImage,1024))return 91;
 memset(a.EEPROMImage,0x55,1024);a.EEPROMImage[0x52]=3;a.EEPROMImage[0x53]=0;
 allocation_enabled=0;
 if(has("flash-bin")){profile_size=16384;status=rtmp_nv_init(&a);snapshot_size=profile_size;}
 else if(has("bin-close")||has("bin-flash")||has("bin-partial")||is("bin-repeat"))status=rtmp_ee_bin_init(&a);
 if(status)return 92;
 if(has("bin-close")){close_calibration(&a);close_calibration(&a);close_clear=!a.EEPROMImage&&!a.CalDCOCImage&&!a.CalDPDAPart1Image&&!a.CalDPDAPart2Image&&!a.bDCOCReloaded&&!a.bDPDReloaded;allocation_enabled=1;reopen_image(&a);}
 if(has("bin-partial")){os_free_mem(a.CalDPDAPart1Image);os_free_mem(a.CalDPDAPart2Image);a.CalDPDAPart1Image=a.CalDPDAPart2Image=NULL;a.bDPDReloaded=FALSE;}
 previous_image=a.EEPROMImage;previous_dcoc=a.CalDCOCImage;previous_dpd1=a.CalDPDAPart1Image;previous_dpd2=a.CalDPDAPart2Image;
 previous_mode=a.E2pCtrl.e2pCurMode;previous_source=a.E2pCtrl.e2pSource;previous_access=a.E2pAccessMode;previous_flags=a.bDCOCReloaded+2*a.bDPDReloaded;
 if(a.EEPROMImage)memcpy(snapshot,a.EEPROMImage,snapshot_size);cal_allocs=0;allocs=0;frees_count=0;allocation_enabled=1;
 if(!strncmp(case_name,"flash-",6)&&!has("flash-bin")){
  profile_size=16384;
  if(is("flash-small"))profile_size=512;
  if(is("flash-base"))profile_size=1024;
  if(is("flash-dcoc-short"))profile_size=9727;
  if(is("flash-dcoc-exact"))profile_size=9728;
  if(is("flash-dpd1-exact"))profile_size=19232;
  if(is("flash-all-short"))profile_size=19879;
  if(is("flash-all-exact"))profile_size=19880;
  if(is("flash-all-large"))profile_size=32768;
  status=rtmp_nv_init(&a);
 }else if(has("bin-flash")){profile_size=16384;status=rtmp_nv_init(&a);}
 else status=rtmp_ee_bin_init(&a);
 if(has("flash-close")){close_calibration(&a);close_calibration(&a);close_clear=!a.EEPROMImage&&!a.CalDCOCImage&&!a.CalDPDAPart1Image&&!a.CalDPDAPart2Image&&!a.bDCOCReloaded&&!a.bDPDReloaded;}
 unchanged=a.EEPROMImage==previous_image&&a.CalDCOCImage==previous_dcoc&&a.CalDPDAPart1Image==previous_dpd1&&a.CalDPDAPart2Image==previous_dpd2&&a.E2pCtrl.e2pCurMode==previous_mode&&a.E2pCtrl.e2pSource==previous_source&&a.E2pAccessMode==previous_access&&a.bDCOCReloaded+2*a.bDPDReloaded==previous_flags&&(!a.EEPROMImage||!memcmp(snapshot,a.EEPROMImage,snapshot_size));
 owned_mask=is_owned(a.CalDCOCImage)+2*is_owned(a.CalDPDAPart1Image)+4*is_owned(a.CalDPDAPart2Image);
 views=(a.CalDCOCImage&&(uintptr_t)a.CalDCOCImage==(uintptr_t)a.EEPROMImage+DCOC_OFFSET)+2*(a.CalDPDAPart1Image&&(uintptr_t)a.CalDPDAPart1Image==(uintptr_t)a.EEPROMImage+DPDPART1_OFFSET)+4*(a.CalDPDAPart2Image&&(uintptr_t)a.CalDPDAPart2Image==(uintptr_t)a.EEPROMImage+DPDPART2_OFFSET);
 printf("{\"status\":%d,\"access\":%d,\"mode\":%d,\"source\":%d,\"flags\":%d,\"bits\":%u,\"views\":%d,\"owned\":%d,\"live\":%d,\"cal_allocs\":%d,\"allocs\":%d,\"frees\":%d,\"flash_reads\":%d,\"unchanged\":%d,\"close_clear\":%d}\n",status,a.E2pAccessMode,a.E2pCtrl.e2pCurMode,a.E2pCtrl.e2pSource,a.bDCOCReloaded+2*a.bDPDReloaded,a.EEPROMImage?((unsigned)a.EEPROMImage[0x52]|((unsigned)a.EEPROMImage[0x53]<<8)):0,views,owned_mask,live_allocs,cal_allocs,allocs,frees_count,flash_reads,unchanged,close_clear);
 for(i=0;i<32;i++)if(owned[i])free(owned[i]);return 0;
}
'''


class WifiBufferLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='k2p-wifi-lifetime-')
        cls.base = Path(cls.temp.name)
        cls.source = lifecycle_source()
        cls.binary = cls.base / 'lifetime'
        source = cls.base / 'lifetime.c'
        source.write_text(cls.source)
        result = subprocess.run([shutil.which('clang'), '-std=gnu99', '-Os', '-Wall', '-Wextra',
                                 '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                                 '-Wno-sign-compare', '-fsanitize=address,undefined',
                                 '-fno-sanitize-recover=undefined', str(source), '-o', str(cls.binary)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def row(self, case):
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True, timeout=5)
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stderr)
        return json.loads(result.stdout)

    def test_flash_full_span_boundaries_and_ram_fallback_bits(self):
        for case, views, flags, bits in [('flash-base', 0, 0, 0), ('flash-dcoc-short', 0, 0, 0),
                                       ('flash-dcoc-exact', 1, 1, 2), ('flash-k2p', 1, 1, 2),
                                       ('flash-dpd1-exact', 3, 1, 2), ('flash-all-short', 3, 1, 2),
                                       ('flash-all-exact', 7, 3, 3), ('flash-all-large', 7, 3, 3)]:
            with self.subTest(case=case):
                row = self.row(case)
                self.assertEqual([row[k] for k in ('status', 'access', 'mode', 'source')], [0, 2, 2, 2])
                self.assertEqual([row[k] for k in ('views', 'flags', 'bits', 'owned', 'live')],
                                 [views, flags, bits, 0, 1])

    def test_flash_capacity_and_io_failures_leave_no_views_or_allocations(self):
        for case, reads in [('flash-small', 0), ('flash-allocation-error', 0), ('flash-read-error', 1)]:
            with self.subTest(case=case):
                row = self.row(case)
                self.assertEqual([row[k] for k in ('status', 'mode', 'source', 'views', 'flags', 'owned', 'live', 'flash_reads')],
                                 [1, 0, 0, 0, 0, 0, 0, reads])

    def test_flash_to_bin_allocates_independent_full_buffers(self):
        row = self.row('flash-bin')
        self.assertEqual([row[k] for k in ('status', 'access', 'owned', 'views', 'live', 'cal_allocs', 'flags')],
                         [0, 4, 7, 0, 4, 3, 3])

    def test_each_failed_flash_to_bin_allocation_preserves_prior_state(self):
        for part in ('dcoc', 'dpd1', 'dpd2'):
            with self.subTest(part=part):
                row = self.row('flash-bin-allocation-' + part)
                self.assertEqual([row[k] for k in ('status', 'access', 'unchanged', 'views', 'owned', 'live')],
                                 [1, 2, 1, 1, 0, 1])

    def test_failed_base_load_frees_only_staged_buffers(self):
        for case, access, views, owned, live in [('flash-bin-read-error', 2, 1, 0, 1),
                                               ('bin-partial-read-error', 4, 0, 1, 2),
                                               ('bin-close-open-read-error', 4, 0, 0, 1)]:
            with self.subTest(case=case):
                row = self.row(case)
                self.assertEqual([row[k] for k in ('status', 'access', 'unchanged', 'views', 'owned', 'live')],
                                 [1, access, 1, views, owned, live])

    def test_bin_to_flash_frees_all_independent_buffers_and_changes_ownership(self):
        row = self.row('bin-flash')
        self.assertEqual([row[k] for k in ('status', 'access', 'views', 'owned', 'live', 'frees')],
                         [0, 2, 1, 0, 1, 4])

    def test_repeated_bin_initialization_reuses_all_owned_buffers(self):
        row = self.row('bin-repeat')
        self.assertEqual([row[k] for k in ('status', 'owned', 'live', 'cal_allocs')], [0, 7, 4, 0])

    def test_partial_bin_allocation_failures_preserve_existing_owned_buffer(self):
        for part in ('dpd1', 'dpd2'):
            with self.subTest(part=part):
                row = self.row('bin-partial-allocation-' + part)
                self.assertEqual([row[k] for k in ('status', 'access', 'unchanged', 'owned', 'live')],
                                 [1, 4, 1, 1, 2])

    def test_close_clears_bin_pointers_before_reopen_and_repeated_cleanup(self):
        row = self.row('bin-close-open')
        self.assertEqual([row[k] for k in ('status', 'close_clear', 'owned', 'live', 'cal_allocs')], [0, 1, 7, 4, 3])
        row = self.row('flash-close')
        self.assertEqual([row[k] for k in ('status', 'close_clear', 'owned', 'views', 'live')], [0, 1, 0, 0, 0])

    def test_each_reopen_allocation_failure_preserves_cleared_state(self):
        for part in ('dcoc', 'dpd1', 'dpd2'):
            with self.subTest(part=part):
                row = self.row('bin-close-open-allocation-' + part)
                self.assertEqual([row[k] for k in ('status', 'close_clear', 'unchanged', 'owned', 'live')], [1, 1, 1, 0, 1])
        row = self.row('bin-close-open-image-allocation-error')
        self.assertEqual([row[k] for k in ('status', 'close_clear', 'unchanged', 'owned', 'live')], [1, 1, 1, 0, 0])


if __name__ == '__main__':
    unittest.main()
