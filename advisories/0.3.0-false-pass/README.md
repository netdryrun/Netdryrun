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
- **Graceful restart on SR Linux, EOS and SONiC** (found by the 0.3.3 cross-platform review): while a peer restarts with graceful restart, its routes stay in the table marked stale until it re-sends them or the stale timer ends, and on these platforms the BGP checks count a stale path as present and best. A route check can pass on a route that is about to go. On FRR, Netdryrun reads the stale flag: a route or `bgp_route` check never passes on a stale path (0.3.3). Mitigation: leave graceful restart off in the lab, or give the checks a `timeout` above the stale timer. Fix scheduled: 0.4.1 (read the stale flag on the other platforms, from a live graceful-restart capture; was scheduled for 0.4).
- **SR Linux prefix counts** (found by the 0.3.3 cross-platform review, seen on a live SR Linux 26.7.2): a `bgp_prefixes` count on SR Linux includes routes dropped by BGP loop detection, which are not usable, so a `min` or `exact` check can pass with fewer usable prefixes. Mitigation: pair the count with `route` checks for the prefixes that matter. Fix scheduled: 0.4.1 (count usable routes only; was scheduled for 0.4).
- **Startup config on Arista cEOS, Nokia SR Linux and SONiC** (fixed in 0.4): a line the NOS rejected at boot makes the run an error (exit 2). cEOS skips such a line and loads the rest, like FRR: Netdryrun reads `show startup-config errors` after the checks, and any listed line, or output it can't read, is an error naming the line. SR Linux: a CLI startup config is one commit containerlab applies at deploy, and a line that doesn't parse or a commit that fails fails the deploy; a JSON one SR Linux loads itself and, when it rejects it, runs without it while the deploy succeeds, so Netdryrun reads its log ("Load of startup configuration failed"; a log it can't read is an error). SONiC (docker-sonic-vs) has no startup config: it is configured with `setup:` commands, which stop the run when they exit non-zero; a config file bound into a SONiC node's `/etc`, `/usr` or `/var/lib`, or an inline startup config, is an error. A `setup:` command is checked by its exit code only: SONiC's `config ...` commands and CONFIG_DB writes can exit 0 and fail later, so configure SONiC's routing with `vtysh -c` lines, which fail at once. On a lab Netdryrun didn't deploy (`netdryrun check`), SR Linux and SONiC say `not verified`. **A topology `exec:` command that fails** is an error on every platform: containerlab only logs it and exits 0, and the node runs without what it configured. **Juniper cJunosEvolved (beta): the config load is not verified yet**; the report says `not verified on junos`: add a positive check for what each changed line creates.
- **A slow peer** (still a limit in 0.3.2). A neighbor with a long advertisement interval can deliver a route after the gate released a negative check. Raise `--settle` and `--hold` above your slowest advertisement interval. *From 0.4:* the windows stretch automatically to the longest interval the drivers read (FRR, SONiC, SR Linux), **except on Arista EOS, where the advertisement delay (`out-delay`) is not read yet: raise `--settle` and `--hold` above it there** (fix planned for 0.4.1). A route that crosses several slow peers can still take one interval per hop.
- **`afi: evpn`** is refused on Arista EOS and Nokia SR Linux (their drivers can't read an EVPN count). On FRR and SONiC the count is read from the router's BGP summary; a family the neighbor doesn't carry counts as 0 received prefixes.

## What we changed in how we release
0.3.1 is the first release cleared by a seven-layer gate, and every release after it goes through the same gate: static checks; unit tests on every supported Python; verdict invariants (property-based tests, fuzzing, and a must-fail matrix that every check type and driver must appear in); mutation testing of the verdict logic, where no surviving mutant may change a verdict; a live lab matrix with chaos tests; review; and a post-publish proof. The record for this release is [`releases/0.3.1/GATE.md`](../../releases/0.3.1/GATE.md).

## Found another way it can pass without looking?
That's the most valuable report we can get. [Open a corpus case](https://github.com/netdryrun/netdryrun/issues/new?template=corpus-case.yml): it becomes a permanent must-fail test, credited to you.
