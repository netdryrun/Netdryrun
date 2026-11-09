#!/usr/bin/env python3
"""Every public surface names the same platforms and version (0.4.2 priority 4).

0.4.1 shipped the NX-OS and RouterOS drivers while scripts/sync_facts.py still listed them as UNRELEASED, so the
generated docs left them out, the GitHub description named them, and three official places disagreed. sync_facts
--check couldn't see it: it compares the docs with what PLATFORMS says, not PLATFORMS with what shipped. This does.

  static      (release gate, static layer, BLOCKER; no network)
              - every driver the last release tag shipped, and that the code still has, is in PLATFORMS, not UNRELEASED;
              - on a release (--release), UNRELEASED is empty;
              - README status, AGENTS.md, llms.txt, the FAQ, the home page, the site's structured data, the
                compatibility matrix (a row and a check-type column per platform), capabilities.json, server.json and
                pyproject keywords name exactly the released platforms (a surface that names none, like server.json's
                one-line description, is fine; one that names some must name all, and nothing unreleased).
  published   (after-publish layer, and weekly; read-only HTTP GETs)
              the GitHub repository description, PyPI's latest release (version, status line), the MCP Registry's
              latest entry, LobeHub's listing and netdryrun.com/llms.txt name the expected version and platforms.

Fail-closed: a surface that can't be read, a block that is missing, a driver with no name pattern, or no release tag
to compare with is a problem, never a pass. Exit 0 agree, 1 disagree, 2 couldn't run.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sync_facts  # noqa: E402

# How each driver's platform is named in prose, keywords and listings. A driver without an entry fails the check.
TOKENS = {
    "frr": r"\bFRR\b",
    "srlinux": r"\bSR ?Linux\b",
    "sonic": r"\bSONiC\b",
    "eos": r"\b(?:Arista|c?EOS)\b",
    "junos": r"\b(?:Juniper|c?Junos\w*)\b",
    "nxos": r"\b(?:NX-?OS|Nexus)\b",
    "routeros": r"\b(?:RouterOS|MikroTik)\b",
}
BLOCKS = {   # surface -> (file, facts block)
    "README status": ("README.md", "readme_status"),
    "AGENTS.md platforms": ("AGENTS.md", "agents_platforms"),
    "llms.txt summary": ("website/docs/llms.txt", "llms_summary"),
    "FAQ platforms": ("website/docs/faq.md", "faq_platforms"),
    "home page status": ("website/docs/index.md", "site_status"),
}
UA = "netdryrun-surfaces-check (+https://github.com/netdryrun/Netdryrun)"


def named(text: str) -> set[str]:
    return {d for d, pat in TOKENS.items() if re.search(pat, text, re.I)}


def agree(surface: str, text: str, released: set[str], unreleased: set[str], must_name: bool = True) -> list[str]:
    got = named(text)
    if not got and not must_name:
        return []
    out = []
    if released - got:
        out.append(f"{surface}: doesn't name {', '.join(sorted(released - got))} (it names {', '.join(sorted(got)) or 'none'})")
    extra = got - released
    if extra:
        out.append(f"{surface}: names {', '.join(sorted(extra))}, which sync_facts doesn't list as released"
                   + (" (it's in UNRELEASED)" if extra <= unreleased else ""))
    return out


# ---- static ---------------------------------------------------------------------------------------------------------
def drivers_in(source: str) -> list[str]:
    tree = ast.parse(source)
    return [k.value for k in sync_facts._assigned(tree, "DRIVERS").keys]


def last_release(root: Path, git=None) -> tuple[str, list[str]]:
    """The newest v* tag and the drivers it shipped (its drivers/__init__.py DRIVERS)."""
    git = git or (lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, timeout=60))
    try:
        tags = git("tag", "--list", "v*", "--sort=-v:refname")
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"git isn't available to read the last release ({e})") from None
    tag = next((t for t in tags.stdout.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)), None) if tags.returncode == 0 else None
    if not tag:
        raise RuntimeError("no release tag (v*) to compare with: fetch the tags (fetch-depth 0) and run again")
    src = git("show", f"{tag}:src/netdryrun/drivers/__init__.py")
    if src.returncode != 0:
        raise RuntimeError(f"can't read {tag}'s drivers: {src.stderr.strip()[:200]}")
    return tag, drivers_in(src.stdout)


def block(text: str, name: str) -> str | None:
    m = re.search(rf"<!-- facts:{name} -->(.*?)<!-- /facts:{name} -->", text, re.S)
    return m.group(1) if m else None


def compat_sets(text: str) -> tuple[set[str], set[str]]:
    """Drivers with a row in the platform table, and drivers with a column in the check-type table."""
    rows, cols = set(), set()
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells[:1] == ["Platform"]:
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                rows |= named(row.split("|")[1])
        if cells[:1] == ["Check type"]:
            cols |= {d for c in cells[1:] for d in named(c)}
    return rows, cols


def static_problems(root: Path = ROOT, release: bool = False, git=None) -> list[str]:
    problems = []
    current = drivers_in((root / "src" / "netdryrun" / "drivers" / "__init__.py").read_text(encoding="utf-8"))
    platforms, unreleased = set(sync_facts.PLATFORMS), set(sync_facts.UNRELEASED)
    problems += [f"driver {d} has no name pattern in surfaces_agree.TOKENS" for d in current if d not in TOKENS]
    released = platforms - unreleased
    try:
        tag, shipped = last_release(root, git)
        stuck = sorted(d for d in set(shipped) & set(current) if d not in platforms)
        problems += [f"{d} shipped in {tag} but sync_facts lists it as UNRELEASED: move it to PLATFORMS, or every "
                     "generated surface leaves it out" for d in stuck]
    except RuntimeError as e:
        problems.append(f"last release: {e}")
    if release and unreleased:
        problems.append(f"this is a release, but sync_facts.UNRELEASED still lists {', '.join(sorted(unreleased))}: "
                        "move what ships to PLATFORMS, take the rest out of DRIVERS")
    for surface, (rel, name) in BLOCKS.items():
        p = root / rel
        body = block(p.read_text(encoding="utf-8"), name) if p.exists() else None
        if body is None:
            problems.append(f"{surface}: no <!-- facts:{name} --> block in {rel}")
            continue
        problems += agree(f"{surface} ({rel})", body, released, unreleased)
    html = (root / "website" / "overrides" / "main.html").read_text(encoding="utf-8")
    m = re.search(r"Supported network operating systems: [^.\"]*\.", html)
    problems += (agree("site structured data (website/overrides/main.html)", m.group(0), released, unreleased) if m
                 else ["site structured data (website/overrides/main.html): no 'Supported network operating systems' line"])
    rows, cols = compat_sets((root / "website" / "docs" / "reference" / "compatibility.md").read_text(encoding="utf-8"))
    for what, got in (("platform rows", rows), ("check-type columns", cols)):
        if got != released:
            problems.append(f"compatibility.md {what}: {', '.join(sorted(got)) or 'none'}; released: "
                            f"{', '.join(sorted(released))}")
    caps = json.loads((root / "website" / "docs" / "capabilities.json").read_text(encoding="utf-8"))
    got = {p.get("driver") for p in caps.get("platforms") or []}
    if got != released:
        problems.append(f"capabilities.json platforms: {', '.join(sorted(map(str, got))) or 'none'}; released: "
                        f"{', '.join(sorted(released))}")
    server = json.loads((root / "server.json").read_text(encoding="utf-8"))
    problems += agree("server.json description", server.get("description", ""), released, unreleased, must_name=False)
    py = (root / "pyproject.toml").read_text(encoding="utf-8")
    kw = re.search(r"(?ms)^keywords\s*=\s*\[(.*?)\]", py)
    problems += (agree("pyproject.toml keywords", kw.group(1), released, unreleased, must_name=False) if kw
                 else ["pyproject.toml: no keywords list"])
    return problems


# ---- published ------------------------------------------------------------------------------------------------------
def http_get(url: str, accept: str = "*/*") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def published_problems(version: str, released: set[str], unreleased: set[str], get=http_get) -> list[str]:
    problems = []

    def read(surface: str, url: str, accept: str = "*/*") -> str | None:
        try:
            return get(url, accept)
        except Exception as e:   # any failure to read is a problem, never a pass
            problems.append(f"{surface}: couldn't read {url} ({type(e).__name__}: {str(e)[:120]})")
            return None

    gh = read("GitHub repository description", "https://github.com/netdryrun/Netdryrun")
    if gh is not None:
        m = re.search(r'<meta name="description" content="([^"]*)"', gh)
        problems += (agree("GitHub repository description", m.group(1), released, unreleased) if m
                     else ["GitHub repository description: no description meta tag on the repository page"])

    pypi = read("PyPI", "https://pypi.org/pypi/netdryrun/json")
    if pypi is not None:
        try:
            info = json.loads(pypi)["info"]
            if info.get("version") != version:
                problems.append(f"PyPI: the latest release is {info.get('version')!r}, expected {version}")
            m = re.search(r"Status: \*\*v([\d.]+?)\.?\*\*.*?drivers for ([^.]*(?:\([^)]*\)[^.]*)*)\.",
                          info.get("description") or "", re.S)
            if not m:
                problems.append("PyPI: the project description has no 'Status: **vX.Y.Z.** ... drivers for ...' line")
            else:
                if m.group(1) != version:
                    problems.append(f"PyPI: the description's status line says v{m.group(1)}, expected v{version}")
                problems += agree("PyPI description status line", m.group(2), released, unreleased)
            problems += agree("PyPI summary", info.get("summary") or "", released, unreleased, must_name=False)
        except (ValueError, KeyError, TypeError) as e:
            problems.append(f"PyPI: unreadable JSON ({e})")

    reg = read("MCP Registry", "https://registry.modelcontextprotocol.io/v0/servers?search=io.github.netdryrun/netdryrun")
    if reg is not None:
        try:
            entries = json.loads(reg).get("servers") or []
            latest = [e for e in entries if ((e.get("_meta") or {}).get("io.modelcontextprotocol.registry/official")
                                             or {}).get("isLatest")]
            if len(latest) != 1:
                problems.append(f"MCP Registry: {len(latest)} entries marked latest, expected 1")
            else:
                s = latest[0].get("server", latest[0])
                if s.get("version") != version:
                    problems.append(f"MCP Registry: the latest entry is {s.get('version')!r}, expected {version}")
                problems += agree("MCP Registry description", s.get("description") or "", released, unreleased,
                                  must_name=False)
        except (ValueError, AttributeError) as e:
            problems.append(f"MCP Registry: unreadable JSON ({e})")

    lobe = read("LobeHub", "https://lobehub.com/mcp/netdryrun-netdryrun", "text/markdown")   # its listing as Markdown
    if lobe is not None:
        m = re.search(r"\|\s*Version\s*\|\s*([^|\s]+)\s*\|", lobe)
        if not m:
            problems.append("LobeHub: no version on the listing page")
        elif m.group(1) != version:
            problems.append(f"LobeHub: the listing shows version {m.group(1)}, expected {version}")

    llms = read("netdryrun.com llms.txt", "https://netdryrun.com/llms.txt")
    if llms is not None:
        if not re.search(rf"current version {re.escape(version)}\b", llms):
            found = re.search(r"current version ([\d.]*\d)", llms)
            problems.append(f"netdryrun.com llms.txt: says version {found.group(1) if found else 'nothing'}, "
                            f"expected {version}")
        m = re.search(r"Supported network OSes: (.*?)\.\s", llms, re.S)
        problems += (agree("netdryrun.com llms.txt platforms", m.group(1), released, unreleased) if m
                     else ["netdryrun.com llms.txt: no 'Supported network OSes:' sentence"])
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("static")
    s.add_argument("--release", action="store_true", help="this is a release: UNRELEASED must be empty")
    p = sub.add_parser("published")
    p.add_argument("--version", help="the version every surface must name (default: the source's)")
    args = ap.parse_args(argv)
    try:
        f = sync_facts.facts()
    except SystemExit as e:
        print(f"ERROR {e}")
        return 2
    released, unreleased = set(f["drivers"]), set(sync_facts.UNRELEASED)
    problems = (static_problems(release=args.release) if args.cmd == "static"
                else published_problems(args.version or f["version"], released, unreleased))
    for x in problems:
        print(f"DISAGREE {x}")
    print(f"surfaces {args.cmd}: {'agree' if not problems else f'{len(problems)} problem(s)'}"
          f" (version {args.version if args.cmd == 'published' and args.version else f['version']}, platforms "
          f"{', '.join(sorted(released))})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
