# New-read review: ndr/fix-eos-agg-v3 (FP-043-EOSNONBGP, FP-043-EOSAGG; RT-0056, RT-0063, RT-0085, RT-0086, RT-0087)

- Reviewer session: adv-eos-agg. It wrote no code, test, record, evidence or allowlist in this change; this file is
  its only commit. (The captures `tests/fixtures/ceos4363m_advagg_*` came from this session's review lab, but the fix
  session chose, trimmed and committed them.)
- Reviewed: 65209e98cd5905a40217719da6ef129939f324e3 (oracles 8a129ac and 937dfb1, fixes bf3d4cd and 2658947, merge
  ad494f0, plants f0f6596 and 359ab8b, review fixes d217125, 8265328 and 65209e9), judged against main
  6df498add4799838aaaba55dcd9462bd6191feb6's tests, as the gate runs them.
- Verdict: merge after the items under "Still open". No false pass found on 65209e9.
- Network OS the new read touches: Arista EOS only. Live runs of every EOS example on the candidate commit are still
  owed to the release gate.

## The new device read

`EosDriver.routes()` (every `route` check on an EOS node, and record's guard evaluation) now also sends
`show rib route ip|ipv6 vrf <vrf> <prefix> | json`, between the routing-table read and the BGP-table read. Nothing
else is new on the device. The BGP table, read before too, is now read in full (every path of every entry, not up to
the first learned path), and every path of the node's own must be the aggregate (`routeType.localAgg`) or name its
source (`routeDetail.redistributionProtocol`), or the read is refused.

## Gate results on 65209e9

- `reproduce --range origin/main..HEAD`: clean (2 fix commits, each with its oracle failing on the parent).
- `plants --base origin/main`: clean, 20 of 20 caught. The own-path rule of 8265328 and 65209e9 sits in a wrapper
  outside the plant hunks of 2658947; it only adds a route or a refusal, and the three-read logic the plant reverses
  is unchanged, so moving it did not weaken the fix.
- `loosening --base origin/main`: blocked, 16 flips and 5 problems. The 5 problems are the entries of
  `fastfix/allow/0.4.3-eos-nonbgp.yml` that predate this review and don't yet say `kind: new-read` or name a
  reviewer; the allowlist is the fix session's to update. Three flips are command-log noise and are not covered here
  (below). The other 13 are judged genuine, listed next.
- Full suite on 65209e9, `PYTHONPATH=src`: 1 failed, 8737 passed, 66 skipped, 1 xfailed. The failure is
  `tests/test_redteam.py::test_ids_are_contiguous_so_no_case_disappears_quietly` (RT-0084 is on
  ndr/fix-frr-importchk-v2): this branch must reach main after that one.

## The flips (13 judged genuine, no assertion weakened)

| Flip | Kind | What changed | Verdict |
|---|---|---|---|
| `tests.test_driver_false_pass::test_eos_existing_vrf_without_the_route_is_a_real_absence` | new-read on eos | main's fake has no answer for the RIB read. The candidate adds the live empty-RIB answer (`ceos4363m_fix043_absent_rib_route_9.json` shape), keeps the empty-list and BGP-VRF-missing assertions, and adds a must-raise for a RIB answer without the VRF. | genuine, stricter |
| `tests.test_driver_false_pass::test_eos_vrf_missing_from_answer_raises` | new-read on eos | test unchanged; the candidate sends the RIB read too, and every read still raises "not in the output" for the missing VRF | genuine |
| `tests.test_verdict_drivers::test_default_vrf_everywhere` | new-read on **eos** (tagged `*` because the test covers every driver) | the command log's new line is `Cli -p 15 -c show rib route ip vrf default 10.1.0.0/16 \| json` on r1, the EOS RIB read, not a temp path. The candidate's fake answers it; the `vrf default` assertion now covers that command too. | genuine, stricter |
| `tests.test_verdict_drivers::test_eos_routes_commands` | new-read on eos | three commands pinned in order instead of two (the RIB read in the right family and VRF), three evidence entries; route values unchanged | genuine, stricter |
| `tests.test_verdict_drivers::test_eos_routes_rules` | new-read on eos | (1) an entry with a malformed key ("10.1.0.0/16 ") that main never read past now raises. (2) 65209e9: the node's own `network` path in the input now carries `routeDetail.redistributionProtocol: "Static"`, as cEOS 4.36.3M prints it (`ceos4363m_advagg_network_ip_bgp.json`, `eos_bgp_paths_local.txt`); every route list main asserted is still asserted, and the bare own path main used is now asserted to be refused. | genuine, stricter; the input change mirrors live |
| `tests.test_redteam::test_accepted_limits_are_published_and_still_behave_as_documented[RT-0056-eos-floating-static-not-selected]` | new-read on eos | the case left the accepted limits (fixed); it now runs as a driver case with the live RIB capture and ends "unexpectedly present via static (not selected)" | genuine |
| `tests.test_redteam::test_accepted_limits_are_published_and_still_behave_as_documented[RT-0063-eos-ospf-default-behind-static]` | new-read on eos | as RT-0056: ends "unexpectedly present via ospf (not selected)" with the live RIB capture | genuine |
| `tests.test_redteam::test_driver_case_does_not_pass[RT-0016-eos-leak-received-not-selected]` | new-read on eos | d217125 adds a RIB answer derived from live captures; a case with an unanswered command now fails the test. Checked: it ends "unexpectedly present via bgp" for its own reason, and a second answer set (no RIB bgp entry, the leaked path not valid; `tests/test_redteam_reverts_043.py`) pins the BGP-table read: the reviewer's mutant that drops the "learned, not installed" route is killed there. | genuine |
| `tests.test_redteam::test_driver_case_does_not_pass[RT-0025-eos-ospf6-never-matches]` | new-read on eos | RIB answer added (`ospf3`, derived; no live OSPFv3 RIB capture). Reverting both layers (EOS map and Route's family names) makes the case pass. | genuine |
| `tests.test_redteam::test_driver_case_does_not_pass[RT-0037-eos-unmapped-route-type-passes-present-false]` | new-read on eos | live empty-RIB answer added, and `routingDisabled` plus the programmed flags added to the routing-table answer as every live answer prints them. Passing the unmapped routeType through raw makes the case pass. | genuine |
| `tests.test_drivers_harden_041::test_eos_mapped_route_types[bgpAggregate-aggregate]` | verdict | `bgpAggregate` now maps to `bgp`, as FRR names its own aggregate (live, same scenario on both); the old pair is replaced by `[bgpAggregate-bgp]`, and `aggregate` joins the must-raise list | genuine (one vocabulary across drivers) |
| `tests.test_false_passes_041::test_eos_route_types[bgpAggregate-10.0.0.0/24-aggregate]` | verdict | same rename, `[bgpAggregate-10.0.0.0/24-bgp]` | genuine |
| `tests.test_verdict_drivers::test_eos_route_types[aggregate-aggregate]` | new-read on eos | replaced by `[bgpAggregate-bgp]`; a plain `aggregate` routeType is now in the must-raise test | genuine, stricter |

Noise, not covered by this review: `tests.test_startup_config_load::test_audit_f1_an_exec_command_that_failed_fails_the_deploy`
and the two `tests.test_verdict_keys_041::test_action_verify_*` tests (temp paths and side labels in the command
log; no EOS read).

## What was checked

- Live, cEOS 4.36.3M beside FRR 10.4.1 (review lab ndr-advagg, destroyed): own aggregates with `advertise-only`,
  `as-set summary-only`, `attribute-map`, no contributors, a denying `match-map`, the same prefix also received from
  a peer, behind a static, `advertise-only` behind a static, IPv6, and IPv6 in a VRF. Every EOS verdict of
  `protocol: bgp` present/absent/not-selected, any-protocol absent and `protocol: static` absent was right and equal
  to FRR's wherever FRR has the construct. `advertise-only` puts the aggregate in the BGP table only (RIB empty), and
  4.36.3M prints `localAgg: true` there, also behind a static. A `network` path prints
  `redistributionProtocol: "Static"` and the aggregate none.
- 23 mutants of the fix and the review fixes, all killed (localAgg ignored or loosened, RIB checks removed, RIB read
  failure read as none, other prefixes or unknown keys accepted, aggregate renamed back, routes made active, the
  own-path rule removed, made RIB-independent or made to need the flag; RT-0016, RT-0025, RT-0037 reverts).
- Refusals: `protocol: aggregate` on EOS is refused in `preflight` (exit 2) before any run; an unread or unknown RIB
  answer, a RIB bgp entry the BGP table doesn't explain, a non-boolean or peer-carried `localAgg`, and an own path
  that is neither aggregate nor redistributed are errors. None reads as a pass.
- The own path that names its source while neither the routing table nor the RIB holds the prefix reads as `bgp`,
  not selected. That only adds a route, so it can fail `present: false` and `present: true`, and can satisfy only
  `protocol: bgp active: false`, which is true (the path is in the BGP table and is sent). It passes nothing it
  shouldn't.

## Still open (not blocking this review's judgement of the flips)

- MINOR: the suite is red until RT-0084 reaches main (merge order, above).
- MINOR (suspected cousin, other driver): NX-OS drops `pathtype aggregate` from received paths and its routing table
  lists only selected routes, so the RT-0086 and RT-0056 shapes may pass `present: false` there (beta driver, not
  checked live). Needs its own record.
- Documented limit: a static whose next hop doesn't resolve is in no EOS read, so `protocol: static present: false`
  passes on EOS where FRR fails it.
- Only cEOS 4.36.3M is captured; the own-path refusal keeps an EOS that doesn't print `localAgg` from reading an
  aggregate as absent, at the cost of an error.
