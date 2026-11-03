#!/usr/bin/env python3
"""Pure actual divider adapter; no clock, MMIO or device operation."""
import hashlib,re
SOURCE_PATHS={'controller':'trunk/linux-4.4.x/drivers/spi/spi-mt7621.c'}
BASELINE_COMMIT='6e91276a33d1bd83d416fc8253feb01f30677743'
BASELINE_BODY='static u32 mt7621_spi_get_clk_div(u32 hclk_freq, u32 freq)\n{\n\tu32 div;\n\n\tdiv = (hclk_freq + freq - 1) / freq;\n\n\tif (div > (RS_CLK_SEL_M + 2))\n\t\treturn RS_CLK_SEL_M;\n\n\tif (div < 2)\n\t\treturn 2;\n\n\treturn div - 2;\n}'
BASELINE_SHA256='ffff94290f04b32c9c7baff6f32ba805f408434fefe7c7b2b3002b8274964571'
INPUTS=(
 ('normal-80m',220000000,80000000,1),
 ('normal-half',220000000,110000000,0),
 ('normal-round-up',220000000,100000000,1),
 ('normal-four',220000000,55000000,2),
 ('normal-lowest',220000000,53697,4095),
 ('too-low',220000000,1,4095),
 ('zero-rate',220000000,0,4095),
 ('above-half',220000000,220000000,0),
 ('above-source',220000000,4294967295,0),
 ('overflow-high',4000000000,900000000,3),
 ('overflow-max',4294967295,800000000,4),
 ('max-encoding',4097,1,4095),
 ('before-max',4096,1,4094),
 ('clamp-max',4098,1,4095),
 ('min-provider',2,1,0),
 ('min-above',2,2,0),
 ('max-both',4294967295,4294967295,0),
 ('max-half',4294967295,2147483647,1),
 ('max-small',4294967295,1048576,4094),
 ('zero-source',0,1,0),
)
BASELINE_EXPECTED={'normal-80m':1,'normal-half':0,'normal-round-up':1,'normal-four':2,
 'normal-lowest':4095,'too-low':4095,'above-half':2,'above-source':2,
 'overflow-high':2,'overflow-max':2,'max-encoding':4095,'before-max':4094,
 'clamp-max':4095,'min-provider':0,'min-above':2,'max-both':2,'max-half':2,
 'max-small':2,'zero-source':2}
CASES=tuple((name,dict(case=name,hclk=h,rate=f,divider=v)) for name,h,f,v in INPUTS)
BASELINE_CASES=tuple((name,dict(case=name,hclk=h,rate=f,divider=BASELINE_EXPECTED[name]))
                     for name,h,f,_ in INPUTS if name in BASELINE_EXPECTED)
BASELINE_FUNCTIONS={'mt7621_spi_get_clk_div':BASELINE_BODY}
BASELINE_FUNCTIONS_SHA256={'mt7621_spi_get_clk_div':BASELINE_SHA256}
def function(text):
 if text.count('static u32 mt7621_spi_get_clk_div')!=1:raise ValueError('Missing/ambiguous clock divider')
 start=text.index('static u32 mt7621_spi_get_clk_div')
 end=text.index('\nstatic void mt7621_spi_prepare',start)
 return text[start:end].rstrip()
def production_fragments(texts):
 lines=re.findall(r'^#define RS_CLK_SEL_M[ \t]+0xfff$',texts['controller'],re.M)
 if len(lines)!=1:raise ValueError('Changed clock selector constant')
 return lines[0]
def generate_source(texts,fixture_root=None,owner_uid=0,baseline=False):
 if set(texts)!=set(SOURCE_PATHS) or type(baseline)is not bool:raise ValueError('Exact clock source/profile required')
 if hashlib.sha256(BASELINE_BODY.encode()).hexdigest()!=BASELINE_SHA256:raise ValueError('Changed clock baseline')
 body=BASELINE_BODY if baseline else function(texts['controller'])
 prefix='#include <stdint.h>\n#include <stdio.h>\n#include <string.h>\n#include <stdlib.h>\ntypedef uint32_t u32;\n'+production_fragments(texts)+'\n'
 cases=''.join('if(!strcmp(argv[1],'+repr(name).replace("'",'"')+')){h='+str(h)+'U;f='+str(f)+'U;name="'+name+'";}\n' for name,h,f,_ in INPUTS)
 main='int main(int argc,char **argv){u32 h=0,f=0,d;const char*name=NULL;if(argc!=2)return 90;'+cases+'if(!name)return 91;d=mt7621_spi_get_clk_div(h,f);printf("{\\"case\\":\\"%s\\",\\"hclk\\":%u,\\"rate\\":%u,\\"divider\\":%u}\\n",name,h,f,d);return 0;}'
 return prefix+body+'\n'+main+'\n'
