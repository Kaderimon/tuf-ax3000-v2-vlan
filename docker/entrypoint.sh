#!/bin/bash
# Link the toolchains bundled with the GPL tree to the hardcoded /opt path.
set -e
TC=/src/asuswrt/release/src-rt-5.04axhnd.675x/toolchains
if [ -d "$TC" ] && [ ! -e /opt/toolchains ]; then
    sudo ln -s "$TC" /opt/toolchains
fi
export PATH="/opt/toolchains/crosstools-arm-gcc-9.2-linux-4.19-glibc-2.30-binutils-2.32/usr/bin:/opt/toolchains/crosstools-aarch64-gcc-9.2-linux-4.19-glibc-2.30-binutils-2.32/usr/bin:$PATH"
export LD_LIBRARY_PATH="/opt/toolchains/crosstools-arm-gcc-9.2-linux-4.19-glibc-2.30-binutils-2.32/usr/lib"
export TOOLCHAIN_BASE=/opt/toolchains
exec "$@"
