# Advisory: Netdryrun 0.4.1 and earlier, FRR and SONiC `bgp_prefixes` counted add-path paths as prefixes

**Affected:** netdryrun 0.4.1 and earlier (FRR since 0.1.0, SONiC since 0.2.0), and the `netdryrun/Netdryrun@v0.4.1`
and earlier Actions. **Severity:** Moderate, as [GHSA-g4f6-4624-2pjv](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-g4f6-4624-2pjv):
it needs one driver family, a peer that sends add-path, and a count-only check; an `only:` list catches it today.
**Patched versions:** 0.4.2. **Found by:** our own release gate (an isolated red-team agent and a fresh verifier on the
0.4.2 candidate, 12 November 2026), before any outside user reported it. **Evidence:** reproduced the same night in a
containerlab lab with FRR 10.4.1.

## What happened

On FRR and SONiC nodes, `bgp_prefixes` read a neighbor's prefix count from FRR's `acceptedPrefixCounter`. When the
neighbor uses BGP add-path and sends more than one path per prefix, FRR counts each path. A neighbor sending 2 prefixes
with 2 paths each read as 4, so `bgp_prefixes min: 4` passed though only 2 prefixes arrived. FRR 10.4.1 accepts
add-path on every session by default, so only the sender needs `addpath-tx-all-paths`.

**Fixed in 0.4.2:** when the neighbor may send add-path, the count is the number of distinct prefixes in
`show bgp ... neighbors N routes json`, and a listing that doesn't add up to FRR's counter gives no verdict. A family
without such a listing (EVPN) is a range, judged only where the whole range agrees.

**Workaround before you upgrade:** add an `only:` list to the check; check the count on a neighbor that doesn't receive
add-path; or turn add-path receive off on that session if your design allows it
(FRR, under `address-family ipv4 unicast`: `neighbor X disable-addpath-rx`; checked on FRR 10.4.1).

The case is `tests/redteam/RT-0067-frr-addpath-paths-counted-as-prefixes.yml`; the oracle is
`tests/oracles/FP-042-ADDPATH`, built from the live capture. GitHub advisory: to be linked when published.
