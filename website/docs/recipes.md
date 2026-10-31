---
title: Guard recipes and scenarios
description: Copy-paste netdryrun.yml fragments for frequent BGP mistakes (a default route leaked, a prefix flood, link subnets in BGP, a max-prefix limit, communities dropped) and a catalog of failure scenarios (link down, node isolated, a peer sends extra prefixes).
---

# Guard recipes and scenarios

`netdryrun record` writes down what exists. These fragments add what must **never** happen, plus failures the network must survive. Paste them under `checks:` or `scenarios:` in your `netdryrun.yml`, then change the node names, neighbors and prefixes to your lab's.

The node names and addresses are those of the [`frr-bgp` example](examples.md#frr-bgp): three FRR routers in a triangle, r1 (AS 65001, `10.0.12.1` to r2, `10.0.13.1` to r3), r2 (AS 65002) and r3 (AS 65003), each announcing one LAN, `192.168.<n>.0/24`. Every fragment on this page passes `netdryrun validate` when added to [`examples/frr-bgp/netdryrun.yml`](https://github.com/netdryrun/Netdryrun/blob/main/examples/frr-bgp/netdryrun.yml). Check yours the same way, without starting a lab:

```bash
netdryrun validate my-lab
```

!!! note "Tested in a lab"
    Each fragment was run on 2026-10-28 with Netdryrun™ 0.3.1, containerlab 0.81.1 and FRR 10.4.1: every guard passed on the `frr-bgp` lab (or the variant named under it) and failed on a copy with the mistake it guards against, with only the guard failing. The **Tested** line under each fragment names both labs and quotes the failure. Each run had the fragment plus r1's two session checks. Your lab is not this lab: run a guard once against a known-bad change in yours before you trust it.

Every key used here is in the [netdryrun.yml reference](reference/config.md), which also explains when each check runs. Most guards are [post-convergence checks](reference/config.md#convergence-semantics): they wait until every configured BGP session on their node is up, then must hold for 10 seconds, so they can't pass just because BGP hasn't come up yet.

## Guard recipes

### No default route via BGP

The most common leak: someone adds `default-originate`, or an export filter that matches the static default. The router may not even use the leaked route (it loses to its own default), so sessions, ping and the forwarding path all look unchanged. `route` with `present: false` fails on a BGP path that was received, selected or not.

```yaml title="checks:"
- type: route          # nobody sends r1 a default route
  node: r1
  prefix: 0.0.0.0/0
  protocol: bgp
  present: false
```

**Tested:** passes on `frr-bgp`; fails on r2 with `neighbor 10.0.12.1 default-originate` (the `frr-bgp-broken` change), exit 1:

```text
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.6s)
```

For IPv6, add the same check for `::/0`. The [`frr-bgp-broken`](examples.md#frr-bgp-broken) example is this check catching a leaked default, and [Ping and "BGP up" passed](posts/ping-missed-the-leak.md) walks through it.

### A prefix-count ceiling

One check per neighbor that catches a leak of *any* prefix, including ones nobody thought to list: a full table, a peer's routes passed to another peer, a redistribution that pulls in more than it should. Set `max` with room for normal growth.

```yaml title="checks:"
- type: bgp_prefixes   # r2 sends r1 between 1 and 10 prefixes
  node: r1
  neighbor: 10.0.12.2
  min: 1
  max: 10
```

The count is of *accepted* prefixes (received minus rejected by import policy), so this also shows a filter that suddenly drops everything (`min`). From 0.3.3, `netdryrun record` writes both sides for every neighbor: today's count as `min` and `max` with 20% headroom; adjust `max` to the growth you expect. `record` also writes the no-default-route and link-subnet guards below for every BGP node (`--no-guards` leaves them out).

**Tested:** passes on `frr-bgp` (2 prefixes); fails on r2 announcing 12 extra static /24s with `redistribute static`, exit 1:

```text
  [FAIL] r1: prefixes from 10.0.12.2 >= 1 and <= 10 -- 14 ipv4-unicast prefixes accepted (0.3s)
```

### No infrastructure or link routes at the edge

`redistribute connected` announces every connected subnet, including the point-to-point links between routers. The LAN arrives and the ping passes, but the link subnets leak too. List the infrastructure prefixes that must stay out of BGP: one check per prefix, because a check matches the prefix you give.

```yaml title="checks:"
- type: route          # the r2-r3 link subnet stays out of BGP
  node: r1
  prefix: 10.0.23.0/30
  protocol: bgp
  present: false
```

The [tutorial](tutorial.md#5-make-a-change-and-run-it) shows this check failing on a `redistribute connected` change while every session, the ping and the prefix-count range pass. Loopbacks and management ranges work the same way.

**Tested:** passes on `frr-bgp`; fails on r3 with `redistribute connected`, exit 1:

```text
  [FAIL] r1: route 10.0.23.0/30 via bgp is absent -- unexpectedly present via bgp (0.4s)
```

### Communities preserved, internal tags stripped

A route can arrive with the right prefix and the wrong attributes: a route-map rewrite that drops a customer community, or an internal tag that leaks to a peer. `bgp_route` checks the BGP best path's attributes. Quote communities: YAML reads some unquoted values as numbers.

```yaml title="checks:"
- type: bgp_route      # r2's LAN keeps its community on the way to r1
  node: r1
  prefix: 192.168.2.0/24
  communities: ["65002:100"]

- type: bgp_route      # and never carries the internal blackhole tag
  node: r1
  prefix: 192.168.2.0/24
  without_communities: ["65002:666", blackhole]
```

The bundled `frr-bgp` routers don't set communities, so the first check fails there by design: tag the route on r2 (a route-map with `set community 65002:100` on its export) before you rely on it. `bgp_route` also checks `as_path`, `as_path_regex`, `local_pref`, `med` and `next_hop`; see [bgp_route](reference/config.md#bgp_route).

**Tested:** both pass on `frr-bgp` with r2 tagging its export to r1 (`route-map TAG-R1 permit 10` with `set community 65002:100`, applied `out` on `neighbor 10.0.12.1`). Without the tag (the bundled lab) the first fails; with `set community 65002:100 65002:666` the second fails. Exit 1 each time:

```text
  [FAIL] r1: BGP best path for 192.168.2.0/24 has communities 65002:100 -- missing communities 65002:100 (best path: as-path '65002', next hop 10.0.12.2, local-pref 100, MED 0, communities none) (0.5s)
  [FAIL] r1: BGP best path for 192.168.2.0/24 has no communities 65002:666 blackhole -- carries communities 65002:666 (best path: as-path '65002', next hop 10.0.12.2, local-pref 100, MED 0, communities 65002:100 65002:666) (0.6s)
```

### Max-prefix holds when a neighbor floods you

A ceiling check says what the network *should* accept. This scenario makes a neighbor actually send too much, so the max-prefix limit in your config is exercised, not just written down. `inject_routes` makes an FRR node announce extra routes for the length of the scenario, then removes them.

Here the config under test has `neighbor 10.0.12.2 maximum-prefix 10 restart 1` on r1, and r2 floods 50 prefixes. FRR closes the session, and with `restart 1` reopens it a minute later:

```yaml title="scenarios:"
- name: r2 sends more than the max-prefix limit
  inject_routes: {node: r2, count: 50, from: 10.100.0.0/24}
  checks:
    - type: bgp_session    # the limit tripped and closed the session
      node: r1
      neighbor: 10.0.12.2
      state: down
    - type: route          # r2's LAN is still reachable, through r3
      node: r1
      prefix: 192.168.2.0/24
      protocol: bgp
```

**Tested:** passes on `frr-bgp` with that line on r1 (the session was `idle` during the flood and came back after it); fails on the bundled lab, which has no limit, exit 1:

```text
  [FAIL] [r2 sends more than the max-prefix limit] r1: BGP session to 10.0.12.2 is down -- state is established (0.5s)
```

**The limit needs `restart`.** Netdryrun checks that the network recovers after every scenario. With `maximum-prefix 10` and no `restart`, FRR kept the session down after the injected routes were withdrawn, and the run failed on recovery, exit 1 (later scenarios would have been skipped):

```text
  [FAIL] [after r2 sends more than the max-prefix limit] recovers: r1: BGP session to 10.0.12.2 is established -- state is idle (120.5s)
```

In a triangle, r3 also passes r2's flood on to r1, unless r1 limits r3 too: the topology decides what your guards must cover.

## Route checks for any protocol

`route` reads the routing table, so its checks work for routes from any protocol, not only BGP: set `protocol` to `ospf`, `ospf6`, `isis`, `static`, `connected` and the other names in [protocol names](reference/config.md#protocol-names).

```yaml title="checks:"
- type: route          # r1 learns r2's loopback from OSPF, not from a static
  node: r1
  prefix: 10.255.0.2/32
  protocol: ospf
```

**Tested:** passes on `frr-bgp` with `ospfd` enabled and OSPF on the r1-r2 link, r2 advertising loopback `10.255.0.2/32`; fails on the bundled lab (no OSPF) at its 60-second timeout, exit 1:

```text
  [FAIL] r1: route 10.255.0.2/32 via ospf is present -- not active via ospf; seen: nothing (60.4s)
```

Netdryrun can't check OSPF or IS-IS adjacencies themselves yet: those checks are on the roadmap, not in a release yet. Until then, a route learned from the protocol is the evidence that the adjacency came up.

## Scenario catalog

`scenarios:` runs extra checks while something is wrong, then restores the network. Each scenario needs at least one fault (`link_down`, `node_isolated` or `inject_routes`) and at least one check. Netdryrun waits until a link fault is visible in BGP before judging the checks; see [scenario timing](reference/config.md#scenario-timing).

### A link fails: traffic reroutes

```yaml title="scenarios:"
- name: r1-r2 link fails
  link_down: {node: r1, interface: eth1}
  checks:
    - type: route          # r2's LAN is still reachable, now via r3
      node: r1
      prefix: 192.168.2.0/24
      protocol: bgp
    - type: ping
      node: r1
      source: 192.168.1.1
      target: 192.168.2.1
    - type: bgp_session    # and the session over the failed link is really down
      node: r1
      neighbor: 10.0.12.2
      state: down
```

Interface names are the ones inside the node (`eth1` on FRR). The [`frr-bgp` example](examples.md#frr-bgp) runs this scenario and also checks that the best path now goes through r3.

**Tested:** passes on `frr-bgp`: `PASSED: 5 passed, 0 failed (5 checks)`, with the session over the failed link in `state is active`.

### A node is isolated: what depended on it goes away cleanly

```yaml title="scenarios:"
- name: r2 isolated
  node_isolated: r2      # every lab link of r2 goes down
  checks:
    - type: route          # r2's LAN is withdrawn, not left behind
      node: r1
      prefix: 192.168.2.0/24
      present: false
    - type: route          # r3's LAN still reaches r1 directly
      node: r1
      prefix: 192.168.3.0/24
      protocol: bgp
```

**Tested:** passes on `frr-bgp`: `PASSED: 4 passed, 0 failed (4 checks)`.

### A peer sends prefixes it doesn't own

The import filter, exercised: r2 announces someone else's prefix and a more-specific of space it shouldn't send, with an AS path that makes them look learned from AS 65400. A correct import filter on r1 rejects them.

```yaml title="scenarios:"
- name: r2 announces what it does not own
  inject_routes: {node: r2, prefixes: [8.8.8.0/24, 192.168.3.0/25], as_path: [65400]}
  checks:
    - type: route          # the hijacked prefix doesn't reach r1
      node: r1
      prefix: 8.8.8.0/24
      protocol: bgp
      present: false
    - type: route          # nor the more-specific of r3's LAN
      node: r1
      prefix: 192.168.3.0/25
      protocol: bgp
      present: false
    - type: bgp_prefixes   # r1 still accepts only r2's own prefixes
      node: r1
      neighbor: 10.0.12.2
      max: 10
```

The bundled `frr-bgp` routers accept everything (`route-map ALLOW-ALL`), so this scenario fails there: that is the finding it exists for.

**Tested:** passes on `frr-bgp` with an import filter on r1 that accepts only the two LANs (`ip prefix-list LANS` permitting `192.168.2.0/24` and `192.168.3.0/24`, matched in a route-map applied `in` on **both** neighbors, because r3 passes r2's routes on); fails on the bundled lab, exit 1:

```text
  [FAIL] [r2 announces what it does not own] r1: route 8.8.8.0/24 via bgp is absent -- unexpectedly present via bgp (0.5s)
  [FAIL] [r2 announces what it does not own] r1: route 192.168.3.0/25 via bgp is absent -- unexpectedly present via bgp (0.5s)
```

The prefix ceiling passed in both runs: two extra prefixes stay well under a `max` with room for growth. The checks that name the prefixes are what caught it.

### A customer exceeds its max-prefix

The same as [max-prefix holds](#max-prefix-holds-when-a-neighbor-floods-you), seen from what must keep working: the customer's session closes, and the rest of the network carries on. The config under test has `neighbor 10.0.13.2 maximum-prefix 10 restart 1` on r1.

```yaml title="scenarios:"
- name: customer r3 floods r1
  inject_routes: {node: r3, count: 200, from: 10.200.0.0/24}
  checks:
    - type: bgp_session    # r1's limit on r3 tripped
      node: r1
      neighbor: 10.0.13.2
      state: down
    - type: bgp_session    # the other session is untouched
      node: r1
      neighbor: 10.0.12.2
    - type: ping           # and r2's LAN still answers
      node: r1
      source: 192.168.1.1
      target: 192.168.2.1
```

**Tested:** passes on `frr-bgp` with that line on r1: `PASSED: 5 passed, 0 failed (5 checks)`. Fails on the bundled lab, which has no limit, exit 1:

```text
  [FAIL] [customer r3 floods r1] r1: BGP session to 10.0.13.2 is down -- state is established (0.2s)
```

Without `restart`, it failed on recovery, as in [max-prefix holds](#max-prefix-holds-when-a-neighbor-floods-you).

`inject_routes` runs on FRR nodes only. To flood a vendor router, inject from an FRR neighbor. `count` takes 1 to 10000 prefixes.

## Next

- [Add Netdryrun to the lab you already have](guides/your-lab.md): record a baseline, then add these guards.
- [netdryrun.yml reference](reference/config.md): every key and the convergence rules.
- [Verdict corpus](corpus.md): 30 realistic BGP changes, and which checks caught each.
