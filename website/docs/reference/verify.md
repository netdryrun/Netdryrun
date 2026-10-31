---
title: verify (0.4, FRR only)
description: netdryrun verify compares a lab before and after a change. You declare what the change is meant to do; every other difference in routing behavior fails. Intent file, snapshot, verdicts and the netdryrun.verify/v1 report.
---

# verify

!!! note "0.4, FRR only"
    `netdryrun verify` is new in 0.4 and is not released yet. It snapshots FRR nodes only; SR Linux, SONiC and Arista EOS follow. A topology with a node of another kind is refused (exit code `2`).

Checks test what someone thought of. `verify` inverts that: **you declare what the change is meant to do, and every other difference in the network's behavior fails.**

```text
netdryrun verify topology.clab.yml --before <dir|git-ref> --after <dir|git-ref> --intent intent.yml [--json report.json]
```

It deploys the lab with the *before* configs, waits for a stable snapshot, destroys the lab, then does the same with the *after* configs (and runs the standing guards on that lab). Then it compares the two snapshots and matches every difference against the intent. Two cold boots: about 2 × 60 to 120 seconds. When the verdict would approve (INTENT MATCHED or NO BEHAVIOR CHANGE), each side boots a second time and must give the same snapshot; if one doesn't, nothing is approved: INCONCLUSIVE, listing every item that differed (`determinism` in the report). A side given as a directory that is also the name of a git ref is refused (exit 2): verify won't guess which is meant.

The same engine runs in three places: this command, the MCP tool [`verify_change`](#over-mcp-verify_change) for AI agents, and the GitHub Action's [`mode: verify`](#in-ci-the-actions-mode-verify) on pull requests.

## The verdict

| Status | Verdict | Exit code | Meaning |
|---|---|---|---|
| `matched` | `INTENT MATCHED` | `0` | Every difference is declared, and every declaration happened. |
| `no_change` | `NO BEHAVIOR CHANGE` | `0` | The snapshots are identical, running configs included, and the intent declares nothing. |
| `failed` | `UNDECLARED CHANGES: DO NOT APPLY` | `1` | A difference nobody declared, a declared change that didn't happen, or a standing guard that failed (`failed_because` says which). |
| `error` | `ERROR: NO VERDICT` | `2` | A bad intent, a different topology, a side that can't be read, an unreadable snapshot, or a lab problem. "Couldn't read" is never "nothing changed". |
| `inconclusive` | `INCONCLUSIVE` | `3` | A lab's state never stopped moving within `--timeout`. Retry at most once, then escalate: this says nothing about the change. |
| `unhealthy_baseline` | `INCONCLUSIVE: UNHEALTHY BASELINE` | `3` | BGP sessions are down in the *before* lab. Fix the baseline, or pass `--allow-unhealthy-baseline` to compare anyway. |

**Explained is not the same as safe.** The report echoes the declared intent at the top, for a human to review: an intent that declares a leak explains the leak. None of its verdicts is a pass of checks. A verdict covers the observed control-plane state of this lab (sessions, RIB, BGP paths and advertisements), nothing else.

**What "anything else fails" covers, exactly.** Declare what you intend to change; anything else that changes in the routing state that `verify` observes fails the run: on every FRR node, its running config, BGP sessions (established or not, remote AS, address families, soft-reconfiguration), the VRFs, routes of every protocol (selected, in the FIB, next hops, distance, metric), every BGP path with its attributes, and what each node advertises to and receives from each neighbor. Not covered, so an undeclared change there does not fail:

- nodes passed with `--unobserved` (hosts without a routing stack);
- communities on routes received before inbound policy (FRR doesn't list them there), and the attributes of a `default-originate` advertisement (its presence is compared);
- IGP adjacency state (OSPF, IS-IS): their routes are compared, their adjacencies are not;
- an update that arrives after the stretched `--settle` (several peers with long advertisement intervals in a row, `update-delay`);
- what a config change would do to routes or events this lab never produces (a prefix-list for prefixes the lab doesn't carry, `maximum-prefix`, dampening, timers, BFD, a password). The change itself is never silent: a config change with no observable effect fails, and an approval lists every changed config line "not tested if the lab doesn't exercise them" (see [config_change_on](#config_change_on));
- the data plane beyond what a standing guard's ping checks.

A lab that gives a different snapshot on a second boot approves nothing (INCONCLUSIVE). Changes that only a boot makes (management addresses, the random link-local addresses containerlab's MACs give) are not configuration changes and are not compared: an IPv6 link-local next hop is named by the lab node and interface that own it (`fe80::%peer1:eth1`), the same on every boot. A link-local next hop the node's own config names (a route-map's `set ipv6 next-hop local`, a static route) and no single lab interface owns keeps its address, so a typo in it is a difference; any other (a neighbour whose interfaces verify can't read, such as an unobserved SR Linux) is compared as `fe80::` with its interface.

**The intent must come from outside the change**: the ticket, the operator, or the base branch. A pass is never earned by copying the undeclared items into the intent. The report says who supplied it (`intent.supplied_by`: `cli` from the command line, `mcp` from an MCP caller, `action` from the GitHub Action). When the intent file itself differs between `--before` and `--after` (the change edits its own intent), every report carries the warning "intent edited in the same change: needs a code-owner review".

## Options

| Option | Default | |
|---|---|---|
| `--before`, `--after` | required | One side each: a git ref or a directory. A **git ref** is the repository's whole tree at that ref, and the topology file in it must be byte-identical to the one given (exit code `2` otherwise: verify compares configs on one topology). A **directory** stands for the folder that holds the topology and every file it binds (for `lab/topo/t.clab.yml` binding `../configs/r1.conf`, a copy of `lab/`, with `configs/r1.conf` in it). A directory wins over a ref of the same name. See [How each side is built](#how-each-side-is-built). |
| `--intent` | required | The intent file. |
| `--json FILE` | | Write the `netdryrun.verify/v1` report. |
| `--markdown FILE` | | Write a Markdown summary: the verdict, the declared intent, the undeclared items with their next diagnostics, the declarations that didn't happen and the guards. Lab text in it is inert (no HTML, links or mentions). The Action posts it as the PR comment. |
| `--intent-source` | `cli` | Who supplied the intent, echoed next to it (`cli` or `action`; the Action passes `action`). |
| `--guards FILE` | see below | The standing guards (a `netdryrun.yml`), run on the *after* lab; they must pass. Its `nodes:` settings (`driver`, `setup`) apply to both labs. See [Standing guards](#standing-guards). |
| `--config-dir DIR` | | With directory sides: the folder each directory stands for, relative to the topology (for example `configs`), when the directories hold only that folder. Every bind must then resolve inside it. With a git ref, it is only checked to exist in the ref. |
| `--unobserved NODE` | | A node without a routing stack (a host). Repeat for several. A node that runs FRR is refused: verify observes it. A node verify can't classify is an error, never silently skipped: a `linux` node with no known routing image, and the host kinds (`host`, `ext-container`, `k8s-kind`), are refused unless named here. Bridges are never observed. |
| `--settle` | `15` | Seconds between the two snapshots that must be identical. Stretched automatically to the longest advertisement interval (MRAI) a node reports, plus 2 s; must exceed any `update-delay` in the lab. |
| `--timeout` | `300` | Seconds to reach a stable snapshot, per lab. |
| `--hold` | `10` | The standing guards' hold window. |
| `--allow-unhealthy-baseline` | | Compare even when sessions are down in the *before* lab. |
| `--keep` | | Leave the *after* lab running, to run the `next_diagnostic` commands. |

### Standing guards

The standing guards catch what an intent can't: an intent that declares a leak explains the leak, and only a guard from the base branch fails it. They are read from the *before* side, never from the change:

| `--before` | `--guards` | Guards used | `guards_source` |
|---|---|---|---|
| git ref | not given | the `netdryrun.yml` next to the topology in that ref, when one exists | `before-ref` (or `none`) |
| git ref | given | that path, read from the ref (exit code `2` if it isn't there) | `before-ref` |
| directory | not given | none: a `netdryrun.yml` in the directory is not used | `none` |
| directory | given | that path | `explicit` |

With no guards, the report's `warnings` and the verdict line say "no standing guards ran".

### How each side is built

Each side is built in its own temporary folder, never shared with the other side or with your working tree: the whole repository tree at the ref (`git archive`), or the whole directory. Every bind and `startup-config` of the topology is then resolved inside that side's tree, the way containerlab resolves it: relative to the topology's folder, with `${VAR}`, `~`, `..` and symlinks followed.

- **A bind that resolves outside the side's tree is an error** (exit code `2`): an absolute path, `~/...`, a variable pointing elsewhere, or a symlink leading out would be the same file on both sides.
- A bound file missing from a side is an error. With a git ref, a bound file left out of `git archive` by `export-ignore` in `.gitattributes` is an error too, and the message says so.
- **Self-check before booting:** verify hashes every bound file on each side, checks that it holds that side's own bytes, and prints which bound files differ between the sides. If the sides differ in bound files but every bound file hashes the same in the two lab folders, it stops with "both sides resolved to the same configs" (exit code `2`).
- **No bound file differs: nothing to verify** (exit code `2`, before any boot). A change to a file the topology doesn't bind isn't in the lab, so there is nothing to compare.
- **Only an observed node's FRR config may differ** (`/etc/frr/<name>.conf`, except `vtysh.conf`). Any other bound file that differs is an error (exit code `2`, before any boot), naming it: FRR's `daemons` (shell that FRR's start script runs), `vtysh.conf`, a script, or the config of a node verify doesn't observe can change what runs without the snapshot judging it. Change such a file in a separate pull request, tested with checks.

## The intent file

One line per prefix or session, so a set of related differences is one line. A line without `vrf:` means the default VRF only.

```yaml
intent:
  - prefix: 10.101.0.0/24              # the customer's new block
    appears_on: [edge1, up1, peer1]
  - prefix: 203.0.113.0/24
    best_path_on: edge1
    to: {local_pref: 200}
  - session: {node: edge1, neighbor: 10.0.9.2, afi: ipv4-unicast}
    goes: down
  - prefix: 192.0.2.128/25
    disappears_from: [cust1]
allow_anywhere: ["10.200.*.0/24"]
```

`intent: []` declares that nothing changes. A file without `intent:`, an unknown key, a wrong type, a prefix with host bits, a session line without `afi:`, two lines about the same route on the same node, or a node that is not in the topology is an error (exit code `2`). The whole intent is validated before any lab boots.

### appears_on

The route is absent on each listed node before (no RIB entry, BGP path or received route), and after the change it is **selected and installed in the FIB** (`state: installed`, the default). `state: selected` accepts a selected route that isn't in the FIB; `state: received` expects it received but not selected. **A discard route is never `installed`:** a route with no next hop that forwards (a gateway or interface, active, in the FIB, and when recursive resolved by one that forwards) drops the traffic: a blackhole, reject or unreachable route (`ip route X Null0`, an anchor for a `network` statement), or a BGP route whose next hop resolves over one. It is declared `state: discard`, so the reviewer sees that the node drops traffic for the prefix.

The report shows, per node, where the new route was learned from, its next hop and AS path. `with:` pins any of them:

```yaml
intent:
  - prefix: 10.101.0.0/24
    appears_on: [up1]
    with: {from: 10.0.2.1, next_hop: 10.0.2.1, as_path: "65000 65101", protocol: bgp}
```

`with:` accepts `from`, `next_hop`, `as_path`, `origin`, `local_pref`, `med`, `weight`, `communities`, `ext_communities`, `large_communities`, `cluster_list`, `originator_id`, `protocol`, `distance` and `metric`. Each value must equal exactly; communities are the exact set.

It explains every new item for that prefix on the listed nodes, and every advertisement of the prefix *to* a listed node. An advertisement to any other neighbor, inside or outside the lab, needs its own line (see [advertisement](#advertisement)). Best-path changes on routes that already existed always need their own line.

### disappears_from

The route was **selected** on each listed node before, and after the change it has no RIB entry and no BGP path there. It explains those removals and the withdrawn advertisements to the listed nodes.

A route that was only received (kept by `soft-reconfiguration inbound`, not selected) is a different kind of difference. Removing `soft-reconfiguration inbound` makes those routes vanish, and that is a difference too. Declare it with `including_received_only: true`, which also accepts a route that was received-only before and requires that nothing of it is left.

### best_path_on

```yaml
intent:
  - prefix: 203.0.113.0/24
    best_path_on: edge1
    to: {local_pref: 200}
```

One meaning: **every listed value must equal exactly after the change, and every attribute not listed stays frozen.** If the winner changes to another neighbor's path, `from`, `next_hop` and the AS path change too, and each must be listed. At least one listed value must actually change. `to:` accepts `from`, `next_hop`, `as_path`, `origin`, `local_pref`, `med`, `weight`, `communities`, `ext_communities`, `large_communities`, `cluster_list` and `originator_id`.

It explains, on that node: the best flag moving between paths; changes to the new best path in the listed attributes only, to exactly the declared values (every other path, the old best included, stays frozen apart from its best flag); the BGP RIB entry's next hops (when `next_hop` is listed) or metric (when `med` is); and advertisements of the prefix, by the node or to it, that differ only in listed attributes and carry the new best path's values. A downstream node whose best path changes needs its own line. A lost backup path is never explained by a best-path line.

### session ... goes: down

```yaml
intent:
  - session: {node: edge1, neighbor: 10.0.9.2, afi: ipv4-unicast}
    goes: down
```

The session was established before, is still configured after, and isn't established. **A neighbor deleted from the config is a different difference, `session removed`**, which `goes: down` never covers (the line doesn't happen, and the removed session is undeclared). It covers both ends of that one session when both are lab nodes, and **only the routes learned over it**: the paths, received routes and advertisements over the session in its address family, and the RIB entries of prefixes that were learned only over it and are now gone. The report lists them. A failover to a backup path is a best-path change on that node and needs its own line; so does a route disappearing from another node. `afi:` is always required (one line per family), so the whole intent is validated before anything boots.

### advertisement

What one node advertises to one neighbor, including neighbors outside the lab: an outbound prepend, a `no-export`, a new advertisement toward a transit.

```yaml
intent:
  - prefix: 192.0.2.0/24
    advertisement: {node: edge1, neighbor: 198.51.100.9}
    to: {as_path: "65000 65000"}       # or: goes: added | removed
```

`to:` follows the `best_path_on` rule (listed exact, the rest frozen); `from` can't be set.

`goes: added` has an attribute limit too. **Without `with:`**, the new advertisement must carry the node's own best path for the prefix: no outbound rewrite. Its AS path, origin, MED, communities (standard, extended and large) and, where it is sent, local preference must equal the best path's. **With `with:`**, the listed attributes must equal the given values, and the rest still equal the best path's:

```yaml
intent:
  - prefix: 10.100.0.0/24
    advertisement: {node: edge1, neighbor: 198.51.100.9}
    goes: added
    with: {as_path: "65101 65101 65101", communities: [no-export]}   # an outbound prepend and no-export
```

`with:` accepts the `to:` attributes and goes with `goes: added` only. A node without a BGP best path for the prefix can't satisfy `goes: added`.

### allow_anywhere

```yaml
intent: []
allow_anywhere: ["10.200.*.0/24", {prefix: 10.9.0.0/16, vrf: cust}]
```

Accepts every difference for the listed prefixes, on every node: churn you accept. An entry is an exact prefix, or a glob:

- `*` stands for **one whole octet** (IPv4) or **one whole hextet** (IPv6), never part of one and never across octets. There are no other wildcards.
- **The prefix length is always explicit** and matched exactly: `10.200.*.0/24` matches `10.200.7.0/24`, not `10.200.7.0/25`.
- **At most /16 of wildcard reach for IPv4 and /48 for IPv6:** the first two octets (three hextets) are written literally. `10.200.*.0/24` and `2001:db8:1:*::/64` are accepted; `10.*.0.0/16`, `10.*/*` and `2001:db8:*::/48` are errors (exit code `2`).

It never matches by containment: `10.0.0.0/8` doesn't cover `10.1.0.0/16`. The report lists every route each entry explained (node, VRF and prefix, under `allowed[].routes`) and every item. Sessions are never covered.

`allow_anywhere` weakens the verdict, and every report that uses it carries a warning: a change that adds or widens it should need a second approver (CODEOWNERS). The CLI can't enforce that.

### config_change_on

```yaml
intent:
  - config_change_on: [edge1]
```

Each FRR node's running config is in the snapshot (see below), so a config change whose effect the lab can't show (a description, a policy for routes the lab doesn't carry, `maximum-prefix`, a timer) is still a difference: with nothing else declared on that node, it fails with "this change has no observable effect in the lab; test it with checks". `config_change_on` declares it for the listed nodes, when you accept that it is not tested. It explains only those nodes' config changes, and it didn't happen if a listed node's config is unchanged.

A config change on a node that a declared line names (and that happened) needs no `config_change_on`; a node a line doesn't name, such as one that only advertises the declared route, does. **Every approval lists each changed config line** (with the section headers above it, `router bgp 65000 > address-family ipv4 unicast > neighbor 10.0.2.2 maximum-prefix 5`) under "not tested if the lab doesn't exercise them": in the report (`untested_config`), the console, the PR comment and its header (`untested_config_lines`), and the MCP result. Read that list: a line there changed nothing this lab could observe.

## What is compared: the snapshot

After convergence, for every FRR node, in every VRF:

- **BGP sessions**: (neighbor, VRF) → established or not, ASNs, address families, local address. The raw FSM state (`active`, `connect`, `idle`) is kept in the evidence but never compared: a session going from `active` to `idle` is no change. Which address families have `soft-reconfiguration inbound` is compared too. Prefix counts are derived and never matched on their own.
- **VRFs**: the VRFs each node has. A VRF added or removed is a diff item (`kind: vrf`).
- **Routes, every protocol** (`kernel`, `connected`, `local`, `static`, `ospf`, `isis`, `bgp` and the rest): (VRF, AFI, SAFI, prefix, protocol) → selected or not, installed in the FIB or not, administrative distance, metric (the OSPF cost, for example), and the next hops with their resolution (recursive next hops keep the next hops that resolve them; IPv6 link-local next hops keep their interface).
- **Every BGP path per prefix**, not only the best: (neighbor or `local`, add-path ID) → best, multipath, valid, origin, AS path, next hops (accessible, IGP metric), local preference, MED, weight, standard, extended and large communities, cluster list, originator ID, atomic aggregate, aggregator.
- **Adj-RIB-Out per session**: what each node advertises to each established neighbor, with the advertised attributes, including neighbors that aren't lab nodes.
- **Received routes before inbound policy**, where `soft-reconfiguration inbound` keeps them.

Normalisation: AS_SEQUENCE order is kept and AS_SET is a sorted set; ASNs are asplain; well-known communities have one form (`no-export` is `65535:65281`); ECMP next-hop sets are compared as sets; absent attributes (MED, local preference) are compared as parsed, never replaced by defaults. Uptimes, timers, counters, table versions and interface indexes are never compared.

Strict reading: verify validates the device output against what it knows. An unknown field, a missing field, a VRF missing from one output, an address family verify doesn't snapshot (EVPN, VPN, labeled unicast) or an unnumbered BGP neighbor is an error (exit code `2`), never a smaller snapshot. The raw output of every command is kept in the report's evidence.

FRR commands: `show vrf`, `show bgp vrf all neighbors json`, `show ip route vrf all json`, `show ipv6 route vrf all json`, `show bgp vrf all ipv4|ipv6 unicast detail json`, and per established session `show bgp [vrf V] ipv4|ipv6 unicast neighbors N advertised-routes detail json` (plus `received-routes` where soft reconfiguration is on).

### Convergence

A snapshot is taken when two full snapshots `--settle` seconds apart are identical: every configured session established, or stably not established, on both samples (compared as established or not), prefix counts stable, and every route and path unchanged. Until then a node isn't ready while its RIB is empty or, if its config has `router bgp`, while it has no BGP state at all (no session and no BGP path: bgpd is answering but hasn't loaded its config). A session that is not established in the *before* snapshot makes the baseline unhealthy (exit code `3`) unless `--allow-unhealthy-baseline`.

**`--settle` stretches to the longest advertisement interval (MRAI) any node reports, plus 2 s, and to the conditional-advertisement timer plus 2 s where a node has an `advertise-map` (`bgp conditional-advertisement timer`, 60 s by default), and must exceed any `update-delay` in the lab.** Two snapshots `settle` apart can't see an update that arrives later than that, so a shorter `settle` could take the snapshot before the last update; the log says when it was stretched. A route that crosses several slow peers can take one interval per hop: raise `--settle` for that. A command that fails while daemons start is retried until `--timeout`; then the snapshot is unreadable (exit code `2`). If the snapshots never match within `--timeout`, the result is `inconclusive`, naming what kept moving.

## The report: netdryrun.verify/v1

JSON Schema: [verify-v1.json](https://netdryrun.com/schemas/verify-v1.json).

```json
{"schema": "netdryrun.verify/v1", "verdict": "UNDECLARED CHANGES: DO NOT APPLY", "status": "failed",
 "intent": {"source": "intent.yml", "supplied_by": "cli", "lines": ["10.101.0.0/24 appears on up1, peer1"]},
 "failed_because": ["undeclared"],
 "undeclared": [{"kind": "rib", "node": "edge1", "vrf": "default", "afi": "ipv4", "safi": "unicast",
                 "prefix": "10.101.0.0/24", "protocol": "bgp", "change": "added",
                 "route_before": "absent", "route_after": "selected and in the FIB",
                 "summary": "edge1 10.101.0.0/24 [bgp]: added",
                 "next_diagnostic": "docker exec clab-ndr-agent-demo-edge1 vtysh -c 'show ip route 10.101.0.0/24'"}],
 "not_happened": [], "declared": [], "allowed": [], "guards": null,
 "evidence": {"before": {"schema": "netdryrun.snapshot/v1"}, "after": {"schema": "netdryrun.snapshot/v1"}}}
```

(Abridged: every item also has `fields`, `before` and `after`, and the report has `run_id`, `warnings`, `baseline`, `timings` and more.) Undeclared items come first; each has one `next_diagnostic`, a read-only command for its node (run it on a lab kept with `--keep`). `not_happened` lists every declared change that didn't happen, with the reason. `declared` lists what each line explained.

## Over MCP: verify_change

AI agents call `verify_change(topology, before, after, intent, guards=None)` on the [MCP server](../ai-agents.md#verify-a-change-against-the-tickets-intent). It runs this same engine, nothing copied:

- `topology`, `before`, `after` and `guards` as on the command line (`C:\...` paths are accepted, as by every Netdryrun tool; use absolute paths). With `NETDRYRUN_MCP_ROOT` set, the topology, directory sides, the intent file and the guards must lie inside it.
- `intent` is the intent as YAML or JSON text (several lines, a JSON object, or text starting with `intent:` or `allow_anywhere:`), or the path of an intent file. The report records `intent_source: "mcp"` (and `intent.supplied_by: "mcp"`).
- The result is typed by [`mcp-result-v1.json`](https://netdryrun.com/schemas/mcp-result-v1.json) (`$defs/verify_result`): the verdict, status, the echoed intent, the warnings, up to 50 undeclared items with their `next_diagnostic` (`undeclared_total` counts all of them), what didn't happen, the guards, and `evidence_file`, the full `netdryrun.verify/v1` report written as `netdryrun-verify-report.json` next to the topology.

The intent should come from the ticket or the operator. An agent must never write it from the diff, or widen it (or add `allow_anywhere`) to make a change pass. Two lab boots: about 2 to 4 minutes.

## In CI: the Action's mode: verify

On a pull request, [the Action](../github-action.md#verify-a-change-against-its-intent-mode-verify) with `mode: verify` runs `verify` with the base branch as *before* and the PR merged into it (GitHub's merge commit, `github.sha`) as *after*, the intent file from the PR (`intent-file`, default `netdryrun-intent.yml`), and the base commit's `netdryrun.yml` as standing guards. **A PR that adds or edits the intent file fails** ("intent edited in this PR: requires a code-owner approval") unless the workflow sets `allow-intent-edit: true`, which it should do only where branch protection requires a code-owner review of that file. The PR comment shows the verdict, the echoed intent, the undeclared items and their next diagnostics.

## Nodes verify does not snapshot, and slow boots

verify 0.4 snapshots FRR nodes only. A node on any other platform (SR Linux, SONiC, Arista EOS, Juniper cJunosEvolved) is refused before a lab boots (exit code `2`), naming it. Pass `--unobserved NODE` to run without it: the lab still boots it, but **changes on that node are not compared**, and every output says so (a warning in the console, the Markdown summary, the JSON report and the MCP result). A Juniper collector for verify is planned for 0.4.1.

**Slow boots.** `--timeout` (default 300 s) is per lab, from the deploy to a stable snapshot. cJunosEvolved took 4 to 19 minutes to boot in our runs, and an approval boots each side twice, so a lab with a Junos node needs about `--timeout 1500` (the Action's `timeout` input) and a job timeout of about two hours; the MCP tool is a poor fit for such labs (client timeouts), so use the CLI or the Action. With the default, a node still booting never yields an approval: the sessions to it are down, which is an unhealthy baseline (exit code `3`) on the *before* side or a difference on the *after* side, and a lab that never settles is INCONCLUSIVE (exit code `3`). Don't pass `--allow-unhealthy-baseline` to get past a node that hasn't booted: with its sessions down on both sides, its routes are compared absent against absent.

## Not in 0.4

Topology changes; SR Linux, SONiC, Arista EOS and Juniper nodes (refused, or run as `--unobserved`); EVPN, VPN and labeled-unicast address families; unnumbered BGP sessions; the data plane beyond the standing guards' ping checks.
