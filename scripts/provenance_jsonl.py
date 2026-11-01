"""Write a release's SLSA build provenance as an in-toto JSON Lines file (`*.intoto.jsonl`).

  python scripts/provenance_jsonl.py BUNDLE OUT DIST_FILE...

BUNDLE is the Sigstore bundle actions/attest-build-provenance writes in the release workflow. It holds one signed
DSSE envelope whose in-toto statement is SLSA provenance for the artifacts. OUT gets that envelope, unchanged, as one
JSON line: the format slsa-github-generator attaches to releases and OpenSSF Scorecard's Signed-Releases check counts.
Nothing is re-signed or rewritten; the bundle (with the certificate that verifies the signature) is attached next to it
as `*.sigstore.json`.

It refuses (exit 1) unless the statement is SLSA provenance and its subjects are exactly the DIST_FILEs, by sha256:
provenance that doesn't describe the files being released is worse than none.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

IN_TOTO_PAYLOAD = "application/vnd.in-toto+json"


def envelope(bundle: dict, dist: list[Path]) -> dict:
    env = bundle.get("dsseEnvelope")
    if not isinstance(env, dict) or env.get("payloadType") != IN_TOTO_PAYLOAD or not env.get("signatures"):
        raise ValueError("the bundle has no signed in-toto DSSE envelope")
    statement = json.loads(base64.b64decode(env["payload"]))
    predicate = statement.get("predicateType", "")
    if not predicate.startswith("https://slsa.dev/provenance/"):
        raise ValueError(f"the statement is {predicate or 'untyped'}, not SLSA provenance")
    subjects = {s.get("name"): (s.get("digest") or {}).get("sha256") for s in statement.get("subject") or []}
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dist}
    if subjects != files:
        raise ValueError(f"the provenance covers {sorted(subjects)}, the release has {sorted(files)} "
                         "(or a sha256 differs)")
    return env


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    bundle, out, dist = Path(argv[0]), Path(argv[1]), [Path(a) for a in argv[2:]]
    try:
        env = envelope(json.loads(bundle.read_text(encoding="utf-8")), dist)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"provenance: {e}", file=sys.stderr)
        return 1
    out.write_text(json.dumps(env, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"provenance: wrote {out} for {', '.join(p.name for p in dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
