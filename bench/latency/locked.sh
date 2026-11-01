#!/usr/bin/env bash
# Run a command while holding the lab machine's shared lab lock (one lab job at a time on the host).
#   bench/latency/locked.sh <owner text> <command>...
# The lock is a directory (NDR_LAB_LOCK, default ~/vendor-vm-lab.lock) with an owner file; it is removed on exit.
set -u
LOCK="${NDR_LAB_LOCK:-$HOME/vendor-vm-lab.lock}"
owner="$1"; shift
until mkdir "$LOCK" 2>/dev/null; do
  echo "lab lock busy ($(cat "$LOCK/owner" 2>/dev/null)); retrying in 60 s" >&2
  sleep 60
done
echo "$owner $(date -Is) pid $$" > "$LOCK/owner"
trap 'rm -rf "$LOCK"' EXIT
"$@"
