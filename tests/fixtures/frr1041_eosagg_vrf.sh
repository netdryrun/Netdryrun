# frr2: kernel VRF blue (table 10), then its BGP instance with the same aggregate as ceos1's vrf blue
. ~/eosagg/lib.sh
docker exec clab-ndr-eosagg-frr2 ip link add blue type vrf table 10
docker exec clab-ndr-eosagg-frr2 ip link set blue up
docker exec clab-ndr-eosagg-frr2 ip link add lo1 type dummy
docker exec clab-ndr-eosagg-frr2 ip link set lo1 master blue
docker exec clab-ndr-eosagg-frr2 ip link set lo1 up
sleep 2
F -c "ip route 10.67.1.0/24 blackhole vrf blue"
F -c "router bgp 65040 vrf blue" -c "bgp router-id 40.40.40.40" -c "address-family ipv4 unicast" -c "network 10.67.1.0/24" -c "aggregate-address 10.67.0.0/16"
V "show vrf"
