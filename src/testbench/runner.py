"""Headless and shared command execution (scripts, assert/limit, variables)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

from .chat_plotting import try_extract_plot_command
from .command_parser import (
    CommandParser,
    handle_help,
    normalize_llm_command_prefix,
    try_parse_quoted_heading,
)
from .command_registry import CommandRegistry
from .limit_assert import (
    evaluate_assert,
    evaluate_limit,
    is_assert_line,
    is_limit_line,
    parse_assert_line,
    parse_limit_line,
    serialize_check,
)
from .script_expand import expand_script_lines
from .session_report import SessionRecorder
from .variables import VariableStore, parse_set_command

@dataclass
class RunOutcome:
    success: bool
    message: str = ""
    result: Any = None
    check: Optional[dict] = None


class BenchRunner:
    """Execute bench scripts with variables, loops, limits, and session recording."""

    def __init__(
        self,
        registry: Optional[CommandRegistry] = None,
        parser: Optional[CommandParser] = None,
        config_file: Optional[str] = None,
    ) -> None:
        self.registry = registry or CommandRegistry(config_file)
        self.parser = parser or CommandParser()
        self.variables = VariableStore()
        cfg = config_file or self.registry.config_manager.config_file
        self.session = SessionRecorder(config_path=cfg)

    @staticmethod
    def load_script_file(path: str) -> List[str]:
        text = Path(path).read_text(encoding="utf-8")
        return BenchRunner.load_script_text(text)

    @staticmethod
    def load_script_text(text: str) -> List[str]:
        lines: List[str] = []
        for raw in text.splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            lines.append(raw.rstrip("\n"))
        return lines

    def expand(self, lines: List[str]) -> List[str]:
        return expand_script_lines(lines, self.variables)

    def run_script(
        self,
        lines: List[str],
        *,
        on_output: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        delay_impl: Optional[Callable[[float], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None,
        record_session: bool = True,
    ) -> SessionRecorder:
        """Expand and run a script; returns the session recorder."""
        expanded = self.expand(lines)
        for cmd in expanded:
            if stop_check and stop_check():
                break
            self.run_line(
                cmd,
                on_output=on_output,
                on_error=on_error,
                delay_impl=delay_impl,
                record=record_session,
            )
        return self.session

    def run_line(
        self,
        command: str,
        *,
        on_output: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        delay_impl: Optional[Callable[[float], None]] = None,
        record: bool = True,
    ) -> RunOutcome:
        out = on_output or (lambda s: None)
        err = on_error or (lambda s: None)

        cmd = (command or "").strip()
        if not cmd:
            return RunOutcome(True)

        try:
            cmd = self._preprocess_line(cmd)
        except ValueError as e:
            err(f"Error: {e}\n")
            if record:
                self.session.record(cmd, status="error", error=str(e))
            return RunOutcome(False, str(e))

        if cmd.lower().startswith("set "):
            try:
                name, value = parse_set_command(cmd)
                self.variables.set(name, self.variables.substitute(value))
                msg = f"Set ${name} = {self.variables.get(name)}"
                out(f"{msg}\n")
                if record:
                    self.session.record(cmd, status="ok", result=msg)
                return RunOutcome(True, msg)
            except ValueError as e:
                err(f"Error: {e}\n")
                if record:
                    self.session.record(cmd, status="error", error=str(e))
                return RunOutcome(False, str(e))

        if is_assert_line(cmd):
            return self._run_assert(cmd, out, err, record=record)
        if is_limit_line(cmd):
            return self._run_limit(cmd, out, err, record=record)

        parts = cmd.split(None, 1)
        if parts and parts[0].lower() == "delay":
            return self._run_delay(cmd, parts, out, err, delay_impl, record=record)

        title = try_parse_quoted_heading(cmd)
        if title is not None:
            out(f"\n=== {title} ===\n")
            if record:
                self.session.record(cmd, status="heading", result=title)
            return RunOutcome(True, title)

        if cmd.lower() == "help" or cmd.lower().startswith("help "):
            args = [] if cmd.lower() == "help" else cmd[5:].strip().split()
            text = handle_help(args, self.registry)
            out(f"\n{text}\n\n")
            if record:
                self.session.record(cmd, status="ok", result=text)
            return RunOutcome(True, text)

        plot_parts = try_extract_plot_command(cmd)
        if plot_parts is not None:
            _, inner = plot_parts
            inner = normalize_llm_command_prefix(inner)
            parsed = self.parser.parse(inner)
            if not parsed:
                msg = "plot needs a valid bench command"
                err(f"Error: {msg}\n")
                if record:
                    self.session.record(cmd, status="error", error=msg)
                return RunOutcome(False, msg)
            try:
                result = self.registry.execute(parsed["category"], parsed["action"], parsed["args"])
                out(f"Result: {result}\n\n")
                if record:
                    self.session.record(cmd, status="ok", result=result)
                return RunOutcome(True, result=result)
            except Exception as e:
                err(f"Error: {e}\n\n")
                if record:
                    self.session.record(cmd, status="error", error=str(e))
                return RunOutcome(False, str(e))

        parsed = self.parser.parse(cmd)
        if not parsed:
            msg = "Invalid command format"
            err(f"Error: {msg}\n")
            if record:
                self.session.record(cmd, status="error", error=msg)
            return RunOutcome(False, msg)

        try:
            result = self.registry.execute(parsed["category"], parsed["action"], parsed["args"])
            response = "OK" if result is None else str(result)
            out(f"Result: {response}\n\n")
            if record:
                self.session.record(cmd, status="ok", result=result)
            return RunOutcome(True, response, result=result)
        except Exception as e:
            err(f"Error: {e}\n\n")
            if record:
                self.session.record(cmd, status="error", error=str(e))
            return RunOutcome(False, str(e))

    def _preprocess_line(self, cmd: str) -> str:
        if cmd.lower().startswith("set "):
            return cmd
        return self.variables.substitute(normalize_llm_command_prefix(cmd))

    def _run_assert(self, cmd, out, err, *, record) -> RunOutcome:
        try:
            bench, expected, tolerance, field = parse_assert_line(cmd)
            bench = normalize_llm_command_prefix(self.variables.substitute(bench))
            parsed = self.parser.parse(bench)
            if not parsed:
                raise ValueError(f"Invalid bench command in assert: {bench}")
            measured = self.registry.execute(parsed["category"], parsed["action"], parsed["args"])
            check = evaluate_assert(measured, expected, tolerance, field)
            status = "pass" if check.passed else "fail"
            line = f"{check.message}\n"
            if check.passed:
                out(line)
            else:
                err(line)
            if record:
                self.session.record(cmd, status=status, result=measured, check=serialize_check(check))
            return RunOutcome(check.passed, check.message, result=measured, check=serialize_check(check))
        except Exception as e:
            err(f"Error: {e}\n\n")
            if record:
                self.session.record(cmd, status="error", error=str(e))
            return RunOutcome(False, str(e))

    def _run_limit(self, cmd, out, err, *, record) -> RunOutcome:
        try:
            bench, vmin, vmax, field = parse_limit_line(cmd)
            bench = normalize_llm_command_prefix(self.variables.substitute(bench))
            parsed = self.parser.parse(bench)
            if not parsed:
                raise ValueError(f"Invalid bench command in limit: {bench}")
            measured = self.registry.execute(parsed["category"], parsed["action"], parsed["args"])
            check = evaluate_limit(measured, vmin, vmax, field)
            status = "pass" if check.passed else "fail"
            line = f"{check.message}\n"
            if check.passed:
                out(line)
            else:
                err(line)
            if record:
                self.session.record(cmd, status=status, result=measured, check=serialize_check(check))
            return RunOutcome(check.passed, check.message, result=measured, check=serialize_check(check))
        except Exception as e:
            err(f"Error: {e}\n\n")
            if record:
                self.session.record(cmd, status="error", error=str(e))
            return RunOutcome(False, str(e))

    def _run_delay(self, cmd, parts, out, err, delay_impl, *, record) -> RunOutcome:
        if len(parts) < 2:
            err("Usage: delay <seconds>\n")
            if record:
                self.session.record(cmd, status="error", error="missing seconds")
            return RunOutcome(False, "missing seconds")
        try:
            sec = float(parts[1].strip())
        except ValueError:
            err(f"Invalid delay value: {parts[1]!r}\n")
            if record:
                self.session.record(cmd, status="error", error="invalid delay")
            return RunOutcome(False, "invalid delay")
        if sec < 0:
            err("Delay must be non-negative.\n")
            if record:
                self.session.record(cmd, status="error", error="negative delay")
            return RunOutcome(False, "negative delay")
        if delay_impl:
            delay_impl(sec)
        else:
            time.sleep(sec)
        if record:
            self.session.record(cmd, status="ok", result={"delay_seconds": sec})
        return RunOutcome(True, f"delayed {sec}s")
