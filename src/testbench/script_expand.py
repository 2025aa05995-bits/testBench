"""Expand ``for`` / ``endfor`` blocks and apply variable substitution."""

from __future__ import annotations

import re
from typing import List

from .variables import VariableStore, parse_set_command

_FOR_RE = re.compile(
    r"^\s*for\s+(\$?[A-Za-z_][\w]*)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*$",
    re.IGNORECASE,
)
_END_RE = re.compile(r"^\s*(endfor|end)\s*$", re.IGNORECASE)


def _frange(start: float, stop: float, step: float) -> List[float]:
    if step == 0:
        raise ValueError("for-loop step cannot be zero")
    values: List[float] = []
    n = 0
    max_iter = 1_000_000
    if step > 0:
        v = start
        while v <= stop + abs(step) * 1e-9:
            values.append(v)
            n += 1
            if n > max_iter:
                raise ValueError("for-loop exceeded maximum iterations")
            v = start + n * step
    else:
        v = start
        while v >= stop - abs(step) * 1e-9:
            values.append(v)
            n += 1
            if n > max_iter:
                raise ValueError("for-loop exceeded maximum iterations")
            v = start + n * step
    return values


def expand_script_lines(lines: List[str], variables: VariableStore) -> List[str]:
    """
    Expand ``for`` … ``endfor`` blocks and apply ``$var`` substitution.

    ``set`` lines update ``variables`` and are not emitted.
    """
    return _process_lines(lines, variables)


def _process_lines(lines: List[str], variables: VariableStore) -> List[str]:
    out: List[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if not line or line.startswith("#"):
            i += 1
            continue

        if line.lower().startswith("set "):
            name, value = parse_set_command(line)
            variables.set(name, variables.substitute(value))
            i += 1
            continue

        m = _FOR_RE.match(line)
        if m:
            var_name = m.group(1).lstrip("$")
            start = float(m.group(2))
            stop = float(m.group(3))
            step = float(m.group(4))
            body, i = _read_loop_body(lines, i + 1)
            for val in _frange(start, stop, step):
                variables.set(var_name, _format_loop_value(val))
                out.extend(_process_lines(body, variables))
            continue

        if _END_RE.match(line):
            raise ValueError(f"Unexpected {line} (no matching for)")

        out.append(variables.substitute(raw.strip()))
        i += 1
    return out


def _read_loop_body(lines: List[str], start_index: int) -> tuple:
    body: List[str] = []
    i = start_index
    depth = 0
    while i < len(lines):
        inner = lines[i]
        inner_s = inner.strip()
        if _FOR_RE.match(inner_s):
            depth += 1
            body.append(inner)
            i += 1
            continue
        if _END_RE.match(inner_s):
            if depth == 0:
                return body, i + 1
            depth -= 1
            body.append(inner)
            i += 1
            continue
        body.append(inner)
        i += 1
    raise ValueError("Unclosed for-loop (missing endfor)")


def _format_loop_value(val: float) -> str:
    if abs(val - round(val)) < 1e-9:
        return str(int(round(val)))
    return repr(val)
