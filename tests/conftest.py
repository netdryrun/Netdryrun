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
