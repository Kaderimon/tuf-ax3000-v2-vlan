# VLAN support for ASUS TUF-AX3000 V2 — research notes

Goal: VLAN support on a TUF-AX3000 V2 without installing Asuswrt-Merlin.

Status (2026-10-23): approach B runs on the router as a one-time-boot test
image (`g69420e1`). VLANs over a trunk port work (§6). How to build and try it:
[`../README.md`](../README.md). Procedure and bring-up log: §5.

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

Outcome:
1. Done (§4, 0001–0007).
2. Done (0003).
3. Done differently. There is no `rtkswitch` backend. Instead, `apg_switch_*`
   is replaced so that Linux bridges and 802.1Q do the VLAN work (0008, design
   note in §4). TUF PHY/LED functions are restored (0005, 0008).
4. Replaced by the dual-image one-time boot (§5). No serial console was needed
   so far.

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

### Patches 0008–0009 and first clean build (2026-10-20)

| # | Problem | Fix |
|---|---|---|
| 0008 | BR63 `shared/prebuild/private.o`: `hnd_get_phy_status/speed/duplex/mib` are one-instruction jumps to `rtk_get_phy_*` (Realtek) and take an **int port**, while TUF callers (`wanduck.c` WAN cable detection, `ethmon.c`, `watchdog.c`) pass an **ifname** → WAN would always look unplugged | `shared/sysdeps/broadcom/tuf_phy.c`: sysfs (`operstate`, `speed`, `duplex`, `statistics/*`) like the TUF 388 firmware; small ints are mapped to the port's ifname instead of dereferenced. BR63 symbols weakened with `objcopy --weaken-symbol` |
| 0008 | BR63 `broadcom.o`: `GetPhyStatus` calls the above with int ports; `apg_switch_vlan_set/unset/isolation` drive `rtkswitch` | `rc/tuf_vlan.c`: `GetPhyStatus` over the TUF port map (modelled on the open QCA version, 3006 structs); `apg_switch_*` disable BCM hw-switching once so Linux bridges/802.1Q/`brport/isolated` are authoritative (TUF front ports are netdevs; `amas_apg.o` already does access=`brctl addif`, trunk=`vconfig`). BR63 symbols weakened |
| 0008 | `rc/Makefile` copied BR63 `prebuild/init-broadcom.o` and `prebuild/ate.o` although full source exists → TUF board init (`init_switch_pre/init_switch` for BCM53134, `generate_switch_para`, jumbo frames, `set_wan_tag`, LEDs) was missing | compile both from source for `TUF-AX3000_V2` |
| 0009 | rebuilt ATF/U-Boot differ from stock | `bootloaders/stock_boot/TUF-AX3000_V2/{armtf.bin,u-boot-nodtb.bin,dt.dtb}` from stock 388_24049, copied in by `bootloaders/Makefile` (`image_linux_fit`) before the Linux FIT is assembled |
| 0009 | `emmc_spl` has no prebuilt objects → `make.uboot` loop aborted before copying images / finishing | `BCM_FLASH_LAYOUT_OPTIONS="options_6756_nand"` for TUF in `build/make.uboot` |

Why not reuse the 388 `GetPhyStatus` binary: 3006 added `POE_INFO poe_info` to
`phy_info` and `seq_no/ui_display/poe_seq_no` to `phy_port`, so the 388 code
would write with the wrong stride and overflow its `phy_port_mapping` buffer.

Result: `make TUF-AX3000_V2` exits 0. Image (superseded by g5361b12 below)
`TUF-AX3000_V2_3.0.0.6_102_40000-g0c9a8c8_nand_squashfs.pkgtb` (sha256 in `out/SHA256SUMS`):

| Check | Result |
|---|---|
| ATF, U-Boot, U-Boot DTB, `fdt_TUF_AX3000_V2` | byte-identical to stock 388_24049 |
| `tuf_vlan`, `tuf_phy`, TUF `init-broadcom` code | present |
| VLAN/SDN code, VLAN web pages | present |
| `vconfig`, `ethswctl`, `CONFIG_VLAN_8021Q=y` | present |

Remaining known gaps: BR63 LED helpers (`setAllLed*`, `setNetLed`) still use
`rtkswitch` (LAN LEDs may ignore LED-off mode); compiler warns about
`conflicting types` for `create_sdn_ifcap`, `start_nbr_monitor`,
`stop_cfgnewob`, `stop_conn_diag_ss` in ASUS's own sources — reviewed:
implicit declarations of `void` functions used before their definition, no
closed callers, return values unused; harmless.

### Static verification and patch 0010 (2026-10-21)

`tools/verify.sh <new.pkgtb> <stock.pkgtb>` checks an image without flashing
(work files in `out/verify/`; needs the `tuf-fw-builder` docker image for `lzop`):

| Check | Tool |
|---|---|
| outer FIT image sha256 | `pkgsplit.py` |
| ATF, U-Boot, U-Boot DTB, `fdt_TUF_AX3000_V2` byte-identical to stock | `fitget.py` + `cmp` |
| kernel in image == build tree `arch/arm/boot/Image` | SDK `hostTools/prebuilt/lzop` |
| all modules: same vermagic; every undefined symbol exported by the kernel (`System.map`) or another module | `kocheck.py` |
| every ELF finds its `NEEDED` libs and resolves its strong undefined symbols in its load scope; reports problems absent from stock | `elfcheck.py`, `elfdiff.py` |
| files in stock but not in the new rootfs | `comm` |

First run found three programs broken that work on stock (stock: none):

| # | Problem | Fix |
|---|---|---|
| 0010 | `lld2d` needs `libbcm_crc.so` (not built): `lltd.arm/Makefile` picks `lld2d.6755axhnd` only for 5.02 SDK flags, so 6756 got `lld2d.hnd` | add `HND_ROUTER_AX_6756`; `lld2d.6755axhnd` has the same dependencies as stock TUF / EBR63 `lld2d` |
| 0010 | prebuilt EBR63 `aaews`/`mastiff` import `vpns_use_tunnel`, `is_wgs_use_tunnel`, defined in `shared/misc.c` only with `RTCONFIG_UAC_TUNNEL` (EBR63 business/multisite option, off for TUF) → lazy-binding crash when reached (ASUS app remote access) | `return 0` stubs in the `#else` branch (no UAC tunnel exists) |

Reviewed, not a problem: busybox `switch_root`/`pivot_root`/`chroot`/`fuser`
are missing (also missing in stock EBR63; rc only uses them with
`RTCONFIG_TEMPROOTFS`, off for TUF as on stock); `ifenslave` (`BONDING=n`),
WebDAV/AiCloud/Download Master/IFTTT/Alexa files (0006), mobile QIS and EULA
pages (unreferenced; absent in EBR63 too), `rom/etc/ssl/certs/letsencrypt.pem`
(unreferenced; `ca-certificates.crt` present).

Result: image `TUF-AX3000_V2_3.0.0.6_102_40000-g5361b12_nand_squashfs.pkgtb`,
all checks pass. With 0011: `…-gb32cae9_nand_squashfs.pkgtb` (sha256
`0e5457b7…469e`), all checks pass; `rc` contains "auto-commit disabled" and no
longer the "reset bootstate" strings.

### Patches 0011–0017: found on the router (2026-10-23)

0011 prepares the test image for the dual-image procedure (§5). The rest were
found by testing on the router (§5.3). Nearly all have the same cause: a
**closed object compiled for the EBR63** makes an assumption the TUF build does
not share. It may check the EBR63 model name, rely on an EBR63 build option
(`BUSINESS`, `CAPTIVE_PORTAL`), or expect the ExpertWiFi web UI. The static
checks (§4) cannot find these, because every symbol resolves and the program
just behaves differently at run time. The fix is always to adjust the open side,
or to patch the closed object in place with `tools/patchinsn.py` (one ARM
instruction, old value verified) or `tools/patchstr.py` (one NUL-terminated
string, must occur exactly once).

| # | Problem | Fix |
|---|---|---|
| 0011 | `sync_boot_state()` would commit the test image as soon as its services start, removing the power-cycle fallback to stock | early return for `TUFAX3000_V2` (see §5.1) |
| 0012 | web UI login → 404 on `/index.html?current_theme=white`. Prebuilt EBR63 `libwebapi/prebuild/priv_webapi.o` `get_ui_support_info()` adds `"BUSINESS": 1` unconditionally, so `state.js` redirects to the ExpertWiFi UI, which TUF does not ship (`httpd`'s own flag is correctly gated on `RTCONFIG_BUSINESS`) | `tools/patchinsn.py priv_webapi.o 25c8 e3a00001 e3a00000` (`mov r0,#1` → `#0` before the `BUSINESS` key) |
| 0013 | VPN server/client pages broken, `top.cachedData` undefined in `httpApi.js`. 3006 `httpApi.js` keeps its cache on `top`, which only the BUSINESS wrapper defines; `Advanced_VPN*_Content.asp` iframes `VPN/vpn*.html` and does not load `httpApi.js` | `httpApi.js`: `if(!top.cachedData) top.cachedData = cachedData;` |
| 0014 | Adaptive QoS / Bandwidth Monitor pages are empty 200 responses. `httpd` serves DPI pages only if `dump_dpi_support()`; prebuilt EBR63 `bwdpi_source/asus/prebuild/libbwdpi.so` has a per-model table with only `ExpertWiFi_EBR63` (stock TUF lib: `TUF-AX3000`, `TUF-AX3000_V2`, same 9-entry bitmap, all 1) | `tools/patchstr.py libbwdpi.so ExpertWiFi_EBR63 TUF-AX3000_V2`. Engine binaries (`tdts.ko`, `shn_ctrl`, `dcd`, `tcd`, `wred`, `tdts_rule_agent`) are byte-identical to stock; `model.enc` differs (8 KiB EBR63 vs 2 KiB stock), left as EBR63 |
| 0015 | client list, system status, QoS data empty while logged in; every `appGet.cgi` returns the login redirect. Prebuilt BR63 `httpd/prebuild/web_hook.o` `referer_check()` (built with `RTCONFIG_BUSINESS`) accepts a Referer only equal to the LAN IP or starting with `expertwifi.net` (`strncmp` len 14); the open code redirects the browser to `www.asusrouter.com`. Patching the closed string is not possible in place (4 bytes longer, neighbours in use) | `shared.h`: `DUT_DOMAIN_NAME` = `expertwifi.net` for `TUFAX3000_V2` (as BUSINESS). Same define feeds `httpd` (`ZVDOMAIN_NAMEVZ` in the dicts), `/etc/hosts`, dnsmasq, wanduck; `gencert.sh` already lists `expertwifi.net`. Web UI: `http://expertwifi.net` or the LAN IP |
| 0016 | client list opens but shows 0 clients. Prebuilt BR63 `networkmap` was built with `RTCONFIG_CAPTIVE_PORTAL`, so its shared-memory `CLIENT_DETAIL_INFO_TABLE` has `subunit[255]` (260644 bytes, `movw 0xfa24`); our `httpd` (no CAPTIVE_PORTAL) expected 260388 bytes and read `ip_mac_num` 255 bytes too early | `networkmap.h`: `subunit[]` also for `TUFAX3000_V2` |
| 0017 | no VLAN tab (page itself works). Closed `libwebapi` `RCisSupport("mtlancfg")` returns `is_amas_support() ? 2 : 0`; closed BR63 `sw-hw-auth/prebuild/hw_auth.o` `getAmasSupportMode()` only whitelists `BR63`/`EBR63`/`ExpertWiFi_EBR63` → `amas_support=0` (AiMesh off too) | `tools/patchstr.py hw_auth.o ExpertWiFi_EBR63 TUF-AX3000_V2` (the string is shared with the ASUS remote-access tunnel whitelist, which now accepts TUF too) |

Other closed objects that still contain `BR63` / `EBR63` strings, not examined
yet: `rc/prebuild/init-broadcom.o` (unused for TUF since 0008),
`rc/prebuild/obd.o`, `rc/prebuild/obd_eth.o` (AiMesh onboarding),
`cfg_mnt/prebuild/cfg_server`, `cfg_client`, `cfg_newob` (AiMesh). They are the
first suspects if AiMesh pairing fails. `ExpertWiFi_EBR63` appeared only in
`hw_auth.o` and `libbwdpi.so`, and both are patched now.

### Design decision: hardware switching off when VLANs are used

`apg_switch_vlan_set()` / `apg_switch_isolation(1, …)` in `rc/tuf_vlan.c` run
`ethswctl -c hw-switching -o disable` once; it stays off until reboot.
Nothing changes until a VLAN or port isolation is configured.

Why: the SF2 / BCM53134 switches run VLAN-unaware by default.

- Trunk port: if L1 is in `br0` untagged and `eth1.20` is in the VLAN 20
  bridge, tagged VID 20 frames from L1 could be forwarded by the switch straight
  to L2 (also in `br0`), never reaching Linux → leak between VLANs.
- Isolation: `/sys/class/net/<if>/brport/isolated` is a Linux bridge flag the
  switch does not know about.

With hw-switching off every frame reaches the Linux bridges, so 802.1Q and
isolation are enforced exactly.

Cost: only wired LAN-port ↔ LAN-port traffic. WAN ↔ LAN and Wi-Fi ↔ wired
already pass through the CPU on this router. Unknown how much: the BCM6756's
Archer accelerator / flow cache may still accelerate bridged flows (then close
to gigabit), or a sustained LAN-LAN copy may load one CPU core and drop below
gigabit. Must be measured.

Alternatives if the cost matters:

1. Disable hw-switching only for trunk ports / isolation; keep it for plain
   access-port VLANs, relying on the Broadcom enet driver limiting hardware
   forwarding to ports in the same Linux bridge (believed, not verified on
   BCM6756). Small change; needs a leak test.
2. Program 802.1Q into the switches (SF2 + BCM53134: 802.1Q enable, VLAN table,
   per-port PVID) via `ethswctl`, using ASUS's `add_ext_53134_vlan()` helpers
   and the Linux `drivers/net/dsa/b53` register layout. Full-speed hardware
   enforcement; most work and highest risk (a mistake can cut LAN).

Plan: ship as is for the first hardware test; measure; do (1) if needed, (2) later.

### Build notes

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

## 5. Flashing and hardware testing

### 5.1 Dual-image boot

- NAND holds two image slots, First and Second (pureUBI). The loader TPL is not
  part of the `.pkgtb` and is never rewritten. Never flash a `*_loader.pkgtb`.
- The TPL boots the **committed** slot. If the reset reason has
  `BCM_BOOT_REASON_ACTIVATE` (0x1) after a software reset, it boots the other
  slot once instead. It overwrites the reset reason on every boot, so any later
  reset returns to the committed slot (`bcmbca/board_tpl.c`).
- `/bin/bcm_bootstate` (stock and this build) reads and sets this state:
  `5` / `7` commit First / Second, `6` / `8` boot First / Second once (writes
  0x1 to `/proc/bootstate/reset_reason`). After a power-on reset
  (`reset_status` 0x80000000) the kernel reads `reset_reason` back as ffffffff.
  So after arming, `bcm_bootstate` can still show the old "Reboot Partition",
  but the one-time boot works. Confirmed on the router in both directions.
- `bcm_flasher <file>` (stock and this build) writes the **inactive** slot and
  does not commit it. The web updater runs `bcm_flasher … 1`, which commits.
- Stock `rc` commits whatever it booted (`sync_boot_state()`) once all services
  have started. Patch 0011 disables that in this build, so the test image stays
  uncommitted until you commit it by hand.

### 5.2 Procedure

Requirements: SSH enabled (LAN only), and **Auto Firmware Upgrade off**
(Administration → Firmware Upgrade, nvram `webs_update_enable=0`). Even then,
`watchdog` checks for updates around 2 AM, so flash and test in one session.
Copying a file to the router: `cat f | ssh admin@192.168.50.1 'cat > /tmp/f'`
(no scp/sftp).

1. Be booted from the committed official slot X (`bcm_bootstate`: Booted X,
   X commit flag 1).
2. `bcm_flasher /tmp/fw.pkgtb` writes slot Y. Check: X commit 1, Y commit 0.
3. Arm the one-time boot into Y (`8` for Second, `6` for First), then `reboot`.
   Do not power-cycle, because the boot reason only survives a software reset.
4. Check: Booted Y, Y commit 0, `nvram get extendno` = `40000-g<commit>`.
5. To go back, `reboot` or power-cycle. To keep the test image, commit Y
   (`5`/`7`); after that there is no automatic fallback.

Never run `bcm_flasher` while booted from the uncommitted test image. The
inactive slot is then the official one, and it would be overwritten.

nvram (settings, SSH login) is shared by both slots and kept across the flash.
The test image ran on nvram from 388; a factory reset was not needed.

Rescue: the boot chain (ATF, U-Boot, DTBs) is byte-identical to stock (0009),
so ASUS rescue mode (hold reset while powering on, ASUS Firmware Restoration /
TFTP) should be the stock one. It has not been tried. A serial console
(USB-UART on the board header) was not needed so far.

### 5.3 Bring-up log (2026-10-23, no serial console)

Starting state: official firmware in First (committed, seq 3), Second seq 2.

| Image | Added | Result on the router |
|---|---|---|
| `gb32cae9` | 0011 | One-time boot into Second worked. Working: kernel (no oops), WAN DHCP + 2.5G port detection (`tuf_phy.c` via `wanduck`), LAN DHCP, both Wi-Fi bands, port link via sysfs, SSH login kept. Broken: web UI shows 404 after login → 0012 |
| `gdeca987` | 0012 | UI loads. VPN pages broken (→ 0013), QoS / Bandwidth Monitor blank (→ 0014), SSID shown empty, client list and System Status empty |
| `g0274168` | 0013, 0014 | VPN and QoS pages render. Client list, System Status and QoS data still empty: every `appGet.cgi` request returns the login redirect → 0015 |
| `g16a7487` | 0015 | System Status and SSID work (the empty SSID was the same `appGet.cgi` failure, not nvram). In a normal browser window only after clearing site data, because cached JS and the `www.asusrouter.com` redirect come from older images. Client list opens with 0 clients → 0016. VLAN page reachable by URL but no menu tab → 0017 |
| — | — | ASUS **Auto Firmware Upgrade** ran: wrote official 388_24049 into Second (the test slot) and committed it. Official firmware then in both slots, nothing lost. From here, official 388_24049 is the committed fallback in Second and test images go into First (`bcm_bootstate 6`) |
| `g69420e1` | 0016, 0017 | Client list, VLAN tab and AiMesh menu work, `amas_support=3`. VLAN trunk test passes (§6) |

`gdfd7466` (0016 only) was built but not flashed.

Note on `amas_support`: rc clears it at boot. It is filled in on the first
`is_amas_support()` call (e.g. when the web UI loads), so an empty value right
after boot is normal.

### 5.4 Open issues

- AiMesh pairing not tested; closed BR63 `cfg_mnt` / `obd` objects unchecked (§4).
- Checks from the list below that are still open, and the firewall follow-ups in §6.
- Features removed, or expected to misbehave, compared with stock: §5.5.
- LAN LED-off mode: the BR63 LED helpers still call `rtkswitch`.

Checks, in order (results in §6):

1. Basics: WAN gets an address (exercises `tuf_phy.c` via `wanduck`), LAN
   DHCP, both Wi-Fi bands, web UI loads, port status page shows link/speed
   (`GetPhyStatus`). **Done, works.**
2. Access-port VLAN: one LAN port in a new VLAN; client gets the VLAN's DHCP
   and cannot reach the main LAN.
3. Trunk port to a managed switch: tagged VLAN works, untagged main LAN works.
   **Done, works.**
4. Leak test: tagged frames sent into the trunk port never appear on other
   ports (`tcpdump -e` on a client of another port).
5. Throughput: `iperf3` between two wired LAN clients before and after
   creating a VLAN (cost of hw-switching off); watch CPU with `top`.
6. Cosmetic: LED-off mode (BR63 LED helpers still call `rtkswitch`).

### 5.5 Differences from stock 388_24049: what is missing or may not work

**Removed to make the build work.** Their closed parts are not in the EBR63
GPL, so the options are off in `target.mak.3004` (patches 0001, 0002, 0004,
0006). The features are not in the image and their menu entries are gone:

| Feature (stock TUF) | Option | Patch | Files stock has, image lacks |
|---|---|---|---|
| Router Boost (gaming packet duplication) | `ROUTERBOOST` | 0001 | kernel `deDupTx` |
| Link aggregation (LACP / bonding of two LAN ports) | `LACP`, `BONDING` | 0002 | `ifenslave` |
| UU game accelerator (NetEase) | `UUPLUGIN` | 0004 | — (downloaded at run time) |
| Alexa, IFTTT, Google Assistant | `ALEXA`, `IFTTT`, `GOOGLE_ASST` | 0006 | `Advanced_Smart_Home_{Alexa,IFTTT}.asp` |
| Instant Guard (ASUS one-tap VPN app) | `INSTANT_GUARD` | 0006 | — |
| AiCloud (web access to USB disk, share links), WebDAV | `WEBDAV`, `APP="none"` | 0006 | `lighttpd` + `mod_*.so`, `cloud_*.asp`, `aicloud_qis.asp` |
| Smart Sync (USB disk ↔ ASUS WebStorage / Dropbox / Google Drive / FTP / Samba) | `SMARTSYNCBASE` | 0006 | `asuswebstorage`, `dropbox_client`, `google_client`, `ftpclient`, `sambaclient`, `usbclient`, `webdav_client`, `inotify` |
| Download Master / USB app install | `APP="none"` | 0006 | `app_*.sh`, `chk_app_state`, `run_app_script` |
| Security change notification page | (0006) | 0006 | `Main_Security_Change_Notification.asp` |

0006 also turned off `NOTIFICATION_CENTER`, but the built `.config` still
has `RTCONFIG_NOTIFICATION_CENTER=y` (something else enables it). The
notification center is therefore built in, but not tested.

Other files stock has and the image does not, without a visible feature:
`hw_accel_dump.sh` (debug), `check_spectrum.sh`, `switch_root` /
`pivot_root` / `chroot` / `fuser` (unused, see §4), mobile QIS pages and EULA
pages, `letsencrypt.pem` (unused). Full list:
`comm -23` of `out/verify/stock.lst` and `new.lst`.

**Present but likely to misbehave** (known cause, not yet seen):

| Area | Why |
|---|---|
| AiMesh (pairing, backhaul, node config) | `cfg_server` / `cfg_client` / `cfg_newob` and `obd*.o` are closed EBR63 builds that still contain `BR63` checks (§4). Only the menu was verified |
| LAN LED-off / LED control | the BR63 LED helpers (`setAllLed*`, `setNetLed`) in `broadcom.o` call `rtkswitch` (Realtek), which the TUF lacks. LAN LEDs may ignore the LED-off setting |
| Wired LAN↔LAN speed with VLANs | once a port is set to Access or single-VID Trunk, `apg_switch_*` turns BCM hardware switching off until reboot (§4 design note). Throughput not measured |
| Adaptive QoS / AiProtection / Traffic Analyzer | pages render (0014), but the DPI engine runs with the EBR63 `model.enc` and has not been checked to classify traffic |
| ASUS Router app, remote access (`aaews`, `mastiff`) | closed EBR63 programs; the tunnel calls they import are stubs (0010). Untested |
| Firmware update from the web UI / auto-upgrade | the online check compares against official TUF firmware (3.0.0.4.388), and the outcome from a 3.0.0.6 image is unknown. The web updater commits what it flashes. Keep auto-upgrade off (§5.2) |
| `router.asus.com` / `www.asusrouter.com` | the router's name is now `expertwifi.net` (0015). Old bookmarks and the stock name do not resolve to the UI |
| Closed EBR63 code in general | 0012–0017 were all found by clicking through the UI. More code paths that check the EBR63 model or `BUSINESS` / `CAPTIVE_PORTAL` options may remain in parts not yet used |

**Built in but not tested yet:** IPv6, Dual WAN / USB modem, USB storage
(Samba, FTP, media server, Time Machine), printer server, WireGuard / OpenVPN
/ IPsec clients and servers (the VPN pages render), Game Mode / Open NAT,
Parental Controls, AiProtection, Smart Connect / roaming, the access-port VLAN
(§5.4).

## 6. Hardware findings

### VLAN test results (2026-10-23, image g69420e1)

Setup: two SDN networks with VLAN IDs and DHCP, one TUF LAN port to an
802.1Q switch (TP-Link Easy Smart), one client per VLAN behind the switch
(access port, PVID = VLAN), main LAN untagged on the trunk. TUF ports left at
the UI default ("All"). Numbers refer to the checks in §5.

| Check | Result |
|---|---|
| 2 Access-port VLAN | not tested (no TUF port set to "Access") |
| 3 Trunk to managed switch | works: VLAN client is learnt in its `brN` via `ethX.VID` of the trunk port only, gets the VLAN's DHCP lease, has internet; main LAN on the same trunk untagged keeps working |
| 4 Leak | no traffic on the VLAN sub-interfaces of other ports (`ethY.VID` rx counters stay 0). Not done: `tcpdump -e` on a client of another port (no `tcpdump` on the router) |
| 4 hw-switching | still **Enabled** (`ethswctl -c hw-switching`) after creating VLANs with all ports on "All": `apg_switch_*` is not called in that mode, unlike the design note in §4 assumes. Harmless while every port carries every VLAN; must be rechecked once a port is set to "Access"/single-VID "Trunk" |
| 5 Throughput | not measured |
| Isolation | VLAN → main LAN, VLAN → other VLAN: blocked. VLAN → WAN: allowed. Main LAN → VLAN: **also blocked** (see below) |
| IPv6 | not tested (`ipv6_service=disabled`) |

### Firewall behaviour of the SDN code

| Finding | Detail |
|---|---|
| Port modes | Network → VLAN offers per LAN port only "All" (default: main LAN untagged + every VLAN tagged), "Access" (one VLAN untagged) and "Trunk" (main LAN untagged + one VID or all). There is no "main LAN only" mode. In "All" every LAN port and both radios (`eth5`/`eth6` = `wl0`/`wl1`) get `ethX.VID` in every VLAN bridge, so VLAN broadcasts reach every port tagged |
| Inter-bridge traffic | `handle_SDN_internal_access()` (`rc/firewall_sdn.c`) ends chain `SDN_IA` (jumped to from `SDN_FF`, before `FORWARD -i br0 -j ACCEPT`) with `-i br+ -o br+ -j DROP`, so main LAN → VLAN is dropped too. The only exception, `sdn_access_rl` (`<idx1>idx2`), always adds both directions. One-way access (main LAN may connect in, VLAN only answers) is not expressible in the UI |
| Router services from a VLAN | `update_SDN_iptables()` writes to `SDN_FI`: DHCP/DNS accept; if `ahs_sw` ("access host service") is off, drop `-d lan_ipaddr`; then `-m state --state NEW -j ACCEPT`. The router's own address **on the VLAN bridge** is not dropped, so every service bound to `0.0.0.0` is reachable from the VLAN: `dropbear` (22, incl. password login if enabled), `cfg_server` (7788), `wanduck` (18017/18018), `miniupnpd` (HTTP port), `infosvr` (udp 9999), SSDP 1900, avahi 5353, `eapd` (udp 59000). `httpd` binds `lan_ipaddr` only and `envrams` (5152) is dropped in `INPUT`, so those are safe |
| Manual rules | rules added with `iptables` at runtime are lost when rc rebuilds the firewall (observed within minutes; trigger not identified). This build calls no user script, so there is no supported way to keep them |

### Proposed follow-ups (not yet patched)

**(a) Generic fix: VLAN → router.** In `update_SDN_iptables()`, when `ahs_sw`
is off, also drop traffic to the bridge's own address
(`pmtl->nw_t.addr`) after the DHCP/DNS accepts, and accept tcp/53 there
(large DNS replies). Result: with "access host service" off, a VLAN client
can reach the router only for DHCP, DNS and ICMP (`INPUT_ICMP` runs before
`SDN_FI`). Matches what the UI option suggests; nothing site-specific.

**(b) User hook: `firewall-start`.** `shared/scripts.c` already has
`run_custom_script()` (runs `/jffs/scripts/<name>` if executable, unless
`jffs2_scripts=0`) and it is linked into rc, but nothing calls it except
`run_postconf("torrc")`. Proposal:

- call `run_custom_script("firewall-start", 0, wan_if, NULL)` at the end of
  `start_firewall()` and after each `handle_SDN_internal_access()` call in
  `rc/sdn.c`, so the script also runs when only the SDN rules are rebuilt;
- add default `jffs2_scripts=0` to `defaults.c` (off unless the user runs
  `nvram set jffs2_scripts=1; nvram commit`);
- semantics as in Asuswrt-Merlin, so existing documentation applies.

Example `/jffs/scripts/firewall-start` (site rules stay on the router, not in
the image; `brA` = exposed VLAN, `brB` = internal VLAN, interface names from
`brctl show`):

```sh
#!/bin/sh
for b in brA brB; do    # VLAN -> router: DHCP and DNS only
  iptables -I SDN_FI 1 -i $b -j DROP
  iptables -I SDN_FI 1 -i $b -p tcp --dport 53 -j ACCEPT
  iptables -I SDN_FI 1 -i $b -p udp -m multiport --dports 53,67 -j ACCEPT
done
# main LAN -> VLAN, one way (replies pass FORWARD's RELATED,ESTABLISHED rule)
iptables -I SDN_IA 1 -i br0 -o brA -p tcp --dport 22 -j ACCEPT
iptables -I SDN_IA 2 -i br0 -o brA -p icmp -j ACCEPT
iptables -I SDN_IA 3 -i br0 -o brB -j ACCEPT
```

The script must tolerate running more than once per boot (whether rc flushes
`SDN_FI`/`SDN_IA` before every call is not verified; if not, delete before
insert, `iptables -D … 2>/dev/null`). With (a) in place the `SDN_FI` part is
not needed.

Still open from the test: Access-port check (2) and hw-switching state after
it, `tcpdump -e` leak test on a client of another port, VLAN hopping from a
switch access port (send VID-tagged frames for other VLANs from the client),
throughput (5), LED-off mode (6).

## 7. Sources

- ASUS TUF-AX3000 V2 firmware: https://www.asus.com/supportonly/tuf-ax3000%20v2/helpdesk_bios/
- ASUS EBR63 firmware/GPL: https://www.asus.com/supportonly/ebr63/helpdesk_bios/
- ASUS VLAN FAQ: https://www.asus.com/support/faq/1049415/
- Guest Network Pro FAQ: https://www.asus.com/support/faq/1049414/
- jacklul/asuswrt-scripts: https://github.com/jacklul/asuswrt-scripts
- Merlin: https://github.com/RMerl/asuswrt-merlin.ng (branch `3006.102-wifi6`)
- SNBForums on 3.0.0.6.102 VLAN models: https://www.snbforums.com/threads/are-all-asus-routers-on-the-3-0-0-6-102-codebase-guaranteed-to-support-vlan-management-guest-network-pro.92855/
