"""Execute one chat line: help, heading, plot, assert/limit, or bench/bc."""

from __future__ import annotations

from typing import Optional

from testbench.chat_plotting import (
    plot_data_csv_path,
    should_log_plot_data_as_csv,
    try_extract_plot_command,
    write_plot_series_csv,
)
from testbench.command_parser import handle_help, try_parse_quoted_heading
from testbench.runner import BenchRunner


def run_chat_command(
    command: str,
    registry,
    parser,
    append_text,
    append_error,
    append_heading,
    append_plot_from_data,
    record_result=None,
    runner: Optional[BenchRunner] = None,
) -> None:
    """
    Run a single user command: help, quoted heading, plot, assert/limit, or bench/bc.

    If ``record_result`` is provided, it is invoked once per executable command:

    - on success: ``record_result(command, result=<value>)``
    - on failure: ``record_result(command, error=<str>)`` or check failure

    Pure UI commands (``help``, quoted headings, parse errors) are not recorded.
    """
    bench = runner or BenchRunner(registry=registry, parser=parser)

    def _out(msg: str) -> None:
        append_text(msg)

    def _err(msg: str) -> None:
        append_error(msg)

    cmd = (command or "").strip()
    if not cmd:
        return

    # Plot with CSV logging stays in this module (GUI-specific display).
    plot_parts = try_extract_plot_command(cmd)
    if plot_parts is not None:
        plot_file_label, plot_inner = plot_parts
        parsed = parser.parse(plot_inner)
        if not parsed:
            append_error(
                "Error: plot needs a valid bench command, e.g. plot bc.sg.measure frequency, "
                'plot "My run" bc.osc.get_trace 1, or plot(bc.sg.measure frequency)\n\n'
            )
            if record_result is not None:
                try:
                    record_result(command, error="plot needs a valid bench command")
                except Exception:
                    pass
            return
        try:
            result = registry.execute(parsed["category"], parsed["action"], parsed["args"])
            if should_log_plot_data_as_csv(result):
                try:
                    csv_path = plot_data_csv_path(plot_file_label)
                    nrows = write_plot_series_csv(result, csv_path)[2]
                    append_text(f"Result: {nrows} data rows logged to CSV (not printed here).\n{csv_path}\n")
                except OSError as e:
                    append_error(f"Could not write plot CSV log: {e}\n")
                    append_text(f"Result: {result}\n")
            else:
                append_text(f"Result: {result}\n")
            append_plot_from_data(result)
            append_text("\n")
            if record_result is not None:
                try:
                    record_result(command, result=result)
                except Exception:
                    pass
        except ValueError as e:
            append_error(f"Error: {e}\n\n")
            if record_result is not None:
                try:
                    record_result(command, error=str(e))
                except Exception:
                    pass
        except Exception as e:
            append_error(f"Error: {e}\n\n")
            if record_result is not None:
                try:
                    record_result(command, error=str(e))
                except Exception:
                    pass
        return

    title = try_parse_quoted_heading(cmd)
    if title is not None:
        append_heading(title)
        return

    outcome = bench.run_line(cmd, on_output=_out, on_error=_err, record=False)

    if record_result is None:
        return

    try:
        if outcome.check is not None:
            if outcome.success:
                record_result(command, result=outcome.check)
            else:
                record_result(command, error=outcome.message or "check failed")
        elif outcome.success:
            record_result(command, result=outcome.result)
        else:
            record_result(command, error=outcome.message or "error")
    except Exception:
        pass
