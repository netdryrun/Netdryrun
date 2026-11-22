#!/bin/bash
# shellcheck disable=SC1090,SC2024,SC2034,SC2164  # a lab capture script kept as it ran (the record of how the fixtures were made)
# fix-eos-nonbgp round 2 (adversary review) on lab ndr-fix043b (cEOS 4.36.3M + FRR 10.4.1): the oracle's phases and
# the extras again with the fixed code, then a BGP aggregate (with and without a learned BGP path for the same
# prefix), the martian routeInput entries, an unresolved static and an OSPF area range, captured for unit tests.
set -u
D=~/fix043b
OUT=$D/out
REPO=~/fix-eos-nonbgp-wip
PY=~/.venvs/netdryrun/bin/python
mkdir -p $OUT
C() { docker exec clab-ndr-fix043b-ceos1 Cli -p 15 -c "$1"; }
F() { docker exec clab-ndr-fix043b-frr1 vtysh -c "configure terminal" "$@"; }
E() { C "$(printf 'configure\n%s\nend' "$1")"; }
cap() { C "$2" > "$OUT/ceos4363m_fix043b_$1" 2> "$OUT/stderr_$1"; echo "$1 rc=$? :: $2 :: $(date -u +%FT%TZ)" >> $OUT/LOG; }
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
C "show version" > $OUT/ceos4363m_fix043b_show_version.txt
docker exec clab-ndr-fix043b-frr1 ip link set eth2 mtu 1500
F -c "interface eth2" -c "ip ospf mtu-ignore"
waitfor "show ip ospf neighbor" "FULL"
waitfor "show ip route vrf default 0.0.0.0/0" "B E +0.0.0.0/0"

# the martian entries a plain cEOS lists in the RIB only, before any change
cap martian0_rib_route.json "show rib route ip vrf default 0.0.0.0/8 | json"
cap martian0_rib_route.txt "show rib route ip vrf default 0.0.0.0/8"
cap martian0_ip_route.json "show ip route vrf default 0.0.0.0/8 | json"
cap martian127_rib_route.json "show rib route ip vrf default 127.0.0.0/8 | json"
cap martian127_rib_route.txt "show rib route ip vrf default 127.0.0.0/8"
cap martian127_ip_route.json "show ip route vrf default 127.0.0.0/8 | json"
cap rib_all.txt "show rib route ip vrf default"

# the oracle's phases with the fix
E 'ip route 0.0.0.0/0 10.0.201.2 250'
waitfor "show rib route ip vrf default 0.0.0.0/0" "^ S +0.0.0.0/0 \[250"
check rt0056 proof.yml
E 'no ip route 0.0.0.0/0 10.0.201.2 250'
waitnot "show rib route ip vrf default 0.0.0.0/0" "^ S "
check healthyA proof.yml
F -c "router bgp 65020" -c "address-family ipv4 unicast" -c "no neighbor 10.0.200.1 default-originate"
F -c "router ospf" -c "default-information originate always"
E 'ip route 0.0.0.0/0 Null0'
waitnot "show ip bgp 0.0.0.0/0 vrf default" "10.0.200.2"
waitfor "show rib route ip vrf default 0.0.0.0/0" "O.* +0.0.0.0/0"
waitfor "show ip route vrf default 0.0.0.0/0" "S +0.0.0.0/0"
check rt0063 proof.yml
F -c "router ospf" -c "no default-information originate always"
waitnot "show rib route ip vrf default 0.0.0.0/0" "O.* +0.0.0.0/0"
check healthyB proof.yml
E 'no ip route 0.0.0.0/0 Null0'
waitnot "show rib route ip vrf default 0.0.0.0/0" "0.0.0.0/0"

# extras as in round 1
E "$(printf 'vrf instance blue\nip routing vrf blue\ninterface Loopback1\nvrf blue\nip address 10.88.0.1/24\nip route vrf blue 10.88.0.0/24 Null0 250\nipv6 unicast-routing\ninterface Loopback2\nipv6 address 2001:db8:5::1/64\nipv6 route 2001:db8:5::/64 Null0 250\nvrf instance red\nrouter bgp 65030\nvrf blue\nrd 65030:1')"
waitfor "show rib route ip vrf blue 10.88.0.0/24" "S +10.88.0.0/24"
waitfor "show rib route ipv6 vrf default 2001:db8:5::/64" "S +2001:db8:5::/64"
check extra extra.yml

# agg: ceos1's own aggregate 10.66.0.0/16 (from a static 10.66.1.0/24 it announces), no BGP-learned /16
E "$(printf 'ip route 10.66.1.0/24 Null0\nrouter bgp 65030\nnetwork 10.66.1.0/24\naggregate-address 10.66.0.0/16')"
waitfor "show ip route vrf default 10.66.0.0/16" "10.66.0.0/16"
sleep 5
cap agg_ip_route.json "show ip route vrf default 10.66.0.0/16 | json"
cap agg_rib_route.json "show rib route ip vrf default 10.66.0.0/16 | json"
cap agg_rib_route.txt "show rib route ip vrf default 10.66.0.0/16"
cap agg_ip_bgp.json "show ip bgp 10.66.0.0/16 vrf default | json"
check agg agg.yml

# aggleak: frr1 also sends 10.66.0.0/16 over eBGP; the aggregate stays selected
F -c "ip route 10.66.0.0/16 blackhole" -c "router bgp 65020" -c "address-family ipv4 unicast" -c "network 10.66.0.0/16"
waitfor "show ip bgp 10.66.0.0/16 vrf default" "10.0.200.2"
sleep 5
cap aggleak_ip_route.json "show ip route vrf default 10.66.0.0/16 | json"
cap aggleak_rib_route.json "show rib route ip vrf default 10.66.0.0/16 | json"
cap aggleak_rib_route.txt "show rib route ip vrf default 10.66.0.0/16"
cap aggleak_ip_bgp.json "show ip bgp 10.66.0.0/16 vrf default | json"
check aggleak agg.yml

# an unresolved static and an OSPF area range
E "$(printf 'ip route 10.77.0.0/24 192.0.2.99\ninterface Loopback3\nip address 10.55.1.1/24\nrouter ospf 1\nnetwork 10.55.1.0/24 area 0.0.0.1\narea 0.0.0.1 range 10.55.0.0/16')"
sleep 15
cap unresolved_rib_route.json "show rib route ip vrf default 10.77.0.0/24 | json"
cap unresolved_ip_route.json "show ip route vrf default 10.77.0.0/24 | json"
cap ospfrange_ip_route.json "show ip route vrf default 10.55.0.0/16 | json"
cap ospfrange_rib_route.json "show rib route ip vrf default 10.55.0.0/16 | json"
cap ospfrange_rib_route.txt "show rib route ip vrf default 10.55.0.0/16"
cap ospfrange_ip_bgp.json "show ip bgp 10.55.0.0/16 vrf default | json"
cap rib_all_end.txt "show rib route ip vrf default"
cap ip_route_all_end.txt "show ip route vrf default"
cat $OUT/LOG
