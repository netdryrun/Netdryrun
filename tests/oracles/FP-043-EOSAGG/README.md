# Oracle FP-043-EOSAGG: one name for the router's own BGP aggregate

Red-team record RT-0087 (this oracle). It turns the two accepted limits RT-0085 (shape a) and RT-0086 (shape b) on
ndr/fix-eos-nonbgp into fixed cases: the fix that makes these tests pass is the fix for both.

## The bug

On Arista EOS the protocol name of the node's own BGP aggregate (`aggregate-address`) depends on whether it won route
selection, and neither name is the one FRR gives the same aggregate.

| Shape | EOS state | main (a5244a0) reads | ndr/fix-eos-nonbgp (49dc098) reads | false pass |
|---|---|---|---|---|
| a, selected (RT-0085) | `show ip route`: `A B` (routeType `bgpAggregate`); BGP table: one own path, `localAgg: true` | `aggregate` | `aggregate` (the RIB's best `bgp` entry is skipped as the same route) | `protocol: bgp, present: false` passes |
| b, behind a static (RT-0086, corpus v2 case 18's setup) | `show ip route`: only `S` (dropRoute); `show rib route ip`: `>S`, ` B` not best; BGP table: one own path, `localAgg: true` | nothing (RIB not read, own BGP path skipped) | `bgp`, not selected | main: `protocol: bgp, present: false` and `protocol: aggregate, present: false` pass; fix branch: `protocol: aggregate, present: false` passes |

The same holds on IPv6 (2001:db8:66::/48) and in VRF blue (10.67.0.0/16), with the aggregate's contributor local
(`network`) or learned from a peer.

## Expected behaviour (decided here)

**The router's own BGP aggregate is `bgp`, on EOS as on every other driver, selected or not.**

- `route <agg> protocol: bgp` passes when the aggregate is the selected route, and `protocol: bgp, present: false`
  fails whenever the aggregate is in the RIB, selected or not. `protocol: bgp, active: false` passes in both cases,
  as on FRR. (The brief listed "`bgp active: false` passes with no learned route" in shape b as a symptom. On FRR the
  same check passes on the same scenario, live, because FRR's aggregate is a bgp candidate in zebra. Under one
  vocabulary that pass is correct, so the oracle requires it, and the false pass in shape b is the `aggregate` one.)
- A check naming the aggregate any other way is never read as absent while it is in the RIB. The oracle accepts either
  of two designs for `protocol: aggregate` on EOS: an EOS-only name that also matches the aggregate, selected or not
  (0.4.2 told users to write it as the RT-0085 workaround), or a refusal before the run, as FRR does today
  (`protocol aggregate is never reported by frr`). It does not accept "absent".
- A BGP path learned for the aggregate's exact prefix still counts as `bgp` (present, not selected while the aggregate
  or a static wins).

Why `bgp`:
1. The fixes-database rule for this class (FX-0.4.3-eos-aggregate-protocol, RT-0044): one protocol vocabulary across
   drivers, tested on the same scenario. FRR 10.4.1, run here on the same scenario, installs its aggregate in zebra as
   `bgp` (distance 200, blackhole), selected or not, and refuses `protocol: aggregate`. The NX-OS driver reads the
   aggregate's URIB entry by its `bgp-<asn>` client name, so it is `bgp` there too (from the driver code and the
   adversary brief; this repo has no NX-OS aggregate capture, and none was made here).
2. The config reference already says so: "EVPN, VPN and aggregate routes are `bgp` there [FRR, SONiC]". `aggregate`
   in the protocol list belongs to SR Linux and Junos, where it names a non-BGP aggregate route type
   (network-instance `aggregate-routes`, `routing-options aggregate`), not BGP's `aggregate-address`.
3. A guard "no BGP route for this prefix" (`protocol: bgp, present: false`) is what users write; it must see every
   BGP route the node holds, its own aggregate included, as it already sees every learned path (RT-0016).
4. FX-0.4.3-eos-aggregate-losing-read-as-bgp: a route's protocol name must not depend on whether it won selection.
   The BGP table's `localAgg` marker names the aggregate in both states.

## Scenario table (live, lab ndr-eosagg, 2026-11-21)

cEOS 4.36.3M ceos1 and FRR 10.4.1 frr2 hold the same aggregates and get the same changes; both peer with FRR up1,
which accepts nothing from them. Verdicts are the real drivers' (probe.py through `check_supported`, `run_check` and
`hold_together`), for 10.66.0.0/16, 2001:db8:66::/48 and vrf blue 10.67.0.0/16 alike unless noted. "EOS main / fix"
is main a5244a0 / ndr/fix-eos-nonbgp 49dc098; "want" is what this oracle requires of EOS.

| Phase | State | Check | FRR | EOS main | EOS fix | want |
|---|---|---|---|---|---|---|
| sel | aggregate selected, own contributor, nothing learned | bgp present: false | FAIL | **PASS** | **PASS** | FAIL |
| | | bgp (active) | PASS | FAIL | FAIL | PASS |
| | | bgp active: false | PASS | FAIL | FAIL | PASS |
| | | aggregate present: false | refused | FAIL | FAIL | FAIL or refused |
| selms | the only contributor learned from up1 (v4, v6; blue as sel) | as sel | as sel | as sel | as sel | as sel |
| exact | sel + up1 sends the exact prefix (v4, v6; blue has no peer, as sel) | bgp present: false | FAIL | FAIL | FAIL | FAIL |
| | | bgp (active) | PASS | FAIL | FAIL | PASS |
| exactstatic | exact + a static for the prefix (the static wins) | bgp present: false | FAIL | FAIL (blue: **PASS**) | FAIL | FAIL |
| | | aggregate present: false | refused | **PASS** | **PASS** | FAIL or refused |
| static | a static wins, the aggregate behind it, nothing learned | bgp present: false | FAIL | **PASS** | FAIL | FAIL |
| | | bgp active: false | PASS | FAIL | PASS | PASS |
| | | aggregate present: false | refused | **PASS** | **PASS** | FAIL or refused |
| | | static (active) | PASS | PASS | PASS | PASS |
| healthystatic | no aggregate, the static only | bgp / aggregate present: false | PASS / refused | PASS | PASS | PASS (unchanged) |
| healthy | nothing for the prefix | bgp / aggregate present: false | PASS / refused | PASS | PASS | PASS (unchanged) |

The full live verdicts are in tests/fixtures/{ceos4363m,frr1041}_eosagg_<phase>_verdicts*.txt.

ndr/fix-eos-nonbgp holds its own captures of both shapes (`ceos4363m_rcheos_aggstatic_*`,
`ceos4363m_fix043b_agg_*`, with its RT-0085/RT-0086 pins); this oracle doesn't copy them. Its captures here are a
separate run of the same image on one scenario shared with FRR, so the fix can be checked against both.

## The tests

- `tests/oracles/FP-043-EOSAGG/test_oracle_fp_043_eosagg.py` (red on main and on ndr/fix-eos-nonbgp): shape a fails
  `bgp present: false` and passes `bgp` (selected), shape b is never absent (`bgp present: false` fails and
  `aggregate present: false` fails or is refused), and every bgp verdict equals FRR's on the same phase.
- `tests/test_oracle_guards_fp_043_eosagg.py` (green on both): the healthy phases, a learned exact path still `bgp`, a
  selected aggregate still fails `present: false`, an aggregate behind a static never passes `present: true`, the
  device premises, FRR's verdicts from the captures equal the live ones, FRR refuses `protocol: aggregate`.

## What a fix must do

1. Name the node's own BGP aggregate `bgp` in `routes()` in every read: selected (routeType `bgpAggregate` in `show ip
   route`) and not selected (the RIB's ` B` entry, the BGP table's path with `routeType.localAgg: true`), in IPv4, IPv6
   and every VRF. Active only when it is the selected, programmed route.
2. Keep every learned BGP path for the prefix (the exact prefix from a peer) as `bgp`, present, not selected unless
   installed; reading the aggregate as `bgp` must not hide a learned path or make it active.
3. `protocol: aggregate` on EOS either matches the own aggregate in both states (selected: active; behind a static:
   present, not active) or is refused before the run, with the docs and the protocol-names table saying which. It is
   never "absent" while the aggregate is in the RIB.
4. An entry the driver can't classify (a RIB `bgp` entry with no BGP-table path to say whether it is the own aggregate
   or a learned path, an unknown routeType) is an error, never a raw or dropped name.
5. Flip RT-0085 and RT-0086 from accepted limits to fixed (`fixed_in`), update tests/known_false_passes.yml, the trust
   page and the CHANGELOG, and keep the workaround text (`bgp_route present: false` on the prefix, verified to fail in
   both shapes) for the released versions.
