# VS Code Setup for TestBench Project

## Quick Start

### 1. Install Virtual Environment
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Run Tasks (Ctrl+Shift+P > Tasks: Run Task)
- **Install dependencies** - Installs all required packages
- **Run GUI Chat** - Launches the PyQt5 GUI chat interface
- **Run Bench CLI** - Runs the sample bench script under `scripts/`
- **Run Tests** - Executes all pytest tests
- **Test Simulated Instruments** - Tests the instrument simulation layer
- **Format Code** - Formats code using black
- **Lint Code** - Checks code style with flake8
- **Type Check** - Validates types with mypy
- **Clean Build Artifacts** - Removes cache and test artifacts

### 3. Debug Configurations (F5)
- **Python: GUI Chat (PyQt5)** - Debug the GUI application
- **Python: Current File** - Debug the currently open file
- **Python: Bench CLI** - Debug the CLI tool
- **Python: Tests (pytest)** - Debug tests with pytest

### 4. Settings
- Python interpreter: `.venv/Scripts/python.exe`
- Auto-format on save: enabled (black)
- Linting: flake8 enabled
- Type checking: basic mode (mypy)
- Max line length: 120 characters

### 5. Recommended Extensions
VS Code will prompt you to install recommended extensions:
- Python (Microsoft)
- Pylance (Microsoft)
- Black Formatter (Microsoft)
- Flake8 (Microsoft)
- Test Explorer (hbenl)

## Project Structure
```
testBench/
├── .vscode/           # VS Code configuration
├── .venv/             # Python virtual environment
├── config/            # Default testbenchconfig.json
├── docs/              # Configuration and other docs
├── scripts/           # Runnable utilities (e.g. bench demo)
├── src/
│   └── testbench/     # Main package (registry, config, parsing, plotting)
│       ├── instruments/
│       ├── command_parser.py
│       ├── chat_plotting.py
│       └── command_registry.py
├── tests/             # Pytest and manual test scripts
├── gui_chat.py        # PyQt5/tkinter chat interface (repo root entry)
└── requirements.txt   # Dependencies
```

## Usage

### Running the GUI Chat
```bash
# Using VS Code task (Ctrl+Shift+P > Run Task)
# Or from terminal:
python gui_chat.py
```

### Running Tests
```bash
# Using VS Code task or:
pytest -v tests
```

### Available Commands
```
help                    # Show all instruments and commands
help <category>         # Show commands for specific instrument
bench.<cat>.<action>    # Execute a command (e.g., bench.ps.on True)
```

## Keyboard Shortcuts
- `F5` - Start debugging
- `Ctrl+Shift+P` - Command palette (run tasks, etc.)
- `Ctrl+K Ctrl+F` - Format document
- `Ctrl+Shift+T` - Run test explorer
