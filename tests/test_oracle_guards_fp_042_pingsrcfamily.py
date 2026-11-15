"""Guards for oracle FP-042-PINGSRCFAMILY: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-PINGSRCFAMILY/ and needs every test there to fail on the fix's parent, so
the guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.
Helpers and the derived device output come from the oracle's own module.

What a fix must keep, on FRR (busybox), SONiC and SR Linux (iputils):
- a ping whose `source` is of the target's family still loads and passes on 3/3 replies bound to that source, for an
  IPv4 source with an IPv4 target and an IPv6 source with an IPv6 target;
- the live SR Linux capture as it is (tests/fixtures/srl_ping.txt, from 192.168.10.1, lo0's live address) still
  passes with `source: 192.168.10.1`;
- a ping without `source` still loads and passes, to an IPv4 and to an IPv6 target;
- a same-family source with 0 replies still fails.
"""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-PINGSRCFAMILY" / "test_oracle_fp_042_pingsrcfamily.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_pingsrcfamily", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

SAME = {"v4-source-v4-target": ("v4", o.V4_TARGET), "v6-source-v6-target": ("v6", o.V6_TARGET)}
TARGETS = {"v4-target": o.V4_TARGET, "v6-target": o.V6_TARGET}


@pytest.mark.parametrize("direction", sorted(SAME))
@pytest.mark.parametrize("kind", o.KINDS)
def test_same_family_source_loads_and_passes(tmp_path, kind, direction):
    fam, target = SAME[direction]
    source = o.SCENARIOS[kind][fam]
    assert f"from {source}" in o.ping_answer(kind, source, target).splitlines()[0]
    r, refused = o.judge(tmp_path, kind, source, target)
    assert refused is None, refused
    assert r.passed, r.detail
    assert "3/3 replies" in r.detail


def test_srl_live_capture_with_its_own_source_passes(tmp_path):
    """srl_ping.txt as captured: 192.168.20.1 from 192.168.10.1, lo0's address in the live srl_local_ipv4.json."""
    class Live(o.DerivedLab):
        def __init__(self):
            self.answers = dict(o.SCENARIOS["srlinux"]["addrs"])
            self.answers[o.ping_argv("srlinux", "192.168.10.1", "192.168.20.1")] = o.fx("srl_ping.txt")

    cfg = o.load(tmp_path, "srlinux", {"type": "ping", "node": o.NODE, "source": "192.168.10.1",
                                       "target": "192.168.20.1"})
    [c] = cfg.checks
    clock = o.Clock()
    r = o.run_check(c, o.SrlDriver(Live(), o.NODE), clock=clock, sleep=clock.sleep)
    assert r.passed, r.detail


@pytest.mark.parametrize("target", sorted(TARGETS))
@pytest.mark.parametrize("kind", o.KINDS)
def test_ping_without_source_unchanged(tmp_path, kind, target):
    r, refused = o.judge(tmp_path, kind, None, TARGETS[target])
    assert refused is None, refused
    assert r.passed, r.detail
    assert "3/3 replies" in r.detail


@pytest.mark.parametrize("kind", o.KINDS)
def test_same_family_source_without_replies_fails(tmp_path, kind):
    source, target = o.SCENARIOS[kind]["v4"], o.V4_TARGET
    lost = o.ping_answer(kind, source, target)
    lost = "\n".join(ln for ln in lost.splitlines() if not ln.startswith("64 bytes"))
    lost = lost.replace("3 packets received", "0 packets received").replace("3 received", "0 received")

    class NoReplies(o.DerivedLab):
        def __init__(self):
            super().__init__(kind, source, target)
            self.answers[o.ping_argv(kind, source, target)] = lost

    cfg = o.load(tmp_path, kind, {"type": "ping", "node": o.NODE, "source": source, "target": target})
    [c] = cfg.checks
    clock = o.Clock()
    r = o.run_check(c, o.SCENARIOS[kind]["driver"](NoReplies(), o.NODE), clock=clock, sleep=clock.sleep)
    assert not r.passed, r.detail
