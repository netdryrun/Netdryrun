"""Guards for oracle FP-042-VERIFYPINSTATIC: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-VERIFYPINSTATIC/ to fail on the fix's parent, so the guards
live here. This file is in the oracle's `evidence:`, so the fix can't change it. The derived edge1 output (marked in
the oracle's docstring) and the intent come from the oracle's own module.

What must keep working:
- the pinned BGP path is the route edge1 selects and installs (no static): INTENT MATCHED, as today;
- the same line with pins edge1's route doesn't meet: not met, as today;
- a line with no pins: the static that wins is part of "the route appears" (no BGP attribute was promised), as today.
"""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-VERIFYPINSTATIC" / "test_oracle_fp_042_verifypinstatic.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_verifypinstatic", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_the_pinned_bgp_path_installed_alone_is_matched():
    after = o.after_outputs(static_hop=None)
    rib = {k.protocol: v for k, v in o.snap(after).items().items() if k.kind == "rib" and k.prefix == o.NEW}
    assert set(rib) == {"bgp"}
    m = o.verify(after)
    assert m.status == "matched", ([d.key.where() for d in m.undeclared], [r.reason for r in m.results])
    assert not m.untested


def test_pins_the_bgp_path_does_not_meet_are_still_not_met():
    m = o.verify(o.after_outputs(static_hop=None), o.INTENT.replace('as_path: "65100"', 'as_path: "65999"'))
    assert m.status != "matched"


def test_a_line_without_pins_still_explains_the_route_that_appears():
    text = f"""
intent:
  - prefix: {o.NEW}
    appears_on: [edge1]
"""
    for static_hop in (None, ("10.0.3.2", "eth3")):
        m = o.verify(o.after_outputs(static_hop=static_hop), text)
        assert m.status == "matched", (static_hop, [d.key.where() for d in m.undeclared])
