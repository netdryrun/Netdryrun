"""The shared fake-lab refusal (tests/fakes.py) and the rule that every fake lab uses it.

The release tooling recognises a new device read by the message "unexpected command: ..." on a fixture that no
longer holds. A fake that words its refusal differently turns a new read into an ordinary verdict change (still
blocked, but without asking for a live run on that network OS), so one wording is enforced here."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from unittest import mock

import pytest

from fakes import COMMAND_LOG, PREFIX, UnexpectedCommand, _plain, command_profiler, logging_commands, seen

TESTS = Path(__file__).resolve().parent
# a hand-made refusal in any spelling: AssertionError("unexpected command..."), f-strings, %-format, .format
OWN_REFUSAL = re.compile(r"""AssertionError\(\s*[fFrRbB]*["']unexpected command""")


def test_refusal_message_begins_with_the_shared_prefix():
    e = UnexpectedCommand("show bgp summary")
    assert isinstance(e, AssertionError)
    assert str(e) == "unexpected command: show bgp summary" and str(e).startswith(PREFIX)
    with pytest.raises(AssertionError, match=r"^unexpected command: show ip route$"):
        raise UnexpectedCommand("show ip route")


def test_no_test_raises_its_own_unexpected_command():
    """Oracle folders are frozen evidence written by oracle sessions; they are left as written."""
    own = []
    for p in sorted(TESTS.rglob("*.py")):
        rel = p.relative_to(TESTS).as_posix()
        if rel in ("fakes.py", "test_fakes.py") or rel.startswith("oracles/"):
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if OWN_REFUSAL.search(line):
                own.append(f"tests/{rel}:{n}: {line.strip()}")
    assert not own, "raise fakes.UnexpectedCommand(command) instead:\n" + "\n".join(own)


@pytest.mark.parametrize("line,hit", [
    ('raise AssertionError(f"unexpected command: {line}")', True),
    ('raise AssertionError(f"unexpected command {cmd!r}")', True),
    ("raise AssertionError('unexpected command %s' % c)", True),
    ('raise AssertionError( "unexpected command")', True),
    ("raise UnexpectedCommand(line)", False),
    ('raise AssertionError(f"unexpected output: {line}")', False),
])
def test_the_scan_sees_every_spelling(line, hit):
    assert bool(OWN_REFUSAL.search(line)) is hit


def test_seen_writes_nothing_unless_the_gate_asks(tmp_path, monkeypatch):
    log = tmp_path / "commands.jsonl"
    monkeypatch.delenv(COMMAND_LOG, raising=False)
    seen("show version")
    assert not log.exists()
    monkeypatch.setenv(COMMAND_LOG, str(log))
    seen("show bgp summary")
    seen(["vtysh", "-c", "show ip route"])
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [r["command"] for r in rows] == ["show bgp summary", '["vtysh", "-c", "show ip route"]']
    assert all(r["test"].endswith("test_seen_writes_nothing_unless_the_gate_asks") for r in rows)


class _AnswersAnything:
    """A fake that never calls seen(): only the profiler can tell what it was asked."""

    def exec(self, node, cmd, timeout=30):
        return "ok"


def _exec_(node, cmd):
    return "ok"


def _star(*a, **k):
    return "ok"


def _kw_only(node, *, cmd):
    return "ok"


# every way the tests bind a device fake (methods, lambdas, other names, *args, keyword-only, MagicMock,
# mock.patch, netns_exec): the hook logs at the boundary between the product and test code, not by name
SHAPES = {
    "method": lambda lab: lab,
    "instance-lambda": lambda lab: setattr(lab, "exec", lambda node, cmd, timeout=30: "ok") or lab,
    "instance-function": lambda lab: setattr(lab, "exec", _exec_) or lab,
    "netns_exec": lambda lab: setattr(lab, "netns_exec", _exec_) or lab,
    "star-args": lambda lab: setattr(lab, "exec", _star) or lab,
    "MagicMock": lambda lab: mock.MagicMock(),
}


def _product_caller(root: Path):
    """A function whose code lives under `root`, standing in for src/netdryrun calling a lab."""
    ns: dict = {}
    exec(compile("def call(target, attr, *a, **k):\n    return getattr(target, attr)(*a, **k)\n",
                 str(root / "caller.py"), "exec"), ns)
    return ns["call"]


def _logged(tmp_path, monkeypatch, run) -> list[dict]:
    log, root = tmp_path / "commands.jsonl", tmp_path / "src"
    monkeypatch.setenv(COMMAND_LOG, str(log))
    hook = command_profiler(code_root=str(root) + os.sep)
    old = sys.getprofile()
    sys.setprofile(hook)
    try:
        run(_product_caller(root))
    finally:
        sys.setprofile(old)
    return [json.loads(json.loads(x)["command"]) for x in log.read_text(encoding="utf-8").splitlines()] \
        if log.exists() else []


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_profiler_logs_every_shape_of_fake(tmp_path, monkeypatch, shape):
    attr = "netns_exec" if shape == "netns_exec" else "exec"
    rows = _logged(tmp_path, monkeypatch,
                   lambda call: call(SHAPES[shape](_AnswersAnything()), attr, "r1", ["vtysh", "-c", "show bgp x"]))
    assert any("show bgp x" in json.dumps(r) and "r1" in json.dumps(r) for r in rows), rows


def test_the_profiler_logs_keyword_only_and_patched_fakes(tmp_path, monkeypatch):
    def run(call):
        call(type("Lab", (), {"exec": staticmethod(_kw_only)})(), "exec", "r1", cmd="show kw")
        with mock.patch.object(_AnswersAnything, "exec", return_value="ok"):
            call(_AnswersAnything(), "exec", "r2", "show patched")
    text = json.dumps(_logged(tmp_path, monkeypatch, run))
    assert "show kw" in text and "show patched" in text, text


def test_the_profiler_logs_only_product_calls_into_test_code(tmp_path, monkeypatch):
    def run(call):
        _AnswersAnything().exec("r1", "from the test itself")       # not the product calling
        call(json, "dumps", ["not a fake"])                          # the product calling the library
    assert _logged(tmp_path, monkeypatch, run) == []


def test_logged_arguments_are_stable_between_runs():
    root = "/w/mixed"
    assert _plain(["/w/mixed/tests/x.yml", "/tmp/pytest-12/t0", object()], root) == \
        ["<root>/tests/x.yml", "/tmp/<tmp>/t0", "object"]


def test_the_hook_is_off_unless_the_gate_asks(tmp_path, monkeypatch):
    monkeypatch.delenv(COMMAND_LOG, raising=False)
    old = sys.getprofile()
    undo = logging_commands()
    assert sys.getprofile() is old
    undo()
