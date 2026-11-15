"""Oracle FP-042-PINGSRCFAMILY (red team 042-IB RT-0081 and RT-0112-a, verifier 042-IV on 3d71d5a): a `ping` check
whose `source` is of the other address family than its `target` loads and passes, although nothing was sent from
that source.

The check as the user means it: "r1 reaches 2001:db8:3::1 *from* its own address 192.0.2.1" (and the reverse, an IPv6
source with an IPv4 target): the usual LAN-to-LAN ping that proves the return path to the source's prefix exists.
Nothing in 0.4.2 compares the two families: config._ping_target refuses only source == target, and checks._ping only
checks that the source is one of the node's own addresses. The drivers pass the source as `ping -I` (FRR and SONiC;
SR Linux `ping`/`ping6 -I` in the srbase namespace).

What the tools do (verifier 042-IV, checked locally on loopback with probe_ping.sh and probe_ping2.sh, WSL):
- busybox 1.30.1 (the FRR image's ping; tests/fixtures/frr_ping.txt is its format, `seq=` and "from <source>:" in
  the banner): `ping -I 127.0.0.1 ::1` prints `PING ::1 (::1): 56 data bytes`, no "from", and pings. busybox drops a
  source of the other family (`if (source_lsa && family mismatch) source_lsa = NULL;`) without an error.
- iputils 20211215 (SONiC, SR Linux): `ping -I 127.0.0.1 ::1` gets a reply, rc 0, and prints
  `PING ::1(::1) from ::1 : 56 data bytes`: the "from" is the address the kernel picked, not the one asked for. The
  reverse (`-I ::1 127.0.0.1`) does the same.
So the ping leaves from the egress interface's address of the target's family and the replies go back there.

Device output: DERIVED, not captured for this case (SOURCES.yml has no kind for a derived file, so it is derived here
in the test, from live captures):
- busybox ping answers from tests/fixtures/frr_ping.txt (FRR), with the target replaced and the banner's
  "from <source>" removed, as busybox prints it when it dropped the source;
- iputils ping answers from tests/fixtures/srl_ping.txt (SR Linux, iputils format), with the target replaced and the
  banner's "from" set to the address the kernel would pick (the node's address on the egress link, of the target's
  family); an IPv6 banner has iputils' IPv6 form `PING <t>(<t>) from <a> : 56 data bytes` (probe_ping.sh output);
- the node's own addresses from each driver's live own-address capture (tests/fixtures/frr_local_ip_addr.json,
  sonic_local_ip_addr.json, srl_local_ipv4.json, srl_local_ipv6.json), with lab IPv6 addresses added where the
  capture has only management and link-local ones (marked below).

The rule: such a check is refused when the file is loaded (ConfigError, what `netdryrun validate` runs) or it never
passes. Failing, unready or refused at run time all satisfy the oracle. Commands the derivation doesn't cover answer
rc 1 (an unknown command): the oracle knows nothing else the node would have said.

Guards (they pass before and after the fix) are in tests/test_oracle_guards_fp_042_pingsrcfamily.py: a same-family
source still loads and passes, in both families, and a check without source is unchanged.
"""
import copy
import ipaddress
import json
from pathlib import Path

import pytest

from netdryrun import config
from netdryrun.checks import run_check
from netdryrun.config import ConfigError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
NODE = "r1"
V6_TARGET = "2001:db8:3::1"   # RT-0081's target: r3's IPv6 loopback
V4_TARGET = "10.0.3.1"        # RT-0112-a's target
SRL_V4 = "info from state /interface * subinterface * ipv4 address *"
SRL_V6 = "info from state /interface * subinterface * ipv6 address *"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


# ---- derived device output ---------------------------------------------------------------------------------------

def busybox_ping(target: str, source: str | None) -> str:
    """busybox ping's answer (3/3 replies), derived from the live tests/fixtures/frr_ping.txt: the captured banner
    `PING 192.168.3.1 (192.168.3.1) from 192.168.1.1: 56 data bytes` with the target replaced, and " from <source>"
    only when busybox bound the source (never when it dropped one of the other family)."""
    text = fx("frr_ping.txt")
    assert text.startswith("PING 192.168.3.1 (192.168.3.1) from 192.168.1.1: 56 data bytes\n")
    assert "3 packets transmitted, 3 packets received" in text
    text = text.replace(" from 192.168.1.1:", f" from {source}:" if source else ":", 1)
    return text.replace("192.168.3.1", target)


def iputils_ping(target: str, kernel_source: str) -> str:
    """iputils ping's answer (3/3 replies), derived from the live tests/fixtures/srl_ping.txt (iputils format): the
    banner names the source the kernel used; an IPv6 banner has iputils' IPv6 form."""
    text = fx("srl_ping.txt")
    banner = "PING 192.168.20.1 (192.168.20.1) from 192.168.10.1 : 56(84) bytes of data.\n"
    assert text.startswith(banner) and "3 packets transmitted, 3 received" in text
    if ipaddress.ip_address(target).version == 6:
        new = f"PING {target}({target}) from {kernel_source} : 56 data bytes\n"
    else:
        new = f"PING {target} ({target}) from {kernel_source} : 56(84) bytes of data.\n"
    return new + text[len(banner):].replace("192.168.20.1", target)


def _ip_j_addr_with(name: str, extra: dict[str, list[str]]) -> str:
    """A live `ip -j addr` capture with global IPv6 lab addresses added (DERIVED): {ifname: [address/len, ...]}."""
    data = json.loads(fx(name))
    for link in data:
        for a in extra.get(link["ifname"], []):
            ip, plen = a.split("/")
            link["addr_info"].append({"family": "inet6", "local": ip, "prefixlen": int(plen), "scope": "global",
                                      "valid_life_time": 4294967295, "preferred_life_time": 4294967295})
    assert all(any(link["ifname"] == k for link in data) for k in extra)
    return json.dumps(data)


def _srl_ipv6_with(extra: dict[str, list[str]]) -> str:
    """The live SR Linux IPv6 own-address capture with lab IPv6 addresses added (DERIVED) on subinterface 0."""
    data = copy.deepcopy(json.loads(fx("srl_local_ipv6.json")))
    for ifname, addrs in extra.items():
        data["interface"].append({"name": ifname, "subinterface": [{"index": 0, "ipv6": {"address": [
            {"ip-prefix": a, "type": "global-unicast", "origin": "static", "status": "preferred"} for a in addrs]}}]})
    return json.dumps(data)


# Per driver: its own-address answers, an IPv4 and an IPv6 lab source of the node, the address the kernel picks
# toward each target family (egress link), and how its ping tool answers.
SCENARIOS = {
    "frr": {
        "driver": FrrDriver,
        # live: lo 192.0.2.1/32, eth1 10.0.12.1/30; DERIVED: lo 2001:db8:1::1/128, eth1 2001:db8:12::1/64
        "addrs": {("ip", "-j", "addr"): _ip_j_addr_with("frr_local_ip_addr.json",
                                                         {"lo": ["2001:db8:1::1/128"], "eth1": ["2001:db8:12::1/64"]})},
        "v4": "192.0.2.1", "v6": "2001:db8:1::1",
        "egress": {4: "10.0.12.1", 6: "2001:db8:12::1"},
        "tool": "busybox",
    },
    "sonic": {
        "driver": SonicDriver,
        # live: Loopback0 192.168.40.1, Ethernet0 10.0.40.1; DERIVED: Loopback0 2001:db8:40::1/128,
        # Ethernet0 2001:db8:40:1::1/64
        "addrs": {("ip", "-j", "addr"): _ip_j_addr_with("sonic_local_ip_addr.json",
                                                         {"Loopback0": ["2001:db8:40::1/128"],
                                                          "Ethernet0": ["2001:db8:40:1::1/64"]})},
        "v4": "192.168.40.1", "v6": "2001:db8:40::1",
        "egress": {4: "10.0.40.1", 6: "2001:db8:40:1::1"},
        "tool": "iputils",
    },
    "srlinux": {
        "driver": SrlDriver,
        # live: lo0 192.168.10.1/32, ethernet-1/1 10.0.100.1/30; DERIVED: lo0 2001:db8:10::1/128,
        # ethernet-1/1 2001:db8:100::1/64
        "addrs": {("sr_cli", "--output-format", "json", SRL_V4): fx("srl_local_ipv4.json"),
                  ("sr_cli", "--output-format", "json", SRL_V6): _srl_ipv6_with(
                      {"lo0": ["2001:db8:10::1/128"], "ethernet-1/1": ["2001:db8:100::1/64"]})},
        "v4": "192.168.10.1", "v6": "2001:db8:10::1",
        "egress": {4: "10.0.100.1", 6: "2001:db8:100::1"},
        "tool": "iputils",
    },
}
KINDS = sorted(SCENARIOS)
# (source family, target): an IPv4 source with an IPv6 target (RT-0081) and the reverse (RT-0112-a)
MISMATCHED = {"v4-source-v6-target": ("v4", V6_TARGET), "v6-source-v4-target": ("v6", V4_TARGET)}


def ping_argv(kind: str, source: str | None, target: str) -> tuple:
    """The ping command the 0.4.2 driver sends (default VRF, count 3)."""
    tail = ("-c", "3", "-W", "1") + (("-I", source) if source else ()) + (target,)
    if kind == "srlinux":
        tool = "ping6" if ipaddress.ip_address(target).version == 6 else "ping"
        return ("ip", "netns", "exec", "srbase-default", tool) + tail
    return ("ping",) + tail


def ping_answer(kind: str, source: str | None, target: str) -> str:
    """What the node's ping tool prints: a source of the target's family is bound; one of the other family is dropped
    (busybox) or ignored (iputils: the kernel's source is printed); no source: the kernel's."""
    sc = SCENARIOS[kind]
    fam = ipaddress.ip_address(target).version
    bound = source if source and ipaddress.ip_address(source).version == fam else None
    if sc["tool"] == "busybox":
        return busybox_ping(target, bound)
    return iputils_ping(target, bound or sc["egress"][fam])


class DerivedLab:
    """The node as derived above. Any command the derivation doesn't cover answers rc 1 (an unknown command)."""

    def __init__(self, kind: str, source: str | None, target: str):
        self.answers = dict(SCENARIOS[kind]["addrs"])
        self.answers[ping_argv(kind, source, target)] = ping_answer(kind, source, target)

    def exec(self, node, cmd, timeout=60, input=None):
        if node == NODE and tuple(cmd) in self.answers:
            return ExecResult(cmd, 0, self.answers[tuple(cmd)], "")
        return ExecResult(cmd, 1, "", f"not derived: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def load(tmp_path: Path, kind: str, check: dict) -> config.Config:
    """The check through the real config loading (what `netdryrun validate` and `run` read)."""
    (tmp_path / "lab.clab.yml").write_text("name: pingsrc\ntopology:\n  nodes:\n    r1: {kind: linux}\n",
                                           encoding="utf-8")
    doc = {"lab": "lab.clab.yml", "nodes": {NODE: {"driver": kind}}, "checks": [check]}
    (tmp_path / "netdryrun.yml").write_text(json.dumps(doc), encoding="utf-8")   # JSON is YAML
    return config.load(tmp_path / "netdryrun.yml")


def judge(tmp_path: Path, kind: str, source: str | None, target: str):
    """(None, None) when the file is refused; else the check's result on the derived node."""
    check = {"type": "ping", "node": NODE, "target": target, **({"source": source} if source else {})}
    try:
        cfg = load(tmp_path, kind, check)
    except ConfigError as e:
        return None, str(e)
    [c] = cfg.checks
    clock = Clock()
    lab = DerivedLab(kind, source, target)
    return run_check(c, SCENARIOS[kind]["driver"](lab, NODE), clock=clock, sleep=clock.sleep), None


def mismatched_facts(kind: str, source: str, target: str) -> None:
    """The derivation says what the tools do: the source is one of the node's addresses, of the other family, and the
    ping answer never shows the ping bound to it, yet it got 3/3 replies."""
    sc = SCENARIOS[kind]
    assert ipaddress.ip_address(source).version != ipaddress.ip_address(target).version
    own = "".join(sc["addrs"].values())
    assert f'"{source}"' in own or f'"{source}/' in own, f"{source} is not one of {kind}'s derived addresses"
    out = ping_answer(kind, source, target)
    assert f"from {source}" not in out.splitlines()[0] and "3 packets transmitted, 3" in out


@pytest.mark.parametrize("direction", sorted(MISMATCHED))
@pytest.mark.parametrize("kind", KINDS)
def test_ping_with_a_source_of_the_other_family_is_refused_or_does_not_pass(tmp_path, kind, direction):
    fam, target = MISMATCHED[direction]
    source = SCENARIOS[kind][fam]
    mismatched_facts(kind, source, target)
    r, refused = judge(tmp_path, kind, source, target)
    if refused is not None:
        return   # refused when loaded: validate exits 2, never a pass
    assert not r.passed, (
        f"{kind}: `ping node {NODE} source {source} target {target}` loaded and PASSED ({r.detail}), but the ping tool "
        f"drops or ignores a source of the other family: nothing was sent from {source}, so the return path to it "
        f"was never tested. The banner: {ping_answer(kind, source, target).splitlines()[0]!r}")
