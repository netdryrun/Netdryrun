"""Guards for oracle FP-043-FRRIMPORTCHK: what is right on main stays right after the fix.

The same recorded boots and replay as tests/oracles/FP-043-FRRIMPORTCHK (FRR 10.4.1, recorded live 2026-11-21):
- the captures say what the oracle claims (the device's own view, and netdryrun's live reports);
- a state where every router's import check is registered (uw boot 1, c18 boots 12 and 13, c18_stuck_boot2 after
  its live remedy) is judged as before: the must-fail checks fail (status "failed", not an error) and on uw `r2 does
  not have 198.51.100.0/24` passes; verify on such an after side finds the aggregate withdrawn (not approved).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "oracle_fp_043_frrimportchk",
    Path(__file__).resolve().parent / "oracles" / "FP-043-FRRIMPORTCHK" / "test_oracle_fp_043_frrimportchk.py")
o = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(o)


def report(boot: str, ph: str, stem: str) -> dict:
    return json.loads((o.FX / boot / ph / f"report_{stem}.json").read_text(encoding="utf-8"))


def _stuck_entry(boot: str, origin: str, prefix: str) -> None:
    """Invalid and not registered, next to a valid sourced path (text and JSON)."""
    entry = json.loads(o.captured(boot, origin, o.JSON))["ipv4"][prefix.split("/")[0]]
    assert entry["valid"] is False and entry.get("isRegistered") is False, entry
    paths = json.loads(o.captured(boot, origin, f"show bgp ipv4 unicast {prefix} json"))["paths"]
    assert any(p.get("valid") and p.get("sourced") for p in paths), paths
    assert o.NOT_REGISTERED in o.captured(boot, origin, o.TEXT)


def _registered_everywhere(boot: str, ph: str) -> None:
    """Every router's import-check table read, none with an unregistered entry: a fix has nothing to remedy here."""
    reads = {k[0]: v for k, v in o.phase(boot, ph).items() if k[1:] == ("exec", ("vtysh", "-c", o.TEXT))}
    assert reads and all(r.rc == 0 and o.NOT_REGISTERED not in r.stdout for r in reads.values()), (
        {n: r.stdout[:200] for n, r in reads.items()})
    for node, r in o.phase(boot, ph).items():
        if node[1:] == ("exec", ("vtysh", "-c", o.JSON)):
            assert "isRegistered" not in r.stdout, node


@pytest.mark.parametrize("lab_key,boot", o.STUCK_ALL, ids=[b for _, b in o.STUCK_ALL])
def test_stuck_captures_say_what_the_oracle_claims(lab_key, boot):
    yml, origin, prefix = o.LABS[lab_key]
    _stuck_entry(boot, origin, prefix)
    assert report(boot, "boot", yml[:-4])["status"] == "passed"                       # the live false pass
    assert o.NOT_REGISTERED not in o.captured(boot, origin, o.TEXT, "remedied")       # the live remedy worked
    assert "isRegistered" not in o.captured(boot, origin, o.JSON, "remedied")
    assert report(boot, "remedied", yml[:-4])["status"] == "failed"
    # `vrf all` is not a valid import-check read: text refuses, JSON prints an empty object (design review F1)
    assert "% No such BGP instance exist" in o.captured(boot, origin, "show bgp vrf all import-check-table detail")
    assert o.captured(boot, origin, "show bgp vrf all import-check-table detail json").split() == ["{", "}"]


@pytest.mark.parametrize("lab_key,boot,ph", o.HEALTHY_ALL, ids=[f"{b}-{ph}" for _, b, ph in o.HEALTHY_ALL])
def test_healthy_captures_say_what_the_oracle_claims(lab_key, boot, ph):
    yml = o.LABS[lab_key][0]
    _registered_everywhere(boot, ph)
    assert report(boot, ph, yml[:-4])["status"] == "failed"


def test_base_captures_say_what_the_oracle_claims():
    _registered_everywhere(o.BASE, "boot")                                          # the before side as replayed
    # a backed `network` (pe1 keeps its discard route) is stuck the same way
    _stuck_entry(o.BASE_STUCK, "pe1", "192.0.2.0/24")


@pytest.mark.parametrize("deploy", [True, False], ids=["run", "check"])
@pytest.mark.parametrize("lab_key,boot,ph", o.HEALTHY_ALL, ids=[f"{b}-{ph}" for _, b, ph in o.HEALTHY_ALL])
def test_registered_state_fails_the_must_fail_checks(monkeypatch, lab_key, boot, ph, deploy):
    rep, _ = o.judged(monkeypatch, lab_key, boot, deploy, start=ph)
    assert rep.status == "failed" and not any(r.passed for r in rep.results), o.summary(rep)


def test_healthy_boot_passes_the_prefix_is_withdrawn(monkeypatch):
    boot, ph = o.HEALTHY["uw"]
    rep, _ = o.judged(monkeypatch, "uw", boot, True, checks="uw_present_false.yml", start=ph)
    assert rep.status == "passed", o.summary(rep)


def test_verify_on_a_registered_after_side_does_not_approve(monkeypatch, tmp_path):
    """Every router registered on the after side: 192.0.2.0/24 is withdrawn, the standing guards fail."""
    boot, ph = o.HEALTHY["c18"]
    res, _ = o.verified(monkeypatch, tmp_path, o.BASE, boot, after_phase=ph)
    assert res.status not in ("matched", "no_change"), (res.status, res.error)
