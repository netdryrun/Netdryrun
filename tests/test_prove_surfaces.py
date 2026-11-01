"""`netdryrun prove` and MCP `prove_checks`: exit codes, the netdryrun.prove/v1 report against its JSON Schema, the
two surfaces agreeing, and a tool description that claims no more than the tool does."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from netdryrun import cli, mcp_server
from netdryrun.prove import LIVE_PENDING, prove_config
from netdryrun.prove import report as preport
from netdryrun.prove.variants import leak_prefixes
from netdryrun.runner import load_config

import prove_helpers as h

jsonschema = pytest.importorskip("jsonschema")
SCHEMA = json.loads((Path(__file__).parents[1] / "website" / "docs" / "schemas" / "prove-v1.json").read_text(
    encoding="utf-8"))
FILTER = "import_filter:edge:CUST-IN permit 10:match ip address prefix-list CUST-IN:+leak:cust"


def valid(data: dict) -> dict:
    jsonschema.Draft202012Validator(SCHEMA).validate(data)
    return data


@pytest.fixture
def lab(tmp_path):
    shutil.copytree(h.FIXTURE, tmp_path / "lab")
    return tmp_path / "lab"


def executor_for(cfg, which="survivor"):
    """A fake executor for the fixture lab: the filter variant survives (old checks), or nothing is set up."""
    from netdryrun.prove import core
    from netdryrun.prove.variants import generate

    base = h.custleak()
    vs = {v.id: v for v in generate({n: ns.config for n, ns in base.nodes.items()}, h.LINKS, cfg.checks,
                                    core._counts(base))}
    states = {FILTER: h.applied(vs[FILTER], h.custleak(cust_extra=["100.64.0.0/24"], edge_filter=None)),
              "session_down:cust:10.0.1.1": h.applied(vs["session_down:cust:10.0.1.1"], h.custleak(down=("ce",))),
              "customer_leak:cust:1": h.applied(vs["customer_leak:cust:1"], h.custleak(cust_extra=leak_prefixes(1)))}
    return h.FakeExecutor(base, states if which == "survivor" else {})


# ---------------------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------------------

def test_plan_lists_variants_and_starts_no_lab(lab, capsys):
    assert cli.main(["prove", str(lab), "--plan", "--max", "3"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("3 variant(s) would run, 22 more generated (raise --max):")
    assert "customer_leak:cust:1" in out and FILTER in out and "No lab was started" in out


def test_plan_with_kinds(lab, capsys):
    assert cli.main(["prove", str(lab / "netdryrun.yml"), "--plan", "--variants", "link_down, session_down"]) == 0
    out = capsys.readouterr().out
    assert "4 variant(s) would run, 0 more" in out and "customer_leak" not in out


def test_plan_bad_kind_is_exit_2(lab, capsys):
    assert cli.main(["prove", str(lab), "--plan", "--variants", "nope"]) == 2
    assert "unknown variant kind(s) nope" in capsys.readouterr().err


def test_a_live_run_is_not_in_this_build(lab, capsys, tmp_path):
    out = tmp_path / "r.json"
    assert cli.main(["prove", str(lab), "--json", str(out)]) == 2
    text = capsys.readouterr().out
    assert "ERROR: NO STRENGTH RESULT" in text and "phase 2" in text and "caught" not in text
    data = valid(json.loads(out.read_text(encoding="utf-8")))
    assert data["status"] == "error" and data["error"] == LIVE_PENDING and data["error_kind"] == "setup"
    assert data["exit_code"] == 2 and data["variants"] == [] and data["counts"]["caught"] == 0


def test_config_error_is_exit_2(tmp_path, capsys):
    assert cli.main(["prove", str(tmp_path / "missing")]) == 2
    assert "not found" in capsys.readouterr().err


def test_a_lab_with_a_node_prove_cannot_read_is_refused(lab, capsys):
    topo = (lab / "topology.clab.yml").read_text(encoding="utf-8")
    (lab / "topology.clab.yml").write_text(topo.replace("    up: {binds: [configs/up.conf:/etc/frr/frr.conf]}",
                                                        "    up: {kind: nokia_srlinux, image: ghcr.io/nokia/srlinux}"),
                                           encoding="utf-8")
    assert cli.main(["prove", str(lab), "--plan"]) == 2
    assert "node up runs srlinux: prove reads FRR nodes only" in capsys.readouterr().err
    assert cli.main(["prove", str(lab)]) == 2


def test_a_bridge_is_no_routing_node(lab, capsys):
    topo = (lab / "topology.clab.yml").read_text(encoding="utf-8")
    (lab / "topology.clab.yml").write_text(topo.replace("  links:", "    br: {kind: bridge}\n  links:"), encoding="utf-8")
    assert cli.main(["prove", str(lab), "--plan"]) == 0


def test_an_unreadable_config_file_is_refused(lab, capsys):
    (lab / "configs" / "up.conf").unlink()
    assert cli.main(["prove", str(lab), "--plan"]) == 2
    assert "the config of up" in capsys.readouterr().err


def test_an_unreadable_topology_is_refused(lab, capsys):
    (lab / "topology.clab.yml").write_text("name: [unclosed", encoding="utf-8")
    assert cli.main(["prove", str(lab), "--plan"]) == 2


def test_cli_with_an_executor(lab, capsys, monkeypatch, tmp_path):
    import netdryrun.prove as prove_pkg
    real = prove_pkg.prove_config
    monkeypatch.setattr(prove_pkg, "prove_config", lambda cfg, **kw: real(cfg, executor=executor_for(cfg), **kw))
    out = tmp_path / "r.json"
    assert cli.main(["prove", str(lab), "--variants", "import_filter", "--max", "1", "--json", str(out)]) == 1
    text = capsys.readouterr().out
    assert "BLIND SPOTS FOUND" in text and "[SURVIVED]" in text and "suggested (review it)" in text
    assert "prove never edits netdryrun.yml" in text
    data = valid(json.loads(out.read_text(encoding="utf-8")))
    assert data["counts"] == {"caught": 0, "survived": 1, "no_effect": 0, "inconclusive": 0, "run": 1, "generated": 25,
                              "not_run": 3}
    assert data["by_kind"] == {"import_filter": {"caught": 0, "survived": 1, "no_effect": 0, "inconclusive": 0}}
    (lab / "netdryrun.yml").chmod(0o444)   # never written
    assert cli.main(["prove", str(lab), "--variants", "import_filter", "--max", "1", "--json", str(lab)]) == 2
    assert "could not write" in capsys.readouterr().err


def test_the_checks_file_is_never_edited(lab, monkeypatch):
    before = (lab / "netdryrun.yml").read_bytes()
    cfg = load_config(lab)
    rep = prove_config(cfg, executor=executor_for(cfg), maximum=3)
    assert rep.variants and (lab / "netdryrun.yml").read_bytes() == before


# ---------------------------------------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------------------------------------

def test_reports_of_every_status_match_the_schema(lab):
    cfg = load_config(lab)
    survivor = prove_config(cfg, executor=executor_for(cfg), kinds=["import_filter"], maximum=1)
    caught = prove_config(cfg, executor=executor_for(cfg), kinds=["session_down"], maximum=1)
    no_effect = prove_config(cfg, executor=executor_for(cfg), kinds=["customer_leak"], maximum=1)
    error = prove_config(cfg, executor=executor_for(cfg, "none"), kinds=["import_filter"], maximum=1)
    for rep, status, code in ((survivor, "failed", 1), (caught, "passed", 0), (no_effect, "inconclusive", 3),
                              (error, "error", 2)):
        data = valid(preport.to_dict(rep))
        assert (data["status"], data["exit_code"], rep.exit_code) == (status, code, code)
        assert data["verdict"] == preport.VERDICTS[status]
        assert json.loads(preport.to_json(rep)) == data
    c = preport.to_dict(caught)["variants"][0]
    assert c["result"] == "caught" and c["failed_checks"] and all(f["evidence"] for f in c["failed_checks"])
    assert "effect" in c and c["effect_items"] >= 1
    assert "suggested_checks" not in c
    e = preport.to_dict(error)
    assert e["variants"] == [] and e["by_kind"] == {} and e["error_kind"] == "apply"
    assert "no strength result" in e["summary"] and "caught" not in e["summary"]


def test_an_error_after_variants_ran_keeps_them_out_of_the_results(lab):
    cfg = load_config(lab)
    ex = executor_for(cfg)
    ex.side_after["session_down:cust:10.0.1.1"] = {"edge kernel routes": "a route left behind"}
    rep = prove_config(cfg, executor=ex, maximum=8)
    data = valid(preport.to_dict(rep))
    assert data["status"] == "error" and data["error_kind"] == "restore"
    assert "edge kernel routes (outside the snapshot)" in data["error"]
    assert data["variants"] == [] and data["counts"]["run"] == 0 and len(data["partial"]) >= 1
    text = preport.console(rep)
    assert "destroy it before any other run" in text and "[caught]" not in text


def test_console_text(lab):
    cfg = load_config(lab)
    rep = prove_config(cfg, executor=executor_for(cfg), kinds=["import_filter", "session_down", "customer_leak"],
                       maximum=3)
    text = preport.console(rep)
    lines = text.splitlines()
    assert lines[0] == preport.VERDICTS["failed"]
    assert lines[1].startswith("caught 1 of 2 known-bad variants with an effect (1 survived, 0 inconclusive; 1 more "
                               "had no effect on routing)")
    assert "By kind: customer_leak 0 caught, 0 survived, 1 no effect; import_filter 0 caught, 1 survived, 0 no " \
           "effect; session_down 1 caught, 0 survived, 0 no effect" in text
    assert "  [caught] cust: BGP session to 10.0.1.1 (edge) shut down" in text
    assert "      failed: " in text and "      unnoticed: edge 100.64.0.0/24 path from 10.0.1.2 added" in text
    assert "  [no effect] cust announces 1 extra prefix(es)" in text
    assert "not run (budget, raise --max)" in text and "Add a check that catches each survivor" in text


def test_a_long_effect_and_evidence_are_cut(lab):
    from netdryrun.prove.core import VariantResult
    from netdryrun.prove.variants import Variant
    from netdryrun.verify.engine import DiffItem
    from netdryrun.verify.snapshot import ItemKey

    items = [DiffItem(ItemKey("vrf", "edge", f"v{i}"), None, True) for i in range(30)]
    v = VariantResult(Variant("x", "link_down", "edge", "d"), "survived", effect=items)
    j = preport.variant_json(v)
    assert len(j["effect"]) == preport.MAX_EFFECT and j["effect_items"] == 30
    assert j["effect"][0] == {"where": "edge vrf v0", "change": "added", "before": None, "after": "True"}


# ---------------------------------------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------------------------------------

def test_prove_checks_without_a_live_executor_is_an_error(lab):
    data = valid(json.loads(mcp_server.prove_checks(str(lab))))
    assert data["status"] == "error" and data["error"] == LIVE_PENDING


def test_prove_checks_config_error(tmp_path):
    data = valid(json.loads(mcp_server.prove_checks(str(tmp_path / "nope"))))
    assert data["status"] == "error" and data["verdict"] == preport.VERDICTS["error"] and data["schema"] == preport.SCHEMA
    assert data["error_kind"] == "setup" and "not found" in data["error"] and data["checks"] == []


def test_prove_checks_and_the_cli_agree(lab, monkeypatch, tmp_path):
    import netdryrun.prove as prove_pkg
    monkeypatch.setattr(mcp_server, "PROVE_EXECUTOR", executor_for)
    via_mcp = valid(json.loads(mcp_server.prove_checks(str(lab), variants="import_filter,session_down",
                                                       max_variants=2)))
    real = prove_pkg.prove_config
    monkeypatch.setattr(prove_pkg, "prove_config", lambda cfg, **kw: real(cfg, executor=executor_for(cfg), **kw))
    out = tmp_path / "r.json"
    assert cli.main(["prove", str(lab), "--variants", "import_filter,session_down", "--max", "2", "--json",
                     str(out)]) == via_mcp["exit_code"] == 1
    via_cli = json.loads(out.read_text(encoding="utf-8"))
    for d in (via_mcp, via_cli):
        d.pop("started"), d.pop("finished")
    assert via_mcp == via_cli


def test_prove_checks_bad_budget(lab, monkeypatch):
    monkeypatch.setattr(mcp_server, "PROVE_EXECUTOR", executor_for)
    data = json.loads(mcp_server.prove_checks(str(lab), max_variants=0))
    assert data["status"] == "error" and "at least 1" in data["error"]


def tool_description(name: str) -> str:
    import asyncio
    tools = asyncio.run(mcp_server.mcp.list_tools())
    tools = getattr(tools, "tools", tools)
    return next(t.description for t in tools if t.name == name)


def test_the_tool_description_claims_no_more_than_the_tool_does():
    d = tool_description("prove_checks")
    for must in ("Call it after writing or recording checks, before relying on them",
                 "If any variant survived, add a check that catches it, or tell the human which blind spot remains",
                 "Never describe the checks as covering more than the caught list",
                 "no survivor does not mean the checks are complete", "It never edits netdryrun.yml",
                 "FRR labs only", "This build has no live executor yet: it answers status error until phase 2 ships",
                 "decide on `status`"):
        assert must in d, must
    for never in ("safe to apply", "proves the checks", "complete coverage", "guarantee"):
        assert never not in d.lower()
    assert mcp_server.CONTRACT in d
