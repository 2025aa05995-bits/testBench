"""Paths and defaults shared by the Lab Automation Chat GUI."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIALOG_START = str(_REPO_ROOT / "config")

_GUI_FONT_PREFS_FILE = str(_REPO_ROOT / "config" / "gui_chat_fonts.json")

DEFAULT_GUI_FONT_PREFS = {
    "chat_family": "Consolas",
    "chat_size": 10,
    "input_family": "Consolas",
    "input_size": 11,
    "suggestions_family": "Consolas",
    "suggestions_size": 10,
    "status_family": "Segoe UI",
    "status_size": 13,
    "menu_family": "Segoe UI",
    "menu_size": 13,
}

EXAMPLE_POWER_CYCLE_COMMANDS = ["bc.ps.on", "delay 1", "bc.ps.off"]


def gui_font_prefs_file() -> str:
    return _GUI_FONT_PREFS_FILE
