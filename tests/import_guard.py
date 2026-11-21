"""A test run tests the checkout it runs in, or the source it says it is testing, and nothing else.

Many clones share one venv whose editable install points at the clone that ran `pip install -e` last. Without this
guard `python -m pytest` in clone A silently imported clone B's netdryrun and passed or failed on the wrong code.
tests/conftest.py exposes `pytest_configure` and `pytest_report_header` from here; the first aborts the session (exit 4)
when netdryrun does not come from the source expected, naming both paths, and the second prints which source this run
tested ("ndr-import-guard: mode=... source=..."). The expected source is one of:

  default                    <checkout>/src, the src beside this tests/ folder. The same folder as <rootdir>/src in the
                             repo, in the fast-fix gate's temporary trees (PYTHONPATH=<tree>/src) and in mutmut's
                             mutants/ copy (mutants/tests beside mutants/src).
  NDR_TEST_SRC=<dir>         that src, declared: the red-team run against an old release
                             (PYTHONPATH=<old>/src:tests ... see tests/redteam/README.md) and the contributor gate's
                             run of this PR's tests on the base branch's code.
  NDR_TEST_INSTALLED=1       an installed copy (the release gate's plain-container layer: `pip install .`, then pytest).
                             Every file of the installed netdryrun (except __pycache__) must be byte-identical to
                             <checkout>/src/netdryrun, with none missing and none extra, and it must not be the
                             checkout's own src (an `-e` install would be). Only the exact value "1" counts.

Every loaded `netdryrun` module is checked, not only the package, and must be a .py file inside the verified tree.
At configure time only the modules imported so far are loaded (the package), so in the first two modes any file under
the verified netdryrun/ that python could import in place of a .py (an extension module such as a .so, a sourceless
.pyc; __pycache__ excepted) is refused too. Data files and the .meta and .spans files mutmut writes next to a mutated
module cannot be imported and are left alone. In installed mode every file is compared byte for byte. The loaded modules are checked again when the session finishes,
which covers what the tests imported: a failure there makes the session exit 4 and no proof is written. After a pass
in the first two modes this puts the verified src first on PYTHONPATH, so a child `python -m netdryrun` runs the same
code instead of whatever the shared venv's editable install points at.

Proof for the gates: when NDR_GUARD_PROOF=<file> is set, a guard that passed at configure AND at session finish writes
{"mode", "source"} there (created exclusively; an existing file that differs fails the session); the variable is dropped from the
environment at configure. A gate that runs pytest on a tree with this guard requires the file: `--noconftest`,
`PYTEST_ADDOPTS=--noconftest` and `--confcutdir` skip conftest.py, and then nothing aborts and nothing is written.

Known limits: it checks the interpreter that runs pytest. A child started with `-I` or `-E`, with a stripped
environment, or by a test that rebuilds `sys.modules`, is not covered; neither is a session that never loads this
conftest unless a gate asks for the proof file."""
from __future__ import annotations

import importlib.machinery
import json
import os
import sys
from pathlib import Path

import pytest

SRC_ENV = "NDR_TEST_SRC"
INSTALLED_ENV = "NDR_TEST_INSTALLED"
PROOF_ENV = "NDR_GUARD_PROOF"
EXIT_CODE = 4


def _loaded(modules) -> dict:
    return {n: m for n, m in list(modules.items()) if n == "netdryrun" or n.startswith("netdryrun.")}


def _files(pkg: Path) -> dict[str, bytes]:
    """Every file of the package except bytecode caches: a .so or a data file counts."""
    return {p.relative_to(pkg).as_posix(): p.read_bytes() for p in sorted(pkg.rglob("*"))
            if p.is_file() and "__pycache__" not in p.relative_to(pkg).parts}


LOADABLE = tuple(s for s in (*importlib.machinery.EXTENSION_SUFFIXES, *importlib.machinery.BYTECODE_SUFFIXES,
                             *importlib.machinery.SOURCE_SUFFIXES) if s != ".py")


def _not_py(pkg: Path) -> list[str]:
    """Files under the package that python could import in place of the .py beside them: every extension-module,
    bytecode and source suffix of importlib.machinery except .py (a .so, a sourceless .pyc). Other files (data, and the
    .meta and .spans files mutmut writes next to a mutated module) cannot be imported and are left alone; installed mode
    compares them anyway. Bytecode caches (__pycache__) are not looked at."""
    return [p.relative_to(pkg).as_posix() for p in sorted(pkg.rglob("*"))
            if p.is_file() and p.name.endswith(LOADABLE) and "__pycache__" not in p.relative_to(pkg).parts]


def import_problem(modules, tests_dir: Path, env) -> tuple[str | None, Path | None, str | None]:
    """(abort message or None, the verified src dir for children's PYTHONPATH or None, the mode name). `modules` is
    sys.modules."""
    checkout_src = tests_dir.resolve().parent / "src"
    installed, declared = env.get(INSTALLED_ENV), env.get(SRC_ENV)
    if installed is not None and installed != "1":
        return f"{INSTALLED_ENV} must be exactly 1 or unset, got {installed!r}", None, None
    if installed is not None and declared is not None:
        return f"{INSTALLED_ENV} and {SRC_ENV} are both set; a run tests one source", None, None
    loaded = _loaded(modules)
    pkg = loaded.get("netdryrun")
    if pkg is None or getattr(pkg, "__file__", None) is None:
        return "netdryrun is not imported as a regular package (no __file__): nothing to verify", None, None
    files: dict[str, Path] = {}
    for name, mod in loaded.items():
        f = getattr(mod, "__file__", None)
        if f is None:
            return f"{name} has no __file__, so where it comes from cannot be verified", None, None
        files[name] = Path(f).resolve()
    odd = sorted(n for n, f in files.items() if f.suffix != ".py")
    if odd:
        return f"{odd[:3]} are not loaded from .py files ({files[odd[0]]}): a compiled or planted module", None, None
    actual = files["netdryrun"].parent

    if installed is not None:
        want = (checkout_src / "netdryrun").resolve()
        if actual == want:
            return (f"{INSTALLED_ENV}=1 expects an installed copy of {want}, but netdryrun is imported from the "
                    f"checkout's own src (an editable install?)"), None, None
        a, b = _files(actual), _files(want)
        missing, extra = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
        differ = sorted(k for k in a.keys() & b.keys() if a[k] != b[k])
        if missing or extra or differ:
            return (f"the installed netdryrun at {actual} is not this checkout's {want}: "
                    f"missing {missing[:5]}, extra {extra[:5]}, different {differ[:5]}"), None, None
        stray = sorted(n for n, f in files.items() if not f.is_relative_to(actual))
        if stray:
            return f"{stray[:3]} are imported from outside the installed copy {actual}", None, None
        return None, None, "installed"

    if declared is not None:
        if not declared or not Path(declared).is_dir():
            return f"{SRC_ENV}={declared!r} is not a directory", None, None
        src, how, mode = Path(declared).resolve(), f"declared by {SRC_ENV}", "declared"
    else:
        src, how, mode = checkout_src.resolve(), "this checkout's own src", "default"
    want = src / "netdryrun"
    stray = {n: f for n, f in files.items() if not f.is_relative_to(want)}
    if stray:
        n, f = next(iter(stray.items()))
        return (f"{n} is imported from {f}, which is not under {want} ({how}). Another clone's editable "
                f"install or a PYTHONPATH entry is shadowing it, so these tests would not test this code. Put "
                f"<checkout>/src first on PYTHONPATH, or declare the source you mean with {SRC_ENV}=<dir>."), None, None
    odd = _not_py(want) if want.is_dir() else []
    if odd:
        return (f"{want} holds files python could import instead of the source beside them ({odd[:3]}): a compiled "
                f"or planted module"), None, None
    return None, src, mode


def children_use(src: Path, env) -> str:
    """PYTHONPATH with the verified src first, then the rest as it was."""
    rest = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and Path(p).resolve() != src]
    return os.pathsep.join([str(src), *rest])


def write_proof(path: str, mode: str, source: str) -> None:
    """Exclusive create. A file that is already there and says the same thing is left alone; anything else raises, so a
    stale proof can never stand in for this run."""
    want = json.dumps({"mode": mode, "source": source})
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        try:
            same = Path(path).read_text(encoding="utf-8") == want
        except OSError:
            same = False
        if not same:      # a stale or foreign file: it must not stand in for this run
            raise RuntimeError(f"{path} already exists and is not this run's proof") from None
        return
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(want)


def _verify() -> tuple[str | None, Path | None, str | None]:
    try:
        import netdryrun  # noqa: F401
        return import_problem(sys.modules, Path(__file__).parent, os.environ)
    except BaseException as e:   # fail closed: an import that raises or exits, a path that cannot be read
        return f"the import guard could not verify where netdryrun comes from ({type(e).__name__}: {e})", None, None


def pytest_configure(config):
    problem, src, mode = _verify()
    if problem:
        pytest.exit(problem, returncode=EXIT_CODE)
    where = str(src) if src is not None else str(Path(sys.modules["netdryrun"].__file__).resolve().parent)
    if src is not None:
        os.environ["PYTHONPATH"] = children_use(src, os.environ)
    config.ndr_import_guard_proof = os.environ.pop(PROOF_ENV, None)
    config.ndr_import_guard_ran = True
    config.ndr_import_guard = (mode, where)


def pytest_sessionfinish(session, exitstatus):
    """The tests import more of netdryrun than the package: check again what is loaded now, and write the proof only if
    it still all comes from the verified source."""
    config = session.config
    if not getattr(config, "ndr_import_guard_ran", False):
        return
    problem, _, mode = _verify()
    if problem:
        sys.stderr.write(f"\nndr-import-guard: {problem}\n")
        session.exitstatus = EXIT_CODE
        return
    proof = getattr(config, "ndr_import_guard_proof", None)
    if proof:
        try:
            write_proof(proof, config.ndr_import_guard[0], config.ndr_import_guard[1])
        except (OSError, RuntimeError) as e:
            sys.stderr.write(f"\nndr-import-guard: could not write the proof: {e}\n")
            session.exitstatus = EXIT_CODE


def pytest_report_header(config):
    ran = getattr(config, "ndr_import_guard", None)
    return f"ndr-import-guard: mode={ran[0]} source={ran[1]}" if ran else "ndr-import-guard: DID NOT RUN"
