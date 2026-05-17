"""Tests for simulated instrument mixin and ARB loading."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.instruments.multimeter.simulated import SimulatedMultimeter  # noqa: E402
from testbench.instruments.function_generator.simulated import SimulatedFunctionGenerator  # noqa: E402
from testbench.instruments.arb_waveform import load_waveform_csv  # noqa: E402
from testbench.config_manager import ConfigManager  # noqa: E402
from testbench.command_registry import CommandRegistry  # noqa: E402


def test_common_actions_reset_status():
    mm = SimulatedMultimeter()
    mm.connect()
    assert "reset" in mm.ACTIONS
    assert "status" in mm.ACTIONS
    mm.execute("reset", [])
    st = mm.execute("status", [])
    assert st["connected"] is True


def test_fault_inject_and_clear():
    mm = SimulatedMultimeter()
    mm.connect()
    mm.execute("fault_inject", ["disconnect"])
    try:
        mm.execute("measure_voltage", [])
        assert False, "expected fault"
    except RuntimeError as e:
        assert "disconnected" in str(e).lower()
    mm.execute("fault_clear", [])
    mm.connect()
    v = mm.execute("measure_voltage", [])
    assert isinstance(v, float)


def test_load_arb_csv(tmp_path):
    p = tmp_path / "wave.csv"
    p.write_text("0,0\n0.001,1\n0.002,0\n", encoding="utf-8")
    t, v = load_waveform_csv(str(p))
    assert len(t) == 3
    assert len(v) == 3

    fg = SimulatedFunctionGenerator()
    fg.connect()
    info = fg.execute("load_arb_csv", [str(p)])
    assert info["points"] == 3
    arb = fg.execute("get_arb", [])
    assert arb["points"] == 3


def test_config_bind(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    src = ROOT / "config" / "testbenchconfig.json"
    cfg_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    cm = ConfigManager(str(cfg_path))
    cm.bind_instrument("ps", "visa", "GPIB0::99::INSTR")
    assert cm.get_visa_resource("ps") == "GPIB0::99::INSTR"
