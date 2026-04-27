#!/usr/bin/env python3
"""Test autocomplete functionality."""

from gui_chat import CommandCompleter
from testbench.command_registry import CommandRegistry
from command_parser import CommandParser, handle_help
import sys
sys.path.insert(0, 'src')


def test_autocomplete():
    """Test command completion suggestions."""
    print("=" * 70)
    print("TESTING AUTOCOMPLETE FUNCTIONALITY")
    print("=" * 70)

    registry = CommandRegistry()
    completer = CommandCompleter(registry)

    # Test cases
    test_cases = [
        ("bench.", "Show all commands"),
        ("bench.ps", "Power supply commands"),
        ("bench.ps.s", "Commands starting with 's'"),
        ("bench.mm.m", "Multimeter measure commands"),
        ("bench.osc.r", "Oscilloscope run/stop"),
    ]

    for partial, description in test_cases:
        print(f"\nInput: '{partial}' ({description})")
        print("-" * 70)
        suggestions = completer.get_suggestions(partial)
        if suggestions:
            for i, suggestion in enumerate(suggestions, 1):
                print(f"  {i}. {suggestion}")
        else:
            print("  (No suggestions)")

    print("\n" + "=" * 70)
    print("AUTOCOMPLETE TEST COMPLETED")
    print("=" * 70)


if __name__ == '__main__':
    test_autocomplete()
