"""The release gate's fake-lab command log for a fixture world that keeps none (scripts/fastfix_gate.py loosening).

A base from before the log (v0.4.2: no tests/fakes.py, a tests/conftest.py that logs nothing) can't show a new device
read that a fake answering by substring hides, so every new-read allowlist entry looked wrong to the judge. When the
base's own tests/conftest.py doesn't install the log, the gate loads this plugin into BOTH runs it compares (the
base's code, then the candidate's code in the base's world), so the two logs come from the same code:

- as pytest loads it, before any product import, it begins the session record (tests/fakes.py begin_session);
- an autouse fixture installs the profiler on every test, logging calls from the tree's src/ into the tree's tests/
  (fakes, mocks, callbacks), with the scrubbing the suite's own log has;
- the logging code is the judge's own tests/fakes.py (the commit the judge came from), which the gate copies beside
  this file as ndr_gate_fakes: never the tree's tests/, never the candidate's;
- it writes a proof that it ran to the file NDR_GATE_CMDLOG_PROOF names (read here, before any product import), and
  the gate fails closed without it.

The gate copies this file as ndr_gate_cmdlog.py into a fresh directory holding only these two files, puts that
directory first on PYTHONPATH (nothing else there can shadow the standard library or the tree; the tree can't shadow
these two names), and loads it with -p ndr_gate_cmdlog. The code under test still runs in the same process as the log
writer, as it does with the suite's own log (the known limit: the log is a set per test, written by the code it
judges)."""
from __future__ import annotations

import json
import os

import ndr_gate_fakes as fakes
import pytest

PROOF_ENV = "NDR_GATE_CMDLOG_PROOF"
_PROOF = os.environ.get(PROOF_ENV)       # before the product is imported: code under test can't move it
_LOG = os.environ.get(fakes.COMMAND_LOG)  # likewise the log this run sorts at the end
_RAN = {"tests": 0}

fakes.begin_session()


@pytest.fixture(autouse=True)
def _ndr_gate_command_log(request, tmp_path_factory):
    """The suite's own _log_fake_lab_commands (tests/conftest.py), for a tree that doesn't have it."""
    root = str(request.config.rootpath)
    undo = fakes.logging_commands(tmp_path_factory.getbasetemp, code_root=os.path.join(root, "src") + os.sep,
                                  fake_root=os.path.join(root, "tests") + os.sep)
    _RAN["tests"] += 1
    try:
        yield
    finally:
        undo()


def _sort_log() -> None:
    """Rows of one test in a fixed order, tests in the order they first logged, so the raw log is byte-stable even
    when a test's threads reach the fakes in a different order on each run. An unreadable row raises, and the run
    then leaves no proof (the gate fails closed)."""
    if not _LOG or not os.path.isfile(_LOG):
        return
    with open(_LOG, encoding="utf-8") as f:
        lines = f.read().splitlines()
    first: dict[str, int] = {}
    keyed = []
    for line in lines:
        test = json.loads(line)["test"]
        keyed.append((first.setdefault(test, len(first)), line))
    with open(_LOG, "w", encoding="utf-8") as f:
        f.writelines(line + "\n" for _, line in sorted(keyed))


def pytest_sessionfinish(session, exitstatus):
    _sort_log()
    if _PROOF:
        with open(_PROOF, "w", encoding="utf-8") as f:
            json.dump({"session": bool(fakes._STATE["session"]), "tests": _RAN["tests"],
                       "root": str(session.config.rootpath), "log": fakes.LOG_FORMAT}, f)
