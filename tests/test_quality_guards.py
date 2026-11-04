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
