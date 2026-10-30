"""IOS XE (Catalyst 8000V) text answers: what each one means, plus strict parsers for the ones we have captured.

IOS prints every error as text and nothing else signals it, so the answer text is the only evidence. This module is the
first layer of an IOS XE driver (built later on the router-state contract) and has no I/O. Findings it encodes
(research/iosxe-capture/devnet/CLASSIFICATION-iosxe-17.15.md, from a live IOS XE 17.15.04c capture):

- `% BGP not active` means the BGP process is not configured: a successful, authoritative answer about the device, and
  nothing about any prefix. It is never "no routes".
- Only three answers prove absence, each for one exact table: `% Subnet not in table` (show ip route with a mask),
  `%Prefix not found` (show ip cef P/len), `% No VRF named X` (show vrf detail X).
- An unknown VRF reads differently per command: a route command says so (`unknown_vrf`); BGP and CEF commands print
  `% Invalid input` with the caret under the VRF name, the same text as a typo (`invalid_input`, ambiguous).
- Children of `N.N.N.N/L is subnetted` print without a mask; the mask comes from the header.
- A line a parser does not know raises. It is never skipped.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

from .base import Route, parser, unexpected


@dataclass(frozen=True)
class Answer:
    """What an IOS answer means. `ok` is True only for an answer with content to parse."""
    kind: str                       # ok | bgp_not_active | absent_route | absent_fib | absent_vrf | unknown_vrf |
                                    # invalid_input | other_error | empty | truncated
    detail: str = ""
    caret_column: int | None = None

    @property
    def ok(self) -> bool:
        return self.kind == "ok"


_INVALID = re.compile(r"^% ?Invalid input detected at '\^' marker\.?\s*$")
_NO_VRF = re.compile(r"^% No VRF named (\S+)\s*$")
_UNKNOWN_VRF = re.compile(r"^% IP routing table vrf (\S+) does not exist\s*$")


def classify(command: str, text: str) -> Answer:
    """Classify a whole answer. Only lines starting with `%` in column 0 are error lines (a legend line may contain
    a `%` inside); a pager prompt means the answer was cut."""
    if not isinstance(text, str) or not text.strip():
        return Answer("empty", f"no output from `{command}`")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if any("--More--" in ln for ln in lines):
        return Answer("truncated", "pager prompt in the answer")
    errors = [ln for ln in lines if ln.startswith("%")]
    if not errors:
        return Answer("ok")
    first = errors[0].rstrip()
    if first.rstrip() == "% BGP not active":
        return Answer("bgp_not_active", first)
    if first == "% Subnet not in table":
        return Answer("absent_route", first)
    if first == "%Prefix not found":
        return Answer("absent_fib", first)
    m = _NO_VRF.match(first)
    if m:
        return Answer("absent_vrf", m.group(1))
    m = _UNKNOWN_VRF.match(first)
    if m:
        return Answer("unknown_vrf", m.group(1))
    if _INVALID.match(first):
        idx = lines.index(errors[0])
        col = None
        if idx >= 1 and lines[idx - 1].strip() == "^":
            col = lines[idx - 1].index("^")
        return Answer("invalid_input", first, col)
    return Answer("other_error", first)


# ---- show ip route (full table) ---------------------------------------------------------------------------------
_PROTOCOL = {"L": "local", "C": "connected", "S": "static", "B": "bgp", "R": "rip", "D": "eigrp", "EX": "eigrp",
             "O": "ospf", "IA": "ospf", "N1": "ospf", "N2": "ospf", "E1": "ospf", "E2": "ospf", "i": "isis",
             "su": "isis", "L1": "isis", "L2": "isis", "ia": "isis", "M": "mobile", "m": "omp", "o": "odr",
             "P": "static", "H": "nhrp", "G": "nhrp", "g": "nhrp", "l": "lisp", "a": "application", "U": "static",
             "n": "nat", "Ni": "nat", "No": "nat", "Nd": "nat"}
_FLAGS = set("*+%&p")
_IPV4 = r"\d{1,3}(?:\.\d{1,3}){3}"
_ROUTE = re.compile(rf"^(?P<codes>\S.*?)\s+(?P<prefix>{_IPV4})(?:/(?P<len>\d{{1,2}}))?\s+(?P<rest>.*)$")
_HEADER = re.compile(rf"^\s+(?P<net>{_IPV4})/(?P<len>\d{{1,2}}) is (?:variably )?subnetted, \d+ subnets?(?:, \d+ masks?)?\s*$")
_GATEWAY = re.compile(r"^Gateway of last resort is (?:not set|\S+ to network \S+)\s*$")
_VIA = re.compile(rf"\[\d+/\d+\] via (?P<nh>{_IPV4})(?:,.*)?$")
_DIRECT = re.compile(r"is directly connected, \S+\s*$")
_CONT = re.compile(rf"^\s+\[\d+/\d+\] via (?P<nh>{_IPV4})(?:,.*)?\s*$")


@dataclass
class TableRoute(Route):
    next_hops: list[str] = field(default_factory=list)


@parser("show ip route")
def parse_route_table(text: str) -> list[TableRoute]:
    """Every route in a `show ip route` table. A table with a legend and a gateway line but no routes is an
    observed empty table; anything that is not a table (error text, nothing, a cut answer) raises."""
    a = classify("show ip route", text)
    if not a.ok:
        raise unexpected("show ip route", f"{a.kind}: {a.detail}" if a.detail else a.kind)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines[0].startswith("Codes:"):
        raise unexpected("show ip route", lines[0])
    i = 1
    while i < len(lines) and lines[i].startswith(" ") and lines[i].strip():
        i += 1                                        # the legend continues on indented lines
    routes: list[TableRoute] = []
    header_len: int | None = None
    saw_gateway = False
    last: TableRoute | None = None
    for ln in lines[i:]:
        if not ln.strip():
            continue
        if _GATEWAY.match(ln):
            saw_gateway = True
            continue
        m = _HEADER.match(ln)
        if m:
            header_len = int(m.group("len"))
            last = None
            continue
        c = _CONT.match(ln)
        if c:
            if last is None:
                raise unexpected("show ip route", ln)
            last.next_hops.append(c.group("nh"))
            continue
        m = _ROUTE.match(ln) if not ln.startswith(" ") else None
        if not m:
            raise unexpected("show ip route", ln)
        codes = m.group("codes").split()
        letters = [t.strip("*+%&") for t in codes]
        letters = [t for t in letters if t]
        if not letters or any(t not in _PROTOCOL for t in letters if not set(t) <= _FLAGS):
            raise unexpected("show ip route", f"unknown route code in: {ln}")
        protocol = _PROTOCOL[letters[0]]
        length = m.group("len")
        if length is None:
            if header_len is None:
                raise unexpected("show ip route", f"route without a mask and no subnet header: {ln}")
            length = str(header_len)
        try:
            prefix = str(ipaddress.ip_network(f"{m.group('prefix')}/{length}", strict=False))
        except ValueError:
            raise unexpected("show ip route", ln) from None
        rest = m.group("rest")
        hops: list[str] = []
        if _DIRECT.search(rest):
            pass
        else:
            v = _VIA.search(rest)
            if not v:
                raise unexpected("show ip route", ln)
            hops.append(v.group("nh"))
        last = TableRoute(prefix, protocol, True, hops)
        routes.append(last)
    if not saw_gateway:
        raise unexpected("show ip route", "no `Gateway of last resort` line: not a complete table")
    return routes


def find_routes(routes: list[TableRoute], prefix: str) -> list[TableRoute]:
    """Routes for exactly `prefix`. A covering or longer route is not an exact match."""
    want = str(ipaddress.ip_network(prefix, strict=False))
    return [r for r in routes if r.prefix == want]


# ---- show vrf ---------------------------------------------------------------------------------------------------
_VRF_HEADER = re.compile(r"^\s+Name\s+Default RD\s+Protocols\s+Interfaces\s*$")


@parser("show vrf")
def parse_vrf_list(text: str) -> dict[str, list[str]]:
    """VRF name to its interfaces from `show vrf`. The header must be the one we know; any other row shape raises."""
    a = classify("show vrf", text)
    if not a.ok:
        raise unexpected("show vrf", f"{a.kind}: {a.detail}" if a.detail else a.kind)
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines or not _VRF_HEADER.match(lines[0]):
        raise unexpected("show vrf", lines[0] if lines else "no output")
    hdr = lines[0]
    start = hdr.index("Interfaces")
    vrfs: dict[str, list[str]] = {}
    current: str | None = None
    for ln in lines[1:]:
        if not ln.startswith(" "):
            raise unexpected("show vrf", ln)
        if ln[: start - 1].strip() == "" and ln[start:].strip():
            if current is None:
                raise unexpected("show vrf", ln)
            vrfs[current].append(ln[start:].strip())
            continue
        name = ln[2:34].strip() if len(ln) > 34 else ln.split()[0]
        parts = ln.split()
        if len(parts) < 3 or not name:
            raise unexpected("show vrf", ln)
        rd_ok = re.match(r"^(<not set>|\S+)$", parts[1] if len(parts) > 1 else "") is not None
        if not rd_ok:
            raise unexpected("show vrf", ln)
        current = parts[0]
        iface = ln[start:].strip() if len(ln) > start else ""
        vrfs[current] = [iface] if iface else []
    return vrfs
