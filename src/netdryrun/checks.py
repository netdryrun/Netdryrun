"""Run behavioral checks.

Positive checks poll until they pass (networks need time to converge), then must pass again on
consecutive samples so a flapping session can't pass on one lucky sample. Negative checks run
after convergence and must hold for a whole window.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from .config import BGP_ATTRIBUTES, Check, community_name
from .drivers import Driver

REACH_WINDOW = 30.0  # seconds for post-convergence prefix counts to reach their range


@dataclass
class Result:
    check: Check
    passed: bool
    detail: str
    attempts: int
    duration: float
    started: str
    evidence: list[dict] = field(default_factory=list)  # raw outputs from the final attempt
    history: list[dict] = field(default_factory=list)   # every sample: time offset, pass/fail, detail
    samples_passed: int = 0    # passing samples over the whole check (history keeps only the last 50)
    samples_unready: int = 0   # failing samples where the node gave no usable state (see Unready)


class Unready(str):
    """The detail of a failing sample that means "no usable state yet", not "the network is wrong": the
    state command failed or its output could not be read, or BGP had no neighbors at all on the node.
    It is how a lab that never came up (inconclusive) is told apart from a change that broke it (failed)."""


def _not_configured(neighbor: str, seen: dict) -> str:
    if not seen:
        return Unready(f"neighbor {neighbor} not configured (no BGP neighbors at all on this node)")
    return f"neighbor {neighbor} not configured (seen: {', '.join(seen)})"


def _bgp_session(d: Driver, p: dict) -> tuple[bool, str, list]:
    obs = d.bgp_neighbors(p.get("vrf", "default"))
    n = obs.value.get(p["neighbor"])
    if n is None:
        return False, _not_configured(p["neighbor"], obs.value), obs.evidence
    if p["state"] == "down":
        return n.state != "established", f"state is {n.state}", obs.evidence
    return n.state == p["state"], f"state is {n.state}", obs.evidence


def _bgp_prefixes(d: Driver, p: dict) -> tuple[bool, str, list]:
    obs = d.bgp_neighbors(p.get("vrf", "default"))
    n = obs.value.get(p["neighbor"])
    if n is None:
        return False, _not_configured(p["neighbor"], obs.value), obs.evidence
    if n.state != "established":
        # counters reset to 0 when a session drops (e.g. a max-prefix trip), so a count
        # from a down session would satisfy "max" by accident
        return False, f"session is {n.state}; prefix counts are only meaningful when established", obs.evidence
    afi = p.get("afi", "ipv4-unicast")
    count = n.prefixes.get(afi, 0)  # established but the family reports nothing: zero prefixes
    if "exact" in p:
        ok = count == p["exact"]
    else:
        ok = count >= p.get("min", 0) and ("max" not in p or count <= p["max"])
    return ok, f"{count} {afi} prefixes accepted", obs.evidence


def _route(d: Driver, p: dict) -> tuple[bool, str, list]:
    obs = d.routes(p["prefix"], p.get("vrf", "default"))
    want_proto = str(p.get("protocol", "")).lower()
    matching = [r for r in obs.value if not want_proto or r.protocol == want_proto]
    active = [r for r in matching if r.active]
    # `is not False`, the same test is_post_convergence uses, so the evaluator and the scheduler can never
    # disagree on what a check means (config validation already insists on a real boolean)
    if p.get("present", True) is not False:
        if active:
            return True, f"active via {active[0].protocol}", obs.evidence
        if p.get("active", True) is False and matching:
            # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
            return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
        return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
    # Absent means not in the routing table at all: a received-but-not-selected route
    # (e.g. a leaked default losing to a local one) is still a leak.
    if matching:
        r = matching[0]
        return False, f"unexpectedly present via {r.protocol}{'' if r.active else ' (not selected)'}", obs.evidence
    return True, "absent", obs.evidence


# "The destination is unreachable" is a ping result, not a ping that did not run: with no route at all,
# iputils prints "connect: Network is unreachable" (busybox "sendto: Network unreachable") and no statistics.
_UNREACHABLE = re.compile(r"network (is )?unreachable|no route to host|destination (host |net )?unreachable", re.I)


def _ping(d: Driver, p: dict) -> tuple[bool, str, list]:
    count = int(p.get("count", 3))
    obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
    sent, received = obs.value
    if sent == 0:
        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
        m = _UNREACHABLE.search(text)
        if m:
            why = f"0/{count} replies (destination unreachable: {m.group(0)})"
            if p.get("expect", "success") == "failure":
                return True, why, obs.evidence
            return False, why, obs.evidence
    if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
        return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
    if p.get("expect", "success") == "success":
        need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
        return received >= need, f"{received}/{sent} replies (need {need})", obs.evidence
    return received == 0, f"{received}/{sent} replies", obs.evidence


def _opt(v) -> str:
    return "not set" if v is None else str(v)


def _describe_path(path) -> str:
    comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
    as_path = "?" if path.as_path is None else f"'{path.as_path}'"
    return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
            f"MED {_opt(path.med)}, communities {comms}")


def _bgp_route(d: Driver, p: dict) -> tuple[bool, str, list]:
    """Attributes of the BGP best path for a prefix, read from the BGP table (not the routing table)."""
    obs = d.bgp_paths(p["prefix"], p.get("vrf", "default"))
    paths = obs.value
    if p.get("present", True) is False:
        # Absent means no path at all in the BGP table, best or not. The router's own non-BGP routes
        # that a NOS lists there (SR Linux, whether exported or not) aren't BGP paths.
        paths = [x for x in paths if not x.local_candidate]
        if paths:
            return False, f"unexpectedly in the BGP table ({len(paths)} path(s); {_describe_path(paths[0])})", obs.evidence
        return True, "no BGP path", obs.evidence
    if not paths:
        return False, "no BGP path", obs.evidence
    best = next((x for x in paths if x.best), None)
    if best is None:
        return False, f"{len(paths)} BGP path(s) but none is best (next hop unreachable?)", obs.evidence
    wrong = []
    have = set(best.all_communities())
    missing = [c for c in p.get("communities", []) if c not in have]
    if missing:
        wrong.append(f"missing communities {' '.join(community_name(c) for c in missing)}")
    extra = [c for c in p.get("without_communities", []) if c in have]
    if extra:
        wrong.append(f"carries communities {' '.join(community_name(c) for c in extra)}")
    if "as_path" in p and best.as_path != p["as_path"]:
        wrong.append(f"as-path is '{best.as_path}', expected '{p['as_path']}'")
    if "as_path_regex" in p and not re.search(p["as_path_regex"], best.as_path or ""):
        wrong.append(f"as-path '{best.as_path}' does not match /{p['as_path_regex']}/")
    for key, label in (("local_pref", "local-pref"), ("med", "MED")):
        if key in p and getattr(best, key) != p[key]:
            wrong.append(f"{label} is {_opt(getattr(best, key))}, expected {p[key]}")
    if "next_hop" in p and best.next_hop != p["next_hop"]:
        wrong.append(f"next hop is {best.next_hop or '?'}, expected {p['next_hop']}")
    if wrong:
        return False, f"{'; '.join(wrong)} (best path: {_describe_path(best)})", obs.evidence
    return True, f"best path: {_describe_path(best)}", obs.evidence


EVALUATORS = {"bgp_session": _bgp_session, "bgp_prefixes": _bgp_prefixes, "route": _route, "ping": _ping,
              "bgp_route": _bgp_route}


def is_post_convergence(check: Check) -> bool:
    """Checks that are trivially true before the network converges, so they must run afterwards
    and hold: "must be absent", "must fail", a session expected NOT established, upper bounds on
    prefix counts (0 prefixes satisfies "max: 10" while BGP is still coming up), and any assertion
    about a best path's attributes (the best path can change when a slower session comes up)."""
    p = check.params
    return (
        (check.type in ("route", "bgp_route") and p.get("present", True) is False)
        # A best-path attribute (next hop, AS path, local-pref, MED, communities, or "must not carry") can
        # pass on a transient best path before the real one arrives: judge it after convergence and hold it
        or (check.type == "bgp_route" and any(k in p for k in BGP_ATTRIBUTES))
        or (check.type == "ping" and p.get("expect", "success") == "failure")
        or (check.type == "bgp_session" and p.get("state", "established") != "established")
        or (check.type == "bgp_prefixes" and ("max" in p or "exact" in p))
    )


def _evaluate(check: Check, driver: Driver) -> tuple[bool, str, list]:
    try:
        return EVALUATORS[check.type](driver, check.params)
    except Exception as e:  # a crashed check is a failed check, with the reason kept
        # the state command failed or its output was unreadable: the node gave no usable state
        return False, Unready(f"error: {e}"), []


def _sample(t: float, ok: bool, detail: str) -> dict:
    h = {"t": round(t, 1), "passed": ok, "detail": str(detail)}
    if not ok and isinstance(detail, Unready):
        h["unready"] = True
    return h


def _counts(history: list[dict]) -> dict:
    return {"samples_passed": sum(h["passed"] for h in history),
            "samples_unready": sum(bool(h.get("unready")) for h in history)}


def run_check(check: Check, driver: Driver, interval: float = 3.0, confirm: int = 2,
              clock=time.monotonic, sleep=time.sleep) -> Result:
    """Positive check: poll until it passes `confirm` samples in a row, or the timeout expires."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = clock()
    history: list[dict] = []
    streak = 0
    while True:
        ok, detail, evidence = _evaluate(check, driver)
        elapsed = clock() - t0
        history.append(_sample(elapsed, ok, detail))
        streak = streak + 1 if ok else 0
        if streak >= confirm or elapsed >= check.timeout:
            passed = streak >= confirm
            if not passed and ok:
                detail = f"{detail}, but not stable ({streak}/{confirm} consecutive passes before timeout)"
            elif not passed and any(h["passed"] for h in history):
                detail = f"{detail} (flapping: passed {sum(h['passed'] for h in history)} of {len(history)} samples)"
            return Result(check, passed, detail, len(history), round(elapsed, 1), started, evidence, history[-50:],
                          **_counts(history))
        sleep(min(interval, max(0.0, check.timeout - elapsed)))


def hold_check(check: Check, driver: Driver, hold: float = 10.0, interval: float = 3.0,
               clock=time.monotonic, sleep=time.sleep) -> Result:
    """Negative check: must stay true for the whole hold window; fails at the first violation."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = clock()
    history: list[dict] = []
    while True:
        ok, detail, evidence = _evaluate(check, driver)
        elapsed = clock() - t0
        history.append(_sample(elapsed, ok, detail))
        if not ok or elapsed >= hold:
            if ok:
                detail = f"{detail} (held {round(elapsed)}s, {len(history)} samples)"
            return Result(check, ok, detail, len(history), round(elapsed, 1), started, evidence, history[-50:],
                          **_counts(history))
        sleep(min(interval, max(0.0, hold - elapsed)))


def converge_then_hold(check: Check, driver: Driver, hold: float = 10.0, interval: float = 3.0,
                       clock=time.monotonic, sleep=time.sleep) -> Result:
    """Post-convergence check: reach the expected state (e.g. prefix count up to min), then hold it.

    Only prefix counts need the "reach" phase (counters ramp up). For absent routes, failing pings
    and down sessions, a violation seen after convergence is a real failure: fail fast."""
    if check.type != "bgp_prefixes":
        return hold_check(check, driver, hold=check.hold or hold, interval=interval, clock=clock, sleep=sleep)
    first = run_check(check, driver, interval=interval, confirm=1, clock=clock, sleep=sleep)
    if not first.passed:
        return first
    held = hold_check(check, driver, hold=check.hold or hold, interval=interval, clock=clock, sleep=sleep)
    held.started = first.started
    held.duration = round(first.duration + held.duration, 1)
    held.attempts += first.attempts
    held.history = (first.history + held.history)[-50:]
    held.samples_passed += first.samples_passed
    held.samples_unready += first.samples_unready
    return held


def _evaluate_all(checks: list[Check], drivers: dict, workers: int = 8) -> list[tuple]:
    """One sample of every check, run concurrently (each is a docker exec), results in input order."""
    if len(checks) <= 1:
        return [_evaluate(c, drivers[c.node]) for c in checks]
    with ThreadPoolExecutor(max_workers=min(workers, len(checks))) as pool:
        return list(pool.map(lambda c: _evaluate(c, drivers[c.node]), checks))


def run_round_robin(checks: list[Check], drivers: dict, interval: float = 3.0, confirm: int = 2,
                    clock=time.monotonic, sleep=time.sleep, on_result=None) -> list[Result]:
    """Positive checks polled together, one concurrent round at a time, against one shared start time.

    A check passes after `confirm` consecutive passing samples. The timeout only ends a check on a
    *failing* sample, so a big list (or a slow round) can't fail a healthy check as "not stable".
    """
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = clock()
    state = {id(c): {"streak": 0, "history": []} for c in checks}
    done: dict[int, Result] = {}
    while len(done) < len(checks):
        pending = [c for c in checks if id(c) not in done]
        for c, (ok, detail, evidence) in zip(pending, _evaluate_all(pending, drivers), strict=True):
            st = state[id(c)]
            elapsed = clock() - t0
            st["history"].append(_sample(elapsed, ok, detail))
            st["streak"] = st["streak"] + 1 if ok else 0
            # The timeout ends a check only on a failing sample. A passing check always gets its
            # confirming samples, however slow the round: it then passes, or fails on the next sample.
            finished = st["streak"] >= confirm or (not ok and elapsed >= c.timeout)
            if not finished:
                continue
            passed = st["streak"] >= confirm
            if not passed and ok:
                detail = f"{detail}, but not stable ({st['streak']}/{confirm} consecutive passes)"
            elif not passed and any(h["passed"] for h in st["history"]):
                detail = f"{detail} (flapping: passed {sum(h['passed'] for h in st['history'])} of {len(st['history'])} samples)"
            done[id(c)] = Result(c, passed, detail, len(st["history"]), round(elapsed, 1), started, evidence,
                                 st["history"][-50:], **_counts(st["history"]))
            if on_result:
                on_result(done[id(c)])
        if len(done) < len(checks):
            elapsed = clock() - t0
            # wake up in time for the nearest deadline among checks that are still failing
            nearest = min((c.timeout - elapsed for c in checks if id(c) not in done and state[id(c)]["streak"] == 0),
                          default=interval)
            sleep(max(0.0, min(interval, nearest)) if nearest > 0 else interval)
    return [done[id(c)] for c in checks]


def _reach_view(c: Check) -> Check | None:
    """The lower-bound part of a prefix check, used to wait for counters to ramp up.

    Upper bounds are never "reached" (0 prefixes satisfies max while BGP is still sending), so a
    max-only check has no reach phase and goes straight into the hold.
    """
    p = c.params
    low = p.get("exact", p.get("min"))
    if not low:
        return None
    params = {k: v for k, v in p.items() if k not in ("min", "max", "exact")}
    params["min"] = low
    return replace(c, params=params, timeout=min(c.timeout, REACH_WINDOW))


def hold_together(checks: list[Check], drivers: dict, hold: float = 10.0, interval: float = 3.0,
                  clock=time.monotonic, sleep=time.sleep, on_result=None) -> list[Result]:
    """Post-convergence checks, each held for its own window (check.hold or `hold`), sampled together.

    Prefix counts with a lower bound first wait (briefly; convergence is already proven) to reach it.
    Then every check must be true on every sample until its own window ends; the first violation fails it.
    """
    failed: dict[int, Result] = {}
    views = {id(c): _reach_view(c) for c in checks if c.type == "bgp_prefixes"}
    reach = [(c, v) for c in checks if (v := views.get(id(c)))]
    if reach:
        for (orig, _), r in zip(reach, run_round_robin([v for _, v in reach], drivers, interval=interval,
                                                       confirm=1, clock=clock, sleep=sleep), strict=True):
            if not r.passed:
                r.check = orig
                failed[id(orig)] = r
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = clock()
    window = {id(c): (c.hold or hold) for c in checks}
    live = [c for c in checks if id(c) not in failed]
    hist: dict[int, list] = {id(c): [] for c in live}
    last: dict[int, tuple] = {}
    finished_ok: dict[int, float] = {}
    while live:
        for c, (ok, detail, evidence) in zip(list(live), _evaluate_all(live, drivers), strict=True):
            t = clock() - t0
            hist[id(c)].append(_sample(t, ok, detail))
            last[id(c)] = (detail, evidence)
            if not ok:
                failed[id(c)] = Result(c, False, detail, len(hist[id(c)]), round(t, 1), started, evidence,
                                       hist[id(c)][-50:], **_counts(hist[id(c)]))
                live.remove(c)
            elif t >= window[id(c)]:
                finished_ok[id(c)] = t
                live.remove(c)
        if live:
            t = clock() - t0
            sleep(max(0.0, min(interval, min(window[id(c)] - t for c in live))))
    results = []
    for c in checks:
        if id(c) in failed:
            r = failed[id(c)]
        else:
            detail, evidence = last[id(c)]
            n, t = len(hist[id(c)]), finished_ok[id(c)]
            r = Result(c, True, f"{detail} (held {round(t)}s, {n} samples)", n, round(t, 1), started, evidence,
                       hist[id(c)][-50:], **_counts(hist[id(c)]))
        results.append(r)
        if on_result:
            on_result(r)
    return results


def never_ready_nodes(results: list[Result]) -> dict[str, str]:
    """The nodes that never gave usable state in these results (condition 4 of inconclusive_reason), each with
    the detail of its first state check. A node's state checks are its bgp_session and bgp_prefixes checks; else
    its route and bgp_route checks (its routing table); else, for a ping-only node, every check on it. The node
    never gave usable state when every sample of every one of them was unready. A ping can't show that a node
    gave control-plane state, so a ping with no replies doesn't count where the node has a state check (agent
    eval T10: bgpd off on every router, routes unreadable, pings answered with 0 replies)."""
    never_ready: dict[str, str] = {}
    for node in sorted({r.check.node for r in results}):
        on_node = [r for r in results if r.check.node == node]
        state = ([r for r in on_node if r.check.type in ("bgp_session", "bgp_prefixes")]
                 or [r for r in on_node if r.check.type in ("route", "bgp_route")] or on_node)
        if all(r.attempts and r.samples_unready == r.attempts for r in state):
            never_ready[node] = state[0].detail
    return never_ready


def inconclusive_reason(results: list[Result]) -> str | None:
    """Why a failed run says nothing about the change, or None if it does. Deliberately conservative:
    a configured BGP session that is down counts as a finding (an ASN typo or a wrong neighbor address
    looks exactly like that), so only "the node never gave usable state" qualifies.

    The run is inconclusive only if all of these hold:
    1. at least one check failed;
    2. no positive check passed on any sample, anywhere in the run (nothing ever showed a working network);
    3. no post-convergence check failed with readable state (a leak, or a session up that must be down,
       proves a working control plane);
    4. every failed check is on a node that never gave usable state: every sample of every bgp_session
       and bgp_prefixes check on it was unready (the state command failed or its output was unreadable,
       or BGP had no neighbors at all); for a node without such checks, every sample of every route and
       bgp_route check on it; for a ping-only node, every sample of every check on it.
    """
    failed = [r for r in results if not r.passed]
    if not failed:
        return None
    if any(r.samples_passed and not is_post_convergence(r.check) for r in results):
        return None
    if any(is_post_convergence(r.check) and r.samples_unready < r.attempts for r in failed):
        return None
    never_ready = never_ready_nodes(results)
    if not all(r.check.node in never_ready for r in failed):
        return None
    nodes = sorted({r.check.node for r in failed})
    why = "; ".join(f"{n}: {never_ready[n]}" for n in nodes)
    return (f"the lab did not reach a testable state: {', '.join(nodes)} never returned usable BGP state "
            f"({why}), and no check passed on any sample. Rerun with a longer timeout, or check that the lab boots")
