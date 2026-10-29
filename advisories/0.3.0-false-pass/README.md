# Advisory: ways Netdryrun 0.3.0 could pass without testing what the file said

**Affected:** netdryrun 0.3.0 and the `netdryrun/netdryrun@v0.3.0` Action. **Fixed in:** 0.3.1. **Found by:** our own pre-launch audit, before any outside user reported it. 0.3.0 is yanked on PyPI: exact pins still install, unpinned installs get 0.3.1.

A change tester has to make it hard for a check to pass without testing what it says. These are the paths our audit found and 0.3.1 fixes, each with a test you can rerun. An audit can't prove it found every such path; if you find another, see the end of this page. Full detail is in the [0.3.1 changelog](../../CHANGELOG.md).

## Config paths: reproduce in seconds, no lab needed

Each file below is a check that means one thing and, on 0.3.0, tested another or nothing. `netdryrun validate` reads the file and the topology without deploying anything:

```bash
uvx netdryrun==0.3.0 validate advisories/0.3.0-false-pass/2-quoted-boolean.yml   # accepted
uvx netdryrun==0.3.1 validate advisories/0.3.0-false-pass/2-quoted-boolean.yml   # refused, exit 2
```

| File | What was meant | What 0.3.0 did | 0.3.1 |
|---|---|---|---|
| [1-misspelled-top-key](1-misspelled-top-key.yml) | A leak guard under a misspelled `chekcs:` | Ignored the block; the run passed on the remaining check | Refused: `unknown top-level keys ['chekcs']; did you mean 'checks'?` |
| [2-quoted-boolean](2-quoted-boolean.yml) | `present: "false"`: the default route must be absent | Read `"false"` as true: the guard passed exactly when the leak was there | Refused: `present must be true or false (unquoted)` |
| [3-unknown-afi](3-unknown-afi.yml) | At most 10 IPv4 prefixes (`afi: ipv4`) | Counted 0 for the unknown family, so `max` always passed | Refused, suggests `ipv4-unicast` |
| [4-unknown-protocol](4-unknown-protocol.yml) | No eBGP default route (`protocol: ebgp`) | Matched no route, so `present: false` always passed | Refused, suggests `bgp` |
| [5-duplicate-key](5-duplicate-key.yml) | `present: false`, with a stray second `present: true` | YAML kept the last value: the guard passed exactly when the leak was there | Refused: `duplicate key 'present' (first defined on line 8)` |
| [6-min-zero](6-min-zero.yml) | "At least some prefixes" (`min: 0`) | Always passed | Refused: use `min: 1` or add `max` |
| [7-vrf-all](7-vrf-all.yml) | No default route in any VRF (`vrf: all`) | Devices answer keyed by VRF name, read as "no routes": always passed | Refused: name one VRF per check |

We ran every row above against the real 0.3.0 from PyPI and against 0.3.1 before publishing this advisory. Inside a check or a scenario, 0.3.0 already refused misspelled keys; the gap was at the top level, under `nodes`, and inside `node_isolated`.

## Runtime paths: covered by tests that fail on 0.3.0

These need a running lab to show, so the proof is in the test suite, which runs on every commit:

| Path | What 0.3.0 could do | Tests |
|---|---|---|
| A failure scenario judged before the fault was visible | Pass the scenario's checks on the network as it was before the link went down | `tests/test_runner_robustness.py`: `test_scenario_positive_cannot_pass_on_pre_fault_state`, `test_scenario_waits_for_the_fault_to_show_in_bgp`, `test_scenario_errors_when_the_fault_never_shows` |
| A negative check evaluated before every session converged | Pass a leak guard before a leak arrived over a session nobody checked | `tests/test_runner_robustness.py`: `test_negative_check_waits_for_every_bgp_session_on_its_node`, `test_negative_check_not_evaluated_if_its_node_never_converges` |
| A driver reading an error as "nothing" (an unknown VRF, a failed command, unrecognized output) | Read "no routes" or "0 prefixes", which passes `present: false` and `max` | `tests/test_driver_false_pass.py`, `tests/test_driver_fuzz.py` (`test_empty_output_raises`) |
| Received paths not counted on some drivers | Miss a leaked route that arrived but wasn't selected | `tests/test_verdict_drivers.py`, `examples/srl-hidden-leak` |

## Limits that remain in 0.3.1
- **A node that never reports BGP neighbors.** In 0.3.1 its negative and attribute checks waited up to their timeout, then still ran, and could pass. **Fixed in 0.3.2:** when the file has a BGP check on that node (`bgp_session`, `bgp_prefixes`, `bgp_route`, or a `route` with `protocol: bgp`), those checks fail as "not evaluated" at the cap. A node with no BGP check anywhere in the file still goes ahead with a warning in each result, since it may not run BGP at all.
- **A slow peer** (still a limit in 0.3.2). A neighbor with a long advertisement interval can deliver a route after the gate released a negative check. Raise `--settle` and `--hold` above your slowest advertisement interval. Planned for 0.4: read each peer's configured advertisement interval and extend the settle window automatically.
- **`afi: evpn`** is refused on Arista EOS and Nokia SR Linux (their drivers can't read an EVPN count). On FRR and SONiC the count is read from the router's BGP summary; a family the neighbor doesn't carry counts as 0 received prefixes.

## What we changed in how we release
0.3.1 is the first release cleared by a seven-layer gate, and every release after it goes through the same gate: static checks; unit tests on every supported Python; verdict invariants (property-based tests, fuzzing, and a must-fail matrix that every check type and driver must appear in); mutation testing of the verdict logic, where no surviving mutant may change a verdict; a live lab matrix with chaos tests; review; and a post-publish proof. The record for this release is [`releases/0.3.1/GATE.md`](../../releases/0.3.1/GATE.md).

## Found another way it can pass without looking?
That's the most valuable report we can get. [Open a corpus case](https://github.com/netdryrun/netdryrun/issues/new?template=corpus-case.yml): it becomes a permanent must-fail test, credited to you.
