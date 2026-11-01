# Advisory: Netdryrun 0.3.3 could pass on a lab whose topology `exec:` command failed

**Affected:** netdryrun 0.3.3 and earlier, and the `netdryrun/netdryrun@v0.3.3` Action, on any lab whose `topology.clab.yml` gives a node `exec:` commands, on every platform. **Fixed in:** 0.4. **Found by:** our own 0.4 multi-vendor audit, which reproduced it on a live lab, before any outside user reported it.

## What happened

containerlab runs a node's `exec:` commands after the node starts. When one of them fails, containerlab logs the error and goes on: the deploy still exits 0, and the node runs without what the command would have configured. Reproduced on containerlab 0.81.1 with an FRR node whose `exec:` ran a `vtysh` line FRR rejects:

```text
ERRO Failed to execute command command="vtysh -c conf t -c router bgp 65001 -c neighbor 10.0.12.2 defualt-originate" node=r1 rc=1
  stdout=
  │ % Unknown command: neighbor 10.0.12.2 defualt-originate
```

containerlab exited 0, and the router ran without the line.

Netdryrun 0.3.3 checks containerlab's exit code, and on FRR it reads the boot log for lines rejected from `frr.conf` (the [0.3.2 advisory](../0.3.2-rejected-config/README.md)). It didn't read containerlab's log of `exec:` commands. So a change, or part of the lab's setup, applied through a topology `exec:` line that failed never reached the lab, and the checks ran on the network without it: a run could pass. A check that the change must not break something passes trivially when the change isn't there. The same holds for `ip route del default` and any other `exec:` line a check depends on.

`setup:` commands in `netdryrun.yml` are not affected: Netdryrun runs them itself and stops the run when one exits non-zero.

## What to do until 0.4

- **Put routing config in `setup:` in `netdryrun.yml`, or, on FRR, in `frr.conf`; never in topology `exec:` lines.** On Arista cEOS, SR Linux and SONiC, 0.3.3 doesn't check the startup config either (a [published limit](https://netdryrun.com/trust/), fixed in 0.4), so `setup:` is the only checked route there.
- Keep `exec:` for lab plumbing. To check a lab once, deploy it by hand with `containerlab deploy -t topology.clab.yml` and look for `Failed to execute command` in its output.

## What 0.4 does

After `containerlab deploy`, Netdryrun reads its output; any `Failed to execute command` line makes the run an **error (exit 2)**, naming the node, the command, its exit code and its output, never a pass. It is the same on every platform, in `netdryrun run` and on both sides of `netdryrun verify`.

## Found another way it can pass without looking?

[Open a corpus case](https://github.com/netdryrun/netdryrun/issues/new?template=corpus-case.yml): it becomes a permanent must-fail test, credited to you.
