# A declared route that is only a blackhole

Case 06 of the [false-passes corpus](../../README.md). Expected: **failed** (UNDECLARED CHANGES), exit code 1; the report names the discard route.
Found by: 0.4 expert gauntlet, finding R5. Fixed in **0.4.0**.

## What was tested

The change adds `ip route 10.101.0.0/24 Null0` and a `network` statement on r1. The intent declares that 10.101.0.0/24 appears on r1 and r2, without saying how.

## What passed wrongly

The 0.4 development build before the expert gauntlet (verify is new in 0.4; this was never released) answered: **INTENT MATCHED**.

verify counted a route as "installed" when it was in the FIB, even with no next hop that forwards. The Null0 route satisfied `appears_on`, so a change that drops the traffic matched its intent.

## What happens now

`appears_on` needs a next hop that forwards. A discard route (blackhole, reject, unreachable, or a BGP route resolving over one) must be declared `state: discard`, so the reviewer sees that the node drops the traffic. Here it is not declared, so the verdict is UNDECLARED CHANGES.

## The tests that hold it

- `tests/test_verify_gauntlet.py::test_appears_on_is_not_satisfied_by_a_discard_route`
- `tests/test_verify_gauntlet.py::test_a_discard_route_is_declared_with_state_discard`

## Rerun it

Needs netdryrun 0.4.0 or later. On an older version this case is not expected to give the verdict above (the point of the case is that the older version did not).

```bash
cd corpus/v3-false-passes/cases/06-appears-on-a-blackhole
netdryrun verify lab/topology.clab.yml --before before --after after --config-dir configs --intent intent.yml --json report.json
```

Compare the exit code and message with [case.yml](case.yml). This case has been written and checked offline only; it has not yet been run in a lab (`live_verified: false` in case.yml).
