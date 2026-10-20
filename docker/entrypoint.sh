#!/bin/bash
# Link the toolchains bundled with the GPL tree to the hardcoded /opt path.
set -e
TC=/src/asuswrt/release/src-rt-5.04axhnd.675x/toolchains
if [ -d "$TC" ] && [ ! -e /opt/toolchains ]; then
    sudo ln -s "$TC" /opt/toolchains
fi
# The vendor toolchain binaries carry an RPATH to ASUS's build host; recreate it.
if [ -d "$TC" ] && [ ! -e /home/defjovi/temp3/toolchain ]; then
    sudo mkdir -p /home/defjovi/temp3
    sudo ln -s "$TC" /home/defjovi/temp3/toolchain
fi
# Appended, not prepended: the toolchain ships its own autotools whose perl
# modules point at the vendor build host, and the Makefile uses absolute
# CROSS_COMPILE paths anyway.
export PATH="$PATH:/opt/toolchains/crosstools-arm-gcc-9.2-linux-4.19-glibc-2.30-binutils-2.32/usr/bin"
export TOOLCHAIN_BASE=/opt/toolchains
exec "$@"
