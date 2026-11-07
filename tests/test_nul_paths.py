"""A path with a NUL byte is a clean error everywhere a path comes in, never a crash (2026-11-07: Hypothesis found
`lab: "\x00"` crashed config.load with ValueError on Python 3.13; coordinator: close the class).

Entry points: netdryrun.yml's `lab`; every MCP tool argument that is a path (all go through mcp_server._host_path);
verify's real-path resolution (topology binds, sides). The CLI and the Action can't receive a NUL in an argument
(exec refuses one), so they reach paths only through file contents, covered by the first and the last."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from netdryrun import config, mcp_server
from netdryrun.config import ConfigError
from netdryrun.verify.run import VerifyInputError, _real

NUL_PATHS = st.builds(lambda a, b, absolute: ("/" if absolute else "") + a + "\x00" + b,
                      st.text(min_size=0, max_size=12).filter(lambda s: "\n" not in s),
                      st.text(min_size=0, max_size=12).filter(lambda s: "\n" not in s), st.booleans())
PROPS = settings(max_examples=60, deadline=None)


@PROPS
@given(lab=NUL_PATHS)
def test_config_lab_with_nul_is_a_config_error(tmp_path_factory, lab):
    d = tmp_path_factory.mktemp("nul")
    p = d / "netdryrun.yml"
    p.write_text(json.dumps({"lab": lab, "checks": [{"type": "bgp_session", "node": "r1", "neighbor": "10.0.0.2"}]}),
                 encoding="utf-8")
    with pytest.raises(ConfigError):
        config.load(p)


@PROPS
@given(path=NUL_PATHS)
def test_every_mcp_path_with_nul_is_a_config_error(path):
    with pytest.raises(ConfigError, match="contains a NUL byte"):
        mcp_server._host_path(path)


@pytest.mark.parametrize("tool,arg", [("dry_run", "path"), ("start_run", "path"), ("run_checks", "path"),
                                      ("validate", "path"), ("record_baseline", "topology"),
                                      ("verify_change", "topology"), ("verify_change", "before"),
                                      ("verify_change", "after"), ("verify_change", "intent"),
                                      ("verify_change", "guards")])
def test_every_mcp_tool_answers_a_nul_path_with_an_error_result(tmp_path, tool, arg):
    import inspect
    f = getattr(mcp_server, tool)
    kw = {q: str(tmp_path) for q, prm in inspect.signature(f).parameters.items()
          if prm.default is inspect.Parameter.empty}
    kw[arg] = str(tmp_path) + "/a\x00b"
    out = json.loads(f(**kw))
    assert "NUL byte" in json.dumps(out) and (out.get("status") == "error" or out.get("valid") is False
                                              or "error" in out)


@PROPS
@given(path=NUL_PATHS)
def test_verify_real_path_with_nul_is_a_verify_input_error(path):
    with pytest.raises(VerifyInputError, match="is not a usable path"):
        _real(Path(path))
