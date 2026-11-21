"""A test run tests the source it says it tests (tests/import_guard.py).

Many clones share one venv whose editable install points at the clone that ran `pip install -e` last; without the
guard, pytest in another clone imported that clone's netdryrun and passed or failed on the wrong code. Each mode of the
guard has a red case (a decoy or a doctored copy aborts the session) and a green one, run in the shape it is used in:
a subprocess pytest in a temporary checkout."""
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

import import_guard
import import_guard as _ig
from import_guard import children_use


def import_problem(*args):
    """(problem, src) of the guard's (problem, src, mode)"""
    return _ig.import_problem(*args)[:2]


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import release_gate  # noqa: E402

STRIPPED = ("PYTHONPATH", "NDR_TEST_SRC", "NDR_TEST_INSTALLED", "NDR_GUARD_PROOF", "PYTEST_ADDOPTS", "PYTHONPYCACHEPREFIX")
CONFTEST = "from import_guard import pytest_configure, pytest_sessionfinish  # noqa: F401\n"


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


def run_pytest(tree: Path, *, pythonpath=None, args=(), quiet=True, cwd=None, **env_extra) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    env.update({k: str(v) for k, v in env_extra.items()}, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pytest", *(["-q"] if quiet else []), "-p", "no:cacheprovider",
                           "-o", "addopts=", "-c", str(tree / "pyproject.toml"), "--rootdir", str(tree), *args],
                          cwd=cwd or tree, env=env, capture_output=True, text=True, timeout=300)


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
             "    assert 'NDR_GUARD_PROOF' not in env\n"
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


@pytest.mark.parametrize("doctor", ["delete", "extra", "edit", "delete-in-subpackage", "extra-in-subpackage",
                                    "compiled-next-to-a-module", "stale-pyc", "package-data"])
def test_an_installed_copy_that_differs_from_the_checkout_aborts(tmp_path, doctor):
    tree, site = make_checkout(tmp_path), installed_copy(tmp_path)
    pkg = site / "netdryrun"
    if doctor == "delete":
        (pkg / "checks.py").unlink()
    elif doctor == "extra":
        (pkg / "planted.py").write_text("x = 1\n", encoding="utf-8")
    elif doctor == "delete-in-subpackage":
        (pkg / "drivers" / "frr.py").unlink()
    elif doctor == "extra-in-subpackage":
        (pkg / "drivers" / "planted.py").write_text("x = 1\n", encoding="utf-8")
    elif doctor == "compiled-next-to-a-module":
        (pkg / "checks.so").write_bytes(b"\x7fELF")
    elif doctor == "stale-pyc":
        (pkg / "checks.pyc").write_bytes(b"\x00")
    elif doctor == "package-data":
        (pkg / "extra.json").write_text("{}", encoding="utf-8")
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


@pytest.mark.parametrize("value", ["", "0", "true", "yes", "11", " 1", "1 ", "1\n"])
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
    assert lines[0] == "set -e"                                                       # a failed step ends the script
    pip = [ln for ln in lines if "pip install" in ln]
    assert len(pip) == 1 and "'.[dev]'" in pip[0] and " -e " not in pip[0], pip      # what pip builds, not the source folder
    assert pip[0].startswith("cd /w && "), pip                                         # the copy, not the read-only mount
    run = [ln for ln in lines if "-m pytest" in ln]
    assert run == ["PYTHONPYCACHEPREFIX=$(mktemp -d) PYTEST_ADDOPTS= NDR_GUARD_PROOF=/tmp/ndr-guard-proof "
                   "NDR_TEST_INSTALLED=1 python -m pytest -q -p no:cacheprovider -rs"], run   # pip's .pyc files are not read
    i = lines.index(run[0])
    assert lines[lines.index(pip[0]) + 1:i] == ["python --version", "rm -f /tmp/ndr-guard-proof"]   # nothing between
    assert len(lines) == i + 2 and lines[i + 1].startswith("grep -q ") and '"installed"' in lines[i + 1]   # the proof
    assert script.count("PYTEST_ADDOPTS") == 1                  # only the reset on the run line; none exported before it
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


# ---- the header and the proof file -------------------------------------------------------------------------------------
HEADER_CONFTEST = "from import_guard import pytest_configure, pytest_report_header, pytest_sessionfinish  # noqa: F401\n"


def test_the_header_names_the_mode_and_the_source(tmp_path):
    tree = make_checkout(tmp_path)
    (tree / "tests" / "conftest.py").write_text(HEADER_CONFTEST, encoding="utf-8")
    p = run_pytest(tree, pythonpath=tree / "src", quiet=False)
    assert p.returncode == 0, out(p)
    assert f"ndr-import-guard: mode=default source={(ROOT / 'src').resolve()}" in p.stdout, out(p)
    other = decoy(tmp_path)
    tree2 = make_checkout(tmp_path / "two", src="empty")
    (tree2 / "tests" / "conftest.py").write_text(HEADER_CONFTEST, encoding="utf-8")
    p = run_pytest(tree2, pythonpath=other, quiet=False, NDR_TEST_SRC=other)
    assert f"ndr-import-guard: mode=declared source={other.resolve()}" in p.stdout, out(p)
    p = run_pytest(tree, pythonpath=installed_copy(tmp_path), quiet=False, NDR_TEST_INSTALLED="1")
    assert "ndr-import-guard: mode=installed source=" in p.stdout, out(p)


def test_the_header_says_so_when_the_guard_did_not_run():
    class Cfg:
        pass
    assert import_guard.pytest_report_header(Cfg()) == "ndr-import-guard: DID NOT RUN"
    cfg = Cfg()
    cfg.ndr_import_guard = ("default", "/x/src")
    assert import_guard.pytest_report_header(cfg) == "ndr-import-guard: mode=default source=/x/src"


def test_a_passing_guard_writes_the_proof_and_drops_the_variable(tmp_path):
    proof = tmp_path / "proof.json"
    probe = "import os\n\ndef test_the_variable_is_gone():\n    assert 'NDR_GUARD_PROOF' not in os.environ\n"
    tree = make_checkout(tmp_path, test=probe)
    p = run_pytest(tree, pythonpath=tree / "src", NDR_GUARD_PROOF=proof)
    assert p.returncode == 0, out(p)
    got = json.loads(proof.read_text(encoding="utf-8"))
    assert got == {"mode": "default", "source": str((ROOT / "src").resolve())}


def test_the_proof_is_created_exclusively_so_a_nested_run_cannot_replace_it(tmp_path):
    proof = tmp_path / "proof.json"
    proof.write_text("first", encoding="utf-8")
    tree = make_checkout(tmp_path)
    assert run_pytest(tree, pythonpath=tree / "src", NDR_GUARD_PROOF=proof).returncode == 0
    assert proof.read_text(encoding="utf-8") == "first"


def test_an_aborted_guard_writes_no_proof(tmp_path):
    proof = tmp_path / "proof.json"
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    aborted(run_pytest(tree, pythonpath=other, NDR_GUARD_PROOF=proof))
    assert not proof.exists()


@pytest.mark.parametrize("bypass", [["--noconftest"], ["--confcutdir", "tests/sub"], ["--confcutdir=tests/sub"]])
def test_a_run_that_skips_conftest_leaves_no_proof(tmp_path, bypass):
    """What the gates catch: the run passes on the wrong code, nothing aborts, and the guard never ran."""
    proof = tmp_path / "proof.json"
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    (tree / "tests" / "sub").mkdir()
    p = run_pytest(tree, pythonpath=other, NDR_GUARD_PROOF=proof, args=bypass, quiet=False)
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)
    assert not proof.exists()
    assert "ndr-import-guard" not in p.stdout


def test_pytest_addopts_noconftest_skips_the_guard_and_leaves_no_proof(tmp_path):
    proof = tmp_path / "proof.json"
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    p = run_pytest(tree, pythonpath=other, NDR_GUARD_PROOF=proof, PYTEST_ADDOPTS="--noconftest")
    assert p.returncode == 0 and not proof.exists(), out(p)


def test_an_import_that_exits_aborts_too(tmp_path):
    tree, other = make_checkout(tmp_path, src="empty"), decoy(tmp_path)
    (other / "netdryrun" / "__init__.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    aborted(run_pytest(tree, pythonpath=other), "could not verify")


def test_a_relative_pythonpath_is_not_listed_twice(tmp_path, monkeypatch):
    src = tmp_path / "checkout" / "src"
    src.mkdir(parents=True)
    monkeypatch.chdir(src.parent)
    assert children_use(src.resolve(), {"PYTHONPATH": "src"}).split(os.pathsep) == [str(src.resolve())]


def test_a_run_with_a_relative_pythonpath_passes_and_children_get_the_absolute_src(tmp_path):
    probe = ("import os\n\ndef test_children_see_one_absolute_src():\n"
             "    parts = [p for p in os.environ['PYTHONPATH'].split(os.pathsep) if p]\n"
             "    assert parts[0] == os.path.realpath(os.path.join(os.getcwd(), 'src')) and parts.count(parts[0]) == 1\n"
             "    assert 'src' not in parts\n")
    tree = make_checkout(tmp_path, test=probe)
    p = run_pytest(tree, pythonpath="src")
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)


def test_every_loaded_module_must_be_a_py_file(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    own = tmp_path / "src" / "netdryrun"
    own.mkdir(parents=True)
    mods = {"netdryrun": mod(own / "__init__.py"), "netdryrun.fast": mod(own / "fast.cpython-312-x86_64-linux-gnu.so")}
    problem, src = import_problem(mods, tests_dir, {})
    assert problem and "not loaded from .py files" in problem and src is None
    mods = {"netdryrun": mod(own / "__init__.py"), "netdryrun.old": mod(own / "old.pyc")}
    assert import_problem(mods, tests_dir, {})[0]


def test_bytecode_caches_are_not_part_of_the_comparison(tmp_path):
    tree, site = make_checkout(tmp_path), installed_copy(tmp_path)
    (site / "netdryrun" / "__pycache__").mkdir()
    (site / "netdryrun" / "__pycache__" / "checks.cpython-312.pyc").write_bytes(b"\x00")
    p = run_pytest(tree, pythonpath=site, NDR_TEST_INSTALLED="1")
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)


# ---- the red-team procedure on an old release (FX-0.4.3-redteam-old-release-procedure-broken) ------------------------
def test_the_red_team_procedure_on_v0_4_1_reports_real_failures_not_errors(tmp_path):
    if shutil.which("git") is None or shutil.which("tar") is None:
        pytest.skip("needs git and tar")
    if subprocess.run(["git", "rev-parse", "--verify", "-q", "v0.4.1^{commit}"], cwd=ROOT,
                      capture_output=True).returncode != 0:
        pytest.skip("the v0.4.1 tag is not in this clone")
    old = tmp_path / "old"
    old.mkdir()
    arc = subprocess.run(["git", "archive", "v0.4.1", "src"], cwd=ROOT, capture_output=True)
    assert arc.returncode == 0
    subprocess.run(["tar", "-x", "-C", str(old)], input=arc.stdout, check=True)
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    env.update(NDR_TEST_SRC=str(old / "src"), PYTHONPATH=f"{old / 'src'}{os.pathsep}{ROOT / 'tests'}",
               PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=", "tests/test_redteam.py"]
    p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    text = out(p)
    assert f"ndr-import-guard: mode=declared source={(old / 'src').resolve()}" in text, text[-1500:]
    last = text.strip().splitlines()[-1]
    assert p.returncode == 1 and " failed" in last and " error" not in last, text[-1500:]    # real false passes
    del env["NDR_TEST_SRC"]
    q = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert q.returncode == 4 and "passed" not in out(q), out(q)[-800:]     # undeclared it aborts, never reads as clean


# ---- the shape mutmut runs in (L-13) --------------------------------------------------------------------------------
def test_the_guard_passes_in_the_shape_mutmut_copies_the_tree_into(tmp_path):
    """mutmut copies src and tests into mutants/ and runs pytest there: tests/ beside src/, with the checkout's own
    src elsewhere. Default mode must accept the copy and refuse the original's src."""
    mutants = tmp_path / "mutants"
    shutil.copytree(ROOT / "src", mutants / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (mutants / "tests").mkdir()
    shutil.copy(ROOT / "tests" / "import_guard.py", mutants / "tests" / "import_guard.py")
    (mutants / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    here = str((mutants / "src").resolve())
    (mutants / "tests" / "test_ok.py").write_text(
        "import netdryrun, pathlib\n\ndef test_it_is_the_copy():\n"
        f"    assert pathlib.Path(netdryrun.__file__).resolve().is_relative_to(pathlib.Path({here!r}))\n", encoding="utf-8")
    (mutants / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8")
    p = run_pytest(mutants, pythonpath=mutants / "src")
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)
    aborted(run_pytest(mutants, pythonpath=ROOT / "src"), (mutants / "src" / "netdryrun").resolve())


# ---- the gates read the proof ------------------------------------------------------------------------------------------
def _load_fastfix():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fastfix_gate_for_import_guard", ROOT / "scripts" / "fastfix_gate.py")
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)
    return gate


def test_the_release_gate_scrubs_what_decides_which_code_or_whether_the_guard_loads(monkeypatch):
    for k in ("NDR_TEST_SRC", "NDR_TEST_INSTALLED", "NDR_GUARD_PROOF", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("KEEP_ME", "1")
    env = release_gate.clean_test_env()
    assert env["KEEP_ME"] == "1"
    assert not {"NDR_TEST_SRC", "NDR_TEST_INSTALLED", "NDR_GUARD_PROOF", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"} & set(env)


def test_the_release_gate_wants_the_right_mode_on_the_right_source(tmp_path):
    proof = tmp_path / "p.json"
    assert "no proof" in (release_gate.guard_proof_problem(proof, "default", tmp_path) or "") or \
        "left no proof" in (release_gate.guard_proof_problem(proof, "default", tmp_path) or "")
    proof.write_text(json.dumps({"mode": "default", "source": str(tmp_path)}), encoding="utf-8")
    assert release_gate.guard_proof_problem(proof, "default", tmp_path) is None
    assert release_gate.guard_proof_problem(proof, "installed", tmp_path)                    # wrong mode
    assert release_gate.guard_proof_problem(proof, "default", tmp_path / "other")            # wrong source
    proof.write_text("[]", encoding="utf-8")
    assert release_gate.guard_proof_problem(proof, "default", tmp_path)                      # not a proof


def test_the_fastfix_gate_refuses_a_run_without_proof_and_accepts_one_with(tmp_path):
    gate = _load_fastfix()
    tree = tmp_path / "tree"
    (tree / "src").mkdir(parents=True)
    done = subprocess.CompletedProcess([], 0, "", "")
    proof = tmp_path / "p.json"
    with pytest.raises(gate.GateError, match="left no proof"):
        gate.check_guard_proof(tree, proof, done)
    proof.write_text(json.dumps({"mode": "declared", "source": str(tree / "src")}), encoding="utf-8")
    with pytest.raises(gate.GateError, match="mode 'declared'"):
        gate.check_guard_proof(tree, proof, done)
    proof.write_text(json.dumps({"mode": "default", "source": str(tmp_path / "elsewhere")}), encoding="utf-8")
    with pytest.raises(gate.GateError, match="not on this tree's own src"):
        gate.check_guard_proof(tree, proof, done)
    proof.write_text(json.dumps({"mode": "default", "source": str(tree / "src")}), encoding="utf-8")
    gate.check_guard_proof(tree, proof, done)


def test_the_fastfix_gate_drops_the_guard_variables_for_its_children(tmp_path, monkeypatch):
    gate = _load_fastfix()
    for k in ("NDR_TEST_SRC", "NDR_TEST_INSTALLED", "NDR_GUARD_PROOF"):
        monkeypatch.setenv(k, "x")
    env = gate.child_env(tmp_path / "tree")
    assert not {"NDR_TEST_SRC", "NDR_TEST_INSTALLED", "NDR_GUARD_PROOF"} & set(env)


def test_the_fastfix_gate_refuses_a_tree_whose_run_skips_the_guard(tmp_path):
    """End to end: a tree with the guard whose pytest run skips conftest (a conftest that no longer loads it)."""
    gate = _load_fastfix()
    tree = make_checkout(tmp_path)
    (tree / "tests" / "conftest.py").write_text("", encoding="utf-8")                    # the guard is never loaded
    with pytest.raises(gate.GateError, match="left no proof"):
        gate.run_pytest(tree, ["tests/test_ok.py"], sys.executable, tmp_path / "work")
    (tree / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    run = gate.run_pytest(tree, ["tests/test_ok.py"], sys.executable, tmp_path / "work2")
    assert run.count("passed") == 1


# ---- the release gate's unit layer needs the proof, and a run without it is a FAIL ------------------------------------
def _unit_layer(monkeypatch, tmp_path, write_proof):
    import argparse
    seen = {}

    def fake_run(cmd, **kw):
        cmd = [str(c) for c in cmd]
        if "-m" in cmd and "pytest" in cmd:
            seen["env"] = kw.get("env")
            if write_proof is not None:
                Path(kw["env"]["NDR_GUARD_PROOF"]).write_text(json.dumps(write_proof), encoding="utf-8")
            return release_gate.Proc(0, "5 passed in 1.00s", 1.0)
        return release_gate.Proc(0, "3.11.0", 0.0)

    monkeypatch.setattr(release_gate, "run", fake_run)
    monkeypatch.setattr(release_gate, "make_venv", lambda *a: release_gate.Proc(0, "", 0.0))
    monkeypatch.setattr(release_gate, "pip_install", lambda *a: release_gate.Proc(0, "", 0.0))
    for k in ("NDR_TEST_SRC", "NDR_TEST_INSTALLED", "PYTEST_ADDOPTS"):
        monkeypatch.setenv(k, "x")
    layer = release_gate.Layer("unit", argparse.Namespace(strict=False, version="x"))
    release_gate.unit_on_python(layer, "3.11", None, tmp_path)
    return layer.checks[-1], seen["env"]


def test_the_unit_layer_passes_only_with_the_guards_proof_and_a_scrubbed_env(monkeypatch, tmp_path):
    good = {"mode": "default", "source": str(ROOT / "src")}
    check, env = _unit_layer(monkeypatch, tmp_path, good)
    assert check.status == release_gate.PASS, check
    assert not {"NDR_TEST_SRC", "NDR_TEST_INSTALLED", "PYTEST_ADDOPTS"} & set(env)
    assert env["NDR_GUARD_PROOF"].endswith("guard-proof-3.11.json")


@pytest.mark.parametrize("proof", [None, {"mode": "declared", "source": str(ROOT / "src")},
                                   {"mode": "default", "source": "/elsewhere/src"}])
def test_the_unit_layer_fails_a_run_without_the_right_proof_even_if_pytest_exited_0(monkeypatch, tmp_path, proof):
    check, _ = _unit_layer(monkeypatch, tmp_path, proof)
    assert check.status == release_gate.FAIL, check
    assert "import guard" in check.summary


# ---- round 4: files that are not .py, the session-finish check, stale proofs, bytecode, the conftest tolerance --------
def tiny_checkout(tmp_path, test, *, extra_src=()):
    """A checkout with a two-module netdryrun (small, so planting a file in it is cheap), the real guard."""
    tree = make_checkout(tmp_path, src="empty", test=test)
    pkg = tree / "src" / "netdryrun"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "checks.py").write_text("VALUE = 1\n", encoding="utf-8")
    for rel, data in extra_src:
        f = pkg / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    return tree


@pytest.mark.parametrize("planted", [("checks.cpython-310-x86_64-linux-gnu.so", b"\x7fELF"), ("checks.pyc", b"\x00"),
                                     ("data.json", b"{}"), ("sub/helper.so", b"\x7fELF")])
@pytest.mark.parametrize("mode", ["default", "declared"])
def test_a_file_that_is_not_py_in_the_verified_src_aborts_before_any_test_runs(tmp_path, planted, mode):
    """The compiled module is not loaded when the guard checks (only the package is), and python prefers it to the .py
    beside it: the guard has to look at the files, not only at what is loaded."""
    tree = tiny_checkout(tmp_path, "import netdryrun.checks\n\ndef test_ok():\n    assert netdryrun.checks.VALUE == 1\n",
                         extra_src=[planted])
    extra = {"NDR_TEST_SRC": tree / "src"} if mode == "declared" else {}
    p = run_pytest(tree, pythonpath=tree / "src", **extra)
    aborted(p, "not .py", planted[0].split("/")[-1])


def test_bytecode_caches_in_the_verified_src_are_fine(tmp_path):
    tree = tiny_checkout(tmp_path, "def test_ok():\n    assert True\n", extra_src=[("__pycache__/checks.cpython-310.pyc", b"\x00")])
    p = run_pytest(tree, pythonpath=tree / "src")
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)


def test_a_module_imported_during_the_session_from_elsewhere_fails_the_session_and_leaves_no_proof(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "late.py").write_text("x = 1\n", encoding="utf-8")
    probe = ("import sys, types\n\ndef test_a_module_arrives_late():\n"
             "    m = types.ModuleType('netdryrun.late')\n"
             f"    m.__file__ = {str(elsewhere / 'late.py')!r}\n"
             "    sys.modules['netdryrun.late'] = m\n")
    tree, proof = tiny_checkout(tmp_path, probe), tmp_path / "proof.json"
    p = run_pytest(tree, pythonpath=tree / "src", NDR_GUARD_PROOF=proof)
    assert p.returncode == 4, out(p)
    assert "1 passed" in p.stdout and "netdryrun.late" in p.stderr, out(p)         # the test ran; the session still fails
    assert not proof.exists()


def test_a_clean_session_writes_the_proof_only_at_the_end(tmp_path):
    proof = tmp_path / "proof.json"
    probe = f"import os\n\ndef test_no_proof_yet():\n    assert not os.path.exists({str(proof)!r})\n"
    tree = tiny_checkout(tmp_path, probe)
    p = run_pytest(tree, pythonpath=tree / "src", NDR_GUARD_PROOF=proof)
    assert p.returncode == 0 and proof.is_file(), out(p)
    assert json.loads(proof.read_text(encoding="utf-8"))["mode"] == "default"


def test_the_session_finish_check_is_skipped_when_the_guard_did_not_run():
    class Cfg:
        pass

    class Session:
        config = Cfg()
        exitstatus = 0
    s = Session()
    import_guard.pytest_sessionfinish(s, 0)
    assert s.exitstatus == 0


# ---- non-.py files in installed mode, compared by content (G7) --------------------------------------------------------
def test_a_data_file_that_differs_in_content_is_caught_in_installed_mode(tmp_path):
    tests_dir = tmp_path / "checkout" / "tests"
    tests_dir.mkdir(parents=True)
    own = tmp_path / "checkout" / "src" / "netdryrun"
    site = tmp_path / "site" / "netdryrun"
    for d, data in ((own, "1"), (site, "2")):
        d.mkdir(parents=True)
        (d / "__init__.py").write_text("", encoding="utf-8")
        (d / "table.json").write_text(data, encoding="utf-8")
    mods = {"netdryrun": mod(site / "__init__.py")}
    problem, _ = import_problem(mods, tests_dir, {"NDR_TEST_INSTALLED": "1"})
    assert problem and "table.json" in problem and "different" in problem
    (site / "table.json").write_text("1", encoding="utf-8")
    assert import_problem(mods, tests_dir, {"NDR_TEST_INSTALLED": "1"})[0] is None


# ---- a planted .pyc in the installed package (the container script's empty bytecode cache) ----------------------------
def _poison_pyc(pkg: Path, monkeypatch) -> None:
    import importlib.util
    from importlib import _bootstrap_external as be
    monkeypatch.setattr(sys, "pycache_prefix", None)      # this session's own prefix (the container's) is not the target's
    src = pkg / "checks.py"
    st = src.stat()
    code = compile(src.read_text(encoding="utf-8") + "\nPOISON = 1\n", str(src), "exec")
    pyc = Path(importlib.util.cache_from_source(str(src)))
    pyc.parent.mkdir(exist_ok=True)
    pyc.write_bytes(be._code_to_timestamp_pyc(code, int(st.st_mtime), st.st_size))


def test_a_planted_pyc_runs_in_place_of_the_compared_source_unless_the_bytecode_cache_is_empty(tmp_path, monkeypatch):
    """The bytes of every file but __pycache__ are compared, so a .pyc with the source's mtime and size gets through the
    guard; PYTHONPYCACHEPREFIX (set by the container script) makes python ignore it."""
    site = installed_copy(tmp_path)
    _poison_pyc(site / "netdryrun", monkeypatch)
    probe = "import netdryrun.checks as c\n\ndef test_poison():\n    assert hasattr(c, 'POISON') is {}\n"
    tree = make_checkout(tmp_path / "a", test=probe.format("True"))
    p = run_pytest(tree, pythonpath=site, NDR_TEST_INSTALLED="1")
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)            # the attack is real without the prefix
    empty = tmp_path / "empty-cache"
    empty.mkdir()
    tree = make_checkout(tmp_path / "b", test=probe.format("False"))
    p = run_pytest(tree, pythonpath=site, NDR_TEST_INSTALLED="1", PYTHONPYCACHEPREFIX=empty)
    assert p.returncode == 0 and "1 passed" in p.stdout, out(p)


# ---- a stale proof must not stand in for a run (R1, F1) ----------------------------------------------------------------
def test_the_release_gate_deletes_a_proof_left_from_an_earlier_run(monkeypatch, tmp_path):
    (tmp_path / "guard-proof-3.11.json").write_text(
        json.dumps({"mode": "default", "source": str(ROOT / "src")}), encoding="utf-8")
    check, _ = _unit_layer(monkeypatch, tmp_path, None)          # this run writes none (the guard did not run)
    assert check.status == release_gate.FAIL, check


def test_the_fastfix_gate_deletes_a_proof_left_from_an_earlier_run(tmp_path):
    gate = _load_fastfix()
    tree = make_checkout(tmp_path)
    (tree / "tests" / "conftest.py").write_text("", encoding="utf-8")                    # the guard is never loaded
    work = tmp_path / "work"
    work.mkdir()
    (work / "guard-proof-junit-0.json").write_text(
        json.dumps({"mode": "default", "source": str(tree / "src")}), encoding="utf-8")
    with pytest.raises(gate.GateError, match="left no proof"):
        gate.run_pytest(tree, ["tests/test_ok.py"], sys.executable, work)


# ---- the mutation layer's environment (R7) -----------------------------------------------------------------------------
def test_the_mutation_layer_runs_mutmut_with_a_scrubbed_environment(monkeypatch, tmp_path):
    import argparse
    seen = []

    def fake_run(cmd, **kw):
        cmd = [str(c) for c in cmd]
        if "run" in cmd and "mutmut" in " ".join(cmd):
            seen.append(kw.get("env"))
            return release_gate.Proc(1, "failed to collect stats", 0.0)
        return release_gate.Proc(0, "mutmut 3.8", 0.0)

    monkeypatch.setattr(release_gate, "run", fake_run)
    monkeypatch.setattr(release_gate, "ROOT", tmp_path)
    for k in ("NDR_TEST_SRC", "NDR_TEST_INSTALLED", "NDR_GUARD_PROOF", "PYTEST_ADDOPTS"):
        monkeypatch.setenv(k, "x")
    args = argparse.Namespace(strict=False, version="x", modules=["checks"], mutation_timeout=5, jobs=1,
                              pin_accepted=False)
    release_gate.layer_mutation(args)
    assert len(seen) == 1 and seen[0] is not None
    assert not {"NDR_TEST_SRC", "NDR_TEST_INSTALLED", "NDR_GUARD_PROOF", "PYTEST_ADDOPTS"} & set(seen[0])


# ---- the conftest's tolerance of an old release (T1, T2) -----------------------------------------------------------------
import conftest as ct  # noqa: E402  (tests/conftest.py)


def _raising(exc):
    def f(name, *a, **k):
        raise exc
    return f


def test_a_release_without_mgmt_is_tolerated_and_nothing_else_is(monkeypatch):
    monkeypatch.setattr(ct.importlib, "import_module", _raising(ModuleNotFoundError("no mgmt", name="netdryrun.mgmt")))
    assert ct.load_mgmt() is None
    for exc in (ModuleNotFoundError("x", name="yaml_missing"), ImportError("cannot import name"),
                ImportError("x", name="netdryrun"), ValueError("boom"), SyntaxError("bad")):
        monkeypatch.setattr(ct.importlib, "import_module", _raising(exc))
        with pytest.raises(type(exc)):
            ct.load_mgmt()


def test_the_real_mgmt_gets_no_readiness_wait():
    from netdryrun import mgmt
    assert ct.load_mgmt() is mgmt and mgmt.READY_BUDGET == 0.0


def test_a_renamed_ready_budget_fails_instead_of_being_skipped(monkeypatch):
    ns = types.SimpleNamespace()
    with pytest.raises(AttributeError):
        ct.disable_ready_wait(monkeypatch, load=lambda: ns)
    ns.READY_BUDGET = 5.0
    ct.disable_ready_wait(monkeypatch, load=lambda: ns)
    assert ns.READY_BUDGET == 0.0
    ct.disable_ready_wait(monkeypatch, load=lambda: None)          # an old release: nothing to disable
