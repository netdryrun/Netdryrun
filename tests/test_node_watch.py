"""The node watch (end-user F3): how often it asks Docker, and that run() puts the plain sleep back. These pin the five
mutants 0.4.1 accepted as test gaps that fail closed (runner.run 268, _NodeWatch.__call__ 1, 4, 5, 6) and the
check interval (_NodeWatch.__init__ 1)."""
from test_runner_robustness import ALWAYS, FakeDriver, FakeLab, World, cfg, install

from netdryrun import runner


class CountingLab:
    def __init__(self):
        self.looks = []

    def stopped_containers(self):
        self.looks.append(runner._clock())
        return {}


def waits_at(monkeypatch, times, every=None):
    clock = iter(times)
    now = {"t": 0.0}

    def tick():
        return now["t"]

    monkeypatch.setattr(runner, "_clock", tick)
    lab = CountingLab()
    watch = runner._NodeWatch(lab, lambda s: None) if every is None else runner._NodeWatch(lab, lambda s: None, every)
    for t in clock:
        now["t"] = t
        watch(1.0)
    return lab.looks


def test_the_containers_are_looked_at_once_every_interval(monkeypatch):
    assert waits_at(monkeypatch, [0, 10, 15, 29, 30, 44], every=15) == [0, 15, 30]


def test_the_default_interval_is_15_seconds(monkeypatch):
    assert waits_at(monkeypatch, [0, 14.9, 15]) == [0, 15]


def test_run_twice_in_one_process(tmp_path, monkeypatch):
    w = World()
    install(monkeypatch, w, FakeLab(w), {n: FakeDriver(w) for n in ("r1", "r2", "r3")})
    for _ in range(2):
        rep = runner.run(cfg(tmp_path, [ALWAYS]), deploy=False)
        assert rep.status == "passed", rep.error
        assert runner._sleep == w.sleep   # the plain sleep is back, not the watch or None
