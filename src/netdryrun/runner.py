"""Orchestrate one dry run: deploy, check, collect evidence, destroy."""
from __future__ import annotations

import ipaddress
import math
import os
import platform
import signal
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from . import __version__
from .checks import (Result, Unready, _sample, hold_together, inconclusive_reason, is_post_convergence,
                     never_ready_nodes, run_round_robin)
from .config import Check, Config, ConfigError, Scenario, load
from .drivers import DriverError, check_supported, detect, for_node
from .drivers.frr import LOAD_RAN, communicate_daemons, parse_config_load_errors
from .drivers.base import NoSuchInstance
from .faults import RouteInjection
from .lab import Lab, LabError

# Every wait in a run goes through these two names (looked up at call time), so tests can drive a whole
# run on a fake clock.
_clock = time.monotonic
_sleep = time.sleep
POLL = 3.0   # seconds between samples, as in checks.py

# Labs this process deployed and must destroy if it is killed (see destroy_active_labs)
_ACTIVE: set = set()


class RunError(RuntimeError):
    """A run that can't go ahead for a reason that is neither the config file nor the lab (bad arguments)."""


# ---------------------------------------------------------------------------------------------------------
# Signals. SIGINT raises KeyboardInterrupt (Python's default). SIGTERM and SIGHUP are turned into
# Interrupted, a KeyboardInterrupt subclass, so they take exactly the same path: run()'s finally destroys
# the lab (unless --keep), and the CLI exits with 128 + the signal number: 130 for SIGINT, 143 for SIGTERM,
# 129 for SIGHUP, the shell convention. An interrupted run has no verdict.
# ---------------------------------------------------------------------------------------------------------

class Interrupted(KeyboardInterrupt):
    def __init__(self, signum: int):
        super().__init__(signal_name(signum))
        self.signum = signum


def signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name
    except ValueError:
        return f"signal {signum}"


def signal_exit_code(signum: int) -> int:
    return 128 + int(signum)


def _raise_interrupted(signum, _frame):
    raise Interrupted(signum)


def _catchable_signals(*names: str) -> list:
    return [s for s in (getattr(signal, n, None) for n in names) if s is not None]


def install_signal_handlers() -> None:
    """Make SIGTERM and SIGHUP clean up like Ctrl-C. Only possible from the main thread."""
    if threading.current_thread() is not threading.main_thread():
        return
    for sig in _catchable_signals("SIGTERM", "SIGHUP"):
        try:
            signal.signal(sig, _raise_interrupted)
        except (ValueError, OSError):
            pass


@contextmanager
def _signals_deferred():
    """Cleanup must not be cut short by a second Ctrl-C or a SIGTERM: signals that arrive meanwhile are
    recorded and re-raised by the caller once the lab is gone."""
    pending: list[int] = []
    old = {}
    if threading.current_thread() is threading.main_thread():
        for sig in _catchable_signals("SIGINT", "SIGTERM", "SIGHUP"):
            try:
                old[sig] = signal.signal(sig, lambda n, _f: pending.append(n))
            except (ValueError, OSError):
                pass
    try:
        yield pending
    finally:
        for sig, handler in old.items():
            if handler is not None:
                signal.signal(sig, handler)


def destroy_active_labs() -> None:
    """Destroy every lab this process deployed and has not cleaned up yet. For a process that is being
    killed while a run is in progress in another thread (the MCP server), where run()'s finally can't run."""
    for lab in list(_ACTIVE):
        try:
            lab.destroy()
        except Exception:
            pass
        _ACTIVE.discard(lab)


def _debug() -> bool:
    return os.environ.get("NETDRYRUN_DEBUG", "") not in ("", "0", "false", "no")


# ---------------------------------------------------------------------------------------------------------
# Loading a config: every way a file can be unreadable is a config error (exit 2), never a traceback that
# exits 1 ("checks failed").
# ---------------------------------------------------------------------------------------------------------

def _config_path(path) -> Path:
    p = Path(path)
    return p / "netdryrun.yml" if p.is_dir() else p


def _yaml_problem(e: yaml.YAMLError) -> str:
    mark = getattr(e, "problem_mark", None)
    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
    return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"


def _shape_problem(p: Path) -> str | None:
    """A clear message for a top-level value of the wrong type, which config.load can trip over."""
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    t = data.get("timeout")
    if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float))):
        try:
            float(t)
        except (TypeError, ValueError):
            return f"{p}: timeout must be a number of seconds (for example 120), got {t!r}"
    for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "a list of scenarios"),
                           ("nodes", dict, "a mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}")):
        v = data.get(key)
        if v is not None and not isinstance(v, typ):
            return f"{p}: {key} must be {what}, not a {type(v).__name__}"
    for k, v in (data.get("nodes") or {}).items():
        if v is not None and not isinstance(v, dict):
            return f"{p}: nodes.{k} must be a mapping (driver:, setup:), not a {type(v).__name__}"
    return None


def load_config(path) -> Config:
    """config.load, with every failure (bad YAML, wrong types, unreadable file) raised as ConfigError."""
    try:
        return load(path)
    except ConfigError:
        raise
    except yaml.YAMLError as e:
        raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
    except Exception as e:
        p = _config_path(path)
        raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None


# ---------------------------------------------------------------------------------------------------------

@dataclass
class RunReport:
    config: Config
    lab_name: str = ""
    started: str = ""
    finished: str = ""
    results: list[Result] = field(default_factory=list)
    error: str = ""
    environment: dict = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def failed(self) -> int:
        return sum(not r.passed for r in self.results)

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if self.results and self.failed == 0:
            return "passed"
        return "inconclusive" if self.inconclusive_reason else "failed"

    @property
    def inconclusive_reason(self) -> str | None:
        """Set when the lab never reached a testable state (see checks.inconclusive_reason)."""
        return None if self.error else inconclusive_reason(self.results)

    @property
    def exit_code(self) -> int:
        return {"passed": 0, "failed": 1, "inconclusive": 3}.get(self.status, 2)


def error_report(path, error: str) -> RunReport:
    """The report of a run that never started (for --json on a config error)."""
    now = _now()
    return RunReport(config=Config(path=_config_path(path), lab=Path(), timeout=0.0, checks=[]),
                     started=now, finished=now, error=error)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_duration(name: str, value) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0 <= value < math.inf):
        raise RunError(f"{name} must be a number of seconds >= 0, got {value!r}")


def preflight(config: Config, lab: Lab, *, full: bool = False) -> None:
    """The checks that need only the config and the topology file: run() makes them before deploying, and
    `netdryrun validate` makes them too. Raises LabError or DriverError.

    full=True (validate) also checks what run() only finds out after deploying: that every node a check
    reads has a driver (detected from its kind and image, or set in nodes.<node>.driver), and that no link
    fault targets an SR Linux node."""
    wanted = {c.node for c in config.checks} | {c.node for sc in config.scenarios for c in sc.checks} \
        | {f.node for sc in config.scenarios for f in sc.faults} | set(config.setup)
    unknown = sorted(wanted - set(lab.nodes))
    if unknown:
        raise LabError(f"unknown node(s) {', '.join(unknown)}; the topology has {', '.join(lab.nodes)}")
    all_checks = config.checks + [c for sc in config.scenarios for c in sc.checks]
    if full:
        for node in sorted({c.node for c in all_checks} - set(config.drivers)):
            detect(lab.nodes[node])
    for c in all_checks:
        check_supported(lab, c, config.drivers.get(c.node))
    for f in (f for sc in config.scenarios for f in sc.faults if f.kind == "inject_routes"):
        driver = config.drivers.get(f.node) or detect(lab.nodes[f.node])
        if driver != "frr":
            raise LabError(f"inject_routes on {f.node} ({driver}) is not supported yet: it needs an FRR node; "
                           "inject the routes from an FRR neighbor instead")
    if full:
        for f in (f for sc in config.scenarios for f in sc.faults if f.kind != "inject_routes"):
            lab._require_linux_links(f.node)


def check_topology(config: Config) -> Lab:
    """`netdryrun validate` past the file itself: load the topology (strictly) and make every pre-deploy
    check, without Docker or containerlab. Raises LabError or DriverError."""
    lab = Lab(config.lab)
    preflight(config, lab, full=True)
    return lab


def rejected_config(lab, config: Config) -> str:
    """Why the lab did not run the config as written, or "". FRR applies its config line by line at boot and skips
    a line it rejects (a typo, a command this release doesn't have): the lab then runs without it, and the checks
    test a network the change never reached. Read after the checks, when every node has booted; a boot log that
    can't be read is no proof either. (Other NOSes: see the config reference, "Config that fails to load".)"""
    found = []
    for name, node in lab.nodes.items():
        if node.kind in ("bridge", "ovs-bridge"):   # no container, no config
            continue
        try:
            driver = config.drivers.get(name) or detect(node)
        except DriverError:
            driver = None   # FRR in an image not named for it is still FRR: its rejected lines still count
        if driver not in ("frr", None):
            continue
        r = lab.boot_log(name)
        if r.rc != 0:
            if driver == "frr":
                found.append(f"{name}: its boot log could not be read ({(r.stderr or r.stdout).strip()[-200:]}), "
                             "so whether its config loaded is unknown")
            continue
        errors = parse_config_load_errors(r.stdout)
        daemons = communicate_daemons(r.stdout)
        if errors and daemons:
            # a line a daemon answered with "Failure to communicate" can still have been applied: one in the same
            # section of that daemon's own running config doesn't count. What can't be read counts (fail closed)
            conf = lab.exec(name, ["cat", "/etc/frr/frr.conf"])
            reads = {d: lab.exec(name, ["vtysh", "-d", d, "-c", "show running-config"]) for d in daemons}
            if conf.rc == 0:
                errors = parse_config_load_errors(r.stdout, {d: x.stdout for d, x in reads.items() if x.rc == 0},
                                                  conf.stdout)
            bad = [x for x in (conf, *reads.values()) if x.rc != 0]
            if bad and errors:
                why = (bad[0].stderr or "").strip()[-200:]
                errors = [*errors, f"(not checked against the running config: {why or 'it could not be read'})"]
        if errors:
            found.append(f"{name}: {'; '.join(errors)}")
        elif driver == "frr" and not LOAD_RAN.search(r.stdout):
            found.append(f"{name}: its boot log shows no sign of a config load (no vtysh boot output, no daemon "
                         "config line), so whether its config loaded is unknown. Netdryrun reads the config load "
                         "FRR's image runs at boot (frr.conf, vtysh -b)")
    if not found:
        return ""
    return ("FRR rejected configuration lines at boot, so the lab ran without them and the checks did not test the "
            f"change as written: {' | '.join(found)}. Fix the config and run again.")


def run(config: Config, *, deploy: bool = True, keep: bool = False, keep_on_failure: bool = False,
        settle: float = 10.0, hold: float = 10.0,
        on_result: Callable[[Result], None] | None = None, log: Callable[[str], None] = lambda _: None) -> RunReport:
    report = RunReport(config=config, started=_now())
    lab = None
    deployed = False      # this run started a deploy: only then is the lab its own to destroy
    interrupted = None    # the signal that ended the run, if any
    try:
        _check_duration("--settle", settle)
        _check_duration("--hold", hold)
        lab = Lab(config.lab)
        report.lab_name = lab.name
        lab.check_tools()
        report.environment = {
            "netdryrun": __version__,
            "containerlab": lab.version(),
            "python": platform.python_version(),
            "host": platform.platform(),
            "nodes": {n.name: {"kind": n.kind, "image": n.image} for n in lab.nodes.values()},
        }
        # Every node a check or a fault names must exist, and every check be readable, before deploying
        preflight(config, lab)
        if deploy:
            # Two runs of the same lab would redeploy each other's containers and destroy them under each
            # other's checks. Refuse instead: a lock for runs on this host, and Docker for everything else.
            lab.acquire_lock()
            existing = lab.existing_containers()
            if existing:
                raise LabError(
                    f"a lab named '{lab.name}' is already running ({len(existing)} container(s), e.g. "
                    f"{sorted(existing)[0]}): another Netdryrun run, or a lab deployed by hand or kept with --keep. "
                    f"Netdryrun won't redeploy or destroy it. Wait for the other run to finish, or remove the lab "
                    f"with: containerlab destroy -t {lab.topology} --cleanup")
            log(f"Deploying lab {lab.name} ({len(lab.nodes)} nodes); this usually takes 30-90 s, longer the first time images are pulled...")
            deployed = True
            if not keep:
                _ACTIVE.add(lab)
            lab.deploy()
        missing = {n.container for n in lab.nodes.values()} - lab.running_containers()
        if missing:
            raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")
        if deploy:
            for node, cmds in config.setup.items():
                log(f"Running setup on {node}...")
                lab.run_setup(node, cmds, log=log)

        drivers = {}

        def driver_for(node: str):
            if node not in drivers:
                drivers[node] = for_node(lab, node, config.drivers.get(node))
            return drivers[node]

        for check in config.checks:
            driver_for(check.node)

        positives = [c for c in config.checks if not is_post_convergence(c)]
        negatives = [c for c in config.checks if is_post_convergence(c)]
        report.results += run_round_robin(positives, drivers, on_result=on_result, clock=_clock, sleep=_sleep)
        if negatives:
            gate_warnings: dict[int, str] = {}
            not_converged = _bgp_convergence_gate(negatives, config.checks, drivers, log=log,
                                                  positive_results=report.results, warnings=gate_warnings)
            if not positives:
                # nothing has proven convergence yet; give the control plane time to come up
                settle = max(settle, 30.0)
            log(f"Convergence checks done; settling {settle:g}s before post-convergence checks...")
            _sleep(settle)
            ready = [c for c in negatives if id(c) not in not_converged]
            report.results += hold_together(ready, drivers, hold=hold, on_result=_with_warnings(gate_warnings, on_result),
                                            clock=_clock, sleep=_sleep)
            for r in not_converged.values():
                report.results.append(r)
                if on_result:
                    on_result(r)
        # Keep the report in the order the user wrote the checks
        order = {id(c): i for i, c in enumerate(config.checks)}
        report.results.sort(key=lambda r: order[id(r.check)])

        # The main checks already show the lab never reached a testable state (no node gave usable state, no
        # check passed on any sample): a scenario on a lab that never converged has no baseline to fault or
        # recover to, so skip them and report inconclusive (exit 3), as the same lab without scenarios does.
        # The results hold failed checks, so this is never a pass. Only when every node the scenarios fault or
        # check is one of those that never gave state: a scenario on a node that did could still find a real
        # failure (exit 1), and a scenario snapshot that can't be read after a readable main phase still stops
        # the run (exit 2).
        scenarios = config.scenarios
        dead = never_ready_nodes(report.results)
        touched = {c.node for sc in scenarios for c in sc.checks} | {f.node for sc in scenarios for f in sc.faults}
        if scenarios and inconclusive_reason(report.results) and touched <= dead.keys():
            log(f"The lab never reached a testable state; {len(scenarios)} scenario(s) skipped")
            scenarios = []
        for sc in scenarios:
            for check in sc.checks:
                driver_for(check.node)
            report.results += run_scenario(lab, sc, drivers, settle=settle, hold=hold, on_result=on_result, log=log,
                                           driver_for=driver_for, baseline_checks=config.checks)
            # Prove the network recovered (not just slept): the positive checks that passed before
            # the scenario must pass again. Checks the change already broke can't recover, so they
            # don't count. Not recovering is a finding about the network, reported as failed checks.
            baseline_ok = [r.check for r in report.results if r.passed and r.check in positives]
            stuck = [r for r in run_round_robin(baseline_ok, drivers, clock=_clock, sleep=_sleep) if not r.passed]
            if stuck:
                for r in stuck:
                    r.check = replace(r.check, name=f"[after {sc.name}] recovers: {r.check.name}")
                    report.results.append(r)
                    if on_result:
                        on_result(r)
                if sc is not config.scenarios[-1]:
                    log(f"The network did not recover after scenario '{sc.name}'; later scenarios skipped")
                break
        rejected = rejected_config(lab, config)
        if rejected:
            report.error = rejected
    except KeyboardInterrupt as e:
        interrupted = e
        report.error = f"interrupted by {signal_name(getattr(e, 'signum', signal.SIGINT))}: no verdict"
        e.report = report
        raise
    except (LabError, DriverError, ConfigError, RunError) as e:
        report.error = str(e)
    except Exception as e:
        # A crash must never look like "checks failed" (exit 1): it is an error (exit 2) with a report
        report.error = (f"internal error: {type(e).__name__}: {e}. This is a Netdryrun bug, not a verdict on the "
                        "change; rerun with --debug (or NETDRYRUN_DEBUG=1) for the traceback, and please report it")
        if _debug():
            traceback.print_exc(file=sys.stderr)
    finally:
        with _signals_deferred() as pending:
            # An interrupted run has no verdict, so --keep-on-failure doesn't apply: only --keep keeps the lab
            keep_now = keep or (keep_on_failure and interrupted is None and report.status != "passed")
            if lab is not None and deployed and not keep_now:
                log("Destroying lab...")
                try:
                    d = lab.destroy()
                    if d.rc != 0:
                        log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
                except Exception as e:  # cleanup trouble must never hide the test results
                    log(f"warning: lab cleanup failed: {e}")
            elif lab is not None and deployed:
                log(f"Lab {lab.name} left running for debugging; destroy with: containerlab destroy -t {lab.topology} --cleanup")
            if lab is not None:
                _ACTIVE.discard(lab)
                lab.release_lock()
            report.finished = _now()
        if pending and interrupted is None:
            # a signal arrived during cleanup: the lab is gone, now honor it
            report.error = report.error or f"interrupted by {signal_name(pending[0])}: no verdict"
            e = Interrupted(pending[0])
            e.report = report
            raise e
    return report


# ---------------------------------------------------------------------------------------------------------
# Post-convergence gate (audit M3).
#
# Positive checks only prove convergence for the sessions and routes the user happened to check; a leak can
# arrive later over a session nobody checked (a slower peer, a NOS that boots later). So before the
# post-convergence phase, every node that carries a post-convergence check must report every configured
# BGP neighbor (in that check's VRF) established, with unchanged prefix counts, on 2 consecutive samples.
# Neighbors that a check expects NOT to be established (bgp_session with another state) are left out.
# Then the settle delay runs, then the hold.
#
# The wait is bounded by the largest timeout of the node's post-convergence checks. If a configured
# session on the node never comes up, its post-convergence checks fail as "not evaluated", saying which
# session (a down session is a finding, as everywhere else). A node that never answers with BGP state is
# not gated (it may not run BGP at all; its own checks show a broken node), nor is a ping-only node whose
# first answer is an error. Prefix counts that keep changing until the deadline don't block.
#
# A node that answers with no BGP neighbors at all is NOT converged: that is exactly what a node answers
# before its BGP config is applied, and a leak can arrive once it is. The gate keeps waiting up to the cap.
# If the node still reports no neighbors then and the file says it runs BGP (a bgp_session, bgp_prefixes or
# bgp_route check on it, or a route check with protocol bgp), its post-convergence checks fail as "not
# evaluated", every sample unready (from 0.3.2; a leak guard would otherwise pass on the empty table). A node
# with no BGP check anywhere in the file may not run BGP at all (static routing): its checks go ahead, each
# with a warning in its result that it was evaluated without BGP convergence.
# ---------------------------------------------------------------------------------------------------------

def _with_warnings(warnings: dict[int, str], on_result=None):
    """An on_result callback that first adds the gate's warning (if any) to the result's detail, so the
    warning is in the report and the console line of each check it concerns. The verdict is unchanged."""
    def add(r: Result) -> None:
        w = warnings.get(id(r.check))
        if w:
            r.detail = f"{r.detail} (warning: {w})"
        if on_result:
            on_result(r)
    return add


def _bgp_convergence_gate(negatives: list[Check], all_checks: list[Check], drivers: dict,
                          log=lambda _: None, positive_results: list[Result] = (),
                          warnings: dict[int, str] | None = None,
                          expected_down: set[tuple[str, str, str]] = frozenset()) -> dict[int, Result]:
    # A node whose positive checks never got usable state on any sample already waited out their timeout:
    # don't wait again (the run is then failed or inconclusive on those checks anyway)
    on_node: dict[str, list[Result]] = {}
    for r in positive_results:
        on_node.setdefault(r.check.node, []).append(r)
    dead = {n for n, rs in on_node.items() if all(r.attempts and r.samples_unready == r.attempts for r in rs)}
    groups: dict[tuple[str, str], list[Check]] = {}
    for c in negatives:
        if c.node not in dead:
            groups.setdefault((c.node, c.params.get("vrf", "default")), []).append(c)
    excluded = {(c.node, c.params.get("vrf", "default"), c.params.get("neighbor")) for c in all_checks
                if c.type == "bgp_session" and c.params.get("state", "established") != "established"}
    excluded |= set(expected_down)   # in a scenario: the sessions over the links it took down
    # nodes the file says run BGP: any BGP check on them, or a route check that names protocol bgp
    bgp_nodes = {c.node for c in all_checks
                 if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                 or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
    deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
          for g in groups}
    started = _now()
    t0 = _clock()
    pending = set(groups)
    first = True
    blocked: dict[int, Result] = {}
    while pending:
        for g in sorted(pending):
            node, vrf = g
            s = st[g]
            t = _clock() - t0
            try:
                nbrs = drivers[node].bgp_neighbors(vrf).value
            except Exception as e:
                if first and all(c.type == "ping" for c in groups[g]):
                    pending.discard(g)   # not a BGP speaker; nothing to wait for
                    continue
                s["streak"], s["detail"], s["empty"] = 0, Unready(f"BGP state unreadable on {node}: {e}"), False
                s["history"].append(_sample(t, False, s["detail"]))
                continue
            s["answered"] = True
            s["empty"] = not nbrs
            if not nbrs:
                # No neighbors at all is what a node answers before its BGP config is applied: not converged
                # (a leak can arrive once it is), so keep waiting, up to the cap
                where = "" if vrf == "default" else f" (vrf {vrf})"
                s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
                s["history"].append(_sample(t, False, s["detail"]))
                continue
            down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
                          if n.state != "established" and (node, vrf, a) not in excluded)
            if down:
                where = "" if vrf == "default" else f" (vrf {vrf})"
                s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
                s["history"].append(_sample(t, False, s["detail"]))
                continue
            counts = {a: dict(n.prefixes) for a, n in nbrs.items()}
            s["streak"] = s["streak"] + 1 if s["streak"] and counts == s["counts"] else 1
            s["counts"] = counts
            s["history"].append(_sample(t, True, "every BGP session established"))
            if s["streak"] >= 2:
                pending.discard(g)
        first = False
        if not pending:
            break
        t = _clock() - t0
        for g in sorted(pending):
            if t < deadline[g]:
                continue
            pending.discard(g)
            s = st[g]
            if not s["answered"]:
                log(f"warning: {g[0]} never returned BGP state; its post-convergence checks start without the BGP gate")
            elif s["empty"] and g[0] in bgp_nodes:
                # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                # leak guard would pass on the empty table. Not evaluated, every sample unready.
                where = "" if g[1] == "default" else f" (vrf {g[1]})"
                for c in groups[g]:
                    detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                     f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
                                     "post-convergence check means nothing before the node's BGP sessions exist")
                    blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                            s["history"][-50:], samples_passed=0,
                                            samples_unready=len(s["history"]))
            elif s["empty"]:
                # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                # BGP at all (static routing). Go ahead, but say so on each check
                where = "" if g[1] == "default" else f" (vrf {g[1]})"
                text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                        "without BGP convergence")
                log(f"warning: {text}")
                if warnings is not None:
                    for c in groups[g]:
                        warnings[id(c)] = text
            elif s["streak"] == 0:
                for c in groups[g]:
                    detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
                              "check only means something once every BGP session on its node is up (a leak can "
                              "arrive over any of them). If a session is down on purpose, add a bgp_session check "
                              "with state: down for it")
                    blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                            s["history"][-50:], samples_passed=0,
                                            samples_unready=sum(bool(h.get("unready")) for h in s["history"]))
            # established but prefix counts still moving at the deadline: go ahead
        if pending:
            nearest = min(deadline[g] for g in pending) - (_clock() - t0)
            _sleep(max(0.0, min(POLL, nearest)))
    return blocked


# ---------------------------------------------------------------------------------------------------------
# Scenario timing (audit B5).
#
# A scenario's positive checks ("the route is still there", "ping still works") are already true before
# the network notices a failure, so they must not be judged on the state from before the fault took effect.
# The rule, in order:
#   1. Before applying a link fault, find the BGP sessions that run over the links going down and are
#      established: on the faulted node (neighbors in the downed interfaces' subnets, or named after the
#      interface for unnumbered BGP) and on the far end of each link, looking through bridges (neighbors
#      whose address is one of the faulted interface's addresses). Default VRF plus the VRFs the scenario's
#      checks use.
#   2. Apply the faults, then wait until every one of those sessions is no longer established on both ends:
#      proof that the network saw the fault. The wait is bounded by the largest timeout of the scenario's
#      checks; if the fault never shows, the run stops with an error (exit 2), never a verdict on pre-fault
#      state. (BGP hold timers without BFD can take up to 180 s: raise timeout.)
#   3. Wait the settle delay (--settle), so the withdrawals propagate beyond the adjacent routers.
#   4. Positive checks must then pass on 2 consecutive samples AND keep passing for the hold window
#      (--hold, or the check's hold): a redundancy claim is about the whole failure, not one instant.
#   5. Post-convergence checks then wait for the same BGP gate as at the top level (every session on their
#      node up, except the sessions over the downed links and those a check expects down, with stable
#      prefix counts; capped at their timeout), then must hold. For inject_routes this is what shows the
#      routes spread beyond the injecting node. A peer with a long advertisement interval can still delay
#      propagation beyond the gate.
# If the BGP state (or interface addresses) needed for step 1 can't be read, the run stops with an error
# (exit 2) before any fault: "couldn't read it" is never "there are none". When the state was read and no
# BGP session runs over the downed links (static routing, a link without BGP, iBGP between
# loopbacks over an IGP), step 2 has nothing to observe; steps 3 and 4 still apply, so give such scenarios
# a settle that covers the failure detection time.
# ---------------------------------------------------------------------------------------------------------

def _ip(text: str):
    try:
        return ipaddress.ip_address(text.split("%")[0])
    except ValueError:
        return None


def _sessions_over_links(lab: Lab, links: list[tuple[str, str]], vrfs: list[str], driver_for,
                         log=lambda _: None, any_state: bool = False) -> list[tuple[str, str, str]]:
    """The established BGP sessions (node, vrf, neighbor) that run over the given (node, interface) links
    (with any_state, every configured session over them, established or not)."""
    established, every = _link_sessions(lab, links, vrfs, driver_for, log=log)
    return every if any_state else established


def _link_sessions(lab: Lab, links: list[tuple[str, str]], vrfs: list[str], driver_for,
                   log=lambda _: None) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """(the established sessions, every configured session) over the links, from one read of each node.

    "Couldn't read it" is never "there are none": BGP state (or interface addresses) that can't be read
    raises LabError naming the node, since the scenario could otherwise be judged without the wait for the
    fault to take effect. Only a node no driver can read (a Linux host), or a VRF or BGP instance the node
    says it doesn't have, has nothing to observe."""
    watch: set[tuple[str, str, str]] = set()
    every: set[tuple[str, str, str]] = set()
    states: dict[tuple[str, str], dict] = {}

    def neighbors(node: str, vrf: str) -> dict:
        if (node, vrf) not in states:
            try:
                driver = driver_for(node)
            except DriverError as e:
                log(f"  {node}: no driver ({e}); no BGP session to observe there")
                states[(node, vrf)] = {}
                return states[(node, vrf)]
            try:
                states[(node, vrf)] = driver.bgp_neighbors(vrf).value
            except NoSuchInstance:
                states[(node, vrf)] = {}   # the node has no such VRF or BGP instance: nothing to observe
            except Exception as e:
                where = "" if vrf == "default" else f" (vrf {vrf})"
                raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                               f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
                               "when the fault took effect") from None
        return states[(node, vrf)]

    for node, iface in links:
        addrs = lab.interface_addresses(node, iface)
        local_ips = {a.ip for a in addrs}
        for vrf in vrfs:
            for key, n in neighbors(node, vrf).items():
                ip = _ip(key)
                over = key == iface or (ip is not None and ip not in local_ips and any(ip in a.network for a in addrs))
                if over:
                    every.add((node, vrf, key))
                    if n.state == "established":
                        watch.add((node, vrf, key))
            for peer, peer_iface in lab.peers_of(node, iface):
                for key, n in neighbors(peer, vrf).items():
                    ip = _ip(key)
                    if key == peer_iface or ip in local_ips:
                        every.add((peer, vrf, key))
                        if n.state == "established":
                            watch.add((peer, vrf, key))
    return sorted(watch), sorted(every)


def _wait_fault_visible(watch: list[tuple[str, str, str]], driver_for, timeout: float, sc: Scenario,
                        log=lambda _: None) -> None:
    if not watch:
        log("  no BGP session runs over the downed links; relying on the settle and hold windows")
        return
    t0 = _clock()
    while True:
        still = []
        by_node: dict[tuple[str, str], list[str]] = {}
        for node, vrf, key in watch:
            by_node.setdefault((node, vrf), []).append(key)
        for (node, vrf), keys in sorted(by_node.items()):
            try:
                nbrs = driver_for(node).bgp_neighbors(vrf).value
            except Exception as e:
                still.append(f"{node}: BGP state unreadable ({e})")
                continue
            still += [f"{node} -> {k}" for k in keys if (n := nbrs.get(k)) is not None and n.state == "established"]
        elapsed = _clock() - t0
        if not still:
            log(f"  the fault took effect after {elapsed:.0f}s ({len(watch)} BGP session(s) over the downed links are down)")
            return
        if elapsed >= timeout:
            raise LabError(
                f"scenario '{sc.name}': the fault did not take effect within {timeout:g}s: BGP session(s) over the "
                f"downed links still established ({', '.join(still[:5])}). Netdryrun won't judge the scenario's "
                "checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) "
                "to notice a failure: raise the checks' timeout, or lower the hold timers in the lab")
        _sleep(max(0.0, min(POLL, timeout - elapsed)))


def _reach_then_hold(checks: list[Check], drivers: dict, hold: float, on_result=None) -> list[Result]:
    """Positive scenario checks: pass on 2 consecutive samples, then keep passing for the hold window."""
    reached = run_round_robin(checks, drivers, clock=_clock, sleep=_sleep)
    ok = [r.check for r in reached if r.passed]
    held = {id(r.check): r for r in hold_together(ok, drivers, hold=hold, clock=_clock, sleep=_sleep)} if ok else {}
    out = []
    for r in reached:
        h = held.get(id(r.check))
        if h is not None:
            window = r.check.hold or hold
            if not h.passed:
                h.detail = (f"{h.detail} (it passed at first, then failed within the {window:g}s hold window: "
                            "the fault took effect late)")
            h.history = (r.history + [{**x, "t": round(x["t"] + r.duration, 1)} for x in h.history])[-50:]
            h.attempts += r.attempts
            h.samples_passed += r.samples_passed
            h.samples_unready += r.samples_unready
            h.duration = round(r.duration + h.duration, 1)
            h.started = r.started
            r = h
        out.append(r)
        if on_result:
            on_result(r)
    return out


def run_scenario(lab: Lab, sc: Scenario, drivers: dict, *, settle: float, hold: float,
                 on_result=None, log=lambda _: None, driver_for=None, baseline_checks: list[Check] = ()) -> list[Result]:
    """Inject the scenario's faults, prove they took effect, run its checks, then restore the links and
    routes and let the network re-converge. See "Scenario timing" above for the rule."""
    if driver_for is None:
        def driver_for(node):
            if node not in drivers:
                drivers[node] = for_node(lab, node)
            return drivers[node]
    downed: list[tuple[str, str]] = []
    injected: list[RouteInjection] = []
    results: list[Result] = []
    log(f"Scenario: {sc.name}")
    # Which links go down, decided before anything changes
    plan = []
    for f in sc.faults:
        if f.kind == "inject_routes":
            plan.append((f, []))
            continue
        lab._require_linux_links(f.node)
        plan.append((f, [f.interface] if f.kind == "link_down" else lab.data_interfaces(f.node)))
    links = [(f.node, iface) for f, ifaces in plan for iface in ifaces]
    vrfs = sorted({"default"} | {c.params.get("vrf", "default") for c in sc.checks})
    # watch: the established sessions over the downed links, which must go down (the fault took effect).
    # over_links: every session over them, established or not, expected down while the fault lasts: the
    # BGP gate for the scenario's post-convergence checks doesn't wait for those.
    watch, over = _link_sessions(lab, links, vrfs, driver_for, log=log) if links else ([], [])
    over_links = set(over)
    try:
        for f, ifaces in plan:
            if f.kind == "inject_routes":
                inj = RouteInjection(lab, f.node, f.prefixes, f.as_path)
                injected.append(inj)   # recorded first: restore even if applying half-fails
                log(f"Injecting {inj.describe()}")
                inj.apply()
                continue
            for iface in ifaces:
                downed.append((f.node, iface))   # recorded first: restore even if this call half-fails
                lab.set_link(f.node, iface, up=False)
        if links:
            _wait_fault_visible(watch, driver_for, max(c.timeout for c in sc.checks), sc, log=log)
        log(f"  settling {settle:g}s before the scenario's checks")
        _sleep(settle)
        positives = [c for c in sc.checks if not is_post_convergence(c)]
        negatives = [c for c in sc.checks if is_post_convergence(c)]
        pos_results = _reach_then_hold(positives, drivers, hold, on_result=on_result)
        results += pos_results
        if negatives:
            # The same BGP gate as at the top level: every session on the node up (except those the fault
            # took down and those a check expects down), with stable prefix counts. For inject_routes, this
            # is what shows the routes have spread to the node under test, not only into the injecting
            # node's own table.
            for c in negatives:
                driver_for(c.node)
            gate_warnings: dict[int, str] = {}
            blocked = _bgp_convergence_gate(negatives, list(baseline_checks) + sc.checks, drivers, log=log,
                                            positive_results=pos_results, warnings=gate_warnings,
                                            expected_down=over_links)
            ready = [c for c in negatives if id(c) not in blocked]
            neg_results = hold_together(ready, drivers, hold=hold, on_result=_with_warnings(gate_warnings, on_result),
                                        clock=_clock, sleep=_sleep)
            for r in blocked.values():
                neg_results.append(r)
                if on_result:
                    on_result(r)
            order = {id(c): i for i, c in enumerate(negatives)}
            results += sorted(neg_results, key=lambda r: order[id(r.check)])
    finally:
        not_restored = []
        for node, iface in downed:
            try:
                lab.set_link(node, iface, up=True)
            except LabError as e:
                not_restored.append(f"{node} {iface}: {e}")
        for inj in injected:
            try:
                inj.restore()
            except LabError as e:
                not_restored.append(str(e))
        if not_restored:
            # A link left down or a route left injected would corrupt every later result: stop the run instead
            raise LabError("could not restore after scenario: " + "; ".join(not_restored))
        applied = sum(inj.applied for inj in injected)
        if downed or applied:
            log(f"Restored {len(downed)} link(s) and {applied} route injection(s); settling {settle:g}s")
            _sleep(settle)
    return results
