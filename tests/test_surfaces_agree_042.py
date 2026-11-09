"""scripts/surfaces_agree.py (0.4.2 priority 4): every surface names the platforms that shipped, fail-closed.

0.4.1 shipped NX-OS and RouterOS while scripts/sync_facts.py still listed them as UNRELEASED: the generated docs left
them out, the GitHub description named them, and three official places disagreed (an outside review found it). Each
test below is one way that can happen again; the static ones run on a copy of this repo's real surfaces."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("surfaces_agree", ROOT / "scripts" / "surfaces_agree.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["surfaces_agree"] = mod
    spec.loader.exec_module(mod)
    return mod


sa = load()
FILES = ["README.md", "AGENTS.md", "website/docs/llms.txt", "website/docs/faq.md", "website/docs/index.md",
         "website/overrides/main.html", "website/docs/reference/compatibility.md", "website/docs/capabilities.json",
         "server.json", "pyproject.toml", "src/netdryrun/drivers/__init__.py"]


@pytest.fixture
def tree(tmp_path):
    for rel in FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    return tmp_path


def fake_git(tag="v9.9.9", drivers=None, tags_rc=0):
    """A git that knows one release tag, which shipped `drivers` (default: what the code has and PLATFORMS names)."""
    shipped = drivers if drivers is not None else [d for d in sa.sync_facts.PLATFORMS]
    src = "DRIVERS = {" + ", ".join(f'"{d}": None' for d in shipped) + "}\n"

    def git(*args):
        if args[:2] == ("tag", "--list"):
            return types.SimpleNamespace(returncode=tags_rc, stdout=f"{tag}\n" if tag else "", stderr="")
        if args[0] == "show":
            return types.SimpleNamespace(returncode=0, stdout=src, stderr="")
        raise AssertionError(args)
    return git


def edit(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8")
    assert old in text, (path, old)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_this_repo_agrees(tree):
    assert sa.static_problems(tree, git=fake_git()) == []


def test_a_driver_that_shipped_but_is_listed_unreleased_blocks(tree, monkeypatch):
    """The 0.4.1 bug: nxos was in the release tag's DRIVERS and in UNRELEASED."""
    monkeypatch.setattr(sa.sync_facts, "UNRELEASED", {**sa.sync_facts.UNRELEASED, "nxos": ("a", "b", "c")})
    monkeypatch.setattr(sa.sync_facts, "PLATFORMS", {k: v for k, v in sa.sync_facts.PLATFORMS.items() if k != "nxos"})
    shipped = [*sa.sync_facts.PLATFORMS, "nxos"]
    problems = sa.static_problems(tree, git=fake_git(drivers=shipped))
    assert any("nxos shipped in v9.9.9 but sync_facts lists it as UNRELEASED" in p for p in problems), problems


def test_a_release_with_anything_unreleased_blocks(tree, monkeypatch):
    monkeypatch.setattr(sa.sync_facts, "UNRELEASED", {"xos": ("X", "X", "X")})
    problems = sa.static_problems(tree, release=True, git=fake_git())
    assert any("UNRELEASED still lists xos" in p for p in problems), problems


@pytest.mark.parametrize("tags_rc,tag", [(0, ""), (128, "v1.0.0")])
def test_no_release_tag_to_compare_with_blocks(tree, tags_rc, tag):
    problems = sa.static_problems(tree, git=fake_git(tag=tag, tags_rc=tags_rc))
    assert any(p.startswith("last release:") for p in problems), problems


def test_git_missing_blocks(tree):
    def git(*a):
        raise FileNotFoundError("git")
    assert any(p.startswith("last release:") for p in sa.static_problems(tree, git=git))


def test_a_status_block_that_leaves_a_platform_out_blocks(tree):
    edit(tree / "AGENTS.md", "SONiC, ", "")
    problems = sa.static_problems(tree, git=fake_git())
    assert any(p.startswith("AGENTS.md platforms") and "doesn't name sonic" in p for p in problems), problems


def test_a_surface_naming_an_unreleased_platform_blocks(tree, monkeypatch):
    monkeypatch.setattr(sa.sync_facts, "UNRELEASED", {**sa.sync_facts.UNRELEASED, "nxos": ("Cisco NX-OS", "", "")})
    monkeypatch.setattr(sa.sync_facts, "PLATFORMS", {k: v for k, v in sa.sync_facts.PLATFORMS.items() if k != "nxos"})
    path = tree / "website" / "docs" / "faq.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("<!-- facts:faq_platforms -->") + len("<!-- facts:faq_platforms -->")
    path.write_text(text[:start] + "Cisco NX-OS, " + text[start:], encoding="utf-8")
    shipped = [d for d in sa.sync_facts.PLATFORMS]
    problems = sa.static_problems(tree, git=fake_git(drivers=shipped))
    assert any("FAQ platforms" in p and "names nxos" in p for p in problems), problems


def test_a_missing_facts_block_blocks(tree):
    edit(tree / "README.md", "<!-- facts:readme_status -->", "<!-- facts:readme_status_gone -->")
    assert any("no <!-- facts:readme_status --> block" in p for p in sa.static_problems(tree, git=fake_git()))


def test_the_compatibility_matrix_needs_a_row_and_a_column_per_platform(tree):
    path = tree / "website" / "docs" / "reference" / "compatibility.md"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines(keepends=True) if not ln.startswith("| SONiC |")]
    path.write_text("".join(lines), encoding="utf-8")
    problems = sa.static_problems(tree, git=fake_git())
    assert any(p.startswith("compatibility.md platform rows") for p in problems), problems


def test_capabilities_json_must_list_every_released_platform(tree):
    path = tree / "website" / "docs" / "capabilities.json"
    caps = json.loads(path.read_text(encoding="utf-8"))
    caps["platforms"] = [p for p in caps["platforms"] if p["driver"] != "frr"]
    path.write_text(json.dumps(caps), encoding="utf-8")
    assert any(p.startswith("capabilities.json platforms") for p in sa.static_problems(tree, git=fake_git()))


def test_pyproject_keywords_that_name_platforms_name_them_all(tree):
    edit(tree / "pyproject.toml", '"juniper",', "")
    problems = sa.static_problems(tree, git=fake_git())
    assert any(p.startswith("pyproject.toml keywords") and "junos" in p for p in problems), problems


def test_a_driver_without_a_name_pattern_blocks(tree, monkeypatch):
    monkeypatch.setattr(sa, "TOKENS", {k: v for k, v in sa.TOKENS.items() if k != "frr"})
    assert "driver frr has no name pattern in surfaces_agree.TOKENS" in sa.static_problems(tree, git=fake_git())


# ---- published ------------------------------------------------------------------------------------------------------
V = "0.4.2"
REL = {"frr", "srlinux", "sonic", "eos", "junos", "nxos", "routeros"}
NAMES = "FRR, Nokia SR Linux, SONiC, Arista EOS, Juniper (beta), Cisco NX-OS (beta) and MikroTik RouterOS (beta)"


def pages(**over):
    base = {
        "https://github.com/netdryrun/Netdryrun": f'<meta name="description" content="Dry-run network changes. {NAMES}.">',
        "https://pypi.org/pypi/netdryrun/json": json.dumps({"info": {
            "version": V, "summary": "Validate BGP and routing changes in a real containerlab lab.",
            "description": f"> Status: **v{V}.** Runs on Linux and WSL2, with drivers for {NAMES}. On the corpus ..."}}),
        "https://registry.modelcontextprotocol.io/v0/servers?search=io.github.netdryrun/netdryrun": json.dumps({"servers": [
            {"server": {"version": "0.4.1", "description": "x"},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": False}}},
            {"server": {"version": V, "description": "Validate BGP and routing changes."},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}}]}),
        "https://lobehub.com/mcp/netdryrun-netdryrun": f"| Field | Value |\n| Version    | {V}   |\n",
        "https://netdryrun.com/llms.txt": f"Supported network OSes: {NAMES}. It runs locally.\ncurrent version {V}). x",
    }
    base.update(over)

    def get(url, accept="*/*"):
        v = base[url]
        if isinstance(v, Exception):
            raise v
        return v
    return get


def published(**over):
    return sa.published_problems(V, REL, set(), get=pages(**over))


def test_published_surfaces_that_agree_pass():
    assert published() == []


def test_the_github_description_naming_fewer_platforms_is_red():
    p = published(**{"https://github.com/netdryrun/Netdryrun": '<meta name="description" content="FRR and SR Linux.">'})
    assert any(x.startswith("GitHub repository description: doesn't name") for x in p), p


def test_pypi_on_an_older_version_or_status_line_is_red():
    old = json.dumps({"info": {"version": "0.4.1", "summary": "s",
                               "description": f"> Status: **v0.4.1.** Runs on Linux, with drivers for {NAMES}. x"}})
    p = published(**{"https://pypi.org/pypi/netdryrun/json": old})
    assert any("PyPI: the latest release is '0.4.1'" in x for x in p) and any("status line says v0.4.1" in x for x in p)


def test_pypi_without_a_status_line_is_red():
    page = json.dumps({"info": {"version": V, "summary": "s", "description": "no status here"}})
    assert any("no 'Status: **vX.Y.Z.**" in x for x in published(**{"https://pypi.org/pypi/netdryrun/json": page}))


def test_a_hostile_pypi_description_cant_stall_the_status_regex():
    """CodeQL py/redos on PR #6: the old pattern backtracked exponentially on 'drivers for ' plus many '()'."""
    page = json.dumps({"info": {"version": V, "summary": "s",
                                "description": "Status: **v.**drivers for " + "()" * 50000}})
    assert any("no 'Status: **vX.Y.Z.**" in x for x in published(**{"https://pypi.org/pypi/netdryrun/json": page}))


def test_a_registry_whose_latest_is_another_version_is_red():
    reg = json.dumps({"servers": [{"server": {"version": "0.4.1", "description": "d"},
                                   "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}}]})
    p = published(**{"https://registry.modelcontextprotocol.io/v0/servers?search=io.github.netdryrun/netdryrun": reg})
    assert any("MCP Registry: the latest entry is '0.4.1'" in x for x in p), p


def test_a_stale_lobehub_listing_is_red():
    p = published(**{"https://lobehub.com/mcp/netdryrun-netdryrun": "| Version    | 0.3.1   |"})
    assert any("LobeHub: the listing shows version 0.3.1" in x for x in p), p


def test_llms_txt_with_old_platforms_is_red():
    page = "Supported network OSes: FRR, Nokia SR Linux, SONiC, Arista EOS and Juniper (beta). x\ncurrent version 0.4.2)"
    p = published(**{"https://netdryrun.com/llms.txt": page})
    assert any(x.startswith("netdryrun.com llms.txt platforms: doesn't name nxos, routeros") for x in p), p


def test_a_surface_that_cant_be_read_is_red_never_a_pass():
    p = published(**{"https://lobehub.com/mcp/netdryrun-netdryrun": OSError("timed out")})
    assert any(x.startswith("LobeHub: couldn't read") for x in p), p


def test_exit_codes(tmp_path):
    script = ROOT / "scripts" / "surfaces_agree.py"
    r = subprocess.run([sys.executable, str(script), "nope"], capture_output=True, text=True)
    assert r.returncode == 2
