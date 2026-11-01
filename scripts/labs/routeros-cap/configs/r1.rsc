# r1, RouterOS 7.23 (uploaded by vrnetlab over FTP as config.auto.rsc and imported; an import stops at its first error)
/system identity set name=r1
/ip address add address=10.10.10.1/32 interface=lo
/ip address add address=192.0.2.1/30 interface=ether2
/ip address add address=198.51.100.1/30 interface=ether3
/ip address add address=192.0.2.5/30 interface=ether5
/ip vrf add name=RED interfaces=ether4
# the VRF's routing table appears a moment later; a connection naming it before then is rejected (live, CHR 7.23.8)
:delay 5s
/ip address add address=203.0.113.1/30 interface=ether4
/ip route add dst-address=0.0.0.0/0 blackhole comment="static default"
/ip firewall address-list add list=bgp-nets address=10.10.10.1/32
/routing filter rule add chain=FROM-PEER1 rule="if (dst == 10.66.0.0/24) { reject }"
/routing filter rule add chain=FROM-PEER1 rule="if (dst == 10.20.0.0/24) { set bgp-local-pref 200; accept }"
/routing filter rule add chain=FROM-PEER1 rule="accept"
/routing filter rule add chain=ACCEPT-ALL rule="accept"
/routing bgp instance add name=bgp1 as=65001 router-id=10.10.10.1
/routing bgp template set default output.network=bgp-nets
/routing bgp connection add name=peer1 instance=bgp1 templates=default remote.address=192.0.2.2 remote.as=65002 local.role=ebgp input.filter=FROM-PEER1 output.filter-chain=ACCEPT-ALL
/routing bgp connection add name=peer2 instance=bgp1 templates=default remote.address=198.51.100.2 remote.as=65004 local.role=ebgp input.filter=ACCEPT-ALL output.filter-chain=ACCEPT-ALL
/routing bgp connection add name=quiet instance=bgp1 templates=default remote.address=192.0.2.6 remote.as=65005 local.role=ebgp input.filter=ACCEPT-ALL output.filter-chain=ACCEPT-ALL
/routing bgp connection add name=idle instance=bgp1 templates=default remote.address=192.0.2.99 remote.as=65009 local.role=ebgp
/routing bgp connection add name=red1 instance=bgp1 templates=default routing-table=RED vrf=RED remote.address=203.0.113.2 remote.as=65003 local.role=ebgp input.filter=ACCEPT-ALL output.filter-chain=ACCEPT-ALL
/log info message="NDR r1.rsc imported to the last line"
