"""The surfaces must agree in verify mode too: the CLI (`netdryrun verify`, exit code and JSON report), the MCP
tool `verify_change` and the GitHub Action (its result step and the step that turns the job red) give the same
verdict for the same verify run. Approving means INTENT MATCHED or NO BEHAVIOR CHANGE, nothing else."""
import json

import pytest

pytest.importorskip("mcp")

from netdryrun import cli, mcp_server  # noqa: E402
from netdryrun.verify import report as vreport  # noqa: E402
from netdryrun.verify import run as vrun  # noqa: E402
from netdryrun.verify.converge import Inconclusive  # noqa: E402
from test_action_verify import read_result  # noqa: E402
from test_surfaces_agree import action_job_fails  # noqa: E402
from test_verify_run import NEW_BLOCK, fake_side, make_lab, side_dir  # noqa: E402
from verify_helpers import add_new_customer_block, base  # noqa: E402

REAL_VERIFY = vrun.verify
STUCK = Inconclusive("the lab's state kept moving", ["edge1 10.9.9.0/24 changed"])
CASES = {
    "matched": (lambda: base().snap(), lambda: add_new_customer_block(base()).snap(), NEW_BLOCK),
    "no_change": (lambda: base().snap(), lambda: base().snap(), "intent: []\n"),
    "failed": (lambda: base().snap(), lambda: add_new_customer_block(base()).snap(), "intent: []\n"),
    "inconclusive": (lambda: base().snap(), lambda: STUCK, NEW_BLOCK),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_cli_mcp_and_action_give_the_same_verify_verdict(case, tmp_path, monkeypatch):
    before, after, intent = CASES[case]
    lab = make_lab(tmp_path)
    b, a = side_dir(tmp_path, lab, "before"), side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    (tmp_path / "intent.yml").write_text(intent)

    def fake_verify(*args, **kw):
        return REAL_VERIFY(*args, side_fn=fake_side(before(), after()), **kw)
    monkeypatch.setattr(vrun, "verify", fake_verify)
    monkeypatch.setattr(cli, "install_signal_handlers", lambda: None)

    out = tmp_path / "report.json"
    code = cli.main(["verify", str(lab / "topology.clab.yml"), "--before", str(b), "--after", str(a),
                     "--intent", str(tmp_path / "intent.yml"), "--json", str(out)])
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["status"] == case and code == vreport.EXIT_CODES[case]

    mcp = json.loads(mcp_server.verify_change(str(lab / "topology.clab.yml"), str(b), str(a), intent))
    assert (mcp["status"], mcp["verdict"]) == (rep["status"], rep["verdict"])

    action = read_result(tmp_path, rep, str(code))
    assert (action["status"], action["verdict"]) == (rep["status"], rep["verdict"])
    approves = case in ("matched", "no_change")
    assert (action["ok"] == "true") is approves
    assert action_job_fails({"run": {"exit_code": str(code)}, "result": action}) is (not approves)
    assert (code == 0) is approves
