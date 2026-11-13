"""Gate layers may differ only in the gate's records or in prose, and only if static ran on the newest commit."""
from types import SimpleNamespace
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate"] = gate
spec.loader.exec_module(gate)


def fake_git(ancestors: set, diffs: dict):
    def git(*args):
        if args[0] == "merge-base":
            return "" if (args[2], args[3]) in ancestors else None
        if args[0] == "diff":
            return diffs[(args[2], args[3])]
        raise AssertionError(args)
    return git


def test_prose_only(monkeypatch):
    """Prose is Markdown no layer but static reads (Layer 6 change-impact review, 2026-11-13): live reads examples.md,
    acceptance runs README.md and lints every docs YAML block, and the tests pin sentences in the CHANGELOG and the
    advisories, so those are never prose-only; a file the code or tests name isn't either, nor one git can't answer for."""
    named = {"CHANGELOG.md", "advisories/x/README.md"}
    def run(cmd, timeout=60):
        path = cmd[cmd.index("-F") + 1]
        return SimpleNamespace(code=0 if path in named else 128 if path == "broken.md" else 1,
                               out="HEAD:tests/t.py" if path in named else "")
    monkeypatch.setattr(gate, "run", run)
    assert gate.prose_only("design/notes.md") and gate.prose_only("advisories/y/README.md")
    for p in ("README.md", "AGENTS.md", "website/docs/examples.md", "website/docs/reference/cli.md",
              "website/docs/llms-full.txt", "CHANGELOG.md", "advisories/x/README.md", "broken.md",
              "src/netdryrun/runner.py", "tests/README.md", "scripts/x.md", ".github/workflows/ci.yml",
              "advisories/x/1.yml", "website/mkdocs.yml", "pyproject.toml"):
        assert not gate.prose_only(p), p


def test_same_commit_is_fine():
    assert gate.code_differs({"static": "a", "unit": "a", "live": "a"}) is None


def test_prose_change_after_the_code_layers_is_allowed_when_static_is_newest(monkeypatch):
    monkeypatch.setattr(gate, "git", fake_git({("old", "new")}, {("old", "new"): "design/notes.md\nreleases/0.3.1/GATE.md"}))
    monkeypatch.setattr(gate, "run", lambda cmd, timeout=60: SimpleNamespace(code=1, out=""))   # nothing names it
    assert gate.code_differs({"static": "new", "unit": "old", "mutation": "old", "live": "old"}) is None


def test_a_docs_file_a_layer_reads_is_never_prose(monkeypatch):
    """Live reads examples.md, acceptance runs README.md: an edit there after those layers passed blocks (Layer 6
    change-impact review, 2026-11-13)."""
    for path in ("README.md", "website/docs/examples.md"):
        monkeypatch.setattr(gate, "git", fake_git({("old", "new")}, {("old", "new"): path}))
        assert "different code" in gate.code_differs({"static": "new", "live": "old"}), path


def test_code_change_between_layers_blocks(monkeypatch):
    monkeypatch.setattr(gate, "git", fake_git({("old", "new")}, {("old", "new"): "README.md\nsrc/netdryrun/runner.py"}))
    assert "different code" in gate.code_differs({"static": "new", "mutation": "old"})


def test_static_must_be_the_newest(monkeypatch):
    monkeypatch.setattr(gate, "git", fake_git(set(), {}))
    assert "not an ancestor" in gate.code_differs({"static": "old", "live": "new"})


def test_missing_static_record_blocks():
    assert "static layer" in gate.code_differs({"unit": "a", "live": "b"})
