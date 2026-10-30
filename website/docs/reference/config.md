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
- **Duplicate keys are errors**, at any depth: `duplicate key 'present' (first defined on line 12)`. Plain YAML keeps the last one silently. The topology file is read the same way. YAML merge keys (`<<: *anchor`) are allowed.
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
| `nodes` | no | | A mapping of node name to settings. Each node accepts only `driver` and `setup`. |
| `nodes.<node>.driver` | no | detected | Force the driver for a node: `frr`, `srlinux`, `eos`, `sonic` or `junos` (Juniper cJunosEvolved, beta). See [drivers](#drivers). |
| `nodes.<node>.setup` | no | | Shell commands run inside the node after deploy, before any check. Each is retried every 5 s until it succeeds (the NOS may still be booting), within a shared 300 s budget. For NOSes that are configured after boot, such as SONiC. |
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

The number of prefixes accepted from a neighbor is within a range. Accepted means received minus rejected by import policy.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `neighbor` | yes | | Neighbor IP address (a link-local address several sessions share is ambiguous, as for `bgp_session`) |
| `min` | one of `min`, `max`, `exact` | | Lower bound, inclusive |
| `max` | one of `min`, `max`, `exact` | | Upper bound, inclusive |
| `exact` | one of `min`, `max`, `exact` | | Exact count |
| `afi` | no | `ipv4-unicast` | Address family: exactly one of `ipv4-unicast`, `ipv6-unicast` or `evpn` (case-insensitive). `evpn` is supported on FRR and SONiC only, not on SR Linux, Arista EOS or Juniper (beta) |

Rules:

- At least one of `min`, `max` or `exact` is required.
- `exact` cannot be combined with `min` or `max`.
- `min` must not be greater than `max`.
- All three are non-negative integers.
- `min: 0` on its own is refused: it always passes. Use `min: 1` or more, or add `max`.
- Any other `afi` is refused (from 0.3.1). An address family the drivers don't report would read as 0 prefixes, which passes `max` and `exact: 0`.
- `afi: evpn` on an SR Linux or Arista EOS node is refused before the lab deploys (exit code `2`): those drivers read only the IPv4 and IPv6 unicast counts (SR Linux has no received-routes counter for EVPN), so an EVPN count would always read 0. SR Linux refuses it from 0.3.1; before, the count read 0 and passed `max`.
- The session must be `established`. Counters reset to 0 when a session drops, so a count from a down session would satisfy `max` by accident; Netdryrun fails the check instead.
- If the session is established but the address family reports nothing, the count is 0.
- A check with `max` or `exact` is a post-convergence check. A check with only `min` is a positive check.

```yaml
- type: bgp_prefixes
  node: r1
  neighbor: 10.0.12.2
  min: 1
  max: 10          # guards against a route leak flooding r1
```

### route

A route is present in (or absent from) the routing table.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `prefix` | yes | | IPv4 or IPv6 prefix |
| `present` | no | `true` | `false` means the route must be absent. Unquoted `true` or `false` only |
| `protocol` | no | any | Only count routes from this protocol: one of the names in [protocol names](#protocol-names). Case-insensitive |
| `vrf` | no | `default` | VRF or network-instance |
| `active` | no | `true` | With `present: true`: `false` also accepts a route that is in the table but not selected (for example a BGP default losing to a local one). Unquoted `true` or `false` only; not allowed with `present: false` |

- **Present** means an *active* route matches: selected and installed on FRR, `active` on SR Linux.
- **Absent** means no matching route at all, active or not. A BGP path that was received from a neighbor still counts as present, valid or not, selected or not (for example a leaked default losing to a local one), so `present: false` fails. This is how the [failing example](../index.md#a-failing-run) is caught. Every driver reads the BGP table for this as well as the routing table; there, only paths received from a neighbor count, not the router's own (network statements, redistribution, SR Linux's static and interface routes).
- `protocol` must be a name the drivers report. `ebgp` and `ibgp` are refused: drivers report both as `bgp`. A name outside the list would match nothing and silently pass `present: false`.
- `present: false` makes it a post-convergence check.

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
| `prefix` | yes | | IPv4 or IPv6 prefix, matched exactly |
| `communities` | no | | The best path must carry **all** of these. Standard (`'65000:100'`), large (`'65000:1:2'`) or well-known names (`no-export`, `no-advertise`, `no-peer`, `blackhole`, `graceful-shutdown`, `accept-own`, `llgr-stale`, `no-llgr`, `no-export-subconfed`) |
| `without_communities` | no | | The best path must carry **none** of these. Same forms as `communities` |
| `as_path` | no | | Exact AS path, ASNs separated by spaces: `"65002 65003"`. `""` is the empty path of a locally originated route. AS sets are written `{65004,65005}` |
| `as_path_regex` | no | | Python regular expression searched in the AS path string, for example `"^65002 "` (learned from 65002) or `"(^| )65666( |$)"` (passes through 65666). It runs with no time limit, so avoid nested repeats such as `(\d+ ?)+$` that can backtrack for minutes |
| `local_pref` | no | | Exact local preference |
| `med` | no | | Exact MED. A path with no MED attribute fails the check, even `med: 0`: with `bgp bestpath med missing-as-worst` a missing MED is the worst, not 0. On Arista EOS, `med: 0` is refused before the lab boots (exit `2`): cEOS prints MED 0 for a path received with no MED, so the two can't be told apart; a non-zero MED is checked as usual |
| `next_hop` | no | | Exact next hop address. A link-local address is refused: devices report it without its interface, and two sessions can share one, so the check couldn't say which path it tests |
| `present` | no | `true` | `false` means no path at all for the prefix in the BGP table, best or not, valid or not. Unquoted `true` or `false` only |
| `vrf` | no | `default` | VRF or network-instance |

Rules:

- Without attribute keys, the check passes when a best path exists.
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
| `target` | yes | | Destination IP address |
| `source` | no | | Source IP address (passed as `ping -I`) |
| `expect` | no | `success` | `success` or `failure` |
| `count` | no | `3` | Packets to send. An integer from 1 to 1000. |
| `min_replies` | no | `count - 1`, at least 1 | Replies needed for `expect: success`: an integer from 1 to `count`. One lost packet is tolerated by default (first-packet ARP). Not allowed with `expect: failure` |
| `vrf` | no | `default` | Runs in the VRF (`ip vrf exec` on FRR) or network-instance namespace (`srbase-<name>` on SR Linux) |

- `expect: failure` passes only with 0 replies, and is a post-convergence check.
- `expect: failure` also passes when ping reports the destination unreachable without sending anything: "Network unreachable" (or "Network is unreachable"), "No route to host" or "Destination unreachable" (0.3.1 and later). With no route at all, ping prints one of these and no statistics.
- If ping did not run at all for any other reason (bad source address, missing VRF), the check fails with an error. It never counts as a successful "failure".

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
| `link_down` | `{node, interface}` or a list of them; no other keys. Interface names as seen inside the node (for example `eth1` on FRR): a Linux interface name of at most 15 letters, digits and `. _ @ -` (checked from 0.3.1). SR Linux links can't be failed yet; fail the FRR or Linux side instead |
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

When the state was read and no BGP session runs over the downed links (static routing, a link without BGP, iBGP between loopbacks over an IGP), step 2 has nothing to observe; steps 3 to 5 still apply, so give such scenarios a `--settle` that covers the failure detection time. `inject_routes` faults have no step 2: Netdryrun instead waits until the injected prefixes are in the node's own BGP table. That alone doesn't show they reached the node under test; the BGP gate in step 5 does, for post-convergence checks: their node's prefix counts must stop changing first. The limit: a peer with a long advertisement interval (for example eBGP with a 30-second `advertisement-interval`) can hold the routes back for longer than 2 samples 3 seconds apart, so they can still arrive after the gate. Raise `--settle` above the advertisement interval for such labs.

### Injecting routes

New in 0.3.1: Netdryrun 0.3.0 rejects the key as unknown.

`inject_routes` makes a node announce routes it normally doesn't, so you can test what the rest of the network does with them: a customer leaking more-specifics, a peer announcing someone else's prefix, a flood that should trip a max-prefix limit.

| Key | Required | Meaning |
|---|---|---|
| `node` | yes | The node that announces the routes. It must be an FRR node with `router bgp` in the default VRF |
| `prefixes` | one of | A prefix or list of prefixes, IPv4 or IPv6 |
| `count` | one of | Announce this many consecutive prefixes (1 to 10000), starting at `from` |
| `from` | no | First prefix for `count`; its length is used for all of them. Default `100.64.0.0/24` |
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
- prefix counts with an upper bound (`max` or `exact`), since 0 prefixes satisfies `max: 10` while BGP is still starting

They run in this order:

1. Every positive check has finished.
2. **Every BGP session on the node is up.** Positive checks only prove convergence for the sessions and routes you happened to check, and a leak can arrive later over a session nobody checked. So for each node (and VRF) that carries a post-convergence check, Netdryrun waits until every configured BGP neighbor there is `established`, with unchanged prefix counts, on 2 consecutive samples. Neighbors that a `bgp_session` check expects in another state (for example `state: down`) don't count. The wait is capped at the largest `timeout` of that node's post-convergence checks. If a session there never comes up, those checks fail as **not evaluated**, naming the session: a down session is a finding, as everywhere else. If a session is down on purpose, add a `bgp_session` check with `state: down` for it. (A node that never answers with BGP state, or whose positive checks never got usable state, is not waited for; prefix counts still changing at the cap don't block.) A node that answers with **no BGP neighbors at all** is not converged: that is what a node answers before its BGP config is applied, and a leak can arrive once it is. Netdryrun keeps waiting, up to the cap. If the node still reports no neighbors then and the file says it runs BGP (a `bgp_session`, `bgp_prefixes` or `bgp_route` check on it, or a `route` check with `protocol: bgp`), its post-convergence checks fail as **not evaluated** ("reported no BGP neighbors by the cap"), every sample unready, so a leak guard can't pass on a router whose BGP config never loaded (from 0.3.2; when nothing anywhere gave usable state, the run is inconclusive). A node with no BGP check anywhere in the file may not run BGP at all: its post-convergence checks run anyway, each with a warning in its result ("reported no BGP neighbors for N s; the check was evaluated without BGP convergence"), and the verdict is unchanged. So a node that doesn't run BGP adds one `timeout` of waiting before its post-convergence checks. 0.3.1 and later.
3. A settle delay (`--settle`, default 10 seconds; at least 30 seconds if the file has no positive checks, because nothing else has shown that the network converged). From 0.4, `--settle` and `--hold` stretch to the longest BGP advertisement interval any session in the lab reports, plus 2 seconds: a peer sends at most once per interval, so a route can arrive that late. **On Arista EOS the advertisement delay (`neighbor ... out-delay`) is not read yet** (planned for 0.4.1): if you configure one, raise `--settle` and `--hold` above it, or a leak sent after the windows can pass a negative check.
4. Each one must then hold for the hold window (`--hold` or the check's `hold`, default 10 seconds), sampled every 3 seconds. A violation at any sample fails the check immediately.

### Config that fails to load

A pass only means something if the lab ran the config you wrote. FRR loads its config line by line at boot and skips a line it rejects (a typo, an incomplete command, a command this release doesn't have), so after the checks Netdryrun reads the boot log of every FRR node in the lab: any rejected line makes the run an **error (exit 2)**, naming the node, the line and the reason. A daemon can complain about a line and still apply it (bgpd answers `bgp graceful-restart` with "Failure to communicate" on FRR 10.4.1). So such a line doesn't count when line N of the node's `frr.conf` is that line and that daemon's own running config (`vtysh -d <daemon>`) has it under the same headers at every depth (`router bgp`, VRF, address family, `vni`), at least as many times as the file does, and has the line's whole block as written. A refused header line (`vni 10`, `address-family ...`) always counts. Every other kind of rejection always counts, and so does any line when the running config or `frr.conf` can't be read. A boot log that can't be read is an error too, and so is an FRR node whose log shows no sign of a config load (Netdryrun reads the load FRR's image runs at boot: `frr.conf` through `vtysh -b`, or a daemon reading its own file). Only the current boot counts, so a line fixed and reloaded with a restart no longer does. A node whose driver can't be detected (FRR in an image not named for it) is read when its log shows FRR's rejected lines (an error); otherwise the report says `not verified (no routing driver)`. A `setup:` command that fails (`vtysh -c` exits 1 on a rejected line) stops the run on every platform.

Known limit: **A line FRR warned about but applied can still make the run an error** (fail closed). Only a line a daemon answered with "Failure to communicate" is compared with the running config; a `Warning` line, a line for `mgmtd` (static routes on FRR 10, whose stored config can show a line a daemon then failed to apply) and a line from a daemon's own config file always count. Mitigation: rewrite the line so FRR loads it without a complaint. Fix scheduled: 0.4.1 (a live capture of each kind; was scheduled for 0.4). The comparison also assumes `/etc/frr/frr.conf` is still the file FRR loaded at boot: a lab hook that rewrites it (`write memory`) before the run ends leaves only the check that line N is the reported line. Fix scheduled: 0.4.1 (compare the file's change time with the boot; was scheduled for 0.4).

**Startup config on Arista cEOS, Nokia SR Linux and SONiC** (fixed in 0.4): a line the NOS rejected at boot makes the run an error (exit 2). cEOS skips such a line and loads the rest, like FRR: Netdryrun reads `show startup-config errors` after the checks, and any listed line, or output it can't read, is an error naming the line. SR Linux: a CLI startup config is one commit containerlab applies at deploy, and a line that doesn't parse or a commit that fails fails the deploy; a JSON one SR Linux loads itself and, when it rejects it, runs without it while the deploy succeeds, so Netdryrun reads its log ("Load of startup configuration failed"; a log it can't read is an error). SONiC (docker-sonic-vs) has no startup config: it is configured with `setup:` commands, which stop the run when they exit non-zero; a config file bound into a SONiC node's `/etc`, `/usr` or `/var/lib`, or an inline startup config, is an error. A `setup:` command is checked by its exit code only: SONiC's `config ...` commands and CONFIG_DB writes can exit 0 and fail later, so configure SONiC's routing with `vtysh -c` lines, which fail at once. On a lab Netdryrun didn't deploy (`netdryrun check`), SR Linux and SONiC say `not verified`. **A topology `exec:` command that fails** is an error on every platform: containerlab only logs it and exits 0, and the node runs without what it configured. **Juniper cJunosEvolved (beta): the config load is not verified yet**; the report says `not verified on junos`: add a positive check for what each changed line creates.

Known limit: **Graceful restart on SR Linux, EOS and SONiC** (found by the 0.3.3 cross-platform review): while a peer restarts with graceful restart, its routes stay in the table marked stale until it re-sends them or the stale timer ends, and on these platforms the BGP checks count a stale path as present and best. A route check can pass on a route that is about to go. On FRR, Netdryrun reads the stale flag: a route or `bgp_route` check never passes on a stale path (0.3.3). Mitigation: leave graceful restart off in the lab, or give the checks a `timeout` above the stale timer. Fix scheduled: 0.4.1 (read the stale flag on the other platforms, from a live graceful-restart capture; was scheduled for 0.4).

Known limit: **SR Linux prefix counts** (found by the 0.3.3 cross-platform review, seen on a live SR Linux 26.7.2): a `bgp_prefixes` count on SR Linux includes routes dropped by BGP loop detection, which are not usable, so a `min` or `exact` check can pass with fewer usable prefixes. Mitigation: pair the count with `route` checks for the prefixes that matter. Fix scheduled: 0.4.1 (count usable routes only; was scheduled for 0.4).

Known limit: the gate sees sessions up and prefix counts stable, not routes still in flight. A peer with a long BGP advertisement interval can deliver a route after a post-convergence check was released and held, so a leak guard can pass on a route that hadn't arrived yet. From 0.4, `--settle` and `--hold` stretch automatically to the longest advertisement interval any session reports, plus 2 s (FRR and SONiC per neighbor, SR Linux `minimum-advertisement-interval`), and the run log says so. Still a limit: on Arista EOS a configured `out-delay` is not read (fix scheduled: 0.4.1), so raise `--settle` and `--hold` above it there; a route that crosses several slow peers can take one interval per hop.

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

| Check | FRR | SR Linux | Arista EOS | SONiC | Juniper cJunosEvolved (beta) |
|---|---|---|---|---|---|
| `bgp_session` | yes | yes | yes | yes | yes |
| `bgp_prefixes` (accepted = received minus rejected by policy) | yes | yes | yes | yes | yes |
| `route` present / absent | yes | yes | yes | yes | yes |
| `bgp_route`: communities (standard, large, well-known), AS path, local preference, MED, next hop, absent | yes | yes | yes | yes | yes |
| `ping` success / failure | yes | yes | yes | yes | yes |
| Failure scenarios on the node's own links | yes | not yet (fail the FRR/Linux side instead) | yes | yes | not yet (fail the FRR/Linux side instead) |
| `inject_routes` on the node | yes | not yet (inject from an FRR neighbor) | not yet | not yet | not yet |
| Tested on a live lab in CI | yes, on every push | yes, on every push | no: parsers tested against output captured from live labs | no: parsers tested against output captured from live labs | no: parsers tested against output captured from a live lab; needs KVM |

**Received paths count as present on every driver:** a BGP route that lost to a static or local route, or that has an unresolvable next hop, may live only in the BGP table, not the routing table. Every driver reads the BGP table too, so a path received from a neighbor counts as present for `present: false`, valid or not, selected or not. The router's own paths (network statements, redistribution, and on SR Linux its static and interface routes listed in the BGP RIB) don't count as received.

**Errors are never "nothing":** from 0.3.1, a failed command or output a driver doesn't recognize is an error on that sample (the check fails with `error: ...`), never read as "no routes" or "no sessions", which would pass `present: false` or `max`. A VRF that doesn't exist on the node is an error too, on every driver: FRR and SONiC confirm the VRF with `show vrf`, SR Linux reads the network-instance's oper-state, and Arista EOS requires the VRF in the `vrfs` map of its answer. `vrf: all` and other names that mean "every VRF" are refused.

**SONiC:** `docker-sonic-vs` routes with FRR inside the container, so the `sonic` driver reads state through `vtysh` like the FRR driver. The image boots unconfigured; put interface IPs (`config interface ip add ...`) and BGP (`vtysh -c ...`) in `nodes.<node>.setup`. See `examples/sonic-frr`.

**Juniper cJunosEvolved (beta):** free from Juniper for non-production labs, and can't be redistributed: download it yourself and `docker load` it. It boots a VM, so the host needs KVM and about 8 GB of memory per node. Hidden routes count as received, except routes rejected by import policy. See the [Juniper driver page](junos.md) and `examples/junos-frr`.

**Arista EOS:** cEOS-lab is free from arista.com (account required) and can't be redistributed. Download it yourself, then `docker import cEOS-lab-<version>.tar ceos:<version>`, and use `kind: arista_ceos` with that image.

| Driver | Source of state |
|---|---|
| FRR | `vtysh -c "show ... json"`; accepted prefixes from `acceptedPrefixCounter`; `bgp_route` from `show bgp <afi> unicast <prefix> json` |
| SR Linux | `sr_cli --output-format json "info from state ..."`; accepted = `received-routes` minus `rejected-routes`; `bgp_route` from the `bgp-rib` local RIB and its `attr-sets` |
| Arista EOS | `Cli -c "show ... \| json"`; `bgp_route` from `show ip bgp <prefix> vrf <vrf>` (the best path is the `active` one) |
| SONiC | the FRR commands, through `vtysh` inside the container |
| Juniper cJunosEvolved (beta) | `cli -c "show ... \| display json"` over the container's SSH hop to the Junos VM; accepted prefixes from `accepted-prefix-count`; `route` and `bgp_route` from `show route <prefix> exact table <table> all extensive` (hidden routes included) |

If a driver can't read what a check asks for, the run stops before deploying (exit code `2`) instead of guessing: "`<key>` is not supported on `<driver>`" for a `bgp_route` attribute (today every driver reads every attribute), and "afi evpn is not supported on eos" (or `srlinux`, `junos`) for an EVPN prefix count on Arista EOS, SR Linux or Juniper, and "med: 0 can't be checked on eos: EOS output cannot tell MED 0 from no MED" for `med: 0` on Arista EOS.

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

`protocol` must be one of these names (case-insensitive): `bgp`, `connected`, `local`, `static`, `kernel`, `ospf`, `ospf6`, `isis`, `rip`, `ripng`, `aggregate`, `eigrp`, `babel`, `nhrp`, `table`, `sharp`, `pbr`, `openfabric`, `bgp-evpn`, `bgp-vpn`, `dhcp`, `arp-nd`, `gribi`. Any other name is a config error with a suggestion where one is close (`direct` → `connected`, `ospfv3` → `ospf6`); `ebgp` and `ibgp` are refused because drivers report both as `bgp`. Before 0.3.1 an unknown name was passed through, matched nothing, and silently passed `present: false`. The failure detail lists the protocols that were seen.
