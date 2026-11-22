"""A corpus case whose run stops with an error (for example case 19's route over the management network) must never be
described on its public page as "every check passed, so Netdryrun called the change safe": an error is neither a pass
nor a block."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


render = _load("corpus_render_errpage", ROOT / "corpus" / "render.py")


def _case(verdict, error=None, failed=()):
    data = json.loads((ROOT / "corpus" / "results" / "results.json").read_text(encoding="utf-8"))
    r = json.loads(json.dumps(data["cases"][0]))
    r["strategies"]["netdryrun"].update(verdict=verdict, error=error, failed_checks=list(failed))
    return r, data["environment"]


def test_an_errored_run_is_never_called_safe_on_its_case_page():
    r, env = _case("error", error="pe1 has a route out over the management network")
    page = render.case_page(r, env, render.load_checks())
    assert "called the change safe" not in page
    assert "every check" not in page
    assert "Nothing was judged: the run stopped before the checks (pe1 has a route out over the management network)" in page
    assert "neither approved nor blocked" in page


def test_an_inconclusive_run_lists_its_checks_as_not_proven_not_failed():
    checks = render.load_checks()
    name = next(iter(checks["netdryrun"]))
    r, env = _case("error", failed=[name])
    page = render.case_page(r, env, checks)
    assert "could not be proven" in page
    assert "failed:" not in page.split("## What Netdryrun flagged", 1)[1].split("##", 1)[0]


def test_a_safe_verdict_still_says_every_check_passed():
    r, env = _case("safe")
    page = render.case_page(r, env, render.load_checks())
    assert "every check in the" in page and "called the change safe" in page
