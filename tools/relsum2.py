import sys
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
f=ELFFile(open(sys.argv[1],'rb')); want=sys.argv[2:]
symtab=f.get_section_by_name('.symtab')
def strat(sec,off):
    d=sec.data(); e=d.find(b'\0',off); return d[off:e].decode('latin1')
for sec in f.iter_sections():
    if not isinstance(sec,RelocationSection) or not sec.name.startswith('.rel.text.'): continue
    fn=sec.name[len('.rel.text.'):]
    if want and fn not in want: continue
    code=f.get_section(sec['sh_info']).data(); out=[]
    for r in sorted(sec.iter_relocations(),key=lambda r:r['r_offset']):
        s=symtab.get_symbol(r['r_info_sym']); off=r['r_offset']
        sh=s['st_shndx']
        if isinstance(sh,int) and sh>0 and f.get_section(sh).name.startswith('.rodata'):
            base=s['st_value'] if s['st_info']['type']!='STT_SECTION' else 0
            add=int.from_bytes(code[off:off+4],'little') if r['r_info_type']==2 else 0
            out.append(f'   str: {strat(f.get_section(sh),base+add)!r}')
        elif not s.name.startswith(('_GLOBAL_OFFSET','__stack_chk')):
            out.append(f'   ->  {s.name}')
    print(f'===== {fn}'); print('\n'.join(x for i,x in enumerate(out) if i==0 or x!=out[i-1]))
