# Review: 0.4.3 public release text (release/0.4.3-surfaces, a7419f4..db1a58e)

- Reviewer session: rev-relprep. It wrote no code, test, fixture, record, evidence or allowlist in this change; this file is its only commit.

**Verdict: APPROVE WITH FIXES.** Every "fixed in 0.4.3" claim is backed by an oracle that fails on v0.4.2 and passes at
HEAD. Facts are in sync, and the strict site build is clean. Two public statements are false as written (findings 1 and
2). The rest are wording, precision and stale-evidence fixes. None of them hides a false pass.

Reviewed in a fresh clone of github.com/netdryrun/Netdryrun at db1a58e (bundle head), WSL Ubuntu-ndr, nice 19, no lab.

## What was run

| Check | Result |
|---|---|
| Oracles FP-043-EOSAGG, EOSNONBGP, FRRIMPORTCHK, SRLEVPNVRF, UNNSESSCHK at HEAD | 65 passed |
| Same oracles against v0.4.2's `src` (`NDR_TEST_SRC`, HEAD's tests) | 37, 4, 11, 3 and 10 failed: every oracle fails on 0.4.2. The failures are real verdicts, for example case 18 `status passed` on a stuck boot and SR Linux EVPN `present: false` passed with the route imported |
| `scripts/sync_facts.py --check` | in sync, version 0.4.3, 0 problems |
| `website/build_llms_full.py` | regenerated file identical to the committed one |
| `mkdocs build --strict` (~/.venvs/mkdocs312, mkdocs 1.6.1) | built, no warnings |
| tests: known_false_passes, release_gate_retired, docs_claims, docs_front_matter, surfaces_agree*, capabilities | 375 passed |
| PyYAML exclusion | `pyyaml>=6.0,!=6.0.4` in pyproject; `tests/test_pyyaml_merge_guard_043.py` present |

## Findings

### 1. Medium: the 0.4.3 post says every 0.4.2 limit is still open and that the roadmap lists them all

`website/docs/news/posts/release-0.4.3.md:30`. 0.4.2's "not fixed" list included cases 1 and 2 and RT-0085, which 0.4.3
fixes. The roadmap (`roadmap.md:28`) lists only a subset: the AS-loop path, the `::/0` guard, add-path and
graceful-restart on other drivers, SR Linux labeled-unicast, `link_down` and `ping` without `source` are missing. The
CHANGELOG lists them all.

Replace with:

> - The other limits 0.4.2 listed as not fixed are still open, among them the node's own exported prefix on SR Linux and Junos, the EOS `out-delay`, the NX-OS FIB state, and a route that takes one advertisement interval per hop. The [CHANGELOG](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) lists them all.

### 2. Medium: the 0.4.1 advisory's evidence line is now false

`advisories/0.4.1-known-false-passes/README.md:8-9`: "the others were confirmed against recorded router output (EOS from
live fixtures), not yet through a Netdryrun live run." Line 37 of the same file says `netdryrun check` passed case 2 on
a live SR Linux 26.7.2 lab, and line 29 says case 1 was reproduced live on cEOS 4.36.3M.

Replace with:

> reported them. **Evidence:** RT-0053 was reproduced in the pinned FRR image; the others were first confirmed against recorded
> router output (EOS from live fixtures). While they were fixed for 0.4.3, case 1 was reproduced on a live cEOS 4.36.3M and
> case 2 through `netdryrun check` on a live SR Linux 26.7.2 lab. We publish them now to be safe. 0.4.1

### 3. Medium: the trust page repeats the stale evidence

`website/docs/trust.md:58`: "Each was rated real by a fresh verifier from the code and the NOS's captured output, not yet
reproduced in a Netdryrun lab run."

Replace with:

> Each was rated real by a fresh verifier from the code and the NOS's captured output; the Arista EOS and SR Linux EVPN cases were later reproduced on live routers while they were fixed for 0.4.3.

Rerun `tests/test_known_false_passes.py` afterwards, because it pins the published text.

### 4. Low: "two false passes found since" in the 0.4.3 post

`release-0.4.3.md:12`. RT-0085 (the EOS aggregate read as `aggregate`) was listed as a known limit in the 0.4.2 notes. Of
the two items, only RT-0086 and RT-0084 were found since.

Replace with:

> 0.4.3 is a fix release. It closes the two cases of the 0.4.1 advisory that 0.4.2 left open and two more false passes: the node's own BGP aggregate on Arista EOS, a 0.4.2 known limit that proved wider, and FRR's import check at boot, found since. Checks on FRR can also name a BGP-unnumbered session by its interface.

### 5. Low: the 0.4.3 post's description reads as "fixes ... and checks"

`release-0.4.3.md:5`. Replace with:

> description: "0.4.3 fixes the two open cases of the 0.4.1 advisory, the node's own BGP aggregate on Arista EOS and FRR's import check at boot. Checks on FRR can now name a BGP-unnumbered session by its interface."

### 6. Low: the "otherwise" in the import-check bullet is ambiguous

`release-0.4.3.md:19`: "On a lab the run deployed, a stuck router gets one reset command and is read again; otherwise the
run is an error, never a pass." Under `check`, and when the router stays stuck after the reset, the run is an error.

Replace with:

> On a lab the run deployed, a stuck router gets one reset command and must then read clean. On a lab the run didn't deploy (`check`), or if the router stays stuck, the run is an error, never a pass.

### 7. Low: the 0.4.2 post says everything "passed"

`release-0.4.2.md:26`. `releases/0.4.2/GATE.md` Layer 5 shows "3 ACCEPTED, 63 PASS". The accepted items are check-pack
verification, the 20-node scale test and the Docker-restart chaos run.

Replace with:

> How it was tested: before publishing, static checks, the unit suite on every supported Python, mutation testing, live labs on the built package and the scripted acceptance round passed on the release commit. Three live items that are optional or not scripted yet were accepted, and the [gate report](https://github.com/netdryrun/Netdryrun/blob/main/releases/0.4.2/GATE.md) lists them. After publishing, one outside listing still named an older version; the gate report records that too.

### 8. Low: the roadmap says "One new limit"

`roadmap.md:16`. 0.4.3 adds two: the SR Linux EVPN ip-vrf case, and the import-check reset, which can briefly announce an
unbacked prefix. The reset is also not run on a live SONiC lab. The post and the CHANGELOG list both.

Replace the tail of the row with:

> New limits: `bgp_route` in an SR Linux EVPN ip-vrf without PE-CE BGP is not evaluated (fail-closed), and the import-check reset can briefly announce an unbacked prefix to a peer |

### 9. Low, depends on the gate: the corpus text for case 18

`website/docs/corpus.md:192`: "unchanged until the corpus is rerun on the 0.4.3 release candidate". Strict static
layer G3 requires fresh corpus results on the release's verdict code. If the 0.4.3 gate reruns the corpus, update this
sentence, case 18's "nondeterministic, excluded" note and "Provenance: both ran on Netdryrun 0.4.2" in README.md:35 and
index.md:155 from the new results. If it doesn't rerun the corpus, write:

> The case's recorded results above are from 0.4.2; the corpus hasn't been rerun on 0.4.3 yet.

### 10. Gap to close after the gate: the 0.4.3 post has no "How it was tested" line

The brief expected the 0.4.3 post to link `releases/0.4.3`. It doesn't. The post has no test paragraph or gate-report
link, while the 0.4.2 post does. `releases/0.4.3/` holds only probe logs so far. After the gate report exists, add the
following before the `[Full changelog]` line:

> How it was tested: the release gate (static checks, the unit suite on every supported Python, mutation testing, live labs on the built package and the scripted acceptance round) ran on the release commit; the [gate report](https://github.com/netdryrun/Netdryrun/blob/main/releases/0.4.3/GATE.md) lists each result.

`releases/tag/v0.4.3` (post line 36, roadmap line 16) resolves only after the tag is pushed. That is expected.

### 11. Low: date check

The CHANGELOG, the post and the roadmap say 2026-11-23. At review time it was 2026-11-22 17:18 UTC (23 November in
UTC+7). Earlier releases match the UTC date of the PyPI upload (0.4.2: Layer 7 at 2026-11-21 11:03 UTC). Publish on 23
November UTC, or move the date to the actual upload day.

### 12. Source string (report only, not changed): record.py:503

`src/netdryrun/record.py:503` prints, in 0.4.3 itself: "Until 0.4.3, check that path's AS path on the peer that sends
it". That is wrong in the shipped 0.4.3: reading the empty path is not in 0.4.3. Proposed text:

> "check of its attributes would pass a changed path. On SR Linux this version can't check it: check that path's AS "
> "path on the peer that sends it"

No test pins the current string (`git grep "Until 0.4.3" tests website` returns nothing).

## Checked and fine

- Voice: the added text uses "Netdryrun" or "our" and names no person, employer or client. It has no AI mention, no
  "eliminates", "guarantees" or "ensures", and no dated promises. The roadmap says "Direction, not a commitment".
  "Planned for a later release" replaces every "planned for 0.4.3" in public docs. The leftovers are internal:
  `fastfix/plan-0.4.3.md`, `fastfix/oracle-specs/RT-S01.md:71` and a test fixture string.
- Every 0.4.3 Fixed item and each oracle-backed claim matches the CHANGELOG and the oracle's ORACLE.yml: the EOS RIB
  read, the EOS aggregate as `bgp` with `protocol: aggregate` refused, SR Linux EVPN imported type-5, FRR import check,
  unnumbered sessions with other drivers refusing with exit 2, and stricter replay. The limits are stated honestly:
  SR Linux EVPN not evaluated, the reset not seen in 3 live tries, SONiC not run live, and the unresolved static on EOS.
- Version strings: 0.4.3 in pyproject, `__init__`, server.json, capabilities.json, llms.txt, Action refs and the trust
  scope. There is no stray current-version 0.4.2.
- known_false_passes.yml record fields now point at "CHANGELOG.md (0.4.3, Fixed)". There is no `#unreleased` anchor
  left anywhere.
