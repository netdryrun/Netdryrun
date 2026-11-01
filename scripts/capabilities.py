"""Netdryrun's machine-readable capability statement: website/docs/capabilities.json, served at
https://netdryrun.com/capabilities.json and referenced from server.json (_meta), AGENTS.md, llms.txt and the MCP
server's instructions.

One place for what an agent (or a person choosing a tool) needs to decide: the use cases and how to invoke each,
the prerequisites, the limits, the platforms, tools, check types, verdicts and exit codes. The facts (version,
platforms, check types, MCP tools, verdict strings) are read from the source, like sync_facts.py does, so the file
can't drift: `python scripts/sync_facts.py` rewrites it and `--check` fails when it is stale.

  python scripts/capabilities.py           print the statement
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "netdryrun"
PAGE = ROOT / "website" / "docs" / "capabilities.json"
URL = "https://netdryrun.com/capabilities.json"
SCHEMA = "netdryrun.capabilities/v1"

USE_CASES = [
    {"id": "dry_run",
     "when": "Before proposing or applying a routing or policy change, when the lab has checks (netdryrun.yml) "
             "that state what must hold.",
     "does": "Deploys the containerlab lab with the change, waits for convergence, runs every check, destroys the "
             "lab. A pass covers only what the checks look at.",
     "mcp": {"tool": "dry_run", "arguments": {"path": "/path/to/lab"}},
     "cli": "netdryrun run /path/to/lab --json report.json",
     "github_action": {"uses": "netdryrun/Netdryrun@vVERSION", "with": {"path": "lab"}}},
    {"id": "verify_change",
     "since": "0.4", "platforms": ["frr"],
     "when": "When no checks exist and a ticket states what the change is meant to do: declare that intent, and "
             "anything else that changes in the routing state fails.",
     "does": "Boots the lab with the before configs and with the after configs, snapshots sessions, routes of every "
             "protocol, every BGP path and every advertisement, and fails on any difference the intent doesn't "
             "declare. An approval needs each side booted twice with identical snapshots.",
     "mcp": {"tool": "verify_change",
             "arguments": {"topology": "/path/to/lab/topology.clab.yml", "before": "main", "after": "/path/to/lab-after",
                           "intent": "intent:\n  - prefix: 10.101.0.0/24\n    appears_on: [edge1, up1, peer1]\n"}},
     "cli": "netdryrun verify topology.clab.yml --before main --after HEAD --intent netdryrun-intent.yml --json report.json",
     "github_action": {"uses": "netdryrun/Netdryrun@vVERSION",
                       "with": {"mode": "verify", "topology": "lab/topology.clab.yml",
                                "intent-file": "netdryrun-intent.yml"}}},
    {"id": "record_baseline",
     "when": "No checks and no stated intent: capture today's behavior as checks, then run them against the change.",
     "does": "Reads sessions and routes from a lab and returns checks as YAML; writes nothing.",
     "mcp": {"tool": "record_baseline", "arguments": {"topology": "/path/to/lab/topology.clab.yml"}},
     "cli": "netdryrun record /path/to/lab/topology.clab.yml --deploy"},
    {"id": "validate",
     "when": "Before a run: check a netdryrun.yml and its topology without starting a lab.",
     "mcp": {"tool": "validate", "arguments": {"path": "/path/to/lab"}},
     "cli": "netdryrun validate /path/to/lab"},
]

PREREQUISITES = [
    "Linux, or Windows with WSL2; not macOS",
    "Docker and containerlab, with root-equivalent rights (labs run privileged containers)",
    "Python 3.10 to 3.14 (pipx install netdryrun, or uvx netdryrun mcp)",
    "Not inside a sandbox without Docker-in-Docker; there, open a pull request and let the GitHub Action run it",
    "Images: FRR and SR Linux are public; SONiC needs docker-sonic-vs; Arista EOS needs your own cEOS image",
    "A lab of the network (a containerlab topology and its configs); Netdryrun never connects to real devices",
]

LIMITS = [
    "A pass of dry_run covers only what the checks look at; behavior no check covers is not tested.",
    "verify_change covers the observed control-plane state of the lab (BGP sessions, routes of every protocol, "
    "every BGP path, advertised and received routes), nothing else: no data plane beyond ping checks.",
    "verify_change is FRR only in 0.4; the topology must be identical on both sides.",
    "verify_change: an intent explains what it declares, leaks included; the intent must come from the ticket or "
    "the operator, never from the diff.",
    "verify_change: received routes are compared before inbound policy without their communities (FRR doesn't list "
    "them there); a default-originate advertisement is compared by presence, not by its attributes.",
    "verify_change: IPv4 and IPv6 unicast only; sessions carrying other address families, and unnumbered BGP "
    "neighbors, are refused (exit 2).",
    "Settle and hold stretch to the longest BGP advertisement interval a driver reads, except on Arista EOS, where "
    "a configured out-delay is not read yet: raise --settle and --hold above it there (planned for 0.4.1).",
    "A route that crosses several peers with long advertisement intervals can take one interval per hop, and "
    "update-delay is not read: raise --settle for those.",
    "A lab whose state never settles gives INCONCLUSIVE (exit 3): this says nothing about the change; retry at "
    "most once, then escalate.",
    "afi: evpn is refused on Arista EOS and Nokia SR Linux.",
    "verify_change does not observe nodes passed as unobserved (hosts), IGP adjacency state (OSPF and IS-IS routes are "
    "compared, their adjacencies are not), or the data plane beyond a standing guard's ping checks: an undeclared "
    "change there does not fail.",
    "record covers every active VRF on FRR and SONiC; on Nokia SR Linux and Arista EOS it records the default VRF "
    "only, with a warning.",
]

EXIT_CODES = {
    "run": {"0": "passed", "1": "failed", "2": "error (no verdict)", "3": "inconclusive"},
    "verify": {"0": "matched or no_change", "1": "failed (undeclared changes, a declaration that didn't happen, or a "
               "failed standing guard)", "2": "error (no verdict)", "3": "inconclusive or unhealthy_baseline"},
}

DOCS = {
    "ai_agents": "https://netdryrun.com/ai-agents/",
    "verify": "https://netdryrun.com/reference/verify/",
    "cli": "https://netdryrun.com/reference/cli/",
    "config": "https://netdryrun.com/reference/config/",
    "github_action": "https://netdryrun.com/github-action/",
    "mcp_result_schema": "https://netdryrun.com/schemas/mcp-result-v1.json",
    "verify_report_schema": "https://netdryrun.com/schemas/verify-v1.json",
    "agents_md": "https://github.com/netdryrun/Netdryrun/blob/main/AGENTS.md",
    "llms_txt": "https://netdryrun.com/llms.txt",
}


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _assigned(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise SystemExit(f"capabilities: no {name} in the source")


def facts() -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sync_facts

    f = sync_facts.facts()
    mcp = _module(SRC / "agent_result.py")
    run_verdicts = [ast.literal_eval(_assigned(mcp, n)) for n in ("CHECKS_PASSED", "DO_NOT_APPLY", "INCONCLUSIVE")]
    verify_verdicts = list(ast.literal_eval(_assigned(_module(SRC / "verify" / "report.py"), "VERDICTS")).values())
    return {**f, "run_verdicts": run_verdicts, "verify_verdicts": verify_verdicts}


def platform_limits(f: dict) -> list[str]:
    """Each released platform's limits, as recorded with the compatibility matrix (tests/compat_verified.json),
    named by platform."""
    verified = json.loads((ROOT / "tests" / "compat_verified.json").read_text(encoding="utf-8"))
    return [f"{names[2]}: {limit}" for driver, names in zip(f["drivers"], f["platforms"], strict=True)
            for limit in verified.get(driver, {}).get("limits", [])]


def render(f: dict | None = None) -> str:
    f = f or facts()
    version = f["version"]
    use_cases = json.loads(json.dumps(USE_CASES).replace("@vVERSION", f"@v{version}"))
    doc = {
        "schema": SCHEMA,
        "url": URL,
        "name": "Netdryrun",
        "version": version,
        "summary": "Netdryrun dry-runs a network change in a real containerlab lab before it reaches production, and "
                   "returns a verdict with evidence. verify_change (0.4, FRR): declare what you intend to change; "
                   "anything else that changes in the routing state fails the run.",
        "use_cases": use_cases,
        "prerequisites": PREREQUISITES,
        "limits": LIMITS + platform_limits(f),
        "platforms": [{"driver": d, "name": p[0]} for d, p in zip(f["drivers"], f["platforms"], strict=True)],
        "mcp": {"install": ["uvx netdryrun mcp", "claude mcp add netdryrun -- netdryrun mcp"],
                "transport": "stdio", "tools": f["mcp_tools"], "registry_name": "io.github.netdryrun/netdryrun"},
        "check_types": f["check_types"],
        "verdicts": {"run": f["run_verdicts"], "verify": f["verify_verdicts"],
                     "decide_on": "status, never the verdict text"},
        "exit_codes": EXIT_CODES,
        "never": ["connects to real devices", "sends telemetry or uploads anything by default (the GitHub Action's "
                  "reserved cloud input is off)", "writes or weakens checks or intents for you"],
        "docs": DOCS,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(render(), end="")
