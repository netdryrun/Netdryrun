"""scripts/acceptance.py (Layer 5b) without a lab: the matrix still matches the examples it edits, every driver and
example is covered, and the release gate's acceptance layer fails closed."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from netdryrun.drivers import DRIVERS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("acceptance", ROOT / "scripts" / "acceptance.py")
acc = importlib.util.module_from_spec(spec)
sys.modules["acceptance"] = acc
spec.loader.exec_module(acc)
gate = sys.modules["release_gate"]
MATRIX = yaml.safe_load((ROOT / "releases" / "acceptance-matrix.yml").read_text(encoding="utf-8"))


def test_every_driver_and_every_example_is_in_the_matrix():
    assert set(MATRIX["drivers"]) == set(DRIVERS), "a driver without acceptance coverage (or a stale one)"
    listed = {ex for d in MATRIX["drivers"].values() for ex in d["examples"]}
    assert listed == set(gate.example_dirs()), "an example no driver runs (or one that no longer exists)"
    for name, d in MATRIX["drivers"].items():
        assert d["claimed"] is True and d.get("mustfail"), name


@pytest.mark.parametrize("drv", sorted(MATRIX["drivers"]))
def test_the_ported_must_fail_change_still_applies(drv, tmp_path):
    """The matrix edits the examples by exact text: an example that changed must fail here, not in the lab."""
    mf = MATRIX["drivers"][drv]["mustfail"]
    ex = tmp_path / "ex"
    shutil.copytree(ROOT / "examples" / mf["example"], ex)
    if drv == "frr":
        acc.apply(ex / "topology.clab.yml", [mf["good_bind"]])
        assert "configs/edge.conf" in (ex / "topology.clab.yml").read_text()
        return
    acc.apply(ex / MATRIX["customer"]["file"], MATRIX["customer"]["replace"])
    if mf.get("file"):
        acc.apply(ex / mf["file"], mf["filter"])
        before = (ex / mf["file"]).read_text()
        acc.apply(ex / mf["file"], mf["drop_match"])
        assert (ex / mf["file"]).read_text() != before
    else:
        nodes = yaml.safe_load((ex / "netdryrun.yml").read_text())["nodes"]
        assert mf["node"] in nodes and mf["drop_match_setup"][0] in mf["setup_last"]


def test_traps_are_filled_in():
    ctx = SimpleNamespace(matrix=MATRIX)
    traps = acc.traps_for(ctx, "r1", "10.0.0.2", "192.168.20.0/24")
    names = [t["name"] for t in traps]
    assert len(set(names)) == len(names) and all(n[:2] in ("T-", "S-") for n in names)
    by = {t["name"]: t for t in traps}
    assert by["T-longest-sub"]["prefix"] == "192.168.20.128/25" and by["T-longest-super"]["prefix"] == "192.168.0.0/16"
    assert not any("{" in str(v) for t in traps for v in t.values())


def test_big30_and_brownfield_generators(tmp_path):
    acc.make_big30(tmp_path / "b30", MATRIX["integrator"]["big30"], ROOT)
    topo = yaml.safe_load((tmp_path / "b30" / "good" / "topology.clab.yml").read_text())["topology"]
    assert len(topo["nodes"]) == 30 and len(topo["links"]) == 56
    kinds = {n.get("kind") for n in topo["nodes"].values()}
    assert {"linux", "nokia_srlinux", "arista_ceos", "sonic-vs"} <= kinds
    acc.make_brownfield(tmp_path / "bf", MATRIX["integrator"]["brownfield"], ROOT)
    assert (tmp_path / "bf" / "leak" / "configs" / "edge.conf").read_text() != \
        (tmp_path / "bf" / "good" / "configs" / "edge.conf").read_text()


def _layer(tmp_path, monkeypatch, items, sha="abc", only=None, adversary=None):
    out = tmp_path / "rel"
    out.mkdir(parents=True)
    (out / "acceptance.json").write_text(json.dumps({"sha": sha, "version": "9.9.9", "items": items}))
    if adversary:
        (out / "acceptance-adversary.md").write_text(adversary)
    monkeypatch.setattr(gate, "run", lambda *a, **k: gate.Proc(0, "", 1.0))
    monkeypatch.setattr(gate, "git", lambda *a: "abc\n")
    args = SimpleNamespace(version="9.9.9", out=str(out), strict=True, acceptance_only=only, acceptance_timeout=1)
    return {c.id: c.status for c in gate.layer_acceptance(args).checks}


def _item(id_, status):
    return {"id": id_, "title": id_, "status": status, "note": "", "got": "", "evidence": "", "seconds": 1}


def test_the_gate_layer_fails_closed(tmp_path, monkeypatch):
    ok = "Commit abc\n\nResult: no open false pass\n"
    st = _layer(tmp_path / "a", monkeypatch, [_item("x", "pass"), _item("y", "fail"), _item("z", "not covered")], adversary=ok)
    assert st == {"x": "PASS", "y": "FAIL", "z": "FAIL", "adversary": "PASS"}   # not covered: a FAIL under --strict
    assert _layer(tmp_path / "b", monkeypatch, [_item("x", "pass")], sha="old") == {"acceptance-ran": "FAIL"}
    assert _layer(tmp_path / "c", monkeypatch, [_item("x", "pass")], only="angle1/*", adversary=ok)["acceptance-complete"] == "FAIL"
    assert _layer(tmp_path / "d", monkeypatch, [_item("x", "pass")])["adversary"] == "FAIL"          # not recorded
    bad = "Commit abc\n\nResult: open false pass\n"
    assert _layer(tmp_path / "e", monkeypatch, [_item("x", "pass")], adversary=bad)["adversary"] == "FAIL"
    stale = "Commit 0ld\n\nResult: no open false pass\n"
    assert _layer(tmp_path / "f", monkeypatch, [_item("x", "pass")], adversary=stale)["adversary"] == "FAIL"


def test_the_release_is_not_ready_without_the_acceptance_layer():
    assert list(gate.LAYERS).index("acceptance") == list(gate.LAYERS).index("live") + 1
