---
title: Test a change on your own lab
description: A step-by-step tutorial. Take a containerlab topology you already have, record a baseline with netdryrun record, prune it, add negative checks, test a change, read the evidence, and run it in GitHub Actions.
---

# Test a change on your own lab

This tutorial takes a containerlab lab you already have and turns it into a test for every change. You will:

1. record a baseline of how the lab behaves today,
2. review and prune it,
3. add checks for things that must never happen,
4. make a change and run the test,
5. read the evidence when it fails,
6. run the same test in GitHub Actions.

It takes about 15 minutes. Every command and output below is from a real run (Netdryrun™ 0.3.1, containerlab 0.81.1, FRR 10.4.1, on WSL2).

## Before you start

You need Netdryrun, Docker and containerlab. See [Getting started](getting-started.md#requirements).

## 1. Your lab

Any containerlab topology works. Here, the bundled `examples/frr-bgp` lab stands in for "your lab": three FRR routers in a triangle, each in its own AS, each announcing one LAN prefix over eBGP.

```bash
git clone https://github.com/netdryrun/netdryrun
mkdir my-lab
cp -r netdryrun/examples/frr-bgp/configs netdryrun/examples/frr-bgp/topology.clab.yml my-lab/
sed -i 's/^name: ndr-frr-bgp/name: ndr-my-lab/' my-lab/topology.clab.yml
```

The folder now holds a topology and router configs, and no `netdryrun.yml`:

```text
my-lab/
  topology.clab.yml     # name: ndr-my-lab, nodes r1 r2 r3
  configs/
    daemons  r1.conf  r2.conf  r3.conf  vtysh.conf
```

The lab name (`name:` in the topology) must be unique on the machine. See [name collisions](troubleshooting.md#a-lab-named-x-is-already-running).

## 2. Record a baseline

`netdryrun record` deploys the lab, waits for BGP to converge, writes down what it sees, and destroys the lab.

```text
$ netdryrun record my-lab/topology.clab.yml --deploy
Deploying lab ndr-my-lab, then waiting 45s for the network to converge...
recording r1 (frr)
recording r2 (frr)
recording r3 (frr)
Recorded 18 checks to /home/ndr/work/docs031/my-lab/netdryrun.yml. Review it, then: netdryrun run /home/ndr/work/docs031/my-lab
```

This took 50 seconds. The file has one check for every established BGP session, every prefix count and every BGP route. The start of it:

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
  exact: 2
- type: bgp_session
  node: r1
  neighbor: 10.0.13.2
# ... 15 more: the same pattern for r2 and r3, plus one route check per learned LAN
```

## 3. Review and prune it

A recorded baseline says "nothing may change". That is rarely what you want. Decide what is allowed to change.

Here is what happens if you skip this step. The change in step 5 adds a LAN on r3, and its first attempt announces it with `redistribute connected`. Run against the raw baseline, the `exact: 2` prefix counts fail, because r1 and r2 now get 6 prefixes:

```text
$ netdryrun run my-lab
Netdryrun 0.3.1: 18 checks from my-lab/netdryrun.yml
Deploying lab ndr-my-lab (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (10.9s)
  ...
Convergence checks done; settling 10s before post-convergence checks...
  [FAIL] r1: prefixes from 10.0.12.2 = 2 -- 6 ipv4-unicast prefixes accepted (0.1s)
  [FAIL] r1: prefixes from 10.0.13.2 = 2 -- 6 ipv4-unicast prefixes accepted (0.1s)
  [FAIL] r2: prefixes from 10.0.12.1 = 2 -- 6 ipv4-unicast prefixes accepted (0.1s)
  [FAIL] r2: prefixes from 10.0.23.2 = 2 -- 6 ipv4-unicast prefixes accepted (0.1s)
  [PASS] r3: prefixes from 10.0.13.1 = 2 -- 2 ipv4-unicast prefixes accepted (held 10s, 5 samples) (10.1s)
  [PASS] r3: prefixes from 10.0.23.1 = 2 -- 2 ipv4-unicast prefixes accepted (held 10s, 5 samples) (10.1s)
Destroying lab...
FAILED: 14 passed, 4 failed (18 checks)
```

The test did its job: something changed. But adding a LAN is allowed, so the baseline should allow it. Edit the file:

- **Keep** every `bgp_session` check. Sessions must stay up.
- **Turn exact prefix counts into ranges.** `min: 2` keeps today's routes; `max: 10` still catches a leak that floods r1. You can also record ranges from the start with `netdryrun record --min-prefixes`.
- **Keep the route checks you care about.** This tutorial keeps r1's and removes the r2 and r3 copies to keep the file short.

## 4. Add negative checks

`record` only writes down what exists. It cannot know what must never exist. Add those checks yourself. For this lab:

- nobody sends r1 a default route,
- the point-to-point link subnets (`10.0.x.x/30`) stay out of BGP,
- and a ping, so the test proves traffic gets through, not only that routes exist.

The reviewed file:

```yaml title="my-lab/netdryrun.yml (reviewed)"
# Baseline recorded with `netdryrun record`, then reviewed by hand.
lab: topology.clab.yml
timeout: 120
checks:
# Every BGP session stays up (recorded).
- type: bgp_session
  node: r1
  neighbor: 10.0.12.2
- type: bgp_session
  node: r1
  neighbor: 10.0.13.2
- type: bgp_session
  node: r2
  neighbor: 10.0.12.1
- type: bgp_session
  node: r2
  neighbor: 10.0.23.2
- type: bgp_session
  node: r3
  neighbor: 10.0.13.1
- type: bgp_session
  node: r3
  neighbor: 10.0.23.1
# Prefix counts may grow when a site adds a LAN, but not past 10 (recorded as exact: 2, edited).
- type: bgp_prefixes
  node: r1
  neighbor: 10.0.12.2
  min: 2
  max: 10
- type: bgp_prefixes
  node: r1
  neighbor: 10.0.13.2
  min: 2
  max: 10
# Each LAN reaches the others (recorded routes; the r2 and r3 copies were removed to keep the file short).
- type: route
  node: r1
  prefix: 192.168.2.0/24
  protocol: bgp
- type: route
  node: r1
  prefix: 192.168.3.0/24
  protocol: bgp
# Added by hand: traffic gets through, not just routes.
- type: ping
  node: r1
  source: 192.168.1.1
  target: 192.168.3.1
# Added by hand: things that must never happen.
- type: route          # nobody sends r1 a default route
  node: r1
  prefix: 0.0.0.0/0
  protocol: bgp
  present: false
- type: route          # point-to-point link subnets stay out of BGP
  node: r1
  prefix: 10.0.23.0/30
  protocol: bgp
  present: false
```

Check it without starting a lab:

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

To check BGP attributes too (communities, AS path, local preference, MED, next hop), add `bgp_route` checks; see the [reference](reference/config.md#check-types).

Negative checks are [post-convergence checks](reference/config.md#convergence-semantics): they run after the positive checks pass and a settle time, and must hold for 10 seconds.

## 5. Make a change and run it

The change: r3 gets a second LAN, 192.168.33.0/24. A first attempt announces it with `redistribute connected`:

```diff title="configs/r3.conf (first attempt)"
 interface lo
  ip address 192.168.3.1/24
+ ip address 192.168.33.1/24
 !
@@
  address-family ipv4 unicast
   network 192.168.3.0/24
+  redistribute connected
```

Run it, and ask for the JSON and Markdown reports:

```text
$ cd my-lab
$ netdryrun run . --json report.json --markdown report.md
Netdryrun 0.3.1: 13 checks from netdryrun.yml
Deploying lab ndr-my-lab (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (13.8s)
  [PASS] r1: BGP session to 10.0.13.2 is established -- state is established (13.8s)
  [PASS] r2: BGP session to 10.0.12.1 is established -- state is established (13.8s)
  [PASS] r2: BGP session to 10.0.23.2 is established -- state is established (13.8s)
  [PASS] r3: BGP session to 10.0.13.1 is established -- state is established (13.8s)
  [PASS] r3: BGP session to 10.0.23.1 is established -- state is established (13.8s)
  [PASS] r1: route 192.168.2.0/24 via bgp is present -- active via bgp (13.8s)
  [PASS] r1: route 192.168.3.0/24 via bgp is present -- active via bgp (13.8s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (need 2) (13.8s)
Convergence checks done; settling 10s before post-convergence checks...
  [PASS] r1: prefixes from 10.0.12.2 >= 2 and <= 10 -- 6 ipv4-unicast prefixes accepted (held 10s, 4 samples) (10.0s)
  [PASS] r1: prefixes from 10.0.13.2 >= 2 and <= 10 -- 6 ipv4-unicast prefixes accepted (held 10s, 4 samples) (10.0s)
  [PASS] r1: route 0.0.0.0/0 via bgp is absent -- absent (held 10s, 4 samples) (10.0s)
  [FAIL] r1: route 10.0.23.0/30 via bgp is absent -- unexpectedly present via bgp (0.3s)
Destroying lab...
FAILED: 12 passed, 1 failed (13 checks)
  wrote json report: report.json
  wrote markdown report: report.md
```

The run took 41 seconds and exited with code `1`. Sessions are up, the ping works, and the prefix count is inside its range. Only the negative check caught the problem: `redistribute connected` also announces r3's link subnets.

## 6. Read the evidence

### Markdown report

`report.md` is the text the GitHub Action puts on the job page and in the PR comment. Failures come first, and each failure has the raw output of every command it ran in a collapsed block (here, the routing table and the BGP table):

````markdown title="report.md"
### ❌ Netdryrun failed

**12 passed, 1 failed** on lab ` ndr-my-lab `

| | Check | Result | Time |
|---|---|---|---|
| ❌ | r1: route 10.0.23.0/30 via bgp is absent | unexpectedly present via bgp | 0.3s |
| ✅ | r1: BGP session to 10.0.12.2 is established | state is established | 13.8s |
...
| ✅ | r1: route 0.0.0.0/0 via bgp is absent | absent (held 10s, 4 samples) | 10.0s |

<details><summary>Evidence: r1: route 10.0.23.0/30 via bgp is absent</summary>

` r1$ vtysh -c show ip route 10.0.23.0/30 json `

```
{
  "10.0.23.0/30":[
    {
      "prefix":"10.0.23.0/30",
      "prefixLen":30,
      "protocol":"bgp",
      "vrfId":0,
      "vrfName":"default",
      "selected":true,
      "destSelected":true,
      "distance":20,
      "metric":0,
      "installed":true,
      "table":254,
      "internalStatus":16,
...
```

` r1$ vtysh -c show bgp ipv4 unicast 10.0.23.0/30 json `

```
{
  "prefix":"10.0.23.0/30",
  "version":4,
  "advertisedTo":{
    "10.0.12.2":{
      "hostname":"r2"
    },
    "10.0.13.2":{
      "hostname":"r3"
    }
  },
  "pathCount":2,
  "paths":[
    {
      "aspath":{
...
      "bestpath":{
...
      "bestpath":{
...
```

</details>

<sub>netdryrun 0.3.1 · containerlab 0.81.1 · 2026-10-28T02:27:25+00:00 · full evidence in the JSON report</sub>
````

### JSON report

`report.json` has everything ([schema](reference/cli.md#json)). The top level says what ran and where:

```json
{"schema": "netdryrun.report/v1", "status": "failed", "lab": "ndr-my-lab", "error": null, "inconclusive_reason": null,
 "summary": {"passed": 12, "failed": 1, "total": 13}}
```

`environment` records the versions and images, so a result can be reproduced:

```json
"environment": {
  "netdryrun": "0.3.1",
  "containerlab": "0.81.1",
  "python": "3.10.12",
  "host": "Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.35",
  "nodes": {
    "r1": {"kind": "linux", "image": "quay.io/frrouting/frr:10.4.1"},
    "r2": {"kind": "linux", "image": "quay.io/frrouting/frr:10.4.1"},
    "r3": {"kind": "linux", "image": "quay.io/frrouting/frr:10.4.1"}
  }
}
```

The failed check, with its history of samples:

```json
{
  "name": "r1: route 10.0.23.0/30 via bgp is absent",
  "type": "route",
  "params": {"node": "r1", "prefix": "10.0.23.0/30", "protocol": "bgp", "present": false},
  "passed": false,
  "detail": "unexpectedly present via bgp",
  "attempts": 1,
  "duration_s": 0.3,
  "started": "2026-10-28T02:27:55+00:00",
  "history": [{"t": 0.3, "passed": false, "detail": "unexpectedly present via bgp"}]
}
```

Its `evidence` holds the command and the full output. The interesting part: the route is selected, installed, and points at r3 (`10.0.13.2`):

```json
{
  "10.0.23.0/30":[
    {
      "prefix":"10.0.23.0/30",
      "protocol":"bgp",
      "selected":true,
      "installed":true,
      "nexthops":[
        {"ip":"10.0.13.2", "interfaceName":"eth2", "active":true}
      ]
    }
  ]
}
```

(Shortened; the report keeps every field.)

To look at the routers yourself, rerun with `--keep-on-failure` and run commands with `docker exec clab-ndr-my-lab-r1 vtysh -c "..."`, then destroy the lab with the command Netdryrun prints. [Troubleshooting](troubleshooting.md#the-lab-never-converges-timeout) has an example.

## 7. Fix the change and run again

Announce only the new LAN, with a `network` statement:

```diff title="configs/r3.conf (fixed)"
 interface lo
  ip address 192.168.3.1/24
+ ip address 192.168.33.1/24
 !
@@
  address-family ipv4 unicast
   network 192.168.3.0/24
+  network 192.168.33.0/24
```

Add a check that the change did what it should, so the test also proves the new LAN arrives:

```yaml
# Added with the change: the new LAN reaches r1.
- type: route
  node: r1
  prefix: 192.168.33.0/24
  protocol: bgp
```

```text
$ netdryrun run . --json report.json --markdown report.md
Netdryrun 0.3.1: 14 checks from netdryrun.yml
Deploying lab ndr-my-lab (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (13.9s)
  [PASS] r1: BGP session to 10.0.13.2 is established -- state is established (13.9s)
  [PASS] r2: BGP session to 10.0.12.1 is established -- state is established (13.9s)
  [PASS] r2: BGP session to 10.0.23.2 is established -- state is established (13.9s)
  [PASS] r3: BGP session to 10.0.13.1 is established -- state is established (13.9s)
  [PASS] r3: BGP session to 10.0.23.1 is established -- state is established (13.9s)
  [PASS] r1: route 192.168.2.0/24 via bgp is present -- active via bgp (13.9s)
  [PASS] r1: route 192.168.3.0/24 via bgp is present -- active via bgp (13.9s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (need 2) (13.9s)
  [PASS] r1: route 192.168.33.0/24 via bgp is present -- active via bgp (13.9s)
Convergence checks done; settling 10s before post-convergence checks...
  [PASS] r1: prefixes from 10.0.12.2 >= 2 and <= 10 -- 3 ipv4-unicast prefixes accepted (held 10s, 4 samples) (10.2s)
  [PASS] r1: prefixes from 10.0.13.2 >= 2 and <= 10 -- 3 ipv4-unicast prefixes accepted (held 10s, 4 samples) (10.2s)
  [PASS] r1: route 0.0.0.0/0 via bgp is absent -- absent (held 10s, 4 samples) (10.2s)
  [PASS] r1: route 10.0.23.0/30 via bgp is absent -- absent (held 10s, 4 samples) (10.2s)
Destroying lab...
PASSED: 14 passed, 0 failed (14 checks)
  wrote json report: report.json
  wrote markdown report: report.md
```

41 seconds, exit code `0`. Commit the change and the updated `netdryrun.yml` together.

## 8. Run it on every pull request

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

Every pull request that touches `network/` now deploys the lab on the runner, runs the checks, posts the Markdown report as a comment, uploads `report.json` as an artifact, and fails if any check fails. Make the job a required status check in your branch protection to block merges on a failure.

On GitHub-hosted runners, the `frr-bgp` example's CI job (install containerlab, pull the FRR image, run its checks including a link-failure scenario; measured on 0.2.0) takes 100 to 107 seconds. Before you open a PR with untrusted contributors, read the [Action security notes](github-action.md#security-notes).

## Next

- [netdryrun.yml reference](reference/config.md): every check type, including `ping` with `expect: failure` and failure scenarios (`link_down`).
- [Troubleshooting](troubleshooting.md): errors you may hit and how to fix them.
- [AI agents](ai-agents.md): let an agent run the same test before it proposes a change.
