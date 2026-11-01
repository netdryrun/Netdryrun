"""Run behavioral checks.

Positive checks poll until they pass (networks need time to converge), then must pass again on
consecutive samples so a flapping session can't pass on one lucky sample. Negative checks run
after convergence and must hold for a whole window.
"""
from __future__ import annotations

import copy
import ipaddress
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from .config import BGP_ATTRIBUTES, Check, community_name
from .drivers import Driver
from .drivers.base import NoSuchInstance

REACH_WINDOW = 30.0  # seconds for post-convergence prefix counts to reach their range
QUIET_SAMPLES = 3    # identical lab fingerprints, at least, before a lab counts as quiescent
QUIET_MARGIN = 2.0   # seconds beyond the longest advertisement interval or timer, as in runner.ADV_MARGIN


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
    first_ready: float | None = None   # seconds into the check of its first sample with usable state (timings)


class Unready(str):
    """The detail of a failing sample that means "no usable state yet", not "the network is wrong": the
    state command failed or its output could not be read, or BGP had no neighbors at all on the node.
    It is how a lab that never came up (inconclusive) is told apart from a change that broke it (failed)."""


class Missing(str):
    """The detail of a failing sample of a positive check whose state was read and shows the thing missing: the
    route isn't active, there is no BGP path (or none is best), an established session has fewer prefixes than
    the minimum, a ping found no route at all. Only this kind of failure may end early, and only in a lab that
    has stopped changing (Quiescence): a session that is down, or state that can't be read, waits out the
    timeout as before (a connect-retry timer can bring a session up late)."""


def _not_configured(neighbor: str, seen: dict) -> str:
    if not seen:
        return Unready(f"neighbor {neighbor} not configured (no BGP neighbors at all on this node)")
    return f"neighbor {neighbor} not configured (seen: {', '.join(seen)})"


def _ambiguous(neighbor: str, n) -> str:
    return Unready(f"neighbor {neighbor} is ambiguous: {len(n.ambiguous)} sessions share it "
                   f"({', '.join(n.ambiguous)}), and either one's state would answer for the other; "
                   "check a global address instead")


def _bgp_session(d: Driver, p: dict) -> tuple[bool, str, list]:
    obs = d.bgp_neighbors(p.get("vrf", "default"))
    n = obs.value.get(p["neighbor"])
    if n is None:
        return False, _not_configured(p["neighbor"], obs.value), obs.evidence
    if n.ambiguous:
        return False, _ambiguous(p["neighbor"], n), obs.evidence
    if p["state"] == "down":
        return n.state != "established", f"state is {n.state}", obs.evidence
    return n.state == p["state"], f"state is {n.state}", obs.evidence


def _bgp_prefixes(d: Driver, p: dict) -> tuple[bool, str, list]:
    obs = d.bgp_neighbors(p.get("vrf", "default"))
    n = obs.value.get(p["neighbor"])
    if n is None:
        return False, _not_configured(p["neighbor"], obs.value), obs.evidence
    if n.ambiguous:
        return False, _ambiguous(p["neighbor"], n), obs.evidence
    if n.state != "established":
        # counters reset to 0 when a session drops (e.g. a max-prefix trip), so a count
        # from a down session would satisfy "max" by accident
        return False, f"session is {n.state}; prefix counts are only meaningful when established", obs.evidence
    afi = p.get("afi", "ipv4-unicast")
    count = n.prefixes.get(afi, 0)  # established but the family reports nothing: zero prefixes
    low, high = (p["exact"], p["exact"]) if "exact" in p else (p.get("min", 0), p.get("max"))

    def within(c: int) -> bool:
        return low <= c and (high is None or c <= high)

    top = n.prefixes_upto.get(afi, count)
    if top == count:
        if count < low:   # established, and short of the minimum
            return False, Missing(f"{count} {afi} prefixes accepted"), obs.evidence
        return within(count), f"{count} {afi} prefixes accepted", obs.evidence
    # Some received routes are hidden for a reason the device doesn't give, so the count is somewhere from
    # `count` to `top`: judged only when every value in that range gives the same answer (interop IOP-7)
    span = (f"{count} to {top} {afi} prefixes accepted ({top - count} received route(s) hidden: rejected by "
            "import policy or with a next hop the node can't use, which its output doesn't tell apart)")
    if within(count) and within(top):
        return True, span, obs.evidence
    if top < low or (high is not None and count > high):
        return False, span, obs.evidence
    if afi in n.prefixes_unread:   # the hidden routes couldn't be read: no usable state, not a wrong network
        return False, Unready(f"error: {span}: {n.prefixes_unread[afi]}"), obs.evidence
    return False, f"{span}: can't tell whether the bound holds", obs.evidence


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
        return False, Missing(f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}"), obs.evidence
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
            return False, Missing(why), obs.evidence
    if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
        return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
    if p.get("expect", "success") == "success":
        need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
        detail = f"{received}/{sent} replies (need {need})"
        # no reply at all: a candidate for ending early, only where the node has no lab route to the target
        # (Quiescence.routed); a partial answer never is
        return received >= need, detail if received >= need or received else Missing(detail), obs.evidence
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
        return False, Missing("no BGP path"), obs.evidence
    best = next((x for x in paths if x.best), None)
    if best is None:
        return False, Missing(f"{len(paths)} BGP path(s) but none is best (next hop unreachable?)"), obs.evidence
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


class RoundMemo:
    """One read per (node, query) per sampling round, shared by every check that asks it: three checks on one
    router no longer send the same `show bgp neighbors` three times. Each caller gets its own copy of the
    observation, all from the same instant. A read that fails fails the same way for every caller. Pings are
    never shared: each ping check sends its own packets."""

    SHARED = frozenset({"bgp_neighbors", "routes", "bgp_paths", "all_routes", "quiescence_timer"})

    def __init__(self, drivers: dict):
        self.drivers = drivers
        self._lock = threading.Lock()
        self._slots: dict[tuple, dict] = {}

    def __getitem__(self, node: str):
        return self.of(node, self.drivers[node])

    def of(self, node: str, driver):
        return _MemoDriver(self, node, driver)

    def read(self, node: str, driver, method: str, args: tuple, kwargs: dict):
        key = (node, method, args, tuple(sorted(kwargs.items())))
        with self._lock:
            slot = self._slots.get(key)
            owner = slot is None
            if owner:
                slot = self._slots[key] = {"done": threading.Event()}
        if owner:
            try:
                slot["value"] = getattr(driver, method)(*args, **kwargs)
            except Exception as e:   # every caller of this read sees the same failure
                slot["error"] = e
            finally:
                slot["done"].set()
        else:
            slot["done"].wait()
        if "error" in slot:
            raise slot["error"]
        return copy.deepcopy(slot["value"])


class _MemoDriver:
    def __init__(self, memo: RoundMemo, node: str, driver):
        self._memo, self._node, self._driver = memo, node, driver

    def __getattr__(self, name: str):
        attr = getattr(self._driver, name)
        if name not in RoundMemo.SHARED or not callable(attr):
            return attr
        return lambda *args, **kwargs: self._memo.read(self._node, self._driver, name, args, kwargs)


def _evaluate_all(checks: list[Check], drivers, workers: int = 8) -> list[tuple]:
    """One sample of every check, run concurrently (each is a docker exec), results in input order. Checks that
    read the same state on the same node share one read (RoundMemo)."""
    if not isinstance(drivers, RoundMemo):
        drivers = RoundMemo(drivers)
    if len(checks) <= 1:
        return [_evaluate(c, drivers[c.node]) for c in checks]
    with ThreadPoolExecutor(max_workers=min(workers, len(checks))) as pool:
        return list(pool.map(lambda c: _evaluate(c, drivers[c.node]), checks))


class Quiescence:
    """Whether the whole lab has stopped changing, for ending a failing positive check before its timeout.

    Each sample is a fingerprint of every routing node: every BGP session (in the default VRF and every VRF a
    check names) with its state and prefix counts, and the node's IPv4 and IPv6 routing tables. The lab is
    quiescent when at least QUIET_SAMPLES fingerprints in a row are identical and they span the window: the
    settle time, and at least the longest advertisement interval (MRAI) or timer any node reports, plus a margin.

    Anything uncertain makes a sample unusable, which starts the count again (fail closed: the check then waits
    out its timeout as before): a session that isn't established, a node with no BGP neighbors, a read that
    fails, an advertisement interval the driver doesn't know, or a node whose driver can't tell what could still
    change the state later on its own (Driver.quiescence_timer: None)."""

    def __init__(self, drivers: dict, vrfs=(), settle: float = 10.0):
        self.drivers = dict(drivers)   # every routing node of the lab
        self.vrfs = sorted({"default"} | set(vrfs))
        self.settle = settle
        self.run: list[tuple[float, object]] = []   # the current run of identical fingerprints: (time, fingerprint)
        self.window = settle
        self.ribs: dict[tuple[str, str, int], list] = {}   # the latest routing tables, for the ping rule

    def reset(self) -> None:
        self.run = []

    def sample(self, memo: RoundMemo, t: float) -> None:
        try:
            fp, window, ribs = self._fingerprint(memo)
        except Exception:   # anything unexpected: not a usable sample
            fp = None
        if fp is None:
            self.run, self.ribs = [], {}
            return
        if self.run and self.run[-1][1] != fp:
            self.run = []
        self.run.append((t, fp))
        self.window, self.ribs = window, ribs

    def quiet_since(self) -> float | None:
        """When the current quiescent stretch began, if it already spans the window; else None."""
        if len(self.run) < QUIET_SAMPLES or self.run[-1][0] - self.run[0][0] < self.window:
            return None
        return self.run[0][0]

    def span(self) -> float:
        return self.run[-1][0] - self.run[0][0] if self.run else 0.0

    def routed(self, node: str, vrf: str, target: str) -> bool:
        """Whether the node's latest routing table has any route to `target` other than a default route installed
        outside the routing daemon (protocol kernel: containerlab's default via the management network, which
        leads out of the lab). Unknown counts as routed, so a ping to it never ends early."""
        try:
            ip = ipaddress.ip_address(target)
        except ValueError:
            return True
        rib = self.ribs.get((node, vrf, ip.version))
        if rib is None:
            return True
        return any(ip in net for r in rib if (net := ipaddress.ip_network(r.prefix, strict=False)).prefixlen
                   or r.protocol != "kernel")

    def _fingerprint(self, memo: RoundMemo):
        fp, ribs = [], {}
        longest = 0.0
        for node in sorted(self.drivers):
            d = memo.of(node, self.drivers[node])
            timer = d.quiescence_timer()
            if timer is None:
                return None, None, None
            longest = max(longest, timer)
            for vrf in self.vrfs:
                try:
                    nbrs = d.bgp_neighbors(vrf).value
                except NoSuchInstance:
                    fp.append((node, vrf, "no such instance"))
                    continue
                if not nbrs or any(n.state != "established" or n.adv_interval is None for n in nbrs.values()):
                    return None, None, None
                longest = max([longest, *(n.adv_interval for n in nbrs.values())])
                fp.append((node, vrf, tuple(sorted((a, n.state, tuple(sorted(n.prefixes.items())),
                                                    tuple(sorted(n.prefixes_upto.items())))
                                                   for a, n in nbrs.items()))))
                for family in (4, 6):
                    try:
                        rib = d.all_routes(vrf, family).value
                    except NoSuchInstance:
                        fp.append((node, vrf, family, "no such instance"))
                        continue
                    ribs[(node, vrf, family)] = rib
                    fp.append((node, vrf, family, tuple(sorted({(r.prefix, r.protocol, r.active) for r in rib}))))
        if not fp:
            return None, None, None
        return tuple(fp), max(self.settle, longest + QUIET_MARGIN if longest > 0 else 0.0), ribs


def _ends_early(c: Check, st: dict, quiet: Quiescence, since: float) -> bool:
    """A failing positive check may end before its timeout only when it never passed, and every sample of it
    since the lab became quiescent showed the thing missing; a ping only when its node has no lab route to the
    target (Quiescence.routed)."""
    if st["passed"] or st["missing_from"] is None or st["missing_from"] > since:
        return False
    if c.type == "ping":
        return not quiet.routed(c.node, c.params.get("vrf", "default"), c.params["target"])
    return True


def run_round_robin(checks: list[Check], drivers: dict, interval: float = 3.0, confirm: int = 2,
                    clock=time.monotonic, sleep=time.sleep, on_result=None,
                    quiet: Quiescence | None = None) -> list[Result]:
    """Positive checks polled together, one concurrent round at a time, against one shared start time.

    A check passes after `confirm` consecutive passing samples. The timeout only ends a check on a
    *failing* sample, so a big list (or a slow round) can't fail a healthy check as "not stable".

    With `quiet`, a check that has only ever failed with its state read and the thing missing (Missing) ends
    before its timeout once the whole lab is quiescent (see Quiescence): an earlier fail, never a pass.
    """
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = clock()
    state = {id(c): {"streak": 0, "history": [], "passed": False, "missing_from": None, "first_ready": None}
             for c in checks}
    done: dict[int, Result] = {}

    def finish(c: Check, passed: bool, detail: str, evidence: list, elapsed: float) -> None:
        st = state[id(c)]
        done[id(c)] = Result(c, passed, detail, len(st["history"]), round(elapsed, 1), started, evidence,
                             st["history"][-50:], **_counts(st["history"]), first_ready=st["first_ready"])
        if on_result:
            on_result(done[id(c)])

    while len(done) < len(checks):
        pending = [c for c in checks if id(c) not in done]
        memo = RoundMemo(drivers)
        last: dict[int, tuple] = {}
        for c, (ok, detail, evidence) in zip(pending, _evaluate_all(pending, memo), strict=True):
            st = state[id(c)]
            elapsed = clock() - t0
            st["history"].append(_sample(elapsed, ok, detail))
            st["streak"] = st["streak"] + 1 if ok else 0
            st["passed"] = st["passed"] or ok
            if st["first_ready"] is None and (ok or not isinstance(detail, Unready)):
                st["first_ready"] = round(elapsed, 1)
            if isinstance(detail, Missing):
                st["missing_from"] = elapsed if st["missing_from"] is None else st["missing_from"]
            else:
                st["missing_from"] = None
            # The timeout ends a check only on a failing sample. A passing check always gets its
            # confirming samples, however slow the round: it then passes, or fails on the next sample.
            finished = st["streak"] >= confirm or (not ok and elapsed >= c.timeout)
            if not finished:
                last[id(c)] = (detail, evidence)
                continue
            passed = st["streak"] >= confirm
            if not passed and ok:
                detail = f"{detail}, but not stable ({st['streak']}/{confirm} consecutive passes)"
            elif not passed and any(h["passed"] for h in st["history"]):
                detail = f"{detail} (flapping: passed {sum(h['passed'] for h in st['history'])} of {len(st['history'])} samples)"
            finish(c, passed, detail, evidence, elapsed)
        if quiet is not None:
            waiting = [c for c in checks if id(c) not in done and not state[id(c)]["passed"]
                       and state[id(c)]["missing_from"] is not None]
            if not waiting:
                quiet.reset()
            else:
                quiet.sample(memo, clock() - t0)
                since = quiet.quiet_since()
                for c in waiting if since is not None else []:
                    if not _ends_early(c, state[id(c)], quiet, since):
                        continue
                    elapsed = clock() - t0
                    detail, evidence = last[id(c)]
                    finish(c, False, f"{detail} (ended early at {elapsed:.0f}s of its {c.timeout:g}s timeout: the lab "
                                     f"was quiescent for {quiet.span():.0f}s, every BGP session established and no "
                                     "prefix count or routing table changing)", evidence, elapsed)
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
