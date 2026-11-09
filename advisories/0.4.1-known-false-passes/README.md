# Advisory: Netdryrun 0.4.1 and earlier, four narrow checks that can pass without seeing the problem

**Affected:** netdryrun 0.4.1 and earlier, and the `netdryrun/Netdryrun@v0.4.1` and earlier Actions (each entry gives
the drivers). **Severity:** Moderate, as [GHSA-g4f6-4624-2pjv](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-g4f6-4624-2pjv):
each case needs a specific driver, config and lab state, and each has a check that catches it today (given below).
**Patched versions:** case 4 is fixed in 0.4.2; cases 1 to 3 are not fixed yet, planned for 0.4.3. **Found by:** our own release gate (two isolated
adversarial reviewers and a fresh verifier on the final 0.4.1 candidate, 9 November 2026), before any outside user
reported them. **Evidence:** RT-0053 was reproduced in the pinned FRR image; the others were confirmed against recorded
router output (EOS from live fixtures), not yet through a Netdryrun live run. We publish them now to be safe. 0.4.1
ships with them published as known limits (trust page, configuration reference, CHANGELOG). Cases 1 to 3 were in
earlier versions too; case 4 is new in 0.4.1. 0.4.1 fixes the cases in the [earlier advisory](../0.4.0-further-false-passes/)
except where that advisory says otherwise.

GitHub advisory: [GHSA-ggcf-664f-c9ff](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-ggcf-664f-c9ff).
Each case is a red-team file in `tests/redteam/` (RT-0053, RT-0056, RT-0058, RT-0063) or an oracle (case 4, RT-S01),
registered in `tests/known_false_passes.yml`; the test fails if the published text or the limit changes unnoticed.

**What to do:** upgrade to 0.4.2 (case 4), and apply the workaround for each of cases 1 to 3 that matches your labs
until 0.4.3 ships.

**1. Arista EOS: `route ... present: false` with a protocol other than `bgp` didn't see a route that lost** (RT-0056,
RT-0063). 0.2.0 and later, Arista EOS. EOS's `show ip route` lists only the route it selected for a
prefix, and the driver looked for routes that weren't selected in the BGP table only. So a floating static (distance
250) behind a BGP default, or an OSPF default behind a local `ip route 0.0.0.0/0 Null0`, wasn't seen, and
`route prefix: 0.0.0.0/0, protocol: static` (or `ospf`) `, present: false` passed. FRR, SONiC and NX-OS list every
candidate and fail the same check. *Workaround:* on EOS, don't rely on `present: false` with a protocol other than
`bgp`: check the route where it comes from (for OSPF, on the neighbor that advertises it, if that isn't EOS), and add a
positive `route` check that the route EOS selected has the protocol you expect. *Planned for 0.4.3:* reads every candidate route.

**2. SR Linux EVPN: `bgp_route present: false` in an ip-vrf didn't see imported type-5 routes** (RT-0058). 0.3.0
and later, SR Linux. In an ip-vrf without its own `protocols bgp` (the usual EVPN layer-3 design), the
check read that network-instance's BGP RIB, which is empty; EVPN routes imported into it are held in the default
network-instance's EVPN RIB. So `bgp_route vrf: ipvrf, prefix: 10.99.0.0/24, present: false` passed with the route
imported and installed. *Workaround:* `route vrf: ipvrf, prefix: 10.99.0.0/24, protocol: bgp, present: false`, which
reads the routing table, where the installed `bgp-evpn` route matches `bgp`. *Planned for 0.4.3:* reads the EVPN RIB for an
ip-vrf.

**3. FRR and SONiC: a `ping` in a VRF to an address on the VRF device itself passed** (RT-0053). 0.1.0 and
later, FRR (SONiC from 0.2.0). Before 0.4.1 a `ping` to any of the node's own addresses passed; 0.4.1 refuses a target
the node answers itself, but reads a VRF's addresses from its enslaved interfaces only. With `ip addr add 10.9.9.9/32 dev red` (a common VRF loopback), `ping vrf: red, target: 10.9.9.9` was
answered by the node itself and passed (reproduced in the pinned FRR 10.4.1 image: `ip -j addr show vrf red` doesn't
list `red`; 2 of 2 replies). *Workaround:* put VRF loopbacks on a dummy interface enslaved to the VRF, or check the
address with a `ping` from another node. *Planned for 0.4.3:* the VRF device's own addresses count as the node's.

**4. SR Linux: `record --attributes` left out an AS path it couldn't read, without a warning (regression in 0.4.1).** 0.4.1 only,
SR Linux (0.4.0 recorded such a path as the empty AS path `""` and pinned it; 0.4.1 reads it as unknown). For a route whose AS path SR Linux prints none of (a route its iBGP peer originates), the recorded
`bgp_route` check had no `as_path`, while the CLI reference says the AS path is pinned; a later change of that path
(for example a hijacked origin relayed by the same peer) passed the baseline. *Workaround:* add `as_path` to such
recorded checks by hand. *Fixed in 0.4.2:* `record` writes no `bgp_route` check for a route whose AS path it can't
read, and an INCOMPLETE BASELINE line names it, so `record` exits 1; a local preference it can't read is named in a
warning. Add that route's check by hand (`as_path: ""` for an empty path). Reading the empty path exactly is planned
for 0.4.3.

## Found another way it can pass without looking?

[Open a corpus case](https://github.com/netdryrun/netdryrun/issues/new?template=corpus-case.yml): it becomes a
permanent must-fail test, credited to you. Or write to [security@netdryrun.com](mailto:security@netdryrun.com).
