"""What every hand-written fake lab in the tests shares.

A fake lab answers the commands a test expects and refuses the rest with `UnexpectedCommand`, whose message always
begins "unexpected command: ". The release tooling (scripts/fastfix_gate.py) reads that prefix: when code under test
sends a fake a command it was never given, the change reads something new from the device, and the gate asks for a
live run on that network OS instead of treating the failure as an ordinary verdict change. A fake that raised its own
wording would hide that, so tests/test_fakes.py refuses any other `unexpected command` raise under tests/.

`seen(command)` records each command a fake was sent, one JSON line per command, in the file named by
NDR_FAKE_COMMAND_LOG when the gate sets it (and nowhere otherwise). Comparing two runs of the same test on two
versions of the code shows a command only the newer one sends, even when a fake that matches by substring answered
it without complaint.

Not every fake calls `seen`, so tests/conftest.py also installs `command_profiler()` while the log is on, on the test's
thread and on every thread started after it (the product evaluates checks on a thread pool). It logs at the boundary,
not by name.

Logged: every call whose caller is a Python function in a file under src/netdryrun and whose callee is a Python
function in a file under tests/ or in unittest/mock.py: a fake class's method, a lambda or function bound in its place
under any name (exec, exec_root, netns_exec or anything a later driver uses), *args or keyword-only alike, functools.
partial around such a function, a MagicMock or mock.patch stand-in, and a callback a test hands in (a fake clock, say;
a change to what the code passes it then shows as new, which only ever asks for more review). Arguments are logged as
plain data, other objects by their type, the test's working directory as <root>, and dict keys sorted.

Only temporary paths the run itself created are replaced, each only as a whole path name and with the rest of the path
kept. tests/conftest.py calls `begin_session()` when it loads, before any product import: from then on tempfile.mkdtemp,
mkstemp, mktemp and NamedTemporaryFile (TemporaryDirectory goes through mkdtemp) are wrapped in the tempfile module
itself, so `from tempfile import mkdtemp` gets the wrapper too, and each path they return is named by who made it:
<tmpN> made by test code during a test, <ptmpN> made by product code during a test (two sequences, so an extra scratch
directory in the product never renumbers the test's own), each numbered from 1 in every test, and <stmpN> made outside
any test (a module- or session-scoped fixture), numbered through the session. pytest's base temporary directory
(tmp_path's parent) is <pytest-tmp>. Any other path, under /tmp or not, is logged as it is.

A copy of the environment is logged by what differs from the environment when the session began (what the product set
at import, an earlier test leaked, a fixture or the code set, changed or removed); values the run inherited are not
logged. The gate runs base and candidate with one environment and one log path, so two runs of one test log the same
lines, and a new call, a new argument next to a temporary path, or a new environment value still logs a new line.

Still logged as noise (it can only flip a test the change did not touch, which asks for more review, never less): a
random name the code draws itself (uuid, pid, os.mkdir under gettempdir), a product change in how many scratch
directories it makes before another one (the later ones renumber), and set iteration order.

Not logged, because no such call is visible to a profiler as product-calls-test-code:
- a C callable answering in a fake's place (dict.get, str.format, list.append, a builtin): it has no Python frame;
- code compiled at run time (mock.create_autospec, exec, eval, compile, types.FunctionType): its file is <string>;
- a stand-in defined outside tests/ (another package, a file compiled under another path);
- a fake called straight from the standard library, such as pool.map(lab.exec) or Thread(target=lab.exec) written in
  the product: the caller is concurrent/futures or threading, not src/netdryrun;
- a fake executable on PATH: it answers in another process.
tests/test_fakes.py refuses each of these shapes in the must-not-pass fixtures (and the last-but-one in src/), so the
gate's comparison never rests on a fake it can't see.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading

PREFIX = "unexpected command: "
COMMAND_LOG = "NDR_FAKE_COMMAND_LOG"


class UnexpectedCommand(AssertionError):
    """A fake lab was sent a command it has no answer for."""

    def __init__(self, command: object):
        self.command = command
        super().__init__(f"{PREFIX}{command}")


def seen(command: object) -> None:
    """Record that a fake lab was sent `command` (only when the gate asks for the log)."""
    path = os.environ.get(COMMAND_LOG)
    if not path:
        return
    test = os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" (", 1)[0]
    # a fake's own record goes through the same scrubbing as the profiler's: the test's temporary paths and the
    # working directory by name, the rest as it is
    plain = _plain(command if isinstance(command, (str, bytes, os.PathLike, list, tuple, dict, set, frozenset))
                   else str(command), os.getcwd())
    text = plain if isinstance(plain, str) else json.dumps(plain, sort_keys=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"test": test, "command": text, "log": LOG_FORMAT}) + "\n")


# 2: temporary paths are scrubbed by what the test created (fastfix_gate.py reads older logs its own way)
LOG_FORMAT = 2

# env: the environment the run's environment copies are compared with (the session's start, or the test's when no
# session began); temps: (path, label, scope) for every temporary path recorded; count: the next number per label kind;
# test: a test is running; session: begin_session() ran
_STATE: dict = {"env": None, "temps": [], "count": {}, "test": False, "session": False}
_PATH_CHAR = r"[\w.~-]"
_SESSION_KIND = "stmp"


def _maker() -> str:
    """Who is making a temporary path now: <stmp> outside a test, <ptmp> product code, <tmp> anything else."""
    if not _STATE["test"]:
        return _SESSION_KIND
    skip = {os.path.abspath(__file__), os.path.abspath(tempfile.__file__)}
    f = sys._getframe(1)
    while f is not None and os.path.abspath(f.f_code.co_filename) in skip:
        f = f.f_back
    where = os.path.abspath(f.f_code.co_filename) if f is not None else ""
    return "ptmp" if where.startswith(_package_root()) else "tmp"


def _record_temp(path: object, label: str | None = None) -> None:
    """Remember a temporary path the run made (and its resolved form): logged as `label`, or the next of its kind."""
    if not isinstance(path, (str, bytes, os.PathLike)):
        return
    text = os.fsdecode(path)
    if not text or any(t[0] == text for t in _STATE["temps"]):
        return
    if label is None:
        kind = _maker()
        _STATE["count"][kind] = _STATE["count"].get(kind, 0) + 1
        label = f"<{kind}{_STATE['count'][kind]}>"
    scope = "test" if _STATE["test"] else "session"
    for p in dict.fromkeys((text, os.path.realpath(text))):
        _STATE["temps"].append((p, label, scope))


def _scrub_temps(text: str) -> str:
    """Each recorded temporary path, as a whole path name (not inside a longer name), by its label; longest first, so
    a directory made inside another keeps its own label."""
    for p, label, _scope in sorted(_STATE["temps"], key=lambda t: len(t[0]), reverse=True):
        text = _whole_path(text, p, label)
    return text


def _whole_path(text: str, path: str, label: str) -> str:
    """`path` as `label` wherever it stands as a whole path name (not part of a longer name either side)."""
    if path not in text:
        return text
    return re.sub(rf"(?<!{_PATH_CHAR}){re.escape(path)}(?!{_PATH_CHAR})", lambda _m: label, text)


def _environment(value: dict) -> bool:
    """A copy of the process environment (subprocess env=dict(os.environ)), not a dict the code built."""
    env = _STATE["env"] if _STATE["env"] is not None else os.environ
    shared = sum(1 for k in env if k in value)
    return len(env) >= 4 and shared >= max(4, len(env) // 2)


def _plain(value: object, root: str, depth: int = 0) -> object:
    """`value` as stable JSON: strings, numbers, lists and dicts as they are (the test's working directory and
    temporary names scrubbed, an environment copy reduced to what differs from the process's), anything else by its
    type name (its repr may hold an address)."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (str, os.PathLike, bytes)):
        text = os.fsdecode(value) if not isinstance(value, bytes) else value.decode("utf-8", "replace")
        return _scrub_temps(_whole_path(text, root, "<root>") if root else text)
    if depth > 4:
        return type(value).__name__
    if isinstance(value, (list, tuple)):
        return [_plain(v, root, depth + 1) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v, root, depth + 1) for v in value), key=repr)
    if isinstance(value, dict):
        if _environment(value):
            # inherited values differ by machine and by run (OLDPWD, a home directory): only what differs from the
            # environment the session began with is logged, so a value the product put in os.environ at import, an
            # earlier test leaked or the code set before copying it shows too
            # (pytest's own PYTEST_CURRENT_TEST names the test's phase, which moves from setup to call)
            start = _STATE["env"] if _STATE["env"] is not None else dict(os.environ)
            out = {str(k): _plain(v, root, depth + 1) for k, v in value.items()
                   if start.get(k) != v and k != "PYTEST_CURRENT_TEST"}
            removed = sorted(str(k) for k in start if k not in value and k != "PYTEST_CURRENT_TEST")
            return {"<environment>": "inherited values not logged", **out,
                    **({"<removed>": removed} if removed else {})}
        return {str(k): _plain(v, root, depth + 1) for k, v in value.items()}
    return type(value).__name__


def _package_root() -> str:
    try:
        import netdryrun
        return os.path.dirname(os.path.abspath(netdryrun.__file__)) + os.sep
    except ImportError:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "netdryrun") + os.sep


def command_profiler(code_root: str | None = None, fake_root: str | None = None):
    """A sys.setprofile hook (install it only while logging) that logs, through `seen`, every call from code under
    `code_root` (src/netdryrun) into code under `fake_root` (tests/) or unittest.mock, with its arguments."""
    import unittest.mock
    code_root = code_root or _package_root()
    fakes = (fake_root or os.path.dirname(os.path.abspath(__file__)) + os.sep,)
    mock_file = os.path.abspath(unittest.mock.__file__)
    callers: dict = {}
    callees: dict = {}

    def profile(frame, event, arg):
        if event != "call" or frame.f_back is None:
            return
        caller = frame.f_back.f_code
        inside = callers.get(caller)
        if inside is None:
            inside = callers[caller] = os.path.abspath(caller.co_filename).startswith(code_root)
        if not inside:
            return
        code = frame.f_code
        fake = callees.get(code)
        if fake is None:
            where = os.path.abspath(code.co_filename)
            fake = callees[code] = (where.startswith(fakes) or where == mock_file) and code not in _WRAPPERS
        if not fake:
            return
        n = code.co_argcount + code.co_kwonlyargcount + bool(code.co_flags & 0x04) + bool(code.co_flags & 0x08)
        root = os.getcwd()
        args = {k: _plain(frame.f_locals.get(k), root) for k in code.co_varnames[:n] if k not in ("self", "cls")}
        seen({"call": code.co_name, "args": args})
    return profile


_ORIGINAL = {n: getattr(tempfile, n) for n in ("mkdtemp", "mkstemp", "mktemp", "NamedTemporaryFile")}


def _mkdtemp(*a, **k):
    path = _ORIGINAL["mkdtemp"](*a, **k)
    _record_temp(path)
    return path


def _mkstemp(*a, **k):
    fd, path = _ORIGINAL["mkstemp"](*a, **k)
    _record_temp(path)
    return fd, path


def _mktemp(*a, **k):
    path = _ORIGINAL["mktemp"](*a, **k)
    _record_temp(path)
    return path


def _named_temporary_file(*a, **k):
    f = _ORIGINAL["NamedTemporaryFile"](*a, **k)
    _record_temp(getattr(f, "name", None))
    return f


# tempfile.TemporaryDirectory makes its directory through tempfile.mkdtemp
_MAKERS = {"mkdtemp": _mkdtemp, "mkstemp": _mkstemp, "mktemp": _mktemp, "NamedTemporaryFile": _named_temporary_file}
_WRAPPERS = {f.__code__ for f in _MAKERS.values()}


def _wrap() -> bool:
    """tempfile's makers replaced by the recording ones; True when this call did it."""
    if all(getattr(tempfile, n) is f for n, f in _MAKERS.items()):
        return False
    for n, f in _MAKERS.items():
        setattr(tempfile, n, f)
    return True


def _unwrap() -> None:
    for n, f in _ORIGINAL.items():
        setattr(tempfile, n, f)


def begin_session() -> None:
    """Called by tests/conftest.py as it loads, while NDR_FAKE_COMMAND_LOG is set: the environment every copy is
    compared with, and tempfile's makers wrapped, both before any product code is imported (a product import first
    would hide what it does at import, so that refuses)."""
    if not os.environ.get(COMMAND_LOG) or _STATE["session"]:
        return
    early = sorted(m for m in sys.modules if m == "netdryrun" or m.startswith("netdryrun."))
    if early:
        raise RuntimeError(f"tests/fakes.py: {early[0]} was imported before the command log began; import fakes and "
                           "call begin_session() first in tests/conftest.py")
    _STATE.update(env=dict(os.environ), session=True)
    _wrap()


def watch_temps(basetemp=None):
    """Start a test's record: no temporary paths of its own yet but pytest's base temporary directory (`basetemp`, a
    path or a callable giving it), numbering from 1, tempfile's makers wrapped (if the session didn't already), and,
    outside a session, the environment now. Returns an undo."""
    if not _STATE["session"]:
        _STATE["env"] = dict(os.environ)
    _STATE["temps"] = [t for t in _STATE["temps"] if t[2] == "session"]
    _STATE["count"] = {k: v for k, v in _STATE["count"].items() if k == _SESSION_KIND}
    _STATE["test"] = True
    if callable(basetemp):
        basetemp = basetemp()
    if basetemp is not None:
        _record_temp(basetemp, "<pytest-tmp>")
    wrapped = _wrap()

    def undo():
        _STATE["test"] = False
        _STATE["temps"] = [t for t in _STATE["temps"] if t[2] == "session"]
        if wrapped:
            _unwrap()
        if not _STATE["session"]:
            _STATE["env"] = None
    return undo


def logging_commands(basetemp=None):
    """Install the profiler on this thread and new ones, and the record of the test's temporary paths, while
    NDR_FAKE_COMMAND_LOG is set; returns an undo."""
    if not os.environ.get(COMMAND_LOG):
        return lambda: None
    old = sys.getprofile()
    unwatch = watch_temps(basetemp)
    hook = command_profiler()
    sys.setprofile(hook)
    threading.setprofile(hook)

    def undo():
        sys.setprofile(old)
        threading.setprofile(None)
        unwatch()
    return undo
