---
title: Test a SONiC change in CI
description: Run SONiC (docker-sonic-vs) in containerlab on every pull request, configure it after boot with setup lines, and fail the job if routing breaks. The exact steps, the checks that matter for SONiC, the gotchas, and measured times.
---

# Test a SONiC change in CI

SONiC is different from most network OSes in a lab: the virtual switch image boots with no configuration, and its services come up one by one after the container starts. This guide shows how to get the image, configure the switch once it's ready, and check its routing on every pull request. It uses [`examples/sonic-frr`](https://github.com/netdryrun/netdryrun/tree/main/examples/sonic-frr): a SONiC VS switch peering eBGP with an FRR router. Every output below is from a real run.

## 1. Get the image

`docker-sonic-vs` is the virtual switch the SONiC project builds for its own tests. It is not on a container registry: the SONiC build server publishes it as a compressed file. Download it and load it into Docker:

```bash
curl -L -o docker-sonic-vs.gz \
  "https://sonic-build.azurewebsites.net/api/sonic/artifacts?branchName=master&platform=vs&target=target/docker-sonic-vs.gz"
docker load -i docker-sonic-vs.gz      # creates docker-sonic-vs:latest
```

The file is about 230 MB (232,075,139 bytes for the build used on this page, downloaded on 2026-10-27). Loaded, the image is 1.92 GB.

The image carries its build id in a label (`docker image inspect docker-sonic-vs:latest --format '{{index .Config.Labels "Tag"}}'`, for example `master.1258173-c10162df4`). `examples/sonic-frr` pins the build the SONiC driver is verified on, so after loading, tag your image with its build id (`docker tag docker-sonic-vs:latest docker-sonic-vs:<build id>`) and put that tag on the example's image line. `scripts/get_sonic_vs.sh` in the repository does the download and the tag in one step.

`branchName=master` is the latest build, so it changes over time. For repeatable CI, keep the file you tested with (as a release asset or in a cache) instead of downloading `master` on every run.

## 2. The lab

```yaml title="topology.clab.yml"
name: ndr-sonic-frr

topology:
  nodes:
    sonic1:
      kind: sonic-vs
      image: docker-sonic-vs:latest
    frr1:
      kind: linux
      image: quay.io/frrouting/frr:10.4.1
      binds:
        - configs/daemons:/etc/frr/daemons
        - configs/vtysh.conf:/etc/frr/vtysh.conf
        - configs/frr1.conf:/etc/frr/frr.conf
  links:
    - endpoints: ["sonic1:eth1", "frr1:eth1"]
```

In `kind: sonic-vs`, the container's `eth1` is the SONiC port `Ethernet0`. The topology names `eth1`; SONiC commands and checks use `Ethernet0`.

## 3. Configure SONiC after boot: `setup`

There's no startup config. Instead, `netdryrun.yml` lists `setup` commands that Netdryrun runs inside the node after deploying the lab and before any check:

```yaml title="netdryrun.yml"
lab: topology.clab.yml
timeout: 180

nodes:
  sonic1:
    setup:
      - supervisorctl status orchagent | grep -q RUNNING && supervisorctl status bgpd | grep -q RUNNING
      - config interface ip add Ethernet0 10.0.40.1/30 && config interface startup Ethernet0
      - config loopback add Loopback0; config interface ip add Loopback0 192.168.40.1/32
      - >-
        vtysh -c "conf t" -c "router bgp 65040" -c "bgp router-id 40.40.40.40" -c "no bgp ebgp-requires-policy"
        -c "neighbor 10.0.40.2 remote-as 65020" -c "address-family ipv4 unicast" -c "network 192.168.40.1/32"
```

Line by line:

1. **Wait for the services.** The container is "running" long before SONiC is. `orchagent` (which programs the switch) and `bgpd` (FRR inside SONiC) have to be `RUNNING` before `config` commands and `vtysh` work. This line fails until they are.
2. **Address and enable the port** with SONiC's `config` CLI, which writes to CONFIG_DB like on a real switch.
3. **A loopback** for the announced prefix.
4. **BGP**, configured in the FRR that runs inside SONiC, through `vtysh`.

Each line is retried every 5 seconds until it succeeds, within a shared budget of 300 seconds. A line runs again from the start if any part of it fails, so put the part that can fail first (as line 1 does), and keep lines that change state safe to run twice.

## 4. The checks that matter for SONiC

```yaml
checks:
  - type: bgp_session
    node: sonic1
    neighbor: 10.0.40.2
  - type: route
    node: sonic1
    prefix: 192.168.20.0/24
    protocol: bgp
  - type: route
    node: frr1
    prefix: 192.168.40.1/32
    protocol: bgp
  - type: ping
    node: sonic1
    source: 192.168.40.1
    target: 192.168.20.1
  - type: bgp_prefixes
    node: frr1
    neighbor: 10.0.40.1
    min: 1
    max: 5
  - type: bgp_route
    node: sonic1
    prefix: 192.168.20.0/24
    as_path: "65020"
    local_pref: 100
    next_hop: 10.0.40.2

scenarios:
  - name: SONiC port Ethernet0 goes down
    link_down: {node: sonic1, interface: Ethernet0}
    checks:
      - {type: bgp_session, node: frr1, neighbor: 10.0.40.1, state: down}
      - {type: route, node: frr1, prefix: 192.168.40.1/32, protocol: bgp, present: false}
```

What to know about these on SONiC:

- **Routing state comes from the FRR inside SONiC.** The `sonic` driver reads sessions, routes and BGP paths through `vtysh`, exactly as on FRR. A route check says what SONiC's routing stack selected. It does not read what `orchagent` programmed (APPL_DB, ASIC_DB).
- **`ping` covers the data path.** It runs from the switch with the loopback as source, so it only passes if the port, its address and the route all work. Keep at least one ping per change.
- **Check from the other side too.** `route` and `bgp_prefixes` on `frr1` prove what SONiC actually announces, which is what a policy change on the switch affects.
- **A port-down scenario uses the SONiC name.** `link_down` on `Ethernet0` takes the port down inside the switch. The scenario then checks that the peer sees the session drop and the route withdrawn, and Netdryrun brings the port back afterwards.
- **Give it time.** `timeout: 180` covers the slow boot; the `setup` budget is separate.

## 5. Run it locally

```bash
pip install netdryrun
netdryrun run examples/sonic-frr
```

```text
Netdryrun 0.3.1: 6 checks from examples/sonic-frr/netdryrun.yml
Deploying lab ndr-sonic-frr (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
Running setup on sonic1...
setup done on sonic1 (4 commands)
  [PASS] sonic1: BGP session to 10.0.40.2 is established -- state is established (13.7s)
  [PASS] sonic1: route 192.168.20.0/24 via bgp is present -- active via bgp (13.7s)
  [PASS] frr1: route 192.168.40.1/32 via bgp is present -- active via bgp (13.7s)
  [PASS] sonic1: ping 192.168.20.1 from 192.168.40.1 expects success -- 3/3 replies (need 2) (13.7s)
Convergence checks done; settling 10s before post-convergence checks...
  [PASS] frr1: prefixes from 10.0.40.1 >= 1 and <= 5 -- 1 ipv4-unicast prefixes accepted (held 10s, 5 samples) (10.2s)
  [PASS] sonic1: BGP best path for 192.168.20.0/24 has as-path '65020', local-pref 100, next hop 10.0.40.2 -- best path: as-path '65020', next hop 10.0.40.2, local-pref 100, MED 0, communities none (held 10s, 5 samples) (10.2s)
Scenario: SONiC port Ethernet0 goes down
  the fault took effect after 0s (1 BGP session(s) over the downed links are down)
  settling 10s before the scenario's checks
  [PASS] [SONiC port Ethernet0 goes down] frr1: BGP session to 10.0.40.1 is down -- state is connect (held 10s, 4 samples) (10.1s)
  [PASS] [SONiC port Ethernet0 goes down] frr1: route 192.168.40.1/32 via bgp is absent -- absent (held 10s, 4 samples) (10.1s)
Restored 1 link(s) and 0 route injection(s); settling 10s
Destroying lab...
PASSED: 8 passed, 0 failed (8 checks)
```

## 6. Run it on every pull request

The workflow is the usual one with one extra step: load the image before Netdryrun deploys the lab. containerlab only pulls images that are missing, so the loaded `docker-sonic-vs:latest` is used as is.

```yaml title=".github/workflows/sonic-dryrun.yml"
name: SONiC dry run
on:
  pull_request:
    paths:
      - "network/sonic/**"
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Load docker-sonic-vs
        run: |
          curl -fsSL -o docker-sonic-vs.gz \
            "https://sonic-build.azurewebsites.net/api/sonic/artifacts?branchName=master&platform=vs&target=target/docker-sonic-vs.gz"
          docker load -i docker-sonic-vs.gz
      - uses: netdryrun/netdryrun@v0.3.2
        with:
          path: network/sonic/
```

On other CI systems: load the image the same way, then install containerlab and Netdryrun and run `sudo env "PATH=$PATH" netdryrun run <folder>`, as in the [FRR guide](frr-ci.md#4-run-it-on-every-pull-request).

This workflow is a recipe, not something Netdryrun's own CI runs yet: SONiC isn't in the project's CI, and the workflow hasn't been run on a hosted runner. The runs on this page are local.

## Times

Wall-clock for `netdryrun run`, including deploying the lab, the `setup` lines, the checks, the port-down scenario and destroying the lab, with both images already loaded. Measured on 2026-10-28 on WSL2 (20 cores, 16 GB), containerlab 0.81.1, Netdryrun 0.3.1 installed from PyPI, running the example folder of a fresh clone:

| Run | Result | Exit | Time |
|---|---|---|---|
| `examples/sonic-frr` (6 checks and a port-down scenario) | `PASSED: 8 passed, 0 failed` | `0` | 99 s |

The positive checks passed 13.7 s after `setup` finished. The [examples page](../examples.md) shows 92 s from the 0.3.1 release check on the same machine the day before; runs differ by a few seconds. In CI, add the time to download the 230 MB image, which depends on the runner's network; caching the file avoids it.

## Gotchas

- **"Running" isn't ready.** The container is up long before SONiC's services are, and `config` and `vtysh` don't work until they are. Make the first `setup` line a readiness check, so every later line starts on a ready switch.
- **`no bgp ebgp-requires-policy`.** With it on (RFC 8212, FRR's default profile), an eBGP neighbor with no route-map comes up and exchanges nothing; see the [FRR guide's gotchas](frr-ci.md#gotchas). The example turns it off to stay short. With real policies, attach route-maps instead.
- **The image is big and not on a registry.** About 230 MB to download and 1.92 GB once loaded. Cache it in CI.
- **Port names differ between the topology and the switch:** `eth1` in `topology.clab.yml`, `Ethernet0` in SONiC commands, checks and scenarios.
- **Memory:** about 300 MiB for the SONiC VS node once up ([FAQ](../faq.md#how-much-memory-and-cpu-does-it-need)).
