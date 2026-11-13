---
title: "Roadmap"
description: "Where Netdryrun is going: shipped releases, the current one, and later themes. Direction, not a commitment: a version ships when its release gate is green."
---

# Roadmap

**Direction, not a commitment.** A version ships when its [release gate](how-its-built.md) is green, never on a date. Items can move, split or be dropped. Security fixes go first. Updated 2026-11-10.

**Beta** means a driver is incomplete and may change, with no support commitment, and the network OS image stays under its vendor's licence: you bring your own where the vendor requires it. A beta driver has passed the gate on captured output from that OS, including the checks that must fail.

## Shipped

| Version | Date | What it added |
|---|---|---|
| [0.4.2](https://github.com/netdryrun/Netdryrun/releases/tag/v0.4.2) | 2026-11-10 | Fix release: the two problems the new-user test found on 0.4.1 (SR Linux on containerlab 0.83, FRR 10.2 with `record`), BGP-unnumbered links in `record` (its interface-named sessions are a named gap until 0.4.3), own-address reads that skipped text before the JSON, case 4 of the [0.4.1 advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.1-known-false-passes/README.md), and six false passes found before release: BGP add-path counted as prefixes (FRR, SONiC, SR Linux, EOS), dampening history and withdrawn paths read as routes (FRR, SONiC), and graceful-restart stale paths counted (FRR, SONiC); see the [0.4.2 advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.2-addpath-prefix-count/README.md). Cases 1 to 3 of the 0.4.1 advisory remain, with workarounds |
| [0.4.1](https://github.com/netdryrun/Netdryrun/releases/tag/v0.4.1) | 2026-11-09 | The false-pass release: fixes for [GHSA-cg9f-xjw5-38ph](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-cg9f-xjw5-38ph) and [GHSA-g4f6-4624-2pjv](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-g4f6-4624-2pjv); Cisco NX-OS and MikroTik RouterOS, beta. Four known false passes remain, published with workarounds ([advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.1-known-false-passes/README.md)) |
| [0.4.0](https://github.com/netdryrun/Netdryrun/releases/tag/v0.4.0) | 2026-10-31 | `verify_change` on FRR: declare what you meant to change, and anything else that changes in the routing state fails |
| [0.3.3](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.3) | 2026-10-30 | The default path for AI agents in sandboxes (open a PR, read a machine-readable verdict); `record` defaults. Affected by [GHSA-cg9f-xjw5-38ph](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-cg9f-xjw5-38ph) |
| [0.3.2](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.2) | 2026-10-28 | The agent contract: a frozen verdict schema, honest tool descriptions, evidence and a next step on every failure |
| [0.3.1](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.1) | 2026-10-28 | Fail closed: unreadable or incomplete state is an error, never a pass |
| 0.1.0 to 0.3.0 | 2026-10-27 | First public releases: CLI, GitHub Action, MCP server; FRR, SR Linux, SONiC, Arista cEOS |

## Current: 0.4.3

A fix release, with no new features:

- Fixes for the two known false passes of 0.4.1 that 0.4.2 doesn't fix (Arista EOS routes that weren't selected, SR Linux EVPN type-5 routes in an ip-vrf), each with a reproducing test written before the fix.
- Limits 0.4.2 doesn't close, each listed on the trust page or the config reference: the node's own exported prefix on SR Linux and Junos (RT-0048), the corpus v2 case 18 race, a narrow attributable proof for a prefix-limit reset, a route that takes one advertisement interval per hop, the EOS `out-delay`, the NX-OS FIB state, and the two FRR config-comparison limits.
- `record --attributes` on SR Linux reads an empty AS path exactly, instead of naming it as a gap.
- `record` and checks name a BGP-unnumbered session by its interface (`eth1`), so a session over an unnumbered link is recorded instead of named as a gap.
- The full release gate on the final release candidate, the scripted end-user acceptance run included.

## Later (in this order, current plan)

- **0.4.4: one router-state contract** shared by the drivers that already pass the gate, so a check means the same thing on every OS.
- **Then: Cumulus Linux, beta.**
- **0.5: check strength and signed verdict receipts.** [Check strength](disclosures/check-strength.md) runs a lab's checks against known-bad variants of the network and lists the ones every check still passes. A receipt records what was checked, the verdict, the evidence and how strong the checks were, so a reviewer can verify it offline.
- **0.6: hosted verification, beta.** Run a verdict without local Docker. The Apache-2.0 CLI, Action and MCP server stay the product and stay free.
- **After that, by demand:** OSPF and IS-IS adjacency checks, path and traceroute checks, EVPN, MPLS and segment routing, more drivers.

Want something moved up? [Open an issue](https://github.com/netdryrun/Netdryrun/issues) or [ask for a test of your own change](contact.md).
