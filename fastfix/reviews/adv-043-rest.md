# Flip review: 0.4.3 candidate against v0.4.2 (surfaces_agree LobeHub WARN; FP-042-UNNSESS gap assertion)

- Reviewer session: adv-043-rest. It wrote no code, test, fixture, record, evidence or allowlist in this change;
  this file is its only commit.
- Reviewed: main c8795b1 (c8795b10a4db) against the published v0.4.2 (61cd95de8b54), in a fresh clone in WSL
  Ubuntu-ndr, shared venv, `PYTHONPATH=src`. Commits read: efae4fd (surfaces_agree), b10448a (oracle
  FP-043-UNNSESSCHK and the FP-042-UNNSESS edit), 12574f4 and 0306e3c (the fix), 97860e2 and ccdba1a (plants).
- Verdict: both flips are acceptable.
  - `gate :: scripts/surfaces_agree.py@15990540b1e6: FAIL -> PASS`
  - `fixtures :: tests.oracles.FP-042-UNNSESS.test_oracle_fp_042_unnsess::test_every_unnumbered_neighbor_is_recorded_or_a_named_gap: FAIL -> PASS`
  Neither weakens a check that stands between a user and a wrong verdict. Flip 1 stops one third-party mirror we
  can't update from blocking the after-publish layer; every surface we publish to still blocks and still fails
  closed. Flip 2 is the v0.4.2 oracle asserting "there must be a gap", which no longer holds because 0.4.3 records
  and checks those sessions; every unnumbered neighbour is now recorded, or still a named gap.

Dominance, re-run here with main's fastfix_gate.py in the gate's dominance mode (`--base 61cd95de --candidate HEAD --dominance`), it prints both flips above as "BLOCKED loosening flip with no reviewed allowlist entry", plus `efae4fdafc has no Session: trailer` (the historic-record case, FX-0.4.3-gate-no-historic-exception, not judged here) and "BLOCKED (28 unexplained flip(s), 27 problem(s))". The other 26 unexplained flips and the allowlist-entry problems are outside this review.

## Flip 1: `gate :: scripts/surfaces_agree.py@15990540b1e6: FAIL -> PASS`

The blob at main is still 15990540b1e6 (`git rev-parse HEAD:scripts/surfaces_agree.py`). The only commit on the
file since v0.4.2 is efae4fd. The flip is v0.4.2's `tests/test_surfaces_agree_042.py` failing on the new script:
`test_a_stale_lobehub_listing_is_red` and `test_a_surface_that_cant_be_read_is_red_never_a_pass` (which used LobeHub
as its unreadable surface).

### What changed, and which way it points

| Change | Direction | Why it is acceptable |
|---|---|---|
| LobeHub version mismatch: `problems` -> `warnings` | looser, by design | LobeHub is a third-party mirror of the MCP Registry, filled automatically; we don't run its registration command (HQ media log, 2026-10-29 on). It has shown 0.3.1 since 0.3.x while the Registry moved on. It was the only DISAGREE in 0.4.2's after-publish run (`releases/0.4.2/GATE.md`: "LobeHub: the listing shows version 0.3.1, expected 0.4.2", 1 problem). A blocker nobody can clear would block every release; it guards no verdict. |
| LobeHub unreadable / no version on the page: `problems` -> `warnings` | looser, by design | same surface, same reason. The `read()` helper takes `into=` and only the LobeHub call passes it. |
| `main` prints `WARN <text>` before `DISAGREE` lines | new output | the stale listing is still printed on every run, and lands in the gate layer's output tail |
| `test_a_surface_that_cant_be_read_is_red_never_a_pass` now uses llms.txt | same strength | the fail-closed read is still tested, on a surface that still blocks |

Nothing here touches a verdict, a check, a driver or the static layer. The surfaces that still block are the ones we
publish: the GitHub description, PyPI (version, status line), the MCP Registry's latest entry (the source LobeHub
mirrors), and netdryrun.com/llms.txt.

### Probes

- Fail closed on the rest (L-2026-11-03-fails-closed-probe): each of the four other URLs raising `OSError` gives 1
  problem and 0 warnings. The `into=` routing does not leak to any other surface.
- A stale Registry (latest 0.4.1) together with a stale LobeHub: the Registry is a problem, LobeHub a warning. The
  surface that LobeHub copies still blocks, so a release that never reached the Registry is still red.
- `main(["published", "--version", "0.4.2"])` with only LobeHub stale: exit 0, output
  `WARN LobeHub: the listing shows version 0.3.1, expected 0.4.2` then `surfaces published: agree (...)`.
- `tests/test_surfaces_agree_042.py` at main: 23 passed. The new test asserts all three LobeHub cases (stale,
  unreadable, matching) and that none is a problem.

### Not covered / minors

- "The media check still watches it" (commit message) is a manual HQ routine (`marketing/MEDIA-LOG.md`, the
  2026-11-21 LobeHub row; `AGENT-REACH-PLAN.md`), not code. Nothing automated fails if nobody looks. Acceptable for a
  third-party listing whose stale text we already know of; the WARN line keeps it visible in every after-publish run.
- In GATE.md the layer's summary line will read "agree"; the WARN is only in the collapsed output tail. A reader of
  the summary won't see it. Cheap follow-up: put the WARN count in the summary line.
- LobeHub still quotes the pass verdict text that 0.3.2 retired (AGENT-REACH-PLAN). That is a stale public
  claim on a site we don't control. This change neither causes nor hides it; it was blocking releases without
  fixing it.

## Flip 2: `fixtures :: tests.oracles.FP-042-UNNSESS.test_oracle_fp_042_unnsess::test_every_unnumbered_neighbor_is_recorded_or_a_named_gap: FAIL -> PASS`

### Why the v0.4.2 test fails on the new code

Ran v0.4.2's `tests/oracles/FP-042-UNNSESS/test_oracle_fp_042_unnsess.py` from a v0.4.2 worktree with
`PYTHONPATH=<main>/src` (import checked: `netdryrun.__file__` is main's). 1 failed, 2 passed. The failure is the
last line only:

```text
>       assert gaps, "record exits 0 with sessions it didn't record"
E       AssertionError: record exits 0 with sessions it didn't record
E       assert []
```

The assertion before it, `assert not missing` (every neighbour is recorded or a named gap), holds. So on the
captured FRR 10.2.1 unnumbered fabric (leaf01 eth1/eth2, spine01 eth1/eth2/eth3) every session is now recorded, and
there is no gap left to name. v0.4.2's oracle demanded a gap unconditionally because in 0.4.2 a gap was the only
honest outcome; the 0.4.3 edit (b10448a, landed with the FP-043 oracle, before the fix 12574f4) requires a gap only
for a session that isn't recorded: `assert gaps or not unrecorded`.

### Which way it points

Strictly better, on the evidence below: an unnumbered session moves from "INCOMPLETE BASELINE, exit 1, nothing
guards it" to a `bgp_session` check plus `bgp_prefixes` checks (exact count per carried family; `exact: 0` for an
eBGP family not carried), judged like a numbered session. The RT-0066 rule ("support it or make every use of it a
loud gap") is kept: supported on FRR, a loud gap everywhere else.

### Probes (each run with main's src on the FP-042-UNNSESS capture, through the real `record.record`, the real
`Lab.interface_addresses`, the real FRR driver and the real `checks._evaluate`)

- P1, recorded checks are real: record writes `bgp_session` for all 5 neighbours, plus `bgp_prefixes` ipv4 `exact: 4`
  and ipv6 `exact: 0` each; `baseline_gaps` is empty. Every recorded check passes on the captured state. For each of
  the 5 neighbours, the `bgp_session` check FAILS (a real failure, not `Unready`) when that session's `bgpState` is
  `Idle` ("state is idle") and when the neighbour is gone from `show bgp neighbors json` ("neighbor eth1 not
  configured (seen: eth2)"). No unnumbered neighbour passes unchecked.
- P2, other drivers keep the gap: with `interface_peers = False` on the driver (every driver except FRR; SONiC sets
  it False explicitly), record writes no `bgp_session` and names every neighbour in an INCOMPLETE BASELINE line.
  v0.4.2's behaviour, so v0.4.2's oracle intent still holds there.
- P3, a key that is no interface name (`10.0.0.256`, a mistyped address) on FRR: INCOMPLETE BASELINE line, no check.
- P4, an unnumbered session that is `Active` at record time: INCOMPLETE BASELINE line naming leaf01 eth2 (it goes
  through the same down-session gap as a numbered one).
- Plants (FX-0.4.3-redteam-fake-unanswered-command: a guard counts only if it fails for its reason):
  `fastfix_gate.py plants --repo . --base v0.4.2`: clean, 22 caught of 22, FP-042-UNNSESS and FP-043-UNNSESSCHK
  both `caught`. Applied by hand:
  - FP-043-UNNSESSCHK's plant (the fix's reverse): 10 of its 10 tests fail, including record writing no checks,
    the down/more states not failing and the address-keyed-driver refusal; FP-042-UNNSESS's 3 tests still pass
    (correct: the plant restores the named gap, which FP-042 accepts).
  - FP-042-UNNSESS's plant (the plain "not recorded" warning, the /32 parser, 169.254 as link-local): its 3 tests
    fail, the first on `missing`, the reason it guards.
- At main: FP-042-UNNSESS, FP-043-UNNSESSCHK, `tests/test_unnumbered_sessions_043.py` and
  `tests/test_oracle_guards_fp_042_unnsess.py`: 52 passed.
- The current FP-043-UNNSESSCHK oracle guards the new behaviour on live captures (FRR 10.2.1 and 10.4.1, states up,
  down = `neighbor eth1 shutdown` on the peer, more = a third prefix): recorded checks pass on up and fail on down
  and on more; hand-written checks naming the interface load and fail; EOS and SR Linux refuse an interface-named
  check before deploying.

### Not covered

- No live lab run in this review; the live evidence is FP-043's captures.
- SONiC can key sessions by interface too; it is left as a gap (interface_peers False), which is safe, not checked.
- Interface names are unique per node, so the shared link-local key problem (FX-0.3.3-shared-link-local-neighbor)
  does not return here: the check names the interface, not the fe80 address. Not probed beyond reading.
