---
title: Batfish, then Netdryrun
description: A two-stage gate for network changes. Batfish analyses FRR configs without booting anything, then Netdryrun boots them in a containerlab lab. Measured results, what each stage caught, and how well Batfish parses FRR.
---

# Batfish, then Netdryrun

[Batfish](https://batfish.org) and Netdryrun™ answer different questions. Batfish reads configs and models the network's routing and forwarding: nothing has to boot, and in the runs below its analysis took 2 to 6 seconds once the Batfish service was running. Netdryrun boots the configs in a containerlab lab and checks what the routing software really does. Run Batfish first on every commit, and boot the lab only when it passes.

This page reports one measured run of that pipeline: four versions of a small FRR network, each tested by both stages. The code is in [`examples/batfish-pipeline`](https://github.com/netdryrun/netdryrun/tree/main/examples/batfish-pipeline).

## The pipeline

The network is the FRR triangle from [`examples/frr-bgp`](examples.md#frr-bgp): three routers, each in its own AS, each announcing one LAN over eBGP.

1. **Batfish** (`batfish_check.py`, 8 checks): every config parses with no parse warnings, no undefined references, all six BGP sessions establish, r1's best paths to the two other LANs, no router learns a default route, a traceroute from r1's LAN to r2's LAN, and the best path after the r1-r2 link fails (a forked snapshot with the interface deactivated).
2. **Netdryrun** (`netdryrun.yml`, 10 checks): r1's two BGP sessions, the prefix count from r2, the route to r2's LAN and its best path, a ping, no default route on r1 or r3, and the same link failure.

The two stages check the same intent with two differences: Batfish checks for a default route on all three routers, while the lab checks r1 and r3 (r2 is the router that would send it), and the lab adds a prefix count and a ping.

```yaml title="examples/batfish-pipeline/github-workflow.yml"
# Example workflow: copy to .github/workflows/ in your repository and adapt the paths.
# Job 1 runs Batfish on every push; nothing boots. Job 2 boots the lab with Netdryrun, only if
# Batfish passed. Not run by this repository's CI.
name: network change gate

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  batfish:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    services:
      batfish:
        image: batfish/batfish:2026.08.27.3685
        ports: ["9996:9996", "9997:9997"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pybatfish==2026.9.17.3748
      - name: Analyse the configs   # waits up to 60 s for the Batfish service to answer
        run: python examples/batfish-pipeline/batfish_check.py examples/batfish-pipeline/configs

  netdryrun:
    needs: batfish   # boot the lab only if Batfish passed
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.2
        with:
          path: examples/batfish-pipeline
```

The workflow is an example to copy: this repository's CI does not run it, and it has not been timed on GitHub's runners. On top of the analysis, the Batfish job pays for pulling the `batfish/batfish` image (712 MB; `docker pull` took 15 s on the test machine), installing pybatfish (14 s there, the first command of the example's run steps) and starting the service. The measurements below come from the equivalent local script, `pipeline.sh`.

## Results

Measured on 2026-10-27 from a fresh clone of commit f368194 (later commits change only documentation), following the example's [README](https://github.com/netdryrun/netdryrun/tree/main/examples/batfish-pipeline#run-it) word for word, on WSL2 (20 cores, 16 GB) with images already pulled: `batfish/batfish:2026.08.27.3685`, pybatfish 2026.9.17.3748, Netdryrun 0.3.0 from PyPI, containerlab 0.81.1, FRR 10.4.1. The Batfish service was already running. The Batfish stage includes loading the snapshot; the lab stage includes deploying and destroying the lab. Each change below replaces r2's config; the last column is the command that reproduces the row.

| Change to r2 | Batfish | Netdryrun lab | Who caught it | Reproduce |
|---|---|---|---|---|
| None (baseline) | pass, 6 s | pass, 66 s | Both pass | `pipeline.sh` |
| Adds `default-originate` toward r1 | **fail**, 3 s | **fail**, 68 s (2 of 10) | Both; Batfish first | `BOTH=1 pipeline.sh default-leak` |
| Route-map name typo (`ALLOW-AL`) toward r1 | **fail**, 2 s | **fail**, 179 s (2 of 10) | Both; Batfish first, but its route model predicts the wrong outcome | `BOTH=1 pipeline.sh route-map-typo` |
| Switches to `frr defaults traditional` and drops the "allow all" route-maps | pass, 3 s | **fail**, 265 s (6 of 10) | **Only the lab** | `BOTH=1 pipeline.sh no-policy` |

### Caught by Batfish first: a leaked default route

r2 starts sending r1 a default route. In a 3-second run, Batfish reports that r1 learns `0.0.0.0/0` from r2 and passes it on to r3. The lab finds the same leak on r1 and r3 after about a minute. There FRR picks the route as its BGP best path and passes it on, but does not install it as the router's route to 0.0.0.0/0; Netdryrun reports it as "present via bgp (not selected)" and fails the check anyway. Stopping at the Batfish stage saves the lab run.

The route-map typo is also caught first: Batfish's `undefinedReferences` question names the missing `ALLOW-AL` and where it is used, `r2.conf line 20`. (`batfish_check.py` maps lines in the wrapped files it gives Batfish back to the original `frr.conf`.) Its routing model, though, still predicts that r1 uses the direct path to r2. FRR denies everything through a route-map that does not exist, so in the lab r1 receives nothing from r2 and reaches r2's LAN through r3. Ping still works; only the best-path check and the prefix count fail. The gate would fail in both stages, but only the lab shows what the network would really do.

### Seen only by the lab: an FRR default

According to the [FRR documentation](https://docs.frrouting.org/en/latest/bgp.html#clicmd-bgp-ebgp-requires-policy), `bgp ebgp-requires-policy` is on by default under the `traditional` profile and off under `datacenter`. An eBGP neighbor with no inbound and outbound policy then receives nothing and sends nothing, but the session still comes up. In the lab, r2 shows `(Policy) (Policy)` for both neighbors and 0 prefixes each way, and 6 of the 10 checks fail: r2's LAN is unreachable from r1, even after the link-failure scenario.

Batfish passed this change. It accepted `frr defaults traditional` without modelling what that profile implies, and predicted every route as before. When `bgp ebgp-requires-policy` is written out explicitly, Batfish reports it as an unrecognized line rather than applying it (Batfish 2026.08.27.3685; the commands are in the example's [README](https://github.com/netdryrun/netdryrun/tree/main/examples/batfish-pipeline#reproduce-the-findings)).

### Where they agreed

For the r1-r2 link failure, Batfish's forked snapshot predicted the same failover path (AS path `65003 65002` through r3) that the lab measured. In a topology this small, failover did not show any convergence behavior that the model missed.

## What Batfish does that this test does not show

This test uses a small part of Batfish. It also tests route maps and other routing policies against every route they could match, analyses ACLs and firewall rules, searches every packet that could match a rule rather than the few a ping sends, finds forwarding loops, compares two snapshots (for example before and after a change, or with links or nodes failed) to report which flows change, and supports many vendors whose software cannot run in a container. Its authors report analysing networks with thousands of nodes within minutes ([SIGCOMM 2023](https://doi.org/10.1145/3603269.3604866)), far more than a lab can boot. See its [list of questions](https://batfish.readthedocs.io/en/latest/questions.html). None of that needs a lab, and Netdryrun does none of it.

## How well Batfish parses FRR

Batfish reads FRR configs as part of its Cumulus Linux and SONiC support. In this test its FRR support was partial, and the way we fed it configs mattered:" (scopes "partial" to what we measured

- **A bare `frr.conf` is detected as Cisco IOS.** On these configs the status was `PARTIALLY_UNRECOGNIZED`: the `frr defaults` line was not recognized, and interfaces were renamed (`eth1` became `Ethernet1`). The BGP answers happened to be right, but FRR syntax was being read with IOS semantics.
- **Cumulus Linux layout.** Wrapped in the "Cumulus concatenated" layout (a hostname line, an interfaces section, a `ports.conf` marker, then `frr.conf`), the same three configs parse as `CUMULUS_CONCATENATED` with status `PASSED`, no warnings, and the lab's interface names. `batfish_check.py` does this wrapping.
- **SONiC layout.** Next to a `config_db.json` with the hostname and interface addresses, the unchanged `frr.conf` files also parse as `SONIC` with status `PASSED` and no warnings. Batfish predicted the same routes as through the Cumulus path, for the baseline and for the `traditional` change.
- **Not every FRR command or default was supported in this test.** In this test, the defaults profile is accepted but not modelled, and `bgp ebgp-requires-policy` is not recognized at all. Make the gate fail on any file that does not parse cleanly or has a parse warning (`fileParseStatus`, `parseWarning`), as the example script does.

The commands that reproduce these findings, and the `(Policy)` output from FRR, are in the example's [README](https://github.com/netdryrun/netdryrun/tree/main/examples/batfish-pipeline#reproduce-the-findings).

These findings cover only BGP with route-maps on three FRR routers. Batfish's support for other vendors (Cisco, Juniper, Arista, Palo Alto and more) is much broader and is not tested here.

## Related research

A HotNets 2025 paper from Google and UC Berkeley, [Towards Accessible Model-Free Verification](https://doi.org/10.1145/3772356.3772380) (Krentsel et al.), joins the two ideas in one system: it boots real router images in the Kubernetes Network Emulator, extracts the converged data plane, and runs Batfish's existing questions on it. The authors report that this caught changes Batfish could not parse and found bugs in Batfish's model. This page keeps the two as separate stages, with the configs as the only shared input.

## Takeaways

- Put Batfish first. It needs no lab, it failed the two changes it caught in 2 to 3 seconds of analysis, and it pointed at the cause: the file and line of the route-map typo, the routers that learn the leaked default.
- Keep the lab stage. The change that passed Batfish broke every route through r2, because of a vendor default that the model, in the version we tested, did not apply.
- Watch for disagreements, not only for failures. On the route-map typo, both stages failed, but Batfish's prediction of the outcome was wrong.

See also [When to use what](when-to-use-what.md) for how Batfish, pyATS/Genie, containerlab and Netdryrun compare.
