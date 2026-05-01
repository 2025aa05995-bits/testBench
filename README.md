Test Bench is a text-driven automation framework for lab instruments.

## Layout

- **`gui_chat.py`** — Run the GUI from the repo root (adds `src` to `PYTHONPATH` automatically).
- **`src/testbench/`** — Core package: registry, config, command parsing, plotting helpers, simulated instruments.
- **`config/testbenchconfig.json`** — Default instrument configuration.
- **`scripts/`** — Small runnable scripts (e.g. power-supply factory demo).
- **`tests/`** — Tests and manual check scripts.
- **`docs/BENCHCONFIG.md`** — Configuration reference.

## Quick start

```powershell
.\setup.bat
.\.venv\Scripts\python.exe .\gui_chat.py
```

Optional: `pip install -r requirements-hardware.txt` for VISA/serial (see `setup.bat`).
