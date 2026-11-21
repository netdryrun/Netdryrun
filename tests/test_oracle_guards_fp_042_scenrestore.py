"""Guards for oracle FP-042-SCENRESTORE: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-SCENRESTORE/ to fail on the fix's parent, so the guards live
here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake-kernel lab, the driver and the
scenario come from the oracle's own module.

What must keep working: a link that was up before the scenario is taken down while the fault lasts and is up again
after restore, for `node_isolated` and for `link_down`, also on the node whose other link is shut.
"""
import importlib.util
from pathlib import Path

from netdryrun.config import Fault

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-SCENRESTORE" / "test_oracle_fp_042_scenrestore.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_scenrestore", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def downs(lab, node, iface):
    return [c for c in lab.commands if c == (node, f"ip link set dev {iface} down")]


def test_node_isolated_brings_back_the_links_that_were_up(monkeypatch, tmp_path):
    for shut in ((("r1", "eth2"),), ()):
        lab = o.make_lab(tmp_path, shut)
        results = o.run(monkeypatch, lab, o.scenario(Fault("node_isolated", "r1")))
        assert [r.passed for r in results] == [True]
        assert downs(lab, "r1", "eth1"), "the fault never took r1 eth1 down"
        assert lab.admin_up("r1", "eth1"), "restore left r1 eth1 down, though it was up before the scenario"
        # the other routers' links are untouched; with nothing shut, r1 eth2 comes back up too
        assert all(lab.admin_up(n, i) for n, i in o.ADDRESSES if n != "r1" or (not shut and i == "eth2"))


def test_link_down_brings_back_the_link_it_took_down(monkeypatch, tmp_path):
    lab = o.make_lab(tmp_path)
    o.run(monkeypatch, lab, o.scenario(Fault("link_down", "r1", "eth1")))
    assert downs(lab, "r1", "eth1") and lab.admin_up("r1", "eth1")
