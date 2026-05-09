"""Generate gui_chat_support/qt_main.py and tk_main.py from gui_chat_monolith.py (repo root).

The monolith file is the legacy single-file snapshot used only for regeneration; the runtime
entry point is gui_chat.py (thin launcher).
"""
from pathlib import Path
import textwrap
import re

ROOT = Path(__file__).resolve().parent.parent
MONOLITH = ROOT / "gui_chat_monolith.py"
SRC = MONOLITH.read_text(encoding="utf-8")
lines = SRC.splitlines(keepends=True)

# --- PyQt: lines 412-1871 (after `if PYQT_AVAILABLE:`)
qt_slice = "".join(lines[411:1871])
qt_slice = textwrap.dedent(qt_slice)

QT_HEADER = '''\
"""PyQt5 Lab Automation Chat window and entrypoint."""

import json
import os
import re
import sys
import threading
from datetime import datetime
from functools import partial
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QListWidget,
    QFileDialog,
    QStatusBar,
    QDialog,
    QLabel,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QMessageBox,
    QDialogButtonBox,
    QStyleFactory,
    QStackedWidget,
)
from PyQt5.QtCore import Qt, QEvent, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QTextCursor, QTextCharFormat

from testbench.chat_plotting import (
    plot_data_csv_path,
    render_plot_to_png_bytes,
    should_log_plot_data_as_csv,
    try_extract_plot_command,
    write_plot_series_csv,
)
from testbench.command_parser import CommandParser, handle_help, normalize_llm_command_prefix
from testbench.command_registry import CommandRegistry
from testbench._paths import default_config_file
from testbench.llm_chat import (
    PROVIDER_AZURE,
    PROVIDER_OPENAI,
    llm_analyze_results,
    llm_chat_to_plan,
    llm_connection_test,
)

from gui_chat_support.assets import gui_app_assets_dir, gui_app_icon_path_preferred, windows_set_app_user_model_id
from gui_chat_support.constants import CONFIG_DIALOG_START, DEFAULT_GUI_FONT_PREFS, EXAMPLE_POWER_CYCLE_COMMANDS
from gui_chat_support.fonts import load_gui_font_preferences, save_gui_font_preferences
from gui_chat_support.sequences import load_test_sequences, save_test_sequences
from gui_chat_support.command_helpers import (
    parse_analyze_keyword,
    looks_like_direct_command,
    try_parse_quoted_heading,
)
from gui_chat_support.command_completer import CommandCompleter
from gui_chat_support.run_command import run_chat_command

_REPO_FILE = str(Path(__file__).resolve().parent.parent / "gui_chat.py")


'''

_repls = [
    ("_looks_like_direct_command", "looks_like_direct_command"),
    ("_CONFIG_DIALOG_START", "CONFIG_DIALOG_START"),
    ("_DEFAULT_GUI_FONT_PREFS", "DEFAULT_GUI_FONT_PREFS"),
    ("_EXAMPLE_POWER_CYCLE_COMMANDS", "EXAMPLE_POWER_CYCLE_COMMANDS"),
    ("_gui_app_assets_dir()", "gui_app_assets_dir(_REPO_FILE)"),
    ("_gui_app_icon_path_preferred()", "gui_app_icon_path_preferred(_REPO_FILE)"),
    ("_windows_set_app_user_model_id()", "windows_set_app_user_model_id()"),
]

for old, new in _repls:
    qt_slice = qt_slice.replace(old, new)

(ROOT / "gui_chat_support" / "qt_main.py").write_text(QT_HEADER + qt_slice, encoding="utf-8")

# --- Tk: lines 1873-3224 (`try:` through end of `except ImportError` block)
tk_slice = "".join(lines[1872:3224])
tk_slice = textwrap.dedent(tk_slice)

TK_HEADER = '''\
"""Tkinter fallback Lab Automation Chat window and entrypoint."""

import json
import os
import re
import sys
import threading
from datetime import datetime
from functools import partial
from pathlib import Path

from testbench.chat_plotting import (
    plot_data_csv_path,
    render_plot_to_png_bytes,
    should_log_plot_data_as_csv,
    try_extract_plot_command,
    write_plot_series_csv,
)
from testbench.command_parser import CommandParser, handle_help, normalize_llm_command_prefix
from testbench.command_registry import CommandRegistry
from testbench._paths import default_config_file
from testbench.llm_chat import (
    PROVIDER_AZURE,
    PROVIDER_OPENAI,
    llm_analyze_results,
    llm_chat_to_plan,
    llm_connection_test,
)

from gui_chat_support.assets import gui_app_assets_dir, gui_app_icon_path_preferred, windows_set_app_user_model_id
from gui_chat_support.constants import CONFIG_DIALOG_START, DEFAULT_GUI_FONT_PREFS, EXAMPLE_POWER_CYCLE_COMMANDS
from gui_chat_support.fonts import load_gui_font_preferences, save_gui_font_preferences
from gui_chat_support.sequences import load_test_sequences, save_test_sequences
from gui_chat_support.command_helpers import (
    parse_analyze_keyword,
    looks_like_direct_command,
    try_parse_quoted_heading,
)
from gui_chat_support.command_completer import CommandCompleter
from gui_chat_support.run_command import run_chat_command

_REPO_FILE = str(Path(__file__).resolve().parent.parent / "gui_chat.py")


'''

for old, new in _repls:
    tk_slice = tk_slice.replace(old, new)

(ROOT / "gui_chat_support" / "tk_main.py").write_text(TK_HEADER + tk_slice, encoding="utf-8")
print("Wrote qt_main.py and tk_main.py")
