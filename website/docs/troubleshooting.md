---
title: Troubleshooting
description: Real Netdryrun errors and how to fix them. containerlab not installed, Docker permission denied, unknown keys, unknown nodes, labs that never converge, checks not evaluated, faults that did not take effect, SR Linux on a Windows drive, missing cEOS image, lab name and port collisions, link_down on SR Linux, and MCP tool timeouts.
---

# Troubleshooting

Each error below was reproduced on purpose on WSL2 (Ubuntu 22.04) with containerlab 0.81.1 and Netdryrun™ 0.3.1, and the output is copied from those runs. The labs are copies of the [tutorial](tutorial.md)'s `my-lab` (lab name `ndr-my-lab`) and of the bundled examples, renamed `ndr-docs-*`. Where an entry shows what an older version did, it says which version.

Exit code `2` means the run has no verdict (a config error, a lab error, a fault that did not take effect, or an internal error; `--debug` shows the traceback of an internal error). Exit code `1` means a check failed. See [exit codes](reference/cli.md#exit-codes).

## Unknown key ... did you mean

```text
$ netdryrun validate my-lab
config error: checks[11]: unknown keys ['presnt'] for type route; did you mean 'present'?; allowed: active, hold, name, node, prefix, present, protocol, timeout, type, vrf
```

Exit code `2`. From 0.3.1, a key Netdryrun doesn't know is an error at every level of the file (top level, `nodes`, checks, scenarios and their faults), not only inside checks. Before 0.3.1, a misspelled key at the top level, under `nodes` or inside a fault was ignored: a whole block of checks under `chekcs:` never ran, and nothing said so. 0.3.1 says `unknown top-level keys ['chekcs']; did you mean 'checks'?; allowed: checks, lab, nodes, scenarios, timeout`. Fix the spelling the message suggests; `allowed:` lists every key that fits there. The same goes for values from a fixed list (`afi`, `protocol`, `state`, `expect`, `driver`), and a key written twice in the same mapping is an error too (`not valid YAML at line 55, column 3: duplicate key 'present' (first defined on line 54)`). Run `netdryrun validate` after upgrading: a file that 0.3.0 accepted can fail here, and every such failure was a check that didn't test what it said.

## containerlab is not installed

```text
$ netdryrun run my-lab
Netdryrun 0.3.1: 14 checks from my-lab/netdryrun.yml
ERROR: 'containerlab' not found on PATH
```

Exit code `2`. Netdryrun drives the `containerlab` CLI and needs it on `PATH`. Install it ([containerlab.dev/install](https://containerlab.dev/install/)) and check with `containerlab version`. The same error names `docker` if Docker is missing. Nothing was deployed, so nothing is destroyed.

## Docker or containerlab permission denied

Without the `docker` group (here, with every supplementary group dropped), Netdryrun stops before deploying anything, because its first step is to ask Docker whether a lab with the same name is already running:

```text
$ netdryrun run my-lab
Netdryrun 0.3.1: 14 checks from my-lab/netdryrun.yml
ERROR: could not list Docker containers: permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

Exit code `2`. `docker ps` fails the same way:

```text
$ docker ps
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

A user in `docker` but not in `clab_admins` gets past that, and then containerlab refuses the deploy. Its message, from a run with Netdryrun 0.2.0 as a user `ndrtest`:

```text
ERROR: containerlab deploy failed:

   ERROR

  User 'ndrtest' is not part of containerlab admin group 'clab_admins', which is required to execute this command.
  To add yourself to this group, run the following command:
      $ sudo usermod -aG clab_admins ndrtest.
```

Fix: add your user to both groups, then start a new login session so the groups apply.

```bash
sudo usermod -aG docker,clab_admins "$USER"
```

On WSL, close the terminal and run `wsl --shutdown` from Windows, then open it again. Check with `id`: both groups must be listed.

```text
$ id
uid=1001(ndrtest) gid=1001(ndrtest) groups=1001(ndrtest),998(clab_admins),999(docker)
```

After this, the same user deployed and ran the lab. Running Netdryrun with `sudo` also works, but then the reports are owned by root.

## A check names a node that is not in the topology

A typo (`r9` instead of `r1`) is caught before anything is deployed:

```text
$ netdryrun run unk
Netdryrun 0.3.1: 14 checks from unk/netdryrun.yml
ERROR: unknown node(s) r9; the topology has r1, r2, r3
```

From 0.3.1, `netdryrun validate` reads the topology too and catches it without starting anything (`lab error: unknown node(s) r9; ...`). Before 0.3.1, `validate` checked only the file itself and printed `OK` for this typo.

Exit code `2`, and nothing is deployed or destroyed: from 0.3.1, a lab you kept running with `--keep` survives a typo like this (0.3.0 and earlier destroyed it). Use the node names from the topology's `nodes:` section (`r1`), not the container names (`clab-ndr-my-lab-r1`).

## The lab never converges (timeout)

A positive check waits up to `timeout` seconds (default 120) for the network to converge, then fails. Here r1 has the wrong `remote-as` for r2 and `timeout` is 30:

```text
$ netdryrun run slow
Netdryrun 0.3.1: 14 checks from slow/netdryrun.yml
Deploying lab ndr-docs-slow (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] r1: BGP session to 10.0.13.2 is established -- state is established (13.3s)
  ...
  [FAIL] r1: BGP session to 10.0.12.2 is established -- state is idle (30.0s)
  [FAIL] r2: BGP session to 10.0.12.1 is established -- state is idle (30.0s)
Convergence checks done; settling 10s before post-convergence checks...
  [FAIL] r1: prefixes from 10.0.12.2 >= 2 and <= 10 -- not evaluated: BGP session(s) on r1 not established: 10.0.12.2 (idle) after waiting 30s. A post-convergence check only means something once every BGP session on its node is up (a leak can arrive over any of them). If a session is down on purpose, add a bgp_session check with state: down for it (30.0s)
  ...
Destroying lab...
FAILED: 8 passed, 6 failed (14 checks)
```

A check that fails at exactly its timeout (`30.0s` here) never reached the expected state. Two causes:

- **The change really breaks something.** The `detail` says what the router reported (`state is idle`). This is the test working.
- **The lab is slow to boot.** SR Linux, SONiC and cEOS take longer than FRR. Raise `timeout` at the top of `netdryrun.yml`, or on one check. `examples/srl-frr` uses 120.

To see why, keep the lab and look inside:

```text
$ netdryrun run slow --keep-on-failure
...
Lab ndr-docs-slow left running for debugging; destroy with: containerlab destroy -t /home/ndr/work/docs031/ts/slow/topology.clab.yml --cleanup
FAILED: 8 passed, 6 failed (14 checks)
$ docker exec clab-ndr-docs-slow-r1 vtysh -c "show bgp summary"
...
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.12.2       4      65099         6        12        0    0    0    never         Idle        0 N/A
r3(10.0.13.2)   4      65003        34        40        4    0    0 00:01:06            3        4 FRRouting/10.4.1_git
```

r1 expects AS 65099 at 10.0.12.2, but r2 is AS 65002. Destroy the lab with the command Netdryrun printed.

The routes still arrive over the r1-r3 session, so the route and ping checks pass. r1's four post-convergence checks (the two prefix counts with `max`, and the two routes that must be absent) report `not evaluated`, because one of r1's sessions is down; see the next entry.

## Not evaluated (a session on the node never came up)

```text
  [FAIL] r1: prefixes from 10.0.12.2 >= 2 and <= 10 -- not evaluated: BGP session(s) on r1 not established: 10.0.12.2 (idle) after waiting 30s. A post-convergence check only means something once every BGP session on its node is up (a leak can arrive over any of them). If a session is down on purpose, add a bgp_session check with state: down for it
```

Exit code `1`. From 0.3.1, a post-convergence check (a route that must be absent, a ping that must fail, a prefix count with `max` or `exact`, a `bgp_route` attribute) starts only once every configured BGP neighbor on its node is up with stable prefix counts. A leak can arrive over any session, so a check that passed while one was still down would prove nothing. Netdryrun waits up to the largest `timeout` of the node's post-convergence checks; if a session is still down then, those checks fail as `not evaluated` and name the session.

Fix: if the session should be up, it's a finding: look at it as in [the lab never converges](#the-lab-never-converges-timeout), or raise `timeout` for a slow NOS. If it is down on purpose (a shut neighbor, a peer that isn't in the lab), add a check that says so, and the wait leaves it out:

```yaml
- type: bgp_session
  node: r1
  neighbor: 10.0.12.2
  state: down
```

## A node without BGP waits a whole timeout

```text
warning: h1 reported no BGP neighbors for 30s; the check was evaluated without BGP convergence
```

From 0.3.1, a node that answers with no BGP neighbors at all is treated as not converged yet, because that is also what a router answers before its BGP config is applied. Its post-convergence checks (a ping that must fail, for example) wait up to their `timeout`, then run with this warning in their result; the verdict is unchanged. That applies only to a node with no BGP check anywhere in the file. From 0.3.2, if the file has a BGP check on the node (`bgp_session`, `bgp_prefixes`, `bgp_route`, or a `route` with `protocol: bgp`), its post-convergence checks fail instead as `not evaluated: <node> reported no BGP neighbors by the cap`: the file says the node runs BGP, so its config never loaded. On a node that really doesn't run BGP, lower the `timeout` of those checks to shorten the wait. If the node should have BGP neighbors, its BGP config was never applied: check its startup config or `setup` commands.

## The fault did not take effect

```text
ERROR: scenario 'r1-r2 link fails': the fault did not take effect within 30s: BGP session(s) over the downed links still established (r2 -> 10.0.12.1). Netdryrun won't judge the scenario's checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) to notice a failure: raise the checks' timeout, or lower the hold timers in the lab
```

Exit code `2`. From 0.3.1, after taking links down a scenario waits until every BGP session that ran over them is down on both ends, so its checks are never judged on the state from before the failure. The wait is capped at the largest `timeout` of the scenario's checks. Here the far end, r2, still had the session up when the time ran out: without BFD, a router notices a dead link only when its BGP hold timer expires (180 s on FRR by default).

Fix: give the scenario's checks a `timeout` above the hold time (for example `timeout: 200` on them, or at the top of the file), lower the hold timers in the lab configs (`timers bgp 3 9` on FRR), or enable BFD. The links are restored and the lab destroyed as usual. See [scenario timing](reference/config.md#scenario-timing).

## Could not read BGP state to find the sessions over the links

```text
ERROR: could not read BGP state on r2 to find the BGP sessions over the links the scenario takes down: `vtysh -c show bgp neighbors json` failed on r2 (rc=1): bgpd is not running. Netdryrun won't judge the scenario without knowing when the fault took effect
```

Reproduced with a copy of `examples/frr-bgp` whose r2 starts without `bgpd`: the main checks on r1 run (the session to r2 fails), then the `r1-r2 link fails` scenario stops here.

Exit code `2`. From 0.3.1, before a scenario takes links down, Netdryrun reads the BGP state of the nodes on both ends of each link (and the addresses of the downed interfaces) to know which sessions the fault must bring down. If that state can't be read, it can't tell when the fault took effect, so it stops before changing anything instead of judging the scenario on the settle delay alone (0.3.0 read it as "no sessions"). Usually the node's routing daemon is still starting or has crashed: check the node (`docker exec <container> vtysh -c "show bgp summary"`), raise the main checks' `timeout` so the lab is fully up before the scenarios start, and rerun. A node no driver can read (a Linux host) and a VRF the node doesn't have count as "no sessions", as before.

## SR Linux fails on a Windows drive (/mnt/c)

On WSL, files under `/mnt/c` are on the Windows filesystem, which has no Linux permissions. If containerlab's lab directory is there, SR Linux cannot save its config. Running containerlab directly in such a folder (a copy of `examples/srl-frr`):

```text
$ containerlab deploy -t topology.clab.yml
09:54:58 INFO Creating lab directory path=/mnt/c/Users/.../d031_srlmnt/clab-ndr-docs-srlmnt
09:54:58 INFO unable to adjust Labdir file ACLs: operation not supported
...
09:55:15 ERRO node "srl1" post-deploy: command execution error:Error in /system:
    Setting permissions for file '/etc/opt/srlinux/config.tmp' failed with error_code = 1 [Operation not permitted]
Error: Commit failed
```

containerlab exits with an error, but the SR Linux container keeps running without its startup config until you destroy the lab. If you point Netdryrun's lab directory there yourself (`CLAB_LABDIR_BASE` under `/mnt/`), the run stops at the deploy, with exit code `2`:

```text
$ CLAB_LABDIR_BASE=$PWD netdryrun run .
Netdryrun 0.3.1: 7 checks from netdryrun.yml
Deploying lab ndr-docs-srlmnt (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
Destroying lab...
ERROR: containerlab deploy failed:
...
09:55:36 ERRO node "srl1" post-deploy: command execution error:Error in /system:
    Setting permissions for file '/etc/opt/srlinux/config.tmp' failed with error_code = 1 [Operation not permitted]
Error: Commit failed
```

Without that, Netdryrun avoids this. When the topology is under `/mnt/`, it puts containerlab's lab directory in `~/.cache/netdryrun/labs` (unless you set `CLAB_LABDIR_BASE` yourself). The same folder with `netdryrun run .`:

```text
$ netdryrun run .
Netdryrun 0.3.1: 7 checks from netdryrun.yml
Deploying lab ndr-docs-srlmnt (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] srl1: BGP session to 10.0.100.2 is established -- state is established (32.8s)
  ...
PASSED: 7 passed, 0 failed (7 checks)
```

If you deploy with containerlab yourself (for example for `netdryrun check`), either keep the lab on the Linux filesystem (`~/...`) or set `CLAB_LABDIR_BASE` to a Linux path. Keeping labs on the Linux filesystem is also faster.

## The cEOS image is missing

Arista does not allow cEOS to be redistributed, so you import it yourself. If the image named in the topology is not in Docker, Docker tries to pull it from Docker Hub and fails:

```text
$ netdryrun run ceos
Netdryrun 0.3.1: 8 checks from ceos/netdryrun.yml
Deploying lab ndr-docs-ceos (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
Destroying lab...
ERROR: containerlab deploy failed:
09:38:28 INFO Containerlab started version=0.81.1
09:38:28 INFO Parsing & checking topology file=topology.clab.yml
09:38:28 INFO Removing directory path=/home/ndr/work/docs031/ts/ceos/clab-ndr-docs-ceos
09:38:28 INFO Creating docker network name=clab IPv4 subnet=172.20.20.0/24 IPv6 subnet=3fff:172:20:20::/64 MTU=0
09:38:28 INFO Pulling image image=docker.io/library/ceos:4.34.1F
09:38:30 ERRO Failed to pull image image=docker.io/library/ceos:4.34.1F err="Error response from daemon: pull access denied for ceos, repository does not exist or may require 'docker login'"
...
```

Exit code `2`. This is a copy of `examples/arista-frr` with the image changed to a tag that isn't in Docker.

Fix: download cEOS-lab from arista.com (free account) and import it with the exact name and tag the topology uses: `docker import cEOS-lab-<version>.tar ceos:<version>`, as the comment in `examples/arista-frr/topology.clab.yml` says. Then check that Docker has it:

```text
$ docker images ceos
IMAGE          ID             DISK USAGE   CONTENT SIZE   EXTRA
ceos:4.36.3M   94cc1e5462fe       3.55GB          976MB
```

`examples/arista-frr` expects `ceos:4.36.3M`. Either import with that tag or change `image:` in the topology to match yours.

## A lab named X is already running

```text
$ netdryrun run other-lab
Netdryrun 0.3.1: 14 checks from other-lab/netdryrun.yml
ERROR: a lab named 'ndr-my-lab' is already running (3 container(s), e.g. clab-ndr-my-lab-r1): another Netdryrun run, or a lab deployed by hand or kept with --keep. Netdryrun won't redeploy or destroy it. Wait for the other run to finish, or remove the lab with: containerlab destroy -t /home/ndr/work/docs031/ts/other-lab/topology.clab.yml --cleanup
```

Here `my-lab` was left running with `--keep`, then `other-lab`, a copy with the same `name:`, was run.

Exit code `2`, before anything is deployed. containerlab lab names are global on a machine: containers are named `clab-<lab>-<node>`. From 0.3.1, `netdryrun run` refuses to deploy a lab whose name is already in use, because redeploying would reconfigure the other lab's containers, and destroying it afterwards would remove them from under whoever is using it. Two runs of the same lab started at the same moment on one host get `another Netdryrun run is already using lab 'ndr-my-lab' on this host; wait for it to finish (two runs of the same lab would collide)` instead, and the first run carries on.

Fix: wait for the other run, destroy the old lab with the command in the message (for a lab you kept with `--keep` or `--keep-on-failure`), or give every lab a unique `name:`. On a shared CI runner or machine, put something unique in the name (for example the branch). `netdryrun check` doesn't deploy, so it still runs against the running lab.

Before 0.3.1, Netdryrun deployed with `containerlab deploy --reconfigure` regardless, so a second lab with the same `name:` **replaced** the first one, even from a different folder. Here, on 0.2.0, `my-lab` was left running with `--keep`, then a copy of it in `other-lab` (same `name: my-lab`) was run:

```text
$ netdryrun run other-lab
Netdryrun 0.2.0: 14 checks from other-lab/netdryrun.yml
Deploying lab my-lab (3 nodes)...
...
Destroying lab...
```

The first lab is gone:

```text
$ netdryrun check my-lab
Netdryrun 0.2.0: 14 checks from my-lab/netdryrun.yml
ERROR: lab containers not running: clab-my-lab-r1, clab-my-lab-r2, clab-my-lab-r3
```

Before you run, check what is up with `docker ps` or `containerlab inspect --all`.

## A host port is already in use

If a topology publishes ports on the host (`ports:` on a node), two containers cannot use the same host port, whether they are in two labs or in one. Here r1 and r2 of the same lab both publish `18179:179`:

```text
$ netdryrun run p2
Netdryrun 0.3.1: 14 checks from p2/netdryrun.yml
Deploying lab ndr-docs-p2 (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
Destroying lab...
ERROR: containerlab deploy failed:
...
09:53:26 ERRO node "r2" deploy: Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint clab-ndr-docs-p2-r2 (cd360913...): Bind for 0.0.0.0:18179 failed: port is already allocated
```

Exit code `2`.

Fix: Netdryrun does not need published ports; it runs every command with `docker exec`. Remove `ports:` from the topology, or use different host ports per lab. `docker ps` shows which container holds the port.

## link_down on an SR Linux node

Failure scenarios take links down with `ip link` inside the node, which works on FRR, SONiC and cEOS but not yet on SR Linux. From 0.3.1, `netdryrun validate` refuses the file (exit code `2`). `run` finds out only when the scenario starts, after the main checks:

```text
$ netdryrun validate srl-ld
lab error: failure scenarios on SR Linux nodes (srl1) are not supported yet; take the link down on the FRR/Linux side of the link instead
$ netdryrun run srl-ld
Netdryrun 0.3.1: 7 checks from srl-ld/netdryrun.yml
Deploying lab ndr-docs-srlld (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] srl1: BGP session to 10.0.100.2 is established -- state is established (14.4s)
  ...
  [PASS] srl1: BGP best path for 192.168.20.0/24 has as-path '65020', local-pref 100, next hop 10.0.100.2 -- best path: as-path '65020', next hop 10.0.100.2, local-pref 100, MED 0, communities none (held 11s, 3 samples) (10.6s)
Scenario: srl1-frr1 link fails
Destroying lab...
ERROR: failure scenarios on SR Linux nodes (srl1) are not supported yet; take the link down on the FRR/Linux side of the link instead
```

Fix: take down the other end of the same link. For `examples/srl-frr`, the link is `srl1:e1-1` to `frr1:eth1`:

```yaml
scenarios:
  - name: srl1-frr1 link fails
    link_down: {node: frr1, interface: eth1}
```

The effect on the network is the same: the link is down for both sides. `node_isolated` on an SR Linux node fails the same way; isolate its neighbors' links instead.

## MCP tool calls time out in the client

`dry_run` deploys a lab, so it takes 30 seconds to several minutes. Many MCP clients give up on a tool call sooner. Reproduced with the Python MCP SDK (mcp 2.3.0), `dry_run` on `my-lab` and a 20-second client timeout:

```text
MCPError: Request 'tools/call' timed out
```

With a 300-second timeout, the same call returned the full result (`"status": "passed"`) after 41 seconds.

When the client gives up, it usually stops the server. From 0.3.1, the server then destroys the lab before it exits: in the run above, the lab's three containers were up when the call timed out and gone a few seconds later, before the client had exited. 0.3.0 and earlier left the lab running. A server killed without a chance to clean up (`SIGKILL`) still leaves it; the next `dry_run` on that lab then refuses to deploy (see [a lab named X is already running](#a-lab-named-x-is-already-running)) until you destroy it with `containerlab destroy -t my-lab/topology.clab.yml --cleanup`.

Fixes:

- **Raise the client's tool timeout** to at least 5 minutes. In Claude Code, set `MCP_TOOL_TIMEOUT` (milliseconds) before starting it, for example `MCP_TOOL_TIMEOUT=600000 claude`. For other clients, look for a tool-call or request timeout setting.
- **Make the lab faster.** Lower `timeout` in `netdryrun.yml` so a broken change fails sooner, and pull images in advance so the first call does not wait on a download.
- **If the client cannot wait that long**, let the agent run `netdryrun run <folder>` in a shell and read `netdryrun-report.json`.

## No PR comment on a big lab

GitHub rejects a comment longer than 65,536 characters. From 0.3.1, the Markdown report (the PR comment and the job summary) stays under that: failed checks come first, and once the table would pass about 65,000 characters it stops with one row that says how many it left out. For a run of 1,500 checks, 5 of them failed, the 0.3.1 report code produced 64,845 characters: the 5 failures and 763 passed checks, then

```text
| | … 732 more checks (0 failed, 732 passed) | not shown: too many for one comment; all are in the JSON report | |
```

The JSON report and the job status always have every check. If the left-out rows matter to your reviewers, trim the file to the checks that matter, or split it into several `netdryrun.yml` files run as a [matrix](github-action.md#several-labs).

0.3.0 and earlier listed every check in the comment, about 90 characters each, so above roughly 700 checks GitHub rejected it: the job log said `could not comment on the PR (needs permissions pull-requests: write ...)` even though the permission was set. The verdict, the job status and the reports were not affected.

## Inconclusive: the lab never came up

Exit code `3` means checks failed, but the lab never reached a testable state, so the result says nothing about your change. Reproduced by turning off `bgpd` in the FRR `daemons` file of a copy of `examples/frr-bgp`, with `timeout: 30` and its failure scenario removed:

```text
$ netdryrun run . --json report.json
Netdryrun 0.3.1: 7 checks from netdryrun.yml
Deploying lab ndr-docs-nobgp (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [FAIL] r1: BGP session to 10.0.12.2 is established -- error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running (33.1s)
  [FAIL] r1: BGP session to 10.0.13.2 is established -- error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running (33.1s)
  [FAIL] r1: route 192.168.3.0/24 via bgp is present -- error: `vtysh -c show bgp ipv4 unicast 192.168.3.0/24 json` failed on r1 (rc=1): bgpd is not running (33.1s)
  [FAIL] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 0/3 replies (need 2) (33.1s)
warning: r1 never returned BGP state; its post-convergence checks start without the BGP gate
Convergence checks done; settling 10s before post-convergence checks...
  [FAIL] r1: prefixes from 10.0.12.2 >= 1 and <= 10 -- error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running (30.1s)
  [FAIL] r1: BGP best path for 192.168.2.0/24 has as-path '65002', next hop 10.0.12.2 -- error: `vtysh -c show bgp ipv4 unicast 192.168.2.0/24 json` failed on r1 (rc=1): bgpd is not running (0.1s)
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- error: `vtysh -c show bgp ipv4 unicast 0.0.0.0/0 json` failed on r1 (rc=1): bgpd is not running (0.1s)
Destroying lab...
INCONCLUSIVE: the lab did not reach a testable state: r1 never returned usable BGP state (r1: error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running), and no check passed on any sample. Rerun with a longer timeout, or check that the lab boots (7 of 7 checks failed; this says nothing about the change)
  wrote json report: report.json
```

The run took 111 seconds. From 0.3.2 the failure scenario can stay in: once the main checks show the lab never reached a testable state, the run logs `The lab never reached a testable state; 1 scenario(s) skipped`, applies no fault, and ends with this verdict (exit code `3`). 0.3.1 instead stopped at the scenario with exit code `2` and [could not read BGP state on r1](#could-not-read-bgp-state-to-find-the-sessions-over-the-links). A lab whose main checks did read state (the session to a node without `bgpd` is down) still stops there with exit code `2`. Either way the run is never `passed`.

The JSON report has the same text in `inconclusive_reason`, and every unready sample in `history` is marked:

```json
{"t": 33.1, "passed": false, "detail": "error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running", "unready": true}
```

How it differs from the other results:

- **`error` (exit `2`):** the run could not start or finish: a config error, a missing tool, a failed deploy, a fault that did not take effect.
- **`failed` (exit `1`):** the lab was up and something is wrong. A configured BGP session that is down (an ASN typo, as in [the lab never converges](#the-lab-never-converges-timeout)) is `failed`, not `inconclusive`.
- **`inconclusive` (exit `3`):** no positive check passed on any sample, and every failed check is on a node whose CLI or BGP never answered.

Fix: check that the lab boots (`containerlab inspect`, `docker logs <container>`), that the routing daemon is enabled, and that `timeout` is long enough for slow NOSes, then rerun. One known limit: a change that deletes a node's whole BGP config looks the same and is reported `inconclusive`. It is still never `passed`. See the [full rules](reference/cli.md#when-a-run-is-inconclusive).

## Still stuck

Run with `--keep-on-failure`, look inside the nodes with `docker exec`, and read the JSON report (`--json report.json`): every check keeps the raw commands and output. If it looks like a bug, [open an issue](https://github.com/netdryrun/netdryrun/issues) with the report attached. See [Support](support.md).
