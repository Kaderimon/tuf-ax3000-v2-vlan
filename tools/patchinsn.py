#!/usr/bin/env python3
# Replace one 32-bit ARM instruction in an object's .text, checking the old one first.
# usage: tools/patchinsn.py <file.o> <text_offset_hex> <old_insn_hex> <new_insn_hex>
#   e.g. tools/patchinsn.py priv_webapi.o 25c8 e3a00001 e3a00000
import struct, sys

path, off, old, new = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16), int(sys.argv[4], 16)
d = bytearray(open(path, 'rb').read())
shoff, = struct.unpack_from('<I', d, 0x20)
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x2e)
sec = lambda i: struct.unpack_from('<10I', d, shoff + i * shentsize)
stroff = sec(shstrndx)[4]
name = lambda s: d[stroff + s[0]:d.index(0, stroff + s[0])].decode()
text = next(s for s in map(sec, range(shnum)) if name(s) == '.text')
pos = text[4] + off
cur, = struct.unpack_from('<I', d, pos)
if cur == new:
    sys.exit(f'{path}: .text+{off:#x} already {new:08x}')
if cur != old:
    sys.exit(f'{path}: .text+{off:#x} is {cur:08x}, expected {old:08x}; not patched')
struct.pack_into('<I', d, pos, new)
open(path, 'wb').write(d)
print(f'{path}: .text+{off:#x} {old:08x} -> {new:08x}')
