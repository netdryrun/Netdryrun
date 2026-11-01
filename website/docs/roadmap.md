---
title: "Roadmap"
description: "Where Netdryrun is going: shipped releases, the current one, and later themes. Direction, not a commitment: a version ships when its release gate is green."
---

# Roadmap

**Direction, not a commitment.** A version ships when its [release gate](how-its-built.md) is green, never on a date. Items can move, split or be dropped. Security fixes go first. Updated 2026-11-02.

**Beta** means a driver is incomplete and may change, with no support commitment, and the network OS image stays under its vendor's licence: you bring your own where the vendor requires it. A beta driver has passed the gate on captured output from that OS, including the checks that must fail.

## Shipped

| Version | Date | What it added |
|---|---|---|
| [0.4.0](https://github.com/netdryrun/Netdryrun/releases/tag/v0.4.0) | 2026-10-31 | `verify_change` on FRR: declare what you meant to change, and anything else that changes in the routing state fails |
| [0.3.3](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.3) | 2026-10-30 | The default path for AI agents in sandboxes (open a PR, read a machine-readable verdict); `record` defaults. Affected by [GHSA-cg9f-xjw5-38ph](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-cg9f-xjw5-38ph) |
| [0.3.2](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.2) | 2026-10-28 | The agent contract: a frozen verdict schema, honest tool descriptions, evidence and a next step on every failure |
| [0.3.1](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.1) | 2026-10-28 | Fail closed: unreadable or incomplete state is an error, never a pass |
| 0.1.0 to 0.3.0 | 2026-10-27 | First public releases: CLI, GitHub Action, MCP server; FRR, SR Linux, SONiC, Arista cEOS |

## Current: 0.4.1

- The fix for [GHSA-cg9f-xjw5-38ph](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-cg9f-xjw5-38ph), plus the further fixes our weekly adversarial testing found before release. 0.3.3 and 0.4.0 are yanked once 0.4.1 is out.
- Cisco NX-OS (Nexus 9000v) and MikroTik RouterOS 7 (CHR), beta, bring your own image.
- Supply-chain hardening: dependencies pinned by hash, build provenance on releases, fuzzing of every output parser.
- A published compatibility matrix: each driver and the exact images it is verified on.

## Later (in this order, current plan)

- **0.4.2: one router-state contract** shared by the drivers that already pass the gate, so a check means the same thing on every OS.
- **0.4.3: Cumulus Linux, beta.**
- **0.5: check strength and signed verdict receipts.** [Check strength](disclosures/check-strength.md) runs a lab's checks against known-bad variants of the network and lists the ones every check still passes. A receipt records what was checked, the verdict, the evidence and how strong the checks were, so a reviewer can verify it offline.
- **0.6: hosted verification, beta.** Run a verdict without local Docker. The Apache-2.0 CLI, Action and MCP server stay the product and stay free.
- **After that, by demand:** OSPF and IS-IS adjacency checks, path and traceroute checks, EVPN, MPLS and segment routing, more drivers.

Want something moved up? [Open an issue](https://github.com/netdryrun/Netdryrun/issues) or [ask for a test of your own change](contact.md).
