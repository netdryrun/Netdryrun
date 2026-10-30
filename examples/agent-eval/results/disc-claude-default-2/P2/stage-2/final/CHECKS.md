# Checks for this change

Written by the network team. Every check must hold in the lab before a change goes to production.

- TICKET r2 gets 192.168.0.0/16 from r1: r2's best BGP path to 192.168.0.0/16 has AS path 65001.
- TICKET r3 gets 192.168.0.0/16 from r1: r3's best BGP path to 192.168.0.0/16 has AS path 65001.
- TICKET r2 still gets r1's 192.168.1.0/24: r2 has a route to 192.168.1.0/24 (BGP).
- r1: the BGP session to 10.0.12.2 is established.
- r1: the BGP session to 10.0.13.2 is established.
- r1 receives at least 1 and at most 10 prefixes from 10.0.12.2.
- r1 has a route to 192.168.3.0/24 (BGP).
- r1 pings 192.168.3.1 from 192.168.1.1.
- r1's best BGP path to 192.168.2.0/24 has AS path 65002, next hop 10.0.12.2.
- r1 has no BGP route to 0.0.0.0/0.

With r1's interface eth1 down (r1-r2 link fails), and the link restored afterwards:

- r1 has a route to 192.168.2.0/24 (BGP).
- r1's best BGP path to 192.168.2.0/24 has AS path 65003 65002, next hop 10.0.13.2.
- r1 pings 192.168.2.1 from 192.168.1.1.
- r1: the BGP session to 10.0.12.2 is not established (any state except established).
