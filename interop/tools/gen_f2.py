"""Writes L1's upstream config (f2.conf): N consecutive /24s from 100.64.0.0 plus a contributor to f1's aggregate.

python interop/tools/gen_f2.py 200 > interop/L1/base/configs/f2.conf
python interop/tools/gen_f2.py 2000 > interop/L1/overlays/M14/f2.conf
"""
import ipaddress
import sys

n = int(sys.argv[1])
base = int(ipaddress.ip_address("100.64.0.0"))
statics = "\n".join(f"ip route {ipaddress.ip_address(base + 256 * i)}/24 blackhole" for i in range(n))
print(f"""frr defaults datacenter
hostname f2
!
interface lo
 ip address 192.168.6.1/24
!
interface eth1
 ip address 10.1.5.1/30
!
{statics}
ip route 172.16.6.0/24 blackhole
!
ip prefix-list UPSTREAM-TABLE seq 10 permit 100.64.0.0/10 ge 24 le 24
ip prefix-list UPSTREAM-TABLE seq 20 permit 172.16.6.0/24
!
route-map STATICS permit 10
 match ip address prefix-list UPSTREAM-TABLE
!
route-map ACCEPT-ALL permit 10
!
route-map TO-F1 permit 10
!
router bgp 65006
 bgp router-id 6.6.6.6
 neighbor 10.1.5.2 remote-as 65005
 address-family ipv4 unicast
  network 192.168.6.0/24
  redistribute static route-map STATICS
  neighbor 10.1.5.2 route-map ACCEPT-ALL in
  neighbor 10.1.5.2 route-map TO-F1 out
  neighbor 10.1.5.2 default-originate
 exit-address-family
!""")
