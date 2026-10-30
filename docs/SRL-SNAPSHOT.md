# SR Linux snapshot for `verify_change`: what exists, what is missing, what to capture

Internal note (2026-10-30). Code: `src/netdryrun/verify/srlinux.py`; tests: `tests/test_verify_srlinux.py`.
Branch `ndr/srl-snapshot` is based on the 0.4.0 line (the snapshot types live there) and merges into `ndr/release-0.4.1` after 0.4 ships.

## State
- **Done offline, from real SR Linux 26.7.2 captures:** strict readers for BGP neighbors, the IPv4 route table, the BGP Local-RIB path listing and BGP attribute sets. Each has a key allowlist, rejects unknown fields, wrong types, stale and pending-delete paths, enabled address families or add-path modes verify does not snapshot, link-local next hops, routes from other network instances, and cut or empty answers.
- **Not done: a `Snapshot`.** `SrlCollector.collect()` refuses, runs no command, and names every source in `MISSING_SOURCES`. `verify.run.classify_nodes` keeps refusing SR Linux nodes, so an SR Linux node can never be passed by `verify_change` until every row below is captured and tested.

## Field to source (what each snapshot field needs, and whether we can read it)
| Snapshot field | SR Linux source | Status |
|---|---|---|
| Session state, peer AS, local AS, local address | `protocols bgp neighbor` | read (`parse_neighbors`) |
| Session counters (received, active, rejected, suppressed, sent) | same | read; kept as separate numbers, none called "accepted" (C5) |
| Session address families | same, `afi-safi` | read; only `ipv4-unicast` enabled, otherwise refused |
| Add-path | same, `add-paths` | refused when send or receive is on |
| RIB entry: prefix, protocol, owner, active, preference, metric | `route-table ipv4-unicast route` | read (`parse_route_table`) |
| RIB entry: installed in FIB | `fib-programming` | read (`fib_programmed`: active, not suppressed, nothing pending or failed) |
| RIB entry: next hops (ECMP set) | the `next-hop-group` named by the route | **missing**: group members not captured |
| BGP path: prefix, peer, path id, used/valid/best/backup | `bgp-rib ... route` | read (`parse_rib_paths`) |
| BGP path: stale | `stale-route` | read, refused when true; flips during a real graceful restart are **unverified** |
| BGP path attributes: origin, next hop, MED, local-pref, AS path, communities, large communities | `bgp-rib attr-sets attr-set` | read (`parse_attr_set`); absent MED or local-pref stays unknown (None) |
| BGP path attributes: extended communities, aggregator, cluster list, originator id | same | **refused** (unknown field) until captured |
| Path next hop reachability, IGP metric | none in the listing | **missing** |
| Adj-RIB-In (what a peer sent), Adj-RIB-Out (what we advertised) | received-routes / advertised-routes listings | **missing** |
| Locally originated route (empty AS path) | attr set without segments | **missing**: printed form unknown, refused |
| Other network instances, IPv6 | same commands per instance and family | **missing** |
| Running configuration (normalised) | `info flat` or `info from running` text | **missing** |
| Link-local next hop with interface | attr set plus interface | refused |

## Live captures needed (one lab run each, under the lab lock, after 0.4's gate; queue order stays: loop count, snapshot captures, then others)
1. **Loop count** (`tests/test_srl_loop_count.py` docstring on `ndr/release-0.4.1`): a looped route's effect on `received-routes`, `rejected-routes`, `active-routes`.
2. **Next-hop group**: `info from state network-instance default route-table next-hop-group <id>` for a plain route and an ECMP route (two next hops, weights).
3. **Adj-RIB-in/out**: `received-routes` and `advertised-routes` per neighbor with soft-reconfiguration (SR Linux keeps the Adj-RIB-In only with it) and without; with an import policy that rejects a prefix.
4. **Attribute rarities**: extended community, aggregator, cluster list, originator id, atomic aggregate true, a route originated here (empty AS path), a link-local IPv6 next hop.
5. **Running config**: the text form to normalise, with a config that has comments, ordering differences, and a secret.
6. **Other network instance and IPv6 session**: a VRF with a session, an IPv6 unicast session.
7. **Graceful restart**: a real restart of a peer, to see `stale-route` turn true.
8. **Next-hop resolution**: a route with an unreachable next hop.

## Rules (0.4 gauntlet R1 to R8 and the contract C1 to C26): where they stand for SR Linux
The rule-by-rule table is in `PREP.md` on `ndr/release-0.4.1`. Short form: the parsers carry C1, C4, C9, C10, C11, C12, C14, C19, C23, C25 and C26 today; C5, C7, C8, C13, C15, C18, C20, C21 and C22 depend on a missing capture, and the collector refuses until they exist.
