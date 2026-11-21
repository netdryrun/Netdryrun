"""Fast-fix guards (0.4.2): the loosening gate and the reproduce-first check.

Design, evidence obligations and the adversary's findings: design/fast-fix-042-impl.md in the business repository.
The rules for contributors are in tests/oracles/README.md. Both commands only ever block; a clean run licenses
nothing to pass.

  python scripts/fastfix_gate.py loosening --repo . --base <merge-base> [--candidate HEAD]
      Compare verdicts at the base with the candidate's, case by case, and block any FAIL/UNKNOWN -> PASS that a
      reviewed allowlist entry (fastfix/allow/*.yml, added or changed in this change) doesn't cover:
      - every committed corpus results.json (records only: this re-runs no lab);
      - the must-not-pass fixtures (red team with its pinned tests, known false passes, committed oracles), run as
        the BASE has them, with only the candidate's src/ packages swapped in.

      --json PATH writes every flip (allowed or not) with its kind. A fixture flip caused by a command the code now
      sends to the device (a fake lab refused it with "unexpected command: ...", or the fake labs' command log shows
      a command only the candidate sent) is kind new-read: its allowlist entry says so, and the release then needs
      live on that network OS. --dominance is the release's run against the published tag: its JSON also says
      whether the tag's fixtures kept the command log, which drivers changed since the tag, and every new-read
      allowlist entry since the tag, so the report can route each one to live.

  python scripts/fastfix_gate.py plants --repo . --candidate HEAD [--base <merge-base>] [--json PATH]
      Living plants: each oracle's tests/oracles/<ID>/plant.diff is its fix's shipped diff reversed. It must still
      apply to the candidate, its oracle must catch it by an assertion raised in the oracle's own folder, and the
      candidate without it must pass. A port (ported_from) touches only files its fix touched and adds no assert or
      raise its fix's reverse doesn't have. A plant changed since --base must have stopped applying first, and comes
      from a session that changed no shipped code. `plant: none` (with plant_why) is only for oracles fixed before
      plants were required; the JSON counts them as owed ports.

  python scripts/fastfix_gate.py loosening-files --base OLD/results.json --candidate NEW/results.json
      The corpus comparison for two results files, with no git and nothing beside this script (the corpus refresh runs
      in the live layer's scratch copy). It accepts no allowlist: commit, then run git mode.

  python scripts/fastfix_gate.py reproduce --repo . --range <merge-base>..HEAD
      Every commit that changes src/ names its oracle ("Fixes-Oracle: <ID>") or says why it has none
      ("No-Oracle: <reason>"). Each oracle tests/oracles/<ID>/ was committed earlier by another session
      ("Oracle: <ID>", "Session: <marker>"), fails on the fix's parent and passes on the fix, judged in the oracle's own
      tree with only src/ swapped in, and every oracle still passes on the candidate.

Exit codes: 0 clean, 1 blocked, 2 could not run (missing git, unreadable input, unresolvable ref). Treat anything
but 0 as a failure. Standard library plus PyYAML (imported only when needed); no path comes from the working
directory, so it runs the same in the repo, a scratch copy, mutmut's runner and the slim container.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

OK, BLOCKED, ERROR = 0, 1, 2

ORACLES = "tests/oracles"
ALLOW_DIR = "fastfix/allow"
REDTEAM_TARGET = "tests/test_redteam.py"
REDTEAM_DIR = "tests/redteam"
KNOWN_FALSE_PASSES = "tests/known_false_passes.yml"
ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9][0-9A-Za-z.-]*$")
SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{2,}$")
PKG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CORPUS_VERDICTS = {"safe": "PASS", "unsafe": "FAIL", "error": "UNKNOWN"}
# how much a case passes: a flip is any rise (MIXED = some runs of a nondeterministic case pass, not all)
RANK = {"FAIL": 0, "UNKNOWN": 0, "MIXED": 1, "PASS": 2}
MIN_WHY = 40
ALLOW_KEYS = {"source", "case", "from", "to", "evidence", "why", "reviewed_by"}
EVIDENCE_NOT_UNDER = ("src/", "fastfix/", "scripts/", ".github/")
# the gate's own tools must not be importable from a tree under test
GATE_MODULES = ("pytest", "_pytest", "pluggy", "yaml", "sitecustomize", "usercustomize")
# the fake labs' command log (tests/fakes.py): set only by the gate, per run, outside the tree under test
COMMAND_LOG_ENV = "NDR_FAKE_COMMAND_LOG"
CHILD_ENV_DROP = ("MUTANT_UNDER_TEST", "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONSTARTUP", "PYTHONHOME",
                  "PYTEST_CURRENT_TEST", "PYTHONPATH", COMMAND_LOG_ENV)
# an oracle on the buggy parent fails by an assertion, or by pytest.raises seeing no refusal
ASSERTION = re.compile(r"^(assert\b|AssertionError\b|Failed: DID NOT RAISE\b)")
# what ships to users besides src/: swapped in from the code under test; a change to it needs a trailer
SURFACES = ("action.yml", "templates")
# the gate's own code: judged by the base's copy, and a change to it must be allowed like a flip
# the gate's own files: once the base has the gate, changing any of them is a flip that needs a reviewed allowlist entry
# (Layer 6 on f220469: the attempt records, labrun and the surfaces check were left out)
GATE_FILES = ("scripts/fastfix_gate.py", "scripts/release_gate.py", ".github/workflows/release-gate.yml",
              "scripts/gate_records.py", "scripts/labrun.py", "scripts/surfaces_agree.py")


# a fixture flip whose cause is a command the code under test now sends to the device: the fake lab refused it
# (tests/fakes.py words every refusal "unexpected command: ..."; pytest may put the exception's name in front, and
# older fakes in oracle folders say "unexpected command <x>")
NEW_READ = "new-read"
UNEXPECTED = re.compile(r"^(?:[A-Za-z_][\w.]*: )?unexpected command\b")
# a new read's reviewer is a session of its own: its commits in the range hold review records and nothing else
REVIEW_DIR = "fastfix/reviews"
# which network OS a fixture test exercises, from its node id: a driver class first (test_x[SrlDriver]), then a
# name in the module or test (test_frr_*, tests.test_nxos); nothing found means every driver ("*")
DRIVER_CLASSES = {"frr": "frr", "sonic": "sonic", "eos": "eos", "srl": "srlinux", "srlinux": "srlinux",
                  "junos": "junos", "nxos": "nxos", "routeros": "routeros"}
DRIVER_ALIASES = {**DRIVER_CLASSES, "arista": "eos", "ceos": "eos", "mikrotik": "routeros"}
# living plants: tests/oracles/<ID>/plant.diff puts the fixed bug back into the shipped code
PLANT = "plant.diff"
SHIPPED_PATHS = ("src", *SURFACES)
PLANT_KEYS = {"plant", "plant_why", "ported_from"}
DRIVERS_DIR = "src/netdryrun/drivers/"
DRIVER_FILES = {"frr": "frr", "sonic": "sonic", "eos": "eos", "srlinux": "srlinux", "junos": "junos", "nxos": "nxos",
                "routeros": "routeros", "routeros_rest": "routeros", "routeros_state": "routeros"}


def shipped(path: str) -> bool:
    return path.startswith("src/") or path == "action.yml" or path.startswith("templates/")


class GateError(Exception):
    """The check could not run or an input was unreadable: exit 2, never a pass."""


# ------------------------------------------------------------------------------------------------ git

def git(repo: Path, *args: str, env: dict | None = None) -> str:
    if shutil.which("git") is None:
        raise GateError("git is not available: the check can't run here (fail-closed)")
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       env={**os.environ, **(env or {}), "GIT_TERMINAL_PROMPT": "0"})
    if p.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {p.stderr.decode(errors='replace').strip()[:400]}")
    return p.stdout.decode("utf-8", errors="replace")


def resolve(repo: Path, ref: str) -> str:
    if not ref or ref.startswith("-"):
        raise GateError(f"not a revision: {ref!r}")
    return git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").strip()


def export(repo: Path, sha: str, dest: Path) -> Path:
    """The committed tree of `sha` (never the working tree; export-ignore attributes don't apply)."""
    dest.mkdir(parents=True, exist_ok=True)
    index = dest.parent / f".index-{dest.name}"
    try:
        git(repo, "read-tree", sha, env={"GIT_INDEX_FILE": str(index)})
        git(repo, "checkout-index", "--all", "--force", f"--prefix={dest.as_posix()}/",
            env={"GIT_INDEX_FILE": str(index)})
    finally:
        index.unlink(missing_ok=True)
    return dest


def split_z(out: str) -> set[str]:
    return {p for p in out.split("\0") if p}


def changed_files(repo: Path, a: str, b: str) -> set[str]:
    return split_z(git(repo, "diff", "--name-only", "-z", "--no-renames", a, b))


def commit_files(repo: Path, sha: str) -> set[str]:
    """Files a commit changes. For a merge: the files its result differs from EVERY parent in (the conflict
    resolution, or an 'evil merge'), which no other commit in the range shows."""
    if len(parents(repo, sha)) > 1:
        try:   # git 2.36+: only what differs from git's own automatic merge (a clean merge shows nothing)
            return split_z(git(repo, "show", "--remerge-diff", "--format=", "--name-only", "-z", sha))
        except GateError:   # older git: --cc also lists files both sides changed cleanly (conservative)
            return split_z(git(repo, "diff-tree", "--cc", "--no-commit-id", "-r", "--name-only", "-z", sha))
    return split_z(git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", "-z", "--no-renames", "--root", sha))


def parents(repo: Path, sha: str) -> list[str]:
    return git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]


def trailers(repo: Path, sha: str) -> dict[str, list[str]]:
    out = git(repo, "show", "-s", "--format=%(trailers:only,unfold)", sha)
    found: dict[str, list[str]] = {}
    for line in out.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and value.strip():
            found.setdefault(key.strip().lower(), []).append(value.strip())
    return found


def session_of(repo: Path, sha: str) -> str | None:
    """The commit's one Session: marker, or None. Two markers are ambiguous: the check can't run."""
    values = trailers(repo, sha).get("session", [])
    if len(values) > 1:
        raise GateError(f"{sha[:10]} carries {len(values)} Session: trailers; exactly one is allowed")
    if values and not SESSION_RE.match(values[0]):
        raise GateError(f"{sha[:10]}: Session: {values[0]!r} is not a valid marker")
    return values[0] if values else None


def same_session(a: str | None, b: str | None) -> bool:
    """Two Session markers name one session when their words match in any order, case or separator (fix-unnsess and
    unnsess-fix): the markers are typed by hand, and a reordered one must not pass for another session. Words that
    differ (unnsess-fix and unnsess-oracle) are different sessions."""
    return bool(a and b) and session_key(a) == session_key(b)


def session_key(s: str) -> tuple[str, ...]:
    return tuple(sorted(w for w in re.split(r"[^a-z0-9]+", s.lower()) if w))


def rev_list(repo: Path, base: str, cand: str) -> list[str]:
    return git(repo, "rev-list", "--reverse", "--topo-order", f"{base}..{cand}").split()


def last_touch(repo: Path, at: str, path: str) -> str | None:
    out = git(repo, "log", "-n", "1", "--format=%H", at, "--", path).split()
    return out[0] if out else None


# ------------------------------------------------------------------------------------------------ inputs

def _no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        raise ValueError(f"duplicate key(s) {dup}")
    return dict(pairs)


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise GateError(f"{path}: unreadable ({e})") from None


def load_yaml(path: Path) -> object:
    try:
        import yaml
    except ImportError:
        raise GateError("PyYAML is not installed: the check can't run here (fail-closed)") from None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise GateError(f"{path}: unreadable ({e})") from None


# ------------------------------------------------------------------------------------------------ comparing

@dataclass(frozen=True)
class Flip:
    source: str
    case: str
    before: str
    after: str
    kind: str = "verdict"           # verdict, gate or new-read
    drivers: tuple[str, ...] = ()   # new-read: the network OSes the read goes to ("*": any)

    def __str__(self) -> str:
        extra = f" [{NEW_READ} on {', '.join(self.drivers)}]" if self.kind == NEW_READ else ""
        return f"{self.source} :: {self.case}: {self.before} -> {self.after}{extra}"

    def as_json(self, allowed_by: str | None = None) -> dict:
        return {"source": self.source, "case": self.case, "from": self.before, "to": self.after, "kind": self.kind,
                "drivers": list(self.drivers), "allowed_by": allowed_by}


@dataclass
class Report:
    flips: list[Flip] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)     # each one blocks
    notes: list[str] = field(default_factory=list)
    allowed: dict[Flip, str] = field(default_factory=dict)    # flip -> the allowlist file that covers it
    skipped_at_base: list[dict] = field(default_factory=list)
    compared: dict[str, int] = field(default_factory=dict)
    shas: dict[str, str] = field(default_factory=dict)
    command_log_at_base: bool = False
    changed_drivers: list[str] = field(default_factory=list)
    new_read_entries: list[dict] = field(default_factory=list)

    def compare(self, source: str, base: dict[str, str], cand: dict[str, str]) -> None:
        """Per case, never in aggregate. A case judged at the base and not at the candidate blocks."""
        for case in sorted(base):
            if case not in cand:
                self.problems.append(f"{source} :: {case}: judged at the base, not at the candidate (removed, renamed "
                                     "or not run): a missing verdict is not a pass")
            elif RANK[cand[case]] > RANK[base[case]]:
                self.flips.append(Flip(source, case, base[case], cand[case]))
        self.notes.append(f"{source}: {len(base)} cases compared")
        kind = "fixtures" if source == "fixtures" else "corpus"
        self.compared[kind] = self.compared.get(kind, 0) + len(base)

    def as_json(self) -> dict:
        return {"base": self.shas.get("base"), "candidate": self.shas.get("candidate"), "compared": self.compared,
                "skipped_at_base": self.skipped_at_base,
                "flips": [f.as_json() for f in self.flips] + [f.as_json(by) for f, by in self.allowed.items()],
                "command_log_at_base": self.command_log_at_base, "changed_drivers": self.changed_drivers,
                "new_read_entries": self.new_read_entries, "problems": self.problems}


def corpus_verdicts(data: object, where: str) -> dict[str, str]:
    """case id -> PASS, MIXED, FAIL or UNKNOWN for the netdryrun strategy. A nondeterministic case keeps every run in
    "runs" (the first is the row's verdict): all safe is PASS, some safe is MIXED. Anything unexpected is unreadable."""
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise GateError(f"{where}: no 'cases' list")
    out: dict[str, str] = {}
    for i, case in enumerate(data["cases"]):
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise GateError(f"{where}: case #{i + 1} has no id")
        cid = case["id"]
        if cid in out:
            raise GateError(f"{where}: case {cid} appears twice")
        try:
            seen = [case["strategies"]["netdryrun"]["verdict"]]
            runs = case.get("runs")
            if runs is not None:
                if not isinstance(runs, list) or not runs:
                    raise TypeError("runs is not a non-empty list")
                seen += [r["netdryrun"] for r in runs]
        except (KeyError, TypeError) as e:
            raise GateError(f"{where}: case {cid}: no netdryrun verdict ({e})") from None
        bad = [v for v in seen if not isinstance(v, str) or v not in CORPUS_VERDICTS]
        if bad:
            raise GateError(f"{where}: case {cid}: unknown verdict {bad[0]!r}")
        mapped = [CORPUS_VERDICTS[v] for v in seen]
        if all(m == "PASS" for m in mapped):
            out[cid] = "PASS"
        elif "PASS" in mapped:
            out[cid] = "MIXED"
        else:
            out[cid] = "UNKNOWN" if "UNKNOWN" in mapped else "FAIL"
    if not out:
        raise GateError(f"{where}: no cases")
    return out


def compare_corpus_files(base_path: Path, cand_path: Path, source: str, report: Report) -> None:
    base = corpus_verdicts(load_json(base_path), str(base_path))
    if not cand_path.is_file():
        report.problems.append(f"{source}: results present at the base, missing at the candidate")
        return
    report.compare(source, base, corpus_verdicts(load_json(cand_path), str(cand_path)))


def corpus_results(tree: Path) -> dict[str, Path]:
    found = {}
    for p in [tree / "corpus" / "results" / "results.json", *sorted((tree / "corpus").glob("*/results/results.json"))]:
        if p.is_file():
            found[p.relative_to(tree).as_posix()] = p
    return found


# ------------------------------------------------------------------------------------------------ running tests

def packages(tree: Path) -> list[str]:
    src = tree / "src"
    return sorted(p.name for p in src.iterdir() if PKG_RE.match(p.name) and (p / "__init__.py").is_file()) \
        if src.is_dir() else []


def compose(world: Path, code: Path, dest: Path) -> Path:
    """`world`'s whole tree (tests, fixtures, data, advisories, pyproject, conftest) with only what ships swapped in
    from `code`: its src/ packages (none named like a gate tool) and SURFACES (action.yml, templates/). Nothing else
    from the code under test reaches the run (no root conftest, no pytest config, no src/sitecustomize.py)."""
    if not packages(world):
        raise GateError(f"{world.name}: no package under src/ to judge")
    shutil.copytree(world, dest, symlinks=True)
    shutil.rmtree(dest / "src")
    (dest / "src").mkdir()
    for n in packages(code):
        if n not in GATE_MODULES:
            shutil.copytree(code / "src" / n, dest / "src" / n, symlinks=True)
    for surface in SURFACES:
        shutil.rmtree(dest / surface, ignore_errors=True) if (dest / surface).is_dir() else (dest / surface).unlink(missing_ok=True)
        if (code / surface).is_dir():
            shutil.copytree(code / surface, dest / surface, symlinks=True)
        elif (code / surface).is_file():
            shutil.copy2(code / surface, dest / surface)
    return dest


def child_env(tree: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in CHILD_ENV_DROP and not k.startswith("MUTMUT")}
    env.update(PYTHONPATH=str(tree / "src"), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    return env


def preflight(tree: Path, python: str) -> None:
    """The packages under test import from this tree; the gate's tools (pytest, pluggy, yaml) and any
    sitecustomize don't (E9: an install elsewhere, or a planted module, must not answer for them)."""
    names = packages(tree)
    if not names:
        raise GateError(f"{tree.name}: no package under src/")
    code = ("import importlib.util as u,sys\n"
            "for n in sys.argv[1:]:\n"
            "    s=u.find_spec(n)\n"
            "    print(n, s.origin if s and s.origin else '-')\n")
    p = subprocess.run([python, "-c", code, *names, *GATE_MODULES], cwd=tree, env=child_env(tree),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise GateError(f"{tree.name}: preflight failed: {p.stderr.strip()[-400:]}")
    src = (tree / "src").resolve()
    for line in p.stdout.splitlines():
        name, _, origin = line.partition(" ")
        inside = origin != "-" and Path(origin).resolve().is_relative_to(tree.resolve())
        if name in names and not (origin != "-" and Path(origin).resolve().is_relative_to(src)):
            raise GateError(f"{tree.name}: {name} imports from {origin}, not from the tree under test")
        if name not in names and inside:
            raise GateError(f"{tree.name}: {name} would import from the tree under test ({origin})")


@dataclass
class PytestRun:
    code: int
    outcomes: dict[str, str]          # node key -> passed / failed / error / skipped
    messages: dict[str, str]          # node key -> failure message
    output: str
    details: dict[str, str] = field(default_factory=dict)    # node key -> the failure's traceback text

    def count(self, outcome: str) -> int:
        return sum(1 for o in self.outcomes.values() if o == outcome)


def run_pytest(tree: Path, targets: list[str], python: str, work: Path, command_log: Path | None = None) -> PytestRun:
    """pytest on `targets` inside `tree`, configured by the tree's own pyproject.toml (the world's), report written
    outside the tree. Exit code and report must agree. With `command_log`, the fake labs record every command they
    are sent there (tests/fakes.py)."""
    preflight(tree, python)
    work.mkdir(parents=True, exist_ok=True)
    xml = work / f"junit-{len(list(work.glob('junit-*.xml')))}.xml"
    ini = tree / "pyproject.toml"
    if not ini.is_file():
        ini = work / "empty.ini"
        ini.write_text("[pytest]\n", encoding="utf-8")
    cmd = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "-c", str(ini),
           "--rootdir", str(tree), "--confcutdir", str(tree), f"--junitxml={xml}", "--", *targets]
    env = child_env(tree)
    if command_log is not None:
        command_log.unlink(missing_ok=True)
        env[COMMAND_LOG_ENV] = str(command_log)
    p = subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True, timeout=1800)
    outcomes: dict[str, str] = {}
    messages: dict[str, str] = {}
    details: dict[str, str] = {}
    if xml.is_file():
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError as e:
            raise GateError(f"pytest's report is unreadable ({e})") from None
        for tc in root.iter("testcase"):
            key = f"{tc.get('classname', '')}::{tc.get('name', '')}"
            kid = next((c for c in tc if c.tag in ("failure", "error", "skipped")), None)
            kinds = {c.tag for c in tc} & {"failure", "error", "skipped"}
            outcome = ("failed" if "failure" in kinds else "error" if "error" in kinds
                       else "skipped" if "skipped" in kinds else "passed")
            if outcomes.get(key, "passed") == "passed":   # reported twice (call, teardown): keep the worse
                outcomes[key] = outcome
                messages[key] = (kid.get("message") or "") if kid is not None else ""
                details[key] = (kid.text or "") if kid is not None else ""
    out = (p.stdout + p.stderr)[-3000:]
    bad = sum(o in ("failed", "error") for o in outcomes.values())
    if p.returncode == 0 and (bad or not outcomes):
        raise GateError(f"pytest exited 0 but its report shows {bad} failed of {len(outcomes)}:\n{out[-800:]}")
    if p.returncode == 1 and not bad:
        raise GateError(f"pytest exited 1 but its report shows no failure:\n{out[-800:]}")
    return PytestRun(p.returncode, outcomes, messages, out, details)


# ------------------------------------------------------------------------------------------------ loosening (git)

def fixture_targets(base_tree: Path, origins: dict[str, str] | None = None) -> list[str]:
    """The must-not-pass fixtures as the BASE has them: the red team, the tests its pinned cases name, every test
    the known-false-pass list names, and every committed oracle. `origins` gets, per target, where it came from."""
    if not (base_tree / REDTEAM_TARGET).is_file():
        raise GateError(f"the base has no {REDTEAM_TARGET}")
    origins = {} if origins is None else origins
    origins.setdefault(REDTEAM_TARGET, "redteam")
    targets = [REDTEAM_TARGET]
    for f in sorted((base_tree / REDTEAM_DIR).glob("RT-*.yml")):
        case = load_yaml(f)
        if not isinstance(case, dict):
            raise GateError(f"{REDTEAM_DIR}/{f.name}: not a mapping")
        if case.get("kind") == "pinned" and not case.get("retired"):
            tests = case.get("tests")
            if not isinstance(tests, list) or not tests:
                raise GateError(f"{REDTEAM_DIR}/{f.name}: a pinned case names no tests")
            targets += [_target(t, f.name) for t in tests]
            for t in tests:
                origins.setdefault(t, "redteam")
    kfp = base_tree / KNOWN_FALSE_PASSES
    if kfp.is_file():
        entries = load_yaml(kfp)
        if not isinstance(entries, list):
            raise GateError(f"{KNOWN_FALSE_PASSES}: not a list")
        for e in entries:
            if not isinstance(e, dict):
                raise GateError(f"{KNOWN_FALSE_PASSES}: an entry is not a mapping")
            targets += [_target(t, KNOWN_FALSE_PASSES) for t in e.get("tests") or []]
            for t in e.get("tests") or []:
                origins.setdefault(t, "known_false_passes")
    oracles = base_tree / ORACLES
    if oracles.is_dir():
        for d in sorted(oracles.iterdir()):
            if d.is_dir() and ID_RE.match(d.name):
                targets.append(f"{ORACLES}/{d.name}")
                origins.setdefault(f"{ORACLES}/{d.name}", "oracles")
    return list(dict.fromkeys(targets))


def junit_key(nodeid: str) -> str:
    """pytest's node id (tests/test_x.py::TestC::test_y[p]) as the junit key run_pytest uses
    (tests.test_x.TestC::test_y[p]). A parameter id may itself hold "::": only the part before "[" is split."""
    head, bracket, param = nodeid.partition("[")
    parts = head.split("::")
    module = parts[0].removesuffix(".py").replace("/", ".")
    key = ".".join([module, *parts[1:-1]]) + "::" + parts[-1] if len(parts) > 1 else module
    return key + bracket + param


def origin_of(key: str, origins: dict[str, str]) -> tuple[str, str]:
    """(target, origin) of a junit key: the target whose file or folder holds the test."""
    classname = key.split("::", 1)[0]
    for target, origin in origins.items():
        prefix = target.split("::", 1)[0].removesuffix(".py").replace("/", ".")
        if classname == prefix or classname.startswith(prefix + "."):
            return target, origin
    return "?", "unknown"


def drivers_of(key: str) -> tuple[str, ...]:
    """The network OSes a fixture test exercises, from its node id: every driver class and every OS name it holds
    (more live runs, never fewer); ("*",) when the id names none (any driver)."""
    found = {DRIVER_CLASSES[m.lower()] for m in re.findall(r"([A-Za-z]+?)Driver\b", key)
             if m.lower() in DRIVER_CLASSES}
    found |= {DRIVER_ALIASES[t] for t in re.split(r"[^a-z0-9]+", key.lower()) if t in DRIVER_ALIASES}
    return tuple(sorted(found)) or ("*",)


def changed_drivers(files: set[str]) -> list[str]:
    """The network OSes whose driver code changed: a shared driver file (base.py, addresses.py, ...) is every one."""
    out = set()
    for f in files:
        if f.startswith(DRIVERS_DIR) and f.endswith(".py"):
            out.add(DRIVER_FILES.get(f[len(DRIVERS_DIR):-3], "*"))
    return sorted(out)


# tests/fakes.py from log format 2 replaces the temporary paths each test made itself (<tmp1>, <pytest-tmp>). An older
# base's fakes logged them as they were: for those logs only the product's own scratch directory names
# (tempfile.mkdtemp(prefix="netdryrun-<what>-") directly under the temp directory, followed by a path inside it) are
# replaced, numbered in the order a test's log names them, so two of them never merge. Nothing else under /tmp is.
LOG_FORMAT = 2
LEGACY_TEMP = r"netdryrun-[a-z]+-[a-z0-9_]{8}"
PATH_CHAR = r"[\w.~:/\\-]"


def legacy_temp_pattern() -> re.Pattern:
    """A product scratch directory in an older log: <temp dir>/netdryrun-<what>-<8 random>, starting a path (nothing
    path-like before it) and followed by a separator."""
    dirs = {tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir()), "/tmp"}
    alts = "|".join(re.escape(d.rstrip("/\\")) for d in sorted(dirs, key=len, reverse=True) if d.rstrip("/\\"))
    return re.compile(rf"(?<!{PATH_CHAR})(?:{alts})[/\\]{LEGACY_TEMP}(?=[/\\])")


def stable_command(text: str, roots: tuple[str, ...] = (), labels: dict[str, str] | None = None,
                   legacy: bool = False) -> str:
    """A logged command as the same text on every run of the same code: the trees under test as <root> (whole path
    names only), JSON with sorted keys, and in an older log (`legacy`) the product's scratch directories as <tmpN>
    (`labels`: the test's numbering so far). Dict keys are never changed, so two keys can't merge; a new call, or a
    new argument next to a temporary path, still reads as new."""
    labels = {} if labels is None else labels
    temp = legacy_temp_pattern() if legacy else None
    ordered = sorted((r for r in roots if r), key=len, reverse=True)

    def scrub(s: str) -> str:
        for r in ordered:
            if r in s:
                s = re.sub(rf"(?<![\w.~-]){re.escape(r)}(?![\w.~-])", "<root>", s)
        if temp is not None:
            s = temp.sub(lambda m: labels.setdefault(m.group(0), f"<tmp{len(labels) + 1}>"), s)
        return s

    def walk(v):
        if isinstance(v, str):
            return scrub(v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    try:
        data = json.loads(text)
    except ValueError:
        return scrub(text)
    if isinstance(data, str):
        return json.dumps(scrub(data))
    if not isinstance(data, (dict, list)):
        return text
    return json.dumps(walk(data), sort_keys=True)


def read_commands(path: Path, roots: tuple[str, ...] = ()) -> dict[str, set[str]] | None:
    """junit key -> the commands the fake labs were sent in that test (stable_command); None when nothing was
    logged."""
    if not path.is_file():
        return None
    out: dict[str, set[str]] = {}
    labels: dict[str, dict[str, str]] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        try:
            row = json.loads(line)
            key = junit_key(row["test"])
            command = stable_command(str(row["command"]), roots, labels.setdefault(key, {}),
                                     legacy=row.get("log") != LOG_FORMAT)
            out.setdefault(key, set()).add(command)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise GateError(f"the fake labs' command log is unreadable at line {n}") from None
    return out or None


def _target(t: object, where: str) -> str:
    if not isinstance(t, str) or not t.startswith("tests/") or ".." in t.split("::")[0]:
        raise GateError(f"{where}: bad test target {t!r}")
    return t


def fixture_compare(base_run: PytestRun, cand_run: PytestRun, report: Report,
                    base_cmds: dict[str, set[str]] | None = None, cand_cmds: dict[str, set[str]] | None = None,
                    origins: dict[str, str] | None = None) -> None:
    """A passing fixture test means the tool refused the bad input (not PASS). On the candidate anything else
    (failed, error, skipped) counts as PASS: fail-closed. A test that fails or errors at the base is a red baseline.
    A test the base skips (here: a tool or file this machine lacks) proves nothing at the base: it isn't compared, so
    a skip on both sides is no flip, and only a pass at the base that turns into anything else is one (PR #6: 65
    docs-snippet tests skip on GitHub's runner)."""
    red = sorted(k for k, o in base_run.outcomes.items() if o not in ("passed", "skipped"))
    if red or base_run.code != 0:
        report.problems.append(f"the baseline is red: {len(red)} fixture test(s) fail on the base itself "
                               f"(pytest exit {base_run.code}): {', '.join(red[:5])}")
    skipped = sorted(k for k, o in base_run.outcomes.items() if o == "skipped")
    if skipped:
        report.notes.append(f"fixtures: {len(skipped)} skipped at the base on this machine, not compared")
    for k in skipped:
        target, origin = origin_of(k, origins or {})
        reason = base_run.messages.get(k, "")[:200]
        # also skipped, for the same reason, at the candidate: neither side ran it on this machine
        report.skipped_at_base.append({"case": k, "target": target, "origin": origin, "reason": reason,
                                       "same_at_candidate": cand_run.outcomes.get(k) == "skipped"
                                       and cand_run.messages.get(k, "")[:200] == reason})
    if cand_run.code not in (0, 1):
        report.problems.append(f"the base's fixtures did not run cleanly on the candidate's code (pytest exit "
                               f"{cand_run.code}; a collection error, or a dependency the candidate needs):\n"
                               f"{cand_run.output[-1200:]}")
    # a guard the base skipped (it couldn't run there) but that fails at the candidate is the tool accepting a
    # must-not-pass input: a red whatever the base could show (Layer 6 on f220469)
    for k, o in sorted(cand_run.outcomes.items()):
        if base_run.outcomes.get(k) == "skipped" and o in ("failed", "error"):
            report.problems.append(f"fixtures :: {k}: skipped at the base, {o} at the candidate: the candidate's code "
                                   "accepts an input this guard must refuse")
    base_v = {k: "FAIL" for k, o in base_run.outcomes.items() if o == "passed"}
    cand_v = {k: "FAIL" if o == "passed" else "PASS" for k, o in cand_run.outcomes.items()}
    before = len(report.flips)
    report.compare("fixtures", base_v, cand_v)
    new_reads(report, before, cand_run, base_v, base_cmds, cand_cmds)


def new_reads(report: Report, first: int, cand_run: PytestRun, compared: dict[str, str],
              base_cmds: dict[str, set[str]] | None, cand_cmds: dict[str, set[str]] | None) -> None:
    """Mark the fixture flips that come from a new device read, and add one for every command only the candidate's
    code sent in a test the base passed (a fake that matches by substring answers a new command without complaint,
    so a read can be new while the test still holds). A new read blocks like any flip; an allowlist entry for it
    says kind: new-read, and the release then needs live on that network OS."""
    for i in range(first, len(report.flips)):
        f = report.flips[i]
        msg = cand_run.messages.get(f.case, "")
        drivers = drivers_of(f.case)
        refused = bool(UNEXPECTED.match(msg))
        # until every base has the command log: a driver test that now fails by an exception, not an assertion
        raised = drivers != ("*",) and bool(msg) and not ASSERTION.match(msg)
        if refused or raised:
            report.flips[i] = Flip(f.source, f.case, f.before, f.after, NEW_READ, drivers)
    if base_cmds is None:
        report.notes.append("fixtures: no fake-lab command log at the base, so new reads are found only by a fake's "
                            "refusal or a driver exception")
        return
    if cand_cmds is None:
        report.problems.append("the fake labs logged commands at the base and none at the candidate: the code under "
                               "test may have turned the log off, so new device reads can't be seen")
        return
    flipped = {f.case: i for i, f in enumerate(report.flips) if f.source == "fixtures"}
    extra_total = 0
    for case in sorted(compared):
        extra = sorted(cand_cmds.get(case, set()) - base_cmds.get(case, set()))
        if not extra:
            continue
        extra_total += 1
        report.notes.append(f"fixtures :: {case}: new command(s) at the candidate: {'; '.join(extra[:3])[:300]}")
        flip = Flip("fixtures", case, "FAIL", "PASS", NEW_READ, drivers_of(case))
        if case in flipped:
            report.flips[flipped[case]] = flip
        else:
            report.flips.append(flip)
    report.notes.append(f"fixtures: fake-lab commands compared, {extra_total} test(s) send something new")


def loosening(repo: Path, base_ref: str, cand_ref: str, python: str, dominance: bool = False) -> Report:
    """`dominance`: the base is the published release, not this change's merge-base. An allowlist entry that
    matches no flip since the release is then only noted (it allows nothing); the stale-entry rule is enforced by the
    run against the change's own base."""
    report = Report()
    base, cand = resolve(repo, base_ref), resolve(repo, cand_ref)
    report.shas.update(base=base, candidate=cand)
    if base == cand:
        raise GateError(f"the base and the candidate are the same commit ({base[:10]}): nothing to compare")
    with tempfile.TemporaryDirectory(prefix="ndr-fastfix-") as tmp:
        work = Path(tmp)
        base_tree = export(repo, base, work / "base")
        cand_tree = export(repo, cand, work / "cand")
        # 1. committed corpus results (records: they change only when someone commits a refresh)
        base_corpora = corpus_results(base_tree)
        if not base_corpora:
            raise GateError("the base has no corpus results.json")
        for rel, path in base_corpora.items():
            compare_corpus_files(path, cand_tree / rel, rel, report)
        # the gate judging itself: once the base has it, a change to the gate's own code is a flip to allow
        if (base_tree / GATE_FILES[0]).is_file():
            touched = changed_files(repo, base, cand)
            report.flips += [Flip("gate", f"{g}@{gate_blob(repo, cand, g)}", "FAIL", "PASS", "gate")
                             for g in GATE_FILES if g in touched]
        # 2. must-not-pass fixtures: the base's world with the base's code, then with the candidate's code
        origins: dict[str, str] = {}
        targets = fixture_targets(base_tree, origins)
        # one log path for both runs (read in between): the path is in the environment the code under test may
        # pass on, so two paths would log two different commands for the same code
        log = work / "cmd.jsonl"
        roots = (str(base_tree), str(work / "mixed"))
        base_run = run_pytest(base_tree, targets, python, work / "r", log)
        base_cmds = read_commands(log, roots)
        mixed = compose(base_tree, cand_tree, work / "mixed")
        cand_run = run_pytest(mixed, targets, python, work / "r", log)
        report.command_log_at_base = base_cmds is not None
        report.changed_drivers = changed_drivers(changed_files(repo, base, cand))
        fixture_compare(base_run, cand_run, report, base_cmds, read_commands(log, roots), origins)
        report.notes.append(f"fixture targets ({len(targets)}): {', '.join(targets)}")
        # 3. the allowlist
        apply_allowlist(repo, base, cand, cand_tree, report, dominance)
    return report


def gate_blob(repo: Path, cand: str, path: str) -> str:
    """The first 12 hex digits of the gate file's blob at the candidate ("deleted" when it's gone): an allowlist entry
    names one version of the gate, so every later edit needs its own."""
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{cand}:{path}"],
                       capture_output=True, text=True)
    return p.stdout.strip()[:12] if p.returncode == 0 and p.stdout.strip() else "deleted"


def apply_allowlist(repo: Path, base: str, cand: str, cand_tree: Path, report: Report,
                    dominance: bool = False) -> None:
    changed = changed_files(repo, base, cand)
    files = sorted(f for f in changed if f.startswith(ALLOW_DIR + "/") and (cand_tree / f).is_file())
    if not files:
        return
    flips = {(f.source, f.case, f.before, f.after): f for f in report.flips}
    used = set()
    cited: set[str] = set()
    reviewers: set[str] = set()
    for f in files:
        for key, kind in allow_entries(f, cand_tree, changed, report, cited, reviewers):
            if kind == NEW_READ:   # the report routes every reviewed new read since the release to live
                report.new_read_entries.append({"case": key[1], "file": f, "drivers": list(drivers_of(key[1]))})
            flip = flips.get(key)
            if flip is None:
                text = (f"{f}: allows {key[0]} :: {key[1]} {key[2]} -> {key[3]}, which is not a flip in this change")
                if dominance:   # since the release: it allows nothing; the change's own run blocks a stale entry
                    report.notes.append(f"{text} (no effect here)")
                else:
                    report.problems.append(f"{text} (stale or pre-loaded entries block)")
            elif (flip.kind == NEW_READ) != (kind == NEW_READ):
                report.problems.append(
                    f"{f}: {flip} " + ("is a new device read: its entry must say kind: new-read, cite the updated "
                                       "test and name the reviewing session" if flip.kind == NEW_READ else
                                       "is not a new device read, but its entry says kind: new-read"))
            else:
                used.add(key)
                report.allowed[flip] = f
                report.notes.append(f"allowed by {f}: {flip}")
    report.flips = [fl for k, fl in flips.items() if k not in used]
    guarded = {f.source for f in flips.values() if "/" in f.source} | cited
    separation_problems(repo, base, cand, report, guarded, reviewers)


def allow_entries(f: str, tree: Path, changed: set[str], report: Report, cited: set[str],
                  reviewers: set[str] | None = None) -> list[tuple[tuple[str, str, str, str], str]]:
    """((source, case, from, to), kind) per valid entry. `kind: new-read` (optional key) is for a fixture flip caused
    by a new device read: it must cite the flipped test's own updated file, and reviewed_by must be
    '<session>: <what was checked>' from a session that changed no shipped code in this change."""
    if not f.endswith(".yml"):
        report.problems.append(f"{f}: an allowlist file must be YAML (.yml)")
        return []
    data = load_yaml(tree / f)
    entries = data.get("flips") if isinstance(data, dict) and set(data) == {"flips"} else None
    if not isinstance(entries, list) or not entries:
        report.problems.append(f"{f}: expected exactly one key, 'flips', holding a non-empty list")
        return []
    keys = []
    for i, e in enumerate(entries):
        where = f"{f} flip #{i + 1}"
        if not isinstance(e, dict) or set(e) - {"kind"} != ALLOW_KEYS:
            report.problems.append(f"{where}: keys must be exactly {sorted(ALLOW_KEYS)}, plus kind: {NEW_READ} for a "
                                   "new device read")
            continue
        kind = e.get("kind", "verdict")
        if "kind" in e and kind != NEW_READ:
            report.problems.append(f"{where}: kind may only be {NEW_READ}")
            continue
        text = {k: e[k] for k in ALLOW_KEYS - {"evidence"}}
        if not all(isinstance(v, str) and v.strip() for v in text.values()):
            report.problems.append(f"{where}: source, case, from, to, why and reviewed_by must be non-empty text")
            continue
        if not literal_key(text["source"], text["case"]):
            report.problems.append(f"{where}: no wildcards in source or case (a case may end in one pytest "
                                   "parameter id such as [FrrDriver], nothing else in brackets)")
            continue
        if text["from"] not in ("FAIL", "UNKNOWN", "MIXED") or text["to"] not in ("MIXED", "PASS") \
                or RANK[text["to"]] <= RANK[text["from"]]:
            report.problems.append(f"{where}: from must be FAIL, UNKNOWN or MIXED and to a higher MIXED or PASS")
            continue
        if len(text["why"].strip()) < MIN_WHY:
            report.problems.append(f"{where}: 'why' must say what changed (at least {MIN_WHY} characters)")
            continue
        ev = [e["evidence"]] if isinstance(e["evidence"], str) else e["evidence"]
        if not isinstance(ev, list) or not ev or not all(isinstance(x, str) and x.strip() for x in ev):
            report.problems.append(f"{where}: evidence must name one or more repository files")
            continue
        # a fixture whose guard test no longer holds may cite the updated test (the reviewer checks it still
        # refuses); everything else cites captures, traces or results, never code
        own_test = fixture_file(text["case"]) if text["source"] == "fixtures" else None
        bad = [x for x in ev if x.startswith(EVIDENCE_NOT_UNDER) or x.startswith(ORACLES + "/") or x not in changed
               or not (tree / x).is_file() or x == text["source"] or (x.endswith(".py") and x != own_test)]
        if bad:
            report.problems.append(f"{where}: evidence must be capture, trace or results files (or, for a fixture, its "
                                   "updated test) that exist at the candidate and changed in this change (not code, "
                                   f"not an oracle, not the allowlist): {', '.join(bad)}")
            continue
        if kind == NEW_READ:
            marker, sep, said = text["reviewed_by"].partition(":")
            if text["source"] != "fixtures" or own_test not in ev:
                report.problems.append(f"{where}: a {NEW_READ} entry is for a fixture flip and cites that test's own "
                                       f"updated file ({own_test or 'a tests/ file'})")
                continue
            if not sep or not SESSION_RE.match(marker.strip()) or len(said.strip()) < 20:
                report.problems.append(f"{where}: a {NEW_READ} entry's reviewed_by is '<session>: <that the updated "
                                       "test asserts the same refusal or verdict>', from a fresh session")
                continue
            if reviewers is not None:
                reviewers.add(marker.strip())
        cited.update(ev)
        keys.append(((text["source"], text["case"], text["from"], text["to"]), kind))
    return keys


_GLOB = "*?[]"


def literal_key(source: str, case: str) -> bool:
    """An entry names exactly one flip, compared by string equality (apply_allowlist), so nothing in it may read as
    a pattern. The one exception: a case may end in a single pytest parameter id, `test_x[FrrDriver]`, because the
    gate itself names parametrised fixture cases that way; its inside holds no glob character and isn't empty."""
    if any(c in source for c in _GLOB):
        return False
    stem, param = case, ""
    if case.endswith("]") and "[" in case:
        i = case.index("[")
        stem, param = case[:i], case[i + 1:-1]
        if not param or any(c in param for c in _GLOB):
            return False
    return bool(stem) and not any(c in stem for c in _GLOB)


def fixture_file(case: str) -> str | None:
    """tests.test_x::test_y[...] -> tests/test_x.py, the only test file a fixture entry may cite."""
    module = case.split("::", 1)[0]
    return module.replace(".", "/") + ".py" if module.startswith("tests.") else None


def separation_problems(repo: Path, base: str, cand: str, report: Report, guarded: set[str],
                        reviewers: set[str] | None = None) -> None:
    """The allowlist is written by someone other than whoever changed the code or the records: every commit touching
    it touches nothing else, and carries a Session marker that no commit changing shipped code, a flipped source or
    the cited evidence carries (and those commits must carry one). A new read's reviewer is such a session too."""
    allow_sessions: dict[str, str | None] = {}
    code_sessions: dict[str, str | None] = {}
    session_files: dict[str, set[str]] = {}
    for sha in rev_list(repo, base, cand):
        files = commit_files(repo, sha)
        s = session_of(repo, sha)
        if s:
            session_files.setdefault(s, set()).update(files)
        if any(f.startswith(ALLOW_DIR + "/") for f in files):
            others = sorted(f for f in files if not f.startswith(ALLOW_DIR + "/"))
            if others or len(parents(repo, sha)) > 1:
                report.problems.append(f"{sha[:10]} changes the allowlist together with other files or in a merge "
                                       f"({', '.join(others[:5])}): an allowlist commit holds nothing else")
            allow_sessions[sha] = session_of(repo, sha)
        if any(shipped(f) or f in guarded or f in GATE_FILES for f in files):
            code_sessions[sha] = session_of(repo, sha)
    for sha, s in {**allow_sessions, **code_sessions}.items():
        if s is None:
            report.problems.append(f"{sha[:10]} has no Session: trailer, so the allowlist's independence can't be shown")
    clash = {a for a in allow_sessions.values() for c in code_sessions.values() if same_session(a, c)}
    if clash:
        report.problems.append(f"the allowlist comes from a session that also changed shipped code, the gate, a "
                               f"flipped record or the cited evidence: {', '.join(sorted(clash))}")
    stale = {r for r in reviewers or () for c in code_sessions.values() if same_session(r, c)}
    if stale:
        report.problems.append(f"a {NEW_READ} entry is reviewed by a session that also changed shipped code, the gate "
                               f"or the cited test in this change (not a fresh session): {', '.join(sorted(stale))}")
    for r in sorted(reviewers or ()):
        files = session_files.get(r)
        if not files:
            report.problems.append(f"a {NEW_READ} entry names reviewer {r}, but no commit in this change carries "
                                   f"Session: {r}: the review is a commit of its own ({REVIEW_DIR}/<name>.md)")
        elif any(not f.startswith(REVIEW_DIR + "/") for f in files):
            other = sorted(f for f in files if not f.startswith(REVIEW_DIR + "/"))
            report.problems.append(f"reviewer {r}'s commits in this change hold more than review records "
                                   f"({', '.join(other[:3])}): a reviewing session only writes {REVIEW_DIR}/")
        if any(same_session(r, a) for a in allow_sessions.values()):
            report.problems.append(f"reviewer {r} also wrote the allowlist: the review comes from another session")


# ------------------------------------------------------------------------------------------------ reproduce-first

def oracle_slug(oid: str) -> str:
    return "test_oracle_" + re.sub(r"[^a-z0-9]", "_", oid.lower())


def oracle_problems(tree: Path, oid: str) -> tuple[list[str], list[str]]:
    """(problems, evidence paths) for tests/oracles/<oid>/ as committed in `tree`."""
    d = tree / ORACLES / oid
    if not d.is_dir():
        return [f"{ORACLES}/{oid}/ does not exist"], []
    problems: list[str] = []
    evidence: list[str] = []
    meta = d / "ORACLE.yml"
    data = load_yaml(meta) if meta.is_file() else None
    if not isinstance(data, dict) or data.get("id") != oid or not str(data.get("bug") or "").strip():
        problems.append(f"{ORACLES}/{oid}/ORACLE.yml must exist and give id: {oid} and a bug: description")
    else:
        ev = [data.get("evidence")] if isinstance(data.get("evidence"), str) else data.get("evidence")
        if not isinstance(ev, list) or not ev or not all(isinstance(x, str) and x.strip() for x in ev):
            problems.append(f"{ORACLES}/{oid}/ORACLE.yml must list evidence: (the real capture, trace or perturbation)")
        else:
            missing = [x for x in ev if not (tree / x).is_file()]
            if missing:
                problems.append(f"{ORACLES}/{oid}/ORACLE.yml names evidence that doesn't exist: {', '.join(missing)}")
            evidence = ev
    tests = sorted(p.name for p in d.rglob("test_*.py"))
    slug = oracle_slug(oid)
    if not tests:
        problems.append(f"{ORACLES}/{oid}/ holds no test_*.py")
    wrong = [t for t in tests if not t.startswith(slug)]
    if wrong:
        problems.append(f"{ORACLES}/{oid}/: test files must be named {slug}*.py (got {', '.join(wrong)})")
    return problems, evidence


def symlink_problems(repo: Path, sha: str, oid: str) -> list[str]:
    """An oracle folder holds plain files only: a symlink (say a conftest.py pointing into src/) would let a fix change
    the oracle without touching tests/oracles/ (Layer 6 on f220469)."""
    out = git(repo, "ls-tree", "-r", sha, "--", f"{ORACLES}/{oid}/")
    links = [ln.split("	", 1)[-1] for ln in out.splitlines() if ln.startswith("120000 ")]
    return [f"{ORACLES}/{oid}/ holds a symlink ({', '.join(links[:3])}): an oracle is plain files"] if links else []


def oracle_ids_touched(files: set[str]) -> set[str]:
    return {f.split("/")[2] for f in files if f.startswith(ORACLES + "/") and f.count("/") >= 3}


def reproduce(repo: Path, rng: str, python: str) -> Report:
    report = Report()
    if rng.count("..") != 1 or "..." in rng:
        raise GateError(f"--range must be BASE..CANDIDATE, got {rng!r}")
    base_ref, cand_ref = rng.split("..")
    base, cand = resolve(repo, base_ref), resolve(repo, cand_ref)
    if base == cand:
        raise GateError(f"the range {rng} is empty: nothing to check")
    commits = rev_list(repo, base, cand)
    info = {sha: (trailers(repo, sha), commit_files(repo, sha), session_of(repo, sha), len(parents(repo, sha)) > 1)
            for sha in commits}
    fixer_sessions: dict[str, set[str]] = {}
    fixes: list[tuple[str, list[str]]] = []
    for sha, (t, files, session, merge) in info.items():
        ids = t.get("fixes-oracle", [])
        bad_ids = [i for i in ids if not ID_RE.match(i)]
        if bad_ids:
            report.problems.append(f"{sha[:10]}: Fixes-Oracle: {bad_ids[0]!r} is not a bug ID like RT-0036")
        ids = [i for i in ids if ID_RE.match(i)]
        if any(shipped(f) for f in files) and not ids:
            reason = " ".join(t.get("no-oracle", []))
            if len(reason) < 20:
                hint = message_problems(git(repo, "show", "-s", "--format=%B", sha))
                report.problems.append(f"{sha[:10]} changes shipped code (src/, action.yml, templates/)"
                                       f"{' in a merge resolution' if merge else ''} without "
                                       "'Fixes-Oracle: <ID>' or 'No-Oracle: <reason, 20+ characters>'"
                                       + (f" in its trailer block ({hint[0]})" if hint else ""))
        if ids and merge:
            report.problems.append(f"{sha[:10]} is a merge: a fix must be its own commit")
            continue
        if ids:
            if session is None:
                report.problems.append(f"{sha[:10]} names Fixes-Oracle but has no Session: trailer")
            for oid in ids:
                fixer_sessions.setdefault(oid, set()).add(session or "")
            fixes.append((sha, ids))
    # every commit in the range that changes an oracle is a pure oracle commit from a non-fixing session
    for sha, (t, files, session, merge) in info.items():
        touched = oracle_ids_touched(files)
        if not touched:
            continue
        if t.get("fixes-oracle") or merge:
            report.problems.append(f"{sha[:10]} changes {ORACLES}/ but is a fix or a merge: oracles change only in "
                                   "oracle commits")
            continue
        for oid in sorted(touched - set(t.get("oracle", []))):
            report.problems.append(f"{sha[:10]} changes {ORACLES}/{oid}/ without the trailer 'Oracle: {oid}'")
        outside = sorted(f for f in files if not f.startswith("tests/"))
        if outside:
            report.problems.append(f"{sha[:10]} is an oracle commit but changes files outside tests/: "
                                   f"{', '.join(outside[:5])}")
        if session is None:
            report.problems.append(f"{sha[:10]} is an oracle commit without a Session: trailer")
    with tempfile.TemporaryDirectory(prefix="ndr-oracle-") as tmp:
        work = Path(tmp)
        trees: dict[str, Path] = {}

        def tree(sha: str) -> Path:
            if sha not in trees:
                trees[sha] = export(repo, sha, work / f"t{len(trees)}")
            return trees[sha]

        def world(oid: str, own: str, evidence: list[str]) -> Path:
            """The range base's tree plus only the oracle's folder and its evidence, as `own` (the last commit that
            wrote the oracle) has them: a harness, conftest or config planted by anyone in the range can't reach it."""
            dest = work / f"w-{oid}-{own[:10]}"
            if not dest.exists():
                shutil.copytree(tree(base), dest, symlinks=True)
                shutil.rmtree(dest / ORACLES / oid, ignore_errors=True)
                shutil.copytree(tree(own) / ORACLES / oid, dest / ORACLES / oid, symlinks=True)
                for rel in evidence:
                    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(tree(own) / rel, dest / rel)
            return dest

        for sha, ids in fixes:
            _, files, session, _ = info[sha]
            parent = parents(repo, sha)[0] if parents(repo, sha) else None
            if parent is None:
                report.problems.append(f"{sha[:10]} is a root commit: no parent to fail on")
                continue
            for oid in ids:
                check_fix(repo, sha, parent, oid, files, session, fixer_sessions, tree, world, python, work, report)
        # every oracle at the candidate holds on the candidate's code, in its own tree
        cand_tree = tree(cand)
        # a fix's plant (it may land after the fix) is the fix's exact reverse, or a port of it that has to exist
        for sha, ids in fixes:
            for oid in ids:
                fix_plant_problems(repo, sha, oid, cand_tree, report)
        here = sorted(d.name for d in (cand_tree / ORACLES).iterdir() if d.is_dir()) \
            if (cand_tree / ORACLES).is_dir() else []
        # an oracle runs forever: one the base held, or one a fix in this range named, must still be at the candidate
        # (Layer 6 on f220469: deleting it after the fix let a No-Oracle commit bring the bug back unseen)
        base_tree = tree(base)
        held = {d.name for d in (base_tree / ORACLES).iterdir() if d.is_dir() and ID_RE.match(d.name)} \
            if (base_tree / ORACLES).is_dir() else set()
        for oid in sorted((held | set(fixer_sessions)) - set(here)):
            report.problems.append(f"oracle {oid} is not at the candidate {cand[:10]}: an oracle stays and runs "
                                   "forever once it exists")
        for oid in here:
            if not ID_RE.match(oid):
                report.problems.append(f"{ORACLES}/{oid}/ is not named by a bug ID")
                continue
            probs, evidence = oracle_problems(cand_tree, oid)
            probs += symlink_problems(repo, cand, oid)
            report.problems += [f"oracle {oid} at the candidate: {p}" for p in probs]
            own = last_touch(repo, cand, f"{ORACLES}/{oid}/")
            if probs or own is None:
                continue
            for h in git(repo, "log", "--format=%H", cand, "--", f"{ORACLES}/{oid}/").split():
                s = session_of(repo, h)
                if s is None or any(same_session(s, f) for f in fixer_sessions.get(oid, set())):
                    report.problems.append(f"oracle {oid}: commit {h[:10]} that wrote it has "
                                           f"{'no Session: trailer' if s is None else f'the fixing session ({s})'}")
            probs, evidence = oracle_problems(tree(own), oid)
            if probs:
                report.problems += [f"oracle {oid} as last written ({own[:10]}): {p}" for p in probs]
                continue
            run = run_pytest(compose(world(oid, own, evidence), cand_tree, work / f"at-{oid}"), [f"{ORACLES}/{oid}"],
                             python, work / "r")
            if run.code != 0 or run.count("passed") != len(run.outcomes):
                report.problems.append(f"oracle {oid} fails on the candidate {cand[:10]} (pytest exit {run.code}): the "
                                       f"bug is back, or the oracle's tree no longer fits the code:\n{run.output[-800:]}")
        report.notes.append(f"{len(commits)} commits, {len(fixes)} fix commits, {len(here)} oracles held at the candidate")
    return report


def check_fix(repo, sha, parent, oid, files, session, fixer_sessions, tree, world, python, work, report) -> None:
    where = f"{sha[:10]} Fixes-Oracle: {oid}"
    own = last_touch(repo, parent, f"{ORACLES}/{oid}/")
    if own is None:
        report.problems.append(f"{where}: {ORACLES}/{oid}/ was not committed before the fix")
        return
    probs, evidence = oracle_problems(tree(own), oid)
    probs += symlink_problems(repo, own, oid)
    if probs:
        report.problems += [f"{where}: {p}" for p in probs]
        return
    if any(f.startswith(ORACLES + "/") for f in files):
        report.problems.append(f"{where}: the fix changes files under {ORACLES}/")
    edited = sorted(set(evidence) & files)
    if edited:
        report.problems.append(f"{where}: the fix edits its oracle's evidence ({', '.join(edited)})")
    adder = git(repo, "log", "--diff-filter=A", "--format=%H", parent, "--", f"{ORACLES}/{oid}/ORACLE.yml").split()
    if not adder or oid not in trailers(repo, adder[-1]).get("oracle", []):
        report.problems.append(f"{where}: the commit that added the oracle lacks the trailer 'Oracle: {oid}'")
    for h in git(repo, "log", "--format=%H", parent, "--", f"{ORACLES}/{oid}/").split():
        s = session_of(repo, h)
        if s is None:
            report.problems.append(f"{where}: oracle commit {h[:10]} has no Session: trailer")
        elif any(same_session(s, f) for f in fixer_sessions.get(oid, set())):
            report.problems.append(f"{where}: oracle commit {h[:10]} is from the fixing session ({s})")
    target = [f"{ORACLES}/{oid}"]
    tag = f"{sha[:8]}-{oid}"
    # judged in the base's tree plus the oracle and its evidence, with only shipped code from parent and fix
    before = run_pytest(compose(world(oid, own, evidence), tree(parent), work / f"b-{tag}"), target, python, work / "r")
    not_assert = sorted(k for k, o in before.outcomes.items()
                        if o != "failed" or not ASSERTION.match(before.messages.get(k, "")))
    if before.code != 1 or not before.outcomes or not_assert:
        report.problems.append(f"{where}: every oracle test must fail on the parent {parent[:10]} with an assertion "
                               f"(pytest exit {before.code}; not an assertion failure: {', '.join(not_assert[:5]) or '-'})")
    after = run_pytest(compose(world(oid, own, evidence), tree(sha), work / f"a-{tag}"), target, python, work / "r")
    if after.code != 0 or after.count("passed") != len(after.outcomes):
        report.problems.append(f"{where}: the oracle must pass on the fix (pytest exit {after.code}, "
                               f"{after.count('failed')} failed, {after.count('error')} errors, "
                               f"{after.count('skipped')} skipped)")
    report.notes.append(f"{where}: fails on {parent[:10]}, checked against the fix (oracle as of {own[:10]}, harness from the base)")


# ------------------------------------------------------------------------------------------------ living plants

_MISSING = object()


def oracle_meta(tree: Path, oid: str) -> dict:
    meta = tree / ORACLES / oid / "ORACLE.yml"
    data = load_yaml(meta) if meta.is_file() else None
    return data if isinstance(data, dict) else {}


def is_ancestor(repo: Path, a: str, b: str) -> bool:
    if shutil.which("git") is None:
        raise GateError("git is not available: the check can't run here (fail-closed)")
    p = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", a, b], capture_output=True)
    if p.returncode not in (0, 1):
        raise GateError(f"git merge-base --is-ancestor {a[:10]} {b[:10]} failed: {p.stderr.decode(errors='replace')[:300]}")
    return p.returncode == 0


def show(repo: Path, sha: str, rel: str) -> str | None:
    """A file as committed at `sha`, or None when it isn't there."""
    p = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{rel}"], capture_output=True)
    return p.stdout.decode("utf-8", errors="replace") if p.returncode == 0 else None


def fixes_by_oracle(repo: Path, cand: str) -> dict[str, list[str]]:
    """Oracle ID -> the commits in the candidate's history whose trailer says Fixes-Oracle: <ID>, newest first."""
    out = git(repo, "log", "--format=%x1e%H%x00%(trailers:key=Fixes-Oracle,valueonly,unfold)", cand)
    found: dict[str, list[str]] = {}
    for rec in out.split("\x1e"):
        sha, _, rest = rec.partition("\0")
        for v in rest.splitlines():
            if v.strip() and sha.strip():
                found.setdefault(v.strip(), []).append(sha.strip())
    return found


def plant_rule_commit(repo: Path, cand: str) -> str | None:
    """The commit that brought plants: the oldest in the candidate's history that writes a `plant:` line into an
    ORACLE.yml. Only an oracle fixed before it may say `plant: none`."""
    out = git(repo, "log", "--format=%H", "--reverse", "--topo-order", "-G", "^plant:", cand, "--",
              f":(glob){ORACLES}/*/ORACLE.yml").split()
    return out[0] if out else None


def normalise_diff(text: str) -> str:
    """A diff as compared for equality: LF line ends, no `index` lines (abbreviation length and modes vary)."""
    lines = [ln.rstrip("\r") for ln in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(ln for ln in lines if not ln.startswith("index ")).rstrip("\n") + "\n"


def reverse_of(repo: Path, fix: str) -> str:
    """The fix's shipped diff reversed (git diff <fix> <fix>^ -- src action.yml templates), in one fixed format."""
    ps = parents(repo, fix)
    if not ps:
        raise GateError(f"{fix[:10]} is a root commit: it has no reverse")
    return normalise_diff(git(repo, "-c", "core.quotepath=off", "diff", "--no-color", "--no-ext-diff", "--no-textconv",
                              "--no-renames", "--no-relative", "-U3", "--diff-algorithm=myers", "--indent-heuristic",
                              "--src-prefix=a/", "--dst-prefix=b/", fix, ps[0], "--", *SHIPPED_PATHS))


_DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
_FILE_LINE = re.compile(r"^(---|\+\+\+) (?:(?:a|b)/(\S+)|/dev/null)$")


def plant_shape_problems(text: str) -> list[str]:
    """A plant changes shipped text files only: no binary patch, rename, copy, mode change or symlink."""
    if "diff --git " not in text:
        return ["holds no diff"]
    problems = []
    for ln in text.splitlines():
        if ln.startswith("diff --git "):
            m = _DIFF_HEADER.match(ln)
            if not m or m.group(1) != m.group(2) or not shipped(m.group(1)):
                problems.append(f"changes something that doesn't ship ({ln[11:90]}): a plant is src/, action.yml or "
                                "templates/ only")
        elif ln.startswith(("--- ", "+++ ")):
            m = _FILE_LINE.match(ln)
            if not m or (m.group(2) and not shipped(m.group(2))):
                problems.append(f"names a file that doesn't ship ({ln[:90]})")
        elif ln.startswith(("GIT binary patch", "Binary files ", "rename ", "copy ", "old mode ", "new mode ",
                            "similarity index ")) or re.match(r"^(new|deleted) file mode (?!100644$|100755$)", ln):
            problems.append(f"holds '{ln[:40]}': a plant changes text files only")
    return problems


_RISKY = re.compile(r"\b(assert|raise)\b|AssertionError")


def added_lines(text: str) -> list[str]:
    return [ln[1:].strip() for ln in text.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def diff_files(text: str) -> set[str]:
    return {m.group(1) for m in map(_DIFF_HEADER.match, text.splitlines()) if m}


def port_problems(text: str, exact: str) -> list[str]:
    """A port re-creates its fix's reverse on moved code: it changes only files the fix changed, and every assert or
    raise it adds is one the exact reverse adds too (a plant brings the bug back; it doesn't fail on purpose)."""
    out = []
    extra = sorted(diff_files(text) - diff_files(exact))
    if extra:
        out.append(f"is a port that changes files its fix didn't ({', '.join(extra[:3])})")
    allowed = set(added_lines(exact))
    risky = [ln for ln in added_lines(text) if _RISKY.search(ln) and ln not in allowed]
    if risky:
        out.append(f"is a port that adds an assert or raise its fix's reverse doesn't have ({risky[0][:80]})")
    return out


_FRAME = re.compile(r"^(\S+?\.py):\d+: ", re.M)


def raising_file(detail: str) -> str | None:
    """The file of the innermost frame in a pytest traceback (`path.py:LINE: ...` lines), as a POSIX path."""
    frames = _FRAME.findall(detail or "")
    return frames[-1].replace("\\", "/") if frames else None


def git_apply(tree: Path, patch: Path, check: bool) -> tuple[bool, str]:
    """git apply inside an exported tree (no repository: discovery stops at the tree)."""
    if shutil.which("git") is None:
        raise GateError("git is not available: the check can't run here (fail-closed)")
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tree.resolve().parent)}
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    p = subprocess.run(["git", "apply", "--whitespace=nowarn", *(["--check"] if check else []), str(patch)],
                       cwd=tree, env=env, capture_output=True)
    return p.returncode == 0, p.stderr.decode(errors="replace").strip()[-300:]


def applies(tree: Path, text: str, work: Path) -> bool:
    patch = work / f"probe-{len(list(work.glob('probe-*')))}.diff"
    patch.write_text(text, encoding="utf-8", newline="\n")
    return git_apply(tree, patch, check=True)[0]


def plant_registry(repo: Path, cand: str, tree: Path, oid: str, fixes: dict[str, list[str]], rule: str | None,
                   work: Path, report: Report, summary: dict) -> str | None:
    """The oracle's plant entry at the candidate; returns the plant's text when it has one to run."""
    meta = oracle_meta(tree, oid)
    plant = meta.get("plant", _MISSING)
    mine = fixes.get(oid, [])
    where = f"oracle {oid}"
    if plant is _MISSING:
        if mine:
            report.problems.append(f"{where} is fixed ({mine[0][:10]}) but its ORACLE.yml names no plant: write "
                                   f"plant: {PLANT} (the fix's reverse)")
        else:
            summary["pending"].append(oid)    # a new oracle: its plant comes after its fix
        return None
    if plant == "none":
        why = meta.get("plant_why")
        if not isinstance(why, str) or len(why.strip()) < MIN_WHY:
            report.problems.append(f"{where}: plant: none needs plant_why: (at least {MIN_WHY} characters)")
        if not mine:
            report.problems.append(f"{where}: plant: none on an oracle with no fix yet; a new oracle gets its plant "
                                   "with its fix, and only an oracle fixed before plants were required may have none")
        elif rule is None or not all(is_ancestor(repo, f, rule) for f in mine):
            report.problems.append(f"{where}: plant: none is only for oracles fixed before plants were required; this "
                                   f"fix ({mine[0][:10]}) is newer, so it needs plant: {PLANT}")
        if (tree / ORACLES / oid / PLANT).exists():
            report.problems.append(f"{where}: says plant: none but holds a {PLANT}")
        summary["not_applicable"].append(oid)
        return None
    if plant != PLANT:
        report.problems.append(f"{where}: plant: must be {PLANT} or none, got {plant!r}")
        return None
    path = tree / ORACLES / oid / PLANT
    probs = symlink_problems(repo, cand, oid)
    if not path.is_file() or path.is_symlink():
        probs.append(f"{ORACLES}/{oid}/{PLANT} is missing or not a plain file")
    report.problems += [f"{where}: {p}" for p in probs]
    if probs:
        return None
    if not mine:
        report.problems.append(f"{where}: has a plant but no fix commit names it (Fixes-Oracle: {oid}): a plant is "
                               "the reverse of a fix, so it can't come first")
        return None
    text = normalise_diff(path.read_text(encoding="utf-8", errors="replace"))
    shape = plant_shape_problems(text)
    if shape:
        report.problems += [f"{where}: {PLANT} {p}" for p in shape]
        return None
    exact = {f: reverse_of(repo, f) for f in mine}
    ported = meta.get("ported_from")
    if ported is None:
        if text not in exact.values():
            report.problems.append(f"{where}: plant is not the fix's exact reverse (git diff {mine[0][:10]} "
                                   f"{mine[0][:10]}^ -- src action.yml templates); a plant ported by hand says "
                                   "ported_from: <the fix's sha>")
            return None
    else:
        try:
            src = resolve(repo, str(ported))
        except GateError:
            src = None
        if src not in exact:
            report.problems.append(f"{where}: ported_from: {ported} is not a commit that fixes it "
                                   f"({', '.join(f[:10] for f in mine)})")
            return None
        if applies(tree, exact[src], work):
            report.problems.append(f"{where}: the plant is ported from {src[:10]}, but that fix's exact reverse still "
                                   "applies to the candidate: use it (a plant can't be traded for an easier one)")
            return None
        port = port_problems(text, exact[src])
        if port:
            report.problems += [f"{where}: {PLANT} {p}" for p in port]
            return None
    return text


def reported_guard(repo: Path, base: str, cand: str, cand_tree: Path, ids: list[str], work: Path,
                   report: Report) -> None:
    """A plant changed in this change must have stopped applying first: the old one may not still apply to the
    candidate (no trading a plant for an easier one), and the re-port comes from a session that changed no shipped
    code in this change (it is a change to the gate's own evidence)."""
    commits = rev_list(repo, base, cand)
    code_sessions = {session_of(repo, s) for s in commits if any(shipped(f) for f in commit_files(repo, s))}
    for oid in ids:
        rel = f"{ORACLES}/{oid}/{PLANT}"
        old = show(repo, base, rel)
        if old is None:
            continue
        new = cand_tree / rel
        if new.is_file() and normalise_diff(new.read_text(encoding="utf-8", errors="replace")) == normalise_diff(old):
            continue
        if not new.is_file():
            report.problems.append(f"plant {oid} was removed in this change: a plant stays once it exists")
            continue
        if applies(cand_tree, normalise_diff(old), work):
            report.problems.append(f"plant {oid} swapped while the old one still applies: re-port only a plant that "
                                   "no longer applies")
        for sha in git(repo, "log", "--format=%H", f"{base}..{cand}", "--", rel).split():
            s = session_of(repo, sha)
            if s is None:
                report.problems.append(f"plant {oid}: {sha[:10]} re-ports it without a Session: trailer")
            elif s in code_sessions:
                report.problems.append(f"plant {oid}: {sha[:10]} re-ports it from a session that changed shipped code "
                                       f"in this change ({s}); the re-port comes from another session")


def plants_world(base_tree: Path, cand_tree: Path, ids: list[str], dest: Path) -> Path:
    """The base's tree (harness, conftest, config) with the candidate's oracle folders and their evidence."""
    shutil.copytree(base_tree, dest, symlinks=True)
    for oid in ids:
        shutil.rmtree(dest / ORACLES / oid, ignore_errors=True)
        shutil.copytree(cand_tree / ORACLES / oid, dest / ORACLES / oid, symlinks=True)
        ev = oracle_meta(cand_tree, oid).get("evidence")
        for rel in ([ev] if isinstance(ev, str) else ev if isinstance(ev, list) else []):
            if isinstance(rel, str) and (rel.startswith(("/", "\\")) or ":" in rel or ".." in rel.replace("\\", "/").split("/")):
                raise GateError(f"{ORACLES}/{oid}/ORACLE.yml: evidence {rel!r} is not a path inside the repository")
            if isinstance(rel, str) and (cand_tree / rel).is_file():
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cand_tree / rel, dest / rel)
    return dest


def oracle_nodes(run: PytestRun, oid: str) -> dict[str, str]:
    prefix = f"{ORACLES.replace('/', '.')}.{oid}."
    return {k: o for k, o in run.outcomes.items() if k.startswith(prefix)}


def plants(repo: Path, cand_ref: str, python: str, base_ref: str | None = None) -> tuple[Report, dict]:
    """Every oracle's plant still applies to the candidate and its oracle still catches it by an assertion, and
    the candidate without the plant passes. With a base: the re-port guard over base..candidate."""
    report = Report()
    cand = resolve(repo, cand_ref)
    base = resolve(repo, base_ref) if base_ref else None
    summary: dict = {"candidate": cand, "base": base, "caught": 0, "applied": 0, "total": 0, "not_applicable": [],
                     "pending": [], "pending_since_base": [], "owed_ports": 0, "oracles": {}}
    with tempfile.TemporaryDirectory(prefix="ndr-plants-") as tmp:
        work = Path(tmp)
        cand_tree = export(repo, cand, work / "cand")
        root = cand_tree / ORACLES
        ids = sorted(d.name for d in root.iterdir() if d.is_dir() and ID_RE.match(d.name)) if root.is_dir() else []
        fixes = fixes_by_oracle(repo, cand)
        rule = plant_rule_commit(repo, cand)
        texts: dict[str, str] = {}
        for oid in ids:
            text = plant_registry(repo, cand, cand_tree, oid, fixes, rule, work, report, summary)
            if text is not None:
                texts[oid] = text
        summary["total"] = len(texts)
        summary["owed_ports"] = len(summary["not_applicable"])
        if base is not None:
            reported_guard(repo, base, cand, cand_tree, ids, work, report)
            # an oracle with no fix that the base already held: nothing has shown it fails on buggy code
            summary["pending_since_base"] = [o for o in summary["pending"]
                                             if show(repo, base, f"{ORACLES}/{o}/ORACLE.yml") is not None]
        world = cand_tree if base is None else plants_world(export(repo, base, work / "base"), cand_tree,
                                                            sorted(texts), work / "world")
        # the candidate as it is passes every planted oracle (reproduce checks this too; re-asserted here)
        if texts:
            clean = run_pytest(compose(world, cand_tree, work / "clean"), [f"{ORACLES}/{o}" for o in texts], python,
                               work / "r")
            for oid in texts:
                nodes = oracle_nodes(clean, oid)
                if not nodes or any(o != "passed" for o in nodes.values()):
                    report.problems.append(f"oracle {oid} doesn't pass on the candidate without its plant "
                                           f"(pytest exit {clean.code})")
        groups: dict[str, list[str]] = {}
        for oid, text in texts.items():
            groups.setdefault(text, []).append(oid)
        for i, (text, oids) in enumerate(groups.items()):
            code = work / f"planted-{i}"
            shutil.copytree(cand_tree, code, symlinks=True)
            patch = work / f"plant-{i}.diff"
            patch.write_text(text, encoding="utf-8", newline="\n")
            ok, err = git_apply(code, patch, check=True)
            if not ok:
                for oid in oids:
                    summary["oracles"][oid] = "does not apply"
                    report.problems.append(f"plant {oid} no longer applies; re-port it in this change ({err})")
                continue
            ok, err = git_apply(code, patch, check=False)
            if not ok:
                raise GateError(f"plant {', '.join(oids)}: git apply failed after its check passed ({err})")
            summary["applied"] += len(oids)
            run = run_pytest(compose(world, code, work / f"m-{i}"), [f"{ORACLES}/{o}" for o in oids], python,
                             work / "r")
            for oid in oids:
                nodes = oracle_nodes(run, oid)
                passed = sorted(k for k, o in nodes.items() if o == "passed")
                broken = sorted(k for k, o in nodes.items()
                                if o != "passed" and (o != "failed" or not ASSERTION.match(run.messages.get(k, ""))))
                # caught means the oracle's own assertion fired: not one the plant put in the code, not a fake's refusal
                own = f"{ORACLES}/{oid}/"
                elsewhere = sorted(k for k, o in nodes.items() if o == "failed" and k not in broken and (
                    "unexpected command" in run.messages.get(k, "")
                    or not (raising_file(run.details.get(k, "")) or "").startswith(own)))
                if passed:
                    summary["oracles"][oid] = "not caught"
                    report.problems.append(f"oracle {oid} no longer catches its bug: with the plant applied "
                                           f"{', '.join(passed[:3])} pass")
                elif run.code not in (0, 1) or not nodes or broken:
                    summary["oracles"][oid] = "breaks the build"
                    report.problems.append(f"plant {oid} breaks the build, not the verdict (pytest exit {run.code}; "
                                           f"not an assertion: {', '.join(broken[:3]) or 'no test ran'}):\n"
                                           f"{run.output[-600:]}")
                elif elsewhere:
                    summary["oracles"][oid] = "caught elsewhere"
                    report.problems.append(
                        f"oracle {oid}: with the plant applied {', '.join(elsewhere[:3])} fail, but not by an assertion "
                        f"raised in {own} (raised in {raising_file(run.details.get(elsewhere[0], '')) or 'an unknown place'}"
                        "; or a fake's refusal): a plant is caught by the oracle's own assertion")
                else:
                    summary["oracles"][oid] = "caught"
                    summary["caught"] += 1
        report.notes.append(f"plants: {summary['caught']} caught of {summary['total']} ({summary['applied']} applied); "
                            f"plant: none {len(summary['not_applicable'])} (owed ports); no fix yet "
                            f"{len(summary['pending'])}, {len(summary['pending_since_base'])} of them since the base")
    return report, summary


def fix_plant_problems(repo: Path, fix: str, oid: str, cand_tree: Path, report: Report) -> None:
    """For a fix in the range: the candidate's plant for it is the fix's exact reverse, or a port of it (ported_from
    the fix) made because the exact reverse no longer applies. plant: none is for older fixes only."""
    where = f"{fix[:10]} Fixes-Oracle: {oid}"
    meta = oracle_meta(cand_tree, oid)
    plant = meta.get("plant", _MISSING)
    if plant is _MISSING:
        report.notes.append(f"{where}: no plant at the candidate yet (static at --candidate requires it)")
        return
    if plant != PLANT:
        report.problems.append(f"{where}: plant: {plant!r} for a fix in this change; it needs plant: {PLANT}, the "
                               "fix's exact reverse")
        return
    path = cand_tree / ORACLES / oid / PLANT
    if not path.is_file() or path.is_symlink():
        report.problems.append(f"{where}: {ORACLES}/{oid}/{PLANT} is missing or not a plain file")
        return
    text = normalise_diff(path.read_text(encoding="utf-8", errors="replace"))
    exact = reverse_of(repo, fix)
    if text == exact:
        report.notes.append(f"{where}: the plant is the fix's exact reverse")
        return
    ported = meta.get("ported_from")
    try:
        src = resolve(repo, str(ported)) if ported else None
    except GateError:
        src = None
    if src == fix:
        with tempfile.TemporaryDirectory(prefix="ndr-probe-") as tmp:
            if not applies(cand_tree, exact, Path(tmp)):
                port = port_problems(text, exact)
                if port:
                    report.problems += [f"{where}: {PLANT} {p}" for p in port]
                else:
                    report.notes.append(f"{where}: the plant is a port (the exact reverse no longer applies)")
                return
    report.problems.append(f"{where}: plant is not the fix's exact reverse (git diff {fix[:10]} {fix[:10]}^ -- src "
                           "action.yml templates)")


# ------------------------------------------------------------------------------------------------ cli

def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def finish(name: str, report: Report) -> int:
    for n in report.notes:
        print(f"  {n}")
    for f in report.flips:
        print(f"BLOCKED loosening flip with no reviewed allowlist entry: {f}")
    if any(f.source == "fixtures" for f in report.flips):
        print("  (fixtures: the base's guard test no longer holds on the candidate's code. It counts as PASS because "
              "the gate can't tell a pass from a changed status such as failed -> error; read the test's failure, and "
              "if the tool still refuses, allow it citing the updated test as evidence)")
    for p in report.problems:
        print(f"BLOCKED {p}")
    if report.flips or report.problems:
        print(f"{name}: BLOCKED ({len(report.flips)} unexplained flip(s), {len(report.problems)} problem(s))")
        return BLOCKED
    print(f"{name}: clean")
    return OK


GATE_TRAILERS = ("Fixes-Oracle", "No-Oracle", "Oracle", "Session")
_GATE_LINE = re.compile(r"^(" + "|".join(GATE_TRAILERS) + r")\s*:", re.I)
_TRAILER_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*:\s*\S")


def message_problems(text: str) -> list[str]:
    """A commit message whose gate trailers git won't read. Git reads trailers only from the last paragraph, and only
    when that paragraph is all trailers: a `Fixes-Oracle:` line in the body is invisible to `reproduce` (897f1e2 and
    ca9d984 on PR #6 put Fixes-Oracle and Session in separate `-m` paragraphs). A Fixes-Oracle or Oracle value must be
    one bug ID (0306e3c's 'Fixes-Oracle: <review name> MINOR-1,2,3,6' named none). No git needed: a commit-msg hook."""
    lines = [ln.rstrip() for ln in text.splitlines() if not ln.startswith("#")]
    paras, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    if len(paras) < 2:
        return []   # a subject only: no trailers to place (reproduce says what a src commit is missing)
    body, last = paras[1:-1], paras[-1]
    problems = [f"'{ln.split(':')[0]}:' is in the message body, not the trailer block: git reads trailers only from "
                "the last paragraph, so the gate won't see it. Put every trailer together at the end, one per line"
                for p in body for ln in p if _GATE_LINE.match(ln)]
    if any(_GATE_LINE.match(ln) for ln in last):
        odd = [ln for ln in last if not _TRAILER_LINE.match(ln) and not ln.startswith((" ", "\t"))]
        if odd:
            problems.append(f"the trailer block also holds {odd[0][:60]!r}, which isn't a trailer: git may not read the "
                            "block at all. Keep the last paragraph to `Key: value` lines")
        for ln in last:
            key, _, value = ln.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key in ("fixes-oracle", "oracle") and not ID_RE.match(value):
                problems.append(f"'{key.title()}: {value[:60]}' doesn't name one bug ID (such as FP-043-UNNSESSCHK or "
                                "RT-0036): one ID per trailer line, nothing else on it")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("loosening", help="block unexplained FAIL/UNKNOWN -> PASS between two commits")
    a.add_argument("--repo", required=True)
    a.add_argument("--base", required=True)
    a.add_argument("--candidate", default="HEAD")
    a.add_argument("--python", default=sys.executable)
    a.add_argument("--json", metavar="PATH", help="also write the comparison (every flip, allowed or not) as JSON")
    a.add_argument("--dominance", action="store_true",
                   help="the base is the published release: an allowlist entry matching no flip is only noted")
    b = sub.add_parser("loosening-files", help="the same for two corpus results.json files, no git")
    b.add_argument("--base", required=True)
    b.add_argument("--candidate", required=True)
    c = sub.add_parser("reproduce", help="fix commits need an earlier, independent, failing-then-passing oracle")
    c.add_argument("--repo", required=True)
    c.add_argument("--range", required=True)
    c.add_argument("--python", default=sys.executable)
    e = sub.add_parser("plants", help="every oracle's plant still applies and its oracle still catches it")
    e.add_argument("--repo", required=True)
    e.add_argument("--candidate", default="HEAD")
    e.add_argument("--base", help="the change's base: also guard re-ported plants over base..candidate")
    e.add_argument("--json", metavar="PATH", help="also write {caught, applied, total, not_applicable, ...} as JSON")
    e.add_argument("--python", default=sys.executable)
    d = sub.add_parser("check-message", help="a commit message's gate trailers are where git reads them (commit-msg)")
    d.add_argument("file")
    args = ap.parse_args(argv)
    if args.cmd == "check-message":
        try:
            problems = message_problems(Path(args.file).read_text(encoding="utf-8", errors="replace"))
        except OSError as e:
            print(f"ERROR cannot read the commit message: {e}")
            return ERROR
        for p in problems:
            print(f"BLOCKED {p}")
        return BLOCKED if problems else OK
    try:
        if args.cmd == "loosening":
            report = loosening(Path(args.repo).resolve(), args.base, args.candidate, args.python, args.dominance)
            if args.json:
                write_json(Path(args.json), report.as_json())
            return finish("loosening", report)
        if args.cmd == "plants":
            report, summary = plants(Path(args.repo).resolve(), args.candidate, args.python, args.base)
            if args.json:
                write_json(Path(args.json), {**summary, "problems": report.problems})
            return finish("plants", report)
        if args.cmd == "loosening-files":
            report = Report()
            compare_corpus_files(Path(args.base), Path(args.candidate), "corpus", report)
            return finish("loosening-files", report)
        return finish("reproduce", reproduce(Path(args.repo).resolve(), args.range, args.python))
    except GateError as e:
        print(f"ERROR {e}")
        return ERROR
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"ERROR {type(e).__name__}: {e}")
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
