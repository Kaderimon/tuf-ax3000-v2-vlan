# Build environment for ASUSWRT HND 5.04axhnd.675x (BCM6756) firmware.
# Ubuntu 20.04 is the newest release that still ships python2 and the
# 32-bit libs the Broadcom SDK host tools expect.
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
        autoconf automake autopoint autogen bash bc binutils-dev bison build-essential bzip2 \
        ca-certificates cmake cpio device-tree-compiler diffutils dos2unix file flex g++ \
        g++-multilib gawk gcc-multilib gengetopt gettext git gperf groff-base gtk-doc-tools \
        intltool lib32stdc++6 lib32z1-dev libc6-dev-i386 libelf-dev libelf1:i386 libexpat1-dev \
        libglib2.0-dev libltdl-dev liblzma-dev liblzo2-dev libncurses5 libncurses5-dev \
        libslang2 libssl-dev libtool libtool-bin libxml-parser-perl libxml2-dev libyaml-dev \
        lzma lzma-dev m4 make mtd-utils patch perl pkg-config python python2 python3 \
        python3-distutils python3-pip python3-pyelftools openssl rsync sharutils shtool sudo texinfo u-boot-tools unzip uuid-dev \
        wget xsltproc xutils-dev xxd xz-utils zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Broadcom build scripts expect /bin/sh to be bash.
RUN ln -sf bash /bin/sh

ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} builder && useradd -m -u ${UID} -g ${GID} -s /bin/bash builder \
    && echo 'builder ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/builder

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
USER builder
RUN git config --global user.email builder@localhost && git config --global user.name builder \
    && git config --global --add safe.directory "*"
WORKDIR /src
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
