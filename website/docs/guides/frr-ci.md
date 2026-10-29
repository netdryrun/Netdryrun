---
title: Test an FRR change in CI
description: Boot your FRR routers in containerlab on every pull request, apply the change, and fail the job if routing breaks. The exact steps, the checks that matter for FRR, the gotchas, and measured times.
---

# Test an FRR change in CI

You keep FRR configs in git, one `frr.conf` per router. This guide makes every pull request that touches them boot the routers in containerlab with the changed configs, check how they route, and fail the job if something broke. It uses [`examples/frr-bgp`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp) and its broken twin [`examples/frr-bgp-broken`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp-broken); every output below is from a real run.

## 1. The lab: one folder next to your configs

`examples/frr-bgp` is three FRR routers in a triangle, each in its own AS, each announcing one LAN over eBGP. The folder holds:

```text
frr-bgp/
  topology.clab.yml      containerlab topology
  configs/r1.conf        one frr.conf per router (r2.conf, r3.conf)
  configs/daemons        which FRR daemons start
  configs/vtysh.conf     one line: service integrated-vtysh-config
  netdryrun.yml          the checks
```

Each router is a plain `linux` node running the FRR image, with the three files bind-mounted where FRR expects them:

```yaml title="topology.clab.yml"
name: ndr-frr-bgp

topology:
  defaults:
    kind: linux
    image: quay.io/frrouting/frr:10.4.1
  nodes:
    r1:
      binds:
        - configs/daemons:/etc/frr/daemons
        - configs/vtysh.conf:/etc/frr/vtysh.conf
        - configs/r1.conf:/etc/frr/frr.conf
    # r2 and r3 the same, with their own frr.conf
  links:
    - endpoints: ["r1:eth1", "r2:eth1"]
    - endpoints: ["r2:eth2", "r3:eth1"]
    - endpoints: ["r3:eth2", "r1:eth2"]
```

FRR details that matter here:

- **`daemons` decides what runs.** `bgpd=yes` (and `staticd=yes` for static routes) or BGP never starts. Netdryrun then reports the run as `inconclusive` (exit code `3`), not as a failed change, because no node ever returned BGP state.
- **`vtysh.conf` with `service integrated-vtysh-config`** makes `vtysh` read the single `frr.conf`, which is the file your pull request changes.
- **`eth0` is containerlab's management interface.** Your links start at `eth1`, and `frr.conf` should name those.
- **Pin the image** to the FRR version you run, not `latest`. Behavior and defaults change between releases.

## 2. The checks that matter for FRR

```yaml title="netdryrun.yml"
lab: topology.clab.yml
timeout: 90   # seconds each positive check may wait for convergence

checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
  - type: bgp_session
    node: r1
    neighbor: 10.0.13.2
  - type: bgp_prefixes
    node: r1
    neighbor: 10.0.12.2
    min: 1
    max: 10          # guards against a route leak flooding r1
  - type: route
    node: r1
    prefix: 192.168.3.0/24
    protocol: bgp
  - type: ping
    node: r1
    source: 192.168.1.1
    target: 192.168.3.1
  - type: bgp_route    # r1 prefers r2's direct path to r2's LAN over the longer path via r3
    node: r1
    prefix: 192.168.2.0/24
    as_path: "65002"
    next_hop: 10.0.12.2
  - type: route        # nothing should send r1 a default route
    node: r1
    prefix: 0.0.0.0/0
    protocol: bgp
    present: false

scenarios:
  - name: r1-r2 link fails
    link_down: {node: r1, interface: eth1}
    checks:
      - type: route        # r2's LAN is still reachable, now via r3
        node: r1
        prefix: 192.168.2.0/24
        protocol: bgp
      - type: bgp_route    # the best path now goes the long way, through r3
        node: r1
        prefix: 192.168.2.0/24
        as_path: "65003 65002"
        next_hop: 10.0.13.2
      - type: ping
        node: r1
        source: 192.168.1.1
        target: 192.168.2.1
      - type: bgp_session  # and the session over the failed link is really down
        node: r1
        neighbor: 10.0.12.2
        state: down        # any state except established
```

On FRR, each check type reads a different part of the router, and the differences are where changes go wrong:

| Check | Reads | Why it matters on FRR |
|---|---|---|
| `bgp_session` | `show bgp neighbors json` | An `Established` session can still carry nothing. Never use it alone |
| `bgp_prefixes` | `acceptedPrefixCounter` in `show bgp neighbors json` | Counts prefixes after your inbound policy. A filter that drops everything shows here first. `max` is a cheap leak guard |
| `route` | `show ip route <prefix> json` (zebra) | Selected and installed. zebra keeps the losing entries too, so `present: false` also fails on a route that was received but lost |
| `bgp_route` | `show bgp ipv4 unicast <prefix> json` (bgpd) | The best path's AS path, next hop, local preference, MED, communities. Catches a change that still delivers the route, but the long way |
| `ping` | `ping -I <source>` in the container | The data plane, from the source address you give |

BGP's best path and zebra's selected route are not the same thing. A default route leaked by a peer is `*>` (best) in `show bgp ipv4 unicast`, because the static it loses to isn't a BGP path, and it is not selected in `show ip route`. Read the table that answers your question: `bgp_route` for "which path does BGP prefer", `route` for "what does the router forward with". The [hidden leak lab](https://github.com/netdryrun/netdryrun/tree/main/examples/srl-hidden-leak) shows both side by side.

## 3. Run it locally

```bash
pip install netdryrun
netdryrun run examples/frr-bgp
```

```text
Netdryrun 0.3.1: 7 checks from examples/frr-bgp/netdryrun.yml
Deploying lab ndr-frr-bgp (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (13.5s)
  [PASS] r1: BGP session to 10.0.13.2 is established -- state is established (13.5s)
  [PASS] r1: route 192.168.3.0/24 via bgp is present -- active via bgp (13.5s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (need 2) (13.5s)
Convergence checks done; settling 10s before post-convergence checks...
  [PASS] r1: prefixes from 10.0.12.2 >= 1 and <= 10 -- 2 ipv4-unicast prefixes accepted (held 10s, 4 samples) (10.3s)
  [PASS] r1: BGP best path for 192.168.2.0/24 has as-path '65002', next hop 10.0.12.2 -- best path: as-path '65002', next hop 10.0.12.2, local-pref 100, MED 0, communities none (held 10s, 4 samples) (10.3s)
  [PASS] r1: route 0.0.0.0/0 via bgp is absent -- absent (held 10s, 4 samples) (10.3s)
Scenario: r1-r2 link fails
  the fault took effect after 0s (2 BGP session(s) over the downed links are down)
  settling 10s before the scenario's checks
  [PASS] [r1-r2 link fails] r1: route 192.168.2.0/24 via bgp is present -- active via bgp (held 12s, 3 samples) (19.4s)
  [PASS] [r1-r2 link fails] r1: ping 192.168.2.1 from 192.168.1.1 expects success -- 3/3 replies (need 2) (held 12s, 3 samples) (19.4s)
  [PASS] [r1-r2 link fails] r1: BGP best path for 192.168.2.0/24 has as-path '65003 65002', next hop 10.0.13.2 -- best path: as-path '65003 65002', next hop 10.0.13.2, local-pref 100, MED 0, communities none (held 10s, 4 samples) (10.0s)
  [PASS] [r1-r2 link fails] r1: BGP session to 10.0.12.2 is down -- state is active (held 10s, 4 samples) (10.0s)
Restored 1 link(s) and 0 route injection(s); settling 10s
Destroying lab...
PASSED: 11 passed, 0 failed (11 checks)
```

The `bgp_route` checks run with the post-convergence checks and must hold for 10 seconds, because the best path can change when a slower session comes up. In the scenario, Netdryrun first waits until both ends of the BGP session over the downed link see it down (here at once, because the interface itself went down), settles 10 seconds, and then the positive checks must keep passing for the hold window, not just once. See [scenario timing](../reference/config.md#scenario-timing).

Now the broken change. `frr-bgp-broken` is the same triangle, but r2's config adds one line, `neighbor 10.0.12.1 default-originate`, toward r1:

```bash
netdryrun run examples/frr-bgp-broken
```

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

Sessions are up, the prefix count is within its limit, and the ping works: the LANs have more specific routes, so a default route changes nothing for them. r1 doesn't even select the leaked default, because in this lab it loses to containerlab's management default route (see [Gotchas](#gotchas)). The `present: false` check fails anyway, because zebra still holds the losing BGP entry, and the run exits with `1`.

## 4. Run it on every pull request

```yaml title=".github/workflows/network-dryrun.yml"
name: Network dry run
on:
  pull_request:
    paths:
      - "network/**"
permissions:
  contents: read
  pull-requests: write   # for pr-comment
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.2
        with:
          path: network/        # the folder with netdryrun.yml
          pr-comment: true
```

The job installs containerlab and Netdryrun, pulls the FRR image, runs the checks, uploads the JSON and JUnit reports, and fails if a check fails. With `pr-comment: true` it also posts the verdict and the evidence for each failed check on the pull request. See [GitHub Action](../github-action.md) for every input, and the security notes before running labs from forks.

**Other CI systems:** any Linux runner that can start privileged Docker containers works. The steps are the same three commands. `env "PATH=$PATH"` keeps the `netdryrun` that `pip` installed on the path under `sudo`:

```bash
bash -c "$(curl -sL https://get.containerlab.dev)" -- -v 0.81.1
pip install netdryrun
sudo env "PATH=$PATH" netdryrun run network/ --junit netdryrun-junit.xml --json netdryrun-report.json
```

Exit codes: `0` passed, `1` a check failed, `2` a setup problem (bad YAML, the lab didn't start), `3` inconclusive (the lab never reached a testable state; rerun it).

## Times

Wall-clock for `netdryrun run`, including deploying and destroying the lab, with images already pulled. Measured on 2026-10-28 on WSL2 (20 cores, 16 GB), containerlab 0.81.1, Netdryrun 0.3.1 installed from PyPI, running the two example folders of a fresh clone:

| Run | Result | Exit | Time |
|---|---|---|---|
| `examples/frr-bgp` (7 checks and a link-failure scenario) | `PASSED: 11 passed, 0 failed` | `0` | 105 s |
| `examples/frr-bgp-broken` | `FAILED: 5 passed, 1 failed` | `1` | 41 s |

The failing run is shorter because it has no failure scenario. `frr-bgp` takes longer than on 0.3.0 (88 s) because 0.3.1 settles 10 s after the fault and holds the scenario's checks for a full window, instead of judging them as soon as they pass. The [examples page](../examples.md) shows 99 s and 39 s for the same two labs from the 0.3.1 release check on the same machine the day before; runs differ by several seconds. On GitHub-hosted `ubuntu-latest` runners, the whole job (installing containerlab and Netdryrun, pulling FRR, running) took 100 to 107 s for `frr-bgp` and 54 to 66 s for `frr-bgp-broken`, over three CI runs on `main` on 2026-10-27, before the 0.3.0 release added a `bgp_route` check to `frr-bgp`; see [the FAQ](../faq.md#how-long-does-a-run-take-and-what-does-ci-cost). On a private repository, jobs are billed by the minute, rounded up: the `frr-bgp` job uses 2.

## Gotchas

- **eBGP without a policy may exchange nothing.** Under FRR's default `traditional` profile, `bgp ebgp-requires-policy` is on (RFC 8212): an eBGP neighbor with no route-map in or out reaches `Established` and accepts and sends nothing. Under `frr defaults datacenter`, which the examples use, it's off. On FRR 10.4.1 with no route-maps, the `traditional` side shows:

    ```text
    Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
    10.9.0.2        4      65002        12        11        1    0    0 00:00:24     (Policy) (Policy) FRRouting/10.4.1_git
    ```

    A `bgp_session` check passes either way; `bgp_prefixes` and `route` checks catch it. Keep the same `frr defaults` line in the lab as in production.
- **containerlab gives `linux` nodes a default route** via the management network. FRR sees it as a kernel route with distance 0, which beats a static or BGP default. If your change or your checks involve the default route, delete it with `exec: ["ip route del default"]` on the node, as the [hidden leak lab](https://github.com/netdryrun/netdryrun/tree/main/examples/srl-hidden-leak) does.
- **Lab names are global on a machine.** Two jobs on one self-hosted runner, or two copies of a folder, must use different `name:` values in `topology.clab.yml`.
- **`frr.conf` is read at boot.** Netdryrun deploys a fresh lab on every run, so the pull request's file is always the one tested. If you poke at a lab kept with `--keep`, changes you make in `vtysh` are not in the file.
