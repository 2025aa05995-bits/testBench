"""Script variable store and ``$name`` substitution."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

_VAR_REF_RE = re.compile(r"\$(\{)?([A-Za-z_][\w]*)\}?")


class VariableStore:
    """Holds named script variables (strings coerced at substitution time)."""

    def __init__(self) -> None:
        self._values: Dict[str, str] = {}

    def clear(self) -> None:
        self._values.clear()

    def set(self, name: str, value: Any) -> None:
        key = _normalize_name(name)
        if not key:
            raise ValueError("Variable name is required")
        self._values[key] = str(value).strip()

    def get(self, name: str) -> Optional[str]:
        return self._values.get(_normalize_name(name))

    def as_dict(self) -> Dict[str, str]:
        return dict(self._values)

    def substitute(self, text: str) -> str:
        """Replace ``$V`` / ``${V}`` with stored values."""

        def _repl(m: re.Match) -> str:
            name = m.group(2)
            if name not in self._values:
                raise ValueError(f"Undefined variable: ${name}")
            return self._values[name]

        return _VAR_REF_RE.sub(_repl, text or "")


def _normalize_name(name: str) -> str:
    n = (name or "").strip()
    if n.startswith("$"):
        n = n[1:]
    return n


def parse_set_command(line: str) -> Optional[tuple]:
    """
    Parse ``set $V 3.3`` or ``set V 3.3``.

    Returns ``(var_name, value_str)`` or ``None``.
    """
    s = (line or "").strip()
    if not s.lower().startswith("set "):
        return None
    rest = s[4:].strip()
    if not rest:
        raise ValueError("Usage: set <name> <value>")
    parts = rest.split(None, 1)
    if len(parts) < 2:
        raise ValueError("Usage: set <name> <value>")
    return _normalize_name(parts[0]), parts[1].strip()
