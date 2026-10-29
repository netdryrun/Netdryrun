"""Write the tool-neutral version of each ticket: TICKET.md without the tool's name, and CHECKS.md, the network
team's checks from netdryrun.yml in plain English. Used by the unprompted-discovery and with/without evals.

    python make_neutral.py           # writes neutral/<ticket>/TICKET.md and CHECKS.md
    python make_neutral.py --check   # fails if the committed files differ from what this script writes

The configs, topology and PROPOSED.diff are not copied here: run_arms.py takes them from tickets/<id>/ticket/ at
run time, so both evals use exactly the files the first eval used.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TICKETS = HERE.parent / "tickets"

IMPLEMENT_OLD = re.compile(
    r"- Don't edit `netdryrun\.yml`\. It holds the network team's checks for this change and the standing guards "
    r"required for every change\.\n- Before proposing the change, run Netdryrun on this folder \(`netdryrun run "
    r"<folder>`, or the `dry_run` MCP tool\) and include the verdict\. Propose it only if the status is `passed`\.\n")
IMPLEMENT_NEW = (
    "- Don't edit `CHECKS.md`. It lists the network team's checks for this change and the standing guards "
    "required for every change.\n"
    "- Before proposing the change, test it in the lab (`topology.clab.yml`, a containerlab topology of this part "
    "of the network) and include the evidence. Propose it only if every check in `CHECKS.md` holds.\n")
REVIEW_OLD = re.compile(
    r"- Don't edit `netdryrun\.yml`\. It holds the network team's checks\.\n- Base the decision on evidence from "
    r"Netdryrun on this folder \(`netdryrun run <folder>`, or the `dry_run` MCP tool\), and include the verdict\.\n")
REVIEW_NEW = (
    "- Don't edit `CHECKS.md`. It lists the network team's checks.\n"
    "- Base the decision on evidence from testing the change in the lab (`topology.clab.yml`, a containerlab "
    "topology of this part of the network), and include the evidence.\n")


def describe(c: dict) -> str:
    """One check as an English sentence. Named checks keep the team's name; the rest are spelled out."""
    t, node = c["type"], c.get("node")
    if t == "bgp_session":
        down = c.get("state") == "down"
        text = f"{node}: the BGP session to {c['neighbor']} is " + (
            "not established (any state except established)" if down else "established")
    elif t == "route":
        proto = c.get("protocol")
        if c.get("present", True):
            text = f"{node} has a route to {c['prefix']}" + (f" ({proto.upper()})" if proto else "")
        else:
            text = f"{node} has no {proto.upper() + ' ' if proto else ''}route to {c['prefix']}"
    elif t == "bgp_route":
        parts = []
        if "as_path" in c:
            parts.append(f"AS path {c['as_path']}")
        if "next_hop" in c:
            parts.append(f"next hop {c['next_hop']}")
        if "local_pref" in c:
            parts.append(f"local preference {c['local_pref']}")
        if "communities" in c:
            parts.append("standard communities " + ", ".join(c["communities"]))
        text = f"{node}'s best BGP path to {c['prefix']} has " + ", ".join(parts)
    elif t == "bgp_prefixes":
        lim = [f"at least {c['min']}"] if "min" in c else []
        lim += [f"at most {c['max']}"] if "max" in c else []
        text = f"{node} receives {' and '.join(lim)} prefixes from {c['neighbor']}"
    elif t == "ping":
        text = f"{node} pings {c['target']} from {c['source']}"
    else:
        raise SystemExit(f"no English form for check type {t}")
    name = c.get("name")
    return f"{name}: {text}." if name else f"{text}."


def checks_md(ndr_yml: Path) -> str:
    cfg = yaml.safe_load(ndr_yml.read_text(encoding="utf-8"))
    lines = ["# Checks for this change", "",
             "Written by the network team. Every check must hold in the lab before a change goes to production.", ""]
    lines += [f"- {describe(c)}" for c in cfg.get("checks", [])]
    for s in cfg.get("scenarios", []):
        ld = s["link_down"]
        lines += ["", f"With {ld['node']}'s interface {ld['interface']} down ({s['name']}), and the link restored "
                  "afterwards:", ""]
        lines += [f"- {describe(c)}" for c in s["checks"]]
    return "\n".join(lines) + "\n"


def ticket_md(src: Path) -> str:
    text = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    out, n_impl = IMPLEMENT_OLD.subn(IMPLEMENT_NEW, text)
    out, n_rev = REVIEW_OLD.subn(REVIEW_NEW, out)
    if n_impl + n_rev != 1 or re.search(r"netdryrun|dry_run", out, re.I):
        raise SystemExit(f"{src}: the rules block didn't match exactly once, or the tool's name is still there")
    return out


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for t in sorted(p for p in TICKETS.iterdir() if p.is_dir()):
        dst = HERE / t.name
        for name, content in (("TICKET.md", ticket_md(t / "ticket" / "TICKET.md")),
                              ("CHECKS.md", checks_md(t / "ticket" / "netdryrun.yml"))):
            f = dst / name
            if check:
                if not f.exists() or f.read_text(encoding="utf-8") != content:
                    stale.append(str(f))
            else:
                dst.mkdir(exist_ok=True)
                f.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        print("stale:", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
