"""Tests for chat input heuristics."""

from gui_chat_support.command_helpers import looks_like_direct_command


def test_natural_language_set_supply_is_not_direct():
    prompt = (
        "Set the supply to 3.3 V, turn it on, and verify the output voltage "
        "is between 3.0 and 3.6 V"
    )
    assert not looks_like_direct_command(prompt)


def test_set_variable_commands_are_direct():
    assert looks_like_direct_command("set $Vnom 3.3")
    assert looks_like_direct_command("set VNOM 3.3")
    assert looks_like_direct_command("set v_nom 3.3")


def test_bench_commands_are_direct():
    assert looks_like_direct_command("bc.ps.set_voltage 3.3")
    assert looks_like_direct_command("bench.ps.on")
