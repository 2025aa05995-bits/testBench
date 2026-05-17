"""Tests for automation loop helpers (failure detection, prompts, config)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.llm_automation_loop import (
    AutomationLoopConfig,
    build_plan_user_content,
    format_conversation_for_plan,
    make_conversation_turn,
    results_need_repair,
    summarize_results_outcome,
    trim_conversation_turns,
)


def test_results_need_repair_error():
    assert results_need_repair([{"command": "bc.ps.on", "error": "timeout"}])


def test_results_need_repair_check_failed():
    assert results_need_repair(
        [
            {
                "command": "limit bc.ps.measure_voltage 3 3.6",
                "result": {"passed": False, "message": "FAIL: 2.1 outside [3, 3.6]"},
            }
        ]
    )


def test_results_need_repair_pass():
    assert not results_need_repair(
        [
            {
                "command": "limit bc.ps.measure_voltage 3 3.6",
                "result": {"passed": True, "message": "PASS: 3.3 in [3, 3.6]"},
            }
        ]
    )


def test_automation_loop_config_nested():
    cfg = {
        "llm": {
            "automation_loop": {
                "enabled": False,
                "max_iterations": 5,
                "multi_turn_history": 2,
            }
        }
    }
    c = AutomationLoopConfig.from_config(cfg)
    assert c.enabled is False
    assert c.max_iterations == 5
    assert c.multi_turn_history == 2


def test_build_plan_user_content_includes_prior_turns():
    turns = [
        make_conversation_turn(
            "set 3.3V",
            ["bc.ps.set_voltage 3.3"],
            [{"command": "bc.ps.set_voltage 3.3", "result": "ok"}],
            analysis="ramp supply",
        )
    ]
    text = build_plan_user_content(
        "now verify",
        "ps.set_voltage — set output",
        "",
        conversation_turns=turns,
    )
    assert "PRIOR TURNS:" in text
    assert "set 3.3V" in text
    assert "REQUEST:\nnow verify" in text


def test_trim_conversation_turns():
    turns = [{"user": str(i)} for i in range(5)]
    out = trim_conversation_turns(turns, 2)
    assert len(out) == 2
    assert out[0]["user"] == "3"


def test_summarize_results_outcome():
    assert "FAIL" in summarize_results_outcome(
        [{"command": "x", "error": "boom"}]
    )
    assert summarize_results_outcome(
        [{"command": "x", "result": {"passed": True, "message": "PASS: 1"}}]
    ).startswith("PASS")
