"""Guards for oracle FP-042-FRRVRFPARSE: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-FRRVRFPARSE/ to fail on the fix's parent, so the guards
live here. This file is in the oracle's `evidence:`, so the fix can't change it.

What must keep working, on FRR and on SONiC (which inherits the FRR VRF list):
- the live capture tests/fixtures/verify/show_vrf.txt (FRR 10.4.1, `vtysh -c 'show vrf'`) lists VRF cust, from the
  `show vrf` command, with the call kept as evidence;
- an empty answer is no VRFs: zebra prints nothing for `show vrf` on a node without VRFs (it skips the default VRF), and
  raising there would make every FRR baseline without VRFs exit 1;
- an inactive VRF is not listed, `default` is never listed, and the "netns-based vrfs" header zebra prints with the
  netns backend is not an error;
- a vtysh failure (rc != 0) still raises.
"""
from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.lab import ExecResult

LIVE = (Path(__file__).parent / "fixtures" / "verify" / "show_vrf.txt").read_text(encoding="utf-8")
LIVE_SHOW_VRF = LIVE.split("\n", 1)[1]   # the first line is the capture's comment


class AnswerLab:
    def __init__(self, text, rc=0):
        self.text, self.rc, self.cmds = text, rc, []

    def exec(self, node, cmd, timeout=60, input=None):
        self.cmds.append(cmd)
        return ExecResult(cmd, self.rc, self.text, "")


DRIVERS = [FrrDriver, SonicDriver]


@pytest.mark.parametrize("cls", DRIVERS)
def test_the_live_show_vrf_capture_lists_cust(cls):
    assert LIVE.startswith("# live capture: FRRouting 10.4.1")
    lab = AnswerLab(LIVE_SHOW_VRF)
    obs = cls(lab, "edge1").vrfs()
    assert obs.value == ["cust"]
    assert ["vtysh", "-c", "show vrf"] in lab.cmds
    assert any(e["cmd"] == "vtysh -c show vrf" and e["output"] == LIVE_SHOW_VRF for e in obs.evidence)


@pytest.mark.parametrize("cls", DRIVERS)
@pytest.mark.parametrize("text", ["", "\n"])
def test_an_empty_answer_is_no_vrfs(cls, text):
    assert cls(AnswerLab(text), "r1").vrfs().value == []


@pytest.mark.parametrize("cls", DRIVERS)
def test_inactive_default_and_netns_header(cls):
    text = "netns-based vrfs\nvrf default id 0 table 254\nvrf red id 5 table 1001 (configured)\nvrf blue inactive\n"
    assert cls(AnswerLab(text), "r1").vrfs().value == ["red"]
    assert cls(AnswerLab("vrf blue inactive (configured)\n"), "r1").vrfs().value == []
    assert cls(AnswerLab(LIVE_SHOW_VRF + "vrf red id 5 table 1002\n"), "r1").vrfs().value == ["cust", "red"]


@pytest.mark.parametrize("cls", DRIVERS)
def test_a_failed_vtysh_still_raises(cls):
    with pytest.raises(DriverError, match=r"rc=1"):
        cls(AnswerLab("Exiting: failed to connect to any daemons.\n", rc=1), "r1").vrfs()
