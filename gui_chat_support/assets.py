"""Application icon path and Windows taskbar identity."""

import os
import sys
from typing import Optional


def gui_app_assets_dir(repo_root_file: str) -> str:
    """Directory containing lab_chat_icon.ico / .png (next to gui_chat.py)."""
    return os.path.join(os.path.dirname(os.path.abspath(repo_root_file)), "assets")


def gui_app_icon_path_preferred(repo_root_file: str) -> Optional[str]:
    """
    Path to window/taskbar icon: prefer multi-size ``lab_chat_icon.ico`` on Windows,
    else ``lab_chat_icon.png``, else any file that exists.
    """
    d = gui_app_assets_dir(repo_root_file)
    ico = os.path.join(d, "lab_chat_icon.ico")
    png = os.path.join(d, "lab_chat_icon.png")
    if sys.platform == "win32" and os.path.isfile(ico):
        return ico
    if os.path.isfile(png):
        return png
    if os.path.isfile(ico):
        return ico
    return None


def windows_set_app_user_model_id() -> None:
    """Pin the taskbar identity to this app instead of python.exe (Windows 7+)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "TestBench.LabAutomationChat.1.0"
        )
    except Exception:
        pass
