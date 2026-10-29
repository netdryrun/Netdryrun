"""The inconclusive status: the lab never reached a testable state, which says nothing about the change."""
import json
from pathlib import Path

from netdryrun import report
from netdryrun.checks import Result, Unready, inconclusive_reason, run_round_robin
from netdryrun.config import Check, Config
from netdryrun.drivers.base import BgpNeighbor, Observation
from netdryrun.drivers.base import DriverError
from netdryrun.mcp_server import _summary
from netdryrun.runner import RunReport


def check(ctype, node="r1", **params):
    return Check(type=ctype, params={"node": node, **params}, name=f"{node} {ctype}", timeout=30)


def result(c, passed=False, attempts=10, samples_passed=0, unready=0, detail="x"):
    return Result(c, passed, detail, attempts, 30.0, "t", samples_passed=samples_passed, samples_unready=unready)


SESSION = check("bgp_session", neighbor="10.0.0.2", state="established")
PING = check("ping", target="10.0.0.9")
ROUTE = check("route", prefix="10.9.0.0/16")
LEAK_GUARD = check("route", prefix="0.0.0.0/0", present=False)


def test_node_that_never_gave_state_is_inconclusive():
    # every session sample unready (no neighbors at all / CLI not answering); routes and pings on it fail too
    rs = [result(SESSION, unready=10, detail="neighbor 10.0.0.2 not configured (no BGP neighbors at all on this node)"),
          result(ROUTE), result(PING),
          result(LEAK_GUARD, passed=True, attempts=4, samples_passed=4)]  # trivially true: doesn't count
    why = inconclusive_reason(rs)
    assert why and "r1" in why and "no BGP neighbors at all" in why


def test_configured_session_down_is_a_finding():
    """An ASN typo or a wrong neighbor address looks exactly like a slow lab: never inconclusive."""
    rs = [result(SESSION, detail="state is active"), result(ROUTE), result(PING)]
    assert inconclusive_reason(rs) is None


def test_any_positive_sample_passing_anywhere_means_the_lab_worked():
    other = check("bgp_session", node="r2", neighbor="10.0.0.1", state="established")
    rs = [result(SESSION, unready=10), result(other, attempts=10, samples_passed=1, detail="state is idle (flapping)")]
    assert inconclusive_reason(rs) is None
    rs = [result(SESSION, unready=10), result(check("ping", node="r2", target="1.1.1.1"), passed=True, samples_passed=2)]
    assert inconclusive_reason(rs) is None


def test_failed_post_convergence_check_with_state_is_a_finding():
    rs = [result(SESSION, unready=10), result(LEAK_GUARD, attempts=1, detail="unexpectedly present via bgp")]
    assert inconclusive_reason(rs) is None


def test_failure_on_a_ready_node_is_a_finding():
    r2 = check("bgp_session", node="r2", neighbor="10.0.0.1", state="established")
    rs = [result(SESSION, unready=10), result(r2, detail="state is connect")]
    assert inconclusive_reason(rs) is None


def test_partly_unready_samples_are_not_enough():
    rs = [result(SESSION, attempts=10, unready=9, detail="state is active")]
    assert inconclusive_reason(rs) is None


def test_node_without_session_checks_needs_every_sample_unready():
    rs = [result(ROUTE, attempts=5, unready=5, detail="error: Cli not ready")]
    assert inconclusive_reason(rs)
    assert inconclusive_reason([result(ROUTE, attempts=5, unready=4)]) is None
    assert inconclusive_reason([result(PING, attempts=5)]) is None  # 0 replies is a finding


def test_all_passed_is_not_inconclusive():
    assert inconclusive_reason([result(SESSION, passed=True, samples_passed=2)]) is None
    assert inconclusive_reason([]) is None


class Flaky:
    """A driver whose CLI is not ready, or a node with BGP not running yet."""

    def __init__(self, mode):
        self.mode = mode

    def bgp_neighbors(self, vrf="default"):
        if self.mode == "error":
            raise DriverError("`Cli -c show ip bgp summary` failed on ceos1 (rc=1): % CLI not ready")
        if self.mode == "empty":
            return Observation({}, [])
        return Observation({"10.0.0.2": BgpNeighbor("10.0.0.2", "active")}, [])


class Clock:
    t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s or 0.1


def _run(mode):
    clock = Clock()
    c = Check(type="bgp_session", params={"node": "r1", "neighbor": "10.0.0.2", "state": "established"},
              name="s", timeout=9)
    return run_round_robin([c], {"r1": Flaky(mode)}, clock=clock, sleep=clock.sleep)


def test_sample_accounting_from_the_runner():
    for mode in ("error", "empty"):
        [r] = _run(mode)
        assert not r.passed and r.samples_unready == r.attempts > 1 and r.samples_passed == 0
        assert all(h.get("unready") for h in r.history)
        assert inconclusive_reason([r])
    [r] = _run("down")
    assert r.samples_unready == 0 and "unready" not in r.history[0]
    assert inconclusive_reason([r]) is None
    assert isinstance(Unready("x"), str)


def _report(results, error=""):
    cfg = Config(path=Path("netdryrun.yml"), lab=Path("topo.clab.yml"), timeout=30, checks=[r.check for r in results])
    return RunReport(config=cfg, lab_name="t", results=results, error=error)


def test_status_exit_code_and_reports():
    rep = _report([result(SESSION, unready=10, detail="error: % CLI not ready"), result(PING)])
    assert rep.status == "inconclusive" and rep.exit_code == 3
    data = json.loads(report.to_json(rep))
    assert data["status"] == "inconclusive" and "testable state" in data["inconclusive_reason"]
    assert data["schema"] == "netdryrun.report/v1"
    assert "INCONCLUSIVE" in report.summary_line(rep)
    md = report.to_markdown(rep)
    assert "inconclusive" in md and "says nothing about the change" in md
    junit = report.to_junit(rep)
    assert 'failures="0" errors="2"' in junit and "<failure" not in junit
    s = _summary(rep, None)
    assert s["verdict"].startswith("INCONCLUSIVE: the lab did not reach a testable state")
    assert "says nothing about your change" in s["verdict"]


def test_other_statuses_unchanged():
    failed = _report([result(SESSION, detail="state is active")])
    assert failed.status == "failed" and failed.exit_code == 1 and failed.inconclusive_reason is None
    assert json.loads(report.to_json(failed))["inconclusive_reason"] is None
    assert _summary(failed, None)["verdict"] == "DO NOT APPLY THIS CHANGE"
    assert 'failures="1" errors="0"' in report.to_junit(failed)
    err = _report([result(SESSION, unready=10)], error="containerlab deploy failed")
    assert err.status == "error" and err.exit_code == 2 and err.inconclusive_reason is None
    ok = _report([result(SESSION, passed=True, samples_passed=2)])
    assert ok.status == "passed" and ok.exit_code == 0 and _summary(ok, None)["verdict"] == "CHECKS PASSED (only what the checks cover)"


def test_summary_flags_failed_checks_that_never_got_state():
    # A failed run can still be a broken lab (bgpd off on every router, say) when other nodes' route and
    # ping checks read cleanly: the status stays failed, but the agent sees which failures had no state.
    rep = _report([result(SESSION, unready=10, detail="error: bgpd is not running"),
                   result(check("route", node="r2", prefix="10.9.0.0/16"), detail="not active via bgp; seen: nothing")])
    assert rep.status == "failed"
    s = _summary(rep, None)
    assert s["checks"][0]["unready"] is True and "unready" not in s["checks"][1]
    ok = _summary(_report([result(SESSION, passed=True, samples_passed=2)]), None)
    assert "unready" not in ok["checks"][0]


def test_a_ping_with_no_replies_does_not_hide_a_node_whose_routing_state_never_came_up():
    """Agent eval T10: bgpd off on every node. r2 has a route check whose every sample errored and a ping that
    read cleanly (0 replies). A ping can't show that a node gave control-plane state, so r2 never did."""
    r2_route = check("route", node="r2", prefix="192.168.11.0/24", protocol="bgp")
    r2_ping = check("ping", node="r2", target="192.168.11.1")
    rs = [result(SESSION, unready=10, detail="error: bgpd is not running"),
          result(r2_route, unready=10, detail="error: bgpd is not running"),
          result(r2_ping, detail="0/3 replies (need 2)"), result(PING, detail="0/3 replies (need 2)")]
    why = inconclusive_reason(rs)
    assert why and "r1" in why and "r2" in why


def test_a_readable_routing_table_still_makes_a_ping_failure_a_finding():
    r2_route = check("route", node="r2", prefix="192.168.11.0/24")
    r2_ping = check("ping", node="r2", target="192.168.11.1")
    rs = [result(SESSION, unready=10), result(r2_route, detail="seen: nothing"), result(r2_ping, detail="0/3 replies")]
    assert inconclusive_reason(rs) is None
    # partly unready is not "never": one readable sample of the routing table is state
    rs = [result(SESSION, unready=10), result(r2_route, attempts=10, unready=9), result(r2_ping, detail="0/3 replies")]
    assert inconclusive_reason(rs) is None
    # a ping-only node still needs every ping sample unready
    rs = [result(SESSION, unready=10), result(r2_ping, detail="0/3 replies")]
    assert inconclusive_reason(rs) is None
