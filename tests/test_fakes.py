"""The shared fake-lab refusal (tests/fakes.py) and the rule that every fake lab uses it.

The release tooling recognises a new device read by the message "unexpected command: ..." on a fixture that no
longer holds. A fake that words its refusal differently turns a new read into an ordinary verdict change (still
blocked, but without asking for a live run on that network OS), so one wording is enforced here."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fakes import COMMAND_LOG, PREFIX, UnexpectedCommand, logging_commands, seen

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

    def exec_root(self, node, cmd):
        return "ok"


def test_the_profiler_logs_a_fake_that_never_calls_seen(tmp_path, monkeypatch):
    log = tmp_path / "commands.jsonl"
    monkeypatch.delenv(COMMAND_LOG, raising=False)
    logging_commands()()                         # off unless the gate asks: installs nothing, undo is a no-op
    _AnswersAnything().exec("r1", ["vtysh", "-c", "show version"])
    assert not log.exists()
    monkeypatch.setenv(COMMAND_LOG, str(log))
    undo = logging_commands()
    try:
        _AnswersAnything().exec("r1", ["vtysh", "-c", "show bgp neighbors"])
        _AnswersAnything().exec_root("r2", "ip -j addr")
    finally:
        undo()
    _AnswersAnything().exec("r1", "after undo")      # the undo took the hook off
    rows = [json.loads(json.loads(x)["command"]) for x in log.read_text(encoding="utf-8").splitlines()]
    assert {"call": "exec", "node": "r1", "cmd": ["vtysh", "-c", "show bgp neighbors"]} in rows
    assert {"call": "exec_root", "node": "r2", "cmd": "ip -j addr"} in rows
    assert not any(r["cmd"] == "after undo" for r in rows)
