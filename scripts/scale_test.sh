#!/usr/bin/env bash
# Scale test: a generated FRR leaf-spine fabric (scripts/scale_topology.py) of LEAVES + 2 nodes, run twice:
#   pass  - the clean fabric: every guard check must pass         (netdryrun exit 0)
#   leak  - one leaf also originates a default route: it must FAIL (netdryrun exit 1)
# and the time of each phase (deploy, convergence, checks, destroy) and the memory the lab held are captured.
#
#   scripts/scale_test.sh LEAVES [options]        48 leaves = 50 nodes, 98 leaves = 100 nodes
#     --ndr CMD        netdryrun command (default: netdryrun on PATH)
#     --out DIR        results folder (default: scale-results/<timestamp>)
#     --only pass|leak run just one variant
#     --leak-leaf K    the leaking leaf (default: the middle one)
#     --no-lock        the caller already has the lab to itself (the release gate); otherwise a run of
#                      more than 8 leaves takes /home/ndr/vendor-vm-lab.lock (override: NDR_LAB_LOCK)
#
# Writes OUT/scale-<LEAVES>.json (one record per variant) and prints a summary. Exit 0 only when pass exits 0,
# leak exits 1 and no lab is left behind; 1 on a wrong verdict; 2 on a setup problem (no Docker, lock held).
# Heavy: see docs/scale.md for the memory per node. Never run it while another heavy job holds the lock.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEAVES="${1:-}"; shift || true
NDR=netdryrun; OUT=""; ONLY=""; LEAK_LEAF=""; LOCK=1
while [ $# -gt 0 ]; do
  case "$1" in
    --ndr) NDR="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --only) ONLY="$2"; shift 2;;
    --leak-leaf) LEAK_LEAF="$2"; shift 2;;
    --no-lock) LOCK=0; shift;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done
case "$LEAVES" in ''|*[!0-9]*) echo "usage: scale_test.sh LEAVES [--ndr CMD] [--out DIR] [--only pass|leak] [--leak-leaf K] [--no-lock]" >&2; exit 2;; esac
[ "$LEAVES" -ge 2 ] || { echo "LEAVES must be at least 2" >&2; exit 2; }
[ -n "$LEAK_LEAF" ] || LEAK_LEAF=$(( (LEAVES + 1) / 2 ))
[ -n "$OUT" ] || OUT="scale-results/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
NODES=$(( LEAVES + 2 ))
PY="$(command -v python3 || command -v python)"
PREFIX="clab-ndr-scale$LEAVES-"

command -v docker >/dev/null && command -v containerlab >/dev/null || { echo "docker and containerlab are required" >&2; exit 2; }

LOCKDIR="${NDR_LAB_LOCK:-/home/ndr/vendor-vm-lab.lock}"; HAVE_LOCK=0
if [ "$LOCK" = 1 ] && [ "$LEAVES" -gt 8 ]; then
  if mkdir "$LOCKDIR" 2>/dev/null; then
    HAVE_LOCK=1; echo "scale_test $NODES nodes, started $(date -u '+%F %T') UTC" > "$LOCKDIR/owner"
  else
    echo "lab lock held: $(cat "$LOCKDIR/owner" 2>/dev/null)" >&2; exit 2
  fi
fi
SAMPLER=""
cleanup() {
  [ -n "$SAMPLER" ] && kill "$SAMPLER" 2>/dev/null
  [ "$HAVE_LOCK" = 1 ] && rm -rf "$LOCKDIR"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT TERM

INOTIFY=$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo 0)
[ "$INOTIFY" -ge 1024 ] || echo "note: fs.inotify.max_user_instances=$INOTIFY; containerlab advises >= 1024 for large labs" >&2

# every 5 s: "<epoch> <MiB used by the lab's containers> <MiB available on the host>"
sample_mem() {  # $1 = file
  while :; do
    used=$(docker stats --no-stream --format '{{.MemUsage}}' $(docker ps -q --filter "name=$PREFIX") 2>/dev/null |
           awk '{v=$1; if (v ~ /GiB/) {sub(/GiB/,"",v); s+=v*1024} else if (v ~ /MiB/) {sub(/MiB/,"",v); s+=v} else if (v ~ /KiB/) {sub(/KiB/,"",v); s+=v/1024}} END{printf "%d", s}')
    avail=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo)
    echo "$(date +%s) ${used:-0} ${avail:-0}" >> "$1"
    sleep 5
  done
}

summarize() {  # log mem variant exit want left t0 t1
  "$PY" "$HERE/scale_summary.py" record --log "$1" --mem "$2" --variant "$3" --leaves "$LEAVES" --nodes "$NODES" \
        --exit "$4" --want "$5" --left "$6" --t0 "$7" --t1 "$8" --out "$OUT/scale-$LEAVES.json"
}

run_variant() {  # $1 = pass|leak, $2 = expected exit
  local variant="$1" want="$2" dir="$OUT/lab-$1-$LEAVES" log="$OUT/$1-$LEAVES.log" mem="$OUT/$1-$LEAVES.mem"
  local leak_args=()
  [ "$variant" = leak ] && leak_args=(--leak "$LEAK_LEAF")
  "$PY" "$HERE/scale_topology.py" "$dir" --leaves "$LEAVES" "${leak_args[@]}" || return 2
  : > "$mem"
  sample_mem "$mem" & SAMPLER=$!
  local t0 t1 code left
  t0=$(date +%s.%N)
  CI=1 "$NDR" run "$dir" --json "$OUT/$variant-$LEAVES.json" --no-step-summary 2>&1 |
    while IFS= read -r line; do printf '%s\t%s\n' "$(date +%s.%N)" "$line"; done > "$log"
  code=${PIPESTATUS[0]}; t1=$(date +%s.%N)
  kill "$SAMPLER" 2>/dev/null; wait "$SAMPLER" 2>/dev/null; SAMPLER=""
  left=$(docker ps -a --filter "name=$PREFIX" --format '{{.Names}}' | wc -l)
  if [ "$left" -gt 0 ]; then  # only this lab: the prefix carries its name and size
    containerlab destroy -t "$dir/topology.clab.yml" --cleanup >/dev/null 2>&1
    left=$(docker ps -a --filter "name=$PREFIX" --format '{{.Names}}' | wc -l)
  fi
  summarize "$log" "$mem" "$variant" "$code" "$want" "$left" "$t0" "$t1"
}

echo "scale test: $LEAVES leaves + 2 spines = $NODES FRR nodes, leak at leaf$LEAK_LEAF, results in $OUT"
if [ "$ONLY" != leak ]; then run_variant pass 0 || exit 2; fi
if [ "$ONLY" != pass ]; then run_variant leak 1 || exit 2; fi
"$PY" "$HERE/scale_summary.py" show "$OUT/scale-$LEAVES.json"
