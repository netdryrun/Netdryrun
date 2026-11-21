"""Append-only attempt records for the release gate's modules, and what they add up to on one commit.
0.4.2 plan, step 2 (HQ design/release-checks-0.4.2-plan.md): one-command reruns of a single module or case, without
letting a rerun wash out a red.

Every time a layer is saved, release_gate.py also writes one attempt record:
`<out>/gate/records/<layer>/<UTC stamp>-<commit>-<pid>.json`, never overwritten. It carries:
- the layer record;
- the commit and the input key (whole tree + environment set);
- the labrun run id;
- the largest child process's resident memory;
- the cases it ran, when it was partial (`--case`, `--resume`).

Rules (each has a red fixture in tests/test_gate_records.py):
- **A FAIL stays FAIL:** a check that failed in any attempt on a commit, or on another commit with the same tree,
  fails there whatever later attempts say, until the code changes (a fix) or an `accepted.json` entry covers it
  (MAJOR only, as before). An empty or message-only commit is the same code: it starts nothing again.
- **Taints:** a check whose run overlaps a wall-clock gap labrun recorded (host sleep, a frozen VM) is no verdict
  for a PASS: it must be run again. A FAIL in a gap still fails, and every tainted run counts as an attempt (Layer 6
  on f220469: `labrun --gap 0` tainted everything, so a FAIL was dropped and could be rerun into a PASS).
- **At most 2 reruns of a case per tree** (3 attempts). A 4th is refused: a case that needs more is flaky, and
  that is a bug to fix, not a rerun to take.
- **An attempt record that can't be read blocks**: it may have held a FAIL.
- **`--resume` continues one run id on one commit only.** It skips the cases that run already finished (pass or fail)
  and never splits a case: a corpus, with all N runs of its nondeterministic cases, is one case.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path

RECORDS = Path("gate") / "records"
MAX_ATTEMPTS = 3          # the first run plus at most 2 reruns, per case and commit
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def _git(root: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def input_key(root: Path, env: dict | None = None) -> str:
    """sha256 over the committed tree, any uncommitted change, and the environment set. Until the closure tool
    (step 5) this is the whole tree: over-approximating, so it only ever calls a record stale too often. No git means
    no key ("unknown"), which nothing treats as fresh."""
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    diff = _git(root, "diff", "HEAD")
    if tree is None or status is None or diff is None:
        return "unknown"
    guard = root / "scripts" / "lab-guard.env"
    data = {"tree": tree.strip(), "status": status, "diff": hashlib.sha256(diff.encode()).hexdigest(),
            "python": platform.python_version(),
            "lab_guard": guard.read_text(encoding="utf-8") if guard.exists() else None, "env": env or {}}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def peak_child_rss_mb() -> float | None:
    """The largest child process's peak resident memory (Linux reports KB). Labs run in containers, which are not
    children: lab memory is the scheduler's (step 3) to measure, so this is named for what it is."""
    try:
        import resource
    except ImportError:
        return None
    kb = max(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return round(kb / 1024, 1)


def tree_of(root: Path, commit: str | None) -> str | None:
    """The tree a commit holds (what was tested); None when git can't tell."""
    if not commit:
        return None
    out = _git(root, "rev-parse", f"{commit}^{{tree}}")
    return out.strip() if out else None


def append(out: Path, rec: dict, *, commit: str | None, key: str, run_id: str, cases: list[str] | None = None,
           peak_mb: float | None = None, tree: str | None = None) -> Path:
    folder = out / RECORDS / rec["layer"]
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = folder / f"{stamp}-{(commit or 'nocommit')[:10]}-{os.getpid()}.json"
    n = 1
    while path.exists():                     # never overwrite an attempt
        path = folder / f"{stamp}-{(commit or 'nocommit')[:10]}-{os.getpid()}-{n}.json"
        n += 1
    data = {**rec, "attempt": {"commit": commit, "tree": tree, "key": key, "run_id": run_id, "cases": cases,
                               "peak_child_rss_mb": peak_mb, "written": time.time()}}
    with open(path, "x", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    return path


def attempts(out: Path, layer: str) -> list[dict]:
    folder = out / RECORDS / layer
    found = []
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            found.append({"_unreadable": True, "_path": str(p)})   # it may have held a FAIL: never skipped
            continue
        d["_path"] = str(p)
        found.append(d)
    return found


def labrun_taints(run_id: str | None, state: Path | None = None) -> list[dict]:
    if not run_id:
        return []
    state = state or Path(os.environ.get("LABRUN_STATE", Path.home() / ".cache" / "netdryrun-labrun"))
    try:
        return json.loads((state / run_id / "result.json").read_text(encoding="utf-8")).get("taints") or []
    except (OSError, ValueError):
        return []


def tainted(check: dict, taints: list[dict]) -> bool:
    end = float(check.get("ended") or 0)
    if not end:
        return False
    start = end - float(check.get("seconds") or 0)
    return any(start <= float(t["to"]) and end >= float(t["from"]) for t in taints)


def case_of(check_id: str) -> str:
    """The case a check belongs to: `example-frr-bgp-clean` -> `example-frr-bgp`, `corpus-v2-status` -> `corpus-v2`."""
    if check_id.startswith("corpus-v"):
        return "-".join(check_id.split("-")[:2])
    return check_id.removesuffix("-clean")


def _same_code(a: dict, commit: str | None, tree: str | None) -> bool:
    return bool(commit and a.get("commit") == commit) or bool(tree and a.get("tree") == tree)


def verdict(recs: list[dict], commit: str | None, taints_of=labrun_taints, tree: str | None = None) -> dict:
    """Every check's status over all attempts on this commit, or on any commit with the same tree: FAIL if any
    attempt failed (in a host gap too), PASS if one untainted attempt passed and none failed, else no verdict. Also the
    attempts per case (tainted ones count) and the attempt records that can't be read (`unreadable`: a red)."""
    checks: dict[str, dict] = {}
    runs_per_case: dict[str, set] = {}
    unreadable = [r["_path"] for r in recs if r.get("_unreadable")]
    for r in recs:
        a = r.get("attempt") or {}
        if r.get("_unreadable") or not _same_code(a, commit, tree):
            continue
        taints = taints_of(a.get("run_id"))
        for c in r.get("checks", []):
            e = checks.setdefault(c["id"], {"status": None, "attempts": 0, "tainted": 0, "failed_in": None})
            e["attempts"] += 1
            runs_per_case.setdefault(case_of(c["id"]), set()).add(r["_path"] if "_path" in r else id(r))
            if tainted(c, taints):
                e["tainted"] += 1
                if c["status"] != FAIL:      # a PASS in a host gap is no verdict; a FAIL there still fails
                    continue
            if c["status"] == FAIL:
                e["status"], e["failed_in"] = FAIL, e["failed_in"] or r.get("_path")
            elif c["status"] == PASS and e["status"] != FAIL:
                e["status"] = PASS
            elif e["status"] is None:
                e["status"] = c["status"]
    return {"checks": checks, "attempts_per_case": {k: len(v) for k, v in runs_per_case.items()},
            "unreadable": unreadable}


def rerun_refused(recs: list[dict], commit: str | None, cases: list[str], tree: str | None = None) -> list[str]:
    """Cases that already used their 3 attempts on this commit or this tree."""
    per = verdict(recs, commit, tree=tree)["attempts_per_case"]
    return [c for c in cases if per.get(c, 0) >= MAX_ATTEMPTS]


def done_cases(recs: list[dict], commit: str | None, run_id: str) -> set[str]:
    """Cases one run id already finished on this commit (pass or fail): what --resume skips."""
    done = set()
    for r in recs:
        a = r.get("attempt") or {}
        if a.get("commit") == commit and a.get("run_id") == run_id:
            taints = labrun_taints(run_id)
            done |= {case_of(c["id"]) for c in r.get("checks", []) if c["status"] in (PASS, FAIL)
                     and not tainted(c, taints)}
    return done


def plan_rows(out: Path, layers: list[str], commit: str | None, key: str) -> list[tuple[str, str, str]]:
    """(layer, state, detail) for `release_gate.py plan`: owed, stale, failed, tainted or passed on this commit."""
    rows = []
    for layer in layers:
        recs = attempts(out, layer)
        bad = [r["_path"] for r in recs if r.get("_unreadable")]
        if bad:
            rows.append((layer, "FAIL", f"{len(bad)} attempt record(s) can't be read (one may have held a FAIL): "
                                        + ", ".join(Path(b).name for b in bad[:3])))
            continue
        on_commit = [r for r in recs if (r.get("attempt") or {}).get("commit") == commit]
        if not on_commit:
            rows.append((layer, "owed", "no attempt on this commit" + (f" ({len(recs)} on others)" if recs else "")))
            continue
        if key == "unknown" or not any((r.get("attempt") or {}).get("key") == key for r in on_commit):
            rows.append((layer, "stale", "attempts on this commit were made on a different tree or environment"))
            continue
        v = verdict(on_commit, commit)
        failed = sorted(k for k, e in v["checks"].items() if e["status"] == FAIL)
        taint = sorted(k for k, e in v["checks"].items() if e["tainted"] and e["status"] is None)
        if failed:
            rows.append((layer, "FAIL", f"{len(failed)} check(s) failed in an attempt on this commit: "
                                        + ", ".join(failed[:6])))
        elif taint:
            rows.append((layer, "tainted", "no verdict (host gap), run again: " + ", ".join(taint[:6])))
        else:
            rows.append((layer, "PASS", f"{len(on_commit)} attempt(s), {len(v['checks'])} checks"))
    return rows
