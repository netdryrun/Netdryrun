# Juniper cJunosEvolved driver (beta): 0.4 review sheet

Branch `ndr/junos`, `main` (0.3.2) merged in. For the 0.4 cold review (layer 6) and the gate. Everything here is checkable from the branch: the fixtures and the commands that produced them are in `tests/fixtures/junos_*` and `tests/fixtures/junos_CAPTURES.md`.

Image: `cjunosevolved:26.2R1.7-EVO` (containerlab kind `juniper_cjunosevolved`), never committed or redistributed. Captured live on 2026-10-28 and 2026-10-29 from four labs: `ndr-junos-cap` (VRF, IPv6, an idle peer, hidden routes), `ndr-junos-ibgp` (iBGP, no-export), `ndr-junos-frr` (the example, and the error while rpd starts), `ndr-cap-junos` (the capture script's lab: out-delay, a routing instance).

## Must-fail coverage, every check type

Two independent sets, both on captured Junos output, both through the real validator and scheduler:

| Check type | `test_driver_matrix.py` (must-fail / control) | `test_driver_junos.py` MUST_FAIL | What the cells cover |
|---|---|---|---|
| `bgp_session` | 2 / 1 | 5 | not established; must be down but is up; peer not configured; unreadable answer; unknown routing instance |
| `bgp_prefixes` | 5 / 1 | 6 | over max, under min, not exact; session down; IPv6 asked on a v4-only session (0, never the v4 count); idle peer read as 0; unreadable answer |
| `route` | 4 / 1 | 8 | leaked default inactive behind a static (received, not selected); hidden for an unusable next hop (received); rejected-by-import route asked active; wrong protocol; unknown instance; unreadable answer |
| `bgp_route` | 9 / 1 | 12 | every key: `present: false` (installed, inactive, hidden next hop), `as_path`, `as_path_regex`, `local_pref`, `med`, `next_hop` (eBGP backup, iBGP forwarding vs protocol next hop), `communities` (standard, large), `without_communities` (no-export); no best path; unknown instance; unreadable answer |
| `ping` | 2 / 1 | 6 | no replies; unreachable; bad source; must fail but replies; must fail in an unknown instance (did not run is not "failed as expected"); unreadable answer |

Address families: `ipv4-unicast` and `ipv6-unicast` have must-fail cells; `evpn` is refused before deploying (`unsupported_afis`). Meta-tests turn CI red if a check type or a driver loses its cells (`test_meta_every_check_type_has_junos_must_fail_cases`, `test_meta_every_driver_and_check_type_has_cells`). The compatibility matrix (`website/docs/reference/compatibility.md`) is generated from these and lists Juniper as beta.

Also on the driver: fuzz (layer 3: empty, truncated, garbage, wrong-type JSON, reordered, mutated) on 11 parser cases plus 2 fail-safe parsers; false-pass regressions (renamed containers, unknown instance, received paths); 124 unit tests in `test_driver_junos.py`.

## Verified live (2026-10-28)

| What | Result |
|---|---|
| `examples/junos-frr`, good configs, fresh deploy | PASSED 13/13, exit 0, 398 s |
| FRR leak (`leaks/frr1.conf`), fresh deploy | FAILED 12/13, exactly the j1 guard, exit 1, 1385 s (host loaded) |
| Junos leak (`leaks/j1.cfg`), fresh deploy | FAILED 12/13, exactly the frr1 guard, exit 1, 985 s |
| Junos leak applied on a running lab, `netdryrun check` | FAILED 12/13, the frr1 guard; the j1 guard read the withdrawn default as absent |
| Through those runs: `bgp_session` (v4, v6), `bgp_prefixes` (v6 `max`), `route` (BGP v4, v6, static), `bgp_route` (communities incl. large, as_path, local_pref, MED, next hop, `present: false` both ways), `ping` with a source | all read correctly on the live device |
| Not-ready shapes: SSH hop refused while the VM boots (rc 255), `xnm:error` "routing subsystem is not running" (invalid JSON) | captured; both are errors on that sample, never "nothing" |

## Verified live on 2026-10-29 (lab window 23:12–23:25, `netdryrun check` on the kept capture lab)

| What | Result |
|---|---|
| `scripts/capture_fixtures.sh junos` on `examples/junos-frr` | ran end to end in 5 min, `fixture_shape.py`: 0 drift (the IPv6 route was captured before its session was up; the script now waits for it) |
| Checks in a routing instance (`vrf: CUST`): static and connected route present, a master-only route absent (`route` and `bgp_route`), an idle VRF session `state: down`, ping inside the VRF with a source | all passed |
| IPv6 ping with a source | passed (3/3) |
| Must-fail on the same lab: a VRF route `present: false`, a route and a BGP path in an unknown instance, an idle VRF session expected established, ping to a prefix the VRF has no route to | 5/5 failed (unknown instance: "routing-instance 'NOPE' does not exist") |
| `netdryrun record` on a lab with a Junos node | recorded 12 checks (sessions, exact prefix counts per family, routes) |
| `out-delay 10` configured: Junos adds `outbound-timer` (seconds) to the peer's options | captured; read as `adv_interval` in the commit that goes on the 0.4 release branch (it needs that branch's `base.py`), with `vrfs()` from a live `show route instance` |

## Not yet live-verified

1. **verify_change** doesn't snapshot Junos in 0.4 (FRR only by design; coordinator decision): a Junos node is refused or `--unobserved`, and the verify reference says so with the boot times.
2. **Hosted CI:** never run on a GitHub runner. cJunosEvolved needs KVM, 4 vCPUs and about 8 GB per node; boot took 4 to 19 minutes here.
3. **Other images:** only 26.2R1.7-EVO. vJunos, other cJunosEvolved releases and real Junos devices are untested.
4. **Multipath / ECMP, add-path, AS sets and confederations from a live device:** the AS-path parser handles `{}` and `()` from documented forms only; a bracketed local AS (`[65001]`) is refused as unknown.
5. **The settle stretch with a Junos `out-delay`** in a full run: the parser reads it from a live capture; the runner's stretch is tested on FRR.

## Decisions for the reviewer

1. **A hidden route rejected by import policy is not present.** Junos keeps it for `show route hidden`; it can never be used, and FRR and EOS don't keep it at all. Every other hidden route (unusable next hop, unknown or no reason) counts as received. The alternative (count it) would make the correct fix, filtering the leak on the way in, fail the guard.
2. **BGP best path when another protocol wins:** the first BGP route whose only reason to lose is route preference, as FRR reports it. A false fail if Junos ever orders entries differently, never a false pass on `present: false` (every received path counts there).
3. **`bgp_route` sees routes received over BGP only:** Junos doesn't list its own exported statics as BGP routes. `present: false` on the originating router passes where FRR would fail; documented.
4. **Prefix counts are Junos's `accepted-prefix-count`**, which also leaves out received routes Junos can't use (FRR counts them). A `min` can fail on Junos where it passes on FRR, never the other way.
5. **The SSH hop inside the container** (`root@176.1.1.1`, `/root/.ssh/sshkey`) is cJunosEvolved's own, as its `cli` wrapper uses; another Junos platform needs another transport.

## Refused before deploying

`afi: evpn`; `link_down` and `node_isolated` on a cJunosEvolved node; `inject_routes` from one; `vrf: master` (use `default`).
