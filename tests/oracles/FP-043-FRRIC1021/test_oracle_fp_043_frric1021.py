"""Oracle FP-043-FRRIC1021: on FRR 10.2.1 the FRR import check refuses the interface next-hop line `  if lo`, so a lab
whose `network` statements resolve over an interface never gets a verdict.

`show bgp import-check-table detail` prints one line per resolved next hop. For an interface next hop
(NEXTHOP_TYPE_IFINDEX) FRR 10.4.1 prints `  if <name>, ifindex <n>` (bgpd/bgp_nexthop.c, 10.4.1) and FRR 10.2.1
prints `  if <name>` with no ifindex (bgpd/bgp_nexthop.c, 10.2.1). The import check's text parser
(frr_import_check.parse_table_text) knows only the 10.4.1 form, so on 10.2.1 every router with a `network` backed by
a connected route (a loopback, an unnumbered link) reads as "a line this check doesn't know: '  if lo'": the guard
retries until its time limit, and `record`, `run` and `check` end in a lab error (exit 2) with no verdict. The JSON
answer of the same table (`"nexthops": [{"interfaceName": "lo"}]`) is read fine. The harm is a false failure on a
supported FRR version, never a false pass. An outside public lab on FRR 10.2.1 met it first ("a line this check
doesn't know: '  if eth3'").

Captured live (tests/fixtures/SOURCES.yml, tests/fixtures/frr_ic1021/capture-cmds.txt): the committed three-router
lab tests/fixtures/unnsesschk_lab.clab.yml with its committed configs, deployed once on FRR 10.2.1 (ic1021_*) and once
on FRR 10.4.1 (ic1041_*), image pinned by digest; each file is one router's answer to one vtysh command. r1 announces
10.1.1.0/24 and 10.1.2.0/24, r3 10.3.1.0/24 and 2001:db8:3::/64, all on its loopback; r2 has no `network`.
record1021-b046245.log is `netdryrun record lab.clab.yml --deploy` on the 10.2.1 lab: the lab error above, for r1
and r3.

The rule: a 10.2.1 table reads as what bgpd holds (each entry valid and registered, with the `network` paths that
depend on it), its text and JSON answers agree, and the guard on a 10.2.1 lab says every router is registered. Lines
of neither form stay refused, and the 10.4.1 answers read as before: those guards are in
tests/test_oracle_guards_fp_043_frric1021.py (listed in ORACLE.yml `evidence:`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun.drivers import frr_import_check as ic
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures" / "frr_ic1021"
BOOT_LOG = Path(__file__).resolve().parents[2] / "fixtures" / "frr_boot_log_clean.txt"
ROUTERS = ("r1", "r2", "r3")
WITH_NETWORKS = ("r1", "r3")   # r2 has no `network` statement: no table to read
FILES = {   # the vtysh command the guard sends -> the captured file's stem
    tuple(ic.BGPD_CONFIG): "bgpd_running_config",
    tuple(ic.VRFS): "show_bgp_vrfs_json",
    tuple(ic.table_commands("default")[0]): "show_bgp_importchecktable_detail",
    tuple(ic.table_commands("default")[1]): "show_bgp_importchecktable_detail_json",
}


def fx(version: str, router: str, stem: str) -> str:
    """One captured answer, as lab.exec gives it to netdryrun (text mode)."""
    return (FX / f"ic{version}_{router}_{stem}.txt").read_text(encoding="utf-8")


def expected_entries(version: str, router: str) -> list:
    """What bgpd holds, built from the captured JSON with the json module alone (not the parser under test): one
    entry per address, valid and registered (no isRegistered false), with the paths that depend on it."""
    top = json.loads(fx(version, router, "show_bgp_importchecktable_detail_json"))
    out = []
    for afi in ("ipv4", "ipv6"):
        for addr, e in top[afi].items():
            paths = tuple(sorted((p["prefix"], p["vrf"], (p["afi"].lower(), p["safi"]), p["flags"]["valid"])
                                 for p in e["paths"]))
            out.append(ic.Entry(addr, e["valid"], e.get("isRegistered", True), paths))
    return sorted(out, key=repr)


def networks(version: str, router: str) -> list:
    """The `network` prefixes of the router's running config, read as plain text (not by the parser under test)."""
    return sorted(ln.split()[1] for ln in fx(version, router, "bgpd_running_config").splitlines()
                  if ln.startswith("  network "))


def read_or_error(parse, version: str, router: str, stem: str):
    """(entries, None), or (None, the parser's refusal)."""
    try:
        return sorted(parse(fx(version, router, stem), stem), key=repr), None
    except ic.Unknown as e:
        return None, e


class CapturedLab:
    """The three routers of one capture. Each command the guard sends answers the captured bytes; the boot log, not
    captured in this lab, is the committed FRR boot log of a clean config load (tests/fixtures/frr_boot_log_clean.txt),
    which only tells the guard bgpd finished loading its config. Anything else answers rc 1."""

    def __init__(self, version: str, derived: dict | None = None):
        self.version = version
        self.derived = derived or {}   # (router, stem) -> text built in a test: DERIVED
        self.asked: list = []

    def exec(self, node, cmd, timeout=60, input=None):
        self.asked.append((node, list(cmd)))
        stem = FILES.get(tuple(cmd))
        if stem is None or node not in ROUTERS:
            return ExecResult(list(cmd), 1, "", f"not captured: {' '.join(cmd)}")
        key = (node, stem)
        text = self.derived[key] if key in self.derived else fx(self.version, node, stem)
        return ExecResult(list(cmd), 0, text, "")

    def boot_log(self, node):
        return ExecResult(["docker", "logs"], 0, BOOT_LOG.read_text(encoding="utf-8"), "")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def guarded(lab, remedy: bool):
    """The guard as run, record and check call it, on every router of the lab: (found, None) or (None, its error)."""
    c = Clock()
    try:
        return ic.guard(lab, {r: "frr" for r in ROUTERS}, remedy=remedy, clock=c, sleep=c.sleep), None
    except ic.ImportCheckError as e:
        return None, e


@pytest.mark.parametrize("router", [pytest.param(r, id=f"10.2.1-{r}") for r in WITH_NETWORKS])
def test_frr_1021_text_table_reads_as_its_entries(router):
    """The 10.2.1 text answer reads as the entries bgpd holds, the same as its JSON answer."""
    want = expected_entries("1021", router)
    assert want and all(e.valid and e.registered and e.paths for e in want), want   # the capture is what it claims
    assert sorted(p[0] for e in want for p in e.paths) == networks("1021", router)
    from_json, json_err = read_or_error(ic.parse_table_json, "1021", router, "show_bgp_importchecktable_detail_json")
    from_text, text_err = read_or_error(ic.parse_table_text, "1021", router, "show_bgp_importchecktable_detail")
    assert text_err is None, f"FRR 10.2.1 {router}: the text table is refused: {text_err}"
    assert json_err is None, f"FRR 10.2.1 {router}: the JSON table is refused: {json_err}"
    assert from_text == want, from_text
    assert from_json == want, from_json


@pytest.mark.parametrize("remedy", [pytest.param(True, id="deployed"), pytest.param(False, id="not-deployed")])
def test_frr_1021_guard_finds_every_router_registered(remedy):
    """The guard on the 10.2.1 lab: every router read and registered, nothing remedied, no error."""
    lab = CapturedLab("1021")
    found, err = guarded(lab, remedy)
    assert err is None, f"the import-check guard on the FRR 10.2.1 lab ended in an error: {err}"
    assert found == {r: "registered" for r in ROUTERS}, found
    assert not any(cmd[:3] == ["vtysh", "-c", "configure terminal"] for _n, cmd in lab.asked), lab.asked
