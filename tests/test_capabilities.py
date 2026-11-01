"""The machine-readable capability statement (website/docs/capabilities.json, https://netdryrun.com/capabilities.json):
generated from the source, so it can't drift, and referenced wherever an agent looks first (server.json, AGENTS.md,
llms.txt, the MCP server's instructions)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import capabilities  # noqa: E402

from netdryrun import __version__  # noqa: E402
from netdryrun.config import CHECK_TYPES  # noqa: E402
from netdryrun.drivers import DRIVERS  # noqa: E402
from netdryrun.verify.report import VERDICTS as VERIFY_VERDICTS  # noqa: E402

DOC = json.loads(capabilities.PAGE.read_text(encoding="utf-8"))


def test_the_published_file_is_the_generated_one():
    assert capabilities.PAGE.read_text(encoding="utf-8") == capabilities.render(), "run python scripts/sync_facts.py"


def test_its_facts_are_the_codes():
    mcp_server = pytest.importorskip("netdryrun.mcp_server")
    assert DOC["schema"] == "netdryrun.capabilities/v1" and DOC["url"] == capabilities.URL
    assert DOC["version"] == __version__
    from sync_facts import UNRELEASED   # public facts follow releases: an unreleased driver isn't listed yet
    assert {p["driver"] for p in DOC["platforms"]} == set(DRIVERS) - set(UNRELEASED)
    assert DOC["check_types"] == list(CHECK_TYPES)
    assert DOC["verdicts"]["run"] == list(mcp_server.VERDICT_ENUM)
    assert DOC["verdicts"]["verify"] == list(VERIFY_VERDICTS.values())
    tools = set(DOC["mcp"]["tools"])
    assert {"dry_run", "verify_change", "record_baseline", "validate"} <= tools
    for uc in DOC["use_cases"]:
        if "mcp" in uc:
            assert uc["mcp"]["tool"] in tools
            import inspect
            params = inspect.signature(getattr(mcp_server, uc["mcp"]["tool"])).parameters
            assert set(uc["mcp"]["arguments"]) <= set(params), uc["id"]
        if "github_action" in uc:
            assert uc["github_action"]["uses"] == f"netdryrun/Netdryrun@v{__version__}"


def test_every_use_case_says_when_and_how():
    for uc in DOC["use_cases"]:
        assert uc["when"] and uc["cli"].startswith("netdryrun ") and ("mcp" in uc), uc["id"]
    assert DOC["prerequisites"] and DOC["limits"] and DOC["exit_codes"]["run"] and DOC["exit_codes"]["verify"]


def test_the_known_limits_are_stated():
    limits = " ".join(DOC["limits"])
    for phrase in ("only what the checks look at", "FRR only", "out-delay", "INCONCLUSIVE", "never from the diff"):
        assert phrase in limits, phrase


def test_it_is_referenced_where_agents_look_first():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["_meta"]["io.modelcontextprotocol.registry/publisher-provided"]["capabilities"] == capabilities.URL
    for rel in ("AGENTS.md", "website/docs/llms.txt", "website/docs/ai-agents.md"):
        assert capabilities.URL in (ROOT / rel).read_text(encoding="utf-8"), rel
    mcp_server = pytest.importorskip("netdryrun.mcp_server")
    assert capabilities.URL in (mcp_server.mcp.instructions or "")


def test_each_released_platforms_verified_limits_are_in_the_statement():
    """The per-platform limits recorded with the compatibility matrix (tests/compat_verified.json) reach the
    capability statement, named by platform, for every released platform (Juniper beta included from 0.4)."""
    import sync_facts

    verified = json.loads((ROOT / "tests" / "compat_verified.json").read_text(encoding="utf-8"))
    limits = DOC["limits"]
    for driver, names in sync_facts.PLATFORMS.items():
        for limit in verified.get(driver, {}).get("limits", []):
            assert f"{names[2]}: {limit}" in limits, (driver, limit)
    assert any(x.startswith("Juniper (beta): ") for x in limits)


def test_a_link_to_the_pre_rename_repository_is_a_stale_phrase_but_the_registry_name_is_not():
    """The repository is netdryrun/Netdryrun since 2026-10-31; the MCP Registry name keeps the old spelling."""
    import re

    import sync_facts

    def stale(text):
        return [why for pat, why in sync_facts.stale_patterns({"version": __version__})
                if "renamed" in why and re.search(pat, text)]

    assert stale("see https://github.com/netdryrun/netdryrun/issues")
    assert stale(f"uses: netdryrun/netdryrun@v{__version__}")
    assert not stale("see https://github.com/netdryrun/Netdryrun/issues")
    assert not stale("the MCP Registry name io.github.netdryrun/netdryrun")
