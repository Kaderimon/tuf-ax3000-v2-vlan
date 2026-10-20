#!/bin/sh
# /jffs/scripts/vlan.sh - VLAN support for stock ASUSWRT (TUF-AX3000 V2)
#
# Creates an isolated network on its own bridge with:
#   - untagged "access" ports (a LAN port pulled out of br0)
#   - and/or tagged "trunk" ports (802.1Q sub-interface on a LAN port,
#     the port itself stays in br0 for the untagged main LAN)
#   - its own subnet, DHCP (via dnsmasq.conf.add), NAT to WAN,
#     and no routing to/from the main LAN.
#
# Usage: vlan.sh start | stop | check | status | ports
# "check" is run every minute from cron and re-applies anything the
# firmware has torn down (bridge rebuilds, firewall restarts).

# ---- configuration (override in /jffs/scripts/vlan.conf) -------------
VLAN_ID=20                  # 802.1Q ID used on trunk ports
BRIDGE=brvlan20             # bridge name (max 15 chars, avoid br1/br2)
ADDR=192.168.20.1           # router address on this VLAN
PREFIX=24
ACCESS_PORTS=""             # untagged ports, e.g. "eth4"
TRUNK_PORTS=""              # tagged ports, e.g. "eth1"
ISOLATE=1                   # 1 = block traffic between this VLAN and br0
ALLOW_ROUTER_ACCESS=0       # 1 = allow web UI/SSH from this VLAN
# -----------------------------------------------------------------------

SCRIPT="$(readlink -f "$0")"
CONF="${SCRIPT%.*}.conf"
[ -f "$CONF" ] && . "$CONF"

TAG="vlan.sh"
CHAIN_FWD="VLAN_FWD_$VLAN_ID"
CHAIN_IN="VLAN_IN_$VLAN_ID"

log() { logger -t "$TAG" "$*"; echo "$*"; }

net_of() { # network address of $ADDR/$PREFIX (busybox ipcalc)
    ipcalc -n "$ADDR/$PREFIX" 2>/dev/null | cut -d= -f2
}

wan_if() {
    _w="$(nvram get wan0_gw_ifname)"
    [ -z "$_w" ] && _w="$(nvram get wan0_ifname)"
    echo "$_w"
}

make_bridge() {
    if [ ! -d "/sys/class/net/$BRIDGE" ]; then
        brctl addbr "$BRIDGE" || return 1
        brctl stp "$BRIDGE" off
        log "created bridge $BRIDGE"
    fi
    ip addr show dev "$BRIDGE" | grep -q "inet $ADDR/" || \
        ip addr add "$ADDR/$PREFIX" brd + dev "$BRIDGE"
    ip link set "$BRIDGE" up
}

in_bridge() { [ "$(basename "$(readlink -f "/sys/class/net/$1/brport/bridge" 2>/dev/null)")" = "$2" ]; }

attach_access() {
    for p in $ACCESS_PORTS; do
        [ -d "/sys/class/net/$p" ] || { log "access port $p not found"; continue; }
        in_bridge "$p" "$BRIDGE" && continue
        _cur="$(basename "$(readlink -f "/sys/class/net/$p/brport/bridge" 2>/dev/null)")"
        [ -n "$_cur" ] && [ "$_cur" != "." ] && brctl delif "$_cur" "$p"
        brctl addif "$BRIDGE" "$p" && log "access port $p -> $BRIDGE"
    done
}

attach_trunk() {
    for p in $TRUNK_PORTS; do
        sub="$p.$VLAN_ID"
        if [ ! -d "/sys/class/net/$sub" ]; then
            if ! ip link add link "$p" name "$sub" type vlan id "$VLAN_ID" 2>/dev/null; then
                log "ERROR: kernel refused 802.1Q interface $sub (no 8021q support?)"
                log "Run 'vlanctl --help' and 'ls /lib/modules/*/kernel/net' and report back"
                continue
            fi
            log "created $sub"
        fi
        ip link set "$sub" up
        in_bridge "$sub" "$BRIDGE" || brctl addif "$BRIDGE" "$sub"
    done
}

firewall() {
    wan="$(wan_if)"
    net="$(net_of)/$PREFIX"

    iptables -N "$CHAIN_FWD" 2>/dev/null || iptables -F "$CHAIN_FWD"
    iptables -N "$CHAIN_IN" 2>/dev/null || iptables -F "$CHAIN_IN"

    # forwarding: VLAN -> WAN only, replies back
    iptables -A "$CHAIN_FWD" -i "$BRIDGE" -o "$wan" -j ACCEPT
    iptables -A "$CHAIN_FWD" -i "$wan" -o "$BRIDGE" -m state --state RELATED,ESTABLISHED -j ACCEPT
    if [ "$ISOLATE" = 1 ]; then
        iptables -A "$CHAIN_FWD" -i "$BRIDGE" -j DROP
        iptables -A "$CHAIN_FWD" -o "$BRIDGE" -j DROP
    else
        iptables -A "$CHAIN_FWD" -i "$BRIDGE" -o br0 -j ACCEPT
        iptables -A "$CHAIN_FWD" -i br0 -o "$BRIDGE" -j ACCEPT
    fi

    # input: DHCP + DNS always, management only if allowed
    iptables -A "$CHAIN_IN" -i "$BRIDGE" -p udp --dport 67 -j ACCEPT
    iptables -A "$CHAIN_IN" -i "$BRIDGE" -p udp --dport 53 -j ACCEPT
    iptables -A "$CHAIN_IN" -i "$BRIDGE" -p tcp --dport 53 -j ACCEPT
    iptables -A "$CHAIN_IN" -i "$BRIDGE" -p icmp -j ACCEPT
    if [ "$ALLOW_ROUTER_ACCESS" = 1 ]; then
        iptables -A "$CHAIN_IN" -i "$BRIDGE" -j ACCEPT
    else
        iptables -A "$CHAIN_IN" -i "$BRIDGE" -j DROP
    fi

    iptables -C FORWARD -j "$CHAIN_FWD" 2>/dev/null || iptables -I FORWARD 1 -j "$CHAIN_FWD"
    iptables -C INPUT -j "$CHAIN_IN" 2>/dev/null || iptables -I INPUT 1 -j "$CHAIN_IN"

    iptables -t nat -C POSTROUTING -s "$net" -o "$wan" -j MASQUERADE 2>/dev/null || \
        iptables -t nat -I POSTROUTING 1 -s "$net" -o "$wan" -j MASQUERADE
}

firewall_ok() {
    iptables -C FORWARD -j "$CHAIN_FWD" 2>/dev/null && \
    iptables -C INPUT -j "$CHAIN_IN" 2>/dev/null && \
    iptables -C "$CHAIN_FWD" -i "$BRIDGE" -o "$(wan_if)" -j ACCEPT 2>/dev/null
}

start() {
    make_bridge || { log "ERROR: could not create $BRIDGE"; exit 1; }
    attach_access
    attach_trunk
    firewall
    cru a vlan_check "* * * * * $SCRIPT check"
    log "VLAN $VLAN_ID up on $BRIDGE ($ADDR/$PREFIX)"
}

check() {
    _fix=0
    [ -d "/sys/class/net/$BRIDGE" ] || _fix=1
    for p in $ACCESS_PORTS; do in_bridge "$p" "$BRIDGE" || _fix=1; done
    for p in $TRUNK_PORTS; do in_bridge "$p.$VLAN_ID" "$BRIDGE" || _fix=1; done
    if [ "$_fix" = 1 ]; then
        log "bridge/ports reset by firmware, re-applying"
        make_bridge; attach_access; attach_trunk
        service restart_dnsmasq >/dev/null 2>&1
    fi
    firewall_ok || { log "firewall reset, re-applying"; firewall; }
}

stop() {
    cru d vlan_check
    wan="$(wan_if)"
    iptables -D FORWARD -j "$CHAIN_FWD" 2>/dev/null
    iptables -D INPUT -j "$CHAIN_IN" 2>/dev/null
    iptables -F "$CHAIN_FWD" 2>/dev/null; iptables -X "$CHAIN_FWD" 2>/dev/null
    iptables -F "$CHAIN_IN" 2>/dev/null; iptables -X "$CHAIN_IN" 2>/dev/null
    iptables -t nat -D POSTROUTING -s "$(net_of)/$PREFIX" -o "$wan" -j MASQUERADE 2>/dev/null
    for p in $TRUNK_PORTS; do ip link del "$p.$VLAN_ID" 2>/dev/null; done
    for p in $ACCESS_PORTS; do
        brctl delif "$BRIDGE" "$p" 2>/dev/null
        brctl addif br0 "$p" 2>/dev/null
    done
    ip link set "$BRIDGE" down 2>/dev/null
    brctl delbr "$BRIDGE" 2>/dev/null
    log "VLAN $VLAN_ID removed, access ports returned to br0"
}

ports() {
    echo "LAN interfaces (nvram lan_ifnames): $(nvram get lan_ifnames)"
    echo "WAN interface: $(wan_if)"
    echo
    for i in /sys/class/net/eth*; do
        n="$(basename "$i")"
        printf '%-8s link=%s speed=%s bridge=%s\n' "$n" \
            "$(cat "$i/carrier" 2>/dev/null)" "$(cat "$i/speed" 2>/dev/null)" \
            "$(basename "$(readlink -f "$i/brport/bridge" 2>/dev/null)")"
    done
    echo
    echo "Plug/unplug a cable and re-run to see which ethX is which physical port."
}

case "$1" in
    start)  start ;;
    stop)   stop ;;
    check)  check ;;
    status) brctl show; echo; iptables -vnL "$CHAIN_FWD"; iptables -vnL "$CHAIN_IN" ;;
    ports)  ports ;;
    *) echo "Usage: $0 start|stop|check|status|ports"; exit 1 ;;
esac
