#!/usr/bin/env bash
# Re-capture a driver's fixtures from a live lab: deploy the pinned example, run exactly the commands the
# driver runs, write the outputs in the format of tests/fixtures/, destroy the lab.
#
#   scripts/capture_fixtures.sh <frr|srlinux|eos|sonic> [--out DIR] [--keep]
#
# The weekly drift check (research/quality-schedule.md, S3) runs this for every driver, then
# `python3 scripts/fixture_shape.py` (what changed in shape) and the driver tests on the fresh captures.
#
# Two kinds of file land in DIR (default tests/fixtures):
#   DIR/<name>        the capture reproduces the committed fixture's scenario, so it replaces it and the
#                     driver tests run on it (frr_bgp_neighbors.txt, srl_route.txt, eos_ping.txt, ...)
#   DIR/shape/<name>  the committed fixture comes from a richer lab (several paths, attributes, a
#                     no-export route) that a pinned example does not reproduce; the capture is kept only to
#                     compare shapes. Fixtures with no capture here are listed in NOT_CAPTURED below.
#
# Labs are named ndr-cap-<driver> (containers clab-ndr-cap-<driver>-*) and only that name is ever destroyed.
# cEOS and SONiC are heavy: they take the vendor-VM lab lock (lesson 54) and retry every 5 minutes.
#   NDR_LOCK_DIR        lock directory (default /home/ndr/vendor-vm-lab.lock)
#   NDR_LOCK_WAIT_MAX   seconds to keep retrying for the lock (default 7200)
#   NDR_LOCK_HELD=1     the caller already holds the lock
#
# Adding a driver (Juniper, NX-OS): add its row to the `case` in "Driver table", write capture_<driver>()
# (use cap / shape / wait_for), and list its uncaptured fixtures. Nothing else in this file changes.
set -euo pipefail
cd "$(dirname "$0")/.."

DRIVERS_HERE="frr srlinux eos sonic"
DRIVERS_ON_BRANCHES="junos (ndr/junos) nxos (ndr/nxos)"

usage() {
  echo "usage: $0 <${DRIVERS_HERE// /|}> [--out DIR] [--keep]" >&2
  echo "drivers on branches, not here yet: $DRIVERS_ON_BRANCHES" >&2
  exit 2
}

DRIVER=${1:-}; [ -n "$DRIVER" ] || usage
shift
OUT=tests/fixtures; KEEP=0
while [ $# -gt 0 ]; do
  case $1 in
    --out) OUT=${2:?--out needs a folder}; shift 2 ;;
    --keep) KEEP=1; shift ;;
    *) usage ;;
  esac
done

# ---- Driver table: example topology, lab name, whether the lab is heavy, fixtures with no capture ----------
LAB=ndr-cap-$DRIVER
HEAVY=0
case $DRIVER in
  frr)     EXAMPLE=examples/frr-bgp;
           NOT_CAPTURED="frr_bgp_paths_local frr_bgp_paths_noexport frr_bgp_paths_v6 (need a locally originated, a no-export and an IPv6 prefix)" ;;
  srlinux) EXAMPLE=examples/srl-frr;
           NOT_CAPTURED="srl_attr_set_backup srl_attr_set_noexport srl_bgp_rib_paths_noexport (need a second path and a no-export prefix)" ;;
  eos)     EXAMPLE=examples/arista-frr; HEAVY=1;
           NOT_CAPTURED="eos_bgp_paths_empty eos_bgp_paths_local eos_bgp_paths_noexport (need a missing, a local and a no-export prefix)" ;;
  sonic)   EXAMPLE=examples/sonic-frr; HEAVY=1; NOT_CAPTURED="" ;;
  junos|nxos) echo "$DRIVER: its driver and captures are on branch ndr/$DRIVER; add it to the driver table when it merges" >&2; exit 2 ;;
  *) usage ;;
esac
P=clab-$LAB            # container name prefix
# A throwaway copy of the example under the lab's own name: containerlab 0.81 destroys by topology file, not by
# --name, and the copy keeps the pinned example untouched (its `name:` line is the only edit).
WORK=$(mktemp -d)
cp -r "$EXAMPLE" "$WORK/lab"
sed -i "s/^name: .*/name: $LAB/" "$WORK/lab/topology.clab.yml"
TOPO=$WORK/lab/topology.clab.yml
grep -q "^name: $LAB\$" "$TOPO" || { echo "could not rename the lab in $TOPO" >&2; exit 1; }

export CLAB_LABDIR_BASE="${CLAB_LABDIR_BASE:-$HOME/.cache/netdryrun/labs}"
CLAB=containerlab
$CLAB version >/dev/null 2>&1 || CLAB="sudo containerlab"

# ---- Helpers -----------------------------------------------------------------------------------------------
mkdir -p "$OUT" "$OUT/shape"
log() { echo "[capture $DRIVER] $*" >&2; }

# cap NAME CMD...      stdout of CMD -> $OUT/NAME.txt (a failing command or an empty answer fails the script)
cap()   { _put "$OUT/$1.txt" "${@:2}"; }
# shape NAME CMD...    same, into $OUT/shape/ (compared by shape only)
shape() { _put "$OUT/shape/$1.txt" "${@:2}"; }
_put() {
  local file=$1; shift
  "$@" > "$file.tmp" || { rm -f "$file.tmp"; log "FAILED: $*"; return 1; }
  [ -s "$file.tmp" ] || { rm -f "$file.tmp"; log "EMPTY answer: $*"; return 1; }
  mv "$file.tmp" "$file"
  log "captured $(basename "$file") ($(wc -c < "$file") bytes)"
}

# wait_for "what" SECONDS CMD...     CMD succeeds quietly within SECONDS, or the script fails (every wait is capped)
wait_for() {
  local what=$1 limit=$2; shift 2
  local end=$(( $(date +%s) + limit ))
  until "$@" >/dev/null 2>&1; do
    [ "$(date +%s)" -lt "$end" ] || { log "timed out after ${limit}s waiting for $what"; return 1; }
    sleep 5
  done
}

LOCK=${NDR_LOCK_DIR:-/home/ndr/vendor-vm-lab.lock}; LOCKED=0
acquire_lock() {
  [ "$HEAVY" = 1 ] && [ "${NDR_LOCK_HELD:-0}" != 1 ] || return 0
  local end=$(( $(date +%s) + ${NDR_LOCK_WAIT_MAX:-7200} ))
  until mkdir "$LOCK" 2>/dev/null; do
    log "lab lock held ($(cat "$LOCK"/owner 2>/dev/null || echo unknown)); retrying in 5 minutes"
    [ "$(date +%s)" -lt "$end" ] || { log "gave up waiting for the lab lock"; exit 3; }
    sleep 300
  done
  LOCKED=1
  echo "capture_fixtures.sh $DRIVER; started $(date -u '+%Y-%m-%d %H:%M:%S') UTC" > "$LOCK/owner"
  log "took $LOCK"
}

DEPLOYED=0
cleanup() {
  local rc=$?
  if [ "$DEPLOYED" = 1 ] && [ "$KEEP" = 0 ]; then
    log "destroying $LAB"
    $CLAB destroy -t "$TOPO" --cleanup >/dev/null 2>&1 || log "destroy failed: remove $P-* by hand"
  fi
  [ "$LOCKED" = 1 ] && rm -rf "$LOCK"
  rm -rf "$WORK"
  exit $rc
}
trap cleanup EXIT

deploy() {
  acquire_lock
  # only ever our own name: a leftover from an interrupted capture is removed, anything else is left alone
  if docker ps -a --format '{{.Names}}' | grep -q "^$P-"; then
    log "removing a leftover $LAB"
    $CLAB destroy -t "$TOPO" --cleanup >/dev/null 2>&1
  fi
  DEPLOYED=1
  log "deploying $EXAMPLE as $LAB"
  $CLAB deploy -t "$TOPO" >/dev/null 2>&1 || { log "deploy failed"; $CLAB deploy -t "$TOPO" 2>&1 | tail -15 >&2; return 1; }
}

frr1() { docker exec "$P-frr1" vtysh "$@"; }

# ---- Drivers: the commands are the ones in src/netdryrun/drivers/<driver>.py -----------------------------------
capture_frr() {                     # frr.py: bgp_neighbors, routes, bgp_paths, ping (node r1 of examples/frr-bgp)
  local r1=$P-r1
  wait_for "r1 to learn 192.168.3.0/24 over BGP" 180 bash -c "docker exec $r1 vtysh -c 'show ip route 192.168.3.0/24 json' | grep -q '\"protocol\":\"bgp\"'"
  sleep 5
  cap   frr_bgp_neighbors     docker exec "$r1" vtysh -c "show bgp neighbors json"
  cap   frr_route             docker exec "$r1" vtysh -c "show ip route 192.168.3.0/24 json"
  cap   frr_bgp_table_header  docker exec "$r1" vtysh -c "show bgp ipv4 unicast 255.255.255.255/32 longer-prefixes json"
  cap   frr_ping              docker exec "$r1" ping -c 3 -W 1 -I 192.168.1.1 192.168.3.1
  shape frr_bgp_paths         docker exec "$r1" vtysh -c "show bgp ipv4 unicast 192.168.3.0/24 json"
  shape frr_all_routes        docker exec "$r1" vtysh -c "show ip route json"
}

# SONiC routes with FRR inside the container, so it is read exactly like FRR (drivers/sonic.py).
capture_sonic() {                   # sonic1 of examples/sonic-frr, configured after boot like its netdryrun.yml setup
  local s=$P-sonic1
  timeout 600 bash scripts/sonic_config.sh "$s" >&2 || { log "SONiC did not come up configured"; return 1; }
  wait_for "sonic1 to learn 192.168.20.0/24" 120 bash -c "docker exec $s vtysh -c 'show ip route 192.168.20.0/24 json' | grep -q '\"protocol\":\"bgp\"'"
  cap   sonic_bgp_neighbors   docker exec "$s" vtysh -c "show bgp neighbors json"
  cap   sonic_route           docker exec "$s" vtysh -c "show ip route 192.168.20.0/24 json"
  shape sonic_bgp_paths       docker exec "$s" vtysh -c "show bgp ipv4 unicast 192.168.20.0/24 json"
  shape sonic_ping            docker exec "$s" ping -c 3 -W 1 -I 192.168.40.1 192.168.20.1
  shape sonic_bgp_table_header docker exec "$s" vtysh -c "show bgp ipv4 unicast 255.255.255.255/32 longer-prefixes json"
}

capture_srlinux() {                 # srlinux.py: bgp_neighbors, routes, bgp_paths, ping, and the hidden-leak case
  local s=$P-srl1 ni="info from state /network-instance default"
  local -a cli=(sr_cli --output-format json)
  wait_for "srl1 BGP established" 300 bash -c "docker exec $s sr_cli 'show network-instance default protocols bgp neighbor' | grep -q established"
  wait_for "srl1 to learn 192.168.20.0/24" 120 bash -c "docker exec $s sr_cli --output-format json '$ni route-table ipv4-unicast route 192.168.20.0/24 id * route-type * route-owner * origin-network-instance *' | grep -q bgp"
  sleep 5
  local rib="$ni bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route"
  cap   srl_bgp_neighbors     docker exec "$s" "${cli[@]}" "$ni protocols bgp neighbor *"
  cap   srl_route             docker exec "$s" "${cli[@]}" "$ni route-table ipv4-unicast route 192.168.20.0/24 id * route-type * route-owner * origin-network-instance *"
  cap   srl_neighbor_local_pref docker exec "$s" "${cli[@]}" "$ni protocols bgp neighbor 10.0.100.2 local-preference"
  cap   srl_rib_empty         docker exec "$s" "${cli[@]}" "$rib 10.99.0.0/16 neighbor * origin-protocol * path-id *"
  cap   srl_ping              docker exec "$s" ip netns exec srbase-default ping -c 3 -W 1 -I 192.168.10.1 192.168.20.1
  shape srl_bgp_rib_paths     docker exec "$s" "${cli[@]}" "$rib 192.168.20.0/24 neighbor * origin-protocol * path-id *"
  local attr
  attr=$(docker exec "$s" "${cli[@]}" "$rib 192.168.20.0/24 neighbor * origin-protocol * path-id *" | python3 -c \
    'import json,sys; print(next(r["attr-id"] for r in json.load(sys.stdin)["route"] if r.get("best-route")))')
  case $attr in ''|*[!0-9]*) log "no numeric attr-id for the best path: $attr"; return 1 ;; esac
  shape srl_attr_set_best     docker exec "$s" "${cli[@]}" "$ni bgp-rib attr-sets attr-set $attr"
  shape srl_all_routes        docker exec "$s" "${cli[@]}" "$ni route-table ipv4-unicast route * id * route-type * route-owner * origin-network-instance *"
  shape srl_netns_list        docker exec "$s" ip netns list
  # the hidden leak (examples/srl-hidden-leak): a BGP default received but outranked by a local static blackhole
  frr1 -c "conf t" -c "router bgp 65020" -c "address-family ipv4 unicast" -c "neighbor 10.0.100.1 default-originate" >/dev/null
  printf '%s\n' "enter candidate" \
    "set / network-instance default next-hop-groups group bh blackhole" \
    "set / network-instance default static-routes route 0.0.0.0/0 next-hop-group bh" \
    "set / network-instance default static-routes route 0.0.0.0/0 admin-state enable" \
    "commit now" | docker exec -i "$s" sr_cli >/dev/null
  sleep 10
  cap srl_leak_route docker exec "$s" "${cli[@]}" "$ni route-table ipv4-unicast route 0.0.0.0/0 id * route-type * route-owner * origin-network-instance *"
  cap srl_leak_rib   docker exec "$s" "${cli[@]}" "$rib 0.0.0.0/0 neighbor * origin-protocol * path-id *"
}

capture_eos() {                     # eos.py: bgp_neighbors, routes, bgp_paths, ping, and the received-not-selected leak
  local c=$P-ceos1 f=$P-frr1
  cli() { docker exec "$c" Cli -p 15 -c "$1"; }
  wait_for "cEOS BGP established" 900 bash -c "docker exec $c Cli -p 15 -c 'show ip bgp summary vrf default | json' | grep -q Established"
  wait_for "ceos1 to learn 192.168.20.0/24" 120 bash -c "docker exec $c Cli -p 15 -c 'show ip route vrf default 192.168.20.0/24 | json' | grep -qi bgp"
  sleep 5
  cap   eos_bgp_summary       cli "show ip bgp summary vrf default | json"
  cap   eos_route             cli "show ip route vrf default 192.168.20.0/24 | json"
  cap   eos_bgp_route         cli "show ip bgp 192.168.20.0/24 vrf default | json"
  cap   eos_ping              cli "ping vrf default 192.168.20.1 repeat 3 source 192.168.30.1"
  shape eos_bgp_paths         cli "show ip bgp 192.168.20.0/24 vrf default | json"
  shape eos_bgp_summary_v6    cli "show ipv6 bgp summary vrf default | json"
  shape eos_all_routes        cli "show ip route vrf default | json"
  # leak: BGP default received, a static default installed instead
  docker exec "$f" vtysh -c "conf t" -c "router bgp 65020" -c "address-family ipv4 unicast" -c "neighbor 10.0.200.1 default-originate" >/dev/null
  cli $'enable\nconfigure\nip route 0.0.0.0/0 Null0\nend' >/dev/null
  sleep 8
  cap eos_leak_route cli "show ip route vrf default 0.0.0.0/0 | json"
  cap eos_leak_bgp   cli "show ip bgp 0.0.0.0/0 vrf default | json"
}

# ---- Run ---------------------------------------------------------------------------------------------------------
deploy
"capture_$DRIVER"
[ -z "$NOT_CAPTURED" ] || log "not captured (scenario-specific): $NOT_CAPTURED"
log "done. Compare shapes: python3 scripts/fixture_shape.py $OUT"
