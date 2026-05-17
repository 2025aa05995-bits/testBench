#!/usr/bin/env python3
"""Legacy entry point — delegates to ``python -m testbench``."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.__main__ import main  # noqa: E402

if __name__ == "__main__":
    # ``bench.py run script.bench`` → same as ``python -m testbench run script.bench``
    raise SystemExit(main())
