"""False passes found by the 0.4.1 release gate's Layer 5b acceptance run (adversary angle), kept failing until fixed.
Each test reproduces one on fake state, with no lab; the red-team corpus lists them (tests/redteam)."""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from netdryrun.verify.engine import match
from netdryrun.verify.intent import parse_intent_text
from netdryrun.verify.snapshot import (AsPath, BgpAttrs, BgpPath, ItemKey, NextHop, NodeSnapshot, PathNextHop,
                                       RibEntry, Session, Snapshot)
from test_action_verify import git, merged, python_of

ROOT = Path(__file__).parents[1]
FENCE = "`" * 3
P = "10.101.0.0/24"


def _attrs(as_path, nh):
    return BgpAttrs(origin="igp", as_path=AsPath.parse(as_path),
                    next_hops=(PathNextHop(nh, "global", True, True, 0, "eth1"),), local_pref=None, med=None,
                    weight=0, communities=(), ext_communities=(), large_communities=(), cluster_list=(),
                    originator_id=None, atomic_aggregate=False, aggregator=None)


def _rib(nh):
    hop = NextHop(nh, "eth1", None, True, True, True, False, False, False, "gateway", 1, (), None)
    return (RibEntry("bgp", None, True, True, 20, 0, None, 254, False, (hop,)),)


def _session(local):
    return Session(state="established", remote_as=65101, local_as=65000, afis=("ipv4-unicast",), local_address=local)


def test_with_from_pin_does_not_explain_a_path_from_an_undeclared_peer():
    """RT-0035. The intent approves the customer's block on edge1 learned *from the customer* (10.0.1.2, AS path
    65101). The change also opened the transit peer's inbound filter, so edge1 now holds a second path for the
    same prefix from 10.0.9.2 with a hijacker's origin AS 65666: not best today, best as soon as the customer
    session drops. The pin must explain only the path that matches it; 0.4.1 b61c325 explains both and says
    INTENT MATCHED."""
    base = {ItemKey("session", "edge1", "default", neighbor="10.0.1.2"): _session("10.0.1.1"),
            ItemKey("session", "edge1", "default", neighbor="10.0.9.2"): _session("10.0.9.1")}
    before = Snapshot({"edge1": NodeSnapshot("edge1", "frr", ("default",), dict(base), config=("router bgp 65000",))})
    after_items = dict(base)
    k = dict(kind="path", node="edge1", vrf="default", afi="ipv4", safi="unicast", prefix=P)
    after_items[ItemKey(**k, neighbor="10.0.1.2")] = BgpPath(_attrs("65101", "10.0.1.2"), True, False, True,
                                                             "external", "10.0.0.11")
    after_items[ItemKey(**k, neighbor="10.0.9.2")] = BgpPath(_attrs("65020 65666", "10.0.9.2"), False, False, True,
                                                             "external", "10.0.0.20")
    after_items[ItemKey("rib", "edge1", "default", "ipv4", "unicast", P, protocol="bgp")] = _rib("10.0.1.2")
    after = Snapshot({"edge1": NodeSnapshot("edge1", "frr", ("default",), after_items,
                                            config=("router bgp 65000", " neighbor 10.0.9.2 route-map ANY in"))})
    intent = parse_intent_text(f"""
intent:
  - prefix: {P}
    appears_on: [edge1]
    with: {{from: 10.0.1.2, as_path: "65101"}}
""")
    m = match(before, after, intent)
    assert m.status != "matched", "a path from an undeclared peer was explained by a pinned line"
    assert any(d.key.neighbor == "10.0.9.2" for d in m.undeclared)


# --- angle 3 (system integrator): documented CI templates -------------------------------------------------------



def test_every_yaml_block_in_the_docs_parses():
    """T-B2. A user copies these into a workflow or a config file: each one must at least be YAML. 0.4.1 b61c325's
    "Use the outputs in a later step" (github-action.md) has an unquoted `run: echo "... $NDR_STATUS: ..."`,
    which GitHub refuses to load."""
    block = re.compile(FENCE + r"ya?ml[^\n]*\n(.*?)" + FENCE, re.DOTALL)
    bad = []
    for md in [ROOT / "README.md", *sorted((ROOT / "website" / "docs").rglob("*.md"))]:
        text = md.read_text(encoding="utf-8")
        for m in block.finditer(text):
            body = re.sub(r"^ {0,4}(?=\S)", "", m.group(1), flags=re.MULTILINE) if m.group(1).startswith("    ") else m.group(1)
            try:
                yaml.safe_load(body)
            except yaml.YAMLError as e:
                line = text[:m.start()].count("\n") + 1
                bad.append(f"{md.relative_to(ROOT)}:{line}: {str(e).splitlines()[0]}")
    assert not bad, "\n".join(bad)


def test_the_check_step_works_after_a_shallow_checkout(tmp_path):
    """T-B1. actions/checkout fetches only github.sha (the merge commit) at depth 1, which every documented workflow
    uses. The merge commit is then present but has no parents in the clone, so "Check the checks file" refused
    every pull request ("github.sha is not this pull request's merge commit"): the product's own CI on pull
    requests has failed this way since 31 Oct (v0.4.0 has the same step). A PR that changes only a config must
    pass this step with the default checkout."""
    origin = tmp_path / "origin"
    (origin / "lab" / "configs").mkdir(parents=True)
    git(origin, "init", "-q")
    (origin / "lab" / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks: []\n")
    (origin / "lab" / "topology.clab.yml").write_text("name: t\n")
    (origin / "lab" / "configs" / "r1.conf").write_text("! r1\n")
    git(origin, "add", ".")
    git(origin, "commit", "-q", "-m", "base")
    base = git(origin, "rev-parse", "HEAD").strip()
    (origin / "lab" / "configs" / "r1.conf").write_text("! r1 changed\n")
    git(origin, "commit", "-q", "-am", "change")
    head = git(origin, "rev-parse", "HEAD").strip()
    merge = merged(origin, base, head)
    git(origin, "update-ref", "refs/pull/1/merge", merge)
    # what actions/checkout does on pull_request with its default fetch-depth: 1
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q")
    git(work, "remote", "add", "origin", origin.as_uri())
    git(work, "fetch", "-q", "--no-tags", "--depth=1", "origin", "+refs/pull/1/merge:refs/remotes/pull/1/merge")
    git(work, "checkout", "-q", "--detach", merge)
    out = work / "gh-output.txt"
    env = {**os.environ, "NDR_PATH": "lab", "NDR_BASE": base, "NDR_HEAD": head, "NDR_MERGE": merge,
           "NDR_ALLOW_CHECK_EDIT": "false", "GITHUB_OUTPUT": str(out)}
    p = subprocess.run([sys.executable, "-c", python_of("Check the checks file")], cwd=work, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
