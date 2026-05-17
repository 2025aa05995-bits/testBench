# Test Bench

## Overview

Test Bench is a **text-driven lab automation** toolkit for Windows (and other platforms with Python). You drive instruments with structured commands (`bench.*` or short alias `bc.*`), switch between **simulated** and **real** hardware via JSON config, run **automated pass/fail checks**, and optionally use a **PyQt** desktop chat UI (`gui_chat.py`) with **LLM-assisted** planning. Tkinter is used if PyQt is unavailable.

The core lives in **`src/testbench/`**: command parser, registry, config manager, script runner, session reports, optional **matplotlib** plots, **RAG** for lab documents, **multi-provider LLM** integration, and **simulated** device classes per instrument family. Real devices use a generic **`RealInstrumentAdapter`** (VISA, TCP/IP, serial) with SCPI **`raw`** support.

---

## Functionality

| Area | What it does |
|------|----------------|
| **Commands** | `bench.<category>.<action> [args...]` or `bc.<category>.<action> [args...]`. Example: `bc.ps.on`, `bc.ps.set_voltage 3.3`. Type `help` or `help <category>` in the GUI. |
| **Instruments** | One **short category key** per device (e.g. `ps`, `osc`, `sg`). Each exposes an **`ACTIONS`** map and an **`execute(action, args)`** implementation. |
| **Simulation vs real** | If `simulate` is true for that category in config, a **simulated** class is used; if false, **`RealInstrumentAdapter`** handles connect/SCPI. Toggle at runtime with `bench.config.set_simulation <category> true\|false` (after reload). |
| **Config** | `bench.config.show`, `reload`, `discover`, `status` — see [docs/BENCHCONFIG.md](docs/BENCHCONFIG.md). |
| **Assert / limit** | Automated **PASS/FAIL** on numeric measurements: `assert` (expected ± tolerance) and `limit` (min/max). Works in the GUI, saved sequences, and headless scripts. |
| **Script variables & sweeps** | `set $V 3.3`, substitute `$V` in commands, and `for V start stop step` … `endfor` blocks (expanded before run). |
| **Headless runner** | `python -m testbench run script.bench` — no GUI; optional JSON/HTML **session reports**. |
| **GUI (`gui_chat.py`)** | Log + command composer, autocomplete, history, **plots**, **sequences** (record/save/run), **LLM** Plan/Agent modes, **Settings** (bench JSON, fonts, LLM), status line. |
| **LLM** | Natural language → proposed `bc.*` command lists; **Plan** (review then `run` / `discard`) or **Agent** (execute when safe). Post-run **analyze** with optional plots. |
| **RAG** | TF–IDF index over `rag_docs/` injects SOP/datasheet context into LLM prompts. Chat: `rag`, `rag reload`, `rag status`. |
| **Simulation extras** | All sim drivers: `reset`, `status`, `identify`, fault injection, measurement noise, settling delay. FG: **ARB CSV** waveforms. **Bench → Bind** maps discovered VISA/serial/TCP addresses to config. |
| **Tests** | `pytest` under `tests/` (instruments, help, LLM parsing, RAG, runner, assert/limit, simulated mixin). |

**Registered instrument categories** (`CommandRegistry.INSTRUMENT_FACTORIES`):

| Key | Instrument | Notes |
|-----|------------|--------|
| `ps` | Power supply | |
| `osc` | Oscilloscope | |
| `sg` | Signal generator | |
| `sa` | Spectrum analyzer | Frequency sweeps, traces |
| `san` | Signal analyzer | Distinct from `sa` |
| `mm` | Multimeter | |
| `fg` | Function generator | |
| `na` | Network analyzer | |
| `fc` | Frequency counter | |
| `el` | Electronic load | |
| `smu` | Source measure unit | |
| `tc` | Temperature chamber | |
| `pm` | Power meter | |
| `config` | Bench settings | Virtual category (not hardware) |

---

## How to install

### Windows (recommended)

1. Install **Python 3.10+** (3.12 recommended). Use [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.12`. Avoid selecting a Python version in `py` that is not actually installed.
2. From the repo root, run **`setup.bat`**. It will:
   - create **`.venv`** if missing,
   - `pip install -r requirements.txt` (PyQt5, matplotlib, Pillow, openai, llama-cpp-python, dev tools),
   - optionally prompt to install **`requirements-hardware.txt`** (PyVISA, pyserial) for real instruments.
3. Start the UI:

   ```powershell
   .\run_gui.bat
   # or:
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

## Scripting and test automation

Scripts are plain text (`.bench`, `.txt`, `.script`, `.cmd`). Lines starting with `#` are comments. The same syntax works in the GUI command box and in saved **Test Sequence** menus (loops are expanded when a sequence starts).

### Headless CLI

```powershell
cd C:\git\testBench
$env:PYTHONPATH = "src"

# Run a script file
.\.venv\Scripts\python.exe -m testbench run scripts\examples\dmm_check.bench

# Inline commands
.\.venv\Scripts\python.exe -m testbench run -c "assert bc.mm.measure_voltage 5.25 0.1"

# Session reports (JSON + HTML); exit code 1 on FAIL
.\.venv\Scripts\python.exe -m testbench run scripts\examples\dmm_check.bench `
  --report logs\last_run.json --report-html logs\last_run.html

# Custom config path
.\.venv\Scripts\python.exe -m testbench run my_test.bench --config config\my_bench.json -q
```

`scripts/bench.py` is a thin wrapper around `python -m testbench`.

### Assert and limit

Run a bench command, then check the numeric result (or a dict field):

```text
assert bc.mm.measure_voltage 5.25 0.1
assert bc.mm.measure_voltage expected=5.25 tolerance=0.1

limit bc.mm.measure_voltage 5.0 5.5
limit bc.mm.measure_voltage min=5.0 max=5.5
limit bc.ps.status field=voltage_v min=3.0 max=3.6
```

Output is `PASS:` or `FAIL:`; headless runs print a final **Verdict** and set exit code **1** if any step failed or errored.

### Variables and sweeps

```text
set $Vnom 3.3
bc.ps.set_voltage $Vnom

for V 3.0 3.6 0.2
  bc.ps.set_voltage $V
  limit bc.ps.measure_voltage min=2.9 max=3.7
endfor
```

`end` is an alias for `endfor`. Nested `for` blocks are supported.

### Other script keywords

| Keyword | Example |
|---------|---------|
| `delay` | `delay 2` — pause seconds (GUI sequences use a Stop button during delay) |
| `"heading"` | `"Power-up sequence"` — section title in log/report |
| `help` | `help` / `help ps` |
| `plot` | `plot bc.osc.get_trace 1` — same as GUI |

### Session reports

Each headless run records steps with status `ok`, `pass`, `fail`, `error`, or `heading`. Exports use schema **`testbench.session.v1`** (JSON) or a summary HTML table (`--report` / `--report-html`).

Examples: [scripts/examples/dmm_check.bench](scripts/examples/dmm_check.bench), [scripts/examples/voltage_sweep.bench](scripts/examples/voltage_sweep.bench).

Simulated instruments, faults, ARB, and `sa` vs `san`: [docs/SIMULATED_INSTRUMENTS.md](docs/SIMULATED_INSTRUMENTS.md).

```text
bc.fg.load_arb_csv scripts/examples/arb_sine.csv
bc.config.bind ps visa GPIB0::1::INSTR
bc.mm.fault_inject overload
```

---

## LLM-assisted chat (GUI)

The Lab Automation Chat UI can turn natural language into **allow-listed** `bc.*` commands. Configuration lives in **`config/testbenchconfig.json`** under `llm`, `azure_openai`, `openai_api`, `local_gguf`, and `rag`. You can also edit these from **Settings → LLM settings** in the GUI.

### Providers

Set `llm.provider` to one of:

| Value | Backend | Typical use |
|-------|---------|-------------|
| `azure_openai` | Azure OpenAI (deployment + API key in `azure_openai`) | Cloud, enterprise |
| `openai` | OpenAI-compatible API (`openai_api`; optional `base_url` for proxies) | Cloud |
| `local_gguf` | [llama.cpp](https://github.com/ggerganov/llama.cpp) via `llama-cpp-python` | Offline / air-gapped |

**Azure:** set `endpoint` (resource base URL or full portal URL — the app normalizes it), `deployment`, `api_version`, and `api_key` (or use env vars where supported).

**OpenAI:** set `api_key` and `model` (`gpt-4o-mini`, etc.). Leave `base_url` empty for the default API.

**Local GGUF:** set `local_gguf.model_path` to a `.gguf` file. Tune `n_ctx`, `n_gpu_layers`, `n_threads`, `max_tokens`, and `chat_format` (`qwen`, `chatml`, `llama-3`, …). Download helpers: `scripts/download_gguf.py`. If the native loader crashes, **restart the GUI** before retrying.

`llm.timeout_seconds` (5–600) applies per LLM request.

### Plan vs Agent mode

Toggle in the chat toolbar or set `llm.chat_mode` to `plan` or `agent`.

- **Plan** — LLM returns a proposed command list and short analysis. Review, then type **`run`**, **`go`**, or **`execute`** to run the plan, or **`discard`** / **`cancel`** to drop it. Unsafe commands (`config`, `raw`) are blocked from auto-execution.
- **Agent** — When the model returns commands that look like direct bench lines, they may run immediately (still subject to validation).

The LLM only sees commands from your registry’s **`ACTIONS`** lists (built into the prompt allow-list).

### Automation loop (repair + multi-turn)

When enabled in `llm.automation_loop` (Settings → LLM settings):

| Setting | Behavior |
|---------|----------|
| **Automation loop** | Master switch for auto-repair and multi-turn context |
| **Max repair iterations** | Cap on automatic repair attempts per user request (default 3) |
| **Auto-repair on failure** | After FAIL/error steps, call the LLM for a minimal fix plan |
| **Closed-loop Agent** | In Agent mode, run repair commands automatically (Plan mode always reviews first) |
| **Multi-turn history** | Prior request/plan/outcome turns included in the next plan prompt |

**Chat commands:**

- `repair` / `repair <hint>` — generate a repair plan from the last captured results (always shown for review in Plan style).
- `clear llm` — reset multi-turn conversation context.

In **Agent** mode with the loop enabled, a failed LLM sequence triggers repair automatically (up to the iteration cap), then post-run **analyze** runs when the loop finishes.

### Analyze (post-run)

After a sequence (especially from an LLM plan), the app can send captured results back to the model for a summary and optional plot spec.

- Type **`analyze`** or **`analyze <follow-up question>`** to re-run analysis on the last results.
- **`llm.auto_analyze_results`** (default `true`) controls automatic analyze after LLM-driven sequences.

### RAG (retrieval-augmented generation)

1. Add text files under **`rag_docs/`** (SOPs, calibration notes, datasheets). See [rag_docs/README.md](rag_docs/README.md).
2. On first LLM call, the app builds an in-memory index over chunked documents.
3. Top chunks are prepended as `CONTEXT:` in Plan and Analyze prompts.

| `rag.backend` | Engine |
|---------------|--------|
| `tfidf` (default) | TF–IDF, no extra packages |
| `embeddings` | `sentence-transformers` semantic search (optional install) |

```powershell
pip install sentence-transformers
```

**Chat commands:**

```text
rag status
rag reload
rag <search query>
```

Configure in `testbenchconfig.json` → `rag`: `enabled`, `backend`, `embedding_model`, `dir`, `extensions`, `top_k`, `chunk_chars`, `max_context_chars`.

### Structured plans with pass/fail checks

In **Plan** mode, the LLM can return schema v2 JSON:

```json
{
  "commands": ["bc.ps.set_voltage 3.3", "bc.ps.on"],
  "analysis": "Apply 3.3 V and verify",
  "checks": [
    {"type": "limit", "command": "bc.ps.measure_voltage", "min": 3.0, "max": 3.6},
    {"type": "assert", "command": "bc.mm.measure_voltage", "expected": 5.25, "tolerance": 0.1}
  ],
  "pass_criteria": ["Supply output within 3.3 V ±10%"]
}
```

`checks` are converted to `assert` / `limit` script lines and appended to the proposed plan. Set `llm.plan_include_checks` to `false` to keep only raw `commands`.

Ask naturally: *“Power the DUT at 3.3 V and verify voltage is in range”* — the model should emit both setup commands and checks.

### LLM-related GUI tips

- Use **simulated** instruments (`simulate: true`) while iterating on prompts and plans.
- Put repeatable tests in **sequences** or `.bench` files once the LLM output stabilizes.
- Do **not** commit real API keys; use env vars or local config overrides.

---

## How to add new instruments

Adding a **new instrument family** (new category key) is a small, repeatable change set.

### 1. Implement the instrument package

Under **`src/testbench/instruments/<your_folder>/`**:

- **`base.py`** — optional abstract base (subclass `InstrumentBase` from `instruments/base.py`) declaring device-specific methods.
- **`simulated.py`** — **`SimulatedYourDevice`** class used when `simulate: true` in config. It should:
  - define **`ACTIONS`**: `dict` mapping each action name to a one-line description (drives `help` and LLM allow-list),
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
| **`run_gui.bat`** | Launch GUI with `.venv` Python. |
| **`setup.bat`** | Create venv, install deps, smoke-test imports. |
| **`src/testbench/`** | Core package: parser, registry, runner, limit/assert, session reports, LLM, RAG, plotting, instruments. |
| **`src/testbench/__main__.py`** | Headless CLI (`python -m testbench run …`). |
| **`config/testbenchconfig.json`** | Bench + LLM + RAG configuration. |
| **`config/gui_chat_fonts.json`** | Optional UI font overrides (Settings → Fonts). |
| **`config/test_sequences.json`** | Saved command sequences (GUI). |
| **`rag_docs/`** | Reference documents for RAG. |
| **`scripts/examples/`** | Example `.bench` automation scripts. |
| **`logs/plot_data/`** | CSV logs for large plot series. |
| **`assets/`** | Application icon (`lab_chat_icon.png` / `.ico`). |
| **`docs/`** | **BENCHCONFIG.md**, **SIMULATED_INSTRUMENTS.md**, etc. |
| **`tests/`** | Automated tests. |

---

## Quick reference

### GUI

```powershell
.\setup.bat
.\run_gui.bat
```

### Headless test

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m testbench run scripts\examples\dmm_check.bench --report logs\report.json
```

### Pytest

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\pytest.exe tests\
```

Optional hardware stack: **`requirements-hardware.txt`** (PyVISA, pyserial) when prompted by `setup.bat`, or `install_hardware.bat` later. Simulation mode does not require VISA.
