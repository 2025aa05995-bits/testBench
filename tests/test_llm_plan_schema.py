"""Tests for structured LLM plan schema and assert/limit codegen."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.llm_plan_schema import (  # noqa: E402
    check_to_command_line,
    finalize_plan,
    merge_plan_commands,
    parse_checks,
    structured_plan_from_payload,
)
from testbench.llm_chat import _parse_plan_response  # noqa: E402


def test_parse_checks_to_assert_line():
    checks = parse_checks(
        [
            {"type": "assert", "command": "bc.mm.measure_voltage", "expected": 5.25, "tolerance": 0.1},
            {"type": "limit", "command": "bc.ps.measure_voltage", "min": 3.0, "max": 3.6},
        ]
    )
    assert len(checks) == 2
    assert "assert bc.mm.measure_voltage 5.25 0.1" == check_to_command_line(checks[0])
    assert "limit bc.ps.measure_voltage 3.0 3.6" == check_to_command_line(checks[1])


def test_merge_plan_commands():
    cmds = merge_plan_commands(
        ["bc.ps.on"],
        parse_checks([{"type": "assert", "command": "bc.mm.measure_voltage", "expected": 5.25, "tolerance": 0.1}]),
    )
    assert cmds[0] == "bc.ps.on"
    assert any(c.startswith("assert ") for c in cmds)


def test_parse_plan_response_with_checks():
    raw = """{
      "commands": ["bc.ps.set_voltage 3.3", "bc.ps.on"],
      "analysis": "Power up",
      "checks": [
        {"type": "limit", "command": "bc.ps.measure_voltage", "min": 3.0, "max": 3.6}
      ],
      "pass_criteria": ["Output voltage within range"]
    }"""
    cmds, analysis = _parse_plan_response(raw, {"llm": {"plan_include_checks": True}})
    assert "bc.ps.on" in cmds
    assert any(c.startswith("limit ") for c in cmds)
    assert "Pass criteria" in analysis


def test_parse_plan_without_checks_when_disabled():
    raw = """{
      "commands": ["bc.ps.on"],
      "analysis": "on",
      "checks": [{"type": "assert", "command": "bc.mm.measure_voltage", "expected": 5.25, "tolerance": 0.1}]
    }"""
    cmds, _ = _parse_plan_response(raw, {"llm": {"plan_include_checks": False}})
    assert cmds == ["bc.ps.on"]


def test_structured_plan_from_payload():
    plan = structured_plan_from_payload(
        {"commands": ["bc.ps.off"], "analysis": "off", "pass_criteria": ["safe"]}
    )
    cmds, analysis = finalize_plan(plan)
    assert cmds == ["bc.ps.off"]
    assert "safe" in analysis
