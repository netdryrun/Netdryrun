"""Unit tests never touch a real lab.

A mutant can turn a faked lab into the real one (for example `side_fn or real_side(...)` into `side_fn and ...`):
the mutation layer then ran `containerlab deploy` on a test topology through passwordless sudo, and left its
containers behind (2026-10-30). Every `containerlab deploy` or `destroy` a unit test reaches through `netdryrun.lab`
fails here instead. A test that fakes `lab._run` itself replaces this guard, as before."""
from pathlib import Path

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


# ------------------------------------------------------------------------------------------------ own-checkout guard

# Many clones share one venv, and its editable install points at whichever clone ran `pip install -e` last. Without
# this guard `python -m pytest` in clone A could silently test clone B's code. pyproject.toml puts this checkout's src
# first (`pythonpath`); this fails the session if netdryrun still does not come from there. The expected path is the
# src beside this tests/ folder: the same folder as <rootdir>/src in the repo, in the fast-fix gate's temporary trees
# (PYTHONPATH=<tree>/src) and in mutmut's mutants/ copy (mutants/tests beside mutants/src).


def own_src_problem(netdryrun_file: str, tests_dir: Path) -> str | None:
    """None when `netdryrun_file` is this checkout's own netdryrun (symlinks resolved), else the abort message."""
    expected = (tests_dir.resolve().parent / "src" / "netdryrun").resolve()
    actual = Path(netdryrun_file).resolve().parent
    if actual == expected:
        return None
    return (f"netdryrun is imported from {actual}, not from this checkout's {expected}. Another clone's editable install "
            f"or a PYTHONPATH entry is shadowing it, so these tests would not test this code. Run pytest from the "
            f"checkout with its own pyproject.toml (pythonpath = [\"src\"]) or set PYTHONPATH=<checkout>/src.")


def pytest_configure(config):
    import netdryrun

    problem = own_src_problem(netdryrun.__file__, Path(__file__).parent)
    if problem:
        pytest.exit(problem, returncode=4)
