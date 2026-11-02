"""`with:` on appears_on explains only what it pins (acceptance round B-6, 2026-11-02): the paths and received routes
from a neighbor whose route matches every BGP pin. A new path for the same prefix from any other neighbor, best or
not, stays undeclared, so the verdict fails."""
from netdryrun.verify.engine import match
from verify_helpers import attrs, base, intent, path, rib

P = "10.101.0.0/24"


def run(before, after, lines):
    return match(before.snap(), after.snap(), intent(lines))


def _customer_and_peer(peer_as_path="65020 65666"):
    after = base()
    after.path("up1", P, "10.0.2.1", path(best=True, as_path="65000 65101", next_hop="10.0.2.1"))
    after.path("up1", P, "10.0.9.2", path(best=False, as_path=peer_as_path, next_hop="10.0.9.2"))
    after.rib("up1", P, rib(hops=("10.0.2.1",)))
    return after


def test_a_path_from_a_neighbor_the_pin_does_not_name_is_undeclared():
    m = run(base(), _customer_and_peer(), [{"prefix": P, "appears_on": "up1",
                                            "with": {"from": "10.0.2.1", "as_path": "65000 65101"}}])
    assert m.status == "failed"
    assert [d.key.where() for d in m.undeclared if d.key.kind == "path"] == [f"up1 {P} path from 10.0.9.2"]


def test_a_from_pin_alone_still_leaves_the_other_neighbor_undeclared():
    """The peer sends the same AS path: only `from` tells them apart, and it does."""
    m = run(base(), _customer_and_peer("65000 65101"), [{"prefix": P, "appears_on": "up1", "with": {"from": "10.0.2.1"}}])
    assert m.status == "failed" and {d.key.neighbor for d in m.undeclared if d.key.kind == "path"} == {"10.0.9.2"}


def test_pins_that_both_paths_satisfy_explain_both():
    """A pin that doesn't tell the neighbors apart (the same AS path, no `from`) explains both: it pinned nothing else."""
    m = run(base(), _customer_and_peer("65000 65101"), [{"prefix": P, "appears_on": "up1",
                                                        "with": {"as_path": "65000 65101"}}])
    assert not [d for d in m.undeclared if d.key.kind == "path"]


def test_without_pins_every_new_path_is_explained_as_before():
    m = run(base(), _customer_and_peer(), [{"prefix": P, "appears_on": "up1"}])
    assert not [d for d in m.undeclared if d.key.kind == "path"]


def test_a_pin_a_received_route_cannot_show_never_matches_it():
    """originator_id isn't shown before inbound policy: `originator_id: null` matches the declared neighbor's path,
    never another neighbor's received route (which can't show it)."""
    after = base()
    after.path("up1", P, "10.0.2.1", path(best=False, as_path="65000 65101", next_hop="10.0.2.1"))
    after.adj_in("up1", "10.0.9.2", P, attrs(as_path="65020 65666", next_hop="10.0.9.2"))
    m = run(base(), after, [{"prefix": P, "appears_on": "up1", "state": "received", "with": {"originator_id": None}}])
    assert m.status == "failed"
    assert [d.key.where() for d in m.undeclared if d.key.kind in ("path", "adj_in")] == \
        [f"up1 {P} received from 10.0.9.2 (before inbound policy)"]


def test_received_before_and_after_policy_from_the_pinned_neighbor_and_nothing_else():
    """state: received. The pinned neighbor's route seen before inbound policy (prepended) and after both count;
    the second neighbor's received route does not."""
    after = base()
    after.path("up1", P, "10.0.2.1", path(best=False, as_path="65000 65101", next_hop="10.0.2.1"))
    after.adj_in("up1", "10.0.2.1", P, attrs(as_path="65000 65000 65101", next_hop="10.0.2.1"))
    after.adj_in("up1", "10.0.9.2", P, attrs(as_path="65020 65666", next_hop="10.0.9.2"))
    m = run(base(), after, [{"prefix": P, "appears_on": "up1", "state": "received", "with": {"as_path": "65000 65101"}}])
    assert m.status == "failed"
    assert [d.key.where() for d in m.undeclared if d.key.kind in ("path", "adj_in")] == \
        [f"up1 {P} received from 10.0.9.2 (before inbound policy)"]


def test_a_received_route_alone_cannot_meet_a_pin_it_cannot_show():
    """The line's own pin check (_pins_ok): the only new candidate is a route received before inbound policy, which
    shows no originator_id, so `originator_id: null` is unknown there, not "no originator": the line isn't met. With an
    allow_anywhere glob explaining the leftover route, a missing attribute read as null gave INTENT MATCHED (Layer 6
    on b03cb7a; mutants _pins_ok 53 and 55)."""
    after = base()
    after.adj_in("up1", "10.0.9.2", P, attrs(as_path="65020 65666", next_hop="10.0.9.2"))
    m = match(base().snap(), after.snap(), intent([{"prefix": P, "appears_on": "up1", "state": "received",
                                                    "with": {"originator_id": None}}], allow=["10.101.*.0/24"]))
    assert m.status == "failed"
    assert not m.lines[0].happened
    assert m.lines[0].reason == "up1: originator_id is not shown, pinned null"
