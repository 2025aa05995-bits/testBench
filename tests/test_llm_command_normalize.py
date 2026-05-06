import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from testbench.command_parser import CommandParser, normalize_llm_command_prefix  # noqa: E402


def test_normalize_bare_category_action():
    assert normalize_llm_command_prefix("osc.run") == "bc.osc.run"
    assert normalize_llm_command_prefix("ps.on True") == "bc.ps.on True"


def test_normalize_already_prefixed():
    assert normalize_llm_command_prefix("bc.osc.run") == "bc.osc.run"
    assert normalize_llm_command_prefix("bench.ps.off") == "bench.ps.off"


def test_normalize_skips_keywords():
    assert normalize_llm_command_prefix("delay 2") == "delay 2"
    assert normalize_llm_command_prefix("help osc") == "help osc"
    assert normalize_llm_command_prefix('plot bc.osc.run') == "plot bc.osc.run"


def test_parse_after_normalize():
    p = CommandParser()
    assert p.parse(normalize_llm_command_prefix("osc.run"))["category"] == "osc"
