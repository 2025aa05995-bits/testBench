"""Render measurement values as PNG plots (scalar, 1D, or 2D series)."""

from __future__ import annotations

import math
import numbers
import re
from io import BytesIO
from typing import Any, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


def try_extract_plot_command(command: str) -> Optional[str]:
    """If command is ``plot(...)`` or ``plot <bench command>``, return the bench command stripped."""
    s = command.strip()
    if not s:
        return None
    # Parentheses form first so ``plot ( bc.x )`` is not treated as space form.
    m = re.match(r"^\s*plot\s*\(\s*(.+)\s*\)\s*$", s, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    m2 = re.match(r"(?i)^plot\s+(.+)$", s)
    if m2:
        return m2.group(1).strip()
    return None


def _as_float_list(seq: Any) -> List[float]:
    return [float(x) for x in seq]


def _dict_xy(d: dict) -> Optional[Tuple[List[float], List[float], str, str, str, str]]:
    lower = {str(k).lower(): v for k, v in d.items()}
    pairs = [
        (("time_s", "voltage_v"), "Time (s)", "Voltage (V)"),
        (("time", "voltage"), "Time (s)", "Voltage (V)"),
        (("t", "v"), "Time (s)", "Voltage (V)"),
        (("x", "y"), "x", "y"),
    ]
    for (kx, ky), xlab, ylab in pairs:
        if kx in lower and ky in lower:
            xv, yv = lower[kx], lower[ky]
            if isinstance(xv, (list, tuple)) and isinstance(yv, (list, tuple)):
                title = f"{xlab} vs {ylab}"
                return _as_float_list(xv), _as_float_list(yv), "line", title, xlab, ylab
    return None


def normalize_plot_series(value: Any) -> Tuple[List[float], List[float], str, str, str, str]:
    """
    Returns x, y, plot_kind ('line'|'bar'|'scatter'), title_suffix, xlabel, ylabel.
    """
    if value is None:
        raise ValueError("Plot data is None")

    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return [0.0], [float(value)], "bar", "scalar", "", "value"

    if isinstance(value, dict):
        got = _dict_xy(value)
        if got:
            xs, ys, kind, title, xlab, ylab = got
            if len(xs) != len(ys):
                raise ValueError(f"x and y length mismatch: {len(xs)} vs {len(ys)}")
            return xs, ys, kind, title, xlab, ylab
        raise ValueError("Dict plot data needs keys like (time_s, voltage_v) or (x, y)")

    if isinstance(value, (list, tuple)):
        if value and all(isinstance(row, (list, tuple)) and len(row) == 2 for row in value):
            if all(
                isinstance(row[0], numbers.Real) and isinstance(row[1], numbers.Real)
                for row in value
            ):
                xs = _as_float_list([row[0] for row in value])
                ys = _as_float_list([row[1] for row in value])
                return xs, ys, "line", "series", "x", "y"

        if len(value) == 2:
            a, b = value[0], value[1]
            if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
                if all(isinstance(x, numbers.Real) for x in a) and all(isinstance(x, numbers.Real) for x in b):
                    xs, ys = _as_float_list(a), _as_float_list(b)
                    if len(xs) != len(ys):
                        raise ValueError(f"x and y length mismatch: {len(xs)} vs {len(ys)}")
                    return xs, ys, "line", "series", "x", "y"

        if all(isinstance(x, numbers.Real) for x in value):
            ys = _as_float_list(value)
            xs = list(range(len(ys)))
            return xs, ys, "line", "1D series", "index", "value"

    if np is not None and isinstance(value, np.ndarray):
        if value.ndim == 1:
            ys = value.astype(float).tolist()
            xs = list(range(len(ys)))
            return xs, ys, "line", "1D array", "index", "value"
        if value.ndim == 2 and value.shape[1] == 2:
            xs = value[:, 0].astype(float).tolist()
            ys = value[:, 1].astype(float).tolist()
            return xs, ys, "line", "2-column array", "x", "y"

    raise ValueError(f"Unsupported plot data type: {type(value).__name__}")


def render_plot_to_png_bytes(
    value: Any,
    *,
    figsize: Tuple[float, float] = (6.0, 3.0),
    dpi: int = 100,
    max_points: int = 50_000,
) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xs, ys, kind, title_suffix, xlab, ylab = normalize_plot_series(value)
    if len(xs) > max_points:
        step = math.ceil(len(xs) / max_points)
        xs = xs[::step]
        ys = ys[::step]

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    if kind == "bar":
        ax.bar([0], ys, width=0.35, color="steelblue")
        ax.set_xticks([0])
        ax.set_xticklabels(["value"])
        if xlab and xlab.strip():
            ax.set_xlabel(xlab)
        ax.set_ylabel(ylab or "value")
    else:
        ax.plot(xs, ys, "-", linewidth=1.2, color="steelblue")
        ax.set_xlabel(xlab or "x")
        ax.set_ylabel(ylab or "y")
    ax.set_title(title_suffix)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
