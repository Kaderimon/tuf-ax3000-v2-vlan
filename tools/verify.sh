#!/bin/bash
# Static checks of a built image against stock, no flashing needed.
# usage: tools/verify.sh <new.pkgtb> <stock.pkgtb> [workdir]
#   - outer FIT image hashes
#   - ATF, U-Boot and DTBs byte-identical to stock
#   - kernel in image == build tree arch/arm/boot/Image (modules are checked against its System.map)
#   - kernel modules: vermagic and symbol resolution
#   - every ELF finds its libraries and symbols (new problems vs stock)
#   - files present in stock but missing from the new rootfs
set -uo pipefail
cd "$(dirname "$0")/.."
NEW=$(realpath "$1") STOCK=$(realpath "$2") W=$(realpath -m "${3:-out/verify}")
T=tools K=build/asuswrt/release/src-rt-5.04axhnd.675x/kernel/linux-4.19
LZOP=build/asuswrt/release/src-rt-5.04axhnd.675x/hostTools/prebuilt
rc=0; fail() { echo "FAIL: $*"; rc=1; }
rm -rf "$W"; mkdir -p "$W/new" "$W/stock"
for d in new stock; do
    img=$NEW; [ $d = stock ] && img=$STOCK
    echo "== $d image: $(basename "$img")"
    python3 -I $T/pkgsplit.py "$img" "$W/$d" || fail "$d image hash"
    unsquashfs -q -n -d "$W/$d/root" "$W/$d/nand_squashfs" >/dev/null 2>&1
done
echo "== boot chain vs stock (rescue mode relies on it)"
for i in atf uboot fdt_uboot fdt_TUF_AX3000_V2; do
    cmp -s <(python3 -I $T/fitget.py "$W/new/bootfs_6756_a0+" $i) <(python3 -I $T/fitget.py "$W/stock/bootfs_6756_a0+" $i) &&
        echo "$i == stock" || fail "$i differs from stock"
done
echo "== kernel"
python3 -I $T/fitget.py "$W/new/bootfs_6756_a0+" kernel > "$W/new/kernel.lzo"
docker run --rm -v "$W/new:/w" -v "$PWD/$LZOP:/t:ro" tuf-fw-builder sh -c '/t/lzop -d -c /w/kernel.lzo > /w/kernel.bin' &&
    cmp -s "$W/new/kernel.bin" $K/arch/arm/boot/Image && echo "kernel == build tree Image" || fail "kernel differs from build tree Image"
strings -a "$W/new/kernel.bin" | grep -m1 "Linux version"
echo "== kernel modules"
find "$W/new/root/lib/modules" -name '*.ko' -exec sh -c 'strings -a "$1" | grep -m1 "^vermagic="' _ {} \; | sort | uniq -c
python3 -I $T/kocheck.py $K/System.map "$W/new/root/lib/modules" || fail "module symbols"
echo "== ELF libraries and symbols"
python3 -I $T/elfcheck.py "$W/stock/root" > "$W/stock.json" & python3 -I $T/elfcheck.py "$W/new/root" > "$W/new.json"; wait
python3 -I $T/elfdiff.py "$W/stock.json" "$W/new.json" || fail "ELF problems not in stock"
echo "== files in stock but not in new (excluding www, modules)"
(cd "$W/stock/root" && find . | sort) > "$W/stock.lst"; (cd "$W/new/root" && find . | sort) > "$W/new.lst"
comm -23 "$W/stock.lst" "$W/new.lst" | grep -vE '^./(www|webs|lib/modules|usr/lighttpd)/' | tr '\n' ' '; echo
echo "($(comm -23 "$W/stock.lst" "$W/new.lst" | wc -l) only in stock, $(comm -13 "$W/stock.lst" "$W/new.lst" | wc -l) only in new; full lists in $W)"
[ $rc = 0 ] && echo "== ALL CHECKS PASSED" || echo "== SOME CHECKS FAILED"
exit $rc
