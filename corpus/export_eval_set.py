"""Export both corpora (v1 and v2) as one JSON file: the eval set.

  python corpus/export_eval_set.py          (writes corpus/eval-set.json)

The file is self-contained: each corpus's base lab (topology and configs) plus every case with
its pre-registered label and its edits. It carries labels and edits only, not Netdryrun's verdicts
(those are in results/ and RESULTS.md). Output is deterministic, so a diff shows real changes.
"""
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CORPORA = {"v1": HERE, "v2": HERE / "v2"}
OUT = HERE / "eval-set.json"
KEEP = ("id", "title", "category", "expected", "rationale", "note", "edits")


def base(root):
    b = root / "base"
    files = {"topology.clab.yml": (b / "topology.clab.yml").read_text(encoding="utf-8").replace("\r\n", "\n")}
    for f in sorted((b / "configs").iterdir()):
        files[f"configs/{f.name}"] = f.read_text(encoding="utf-8").replace("\r\n", "\n")
    return files


def main():
    corpora = {}
    for name, root in CORPORA.items():
        cases = []
        for p in sorted((root / "cases").glob("*.yml")):
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
            cases.append({k: d[k] for k in KEEP if k in d})
        corpora[name] = {"intent": str((root / "INTENT.md").relative_to(HERE.parent)).replace("\\", "/"),
                         "base": base(root), "cases": cases}
    total = sum(len(c["cases"]) for c in corpora.values())
    doc = {
        "name": "netdryrun-network-change-verdict-corpus",
        "cases": total,
        "license": "Apache-2.0",
        "source": "https://github.com/netdryrun/netdryrun/tree/main/corpus",
        "how_to_use": ("For each case, copy the base lab, apply the case's edits (replace the text in the "
                       "named node's config, or append a line), then decide whether the change is safe. "
                       "'expected' is the label."),
        "how_labels_were_decided": ("Written before any run, by one maintainer's judgment: would an experienced "
                                    "operator reject this change in review because it causes harm? Not derived "
                                    "from the checks. Labels are the maintainer's, not independent ground truth."),
        "edit_format": {"node": "router whose configs/<node>.conf is edited",
                        "replace/with": "exact text to find and its replacement",
                        "append": "a line added at the end of the config"},
        "amendments": "corpus/AMENDMENTS.md and corpus/v2/AMENDMENTS.md list every label or case change made after a run.",
        "labels": {"safe": "the change should be applied", "unsafe": "the change should be rejected"},
        "corpora": corpora,
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({total} cases)")


if __name__ == "__main__":
    sys.exit(main())
