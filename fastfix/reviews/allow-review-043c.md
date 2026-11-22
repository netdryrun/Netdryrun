# Allowlist review: 0.4.3 FRR unnumbered new reads and the gate at its HEAD blob

- Reviewer session: allow-review-043c. It wrote no code, test, fixture, record, evidence or allowlist in this
  change; this file is its only commit.
- Reviewed: allowlist commit 1055792 (session allow-043c) on main a7419f4, against the published v0.4.2
  (61cd95de8b54), in a fresh clone in WSL Ubuntu-ndr, shared venv, `PYTHONPATH=src`, nice 19, no lab.
- Files: `fastfix/allow/0.4.3-gate.yml`, `fastfix/allow/0.4.3-rest.yml`, `fastfix/allow/0.4.3-unnsess-newread.yml`.
- Verdict: **APPROVE** every entry in the three files. No entry is rejected.

## 1. Gate-file entries (`0.4.3-gate.yml`, and `surfaces_agree.py` in `0.4.3-rest.yml`)

Blobs at the candidate match the entries: fastfix_gate.py a035930cfb1f, release_gate.py 7fbeececd3ab,
fastfix_cmdlog.py f8d93ecbe443, tests/fakes.py 9daf357ee940, surfaces_agree.py 15990540b1e6. Since the allowlist
that last named them (62cea1b, and 268a7d5 for surfaces_agree.py), the only commit on any gate file is 01e0a73, on
scripts/fastfix_gate.py. The release_gate.py, fastfix_cmdlog.py and tests/fakes.py entries are unchanged from that
reviewed allowlist and still name the HEAD blobs.

**scripts/fastfix_gate.py, 099a76ecf215..a035930cfb1f (01e0a73 only).** One rule changes, in `allow_entries`, plus
the new helper `live_capture` and a longer hint in one problem message. Read line by line:

- Every condition of the old `bad` list is still there: code paths under the not-evidence prefixes, a missing file,
  the flipped source itself, and `.py` other than the flipped test.
- The two conditions "under tests/oracles/" and "not changed in this change" are lifted for one path only: the
  flipped test's own file. And only when all of these hold (`as_run`):
  - the entry is `kind: new-read`;
  - its source is `fixtures`;
  - its own test is cited;
  - another cited file passes `live_capture`.
- `live_capture` accepts only a file that is:
  - under tests/fixtures/;
  - not `.py`, not SOURCES.yml, not in `__pycache__`;
  - changed in this change and present at the candidate;
  - filed under `kind: live-capture` with a non-empty source, by its exact name or by a pattern with a literal stem.
  An unreadable SOURCES.yml names nothing.
- Untouched: the reviewer-session rule, the separation rule, the literal-key rule, stale and dead entries, the kind
  match, and live routing (`new_read_entries`).

So the gate refuses everything it refused at 099a76ecf215 except one new evidence shape: an oracle-folder or
unchanged test cited by a new-read entry beside a changed, labelled live capture. Before, the gate refused that shape
outright. That made a real, stricter new read on such a test impossible to clear, and the only workaround was a
cosmetic edit to the test.

I judge this acceptable as a deliberate relaxation, and I'm saying so explicitly. It is not a tightening. It is
bounded by:
- the capture;
- a fresh reviewer, a commit of their own;
- live runs on every OS the read touches (here `*`).
The adversary review in fastfix/reviews/adv-newread-evidence.md approved it.

Its open weakness is that the gate trusts the SOURCES.yml label and doesn't tie the capture to the logged command.
For these entries I checked that by hand (section 3).

The new-read gate tests pass at HEAD: 64 selected in tests/test_fastfix_gate.py.

**The earlier blobs.** The full diff against v0.4.2 was reviewed and approved by the earlier sessions the entries
name. I re-checked only that nothing else moved.

**scripts/surfaces_agree.py.** This change is genuinely looser, by design and for one surface only. A stale or
unreadable LobeHub listing becomes a printed WARN. GitHub, PyPI, the MCP Registry entry and llms.txt still block and
still fail closed. Nothing touches a verdict. The adv-043-rest record covers it. I accept it as already reviewed.
That WARN is read only by hand, which is a known gap to close separately.

## 2. The genuine failure: FP-042-UNNSESS `test_every_unnumbered_neighbor_is_recorded_or_a_named_gap`

I ran v0.4.2's own tests from a v0.4.2 worktree (its conftest and fixtures). The files were tests/oracles/FP-042-UNNSESS,
FP-042-FRR102 and FP-042-UNNUMBERED, plus tests/test_oracle_guards_fp_042_unnsess.py.

- On v0.4.2's src: 13 passed.
- On the candidate's src: 12 passed, 1 failed. `netdryrun.__file__` confirmed the candidate's src was the one loaded.
  - The failure is at line 133, `assert gaps`: "record exits 0 with sessions it didn't record".
  - The assertion before it (every neighbour recorded or a named gap) holds.

I ran the candidate's `record` on v0.4.2's CapturedLab, wrapped to log every exec:

- It sends `vtysh -c show bgp ipv4 unicast neighbors <ethN> routes json`, five times: leaf01 eth1 and eth2, and
  spine01 eth1, eth2 and eth3. The fake answers each one rc=1.
- It writes a `bgp_session` check for all five sessions.
- It writes `bgp_prefixes` checks with exact counts: ipv4 4/4/2/2/2, and ipv6 0 each. Each comes with the warning
  "recorded as exactly N prefixes, not a range, because the prefixes it sends could not be read".
- v0.4.2 wrote no check for any of these sessions.

So the change is stricter. An unanswered read fails safe to an exact count.

I also fed the routes read the live capture bytes. Their counts disagree with the fabric's `prefixesReceived`, and
record again fell back to the exact count. So an inconsistent answer fails safe too.

At HEAD, the FP-043-UNNSESSCHK oracle passes, along with the 0.4.3 FP-042-UNNSESS oracle and its guards (17 passed).
That oracle drives these live captures and shows that the recorded checks fail on a session going down and on an
extra prefix.

The template `show bgp <afi> unicast neighbors <x> routes json` is the same in v0.4.2's frr.py. What's new is the
argument, an interface name.

## 3. New-read entries and the capture check

The eight entries are the seven in 0.4.3-unnsess-newread.yml and the FP-042-UNNSESS entry in 0.4.3-rest.yml.

- **Seven tests pass unchanged, in both runs** (see above). Their assertions are the same as at v0.4.2; the only
  difference is the new routes read.
- **Captures cited:**
  - tests/fixtures/unnsesschk1021_capture.txt and unnsesschk1041_capture.txt;
  - unnsesschk{1021,1041}_r2_eth{1,2}_ipv4_routes_up.json.
- **Where they came from:** they were added in b10448a, session unnsess-oracle. That is not the allowlist writer,
  the fixer or this reviewer.
- **SOURCES.yml lines:** `git blame` traces all 28 lines that file them (838-865) to b10448a. No commit in
  a7419f4..1055792 touches tests/fixtures/. The allowlist session did not write the label.
- **The capture logs:** each log has a line
  `clab-ndr-unnsess-r2 rc=0 unnsesschk_r2_eth{1,2}_ipv4_routes_up.json <- vtysh -c show bgp ipv4 unicast neighbors
  eth{1,2} routes json`.
  That is the same command, word for word, as the one logged at the candidate.
- **The JSON itself:**
  - It has FRR's shape: vrfId, vrfName, tableVersion, routerId, localAS, and routes keyed by prefix, with
    `peerId` set to the neighbour's fe80:: link-local address.
  - The 10.4.1 files add `totalRoutes` and `totalPaths` and the `linkLocalOnly` next-hop form, as SOURCES.yml says.
    10.2.1 prints neither.
  - The prefix counts agree across the state set: eth1 has 2, eth2 has 1.
  - I judge it FRR's real answer to that command for an interface-named (unnumbered) neighbour.
- **How they belong to these tests:**
  - They answer the exact new read these tests trigger, on FRR 10.2.1, the version of the FP-042 fabric.
  - They are the evidence of the oracle that drives the fix.
  - They were captured on lab ndr-unnsess, not on the FP-042 fabric. So they vouch for the command and the answer's
    shape, not for leaf01 and spine01's own counts. In these tests' fakes the read is unanswered and the result is
    the exact count.
- **Live coverage:** each flip is `[new-read on *]`, and frr.py changed, so the release gate keeps FRR (and every
  OS) on live for the candidate.

## 4. Entries against the flips

I compared with the allowlist session's gate run on 1055792.

- **Dominance (the stricter judge).** Every entry in the three files is printed as "allowed by". There are 0
  unexplained flips and no stale or dead entry. The two remaining problems are:
  - the efae4fd line the historic record waives;
  - this review's missing commit, which this record supplies.
- **Loosening against v0.4.2 (the old judge).** These lines are dropped:
  - the bare-path gate flips and the `<path>@<blob>` stale lines, by the gate-naming bridge;
  - the `kind` keys lines for these entries, together with the FP-042-UNNSESS verdict flip, by the kind bridge.

  Each one is dropped only after dominance matched it. Each entry's source, case, from and to equal a printed flip
  character for character.
