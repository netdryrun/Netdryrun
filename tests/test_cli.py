from urllib.parse import parse_qs, urlparse

from netdryrun import __version__
from netdryrun.cli import feedback_url, main


def test_feedback_url_prefills_only_version_and_platform():
    u = urlparse(feedback_url())
    q = parse_qs(u.query)
    assert u.netloc == "github.com" and u.path == "/netdryrun/netdryrun/issues/new"
    assert q["template"] == ["feedback.yml"] and q["version"] == [__version__]
    assert set(q) == {"template", "labels", "version", "platform"}


def test_feedback_print_only(capsys):
    assert main(["feedback", "--print-only"]) == 0
    out = capsys.readouterr().out
    assert "Nothing is sent until you submit it" in out and "issues/new?template=feedback.yml" in out


def test_ctrl_c_gives_clean_message_not_traceback(tmp_path, monkeypatch, capsys):
    import netdryrun.cli as cli

    (tmp_path / "topo.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {}\n")
    (tmp_path / "netdryrun.yml").write_text("lab: topo.clab.yml\nchecks:\n  - {type: ping, node: r1, target: 10.0.0.1}\n")

    def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run", interrupted)
    assert cli.main(["run", str(tmp_path)]) == 130
    assert "Interrupted: no verdict" in capsys.readouterr().err


def test_feedback_template_price_questions_are_optional_and_private_route_offered():
    from pathlib import Path

    import yaml

    tpl = yaml.safe_load((Path(__file__).resolve().parent.parent / ".github" / "ISSUE_TEMPLATE" / "feedback.yml").read_text(encoding="utf-8"))
    fields = {b["id"]: b for b in tpl["body"] if "id" in b}
    for fid in ("keep_price", "too_expensive", "too_cheap"):
        assert fid in fields and not fields[fid].get("validations", {}).get("required")
    assert "hello@netdryrun.com" in fields["keep_price"]["attributes"]["description"]
