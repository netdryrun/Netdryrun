# A link-local next hop that is a typo

Case 03 of the [false-passes corpus](../../README.md). Expected: **failed** (UNDECLARED CHANGES), exit code 1, with `fe80::dead` in the report.
Found by: 0.4 expert gauntlet, finding R1. Fixed in **0.4.0**.

## What was tested

Two routers peer over their link-local addresses. In the *after* config r2 announces its prefix to r1 through a route-map that sets the link-local next hop to `fe80::dead`, an address no router in the lab owns. The intent declares that nothing changes.

## What passed wrongly

The 0.4 development build before the expert gauntlet (verify is new in 0.4; this was never released) answered: **NO BEHAVIOR CHANGE (the typed difference was collapsed)**.

verify replaced every link-local address with `fe80::` because "only a boot makes them", which is false for an address the config names. The wrong next hop looked identical to the right one.

## What happens now

A link-local next hop is named by the lab node and interface that own it. An address no node owns is kept as written, so the typo is a difference: the report names `fe80::dead` and the verdict is UNDECLARED CHANGES.

## What this case does and does not show

In 0.4 the change also fails because the running config of r2 differs and nothing declares it (the config-change rule), so the verdict would be *failed* even without the link-local fix. The case pins that the report names the address `fe80::dead` (searched in the console output and in `report.json`); the tests below pin the rule itself. It is a smoke test, not a discriminator. The lab must be run to confirm FRR really sends that next hop.

## The tests that hold it

- `tests/test_verify_gauntlet.py::test_a_link_local_next_hop_is_named_by_its_owner_and_anything_else_kept`
- `tests/test_verify_gauntlet.py::test_cold_6_an_unowned_link_local_is_kept_only_when_the_config_names_it`

## Rerun it

Needs netdryrun 0.4.0 or later. On an older version this case is not expected to give the verdict above (the point of the case is that the older version did not).

```bash
cd corpus/v3-false-passes/cases/03-link-local-next-hop-typo
netdryrun verify lab/topology.clab.yml --before before --after after --config-dir configs --intent intent.yml --json report.json
```

Compare the exit code and message with [case.yml](case.yml). This case has been written and checked offline only; it has not yet been run in a lab (`live_verified: false` in case.yml).
