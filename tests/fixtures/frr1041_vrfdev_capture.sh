#!/usr/bin/env bash
# RT-0053 capture: ip -j addr with an address on the VRF device itself, in the pinned FRR image (no lab, one container)
docker run --rm --name ndr-cap-vrfdev --privileged quay.io/frrouting/frr:10.4.1 sh -c '
ip link add red type vrf table 10; ip link set red up
ip link add d0 type dummy; ip link set d0 master red; ip link set d0 up; ip addr add 10.0.23.1/30 dev d0
ip addr add 10.9.9.9/32 dev red; ip addr add 10.8.8.1/24 dev red; ip -6 addr add 2001:db8:99::9/128 dev red
echo "== ip -V"; ip -V
echo "== ip -j addr show vrf red"; ip -j addr show vrf red
echo "== ip -j addr"; ip -j addr
echo "== ip -j addr show dev red"; ip -j addr show dev red
echo "== ping vrf device /32"; ip vrf exec red ping -c 2 -W 1 10.9.9.9; echo rc=$?
echo "== ping other addr in /24 on vrf device"; ip vrf exec red ping -c 2 -W 1 10.8.8.77; echo rc=$?
echo "== local table 10"; ip route show table 10
echo "== ip vrf exec red ping enslaved addr"; ip vrf exec red ping -c 1 -W 1 10.0.23.1; echo rc=$?
'
