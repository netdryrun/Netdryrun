# Checks for this change

Written by the network team. Every check must hold in the lab before a change goes to production.

- GUARD session to cust1 up: edge1: the BGP session to 10.0.1.2 is established.
- GUARD session to up1 up: edge1: the BGP session to 10.0.2.2 is established.
- GUARD session to peer1 up: edge1: the BGP session to 10.0.3.2 is established.
- GUARD up1 receives our block: up1 has a route to 192.0.2.0/24 (BGP).
- GUARD peer1 receives the customer's 10.100.0.0/24: peer1 has a route to 10.100.0.0/24 (BGP).
- GUARD customer reaches the internet via up1: cust1 pings 203.0.113.1 from 10.100.0.1.
- LEAK GUARD peer1 must not get upstream routes: peer1 has no BGP route to 203.0.113.0/24.
- LEAK GUARD peer1 must not get the upstream's default route: peer1 has no BGP route to 0.0.0.0/0.
- LEAK GUARD up1 must not get peer routes: up1 has no BGP route to 198.51.100.0/24.
- LEAK GUARD peer1 gets at most our 2 prefixes: peer1 receives at most 2 prefixes from 10.0.3.1.
- LEAK GUARD edge1 rejects prefixes the customer doesn't own: edge1 has no BGP route to 8.8.8.0/24.
