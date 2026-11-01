"""After-publish and the nightly gate: every public place names the released version, or the check names each
place that doesn't (PyPI, the GitHub latest release, main's README status line, Action refs and published-action.yml
RELEASE, the website, the MCP Registry). All I/O is faked here: the gate makes one bounded request per source."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate"] = gate
spec.loader.exec_module(gate)

V = "0.3.3"
NAME = "io.github.netdryrun/netdryrun"
ACTION = ".github/workflows/published-action.yml"
NOTES = ("**The agent runtime.** 0.3.3 lets an AI agent get a verdict without local Docker.\n\n"
         "**Full Changelog**: https://github.com/netdryrun/Netdryrun/compare/v0.3.2...v0.3.3")
# what `gh release create --generate-notes` (release.yml) writes before the notes are pasted
GENERATED = ("## What's Changed\n* Agent runtime by @someone in https://github.com/netdryrun/Netdryrun/pull/12\n\n"
             "## New Contributors\n* @someone made their first contribution in "
             "https://github.com/netdryrun/Netdryrun/pull/12\n\n"
             "**Full Changelog**: https://github.com/netdryrun/Netdryrun/compare/v0.3.2...v0.3.3")


def registry(latest, listed=("0.3.2",)):
    servers = [{"server": {"name": NAME, "version": v},
                "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": v == latest}}}
               for v in sorted({*listed, latest} - {None})]
    return json.dumps({"servers": servers, "metadata": {"count": len(servers)}})


def sources(v=V, *, pypi=None, github=None, home=None, llms=None, reg=None):
    """url -> (HTTP status, body): every source on version v unless overridden."""
    return {
        "https://pypi.org/pypi/netdryrun/json": (200, json.dumps({"info": {"version": pypi or v}})),
        "https://api.github.com/repos/netdryrun/Netdryrun/releases/latest":
            github if isinstance(github, tuple) else (200, json.dumps({"tag_name": f"v{github or v}",
                                                                       "body": NOTES})),
        "https://netdryrun.com/": home or (200, f'<script>{{"softwareVersion": "{v}"}}</script>'
                                                f"<p>Version {v}.</p><code>uses: netdryrun/Netdryrun@v{v}</code>"),
        "https://netdryrun.com/llms.txt": llms or (200, f"current version {v}). Facts: version {v};"),
        f"https://registry.modelcontextprotocol.io/v0/servers?search={NAME}": reg or (200, registry(v)),
    }


def main_files(v=V, **extra):
    files = {
        "README.md": f"# Netdryrun\n\n<!-- facts:readme_status -->\n> Status: **v{v}.** Runs on Linux.\n",
        ACTION: f'name: Published release\nenv:\n  RELEASE: "{v}"\njobs:\n  - uses: netdryrun/Netdryrun@v{v}\n',
        "website/docs/github-action.md": f"x\n```yaml\n- uses: netdryrun/Netdryrun@v{v}\n```\n",
    }
    files.update(extra)
    return files


def check(get=None, main=None, strict=False):
    layer = gate.Layer("after-publish", SimpleNamespace(strict=strict, version=V))
    web = get if get is not None else sources()
    gate.release_consistency(layer, V, get=lambda url: web.get(url, (None, "")),
                             main=lambda: main_files() if main is None else main)
    return {c.id: c for c in layer.checks}


def test_everything_on_the_release_passes():
    checks = check()
    assert set(checks) == {"latest-pypi", "latest-github", "main-version", "site-version", "mcp-registry"}
    assert all(c.status == gate.PASS for c in checks.values()), {i: c.summary for i, c in checks.items()}
    assert all(c.severity == gate.BLOCKER for c in checks.values())


def test_pypi_latest_behind_is_named():
    c = check(sources(pypi="0.3.2"))["latest-pypi"]
    assert c.status == gate.FAIL and "0.3.2" in c.summary


def test_github_latest_release_behind_is_named():
    c = check(sources(github="0.3.2"))["latest-github"]
    assert c.status == gate.FAIL and "v0.3.2" in c.summary


def test_no_github_release_marked_latest_fails():
    c = check(sources(github=(404, '{"message": "Not Found"}')))["latest-github"]
    assert c.status == gate.FAIL and "no release" in c.summary


@pytest.mark.parametrize("body", [None, "", "  \n", GENERATED])
def test_a_latest_release_with_only_generated_notes_fails(body):
    release = json.dumps({"tag_name": f"v{V}", "body": body})
    c = check(sources(github=(200, release)))["latest-github"]
    assert c.status == gate.FAIL and "notes" in c.summary


def test_registry_latest_must_be_the_release_not_just_listed():
    c = check(sources(reg=(200, registry("0.3.2", listed=(V,)))))["mcp-registry"]
    assert c.status == gate.FAIL and "0.3.2" in c.summary


def test_registry_without_the_release_fails():
    c = check(sources(reg=(200, registry("0.3.2"))))["mcp-registry"]
    assert c.status == gate.FAIL


def test_each_place_on_main_that_says_another_version_is_named_with_its_line():
    old = main_files("0.3.2")
    old["website/docs/guide.md"] = "a\nb\n  uses: netdryrun/netdryrun@v0.3.1\n"   # the pre-rename spelling still counts
    c = check(main=old)["main-version"]
    assert c.status == gate.FAIL
    for where in ("README.md:4", f"{ACTION}:3", f"{ACTION}:5", "website/docs/github-action.md:3",
                  "website/docs/guide.md:3"):
        assert where in c.output, where
    assert "netdryrun/netdryrun@v0.3.1" in c.output and "RELEASE 0.3.2" in c.output


def test_history_on_main_keeps_its_old_versions():
    files = main_files(**{"CHANGELOG.md": "keeps running `uses: netdryrun/netdryrun@v0.3.0`\n",
                          "advisories/0.3.2-rejected-config/README.md": "the `netdryrun/netdryrun@v0.3.2` Action\n",
                          "releases/0.3.1/gate/static.json": "netdryrun/netdryrun@v0.3.1\n"})
    assert check(main=files)["main-version"].status == gate.PASS


def test_old_refs_in_test_fixtures_on_main_are_ignored():
    # this very file holds old Action refs as fixtures; once on main it must not page the nightly
    files = main_files(**{"tests/test_release_gate_consistency.py": "netdryrun/Netdryrun@v0.3.1\n"})
    assert check(main=files)["main-version"].status == gate.PASS


def test_a_missing_status_line_or_release_pin_fails():
    files = main_files()
    files["README.md"] = "# Netdryrun\n"
    files[ACTION] = "name: Published release\n"
    c = check(main=files)["main-version"]
    assert c.status == gate.FAIL and "status line" in c.output and "RELEASE" in c.output


def test_site_pages_name_each_old_version_with_the_page():
    c = check(sources(home=(200, '{"softwareVersion": "0.3.2"} uses: netdryrun/Netdryrun@v0.3.3 Version 0.3.3.')))
    c = c["site-version"]
    assert c.status == gate.FAIL and "https://netdryrun.com/" in c.output and "0.3.2" in c.output


def test_a_site_page_that_names_no_version_fails():
    c = check(sources(llms=(200, "Netdryrun validates BGP changes.")))["site-version"]
    assert c.status == gate.FAIL and "llms.txt" in c.output


def test_an_old_release_named_as_history_on_the_site_is_not_the_version():
    # provenance and advisories name past releases without saying "version"
    c = check(sources(llms=(200, f"version {V}. Provenance: both ran on Netdryrun 0.3.1.")))["site-version"]
    assert c.status == gate.PASS


@pytest.mark.parametrize("url_part", ["pypi.org", "api.github.com", "netdryrun.com/llms", "registry."])
def test_an_unreachable_source_is_skipped_never_passed(url_part):
    web = {u: ((None, "") if url_part in u else r) for u, r in sources().items()}
    checks = check(web)
    skipped = [i for i, c in checks.items() if c.status == gate.SKIP]
    assert len(skipped) == 1, {i: c.status for i, c in checks.items()}


def test_an_unreadable_main_is_skipped_and_fails_under_strict():
    assert check(main={})["main-version"].status == gate.FAIL   # read, but no status line and no RELEASE pin
    layer = gate.Layer("after-publish", SimpleNamespace(strict=True, version=V))
    gate.release_consistency(layer, V, get=lambda url: sources().get(url), main=lambda: None)
    c = {c.id: c for c in layer.checks}["main-version"]
    assert c.status == gate.FAIL and "skipped under --strict" in c.summary


def test_an_unparseable_answer_fails():
    web = sources()
    web["https://pypi.org/pypi/netdryrun/json"] = (200, "<html>maintenance</html>")
    assert check(web)["latest-pypi"].status == gate.FAIL


def test_the_nightly_runs_it_as_its_own_layer_outside_the_release_record(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(gate, "release_consistency", lambda layer, v, **kw: calls.append(v))
    layer = gate.RUNNERS["consistency"](SimpleNamespace(strict=True, version=V))
    assert calls == [V] and layer.name == "consistency"
    assert "consistency" not in gate.LAYERS   # never a layer the release record waits for
    assert layer.record()["title"]


def test_after_publish_runs_it(monkeypatch):
    calls = []
    monkeypatch.setattr(gate, "release_consistency", lambda layer, v, **kw: calls.append(v))
    monkeypatch.setattr(gate, "http_status", lambda url: 200)
    monkeypatch.setattr(gate, "after_publish_live", lambda *a: None)
    monkeypatch.setattr(gate.shutil, "which", lambda name: None)
    gate.layer_after_publish(SimpleNamespace(strict=False, version=V, pythons=[]))
    assert calls == [V]
