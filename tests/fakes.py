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
"""
from __future__ import annotations

import json
import os

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
