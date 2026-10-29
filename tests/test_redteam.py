"""The red-team corpus (tests/redteam/): every false pass ever found stays a failing case, forever.

See tests/redteam/README.md for the file format. Each kind runs through real code:
- config: the real CLI's `validate` must exit 2;
- check: the real validator and scheduler, on normalized per-node state, must not pass;
- driver: the real driver and parser, on raw device output, must not pass;
- pinned: the tests that reproduce a runner-level finding must still exist.

It imports nothing from other test files and only long-standing package APIs, so it can run against an
old release to show which cases it fails (each one a false pass that release had):
    PYTHONPATH=<old>/src:tests pytest tests/test_redteam.py
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest
import yaml

from netdryrun import cli
from netdryrun.checks import hold_together, is_post_convergence, run_check, run_round_robin
from netdryrun.config import _validate_check
from netdryrun.drivers import DRIVERS
from netdryrun.drivers.base import BgpNeighbor, BgpPath, Observation, Route
from netdryrun.lab import ExecResult

ROOT = Path(__file__).resolve().parents[1]
# NDR_REDTEAM_DIR points the case tests at another folder: the weekly adversarial run uses it to try its
# candidates without seeing this corpus. A candidate whose test FAILS is a false pass
# (run with -k "is_refused or does_not_pass").
CORPUS = Path(os.environ.get("NDR_REDTEAM_DIR") or Path(__file__).parent / "redteam")
FIXTURES = Path(__file__).parent / "fixtures"
FLOOR = 20   # cases in the corpus when this test was written; it only goes up
KINDS = ("config", "check", "driver", "pinned")


def _cases():
    return [(p, yaml.safe_load(p.read_text(encoding="utf-8"))) for p in sorted(CORPUS.glob("RT-*.yml"))]


CASES = _cases()


def _params(kind):
    return [pytest.param(case, id=p.stem) for p, case in CASES if case["kind"] == kind and not case.get("retired")]


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Lab:
    """A node answering each command with the first output whose needle is in the command line."""

    def __init__(self, rules):
        self.rules, self.nodes = rules, {}

    def exec(self, node, cmd, timeout=60, input=None):
        line = " ".join(cmd)
        for needle, (rc, out, err) in self.rules:
            if needle in line:
                return ExecResult(list(cmd), rc, out, err)
        raise AssertionError(f"unexpected command: {line}")


# ----------------------------------------------------------------------------------------------- kinds

@pytest.mark.parametrize("case", _params("config"))
def test_config_case_is_refused(case, tmp_path, capsys):
    if "file" in case:
        path = ROOT / case["file"]
    else:
        (tmp_path / "topology.clab.yml").write_text(case.get("topology", "name: t\ntopology:\n  nodes: {}\n"))
        path = tmp_path / "netdryrun.yml"
        path.write_text(case["config"])
    assert cli.main(["validate", str(path)]) == 2, f"{case['id']} was accepted: {capsys.readouterr().out}"


class StateDriver:
    def __init__(self, state: dict):
        s = state or {}
        self.neighbors = {a: BgpNeighbor(a, n["state"], dict(n.get("prefixes", {}))) for a, n in (s.get("neighbors") or {}).items()}
        self.route_map = {p: [Route(p, r["protocol"], r["active"]) for r in rs] for p, rs in (s.get("routes") or {}).items()}
        self.paths = {p: [BgpPath(**{"best": False, "as_path": "", "next_hop": None, "local_pref": None, "med": None,
                                     "communities": [], **x}) for x in xs] for p, xs in (s.get("paths") or {}).items()}
        self.pings = {t: tuple(v) for t, v in (s.get("pings") or {}).items()}

    def bgp_neighbors(self, vrf="default"):
        return Observation(dict(self.neighbors), [])

    def routes(self, prefix, vrf="default"):
        return Observation(list(self.route_map.get(prefix, [])), [])

    def bgp_paths(self, prefix, vrf="default"):
        return Observation(list(self.paths.get(prefix, [])), [])

    def ping(self, target, source, count, vrf="default"):
        return Observation(self.pings.get(target, (count, 0)), [{"stderr": ""}])


@pytest.mark.parametrize("case", _params("check"))
def test_check_case_does_not_pass(case):
    clock = FakeClock()
    drivers = {node: StateDriver(s) for node, s in case["state"].items()}
    checks = [_validate_check(i, dict(c), 20) for i, c in enumerate(case["checks"])]
    results = run_round_robin([c for c in checks if not is_post_convergence(c)], drivers,
                              clock=clock, sleep=clock.sleep)
    results += hold_together([c for c in checks if is_post_convergence(c)], drivers, hold=10,
                             clock=clock, sleep=clock.sleep)
    passed = [r.check.name for r in results if r.passed]
    assert not passed, f"{case['id']}: passed: {passed}"


@pytest.mark.parametrize("case", _params("driver"))
def test_driver_case_does_not_pass(case):
    rules = []
    for o in case["outputs"]:
        text = (FIXTURES / o["fixture"]).read_text(encoding="utf-8") if "fixture" in o else o.get("output", "")
        rules.append((o["needle"], (o.get("rc", 0), text, o.get("stderr", ""))))
    check = _validate_check(0, dict(case["check"]), 20)
    driver = DRIVERS[case["driver"]](Lab(rules), check.node)
    clock = FakeClock()
    if is_post_convergence(check):
        [r] = hold_together([check], {check.node: driver}, hold=10, clock=clock, sleep=clock.sleep)
    else:
        r = run_check(check, driver, clock=clock, sleep=clock.sleep)
    assert r.passed is False, f"{case['id']}: passed: {r.detail}"


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


@pytest.mark.parametrize("case", _params("pinned"))
def test_pinned_case_tests_still_exist(case):
    assert case["tests"], case["id"]
    for node_id in case["tests"]:
        file, _, name = node_id.partition("::")
        assert name in _test_functions(ROOT / file), f"{case['id']}: {node_id} no longer exists"


# ------------------------------------------------------------------------------------------- the corpus

def test_every_case_is_well_formed():
    for p, case in CASES:
        assert isinstance(case, dict), p.name
        assert {"id", "title", "found", "fixed_in", "kind"} <= set(case), f"{p.name}: missing fields"
        assert case["kind"] in KINDS, f"{p.name}: unknown kind {case['kind']!r}"
        assert p.name.startswith(case["id"] + "-"), f"{p.name}: file name doesn't start with its id"
    assert len({c["id"] for _, c in CASES}) == len(CASES), "duplicate ids"


def test_ids_are_contiguous_so_no_case_disappears_quietly():
    numbers = sorted(int(re.fullmatch(r"RT-(\d{4})", c["id"]).group(1)) for _, c in CASES)
    assert numbers == list(range(1, len(numbers) + 1)), f"missing case numbers: {sorted(set(range(1, max(numbers) + 1)) - set(numbers))}"
    assert len(CASES) >= FLOOR, f"the corpus shrank below {FLOOR} cases"


def test_every_kind_is_exercised():
    assert {c["kind"] for _, c in CASES} == set(KINDS)
