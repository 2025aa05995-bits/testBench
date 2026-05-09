"""Lab Automation Chat — thin entry; implementations live in ``gui_chat_support/``."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, 'src'))
sys.path.insert(0, _ROOT)

from gui_chat_support.command_completer import CommandCompleter

__all__ = ['CommandCompleter', 'main']


def main() -> None:
    try:
        import PyQt5.QtWidgets  # noqa: F401
    except ImportError:
        from gui_chat_support.tk_main import main as _run
    else:
        from gui_chat_support.qt_main import main as _run
    _run()


if __name__ == '__main__':
    main()
