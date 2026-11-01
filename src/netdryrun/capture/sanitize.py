"""Deterministic, structure-preserving sanitiser for captured device output.

What it rewrites, the same way in every file of a bundle (one mapping per bundle):
- IPv4 addresses into 10.0.0.0/8, one /16 at a time: the last two octets are kept, /16s keep their order, and a
  shorter prefix (/8 to /15) gets an aligned block, so prefix lengths and containment survive.
- IPv6 addresses into the documentation range 3fff::/20 (RFC 9637), one /32 at a time, in the same way.
- AS numbers where the output says they are AS numbers (keys such as remoteAs and peer-as, AS paths, the AS half of
  a community, `remote-as 65001` and `AS 65001` in text): 2-byte ASNs to 64512 and up, 4-byte ones to 4200000000
  and up, in order. Reserved values (0, 23456, 65535, 4294967295) and well-known communities are kept.
- Hostnames and domain names (given with --hostname, plus the values of hostname-like keys) to host-1, host-2, ...
- Secrets (passwords, keys) to <removed>.

What it keeps: every key, every value that isn't one of the above, list lengths and order, numbers as printed, and
addresses that identify nobody (loopback, link-local, multicast, masks, 0.0.0.0/8, the documentation and
benchmarking ranges, IPv6 ::/8 and 2001:db8::/32), and prefixes shorter than /8 (IPv6 /20). Unknown fields are kept: removing them would hide shape drift.

The mapping never leaves the contributor's machine. Running it twice on the same input gives the same output.
"""
from __future__ import annotations

import ipaddress
import json
import re

VERSION = "1"

V4_POOL = ipaddress.ip_network("10.0.0.0/8")      # 256 /16 slots
V6_POOL = ipaddress.ip_network("3fff::/20")       # 4096 /32 slots
V4_KEEP = [ipaddress.ip_network(n) for n in ("0.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "224.0.0.0/4", "240.0.0.0/4",
                                             "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "198.18.0.0/15")]
V6_KEEP = [ipaddress.ip_network(n) for n in ("::/8", "fe80::/10", "ff00::/8", "2001:db8::/32")]
ASN_RESERVED = frozenset({0, 23456, 65535, 4294967295})
ASN2_BASE, ASN2_LAST = 64512, 65534
ASN4_BASE, ASN4_LAST = 4200000000, 4294967294
KEEP_NAMES = frozenset({"", "localhost", "localdomain", "none", "null", "default", "unknown", "n/a"})

_V4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?(?![\w]|\.\d)")
_V6 = re.compile(r"(?<![\w:.])((?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4})(?:/(\d{1,3}))?(?![\w:.])")
# Keys whose value is an AS number, or an AS path; keys under which AS-like numbers are counts, not ASNs
_AS_KEY = re.compile(r"(?i)^(local|remote|peer|neighbor|my|router|origin|confed(eration)?)?[-_]?(as|asn|as[-_]?number|"
                     r"autonomous[-_]?system)$|^(local|peer|remote)AS$")
_PATH_KEY = re.compile(r"(?i)^as[-_]?path([-_]?(entry|string|segments?|list))?$")
_NOT_ASN_KEY = re.compile(r"(?i)(len|length|count|num|number|size|weight|metric|pref|med|time|age|index|type|id)$")
_COMMUNITY_KEY = re.compile(r"(?i)communit")
_NAME_KEY = re.compile(r"(?i)^(host[-_]?name|domain[-_]?name|domain|fqdn|sys[-_]?name|router[-_]?name|device[-_]?name)$")
_SECRET_KEY = re.compile(r"(?i)(password|passwd|secret|auth[-_]?key|authentication[-_]?key|pre[-_]?shared|psk|md5|"
                         r"key[-_]?string|private[-_]?key)")
# `AS 65001` only in capitals: "as" in a sentence is not an AS number
_TEXT_ASN = re.compile(r"((?i:\b(?:router bgp|remote-as|local-as|peer-as|neighbor-as|autonomous-system)\s+)|"
                       r"\bAS[ :]?|\bASN\s*[:=]?\s*)(\d+)\b")
_TEXT_SECRET = re.compile(r"(?i)(\b(?:password|secret|authentication-key|auth-key|pre-shared-key|key-string|md5)"
                          r"(?:\s+\d)?\s+)(\S+)")
_TEXT_HOSTNAME = re.compile(r"(?im)^\s*(?:hostname|host-name)\s+(\S+)")
_COMMUNITY_TOKEN = re.compile(r"(?:(?<=large:)|(?<![\w.:]))(\d+)(:\d+(?::\d+)?)(?![\w.:])")
_DIGITS = re.compile(r"(?<![\w.:{,])(\d+)(?![\w.:])|(?<=[{,])(\d+)(?=[,}])")


class Raw(str):
    """A JSON number as printed (1.0 stays 1.0, 1e5 stays 1e5)."""


class Obj(list):
    """A JSON object as its (key, value) pairs, repeated keys and order kept."""


def _loads(text: str):
    return json.loads(text, object_pairs_hook=Obj, parse_int=Raw, parse_float=Raw, parse_constant=Raw)


def _is_json(text: str) -> bool:
    s = text.strip()
    if not s or s[0] not in "{[":
        return False
    try:
        _loads(s)
        return True
    except (ValueError, RecursionError):
        return False


def _dumps(value, indent: str | None, colon: str, depth: int = 0) -> str:
    if isinstance(value, Raw):
        return str(value)
    if not isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    is_obj = isinstance(value, Obj)
    if not value:
        return "{}" if is_obj else "[]"
    if is_obj:
        items = [json.dumps(k, ensure_ascii=False) + colon + _dumps(v, indent, colon, depth + 1) for k, v in value]
    else:
        items = [_dumps(v, indent, colon, depth + 1) for v in value]
    o, c = ("{", "}") if is_obj else ("[", "]")
    if indent is None:
        return o + ("," + (" " if colon == ": " else "")).join(items) + c
    pad, inner = "\n" + indent * depth, "\n" + indent * (depth + 1)
    return o + inner + ("," + inner).join(items) + pad + c


def _layout(text: str) -> tuple[str | None, str]:
    m = re.search(r"\n([ \t]+)\S", text)
    indent = m.group(1) if m and "\n" in text.strip() else None
    m = re.search(r'"([ 	]*:[ 	]*)\S', text)
    return indent, m.group(1) if m else ":"


def _keep_v4(a) -> bool:
    return any(a in n for n in V4_KEEP)


def _keep_v6(a) -> bool:
    return any(a in n for n in V6_KEEP)


def _huge(m, below: int) -> bool:
    """A prefix shorter than /8 (IPv6: /20) covers too much space to say whose network it is (192.0.0.0/2, 2000::/3):
    kept as printed. Addresses under it are still rewritten, so containment in it is not kept."""
    return m.group(2) is not None and int(m.group(2)) < below


def _parse_addr(text: str):
    try:
        return ipaddress.ip_address(text.split("%")[0])
    except ValueError:
        return None


class Sanitizer:
    """One bundle's mapping. collect() every text first, then build(), then rewrite each text."""

    def __init__(self, hostnames=()):
        self.v4_units: set[int] = set()
        self.v6_units: set[int] = set()
        self.v4_short: set[tuple[int, int]] = set()   # (network as int, length) of prefixes shorter than /16
        self.v6_short: set[tuple[int, int]] = set()   # shorter than /32
        self.asns: set[int] = set()
        self.names: set[str] = {h.strip().lower() for h in hostnames if h and h.strip().lower() not in KEEP_NAMES}
        self.problems: list[str] = []
        self.v4_map: dict[int, int] = {}
        self.v6_map: dict[int, int] = {}
        self.asn_map: dict[int, int] = {}
        self.name_map: dict[str, str] = {}
        self.counts = {"ipv4_addresses": 0, "ipv6_addresses": 0, "as_numbers": 0, "names": 0, "secrets": 0}

    # ---- pass 1: what is in the bundle --------------------------------------------------------------------------
    def collect(self, text: str) -> None:
        self._collect_addresses(text)
        for m in _TEXT_ASN.finditer(text):
            self._asn(m.group(2))
        for m in _TEXT_HOSTNAME.finditer(text):
            self._name(m.group(1))
        if _is_json(text):
            self._walk(_loads(text.strip()), [], collect=True)

    def _collect_addresses(self, text: str) -> None:
        for m in _V4.finditer(text):
            a = _parse_addr(m.group(1))
            if a is None or a.version != 4 or _keep_v4(a) or _huge(m, 8):
                continue
            self.v4_units.add(int(a) >> 16)
            if _huge(m, 8):
                continue
            if m.group(2) is not None and int(m.group(2)) < 16:
                ln = int(m.group(2))
                self.v4_short.add((int(a) & ~((1 << (32 - ln)) - 1) & 0xFFFFFFFF, ln))
        for m in _V6.finditer(text):
            a = _parse_addr(m.group(1))
            if a is None or a.version != 6 or _keep_v6(a):
                continue
            if _huge(m, 20):
                continue
            self.v6_units.add(int(a) >> 96)
            if m.group(2) is not None and int(m.group(2)) < 32:
                ln = int(m.group(2))
                self.v6_short.add((int(a) & ~((1 << (128 - ln)) - 1), ln))

    def _asn(self, token) -> None:
        try:
            n = int(str(token))
        except ValueError:
            return
        if 0 <= n <= 4294967295 and n not in ASN_RESERVED:
            self.asns.add(n)

    def _name(self, value) -> None:
        v = str(value).strip().lower()
        if v not in KEEP_NAMES and not _parse_addr(v) and not re.fullmatch(r"[\d.]+", v):
            self.names.add(v)

    # ---- the mapping --------------------------------------------------------------------------------------------
    def build(self) -> None:
        self.v4_map = self._blocks(self.v4_units, self.v4_short, unit_bits=16, slots=256, base=int(V4_POOL[0]) >> 16,
                                   what="IPv4 /16s")
        self.v6_map = self._blocks(self.v6_units, self.v6_short, unit_bits=32, slots=4096, base=int(V6_POOL[0]) >> 96,
                                   what="IPv6 /32s")
        two = sorted(a for a in self.asns if a <= 65535)
        four = sorted(a for a in self.asns if a > 65535)
        if len(two) > ASN2_LAST - ASN2_BASE + 1:
            self.problems.append(f"{len(two)} 2-byte AS numbers: more than the private range holds")
        self.asn_map = {a: ASN2_BASE + i for i, a in enumerate(two)} | {a: ASN4_BASE + i for i, a in enumerate(four)}
        # longest first, so "r10" is never rewritten as "r1" plus "0"
        self.name_map = {n: f"host-{i + 1}" for i, n in enumerate(sorted(self.names))}
        self._name_re = (re.compile(r"(?i)(?<![\w-])(" + "|".join(re.escape(n) for n in sorted(self.names, key=len, reverse=True))
                                    + r")(?![\w-])") if self.names else None)

    def _blocks(self, units: set[int], short: set[tuple[int, int]], unit_bits: int, slots: int, base: int,
                what: str) -> dict[int, int]:
        """unit -> pool unit: units in sorted order, a short prefix's units as one aligned block."""
        width = 32 if unit_bits == 16 else 128
        blocks: list[tuple[int, int]] = []          # (first unit, number of units)
        for net, ln in sorted(short, key=lambda x: (x[1], x[0])):
            first, size = net >> (width - unit_bits), 1 << (unit_bits - ln)
            if not any(f <= first < f + s for f, s in blocks):
                blocks = [(f, s) for f, s in blocks if not first <= f < first + size] + [(first, size)]
        covered = {u for f, s in blocks for u in range(f, f + s)}
        items = sorted(blocks + [(u, 1) for u in units if u not in covered])
        out: dict[int, int] = {}
        cursor = 0
        for first, size in items:
            cursor = -(-cursor // size) * size      # align the block to its size
            for i in range(size):
                out[first + i] = base + cursor + i
            cursor += size
        if cursor > slots:
            self.problems.append(f"{len(items)} distinct {what} need {cursor} slots; the pool has {slots}")
        return out

    # ---- pass 2: rewrite ----------------------------------------------------------------------------------------
    def text(self, text: str) -> str:
        """Every address, recognised AS number, name and secret in a text, rewritten."""
        if _is_json(text):
            indent, colon = _layout(text)
            lead = text[:len(text) - len(text.lstrip())]
            trail = text[len(text.rstrip()):]
            return lead + _dumps(self._walk(_loads(text.strip()), [], collect=False), indent, colon) + trail
        out = self._plain(text)
        out = _TEXT_ASN.sub(lambda m: m.group(1) + self._map_asn(m.group(2)), out)
        out = re.sub(r"(?im)^.*communit.*$", lambda m: self._communities(m.group(0)), out)
        out = _TEXT_SECRET.sub(self._secret, out)
        return out

    def names_only(self, text: str) -> str:
        """Only the names rewritten: what a text's shape is compared on (a name is not structure)."""
        return self._name_re.sub(self._sub_name, text) if self._name_re is not None else text

    def _secret(self, m) -> str:
        self.counts["secrets"] += 1
        return m.group(1) + "<removed>"

    def _plain(self, s: str) -> str:
        """Addresses and names in a string (no AS context)."""
        s = _V6.sub(self._sub_v6, s)
        s = _V4.sub(self._sub_v4, s)
        if self._name_re is not None:
            s = self._name_re.sub(self._sub_name, s)
        return s

    def _sub_v4(self, m) -> str:
        a = _parse_addr(m.group(1))
        if a is None or a.version != 4 or _keep_v4(a) or _huge(m, 8):
            return m.group(0)
        unit = int(a) >> 16
        if unit not in self.v4_map:   # never seen by collect(): keep it, and the leak check reports it
            self.problems.append(f"{m.group(1)} was not collected before the rewrite")
            return m.group(0)
        self.counts["ipv4_addresses"] += 1
        new = ipaddress.IPv4Address((self.v4_map[unit] << 16) | (int(a) & 0xFFFF))
        return str(new) + (f"/{m.group(2)}" if m.group(2) is not None else "")

    def _sub_v6(self, m) -> str:
        raw = m.group(1)
        a = _parse_addr(raw)
        if a is None or a.version != 6 or _keep_v6(a) or _huge(m, 20):
            return m.group(0)
        if int(a) >> 96 not in self.v6_map:
            self.problems.append(f"{raw} was not collected before the rewrite")
            return m.group(0)
        self.counts["ipv6_addresses"] += 1
        new = ipaddress.IPv6Address((self.v6_map[int(a) >> 96] << 96) | (int(a) & ((1 << 96) - 1)))
        return new.compressed + (f"/{m.group(2)}" if m.group(2) is not None else "")

    def _sub_name(self, m) -> str:
        self.counts["names"] += 1
        return self.name_map[m.group(1).lower()]

    def _map_asn(self, token: str) -> str:
        try:
            n = int(token)
        except ValueError:
            return token
        if n in self.asn_map:
            self.counts["as_numbers"] += 1
            return str(self.asn_map[n])
        return token

    def _communities(self, s: str) -> str:
        return _COMMUNITY_TOKEN.sub(lambda m: self._map_asn(m.group(1)) + m.group(2), s)

    def _as_tokens(self, s: str) -> str:
        return _DIGITS.sub(lambda m: self._map_asn(m.group(1) or m.group(2)), s)

    def _walk(self, node, path: list[str], collect: bool):
        """Collect from, or rewrite, a parsed JSON value. `path` is the keys above it."""
        key = path[-1] if path else ""
        as_ctx = any(_AS_KEY.match(k) or _PATH_KEY.match(k) for k in path)
        comm_ctx = any(_COMMUNITY_KEY.search(k) for k in path)
        if isinstance(node, Obj):
            pairs = [(k, self._walk(v, path + [k], collect)) for k, v in node]
            return None if collect else Obj((self._plain(k), v) for k, v in pairs)
        if isinstance(node, list):
            items = [self._walk(v, path, collect) for v in node]   # an element is read under its list's key
            return None if collect else items
        bare = key
        if isinstance(node, Raw):
            asn_here = as_ctx and not (_NOT_ASN_KEY.search(bare) and not _AS_KEY.match(bare))
            if asn_here and re.fullmatch(r"\d+", node):
                if collect:
                    self._asn(node)
                    return None
                return Raw(self._map_asn(node))
            return None if collect else node
        if not isinstance(node, str):
            return None if collect else node
        if _SECRET_KEY.search(bare) and node:
            if collect:
                return None
            self.counts["secrets"] += 1
            return "<removed>"
        if _NAME_KEY.match(bare):
            if collect:
                self._name(node)
                return None
        if collect:
            if as_ctx:
                for m in _DIGITS.finditer(node):
                    self._asn(m.group(1) or m.group(2))
            if comm_ctx:
                for m in _COMMUNITY_TOKEN.finditer(node):
                    self._asn(m.group(1))
            for m in _TEXT_ASN.finditer(node):
                self._asn(m.group(2))
            return None
        out = self._plain(node)
        if as_ctx:
            out = self._as_tokens(out)
        elif comm_ctx:
            out = self._communities(out)
        else:
            out = _TEXT_ASN.sub(lambda m: m.group(1) + self._map_asn(m.group(2)), out)
        return out

    def mapping(self) -> dict:
        """The mapping, for the contributor's own records (never part of the bundle)."""
        def v4(u):
            return f"{u >> 8}.{u & 0xFF}.0.0/16"

        def v6(u):
            return str(ipaddress.IPv6Address(u << 96)) + "/32"
        return {"sanitizer": VERSION,
                "ipv4_16": {v4(k): v4(v) for k, v in sorted(self.v4_map.items())},
                "ipv6_32": {v6(k): v6(v) for k, v in sorted(self.v6_map.items())},
                "asn": {str(k): v for k, v in sorted(self.asn_map.items())},
                "hostname": dict(sorted(self.name_map.items()))}


# ---- checks that don't trust the rewrite: run on the output alone ------------------------------------------------
def leaks(text: str, originals: dict | None = None) -> list[str]:
    """What in a sanitised text still looks identifying: a public address outside the kept ranges, an AS number in
    an AS context outside the private ranges, or (with the mapping's originals) a name that was replaced."""
    found = []
    for m in _V4.finditer(text):
        a = _parse_addr(m.group(1))
        if a and a.version == 4 and not _keep_v4(a) and a not in V4_POOL and not _huge(m, 8):
            found.append(f"IPv4 address {m.group(1)}")
    for m in _V6.finditer(text):
        a = _parse_addr(m.group(1))
        if a and a.version == 6 and not _keep_v6(a) and a not in V6_POOL and not _huge(m, 20):
            found.append(f"IPv6 address {m.group(1)}")
    probe = Sanitizer()
    probe.collect(text)
    for n in sorted(probe.asns):
        if not (ASN2_BASE <= n <= ASN2_LAST or ASN4_BASE <= n <= ASN4_LAST):
            found.append(f"AS number {n}")
    for name in (originals or {}).get("hostname", {}):
        if re.search(r"(?i)(?<![\w-])" + re.escape(name) + r"(?![\w-])", text):
            found.append(f"name {name}")
    return sorted(set(found))


def shape(text: str):
    """The structure of an output: for JSON, the key paths and value types with addresses written `*`; for text,
    the lines with digits written N. Sanitising must not change it."""
    if not _is_json(text):
        return sorted({re.sub(r"[\w.:/%-]*\d[\w.:/%-]*", "N", ln) for ln in text.splitlines()})
    out: set[str] = set()

    def walk(v, p):
        if isinstance(v, Obj):
            for k, x in v:
                k = "*" if _parse_addr(k.split("/")[0]) else k
                walk(x, f"{p}/{k}")
        elif isinstance(v, list):
            out.add(f"{p}[{len(v)}]")
            for x in v:
                walk(x, p + "[]")
        else:
            out.add(f"{p}:{'num' if isinstance(v, Raw) else type(v).__name__}")
    walk(_loads(text.strip()), "")
    return sorted(out)
