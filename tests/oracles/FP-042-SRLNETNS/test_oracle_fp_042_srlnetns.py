"""Oracle FP-042-SRLNETNS: on containerlab 0.83 SR Linux runs in a namespace holder that containerlab made for it.

What the lab showed (tests/fixtures/clab083_srl_netns_capture.txt, containerlab 0.83.0, examples/srl-frr deployed as
ndr-srl-netns, SR Linux 26.7.2):
- srl1's container has `HostConfig.NetworkMode` = `container:4b66c3e3...` (the full id), and no networks of its own;
- that id is the container `/clab-ndr-srl-netns-srl1-netns`, which is not a node of the topology. Its labels are
  `containerlab: ndr-srl-netns`, `clab-internal-node: "true"`, `clab-node-type: srl-netns`,
  `clab-root-node-name: srl1`, `clab-root-node-longname: clab-ndr-srl-netns-srl1`; it is on the `clab` network;
- srl1 and the holder share one network namespace (net:[4026532304]); frr1 has its own;
- netdryrun 0.4.1 `check` exits 2: "reads srl1, which runs in the namespace of 4b66c3e3..., which is not a lab node".

The rule (spec fastfix/oracle-specs/FP-042-SRLNETNS.md): the refusal stays for every namespace that isn't the lab's.
Only a holder that containerlab made for this node of this lab, as its labels show, may stand in for a lab node.
Still refused: network-mode host; a holder whose labels name another lab or another node; a container with the
holder's name and none of its labels; a holder `docker inspect` can't read.

Everything goes through `mgmt.prepare` (which reads each node with `docker_mgmt` and ends in `refuse_checks`) on a real
`Lab` built from the deployed topology, with Docker's answers taken from the capture: `docker inspect <container>`
answers by name, full id or id prefix, as Docker does. Any other Docker command wasn't captured and fails (rc 1). frr1's
own management-route step (`prepare_linux`, which reads its routes) isn't part of this bug and wasn't captured: it is
stood in for, marking frr1 as handled.

The tests here fail on the parent. The guards, which pass before and after the fix, are in
tests/test_oracle_guards_fp_042_srlnetns.py (listed in ORACLE.yml `evidence:`).
"""
import copy
import json
from pathlib import Path

from netdryrun import lab as labmod
from netdryrun import mgmt
from netdryrun.config import _validate_check, load_yaml
from netdryrun.lab import ExecResult, Lab, LabError

ROOT = Path(__file__).resolve().parents[3]
FX = ROOT / "tests" / "fixtures"
HOLDER_ID = "4b66c3e32d2d32f86eefba43b4420e5c7112c2575ae12bcc6ebc9e9335a2a92c"


def inspect(name: str) -> dict:
    return json.loads((FX / f"clab083_srl_netns_inspect_{name}.json").read_text(encoding="utf-8"))


def captured() -> dict:
    """Every container of the lab as `docker inspect` printed it: srl1, its holder, frr1."""
    return {"srl1": inspect("srl1"), "holder": inspect("srl1_netns"), "frr1": inspect("frr1")}


def checks():
    """The example's own checks (examples/srl-frr/netdryrun.yml, the file the capture ran)."""
    raw = load_yaml((ROOT / "examples" / "srl-frr" / "netdryrun.yml").read_text(encoding="utf-8"), "netdryrun.yml")
    return [_validate_check(i, c, 20) for i, c in enumerate(raw["checks"])]


def docker(containers: dict):
    """`docker inspect X...` answered from the captured containers (X a name, with or without "/", a full id or a
    unique id prefix); found ones printed as a list, a missing one an error with rc 1, as Docker does."""
    def run(cmd, timeout=600, env=None, input=None, errors=None):
        args = list(cmd)
        if args[:2] != ["docker", "inspect"] or any(a.startswith(("-f", "--format")) for a in args[2:]):
            return ExecResult(args, 1, "", f"not captured: {' '.join(args)}")
        targets, rest = [], args[2:]
        while rest:
            a = rest.pop(0)
            if a == "--type":
                rest.pop(0)
            elif not a.startswith("-"):
                targets.append(a)
        found, missing = [], []
        for t in targets:
            hits = [c for c in containers.values() if c["Name"].lstrip("/") == t.lstrip("/") or c["Id"] == t] or \
                   [c for c in containers.values() if c["Id"].startswith(t)]
            (found.append(hits[0]) if len(hits) == 1 else missing.append(t))
        err = "".join(f"Error response from daemon: No such object: {t}\n" for t in missing)
        return ExecResult(args, 1 if missing else 0, json.dumps(found), err)
    return run


def lab_of(monkeypatch, tmp_path, containers: dict) -> Lab:
    topo = tmp_path / "topology.clab.yml"
    topo.write_bytes((FX / "clab083_srl_netns_topology.clab.yml").read_bytes())
    monkeypatch.setattr(labmod, "_run", docker(containers))

    def frr1_handled(lab, m, log):
        m.kind = "linux"
    monkeypatch.setattr(mgmt, "prepare_linux", frr1_handled)
    return Lab(topo)


def prepare(monkeypatch, tmp_path, containers: dict):
    """mgmt.prepare on the lab: None when the checks may run, else the LabError it raised."""
    lab = lab_of(monkeypatch, tmp_path, containers)
    try:
        mgmt.prepare(lab, checks(), sleep=lambda s: None)
    except LabError as e:
        return e
    return None


def relabel(holder: dict, old: str, new: str) -> dict:
    """The holder as another one would print: `old` replaced by `new` in its name and every label (the id stays, so
    srl1's NetworkMode still names it)."""
    h = copy.deepcopy(holder)
    h["Name"] = h["Name"].replace(old, new)
    h["Config"]["Labels"] = {k: v.replace(old, new) for k, v in h["Config"]["Labels"].items()}
    return h


# ------------------------------------------------------------------ red on 0.4.1

def test_captured_layout_is_accepted(monkeypatch, tmp_path):
    """The 0.83 layout as captured: srl1 in the namespace of the holder containerlab made for it. Its checks run."""
    error = prepare(monkeypatch, tmp_path, captured())
    assert error is None, f"refused the captured containerlab 0.83 layout: {error}"
