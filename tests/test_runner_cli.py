"""Headless runner and signal analyzer registration."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.command_registry import CommandRegistry  # noqa: E402
from testbench.runner import BenchRunner  # noqa: E402


def test_san_registered():
    reg = CommandRegistry()
    assert "san" in reg.instruments
    assert reg.get_instrument_name("san") == "Signal Analyzer"


def test_runner_assert_pass_and_report():
    runner = BenchRunner()
    lines = [
        '"check"',
        "assert bc.mm.measure_voltage 5.25 0.1",
    ]
    runner.run_script(lines, record_session=True)
    assert runner.session.pass_count == 1
    assert runner.session.verdict == "PASS"

    with tempfile.TemporaryDirectory() as td:
        jp = Path(td) / "report.json"
        runner.session.export_json(str(jp))
        data = json.loads(jp.read_text(encoding="utf-8"))
        assert data["schema"] == "testbench.session.v1"
        assert data["summary"]["pass"] == 1
