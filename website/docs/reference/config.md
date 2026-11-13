---
title: netdryrun.yml reference
description: Reference for netdryrun.yml. Top-level keys, every check type and key (bgp_session, bgp_prefixes, route, bgp_route, ping), convergence semantics, drivers and protocol names.
---

# netdryrun.yml reference

`netdryrun.yml` describes one lab and the behavior you expect from it. Commands accept either the file or the folder that contains it (`netdryrun run network/` reads `network/netdryrun.yml`).

```yaml title="netdryrun.yml"
lab: topology.clab.yml
timeout: 90
nodes:
  r1:
    driver: frr
checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
  - type: route
    node: r1
    prefix: 0.0.0.0/0
    protocol: bgp
    present: false
```

Validation is strict, and every problem is an error (exit code `2`) before anything is deployed. Run `netdryrun validate` to check a file without starting a lab. From 0.3.1:

- **Unknown keys are errors at every level**: the top level, `nodes.<node>`, checks, scenarios, `link_down`, `node_isolated` and `inject_routes`. A misspelled key gets a suggestion: `unknown keys ['presnt'] for type route; did you mean 'present'?`. Before 0.3.1, a misspelled key at the top level, under `nodes` or inside a fault was ignored, so a misspelled block of checks never ran (keys inside a check or a scenario were already refused).
- **Duplicate keys are errors**, at any depth: `duplicate key 'present' (first defined on line 12)`. Plain YAML keeps the last one silently. The topology file is read the same way. One YAML merge key per mapping (`<<: *anchor`, or `<<: [*a, *b]`) is allowed, and a key written next to it overrides the merged one; from 0.4.1 two `<<` keys in one mapping, or merge sources that share a key, are errors, since YAML keeps one of them without a word and a guard could disappear. A key written explicitly replaces a merged map or list as a whole (the merge is shallow).
- **Malformed YAML** is reported on one line, with its position: `netdryrun.yml: not valid YAML at line 7, column 3: ...`.
- **Booleans must be real booleans**: `present` and `active` take unquoted `true` or `false`. A quoted `"false"`, `0`, `null` or an empty value is refused instead of being read as something else.
- **Values come from fixed lists** where the drivers only understand certain values: `type`, `state`, `afi`, `protocol`, `expect` and `nodes.<node>.driver`. A near miss gets a suggestion (`afi: ipv4` → `did you mean 'ipv4-unicast'?`).
- **Numbers are range-checked**: see the tables below. Required keys missing, IP addresses that don't parse, and keys that make no sense together (`min_replies` with `expect: failure`, `hold` on a check where it has no effect) are errors too.

## Top-level keys

| Key | Required | Default | Meaning |
|---|---|---|---|
| `lab` | yes | | Path to the containerlab topology file, relative to `netdryrun.yml`. The topology must have a `name`. |
| `timeout` | no | `120` | Seconds a check may wait (see [convergence semantics](#convergence-semantics)). A positive number, at most `86400`. Each check can override it. |
| `checks` | yes | | List of checks. At least one is required. |
| `nodes` | no | | A mapping of node name to settings. Each node accepts only `driver`, `setup` and `peers`. |
| `nodes.<node>.driver` | no | detected | Force the driver for a node: `frr`, `srlinux`, `eos`, `sonic`, `junos` (Juniper cJunosEvolved, beta), `nxos` (Cisco NX-OS, Nexus 9000v, beta) or `routeros` (MikroTik RouterOS 7, CHR, beta). See [drivers](#drivers). |
| `nodes.<node>.setup` | no | | Shell commands run inside the node after deploy, before any check. Each is retried every 5 s until it succeeds (the NOS may still be booting), within a shared 300 s budget. For NOSes that are configured after boot, such as SONiC. The only step with internet access: Docker's management default route is deleted right after it (see [the management network](#the-management-network)). |
| `nodes.<node>.peers` | no | | Per-neighbor settings, keyed by the neighbor's address (`<vrf>/<address>` outside the default VRF). The only setting is `eor: not_sent`, for a peer that never sends End-of-RIB: the convergence gate then doesn't wait when its End-of-RIB can't be read (it still waits for the session, stable prefix counts, and an End-of-RIB the node reports pending). The address is written without an IPv6 scope. A session that does report End-of-RIB still uses it. A peer the node has no BGP session with is an error at run time. See [convergence semantics](#convergence-semantics). |
| `scenarios` | no | | A non-empty list of [failure scenarios](#failure-scenarios). |

No other top-level key is accepted.

## Keys every check accepts

| Key | Default | Meaning |
|---|---|---|
| `type` | required | `bgp_session`, `bgp_prefixes`, `route`, `bgp_route` or `ping` |
| `node` | required | Node name from the topology (for example `r1`) |
| `name` | generated | Label used in reports. The default describes the check, for example `r1: BGP session to 10.0.12.2 is established`. |
| `timeout` | top-level `timeout` | Seconds this check may wait to pass. A positive number, at most `86400`. |
| `hold` | `--hold` (10) | Seconds a [post-convergence check](#convergence-semantics) must hold. A positive number, at most `86400`. Only allowed on post-convergence checks: on any other check it would have no effect, so it is an error. |
| `vrf` | `default` | VRF (FRR, SONiC, Arista EOS) or network-instance (SR Linux) to look in. Letters, digits and `. _ : -`, at most 64 characters: the name goes into the device's CLI command, so anything else is refused (0.3.1 and later; 0.3.0 did not check it). `vrf: all` is refused: name one VRF per check. A VRF that doesn't exist on the node is an error on every driver, never "no routes" (see [drivers](#drivers)). |

Each check type accepts only these keys and the ones in its own table.

IP addresses and prefixes are normalized, so `2001:db8:0::1` in YAML matches `2001:db8::1` on the device. Prefixes with host bits set are reduced to the network (`10.0.0.1/24` becomes `10.0.0.0/24`).

## Check types

### bgp_session

A BGP session reaches a state.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `neighbor` | yes | | Neighbor IP address as configured on `node`. A link-local address that several sessions share (`fe80::1` on two interfaces) is ambiguous: the check is not evaluated, so use a global address |
| `state` | no | `established` | One of `idle`, `connect`, `active`, `opensent`, `openconfirm`, `established`, or `down` (any state except established). Case-insensitive |

The check fails if the neighbor is not configured. A `state` other than `established` makes it a post-convergence check.

```yaml
- type: bgp_session
  node: r1
  neighbor: 10.0.12.2
```

### bgp_prefixes

The number of prefixes accepted from a neighbor is within a range, and (with `only`) every one of them is in a set you list. Accepted means received minus rejected by import policy.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `neighbor` | yes | | Neighbor IP address (a link-local address several sessions share is ambiguous, as for `bgp_session`) |
| `min` | one of `min`, `max`, `exact`, `only` | | Lower bound, inclusive |
| `max` | one of `min`, `max`, `exact`, `only` | | Upper bound, inclusive |
| `exact` | one of `min`, `max`, `exact`, `only` | | Exact count |
| `only` | one of `min`, `max`, `exact`, `only` | | 0.4.1: the prefixes this neighbor may send, a list of prefixes in the check's `afi` (`ipv4-unicast` or `ipv6-unicast`). Any other accepted prefix fails the check, even when the count is in range, and so does one that replaces a listed prefix. `[]` means nothing may arrive. Each entry must be a network address: `10.1.1.77/24` is refused (it would widen the list to `10.1.1.0/24`). FRR and SONiC only: on other drivers it is refused before the lab deploys (exit code `2`). `netdryrun record` writes it on every eBGP neighbor |
| `afi` | no | `ipv4-unicast` | Address family: exactly one of `ipv4-unicast`, `ipv6-unicast` or `evpn` (case-insensitive). `evpn` is supported on FRR and SONiC only, not on SR Linux, Arista EOS, Juniper (beta), Cisco NX-OS (beta) or MikroTik RouterOS (beta); `ipv6-unicast` is refused on MikroTik RouterOS (beta), whose driver reads IPv4 only. Required (from 0.4.1) when the neighbor is an IPv6 address: the default is a family such a session usually doesn't carry |

Rules:

- At least one of `min`, `max`, `exact` or `only` is required.
- Without `afi` the check counts IPv4 unicast only, also on an IPv4 session that carries IPv6 or EVPN as well, and the check's name doesn't say the family. Write one check per family the session carries.
- **A family the session doesn't carry** (0.4.1): `exact: 0` passes, saying so ("0 ipv6-unicast prefixes (the session doesn't carry ipv6-unicast)"): nothing of that family can arrive, and the check fails the day the family is added and sends a prefix. Every other bound (`min`, `max`, `only`, `exact` above 0) fails with "the session to X doesn't carry ipv6-unicast": a count of 0 that was never counted is not read as one. Before 0.4.1 such a family counted 0, so `max: 3` passed while an IPv6 neighbor sent 500 IPv6 prefixes on the default `ipv4-unicast`.
- `exact` cannot be combined with `min` or `max`.
- `min` must not be greater than `max`.
- All three are non-negative integers.
- `min: 0` on its own is refused: it always passes. Use `min: 1` or more, or add `max`.
- Any other `afi` is refused (from 0.3.1). An address family the drivers don't report would read as 0 prefixes, which passes `max` and `exact: 0`.
- `afi: evpn` on an SR Linux or Arista EOS node is refused before the lab deploys (exit code `2`): those drivers read only the IPv4 and IPv6 unicast counts (SR Linux has no received-routes counter for EVPN), so an EVPN count would always read 0. SR Linux refuses it from 0.3.1; before, the count read 0 and passed `max`.
- The session must be `established`. Counters reset to 0 when a session drops, so a count from a down session would satisfy `max` by accident; Netdryrun fails the check instead.
- If the session is established but the address family reports nothing, the count is 0.
- **Add-path** (from 0.4.2): when a neighbor may send several paths per prefix (BGP add-path), the device's counter counts paths, not prefixes. FRR and SONiC then count the distinct prefixes in `show bgp ... neighbors N routes json`, and SR Linux in its local RIB (`bgp-rib`); a listing that doesn't add up to the counter is an error, never a count. Arista EOS has no such listing read yet: its `prefixAccepted` P becomes the range 1 to P (as an FRR EVPN count does), judged only where the whole range agrees: `max` passes when P is within it, `max: 0` and `exact: 0` fail, and `min` above P fails, but P above `max`, or a `min` from 2 to P, gets no verdict (not ready), not a fail. A session that may send add-path is one whose add-path state says so or doesn't say. In 0.4.1 and earlier, `min` and `exact` could pass on fewer prefixes ([advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.2-addpath-prefix-count/README.md)).
- **Graceful restart** (FRR and SONiC, from 0.4.2): while a neighbor that kept its forwarding state across a restart (the F-bit FRR prints as `gracefulRestartInfo.<afi>.fBit`) hasn't sent End-of-RIB for the family, bgpd keeps its old paths marked stale and counts them as accepted. Such a count isn't settled: no bound is judged on it (the check is not ready and samples again), and `record` leaves it out. Once End-of-RIB arrives the count is the peer's. A neighbor with the F-bit clear, or without graceful restart, is counted as before. In 0.4.1 and earlier, `min` could pass on stale paths the peer no longer sends ([advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.2-addpath-prefix-count/README.md)).
- A check with `max`, `exact` or `only` is a post-convergence check. A check with only `min` is a positive check.
- With `only`, the prefixes come from the neighbor's accepted routes (FRR: `show bgp <afi> unicast neighbors <address> routes json`). A count above 0 with no route listed is no answer (the check fails as not ready), never "nothing new".

```yaml
- type: bgp_prefixes
  node: r1
  neighbor: 10.0.12.2
  min: 1
  max: 10          # guards against a route leak flooding r1
```

A customer that may announce only its own block. A range alone (`min: 1`, `max: 3`) passes when a broken inbound filter lets one prefix it doesn't own through; `only` fails it ([`examples/frr-customer-leak`](https://github.com/netdryrun/Netdryrun/tree/main/examples/frr-customer-leak)):

```yaml
- type: bgp_prefixes
  node: edge
  neighbor: 10.0.1.2
  min: 1
  max: 3
  only: [10.10.0.0/24]   # anything else from the customer fails
```

### route

A route is present in (or absent from) the routing table.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `prefix` | yes | | IPv4 or IPv6 prefix with its length: `0.0.0.0/0` for a default route, `192.0.2.1/32` for one host. From 0.4.1 a prefix without a length is a config error (it used to mean a single host, so `0.0.0.0` checked 0.0.0.0/32) |
| `present` | no | `true` | `false` means the route must be absent. Unquoted `true` or `false` only |
| `protocol` | no | any | Only count routes from this protocol: one of the names in [protocol names](#protocol-names). Case-insensitive |
| `vrf` | no | `default` | VRF or network-instance |
| `active` | no | `true` | With `present: true`: `false` also accepts a route that is in the table but not selected (for example a BGP default losing to a local one). Unquoted `true` or `false` only; not allowed with `present: false` |

- **Present** means an *active* route matches: selected and installed on FRR, with none of zebra's failure flags set (`failed`, `offloadFailed`, `queued`; and `trapped` on a BGP or static route), `active` on SR Linux. On SONiC a BGP or static route is active only with `offloaded: true`, since 0.4.1: a SONiC build that never reports offload fails `route` checks on such routes. The shipped sonic-vs build printed `offloaded` even with orchagent stopped, so it isn't proof that the ASIC programmed the route: pair such checks with a `ping`. A route whose install is still queued is a transient state: it fails a positive check only when the sample lands on it, and it still counts as present for `present: false`.
- **Absent** means no matching route at all, active or not. A BGP path that was received from a neighbor still counts as present, valid or not, selected or not (for example a leaked default losing to a local one, or a path BGP dampening suppressed), so `present: false` fails. A path FRR or SONiC still lists after the neighbor withdrew it (a dampening history entry, or a path being removed) is no path, from 0.4.2: in 0.3.1 to 0.4.1 it read as present and not selected (RT-0070). This is how the [failing example](../index.md#a-failing-run) is caught. Every driver reads the BGP table for this as well as the routing table; there, only paths received from a neighbor count, not the router's own (network statements, redistribution, SR Linux's static and interface routes).
- **Known limit (Arista EOS, a known false pass (found offline, published conservatively), accepted for 0.4.1; RT-0056, RT-0063):** EOS's `show ip route` lists only the route it selected for a prefix, and the driver reads routes that weren't selected from the BGP table only. So a static, OSPF or IS-IS route that is present but loses to another protocol (a floating static behind a BGP default, an OSPF default behind a local static) isn't seen, and `route` with that `protocol` and `present: false` passes. FRR, SONiC and NX-OS list every candidate route and fail the same check. **Mitigation:** on EOS, don't rely on `present: false` with a protocol other than `bgp`: check the route where it comes from (for OSPF, on the neighbor that advertises it, if that isn't EOS), and add a positive `route` check that the route EOS selected has the protocol you expect. **Fix:** planned for 0.4.3.
- `protocol` must be a name the drivers report. `ebgp` and `ibgp` are refused: drivers report both as `bgp`. A name outside the list would match nothing and silently pass `present: false`.
- `present: false` makes it a post-convergence check.
- A route that is selected and installed is present even when its BGP path carries LLGR_STALE (65535:6, a long-lived
  graceful-restart stale path): `route` reads the routing table. `bgp_route` refuses such a path as not settled (0.4.1).
  To check that a route is not only installed but freshly learned, use `bgp_route`.

```yaml
- type: route
  node: r1
  prefix: 192.168.3.0/24
  protocol: bgp
```

### bgp_route

Attributes of the BGP **best path** for a prefix: communities, AS path, local preference, MED, next hop. Many real policy bugs live here: a route that is still present but lost its community, got the wrong local preference, or now goes the long way. `route` reads the routing table; `bgp_route` reads the BGP table.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `prefix` | yes | | IPv4 or IPv6 prefix with its length, matched exactly (a prefix without a length is a config error from 0.4.1) |
| `communities` | no | | The best path must carry **all** of these. Standard (`'65000:100'`), large (`'65000:1:2'`) or well-known names (`no-export`, `no-advertise`, `no-peer`, `blackhole`, `graceful-shutdown`, `accept-own`, `llgr-stale`, `no-llgr`, `no-export-subconfed`, and from 0.4.1 `internet` (0:0), `accept-own-nexthop`, `route-filter-translated-v4`, `route-filter-v4`, `route-filter-translated-v6`, `route-filter-v6`) |
| `without_communities` | no | | The best path must carry **none** of these. Same forms as `communities`. From 0.4.1 a path carrying a community the device prints by a name Netdryrun can't turn into a number (a name it doesn't know) fails the check: it could be one of these. On an FRR or SONiC node with any `bgp community alias`, a `communities` or `without_communities` check fails whenever the path carries any community: an alias can look like any community (a number, leading zeros, a well-known name), so no printed community can be trusted there. 0.4.0 and earlier kept such names as text, so FRR's `internet`, `accept-own-nexthop` and `route-filter-translated-v4` never matched `0:0`, `65535:8` and `65535:2`, and the check passed. Refused before deploying on Juniper (beta), whose output leaves the communities out of a path with none, so a missing list can't be told from one it didn't print (0.4.1) |
| `as_path` | no | | Exact AS path, ASNs separated by spaces: `"65002 65003"`. `""` is the empty path of a locally originated route. AS sets are written `{65004,65005}` |
| `as_path_regex` | no | | Python regular expression searched in the AS path string, for example `"^65002 "` (learned from 65002) or `"(^| )65666( |$)"` (passes through 65666). It runs with no time limit, so avoid nested repeats such as `(\d+ ?)+$` that can backtrack for minutes. A best path whose AS path the device didn't print is an error for `as_path` and `as_path_regex`, never the empty path that `^$` matches (0.4.1). A pattern that matches every learned AS path (a stray `|`, `.*`, `.+`, `\d`) is refused: it is tried on four sample paths, and one that matches all of them would assert nothing more than "learned from a peer" (0.4.1; `^$` stays valid). The probe catches the common accidents, not every pattern that matches broadly: the check asserts exactly what the pattern says, so write one that names the AS numbers you mean |
| `local_pref` | no | | Exact local preference |
| `med` | no | | Exact MED. A path with no MED attribute fails the check, even `med: 0`: with `bgp bestpath med missing-as-worst` a missing MED is the worst, not 0. On Arista EOS, `med: 0` is refused before the lab boots (exit `2`): cEOS prints MED 0 for a path received with no MED, so the two can't be told apart; a non-zero MED is checked as usual |
| `next_hop` | no | | Exact next hop address. A link-local address is refused: devices report it without its interface, and two sessions can share one, so the check couldn't say which path it tests |
| `present` | no | `true` | `false` means no path at all for the prefix in the BGP table, best or not, valid or not, the node's own included (see below). Unquoted `true` or `false` only |
| `vrf` | no | `default` | VRF or network-instance |

Rules:

- Without attribute keys, the check passes when a best path exists. The router's own routes that SR Linux lists in its BGP RIB (static and interface routes, marked best whether they are advertised or not) are not BGP paths: from 0.4.1 a check whose only path is one of them fails (0.4.0 passed it; FRR, which lists only BGP paths, always failed it). Check such a route on the neighbor that should receive it.
- `present: false` passes only when the node's BGP table holds no path for the prefix: a received path, and the node's own path where the NOS lists it (FRR, SONiC, Arista EOS and NX-OS list their own paths there; from 0.4.1, RouterOS's own prefix advertised to a peer, one `bgp-output` row per peer, counts too: 0.4.0 passed it).
- **Known limit (SR Linux and Juniper, accepted for 0.4.1):** `bgp_route present: false` doesn't see a prefix the node itself originates and exports. SR Linux lists its own static and interface routes in the BGP table whether an export policy advertises them or not, and Junos lists none of its own routes there even when exported, so neither can show from the BGP table whether the node advertises the prefix. The check reads received paths there, and its pass says so ("a prefix this node originates itself isn't checked"). **Mitigation:** put the `present: false` guard on the neighbor that would receive the route; that catches it on every driver. **Fix:** planned for 0.4.3: read what the node advertises (its adj-rib-out).
- **Known limit (SR Linux EVPN, a known false pass (found offline, published conservatively), accepted for 0.4.1; RT-0058):** in an ip-vrf without its own `protocols bgp` (the usual EVPN layer-3 design), `bgp_route` with that `vrf` reads the network-instance's own BGP RIB, which is empty: EVPN type-5 routes imported into it are held in the default network-instance's EVPN RIB, which the driver doesn't read. So `bgp_route` with `present: false` passes there while the route is imported and installed. **Mitigation:** use a `route` check with the same `vrf`, `protocol: bgp` and `present: false`: it reads the routing table, where the installed route (`bgp-evpn`) matches `bgp`. **Fix:** planned for 0.4.3.
- **Quote communities.** YAML reads some unquoted values as numbers (`65000:10` is a base-60 number to YAML 1.1), so an unquoted community that YAML turns into a number is a config error.
- A community can't be in both `communities` and `without_communities`.
- `present: false` can't be combined with attribute keys. To forbid a community on the best path, use `without_communities`.
- The check fails if there is no path, or no best path (for example when the next hop is unreachable). The failure detail shows what the best path actually carries.
- **Local preference** is the effective value: a path without a LOCAL_PREF attribute (eBGP-learned or local) gets the device's default (FRR and SONiC: `bgp default local-preference`; SR Linux: the neighbor's `local-preference`; Arista EOS reports it directly). The exception is a locally originated path on Arista EOS, which reports no local preference; asserting `local_pref` on it fails with "not set".
- **Next hop** is the address the device reports. For an IPv6 path FRR may list only the link-local next hop.
- `present: false`, and any attribute key (`communities`, `without_communities`, `as_path`, `as_path_regex`, `local_pref`, `med`, `next_hop`), make it a post-convergence check. The best path can change when a slower session comes up, so an attribute check could pass on a temporary best path before the real one arrives; it is judged only after every BGP session on the node is up and the settle delay, and must hold (0.3.1 and later; 0.3.0 judged attribute checks other than `without_communities` on 2 early samples). A `bgp_route` with no attribute keys (the best path exists) is a positive check.

```yaml
- type: bgp_route         # customer routes are tagged and preferred
  node: r1
  prefix: 192.168.20.0/24
  communities: ["65000:100", no-export]
  local_pref: 200
  as_path: "65020"

- type: bgp_route         # the internal tag must never reach the peer
  node: peer1
  prefix: 192.168.20.0/24
  without_communities: ["65000:666"]
```

### ping

Reachability from a node.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `target` | yes | | Destination IP address. From 0.4.1 it must be a host the ping leaves the node for: an unspecified, loopback, multicast or limited-broadcast address, the `source` itself, or an IPv4-mapped IPv6 address (`::ffff:10.0.0.1`: write the IPv4 address) is refused before the lab deploys, and at run time a target the node answers itself fails the check (see below) |
| `source` | no | | Source IP address (passed as `ping -I`) |
| `expect` | no | `success` | `success` or `failure` |
| `count` | no | `3` | Packets to send. An integer from 1 to 1000. |
| `min_replies` | no | `count - 1`, at least 1 | Replies needed for `expect: success`: an integer from 1 to `count`. One lost packet is tolerated by default (first-packet ARP). Not allowed with `expect: failure` |
| `vrf` | no | `default` | Runs in the VRF (`ip vrf exec` on FRR) or network-instance namespace (`srbase-<name>` on SR Linux) |

- `expect: failure` passes only with 0 replies, and is a post-convergence check.
- `expect: failure` also passes when ping reports the destination unreachable without sending anything: "Network unreachable" (or "Network is unreachable"), "No route to host" or "Destination unreachable" (0.3.1 and later). With no route at all, ping prints one of these and no statistics.
- If ping did not run at all for any other reason (bad source address, missing VRF), the check fails with an error. It never counts as a successful "failure".
- **Never over the management network** (0.4.1): a target or source in it is a run error, and a ping whose node has a
  route over its management interface ends the run (see [the management network](#the-management-network)). `source`
  must be one of the node's own addresses in the check's VRF, or the check is not evaluated.
- **A target the node answers itself fails the check** (0.4.1): one of the node's own addresses in the check's VRF, IPv4
  or IPv6 (primary, secondary and link-local; on Arista EOS also `ip address virtual` and its secondaries), the broadcast
  address of one of its IPv4 subnets (shorter than /31), or the IPv6 subnet-router anycast address of one of its IPv6
  prefixes (the prefix with all host bits zero, shorter than /127; RFC 4291 2.6.1). The anycast refusal applies on every
  driver, also on a NOS that doesn't answer that address: it fails closed. Each driver reads the node's addresses with
  its own command; output it can't read is retried, then not evaluated, never "not own". A target of an address family
  the driver can't read the node's addresses for is not evaluated either.
- Not read as own: VRRP, VARP (`ip virtual-router address`) and HSRP virtual addresses (on every driver), IPv6
  anycast addresses (NX-OS `ipv6 address ... anycast`) and anycast gateways other than EOS `ip address virtual`. Don't ping a first-hop redundancy address from a node that may hold it.
- **The VRF device's own address (FRR and SONiC, from 0.4.2; RT-0053):** in a VRF, the node's own addresses are those of the interfaces enslaved to the VRF and of the VRF device itself (`ip -j addr show vrf <vrf>` and `ip -j addr show dev <vrf>`), so a `ping` to a VRF loopback on the VRF device (`ip addr add 10.9.9.9/32 dev red`) is refused as the node's own. In 0.4.1 and earlier it was answered by the node and passed (case 3 of the 0.4.1 advisory).

```yaml
- type: ping
  node: r1
  source: 192.168.1.1
  target: 192.168.3.1
```

## Failure scenarios

`scenarios:` runs extra checks while something is wrong, then puts it right. Use it to prove the network survives a failure, for example that traffic reroutes when an uplink dies, or that your max-prefix limit and import filters hold when a neighbor misbehaves.

```yaml
scenarios:
  - name: r1-r2 link fails
    link_down: {node: r1, interface: eth1}   # or a list of links
    checks:
      - {type: route, node: r1, prefix: 192.168.2.0/24, protocol: bgp}   # rerouted via r3
      - {type: ping, node: r1, source: 192.168.1.1, target: 192.168.2.1}
      - {type: bgp_session, node: r1, neighbor: 10.0.12.2, state: down}

  - node_isolated: r2          # all of r2's lab links down
    checks:
      - {type: route, node: r1, prefix: 192.168.2.0/24, present: false}

  - name: customer floods us
    inject_routes: {node: ce1, count: 200, from: 10.100.16.0/24}   # ce1 announces 200 extra /24s
    checks:
      - {type: bgp_prefixes, node: up1, neighbor: 10.0.2.1, max: 51}   # the max-prefix limit holds

  - name: peer announces what it does not own
    inject_routes: {node: peer1, prefixes: [10.100.0.0/25, 8.8.8.0/24], as_path: [65400]}
    checks:
      - {type: bgp_prefixes, node: pe2, neighbor: 10.0.4.2, max: 1}   # the import filter holds
      - {type: route, node: ce1, prefix: 10.100.0.0/25, protocol: bgp, present: false}
```

| Key | Meaning |
|---|---|
| `name` | Label shown before each check (default: generated from the faults) |
| `link_down` | `{node, interface}` or a list of them; no other keys. Interface names as seen inside the node (for example `eth1` on FRR): a Linux interface name of at most 15 letters, digits and `. _ @ -` (checked from 0.3.1). From 0.4.1 the interface must be an endpoint of a link in the topology on that node, in the topology's own spelling: the management `eth0`, `lo` or any other name is refused before the lab deploys (exit code `2`), and after the fault the interface must be administratively down, or the scenario is an error. SR Linux links and every VM kind (RouterOS, NX-OS, Junos and other vrnetlab nodes) can't be failed yet; fail the FRR or Linux side instead |
| `node_isolated` | A node name, `{node}`, or a list of them: every lab link of that node goes down |
| `inject_routes` | `{node, prefixes}` or `{node, count}` (or a list of them): the node announces extra routes. 0.3.1 and later. See below |
| `checks` | Same check types and keys as the top level. See [scenario timing](#scenario-timing) |

A scenario needs at least one fault and at least one check, and accepts no other keys. Scenarios run after the main checks, one at a time. Links and injected routes are always restored afterwards, even if a check fails, and Netdryrun waits for the network to settle before the next scenario. If the network does not recover, the checks that passed before the scenario are reported as failed `[after <scenario>] recovers: ...` checks, and later scenarios are skipped.

### Scenario timing

A scenario's positive checks ("the route is still there", "ping still works") are already true before the network notices the failure, so Netdryrun makes sure they are never judged on the state from before the fault (0.3.1 and later):

1. Before taking links down, it notes the established BGP sessions that run over them, on both ends of each link (looking through bridges), in the default VRF and the VRFs the scenario's checks use. If that BGP state, or the addresses of the downed interfaces, can't be read, the run stops with exit code `2` naming the node, before any link goes down: "couldn't read it" is never taken for "there are none". A node no driver can read (a Linux host) and a VRF the node doesn't have have no sessions to note.
2. After applying the faults, it waits until every one of those sessions is down **on both ends**: proof that the network saw the fault. The wait is capped at the largest `timeout` of the scenario's checks. If the fault still isn't visible by then, the run stops with exit code `2` and "the fault did not take effect", never a verdict. Without BFD, BGP can take its hold time (up to 180 s) to notice a failure: raise the checks' `timeout`, or lower the hold timers in the lab.
3. It waits the settle delay (`--settle`), so withdrawals propagate beyond the adjacent routers.
4. Positive checks must pass on 2 consecutive samples **and** keep passing for the hold window (`--hold`; a positive check can't set its own `hold`): a redundancy claim is about the whole failure, not one instant. A check that passes at first and then fails within the window fails.
5. Post-convergence checks then wait for the same [BGP gate](#convergence-semantics) as at the top level: every BGP session on their node up, with unchanged prefix counts on 2 consecutive samples, capped at their `timeout`. Sessions over the downed links don't count (the fault took them down), nor do sessions a `bgp_session` check in the scenario or at the top level expects in another state. If another session on the node stays down, the checks fail as **not evaluated**; a session the fault takes down indirectly (for example iBGP between loopbacks whose only path was the downed link) needs a `bgp_session` check with `state: down` in the scenario. Then the checks must hold, as everywhere else. 0.3.1 and later.

When the state was read and no BGP session runs over the downed links (static routing, a link without BGP, iBGP between loopbacks over an IGP), step 2 has nothing to observe; steps 3 to 5 still apply, so give such scenarios a `--settle` that covers the failure detection time. `inject_routes` faults have no step 2: Netdryrun instead waits until the injected paths are in the node's own BGP table (routes it originates with the injection's AS path, not the prefixes learned from a neighbor). That doesn't show they reached the node under test, and neither does the BGP gate in step 5: it waits until the prefix counts on a post-convergence check's node stop changing, and counts that never changed are stable at once. So, from 0.4.1, Netdryrun first waits, before the scenario's checks, until the injecting node advertises every injected route to each BGP peer established in its family: the injected path itself, a route the node originates with the injection's AS path, not the same prefix from a path it learned (the case a hijack test sets up) or another of its own (read from its adj-rib-out: `show bgp <afi> unicast neighbors <peer> advertised-routes detail json`, its routes after outbound policy, read as strictly as `verify` reads them), for at most twice the longest advertisement interval plus `--settle`. After the checks, while the routes are still in, it applies one rule. A peer counts as reached only if all of these hold: its session was established in the prefix's family when the routes went in; it was advertised every injected prefix of that family before the checks ran; it is still established and still advertised them; and its session never reset in between (bgpd's `connectionsDropped` didn't change and could be read, its uptime is at least the time since the routes went in, and it isn't a dynamic `bgp listen range` peer, which FRR recreates on reconnect). Every other peer seen in that family is quiet: an outbound filter towards it, a session that went down, reset or came up while the checks ran, or routes advertised too late. A peer the node sends several paths per prefix (add-path) is quiet too: FRR's listing then shows the node's paths with their per-family IDs, including one an outbound filter denied to that peer, so it can't show which path the peer got. FRR may print those IDs on every path when any neighbor in the family has add-path send enabled, so on such a node every inject scenario reads inconclusive. A prefix a peer already had an advertised entry for before the injection is never read as delivered to that peer either: FRR shows the node's current path under an existing entry before any UPDATE leaves, so a hijack test of a prefix the injecting node already advertises reads inconclusive. And an injected prefix the node already originates itself with the AS path the injection would carry (a redistributed connected or static route, an aggregate, a `network` statement) is refused before the scenario runs, since its route couldn't be told from the injected one: inject a prefix it doesn't originate, or give the injection an `as_path`. A family no established session carried when the routes went in sent nothing. When any peer is quiet, every check in the scenario that passed is reported not passed, naming the peer and the prefixes ("inconclusive: the injected routes on r2 did not all reach its BGP peers: 10.0.12.1 was not sent 100.64.0.0/24 ..."; "the injected routes never left r2: no established ipv6 BGP session there carries ..."). Every passed check, not only `present: false` or `max`: a check that the attack had no effect (the legitimate best path stays, the session stays up, a ping still works, `min` holds) passes just as well on routes that never arrived. A check that failed anyway stays a plain failure. The run is then inconclusive (exit `3`) unless another check failed for real. Sessions or advertised routes that can't be read are inconclusive too. A prefix-limit reset doesn't count as delivery: another node's injection, or a link failure that reroutes traffic, can trip the limit just as well. So a scenario whose injected routes trip a `maximum-prefix` limit reads inconclusive as a whole: the session the limit tears down was one the routes had to reach. So test a prefix limit in a separate scenario, with routes that reach the peer, or accept that scenario's inconclusive verdict; keep other checks out of it, so the inconclusive doesn't cover them. To test a node beside one the injecting node filters on purpose, inject on a node whose BGP peers all get the routes. A filter further along the path is what such a scenario tests: the injecting node sent the routes, so it is judged as usual. A peer with a long advertisement interval (for example eBGP with a 30-second `advertisement-interval`) can also hold the routes back for longer than 2 samples 3 seconds apart, so they can still arrive after the gate: raise `--settle` above the advertisement interval for such labs.

### Injecting routes

New in 0.3.1: Netdryrun 0.3.0 rejects the key as unknown.

`inject_routes` makes a node announce routes it normally doesn't, so you can test what the rest of the network does with them: a customer leaking more-specifics, a peer announcing someone else's prefix, a flood that should trip a max-prefix limit.

| Key | Required | Meaning |
|---|---|---|
| `node` | yes | The node that announces the routes. It must be an FRR node with `router bgp` in the default VRF |
| `prefixes` | one of | A prefix or list of prefixes, IPv4 or IPv6, each with its length |
| `count` | one of | Announce this many consecutive prefixes (1 to 10000), starting at `from` |
| `from` | no | First prefix for `count`, with its length, which is used for all of them. Default `100.64.0.0/24` |
| `as_path` | no | List of AS numbers prepended to the injected routes, so they look learned from those networks |

On the node, Netdryrun adds a blackhole static route and a BGP `network` statement per prefix (with `as_path`, through a route-map named `NDR-INJECT`). It applies them with `vtysh -f` and waits until every prefix is in the node's own BGP table before running the scenario's checks (whose post-convergence checks then wait for the BGP gate on their own node; see [scenario timing](#scenario-timing)). Afterwards it removes exactly what it added and waits until the prefixes are gone. What the node's neighbors do with the routes is up to the policy under test: an outbound filter on the node itself can still stop them.

Limits: only FRR nodes are supported. Any other node is refused before the lab deploys; inject the routes from an FRR neighbor instead. A prefix that is already a `network` statement or a static route on the node is refused, because removing it afterwards would delete real config. IPv6 prefixes need the BGP sessions to carry IPv6 unicast.

## Convergence semantics

Networks need time to converge, and some checks are trivially true before they do. Netdryrun splits checks into two groups.

**Positive checks** (session `established`, prefix count with only `min`, route present, a `bgp_route` best path that exists with no attribute asserted, ping expected to succeed):

- Polled every 3 seconds until they pass on **2 consecutive samples**, or until `timeout` expires.
- A single lucky sample is not enough. If the last sample passed but the streak was too short, the result says "not stable". If the check passed some samples but not consistently, the result says "flapping".

**Post-convergence checks** are the ones that would pass on a network that has not come up yet:

- routes that must be absent (`present: false` on `route` or `bgp_route`)
- best-path attributes (`bgp_route` with any of `communities`, `without_communities`, `as_path`, `as_path_regex`, `local_pref`, `med`, `next_hop`): a best path seen while a slower session is still coming up can be replaced when it arrives
- pings that must fail (`expect: failure`)
- sessions expected in a state other than `established`
- prefix counts with an upper bound (`max` or `exact`), since 0 prefixes satisfies `max: 10` while BGP is still starting, and prefix lists with `only`, since an empty list has nothing outside the allowed set

They run in this order:

1. Every positive check has finished.
2. **Every BGP session on the node is up.** Positive checks only prove convergence for the sessions and routes you happened to check, and a leak can arrive later over a session nobody checked. So for each node (and VRF) that carries a post-convergence check, Netdryrun waits until every configured BGP neighbor there is `established`, with unchanged prefix counts, on 2 consecutive samples. Neighbors that a `bgp_session` check expects in another state (for example `state: down`) don't count. The wait is capped at the largest `timeout` of that node's post-convergence checks. If a session there never comes up, those checks fail as **not evaluated**, naming the session: a down session is a finding, as everywhere else. If a session is down on purpose, add a `bgp_session` check with `state: down` for it. Prefix counts still changing at the cap don't block. A node whose BGP state can't be read is waited for up to the cap like any other. If it was never readable by then and the file says it runs BGP (as defined below), its post-convergence checks fail as **not evaluated** ("could not be read by the cap"), every sample unready: nothing showed it converged (0.4.1; earlier, such a node was not waited for). On a node with no BGP check in the file, they run with a warning ("could not be read by the cap; the check was evaluated without the BGP gate"). A ping-only node with no BGP instance at all, and a node whose positive checks never got usable state (they already waited out their timeout), are not waited for. A node that answers with **no BGP neighbors at all** is not converged: that is what a node answers before its BGP config is applied, and a leak can arrive once it is. Netdryrun keeps waiting, up to the cap. If the node still reports no neighbors then and the file says it runs BGP (a `bgp_session`, `bgp_prefixes` or `bgp_route` check on it, or a `route` check with `protocol: bgp`), its post-convergence checks fail as **not evaluated** ("reported no BGP neighbors by the cap"), every sample unready, so a leak guard can't pass on a router whose BGP config never loaded (from 0.3.2; when nothing anywhere gave usable state, the run is inconclusive). A node with no BGP check anywhere in the file may not run BGP at all: its post-convergence checks run anyway, each with a warning in its result ("reported no BGP neighbors for N s; the check was evaluated without BGP convergence"), and the verdict is unchanged. So a node that doesn't run BGP adds one `timeout` of waiting before its post-convergence checks. 0.3.1 and later.

   **From 0.4.1, the gate also waits for the rest of the lab, and for End-of-RIB.**

   - *Every other routing node.* A leak can come from two hops away, over a session on another router that is still coming up. So the gate also waits, up to the same cap (the largest `timeout` of the post-convergence checks), for every lab node with a routing driver, in the default VRF and every VRF the checks name. On those nodes nothing blocks: at the cap, a session still down, prefix counts still moving, no BGP neighbors on a node the file says runs BGP, or BGP state that can't be read is a **warning** on every post-convergence check, naming the node and the session, and the checks run. A node no driver recognises (a Linux host) and a node with no BGP that no check names are not waited for. A session a `bgp_session` check declares down is left out at both ends of its link.
   - *End-of-RIB.* An established session whose counts hold still for two samples can still be receiving its table (during a graceful restart, or over a slow link). Each driver reads whether the neighbor has sent End-of-RIB for each family. Until it has, the session is not settled; at the cap that blocks the post-convergence checks of the check's own node (as a down session does) and is a warning on any other node. A neighbor that negotiates graceful restart but never sends End-of-RIB (some route injectors) is declared with `nodes.<node>.peers.<address>.eor: not_sent`: the gate then doesn't wait when its End-of-RIB can't be read, but still waits while the neighbor reports it pending (the declaration never weakens a read). A session without graceful restart negotiated has no End-of-RIB to wait for: it is judged by stable counts, with one warning per run naming it. Keep the graceful-restart helper on (FRR's default) to have it tracked. **RouterOS 7.x never sends End-of-RIB** (it receives it; captured on 7.23), so a peer's End-of-RIB from a RouterOS node stays pending forever. When the peer is a RouterOS node in the lab that Netdryrun can place (the link on which the node has an address in the neighbor's subnet leads to that RouterOS node only, and the RouterOS node's own addresses, read through its driver, include the neighbor address), a *pending* End-of-RIB from it is handled the same way: the session is judged by stable counts, with one warning per run naming the RouterOS node. Everything else is still waited for, up to the cap: an End-of-RIB that can't be read, a RouterOS peer the topology can't place (iBGP between loopbacks, a link-local neighbor), and a RouterOS node whose driver isn't chosen.
   - *Warnings.* Each warning is in the check's result (`warnings` in the JSON report and the MCP result, a line under the check on the console, a block in the Markdown summary), and the run counts them. A warning never changes a verdict.
   - *What is still not waited for:* a route can take one advertisement interval per hop after every session is up and every End-of-RIB is in, so a leak that crosses several peers with long intervals can still arrive after the windows. Raise `--settle` above the longest interval times the number of hops. A full fix is planned for 0.4.3.
3. A settle delay (`--settle`, default 10 seconds; at least 30 seconds if the file has no positive checks, because nothing else has shown that the network converged). From 0.4, `--settle` and `--hold` stretch to the longest BGP advertisement interval any session in the lab reports, plus 2 seconds: a peer sends at most once per interval, so a route can arrive that late. **On Arista EOS the advertisement delay (`neighbor ... out-delay`) is not read yet** (fix scheduled: 0.4.3): if you configure one, raise `--settle` and `--hold` above it, or a leak sent after the windows can pass a negative check.
4. Each one must then hold for the hold window (`--hold` or the check's `hold`, default 10 seconds), sampled every 3 seconds. A violation at any sample fails the check immediately.

### The management network

Docker gives every Linux container a default route over its management interface (`default via 172.20.20.1 dev eth0`
on containerlab's `clab` network), and containerlab's built-in cEOS config adds `ip route 0.0.0.0/0 <gateway>` in VRF
default. A route there is not a lab path: a ping over it leaves the lab, Docker masquerades it, and anything the Docker
host reaches answers. Production has no such route, so from 0.4.1, after deploy, startup config and every `setup:`
command, and before the first check, Netdryrun deletes exactly that route (IPv4 and IPv6) on each Linux and SONiC node
(in the node, as root) and each cEOS node (in its config, once the startup config has loaded), then waits `--settle` once so routing can react. A default
route the lab configured itself is never touched. The report says what was removed on each node
(`environment.nodes.<node>.management_default`).

The run ends as an **error (exit 2)**, never a pass, when: any other route uses a management interface (a static route
via the management gateway, a default with a `proto`, a multipath default with a management leg); routes can't be read
or changed (for a Linux image without `ip`, Netdryrun reads and changes its routes from a pinned alpine helper container that joins only the node's network namespace; on a host that can't pull it, the error names the `docker pull` to run); a route over the management interface comes back
(checked before and after every ping on FRR, SONiC and cEOS, after the positive checks, around the hold and around each
scenario); a ping's `target` or `source` is in a management network, or scoped to a management interface; a check reads
a node in the Docker host's namespace (`network-mode: host`); or a check reads the management VRF (NX-OS `management`,
SR Linux `mgmt`). The frr and sonic drivers are refused on VM kinds, where they would run in the container that launches
the VM.

So internet access from lab nodes works only during `setup:`, and a ping to an internet address can't pass. Nodes with
`network-mode: host` or `container:` are not touched. On a lab Netdryrun didn't deploy, the route is deleted too and not
restored.

Known limit: a vrnetlab VM node (NX-OS, RouterOS, Junos VMs) used as a transit router is not read for a management route
inside the VM.

### Config that fails to load

A pass only means something if the lab ran the config you wrote. FRR loads its config line by line at boot and skips a line it rejects (a typo, an incomplete command, a command this release doesn't have), so after the checks Netdryrun reads the boot log of every FRR node in the lab: any rejected line makes the run an **error (exit 2)**, naming the node, the line and the reason. A daemon can complain about a line and still apply it (bgpd answers `bgp graceful-restart` with "Failure to communicate" on FRR 10.4.1). So such a line doesn't count when line N of the node's `frr.conf` is that line and that daemon's own running config (`vtysh -d <daemon>`) has it under the same headers at every depth (`router bgp`, VRF, address family, `vni`), at least as many times as the file does, and has the line's whole block as written. A refused header line (`vni 10`, `address-family ...`) always counts. Every other kind of rejection always counts, and so does any line when the running config or `frr.conf` can't be read. A boot log that can't be read is an error too, and so is an FRR node whose log shows no sign of a config load (Netdryrun reads the load FRR's image runs at boot: `frr.conf` through `vtysh -b`, or a daemon reading its own file). Only the current boot counts, so a line fixed and reloaded with a restart no longer does. A node whose driver can't be detected (FRR in an image not named for it) is read when its log shows FRR's rejected lines (an error); otherwise the report says `not verified (no routing driver)`. A `setup:` command that fails (`vtysh -c` exits 1 on a rejected line) stops the run on every platform.

Known limit: **A line FRR warned about but applied can still make the run an error** (fail closed). Only a line a daemon answered with "Failure to communicate" is compared with the running config; a `Warning` line, a line for `mgmtd` (static routes on FRR 10, whose stored config can show a line a daemon then failed to apply) and a line from a daemon's own config file always count. Mitigation: rewrite the line so FRR loads it without a complaint. Fix scheduled: 0.4.3 (a live capture of each kind; was scheduled for 0.4, 0.4.1, then 0.4.2). The comparison also assumes `/etc/frr/frr.conf` is still the file FRR loaded at boot: a lab hook that rewrites it (`write memory`) before the run ends leaves only the check that line N is the reported line, so a rejected line could go unnoticed. Mitigation: don't save the running config over the bound `frr.conf` during a run (no `write memory` in `setup:` commands or lab hooks); bind the final config as the file FRR loads at boot. Fix scheduled: 0.4.3 (compare the file's change time with the boot; was scheduled for 0.4, 0.4.1, then 0.4.2).

**Startup config on Arista cEOS, Nokia SR Linux and SONiC** (fixed in 0.4): a line the NOS rejected at boot makes the run an error (exit 2). cEOS skips such a line and loads the rest, like FRR: Netdryrun reads `show startup-config errors` after the checks, and any listed line, or output it can't read, is an error naming the line. SR Linux: a CLI startup config is one commit containerlab applies at deploy, and a line that doesn't parse or a commit that fails fails the deploy; a JSON one SR Linux loads itself and, when it rejects it, runs without it while the deploy succeeds, so Netdryrun reads its log ("Load of startup configuration failed"; a log it can't read is an error). SONiC (docker-sonic-vs) has no startup config: it is configured with `setup:` commands, which stop the run when they exit non-zero; a config file bound into a SONiC node's `/etc`, `/usr` or `/var/lib`, or an inline startup config, is an error. A `setup:` command is checked by its exit code only: SONiC's `config ...` commands and CONFIG_DB writes can exit 0 and fail later, so configure SONiC's routing with `vtysh -c` lines, which fail at once. On a lab Netdryrun didn't deploy (`netdryrun check`), SR Linux and SONiC say `not verified`. **A topology `exec:` command that fails** is an error on every platform: containerlab only logs it and exits 0, and the node runs without what it configured. **Juniper cJunosEvolved (beta): the config load is not verified yet**; the report says `not verified on junos`: add a positive check for what each changed line creates.

Graceful restart (found by the 0.3.3 cross-platform review): while a peer restarts with graceful restart, its routes stay in the table marked stale until it re-sends them or the stale timer ends. On FRR and SONiC (which runs FRR) Netdryrun reads the stale flag, and a `route` or `bgp_route` check never passes on a stale path (0.3.3). On SR Linux (`stale-route`), Arista EOS (`routeType.stale`) and Juniper (beta; `Stale` or `LongLivedStale` in the route's state) a stale path stops the read with a 'not settled' error, so the check samples again until the mark clears (0.4.1); on SR Linux, EOS, Juniper and SONiC the field hasn't been seen turning true in a live graceful restart yet.

**SR Linux prefix counts, fixed in 0.4.1:** a `bgp_prefixes` count on SR Linux leaves out routes that failed BGP loop detection. SR Linux counts them in the neighbor's `received-routes` but not in `rejected-routes`, so 0.4.0 and earlier counted them and a `min` or `exact` check could pass with fewer usable prefixes. The driver now reads the local RIB and takes off every path marked exactly `invalid-reason: {as-loop: true}` (captured live from `examples/srl-frr`, 2026-11-02), so the count agrees with FRR and Junos, which don't accept such routes. A path marked with anything else (both `as-loop` and `rejected-route`, or a reason such as `next-hop-unresolved`) may or may not be in the count, so the count becomes a range, and a bound is judged only when the whole range gives the same answer.

Known limit: the gate sees sessions up and prefix counts stable, not routes still in flight. A peer with a long BGP advertisement interval can deliver a route after a post-convergence check was released and held, so a leak guard can pass on a route that hadn't arrived yet. From 0.4, `--settle` and `--hold` stretch automatically to the longest advertisement interval any session reports, plus 2 s (FRR and SONiC per neighbor, SR Linux `minimum-advertisement-interval`), and the run log says so. Still a limit: on Arista EOS a configured `out-delay` is not read (fix scheduled: 0.4.3), so raise `--settle` and `--hold` above it there; a route that crosses several slow peers can take one interval per hop.

Prefix counts with an upper bound start like this (step 4), because counters ramp up and the BGP gate has already waited for stable counts:

- `max` only: no wait. The count must be within `max` from the first sample of the hold window to the last (0 prefixes is within any `max`).
- `exact: N` (N at least 1) and `min` with `max`: first a short wait, up to 30 seconds (or `timeout` if shorter), for the count to reach at least N (or `min`); a count that never gets there fails. Then the full condition (`exact`, or the whole range) must hold on every sample of the hold window, so a count that overshoots fails.
- `exact: 0`: no wait; it must hold like `max: 0`.

`hold` is accepted only on post-convergence checks. A positive check passes after 2 consecutive passing samples, so a `hold` on it would be ignored; that is an error rather than a silent no-op. (Inside a scenario, positive checks do hold for `--hold`; see [scenario timing](#scenario-timing).)

Results are reported in the order the checks appear in the file.

## Drivers

A driver turns device state into a common shape. Netdryrun detects it from the topology:

- `kind: nokia_srlinux` or `kind: srl` uses `srlinux`
- `kind: arista_ceos` or `kind: ceos` uses `eos`
- `kind: juniper_cjunosevolved` or `kind: cjunosevolved` uses `junos` (beta)
- `kind: sonic-vs`, or an image whose name contains `sonic`, uses `sonic`
- an image whose name contains `frr` uses `frr`
- anything else is an error unless you set `nodes.<node>.driver`

| Check | FRR | SR Linux | Arista EOS | SONiC | Juniper cJunosEvolved (beta) | Cisco NX-OS (beta) | MikroTik RouterOS (beta) |
|---|---|---|---|---|---|---|---|
| `bgp_session` | yes | yes | yes | yes | yes | yes | yes (IPv4 sessions only) |
| `bgp_prefixes` (accepted = received minus rejected by policy) | yes | yes | yes | yes | yes | yes | yes (`ipv4-unicast` only; accepted counted from the routing table, since the session's `prefix-count` is the received count) |
| `route` present / absent | yes | yes | yes | yes | yes | yes; known beta limit: `present` reads the routing table's best flag (`ubest`), not FIB programming, so pair it with a `ping` across the same path | yes (IPv4 only) |
| `bgp_route`: communities (standard, large, well-known), AS path, local preference, MED, next hop, absent | yes | yes | yes | yes | yes | yes, except `without_communities` and `med: 0`, refused before the lab deploys (exit code `2`) | yes (IPv4), except `without_communities` and `med: 0`, refused before the lab deploys (exit code `2`) |
| `ping` success / failure | yes | yes | yes | yes | yes | yes | yes, outside a VRF (inside one it is refused) |
| Failure scenarios on the node's own links | yes | not yet (fail the FRR/Linux side instead) | yes | yes | not yet (fail the FRR/Linux side instead) | not yet (fail the FRR/Linux side instead) | not yet (fail the FRR/Linux side instead) |
| `inject_routes` on the node | yes | not yet (inject from an FRR neighbor) | not yet | not yet | not yet | not yet | not yet |
| Tested on a live lab in CI | yes, on every push | yes, on every push | no: parsers tested against output captured from live labs | no: parsers tested against output captured from live labs | no: parsers tested against output captured from a live lab; needs KVM | no: parsers tested against output captured from a live lab; needs KVM | no: parsers tested against output captured from a live lab; needs KVM |

**Received paths count as present on every driver:** a BGP route that lost to a static or local route, or that has an unresolvable next hop, may live only in the BGP table, not the routing table. Every driver reads the BGP table too, so a path received from a neighbor counts as present for `present: false`, valid or not, selected or not. The router's own paths (network statements, redistribution, and on SR Linux its static and interface routes listed in the BGP RIB) don't count as received. Neither does a route the import policy rejected, which FRR and Arista EOS drop and SR Linux and Junos keep, marked (SR Linux: `invalid-reason` `rejected-route`; Junos: hidden, "Rejected by import policy"). An SR Linux path marked invalid for any other reason, or marked invalid (`valid-route: false`) with no reason given, is an error until the driver reads that reason.

**Errors are never "nothing":** from 0.3.1, a failed command or output a driver doesn't recognize is an error on that sample (the check fails with `error: ...`), never read as "no routes" or "no sessions", which would pass `present: false` or `max`. A VRF that doesn't exist on the node is an error too, on every driver: FRR and SONiC confirm the VRF with `show vrf`, SR Linux reads the network-instance's oper-state, and Arista EOS requires the VRF in the `vrfs` map of its answer. `vrf: all` and other names that mean "every VRF" are refused.

**SONiC:** `docker-sonic-vs` routes with FRR inside the container, so the `sonic` driver reads state through `vtysh` like the FRR driver. The image boots unconfigured; put interface IPs (`config interface ip add ...`) and BGP (`vtysh -c ...`) in `nodes.<node>.setup`. See `examples/sonic-frr`.

**Juniper cJunosEvolved (beta):** free from Juniper for non-production labs, and can't be redistributed: download it yourself and `docker load` it. It boots a VM, so the host needs KVM and about 8 GB of memory per node. Hidden routes count as received, except routes rejected by import policy. See the [Juniper driver page](junos.md) and `examples/junos-frr`.

**Arista EOS:** cEOS-lab is free from arista.com (account required) and can't be redistributed. Download it yourself, then `docker import cEOS-lab-<version>.tar ceos:<version>`, and use `kind: arista_ceos` with that image.

| Driver | Source of state |
|---|---|
| FRR | `vtysh -c "show ... json"`; accepted prefixes from `acceptedPrefixCounter` (with add-path, the distinct prefixes in the neighbor's routes listing); `bgp_route` from `show bgp <afi> unicast <prefix> json` |
| SR Linux | `sr_cli --output-format json "info from state ..."`; accepted = `received-routes` minus `rejected-routes` (with add-path, the distinct prefixes of the neighbor's paths in the local RIB); `bgp_route` from the `bgp-rib` local RIB and its `attr-sets` |
| Arista EOS | `Cli -c "show ... \| json"`; accepted prefixes from `prefixAccepted` (with add-path, the range 1 to that count); `bgp_route` from `show ip bgp <prefix> vrf <vrf>` (the best path is the `active` one) |
| SONiC | the FRR commands, through `vtysh` inside the container |
| Cisco NX-OS (beta) | NX-API JSON-RPC from inside the container (a small helper POSTs to `https://127.0.0.1/ins`, which reaches the VM): `show bgp ... vrf <vrf>`, `show ip route <prefix> vrf <vrf>`; `"result": null` reads as nothing only once the VRF is confirmed with `show vrf <name>` |
| MikroTik RouterOS (beta) | the REST API from inside the container: sessions from `/routing/bgp/session` and `/routing/bgp/connection`, routes from `/routing/route`; accepted prefixes are counted from the routing table (paths of that session that policy didn't filter), since `prefix-count` is the received count |
| Juniper cJunosEvolved (beta) | `cli -c "show ... \| display json"` over the container's SSH hop to the Junos VM; accepted prefixes = `received-prefix-count` minus the hidden routes rejected by import policy; `route` and `bgp_route` from `show route <prefix> exact table <table> all extensive` (hidden routes included) |

If a driver can't read what a check asks for, the run stops before deploying (exit code `2`) instead of guessing: "`<key>` is not supported on `<driver>`" for a `bgp_route` attribute (today every driver reads every attribute), and "afi evpn is not supported on eos" (or `srlinux`, `junos`) for an EVPN prefix count on Arista EOS, SR Linux or Juniper, and "med: 0 can't be checked on eos: EOS output cannot tell MED 0 from no MED" for `med: 0` on Arista EOS. From 0.4.1 also "only is not supported on `<driver>` yet" for a `bgp_prefixes` `only` list outside FRR and SONiC, and "protocol `<name>` is never reported by `<driver>`" for a [protocol name](#protocol-names) the node's driver can't report.

Every command and its raw output is kept in the [JSON report](cli.md#json).

## Protocol names

`protocol` on a route check is compared in lower case with the protocol the device reports, after normalization:

| Use | FRR reports | SR Linux reports |
|---|---|---|
| `bgp` | `bgp` | `bgp` |
| `static` | `static` | `static` |
| `connected` | `connected` | `local` |
| `local` | `local` | `host` |
| `ospf` | `ospf` | `ospfv2` |
| `ospf6` | `ospf6` | `ospfv3` |
| `isis` | `isis` | `isis` |

OSPF and RIP names follow the prefix's address family, on every driver, from 0.4.1: `ospf` on an IPv4 prefix matches every OSPF route for it, OSPFv2 and OSPFv3 carrying IPv4 (RFC 5838, reported by Junos as `OSPF3`, SR Linux as `ospfv3`, EOS and NX-OS by their OSPFv3 route types); `ospf6` is OSPF on an IPv6 prefix. `rip` and `ripng` work the same way. Before 0.4.1 an OSPFv3 route carrying IPv4 was reported as `ospf6`, a name validate refuses for IPv4, so `protocol: ospf present: false` passed with the route installed. A check's detail keeps the device's own name, for example `active via ospf (OSPF3)`. As a result, no check can name OSPFv2 alone: a guard "OSPFv2 is gone" fails while OSPFv3 carries the prefix (check the OSPF process on the device instead).

`protocol` must be one of these names (case-insensitive): `bgp`, `connected`, `local`, `static`, `kernel`, `ospf`, `ospf6`, `isis`, `rip`, `ripng`, `aggregate`, `eigrp`, `babel`, `nhrp`, `table`, `sharp`, `pbr`, `openfabric`, `bgp-evpn`, `bgp-vpn`, `dhcp`, `arp-nd`, `gribi`. Any other name is a config error with a suggestion where one is close (`direct` → `connected`, `ospfv3` → `ospf6`); `ebgp` and `ibgp` are refused because drivers report both as `bgp`. Before 0.3.1 an unknown name was passed through, matched nothing, and silently passed `present: false`. The failure detail lists the protocols that were seen.

From 0.4.1 a name must also be one the node's driver can report, or the check is refused before the lab deploys (exit code `2`): it could never match a route there, so `present: false` would always pass. FRR and SONiC report zebra's names (`bgp`, `connected`, `local`, `static`, `kernel`, `ospf`, `ospf6`, `isis`, `rip`, `ripng`, `eigrp`, `babel`, `nhrp`, `table`, `sharp`, `pbr`, `openfabric`); EVPN, VPN and aggregate routes are `bgp` there, so `bgp-evpn`, `bgp-vpn` and `aggregate` are refused on FRR. SR Linux reports `bgp`, `bgp-evpn`, `bgp-vpn`, `connected`, `local`, `static`, `aggregate`, `ospf`, `ospf6`, `isis`, `dhcp`, `arp-nd` and `gribi`; Arista EOS `bgp`, `connected`, `static`, `ospf`, `ospf6` (every OSPF route in an IPv6 table), `isis` and `aggregate`. `protocol: bgp` matches SR Linux's `bgp-evpn` and `bgp-vpn` routes too, so a guard against BGP sees every BGP-learned route; `protocol: bgp-evpn` matches only EVPN routes (0.4.0 and earlier read every SR Linux BGP route type as `bgp`, so `bgp-evpn` never matched). The name must also fit the prefix's address family: `ospf` and `rip` on an IPv6 prefix, and `ospf6` and `ripng` on an IPv4 prefix, are config errors (exit code `2`) from 0.4.1, since every driver reports OSPF and RIP routes by the prefix's family (above).
