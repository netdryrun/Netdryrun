#!/bin/bash
# FP-043-EOSNONBGP captures on lab ndr-fp043 (cEOS 4.36.3M ceos1, FRR 10.4.1 frr1). Every file is the Cli stdout,
# byte for byte, of `docker exec clab-ndr-fp043-ceos1 Cli -p 15 -c "<command>"`.
set -u
C=~/fp043/cli.sh
OUT=~/fp043/cap
REPO="/mnt/c/NetCL Business/wt/oracle-eos-nonbgp"
PY=~/.venvs/netdryrun/bin/python
mkdir -p $OUT
F() { docker exec clab-ndr-fp043-frr1 vtysh -c "configure terminal" "$@"; }
E() { $C "$(printf 'configure\n%s\nend' "$1")"; }
cap() {   # cap <phase> <name> <command>
  docker exec clab-ndr-fp043-ceos1 Cli -p 15 -c "$3" > "$OUT/ceos4363m_fp043_$1_$2" 2> "$OUT/stderr_$1_$2"
  echo "$1 $2 rc=$? :: $3 :: $(date -u +%FT%TZ)" >> $OUT/LOG
}
waitfor() {  # waitfor <command> <grep -E pattern>
  for i in $(seq 1 40); do $C "$1" | grep -Eq "$2" && return 0; sleep 3; done
  echo "TIMEOUT waiting for $2 in $1"; return 1
}
waitnot() {
  for i in $(seq 1 40); do $C "$1" | grep -Eq "$2" || return 0; sleep 3; done
  echo "TIMEOUT waiting for no $2 in $1"; return 1
}
check() {   # check <phase>
  (cd "$REPO" && PYTHONPATH=src $PY -m netdryrun check ~/fp043/netdryrun.yml --settle 2 --hold 6 \
     --json "$OUT/ceos4363m_fp043_$1_report.json" > "$OUT/ceos4363m_fp043_$1_check.txt" 2>&1; echo "$1 check exit=$?" >> $OUT/LOG)
}
std() {   # the reads the driver makes today plus the candidate reads, for 0.0.0.0/0
  cap $1 ip_route.json "show ip route vrf default 0.0.0.0/0 | json"
  cap $1 ip_bgp.json "show ip bgp 0.0.0.0/0 vrf default | json"
  cap $1 rib_route.json "show rib route ip vrf default 0.0.0.0/0 | json"
  cap $1 rib_route.txt "show rib route ip vrf default 0.0.0.0/0"
}

: > $OUT/LOG
$C "show version" > $OUT/ceos4363m_fp043_show_version.txt

# phase rt0056: eBGP default from frr1 selected (200), floating static 250 via 10.0.201.2 configured, valid, not selected
waitfor "show rib route ip vrf default 0.0.0.0/0" "^ S +0.0.0.0/0 \[250"
std rt0056
cap rt0056 ip_route_detail.txt "show ip route vrf default 0.0.0.0/0 detail"
cap rt0056 ip_route_static.txt "show ip route vrf default static"
cap rt0056 ip_route_9.json "show ip route vrf default 9.9.9.0/24 | json"
cap rt0056 ip_bgp_9.json "show ip bgp 9.9.9.0/24 vrf default | json"
cap rt0056 rib_route_9.json "show rib route ip vrf default 9.9.9.0/24 | json"
cap rt0056 running_config.txt "show running-config"
check rt0056

# phase rt0056sel: eBGP session shut, the same static is selected (it is valid)
E $'router bgp 65030\nneighbor 10.0.200.2 shutdown'
waitfor "show ip route vrf default 0.0.0.0/0" "^ S +0.0.0.0/0 \[250"
cap rt0056sel ip_route.json "show ip route vrf default 0.0.0.0/0 | json"
cap rt0056sel rib_route.json "show rib route ip vrf default 0.0.0.0/0 | json"
E $'router bgp 65030\nno neighbor 10.0.200.2 shutdown'
waitfor "show ip route vrf default 0.0.0.0/0" "B E +0.0.0.0/0"

# phase healthyA: eBGP default only, no static
E 'no ip route 0.0.0.0/0 10.0.201.2 250'
waitnot "show rib route ip vrf default 0.0.0.0/0" "^ S "
std healthyA
check healthyA

# phase rt0063: static Null0 default (1) selected, OSPF default from frr1 (110) in the RIB, no BGP default
F -c "router bgp 65020" -c "address-family ipv4 unicast" -c "no neighbor 10.0.200.1 default-originate"
F -c "router ospf" -c "default-information originate always"
E 'ip route 0.0.0.0/0 Null0'
waitnot "show ip bgp 0.0.0.0/0 vrf default" "10.0.200.2"
waitfor "show rib route ip vrf default 0.0.0.0/0" "O.* +0.0.0.0/0"
waitfor "show ip route vrf default 0.0.0.0/0" "S +0.0.0.0/0"
std rt0063
cap rt0063 ip_route_detail.txt "show ip route vrf default 0.0.0.0/0 detail"
cap rt0063 ip_route_ospf.txt "show ip route vrf default ospf"
cap rt0063 ospf_database.txt "show ip ospf database"
cap rt0063 running_config.txt "show running-config"
check rt0063

# phase ospfsel: Null0 static removed, the OSPF default is selected
E 'no ip route 0.0.0.0/0 Null0'
waitfor "show ip route vrf default 0.0.0.0/0" "O.* +0.0.0.0/0"
cap ospfsel ip_route.json "show ip route vrf default 0.0.0.0/0 | json"
cap ospfsel rib_route.json "show rib route ip vrf default 0.0.0.0/0 | json"

# phase healthyB: static Null0 only, frr1 sends no default at all
E 'ip route 0.0.0.0/0 Null0'
F -c "router ospf" -c "no default-information originate always"
waitnot "show rib route ip vrf default 0.0.0.0/0" "O.* +0.0.0.0/0"
std healthyB
check healthyB
cat $OUT/LOG
