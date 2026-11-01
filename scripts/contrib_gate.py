"""Contributor CI gates (.github/workflows/contrib.yml). Each subcommand exits 1 with one line per problem.

  provenance                      every tests/fixtures file has a recorded source; every captures/ bundle validates
  corpus --base REF               no pre-registered corpus case or its expected verdict changed without an
                                  AMENDMENTS.md entry naming it
  corpus-results OLD NEW          no netdryrun verdict in a corpus rerun differs from the committed results
  known-false-passes --base REF   the known-false-pass tests, as REF has them, pass against this checkout's code
  fails-on-revert --base REF      a change to verdict code comes with a test that fails on REF's code
  dco --base REF                  every commit in REF..HEAD has a Signed-off-by line for its author
  disclosure EVENT_JSON           the pull request says, with one ticked box, whether AI tools were used
  labs [--run]                    every community/labs template has the required files; --run: good passes, bad fails

Everything runs on `pull_request` with a read-only token and no secrets, so a fork's pull request runs it too.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE_KINDS = {"live-capture", "lab-input", "report"}
# Code a verdict depends on: a change here needs a test that fails on the base branch's code
VERDICT_PATHS = ("src/netdryrun/drivers/", "src/netdryrun/checks.py", "src/netdryrun/runner.py",
                 "src/netdryrun/config.py", "src/netdryrun/faults.py", "src/netdryrun/lab.py",
                 "src/netdryrun/verify/", "src/netdryrun/capture/")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


# ---- fixture provenance -----------------------------------------------------------------------------------------
def provenance(root: Path | None = None) -> list[str]:
    root = root or ROOT
    fixtures = root / "tests" / "fixtures"
    problems = []
    try:
        entries = yaml.safe_load((fixtures / "SOURCES.yml").read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError) as e:
        return [f"tests/fixtures/SOURCES.yml: cannot read it: {e}"]
    files = sorted(p.relative_to(fixtures).as_posix() for p in fixtures.rglob("*")
                   if p.is_file() and p.name != "SOURCES.yml" and "__pycache__" not in p.parts)
    covered: set[str] = set()
    for i, e in enumerate(entries):
        where = f"tests/fixtures/SOURCES.yml entry {i + 1}"
        if not isinstance(e, dict) or not e.get("files") or not str(e.get("source") or "").strip() or not e.get("added"):
            problems.append(f"{where}: needs files, source and added")
            continue
        if e.get("kind") not in SOURCE_KINDS:
            problems.append(f"{where}: kind must be one of {sorted(SOURCE_KINDS)}")
        for pattern in e["files"]:
            hits = fnmatch.filter(files, pattern)
            if not hits:
                problems.append(f"{where}: {pattern} matches no file")
            covered.update(hits)
    problems += [f"tests/fixtures/{f}: no recorded source in tests/fixtures/SOURCES.yml" for f in files if f not in covered]

    captures = root / "captures"
    if captures.is_dir():
        sys.path.insert(0, str(root / "src"))
        from netdryrun.capture import bundle

        bundles = sorted(m.parent for m in captures.rglob("manifest.json"))
        for b in bundles:
            found, _notes = bundle.validate(b)
            problems += [f"{b.relative_to(root).as_posix()}: {p}" for p in found]
        stray = [p for p in captures.rglob("*") if p.is_file() and p.name != "README.md"
                 and not any(b in p.parents for b in bundles)]
        problems += [f"{p.relative_to(root).as_posix()}: a file in captures/ outside a bundle" for p in stray]
    return problems


# ---- corpus -----------------------------------------------------------------------------------------------------
def _cases(tree: Path) -> dict[str, str]:
    out = {}
    for name, base in (("v1", tree / "corpus"), ("v2", tree / "corpus" / "v2")):
        for p in sorted((base / "cases").glob("*.yml")):
            out[f"{name}/{p.stem}"] = p.read_text(encoding="utf-8")
    return out


def _export(ref: str, dest: Path) -> Path:
    """REF's tracked tree, unpacked in dest (git archive: no checkout of this working tree is touched)."""
    dest.mkdir(parents=True, exist_ok=True)
    data = subprocess.run(["git", "archive", "--format=tar", ref], cwd=ROOT, check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=data, check=True)
    return dest


def corpus_guard(base_tree: Path, head_tree: Path) -> list[str]:
    before, after = _cases(base_tree), _cases(head_tree)
    new_entries = ""
    problems = []
    for rel in ("corpus/AMENDMENTS.md", "corpus/v2/AMENDMENTS.md"):
        old = (base_tree / rel).read_text(encoding="utf-8") if (base_tree / rel).is_file() else ""
        new = (head_tree / rel).read_text(encoding="utf-8") if (head_tree / rel).is_file() else ""
        if not new.startswith(old):
            problems.append(f"{rel}: an existing entry was edited or removed (entries are append-only)")
        else:
            new_entries += new[len(old):]
    for case, text in before.items():
        if after.get(case) == text:
            continue
        case_id = case.split("/", 1)[1]
        what = "deleted" if case not in after else "changed"
        if case not in after:
            problems.append(f"corpus/{case}: a pre-registered case was deleted (cases are never removed)")
            continue
        old_v = (yaml.safe_load(text) or {}).get("expected")
        new_v = (yaml.safe_load(after[case]) or {}).get("expected")
        detail = f"expected verdict {old_v} -> {new_v}" if old_v != new_v else "case file edited"
        if case_id not in new_entries:
            problems.append(f"corpus/{case}: {what} ({detail}) without a new AMENDMENTS.md entry naming {case_id}")
    # the committed results and the nondeterministic list are what a rerun is compared with: same rule
    for results in ("corpus/results/results.json", "corpus/v2/results/results.json"):
        if not (base_tree / results).is_file():
            continue
        if not (head_tree / results).is_file():
            problems.append(f"{results}: deleted")
            continue
        changed, _ = corpus_results(base_tree / results, head_tree / results, nondeterministic=set())
        problems += [f"{results}: {c} without a new AMENDMENTS.md entry naming it" for c in changed
                     if c.split(":", 1)[0] not in new_entries]
    nd = "corpus/v2/NONDETERMINISTIC.yml"
    if (base_tree / nd).is_file():
        before_nd = _nondeterministic(base_tree / "corpus/v2/results/results.json")
        after_nd = _nondeterministic(head_tree / "corpus/v2/results/results.json")
        problems += [f"{nd}: {c} added without a new AMENDMENTS.md entry naming it" for c in sorted(after_nd - before_nd)
                     if c not in new_entries]
    return problems


def _nondeterministic(results_path: Path) -> set[str]:
    p = results_path.parent.parent / "NONDETERMINISTIC.yml"
    return set(yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else set()


def corpus_results(old_path: Path, new_path: Path, nondeterministic: set[str] | None = None) -> tuple[list[str], list[str]]:
    """(problems, notes): a netdryrun verdict that differs from the committed one is a problem, except for a case
    listed as nondeterministic (corpus/<v>/NONDETERMINISTIC.yml next to the committed results), which is a note."""
    old, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (old_path, new_path))
    skip = _nondeterministic(Path(old_path)) if nondeterministic is None else nondeterministic
    before = {c["id"]: c["strategies"]["netdryrun"]["verdict"] for c in old["cases"]}
    after = {c["id"]: c["strategies"]["netdryrun"]["verdict"] for c in new["cases"]}
    problems, notes = [], []
    for case, verdict in before.items():
        got = after.get(case)
        line = f"{case}: netdryrun verdict {verdict} in the committed results, {got} in this run"
        if got == verdict:
            continue
        (notes if case in skip else problems).append(line + (" (nondeterministic case, not scored)" if case in skip else ""))
    return problems, notes


# ---- tests from another tree ------------------------------------------------------------------------------------
def registry_tests(registry: Path) -> list[str]:
    entries = yaml.safe_load(registry.read_text(encoding="utf-8")) or []
    return sorted({t for e in entries for t in (e.get("tests") or [])})


def _pytest(tests_tree: Path, src: Path, targets: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(src), PYTHONDONTWRITEBYTECODE="1")
    check = subprocess.run([sys.executable, "-c", "import netdryrun; print(netdryrun.__file__)"], cwd=tests_tree,
                           env=env, capture_output=True, text=True)
    if not check.stdout.strip().startswith(str(src)):
        raise SystemExit(f"netdryrun was imported from {check.stdout.strip() or check.stderr.strip()}, not {src}")
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets], cwd=tests_tree,
                          env=env, capture_output=True, text=True)


def known_false_passes(base: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        tree = _export(base, Path(tmp) / "base")
        shutil.rmtree(tree / "src", ignore_errors=True)        # the tests are the base's; the code is this checkout's
        reg = tree / "tests" / "known_false_passes.yml"
        targets = registry_tests(reg) if reg.is_file() else registry_tests(ROOT / "tests" / "known_false_passes.yml")
        if not targets:
            return []
        r = _pytest(tree, ROOT / "src", targets)
        if r.returncode != 0:
            tail = "\n".join(r.stdout.strip().splitlines()[-25:])
            return [f"a known false pass is back: the base branch's tests fail on this code\n{tail}"]
    return []


def changed_files(base: str) -> list[str]:
    return [ln for ln in git("diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD").splitlines() if ln]


def fails_on_revert(base: str) -> list[str]:
    changed = changed_files(base)
    verdict = [f for f in changed if f.startswith(VERDICT_PATHS)]
    if not verdict:
        return []
    tests = [f for f in changed if re.fullmatch(r"tests/(.*/)?test_[^/]+\.py", f)]
    if not tests:
        return [f"verdict code changed ({', '.join(verdict[:5])}) with no test added or changed: add a test that "
                "fails without the change"]
    with tempfile.TemporaryDirectory() as tmp:
        base_src = _export(base, Path(tmp) / "base") / "src"
        r = _pytest(ROOT, base_src, tests)
    if r.returncode == 0:
        return [f"the changed tests ({', '.join(tests)}) also pass on the base branch's code, so they don't test the "
                "change: add a test that fails without it"]
    if r.returncode not in (1, 2):        # 1: tests failed, 2: collection failed (a new name the base lacks)
        return [f"pytest exited {r.returncode} running the changed tests on the base code:\n{r.stdout[-1500:]}"]
    return []


# ---- sign-off and disclosure ------------------------------------------------------------------------------------
def dco(base: str) -> list[str]:
    problems = []
    log = git("log", "--no-merges", "--format=%H%x1f%an%x1f%ae%x1f%B%x1e", f"{base}..HEAD")
    for rec in filter(None, (r.strip() for r in log.split("\x1e"))):
        sha, name, email, body = rec.split("\x1f", 3)
        offs = re.findall(r"^Signed-off-by:\s*(.+?)\s*<([^>]+)>\s*$", body, re.M)
        if not any(e.lower() == email.lower() or n == name for n, e in offs):
            problems.append(f"{sha[:10]} ({name} <{email}>): no Signed-off-by line for its author (git commit -s)")
    return problems


DISCLOSURE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(No AI tools|AI tools)\b", re.M)


def disclosure(body: str | None) -> list[str]:
    boxes = DISCLOSURE.findall(body or "")
    ticked = [label for mark, label in boxes if mark.lower() == "x"]
    if len(ticked) != 1:
        return ["tick exactly one box under \"AI use\" in the pull request description (it's a disclosure, not a "
                "ban: see CONTRIBUTING.md#ai-use)"]
    return []


# ---- lab templates ----------------------------------------------------------------------------------------------
LAB_META = ("name", "description", "nos", "images", "licence", "expected", "bad_change", "author", "source")


def _bad_lab(template: Path, dest: Path) -> Path:
    shutil.copytree(template, dest, ignore=shutil.ignore_patterns("bad"))
    shutil.copytree(template / "bad", dest, dirs_exist_ok=True)
    return dest


def labs(root: Path | None = None, run_them: bool = False) -> list[str]:
    root = root or ROOT
    sys.path.insert(0, str(root / "src"))
    from netdryrun import config
    from netdryrun.drivers import DRIVERS
    from netdryrun.lab import Lab, LabError

    problems = []
    for t in sorted(p.parent for p in (root / "community" / "labs").glob("*/template.yml")):
        rel = t.relative_to(root).as_posix()
        try:
            meta = yaml.safe_load((t / "template.yml").read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            problems.append(f"{rel}/template.yml: not YAML: {e}")
            continue
        missing = [k for k in LAB_META if not meta.get(k)]
        if missing:
            problems.append(f"{rel}/template.yml: missing {', '.join(missing)}")
            continue
        if meta["expected"] != {"good": "passed", "bad": "failed"}:
            problems.append(f"{rel}/template.yml: expected must be {{good: passed, bad: failed}}")
        unknown = [n for n in meta["nos"] if n not in DRIVERS]
        if unknown:
            problems.append(f"{rel}/template.yml: nos {unknown} has no driver ({sorted(DRIVERS)})")
        if meta["licence"] not in ("free", "bring-your-own-image"):
            problems.append(f"{rel}/template.yml: licence must be free or bring-your-own-image")
        for image in meta["images"]:
            if ":" not in image.rsplit("/", 1)[-1] and "@sha256:" not in image or image.endswith(":latest"):
                problems.append(f"{rel}/template.yml: image {image} is not pinned to a version or digest")
        if meta["licence"] == "bring-your-own-image":
            for side in ("good", "bad"):
                rep = t / "reports" / f"{side}.json"
                if not rep.is_file():
                    problems.append(f"{rel}: a bring-your-own-image template needs reports/{side}.json from your run")
                    continue
                status = json.loads(rep.read_text(encoding="utf-8")).get("status")
                if status != meta["expected"].get(side):
                    problems.append(f"{rel}/reports/{side}.json: status {status}, expected {meta['expected'].get(side)}")
        bad = t / "bad"
        overlay = [p.relative_to(bad) for p in bad.rglob("*") if p.is_file()] if bad.is_dir() else []
        if not overlay:
            problems.append(f"{rel}: no bad/ change (the broken variant that must fail)")
        problems += [f"{rel}/bad/{p.as_posix()}: replaces no file of the good lab (a bad change edits the lab)"
                     for p in overlay if not (t / p).is_file()]
        for side, lab_dir in (("good", t),):
            try:
                Lab(lab_dir / "topology.clab.yml")
                config.load(lab_dir / "netdryrun.yml")
            except (LabError, config.ConfigError, OSError) as e:
                problems.append(f"{rel} ({side}): {e}")
        if run_them and not problems and meta["licence"] == "free":
            with tempfile.TemporaryDirectory() as tmp:
                for side, lab_dir in (("good", t), ("bad", _bad_lab(t, Path(tmp) / "bad"))):
                    r = subprocess.run([sys.executable, "-m", "netdryrun", "run", str(lab_dir)], capture_output=True,
                                       text=True)
                    want = {"good": 0, "bad": 1}[side]
                    if r.returncode != want:
                        problems.append(f"{rel} ({side}): exit {r.returncode}, expected {want}\n{r.stdout[-1200:]}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("provenance")
    for name in ("corpus", "known-false-passes", "fails-on-revert", "dco"):
        sub.add_parser(name).add_argument("--base", required=True)
    p = sub.add_parser("corpus-results")
    p.add_argument("old")
    p.add_argument("new")
    sub.add_parser("disclosure").add_argument("event")
    sub.add_parser("labs").add_argument("--run", action="store_true")
    args = ap.parse_args(argv)

    notes: list[str] = []
    if args.cmd == "provenance":
        problems = provenance()
    elif args.cmd == "corpus":
        with tempfile.TemporaryDirectory() as tmp:
            problems = corpus_guard(_export(args.base, Path(tmp) / "base"), ROOT)
    elif args.cmd == "corpus-results":
        problems, notes = corpus_results(Path(args.old), Path(args.new))
    elif args.cmd == "known-false-passes":
        problems = known_false_passes(args.base)
    elif args.cmd == "fails-on-revert":
        problems = fails_on_revert(args.base)
    elif args.cmd == "dco":
        problems = dco(args.base)
    elif args.cmd == "disclosure":
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
        problems = disclosure((event.get("pull_request") or {}).get("body"))
    else:
        problems = labs(run_them=args.run)
    for n in notes:
        print(f"note: {n}")
    for p in problems:
        print(f"::error::{p}" if os.environ.get("GITHUB_ACTIONS") else f"problem: {p}")
    print(f"{args.cmd}: {'ok' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
