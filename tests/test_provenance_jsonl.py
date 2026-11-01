"""scripts/provenance_jsonl.py: the release's SLSA provenance as *.intoto.jsonl, only when it describes the release."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "provenance_jsonl.py"


def bundle(subjects: dict[str, str], predicate="https://slsa.dev/provenance/v1", payload_type="application/vnd.in-toto+json"):
    statement = {"_type": "https://in-toto.io/Statement/v1", "predicateType": predicate,
                 "subject": [{"name": n, "digest": {"sha256": d}} for n, d in subjects.items()], "predicate": {}}
    return {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json", "verificationMaterial": {"certificate": {}},
            "dsseEnvelope": {"payload": base64.b64encode(json.dumps(statement).encode()).decode(),
                             "payloadType": payload_type, "signatures": [{"sig": "c2ln"}]}}


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    d.mkdir()
    (d / "netdryrun-0.4.1-py3-none-any.whl").write_bytes(b"wheel")
    (d / "netdryrun-0.4.1.tar.gz").write_bytes(b"sdist")
    return d


def run(tmp_path, b, files):
    (tmp_path / "b.json").write_text(json.dumps(b))
    out = tmp_path / "netdryrun-v0.4.1.intoto.jsonl"
    p = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "b.json"), str(out), *map(str, files)],
                       capture_output=True, text=True)
    return p, out


def digests(dist):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dist.iterdir())}


def test_the_envelope_is_written_unchanged_as_one_json_line(tmp_path, dist):
    b = bundle(digests(dist))
    p, out = run(tmp_path, b, sorted(dist.iterdir()))
    assert p.returncode == 0, p.stderr
    lines = out.read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0]) == b["dsseEnvelope"]


@pytest.mark.parametrize("change,why", [
    (lambda d: {**d, "netdryrun-0.4.1.tar.gz": "0" * 64}, "sha256 differs"),
    (lambda d: {k: v for k, v in d.items() if k.endswith(".whl")}, "the provenance covers"),
    (lambda d: {**d, "extra.whl": "1" * 64}, "the provenance covers"),
])
def test_provenance_that_does_not_describe_the_release_is_refused(tmp_path, dist, change, why):
    p, out = run(tmp_path, bundle(change(digests(dist))), sorted(dist.iterdir()))
    assert p.returncode == 1 and why in p.stderr and not out.exists()


def test_only_signed_slsa_provenance_is_accepted(tmp_path, dist):
    p, _ = run(tmp_path, bundle(digests(dist), predicate="https://spdx.dev/Document"), sorted(dist.iterdir()))
    assert p.returncode == 1 and "not SLSA provenance" in p.stderr
    unsigned = bundle(digests(dist))
    unsigned["dsseEnvelope"]["signatures"] = []
    p, _ = run(tmp_path, unsigned, sorted(dist.iterdir()))
    assert p.returncode == 1 and "no signed in-toto DSSE envelope" in p.stderr
