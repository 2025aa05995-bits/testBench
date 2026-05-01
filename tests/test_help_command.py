#!/usr/bin/env python3
"""Quick test script to verify help command and command execution."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from testbench.command_parser import CommandParser, handle_help  # noqa: E402
from testbench.command_registry import CommandRegistry  # noqa: E402


def test_help_command():
    """Test the help command functionality."""
    print("=" * 70)
    print("TESTING HELP COMMAND FUNCTIONALITY")
    print("=" * 70)

    registry = CommandRegistry()

    # Test 1: Help all
    print("\nTest 1: 'help' (show all commands)")
    print("-" * 70)
    help_text = handle_help([], registry)
    print(help_text)

    # Test 2: Help for specific instrument
    print("\n\nTest 2: 'help ps' (power supply commands)")
    print("-" * 70)
    help_text = handle_help(['ps'], registry)
    print(help_text)

    # Test 3: Help for specific instrument (multimeter)
    print("\n\nTest 3: 'help mm' (multimeter commands)")
    print("-" * 70)
    help_text = handle_help(['mm'], registry)
    print(help_text)

    # Test 4: Invalid instrument
    print("\n\nTest 4: 'help invalid' (invalid instrument)")
    print("-" * 70)
    help_text = handle_help(['invalid'], registry)
    print(help_text)


def test_command_execution():
    """Test command parsing and execution."""
    print("\n\n" + "=" * 70)
    print("TESTING COMMAND EXECUTION")
    print("=" * 70)

    parser = CommandParser()
    registry = CommandRegistry()

    # Test valid command with bench alias
    print("\nTest 1: Parse 'bench.ps.on True'")
    print("-" * 70)
    parsed = parser.parse("bench.ps.on True")
    print(f"Parsed: {parsed}")
    if parsed:
        try:
            result = registry.execute(
                parsed['category'], parsed['action'], parsed['args'])
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")

    # Test another command with bc alias
    print("\n\nTest 2: Parse 'bc.ps.setVoltage 12.5'")
    print("-" * 70)
    parsed = parser.parse("bc.ps.setVoltage 12.5")
    print(f"Parsed: {parsed}")
    if parsed:
        try:
            result = registry.execute(
                parsed['category'], parsed['action'], parsed['args'])
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")

    # Test measurement
    print("\n\nTest 3: Parse 'bench.mm.measure_voltage'")
    print("-" * 70)
    parsed = parser.parse("bench.mm.measure_voltage")
    print(f"Parsed: {parsed}")
    if parsed:
        try:
            result = registry.execute(
                parsed['category'], parsed['action'], parsed['args'])
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")

    # Test invalid command
    print("\n\nTest 4: Parse invalid command 'invalid.command'")
    print("-" * 70)
    parsed = parser.parse("invalid.command")
    print(f"Parsed: {parsed}")

    # Test invalid category
    print("\n\nTest 5: Execute command with invalid category 'bench.invalid.test'")
    print("-" * 70)
    parsed = parser.parse("bench.invalid.test")
    print(f"Parsed: {parsed}")
    if parsed:
        try:
            result = registry.execute(
                parsed['category'], parsed['action'], parsed['args'])
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == '__main__':
    test_help_command()
    test_command_execution()
    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)
