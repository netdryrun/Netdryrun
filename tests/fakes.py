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

Not every fake calls `seen`, so tests/conftest.py also installs `command_profiler()` while the log is on: it records
every call to a method named `exec` or `exec_root` (the only way code under test reaches a device, fake or real),
whatever fake answers it, including the ones in tests/oracles/.
"""
from __future__ import annotations

import json
import os
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


def command_profiler():
    """A sys.setprofile hook that logs every exec/exec_root call through `seen` (install it only while logging)."""
    def profile(frame, event, arg):
        if event != "call" or frame.f_code.co_name not in ("exec", "exec_root"):
            return
        code = frame.f_code
        args = [frame.f_locals.get(n) for n in code.co_varnames[:code.co_argcount] if n != "self"]
        if len(args) >= 2:
            seen({"call": code.co_name, "node": args[0], "cmd": args[1]})
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
