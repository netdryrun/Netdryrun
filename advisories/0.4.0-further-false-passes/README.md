# Advisory: Netdryrun 0.4.0 and earlier, further checks that can pass without seeing the problem

**Affected:** netdryrun 0.4.0 and earlier (each entry gives the first affected version and the drivers), and the `netdryrun/Netdryrun@v0.4.0` and earlier Actions. **Severity:** Moderate, as [GHSA-cg9f-xjw5-38ph](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-cg9f-xjw5-38ph): each case needs a specific config, driver or lab condition, and in each one a correctly written check on the affected route or session, or a `ping` through it, would have caught the change. **Fixed in:** 0.4.1. **GitHub advisory:** [GHSA-g4f6-4624-2pjv](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-g4f6-4624-2pjv). **Found by:** our own release gate: the weekly adversarial run (1 November 2026), fuzzing, and the 0.4.1 acceptance round (2 November 2026), before any outside user reported them.

**What to do:** upgrade to 0.4.1 and re-run your checks. Re-record any baseline made with `netdryrun record`. 0.4.1 refuses some files that 0.4.0 accepted (a prefix without a length, an IPv6 `bgp_prefixes` neighbor without `afi`), and every such refusal is a check that could never fail before.

## Config: checks that could not fail

**1. A prefix written without a length was read as a single host.** 0.1.0 and later, every driver. `route prefix: 0.0.0.0, protocol: bgp, present: false`, written to mean "no default route via BGP", checked 0.0.0.0/32 and passed with a leaked 0.0.0.0/0 installed; the same applied to `bgp_route`, `only` entries and `inject_routes` prefixes. *Until 0.4.1:* write every prefix with its length (`0.0.0.0/0`, `::/0`, `192.0.2.1/32`). *0.4.1:* a prefix without a length is a config error (exit 2) naming the check.

**2. `bgp_prefixes` on an IPv6 neighbor without `afi` counted the IPv4 family.** 0.1.0 and later, every driver. With no `afi` the check read `ipv4-unicast`, which an IPv6 session usually doesn't carry, so the count read 0 and `max: 3` passed while the neighbor sent 500 IPv6 prefixes. *Until 0.4.1:* set `afi: ipv6-unicast` on every IPv6 neighbor. *0.4.1:* it is a config error with that hint.

**3. A family the session doesn't carry counted as 0, and `record` wrote nothing for it.** 0.1.0 (the count) and 0.2.0 (`record`) and later, every driver. Any `max` on such a family passed, and a baseline recorded on an IPv4-only eBGP session passed a change that added IPv6 to it and leaked IPv6 prefixes or an IPv6 default. *Until 0.4.1:* add `bgp_prefixes` checks with the right `afi` for each family a session may carry, and a `route prefix: ::/0, protocol: bgp, present: false` guard. *0.4.1:* on a family the session doesn't carry only `exact: 0` passes, saying so, and every other bound fails; `record` writes `exact: 0` for that family on each eBGP session and the `::/0` guard.

## `verify`

**4. A `with:` pin on `appears_on` explained every new path for the prefix.** 0.4.0, `verify` (FRR labs). Once the best path matched the pins, a second, non-best path from a peer the line doesn't name (a transit peer whose inbound filter the same change opened, with a hijacker's origin AS) was explained too, and the verdict was INTENT MATCHED. *Until 0.4.1:* don't rely on pins to exclude other peers; read the report's per-node paths for every prefix you declare. *0.4.1:* a pinned line explains only the paths and received routes from a neighbor that matches every pin; any other new path is undeclared.

## Drivers: device output read as "not there" or "present"

**5. FRR: a route zebra selected but failed to install counted as present** (RT-0021). 0.4.0 and earlier, FRR and SONiC. zebra leaves `installed` out when the route isn't in the FIB, and the driver read a missing key as installed, so `route` passed. *Until 0.4.1:* add a `ping` check through the route. *0.4.1:* only `installed: true` without `failed` counts.

**6. Well-known community names never matched their numbers** (RT-0022, RT-0027). 0.3.0 and later, FRR and SONiC. bgpd prints 65535:2, 65535:3, 65535:4, 65535:5 and 65535:8 by name (`route-filter-translated-v4`, `accept-own-nexthop`, ...), which were kept as text, so `without_communities: ['65535:8']` passed on a path that carried it. (RT-0027, 0:0 printed as `internet`, was not reproduced on FRR 10.4.1, which prints `0:0`.) A `bgp community alias` was kept as text too and passed the same way. *Until 0.4.1:* check communities you must never carry with `communities:` on a path that must not exist, or remove aliases from the lab. *0.4.1:* every name bgpd prints reads as its number, and `without_communities` fails on a name it can't turn into a number.

**7. SR Linux: `protocol: bgp-evpn` matched nothing** (RT-0023). 0.1.0 and later, SR Linux. Every BGP route type read as `bgp`, so `protocol: bgp-evpn, present: false` always passed. *Until 0.4.1:* use `protocol: bgp` (which matched EVPN routes). *0.4.1:* `bgp-evpn` and `bgp-vpn` keep their names; `protocol: bgp` still matches them.

**8. A protocol name the node's driver never reports was accepted** (RT-0024). 0.1.0 and later, every driver. For example `protocol: bgp-evpn` on an FRR node (zebra reports EVPN routes as `bgp`) matched nothing, so `present: false` passed. *Until 0.4.1:* use only the names in the 0.4.1 protocol-names table for your driver. *0.4.1:* `validate` and `run` refuse any other name (exit 2).

**9. Arista EOS: OSPFv3 routes never matched `ospf6`, and an unmapped route type matched nothing** (RT-0025, acceptance round). 0.2.0 and later, Arista EOS. No route type gave `ospf6`, and a `routeType` the driver didn't map (a nexthop-group static, a leaked route) was passed through raw; either way `present: false` passed with the route installed. *Until 0.4.1:* add a `route` check without `protocol` for prefixes that must be absent. *0.4.1:* OSPF in an IPv6 table is `ospf6` (live cEOS 4.36.3M prints `routeType: ospf`), and an unmapped type is an error.

**10. SR Linux: the router's own route counted as a BGP best path** (RT-0026). 0.3.0 and later, SR Linux. SR Linux lists its static and interface routes in the BGP RIB, marked best, so `bgp_route` passed on a route the router doesn't learn or advertise over BGP. *Until 0.4.1:* pair `bgp_route` with a `bgp_prefixes` check on the neighbor that should send it. *0.4.1:* a check whose only path is the router's own route fails, saying so.

**11. Juniper: a static with `no-install` counted as active** (acceptance A-3, confirmed live on `examples/junos-frr`). 0.4.0, Juniper (beta). Junos keeps the `*` on such a route and marks it `NotInstall`; `route protocol: static` passed while ping to it failed. *Until 0.4.1:* add a `ping` check through statics that must forward. *0.4.1:* a `NotInstall` entry is not active.

**12. SR Linux: an active route not in the FIB, and AS-loop routes, were counted** (acceptance A-1/A-2, live capture for AS-loop). 0.1.0 and later (FIB), 0.1.0 and later (AS-loop, documented as a limit since 0.3.3), SR Linux. A route SR Linux marks active before (or without) its FIB add counted as present; paths that failed AS-loop detection counted as accepted prefixes, so a `min` could pass on routes nobody can use. *Until 0.4.1:* add a `ping` check through the route; don't rely on `min` on SR Linux. *0.4.1:* active needs a completed FIB add; AS-loop paths are taken off the count.

## Defence in depth: no real device output was seen to trigger these

**13. An answer listing another prefix read as "not there".** 0.1.0 and later. Asked live for a /25 inside an installed /24 (2 November), FRR 10.4.1 (zebra and bgpd), cEOS 4.36.3M `show ip bgp`, SR Linux 26.7.2 and Junos (`exact`) answer with nothing; cEOS `show ip route <prefix>` answers with the covering /24, and the driver correctly skips it. So no released driver was seen to produce this, but a route listed for another prefix was skipped silently. *0.4.1:* everywhere but EOS's routing table it is an error.

**14. A count that disagrees with the list it counts.** 0.4.0 and earlier (Junos 0.4.0). Junos `rt-entry-count`, FRR/SONiC `pathCount` and EOS `totalPaths` were never compared with the entries printed beside them, so an entry dropped from under its count (found by fuzzing, never seen live) would read as one path less or none. *0.4.1:* a disagreement is a parse error.

## Scenarios

**15. `inject_routes`: routes that never left the injecting node were not noticed.** 0.3.1 and later, FRR injectors. The scenario BGP gate waits for prefix counts to stop changing, which counts that never changed do at once: with an outbound filter on the injecting node, or no session carrying the family, a `max:` or `present: false` check elsewhere passed on routes that were never sent. *Until 0.4.1:* pair each such scenario with a positive check that the injected routes reach a node they should reach (`bgp_prefixes min:` on the injecting node's neighbor). *0.4.1:* the injecting node's sent-prefix counts are read before and during the injection, and a scenario whose routes never left is inconclusive (exit 3), never a pass.

## The lab: Docker's management network

**16. A ping with no lab route left the lab over the management network** (second 0.4.1 red team, B3). 0.1.0 and later,
FRR and SONiC (every Linux container), and Arista cEOS deployed without a full startup-config. Docker gives each
container a default route over its management interface (`default via 172.20.20.1 dev eth0`), and containerlab's
built-in cEOS config adds `ip route 0.0.0.0/0 <management gateway>` in VRF default. A change that removed the lab's
route to a target left that route in place: the ping went out over the management network, Docker masqueraded it, and
any address the Docker host reaches (the host itself, its LAN, the internet) answered, so `ping expect: success` passed.
*Until 0.4.1:* delete the management default route in each node (`ip route del default dev eth0` in `setup:` on Linux
nodes; `no ip route 0.0.0.0/0 <gateway>` in the cEOS startup-config), and pair each ping with a `route` check for the
target's prefix with `protocol:` set. *0.4.1:* after `setup:` and before the first check, Netdryrun deletes exactly
Docker's (and containerlab's cEOS) default route via the management gateway; any other route over a management
interface, a route that comes back (checked around every ping and phase), a ping target or source in the management
network, or routes it can't read end the run as an error (exit 2), never a pass.

**17. `route 0.0.0.0/0` passed on Docker's own default route.** 0.1.0 and later, FRR and SONiC (a `route` check on
`0.0.0.0/0` or `::/0` without `protocol:`), and cEOS (also with `protocol: static`) on containerlab's management default.
The check passed whether or not the lab had a default route. *Until 0.4.1:* set `protocol:` on default-route checks
(`bgp`, or the protocol the lab uses). *0.4.1:* the management default is gone before the checks (case 16).

## Found by the 0.4.1 release candidate's red team (8 November 2026)

Two isolated attackers and a fresh verifier on the final 0.4.1 candidate found these; each was in 0.4.0 too.

**18. OSPFv3 carrying IPv4 never matched `protocol: ospf`** (RT-0044, RT-0045). 0.2.0 and later, Juniper (beta), SR Linux, Arista EOS and Cisco NX-OS (beta). An OSPFv3 route for an IPv4 prefix (RFC 5838 address family) was reported as `ospf6`, so `route <IPv4 prefix> protocol: ospf present: false` passed with the route installed. *Until 0.4.1:* add a `route` check without `protocol` for IPv4 prefixes that must be absent. *0.4.1:* OSPF and RIP names follow the prefix's family on every driver, so OSPFv3 carrying IPv4 is `ospf`.

**19. `bgp_route present: false` passed on a prefix the node advertised itself** (RT-0048, RT-0051). 0.3.0 and later, SR Linux and RouterOS (beta). SR Linux lists its own static and interface routes in the BGP RIB and the driver set them aside; RouterOS lists an advertised own prefix only as `bgp-output` rows, which the driver didn't read. FRR, EOS and NX-OS failed the same check. *Until 0.4.1:* check the prefix on the neighbor that would receive it. *0.4.1:* RouterOS's advertised own prefix fails `present: false`. On SR Linux and Junos the case is **accepted as a documented limit** (owner decision, 8 November 2026): `bgp_route present: false` doesn't see a prefix the node itself originates and exports, and the check's pass says so. Keep the guard on the neighbor that would receive the route; 0.4.2 reads what the node advertises (its adj-rib-out).

**20. Two YAML merge keys in one mapping dropped a guard** (RT-0050). 0.3.0 and later, every driver. With `<<: *guard` and `<<: *other` in one check, YAML keeps only one, and the strict loader didn't compare merge keys; merge sources that shared a key also kept one silently. *Until 0.4.1:* write each check's keys out, or use one `<<:`. *0.4.1:* a repeated `<<` and merge sources sharing a key are errors (exit 2).

**21. A baseline from `record --attributes` passed a best path that gained no-export or blackhole** (RT-0052). 0.3.0 and later, every driver. It wrote today's communities as a set the path must carry, not one it must equal, and nothing when the path had none. *Until 0.4.1:* add `without_communities: [no-export, no-advertise, blackhole]` to recorded `bgp_route` checks by hand. *0.4.1:* `record --attributes` also forbids every well-known community the path doesn't carry (where the driver can read communities).

**22. FRR and SONiC: a route the dataplane failed to program counted as present** (RT-0046, RT-0047). 0.1.0 and later, FRR and SONiC. zebra's `offloadFailed`, `queued` and `trapped` flags were not read, and on SONiC a BGP or static route the ASIC never programmed (no `offloaded`, for example with orchagent stopped) counted as active. *Until 0.4.1:* add a `ping` through routes that must forward. *0.4.1:* every zebra failure flag takes a route out of forwarding, and on SONiC BGP and static routes need `offloaded: true`.

**23. FRR: a community alias shaped like a community hid the real one** (RT-0049). 0.3.0 and later, FRR and SONiC. With `bgp community alias 65020:777 65020:100`, bgpd prints `65020:100` in place of 65020:777, so `without_communities: ['65020:777']` passed. *Until 0.4.1:* don't alias communities on nodes you check (a community-shaped alias, one with leading zeros or a well-known name all read as a real community). *0.4.1:* a community check reads the node's alias lines, and on a node with any alias every community check fails, saying the communities can't be read.

**How each was confirmed (8 November 2026).** Live on the lab machine, on the fix: SR Linux's own exported static
(case 19), cEOS printing routeType `OSPFv3` on an IPv4 route (case 18), an FRR community alias (case 23), and SONiC
BGP and static routes with `offloaded` (case 22: sonic-vs printed `offloaded` even with orchagent stopped, so that
build doesn't produce the uninstalled state; the rule stays, fail-closed). From captured output only: RouterOS's
`bgp-output` rows (case 19, from a live 7.23.8 capture), Junos's own static (case 19, from a live capture), OSPFv3
carrying IPv4 on Junos and SR Linux (case 18: crafted output; the SR Linux lab formed no OSPF route and the Junos lab
stopped at the memory guard), `offloadFailed` (case 22, never seen live) and the YAML and `record` cases (20, 21),
which need no device.

## Found another way it can pass without looking?

[Open a corpus case](https://github.com/netdryrun/netdryrun/issues/new?template=corpus-case.yml): it becomes a permanent must-fail test, credited to you. Or write to [security@netdryrun.com](mailto:security@netdryrun.com).
