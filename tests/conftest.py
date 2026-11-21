"""Unit tests never touch a real lab.

A mutant can turn a faked lab into the real one (for example `side_fn or real_side(...)` into `side_fn and ...`):
the mutation layer then ran `containerlab deploy` on a test topology through passwordless sudo, and left its
containers behind (2026-10-30). Every `containerlab deploy` or `destroy` a unit test reaches through `netdryrun.lab`
fails here instead. A test that fakes `lab._run` itself replaces this guard, as before."""
import pytest

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


@pytest.fixture(autouse=True)
def _no_readiness_wait(monkeypatch):
    """mgmt.prepare waits up to READY_BUDGET for a booting NOS; unit tests' fakes answer at once or never, so they get
    no wait (the readiness tests set their own budget)."""
    from netdryrun import mgmt
    monkeypatch.setattr(mgmt, "READY_BUDGET", 0.0)


@pytest.fixture(autouse=True)
def _no_import_check_gap(monkeypatch):
    """The FRR import-check guard (FP-043-FRRIMPORTCHK) takes two samples SAMPLE_GAP apart before every run's checks.
    Unit tests' fakes answer the same at once, and many tests time their fake worlds from the run's start, so the two
    samples are taken with no gap here (both are still taken and must agree; an unreadable or changing answer still
    waits RETRY_GAP, so the time limit is still reached). tests/test_frr_import_check.py keeps the real gap."""
    from netdryrun.drivers import frr_import_check
    monkeypatch.setattr(frr_import_check, "SAMPLE_GAP", 0.0)


@pytest.fixture(autouse=True)
def _log_fake_lab_commands():
    """With NDR_FAKE_COMMAND_LOG set (the release gate sets it, nothing else does), every command a test sends to a
    lab, fake or real, is logged through tests/fakes.py, so comparing two versions shows a new device read even where
    the fake answers anything (tests/fakes.py)."""
    from fakes import logging_commands
    undo = logging_commands()
    try:
        yield
    finally:
        undo()
