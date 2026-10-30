"""Offline checks of the false-passes corpus: no lab, no Docker, no network.

    python corpus/v3-false-passes/check_cases.py

What it proves: every case is complete and well-formed, its expected verdict is a failure (never a pass), the files
it needs exist and are consistent with what the write-up says (a verify case's sides differ exactly where the case
says they do), and the pre-registration manifest still matches. What it does not prove: how any netdryrun version
behaves on the case. That needs a lab (run_cases.py).
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"
STATUS_EXIT = {"failed": 1, "error": 2, "inconclusive": 3, "refused": 1}
MODES = {"run", "verify", "action"}
REQUIRED = ("id", "title", "mode", "command", "expected", "expected_from", "fixed_in", "passed_wrongly", "source",
            "holds", "pre_registered", "live_verified")
SEMVER = re.compile(r"\d+\.\d+\.\d+$")
TEST_REF = re.compile(r"tests/[\w/]+\.py(::\w+)?$")
MANIFEST = HERE / "MANIFEST.sha256"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def binds(topology: dict) -> list[str]:
    t = topology.get("topology") or {}
    nodes = list((t.get("nodes") or {}).values())
    nodes += list((t.get("kinds") or {}).values()) + [t.get("defaults") or {}]
    out = []
    for n in nodes:
        for b in (n or {}).get("binds") or []:
            out.append(b.split(":")[0])
        if (n or {}).get("startup-config"):
            out.append(n["startup-config"])
    return sorted(set(out))


def manifest_lines() -> list[str]:
    rows = []
    for p in sorted(CASES.glob("*/case.yml")):
        data = p.read_bytes().replace(b"\r\n", b"\n")        # the same hash on a CRLF checkout
        rows.append(f"{hashlib.sha256(data).hexdigest()}  {p.relative_to(HERE).as_posix()}")
    return rows


def check_case(d: Path) -> list[str]:
    errs: list[str] = []
    err = errs.append
    cy = d / "case.yml"
    if not cy.exists():
        return [f"{d.name}: no case.yml"]
    c = load_yaml(cy)
    for k in REQUIRED:
        if k not in c:
            err(f"{d.name}: case.yml misses {k}")
    if errs:
        return errs
    if c["id"] != d.name:
        err(f"{d.name}: id {c['id']!r} does not match the folder")
    if c["mode"] not in MODES:
        err(f"{d.name}: mode must be one of {sorted(MODES)}")
    exp = c["expected"]
    if exp.get("status") == "passed" or exp.get("status") not in STATUS_EXIT:
        err(f"{d.name}: expected.status must be one of {sorted(STATUS_EXIT)} (a false-pass case never expects a pass)")
    elif exp.get("exit_code") != STATUS_EXIT[exp["status"]]:
        err(f"{d.name}: exit code {exp.get('exit_code')} does not fit status {exp['status']}")
    if exp.get("exit_code") == 0:
        err(f"{d.name}: expected exit code 0 is a pass")
    if not exp.get("must_report") or not all(isinstance(x, str) and x for x in exp["must_report"]):
        err(f"{d.name}: expected.must_report needs at least one non-empty string")
    for k in ("expected_from", "fixed_in"):
        if not SEMVER.match(str(c[k])):
            err(f"{d.name}: {k} must be a version like 0.4.0")
    if c["live_verified"] not in (True, False):
        err(f"{d.name}: live_verified must be true or false")
    for t in c["holds"]:
        if not TEST_REF.match(t):
            err(f"{d.name}: holds entry {t!r} is not a tests/...py::name reference")
    if not (d / "WRITEUP.md").exists():
        err(f"{d.name}: no WRITEUP.md")
    elif "case.yml" not in (d / "WRITEUP.md").read_text(encoding="utf-8"):
        err(f"{d.name}: WRITEUP.md should point at case.yml")
    err_before = len(errs)
    {"run": check_run, "verify": check_verify, "action": check_action}[c["mode"]](d, c, err)
    return errs if len(errs) > err_before or errs else errs


def check_run(d: Path, c: dict, err) -> None:
    lab = d / "lab"
    topo_path = lab / "topology.clab.yml"
    if not topo_path.exists():
        return err(f"{d.name}: no lab/topology.clab.yml")
    topo = load_yaml(topo_path)
    if not str(topo.get("name", "")).startswith("ndr-"):
        err(f"{d.name}: lab name must start with ndr- (the gate removes only labs named ndr-*)")
    for b in binds(topo):
        if not (lab / b).exists():
            err(f"{d.name}: the topology binds {b}, which is not in lab/")
    spec = lab / "netdryrun.yml"
    if not spec.exists():
        return err(f"{d.name}: no lab/netdryrun.yml")
    try:
        from netdryrun.config import load
        load(spec)
    except Exception as e:  # noqa: BLE001 - report any config problem as a case problem
        err(f"{d.name}: netdryrun.yml does not validate: {e}")
    if d.name.startswith("01-"):
        text = (lab / "configs" / "r1.conf").read_text(encoding="utf-8")
        for line in ("default-orignate", "maximum-prefix\n", "10.9.9.9 route-map"):
            if line not in text:
                err(f"{d.name}: r1.conf lacks the rejected line containing {line.strip()!r}")
    if d.name.startswith("02-") and "exec" not in (topo["topology"]["nodes"]["r1"] or {}):
        err(f"{d.name}: r1 has no exec: command")
    if d.name.startswith("08-"):
        srl = (lab / "configs" / "srl1.json").read_text(encoding="utf-8")
        if "peer-groop" not in srl:
            err(f"{d.name}: srl1.json lacks the misspelled key the case is about")
        import json
        json.loads(srl)       # it must be valid JSON: the router rejects the schema, not the syntax


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_verify(d: Path, c: dict, err) -> None:
    topo_path = d / "lab" / "topology.clab.yml"
    if not topo_path.exists():
        return err(f"{d.name}: no lab/topology.clab.yml")
    topo = load_yaml(topo_path)
    if not str(topo.get("name", "")).startswith("ndr-"):
        err(f"{d.name}: lab name must start with ndr-")
    for side in ("before", "after"):
        if not (d / side).is_dir():
            return err(f"{d.name}: no {side}/ folder")
    bound = [Path(b).name for b in binds(topo)]
    for b in bound:
        for side in ("before", "after"):
            if not (d / side / b).exists():
                err(f"{d.name}: {side}/ lacks the bound file {b}")
    differs = sorted(n for n in bound if (d / "before" / n).exists() and (d / "after" / n).exists()
                     and sha(d / "before" / n) != sha(d / "after" / n))
    unbound_extra = sorted(p.name for p in (d / "after").iterdir() if p.name not in bound)
    want = {"04-": ["daemons"], "05-": [], "03-": ["r2.conf"], "06-": ["r1.conf"]}
    for prefix, files in want.items():
        if d.name.startswith(prefix) and differs != files:
            err(f"{d.name}: bound files that differ are {differs}, the case says {files}")
    if d.name.startswith("05-") and not unbound_extra:
        err(f"{d.name}: the edited file must be one the topology does not bind")
    intent = d / "intent.yml"
    if not intent.exists():
        return err(f"{d.name}: no intent.yml")
    data = load_yaml(intent)
    if not isinstance(data, dict) or "intent" not in data:
        err(f"{d.name}: intent.yml needs an intent: key")
    try:   # the real parser, when this checkout has verify (0.4 and later)
        from netdryrun.verify.intent import parse_intent_text
    except ImportError:
        parse_intent_text = None
    if parse_intent_text:
        try:
            parse_intent_text(intent.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            err(f"{d.name}: intent.yml does not parse: {e}")


def check_action(d: Path, c: dict, err) -> None:
    wf = ".github/workflows/netdryrun.yml"
    b, h = d / "base" / wf, d / "head" / wf
    if not (b.exists() and h.exists()):
        return err(f"{d.name}: base/ and head/ each need {wf}")
    if sha(b) == sha(h):
        err(f"{d.name}: the workflow must differ between base and head")
    steps = load_yaml(h)["jobs"]["verify"]["steps"]
    with_ = next(s["with"] for s in steps if "netdryrun" in str(s.get("uses", "")))
    if with_.get("mode") != "verify" or with_.get("allow-intent-edit") is not True:
        err(f"{d.name}: head's workflow must run mode: verify with allow-intent-edit: true")
    base_with = next(s["with"] for s in load_yaml(b)["jobs"]["verify"]["steps"] if "netdryrun" in str(s.get("uses", "")))
    if base_with.get("allow-intent-edit") is not False:
        err(f"{d.name}: base's workflow must have allow-intent-edit: false")
    if sha(d / "base" / "intent.yml") == sha(d / "head" / "intent.yml"):
        err(f"{d.name}: the intent must differ between base and head")


def main() -> int:
    errs: list[str] = []
    dirs = sorted(p for p in CASES.iterdir() if p.is_dir())
    if len(dirs) < 8:
        errs.append(f"expected at least 8 cases, found {len(dirs)}")
    for d in dirs:
        errs += check_case(d)
    if MANIFEST.exists():
        have = MANIFEST.read_text(encoding="utf-8").strip().splitlines()
        if have != manifest_lines():
            errs.append("MANIFEST.sha256 does not match the case.yml files: an expected verdict changed after "
                        "pre-registration. Record it in AMENDMENTS.md and regenerate the manifest "
                        "(python check_cases.py --write-manifest)")
    else:
        errs.append("MANIFEST.sha256 is missing (python check_cases.py --write-manifest)")
    for e in errs:
        print("FAIL", e)
    print(f"{len(dirs)} cases checked, {len(errs)} problem(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    if "--write-manifest" in sys.argv:
        MANIFEST.write_text("\n".join(manifest_lines()) + "\n", encoding="utf-8", newline="\n")
        print("wrote", MANIFEST)
        sys.exit(0)
    sys.exit(main())
