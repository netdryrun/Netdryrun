"""The false-passes corpus (corpus/v3-false-passes) is well-formed and honest, offline."""
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "corpus" / "v3-false-passes"


def load(name):
    spec = importlib.util.spec_from_file_location(f"v3_{name}", V3 / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


check = load("check_cases")
runner = load("run_cases")


def test_every_case_passes_the_offline_check_and_the_manifest_matches():
    assert check.main() == 0


def test_no_case_expects_a_pass():
    cases = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in V3.glob("cases/*/case.yml")]
    assert len(cases) == 8
    for c in cases:
        assert c["expected"]["status"] != "passed" and c["expected"]["exit_code"] != 0, c["id"]
        assert c["live_verified"] is False                # nothing is claimed as run until it has been
    assert {c["id"].split("-")[0] for c in cases} == {f"{i:02d}" for i in range(1, 9)}


def test_the_checker_rejects_a_case_that_expects_a_pass(tmp_path, monkeypatch):
    src = V3 / "cases" / "01-rejected-config-line"
    case = tmp_path / "cases" / "01-rejected-config-line"
    case.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(src, case)
    cy = case / "case.yml"
    cy.write_text(cy.read_text(encoding="utf-8").replace("status: error", "status: passed").replace("exit_code: 2", "exit_code: 0"),
                  encoding="utf-8")
    errs = check.check_case(case)
    assert any("never expects a pass" in e for e in errs) and any("exit code 0" in e for e in errs)


def test_the_checker_catches_an_edited_expectation(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "MANIFEST", tmp_path / "MANIFEST.sha256")
    (tmp_path / "MANIFEST.sha256").write_text("deadbeef  cases/01/case.yml\n", encoding="utf-8")
    assert check.main() == 1


@pytest.mark.parametrize("version,skipped", [("0.3.3", True), ("0.4.0", False), ("0.4.1", False)])
def test_old_versions_are_not_expected_to_give_the_new_verdict(version, skipped):
    case = V3 / "cases" / "03-link-local-next-hop-typo"
    c = yaml.safe_load((case / "case.yml").read_text(encoding="utf-8"))
    row = runner.run_case(case, c, version, dry=True)
    assert (row["result"] == "skipped") is skipped


def test_the_action_case_is_never_run_here_and_the_judge_checks_exit_code_and_messages():
    case = V3 / "cases" / "07-pr-edits-its-own-workflow"
    c = yaml.safe_load((case / "case.yml").read_text(encoding="utf-8"))
    assert runner.run_case(case, c, "9.9.9", dry=False)["result"] == "skipped"
    c01 = yaml.safe_load((V3 / "cases" / "01-rejected-config-line" / "case.yml").read_text(encoding="utf-8"))
    ok = "ERROR: FRR rejected configuration lines at boot: r1: line 21: neighbor 10.0.12.2 default-orignate"
    assert runner.judge(c01, 2, ok) == []
    assert runner.judge(c01, 0, "PASSED: 7 passed") != []
    assert runner.judge(c01, 2, "ERROR: something else") != []
