"""Guards for oracle FP-042-SRLNETNS: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-SRLNETNS/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.
Helpers and the captured data come from the oracle's own module (tests/oracles/FP-042-SRLNETNS/).
"""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-SRLNETNS" / "test_oracle_fp_042_srlnetns.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_srlnetns", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_the_capture_is_what_the_oracle_says():
    c = o.captured()
    assert c["srl1"]["HostConfig"]["NetworkMode"] == f"container:{o.HOLDER_ID}"
    assert c["holder"]["Id"] == o.HOLDER_ID and c["holder"]["Name"] == "/clab-ndr-srl-netns-srl1-netns"
    labels = c["holder"]["Config"]["Labels"]
    assert (labels["containerlab"], labels["clab-internal-node"], labels["clab-root-node-name"]) == \
        ("ndr-srl-netns", "true", "srl1")


@pytest.mark.parametrize("old,new", [("ndr-srl-netns", "other-lab"), ("srl1", "srl9")],
                         ids=["another-lab", "another-node"])
def test_a_holder_named_for_something_else_is_refused(monkeypatch, tmp_path, old, new):
    c = o.captured()
    c["holder"] = o.relabel(c["holder"], old, new)
    error = o.prepare(monkeypatch, tmp_path, c)
    assert error is not None and "srl1" in str(error), error


def test_a_holder_without_labels_is_refused(monkeypatch, tmp_path):
    """The holder's name and id, none of its labels: it only looks like containerlab's."""
    c = o.captured()
    c["holder"]["Config"]["Labels"] = {}
    error = o.prepare(monkeypatch, tmp_path, c)
    assert error is not None and "srl1" in str(error), error


def test_a_holder_docker_cant_read_is_refused(monkeypatch, tmp_path):
    c = o.captured()
    del c["holder"]
    error = o.prepare(monkeypatch, tmp_path, c)
    assert error is not None and "srl1" in str(error), error


def test_network_mode_host_is_refused(monkeypatch, tmp_path):
    c = o.captured()
    c["srl1"]["HostConfig"]["NetworkMode"] = "host"
    error = o.prepare(monkeypatch, tmp_path, c)
    assert error is not None and "srl1" in str(error) and "host" in str(error), error
