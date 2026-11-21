# Layer 6: independent review, Netdryrun 0.4.2

Reviewed: the whole diff `v0.4.1..f220469` (the first `ndr/release-0.4.2` push, 2026-11-10), then the docs delta
`f220469..e6522db`. Every finding below is checked against the code; the fix commits are on `ndr/release-0.4.2`.

## Provenance

| Review | Reviewer | Output |
|---|---|---|
| Cold review | a fresh agent with none of the author's context, read-only on the worktree (~161k tokens) | findings 1-7 below |
| Adversary (angle 5) | one fresh attacker on an export of code, user docs, fixtures and the red-team harness only (~228k tokens) | RT-0066 (a BLOCKER), one LOW, 7 attempts refused |
| GPT and Grok, shipped code | `research/tools/ask_models.py`, brief `research/model-reviews/release-0.4.2/brief-shipped.md` (sha256 cbb34ee4d73e) | `research/model-reviews/release-0.4.2/shipped/` |
| GPT and Grok, gate scripts | the same tool, brief `brief-gate.md` (sha256 ede220941e07; resent once, the privacy check refused a git `index` line) | `research/model-reviews/release-0.4.2/gate/` |
| Docs delta e6522db | the release session, against the code | findings 8-9 |

One attacker instead of two, and no separate verifier: the release session reproduced the attacker's BLOCKER itself
(the repro script on the committed captures). Token budget, owner rule.

## Shipped code

| # | Finding | From | Severity | Decision | Commit / test |
|---|---|---|---|---|---|
| A1 | `record` on a BGP-unnumbered FRR fabric left every interface-named session out with a plain warning and exited 0: a dropped session or a prefix flood passed the baseline (RT-0066) | adversary | BLOCKER | Fixed: an INCOMPLETE BASELINE line names each such session; `record` exits 1. Naming them in checks is 0.4.3 | `67745a5`, oracle `FP-042-UNNSESS` |
| A2 | A numbered 169.254.0.0/30 link with a session over it was called unnumbered and left unguarded | adversary | LOW | Fixed: only fe80::/10 is link-local for "unnumbered" | `67745a5`, `FP-042-UNNSESS` |
| G1 | `inet A peer B/31` read as A/32: the wrong subnet guarded, exit 0 (a regression from the UNNUMBERED fix) | Grok, confirmed | MAJOR | Fixed: A in the peer's subnet, else a gap; no prefix length is a gap | `67745a5`, `FP-042-UNNSESS` |
| 6 | A gap line quoting device text with "only the first" was taken for a size cap and dropped | cold review | MINOR | Fixed: only `record`'s own two cap lines are exempt | `1289ef1`, oracle `FP-042-CAPMSG` |
| 7, 8 | The advice to add `as_path: ""` by hand on SR Linux can't work: the driver reads the missing container as unknown, so that check never gets a verdict. It was in the CHANGELOG, trust.md, cli.md, the advisory and the record warning | cold review; docs delta | MINOR | Fixed: "check that path's AS path on the peer that sends it", until 0.4.3 | `9d155d7` (No-Oracle: message text) |
| 9 | The roadmap and the news post called unnumbered `record` fixed while A1 was open | docs delta | MINOR | Fixed with A1: they say the sessions are a named gap until 0.4.3 | `fad7bb5` |
| G2 | `parse_paths_available` takes the first entry header and one "Paths:" line anywhere | Grok | MINOR | 0.4.3: require exactly one entry header (FRR prints one for an exact prefix) | `fastfix/plan-0.4.3.md` |
| G3 | `needs_text_count` catches ValueError only; deep JSON raises RecursionError | GPT, Grok, cold review | MINOR | 0.4.3; every caller fails closed | `fastfix/plan-0.4.3.md` |
| R1 | `_load` accepts `null`, `0`, `false` or a string | Grok | none | Refuted: every reader raises DriverError on them (checked) | |
| R2 | `_attribute_check` with `warnings=None` drops the gap silently | Grok | none | Not reachable: `record` always passes a list | |
| R3 | local_pref None is a warning, not a gap | Grok | none | As designed: a path without LOCAL_PREF is a real answer on some drivers | |

The cold reviewer and the attacker found nothing in: the FRR text path count, `mgmt.own_holder`, `addresses._load`,
`lab.interface_addresses` (apart from G1), `_unnumbered` (apart from A1, A2) and `_attribute_check`.

## Release gate

| # | Finding | From | Severity | Decision | Commit / test |
|---|---|---|---|---|---|
| 1 | A `--case` or `--resume` live run with no full layer on the commit saved a partial `live.json` that could clear | cold review, Grok | MAJOR | Fixed: `live-partial` BLOCKER until a full run | `1a05ec7`, `tests/test_gate_records.py` |
| 2 | A FAIL and the rerun limit were keyed on the commit: an empty commit started again | cold review | MAJOR | Fixed: they follow the tree | `1a05ec7` |
| 3 | A FAIL in a labrun host gap was dropped and not counted (`--gap 0` tainted everything) | cold review, Grok | MAJOR | Fixed: a FAIL there fails, every tainted run counts; labrun records its limits | `1a05ec7` |
| 5 | An unreadable attempt record (it may have held a FAIL) was skipped | cold review, GPT, Grok | MINOR | Fixed: a BLOCKER | `1a05ec7` |
| 4 | `No-Oracle:` is free text nobody reviews | cold review, GPT, Grok | MAJOR | 0.4.3 design: a reviewed entry with narrow kinds. In 0.4.2 the reviewer read both `No-Oracle` reasons in the range (f220469 version bump, 9d155d7 warning text) against their diffs | `fastfix/plan-0.4.3.md` |
| G4 | An oracle deleted after its fix (then a No-Oracle revert) went unseen | GPT, Grok | MAJOR | Fixed: an oracle the base holds or a fix names must stay | `149f0d6`, `tests/test_fastfix_gate.py` |
| G5 | A symlink in an oracle folder let a fix change its oracle through `src/` | Grok | MAJOR | Fixed: refused | `149f0d6` |
| G6 | `GATE_FILES` lacked `gate_records.py`, `labrun.py`, `surfaces_agree.py` | GPT | MAJOR | Fixed | `149f0d6` |
| G7 | A guard skipped at the base and failing at the candidate was not compared | Grok | MINOR | Fixed: a red | `149f0d6` |
| G8 | A FAIL vanished from GATE.md when the latest record lacked that check | GPT | MAJOR | Fixed | `149f0d6` |
| G9 | The bootstrap judges itself; the candidate could forge its JUnit report; allowlist `reviewed_by` unchecked; Session markers self-declared; shipped paths narrow | GPT, Grok | MAJOR (design) | 0.4.3 plan. 0.4.2 is the bootstrap release: its static layer runs this checkout's gate, as RELEASING.md says | `fastfix/plan-0.4.3.md` |
| R4 | Pytest crashes or timeouts read as passes | GPT | none | Refuted: any exit but 0/1 is a problem in both callers, and 0/1 must agree with the report | |

## What this review did not cover

- No lab: the attacker worked offline, and nothing here ran in containerlab. A1's repro used the committed captures.
- The fresh-user walk-through (an agent following the getting-started guide and tutorial on the candidate) belongs to
  the acceptance layer run by the coordinator.
- The final candidate after these fixes was not reviewed again by a fresh agent; the reproduce check, the unit suite
  and the oracles are what hold it.
