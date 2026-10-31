---
title: Ping and "BGP up" passed. The route leak was still there.
description: A one-line default-originate change leaks a default route. Every BGP session stays up and every ping answers, because the router receives the route but doesn't select it. The lab, the commands, the evidence, and what a lab can't prove.
---

# Ping and "BGP up" passed. The route leak was still there.

*2026-10-28 · Netdryrun™ 0.3.1, containerlab 0.81.1, FRR 10.4.1*

A one-line change makes a router send its neighbor a default route. After the change, both BGP sessions are established and the ping between the LANs answers. A test made of those checks reports a pass. The leaked default is in the neighbor's routing table anyway, received but not selected, waiting for the day the route it loses to goes away.

This post walks through that case with the bundled [`frr-bgp-broken`](../examples.md#frr-bgp-broken) example: the lab, the change, the commands, the evidence, and what a lab run like this can and can't tell you. Everything quoted is real output from the runs named next to it.

## The lab and the change

Three FRR routers in a triangle, each in its own AS, each announcing one LAN over eBGP: r1 (AS 65001, `192.168.1.0/24`), r2 (AS 65002, `192.168.2.0/24`) and r3 (AS 65003, `192.168.3.0/24`). The example is the [`frr-bgp`](../examples.md#frr-bgp) lab with one change in r2's config, [`r2-bad.conf`](https://github.com/netdryrun/Netdryrun/blob/main/examples/frr-bgp-broken/r2-bad.conf):

```text title="r2-bad.conf"
router bgp 65002
 ...
 address-family ipv4 unicast
  network 192.168.2.0/24
  ! The bad change: someone added default-originate toward r1
  neighbor 10.0.12.1 default-originate
```

`default-originate` makes r2 announce `0.0.0.0/0` to r1 whether or not r2 has a default route itself. Toward a customer that is sometimes intended. Toward a peer, or a router that has its own way out, it offers to carry all traffic that has no more specific route.

## The checks

The example's [`netdryrun.yml`](https://github.com/netdryrun/Netdryrun/blob/main/examples/frr-bgp-broken/netdryrun.yml) has six checks, all on r1: both BGP sessions established, between 1 and 10 prefixes from r2, a route to r3's LAN, a ping from r1's LAN to r3's, and one negative check:

```yaml
- type: route        # nothing should send r1 a default route
  node: r1
  prefix: 0.0.0.0/0
  protocol: bgp
  present: false
```

## The run

On Linux or WSL2 with Docker and containerlab:

```bash
pipx install netdryrun
git clone https://github.com/netdryrun/Netdryrun && cd netdryrun
netdryrun run examples/frr-bgp-broken
```

This output is from the re-recorded [FRR CI guide](../guides/frr-ci.md#3-run-it-locally):

```text
Netdryrun 0.3.1: 6 checks from examples/frr-bgp-broken/netdryrun.yml
Deploying lab ndr-frr-broken (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (13.5s)
  [PASS] r1: BGP session to 10.0.13.2 is established -- state is established (13.5s)
  [PASS] r1: route 192.168.3.0/24 via bgp is present -- active via bgp (13.5s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (need 2) (13.5s)
Convergence checks done; settling 10s before post-convergence checks...
  [PASS] r1: prefixes from 10.0.12.2 >= 1 and <= 10 -- 3 ipv4-unicast prefixes accepted (held 10s, 5 samples) (10.1s)
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.2s)
Destroying lab...
FAILED: 5 passed, 1 failed (6 checks)
```

Exit code `1`. In the 0.3.1 release check, the same example took 39 seconds from deploy to destroy, with the images already pulled ([`live.json`](https://github.com/netdryrun/Netdryrun/blob/main/releases/0.3.1/gate/live.json)).

## The diff against a ping-only check

Five of the six checks passed. Split them by what a common pre-change test looks at:

| Check | Result | Ping-only test | Sessions-up test | This file |
|---|---|---|---|---|
| ping 192.168.3.1 from 192.168.1.1 | pass | ✓ | | ✓ |
| BGP session to r2 established | pass | | ✓ | ✓ |
| BGP session to r3 established | pass | | ✓ | ✓ |
| route to r3's LAN present | pass | | | ✓ |
| 1 to 10 prefixes from r2 | pass (3 accepted) | | | ✓ |
| no default route via BGP | **fail** | | | ✓ |
| **Verdict** | | **pass** | **pass** | **fail** |

A test made only of the ping, or only of the sessions, would have run on this same lab and passed this change. The prefix ceiling passed too: the leak added one prefix (2 became 3), well inside a range that leaves room for growth. Only the check that names the forbidden route failed.

Why the ping still works: the LANs have more specific routes, so a default changes nothing for traffic between them. And r1 doesn't even select the leaked default: containerlab gives each node a default route through its management network, which FRR sees as a kernel route with distance 0, and that beats BGP's 20. So forwarding on r1 is exactly what it was before the change.

The same pattern shows up in the [verdict corpus](../corpus.md), a benchmark of BGP changes the maintainers wrote on one FRR topology, with expected verdicts committed before any run. In [case 17](../corpus/17-default-leaked-to-peer.md), `default-originate` toward a peer, the ping-only and all-sessions-up strategies approved the change and Netdryrun's intent checks rejected it.

## The evidence

The run with `--json report.json` writes every command and its raw output next to each check. The verdict as the [MCP server](../ai-agents.md#result-and-verdict) returns it for this example, shortened to the failed check:

```json
{
  "status": "failed",
  "passed": 5,
  "failed": 1,
  "error": null,
  "inconclusive_reason": null,
  "lab": "ndr-frr-broken",
  "checks": [
    {"name": "r1: route 0.0.0.0/0 via bgp is absent", "passed": false,
     "detail": "unexpectedly present via bgp (not selected)"}
  ],
  "evidence_file": "/path/to/lab/netdryrun-report.json",
  "verdict": "DO NOT APPLY THIS CHANGE"
}
```

The raw output behind a "(not selected)" verdict looks like this. This excerpt is from a different lab with the same leak: a peer router, `peer1`, received an upstream's default route (a validation run on Netdryrun 0.3.0, committed as the test fixture [`report-real-failed-leak.json`](https://github.com/netdryrun/Netdryrun/blob/main/tests/fixtures/report-real-failed-leak.json). The report stores `output` as the command's text; here it is parsed and shortened to the fields that matter):

```json
{
  "node": "peer1",
  "cmd": "vtysh -c show ip route 0.0.0.0/0 json",
  "rc": 0,
  "output": {
    "0.0.0.0/0": [
      {"protocol": "bgp", "distance": 20,
       "nexthops": [{"ip": "10.0.3.1", "interfaceName": "eth1", "active": true}]},
      {"protocol": "kernel", "selected": true, "installed": true, "distance": 0,
       "nexthops": [{"ip": "172.20.20.1", "interfaceName": "eth0", "active": true}]}
    ]
  }
}
```

Two entries for `0.0.0.0/0`. The BGP one, from the neighbor at `10.0.3.1`, has no `selected` or `installed`. The kernel one, containerlab's management default through `eth0`, is selected and installed. A check that asks "what does the router forward with?" sees only the kernel route. Netdryrun's `present: false` counts any BGP path the router received, selected or not, and fails.

To look at it yourself, rerun with `--keep-on-failure` and query the router, then destroy the lab with the command Netdryrun prints:

```bash
netdryrun run examples/frr-bgp-broken --keep-on-failure
docker exec clab-ndr-frr-broken-r1 vtysh -c "show ip route 0.0.0.0/0"
docker exec clab-ndr-frr-broken-r1 vtysh -c "show bgp ipv4 unicast 0.0.0.0/0"
```

## Why it matters if nothing changed

In this lab the leak is harmless today. It stops being harmless when the route it loses to goes away: a link fails, someone cleans up a static default, a device without a management default runs the same config. Then the received default becomes the best route, and all traffic with no more specific route goes to the neighbor that leaked it. The [hidden-leak lab](https://github.com/netdryrun/Netdryrun/tree/main/examples/srl-hidden-leak) shows the same leak on Nokia SR Linux and FRR, how to see it by hand in each CLI, and what happens when the static default goes away.

A static analyzer such as Batfish also catches this particular leak, from the configs alone. The [Batfish page](../batfish.md) shows a leak it misses and the lab catches.

## Try it without installing anything

[Open Netdryrun in GitHub Codespaces](https://codespaces.new/netdryrun/Netdryrun?quickstart=1) and click **Create codespace**. It comes with Docker, containerlab and Netdryrun, and pulls the FRR image. When the terminal shows `Ready`, run:

```bash
netdryrun run examples/frr-bgp-broken
```

It uses your GitHub account's free Codespaces hours (2-core machine). Stop or delete the codespace when you're done.

To add the same check to a lab you already have, see [Add Netdryrun to the lab you already have](../guides/your-lab.md). More guards like this one are on [Guard recipes](../recipes.md).

## What a lab can't prove

This run shows one thing: in this lab, with these configs, r1 received a default route over BGP that it shouldn't have, and the check that names it caught it. It does not show:

- **That your network is free of leaks.** The check knows about `0.0.0.0/0` and nothing else. A leak of any other prefix needs its own check, or a prefix ceiling tight enough to notice it. A pass covers the checks in the file and nothing more.
- **That your vendor behaves like FRR.** The lab ran FRR containers. Route selection, defaults and timers on the routers you run in production can differ.
- **Behavior at production scale.** Three routers and a handful of prefixes say nothing about full tables, many peers, hardware or ASIC limits, or convergence time at scale.
- **What production traffic would do.** Ping tests a path between two addresses you choose; it's evidence for that path only.

More in [what a lab cannot prove](../trust.md#what-a-lab-cannot-prove). A lab run is evidence for one change in one lab, and a reviewer can read every command and output behind it.
