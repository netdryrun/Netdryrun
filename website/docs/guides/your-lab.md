---
title: Add Netdryrun to the lab you already have
description: Ten minutes from an existing containerlab topology to a test for every change. Record the lab's steady state with netdryrun record, review it, add one negative check, and run it on every pull request with the GitHub Action.
---

# Add Netdryrun to the lab you already have (10 minutes)

You have a containerlab BGP lab: a `topology.clab.yml` and its router configs. This page turns it into a test that every later change has to pass, in four steps:

1. record the lab's steady state,
2. review what was recorded,
3. add one check for something that must never happen,
4. run it on every pull request.

The commands and output below are from a real run on Netdryrun™ 0.3.1, containerlab 0.81.1 and FRR 10.4.1 on WSL2, with the [`frr-bgp`](../examples.md#frr-bgp) example copied into a folder named `my-lab` standing in for your lab. The [tutorial](../tutorial.md) is the long version of the same path, with a failing change and the evidence it leaves.

## Before you start

- Netdryrun, Docker and containerlab on Linux or WSL2: see [Getting started](../getting-started.md#requirements). Or skip the install and use [GitHub Codespaces](../getting-started.md#try-it-in-your-browser), which has all three.
- Nodes Netdryrun can read: FRR (an image whose name contains `frr`), Nokia SR Linux, SONiC or Arista cEOS. Linux hosts in the lab are fine; they just aren't checked. For another FRR-based image, set `nodes.<node>.driver: frr` ([drivers](../reference/config.md#drivers)).
- A `name:` in the topology that no other running lab uses. Netdryrun deploys and destroys the lab itself.

The ten minutes assume the images are already pulled. Recording took 50 seconds here, and each run about 40.

## 1. Record the steady state

```text
$ netdryrun record my-lab/topology.clab.yml --deploy
Deploying lab ndr-my-lab, then waiting 45s for the network to converge...
recording r1 (frr)
recording r2 (frr)
recording r3 (frr)
Recorded 18 checks to /home/ndr/work/docs031/my-lab/netdryrun.yml. Review it, then: netdryrun run /home/ndr/work/docs031/my-lab
```

`record --deploy` deploys the lab, waits for BGP to converge (`--wait`, 45 seconds by default), writes `netdryrun.yml` next to the topology, and destroys the lab. Without `--deploy` it reads a lab that is already running. It writes one check for every established BGP session, every prefix count, and up to 50 BGP routes per node:

```yaml title="my-lab/netdryrun.yml (recorded)"
# Recorded by netdryrun 0.3.1 record on 2026-10-28T02:26:27+00:00.
# This is a baseline of the network's behavior when it was recorded. Review it before committing:
# remove anything that is allowed to change, and add negative checks (route present: false,
# ping expect: failure) for things that must never happen. Docs: https://netdryrun.com/reference/config/
lab: topology.clab.yml
timeout: 120
checks:
- type: bgp_session
  node: r1
  neighbor: 10.0.12.2
- type: bgp_prefixes
  node: r1
  neighbor: 10.0.12.2
  afi: ipv4-unicast
  min: 2
  max: 4
- type: bgp_session
  node: r1
  neighbor: 10.0.13.2
# ... 15 more: the same pattern for r2 and r3, plus one route check per learned LAN
```

!!! tip "A lab you just cloned"
    The recorded file is the lab's steady state, written down. `netdryrun run` deploys the lab from scratch and checks that it reaches that state again. That is useful on its own, before you test any change: after you clone a public lab, bump an image tag, or move the lab to another machine or to CI, a pass says the lab still converges the way it did when you recorded it. A failure names the session or route that didn't come back.

`record` reads BGP. Routes from OSPF, IS-IS, static or connected can be checked too: add `route` checks with `protocol: ospf` (or `isis`, `static`, `connected`) by hand. Checks for the OSPF and IS-IS adjacencies themselves are planned for 0.5.

## 2. Review it

A recorded baseline allows only modest growth: from 0.3.3 each prefix count is today's count as `min` and 20% more (at least 2) as `max` (0.3.2 and earlier recorded `exact`, which failed the day a site added a LAN). Decide what is allowed to change.

- **Keep** every `bgp_session` check.
- **Set the prefix ranges to the growth you expect**, for example `max: 10` where sites are added often. `max` stays a cheap leak guard. `--exact-prefixes` pins exact counts; `--min-prefixes` records minimums only.
- **Keep the standard guards** `record` adds: no default route and no link subnet via BGP on each BGP node. A prefix range has room for one leaked default route; the guard is what catches it.
- **Keep the route checks you care about**, and drop the rest.

Add `--attributes` to `record` if you also want each route's AS path, local preference and communities pinned.

## 3. Add one negative check

`record` writes down only what exists. It can't know what must never exist. Start with the leak that the usual checks miss, a default route arriving over BGP:

```yaml title="add under checks:"
- type: route          # nobody sends r1 a default route
  node: r1
  prefix: 0.0.0.0/0
  protocol: bgp
  present: false
```

It fails on a BGP default that r1 received, even one r1 doesn't select, which is why ping and session checks miss it ([the story](../posts/ping-missed-the-leak.md)). More guards to paste, such as link subnets kept out of BGP, a community that must survive, and a neighbor flooding you, are on [Guard recipes](../recipes.md).

Check the file without starting a lab. This is the tutorial's reviewed file, with the default-route check and one more for a link subnet:

```text
$ netdryrun validate my-lab
OK: my-lab/netdryrun.yml (13 checks, lab /home/ndr/work/docs031/my-lab/topology.clab.yml, 3 nodes)
  - [bgp_session] r1: BGP session to 10.0.12.2 is established
  - [bgp_session] r1: BGP session to 10.0.13.2 is established
  - [bgp_session] r2: BGP session to 10.0.12.1 is established
  - [bgp_session] r2: BGP session to 10.0.23.2 is established
  - [bgp_session] r3: BGP session to 10.0.13.1 is established
  - [bgp_session] r3: BGP session to 10.0.23.1 is established
  - [bgp_prefixes] r1: prefixes from 10.0.12.2 >= 2 and <= 10
  - [bgp_prefixes] r1: prefixes from 10.0.13.2 >= 2 and <= 10
  - [route] r1: route 192.168.2.0/24 via bgp is present
  - [route] r1: route 192.168.3.0/24 via bgp is present
  - [ping] r1: ping 192.168.3.1 from 192.168.1.1 expects success
  - [route] r1: route 0.0.0.0/0 via bgp is absent
  - [route] r1: route 10.0.23.0/30 via bgp is absent
```

Then run it: `netdryrun run my-lab`. On the unchanged lab, every check should pass. Then make your change and run it again. In the tutorial, a change that announced a new LAN with `redistribute connected` passed every session, the ping and the prefix range, and failed only a negative check:

```text
  [FAIL] r1: route 10.0.23.0/30 via bgp is absent -- unexpectedly present via bgp (0.3s)
Destroying lab...
FAILED: 12 passed, 1 failed (13 checks)
```

Exit code `1`, with the routing table and BGP table output that proved it in the report. [Read the evidence](../tutorial.md#6-read-the-evidence) shows the full report.

## 4. Run it on every pull request

Put the lab folder in your repository (here, `network/`) and add a workflow:

```yaml title=".github/workflows/network-dryrun.yml"
name: Network dry run
on:
  pull_request:
    paths:
      - "network/**"
permissions:
  contents: read
  pull-requests: write   # only for pr-comment
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.3
        with:
          path: network/
          pr-comment: true
```

Every pull request that touches `network/` now deploys the lab on the runner, runs the checks, posts the Markdown report as a comment, uploads `report.json`, and fails the job if a check fails. Make the job a required status check to block merges on a failure. Read the [Action security notes](../github-action.md#security-notes) before you run labs from forks.

## What a pass means

A pass says every check in the file held in the lab. It says nothing about behavior no check looks at, and a container lab isn't your production hardware or scale ([what a lab cannot prove](../trust.md#what-a-lab-cannot-prove)). The baseline and the guards are what make a pass worth something; review them like code.

## Next

- [Guard recipes and scenarios](../recipes.md): more negative checks, and failures the network must survive.
- [Tutorial](../tutorial.md): the same path with a failing change, the fix, and the full evidence.
- [AI agents](../ai-agents.md): let an agent run the same test before it proposes a change.
