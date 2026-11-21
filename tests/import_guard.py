"""A test run tests the checkout it runs in, or the source it says it is testing, and nothing else.

Many clones share one venv whose editable install points at the clone that ran `pip install -e` last. Without this
guard `python -m pytest` in clone A silently imported clone B's netdryrun and passed or failed on the wrong code.
tests/conftest.py exposes `pytest_configure` from here; it aborts the session (exit 4) when netdryrun does not come
from the source expected, naming both paths. The expected source is one of:

  default                    <checkout>/src, the src beside this tests/ folder. The same folder as <rootdir>/src in the
                             repo, in the fast-fix gate's temporary trees (PYTHONPATH=<tree>/src) and in mutmut's
                             mutants/ copy (mutants/tests beside mutants/src).
  NDR_TEST_SRC=<dir>         that src, declared: the red-team run against an old release
                             (PYTHONPATH=<old>/src:tests ... see tests/redteam/README.md) and the contributor gate's
                             run of this PR's tests on the base branch's code.
  NDR_TEST_INSTALLED=1       an installed copy (the release gate's plain-container layer: `pip install .`, then pytest).
                             Every .py file of the installed netdryrun must be byte-identical to
                             <checkout>/src/netdryrun, with none missing and none extra, and it must not be the
                             checkout's own src (an `-e` install would be). Only the exact value "1" counts.

Every loaded `netdryrun` module is checked, not only the package. After a pass in the first two modes this puts the
verified src first on PYTHONPATH, so a child `python -m netdryrun` runs the same code instead of whatever the shared
venv's editable install points at."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SRC_ENV = "NDR_TEST_SRC"
INSTALLED_ENV = "NDR_TEST_INSTALLED"
EXIT_CODE = 4


def _loaded(modules) -> dict:
    return {n: m for n, m in list(modules.items()) if n == "netdryrun" or n.startswith("netdryrun.")}


def _py_files(pkg: Path) -> dict[str, bytes]:
    return {p.relative_to(pkg).as_posix(): p.read_bytes() for p in sorted(pkg.rglob("*.py"))}


def import_problem(modules, tests_dir: Path, env) -> tuple[str | None, Path | None]:
    """(abort message or None, the verified src dir for children's PYTHONPATH or None). `modules` is sys.modules."""
    checkout_src = tests_dir.resolve().parent / "src"
    installed, declared = env.get(INSTALLED_ENV), env.get(SRC_ENV)
    if installed is not None and installed != "1":
        return f"{INSTALLED_ENV} must be exactly 1 or unset, got {installed!r}", None
    if installed is not None and declared is not None:
        return f"{INSTALLED_ENV} and {SRC_ENV} are both set; a run tests one source", None
    loaded = _loaded(modules)
    pkg = loaded.get("netdryrun")
    if pkg is None or getattr(pkg, "__file__", None) is None:
        return "netdryrun is not imported as a regular package (no __file__): nothing to verify", None
    files: dict[str, Path] = {}
    for name, mod in loaded.items():
        f = getattr(mod, "__file__", None)
        if f is None:
            return f"{name} has no __file__, so where it comes from cannot be verified", None
        files[name] = Path(f).resolve()
    actual = files["netdryrun"].parent

    if installed is not None:
        want = (checkout_src / "netdryrun").resolve()
        if actual == want:
            return (f"{INSTALLED_ENV}=1 expects an installed copy of {want}, but netdryrun is imported from the "
                    f"checkout's own src (an editable install?)"), None
        a, b = _py_files(actual), _py_files(want)
        missing, extra = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
        differ = sorted(k for k in a.keys() & b.keys() if a[k] != b[k])
        if missing or extra or differ:
            return (f"the installed netdryrun at {actual} is not this checkout's {want}: "
                    f"missing {missing[:5]}, extra {extra[:5]}, different {differ[:5]}"), None
        stray = sorted(n for n, f in files.items() if not f.is_relative_to(actual))
        if stray:
            return f"{stray[:3]} are imported from outside the installed copy {actual}", None
        return None, None

    if declared is not None:
        if not declared or not Path(declared).is_dir():
            return f"{SRC_ENV}={declared!r} is not a directory", None
        src, how = Path(declared).resolve(), f"declared by {SRC_ENV}"
    else:
        src, how = checkout_src.resolve(), "this checkout's own src"
    want = src / "netdryrun"
    stray = {n: f for n, f in files.items() if not f.is_relative_to(want)}
    if stray:
        n, f = next(iter(stray.items()))
        return (f"netdryrun is imported from {actual}, not from {want} ({how}); {n} is at {f}. Another clone's editable "
                f"install or a PYTHONPATH entry is shadowing it, so these tests would not test this code. Put "
                f"<checkout>/src first on PYTHONPATH, or declare the source you mean with {SRC_ENV}=<dir>."), None
    return None, src


def children_use(src: Path, env) -> str:
    """PYTHONPATH with the verified src first, then the rest as it was."""
    rest = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and Path(p).resolve() != src]
    return os.pathsep.join([str(src), *rest])


def pytest_configure(config):
    problem, src = None, None
    try:
        import netdryrun  # noqa: F401
        problem, src = import_problem(sys.modules, Path(__file__).parent, os.environ)
    except BaseException as e:   # fail closed: an import that raises, a path that cannot be read
        problem = f"the import guard could not verify where netdryrun comes from ({type(e).__name__}: {e})"
    if problem:
        pytest.exit(problem, returncode=EXIT_CODE)
    if src is not None:
        os.environ["PYTHONPATH"] = children_use(src, os.environ)
    config.ndr_import_guard_ran = True
