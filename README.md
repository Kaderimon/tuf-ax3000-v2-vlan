# tuf-firmware

VLAN support for the ASUS TUF-AX3000 V2 without Asuswrt-Merlin.

| Path | What |
|---|---|
| [`usb-approach/`](usb-approach/) | Works on stock firmware: SSH + USB startup hook + `vlan.sh` |
| [`docs/RESEARCH.md`](docs/RESEARCH.md) | Full analysis: stock vs EBR63 3.0.0.6.102 firmware, GPL, Merlin, blockers, plan |
| [`tools/`](tools/) | Firmware analysis helpers (FIT/DTB parsers, `.o` relocation summariser); `verify.sh` statically checks a built image against stock |
| `docker/`, `build.sh` | Reproducible build environment for the 3.0.0.6.102 GPL tree |
| `build/` (ignored) | Extracted EBR63 GPL 3.0.0.6.102_44547 |
| `downloads/` (ignored) | Original ASUS zips |

## Building

```sh
# one-time: get the GPL tree (1.4 GB)
mkdir -p downloads build
curl -o downloads/GPL_EBR63_300610244547.zip \
  https://dlcdnets.asus.com/pub/ASUS/wireless/EBR63/GPL_EBR63_300610244547.zip
unzip -p downloads/GPL_EBR63_300610244547.zip | tar -xzf - -C build

./build.sh image                 # docker build env (Ubuntu 20.04)
./build.sh build TUF-AX3000_V2   # log in logs/
./build.sh shell                 # debug inside the container
```

Status: see "Build log" in [`docs/RESEARCH.md`](docs/RESEARCH.md).

**Do not flash anything from this tree without a UART console attached.**
