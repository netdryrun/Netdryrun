# A transit leak that ping can't see

A network learns routes from its transit provider and, after a policy change, announces them to a settlement-free peer. Every BGP session stays up and the customer is still reachable, but the peer now has the provider's prefix in its table, learned through you.

This is the pattern [RFC 7908](https://www.rfc-editor.org/rfc/rfc7908) calls *Type 3: Leak of Transit-Provider Prefixes to Peer*. The lab reproduces the mechanism (a wrong outbound policy), not any specific incident.

## The lab

```text
                     prov (AS 65020)  203.0.113.0/24
                        |  10.0.2.0/30
cust (AS 65010)  --  net (AS 65001)  --  peer (AS 65030)
192.0.2.0/24    10.0.1.0/30   |   10.0.3.0/30    198.51.100.0/24
                          172.16.0.0/24
```

`net` is the network under change. Four FRR 10.4.1 routers (`quay.io/frrouting/frr:10.4.1`).

- [`configs/net.conf`](configs/net.conf) is the correct config. Inbound it sets a community by where each route was learned (65001:300 for customer routes). The route-maps `TO-PEER` and `TO-PROVIDER` send the peer and the provider only customer routes and `net`'s own prefix.
- [`configs/net-leaky.conf`](configs/net-leaky.conf) is the same file with one line changed: the peer's outbound policy is `ALLOW-ALL`, a route-map with one empty permit clause.

```diff
-  neighbor 10.0.3.2 route-map TO-PEER out
+  neighbor 10.0.3.2 route-map ALLOW-ALL out
```

## Run it

From a clone of this repository, with Docker and containerlab on a host that allows privileged containers (or in Codespaces):

```bash
pip install netdryrun
netdryrun run examples/leak-pattern/netdryrun.yml        # correct config: PASSED, 8 of 8
netdryrun run examples/leak-pattern/netdryrun-leaky.yml  # the change: FAILED, 6 passed, 2 failed
netdryrun run examples/leak-pattern/netdryrun-roles.yml  # the change plus BGP roles: PASSED, 8 of 8
```

To look around by hand:

```bash
cd examples/leak-pattern
containerlab deploy -t topology-leaky.clab.yml
docker exec -it clab-ndr-leak-pattern-net vtysh -c "show bgp ipv4 unicast neighbors 10.0.3.2 advertised-routes"
docker exec -it clab-ndr-leak-pattern-peer vtysh -c "show bgp ipv4 unicast"
containerlab destroy -t topology-leaky.clab.yml --cleanup
```

## What the checks show

Sessions up, the peer's BGP route to the customer, its AS path, and a ping to the customer pass on every config. The two that fail on the leaky one:

- `peer` accepts 3 prefixes from `net` instead of exactly 2. (An exact count is brittle: it fails when a legitimate customer prefix is added.)
- `peer` has a BGP route to `203.0.113.0/24`, the provider's prefix.

Both checks look at the peer's table, not at what `net` advertises, so a peer that filters on its side would hide the leak from them.

## The same change with BGP roles

`netdryrun-roles.yml` runs the leaky policy with [RFC 9234](https://www.rfc-editor.org/rfc/rfc9234) roles configured on both ends of every session (`local-role` in [`configs-roles/`](configs-roles/)). `net` marks routes learned from its provider with the Only-to-Customer attribute and does not send them to the peer, even though the outbound policy would permit them. Roles only work when both neighbours configure them, so this protects you from your own policy mistakes, not from a peer that has no roles.

## Limits

A pass covers only the checks written here. This lab doesn't use RPKI, IRR filters or maximum-prefix limits on the receiving side, and FRR's defaults are not another vendor's.
