# VLAN support for ASUS TUF-AX3000 V2 — research notes

Goal: VLAN support on a TUF-AX3000 V2 without installing Asuswrt-Merlin.

## 1. Starting point

| | |
|---|---|
| Router | ASUS TUF Gaming AX3000 V2 (`TUF-AX3000_V2`) |
| Latest stock firmware | 3.0.0.4.388_24049 (2026-09-14) |
| SoC | Broadcom BCM6756 rev a0+, NAND, squashfs |
| Kernel / BSP | Linux 4.19.183, Broadcom SDK 5.04L.02p1 |
| Extra hardware | BCM53134 external switch (`SWITCH2`), BCM84880 2.5G PHY (`EXT_PHY`) |

ASUS's VLAN feature ("Guest Network Pro" / "Network", LAN → VLAN with trunk/access
ports) only exists in the 3.0.0.6.102 firmware branch. ASUS has never released
3.0.0.6.102 for the TUF-AX3000 V2 — every TUF build is 3.0.0.4.388.x.
Merlin does not support this model either (no prebuilt blobs for it in any branch).

## 2. Approach A — stock firmware + USB startup hook (works today)

Code: [`../usb-approach/`](../usb-approach/)

Stock ASUSWRT exposes SSH and a persistent `/jffs`, but runs no user scripts at boot.
[jacklul/asuswrt-scripts](https://github.com/jacklul/asuswrt-scripts) restores that via
an "asusware" package on a USB stick that the firmware auto-starts on mount
(`asusware-usb-mount-script`), which then runs `/jffs/scripts/usb-mount-script`.

- `vlan.sh` — creates `brvlan20` (192.168.20.1/24), moves *access* ports out of `br0`,
  adds 802.1Q sub-interfaces (`ethX.20`) for *trunk* ports, NAT to WAN, isolation from
  LAN, management lockout. `check` runs every minute via `cru` and re-applies anything
  the firmware tears down. Commands: `start|stop|check|status|ports`.
- `dnsmasq.conf.add` — DHCP/DNS for the VLAN; applied by jacklul's `custom-configs`.
- `usb-mount-script` — boot entry, once per boot.

Install:
1. Administration → System: enable SSH (LAN only) and "Format JFFS partition at next boot", reboot.
2. Plug a USB stick, then over SSH:
   ```sh
   curl "https://raw.githubusercontent.com/jacklul/asuswrt-scripts/master/asusware-usb-mount-script/asusware-usb-mount-script.sh" | sh
   curl "https://raw.githubusercontent.com/jacklul/asuswrt-scripts/master/install.sh" | sh
   /jffs/scripts/jas.sh install custom-configs
   ```
3. `scp vlan.sh usb-mount-script admin@<router>:/jffs/scripts/` and
   `scp dnsmasq.conf.add admin@<router>:/jffs/configs/`
4. `/jffs/scripts/vlan.sh ports` (move a cable, re-run) to map `ethX` ↔ physical port.
5. Put `ACCESS_PORTS="..."` / `TRUNK_PORTS="..."` in `/jffs/scripts/vlan.conf`,
   test with `vlan.sh start`, then reboot to confirm persistence.

Caveats: never put your own uplink port in the VLAN; USB stick must stay plugged;
if `ip link add ... type vlan` fails, the kernel lacks 8021q and Broadcom `vlanctl`
must be used instead; firmware updates can break the asusware hook.

Untested on real hardware at time of writing.

## 3. Approach B — port 3.0.0.6.102 VLAN firmware

### 3.1 Donor: ASUS ExpertWiFi EBR63

Only BCM6756 model found on 3.0.0.6.102 with VLAN. Firmware analysis
(`tools/fitls.py`, `tools/fitget.py`, `tools/dtdump.py`):

| | TUF-AX3000 V2 388_24049 | EBR63 3.0.0.6.102_46518 |
|---|---|---|
| FIT compatible | `chip=6756;rev=a0+;flash=nand` | identical |
| Kernel | 4.19.183 | 4.19.183 (different build) |
| SDK | 5.04L.02p1 | 5.04L.02p1 |
| Board DTBs in bootfs | 35 | 36, **includes `TUF_AX3000_V2`** |
| TUF DTB sha256 | `53e0a1f4…6975` | **byte-identical** |
| Signed | no | yes (`/security signature`, `BR63_sec`, `ASUSFLAG_IN_BOOT`) |
| LAN switch | SF2 + **BCM53134** | SF2 + **Realtek RTL8367S** (`rtl8367s.ko`, `/sbin/rtkswitch`) |

Conclusion: the 3006 kernel already boots the TUF board, but flashing the EBR63
image directly is not viable (wrong userspace/port model, wrong switch chip,
signed image with mismatched model name).

### 3.2 EBR63 GPL source (3.0.0.6.102_44547, 1.32 GB)

`downloads/GPL_EBR63_300610244547.zip` → `build/asuswrt/`

- Bundled toolchain: `release/src-rt-5.04axhnd.675x/toolchains/crosstools-arm-gcc-9.2-linux-4.19-glibc-2.30-binutils-2.32`.
- **`target.mak` contains an official `TUF-AX3000_V2` target** (`HND-96756_BASE`,
  `EXT_PHY="BCM84880" SWITCH2="BCM53134"`), without `MTLANCFG=y`.
  `BR63` has `MTLANCFG=y` (→ `RTCONFIG_MULTILAN_CFG`, 445 uses in rc/shared) plus
  `BUSINESS`, `DASHBOARD`, `CAPTIVE_PORTAL`, `SECUREBOOT=y`, `NEW_SWITCH_ORDER=y`.
- rc/shared source has TUF-AX3000_V2 board code (`init-broadcom.c`, `watchdog.c`,
  `defaults.c`, `model.c`, …).
- Wi-Fi driver is a per-chip blob (`router-sysdep/hnd_extra/prebuilt/wl.o`), so it
  applies to the TUF too.

### 3.3 The blocker: closed `rc/prebuild/broadcom.o`

Closed objects in `release/src/router/rc/prebuild/` are compiled **for BR63**:
`broadcom.o`, `sdn-interface-broadcom.o`, `amas_*.o`, `ate-broadcom.o`, …

`broadcom.o` contains the VLAN switch layer (`apg_switch_vlan_set`,
`apg_switch_vlan_unset`, `apg_switch_isolation`, `apg_create_eth_vlan`,
`portmask_remap`) and LED/PHY code. In BR63's build:
- the VLAN functions drive the Realtek switch via `rtkswitch` commands;
- there is no TUF code (`ex53134`, `GetExtPhyStatus`, `led_extphy_gpio`, `LED_EXTPHY`
  exist in stock TUF `rc` but not in this object).

### 3.4 Merlin

Branch `3006.102-wifi6` has per-model prebuilts for 17 models, none for TUF-AX3000 V2.
Every VLAN-capable model's `broadcom.o` (GT-AX6000, RT-AX86U Pro, RT-AX88U Pro,
GT-AXE16000, BE models, XT12…) implements `apg_switch_*` via `rtkswitch` — i.e. a
Realtek switch. Nothing reusable for BCM53134. (`tools/relsum2.py` dumps called
symbols + string constants per function from a relocatable `.o`.)

### 3.5 Reusable building blocks

1. **ASUS BCM53134 802.1Q helpers** (open source, written for EBG19, disabled):
   `release/src/router/rc/sysdeps/init-broadcom.c` — `enable_ext_53134_8021qvlan()`,
   `add_ext_53134_vlan()`, `read_ext_53134_vlan()`. They use
   `ethswctl -c pmdioaccess` on registers 0x3400 (802.1Q enable), 0x0580/0x0581/0x0583
   (VLAN table rw-ctrl / index / entry: fwd bits 0–8, untag bits 9–17).
   Stock TUF firmware ships `/bin/ethswctl` with `pmdioaccess`.
2. **`rtkswitch` command contract** (open source):
   `release/src/router/shared/sysdeps/broadcom/rtkswitch.c` — 36 set VID, 37 set prio,
   390/3900/3902 create VLAN, 3901 reset VLAN, 391/3911 set PVID, 395x accept types,
   398/3980 QoS, 399 dump. Implementing a BCM53134 backend for this contract lets the
   closed `apg_switch_*` logic drive the TUF's switch unchanged.
3. **Linux `drivers/net/dsa/b53`** (GPL) — register definitions for the BCM53xx
   family incl. 53134: PVID (`B53_VLAN_PORT_DEF_TAG`), VLAN control, table access.

### 3.6 Plan

1. Baseline: build `TUF-AX3000_V2` target from the 3006 tree unchanged. Identify
   which BR63-only prebuilts break or mis-behave.
2. Enable `MTLANCFG=y` for the TUF target.
3. Replace the hardware layer: TUF `rtkswitch` backend on BCM53134 + SF2;
   TUF port map for `portmask_remap`; restore TUF LED/PHY functions.
4. Only flash with a serial (UART) console attached for recovery.

## 4. Build log

Environment: `docker/Dockerfile` (Ubuntu 20.04), `./build.sh build TUF-AX3000_V2`.
The GPL tree is a local git repo (`build/asuswrt`, commit 1 = pristine); every
source change is exported to [`../patches/`](../patches/).

Gotchas found getting the vendor build system to run:

| Symptom | Cause | Fix |
|---|---|---|
| `xxd is required`, pyelftools/openssl checks | missing host packages | added to Dockerfile |
| `fatal: empty ident name` | build scripts call git | git identity in image |
| `Could not retreive version from automake` | toolchain `usr/bin` first in PATH shadows host autotools with broken copies | toolchain appended to PATH |
| `cc1: libisl.so.15: cannot open` | toolchain binaries have RPATH `/home/defjovi/temp3/toolchain/...` (ASUS build host) | entrypoint symlinks that path to the bundled toolchains |
| model settings ignored | real target file is `buildtools/target.mak.3004`; `release/src-rt/target.mak` is unused. Model vars are also cached in `src-rt-5.04axhnd.675x/.config` | patch `target.mak.3004`; delete `.config` after changing it |
| kernel re-config skipped | stamps `build/.done_pre_kernelbuild`, `kernel/linux-4.19/.pre_kernelbuild` | delete stamps |

TUF-specific gaps in the BR63 GPL:

| # | Gap | Resolution |
|---|---|---|
| 0001 | `net/netfilter/deDupTx/deDupTx.o` (closed, ROUTERBOOST) not shipped | `ROUTERBOOST=n` for TUF (Router Boost gaming feature dropped) |
| 0002 | `rc/prebuild/agg_brcm.o` (closed, LACP/BONDING) not shipped | `LACP=n BONDING=n` (link aggregation dropped) |
| 0003 | `rc/prebuild/amas_wgn.o` not shipped; closed objects were compiled with BR63's `MULTILAN_CFG` | `MTLANCFG=y` — enables VLAN/SDN and turns off `AMAS_WGN` |
| 0004 | `exec_uu` (closed, UU game accelerator) | `UUPLUGIN=n` |
| 0005 | rc link: `bcm53134_led_control`, `lan_phy_led_pinmux`, `get_ext_phy_id`, `extphy_bit_op` — TUF board code missing from BR63 `broadcom.o`/`ate-broadcom.o`/`private.o` | extracted from the **TUF 388 GPL** (`GPL_TUF_AX3000_V2_300438823785`) blobs into `rc/prebuild/tuf_hw.o` by [`../tufhw/extract.sh`](../tufhw/extract.sh) and linked only for `BUILD_NAME=TUF-AX3000_V2` |

| 0006 | httpd link: IFTTT/Alexa, Instant Guard (`ig_*`) closed parts | disabled TUF-only cloud features: `ALEXA IFTTT GOOGLE_ASST INSTANT_GUARD NOTIFICATION_CENTER SMARTSYNCBASE WEBDAV =n`, `APP="none"` |
| 0007 | U-Boot link: BR63 prebuilt `dt_parsing.o` calls Realtek `rtl8367s_init` | replaced the 8 prebuilt objects in `bootloaders/obj/{uboot,nand_spl}` with the TUF 388 GPL ones (3 of 8 differ) |
| — | `bootloaders/obj/emmc_spl` fails (no prebuilt objects) | open; irrelevant for NAND, but stops `make` after the NAND image is written |

### First image (2026-10-20)

`bootloaders/obj/binaries/TUF-AX3000_V2_3.0.0.6_102_40000-g7705a62_nand_squashfs.pkgtb` (55 MB)

| Check | Result |
|---|---|
| FIT description / compatible | `TUF-AX3000_V2`, `chip=6756;rev=a0+;flash=nand` — same as stock |
| Signature | none (stock TUF is unsigned too) |
| Extra FIT prop | `asus = ASUSFLAG_IN_BOOT` (3006-era; also on EBR63) — effect on 388 updater unknown |
| `fdt_TUF_AX3000_V2`, `fdt_uboot` | byte-identical to stock |
| ATF, U-Boot | rebuilt, differ from stock → **plan: swap in stock TUF ATF/U-Boot before any flash** |
| rc VLAN/SDN code | present (same marker count as EBR63; stock TUF has none) |
| Web UI | `Advanced_VLAN_Profile_Content.asp`, `Advanced_VLAN_Switch_Content.asp`, `SDN.asp` |
| `tuf_hw.o` functions | linked in rc |
| Kernel modules | 127 (= stock), incl. `wl`, `bcm_enet`, `archer`, `pktflow` |

**Known gap:** the closed `apg_switch_*` VLAN code runs `rtkswitch <cmd>`
(Realtek backend, `/dev/rtkswitch`); the TUF image has neither the applet nor the
driver, so per-port wired VLAN programming is a no-op. Next step: a TUF
`rtkswitch` backend (BCM53134 via `ethswctl pmdioaccess` + Linux 802.1Q on the
per-port netdevs).

How `tuf_hw.o` is made: `objcopy --keep-global-symbol=<fn>` localizes every
other global of the 388 object (so nothing clashes with the BR63 objects), then
`ld -r --gc-sections -u <fn>` drops code the function can't reach. Remaining
undefined symbols are libc / libshared / libnvram / wl functions that rc already
links. Decoded behaviour (via `tools/armdis.py` + `tools/datadump.py`):

- `lan_phy_led_pinmux(force)`: `sw 0xff800554 0`; `sw 0xff800558 (force?0x4012:0x2012)`; `sw 0xff80055c 0x21`
- `bcm53134_led_control(mode)`: mode 0 → `ethswctl -c pmdioaccess -x 0x0018 -l 2 -d 0` and `-x 0x001a … -d 0`; mode 1 → `-x 0x001a … -d 0`; mode 2 → no-op
- `get_ext_phy_id()`: probes the BCM84880 via `ethctl_phy_op`, sets nvram, uses `start_envrams`/`popen`
- `extphy_bit_op(reg,val,wr,start,end,wait_ms)`: masked read/write on the ext PHY

Kernel builds completely with 0001. After changing feature flags, untracked
`*.o` under `rc/`, `shared/`, `httpd/` are deleted
(`git ls-files -o --exclude-standard`) so nothing mixes old and new flags; shipped
prebuilts are tracked in git and untouched.

Remaining closed `rc/prebuild` objects with no source for TUF-relevant options:
none found besides the above (others are for QCA/Lantiq/Ralink/Realtek/DSL or
other models: `cfe.o`, `ledg.o`, `rtkmonitor.o`, `rpmac.o`).

Notes: `cp: cannot stat .../bcm96756/main/src/router-sysdep/hnd_extra/prebuilt/*`
during "hnd_router platform work" is non-fatal; the real blobs live in
`router-sysdep/hnd_extra/prebuilt/` and `bcmdrivers/*/impl*/`. `rdpa/bdmf/wfd`
belong to Runner-based chips, not BCM6756.

## 5. Sources

- ASUS TUF-AX3000 V2 firmware: https://www.asus.com/supportonly/tuf-ax3000%20v2/helpdesk_bios/
- ASUS EBR63 firmware/GPL: https://www.asus.com/supportonly/ebr63/helpdesk_bios/
- ASUS VLAN FAQ: https://www.asus.com/support/faq/1049415/
- Guest Network Pro FAQ: https://www.asus.com/support/faq/1049414/
- jacklul/asuswrt-scripts: https://github.com/jacklul/asuswrt-scripts
- Merlin: https://github.com/RMerl/asuswrt-merlin.ng (branch `3006.102-wifi6`)
- SNBForums on 3.0.0.6.102 VLAN models: https://www.snbforums.com/threads/are-all-asus-routers-on-the-3-0-0-6-102-codebase-guaranteed-to-support-vlan-management-guest-network-pro.92855/
