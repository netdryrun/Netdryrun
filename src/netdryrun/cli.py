"""Command-line interface: netdryrun run | check | validate | record | mcp | feedback."""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import traceback
from pathlib import Path

from . import __version__, report
from .config import ConfigError
from .runner import error_report, install_signal_handlers, load_config, run, signal_exit_code, signal_name

EXIT_CODES = """exit codes:
  0  passed        every check passed
  1  failed        at least one check failed (the change broke something)
  2  error         config error, bad topology, lab problem, bad option, a report that could not be
                   written (after the verdict, which is printed), or an internal error: no verdict
  3  inconclusive  the lab never reached a testable state: no verdict
  130, 143, 129    interrupted by SIGINT (Ctrl-C), SIGTERM or SIGHUP: no verdict; the lab is destroyed
                   unless --keep was set

Set NETDRYRUN_DEBUG=1 (or pass --debug) to print the traceback of an internal error."""


def _seconds(text: str) -> float:
    """argparse type for a duration: a number >= 0 (a bad value exits 2 with a one-line message)."""
    try:
        v = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a number of seconds, got {text!r}") from None
    if not (0 <= v < math.inf):
        raise argparse.ArgumentTypeError(f"must be a number of seconds >= 0, got {text}")
    return v


def _write_outputs(rep, args) -> list[str]:
    """Write every requested report, even if an earlier one fails. Returns one line per report that could
    not be written (empty if all were)."""
    failures = []
    outputs = {"json": report.to_json, "markdown": report.to_markdown, "junit": report.to_junit,
               "verdict": lambda r: _verdict_json(r, args)}
    for key, render in outputs.items():
        path = getattr(args, key, None)
        if path:
            try:
                Path(path).write_text(render(rep), encoding="utf-8")
            except OSError as e:
                failures.append(f"could not write {path}: {e.strerror or e}; the verdict was {rep.status}")
                continue
            print(f"  wrote {key} report: {path}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and not getattr(args, "no_step_summary", False):
        try:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(report.to_markdown(rep))
        except OSError as e:
            failures.append(f"could not write {summary}: {e.strerror or e}; the verdict was {rep.status}")
    for line in failures:
        print(line, file=sys.stderr)
    return failures


def _verdict_json(rep, args) -> str:
    """The agent result (netdryrun.mcp-result/v1), as the MCP tools return it. A run that never started (a
    config error) is the setup error; `tested` was read before the run."""
    from . import agent_result

    if getattr(args, "tested", None) is None:   # no config was loaded: nothing ran
        return json.dumps({"schema": agent_result.RESULT_SCHEMA, "status": "error", "error": rep.error,
                           "verdict": agent_result.DO_NOT_APPLY}, indent=2)
    result = agent_result._summary(rep, getattr(args, "json", None), args.tested)
    return json.dumps(agent_result.hold_to_files(result, rep.config, args.tested), indent=2)


def _cmd_run(args, deploy: bool) -> int:
    try:
        cfg = load_config(args.path)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        if getattr(args, "json", None) or getattr(args, "verdict", None):
            _write_outputs(error_report(args.path, f"config error: {e}"), args)
        return 2
    if getattr(args, "verdict", None):
        from .agent_result import _tested
        args.tested = _tested(cfg, deployed=deploy)   # the files this run uses, read before it starts
    print(f"Netdryrun {__version__}: {len(cfg.checks)} checks from {cfg.path}")
    install_signal_handlers()
    try:
        rep = run(cfg, deploy=deploy, keep=args.keep, keep_on_failure=getattr(args, 'keep_on_failure', False),
                  settle=args.settle, hold=args.hold,
                  on_result=lambda r: print(report.console_line(r), flush=True),
                  log=lambda m: print(m, flush=True))
    except KeyboardInterrupt as e:
        # run() destroys the lab in its finally block before the interrupt reaches us
        signum = getattr(e, "signum", signal.SIGINT)
        partial = getattr(e, "report", None)
        if partial is not None:
            try:
                _write_outputs(partial, args)   # status "error": an interrupted run has no verdict
            except Exception:
                pass
        print(f"\nInterrupted: no verdict ({signal_name(signum)}). The lab was cleaned up unless --keep was set.",
              file=sys.stderr)
        return signal_exit_code(signum)
    print(report.summary_line(rep))
    if _write_outputs(rep, args):
        # The verdict is in, but evidence the user asked for is missing: no usable result (exit 2)
        return 2
    if sys.stdout.isatty() and not os.environ.get("CI"):
        print("How did it go? Run `netdryrun feedback` (opens a GitHub form; nothing is sent automatically).")
    return rep.exit_code


def _cmd_validate(args) -> int:
    try:
        cfg = load_config(args.path)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    from .drivers import DriverError
    from .lab import LabError
    from .runner import check_topology

    try:
        lab = check_topology(cfg)   # the topology and every check run makes before deploying
    except LabError as e:
        print(f"lab error: {e}", file=sys.stderr)
        return 2
    except DriverError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"OK: {cfg.path} ({len(cfg.checks)} checks, lab {cfg.lab}, {len(lab.nodes)} nodes)")
    for c in cfg.checks:
        print(f"  - [{c.type}] {c.name}")
    return 0


def _cmd_record(args) -> int:
    import os
    import time

    from .lab import Lab, LabError
    from .record import record, render

    topo = Path(args.topology).resolve()
    if not topo.exists():
        print(f"error: {topo} not found", file=sys.stderr)
        return 2
    out = Path(args.out).resolve() if args.out else topo.parent / "netdryrun.yml"
    if out.exists() and not args.force:
        print(f"error: {out} exists; use --force to overwrite or --out to pick another file", file=sys.stderr)
        return 2
    try:
        lab = Lab(topo)
    except LabError as e:
        print(f"lab error: {e}", file=sys.stderr)
        return 2
    try:
        if args.deploy:
            print(f"Deploying lab {lab.name}, then waiting {args.wait:g}s for the network to converge...", flush=True)
            lab.deploy()
            time.sleep(args.wait)
        mode = "exact" if args.exact_prefixes else "min" if args.min_prefixes else "range"
        data, warnings = record(topo, include_routes=not args.no_routes, prefix_mode=mode, attributes=args.attributes,
                                guards=not args.no_guards, log=lambda m: print(m, flush=True))
    except LabError as e:
        print(f"lab error: {e}", file=sys.stderr)
        return 2
    finally:
        if args.deploy:
            lab.destroy()
    if not data["checks"]:
        for w in warnings:
            print(f"warning: {w}")
        print("error: nothing to record (no established BGP sessions or BGP routes found); is the lab converged? "
              "Try --deploy with a longer --wait.", file=sys.stderr)
        return 2
    data["lab"] = os.path.relpath(topo, out.parent).replace(os.sep, "/")
    out.write_text(render(data, warnings), encoding="utf-8")
    for w in warnings:
        print(f"warning: {w}")
    for w in (w for w in warnings if w.startswith("INCOMPLETE BASELINE")):
        print(f"\n*** {w} ***", file=sys.stderr)
    print(f"Recorded {len(data['checks'])} checks to {out}. Review it, then: netdryrun run {out.parent}")
    return 0


FEEDBACK_URL = "https://github.com/netdryrun/netdryrun/issues/new"


def feedback_url() -> str:
    """The feedback form, prefilled with the version and platform only. Nothing is sent until the user submits."""
    import platform
    from urllib.parse import urlencode

    query = {"template": "feedback.yml", "labels": "feedback", "version": __version__,
             "platform": f"{platform.system()} {platform.release()}, Python {platform.python_version()}"}
    return f"{FEEDBACK_URL}?{urlencode(query)}"


def _cmd_feedback(args) -> int:
    url = feedback_url()
    print("Thanks for trying Netdryrun. The form asks what you tested and what got in the way; it takes 2 minutes.")
    print("Nothing is sent until you submit it on GitHub. Prefilled: your Netdryrun version and platform.")
    print(url)
    if not args.print_only:
        import webbrowser

        webbrowser.open(url)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="netdryrun", description="Test network changes in a real virtual lab before production.",
                                 epilog=EXIT_CODES, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"netdryrun {__version__}")
    ap.add_argument("--debug", action="store_true", help="print the traceback of an internal error")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--debug", action="store_true", default=argparse.SUPPRESS,
                        help="print the traceback of an internal error")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_run_opts(p):
        p.add_argument("path", nargs="?", default=".", help="netdryrun.yml or the folder containing it")
        p.add_argument("--json", metavar="FILE", help="write the full evidence report as JSON")
        p.add_argument("--markdown", metavar="FILE", help="write a Markdown summary (for PR comments)")
        p.add_argument("--junit", metavar="FILE", help="write JUnit XML (for CI test reporting)")
        p.add_argument("--verdict", metavar="FILE",
                       help="write the agent result as JSON: status, verdict, failures and the files tested, "
                            "the shape the MCP tools return (netdryrun.mcp-result/v1)")
        p.add_argument("--settle", type=_seconds, default=10.0, help="seconds to wait before negative checks (default 10)")
        p.add_argument("--hold", type=_seconds, default=10.0, help="seconds a negative check must hold (default 10)")
        p.add_argument("--no-step-summary", action="store_true", help="don't append to $GITHUB_STEP_SUMMARY")

    p_run = sub.add_parser("run", help="deploy the lab, run checks, destroy the lab", parents=[common],
                           epilog=EXIT_CODES, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_opts(p_run)
    p_run.add_argument("--keep", action="store_true", help="leave the lab running afterwards (for debugging)")
    p_run.add_argument("--keep-on-failure", action="store_true", help="leave the lab running only if a check fails")

    p_check = sub.add_parser("check", help="run checks against an already running lab", parents=[common],
                             epilog=EXIT_CODES, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_opts(p_check)
    p_check.set_defaults(keep=True)

    p_val = sub.add_parser("validate", help="validate netdryrun.yml without running anything", parents=[common])
    p_val.add_argument("path", nargs="?", default=".")

    p_rec = sub.add_parser("record", help="snapshot a known-good lab into a netdryrun.yml baseline", parents=[common])
    p_rec.add_argument("topology", help="containerlab topology file of the lab to record")
    p_rec.add_argument("--out", metavar="FILE", help="where to write (default: netdryrun.yml next to the topology)")
    p_rec.add_argument("--deploy", action="store_true", help="deploy the lab first and destroy it afterwards")
    p_rec.add_argument("--wait", type=_seconds, default=45.0, help="with --deploy: seconds to let BGP converge (default 45)")
    counts = p_rec.add_mutually_exclusive_group()
    counts.add_argument("--exact-prefixes", action="store_true",
                        help="pin prefix counts exactly (default: today's count as min, max with 20%% headroom)")
    counts.add_argument("--min-prefixes", action="store_true", help="record prefix counts as minimums only")
    p_rec.add_argument("--no-guards", action="store_true",
                       help="don't add the standard guards (no default route and no link subnet via BGP on each BGP "
                            "node, except what it learns today), which record writes by default")
    p_rec.add_argument("--no-routes", action="store_true", help="don't record individual BGP routes")
    p_rec.add_argument("--attributes", action="store_true",
                       help="also pin each BGP route's AS path, local preference and communities (bgp_route checks)")
    p_rec.add_argument("--force", action="store_true", help="overwrite an existing output file")

    sub.add_parser("mcp", help="run the MCP server (stdio) so AI agents can dry-run changes")

    p_fb = sub.add_parser("feedback", help="open a short feedback form on GitHub (nothing is sent automatically)")
    p_fb.add_argument("--print-only", action="store_true", help="print the form URL instead of opening a browser")

    args = ap.parse_args(argv)
    if args.debug:
        os.environ["NETDRYRUN_DEBUG"] = "1"
    try:
        if args.cmd == "mcp":
            from .mcp_server import main as mcp_main
            mcp_main()
            return 0
        if args.cmd == "validate":
            return _cmd_validate(args)
        if args.cmd == "record":
            return _cmd_record(args)
        if args.cmd == "feedback":
            return _cmd_feedback(args)
        return _cmd_run(args, deploy=args.cmd == "run")
    except KeyboardInterrupt as e:
        signum = getattr(e, "signum", signal.SIGINT)
        print(f"\nInterrupted ({signal_name(signum)}).", file=sys.stderr)
        return signal_exit_code(signum)
    except Exception as e:
        # Anything unexpected is an error (exit 2), never "checks failed" (exit 1), and never a bare traceback
        if os.environ.get("NETDRYRUN_DEBUG", "") not in ("", "0", "false", "no"):
            traceback.print_exc()
        print(f"error: internal error: {type(e).__name__}: {e} (rerun with --debug for the traceback)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
