# shellcheck shell=bash
# shellcheck disable=SC1090,SC2024,SC2034,SC2164  # a lab capture script kept as it ran (the record of how the fixtures were made)
# helpers for lab ndr-eosagg
C() { docker exec clab-ndr-eosagg-ceos1 Cli -p 15 -c "$1"; }
E() { C "$(printf 'configure\n%s\nend' "$1")"; }
V() { docker exec clab-ndr-eosagg-frr2 vtysh -c "$1"; }
F() { docker exec clab-ndr-eosagg-frr2 vtysh -c "configure terminal" "$@"; }
U() { docker exec clab-ndr-eosagg-up1 vtysh -c "configure terminal" "$@"; }
waitc() { for i in $(seq 1 60); do C "$1" 2>/dev/null | grep -Eq "$2" && return 0; sleep 3; done; echo "TIMEOUT ceos1 $2 in $1"; return 1; }
waitcn() { for i in $(seq 1 60); do C "$1" 2>/dev/null | grep -Eq "$2" || return 0; sleep 3; done; echo "TIMEOUT ceos1 no $2 in $1"; return 1; }
waitf() { for i in $(seq 1 60); do V "$1" 2>/dev/null | grep -Eq "$2" && return 0; sleep 3; done; echo "TIMEOUT frr2 $2 in $1"; return 1; }
waitfn() { for i in $(seq 1 60); do V "$1" 2>/dev/null | grep -Eq "$2" || return 0; sleep 3; done; echo "TIMEOUT frr2 no $2 in $1"; return 1; }
