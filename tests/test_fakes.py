"""The shared fake-lab refusal (tests/fakes.py) and the rule that every fake lab uses it.

The release tooling recognises a new device read by the message "unexpected command: ..." on a fixture that no
longer holds. A fake that words its refusal differently turns a new read into an ordinary verdict change (still
blocked, but without asking for a live run on that network OS), so one wording is enforced here."""
from __future__ import annotations

import ast
import builtins
import json
import os
import re
import sys
from pathlib import Path
from unittest import mock

import pytest

from fakes import COMMAND_LOG, PREFIX, UnexpectedCommand, _plain, command_profiler, logging_commands, seen

TESTS = Path(__file__).resolve().parent
# a hand-made refusal in any spelling: AssertionError("unexpected command..."), f-strings, %-format, .format
OWN_REFUSAL = re.compile(r"""AssertionError\(\s*[fFrRbB]*["']unexpected command""")


def test_refusal_message_begins_with_the_shared_prefix():
    e = UnexpectedCommand("show bgp summary")
    assert isinstance(e, AssertionError)
    assert str(e) == "unexpected command: show bgp summary" and str(e).startswith(PREFIX)
    with pytest.raises(AssertionError, match=r"^unexpected command: show ip route$"):
        raise UnexpectedCommand("show ip route")


def test_no_test_raises_its_own_unexpected_command():
    """Oracle folders are frozen evidence written by oracle sessions; they are left as written."""
    own = []
    for p in sorted(TESTS.rglob("*.py")):
        rel = p.relative_to(TESTS).as_posix()
        if rel in ("fakes.py", "test_fakes.py") or rel.startswith("oracles/"):
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if OWN_REFUSAL.search(line):
                own.append(f"tests/{rel}:{n}: {line.strip()}")
    assert not own, "raise fakes.UnexpectedCommand(command) instead:\n" + "\n".join(own)


@pytest.mark.parametrize("line,hit", [
    ('raise AssertionError(f"unexpected command: {line}")', True),
    ('raise AssertionError(f"unexpected command {cmd!r}")', True),
    ("raise AssertionError('unexpected command %s' % c)", True),
    ('raise AssertionError( "unexpected command")', True),
    ("raise UnexpectedCommand(line)", False),
    ('raise AssertionError(f"unexpected output: {line}")', False),
])
def test_the_scan_sees_every_spelling(line, hit):
    assert bool(OWN_REFUSAL.search(line)) is hit


def test_seen_writes_nothing_unless_the_gate_asks(tmp_path, monkeypatch):
    log = tmp_path / "commands.jsonl"
    monkeypatch.delenv(COMMAND_LOG, raising=False)
    seen("show version")
    assert not log.exists()
    monkeypatch.setenv(COMMAND_LOG, str(log))
    seen("show bgp summary")
    seen(["vtysh", "-c", "show ip route"])
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [r["command"] for r in rows] == ["show bgp summary", '["vtysh", "-c", "show ip route"]']
    assert all(r["test"].endswith("test_seen_writes_nothing_unless_the_gate_asks") for r in rows)


class _AnswersAnything:
    """A fake that never calls seen(): only the profiler can tell what it was asked."""

    def exec(self, node, cmd, timeout=30):
        return "ok"


def _exec_(node, cmd):
    return "ok"


def _star(*a, **k):
    return "ok"


def _kw_only(node, *, cmd):
    return "ok"


# every way the tests bind a device fake (methods, lambdas, other names, *args, keyword-only, MagicMock,
# mock.patch, netns_exec): the hook logs at the boundary between the product and test code, not by name
SHAPES = {
    "method": lambda lab: lab,
    "instance-lambda": lambda lab: setattr(lab, "exec", lambda node, cmd, timeout=30: "ok") or lab,
    "instance-function": lambda lab: setattr(lab, "exec", _exec_) or lab,
    "netns_exec": lambda lab: setattr(lab, "netns_exec", _exec_) or lab,
    "star-args": lambda lab: setattr(lab, "exec", _star) or lab,
    "MagicMock": lambda lab: mock.MagicMock(),
}


def _product_caller(root: Path):
    """A function whose code lives under `root`, standing in for src/netdryrun calling a lab."""
    ns: dict = {}
    exec(compile("def call(target, attr, *a, **k):\n    return getattr(target, attr)(*a, **k)\n",
                 str(root / "caller.py"), "exec"), ns)
    return ns["call"]


def _logged(tmp_path, monkeypatch, run) -> list[dict]:
    log, root = tmp_path / "commands.jsonl", tmp_path / "src"
    monkeypatch.setenv(COMMAND_LOG, str(log))
    hook = command_profiler(code_root=str(root) + os.sep)
    old = sys.getprofile()
    sys.setprofile(hook)
    try:
        run(_product_caller(root))
    finally:
        sys.setprofile(old)
    return [json.loads(json.loads(x)["command"]) for x in log.read_text(encoding="utf-8").splitlines()] \
        if log.exists() else []


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_profiler_logs_every_shape_of_fake(tmp_path, monkeypatch, shape):
    attr = "netns_exec" if shape == "netns_exec" else "exec"
    rows = _logged(tmp_path, monkeypatch,
                   lambda call: call(SHAPES[shape](_AnswersAnything()), attr, "r1", ["vtysh", "-c", "show bgp x"]))
    assert any("show bgp x" in json.dumps(r) and "r1" in json.dumps(r) for r in rows), rows


def test_the_profiler_logs_keyword_only_and_patched_fakes(tmp_path, monkeypatch):
    def run(call):
        call(type("Lab", (), {"exec": staticmethod(_kw_only)})(), "exec", "r1", cmd="show kw")
        with mock.patch.object(_AnswersAnything, "exec", return_value="ok"):
            call(_AnswersAnything(), "exec", "r2", "show patched")
    text = json.dumps(_logged(tmp_path, monkeypatch, run))
    assert "show kw" in text and "show patched" in text, text


def test_the_profiler_logs_only_product_calls_into_test_code(tmp_path, monkeypatch):
    def run(call):
        _AnswersAnything().exec("r1", "from the test itself")       # not the product calling
        call(json, "dumps", ["not a fake"])                          # the product calling the library
    assert _logged(tmp_path, monkeypatch, run) == []


def test_logged_arguments_are_stable_between_runs():
    root = "/w/mixed"
    assert _plain(["/w/mixed/tests/x.yml", "/tmp/pytest-12/t0", object()], root) == \
        ["<root>/tests/x.yml", "/tmp/<tmp>/t0", "object"]


def test_the_hook_is_off_unless_the_gate_asks(tmp_path, monkeypatch):
    monkeypatch.delenv(COMMAND_LOG, raising=False)
    old = sys.getprofile()
    undo = logging_commands()
    assert sys.getprofile() is old
    undo()


def test_a_fake_called_from_a_product_thread_pool_is_logged(tmp_path, monkeypatch):
    """The product evaluates checks on a thread pool (checks._evaluate_all): a fake called from a worker thread is
    logged only because logging_commands also hooks new threads (threading.setprofile)."""
    log, root = tmp_path / "commands.jsonl", tmp_path / "src"
    monkeypatch.setenv(COMMAND_LOG, str(log))
    monkeypatch.setattr("fakes._package_root", lambda: str(root) + os.sep)
    ns: dict = {}
    exec(compile("import concurrent.futures\n"
                 "def _one(lab, node):\n    return lab.exec(node, ['show', 'bgp', node])\n"
                 "def evaluate_all(lab, nodes):\n"
                 "    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:\n"
                 "        return list(pool.map(lambda n: _one(lab, n), nodes))\n",
                 str(root / "checks.py"), "exec"), ns)
    old = sys.getprofile()
    undo = logging_commands()
    try:
        assert ns["evaluate_all"](_AnswersAnything(), ["r1", "r2"]) == ["ok", "ok"]
    finally:
        undo()
        sys.setprofile(old)
    rows = [json.loads(json.loads(x)["command"]) for x in log.read_text(encoding="utf-8").splitlines()] \
        if log.exists() else []
    assert sorted(r["args"]["node"] for r in rows if r["call"] == "exec") == ["r1", "r2"], rows


# ---- shapes the logger can't see, refused where the gate relies on it

# A fake the profiler can't log: a C function (dict.get, str.format, a builtin) runs without a Python frame;
# create_autospec, exec, eval and compile make code whose file is "<string>"; a stand-in imported from outside tests/
# is not test code; a fake executable answers in another process. None of them may stand in for a device in a
# must-not-pass fixture.
C_METHODS = {"get", "format", "format_map", "__getitem__", "__call__", "pop", "setdefault", "join", "split",
             "strip", "replace", "startswith", "endswith", "lower", "upper", "copy", "items", "keys", "values",
             "append", "extend", "update", "count", "index", "encode", "decode", "__contains__", "send", "write"}
BUILTIN_NAMES = set(dir(builtins))
CODE_MAKERS = {"exec", "eval", "compile", "FunctionType", "LambdaType", "create_autospec"}
CODE_ATTRS = {"FunctionType", "LambdaType", "create_autospec"}
TEST_MODULES = {"fakes", "conftest", "mock", "unittest", "pytest", "functools"}


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Call)):
        node = node.value if isinstance(node, ast.Attribute) else node.func
    return node.id if isinstance(node, ast.Name) else None


def unseen_fakes(source: str, where: str = "<fixture>") -> list[str]:
    """Each place in a fixture's source that binds a device stand-in the command logger can't see, or makes one."""
    tree = ast.parse(source)
    local = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    local |= {t.id for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))
              for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    local |= {a.arg for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
              for a in n.args.args + n.args.kwonlyargs + n.args.posonlyargs}
    foreign: dict[str, str] = {}      # a name bound by an import from outside tests/
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and not n.level and n.module and n.module.split(".")[0] not in TEST_MODULES \
                and not n.module.startswith(("tests", "test_", "fake")):
            foreign.update({a.asname or a.name: n.module for a in n.names})
        elif isinstance(n, ast.Import):
            foreign.update({(a.asname or a.name).split(".")[0]: a.name for a in n.names
                            if a.name.split(".")[0] not in TEST_MODULES and not a.name.startswith(("test_", "fake"))})
    out: list[str] = []

    def say(node: ast.AST, what: str) -> None:
        out.append(f"{where}:{node.lineno}: {what}: {ast.unparse(node)[:80]}")

    def judge(value: ast.AST, target: str | None = None) -> None:
        """A value bound in place of a device method or lab (`target`: the name it is bound to, when known)."""
        if isinstance(value, ast.Attribute) and value.attr == target and \
                foreign.get(_root_name(value) or "", "").startswith("netdryrun"):
            return      # the product's own method put back (vrfs = Driver.vrfs): real code, not a stand-in
        if isinstance(value, ast.Call) and _root_name(value.func) in ("partial", "functools") and value.args:
            judge(value.args[0])
        elif isinstance(value, ast.Attribute) and value.attr in C_METHODS:
            say(value, "a C method answers without a Python frame")
        elif isinstance(value, ast.Name) and value.id in BUILTIN_NAMES and value.id not in local:
            say(value, "a builtin answers without a Python frame")
        elif isinstance(value, ast.Name) and value.id in foreign and value.id not in local:
            say(value, f"a stand-in imported from {foreign[value.id]}, outside tests/")
        elif isinstance(value, ast.Attribute) and _root_name(value) in foreign and _root_name(value) not in local:
            say(value, f"a stand-in from {foreign[_root_name(value)]}, outside tests/")

    for n in ast.walk(tree):
        name = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
        if isinstance(n, ast.Name) and name in CODE_MAKERS or isinstance(n, ast.Attribute) and name in CODE_ATTRS:
            say(n, "makes code whose file is <string>")
        if isinstance(n, ast.Call):
            fn = n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id if isinstance(n.func, ast.Name) else ""
            mode = n.args[-1] if n.args else None
            if fn == "chmod" and not (isinstance(mode, ast.Constant) and isinstance(mode.value, int)
                                      and not mode.value & 0o111) or (fn in ("setenv", "setitem") and any(
                    isinstance(a, ast.Constant) and a.value == "PATH" for a in n.args)):
                say(n, "a fake executable answers in another process")
            if fn in ("staticmethod", "classmethod") and n.args:
                judge(n.args[0])
            if fn in ("setattr", "object") and len(n.args) >= 3:
                judge(n.args[2])
            if fn == "patch" and len(n.args) >= 2:
                judge(n.args[1])
            if fn == "type" and len(n.args) == 3 and isinstance(n.args[2], ast.Dict):
                for v in n.args[2].values:
                    judge(v)
            for k in n.keywords:
                if k.arg == "new" or (fn in ("SimpleNamespace", "Namespace") and k.arg):
                    judge(k.value)
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) for t in n.targets):
            judge(n.value)
        if isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store) and isinstance(n.slice, ast.Constant) \
                and n.slice.value == "PATH":
            say(n, "a fake executable answers in another process")
        if isinstance(n, ast.ClassDef):
            for b in n.body:
                if isinstance(b, ast.Assign):
                    judge(b.value, b.targets[0].id if isinstance(b.targets[0], ast.Name) else None)
    return out


def _fixture_files() -> list[Path]:
    """The must-not-pass fixtures the gate runs with the command log (scripts/fastfix_gate.py fixture_targets), and
    every module under tests/ they import."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fastfix_gate_for_fakes", TESTS.parent / "scripts" / "fastfix_gate.py")
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)
    todo = [TESTS / "conftest.py"]
    for t in gate.fixture_targets(TESTS.parent):
        p = TESTS.parent / t.split("::")[0]
        todo += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    done: set[Path] = set()
    while todo:
        p = todo.pop()
        if p in done or not p.is_file():
            continue
        done.add(p)
        for m in re.findall(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", p.read_text(encoding="utf-8"), re.M):
            todo.append(TESTS / f"{m}.py")
    return sorted(done)


# shapes in fixtures that stand in for no device: (file, the refused code) -> why. An entry the scan no longer finds
# fails, so the list can't outlive what it describes.
NOT_A_DEVICE = {
    ("tests/test_acceptance_041.py", "(bin_ / 'sudo').chmod(493)"):
        "a sudo that runs its own arguments, for the Action's shell steps; it answers no device command",
    ("tests/test_runner_robustness.py", "monkeypatch.setenv('PATH', str(tmp_path))"):
        "empties PATH so validate can find no containerlab or docker; it writes no executable",
    ("tests/test_surfaces_agree.py", "eval"):
        "evaluates the Action's if: expression (literals and operators only); it makes no fake",
}


def test_no_fixture_uses_a_fake_the_command_log_cant_see():
    found, used = [], set()
    for p in _fixture_files():
        rel = p.relative_to(TESTS.parent).as_posix()
        for hit in unseen_fakes(p.read_text(encoding="utf-8"), rel):
            key = (rel, hit.split(": ", 2)[-1])
            if key in NOT_A_DEVICE:
                used.add(key)
            else:
                found.append(hit)
    stale = sorted(set(NOT_A_DEVICE) - used)
    assert not stale, f"NOT_A_DEVICE entries the scan no longer finds: {stale}"
    assert not found, ("a must-not-pass fixture answers device commands where tests/fakes.py can't log them; write the "
                       "fake as a Python function, lambda or class under tests/, or a MagicMock:\n" + "\n".join(found))


@pytest.mark.parametrize("src,hit", [
    ("lab.exec = CANNED.get", "C method"),
    ("L = type('L', (), {'exec': staticmethod('{}-ok'.format)})", "C method"),
    ("monkeypatch.setattr(lab, 'exec', repr)", "builtin"),
    ("m = mock.create_autospec(fn, return_value='ok')", "<string>"),
    ("ns = {}\nexec('def f(n, c):\\n    return 1', ns)", "<string>"),
    ("from netdryrun.lab import Lab\nlab.exec = Lab.exec", "outside tests/"),
    ("from elsewhere import outside_fake\nmonkeypatch.setattr(lab, 'exec', outside_fake)", "outside tests/"),
    ("import os\nlab.exec = os.getcwd", "outside tests/"),
    ("lab.exec = functools.partial(CANNED.get, 'x')", "C method"),
    ("os.chmod(tool, 0o755)", "another process"),
    ("monkeypatch.setenv('PATH', str(tmp_path))", "another process"),
    ("os.environ['PATH'] = str(bin_dir)", "another process"),
    ("class Lab:\n    exec = CANNED.get", "C method"),
    ("with mock.patch.object(Lab, 'exec', new=CANNED.get):\n    pass", "C method"),
])
def test_the_scan_refuses_each_shape_the_logger_misses(src, hit):
    found = unseen_fakes(src)
    assert found and hit in found[0], found


@pytest.mark.parametrize("src", [
    "lab.exec = lambda node, cmd, timeout=30: 'ok'",
    "def fake(node, cmd):\n    return 'ok'\nmonkeypatch.setattr(lab, 'exec', fake)",
    "lab.exec = mock.MagicMock(side_effect=CANNED.get)",
    "from fakes import UnexpectedCommand\nlab.exec = Fake().exec",
    "lab.exec = functools.partial(fake, 'r1')",
    "drv.exec_root = drv.exec",
    "out = sorted(rows, key=CANNED.get)",
])
def test_the_scan_leaves_fakes_the_logger_sees(src):
    assert unseen_fakes(src) == []


def test_no_product_code_hands_a_lab_call_to_a_pool_or_callback():
    """pool.map(lab.exec) calls the fake from a stdlib frame, which the logger doesn't count as the product: the
    product calls a lab method itself (inside a lambda or function of its own), never passes it on bound."""
    found = []
    for p in sorted((TESTS.parent / "src" / "netdryrun").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        found += [f"{p.relative_to(TESTS.parent).as_posix()}:{n.lineno}: {ast.unparse(n)}" for n in ast.walk(tree)
                  if isinstance(n, ast.Attribute) and n.attr in ("exec", "exec_root", "netns_exec")
                  and id(n) not in called and isinstance(n.ctx, ast.Load)]
    assert not found, "\n".join(found)
