"""Oracle FP-042-RTS01 (red team RT-S01): `record --attributes` on SR Linux drops the AS path of a route its iBGP peer originates, silently.

What the lab showed (tests/fixtures/srl_rt_s01_capture.txt):
- **Lab:** SR Linux 26.7.2 (srl1) and FRR 10.4.1 (frr1), both in AS 65010, iBGP over 10.0.100.0/30. frr1 originates
  192.168.20.0/24.
- **Phase empty:** srl1's local-RIB best path comes from 10.0.100.2, `neighbor-as` 65010, with attr-set 5. Its attr-set
  has no `as-path` container at all, and SR Linux's own text report prints `Path : i`, the empty AS path.
- **Phase prepended:** frr1 prepends 64666 towards srl1. The best path's attr-set 7 has `as-path` with segment
  [64666], and the report prints `i [64666]`.
- **Phase empty_again:** the prepend is removed. Attr-set 8 has no `as-path` again.
- **netdryrun 0.4.1 `record --attributes`** on the running lab (tests/fixtures/srl_rt_s01_record_041.yml) wrote srl1's
  `bgp_route` for 192.168.20.0/24 with `local_pref: 100` and no `as_path`. No warning names it: its only gap is a
  link-subnet line about another thing.

The rule (spec fastfix/oracle-specs/RT-S01.md): recording that route is never silent. The recorded check pins the
empty AS path (`as_path: ""`, the path SR Linux printed). Otherwise `record` gets an INCOMPLETE BASELINE line that names
the route and its AS path. Either way, nothing recorded may pass once the path has become 64666.

The spec's third test, a local preference the driver can't read, has no ground in this capture: every captured
attr-set prints `local-pref` 100. The guards in tests/test_oracle_guards_fp_042_rts01.py pin that it is recorded as 100.

Everything goes through the real SrlDriver, `record._attribute_check` and `checks.run_check`, fed srl1's captured
answers. A command that wasn't captured answers rc 1.

The tests here fail on the parent. The guards, which pass before and after the fix, are in
tests/test_oracle_guards_fp_042_rts01.py (listed in ORACLE.yml `evidence:`).
"""
import re
from pathlib import Path

from netdryrun import record as rec
from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
PREFIX = "192.168.20.0/24"
RIB = (f"info from state /network-instance default bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route {PREFIX} "
       "neighbor * origin-protocol * path-id *")
ATTR_ID = {"empty": "5", "prepended": "7", "empty_again": "8"}
AS_PATH = re.compile(r"as[ _-]?path", re.IGNORECASE)


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


class CapturedLab:
    """srl1 at one phase of the capture: its two answers, as `sr_cli --output-format json '<command>'` printed them."""

    def __init__(self, phase: str):
        self.answers = {RIB: fx(f"srl_rt_s01_{phase}_bgp_rib.txt"),
                        f"info from state /network-instance default bgp-rib attr-sets attr-set {ATTR_ID[phase]}":
                            fx(f"srl_rt_s01_{phase}_attr_set.txt")}

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "srl1" and cmd[:3] == ["sr_cli", "--output-format", "json"] and len(cmd) == 4 \
                and cmd[3] in self.answers:
            return ExecResult(cmd, 0, self.answers[cmd[3]], "")
        return ExecResult(cmd, 1, "", f"not captured: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def recorded(phase: str = "empty"):
    """`record --attributes`'s check for the route at `phase`, and the warnings recording it gave."""
    warnings: list = []
    check = rec._attribute_check(SrlDriver(CapturedLab(phase), "srl1"), "srl1", PREFIX, "default", warnings)
    return check, warnings


def run_on(check: dict, phase: str):
    c = Clock()
    return run_check(_validate_check(0, dict(check), 20), SrlDriver(CapturedLab(phase), "srl1"), clock=c,
                     sleep=c.sleep)


def named_gap(warnings: list) -> list:
    """INCOMPLETE BASELINE lines (record exits 1 on them) that name the route and its AS path."""
    return [w for w in rec.baseline_gaps(warnings) if PREFIX in w and AS_PATH.search(w)]


# ------------------------------------------------------------------ red on 0.4.1

def test_recording_the_empty_as_path_is_never_silent():
    check, warnings = recorded("empty")
    pinned = check is not None and check.get("as_path") == ""
    assert pinned or named_gap(warnings), f"recorded {check} with warnings {warnings}"


def test_nothing_recorded_passes_once_the_path_is_64666():
    check, warnings = recorded("empty")
    if check is None:                      # no check at all: then the gap must be named (test above), nothing passes
        assert named_gap(warnings), warnings
        return
    r = run_on(check, "prepended")
    assert not r.passed, f"the check recorded on the empty path passed on AS path 64666: {check} -> {r.detail}"
