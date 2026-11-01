"""Golden output of `netdryrun prove`: the exact JSON and console text of a full run, of every error path, and every
generated variant with all its fields. What an agent or a human reads is part of the contract: a changed word is a
reviewed change (rerun with NETDRYRUN_UPDATE_GOLDEN=1 and read the diff), never a silent one.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from netdryrun.config import load as load_config_file
from netdryrun.prove import core
from netdryrun.prove import report as preport
from netdryrun.prove.core import ProveError, prove
from netdryrun.prove.variants import generate, leak_prefixes
from netdryrun.verify.converge import Inconclusive

import prove_helpers as h
from test_prove_variants import CONFIGS, RICH

GOLDEN = Path(__file__).parent / "fixtures" / "prove-golden"
STAMP = "2026-01-01T00:00:00+00:00"
FILTER = "import_filter:edge:CUST-IN permit 10:match ip address prefix-list CUST-IN"


def golden(name: str, text: str) -> None:
    path = GOLDEN / f"{name}.txt"
    if os.environ.get("NETDRYRUN_UPDATE_GOLDEN"):
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.read_text(encoding="utf-8") == text, f"{name}: rerun with NETDRYRUN_UPDATE_GOLDEN=1 and review the diff"


def render(rep) -> str:
    data = preport.to_dict(rep)
    data.pop("netdryrun")
    return preport.console(rep) + "\n----\n" + json.dumps(data, indent=2) + "\n"


def checks():
    return load_config_file(h.FIXTURE / "netdryrun.yml").checks


def variants(cks, base):
    return {v.id: v for v in generate({n: ns.config for n, ns in base.nodes.items()}, h.LINKS, cks, core._counts(base),
                                      core.blocked(base))}


def run(ex, cks=None, **kw):
    return prove(ex, checks() if cks is None else cks, clock=lambda: STAMP, **kw)


def full_states(vs):
    leak = lambda n: h.custleak(cust_extra=leak_prefixes(n))  # noqa: E731
    states = {
        "customer_leak:cust:1": leak(1), "customer_leak:cust:2": leak(2),
        FILTER: h.custleak(edge_filter=None),
        "session_down:cust:10.0.1.1": h.custleak(down=("ce",)),
        "link_down:cust:eth1--edge:eth1": h.custleak(link_down=("ce",)),
        "attribute_drift:cust:ALLOW-ALL permit 10:+set local-preference 50": h.custleak(lp_at={"cust": 50}),
        "default_leak:cust:0.0.0.0/0": h.custleak(cust_extra=["0.0.0.0/0"]),
        "link_subnet_leak:cust:10.0.1.0/30": h.custleak(cust_extra=["10.0.1.0/30"]),
    }
    return {k: h.applied(vs[k], s) for k, s in states.items()}


def test_golden_full_run():
    base = h.custleak()
    vs = variants(checks(), base)
    golden("full-run", render(run(h.FakeExecutor(base, full_states(vs)))))


def test_golden_wide_run():
    """Kinds never generated are named; a run where nothing had an effect has no strength result."""
    base = h.custleak()
    vs = variants(checks(), base)
    states = full_states(vs)
    states["session_down:edge:10.0.2.2"] = h.applied(vs["session_down:edge:10.0.2.2"], h.custleak(down=("eu",)))
    ex = h.FakeExecutor(base, states)
    rep = run(ex, kinds=["session_down", "link_down", "more_specific", "max_prefix_edge"], maximum=2)
    golden("kinds-run", render(rep))
    rep = run(h.FakeExecutor(base, states), kinds=["customer_leak", "default_leak"], maximum=3)
    assert rep.status == "inconclusive" and rep.exit_code == 2   # no variant had an effect
    golden("no-effect-run", render(rep))


def error_cases():
    base = h.custleak()
    cks = checks()
    vs = variants(cks, base)
    good = full_states(vs)
    out = {}

    def ex(states=None, **kw):
        e = h.FakeExecutor(base, good if states is None else states)
        for k, v in kw.items():
            setattr(e, k, v)
        return e
    out["no-checks"] = run(ex(), [])
    out["baseline-fails"] = run(h.FakeExecutor(h.custleak(down=("ce", "eu"))))

    class Unsettled(h.FakeExecutor):
        def snapshot(self):
            return Inconclusive("kept moving", ["edge x"])
    out["baseline-unsettled"] = run(Unsettled(base))
    out["no-variant"] = run(h.FakeExecutor(base, links=[]), kinds=["link_down"])
    out["bad-kind"] = run(ex(), kinds=["nope", "zap"])
    out["bad-max"] = run(ex(), maximum=0)
    e = ex()
    e.results = {FILTER: lambda c: h.evaluate(c, base, started="2000-01-01T00:00:00+00:00")}
    out["stale-variant-run"] = run(e, kinds=["import_filter"], maximum=1)
    e = ex()
    e.results = {FILTER: lambda c: h.evaluate(c[:-1], good[FILTER])}
    out["short-variant-run"] = run(e, kinds=["import_filter"], maximum=1)
    out["not-applied"] = run(ex({}), kinds=["import_filter"], maximum=1)
    other = h.with_config(good[FILTER], "up", adds=("router bgp 65020 > neighbor 10.0.2.1 shutdown",))
    out["other-node-config"] = run(ex({FILTER: other}), kinds=["import_filter"], maximum=1)
    out["link-not-down"] = run(ex({}), kinds=["link_down"], maximum=1)
    sd = "session_down:cust:10.0.1.1"
    out["session-not-down"] = run(ex({sd: h.applied(vs[sd], base)}), kinds=["session_down"], maximum=1)
    out["revert-fails"] = run(ex(fail_revert={FILTER}), kinds=["import_filter"], maximum=1)
    out["apply-fails"] = run(ex(fail_apply={FILTER}), kinds=["import_filter"], maximum=1)
    many = h.custleak(edge_filter=None, cust_extra=leak_prefixes(3))
    out["restore-drift"] = run(ex(after={FILTER: many}), kinds=["import_filter"], maximum=1)
    e = ex()
    e.side_after = {FILTER: {"edge kernel routes": "a route left behind", "up frr pids": "restarted"}}
    out["restore-side-state"] = run(e, kinds=["import_filter"], maximum=1)
    out["restore-unsettled"] = run(ex(after={FILTER: Inconclusive("kept moving", [])}), kinds=["import_filter"],
                                   maximum=1)
    out["variant-unsettled"] = run(ex({FILTER: Inconclusive("never quiet", ["edge y"])}), kinds=["import_filter"],
                                   maximum=1)

    class StillFailing(h.FakeExecutor):
        calls = 0

        def run_checks(self, c):
            out_ = super().run_checks(c)
            StillFailing.calls += 1
            if StillFailing.calls == 3:
                out_ = [replace(r, passed=False, detail="state is idle") for r in out_]
            return out_
    out["fails-after-revert"] = run(StillFailing(base, good), kinds=["import_filter"], maximum=1)

    class Raising(h.FakeExecutor):
        def apply(self, v):
            super().apply(v)
            raise ProveError("the executor refused it")
    out["apply-prove-error"] = run(Raising(base, good), kinds=["import_filter"], maximum=1)
    return out


@pytest.mark.parametrize("name", ["no-checks", "baseline-fails", "baseline-unsettled", "no-variant", "bad-kind",
                                  "bad-max", "stale-variant-run", "short-variant-run", "not-applied",
                                  "other-node-config", "link-not-down", "session-not-down", "revert-fails",
                                  "apply-fails", "restore-drift", "restore-side-state", "restore-unsettled",
                                  "variant-unsettled", "fails-after-revert", "apply-prove-error"])
def test_golden_errors(name):
    rep = error_cases()[name]
    assert rep.status == "error" and rep.exit_code == 2
    golden(f"error-{name}", render(rep))


def test_golden_variants():
    """Every field of every variant generated for three configs (no lab state: --plan's view)."""
    deny = ("ip prefix-list P seq 5 permit 10.0.0.0/8 le 24\nipv6 prefix-list P6 seq 5 permit 2001:db8::/32\n"
            "route-map M deny 5\n match ip address prefix-list P\n match community C\nexit\n"
            "route-map M permit 10\n set community 65000:9\n set as-path prepend 1 1\nexit\n"
            "route-map M6 permit 10\n match ipv6 address prefix-list P6\nexit\n"
            "interface eth1\n ip address 10.0.0.1/30\n ipv6 address 2001:db8:9::1/64\n"
            "router bgp 1\n neighbor 10.0.0.2 remote-as 2\n neighbor 2001:db8:9::2 remote-as 3\n"
            " address-family ipv4 unicast\n  neighbor 10.0.0.2 route-map M in\n exit-address-family\n"
            " address-family ipv6 unicast\n  neighbor 2001:db8:9::2 route-map M6 in\n exit-address-family\n")
    for name, cfgs, links in (("custleak", CONFIGS, h.LINKS), ("rich", {"r1": RICH}, [(("r1", "eth1"), ("x", "eth1"))]),
                              ("deny", {"r": deny}, [(("r", "eth1"), ("z", "eth1"))])):
        vs = generate(cfgs, links)
        golden(f"variants-{name}", json.dumps([asdict(v) for v in vs], indent=1) + "\n")
