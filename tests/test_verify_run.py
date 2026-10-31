"""`netdryrun verify` end to end without a lab: the sides (directories and git refs), the topology rule,
node classification, the verdict statuses and exit codes, the guards, the report and its JSON Schema."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from netdryrun import cli
from netdryrun.verify import report as vreport
from netdryrun.verify import run as vrun
from netdryrun.verify.converge import Inconclusive
from netdryrun.verify.snapshot import SnapshotError
from verify_helpers import add_new_customer_block, attrs, base, rib, session

jsonschema = pytest.importorskip("jsonschema")
ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "website/docs/schemas/verify-v1.json").read_text(encoding="utf-8"))

TOPO = """name: vlab
topology:
  defaults:
    kind: linux
    image: quay.io/frrouting/frr:10.4.1
    binds:
      - configs/daemons:/etc/frr/daemons
      - shared/vtysh.conf:/etc/frr/vtysh.conf
  nodes:
    cust1: {binds: [configs/cust1.conf:/etc/frr/frr.conf]}
    edge1: {binds: [configs/edge1.conf:/etc/frr/frr.conf]}
    up1: {binds: [configs/up1.conf:/etc/frr/frr.conf]}
    peer1: {binds: [configs/peer1.conf:/etc/frr/frr.conf]}
  links:
    - endpoints: ["edge1:eth1", "cust1:eth1"]
"""
GUARDS = """lab: topology.clab.yml
checks:
  - {type: bgp_session, node: edge1, neighbor: 10.0.1.2}
  - {type: route, node: peer1, prefix: 203.0.113.0/24, present: false}
"""


def validate(res) -> dict:
    data = json.loads(vreport.to_json(res))
    jsonschema.Draft202012Validator(SCHEMA).validate(data)
    return data


def make_lab(tmp_path: Path, topo: str = TOPO) -> Path:
    d = tmp_path / "lab"
    (d / "configs").mkdir(parents=True)
    (d / "shared").mkdir()
    (d / "topology.clab.yml").write_text(topo)
    (d / "shared" / "vtysh.conf").write_text("service integrated-vtysh-config\n")
    for f in ("daemons", "cust1.conf", "edge1.conf", "up1.conf", "peer1.conf"):
        (d / "configs" / f).write_text(f"! {f} before\n")
    return d


def side_dir(tmp_path: Path, lab: Path, name: str, edit: str | None = None) -> Path:
    """A directory side: a copy of the lab's tree (its configs and every other bound file)."""
    d = tmp_path / name
    for sub in ("configs", "shared"):
        shutil.copytree(lab / sub, d / sub)
    if edit:
        (d / "configs" / "edge1.conf").write_text(edit)
    return d


def intent_file(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "intent.yml"
    p.write_text(text)
    return p


def fake_side(before, after, guards=None, raise_on=None):
    calls = []

    def side(label, topology, on_up=None):
        folder = Path(topology).parent
        calls.append((label, {f.relative_to(folder).as_posix(): f.read_bytes()
                              for f in folder.rglob("*") if f.is_file()}))
        if raise_on == label:
            raise SnapshotError("unexpected output from `show bgp vrf all neighbors json`: unknown field(s) ['x']")
        snap = before if label in ("before", "rerun-before") else after
        return snap, 1.0, (guards if label == "after" else None)
    side.calls = calls
    return side


NEW_BLOCK = "intent:\n  - prefix: 10.101.0.0/24\n    appears_on: [edge1, up1, peer1]\n"


def run_verify(tmp_path, before_snap, after_snap, intent_text=NEW_BLOCK, guards=None, **kw):
    lab = make_lab(tmp_path)
    b = side_dir(tmp_path, lab, "before")
    a = side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    side = fake_side(before_snap, after_snap, guards=guards, raise_on=kw.pop("raise_on", None))
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, intent_text)),
                      side_fn=side, **kw)
    return res, side


# --- statuses and exit codes -------------------------------------------------------------------------------

def test_matched(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap())
    assert (res.status, res.exit_code) == ("matched", 0)
    data = validate(res)
    assert data["verdict"] == "INTENT MATCHED" and data["intent"]["lines"] and not data["undeclared"]
    assert data["evidence"]["before"]["schema"] == "netdryrun.snapshot/v1"
    assert [c[0] for c in side.calls] == ["before", "after", "rerun-before", "rerun-after"]
    # each side's lab folder holds the topology byte for byte, its own configs and the shared binds
    bfiles, afiles = side.calls[0][1], side.calls[1][1]
    assert afiles["configs/edge1.conf"] == b"! edge1 after\n"
    assert bfiles["configs/edge1.conf"] == b"! edge1.conf before\n"
    assert "shared/vtysh.conf" in afiles
    assert afiles["topology.clab.yml"] == bfiles["topology.clab.yml"] == TOPO.encode()


def test_undeclared_changes(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap(), intent_text="intent: []\n")
    assert (res.status, res.exit_code) == ("failed", 1) and res.failed_because == ["undeclared"]
    data = validate(res)
    assert data["verdict"] == "UNDECLARED CHANGES: DO NOT APPLY"
    for it in data["undeclared"]:
        assert it["next_diagnostic"].startswith("docker exec clab-vlab-") and "vtysh" in it["next_diagnostic"]
    assert {it["route_before"] for it in data["undeclared"] if it["kind"] == "rib"} == {"absent"}


def test_declared_but_did_not_happen(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap())
    assert (res.status, res.exit_code) == ("failed", 1) and res.failed_because == ["not_happened"]
    assert validate(res)["not_happened"][0]["intent"] == 0


def test_no_behavior_change(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap(), intent_text="intent: []\n")
    assert (res.status, res.exit_code) == ("no_change", 0)
    assert validate(res)["verdict"] == "NO BEHAVIOR CHANGE"


def test_unreadable_snapshot_is_exit_2(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap(), raise_on="after")
    assert (res.status, res.exit_code) == ("error", 2) and res.match is None
    assert validate(res)["error"]


def test_inconclusive_is_exit_3(tmp_path):
    inc = Inconclusive("kept moving", ["edge1 203.0.113.0/24 changed"])
    res, side = run_verify(tmp_path, inc, base().snap())
    assert (res.status, res.exit_code) == ("inconclusive", 3)
    assert [c[0] for c in side.calls] == ["before"]           # the after lab is not deployed
    data = validate(res)
    assert data["inconclusive"]["side"] == "before" and data["inconclusive"]["moving"]


def test_unhealthy_baseline(tmp_path):
    from verify_helpers import session
    lab = base()
    lab.session("edge1", "10.0.9.2", session(None, state="active"))
    res, side = run_verify(tmp_path, lab.snap(), base().snap())
    assert (res.status, res.exit_code) == ("unhealthy_baseline", 3) and res.baseline_problems
    assert [c[0] for c in side.calls] == ["before"]
    validate(res)
    after = add_new_customer_block(lab.copy())
    res, _ = run_verify(tmp_path / "again", lab.snap(), after.snap(), allow_unhealthy_baseline=True)
    assert res.status == "matched" and res.baseline_overridden
    assert validate(res)["baseline"] == {"healthy": False, "problems": res.baseline_problems, "overridden": True}


def test_failed_guards_fail_a_matched_intent(tmp_path):
    """A dishonest intent can explain a leak; the standing guards (from the base) still fail it."""
    guards = {"status": "failed", "passed": 1, "failed": 1, "error": None, "source": "netdryrun.yml at main",
              "failures": [{"check": "LEAK GUARD", "node": "peer1", "reason": "route present"}]}
    after = base()
    after.adj_out("edge1", "10.0.3.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    after.learn("peer1", "203.0.113.0/24", "10.0.3.1", "65000 65002")
    res, _ = run_verify(tmp_path, base().snap(), after.snap(), guards=guards,
                        intent_text="intent:\n  - {prefix: 203.0.113.0/24, appears_on: [peer1]}\n")
    assert (res.status, res.exit_code) == ("failed", 1) and res.failed_because == ["guards"]
    assert validate(res)["guards"]["failed"] == 1


@pytest.mark.parametrize("gstatus,status", [("error", "error"), ("inconclusive", "inconclusive")])
def test_guards_without_a_verdict_leave_no_verdict(tmp_path, gstatus, status):
    guards = {"status": gstatus, "passed": 0, "failed": 0, "error": "lab problem", "failures": []}
    res, _ = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap(), guards=guards)
    assert res.status == status
    validate(res)


def test_allow_anywhere_warns(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap(),
                        intent_text="intent: []\nallow_anywhere: ['10.200.*.0/24']\n")
    assert res.status == "no_change" and res.warnings == [vreport.ALLOW_WARNING, vreport.NO_GUARDS_WARNING]


def test_bad_intent_is_exit_2(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), base().snap(), intent_text="intent:\n  - prefix: nope\n")
    assert (res.status, res.exit_code) == ("error", 2) and not side.calls
    assert validate(res)["intent"] is None


def test_unknown_node_in_the_intent_is_exit_2(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), base().snap(),
                           intent_text="intent:\n  - {prefix: 10.1.0.0/24, appears_on: [r9]}\n")
    assert res.exit_code == 2 and not side.calls


# --- the determinism rule: no approval from a single boot (0.4 roadmap review) ---------------------------------
# An approving verdict (INTENT MATCHED, NO BEHAVIOR CHANGE) boots the after side a second time; if that rerun
# gives a different snapshot, the lab isn't deterministic and nothing is approved: INCONCLUSIVE, naming the
# items that differed. A failing verdict approves nothing and needs no rerun.

def rerun_side(before, after, rerun):
    side = fake_side(before, after)
    inner = side

    def wrapped(label, topology, on_up=None):
        snap, t, extra = inner(label, topology, on_up)
        return (rerun if label == "rerun-after" else snap), t, extra
    wrapped.calls = side.calls
    return wrapped


def test_an_approval_is_confirmed_by_a_rerun_of_the_after_side(tmp_path):
    after = add_new_customer_block(base()).snap()
    res, side = run_verify(tmp_path, base().snap(), after)
    assert (res.status, res.exit_code) == ("matched", 0)
    assert [c[0] for c in side.calls] == ["before", "after", "rerun-before", "rerun-after"]
    assert side.calls[0][1] == side.calls[2][1] and side.calls[1][1] == side.calls[3][1]   # each side's own files
    data = validate(res)
    assert data["determinism"] == {"reruns": ["before", "after"], "identical": True, "differing": []}
    assert {"rerun_before_s", "rerun_after_s"} <= set(data["timings"])


def test_a_rerun_that_differs_is_inconclusive_naming_what_differed(tmp_path):
    lab, b, a = make_lab(tmp_path), None, None
    after = add_new_customer_block(base())
    flaky = after.copy()
    flaky.rib("edge1", "10.99.0.0/24", rib("kernel", hops=(), distance=0))
    b, a = side_dir(tmp_path, lab, "before"), side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    side = rerun_side(base().snap(), after.snap(), flaky.snap())
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, NEW_BLOCK)), side_fn=side)
    assert (res.status, res.exit_code) == ("inconclusive", 3)
    data = validate(res)
    assert data["inconclusive"]["side"] == "rerun" and any("10.99.0.0/24" in x for x in data["inconclusive"]["moving"])
    assert data["determinism"]["identical"] is False and data["determinism"]["differing"]
    assert "INCONCLUSIVE" in data["verdict"]


def test_no_behavior_change_is_also_confirmed_by_a_rerun(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), base().snap(), intent_text="intent: []\n")
    assert res.status == "no_change" and [c[0] for c in side.calls] == ["before", "after", "rerun-before", "rerun-after"]


def test_a_failed_verdict_needs_no_rerun(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap(), intent_text="intent: []\n")
    assert res.status == "failed" and [c[0] for c in side.calls] == ["before", "after"]
    assert validate(res)["determinism"] is None


def test_a_rerun_that_never_settles_is_inconclusive(tmp_path):
    lab = make_lab(tmp_path)
    b, a = side_dir(tmp_path, lab, "before"), side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    side = rerun_side(base().snap(), add_new_customer_block(base()).snap(),
                      Inconclusive("the snapshot kept changing", ["edge1: rib 10.9.9.0/24"]))
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, NEW_BLOCK)), side_fn=side)
    assert (res.status, res.exit_code) == ("inconclusive", 3) and validate(res)["inconclusive"]["side"] == "rerun"


# --- sides and the topology rule ---------------------------------------------------------------------------

def test_bind_anchor(tmp_path):
    lab = make_lab(tmp_path)
    topo = lab / "topology.clab.yml"
    assert vrun.bind_anchor(topo) == lab.resolve()                     # configs/ and shared/ next to it
    (lab / "topo").mkdir()
    (lab / "topo" / "t.clab.yml").write_text(TOPO.replace("configs/", "../configs/").replace("shared/", "../shared/"))
    assert vrun.bind_anchor(lab / "topo" / "t.clab.yml") == lab.resolve()
    agent = ROOT / "examples/agent-demo/topology.clab.yml"
    assert vrun.bind_anchor(agent) == agent.resolve().parent


def test_a_side_missing_a_bound_file_is_an_error(tmp_path):
    lab = make_lab(tmp_path)
    side = side_dir(tmp_path, lab, "before")
    (side / "configs" / "up1.conf").unlink()
    with pytest.raises(vrun.VerifyInputError, match="missing"):
        vrun.materialize(str(side), "before", lab / "topology.clab.yml", tmp_path / "w")


def test_a_side_that_is_neither_a_directory_nor_a_ref(tmp_path):
    lab = make_lab(tmp_path)
    git(lab, "init", "-q")
    with pytest.raises(vrun.VerifyInputError):
        vrun.materialize("no-such-ref", "before", lab / "topology.clab.yml", tmp_path / "w")


def git(cwd: Path, *args: str) -> str:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    p = subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "commit.gpgsign=false",
                        *args], cwd=cwd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


def repo_lab(tmp_path: Path) -> Path:
    lab = make_lab(tmp_path)
    (lab / "netdryrun.yml").write_text(GUARDS)
    git(lab, "init", "-q")
    git(lab, "add", ".")
    git(lab, "commit", "-q", "-m", "base")
    return lab


def test_git_ref_side(tmp_path):
    lab = repo_lab(tmp_path)
    (lab / "configs" / "edge1.conf").write_text("! edge1 after\n")
    side = vrun.materialize("HEAD", "before", lab / "topology.clab.yml", tmp_path / "w")
    topo = side.topology
    assert "git ref HEAD" in side.desc and (topo.parent / "configs" / "edge1.conf").read_text() == "! edge1.conf before\n"
    assert topo.read_bytes() == (lab / "topology.clab.yml").read_bytes()
    assert set(side.bound) == {"configs/daemons", "shared/vtysh.conf", "configs/cust1.conf", "configs/edge1.conf",
                               "configs/up1.conf", "configs/peer1.conf"} and side.bound == side.sources


def test_topology_changed_since_the_ref_is_exit_2(tmp_path):
    lab = repo_lab(tmp_path)
    (lab / "topology.clab.yml").write_text(TOPO + "    - endpoints: [\"edge1:eth2\", \"up1:eth1\"]\n")
    res = vrun.verify(str(lab / "topology.clab.yml"), "HEAD", str(lab / "configs"),
                      str(intent_file(tmp_path, "intent: []\n")), config_dir_name="configs",
                      side_fn=fake_side(base().snap(), base().snap()))
    assert (res.status, res.exit_code) == ("error", 2)
    validate(res)
    code = cli.main(["verify", str(lab / "topology.clab.yml"), "--before", "HEAD", "--after", str(lab / "configs"),
                     "--intent", str(tmp_path / "intent.yml"), "--config-dir", "configs"])
    assert code == 2


def test_guards_are_read_from_the_before_ref(tmp_path, monkeypatch):
    lab = repo_lab(tmp_path)
    # the change weakens the guards in the working tree: verify must ignore that
    (lab / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: bgp_session, node: edge1, neighbor: 10.0.1.2}\n")
    (lab / "configs" / "edge1.conf").write_text("! edge1 after\n")
    seen = {}

    def fake_guards(cfg, topology, settle, hold, log):
        seen["checks"] = len(cfg.checks)
        return {"status": "passed", "passed": len(cfg.checks), "failed": 0, "error": None, "failures": []}
    monkeypatch.setattr(vrun, "run_guards", fake_guards)

    def side(label, topology, on_up=None):
        extra = on_up(None, topology) if on_up else None
        return (base().snap(), 1.0, extra)
    res = vrun.verify(str(lab / "topology.clab.yml"), "HEAD", str(lab),
                      str(intent_file(tmp_path, "intent: []\n")), guards=str(lab / "netdryrun.yml"), side_fn=side)
    assert res.status == "no_change", res.error
    assert seen["checks"] == 2 and res.guards["source"] == "netdryrun.yml at HEAD"
    validate(res)


# --- nodes -------------------------------------------------------------------------------------------------

def test_node_classification(tmp_path):
    from netdryrun.lab import Lab
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}\n"
                    "    h1: {kind: linux, image: alpine:3}\n    br: {kind: bridge}\n"
                    "    s1: {kind: nokia_srlinux, image: ghcr.io/nokia/srlinux}\n")
    lab = Lab(topo)
    with pytest.raises(vrun.VerifyInputError):           # h1 can't be classified
        vrun.classify_nodes(lab, {}, [])
    with pytest.raises(vrun.VerifyInputError):           # s1 is SR Linux: FRR only in 0.4
        vrun.classify_nodes(lab, {}, ["h1"])
    assert vrun.classify_nodes(lab, {}, ["h1", "s1"]) == {"r1": "frr", "h1": "", "br": "", "s1": ""}
    assert vrun.classify_nodes(lab, {"h1": "frr"}, ["s1"])["h1"] == "frr"
    with pytest.raises(vrun.VerifyInputError):
        vrun.classify_nodes(lab, {}, ["h1", "s1", "zz"])


# --- CLI ---------------------------------------------------------------------------------------------------

def test_cli_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    out = tmp_path / "r.json"
    for status in ("matched", "no_change", "failed", "error", "inconclusive", "unhealthy_baseline"):
        res = vreport.VerifyResult(status=status, run_id="x")
        monkeypatch.setattr(vrun, "verify", lambda *a, _r=res, **k: _r)
        code = cli.main(["verify", "t.yml", "--before", "a", "--after", "b", "--intent", "i.yml", "--json", str(out)])
        assert code == vreport.EXIT_CODES[status]
        jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(out.read_text()))
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_cli_bad_intent_is_exit_2(tmp_path):
    lab = make_lab(tmp_path)
    code = cli.main(["verify", str(lab / "topology.clab.yml"), "--before", str(lab / "configs"), "--after",
                     str(lab / "configs"), "--intent", str(intent_file(tmp_path, "intent: {}\n"))])
    assert code == 2


def test_console_echoes_the_intent_first(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap())
    lines = vreport.console(res).splitlines()
    assert lines[0].startswith("verify: INTENT MATCHED") and lines[1].startswith("Intent (")


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["properties"]["schema"]["const"] == vreport.SCHEMA


# --- each side is a whole, isolated tree (review finding 1) ------------------------------------------------

NESTED_TOPO = """name: nlab
topology:
  defaults: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
  nodes:
    r1: {binds: ["../configs/r1.conf:/etc/frr/frr.conf"]}
    r2: {binds: ["../configs/r2.conf:/etc/frr/frr.conf"]}
"""


def bound_bytes(topology: Path) -> dict[str, bytes]:
    """What each bind of a materialized topology points at, read the way containerlab resolves it."""
    import os
    return {src: (topology.parent / os.path.expandvars(src)).read_bytes() for src in vrun.bind_sources(topology)}


def capture_side(snap):
    calls = {}

    def side(label, topology, on_up=None):
        calls[label] = bound_bytes(Path(topology))
        return snap, 1.0, None
    side.calls = calls
    return side


def nested_repo(tmp_path: Path) -> Path:
    lab = tmp_path / "lab"
    (lab / "topo").mkdir(parents=True)
    (lab / "configs").mkdir()
    (lab / "topo" / "t.clab.yml").write_text(NESTED_TOPO)
    for r in ("r1", "r2"):
        (lab / "configs" / f"{r}.conf").write_text(f"! {r} before\n")
    git(lab, "init", "-q")
    git(lab, "add", ".")
    git(lab, "commit", "-q", "-m", "before")
    (lab / "configs" / "r1.conf").write_text("! r1 after\n")
    git(lab, "commit", "-q", "-am", "after")
    return lab


def test_parent_relative_binds_keep_each_side_on_its_own_configs(tmp_path):
    lab = nested_repo(tmp_path)
    side = capture_side(base().snap())
    res = vrun.verify(str(lab / "topo" / "t.clab.yml"), "HEAD~1", "HEAD", str(intent_file(tmp_path, "intent: []\n")),
                      side_fn=side)
    assert res.error == "" or "both sides" not in res.error
    assert side.calls["before"]["../configs/r1.conf"] == b"! r1 before\n"
    assert side.calls["after"]["../configs/r1.conf"] == b"! r1 after\n"
    assert side.calls["before"]["../configs/r2.conf"] == side.calls["after"]["../configs/r2.conf"]


def test_parent_relative_binds_with_directory_sides(tmp_path):
    lab = nested_repo(tmp_path)
    b, a = tmp_path / "b", tmp_path / "a"
    for d, text in ((b, "! r1 before\n"), (a, "! r1 after\n")):
        shutil.copytree(lab / "configs", d / "configs")
        (d / "configs" / "r1.conf").write_text(text)
    side = capture_side(base().snap())
    vrun.verify(str(lab / "topo" / "t.clab.yml"), str(b), str(a), str(intent_file(tmp_path, "intent: []\n")),
                side_fn=side)
    assert side.calls["before"]["../configs/r1.conf"] == b"! r1 before\n"
    assert side.calls["after"]["../configs/r1.conf"] == b"! r1 after\n"


def test_narrow_config_dir_on_directory_sides_never_shares_a_file(tmp_path):
    """With --config-dir, a directory side is that folder only: a bind outside it would come from somewhere
    shared by both sides, so it is exit 2."""
    lab = make_lab(tmp_path)
    b, a = tmp_path / "before", tmp_path / "after"          # each the config folder only
    shutil.copytree(lab / "configs", b)
    shutil.copytree(lab / "configs", a)
    (a / "edge1.conf").write_text("! edge1 after\n")
    side = fake_side(base().snap(), base().snap())
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, "intent: []\n")),
                      config_dir_name="configs", side_fn=side)
    assert res.exit_code == 2 and "shared/vtysh.conf" in res.error and not side.calls


@pytest.mark.parametrize("bind", ["/etc/frr/r1.conf", "~/r1.conf", "${NDR_TEST_CFG}/r1.conf", "../../elsewhere/r1.conf",
                                  "link/r1.conf"])
def test_a_bind_outside_the_side_tree_is_exit_2(tmp_path, monkeypatch, bind):
    lab = nested_repo(tmp_path)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "r1.conf").write_text("! shared\n")
    monkeypatch.setenv("NDR_TEST_CFG", str(tmp_path / "elsewhere"))
    (lab / "topo" / "link").symlink_to(tmp_path / "elsewhere")
    topo = lab / "topo" / "t.clab.yml"
    topo.write_text(NESTED_TOPO.replace("../configs/r1.conf", bind))
    git(lab, "add", ".")
    git(lab, "commit", "-q", "-m", "bind outside")
    git(lab, "tag", "b")
    side = capture_side(base().snap())
    res = vrun.verify(str(topo), "b", "HEAD", str(intent_file(tmp_path, "intent: []\n")), side_fn=side)
    assert res.exit_code == 2 and "resolves outside" in res.error and not side.calls


def test_env_and_parent_binds_inside_the_tree_resolve_per_side(tmp_path, monkeypatch):
    lab = nested_repo(tmp_path)
    monkeypatch.setenv("NDR_TEST_DIR", "configs")
    topo = lab / "topo" / "t.clab.yml"
    topo.write_text(NESTED_TOPO.replace("../configs/r1.conf", "../${NDR_TEST_DIR}/r1.conf"))
    git(lab, "commit", "-q", "-am", "env bind")
    (lab / "configs" / "r1.conf").write_text("! r1 third\n")
    git(lab, "commit", "-q", "-am", "third")
    side = capture_side(base().snap())
    vrun.verify(str(topo), "HEAD~1", "HEAD", str(intent_file(tmp_path, "intent: []\n")), side_fn=side)
    assert side.calls["before"]["../${NDR_TEST_DIR}/r1.conf"] == b"! r1 after\n"   # captured as written
    assert side.calls["after"]["../${NDR_TEST_DIR}/r1.conf"] == b"! r1 third\n"


def test_self_check_both_sides_resolved_to_the_same_configs(tmp_path):
    def mk(label, bound, sources):
        return vrun.Side(label=label, topology=tmp_path / "t.clab.yml", desc=label, root=tmp_path, bound=bound,
                         sources=sources)
    logs = []
    same = {"configs/r1.conf": "aa", "configs/r2.conf": "bb"}
    with pytest.raises(vrun.VerifyInputError, match="both sides resolved to the same configs"):
        vrun.check_sides(mk("before", same, same), mk("after", same, {**same, "configs/r1.conf": "cc"}), logs.append)
    with pytest.raises(vrun.VerifyInputError, match="nothing to verify"):   # gauntlet 0.4, R3
        vrun.check_sides(mk("before", same, same), mk("after", same, same), logs.append)
    other = {**same, "configs/r1.conf": "cc"}
    vrun.check_sides(mk("before", same, same), mk("after", other, other), logs.append)
    assert "configs/r1.conf" in logs[-1] and "configs/r2.conf" not in logs[-1]


# --- binds outside the config folder come from each side too (review finding 2) -----------------------------

def test_binds_outside_the_config_folder_come_from_each_ref(tmp_path):
    lab = repo_lab(tmp_path)
    (lab / "shared" / "vtysh.conf").write_text("! vtysh after\n")
    git(lab, "commit", "-q", "-am", "after")
    (lab / "shared" / "vtysh.conf").write_text("! vtysh in the working tree\n")
    topo, work = lab / "topology.clab.yml", tmp_path / "work"
    bside = vrun.materialize("HEAD~1", "before", topo, work, "configs")
    aside = vrun.materialize("HEAD", "after", topo, work, "configs")
    assert bound_bytes(bside.topology)["shared/vtysh.conf"] == b"service integrated-vtysh-config\n"
    assert bound_bytes(aside.topology)["shared/vtysh.conf"] == b"! vtysh after\n"
    # and a changed vtysh.conf is not a router config: verify refuses it (gauntlet 0.4, R2)
    side = capture_side(base().snap())
    res = vrun.verify(str(topo), "HEAD~1", "HEAD", str(intent_file(tmp_path, "intent: []\n")),
                      config_dir_name="configs", side_fn=side)
    assert res.exit_code == 2 and "shared/vtysh.conf" in res.error and not side.calls


def test_a_bound_file_left_out_by_export_ignore_is_exit_2(tmp_path):
    lab = repo_lab(tmp_path)
    (lab / ".gitattributes").write_text("configs/edge1.conf export-ignore\n")
    git(lab, "add", ".gitattributes")
    git(lab, "commit", "-q", "-m", "export-ignore")
    side = capture_side(base().snap())
    res = vrun.verify(str(lab / "topology.clab.yml"), "HEAD", "HEAD", str(intent_file(tmp_path, "intent: []\n")),
                      side_fn=side)
    assert res.exit_code == 2 and "export-ignore" in res.error and "configs/edge1.conf" in res.error
    assert not side.calls


def test_the_report_lists_every_route_an_allow_entry_explained(tmp_path):
    after = base()
    after.learn("cust1", "10.200.5.0/24", "10.0.1.1", "65000 65002")
    after.learn("up1", "10.200.6.0/24", "10.0.2.1", "65000 65002")
    res, _ = run_verify(tmp_path, base().snap(), after.snap(),
                        intent_text="intent: []\nallow_anywhere: ['10.200.*.0/24']\n")
    assert res.status == "matched"
    (entry,) = validate(res)["allowed"]
    assert entry["routes"] == [{"node": "cust1", "vrf": "default", "prefix": "10.200.5.0/24"},
                               {"node": "up1", "vrf": "default", "prefix": "10.200.6.0/24"}]
    text = vreport.console(res)
    assert "cust1 10.200.5.0/24" in text and "up1 10.200.6.0/24" in text


# --- standing guards: from the before side, never optional in silence (review finding 4) --------------------

LEAK_INTENT = "intent:\n  - {prefix: 203.0.113.0/24, appears_on: [peer1]}\n"


def leaked_after():
    after = base()
    after.adj_out("edge1", "10.0.3.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    after.learn("peer1", "203.0.113.0/24", "10.0.3.1", "65000 65002")
    return after


def guards_on(after_snap):
    """A run_guards stand-in that evaluates `route ... present: false` checks on the after snapshot."""
    seen = {}

    def fake(cfg, topology, settle, hold, log):
        seen["checks"] = [c.params for c in cfg.checks]
        items = after_snap.items()
        failures = [{"check": c.name, "node": c.params["node"], "reason": "route present"} for c in cfg.checks
                    if c.type == "route" and c.params.get("present") is False
                    and any(k.kind == "rib" and k.node == c.params["node"] and k.prefix == c.params["prefix"]
                            for k in items)]
        return {"status": "failed" if failures else "passed", "passed": len(cfg.checks) - len(failures),
                "failed": len(failures), "error": None, "failures": failures}
    fake.seen = seen
    return fake


def guard_side(before_snap, after_snap):
    def side(label, topology, on_up=None):
        snap = before_snap if label in ("before", "rerun-before") else after_snap
        return snap, 1.0, (on_up(None, topology) if on_up and label == "after" else None)
    return side


def test_dishonest_intent_fails_through_guards_read_from_the_before_ref(tmp_path, monkeypatch):
    """No --guards: the netdryrun.yml of the before ref runs on the after lab, and its leak guard fails the
    intent that declares the leak, even though the change deleted that guard in the working tree."""
    lab = repo_lab(tmp_path)
    (lab / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: bgp_session, node: edge1, neighbor: 10.0.1.2}\n")
    (lab / "configs" / "edge1.conf").write_text("! edge1 leaks\n")
    after = leaked_after().snap()
    fake = guards_on(after)
    monkeypatch.setattr(vrun, "run_guards", fake)
    res = vrun.verify(str(lab / "topology.clab.yml"), "HEAD", str(lab), str(intent_file(tmp_path, LEAK_INTENT)),
                      side_fn=guard_side(base().snap(), after))
    assert (res.status, res.exit_code) == ("failed", 1) and res.failed_because == ["guards"], res.error
    assert len(fake.seen["checks"]) == 2 and res.guards_source == "before-ref"
    data = validate(res)
    assert data["guards_source"] == "before-ref" and data["guards"]["failed"] == 1


def test_no_guards_with_a_directory_before_on_the_dishonest_intent(tmp_path, monkeypatch):
    """A directory --before: guards come only from an explicit --guards (never a netdryrun.yml found in
    the side), and a verdict without guards says so, visibly."""
    lab = make_lab(tmp_path)
    (lab / "netdryrun.yml").write_text(GUARDS)
    b, a = side_dir(tmp_path, lab, "before"), side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    shutil.copy(lab / "netdryrun.yml", b / "netdryrun.yml")
    after = leaked_after().snap()
    fake = guards_on(after)
    monkeypatch.setattr(vrun, "run_guards", fake)
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, LEAK_INTENT)),
                      side_fn=guard_side(base().snap(), after))
    assert res.status == "matched" and res.guards is None and not fake.seen
    assert res.guards_source == "none" and vreport.NO_GUARDS_WARNING in res.warnings
    data = validate(res)
    assert data["guards_source"] == "none" and vreport.NO_GUARDS_WARNING in data["warnings"]
    first = vreport.console(res).splitlines()[0]
    assert first.startswith("verify: INTENT MATCHED") and "no standing guards ran" in first
    # an explicit --guards with a directory --before: read from that path, and said so
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, LEAK_INTENT)),
                      guards=str(lab / "netdryrun.yml"), side_fn=guard_side(base().snap(), after))
    assert res.status == "failed" and res.guards_source == "explicit" and validate(res)["guards_source"] == "explicit"


def test_a_vrf_diff_item_in_the_report(tmp_path):
    after = base().snap()
    after.nodes["edge1"].vrfs = ("cust", "default")
    res, _ = run_verify(tmp_path, base().snap(), after, intent_text="intent: []\n")
    (item,) = validate(res)["undeclared"]
    assert (item["kind"], item["vrf"], item["change"]) == ("vrf", "cust", "added")
    assert item["next_diagnostic"].endswith("'show vrf'") and "vrf cust" in item["summary"]


# --- validation before booting, and the report-write rule (review finding 10) --------------------------------

def test_a_session_line_without_afi_is_exit_2_before_anything_boots(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), base().snap(),
                           intent_text="intent:\n  - {session: {node: edge1, neighbor: 10.0.3.2}, goes: down}\n")
    assert res.exit_code == 2 and "afi" in res.error and not side.calls


@pytest.mark.parametrize("how", ["directory", "render"])
def test_cli_json_report_that_cannot_be_written_is_one_line_and_exit_2(tmp_path, monkeypatch, capsys, how):
    res = vreport.VerifyResult(status="matched", run_id="x")
    monkeypatch.setattr(vrun, "verify", lambda *a, **k: res)
    target = tmp_path / "r.json"
    if how == "directory":
        target.mkdir()
    else:
        def boom(_r):
            raise ValueError("Out of range float values are not JSON compliant")
        monkeypatch.setattr(vreport, "to_json", boom)
    code = cli.main(["verify", "t.yml", "--before", "a", "--after", "b", "--intent", "i.yml", "--json", str(target)])
    err = capsys.readouterr().err.strip().splitlines()
    assert code == 2 and len(err) == 1
    assert err[0].startswith(f"could not write {target}: ") and err[0].endswith("; the verdict was INTENT MATCHED")


# --- who supplied the intent, and an intent edited by the change ----------------------------------------------

def test_intent_source_is_reported(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap(), intent_text="intent: []\n", intent_source="mcp")
    assert res.intent_supplied_by == "mcp" and validate(res)["intent"]["supplied_by"] == "mcp"
    res, _ = run_verify(tmp_path / "default", base().snap(), base().snap(), intent_text="intent: []\n")
    assert res.intent_supplied_by == "cli"


def test_an_intent_edited_in_the_same_change_is_flagged(tmp_path):
    lab = repo_lab(tmp_path)
    (lab / "netdryrun-intent.yml").write_text("intent: []\n")
    git(lab, "add", "netdryrun-intent.yml")
    git(lab, "commit", "-q", "-m", "intent")
    (lab / "configs" / "edge1.conf").write_text("! edge1 second\n")
    git(lab, "commit", "-q", "-am", "a config change alone")
    side = capture_side(base().snap())
    res = vrun.verify(str(lab / "topology.clab.yml"), "HEAD~1", "HEAD", str(lab / "netdryrun-intent.yml"), side_fn=side)
    assert res.status == "no_change" and vreport.INTENT_EDITED_WARNING not in res.warnings, res.error
    (lab / "netdryrun-intent.yml").write_text("intent: []\nallow_anywhere: ['10.200.*.0/24']\n")
    (lab / "configs" / "edge1.conf").write_text("! edge1 third\n")
    git(lab, "commit", "-q", "-am", "widen")
    res = vrun.verify(str(lab / "topology.clab.yml"), "HEAD~1", "HEAD", str(lab / "netdryrun-intent.yml"), side_fn=side)
    assert vreport.INTENT_EDITED_WARNING in res.warnings
    assert "intent edited in the same change: needs a code-owner review" in vreport.console(res)
    validate(res)


def test_host_kinds_are_refused_unless_unobserved(tmp_path):
    from netdryrun.lab import Lab
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}\n"
                    "    x1: {kind: ext-container}\n    br: {kind: bridge}\n")
    lab = Lab(topo)
    with pytest.raises(vrun.VerifyInputError, match="x1"):
        vrun.classify_nodes(lab, {}, [])
    assert vrun.classify_nodes(lab, {}, ["x1"]) == {"r1": "frr", "x1": "", "br": ""}


@pytest.mark.parametrize("driver", ["srlinux", "eos", "sonic", "junos"])
def test_a_node_verify_cannot_snapshot_is_refused_and_named_with_the_way_out(tmp_path, monkeypatch, driver):
    """verify 0.4 snapshots FRR only. Any other platform (Junos included: its collector is 0.4.1) is refused
    before a lab boots, naming --unobserved and what it costs; it is never snapshotted by a guess."""
    from netdryrun.lab import Lab
    monkeypatch.setattr(vrun, "DRIVERS", {**vrun.DRIVERS, driver: object})
    monkeypatch.setattr(vrun, "detect", lambda node: driver if node.name == "x1" else "frr")
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}\n"
                    "    x1: {kind: linux, image: some/nos:1}\n")
    lab = Lab(topo)
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.classify_nodes(lab, {}, [])
    assert "x1" in str(e.value) and driver in str(e.value) and "--unobserved x1" in str(e.value)
    assert "not compared" in str(e.value)
    assert vrun.classify_nodes(lab, {}, ["x1"]) == {"r1": "frr", "x1": ""}
    assert vrun.unobserved_reasons(lab, {"r1": "frr", "x1": ""})["x1"].startswith(f"runs {driver}")


def test_an_unobserved_node_is_stated_in_every_output(tmp_path, monkeypatch):
    """A node run as --unobserved: the console, the Markdown and the JSON report all say that changes on it
    are not compared (never silently a smaller snapshot). (An FRR router can't be unobserved: gauntlet R8.)"""
    lab = make_lab(tmp_path, TOPO.replace("    peer1: {binds: [configs/peer1.conf:/etc/frr/frr.conf]}",
                                          "    peer1: {binds: [configs/peer1.conf:/etc/frr/frr.conf], image: alpine:3}"))
    b, a = side_dir(tmp_path, lab, "before"), side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    snap_b, snap_a = base().snap(), base().snap()
    side = fake_side(snap_b, snap_a)
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, "intent: []\n")),
                      side_fn=side, unobserved=["peer1"])
    assert res.status == "no_change", res.error
    line = next(w for w in res.warnings if "peer1" in w)
    assert "not compared" in line
    assert line in vreport.console(res) and "peer1" in vreport.markdown(res)
    assert any("peer1" in w for w in validate(res)["warnings"])


def test_a_peer_still_booting_at_the_timeout_never_approves(tmp_path):
    """A slow node (cJunosEvolved booted in 4 to 19 minutes in the Juniper session's runs) can still be booting
    when the snapshot settles: the FRR sessions to it are down. With the default timeout that is an unhealthy
    baseline (exit 3), a lab that never settles is INCONCLUSIVE (exit 3): never an approval."""
    booting = base()
    booting.session("edge1", "10.0.3.2", session(None, state="active", remote_as=65003))
    booting.session("peer1", "10.0.3.1", session(None, state="active"))
    res, _ = run_verify(tmp_path / "a", booting.snap(), booting.snap(), intent_text="intent: []\n")
    assert (res.status, res.exit_code) == ("unhealthy_baseline", 3)
    # booted by the after side: the sessions that came up are differences, not an approval
    res, _ = run_verify(tmp_path / "b", booting.snap(), base().snap(), intent_text="intent: []\n",
                        allow_unhealthy_baseline=True)
    assert res.status == "failed" and res.exit_code == 1
    # still moving at the timeout
    stuck = Inconclusive("the lab's state kept moving within 300s", ["edge1 session 10.0.3.2 changed"])
    res, _ = run_verify(tmp_path / "c", base().snap(), stuck, intent_text="intent: []\n")
    assert (res.status, res.exit_code) == ("inconclusive", 3)


# --- cold review of 0.4 (layer 6, 2026-10-28) ------------------------------------------------------------------

def test_cold_1_a_directory_named_like_a_ref_is_ambiguous_and_refused(tmp_path, monkeypatch):
    """A PR adds a folder named exactly like the base commit's hash, holding its own configs: in the Action
    (which passes hashes, in the PR's checkout) that folder became the before side, the base's guards were
    dropped and the change compared against itself: NO BEHAVIOR CHANGE. A side that is both a directory and a
    git ref is exit 2."""
    lab = repo_lab(tmp_path)
    base_sha = git(lab, "rev-parse", "HEAD").strip()
    (lab / "configs" / "edge1.conf").write_text("! edge1 after: the leak\n")
    for sub in ("configs", "shared"):
        shutil.copytree(lab / sub, lab / base_sha / sub)
    git(lab, "add", ".")
    git(lab, "commit", "-q", "-m", "pr")
    head_sha = git(lab, "rev-parse", "HEAD").strip()
    monkeypatch.chdir(lab)
    side = fake_side(base().snap(), base().snap())
    res = vrun.verify(str(lab / "topology.clab.yml"), base_sha, head_sha, str(intent_file(tmp_path, "intent: []\n")),
                      side_fn=side, intent_source="action")
    assert (res.status, res.exit_code) == ("error", 2) and not side.calls
    assert "both a directory and a git ref" in res.error


def test_cold_5_an_approval_reruns_the_before_side_too(tmp_path):
    """A before boot that is stably missing an item (a race in the lab) hides a change that removes it:
    an approval needs each side twice, identical."""
    lab = make_lab(tmp_path)
    b, a = side_dir(tmp_path, lab, "before"), side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    flaky_before = base()
    flaky_before.drop("cust1", "path", "198.18.0.0/24")
    flaky_before.drop("cust1", "rib", "198.18.0.0/24")
    snaps = {"before": flaky_before.snap(), "after": flaky_before.snap(), "rerun-before": base().snap(),
             "rerun-after": flaky_before.snap()}
    calls = []

    def side(label, topology, on_up=None):
        calls.append(label)
        return snaps[label], 1.0, None
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, "intent: []\n")),
                      side_fn=side)
    assert calls == ["before", "after", "rerun-before"]          # the before rerun differed: no need for more
    assert (res.status, res.exit_code) == ("inconclusive", 3)
    data = validate(res)
    assert data["determinism"]["identical"] is False and any("cust1" in x for x in data["determinism"]["differing"])
