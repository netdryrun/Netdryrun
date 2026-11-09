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
CHILD_ENV_DROP = ("MUTANT_UNDER_TEST", "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONSTARTUP", "PYTHONHOME",
                  "PYTEST_CURRENT_TEST", "PYTHONPATH")
ASSERTION = re.compile(r"^(assert\b|AssertionError\b)")


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

    def __str__(self) -> str:
        return f"{self.source} :: {self.case}: {self.before} -> {self.after}"


@dataclass
class Report:
    flips: list[Flip] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)     # each one blocks
    notes: list[str] = field(default_factory=list)

    def compare(self, source: str, base: dict[str, str], cand: dict[str, str]) -> None:
        """Per case, never in aggregate. A case judged at the base and not at the candidate blocks."""
        for case in sorted(base):
            if case not in cand:
                self.problems.append(f"{source} :: {case}: judged at the base, not at the candidate (removed, renamed "
                                     "or not run): a missing verdict is not a pass")
            elif RANK[cand[case]] > RANK[base[case]]:
                self.flips.append(Flip(source, case, base[case], cand[case]))
        self.notes.append(f"{source}: {len(base)} cases compared")


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
        bad = [v for v in seen if v not in CORPUS_VERDICTS]
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
    """`world`'s whole tree (tests, fixtures, data, advisories, pyproject, conftest) with only `code`'s src/
    packages swapped in, and only the package names `world` has: nothing else from the code under test can reach
    the run (no root conftest, no pytest config, no src/sitecustomize.py or src/pytest.py shadowing a tool)."""
    names = packages(world)
    if not names:
        raise GateError(f"{world.name}: no package under src/ to judge")
    shutil.copytree(world, dest, symlinks=True)
    shutil.rmtree(dest / "src")
    (dest / "src").mkdir()
    for n in names:
        if (code / "src" / n / "__init__.py").is_file():
            shutil.copytree(code / "src" / n, dest / "src" / n, symlinks=True)
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

    def count(self, outcome: str) -> int:
        return sum(1 for o in self.outcomes.values() if o == outcome)


def run_pytest(tree: Path, targets: list[str], python: str, work: Path) -> PytestRun:
    """pytest on `targets` inside `tree`, configured by the tree's own pyproject.toml (the world's), report written
    outside the tree. Exit code and report must agree."""
    preflight(tree, python)
    work.mkdir(parents=True, exist_ok=True)
    xml = work / f"junit-{len(list(work.glob('junit-*.xml')))}.xml"
    ini = tree / "pyproject.toml"
    if not ini.is_file():
        ini = work / "empty.ini"
        ini.write_text("[pytest]\n", encoding="utf-8")
    cmd = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "-c", str(ini),
           "--rootdir", str(tree), "--confcutdir", str(tree), f"--junitxml={xml}", "--", *targets]
    p = subprocess.run(cmd, cwd=tree, env=child_env(tree), capture_output=True, text=True, timeout=1800)
    outcomes: dict[str, str] = {}
    messages: dict[str, str] = {}
    if xml.is_file():
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError as e:
            raise GateError(f"pytest's report is unreadable ({e})") from None
        for tc in root.iter("testcase"):
            key = f"{tc.get('classname', '')}::{tc.get('name', '')}"
            kid = next(iter(tc), None)
            kinds = {c.tag for c in tc} & {"failure", "error", "skipped"}
            outcome = ("failed" if "failure" in kinds else "error" if "error" in kinds
                       else "skipped" if "skipped" in kinds else "passed")
            if outcomes.get(key, "passed") == "passed":   # reported twice (call, teardown): keep the worse
                outcomes[key] = outcome
                messages[key] = (kid.get("message") or "") if kid is not None else ""
    out = (p.stdout + p.stderr)[-3000:]
    bad = sum(o in ("failed", "error") for o in outcomes.values())
    if p.returncode == 0 and (bad or not outcomes):
        raise GateError(f"pytest exited 0 but its report shows {bad} failed of {len(outcomes)}:\n{out[-800:]}")
    if p.returncode == 1 and not bad:
        raise GateError(f"pytest exited 1 but its report shows no failure:\n{out[-800:]}")
    return PytestRun(p.returncode, outcomes, messages, out)


# ------------------------------------------------------------------------------------------------ loosening (git)

def fixture_targets(base_tree: Path) -> list[str]:
    """The must-not-pass fixtures as the BASE has them: the red team, the tests its pinned cases name, every test
    the known-false-pass list names, and every committed oracle."""
    if not (base_tree / REDTEAM_TARGET).is_file():
        raise GateError(f"the base has no {REDTEAM_TARGET}")
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
    kfp = base_tree / KNOWN_FALSE_PASSES
    if kfp.is_file():
        entries = load_yaml(kfp)
        if not isinstance(entries, list):
            raise GateError(f"{KNOWN_FALSE_PASSES}: not a list")
        for e in entries:
            if not isinstance(e, dict):
                raise GateError(f"{KNOWN_FALSE_PASSES}: an entry is not a mapping")
            targets += [_target(t, KNOWN_FALSE_PASSES) for t in e.get("tests") or []]
    oracles = base_tree / ORACLES
    if oracles.is_dir():
        targets += [f"{ORACLES}/{d.name}" for d in sorted(oracles.iterdir()) if d.is_dir() and ID_RE.match(d.name)]
    return list(dict.fromkeys(targets))


def _target(t: object, where: str) -> str:
    if not isinstance(t, str) or not t.startswith("tests/") or ".." in t.split("::")[0]:
        raise GateError(f"{where}: bad test target {t!r}")
    return t


def fixture_compare(base_run: PytestRun, cand_run: PytestRun, report: Report) -> None:
    """A passing fixture test means the tool refused the bad input (not PASS). On the candidate anything else
    (failed, error, skipped) counts as PASS: fail-closed. A test red or skipped at the base is a red baseline."""
    red = sorted(k for k, o in base_run.outcomes.items() if o != "passed")
    if red or base_run.code != 0:
        report.problems.append(f"the baseline is red: {len(red)} fixture test(s) don't pass on the base itself "
                               f"(pytest exit {base_run.code}): {', '.join(red[:5])}")
    if cand_run.code not in (0, 1):
        report.problems.append(f"the base's fixtures did not run cleanly on the candidate's code (pytest exit "
                               f"{cand_run.code}; a collection error, or a dependency the candidate needs):\n"
                               f"{cand_run.output[-1200:]}")
    base_v = {k: "FAIL" for k, o in base_run.outcomes.items() if o == "passed"}
    cand_v = {k: "FAIL" if o == "passed" else "PASS" for k, o in cand_run.outcomes.items()}
    report.compare("fixtures", base_v, cand_v)


def loosening(repo: Path, base_ref: str, cand_ref: str, python: str) -> Report:
    report = Report()
    base, cand = resolve(repo, base_ref), resolve(repo, cand_ref)
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
        # 2. must-not-pass fixtures: the base's world with the base's code, then with the candidate's code
        targets = fixture_targets(base_tree)
        base_run = run_pytest(base_tree, targets, python, work / "r")
        cand_run = run_pytest(compose(base_tree, cand_tree, work / "mixed"), targets, python, work / "r")
        fixture_compare(base_run, cand_run, report)
        report.notes.append(f"fixture targets ({len(targets)}): {', '.join(targets)}")
        # 3. the allowlist
        apply_allowlist(repo, base, cand, cand_tree, report)
    return report


def apply_allowlist(repo: Path, base: str, cand: str, cand_tree: Path, report: Report) -> None:
    changed = changed_files(repo, base, cand)
    files = sorted(f for f in changed if f.startswith(ALLOW_DIR + "/") and (cand_tree / f).is_file())
    if not files:
        return
    flips = {(f.source, f.case, f.before, f.after): f for f in report.flips}
    used = set()
    for f in files:
        for key in allow_entries(f, cand_tree, changed, report):
            if key in flips:
                used.add(key)
                report.notes.append(f"allowed by {f}: {flips[key]}")
            else:
                report.problems.append(f"{f}: allows {key[0]} :: {key[1]} {key[2]} -> {key[3]}, which is not a flip "
                                       "in this change (stale or pre-loaded entries block)")
    report.flips = [fl for k, fl in flips.items() if k not in used]
    separation_problems(repo, base, cand, report)


def allow_entries(f: str, tree: Path, changed: set[str], report: Report) -> list[tuple[str, str, str, str]]:
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
        if not isinstance(e, dict) or set(e) != ALLOW_KEYS:
            report.problems.append(f"{where}: keys must be exactly {sorted(ALLOW_KEYS)}")
            continue
        text = {k: e[k] for k in ALLOW_KEYS - {"evidence"}}
        if not all(isinstance(v, str) and v.strip() for v in text.values()):
            report.problems.append(f"{where}: source, case, from, to, why and reviewed_by must be non-empty text")
            continue
        if any(c in text["source"] + text["case"] for c in "*?["):
            report.problems.append(f"{where}: no wildcards in source or case")
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
        test_ok = text["source"] == "fixtures"
        bad = [x for x in ev if x.startswith(EVIDENCE_NOT_UNDER) or x.startswith(ORACLES + "/") or x not in changed
               or not (tree / x).is_file() or (x.endswith(".py") and not (test_ok and x.startswith("tests/")))]
        if bad:
            report.problems.append(f"{where}: evidence must be capture, trace or results files (or, for a fixture, its "
                                   "updated test) that exist at the candidate and changed in this change (not code, "
                                   f"not an oracle, not the allowlist): {', '.join(bad)}")
            continue
        keys.append((text["source"], text["case"], text["from"], text["to"]))
    return keys


def separation_problems(repo: Path, base: str, cand: str, report: Report) -> None:
    """The allowlist is written by someone other than whoever changed the code: every commit touching it touches
    nothing else, and carries a Session marker no commit changing src/ in this change carries."""
    allow_sessions: dict[str, str | None] = {}
    code_sessions: dict[str, str | None] = {}
    for sha in rev_list(repo, base, cand):
        files = commit_files(repo, sha)
        if any(f.startswith(ALLOW_DIR + "/") for f in files):
            others = sorted(f for f in files if not f.startswith(ALLOW_DIR + "/"))
            if others or len(parents(repo, sha)) > 1:
                report.problems.append(f"{sha[:10]} changes the allowlist together with other files or in a merge "
                                       f"({', '.join(others[:5])}): an allowlist commit holds nothing else")
            allow_sessions[sha] = session_of(repo, sha)
        if any(f.startswith("src/") for f in files):
            code_sessions[sha] = session_of(repo, sha)
    for sha, s in {**allow_sessions, **code_sessions}.items():
        if s is None:
            report.problems.append(f"{sha[:10]} has no Session: trailer, so the allowlist's independence can't be shown")
    clash = {s for s in allow_sessions.values() if s} & {s for s in code_sessions.values() if s}
    if clash:
        report.problems.append(f"the allowlist comes from a session that also changed src/: {', '.join(sorted(clash))}")


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
    tests = sorted(p.name for p in d.glob("test_*.py"))
    slug = oracle_slug(oid)
    if not tests:
        problems.append(f"{ORACLES}/{oid}/ holds no test_*.py")
    wrong = [t for t in tests if not t.startswith(slug)]
    if wrong:
        problems.append(f"{ORACLES}/{oid}/: test files must be named {slug}*.py (got {', '.join(wrong)})")
    return problems, evidence


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
        if any(f.startswith("src/") for f in files) and not ids:
            reason = " ".join(t.get("no-oracle", []))
            if len(reason) < 20:
                report.problems.append(f"{sha[:10]} changes src/{' in a merge resolution' if merge else ''} without "
                                       "'Fixes-Oracle: <ID>' or 'No-Oracle: <reason, 20+ characters>'")
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

        for sha, ids in fixes:
            _, files, session, _ = info[sha]
            parent = parents(repo, sha)[0] if parents(repo, sha) else None
            if parent is None:
                report.problems.append(f"{sha[:10]} is a root commit: no parent to fail on")
                continue
            for oid in ids:
                check_fix(repo, sha, parent, oid, files, session, fixer_sessions, tree, python, work, report)
        # every oracle at the candidate holds on the candidate's code, in its own tree
        cand_tree = tree(cand)
        here = sorted(d.name for d in (cand_tree / ORACLES).iterdir() if d.is_dir()) \
            if (cand_tree / ORACLES).is_dir() else []
        for oid in here:
            if not ID_RE.match(oid):
                report.problems.append(f"{ORACLES}/{oid}/ is not named by a bug ID")
                continue
            probs, _ = oracle_problems(cand_tree, oid)
            report.problems += [f"oracle {oid} at the candidate: {p}" for p in probs]
            own = last_touch(repo, cand, f"{ORACLES}/{oid}/")
            if probs or own is None:
                continue
            for h in git(repo, "log", "--format=%H", cand, "--", f"{ORACLES}/{oid}/").split():
                s = session_of(repo, h)
                if s is None or s in fixer_sessions.get(oid, set()):
                    report.problems.append(f"oracle {oid}: commit {h[:10]} that wrote it has "
                                           f"{'no Session: trailer' if s is None else f'the fixing session ({s})'}")
            run = run_pytest(compose(tree(own), cand_tree, work / f"at-{oid}"), [f"{ORACLES}/{oid}"], python, work / "r")
            if run.code != 0 or run.count("passed") != len(run.outcomes):
                report.problems.append(f"oracle {oid} fails on the candidate {cand[:10]} (pytest exit {run.code}): the "
                                       f"bug is back, or the oracle's tree no longer fits the code:\n{run.output[-800:]}")
        report.notes.append(f"{len(commits)} commits, {len(fixes)} fix commits, {len(here)} oracles held at the candidate")
    return report


def check_fix(repo, sha, parent, oid, files, session, fixer_sessions, tree, python, work, report) -> None:
    where = f"{sha[:10]} Fixes-Oracle: {oid}"
    own = last_touch(repo, parent, f"{ORACLES}/{oid}/")
    if own is None:
        report.problems.append(f"{where}: {ORACLES}/{oid}/ was not committed before the fix")
        return
    probs, evidence = oracle_problems(tree(own), oid)
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
        elif s in fixer_sessions.get(oid, set()):
            report.problems.append(f"{where}: oracle commit {h[:10]} is from the fixing session ({s})")
    target = [f"{ORACLES}/{oid}"]
    tag = f"{sha[:8]}-{oid}"
    # judged in the oracle's own tree (its tests, conftest, fixtures, config), with only src/ from parent and fix
    before = run_pytest(compose(tree(own), tree(parent), work / f"b-{tag}"), target, python, work / "r")
    not_assert = sorted(k for k, o in before.outcomes.items()
                        if o != "failed" or not ASSERTION.match(before.messages.get(k, "")))
    if before.code != 1 or not before.outcomes or not_assert:
        report.problems.append(f"{where}: every oracle test must fail on the parent {parent[:10]} with an assertion "
                               f"(pytest exit {before.code}; not an assertion failure: {', '.join(not_assert[:5]) or '-'})")
    after = run_pytest(compose(tree(own), tree(sha), work / f"a-{tag}"), target, python, work / "r")
    if after.code != 0 or after.count("passed") != len(after.outcomes):
        report.problems.append(f"{where}: the oracle must pass on the fix (pytest exit {after.code}, "
                               f"{after.count('failed')} failed, {after.count('error')} errors, "
                               f"{after.count('skipped')} skipped)")
    report.notes.append(f"{where}: fails on {parent[:10]}, checked against the fix in the tree of {own[:10]}")


# ------------------------------------------------------------------------------------------------ cli

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("loosening", help="block unexplained FAIL/UNKNOWN -> PASS between two commits")
    a.add_argument("--repo", required=True)
    a.add_argument("--base", required=True)
    a.add_argument("--candidate", default="HEAD")
    a.add_argument("--python", default=sys.executable)
    b = sub.add_parser("loosening-files", help="the same for two corpus results.json files, no git")
    b.add_argument("--base", required=True)
    b.add_argument("--candidate", required=True)
    c = sub.add_parser("reproduce", help="fix commits need an earlier, independent, failing-then-passing oracle")
    c.add_argument("--repo", required=True)
    c.add_argument("--range", required=True)
    c.add_argument("--python", default=sys.executable)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "loosening":
            return finish("loosening", loosening(Path(args.repo).resolve(), args.base, args.candidate, args.python))
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
