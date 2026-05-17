"""Tests for assert/limit parsing and evaluation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.limit_assert import (  # noqa: E402
    evaluate_assert,
    evaluate_limit,
    parse_assert_line,
    parse_limit_line,
)


def test_parse_assert_positional():
    bench, exp, tol, field = parse_assert_line("assert bc.mm.measure_voltage 5.25 0.1")
    assert bench == "bc.mm.measure_voltage"
    assert exp == 5.25
    assert tol == 0.1
    assert field is None


def test_parse_limit_kv():
    bench, vmin, vmax, field = parse_limit_line(
        "limit bc.ps.status field=voltage_v min=3.0 max=3.6"
    )
    assert bench == "bc.ps.status"
    assert vmin == 3.0
    assert vmax == 3.6
    assert field == "voltage_v"


def test_evaluate_assert_pass_fail():
    ok = evaluate_assert(5.24, 5.25, 0.1)
    assert ok.passed
    bad = evaluate_assert(5.5, 5.25, 0.1)
    assert not bad.passed


def test_evaluate_limit_dict_field():
    ok = evaluate_limit({"voltage_v": 3.3}, 3.0, 3.6, field="voltage_v")
    assert ok.passed
