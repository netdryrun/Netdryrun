"""GATE.md verdicts: accepted MAJOR checks, and the state between the pre-publish layers and the proof."""
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate"] = gate
spec.loader.exec_module(gate)


def record(name, checks):
    return {"title": gate.LAYERS[name], "git": {"sha": "a", "branch": "b", "dirty": False}, "started": "now",
            "seconds": 1, "host": "h", "python": "3", "tools": {}, "sections": [],
            "checks": [{"id": i, "title": i, "severity": sev, "status": st, "summary": "", "output": "",
                        "seconds": 0, "command": ""} for i, sev, st in checks]}


NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)
FRESH = {"date": "2026-11-03T08:00+00:00", "run": "r", "false_pass": False, "green": True, "readme": "success",
         "netdryrun": "netdryrun 9.9.9",
         "results": [{"step": "own topology", "want": 0, "got": 0, "ok": True},
                     {"step": "own topology, fail-bogon", "want": 1, "got": 1, "ok": True},
                     {"step": "own topology, pass-description", "want": 0, "got": 0, "ok": True}],
         "unseen": {"netdryrun": "netdryrun 9.9.9", "false_pass": False}}


def write(tmp_path, layers, accepted=None, review=True, stranger=FRESH):
    status = None
    if stranger is not None:
        status = tmp_path / "STATUS.json"
        status.write_text(stranger if isinstance(stranger, str) else json.dumps(stranger))
    for name, checks in layers.items():
        (tmp_path / "gate").mkdir(exist_ok=True)
        (tmp_path / "gate" / f"{name}.json").write_text(json.dumps(record(name, checks)))
    if accepted is not None:
        (tmp_path / "accepted.json").write_text(json.dumps({"checks": accepted}))
    if review:
        (tmp_path / "review.md").write_text("review")
    return SimpleNamespace(out=str(tmp_path), version="9.9.9", stranger_status=status and str(status))


_render = gate.render


def render(args):
    return _render(args, now=NOW)


gate = SimpleNamespace(**{k: getattr(gate, k) for k in dir(gate) if not k.startswith("__")})
gate.render = render


PRE = {"static": [("s", "BLOCKER", "PASS")], "unit": [("u", "BLOCKER", "PASS")], "mutation": [("m", "BLOCKER", "PASS")],
       "acceptance": [("a", "BLOCKER", "PASS")]}


def test_a_skipped_major_can_be_accepted(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("pack", "MAJOR", "SKIP")], "after-publish": [("p", "BLOCKER", "PASS")]},
                 accepted={"live/pack": "not sold yet"})
    text, cleared = gate.render(args)
    assert cleared, text
    assert "not sold yet" in text


def test_a_skipped_major_without_acceptance_blocks(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("pack", "MAJOR", "SKIP")], "after-publish": [("p", "BLOCKER", "PASS")]})
    text, cleared = gate.render(args)
    assert not cleared
    assert "live/pack" in text


def test_a_skipped_blocker_cannot_be_accepted(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("x", "BLOCKER", "SKIP")], "after-publish": [("p", "BLOCKER", "PASS")]},
                 accepted={"live/x": "please"})
    text, cleared = gate.render(args)
    assert not cleared
    assert "BLOCKER checks skipped" in text


@pytest.mark.parametrize("check", ["corpus-v2-nondeterministic-held", "corpus-v2-nondeterministic-caught", "x"])
def test_a_failed_blocker_cannot_be_accepted(tmp_path, check):
    """accepted.json can't turn a failed BLOCKER into ACCEPTED, whatever its id: only the gate itself sets a check's
    severity."""
    args = write(tmp_path, {**PRE, "live": [(check, "BLOCKER", "FAIL")], "after-publish": [("p", "BLOCKER", "PASS")]},
                 accepted={f"live/{check}": "please"})
    text, cleared = gate.render(args)
    assert not cleared and f"live/{check}" in text.split("**BLOCKER failures:**")[1]
    assert "(accepted: please)" not in text


def test_ready_to_publish_when_only_the_proof_is_missing(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("l", "BLOCKER", "PASS")]})
    text, cleared = gate.render(args)
    assert not cleared
    assert "**READY TO PUBLISH**" in text


def test_not_ready_without_the_review(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("l", "BLOCKER", "PASS")]}, review=False)
    text, _ = gate.render(args)
    assert "**INCOMPLETE**" in text


def test_not_ready_when_a_pre_publish_layer_is_missing(tmp_path):
    args = write(tmp_path, PRE)
    text, _ = gate.render(args)
    assert "**INCOMPLETE**" in text


# --- the synthetic stranger (0.4.1): 0.3.3 and 0.4.0 shipped while it reported a false pass ---------------------

ALL = {**PRE, "live": [("l", "BLOCKER", "PASS")], "after-publish": [("p", "BLOCKER", "PASS")]}


def test_cleared_with_a_fresh_stranger_status(tmp_path):
    text, cleared = gate.render(write(tmp_path, ALL))
    assert cleared, text


@pytest.mark.parametrize("stranger,why", [
    (None, "no stranger status"),
    ("{not json", "can't be read"),
    ("[]", "not a JSON object"),
    ({**FRESH, "false_pass": True}, "false pass"),
    ({k: v for k, v in FRESH.items() if k != "false_pass"}, "false pass"),
    ({**FRESH, "unseen": {"false_pass": True}}, "unseen labs report a false pass"),
    ({**FRESH, "date": "2026-11-01T23:59+00:00"}, "more than 36 hours"),
    ({**FRESH, "date": "2026-11-05T00:00+00:00"}, "more than 36 hours"),
    ({**FRESH, "date": "2026-11-03T08:00"}, "no readable date"),
    ({k: v for k, v in FRESH.items() if k != "date"}, "no readable date"),
    ({**FRESH, "netdryrun": "netdryrun 9.9.8"}, "tested netdryrun 9.9.8, not 9.9.9"),
    ({**FRESH, "unseen": {"netdryrun": "netdryrun 9.9.8", "false_pass": False}}, "tested netdryrun 9.9.8"),
    ({**FRESH, "netdryrun": None}, "doesn't say which netdryrun"),
    ({k: v for k, v in FRESH.items() if k != "netdryrun"}, "doesn't say which netdryrun"),
    ({**FRESH, "green": False, "readme": "failure"}, "not green"),
    ({k: v for k, v in FRESH.items() if k != "green"}, "not green"),
    # record failed, so no must-fail change ran: false_pass false, and it says nothing (cold review 2026-11-01)
    ({**FRESH, "results": [{"step": "own topology", "want": 0, "got": 2, "ok": False}]}, "no must-fail change"),
    ({**FRESH, "results": [{"step": "own machine", "want": 1, "got": 1, "ok": True}]}, "no must-fail change"),
    ({**FRESH, "results": "x"}, "no must-fail change"),
])
def test_the_stranger_keeps_the_release_from_clearing(tmp_path, stranger, why):
    text, cleared = gate.render(write(tmp_path, ALL, stranger=stranger))
    assert not cleared and "**NOT CLEARED**" in text and why in text, text
    # not READY TO PUBLISH either
    text, _ = gate.render(write(tmp_path, {**PRE, "live": [("l", "BLOCKER", "PASS")]}, stranger=stranger))
    assert "**READY TO PUBLISH**" not in text


def test_a_status_just_inside_36_hours_is_fresh():
    ok = {**FRESH, "date": "2026-11-02T00:00+00:00"}
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        p.write_text(json.dumps(ok))
        assert _gate_problems(str(p), NOW) == []
        p.write_text(json.dumps({**ok, "date": "2026-11-01T23:59+00:00"}))
        assert _gate_problems(str(p), NOW)


def _gate_problems(path, now):
    return sys.modules["release_gate"].stranger_problems(path, "9.9.9", now)
