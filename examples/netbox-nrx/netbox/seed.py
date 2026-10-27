"""Load the demo network into an empty NetBox: four FRR routers in a ring.

Everything nrx needs comes from NetBox: devices with the "router" role and
the "frr" platform, cabled interfaces, IP addresses, an ASN per device
(local config context) and a config template that renders each router's
FRR config from that data. Rerunning the script is safe: it reuses objects
that already exist.

    export NB_API_URL=http://127.0.0.1:8000 NB_API_TOKEN=...
    python seed.py

Needs pynetbox (nrx installs it).
"""

import os
from pathlib import Path

import pynetbox

HERE = Path(__file__).parent

# name: (ASN, LAN prefix announced from lo)
ROUTERS = {
    "r1": (65001, "192.168.1.1/24"),
    "r2": (65002, "192.168.2.1/24"),
    "r3": (65003, "192.168.3.1/24"),
    "r4": (65004, "192.168.4.1/24"),
}

# (a-side, b-side), each "device:interface" with its address on the /30
CABLES = [
    (("r1", "eth1", "10.0.12.1/30"), ("r2", "eth1", "10.0.12.2/30")),
    (("r2", "eth2", "10.0.23.1/30"), ("r3", "eth1", "10.0.23.2/30")),
    (("r3", "eth2", "10.0.34.1/30"), ("r4", "eth1", "10.0.34.2/30")),
    (("r4", "eth2", "10.0.14.2/30"), ("r1", "eth2", "10.0.14.1/30")),
]


def get_or_create(endpoint, lookup, **extra):
    obj = endpoint.get(**lookup)
    return obj or endpoint.create(**lookup, **extra)


def main():
    nb = pynetbox.api(os.environ["NB_API_URL"], token=os.environ["NB_API_TOKEN"])

    template = (HERE / "frr.conf.j2").read_text()
    tmpl = nb.extras.config_templates.get(name="frr-bgp")
    if tmpl:
        tmpl.update({"template_code": template})
    else:
        tmpl = nb.extras.config_templates.create(name="frr-bgp", template_code=template)

    site = get_or_create(nb.dcim.sites, {"slug": "demo-dc1"}, name="demo-dc1", status="active")
    role = get_or_create(nb.dcim.device_roles, {"slug": "router"}, name="router", color="2196f3")
    maker = get_or_create(nb.dcim.manufacturers, {"slug": "frrouting"}, name="FRRouting")
    dtype = get_or_create(nb.dcim.device_types, {"slug": "frr-router"}, model="frr-router", manufacturer=maker.id)
    platform = get_or_create(nb.dcim.platforms, {"slug": "frr"}, name="FRR")
    platform.update({"config_template": tmpl.id})

    devices, interfaces = {}, {}
    for name, (asn, lan) in ROUTERS.items():
        dev = get_or_create(
            nb.dcim.devices, {"name": name, "site_id": site.id},
            site=site.id, role=role.id, device_type=dtype.id, platform=platform.id,
            status="active", local_context_data={"bgp": {"asn": asn}},
        )
        devices[name] = dev
        lo = get_or_create(nb.dcim.interfaces, {"device_id": dev.id, "name": "lo"}, device=dev.id, type="virtual")
        get_or_create(nb.ipam.ip_addresses, {"address": lan}, assigned_object_type="dcim.interface", assigned_object_id=lo.id)

    for a, b in CABLES:
        ends = []
        for dev_name, if_name, addr in (a, b):
            dev = devices[dev_name]
            iface = get_or_create(nb.dcim.interfaces, {"device_id": dev.id, "name": if_name}, device=dev.id, type="1000base-t")
            get_or_create(nb.ipam.ip_addresses, {"address": addr}, assigned_object_type="dcim.interface", assigned_object_id=iface.id)
            interfaces[(dev_name, if_name)] = iface
            ends.append(iface)
        if not ends[0].cable:
            nb.dcim.cables.create(
                a_terminations=[{"object_type": "dcim.interface", "object_id": ends[0].id}],
                b_terminations=[{"object_type": "dcim.interface", "object_id": ends[1].id}],
                status="connected",
            )

    print(f"NetBox seeded: site demo-dc1, {len(devices)} routers, {len(CABLES)} cables, config template frr-bgp")


if __name__ == "__main__":
    main()
