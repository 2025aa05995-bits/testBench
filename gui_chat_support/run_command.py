"""Execute one chat line: help, heading, plot, or bench/bc."""

from testbench.chat_plotting import (
    plot_data_csv_path,
    should_log_plot_data_as_csv,
    try_extract_plot_command,
    write_plot_series_csv,
)
from testbench.command_parser import handle_help

from .command_helpers import try_parse_quoted_heading


def run_chat_command(
    command: str,
    registry,
    parser,
    append_text,
    append_error,
    append_heading,
    append_plot_from_data,
    record_result=None,
) -> None:
    """
    Run a single user command: help, quoted heading, plot, or bench/bc.

    If ``record_result`` is provided, it is invoked once per executable command:

    - on success: ``record_result(command, result=<value>)``
    - on failure: ``record_result(command, error=<str>)``

    Pure UI commands (``help``, quoted headings, parse errors) are not recorded.
    """

    def _emit_result(value) -> None:
        if record_result is not None:
            try:
                record_result(command, result=value)
            except Exception:
                pass

    def _emit_error(err) -> None:
        if record_result is not None:
            try:
                record_result(command, error=str(err))
            except Exception:
                pass

    cmd = (command or "").strip()
    if not cmd:
        return
    if cmd.lower() == "help":
        response = handle_help([], registry)
        append_text(f"\n{response}\n\n")
        return
    if cmd.lower().startswith("help "):
        args = cmd[5:].strip().split()
        response = handle_help(args, registry)
        append_text(f"\n{response}\n\n")
        return

    title = try_parse_quoted_heading(cmd)
    if title is not None:
        append_heading(title)
        return

    plot_parts = try_extract_plot_command(cmd)
    if plot_parts is not None:
        plot_file_label, plot_inner = plot_parts
        parsed = parser.parse(plot_inner)
        if not parsed:
            append_error(
                "Error: plot needs a valid bench command, e.g. plot bc.sg.measure frequency, "
                'plot "My run" bc.osc.get_trace 1, or plot(bc.sg.measure frequency)\n\n'
            )
            _emit_error("plot needs a valid bench command")
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
            _emit_result(result)
        except ValueError as e:
            append_error(f"Error: {e}\n\n")
            _emit_error(e)
        except Exception as e:
            append_error(f"Error: {e}\n\n")
            _emit_error(e)
        return

    parsed = parser.parse(cmd)
    if not parsed:
        append_error(
            "Error: Invalid command format. Expected: bench.<category>.<action> or bc.<category>.<action> [args...]\n"
        )
        append_error("       Example: bench.ps.on True or bc.ps.on True\n")
        append_error("       Type 'help' for all available commands\n\n")
        return

    try:
        result = registry.execute(parsed["category"], parsed["action"], parsed["args"])
        response = "OK" if result is None else str(result)
        append_text(f"Result: {response}\n\n")
        _emit_result(result)
    except ValueError as e:
        append_error(f"Error: {e}\n\n")
        _emit_error(e)
    except Exception as e:
        append_error(f"Error: {e}\n\n")
        _emit_error(e)
