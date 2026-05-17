"""Tests for LLM command list validation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from testbench.command_parser import CommandParser
from gui_chat_support.command_helpers import validate_llm_commands


def test_bare_section_title_coerced_to_quoted_heading():
    parser = CommandParser()
    safe, err = validate_llm_commands(
        ["Power Cycle", "bc.ps.off", "delay 1", "bc.ps.on"],
        parser,
    )
    assert err is None
    assert safe[0] == '"Power Cycle"'
    assert safe[1:] == ["bc.ps.off", "delay 1", "bc.ps.on"]


def test_capture_osc_coerced_to_heading():
    parser = CommandParser()
    safe, err = validate_llm_commands(
        ["Power Cycle", "Capture OSC", "bc.ps.on", "bc.osc.run"],
        parser,
    )
    assert err is None
    assert safe[0] == '"Power Cycle"'
    assert safe[1] == '"Capture OSC"'
    assert safe[2:] == ["bc.ps.on", "bc.osc.run"]


def test_invalid_command_still_fails():
    parser = CommandParser()
    safe, err = validate_llm_commands(["not a real command at all"], parser)
    assert safe == []
    assert err and "invalid command" in err.lower()
