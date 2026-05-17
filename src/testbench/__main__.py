"""Headless CLI: ``python -m testbench run <script>``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._paths import default_config_file, repo_root
from .runner import BenchRunner


def _ensure_src_path() -> None:
    src = repo_root() / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main(argv: list | None = None) -> int:
    _ensure_src_path()
    parser = argparse.ArgumentParser(prog="testbench", description="Test Bench headless runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a script file or inline commands")
    run_p.add_argument("script", nargs="?", help="Path to .bench / .txt script")
    run_p.add_argument("-c", "--command", action="append", dest="commands", help="Inline command (repeatable)")
    run_p.add_argument("--config", default=None, help="Path to testbenchconfig.json")
    run_p.add_argument("--report", dest="report_json", default=None, help="Write JSON session report to this path")
    run_p.add_argument("--report-html", dest="report_html", default=None, help="Write HTML session report to this path")
    run_p.add_argument("-q", "--quiet", action="store_true", help="Only print errors and pass/fail lines")

    args = parser.parse_args(argv)
    if args.command != "run":
        parser.print_help()
        return 2

    config = args.config or str(default_config_file())
    lines: list = []
    if args.script:
        lines.extend(BenchRunner.load_script_file(args.script))
    if args.commands:
        lines.extend(args.commands)
    if not lines:
        run_p.error("Provide a script file and/or -c commands")

    runner = BenchRunner(config_file=config)

    def out(msg: str) -> None:
        if not args.quiet:
            sys.stdout.write(msg)
            sys.stdout.flush()

    def err(msg: str) -> None:
        sys.stderr.write(msg)
        sys.stderr.flush()

    runner.run_script(lines, on_output=out, on_error=err, record_session=True)

    if args.report_json:
        path = runner.session.export_json(args.report_json)
        out(f"Report written: {path}\n")
    if args.report_html:
        path = runner.session.export_html(args.report_html)
        out(f"HTML report written: {path}\n")

    summary = runner.session.to_dict()["summary"]
    verdict = runner.session.verdict
    out(f"\nVerdict: {verdict} (pass={summary['pass']} fail={summary['fail']} error={summary['error']})\n")

    return 0 if verdict in ("PASS", "OK") else 1


if __name__ == "__main__":
    raise SystemExit(main())
