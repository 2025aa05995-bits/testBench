"""Tests for script variable expansion and for-loops."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.script_expand import expand_script_lines  # noqa: E402
from testbench.variables import VariableStore  # noqa: E402


def test_set_and_substitute():
    v = VariableStore()
    lines = ["set V 3.3", "bc.ps.set_voltage $V"]
    out = expand_script_lines(lines, v)
    assert out == ["bc.ps.set_voltage 3.3"]


def test_for_loop_expansion():
    v = VariableStore()
    lines = [
        "for V 1 2 1",
        "bc.ps.set_voltage $V",
        "endfor",
    ]
    out = expand_script_lines(lines, v)
    assert out == ["bc.ps.set_voltage 1", "bc.ps.set_voltage 2"]
