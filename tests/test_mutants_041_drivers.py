"""0.4.1 release gate: the stale-path and malformed-path errors on EOS, SR Linux and NX-OS say what was refused, where.

Each test edits a real capture in memory (json.loads, change one field, json.dumps) and asserts the exact error: the
prefix and peer a graceful-restart refusal names, the command an unexpected-output error names, and the snippet of
the offending output it quotes. A refusal that names the wrong peer or no command sends the operator to the wrong place.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun.drivers import DriverError, detect, eos, nxos, srlinux
from netdryrun.drivers.stale import refuse_if_stale, strict_bool
from netdryrun.lab import Node

FIX = Path(__file__).parent / "fixtures"
NOT_SETTLED = "is stale (graceful restart in progress): not settled"


def load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def error(fn, *args) -> str:
    with pytest.raises(DriverError) as ei:
        fn(*args)
    return str(ei.value)


def unexpected_msg(command: str, snippet: str) -> str:
    return f"unexpected output from `{command}`: {snippet}"


# ---- stale.strict_bool / stale.refuse_if_stale -----------------------------------------------------------------------

def test_strict_bool_returns_the_boolean_itself():
    assert strict_bool("cmd", True) is True
    assert strict_bool("cmd", False) is False


def test_strict_bool_error_names_the_command_and_quotes_60_chars():
    msg = error(strict_bool, "show x", "z" * 100)
    assert msg == unexpected_msg("show x", f"stale mark is not a boolean: {'z' * 60!r}")


def test_refuse_if_stale_names_prefix_and_peer_or_a_question_mark():
    refuse_if_stale("10.0.0.0/8", "10.1.1.1", False)   # not stale: no error
    assert error(refuse_if_stale, "10.0.0.0/8", "10.1.1.1", True) == f"10.0.0.0/8: BGP path from 10.1.1.1 {NOT_SETTLED}"
    assert error(refuse_if_stale, "10.0.0.0/8", None, True) == f"10.0.0.0/8: BGP path from ? {NOT_SETTLED}"


# ---- Arista EOS: _bgp_entries ----------------------------------------------------------------------------------------
EOS_PFX = "192.168.20.0/24"


def eos_paths():
    data = load("eos_bgp_paths.txt")
    return data, data["vrfs"]["default"]["bgpRouteEntries"][EOS_PFX]["bgpRoutePaths"]


def test_eos_stale_path_names_the_prefix_and_peer():
    data, paths = eos_paths()
    assert paths[0]["peerEntry"]["peerAddr"] == "10.3.1.2"
    paths[0]["routeType"]["stale"] = True
    msg = error(eos.parse_bgp_paths, json.dumps(data), EOS_PFX)
    assert msg == f"{EOS_PFX}: BGP path from 10.3.1.2 {NOT_SETTLED}"


def test_eos_stale_path_without_peer_entry_is_an_error_for_the_missing_key():
    """It said "from ?" (Layer 6 round 3 on 5e65852): a path without peerEntry is unreadable, stale or not."""
    data, paths = eos_paths()
    paths[0]["routeType"]["stale"] = True
    del paths[0]["peerEntry"]
    assert "no peerEntry" in error(eos.parse_bgp_paths, json.dumps(data), EOS_PFX)


def test_eos_stale_mark_of_unknown_type_names_the_bgp_command():
    data, paths = eos_paths()
    paths[0]["routeType"]["stale"] = "yes"
    msg = error(eos.parse_bgp_paths, json.dumps(data), EOS_PFX)
    assert msg == unexpected_msg(eos.BGP_CMD, "stale is not a boolean: 'yes'")


def test_eos_path_that_is_not_an_object_names_command_key_and_150_chars():
    data, paths = eos_paths()
    paths[0] = "x" * 300
    msg = error(eos.parse_bgp_paths, json.dumps(data), EOS_PFX)
    assert msg == unexpected_msg(eos.BGP_CMD, f"{EOS_PFX} path: {'x' * 150}")


# ---- Nokia SR Linux: _rib_rows ---------------------------------------------------------------------------------------
SRL_PFX = "192.168.20.0/24"


def test_srl_stale_row_names_the_prefix_and_neighbor():
    data = load("srl_bgp_rib_paths.txt")
    assert data["route"][0]["neighbor"] == "10.2.1.2"
    data["route"][0]["stale-route"] = True
    msg = error(srlinux.parse_rib_paths, json.dumps(data), SRL_PFX)
    assert msg == f"{SRL_PFX}: BGP path from 10.2.1.2 {NOT_SETTLED}"


def test_srl_stale_mark_of_unknown_type_names_the_rib_command():
    data = load("srl_bgp_rib_paths.txt")
    data["route"][0]["stale-route"] = "yes"
    msg = error(srlinux.parse_rib_paths, json.dumps(data), SRL_PFX)
    assert msg == unexpected_msg(srlinux.RIB_CMD, "stale mark is not a boolean: 'yes'")


def test_srl_row_without_prefix_names_the_rib_command_and_150_chars():
    data = load("srl_bgp_rib_paths.txt")
    row = {"neighbor": "y" * 300}
    data["route"][0] = row
    msg = error(srlinux.parse_rib_paths, json.dumps(data), SRL_PFX)
    assert msg == unexpected_msg(srlinux.RIB_CMD, str(row)[:150])


def test_srl_row_whose_prefix_is_not_a_prefix_names_the_rib_command():
    data = load("srl_bgp_rib_paths.txt")
    data["route"][0]["prefix"] = "not-a-prefix"
    msg = error(srlinux.parse_rib_paths, json.dumps(data), SRL_PFX)
    assert msg == unexpected_msg(srlinux.RIB_CMD, "not a prefix: 'not-a-prefix'")


# ---- Cisco NX-OS: _bgp_paths_raw -------------------------------------------------------------------------------------

def nxos_paths(data) -> list[dict]:
    """Every BGP path dict in a captured NX-OS reply (the ones carrying `pathstaled`)."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            if "pathstaled" in o:
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    assert found, "the capture no longer has pathstaled: has its format changed?"
    return found


def test_nxos_stale_ipv4_path_names_the_prefix_and_neighbor():
    data = load("nxos_bgp_20.txt")
    p = nxos_paths(data)[0]
    assert p["neighbor"] == "10.0.1.2" and "ipv6neighbor" not in p
    p["pathstaled"] = "true"
    msg = error(nxos.parse_bgp_paths, json.dumps(data), "192.168.20.0/24")
    assert msg == f"192.168.20.0/24: BGP path from 10.0.1.2 {NOT_SETTLED}"


def test_nxos_stale_ipv6_path_names_the_ipv6_neighbor():
    data = load("nxos_bgp_v6.txt")
    p = nxos_paths(data)[0]
    assert p["ipv6neighbor"] == "2001:db8:1::2" and "neighbor" not in p
    p["pathstaled"] = "true"
    msg = error(nxos.parse_bgp_paths, json.dumps(data), "2001:db8:20::/48")
    assert msg == f"2001:db8:20::/48: BGP path from 2001:db8:1::2 {NOT_SETTLED}"


def test_nxos_pathstaled_of_unknown_value_names_the_bgp_command():
    data = load("nxos_bgp_20.txt")
    nxos_paths(data)[0]["pathstaled"] = "yes"
    msg = error(nxos.parse_bgp_paths, json.dumps(data), "192.168.20.0/24")
    assert msg == unexpected_msg(nxos.BGP_CMD, "not a boolean: 'yes'")


def test_nxos_bgp_paths_raw_body_error_names_the_bgp_command():
    # Both public callers parse the body first; this pins the command _bgp_paths_raw itself names.
    data = load("nxos_bgp_20.txt")
    data["result"]["body"] = [data["result"]["body"]]
    msg = error(nxos._bgp_paths_raw, json.dumps(data), "192.168.20.0/24", "default")
    assert msg.startswith(unexpected_msg(nxos.BGP_CMD, "body is not an object: "))


# ---- detect ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("image", ["example/routeros:7.16", "registry.local/RouterOS-chr:7.16"])
def test_detect_routeros_by_image_name_alone(image):
    """Recognised by its image name alone, and refused: RouterOS is a beta driver used only when chosen."""
    with pytest.raises(DriverError) as e:
        detect(Node("r1", "clab-x-r1", "linux", image))
    assert "runs MikroTik RouterOS" in str(e.value)
