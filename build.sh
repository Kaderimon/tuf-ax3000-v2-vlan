#!/bin/bash
# Usage: ./build.sh [image|shell|build [TARGET]]
#   image  - build the docker image
#   shell  - interactive shell in the build container
#   build  - build firmware (default target TUF-AX3000_V2), log to logs/
set -eo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
IMAGE=tuf-fw-builder
RUN=(docker run --rm -v "$ROOT/build:/src" -w /src/asuswrt/release/src-rt-5.04axhnd.675x)

case "${1:-build}" in
    image)
        docker build --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" -t "$IMAGE" docker/
        ;;
    shell)
        "${RUN[@]}" -it "$IMAGE" bash
        ;;
    build)
        target="${2:-TUF-AX3000_V2}"
        mkdir -p logs
        log="logs/build-$target-$(date +%Y%m%d-%H%M%S).log"
        echo "logging to $log"
        "${RUN[@]}" "$IMAGE" bash -c "make $target" 2>&1 | tee "$log"
        ;;
    *)
        sed -n '2,6p' "$0"; exit 1 ;;
esac
