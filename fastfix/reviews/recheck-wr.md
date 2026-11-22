# New-read review: three EOS red-team refusal flips on ndr/fix-eos-agg-v3 (RT-0016, RT-0025, RT-0037)

- Reviewer session: recheck-wr. It wrote no code, test, record, evidence or allowlist in this change; this file is
  its only commit. The allowlist entries were written by session allow-043-wr (781c3af).
- Reviewed: the EOS branch merge b230514 (main 1d50092 into ndr/fix-eos-agg-v3), then a local merge of
  ndr/fix-redteam-wrongreason db706e0 into it (as main now has it, 46cab9d), re-checked on 336fb1c / 781c3af,
  judged against main's tests and red-team case files, as the gate runs them (base tree, candidate's src/).
- Verdict: genuine-allow for all three flips. No loosening found.
- Network OS the new read touches: Arista EOS only (`show rib route ip|ipv6 vrf <vrf> <prefix> | json`). Live runs of
  every EOS example on the candidate commit are still owed to the release gate.

## The flips

All three are `tests.test_redteam::test_driver_case_that_ends_in_an_error_ends_in_its_refusal[...]: FAIL -> PASS
[new-read on eos]`. Their `test_driver_case_does_not_pass` siblings are already allowed in this file (adv-eos-agg).

| Flip | At the gate (main's test and case file, candidate's code) | Candidate's own case | Verdict |
|---|---|---|---|
| `[RT-0016-eos-leak-received-not-selected]` | fails: "the fake lab has no answer for ['Cli -p 15 -c show rib route ip vrf default 0.0.0.0/0 \| json']" (harness gap) | answers the RIB read (derived from live captures) and ends "unexpectedly present via bgp" | genuine-allow |
| `[RT-0025-eos-ospf6-never-matches]` | fails: no answer for `show rib route ipv6 vrf default 2001:db8:77::/48 \| json` | answers it (derived from the live IPv6 RIB capture) and ends "unexpectedly present via ospf6" | genuine-allow |
| `[RT-0037-eos-unmapped-route-type-passes-present-false]` | fails: no answer for `show rib route ip vrf default 10.1.0.0/16 \| json` | answers it (live empty-RIB capture, routingDisabled added) and ends in the refusal "is not one this driver maps to a protocol" | genuine-allow |

Quotable sentences (as in fastfix/allow/0.4.3-eos-agg.yml):

- RT-0016: recheck-wr: fails at base only on the unanswered new EOS RIB read; candidate's case answers it and ends
  "unexpectedly present via bgp" (BGP-table path pinned in reverts_043).
- RT-0025: recheck-wr: fails at base only on the unanswered new EOS IPv6 RIB read; candidate's case ends "unexpectedly
  present via ospf6", and reverting both name layers makes it pass.
- RT-0037: recheck-wr: base fails only on the unanswered RIB read; candidate ends in the routeType refusal, and passing
  it through raw makes does_not_pass[RT-0037] fail.

## What was checked

- Main's tests/test_redteam.py and tests/redteam/ with the candidate's src/ (`-k "RT-0016 or RT-0025 or RT-0037"`):
  6 failed on 1d50092's tests (both tests per case), 3 failed on 46cab9d's tests (`ends_in_its_refusal`), every
  failure "the fake lab has no answer for [... show rib route ...]". The same tests on main's own src/: 6 passed.
- Candidate's own red-team and revert tests (tests/test_redteam.py, tests/test_redteam_reverts_043.py,
  tests/test_known_false_passes.py) on the local merge with db706e0: 251 passed, 0 skipped; on 781c3af, the EOS
  subset: 54 passed.
- RT-0037 revert in the source (eos.py `_protocol` returns the raw routeType instead of raising):
  `test_driver_case_does_not_pass[RT-0037]` FAILED ("RT-0037: passed: absent (held 10s, 5 samples)") and
  `ends_in_its_refusal[RT-0037]` passed. So this flip's test does not itself catch the false pass; its
  `does_not_pass` sibling does. Checked on b230514 and again on 781c3af.
- RT-0016 and RT-0025 reverts: by tests/test_redteam_reverts_043.py (routing-table-only read, ospf named without
  family, the BGP-table-only answer set for RT-0016), all passing on the candidate; they put the bug back and assert
  the case passes.
- Gate, local merge of db706e0 into b230514, `fastfix_gate.py loosening --repo . --base db706e0`: 13 flips allowed by
  the existing entries; BLOCKED exactly these 3 flips, no skipped-at-base problem (the RT-0037 problem was only the
  base's skip, removed by db706e0).

## Still open (not blocking these flips)

- MINOR: with its derived RIB answer, RT-0016 in the corpus is caught through the RIB's losing bgp entry; the BGP-table
  path alone is pinned only in tests/test_redteam_reverts_043.py, not in the red-team corpus.
- MINOR (Review 1, db706e0): a WRONG_REASON case that passes is no longer listed by the release gate's
  skipped-at-base MAJOR, and the AST no-skip guard in tests/test_redteam.py misses aliased or indirect skips
  (`import pytest as pt`, `_pytest.outcomes.skip`, `getattr`, `unittest.SkipTest`, conftest).
