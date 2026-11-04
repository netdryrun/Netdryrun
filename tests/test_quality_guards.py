"""Guards G1 and G2 (QUALITY-SYSTEM rule 10, classes E7 and E9; owner 2026-11-04: "don't just fix, learn how to predict
and avoid bugs like these"). Each has a red fixture: the state that slipped through before the guard existed."""
import importlib.util
import json
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate_guards", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate_guards"] = gate
spec.loader.exec_module(gate)


# --- G1 mutation closure (E7) ---------------------------------------------------------------------------------------

def test_every_src_module_is_mutated_or_exempt_with_a_reason():
    assert gate.mutation_closure() == []


def test_faults_outside_the_mutation_set_turns_g1_red():
    """The red fixture: 7532310's VERDICT_MODULES, without faults (outside mutation through Layer 6 rounds 2-9)."""
    before = {k: v for k, v in gate.VERDICT_MODULES.items() if k != "faults"}
    assert gate.mutation_closure(verdict_modules=before) == [
        "src/netdryrun/faults.py: neither mutated (VERDICT_MODULES) nor exempt (MUTATION_EXEMPT, with a reason)"]


def test_a_new_module_nobody_listed_turns_g1_red(tmp_path):
    pkg = tmp_path / "src" / "netdryrun"
    pkg.mkdir(parents=True)
    (pkg / "checks.py").write_text("")
    (pkg / "newproof.py").write_text("")
    assert gate.mutation_closure(tmp_path, {"checks": "src/netdryrun/checks.py"}, {}) == [
        "src/netdryrun/newproof.py: neither mutated (VERDICT_MODULES) nor exempt (MUTATION_EXEMPT, with a reason)"]


def test_g1_refuses_an_exemption_without_a_reason_a_stale_one_and_a_double_listing(tmp_path):
    pkg = tmp_path / "src" / "netdryrun"
    pkg.mkdir(parents=True)
    (pkg / "checks.py").write_text("")
    (pkg / "cli.py").write_text("")
    problems = gate.mutation_closure(tmp_path, {"checks": "src/netdryrun/checks.py"},
                                     {"src/netdryrun/cli.py": " ", "src/netdryrun/checks.py": "x",
                                      "src/netdryrun/gone.py": "removed"})
    assert sorted(problems) == sorted(["src/netdryrun/checks.py: exempt but also mutated",
                                       "src/netdryrun/gone.py: exempt, but no such file",
                                       "src/netdryrun/cli.py: exempt without a reason"])


def test_the_static_layer_carries_g1():
    import inspect
    assert "mutation_closure()" in inspect.getsource(gate.layer_static)


# --- G2 harness preflight (E9) --------------------------------------------------------------------------------------

def test_signals_at_their_defaults_pass_the_preflight():
    if any(signal.getsignal(getattr(signal, n)) == signal.SIG_IGN for n in ("SIGINT", "SIGQUIT") if hasattr(signal, n)):
        pytest.skip("this test process itself was started with a signal ignored")
    assert gate.harness_problem() is None


def test_an_ignored_sigint_fails_the_preflight(monkeypatch):
    real = signal.getsignal
    monkeypatch.setattr(gate.signal, "getsignal", lambda s: signal.SIG_IGN if s == signal.SIGINT else real(s))
    msg = gate.harness_problem()
    assert msg.startswith("SIGINT is ignored in this process") and "os.execvp" in msg


@pytest.mark.skipif(os.name != "posix", reason="POSIX shell trap")
@pytest.mark.parametrize("layer", ["unit", "live"])
def test_the_gate_refuses_to_start_under_trap_ignore_int(layer, tmp_path):
    """The red fixture: `trap '' INT` (what a background job of a non-interactive shell gets), then the layer."""
    probe = ("import importlib.util, sys; s = importlib.util.spec_from_file_location('g', sys.argv[1]); "
             "g = importlib.util.module_from_spec(s); sys.modules['g'] = g; s.loader.exec_module(g); "
             "a = g.argparse.Namespace(version='0.0.0', strict=True); "
             f"lay = g.layer_{layer}(a); c = lay.checks[0]; print(c.id, c.status); print(c.summary)")
    script = tmp_path / "probe.py"
    script.write_text(probe)
    cmd = " ".join(shlex.quote(str(x)) for x in (sys.executable, script, ROOT / "scripts" / "release_gate.py"))
    r = subprocess.run(["bash", "-c", f"trap '' INT; exec {cmd}"],
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    lines = r.stdout.splitlines()
    assert "harness FAIL" in lines, r.stdout + r.stderr
    assert lines[lines.index("harness FAIL") + 1].startswith("SIGINT is ignored in this process")


# --- G3 reference freshness (E8) ------------------------------------------------------------------------------------

def _tree(tmp_path, content="x = 1\n"):
    (tmp_path / "src" / "netdryrun").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "netdryrun" / "checks.py").write_text(content)
    return gate.verdict_tree(tmp_path, {"checks": "src/netdryrun/checks.py"})


def test_the_verdict_tree_follows_the_verdict_code_and_ignores_line_endings(tmp_path):
    a = _tree(tmp_path)
    assert _tree(tmp_path, "x = 1\r\n") == a
    assert _tree(tmp_path, "x = 2\n") != a


def _corpus(tmp_path, tree):
    for path in gate.CORPORA.values():
        f = tmp_path / path
        f.parent.mkdir(parents=True, exist_ok=True)
        env = {"generated": "now"} if tree is None else {"generated": "now", "verdict_tree": tree}
        f.write_text(json.dumps({"environment": env, "cases": []}))


def test_results_without_a_verdict_tree_are_stale_the_7532310_shape(tmp_path, monkeypatch):
    """The red fixture: results recorded before G3 (7532310's v1 and v2) name no verdict tree, so both are stale."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "VERDICT_MODULES", {"checks": "src/netdryrun/checks.py"})
    _tree(tmp_path)
    _corpus(tmp_path, None)
    stale = gate.stale_corpora(tmp_path)
    assert sorted(stale) == ["v1", "v2"] and "unrecorded" in stale["v2"]


def test_results_from_this_verdict_code_are_fresh_and_a_change_makes_them_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "VERDICT_MODULES", {"checks": "src/netdryrun/checks.py"})
    _corpus(tmp_path, _tree(tmp_path))
    assert gate.stale_corpora(tmp_path) == {}
    _tree(tmp_path, "x = 2\n")
    assert sorted(gate.stale_corpora(tmp_path)) == ["v1", "v2"]


def test_the_tag_check_blocks_stale_results(monkeypatch):
    monkeypatch.setattr(gate, "stale_corpora", lambda root=None: {"v2": "ran on unrecorded verdict code"})
    monkeypatch.setattr(gate, "git", lambda *a: "")
    monkeypatch.setattr(gate, "http_status", lambda url: 404)
    layer = gate.Layer("static", gate.argparse.Namespace(strict=True, version="0.0.0"))
    gate.candidate_checks(layer, "0.0.0")
    by_id = {c.id: c for c in layer.checks}
    assert by_id["corpus-v2-tagged-fresh"].status == gate.FAIL and by_id["corpus-v2-tagged-fresh"].severity == gate.BLOCKER
    assert by_id["corpus-v1-tagged-fresh"].status == gate.PASS


def test_the_static_layer_names_stale_corpora_as_a_major():
    import inspect
    src = inspect.getsource(gate.layer_static)
    assert "stale_corpora()" in src and '"corpus-fresh"' in src


def _live(monkeypatch, stale, corpus_ok=True):
    calls = []
    monkeypatch.setattr(gate, "harness_problem", lambda: None)
    monkeypatch.setattr(gate.Layer, "tool", lambda self, name, cmd: self.tools.__setitem__(name, "x") or True)
    monkeypatch.setattr(gate, "clab_containers", lambda: set())
    monkeypatch.setattr(gate, "live_install", lambda live, args: True)
    monkeypatch.setattr(gate, "stale_corpora", lambda root=None: {v: "stale" for v in stale})
    monkeypatch.setattr(gate, "live_examples", lambda live, args: calls.append("examples"))

    def corpora(live, args, only=None, skip=(), fail_fast=False):
        calls.append(("corpora", tuple(only) if only is not None else None, tuple(skip), fail_fast))
        return corpus_ok
    monkeypatch.setattr(gate, "live_corpora", corpora)
    monkeypatch.setattr(gate, "live_chaos", lambda live, args: calls.append("chaos"))
    monkeypatch.setattr(gate, "run", lambda *a, **k: SimpleNamespace(code=0, out="", seconds=0.0))
    monkeypatch.setattr(gate.Layer, "add_proc", lambda self, *a, **k: None)
    args = gate.argparse.Namespace(strict=True, version="0.0.0", skip_corpus=False, allow_running_labs=False, pack=None)
    layer = gate.layer_live(args)
    return calls, layer


def test_a_stale_corpus_runs_first_and_fails_fast(monkeypatch):
    calls, _ = _live(monkeypatch, ["v2"])
    assert calls[0] == ("corpora", ("v2",), (), True) and calls[1] == "examples"
    assert ("corpora", None, ("v2",), False) in calls   # the fresh one later, the stale one not twice


def test_a_stale_corpus_that_differs_stops_the_live_layer(monkeypatch):
    calls, layer = _live(monkeypatch, ["v2"], corpus_ok=False)
    assert calls == [("corpora", ("v2",), (), True)]
    stop = [c for c in layer.checks if c.id == "live-stopped"]
    assert stop and stop[0].status == gate.FAIL


def test_fresh_corpora_run_after_the_examples_as_before(monkeypatch):
    calls, _ = _live(monkeypatch, [])
    assert calls[0] == "examples" and calls[1] == ("corpora", None, (), False)


def test_run_py_expect_names_the_first_verdict_that_differs():
    spec2 = importlib.util.spec_from_file_location("corpus_run_g3", ROOT / "corpus" / "run.py")
    run_py = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(run_py)
    row = {"id": "01-no-change", "strategies": {"ping": {"verdict": "safe"}, "sessions": {"verdict": "safe"},
                                                "netdryrun": {"verdict": "safe"}}}
    committed = {"01-no-change": {"strategies": {"ping": {"verdict": "safe"}, "sessions": {"verdict": "safe"},
                                                 "netdryrun": {"verdict": "error"}}}}
    assert run_py.expect_mismatch(row, committed, set()) == "EXPECT MISMATCH 01-no-change netdryrun: committed error, now safe"
    assert run_py.expect_mismatch(row, committed, {"01-no-change"}) is None   # nondeterministic: never a stop


# --- NOTICE in the wheel and the sdist (Apache-2.0 section 4(d)) ----------------------------------------------------

def test_the_notice_names_the_holder_and_the_trademark():
    assert (ROOT / "NOTICE").read_text(encoding="utf-8") == (
        "Netdryrun\nCopyright 2026 Victor Khen and Netdryrun contributors\n"
        "\"Netdryrun\" is a trademark; see TRADEMARKS.md.\n")


def test_the_package_lists_notice_as_a_license_file():
    # Python 3.10 has no tomllib: the one line, read as written
    assert 'license-files = ["LICENSE", "NOTICE"]' in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()


def _dist(tmp_path, wheel_notice, sdist_notice):
    import io
    import tarfile
    import zipfile
    with zipfile.ZipFile(tmp_path / "netdryrun-0.0.0-py3-none-any.whl", "w") as z:
        z.writestr("netdryrun/__init__.py", "")
        if wheel_notice is not None:
            z.writestr("netdryrun-0.0.0.dist-info/licenses/NOTICE", wheel_notice)
    with tarfile.open(tmp_path / "netdryrun-0.0.0.tar.gz", "w:gz") as t:
        for name, data in (("netdryrun-0.0.0/pyproject.toml", ""), ("netdryrun-0.0.0/NOTICE", sdist_notice)):
            if data is None:
                continue
            info = tarfile.TarInfo(name)
            info.size = len(data.encode())
            t.addfile(info, io.BytesIO(data.encode()))
    return tmp_path


def test_a_wheel_and_sdist_with_the_notice_pass(tmp_path):
    assert gate.notice_problems(_dist(tmp_path, gate.NOTICE_TEXT, gate.NOTICE_TEXT)) == []


def test_a_wheel_without_the_notice_or_with_another_one_fails(tmp_path):
    assert gate.notice_problems(_dist(tmp_path, None, gate.NOTICE_TEXT)) == [
        "netdryrun-0.0.0-py3-none-any.whl: no .dist-info/licenses/NOTICE"]


def test_an_sdist_with_a_different_notice_fails(tmp_path):
    assert gate.notice_problems(_dist(tmp_path, gate.NOTICE_TEXT, "Someone else\n")) == [
        "netdryrun-0.0.0.tar.gz: NOTICE differs from the repository's"]


# --- G3 in the live layer's corpus copy (found by the 0.4.1 live run on 765cdbb, 2026-11-04) -------------------------

def _run_py_verdict_tree(corpus_dir: Path, env: dict | None = None):
    """corpus/run.py's _verdict_tree, run in a fresh interpreter from corpus_dir (a copy or the repo's corpus/)."""
    code = ("import importlib.util, sys; s = importlib.util.spec_from_file_location('ndr_run', sys.argv[1]); "
            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print(repr(m._verdict_tree()))")
    full = {k: v for k, v in os.environ.items() if k != "NDR_VERDICT_TREE"}
    full.update(env or {})
    # run.py imports netdryrun; the pre-push suite finds it through a relative PYTHONPATH=src, so make it absolute
    full["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src")] + [p for p in full.get("PYTHONPATH", "").split(os.pathsep) if p])
    p = subprocess.run([sys.executable, "-c", code, str(corpus_dir / "run.py")], capture_output=True, text=True,
                       env=full)   # the runner's cwd: run.py resolves from its own path, and mutmut finds its config here
    assert p.returncode == 0, p.stderr
    return eval(p.stdout.strip())


def test_run_py_in_the_live_copy_shape_does_not_crash_and_records_no_tree(tmp_path):
    """The red fixture: the live layer copies only corpus/ into a scratch folder; run.py imported scripts/release_gate.py
    from beside it and crashed (FileNotFoundError) before any case ran. With no tree available it records None, which
    G3 reads as stale (fail-closed), never a tree of nothing."""
    import shutil
    copy = tmp_path / "corpus"
    shutil.copytree(ROOT / "corpus", copy, ignore=shutil.ignore_patterns("results", "__pycache__"))
    assert _run_py_verdict_tree(copy) is None


def test_run_py_takes_the_tree_the_gate_hands_it(tmp_path):
    import shutil
    copy = tmp_path / "corpus"
    shutil.copytree(ROOT / "corpus", copy, ignore=shutil.ignore_patterns("results", "__pycache__"))
    assert _run_py_verdict_tree(copy, {"NDR_VERDICT_TREE": gate.verdict_tree()}) == gate.verdict_tree()


def test_run_py_in_the_repo_records_the_gates_tree():
    assert _run_py_verdict_tree(ROOT / "corpus") == gate.verdict_tree()


def test_the_live_corpus_rerun_hands_run_py_the_verdict_tree(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(gate, "run", lambda cmd, **kw: seen.append(kw.get("env") or {}) or gate.Proc(1, "x", 0.0))
    layer = SimpleNamespace(add=lambda *a, **k: None)
    live = SimpleNamespace(layer=layer, work=tmp_path, python="python", assert_clean=lambda *a, **k: None)
    args = SimpleNamespace(skip_corpus=False)
    monkeypatch.setattr(gate, "write_out", lambda *a, **k: None)
    gate.live_corpora(live, args)
    assert len(seen) == 2 and all(e.get("NDR_VERDICT_TREE") == gate.verdict_tree() for e in seen)
