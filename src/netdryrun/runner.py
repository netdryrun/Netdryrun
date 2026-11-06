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
from .drivers import BETA_DRIVERS, DriverError, Undetectable, check_supported, for_node, resolve
from .drivers.frr import LOAD_RAN, communicate_daemons, parse_config_load_errors
from .drivers.base import NoSuchInstance
from .faults import RouteInjection
from . import mgmt
from .lab import NXOS_KINDS, VM_KINDS, Lab, LabError

# Every wait in a run goes through these two names (looked up at call time), so tests can drive a whole
# run on a fake clock.
_clock = time.monotonic
_sleep = time.sleep
POLL = 3.0   # seconds between samples, as in checks.py

# Labs this process deployed and must destroy if it is killed (see destroy_active_labs)
_ACTIVE: set = set()


class _NodeWatch:
    """A sleep that first asks Docker, at most every `every` seconds of the run's clock, whether any node's container
    stopped. One did: LabError (exit 2), naming it with its last log lines. A check that samples a stopped node only
    sees command errors, and polling them to the timeout gave no verdict for as long as 23 minutes (0.4.1 acceptance,
    a VM node without KVM)."""

    def __init__(self, lab: Lab, sleep, every: float = 15.0):
        self.lab, self.sleep, self.every, self.last = lab, sleep, every, None

    def __call__(self, seconds: float) -> None:
        now = _clock()
        if self.last is None or now - self.last >= self.every:
            self.last = now
            stopped = self.lab.stopped_containers()
            if stopped:
                raise LabError("node container(s) stopped during the run, so no check can be evaluated: " +
                               "; ".join(f"{c} ({why})" for c, why in sorted(stopped.items())))
        self.sleep(seconds)


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
        """Set when the lab never reached a testable state (see checks.inconclusive_reason), or when every failed
        check is in a scenario whose injected routes never left their node (NeverLeft)."""
        if self.error:
            return None
        failed = [r for r in self.results if not r.passed]
        if failed and all(isinstance(r.detail, NeverLeft) for r in failed):
            return str(failed[0].detail)
        return inconclusive_reason(self.results)

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
    for node, name in sorted(config.drivers.items()):   # a set driver is checked against the node, never trusted
        if node in lab.nodes:
            resolve(lab.nodes[node], name)
    if full:
        for node in sorted({c.node for c in all_checks}):
            resolve(lab.nodes[node], config.drivers.get(node))
    for c in all_checks:
        check_supported(lab, c, config.drivers.get(c.node))
        node = lab.nodes[c.node]
        # a check in the management VRF or instance tests Docker's network, not the lab's (B3, R2)
        if (c.params.get("vrf") == "management" and node.kind in NXOS_KINDS) or \
                (c.params.get("vrf") == "mgmt" and node.kind in ("nokia_srlinux", "srl")):
            raise LabError(f"check '{c.name}' reads vrf {c.params['vrf']} on {c.node}: that is its management "
                           "network (Docker's), not a lab VRF")
        if node.kind in VM_KINDS or node.kind.startswith("vr-"):
            try:
                drv = resolve(node, config.drivers.get(c.node))
            except Exception:
                drv = None
            if drv in ("frr", "sonic"):
                # the frr/sonic drivers would run in the vrnetlab launcher's namespace, which keeps Docker's
                # default route, not in the VM (B3 adjacent, R12)
                raise LabError(f"node {c.node} is a VM kind ({node.kind}): the {drv} driver would read and ping from "
                               "the container that launches the VM, not from the router")
    for f in (f for sc in config.scenarios for f in sc.faults if f.kind == "inject_routes"):
        driver = resolve(lab.nodes[f.node], config.drivers.get(f.node))
        if driver != "frr":
            raise LabError(f"inject_routes on {f.node} ({driver}) is not supported yet: it needs an FRR node; "
                           "inject the routes from an FRR neighbor instead")
    if full:
        for f in (f for sc in config.scenarios for f in sc.faults if f.kind != "inject_routes"):
            lab._require_linux_links(f.node)
    for sc in config.scenarios:
        for f in (f for f in sc.faults if f.kind == "link_down"):
            # only an interface on a topology link is a lab link: management eth0, lo or a name not in links: would
            # take nothing down that the checks depend on, and every scenario check would pass (red team B-9001)
            ends = sorted({i for a, b in getattr(lab, "links", []) for n, i in (a, b) if n == f.node})
            if f.interface not in ends and f.interface not in {_container_iface(i) for i in ends}:
                raise LabError(f"scenario '{sc.name}': link_down {f.node} {f.interface}: not an interface of a link in "
                               f"the topology (links on {f.node}: {', '.join(ends) or 'none'}); a fault on any other "
                               "interface takes no lab link down")


def _warn_beta(config: Config, log) -> None:
    for node, name in sorted(config.drivers.items()):
        if name in BETA_DRIVERS:
            log(f"Warning: {node} uses the {name} driver, an unreleased beta: its verdicts are not covered by a "
                "released gate yet")


def check_topology(config: Config) -> Lab:
    """`netdryrun validate` past the file itself: load the topology (strictly) and make every pre-deploy
    check, without Docker or containerlab. Raises LabError or DriverError."""
    lab = Lab(config.lab)
    preflight(config, lab, full=True)
    return lab


def _driver_of(config: Config):
    """The driver a node runs as: the config's override, else detected from its kind and image; None: unknown."""
    def driver_of(name: str, node) -> str | None:
        try:
            return resolve(node, config.drivers.get(name))
        except DriverError:
            return None   # FRR in an image not named for it is still FRR: its rejected lines still count
    return driver_of


def _bound_files(lab, name: str) -> list[str]:
    """The binds and startup-config the topology gives a node (in its node entry, defaults, kinds or groups)."""
    from .verify.run import bind_reach
    try:
        targets = bind_reach(Path(lab.topology))
    except Exception:   # unreadable here: verify's and the run's own topology checks report it
        return ["(the topology's binds could not be read)"]
    return [f"{src}:{dest}" for src, where in targets.items() for node, dest in where if node == name]


# Where a file bound into docker-sonic-vs can change its config (CONFIG_DB, FRR, templates, supervisord's programs):
# a bind into, or above, any of these (multi-vendor audit F6)
SONIC_CONFIG_PLACES = ("/etc", "/usr", "/var/lib")


def _sonic_config_bind(bind: str) -> bool:
    if bind.startswith("(") or bind.endswith(":startup-config"):
        return True
    dest = bind.split(":", 2)[1] if ":" in bind else bind
    d = "/" + dest.strip("/")
    return d == "/" or any(d == p or d.startswith(p + "/") or p.startswith(d + "/") for p in SONIC_CONFIG_PLACES)


SRL_LOAD_FAILED = "Load of startup configuration failed"


def _startup_load(lab, name: str, driver: str, bound, deployed: bool = True) -> list[str] | None:
    """A non-FRR node's startup-config load ([]: clean, else why not), or None where no platform rule applies
    (recorded "not verified on <driver>"). On a lab this run didn't deploy (`check`), SR Linux and SONiC are not
    verified: SR Linux's deploy may have failed with the container still running, and no setup command ran on
    SONiC (multi-vendor audit F2)."""
    if driver == "eos":
        # cEOS skips a startup-config line it rejects and loads the rest, like FRR; it lists them (live, 4.36.3M)
        from .drivers.eos import STARTUP_ERRORS_CMD, parse_startup_config_errors
        r = lab.exec(name, ["Cli", "-p", "15", "-c", STARTUP_ERRORS_CMD])
        if r.rc != 0:
            return [f"its startup-config errors could not be read ({(r.stderr or r.stdout).strip()[-200:]}), so "
                    "whether its config loaded is unknown"]
        try:
            return parse_startup_config_errors(r.stdout)
        except DriverError as e:
            return [f"{e}; so whether its config loaded is unknown"]
    if driver == "routeros":
        # vrnetlab uploads the startup config over FTP and RouterOS runs it, stopping at the first line it rejects (live,
        # CHR 7.23.8). vrnetlab's own log says whether there was a config to upload and whether the upload worked
        r = lab.boot_log(name)
        if r.rc != 0 or "Startup complete in:" not in r.stdout:
            return ["its vrnetlab log doesn't show a completed startup, so whether its config loaded is unknown"]
        if "Pushing config via FTP" not in r.stdout:
            return []   # no startup config: nothing to load
        if "Giving up after" in r.stdout:
            return ["vrnetlab could not upload its startup config over FTP (it gave up), so the router runs without it"]
        from .drivers.routeros import RouterosDriver
        try:
            return RouterosDriver(lab, name).startup_errors()
        except DriverError as e:
            return [f"{e}; so whether its config loaded is unknown" if "unknown" not in str(e) else str(e)]
    if driver == "nxos":
        # vrnetlab types the startup config into the NX-OS VM after boot and logs NX-OS's answer to each line (live,
        # 10.4(8)): a rejected line is skipped and the rest loads, as on FRR and EOS
        from .drivers.nxos import parse_startup_log
        r = lab.boot_log(name)
        if r.rc != 0:
            return [f"its vrnetlab log could not be read ({(r.stderr or r.stdout).strip()[-200:]}), so whether its "
                    "config loaded is unknown"]
        try:
            return parse_startup_log(r.stdout)
        except DriverError as e:
            return [str(e)]
    if driver in ("srlinux", "sonic") and not deployed:
        return None
    if driver == "srlinux":
        # A CLI startup config is one commit containerlab applies at deploy: a line that doesn't parse, or a commit
        # that fails, fails the deploy (live, 26.7.2). A JSON one SR Linux loads itself, and when it rejects it the
        # deploy still succeeds and the node runs without it (live): its log says so (multi-vendor audit F3)
        r = lab.exec(name, ["grep", "-h", SRL_LOAD_FAILED, "/var/log/messages"])
        if r.rc == 1:   # grep: no such line
            return []
        if r.rc != 0:
            return [f"its startup-config load log could not be read ({(r.stderr or r.stdout).strip()[-200:] or 'rc '}"
                    f"{'' if (r.stderr or r.stdout).strip() else r.rc}), so whether its config loaded is unknown"]
        why = " ".join(r.stdout.split())
        return [f"it failed to load its startup config: {why[why.find(SRL_LOAD_FAILED):][:300]}"]
    if driver == "sonic":
        # docker-sonic-vs has no startup config: Netdryrun configures it with setup commands, each checked. A
        # config file bound into it is not checked: an error, never a silent pass
        files = [b for b in bound(name) if _sonic_config_bind(b)]
        if files:
            return [f"a config bound into a SONiC node is not checked ({', '.join(files[:3])}): configure SONiC "
                    "with setup commands (nodes.<name>.setup), which are checked"]
        return []
    return None


def config_load_by_node(lab, driver_of, bound=None, deployed: bool = True) -> dict[str, list[str]]:
    """Each node whose config load was read -> why the lab didn't run its config as written ([]: it did). FRR
    applies its config line by line at boot and skips a line it rejects (a typo, a command this release doesn't
    have): the lab then runs without it, and the checks test a network the change never reached. Read when every
    node has booted; a boot log that can't be read is no proof either. FRR nodes are always listed; a node whose
    driver is unknown only when its log shows rejected lines. (Other NOSes: see the config reference, "Config
    that fails to load".)"""
    bound = bound or (lambda name: _bound_files(lab, name))
    found: dict[str, list[str]] = {}
    for name, node in lab.nodes.items():
        if node.kind in ("bridge", "ovs-bridge"):   # no container, no config
            continue
        driver = driver_of(name, node)
        if driver not in ("frr", None):
            load = _startup_load(lab, name, driver, bound, deployed)
            if load is not None:
                found[name] = load
            continue
        r = lab.boot_log(name)
        if r.rc != 0:
            if driver == "frr":
                found[name] = [f"its boot log could not be read ({(r.stderr or r.stdout).strip()[-200:]}), "
                               "so whether its config loaded is unknown"]
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
            found[name] = errors
        elif driver == "frr" and not LOAD_RAN.search(r.stdout):
            found[name] = ["its boot log shows no sign of a config load (no vtysh boot output, no daemon config "
                           "line), so whether its config loaded is unknown. Netdryrun reads the config load FRR's "
                           "image runs at boot (frr.conf, vtysh -b)"]
        elif driver == "frr":
            found[name] = []
    return found


def rejected_config_message(by_node: dict[str, list[str]]) -> str:
    """The error for nodes that didn't run their config as written, or "" when every one did."""
    found = [f"{name}: {'; '.join(errors)}" for name, errors in by_node.items() if errors]
    if not found:
        return ""
    return ("The NOS rejected configuration lines at boot, so the lab ran without them and the checks did not test the "
            f"change as written: {' | '.join(found)}. Fix the config and run again.")


def run(config: Config, *, deploy: bool = True, keep: bool = False, keep_on_failure: bool = False,
        settle: float = 10.0, hold: float = 10.0,
        on_result: Callable[[Result], None] | None = None, log: Callable[[str], None] = lambda _: None) -> RunReport:
    report = RunReport(config=config, started=_now())
    eor_reported: set = set()   # untracked End-of-RIB warnings already given in this run (once per session)
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
        _warn_beta(config, log)
        if deploy:
            # A VM node can't boot without KVM: say so before deploying a lab that would never come up
            kvm = lab.kvm_problem()
            if kvm:
                raise LabError(kvm)
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
        # From here every wait also watches the nodes: a container that stops (a VM that couldn't boot, a NOS
        # that crashed) can never answer, so the run ends at once as an error instead of polling it to the timeout
        global _sleep
        unwatched, _sleep = _sleep, _NodeWatch(lab, _sleep)
        if deploy:
            for node, cmds in config.setup.items():
                log(f"Running setup on {node}...")
                lab.run_setup(node, cmds, log=log)
        # After setup:, before the first check: no route out of the lab over the management network (red team round
        # 4, B3; design e, option A): Docker's default route is deleted, any other is a run error
        every_check = config.checks + [c for sc in config.scenarios for c in sc.checks]
        state = mgmt.prepare(lab, every_check, log=log, sleep=_sleep)
        for n in sorted({c.node for c in every_check}):
            try:
                drv = resolve(lab.nodes[n], config.drivers.get(n))
            except Exception:
                continue   # no driver: for_node says so when the check runs
            mgmt.require_covered(lab, state, n, drv)
        env_nodes = report.environment.setdefault("nodes", {})
        for name, m in state.items():
            env_nodes.setdefault(name, {})["management_default"] = mgmt.describe(m, lab.nodes[name].kind)
        if any(m.removed for m in state.values()):
            # zebra withdraws a redistributed kernel default asynchronously: let routing settle before any check (R6)
            log(f"Management default routes removed; settling {settle:g}s before the checks...")
            _sleep(settle)

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
        mgmt.recheck(lab, "after the positive checks")
        _check_declared_peers(config.eor_not_sent, driver_for)
        if negatives or config.scenarios:
            settle, hold = _stretch_for_advertisement_intervals(lab, driver_for, config, settle, hold, log)
        if negatives:
            gate_warnings: dict[int, list[dict]] = {}
            not_converged = _bgp_convergence_gate(negatives, config.checks, drivers, log=log,
                                                  positive_results=report.results, warnings=gate_warnings,
                                                  lab=lab, extras=_routing_nodes(lab, driver_for),
                                                  eor_not_sent=config.eor_not_sent, eor_reported=eor_reported)
            if not positives:
                # nothing has proven convergence yet; give the control plane time to come up
                settle = max(settle, 30.0)
            log(f"Convergence checks done; settling {settle:g}s before post-convergence checks...")
            _sleep(settle)
            ready = [c for c in negatives if id(c) not in not_converged]
            mgmt.recheck(lab, "before the post-convergence checks")
            report.results += hold_together(ready, drivers, hold=hold, on_result=_with_warnings(gate_warnings, on_result),
                                            clock=_clock, sleep=_sleep)
            mgmt.recheck(lab, "after the post-convergence checks")
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
            mgmt.recheck(lab, f"before scenario '{sc.name}'")
            report.results += run_scenario(lab, sc, drivers, settle=settle, hold=hold, on_result=on_result, log=log,
                                           driver_for=driver_for, baseline_checks=config.checks,
                                           eor_not_sent=config.eor_not_sent, eor_reported=eor_reported)
            mgmt.recheck(lab, f"after scenario '{sc.name}'")
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
        by_node = config_load_by_node(lab, _driver_of(config), deployed=deploy)
        _config_load(lab, driver_for, report, by_node)
        rejected = rejected_config_message(by_node)
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
        if isinstance(_sleep, _NodeWatch):
            _sleep = unwatched
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

def warn(warnings: dict | None, check, code: str, node: str, text: str, session: str | None = None) -> None:
    """Record a convergence warning for one check (the gate's dict: id(check) -> list of warnings)."""
    if warnings is not None:
        warnings.setdefault(id(check), []).append({"code": code, "node": node, "session": session, "text": text})


def _with_warnings(warnings: dict[int, list[dict]], on_result=None):
    """An on_result callback that first adds the gate's warnings (if any) to the result, so they are in every
    output channel of each check they concern. The verdict is unchanged."""
    def add(r: Result) -> None:
        r.warnings.extend(warnings.get(id(r.check), []))
        if on_result:
            on_result(r)
    return add


def _config_load(lab, driver_for, report: RunReport, by_node: dict[str, list[str]]) -> None:
    """Each node's config load in the report (environment.nodes.<node>.config_load: "clean", why it didn't load
    as written, or "not verified on <driver>"), with its image digest and NOS version, so a verdict is tied to
    what ran."""
    nodes = report.environment.setdefault("nodes", {})
    for node in sorted(lab.nodes):
        try:
            drv = driver_for(node)
        except DriverError:
            # a host, or a router whose driver can't be detected: its load is read only if its log shows FRR's
            # rejected lines (an error then); otherwise it is said, never "clean" (multi-vendor audit F7)
            if lab.nodes[node].kind not in ("bridge", "ovs-bridge"):
                nodes.setdefault(node, {})["config_load"] = "not verified (no routing driver)"
            continue
        entry = nodes.setdefault(node, {})
        entry["nos_version"] = drv.nos_version()
        entry["image_digest"] = lab.image_digest(lab.nodes[node].image)
        if node not in by_node:
            entry["config_load"] = f"not verified on {drv.name}"
        else:
            entry["config_load"] = list(by_node[node]) or "clean"


ADV_MARGIN = 2.0   # seconds beyond the longest advertisement interval


def _stretch_for_advertisement_intervals(lab, driver_for, config: Config, settle: float, hold: float, log):
    """(settle, hold), each at least the longest advertisement interval (MRAI) any BGP session in the lab reports,
    plus a margin (0.3.2 multi-vendor audit). A peer sends at most once per interval, so a leak can arrive that
    long after the sessions look settled; with shorter windows a negative check samples a prefix count still
    stable at 0 and passes. A route that crosses several such peers can take one interval per hop: raise
    --settle for that."""
    vrfs = {"default"} | {c.params["vrf"] for c in config.checks if c.params.get("vrf")}
    vrfs |= {c.params["vrf"] for sc in config.scenarios for c in sc.checks if c.params.get("vrf")}
    longest, where = 0.0, ""
    for node in sorted(lab.nodes):
        try:
            drv = driver_for(node)
        except DriverError:
            continue   # a node without a routing driver (a host) sends no BGP updates
        for vrf in sorted(vrfs):
            try:
                neighbors = drv.bgp_neighbors(vrf).value
            except DriverError:
                continue   # no BGP there (yet): its sessions are judged by the gate and the checks
            for n in neighbors.values():
                if n.adv_interval is not None and n.adv_interval > longest:
                    longest, where = n.adv_interval, f"{node} (to {n.address}{'' if vrf == 'default' else f', vrf {vrf}'})"
    need = longest + ADV_MARGIN if longest > 0 else 0.0
    if need > min(settle, hold):
        log(f"{where} has an advertisement interval of {longest:g}s, so a route can arrive that late: settle and "
            f"hold extended to at least {need:g}s")
        settle, hold = max(settle, need), max(hold, need)
    return settle, hold


def _routing_nodes(lab, driver_for) -> dict:
    """Every lab node with a routing driver: node -> its driver, or the reason it has none that can be read (a beta
    NOS not chosen, a driver setting that doesn't match). A node no driver recognises (a Linux host, a bridge) runs no
    routing protocol Netdryrun can see and is left out."""
    out: dict = {}
    for node in sorted(getattr(lab, "nodes", {}) or {}):
        try:
            out[node] = driver_for(node)
        except Undetectable:
            continue
        except DriverError as e:
            out[node] = str(e)
    return out


def _far_ends(lab, declared: set[tuple[str, str, str]]) -> set[tuple[str, str, str]]:
    """The other end of each session the file declares not established, where the topology shows it, and nothing
    more: on the link whose subnet holds the declared neighbor address, the one peer that owns that address on its
    interface, keyed by the declaring node's own address in that same subnet (never its other addresses on the link,
    never the other peers on a shared segment: adversary finding on 6d66267, dual-stack and bridged links). For
    unnumbered BGP (the neighbor named by its interface), the peer interface, only when exactly one peer is on the
    link. A session the topology can't place (iBGP between loopbacks, a VM's interfaces) has no far end here; the gate
    then waits for it there as for any other session (a warning on another node, a block on the check's own)."""
    out: set[tuple[str, str, str]] = set()
    for node, vrf, key in declared:
        if not key:
            continue
        ip = _ip(str(key))
        for a, b in getattr(lab, "links", []):
            for n, iface in (a, b):
                if n != node:
                    continue
                peers = lab.peers_of(node, iface)
                if key == iface:
                    if len(peers) == 1:
                        out.add((peers[0][0], vrf, peers[0][1]))
                    continue
                if ip is None:
                    continue
                try:
                    mine = [x for x in lab.interface_addresses(node, iface)
                            if x.version == ip.version and ip in x.network and x.ip != ip]
                except Exception:
                    continue   # unreadable: no far end, so the far end is waited for (never excluded)
                if len(mine) != 1:
                    continue
                for peer, piface in peers:
                    try:
                        theirs = {x.ip for x in lab.interface_addresses(peer, piface)}
                    except Exception:
                        continue
                    if ip in theirs:
                        out.add((peer, vrf, str(mine[0].ip)))
    return out


def _bgp_convergence_gate(negatives: list[Check], all_checks: list[Check], drivers: dict,
                          log=lambda _: None, positive_results: list[Result] = (),
                          warnings: dict[int, list[dict]] | None = None,
                          expected_down: set[tuple[str, str, str]] = frozenset(),
                          lab=None, extras: dict | None = None, eor_not_sent: frozenset = frozenset(),
                          eor_reported: set | None = None) -> dict[int, Result]:
    """Wait for BGP convergence before the post-convergence checks; returns the checks it blocked.

    Own nodes (a node with post-convergence checks, in each VRF they name): every session up, except those declared
    not established, with prefix counts stable over two samples; still down at the cap blocks that node's checks.
    Other routing nodes (`extras`, design round 3 "G"): every lab node with a routing driver, in the default VRF and
    every VRF the file's checks name, waited on up to the same cap (the longest timeout of the post-convergence
    checks), warning-only: at the cap a session still down, counts still moving or state that can't be read there is a
    warning on every post-convergence check, never a block. Counts still moving on an own node at the cap go ahead
    with a warning too (W2).

    End-of-RIB (design round 3, R3): once every session is up, a session whose End-of-RIB is "pending" or "unknown"
    (Driver.end_of_rib) is not settled: its table may still be arriving. At the cap that blocks the own node's checks
    and is a warning elsewhere. A peer declared `eor: not_sent` is not waited for. A session with graceful restart not
    negotiated ("untracked") settles by the count rule, with one warning per run and session (`eor_reported`)."""
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
    declared = {(c.node, c.params.get("vrf", "default"), c.params.get("neighbor")) for c in all_checks
                if c.type == "bgp_session" and c.params.get("state", "established") != "established"}
    excluded = set(declared) | set(expected_down)   # in a scenario: the sessions over the links it took down
    if declared and lab is not None:
        excluded |= _far_ends(lab, declared)         # a session declared down is down at both ends
    # nodes the file says run BGP: any BGP check on them, or a route check that names protocol bgp
    bgp_checks = [c for c in all_checks if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")]
    bgp_nodes = {c.node for c in bgp_checks}
    # and the VRFs they say it runs BGP in: a node's other VRFs may have no BGP at all (round 4 code adversary, 1)
    bgp_groups = {(c.node, c.params.get("vrf", "default")) for c in bgp_checks}
    deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
    cap = max(deadline.values(), default=0.0)
    vrfs = {"default"} | {c.params["vrf"] for c in all_checks if c.params.get("vrf")}
    extra_drivers: dict[tuple[str, str], object] = {}
    if groups:
        for node, drv in (extras or {}).items():
            if node in dead:
                continue
            for vrf in sorted(vrfs):
                if (node, vrf) not in groups:
                    extra_drivers[(node, vrf)] = drv
                    deadline[(node, vrf)] = cap
    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": [],
              "down": [], "reads": 0, "error": "", "eor_wait": [], "untracked": set()}
          for g in list(groups) + list(extra_drivers)}
    started = _now()
    t0 = _clock()
    pending = set(groups) | set(extra_drivers)
    first = True
    blocked: dict[int, Result] = {}
    extra_warnings: list[tuple[str, str, str | None, str]] = []   # (code, node, session, text)

    def warn_extra(g, code: str, text: str, session: str | None = None) -> None:
        log(f"warning: {text}")
        extra_warnings.append((code, g[0], session, text))

    while pending:
        for g in sorted(pending):
            node, vrf = g
            s = st[g]
            t = _clock() - t0
            where = "" if vrf == "default" else f" (vrf {vrf})"
            is_extra = g in extra_drivers
            s["reads"] += 1
            if is_extra and isinstance(extra_drivers[g], str):
                pending.discard(g)
                warn_extra(g, "gate-unreadable", f"convergence: {node} was not watched before this check ran "
                           f"({extra_drivers[g]})")
                continue
            try:
                nbrs = (extra_drivers[g] if is_extra else drivers[node]).bgp_neighbors(vrf).value
            except Exception as e:
                if (not is_extra and first and g not in bgp_groups and isinstance(e, NoSuchInstance)
                        and all(c.type == "ping" for c in groups[g])):
                    # a ping-only node no check says runs BGP, with no BGP instance at all: nothing to wait for. Any
                    # other failed read (a bgpd still starting) is an unready sample like any node's, and a node never
                    # readable by the cap is warned or blocked there (red team round 4, B2, design m4)
                    pending.discard(g)
                    continue
                if is_extra and isinstance(e, NoSuchInstance) and (vrf != "default" or node not in bgp_nodes):
                    pending.discard(g)   # no such VRF, or no BGP on a node no check says runs it: nothing to wait for
                    continue
                if is_extra and not s["answered"] and s["reads"] == 1 and not isinstance(e, NoSuchInstance):
                    pending.discard(g)   # a first read that fails is a warning, not a wait on a broken CLI
                    warn_extra(g, "gate-unreadable", f"convergence: {node}'s BGP state{where} could not be read "
                               f"before this check ran ({' '.join(str(e).split())[:200]})")
                    continue
                s["streak"], s["detail"], s["empty"], s["down"] = 0, Unready(f"BGP state unreadable on {node}: {e}"), False, []
                s["error"] = str(e) or type(e).__name__
                s["history"].append(_sample(t, False, s["detail"]))
                continue
            s["answered"] = True
            s["empty"] = not nbrs
            s["error"] = ""
            if not nbrs:
                if is_extra and node not in bgp_nodes and s["reads"] == 1:
                    pending.discard(g)   # a routing node with no BGP configured (static or IGP only)
                    continue
                # No neighbors at all is what a node answers before its BGP config is applied: not converged
                # (a leak can arrive once it is), so keep waiting, up to the cap
                s["streak"], s["detail"], s["down"] = 0, Unready(f"no BGP neighbors at all on {node}{where}"), []
                s["history"].append(_sample(t, False, s["detail"]))
                continue
            down = sorted((a, n.state) for a, n in nbrs.items()
                          if n.state != "established" and (node, vrf, a) not in excluded)
            if down:
                s["down"] = down
                s["streak"], s["detail"] = 0, (f"BGP session(s) on {node}{where} not established: "
                                               + ", ".join(f"{a} ({state})" for a, state in down))
                s["history"].append(_sample(t, False, s["detail"]))
                continue
            s["down"] = []
            drv = extra_drivers[g] if is_extra else drivers[node]
            read_eor = getattr(drv, "end_of_rib", None)
            eor: dict = {}
            if read_eor is not None:
                try:
                    eor = read_eor(vrf, nbrs) or {}
                except Exception:   # never raises by contract; a driver that does reads unknown
                    eor = {a: {"*": "unknown"} for a, n in nbrs.items() if n.state == "established"}
            waiting, untracked = [], set()
            for a, fams in sorted(eor.items()):
                if (node, vrf, a) in excluded or not isinstance(fams, dict):
                    continue
                carried = {f for f, n in getattr(nbrs.get(a), "prefixes", {}).items() if n}
                if "*" not in fams and carried - set(fams):
                    # routes in a family the End-of-RIB read doesn't list: graceful restart wasn't negotiated for it,
                    # so its End-of-RIB can't be tracked: judged by stable counts, warned once (round 4, h)
                    untracked.add(a)
                for fam, state in sorted(fams.items()):
                    if state == "untracked":
                        untracked.add(a)
                    elif state == "pending" or (state != "received"
                                                and (node, vrf, _canon_ip(a)) not in eor_not_sent):
                        # eor: not_sent excuses only what can't be read; a "pending" read is the table still
                        # arriving, and the declaration never weakens a read (design M7)
                        waiting.append((a, fam, state))
            s["untracked"] |= untracked
            s["eor_wait"] = waiting
            if waiting:
                s["streak"], s["detail"] = 0, (f"End-of-RIB not received on {node}{where} from: "
                                               + ", ".join(f"{a} ({'all families' if f == '*' else f}: {st_})"
                                                           for a, f, st_ in waiting))
                s["history"].append(_sample(t, False, s["detail"]))
                continue
            # received counts too, where the driver knows more were received than it counts (Junos hidden routes):
            # a route still arriving there is churn even when the accepted count holds still
            counts = {a: (dict(n.prefixes), dict(n.prefixes_upto)) for a, n in nbrs.items()}
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
            where = "" if g[1] == "default" else f" (vrf {g[1]})"
            if g in extra_drivers:
                if s["eor_wait"] and not s["down"]:
                    for a, fam, state in s["eor_wait"]:
                        warn_extra(g, "gate-eor-pending", f"convergence: {g[0]}'s session to {a}{where} had not sent "
                                   f"End-of-RIB ({'all families' if fam == '*' else fam}: {state}) when this check ran "
                                   f"(waited {deadline[g]:g}s); its routes may still have been arriving", session=a)
                elif s["down"]:
                    for a, state in s["down"]:
                        warn_extra(g, "gate-session-down", f"convergence: {g[0]}'s session to {a}{where} was not "
                                   f"established ({state}) when this check ran (waited {deadline[g]:g}s). If it is "
                                   f"down on purpose, add a bgp_session check on {g[0]} with state: down for it: the "
                                   "gate then doesn't wait for it", session=a)
                elif s["error"] or not s["answered"]:
                    warn_extra(g, "gate-unreadable", f"convergence: {g[0]}'s BGP state{where} could not be read "
                               f"by the cap ({deadline[g]:g}s): {' '.join(s['error'].split())[:200]}")
                elif s["empty"]:
                    warn_extra(g, "gate-no-neighbors", f"convergence: {g[0]} reported no BGP neighbors{where} by "
                               f"the cap ({deadline[g]:g}s), although checks in the file expect BGP on it")
                else:
                    warn_extra(g, "gate-counts-moving", f"convergence: {g[0]}'s BGP prefix counts{where} were still "
                               f"changing when this check ran (waited {deadline[g]:g}s)")
                continue
            if not s["answered"] and g in bgp_groups:
                # never readable on a node the file says runs BGP: nothing showed it converged, so its post-convergence
                # checks are not evaluated, as with no neighbors at all (red team round 4, B1)
                for c in groups[g]:
                    detail = Unready(f"not evaluated: {g[0]}'s BGP state{where} could not be read by the cap "
                                     f"({deadline[g]:g}s): {' '.join(s['error'].split())[:200]}. A post-convergence "
                                     "check means nothing before the node's BGP state shows it converged")
                    blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                            s["history"][-50:], samples_passed=0,
                                            samples_unready=len(s["history"]))
            elif not s["answered"]:
                text = (f"convergence: {g[0]}'s BGP state{where} could not be read by the cap ({deadline[g]:g}s); the "
                        "check was evaluated without the BGP gate")
                log(f"warning: {text}")
                for c in groups[g]:
                    warn(warnings, c, "gate-unreadable", g[0], text)
            elif s["empty"] and g[0] in bgp_nodes:
                # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                # leak guard would pass on the empty table. Not evaluated, every sample unready.
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
                text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                        "without BGP convergence")
                log(f"warning: {text}")
                for c in groups[g]:
                    warn(warnings, c, "no-bgp-neighbors", g[0], text)
            elif s["streak"] == 0 and s["eor_wait"] and not s["down"]:
                for c in groups[g]:
                    detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence check "
                              "only means something once the node's neighbors have sent their whole table (End-of-RIB). "
                              f"For a peer that never sends End-of-RIB, declare nodes.{g[0]}.peers."
                              f"{'' if g[1] == 'default' else g[1] + '/'}<address>.eor: not_sent")
                    blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                            s["history"][-50:], samples_passed=0,
                                            samples_unready=sum(bool(h.get("unready")) for h in s["history"]))
            elif s["streak"] == 0:
                for c in groups[g]:
                    detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
                              "check only means something once every BGP session on its node is up (a leak can "
                              "arrive over any of them). If a session is down on purpose, add a bgp_session check "
                              "with state: down for it")
                    blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                            s["history"][-50:], samples_passed=0,
                                            samples_unready=sum(bool(h.get("unready")) for h in s["history"]))
            else:
                # established but prefix counts still moving at the deadline: go ahead, with a warning (W2)
                text = (f"convergence: {g[0]}'s BGP prefix counts{where} were still changing when this check ran "
                        f"(waited {deadline[g]:g}s)")
                log(f"warning: {text}")
                for c in groups[g]:
                    warn(warnings, c, "gate-counts-moving", g[0], text)
        if pending:
            nearest = min(deadline[g] for g in pending) - (_clock() - t0)
            _sleep(max(0.0, min(POLL, nearest)))
    for code, node, session, text in extra_warnings:
        for c in negatives:
            if id(c) not in blocked:
                warn(warnings, c, code, node, text, session=session)
    # untracked End-of-RIB: once per run and session, on the first post-convergence check that ran
    first_ready = next((c for c in negatives if id(c) not in blocked), None)
    for g in sorted(st):
        for a in sorted(st[g]["untracked"]):
            key = (g[0], g[1], a)
            if first_ready is None or (eor_reported is not None and key in eor_reported):
                continue
            if eor_reported is not None:
                eor_reported.add(key)
            where = "" if g[1] == "default" else f" (vrf {g[1]})"
            text = (f"convergence: {g[0]}'s session to {a}{where} doesn't negotiate graceful restart, so its "
                    "End-of-RIB can't be tracked; the gate judged it by stable prefix counts only (a route can still "
                    "arrive later)")
            log(f"warning: {text}")
            warn(warnings, first_ready, "eor-untracked", g[0], text, session=a)
    return blocked


def _container_iface(name: str) -> str:
    """The container interface behind a containerlab interface alias (cEOS `Ethernet1` is `eth1`, SR Linux
    `ethernet-1/1` is `e1-1`); any other name is itself."""
    import re as _re
    m = _re.fullmatch(r"Ethernet(\d+)", name)
    if m:
        return f"eth{m.group(1)}"
    m = _re.fullmatch(r"ethernet-(\d+)/(\d+)", name)
    return f"e{m.group(1)}-{m.group(2)}" if m else name


def _check_declared_peers(declared, driver_for) -> None:
    """Each `nodes.<node>.peers.<address>.eor: not_sent` must name a BGP session the node has: one that names none is a
    config error (a typo would otherwise excuse nothing, silently). Read once the lab is up (after the positive
    checks), so a session that is configured but down still counts."""
    by_node: dict[tuple[str, str], list[str]] = {}
    for node, vrf, addr in sorted(declared):
        by_node.setdefault((node, vrf), []).append(addr)
    for (node, vrf), addrs in by_node.items():
        have = None
        for attempt in range(3):
            try:
                have = {_canon_ip(k) for k in driver_for(node).bgp_neighbors(vrf).value}
                break
            except NoSuchInstance:
                have = set()
                break
            except DriverError:
                if attempt == 2:
                    raise
                _sleep(POLL)
        missing = [a for a in addrs if a not in have]
        if missing:
            where = "" if vrf == "default" else f"{vrf}/"
            raise ConfigError(f"nodes.{node}.peers.{where}{missing[0]}: {node} has no BGP session to {missing[0]}"
                              f"{'' if vrf == 'default' else f' in vrf {vrf}'} (its sessions: "
                              f"{', '.join(sorted(have)) or 'none'}); eor: not_sent must name one of them")


def _canon_ip(addr: str) -> str:
    try:
        return str(ipaddress.ip_address(str(addr).split("%")[0]))
    except ValueError:
        return str(addr)


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
                 on_result=None, log=lambda _: None, driver_for=None, baseline_checks: list[Check] = (),
                 eor_not_sent: frozenset = frozenset(), eor_reported: set | None = None) -> list[Result]:
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
    # With injected routes, a check's result is shown once the delivery verdict is known: a PASS streamed now could
    # turn inconclusive after restore, and the console must never say PASS for it (Layer 6 round 7 on 99fe33e)
    show, held = on_result, any(f.kind == "inject_routes" for f in sc.faults)
    if held:
        on_result = None
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
                if lab.admin_up(f.node, iface):
                    # the flag, not the state column: a veth whose peer is down reads LOWERLAYERDOWN while admin-up
                    raise LabError(f"scenario '{sc.name}': {f.node} {iface} is still administratively up after "
                                   "`ip link set down`: the fault did not take effect")
        if links:
            _wait_fault_visible(watch, driver_for, max(c.timeout for c in sc.checks), sc, log=log)
        for inj in injected:   # the checks run once the routes left, not before (Layer 6 round 6 on 1a597d7)
            if inj.applied:
                log(f"  waiting until {inj.node}'s BGP peers are sent its injected routes")
                inj.await_delivery(settle)
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
            gate_warnings: dict[int, list[dict]] = {}
            blocked = _bgp_convergence_gate(negatives, list(baseline_checks) + sc.checks, drivers, log=log,
                                            positive_results=pos_results, warnings=gate_warnings,
                                            expected_down=over_links, lab=lab, extras=_routing_nodes(lab, driver_for),
                                            eor_not_sent=eor_not_sent, eor_reported=eor_reported)
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
            # A link left down or a route left injected would corrupt every later result: stop the run instead. The
            # results held for the delivery verdict are shown first, judged as never-left ones would be (round 8)
            if held and show:
                for r in _never_left(injected, results, log):
                    show(r)
            raise LabError("could not restore after scenario: " + "; ".join(not_restored))
        applied = sum(inj.applied for inj in injected)
        if downed or applied:
            log(f"Restored {len(downed)} link(s) and {applied} route injection(s); settling {settle:g}s")
            _sleep(settle)
    results = _never_left(injected, results, log)
    if held and show:
        for r in results:
            show(r)
    return results


def _some(prefixes: list[str]) -> str:
    return ", ".join(prefixes[:5]) + (f" and {len(prefixes) - 5} more" if len(prefixes) > 5 else "")


class NeverLeft(Unready):
    """The detail of a scenario check whose injected routes never left the injecting node: the scenario tested
    nothing, and the run is inconclusive unless something else failed (RunReport.inconclusive_reason)."""


def _never_left(injected: list[RouteInjection], results: list[Result], log=lambda _: None) -> list[Result]:
    """A scenario's results, or, when an injected prefix didn't provably reach a BGP peer of its node (RouteInjection's
    one rule: the session up at apply and at restore, never reset, and the prefix in its advertised routes before the
    checks ran and after), or its family had no established session, every passed check not passed and inconclusive
    (acceptance round B-5; every peer: Layer 6 on b03cb7a; every prefix: round 3 on 5e65852). Every passed check, not
    only the ones that would pass on missing routes: "the attack had no effect" checks (the legitimate best path stays,
    the session stays up, ping works, `min` holds) pass on routes that never arrived too (round 6 on 1a597d7). A
    check that failed stays failed: routes that never left can't have made it fail (Layer 6 on b03cb7a)."""
    quiet = [inj for inj in injected if inj.applied and inj.left is not True]
    if not quiet:
        return results
    inj = quiet[0]
    if inj.quiet:   # a check on the far side of one of these peers passed on nothing (Layer 6)
        held = "; ".join(f"{peer} was not sent {_some(missing)}" for peer, missing in inj.quiet.items())
        text = (f"inconclusive: the injected routes on {inj.node} did not all reach its BGP peers: {held} (not in the "
                "routes it advertised to them while the routes were in, or the session wasn't up from when they went in "
                "until then without a reset: an outbound filter, or a session that went down, reset or came up while "
                "the checks ran), so this scenario tested nothing")
    elif inj.unsent:
        why = "; ".join(f"no established {afi} BGP session there carries {_some(prefixes)}"
                        for afi, prefixes in inj.unsent.items())
        text = f"inconclusive: the injected routes never left {inj.node}: {why}, so this scenario tested nothing"
    else:
        text = (f"inconclusive: the injected routes on {inj.node} may not have left: its BGP sessions or advertised "
                "routes could not be read, so this scenario tested nothing")
    detail = NeverLeft(text)
    log(f"  {detail}")
    return [replace(r, passed=False, detail=detail, samples_passed=0) if r.passed else r for r in results]
