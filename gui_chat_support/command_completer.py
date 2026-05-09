"""Autocomplete suggestions for bench./bc. commands."""

import re


class CommandCompleter:
    """Helper class to generate autocomplete suggestions."""

    def __init__(self, registry):
        self.registry = registry
        self.all_commands = self._build_command_list()

    def _build_command_list(self):
        """Build list of commands in 'bench.<category>.<action>' or 'bc.<category>.<action>' format."""
        tops = ["bench", "bc"]
        commands = []
        for category, actions in self.registry.get_all_commands().items():
            for action in actions.keys():
                for top in tops:
                    commands.append(f"{top}.{category}.{action}")
        return sorted(set(commands))

    def get_suggestions(self, partial_input: str, max_suggestions: int = 10) -> list:
        """Get autocomplete suggestions for the given partial input."""
        text = partial_input.strip()
        if not text:
            return self.all_commands[:max_suggestions]

        last_fragment = re.split(r"[;\n\r]+", text)[-1].strip().lower()
        if not last_fragment:
            return self.all_commands[:max_suggestions]

        suggestions = [cmd for cmd in self.all_commands if cmd.lower().startswith(last_fragment)]
        return suggestions[:max_suggestions]
