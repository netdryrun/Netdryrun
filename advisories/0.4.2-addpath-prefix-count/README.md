# Advisory: Netdryrun 0.4.1 and earlier, `bgp_prefixes` counted add-path paths as prefixes (FRR, SONiC, SR Linux, Arista EOS)

**Affected:** netdryrun 0.4.1 and earlier: FRR since 0.1.0, SONiC since 0.2.0, Nokia SR Linux since 0.1.0 and Arista
EOS since 0.2.0, and the `netdryrun/Netdryrun@v0.4.1` and earlier Actions. **Severity:** Moderate, as
[GHSA-g4f6-4624-2pjv](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-g4f6-4624-2pjv): it needs a
peer that sends add-path and a count-only check; an `only:` list catches it today on FRR and SONiC.
**Patched versions:** 0.4.2. **Found by:** our own release gate (an isolated red-team agent and a fresh verifier on the
0.4.2 candidate, 12 and 13 November 2026), before any outside user reported it. **Evidence:** reproduced in containerlab
labs with FRR 10.4.1 (RT-0067), SR Linux 26.7.2 (RT-0068) and cEOS 4.36.3M (RT-0069).

## What happened

`bgp_prefixes` read a neighbor's prefix count from a counter the device keeps per neighbor. When the neighbor uses BGP
add-path and sends more than one path per prefix, that counter counts each path. A neighbor sending 2 prefixes with 2
paths each read as 4, so `bgp_prefixes min: 4` passed though only 2 prefixes arrived.

- **FRR and SONiC:** `acceptedPrefixCounter`. FRR 10.4.1 accepts add-path on every session by default, so only the
  sender needs `addpath-tx-all-paths`.
- **SR Linux:** `received-routes` minus `rejected-routes` (and, since 0.4.1, minus the paths that failed AS-loop
  detection), with `add-paths receive true` on the neighbor's family.
- **Arista EOS:** the summary's `prefixAccepted`. cEOS advertises additional-paths receive by default, so here too only
  the sender needs to send add-path.

**Fixed in 0.4.2:** when the neighbor may send add-path (its add-path state says so, or doesn't say):

- FRR and SONiC count the distinct prefixes in `show bgp ... neighbors N routes json`, and a listing that doesn't add
  up to FRR's counter gives no verdict. A family without such a listing (EVPN) is a range, judged only where the whole
  range agrees.
- SR Linux counts the distinct prefixes of the neighbor's paths in the local RIB (`bgp-rib`), which it already read for
  the AS-loop paths; a RIB whose usable paths don't add up to the counter gives no verdict.
- Arista EOS reads the peer's add-path receive state (`show ip bgp neighbors N vrf V | json`,
  `receivingAddPaths.enabled`). Where it isn't clearly off, `prefixAccepted` P becomes the range 1 to P prefixes: `max`
  and `exact: 0` still get a verdict, `min` above 1 gets none. Counting EOS prefixes from a route listing is planned.

**Workaround before you upgrade:** add an `only:` list to the check (FRR and SONiC); check the count on a neighbor that
doesn't receive add-path; or turn add-path receive off on that session if your design allows it (FRR, under
`address-family ipv4 unicast`: `neighbor X disable-addpath-rx`, checked on FRR 10.4.1; SR Linux:
`afi-safi ipv4-unicast add-paths receive false` on the neighbor or group; EOS: `no neighbor X additional-paths
receive`). On SR Linux and EOS, `only:` is refused (those drivers read no per-neighbor prefix list); a `route`
check with `present: true` on each prefix you expect catches it there.

The cases are `tests/redteam/RT-0067-frr-addpath-paths-counted-as-prefixes.yml`,
`tests/redteam/RT-0068-srl-addpath-paths-counted-as-prefixes.yml` and
`tests/redteam/RT-0069-eos-addpath-paths-counted-as-prefixes.yml`; the oracles are `tests/oracles/FP-042-ADDPATH`,
`tests/oracles/FP-042-SRLADDPATH` and `tests/oracles/FP-042-EOSADDPATH`, built from the live captures. GitHub advisory:
to be linked when published.

## Also fixed in 0.4.2: FRR and SONiC read a dampening history entry as a received route

**Affected:** FRR and SONiC, netdryrun 0.3.1 to 0.4.1 (0.4.1 only for the default route `0.0.0.0/0`). With
`bgp dampening`, bgpd keeps a route the neighbor withdrew listed as a dampening history entry until its penalty decays
(also a path it is still removing). The driver read that path as a received BGP route that wasn't selected, so
`route ... protocol: bgp active: false` passed ("present via bgp (not selected)") after the route was withdrawn, and a
`present: false` guard failed though the route was gone. From 0.4.2 such a path is no path; a route dampening
suppressed (the neighbor still announces it) is still present and not selected. **Workaround:** check the withdrawn
route with `present: false`, which fails on it (a false alarm, never a false pass), or clear dampening first
(`clear bgp ipv4 unicast dampening`). Case `tests/redteam/RT-0070-frr-dampening-history-entry-read-as-route.yml`, oracle
`tests/oracles/FP-042-FRRDAMP`, from a live FRR 10.4.1 capture.
