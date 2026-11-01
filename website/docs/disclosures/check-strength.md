---
title: "Check strength: measuring network checks against known-bad variants (defensive publication)"
description: "A dated technical disclosure of check strength: run a network lab's checks against known-bad variants of the network, and report which variants every check still passes. Published so the method is available to everyone as prior art."
---

# Check strength: measuring network checks against known-bad variants

**Defensive publication by the Netdryrun project.** First made public at netdryrun.com on the date in this page's git history and archive copies. It is meant to make the method below available to everyone as prior art, so that anyone can use it. A publication can't guarantee what a patent office does, but it can be cited against claims on what it discloses. The implementation is open source (Apache-2.0) at [github.com/netdryrun/Netdryrun](https://github.com/netdryrun/Netdryrun).

## Problem

Network changes are increasingly tested, by people and by AI agents, in a lab of real network-operating-system software booted from the team's own configurations. The tests are checks such as:

- "BGP session X is established";
- "between N and M prefixes are received from neighbour Y";
- "route Z is present" and "route W is absent";
- "the best path to P has local preference 200".

A pass only means these checks passed. If they are weak, a broken change passes too. Checks written by hand, generated from today's state, or written by an AI agent can all be weak in ways nobody notices until a real fault gets through. Netdryrun had exactly this failure: a generated prefix-count range let a leaked customer prefix pass ([advisory GHSA-cg9f-xjw5-38ph](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-cg9f-xjw5-38ph)).

## Method

Check strength measures a set of network checks by running them against known-bad variants of the network itself, and reports which variants every check still passes. It is mutation testing aimed at the network instead of program code.

### 1. Baseline

Boot the lab, or use a running one, and run the checks. Every check must pass. If one fails, stop with no strength result.

Then take a **baseline snapshot**: sessions and their states; routes of every protocol in every VRF and address family; and every BGP path with its attributes (AS path, next hop, local preference, MED, communities, origin). Where a platform can't list every received path, use the best path per prefix plus the received count, and say so in the result.

**Convergence** is N identical canonical samples (for example 3) taken a positive minimum gap apart: the larger of the BGP advertisement interval (MRAI) and a floor such as 5 s, because the iBGP MRAI is often 0. It must happen within a timeout (for example 90 s). Hitting the timeout is an error, not a result.

**Canonical form** keeps only routing facts. It sorts unordered collections (the set of routes, sessions and paths, communities, AS_SET members) and keeps ordered sequences in order (AS_PATH sequences, cluster lists, segment lists), so two different paths never compare equal. It drops uptimes, timers, ages, LSA ages, counters, path identifiers, and the router-local tie-break on route age (the oldest-external rule), so two samples of the same routing state do compare equal.

### 2. Variants from the lab's own configuration

Variants come only from the lab's configuration and its checks: never from the change under test, never as free text. Each variant is data:

- the node;
- what the variant does;
- the commands that apply it and the commands that revert it;
- the configuration lines that prove it took effect;
- its **footprint**.

The footprint is the variant's own mechanism: the locally originated route entry for each prefix the variant originates, **on the originating node only**. The same prefix learned on any other node is an effect, not footprint. So is an accepted prefix-count change at a neighbour, and so is the route on the originating node itself when it was learned, not originated. The node's advertisements of its own footprint, and copies a receiver holds but its policy rejected (pre-policy, received-only), are not effects. Effects are read from post-policy state. So a leak that is accepted anywhere always shows an effect, and a leak the receiving policy rejects is **no effect**: the policy did its job, and that is not a blind spot.

Variant kinds, with concrete operators:

- **customer_leak.** A BGP speaker announces extra /24 prefixes from address space no config or check names (for example 100.64.0.0/10 shared space), originated with a discard (blackhole) static and a `network` statement in the session's address family and VRF. For every prefix-count check with range [L, U] on that session, given today's count C, emit a **paired range variant**: one leak of U−C prefixes, inside the range (skipped when U equals C), and one of U−C+1, just outside it. If the measured count at the neighbour reaches U+1 and every check still passes, the range check isn't doing its job. If the extra prefixes never arrive, the variant is judged by its effect like any other. Also leak 1 and 2 prefixes.
- **import_filter.** Edit an inbound route-map or prefix-list. Each variant is a candidate whose effect is judged from the snapshot, not assumed:
  - deleting one `match` condition: same-type matches in one clause are ORed and different types are ANDed, so this can widen or narrow what the clause matches;
  - deleting a `deny` clause, which usually widens what is accepted;
  - deleting a `permit` entry of a prefix-list, which usually drops routes;
  - swapping permit and deny.
  When the neighbour is itself a lab node and today's state shows nothing the filter blocks, first compose the edit with a one-prefix leak from that neighbour that the filter would block, so the variant has something to act on. Where the neighbour already sends routes the filter drops, the edit takes effect on its own.
- **session_down.** `neighbor X shutdown`, one per session that carries prefixes; also BFD down with the link left up, where BFD is configured.
- **link_down.** One link of the topology down, one per link.
- **attribute_drift.** Change a `set local-preference` on an inbound route-map to a value that changes the best path. Local preference isn't sent to eBGP neighbours, except confederation peers, so an outbound local-preference change toward plain eBGP is skipped. Also: delete a `set community` (including no-export and graceful-shutdown) or a `set as-path prepend`; add `set local-preference 50` to an inbound permit clause that sets none; remove `next-hop-self` on an iBGP session.
- **default_leak** and **link_subnet_leak.** Originate 0.0.0.0/0 (::/0 for IPv6), or a link subnet, into BGP.
- **more_specific.** Announce a more-specific inside an aggregate the lab carries.
- **max_prefix_edge.** Announce max-prefix limit + 1 where a limit is configured, and remove the limit.

A budget (for example 8 variants) is filled round robin across kinds, taking the first variant of each kind first. Kinds with no eligible variant are skipped and listed as "not generated" in the result.

### 3. For each variant

1. Apply it.
2. Confirm it took effect. The running configuration must show exactly the lines the variant removes and adds; a link_down or session_down must show the state change. If it didn't take effect, that's an error, never "no effect".
3. Wait for convergence, snapshot, and run the checks.
4. **Always revert**, whatever happened, by command, configuration rollback or redeploy.
5. Wait for convergence, snapshot, and run the checks again.

Every step has a timeout. A timeout in apply, convergence, the checks or the revert is an error.

### 4. Verify the restore

The canonical post-revert snapshot must equal the baseline, and every check must pass again. Otherwise the whole run stops with an error, because later variants would run on a different network. Restore is checked, never assumed.

### 5. Classify each variant

The **effect** is the canonical difference between the variant's snapshot and the baseline, outside its footprint. A **catching failure** is a check result that meets all of these:

- the same check passed at the baseline and passes again after the restore;
- it failed on this variant;
- the result is one-per-check and fresh: started after the variant was applied and confirmed;
- it has usable device state and evidence from this run showing the variant's effect;
- it doesn't depend only on naming the variant's own invented prefixes.

The baseline pass and the restored pass are what tie the failure to the variant rather than to a fault that already existed. The classes are exhaustive:

| Effect | Checks | Class |
|---|---|---|
| yes | at least one catching failure | **caught** |
| yes | all pass | **survived** (a blind spot, reported with the effect nobody noticed) |
| yes | no catching failure, but some checks failed without counting (no evidence, no usable state, or fitted only to the invented prefixes); the rest passed | **survived**, with those failures noted |
| no | all pass | **no effect** (an equivalent variant: never counted as caught or survived) |
| no | any failure | **inconclusive** (a flaky check, or state the snapshot doesn't see) |

A run with no variant, or none with an effect, has no strength result, never "caught 0 of 0", and exits 2. Results are attributed per check: which checks failed for which variant.

### 6. Report

The summary is always "caught N of M known-bad variants (K no effect, J inconclusive, kinds not generated: …)", never "your checks are complete".

For each survivor, the report suggests a check written from the baseline state. Examples: the exact prefix set or count a session carries today, a route that must stay or stay absent, a best path's attributes. A suggestion never pins the variant's own invented prefixes. It can be re-run against that survivor to prove it catches it. Suggestions are text for a human or agent to review: the tool never edits the checks.

Exit codes: 0 when at least one variant had an effect and none survived; 1 when anything survived; 2 on any setup, apply, timeout, restore or internal error, and when no variant had an effect.

## Uses and variations (all disclosed here)

**Interfaces.** A CLI command; a CI step that fails or warns when a variant survives; and an MCP or other tool-call interface for AI agents. An agent writes or generates checks, calls the tool, reads the survivors and suggestions, adds checks, and calls again until nothing survives or a human accepts what remains. Results can gate or annotate other outputs: a signed verdict receipt, a pull-request comment, a dashboard, a change ticket.

**What gets measured.** Checks recorded from a known-good lab, measured before they're trusted. A must-fail variant at the edge of every tolerance a generator introduces. Mutating the checks or their expected values, as well as the network: boundary values, property-based generation, metamorphic relations between the baseline and mutated runs.

**Where it runs.** Any network-operating-system software in containers, virtual machines, emulators or hardware labs. Also against model-based verifiers (configuration analysis, simulation) instead of running software, or across both, comparing their classifications.

**Protocols and operators beyond BGP:**

- **OSPF and IS-IS:** change an interface metric; set overload or max-metric; make an interface passive; change the area type or level; remove a redistribution filter.
- **EVPN:** withdraw a type-3 route, leak a type-5 route, edit a route target or ESI.
- **MPLS and segment routing:** remove a label binding, change an SR policy preference.
- **Static routes:** delete one, change its next hop.
- **ACLs and firewall policy:** delete an entry, swap permit and deny.
- **NAT:** delete a rule.
- **Multicast:** remove an RP or a join.
- **Interfaces:** take a LAG member down, change an MTU.
- **Data plane:** measured with ping, traceroute or packet probes and correlated with control-plane state.
- **BGP across all address families**, including RPKI-invalid announcements and AS-path changes that flip the best path.

**How variants are applied.** As configuration edits, runtime commands, link or node faults, routes injected by an emulated peer, or by booting the lab again with mutated configuration files instead of applying and reverting live. Variants can run in parallel in separate lab copies, or from snapshots and checkpoints of a lab.

**How variants are chosen.** Generated from configuration, from the checks' tolerances, from a library of incident patterns, from past outages or production telemetry, or proposed by a model that suggests plausible faults. They can be weighted or ranked by likely harm (for example a more-specific or a customer route over a transit route), by topology position, or by which checks they exercise, then selected under a time budget.

**Scores.** Per check, per kind and over time, including severity-weighted scores and partial detection. Minimising a check suite while keeping the same set of caught variants.

## Prior art we know of

This publication describes a combination of steps. Related public work:

- mutation testing in software (Andrews et al., 2006; the Jia and Harman survey);
- NetCov (NSDI 2023), which defines configuration coverage by mutation and sets it aside as hard to compute and interpret;
- Yardstick (SIGCOMM 2021);
- fault injection to validate alerts and monitoring (chaos engineering);
- emulation-based change testing (CrystalNet, SOSP 2017).
