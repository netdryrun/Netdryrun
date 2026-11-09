---
date: 2026-11-09
slug: release-0.4.1
title: "Netdryrun 0.4.1: the false-pass release"
description: "0.4.1 fixes the false passes in our two earlier advisories, publishes four narrower ones our final red team found, and replaces 0.3.3 and 0.4.0, now yanked from PyPI."
categories:
  - Releases
---

# Netdryrun 0.4.1: the false-pass release

A verifier that says "passed" without really checking is worse than no verifier. 0.4.1 is about that one thing.

<!-- more -->

- **Fixes the false passes in our two earlier advisories:** the `record` prefix range ([GHSA-cg9f-xjw5-38ph](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-cg9f-xjw5-38ph)) and the 23 cases in [GHSA-g4f6-4624-2pjv](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-g4f6-4624-2pjv). One part of case 19 stays a documented limit on SR Linux and Junos. Each fixed case has a test that must fail.
- **Publishes four narrower ones** that our final red team found on the release candidate, with a workaround for each: on Arista EOS, SR Linux EVPN, FRR/SONiC VRF pings, and SR Linux `record --attributes` (a regression in 0.4.1). [Known false passes in 0.4.1](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.1-known-false-passes/README.md). *Update, 10 November:* 0.4.2 fixes the `record --attributes` case; the other three are planned for 0.4.3, so keep their workarounds until then.
- **0.3.3 and 0.4.0 are yanked** from PyPI. Upgrade with `pipx upgrade netdryrun` and pin `netdryrun/Netdryrun@v0.4.2`.
- **Record your baselines again.** 0.4.1 refuses some files 0.4.0 accepted, such as a prefix without a length or an IPv6 `bgp_prefixes` neighbor without `afi`. Every such refusal is a check that could never fail before.
- **Also new:** Cisco NX-OS and MikroTik RouterOS drivers (beta, used only when you choose them), the capture kit (`netdryrun capture` and `sanitize`), and contributor gates on every pull request.

How it was tested: static checks, the unit suite, mutation testing, both verdict corpora, live labs on every example across 7 network OSes, our end-to-end new-user test, and a red team on the final candidate. One layer, the scripted end-user walk-through, was not run on the final commit; the [release review](https://github.com/netdryrun/Netdryrun/blob/main/releases/0.4.1/review.md) says why.

Found after release by the same new-user test on a fresh GitHub runner (both fail safe: an error, never a wrong pass; both fixed in 0.4.2, except that `record` on a BGP-unnumbered fabric still exits 1, naming each interface-named session it can't record yet):

- **SR Linux on containerlab 0.83:** `netdryrun run examples/srl-frr` stops with exit 2, "runs in the namespace of … which is not a lab node". The check that keeps a run from testing the host refuses SR Linux's network namespace there. We're confirming which containerlab versions are affected; the FRR examples run normally.
- **FRR 10.2 with `record`:** it can't read one of FRR's replies, exits 1 and lists each guard it couldn't write. Until the fix, add those guards by hand.

Think you can make it say "passed" when it shouldn't? [Open a corpus case](https://github.com/netdryrun/Netdryrun/issues/new?template=corpus-case.yml) and it becomes a permanent must-fail test.

[Full changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) · [Release on GitHub](https://github.com/netdryrun/Netdryrun/releases/tag/v0.4.1)
