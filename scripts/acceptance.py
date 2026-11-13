"""Layer 5b of the release gate: acceptance from five angles, scripted (RELEASING.md, releases/acceptance-matrix.yml).

Runs on the lab machine (Linux, Docker, containerlab, the vendor images). It clones this repository's HEAD into a
clean work folder, builds and installs the wheel in a fresh virtualenv, and runs, against the installed package:

  angle 1, each network OS:  every example (good and each leak), the ported must-fail change (a customer filter loses
                             its match) with a `record` baseline, and the vendor output traps on the kept good lab;
  angle 2, the end user:     the README's blocks word for word in a fresh container (only the package source
                             substituted), and the common mistakes (exit 2, a clear message, no lab left);
  angle 3, the integrator:   a 30-node multi-vendor lab (also angle 1's mixed lab), two runs at once, a
                             brownfield-sized FRR policy, every JSON report read against the published schemas, and
                             the documented CI templates;
  angle 4, the AI agent:     the MCP server on a fresh lab: dry_run, start_run/get_result, record_baseline,
                             verify_change, and a leaky change that must be rejected; the size of each result.

Angle 5 (two isolated red-teamers) and reading the mismatches stay with agents: releases/ACCEPTANCE-PROMPT.md.

It takes the lab lock for each lab (and yields to a running release gate or stranger), cleans up after every lab,
and resumes after an interruption: results are kept per commit in the work folder (--fresh starts over).
Writes releases/<version>/acceptance.json and acceptance.md. Fails closed: exit 1 on any expectation mismatch,
leftover lab, traceback, or an item that couldn't be covered (a driver the matrix claims included).

    python scripts/acceptance.py                 # everything
    python scripts/acceptance.py --only 'angle1/frr/*,angle3/*'
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from release_gate import documented_examples  # noqa: E402

MATRIX = ROOT / "releases" / "acceptance-matrix.yml"
DEFAULT_LOCK = "/home/ndr/vendor-vm-lab.lock"
PRIORITY = r"release_gate\.py (live|all)|stranger\.py|unseen\.py"   # these runs go first
SUMMARY = re.compile(r"^(PASSED|FAILED|ERROR|INCONCLUSIVE)\b.*$", re.M)
PASS, FAIL, NOT_COVERED = "pass", "fail", "not covered"


# ------------------------------------------------------------------------------------------------- plumbing

@dataclass
class Proc:
    code: int
    out: str
    seconds: float


def sh(cmd, cwd=None, timeout=3600, env=None, input_=None) -> Proc:
    """Run a command (a list, or a string for bash); never raises for a missing tool or a timeout."""
    t0 = time.monotonic()
    args = ["bash", "-c", cmd] if isinstance(cmd, str) else [str(c) for c in cmd]
    try:
        p = subprocess.run(args, cwd=cwd, env=env, input=input_, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, text=True, errors="replace")
        return Proc(p.returncode, p.stdout, time.monotonic() - t0)
    except FileNotFoundError:
        return Proc(127, f"command not found: {args[0]}", time.monotonic() - t0)
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        return Proc(124, f"{out}\n[timed out after {timeout:.0f} s]", time.monotonic() - t0)


def summary_line(out: str) -> str:
    found = SUMMARY.findall(out) and [m.group(0) for m in SUMMARY.finditer(out)]
    return found[-1].strip() if found else ""


def leftovers() -> list[str]:
    p = sh(["docker", "ps", "-a", "--format", "{{.Names}}"], timeout=60)
    return sorted(n for n in p.out.split() if n.startswith("clab-")) if p.code == 0 else ["(docker ps failed)"]


def destroy(topology: Path) -> None:
    sh(["sudo", "-n", "containerlab", "destroy", "-t", topology, "--cleanup"], timeout=600)


class LabLock:
    """The shared lab lock: an atomic directory with an owner file. Yields to the release gate's live layer and
    the synthetic stranger, which have priority on the lab machine."""

    def __init__(self, path: str, what: str):
        self.path, self.what = Path(path), what

    def __enter__(self):
        waited = 0
        while True:
            if sh(["pgrep", "-f", PRIORITY], timeout=30).code != 0:
                try:
                    self.path.mkdir()
                    break
                except FileExistsError:
                    pass
            if waited % 300 == 0:
                owner = (self.path / "owner").read_text(errors="replace").strip() if (self.path / "owner").exists() else "a priority run"
                print(f"  waiting for the lab: {owner}", flush=True)
            time.sleep(15)
            waited += 15
        (self.path / "owner").write_text(f"acceptance.py (Layer 5b) {self.what} since {dt.datetime.now().isoformat()} "
                                         f"pid {os.getpid()}\n")
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)


@dataclass
class Result:
    id: str
    angle: str
    driver: str
    title: str
    status: str = FAIL
    expected: str = ""
    got: str = ""
    seconds: float = 0.0
    note: str = ""
    evidence: str = ""
    sha: str = ""


@dataclass
class Ctx:
    args: argparse.Namespace
    matrix: dict
    work: Path
    src: Path                      # the clean clone
    ndr: Path                      # the installed netdryrun
    python: Path                   # the venv's python (has Netdryrun's dependencies)
    sha: str
    docs: dict = field(default_factory=dict)
    exits: dict = field(default_factory=dict)   # report path -> exit code, for the schema reader

    def fresh(self, example: str, tag: str = "") -> Path:
        """A fresh copy of an example (and of frr-bgp, whose configs some examples bind)."""
        base = self.work / "labs"
        base.mkdir(exist_ok=True)
        d = base / f"{example}{tag}"
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(self.src / "examples" / example, d)
        if not (base / "frr-bgp").exists():
            shutil.copytree(self.src / "examples" / "frr-bgp", base / "frr-bgp")
        return d

    def run(self, path: Path, *extra, cmd="run", timeout=3600) -> Proc:
        report = self.work / "reports" / f"{path.parent.name if path.is_file() else path.name}-{len(self.exits)}.json"
        report.parent.mkdir(exist_ok=True)
        p = sh([self.ndr, cmd, path, "--json", report, "--no-step-summary", *extra], timeout=timeout)
        self.exits[str(report)] = p.code
        return p


def expect_run(ctx: Ctx, r: Result, path: Path, code: int, summary: str | None = None, *extra) -> Proc:
    """Run netdryrun and judge it: the exit code, the summary line (when given), no traceback."""
    p = ctx.run(path, *extra)
    got = summary_line(p.out)
    r.expected = f"exit {code}" + (f", `{summary}`" if summary else "")
    r.got = f"exit {p.code}" + (f", `{got}`" if got else "")
    r.seconds += p.seconds
    ok = p.code == code and (summary is None or summary in got) and "Traceback" not in p.out
    r.status = PASS if ok else FAIL
    if not ok:
        r.evidence = p.out[-4000:]
    return p


def apply(path: Path, pairs) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in text:
            raise AssertionError(f"{path.name}: the matrix's text to replace is not there: {old[:80]!r}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


# ------------------------------------------------------------------------------------------------- angle 1

def items_angle1(ctx: Ctx):
    docs = ctx.docs
    for drv, spec in ctx.matrix["drivers"].items():
        for ex in spec["examples"]:
            row = docs.get(ex)
            yield f"angle1/{drv}/example/{ex}", drv, f"example {ex}", (lambda r, ex=ex, row=row: example(ctx, r, ex, row))
            folder = ctx.src / "examples" / ex
            for leak in sorted((folder / "leaks").glob("*")) if (folder / "leaks").is_dir() else []:
                yield (f"angle1/{drv}/example/{ex}/leak-{leak.name}", drv, f"example {ex}, leaks/{leak.name}",
                       lambda r, ex=ex, row=row, leak=leak: example(ctx, r, ex, row, leak=leak))
            if ex == "leak-pattern":
                for i, f in ((1, "netdryrun-leaky.yml"), (2, "netdryrun-roles.yml")):
                    yield (f"angle1/{drv}/example/{ex}/{f}", drv, f"example {ex}, {f}",
                           lambda r, ex=ex, row=row, i=i, f=f: example(ctx, r, ex, row, variant=(i, f)))
        if spec.get("mustfail"):
            yield f"angle1/{drv}/mustfail", drv, "ported must-fail change with a record baseline, and the vendor traps", \
                (lambda r, drv=drv, spec=spec: mustfail(ctx, r, drv, spec["mustfail"]))


def example(ctx: Ctx, r: Result, ex: str, row: dict | None, leak: Path | None = None, variant=None) -> None:
    if not row or not row["codes"]:
        r.status, r.note = FAIL, "no documented expected result in website/docs/examples.md"
        return
    d = ctx.fresh(ex, f"-{leak.name}" if leak else f"-{variant[1]}" if variant else "")
    with LabLock(ctx.args.lock, r.id):
        if ex == "agent-demo":
            p = sh(["bash", d / "demo.sh"], cwd=ctx.work,
                   env={**os.environ, "NDR": str(ctx.ndr), "OUT": str(ctx.work / "reports" / "agent-demo")})
            r.expected, r.got, r.seconds = "`Demo OK`, exit 0", f"exit {p.code}, `{p.out.strip().splitlines()[-1:]}`", p.seconds
            r.status = PASS if p.code == 0 and "Demo OK" in p.out and "Traceback" not in p.out else FAIL
            r.evidence = "" if r.status == PASS else p.out[-4000:]
            return
        i = 1 if leak else variant[0] if variant else 0
        if leak:
            shutil.copy(leak, d / "configs" / leak.name)
        path = d / variant[1] if variant else d
        expect_run(ctx, r, path, row["codes"][i], row["outcomes"][i])
        if not leak and not variant and row.get("seconds") and r.status == PASS:
            lo, hi = min(row["seconds"]), max(row["seconds"])
            if r.seconds > 2 * hi or r.seconds < 0.5 * lo:
                r.note = f"time {r.seconds:.0f} s, documented {lo}-{hi} s (off by more than 2x)"


def traps_for(ctx: Ctx, node: str, neighbor: str, legit: str) -> list[dict]:
    net = legit.rsplit(".", 1)[0]          # 192.168.20.0/24 -> 192.168.20
    fill = {"node": node, "neighbor": neighbor, "legit": legit, "legit_sub": f"{net}.128/25",
            "legit_super": f"{net.rsplit('.', 1)[0]}.0.0/16"}
    out = []
    for t in ctx.matrix["traps"]:
        c = {}
        for k, v in t.items():
            c[k] = v.format(**fill) if isinstance(v, str) else v
        out.append(c)
    return out


def record_gaps(p, known: list, baseline: Path, who: str) -> list[str]:
    """record's exit: 0 is no gap; 1 with INCOMPLETE BASELINE lines, every one a documented limit the matrix lists
    (each with why), returns the gaps so the item can go on with the baseline record wrote, as a user who read record's
    error would; anything else raises, naming every gap the matrix doesn't list."""
    if p.code == 0:
        return []
    if p.code == 1 and "INCOMPLETE BASELINE" in p.out:
        gaps = sorted(set(re.findall(r"^\*\*\* (INCOMPLETE BASELINE: .*?) \*\*\*$", p.out, re.M)))
        # record's own size-cap lines don't count toward its exit code (record._is_size_cap): leave them out here too
        gaps = [g for g in gaps if not re.search(r" has \d+ (link subnets|BGP routes \(IPv[46]\)); only the first \d+ "
                                                 r"are (guarded|recorded)", g)]
        allowed = [re.compile(k["match"]) for k in known]
        unknown = [g for g in gaps if not any(a.search(g) for a in allowed)]
        if gaps and not unknown and baseline.exists():
            return gaps
        raise RuntimeError(f"record failed: exit 1 on gap(s) not listed as known for {who}: {unknown or 'none parsed'}"
                           f"\n{p.out[-3000:]}")
    raise RuntimeError(f"record failed: exit {p.code}\n{p.out[-3000:]}")


def mustfail(ctx: Ctx, r: Result, drv: str, spec: dict) -> None:
    base = ctx.work / "mustfail" / drv
    shutil.rmtree(base, ignore_errors=True)
    good, bad = base / "good", base / "bad"
    for d in (good, bad):
        shutil.copytree(ctx.src / "examples" / spec["example"], d, ignore=shutil.ignore_patterns("leaks"))
        if not (base / "frr-bgp").exists():
            shutil.copytree(ctx.src / "examples" / "frr-bgp", base / "frr-bgp")
    cfg_good = yaml.safe_load((good / "netdryrun.yml").read_text())
    if drv == "frr":       # the example itself: configs/edge.conf is the good config, edge-bad.conf the change
        apply(good / "topology.clab.yml", [spec["good_bind"]])
    else:
        for d in (good, bad):
            apply(d / ctx.matrix["customer"]["file"], ctx.matrix["customer"]["replace"])
            if spec.get("file"):
                apply(d / spec["file"], spec["filter"])
        if spec.get("file"):
            apply(bad / spec["file"], spec["drop_match"])
    for e in spec.get("peer_edits", []):   # the same on both labs (a prefix the good filter must reject)
        for d in (good, bad):
            apply(d / e["file"], e["replace"])
    setup = None
    if spec.get("setup_last"):   # SONiC: configured after boot by setup commands
        setup = {"good": cfg_good["nodes"], "bad": json.loads(json.dumps(cfg_good["nodes"]))}
        setup["good"][spec["node"]]["setup"][-1] = spec["setup_last"]
        setup["bad"][spec["node"]]["setup"][-1] = spec["setup_last"].replace(*spec["drop_match_setup"])
    neighbor, node = spec["neighbor"], spec["node"]
    legit = spec.get("legit", "192.168.20.0/24")
    # the example's own settings: a beta NOS's driver and the example's timeout (a VM boots for minutes). Without
    # them record left the node out and the baseline ran with timeout 120 (acceptance on d87aa3e: nxos, routeros)
    ex_nodes = cfg_good.get("nodes") or {}
    drivers = [f"--driver={n}={v['driver']}" for n, v in sorted(ex_nodes.items()) if isinstance(v, dict) and v.get("driver")]
    ex_timeout = cfg_good.get("timeout")
    with LabLock(ctx.args.lock, r.id):
        try:
            # 1. record the baseline on the good lab (a lab configured after boot is booted and set up first)
            t0 = time.monotonic()
            if setup:
                boot = good / "boot.yml"
                boot.write_text(yaml.safe_dump({"lab": "topology.clab.yml", "timeout": 300, "nodes": setup["good"],
                                                "checks": [{"type": "bgp_session", "node": node, "neighbor": neighbor}]}))
                p = sh([ctx.ndr, "run", boot, "--keep", "--no-step-summary"], timeout=1800)
                if p.code != 0:
                    raise RuntimeError(f"the good lab did not come up for record: exit {p.code}\n{p.out[-3000:]}")
                time.sleep(20)
                p = sh([ctx.ndr, "record", good / "topology.clab.yml", "--out", good / "netdryrun.yml", "--force", *drivers],
                       timeout=1800)
                destroy(good / "topology.clab.yml")
            else:
                # record --deploy waits for VM nodes to answer before its --wait (0.4.1); a VM NOS needs a long wait
                # for its sessions to come up (0.4.1 hand acceptance: 240 s RouterOS, 420-480 s Junos and NX-OS)
                wait = ["--wait", str(spec["record_wait"])] if spec.get("record_wait") else []
                p = sh([ctx.ndr, "record", good / "topology.clab.yml", "--deploy", "--out", good / "netdryrun.yml",
                        "--force", *wait, *drivers], timeout=3600)
            known = record_gaps(p, spec.get("known_gaps", []), good / "netdryrun.yml", drv)
            recorded = yaml.safe_load((good / "netdryrun.yml").read_text())
            for n, v in ex_nodes.items():   # the example's node settings (setup, driver), merged over record's
                if isinstance(v, dict):
                    recorded.setdefault("nodes", {}).setdefault(n, {}).update(v)
            if ex_timeout and ex_timeout > recorded.get("timeout", 0):
                recorded["timeout"] = ex_timeout
            # the checks record's gap lines tell a user to add by hand (the matrix gives them, each with why)
            hand = [{k: v for k, v in c.items() if k != "why"} for c in spec.get("hand_checks", [])]
            recorded["checks"] = list(recorded.get("checks") or []) + hand
            (good / "netdryrun.yml").write_text(yaml.safe_dump(recorded, sort_keys=False))
            if setup:   # merged over the example's settings (driver), never replacing them (code review of the batch)
                base_nodes = json.loads(json.dumps(recorded.get("nodes", {})))
                recorded["nodes"] = {**base_nodes, **{n: {**base_nodes.get(n, {}), **v} for n, v in setup["good"].items()}}
                (good / "netdryrun.yml").write_text(yaml.safe_dump(recorded, sort_keys=False))
                recorded["nodes"] = {**base_nodes, **{n: {**base_nodes.get(n, {}), **v} for n, v in setup["bad"].items()}}
            (bad / "netdryrun.yml").write_text(yaml.safe_dump(recorded, sort_keys=False))
            r.seconds += time.monotonic() - t0
            notes = [f"record: {len(recorded['checks']) - len(hand)} checks" + (f" + {len(hand)} by hand" if hand else "")]
            if known:
                notes.append(f"record exit 1 on {len(known)} known driver gap(s): " + " | ".join(known))
            # 2. the good lab must pass its own baseline, from a fresh deploy; it is kept for the traps
            expect_run(ctx, r, good, 0, None, "--keep")
            if r.status != PASS:
                notes.append("the baseline fails on the good lab")
                r.note = "; ".join(notes)   # the note was lost on this early return (acceptance on d87aa3e)
                return
            # 3. the vendor output traps on the kept lab: each T- check fails, each S- check passes
            traps = good / "traps.yml"
            trap_checks = traps_for(ctx, node, neighbor, legit)
            run_error_traps = [c for c in trap_checks if c["name"] in spec.get("run_error_traps", [])]
            trap_checks = [c for c in trap_checks if c not in run_error_traps]
            node_cfg = {"nodes": recorded["nodes"]} if recorded.get("nodes") else {}
            for c in run_error_traps:   # a run error by design on this driver: alone, it must end in exit 2
                lone = good / f"trap-{c['name']}.yml"
                lone.write_text(yaml.safe_dump({"lab": "topology.clab.yml", "timeout": 20, **node_cfg, "checks": [c]},
                                               sort_keys=False))
                pe = ctx.run(lone, cmd="check")
                if pe.code != 2 or "Traceback" in pe.out or "routing-instance" not in pe.out:
                    r.status = FAIL
                    notes.append(f"{c['name']}: exit {pe.code}, expected 2 (a run error on {drv})")
                    r.evidence = pe.out[-4000:]
            traps.write_text(yaml.safe_dump({"lab": "topology.clab.yml", "timeout": 20, **node_cfg,
                                             "checks": trap_checks}, sort_keys=False))
            p = ctx.run(traps, cmd="check")
            rep = json.loads(Path(next(k for k in reversed(list(ctx.exits)))).read_text())
            wrong = [c["name"] for c in rep.get("checks", []) if c["name"].startswith("T-") and c["passed"]] + \
                    [c["name"] for c in rep.get("checks", []) if c["name"].startswith("S-") and not c["passed"]]
            if p.code != 1 or wrong or "Traceback" in p.out:
                r.status = FAIL
                notes.append(f"traps: exit {p.code}, wrong: {', '.join(wrong) or 'none'}")
                r.evidence = p.out[-4000:]
            else:
                notes.append(f"{sum(c['name'].startswith('T-') for c in rep['checks'])} traps failed as they must")
            destroy(good / "topology.clab.yml")
            # 4. the change must fail
            good_status = r.status
            q = Result(r.id, r.angle, drv, "")
            expect_run(ctx, q, bad, 1)
            r.seconds += q.seconds
            r.expected, r.got = "baseline passes, traps fail, the change fails (exit 1)", q.got
            if q.status != PASS:
                r.status, r.evidence = FAIL, q.evidence
                notes.append("THE MUST-FAIL CHANGE DID NOT FAIL" if "exit 0" in q.got else "the change did not end in exit 1")
            else:
                r.status = good_status
            r.note = "; ".join(notes)
        except (RuntimeError, AssertionError) as e:
            r.status, r.note = FAIL, str(e).splitlines()[0]
            r.evidence = str(e)[-4000:]
        finally:
            for d in (good, bad):
                destroy(d / "topology.clab.yml")


# ------------------------------------------------------------------------------------------------- angle 2

def items_angle2(ctx: Ctx):
    eu = ctx.matrix["enduser"]
    yield "angle2/readme", "-", "README quick start and own topology, word for word in a fresh container", \
        (lambda r: readme_in_container(ctx, r, eu))
    for m in eu["mistakes"]:
        yield f"angle2/mistake/{m['id']}", "-", f"common mistake: {m['id']}", (lambda r, m=m: mistake(ctx, r, m))


def readme_block(md: str, heading: str) -> list[str]:
    at = md.index(f"### {heading}")
    m = re.search(r"```bash\n(.*?)```", md[at:], re.DOTALL)
    if not m:
        raise AssertionError(f"README: no bash block under '### {heading}'")
    return [ln for ln in m.group(1).splitlines() if ln.strip()]


def readme_in_container(ctx: Ctx, r: Result, eu: dict) -> None:
    """The README's own-machine block and its own-topology block (on the frr-customer-leak lab, recorded on the good
    config, then the bad change) in a fresh container that uses the host's Docker. Only the package source is
    substituted (the built wheel for `pipx install netdryrun`), and the clone is this commit."""
    md = (ctx.src / "README.md").read_text(encoding="utf-8")
    machine = readme_block(md, "On your own machine")
    own = readme_block(md, "On your own containerlab topology (3 commands)")
    wheel = next((ctx.work / "dist").glob("netdryrun-*.whl"))
    box = ctx.work / "enduser"
    shutil.rmtree(box, ignore_errors=True)
    if box.exists():   # files the container wrote as root survive rmtree: start in a fresh folder (rehearsal on 79e6205)
        box = ctx.work / f"enduser-{int(time.time())}"
    box.mkdir()
    shutil.copy(wheel, box / wheel.name)
    steps, want = [], []
    for line in machine:
        cmd = line.split("#", 1)[0].strip()
        if not cmd:
            continue
        cmd = cmd.replace("pipx install netdryrun", f"pipx install {box / wheel.name}")
        if cmd.startswith("git clone"):
            cmd = cmd.replace("https://github.com/netdryrun/Netdryrun", str(box / "repo.git"))
        steps.append(cmd)
        want.append(1 if "should fail" in line.lower() else 0)
    sh(["git", "clone", "-q", "--bare", ctx.src, box / "repo.git"], timeout=600)
    # the bare clone is bind-mounted from the lab machine's user into a root container: git refuses it as "dubious
    # ownership" (acceptance on d87aa3e). A user cloning from GitHub never meets this; trust the mounted clone only
    script = ["set +e", "export PATH=$HOME/.local/bin:$PATH", f"git config --global --add safe.directory {box / 'repo.git'}",
              "codes=()"]
    for s in steps:
        script.append(f"{s}; codes+=($?); echo \"== step exit ${{codes[-1]}}: {s.replace(chr(34), '')}\"")
    # own topology: a lab that is not the README's example: frr-customer-leak with its good config
    rec = next(c.split("#", 1)[0].strip() for c in own if c.strip().startswith("netdryrun record"))
    run = next(c.split("#", 1)[0].strip() for c in own if c.strip().startswith("netdryrun run"))
    lab = re.search(r"netdryrun run (\S+)", run).group(1)
    script += [f"cd {box} && rm -rf {lab} && cp -r $OLDPWD/examples/frr-customer-leak {lab} && cp -r $OLDPWD/examples/frr-bgp .",
               f"sed -i 's#- edge-bad.conf:#- configs/edge.conf:#' {lab}/topology.clab.yml && rm -f {lab}/netdryrun.yml",
               f"{rec}; codes+=($?); echo \"== step exit ${{codes[-1]}}: record\"",
               f"sed -i 's#- configs/edge.conf:#- edge-bad.conf:#' {lab}/topology.clab.yml",
               f"{run}; codes+=($?); echo \"== step exit ${{codes[-1]}}: run, the customer filter lost its match\"",
               'echo "CODES ${codes[*]}"']
    want += [0, 1]
    (box / "steps.sh").write_text("\n".join(script) + "\n")
    setup = ("apt-get update -qq >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git pipx sudo curl "
             "ca-certificates docker.io >/dev/null && bash -c \"$(curl -sL https://get.containerlab.dev)\" >/dev/null 2>&1")
    mounts = ["-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", "/var/run/netns:/var/run/netns",
              "-v", "/var/lib/docker/containers:/var/lib/docker/containers", "-v", "/etc/hosts:/etc/hosts",
              "-v", f"{box}:{box}"]
    with LabLock(ctx.args.lock, r.id):
        p = sh(["docker", "run", "--rm", "--privileged", "--network", "host", "--pid", "host", *mounts, "-w", str(box),
                eu["image"], "bash", "-c", f"{setup} && bash {box}/steps.sh"], timeout=5400)
        left = leftovers()
        for x in left:
            sh(["docker", "rm", "-f", x], timeout=120)
    m = re.search(r"CODES ([\d ]*)", p.out)
    got = [int(c) for c in m.group(1).split()] if m else []
    r.seconds, r.expected, r.got = p.seconds, " ".join(map(str, want)), " ".join(map(str, got)) or f"exit {p.code}"
    r.status = PASS if got == want and not left and "Traceback" not in p.out else FAIL
    r.note = f"left behind: {', '.join(left)}" if left else ""
    if r.status != PASS:
        r.evidence = p.out[-6000:]


def mistake(ctx: Ctx, r: Result, m: dict) -> None:
    """A common mistake: exit 2, a message on the last line, no traceback, no lab left behind."""
    with LabLock(ctx.args.lock, r.id):
        before = set(leftovers())
        env = None
        if m.get("path"):
            path = Path(m["path"])
        else:
            d = ctx.fresh(m["example"], f"-mistake-{m['id']}")
            path = d
            if m.get("edit"):
                apply(d / m["file"], [m["edit"]])
        cmd = [ctx.ndr, "run", path, "--no-step-summary"]
        if m.get("as_user") and os.getuid() == 0:
            raise AssertionError("no-docker-permission can't be reproduced as root (root reaches Docker anyway)")
        if m.get("as_user"):     # no access to the Docker socket: this user without its supplementary groups
            # (docker among them). `nobody` couldn't read the install under the lab user's home, so netdryrun never
            # started (acceptance on d87aa3e); the same user minus the docker group is the mistake itself
            cmd = ["sudo", "-n", "setpriv", f"--reuid={os.getuid()}", f"--regid={os.getgid()}", "--clear-groups",
                   "env", f"HOME={Path.home()}", *map(str, cmd)]
        if m.get("hide_kvm"):    # what a machine without KVM looks like to the netdryrun process
            # /dev/kvm can't be removed or covered in place (a mount point; a bind of /dev/null is still a character
            # device: acceptance on d87aa3e), so this mount namespace gets a /dev of its own without it
            cmd = ["sudo", "-n", "unshare", "-m", "sh", "-c",
                   "mkdir -p /run/ndr-nokvm && mount -t tmpfs none /run/ndr-nokvm && "
                   "cp -a /dev/null /dev/zero /dev/random /dev/urandom /dev/tty /run/ndr-nokvm/ && "
                   "ln -s /proc/self/fd /run/ndr-nokvm/fd && mount --bind /run/ndr-nokvm /dev && "
                   'test ! -e /dev/kvm && exec "$@"', "sh", *map(str, cmd)]
        p = sh(cmd, timeout=1800, env=env)
        left = sorted(set(leftovers()) - before)
        for x in left:
            sh(["docker", "rm", "-f", x], timeout=120)
    last = next((ln for ln in reversed(p.out.strip().splitlines()) if ln.strip()), "")
    r.seconds, r.expected, r.got = p.seconds, "exit 2, a message, no lab left", f"exit {p.code}: {last[:160]}"
    # the mistake's own message, not any exit 2 (code review of the 0.4.1 batch: a run stopped by something else, a
    # /dev without stdin, a containerlab group check, passed as the mistake)
    said = re.search(m["expect"], p.out, re.I) if m.get("expect") else True
    r.status = PASS if p.code == 2 and "Traceback" not in p.out and not left and last and said else FAIL
    if not said:
        r.got += f" (no {m['expect']!r} in the output)"
    r.note = f"left behind: {', '.join(left)}" if left else ""
    if r.status != PASS:
        r.evidence = p.out[-4000:]


# ------------------------------------------------------------------------------------------------- angle 3

def items_angle3(ctx: Ctx):
    i = ctx.matrix["integrator"]
    if i.get("concurrency"):
        yield "angle3/concurrency/same-lab", "-", "the same lab twice at once: the second exits 2, the first keeps its verdict", \
            (lambda r: concurrency(ctx, r, same=True))
        yield "angle3/concurrency/different-labs", "-", "two different labs at once, started 20 s apart", \
            (lambda r: concurrency(ctx, r, same=False))
    if i.get("brownfield"):
        for v, code in (("good", 0), ("leak", 1), ("swap", 1), ("cosmetic", 0)):
            yield f"angle3/brownfield/{v}", "frr", f"brownfield FRR policy, {v}", (lambda r, v=v, code=code: brownfield(ctx, r, v, code))
    if i.get("big30"):
        for v, code in (("good", 0), ("bad", 1)):
            yield f"angle3/big30/{v}", "mixed", f"30-node multi-vendor lab, {v} (also angle 1's mixed lab)", \
                (lambda r, v=v, code=code: big30(ctx, r, v, code))
    if i.get("templates"):
        yield "angle3/templates", "-", "documented CI templates: YAML and actionlint", (lambda r: templates(ctx, r))
    if i.get("schema"):   # last: it reads every report the other items wrote
        yield "angle3/schema", "-", "every JSON report read against the published schema, status against exit code", \
            (lambda r: schema(ctx, r))


def concurrency(ctx: Ctx, r: Result, same: bool) -> None:
    import threading
    a = ctx.fresh("frr-bgp", "-conc-a")
    b = ctx.fresh("frr-bgp", "-conc-b") if same else ctx.fresh("frr-customer-leak", "-conc-b")
    res: dict[str, Proc] = {}
    with LabLock(ctx.args.lock, r.id):
        def go(name, path, delay):
            time.sleep(delay)
            res[name] = ctx.run(path)
        ts = [threading.Thread(target=go, args=("a", a, 0)), threading.Thread(target=go, args=("b", b, 8 if same else 20))]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        left = leftovers()
    want = (0, 2) if same else (0, 1)
    got = (res["a"].code, res["b"].code)
    r.expected, r.got, r.seconds = f"exits {want}", f"exits {got}", max(p.seconds for p in res.values())
    msg_ok = not same or "already using lab" in res["b"].out
    r.status = PASS if got == want and msg_ok and not left and not any("Traceback" in p.out for p in res.values()) else FAIL
    if r.status != PASS:
        r.evidence = (res["a"].out[-2000:] + "\n----\n" + res["b"].out[-2000:])
        if not same and "Address already in use" in res["b"].out:
            r.note = ("containerlab could not give both labs management addresses at once (docker 'Address already "
                      "in use'): documented as one lab at a time per host")


def brownfield(ctx: Ctx, r: Result, variant: str, code: int) -> None:
    base = ctx.work / "brownfield"
    if variant == "good" or not (base / "netdryrun.yml").exists():
        make_brownfield(base, ctx.matrix["integrator"]["brownfield"], ctx.src)
        with LabLock(ctx.args.lock, r.id + "/record"):
            p = sh([ctx.ndr, "record", base / "good" / "topology.clab.yml", "--deploy", "--out", base / "netdryrun.yml",
                    "--force"], timeout=3600)
        if p.code != 0:
            r.status, r.note, r.evidence = FAIL, f"record failed: exit {p.code}", p.out[-4000:]
            return
        r.seconds += p.seconds
        r.note = f"record {p.seconds:.0f} s"
    d = base / variant
    (d / "netdryrun.yml").write_text(re.sub(r"(?m)^lab: .*$", "lab: topology.clab.yml", (base / "netdryrun.yml").read_text()))
    with LabLock(ctx.args.lock, r.id):
        expect_run(ctx, r, d, code)
    if variant == "swap" and r.status == FAIL and "exit 0" in r.got:
        r.note = ("a replaced prefix with the count unchanged passes above 500 prefixes, where record writes an exact "
                  "count and no `only` list (documented limit)")


def big30(ctx: Ctx, r: Result, variant: str, code: int) -> None:
    base = ctx.work / "big30"
    spec = ctx.matrix["integrator"]["big30"]
    if variant == "good" or not (base / "good" / "netdryrun.yml").exists():
        make_big30(base, spec, ctx.src)
        good = base / "good"
        with LabLock(ctx.args.lock, r.id + "/record"):
            boot = {"lab": "topology.clab.yml", "timeout": 600, "nodes": yaml.safe_load((good / "setup.yml").read_text())["nodes"],
                    "checks": [{"type": "bgp_session", "node": f"leaf{i}", "neighbor": f"10.1.{i}.0"}
                               for i in sorted({1, *spec["srlinux"], *spec["eos"], *spec["sonic"]})]}
            (good / "boot.yml").write_text(yaml.safe_dump(boot, sort_keys=False))
            p = sh([ctx.ndr, "run", good / "boot.yml", "--keep", "--no-step-summary"], timeout=3600)
            r.note = f"deploy+boot {p.seconds:.0f} s"
            if p.code == 0:
                time.sleep(30)
                q = sh([ctx.ndr, "record", good / "topology.clab.yml", "--out", base / "baseline.yml", "--force"], timeout=7200)
                r.note += f", record {q.seconds:.0f} s"
            t0 = time.monotonic()
            destroy(good / "topology.clab.yml")
            r.note += f", destroy {time.monotonic() - t0:.0f} s"
        if p.code != 0:
            r.status, r.evidence = FAIL, p.out[-4000:]
            return
        try:
            gaps = record_gaps(q, spec.get("known_gaps", []), base / "baseline.yml", "big30")
        except RuntimeError as e:
            r.status, r.note, r.evidence = FAIL, str(e).splitlines()[0], str(e)[-4000:]
            return
        if gaps:
            r.note += f", record exit 1 on {len(gaps)} known gap(s)"
        rec = yaml.safe_load((base / "baseline.yml").read_text())
        rec.update(lab="topology.clab.yml", timeout=600, nodes=boot["nodes"])
        for v in ("good", "bad"):
            (base / v / "netdryrun.yml").write_text(yaml.safe_dump(rec, sort_keys=False))
    with LabLock(ctx.args.lock, r.id):
        expect_run(ctx, r, base / variant, code)


def templates(ctx: Ctx, r: Result) -> None:
    """Every YAML block in the docs parses; every workflow among them passes actionlint (a step list is wrapped in a
    minimal job). Not covered without actionlint."""
    lint = shutil.which("actionlint") or str(Path.home() / ".local/bin/actionlint")
    if not Path(lint).exists():
        r.status, r.note = NOT_COVERED, "actionlint is not installed"
        return
    out = ctx.work / "templates"
    shutil.rmtree(out, ignore_errors=True)
    (out / ".github" / "workflows").mkdir(parents=True)
    bad, n = [], 0
    files = [ctx.src / "README.md", *sorted((ctx.src / "website" / "docs").rglob("*.md"))]
    for md in files:
        for m in re.finditer(r"```ya?ml[^\n]*\n(.*?)```", md.read_text(encoding="utf-8"), re.DOTALL):
            body = m.group(1)
            try:
                data = yaml.safe_load(body)
            except yaml.YAMLError as e:
                bad.append(f"{md.relative_to(ctx.src)}: not YAML: {str(e).splitlines()[0]}")
                continue
            if isinstance(data, dict) and "jobs" in data:
                wf = body
            elif isinstance(data, list) and data and isinstance(data[0], dict) and ("uses" in data[0] or "run" in data[0]):
                wf = "on: pull_request\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n" + \
                     "\n".join("    " + ln[6:] if ln.startswith("      ") else "    " + ln for ln in body.splitlines()) + "\n"
            else:
                continue
            n += 1
            (out / ".github" / "workflows" / f"w{n}.yml").write_text(wf)
    gi = sh(["git", "init", "-q"], cwd=out, timeout=60)   # actionlint finds workflows from a repository root only
    if gi.code != 0:
        r.status, r.note = FAIL, f"git init in {out} failed: {gi.out[-300:]}"
        return
    p = sh([lint, "-no-color"], cwd=out, timeout=300)
    if p.code not in (0, 1):
        r.status, r.note = NOT_COVERED, f"actionlint failed to run: exit {p.code}"
        return
    if p.code:
        bad.append(p.out.strip()[-3000:])
    r.expected, r.got, r.seconds = "every YAML block parses; every workflow lints clean", f"{n} workflows, {len(bad)} problem(s)", p.seconds
    r.status, r.evidence = (PASS, "") if not bad else (FAIL, "\n".join(bad))


def schema(ctx: Ctx, r: Result) -> None:
    """What an integrator's script does: validate each report against the published schema and decide on status;
    the status must agree with the exit code of the run that wrote it, and with the report's own checks."""
    code = r'''
import json, sys
import jsonschema
schema = json.load(open(sys.argv[1]))
exits = json.load(open(sys.argv[2]))
problems, n = [], 0
CODE = {"passed": 0, "failed": 1, "error": 2, "inconclusive": 3}
for path, code in exits.items():
    try:
        rep = json.load(open(path))
    except Exception as e:
        if code in (0, 1):
            problems.append(f"{path}: exit {code} but no readable report ({e})")
        continue
    n += 1
    try:
        jsonschema.validate(rep, schema)
    except jsonschema.ValidationError as e:
        problems.append(f"{path}: {list(e.absolute_path)}: {e.message[:200]}")
    st, checks = rep.get("status"), rep.get("checks") or []
    if CODE.get(st) != code:
        problems.append(f"{path}: status {st} but exit {code}")
    if st == "passed" and (not checks or not all(c.get("passed") is True for c in checks)):
        problems.append(f"{path}: passed with a failed check, or no checks")
print(f"READ {n}")
print("\n".join(problems))
sys.exit(1 if problems else 0)
'''
    (ctx.work / "exits.json").write_text(json.dumps(ctx.exits))
    p = sh([ctx.python, "-c", code, ctx.src / "website/docs/schemas/report-v1.json", ctx.work / "exits.json"], timeout=600)
    if "No module named 'jsonschema'" in p.out:
        sh([ctx.python, "-m", "pip", "install", "-q", "jsonschema"], timeout=600)
        p = sh([ctx.python, "-c", code, ctx.src / "website/docs/schemas/report-v1.json", ctx.work / "exits.json"], timeout=600)
    m = re.search(r"READ (\d+)", p.out)
    r.expected, r.got = "every report valid and consistent", f"{m.group(1) if m else 0} reports, exit {p.code}"
    r.status = PASS if p.code == 0 and m and int(m.group(1)) > 0 else FAIL
    r.evidence = "" if r.status == PASS else p.out[-4000:]


def make_brownfield(base: Path, spec: dict, src: Path) -> None:
    """cust (AS 64610) -> edge (AS 64600) -> up (AS 64700). cust announces N /24s it owns and 203.0.113.0/24 it doesn't;
    edge's import policy is a long real-world-style route-map. good: as written; leak: clause 100 loses its prefix-list
    match; swap: the leak plus one legitimate prefix withdrawn (the count is unchanged); cosmetic: a description."""
    shutil.rmtree(base, ignore_errors=True)
    g = base / "good"
    (g / "configs").mkdir(parents=True)
    for f in ("daemons", "vtysh.conf"):
        shutil.copy(src / "examples" / "frr-bgp" / "configs" / f, g / "configs" / f)
    n = spec["customer_prefixes"]
    own = [f"100.{80 + i // 256}.{i % 256}.0/24" for i in range(n)]
    cust = ["frr defaults traditional", "hostname cust", "!", "interface eth1", " ip address 10.30.1.2/30", "!"]
    cust += [f"ip route {p} blackhole" for p in own] + ["ip route 203.0.113.0/24 blackhole", "!",
             "route-map ALLOW permit 10", "!", "router bgp 64610", " bgp router-id 10.30.1.2", " no bgp ebgp-requires-policy",
             " neighbor 10.30.1.1 remote-as 64600", " address-family ipv4 unicast", "  redistribute static",
             "  neighbor 10.30.1.1 route-map ALLOW in", "  neighbor 10.30.1.1 route-map ALLOW out", " exit-address-family", "!"]
    edge = ["frr defaults traditional", "hostname edge", "!", "interface eth1",
            " description cust AS64610 (customer, contract 4711)", " ip address 10.30.1.1/30", "!", "interface eth2",
            " description up AS64700 (transit)", " ip address 10.30.2.1/30", "!", "ip route 172.30.0.0/16 blackhole", "!"]
    edge += [f"ip prefix-list CUST-IN seq {5 * (i + 1)} permit {p}" for i, p in enumerate(own)]
    edge += [f"ip prefix-list BOGONS seq {5 * (i + 1)} permit {10 + i // 256}.{i % 256}.0.0/16 le 32" for i in range(spec["bogons"])]
    edge += ["ip prefix-list OURS seq 5 permit 172.30.0.0/16", "!", "bgp as-path access-list CUST-ASPATH seq 5 permit ^64610(_64610)*$"]
    edge += [f"bgp as-path access-list BAD-ASPATH seq {5 * (i + 1)} permit _{64512 + i}_" for i in range(40)]
    edge += [f"bgp community-list standard CUST-TAG-{i} seq 5 permit 64610:{100 + i}" for i in range(30)]
    edge += ["bgp community-list standard BLACKHOLE seq 5 permit 64600:666", "!",
             "route-map CUST-IN deny 5", " match ip address prefix-list BOGONS", "!",
             "route-map CUST-IN deny 6", " match as-path BAD-ASPATH", "!",
             "route-map CUST-IN permit 7", " match community BLACKHOLE", " set community no-export additive",
             " set local-preference 50", "!"]
    for i in range(30):
        edge += [f"route-map CUST-IN permit {10 + i}", f" match community CUST-TAG-{i}", " match ip address prefix-list CUST-IN",
                 f" set local-preference {200 - i}", f" set community 64600:{1000 + i} additive", "!"]
    edge += ["route-map CUST-IN permit 100", " match ip address prefix-list CUST-IN", " match as-path CUST-ASPATH",
             " set local-preference 200", " set community 64600:1000 additive", "!", "route-map CUST-IN deny 200", "!",
             "route-map UP-OUT permit 10", " match ip address prefix-list OURS", "!",
             "route-map UP-OUT permit 20", " match ip address prefix-list CUST-IN", " set as-path prepend 64600", "!",
             "route-map UP-IN permit 10", " set local-preference 100", "!",
             "router bgp 64600", " bgp router-id 10.30.2.1", " neighbor 10.30.1.2 remote-as 64610",
             " neighbor 10.30.1.2 description cust", " neighbor 10.30.2.2 remote-as 64700", " neighbor 10.30.2.2 description up",
             " address-family ipv4 unicast", "  network 172.30.0.0/16", "  neighbor 10.30.1.2 route-map CUST-IN in",
             "  neighbor 10.30.1.2 maximum-prefix 2000", "  neighbor 10.30.2.2 route-map UP-IN in",
             "  neighbor 10.30.2.2 route-map UP-OUT out", " exit-address-family", "!"]
    up = ["frr defaults traditional", "hostname up", "!", "interface eth1", " ip address 10.30.2.2/30", "!",
          "ip route 0.0.0.0/0 blackhole", "!", "route-map ALLOW permit 10", "!", "router bgp 64700", " bgp router-id 10.30.2.2",
          " neighbor 10.30.2.1 remote-as 64600", " address-family ipv4 unicast", "  neighbor 10.30.2.1 route-map ALLOW in",
          "  neighbor 10.30.2.1 route-map ALLOW out", " exit-address-family", "!"]
    for name, lines in (("cust", cust), ("edge", edge), ("up", up)):
        (g / "configs" / f"{name}.conf").write_text("\n".join(lines) + "\n")
    node = lambda n: (f"    {n}:\n      kind: linux\n      image: quay.io/frrouting/frr:10.4.1\n      binds:\n"  # noqa: E731
                      f"        - configs/daemons:/etc/frr/daemons\n        - configs/vtysh.conf:/etc/frr/vtysh.conf\n"
                      f"        - configs/{n}.conf:/etc/frr/frr.conf\n")
    (g / "topology.clab.yml").write_text("name: ndr-brown\ntopology:\n  nodes:\n" + node("cust") + node("edge") + node("up") +
                                        '  links:\n    - endpoints: ["edge:eth1", "cust:eth1"]\n'
                                        '    - endpoints: ["edge:eth2", "up:eth1"]\n')
    leak = [("route-map CUST-IN permit 100\n match ip address prefix-list CUST-IN\n", "route-map CUST-IN permit 100\n")]
    for v in ("leak", "swap", "cosmetic"):
        shutil.copytree(g, base / v)
    apply(base / "leak" / "configs" / "edge.conf", leak)
    apply(base / "swap" / "configs" / "edge.conf", leak)
    apply(base / "swap" / "configs" / "cust.conf", [(f"ip route {own[n // 2]} blackhole\n", "")])
    apply(base / "cosmetic" / "configs" / "edge.conf", [("contract 4711", "contract 4712")])


def make_big30(base: Path, spec: dict, src: Path) -> None:
    """Leaf-spine: 2 FRR spines, both AS 65000 so that no leaf carries one spine's routes to the other (with two
    spine ASes the leaves are transit, and which paths they pass on follows best-path timing, different on every
    deploy), and 28 leaves (AS 65101..), each with /31s to both spines and its loopback 172.16.<i>.1/32 announced.
    Leaves listed under srlinux, eos and sonic run that NOS, the rest FRR. bad: the last FRR leaf announces
    203.0.113.0/24, which it doesn't own."""
    shutil.rmtree(base, ignore_errors=True)
    g = base / "good"
    (g / "configs").mkdir(parents=True)
    for f in ("daemons", "vtysh.conf"):
        shutil.copy(src / "examples" / "frr-bgp" / "configs" / f, g / "configs" / f)
    leaves = range(1, spec["leaves"] + 1)
    frr = "quay.io/frrouting/frr:10.4.1"
    def frr_node(name):
        return (f"    {name}:\n      kind: linux\n      image: {frr}\n      binds:\n        - configs/daemons:/etc/frr/daemons\n"
                f"        - configs/vtysh.conf:/etc/frr/vtysh.conf\n        - configs/{name}.conf:/etc/frr/frr.conf\n")
    nodes, links, setup = [], [], {}
    for s, asn in ((1, 65000), (2, 65000)):
        lines = [f"frr defaults datacenter\nhostname spine{s}\n!\ninterface lo\n ip address 10.255.0.{s}/32\n!"]
        lines += [f"interface eth{i}\n ip address 10.{s}.{i}.0/31\n!" for i in leaves]
        lines.append(f"route-map ALLOW-ALL permit 10\n!\nrouter bgp {asn}\n bgp router-id 10.255.0.{s}")
        lines += [f" neighbor 10.{s}.{i}.1 remote-as {65100 + i}" for i in leaves]
        lines.append(f" address-family ipv4 unicast\n  network 10.255.0.{s}/32")
        lines += [f"  neighbor 10.{s}.{i}.1 route-map ALLOW-ALL in\n  neighbor 10.{s}.{i}.1 route-map ALLOW-ALL out" for i in leaves]
        lines.append(" exit-address-family\n!")
        (g / "configs" / f"spine{s}.conf").write_text("\n".join(lines) + "\n")
        nodes.append(frr_node(f"spine{s}"))
    for i in leaves:
        name, asn, lo = f"leaf{i}", 65100 + i, f"172.16.{i}.1"
        if i in spec["srlinux"]:
            cli = [f"set / interface ethernet-1/{k} admin-state enable" for k in (1, 2)]
            cli += [f"set / interface ethernet-1/{k} subinterface 0 ipv4 admin-state enable" for k in (1, 2)]
            cli += [f"set / interface ethernet-1/{k} subinterface 0 ipv4 address 10.{k}.{i}.1/31" for k in (1, 2)]
            cli += ["set / interface lo0 subinterface 0 ipv4 admin-state enable",
                    f"set / interface lo0 subinterface 0 ipv4 address {lo}/32",
                    "set / network-instance default interface ethernet-1/1.0", "set / network-instance default interface ethernet-1/2.0",
                    "set / network-instance default interface lo0.0",
                    "set / routing-policy policy accept-all default-action policy-result accept",
                    "set / network-instance default protocols bgp admin-state enable",
                    f"set / network-instance default protocols bgp autonomous-system {asn}",
                    f"set / network-instance default protocols bgp router-id {lo}",
                    "set / network-instance default protocols bgp afi-safi ipv4-unicast admin-state enable",
                    "set / network-instance default protocols bgp group ebgp export-policy [ accept-all ]",
                    "set / network-instance default protocols bgp group ebgp import-policy [ accept-all ]"]
            for k, peer in ((1, 65000), (2, 65000)):
                cli += [f"set / network-instance default protocols bgp neighbor 10.{k}.{i}.0 peer-group ebgp",
                        f"set / network-instance default protocols bgp neighbor 10.{k}.{i}.0 peer-as {peer}"]
            (g / "configs" / f"{name}.cli").write_text("\n".join(cli) + "\n")
            nodes.append(f"    {name}:\n      kind: nokia_srlinux\n      image: ghcr.io/nokia/srlinux:26.7.2\n"
                         f"      startup-config: configs/{name}.cli\n")
            ifs = ("e1-1", "e1-2")
        elif i in spec["eos"]:
            (g / "configs" / f"{name}.cfg").write_text(
                f"hostname {name}\n!\nservice routing protocols model multi-agent\n!\n"
                f"interface Ethernet1\n   no switchport\n   ip address 10.1.{i}.1/31\n!\n"
                f"interface Ethernet2\n   no switchport\n   ip address 10.2.{i}.1/31\n!\n"
                f"interface Loopback0\n   ip address {lo}/32\n!\nip routing\n!\n"
                f"router bgp {asn}\n   router-id {lo}\n   neighbor 10.1.{i}.0 remote-as 65000\n"
                f"   neighbor 10.2.{i}.0 remote-as 65000\n   network {lo}/32\n!\nend\n")
            nodes.append(f"    {name}:\n      kind: arista_ceos\n      image: ceos:4.36.3M\n      startup-config: configs/{name}.cfg\n")
            ifs = ("eth1", "eth2")
        elif i in spec["sonic"]:
            nodes.append(f"    {name}:\n      kind: sonic-vs\n      image: docker-sonic-vs:master.1258173-c10162df4\n")
            setup[name] = {"setup": [
                "supervisorctl status orchagent | grep -q RUNNING && supervisorctl status bgpd | grep -q RUNNING",
                f"config interface ip add Ethernet0 10.1.{i}.1/31 && config interface startup Ethernet0",
                f"config interface ip add Ethernet4 10.2.{i}.1/31 && config interface startup Ethernet4",
                f"config loopback add Loopback0; config interface ip add Loopback0 {lo}/32",
                f'vtysh -c "conf t" -c "router bgp {asn}" -c "bgp router-id {lo}" -c "no bgp ebgp-requires-policy" '
                f'-c "neighbor 10.1.{i}.0 remote-as 65000" -c "neighbor 10.2.{i}.0 remote-as 65000" '
                f'-c "address-family ipv4 unicast" -c "network {lo}/32"']}
            ifs = ("eth1", "eth2")
        else:
            (g / "configs" / f"{name}.conf").write_text(
                f"frr defaults datacenter\nhostname {name}\n!\ninterface lo\n ip address {lo}/32\n!\n"
                f"interface eth1\n ip address 10.1.{i}.1/31\n!\ninterface eth2\n ip address 10.2.{i}.1/31\n!\n"
                f"route-map ALLOW-ALL permit 10\n!\nrouter bgp {asn}\n bgp router-id {lo}\n"
                f" neighbor 10.1.{i}.0 remote-as 65000\n neighbor 10.2.{i}.0 remote-as 65000\n"
                f" address-family ipv4 unicast\n  network {lo}/32\n"
                f"  neighbor 10.1.{i}.0 route-map ALLOW-ALL in\n  neighbor 10.1.{i}.0 route-map ALLOW-ALL out\n"
                f"  neighbor 10.2.{i}.0 route-map ALLOW-ALL in\n  neighbor 10.2.{i}.0 route-map ALLOW-ALL out\n"
                f" exit-address-family\n!\n")
            nodes.append(frr_node(name))
            ifs = ("eth1", "eth2")
        links += [f'    - endpoints: ["spine1:eth{i}", "{name}:{ifs[0]}"]', f'    - endpoints: ["spine2:eth{i}", "{name}:{ifs[1]}"]']
    (g / "topology.clab.yml").write_text("name: ndr-big30\ntopology:\n  nodes:\n" + "".join(nodes) + "  links:\n" + "\n".join(links) + "\n")
    (g / "setup.yml").write_text(yaml.safe_dump({"nodes": setup}, sort_keys=False, width=1000))
    shutil.copytree(g, base / "bad")
    bad = [k for k in leaves if k not in (*spec["srlinux"], *spec["eos"], *spec["sonic"])][-1]
    apply(base / "bad" / "configs" / f"leaf{bad}.conf",
          [(f"  network 172.16.{bad}.1/32\n", f"  network 172.16.{bad}.1/32\n  network 203.0.113.0/24\n"),
           ("router bgp", "ip route 203.0.113.0/24 blackhole\n!\nrouter bgp")])


# ------------------------------------------------------------------------------------------------- angle 4

MCP_SMOKE = r'''
import asyncio, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ndr, work, src = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
lab = work / "lab"
results, problems = [], []

def tokens(text):
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return round(len(text) / 4)

def patch(diff):
    shutil.copy(src / "examples/agent-demo/configs/edge1.conf", lab / "configs/edge1.conf")
    subprocess.run(["patch", "-s", "-p1", "-d", str(lab)], input=(src / "examples/agent-demo" / diff).read_bytes(), check=True)

async def main():
    params = StdioServerParameters(command=ndr, args=["mcp"], env={**os.environ, "NETDRYRUN_MCP_ROOT": str(work)})
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        async def call(tool, **args):
            t0 = time.monotonic()
            res = await s.call_tool(tool, args)
            text = "\n".join(getattr(c, "text", "") for c in res.content)
            results.append({"tool": tool, "bytes": len(text.encode()), "tokens": tokens(text), "seconds": round(time.monotonic() - t0, 1)})
            try:
                return json.loads(text)
            except ValueError:
                return {"raw": text}
        tools = await s.list_tools()
        listing = json.dumps([{"name": t.name, "description": t.description} for t in tools.tools])
        results.append({"tool": "tools/list", "bytes": len(listing.encode()), "tokens": tokens(listing), "seconds": 0})
        patch(sys.argv[4])                       # the leaky change: must be rejected
        r1 = await call("dry_run", path=str(lab))
        if r1.get("status") != "failed" or "DO NOT APPLY" not in str(r1.get("verdict")):
            problems.append(f"dry_run on the leaky change: status {r1.get('status')}, verdict {r1.get('verdict')}")
        patch(sys.argv[5])                       # the fix: must pass, through start_run/get_result
        st = await call("start_run", path=str(lab))
        rid = st.get("run_id")
        for _ in range(240):
            g = await call("get_result", run_id=rid)
            if g.get("status") != "running":
                break
            await asyncio.sleep(5)
        if g.get("status") != "passed":
            problems.append(f"start_run/get_result on the fix: status {g.get('status')}")
        rb = await call("record_baseline", topology=str(lab / "topology.clab.yml"))
        if "checks:" not in json.dumps(rb):
            problems.append("record_baseline returned no checks")
        before = work / "before"; after = work / "after"
        for d, diff in ((before, None), (after, sys.argv[5])):
            shutil.rmtree(d, ignore_errors=True); shutil.copytree(src / "examples/agent-demo", d)
            if diff:
                subprocess.run(["patch", "-s", "-p1", "-d", str(d)], input=(src / "examples/agent-demo" / diff).read_bytes(), check=True)
        # a directory as `before` uses only explicit guards (reference/verify.md, standing guards): pass the base
        # side's netdryrun.yml, as an agent with directory sides must
        guards = before / "netdryrun.yml"
        if not guards.exists():
            problems.append(f"verify_change: no {guards} to pass as the standing guards")
        v = await call("verify_change", topology=str(before / "topology.clab.yml"), before=str(before), after=str(after),
                       intent=sys.argv[6], guards=str(guards))
        known = sys.argv[7] if len(sys.argv) > 7 else ""
        if v.get("status") == "inconclusive" and known and re.search(known, json.dumps(v)):
            # a documented, fail-safe INCONCLUSIVE (the acceptance matrix names it and why): reported, not a problem
            print("KNOWN " + json.dumps({"status": v.get("status"), "match": known}))
        elif v.get("status") not in ("matched", "failed", "no_change"):
            problems.append(f"verify_change: status {v.get('status')}: {str(v)[:300]}")
        if v.get("guards_source") != "explicit":
            problems.append(f"verify_change: guards_source {v.get('guards_source')!r}, not the explicit guards")
    print("RESULTS " + json.dumps(results))
    print("VERIFY " + json.dumps({k: v.get(k) for k in ("status", "verdict")}))
    print("PROBLEMS " + json.dumps(problems))

asyncio.run(main())
'''


def items_angle4(ctx: Ctx):
    yield "angle4/mcp", "frr", "the MCP tools on a fresh lab, a leaky change rejected, result sizes", (lambda r: mcp(ctx, r))


def mcp(ctx: Ctx, r: Result) -> None:
    spec = ctx.matrix["mcp"]
    work = ctx.work / "mcp"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    shutil.copytree(ctx.src / "examples" / spec["example"], work / "lab")
    intent = spec.get("intent", "intent:\n  - prefix: 10.101.0.0/24\n    appears_on: [edge1, up1, peer1]\n")
    with LabLock(ctx.args.lock, r.id):
        p = sh([ctx.python, "-c", MCP_SMOKE, ctx.ndr, work, ctx.src, spec["leaky"], spec["fix"], intent,
                spec.get("verify_known_inconclusive", {}).get("match", "")], timeout=5400)
        left = leftovers()
    res = re.search(r"^RESULTS (.*)$", p.out, re.M)
    probs = re.search(r"^PROBLEMS (.*)$", p.out, re.M)
    sizes = json.loads(res.group(1)) if res else []
    problems = json.loads(probs.group(1)) if probs else [f"the smoke test did not finish: exit {p.code}"]
    r.seconds = p.seconds
    r.expected = "leaky change: DO NOT APPLY; fix: passed; record and verify answer"
    r.got = "; ".join(problems) or "as expected"
    r.note = ", ".join(f"{s['tool']} {s['tokens']} tokens" for s in sizes)
    if re.search(r"^KNOWN ", p.out, re.M):
        r.note += f"; verify_change INCONCLUSIVE, known: {spec['verify_known_inconclusive']['why']}"
    r.status = PASS if not problems and not left and "Traceback" not in p.out else FAIL
    if left:
        r.note += f"; left behind: {', '.join(left)}"
    if r.status != PASS:
        r.evidence = p.out[-6000:]


# ------------------------------------------------------------------------------------------------- the run

ANGLES = {"1": items_angle1, "2": items_angle2, "3": items_angle3, "4": items_angle4}


def prepare(args, work: Path) -> tuple[Path, Path, Path, str]:
    """A clean clone of this repository's HEAD, its wheel, and a fresh virtualenv with the wheel installed."""
    sha = sh(["git", "rev-parse", "HEAD"], cwd=ROOT).out.strip()
    src = work / "src"
    if not (src / ".git").exists() or sh(["git", "rev-parse", "HEAD"], cwd=src).out.strip() != sha:
        shutil.rmtree(src, ignore_errors=True)
        p = sh(["git", "clone", "-q", "--no-local", ROOT, src], timeout=900)
        if p.code:
            raise SystemExit(f"clone failed: {p.out}")
        sh(["git", "checkout", "-q", sha], cwd=src)
    venv = work / "venv"
    ndr = venv / "bin" / "netdryrun"
    want = f"netdryrun {args.version}"
    if not ndr.exists() or sh([ndr, "--version"]).out.strip() != want:
        shutil.rmtree(venv, ignore_errors=True)
        shutil.rmtree(work / "dist", ignore_errors=True)
        for cmd in ([sys.executable, "-m", "venv", venv], [venv / "bin/python", "-m", "pip", "install", "-q", "build", "tiktoken"],
                    [venv / "bin/python", "-m", "build", "-q", "--wheel", "-o", work / "dist", src]):
            p = sh(cmd, timeout=1800)
            if p.code:
                raise SystemExit(f"{' '.join(map(str, cmd))} failed:\n{p.out[-3000:]}")
        wheel = next((work / "dist").glob("netdryrun-*.whl"))
        p = sh([venv / "bin/python", "-m", "pip", "install", "-q", wheel], timeout=1800)
        if p.code or sh([ndr, "--version"]).out.strip() != want:
            raise SystemExit(f"installing {wheel.name} did not give `{want}`:\n{p.out[-3000:]}")
    return src, ndr, venv / "bin" / "python", sha


def render(version: str, sha: str, results: list[Result], started: str) -> str:
    counts = {s: sum(r.status == s for r in results) for s in (PASS, FAIL, NOT_COVERED)}
    ok = not counts[FAIL] and not counts[NOT_COVERED]
    lines = [f"# Acceptance from five angles: Netdryrun {version}", "",
             "Written by `scripts/acceptance.py` (Layer 5b, [RELEASING.md](../../RELEASING.md)). Angle 5 (the adversary) "
             "is recorded by hand in `acceptance-adversary.md` ([prompt](../ACCEPTANCE-PROMPT.md)).", "",
             f"Commit `{sha}`; started {started}. **{'ACCEPTED' if ok else 'NOT ACCEPTED'}**: {counts[PASS]} pass, "
             f"{counts[FAIL]} fail, {counts[NOT_COVERED]} not covered.", ""]
    names = {"angle1": "Angle 1: each network OS", "angle2": "Angle 2: the end user", "angle3": "Angle 3: the system integrator",
             "angle4": "Angle 4: the AI agent"}
    for angle, title in names.items():
        rows = [r for r in results if r.angle == angle]
        if not rows:
            continue
        lines += [f"## {title}", "", "| Item | Driver | Result | Expected | Got | Time | Note |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            cell = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
            lines.append(f"| {cell(r.title)} | {r.driver} | **{r.status}** | {cell(r.expected)} | {cell(r.got)} | "
                         f"{r.seconds:.0f} s | {cell(r.note)} |")
        lines.append("")
    for r in results:
        if r.evidence:
            lines += [f"<details><summary>{r.status}: {r.id}</summary>", "", "```text", r.evidence.replace("```", "'''"), "```",
                      "", "</details>", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="the release under test (default: pyproject.toml's version)")
    ap.add_argument("--work", help="work folder (default ~/ndr-acceptance/<version>)")
    ap.add_argument("--out", help="where acceptance.json and acceptance.md go (default releases/<version>)")
    ap.add_argument("--only", help="comma-separated glob patterns of item ids, e.g. 'angle1/frr/*'")
    ap.add_argument("--angles", default="1,2,3,4", help="angles to run (default 1,2,3,4)")
    ap.add_argument("--fresh", action="store_true", help="ignore results kept from an interrupted run")
    ap.add_argument("--lock", default=DEFAULT_LOCK, help=f"the lab lock directory (default {DEFAULT_LOCK})")
    ap.add_argument("--list", action="store_true", help="list the items and exit")
    args = ap.parse_args()
    if not args.version:
        args.version = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    work = Path(args.work or Path.home() / "ndr-acceptance" / args.version)
    out = Path(args.out or ROOT / "releases" / args.version)
    work.mkdir(parents=True, exist_ok=True)
    matrix = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if args.list:
        src, ndr, python, sha = ROOT, Path("netdryrun"), Path(sys.executable), "HEAD"
    else:
        src, ndr, python, sha = prepare(args, work)
    ctx = Ctx(args, matrix, work, src, ndr, python, sha, docs=documented_examples())
    state_path = work / "state.json"
    state = {} if args.fresh or not state_path.exists() else json.loads(state_path.read_text())
    done = {k: v for k, v in state.get("results", {}).items() if state.get("sha") == sha}
    ctx.exits = state.get("exits", {}) if state.get("sha") == sha else {}
    patterns = [p for p in (args.only or "").split(",") if p]
    results = []
    for angle in args.angles.split(","):
        for id_, drv, title, fn in ANGLES[angle](ctx):
            if patterns and not any(fnmatch.fnmatch(id_, p) for p in patterns):
                continue
            if args.list:
                print(id_)
                continue
            if id_ in done:
                results.append(Result(**done[id_]))
                print(f"[kept] {id_}: {done[id_]['status']}", flush=True)
                continue
            r = Result(id_, f"angle{angle}", drv, title, sha=sha)
            print(f"== {id_}", flush=True)
            try:
                fn(r)
            except Exception as e:   # one item's harness failure is that item's failure, never the run's silence
                import traceback
                r.status, r.note, r.evidence = FAIL, f"harness error: {e!r}"[:300], traceback.format_exc()[-4000:]
            left = leftovers()
            if left:
                r.status, r.note = FAIL, f"{r.note}; lab left behind: {', '.join(left)}".strip("; ")
                for x in left:
                    sh(["docker", "rm", "-f", x], timeout=120)
            print(f"   {r.status}: {r.got} ({r.seconds:.0f} s) {r.note}", flush=True)
            results.append(r)
            done[id_] = asdict(r)
            state_path.write_text(json.dumps({"sha": sha, "results": done, "exits": ctx.exits}, indent=1))
    if args.list:
        return 0
    # A claimed driver with no passing live item is not covered, whatever else ran
    for drv, spec in matrix["drivers"].items():
        mine = [r for r in results if r.driver == drv]
        if spec.get("claimed") and not patterns and not any(r.status == PASS for r in mine):
            results.append(Result(f"angle1/{drv}/covered", "angle1", drv, f"{drv} covered live", NOT_COVERED,
                                  note="a driver the release claims has no passing live run", sha=sha))
    out.mkdir(parents=True, exist_ok=True)
    (out / "acceptance.json").write_text(json.dumps({"schema": "netdryrun.acceptance/v1", "version": args.version, "sha": sha,
                                                     "started": started, "items": [asdict(r) for r in results]}, indent=1) + "\n")
    (out / "acceptance.md").write_text(render(args.version, sha, results, started) + "\n", encoding="utf-8")
    bad = [r for r in results if r.status != PASS]
    print(f"acceptance: {len(results) - len(bad)} pass, {len(bad)} not passing; wrote {out / 'acceptance.md'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
