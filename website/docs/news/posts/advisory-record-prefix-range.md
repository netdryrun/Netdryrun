---
date: 2026-11-01
slug: advisory-record-prefix-range
title: "Advisory: record's default prefix check lets a small leak pass (0.3.3 and 0.4.0)"
description: "A baseline written by netdryrun record allows 20% more prefixes per neighbor, so a change that leaks one customer prefix can pass. Workaround: --exact-prefixes. Fix in 0.4.1."
categories:
  - Findings
---

# Advisory: `record`'s default prefix check lets a small leak pass

A baseline written by `netdryrun record` in 0.3.3 and 0.4.0 allows each BGP neighbor up to 20% more prefixes (at least 2) than today. So a change that leaks one or two extra prefixes from a neighbor can pass.

<!-- more -->

Our own end-to-end test found it on 31 October: deleting the `match` line of a customer's inbound route-map let the customer's 203.0.113.128/25 in, the recorded check allowed 1 to 3 prefixes, the neighbor sent 2, and `netdryrun run` passed. We released 0.4.0 on the same code without publishing it, which was our mistake.

- **Workaround now:** `netdryrun record <topology> --exact-prefixes`, or set each `max:` to today's count, and add `present: false` route checks for prefixes that must never arrive. A pinned count still misses a leak that replaces a prefix at the same count.
- **Fix in 0.4.1:** `record` adds a check that no new prefix arrives from each eBGP neighbor, and the release gate refuses a release while our end-to-end test reports a false pass. 0.3.3 and 0.4.0 will be yanked when it ships.

[Full advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.0-record-prefix-range/README.md) · [GHSA-cg9f-xjw5-38ph](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-cg9f-xjw5-38ph)
