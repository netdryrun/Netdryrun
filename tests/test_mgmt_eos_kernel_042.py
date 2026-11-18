"""cEOS lists the container's Linux default as a `kernel` route over Management0 while it is still starting; prepare
waits that out (bounded), then judges as before. Derived inputs shaped like `show ip route vrf all | json`."""
import json

import pytest

from netdryrun import mgmt
from netdryrun.lab import ExecResult, LabError
from netdryrun.mgmt import ManagementPathError
from test_mgmt import GW4, GW6, EosLab


def _route(rtype, gw, intf="Management0"):
    return {"routeType": rtype, "vias": [{"nexthopAddr": gw, "interface": intf}]}


class KernelLab(EosLab):
    """Its table lists `extra` routes (per family) for the first `lasts` table reads of each family."""

    def __init__(self, extra4=None, extra6=None, lasts=10 ** 6, **kw):
        super().__init__(**kw)
        self.extra = {4: extra4 or {}, 6: extra6 or {}}
        self.lasts, self.table_reads = lasts, {4: 0, 6: 0}

    def exec(self, node, cmd, timeout=60, input=None):
        c = cmd[-1]
        if "route vrf all" in c:
            fam = 6 if "ipv6" in c else 4
            base = json.loads(super().exec(node, cmd, timeout, input).stdout)
            self.table_reads[fam] += 1
            if self.table_reads[fam] <= self.lasts:
                base["vrfs"]["default"]["routes"].update(self.extra[fam])
            return ExecResult(cmd, 0, json.dumps(base), "")
        return super().exec(node, cmd, timeout, input)


def test_a_kernel_default_while_ceos_starts_is_waited_out():
    slept = []
    lab = KernelLab(extra4={"0.0.0.0/0": _route("kernel", GW4)}, extra6={"::/0": _route("kernel", GW6)}, lasts=3)
    m = mgmt.prepare(lab, [], sleep=slept.append)["r1"]
    assert slept == [2.0, 2.0, 2.0]
    assert m.removed == ["ip route 0.0.0.0/0 172.31.99.1", "ipv6 route ::0/0 3fff:172:31:99::1"]


def test_a_kernel_default_that_stays_is_a_run_error_after_the_wait():
    slept = []
    lab = KernelLab(extra4={"0.0.0.0/0": _route("kernel", GW4)})
    with pytest.raises(ManagementPathError, match=r"0\.0\.0\.0/0 \(vrf default, kernel\) via 172\.31\.99\.1 Management0"):
        mgmt.prepare(lab, [], sleep=slept.append)
    assert sum(slept) == mgmt.EOS_KERNEL_WAIT and set(slept) == {2.0}


@pytest.mark.parametrize("extra", [
    {"0.0.0.0/0": _route("kernel", GW4), "10.77.0.0/16": _route("static", GW4)},   # another route as well
    {"0.0.0.0/0": _route("kernel", "172.31.99.77")},                                 # not via the gateway
    {"10.77.0.0/16": _route("kernel", GW4)},                                         # not a default
    {"0.0.0.0/0": _route("static", GW4)},                                            # a static with no config line
    {"0.0.0.0/0": {"routeType": "kernel", "vias": [{"nexthopAddr": GW4, "interface": "Management0"},
                                                    {"nexthopAddr": "10.0.0.1", "interface": "Ethernet1"}]}},
])
def test_anything_else_over_management_is_a_run_error_at_once(extra):
    slept = []
    lab = KernelLab(extra4=extra)
    with pytest.raises(ManagementPathError, match="has a route out over the management network"):
        mgmt.prepare(lab, [], sleep=slept.append)
    assert slept == []


def test_a_static_line_back_in_the_config_is_not_waited_out():
    slept = []
    lab = KernelLab(extra4={"0.0.0.0/0": _route("kernel", GW4)})
    lab.startup = "hostname e1\nip route 10.77.0.0/16 172.31.99.1\n"
    lab.running = lab.startup
    with pytest.raises(ManagementPathError, match="in its config"):
        mgmt.prepare(lab, [], sleep=slept.append)
    assert slept == []


def test_the_wait_reads_unreadable_output_as_a_run_error():
    class Garbled(KernelLab):
        def exec(self, node, cmd, timeout=60, input=None):
            if "route vrf all" in cmd[-1]:
                return ExecResult(cmd, 0, "% Invalid input", "")
            return super().exec(node, cmd, timeout, input)
    with pytest.raises(LabError, match="can't be read"):
        mgmt.prepare(Garbled(), [], sleep=lambda s: None)
