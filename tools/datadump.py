#!/usr/bin/env python3
"""Dump pointer tables in a section (default .data) of a relocatable .o,
resolving relocations to strings/symbols. usage: datadump.py file.o [section] [start end]"""
import sys
from elftools.elf.elffile import ELFFile
f = ELFFile(open(sys.argv[1], 'rb'))
secname = sys.argv[2] if len(sys.argv) > 2 else '.data'
lo, hi = (int(sys.argv[3], 0), int(sys.argv[4], 0)) if len(sys.argv) > 4 else (0, 1 << 30)
sec = f.get_section_by_name(secname); data = sec.data()
symtab = f.get_section_by_name('.symtab')
rel = f.get_section_by_name('.rel' + secname)
rels = {r['r_offset']: r for r in rel.iter_relocations()} if rel else {}
def cstr(s, off):
    d = s.data(); return d[off:d.find(b'\0', off)].decode('latin1')
for off in range(max(lo, 0), min(hi, len(data)), 4):
    word = int.from_bytes(data[off:off + 4], 'little')
    r = rels.get(off)
    if r:
        s = symtab.get_symbol(r['r_info_sym']); sh = s['st_shndx']
        tgt = f.get_section(sh) if isinstance(sh, int) and sh > 0 else None
        base = s['st_value'] if s['st_info']['type'] != 'STT_SECTION' else 0
        txt = repr(cstr(tgt, base + word)) if tgt is not None and tgt.name.startswith('.rodata') else (s.name or tgt.name)
    else:
        txt = 'NULL' if word == 0 else hex(word)
    print(f'{off:#06x}: {txt}')
