"""A test run tests the source it says it tests (tests/import_guard.py).

Many clones share one venv whose editable install points at the clone that ran `pip install -e` last; without the
guard, pytest in another clone imported that clone's netdryrun and passed or failed on the wrong code. Each mode of the
guard has a red case (a decoy or a doctored copy aborts the session) and a green one, run in the shape it is used in:
a subprocess pytest in a temporary checkout."""
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

import import_guard
from import_guard import children_use, import_problem

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import release_gate  # noqa: E402

STRIPPED = ("PYTHONPATH", "NDR_TEST_SRC", "NDR_TEST_INSTALLED")
CONFTEST = "from import_guard import pytest_configure  # noqa: F401\n"


def make_checkout(tmp_path, *, src="link", test="def test_ok():\n    assert True\n") -> Path:
    """A minimal checkout: the real guard, a conftest that only exposes it, one test, a pyproject WITHOUT pythonpath.
    src="link": a symlink to this repo's src (the guard must resolve symlinks); "empty": no netdryrun at all."""
    tree = tmp_path / "checkout"
    (tree / "tests").mkdir(parents=True)
    shutil.copy(ROOT / "tests" / "import_guard.py", tree / "tests" / "import_guard.py")
    (tree / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    (tree / "tests" / "test_ok.py").write_text(test, encoding="utf-8")
    (tree / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8")
    if src == "link":
        (tree / "src").symlink_to(ROOT / "src", target_is_directory=True)
    else:
        (tree / "src").mkdir()
    return tree


def run_pytest(tree: Path, *, pythonpath=None, **env_extra) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    env.update({k: str(v) for k, v in env_extra.items()}, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                           "-c", str(tree / "pyproject.toml"), "--rootdir", str(tree)],
                          cwd=tree, env=env, capture_output=True, text=True, timeout=300)


def out(p) -> str:
    return p.stdout + p.stderr


def decoy(tmp_path) -> Path:
    d = tmp_path / "other-clone" / "src"
    (d / "netdryrun").mkdir(parents=True)
    (d / "netdryrun" / "__init__.py").write_text("", encoding="utf-8")
    return d


def installed_copy(tmp_path) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    shutil.copytree(ROOT / "src" / "netdryrun", site / "netdryrun", ignore=shutil.ignore_patterns("__pycache__"))
    return site


def aborted(p, *named):
    assert p.returncode == 4, out(p)
    assert "passed" not in out(p), out(p)         # no test ran
    for n in named:
        assert str(n) in out(p), (n, out(p))


# ---- the default: this checkout's own src ----------------------------------------------------------------------------
def test_netdryrun_from_another_clone_aborts_the_session(tmp_path):
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    aborted(run_pytest(tree, pythonpath=other), (other / "netdryrun").resolve(), (tree / "src" / "netdryrun").resolve())


def test_the_shared_venv_install_is_not_this_checkout(tmp_path):
    """No PYTHONPATH: netdryrun comes from the interpreter's own install (the editable one of whichever clone ran
    pip install -e), which is not this checkout's src."""
    tree = make_checkout(tmp_path, src="empty")
    aborted(run_pytest(tree), (tree / "src" / "netdryrun").resolve())


def test_the_checkouts_own_src_passes_even_through_a_symlink(tmp_path):
    tree = make_checkout(tmp_path)
    p = run_pytest(tree, pythonpath=tree / "src")        # the fast-fix gate's PYTHONPATH=<tree>/src
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)


def test_the_guard_ran_in_this_session(request):
    assert request.config.ndr_import_guard_ran is True


def test_this_session_runs_the_checkouts_own_netdryrun():
    import netdryrun
    if os.environ.get(import_guard.INSTALLED_ENV) == "1":
        pytest.skip("the plain-container layer tests the installed copy")
    assert Path(netdryrun.__file__).resolve().is_relative_to((ROOT / "src" / "netdryrun").resolve())


# ---- children run the verified source --------------------------------------------------------------------------------
def test_a_child_python_gets_the_verified_src_first(tmp_path):
    """tests run `sys.executable -m netdryrun` (test_mcp, test_advisory_fixtures); with no PYTHONPATH of their own they
    imported the shared venv's editable install, whose code is another clone's. The guard puts the verified src first."""
    probe = ("import os, subprocess, sys\nfrom pathlib import Path\n\n"
             "def test_child_sees_the_verified_src():\n"
             "    env = dict(os.environ)\n"
             "    got = subprocess.run([sys.executable, '-c', 'import sys; print(sys.path[1])'], env=env,\n"
             "                         capture_output=True, text=True).stdout.strip()\n"
             f"    assert Path(got).resolve() == Path({str((ROOT / 'src').resolve())!r})\n")
    tree = make_checkout(tmp_path, test=probe)
    launcher = (f"import sys; sys.path.insert(0, {str(tree / 'src')!r}); import pytest; "
                f"sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '-o', 'addopts=', '-c', "
                f"{str(tree / 'pyproject.toml')!r}, '--rootdir', {str(tree)!r}]))")
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED}     # no PYTHONPATH at all
    p = subprocess.run([sys.executable, "-c", launcher], cwd=tree, env=env, capture_output=True, text=True, timeout=300)
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)


def test_children_use_puts_the_verified_src_first_once(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    sep = os.pathsep
    assert children_use(src, {}) == str(src)
    assert children_use(src, {"PYTHONPATH": f"/a{sep}{src}{sep}/b"}) == sep.join([str(src), "/a", "/b"])


# ---- NDR_TEST_SRC: a declared source ---------------------------------------------------------------------------------
def test_a_declared_src_is_the_source_under_test(tmp_path):
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    p = run_pytest(tree, pythonpath=other, NDR_TEST_SRC=other)
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)


def test_a_declared_src_that_is_not_what_imports_aborts(tmp_path):
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    aborted(run_pytest(tree, pythonpath=tree / "src", NDR_TEST_SRC=other), (other / "netdryrun").resolve())
    aborted(run_pytest(tree, pythonpath=other, NDR_TEST_SRC=tmp_path / "nowhere"))


# ---- NDR_TEST_INSTALLED: an installed copy, byte for byte ------------------------------------------------------------
def test_an_installed_copy_identical_to_the_checkout_passes(tmp_path):
    tree, site = make_checkout(tmp_path), installed_copy(tmp_path)
    p = run_pytest(tree, pythonpath=site, NDR_TEST_INSTALLED="1")
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)


@pytest.mark.parametrize("doctor", ["delete", "extra", "edit"])
def test_an_installed_copy_that_differs_from_the_checkout_aborts(tmp_path, doctor):
    tree, site = make_checkout(tmp_path), installed_copy(tmp_path)
    pkg = site / "netdryrun"
    if doctor == "delete":
        (pkg / "checks.py").unlink()
    elif doctor == "extra":
        (pkg / "planted.py").write_text("x = 1\n", encoding="utf-8")
    else:
        (pkg / "checks.py").write_text((pkg / "checks.py").read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    aborted(run_pytest(tree, pythonpath=site, NDR_TEST_INSTALLED="1"), pkg.resolve())


def test_foreign_code_in_place_of_the_installed_copy_aborts(tmp_path):
    tree = make_checkout(tmp_path)
    aborted(run_pytest(tree, pythonpath=decoy(tmp_path), NDR_TEST_INSTALLED="1"))


def test_an_editable_install_is_not_an_installed_copy(tmp_path):
    """What `pip install -e` would give the container: the checkout's own src."""
    tree = make_checkout(tmp_path)
    p = run_pytest(tree, pythonpath=tree / "src", NDR_TEST_INSTALLED="1")
    aborted(p)
    assert "editable" in out(p)


@pytest.mark.parametrize("value", ["", "0", "true", "yes", "11"])
def test_only_the_exact_value_1_turns_installed_mode_on(tmp_path, value):
    tree = make_checkout(tmp_path)
    aborted(run_pytest(tree, pythonpath=installed_copy(tmp_path), NDR_TEST_INSTALLED=value), "exactly 1")


def test_installed_and_declared_together_abort(tmp_path):
    tree, site = make_checkout(tmp_path), installed_copy(tmp_path)
    aborted(run_pytest(tree, pythonpath=site, NDR_TEST_INSTALLED="1", NDR_TEST_SRC=site), "both set")


def test_an_import_that_raises_aborts_instead_of_crashing(tmp_path):
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    (other / "netdryrun" / "__init__.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    p = run_pytest(tree, pythonpath=other)
    aborted(p, "could not verify")
    assert "boom" in out(p)


# ---- the comparison itself -------------------------------------------------------------------------------------------
def mod(path) -> types.SimpleNamespace:
    return types.SimpleNamespace(__file__=None if path is None else str(path))


def test_a_loaded_submodule_from_elsewhere_is_caught_not_only_the_package(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    own = tmp_path / "src" / "netdryrun"
    ok = {"netdryrun": mod(own / "__init__.py"), "netdryrun.checks": mod(own / "checks.py")}
    assert import_problem(ok, tests_dir, {}) == (None, (tmp_path / "src").resolve())
    bad = {**ok, "netdryrun.lab": mod(tmp_path / "elsewhere" / "src" / "netdryrun" / "lab.py")}
    problem, src = import_problem(bad, tests_dir, {})
    assert problem and "netdryrun.lab" in problem and src is None


def test_a_package_without_a_file_cannot_be_verified(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    problem, _ = import_problem({"netdryrun": mod(None)}, tests_dir, {})
    assert problem and "regular package" in problem
    problem, _ = import_problem({}, tests_dir, {})
    assert problem
    own = tmp_path / "src" / "netdryrun"
    problem, _ = import_problem({"netdryrun": mod(own / "__init__.py"), "netdryrun.x": mod(None)}, tests_dir, {})
    assert problem and "netdryrun.x" in problem


@pytest.mark.skipif(sys.platform in ("win32", "darwin"), reason="needs a case-sensitive file system")
def test_paths_that_differ_only_in_case_are_different_places(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    problem, _ = import_problem({"netdryrun": mod(tmp_path / "SRC" / "netdryrun" / "__init__.py")}, tests_dir, {})
    assert problem


def test_a_user_site_install_is_not_the_installed_copy(tmp_path):
    """The installed mode compares bytes, not locations: a package in the user site that differs from the checkout fails."""
    tests_dir = tmp_path / "checkout" / "tests"
    tests_dir.mkdir(parents=True)
    (tmp_path / "checkout" / "src" / "netdryrun").mkdir(parents=True)
    (tmp_path / "checkout" / "src" / "netdryrun" / "__init__.py").write_text("a = 1\n", encoding="utf-8")
    user = tmp_path / "home" / ".local" / "lib" / "python3" / "site-packages" / "netdryrun"
    user.mkdir(parents=True)
    (user / "__init__.py").write_text("a = 2\n", encoding="utf-8")
    problem, _ = import_problem({"netdryrun": mod(user / "__init__.py")}, tests_dir, {"NDR_TEST_INSTALLED": "1"})
    assert problem and "different" in problem
    (user / "__init__.py").write_text("a = 1\n", encoding="utf-8")
    assert import_problem({"netdryrun": mod(user / "__init__.py")}, tests_dir, {"NDR_TEST_INSTALLED": "1"})[0] is None


# ---- the release gate's container layer ------------------------------------------------------------------------------
def test_the_container_layer_installs_a_real_package_and_tells_the_guard():
    script = release_gate.CONTAINER_SCRIPT
    lines = script.splitlines()
    pip = [ln for ln in lines if "pip install" in ln]
    assert len(pip) == 1 and "'.[dev]'" in pip[0] and " -e " not in pip[0], pip      # what pip builds, not the source folder
    run = [ln for ln in lines if "-m pytest" in ln]
    assert run == ["NDR_TEST_INSTALLED=1 python -m pytest -q -p no:cacheprovider -rs"], run
    assert lines[lines.index(pip[0]) + 1:lines.index(run[0])] == ["python --version"]   # nothing between install and test
    assert "PYTHONPATH" not in script and "pythonpath" not in script                   # nothing may put /w/src first


# ---- the fast-fix gate runs each tree on its own src -----------------------------------------------------------------
def test_the_fastfix_gate_does_not_pass_a_declared_source_to_its_children(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("fastfix_gate_for_import_guard", ROOT / "scripts" / "fastfix_gate.py")
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)
    monkeypatch.setenv("NDR_TEST_SRC", str(tmp_path))
    monkeypatch.setenv("NDR_TEST_INSTALLED", "1")
    env = gate.child_env(tmp_path / "tree")
    assert "NDR_TEST_SRC" not in env and "NDR_TEST_INSTALLED" not in env
    assert env["PYTHONPATH"] == str(tmp_path / "tree" / "src")


def test_a_declared_src_must_be_a_directory(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    own = tmp_path / "src" / "netdryrun"
    ok = {"netdryrun": mod(own / "__init__.py")}
    problem, _ = import_problem(ok, tests_dir, {"NDR_TEST_SRC": str(tmp_path / "src")})   # not a directory on disk yet
    assert problem and "not a directory" in problem
    own.mkdir(parents=True)
    assert import_problem(ok, tests_dir, {"NDR_TEST_SRC": str(tmp_path / "src")}) == (None, (tmp_path / "src").resolve())
    assert import_problem(ok, tests_dir, {"NDR_TEST_SRC": ""})[0]          # an empty declaration is not the default


def test_installed_mode_checks_where_every_module_comes_from(tmp_path):
    tests_dir = tmp_path / "checkout" / "tests"
    tests_dir.mkdir(parents=True)
    own = tmp_path / "checkout" / "src" / "netdryrun"
    own.mkdir(parents=True)
    (own / "__init__.py").write_text("", encoding="utf-8")
    site = tmp_path / "site" / "netdryrun"
    site.mkdir(parents=True)
    (site / "__init__.py").write_text("", encoding="utf-8")
    env = {"NDR_TEST_INSTALLED": "1"}
    good = {"netdryrun": mod(site / "__init__.py")}
    assert import_problem(good, tests_dir, env) == (None, None)
    bad = {**good, "netdryrun.lab": mod(own / "lab.py")}          # a submodule from the checkout, not the installed copy
    problem, _ = import_problem(bad, tests_dir, env)
    assert problem and "netdryrun.lab" in problem and "outside the installed copy" in problem


def test_a_declared_src_may_be_a_symlink(tmp_path):
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    link = tmp_path / "declared-src"
    link.symlink_to(other, target_is_directory=True)
    p = run_pytest(tree, pythonpath=other, NDR_TEST_SRC=link)
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)
