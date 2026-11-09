# Oracle spec FP-042-SRLNETNS: SR Linux refused as "not a lab node" on containerlab 0.83

Status: **spec only**. A session that is not the fixer writes the oracle from a real run on containerlab 0.83.0
(GitHub runner or the laptop). The capture waits for "IPI: renders done" and the hub's ok.

## The bug (found by the stranger on published 0.4.1)
- **Where:** hq run 42599196181, readme job, containerlab 0.83.0.
- **What happens:** `netdryrun run examples/srl-frr` exits 2 with "check 'srl1: BGP session to 10.0.100.2 is
  established' reads srl1, which runs in the namespace of 51073d3c..., which is not a lab node: it would test the
  host, not the lab".
- **The code path:** `mgmt.refuse_checks`. srl1's Docker `NetworkMode` is `container:<id>`, and `mgmt._owner` finds no
  lab node with that name, container name or id.
- **Why the local gate passed:** on the older containerlab the live gate ran, srl-frr passed, so the layout changed.
- **Severity:** it fails safe, but the README path for SR Linux is broken on current containerlab.

## The guard must stay
- The refusal exists for a false-pass reason: a check run in the host's namespace, or in a foreign container's,
  tests that network and not the lab.
- **The fix may accept only a namespace holder that containerlab created for this lab node.** Proof comes from the
  capture, for example:
  - the holder's containerlab labels: `containerlab=<this lab>` and `clab-node-name=<this node>`;
  - its name pattern;
  - a documented containerlab mechanism, cited from the containerlab 0.83 source or release notes.
- **Still refused:** network-mode host; a container of another lab; a container without this lab's labels; a
  container whose labels name another node. A holder that only *looks* like ours (a name match without labels) is
  refused.

## Evidence to capture (on containerlab 0.83.0, examples/srl-frr unchanged)
- **The versions:** `containerlab version`, and the SR Linux image digest.
- **For every container of the lab, and for the container named by srl1's NetworkMode:**
  `docker inspect --format '{{json .}}'`. Keep the Name, Id, Config.Labels, HostConfig.NetworkMode and State.Pid.
- **Anything else the namespace holder starts:** `docker ps -a --filter label=containerlab=<lab>`, and the same
  without the filter, to see an unlabelled sidecar.
- **The namespaces:** `ls -l /proc/<pid>/ns/net` for srl1, the holder and the FRR node.
- **For contrast:** the same `docker inspect` on the containerlab version the 0.4.1 gate used.
- **Save to:** `tests/fixtures/clab083_srl_inspect.json` and friends, plus `capture.txt` (versions, commands, date),
  with provenance entries.

## The oracle (after the capture)
- **Folder:** `tests/oracles/FP-042-SRLNETNS/`. The tests feed the captured `docker inspect` data through the same
  path `refuse_checks` uses (a fake Lab whose `docker_inspect` returns the captured JSON).
- **The tests:**
  1. The captured 0.83 srl-frr layout is accepted: no LabError for srl1's checks.
  2. **The guard holds:** the same layout with the holder's labels naming another lab, or another node, or removed,
     is refused. network-mode host is refused.
- **On the parent commit:** test 1 must fail with an assertion (the LabError is turned into one), and test 2 passes
  there too, as a guard.

## Also in this fix
- `compatibility.md` gains a "containerlab versions tested" row: the versions the gate's live layer and the stranger
  ran on, with dates.
- The stranger keeps running on GitHub's current containerlab before every tag (0.4.2 priority 2).
