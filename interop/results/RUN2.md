# Interop run 2 on 3ca6145: report (2026-10-31)

`ndr/interop` merged with `ndr/release-0.4.0` at 3ca6145 (fixes for IOP-1/2/3). Lab lock owner "interop rerun on
3ca6145", taken 04:03 and released 12:33 (+07:00). Every `ndr-interop-*` lab destroyed.

Everything is pre-registered: `interop/L1/oracle.yml`, `L1/s8/oracle.yml`, `L2/oracle.yml`, `L1/s11/oracle.yml`,
`ecmp/oracle.yml`, and the expectations in `L2/extra/iop6-live.yml`. Per-run table: `results/SUMMARY.md`. Raw JSON
reports, probes and logs: `results/L1`, `results/L1s8`, `results/L2` (gitignored).

## Findings

### BLOCKER IOP-6: SR Linux driver counts a route rejected by import policy as a received path (false pass on `route active: false`)

- **Oracle line:**
  - L1 M07 `R02 s1 bgp_route 192.168.6.0/24 present: false` → pass: "rejected by import policy: not in the local RIB".
  - Live check `X1` in `L2/extra/iop6-live.yml` → fail.
- **Netdryrun said:**
  - M07 R02: `[FAIL] unexpectedly in the BGP table (1 path(s); as-path '65005 65006', next hop 10.1.2.2 ...)`.
  - L2 r1 X1 `route 203.0.113.0/24 protocol: bgp active: false`: **`[PASS] present via bgp (not selected)`**. This is
    the false pass.
- **Evidence:**
  - SR Linux keeps the rejected route in `bgp-rib ... local-rib`: `"valid-route": false, "best-route": false,
    "invalid-reason": {"rejected-route": true}`.
  - The neighbor summary shows `ipv4-unicast [207/206/1]`, so the count is right. The driver's `_bgp_learned` only
    tests `origin-protocol`.
  - FRR, EOS and Junos keep no such path: M06 (Junos) and M08 (cEOS) R01 and R03 passed as the oracle said.
- **False-pass paths, answering the coordinator:**
  - `route ... active: false` passes (shown live on r1 and on the captured shape).
  - Plain `route`, best-path and attribute `bgp_route` checks fail correctly: there is no best path.
  - `bgp_prefixes min:` is not affected: received − rejected = 206 live.
- **Also:** the failure reason for a best-path check on such a route says "none is best (next hop unreachable?)",
  which is wrong here (it was rejected by policy).
- **Tests:** `tests/test_interop_04_run2.py`:
  - `test_srl_route_rejected_by_import_policy_is_not_a_received_path`
  - `..._is_absent_from_route_checks`
  - `..._does_not_satisfy_active_false`
  - Fixtures: `srl_rib_rejected.txt` and `srl_attr_set_rejected.txt`.

### BLOCKER IOP-7: Junos prefix count drops a received route whose next hop is unusable (false pass on `max`/`exact`)

- **Oracle line:** L1 M09 `C24 j1 count from f1 exact: 206` → pass: "the route passed import policy: accepted".
- **Netdryrun said:** `[FAIL] 205 ipv4-unicast prefixes accepted`. This was the same in 4 of 4 M09 runs (1 fresh,
  3 reapply).
- **Evidence:** Junos `show bgp neighbor`: Received 206, Accepted 205, Active 205. The route is `State: <Hidden Ext>`,
  "Hidden reason: Protocol nexthop is not on the interface". The junos driver reads `accepted-prefix-count`. SR Linux
  (C26 207), EOS (C28/C29 207) and FRR/SONiC (C30 206) kept their full counts in the same overlay.
- **False-pass path:** on the captured shape, `bgp_prefixes max: 205` and `exact: 205` on j1 **pass**, while the
  reference count (received − rejected by import policy = 206) fails them. A count guard misses an extra received
  route whose next hop Junos can't use. A `present: false` guard on that prefix still catches it (R01 failed in M09).
- **Tests:**
  - `test_junos_count_keeps_a_received_route_with_an_unusable_next_hop`
  - `test_junos_undercount_does_not_pass_an_upper_bound_the_reference_count_breaks`
  - Fixture: `junos_bgp_neighbor_hidden_nexthop.txt`.

### MAJOR IOP-8: verify refuses any FRR snapshot where a node has multipath paths to a prefix it advertises

- **Oracle line:**
  - S11 (`L1/s11/oracle.yml`): `failed` (exit 1, undeclared changes plus failed guards). It must never be
    `matched`/`no_change`.
  - FRR-only reproduction (`interop/ecmp/oracle.yml`): `matched` (exit 0).
- **Netdryrun said:** both runs gave `ERROR: NO VERDICT` (exit 2): "unreadable snapshot: f1|fb: unexpected output
  from `show bgp ipv4 unicast neighbors ... advertised-routes detail json`: 192.168.3.1/32: several paths without
  addpathTxId; verify can't tell them apart".
- **Evidence:** fb holds two equal eBGP paths to 192.168.3.1/32 (two parallel sessions). FRR's advertised-routes JSON
  lists both (`pathCount: 2`, one with `bestpath.overall`) with no `addpathTxId`, even though without add-path the
  neighbor receives only the best path. It reproduces on a 3-node FRR-only lab, which is verify's supported case.
- **Severity:** MAJOR, not BLOCKER: verify fails closed and never approves. But it can't run on any lab where an FRR
  node has ECMP paths to an advertised prefix. S11's intended question (the leak plus guards on mixed-vendor
  neighbours) stayed unanswered because of it.
- **Test:** `test_verify_adj_out_with_multipath_reads_the_advertised_best_path`, with fixture
  `frr_adj_out_multipath.txt` (hostnames replaced).

### Still open from run 1

- **MINOR IOP-5 (hold judged on one sample).** 790 of 2,176 held post-convergence checks in run 2 report
  `held ..s, 1 samples`. Better than run 1 (all of them), but not fixed.
- **MAJOR IOP-4 (provisional: one transient SR Linux CLI error fails a check).** It did not recur: no check in any of
  the 70 run-2 reports ended on an error. The test from run 1 stays as the coordinator left it.

### Fixes verified (IOP-1, IOP-2, IOP-3)

- **IOP-1 (Junos MED):**
  - T01 `j1 med: 0` on a route with no MED fails, "MED is not set", in all 37 L1 reports.
  - L2 U01 (c2) fails in all 25 L2 reports.
  - C78 (`med: 0` on a real MED 0, Junos) still passes.
- **IOP-2 (EOS `med: 0`):** T02, C80 (L1) and U02 (L2) are refused before deploy: exit 2, no container created (0/0),
  and `validate` also exits 2. The message: "med: 0 can't be checked on eos: EOS output cannot tell MED 0 from no MED".
- **IOP-3 (EOS AS_SET):** C67 `as_path "65005 {65004,65006}"` on cEOS passes in every L1 report where the oracle expects it (35 of 37; it fails only in M12 and M13, as the oracle says), as on Junos (C65) and
  SR Linux (C66).

## Oracle lines that were wrong (NOS assumptions, not Netdryrun)

| Line | What the oracle assumed | What the NOS did (evidence) | Netdryrun |
|---|---|---|---|
| C77/T06 (corrected before run 2, commit a22603a) | cEOS ECMP best = lowest peer address | cEOS keeps the first-received path as ECMP head ("Not best: ECMP-Fast configured") | read cEOS's best correctly; the pair rule (exactly one passes) held in every run |
| M09 C89, C92 (s1) | the unreachable third-party next hop makes the route unusable on SR Linux | SR Linux resolves 10.99.99.99 through its static blackhole default: `<Best,Valid,Used>`, "Invalid Reason: None" (Grok predicted this in the model review) | read SR Linux correctly |
| N03 D15 (c2 count 4) | an SR Linux reflector does not reflect a path it can't resolve | r1 shows P1 `<>`, "Invalid Reason: Next_hop_unresolved", yet "advertised to: [10.2.2.2, 10.2.3.2]", so c2 received 5 | read Junos correctly (count 5; P1 hidden, not active) |

## Determinism

| | Fresh deploys | Reapply runs | Same verdicts every time |
|---|---|---|---|
| L1 baseline | 3 | 4 (after each session-break revert) | yes (0 mismatches in all 7) |
| L1 M01, M02, M03, M04 | 3 each | 1 each | yes |
| L1 M06 (reapply confirm) | 1 | 1 | yes |
| L1 M09 | 1 | 3 | yes (same 3 lines each time) |
| L2 baseline | 3 | 5 | yes |
| L2 N01, N08 | 3 each | 1 each | yes |
| L2 N03 (reapply confirm) | 1 | 3 | yes (same D15 line each time) |

Fresh and reapply verdicts matched for every overlay run both ways. cJunosEvolved took 182–766 s to answer per boot;
no verdict depended on it.

## Verdict table (oracle vs actual)

70 Netdryrun reports (5,187 check verdicts) plus 2 verify runs and 1 live IOP-6 probe. 61 reports match the oracle
exactly. The 9 that don't are listed below, all classified above. Full table: `results/SUMMARY.md`.

| Variant | Runs | Mismatch | Classification |
|---|---|---|---|
| L1 base, M01–M06, M08, M10–M14 | 33 | none | |
| L1 M07 | 1 | R02 (fail, oracle pass) | BLOCKER IOP-6 |
| L1 M09 | 4 | C24 (fail); C89, C92 (pass) | C24: BLOCKER IOP-7. C89/C92: oracle wrong (SR Linux resolves the next hop) |
| L1 refusals T02, C80 | 2 | none (exit 2, no deploy) | IOP-2 fix verified |
| L1s8 base, S8a–S8d | 5 | none | S8a: SR Linux deploy failed on the bad line. S8b: cEOS "line 33 ... (Invalid input)". S8c: FRR "line 231 ... (Unknown command)". S8d: SONiC setup failed. All exit 2 |
| L2 base, N01, N02, N04–N08 | 17 | none | |
| L2 N03 | 4 | D15 (pass, oracle fail) | oracle wrong (SR Linux reflects its unresolved path) |
| L2 refusal U02 | 1 | none | IOP-2 fix verified |
| S11 verify (L1 base → M01) | 1 | error (oracle failed) | MAJOR IOP-8 |
| FRR-only ECMP verify | 1 | error (oracle matched) | MAJOR IOP-8 |
| L2 live IOP-6 probe | 1 | X1 pass (expected fail) | BLOCKER IOP-6 |

## Harness faults (mine, corrected; no Netdryrun verdict depends on them)

- **The first reapply step deleted part of the running lab's containerlab dir** (cEOS flash), through `lab.py`
  rebuilding the base dir. The check then errored on a1's startup-config. The lab was destroyed and redeployed, and
  the builder now keeps `clab-*` dirs (commit 0ecd79f). Results are kept in `results/L1/harness-fault/`.
- **cEOS needs the value on `no set as-path prepend` / `no set large-community`.** The first M05 apply did not apply.
  The syntax is fixed and the rerun of M05 matches.
- **The first S11 launch never ran** (a quoting error, nothing deployed). Relaunched.
- **T05 (positive, expected fail) waited the 1,200 s fresh timeout on every L1 run.** It now has `timeout: 60`; its
  verdict can't change.

## Planned vs run

| Item | Planned | Run |
|---|---|---|
| L1 baseline fresh | 3 | 3 |
| L1 mutants M01–M14 | 14 | 14 (reapply), plus fresh x3 for M01–M04 and fresh x1 for M06 and M09; M09 reapply x3 |
| L1s8 (config rejected) | base + 4 | 5 |
| L2 baseline fresh | 3 | 3 |
| L2 mutants N01–N08 | 8 | 8 (reapply), plus fresh x3 for N01/N08 and fresh x1 for N03; N03 reapply x3 |
| `med: 0` refusals | 3 | 3 |
| S11 verify | 1 if time | 1, plus an FRR-only reproduction; no verdict (IOP-8) |

Not run: S7 timing, S9 VRF and S8 on Junos (reasons in `interop/SCENARIOS.md`), and L3 (not in scope).
