# New-read review: ndr/fix-srl-evpn (RT-0058, oracle FP-043-SRLEVPNVRF)

- Reviewer session: recheck-srl. It wrote no code, test, record, evidence or allowlist in this change; this file is
  its only commit.
- Reviewed: bb9ab0d (fix a470a6f plus the hardening after this session's adversary review of a470a6f), judged against
  main 6a99c16's tests, as the gate runs them.
- Network OS the new reads touch: SR Linux only (`src/netdryrun/drivers/srlinux.py`).

## The new device reads

In a named network-instance, `routes` and `bgp_paths` on SR Linux now also send:
- `info from state /network-instance default bgp-rib afi-safi evpn evpn local-rib` (the EVPN RIB, where type-5 routes
  imported into an ip-vrf live), and
- `info from state /network-instance <vrf> route-table <afi> route <prefix> id * route-type * route-owner *
  origin-network-instance *` (from `bgp_paths`; `routes` already sent it).

With two or more EVPN candidates, or one candidate and an active bgp-evpn route, `bgp_paths` also reads the ip-vrf's
`route-table next-hop-group <id>`, `route-table next-hop <id>`, and in design B its own `bgp-rib attr-sets attr-set
<id>`. None of the seven fixtures below reaches those.

## The flips (all seven: genuine stricter-test flips, no assertion weakened)

| Test | What changed | Verdict |
|---|---|---|
| `tests.test_redteam::test_accepted_limits_are_published_and_still_behave_as_documented[RT-0058-srl-evpn-bgp-route-absent]` | RT-0058 is no longer an accepted limit (`fixed_in: 0.4.3`); its outputs gain the live EVPN RIB, route-table and attr-set captures (srl2672_fp043_present_*), and it is now judged by `test_driver_case_does_not_pass[RT-0058-...]`, which requires the check not to pass | genuine, stricter |
| `tests.test_verdict_drivers::test_srl_bgp_paths_commands` | the expected command list gains the EVPN RIB and route-table reads; the lab answers them `{}`. In the `nope` case the error is still `NoSuchInstance` from oper-state (checked), not another DriverError | genuine |
| `tests.test_verdict_drivers::test_srl_evidence_is_kept_everywhere` | evidence count for `bgp_paths` in a vrf goes from 2 to 4 (the two new reads are kept as evidence) | genuine, stricter |
| `tests.test_verdict_drivers::test_srl_local_pref_from_the_neighbor` | only the shared `_srl_paths_lab` helper changed, answering the new reads `{}` (nothing imported, nothing installed); every assertion is unchanged | genuine |
| `tests.test_verdict_drivers::test_srl_routes` | one more expected command (the EVPN RIB read in a named vrf) | genuine, stricter |
| `tests.test_driver_false_pass::test_srl_existing_network_instance_without_the_route_is_a_real_absence` | test file unchanged; the catch-all fake `("", "{\n}")` now also answers the EVPN RIB and route-table reads. `{}` there is SR Linux's answer for an empty container, and absence is still `[]` because nothing is imported. Passes on main's src and on the candidate's | genuine (new read answered, assertion unchanged) |
| `tests.test_driver_false_pass::test_srl_unknown_network_instance_raises_instead_of_no_routes` | test file unchanged; same catch-all answers the new reads. The command log shows the driver still ends on the oper-state read and raises `NoSuchInstance: network-instance 'CUSTOMR' does not exist`, the refusal the test is about, for `routes` and `bgp_paths` | genuine (new read answered, assertion unchanged) |

## What was checked

- Fresh clone of origin/ndr/fix-srl-evpn at bb9ab0d, `PYTHONPATH=src`: full suite 8261 passed, 66 skipped, 1 xfailed.
  The two test_driver_false_pass tests from main 6a99c16 pass with main's src and with bb9ab0d's src; their command
  logs were compared (the new commands are exactly the two reads above).
- The adversary review of a470a6f (MINOR 1-4) is closed in bb9ab0d: one candidate is checked against the ip-vrf's
  VTEPs when an active bgp-evpn route exists; the design-B row must be the attr-set asked for and hold a local-pref,
  for one candidate as for several; `_index` takes ASCII digits only. The offline attacks that passed on a470a6f
  (lone best-route path while the ip-vrf forwards elsewhere or ECMPs, row local-pref 300 vs path 100, empty or
  other-index row answer, Unicode digits) now raise.
- Mutants on bb9ab0d, all killed: candidates ignore best-route, default instance takes the first of several, design-B
  attr-id not digit-checked, local-pref compare skipped for a path without local-pref, one candidate not
  cross-checked, row index unchecked, row without local-pref accepted, `_index` without `isascii`.
- Live (SR Linux 26.7.2, lab rchk-srl, on a470a6f, driver level): two PEs with local-pref 200, ECMP over two RDs,
  the same RD on both PEs, equal local-pref with a longer AS path, VRF import policies (one per VRF, and one path in
  two VRFs), a PE link down through the hold time, and a 150 s PE flap race: no false pass; ambiguous states raise.
  EVPN cannot be configured in the default network-instance on 26.7.2.

## Live runs still owed

The release gate needs live runs on the candidate commit of every SR Linux example, because these reads are new.
Design A (an ip-vrf without `protocols bgp`) is "not evaluated" through `check` (the convergence gate sees no BGP
neighbors in that vrf): fail-closed, published as a limit in bb9ab0d.
