# Interop stress test: scenarios (L1 mixed-5, L2 iBGP / route reflector)

Pre-registered: every check's expected verdict is in `L1/oracle.yml`, `L1/s8/oracle.yml` and `L2/oracle.yml`
(generated from the hand-written `oracle.src.yml` next to each), committed before any lab booted. Each overlay in
`L1/overlays.yml`, `L1/s8/overlays.yml` and `L2/overlays.yml` is one change to the baseline and must flip exactly the
checks its oracle names; any other flip is a finding.

Layout: `<lab>/base/` (topology, configs, `netdryrun.yml`), `<lab>/overlays.yml` (edits for a fresh deploy, typed
apply/revert commands for the running lab, raw probes), `tools/` (build, oracle expansion, lab driver, comparison),
`results/` (JSON reports, gitignored; `results/SUMMARY.md` is committed).

## Labs

| Lab | Nodes | Purpose |
|---|---|---|
| L1 | j1 Junos 65001, s1 SR Linux 65002, a1 cEOS 65003 (two parallel sessions), n1 SONiC 65004, f1 FRR 65005 transit, f2 FRR 65006 upstream (203 prefixes incl. a default) | every 0.4 driver reading another vendor's routes |
| L1s8 | L1 without j1 | config rejected at load (S8), fast to boot |
| L2 | r1 SR Linux route reflector, clients c1 cEOS, c2 Junos, c3 FRR (AS 65100); e1 FRR edge 65200 | iBGP attributes, reflection, next-hop resolution |

## Scenarios and where they run

| # | Scenario | L1 | L2 |
|---|---|---|---|
| S0 | Baseline, read on both ends (sessions, exact counts, routes, pings) | C01-C46, C82-C87; fresh x3 | D01-D26, D46-D48; fresh x3 |
| S1 | Leak; every other NOS's guard must fail | M01 (default from the transit), M02 (Junos more-specific) | N01 (default reflected to every client) |
| S2 | Attributes set by one vendor, read on every other | C47-C67; M03 (large community), M04 (no-export), M05 (prepend) | D27-D39; N02 (local-pref), N08 (large community) |
| S3 | IPv6 global next hops, v6 counts, v6 count on a v4-only session | C03/C04/C07/C08, C18/C20/C25/C27, C33/C36/C87, T05 | - |
| S4 | Import policy rejects: `present: false` passes, `route` fails, count drops | M06 (Junos), M07 (SR Linux), M08 (cEOS) with probes R01-R03 | - |
| S5 | Next hop unreachable: received, not active, no best path, still counted | M09 (third-party next hop to all four spokes) | N03 (reflector gets an unresolvable next hop) |
| S6 | Sessions broken in vendor-specific ways | M10 (Junos prefix limit), M11 (SR Linux peer AS), M12 (cEOS admin shut, ECMP sibling stays up), M13 (MD5, FRR/SONiC) | N04 (Junos AS typo), N05 (cEOS admin shut), N06 (Junos prefix limit), N07 (MD5) |
| S7 | Timing | not run (see below) | not run |
| S8 | Config rejected on load | S8a SR Linux, S8b cEOS, S8c FRR, S8d SONiC setup | - |
| S9 | VRF | not run (see below) | not run |
| S10 | ECMP best vs non-best path | C77, T06; M12 | - |
| S11 | `verify` mode with mixed-vendor neighbours | run last if lab time allows | - |
| S12 | Scale (200, then 2,000 prefixes) | C23-C30; M14 | - |

Traps (expected to FAIL in the baseline): T01-T09 (L1), U01-U05 (L2): MED 0 asserted where the MED is missing or
non-zero, the non-best ECMP next hop, a wrong large community, a mis-anchored regex, a wrong local-pref, the FRR
client's non-best eBGP next hop.

## Determinism and the reapply path

- Fresh deploys x3: L1 baseline, M01, M02, M03, M04; L2 baseline, N01, N08 (mutants whose expected failures are
  post-convergence or attribute checks on the non-FRR drivers: where a false pass would come from).
- M09 and N03 (S5) run reapply x3 plus one fresh deploy instead: their expected failures include positive checks,
  which wait the full fresh-deploy timeout (1,200 s, for cJunosEvolved) before failing.
- Every other overlay: applied on the running lab, `netdryrun check`, reverted, and the baseline checked again.
- One fresh deploy per lab confirms the reapply path: M06 (L1), N03 (L2).
- Waits after a change on the running lab: 45 s; 150 s after a session-breaking change (graceful-restart stale timer).

## Model review (ChatGPT and Grok, 2026-10-30)

Brief and answers: `research/interop/model-review/` in the business repository. Additions merged:

| Addition | Suggested by | What changed |
|---|---|---|
| A MED shown as 0 when none was received is a false pass on whichever NOS does it, FRR/SONiC included | Grok, ChatGPT | Already covered: T01-T04 (L1) and U01-U03 (L2) include FRR and SONiC as controls; kept |
| Junos may replace or ignore a third-party next hop on a single-hop eBGP session, and a static discard default may resolve it | Grok | M09's oracle marks these as NOS assumptions; the probe (`show route ... extensive`) decides which side a mismatch is on |
| SONiC's FRR template may enable graceful restart, leaving stale paths after a session break on a running lab | Grok | Session-breaking overlays wait 150 s before `check`; known GR limit on SR Linux/EOS/SONiC noted in the report |
| Junos prefix-limit teardown stays idle until cleared, stacking onto the next overlay | Grok | Teardown uses `idle-timeout forever` (deterministic) and the revert clears the session; the baseline is checked again after every revert |
| An empty AS path is printed with an origin code (`I`/`i`) | Grok | Already covered: D36-D39 assert `as_path: ""` on cEOS, FRR, SR Linux and Junos |
| A blind reviewer given the same assumptions confirms a wrong oracle | Grok, ChatGPT | The independent reviewer gets configs and checks only, no oracle and no reasoning |
| Compare fresh and reapplied results for every state-changing mutant | ChatGPT | Partly: one fresh confirm per lab plus fresh x3 on the leak/attribute mutants; the rest is a stated limit |

Not merged, with the reason: FRR does not send communities without `send-community` (FRR has sent standard, extended
and large communities by default since 7.x; C48/C49 show it either way); M02 does not leak past the aggregate (the /25
is 172.17.1.128/25, outside 172.16.0.0/16); contributors drop the as-set aggregate (accounted for: only n1 is a
contributor among the spokes, and its count excludes it).

## Not run

- S7 timing (MRAI races, a link flap inside the settle window, a late-booting Junos): needs fault timing the overlays
  can't express; EOS `out-delay` is a documented 0.4 limit (fix scheduled 0.4.1).
- S9 VRF: the examples have no multi-vendor VRF configs to copy, and the brief forbids inventing vendor syntax.
- S8 on Junos: the reference says the cJunosEvolved config load is not verified yet (documented limit).
- L3 (NX-OS, MikroTik): not in this run's scope.
