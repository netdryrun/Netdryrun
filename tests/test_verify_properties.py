"""Verdict invariant: any undeclared change injected into an after-snapshot gives UNDECLARED CHANGES."""
from dataclasses import replace

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from netdryrun.verify.engine import match
from netdryrun.verify.snapshot import BgpAttrs, BgpPath, ItemKey, RibEntry, Session
from verify_helpers import add_new_customer_block, attrs, base, intent, path, rib

NEW_PREFIXES = ["10.250.0.0/24", "0.0.0.0/0", "172.16.0.0/12", "2001:db8:99::/48"]


def mutate(value, how: int):
    """A value that is guaranteed to differ from `value`."""
    if isinstance(value, Session):
        return replace(value, state="idle" if value.established else "established", local_address=None)
    if isinstance(value, tuple):
        e = value[0]
        return (replace(e, distance=e.distance + 1),) if how % 2 else (replace(e, fib=not e.fib),)
    if isinstance(value, BgpPath):
        if how % 3 == 0:
            return replace(value, best=not value.best)
        if how % 3 == 1:
            return replace(value, attrs=_mutate_attrs(value.attrs, how))
        return replace(value, valid=not value.valid)
    assert isinstance(value, BgpAttrs)
    return _mutate_attrs(value, how)


def _mutate_attrs(a: BgpAttrs, how: int) -> BgpAttrs:
    choice = how % 4
    if choice == 0:
        return replace(a, med=(a.med or 0) + 1)
    if choice == 1:
        return replace(a, communities=tuple(sorted(set(a.communities) | {"65000:999"})) if "65000:999" not in
                       a.communities else tuple(c for c in a.communities if c != "65000:999"))
    if choice == 2:
        return replace(a, large_communities=("65000:9:9",) if a.large_communities != ("65000:9:9",) else ())
    return replace(a, local_pref=(a.local_pref or 0) + 7)


@st.composite
def injections(draw, keys):
    kind = draw(st.sampled_from(["remove", "change", "add"]))
    if kind == "add":
        node = draw(st.sampled_from(["cust1", "edge1", "up1", "peer1"]))
        prefix = draw(st.sampled_from(NEW_PREFIXES))
        what = draw(st.sampled_from(["rib", "path", "adj_out", "adj_in", "session"]))
        return ("add", node, prefix, what)
    key = draw(st.sampled_from(keys))
    return (kind, key, draw(st.integers(0, 11)))


def inject(lab, inj):
    if inj[0] == "add":
        _, node, prefix, what = inj
        afi = "ipv6" if ":" in prefix else "ipv4"
        if what == "session":
            from verify_helpers import session
            lab.session(node, "192.0.2.77", session(None, state="active"))
        elif what == "rib":
            lab.rib(node, prefix, rib("static", hops=(), distance=1))
        elif what == "path":
            lab.path(node, prefix, "10.9.9.9", path(as_path="64512", next_hop="10.9.9.9", best=False))
        elif what == "adj_out":
            lab.adj_out(node, "10.9.9.9", prefix, attrs(as_path="64512", next_hop="10.9.9.8"))
        else:
            lab.adj_in(node, "10.9.9.9", prefix, attrs(as_path="64512", next_hop="10.9.9.9"))
        assert afi
        return
    kind, key, how = inj
    items = lab.items[key.node]
    if kind == "remove":
        del items[key]
    else:
        items[key] = mutate(items[key], how)


BASE_KEYS = sorted(k for n in base().items.values() for k in n)
SCENARIO_KEYS = [k for k in sorted(k for n in add_new_customer_block(base()).items.values() for k in n)
                 if k.prefix != "10.101.0.0/24"]
CFG = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@CFG
@given(st.lists(injections(BASE_KEYS), min_size=1, max_size=3))
def test_any_injected_change_with_an_empty_intent_fails(injs):
    after = base()
    for inj in injs:
        try:
            inject(after, inj)
        except KeyError:
            pass   # the same key removed twice
    before = base().snap()
    snap = after.snap()
    if snap.items() == before.items():
        return     # two injections cancelled out (removed then re-added): nothing to judge
    assert match(before, snap, intent()).status == "failed"


@CFG
@given(st.lists(injections(SCENARIO_KEYS), min_size=1, max_size=3))
def test_any_injected_change_beside_a_matched_intent_fails(injs):
    lines = [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}]
    before = base().snap()
    clean = add_new_customer_block(base())
    assert match(before, clean.snap(), intent(lines)).status == "matched"
    after = add_new_customer_block(base())
    for inj in injs:
        try:
            inject(after, inj)
        except KeyError:
            pass
    if after.snap().items() == clean.snap().items():
        return
    m = match(before, after.snap(), intent(lines))
    assert m.status == "failed"
    assert m.undeclared or m.not_happened


def test_the_injection_kinds_cover_every_item_kind():
    kinds = {k.kind for k in BASE_KEYS}
    assert kinds == {"session", "rib", "path", "adj_out"} | (kinds & {"adj_in"})
    assert isinstance(rib()[0], RibEntry) and isinstance(BASE_KEYS[0], ItemKey)
