# 0.4.1 acceptance (Layer 5b), final candidate 8ce7dde (src identical to b88adef and 6e0a027)

Run hands-on in WSL (`Ubuntu-ndr`) from clean clones, one lab at a time under the lab lock. Vendor images are local only.
The first rounds ran on b61c325 and acb546b; after the fixes, what they touched was rerun on b03cb7a
(`ndr/release-0.4.1`; it differs from 553662c only in `releases/`).
**Result of this round: no open BLOCKER.** MINORs are listed at the end for triage.

## Final delta on 6e0a027 (inject_routes delivery redesign; wheel src identical to b88adef and 7532310; 8ce7dde differs from b88adef only outside src/)

One lab at a time under the lock; free memory 22 GB in WSL and 11 GB on Windows at start; the whole round took about 10 minutes.
**Result: no open BLOCKER, no finding.**

| Case | Lab | Expected | Got |
|---|---|---|---|
| Routes reach every peer | FRR chain n-h-x, h injects 10.100.0.0/24, check on x | PASSED | PASSED 2/2, exit 0 (59 s) |
| Filter towards one peer, check that passes (on n) | same, outbound deny-all on h towards x | INCONCLUSIVE naming the peer | INCONCLUSIVE, exit 3: "10.0.2.2 was not sent 10.100.0.0/24" (74 s) |
| Filter towards x, check on x | same | a real failure stays failed | FAILED 1/1, exit 1 (the check fails because x never has the route) |
| Hijack: P learned from n, h injects the same P, `advertisement-interval 30` towards x | FRR 10.4.1 | INCONCLUSIVE | INCONCLUSIVE, exit 3: "10.0.1.1 and 10.0.2.2 were not sent 203.0.113.0/24" (124 s) |
| cEOS example | arista-frr | PASSED | PASSED 10/10 (107 s) |
| SR Linux example | srl-frr | PASSED | PASSED 7/7 (68 s) |
| FRR examples | frr-bgp, leak-pattern | PASSED | PASSED 11/11 and 8/8 |
| FRR examples with failures | frr-customer-leak (ships the leaky config), frr-bgp-broken | FAILED | FAILED 19/2 and FAILED 5/1, as in earlier rounds |

Regression check for false inconclusives: no shipped example contains `inject_routes`, so the shipped examples' own scenarios (link_down) and the delivered inject case above were used; none read inconclusive.

FRR's advertised-routes detail JSON towards x on h, captured once a second around the hijack injection (91 snapshots; on FRR 10.4.1):
- before the injection: `{}` (nothing advertised to x yet) and then the path learned from n (pathCount 1, AS path 65001);
- right after the injection, while the 30 s advertisement-interval holds the update back: the prefix is listed with `advertisedTo` x **and** n, `pathCount` 2, the new local path (`local`, `sourced`) first, with the AS path still printed as 65001 for a few seconds and then "Local"; x has not been sent the update yet;
- after the interval, pathCount returns to 1 (the injected path is withdrawn when the scenario restores).
So FRR lists a prefix as advertised to a peer while the update is still waiting, which is why delivery has to be matched on the injected path; the run read INCONCLUSIVE as it must.

Harness notes, not product findings: my first filtered case put its check on x (so it correctly FAILED), and two examples that bind configs from a sibling folder had to run in place.

## Delta round on eaa323c (live, after the Layer 6 fixes)

Only what the fixes since b03cb7a touch was rerun, one lab at a time under the lab lock. Result: **no open BLOCKER**.

| Change | Live case | Result |
|---|---|---|
| inject_routes must reach every established peer | FRR triangle, r2 injects, outbound filter towards r3 (check on r1 passes) | INCONCLUSIVE, exit 3, naming peer 10.0.23.2 as not reached (62 s) |
| same, a check that really fails | same lab, check for a prefix never injected | FAILED, exit 1 (stays a plain failure) |
| same, no filter | same lab without the filter | PASSED, exit 0 |
| NX-OS / RouterOS only with an explicit `driver:` | nxos-frr and mikrotik examples with the `driver:` line removed | both exit 2 in under 2 s, no lab started |
| `only` on FRR | stranger lab, record then must-fail (customer filter loses its match) | record 63 checks, good 63/0, must-fail FAILED 62/1, 14/14 traps fail |
| EOS missing programmed flag | arista-frr example | PASSED 10/10 in 151 s (rerun; see note) |
| SR Linux AS-loop | srl-frr, frr1 injects a path containing the SR Linux AS 65010 | see note 2 |
| INCOMPLETE BASELINE | seen live in the degraded run (note 1) | printed per node, record still wrote its checks |

Not rerun on eaa323c (no live run): NX-OS and Junos unmapped-route-type errors, NX-OS and RouterOS beta warning text, RouterOS prefix-count cross-check beyond the earlier RouterOS example (b03cb7a), `only` count-vs-list mismatch beyond what the FRR record/run exercises. **Not covered** live.

Notes:
1. The first EOS run and the first FRR record ran while the host was slow (docker exec calls timing out at 15 s). The EOS run ended exit 2 "could not read the addresses of eth1 on frr1: timed out after 15s" (fail-closed, no false verdict), and the FRR record printed INCOMPLETE BASELINE for seven interfaces and wrote 48 checks instead of 63. After the slowdown ended, both reruns were clean (EOS 10/10, record 63). One MINOR: after the slow EOS run the destroy left `clab-ndr-arista-frr-ceos1` in state Exited (137), so a lab remained after an error (M-9).
2. SR Linux AS-loop: the check `route 10.100.0.0/24 present: false` on srl1 errors with "the path from 10.0.100.2 is invalid for as-loop, a reason the srlinux driver doesn't read yet" and the run FAILS (exit 1). The `bgp_prefixes max: 2` check passes (1 accepted: the looped path is not counted). This is fail-closed, not a false pass, but a looped path the device rejects cannot yet be asserted absent (M-10).

## Angle 1: each NOS (live)

For each driver: its example (good, and every leak must fail), the stranger's must-fail change (a customer filter loses its `match` line)
ported to that NOS with a `record` baseline, and the vendor output traps against the kept good lab (the harness keeps that lab on purpose and destroys it afterwards).

| Driver | Example good | Leaks fail | Record baseline | Must-fail change | Traps | Run on |
|---|---|---|---|---|---|---|
| FRR | PASS (frr-bgp, leak examples, batfish, agent-demo) | yes | 63 checks, good 63/0 | FAILED 62/1 (exit 1) | 14/14 fail correctly | b03cb7a (examples on b61c325) |
| SR Linux | PASS 7/7, hidden-leak PASS 9/9 | 2 of 2 | 8 checks | FAILED 7/1 | 14/14 | b61c325 |
| SONiC | PASS 8/8 | no leak example | 10 checks | FAILED 9/1 | 14/14 | b61c325 |
| Arista cEOS | PASS 10/10 | no leak example | 10 checks | FAILED 9/1 | 14/14 | b61c325 |
| Junos (beta) | PASS 13/13 | 2 of 2 | 24 checks, good 24/0 | FAILED 23/1 | 14/14 | acb546b |
| NX-OS (beta) | PASS 10/10 | 1 of 1 | 14 checks, good 14/0 | FAILED 13/1 | 14/14 | acb546b |
| MikroTik RouterOS (beta) | PASS 10/10 | 1 of 1 | 12 checks, good 12/0 | FAILED 11/1 | 14/14 | b03cb7a |

- Mixed lab of 3+ NOSes: each vendor lab pairs the vendor node with FRR, and the 30-node lab (angle 3) is FRR only. One lab with three different vendor images at once was not run: **not covered**.
- VM NOSes (Junos, NX-OS, MikroTik) need `record --wait 240` or more (420-480 for Junos and NX-OS); the default 45 s records only guards. Now documented (e741c7e).
- Times per run: FRR, SR Linux, SONiC, cEOS 1-2 min; RouterOS 1.5 min plus 4 min record; Junos 8-14 min; NX-OS 7-12 min.
- On b61c325 Junos and NX-OS must-fail runs were invalid (guards-only baseline); the acb546b reruns with a long wait are the ones in the table.

## Angle 2: end user, clean machine

Clean clone, candidate wheel in a fresh venv, README, getting-started, your-lab and tutorial word for word, then the common mistakes.
Missing image, no Docker permission, config typo, wrong path: clear message, exit 2, no lab left.
No KVM for a VM NOS: refused up front, exit 2 (F3, checked live). A stopped node container ends the run at once, naming the container and its last log lines (checked live, 69 s).
A lab lock file left by another user or sudo is no longer an internal error (F2, checked live).
Not covered: a separate clean OS install (the clean clone ran on the same host).

## Angle 3: integrator

- GitHub Action: run and verify modes, shallow checkout, stale reports, committed verdict file, inputs of the other mode, contradictory reports, actionlint and the repo's Action tests. A real fork PR, PR comments and a hosted runner: **not covered** (no owner credentials).
- GitLab component and the other CI templates: unit tests and a shell harness only. A real GitLab run: **not covered**.
- 30-node FRR topology: deploy and boot 113-148 s, record of 1887 checks 467 s, good run 387 s PASS 1887/0, broken change FAIL 56/1831 in 417 s. (The first attempt with two spine ASes was non-deterministic: harness error, not product.)
- Brownfield-sized FRR policy: record 117 checks; good PASS, leak and swapped policy FAIL, cosmetic change PASS (about 1 min each).
- Two runs at once: different labs run side by side; the same lab name is refused with exit 2 and a clear message.
- JSON report and MCP result validated against the published schemas by a script; every status matches the exit code.

## Angle 4: AI agent via MCP (scripted smoke only)

dry_run, start_run/get_result, run_checks, record_baseline, validate, check_types, verify_change, and one leaky change rejected, over a stdio client; result sizes measured in tokens.
`verify_change` on the agent-demo lab came back INCONCLUSIVE (an FRR graceful-restart stale path for edge1's 0.0.0.0/0 from up1 prevents a stable snapshot in 300 s). That is fail-safe, not a false pass (M-8 below).
`claude mcp add` and Codespaces: **not covered**.

## Angle 5: adversary

Two isolated subagent rounds tried to produce false passes; each candidate was confirmed live or by a fresh verifier (findings B-1..B-6, A-1..A-7).
No adversary round was run on b03cb7a (budget): **not covered**.

## Findings

| ID | Severity | What | Status |
|---|---|---|---|
| B-1 | BLOCKER | A prefix without a length (`0.0.0.0`) was read as /32; a default-route guard could never fail | fixed b0d49b7; RT-0029..RT-0035 |
| B-2, B-3 | BLOCKER | bgp_prefixes on an IPv6 neighbor, or a family the session doesn't carry, passed on a 0 nobody counted | fixed f798555, a79fedd; RT-0036 |
| B-4 | BLOCKER | record accepted a baseline with a session down | fixed f798555 (INCOMPLETE BASELINE) |
| B-5 | BLOCKER | injected routes that never left the injector passed a scenario | fixed 1a25175, 3ac7fe4 (live pfxSnt captures) |
| B-6 | BLOCKER | verify `with:` pin explained a path from an undeclared peer | fixed 20dd04f; tests/test_acceptance_041.py |
| A-1..A-7 | MAJOR | driver false passes: EOS unmapped routeType, FRR path without AS-path, SR Linux up family without counters, route not in FIB, AS-loop routes, Junos no-install and stale GR | fixed fbc52fc, 82eb7ad, cf3d37a; A-4 restarter-mode live: **not covered** here (Junos session) |
| T-B1 | BLOCKER | Action refused a shallow checkout | fixed 977a11d |
| T-B2 | MAJOR | invalid YAML snippet in github-action.md | fixed 6b63121, 977a11d |
| M1, M4 | BLOCKER | stale or committed verdict reached the artifact; contradictory report accepted | fixed 977a11d |
| M2, M3, M5, M6, M7 | MAJOR/MINOR | other-mode inputs, settle default, GitLab check-edit guard | fixed 977a11d |
| F1 | MAJOR | tutorial output differed from real 0.4.1 output | fixed 0157689 |
| F2 | MAJOR | lock file left by another user: internal error | fixed c441b42 (test 9e8b5dc); live OK |
| F3 | BLOCKER | stopped node container didn't end the run; no KVM preflight | fixed c441b42; live OK |
| R-1 | BLOCKER | `record` wrote ipv6-unicast checks RouterOS refuses (record then run was exit 2) | fixed e741c7e (test d216272); live OK on b03cb7a |
| docs | MINOR | graceful-restart contradiction, config.md vs compatibility.md | fixed 3176ef3 |

## Not covered (explicit)

Real fork PR, PR comment and hosted runner for the Action; a real GitLab run; `claude mcp add`; Codespaces; a mixed lab with three vendor images at once;
a separate clean OS install; A-4 restarter-mode live; an adversary round on the final candidate.
SR Linux, SONiC and cEOS live runs were on b61c325 and Junos and NX-OS on acb546b, not repeated on b03cb7a. The changes since touch `record.py`, `faults.py` and `drivers/__init__.py`; the FRR and RouterOS reruns exercise them.

## MINORs for triage

- M-8: `verify_change` on agent-demo is INCONCLUSIVE because of a stale GR path (fail-safe; needs a longer settle or a doc note).
- M-9: after a degraded (slow-host) run, destroy left an exited node container.
- M-10: SR Linux: `route ... present: false` for an AS-loop path errors (driver does not read the reason); fail-closed.
- VM NOSes: `record` without `--wait` records guards only (documented now).
