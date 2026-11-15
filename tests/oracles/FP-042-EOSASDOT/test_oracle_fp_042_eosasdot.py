"""Oracle FP-042-EOSASDOT (red team 042-IA RT-0002, verifier 042-IV on 3d71d5a): the EOS driver hands an asdot AS
path to `as_path_regex` as text, so a "no private 4-byte ASN" guard passes on a path through AS 4200000001.

The check as the user means it: "the best path to 192.168.20.0/24 on ceos1 carries no private 4-byte ASN" (a
remove-private-as / leak guard; RFC 6996 range 4200000000-4294967294), written as
`as_path_regex: '^(?!.*\\b42[0-9]{8}\\b)'`. netdryrun.yml takes ASNs in asplain only (config.normalize_as_path refuses
a dotted ASN), and validate accepts the regex (it doesn't match AS_PATH_PROBES' 4200000001).

Why the NOS prints asdot: EOS has a global `bgp asn notation asdot` that switches displayed ASNs to asdot (RFC 5396);
the JSON `asPathEntry.asPath` is the displayed path, a string (tests/fixtures/eos_bgp_paths.txt), not a list of
integers. With it, the path 4200000001 65020 prints as "64086.59905 65020" (64086 * 65536 + 59905 = 4200000001).
NOT CONFIRMED LIVE (verifier: about 70% that `| json` follows the notation); the fix is safe either way.

Device output: DERIVED, not captured (SOURCES.yml has no kind for a derived file, so it is derived here in the test):
tests/fixtures/eos_bgp_paths.txt (cEOS 4.36.3M `show ip bgp 192.168.20.0/24 vrf default | json`, live) with the best
path's asPath "65020" replaced by "64086.59905 65020". Everything else is as captured.

The rule: the EOS driver refuses a dotted token as unexpected output (DriverError, as nxos._as_path does) or reads it
as asplain ("4200000001 65020"); the guard never passes on this output. Commands the derivation doesn't cover answer
rc 1 (an unknown command).

Guards (they pass before and after the fix) are in tests/test_oracle_guards_fp_042_eosasdot.py.
"""
import re
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers import eos
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.eos import EosDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
NODE = "ceos1"
PREFIX = "192.168.20.0/24"
BGP = f"show ip bgp {PREFIX} vrf default | json"
GUARD = r"^(?!.*\b42[0-9]{8}\b)"   # RT-0002's regex: no private 4-byte ASN anywhere in the path
ASDOT = "64086.59905"
ASPLAIN = 4200000001


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def derived(as_path: str) -> str:
    """eos_bgp_paths.txt (live) with the best path's AS path "65020" replaced (DERIVED)."""
    text = fx("eos_bgp_paths.txt")
    old = '"asPath": "65020"\n'
    assert text.count(old) == 1 and '"active": true' in text
    return text.replace(old, f'"asPath": "{as_path}"\n')


class CapturedLab:
    """ceos1 answering the BGP read with `bgp_text`; any other command answers rc 1 (an unknown command)."""

    def __init__(self, bgp_text: str):
        self.bgp_text = bgp_text

    def exec(self, node, cmd, timeout=60, input=None):
        if node == NODE and list(cmd) == ["Cli", "-p", "15", "-c", BGP]:
            return ExecResult(cmd, 0, self.bgp_text, "")
        return ExecResult(cmd, 1, "", f"% Invalid input (not derived: {' '.join(cmd)})")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def bgp_route(bgp_text: str, **attrs):
    c = Clock()
    check = _validate_check(0, {"type": "bgp_route", "node": NODE, "prefix": PREFIX, **attrs}, 20)
    return run_check(check, EosDriver(CapturedLab(bgp_text), NODE), clock=c, sleep=c.sleep)


def asdot_facts():
    a, b = (int(x) for x in ASDOT.split("."))
    assert a * 65536 + b == ASPLAIN and 4200000000 <= ASPLAIN <= 4294967294
    assert re.search(GUARD, f"{ASPLAIN} 65020") is None      # the guard fails on the path in asplain
    assert re.search(GUARD, f"{ASDOT} 65020") is not None    # ... and matches the asdot text


def test_private_4byte_asn_guard_does_not_pass_on_an_asdot_path():
    """RT-0002 as the runner judges it: the guard passed on the best path 64086.59905 65020 (= 4200000001 65020)."""
    asdot_facts()
    r = bgp_route(derived(f"{ASDOT} 65020"), as_path_regex=GUARD)
    assert not r.passed, (f"`as_path_regex: {GUARD}` (no private 4-byte ASN) passed on the EOS best path "
                          f"'{ASDOT} 65020', which is {ASPLAIN} 65020: {r.detail}")


def test_asdot_as_path_is_refused_or_read_as_asplain():
    """The parser never yields a dotted ASN as a normal AS path: unexpected output, or asplain."""
    asdot_facts()
    try:
        paths = eos.parse_bgp_paths(derived(f"{ASDOT} 65020"), PREFIX)
    except DriverError:
        return
    best = [p for p in paths if p.best]
    assert [p.as_path for p in best] == [f"{ASPLAIN} 65020"], (
        f"EOS best path read as {[p.as_path for p in best]!r} from asPath '{ASDOT} 65020': a dotted ASN must be "
        f"refused as unexpected output or converted to asplain ({ASPLAIN} 65020)")
