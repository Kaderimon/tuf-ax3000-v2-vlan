# tuf-firmware

VLAN support for the ASUS TUF-AX3000 V2 without Asuswrt-Merlin.

ASUS ships VLAN / "Guest Network Pro" only in the 3.0.0.6.102 firmware branch and
never released that branch for the TUF-AX3000 V2. This repo builds a
3.0.0.6.102 firmware for the TUF from the ASUS ExpertWiFi EBR63 GPL tree (same
BCM6756 SoC; the tree already contains a `TUF-AX3000_V2` target), plus patches
for everything that breaks because the closed parts of that tree were compiled
for the EBR63. Full analysis: [`docs/RESEARCH.md`](docs/RESEARCH.md).

## Status (2026-10-23, image `g69420e1`)

Running on a real TUF-AX3000 V2 as a one-time-boot test image, with official
firmware as fallback in the other slot.

| Area                                                                      | State                                                                                                                                                         |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Boot, kernel, WAN (DHCP, 2.5G port), LAN DHCP, both Wi-Fi bands, SSH      | works                                                                                                                                                         |
| Web UI: login, System Status, SSID, client list, VPN, Adaptive QoS pages  | works                                                                                                                                                         |
| Network → VLAN, Guest Network Pro / SDN networks with own VLAN ID + DHCP  | works: trunk port to an 802.1Q switch carries the VLANs tagged and the main LAN untagged; VLANs isolated from main LAN and each other, have internet          |
| AiMesh menu                                                               | shown (`amas_support=3`); pairing not tested                                                                                                                  |
| Access-port VLAN, leak test from a client, throughput, IPv6, LED-off mode | not tested                                                                                                                                                    |
| Likely to misbehave | AiMesh pairing (closed EBR63 AiMesh daemons), LAN LED-off mode, wired LAN↔LAN speed once a port is Access/Trunk (hardware switching off), web-UI firmware update / auto-upgrade, `router.asus.com` name (now `expertwifi.net`) |
| Removed (closed parts missing from the EBR63 GPL) | Router Boost, link aggregation (LACP), UU accelerator, Alexa / IFTTT / Google Assistant, Instant Guard, AiCloud / WebDAV, Smart Sync, Download Master |

What is missing or may not work compared with stock, and why:
[`docs/RESEARCH.md` §5.5](docs/RESEARCH.md#55-differences-from-stock-388_24049-what-is-missing-or-may-not-work).
Open issues and test status: [§5.4](docs/RESEARCH.md#54-open-issues) and §6.
If you rely on any removed feature, stay on official firmware.

**This is experimental firmware. Only try it with the dual-image procedure below,
which keeps official firmware as an automatic fallback.**

## Layout

| Path                                              | What                                                                                                                                            |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| [`docs/RESEARCH.md`](docs/RESEARCH.md)            | Analysis, every patch with reason, flashing procedure, hardware results                                                                         |
| [`patches/`](patches/)                            | `git format-patch` series against the pristine EBR63 GPL tree (binary objects included)                                                         |
| `docker/`, `build.sh`                             | Reproducible build environment (Ubuntu 20.04)                                                                                                   |
| [`tools/`](tools/)                                | Image analysis (`fitls.py`, `fitget.py`, `pkgsplit.py`, …), `verify.sh` static image check, binary patch helpers `patchinsn.py` / `patchstr.py` |
| [`tufhw/`](tufhw/)                                | Extracts TUF board functions from the TUF 388 GPL blobs (result is in patch 0005)                                                               |
| [`usb-approach/`](usb-approach/)                  | Alternative without custom firmware: stock firmware + USB startup hook + `vlan.sh` (untested)                                                   |
| `build/`, `downloads/`, `out/`, `logs/` (ignored) | GPL tree, ASUS zips, built images, build logs                                                                                                   |

## Building

```sh
# one-time: get the GPL tree (1.4 GB) and apply the patches
mkdir -p downloads build
curl -o downloads/GPL_EBR63_300610244547.zip \
  https://dlcdnets.asus.com/pub/ASUS/wireless/EBR63/GPL_EBR63_300610244547.zip
unzip -p downloads/GPL_EBR63_300610244547.zip | tar -xzf - -C build
cd build/asuswrt
git init -q && git add -A && git commit -qm "pristine GPL_EBR63 3.0.0.6.102_44547"
git am ../../patches/*.patch
cd ../..

./build.sh image                 # docker build env
./build.sh build TUF-AX3000_V2   # ~30 min first time; log in logs/
./build.sh shell                 # debug inside the container
```

Result: `build/asuswrt/release/src-rt-5.04axhnd.675x/targets/96756GW/TUF-AX3000_V2_3.0.0.6_102_40000-g<commit>_nand_squashfs.pkgtb`.
Ignore the `*_loader.pkgtb` next to it: it also rewrites the boot loader and must
never be flashed.

Optional static check against stock (no router needed):
`tools/verify.sh <new.pkgtb> <stock 388 .pkgtb>`, see RESEARCH §4.

## Trying it on a router

How it stays safe: the router has two firmware slots. The boot loader starts the
_committed_ slot; `bcm_bootstate` can ask it to start the other slot **once**.
The test image is never committed (patch 0011), so any later reboot or power
cycle returns to official firmware. Details: [RESEARCH §5](docs/RESEARCH.md#5-flashing-and-hardware-testing).

Before you start, in the official web UI:

- **Administration → Firmware Upgrade → Auto Firmware Upgrade: off.** Otherwise
  ASUS's updater can overwrite the test slot and commit itself (happened once).
- **Administration → System → Enable SSH: LAN only.** Login and settings are kept
  across the flash.

Then:

```sh
# 1. on the router: you must be on the committed (official) slot
bcm_bootstate | grep -E "Booted|commit flag"    # Booted X, X commit flag 1

# 2. on the PC (the router has no scp/sftp)
cat TUF-AX3000_V2_*_nand_squashfs.pkgtb | ssh admin@192.168.1.1 'cat > /tmp/fw.pkgtb'

# 3. on the router
sha256sum /tmp/fw.pkgtb                         # compare with the PC
bcm_flasher /tmp/fw.pkgtb                       # writes the other slot, no commit
bcm_bootstate | grep -E "Booted|commit flag"    # running slot 1, other slot 0
bcm_bootstate 8     # if the new image is in Second (booted First)
bcm_bootstate 6     # if the new image is in First  (booted Second)
reboot              # a reboot, not a power cycle
```

After 3–5 minutes: `nvram get extendno` shows `40000-g<commit>`, and
`bcm_bootstate` shows the other slot booted with commit flag 0.

- Web UI: `http://192.168.1.1/` (redirects to `http://expertwifi.net`, see
  patch 0015). If pages look empty or loop back to the login page, clear the
  browser's site data for `192.168.1.1`, `expertwifi.net`, `asusrouter.com`
  and `router.asus.com`, or use a private window.
- VLANs: Advanced Settings → LAN → VLAN, and Guest Network Pro for the
  networks.
- Back to official firmware: `reboot` or pull the power.
- Never run `bcm_flasher` while booted from the test image: it writes the
  inactive slot, which is your official fallback. Reboot to official first.
- To keep the test image permanently: `bcm_bootstate 5` (commit First) or `7`
  (commit Second), whichever holds it. You then have no automatic fallback.

If the router does not come back at all: pull power and start it again (boots
the committed official slot). Last resort is ASUS rescue mode (hold reset while
powering on, ASUS Firmware Restoration / TFTP); the boot chain is byte-identical
to stock, so it should be the stock one, but that has not been tried.
