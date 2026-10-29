"""The published compatibility matrix is generated, not typed: it must match the driver tests, and the capture
script must cover every driver on main."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import compat_matrix  # noqa: E402

from netdryrun.drivers import DRIVERS  # noqa: E402


def test_page_matches_the_tests():
    assert compat_matrix.PAGE.read_text(encoding="utf-8") == compat_matrix.render(), \
        "website/docs/reference/compatibility.md is out of date: run python scripts/compat_matrix.py"


def test_every_driver_has_an_image_a_date_and_a_capture_script_entry():
    verified = json.loads(compat_matrix.VERIFIED.read_text(encoding="utf-8"))
    script = (ROOT / "scripts" / "capture_fixtures.sh").read_text(encoding="utf-8")
    for name in DRIVERS:
        assert name in compat_matrix.EXAMPLES and name in verified
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", verified[name]["date"])
        assert ":" in compat_matrix._image(name)
        assert f"capture_{name}()" in script, f"scripts/capture_fixtures.sh has no capture_{name}()"


def test_the_page_never_calls_an_untested_cell_verified():
    page = compat_matrix.render()
    assert "no control" not in page
    for line in page.splitlines():
        if "no must-fail test" in line:
            assert "verified" not in line.split("no must-fail test")[0].split("|")[-1]


def test_pinned_sonic_build_is_the_one_the_page_names():
    topo = (ROOT / "examples" / "sonic-frr" / "topology.clab.yml").read_text(encoding="utf-8")
    assert re.search(r"image: docker-sonic-vs:master\.\d+-[0-9a-f]+\s", topo)
    assert re.search(r"docker-sonic-vs:master\.\d+-[0-9a-f]+", compat_matrix.render())


@pytest.mark.skipif(sys.platform == "win32", reason="bash syntax check on the Linux side")
def test_capture_script_parses_and_refuses_an_unknown_driver():
    script = str(ROOT / "scripts" / "capture_fixtures.sh")
    assert subprocess.run(["bash", "-n", script]).returncode == 0
    r = subprocess.run(["bash", script, "nosuchdriver"], capture_output=True, text=True)
    assert r.returncode == 2 and "usage" in r.stderr
