"""The agent result: what an AI agent reads after a run, as the MCP tools return it and as `netdryrun run
--verdict` writes it (netdryrun.mcp-result/v1, https://netdryrun.com/schemas/mcp-result-v1.json). No MCP
import, so the plain CLI can write it."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
from pathlib import Path

from .config import VRF_NAME
from .drivers import DriverError, detect
from .lab import Lab, Node

# The result contract, published as https://netdryrun.com/schemas/mcp-result-v1.json. The three verdict strings
# are frozen: agents match on them, so they never change within v1.
RESULT_SCHEMA = "netdryrun.mcp-result/v1"
CHECKS_PASSED = "CHECKS PASSED (only what the checks cover)"   # never "safe": a pass covers only the checks
DO_NOT_APPLY = "DO NOT APPLY THIS CHANGE"
INCONCLUSIVE = ("INCONCLUSIVE: the lab did not reach a testable state; this says nothing about your change. "
                "Do not apply it until a run passes.")
VERDICT_ENUM = (CHECKS_PASSED, DO_NOT_APPLY, INCONCLUSIVE)
VERDICTS = {"passed": CHECKS_PASSED, "inconclusive": INCONCLUSIVE}   # any other status, including future ones: DO_NOT_APPLY


def _text(value, limit: int) -> str | None:
    """Text that can quote lab output (an error line, a state name), kept to one short line: it reaches
    the agent as data, never as a block that could pass for instructions. The verdict never depends on it."""
    if value is None or value == "":
        return None
    t = " ".join(str(value).split())
    return t if len(t) <= limit else t[:limit] + "..."


def _check(r) -> dict:
    c = {"name": _text(r.check.name, 300), "passed": r.passed, "detail": _text(r.detail, 300)}
    if not r.passed and r.attempts and r.samples_unready == r.attempts:
        # every sample failed for lack of state (the command failed, its output was unreadable, or no BGP
        # neighbors at all): a lab problem on that node is as likely as a bad change
        c["unready"] = True
    return c


# How each driver runs one CLI command inside its node: the prefix of a next_diagnostic command.
_CLI = {"frr": ("vtysh", "-c"), "sonic": ("vtysh", "-c"), "eos": ("Cli", "-p", "15", "-c"), "srlinux": ("sr_cli",)}


def _driver_name(rep, node: str) -> str | None:
    override = rep.config.drivers.get(node)
    if override:
        return override if override in _CLI else None
    info = (rep.environment.get("nodes") or {}).get(node)
    if not isinstance(info, dict):
        return None
    try:
        return detect(Node(node, "", str(info.get("kind", "")), str(info.get("image", ""))))
    except DriverError:
        return None


def _show_command(driver: str, check) -> str | None:
    """One read-only CLI command that shows the state a failed check looked at, in the node's own CLI. Only
    validated values reach it (a VRF name, a parsed prefix or address), never free text from the config."""
    p, t = check.params, check.type
    vrf = str(p.get("vrf", "default"))
    if not VRF_NAME.fullmatch(vrf):
        return None
    try:
        if t in ("route", "bgp_route"):
            addr = ipaddress.ip_network(str(p["prefix"]), strict=False)
        elif t == "ping":
            addr = ipaddress.ip_address(str(p["target"]))
        else:   # bgp_session, bgp_prefixes: the neighbor's family, when it is an address
            try:
                addr = ipaddress.ip_address(str(p.get("neighbor", "")))
            except ValueError:
                addr = None
    except (KeyError, ValueError):
        return None
    afi = str(p.get("afi", "ipv6-unicast" if addr and addr.version == 6 else "ipv4-unicast"))
    v6 = (addr.version == 6) if addr else afi == "ipv6-unicast"
    fam, bgp_afi = ("ipv6", "ipv6") if v6 else ("ip", "ipv4")
    if driver in ("frr", "sonic"):
        in_vrf = "" if vrf == "default" else f" vrf {vrf}"
        if t == "bgp_session":
            return f"show bgp{in_vrf} summary"
        if t == "bgp_prefixes":
            return "show bgp l2vpn evpn summary" if afi == "evpn" else f"show bgp{in_vrf} {bgp_afi} unicast summary"
        if t in ("route", "ping"):
            return f"show {fam} route{in_vrf} {addr}"
        if t == "bgp_route":
            return f"show bgp{in_vrf} {bgp_afi} unicast {addr}"
    if driver == "eos":
        if t in ("bgp_session", "bgp_prefixes"):
            return "show bgp evpn summary" if afi == "evpn" else f"show {fam} bgp summary vrf {vrf}"
        if t in ("route", "ping"):
            return f"show {fam} route vrf {vrf} {addr}"
        if t == "bgp_route":
            return f"show {fam} bgp {addr} vrf {vrf}"
    if driver == "srlinux":
        table = "ipv6-unicast" if v6 else "ipv4-unicast"
        if t in ("bgp_session", "bgp_prefixes"):
            return f"info from state /network-instance {vrf} protocols bgp neighbor *"
        if t == "route":
            return (f"info from state /network-instance {vrf} route-table {table} route {addr} "
                    "id * route-type * route-owner * origin-network-instance *")
        if t == "bgp_route":
            return (f"info from state /network-instance {vrf} bgp-rib afi-safi {table} {table} local-rib "
                    f"route {addr} neighbor * origin-protocol * path-id *")
        if t == "ping":   # the whole table: which route, if any, covers the target
            return (f"info from state /network-instance {vrf} route-table {table} route * "
                    "id * route-type * route-owner * origin-network-instance *")
    return None


def _containers(rep) -> dict[str, str]:
    try:
        return {name: n.container for name, n in Lab(rep.config.lab).nodes.items()}
    except Exception:  # topology gone or unreadable: fall back to containerlab's default names
        return {}


def _next_diagnostic(rep, check, containers: dict[str, str]) -> str | None:
    node = str(check.params.get("node", ""))
    driver = _driver_name(rep, node)
    show = _show_command(driver, check) if driver else None
    container = containers.get(node) or (f"clab-{rep.lab_name}-{node}" if rep.lab_name and node else None)
    if not show or not container:
        return None
    return "docker exec " + shlex.join([container, *_CLI[driver], show])


def _evidence(r) -> dict | None:
    """A short excerpt of the raw evidence: the first command that failed, else the last command run."""
    if not r.evidence:
        return None
    e = next((x for x in r.evidence if x.get("rc") != 0), r.evidence[-1])
    return {"cmd": _text(e.get("cmd"), 200), "rc": e.get("rc"),
            "excerpt": _text(str(e.get("output") or "").strip() or e.get("stderr"), 200)}


def _failures(rep) -> list[dict]:
    failed = [r for r in rep.results if not r.passed]
    containers = _containers(rep) if failed else {}
    return [{"check": _text(r.check.name, 300), "node": _text(r.check.params.get("node"), 100),
             "reason": _text(r.detail, 300), "evidence": _evidence(r),
             "next_diagnostic": _next_diagnostic(rep, r.check, containers)} for r in failed]


def _summary(rep, evidence_path: str | None, tested: dict | None = None) -> dict:
    """The tool result. `tested` is read before the run (_execute passes it); without it, the files are read now."""
    return {
        "schema": RESULT_SCHEMA,
        "status": rep.status,
        "passed": rep.passed,
        "failed": rep.failed,
        "error": _text(rep.error, 1000),
        "inconclusive_reason": _text(rep.inconclusive_reason, 1000),
        "lab": _text(rep.lab_name, 100),
        "checks": [_check(r) for r in rep.results],
        "failures": _failures(rep),
        "evidence_file": evidence_path,
        "verdict": VERDICTS.get(rep.status, DO_NOT_APPLY),
        "tested": _with_nodes(tested if tested is not None else _tested(rep.config, deployed=False), rep),
    }



TESTED_FILES_MAX = 200   # a bind of a large folder must not turn a dry run into a hashing job


def _with_nodes(tested: dict, rep) -> dict:
    """`tested.nodes`: each node's image, its digest and the NOS version it reported (null where not read), and
    its config load, so a verdict is tied to what ran, not only to the files."""
    nodes = {}
    for name, n in sorted((rep.environment.get("nodes") or {}).items()):
        nodes[name] = {"image": n.get("image", ""), "image_digest": n.get("image_digest"),
                       "nos_version": n.get("nos_version"), "config_load": n.get("config_load", "not checked")}
    return {**tested, "nodes": nodes}


def _tested(cfg, deployed: bool, outside_root=lambda path: None) -> dict:
    """What a run tested, so a verdict can be tied to a version of the files (agent eval T06: a run on the
    unedited folder looked like a run of the change): a sha256 of netdryrun.yml, the topology and every file the
    topology binds, loads as a startup config or licence, or reads as env-files, in defaults, kinds, groups and
    nodes (a bound folder: the files in it), read before the run; `config` is the netdryrun.yml that ran. Keys
    are paths relative to the folder of netdryrun.yml. `complete` is false when a file can't be read, is
    outside NETDRYRUN_MCP_ROOT (not read), is named with ~, ${VAR} or a URL (containerlab resolves those; not
    read here), or there are more than TESTED_FILES_MAX."""
    import hashlib
    import itertools

    import yaml

    base, lab_dir = cfg.path.parent.resolve(), cfg.lab.parent.resolve()
    sources = [cfg.path, cfg.lab]
    complete = True
    try:
        t = (yaml.safe_load(cfg.lab.read_text(encoding="utf-8")) or {}).get("topology") or {}
    except (OSError, yaml.YAMLError, AttributeError):
        t, complete = {}, False
    if not isinstance(t, dict):
        t, complete = {}, False
    # A shape this can't read (a list where a mapping belongs) only makes the list incomplete: reading the
    # files a run uses must never stop the run or its report
    sections = [t.get("defaults")]
    for key in ("kinds", "groups", "nodes"):
        v = t.get(key) or {}
        if isinstance(v, dict):
            sections += v.values()
        else:
            complete = False
    refs: list[str] = []
    for sec in sections:
        if sec is None:
            continue
        if not isinstance(sec, dict):
            complete = False
            continue
        for key in ("binds", "env-files"):
            v = sec.get(key) or []
            if not isinstance(v, list):
                complete = False
                continue
            refs += [str(b).split(":", 1)[0] if key == "binds" else str(b) for b in v if isinstance(b, str)]
        for key in ("startup-config", "license"):
            v = sec.get(key)
            if isinstance(v, str) and "\n" not in v:   # containerlab also takes a startup config inline
                refs.append(v)
    for ref in refs:
        # containerlab expands ~ (the sudo user's home) and ${VAR}, and downloads URLs: not read here, so the
        # list can't say it is complete
        if ref.startswith("~") or "$" in ref or re.match(r"^[a-z][a-z0-9+.-]*://", ref, re.I):
            complete = False
        else:
            sources.append(lab_dir / ref)
    files: dict[str, str] = {}
    for src in sources:
        src = Path(src)
        if outside_root(src.resolve()):   # not even listed or walked: the root check comes first
            complete = False
            continue
        if src.is_dir():   # stop walking at the cap: a bound system folder can hold many thousands of files
            found = list(itertools.islice((p for p in src.rglob("*") if p.is_file()), TESTED_FILES_MAX + 1))
        else:
            found = [src]
        for f in sorted(found):
            f = f.resolve()
            try:
                key = Path(os.path.relpath(f, base)).as_posix()
            except ValueError:   # another drive on Windows
                key = f.as_posix()
            if key in files:
                continue
            if len(files) >= TESTED_FILES_MAX or outside_root(f):
                complete = False
                continue
            try:
                files[key] = hashlib.sha256(f.read_bytes()).hexdigest()
            except OSError:
                complete = False
    return {"config": str(cfg.path.resolve()), "lab_deployed_by_this_run": deployed,
            "files": dict(sorted(files.items())), "complete": complete}


def hold_to_files(result: dict, cfg, tested: dict, outside_root=lambda path: None) -> dict:
    """A run that deployed from the files is tied to their hashes, read before it started. If any of them
    changed by the time it finished, the lab may have run either version: the result becomes an error (never a
    pass with the old hashes), naming the files, with them in tested.changed_during_run. A run on a lab that
    was already running (lab_deployed_by_this_run: false) didn't load the files, so nothing is compared."""
    if not tested.get("lab_deployed_by_this_run"):
        return result
    before, now = tested.get("files") or {}, _tested(cfg, True, outside_root)["files"]
    changed = sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))
    if not changed:
        return result
    return {**result, "status": "error", "verdict": DO_NOT_APPLY, "tested": {**tested, "changed_during_run": changed},
            "error": (f"files changed while the run was in progress: {', '.join(changed[:10])}. The lab may have "
                      "run either version, so this result can't be tied to the hashes in tested: run again")}


STATUSES = ("passed", "failed", "inconclusive", "error")


def pr_comment_header(result: dict, commit: str | None = None) -> str:
    """The first two lines of the PR comment or MR note (0.3.3), a fixed format an agent can read without
    parsing the rest: an HTML comment with the result's status, verdict, counts and the commit it describes as
    JSON, then the same in words.

        <!-- netdryrun-verdict: {"schema": "netdryrun.mcp-result/v1", "status": ..., "verdict": ..., ...} -->
        **Netdryrun: <verdict>** · status `<status>` · <n> passed, <n> failed · commit `<sha>`

    Only a known status whose verdict and counts agree with it is shown; anything else (no result, lab text,
    a pass with failures or with no check) is status error, DO NOT APPLY THIS CHANGE: the header never claims
    a pass the run didn't give. `commit` (the head commit tested) is shown only when it is a hex SHA, so an
    agent can tell a header left from an older commit."""
    status, verdict = result.get("status"), result.get("verdict")
    passed, failed = result.get("passed"), result.get("failed")
    counts_ok = all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (passed, failed))
    ok = (status in STATUSES and counts_ok and verdict == VERDICTS.get(status, DO_NOT_APPLY)
          and (status != "passed" or (failed == 0 and passed > 0)))
    if not ok:
        status, verdict = "error", DO_NOT_APPLY
        passed, failed = (passed, failed) if counts_ok else (0, 0)
    data = {"schema": RESULT_SCHEMA, "status": status, "verdict": verdict, "passed": passed, "failed": failed}
    words = f"**Netdryrun: {verdict}** · status `{status}` · {passed} passed, {failed} failed"
    if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{7,40}", commit):
        data["commit"] = commit
        words += f" · commit `{commit[:12]}`"
    return f"<!-- netdryrun-verdict: {json.dumps(data)} -->\n{words}\n"


def verify_comment_header(report: dict, commit: str | None = None) -> str:
    """pr_comment_header for mode: verify (0.4): the same two lines, read from the verify report
    (`netdryrun.verify/v1`), with verify's own verdict and counts of undeclared differences and declared changes
    that didn't happen. Only a known status whose verdict is verify's word for it, and an approval
    (INTENT MATCHED, NO BEHAVIOR CHANGE) with nothing undeclared, nothing missing and no failed guard, is shown;
    anything else is status error, ERROR: NO VERDICT. It never says a run-mode verdict."""
    from .verify import report as vreport

    r = report if isinstance(report, dict) else {}
    status, verdict = r.get("status"), r.get("verdict")
    undeclared, missing = r.get("undeclared"), r.get("not_happened")
    guards = r.get("guards") if isinstance(r.get("guards"), dict) else {}
    lists_ok = isinstance(undeclared, list) and isinstance(missing, list)
    ok = (r.get("schema") == vreport.SCHEMA and status in vreport.VERDICTS and verdict == vreport.VERDICTS[status]
          and lists_ok and (status not in ("matched", "no_change")
                            or (not undeclared and not missing and not guards.get("failed"))))
    if not ok:
        status, verdict = "error", vreport.VERDICTS["error"]
    counts = (len(undeclared), len(missing)) if lists_ok else (0, 0)
    # running-config lines of an approval that the lab didn't exercise (gauntlet 0.4, R4): never hidden
    untested = r.get("untested_config") if isinstance(r.get("untested_config"), list) else []
    lines = sum(len(u.get("added") or []) + len(u.get("removed") or []) for u in untested if isinstance(u, dict))
    if status not in ("matched", "no_change"):
        lines = 0
    data = {"schema": vreport.SCHEMA, "status": status, "verdict": verdict, "undeclared": counts[0],
            "not_happened": counts[1], "untested_config_lines": lines}
    words = (f"**Netdryrun verify: {verdict}** · status `{status}` · {counts[0]} undeclared, "
             f"{counts[1]} not happened" + (f" · {lines} config line(s) not tested if the lab doesn't exercise them"
                                            if lines else ""))
    if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{7,40}", commit):
        data["commit"] = commit
        words += f" · commit `{commit[:12]}`"
    return f"<!-- netdryrun-verdict: {json.dumps(data)} -->\n{words}\n"
