#!/usr/bin/env python3
# Replace one NUL-terminated string in a binary in place (new must not be longer; padded with NULs).
# usage: tools/patchstr.py <file> <old> <new>
#   e.g. tools/patchstr.py libbwdpi.so ExpertWiFi_EBR63 TUF-AX3000_V2
import sys

path, old, new = sys.argv[1], sys.argv[2].encode() + b'\0', sys.argv[3].encode() + b'\0'
if len(new) > len(old):
    sys.exit(f'"{sys.argv[3]}" is longer than "{sys.argv[2]}"')
d = bytearray(open(path, 'rb').read())
hits = [i for i in range(len(d)) if d.startswith(old, i) and (i == 0 or d[i - 1] == 0)]
if not hits and d.count(new.ljust(len(old), b'\0')) == 1:
    sys.exit(f'{path}: already patched')
if len(hits) != 1:
    sys.exit(f'{path}: "{sys.argv[2]}" found {len(hits)} times, expected 1; not patched')
d[hits[0]:hits[0] + len(old)] = new.ljust(len(old), b'\0')
open(path, 'wb').write(d)
print(f'{path}: {hits[0]:#x} "{sys.argv[2]}" -> "{sys.argv[3]}"')
