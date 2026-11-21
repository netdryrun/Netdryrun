"""What every hand-written fake lab in the tests shares.

A fake lab answers the commands a test expects and refuses the rest with `UnexpectedCommand`, whose message always
begins "unexpected command: ". The release tooling (scripts/fastfix_gate.py) reads that prefix: when code under test
sends a fake a command it was never given, the change reads something new from the device, and the gate asks for a
live run on that network OS instead of treating the failure as an ordinary verdict change. A fake that raised its own
wording would hide that, so tests/test_fakes.py refuses any other `unexpected command` raise under tests/.

`seen(command)` records each command a fake was sent, one JSON line per command, in the file named by
NDR_FAKE_COMMAND_LOG when the gate sets it (and nowhere otherwise). Comparing two runs of the same test on two
versions of the code shows a command only the newer one sends, even when a fake that matches by substring answered
it without complaint.

Not every fake calls `seen`, so tests/conftest.py also installs `command_profiler()` while the log is on, on the test's
thread and on every thread started after it (the product evaluates checks on a thread pool). It logs at the boundary,
not by name.

Logged: every call whose caller is a Python function in a file under src/netdryrun and whose callee is a Python
function in a file under tests/ or in unittest/mock.py: a fake class's method, a lambda or function bound in its place
under any name (exec, exec_root, netns_exec or anything a later driver uses), *args or keyword-only alike, functools.
partial around such a function, a MagicMock or mock.patch stand-in, and a callback a test hands in (a fake clock, say;
a change to what the code passes it then shows as new, which only ever asks for more review). Arguments are logged as
plain data, other objects by their type, the test's working directory as <root>, so two runs of one test log the
same lines.

Not logged, because no such call is visible to a profiler as product-calls-test-code:
- a C callable answering in a fake's place (dict.get, str.format, list.append, a builtin): it has no Python frame;
- code compiled at run time (mock.create_autospec, exec, eval, compile, types.FunctionType): its file is <string>;
- a stand-in defined outside tests/ (another package, a file compiled under another path);
- a fake called straight from the standard library, such as pool.map(lab.exec) or Thread(target=lab.exec) written in
  the product: the caller is concurrent/futures or threading, not src/netdryrun;
- a fake executable on PATH: it answers in another process.
tests/test_fakes.py refuses each of these shapes in the must-not-pass fixtures (and the last-but-one in src/), so the
gate's comparison never rests on a fake it can't see.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading

PREFIX = "unexpected command: "
COMMAND_LOG = "NDR_FAKE_COMMAND_LOG"


class UnexpectedCommand(AssertionError):
    """A fake lab was sent a command it has no answer for."""

    def __init__(self, command: object):
        self.command = command
        super().__init__(f"{PREFIX}{command}")


def seen(command: object) -> None:
    """Record that a fake lab was sent `command` (only when the gate asks for the log)."""
    path = os.environ.get(COMMAND_LOG)
    if not path:
        return
    test = os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" (", 1)[0]
    text = command if isinstance(command, str) else json.dumps(command, default=str)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"test": test, "command": text}) + "\n")


_TMP = re.compile(r"pytest-\d+|tmp[A-Za-z0-9_]{6,}")


def _plain(value: object, root: str, depth: int = 0) -> object:
    """`value` as stable JSON: strings, numbers, lists and dicts as they are (the test's working directory and
    temporary names scrubbed), anything else by its type name (its repr may hold an address)."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (str, os.PathLike, bytes)):
        text = os.fsdecode(value) if not isinstance(value, bytes) else value.decode("utf-8", "replace")
        return _TMP.sub("<tmp>", text.replace(root, "<root>"))
    if depth > 4:
        return type(value).__name__
    if isinstance(value, (list, tuple)):
        return [_plain(v, root, depth + 1) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v, root, depth + 1) for v in value), key=repr)
    if isinstance(value, dict):
        return {str(k): _plain(v, root, depth + 1) for k, v in value.items()}
    return type(value).__name__


def _package_root() -> str:
    try:
        import netdryrun
        return os.path.dirname(os.path.abspath(netdryrun.__file__)) + os.sep
    except ImportError:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "netdryrun") + os.sep


def command_profiler(code_root: str | None = None, fake_root: str | None = None):
    """A sys.setprofile hook (install it only while logging) that logs, through `seen`, every call from code under
    `code_root` (src/netdryrun) into code under `fake_root` (tests/) or unittest.mock, with its arguments."""
    import unittest.mock
    code_root = code_root or _package_root()
    fakes = (fake_root or os.path.dirname(os.path.abspath(__file__)) + os.sep,)
    mock_file = os.path.abspath(unittest.mock.__file__)
    callers: dict = {}
    callees: dict = {}

    def profile(frame, event, arg):
        if event != "call" or frame.f_back is None:
            return
        caller = frame.f_back.f_code
        inside = callers.get(caller)
        if inside is None:
            inside = callers[caller] = os.path.abspath(caller.co_filename).startswith(code_root)
        if not inside:
            return
        code = frame.f_code
        fake = callees.get(code)
        if fake is None:
            where = os.path.abspath(code.co_filename)
            fake = callees[code] = where.startswith(fakes) or where == mock_file
        if not fake:
            return
        n = code.co_argcount + code.co_kwonlyargcount + bool(code.co_flags & 0x04) + bool(code.co_flags & 0x08)
        root = os.getcwd()
        args = {k: _plain(frame.f_locals.get(k), root) for k in code.co_varnames[:n] if k not in ("self", "cls")}
        seen({"call": code.co_name, "args": args})
    return profile


def logging_commands():
    """Install the profiler on this thread and new ones while NDR_FAKE_COMMAND_LOG is set; returns an undo."""
    if not os.environ.get(COMMAND_LOG):
        return lambda: None
    old = sys.getprofile()
    hook = command_profiler()
    sys.setprofile(hook)
    threading.setprofile(hook)

    def undo():
        sys.setprofile(old)
        threading.setprofile(None)
    return undo
