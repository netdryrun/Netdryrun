#!/bin/bash
# phase A: no learned path from frr1; a static for each aggregate prefix on ceos1 (the static wins: distance 1 < 200)
F() { docker exec clab-ndr-rcheos-frr1 vtysh -c "configure terminal" "$@"; }
E() { docker exec clab-ndr-rcheos-ceos1 Cli -p 15 -c "$(printf 'configure\n%s\nend' "$1")"; }
F -c "router bgp 65020" -c "address-family ipv4 unicast" -c "no redistribute static" -c "exit-address-family" \
  -c "address-family ipv6 unicast" -c "no redistribute static"
E "$(printf 'ip route 10.66.0.0/16 Null0\nipv6 route 2001:db8:66::/48 Null0\nip route vrf blue 10.67.0.0/16 Null0')"
sleep 8
cd ~/recheck-eos-lab
./show.sh "show ip route vrf default 10.66.0.0/16" "show rib route ip vrf default 10.66.0.0/16" "show ip bgp 10.66.0.0/16 vrf default" \
  "show rib route ipv6 vrf default 2001:db8:66::/48" "show rib route ip vrf blue 10.67.0.0/16" | grep -Ev "^ +[A-Z].* - |Source Codes"
mkdir -p out
for c in "show ip route vrf default 10.66.0.0/16 | json" "show rib route ip vrf default 10.66.0.0/16 | json" "show ip bgp 10.66.0.0/16 vrf default | json" \
         "show rib route ip vrf default 10.66.0.0/16" "show rib route ipv6 vrf default 2001:db8:66::/48 | json" "show ipv6 route vrf default 2001:db8:66::/48 | json" \
         "show rib route ip vrf blue 10.67.0.0/16 | json" "show ip route vrf blue 10.67.0.0/16 | json" "show version"; do
  f=$(echo "$c" | tr ' /:|' '____' | tr -s _)
  docker exec clab-ndr-rcheos-ceos1 Cli -p 15 -c "$c" > "out/phaseA_$f.txt"
  echo "phaseA rc=$? $c $(date -u +%FT%TZ)" >> out/LOG
done
./probeall.sh phaseA
