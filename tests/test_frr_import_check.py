"""The FRR import-check guard (drivers/frr_import_check.py; oracle FP-043-FRRIMPORTCHK, RT-0084).

Live answers come from the oracle's captures (FRR 10.4.1, tests/fixtures/frr_fp043ic, SOURCES.yml). DERIVED answers
start from a live one and change only what the test names.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun.drivers import frr_import_check as ic
from netdryrun.lab import ExecResult, LabError

FX = Path(__file__).resolve().parent / "fixtures" / "frr_fp043ic"
TEXT = ["vtysh", "-c", "show bgp import-check-table detail"]
JSON = ["vtysh", "-c", "show bgp import-check-table detail json"]


def live(boot: str, node: str, argv: list[str], ph: str = "boot") -> str:
    hit = None
    for e in json.loads((FX / boot / ph / "phase.json").read_text(encoding="utf-8")):
        if e["node"] == node and e["argv"] == argv:
            hit = e["stdout"].replace("\r\n", "\n")
    assert hit is not None, (boot, node, argv)
    return hit


STUCK_CONFIG = live("c18_stuck_boot2", "pe1", ic.BGPD_CONFIG)
STUCK_JSON = live("c18_stuck_boot2", "pe1", JSON)
STUCK_TEXT = live("c18_stuck_boot2", "pe1", TEXT)
REMEDIED_JSON = live("c18_stuck_boot2", "pe1", JSON, "remedied")
REMEDIED_TEXT = live("c18_stuck_boot2", "pe1", TEXT, "remedied")
VALID_JSON = live("c18_healthy_boot12", "ce1", JSON)
VALID_TEXT = live("c18_healthy_boot12", "ce1", TEXT)
EMPTY_JSON = live("c18_stuck_boot2", "pe2", JSON)
EMPTY_TEXT = live("c18_stuck_boot2", "pe2", TEXT)
SESSIONS = live("c18_stuck_boot2", "pe1", ic.NEIGHBORS)


@pytest.fixture(autouse=True)
def _real_gap(monkeypatch):
    """conftest.py takes the two samples with no gap for the runner's fakes; here the real gap is tested."""
    monkeypatch.setattr(ic, "SAMPLE_GAP", 2.0)


# ------------------------------------------------------------------------------------------------ parsers

def test_bgpd_config_live():
    (inst,) = ic.parse_bgpd_config(STUCK_CONFIG)
    assert (inst.header, inst.kind, inst.vrf, inst.import_check) == ("router bgp 65000", "", "default", True)
    assert inst.checked == [ic.Network("192.0.2.0/24", ("ipv4", "unicast"))]


def _config(body: str) -> str:
    return f"Building configuration...\n\nCurrent configuration:\n!\nfrr version 10.4.1_git\n!\n{body}!\nend\n"


def test_bgpd_config_instances_families_and_exclusions():
    text = _config("router bgp 65000\n address-family ipv4 unicast\n  network 10.0.0.0/8 route-map X\n"
                   "  network 0.0.0.0/32\n exit-address-family\n address-family ipv6 unicast\n  network 2001:db8::/32\n"
                   "  network ::/128\n exit-address-family\n address-family ipv4 multicast\n  network 10.9.0.0/16\n"
                   " exit-address-family\nexit\n!\nrouter bgp 65000 vrf red\n no bgp network import-check\n"
                   " address-family ipv4 unicast\n  network 10.1.0.0/16\n exit-address-family\nexit\n!\n"
                   "router bgp 65000 view v1\n address-family ipv4 unicast\n  network 10.2.0.0/16\n"
                   " exit-address-family\nexit\n!\nrouter bgp 65001 vrf blue as-notation dot\n"
                   " address-family ipv4 labeled-unicast\n  network 10.3.0.0/16\n exit-address-family\nexit\n")
    default, red, view, blue = ic.parse_bgpd_config(text)
    assert default.checked == [ic.Network("10.0.0.0/8", ("ipv4", "unicast")),
                               ic.Network("2001:db8::/32", ("ipv6", "unicast"))]   # never-registered, multicast out
    assert (red.vrf, red.import_check, red.checked) == ("red", False, [])          # the user turned it off
    assert (view.kind, view.checked) == ("view", [])                               # views never import-check
    assert blue.header == "router bgp 65001 vrf blue as-notation dot"
    assert blue.checked == [ic.Network("10.3.0.0/16", ("ipv4", "labeled-unicast"))]


def test_bgpd_config_network_at_router_level_is_ipv4_unicast():
    (inst,) = ic.parse_bgpd_config(_config("router bgp 1\n network 10.0.0.0/24\nexit\n"))
    assert inst.checked == [ic.Network("10.0.0.0/24", ("ipv4", "unicast"))]


@pytest.mark.parametrize("text", [
    "",                                                                           # nothing
    STUCK_CONFIG.replace("\nend\n", "\n"),                                         # cut short
    "% bgpd is not running\n",                                                    # an error
    _config("router bgp 1\n address-family ipv4 unicast\n  network 10.0.0.0/24\n"),  # no exit
    _config("router bgp 1\n address-family ipv4 unicast\n  network 10.0.0.0/24\nexit\n"),  # family left open
    _config("router bgp 1 vrf a b\nexit\n"),                                       # a router line it doesn't know
    _config("router bgp 1 vrf r;ed\nexit\n"),                                     # a name not fit for a command
    _config("router bgp 1\n address-family ipv4 sr-te\n  network 10.0.0.0/24\n exit-address-family\nexit\n"),
    _config("router bgp 1\n address-family ipv4 unicast\n  network 10.0.0.1/24\n exit-address-family\nexit\n"),
    _config("router bgp 1\n address-family ipv4 unicast\n  network 2001:db8::/32\n exit-address-family\nexit\n"),
    _config("router bgp 1\nip route 1.1.1.0/24 lo\nexit\n"),                      # a top-level line inside
    _config(" network 10.0.0.0/24\n"),                                            # outside router bgp
    _config("router bgp 1\n address-family ipv4 unicast\n address-family ipv6 unicast\n exit-address-family\nexit\n"),
])
def test_bgpd_config_not_understood_is_unknown(text):
    with pytest.raises(ic.Unknown):
        ic.parse_bgpd_config(text)


def test_table_live_stuck_remedied_and_valid():
    (stuck,) = ic.parse_table_json(STUCK_JSON, "j")
    assert ic.parse_table_text(STUCK_TEXT, "t") == [stuck]
    assert (stuck.valid, stuck.registered) == (False, False)
    assert stuck.paths == (("192.0.2.0/24", "default", ("ipv4", "unicast"), True),)
    assert stuck.stuck() == "is not registered with zebra"
    (rem,) = ic.parse_table_json(REMEDIED_JSON, "j")
    assert ic.parse_table_text(REMEDIED_TEXT, "t") == [rem]
    assert (rem.valid, rem.registered, rem.paths[0][3], rem.stuck()) == (False, True, False, None)
    (ok,) = ic.parse_table_json(VALID_JSON, "j")
    assert ic.parse_table_text(VALID_TEXT, "t") == [ok]
    assert (ok.valid, ok.registered, ok.paths[0][3], ok.stuck()) == (True, True, True, None)
    assert ic.parse_table_json(EMPTY_JSON, "j") == [] == ic.parse_table_text(EMPTY_TEXT, "t")


def test_contradiction_without_the_flag_is_stuck():
    """DERIVED: the stuck entry with its registration flag gone (JSON key, text line)."""
    j = STUCK_JSON.replace(',"isRegistered":false', "")
    t = "".join(ln for ln in STUCK_TEXT.splitlines(keepends=True) if "Is not Registered" not in ln)
    (e,) = ic.parse_table_json(j, "j")
    assert ic.parse_table_text(t, "t") == [e] and e.registered
    assert e.stuck() == "is invalid while a path that depends on it is valid"
    (v,) = ic.parse_table_json(VALID_JSON.replace('"bestpath":true,"valid":true', '"bestpath":true,"valid":false'), "j")
    assert v.stuck() == "is valid while a path that depends on it is invalid"


def test_two_networks_of_one_address_are_both_kept():
    """DERIVED: bgpd keys entries by address only; two networks of one address print the same key."""
    entry = STUCK_JSON.split('"ipv4":{', 1)[1].rsplit("}\n},", 1)[0]
    second = entry.replace("192.0.2.0/24", "192.0.2.0/25")
    got = ic.parse_table_json('{\n"ipv4":{' + entry + "}," + second +'}\n},"ipv6":{}}', "j")
    assert sorted(e.paths[0][0] for e in got) == ["192.0.2.0/24", "192.0.2.0/25"]


@pytest.mark.parametrize("text", [
    "{\n}\n",                                                                   # `vrf all`, a missing instance
    "",
    "% Unknown command: show bgp import-check-table detail json\n",
    STUCK_JSON.replace('"ipv6":{}', '"ipv6":{},"ipv6":{}'),                     # a family twice
    STUCK_JSON.replace(',"ipv6":{}', ""),                                       # a family missing
    STUCK_JSON.replace('"valid":false,"complete"', '"validState":false,"complete"'),
    STUCK_JSON.replace('"isRegistered":false', '"registered":false'),           # a renamed flag
    STUCK_JSON.replace('"isRegistered":false', '"isRegistered":true'),
    STUCK_JSON.replace('"pathCount":1', '"pathCount":2'),
    STUCK_JSON.replace('"vrf":"default"', '"vrf":"default","color":1'),
    STUCK_JSON.replace('"afi":"IPv4"', '"afi":"L2VPN"'),
    STUCK_JSON.replace('"prefix":"192.0.2.0/24"', '"prefix":"192.0.2.1/24"'),
    STUCK_JSON.replace('"bestpath":true,"valid":true', '"bestpath":true'),
    STUCK_JSON.replace('"192.0.2.0":', '"2001:db8::":'),
    STUCK_JSON.replace('"valid":false,"complete":false,"pathCount":1', '"valid":false,"valid":false,"pathCount":1'),
])
def test_table_json_not_understood_is_unknown(text):
    with pytest.raises(ic.Unknown):
        ic.parse_table_json(text, "j")


@pytest.mark.parametrize("text", [
    "% No such BGP instance exist\n",                                           # `vrf all`, a missing instance
    "",
    STUCK_TEXT.replace("Current BGP import check cache:", "BGP import check entries:"),
    STUCK_TEXT.replace(" invalid,", " state not ok,"),
    STUCK_TEXT.replace("#paths 1", "#paths 2"),
    STUCK_TEXT.replace("  Is not Registered", "  Is not Registered yet"),
    STUCK_TEXT.replace("Paths:\n", "Paths:\n    9/1 10.0.0.0/8 VRF default flags 0x10\n").replace("#paths 1", "#paths 2"),
    VALID_TEXT.replace("  Resolved prefix", "  Is not Registered\n  Resolved prefix"),
    VALID_TEXT + "something else\n",
])
def test_table_text_not_understood_is_unknown(text):
    with pytest.raises(ic.Unknown):
        ic.parse_table_text(text, "t")


def test_reads_are_per_instance_never_vrf_all():
    assert ic.table_commands("default") == (TEXT, JSON)
    assert ic.table_commands("red") == (["vtysh", "-c", "show bgp vrf red import-check-table detail"],
                                        ["vtysh", "-c", "show bgp vrf red import-check-table detail json"])
    for bad in ("all", "ALL", "a b", "r;x"):
        with pytest.raises(ic.Unknown):
            ic.table_commands(bad)


def test_remedy_command_one_call_per_router_under_exact_headers():
    a = ic.Instance("router bgp 65000", "", "default")
    b = ic.Instance("router bgp 1.10 vrf red as-notation dot", "", "red")
    assert ic.remedy_command([a]) == ["vtysh", "-c", "configure terminal", "-c", "router bgp 65000",
                                      "-c", "no bgp network import-check", "-c", "bgp network import-check",
                                      "-c", "end"]
    assert ic.remedy_command([a, b])[2:] == [
        "configure terminal", "-c", "router bgp 65000", "-c", "no bgp network import-check", "-c",
        "bgp network import-check", "-c", "exit", "-c", "router bgp 1.10 vrf red as-notation dot", "-c",
        "no bgp network import-check", "-c", "bgp network import-check", "-c", "end"]


# ------------------------------------------------------------------------------------------------ the guard

class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class Lab:
    """Answers from `answers[(node, argv)]` (a list: one per read, the last repeats); the remedy switches to
    `after`. Boot logs: a finished vtysh -b."""

    def __init__(self, answers, after=None, remedy=(0, "", ""), boot_log="[42|bgpd] sending configuration\n[42|bgpd] done"):
        self.answers, self.after, self.remedy, self.log = answers, after, remedy, boot_log
        self.asked, self.remedied = [], []

    def exec(self, node, argv, timeout=60, input=None):
        self.asked.append((node, tuple(argv)))
        if "no bgp network import-check" in argv:
            self.remedied.append((node, tuple(argv)))
            if self.after is not None:
                self.answers = self.after
            return ExecResult(argv, *self.remedy)
        got = self.answers.get((node, tuple(argv)))
        if got is None:
            return ExecResult(argv, 1, "", "not here")
        if isinstance(got, list):
            got = got.pop(0) if len(got) > 1 else got[0]
        return ExecResult(argv, *got)

    def boot_log(self, node):
        return ExecResult([], 0, self.log, "")


def node_answers(node="pe1", config=STUCK_CONFIG, j=STUCK_JSON, t=STUCK_TEXT, sessions=SESSIONS):
    return {(node, tuple(ic.BGPD_CONFIG)): (0, config, ""), (node, tuple(JSON)): (0, j, ""),
            (node, tuple(TEXT)): (0, t, ""), (node, tuple(ic.NEIGHBORS)): (0, sessions, "")}


def run(lab, remedy=True, nodes=None, budget=20.0):
    clock = Clock()
    logs = []
    out = ic.guard(lab, nodes or {"pe1": "frr"}, remedy=remedy, clock=clock, sleep=clock.sleep, log=logs.append,
                   budget=budget)
    return out, clock, logs


def test_registered_lab_is_left_alone_after_two_agreeing_samples():
    lab = Lab(node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT))
    out, clock, _ = run(lab)
    assert out == {"pe1": "registered"} and lab.remedied == [] and clock.sleeps == [ic.SAMPLE_GAP]
    assert sum(a == ("pe1", tuple(JSON)) for a in lab.asked) == 2
    assert not any("vrf all" in " ".join(a[1]) for a in lab.asked)


def test_stuck_lab_is_remedied_then_judged_clean():
    lab = Lab(node_answers(), after=node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT))
    out, _, logs = run(lab)
    assert lab.remedied == [("pe1", tuple(ic.remedy_command([ic.parse_bgpd_config(STUCK_CONFIG)[0]])))]
    assert out["pe1"].startswith("remedied: 192.0.2.0/24") and "toggling" in logs[0]


def test_stuck_without_remedy_is_an_error_and_touches_nothing():
    lab = Lab(node_answers())
    with pytest.raises(ic.ImportCheckError, match="didn't deploy.*pe1: 192.0.2.0/24") as e:
        run(lab, remedy=False)
    assert isinstance(e.value, LabError) and lab.remedied == []


def test_still_stuck_after_the_remedy_is_an_error():
    lab = Lab(node_answers(), after=node_answers())
    with pytest.raises(ic.ImportCheckError, match="still stuck after the remedy"):
        run(lab)


@pytest.mark.parametrize("remedy", [(1, "", "% BGP instance is already running; AS is 65000"), (0, "warning", "")])
def test_remedy_that_answers_anything_is_an_error(remedy):
    lab = Lab(node_answers(), after=node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT), remedy=remedy)
    with pytest.raises(ic.ImportCheckError, match="remedy failed"):
        run(lab)


def test_running_config_changed_by_the_remedy_is_an_error():
    after = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT,
                         config=STUCK_CONFIG.replace(" exit-address-family", "  network 10.0.0.0/8\n exit-address-family"))
    after[("pe1", tuple(JSON))] = (0, REMEDIED_JSON.replace("}\n},", '},"10.0.0.0":' + REMEDIED_JSON.split(
        '"192.0.2.0":', 1)[1].split("}\n},", 1)[0].replace("192.0.2.0/24", "10.0.0.0/8") + "}\n},"), "")
    after[("pe1", tuple(TEXT))] = (0, REMEDIED_TEXT + REMEDIED_TEXT.split("\n", 1)[1].replace("192.0.2.0", "10.0.0.0")
                                   .replace("10.0.0.0/24", "10.0.0.0/8"), "")
    lab = Lab(node_answers(), after=after)
    with pytest.raises(ic.ImportCheckError, match="running config changed"):
        run(lab)


@pytest.mark.parametrize("change", [
    ('"connectionsDropped":0', '"connectionsDropped":1'),                       # a session dropped
    ('"connectionsEstablished":1', '"connectionsEstablished":2'),               # and came back
    ('"bgpState":"Established"', '"bgpState":"Idle"'),                          # down now
])
def test_a_session_reset_by_the_remedy_is_an_error(change):
    assert change[0] in SESSIONS
    after = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT, sessions=SESSIONS.replace(*change, 1))
    lab = Lab(node_answers(), after=after)
    with pytest.raises(ic.ImportCheckError, match="changed across the import-check remedy"):
        run(lab)


def test_a_session_that_comes_up_during_the_remedy_is_not_a_reset():
    before = SESSIONS.replace('"bgpState":"Established"', '"bgpState":"Active"').replace(
        '"connectionsEstablished":1', '"connectionsEstablished":0')
    lab = Lab(node_answers(sessions=before), after=node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT))
    assert run(lab)[0]["pe1"].startswith("remedied")


def test_unreadable_sessions_around_the_remedy_are_an_error():
    lab = Lab(node_answers(sessions="% error"), after=node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT))
    with pytest.raises(ic.ImportCheckError, match="sessions could not be read"):
        run(lab)


@pytest.mark.parametrize("what,change", [
    ("json", lambda a: a.__setitem__(("pe1", tuple(JSON)), (1, "", "Exiting: failed to connect to any daemons."))),
    ("text", lambda a: a.__setitem__(("pe1", tuple(TEXT)), (0, "% Unknown command: x\n", ""))),
    ("empty", lambda a: (a.__setitem__(("pe1", tuple(JSON)), (0, EMPTY_JSON, "")),
                         a.__setitem__(("pe1", tuple(TEXT)), (0, EMPTY_TEXT, "")))),
    ("disagree", lambda a: a.__setitem__(("pe1", tuple(TEXT)), (0, STUCK_TEXT, ""))),
    ("config", lambda a: a.__setitem__(("pe1", tuple(ic.BGPD_CONFIG)), (1, "", "bgpd is not running"))),
])
def test_unknown_until_the_time_limit_is_an_error(what, change):
    answers = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT)
    answers[("pe1", ("cat", "/etc/frr/frr.conf"))] = (0, "router bgp 65000\n network 192.0.2.0/24\n", "")
    change(answers)
    lab = Lab(answers)
    with pytest.raises(ic.ImportCheckError, match="within 20s") as e:
        run(lab, budget=20.0)
    assert "No verdict" in str(e.value) and lab.remedied == []


def test_bgpd_without_its_config_yet_is_waited_for():
    """An early read: bgpd answers with no `router bgp` while the startup config has one; then it loads."""
    early = _config("")
    answers = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT)
    answers[("pe1", tuple(ic.BGPD_CONFIG))] = [(0, early, ""), (0, early, ""), (0, STUCK_CONFIG, "")]
    answers[("pe1", ("cat", "/etc/frr/frr.conf"))] = (0, "router bgp 65000\n", "")
    out, clock, _ = run(Lab(answers))
    assert out == {"pe1": "registered"} and len(clock.sleeps) == 3


def test_bgpd_still_applying_its_config_is_waited_for():
    lab = Lab(node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT), boot_log="[42|bgpd] sending configuration\n")
    with pytest.raises(ic.ImportCheckError, match="still applying"):
        run(lab)


def test_samples_that_differ_are_read_again():
    answers = node_answers()
    answers[("pe1", tuple(JSON))] = [(0, EMPTY_JSON, ""), (0, REMEDIED_JSON, "")]
    answers[("pe1", tuple(TEXT))] = [(0, EMPTY_TEXT, ""), (0, REMEDIED_TEXT, "")]
    out, clock, _ = run(Lab(answers))
    assert out == {"pe1": "registered"} and len(clock.sleeps) == 2


def test_router_without_bgp_is_skipped_only_on_proof():
    answers = {("r3", tuple(ic.BGPD_CONFIG)): (1, "", "bgpd is not running"),
               ("r3", ("cat", "/etc/frr/frr.conf")): (0, "router ospf\n", "")}
    out, _, _ = run(Lab(answers), nodes={"r3": "frr"})
    assert out["r3"].startswith("bgpd doesn't answer")
    del answers[("r3", ("cat", "/etc/frr/frr.conf"))]   # nothing readable: unknown, never "no BGP"
    with pytest.raises(ic.ImportCheckError):
        run(Lab(answers), nodes={"r3": "frr"})


def test_instance_with_import_check_off_or_no_networks_is_not_read():
    off = STUCK_CONFIG.replace(" bgp router-id", " no bgp network import-check\n bgp router-id")
    lab = Lab(node_answers(config=off))
    assert run(lab)[0] == {"pe1": "registered"}
    assert not any(a[1] in (tuple(JSON), tuple(TEXT)) for a in lab.asked)


def test_candidates_are_every_frr_and_sonic_router():
    from types import SimpleNamespace as N
    lab = N(nodes={"a": N(kind="linux"), "b": N(kind="sonic-vs"), "s": N(kind="bridge"), "h": N(kind="linux"),
                   "e": N(kind="ceos")})
    drivers = {"a": "frr", "b": "sonic", "s": "frr", "h": None, "e": "eos"}
    assert ic.candidates(lab, lambda name, node: drivers[name]) == {"a": "frr", "b": "sonic"}


# ------------------------------------------------------------------------------------------------ every cut of a live answer

@pytest.mark.parametrize("parse,text", [
    (ic.parse_bgpd_config, STUCK_CONFIG),
    (lambda t: ic.parse_table_json(t, "j"), STUCK_JSON), (lambda t: ic.parse_table_json(t, "j"), VALID_JSON),
])
def test_a_cut_answer_is_unknown_never_fewer_entries(parse, text):
    """A config or JSON read cut short never loses a network or an entry: it raises, or reads the same."""
    whole = parse(text)
    assert whole
    for cut in range(len(text.rstrip())):
        try:
            got = parse(text[:cut])
        except ic.Unknown:
            continue
        assert got == whole, (cut, text[:cut][-80:])


@pytest.mark.parametrize("text", [STUCK_TEXT, VALID_TEXT])
def test_a_cut_text_answer_loses_only_whole_entries_and_the_guard_refuses_it(text):
    """The text form has no end marker: cut after a whole entry (or after the header) it reads as a shorter table,
    which no parser can tell from a real one. Never a changed entry; and the guard refuses the shorter table, because
    the JSON lists more (text and JSON must agree) and every `network` needs its entry."""
    whole = ic.parse_table_text(text, "t")
    for cut in range(len(text.rstrip())):
        try:
            got = ic.parse_table_text(text[:cut], "t")
        except ic.Unknown:
            continue
        assert got == whole[:len(got)], (cut, text[:cut][-80:])
    head = text.split("\n", 1)[0] + "\n"
    assert ic.parse_table_text(head, "t") == []
    answers = node_answers(j=REMEDIED_JSON, t=head)
    with pytest.raises(ic.ImportCheckError, match="No verdict"):
        run(Lab(answers))


# ------------------------------------------------------------------------------------------------ wiring

def _oracle():
    import importlib.util
    path = Path(__file__).resolve().parent / "oracles" / "FP-043-FRRIMPORTCHK" / "test_oracle_fp_043_frrimportchk.py"
    spec = importlib.util.spec_from_file_location("oracle_fp043_wiring", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _spy(monkeypatch):
    calls = []
    real = ic.guard

    def spy(lab, nodes, **kw):
        calls.append((sorted(nodes), kw["remedy"], kw.get("label", "")))
        return real(lab, nodes, **kw)
    monkeypatch.setattr(ic, "guard", spy)
    return calls


@pytest.mark.parametrize("deploy", [True, False])
def test_run_guards_every_frr_router_then_rechecks_before_the_verdict(monkeypatch, deploy):
    o = _oracle()
    calls = _spy(monkeypatch)
    rep, lab = o.judged(monkeypatch, "c18", "c18_healthy_boot12", deploy)
    routers = sorted(n for n in lab.nodes if n in ("ce1", "pe1", "pe2", "peer1", "up1"))
    assert calls == [(routers, deploy, ""), (routers, False, "before the verdict")]
    assert {n: v.get("import_check") for n, v in rep.environment["nodes"].items() if "import_check" in v} == \
        {n: "registered" for n in routers}


def test_verify_guards_each_boot_before_and_after_its_snapshot(monkeypatch, tmp_path):
    o = _oracle()
    calls = _spy(monkeypatch)
    o.verified(monkeypatch, tmp_path, o.BASE, "c18_healthy_boot12")
    # deployed()'s own calls (the standing guards' runner.run, nested inside the after side, adds its two detect-only
    # calls: remedy False, labels "" and "before the verdict")
    own = [c for c in calls if c[1:] in ((True, ""), (False, "after the snapshot"))]
    assert len(own) >= 4 and len(own) % 2 == 0
    for first, second in zip(own[::2], own[1::2], strict=True):
        assert first[1:] == (True, "") and second[1:] == (False, "after the snapshot") and first[0] == second[0]
        assert first[0] == ["ce1", "pe1", "pe2", "peer1", "up1"]
    assert [c[1:] for c in calls if c not in own] in ([], [(False, ""), (False, "before the verdict")])


# ------------------------------------------------------------------------- healthy states with no entry (review 58eb8e0)
# Live answers of one FRR 10.4.1 router (tests/fixtures/frr_fp043ic_followup, SOURCES.yml): `network 198.51.100.0/24
# route-map DENYALL` (deny), `network 192.0.2.0/24 backdoor`, a backed `network 203.0.113.0/24`, and `router bgp 65001
# vrf GHOST` with no VRF device (its entry invalid and not registered). Main passed this lab; 58eb8e0 stopped it.

FU = Path(__file__).resolve().parent / "fixtures" / "frr_fp043ic_followup"
GHOST_TEXT = ["vtysh", "-c", "show bgp vrf GHOST import-check-table detail"]
GHOST_JSON = ["vtysh", "-c", "show bgp vrf GHOST import-check-table detail json"]
DENIED = ["vtysh", "-c", "show bgp ipv4 unicast 198.51.100.0/24 json"]
BOOT_LOG = (FU / "r1_bootlog_bgpd.txt").read_text()


def fu(name: str) -> str:
    return (FU / name).read_text()


def r1_answers(**change):
    a = {("r1", tuple(ic.BGPD_CONFIG)): (0, fu("r1_bgpd_config.txt"), ""),
         ("r1", tuple(JSON)): (0, fu("r1_table.json"), ""), ("r1", tuple(TEXT)): (0, fu("r1_table.txt"), ""),
         ("r1", tuple(GHOST_JSON)): (0, fu("r1_ghost_table.json"), ""),
         ("r1", tuple(GHOST_TEXT)): (0, fu("r1_ghost_table.txt"), ""),
         ("r1", tuple(ic.VRFS)): (0, fu("r1_bgp_vrfs.json"), ""),
         ("r1", tuple(DENIED)): (0, fu("r1_denied_prefix.json"), "")}
    for k, v in change.items():
        a[("r1", tuple({"config": ic.BGPD_CONFIG, "denied": DENIED, "vrfs": ic.VRFS, "ghost_json": GHOST_JSON,
                        "ghost_text": GHOST_TEXT}[k]))] = v
    return a


def run_r1(answers, driver="frr", boot_log=BOOT_LOG, budget=60.0):
    return run(Lab(answers, boot_log=boot_log), nodes={"r1": driver}, budget=budget)


def test_followup_config_live():
    default, ghost = ic.parse_bgpd_config(fu("r1_bgpd_config.txt"))
    assert [(n.prefix, n.route_map, n.backdoor) for n in default.networks] == [
        ("192.0.2.0/24", False, True), ("198.51.100.0/24", True, False), ("203.0.113.0/24", False, False)]
    assert [n.prefix for n in default.checked] == ["198.51.100.0/24", "203.0.113.0/24"]   # a backdoor never announces
    assert ghost.vrf == "GHOST" and [n.prefix for n in ghost.checked] == ["100.64.0.0/24"]
    assert ic.parse_bgp_vrfs(fu("r1_bgp_vrfs.json")) == {"default": 0, "GHOST": -1}


def test_a_route_map_denied_network_and_a_vrf_without_device_judge_normally():
    """MAJOR-1: the live lab main passed is registered, each exemption named, and only after the route-map delay."""
    out, clock, _ = run_r1(r1_answers())
    assert out["r1"].startswith("registered; ")
    assert "198.51.100.0/24 (vrf default) needs no entry: denied by its route-map" in out["r1"]
    assert "100.64.0.0 (vrf GHOST) needs no entry: its VRF is not active in zebra" in out["r1"]
    assert sum(clock.sleeps) >= ic.RMAP_DELAY_DEFAULT + ic.SAMPLE_GAP + 1.0


def test_the_route_map_delay_comes_from_the_config():
    cfg = fu("r1_bgpd_config.txt").replace("service integrated-vtysh-config\n",
                                           "service integrated-vtysh-config\nbgp route-map delay-timer 30\n")
    assert ic.route_map_delay(cfg) == 30
    _, clock, _ = run_r1(r1_answers(config=(0, cfg, "")))
    assert sum(clock.sleeps) >= 30 + ic.SAMPLE_GAP + 1.0
    with pytest.raises(ic.Unknown):
        ic.route_map_delay(cfg + "bgp route-map delay-timer 1\n")


def test_a_deny_that_turns_into_a_path_within_the_delay_is_never_trusted():
    """A route-map defined after the `network` (or changed while bgpd loads) is re-applied after the delay: a path of
    its own with no entry is unknown, never a pass on the earlier deny."""
    own = fu("r1_own_prefix.json").replace("203.0.113.0/24", "198.51.100.0/24")
    seq = [(0, fu("r1_denied_prefix.json"), "")] * 3 + [(0, own, "")]
    with pytest.raises(ic.ImportCheckError, match="198.51.100.0/24 .* a path of its own"):
        run_r1(r1_answers(denied=seq))


@pytest.mark.parametrize("why,kw,match", [
    ("bgpd still loading", {"boot_log": "[45|bgpd] sending configuration\n"}, "still applying"),
    ("no load in the log", {"boot_log": "nothing from vtysh -b\n"}, "doesn't show bgpd finished"),
    ("SONiC: no load signal", {"driver": "sonic"}, "on a sonic router"),
])
def test_a_route_map_network_with_no_entry_is_exempt_only_on_proof(why, kw, match):
    with pytest.raises(ic.ImportCheckError, match=match):
        run_r1(r1_answers(), **kw)


@pytest.mark.parametrize("answer", [
    (1, "", "bgpd is not running"),                        # unreadable
    (0, '{"warning":"something new"}', ""),                # a shape the reader doesn't know
    (0, fu("r1_own_prefix.json"), ""),                     # an answer about another prefix
])
def test_a_route_map_deny_needs_bgpd_to_say_it_holds_no_path(answer):
    with pytest.raises(ic.ImportCheckError, match="198.51.100.0/24"):
        run_r1(r1_answers(denied=answer))


def test_a_network_without_route_map_and_without_entry_is_still_unknown():
    cfg = fu("r1_bgpd_config.txt").replace("network 198.51.100.0/24 route-map DENYALL", "network 198.51.100.0/24")
    with pytest.raises(ic.ImportCheckError, match="no import-check entry for network.s. 198.51.100.0/24"):
        run_r1(r1_answers(config=(0, cfg, "")))


def test_a_vrf_without_device_is_exempt_only_on_bgpds_own_vrf_id():
    active = fu("r1_bgp_vrfs.json").replace('"vrfId":-1', '"vrfId":7')
    with pytest.raises(ic.ImportCheckError, match="text and JSON answers disagree"):   # "Unknown" is the inactive name
        run_r1(r1_answers(vrfs=(0, active, "")))
    with pytest.raises(ic.ImportCheckError, match="show bgp vrfs json"):
        run_r1(r1_answers(vrfs=(1, "", "bgpd is not running")))
    gone = fu("r1_bgp_vrfs.json").replace('"GHOST"', '"OTHER"')
    with pytest.raises(ic.ImportCheckError, match="doesn't list the instance"):
        run_r1(r1_answers(vrfs=(0, gone, "")))


def test_an_announced_path_in_a_vrf_without_device_is_still_stuck():
    j = fu("r1_ghost_table.json").replace('"bestpath":false,"valid":false', '"bestpath":true,"valid":true')
    t = fu("r1_ghost_table.txt").replace("flags 0x0", "flags 0x18")
    lab = Lab(r1_answers(ghost_json=(0, j, ""), ghost_text=(0, t, "")), boot_log=BOOT_LOG)
    with pytest.raises(ic.ImportCheckError, match="100.64.0.0/24 in .router bgp 65001 vrf GHOST. is not registered"):
        run(lab, remedy=False, nodes={"r1": "frr"}, budget=60.0)


@pytest.mark.parametrize("text", [
    "", "{}", '{"vrfs":{}}', '{"vrfs":{},"totalVrfs":1}', '{"vrfs":{"a":{"vrfId":"1"}},"totalVrfs":1}',
    '{"vrfs":{"a":{"vrfId":-2}},"totalVrfs":1}', '{"vrfs":{"a":{"vrfId":1},"a":{"vrfId":-1}},"totalVrfs":2}',
    '{"vrfs":{"a":{"vrfId":true}},"totalVrfs":1}', '{"vrfs":[],"totalVrfs":0}',
])
def test_bgp_vrfs_not_understood_is_unknown(text):
    with pytest.raises(ic.Unknown):
        ic.parse_bgp_vrfs(text)


# ------------------------------------------------------------------------------------ bgpd off (review MAJOR-2)

def off_answers(**change):
    a = {("r1", tuple(ic.BGPD_CONFIG)): (1, fu("off_bgpd_config.txt"), ""),
         ("r1", ("cat", "/etc/frr/frr.conf")): (0, fu("r1.conf"), ""),
         ("r1", tuple(ic.DAEMONS)): (0, fu("off_daemons"), ""),
         ("r1", tuple(ic.PROCESSES)): (0, fu("r1_comm_bgpd_off.txt"), "")}
    for k, v in change.items():
        a[("r1", tuple({"config": ic.BGPD_CONFIG, "daemons": ic.DAEMONS, "procs": ic.PROCESSES}[k]))] = v
    return a


def test_bgpd_off_is_skipped_on_positive_evidence():
    """Agent eval T10: `bgpd=no` with `router bgp` in frr.conf. Nothing announces, so nothing is checked; main's
    inconclusive verdict comes from the checks (test_verdict_runner)."""
    out, _, _ = run(Lab(off_answers()), nodes={"r1": "frr"})
    assert out == {"r1": ic.BGPD_DOWN}


@pytest.mark.parametrize("change", [
    {"config": (1, "", "% Can't open configuration file\n")},                       # another failure
    {"daemons": (0, fu("off_daemons").replace("bgpd=no", "bgpd=yes"), "")},          # watchfrr runs it: starting/died
    {"daemons": (0, fu("off_daemons").replace("bgpd=no\n", ""), "")},                # not said
    {"daemons": (0, fu("off_daemons") + "bgpd=no\n", "")},                           # said twice
    {"daemons": (1, "", "cat: can't open '/etc/frr/daemons'")},
    {"procs": (0, fu("r1_comm_bgpd_on.txt"), "")},                                   # a bgpd process runs
    {"procs": (1, fu("r1_comm_bgpd_off.txt"), "cat: can't open '/proc/99/comm'")},  # a list that can't be trusted
    {"procs": (0, "", "")},
])
def test_bgpd_off_needs_every_piece_of_evidence(change):
    with pytest.raises(ic.ImportCheckError, match="within 20s"):
        run(Lab(off_answers(**change)), nodes={"r1": "frr"})


def test_an_unreadable_boot_log_is_waited_for_then_an_error():
    """MINOR-2: a failed boot-log read never skips the wait for bgpd's config load."""
    class NoLog(Lab):
        def boot_log(self, node):
            return ExecResult([], 1, "", "Error response from daemon: No such container")
    with pytest.raises(ic.ImportCheckError, match="boot log could not be read"):
        run(NoLog(node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT)))


# ------------------------------------------------------------------- verify honors driver settings (review MINOR-1)

def test_verify_guards_a_router_its_guards_file_names_frr(monkeypatch, tmp_path):
    """A router only `nodes.<node>.driver: frr` identifies (its image names no NOS) is guarded by verify as by run:
    one reader, runner.driver_resolver (FX-0.4.0-verify-config-load)."""
    from netdryrun.lab import Node
    from netdryrun.verify import run as vrun

    node = Node("x", "clab-t-x", "linux", "example.com/edge-router:1")
    assert vrun._driver_or_none("x", node) is None   # detection alone can't place it

    class DeployLab:
        name, nodes = "t", {"x": node}

        def __init__(self, topology):
            pass

        def check_tools(self):
            pass

        def acquire_lock(self):
            pass

        def release_lock(self):
            pass

        def existing_containers(self):
            return set()

        def deploy(self):
            pass

        def running_containers(self):
            return {"clab-t-x"}

        def destroy(self):
            pass

    guarded = []
    monkeypatch.setattr(vrun, "Lab", DeployLab)
    monkeypatch.setattr(ic, "guard", lambda lab, nodes, **kw: guarded.append((dict(nodes), kw["remedy"])) or {})
    seen = {}
    real = vrun.deployed

    def deployed(topology, setup, keep, log, driver_of=None):
        seen["driver_of"] = driver_of
        return real(topology, setup, keep, log, driver_of=driver_of)
    monkeypatch.setattr(vrun, "deployed", deployed)
    monkeypatch.setattr(vrun, "expects_bgp", lambda exec_fn, n: (_ for _ in ()).throw(RuntimeError("past the guard")))
    side = vrun.real_side(nodes={"x": "frr"}, setup={}, settle=0, timeout=1, keep_after=False, log=lambda _: None,
                          drivers={"x": "frr"})
    with pytest.raises(RuntimeError, match="past the guard"):
        side("before", tmp_path / "t.clab.yml")
    assert seen["driver_of"]("x", node) == "frr"
    assert guarded == [({"x": "frr"}, True)]


# ----------------------------------------------------------------------------- record --deploy (review MINOR-3)

def _record_deploy(monkeypatch, tmp_path, guard):
    from netdryrun import cli, lab as labmod, record as recmod
    from netdryrun.lab import Node

    events = []

    class DeployLab:
        name = "t"
        nodes = {"r1": Node("r1", "clab-t-r1", "linux", "quay.io/frrouting/frr:10.4.1")}

        def __init__(self, topology):
            pass

        def deploy(self):
            events.append("deploy")

        def destroy(self):
            events.append("destroy")
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\n")
    monkeypatch.setattr(labmod, "Lab", DeployLab)
    monkeypatch.setattr(cli, "_await_vm_nodes", lambda lab, drivers: events.append("vm wait"))
    monkeypatch.setattr("time.sleep", lambda s: events.append(f"sleep {s:g}"))
    monkeypatch.setattr(recmod, "record", lambda *a, **k: (events.append("record") or (
        {"lab": "t", "timeout": 120, "checks": [{"type": "route", "node": "r1", "prefix": "192.0.2.0/24"}]}, [])))

    def spy(lab, nodes, **kw):
        events.append(("guard", dict(nodes), kw["remedy"], kw.get("label", "")))
        return guard(kw["remedy"])
    monkeypatch.setattr(ic, "guard", spy)
    out = tmp_path / "netdryrun.yml"
    rc = cli.main(["record", str(topo), "--deploy", "--wait", "5", "--out", str(out)])
    return rc, events, out


def test_record_deploy_guards_before_and_after_recording(monkeypatch, tmp_path):
    rc, events, out = _record_deploy(monkeypatch, tmp_path, lambda remedy: {"r1": "registered"})
    assert rc == 0 and out.exists()
    assert events == ["deploy", "vm wait", ("guard", {"r1": "frr"}, True, ""), "sleep 5", "record",
                      ("guard", {"r1": "frr"}, False, "after the recording"), "destroy"]


@pytest.mark.parametrize("stuck_when", [True, False])
def test_record_deploy_on_a_stuck_boot_writes_nothing(monkeypatch, tmp_path, capsys, stuck_when):
    def guard(remedy):
        if remedy == stuck_when:
            raise ic.ImportCheckError("FRR's import check is still stuck after the remedy: r1: 192.0.2.0/24")
        return {"r1": "registered"}
    rc, events, out = _record_deploy(monkeypatch, tmp_path, guard)
    assert rc == 2 and not out.exists() and events[-1] == "destroy"
    assert "import check" in capsys.readouterr().err
