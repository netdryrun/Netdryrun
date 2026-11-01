# Advisory: Netdryrun 0.3.3 and 0.4.0, a baseline from `netdryrun record` can pass a leaked customer prefix

**Affected:** netdryrun 0.3.3 and 0.4.0, and the `netdryrun/netdryrun@v0.3.3` and `@v0.4.0` Actions, when the checks were written by `netdryrun record` (or the `record_baseline` MCP tool) without `--exact-prefixes`. That is the README's "on your own containerlab topology" path. Hand-written checks and the examples are not affected by this default. **Fixed in:** 0.4.1 (not released yet); 0.3.3 and 0.4.0 will be yanked from PyPI when it ships. **Found by:** our own end-to-end test (the synthetic stranger), on 31 October 2026, before any outside user reported it.

## What happened

`record` turns today's received-prefix count from each BGP neighbor into a range check: today's count as the minimum and up to 20% more (at least 2) as the maximum. The headroom is there so normal growth doesn't fail the check. It also means a change that lets one or two extra prefixes in from a neighbor still passes.

In a small FRR lab, a core router accepts one /24 from a customer through an inbound filter:

```text
route-map CUST-IN permit 10
 match ip address prefix-list CUST-IN
```

The change deletes the `match` line. The customer's 203.0.113.128/25, which it doesn't own, is now accepted and passed on. The recorded check allows 1 to 3 prefixes from that neighbor, it receives 2, and `netdryrun run` exits 0. It should exit 1.

We found this on 31 October and released 0.4.0 on the same code without publishing it. That was our mistake: the release gate didn't read the end-to-end test's result. From 0.4.1 it must.

## What to do until 0.4.1

- **Re-record with exact counts:** `netdryrun record <topology> --exact-prefixes`. Any change in a neighbor's prefix count then fails.
- Or edit the generated `netdryrun.yml` and set each `bgp_prefixes` check's `max:` to today's count.
- Add `route` checks with `present: false` for prefixes that must never arrive from a neighbor.

**Limit of the workaround:** a pinned count still misses a leak that *replaces* a prefix (one route withdrawn, a different one accepted, same count). Checks on the specific prefixes cover that case.

## What 0.4.1 will do

- `record` will add a check that no prefix outside today's received set arrives from each eBGP neighbor, so a new prefix fails even when the count is in range.
- This case joins the verdict corpus as a must-fail case, and the release gate will refuse a release while our end-to-end test reports a false pass.

## Found another way it can pass without looking?

[Open a corpus case](https://github.com/netdryrun/netdryrun/issues/new?template=corpus-case.yml): it becomes a permanent must-fail test, credited to you. Or write to [security@netdryrun.com](mailto:security@netdryrun.com).
