# Test Bench

## Overview

Test Bench is a **text-driven lab automation** toolkit for Windows (and other platforms with Python). You drive instruments with structured commands (`bench.*` or short alias `bc.*`), switch between **simulated** and **real** hardware via JSON config, and optionally use a **PyQt** desktop chat UI (`gui_chat.py`) or plain **Tkinter** if PyQt is unavailable.

The core lives in **`src/testbench/`**: a **command parser**, **command registry**, **config manager**, optional **matplotlib** plots, and **simulated** device classes per instrument family. Real devices use a generic **`RealInstrumentAdapter`** (VISA, TCP/IP, serial) with SCPI **`raw`** support.

---

## Functionality

| Area | What it does |
|------|----------------|
| **Commands** | `bench.<category>.<action> [args...]` or `bc.<category>.<action> [args...]`. Example: `bc.ps.on`, `bc.ps.set_voltage 3.3`. Type `help` or `help <category>` in the GUI. |
| **Instruments** | One **short category key** per device (e.g. `ps`, `osc`, `sg`). Each exposes an **`ACTIONS`** map and an **`execute(action, args)`** implementation. |
| **Simulation vs real** | If `simulate` is true for that category in config, a **simulated** class is used; if false, **`RealInstrumentAdapter`** handles connect/SCPI. Toggle at runtime with `bench.config.set_simulation <category> true\|false` (after reload). |
| **Config** | `bench.config.show`, `reload`, `discover`, `status` — see [docs/BENCHCONFIG.md](docs/BENCHCONFIG.md). |
| **GUI (`gui_chat.py`)** | Log + command composer, autocomplete, command history, **plots** (`plot bc...` or `plot "Label" bc...`), **sequences** (record/stop, categories, CSV plot logs under `logs/plot_data/`), **Settings** (Bench JSON editor, **Fonts**), menus, status line. |
| **Tests** | `pytest` under `tests/` (e.g. simulated instruments, help, autocomplete). |

**Registered instrument categories** (keys in `CommandRegistry.INSTRUMENT_FACTORIES`):  
`ps`, `osc`, `sg`, `sa`, `mm`, `fg`, `na`, `fc`, `el`, `smu`, `tc`, `pm` — plus virtual `config` for bench-wide settings.

---

## How to install

### Windows (recommended)

1. Install **Python 3.10+** (Microsoft Store or [python.org](https://www.python.org/downloads/)).
2. From the repo root, run **`setup.bat`**. It will:
   - create **`.venv`** if missing,
   - `pip install -r requirements.txt` (PyQt5, matplotlib, Pillow, dev tools),
   - optionally prompt to install **`requirements-hardware.txt`** (PyVISA, pyserial, etc.) for real instruments.
3. Start the UI:

   ```powershell
   .\.venv\Scripts\python.exe .\gui_chat.py
   ```

### Manual (any OS)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # Linux/macOS
pip install -r requirements-hardware.txt       # optional, for VISA/serial
python gui_chat.py
```

`gui_chat.py` prepends **`src`** to `sys.path` so `import testbench` works without installing the package.

---

## How to add new instruments

Adding a **new instrument family** (new category key) is a small, repeatable change set.

### 1. Implement the instrument package

Under **`src/testbench/instruments/<your_folder>/`**:

- **`base.py`** — optional abstract base (subclass `InstrumentBase` from `instruments/base.py`) declaring device-specific methods.
- **`simulated.py`** — **`SimulatedYourDevice`** class used when `simulate: true` in config. It should:
  - define **`ACTIONS`**: `dict` mapping each action name to a one-line description (drives `help`),
  - implement **`execute(self, action: str, args: list)`** — dispatch to methods; parse `args` as needed,
  - implement **`connect` / `disconnect` / `status`** (and any other behavior you need).

Follow an existing family (e.g. **`power_supply/simulated.py`**) as a template. More examples: [docs/SIMULATED_INSTRUMENTS.md](docs/SIMULATED_INSTRUMENTS.md).

### 2. Export from `instruments`

- Update **`src/testbench/instruments/__init__.py`**: import and re-export your base + `Simulated*` class in **`__all__`**.

### 3. Register in `CommandRegistry`

In **`src/testbench/command_registry.py`**:

- **Import** your `Simulated...` class at the top with the other instruments.
- Add a line to **`INSTRUMENT_FACTORIES`**:  
  `'<short_key>': SimulatedYourDevice,`  
  The **`<short_key>`** must match the key you will use in JSON and in commands (`bc.<short_key>.<action>`).

Optionally extend **`get_instrument_name()`** so `help` shows a friendly label for your category.

### 4. Add configuration

In **`config/testbenchconfig.json`**, under **`instruments`**, add a block for your **`<short_key>`** (copy shape from an existing entry): `name`, `simulate`, `type`, `protocol`, addresses, `timeout_ms`, etc. Details: [docs/BENCHCONFIG.md](docs/BENCHCONFIG.md).

### 5. Real hardware (optional)

You do **not** need a separate “real” Python class per model: with **`simulate: false`**, the registry instantiates **`RealInstrumentAdapter`**, which speaks SCPI over the configured **VISA / TCP/IP / Serial** transport. Use actions like **`bc.<key>.raw *IDN?`** for arbitrary commands, plus **`connect`**, **`disconnect`**, **`identify`**, **`status`**, **`reset`** as documented on that adapter.

### 6. Verify

Run **`pytest`**, exercise **`help <your_key>`** in the GUI, and try a few `bc.<your_key>.<action>` commands in simulation before switching to real mode.

---

## Repository layout

| Path | Role |
|------|------|
| **`gui_chat.py`** | GUI entry point (PyQt preferred; Tk fallback). |
| **`src/testbench/`** | Core package: parser, registry, config, plotting, instruments. |
| **`config/testbenchconfig.json`** | Default bench configuration. |
| **`config/gui_chat_fonts.json`** | Optional UI font overrides (created from **Settings → Fonts**). |
| **`config/test_sequences.json`** | Saved command sequences (GUI). |
| **`logs/plot_data/`** | CSV logs for large plot series. |
| **`assets/`** | Application icon (`lab_chat_icon.png` / `.ico`). |
| **`docs/`** | **BENCHCONFIG.md**, **SIMULATED_INSTRUMENTS.md**, etc. |
| **`tests/`** | Automated tests. |

---

## Quick reference (GUI)

```powershell
.\setup.bat
.\.venv\Scripts\python.exe .\gui_chat.py
```

Optional hardware stack: install **`requirements-hardware.txt`** when prompted by `setup.bat`, or `pip install -r requirements-hardware.txt` manually.
