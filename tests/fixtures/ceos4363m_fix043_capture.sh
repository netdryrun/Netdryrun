#!/bin/bash
# fix-eos-nonbgp live proof on lab ndr-fix043 (cEOS 4.36.3M + FRR 10.4.1): the oracle's phases, checked with the fix,
# then extra captures (absent prefix, connected, VRF, IPv6, unknown VRF) for the parser's unit tests.
set -u
D=~/fix043
OUT=$D/out
REPO=~/fix-eos-nonbgp-wip
PY=~/.venvs/netdryrun/bin/python
mkdir -p $OUT
C() { docker exec clab-ndr-fix043-ceos1 Cli -p 15 -c "$1"; }
F() { docker exec clab-ndr-fix043-frr1 vtysh -c "configure terminal" "$@"; }
E() { C "$(printf 'configure\n%s\nend' "$1")"; }
cap() { C "$2" > "$OUT/ceos4363m_fix043_$1" 2> "$OUT/stderr_$1"; echo "$1 rc=$? :: $2 :: $(date -u +%FT%TZ)" >> $OUT/LOG; }
waitfor() { for i in $(seq 1 60); do C "$1" | grep -Eq "$2" && return 0; sleep 3; done; echo "TIMEOUT $2 in $1" | tee -a $OUT/LOG; return 1; }
waitnot() { for i in $(seq 1 60); do C "$1" | grep -Eq "$2" || return 0; sleep 3; done; echo "TIMEOUT no $2 in $1" | tee -a $OUT/LOG; return 1; }
check() {   # check <phase> <yml>
  (cd "$REPO" && PYTHONPATH=src $PY -m netdryrun check $D/$2 --settle 2 --hold 6 --json "$OUT/report_$1.json" > "$OUT/check_$1.txt" 2>&1
   echo "$1 check exit=$?" >> $OUT/LOG)
  $PY - "$OUT/report_$1.json" "$1" <<'PYEOF' | tee -a $OUT/VERDICTS
import json, sys
rep = json.load(open(sys.argv[1]))
for c in rep["checks"]:
    print(f"{sys.argv[2]:10} {c['name']:28} passed={c['passed']}  {str(c.get('detail',''))[:110]}")
PYEOF
}
: > $OUT/LOG; : > $OUT/VERDICTS
C "show version" > $OUT/show_version.txt
# as the oracle's lab: frr1 eth2 MTU 1500 and mtu-ignore, so OSPF reaches FULL with cEOS's Ethernet2 (1500)
docker exec clab-ndr-fix043-frr1 ip link set eth2 mtu 1500
F -c "interface eth2" -c "ip ospf mtu-ignore"
waitfor "show ip ospf neighbor" "FULL"

# rt0056: eBGP default selected, floating static 250 configured
E 'ip route 0.0.0.0/0 10.0.201.2 250'
waitfor "show ip route vrf default 0.0.0.0/0" "B E +0.0.0.0/0"
waitfor "show rib route ip vrf default 0.0.0.0/0" "^ S +0.0.0.0/0 \[250"
cap rt0056_rib_route.txt "show rib route ip vrf default 0.0.0.0/0"
check rt0056 proof.yml

# healthyA: no static
E 'no ip route 0.0.0.0/0 10.0.201.2 250'
waitnot "show rib route ip vrf default 0.0.0.0/0" "^ S "
check healthyA proof.yml

# rt0063: static Null0 selected, OSPF default not selected, no BGP default
F -c "router bgp 65020" -c "address-family ipv4 unicast" -c "no neighbor 10.0.200.1 default-originate"
F -c "router ospf" -c "default-information originate always"
E 'ip route 0.0.0.0/0 Null0'
waitnot "show ip bgp 0.0.0.0/0 vrf default" "10.0.200.2"
waitfor "show rib route ip vrf default 0.0.0.0/0" "O.* +0.0.0.0/0"
waitfor "show ip route vrf default 0.0.0.0/0" "S +0.0.0.0/0"
cap rt0063_rib_route.txt "show rib route ip vrf default 0.0.0.0/0"
check rt0063 proof.yml

# healthyB: static Null0 only
F -c "router ospf" -c "no default-information originate always"
waitnot "show rib route ip vrf default 0.0.0.0/0" "O.* +0.0.0.0/0"
check healthyB proof.yml

# extras: no default at all; VRF blue with connected 10.88.0.0/24 and a static 250 behind it; IPv6 likewise
E 'no ip route 0.0.0.0/0 Null0'
waitnot "show rib route ip vrf default 0.0.0.0/0" "0.0.0.0/0"
E $'vrf instance blue\nip routing vrf blue\ninterface Loopback1\nvrf blue\nip address 10.88.0.1/24\nip route vrf blue 10.88.0.0/24 Null0 250\nipv6 unicast-routing\ninterface Loopback2\nipv6 address 2001:db8:5::1/64\nipv6 route 2001:db8:5::/64 Null0 250\nvrf instance red\nrouter bgp 65030\nvrf blue\nrd 65030:1'
waitfor "show rib route ip vrf blue 10.88.0.0/24" "S +10.88.0.0/24"
waitfor "show rib route ipv6 vrf default 2001:db8:5::/64" "S +2001:db8:5::/64"
cap absent_rib_route_9.json "show rib route ip vrf default 9.9.9.0/24 | json"
cap absent_ip_route_9.json "show ip route vrf default 9.9.9.0/24 | json"
cap connected_rib_route.json "show rib route ip vrf default 10.0.200.0/30 | json"
cap vrf_rib_route.json "show rib route ip vrf blue 10.88.0.0/24 | json"
cap vrf_rib_route.txt "show rib route ip vrf blue 10.88.0.0/24"
cap vrf_ip_route.json "show ip route vrf blue 10.88.0.0/24 | json"
cap vrf_ip_bgp.json "show ip bgp 10.88.0.0/24 vrf blue | json"
cap vrf_absent_rib_route_9.json "show rib route ip vrf blue 9.9.9.0/24 | json"
cap nosuchvrf_rib_route.json "show rib route ip vrf nosuch 9.9.9.0/24 | json"
cap norouting_rib_route.json "show rib route ip vrf red 9.9.9.0/24 | json"
cap v6_rib_route.json "show rib route ipv6 vrf default 2001:db8:5::/64 | json"
cap v6_rib_route.txt "show rib route ipv6 vrf default 2001:db8:5::/64"
cap v6_ip_route.json "show ipv6 route vrf default 2001:db8:5::/64 | json"
cap v6_ip_bgp.json "show ipv6 bgp 2001:db8:5::/64 vrf default | json"
cap v6_absent_rib_route.json "show rib route ipv6 vrf default 2001:db8:99::/64 | json"
cap v6_absent_ip_route.json "show ipv6 route vrf default 2001:db8:99::/64 | json"
check extra extra.yml
cat $OUT/LOG
