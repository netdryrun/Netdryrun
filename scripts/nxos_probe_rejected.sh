#!/usr/bin/env bash
# Capture how a Nexus 9000v (vrnetlab) logs a startup-config line NX-OS rejects: boot examples/nxos-frr with two
# bad lines added to n1's config, wait until vrnetlab says the config is applied, save the container log as a
# fixture, destroy. The caller holds the vendor-VM lab lock (/home/ndr/vendor-vm-lab.lock). Only the lab named
# ndr-nxos-probe is ever destroyed.
#
#   scripts/nxos_probe_rejected.sh [OUT]      # OUT default: tests/fixtures/nxos_boot_log_rejected.txt
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:-tests/fixtures/nxos_boot_log_rejected.txt}
LAB=ndr-nxos-probe
WORK=$(mktemp -d)
cp -r examples/nxos-frr "$WORK/lab"
sed -i "s/^name: .*/name: $LAB/" "$WORK/lab/topology.clab.yml"
grep -q "^name: $LAB\$" "$WORK/lab/topology.clab.yml"
# two lines NX-OS refuses: a command that doesn't exist, and a prefix that isn't one
printf '%s\n' "this-is-not-a-command" "ip prefix-list PROBE seq 5 permit 300.0.0.0/8" >> "$WORK/lab/configs/n1.cfg"
cleanup() { containerlab destroy -t "$WORK/lab/topology.clab.yml" --cleanup >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
containerlab deploy -t "$WORK/lab/topology.clab.yml" >/dev/null
C=clab-$LAB-n1
for _ in $(seq 1 120); do                         # at most 20 minutes
  [ "$(docker exec "$C" cat /health 2>/dev/null)" = "0 running" ] && break
  sleep 10
done
[ "$(docker exec "$C" cat /health 2>/dev/null)" = "0 running" ] || { echo "n1 never became ready" >&2; exit 1; }
docker logs "$C" > "$OUT" 2>&1
echo "saved $OUT ($(wc -c < "$OUT") bytes)"
