"""verify's lab-facing glue and its verdict-path helpers, pinned without a lab: `real_side` and `run_guards` with the
lab, the snapshot loop and the runner faked; the bind, node and collection helpers on small topologies. Each
test pins a behaviour a mutation run showed no test held (mutmut 3 on run.py, before 0.4)."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun import runner
from netdryrun.config import ConfigError
from netdryrun.lab import ExecResult, LabError, Node
from netdryrun.verify import run as vrun
from netdryrun.verify.converge import Inconclusive
from netdryrun.verify.snapshot import NodeSnapshot, Snapshot
from test_verify_run import make_lab
from verify_helpers import base

FRR_IMAGE = "quay.io/frrouting/frr:10.4.1"


def node(name: str, kind: str = "linux", image: str = FRR_IMAGE) -> Node:
    return Node(name, f"clab-t-{name}", kind, image)


def fake_lab(*nodes: Node) -> SimpleNamespace:
    return SimpleNamespace(nodes={n.name: n for n in nodes})


# --- real_side ---------------------------------------------------------------------------------------------

class SideLab:
    """A deployed lab: `cat` of each node's FRR config files, every exec recorded with its time limit."""

    def __init__(self, files: dict[tuple[str, str], str]):
        self.files, self.execs = files, []

    def exec(self, node, argv, timeout="unset"):
        self.execs.append((node, argv, timeout))
        path = argv[1] if isinstance(argv, list) and len(argv) == 2 and argv[0] == "cat" else None
        if (node, path) in self.files:
            return ExecResult(argv, 0, self.files[(node, path)], "")
        return ExecResult(argv or [], 1, "", "No such file")


NODES = {"r1": "frr", "r2": "frr", "h1": ""}
FILES = {("r1", "/etc/frr/frr.conf"): "frr version 10.4.1\nrouter bgp 65001\n",
         ("r2", "/etc/frr/frr.conf"): "frr version 10.4.1\nrouter ospf\n",
         ("h1", "/etc/frr/frr.conf"): "router bgp 65009\n"}


def patch_side(monkeypatch, snap, loaded_error: Exception | None = None):
    """Fake every lab-touching piece real_side calls; returns the record of what each was given."""
    lab = SideLab(FILES)
    rec = SimpleNamespace(lab=lab, deployed=[], stable=[], collect=[], loaded=[])

    @contextmanager
    def deployed(topology, setup, keep, log):
        rec.deployed.append((topology, setup, keep, log))
        yield lab

    def stable_snapshot(collect, *, settle, timeout, log, bgp_nodes):
        rec.stable.append({"settle": settle, "timeout": timeout, "log": log, "bgp_nodes": bgp_nodes})
        return collect()

    def collect(lab_, nodes, cmd_timeout):
        rec.collect.append((lab_, nodes, cmd_timeout))
        return snap

    def check_config_loaded(lab_, nodes, label):
        rec.loaded.append((lab_, nodes, label))
        if loaded_error is not None:
            raise loaded_error

    monkeypatch.setattr(vrun, "deployed", deployed)
    monkeypatch.setattr(vrun, "stable_snapshot", stable_snapshot)
    monkeypatch.setattr(vrun, "collect", collect)
    monkeypatch.setattr(vrun, "check_config_loaded", check_config_loaded)
    monkeypatch.setattr(vrun, "time", SimpleNamespace(monotonic=iter([100.0, 101.234]).__next__))
    return rec


def make_side(*, timeout=300.0, keep_after=False, settle=2.5, logs=None):
    log = (logs if logs is not None else []).append
    setup = {"r1": ["ip link set eth1 up"]}
    return vrun.real_side(nodes=NODES, setup=setup, settle=settle, timeout=timeout, keep_after=keep_after,
                          log=log), setup, log


def test_real_side_deploys_snapshots_checks_the_load_and_runs_on_up(monkeypatch):
    """One side, end to end: deploy the given topology with the setup and the side's log, wait for a stable
    snapshot of that lab, check the config loaded, run on_up on the same lab, and return the snapshot, the
    wall time (one decimal) and what on_up returned. Any argument dropped or swapped here boots or judges the
    wrong thing."""
    snap = base().snap()
    rec = patch_side(monkeypatch, snap)
    logs = []
    side, setup, log = make_side(logs=logs)
    seen = []
    topo = Path("/labs/after/topology.clab.yml")
    out = side("after", topo, on_up=lambda lab, t: seen.append((lab, t)) or {"status": "passed"})
    assert out == (snap, 1.2, {"status": "passed"}) and out[0] is snap
    assert rec.deployed == [(topo, setup, False, log)] and rec.deployed[0][2] is False
    assert rec.collect == [(rec.lab, NODES, 300.0)] and rec.collect[0][1] is NODES
    assert rec.stable == [{"settle": 2.5, "timeout": 300.0, "log": log, "bgp_nodes": {"r1"}}]
    assert rec.loaded == [(rec.lab, NODES, "after")]
    assert seen == [(rec.lab, topo)]
    assert logs == ["[after] waiting for a stable snapshot (settle 2.5s, timeout 300s)..."]


def test_real_side_reads_bgp_nodes_with_a_60s_exec_on_frr_nodes_only(monkeypatch):
    """bgp_nodes are the FRR nodes whose config file has `router bgp`, read in the container with a 60s limit; a
    node not snapshotted is never read, even with `router bgp` in its file (it would be waited on for nothing)."""
    rec = patch_side(monkeypatch, base().snap())
    side, _, _ = make_side()
    side("before", Path("t.clab.yml"))
    assert rec.lab.execs == [("r1", ["cat", "/etc/frr/frr.conf"], 60), ("r2", ["cat", "/etc/frr/frr.conf"], 60),
                             ("r2", ["cat", "/etc/frr/bgpd.conf"], 60)]
    assert rec.stable[0]["bgp_nodes"] == {"r1"}


@pytest.mark.parametrize("timeout, cmd_timeout", [(30.0, 60.0), (300.0, 300.0)])
def test_real_side_gives_each_command_at_least_60s(monkeypatch, timeout, cmd_timeout):
    """Each snapshot command may run for the side's timeout, never less than 60s (a short --timeout would cut a
    slow `show` and read as an incomplete snapshot)."""
    rec = patch_side(monkeypatch, base().snap())
    side, _, _ = make_side(timeout=timeout)
    side("before", Path("t.clab.yml"))
    assert rec.collect[0][2] == cmd_timeout and rec.stable[0]["timeout"] == timeout


@pytest.mark.parametrize("keep_after, label, keep", [(True, "after", True), (True, "before", False),
                                                     (False, "after", False), (False, "before", False)])
def test_real_side_keeps_only_the_after_lab_and_only_with_keep(monkeypatch, keep_after, label, keep):
    """--keep leaves the after lab running for inspection; the before lab (and every lab without --keep) is
    destroyed, or the next side would find a lab of the same name already up."""
    rec = patch_side(monkeypatch, base().snap())
    side, _, _ = make_side(keep_after=keep_after)
    side(label, Path("t.clab.yml"))
    assert rec.deployed[0][2] is keep


def test_real_side_without_on_up_returns_no_extra(monkeypatch):
    """The before side has no guards: its third value is None, and the load is checked under its own label."""
    snap = base().snap()
    rec = patch_side(monkeypatch, snap)
    side, _, _ = make_side()
    assert side("before", Path("t.clab.yml")) == (snap, 1.2, None)
    assert rec.loaded == [(rec.lab, NODES, "before")]


def test_real_side_that_never_settles_skips_the_load_check_and_the_guards(monkeypatch):
    """An inconclusive snapshot is returned as is: no load check and no guards run on a lab that never settled."""
    inc = Inconclusive("never settled", ["edge1: rib 10.0.0.0/24"])
    rec = patch_side(monkeypatch, inc)
    side, _, _ = make_side()
    called = []
    out = side("after", Path("t.clab.yml"), on_up=lambda lab, t: called.append(1) or {"status": "passed"})
    assert out == (inc, 1.2, None) and out[0] is inc
    assert rec.loaded == [] and called == []


def test_real_side_stops_on_a_rejected_config_before_the_guards(monkeypatch):
    """A config the NOS rejected stops the side (exit 2) before the guards run on it."""
    patch_side(monkeypatch, base().snap(), loaded_error=LabError("[after] rejected. No verdict."))
    side, _, _ = make_side()
    called = []
    with pytest.raises(LabError, match="rejected"):
        side("after", Path("t.clab.yml"), on_up=lambda lab, t: called.append(1))
    assert called == []


# --- run_guards --------------------------------------------------------------------------------------------

@dataclass
class Cfg:
    path: Path
    lab: Path
    timeout: float


def patch_run(monkeypatch, rep):
    calls = []

    def run(config, *, deploy, keep, settle, hold, log):
        calls.append({"config": config, "deploy": deploy, "keep": keep, "settle": settle, "hold": hold, "log": log})
        return rep
    monkeypatch.setattr(runner, "run", run)
    return calls


class Detail:
    def __str__(self):
        return "route present on peer1"


def result(name, passed, node=None, detail="ok"):
    params = {"node": node} if node else {"prefix": "203.0.113.0/24"}
    return SimpleNamespace(check=SimpleNamespace(name=name, params=params), passed=passed, detail=detail)


def test_run_guards_runs_the_guards_on_the_lab_already_up_and_reports_failures(monkeypatch):
    """The guards run on the after lab verify deployed: never deploy, never destroy it (verify does), with the
    topology swapped in and the rest of the guards config untouched. The report keeps the status, the counts, the
    error and each failed check with its node and reason."""
    rep = SimpleNamespace(status="failed", passed=1, failed=2, error="boom",
                          results=[result("bgp_session edge1", True, node="edge1"),
                                   result("route peer1", False, node="peer1", detail=Detail()),
                                   result("route anywhere", False, detail=Detail())])
    calls = patch_run(monkeypatch, rep)
    log = [].append
    cfg = Cfg(Path("/base/netdryrun.yml"), Path("/base/topology.clab.yml"), 42.0)
    out = vrun.run_guards(cfg, Path("/work/after/topology.clab.yml"), 3.0, 7.0, log)
    assert calls == [{"config": Cfg(Path("/base/netdryrun.yml"), Path("/work/after/topology.clab.yml"), 42.0),
                      "deploy": False, "keep": True, "settle": 3.0, "hold": 7.0, "log": log}]
    assert calls[0]["deploy"] is False and calls[0]["keep"] is True and calls[0]["log"] is log
    assert out == {"status": "failed", "passed": 1, "failed": 2, "error": "boom",
                   "failures": [{"check": "route peer1", "node": "peer1", "reason": "route present on peer1"},
                                {"check": "route anywhere", "node": None, "reason": "route present on peer1"}]}


def test_run_guards_reports_no_error_as_none(monkeypatch):
    """An empty error is None in the report (the schema's "no error"), never an empty string."""
    patch_run(monkeypatch, SimpleNamespace(status="passed", passed=2, failed=0, error="", results=[]))
    out = vrun.run_guards(Cfg(Path("g.yml"), Path("t.yml"), 1.0), Path("t2.yml"), 1.0, 1.0, print)
    assert out == {"status": "passed", "passed": 2, "failed": 0, "error": None, "failures": []}
    assert out["error"] is None


# --- check_sides -------------------------------------------------------------------------------------------

def mk_side(tmp_path, label, bound, sources):
    return vrun.Side(label=label, topology=tmp_path / "t.clab.yml", desc=f"directory {label}", root=tmp_path,
                     bound=bound, sources=sources)


def test_check_sides_counts_a_file_bound_on_one_side_only(tmp_path):
    """A bound file present on one side only is a difference (a file the change adds or removes)."""
    same = {"configs/r1.conf": "aa"}
    after = {**same, "configs/r2.conf": "bb"}
    logs = []
    assert vrun.check_sides(mk_side(tmp_path, "before", same, same), mk_side(tmp_path, "after", after, after),
                            logs.append) == ["configs/r2.conf"]


def test_check_sides_names_every_differing_file(tmp_path):
    """The self-check's log line and its collapsed-sides error list the files, comma separated, in full."""
    b = {"configs/r1.conf": "aa", "configs/r2.conf": "bb"}
    a = {"configs/r1.conf": "cc", "configs/r2.conf": "dd"}
    logs = []
    vrun.check_sides(mk_side(tmp_path, "before", b, b), mk_side(tmp_path, "after", a, a), logs.append)
    assert logs == ["bound files that differ between the sides: configs/r1.conf, configs/r2.conf"]
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.check_sides(mk_side(tmp_path, "before", b, b), mk_side(tmp_path, "after", b, a), logs.append)
    assert str(e.value) == ("both sides resolved to the same configs: configs/r1.conf, configs/r2.conf differ between "
                            "directory before and directory after, but every bound file hashes the same in the two "
                            "lab folders; refusing to compare")


# --- check_changed_binds -----------------------------------------------------------------------------------

def topo_file(tmp_path, nodes_yaml: str) -> Path:
    t = tmp_path / "t.clab.yml"
    t.write_text(f"name: t\ntopology:\n  nodes:\n{nodes_yaml}")
    return t


def test_a_changed_file_inside_a_bound_folder_is_judged_by_its_path_in_the_container(tmp_path):
    """A folder bound to /etc/frr: a changed frr.conf in it is a router config (allowed); a changed daemons in
    it is not (refused, named by its path in the container)."""
    t = topo_file(tmp_path, f"    r1: {{kind: linux, image: {FRR_IMAGE}, binds: [cfg:/etc/frr]}}\n")
    vrun.check_changed_binds(t, ["cfg/frr.conf"], {"r1": "frr"})
    with pytest.raises(vrun.VerifyInputError, match=r"cfg/daemons \(/etc/frr/daemons on r1\)"):
        vrun.check_changed_binds(t, ["cfg/daemons"], {"r1": "frr"})


def test_the_longest_bind_covering_a_changed_file_decides(tmp_path):
    """A file bound on its own inside a folder bound elsewhere is judged by its own bind (the more specific
    mount is what the container sees)."""
    t = topo_file(tmp_path, f"    r1: {{kind: linux, image: {FRR_IMAGE}, "
                            "binds: [conf:/opt/conf, conf/frr.conf:/etc/frr/frr.conf]}\n")
    vrun.check_changed_binds(t, ["conf/frr.conf"], {"r1": "frr"})
    with pytest.raises(vrun.VerifyInputError, match=r"conf/x.sh \(/opt/conf/x.sh on r1\)"):
        vrun.check_changed_binds(t, ["conf/x.sh"], {"r1": "frr"})


def test_changed_files_no_observed_node_runs_are_refused_with_the_full_message(tmp_path):
    """A changed file no container receives (bound only by a bridge) is refused as `? on ?`, a changed startup
    folder by its startup-config, each once, `; ` separated, with the way out."""
    t = topo_file(tmp_path, f"    r1: {{kind: linux, image: {FRR_IMAGE}, startup-config: sc}}\n"
                            "    br: {kind: bridge, binds: [b/x.conf:/etc/frr/frr.conf]}\n")
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.check_changed_binds(t, ["b/x.conf", "sc/x", "b/x.conf"], {"r1": "frr", "br": ""})
    assert str(e.value) == ("changed bound file(s) that are not a router config of a node verify observes: "
                            "b/x.conf (? on ?); sc/x (startup-config on r1). verify judges a change by what the "
                            "observed FRR nodes do, and can't tell what this file changes; change it in a separate "
                            "PR, tested with checks")


def test_a_changed_daemons_file_on_the_demo_lab_is_refused(tmp_path):
    """The demo lab's FRR `daemons` (a defaults bind) reaches every node: a change to it is refused on each."""
    t = make_lab(tmp_path) / "topology.clab.yml"
    nodes = {n: "frr" for n in ("cust1", "edge1", "up1", "peer1")}
    vrun.check_changed_binds(t, ["configs/edge1.conf"], nodes)
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.check_changed_binds(t, ["configs/daemons"], nodes)
    for n in nodes:
        assert f"configs/daemons (/etc/frr/daemons on {n})" in str(e.value)


# --- bind_reach --------------------------------------------------------------------------------------------

def test_bind_reach_names_the_topology_in_a_yaml_error(tmp_path):
    """A topology that isn't YAML: the error names the file."""
    t = tmp_path / "t.clab.yml"
    t.write_text("topology: [unclosed\n")
    with pytest.raises(ConfigError) as e:
        vrun.bind_reach(t)
    assert str(e.value).startswith(f"{t}: not valid YAML")


def test_bind_reach_tolerates_empty_and_malformed_sections(tmp_path):
    """Null defaults, a null node and a non-mapping section are skipped, never a crash; a bind with a mode keeps
    its source and destination; a bind without a colon or not a string is ignored."""
    t = tmp_path / "t.clab.yml"
    t.write_text("name: t\ntopology:\n  defaults:\n  kinds: [x]\n  groups: [y]\n  nodes:\n    r1:\n"
                 f"    r2: {{kind: linux, image: {FRR_IMAGE}, binds: [c/r2.conf:/etc/frr/frr.conf:ro, nocolon, 5]}}\n")
    assert vrun.bind_reach(t) == {"c/r2.conf": [("r2", "/etc/frr/frr.conf")]}
    t.write_text("name: t\ntopology:\n  defaults: {binds: [c/d:/etc/frr/daemons]}\n  nodes: [r1]\n")
    assert vrun.bind_reach(t) == {}
    t.write_text("name: t\ntopology:\n  defaults: {binds: [c/d:/etc/frr/daemons]}\n  nodes:\n    r1:\n")
    assert vrun.bind_reach(t) == {"c/d": [("r1", "/etc/frr/daemons")]}


def test_bind_reach_splits_at_the_first_colons(tmp_path):
    """source:destination[:mode]: the first field is the host path, the second the container path."""
    t = tmp_path / "t.clab.yml"
    t.write_text(f"name: t\ntopology:\n  nodes:\n    r1: {{image: {FRR_IMAGE}, binds: ['a:/etc/frr/frr.conf:ro:z']}}\n")
    assert vrun.bind_reach(t) == {"a": [("r1", "/etc/frr/frr.conf")]}


def test_bind_reach_leaves_out_bridges_by_kind_from_group_and_keeps_later_nodes(tmp_path):
    """A node whose group makes it a bridge has no container (left out) even with a linux default; a bridge
    listed first never stops the nodes after it."""
    t = tmp_path / "t.clab.yml"
    t.write_text("name: t\ntopology:\n  defaults: {kind: linux, binds: [c/d:/etc/frr/daemons]}\n"
                 "  groups:\n    sw: {kind: bridge}\n  nodes:\n    b0: {kind: bridge}\n    s1: {group: sw}\n"
                 "    r1: {}\n")
    assert vrun.bind_reach(t) == {"c/d": [("r1", "/etc/frr/daemons")]}


def test_bind_reach_records_startup_configs_file_and_inline(tmp_path):
    """A startup-config file reaches its node as `startup-config`; an inline one (several lines) is keyed as
    inline, never by its text."""
    t = tmp_path / "t.clab.yml"
    t.write_text(f"name: t\ntopology:\n  nodes:\n    r1: {{image: {FRR_IMAGE}, startup-config: cfg/r1.cfg}}\n"
                 "    r2:\n      startup-config: |\n        hostname r2\n        router bgp 1\n")
    assert vrun.bind_reach(t) == {"cfg/r1.cfg": [("r1", "startup-config")],
                                  "(inline startup-config)": [("r2", "startup-config")]}


# --- classify_nodes ----------------------------------------------------------------------------------------

def test_classify_names_every_unknown_unobserved_node():
    """--unobserved naming nodes not in the topology lists them all."""
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.classify_nodes(fake_lab(node("r1")), {}, ["zz", "yy"])
    assert str(e.value) == "--unobserved names node(s) not in the topology: yy, zz"


def test_unobserved_refuses_a_node_the_guards_say_runs_frr():
    """A node the guards file sets to FRR can't be unobserved, whatever its image says: it would go uncompared."""
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.classify_nodes(fake_lab(node("h1", image="alpine:3")), {"h1": "frr"}, ["h1"])
    assert str(e.value) == "--unobserved h1: h1 runs FRR, which verify observes; a change on it would go uncompared"


def test_a_host_kind_is_refused_unless_the_guards_name_its_driver():
    """A host kind without a driver in the guards is refused with --unobserved as the way out; with `driver: frr`
    it is snapshotted."""
    lab = fake_lab(node("x1", kind="host", image=""))
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.classify_nodes(lab, {}, [])
    assert str(e.value) == ("node x1 is of kind host: verify can't observe it, and an unobserved node could hide a "
                            "change. Pass --unobserved x1 if it has no routing stack")
    assert vrun.classify_nodes(lab, {"x1": "frr"}, []) == {"x1": "frr"}


def test_an_undetectable_node_is_refused_with_both_ways_out():
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.classify_nodes(fake_lab(node("h1", image="alpine:3")), {}, [])
    assert str(e.value) == ("cannot tell what runs on node h1 (kind 'linux', image 'alpine:3'); set nodes.h1.driver: "
                            "frr in the guards file, or pass --unobserved h1 if it is a host without a routing stack")


def test_an_unknown_driver_in_the_guards_is_refused():
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.classify_nodes(fake_lab(node("r1")), {"r1": "bogus"}, [])
    assert str(e.value) == "node r1: unknown driver 'bogus'"


# --- unobserved_reasons ------------------------------------------------------------------------------------

def test_unobserved_reasons_for_every_kind_of_unobserved_node():
    """Every unobserved node gets its reason: a bridge has no routing stack; a detected non-FRR NOS is named; a
    host, or an FRR image the guards set to another driver, was named --unobserved. A bridge sorted first never
    hides the rest."""
    lab = fake_lab(node("a-br", kind="bridge", image=""), node("h1", image="alpine:3"),
                   node("r9"), node("s1", kind="nokia_srlinux", image="ghcr.io/nokia/srlinux"), node("r1"))
    assert vrun.unobserved_reasons(lab, {"a-br": "", "h1": "", "r9": "", "s1": "", "r1": "frr"}) == {
        "a-br": "a bridge (no routing stack)",
        "h1": "named --unobserved (kind linux): changes on h1 are not compared",
        "r9": "named --unobserved (kind linux): changes on r9 are not compared",
        "s1": "runs srlinux: verify 0.4 snapshots FRR only; changes on s1 are not compared"}


# --- collect -----------------------------------------------------------------------------------------------

class CollectLab:
    def __init__(self, *nodes: Node):
        self.nodes = {n.name: n for n in nodes}
        self.execs = []

    def exec(self, node, argv, timeout="unset"):
        self.execs.append((node, argv[0], timeout))
        return ExecResult(argv, 0, "", "")


def patch_collector(monkeypatch):
    built = []

    class Collector:
        def __init__(self, n, exec_fn, owners=None):
            self.n, self.exec_fn = n, exec_fn
            built.append(n)

        def collect(self):
            assert self.exec_fn(self.n, ["vtysh", "-c", "show version"]) == (0, "", "")
            return NodeSnapshot(self.n, "frr", ("default",), {})
    monkeypatch.setattr(vrun, "FrrCollector", Collector)
    return built


@pytest.mark.parametrize("kw, limit", [({}, 60), ({"cmd_timeout": 45}, 45)])
def test_collect_runs_every_command_with_its_time_limit(monkeypatch, kw, limit):
    """Every command in a node (its addresses, each snapshot command) runs with the per-command limit, 60s by
    default."""
    patch_collector(monkeypatch)
    lab = CollectLab(node("r1"))
    vrun.collect(lab, {"r1": "frr"}, **kw)
    assert lab.execs == [("r1", "ip", limit), ("r1", "vtysh", limit)]


def test_collect_snapshots_frr_nodes_and_states_the_others(monkeypatch):
    """The snapshot holds each FRR node's collection and, for every node it leaves out, the reason computed on
    this lab and these nodes."""
    built = patch_collector(monkeypatch)
    seen = []

    def reasons(lab, nodes):
        seen.append((lab, nodes))
        return {"h1": "named --unobserved"}
    monkeypatch.setattr(vrun, "unobserved_reasons", reasons)
    lab = CollectLab(node("r1"), node("h1", image="alpine:3"))
    nodes = {"r1": "frr", "h1": ""}
    snap = vrun.collect(lab, nodes)
    assert isinstance(snap, Snapshot) and built == ["r1"]
    assert list(snap.nodes) == ["r1"] and snap.nodes["r1"].node == "r1"
    assert snap.unobserved == {"h1": "named --unobserved"}
    assert seen == [(lab, nodes)] and seen[0][0] is lab and seen[0][1] is nodes


# --- check_config_loaded -----------------------------------------------------------------------------------

def test_check_config_loaded_reads_each_node_by_its_snapshot_driver_else_by_detection(monkeypatch):
    """A snapshotted node is read by its driver; a node not snapshotted by the driver it is detected as, or by
    its log when none is (None). A rejected line stops the side, naming it."""
    lab = fake_lab(node("r1"), node("s1", kind="nokia_srlinux", image="ghcr.io/nokia/srlinux"),
                   node("h1", image="alpine:3"))
    drivers = {}

    def by_node(lab_, driver_of):
        assert lab_ is lab
        drivers.update({n: driver_of(n, nd) for n, nd in lab_.nodes.items()})
        return {"h1": ["line 3: bad"]}
    monkeypatch.setattr(runner, "config_load_by_node", by_node)
    monkeypatch.setattr(runner, "rejected_config_message", lambda found: "h1 rejected." if found else "")
    with pytest.raises(LabError) as e:
        vrun.check_config_loaded(lab, {"r1": "frr", "s1": "", "h1": ""}, "after")
    assert str(e.value) == "[after] h1 rejected. No verdict."
    assert drivers == {"r1": "frr", "s1": "srlinux", "h1": None}
    monkeypatch.setattr(runner, "rejected_config_message", lambda found: "")
    vrun.check_config_loaded(lab, {"r1": "frr"}, "before")


def test_check_config_loaded_trusts_the_snapshot_driver_over_detection(monkeypatch):
    """A node verify snapshots is read by the driver it was snapshotted with, even when its image alone wouldn't
    detect as that driver (a custom FRR image): never by re-detection."""
    lab = fake_lab(node("r1", image="registry.example/custom-router:1"))
    drivers = {}

    def by_node(lab_, driver_of):
        drivers.update({n: driver_of(n, nd) for n, nd in lab_.nodes.items()})
        return {}
    monkeypatch.setattr(runner, "config_load_by_node", by_node)
    monkeypatch.setattr(vrun, "detect", lambda nd: (_ for _ in ()).throw(AssertionError("re-detected")))
    vrun.check_config_loaded(lab, {"r1": "frr"}, "before")
    assert drivers == {"r1": "frr"}


def test_bind_reach_reads_the_topology_as_utf8_on_every_platform(tmp_path, monkeypatch):
    """The topology is read as UTF-8 whatever the platform's default encoding (Windows: cp1252), so a non-ASCII
    path in a bind reads the same everywhere."""
    import codecs
    t = tmp_path / "t.clab.yml"
    t.write_text(f"name: t\ntopology:\n  nodes:\n    r1: {{image: {FRR_IMAGE}, binds: ['café/r1.conf:/etc/frr/frr.conf']}}\n",
                 encoding="utf-8")
    real = Path.read_text
    seen = []

    def read_text(self, *args, **kwargs):
        seen.append(kwargs.get("encoding", args[0] if args else None))
        return real(self, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_text)
    assert vrun.bind_reach(t) == {"café/r1.conf": [("r1", "/etc/frr/frr.conf")]}
    assert seen and all(e is not None and codecs.lookup(e).name == "utf-8" for e in seen)
