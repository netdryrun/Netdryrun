"""The reference docs claim exactly what the code does: keys, values, defaults, options, exit codes, drivers.

`test_config_strict.py` already loads every YAML snippet in the docs. This covers the claims that are not
YAML: the reference tables. A key documented but not accepted, a key accepted but not documented, a default
that differs, an exit code nobody returns: each turns CI red here, naming the row. (0.3.1's cold review
found range-check docs disagreeing with the code; HQ lesson 30: the README understated what `route` does.)

Also: every topology the project ships pins its NOS image, so a test run can't silently move to a new NOS
release (driver drift).
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
import yaml

from netdryrun import checks, cli, config, runner
from netdryrun.drivers import DRIVERS

ROOT = Path(__file__).resolve().parents[1]
CONFIG_MD = (ROOT / "website" / "docs" / "reference" / "config.md").read_text(encoding="utf-8")
CLI_MD = (ROOT / "website" / "docs" / "reference" / "cli.md").read_text(encoding="utf-8")
CLI_PY = inspect.getsource(cli)

ROW_KEY = re.compile(r"^\| `([^`]+)`", re.M)


def section(text: str, heading: str) -> str:
    """The text under a Markdown heading, up to the next heading of the same or a higher level."""
    m = re.search(rf"^(#+) {re.escape(heading)}\s*$", text, re.M)
    assert m, f"heading {heading!r} not found: the docs were restructured, update this test"
    level = len(m.group(1))
    end = re.compile(rf"^#{{1,{level}}} ", re.M).search(text, m.end())
    return text[m.end(): end.start() if end else len(text)]


def first_table(text: str) -> str:
    m = re.search(r"((?:^\|.*\n)+)", text, re.M)
    assert m, "no table in this section"
    return m.group(1)


def row_keys(table: str) -> list[str]:
    return ROW_KEY.findall(table)


def row(table: str, key: str) -> str:
    m = re.search(rf"^\| `{re.escape(key)}` \|(.*)$", table, re.M)
    assert m, f"no row for `{key}`"
    return m.group(1)


def backticked(text: str) -> set[str]:
    return set(re.findall(r"`([^`]+)`", text))


# --------------------------------------------------------------------------------------- netdryrun.yml

def test_top_level_keys_table_matches_the_validator():
    keys = row_keys(first_table(section(CONFIG_MD, "Top-level keys")))
    top = {k for k in keys if not k.startswith("nodes.")}
    node = {k.split(".", 2)[2] for k in keys if k.startswith("nodes.<node>.")}
    assert top == set(config.TOP_LEVEL_KEYS)
    assert node == set(config.NODE_KEYS)


def test_common_check_keys_table():
    keys = set(row_keys(first_table(section(CONFIG_MD, "Keys every check accepts"))))
    # node and vrf are listed here because every type takes them; the code declares them per type
    assert keys - {"node", "vrf"} == set(config.COMMON_KEYS)
    for ctype, spec in config.CHECK_TYPES.items():
        assert "node" in spec["required"] and "vrf" in spec["optional"], ctype


@pytest.mark.parametrize("ctype", sorted(config.CHECK_TYPES))
def test_each_check_type_documents_exactly_its_keys(ctype):
    common = set(row_keys(first_table(section(CONFIG_MD, "Keys every check accepts"))))
    own = set(row_keys(first_table(section(CONFIG_MD, ctype))))
    spec = config.CHECK_TYPES[ctype]
    code = set(spec["required"]) | set(spec["optional"])
    documented = own | (common - set(config.COMMON_KEYS))   # vrf from the common table
    undocumented = sorted(code - documented - set(config.COMMON_KEYS))
    assert not undocumented, f"{ctype}: keys the code accepts but the reference doesn't list: {undocumented}"
    phantom = sorted(own - code)
    assert not phantom, f"{ctype}: keys the reference lists but the code refuses: {phantom}"
    if "vrf" not in code:
        pytest.fail(f"{ctype} doesn't accept vrf, but the common-keys table says every check does")


@pytest.mark.parametrize("ctype", sorted(config.CHECK_TYPES))
def test_required_column_matches(ctype):
    table = first_table(section(CONFIG_MD, ctype))
    for key in row_keys(table):
        if key == "node":
            continue
        required_cell = row(table, key).split("|")[0].strip()
        assert (required_cell == "yes") == (key in config.CHECK_TYPES[ctype]["required"]), \
            f"{ctype}.{key}: the reference says required={required_cell!r}"


def test_check_type_list():
    common = first_table(section(CONFIG_MD, "Keys every check accepts"))
    assert backticked(row(common, "type")) == set(config.CHECK_TYPES)


def test_value_lists():
    s = first_table(section(CONFIG_MD, "bgp_session"))
    assert backticked(row(s, "state")) == set(config.BGP_STATES)
    px = first_table(section(CONFIG_MD, "bgp_prefixes"))
    assert backticked(row(px, "afi")) == set(config.AFIS)
    ping = first_table(section(CONFIG_MD, "ping"))
    assert backticked(row(ping, "expect")) == {"success", "failure"}
    top = first_table(section(CONFIG_MD, "Top-level keys"))
    assert backticked(row(top, "nodes.<node>.driver")) & set(DRIVERS) == set(config.DRIVER_NAMES) == set(DRIVERS)


DISPLAY = {"frr": "FRR", "sonic": "SONiC", "srlinux": "SR Linux", "eos": "Arista EOS"}


def test_evpn_support_claim_matches_the_drivers():
    afi = row(first_table(section(CONFIG_MD, "bgp_prefixes")), "afi")
    supported, _, refused = afi.partition("not on")
    assert refused, "the afi row no longer says where evpn is not supported"
    for name, cls in DRIVERS.items():
        where = refused if "evpn" in cls.unsupported_afis else supported
        assert DISPLAY[name] in where, f"the afi row puts {DISPLAY[name]} on the wrong side for evpn"


def test_protocol_names_are_accepted():
    table = first_table(section(CONFIG_MD, "Protocol names"))
    used = row_keys(table)
    assert used, "no protocol names table"
    assert set(used) <= set(config.PROTOCOLS), f"documented protocols the validator refuses: {set(used) - set(config.PROTOCOLS)}"


def test_scenario_and_inject_keys_tables():
    sc = section(CONFIG_MD, "Failure scenarios")
    tables = re.findall(r"((?:^\|.*\n)+)", sc, re.M)
    scenario = next(t for t in tables if "`node_isolated`" in t)
    assert set(row_keys(scenario)) == set(config.SCENARIO_KEYS)
    inject = first_table(section(CONFIG_MD, "Injecting routes"))
    assert set(row_keys(inject)) == set(config.INJECT_KEYS)


def test_driver_table_has_a_row_and_a_column_for_everything():
    table = first_table(section(CONFIG_MD, "Drivers"))
    header = table.splitlines()[0]
    for name in DRIVERS:
        assert DISPLAY[name] in header, f"driver {name} has no column in the drivers table"
    for ctype in config.CHECK_TYPES:
        assert re.search(rf"^\| `{ctype}`", table, re.M), f"check type {ctype} has no row in the drivers table"


def test_documented_defaults():
    top = first_table(section(CONFIG_MD, "Top-level keys"))
    code_default = float(re.search(r'"timeout" in data else ([\d.]+)', inspect.getsource(config.load)).group(1))
    assert float(row(top, "timeout").split("|")[1].strip(" `")) == code_default
    common = first_table(section(CONFIG_MD, "Keys every check accepts"))
    hold_default = inspect.signature(runner.run).parameters["hold"].default
    assert f"`--hold` ({hold_default:g})" in row(common, "hold")
    ping = first_table(section(CONFIG_MD, "ping"))
    assert re.search(r'p\.get\("count", 3\)', inspect.getsource(checks._ping))
    assert "`3`" in row(ping, "count")


# ------------------------------------------------------------------------------------------------- CLI

def test_every_cli_option_is_documented_and_every_documented_option_exists():
    documented = set(re.findall(r"^\| `(--[a-z-]+)", CLI_MD, re.M))
    code = set(re.findall(r'add_argument\("(--[a-z-]+)"', CLI_PY)) - {"--version"}
    assert code - documented == set(), f"options the CLI has but cli.md doesn't list: {sorted(code - documented)}"
    assert documented - code == set(), f"options cli.md lists but the CLI doesn't have: {sorted(documented - code)}"


def test_documented_option_defaults():
    defaults = inspect.signature(runner.run).parameters
    opts = CLI_MD
    for flag, key in (("--settle", "settle"), ("--hold", "hold")):
        m = re.search(rf"^\| `{flag} SECONDS` \| `([\d.]+)`", opts, re.M)
        assert m and float(m.group(1)) == defaults[key].default
        assert re.search(rf'"{flag}", type=_seconds, default={defaults[key].default}', CLI_PY)


def test_exit_code_table_matches_the_code():
    table = first_table(section(CLI_MD, "Exit codes"))
    rows = dict(re.findall(r"^\| `(\d+)` \| `(\w+)` \|", table, re.M))
    documented = {int(k): v for k, v in rows.items()}
    from netdryrun.runner import RunReport, signal_exit_code
    fake = type("R", (), {})
    for status in ("passed", "failed", "inconclusive", "error"):
        r = fake()
        r.status = status
        code = RunReport.exit_code.fget(r)
        assert documented.get(code) == status, f"exit code {code} ({status}) is not documented as {status}"
    import signal
    for sig in ("SIGINT", "SIGTERM", "SIGHUP"):
        code = signal_exit_code(getattr(signal, sig))
        assert documented.get(code) == "error", f"{sig} exits {code}, documented as {documented.get(code)}"
    # the CLI's own --help epilog lists the same codes
    in_help = {int(c) for line in re.findall(r"^\s+(\d+(?:, \d+)*)\s", cli.EXIT_CODES, re.M) for c in line.split(", ")}
    assert in_help == set(documented)


# --------------------------------------------------------------------------------- pinned NOS images

# A shipped topology that can't pin its image yet, and why. Pinning is how a NOS update shows up as a
# deliberate commit (with re-captured fixtures) instead of a silent change under the tests.
UNPINNED_ON_PURPOSE: dict[str, str] = {}


def _topologies():
    files = sorted(ROOT.glob("examples/**/*.clab.yml")) + sorted(ROOT.glob("corpus/**/base/*.clab.yml"))
    return [pytest.param(f, id=str(f.relative_to(ROOT)).replace("\\", "/")) for f in files]


@pytest.mark.parametrize("topo", _topologies())
def test_every_shipped_topology_pins_its_image(topo):
    rel = str(topo.relative_to(ROOT)).replace("\\", "/")
    data = yaml.safe_load(topo.read_text(encoding="utf-8")) or {}
    t = data.get("topology") or {}
    images = [n.get("image") for n in (t.get("nodes") or {}).values() if isinstance(n, dict) and n.get("image")]
    images += [k.get("image") for k in (t.get("kinds") or {}).values() if isinstance(k, dict) and k.get("image")]
    images += [k.get("image") for k in [t.get("defaults") or {}] if k.get("image")]
    unpinned = [i for i in images if ":" not in i.rsplit("/", 1)[-1] or i.endswith(":latest")]
    if rel in UNPINNED_ON_PURPOSE:
        assert unpinned, f"{rel} pins its image now: remove it from UNPINNED_ON_PURPOSE"
        pytest.xfail(UNPINNED_ON_PURPOSE[rel])
    assert not unpinned, f"{rel}: unpinned NOS images {unpinned} (pin a version tag)"


def test_there_are_topologies_to_check():
    assert len(_topologies()) >= 8


def test_the_verdict_strings_the_docs_quote_are_the_ones_the_mcp_server_returns():
    """0.3.2 agent contract: agents copy these strings, so a doc that quotes an old or edited verdict is a wrong
    instruction. The spec and the AI agents page list all three; the shorter surfaces quote the pass and fail."""
    mcp_server = pytest.importorskip("netdryrun.mcp_server")
    full = [ROOT / "website" / "docs" / "spec" / "verdict-v1.md", ROOT / "website" / "docs" / "ai-agents.md",
            ROOT / "website" / "docs" / "schemas" / "mcp-result-v1.json"]
    short = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "skills" / "netdryrun" / "SKILL.md"]
    for path in full + short:
        text = path.read_text(encoding="utf-8")
        wanted = mcp_server.VERDICT_ENUM if path in full else mcp_server.VERDICT_ENUM[:2]
        for verdict in wanted:
            assert verdict in text, f"{path.relative_to(ROOT)} doesn't quote the verdict {verdict!r}"
