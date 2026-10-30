"""Build a runnable copy of an interop lab: the baseline or one overlay applied to it.

    python interop/tools/build.py L1 base OUTDIR
    python interop/tools/build.py L1 M01 OUTDIR
    python interop/tools/build.py L1s8 S8a OUTDIR

Writes OUTDIR/{topology.clab.yml, netdryrun.yml, check.yml, configs/...}. netdryrun.yml is the fresh-deploy file
(timeout 1200 for the labs with Junos); check.yml is the same checks with timeout 120, for `netdryrun check` on a
lab that is already up. Each overlay edit must match exactly once, or the build fails. Every file is written with
Unix line ends, whatever the checkout has.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]   # interop/
LABS = {"L1": ("L1/base", None, "L1/overlays.yml"),
        "L1s8": ("L1/base", "L1/s8", "L1/s8/overlays.yml"),
        "L2": ("L2/base", None, "L2/overlays.yml")}
CRLF, LF = b"\r\n", b"\n"


def _read(p: Path) -> str:
    return p.read_bytes().replace(CRLF, LF).decode("utf-8")


def _write(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8").replace(CRLF, LF))


def overlays(lab: str) -> dict:
    return yaml.safe_load(_read(HERE / LABS[lab][2]))["overlays"]


def build(lab: str, variant: str, out: Path) -> Path:
    base, extra, _ = LABS[lab]
    # containerlab keeps a running lab's state in clab-<name>/ next to the topology (cEOS flash among it): never
    # touch it. Everything else in OUTDIR is rebuilt.
    out.mkdir(parents=True, exist_ok=True)
    for f in out.iterdir():
        if f.name.startswith("clab-"):
            continue
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    shutil.copytree(HERE / base, out, dirs_exist_ok=True)
    if extra:
        for f in (HERE / extra).iterdir():
            if f.name != "overlays.yml":
                shutil.copy(f, out / f.name)
    for f in out.rglob("*"):
        if f.is_file():
            _write(f, _read(f))
    if variant != "base":
        ov = overlays(lab)[variant]
        for e in ov.get("edits", []):
            target = out / e["file"]
            text = _read(target)
            if "replace" in e:
                n = text.count(e["replace"])
                if n != 1:
                    raise SystemExit(f"{lab}/{variant}: edit for {e['file']} matches {n} times, not once")
                text = text.replace(e["replace"], e["with"])
            elif "append" in e:
                text = text + ("" if text.endswith("\n") else "\n") + e["append"]
            elif "from_file" in e:
                text = _read(HERE / Path(LABS[lab][2]).parent / e["from_file"])
            else:
                raise SystemExit(f"{lab}/{variant}: unknown edit {e}")
            _write(target, text)
    nd = _read(out / "netdryrun.yml")
    _write(out / "check.yml", re.sub(r"^timeout: \d+.*$", "timeout: 120", nd, count=1, flags=re.M))
    return out


if __name__ == "__main__":
    print(build(sys.argv[1], sys.argv[2], Path(sys.argv[3])))
