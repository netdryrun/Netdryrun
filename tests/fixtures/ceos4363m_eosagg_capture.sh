#!/bin/bash
# FP-043-EOSAGG captures on lab ndr-eosagg: cEOS 4.36.3M ceos1 and FRR 10.4.1 frr2 hold the same BGP aggregates
# (10.66.0.0/16, 2001:db8:66::/48, vrf blue 10.67.0.0/16, each with a contributing `network`), both peering with
# FRR 10.4.1 up1 (which accepts nothing from them). Each phase changes both the same way, then every file is the stdout,
# byte for byte, of `docker exec clab-ndr-eosagg-ceos1 Cli -p 15 -c "<command>"` or
# `docker exec clab-ndr-eosagg-frr2 vtysh -c "<command>"`, and the checks run through the real drivers on both (probe.py).
set -u
. ~/eosagg/lib.sh
OUT=~/eosagg/out
MAIN=~/oracle-eos-agg
FIX=~/oracle-eos-agg-fix
PY=~/.venvs/netdryrun/bin/python
mkdir -p $OUT
ce() { docker exec clab-ndr-eosagg-ceos1 Cli -p 15 -c "$3" > "$OUT/ceos4363m_eosagg_$1_$2" 2> "$OUT/stderr_ceos_$1_$2"
       echo "ceos1 $1 $2 rc=$? :: $3 :: $(date -u +%FT%TZ)" >> $OUT/LOG; }
fr() { docker exec clab-ndr-eosagg-frr2 vtysh -c "$3" > "$OUT/frr1041_eosagg_$1_$2" 2> "$OUT/stderr_frr_$1_$2"
       echo "frr2 $1 $2 rc=$? :: $3 :: $(date -u +%FT%TZ)" >> $OUT/LOG; }
caps() {   # caps <phase>: the reads the EOS driver makes (main: route + bgp; fix-eos-nonbgp: + rib) and the FRR ones
  local ph=$1
  for spec in "v4 ip default 10.66.0.0/16 ipv4" "v6 ipv6 default 2001:db8:66::/48 ipv6" "blue ip blue 10.67.0.0/16 ipv4"; do
    set -- $spec; local k=$1 fam=$2 vrf=$3 p=$4 afi=$5
    ce $ph ${k}_ip_route.json "show $fam route vrf $vrf $p | json"
    ce $ph ${k}_rib_route.json "show rib route $fam vrf $vrf $p | json"
    ce $ph ${k}_ip_bgp.json "show $fam bgp $p vrf $vrf | json"
    ce $ph ${k}_rib_route.txt "show rib route $fam vrf $vrf $p"
    ce $ph ${k}_ip_bgp.txt "show $fam bgp $p vrf $vrf"
    local vp=""; [ $vrf = default ] || vp=" vrf $vrf"
    fr $ph ${k}_ip_route.json "show $fam route$vp $p json"
    fr $ph ${k}_bgp.json "show bgp$vp $afi unicast $p json"
    fr $ph ${k}_ip_route.txt "show $fam route$vp $p"
    fr $ph ${k}_bgp.txt "show bgp$vp $afi unicast $p"
  done
  fr $ph vrf.txt "show vrf"
}
check() {   # check <phase>: the oracle checks through the real drivers on the live nodes (probe.py), EOS with main and
            # with fix-eos-nonbgp, FRR with main (the FRR driver is the same on both)
  local ph=$1
  (cd $MAIN && PYTHONPATH=src $PY ~/eosagg/probe.py "$ph eos main $(git rev-parse --short HEAD)" eos ceos1) > "$OUT/ceos4363m_eosagg_${ph}_verdicts_main.txt" 2>&1
  (cd $FIX && PYTHONPATH=src $PY ~/eosagg/probe.py "$ph eos fix $(git rev-parse --short HEAD)" eos ceos1) > "$OUT/ceos4363m_eosagg_${ph}_verdicts_fix.txt" 2>&1
  (cd $MAIN && PYTHONPATH=src $PY ~/eosagg/probe.py "$ph frr main $(git rev-parse --short HEAD)" frr frr2) > "$OUT/frr1041_eosagg_${ph}_verdicts.txt" 2>&1
  cat "$OUT/ceos4363m_eosagg_${ph}_verdicts_main.txt" "$OUT/ceos4363m_eosagg_${ph}_verdicts_fix.txt" "$OUT/frr1041_eosagg_${ph}_verdicts.txt" >> $OUT/VERDICTS
  echo "probe $ph done $(date -u +%FT%TZ)" >> $OUT/LOG
}
phase() { caps $1; check $1; }

: > $OUT/LOG; : > $OUT/VERDICTS
C "show version" > $OUT/ceos4363m_eosagg_show_version.txt
V "show version" > $OUT/frr1041_eosagg_show_version.txt
C "show running-config" > $OUT/ceos4363m_eosagg_running_config_start.txt
V "show running-config" > $OUT/frr1041_eosagg_running_config_start.txt

# sel: each aggregate selected, its contributor the node's own network, nothing learned in the range
waitc "show ip route vrf default 10.66.0.0/16" "A B +10.66.0.0/16"
waitc "show ipv6 route vrf default 2001:db8:66::/48" "A B +2001:db8:66::/48"
waitc "show ip route vrf blue 10.67.0.0/16" "A B +10.67.0.0/16"
waitf "show ip route vrf blue 10.67.0.0/16" "Known via .bgp"
phase sel

# selms: the own contributors withdrawn (default VRF, both families), up1 sends a more-specific: the only contributor
# of the aggregate is learned
E "$(printf 'router bgp 65030\nno network 10.66.1.0/24')"
E "$(printf 'router bgp 65030\naddress-family ipv6\nno network 2001:db8:66:1::/64')"
F -c "router bgp 65040" -c "address-family ipv4 unicast" -c "no network 10.66.1.0/24"
F -c "router bgp 65040" -c "address-family ipv6 unicast" -c "no network 2001:db8:66:1::/64"
U -c "router bgp 65020" -c "address-family ipv4 unicast" -c "network 10.66.2.0/24"
U -c "router bgp 65020" -c "address-family ipv6 unicast" -c "network 2001:db8:66:2::/64"
waitc "show ip bgp 10.66.2.0/24 vrf default" "10.0.200.2"
waitc "show ipv6 bgp 2001:db8:66:2::/64 vrf default" "2001:db8:200::2"
waitcn "show ip bgp 10.66.1.0/24 vrf default" "10.66.1.0/24"
waitf "show bgp ipv4 unicast 10.66.2.0/24" "10.0.210.2"
waitf "show bgp ipv6 unicast 2001:db8:66:2::/64" "2001:db8:210::2"
waitfn "show bgp ipv4 unicast 10.66.1.0/24" "10.66.1.0/24"
sleep 5
phase selms
U -c "router bgp 65020" -c "address-family ipv4 unicast" -c "no network 10.66.2.0/24"
U -c "router bgp 65020" -c "address-family ipv6 unicast" -c "no network 2001:db8:66:2::/64"
E "$(printf 'router bgp 65030\nnetwork 10.66.1.0/24')"
E "$(printf 'router bgp 65030\naddress-family ipv6\nnetwork 2001:db8:66:1::/64')"
F -c "router bgp 65040" -c "address-family ipv4 unicast" -c "network 10.66.1.0/24"
F -c "router bgp 65040" -c "address-family ipv6 unicast" -c "network 2001:db8:66:1::/64"
waitcn "show ip bgp 10.66.2.0/24 vrf default" "10.66.2.0/24"
waitfn "show bgp ipv4 unicast 10.66.2.0/24" "10.66.2.0/24"

# exact: up1 also sends the exact prefix of the aggregate (a learned path for it), both families
U -c "router bgp 65020" -c "address-family ipv4 unicast" -c "network 10.66.0.0/16"
U -c "router bgp 65020" -c "address-family ipv6 unicast" -c "network 2001:db8:66::/48"
waitc "show ip bgp 10.66.0.0/16 vrf default" "10.0.200.2"
waitc "show ipv6 bgp 2001:db8:66::/48 vrf default" "2001:db8:200::2"
waitf "show bgp ipv4 unicast 10.66.0.0/16" "10.0.210.2"
waitf "show bgp ipv6 unicast 2001:db8:66::/48" "2001:db8:210::2"
sleep 5
phase exact

# exactstatic: a static (Null0 / blackhole) for each aggregate prefix as well; the learned exact path stays
E "$(printf 'ip route 10.66.0.0/16 Null0\nipv6 route 2001:db8:66::/48 Null0\nip route vrf blue 10.67.0.0/16 Null0')"
F -c "ip route 10.66.0.0/16 blackhole" -c "ipv6 route 2001:db8:66::/48 blackhole" -c "ip route 10.67.0.0/16 blackhole vrf blue"
waitc "show ip route vrf default 10.66.0.0/16" "S +10.66.0.0/16"
waitc "show ipv6 route vrf default 2001:db8:66::/48" "S +2001:db8:66::/48"
waitc "show ip route vrf blue 10.67.0.0/16" "S +10.67.0.0/16"
waitf "show ip route vrf blue 10.67.0.0/16" "Known via .static.*best"
sleep 5
phase exactstatic

# static (the setup of corpus v2 case 18): the learned exact path withdrawn; the static wins, the aggregate stays
U -c "router bgp 65020" -c "address-family ipv4 unicast" -c "no network 10.66.0.0/16"
U -c "router bgp 65020" -c "address-family ipv6 unicast" -c "no network 2001:db8:66::/48"
waitcn "show ip bgp 10.66.0.0/16 vrf default" "10.0.200.2"
waitcn "show ipv6 bgp 2001:db8:66::/48 vrf default" "2001:db8:200::2"
waitfn "show bgp ipv4 unicast 10.66.0.0/16" "10.0.210.2"
waitfn "show bgp ipv6 unicast 2001:db8:66::/48" "2001:db8:210::2"
sleep 5
phase static

# healthystatic: every aggregate removed; the statics stay (no BGP route of any kind for the prefixes)
E "$(printf 'router bgp 65030\nno aggregate-address 10.66.0.0/16')"
E "$(printf 'router bgp 65030\naddress-family ipv6\nno aggregate-address 2001:db8:66::/48')"
E "$(printf 'router bgp 65030\nvrf blue\nno aggregate-address 10.67.0.0/16')"
F -c "router bgp 65040" -c "address-family ipv4 unicast" -c "no aggregate-address 10.66.0.0/16"
F -c "router bgp 65040" -c "address-family ipv6 unicast" -c "no aggregate-address 2001:db8:66::/48"
F -c "router bgp 65040 vrf blue" -c "address-family ipv4 unicast" -c "no aggregate-address 10.67.0.0/16"
waitcn "show rib route ip vrf default 10.66.0.0/16" " B +10.66.0.0/16"
waitcn "show rib route ipv6 vrf default 2001:db8:66::/48" " B +2001:db8:66::/48"
waitcn "show rib route ip vrf blue 10.67.0.0/16" " B +10.67.0.0/16"
waitfn "show ip route vrf blue 10.67.0.0/16" "bgp"
waitfn "show ip route 10.66.0.0/16" "bgp"
waitfn "show ipv6 route 2001:db8:66::/48" "bgp"
sleep 5
phase healthystatic

# healthy: the statics removed too: nothing for the prefixes
E "$(printf 'no ip route 10.66.0.0/16 Null0\nno ipv6 route 2001:db8:66::/48 Null0\nno ip route vrf blue 10.67.0.0/16 Null0')"
F -c "no ip route 10.66.0.0/16 blackhole" -c "no ipv6 route 2001:db8:66::/48 blackhole" -c "no ip route 10.67.0.0/16 blackhole vrf blue"
waitcn "show rib route ip vrf default 10.66.0.0/16" "S +10.66.0.0/16"
waitfn "show ip route vrf blue 10.67.0.0/16" "static"
sleep 5
phase healthy

# FRR refuses `protocol: aggregate` before deploying anything
(cd $MAIN && PYTHONPATH=src $PY -m netdryrun check ~/eosagg/frr_agg.yml --settle 2 --hold 6 > "$OUT/frr1041_eosagg_aggrefused_check.txt" 2>&1
 echo "frr2 aggrefused check main exit=$?" >> $OUT/LOG)
C "show running-config" > $OUT/ceos4363m_eosagg_running_config_end.txt
V "show running-config" > $OUT/frr1041_eosagg_running_config_end.txt
grep -v "rc=0" $OUT/LOG; echo DONE
