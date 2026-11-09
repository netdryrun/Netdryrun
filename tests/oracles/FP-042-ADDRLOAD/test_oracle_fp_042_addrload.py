"""Oracle FP-042-ADDRLOAD: the own-address parsers read JSON that starts after text they skip.

The evidence:
- **The crash** (crash-64187dc6186124ff3f0c0508128ec4d9c7acfc2d in this folder): ClusterFuzzLite's `fuzz_parsers` on
  PR #6 (commit 4747d42, 2026-11-09), reproduced and saved by it.
  - Its first byte (0x0a) picks the target `addresses.parse_eos_interfaces`. The rest is the output: the
    eos_local_ipv4 fixture with "FFFFFFFFF" before its `{` and one byte of a `vrf` value mangled.
  - `parse_eos_interfaces(output, "default", "x")` returns [] on it.
- **The fuzzer's rule** (tests/test_driver_fuzz.py `outcome`): output that is not a real empty answer must raise
  DriverError, never read as "no addresses".
- **The cause** (spec fastfix/oracle-specs/FP-042-ADDRLOAD.md): `addresses._load` starts reading at the first `{` or
  `[` and drops whatever came before it.
  - Every reader of the own-address list goes through it (the ping check's own-target and source guards, red team
    B-9006).
  - None of the captured answers has text before its JSON (each committed fixture starts with `{` or `[`), so no
    captured answer needs that leniency.

The rule: output with text before its JSON is unexpected output, a DriverError; a captured answer with only
whitespace around it still reads exactly as it does now.

The tests here fail on the parent. The guards, which pass before and after the fix, are in
tests/test_oracle_guards_fp_042_addrload.py (listed in ORACLE.yml `evidence:`).
"""
from pathlib import Path

import pytest

from netdryrun.drivers import addresses
from netdryrun.drivers.base import DriverError

HERE = Path(__file__).resolve().parent
FX = HERE.parents[1] / "fixtures"
CRASH = HERE / "crash-64187dc6186124ff3f0c0508128ec4d9c7acfc2d"

# every reader of `_load`, called as the fuzz targets call it (tests/test_driver_fuzz.py CASES), with its fixtures
READERS = {
    "parse_ip_j_addr": (lambda t: addresses.parse_ip_j_addr(t, skip_enslaved=True),
                        ["frr_local_ip_addr.json", "sonic_local_ip_addr.json"]),
    "parse_eos_interfaces": (lambda t: addresses.parse_eos_interfaces(t, "default", "x"),
                             ["eos_local_ipv4.json", "eos_local_ipv6.json"]),
    "parse_nxos_ip_brief": (lambda t: addresses.parse_nxos_ip_brief(t, "default"), ["nxos_local_ip_brief.json"]),
    "parse_nxos_ip_detail": (lambda t: addresses.parse_nxos_ip_detail(t, "default"), ["nxos_local_ip_detail.json"]),
    "parse_nxos_ipv6_detail": (lambda t: addresses.parse_nxos_ipv6_detail(t, "RED"), ["nxos_local_ipv6_detail.json"]),
    "parse_routeros_addresses": (lambda t: addresses.parse_routeros_addresses(addresses._load("x", t), "default", "x"),
                                 ["routeros_local_ipv4.json", "routeros_local_ipv6.json"]),
    "parse_srl_addresses": (lambda t: addresses.parse_srl_addresses(t, "x"),
                            ["srl_local_ipv4.json", "srl_local_ipv6.json"]),
    "parse_junos_terse": (lambda t: addresses.parse_junos_terse(t), ["junos_local_interfaces_terse.json"]),
}
CASES = [(name, fixture) for name, (_, fixtures) in READERS.items() for fixture in fixtures]
IDS = [f"{name}-{fixture}" for name, fixture in CASES]
LEADING = ["% Invalid input\n", "FFFF"]


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def read(name: str, text: str) -> list:
    return sorted(map(str, READERS[name][0](text)))


# ------------------------------------------------------------------ red on 0.4.1

def test_the_fuzzers_crash_input_raises():
    data = CRASH.read_bytes()
    text = data[1:].decode("utf-8", "replace")      # as fuzz_parsers.TestOneInput hands it over
    with pytest.raises(DriverError):
        addresses.parse_eos_interfaces(text, "default", "x")


@pytest.mark.parametrize("lead", LEADING, ids=["cli-error", "junk"])
@pytest.mark.parametrize("name,fixture", CASES, ids=IDS)
def test_text_before_the_json_raises(name, fixture, lead):
    with pytest.raises(DriverError):
        read(name, lead + fx(fixture))
