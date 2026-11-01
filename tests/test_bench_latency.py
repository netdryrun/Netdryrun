"""The latency benchmark (bench/latency/bench.py): its changes still apply to the examples, and its percentiles."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("bench_latency", ROOT / "bench" / "latency" / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.mark.parametrize("lab,change", [(lab, ch) for lab, chs in bench.CHANGES.items() for ch in chs])
def test_every_change_applies_to_its_example(tmp_path, lab, change):
    d = tmp_path / lab
    shutil.copytree(ROOT / "examples" / lab, d)
    before = {p.relative_to(d): p.read_bytes() for p in d.rglob("*") if p.is_file()}
    bench.CHANGES[lab][change](d)
    after = {p.relative_to(d): p.read_bytes() for p in d.rglob("*") if p.is_file()}
    assert (before == after) == (change == "good")


def test_nearest_rank_percentiles():
    vals = [float(v) for v in range(1, 21)]
    assert bench.pct(vals, .5) == 10 and bench.pct(vals, .95) == 19 and bench.pct([3.0], .95) == 3
    assert bench.pct([], .5) is None and bench.pct([None, 2.0], .5) == 2


def test_report_flags_a_status_that_differs_between_labels(tmp_path, capsys):
    def row(label, status, wall):
        return {"label": label, "lab": "frr-bgp", "change": "good", "trial": 0, "wall_s": wall, "status": status,
                "timings": {"deploy": 5.0, "converge": 20.0}}
    f = tmp_path / "r.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in (row("before", "passed", 60), row("after", "passed", 50))) + "\n")
    assert bench.main(["report", str(f)]) == 0
    assert "| after | frr-bgp | good | 1 | passed 1 | 50 | 50 | 50 | 5/5 |" in capsys.readouterr().out
    f.write_text(f.read_text() + json.dumps(row("after", "failed", 40)) + "\n")
    assert bench.main(["report", str(f)]) == 1
    assert "frr-bgp good: DIFFERENT" in capsys.readouterr().out
