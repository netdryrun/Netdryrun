"""Keep every public fact about Netdryrun in sync with the source.

The facts are derived, never typed by hand:
  version      src/netdryrun/__init__.py (__version__)
  platforms    src/netdryrun/drivers/__init__.py (DRIVERS), named by PLATFORMS below
  check types  src/netdryrun/config.py (CHECK_TYPES)
  MCP tools    src/netdryrun/mcp_server.py (@mcp.tool functions)
  corpus       corpus/results/results.json (pre-registered scores)

They are written into marked blocks (<!-- facts:NAME -->...<!-- /facts:NAME -->), the version
fields of server.json, the GitHub Action refs in the docs, the netdryrun==VERSION pins of the GitLab
CI/CD component and its docs, and website/docs/llms-full.txt.

  python scripts/sync_facts.py           rewrite everything
  python scripts/sync_facts.py --check   exit 1 on any drift or stale phrase (CI)
  python scripts/sync_facts.py --json    print the facts
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "netdryrun"

# driver name -> (long, medium, short). A new driver without an entry here fails the script.
PLATFORMS = {
    "frr": ("FRR", "FRR", "FRR"),
    "srlinux": ("Nokia SR Linux", "Nokia SR Linux", "SR Linux"),
    "sonic": ("SONiC (docker-sonic-vs)", "SONiC", "SONiC"),
    "eos": ("Arista EOS (cEOS, bring your own image)", "Arista EOS (bring your own cEOS image)", "Arista EOS"),
}

# Public files the stale-phrase lint reads.
PUBLIC = ["README.md", "AGENTS.md", "templates/netdryrun.yml", "website/docs/llms.txt", "website/docs/llms-full.txt",
          *sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "website" / "docs").rglob("*.md"))]


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _assigned(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return node.value
    raise SystemExit(f"sync_facts: {name} not found")


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def facts() -> dict:
    version = ast.literal_eval(_assigned(_module(SRC / "__init__.py"), "__version__"))
    drivers = [k.value for k in _assigned(_module(SRC / "drivers" / "__init__.py"), "DRIVERS").keys]
    if set(drivers) != set(PLATFORMS):
        raise SystemExit(f"sync_facts: DRIVERS {sorted(drivers)} != PLATFORMS {sorted(PLATFORMS)}; name the new platform in PLATFORMS")
    check_types = [k.value for k in _assigned(_module(SRC / "config.py"), "CHECK_TYPES").keys]
    mcp_tools = [n.name for n in _module(SRC / "mcp_server.py").body if isinstance(n, ast.FunctionDef)
                 and any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool" for d in n.decorator_list)]

    return {"version": version, "platforms": [PLATFORMS[d] for d in PLATFORMS], "drivers": list(PLATFORMS),
            "check_types": check_types, "mcp_tools": mcp_tools,
            "corpus": _corpus(ROOT / "corpus" / "results" / "results.json"),
            "corpus_v2": _corpus(ROOT / "corpus" / "v2" / "results" / "results.json")}


def _corpus(path: Path) -> dict:
    results = json.loads(path.read_text(encoding="utf-8"))
    cases = results["cases"]
    corpus = {"cases": len(cases), "harmful": sum(c["expected"] == "unsafe" for c in cases),
              "generated": results["environment"]["generated"][:10], "ran_with": results["environment"]["netdryrun"]}
    for strategy in ("netdryrun", "ping", "sessions"):
        corpus[strategy] = sum(bool(c["strategies"][strategy]["correct"]) for c in cases)
    corpus["losses"] = [{"id": c["id"], "title": c["title"], "expected": c["expected"]}
                        for c in cases if not c["strategies"]["netdryrun"]["correct"]]
    return corpus


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def blocks(f: dict) -> dict[str, str]:
    long_, mid, short = (_join([p[i] for p in f["platforms"]]) for i in range(3))
    c = f["corpus"]
    scores = f"Netdryrun {c['netdryrun']}/{c['cases']}, ping-only {c['ping']}/{c['cases']}, sessions-up {c['sessions']}/{c['cases']}"
    c2 = f["corpus_v2"]
    ran = _join(sorted({c["ran_with"], c2["ran_with"]}))
    corpus_sentence = (f"On the {{link}}, Netdryrun judged {c['netdryrun']}/{c['cases']} realistic BGP changes correctly "
                       f"(ping-only checks {c['ping']}/{c['cases']}, all-sessions-up checks {c['sessions']}/{c['cases']}) and "
                       f"{c2['netdryrun']}/{c2['cases']} on the harder v2 ({c2['ping']}/{c2['cases']} and {c2['sessions']}/{c2['cases']}). "
                       f"Both are small benchmarks the maintainers wrote on one FRR topology, with expected verdicts committed "
                       f"before any run, and both ran on Netdryrun {ran}: they compare methods, they are not a production "
                       "reliability estimate.")
    losses = {kind: [x for x in c["losses"] if x["expected"] == kind] for kind in ("unsafe", "safe")}
    checks = _join([f"`{t}`" for t in f["check_types"]])
    attrs = "bgp_route" in f["check_types"]  # BGP best-path attribute checks exist
    covers = "BGP sessions, prefix counts, " + ("routes, BGP best-path attributes and ping" if attrs else "routes and ping")
    tools = _join([f"`{t}`" for t in f["mcp_tools"]])
    v = f["version"]
    return {
        "readme_status": (f"> Status: **v{v}, early.** Works today with {long_} on Linux and WSL2. "
                          + corpus_sentence.format(link="[verdict corpus](https://netdryrun.com/corpus/)")
                          + " Feedback and issues are very welcome."),
        "site_status": (f"Version {v}, early. Works with {mid} on Linux and WSL2. Check types: {checks} "
                        f"(IPv4/IPv6 unicast {covers}), plus link-down and node-isolation failure scenarios. "
                        + corpus_sentence.format(link="[verdict corpus](corpus.md)")
                        + " Issues and feedback: [github.com/netdryrun/netdryrun](https://github.com/netdryrun/netdryrun/issues)."),
        "when_status": (f"It is early (version {v}). Drivers exist for {mid}, and checks cover {covers}, "
                        "with link-down and node-isolation failure scenarios."),
        "llms_summary": (f"> Netdryrun is an open-source tool (Python, Apache-2.0) that tests network changes in a real containerlab "
                         "virtual lab before they reach production. It waits for convergence, checks BGP sessions, prefixes, routes and "
                         f"reachability, and returns a pass/fail verdict with evidence. Supported network OSes: {long_}. "
                         "It runs locally, in GitHub Actions, or as an MCP server for AI agents.\n\n"
                         f"Install: `pip install netdryrun` (current version {v}). Source: https://github.com/netdryrun/netdryrun\n\n"
                         f"Facts (generated from the source): version {v}; check types {checks}; MCP tools {tools}; "
                         f"verdict corpus {scores}."),
        "llms_corpus": (f"- [Verdict corpus](https://netdryrun.com/corpus/): {c['cases']} realistic BGP changes with pre-registered "
                        f"verdicts; {scores} correct"),
        "trust_scope": (f"Version {v} also covers only BGP (IPv4/IPv6 unicast), routes"
                        + (", BGP best-path attributes" if attrs else "") + " and ping, plus link-down and node-isolation "
                        "failure scenarios. OSPF/IS-IS adjacencies and path checks"
                        + ("" if attrs else " and policy attributes") + " are not covered yet."),
        "built_losses": (f"**Verdict Corpus v1: wrong on {len(c['losses'])} of {c['cases']} cases.** It approved "
                         f"{_count(len(losses['unsafe']), 'harmful change')} and blocked {_count(len(losses['safe']), 'safe one')} "
                         f"([RESULTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/RESULTS.md))."),
        "agents_platforms": short,
        "faq_platforms": long_,
        "mcp_tools": tools,
    }


def sync_blocks(text: str, values: dict[str, str], where: str, problems: list[str]) -> str:
    def repl(m: re.Match) -> str:
        name, body = m.group(1), m.group(2)
        if name not in values:
            problems.append(f"{where}: unknown facts block {name!r}")
            return m.group(0)
        value = values[name]
        if body.startswith("\n"):        # block form keeps its own lines
            value = f"\n{value}\n"
        return f"<!-- facts:{name} -->{value}<!-- /facts:{name} -->"
    return re.sub(r"<!-- facts:(\w+) -->(.*?)<!-- /facts:\1 -->", repl, text, flags=re.S)


# Phrases that were once true and must not come back. Each is (regex, why).
def stale_patterns(f: dict) -> list[tuple[str, str]]:
    v = re.escape(f["version"])
    return [
        (rf"netdryrun/netdryrun@v(?!{v}\b)\d+\.\d+\.\d+", "GitHub Action pinned to an old release"),
        (rf"netdryrun==(?!{v}\b)\d+\.\d+\.\d+", "GitLab component pinned to an old release"),
        (rf"(?i)\bversion (?!{v}\b)0\.\d+\.\d+", "old Netdryrun version"),
        (r"(?i)results? (?:are )?(?:pending|forthcoming)|coming soon", "corpus results are published"),
        (r"(?i)only (?:for )?FRR and (?:Nokia )?SR ?Linux|FRR and (?:Nokia )?SR Linux on Linux", "platform list is out of date"),
        (r"(?i)\bv0\.1 covers", "old version scope"),
        (r"(?i)licensed vendor images is on the roadmap", "Arista cEOS (bring your own image) is supported"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if anything is out of sync")
    ap.add_argument("--json", action="store_true", help="print the facts as JSON and exit")
    args = ap.parse_args()
    f = facts()
    if args.json:
        print(json.dumps(f, indent=2))
        return 0
    values, problems, changed = blocks(f), [], {}

    for rel in ("README.md", "AGENTS.md", "website/docs/index.md", "website/docs/when-to-use-what.md",
                "website/docs/llms.txt", "website/docs/github-action.md", "website/docs/trust.md",
                "website/docs/how-its-built.md", "website/docs/ai-agents.md", "website/docs/faq.md",
                "website/docs/tutorial.md", "website/docs/examples.md", "website/docs/troubleshooting.md",
                "website/docs/gitlab-ci.md", "templates/netdryrun.yml"):
        path = ROOT / rel
        old = path.read_text(encoding="utf-8")
        new = sync_blocks(old, values, rel, problems)
        new = re.sub(r"netdryrun/netdryrun@v\d+\.\d+\.\d+", f"netdryrun/netdryrun@v{f['version']}", new)
        new = re.sub(r"netdryrun==\d+\.\d+\.\d+", f"netdryrun=={f['version']}", new)
        if new != old:
            changed[rel] = new

    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    old_server = json.dumps(server)
    server["version"] = f["version"]
    for pkg in server.get("packages", []):
        if pkg.get("identifier") == "netdryrun":
            pkg["version"] = f["version"]
    if json.dumps(server) != old_server:
        text = (ROOT / "server.json").read_text(encoding="utf-8")
        changed["server.json"] = re.sub(r'("version": ")[^"]*(")', rf'\g<1>{f["version"]}\g<2>', text)

    # llms-full.txt is built from the docs, so build it after the docs are synced.
    for rel, text in changed.items():
        if not args.check:
            (ROOT / rel).write_text(text, encoding="utf-8", newline="\n")
    sys.path.insert(0, str(ROOT / "website"))
    import build_llms_full
    if args.check and changed:
        problems += [f"{rel}: out of sync with the source" for rel in changed]
    else:
        full = build_llms_full.build()
        full_path = ROOT / "website" / "docs" / "llms-full.txt"
        if full != full_path.read_text(encoding="utf-8"):
            if args.check:
                problems.append("website/docs/llms-full.txt: out of date (run python scripts/sync_facts.py)")
            else:
                full_path.write_text(full, encoding="utf-8", newline="\n")
                changed["website/docs/llms-full.txt"] = full

    for rel in PUBLIC:
        path = ROOT / rel
        if not path.exists():
            continue
        text = changed.get(rel) or path.read_text(encoding="utf-8")
        for pattern, why in stale_patterns(f):
            for m in re.finditer(pattern, text):
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{rel}:{line}: stale phrase {m.group(0)!r} ({why})")

    for p in problems:
        print(p, file=sys.stderr)
    if args.check:
        print(f"facts: {'DRIFT' if problems else 'in sync'} (version {f['version']}, {len(problems)} problem(s))")
    else:
        print(f"facts: rewrote {', '.join(changed) or 'nothing'}" + (f"; {len(problems)} problem(s) need a manual fix" if problems else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
