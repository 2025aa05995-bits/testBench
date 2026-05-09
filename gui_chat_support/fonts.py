"""Load/save optional GUI font overrides (config/gui_chat_fonts.json)."""

import json
import os
from typing import Any, Dict

from .constants import DEFAULT_GUI_FONT_PREFS, gui_font_prefs_file


def load_gui_font_preferences() -> Dict[str, Any]:
    out = dict(DEFAULT_GUI_FONT_PREFS)
    path = gui_font_prefs_file()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        return out
    if not isinstance(data, dict):
        return out
    for key, default in DEFAULT_GUI_FONT_PREFS.items():
        if key not in data:
            continue
        v = data[key]
        if key.endswith("_size"):
            try:
                out[key] = max(6, min(48, int(v)))
            except (TypeError, ValueError):
                pass
        else:
            if isinstance(v, str) and v.strip():
                out[key] = v.strip()
    return out


def save_gui_font_preferences(prefs: dict) -> None:
    path = gui_font_prefs_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    to_save = {k: prefs.get(k, DEFAULT_GUI_FONT_PREFS[k]) for k in DEFAULT_GUI_FONT_PREFS}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)
