#!/usr/bin/env python3
"""Disassemble functions from an ARM relocatable .o (built with -ffunction-sections),
annotating relocations with symbol names and string literals.
usage: armdis.py file.o func [func...]"""
import sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

f = ELFFile(open(sys.argv[1], 'rb'))
symtab = f.get_section_by_name('.symtab')

def cstr(sec, off):
    d = sec.data()
    return d[off:d.find(b'\0', off)].decode('latin1')

def reloc_note(r, code):
    s = symtab.get_symbol(r['r_info_sym'])
    sh = s['st_shndx']
    if isinstance(sh, int) and sh > 0:
        tgt = f.get_section(sh)
        if tgt.name.startswith('.rodata'):
            base = s['st_value'] if s['st_info']['type'] != 'STT_SECTION' else 0
            add = int.from_bytes(code[r['r_offset']:r['r_offset'] + 4], 'little') if r['r_info_type'] == 2 else 0
            return repr(cstr(tgt, base + add))
    return s.name or f.get_section(sh).name if isinstance(sh, int) else s.name

for fn in sys.argv[2:]:
    sym = next(s for s in symtab.iter_symbols() if s.name == fn and s['st_info']['type'] == 'STT_FUNC')
    sec = f.get_section(sym['st_shndx'])
    code = sec.data()
    rel = f.get_section_by_name('.rel' + sec.name)
    notes = {r['r_offset']: reloc_note(r, code) for r in rel.iter_relocations()} if rel else {}
    thumb = sym['st_value'] & 1
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM)
    print(f'===== {fn} ({len(code)} bytes, {"thumb" if thumb else "arm"})')
    for ins in md.disasm(code, 0):
        n = notes.get(ins.address) or notes.get(ins.address & ~3)
        print(f'  {ins.address:04x}: {ins.mnemonic:8s} {ins.op_str}' + (f'    ; {n}' if n else ''))
    lit = sorted(o for o in notes if o >= 0)
    for o in lit:
        if not any(i.address == o for i in md.disasm(code, 0)):
            print(f'  lit {o:04x}: {notes[o]}')
