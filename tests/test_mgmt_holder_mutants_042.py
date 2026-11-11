"""mgmt.own_holder, one behavior per test (0.4.2 mutation layer on be62293: 14 survivors). The identity check decides
whether a container's Docker networks count as an SR Linux node's management networks, and so whether a ping over
them is refused: a holder that isn't this node's, or that doesn't hold its own namespace, must never count."""
from netdryrun import mgmt
from netdryrun.lab import LabError

LAB = "L"
ID = "abc123def4567890abcdef"
NAME = "clab-L-srl1-netns"


def holder(**over):
    d = {"Id": ID, "Name": "/" + NAME,
         "Config": {"Labels": {"containerlab": LAB, "clab-internal-node": "true", "clab-root-node-name": "srl1"}},
         "HostConfig": {"NetworkMode": "clab"},
         "NetworkSettings": {"Networks": {"clab": {"IPAddress": "172.20.20.2", "IPPrefixLen": 24,
                                                  "Gateway": "172.20.20.1"}}}}
    for k, v in over.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    return d


class FakeLab:
    name = LAB

    def __init__(self, data):
        self.data, self.asked = data, []

    def docker_inspect_container(self, ref):
        self.asked.append(ref)
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def own(data, ref):
    m = mgmt.Mgmt("srl1", "container:" + ref)
    m.cid = "nodecid"
    return mgmt.own_holder(FakeLab(data), "srl1", m)


def test_found_by_its_name_when_the_id_doesnt_match():
    h = own(holder(), NAME)
    assert h is not None and h.holder == NAME and h.node == "srl1" and h.cid == "nodecid"
    assert [str(s) for s in h.subnets] == ["172.20.20.0/24"]


def test_a_reference_with_docker_s_leading_slash_matches_the_name():
    assert own(holder(), "/" + NAME) is not None


def test_a_name_that_starts_with_x_matches_as_written():
    assert own(holder(Name="/Xh"), "Xh") is not None


def test_found_by_its_id_prefix():
    assert own(holder(Name="/somethingelse"), ID[:12]) is not None


def test_neither_the_id_nor_the_name_matches_the_reference():
    assert own(holder(Name="/other"), "clab-L-srl1-other") is None


def test_an_inspect_without_id_or_name_never_matches():
    assert own(holder(Id=None, Name=None), "X") is None
    assert own(holder(Id=None, Name=None), "XXXX") is None
    assert own(holder(Name=None), "XXXX") is None


def test_labels_under_a_config_that_isnt_an_object_dont_count():
    assert own(holder(Config="not an object"), NAME) is None


def test_a_holder_without_its_own_namespace_never_counts():
    for mode in ("host", "none", "", "container:" + ID):
        assert own(holder(HostConfig={"NetworkMode": mode}), NAME) is None, mode


def test_a_holder_named_by_id_only_is_shown_by_the_short_id():
    h = own(holder(Name=None), ID[:12])
    assert h is not None and h.holder == ID[:12]


def test_an_inspect_error_is_no_holder():
    m = mgmt.Mgmt("srl1", "container:" + NAME)
    assert mgmt.own_holder(FakeLab(LabError("gone")), "srl1", m) is None
