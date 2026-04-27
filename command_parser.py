import re
from typing import Optional, Dict


class CommandParser:
    def parse(self, command: str):
        # Example: bench.ps.on True or bench.ps.setVoltage 12
        pattern = r"^(\w+)\.(\w+)\.(\w+)(?:\s+(.*))?$"
        match = re.match(pattern, command.strip())
        if not match:
            return None
        top, category, action, args = match.groups()
        args = args.split() if args else []
        return {
            'top': top,
            'category': category,
            'action': action,
            'args': args
        }


def handle_help(args: list, registry) -> str:
    """Handle help command to show available commands.

    Args:
        args: Command arguments (empty for all help, or [category] for specific help)
        registry: CommandRegistry instance

    Returns:
        Formatted help text
    """
    if not args:
        # Show all commands
        return _format_all_commands(registry)
    else:
        # Show commands for specific instrument
        category = args[0].lower()
        return _format_instrument_commands(category, registry)


def _format_all_commands(registry) -> str:
    """Format help text showing all available commands."""
    all_commands = registry.get_all_commands()

    if not all_commands:
        return "No commands available."

    lines = ["Available Commands:\n"]

    for category in sorted(all_commands.keys()):
        instrument_name = registry.get_instrument_name(category)
        display_name = f"{instrument_name} ({category})" if instrument_name else category
        lines.append(f"\n{display_name}:")

        actions = all_commands[category]
        for action, description in sorted(actions.items()):
            lines.append(f"  {action:<20} {description}")

    return "\n".join(lines)


def _format_instrument_commands(category: str, registry) -> str:
    """Format help text for a specific instrument."""
    commands = registry.get_instrument_commands(category)

    if commands is None:
        return f"Unknown instrument: {category}\n\nUse 'help' to see all available instruments."

    instrument_name = registry.get_instrument_name(category)
    display_name = f"{instrument_name} ({category})" if instrument_name else category

    lines = [f"Commands for {display_name}:\n"]

    for action, description in sorted(commands.items()):
        lines.append(f"  {action:<20} {description}")

    return "\n".join(lines)


# Example usage
if __name__ == "__main__":
    parser = CommandParser()
    print(parser.parse("bench.ps.on True"))
    print(parser.parse("bench.ps.setVoltage 12"))
