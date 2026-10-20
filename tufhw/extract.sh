#!/bin/bash
# Extract TUF-AX3000_V2 board functions from the TUF 388 GPL closed objects into
# one relocatable object (tuf_hw.o) that links into the 3006 rc without clashes.
#   1. localize every global except the wanted symbol (no duplicate definitions)
#   2. ld -r --gc-sections -u <sym>: drop function sections the symbol can't reach
# usage (inside build container): extract.sh <tuf388 release/src/router dir> <outdir>
set -euo pipefail
SRC=$1 OUT=$2
X=/opt/toolchains/crosstools-arm-gcc-9.2-linux-4.19-glibc-2.30-binutils-2.32/usr/bin/arm-buildroot-linux-gnueabi-
mkdir -p "$OUT/tmp"
# object:symbol pairs
PAIRS="rc/prebuild/broadcom.o:bcm53134_led_control rc/prebuild/broadcom.o:lan_phy_led_pinmux rc/prebuild/ate-broadcom.o:get_ext_phy_id shared/prebuild/private.o:extphy_bit_op"
parts=()
for p in $PAIRS; do
    obj=${p%%:*} sym=${p##*:}
    "${X}objcopy" --keep-global-symbol="$sym" "$SRC/$obj" "$OUT/tmp/$sym.loc.o"
    "${X}ld" -r --gc-sections -u "$sym" -o "$OUT/tmp/$sym.o" "$OUT/tmp/$sym.loc.o"
    parts+=("$OUT/tmp/$sym.o")
done
"${X}ld" -r -o "$OUT/tuf_hw.o" "${parts[@]}"
echo "== defined:";   "${X}nm" "$OUT/tuf_hw.o" | grep ' T '
echo "== undefined:"; "${X}nm" -u "$OUT/tuf_hw.o" | awk '{print $2}' | sort -u | tr '\n' ' '; echo
"${X}size" "$OUT/tuf_hw.o"
