"""Load arbitrary waveform data from CSV for simulated function generators."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Tuple


def load_waveform_csv(path: str) -> Tuple[List[float], List[float]]:
    """
    Load waveform from CSV.

    Accepts:
    - One column: voltage samples (time implied as 0..n-1)
    - Two+ columns: first = time, second = voltage (header row skipped if non-numeric)

    Returns ``(times, voltages)``.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Waveform file not found: {path}")

    rows: List[List[str]] = []
    with p.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or all(not c.strip() for c in row):
                continue
            rows.append([c.strip() for c in row])

    if not rows:
        raise ValueError(f"Empty waveform CSV: {path}")

    def _floats(cells: List[str]) -> List[float]:
        return [float(c) for c in cells]

    try:
        if len(rows[0]) == 1:
            v = _floats([r[0] for r in rows])
            t = [float(i) for i in range(len(v))]
            return t, v
        t = _floats([r[0] for r in rows])
        v = _floats([r[1] for r in rows])
        return t, v
    except ValueError:
        # skip header row
        if len(rows) < 2:
            raise ValueError(f"Could not parse waveform CSV: {path}") from None
        try:
            if len(rows[1]) == 1:
                v = _floats([r[0] for r in rows[1:]])
                t = [float(i) for i in range(len(v))]
                return t, v
            t = _floats([r[0] for r in rows[1:]])
            v = _floats([r[1] for r in rows[1:]])
            return t, v
        except ValueError as e:
            raise ValueError(f"Could not parse waveform CSV: {path}") from e
