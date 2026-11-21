"""Oracle FP-043-FRRIMPORTCHK: on FRR, a `network` statement with no route behind it stays announced for the life of the
lab when bgpd applied it before its zebra connection was up, while production withdraws the prefix.

FRR bgpd (10.4.1; the same code in 8.5.4, 10.2.1 and master): a `network P` applied before the zebra connection is up
passes the import check (bgp_isvalid_nexthop() answers valid while there is no zebra connection), its nexthop-tracking
registration fails, and bgp_nht_register_nexthops() never sends it again (it walks the nexthop cache, not the
import-check table). The path stays `valid, sourced, local, best` and advertised whatever zebra's RIB holds. bgpd shows
the contradiction itself: the import-check entry is invalid and "Is not Registered" (JSON `"isRegistered": false`)
next to that valid sourced path. In a lab this happens on most boots; a router changed while running (production) has
the import check registered and withdraws the prefix. So a change that removes the route behind a `network` statement
is approved, by `run`/`check` and by `verify`.

Captured live (tests/fixtures/SOURCES.yml; tests/fixtures/frr_fp043ic/lab/capture.sh and record.py): every answer is
the exact bytes Docker returned for one command netdryrun (or the capture) ran in a node, kept as a JSON string (UTF-8,
checked lossless) with node, argv, rc and the sha256 of the raw bytes, in the phase's phase.json. Boots:
- uw: the user's two-router lab, r1 `network 198.51.100.0/24` with no route behind it, r2 its eBGP neighbor; `route
  r2 198.51.100.0/24 present: true` must fail. It never stuck live (0 of 6 boots alone, 0 of 5 beside three more
  FRR routers, uwl): it is the guards' healthy user lab, with r1's import check registered and the prefix withdrawn.
- c18: corpus v2 case 18 as changed (pe1's `ip route 192.0.2.0/24 blackhole` deleted, `network 192.0.2.0/24` kept);
  the two I2 checks (up1, peer1 have 192.0.2.0/24, protocol bgp) must fail. pe1 was stuck on 7 of 11 fresh boots;
  netdryrun (origin/main) passed both checks live on every stuck boot recorded (boot/report_c18_present_true.json)
  and failed them on every boot where pe1 was registered. ce1, peer1 and up1 (backed networks) were stuck on 8 of the
  11 too, beside a stuck and a registered pe1 alike; all five registered on 2. c18base: the unchanged base (verify's
  before side); pe1 was stuck on 1 of 2 boots there, with the discard route behind its network.
Stuck boots were then remedied live on the originating router only: the import check toggled off and on in one vtysh
call (`no bgp network import-check`, `bgp network import-check`); 15 s later its entry was registered, the unbacked
prefix withdrawn, and the same reads were recorded again ("remedied").

The replay answers exactly what was recorded in the current phase (the latest answer to that command); anything else
answers rc 1. The remedy above, sent to the originating router, moves the replay to the remedied phase, so a fix that
remedies is judged on what the routers did after it. A fix that remedies some other way meets rc 1 and must end as an
error. The runs go through public paths: runner.run on the recorded lab (as `netdryrun run` and as `netdryrun check`),
and verify() with real_side (as `netdryrun verify`); the labs are replaced, nothing else.

DERIVED answers (built in the tests below, never fixtures) are marked so: each starts from a live answer and changes
only what its test names.

The rule: no verdict is taken from a lab where an FRR router with import check enabled holds a `network` whose
import-check entry is not registered, or invalid next to a valid sourced path: the run remedies it before judging (the
remedied state is then judged) or ends as an error. A read of the import-check table that fails, isn't recognized, or
lacks an entry for a configured `network` (`{}` included) is an error, never "nothing stuck". Guards (healthy boots,
the remedied state, the captures' own claims) are in tests/test_oracle_guards_fp_043_frrimportchk.py.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun import checks as checks_mod
from netdryrun import runner
from netdryrun.lab import ExecResult, Lab

ROOT = Path(__file__).resolve().parents[3]
FX = ROOT / "tests" / "fixtures" / "frr_fp043ic"
LABS = {   # lab -> (checks file, originating router, its prefix)
    "uw": ("uw_present_true.yml", "r1", "198.51.100.0/24"),
    "c18": ("c18_present_true.yml", "pe1", "192.0.2.0/24"),
}
STUCK = {"c18": "c18_stuck_boot1"}   # uw never stuck live (see the docstring)
STUCK_ALL = [("c18", "c18_stuck_boot1"), ("c18", "c18_stuck_boot2")]     # every stuck boot kept
# Registered everywhere (lab, boot, phase): no router has anything to remedy, so a fix judges these as main does.
# c18_stuck_boot2 after its live remedy too (on c18_stuck_boot1, ce1, peer1 and up1 stayed stuck after pe1's remedy).
HEALTHY = {"uw": ("uw_healthy_boot1", "boot"), "c18": ("c18_healthy_boot12", "boot")}
HEALTHY_ALL = [("uw", "uw_healthy_boot1", "boot"), ("c18", "c18_healthy_boot12", "boot"),
               ("c18", "c18_healthy_boot13", "boot"), ("c18", "c18_stuck_boot2", "remedied")]
BASE = "c18base_healthy_boot1"          # verify's before side (corpus v2 base, unchanged)
BASE_STUCK = "c18base_stuck_boot2"      # the base stuck too: pe1's network backed by the discard route, still unregistered
TEXT = "show bgp import-check-table detail"
JSON = "show bgp import-check-table detail json"
NOT_REGISTERED = "Is not Registered"


def _text(s: str) -> str:   # what lab._run's text=True gives netdryrun from these bytes (universal newlines)
    return s.replace("\r\n", "\n").replace("\r", "\n")


def phase(boot: str, name: str) -> dict:
    """{(node, how, argv): ExecResult} of one recorded phase: the latest answer to each command."""
    out = {}
    for e in json.loads((FX / boot / name / "phase.json").read_text(encoding="utf-8")):
        out[(e["node"], e["how"], tuple(e["argv"]))] = ExecResult(e["argv"], e["rc"], _text(e["stdout"]),
                                                                  _text(e["stderr"]))
    return out


def captured(boot: str, node: str, cmd: str, ph: str = "boot") -> str:
    return phase(boot, ph)[(node, "exec", ("vtysh", "-c", cmd))].stdout


class RecordedLab:
    """One recorded boot. Nodes and links come from the topology file; exec answers what the node answered in the
    current phase. No Docker: the management-route step has nothing to read (the routes were removed live by the
    recorded `check`), as on the unit tests' fake labs."""

    def __init__(self, boot: str, topology: Path, origin: str, derived: dict | None = None):
        real = Lab(Path(topology))
        self.name, self.topology, self.nodes, self.links = real.name, real.topology, real.nodes, real.links
        self.boot, self.origin, self.phase, self.start = boot, origin, "boot", "boot"
        self.phases = {p.name: phase(boot, p.name) for p in (FX / boot).iterdir() if (p / "phase.json").is_file()}
        self.derived = derived or {}   # (node, argv) -> ExecResult built in a test: DERIVED
        self.asked: list = []
        self.remedies = 0

    def _answer(self, node, how, cmd):
        cmd = list(cmd)
        self.asked.append((node, how, cmd))
        if how == "exec" and node == self.origin and self._remedy(cmd):
            self.remedies += 1
            if "remedied" in self.phases:
                self.phase = "remedied"
                r = json.loads((FX / self.boot / "remedy.json").read_text(encoding="utf-8"))
                return ExecResult(cmd, 0, _text(r["stdout"]), _text(r["stderr"]))
        if self.phase == self.start and (node, tuple(cmd)) in self.derived:   # before any remedy only
            return self.derived[(node, tuple(cmd))]
        got = self.phases[self.phase].get((node, how, tuple(cmd)))
        if got is not None:
            return ExecResult(cmd, got.rc, got.stdout, got.stderr)
        return ExecResult(cmd, 1, "", f"not recorded on {node} in phase {self.phase}: {' '.join(cmd)}")

    @staticmethod
    def _remedy(cmd: list[str]) -> bool:
        args = [a.strip() for a in cmd[1:] if a != "-c"] if cmd[:1] == ["vtysh"] else []
        return ("no bgp network import-check" in args and "bgp network import-check" in args
                and args.index("bgp network import-check") > args.index("no bgp network import-check"))

    def exec(self, node, cmd, timeout=60, input=None):
        return self._answer(node, "exec", cmd)

    def exec_root(self, node, cmd, timeout=60):
        return self._answer(node, "exec_root", cmd)

    def boot_log(self, node):
        logs = [(k, v) for k, v in self.phases[self.phase].items() if k[0] == node and k[1] == "boot_log"]
        if not logs:
            return ExecResult(["docker", "logs"], 1, "", "not recorded")
        r = logs[-1][1]
        return ExecResult(r.cmd, r.rc, f"{r.stdout}\n{r.stderr}", r.stderr)

    def image_digest(self, image):
        return None

    def check_tools(self):
        pass

    def version(self):
        return "0.81.1"

    def kvm_problem(self):
        return None

    def acquire_lock(self):
        pass

    def release_lock(self):
        pass

    def existing_containers(self):
        return set()

    def deploy(self):
        return ExecResult([], 0, "", "")

    def destroy(self):
        return ExecResult([], 0, "", "")

    def running_containers(self):
        return {n.container for n in self.nodes.values()}

    def stopped_containers(self):
        return {}

    def run_setup(self, *a, **k):
        pass


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, s)


def fake_time(monkeypatch, clock):
    import time as real_time
    fake = SimpleNamespace(sleep=clock.sleep, monotonic=clock, time=lambda: real_time.time() + clock.t)
    monkeypatch.setattr(runner, "_clock", clock, raising=False)
    monkeypatch.setattr(runner, "_sleep", clock.sleep, raising=False)
    monkeypatch.setattr(runner, "time", fake)
    for name in ("run_round_robin", "hold_together"):
        orig = getattr(checks_mod, name)
        monkeypatch.setattr(runner, name, lambda *a, _o=orig, **k: _o(*a, **{**k, "clock": clock, "sleep": clock.sleep}))
    from netdryrun.verify import converge
    from netdryrun.verify import run as vrun
    monkeypatch.setattr(vrun, "time", fake)
    monkeypatch.setattr(converge, "time", fake)
    orig_stable = converge.stable_snapshot
    monkeypatch.setattr(vrun, "stable_snapshot",
                        lambda *a, **k: orig_stable(*a, **{**k, "clock": clock, "sleep": clock.sleep}))


def judged(monkeypatch, lab_key: str, boot: str, deploy: bool, derived: dict | None = None, checks: str | None = None,
           start: str = "boot"):
    """runner.run on the recorded boot, the way `netdryrun run` (deploy) or `netdryrun check` runs it."""
    yml, origin, _ = LABS[lab_key]
    config = runner.load_config(FX / "lab" / (checks or yml))
    lab = RecordedLab(boot, config.lab, origin, derived)
    lab.phase = lab.start = start
    fake_time(monkeypatch, Clock())
    monkeypatch.setattr(runner, "Lab", lambda path: lab)
    return runner.run(config, deploy=deploy), lab


def summary(rep) -> str:
    return f"status {rep.status}, error {rep.error!r}, " + "; ".join(
        f"{r.check.name}: {'PASS' if r.passed else 'FAIL'} ({r.detail})" for r in rep.results)


C18_INTENT = """# the ticket: pe1's discard route for 192.0.2.0/24 looks unused and goes away; whatever that does to 192.0.2.0/24
# itself is left to the standing guards (the base branch's checks: the upstream and the peer keep our aggregate)
intent:
  - config_change_on: [pe1]
allow_anywhere: ["192.0.2.0/24"]
"""
C18_GUARDS = FX / "lab" / "c18_present_true.yml"   # corpus v2 I2 (specs/intent.yml): up1 and peer1 have 192.0.2.0/24


def verified(monkeypatch, tmp_path, before_boot: str, after_boot: str, after_phase: str = "boot"):
    """`netdryrun verify` on case 18: before = corpus v2 base, after = the case's edit, each side's boots (the first
    and the determinism rerun) replayed from the given recorded boot (the after side from after_phase)."""
    from netdryrun.verify import run as vrun
    base = ROOT / "corpus" / "v2" / "base"
    sides = {}
    for label, edit in (("before", False), ("after", True)):
        d = tmp_path / label
        shutil.copytree(base, d)
        (d / "topology.clab.yml").rename(d / "c18_topology.clab.yml")
        if edit:
            p = d / "configs" / "pe1.conf"
            p.write_text(p.read_text(encoding="utf-8").replace("ip route 192.0.2.0/24 blackhole\n", ""), encoding="utf-8")
    labs = []

    def lab_for(topology):
        conf = (Path(topology).parent / "configs" / "pe1.conf").read_text(encoding="utf-8")
        boot = before_boot if "ip route 192.0.2.0/24 blackhole" in conf else after_boot
        lab = RecordedLab(boot, FX / "lab" / "c18_topology.clab.yml", "pe1")
        if boot == after_boot:
            lab.phase = lab.start = after_phase
        labs.append(lab)
        return lab
    monkeypatch.setattr(vrun, "Lab", lambda topology: lab_for(topology) if sides.get("ready") else Lab(topology))
    monkeypatch.setattr(runner, "Lab", lambda path: labs[-1])   # the standing guards run on the after lab, as booted
    fake_time(monkeypatch, Clock())
    intent = tmp_path / "intent.yml"
    intent.write_text(C18_INTENT, encoding="utf-8")
    topo = tmp_path / "before" / "c18_topology.clab.yml"
    orig_materialize = vrun.materialize

    def materialize(*a, **k):   # the sides are read from disk as given; only the booted labs are replayed
        s = orig_materialize(*a, **k)
        sides["ready"] = True
        return s
    monkeypatch.setattr(vrun, "materialize", materialize)
    res = vrun.verify(str(topo), str(tmp_path / "before"), str(tmp_path / "after"), str(intent), guards=str(C18_GUARDS))
    return res, labs


# ------------------------------------------------------------------------------------------------ the stuck boots

@pytest.mark.parametrize("deploy", [True, False], ids=["run", "check"])
@pytest.mark.parametrize("lab_key,boot", STUCK_ALL, ids=[b for _, b in STUCK_ALL])
def test_stuck_import_check_is_never_judged_passing(monkeypatch, lab_key, boot, deploy):
    """The stuck boot: the originating router announces a prefix it has no route for, its import-check entry invalid
    and not registered. netdryrun passed the must-fail checks live; the run must remedy first (then they fail) or
    end as an error."""
    _, origin, prefix = LABS[lab_key]
    assert NOT_REGISTERED in captured(boot, origin, TEXT)                    # the device's own view
    assert json.loads((FX / boot / "boot" / f"report_{LABS[lab_key][0][:-4]}.json").read_text())["status"] == "passed"
    rep, lab = judged(monkeypatch, lab_key, boot, deploy)
    assert rep.status != "passed" and not any(r.passed for r in rep.results), (
        f"{lab_key}: judged on a lab whose {origin} announces {prefix} with its import check not registered with zebra "
        f"(production withdraws it): {summary(rep)}")


@pytest.mark.parametrize("boot", [b for k, b in STUCK_ALL if k == "c18"])
def test_verify_never_approves_case_18_on_a_stuck_boot(monkeypatch, tmp_path, boot):
    """`netdryrun verify` on case 18 with the standing guards (corpus v2 I2: up1 and peer1 keep 192.0.2.0/24) and an
    intent that leaves 192.0.2.0/24 to them. The after boots (first and determinism rerun) are stuck: up1 and peer1
    keep the aggregate, the guards pass, and verify approved (`matched`) on main. Production withdraws the aggregate
    (as the healthy boots do, where the guards fail): verify must not approve."""
    res, labs = verified(monkeypatch, tmp_path, BASE, boot)
    assert res.status not in ("matched", "no_change"), (
        f"verify approved case 18 ({res.status}) on boots whose pe1 announces 192.0.2.0/24 with no route behind it "
        f"and its import check not registered: error {res.error!r}, guards {res.guards}, determinism {res.determinism}")


# ------------------------------------------- DERIVED: answers a run can't trust, on recorded c18 boots (pe1 changed)

READS = (TEXT, JSON, "show bgp import-check-table", "show bgp import-check-table json")   # every form recorded


def _derive(boot: str, node: str, change, ph: str = "boot") -> dict:
    """{(node, argv): answer} for every import-check read of the default instance, each made by change(cmd, live)."""
    out = {}
    for c in READS:
        rc, stdout, stderr = change(c, captured(boot, node, c, ph))
        out[(node, ("vtysh", "-c", c))] = ExecResult(["vtysh", "-c", c], rc, stdout, stderr)
    return out


def _unknown_command(boot, node, ph):
    """Every read refused (an FRR without the command)."""
    return _derive(boot, node, lambda c, live: (1, f"% Unknown command: {c}\n", ""), ph)


def _read_fails(boot, node, ph):
    """Every read fails (bgpd not answering)."""
    return _derive(boot, node, lambda c, live: (1, "", "Exiting: failed to connect to any daemons.\n"), ph)


def _empty_table(boot, node, ph):
    """The answers pe2 (no `network` lines) gave live, on pe1 which has one: an empty table, as a read before bgpd
    has applied its config looks (and like the `{}` that `vrf all` prints). An entry is missing for a configured
    network."""
    return _derive(boot, node, lambda c, live: (0, captured(boot, "pe2", c, ph), ""), ph)


def _unrecognized_shape(boot, node, ph):
    """The live answers with their header and keys in words this FRR never printed."""
    def change(c, live):
        if c.endswith("json"):
            return 0, re.sub(r'"(valid|isRegistered|complete|pathCount|paths)"', lambda m: f'"{m.group(1)}State"', live), ""
        return 0, live.replace("Current BGP import check cache:", "BGP import check entries:").replace(
            " valid,", " state ok,").replace(" invalid,", " state not ok,"), ""
    return _derive(boot, node, change, ph)


@pytest.mark.parametrize("make", [_unknown_command, _read_fails, _empty_table, _unrecognized_shape])
def test_unreadable_import_check_table_is_an_error(monkeypatch, make):
    """On c18 with every router registered (c18_stuck_boot2 after its live remedy), pe1's import-check table can't be read, isn't recognized,
    or has no entry for the `network` its bgpd runs: whether that network is registered is unknown, so the run ends as
    an error (on main it judged: "failed")."""
    boot, ph = HEALTHY["c18"]
    rep, lab = judged(monkeypatch, "c18", boot, True, derived=make(boot, "pe1", ph), start=ph)
    assert rep.status == "error", f"{make.__name__}: must end the run as an error: {summary(rep)}"


def test_contradiction_alone_is_detected(monkeypatch):
    """The stuck c18 boot where only pe1 was stuck, its answers without the registration flag ("Is not Registered"
    line and `isRegistered` key removed). The entry is still invalid next to a valid, sourced, best `network` path in
    bgpd's own table: FRR contradicting itself is the primary signal, whatever the flag is called. (The derived
    answers stand in for the boot phase only: after a remedy the replay answers what pe1 answered live.)"""
    boot = "c18_stuck_boot2"
    def change(c, live):
        if c.endswith("json"):
            return 0, re.sub(r',?\s*"isRegistered"\s*:\s*false', "", live), ""
        return 0, "".join(ln for ln in live.splitlines(keepends=True) if NOT_REGISTERED not in ln), ""
    derived = _derive(boot, "pe1", change)
    assert all(NOT_REGISTERED not in r.stdout and "isRegistered" not in r.stdout for r in derived.values())
    assert all(" invalid," in r.stdout or '"valid":false' in r.stdout for r in derived.values()), derived
    rep, lab = judged(monkeypatch, "c18", boot, True, derived=derived)
    assert rep.status != "passed" and not any(r.passed for r in rep.results), summary(rep)
