"""Render measurement values as PNG plots (scalar, 1D, or 2D series)."""

from __future__ import annotations

import csv
import math
import numbers
import os
import re
from datetime import datetime
from io import BytesIO
from typing import Any, List, Optional, Tuple

from testbench._paths import repo_root

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


def try_extract_plot_command(command: str) -> Optional[Tuple[Optional[str], str]]:
    """
    If the line is a plot command, return ``(csv_name_label_or_None, bench_command_inner)``.

    Forms:

    - ``plot(inner)`` → ``(None, inner)``
    - ``plot "My Label" bc.osc.get_trace 1`` → ``("My Label", "bc.osc.get_trace 1")``
    - ``plot 'My Label' bc.x`` → same with single quotes
    - ``plot bc.x`` → ``(None, "bc.x")``
    """
    s = command.strip()
    if not s:
        return None
    # Parentheses form first so ``plot ( bc.x )`` is not treated as space form.
    m = re.match(r"^\s*plot\s*\(\s*(.+)\s*\)\s*$", s, re.IGNORECASE | re.DOTALL)
    if m:
        return None, m.group(1).strip()
    # Quoted CSV / log name, then bench command (double quotes)
    mq = re.match(r'(?i)^plot\s+"([^"]*)"\s+(.+)$', s)
    if mq:
        label = mq.group(1).strip() or None
        return label, mq.group(2).strip()
    mq2 = re.match(r"(?i)^plot\s+'([^']*)'\s+(.+)$", s)
    if mq2:
        label = mq2.group(1).strip() or None
        return label, mq2.group(2).strip()
    m2 = re.match(r"(?i)^plot\s+(.+)$", s)
    if m2:
        return None, m2.group(1).strip()
    return None


def _as_float_list(seq: Any) -> List[float]:
    return [float(x) for x in seq]


def _truncate_to_common_length(
    xs: List[Any], ys: List[Any], ticks: Optional[List[str]] = None
) -> Tuple[List[Any], List[Any], List[str]]:
    """Trim ``xs``/``ys`` (and optional ``ticks``) to the shortest length so a
    mismatched series (common when an LLM returns truncated arrays) still plots.
    """
    n = min(len(xs), len(ys))
    if ticks:
        n = min(n, len(ticks))
        ticks = list(ticks)[:n]
    else:
        ticks = []
    return list(xs)[:n], list(ys)[:n], ticks


def _coerce_xy_for_plot(xv: Any, yv: Any) -> Optional[Tuple[List[float], List[float], List[str]]]:
    """
    Return ``(xs, ys, x_tick_labels)`` if ``xv``/``yv`` can plot together.

    ``x_tick_labels`` is non-empty only when ``xv`` is a list of strings
    (e.g. categorical labels for a bar chart); in that case ``xs`` is
    ``[0, 1, ..., n-1]`` and the labels are used for axis ticks.

    If ``xv`` and ``yv`` have different lengths, both are trimmed to the
    shortest length so callers can still render a (possibly truncated) plot.
    """
    if not isinstance(xv, (list, tuple)) or not isinstance(yv, (list, tuple)):
        return None
    if not all(isinstance(v, numbers.Real) and not isinstance(v, bool) for v in yv):
        return None
    if all(isinstance(v, numbers.Real) and not isinstance(v, bool) for v in xv):
        xs_f, ys_f, _ = _truncate_to_common_length(_as_float_list(xv), _as_float_list(yv))
        return xs_f, ys_f, []
    if all(isinstance(v, str) for v in xv):
        labels = [str(v) for v in xv]
        ys_f = _as_float_list(yv)
        n = min(len(labels), len(ys_f))
        labels = labels[:n]
        ys_f = ys_f[:n]
        return list(range(n)), ys_f, labels
    return None


def _dict_xy(d: dict) -> Optional[Tuple[List[float], List[float], str, str, str, str, List[str]]]:
    lower = {str(k).lower(): v for k, v in d.items()}
    pairs = [
        (("time_s", "voltage_v"), "Time (s)", "Voltage (V)"),
        (("time", "voltage"), "Time (s)", "Voltage (V)"),
        (("t", "v"), "Time (s)", "Voltage (V)"),
        (("frequencies", "data"), "Frequency (Hz)", "Power (dBm)"),
        (("frequency_hz", "power_dbm"), "Frequency (Hz)", "Power (dBm)"),
        (("x", "y"), "x", "y"),
    ]
    for (kx, ky), xlab, ylab in pairs:
        if kx in lower and ky in lower:
            coerced = _coerce_xy_for_plot(lower[kx], lower[ky])
            if coerced is None:
                continue
            xs, ys, ticks = coerced
            title = f"{xlab} vs {ylab}"
            return xs, ys, "line", title, xlab, ylab, ticks
    return None


def _apply_llm_overrides(
    value: dict,
    xs: List[float],
    ys: List[float],
    kind: str,
    title: str,
    xlab: str,
    ylab: str,
    xticks: List[str],
) -> Tuple[List[float], List[float], str, str, str, str, List[str]]:
    """Apply optional ``title``/``xlabel``/``ylabel``/``kind`` overrides from an LLM plot spec dict."""
    lower = {str(k).lower(): v for k, v in value.items()}
    title_v = lower.get("title")
    if isinstance(title_v, str) and title_v.strip():
        title = title_v.strip()
    xlab_v = lower.get("xlabel", lower.get("x_label"))
    if isinstance(xlab_v, str) and xlab_v.strip():
        xlab = xlab_v.strip()
    ylab_v = lower.get("ylabel", lower.get("y_label"))
    if isinstance(ylab_v, str) and ylab_v.strip():
        ylab = ylab_v.strip()
    kind_v = lower.get("kind")
    if isinstance(kind_v, str) and kind_v.strip().lower() in {"line", "bar", "scatter"}:
        kind = kind_v.strip().lower()
    return xs, ys, kind, title, xlab, ylab, xticks


def normalize_plot_series(
    value: Any,
) -> Tuple[List[float], List[float], str, str, str, str, List[str]]:
    """
    Returns ``(x, y, plot_kind, title_suffix, xlabel, ylabel, xticks)`` where
    ``plot_kind`` is one of ``'line'|'bar'|'scatter'`` and ``xticks`` is a
    (possibly empty) list of categorical x-tick labels (used for bar charts
    when the LLM supplies string labels in ``x``).
    """
    if value is None:
        raise ValueError("Plot data is None")

    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return [0.0], [float(value)], "bar", "scalar", "", "value", ["value"]

    if isinstance(value, dict):
        got = _dict_xy(value)
        if got:
            xs, ys, kind, title, xlab, ylab, xticks = got
            xs, ys, xticks = _truncate_to_common_length(xs, ys, xticks)
            return _apply_llm_overrides(value, xs, ys, kind, title, xlab, ylab, xticks)
        raise ValueError("Dict plot data needs keys like (time_s, voltage_v) or (x, y)")

    if isinstance(value, (list, tuple)):
        if value and all(isinstance(row, (list, tuple)) and len(row) == 2 for row in value):
            if all(
                isinstance(row[0], numbers.Real) and isinstance(row[1], numbers.Real)
                for row in value
            ):
                xs = _as_float_list([row[0] for row in value])
                ys = _as_float_list([row[1] for row in value])
                return xs, ys, "line", "series", "x", "y", []

        if len(value) == 2:
            a, b = value[0], value[1]
            if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
                if all(isinstance(x, numbers.Real) for x in a) and all(isinstance(x, numbers.Real) for x in b):
                    xs, ys = _as_float_list(a), _as_float_list(b)
                    xs, ys, _ = _truncate_to_common_length(xs, ys)
                    return xs, ys, "line", "series", "x", "y", []

        if all(isinstance(x, numbers.Real) for x in value):
            ys = _as_float_list(value)
            xs = list(range(len(ys)))
            return xs, ys, "line", "1D series", "index", "value", []

    if np is not None and isinstance(value, np.ndarray):
        if value.ndim == 1:
            ys = value.astype(float).tolist()
            xs = list(range(len(ys)))
            return xs, ys, "line", "1D array", "index", "value", []
        if value.ndim == 2 and value.shape[1] == 2:
            xs = value[:, 0].astype(float).tolist()
            ys = value[:, 1].astype(float).tolist()
            return xs, ys, "line", "2-column array", "x", "y", []

    raise ValueError(f"Unsupported plot data type: {type(value).__name__}")


def should_log_plot_data_as_csv(value: Any) -> bool:
    """True for 1D/2D series data; False for scalar and unplottable values."""
    try:
        xs, ys, kind, _t, _xl, _yl, _ticks = normalize_plot_series(value)
    except (ValueError, TypeError):
        return False
    if kind == "bar" and len(ys) == 1:
        return False
    return len(xs) > 0


def _sanitize_plot_csv_filename_label(label: str, max_len: int = 80) -> str:
    """Make a safe single path component from user text (e.g. ``Test Data`` → ``Test_Data``)."""
    bad = set('<>:"/\\|?*\n\r\t')
    out = []
    for ch in (label or "").strip():
        if ch in bad or ord(ch) < 32:
            out.append("_")
        elif ch == " ":
            out.append("_")
        else:
            out.append(ch)
    s = "".join(out).strip("._")
    while "__" in s:
        s = s.replace("__", "_")
    s = s[:max_len].strip("_")
    return s or "plot_data"


def plot_data_csv_path(file_label: Optional[str] = None) -> str:
    """Timestamped CSV path under ``<repo>/logs/plot_data/``; optional *file_label* prefixes the stem."""
    base = repo_root() / "logs" / "plot_data"
    os.makedirs(base, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    if file_label and str(file_label).strip():
        stem = _sanitize_plot_csv_filename_label(str(file_label))
        return str(base / f"{stem}_{ts}.csv")
    return str(base / f"plot_data_{ts}.csv")


def default_plot_data_csv_path() -> str:
    """Same as ``plot_data_csv_path()`` with no label (backward compatible)."""
    return plot_data_csv_path(None)


def write_plot_series_csv(value: Any, out_path: str) -> Tuple[str, str, int]:
    """
    Write normalized x/y series to CSV. Returns (x_column_header, y_column_header, row_count).
    """
    xs, ys, _kind, _title, xlab, ylab, _ticks = normalize_plot_series(value)
    xcol = (xlab or "x").strip() or "x"
    ycol = (ylab or "y").strip() or "y"
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([xcol, ycol])
        for i in range(len(xs)):
            w.writerow([xs[i], ys[i]])
    return xcol, ycol, len(xs)


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

    xs, ys, kind, title_suffix, xlab, ylab, xticks = normalize_plot_series(value)
    if len(xs) > max_points:
        step = math.ceil(len(xs) / max_points)
        xs = xs[::step]
        ys = ys[::step]
        if xticks and len(xticks) > max_points:
            xticks = xticks[::step]

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    if kind == "bar":
        ax.bar(xs, ys, width=0.6, color="steelblue")
        if xticks:
            ax.set_xticks(xs)
            ax.set_xticklabels(xticks, rotation=20 if len(xticks) > 4 else 0, ha="right")
        elif len(ys) == 1:
            ax.set_xticks([0])
            ax.set_xticklabels(["value"])
        if xlab and xlab.strip():
            ax.set_xlabel(xlab)
        ax.set_ylabel(ylab or "value")
    elif kind == "scatter":
        ax.scatter(xs, ys, s=18, color="steelblue")
        ax.set_xlabel(xlab or "x")
        ax.set_ylabel(ylab or "y")
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
