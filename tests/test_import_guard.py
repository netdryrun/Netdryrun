"""A test run tests the checkout it runs in (tests/conftest.py `pytest_configure`).

Many clones share one venv whose editable install points at the clone that ran `pip install -e` last; without the
guard, pytest in another clone imported that clone's netdryrun and passed or failed on the wrong code."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFTEST = ROOT / "tests" / "conftest.py"

_spec = importlib.util.spec_from_file_location("_ndr_conftest_under_test", CONFTEST)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def make_checkout(tmp_path, *, real_src: bool) -> Path:
    """A minimal checkout: the real conftest, one passing test, a pyproject WITHOUT `pythonpath`. With `real_src` its
    src is a symlink to this repo's src (so the guard must resolve symlinks); without, it has no netdryrun at all."""
    tree = tmp_path / "checkout"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests" / "conftest.py").write_text(CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
    (tree / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tree / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8")
    if real_src:
        (tree / "src").symlink_to(ROOT / "src", target_is_directory=True)
    else:
        (tree / "src").mkdir()
    return tree


def pytest_in(tree: Path, pythonpath: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(PYTHONPATH=str(pythonpath), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                           "-c", str(tree / "pyproject.toml"), "--rootdir", str(tree)],
                          cwd=tree, env=env, capture_output=True, text=True, timeout=300)


def decoy(tmp_path) -> Path:
    d = tmp_path / "other-clone" / "src"
    (d / "netdryrun").mkdir(parents=True)
    (d / "netdryrun" / "__init__.py").write_text("", encoding="utf-8")
    return d


def test_netdryrun_from_another_clone_aborts_the_session(tmp_path):
    tree = make_checkout(tmp_path, real_src=False)
    other = decoy(tmp_path)
    p = pytest_in(tree, other)
    out = p.stdout + p.stderr
    assert p.returncode == 4, out
    assert "passed" not in out, out                      # the test did not run
    assert str((other / "netdryrun").resolve()) in out   # names where it came from
    assert str((tree / "src" / "netdryrun").resolve()) in out   # and where it should have come from


def test_the_checkouts_own_src_passes_even_through_a_symlink(tmp_path):
    tree = make_checkout(tmp_path, real_src=True)
    p = pytest_in(tree, tree / "src")                    # the fast-fix gate's PYTHONPATH=<tree>/src
    assert p.returncode == 0, p.stdout + p.stderr
    assert "1 passed" in p.stdout


def test_own_src_problem_compares_resolved_paths(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    assert guard.own_src_problem(str(tmp_path / "src" / "netdryrun" / "__init__.py"), tests_dir) is None
    assert guard.own_src_problem(str(tmp_path / "other" / "src" / "netdryrun" / "__init__.py"), tests_dir)


def test_this_session_runs_the_checkouts_own_netdryrun():
    import netdryrun
    assert Path(netdryrun.__file__).resolve().is_relative_to((ROOT / "src" / "netdryrun").resolve())
