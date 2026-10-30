# r1 startup config, RouterOS 7.23 (uploaded by vrnetlab over FTP as config.auto.rsc and imported; an import stops at its
# first error).
/system identity set name=r1
# RouterOS already has a loopback interface named lo
/ip address add address=192.168.10.1/32 interface=lo
/ip address add address=10.0.100.1/30 interface=ether2
/ip route add dst-address=0.0.0.0/0 blackhole comment="static default"
/ip firewall address-list add list=own-lan address=192.168.10.1/32
/routing filter rule add chain=ACCEPT-ALL rule="accept"
/routing filter rule add chain=EXPORT-OWN rule="if (dst == 192.168.10.1/32) { accept }"
/routing filter rule add chain=EXPORT-OWN rule="reject"
# RouterOS 7.23: the AS and router id live in a BGP instance, which a connection must name
/routing bgp instance add name=bgp1 as=65010 router-id=10.10.10.10
/routing bgp template set default output.network=own-lan
/routing bgp connection add name=frr1 instance=bgp1 templates=default remote.address=10.0.100.2 remote.as=65020 local.role=ebgp input.filter=ACCEPT-ALL output.filter-chain=EXPORT-OWN
/log info message="NDR r1.rsc imported to the last line"
