"""The Netdryrun release gate: run the automatic layers and record what cleared a release.

Netdryrun sells one thing, a verdict people can trust, so this gate hunts above all for false
passes. Every layer is a list of checks; each check has a severity:

  BLOCKER  a failure stops the release (the script exits 1)
  MAJOR    must be fixed, or accepted with a written reason in releases/<version>/accepted.json
  INFO     recorded, never blocks

A check that cannot run (a tool is missing, no lab machine) is SKIP, never PASS. With --strict, a
skipped BLOCKER counts as a failure; CI always runs with --strict.

Layers (RELEASING.md explains each one):
  python scripts/release_gate.py static          lint, workflow lint, public facts, version consistency
  python scripts/release_gate.py unit            tests on Python 3.10-3.14 and in a plain container, coverage
  python scripts/release_gate.py mutation        mutmut on the verdict modules; survivors block
  python scripts/release_gate.py live            the built wheel on the lab machine: examples, corpora, chaos
  python scripts/release_gate.py after-publish X pip and uvx from PyPI, MCP handshake, one live example,
                                                release consistency (every public place names X)
  python scripts/release_gate.py consistency     release consistency alone, on main (the nightly; not a release layer)
  python scripts/release_gate.py all             static, unit, mutation and live, in that order
  python scripts/release_gate.py report          rebuild GATE.md from the recorded layers

Each layer writes releases/<version>/gate/<layer>.json, then GATE.md is rebuilt from every layer
recorded for that version (layers run on different machines and at different times). GATE.md says
CLEARED only when every layer ran on the same clean commit with no BLOCKER failed or skipped and
every MAJOR failure accepted.

Dependency-light on purpose: the standard library only, plus PyYAML (a Netdryrun dependency) in
the live layer. The tools it drives (ruff, actionlint, shellcheck, uv, docker, mutmut, containerlab)
are found on PATH or in the running Python.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "netdryrun"

# Every Python version Netdryrun supports. The static layer checks pyproject.toml agrees.
PYTHONS = ("3.10", "3.11", "3.12", "3.13", "3.14")
COVERAGE_PYTHON = "3.12"          # the interpreter whose run also measures coverage
SLIM_IMAGE = "python:3.12-slim"   # a plain container: no containerlab, no Docker, like CI runners

# The modules that decide a verdict. Coverage is reported for them; mutation testing attacks them.
VERDICT_MODULES = {
    "checks": "src/netdryrun/checks.py",
    "config": "src/netdryrun/config.py",
    "runner": "src/netdryrun/runner.py",
    "drivers": "src/netdryrun/drivers/",
    # verify (0.4): the diff and the match against the intent decide its verdict; the intent parser decides
    # what a declaration may explain
    "verify.engine": "src/netdryrun/verify/engine.py",
    "verify.intent": "src/netdryrun/verify/intent.py",
    # the rest of verify (0.4 release gate): what is collected and normalised (frr, snapshot), when a snapshot is
    # taken (converge), what may be compared at all (run: sides, binds, nodes, config load) and what the report
    # and the PR header say (report)
    "verify.frr": "src/netdryrun/verify/frr.py",
    "verify.snapshot": "src/netdryrun/verify/snapshot.py",
    "verify.converge": "src/netdryrun/verify/converge.py",
    "verify.run": "src/netdryrun/verify/run.py",
    "verify.report": "src/netdryrun/verify/report.py",
}

# Coverage floors (percent of lines and branches). A ratchet: raise a floor when coverage rises,
# never lower one to make a release pass. Raised after the mutation-testing work of 2026-10-27 to the
# coverage measured then (Python 3.12, rounded down; drivers measured 100, floored at 99 so that one
# platform-specific branch does not fail the gate): checks 99.5, config 99.2, runner 98.3, drivers 100.
# The runner's deploy, scenario and gate paths run on a fake lab and a fake clock (tests/test_verdict_runner.py).
# verify.engine and verify.intent joined in 0.4 at the coverage measured then (Python 3.10, rounded down):
# engine 95.9, intent 93.3.
# Verdict modules gated on the functions that decide what verify compares, refuses or reports (coordinator, 0.4):
# a survivor there, or a mutant in code no test runs anywhere in the module, is a BLOCKER; the other survivors
# (parsers that fail closed, rendering) are counted and named, and their full zero is a 0.4.1 gate item. A function
# found on that path joins the list (a floor, not a ceiling).
SCOPED_FUNCTIONS = {
    "verify.frr": {"_boot_free", "parse_link_local", "link_local_names", "configured_link_locals",
                   "link_local_owners", "parse_running_config", "qualified", "cond_adv_timer"},
    "verify.run": {"check_sides", "check_changed_binds", "bind_reach", "is_router_config", "classify_nodes",
                   "check_config_loaded", "collect", "unobserved_reasons"},
    "verify.converge": {"stable_snapshot", "_not_ready"},
    "verify.snapshot": {"ItemKey.__post_init__", "NodeSnapshot.__post_init__", "value_matches_kind",
                        "Snapshot.stability_view", "Snapshot.items"},
    "verify.report": {"to_dict", "VerifyResult.verdict", "VerifyResult.exit_code"},
}
SCOPED_KNOWN_LABEL = "parsers that fail closed and rendering; their full zero is a 0.4.1 gate item"


def gated(module: str, name: str, status: str) -> bool:
    """Whether a surviving mutant blocks the release: always in a fully gated module; in a scoped one, when its
    function is on the verdict path or no test runs its code (no untested code in a verdict module ships)."""
    if module not in SCOPED_FUNCTIONS or status == "no tests":
        return True
    fn = mutant_function(name).removeprefix(f"{module}.")
    return fn in SCOPED_FUNCTIONS[module]


# verify.* raised or set on 2026-10-30 (0.4 release gate) to the coverage measured then, rounded down, minus one
COVERAGE_FLOORS = {"checks": 99, "config": 99, "runner": 98, "drivers": 99, "verify.engine": 98, "verify.intent": 97,
                   "verify.frr": 88, "verify.snapshot": 90, "verify.converge": 96, "verify.run": 83, "verify.report": 88}

# Files that are evidence of past runs, and advisories about past versions (which name those versions on
# purpose; tests/test_advisory_fixtures.py keeps their fixtures honest): never rewritten, so never linted or
# version-checked.
EVIDENCE = ("examples/agent-eval/results/", "examples/agent-eval/validation/", "corpus/results/", "corpus/v2/results/",
            "advisories/")

# Expected exit code of `netdryrun run` when it is stopped by a signal (128 + signal number, the
# shell convention). SIGINT is documented (CHANGELOG 0.3.0: "Interrupted: no verdict", 130).
SIGNAL_EXIT = {"SIGINT": 130, "SIGTERM": 143}

LAYERS = {  # name -> title, in report order
    "static": "Layer 1: static",
    "unit": "Layer 2: unit tests on every supported Python",
    "mutation": "Layer 4: mutation testing",
    "live": "Layer 5: live matrix on the built package",
    "after-publish": "Layer 7: after-publish proof",
}
# Run by the nightly gate on main, outside the release record (GATE.md never waits for it).
CHECK_LAYERS = {"consistency": "Release consistency: every public place names the release"}
BLOCKER, MAJOR, INFO = "BLOCKER", "MAJOR", "INFO"
PASS, FAIL, SKIP, ACCEPTED = "PASS", "FAIL", "SKIP", "ACCEPTED"


# --------------------------------------------------------------------------------------------
# Checks, layers and running commands
# --------------------------------------------------------------------------------------------

@dataclass
class Check:
    id: str                 # stable, used in accepted.json as "<layer>/<id>"
    title: str
    severity: str
    status: str
    seconds: float = 0.0
    summary: str = ""       # one line for the table
    output: str = ""        # the evidence: command output (tail) or a computed listing
    command: str = ""


@dataclass
class Proc:
    code: int
    out: str
    seconds: float


def run(cmd: list[str], *, cwd: Path = ROOT, timeout: float = 900, env: dict | None = None) -> Proc:
    """Run a command, stdout and stderr merged in order. Never raises for a missing tool or a timeout."""
    t0 = time.monotonic()
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return Proc(p.returncode, p.stdout.decode("utf-8", "replace"), time.monotonic() - t0)
    except FileNotFoundError:
        return Proc(127, f"command not found: {cmd[0]}", time.monotonic() - t0)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace")
        return Proc(124, f"{out}\n[timed out after {timeout:.0f} s]", time.monotonic() - t0)


def tail(text: str, lines: int = 60) -> str:
    rows = text.rstrip().splitlines()
    return "\n".join(rows if len(rows) <= lines else [f"[... {len(rows) - lines} earlier lines]"] + rows[-lines:])


def cmdline(cmd: list) -> str:
    return " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)


class Layer:
    """One layer's run: its checks, the environment it ran in, and extra Markdown for GATE.md."""

    def __init__(self, name: str, args: argparse.Namespace):
        self.name, self.args = name, args
        self.checks: list[Check] = []
        self.tools: dict[str, str] = {}
        self.sections: list[str] = []      # extra Markdown (coverage table, mutant list)
        self.started = now()
        self.t0 = time.monotonic()

    def add(self, id: str, title: str, severity: str, ok: bool | None, summary: str = "",
            output: str = "", seconds: float = 0.0, command: str = "") -> Check:
        """ok=True PASS, ok=False FAIL, ok=None SKIP (a FAIL under --strict when it is a BLOCKER)."""
        status = PASS if ok else FAIL if ok is False else SKIP
        if status == SKIP and self.args.strict and severity == BLOCKER:
            status, summary = FAIL, f"skipped under --strict: {summary}"
        check = Check(id, title, severity, status, round(seconds, 1), summary, output, command)
        self.checks.append(check)
        print(f"  [{check.status}] {severity:<7} {title}" + (f": {summary}" if summary else ""), flush=True)
        return check

    def add_proc(self, id: str, title: str, severity: str, cmd: list, proc: Proc, summary: str = "") -> Check:
        """A check that passes when the command exits 0."""
        ok = proc.code == 0
        first = summary if ok and summary else (proc.out.strip().splitlines() or [""])[-1][:200]
        return self.add(id, title, severity, ok, first, tail(proc.out), proc.seconds, cmdline(cmd))

    def tool(self, name: str, version_cmd: list) -> str | None:
        """Record a tool's version; None when it is not installed."""
        p = run(version_cmd, timeout=60)
        if p.code != 0:
            return None
        version = next((ln.strip() for ln in p.out.splitlines() if ln.strip()), "?")
        self.tools[name] = version.removeprefix(name + " ")[:80]
        return version

    def record(self) -> dict:
        return {"layer": self.name, "title": {**LAYERS, **CHECK_LAYERS}[self.name], "version": self.args.version,
                "started": self.started, "seconds": round(time.monotonic() - self.t0, 1),
                "git": git_state(), "host": f"{platform.system()} {platform.release()} ({platform.machine()})",
                "python": platform.python_version(), "strict": bool(self.args.strict),
                "tools": self.tools, "checks": [asdict(c) for c in self.checks], "sections": self.sections}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def venv_bin(venv: Path, name: str) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / (name + (".exe" if os.name == "nt" else ""))


# --------------------------------------------------------------------------------------------
# Facts read from the repository
# --------------------------------------------------------------------------------------------

def pyproject_text() -> str:
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def package_version() -> str:
    m = re.search(r'(?ms)^\[project\]\s*$.*?^version\s*=\s*"([^"]+)"', pyproject_text())
    if not m:
        raise SystemExit("release_gate: no [project] version in pyproject.toml")
    return m.group(1)


def git(*args: str) -> str | None:
    p = run(["git", "-C", ROOT, *args], timeout=60)
    return p.out.strip() if p.code == 0 else None


def git_state() -> dict:
    """The commit under test. Falls back to reading .git by hand where git can't (a Windows
    worktree seen from WSL); the tree's cleanliness is then unknown, which never clears a release."""
    sha = git("rev-parse", "HEAD")
    if sha:
        # the gate's own records (releases/) don't make the code under test dirty
        dirty = git("status", "--porcelain", "--untracked-files=no", "--", ".", ":(exclude)releases")
        return {"sha": sha, "dirty": bool(dirty) if dirty is not None else None,
                "branch": git("rev-parse", "--abbrev-ref", "HEAD")}
    sha, branch = _read_head()
    return {"sha": sha, "dirty": None, "branch": branch}


def _read_head() -> tuple[str | None, str | None]:
    def local(p: str) -> Path:  # C:/x/y -> /mnt/c/x/y when running in WSL
        m = re.match(r"^([A-Za-z]):[/\\](.*)", p)
        return Path(f"/mnt/{m.group(1).lower()}/{m.group(2)}") if m and os.name != "nt" else Path(p)
    try:
        dotgit = ROOT / ".git"
        gitdir = local(dotgit.read_text().split("gitdir:", 1)[1].strip()) if dotgit.is_file() else dotgit
        head = (gitdir / "HEAD").read_text().strip()
        if not head.startswith("ref:"):
            return head, None
        ref = head.split(" ", 1)[1]
        common = gitdir / (gitdir / "commondir").read_text().strip() if (gitdir / "commondir").exists() else gitdir
        for base in (gitdir, common):
            if (base / ref).exists():
                return (base / ref).read_text().strip(), ref.removeprefix("refs/heads/")
        for line in (common / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line.split()[0], ref.removeprefix("refs/heads/")
    except (OSError, IndexError):
        pass
    return None, None


def matches(rel: str, pattern: str) -> bool:
    """'*.sh' matches a file name anywhere; 'dir/*' anything under dir/; else the whole path."""
    if "/" not in pattern:
        return fnmatch.fnmatch(rel.rsplit("/", 1)[-1], pattern)
    if pattern.endswith("/*"):
        return rel.startswith(pattern[:-1])
    return fnmatch.fnmatch(rel, pattern)


def tracked_files(patterns: tuple[str, ...]) -> list[Path]:
    """Repository files matching patterns (see matches), evidence folders excluded, git-tracked when git works."""
    listed = git("ls-files")
    if listed is not None:
        files = [ROOT / f for f in listed.splitlines()]
    else:
        skip = {".git", "mutants", ".venv", "node_modules", "site", ".cache", "releases"}
        files = [p for p in ROOT.rglob("*") if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]
    out = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if any(rel.startswith(e) for e in EVIDENCE):
            continue
        if any(matches(rel, p) for p in patterns) and f.exists():
            out.append(f)
    return sorted(out)


def documented_examples() -> dict[str, dict]:
    """The "At a glance" table of website/docs/examples.md: each example's expected outcomes
    (summary lines, paired with exit codes) and its documented time in seconds."""
    rows = {}
    for line in (ROOT / "website" / "docs" / "examples.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*\[([\w-]+)\]\(#[\w-]+\)[^|]*\|(.*)\|\s*$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        if len(cells) < 5:
            continue
        outcomes = re.findall(r"`([^`]+)`", cells[2])
        codes = [int(c) for c in re.findall(r"`(\d+)`", cells[3])]
        times = [int(t) for t in re.findall(r"(\d+)", cells[4])]
        rows[m.group(1)] = {"outcomes": outcomes, "codes": codes, "seconds": times}
    return rows


def example_dirs() -> list[str]:
    return sorted(p.parent.name for p in (ROOT / "examples").glob("*/netdryrun.yml"))


# --------------------------------------------------------------------------------------------
# Layer 1: static
# --------------------------------------------------------------------------------------------

def layer_static(args) -> Layer:
    layer = Layer("static", args)

    # ruff: the dev extra pins it, so prefer the running Python's copy over one on PATH
    ruff = [sys.executable, "-m", "ruff"] if run([sys.executable, "-m", "ruff", "--version"]).code == 0 else ["ruff"]
    if layer.tool("ruff", [*ruff, "--version"]):
        cmd = [*ruff, "check", "--output-format", "concise", "."]
        layer.add_proc("ruff", "ruff (config in pyproject.toml)", BLOCKER, cmd, run(cmd))
    else:
        layer.add("ruff", "ruff (config in pyproject.toml)", BLOCKER, None, "ruff is not installed (pip install -e '.[dev]')")

    # actionlint, with shellcheck on every run: block when shellcheck is installed
    shellcheck = shutil.which("shellcheck")
    if layer.tool("actionlint", ["actionlint", "-version"]):
        cmd = ["actionlint", "-color=false"] + ([f"-shellcheck={shellcheck}"] if shellcheck else ["-shellcheck="])
        layer.add_proc("actionlint", "actionlint on every workflow" + (" (with shellcheck)" if shellcheck else ""),
                       BLOCKER, cmd, run(cmd), "clean")
    else:
        layer.add("actionlint", "actionlint on every workflow", BLOCKER, None, "actionlint is not installed")

    # shellcheck on every tracked shell script: errors block, warnings are MAJOR
    scripts = [str(p.relative_to(ROOT)) for p in tracked_files(("*.sh",))]
    if shellcheck and layer.tool("shellcheck", ["shellcheck", "--version"]):
        layer.tools["shellcheck"] = run(["shellcheck", "--version"]).out.split("version:")[-1].split()[0]
        for level, sev in (("error", BLOCKER), ("warning", MAJOR)):
            cmd = ["shellcheck", "-S", level, "-f", "gcc", *scripts]
            p = run(cmd)
            n = len(p.out.strip().splitlines()) if p.code else 0
            layer.add(f"shellcheck-{level}", f"shellcheck, {level} level, {len(scripts)} scripts", sev, p.code == 0,
                      "clean" if p.code == 0 else f"{n} finding(s)", tail(p.out), p.seconds, f"shellcheck -S {level} <scripts>")
    else:
        layer.add("shellcheck-error", "shellcheck on every shell script", BLOCKER, None, "shellcheck is not installed")

    # GitHub evaluates ${{ }} anywhere in a workflow string; an empty one breaks the whole file
    t0 = time.monotonic()
    empties = []
    for f in [ROOT / "action.yml", *sorted((ROOT / ".github" / "workflows").glob("*.yml"))]:
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"\$\{\{(.*?)\}\}", text, re.S):
            if not m.group(1).strip():
                empties.append(f"{f.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1}: empty expression")
    layer.add("empty-expressions", "no empty ${{ }} in action.yml or workflows", BLOCKER, not empties,
              f"{len(empties)} found" if empties else "none", "\n".join(empties), time.monotonic() - t0)

    cmd = [sys.executable, "scripts/sync_facts.py", "--check"]
    layer.add_proc("sync-facts", "public facts match the source (sync_facts.py --check)", BLOCKER, cmd, run(cmd))

    t0 = time.monotonic()
    found, problems = version_sources(args.version)
    listing = "\n".join(f"{'ok ' if v == args.version else 'BAD'} {v:<10} {where}" for where, v in found)
    layer.add("versions", f"every version reference says {args.version}", BLOCKER, not problems,
              f"{len(found)} references agree" if not problems else "; ".join(problems[:3]),
              listing, time.monotonic() - t0)

    t0 = time.monotonic()
    py_problems = python_support_problems()
    layer.add("python-range", f"pyproject.toml declares Python {PYTHONS[0]} to {PYTHONS[-1]}, the versions tested",
              MAJOR, not py_problems, "; ".join(py_problems) or "requires-python and classifiers agree",
              seconds=time.monotonic() - t0)

    t0 = time.monotonic()
    docs, dirs = documented_examples(), example_dirs()
    missing = [d for d in dirs if d not in docs]
    unknown = [d for d in docs if d not in dirs]
    unpaired = [d for d, row in docs.items() if len(row["outcomes"]) != len(row["codes"]) or not row["codes"]]
    bad = [f"undocumented: {', '.join(missing)}"] * bool(missing) + [f"no such example: {', '.join(unknown)}"] * bool(unknown) \
        + [f"expected result without an exit code: {', '.join(unpaired)}"] * bool(unpaired)
    layer.add("examples-documented", "every example has a documented expected result and exit code", MAJOR,
              not bad, "; ".join(bad) or f"{len(dirs)} examples", json.dumps(docs, indent=1), time.monotonic() - t0)

    # the live layer removes leftovers by this prefix only, so a lab we ship under another name would leak
    topos = sorted(p for d in ("examples", "corpus") for p in (ROOT / d).rglob("*.clab.yml"))
    names = {p: (re.search(r"^name:\s*(\S+)", p.read_text(encoding="utf-8"), re.M) or [None, ""])[1] for p in topos}
    off = [f"{p.relative_to(ROOT).as_posix()} ({n or 'no name'})" for p, n in names.items()
           if not n.startswith(OUR_LAB_PREFIX.removeprefix("clab-"))]
    layer.add("lab-names", "every topology we ship is named ndr-*", BLOCKER, not off,
              "; ".join(off) or f"{len(topos)} topologies")
    tracked = run(["git", "ls-files"]).out.split()
    texts = []
    for f in tracked:
        try:
            texts.append((f, (ROOT / f).read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            pass   # binary or unreadable: no public text in it
    retired = retired_string_problems(texts)
    layer.add("retired-strings", "no retired public string outside the history (CHANGELOG, advisories, records)",
              BLOCKER, not retired, "; ".join(retired[:10]) or "none")

    if args.candidate:
        candidate_checks(layer, args.version)
    return layer


def version_sources(version: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Every place that states the package version, and what each one says."""
    found: list[tuple[str, str]] = []
    m = re.search(r'(?ms)^\[project\]\s*$.*?^version\s*=\s*"([^"]+)"', pyproject_text())
    found.append(("pyproject.toml [project] version", m.group(1) if m else "missing"))
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', (SRC / "__init__.py").read_text(encoding="utf-8"), re.M)
    found.append(("src/netdryrun/__init__.py __version__", m.group(1) if m else "missing"))
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    found.append(("server.json version", server.get("version", "missing")))
    for pkg in server.get("packages", []):
        found.append((f"server.json packages[{pkg.get('identifier')}] version", pkg.get("version", "missing")))
    m = re.search(r"^## (\d+\.\d+\.\d+)\b", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    found.append(("CHANGELOG.md newest release heading", m.group(1) if m else "missing"))

    # `uses: netdryrun/Netdryrun@vX.Y.Z` in docs, examples and workflows; `netdryrun==X.Y.Z` and
    # `netdryrun@X.Y.Z` (uvx) in the docs. Other projects' tags are not ours to check.
    docs = tracked_files(("README.md", "AGENTS.md", "action.yml", "website/docs/*", "examples/*", ".github/*"))
    for f in docs:
        if f.suffix not in (".md", ".txt", ".yml", ".yaml", ".sh", ".py", ".json"):
            continue
        if f.name == "published-action.yml":   # tests the *published* release: bumped after the proof
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = f.relative_to(ROOT).as_posix()
        patterns = [r"(?i:netdryrun/netdryrun)@v(\d+\.\d+\.\d+)"]
        if not rel.startswith("examples/"):   # an example may name the version it was recorded with
            patterns.append(r"\bnetdryrun(?:\[mcp\])?(?:==|@)(\d+\.\d+\.\d+)")
        for pat in patterns:
            for m in re.finditer(pat, text):
                found.append((f"{rel}:{text.count(chr(10), 0, m.start()) + 1} {m.group(0)}", m.group(1)))
    problems = [f"{where} says {v}" for where, v in found if v != version]
    return found, problems


# Public strings the project retired, with the release that retired them. An agent or a user copies these
# exactly, so a doc that still shows one is a wrong instruction. The old text stays only where history is
# recorded: the paths below, and a line that says it is history.
RETIRED = {"SAFE" + " TO PROCEED": "the MCP pass verdict until 0.3.1 (0.3.2: CHECKS PASSED (only what the checks cover))"}
RETIRED_HISTORY_PATHS = ("CHANGELOG.md", "advisories/", "releases/", "examples/agent-eval/results/",
                         "examples/agent-eval/RESULTS.md", "examples/agent-demo/AGENT-RUN.md")
RETIRED_HISTORY_LINE = re.compile(r"\b\d+\.\d+\.\d+ (said|returned)\b|\bbefore \d+\.\d+\.\d+\b|\brenamed\b", re.I)


def retired_string_problems(texts) -> list[str]:
    """`path:line: retired "..." (why)` for each retired string found outside the recorded history."""
    problems = []
    for path, text in texts:
        if path.startswith(RETIRED_HISTORY_PATHS):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for old, why in RETIRED.items():
                if old in line and not RETIRED_HISTORY_LINE.search(line):
                    problems.append(f"{path}:{n}: retired {old!r} ({why})")
    return problems


def python_support_problems() -> list[str]:
    text = pyproject_text()
    problems = []
    m = re.search(r'^requires-python\s*=\s*">=\s*([\d.]+)"', text, re.M)
    if not m or m.group(1) != PYTHONS[0]:
        problems.append(f"requires-python is {m.group(0) if m else 'missing'}, expected >={PYTHONS[0]}")
    missing = [v for v in PYTHONS if f'"Programming Language :: Python :: {v}"' not in text]
    if missing:
        problems.append(f"no classifier for Python {', '.join(missing)}")
    return problems


def candidate_checks(layer: Layer, version: str) -> None:
    """Only for the release candidate itself: the CHANGELOG is cut and the version is unused."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## Unreleased\s*$(.*?)(?=^## )", text, re.M | re.S)
    pending = [ln for ln in (m.group(1) if m else "").splitlines() if ln.strip().startswith(("-", "*"))]
    layer.add("changelog-cut", f"CHANGELOG has no Unreleased entries left (all under {version})", BLOCKER,
              not pending, f"{len(pending)} entries still under Unreleased" if pending else "cut")
    tags = git("tag", "-l", f"v{version}")
    layer.add("tag-unused", f"tag v{version} does not exist yet", BLOCKER,
              None if tags is None else not tags, "git unavailable" if tags is None else ("exists" if tags else "unused"))
    status = http_status(f"https://pypi.org/pypi/netdryrun/{version}/json")
    layer.add("pypi-unused", f"PyPI has no netdryrun {version} yet", BLOCKER,
              None if status is None else status == 404, f"HTTP {status}" if status else "PyPI unreachable")


def http_status(url: str) -> int | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return None


# --------------------------------------------------------------------------------------------
# Layer 2: unit tests on every supported Python, in a plain container, with coverage
# --------------------------------------------------------------------------------------------

def layer_unit(args) -> Layer:
    layer = Layer("unit", args)
    uv = shutil.which("uv")
    if uv:
        layer.tool("uv", ["uv", "--version"])
    work = Path(tempfile.mkdtemp(prefix="ndr-gate-unit-"))
    try:
        for py in args.pythons:
            unit_on_python(layer, py, uv, work)
        unit_in_container(layer)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return layer


def make_venv(py: str, uv: str | None, venv: Path) -> Proc:
    """A fresh virtual environment on Python `py`; uv downloads the interpreter when it is missing."""
    if uv:
        return run([uv, "venv", "-q", "--seed", "--python", py, venv], timeout=600)
    exe = shutil.which(f"python{py}")
    if not exe:
        return Proc(127, f"no uv and no python{py} on PATH", 0)
    return run([exe, "-m", "venv", venv], timeout=600)


def pip_install(uv: str | None, venv: Path, *specs: str) -> Proc:
    python = venv_bin(venv, "python")
    if uv:
        return run([uv, "pip", "install", "-q", "--python", python, *specs], timeout=1200)
    return run([python, "-m", "pip", "install", "-q", "--disable-pip-version-check", *specs], timeout=1200)


def pytest_summary(out: str) -> str:
    m = re.findall(r"^=*\s*(\d+ (?:passed|failed|errors?|skipped)[^\n=]*?) in [\d.]+s", out, re.M)
    return m[-1] if m else (out.strip().splitlines() or ["no output"])[-1][:200]


def unit_on_python(layer: Layer, py: str, uv: str | None, work: Path) -> None:
    venv = work / f"py{py}"
    title = f"unit tests on Python {py}" + (" (with coverage)" if py == COVERAGE_PYTHON else "")
    t0 = time.monotonic()
    p = make_venv(py, uv, venv)
    if p.code == 0:
        p = pip_install(uv, venv, "-e", f"{ROOT}[dev]")
    if p.code != 0:
        # an interpreter we cannot get is a skip; a dev extra that will not install is a failure
        ok = None if p.code == 127 or "No interpreter found" in p.out or "not found" in p.out.lower() else False
        layer.add(f"pytest-{py}", title, BLOCKER, ok, "could not set up: " + p.out.strip()[-200:], tail(p.out),
                  time.monotonic() - t0)
        return
    exact = run([venv_bin(venv, "python"), "-c", "import platform; print(platform.python_version())"]).out.strip()
    cmd = [venv_bin(venv, "python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs"]
    env = dict(os.environ)
    cov_json = work / "coverage.json"
    if py == COVERAGE_PYTHON:
        cmd += ["--cov=netdryrun", "--cov-branch", f"--cov-report=json:{cov_json}"]
        env["COVERAGE_FILE"] = str(work / ".coverage")
    p = run(cmd, env=env, timeout=1800)
    layer.add(f"pytest-{py}", title.replace(f"Python {py}", f"Python {exact or py}"), BLOCKER, p.code == 0,
              pytest_summary(p.out), tail(p.out, 80), time.monotonic() - t0, cmdline(["python", *cmd[1:]]))
    if py == COVERAGE_PYTHON:
        coverage_checks(layer, cov_json if p.code == 0 or cov_json.exists() else None)


def coverage_checks(layer: Layer, cov_json: Path | None) -> None:
    if not cov_json or not cov_json.exists():
        layer.add("coverage", "coverage of the verdict modules", MAJOR, None, "no coverage data (pytest-cov missing?)")
        return
    files = json.loads(cov_json.read_text())["files"]
    rows, below = [], []
    for name, path in VERDICT_MODULES.items():
        parts = [s["summary"] for f, s in files.items() if f.replace("\\", "/").endswith(path) or
                 (path.endswith("/") and path in f.replace("\\", "/"))]
        stmts = sum(s["num_statements"] for s in parts)
        lines = sum(s["covered_lines"] for s in parts)
        branches = sum(s.get("num_branches", 0) for s in parts)
        cbranches = sum(s.get("covered_branches", 0) for s in parts)
        pct = 100.0 * (lines + cbranches) / max(1, stmts + branches)
        floor = COVERAGE_FLOORS[name]
        if pct < floor:
            below.append(f"{name} {pct:.1f}% < {floor}%")
        rows.append(f"| `{path}` | {lines}/{stmts} | {cbranches}/{branches} | {pct:.1f}% | {floor}% |")
    table = ("| Module | Lines | Branches | Covered | Floor |\n|---|---|---|---|---|\n" + "\n".join(rows))
    layer.sections.append("**Coverage of the verdict modules** (lines and branches, Python "
                          f"{COVERAGE_PYTHON}):\n\n{table}")
    layer.add("coverage", "coverage of the verdict modules at or above the floors", MAJOR, not below,
              "; ".join(below) or "all at or above their floors", table)


def unit_in_container(layer: Layer) -> None:
    title = f"unit tests in a plain {SLIM_IMAGE} container (no containerlab, no Docker)"
    if not layer.tool("docker", ["docker", "version", "--format", "{{.Server.Version}}"]):
        layer.add("pytest-container", title, BLOCKER, None, "Docker is not available")
        return
    # Copy the tree inside the container (the mount is read-only) and install it as a normal
    # package, so the tests run against what pip builds, not the source folder.
    script = (
        "set -e\n"
        "if command -v containerlab >/dev/null || command -v docker >/dev/null; then echo 'not a plain environment'; exit 90; fi\n"
        "mkdir /w && tar -C /src --exclude=./mutants --exclude=./.git --exclude=./releases -cf - . | tar -C /w -xf -\n"
        "cd /w && pip install -q --disable-pip-version-check --root-user-action=ignore '.[dev]'\n"
        "python --version\n"
        "python -m pytest -q -p no:cacheprovider -rs\n")
    cmd = ["docker", "run", "--rm", "-v", f"{ROOT}:/src:ro", SLIM_IMAGE, "sh", "-c", script]
    p = run(cmd, timeout=1800)
    layer.add("pytest-container", title, BLOCKER, p.code == 0, pytest_summary(p.out), tail(p.out, 80), p.seconds,
              f"docker run --rm -v <repo>:/src:ro {SLIM_IMAGE} sh -c <install and pytest>")


# --------------------------------------------------------------------------------------------
# Layer 4: mutation testing
# --------------------------------------------------------------------------------------------

CAUGHT = {"killed", "timeout", "segfault"}   # a mutant the tests noticed (a hang or crash counts)


def layer_mutation(args) -> Layer:
    layer = Layer("mutation", args)
    modules = args.modules
    if os.name == "nt":
        layer.add("mutmut", "mutmut runs", BLOCKER, None, "mutmut needs Linux or macOS (use WSL)")
        return layer
    mutmut = [sys.executable, "-m", "mutmut"]
    if not layer.tool("mutmut", [*mutmut, "--version"]):
        layer.add("mutmut", "mutmut runs", BLOCKER, None, "mutmut is not installed in this Python (pip install -e '.[dev]')")
        return layer
    # A fresh mutants/ every time: mutmut caches results, and a stale "killed" would hide a survivor
    shutil.rmtree(ROOT / "mutants", ignore_errors=True)
    globs = [f"netdryrun.{m}.*" if m != "drivers" else "netdryrun.drivers.*" for m in modules]
    cmd = [*mutmut, "run", "--max-children", str(args.jobs), *globs]
    p = run(cmd, timeout=args.mutation_timeout)
    out = p.out.replace("\r", "\n")
    if p.code != 0 or "failed to collect stats" in out:
        layer.add("mutmut", f"mutmut run on {', '.join(modules)}", BLOCKER, False,
                  "mutmut did not complete", tail(out), p.seconds, cmdline(["mutmut", *cmd[3:]]))
        return layer
    results = run([*mutmut, "results", "--all", "true"], timeout=600).out
    status: dict[str, str] = {}
    for line in results.splitlines():
        m = re.match(r"^\s*(netdryrun\.\S+): (.+?)\s*$", line)
        if m:
            status[m.group(1)] = m.group(2)
    accepted = load_accepted(args.version).get("mutants", {})
    survived_names = sorted(n for n, s in status.items() if s != "not checked" and s not in CAUGHT
                            and any(n.startswith(f"netdryrun.{m}.") for m in modules))
    diffs = mutant_diffs(survived_names, mutmut, args.jobs)
    if args.pin_accepted:
        pin_accepted(args, accepted, diffs)
    survivors_all: dict[str, list[str]] = {}
    for module in modules:
        prefix = f"netdryrun.{module}."
        mine = {n: s for n, s in status.items() if n.startswith(prefix)}
        checked = {n: s for n, s in mine.items() if s != "not checked"}
        survived = sorted(n for n, s in checked.items() if s not in CAUGHT)
        unaccepted = [n for n in survived if not accepted_now(accepted, n, diffs)]
        open_ = [n for n in unaccepted if gated(module, n, checked[n])]
        known = [n for n in unaccepted if n not in open_]
        stale = [n for n in survived if n in accepted and not accepted_now(accepted, n, diffs)]
        survivors_all[module] = survived
        caught = len(checked) - len(survived)
        score = 100.0 * caught / max(1, len(checked))
        untested = sum(checked[n] == "no tests" for n in survived)
        by_class = accepted_by_class(accepted, survived, diffs)
        summary = (f"{len(mine)} generated, {caught}/{len(checked)} caught ({score:.1f}%); not caught: "
                   f"{len(survived) - untested} survived the tests, {untested} in code no test runs"
                   + (f", {sum(by_class.values())} accepted ("
                      + ", ".join(f"{v} {k}" for k, v in sorted(by_class.items())) + ")"
                      if by_class else "")
                   + (f"; {len(stale)} accepted entries don't accept their mutant (diff moved, no class, or no reviewed argument): see the notes"
                      if stale else "")
                   + (f"; {len(known)} outside the gated functions ({SCOPED_KNOWN_LABEL})" if known else ""))
        if known:
            by_fn: dict[str, int] = {}
            for n in known:
                by_fn[mutant_function(n)] = by_fn.get(mutant_function(n), 0) + 1
            layer.sections.append(f"**{VERDICT_MODULES[module]}: {len(known)} survivors outside the gated functions** "
                                  f"({SCOPED_KNOWN_LABEL}): " + ", ".join(f"`{f}` {c}" for f, c in
                                                                         sorted(by_fn.items(), key=lambda x: -x[1])))
        if not checked:
            layer.add(f"mutants-{module}", f"no surviving mutants in {VERDICT_MODULES[module]}", BLOCKER, False,
                      "no mutants were checked", tail(out), p.seconds)
            continue
        layer.add(f"mutants-{module}", f"no surviving mutants in {VERDICT_MODULES[module]}", BLOCKER, not open_,
                  summary, tail("\n".join(f"{n}: {checked[n]}" + (f"  [accepted, {accepted[n]['class']}: {reason(accepted[n])}]" if accepted_now(accepted, n, diffs)
                                                                   else f"  [NOT accepted: {acceptance_problem(accepted[n], n, diffs)}]" if n in accepted else "")
                                          for n in survived), 40), p.seconds if module == modules[0] else 0.0,
                  cmdline(["mutmut", *cmd[3:]]))
    if args.carry_mutation:
        carry_mutation(layer, args.carry_mutation, modules)
    require_every_module(layer, [*modules, *(c.id.removeprefix("mutants-") for c in layer.checks)])
    gone = sorted(n for n in accepted if n not in survived_names
                  and any(n.startswith(f"netdryrun.{m}.") for m in modules))
    if gone:
        layer.sections.append(f"**Accepted entries that no longer survive** ({len(gone)}; remove them from "
                              "accepted.json): " + ", ".join(f"`{n}`" for n in gone[:40]) + (" ..." if len(gone) > 40 else ""))
    layer.sections.append(mutant_section(survivors_all, status, accepted, diffs, args))
    return layer


def carry_mutation(layer: Layer, path: str, modules: list[str]) -> None:
    """--carry-mutation: keep an earlier mutation record for each verdict module not mutated in this run, only
    when its source is byte-identical at this commit (0.4.0: the interop fixes changed drivers only). A module
    whose source changed since, or that git can't compare, fails: it must be mutated at this commit."""
    prev = json.loads(Path(path).read_text(encoding="utf-8"))
    sha = prev["git"]["sha"]
    for c in prev["checks"]:
        module = c["id"].removeprefix("mutants-")
        if module not in VERDICT_MODULES or module in modules:
            continue
        src = VERDICT_MODULES[module]
        changed = git("diff", "--name-only", sha, "HEAD", "--", src)
        if changed == "":
            layer.add(c["id"], c["title"], c["severity"], {PASS: True, FAIL: False}.get(c["status"]),
                      f"carried over from {sha[:7]}: {src} is byte-identical at this commit. {c['summary']}",
                      c["output"], 0.0, c["command"])
            layer.sections += [s for s in prev.get("sections", []) if s.startswith(f"**{src}:")]
        else:
            why = f"{changed.replace(chr(10), ', ')} changed since {sha[:7]}" if changed else                 f"git can't compare {src} with {sha[:7]}"
            layer.add(c["id"], c["title"], c["severity"], False, f"not carried over: {why}: mutate it at this commit")


def require_every_module(layer: Layer, covered: list[str]) -> None:
    """Every verdict module is mutated in this run or carried over: a partial run never reads as a full layer."""
    for module, src in VERDICT_MODULES.items():
        if module not in covered:
            layer.add(f"mutants-{module}", f"no surviving mutants in {src}", BLOCKER, False,
                      "not mutated at this commit (run it, or --carry-mutation a record whose file is unchanged)")


def mutant_fingerprint(diff: str) -> str:
    """What a mutant changes, without line numbers: the diff body minus its ---/+++/@@ headers. An accepted
    entry pins this, so when code moves and mutmut renumbers its mutants, an ID that now names a different
    mutant is no longer accepted (it happened in 0.3.1: x_run__mutmut_225 came to mean `d.rc == 0`)."""
    body = [ln.rstrip() for ln in diff.splitlines() if not ln.startswith(("---", "+++", "@@"))]
    return hashlib.sha256("\n".join(body).encode()).hexdigest()[:16]


def reason(entry) -> str:
    return entry if isinstance(entry, str) else entry.get("reason", "")


# Every accepted survivor says why in one of these classes (RELEASE-GATE.md, Layer 4).
ACCEPT_CLASSES = ("message-text", "logging", "equivalent", "timing-only", "safety")

# The functions that decide a verdict: check evaluation, the convergence and no-neighbor gates, inconclusive
# classification, the fault-visible wait and the exit-code mapping. A survivor here is accepted only with a
# written argument that it can't turn a failure into a pass, checked by the Layer 6 adversarial reviewer
# ("argument" and "reviewed" in its accepted.json entry). The `tested` hashing (agent_result.py) is not in
# the mutated modules; its behaviour is pinned by tests.
VERDICT_FUNCTIONS = frozenset({
    "checks._bgp_session", "checks._bgp_prefixes", "checks._route", "checks._ping", "checks._bgp_route",
    "checks._not_configured", "checks.is_post_convergence", "checks._evaluate", "checks._counts", "checks.run_check",
    "checks.hold_check", "checks.converge_then_hold", "checks.run_round_robin", "checks._reach_view",
    "checks.hold_together", "checks.never_ready_nodes", "checks.inconclusive_reason",
    "runner._bgp_convergence_gate", "runner._wait_fault_visible", "runner._link_sessions",
    "runner._sessions_over_links", "runner._reach_then_hold", "runner.run_scenario",
    "runner.RunReport.passed", "runner.RunReport.failed", "runner.RunReport.status",
    "runner.RunReport.inconclusive_reason", "runner.RunReport.exit_code",
    "runner.config_load_by_node", "runner._startup_load", "runner.rejected_config_message",
})


def acceptance_problem(entry, name: str, diffs: dict[str, str]) -> str | None:
    """Why an accepted.json entry doesn't accept this mutant today, or None if it does."""
    if not isinstance(entry, dict):
        return "no entry, or the old format with no diff fingerprint"
    if name not in diffs or entry.get("diff") != mutant_fingerprint(diffs[name]):
        return "its diff fingerprint doesn't match this mutant (code moved: re-review)"
    if entry.get("class") not in ACCEPT_CLASSES:
        return f"no class (one of {', '.join(ACCEPT_CLASSES)})"
    if mutant_function(name) in VERDICT_FUNCTIONS and not (entry.get("argument") and entry.get("reviewed")):
        return ("a verdict-deciding function: needs a written argument that it can't turn a failure into a pass, "
                "checked by the adversarial reviewer (argument, reviewed)")
    return None


def accepted_by_class(accepted: dict, names, diffs: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for n in names:
        if acceptance_problem(accepted.get(n), n, diffs) is None:
            out[accepted[n]["class"]] = out.get(accepted[n]["class"], 0) + 1
    return out


def accepted_now(accepted: dict, name: str, diffs: dict[str, str]) -> bool:
    """Accepted only if the entry pins the diff this mutant has today, names a class, and, in a verdict-deciding
    function, carries a reviewed argument."""
    return acceptance_problem(accepted.get(name), name, diffs) is None


def pin_accepted(args, accepted: dict, diffs: dict[str, str]) -> None:
    """--pin-accepted: add fingerprints to entries that have none (the old format), right after each one was
    audited against its current diff. An entry that already pins a different diff is never rewritten."""
    path = out_dir(args) / "accepted.json"
    data = load_accepted(args.version, out_dir(args))
    pinned = 0
    for n, entry in list(data.get("mutants", {}).items()):
        if isinstance(entry, str) and n in diffs:
            data["mutants"][n] = {"reason": entry, "diff": mutant_fingerprint(diffs[n])}
            pinned += 1
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    accepted.clear()
    accepted.update(data.get("mutants", {}))
    print(f"pinned {pinned} accepted mutants to their current diffs in {path}", flush=True)


def mutant_diffs(names: list[str], mutmut: list, jobs: int) -> dict[str, str]:
    def show(n: str) -> tuple[str, str]:
        return n, run([*mutmut, "show", n], timeout=120).out.strip()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        return dict(pool.map(show, names))


def mutant_function(name: str) -> str:
    """netdryrun.checks.x_run_check__mutmut_3 -> checks.run_check; xǁClassǁmethod -> Class.method"""
    base = name.rsplit("__mutmut_", 1)[0]
    module, _, func = base.rpartition(".")
    func = func.removeprefix("x_").removeprefix("xǁ").replace("ǁ", ".")
    return f"{module.removeprefix('netdryrun.')}.{func}"


def mutant_section(survivors: dict[str, list[str]], status: dict, accepted: dict, diffs: dict[str, str], args) -> str:
    """Survivors grouped by function, each with its diff (written to mutants.md beside GATE.md)."""
    names = [n for ns in survivors.values() for n in ns]
    if not names:
        return "**Surviving mutants:** none."
    by_func: dict[str, list[str]] = {}
    for n in names:
        by_func.setdefault(mutant_function(n), []).append(n)
    lines = [f"# Surviving mutants, Netdryrun {args.version}", "",
             "Each mutant below is a deliberate change to the code that no test noticed. In verdict logic each is a "
             "BLOCKER until a test kills it or it is accepted as harmless in accepted.json with a reason.", ""]
    for func, ns in sorted(by_func.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines += [f"## `{func}` ({len(ns)})", ""]
        for n in ns:
            note = (f" (accepted, {accepted[n]['class']}: {reason(accepted[n])})" if accepted_now(accepted, n, diffs) else
                    f" (NOT accepted: {acceptance_problem(accepted[n], n, diffs)}; {reason(accepted[n])})" if n in accepted else "")
            if n in accepted and isinstance(accepted[n], dict) and accepted[n].get("argument"):
                note += f"; argument: {accepted[n]['argument']}; reviewed: {accepted[n].get('reviewed', 'no')}"
            fp = mutant_fingerprint(diffs.get(n, ""))
            lines += [f"`{n}`: {status[n]}{note}; diff fingerprint `{fp}`", "", "```diff",
                      diffs.get(n) or "(no diff)", "```", ""]
    write_out(args, "mutants.md", "\n".join(lines))
    table = "\n".join(f"| `{f}` | {len(ns)} |" for f, ns in sorted(by_func.items(), key=lambda kv: (-len(kv[1]), kv[0])))
    return (f"**Surviving mutants by function** ({len(names)} in all; every diff is in [mutants.md](mutants.md)):\n\n"
            f"| Function | Survivors |\n|---|---|\n{table}")


# --------------------------------------------------------------------------------------------
# Layer 5: live matrix on the built package (the lab machine)
# --------------------------------------------------------------------------------------------

OUR_LAB_PREFIX = "clab-ndr-"   # every topology in examples/ and corpus/ is named ndr-* (a static check enforces it)


def clab_containers() -> set[str] | None:
    p = run(["docker", "ps", "-a", "--filter", "name=clab-", "--format", "{{.Names}}"], timeout=60)
    return set(p.out.split()) if p.code == 0 else None


class Live:
    """Shared state for the live layer: the installed wheel, a scratch folder, the lab snapshot."""

    def __init__(self, layer: Layer, work: Path):
        self.layer, self.work = layer, work
        self.venv = work / "venv"
        self.ndr = venv_bin(self.venv, "netdryrun")
        self.python = venv_bin(self.venv, "python")
        self.before: set[str] = set()

    def copy_example(self, name: str, tag: str = "") -> Path:
        dst = self.work / "examples" / f"{name}{tag}"
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(ROOT / "examples" / name, dst)
        return dst

    def leftovers(self) -> list[str]:
        now_ = clab_containers()
        return sorted((now_ or set()) - self.before)

    def assert_clean(self, id: str, title: str) -> bool:
        """No lab container left behind. Removes only our own leftovers (every lab we ship is named ndr-*),
        so a lab someone else started on the machine is reported but never touched."""
        left = self.leftovers()
        self.layer.add(f"{id}-clean", f"{title}: no lab left running", BLOCKER, not left,
                       f"left running: {', '.join(left)}" if left else "none left")
        for c in left:
            if c.startswith(OUR_LAB_PREFIX):
                run(["docker", "rm", "-f", c], timeout=120)
        return not left

    def netdryrun_run(self, folder: Path, timeout: float = 1800) -> Proc:
        report = self.work / "reports" / f"{folder.name}.json"
        report.parent.mkdir(exist_ok=True)
        env = {**os.environ, "CI": "1"}   # no interactive feedback prompt
        return run([self.ndr, "run", folder, "--json", report, "--no-step-summary"], cwd=self.work, env=env,
                   timeout=timeout)


def layer_live(args) -> Layer:
    layer = Layer("live", args)
    for tool, cmd in (("containerlab", ["containerlab", "version"]),
                      ("docker", ["docker", "version", "--format", "{{.Server.Version}}"])):
        if not layer.tool(tool, cmd):
            layer.add("lab-machine", "the lab machine is ready (containerlab and Docker)", BLOCKER, None,
                      f"{tool} is not available: run the live layer on the lab machine")
            return layer
    layer.tools["containerlab"] = re.sub(r"\s+", " ", layer.tools["containerlab"])
    before = clab_containers() or set()
    if before and not args.allow_running_labs:
        layer.add("lab-machine", "the lab machine has no lab running", BLOCKER, False,
                  f"already running: {', '.join(sorted(before))} (stop them, or pass --allow-running-labs)")
        return layer
    work = Path(tempfile.mkdtemp(prefix="ndr-gate-live-"))
    live = Live(layer, work)
    live.before = before
    try:
        if not live_install(live, args):
            return layer
        live_examples(live, args)
        live_corpora(live, args)
        cmd = [live.python, ROOT / "scripts" / "mcp_handshake.py", live.ndr, "mcp"]
        layer.add_proc("mcp-handshake", "MCP handshake against the installed wheel", BLOCKER, cmd, run(cmd, timeout=300))
        if args.pack:
            cmd = ["bash", args.pack]
            layer.add_proc("pack", f"check pack verification ({args.pack})", MAJOR, cmd,
                           run(cmd, env={**os.environ, "NDR": str(live.ndr)}, timeout=7200))
        else:
            layer.add("pack", "check pack verification", MAJOR, None, "no --pack script given")
        layer.add("scale", "20-node scale test", MAJOR, None, "not scripted in the repository yet: run it by hand")
        live_chaos(live, args)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return layer


def live_install(live: Live, args) -> bool:
    """Build the wheel and install it in a fresh venv: everything else runs that, not the source tree."""
    layer, uv = live.layer, shutil.which("uv")
    dist = live.work / "dist"
    cmd = [uv, "build", "--wheel", "--out-dir", dist] if uv else [sys.executable, "-m", "build", "--wheel", "--outdir", dist]
    p = run(cmd, timeout=900)
    wheels = sorted(dist.glob("netdryrun-*.whl"))
    layer.add_proc("build", "build the wheel", BLOCKER, cmd, p, wheels[0].name if wheels else "")
    if not wheels:
        return False
    p = make_venv(COVERAGE_PYTHON, uv, live.venv)
    if p.code == 0:
        p = pip_install(uv, live.venv, str(wheels[0]))
    layer.add_proc("install", f"install {wheels[0].name} in a fresh venv", BLOCKER, ["pip", "install", wheels[0].name], p)
    if p.code != 0:
        return False
    where = run([live.python, "-c", "import netdryrun; print(netdryrun.__file__)"], cwd=live.work)
    inside = where.code == 0 and str(live.venv) in where.out and str(ROOT) not in where.out
    layer.add("installed-not-source", "runs the installed package, not the source tree", BLOCKER, inside,
              where.out.strip()[-200:])
    v = run([live.ndr, "--version"], cwd=live.work)
    layer.add("installed-version", f"netdryrun --version says {args.version}", BLOCKER,
              v.out.strip() == f"netdryrun {args.version}", v.out.strip()[:200])
    return inside


def images_available(folder: Path) -> list[str]:
    """Images the topology needs that are neither local nor pullable."""
    import yaml
    topo = yaml.safe_load((folder / "topology.clab.yml").read_text(encoding="utf-8"))["topology"]
    images = {n.get("image") for n in (topo.get("nodes") or {}).values() if n and n.get("image")}
    images |= {k.get("image") for k in (topo.get("kinds") or {}).values() if k and k.get("image")}
    if (topo.get("defaults") or {}).get("image"):
        images.add(topo["defaults"]["image"])
    missing = []
    for image in sorted(i for i in images if i):
        if run(["docker", "image", "inspect", image], timeout=60).code != 0 and \
                run(["docker", "pull", image], timeout=1800).code != 0:
            missing.append(image)
    return missing


# An example whose documented expectations include variants: each file in the subfolder replaces
# the file of the same name in configs/, and the run must give the second documented outcome.
VARIANTS = {"srl-hidden-leak": "leaks"}


def live_examples(live: Live, args) -> None:
    layer = live.layer
    docs = documented_examples()
    times = []
    for name in example_dirs():
        if args.examples and name not in args.examples:
            continue
        row = docs.get(name)
        if not row or not row["codes"]:
            layer.add(f"example-{name}", f"example {name}", BLOCKER, False, "no documented expected result")
            continue
        folder = live.copy_example(name)
        missing = images_available(folder)
        if missing:
            layer.add(f"example-{name}", f"example {name}", BLOCKER, None, f"image not available: {', '.join(missing)}")
            continue
        runs = [(folder, row["outcomes"][0], row["codes"][0], "")]
        if name in VARIANTS and len(row["codes"]) > 1:
            for variant in sorted((ROOT / "examples" / name / VARIANTS[name]).iterdir()):
                f = live.copy_example(name, f"-{variant.stem}")
                shutil.copy(variant, f / "configs" / variant.name)
                runs.append((f, row["outcomes"][1], row["codes"][1], f" with {VARIANTS[name]}/{variant.name}"))
        for folder_, outcome, code, label in runs:
            if outcome.startswith("Demo OK"):
                cmd = ["bash", ROOT / "examples" / name / "demo.sh"]
                p = run(cmd, cwd=live.work, env={**os.environ, "NDR": str(live.ndr), "OUT": str(live.work / "demo")},
                        timeout=1800)
            else:
                p = live.netdryrun_run(folder_)
            ok = p.code == code and outcome in p.out and "Traceback" not in p.out
            got = next((ln for ln in reversed(p.out.splitlines()) if re.match(r"^(PASSED|FAILED|ERROR|INCONCLUSIVE|Demo)", ln)), "")
            layer.add(f"example-{name}{folder_.name.removeprefix(name)}", f"example {name}{label}: `{outcome}`, exit {code}",
                      BLOCKER, ok, f"exit {p.code}: {got[:160]}", tail(p.out), p.seconds)
            if not label:
                times.append((name, p.seconds, row["seconds"]))
            live.assert_clean(f"example-{name}{folder_.name.removeprefix(name)}", f"example {name}{label}")
    # Documented times: flag any that is off by more than 2x either way
    off = [f"{n}: {s:.0f} s, documented {'-'.join(map(str, d))} s" for n, s, d in times
           if d and (s > 2 * max(d) or s < 0.5 * min(d))]
    layer.add("example-times", "example times match the docs (within 2x)", MAJOR, not off,
              "; ".join(off) or "all within 2x",
              "\n".join(f"{n}: {s:.0f} s (documented {'-'.join(map(str, d))} s)" for n, s, d in times))


def harmful_approved(cases: list[dict], skip=()) -> list[str]:
    """The case IDs where a harmful change ("expected": "unsafe") got Netdryrun's approval: the false passes, counted
    on their own. Cases in `skip` (nondeterministic) are left out."""
    return sorted(c["id"] for c in cases if c["id"] not in skip
                  and c.get("expected") == "unsafe" and c.get("strategies", {}).get("netdryrun", {}).get("verdict") == "safe")


# The cases each corpus may exempt from the verdict diff: adding one to NONDETERMINISTIC.yml takes a change here too.
NONDETERMINISTIC_PINNED = {"v1": [], "v2": ["18-aggregate-discard-route-removed"]}


def nondeterministic_problems(version: str, nd: dict, new: dict) -> list[str]:
    """Why the nondeterministic exemption doesn't hold this run: a list that differs from the pinned one, a case
    that didn't run its repeats, or any run that ended in error (an error is never part of the race)."""
    out = []
    if sorted(nd) != sorted(NONDETERMINISTIC_PINNED.get(version, [])):
        out.append(f"NONDETERMINISTIC.yml lists {sorted(nd)}, the gate pins {NONDETERMINISTIC_PINNED.get(version, [])}")
    for cid in sorted(nd):
        runs = new.get(cid, {}).get("runs") or []
        if len(runs) < 2:
            out.append(f"{cid}: {len(runs)} runs recorded, not the repeats")
        bad = [f"run {i + 1} {s}" for i, r in enumerate(runs) for s, v in r.items() if v not in ("safe", "unsafe")]
        if bad:
            out.append(f"{cid}: error in {', '.join(bad)}")
    return out


def nd_always_approved(published: dict, rerun: dict) -> bool:
    """A harmful nondeterministic case that Netdryrun approved in every run of this release."""
    runs = rerun.get("runs") or []
    expected = rerun.get("expected") or published.get("expected")   # a case new in this release has no published row
    return expected == "unsafe" and bool(runs) and all(r.get("netdryrun") == "safe" for r in runs)


def nondeterministic_cases(corpus: Path) -> dict:
    """corpus/[v2/]NONDETERMINISTIC.yml: cases whose verdict follows a race in the lab, recorded and never a blocker."""
    import yaml   # the gate's Python has Netdryrun's dependencies (Layer 5 installs the package)
    path = corpus / "NONDETERMINISTIC.yml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def harmful_approved_check(published: list[dict], rerun: list[dict], skip=()) -> tuple[bool, str]:
    """A harmful case approved that isn't among the published known misses is a BLOCKER, whatever the score."""
    known, now = set(harmful_approved(published, skip)), harmful_approved(rerun, skip)
    new = [c for c in now if c not in known]
    summary = f"harmful changes approved: {len(now)} ({', '.join(now) or 'none'}); published known misses: "               f"{', '.join(sorted(known)) or 'none'}"
    if new:
        summary += f"; new, not published: {', '.join(new)}"
    return not new, summary


def live_corpora(live: Live, args) -> None:
    """Rerun both Verdict Corpus versions from a scratch copy; every verdict must match results.json."""
    layer = live.layer
    if args.skip_corpus:
        layer.add("corpus", "Verdict Corpus reruns", BLOCKER, None, "skipped with --skip-corpus")
        return
    copy = live.work / "corpus"
    shutil.copytree(ROOT / "corpus", copy)   # run.py writes its results beside itself: never into the repo
    for version, sub in (("v1", ""), ("v2", "v2")):
        cmd = [live.python, copy / "run.py", "--corpus", version, "--workdir", live.work / f"corpus-{version}"]
        p = run(cmd, cwd=live.work, timeout=4 * 3600)
        committed = ROOT / "corpus" / sub / "results" / "results.json"
        fresh = copy / sub / "results" / "results.json"
        diffs = []
        nd = nondeterministic_cases(ROOT / "corpus" / sub)
        if fresh.exists():   # kept beside GATE.md: the corpus results of this exact release, for the docs
            write_out(args, f"corpus-{version}-results.json", fresh.read_text(encoding="utf-8"))
        if p.code == 0:
            old = {c["id"]: c for c in json.loads(committed.read_text(encoding="utf-8"))["cases"]}
            new = {c["id"]: c for c in json.loads(fresh.read_text(encoding="utf-8"))["cases"]}
            for cid in sorted((set(old) | set(new)) - set(nd)):
                for s in ("ping", "sessions", "netdryrun"):
                    a = old.get(cid, {}).get("strategies", {}).get(s, {}).get("verdict")
                    b = new.get(cid, {}).get("strategies", {}).get(s, {}).get("verdict")
                    if a != b:
                        diffs.append(f"{cid} {s}: committed {a}, now {b}")
        layer.add(f"corpus-{version}", f"Verdict Corpus {version}: every verdict matches the committed results.json",
                  BLOCKER, p.code == 0 and not diffs,
                  f"exit {p.code}" if p.code else (f"{len(diffs)} verdict(s) differ" if diffs else "all verdicts match"),
                  "\n".join(diffs) or tail(p.out), p.seconds, cmdline(["python", "corpus/run.py", "--corpus", version]))
        if p.code == 0 and (nd or NONDETERMINISTIC_PINNED.get(version)):
            # the verdicts are recorded, never a blocker: they follow the lab, not the change. The exemption
            # itself is held: the pinned list, the repeats ran, and no run ended in error
            problems = nondeterministic_problems(version, nd, new)
            layer.add(f"corpus-{version}-nondeterministic-held",
                      f"Verdict Corpus {version}: the nondeterministic exemption holds (pinned list, repeats ran, no error)",
                      BLOCKER, not problems, "; ".join(problems) or ", ".join(sorted(nd)))
            seen = "; ".join(f"{cid}: " + ", ".join(str(r.get("netdryrun")) for r in new.get(cid, {}).get("runs", []))
                             for cid in nd)
            # every run approving a harmful case is shown as a failed INFO line: not a blocker (it happens by chance),
            # but in plain sight
            approved = [cid for cid in nd if nd_always_approved(old.get(cid, {}), new.get(cid, {}))]
            layer.add(f"corpus-{version}-nondeterministic",
                      f"Verdict Corpus {version}: nondeterministic cases recorded (known, not scored, never a blocker)",
                      INFO, not approved, f"Netdryrun verdicts per run: {seen}"
                      + (f"; every run approved the harmful change: {', '.join(approved)}" if approved else ""))
        if p.code == 0 and fresh.exists():
            ok, summary = harmful_approved_check(list(old.values()), list(new.values()), nd)
            layer.add(f"corpus-{version}-harmful-approved",
                      f"Verdict Corpus {version}: no harmful change approved beyond the published known misses",
                      BLOCKER, ok, summary)
        live.assert_clean(f"corpus-{version}", f"Verdict Corpus {version}")


def live_chaos(live: Live, args) -> None:
    """Interrupt and break runs on purpose. Each case must end with the documented exit code, a
    clear message (no traceback) and no lab left running."""
    for sig in ("SIGINT", "SIGTERM"):
        for phase, marker in (("deploy", r"Deploying lab"), ("checks", r"\[(PASS|FAIL)\]|Convergence checks done")):
            chaos_signal(live, sig, phase, marker)
    chaos_broken(live, "missing-image", "a node's image does not exist",
                 lambda topo: topo["topology"]["nodes"]["r3"].__setitem__("image", "netdryrun-gate.invalid/missing:never"))
    chaos_broken(live, "deploy-fails", "a node cannot be created (a bind source does not exist)",
                 lambda topo: topo["topology"]["nodes"]["r3"]["binds"].append("/nonexistent/netdryrun-gate:/gate"))
    chaos_concurrent(live)
    if args.chaos_docker_restart:
        chaos_docker_restart(live)
    else:
        live.layer.add("chaos-docker-restart", "Docker restarts mid-run", MAJOR, None,
                       "off by default (restarts every container on the machine): pass --chaos-docker-restart")


def chaos_signal(live: Live, sig: str, phase: str, marker: str) -> None:
    """Send `sig` once `marker` appears. SIGINT goes to the process group, as Ctrl+C does; SIGTERM
    to netdryrun alone, as `kill` or a CI runner does."""
    layer, id_ = live.layer, f"chaos-{sig.lower()}-{phase}"
    title = f"{sig} during {phase}: exit {SIGNAL_EXIT[sig]}, a clear message"
    folder = live.copy_example("frr-bgp", f"-{id_}")
    t0 = time.monotonic()
    proc = subprocess.Popen([str(live.ndr), "run", str(folder), "--no-step-summary"], cwd=live.work,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
                            env={**os.environ, "CI": "1"})
    lines: list[str] = []
    seen = threading.Event()

    def reader() -> None:
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace")
            lines.append(line)
            if re.search(marker, line):
                seen.set()
    threading.Thread(target=reader, daemon=True).start()
    if not seen.wait(600):
        proc.kill()
        proc.wait()
        layer.add(id_, title, BLOCKER, False, f"never reached {phase}", tail("".join(lines)), time.monotonic() - t0)
        live.assert_clean(id_, f"{sig} during {phase}")
        return
    time.sleep(3 if phase == "deploy" else 1)     # inside the phase, not on its first line
    signum = getattr(signal, sig)
    if sig == "SIGINT":
        os.killpg(proc.pid, signum)
    else:
        proc.send_signal(signum)
    try:
        code = proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = proc.wait()
        lines.append(f"\n[did not exit within 300 s of {sig}; killed]")
    time.sleep(0.5)  # let the reader drain
    out = "".join(lines)
    code = 128 - code if code < 0 else code   # Popen reports death by signal N as -N
    ok = code == SIGNAL_EXIT[sig] and "Traceback" not in out and (sig != "SIGINT" or "Interrupted" in out)
    layer.add(id_, title, BLOCKER, ok, f"exit {code}" + ("; traceback printed" if "Traceback" in out else ""),
              tail(out), time.monotonic() - t0)
    live.assert_clean(id_, f"{sig} during {phase}")


def chaos_broken(live: Live, id_: str, what: str, mutate) -> None:
    """A topology that cannot deploy must give exit 2 with a message, and nothing left running."""
    import yaml
    folder = live.copy_example("frr-bgp", f"-{id_}")
    topo_file = folder / "topology.clab.yml"
    topo = yaml.safe_load(topo_file.read_text(encoding="utf-8"))
    mutate(topo)
    topo_file.write_text(yaml.safe_dump(topo, sort_keys=False), encoding="utf-8")
    p = live.netdryrun_run(folder, timeout=900)
    last = (p.out.strip().splitlines() or [""])[-1]
    ok = p.code == 2 and "Traceback" not in p.out and "ERROR" in p.out
    live.layer.add(f"chaos-{id_}", f"{what}: exit 2 with a clear error", BLOCKER, ok, f"exit {p.code}: {last[:160]}",
                   tail(p.out), p.seconds)
    live.assert_clean(f"chaos-{id_}", what)


def chaos_concurrent(live: Live) -> None:
    """Two runs of the same lab at once. One must pass as documented; the other must pass too or
    refuse with exit 2. A failed (1) or inconclusive (3) verdict means the runs interfered."""
    a, b = live.copy_example("frr-bgp", "-twin-a"), live.copy_example("frr-bgp", "-twin-b")
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        pa, pb = pool.map(lambda f: live.netdryrun_run(f, timeout=1800), (a, b))
    codes = sorted((pa.code, pb.code))
    ok = codes in ([0, 0], [0, 2]) and "Traceback" not in pa.out + pb.out
    live.layer.add("chaos-concurrent", "two runs of the same lab at once: no false verdict, no crash", BLOCKER, ok,
                   f"exit codes {pa.code} and {pb.code}",
                   f"--- run A (exit {pa.code})\n{tail(pa.out, 30)}\n--- run B (exit {pb.code})\n{tail(pb.out, 30)}",
                   max(pa.seconds, pb.seconds))
    live.assert_clean("chaos-concurrent", "two runs at once")


def chaos_docker_restart(live: Live) -> None:
    folder = live.copy_example("frr-bgp", "-docker-restart")
    result: dict[str, Proc] = {}
    t = threading.Thread(target=lambda: result.setdefault("p", live.netdryrun_run(folder, timeout=1800)))
    t.start()
    time.sleep(45)   # mid-deploy or early checks
    run(["sudo", "-n", "systemctl", "restart", "docker"], timeout=300)
    t.join()
    p = result["p"]
    ok = p.code in (1, 2, 3) and "Traceback" not in p.out   # anything but a pass, and no crash
    live.layer.add("chaos-docker-restart", "Docker restarts mid-run: never passed, a clear message", BLOCKER, ok,
                   f"exit {p.code}", tail(p.out), p.seconds)
    live.assert_clean("chaos-docker-restart", "Docker restart")


# --------------------------------------------------------------------------------------------
# Layer 7: after-publish proof
# --------------------------------------------------------------------------------------------

def layer_after_publish(args) -> Layer:
    layer = Layer("after-publish", args)
    v = args.version
    status = http_status(f"https://pypi.org/pypi/netdryrun/{v}/json")
    layer.add("pypi", f"PyPI serves netdryrun {v}", BLOCKER, status == 200 if status else None, f"HTTP {status}")
    uv = shutil.which("uv")
    if uv:
        layer.tool("uv", ["uv", "--version"])
    work = Path(tempfile.mkdtemp(prefix="ndr-gate-publish-"))
    handshake = ROOT / "scripts" / "mcp_handshake.py"
    try:
        for py in args.pythons:
            venv = work / f"py{py}"
            t0 = time.monotonic()
            p = make_venv(py, uv, venv)
            if p.code == 0:   # pip itself, from PyPI, no cache: what a user's `pip install` does
                p = run([venv_bin(venv, "python"), "-m", "pip", "install", "-q", "--no-cache-dir",
                         "--disable-pip-version-check", f"netdryrun=={v}"], cwd=work, timeout=900)
            if p.code == 0:
                p = run([venv_bin(venv, "netdryrun"), "--version"], cwd=work)
                if p.out.strip() != f"netdryrun {v}":
                    p = Proc(1, f"--version printed {p.out.strip()!r}", p.seconds)
            if p.code == 0:
                p = run([venv_bin(venv, "netdryrun"), "validate", ROOT / "examples" / "frr-bgp"], cwd=work)
            if p.code == 0:
                p = run([venv_bin(venv, "python"), handshake, venv_bin(venv, "netdryrun"), "mcp"], cwd=work, timeout=300)
            layer.add(f"pip-{py}", f"pip install netdryrun=={v} on Python {py}: --version, validate, MCP handshake",
                      BLOCKER, p.code == 0, (p.out.strip().splitlines() or [""])[-1][:160], tail(p.out),
                      time.monotonic() - t0)
            if uv:
                t0 = time.monotonic()
                uvx = [uv, "tool", "run", "--refresh", "--python", py, f"netdryrun@{v}"]
                p = run([*uvx, "--version"], cwd=work, timeout=900)
                if p.code == 0 and (p.out.strip().splitlines() or [""])[-1] != f"netdryrun {v}":
                    p = Proc(1, p.out, p.seconds)
                if p.code == 0:
                    p = run([sys.executable, handshake, *uvx, "mcp"], cwd=work, timeout=300)
                layer.add(f"uvx-{py}", f"uvx netdryrun@{v} on Python {py}: --version, MCP handshake", BLOCKER,
                          p.code == 0, (p.out.strip().splitlines() or [""])[-1][:160], tail(p.out), time.monotonic() - t0)
            else:
                layer.add(f"uvx-{py}", f"uvx netdryrun@{v} on Python {py}", BLOCKER, None, "uv is not installed")
        after_publish_live(layer, work, args)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    release_consistency(layer, v)
    if shutil.which("gh"):
        p = run(["gh", "run", "list", "--workflow", "published-action.yml", "--limit", "1",
                 "--json", "conclusion,headSha,url"], timeout=120)
        try:
            last = json.loads(p.out)[0]
            layer.add("published-action", "the Action by its tag passes a good change and rejects a bad one "
                      "(latest published-action.yml run)", MAJOR, last["conclusion"] == "success",
                      f"{last['conclusion'] or 'running'} at {last['headSha'][:7]}: {last['url']}")
        except (ValueError, IndexError, KeyError):
            layer.add("published-action", "latest published-action.yml run", MAJOR, None, p.out.strip()[-160:])
    else:
        layer.add("published-action", "latest published-action.yml run", MAJOR, None, "gh is not installed")
    return layer


def after_publish_live(layer: Layer, work: Path, args) -> None:
    """One live example with the package from PyPI: frr-bgp must give its documented result."""
    if not shutil.which("containerlab"):
        layer.add("live-example", "one live example from the PyPI package", BLOCKER, None, "containerlab is not installed")
        return
    venv = work / f"py{COVERAGE_PYTHON}"
    if not venv_bin(venv, "netdryrun").exists():
        layer.add("live-example", "one live example from the PyPI package", BLOCKER, False, "the pip install failed")
        return
    row = documented_examples()["frr-bgp"]
    before = clab_containers() or set()
    shutil.copytree(ROOT / "examples" / "frr-bgp", work / "frr-bgp")
    p = run([venv_bin(venv, "netdryrun"), "run", work / "frr-bgp", "--no-step-summary"], cwd=work,
            env={**os.environ, "CI": "1"}, timeout=1800)
    left = sorted((clab_containers() or set()) - before)
    ok = p.code == row["codes"][0] and row["outcomes"][0] in p.out and not left
    layer.add("live-example", f"frr-bgp from PyPI: `{row['outcomes'][0]}`, exit {row['codes'][0]}, no lab left",
              BLOCKER, ok, f"exit {p.code}" + (f"; left running: {', '.join(left)}" if left else ""), tail(p.out), p.seconds)


# --------------------------------------------------------------------------------------------
# Release consistency: every public place names the released version (after-publish, and nightly on main)
# --------------------------------------------------------------------------------------------

SITE_PAGES = ("https://netdryrun.com/", "https://netdryrun.com/llms.txt")
PUBLISHED_ACTION = ".github/workflows/published-action.yml"
ACTION_REF = re.compile(r"(?i:netdryrun/netdryrun)@v(\d+\.\d+\.\d+)")   # either case: GitHub repo names are case-insensitive
README_STATUS = re.compile(r"^> Status: \*\*v(\d+\.\d+\.\d+)\.\*\*", re.M)
RELEASE_PIN = re.compile(r'^\s*RELEASE:\s*"?(\d+\.\d+\.\d+)"?\s*$', re.M)
# What the site says about the current version: its structured data, the Action ref, and "version X.Y.Z" (the
# phrase sync_facts writes). Past releases named as history ("ran on Netdryrun 0.3.1") match none of these.
SITE_VERSION = re.compile(r'"softwareVersion":\s*"(\d+\.\d+\.\d+)"|(?i:netdryrun/netdryrun)@v(\d+\.\d+\.\d+)'
                          r"|(?i:\bversion) (\d+\.\d+\.\d+)")


def fetch(url: str) -> tuple[int | None, str]:
    """One GET, 30 s, no retry: (HTTP status, body), or (None, why) when unreachable."""
    req = urllib.request.Request(url, headers={"User-Agent": "netdryrun-release-gate"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(5_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, str(e)


def main_texts() -> dict[str, str] | None:
    """README.md, published-action.yml and every file naming the Action, as origin/main has them after one fetch."""
    if run(["git", "-C", ROOT, "fetch", "--quiet", "origin", "main"], timeout=120).code != 0:
        return None
    p = run(["git", "-C", ROOT, "grep", "-l", "-i", "-F", "netdryrun/netdryrun@v", "origin/main"], timeout=60)
    if p.code not in (0, 1):   # 1: no match
        return None
    paths = {ln.split(":", 1)[1] for ln in p.out.splitlines() if ln.startswith("origin/main:")}
    texts = {}
    for path in sorted(paths | {"README.md", PUBLISHED_ACTION}):
        q = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/main:{path}"], capture_output=True, timeout=60)
        if q.returncode == 0:
            texts[path] = q.stdout.decode("utf-8", "replace")
    return texts


def line_of(text: str, m: re.Match) -> int:
    return text.count("\n", 0, m.start()) + 1


def main_version_problems(version: str, texts: dict[str, str]) -> tuple[list[str], list[str]]:
    """(what main says, each place that says another version): the README status line, published-action.yml's
    RELEASE, and every Action ref outside the recorded history."""
    found, problems = [], []
    readme = texts.get("README.md", "")
    m = README_STATUS.search(readme)
    if m:
        found.append((f"README.md:{line_of(readme, m)} status line v{m.group(1)}", m.group(1)))
    else:
        problems.append("README.md: no status line (> Status: **vX.Y.Z.**)")
    action = texts.get(PUBLISHED_ACTION, "")
    m = RELEASE_PIN.search(action)
    if m:
        found.append((f"{PUBLISHED_ACTION}:{line_of(action, m)} RELEASE {m.group(1)}", m.group(1)))
    else:
        problems.append(f"{PUBLISHED_ACTION}: no RELEASE pin")
    for path, text in sorted(texts.items()):
        # tests/ holds old refs on purpose (this check's own fixtures); users never read them
        if not path.startswith(RETIRED_HISTORY_PATHS + ("tests/",)):
            found += [(f"{path}:{line_of(text, m)} {m.group(0)}", m.group(1)) for m in ACTION_REF.finditer(text)]
    problems += [where for where, v in found if v != version]
    return [where for where, _ in found], problems


def site_version_problems(version: str, url: str, body: str) -> tuple[list[str], list[str]]:
    found = [(f"{url} {m.group(0)}", next(g for g in m.groups() if g)) for m in SITE_VERSION.finditer(body)]
    problems = [where for where, v in found if v != version] or ([] if found else [f"{url}: names no version"])
    return [where for where, _ in found], problems


# What `gh release create --generate-notes` (release.yml) writes on its own: anything else means notes were pasted.
GENERATED_NOTES = re.compile(r"## What's Changed|## New Contributors|\*\*Full Changelog\*\*: \S+"
                             r"|\* .* in https://github\.com/\S+/pull/\d+")


def release_notes_pasted(body) -> bool:
    return any(ln.strip() and not GENERATED_NOTES.fullmatch(ln.strip()) for ln in str(body or "").splitlines())


def registry_latest(data, name: str) -> tuple[str | None, list[str]]:
    """(the version the MCP Registry marks latest, every version it lists) for one server."""
    latest, listed = None, []
    for item in data.get("servers", []) if isinstance(data, dict) else []:
        server = item.get("server", item)
        if server.get("name") != name or "version" not in server:
            continue
        listed.append(server["version"])
        meta = item.get("_meta") or server.get("_meta") or {}
        if meta.get("io.modelcontextprotocol.registry/official", {}).get("isLatest"):
            latest = server["version"]
    return latest, sorted(listed)


def release_consistency(layer: Layer, version: str, get=fetch, main=main_texts) -> None:
    """Every public place names `version`: PyPI's latest, the GitHub latest release, main (README status line,
    Action refs, published-action.yml RELEASE), the website, the MCP Registry's latest. One request per source,
    no retry; a source that can't be read is SKIP, never PASS."""
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    name = server["name"]
    repo = server["repository"]["url"].removeprefix("https://github.com/")

    def report(id_: str, title: str, ok: bool | None, summary: str, found=(), problems=()) -> None:
        if problems:
            summary = "; ".join(problems)[:300]
        output = "\n".join([*(f"WRONG {p}" for p in problems), *(f"ok    {f}" for f in found if f not in problems)])
        layer.add(id_, title, BLOCKER, ok, summary, output)

    def get_json(url: str):
        status, body = get(url) or (None, "")
        if status is None:
            return None, f"unreachable: {body}".strip()
        try:
            return status, json.loads(body)
        except ValueError:
            return status, None

    title = f"PyPI's latest netdryrun is {version}"
    status, data = get_json("https://pypi.org/pypi/netdryrun/json")
    if status is None:
        report("latest-pypi", title, None, data)
    else:
        got = data.get("info", {}).get("version") if isinstance(data, dict) else None
        report("latest-pypi", title, got == version, f"PyPI latest: {got or f'unreadable (HTTP {status})'}")

    title = f"the GitHub latest release is v{version} (notes pasted, marked latest)"
    status, data = get_json(f"https://api.github.com/repos/{repo}/releases/latest")
    if status is None:
        report("latest-github", title, None, data)
    elif status == 404:
        report("latest-github", title, False, "no release is marked latest")
    else:
        got = data.get("tag_name") if isinstance(data, dict) else None
        pasted = got and release_notes_pasted(data.get("body"))
        report("latest-github", title, bool(got == f"v{version}" and pasted),
               f"latest release: {got or f'unreadable (HTTP {status})'}"
               + ("" if pasted or not got else "; its notes are only what GitHub generates (paste the release notes)"))

    title = f"main names {version}: README status line, every netdryrun/Netdryrun@v ref, published-action.yml RELEASE"
    texts = main()
    if texts is None:
        report("main-version", title, None, "could not fetch and read origin/main")
    else:
        found, problems = main_version_problems(version, texts)
        report("main-version", title, not problems, f"{len(found)} places say {version}", found, problems)

    title = f"netdryrun.com names {version} (home page, llms.txt)"
    found, problems, unreachable = [], [], []
    for url in SITE_PAGES:
        status, body = get(url) or (None, "")
        if status != 200:
            (unreachable if status is None else problems).append(f"{url}: " + (body or f"HTTP {status}"))
            continue
        f, p = site_version_problems(version, url, body)
        found, problems = found + f, problems + p
    if unreachable and not problems:
        report("site-version", title, None, "; ".join(unreachable))
    else:
        report("site-version", title, not problems, f"{len(found)} mentions say {version}", found, problems)

    title = f"the MCP Registry's latest {name} is {version}"
    status, data = get_json(f"https://registry.modelcontextprotocol.io/v0/servers?search={name}")
    if status is None:
        report("mcp-registry", title, None, data)
    else:
        latest, listed = registry_latest(data, name)
        report("mcp-registry", title, latest == version,
               f"latest: {latest or 'none'}; listed: {', '.join(listed) or 'none'}")


def layer_consistency(args) -> Layer:
    """The nightly's check on main between releases: the same release_consistency as after-publish."""
    layer = Layer("consistency", args)
    release_consistency(layer, args.version)
    return layer


# --------------------------------------------------------------------------------------------
# Reports: releases/<version>/gate/<layer>.json -> releases/<version>/GATE.md
# --------------------------------------------------------------------------------------------

def out_dir(args) -> Path:
    return Path(args.out) if args.out else ROOT / "releases" / args.version


def write_out(args, name: str, text: str) -> Path:
    path = out_dir(args) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def load_accepted(version: str, folder: Path | None = None) -> dict:
    """releases/<version>/accepted.json: {"checks": {"layer/id": reason},
    "mutants": {name: {"reason": ..., "diff": fingerprint}}} (a mutant entry without a matching fingerprint is stale).
    Accepting is for MAJOR checks and for mutants shown harmless; a BLOCKER check can't be accepted."""
    path = (folder or ROOT / "releases" / version) / "accepted.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def ready_to_publish(blockers, skipped, majors, missing, notes) -> bool:
    """Everything is in except the proof that can only run after publishing."""
    return not (blockers or skipped or majors or notes) and missing == ["after-publish"]


def render(args) -> tuple[str, bool]:
    """GATE.md from every recorded layer, and whether the release is cleared."""
    folder = out_dir(args)
    records = {}
    for name in LAYERS:
        path = folder / "gate" / f"{name}.json"
        if path.exists():
            records[name] = json.loads(path.read_text(encoding="utf-8"))
    accepted = load_accepted(args.version, folder).get("checks", {})
    blockers, skipped, majors, notes = [], [], [], []
    for name, rec in records.items():
        for c in rec["checks"]:
            key = f"{name}/{c['id']}"
            if c["status"] in (FAIL, SKIP) and c["severity"] == MAJOR and key in accepted:
                c["status"], c["summary"] = ACCEPTED, f"{c['summary']} (accepted: {accepted[key]})"
            if c["status"] == FAIL and c["severity"] == BLOCKER:
                blockers.append(f"{key}: {c['title']}")
            elif c["status"] == SKIP and c["severity"] == BLOCKER:
                skipped.append(f"{key}: {c['title']}")
            elif c["status"] in (FAIL, SKIP) and c["severity"] == MAJOR:
                majors.append(f"{key}: {c['title']}")
    missing = [n for n in LAYERS if n not in records]
    differ = code_differs({name: rec["git"].get("sha") for name, rec in records.items()})
    if differ:
        notes.append(differ)
    if any(rec["git"].get("dirty") is not False for rec in records.values()):
        notes.append("a layer ran on a tree with uncommitted changes, or where git could not tell")
    review = folder / "review.md"
    if not review.exists():
        notes.append("no independent review recorded (review.md, layer 6)")
    cleared = not (blockers or skipped or majors or missing or notes)
    if blockers:
        verdict = f"**NOT CLEARED**: {len(blockers)} BLOCKER check(s) failed."
    elif cleared:
        verdict = "**CLEARED**: every layer ran on the same clean commit; no BLOCKER failed or was skipped; every MAJOR passed or was accepted."
    elif ready_to_publish(blockers, skipped, majors, missing, notes):
        verdict = ("**READY TO PUBLISH**: every layer before publishing ran on the same clean commit; no BLOCKER failed "
                   "or was skipped; every MAJOR passed or was accepted. Tag it, then run `after-publish` to clear it.")
    else:
        verdict = "**INCOMPLETE**: no BLOCKER failed, but the gate is not complete (see below)."

    lines = [f"# Release gate: Netdryrun {args.version}", "",
             "Written by `scripts/release_gate.py` (see [RELEASING.md](../../RELEASING.md)). Do not edit by hand: "
             "rerun a layer, or record a decision in `accepted.json` or `review.md`.", "", verdict, ""]
    for title, items in (("BLOCKER failures", blockers), ("BLOCKER checks skipped", skipped),
                         ("MAJOR checks not passed or accepted", majors),
                         ("Layers not run yet", [LAYERS[n] for n in missing]), ("Other gaps", notes)):
        if items:
            lines += [f"**{title}:**", ""] + [f"- {cell(i)}" for i in items] + [""]

    lines += ["| Layer | Commit | Ran | Time | Result |", "|---|---|---|---|---|"]
    for name, title in LAYERS.items():
        rec = records.get(name)
        if not rec:
            lines.append(f"| {title} | | not run | | |")
            continue
        g = rec["git"]
        sha = (g.get("sha") or "unknown")[:10] + {True: " (dirty)", None: " (clean?)", False: ""}[g.get("dirty")]
        counts = {}
        for c in rec["checks"]:
            counts[c["status"]] = counts.get(c["status"], 0) + 1
        lines.append(f"| [{title}](#{anchor(title)}) | `{sha}` | {rec['started']} | {fmt_secs(rec['seconds'])} | "
                     + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) + " |")
    lines.append("")

    for rec in records.values():
        g = rec["git"]
        lines += [f"## {rec['title']}", "",
                  f"Commit `{g.get('sha') or 'unknown'}` on `{g.get('branch') or '?'}`"
                  f"{' (uncommitted changes)' if g.get('dirty') else ' (cleanliness unknown: git unavailable)' if g.get('dirty') is None else ''}; "
                  f"{rec['started']}; {fmt_secs(rec['seconds'])}; {rec['host']}; Python {rec['python']}"
                  f"{'; --strict' if rec.get('strict') else ''}.", ""]
        if rec["tools"]:
            lines += ["Tools: " + "; ".join(f"{k} {v}" for k, v in sorted(rec["tools"].items())) + ".", ""]
        lines += ["| Check | Severity | Result | Time | Notes |", "|---|---|---|---|---|"]
        for c in rec["checks"]:
            lines.append(f"| {cell(c['title'])} | {c['severity']} | **{c['status']}** | {fmt_secs(c['seconds'])} | {cell(c['summary'])} |")
        lines.append("")
        for s in rec.get("sections", []):
            lines += [s, ""]
        failing = [c for c in rec["checks"] if c["status"] in (FAIL, ACCEPTED) and c["output"]]
        for c in failing:
            lines += [f"<details><summary>{c['status']}: {cell(c['title'])}</summary>", ""]
            if c["command"]:
                lines += [f"`{c['command']}`", ""]
            lines += ["```text", c["output"].replace("```", "'''"), "```", "", "</details>", ""]
    lines += ["## Layer 6: independent review", ""]
    lines += [review.read_text(encoding="utf-8").strip(), ""] if review.exists() else [
        "Not recorded yet. Put the cold review, outside-model review, claims audit and fresh-user replay "
        "findings, and the decision on each, in `review.md` beside this file.", ""]
    return "\n".join(lines), cleared


def prose_only(path: str) -> bool:
    """Files no layer but static reads: Markdown outside the code, tests and scripts, and the generated llms texts."""
    if path.startswith(("src/", "tests/", "scripts/", ".github/")):
        return False
    return path.endswith(".md") or path in ("website/docs/llms.txt", "website/docs/llms-full.txt")


def code_differs(shas: dict[str, str | None]) -> str | None:
    """Layers may run on different commits only when those differ in releases/ (the gate's own records,
    committed between layers) or in prose (prose_only), and only if the static layer, which checks the
    prose (facts, versions, links), ran on the newest of them. Anything else means different code."""
    known = {n: str(s) for n, s in shas.items() if s}
    if len(set(known.values())) <= 1:
        return None
    ref = known.get("static")
    if ref is None:
        return "the layers ran on different commits and the static layer, which must run on the newest, has no record"
    for name, other in known.items():
        if other == ref:
            continue
        if git("merge-base", "--is-ancestor", other, ref) is None:
            return f"the {name} layer ran on {other[:7]}, which is not an ancestor of the static layer's {ref[:7]}"
        changed = git("diff", "--name-only", other, ref)
        if changed is None:
            return "the layers ran on different commits and git cannot compare them: " + ", ".join(
                s[:7] for s in set(known.values()))
        code = [f for f in changed.splitlines() if not f.startswith("releases/") and not prose_only(f)]
        if code:
            return f"the layers ran on different code: {other[:7]} ({name}) and {ref[:7]} (static) differ in {', '.join(code[:5])}"
    return None


def anchor(title: str) -> str:
    return re.sub(r"[^\w\- ]", "", title.lower()).strip().replace(" ", "-")


def fmt_secs(s: float) -> str:
    s = float(s or 0)
    return f"{s:.1f} s" if s < 90 else f"{s / 60:.1f} min"


def save(layer: Layer) -> None:
    args = layer.args
    rec = layer.record()
    write_out(args, f"gate/{layer.name}.json", json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    text, _ = render(args)
    path = write_out(args, "GATE.md", text)
    print(f"wrote {path}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:   # the layer's own section, on the GitHub job page
        section = text[text.find(f"## {rec['title']}"):]
        section = section[:section.find("\n## ", 4)] if "\n## " in section[4:] else section
        with open(summary, "a", encoding="utf-8") as f:
            f.write(section + "\n")


def layer_failed(layer: Layer) -> bool:
    return any(c.status == FAIL and c.severity == BLOCKER for c in layer.checks)


# --------------------------------------------------------------------------------------------

RUNNERS = {"static": layer_static, "unit": layer_unit, "mutation": layer_mutation, "live": layer_live,
           "after-publish": layer_after_publish, "consistency": layer_consistency}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Layers: " + ", ".join(RUNNERS) + ". See RELEASING.md.")
    ap.add_argument("layer", choices=[*RUNNERS, "all", "report"])
    ap.add_argument("publish_version", nargs="?", help="after-publish: the version just published")
    ap.add_argument("--version", help="the release under test (default: pyproject.toml's version)")
    ap.add_argument("--out", help="report folder (default releases/<version>)")
    ap.add_argument("--strict", action="store_true", help="a skipped BLOCKER (missing tool, no Docker) is a failure")
    ap.add_argument("--candidate", action="store_true",
                    help="static: this is the release candidate (CHANGELOG cut, tag and PyPI version unused)")
    ap.add_argument("--pythons", default=",".join(PYTHONS), help=f"unit/after-publish: versions (default {','.join(PYTHONS)})")
    ap.add_argument("--modules", default=",".join(VERDICT_MODULES), help="mutation: modules to mutate (default all)")
    ap.add_argument("--carry-mutation", metavar="MUTATION_JSON",
                    help="mutation: keep this earlier record for every module not in --modules whose source is "
                         "byte-identical at this commit")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2, help="mutation: parallel workers")
    ap.add_argument("--mutation-timeout", type=float, default=4 * 3600, help="mutation: seconds (default 4 h)")
    ap.add_argument("--examples", help="live: only these examples (comma-separated)")
    ap.add_argument("--skip-corpus", action="store_true", help="live: skip the corpus reruns (recorded as SKIP)")
    ap.add_argument("--pack", help="live: a check pack's verify script, run with NDR=<installed netdryrun>")
    ap.add_argument("--pin-accepted", action="store_true",
                    help="mutation: add diff fingerprints to accepted mutants that have none, after auditing each one")
    ap.add_argument("--allow-running-labs", action="store_true",
                    help="live: start although clab- containers exist (only new ones count as left over)")
    ap.add_argument("--chaos-docker-restart", action="store_true", help="live: also restart Docker mid-run (sudo)")
    args = ap.parse_args()

    if args.layer == "after-publish":
        if not args.publish_version:
            ap.error("after-publish needs the published VERSION")
        args.version = args.publish_version
    args.version = args.version or package_version()
    args.pythons = [p for p in args.pythons.split(",") if p]
    args.modules = [m for m in args.modules.split(",") if m]
    args.examples = [e for e in (args.examples or "").split(",") if e]
    bad = [m for m in args.modules if m not in VERDICT_MODULES]
    if bad:
        ap.error(f"unknown module(s) {bad}; choose from {list(VERDICT_MODULES)}")

    if args.layer == "report":
        text, cleared = render(args)
        state = "CLEARED" if cleared else "READY TO PUBLISH" if "**READY TO PUBLISH**" in text else "not cleared"
        print(f"wrote {write_out(args, 'GATE.md', text)}: {state}")
        return 0 if cleared else 1

    names = ["static", "unit", "mutation", "live"] if args.layer == "all" else [args.layer]
    failed = []
    for name in names:
        print(f"== {({**LAYERS, **CHECK_LAYERS})[name]} (Netdryrun {args.version})", flush=True)
        layer = RUNNERS[name](args)
        save(layer)
        if layer_failed(layer):
            failed.append(name)
    print(f"gate: {'BLOCKER failure in ' + ', '.join(failed) if failed else 'no BLOCKER failed'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
