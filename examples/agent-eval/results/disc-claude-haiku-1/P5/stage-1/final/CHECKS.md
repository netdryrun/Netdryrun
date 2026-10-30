# Checks for this change

Written by the network team. Every check must hold in the lab before a change goes to production.

- r1 session to r2 up: r1: the BGP session to 10.0.12.2 is established.
- r1 session to r3 up: r1: the BGP session to 10.0.13.2 is established.
- r2 gets r1's LAN: r2 has a route to 192.168.1.0/24 (BGP).
- r3 gets r1's LAN: r3 has a route to 192.168.1.0/24 (BGP).
- r2's LAN reaches r1's LAN: r2 pings 192.168.1.1 from 192.168.2.1.
