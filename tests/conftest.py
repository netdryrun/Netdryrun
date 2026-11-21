"""Unit tests never touch a real lab.

A mutant can turn a faked lab into the real one (for example `side_fn or real_side(...)` into `side_fn and ...`):
the mutation layer then ran `containerlab deploy` on a test topology through passwordless sudo, and left its
containers behind (2026-10-30). Every `containerlab deploy` or `destroy` a unit test reaches through `netdryrun.lab`
fails here instead. A test that fakes `lab._run` itself replaces this guard, as before."""
import importlib

import pytest
from import_guard import pytest_configure, pytest_report_header, pytest_sessionfinish  # noqa: F401  (aborts if netdryrun is not the source under test)

import fakes

# the release gate's command log (tests/fakes.py) begins before any test module imports the product
fakes.begin_session()

REAL_LAB_TOOLS = {"containerlab", "clab"}
CHANGES_A_LAB = {"deploy", "destroy"}   # read-only commands (`containerlab version`) stay allowed


@pytest.fixture(autouse=True)
def _no_real_lab(monkeypatch):
    from netdryrun import lab

    real = lab._run

    def guarded(cmd, *args, **kwargs):
        words = {str(c).rsplit("/", 1)[-1] for c in cmd}
        if words & REAL_LAB_TOOLS and words & CHANGES_A_LAB:
            raise RuntimeError(f"a unit test tried to run a real lab command: {' '.join(map(str, cmd))[:200]}")
        return real(cmd, *args, **kwargs)
    monkeypatch.setattr(lab, "_run", guarded)


def load_mgmt():
    """netdryrun.mgmt, or None for a release from before mgmt.py (the red-team procedure, tests/redteam/README.md). Any
    other import failure, including one inside mgmt.py, is a real error."""
    try:
        return importlib.import_module("netdryrun.mgmt")
    except ImportError as e:
        if e.name != "netdryrun.mgmt":
            raise
        return None


def disable_ready_wait(monkeypatch, load=load_mgmt):
    mgmt = load()
    if mgmt is not None:
        monkeypatch.setattr(mgmt, "READY_BUDGET", 0.0)     # a renamed attribute must fail here, not be skipped


@pytest.fixture(autouse=True)
def _no_readiness_wait(monkeypatch):
    """mgmt.prepare waits up to READY_BUDGET for a booting NOS; unit tests' fakes answer at once or never, so they get
    no wait (the readiness tests set their own budget)."""
    disable_ready_wait(monkeypatch)


@pytest.fixture(autouse=True)
def _log_fake_lab_commands(tmp_path_factory):
    """With NDR_FAKE_COMMAND_LOG set (the release gate sets it, nothing else does), every command a test sends to a
    lab, fake or real, is logged through tests/fakes.py, so comparing two versions shows a new device read even where
    the fake answers anything (tests/fakes.py)."""
    from fakes import logging_commands
    undo = logging_commands(tmp_path_factory.getbasetemp)
    try:
        yield
    finally:
        undo()
